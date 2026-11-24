# Đặt ngưỡng, thời gian và đơn vị Duration rõ ràng

Circuit breaker chỉ bảo vệ dịch vụ hiệu quả khi các ngưỡng và khoảng thời gian phản ánh đúng đặc tính của lời gọi phụ thuộc. Nếu ngưỡng lỗi quá thấp, một vài lỗi thoáng qua có thể làm mạch mở liên tục. Nếu ngưỡng quá cao hoặc cửa sổ cần quá nhiều mẫu, ứng dụng có thể tiếp tục gọi một dịch vụ đang hỏng trong thời gian dài. Nếu đặt nhầm đơn vị thời gian, timeout vài giây có thể biến thành vài mili giây hoặc vài phút.

Trong Spring Cloud CircuitBreaker với Resilience4j, cần xác định rõ các giá trị như `failureRateThreshold`, `slowCallRateThreshold`, `slowCallDurationThreshold`, `waitDurationInOpenState` và `timeoutDuration`. Các giá trị tỷ lệ là phần trăm; các khoảng thời gian nên được biểu diễn rõ bằng `java.time.Duration` trong Java hoặc hậu tố đơn vị trong YAML. Bài học này hướng dẫn cách đọc, chọn và kiểm tra những tham số đó trong module **SPRING_CLOUD_CIRCUIT_BREAKER**.

## 1. Phân biệt ngưỡng tỷ lệ, ngưỡng thời gian và số lượng mẫu

Các tham số cấu hình circuit breaker thường xuất hiện cùng nhau nhưng đại diện cho ba loại đại lượng khác nhau:

| Nhóm | Tham số tiêu biểu | Đơn vị | Tác dụng |
|---|---|---|---|
| Tỷ lệ | `failureRateThreshold` | Phần trăm (%) | Quy định tỷ lệ lỗi đủ để mở mạch. |
| Tỷ lệ | `slowCallRateThreshold` | Phần trăm (%) | Quy định tỷ lệ lời gọi chậm đủ để mở mạch. |
| Thời lượng | `slowCallDurationThreshold` | `Duration` | Xác định một lời gọi mất bao lâu thì được tính là chậm. |
| Thời lượng | `waitDurationInOpenState` | `Duration` | Quy định thời gian circuit breaker ở trạng thái `OPEN` trước khi cho phép thăm dò theo cơ chế cấu hình. |
| Số lượng | `slidingWindowSize` | Số lời gọi hoặc số giây tùy loại cửa sổ | Xác định phạm vi dữ liệu được dùng để thống kê. |
| Số lượng | `minimumNumberOfCalls` | Số lời gọi | Quy định số kết quả tối thiểu cần có trước khi đánh giá tỷ lệ. |
| Thời lượng | `timeoutDuration` | `Duration` | Giới hạn thời gian chờ của tác vụ bất đồng bộ được TimeLimiter hỗ trợ. |

Không được nhầm `slidingWindowSize` với `minimumNumberOfCalls`. Với cửa sổ `COUNT_BASED`, cả hai là số lượng lời gọi nhưng có ý nghĩa khác nhau. Với `TIME_BASED`, `slidingWindowSize` là số giây, trong khi `minimumNumberOfCalls` vẫn là số lượng kết quả tối thiểu.

Circuit breaker chỉ bắt đầu đánh giá tỷ lệ sau khi cửa sổ có đủ số mẫu tối thiểu. Khi đã đủ mẫu, mạch có thể mở nếu tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm đạt ngưỡng tương ứng. Ví dụ, nếu `failureRateThreshold` là 50%, 5 lỗi trong 10 lời gọi được ghi nhận sẽ đạt ngưỡng. Nếu chỉ có 4 kết quả, tỷ lệ quan sát được là 100% nhưng chưa đủ 10 mẫu thì chưa thể dùng tỷ lệ đó để ra quyết định theo cấu hình này.

## 2. Chọn failureRateThreshold và slowCallRateThreshold

`failureRateThreshold` là ngưỡng phần trăm lỗi. `slowCallRateThreshold` là ngưỡng phần trăm lời gọi chậm. Cả hai thường được đặt trong khoảng 0 đến 100. Giá trị càng thấp thì circuit breaker càng nhạy với lỗi hoặc độ trễ; giá trị càng cao thì cần tỷ lệ bất thường lớn hơn mới mở mạch.

