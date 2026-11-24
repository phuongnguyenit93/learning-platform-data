# Kiểm thử cửa sổ theo số lượng và theo thời gian

Resilience4j Circuit Breaker dùng sliding window để tổng hợp kết quả lời gọi gần đây, sau đó tính failure rate và slow call rate. Hai kiểu cửa sổ phổ biến là COUNT_BASED và TIME_BASED. Kiểm thử cần xác nhận cửa sổ giữ đúng phạm vi dữ liệu, chỉ đánh giá khi đủ số mẫu tối thiểu và chuyển trạng thái theo ngưỡng đã cấu hình.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, kiểm thử hai kiểu cửa sổ giúp xác nhận cấu hình bảo vệ dịch vụ hoạt động đúng với lưu lượng thực tế. Ta cần kiểm tra cả kết quả thành công, lỗi, lời gọi chậm, dữ liệu bị loại khỏi cửa sổ và trạng thái CLOSED/OPEN/HALF_OPEN. Bài kiểm thử nên kiểm soát thời gian và thứ tự lời gọi để kết quả ổn định, dễ giải thích.

## 1. Hai kiểu cửa sổ có đơn vị khác nhau

| Kiểu | Ý nghĩa của `slidingWindowSize` | Dữ liệu được giữ |
| --- | --- | --- |
| `COUNT_BASED` | Số lượng lời gọi đã hoàn tất gần nhất | N kết quả gần nhất |
| `TIME_BASED` | Số giây của khoảng quan sát | Kết quả nằm trong N giây gần nhất, được tổng hợp theo bucket thời gian |

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-count:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
      inventory-time:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
~~~

Với `inventory-count`, cửa sổ giữ tối đa 20 kết quả lời gọi gần nhất. Với `inventory-time`, cửa sổ quan sát 10 giây gần nhất; kích thước 10 ở đây là 10 giây, không phải 10 request.

COUNT_BASED phù hợp khi muốn đánh giá theo số mẫu, bất kể tốc độ request. TIME_BASED phù hợp khi cần đánh giá sức khỏe trong một khoảng thời gian cố định dù lưu lượng thay đổi.

## 2. Các tham số cần kiểm tra cùng sliding window

Chỉ kiểm tra `slidingWindowSize` là chưa đủ. Các tham số sau quyết định thời điểm Circuit Breaker đánh giá và chuyển trạng thái:

| Thuộc tính | Vai trò khi kiểm thử |
| --- | --- |
| `slidingWindowType` | Chọn cửa sổ theo số lời gọi hay theo thời gian |
| `slidingWindowSize` | Xác định số mẫu hoặc độ dài khoảng thời gian |
| `minimumNumberOfCalls` | Số kết quả tối thiểu trước khi tính tỷ lệ |
| `failureRateThreshold` | Ngưỡng phần trăm lời gọi thất bại để mở mạch |
| `slowCallDurationThreshold` | Thời lượng từ đó lời gọi được xem là chậm |
| `slowCallRateThreshold` | Ngưỡng phần trăm lời gọi chậm để mở mạch |
| `waitDurationInOpenState` | Thời gian mạch ở OPEN trước khi cho phép kiểm tra phục hồi |
| `permittedNumberOfCallsInHalfOpenState` | Số lời gọi thử nghiệm được phép trong HALF_OPEN |

Ví dụ cấu hình dùng cho kiểm thử:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-test:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        slowCallDurationThreshold: 100ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 2s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Các giá trị nhỏ giúp tái hiện hành vi nhanh trong test. Chúng chỉ dành cho cấu hình kiểm thử; không nên sao chép nguyên xi vào production nếu chưa đánh giá lưu lượng và độ trễ của phụ thuộc.

## 3. Kiểm tra minimumNumberOfCalls

`minimumNumberOfCalls` ngăn Circuit Breaker đưa ra quyết định dựa trên quá ít mẫu. Ví dụ, cửa sổ có kích thước 10 và ngưỡng lỗi 50%, nhưng chỉ có 3 lời gọi và cả 3 đều thất bại. Tỷ lệ quan sát là 100%, tuy nhiên Circuit Breaker chưa mở mạch nếu `minimumNumberOfCalls` là 5.

Kịch bản kiểm thử:

1. Tạo Circuit Breaker với cửa sổ 10, tối thiểu 5 lời gọi và failure threshold 50%.
2. Ghi nhận 3 kết quả lỗi.
3. Xác nhận trạng thái vẫn CLOSED vì chưa đủ 5 mẫu.
4. Ghi nhận thêm 2 kết quả lỗi.
5. Xác nhận failure rate đạt 100% trên 5 mẫu và mạch chuyển OPEN.

