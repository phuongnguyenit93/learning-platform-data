# Kiểm thử minimumNumberOfCalls và trường hợp chưa đủ mẫu

Trong Resilience4j, circuit breaker không quyết định mở mạch chỉ vì vừa xuất hiện một vài lỗi. Trước khi tính failure rate hoặc slow call rate, breaker cần thu thập đủ số kết quả được quy định bởi `minimumNumberOfCalls`. Nếu cửa sổ thống kê chưa có đủ mẫu, breaker vẫn ở `CLOSED` dù tất cả những lời gọi đã quan sát đều thất bại.

Đây là hành vi có chủ đích để tránh kết luận từ một tập mẫu quá nhỏ. Khi kiểm thử, cần xác nhận cả hai phía: breaker chưa mở khi số mẫu thấp hơn ngưỡng tối thiểu, và bắt đầu đánh giá tỷ lệ khi đã đủ mẫu. Cũng cần phân biệt trường hợp thiếu mẫu với trường hợp phụ thuộc khỏe mạnh: cả hai có thể khiến breaker vẫn `CLOSED`, nhưng nguyên nhân và dữ liệu thống kê khác nhau.

## 1. `minimumNumberOfCalls` kiểm soát điều gì?

`minimumNumberOfCalls` là số lời gọi tối thiểu cần được ghi nhận trong sliding window trước khi Resilience4j tính failure rate và slow call rate để quyết định mở breaker. Giá trị này không phải số lần lỗi tối thiểu. Các mẫu có thể gồm cả lời gọi thành công và thất bại; exception bị cấu hình ignore không đóng góp vào số mẫu success/failure.

Ví dụ, cấu hình có `minimumNumberOfCalls: 5` và `failureRateThreshold: 50`. Nếu breaker mới ghi nhận ba lời gọi và cả ba đều thất bại, nó vẫn chưa đủ mẫu để đánh giá failure rate. Khi lời gọi thứ tư cũng thất bại, kết quả vẫn chưa đủ năm mẫu. Sau khi ghi nhận lời gọi thứ năm, breaker mới tính tỷ lệ lỗi trên các mẫu trong cửa sổ.

| Số mẫu được ghi nhận | Kết quả | Failure rate có được đánh giá? | Trạng thái có thể xảy ra |
|---:|---|---|---|
| 1 | 1 lỗi | Chưa | `CLOSED` |
| 2 | 2 lỗi | Chưa | `CLOSED` |
| 3 | 3 lỗi | Chưa | `CLOSED` |
| 4 | 4 lỗi | Chưa | `CLOSED` |
| 5 | 5 lỗi | Có, 100% | Chuyển `OPEN` nếu ngưỡng là 50% |

Trong ví dụ này, breaker không bỏ qua các lỗi đầu tiên. Chúng vẫn được ghi vào thống kê và có thể được quan sát qua số mẫu cùng số lần lỗi. Chỉ có quyết định dựa trên tỷ lệ bị trì hoãn cho đến khi đủ mẫu.

## 2. Phân biệt slidingWindowSize và minimumNumberOfCalls

Hai thuộc tính này có liên quan nhưng không thay thế nhau:

- `slidingWindowSize` xác định kích thước cửa sổ thống kê.
- `minimumNumberOfCalls` xác định số mẫu tối thiểu phải có trong cửa sổ trước khi tính tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm.

Với cửa sổ `COUNT_BASED`, `slidingWindowSize` là số lời gọi gần nhất được giữ trong cửa sổ. Với cửa sổ `TIME_BASED`, nó biểu thị số bucket thời gian tạo thành khoảng cửa sổ. `minimumNumberOfCalls` vẫn là số kết quả tối thiểu cần có trong cửa sổ đó.

