# recordExceptionPredicate và quy tắc phân loại tùy chỉnh

## Vì sao cần phân loại ngoại lệ?

Trong Spring Cloud Circuit Breaker dùng Resilience4j, Circuit Breaker quyết định có mở mạch hay không dựa trên kết quả lời gọi được ghi nhận trong sliding window. Mặc định, một ngoại lệ thoát ra từ lời gọi được xem là thất bại. Tuy nhiên, không phải ngoại lệ nào cũng cho thấy dịch vụ phụ thuộc đang suy giảm.

Ví dụ, timeout kết nối hoặc lỗi máy chủ 503 thường là dấu hiệu cần bảo vệ hệ thống. Ngược lại, lỗi dữ liệu đầu vào không hợp lệ có thể là lỗi nghiệp vụ do client gửi lên. Nếu tính mọi lỗi đầu vào là lỗi hạ tầng, một đợt request sai định dạng có thể khiến Circuit Breaker mở dù dịch vụ phụ thuộc vẫn khỏe.

Resilience4j cho phép xác định quy tắc phân loại bằng predicate. Predicate nhận một `Throwable` và trả về `true` hoặc `false`. Trong cấu hình, quy tắc ghi nhận ngoại lệ thường được gọi là `recordExceptionPredicate`; Java builder cung cấp API để đặt predicate này cùng predicate bỏ qua ngoại lệ.

## Quy tắc đánh giá một ngoại lệ

Khi lời gọi kết thúc bằng ngoại lệ, Resilience4j áp dụng quy tắc phân loại theo thứ tự:

1. Nếu predicate bỏ qua ngoại lệ trả về `true`, ngoại lệ bị bỏ qua và không tham gia tỷ lệ thành công hoặc thất bại.
2. Nếu ngoại lệ không bị bỏ qua và predicate ghi nhận lỗi trả về `true`, lời gọi được tính là thất bại.
3. Nếu ngoại lệ không bị bỏ qua nhưng predicate ghi nhận lỗi trả về `false`, lời gọi được tính là thành công đối với thống kê Circuit Breaker.

Việc phân loại chỉ ảnh hưởng đến số liệu và quyết định trạng thái của Circuit Breaker. Ngoại lệ bị bỏ qua hoặc được phân loại là thành công vẫn có thể tiếp tục truyền tới caller; predicate không tự biến ngoại lệ thành response thành công và không thay thế fallback.

| Kết quả predicate bỏ qua | Kết quả predicate ghi nhận lỗi | Cách Circuit Breaker tính |
| --- | --- | --- |
| `true` | Không cần đánh giá | Bỏ qua, không tăng số thành công hoặc thất bại. |
| `false` | `true` | Ghi nhận thất bại. |
| `false` | `false` | Ghi nhận thành công. |

Mặc định, nếu không cấu hình danh sách hoặc predicate riêng, ngoại lệ được ghi nhận là thất bại và không có ngoại lệ nào bị bỏ qua. Nếu dùng `recordExceptions`, các loại ngoại lệ khớp danh sách được ghi nhận; ngoại lệ không khớp được xem là thành công, trừ khi khớp quy tắc bỏ qua. `ignoreExceptions` có độ ưu tiên cao hơn việc ghi nhận lỗi.

## Viết recordExceptionPredicate tùy chỉnh

Giả sử dịch vụ danh mục có các loại lỗi sau:

- `TimeoutException` và `ConnectException`: dịch vụ không phản hồi hoặc không thể kết nối, cần tính là lỗi.
- `ServiceUnavailableException`: dịch vụ phụ thuộc báo không khả dụng, cần tính là lỗi.
- `InvalidCatalogRequestException`: request sai dữ liệu nghiệp vụ, không nên làm tăng tỷ lệ lỗi hạ tầng.
- Các ngoại lệ còn lại: cần được phân loại theo chính sách của ứng dụng; ví dụ dưới đây không tự động coi chúng là lỗi.

Có thể viết predicate tường minh:

