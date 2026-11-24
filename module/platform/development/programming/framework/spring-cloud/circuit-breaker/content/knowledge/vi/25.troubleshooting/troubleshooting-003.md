# Mạch mở quá sớm do nhiều thao tác dùng chung thống kê

## Mục tiêu của bài học

Một circuit breaker được thiết kế để đánh giá sức khỏe của một lời gọi được bảo vệ. Nếu nhiều thao tác nghiệp vụ khác nhau cùng dùng một breaker instance, kết quả của chúng sẽ đi vào cùng sliding window. Một thao tác thường xuyên lỗi hoặc chậm có thể làm tỷ lệ lỗi tổng hợp vượt ngưỡng, khiến breaker OPEN và chặn cả thao tác khác vốn vẫn hoạt động tốt.

Trong Spring Cloud CircuitBreaker với Resilience4j, cần phân biệt rõ **breaker id** và **groupName**. Dùng chung id có thể khiến nhiều lời gọi chia sẻ trạng thái và thống kê. Dùng chung groupName nhằm chọn chính sách cấu hình chung; bản thân groupName không hợp nhất trạng thái của các breaker có id khác nhau.

Sau bài học, bạn có thể:

- Nhận biết dấu hiệu nhiều thao tác đang dùng chung breaker instance.
- Giải thích vì sao lỗi của một thao tác làm breaker chặn thao tác khác.
- Phân biệt id của breaker với groupName dùng để chọn cấu hình.
- Chọn ranh giới breaker dựa trên phụ thuộc, semantics lỗi và SLO của thao tác.
- Cấu hình nhiều breaker riêng nhưng dùng chung một policy Resilience4j.
- Kiểm tra sliding window, minimumNumberOfCalls và exception classification.
- Chẩn đoán tên breaker thực tế qua metric, event và log.
- Tránh chia breaker quá nhỏ đến mức không đủ mẫu để đánh giá.

## 1. Triệu chứng: một thao tác lỗi làm thao tác khác bị chặn

Giả sử order-service gọi inventory-service qua hai thao tác:

- `readAvailability(sku)` đọc tồn kho. Đây là lời gọi nhanh và thường thành công.
- `reserveStock(sku, quantity)` giữ hàng. Thao tác này có thể bị từ chối do hết hàng hoặc xung đột nghiệp vụ.

Nếu cả hai thao tác cùng dùng breaker tên `inventory`, các kết quả có thể đi vào cùng một sliding window. Ví dụ trong 10 lời gọi gần nhất có 5 lần reserve bị lỗi và 5 lần đọc tồn kho thành công. Với `minimumNumberOfCalls: 10` và `failureRateThreshold: 50`, breaker có thể mở khi vừa đủ 10 mẫu.

Sau khi breaker chuyển OPEN, lời gọi đọc tồn kho tiếp theo cũng có thể bị từ chối, dù chính thao tác đọc vẫn khỏe mạnh. Người vận hành nhìn thấy lỗi ở endpoint đọc và nghĩ rằng inventory-service đã ngừng hoạt động, trong khi nguyên nhân là các lỗi từ thao tác reserve đã làm tăng failure rate của breaker dùng chung.

Luồng minh họa:

    readAvailability  ---- success ----+
    reserveStock      ---- error ------+
    readAvailability  ---- success ----+--> breaker: inventory
    reserveStock      ---- error ------+       shared window
    reserveStock      ---- error ------+
    readAvailability  ---- success ----+
    reserveStock      ---- error ------+
    reserveStock      ---- error ------+
    readAvailability  ---- success ----+
    reserveStock      ---- error ------+
                                                |
                                                v
                                      failure rate reaches threshold
                                                |
                                                v
                                         breaker OPEN
                                                |
                          +---------------------+------------------+
                          |                                        |
                   readAvailability                         reserveStock
                    rejected                                  rejected

Dấu hiệu thường gặp:

- Breaker OPEN dù một số endpoint vẫn có tỷ lệ thành công tốt.
- Lỗi hoặc slow call tập trung ở một thao tác, nhưng metric chỉ có một breaker name.
- Số lời gọi bị từ chối tăng trên nhiều phương thức cùng dùng breaker.
- Fallback của thao tác khỏe mạnh cũng chạy vì breaker đã mở trước khi Supplier được thực thi.
- Đội vận hành không thể xác định thao tác nào đóng góp nhiều lỗi nhất từ metric breaker hiện tại.

