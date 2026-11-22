# Những bảo đảm giao dịch không tự cung cấp cho lời gọi từ xa

> **Ngữ cảnh:** Spring Framework — transaction management, phần Tổng quan. Trong bài này, “lời gọi từ xa” là HTTP/REST, gRPC hoặc lời gọi tới một dịch vụ khác qua mạng. Một dịch vụ được gọi có thể dùng Spring và cơ sở dữ liệu riêng, nhưng điều đó không đồng nghĩa hai dịch vụ đang tham gia cùng một giao dịch.

## 1. Vấn đề cốt lõi

`@Transactional` giúp quản lý giao dịch của **những tài nguyên thực sự tham gia vào transaction manager** ở phía ứng dụng hiện tại. Ví dụ, với `JpaTransactionManager`, các thao tác JPA trên nguồn dữ liệu được quản lý có thể cùng commit hoặc rollback. Tuy nhiên, một yêu cầu HTTP gửi sang hệ thống thanh toán, tồn kho hay bên thứ ba **không tự động trở thành một thao tác có thể rollback theo giao dịch JPA đó**.

Xét quy trình tạo đơn:

1. Service A ghi đơn hàng vào database A.
2. Service A gọi HTTP tới service B để thu tiền.
3. Service B ghi giao dịch thu tiền vào database B hoặc gọi nhà cung cấp thanh toán.
4. Service A gặp lỗi và rollback giao dịch database A.

Kết quả có thể là **A không có đơn hàng nhưng B đã ghi nhận thu tiền**. Spring không thể tự thu hồi lời gọi HTTP đã hoàn thành hay rollback cơ sở dữ liệu của B chỉ vì transaction của A bị hủy.

Điểm phân biệt cần giữ rõ:

- **Giao dịch cục bộ (local transaction):** một ranh giới commit/rollback đối với các tài nguyên đã được transaction manager điều phối.
- **Lời gọi từ xa (remote call):** một giao tiếp qua mạng, có kết quả, timeout và trạng thái xử lý riêng ở phía nhận.
- **Nghiệp vụ phân tán:** chuỗi tác động trên nhiều hệ thống; yêu cầu bảo đảm riêng về nhất quán, chống trùng, khôi phục và bù trừ.

`@Transactional` không phải giao thức giao dịch phân tán; hai service đều dùng `@Transactional` cũng không tự tạo ra một giao dịch chung.

## 2. Chính xác Spring bảo đảm điều gì?

Ở mô hình lập trình imperative thường gặp, Spring dùng `PlatformTransactionManager` và ràng buộc transaction vào ngữ cảnh thực thi của luồng hiện tại. Lời gọi đi qua Spring proxy được áp dụng `@Transactional` có thể mở, tham gia, commit hoặc rollback giao dịch theo cấu hình. Các thao tác JDBC/JPA đúng nguồn dữ liệu và transaction manager có thể tham gia giao dịch ấy.

Bảo đảm đó **có điều kiện và phạm vi**:

| Khả năng | Khi nào có thể kỳ vọng? | Giới hạn cần nhớ |
| --- | --- | --- |
| Atomicity của các lệnh database A | Các lệnh tham gia cùng giao dịch database A | Không bao gồm HTTP request hoặc database B |
| Rollback khi code ném lỗi | Transaction còn hoạt động và quy tắc rollback phù hợp | Mặc định rollback với `RuntimeException`/`Error`; checked exception không mặc định gây rollback |
| Isolation/locking | Database hỗ trợ mức isolation, lock và transaction được cấu hình đúng | Không khóa hay cô lập bản ghi ở service B |
| Timeout của transaction | Transaction manager/tài nguyên có thực thi timeout | Không có nghĩa B đã hủy tác động; HTTP timeout là cơ chế khác |
| Propagation như `REQUIRED`, `REQUIRES_NEW` | Trong các lời gọi có transaction management áp dụng tại cùng ứng dụng/ngữ cảnh | Không lan truyền transaction qua REST/gRPC |
| Commit thành công tại A | Database A chấp nhận commit | Không chứng minh B đã làm xong, làm đúng một lần hay sẽ luôn sẵn sàng |

