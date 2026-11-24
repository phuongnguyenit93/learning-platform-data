# Cửa sổ theo số lời gọi và theo khoảng thời gian

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, Circuit Breaker của Spring Cloud kết hợp Resilience4j giúp giới hạn tác động khi một dịch vụ phụ thuộc chậm hoặc không khả dụng. Để quyết định khi nào cần mở mạch, Circuit Breaker phải quan sát kết quả các lời gọi gần đây. Resilience4j cung cấp hai cách quan sát: cửa sổ theo số lời gọi (**COUNT_BASED**) và cửa sổ theo thời gian (**TIME_BASED**).

Hai kiểu cửa sổ cùng phục vụ một mục tiêu: tính tỷ lệ lỗi và tỷ lệ lời gọi chậm từ dữ liệu gần đây. Điểm khác nhau là cách xác định phạm vi dữ liệu. COUNT_BASED giữ một số lượng lời gọi mới nhất; TIME_BASED giữ kết quả trong một khoảng thời gian gần nhất. Chọn đúng kiểu cửa sổ giúp Circuit Breaker phản ứng phù hợp với lưu lượng thực tế của dịch vụ.

## 1. Sliding window dùng để làm gì?

Giả sử dịch vụ Đơn hàng gọi dịch vụ Kho để kiểm tra tồn kho. Nếu chỉ nhìn vào một lời gọi, một lỗi đơn lẻ có thể khiến hệ thống phản ứng quá sớm. Ngược lại, nếu chỉ tính tỷ lệ lỗi từ khi ứng dụng khởi động, các lỗi cũ có thể tiếp tục ảnh hưởng đến quyết định dù dịch vụ Kho đã phục hồi.

Sliding window (cửa sổ trượt) giới hạn dữ liệu được dùng để đánh giá tình trạng gần đây. Mỗi khi một lời gọi hoàn tất, kết quả của nó được ghi nhận. Khi cửa sổ dịch chuyển, dữ liệu nằm ngoài phạm vi sẽ không còn tham gia vào phép tính.

Circuit Breaker thường theo dõi ít nhất hai tỷ lệ:

- **Tỷ lệ lỗi (failure rate):** phần trăm lời gọi được ghi nhận là thất bại.
- **Tỷ lệ lời gọi chậm (slow call rate):** phần trăm lời gọi có thời gian thực hiện vượt **slowCallDurationThreshold**.

Các tỷ lệ này được so sánh với **failureRateThreshold** và **slowCallRateThreshold**. Nếu một tỷ lệ đạt hoặc vượt ngưỡng sau khi đã có đủ số mẫu tối thiểu, Circuit Breaker có thể chuyển từ CLOSED sang OPEN.

Về khái niệm, hai phép tính có dạng:

$$
\text{Failure rate} =
\frac{\text{số lời gọi thất bại}}{\text{tổng lời gọi được ghi nhận trong cửa sổ}}
\times 100\%
$$

$$
\text{Slow call rate} =
\frac{\text{số lời gọi chậm}}{\text{tổng lời gọi được ghi nhận trong cửa sổ}}
\times 100\%
$$

Một lời gọi chậm vẫn có thể thành công. Ví dụ, dịch vụ Kho trả HTTP 200 sau 4 giây; nếu ngưỡng lời gọi chậm là 2 giây, lời gọi đó được xem là chậm dù không thất bại. Việc theo dõi riêng hai tỷ lệ giúp phát hiện cả tình trạng lỗi và suy giảm độ trễ.

## 2. Cửa sổ theo số lời gọi — COUNT_BASED

Với **COUNT_BASED**, **slidingWindowSize** là số lượng lời gọi gần nhất được giữ trong cửa sổ. Ví dụ, kích thước bằng 10 nghĩa là Circuit Breaker đánh giá tối đa 10 kết quả lời gọi gần nhất đã hoàn tất.

Khi có kết quả mới:

1. Kết quả mới được thêm vào cửa sổ.
2. Nếu cửa sổ đã đủ kích thước, kết quả cũ nhất rời khỏi cửa sổ.
3. Circuit Breaker cập nhật số lượng thành công, thất bại và lời gọi chậm trong cửa sổ.
4. Khi đủ số mẫu tối thiểu, các tỷ lệ được so sánh với ngưỡng cấu hình.