## 2. Vì sao nhiều thao tác dùng chung thống kê?

Circuit breaker giữ trạng thái và sliding window theo instance. Nếu ứng dụng lấy cùng một breaker instance cho nhiều thao tác, các lần gọi đó cùng cập nhật dữ liệu thống kê.

Một số nguyên nhân phổ biến:

1. **Tái sử dụng cùng id:** nhiều gateway hoặc phương thức gọi `factory.create("inventory")`.
2. **Tên breaker được chuẩn hóa quá rộng:** một resolver tùy chỉnh bỏ tên phương thức và chỉ trả về service ID.
3. **Cùng một wrapper được dùng cho nhiều loại thao tác:** một helper cố định breaker name dù Supplier gọi endpoint khác nhau.
4. **Cấu hình Feign dùng tên chung:** nhiều method được ánh xạ về cùng tên breaker do quy tắc đặt tên hoặc resolver của ứng dụng.
5. **Breaker bao quanh cả quy trình nhiều bước:** lỗi từ nhiều phụ thuộc hoặc xử lý nghiệp vụ cùng được ghi nhận vào một breaker.

Ví dụ dễ gây chia sẻ thống kê:

    public InventoryResponse read(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.read(sku),
            error -> InventoryResponse.unknown(sku)
        );
    }

    public ReservationResponse reserve(String sku, int quantity) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.reserve(sku, quantity),
            error -> ReservationResponse.pending(sku)
        );
    }

Cả hai phương thức dùng cùng id `inventory`. Trong Resilience4j, tên instance là khóa nhận diện breaker. Việc gọi factory với cùng id thường lấy cùng breaker instance được quản lý trong factory/registry, nên trạng thái và sliding window được chia sẻ.

Không phải cứ cùng một service ID hoặc cùng một groupName là các breaker tự động dùng chung thống kê. Hãy kiểm tra id thực tế mà factory sử dụng.

## 3. Phân biệt id và groupName

Với Spring Cloud CircuitBreaker, hai tham số có vai trò khác nhau:

- **id** định danh breaker instance. Đây là tên gắn với trạng thái, sliding window và metric của breaker.
- **groupName** chọn cấu hình nhóm dùng cho breaker khi implementation hỗ trợ phân giải cấu hình theo nhóm.

Ví dụ:

    CircuitBreaker readBreaker =
        circuitBreakerFactory.create("inventory-read", "inventory");

    CircuitBreaker reserveBreaker =
        circuitBreakerFactory.create("inventory-reserve", "inventory");

Hai breaker có id khác nhau nên có trạng thái và thống kê riêng. Chúng cùng dùng groupName `inventory` để nhận chính sách cấu hình chung.

Có thể hình dung:

    groupName: inventory
       |
       +-- id: inventory-read
       |      state: CLOSED / OPEN / HALF_OPEN
       |      sliding window: riêng
       |
       +-- id: inventory-reserve
              state: CLOSED / OPEN / HALF_OPEN
              sliding window: riêng

Bảng phân biệt:

| Cách dùng | Trạng thái và thống kê | Cấu hình |
| --- | --- | --- |
| Cùng id, cùng groupName | Có thể dùng chung breaker instance và window. | Cùng ngữ cảnh cấu hình. |
| Khác id, cùng groupName | Riêng cho từng breaker. | Có thể dùng chung chính sách nhóm. |
| Khác id, khác groupName | Riêng cho từng breaker. | Có thể dùng chính sách khác nhau. |

Điểm cần nhớ: groupName không phải một nhãn để gom nhiều breaker thành một thống kê. Nếu mục tiêu là tách ảnh hưởng giữa read và reserve, hãy cấp id khác nhau. Nếu mục tiêu là dùng chung sliding window, hãy chủ động dùng cùng id và chấp nhận rằng lỗi của một thao tác ảnh hưởng đến thao tác còn lại.

## 4. Chọn ranh giới breaker theo hành vi vận hành

Không nhất thiết mỗi endpoint HTTP phải có một breaker riêng. Ranh giới nên phản ánh các thao tác có đặc tính vận hành tương tự.

Hãy xem xét các yếu tố:

- **Phụ thuộc được gọi:** hai thao tác có cùng phụ thuộc từ xa hay gọi hai hệ thống khác nhau?
- **Semantics lỗi:** lỗi là dấu hiệu phụ thuộc không khả dụng hay là kết quả nghiệp vụ bình thường?
- **SLO và deadline:** hai thao tác có cùng ngân sách thời gian và ngưỡng chậm không?
- **Tải và tần suất:** một thao tác có lưu lượng lớn, thao tác kia có lưu lượng thấp không?
- **Hậu quả khi OPEN:** có hợp lý khi chặn cả hai thao tác cùng lúc không?
- **Fallback:** hai thao tác có cùng khả năng trả dữ liệu dự phòng an toàn không?

Ví dụ:

| Thao tác | Đặc tính | Ranh giới gợi ý |
| --- | --- | --- |
| Đọc tồn kho | Đọc nhanh, có thể dùng cache với metadata freshness. | `inventory-read` |
| Giữ hàng | Thao tác ghi, cần idempotency và trạng thái kết quả không chắc chắn khi timeout. | `inventory-reserve` |
| Xuất báo cáo tồn kho | Có thể chạy lâu và trả stream lớn. | `inventory-export` |
| Đọc giá | Phụ thuộc pricing-service, có SLO và fallback riêng. | `pricing-read` |

Nếu read và reserve có cùng failure mode, cùng deadline và cần bảo vệ inventory-service như một năng lực chung, có thể cố ý dùng chung breaker. Tuy nhiên, nếu lỗi nghiệp vụ của reserve không phản ánh sức khỏe dịch vụ, việc gộp thống kê thường làm sai tín hiệu. Cần xác định rõ lỗi nào được ghi nhận trước khi quyết định chia sẻ.

## 5. Phân loại exception trước khi điều chỉnh ngưỡng

Breaker có thể mở sớm vì các lỗi nghiệp vụ bị ghi nhận như lỗi phụ thuộc. Ví dụ, reserve trả về HTTP 409 khi tồn kho không đủ. Nếu client chuyển status này thành exception và breaker ghi nhận mọi exception, những lần hết hàng có thể làm tăng failure rate dù inventory-service vẫn hoạt động đúng.

Cần phân biệt:

- **Lỗi hạ tầng/phụ thuộc:** connection refused, timeout, HTTP 5xx hoặc lỗi giao tiếp có thể phản ánh dịch vụ không khỏe.
- **Kết quả nghiệp vụ:** hết hàng, xung đột phiên bản, yêu cầu không hợp lệ hoặc trạng thái không cho phép.
- **Lỗi lập trình:** NullPointerException, mapping sai hoặc vi phạm invariant trong ứng dụng caller.

Resilience4j cho phép cấu hình exception được ghi nhận hoặc bỏ qua:

    resilience4j:
      circuitbreaker:
        instances:
          inventory-reserve:
            recordExceptions:
              - java.io.IOException
              - java.util.concurrent.TimeoutException
            ignoreExceptions:
              - com.example.inventory.OutOfStockException
              - com.example.inventory.ReservationConflictException

Tên exception trong ví dụ là lớp do ứng dụng định nghĩa và cần điều chỉnh theo HTTP client thực tế. Nếu status 409 được chuyển thành một exception riêng, có thể phân loại nó là kết quả nghiệp vụ và bỏ qua đối với failure rate. Đừng bỏ qua mọi HTTP 4xx một cách máy móc; 429 có thể biểu thị quá tải hoặc giới hạn tốc độ và cần chính sách riêng.

Nếu một thao tác thường trả lỗi nghiệp vụ nhưng một thao tác khác dùng chung breaker, hãy xác minh lỗi nghiệp vụ có bị tính vào failure rate hay không. Việc tách breaker không thay thế phân loại exception; hai việc giải quyết hai nguyên nhân khác nhau.

## 6. Cấu hình nhiều breaker dùng chung policy

Có thể tạo policy chung trong `configs`, sau đó khai báo từng breaker trong `instances` với id riêng:

    resilience4j:
      circuitbreaker:
        configs:
          inventory-policy:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            slowCallDurationThreshold: 800ms
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

        instances:
          inventory-read:
            baseConfig: inventory-policy

          inventory-reserve:
            baseConfig: inventory-policy
            minimumNumberOfCalls: 8

          inventory-export:
            baseConfig: inventory-policy
            slowCallDurationThreshold: 5s
            slowCallRateThreshold: 70

Cấu hình này tạo ba instance breaker độc lập. Cả ba kế thừa chính sách `inventory-policy`, nhưng mỗi instance có sliding window và trạng thái riêng. inventory-reserve thay đổi minimumNumberOfCalls; inventory-export thay đổi ngưỡng lời gọi chậm.

