# Tổng quan JTA, XA và lựa chọn bù trừ nghiệp vụ

## Mục tiêu

Một nghiệp vụ có thể cập nhật nhiều tài nguyên: hai cơ sở dữ liệu, database và message broker, hoặc nhiều dịch vụ độc lập. Transaction cục bộ của một database chỉ bảo vệ các thao tác thuộc transaction đó. Khi cần phối hợp nhiều tài nguyên, kiến trúc phải chọn cách bảo đảm tính nhất quán phù hợp.

Hai hướng thường gặp là:

- **JTA/XA:** phối hợp transaction phân tán giữa các tài nguyên có hỗ trợ XA, thường dùng two-phase commit để cùng commit hoặc rollback.
- **Bù trừ nghiệp vụ (compensation/Saga):** chia quy trình thành nhiều transaction cục bộ; nếu bước sau thất bại, thực hiện hành động nghiệp vụ bù cho các bước đã hoàn tất.

Sau bài này, bạn có thể:

- Phân biệt transaction cục bộ, JTA và giao thức XA.
- Mô tả cách transaction coordinator thực hiện two-phase commit.
- Xác định điều kiện để JPA, JDBC và JMS cùng tham gia transaction phân tán.
- Hiểu trạng thái in-doubt, recovery và heuristic outcome.
- Nhận biết giới hạn của XA với HTTP API và dịch vụ độc lập.
- Thiết kế Saga với bước thuận, bước bù và trạng thái tiến trình.
- Kết hợp transactional outbox/inbox với retry và idempotency.
- Chọn XA hay compensation dựa trên yêu cầu nhất quán, thời gian và khả năng vận hành.

## 1. Vì sao một transaction cục bộ chưa đủ?

Giả sử một thao tác tạo đơn hàng cần:

1. Ghi đơn hàng vào database Order.
2. Trừ tồn kho trong database Inventory.
3. Gửi message để hệ thống giao hàng nhận việc.

Nếu cả ba thao tác dùng cùng một transaction manager và cùng một tài nguyên database, một transaction cục bộ có thể bảo vệ chúng. Nhưng nếu mỗi database có connection riêng hoặc message broker là một tài nguyên độc lập, transaction của một database không tự động điều khiển các tài nguyên còn lại.

Một tình huống lỗi:

- Order database đã commit đơn hàng.
- Inventory database bị lỗi trước khi trừ tồn kho.
- Message chưa được gửi.

Hệ thống có đơn hàng nhưng chưa giữ được hàng. Nếu thử gửi lại toàn bộ request mà không có thiết kế chống trùng, đơn hàng có thể bị tạo hai lần.

Cần phân biệt ba phạm vi:

| Phạm vi | Đơn vị bảo đảm | Ví dụ |
|---|---|---|
| Transaction cục bộ | Một resource manager hoặc một database transaction | Một JpaTransactionManager quản lý một EntityManagerFactory |
| Transaction phân tán JTA/XA | Nhiều XA resource được coordinator điều phối | Hai XA database và một XA JMS resource |
| Quy trình Saga | Nhiều transaction cục bộ nối tiếp hoặc theo sự kiện | Tạo đơn, giữ hàng, thanh toán, giao hàng và bù trừ khi cần |

Không nên mặc định nhiều phương thức có @Transactional đồng nghĩa nhiều database được commit nguyên tử. Cần xác định transaction manager thực sự đang được dùng và những resource nào đã được enlist vào transaction đó.

## 2. JTA và XA là gì?

**JTA (Jakarta Transactions)** là API và mô hình quản lý transaction phân tán trong hệ sinh thái Java. Ứng dụng bắt đầu, commit hoặc rollback transaction thông qua transaction manager. JPA, JDBC và JMS có thể tham gia nếu được cấu hình với tài nguyên tương thích.

**XA** là giao thức chuẩn để transaction manager phối hợp nhiều resource manager. Resource manager có thể là database hoặc message provider hỗ trợ XA. XA mô tả cách coordinator yêu cầu từng tài nguyên chuẩn bị commit và sau đó commit hoặc rollback theo quyết định chung.

Có thể hiểu quan hệ như sau:

- JTA là API và mô hình điều phối transaction phía Java.
- XA là giao thức phối hợp giữa transaction manager và các XA resource.
- Transaction coordinator là thành phần giữ trạng thái quyết định chung và điều phối các resource.
- Resource manager là thành phần quản lý dữ liệu thực tế, chẳng hạn database hoặc JMS provider.

