# Kiểm thử lời gọi chậm độc lập với lời gọi lỗi

Circuit breaker của Resilience4j có thể mở mạch vì hai tín hiệu riêng: tỷ lệ lời gọi thất bại và tỷ lệ lời gọi chậm. Khi kiểm thử, cần tạo được hai tình huống độc lập để chứng minh rằng một lời gọi trả kết quả thành công nhưng mất quá nhiều thời gian vẫn có thể làm mạch mở, trong khi một lời gọi thất bại nhanh làm tăng failure rate mà không làm tăng slow call rate.

Phân biệt hai tình huống giúp tránh cấu hình circuit breaker chỉ phát hiện lỗi HTTP hoặc exception mà bỏ sót suy giảm độ trễ. Một dịch vụ có thể vẫn trả HTTP 200 nhưng mất vài giây để phản hồi; những lời gọi này vẫn chiếm luồng, kết nối và ngân sách thời gian của dịch vụ gọi.

## Hai tín hiệu được đánh giá độc lập

Resilience4j ghi nhận kết quả và thời gian thực thi của mỗi lời gọi trong sliding window. Từ các mẫu đó, nó tính hai tỷ lệ:

| Tín hiệu | Cách tính | Ý nghĩa |
|---|---|---|
| Failure rate | Số lời gọi được ghi nhận thất bại chia cho tổng số lời gọi được đánh giá. | Phụ thuộc không hoàn thành lời gọi thành công. |
| Slow call rate | Số lời gọi có thời gian thực thi vượt ngưỡng chậm chia cho tổng số lời gọi được đánh giá. | Phụ thuộc phản hồi quá chậm, dù có thể vẫn trả kết quả thành công. |

Ba thuộc tính cần phân biệt:

- **failureRateThreshold**: tỷ lệ lỗi tối đa trước khi circuit breaker mở.
- **slowCallDurationThreshold**: thời lượng từ đó một lời gọi được xem là chậm.
- **slowCallRateThreshold**: tỷ lệ lời gọi chậm tối đa trước khi circuit breaker mở.

Slow call rate không phải timeout. Nó là một tỷ lệ phần trăm. slowCallDurationThreshold mới là mốc thời gian dùng để phân loại từng lời gọi.

Sau khi có ít nhất minimumNumberOfCalls, circuit breaker có thể chuyển từ CLOSED sang OPEN nếu failure rate đạt ngưỡng **hoặc** slow call rate đạt ngưỡng. Không cần cả hai cùng vượt ngưỡng. Một lời gọi vừa chậm vừa thất bại có thể đóng góp vào cả hai tỷ lệ; vì vậy không cộng hai tỷ lệ để suy ra số lời gọi có vấn đề.

## Thiết kế ba tình huống kiểm thử riêng

Để kiểm tra đúng từng tín hiệu, hãy tạo các lời gọi có kết quả và thời lượng được kiểm soát:

| Tình huống | Kết quả HTTP/ứng dụng | Thời lượng | Failure rate | Slow call rate |
|---|---|---|---|---|
| Chậm nhưng thành công | Thành công, ví dụ HTTP 200 | Lớn hơn slowCallDurationThreshold | Không tăng | Tăng |
| Thất bại nhanh | Ném exception hoặc trả status được chuyển thành lỗi | Nhỏ hơn slowCallDurationThreshold | Tăng | Không tăng |
| Chậm và thất bại | Ném exception sau khi chờ lâu | Lớn hơn slowCallDurationThreshold | Tăng | Tăng |

Ví dụ, dùng cửa sổ 10 lời gọi, minimumNumberOfCalls là 10, failureRateThreshold là 50%, slowCallDurationThreshold là 100 ms và slowCallRateThreshold là 50%.

- Sáu lời gọi thành công sau 180 ms và bốn lời gọi thành công nhanh: failure rate bằng 0%, slow call rate bằng 60%. Mạch mở do lời gọi chậm.
- Sáu lời gọi thất bại sau 5 ms và bốn lời gọi thành công nhanh: failure rate bằng 60%, slow call rate bằng 0%. Mạch mở do lỗi.
- Sáu lời gọi vừa chậm vừa thất bại: cả hai tỷ lệ đều tăng. Tình huống này kiểm tra sự giao nhau của hai tín hiệu, không thay thế hai kiểm thử độc lập phía trên.

Điều quan trọng là không để timeout ngắn hơn thời gian phản hồi chậm trong bài kiểm thử đầu tiên. Nếu timeout kích hoạt trước khi lời gọi trả kết quả, tình huống “chậm nhưng thành công” sẽ trở thành một lỗi timeout và không còn cô lập được slow call rate.

## Cấu hình Resilience4j cho bài kiểm thử