```java
import java.net.ConnectException;
import java.util.concurrent.TimeoutException;
import java.util.function.Predicate;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

Predicate<Throwable> recordFailure = error ->
    error instanceof TimeoutException
        || error instanceof ConnectException
        || error instanceof ServiceUnavailableException;

Predicate<Throwable> ignoreFailure =
    InvalidCatalogRequestException.class::isInstance;

CircuitBreakerConfig circuitBreakerConfig = CircuitBreakerConfig.custom()
    .recordException(recordFailure)
    .ignoreException(ignoreFailure)
    .failureRateThreshold(50)
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .build();
```

`ServiceUnavailableException` và `InvalidCatalogRequestException` là các kiểu ngoại lệ do ứng dụng định nghĩa trong ví dụ. Predicate `recordFailure` chỉ ghi nhận ba nhóm lỗi đã nêu. Ngoại lệ khác không khớp predicate và không bị bỏ qua sẽ được tính là thành công đối với Circuit Breaker. Đây là chính sách có chủ đích của ví dụ; trong hệ thống thực tế, cần quyết định rõ cách xử lý các lỗi chưa biết thay vì vô tình phân loại chúng thành thành công.

Nếu muốn mặc định ghi nhận mọi ngoại lệ trừ một số ngoại lệ nghiệp vụ, hãy giữ quy tắc ghi nhận mặc định và chỉ khai báo predicate bỏ qua. Cách này thường an toàn hơn khi ứng dụng có nhiều loại lỗi hạ tầng mới có thể xuất hiện trong tương lai.

## Tích hợp predicate vào Spring Cloud Circuit Breaker

Khi dùng starter Resilience4j, nên tùy chỉnh factory được Spring tạo bằng `Customizer`. Ví dụ cấu hình predicate mặc định cho các Circuit Breaker do factory tạo:

```java
@Configuration(proxyBeanMethods = false)
public class CatalogCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> catalogCircuitBreakerCustomizer() {
        return factory -> factory.configureDefault(id -> {
            CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .recordException(error ->
                    error instanceof TimeoutException
                        || error instanceof ConnectException
                        || error instanceof ServiceUnavailableException
                )
                .ignoreException(
                    InvalidCatalogRequestException.class::isInstance
                )
                .failureRateThreshold(50)
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .build();

            return new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(config)
                .build();
        });
    }
}
```

Các import cần thiết gồm `Customizer`, `Resilience4JCircuitBreakerFactory`, `Resilience4JConfigBuilder`, `CircuitBreakerConfig`, `TimeoutException` và `ConnectException`. Tên API builder phải khớp phiên bản Resilience4j và Spring Cloud Circuit Breaker đang được quản lý bởi BOM của ứng dụng. Trong Java builder, `recordException(...)` đặt predicate ghi nhận lỗi; tên khái niệm hoặc thuộc tính cấu hình tương ứng thường được mô tả là `recordExceptionPredicate`.

`configureDefault` áp dụng quy tắc mặc định cho các ID được factory tạo. Nếu mỗi dịch vụ cần một chính sách riêng, hãy cấu hình theo ID thay vì áp dụng cùng một predicate cho mọi dịch vụ. Ví dụ, dịch vụ thanh toán có thể cần ghi nhận lỗi từ cổng thanh toán, trong khi dịch vụ tìm kiếm có thể phân loại một số lỗi truy vấn thành lỗi nghiệp vụ.

Không nên khai báo thêm một factory Resilience4j mới chỉ để thay predicate. Starter đã cung cấp factory và auto-configuration; customizer là điểm mở rộng phù hợp để bổ sung cấu hình.

## Phân loại ngoại lệ theo lớp và quan hệ kế thừa

Predicate thường dùng `instanceof` hoặc `Class::isInstance` để xét cả lớp con. Điều này hữu ích khi nhiều ngoại lệ cụ thể cùng kế thừa một lớp cơ sở:

```java
Predicate<Throwable> isRemoteServiceFailure = error ->
    error instanceof RemoteServiceException
        || error instanceof TimeoutException;
```

