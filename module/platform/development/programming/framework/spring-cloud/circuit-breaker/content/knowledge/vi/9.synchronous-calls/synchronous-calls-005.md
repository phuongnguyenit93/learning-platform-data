# Xử lý exception wrapper và xác định nguyên nhân gốc

Khi một lời gọi đồng bộ đến dịch vụ phụ thuộc thất bại, ngoại lệ mà circuit breaker nhận được đôi khi không phải ngoại lệ ban đầu. Thư viện HTTP, proxy, reflection hoặc mã chờ kết quả từ Future có thể bọc lỗi gốc trong một ngoại lệ khác. Nếu Resilience4j chỉ được cấu hình để ghi nhận SocketTimeoutException nhưng lời gọi thực tế ném ResourceAccessException hoặc ExecutionException, quy tắc phân loại có thể không khớp.

Để circuit breaker phản ánh đúng sức khỏe của phụ thuộc, cần hiểu chuỗi ngoại lệ, xác định kiểu ngoại lệ thực sự thoát khỏi phần công việc được bảo vệ và chỉ mở lớp bọc khi đó là wrapper kỹ thuật đã biết. Không nên bỏ toàn bộ ngữ cảnh của ngoại lệ hoặc coi mọi nguyên nhân sâu nhất là lỗi phụ thuộc.

## Vì sao ngoại lệ bị bọc?

Một ngoại lệ có thể đi qua nhiều lớp trước khi tới circuit breaker:

1. HTTP client gặp lỗi mạng hoặc timeout.
2. Adapter chuyển lỗi kỹ thuật thành ngoại lệ của miền dịch vụ.
3. Proxy hoặc reflection bọc ngoại lệ trong một wrapper.
4. Supplier được truyền vào circuit breaker ném ngoại lệ cuối cùng ra ngoài.

Ví dụ, dịch vụ tồn kho không phản hồi đúng hạn. HTTP client ném SocketTimeoutException, adapter chuyển thành InventoryUnavailableException, rồi một lớp thực thi bất đồng bộ được chờ bằng Future.get() có thể đưa lỗi vào ExecutionException. Khi đó, circuit breaker nhìn thấy ExecutionException ở ranh giới gọi, không trực tiếp nhìn thấy SocketTimeoutException.

~~~mermaid
flowchart TD
    A[Lời gọi dịch vụ tồn kho] --> B[HTTP client]
    B -->|SocketTimeoutException| C[Adapter]
    C -->|InventoryUnavailableException| D[Future hoặc proxy]
    D -->|ExecutionException / wrapper| E[Supplier được bảo vệ]
    E --> F[Circuit breaker phân loại Throwable]
    F --> G[Fallback hoặc truyền lỗi]
~~~

Circuit breaker phân loại ngoại lệ được ném ra từ phần công việc mà nó bảo vệ. Vì vậy, điều quan trọng là quan sát ngoại lệ tại đúng ranh giới này thay vì chỉ suy luận từ lỗi đầu tiên xuất hiện trong log.

## Các wrapper thường gặp trong lời gọi đồng bộ

Một số lớp Java thường được dùng để bọc lỗi:

| Wrapper | Ngữ cảnh thường gặp | Cách lấy nguyên nhân bên trong |
|---|---|---|
| CompletionException | Lấy kết quả từ CompletableFuture bằng join(). | getCause() |
| ExecutionException | Lấy kết quả từ Future bằng get(). | getCause() |
| InvocationTargetException | Gọi phương thức qua reflection. | getTargetException() hoặc getCause() |
| UndeclaredThrowableException | Lời gọi qua JDK dynamic proxy gặp checked exception không khai báo trong chữ ký. | getUndeclaredThrowable() hoặc getCause() |

Các wrapper này thường không mang ý nghĩa nghiệp vụ riêng; chúng cho biết lỗi đã đi qua cơ chế thực thi nào. Có thể mở chúng để phân loại lỗi gốc khi cần.