Spring cung cấp lớp tích hợp như **JtaTransactionManager** để tham gia transaction do JTA coordinator quản lý. Spring không tự biến hai transaction cục bộ độc lập thành một transaction XA chỉ bằng cách đặt nhiều annotation @Transactional.

Một JTA coordinator có thể được cung cấp bởi application server hoặc một triển khai transaction manager độc lập, chẳng hạn Narayana hoặc Atomikos. Cách cấu hình phụ thuộc phiên bản Spring Boot, provider JPA, driver database, JMS provider và nền tảng triển khai.

## 3. Two-phase commit hoạt động như thế nào?

XA thường sử dụng **two-phase commit (2PC)**. Coordinator cần nhận được cam kết rằng các resource đã chuẩn bị có thể commit trước khi phát quyết định commit chung.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant TM as JTA Coordinator
    participant DB1 as Order XA DB
    participant DB2 as Inventory XA DB
    App->>TM: Begin transaction
    App->>DB1: Update order
    App->>DB2: Reserve stock
    App->>TM: Commit
    TM->>DB1: Prepare
    TM->>DB2: Prepare
    DB1-->>TM: Vote YES
    DB2-->>TM: Vote YES
    TM->>DB1: Commit
    TM->>DB2: Commit
    TM-->>App: Commit completed
~~~

Hai pha chính:

**Pha 1 — Prepare**

1. Ứng dụng yêu cầu commit.
2. Coordinator gửi prepare đến từng XA resource đã enlist.
3. Mỗi resource kiểm tra khả năng commit và lưu trạng thái cần thiết vào log bền vững.
4. Resource trả lời YES nếu đã sẵn sàng commit, hoặc NO nếu không thể commit.

Resource đã trả lời YES phải giữ trạng thái cần thiết để có thể hoàn tất quyết định sau đó. Khóa và tài nguyên có thể được giữ trong lúc chờ quyết định cuối.

**Pha 2 — Commit hoặc rollback**

- Nếu mọi resource đều vote YES, coordinator ghi quyết định commit bền vững rồi gửi commit đến từng resource.
- Nếu có resource vote NO hoặc một điều kiện buộc rollback, coordinator quyết định rollback và thông báo cho các resource.
- Resource thực hiện quyết định và giải phóng trạng thái transaction.

Mục tiêu là không để một resource tự commit khi các resource khác đã rollback. Coordinator cần lưu log để có thể phục hồi quyết định sau sự cố.

Một số hệ thống có tối ưu hóa one-phase commit khi chỉ có một XA resource tham gia. Khi có nhiều resource, quy trình prepare/commit là phần quan trọng tạo nên phối hợp phân tán.

## 4. Điều kiện để JPA tham gia JTA/XA

JPA có thể chạy với transaction cục bộ hoặc JTA. Để entity manager tham gia JTA transaction, persistence unit và EntityManagerFactory phải được cấu hình theo transaction type phù hợp, thường là JTA. DataSource phải là XA-aware và được transaction manager quản lý.

Các điều kiện thường cần:

- JTA coordinator đang hoạt động và được cấu hình trong ứng dụng.
- DataSource dùng XA driver/provider và được đăng ký với coordinator.
- EntityManagerFactory dùng JTA transaction integration.
- Repository hoặc EntityManager được kết nối đúng persistence unit và JTA transaction manager.
- Các resource tham gia cùng transaction đều hỗ trợ XA và được enlist đúng cách.
- Transaction timeout, recovery log và thông tin định danh resource được cấu hình bền vững.

Ở tầng Spring, service có thể chỉ rõ transaction manager:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPlacementService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderPlacementService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional(transactionManager = "jtaTransactionManager")
    public void placeOrder(Order order, Long productId, int quantity) {
        orderRepository.save(order);
        inventoryRepository.reserve(productId, quantity);
    }
}
~~~

Đoạn code minh họa chỉ có ý nghĩa khi cả hai repository được cấu hình trên các persistence unit/XA DataSource đã enlist vào cùng JTA coordinator. Nếu repository thứ hai dùng một JpaTransactionManager cục bộ hoặc một DataSource không XA, annotation trên phương thức không tự làm cho cập nhật đó thuộc cùng transaction phân tán.