Một chi tiết Spring thường gặp: với proxy mode mặc định, tự gọi phương thức `@Transactional` từ phương thức khác **trong cùng instance** không đi qua proxy, nên annotation ở phương thức được tự gọi có thể không có hiệu lực. Đây là lưu ý bổ sung về **ranh giới local**; kể cả khi proxy hoạt động hoàn hảo, nó vẫn không mở rộng atomicity sang HTTP.

Reactive transaction dùng `ReactiveTransactionManager` và Reactor context thay vì cơ chế gắn vào thread thường thấy. Sự khác biệt kỹ thuật này cũng **không biến một lời gọi network thông thường thành participant của transaction**.

## 3. Ví dụ sai kỳ vọng: “rollback thì thu tiền cũng mất”

Ví dụ sau là **trích đoạn minh họa**, giả định `OrderRepository` và `PaymentClient` đã được định nghĩa trong dự án Spring. Đây không phải một tệp Java độc lập:

```java
@Service
class CheckoutService {
    private final OrderRepository orders;
    private final PaymentClient payments;

    CheckoutService(OrderRepository orders, PaymentClient payments) {
        this.orders = orders;
        this.payments = payments;
    }

    @Transactional
    public void checkout(UUID orderId) {
        orders.markPending(orderId);      // Ghi database A
        payments.charge(orderId);         // HTTP tới service B
        throw new IllegalStateException("Lỗi sau khi thu tiền");
    }
}
```

Nếu `payments.charge(...)` đã được B xử lý thành công, exception cuối phương thức khiến giao dịch database A rollback theo quy tắc mặc định. **Khoản thu tiền tại B vẫn có thể tồn tại.** Việc Spring ném exception và trả HTTP 500 cho người gọi A không có nghĩa B đã rollback.

Đảo thứ tự cũng không tạo atomicity:

- **Gọi B trước commit A:** B có thể hoàn tất, sau đó commit A thất bại.
- **Commit A rồi gọi B:** A có thể hoàn tất, nhưng tiến trình chết, mạng lỗi hoặc B từ chối trước khi tác động ở B diễn ra.
- **Gọi B rồi chờ response trong transaction A:** transaction A giữ kết nối/lock lâu hơn mà vẫn không kiểm soát được transaction tại B.

Không có cách sắp xếp đơn thuần hai thao tác độc lập để loại bỏ mọi khoảng trống giữa chúng.

## 4. Những trường hợp hỏng hóc phải phân biệt

| Tình huống | A biết chắc điều gì? | Điều có thể đã xảy ra tại B | Hướng xử lý |
| --- | --- | --- | --- |
| B trả lỗi trước khi thực thi theo hợp đồng API | Yêu cầu thất bại theo kết quả đã nhận | Không có tác động nếu hợp đồng thực sự bảo đảm điều đó | Phân loại lỗi theo hợp đồng; không tự retry mọi mã lỗi |
| A timeout khi chờ B | A **không biết chắc** kết quả | B chưa nhận, đang xử lý hoặc đã commit | Tra cứu trạng thái bằng ID ổn định; retry an toàn với idempotency key |
| B thực thi xong nhưng response bị mất | A thấy timeout/lỗi mạng | Tác động đã có | Chống trùng và reconcile, tránh gửi lệnh tạo tác động mới |
| A rollback sau khi B trả success | A rollback local | B có thể đã commit | Bù trừ/reconcile theo nghiệp vụ; rollback A không đủ |
| A commit rồi chết trước khi phát yêu cầu | A đã lưu local | B chưa từng nhận | Durable outbox hoặc một cơ chế lưu công việc bền vững |
| B nhận trùng do retry/redelivery | Có thể có nhiều lần giao yêu cầu | Nguy cơ thu tiền/trừ kho nhiều lần | Dedupe phía B bằng khóa duy nhất và transaction của B |
| B hoàn tất chậm hoặc callback đến sai thứ tự | A có trạng thái quan sát tạm thời | Kết quả cũ có thể đến sau kết quả mới | State machine, version/sequence, xử lý idempotent |