Khi kiểm thử, hãy xác nhận số lời gọi đã được ghi nhận bằng metrics của instance. Exception được cấu hình bỏ qua không được tính như một kết quả thành công hay thất bại trong cửa sổ. Lời gọi bị từ chối khi mạch OPEN cũng không phải một lời gọi mới đến phụ thuộc để đưa vào mẫu.

## 4. Kiểm thử COUNT_BASED bằng JUnit

Có thể ghi nhận kết quả trực tiếp trên Circuit Breaker bằng `onSuccess` và `onError`. Cách này hữu ích để kiểm tra logic cửa sổ mà không phụ thuộc vào HTTP server hoặc client thật:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CountBasedWindowTest {
    @Test
    void opensOnlyAfterMinimumNumberOfCalls() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .build();

        CircuitBreaker breaker =
                CircuitBreaker.of("inventory-count-test", config);

        breaker.onError(10, TimeUnit.MILLISECONDS,
                new IOException("connection failed"));
        breaker.onError(10, TimeUnit.MILLISECONDS,
                new IOException("connection failed"));
        breaker.onSuccess(10, TimeUnit.MILLISECONDS);

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());

        breaker.onSuccess(10, TimeUnit.MILLISECONDS);

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }
}
~~~

Sau 3 kết quả, Circuit Breaker chưa có đủ mẫu để đánh giá. Kết quả thứ tư làm đủ minimumNumberOfCalls; khi đó 2 trong 4 lời gọi thất bại, tỷ lệ lỗi bằng 50% và đạt ngưỡng nên mạch chuyển OPEN.

`onSuccess` và `onError` mô phỏng kết quả đã hoàn tất của một lời gọi. Trong kiểm thử tích hợp, có thể thay chúng bằng lời gọi thực qua `executeSupplier`, `executeCallable` hoặc decorator phù hợp để xác nhận cả HTTP client, timeout và phân loại exception.

## 5. Kiểm tra việc loại kết quả cũ khỏi COUNT_BASED window

COUNT_BASED chỉ giữ N kết quả gần nhất. Khi kết quả mới đi vào cửa sổ đã đầy, kết quả cũ nhất bị loại khỏi thống kê.

Ví dụ với cửa sổ 4, minimumNumberOfCalls bằng 4 và failure threshold 50%:

| Thứ tự | Kết quả mới | Bốn kết quả trong cửa sổ sau khi ghi nhận | Failure rate |
| ---: | --- | --- | ---: |
| 1 | Thành công | Chưa đủ mẫu | Chưa đánh giá |
| 2 | Thành công | Chưa đủ mẫu | Chưa đánh giá |
| 3 | Thành công | Chưa đủ mẫu | Chưa đánh giá |
| 4 | Thành công | Thành công, thành công, thành công, thành công | 0% |
| 5 | Thất bại | Thành công, thành công, thành công, thất bại | 25% |
| 6 | Thất bại | Thành công, thành công, thất bại, thất bại | 50% |

Sau kết quả thứ năm, thành công đầu tiên đã rời khỏi cửa sổ. Sau kết quả thứ sáu, cửa sổ còn hai thành công và hai thất bại, nên tỷ lệ lỗi đạt 50% và Circuit Breaker mở mạch.

Test tương ứng:

~~~java
@Test
void evictsOldestResultWhenCountWindowIsFull() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50)
            .build();

    CircuitBreaker breaker =
            CircuitBreaker.of("inventory-eviction-test", config);

    for (int i = 0; i < 4; i++) {
        breaker.onSuccess(5, TimeUnit.MILLISECONDS);
    }
    assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());

    breaker.onError(5, TimeUnit.MILLISECONDS, new IOException("first failure"));
    assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());

    breaker.onError(5, TimeUnit.MILLISECONDS, new IOException("second failure"));
    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
}
~~~

Kiểm thử này xác nhận cửa sổ trượt theo số lượng, thay vì tính tỷ lệ trên toàn bộ lịch sử từ lúc instance được tạo.

## 6. Kiểm thử TIME_BASED window

Với TIME_BASED, mỗi bucket đại diện cho một khoảng thời gian và cửa sổ chỉ giữ các bucket nằm trong số giây đã cấu hình. Ví dụ `slidingWindowSize: 5` theo dõi khoảng 5 giây gần nhất. Khi thời gian tiến lên, bucket cũ hết hạn và thống kê của nó không còn đóng góp vào tổng.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-time-test:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 5
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        slowCallDurationThreshold: 200ms
        slowCallRateThreshold: 50