Tuy nhiên, không phải ngoại lệ nào có cause cũng chỉ là wrapper. ResourceAccessException của Spring có thể diễn đạt lỗi truy cập tài nguyên và bọc IOException; InventoryUnavailableException có thể là ngoại lệ miền có ý nghĩa đối với ứng dụng. Không nên mở mọi lớp tùy ý vì có thể làm mất thông tin hữu ích hoặc phân loại sai một lỗi nghiệp vụ có nguyên nhân sâu hơn.

## Xác định nguyên nhân gốc một cách có kiểm soát

Một cách an toàn là chỉ mở các wrapper kỹ thuật đã biết, giới hạn độ sâu và phát hiện vòng lặp trong chuỗi cause. Ví dụ:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.UndeclaredThrowableException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public final class ExceptionUtils {

    private static final int MAX_UNWRAP_DEPTH = 16;

    private ExceptionUtils() {
    }

    public static Throwable unwrapKnownWrappers(Throwable error) {
        Throwable current = error;

        Set<Throwable> visited = Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>()
        );

        for (int depth = 0;
             current != null && depth < MAX_UNWRAP_DEPTH && visited.add(current);
             depth++) {

            Throwable next = null;

            if (current instanceof CompletionException
                    || current instanceof ExecutionException) {
                next = current.getCause();
            } else if (current instanceof InvocationTargetException) {
                next = ((InvocationTargetException) current).getTargetException();
            } else if (current instanceof UndeclaredThrowableException) {
                next = ((UndeclaredThrowableException) current)
                        .getUndeclaredThrowable();
            }

            if (next == null || next == current) {
                break;
            }

            current = next;
        }

        return current;
    }
}
~~~

Hàm này chỉ mở bốn loại wrapper đã biết. Nó dừng khi không còn cause, khi cause trỏ lại chính đối tượng hiện tại, khi gặp một đối tượng đã duyệt hoặc khi đạt giới hạn độ sâu. Việc dùng identity set giúp phát hiện vòng lặp theo chính đối tượng Throwable, không phụ thuộc vào cách lớp ngoại lệ triển khai equals().

Tên hàm là unwrapKnownWrappers vì nó không cố tìm một “nguyên nhân gốc” bằng cách đi sâu qua mọi cause. Nếu gặp một ngoại lệ miền như InventoryUnavailableException hoặc một wrapper có ý nghĩa như ResourceAccessException, hàm giữ nguyên ngoại lệ đó. Lớp gọi có thể quyết định phân loại theo loại ngoại lệ này hoặc kiểm tra cause trong một quy tắc riêng.

## Dùng predicate để phân loại ngoại lệ trong Resilience4j

Khi cần phân loại theo nguyên nhân bên trong wrapper, có thể dùng các predicate của CircuitBreakerConfig. Predicate cho phép kiểm tra Throwable thực tế mà circuit breaker nhận được và mở wrapper đã biết trước khi quyết định.

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeoutException;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .recordException(error -> {
            Throwable cause = ExceptionUtils.unwrapKnownWrappers(error);

            return cause instanceof SocketTimeoutException
                    || cause instanceof ConnectException
                    || cause instanceof TimeoutException
                    || cause instanceof IOException
                    || cause instanceof InventoryUnavailableException;
        })
        .ignoreException(error -> {
            Throwable cause = ExceptionUtils.unwrapKnownWrappers(error);

            return cause instanceof InvalidSkuException
                    || cause instanceof ProductNotFoundException;
        })
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .build();
~~~

Trong ví dụ, lỗi kết nối, timeout và InventoryUnavailableException được tính là thất bại. InvalidSkuException và ProductNotFoundException bị bỏ qua vì chúng biểu diễn kết quả nghiệp vụ hoặc đầu vào không hợp lệ, không phản ánh tình trạng phụ thuộc.