Có thể cấu hình instance trong application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 100ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Với cấu hình này:

- Cửa sổ đếm giữ tối đa 10 kết quả gần nhất.
- Circuit breaker chưa đánh giá tỷ lệ cho đến khi có ít nhất 10 lời gọi.
- Lời gọi mất hơn ngưỡng 100 ms được phân loại là chậm.
- Khi ít nhất một nửa số mẫu được đánh giá là chậm, mạch có thể mở dù tất cả lời gọi đều thành công.
- Khi ít nhất một nửa số mẫu thất bại, mạch cũng có thể mở dù các lời gọi thất bại đều kết thúc nhanh.

Trong kiểm thử, COUNT_BASED thường dễ kiểm soát hơn TIME_BASED vì số mẫu được xác định rõ. Nếu dùng TIME_BASED, slidingWindowSize biểu thị độ dài cửa sổ thời gian; hãy bảo đảm các lời gọi thử nghiệm nằm trong cùng cửa sổ và đủ minimumNumberOfCalls.

Các giá trị trên chỉ dành cho môi trường kiểm thử. Ngưỡng vận hành thực tế cần dựa trên ngân sách độ trễ, phân phối latency và lưu lượng của dịch vụ.

## Kiểm thử unit bằng Resilience4j CircuitBreaker

Có thể kiểm tra trực tiếp hành vi của Resilience4j mà không cần khởi động Spring context. Mỗi test tạo một circuit breaker mới để trạng thái và số liệu của test trước không ảnh hưởng test sau.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

class CircuitBreakerSlowCallTest {

    private CircuitBreaker newBreaker(String name) {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(
                        CircuitBreakerConfig.SlidingWindowType.COUNT_BASED
                )
                .slidingWindowSize(10)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .slowCallDurationThreshold(Duration.ofMillis(100))
                .slowCallRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build();

        return CircuitBreaker.of(name, config);
    }

    private String responseAfter(long delayMillis, boolean fail) {
        if (delayMillis > 0) {
            try {
                Thread.sleep(delayMillis);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Test interrupted", ex);
            }
        }

        if (fail) {
            throw new IllegalStateException("Downstream failed");
        }

        return "OK";
    }

    @Test
    void slowSuccessfulCallsOpenBreakerWithoutFailures() {
        CircuitBreaker breaker = newBreaker("slow-success");

        for (int i = 0; i < 6; i++) {
            assertEquals(
                    "OK",
                    breaker.executeSupplier(() -> responseAfter(180, false))
            );
        }

        for (int i = 0; i < 4; i++) {
            assertEquals(
                    "OK",
                    breaker.executeSupplier(() -> responseAfter(0, false))
            );
        }

        assertEquals(
                0.0f,
                breaker.getMetrics().getFailureRate(),
                0.01f
        );
        assertTrue(breaker.getMetrics().getSlowCallRate() >= 50.0f);
        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }

    @Test
    void fastFailuresOpenBreakerWithoutSlowCalls() {
        CircuitBreaker breaker = newBreaker("fast-failure");

        for (int i = 0; i < 6; i++) {
            assertThrows(
                    IllegalStateException.class,
                    () -> breaker.executeSupplier(
                            () -> responseAfter(0, true)
                    )
            );
        }

        for (int i = 0; i < 4; i++) {
            assertEquals(
                    "OK",
                    breaker.executeSupplier(() -> responseAfter(0, false))
            );
        }

        assertTrue(breaker.getMetrics().getFailureRate() >= 50.0f);
        assertEquals(
                0.0f,
                breaker.getMetrics().getSlowCallRate(),
                0.01f
        );
        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }
}
~~~

Hai test xác nhận hai đường mở mạch khác nhau:

- Test thứ nhất chỉ có lời gọi thành công. Failure rate phải bằng 0%, nhưng slow call rate đạt 60% và trạng thái chuyển OPEN.
- Test thứ hai chỉ có lỗi nhanh. Failure rate đạt 60%, còn slow call rate bằng 0%.

Ví dụ dùng thời gian thực để làm lời gọi chậm. Trong CI hoặc máy chạy tải cao, scheduler có thể làm một lời gọi nhanh bị trễ ngoài dự kiến. Hãy để khoảng cách giữa thời lượng chậm và ngưỡng đủ lớn, tránh kiểm tra đúng sát ranh giới, và không chạy các test thời gian nhạy cảm song song nếu môi trường quá tải. Với integration test, có thể dùng HTTP stub có độ trễ cố định để quan sát cả client và circuit breaker.

## Kiểm thử tích hợp qua HTTP client

Unit test trên kiểm tra trực tiếp bộ đếm Resilience4j. Một integration test nên xác nhận cả đường HTTP thực tế: response thành công nhưng chậm được đo là slow call, còn lỗi nhanh được đo là failure.