~~~

Kịch bản kiểm thử nên tập trung vào ba điểm:

1. Ghi nhận một số kết quả trong cùng khoảng thời gian và xác nhận chúng được tính vào cửa sổ.
2. Tiến thời gian vượt khỏi khoảng chứa các kết quả cũ, sau đó tạo hoặc đọc snapshot thống kê để xác nhận các bucket hết hạn không còn được tính.
3. Ghi nhận kết quả mới trong bucket hiện tại và xác nhận tỷ lệ được tính trên các bucket còn hiệu lực.

Để test ổn định, ưu tiên điều khiển thời gian bằng clock giả nếu phiên bản Resilience4j đang dùng hỗ trợ cấu hình clock cho Circuit Breaker. Nếu không có khả năng inject clock, dùng kiểm thử tích hợp với cửa sổ ngắn và Awaitility để chờ điều kiện thống kê thay đổi; tránh phụ thuộc vào một `Thread.sleep` cố định rồi giả định bucket đã xoay chính xác tại thời điểm đó.

Ví dụ về cấu hình TIME_BASED cần kiểm tra:

- `slidingWindowSize` là số giây, không phải số request.
- Nhiều lời gọi trong cùng một bucket thời gian được tổng hợp trong bucket đó.
- Kết quả cũ rời khỏi cửa sổ khi bucket tương ứng hết hạn.
- `minimumNumberOfCalls` vẫn phải đạt trước khi tỷ lệ được dùng để mở mạch.
- Lưu lượng thấp có thể khiến cửa sổ thời gian chưa có đủ mẫu để đánh giá.

## 7. Kiểm tra sự khác nhau khi lưu lượng thay đổi

COUNT_BASED và TIME_BASED có thể cho kết quả khác nhau khi tốc độ request thay đổi:

| Tình huống | COUNT_BASED | TIME_BASED |
| --- | --- | --- |
| Lưu lượng tăng đột biến | Cửa sổ N lời gọi bao phủ khoảng thời gian ngắn hơn | Cửa sổ vẫn giữ nguyên số giây nhưng chứa nhiều lời gọi hơn |
| Lưu lượng giảm mạnh | Cửa sổ N lời gọi trải dài qua thời gian lâu hơn | Cửa sổ chỉ giữ dữ liệu trong khoảng giây đã chọn |
| Cần đánh giá N lời gọi gần nhất | Phù hợp trực tiếp | Không đảm bảo có đúng N lời gọi |
| Cần đánh giá 30 giây gần nhất | Khoảng thời gian thực tế thay đổi theo lưu lượng | Phù hợp trực tiếp |

Một bài kiểm thử tốt nên tạo ít nhất hai nhịp tải: nhịp có nhiều lời gọi trong một giây và nhịp có ít lời gọi trong vài giây. Quan sát số kết quả được buffer và failure rate để xác nhận hai loại cửa sổ phản ứng đúng theo đơn vị của chúng.

## 8. Kiểm thử slow call rate riêng với failure rate

Một lời gọi chậm vẫn có thể hoàn tất thành công. Vì vậy, failure rate và slow call rate cần được kiểm tra độc lập.

Ví dụ:

~~~java
@Test
void opensWhenSlowCallRateReachesThreshold() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(75)
            .slowCallDurationThreshold(java.time.Duration.ofMillis(100))
            .slowCallRateThreshold(50)
            .build();

    CircuitBreaker breaker =
            CircuitBreaker.of("inventory-slow-test", config);

    breaker.onSuccess(200, TimeUnit.MILLISECONDS);
    breaker.onSuccess(250, TimeUnit.MILLISECONDS);
    breaker.onSuccess(20, TimeUnit.MILLISECONDS);
    breaker.onSuccess(30, TimeUnit.MILLISECONDS);

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
}
~~~

Trong 4 lời gọi, có 2 lời gọi chậm hơn 100 ms nhưng cả 4 đều thành công. Failure rate bằng 0%, còn slow call rate bằng 50%. Vì slow call threshold là 50%, Circuit Breaker mở mạch do tỷ lệ lời gọi chậm đạt ngưỡng, không phải do exception.

