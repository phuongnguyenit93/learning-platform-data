# Truyền hàm fallback nhận Throwable

Trong Spring Cloud CircuitBreaker, một lời gọi được bảo vệ thường có hai phần: thao tác chính cần thực hiện và hàm dự phòng sẽ chạy khi thao tác chính không thể cung cấp kết quả. Với API đồng bộ, hàm dự phòng được truyền dưới dạng `Function<Throwable, T>`. Tham số `Throwable` cho biết nguyên nhân khiến lời gọi chính thất bại hoặc bị Circuit Breaker từ chối; giá trị trả về `T` là kết quả mà ứng dụng gửi tiếp cho bên gọi.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, cách truyền hàm này giúp ứng dụng phản ứng phù hợp khi dịch vụ phụ thuộc chậm hoặc không khả dụng. Thay vì dùng một giá trị mặc định cho mọi tình huống, fallback có thể phân loại lỗi, ghi log, lấy dữ liệu gần nhất từ cache hoặc chuyển lỗi nghiệp vụ về đúng nơi xử lý.

## 1. Hợp đồng của hàm fallback

API đồng bộ của Spring Cloud CircuitBreaker có dạng khái quát:

```java
<T> T run(
        Supplier<T> toRun,
        Function<Throwable, T> fallback
);
```

Hai tham số có vai trò khác nhau:

| Tham số | Kiểu | Vai trò |
| --- | --- | --- |
| `toRun` | `Supplier<T>` | Cung cấp thao tác chính và tạo ra kết quả kiểu `T` |
| `fallback` | `Function<Throwable, T>` | Nhận nguyên nhân lỗi và tạo kết quả thay thế cùng kiểu `T` |

`Supplier<T>` không nhận tham số đầu vào. Nó chỉ mô tả thao tác cần thực hiện khi Circuit Breaker cho phép lời gọi đi qua. `Function<Throwable, T>` nhận một đối số là nguyên nhân lỗi và phải trả về một giá trị tương thích với kiểu kết quả của thao tác chính.

Ví dụ, nếu thao tác lấy tồn kho trả về `InventoryResult`, hàm fallback cũng phải trả về `InventoryResult`:

```java
Function<Throwable, InventoryResult> fallback =
        failure -> InventoryResult.unavailable();

InventoryResult result = circuitBreaker.run(
        () -> inventoryClient.find("SKU-100"),
        fallback
);
```

Biểu thức `failure -> ...` là lambda của `Function`. Biến `failure` chính là đối tượng `Throwable` mà API truyền vào. Ứng dụng có thể đọc kiểu exception, thông điệp hoặc nguyên nhân gốc để quyết định cách phản hồi.

Điểm cần nhớ là fallback nhận **một nguyên nhân lỗi** và trả về **một kết quả cùng kiểu với lời gọi chính**. Nó không phải một `Supplier` thứ hai và cũng không phải một hàm không tham số.

## 2. Truyền fallback bằng lambda