Có thể hình dung cửa sổ kích thước 5 như sau:

~~~text
Thời điểm A: [Thành công, Thành công, Lỗi, Thành công, Thành công]
Thêm một lời gọi Lỗi:
Thời điểm B: [Thành công, Lỗi, Thành công, Thành công, Lỗi]
               ^ kết quả cũ nhất đã rời cửa sổ
~~~

Ví dụ, cửa sổ có 10 lời gọi và ghi nhận 3 lời gọi thất bại. Tỷ lệ lỗi là 30%. Nếu ngưỡng lỗi là 50%, mạch chưa mở vì tỷ lệ chưa đạt ngưỡng. Khi các lời gọi mới hoàn tất và thay thế những kết quả cũ, tỷ lệ có thể tăng hoặc giảm. Nếu cửa sổ hiện có 5 lời gọi thất bại trong 10 lời gọi, tỷ lệ lỗi đạt 50% và chạm ngưỡng.

### Đặc điểm của COUNT_BASED

- Số lượng mẫu trong cửa sổ tương đối ổn định sau khi cửa sổ đã đầy.
- Thời gian bao phủ của cửa sổ thay đổi theo lưu lượng. Với 100 lời gọi mỗi giây, cửa sổ 100 lời gọi chỉ phản ánh xấp xỉ một giây; với một lời gọi mỗi phút, nó có thể phản ánh gần 100 phút.
- Mỗi lời gọi có trọng số như nhau trong phép tính tỷ lệ, dù các lời gọi cách nhau vài mili giây hay vài phút.
- Cửa sổ phù hợp khi muốn đánh giá một số giao dịch gần nhất và lưu lượng không thay đổi quá đột ngột, hoặc khi số lượng mẫu là tiêu chí quan trọng hơn độ dài thời gian.

COUNT_BASED không có nghĩa là Circuit Breaker chỉ hoạt động sau khi đủ toàn bộ **slidingWindowSize**. Việc bắt đầu tính tỷ lệ được kiểm soát bởi **minimumNumberOfCalls**. Ví dụ, kích thước cửa sổ là 20 nhưng số mẫu tối thiểu là 10, Circuit Breaker có thể đánh giá sau khi đã ghi nhận đủ 10 lời gọi; cửa sổ tiếp tục được cập nhật khi có thêm kết quả.

## 3. Cửa sổ theo khoảng thời gian — TIME_BASED

Với **TIME_BASED**, **slidingWindowSize** là độ dài cửa sổ tính bằng giây. Ví dụ, kích thước bằng 10 nghĩa là Circuit Breaker quan sát các kết quả lời gọi trong 10 giây gần nhất.

Resilience4j chia cửa sổ thời gian thành các bucket (ô thống kê), mỗi bucket tương ứng một giây. Mỗi bucket lưu phần thống kê của các lời gọi được ghi nhận trong giây đó. Khi cửa sổ trượt sang giây mới, bucket cũ nhất rời khỏi phạm vi và bucket mới được dùng để thu thập kết quả tiếp theo. Các số liệu trong những bucket còn nằm trong cửa sổ được cộng lại để tạo thống kê tổng.

Ví dụ, với cửa sổ 5 giây, tại thời điểm 12:00:05, phạm vi quan sát gần đúng là các bucket từ 12:00:01 đến 12:00:05. Khi sang 12:00:06, bucket của 12:00:01 rời cửa sổ và bucket 12:00:06 được thêm vào.

~~~text
Thời điểm 12:00:05
[12:00:01] [12:00:02] [12:00:03] [12:00:04] [12:00:05]
      <---------- cửa sổ 5 giây ---------->

Thời điểm 12:00:06
             [12:00:02] [12:00:03] [12:00:04] [12:00:05] [12:00:06]
                   <---------- cửa sổ 5 giây ---------->
~~~

Giả sử trong 10 giây gần nhất có 40 lời gọi, trong đó 8 lời gọi thất bại. Tỷ lệ lỗi là 20%. Nếu trong giây tiếp theo có thêm 10 lời gọi và bucket cũ nhất rời cửa sổ, tỷ lệ mới được tính trên tổng kết quả còn lại trong phạm vi 10 giây mới. Số lượng lời gọi trong cửa sổ có thể tăng hoặc giảm theo lưu lượng; nó không cố định như COUNT_BASED.