Predicate ignore có ưu tiên khi một ngoại lệ đồng thời khớp điều kiện bỏ qua và điều kiện ghi nhận. Ngoại lệ bị bỏ qua không làm tăng số lời gọi thành công hoặc thất bại. Nếu record predicate trả về false và ngoại lệ không bị ignore, Resilience4j xem lời gọi là thành công trong thống kê.

Khi dùng predicate, hãy thống nhất quy tắc với recordExceptions và ignoreExceptions nếu dự án đang khai báo cả hai. Tránh tạo nhiều chính sách chồng chéo khiến người đọc khó xác định ngoại lệ nào thực sự được ghi nhận. Với mỗi instance, nên có một quy tắc phân loại rõ ràng và được kiểm thử bằng các kiểu Throwable thực tế.

## Chuyển đổi lỗi kỹ thuật thành ngoại lệ miền tại ranh giới client

Trong nhiều ứng dụng, cách dễ duy trì hơn là chuyển lỗi của thư viện bên dưới thành ngoại lệ miền có ý nghĩa tại adapter. Như vậy, circuit breaker có thể phân loại một số kiểu ngoại lệ ổn định mà không phụ thuộc vào thư viện HTTP cụ thể.

Ví dụ với client đồng bộ của Spring:

~~~java
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

public class InventoryRemoteClient {

    private final RestClient restClient;

    public InventoryRemoteClient(RestClient restClient) {
        this.restClient = restClient;
    }

    public Inventory find(String sku) {
        try {
            return restClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(Inventory.class);
        } catch (ResourceAccessException ex) {
            throw new InventoryUnavailableException(
                    "Cannot access inventory service", ex
            );
        }
    }
}
~~~

InventoryUnavailableException là ngoại lệ miền minh họa của ứng dụng. Adapter giữ nguyên ResourceAccessException làm cause để log và chẩn đoán, nhưng caller nhận một kiểu lỗi ổn định thể hiện phụ thuộc tồn kho không sẵn sàng.

Cách làm này có một lợi ích quan trọng: circuit breaker không cần biết từng chi tiết triển khai của HTTP client. Khi đổi thư viện hoặc thay đổi cấu trúc wrapper, adapter vẫn có thể giữ hợp đồng ngoại lệ của miền dịch vụ.

Không nên chuyển mọi ResourceAccessException thành cùng một lỗi nếu nguyên nhân có ý nghĩa khác nhau. Ví dụ, lỗi cấu hình URL hoặc chứng chỉ có thể cần cảnh báo vận hành riêng. Hãy giữ cause gốc và, nếu cần, phân loại thành các ngoại lệ miền cụ thể như InventoryTimeoutException hoặc InventoryConnectionException.

## Xử lý wrapper khi chờ Future trong mã đồng bộ

Một phương thức đồng bộ có thể gọi Future.get() để chờ kết quả. Khi tác vụ bên trong thất bại, get() ném ExecutionException và nguyên nhân thật nằm trong getCause().

~~~java
public Inventory findInventory(String sku) {
    try {
        return inventoryExecutor.submit(
                () -> inventoryClient.find(sku)
        ).get();
    } catch (ExecutionException ex) {
        Throwable cause = ExceptionUtils.unwrapKnownWrappers(ex);
        throw new InventoryUnavailableException(
                "Inventory lookup failed", cause
        );
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new InventoryRequestInterruptedException(
                "Inventory lookup was interrupted", ex
        );
    }
}
~~~

Đoạn mã minh họa cách chuyển lỗi tác vụ thành ngoại lệ miền và giữ trạng thái interrupt. InterruptedException có ý nghĩa điều khiển luồng: thread hiện tại bị yêu cầu dừng chờ. Không nên coi nó như timeout của dịch vụ phụ thuộc hoặc nuốt nó rồi tiếp tục xử lý như bình thường.