Tên bean jtaTransactionManager trong ví dụ là tên cấu hình của ứng dụng. Với Spring Boot, cách tạo bean, khai báo XA DataSource và liên kết provider phụ thuộc phiên bản và triển khai JTA đang dùng. Không sao chép cấu hình từ một provider sang provider khác mà không kiểm tra tài liệu tương ứng.

## 5. JDBC, JMS và các resource khác

JTA/XA không chỉ dành cho JPA. Một transaction có thể phối hợp database và message broker nếu cả hai đều cung cấp XA resource tương thích.

Ví dụ về thành phần tham gia:

| Tài nguyên | Thành phần cần có |
|---|---|
| JPA/Hibernate | JTA EntityManagerFactory và XA DataSource |
| JDBC thuần | XADataSource và XAConnection/XAResource phù hợp |
| JMS | XA-capable ConnectionFactory/Session do provider cung cấp |
| Database thứ hai | Driver và XA DataSource được enlist vào cùng coordinator |

Ví dụ nghiệp vụ ghi đơn hàng và gửi message có thể dùng cùng một JTA transaction nếu database và JMS provider đều được cấu hình XA:

~~~java
@Transactional(transactionManager = "jtaTransactionManager")
public void createOrderAndNotify(Order order) {
    orderRepository.save(order);
    jmsTemplate.convertAndSend("orders.created", order.getId());
}
~~~

Đây là minh họa về luồng sử dụng. Để message thực sự tham gia cùng transaction, JMS connection factory, session và cấu hình JmsTemplate phải hỗ trợ và sử dụng XA transaction do coordinator quản lý. Một JMS template dùng local session transaction hoặc gửi message ngoài transaction sẽ không tự động được phối hợp.

Không phải mọi broker hoặc mọi connection factory đều hỗ trợ XA trong mọi cấu hình. Cần kiểm tra loại connection factory và cách provider enlist resource. Nếu không có XA, hãy cân nhắc outbox thay vì giả định message sẽ rollback cùng database.

## 6. Recovery và trạng thái in-doubt

Coordinator hoặc resource có thể gặp sự cố giữa hai pha. Ví dụ, cả hai database đã prepare và vote YES, nhưng coordinator dừng trước khi gửi quyết định commit. Các resource có thể giữ transaction ở trạng thái **in-doubt** vì chưa biết quyết định cuối cùng.

Recovery cần:

1. Ghi transaction log và resource identity vào nơi lưu bền vững.
2. Khởi động lại coordinator với cùng thông tin recovery.
3. Kết nối lại resource manager đã tham gia transaction.
4. Đọc trạng thái transaction còn dang dở.
5. Hoàn tất commit hoặc rollback theo quyết định đã ghi trong log.

Không được xóa log hoặc đổi định danh XA resource một cách tùy tiện khi còn transaction chưa phục hồi. Nếu coordinator không nhận diện được resource cũ, giao dịch có thể bị treo và cần điều tra vận hành.

Một **heuristic outcome** xảy ra khi resource tự đưa ra quyết định commit hoặc rollback khác với quyết định coordinator, thường do timeout hoặc can thiệp quản trị. Trường hợp này có thể phá vỡ atomicity dự kiến và cần xử lý thủ công, đối soát dữ liệu hoặc bù trừ nghiệp vụ.

Vì vậy, XA cần được vận hành như một hạ tầng có trạng thái bền vững, có log, monitoring, recovery procedure và runbook. Chỉ cấu hình annotation mà không cấu hình recovery là chưa đủ cho production.

## 7. Chi phí và giới hạn của XA

2PC cung cấp phối hợp commit mạnh giữa các XA resource, nhưng phải trả chi phí:

- Nhiều lượt trao đổi mạng giữa coordinator và resource.
- Resource có thể giữ khóa hoặc trạng thái prepared trong thời gian chờ quyết định.
- Transaction lâu làm giảm khả năng xử lý đồng thời và tăng nguy cơ timeout.
- Coordinator và recovery log trở thành thành phần hạ tầng cần vận hành ổn định.
- Tất cả resource tham gia phải hỗ trợ XA và được cấu hình đúng.
- Sự cố network hoặc coordinator có thể khiến transaction in-doubt cần recovery.