Ví dụ cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 60
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
```

Trong cấu hình này, breaker giữ tối đa 10 kết quả gần nhất nhưng chỉ bắt đầu đánh giá tỷ lệ sau khi có ít nhất 4 mẫu hợp lệ trong cửa sổ. Khi đủ mẫu, nếu failure rate đạt hoặc vượt 60%, breaker có thể chuyển sang `OPEN`. Slow call rate cũng cần đủ mẫu trước khi được dùng để đánh giá.

Không nên đặt `minimumNumberOfCalls` quá cao so với lưu lượng thực tế. Nếu một operation chỉ nhận vài lời gọi trong khoảng thời gian dài, breaker có thể hiếm khi đạt ngưỡng mẫu. Ngược lại, đặt giá trị quá thấp khiến một vài lỗi ngẫu nhiên có thể mở mạch sớm.

## 3. Failure rate chưa xác định khi thiếu mẫu

Resilience4j biểu diễn failure rate chưa thể tính bằng giá trị `-1.0` trong metric của breaker khi số mẫu chưa đạt `minimumNumberOfCalls`. Giá trị này có nghĩa là **chưa đủ dữ liệu để đánh giá**, không có nghĩa failure rate bằng âm một phần trăm hoặc hệ thống không có lỗi.

Các metric hữu ích khi kiểm tra tình huống thiếu mẫu gồm:

- `getNumberOfBufferedCalls()`: số mẫu hiện có trong sliding window.
- `getNumberOfFailedCalls()`: số lời gọi lỗi đang được giữ trong cửa sổ.
- `getNumberOfSuccessfulCalls()`: số lời gọi thành công đang được giữ trong cửa sổ.
- `getFailureRate()`: failure rate, hoặc `-1.0` khi chưa đủ mẫu.
- `getState()`: trạng thái hiện tại của breaker.

Ví dụ, nếu có ba lỗi và `minimumNumberOfCalls` bằng năm, metric có thể cho thấy ba mẫu được buffer, ba lỗi, không có success, failure rate bằng `-1.0` và state vẫn là `CLOSED`. Dữ liệu này khác với trường hợp có năm lời gọi thành công, failure rate bằng 0% và state `CLOSED`.

## 4. Kiểm thử trực tiếp bằng JUnit 5

Có thể kiểm thử hành vi của Resilience4j mà không cần khởi động Spring context bằng cách tạo một breaker với cấu hình nhỏ. Cách này giúp test tập trung vào quy tắc của `minimumNumberOfCalls` và tránh phụ thuộc thời gian mạng.

Ví dụ dưới đây dùng cửa sổ theo số lượng gồm 10 mẫu, yêu cầu tối thiểu 4 mẫu và ngưỡng lỗi 60%:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

class MinimumNumberOfCallsTest {

    private CircuitBreaker newBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(10)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(60)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreaker.of("inventory-test", config);
    }

    private void fail(CircuitBreaker breaker) {
        assertThrows(IllegalStateException.class, () ->
                breaker.executeSupplier(() -> {
                    throw new IllegalStateException("inventory unavailable");
                })
        );
    }

    @Test
    void staysClosedWhenThereAreFewerSamplesThanMinimum() {
        CircuitBreaker breaker = newBreaker();

        fail(breaker);
        fail(breaker);
        fail(breaker);

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
        assertEquals(3, breaker.getMetrics().getNumberOfBufferedCalls());
        assertEquals(3, breaker.getMetrics().getNumberOfFailedCalls());
        assertEquals(-1.0f, breaker.getMetrics().getFailureRate(), 0.001f);
    }

    @Test
    void evaluatesFailureRateWhenMinimumSamplesAreReached() {
        CircuitBreaker breaker = newBreaker();

        fail(breaker);
        fail(breaker);
        fail(breaker);

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());

        assertEquals("ok", breaker.executeSupplier(() -> "ok"));

        assertEquals(4, breaker.getMetrics().getNumberOfBufferedCalls());
        assertEquals(3, breaker.getMetrics().getNumberOfFailedCalls());
        assertEquals(75.0f, breaker.getMetrics().getFailureRate(), 0.001f);
        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }

    @Test
    void remainsClosedWhenRateIsBelowThresholdAfterMinimumSamples() {
        CircuitBreaker breaker = newBreaker();

        fail(breaker);
        fail(breaker);
        breaker.executeSupplier(() -> "first success");
        breaker.executeSupplier(() -> "second success");

        assertEquals(4, breaker.getMetrics().getNumberOfBufferedCalls());
        assertEquals(2, breaker.getMetrics().getNumberOfFailedCalls());
        assertEquals(50.0f, breaker.getMetrics().getFailureRate(), 0.001f);
        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
    }
}
```

Ba test thể hiện ba tình huống:

1. Có ba mẫu lỗi nhưng chưa đủ bốn mẫu, breaker giữ `CLOSED` và failure rate chưa xác định.
2. Khi mẫu thứ tư được ghi nhận, failure rate là 75%, vượt ngưỡng 60%, nên breaker chuyển `OPEN`.
3. Khi đủ bốn mẫu nhưng failure rate là 50%, thấp hơn ngưỡng 60%, breaker vẫn `CLOSED`.