Nếu dùng Spring Cloud CircuitBreaker factory với groupName, có thể truyền groupName tương ứng khi tạo breaker:

    CircuitBreaker readBreaker =
        circuitBreakerFactory.create("inventory-read", "inventory");

    CircuitBreaker reserveBreaker =
        circuitBreakerFactory.create("inventory-reserve", "inventory");

Kiểm tra quy tắc phân giải cấu hình của phiên bản Spring Cloud CircuitBreaker đang dùng và xác nhận cấu hình hiệu lực qua log/metric. Không giả định rằng khai báo một block YAML sẽ tự động làm cho mọi factory hoặc customizer chọn đúng nhóm nếu id và groupName không khớp.

## 7. Sửa code bằng id riêng cho từng thao tác

Một cách sửa trực tiếp là thay id dùng chung bằng id có ý nghĩa vận hành:

    @Service
    public class InventoryGateway {

        private final InventoryClient inventoryClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public InventoryGateway(
                InventoryClient inventoryClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse read(String sku) {
            return circuitBreakerFactory
                .create("inventory-read", "inventory")
                .run(
                    () -> inventoryClient.read(sku),
                    error -> InventoryResponse.unknown(sku)
                );
        }

        public ReservationResponse reserve(String sku, int quantity) {
            return circuitBreakerFactory
                .create("inventory-reserve", "inventory")
                .run(
                    () -> inventoryClient.reserve(sku, quantity),
                    error -> ReservationResponse.pending(sku)
                );
        }
    }

Trong ví dụ, read và reserve dùng cùng groupName nhưng id khác nhau. Nếu reserve bị lỗi liên tục, breaker inventory-reserve có thể OPEN trong khi inventory-read vẫn CLOSED và tiếp tục phục vụ truy vấn.

Fallback cũng khác nhau vì hai thao tác có semantics riêng:

- Đọc tồn kho không thành công có thể trả UNKNOWN hoặc dữ liệu cache hợp lệ.
- Giữ hàng timeout có thể trả PENDING/UNKNOWN và yêu cầu tra cứu trạng thái bằng operation ID; không nên khẳng định lệnh ghi thất bại nếu server có thể đã thực hiện.

Các kiểu InventoryResponse và ReservationResponse là hợp đồng do ứng dụng định nghĩa. Hãy bảo đảm tầng gọi phân biệt được dữ liệu chính và dữ liệu fallback.

## 8. Tránh chia breaker quá nhỏ

Tách breaker giúp cô lập thống kê, nhưng mỗi breaker cần đủ số mẫu để đánh giá. Nếu tạo breaker riêng cho từng URL, SKU, user hoặc request, lưu lượng sẽ bị chia thành nhiều nhóm nhỏ và nhiều breaker không bao giờ đạt minimumNumberOfCalls.

Không nên tạo id động:

    // Không nên: số lượng breaker có thể tăng theo dữ liệu request.
    circuitBreakerFactory.create("inventory-" + sku);

Thay vào đó, dùng tên ổn định theo thao tác:

    circuitBreakerFactory.create("inventory-read");
    circuitBreakerFactory.create("inventory-reserve");

Một breaker quá ít mẫu có thể vẫn CLOSED dù tỷ lệ lỗi của vài lần gọi là 100%, vì chưa đạt minimumNumberOfCalls. Khi chia nhỏ, cần xem lại:

- Lưu lượng bình thường của từng thao tác.
- minimumNumberOfCalls và slidingWindowSize.
- Thời gian cần để thu thập đủ mẫu.
- Số breaker instance được tạo trong mỗi JVM.
- Số chuỗi metric và event tăng thêm.
- Khả năng cấu hình và theo dõi từng breaker.

Chỉ tách khi khác biệt về lỗi, SLO, timeout, fallback hoặc hậu quả khi OPEN đủ lớn để biện minh cho một thống kê độc lập. Nếu các thao tác có cùng hành vi và cùng cần ngắt khi phụ thuộc chung suy giảm, dùng chung breaker có thể là lựa chọn hợp lý.

## 9. Kiểm tra tên breaker thực tế

Trong ứng dụng Spring Cloud CircuitBreaker, tên breaker thực tế phụ thuộc cách gọi factory hoặc quy tắc đặt tên của tích hợp client. Với OpenFeign, tên có thể được tạo từ client và method; một CircuitBreakerNameResolver tùy chỉnh có thể thay đổi cách đặt tên. Các chi tiết này có thể thay đổi theo phiên bản.

Khi chẩn đoán, đừng chỉ suy đoán tên từ service ID. Hãy kiểm tra:

- Tên breaker xuất hiện trong log khi tạo hoặc chuyển trạng thái.
- Tag `name` trong metric Resilience4j.
- Danh sách instance từ endpoint Actuator nếu tích hợp đó được bật.
- Event state transition và event call not permitted.
- Tên id truyền vào `factory.create(id)` hoặc `factory.create(id, groupName)`.
- Resolver tùy chỉnh của Feign nếu ứng dụng sử dụng.

Ví dụ truy vấn metric Prometheus có thể lọc theo tag name:

    resilience4j_circuitbreaker_state{name="inventory-read",state="open"}

Tên metric được Prometheus chuẩn hóa từ Micrometer và có thể khác theo registry/version. Truy vấn minh họa cho thấy cần lọc theo breaker name và state, thay vì gộp mọi metric circuit breaker vào một chuỗi duy nhất.

Nếu dashboard chỉ có `name=inventory` trong khi ứng dụng có read, reserve và export, có thể các thao tác đã được ánh xạ về một breaker name. Xác minh resolver và lời gọi factory trước khi đổi ngưỡng.

## 10. Đọc sliding window để xác định thao tác nào làm breaker mở

Khi breaker mở, hãy xem các mẫu đã đóng góp vào cửa sổ:

- Số lời gọi được ghi nhận.
- Số lỗi và loại exception.
- Số slow call.
- Failure rate và slow call rate.
- Thời điểm các lời gọi lỗi xuất hiện.
- Thao tác nghiệp vụ nào phát ra lời gọi đó.

Với COUNT_BASED, slidingWindowSize là số kết quả gần nhất được giữ để tính tỷ lệ. Với TIME_BASED, cửa sổ biểu diễn khoảng thời gian và kết quả được tổng hợp theo bucket. minimumNumberOfCalls xác định số mẫu tối thiểu trước khi đánh giá tỷ lệ.

Ví dụ cấu hình:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 10
            minimumNumberOfCalls: 10
            failureRateThreshold: 50

Khi có 10 mẫu và ít nhất 5 lỗi được ghi nhận, failure rate đạt 50% và breaker có thể mở. Nếu 5 lỗi đều đến từ reserve còn 5 lời gọi read thành công, breaker chung sẽ mở cho cả hai thao tác.

Nếu đã tách id, cần kiểm tra riêng từng window. inventory-reserve có thể đạt tỷ lệ lỗi cao và OPEN; inventory-read có thể vẫn CLOSED. Tuy nhiên, nếu reserve chỉ có 3 mẫu trong khi minimumNumberOfCalls là 10, breaker riêng của reserve chưa đủ dữ liệu để mở. Đừng hạ minimumNumberOfCalls chỉ để làm dashboard phản ứng nhanh mà chưa xem lưu lượng và độ ổn định thống kê.

## 11. Fallback không nên làm sai thống kê

Vị trí xử lý lỗi ảnh hưởng đến kết quả mà breaker quan sát. Nếu ứng dụng bắt exception bên trong Supplier và trả về một giá trị mặc định, breaker có thể ghi nhận lời gọi là thành công.

Ví dụ không phù hợp:

    return breaker.run(() -> {
        try {
            return inventoryClient.reserve(sku, quantity);
        } catch (RuntimeException error) {
            return ReservationResponse.pending(sku);
        }
    });

Supplier đã chuyển lỗi thành một kết quả bình thường trước khi breaker nhận được tín hiệu lỗi. Failure rate có thể thấp hơn thực tế.

Hãy để lỗi thoát khỏi Supplier và dùng fallback ở lớp bảo vệ:

    return breaker.run(
        () -> inventoryClient.reserve(sku, quantity),
        error -> ReservationResponse.pending(sku)
    );

Với reactive operator, đặt fallback sau CircuitBreakerOperator để breaker nhận được lỗi trước khi lỗi được chuyển thành publisher thành công. Nếu fallback được cấu hình qua Spring Cloud CircuitBreaker factory, dùng overload run có fallback và kiểm tra hành vi của implementation.

Cần phân biệt lỗi nghiệp vụ được chủ động chuyển thành kết quả với lỗi hạ tầng. Nếu hết hàng là kết quả nghiệp vụ bình thường, client có thể ánh xạ HTTP 409 thành một response domain mà không tính là lỗi circuit breaker. Nhưng timeout hoặc connection failure vẫn phải được ghi nhận theo policy. Không dùng fallback chung để che mọi exception.

## 12. Theo dõi ảnh hưởng giữa các thao tác

Sau khi tách breaker, dashboard cần hiển thị riêng từng id:

| Breaker | State | Calls | Failure rate | Slow call rate | Not permitted |
| --- | --- | --- | --- | --- | --- |
| inventory-read | CLOSED | 240 | 2% | 4% | 0 |
| inventory-reserve | OPEN | 80 | 62% | 18% | 35 |
| inventory-export | CLOSED | 12 | 0% | 25% | 0 |

Các con số chỉ minh họa. Chúng cho thấy reserve có thể OPEN trong khi read và export vẫn được phép chạy. Nếu muốn xem sức khỏe tổng thể của inventory-service, hãy tạo dashboard tổng hợp riêng từ metric của các breaker và metric phía server; không gộp trạng thái thành một breaker duy nhất nếu điều đó làm mất khả năng cô lập.

Các metric cần quan sát:

- State gauge theo breaker name.
- Calls theo outcome và thời lượng.
- Failure rate, slow call rate.
- Not-permitted calls.
- State transition events.
- Fallback count theo thao tác.
- HTTP latency và status theo endpoint hoặc instance ở phía phụ thuộc.

Trong môi trường nhiều pod, mỗi JVM thường có trạng thái breaker riêng. Dashboard cần giữ tag pod/instance để phân biệt một pod OPEN với toàn bộ service OPEN. Tránh tag metric bằng SKU, request ID hoặc exception message vì cardinality có thể tăng không giới hạn.

## 13. Bài thực hành: tái hiện và sửa breaker mở quá sớm

Tạo InventoryGateway với hai thao tác read và reserve. Bắt đầu bằng cấu hình dùng chung id `inventory` để quan sát lỗi, sau đó tách thành hai breaker.

**Phần A — Tái hiện**

1. Dùng `factory.create("inventory")` cho cả read và reserve.
2. Cấu hình COUNT_BASED window size 10, minimumNumberOfCalls 10 và failureRateThreshold 50.
3. Cho 5 lời gọi reserve phát sinh lỗi được ghi nhận.
4. Cho 5 lời gọi read thành công.
5. Quan sát breaker chuyển OPEN khi đủ 10 mẫu.
6. Gọi read lần nữa và xác nhận Supplier không chạy vì breaker đã OPEN.

**Phần B — Sửa ranh giới**

1. Đổi read thành `factory.create("inventory-read", "inventory")`.
2. Đổi reserve thành `factory.create("inventory-reserve", "inventory")`.
3. Giữ chính sách cấu hình nhóm inventory giống nhau.
4. Lặp lại 5 lỗi reserve và 5 lần read thành công.
5. Xác nhận inventory-reserve có thể OPEN trong khi inventory-read vẫn CLOSED.
6. Kiểm tra metric và event có hai breaker name riêng.

**Phần C — Kiểm tra policy và số mẫu**

1. Cho reserve trả lỗi nghiệp vụ hết hàng và cấu hình exception đó là ignored nếu hợp đồng domain xác định đây không phải lỗi sức khỏe.
2. Cho reserve timeout để xác nhận lỗi phụ thuộc vẫn được ghi nhận.
3. Giảm lưu lượng reserve và quan sát ảnh hưởng của minimumNumberOfCalls.
4. Thử một breaker id động theo SKU trong môi trường test để thấy số instance/metric tăng; sau đó thay bằng id ổn định.
5. Xác nhận fallback không nuốt lỗi timeout trước khi breaker ghi nhận.

Khi hoàn thành, bạn cần giải thích được cùng id có thể chia sẻ trạng thái và sliding window, cùng groupName chỉ nhằm chia sẻ chính sách cấu hình, và vì sao tách breaker phải cân bằng giữa cô lập lỗi với đủ số mẫu. Hãy dùng metric và event để chứng minh thao tác nào làm breaker mở, thay vì chỉ tăng failureRateThreshold để che triệu chứng.

## Tài liệu tham khảo

- Spring Cloud CircuitBreaker — Resilience4J configuration: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
- Resilience4j — CircuitBreaker and sliding window: https://resilience4j.readme.io/docs/circuitbreaker
- Spring Cloud OpenFeign — CircuitBreaker support and naming: https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html