Ví dụ:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        failureRateThreshold: 50
        slowCallRateThreshold: 60
```

Với cấu hình này, khi đã đủ mẫu, circuit breaker có thể mở nếu ít nhất 50% lời gọi được ghi nhận là thất bại hoặc ít nhất 60% lời gọi được xem là chậm. Đây là hai điều kiện độc lập; chỉ cần một trong hai tỷ lệ đạt ngưỡng là có thể kích hoạt mở mạch.

Tỷ lệ lỗi và tỷ lệ lời gọi chậm phản ánh hai kiểu suy giảm khác nhau:

- Dịch vụ phụ thuộc trả lỗi kết nối hoặc ngoại lệ có thể làm tỷ lệ lỗi tăng.
- Dịch vụ phụ thuộc vẫn trả kết quả thành công nhưng quá chậm có thể làm tỷ lệ lời gọi chậm tăng.

Ví dụ, một dịch vụ tồn kho trả HTTP 200 nhưng mất 4 giây để phản hồi. Nếu luồng đặt hàng chỉ có ngân sách 1 giây cho bước tra cứu tồn kho, lời gọi này vẫn gây hại dù không có lỗi HTTP. `slowCallDurationThreshold` sẽ xác định lời gọi đó có được tính là chậm hay không; `slowCallRateThreshold` quyết định tỷ lệ lời gọi chậm nào đủ để mở mạch.

Không nên chọn ngưỡng chỉ dựa trên một con số phổ biến. Hãy sử dụng số liệu độ trễ và tỷ lệ lỗi thực tế, mục tiêu thời gian phản hồi của nghiệp vụ và mức độ quan trọng của phụ thuộc. Với một dịch vụ đọc dữ liệu có thể dùng cache, ngưỡng có thể khác dịch vụ xác thực hoặc thanh toán.

## 3. Đặt slowCallDurationThreshold theo ngân sách độ trễ

`slowCallDurationThreshold` là thời lượng mà từ đó một lời gọi được phân loại là chậm. Giá trị này nên thấp hơn hoặc bằng phần ngân sách độ trễ mà ứng dụng dành cho phụ thuộc đó, có tính đến thời gian xử lý còn lại ở các bước khác.

Giả sử một API đặt hàng có mục tiêu phản hồi trong 1.500 ms. Sau khi trừ thời gian kiểm tra đầu vào, ghi cơ sở dữ liệu và tạo phản hồi, ứng dụng chỉ có thể dành khoảng 500 ms cho dịch vụ tồn kho. Có thể bắt đầu đánh giá với ngưỡng lời gọi chậm khoảng 400 ms hoặc 500 ms, rồi điều chỉnh theo số liệu thực tế.

| Ngân sách cho lời gọi phụ thuộc | Ngưỡng chậm minh họa | Nhận xét |
|---:|---:|---|
| 300 ms | 250 ms | Dùng cho lời gọi cần phản hồi rất nhanh. |
| 500 ms | 400 ms | Chừa một khoảng dự phòng trước khi hết ngân sách. |
| 2 giây | 1,5 giây | Có thể phù hợp với tác vụ có độ trễ cao hơn. |

Đây là ví dụ lựa chọn ban đầu, không phải ngưỡng chuẩn cho mọi hệ thống. Hãy đo phân phối độ trễ của client, xem xét p95/p99 và xác định mức chậm bắt đầu ảnh hưởng đến trải nghiệm hoặc làm cạn tài nguyên. Nếu ngưỡng đặt thấp hơn cả độ trễ bình thường, circuit breaker có thể mở ngay cả khi dịch vụ đang hoạt động tốt.

## 4. Đặt waitDurationInOpenState và hành vi thăm dò

`waitDurationInOpenState` quy định circuit breaker ở trạng thái `OPEN` trong bao lâu trước khi chuyển sang giai đoạn cho phép kiểm tra khả năng phục hồi. Với cấu hình thông thường, sau khoảng chờ này circuit breaker chuyển sang `HALF_OPEN` khi có lời gọi tiếp theo hoặc theo cơ chế tự động chuyển trạng thái nếu đã bật tùy chọn tương ứng.

Ví dụ:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

Mạch sẽ chờ 15 giây ở `OPEN`, sau đó cho phép tối đa 3 lời gọi thăm dò ở `HALF_OPEN`. Nếu các kết quả thăm dò đạt yêu cầu, mạch có thể trở lại `CLOSED`; nếu tiếp tục thất bại, mạch trở lại `OPEN` theo chính sách của Resilience4j.

Thời gian mở mạch quá ngắn có thể khiến ứng dụng thử lại liên tục khi dịch vụ phụ thuộc chưa kịp phục hồi. Thời gian quá dài lại trì hoãn cơ hội khôi phục lưu lượng dù dịch vụ đã khỏe mạnh. Hãy cân nhắc thời gian phục hồi thường thấy của phụ thuộc, chính sách retry ở các tầng khác và tác động của việc tiếp tục từ chối yêu cầu.

`waitDurationInOpenState` không phải timeout của một lời gọi. Nó không giới hạn thời gian HTTP request đang chạy. Timeout của client và `TimeLimiter` là các cấu hình riêng.

## 5. Biểu diễn thời gian trong YAML

Trong `application.yml`, các thuộc tính thời lượng của Resilience4j có thể được biểu diễn bằng cú pháp duration có hậu tố đơn vị. Nên luôn ghi rõ đơn vị để người đọc không phải suy đoán.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slowCallDurationThreshold: 750ms
        waitDurationInOpenState: 12s
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
```