**Timeout không tương đương “B chưa làm gì”; retry không tương đương “thử lần đầu”.** Một HTTP 200 hoặc 202 cũng chỉ có ý nghĩa theo **hợp đồng API**: 200 có thể báo thao tác đã hoàn tất, còn 202 thường biểu thị đã nhận để xử lý tiếp. Không tự suy diễn thời điểm commit hay độ bền từ mã status.

Đặc biệt, nếu A gọi API thanh toán rồi nhận `SocketTimeoutException`, không được tự động kết luận thu tiền thất bại và phát lệnh mới với mã giao dịch mới. Cần giữ mã yêu cầu cũ để truy vấn hoặc retry một cách idempotent.

## 5. Vì sao ACID của từng service không đủ cho cả chuỗi?

- **Atomicity:** A và B có thể atomic riêng, nhưng không có atomicity chung nếu không cùng tham gia một giao thức commit phân tán.
- **Consistency:** ràng buộc dữ liệu cục bộ của A không tự kiểm tra hay áp đặt bất biến nghiệp vụ xuyên A–B. Ví dụ “không xác nhận đơn khi chưa thu tiền” cần được biểu diễn bằng trạng thái và quy tắc ứng dụng.
- **Isolation:** isolation của DB A không khiến thao tác đang chạy ở B bị cách ly với người dùng khác. B có thể thấy tác động trước khi A commit.
- **Durability:** sau khi B commit, việc A rollback không xóa dữ liệu bền vững của B.

Các bảo đảm giao dịch là hợp đồng của từng tài nguyên tham gia. Không nên suy ra “toàn bộ quy trình là ACID” từ việc mọi service đều dùng Spring Data/JPA hoặc mỗi handler đều có `@Transactional`.

Ngay cả gọi xa bên trong transaction đang mở cũng làm tăng rủi ro vận hành: giữ DB connection và lock khi chờ mạng, tăng contention, timeout dây chuyền và khả năng hết connection pool. Vì vậy, trong thiết kế thông thường, **tránh giữ local transaction mở trong lúc chờ thao tác mạng dài hoặc không dự đoán được**.

## 6. Chọn bảo đảm theo yêu cầu nghiệp vụ

Trước khi chọn kỹ thuật, mô tả bất biến cần giữ. Chẳng hạn:

- “Mỗi yêu cầu thanh toán hợp lệ chỉ ghi nhận **một lần tác động tài chính**.”
- “Không chuyển đơn sang `PAID` trước khi có bằng chứng thanh toán đã thành công.”
- “Mọi đơn `PENDING_PAYMENT` cuối cùng phải được xử lý hoặc đưa vào trạng thái cần can thiệp.”
- “Hủy đơn đã thu tiền phải tạo hoàn tiền có thể theo dõi, dù hoàn tiền hoàn tất sau.”

Bốn câu trên lần lượt cần **idempotency**, **quy tắc chuyển trạng thái**, **cơ chế retry/giám sát**, và **bù trừ**. Một annotation giao dịch không thực hiện thay tất cả.

Nên tách rõ:

1. **Kết quả của local transaction:** đã commit, rollback hoặc chưa rõ do sự cố.
2. **Trạng thái yêu cầu từ xa:** chưa gửi, đã gửi, đã được chấp nhận, đã thực hiện, thất bại cuối cùng hoặc chưa xác định.
3. **Trạng thái nghiệp vụ tổng:** `PENDING`, `PROCESSING`, `COMPLETED`, `COMPENSATING`, `FAILED`... tùy miền nghiệp vụ.