Giả sử dịch vụ Đơn hàng gọi dịch vụ Kho để đọc tồn kho. Khi dịch vụ Kho không phản hồi, ứng dụng có thể trả trạng thái chưa xác định tồn kho. Ta dùng `CircuitBreakerFactory` để tạo Circuit Breaker và truyền lambda làm fallback:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult find(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> inventoryClient.find(sku),
                failure -> InventoryResult.unavailable(sku)
        );
    }
}
```

Trong ví dụ:

1. `circuitBreakerFactory.create("inventory")` lấy Circuit Breaker có tên `inventory`.
2. Lambda `() -> inventoryClient.find(sku)` mô tả lời gọi chính đến dịch vụ Kho.
3. Lambda `failure -> InventoryResult.unavailable(sku)` là fallback nhận nguyên nhân lỗi và tạo kết quả dự phòng.
4. Cả lời gọi chính và fallback đều trả về `InventoryResult`, nên phương thức `find` giữ được một kiểu kết quả nhất quán.

Đoạn mã tập trung vào cách truyền hàm; `InventoryClient` và `InventoryResult` là các thành phần nghiệp vụ của ví dụ. Instance `inventory` cần được cấu hình trong application.yml theo cấu hình Circuit Breaker mà ứng dụng sử dụng.

Fallback trong ví dụ chưa dùng đến biến `failure`, nhưng chữ ký lambda vẫn nhận biến đó. Khi cần phân loại nguyên nhân, ta sử dụng chính biến này thay vì bỏ qua nó.

## 3. Phân loại Throwable để chọn phản hồi

Kiểu `Throwable` cho phép fallback nhận nhiều loại nguyên nhân. Chẳng hạn, lời gọi có thể thất bại do timeout, lỗi kết nối, lỗi máy chủ hoặc do Circuit Breaker đang OPEN. Các trường hợp này không nhất thiết cần cùng một phản hồi.

Với Resilience4j, khi Circuit Breaker đang OPEN và chặn lời gọi, ứng dụng thường nhận `CallNotPermittedException`. Thao tác chính không được gọi đến dịch vụ phụ thuộc. Khi lỗi đến từ HTTP client, nguyên nhân có thể là exception của client; khi có TimeLimiter, lỗi có thể liên quan đến timeout.

Ví dụ, fallback có thể phân loại một số tình huống:

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.web.client.ResourceAccessException;

private InventoryResult fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof CallNotPermittedException) {
        log.warn("Circuit Breaker đang mở; bỏ qua lời gọi lấy tồn kho");
        return inventoryCache.findRecent(sku)
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }

    if (failure instanceof ResourceAccessException) {
        log.warn("Không kết nối được dịch vụ Kho");
        return inventoryCache.findRecent(sku)
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }

    if (failure instanceof InventoryNotFoundException) {
        throw (InventoryNotFoundException) failure;
    }

    throw new IllegalStateException("Không thể lấy tồn kho", failure);
}
```

Phương thức trên nhận cả `sku` và `Throwable` vì đây là phương thức nghiệp vụ thông thường mà lambda sẽ gọi. Có thể truyền nó bằng:

```java
return circuitBreaker.run(
        () -> inventoryClient.find(sku),
        failure -> fallbackInventory(sku, failure)
);
```

Một số điểm trong cách phân loại:

- **CallNotPermittedException**: Circuit Breaker đã chặn lời gọi vì mạch OPEN. Có thể dùng cache hoặc trả trạng thái tạm thời không sẵn sàng.
- **ResourceAccessException**: ví dụ về lỗi truy cập tài nguyên hoặc kết nối từ Spring Web. Có thể dùng dữ liệu gần nhất nếu nghiệp vụ cho phép.
- **InventoryNotFoundException**: ví dụ về lỗi nghiệp vụ. Nếu “không tìm thấy sản phẩm” phải được báo đúng nghĩa, không nên biến nó thành phản hồi “dịch vụ Kho tạm thời không khả dụng”.
- **Nguyên nhân chưa nhận diện**: giữ nguyên nguyên nhân trong exception mới để tầng xử lý cao hơn còn khả năng chẩn đoán.

Các kiểu exception cụ thể phụ thuộc thư viện và client mà ứng dụng dùng. Hãy phân loại theo loại exception thực tế của ứng dụng; không nên giả định mọi lỗi HTTP đều có cùng kiểu.

## 4. Vì sao phải xử lý Throwable có chọn lọc?

`Throwable` là lớp gốc của cả `Exception` và `Error`. Việc API dùng `Throwable` giúp hàm fallback nhận được một kiểu nguyên nhân rộng, nhưng không có nghĩa ứng dụng nên nuốt mọi đối tượng nhận được.

Các lỗi nghiệp vụ, lỗi kết nối và lỗi timeout có thể cần cách phản hồi khác nhau. Ngược lại, những lỗi nghiêm trọng của JVM như một số loại `Error` thường không nên bị chuyển thành kết quả dự phòng bình thường. Nếu fallback trả về “không có tồn kho” cho mọi lỗi, một lỗi nghiêm trọng có thể bị che giấu và khiến hệ thống tiếp tục chạy với trạng thái sai.

Khi cần chuyển tiếp lỗi, có thể giữ nguyên exception runtime hoặc Error, đồng thời bọc checked exception trong một exception phù hợp:

```java
private static RuntimeException propagate(Throwable failure) {
    if (failure instanceof RuntimeException) {
        return (RuntimeException) failure;
    }
    if (failure instanceof Error) {
        throw (Error) failure;
    }
    return new IllegalStateException("Lời gọi phụ thuộc thất bại", failure);
}
```