Một số cách ghi thường dùng:

| Giá trị YAML | Ý nghĩa |
|---|---|
| `250ms` | 250 mili giây |
| `750ms` | 750 mili giây |
| `2s` | 2 giây |
| `3m` | 3 phút |
| `1h` | 1 giờ |
| `PT1.5S` | 1,5 giây theo định dạng ISO-8601 Duration |

Spring Boot hỗ trợ chuyển đổi các chuỗi thời lượng có đơn vị và định dạng ISO-8601 sang `java.time.Duration` cho các thuộc tính được bind. Khi thiếu hậu tố, giá trị số có thể được hiểu theo đơn vị mặc định của thuộc tính hoặc kiểu bind; điều đó khiến cấu hình khó đọc và dễ gây nhầm lẫn. Vì vậy, hãy viết rõ `ms`, `s`, `m` hoặc định dạng ISO-8601 thay vì chỉ ghi số trần.

Không dùng `500` để biểu thị 500 giây khi ý định là 500 mili giây. Hãy ghi `500ms`. Tương tự, không ghi `2` nếu ý định là 2 giây; hãy ghi `2s`.

## 6. Biểu diễn thời gian trong Java bằng Duration

Trong Java, dùng `java.time.Duration` để biểu diễn khoảng thời gian. API này giúp đơn vị trở nên rõ ràng ngay tại nơi tạo giá trị:

```java
import java.time.Duration;

Duration.ofMillis(500);       // 500 ms
Duration.ofSeconds(2);        // 2 s
Duration.ofMinutes(1);        // 1 phút
Duration.ofSeconds(1).plusMillis(250); // 1.25 s
Duration.parse("PT2S");      // 2 s theo ISO-8601
```