XA phù hợp hơn với các transaction ngắn, tài nguyên XA tương thích và yêu cầu atomic commit rõ ràng. Nó thường không phù hợp với quy trình kéo dài nhiều phút, chờ con người, gọi API bên ngoài hoặc nhiều bước cần retry độc lập.

**XA không biến một HTTP request đến dịch vụ khác thành XA resource.** REST API thông thường không tham gia prepare/commit theo XA. Nếu một service đã thực hiện side effect rồi service khác lỗi, coordinator không thể tự rollback side effect đó. Với giao tiếp service-to-service, Saga và compensation thường phù hợp hơn.

## 8. Compensation và Saga là gì?

**Compensation** là một thao tác nghiệp vụ nhằm bù lại tác động của một bước đã commit. Nó không phải rollback database transaction cũ. Transaction cũ đã commit và lịch sử đó vẫn tồn tại; compensation tạo một thay đổi mới để đưa hệ thống về trạng thái nghiệp vụ được chấp nhận.

**Saga** là chuỗi các transaction cục bộ. Mỗi bước commit độc lập; nếu bước sau thất bại, hệ thống quyết định retry, tiếp tục theo nhánh khác hoặc chạy các hành động bù cho bước đã hoàn tất.

Ví dụ đặt hàng:

| Bước thuận | Kết quả | Hành động bù có thể có |
|---|---|---|
| Tạo đơn ở trạng thái PENDING | Đơn được tạo | Hủy đơn hoặc chuyển CANCELLED |
| Giữ hàng | Tồn kho được giữ | Giải phóng hàng đã giữ |
| Thu tiền | Thanh toán thành công | Hoàn tiền |
| Tạo vận đơn | Vận chuyển được yêu cầu | Hủy vận đơn nếu nhà vận chuyển cho phép |

Compensation mang ý nghĩa nghiệp vụ. Hoàn tiền không xóa sự kiện thanh toán đã xảy ra; nó tạo một giao dịch hoàn tiền. Giải phóng hàng không làm như chưa từng có reservation; nó ghi nhận reservation đã bị hủy.

Không phải mọi thao tác đều có thể bù hoàn toàn. Email đã gửi không thể thu hồi khỏi hộp thư. Hàng đã giao có thể cần quy trình trả hàng. Vì vậy, thiết kế Saga phải mô tả rõ trạng thái cuối có thể đạt được và cách xử lý khi compensation cũng thất bại.

## 9. Thiết kế Saga theo kiểu orchestration

Trong **orchestration**, một coordinator nghiệp vụ điều khiển thứ tự bước, lưu trạng thái tiến trình và quyết định bước tiếp theo. Cách này dễ quan sát luồng khi quy trình có nhiều nhánh và compensation.

Một trạng thái Saga có thể gồm:

- saga_id: định danh duy nhất của quy trình.
- business_key: khóa nghiệp vụ, ví dụ order_id.
- current_step: bước đang thực hiện.
- status: RUNNING, COMPLETED, COMPENSATING, COMPENSATED hoặc FAILED.
- attempt_count: số lần thử của bước hiện tại.
- last_error: lỗi gần nhất.
- created_at, updated_at: thời điểm phục vụ vận hành.

Luồng orchestration:

~~~text
START
  |
  v
Create pending order
  |
  v
Reserve inventory
  |
  v
Charge payment
  |
  v
Create shipment
  |
  v
Mark order confirmed
  |
  v
COMPLETED

Nếu Charge payment thất bại vĩnh viễn:
  Release inventory
  Cancel pending order
  COMPENSATED
~~~

Mỗi bước phải cập nhật trạng thái Saga cùng kết quả transaction cục bộ hoặc lưu event/outbox tương ứng. Không chỉ giữ tiến độ trong bộ nhớ của coordinator vì tiến trình có thể dừng bất kỳ lúc nào.

Ví dụ service xử lý reservation:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryStep {

    private final InventoryRepository inventoryRepository;
    private final SagaEventRepository sagaEventRepository;

    public InventoryStep(
            InventoryRepository inventoryRepository,
            SagaEventRepository sagaEventRepository) {
        this.inventoryRepository = inventoryRepository;
        this.sagaEventRepository = sagaEventRepository;
    }

    @Transactional
    public void reserve(String sagaId, Long productId, int quantity) {
        inventoryRepository.reserve(productId, quantity);
        sagaEventRepository.record(
            sagaId,
            "INVENTORY_RESERVED",
            productId.toString()
        );
    }
}
~~~