Client timeout nên được đưa về trạng thái **UNKNOWN/PENDING_RECONCILIATION** khi chưa có bằng chứng thất bại cuối cùng; không mặc định đánh dấu “đã thất bại”.

## 7. Transactional Outbox: lưu ý định gửi trong cùng giao dịch local

**Vấn đề dual write:** lưu đơn hàng vào database A và đồng thời publish event/gọi B là hai thao tác trên hai hệ thống. Nếu A commit nhưng tiến trình chết trước khi publish, sự kiện bị mất; nếu publish trước commit mà A rollback, B nhận sự kiện cho một trạng thái không tồn tại.

**Transactional Outbox** thay đổi điểm lưu trách nhiệm:

```text
Một transaction local tại A:
    INSERT/UPDATE orders
    INSERT outbox_event (event_id, aggregate_id, type, payload, status)
    COMMIT

Sau commit (tiến trình độc lập):
    Poll/CDC lấy outbox_event đã commit
    Gửi event hoặc yêu cầu tới B
    Khi có xác nhận hợp lệ, đánh dấu đã chuyển
    Lỗi tạm thời -> retry với cùng event_id
```

Đơn hàng và bản ghi outbox nằm **cùng database, cùng transaction** nên hoặc cả hai được commit, hoặc cả hai rollback. Relay có thể chết sau khi B xử lý nhưng trước khi đánh dấu outbox đã gửi; vì vậy **outbox thường mang lại khả năng gửi ít nhất một lần (at-least-once), không bảo đảm B xử lý đúng một lần**. Phía B vẫn phải chống trùng.

Ví dụ trích đoạn **Spring Boot 3.x / Java 17+**, chỉ thể hiện nơi đặt ranh giới transaction; giả định các entity và Spring Data repository đã được khai báo trong ứng dụng:

```java
@Service
class OrderApplicationService {
    private final OrderJpaRepository orders;
    private final OutboxJpaRepository outbox;

    OrderApplicationService(OrderJpaRepository orders,
                            OutboxJpaRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID createOrder(UUID customerId, long amountMinorUnits) {
        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        orders.save(new OrderEntity(
                orderId, customerId, amountMinorUnits, "PENDING_PAYMENT"));
        outbox.save(new OutboxEntity(
                eventId, orderId, "PaymentRequested", amountMinorUnits));

        return orderId; // Cả hai bản ghi cùng commit hoặc cùng rollback
    }
}
```

`OrderEntity`, `OutboxEntity` và hai repository trong ví dụ là kiểu ứng dụng tự định nghĩa, **không phải API sẵn có của Spring**. Kiểu số tiền nên dùng đơn vị nhỏ nhất của tiền tệ (ví dụ đồng xu) hoặc `BigDecimal` với scale và quy tắc làm tròn rõ ràng, thay vì `double`.

Một outbox thực tế nên lưu `event_id` duy nhất, `aggregate_id`, `event_type`/schema version, payload, thời điểm tạo, trạng thái gửi, số lần thử, thời điểm retry tiếp theo và thông tin lỗi. Relay cần chiến lược claim/lease an toàn khi chạy nhiều instance; tránh hai worker cùng chọn một hàng chưa khóa rồi phát không kiểm soát. Với database hỗ trợ, có thể dùng `FOR UPDATE SKIP LOCKED`, hoặc CDC/connector đáng tin cậy. Cần cơ chế xử lý poison message/dead-letter và cảnh báo event tồn quá lâu.

### Về thứ tự và thay đổi trạng thái

Nếu cùng một đơn có nhiều event, dùng version/sequence tăng theo aggregate để phía nhận nhận ra event cũ hoặc sai thứ tự. Đừng giả định nhiều consumer, nhiều partition và nhiều lần retry luôn giữ nguyên thứ tự. Lưu ý thêm: outbox giải quyết **atomicity giữa dữ liệu A và ý định gửi**; nó không tự biến B thành một phần của local transaction.

## 8. Idempotency và Inbox: chống tác động trùng ở phía nhận