Test này giúp phát hiện cấu hình chỉ theo dõi lỗi exception mà bỏ qua suy giảm độ trễ. Cần chọn thời lượng và số mẫu đủ rõ ràng để tránh phụ thuộc vào tốc độ máy chạy test; ví dụ dùng `onSuccess(duration, unit)` giúp ghi nhận thời lượng xác định mà không phải chờ thực tế.

## 9. Kiểm tra các trạng thái sau khi cửa sổ đạt ngưỡng

Khi đủ mẫu và tỷ lệ chạm ngưỡng, Circuit Breaker chuyển từ CLOSED sang OPEN. Khi OPEN, lời gọi mới bị từ chối bằng `CallNotPermittedException` mà không chạy supplier. Sau `waitDurationInOpenState`, mạch có thể chuyển sang HALF_OPEN và chỉ cho phép số lời gọi thử nghiệm đã cấu hình.

Các điểm nên xác nhận:

| Trạng thái | Hành vi cần kiểm tra |
| --- | --- |
| CLOSED | Lời gọi được thực hiện và kết quả được đưa vào cửa sổ |
| OPEN | Lời gọi mới bị từ chối; supplier không được gọi |
| HALF_OPEN | Chỉ số lời gọi thử nghiệm được phép mới đi qua |
| Trở lại CLOSED | Các lời gọi thử nghiệm đạt yêu cầu theo ngưỡng |
| Quay lại OPEN | Lời gọi thử nghiệm tiếp tục lỗi hoặc chậm vượt ngưỡng |

Không nên kiểm tra chuyển trạng thái bằng cách chỉ assert một exception bất kỳ. Hãy assert state hiện tại, số lần supplier được gọi và loại exception bị từ chối. Điều này giúp phân biệt lỗi thật từ dịch vụ phụ thuộc với việc Circuit Breaker chủ động chặn request.

## 10. Kiểm thử exception bị ignore và exception được ghi nhận

Sliding window chỉ nên phản ánh những kết quả được cấu hình để tham gia thống kê. Resilience4j cho phép bỏ qua một số exception nghiệp vụ, chẳng hạn sản phẩm không tồn tại, để chúng không làm tăng failure rate của dịch vụ Kho.

Ví dụ cấu hình:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(4)
        .minimumNumberOfCalls(4)
        .failureRateThreshold(50)
        .ignoreExceptions(InventoryNotFoundException.class)
        .build();
~~~

Khi kiểm thử, ghi nhận một `InventoryNotFoundException` rồi kiểm tra số lời gọi được buffer không tăng như một kết quả thành công hoặc thất bại. Sau đó ghi nhận đủ các kết quả được tính và xác nhận tỷ lệ được tính trên các kết quả đó.

Không nhầm exception bị ignore với exception được xem là thành công. Lỗi bị ignore không đóng góp vào failure rate và cũng không làm tăng số mẫu như một lời gọi thành công. Lỗi từ chối do mạch OPEN cũng không phải kết quả của lời gọi đến phụ thuộc để thêm vào cửa sổ.

## 11. Tổ chức test để tránh kết quả phụ thuộc lẫn nhau

Mỗi test nên tạo Circuit Breaker instance riêng hoặc dùng registry riêng cho test đó. Điều này tránh lịch sử cửa sổ từ test trước làm thay đổi kết quả test sau.

Một số nguyên tắc:

- Dùng tên instance riêng cho từng test hoặc tạo instance mới từ cấu hình test.
- Không chia sẻ một Circuit Breaker mutable giữa nhiều test chạy song song.
- Dùng `onSuccess` và `onError` để kiểm tra thống kê một cách xác định khi không cần kiểm tra HTTP client.
- Dùng mock server hoặc client giả khi cần xác minh exception thực tế được chuyển đến Circuit Breaker.
- Với TIME_BASED, điều khiển clock nếu phiên bản hỗ trợ; nếu không, chờ điều kiện bằng polling có timeout thay vì dựa vào sleep cứng.
- Đặt `waitDurationInOpenState` ngắn trong test state transition và khôi phục cấu hình production riêng.
- Xác minh trạng thái và metrics sau mỗi giai đoạn, không chỉ kiểm tra kết quả trả về cuối cùng.

Không dùng chung registry singleton của môi trường ứng dụng cho các test độc lập nếu các test có thể thay đổi state của cùng instance. Registry dùng chung là hành vi cần có trong runtime production, còn test cần cô lập dữ liệu để có thể lặp lại ổn định.