Có thể dùng WireMock để tạo hai phản hồi:

~~~java
stubFor(get(urlEqualTo("/inventory/SKU-1"))
        .willReturn(aResponse()
                .withStatus(200)
                .withFixedDelay(250)
                .withHeader("Content-Type", "application/json")
                .withBody("{\"sku\":\"SKU-1\",\"available\":12}")));

stubFor(get(urlEqualTo("/inventory/SKU-2"))
        .willReturn(aResponse()
                .withStatus(500)
                .withFixedDelay(5)));
~~~

Với phản hồi đầu, HTTP client nhận status 200 sau độ trễ 250 ms. Nếu slowCallDurationThreshold thấp hơn 250 ms và timeout của client/TimeLimiter dài hơn 250 ms, circuit breaker ghi nhận một lời gọi chậm nhưng thành công.

Với phản hồi thứ hai, dịch vụ trả status 500 nhanh. Cần cấu hình HTTP client hoặc adapter chuyển status này thành exception nếu muốn circuit breaker ghi nhận là thất bại. Một số client tự ném exception cho response 5xx; một số luồng xử lý có thể chuyển response thành object bình thường. Hãy xác nhận hành vi thật của client thay vì giả định mọi status 500 đều tự động trở thành failure.

Không dùng một circuit breaker đã OPEN để chạy cả hai kịch bản liên tiếp. Khi mạch mở, lời gọi bị từ chối trước khi tới stub và kết quả không còn phản ánh độ trễ của dịch vụ. Tạo instance riêng cho mỗi kịch bản hoặc reset trạng thái có kiểm soát trước khi bắt đầu.

## Đặt timeout đủ dài để cô lập slow call

Circuit breaker không dừng một lời gọi chỉ vì thời gian của nó vượt slowCallDurationThreshold. Nó ghi nhận thời lượng khi lời gọi hoàn tất, sau đó dùng kết quả trong sliding window để tính slow call rate. Nếu tỷ lệ vượt ngưỡng, những lời gọi tiếp theo mới có thể bị từ chối khi mạch OPEN.

Timeout có nhiệm vụ khác: kết thúc việc chờ một lời gọi khi hết deadline. Nếu timeout ngắn hơn slowCallDurationThreshold, các lời gọi có thể thất bại do timeout trước khi được ghi nhận như những lần thành công chậm.

Khi kiểm thử slow success:

1. Chọn slowCallDurationThreshold, ví dụ 100 ms.
2. Cho stub phản hồi thành công sau khoảng 250 ms.
3. Đặt timeout của HTTP client và TimeLimiter dài hơn độ trễ đó, ví dụ 1 giây.
4. Xác nhận response vẫn thành công.
5. Xác nhận slow call count tăng, failure count không tăng.

Sau đó, kiểm thử timeout riêng bằng một response chậm hơn timeout. Trường hợp đó xác minh đường lỗi timeout, không phải kiểm thử độc lập cho slow call thành công.

## Quan sát metrics và trạng thái

Resilience4j cung cấp metrics của circuit breaker để đọc riêng failure rate và slow call rate. Trong unit test, có thể kiểm tra trực tiếp:

~~~java
CircuitBreaker.Metrics metrics = breaker.getMetrics();

float failureRate = metrics.getFailureRate();
float slowCallRate = metrics.getSlowCallRate();

int failedCalls = metrics.getNumberOfFailedCalls();
int slowCalls = metrics.getNumberOfSlowCalls();
~~~

Khi tích hợp Spring Boot Actuator và Micrometer, có thể xuất metrics của Resilience4j để theo dõi theo tên instance. Tên metric cụ thể và tag có thể thay đổi theo phiên bản thư viện và cấu hình registry; hãy kiểm tra các metric thực tế được expose trong môi trường ứng dụng.

Nên theo dõi tối thiểu:

- Failure rate và số lời gọi thất bại.
- Slow call rate và số lời gọi chậm.
- Độ trễ p50, p95 và p99 của lời gọi phụ thuộc.
- Trạng thái CLOSED, OPEN và HALF_OPEN.
- Số lần bị từ chối khi mạch OPEN.
- Số lần fallback được gọi.

Không gộp slow call rate vào failure rate khi tạo dashboard. Nếu chỉ xem tỷ lệ lỗi, nhóm vận hành có thể bỏ lỡ tình huống dịch vụ vẫn trả 2xx nhưng latency tăng cao. Ngược lại, nếu chỉ xem latency, có thể bỏ lỡ lỗi nhanh do kết nối hoặc server.

## Các lỗi thường gặp khi viết test