**Idempotency** nghĩa là áp dụng cùng một yêu cầu nghiệp vụ nhiều lần vẫn cho **cùng hiệu ứng nghiệp vụ** như một lần. Nó đặc biệt quan trọng khi A không biết B đã xử lý hay chưa.

Một hợp đồng HTTP có thể quy định:

```http
POST /payments
Idempotency-Key: 7cb0c613-76a1-491d-a747-5ae194b4f52f
Content-Type: application/json

{"orderId":"9fd3e0e4-9fb7-467b-8396-1eeab0b98f14","amountMinorUnits":125000}
```

Ở B, khóa `Idempotency-Key` gắn với **một thao tác logic**, không tạo khóa mới cho mỗi lần retry. B cần lưu key và kết quả bền vững; đặt unique constraint, chẳng hạn trên `(client_id, idempotency_key)`. Nếu request lặp có **cùng key nhưng payload khác**, trả lỗi xung đột theo hợp đồng. Nếu cùng key và payload hợp lệ đã hoàn tất, trả kết quả đã lưu, không thu tiền lần nữa.

Nguyên tắc cài đặt:

- Dedupe/check điều kiện và tác động lên database B phải phối hợp **nguyên tử** bằng transaction và unique constraint; chỉ “SELECT xem key tồn tại” rồi “INSERT” không đủ khi hai request đến đồng thời.
- Lưu trạng thái `IN_PROGRESS`/`SUCCEEDED`/`FAILED_FINAL` khi cần. Request thứ hai gặp `IN_PROGRESS` phải nhận kết quả đang xử lý, chờ/poll hoặc retry sau; không âm thầm thực hiện lần nữa.
- Chọn thời hạn giữ key dài hơn cửa sổ retry/redelivery có thể xảy ra, theo hợp đồng hệ thống. Expire quá sớm có thể làm yêu cầu cũ trở thành yêu cầu mới.
- Nếu B lại gọi dịch vụ thứ ba, B cũng phải truyền một khóa idempotency phù hợp xuống bước tạo side effect tiếp theo, nếu API đó hỗ trợ. Unique key chỉ trong database B **không thể tự ngăn** duplicate ở nhà cung cấp ngoài khi B crash giữa gọi nhà cung cấp và ghi kết quả.
- Đối với consumer nhận event, mô hình **Inbox/Processed Messages** lưu `(consumer_id, event_id)` duy nhất trong **cùng transaction với cập nhật nghiệp vụ**. Redelivery sẽ không áp dụng hiệu ứng lần hai.

```sql
-- PostgreSQL, minh họa constraint cốt lõi:
CREATE TABLE processed_messages (
    consumer_id text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_id, event_id)
);
```

Sau khi claim event thành công trong transaction B, cập nhật dữ liệu nghiệp vụ rồi commit; nếu transaction rollback, cả marker processed và thay đổi nghiệp vụ cũng rollback. Khi xảy ra xung đột unique, xác định đó là event đã xử lý, không áp dụng side effect nữa. Với HTTP request bên ngoài có side effect không tham gia transaction B, cần thêm trạng thái durable và reconciliation riêng.

**“Exactly once” là một tuyên bố phải gắn với phạm vi.** Một broker có thể có ngữ nghĩa xử lý đúng một lần **trong phạm vi nó kiểm soát**, nhưng không tự bảo đảm rằng một yêu cầu thu tiền sang hệ thống ngoài được thực hiện đúng một lần. Mục tiêu thực tế thường là **at-least-once delivery + xử lý idempotent + đối soát**, tạo hiệu ứng nghiệp vụ tương đương một lần.

## 9. Saga và compensation khi nghiệp vụ trải nhiều service

Với quy trình gồm nhiều bước có transaction riêng, **Saga** mô tả các local transaction và các hành động bù trừ có ý nghĩa nghiệp vụ:

```text
Tạo đơn PENDING tại A
    -> Giữ hàng tại Inventory
    -> Thu tiền tại Payment
    -> Xác nhận đơn tại A

Nếu thu tiền thất bại cuối cùng:
    -> Hủy giữ hàng
    -> Đánh dấu đơn PAYMENT_FAILED

Nếu đã thu tiền nhưng bước sau thất bại:
    -> Yêu cầu hoàn tiền (một giao dịch mới)
    -> Theo dõi hoàn tiền đến trạng thái kết thúc
```

Có thể điều phối bằng **orchestration** (một coordinator giữ state và ra lệnh) hoặc **choreography** (các service phản ứng theo event). Cả hai cần ID tương quan, event/command idempotent, timeout, retry, trạng thái bền vững, và đường xử lý khi bù trừ cũng thất bại.

**Compensation không phải database rollback xuyên hệ thống.** Hoàn tiền có thể tạo một giao dịch riêng, mất phí, bị từ chối hoặc hoàn tất muộn; người khác có thể quan sát trạng thái trung gian. Saga cũng **không cung cấp isolation toàn cục**: phải quản lý hành vi concurrent, giữ chỗ, phiên bản và tính hợp lệ của chuyển trạng thái.

**TCC (Try–Confirm–Cancel)** phù hợp khi các service hỗ trợ tài nguyên đặt giữ/confirm/cancel với hợp đồng rõ. TCC yêu cầu thiết kế API và giữ tài nguyên có thời hạn, không phải tính năng tự sinh ra từ `@Transactional`.

## 10. Khi nào dùng distributed transaction / XA / 2PC?

Một giao dịch phân tán với **two-phase commit (2PC)** có thể điều phối nhiều tài nguyên hỗ trợ giao thức, thường thông qua XA/JTA và `JtaTransactionManager` trong môi trường tương thích. Nhưng cần **mọi participant liên quan** có khả năng enlist/prepare/commit theo cùng coordinator. Một API HTTP thông thường hoặc dịch vụ thanh toán bên thứ ba **không tự nhiên là XA resource**.

2PC bổ sung độ phức tạp, chi phí phối hợp và khả năng participant giữ tài nguyên trong thời gian chờ. Nó cũng không giải quyết vô điều kiện mọi loại sự cố, chính sách bù trừ hoặc hành động bên ngoài. Chỉ cân nhắc khi yêu cầu atomicity rất chặt, tất cả tài nguyên hỗ trợ thật sự và đội ngũ có khả năng vận hành recovery của coordinator. Với microservices giao tiếp HTTP, outbox, idempotency, state machine và Saga thường khả thi hơn.

Đừng hiểu cấu hình `@Transactional(transactionManager = "...")` hay `Propagation.REQUIRES_NEW` là đã có 2PC. `REQUIRES_NEW` chỉ tạo **một transaction local độc lập** trong phạm vi transaction manager tương ứng.

## 11. `@TransactionalEventListener(AFTER_COMMIT)` giúp gì, thiếu gì?

Spring cung cấp listener có thể chạy theo pha giao dịch:

```java
@Component
class OrderNotificationListener {
    private final PaymentClient payments;

    OrderNotificationListener(PaymentClient payments) {
        this.payments = payments;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onOrderPlaced(OrderPlaced event) {
        payments.requestPayment(event.orderId());
    }
}
```

Đây cũng là **trích đoạn tích hợp**, giả định `PaymentClient` và record `OrderPlaced` được ứng dụng định nghĩa.

Listener chạy sau commit giúp **tránh gửi yêu cầu cho transaction A đã rollback**. Nhưng có một khoảng trống: nếu tiến trình chết sau commit A và trước/khi listener gửi, event trong bộ nhớ có thể mất, và không có durable retry mặc định. Vì vậy, listener **không thay thế transactional outbox** khi yêu cầu “đã commit thì cuối cùng phải gửi”.