Ví dụ giả định event/state được ghi trong cùng database và cùng transaction với thao tác reservation. Nếu cần gửi message sang service khác, hãy ghi thêm outbox record trong transaction đó; worker sẽ publish sau commit. Bản ghi trạng thái bước phải có khóa duy nhất hoặc version để tránh hai worker xử lý cùng bước đồng thời.

## 10. Thiết kế compensation an toàn

Mỗi bước thuận cần xác định trước:

- Điều kiện bước được coi là thành công.
- Kết quả cần lưu để có thể bù sau này.
- Compensation tương ứng và dữ liệu cần thiết để thực hiện.
- Compensation có thể retry hay không.
- Điều kiện nào khiến compensation không còn hợp lệ.
- Cách xử lý khi compensation thất bại hoặc chỉ hoàn thành một phần.

Ví dụ bước giữ hàng lưu reservation_id. Compensation phải giải phóng đúng reservation đó, không cộng tồn kho một cách vô điều kiện vì có thể giải phóng nhầm một lần giữ hàng khác.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationCompensation {

    private final ReservationRepository reservationRepository;

    public ReservationCompensation(
            ReservationRepository reservationRepository) {
        this.reservationRepository = reservationRepository;
    }

    @Transactional
    public void releaseReservation(String reservationId) {
        Reservation reservation = reservationRepository
            .findById(reservationId)
            .orElseThrow();

        if (reservation.getStatus() == ReservationStatus.RELEASED) {
            return;
        }

        if (reservation.getStatus() != ReservationStatus.RESERVED) {
            throw new IllegalStateException(
                "Reservation cannot be released from current state");
        }

        reservation.release();
    }
}
~~~

Đoạn code minh họa hành động bù idempotent theo trạng thái: gọi lại khi đã RELEASED không tạo thêm một lần cộng tồn kho. Cần bảo đảm cập nhật trạng thái và thay đổi số lượng được commit trong cùng transaction. Nếu hai lệnh release chạy đồng thời, cần thêm optimistic locking, pessimistic locking hoặc câu lệnh cập nhật có điều kiện để tránh giải phóng hai lần.

Khi bù nhiều bước, thường thực hiện theo thứ tự ngược với các bước thuận đã hoàn tất. Ví dụ nếu đã giữ hàng rồi thu tiền, khi tạo vận đơn thất bại thì có thể hoàn tiền trước rồi giải phóng hàng, tùy quy tắc nghiệp vụ. Không có một thứ tự chung cho mọi quy trình; hãy xác định theo phụ thuộc và rủi ro thực tế.

## 11. Orchestration và choreography

Trong **choreography**, mỗi service phát event sau transaction cục bộ và service khác phản ứng với event đó. Không có một coordinator trung tâm điều khiển từng bước.

| Tiêu chí | Orchestration | Choreography |
|---|---|---|
| Điều khiển | Một orchestrator quyết định bước tiếp theo | Các service phản ứng với event |
| Theo dõi tiến trình | Trạng thái Saga tập trung | Phải tổng hợp event và trạng thái từ nhiều service |
| Phụ thuộc | Service tham gia phụ thuộc contract với orchestrator | Service phụ thuộc event contract của nhau |
| Phù hợp | Luồng nhiều nhánh, compensation phức tạp | Luồng tương đối đơn giản, event-driven |
| Rủi ro | Orchestrator trở thành thành phần quan trọng cần HA | Luồng nghiệp vụ phân tán khó lần theo và dễ tạo phụ thuộc ngầm |

Choreography có thể giảm sự phụ thuộc vào một service điều phối, nhưng không làm biến mất nhu cầu lưu trạng thái, retry, idempotency và quan sát. Nếu một event kích hoạt nhiều consumer, mỗi consumer cần xác định trách nhiệm và trạng thái xử lý riêng.

## 12. Transactional outbox và inbox trong Saga

Khi service cập nhật database rồi publish event bằng hai thao tác riêng, có hai tình huống lỗi:

- Database commit nhưng publish thất bại: service khác không nhận được event.
- Publish thành công nhưng database rollback: service khác nhận event cho thay đổi chưa commit.