### Đặc điểm của TIME_BASED

- Phạm vi quan sát luôn hướng tới một khoảng thời gian cố định, ví dụ 10 giây gần nhất.
- Số lượng mẫu thay đổi theo lưu lượng. Trong giờ cao điểm có thể có hàng trăm lời gọi; lúc ít tải có thể chỉ có vài lời gọi.
- Kết quả cũ tự rời khỏi cửa sổ khi khoảng thời gian tương ứng trôi qua, nên tỷ lệ phản ánh tình hình theo thời gian.
- Kiểu cửa sổ này hữu ích khi lưu lượng thay đổi đáng kể và muốn biết tình trạng dịch vụ trong một khoảng thời gian ngắn gần nhất.

TIME_BASED không tự động đưa ra quyết định chỉ vì một bucket có tỷ lệ lỗi cao. Circuit Breaker vẫn cần đạt **minimumNumberOfCalls** trong cửa sổ trước khi tính tỷ lệ. Ví dụ, cửa sổ 10 giây có 4 lời gọi, trong đó 2 lỗi, tạo tỷ lệ quan sát được là 50%; nhưng nếu **minimumNumberOfCalls** là 10 thì chưa đủ mẫu để dùng tỷ lệ đó ra quyết định mở mạch.

## 4. Vai trò của minimumNumberOfCalls

**minimumNumberOfCalls** là số lời gọi tối thiểu phải được ghi nhận trong cửa sổ trước khi Circuit Breaker tính tỷ lệ lỗi và tỷ lệ lời gọi chậm để quyết định trạng thái.

Tham số này giúp tránh kết luận từ một mẫu quá nhỏ. Nếu chỉ có 2 lời gọi và cả 2 đều thất bại, tỷ lệ lỗi là 100%, nhưng chưa chắc đó đã là dấu hiệu đủ tin cậy để ngắt mọi lời gọi tiếp theo. Khi yêu cầu tối thiểu là 10, Circuit Breaker chờ đủ 10 kết quả trước khi đánh giá tỷ lệ.

Ví dụ với **minimumNumberOfCalls: 10**:

| Số lời gọi đã ghi nhận | Số lời gọi thất bại | Tỷ lệ lỗi quan sát được | Đủ mẫu để đánh giá? |
| ---: | ---: | ---: | --- |
| 2 | 2 | 100% | Chưa |
| 8 | 4 | 50% | Chưa |
| 10 | 4 | 40% | Đủ |
| 10 | 6 | 60% | Đủ |

Giả sử **failureRateThreshold** bằng 50%. Khi có 10 kết quả và 4 lỗi, tỷ lệ 40% chưa chạm ngưỡng. Khi có 10 kết quả và 6 lỗi, tỷ lệ 60% vượt ngưỡng nên Circuit Breaker có thể mở mạch.

Đối với TIME_BASED, nếu lưu lượng quá thấp và cửa sổ không bao giờ có đủ số lời gọi tối thiểu, Circuit Breaker sẽ không tính tỷ lệ để mở mạch dựa trên các mẫu đó. Đối với COUNT_BASED, thời gian cần thiết để tích lũy đủ mẫu có thể kéo dài khi ít lưu lượng. Vì vậy, cần cân nhắc cả kích thước cửa sổ, lưu lượng thực tế và số mẫu tối thiểu.

## 5. So sánh hai kiểu cửa sổ

| Tiêu chí | COUNT_BASED | TIME_BASED |
| --- | --- | --- |
| **slidingWindowSize** biểu thị | Số lời gọi gần nhất | Số giây gần nhất |
| Phạm vi quan sát | Thay đổi theo tốc độ gọi | Cố định theo thời gian |
| Số mẫu trong cửa sổ | Ổn định khi cửa sổ đã đầy | Thay đổi theo lưu lượng |
| Khi lưu lượng tăng | Cửa sổ bao phủ khoảng thời gian ngắn hơn | Có nhiều mẫu hơn trong cùng khoảng thời gian |
| Khi lưu lượng giảm | Cửa sổ bao phủ khoảng thời gian dài hơn | Có thể không đủ mẫu tối thiểu |
| Thích hợp khi | Muốn đánh giá N lời gọi mới nhất | Muốn đánh giá tình trạng trong T giây gần nhất |