Ngoài ra, tại các pha `AFTER_COMMIT`/`AFTER_COMPLETION`, tài nguyên transaction có thể vẫn truy cập được nhưng transaction cũ đã kết thúc; cập nhật DB mới không được giả định tự commit. Khi cần ghi DB trong callback sau commit, hãy dùng một transaction mới thực sự (ví dụ method đi qua proxy với `REQUIRES_NEW`), hoặc đặt trách nhiệm ghi bền vững trong transaction ban đầu như outbox.

## 12. Thiết kế đồng bộ khi bắt buộc phải gọi trực tiếp

Không phải quy trình nào cũng cần queue. Nếu phải gọi B đồng bộ để đưa ra quyết định tức thì:

1. Xác định B có hợp đồng **idempotent request** và endpoint tra cứu trạng thái theo business request ID không. Nếu không, cần thiết kế cơ chế đối soát trước khi bật retry tự động cho side effect.
2. Giữ lời gọi HTTP ngoài transaction DB A nếu có thể; chỉ mở transaction ngắn để ghi kết quả đã xác minh. Không nói rằng cách tách này tạo atomicity xuyên hệ thống.
3. Đặt connect timeout và response timeout hợp lý, retry có giới hạn với exponential backoff và jitter, chỉ cho lỗi có thể thử lại. Xem xét rate limit, circuit breaker và bulkhead để ngăn lỗi dây chuyền.
4. Đưa kết quả chưa rõ vào `PENDING_RECONCILIATION`; truy vấn trạng thái tại B bằng request ID, xử lý callback có xác thực khi có, và cung cấp đường xử lý thủ công nếu vẫn không xác minh được.
5. Định nghĩa thứ tự chuyển trạng thái hợp lệ bằng version/optimistic locking hoặc điều kiện update. Callback cũ không được ghi đè kết quả mới.
6. Chỉ trả “hoàn tất” khi điều kiện nghiệp vụ thực sự đạt. Khi cần xử lý bất đồng bộ, trả mã theo hợp đồng (ví dụ HTTP 202 với URL/status ID) và cung cấp cách theo dõi.

Một quy trình bảo đảm tốt **không nhầm lẫn khả năng gửi thành công với tác động nghiệp vụ thành công**.

## 13. Kịch bản kiểm thử bắt buộc

| Kịch bản cố ý gây lỗi | Quan sát cần xác nhận |
| --- | --- |
| A rollback sau khi B đã xử lý | Tác động B không biến mất; hệ thống phát hiện và bù trừ/đối soát đúng |
| B xử lý thành công nhưng bỏ response | A retry bằng **cùng idempotency key**; B không lặp side effect |
| Dừng tiến trình A ngay sau commit order + outbox | Relay sau restart vẫn lấy được event |
| Dừng relay sau khi B nhận nhưng trước khi mark sent | Event có thể gửi lại; B dedupe an toàn |
| Hai worker A/relay cùng xử lý một event | Claim/lease/unique constraint ngăn cập nhật sai hoặc tác động trùng |
| Hai request đồng thời cùng idempotency key | Unique constraint phía B xác định một thao tác logic duy nhất |
| B lỗi lâu, sau đó hồi phục | Backoff/retry, trạng thái pending, cảnh báo và hoàn thành cuối cùng |
| Event/callback sai thứ tự, trễ hoặc gửi trùng | State machine/version không đi lùi trạng thái |
| Compensation thất bại | Vẫn có trạng thái và lịch retry/escalation, không “mất dấu” yêu cầu |
| Transaction gặp checked exception | Quy tắc rollback được cấu hình/chứng minh theo kỳ vọng |

Trong tích hợp thực, dùng test database và mock HTTP server hoặc môi trường mô phỏng service B; chèn lỗi **tại ranh giới giữa commit, gửi, nhận và xác nhận**. Integration test chỉ kiểm tra happy path không phát hiện các khoảng trống quan trọng. Với thanh toán thật, tránh tạo giao dịch tài chính thật khi kiểm thử lỗi; dùng sandbox hoặc adapter giả lập.