Các test dùng supplier đồng bộ và exception xác định nên không phụ thuộc DNS, HTTP server hoặc thời gian chờ thực. Khi đưa vào dự án, cần có dependency Resilience4j CircuitBreaker và JUnit Jupiter phù hợp với dependency management đang dùng.

## 5. Vì sao ba lỗi liên tiếp chưa chắc làm breaker mở?

Giả sử cấu hình production có:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      pricing:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
```

Nếu instance `pricing` vừa được tạo và ba lời gọi đầu tiên đều timeout, breaker vẫn chưa đủ 10 mẫu để đánh giá failure rate. Nó có thể tiếp tục cho phép các lời gọi mới đi tới pricing service cho đến khi đạt đủ mẫu. Đây là trade-off giữa việc tránh quyết định từ quá ít dữ liệu và việc phát hiện lỗi nhanh.

Khi lưu lượng cao, 10 mẫu có thể được thu thập trong thời gian ngắn. Khi lưu lượng thấp, việc đạt 10 mẫu có thể mất nhiều giây hoặc nhiều phút. Vì vậy, cùng một `minimumNumberOfCalls` có thể tạo thời gian phát hiện khác nhau giữa các dependency.

Không nên diễn giải trạng thái `CLOSED` trong giai đoạn thiếu mẫu thành “dependency khỏe”. Nó chỉ nói breaker chưa có đủ bằng chứng để mở mạch theo thống kê hiện tại. Cần đọc cùng số mẫu, lỗi, latency và metric HTTP client.

## 6. Ảnh hưởng của COUNT_BASED và TIME_BASED

### COUNT_BASED

Với `COUNT_BASED`, cửa sổ chứa tối đa `slidingWindowSize` lời gọi gần nhất. Khi có lời gọi mới, mẫu cũ nhất bị loại khỏi cửa sổ. `minimumNumberOfCalls` xác định số kết quả tối thiểu phải được ghi nhận trước khi đánh giá tỷ lệ.

Ví dụ, cửa sổ có kích thước 10 và yêu cầu tối thiểu 4 mẫu. Sau ba lời gọi, chưa đủ mẫu. Sau lời gọi thứ tư, tỷ lệ bắt đầu được đánh giá. Khi cửa sổ đã có 10 mẫu, mỗi lời gọi mới thay thế một mẫu cũ và tỷ lệ được tính trên tập mẫu gần nhất.

### TIME_BASED

Với `TIME_BASED`, cửa sổ bao phủ một khoảng thời gian được chia thành các bucket. Các kết quả trong khoảng thời gian đó được tổng hợp; mẫu cũ dần rời khỏi cửa sổ khi thời gian trôi qua. `minimumNumberOfCalls` vẫn yêu cầu có đủ số lời gọi trong cửa sổ trước khi đánh giá tỷ lệ.

Ví dụ, cửa sổ 10 giây và `minimumNumberOfCalls: 5`. Nếu trong 10 giây chỉ có ba request và cả ba đều lỗi, breaker chưa đủ mẫu để tính failure rate. Khi traffic thấp, TIME_BASED không tự khắc phục thiếu mẫu; nó chỉ giới hạn khoảng thời gian mà các mẫu được xem xét.

| Kiểu cửa sổ | Kích thước biểu thị | Trường hợp thiếu mẫu thường gặp |
|---|---|---|
| `COUNT_BASED` | Số lời gọi gần nhất | Instance mới hoặc operation có ít traffic chưa tích lũy đủ số lời gọi |
| `TIME_BASED` | Số bucket thời gian | Traffic trong khoảng thời gian quan sát quá thấp để đạt `minimumNumberOfCalls` |

## 7. Kiểm thử trường hợp chưa đủ mẫu với TIME_BASED

Với `TIME_BASED`, nên kiểm tra số mẫu trong một khoảng thời gian xác định. Không cần dựa vào việc chờ một dịch vụ thật bị lỗi; có thể gọi trực tiếp breaker với supplier ném exception để tạo mẫu có kiểm soát.

Ví dụ cấu hình:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.TIME_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50)
        .build();

CircuitBreaker breaker = CircuitBreaker.of("low-traffic", config);
```