Ví dụ cấu hình Resilience4j bằng Java:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory> circuitBreakerDefaults() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                    .slidingWindowSize(20)
                    .minimumNumberOfCalls(10)
                    .failureRateThreshold(50)
                    .slowCallRateThreshold(60)
                    .slowCallDurationThreshold(Duration.ofMillis(750))
                    .waitDurationInOpenState(Duration.ofSeconds(12))
                    .permittedNumberOfCallsInHalfOpenState(3)
                    .build())
                .timeLimiterConfig(TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(2))
                    .build())
                .build()
        );
    }
}
```

Đọc các giá trị Java theo đơn vị:

- `Duration.ofMillis(750)` là 750 ms, tức 0,75 giây.
- `Duration.ofSeconds(12)` là thời gian mạch ở `OPEN` trước khi thăm dò.
- `Duration.ofSeconds(2)` là timeout của TimeLimiter cho tác vụ bất đồng bộ được tích hợp.

Khi cần chuyển từ một cấu hình bên ngoài sang Java, có thể dùng `Duration.parse("PT2S")` cho chuỗi ISO-8601. Với giá trị do người dùng nhập, nên kiểm tra định dạng và giới hạn hợp lệ trước khi đưa vào cấu hình. Tránh tự ghép số với đơn vị bằng phép nối chuỗi nếu có thể dùng API `Duration` rõ nghĩa.

## 7. Phân biệt timeout của client, TimeLimiter và circuit breaker

Ba cơ chế này thường cùng xuất hiện trong một lời gọi nhưng có trách nhiệm khác nhau:

| Cơ chế | Tham số ví dụ | Điều nó giới hạn |
|---|---|---|
| HTTP client timeout | connect timeout, response/read timeout | Thời gian chờ kết nối hoặc phản hồi từ máy chủ. |
| Resilience4j TimeLimiter | `timeoutDuration` | Thời gian chờ của tác vụ bất đồng bộ được bọc bởi TimeLimiter. |
| Circuit breaker | `slowCallDurationThreshold` | Mốc để phân loại một lời gọi là chậm trong thống kê. |
| Circuit breaker | `waitDurationInOpenState` | Thời gian giữ mạch ở trạng thái `OPEN`. |

Ví dụ, client có response timeout 3 giây, TimeLimiter có timeout 2 giây và `slowCallDurationThreshold` là 1 giây. Một lời gọi hoàn tất trong 1,4 giây có thể bị phân loại là chậm dù client chưa timeout. Một lời gọi kéo dài quá 2 giây có thể bị TimeLimiter kết thúc trước khi client chờ đủ 3 giây, nếu thao tác và cơ chế hủy hỗ trợ điều đó. Khi mạch đã `OPEN`, lời gọi mới có thể bị từ chối ngay mà không chờ timeout của client.

TimeLimiter không đảm bảo mọi thao tác I/O bên dưới đều bị hủy. Đặc biệt, việc timeout một `Future` không nhất thiết dừng được request mạng nếu HTTP client không hỗ trợ hủy đúng cách. Hãy cấu hình timeout tại client và kiểm tra hành vi giải phóng tài nguyên.

## 8. Một cấu hình YAML hoàn chỉnh cho phụ thuộc inventory

Ví dụ sau kết hợp cửa sổ, ngưỡng lỗi, ngưỡng lời gọi chậm và thời lượng rõ đơn vị:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 750ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 12s
        permittedNumberOfCallsInHalfOpenState: 3

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
```

Diễn giải cấu hình:

1. Resilience4j giữ tối đa 20 kết quả gần nhất và chỉ đánh giá tỷ lệ sau ít nhất 10 kết quả.
2. Mạch có thể mở khi tỷ lệ lỗi đạt 50% hoặc tỷ lệ lời gọi mất từ 750 ms trở lên đạt 60%.
3. Khi mạch mở, nó chờ 12 giây trước khi cho phép thăm dò theo cơ chế chuyển trạng thái.
4. Ở `HALF_OPEN`, tối đa 3 lời gọi được phép thăm dò.
5. TimeLimiter đặt thời gian chờ 2 giây cho tác vụ bất đồng bộ được hỗ trợ.

Các giá trị ví dụ không tự động bảo đảm timeout tổng của request là 2 giây. Thời gian tổng còn phụ thuộc timeout của client, retry, xử lý nội bộ và cách các cơ chế được bọc lồng nhau.

## 9. Cách chọn giá trị từ số liệu thực tế

Khi cấu hình cho một phụ thuộc mới, có thể bắt đầu theo trình tự sau:

1. **Xác định ngân sách độ trễ:** từ mục tiêu phản hồi của API, trừ thời gian xử lý nội bộ và các phụ thuộc khác để xác định phần thời gian dành cho lời gọi này.
2. **Đo độ trễ bình thường:** quan sát p50, p95, p99 và các đợt tăng độ trễ để chọn `slowCallDurationThreshold` cao hơn vùng hoạt động bình thường nhưng thấp hơn giới hạn gây ảnh hưởng nghiệp vụ.
3. **Đo tỷ lệ lỗi nền:** chọn `failureRateThreshold` sao cho lỗi ngẫu nhiên thông thường không làm mở mạch nhưng sự cố thực sự được phát hiện kịp thời.
4. **Chọn cửa sổ và số mẫu tối thiểu:** dùng lưu lượng trên từng instance để ước lượng thời gian cần tích lũy đủ mẫu. Với `TIME_BASED`, kiểm tra số lời gọi thực sự xuất hiện trong khoảng thời gian đó.
5. **Chọn thời gian mở mạch:** cân nhắc thời gian phụ thuộc cần để hồi phục và ảnh hưởng của việc từ chối thêm yêu cầu.
6. **Đặt timeout ở client:** đảm bảo kết nối và phản hồi có giới hạn; nếu dùng TimeLimiter, xác minh tác vụ có thể hủy và tài nguyên được giải phóng.
7. **Theo dõi và điều chỉnh:** so sánh số lần mở mạch, tỷ lệ lỗi, tỷ lệ lời gọi chậm và số lần fallback với hành vi người dùng thực tế.