Với CompletableFuture.join(), lỗi tác vụ thường được ném dưới dạng CompletionException. Có thể mở wrapper này để xem lỗi bên trong, nhưng cần giữ ngoại lệ gốc trong cause chain để phục vụ chẩn đoán.

Nếu ứng dụng không cần chờ đồng bộ, hãy cân nhắc giữ luồng xử lý bất đồng bộ thay vì gọi get() hoặc join(). Việc chờ chặn thread có thể làm giảm năng lực phục vụ và tạo thêm áp lực khi dịch vụ phụ thuộc chậm.

## Kết hợp nguyên nhân gốc với fallback

Spring Cloud CircuitBreaker cung cấp fallback function nhận Throwable khi lời gọi thất bại hoặc circuit breaker từ chối lời gọi. Fallback có thể mở các wrapper đã biết để chọn phản hồi phù hợp, nhưng vẫn nên ghi log ngoại lệ ngoài cùng để giữ ngữ cảnh.

~~~java
public Inventory findInventory(String sku) {
    return circuitBreakerFactory.create("inventory-read").run(
            () -> inventoryClient.find(sku),
            error -> {
                Throwable cause =
                        ExceptionUtils.unwrapKnownWrappers(error);

                if (cause instanceof ProductNotFoundException) {
                    return Inventory.notFound(sku);
                }

                if (cause instanceof CallNotPermittedException) {
                    return Inventory.unavailable(sku);
                }

                log.warn(
                        "Inventory lookup failed; cause type: {}",
                        cause == null ? "unknown" : cause.getClass().getName(),
                        error
                );

                return Inventory.unavailable(sku);
            }
    );
}
~~~

ProductNotFoundException có thể được bỏ qua trong thống kê circuit breaker nhưng vẫn được chuyển thành kết quả not-found ở fallback. CallNotPermittedException biểu thị circuit breaker đang từ chối lời gọi vì mạch OPEN; nó là kết quả của cơ chế bảo vệ tại chỗ, không phải một lần gọi mới đến dịch vụ từ xa thất bại.

Fallback nên trả kết quả phù hợp với nghiệp vụ. Với màn hình tham khảo, có thể trả cache gần nhất kèm trạng thái dữ liệu cũ. Với thao tác xác nhận tồn kho hoặc thanh toán, không nên giả định thao tác thành công khi không nhận được kết quả từ phụ thuộc. Hãy phân biệt dữ liệu không tồn tại, dữ liệu tạm thời không sẵn sàng và kết quả chưa xác định.

## Không làm mất ngữ cảnh khi tìm nguyên nhân gốc

Một số cách xử lý có thể làm chẩn đoán khó hơn:

| Cách xử lý | Rủi ro | Cách tốt hơn |
|---|---|---|
| Mở mọi cause cho đến khi không còn cause | Có thể bỏ qua ngoại lệ miền mang ý nghĩa quan trọng. | Chỉ mở wrapper kỹ thuật đã biết. |
| Chỉ log root cause | Mất thông tin lớp bọc cho biết tầng nào chuyển đổi lỗi. | Ghi cả ngoại lệ ngoài cùng và kiểu nguyên nhân đã phân loại. |
| Cấu hình recordExceptions theo một kiểu lỗi gốc duy nhất | Wrapper khiến predicate không khớp. | Chuẩn hóa tại adapter hoặc dùng predicate có mở wrapper có kiểm soát. |
| Bắt ngoại lệ rồi trả giá trị mặc định trong supplier | Circuit breaker thấy kết quả thành công và không ghi nhận lỗi. | Để ngoại lệ cần thống kê thoát khỏi supplier rồi xử lý ở fallback. |
| Bỏ qua mọi RuntimeException | Lỗi lập trình hoặc lỗi phụ thuộc có thể bị che giấu. | Bỏ qua các kiểu nghiệp vụ cụ thể đã xác định. |
| Nuốt InterruptedException | Mất tín hiệu yêu cầu dừng thread. | Khôi phục cờ interrupt và truyền lỗi theo hợp đồng của ứng dụng. |