Sau đó fallback có thể xử lý các lỗi dự kiến và chuyển tiếp những lỗi còn lại:

```java
private InventoryResult fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof CallNotPermittedException
            || failure instanceof ResourceAccessException) {
        return inventoryCache.findRecent(sku)
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }

    throw propagate(failure);
}
```

Trong mã thực tế, cần chọn chính sách theo nghiệp vụ và thư viện đang dùng. Ví dụ trên minh họa nguyên tắc: chỉ chuyển một số lỗi đã dự kiến thành kết quả dự phòng; giữ nguyên nguyên nhân của lỗi ngoài dự kiến để việc xử lý và quan sát không mất thông tin.

## 5. Dùng method reference hoặc phương thức riêng

Khi fallback có nhiều nhánh xử lý, đặt logic trong một phương thức riêng giúp lời gọi chính dễ đọc hơn. Nếu phương thức nhận đúng một tham số `Throwable` và trả về đúng kiểu kết quả, có thể truyền method reference:

```java
private InventoryResult fallback(Throwable failure) {
    if (failure instanceof CallNotPermittedException) {
        return InventoryResult.unavailable();
    }
    throw propagate(failure);
}

public InventoryResult find(String sku) {
    CircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("inventory");

    return circuitBreaker.run(
            () -> inventoryClient.find(sku),
            this::fallback
    );
}
```

`this::fallback` tương đương với lambda `failure -> this.fallback(failure)`. Cả hai đều phù hợp với `Function<Throwable, InventoryResult>`.

Nếu fallback cần thêm dữ liệu của lời gọi như `sku`, có thể dùng lambda để đóng gói biến đó:

```java
return circuitBreaker.run(
        () -> inventoryClient.find(sku),
        failure -> fallbackInventory(sku, failure)
);
```

Không thể truyền trực tiếp `this::fallbackInventory` trong ví dụ này nếu phương thức nhận hai tham số `String` và `Throwable`, vì `Function<Throwable, T>` chỉ truyền một đối số. Lambda đóng vai trò nối tham số ngữ cảnh `sku` với đối số `failure` do Circuit Breaker cung cấp.

## 6. Fallback trong lời gọi reactive

Với ứng dụng reactive, kiểu kết quả không phải một giá trị đồng bộ `T` mà thường là một publisher như `Mono<T>`. API reactive của Spring Cloud CircuitBreaker nhận publisher chính và một hàm fallback có dạng `Function<Throwable, Publisher<T>>` (thường dùng `Mono<T>` hoặc `Flux<T>` tùy kiểu lời gọi).

Ví dụ với `Mono<InventoryResult>`:

```java
import reactor.core.publisher.Mono;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;

public Mono<InventoryResult> findReactive(String sku) {
    ReactiveCircuitBreaker circuitBreaker =
            reactiveCircuitBreakerFactory.create("inventory");

    Mono<InventoryResult> primary =
            webClient.get()
                    .uri("/items/{sku}", sku)
                    .retrieve()
                    .bodyToMono(InventoryResult.class);

    return circuitBreaker.run(
            primary,
            failure -> {
                if (failure instanceof CallNotPermittedException) {
                    return inventoryCache.findRecentReactive(sku)
                            .defaultIfEmpty(InventoryResult.unavailable(sku));
                }
                return Mono.just(InventoryResult.unavailable(sku));
            }
    );
}
```

Ở đây, fallback nhận `Throwable` nhưng phải trả về publisher có kiểu tương thích với publisher chính. `Mono.just(...)` tạo một `Mono` chứa kết quả dự phòng. Nếu dùng `Flux<T>` cho lời gọi chính, fallback phải trả publisher tương thích với kiểu đó theo chữ ký API được dùng.

Không gọi `block()` trong fallback reactive chỉ để lấy giá trị đồng bộ. Hãy tiếp tục nối các thao tác vào chuỗi publisher để tránh chặn luồng xử lý reactive. Nếu cache cũng là một lời gọi bất đồng bộ, trả trực tiếp publisher của cache như trong ví dụ.

## 7. Những lỗi thường gặp khi truyền hàm fallback