Transactional outbox giải quyết khoảng trống này bằng cách ghi dữ liệu nghiệp vụ và outbox record trong cùng local transaction. Worker đọc outbox và publish message sau commit.

Một outbox record thường có:

| Trường | Ý nghĩa |
|---|---|
| event_id | ID duy nhất của message |
| aggregate_id | ID đơn hàng hoặc đối tượng nghiệp vụ |
| event_type | Loại event |
| payload | Dữ liệu consumer cần |
| created_at | Thời điểm tạo |
| published_at | Thời điểm broker xác nhận |
| attempt_count | Số lần thử publish |

Publish có thể lặp nếu worker dừng sau khi broker nhận message nhưng trước khi outbox được đánh dấu. Vì vậy consumer nên dùng **inbox** hoặc bảng processed_message với unique constraint trên event_id. Consumer ghi nhận event đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng transaction.

Mô hình thường gặp là **at-least-once delivery cộng xử lý idempotent**. Không nên gọi đó là exactly-once end-to-end. Broker có thể giao message trùng; inbox đảm bảo cùng event không áp dụng thay đổi nghiệp vụ lần thứ hai.

## 13. Retry, timeout và dead-letter trong Saga

Không phải mọi lỗi đều cần compensation ngay.

- Lỗi tạm thời như timeout mạng hoặc service quá tải: retry bước hiện tại với backoff và giới hạn.
- Lỗi nghiệp vụ vĩnh viễn như không đủ hàng: chuyển sang nhánh compensation.
- Không rõ kết quả do timeout: truy vấn trạng thái bằng business key hoặc idempotency key trước khi quyết định chạy lại.
- Compensation thất bại: giữ Saga ở trạng thái COMPENSATING, lưu lỗi và retry hoặc chuyển dead-letter để vận hành xử lý.

Một request timeout không chứng minh service đích chưa thực hiện thao tác. Có thể service đã commit nhưng response bị mất trên đường về. Nếu gọi lại với một ID mới, nghiệp vụ có thể bị thực hiện hai lần. Mỗi bước cần một idempotency key ổn định, chẳng hạn saga_id cộng tên bước, để service đích nhận diện request lặp.

Không retry vô hạn. Lưu attempt count, next_retry_at, error code và trạng thái để worker có thể tiếp tục sau restart. Dùng exponential backoff và jitter để tránh tạo đợt retry đồng loạt. Sau ngưỡng đã định, chuyển sang dead-letter hoặc yêu cầu can thiệp nghiệp vụ.

## 14. So sánh JTA/XA với Saga/compensation

| Tiêu chí | JTA/XA | Saga/compensation |
|---|---|---|
| Cơ chế | Two-phase commit giữa XA resource | Chuỗi transaction cục bộ và hành động bù |
| Tính nhất quán | Atomic commit giữa resource tham gia | Eventual consistency trong suốt quy trình |
| Thời gian | Phù hợp transaction ngắn | Phù hợp quy trình dài và nhiều bước |
| Hỗ trợ resource | Mọi resource phải hỗ trợ XA và enlist đúng | Mỗi service dùng transaction cục bộ |
| Khóa và tải | Có thể giữ trạng thái prepared/lock trong 2PC | Không giữ một transaction phân tán xuyên suốt |
| Lỗi sau một bước commit | Coordinator recovery quyết định commit/rollback | Chạy retry, nhánh thay thế hoặc compensation |
| Side effect HTTP | Không tự phối hợp được | Có thể mô hình hóa bước và compensation |
| Độ phức tạp | Hạ tầng coordinator, XA driver, recovery | Thiết kế trạng thái, retry, idempotency và compensation |

Một lựa chọn thứ ba thường hữu ích là **transactional outbox** khi cần đồng bộ một database với message broker nhưng không muốn hoặc không thể dùng XA. Outbox không làm nhiều service commit nguyên tử; nó bảo đảm thay đổi database và yêu cầu phát event được lưu cùng transaction, sau đó message được giao theo mô hình có thể lặp.

## 15. Cách chọn giải pháp

Hãy bắt đầu từ yêu cầu nghiệp vụ và khả năng kỹ thuật của các tài nguyên.

**Chọn transaction cục bộ** khi mọi thay đổi nằm trong một database transaction và không cần phối hợp tài nguyên khác.

**Cân nhắc JTA/XA** khi:

- Có nhiều resource manager thực sự hỗ trợ XA.
- Nghiệp vụ cần atomic commit giữa các resource.
- Transaction ngắn và không phải chờ người dùng hoặc API ngoài.
- Đội vận hành có thể quản lý coordinator, log, timeout và recovery.
- Driver, provider và cấu hình JTA đã được kiểm chứng trên môi trường triển khai.

**Cân nhắc Saga/compensation** khi:

- Quy trình trải qua nhiều service hoặc nhiều database độc lập.
- Các bước có thể commit cục bộ và chấp nhận trạng thái trung gian.
- Có hành động nghiệp vụ bù rõ ràng.
- Quy trình kéo dài, cần retry độc lập và có thể cần can thiệp thủ công.
- Giao tiếp sử dụng HTTP hoặc message broker không hỗ trợ XA.

Nếu không thể bù một side effect, hãy thiết kế bước đó ở cuối quy trình hoặc thêm bước xác nhận/ủy quyền trước khi thực hiện. Ví dụ gửi email thông báo chỉ sau khi đơn đã được xác nhận, thay vì gửi ở đầu Saga.

## 16. Kiểm thử và vận hành

Với JTA/XA, cần kiểm thử nhiều tình huống hơn một test commit thành công:

1. Cả hai resource prepare và commit thành công.
2. Một resource vote NO, xác nhận các resource còn lại rollback.
3. Coordinator dừng sau prepare; khởi động lại và xác nhận recovery hoàn tất quyết định.
4. Một resource mất kết nối trong pha commit; kiểm tra trạng thái in-doubt và recovery.
5. Timeout, deadlock hoặc heuristic outcome được ghi log và cảnh báo đúng.
6. Xác nhận mỗi repository thực sự tham gia cùng JTA transaction, không chạy trên local transaction riêng.

Với Saga, cần kiểm thử:

1. Tất cả bước thuận thành công.
2. Bước tạm thời thất bại rồi retry thành công.
3. Bước nghiệp vụ thất bại vĩnh viễn và compensation chạy theo đúng thứ tự.
4. Compensation được gọi lặp nhưng chỉ tạo hiệu ứng nghiệp vụ một lần.
5. Response timeout sau khi service đích đã commit; request lặp không tạo dữ liệu trùng.
6. Event outbox được publish lại; consumer inbox bỏ qua event đã xử lý.
7. Worker dừng giữa các bước; Saga tiếp tục từ trạng thái bền vững sau restart.
8. Compensation thất bại; trạng thái được giữ để retry hoặc vận hành can thiệp.

Monitoring nên có transaction ID hoặc saga_id xuyên suốt log, metric thời gian từng bước, số lần retry, số transaction in-doubt, số compensation đang chờ và số message dead-letter. Tránh chỉ ghi một log tổng quát khiến không thể xác định resource hoặc bước nào thất bại.

## 17. Checklist thiết kế

- Xác định tất cả resource được cập nhật và transaction manager đang quản lý chúng.
- Kiểm tra resource có hỗ trợ XA thật sự hay chỉ có local transaction.
- Nếu dùng JTA, cấu hình JTA persistence unit, XA DataSource, XA JMS resource và recovery log.
- Xác định timeout và quy trình xử lý in-doubt/heuristic outcome.
- Giữ XA transaction ngắn, tránh gọi HTTP hoặc chờ tác vụ bên ngoài trong transaction.
- Nếu dùng Saga, xác định trạng thái bền vững, business key, bước thuận và bước bù.
- Thiết kế compensation theo ý nghĩa nghiệp vụ; không giả định nó là rollback vật lý.
- Dùng outbox/inbox, idempotency key và unique constraint để chống message/request trùng.
- Retry có giới hạn, backoff, jitter và dead-letter.
- Kiểm thử sự cố giữa các bước, restart, duplicate delivery và compensation failure.
- Theo dõi trạng thái tiến trình và chuẩn bị runbook cho thao tác cần can thiệp thủ công.

JTA/XA và Saga giải quyết hai dạng bài toán khác nhau. XA phối hợp quyết định commit giữa các resource có hỗ trợ giao thức; Saga quản lý một quy trình nghiệp vụ qua nhiều transaction độc lập bằng retry và compensation. Chọn giải pháp dựa trên yêu cầu atomicity, loại tài nguyên, thời gian xử lý và khả năng vận hành khi một bước thất bại.