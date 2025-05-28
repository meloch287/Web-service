import numpy as np
import matplotlib.pyplot as plt
import logging
import matplotlib

# логи 
logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def plot_expected_load(hours: np.ndarray, combined_density: np.ndarray, anomaly_windows: list, show_plot=True):
    """Визуализация ожидаемой нагрузки."""
    try:
        plt.figure(figsize=(10, 6))
        plt.plot(hours, combined_density / combined_density.sum() * 24, label='Ожидаемая нагрузка')
        for window in anomaly_windows:
            plt.axvspan(window[0], window[1], color='yellow', alpha=0.2,
                        label='Окно аномалии' if window == anomaly_windows[0] else "")
        plt.title('Ожидаемое распределение нагрузки с аномалиями')
        plt.xlabel('Часы суток')
        plt.ylabel('Плотность')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig("fixed_combined_intensity_with_anomaly.png")
        
        if show_plot:
            plt.show()
        else:
            plt.close() 
            
        logging.info("График распределения нагрузки сохранен")
    except Exception as e:
        logging.error(f"Ошибка при визуализации нагрузки: {str(e)}")
        print(f"Ошибка при визуализации нагрузки: {e}")
        plt.close()  

def plot_actual_load(send_times: np.ndarray, total_sim_seconds: float,
                     bad_transaction_hours: list, good_transaction_hours: list,
                     combined_density: np.ndarray, hours: np.ndarray, anomaly_windows: list,
                     show_plot=True):
    """Визуализация фактической нагрузки."""
    try:
        actual_hours = send_times / total_sim_seconds * 24
        bad_hours = np.array(bad_transaction_hours)
        good_hours = np.array(good_transaction_hours)
        
        combined_density_normalized = combined_density / np.trapezoid(combined_density, hours)

        plt.figure(figsize=(10, 6))
        plt.hist(actual_hours, bins=50, alpha=0.3, color='blue', density=True, label='Фактическое распределение')
        if len(bad_hours) > 0:
            plt.hist(bad_hours, bins=30, alpha=0.5, color='red', density=True, label='Плохие транзакции')
        plt.plot(hours, combined_density_normalized, 'k-', linewidth=2, label='Ожидаемая нагрузка')
        for window in anomaly_windows:
            plt.axvspan(window[0], window[1], color='yellow', alpha=0.2,
                        label='Окно аномалии' if window == anomaly_windows[0] else "")
        plt.title('Распределение транзакций по времени')
        plt.xlabel('Часы суток')
        plt.ylabel('Плотность')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig("fixed_transaction_distribution.png")
        
        if show_plot:
            plt.show()
        else:
            plt.close()  
            
        logging.info("График распределения транзакций сохранен")
    except Exception as e:
        logging.error(f"Ошибка при визуализации распределения транзакций: {str(e)}")
        print(f"Ошибка при визуализации распределения транзакций: {e}")
        plt.close() 

def close_all_figures():
    """Закрыть все открытые фигуры matplotlib."""
    plt.close('all')