## 12. Những lỗi thường gặp khi kiểm thử sliding window

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nhầm TIME_BASED size là số request | Kịch bản test tạo sai số mẫu | Ghi rõ đơn vị giây trong test |
| Không kiểm tra minimumNumberOfCalls | Kỳ vọng mạch OPEN quá sớm | Tạo đủ số kết quả được tính trước khi assert |
| Dùng một instance chung cho nhiều test | Lịch sử cửa sổ làm test phụ thuộc thứ tự | Tạo instance riêng cho mỗi test |
| Kiểm tra chỉ failure rate | Bỏ sót suy giảm do lời gọi chậm | Kiểm tra slow call threshold và slow call rate |
| Dùng Thread.sleep cố định cho TIME_BASED | Test dễ flaky ở ranh giới bucket | Dùng clock kiểm soát được hoặc Awaitility |
| Ghi nhận exception bị ignore như một success | Tính sai mẫu và tỷ lệ | Xác nhận exception bị ignore không đóng góp vào cửa sổ |
| Tiếp tục gọi supplier sau khi mạch OPEN | Test không phân biệt được từ chối với lỗi phụ thuộc | Assert supplier không được gọi khi OPEN |
| Chỉ kiểm tra kết quả API | Không biết cửa sổ hoặc state có cập nhật đúng | Kiểm tra state, metrics và số lần gọi |

## 13. Bộ kịch bản kiểm thử tối thiểu

Trước khi chấp nhận cấu hình, nên có các kịch bản:

1. COUNT_BASED chưa đủ `minimumNumberOfCalls`: mạch vẫn CLOSED dù tỷ lệ lỗi tạm thời cao.
2. COUNT_BASED đủ mẫu và tỷ lệ đạt ngưỡng: mạch chuyển OPEN.
3. COUNT_BASED nhận kết quả mới: kết quả cũ nhất bị loại khỏi cửa sổ.
4. TIME_BASED có kết quả trong khoảng quan sát: các kết quả được tính trong bucket tương ứng.
5. TIME_BASED hết hạn bucket cũ: kết quả ngoài khoảng thời gian không còn đóng góp vào thống kê.
6. Slow call rate đạt ngưỡng trong khi failure rate thấp: mạch vẫn có thể OPEN do lời gọi chậm.
7. Exception bị ignore: không làm tăng failure rate hoặc số mẫu được tính.
8. OPEN từ chối lời gọi: supplier không chạy và trạng thái không bị nhầm thành lỗi mới của phụ thuộc.
9. HALF_OPEN thử nghiệm: chỉ số lời gọi được phép đi qua được thực hiện.
10. Kết quả thử nghiệm phục hồi hoặc thất bại: mạch chuyển CLOSED hoặc OPEN đúng theo cấu hình.

## 14. Quy trình thực hiện kiểm thử

Khi kiểm thử sliding window trong một module Spring Cloud, hãy thực hiện theo trình tự:

1. Chọn kiểu cửa sổ COUNT_BASED hoặc TIME_BASED theo mục tiêu quan sát.
2. Đặt kích thước cửa sổ, minimumNumberOfCalls và các ngưỡng lỗi/chậm có thể tái hiện nhanh trong test.
3. Tạo instance Circuit Breaker mới để cô lập trạng thái.
4. Ghi nhận kết quả thành công, thất bại và chậm theo thứ tự xác định.
5. Kiểm tra số mẫu được buffer, failure rate, slow call rate và state sau từng giai đoạn.
6. Với COUNT_BASED, xác nhận kết quả cũ rời cửa sổ khi có kết quả mới.
7. Với TIME_BASED, điều khiển thời gian hoặc chờ bucket hết hạn bằng cơ chế polling có giới hạn.
8. Kiểm tra exception ignore, lời gọi bị từ chối và chuyển trạng thái HALF_OPEN.
9. Chạy kiểm thử tích hợp với HTTP client để xác nhận timeout và status lỗi thực tế được ghi nhận đúng.
10. Giữ cấu hình kiểm thử tách biệt khỏi cấu hình production và ghi rõ đơn vị của mọi tham số.

Kiểm thử cửa sổ theo số lượng xác nhận Circuit Breaker luôn đánh giá trên N kết quả gần nhất; kiểm thử cửa sổ theo thời gian xác nhận dữ liệu cũ hết hạn theo khoảng giây đã cấu hình. Khi kiểm tra thêm minimumNumberOfCalls, slow call rate và các trạng thái, nhóm phát triển có thể tin cậy rằng Resilience4j mở mạch đúng thời điểm và bảo vệ dịch vụ phụ thuộc theo chính sách mong muốn.