| Lỗi trong test | Vì sao kết quả sai | Cách khắc phục |
|---|---|---|
| Dùng response 500 để kiểm tra slow call rate | Test đang đo lỗi; nếu nhanh thì không chứng minh slow call độc lập. | Dùng response thành công có độ trễ vượt ngưỡng. |
| Dùng timeout ngắn hơn độ trễ stub | Lời gọi trở thành lỗi timeout thay vì slow success. | Đặt timeout dài hơn độ trễ trong test slow-success. |
| Không đủ minimumNumberOfCalls | Circuit breaker chưa đánh giá tỷ lệ. | Gửi đủ mẫu trong cửa sổ. |
| Dùng chung breaker đã OPEN cho nhiều test | Lời gọi sau bị từ chối trước khi chạy. | Tạo breaker riêng cho mỗi test hoặc reset có kiểm soát. |
| Đặt delay sát slowCallDurationThreshold | Test không ổn định do scheduler và tải máy. | Tạo khoảng cách thời gian đủ lớn. |
| Dùng TIME_BASED nhưng test chạy quá lâu | Các mẫu cũ rời khỏi cửa sổ trước khi đủ số lượng. | Dùng COUNT_BASED hoặc bảo đảm mọi mẫu nằm trong cửa sổ. |
| Xem mọi HTTP 5xx tự động là exception | Hành vi phụ thuộc HTTP client và cách xử lý response. | Kiểm tra adapter/client và chuyển status thành lỗi khi cần. |

Một bài kiểm thử tốt phải chứng minh điều kiện kích hoạt, không chỉ kiểm tra trạng thái cuối. Hãy assert cả response, failure rate, slow call rate, số mẫu và trạng thái circuit breaker.

## Kiểm tra HALF_OPEN sau khi mở vì lời gọi chậm

Sau khi mạch mở do slow call rate, có thể kiểm tra quá trình phục hồi:

1. Cấu hình waitDurationInOpenState ngắn trong test, chẳng hạn 200 ms.
2. Sau khi mạch OPEN, xác nhận lời gọi tiếp theo bị từ chối nhanh.
3. Chờ hết khoảng OPEN theo cơ chế thời gian của test.
4. Cho phép một số lời gọi thăm dò ở HALF_OPEN.
5. Chuyển stub sang phản hồi nhanh và thành công.
6. Xác nhận circuit breaker trở lại CLOSED sau khi các mẫu thăm dò đạt yêu cầu.

Nếu dịch vụ vẫn phản hồi chậm trong HALF_OPEN, mạch có thể mở lại. Số lời gọi thăm dò được giới hạn bởi permittedNumberOfCallsInHalfOpenState. Không tạo một đợt tải lớn khi kiểm tra phục hồi.

Test HALF_OPEN nên tách khỏi test xác nhận slow success và fast failure. Mỗi test chỉ kiểm tra một hành vi chính để khi thất bại có thể xác định nguyên nhân rõ ràng.

## Checklist kiểm thử

1. Tạo circuit breaker mới cho mỗi kịch bản và dùng cửa sổ có số mẫu xác định.
2. Đặt minimumNumberOfCalls đủ thấp để test có thể hoàn thành nhưng vẫn kiểm tra đúng điều kiện.
3. Kiểm thử slow success bằng response thành công có độ trễ lớn hơn slowCallDurationThreshold.
4. Xác nhận failure rate bằng 0 và slow call rate vượt ngưỡng trong kịch bản slow success.
5. Kiểm thử fast failure bằng exception hoặc status được chuyển thành lỗi với thời gian thấp hơn ngưỡng chậm.
6. Xác nhận failure rate vượt ngưỡng và slow call rate bằng 0 trong kịch bản fast failure.
7. Kiểm thử riêng trường hợp vừa chậm vừa thất bại để xác nhận hai tỷ lệ có thể cùng tăng.
8. Đặt timeout dài hơn độ trễ trong test slow-success; kiểm tra timeout riêng.
9. Xác nhận circuit breaker OPEN từ chối lời gọi tiếp theo và HALF_OPEN phục hồi theo cấu hình.
10. Quan sát metrics riêng cho lỗi và lời gọi chậm.

Kiểm thử lời gọi chậm độc lập với lời gọi lỗi giúp xác nhận circuit breaker bảo vệ cả tính sẵn sàng lẫn độ trễ của dịch vụ phụ thuộc. Một response thành công nhưng chậm phải có thể làm tăng slow call rate mà không làm tăng failure rate; một lỗi nhanh phải làm tăng failure rate mà không bị nhầm thành lời gọi chậm. Khi test cô lập được hai tín hiệu này, nhóm phát triển có thể tin cậy hơn vào cấu hình Resilience4j và phát hiện sớm tình trạng suy giảm hiệu năng trước khi nó lan sang các dịch vụ gọi.