Ví dụ, dịch vụ Kho có lưu lượng 5 lời gọi mỗi giây. Cửa sổ COUNT_BASED kích thước 50 sẽ bao phủ khoảng 10 giây khi lưu lượng ổn định. Nếu lưu lượng tăng lên 50 lời gọi mỗi giây, cùng cửa sổ chỉ bao phủ khoảng một giây. Cửa sổ TIME_BASED 10 giây vẫn bao phủ 10 giây trong cả hai trường hợp, nhưng số mẫu sẽ khác nhau.

Không có kiểu nào luôn tốt hơn. COUNT_BASED trả lời câu hỏi “N lời gọi gần nhất có đang gặp vấn đề không?”, còn TIME_BASED trả lời câu hỏi “Trong T giây gần nhất, dịch vụ có đang gặp vấn đề không?”. Câu hỏi vận hành cần trả lời nên quyết định lựa chọn.

## 6. Cấu hình trong Spring Cloud CircuitBreaker với Resilience4j

Spring Cloud CircuitBreaker cho phép dùng Resilience4j làm implementation. Các instance được cấu hình theo tên trong **application.yml**. Tên instance phải trùng với tên được dùng khi tạo Circuit Breaker trong ứng dụng, ví dụ **inventory**.

### Ví dụ COUNT_BASED

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
~~~

Trong cấu hình này:

- Cửa sổ giữ tối đa 20 lời gọi gần nhất.
- Cần ít nhất 10 kết quả trước khi tính tỷ lệ.
- Nếu tỷ lệ lỗi đạt 50% hoặc tỷ lệ lời gọi chậm đạt 60%, Circuit Breaker có thể chuyển sang OPEN.
- Lời gọi kéo dài hơn 2 giây được phân loại là lời gọi chậm.
- Khi đã OPEN, mạch duy trì trạng thái trong 10 giây theo **waitDurationInOpenState** trước khi cho phép giai đoạn thử nghiệm HALF_OPEN.

### Ví dụ TIME_BASED

Để chuyển sang cửa sổ thời gian, thay đổi kiểu và kích thước cửa sổ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
~~~

Ở cấu hình này, **slidingWindowSize: 10** có nghĩa là 10 giây gần nhất, không phải 10 lời gọi. Nếu trong khoảng thời gian đó có ít hơn 10 kết quả, Circuit Breaker chưa đủ mẫu để đánh giá tỷ lệ. Các tham số về ngưỡng lỗi, lời gọi chậm và thời gian OPEN có ý nghĩa tương tự ví dụ COUNT_BASED.

Hai đoạn YAML trên là hai lựa chọn cấu hình cho cùng instance **inventory**; khi triển khai, chọn một kiểu cửa sổ phù hợp với mục tiêu vận hành. Không nên tạo hai cấu hình trùng tên instance với mong muốn chúng hoạt động đồng thời.

### Gọi Circuit Breaker theo tên instance

Với Spring Cloud CircuitBreaker abstraction, ứng dụng có thể tạo Circuit Breaker theo tên cấu hình:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Inventory getInventory(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> callInventoryService(sku),
                error -> Inventory.unavailable(sku)
        );
    }

    private Inventory callInventoryService(String sku) {
        // Thực hiện lời gọi HTTP đến dịch vụ Kho.
        return fetchInventory(sku);
    }

    private Inventory fetchInventory(String sku) {
        // Phần gọi HTTP được lược giản để tập trung vào Circuit Breaker.
        return new Inventory(sku);
    }
}
~~~

Tên **inventory** liên kết lời gọi trong mã nguồn với instance cấu hình trong YAML. Trong ứng dụng thực tế, phần gọi HTTP cần được triển khai bằng client phù hợp và fallback phải biểu diễn chính xác trạng thái dữ liệu. Ví dụ trên chỉ minh họa cách chọn instance; nó không thay thế việc cấu hình timeout cho HTTP client.

## 7. Chọn kích thước cửa sổ và ngưỡng như thế nào?

Kích thước cửa sổ và số mẫu tối thiểu ảnh hưởng trực tiếp đến tốc độ phát hiện lỗi và độ ổn định của quyết định.