Không nên thay đổi nhiều ngưỡng cùng lúc khi điều tra sự cố. Hãy thay một nhóm giá trị có liên quan, ghi lại giả thuyết và quan sát số liệu trước/sau để biết tác động của điều chỉnh.

## 10. Lỗi thường gặp khi đặt ngưỡng và Duration

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Mạch mở gần như ngay lập tức | `failureRateThreshold` quá thấp hoặc `minimumNumberOfCalls` quá nhỏ. | Đối chiếu tỷ lệ lỗi và số mẫu trong cửa sổ. |
| Mạch không mở dù dịch vụ rất chậm | `slowCallDurationThreshold` quá cao hoặc chưa đủ mẫu. | Đo thời gian lời gọi và kiểm tra cấu hình cửa sổ. |
| Timeout xảy ra gần như tức thì | Ghi số không có hậu tố đơn vị hoặc chuyển nhầm mili giây thành giây. | Kiểm tra kiểu bind và giá trị `Duration` thực tế. |
| Mạch giữ `OPEN` quá lâu | `waitDurationInOpenState` lớn hơn nhu cầu phục hồi. | So sánh thời gian chờ với thời gian hồi phục thực tế của phụ thuộc. |
| Mạch liên tục dao động OPEN/HALF_OPEN | Thời gian thăm dò quá ngắn, dịch vụ chưa ổn định hoặc ngưỡng quá nhạy. | Quan sát kết quả thăm dò và thời gian hồi phục. |
| TimeLimiter timeout nhưng request vẫn chạy | Tác vụ hoặc HTTP client không hỗ trợ hủy hoàn toàn. | Kiểm tra cancellation, socket và tài nguyên phía client. |
| Các môi trường có hành vi khác nhau | Cấu hình dùng số trần hoặc đơn vị không nhất quán. | Ghi rõ hậu tố đơn vị và kiểm tra cấu hình đã bind. |

## 11. Kiểm tra cấu hình trước khi triển khai

Trước khi đưa circuit breaker vào môi trường thật, hãy xác nhận:

- [ ] Các ngưỡng tỷ lệ được hiểu là phần trăm và nằm trong phạm vi hợp lệ.
- [ ] `minimumNumberOfCalls` và `slidingWindowSize` phù hợp với lưu lượng thực tế.
- [ ] `slowCallDurationThreshold` dựa trên ngân sách độ trễ của phụ thuộc.
- [ ] `waitDurationInOpenState` phù hợp với thời gian phục hồi và chính sách thăm dò.
- [ ] Mọi thuộc tính thời lượng trong YAML đều có hậu tố đơn vị rõ ràng.
- [ ] Mọi giá trị thời lượng trong Java đều dùng `Duration.ofMillis`, `ofSeconds`, `ofMinutes` hoặc `Duration.parse`.
- [ ] Timeout ở HTTP client và TimeLimiter được phân biệt, không thay thế lẫn nhau.
- [ ] Có kiểm thử cho lời gọi thành công, lỗi, chậm, timeout và phục hồi.
- [ ] Metrics cho phép quan sát tỷ lệ lỗi, tỷ lệ lời gọi chậm và trạng thái circuit breaker.

Đặt ngưỡng và thời gian đúng đơn vị giúp circuit breaker phản ứng có chủ đích trước lỗi và độ trễ của dịch vụ phụ thuộc. Hãy dùng cấu hình dễ đọc, dựa trên số liệu vận hành và kiểm tra giá trị đã bind trước khi triển khai để tránh một lỗi đơn vị nhỏ làm thay đổi hoàn toàn hành vi bảo vệ dịch vụ.