| Cách viết hoặc cách xử lý | Vấn đề | Cách sửa |
| --- | --- | --- |
| Truyền `() -> fallback()` | Đây là lambda không tham số, không khớp `Function<Throwable, T>` | Dùng `failure -> fallback(failure)` |
| Fallback trả kiểu khác kiểu của lời gọi chính | Không khớp kiểu `T` của API | Trả về cùng kiểu kết quả hoặc kiểu con tương thích |
| Bỏ qua biến `Throwable` trong mọi trường hợp | Mất thông tin để phân loại lỗi và chẩn đoán | Dùng nguyên nhân để chọn phản hồi phù hợp |
| Trả dữ liệu mặc định cho mọi exception | Có thể che giấu lỗi nghiệp vụ hoặc lỗi lập trình | Chỉ xử lý các loại lỗi đã dự kiến; chuyển tiếp lỗi còn lại |
| Gọi lại cùng dịch vụ phụ thuộc trong fallback | Có thể tạo vòng lặp hoặc tiếp tục tăng tải khi phụ thuộc đang lỗi | Dùng cache, kết quả giới hạn hoặc phản hồi không khả dụng |
| Log toàn bộ thông tin nhạy cảm từ exception | Có thể làm lộ dữ liệu trong log | Ghi mã lỗi, tên phụ thuộc và thông tin đã được lọc |
| Dùng lambda fallback đồng bộ cho API reactive | Kiểu trả về không còn là publisher mong đợi | Trả về `Mono<T>` hoặc publisher phù hợp |

Một fallback cũng có thể tự phát sinh exception, ví dụ cache bị lỗi hoặc logic dự phòng ném exception. Khi đó, lời gọi tổng thể vẫn có thể thất bại và lỗi fallback sẽ được chuyển lên tầng gọi. Vì vậy, fallback nên ngắn gọn, có ít phụ thuộc và có cách xử lý lỗi riêng phù hợp.

## 8. Theo dõi và kiểm tra hành vi fallback

Để biết fallback đang bảo vệ dịch vụ hiệu quả hay che giấu sự cố, nên theo dõi ít nhất:

- Số lần lời gọi chính thất bại theo từng loại nguyên nhân.
- Số lần fallback được gọi, phân tách theo tên Circuit Breaker và loại lỗi.
- Số lần bị từ chối do mạch OPEN, thường nhận diện qua `CallNotPermittedException`.
- Tỷ lệ fallback trả kết quả thành công và tỷ lệ fallback tự thất bại.
- Độ trễ của lời gọi chính, fallback và phản hồi cuối cùng.

Khi kiểm tra, có thể mô phỏng ba trường hợp: lời gọi chính thành công thì fallback không được dùng; lời gọi chính ném một exception đã được hỗ trợ thì fallback nhận đúng exception và trả kết quả dự phòng; Circuit Breaker OPEN thì lời gọi bị chặn và fallback xử lý nguyên nhân từ chối. Ngoài ra, cần kiểm tra một lỗi không được dự kiến có được chuyển tiếp đúng cách hay bị biến thành kết quả mặc định.

Không nên chỉ đếm số phản hồi HTTP thành công ở API ngoài cùng. Nếu fallback luôn trả HTTP 200, dashboard có thể trông khỏe trong khi dịch vụ Kho đã ngừng phục vụ. Cần kết hợp số liệu fallback với trạng thái Circuit Breaker, tỷ lệ lỗi và sức khỏe của dịch vụ phụ thuộc.

## 9. Ghi nhớ

Khi dùng common API của Spring Cloud CircuitBreaker, hãy truyền lời gọi chính bằng `Supplier<T>` và hàm dự phòng bằng `Function<Throwable, T>`. Tham số `Throwable` cung cấp nguyên nhân để fallback lựa chọn cách phản hồi; giá trị trả về phải cùng kiểu với kết quả của lời gọi chính. Dùng lambda khi cần kết hợp thêm dữ liệu ngữ cảnh, dùng method reference khi phương thức fallback có đúng chữ ký một tham số, và chỉ chuyển các lỗi đã dự kiến thành kết quả dự phòng.

Với lời gọi reactive, vẫn nhận nguyên nhân qua `Throwable`, nhưng fallback phải trả về publisher phù hợp. Trong cả hai mô hình, giữ lại thông tin lỗi, phân biệt lỗi hạ tầng với lỗi nghiệp vụ và theo dõi tần suất fallback sẽ giúp Circuit Breaker bảo vệ dịch vụ mà không che khuất tình trạng thực tế của hệ thống.