**Cửa sổ quá nhỏ** có thể phản ứng nhanh nhưng tỷ lệ biến động mạnh khi chỉ một vài lời gọi thay đổi kết quả. Một đợt lỗi ngắn có thể khiến mạch mở dù dịch vụ đã sớm phục hồi.

**Cửa sổ quá lớn** làm mượt biến động ngẫu nhiên nhưng có thể khiến sự cố mới bị pha loãng bởi nhiều kết quả thành công cũ. Circuit Breaker có thể cần nhiều thời gian hơn để phát hiện suy giảm.

**minimumNumberOfCalls quá thấp** làm cho quyết định dễ bị chi phối bởi một mẫu nhỏ. **minimumNumberOfCalls quá cao** có thể làm chậm quyết định, nhất là với dịch vụ ít lưu lượng hoặc cửa sổ TIME_BASED ngắn.

Một quy trình chọn cấu hình thực tế:

1. Đo lưu lượng theo thời gian, bao gồm giờ cao điểm và thời điểm ít yêu cầu.
2. Xác định mục tiêu phát hiện sự cố, ví dụ cần phản ứng trong 10 giây gần nhất hay sau 50 giao dịch gần nhất.
3. Chọn COUNT_BASED hoặc TIME_BASED theo mục tiêu đó.
4. Chọn **minimumNumberOfCalls** sao cho tỷ lệ không bị tính từ mẫu quá nhỏ, nhưng vẫn có thể đạt được với lưu lượng bình thường.
5. Đặt **failureRateThreshold** và **slowCallRateThreshold** dựa trên mức suy giảm có thể chấp nhận.
6. Quan sát trạng thái mạch và điều chỉnh dựa trên dữ liệu vận hành thực tế.

Đối với một dịch vụ có lưu lượng dao động theo giờ, TIME_BASED thường giúp câu hỏi “tình trạng trong 10 giây vừa qua” nhất quán hơn. Tuy vậy, phải kiểm tra lưu lượng thấp có đáp ứng **minimumNumberOfCalls** hay không. Với một tác vụ nền có số lần gọi đều đặn nhưng không nhiều, COUNT_BASED có thể giúp đánh giá một nhóm giao dịch gần nhất rõ ràng hơn.

## 8. Các điểm cần chú ý khi đọc kết quả

**Chỉ lời gọi đã có kết quả mới đóng góp vào thống kê.** Một lời gọi vẫn đang chờ không thể được phân loại là thành công, thất bại hoặc chậm cho đến khi nó hoàn tất hoặc bị timeout. Nếu dịch vụ phụ thuộc có thể treo lâu, cần cấu hình timeout ở HTTP client hoặc dùng TimeLimiter phù hợp. Circuit Breaker không tự thay thế timeout.

**Không phải exception nào cũng phải tính là lỗi phụ thuộc.** Một lỗi nghiệp vụ như mã SKU không tồn tại có thể là phản hồi hợp lệ của dịch vụ Kho. Nếu cấu hình ghi nhận nó như lỗi hạ tầng, tỷ lệ lỗi sẽ tăng sai lệch. Cần phân loại exception được ghi nhận và exception được bỏ qua theo ngữ nghĩa của ứng dụng.

**Lời gọi bị từ chối khi mạch OPEN khác với lời gọi thất bại.** Lời gọi bị từ chối không đi đến dịch vụ Kho, nên không phải một kết quả mới của thao tác phụ thuộc để đưa vào sliding window. Cần theo dõi số lời gọi bị từ chối riêng để biết Circuit Breaker đang chặn bao nhiêu yêu cầu.

**Tỷ lệ lỗi và tỷ lệ lời gọi chậm cần được đọc cùng nhau.** Dịch vụ có thể trả kết quả thành công nhưng quá chậm để đáp ứng nhu cầu. Nếu chỉ theo dõi failure rate, tình trạng này có thể không được phát hiện kịp thời.

**Mỗi instance có cửa sổ và thống kê riêng.** Nên đặt Circuit Breaker theo từng dịch vụ phụ thuộc hoặc nhóm thao tác có đặc tính tương đồng. Nếu nhiều phụ thuộc không liên quan dùng chung một instance, lỗi ở một phụ thuộc có thể làm ảnh hưởng quyết định đối với các phụ thuộc khác.

## 9. Theo dõi và kiểm chứng lựa chọn cửa sổ

Khi chạy thử, hãy quan sát các chỉ số theo từng instance:

- Trạng thái Circuit Breaker: CLOSED, OPEN hay HALF_OPEN.
- Tổng số lời gọi được ghi nhận, số thành công và số thất bại.
- Failure rate và slow call rate.
- Số lời gọi bị từ chối khi mạch OPEN.
- Số lần fallback được thực hiện và độ trễ phản hồi cuối cùng.

Resilience4j có thể cung cấp metrics qua Micrometer khi ứng dụng bật cấu hình tích hợp phù hợp. Spring Boot Actuator và hệ thống như Prometheus có thể thu thập số liệu để hiển thị trên dashboard. Khi đánh giá cửa sổ, cần đối chiếu tỷ lệ với số mẫu và phạm vi thời gian thực tế; một tỷ lệ 100% từ hai lời gọi mang ý nghĩa khác với 100% từ hai trăm lời gọi.

Một thử nghiệm đơn giản cho dịch vụ Kho:

1. Gửi lưu lượng ổn định với phần lớn lời gọi thành công và quan sát cửa sổ.
2. Tạo một đợt lỗi có kiểm soát để tỷ lệ lỗi tăng dần.
3. Quan sát thời điểm Circuit Breaker đủ **minimumNumberOfCalls** và chuyển sang OPEN.
4. Ngừng tạo lỗi, để các kết quả tốt mới đi vào cửa sổ hoặc chờ các bucket lỗi cũ hết phạm vi.
5. Quan sát giai đoạn HALF_OPEN và việc mạch trở lại CLOSED khi các lời gọi thử nghiệm đạt yêu cầu.

Với COUNT_BASED, cần quan sát số lời gọi mới thay thế kết quả cũ. Với TIME_BASED, cần quan sát các bucket cũ hết hạn theo thời gian. Hai cách này giúp giải thích vì sao tỷ lệ lỗi có thể giảm sau khi dịch vụ phục hồi, dù không có thao tác xóa lịch sử thủ công.

## 10. Tình huống lựa chọn

Một nền tảng bán hàng có hai loại phụ thuộc:

- Dịch vụ Kho nhận lưu lượng lớn, biến động mạnh theo chiến dịch. Nhóm vận hành muốn biết tỷ lệ lỗi trong 10 giây gần nhất để bảo vệ các yêu cầu đặt hàng. TIME_BASED với cửa sổ 10 giây là lựa chọn phù hợp để thử nghiệm, kèm **minimumNumberOfCalls** được chọn theo lưu lượng thấp nhất dự kiến.
- Một tác vụ đồng bộ định kỳ gửi một nhóm giao dịch với số lượng tương đối cố định. Nhóm phát triển muốn đánh giá 30 lời gọi gần nhất bất kể nhóm đó mất bao lâu để hoàn thành. COUNT_BASED với cửa sổ 30 lời gọi phù hợp hơn với mục tiêu này.

Trong cả hai trường hợp, nhóm phát triển vẫn phải đo độ trễ, phân loại exception và đặt timeout. Sau khi triển khai, cần so sánh số lần mạch mở, số lời gọi bị từ chối, tỷ lệ fallback và thời gian phục hồi để điều chỉnh cấu hình.

## 11. Tự kiểm tra

1. Với **COUNT_BASED** và **slidingWindowSize: 50**, Circuit Breaker đang quan sát điều gì?
2. Với **TIME_BASED** và **slidingWindowSize: 10**, số 10 biểu thị số lời gọi hay số giây?
3. Vì sao **minimumNumberOfCalls** quan trọng khi cửa sổ TIME_BASED có lưu lượng thấp?
4. Nếu lưu lượng tăng gấp 10 lần, phạm vi thời gian của cửa sổ COUNT_BASED thay đổi như thế nào?
5. Một lời gọi trả kết quả thành công sau 5 giây có thể ảnh hưởng đến tỷ lệ nào?
6. Vì sao lời gọi bị từ chối ở trạng thái OPEN cần được theo dõi riêng với lời gọi thất bại?

Khi trả lời được các câu hỏi này, bạn có thể đọc cấu hình sliding window, giải thích sự khác nhau giữa COUNT_BASED và TIME_BASED, và lựa chọn phạm vi thống kê phù hợp với lưu lượng của từng dịch vụ trong Spring Cloud CircuitBreaker.