Nếu `ServiceUnavailableException` kế thừa `RemoteServiceException`, predicate trên cũng nhận diện ngoại lệ đó. Hãy thiết kế cây ngoại lệ theo ý nghĩa ổn định, chẳng hạn tách `RemoteServiceException` khỏi `BusinessRuleException`, để predicate không phải liệt kê quá nhiều lớp rời rạc.

Tránh phân loại chỉ dựa vào tên lớp dạng chuỗi hoặc nội dung message. Message có thể thay đổi theo thư viện, ngôn ngữ hoặc phiên bản dịch vụ; tên lớp cũng có thể thay đổi khi refactor. Kiểm tra kiểu ngoại lệ và dữ liệu có cấu trúc thường đáng tin cậy hơn.

## Xử lý ngoại lệ bị bọc

Trong lời gọi bất đồng bộ, ngoại lệ thực tế có thể được bọc bởi `CompletionException` hoặc `ExecutionException`. Nếu predicate chỉ kiểm tra lớp của ngoại lệ ngoài cùng, nó có thể không nhận ra timeout hoặc lỗi kết nối nằm trong `cause`.

Có thể chuẩn hóa ngoại lệ trước khi phân loại:

```java
private static Throwable unwrap(Throwable error) {
    while ((error instanceof CompletionException
            || error instanceof ExecutionException)
            && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}

Predicate<Throwable> recordFailure = error -> {
    Throwable cause = unwrap(error);
    return cause instanceof TimeoutException
        || cause instanceof ConnectException
        || cause instanceof ServiceUnavailableException;
};
```

Hãy chỉ mở các wrapper đã biết và dừng khi không còn `cause`. Không duyệt vô hạn hoặc giả định mọi `cause` đều là lỗi gốc. Trong hệ thống dùng HTTP client, có thể cần kiểm tra thêm loại exception do client phát ra, chẳng hạn lỗi kết nối, lỗi đọc response hoặc lỗi trạng thái HTTP. Nên viết test cho đúng kiểu ngoại lệ mà client thực tế ném ra.

## Phân biệt recordExceptionPredicate và recordResult

Predicate ngoại lệ chỉ được gọi khi supplier kết thúc bằng `Throwable`. Một số client lại trả về một đối tượng response có trạng thái lỗi mà không ném exception. Khi đó Circuit Breaker có thể nhìn thấy một kết quả bình thường nếu ứng dụng không chuyển trạng thái HTTP thành exception.

Ví dụ, một client tùy chỉnh có thể trả về `CatalogResponse` với mã 503. Nếu muốn mã này được tính là lỗi, có thể dùng predicate kết quả (`recordResult`) nếu phiên bản Resilience4j đang dùng hỗ trợ:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .recordResult(result ->
        result instanceof CatalogResponse response
            && response.statusCode() >= 500
    )
    .build();