Nếu chỉ thực hiện ba lời gọi lỗi trong khoảng cửa sổ, cần xác nhận breaker vẫn `CLOSED` và failure rate chưa xác định. Khi thêm đủ mẫu, tỷ lệ mới được đánh giá. Để test ổn định, không nên dùng `Thread.sleep()` dài hoặc giả định chính xác thời điểm bucket xoay vòng. Nếu cần kiểm thử ranh giới thời gian, dùng khả năng clock tùy chỉnh mà phiên bản Resilience4j đang sử dụng hỗ trợ, hoặc kiểm thử ở mức tích hợp với thời gian được kiểm soát.

## 8. Exception bị ignore có ảnh hưởng đến minimumNumberOfCalls không?

Resilience4j phân biệt exception được ghi nhận là failure, exception được xem như success và exception được ignore. Exception bị ignore không được tính vào failure rate hoặc success rate, nên không giúp đạt số mẫu tối thiểu.

Ví dụ, cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
```

Nếu ba lời gọi phát sinh `InvalidSkuException` và một lời gọi timeout được ghi nhận là failure, không nên xem đó là bốn mẫu success/failure. Các exception bị ignore không đóng góp vào số mẫu dùng để tính tỷ lệ. Vì vậy, số lần gọi tổng ở tầng HTTP hoặc số lần supplier chạy có thể lớn hơn số mẫu được dùng cho failure rate.

Khi test, hãy kiểm tra riêng số lời gọi đã thực hiện, số mẫu buffered, số success, số failure và số ignored. Đừng chỉ đếm tổng request rồi kết luận breaker đã đủ `minimumNumberOfCalls`.

## 9. Test fallback không làm sai thống kê breaker

Fallback thường được thực thi sau khi lời gọi được bảo vệ thất bại. Nếu fallback được áp dụng bên ngoài breaker, breaker ghi nhận exception của supplier trước khi caller nhận kết quả fallback. Kết quả fallback không biến lần gọi lỗi thành success của breaker.

Ví dụ:

```java
String result;
try {
    result = breaker.executeSupplier(() -> {
        throw new IllegalStateException("pricing unavailable");
    });
} catch (IllegalStateException error) {
    result = "cached-price";
}
```

Trong ví dụ, breaker ghi nhận supplier thất bại. Mã bên ngoài bắt exception và tạo fallback. Khi kiểm thử, xác nhận `getNumberOfFailedCalls()` tăng, không phải `getNumberOfSuccessfulCalls()` tăng vì fallback đã trả một giá trị cho caller.

Nếu tự bắt exception bên trong supplier và trả fallback như một kết quả bình thường trước khi breaker quan sát được lỗi, breaker có thể ghi nhận success. Cấu trúc xử lý exception vì vậy ảnh hưởng trực tiếp tới ý nghĩa của thống kê.

## 10. Các lỗi thường gặp khi viết test

| Lỗi kiểm thử | Vì sao sai | Cách sửa |
|---|---|---|
| Kỳ vọng breaker mở ngay sau lỗi đầu tiên | Chưa đạt `minimumNumberOfCalls` | Tạo đủ mẫu trước khi kiểm tra threshold |
| Chỉ assert state là `CLOSED` | Không phân biệt thiếu mẫu với tỷ lệ lỗi thấp | Assert buffered calls, success/failure count và failure rate |
| Dùng `slidingWindowSize` thay cho `minimumNumberOfCalls` | Hai thuộc tính có vai trò khác nhau | Cấu hình và kiểm tra riêng cả hai |
| Đếm mọi request gồm cả ignored | Exception ignored không tham gia failure/success rate | Kiểm tra metric ignored và số mẫu thực tế |
| Dùng HTTP server thật cho unit test đơn giản | Test chậm và phụ thuộc môi trường mạng | Dùng supplier xác định để kiểm thử state machine |
| Dùng `sleep` để chờ TIME_BASED window | Dễ tạo test không ổn định | Kiểm soát clock hoặc test với khoảng thời gian có chủ đích |
| Xem `CLOSED` là bằng chứng dependency khỏe | Có thể chưa đủ mẫu để đánh giá | Đọc failure rate, sample count và latency cùng state |
| Đưa fallback vào trong supplier rồi mong breaker ghi nhận lỗi | Breaker có thể chỉ nhìn thấy kết quả bình thường | Đặt fallback ngoài vùng được bảo vệ hoặc cấu hình theo semantics mong muốn |

## 11. Kiểm thử cấu hình trong Spring Boot

Unit test tạo `CircuitBreaker` trực tiếp xác nhận quy tắc của Resilience4j. Nhưng ứng dụng Spring Cloud còn cần kiểm tra cấu hình thực tế được bind đúng ID. Một integration test có thể nạp cấu hình test và lấy breaker từ registry hoặc gọi gateway được Spring quản lý.

Ví dụ cấu hình test:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-test:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 60
```