Nên ghi log với các trường như circuit breaker ID, kiểu ngoại lệ ngoài cùng, kiểu nguyên nhân được phân loại và request correlation ID. Correlation ID dùng cho log theo request; không đưa nó vào tên circuit breaker hoặc nhãn metrics vì sẽ tạo cardinality cao.

## Kiểm thử việc mở wrapper và phân loại

Kiểm thử nên xác nhận cả kết quả phân loại lẫn ngoại lệ được truyền tới caller. Có thể tạo các lời gọi đồng bộ giả lập ném trực tiếp hoặc bọc các kiểu ngoại lệ:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Supplier ném trực tiếp SocketTimeoutException | Predicate nhận diện timeout và ghi nhận thất bại. |
| Supplier ném ExecutionException chứa IOException | Hàm unwrap mở wrapper đã biết và phân loại lỗi kết nối. |
| Supplier ném CompletionException chứa SocketTimeoutException | Nguyên nhân bên trong được nhận diện. |
| Supplier ném InventoryUnavailableException có cause là IOException | Ngoại lệ miền được giữ nguyên và được ghi nhận theo chính sách. |
| Supplier ném ProductNotFoundException | Ngoại lệ bị bỏ qua trong thống kê nhưng vẫn được truyền tới fallback. |
| Supplier bắt timeout rồi trả Inventory.unavailable() | Circuit breaker thấy kết quả bình thường; kiểm thử xác nhận đây không phải lỗi được ghi nhận. |
| Supplier ném CallNotPermittedException do mạch OPEN | Fallback xử lý việc từ chối, không coi đó là một lần gọi phụ thuộc mới. |
| Thread bị interrupt khi chờ Future.get() | Cờ interrupt được khôi phục và không bị nuốt. |

Trong kiểm thử circuit breaker, dùng cửa sổ nhỏ và số mẫu tối thiểu phù hợp để quan sát trạng thái CLOSED chuyển sang OPEN. Đồng thời kiểm tra failure count, ignored count hoặc các metrics tương ứng của phiên bản Resilience4j đang dùng. Không chỉ kiểm tra giá trị fallback cuối cùng, vì cùng một fallback có thể được trả cho nhiều nguyên nhân khác nhau.

## Quy trình xử lý exception wrapper

1. Ghi nhận kiểu Throwable ngoài cùng tại ranh giới supplier được bảo vệ.
2. Xem cause chain và xác định wrapper kỹ thuật có thể mở an toàn.
3. Giữ nguyên ngoại lệ miền hoặc wrapper có ý nghĩa như ResourceAccessException nếu chúng cung cấp ngữ cảnh hữu ích.
4. Chuẩn hóa lỗi thư viện thành ngoại lệ miền tại adapter khi cần một hợp đồng ổn định.
5. Cấu hình record/ignore predicate theo kiểu lỗi thực sự tới circuit breaker.
6. Dùng fallback để ánh xạ lỗi sang phản hồi nghiệp vụ, đồng thời log đủ ngữ cảnh.
7. Kiểm thử lỗi trực tiếp, lỗi bọc, lỗi bị bắt, lỗi nghiệp vụ và interrupt.

Với Spring Cloud CircuitBreaker tích hợp Resilience4j, xác định đúng exception wrapper và nguyên nhân gốc giúp bộ ngắt mạch ghi nhận đúng lỗi của dịch vụ phụ thuộc. Hãy mở wrapper kỹ thuật có chủ đích, giữ lại ngữ cảnh miền và cấu hình predicate tại đúng ranh giới lời gọi. Khi đó, circuit breaker có thể phản ứng với timeout hoặc lỗi kết nối mà không nhầm lẫn chúng với kết quả nghiệp vụ hay lỗi điều khiển luồng.