```

Trong ví dụ, `CatalogResponse` là kiểu response do ứng dụng định nghĩa. `recordResult` đánh giá giá trị trả về; `recordException` đánh giá ngoại lệ. Nếu HTTP client đã ném exception cho status 5xx, hãy phân loại exception đó thay vì thêm quy tắc result trùng lặp. Không phải mọi lỗi nghiệp vụ hoặc mã 4xx đều nên mở circuit breaker; hãy quyết định theo hợp đồng dịch vụ.

## Quan hệ giữa phân loại lỗi và fallback

Fallback xử lý kết quả ở tầng gọi, còn predicate quyết định cách Circuit Breaker ghi nhận ngoại lệ. Hai cơ chế này có thể cùng xuất hiện trong một lời gọi:

```java
public CatalogItem find(String id) {
    return circuitBreakerFactory.create("catalog").run(
        () -> catalogClient.find(id),
        error -> {
            log.warn("Catalog call failed for id={}", id, error);
            return CatalogItem.unavailable(id);
        }
    );
}
```

Nếu lỗi kết nối khớp `recordExceptionPredicate`, Circuit Breaker ghi nhận thất bại rồi fallback có thể trả phản hồi thay thế. Nếu lỗi đầu vào khớp predicate bỏ qua, Circuit Breaker không tăng tỷ lệ lỗi; tuy vậy exception vẫn có thể đi vào fallback theo hợp đồng của lời gọi được bọc. Vì thế, không suy ra số lỗi Circuit Breaker từ số lần fallback chạy.

Fallback cần giữ đúng ngữ nghĩa nghiệp vụ. `unavailable` nên thể hiện rõ dữ liệu chưa xác định hoặc dịch vụ tạm thời không sẵn sàng; không nên trả một đối tượng rỗng khiến tầng trên tưởng rằng không có bản ghi tương ứng.

## Kiểm thử quy tắc phân loại

Predicate là logic nghiệp vụ của chính sách bảo vệ, nên cần kiểm thử từng nhóm ngoại lệ. Có thể kiểm tra trực tiếp predicate trước, sau đó kiểm tra Circuit Breaker với các lời gọi giả lập để xác nhận số liệu:

| Trường hợp | Predicate bỏ qua | Predicate ghi nhận lỗi | Kết quả mong đợi |
| --- | --- | --- | --- |
| Timeout kết nối | `false` | `true` | Tăng số thất bại. |
| Lỗi dịch vụ 503 | `false` | `true` | Tăng số thất bại. |
| Request sai dữ liệu | `true` | Không xét | Không tăng số thành công hoặc thất bại. |
| Ngoại lệ không nằm trong nhóm được ghi nhận | `false` | `false` | Được tính là thành công đối với thống kê. |
| `CompletionException` bọc timeout | `false` sau unwrap | `true` sau unwrap | Tăng số thất bại. |

Ví dụ kiểm thử predicate bằng JUnit:

```java
@Test
void recordsTimeoutAsFailure() {
    Predicate<Throwable> recordFailure = error ->
        error instanceof TimeoutException;

    assertThat(recordFailure.test(new TimeoutException())).isTrue();
}

@Test
void ignoresInvalidRequest() {
    Predicate<Throwable> ignoreFailure =
        InvalidCatalogRequestException.class::isInstance;

    assertThat(ignoreFailure.test(new InvalidCatalogRequestException()))
        .isTrue();
}
```

Đây là ví dụ kiểm tra predicate độc lập; khi tích hợp thực tế, nên bổ sung kiểm thử Circuit Breaker xác nhận ignored exception không làm thay đổi failure rate và fallback có hành vi đúng. Đồng thời kiểm tra số lời gọi tối thiểu và sliding window để tránh kết luận sai khi chưa đủ mẫu.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Ghi nhận mọi exception là lỗi hạ tầng. | Lỗi request hoặc nghiệp vụ có thể làm mạch mở sai. | Xác định nhóm lỗi hạ tầng và nhóm cần bỏ qua. |
| Predicate chỉ kiểm tra exception ngoài cùng. | Không nhận ra timeout nằm trong `CompletionException` hoặc `ExecutionException`. | Mở wrapper đã biết trước khi phân loại. |
| Nghĩ exception bị ignore sẽ bị nuốt. | Caller vẫn có thể nhận exception hoặc chạy fallback. | Tách việc ghi nhận thống kê khỏi việc xử lý exception. |
| Dùng predicate trả về `false` như fallback. | Exception vẫn có thể truyền ra ngoài dù được tính như thành công trong thống kê. | Cấu hình fallback riêng theo hợp đồng gọi. |
| Chỉ phân loại exception trong khi client trả response lỗi bình thường. | HTTP 5xx có thể bị tính là thành công. | Dùng `recordResult` hoặc chuyển response lỗi thành exception phù hợp. |
| Trộn predicate và danh sách exception mà không kiểm tra quy tắc ưu tiên. | Chính sách thực tế khác với dự kiến. | Định nghĩa một quy tắc rõ ràng và kiểm thử trên đúng phiên bản thư viện. |

Một `recordExceptionPredicate` tốt phải phản ánh đúng ý nghĩa của lỗi đối với dịch vụ phụ thuộc. Khi phân biệt rõ ngoại lệ cần ghi nhận, ngoại lệ cần bỏ qua, response lỗi và fallback, Resilience4j có thể tính failure rate sát thực tế hơn và chỉ mở circuit breaker khi có tín hiệu suy giảm đáng tin cậy.