Trong integration test, cần xác nhận instance `inventory-test` có cấu hình hiệu lực đúng như dự kiến. Sau đó thực hiện ba lỗi, kiểm tra state vẫn `CLOSED` và failure rate chưa xác định; thêm mẫu thứ tư để xác nhận tỷ lệ bắt đầu được tính. Nếu gateway dùng `CircuitBreakerFactory`, gọi đúng ID từ gateway để bảo đảm tên trong mã trùng tên cấu hình.

Không nên chỉ kiểm tra file YAML bằng cách đọc chuỗi. Điều cần xác minh là Spring Boot đã nạp thuộc tính và Resilience4j đã tạo instance với cấu hình đó. Có thể dùng registry/metrics hoặc hành vi của breaker để xác nhận.

## 12. Chọn minimumNumberOfCalls theo lưu lượng

`minimumNumberOfCalls` cần được chọn dựa trên lưu lượng của từng breaker instance, không phải tổng lưu lượng toàn ứng dụng. Một breaker theo operation có thể nhận ít traffic hơn breaker theo dependency. Nếu tách quá nhỏ, mỗi instance có thể không bao giờ đủ mẫu trong khoảng thời gian mà hệ thống cần phát hiện sự cố.

Hãy xem xét:

- Lưu lượng trung bình và lưu lượng thấp điểm của từng dependency/operation.
- Kích thước và loại sliding window.
- Thời gian chấp nhận được để thu thập đủ mẫu.
- Tỷ lệ lỗi có thể chấp nhận trước khi mở mạch.
- Mức độ nguy hiểm khi tiếp tục gọi phụ thuộc đang lỗi.
- Các cơ chế bảo vệ khác như connect/read timeout, deadline tổng, bulkhead và rate limiter.

Nếu traffic thấp, không nên giảm `minimumNumberOfCalls` một cách máy móc. Có thể gom các thao tác có cùng failure domain để tăng mẫu, dùng timeout và bulkhead để giới hạn tác động trong lúc thiếu mẫu, hoặc chọn một chiến lược health signal phù hợp. Circuit breaker chỉ có thể đánh giá tỷ lệ từ những mẫu thực sự được ghi nhận.

## 13. Quy trình kiểm thử minimumNumberOfCalls

Khi viết test cho một breaker, thực hiện theo trình tự sau:

1. Chọn `slidingWindowType` và `slidingWindowSize` phù hợp với bài test.
2. Đặt `minimumNumberOfCalls` nhỏ để có thể tạo đủ mẫu xác định.
3. Đặt `failureRateThreshold` rõ ràng, tránh test đúng sát ranh giới nếu không cần kiểm tra phép so sánh ngưỡng.
4. Tạo số mẫu ít hơn `minimumNumberOfCalls`, gồm các lỗi có kiểm soát.
5. Xác nhận breaker vẫn `CLOSED`, số mẫu buffered đúng và failure rate bằng `-1.0` khi chưa đủ mẫu.
6. Tạo thêm lời gọi để đạt minimum; xác nhận failure rate được tính và state thay đổi nếu tỷ lệ đạt ngưỡng.
7. Tạo trường hợp đủ mẫu nhưng tỷ lệ dưới ngưỡng; xác nhận breaker tiếp tục `CLOSED`.
8. Nếu có `ignoreExceptions`, xác nhận ignored không làm tăng số mẫu success/failure.
9. Nếu có fallback, xác nhận breaker vẫn ghi nhận lỗi gốc khi fallback được xử lý bên ngoài supplier.
10. Với `TIME_BASED`, kiểm tra hành vi theo khoảng thời gian và tránh test dựa trên sleep không xác định.

`minimumNumberOfCalls` ngăn circuit breaker đưa ra quyết định dựa trên quá ít dữ liệu. Khi chưa đủ mẫu, state vẫn có thể là `CLOSED` và failure rate được biểu diễn là chưa xác định (`-1.0`). Một bài kiểm thử tốt cần xác nhận số mẫu, số success/failure, failure rate và state cùng lúc; nhờ đó phân biệt được breaker đang chờ dữ liệu với breaker đã đánh giá dependency là đủ ổn định.