Các chỉ số nên giám sát: tuổi event outbox chưa gửi, số lần retry, số message dead-letter, số command ở trạng thái chưa xác định, tỷ lệ trùng idempotency key, số saga đang bù trừ và độ trễ từ commit local đến hoàn tất nghiệp vụ. Cần correlation ID/request ID xuyên log và trace, nhưng **correlation ID để truy vết khác với idempotency key để ngăn tác động trùng** nếu không được thiết kế thống nhất.

## 14. Những hiểu lầm thường gặp

| Nhận định | Sự thật |
| --- | --- |
| “Có `@Transactional` nên mọi bước trong method đều rollback.” | Chỉ các tài nguyên tham gia transaction được điều phối; HTTP side effect không tự rollback. |
| “A và B đều dùng Spring nên cùng giao dịch.” | Mỗi service có transaction manager/transaction riêng, trừ khi có thiết kế giao thức distributed transaction thực sự. |
| “HTTP timeout nghĩa là B chưa thu tiền.” | Kết quả **không xác định**; B có thể đã hoàn tất nhưng response bị mất. |
| “Retry chắc chắn sẽ hoàn tất an toàn.” | Retry có thể tạo side effect trùng nếu B không idempotent. |
| “Gửi event trong `AFTER_COMMIT` là không thể mất event.” | Process có thể chết trước khi gửi; outbox cần cho phát hành bền vững. |
| “Outbox bảo đảm exactly-once toàn hệ thống.” | Outbox bảo đảm lưu ý định gửi atomic với dữ liệu A; relay có thể gửi trùng. |
| “Saga rollback giống ACID.” | Saga dùng các transaction và compensation riêng, có trạng thái trung gian, có thể cần can thiệp. |
| “`REQUIRES_NEW` làm transaction lan qua service B.” | Nó là propagation tại local Spring transaction manager, không phải giao thức mạng. |

## 15. Checklist áp dụng cho một lời gọi từ xa có side effect

- [ ] Vẽ rõ ranh giới database/transaction manager và những service không tham gia giao dịch.
- [ ] Viết bất biến nghiệp vụ: điều gì tuyệt đối không được xảy ra, điều gì được phép nhất quán sau.
- [ ] Gán request/event ID duy nhất **và giữ nguyên qua retry**; xác định key/payload/version.
- [ ] Định nghĩa kết quả success, terminal failure và unknown; có endpoint tra cứu hoặc reconciliation.
- [ ] Bảo vệ side effect bằng unique constraint và logic xử lý trùng ngay tại phía thực thi.
- [ ] Nếu cần phát hành chắc chắn sau commit A, lưu outbox trong cùng local transaction.
- [ ] Có relay/retry/claim/monitoring và thiết kế cho duplicate, out-of-order, poison message.
- [ ] Với chuỗi nhiều bước, biểu diễn Saga/TCC bằng state machine và phương án compensation idempotent.
- [ ] Giữ transaction DB ngắn; không giữ lock trong thời gian dài chờ mạng nếu có thể.
- [ ] Test timeout sau success, crash ở các điểm chuyển giao, concurrent retry và bù trừ lỗi.

**Kết luận:** `@Transactional` quản lý tính toàn vẹn của transaction mà Spring thực sự kiểm soát. Tính đúng đắn của một chuỗi xuyên dịch vụ đến từ **hợp đồng API, idempotency, ghi ý định bền vững, state machine, bù trừ và đối soát**. “Giao dịch cục bộ thành công” và “nghiệp vụ phân tán hoàn thành” là hai mốc khác nhau, cần được mô hình hóa và quan sát riêng.

## Tài liệu đối chiếu

- Spring Framework — [Declarative Transaction Management / Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- Spring Framework — [Declarative transaction semantics](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Spring Framework — [Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- AWS Prescriptive Guidance — [Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).
- Microservices.io — [Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html), [Idempotent consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html), [Saga](https://microservices.io/patterns/data/saga.html).
