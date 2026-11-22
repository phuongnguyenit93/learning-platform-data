# Kiểm thử giao dịch, xung đột đồng thời và yêu cầu lặp

Trong Domain-Driven Design (DDD), một use case thường tải aggregate, kiểm tra quyền, thực hiện hành vi miền, lưu trạng thái và ghi nhận sự kiện. Khi chỉ có một request chạy tuần tự, luồng này có vẻ đơn giản. Nhưng trong môi trường thật, hai request có thể cùng đọc một trạng thái, nhiều transaction có thể cùng cập nhật một aggregate, client có thể gửi lại command sau timeout, và message broker có thể giao một event nhiều lần.

Các tình huống đó có thể làm phát sinh lỗi mà unit test thông thường không phát hiện: mất cập nhật, giữ hàng vượt tồn kho, thu tiền hai lần, tạo reservation trùng hoặc ghi aggregate mà không có outbox event. Vì vậy, cần kiểm thử ở nhiều cấp: domain behavior, application orchestration, transaction thật, concurrency control và khả năng xử lý yêu cầu lặp.

Bài học này tập trung vào **kiểm thử giao dịch, xung đột đồng thời và yêu cầu lặp**. Mục tiêu là thiết kế test có thể chứng minh trạng thái cuối cùng đúng khi transaction commit/rollback, khi nhiều request tranh chấp và khi cùng một ý định được gửi nhiều lần. Test phải kiểm tra kết quả có ý nghĩa nghiệp vụ, không chỉ xác nhận một method đã được gọi.

## Sau bài học này

Bạn có thể:

- Phân biệt unit test domain, application test và persistence integration test.
- Kiểm tra transaction commit, rollback, flush và rollback rules.
- Nhận biết ảnh hưởng của transaction do Spring Test quản lý.
- Kiểm thử optimistic locking và pessimistic locking bằng transaction độc lập.
- Viết concurrency test có đồng bộ xác định thay vì dựa vào sleep.
- Kiểm tra invariant khi nhiều request cùng cập nhật aggregate.
- Thiết kế và kiểm thử idempotency key cho command được gửi lặp.
- Kiểm thử unique constraint, outbox, inbox và consumer nhận message trùng.
- Phân biệt retry an toàn với retry có thể lặp tác động.
- Chọn database/test environment đủ gần production để kiểm tra hành vi transaction.

## 1. Vì sao cần kiểm thử transaction và concurrency?

Một unit test có thể chứng minh aggregate từ chối xác nhận đơn đã hủy. Nhưng điều đó chưa chứng minh hai request đồng thời không thể cùng xác nhận đơn, hoặc transaction sẽ rollback khi bước ghi outbox thất bại.

Ví dụ tồn kho còn một sản phẩm. Hai khách hàng cùng gửi yêu cầu giữ một sản phẩm:

1. Request A đọc available = 1.
2. Request B cũng đọc available = 1.
3. A kiểm tra đủ hàng.
4. B cũng kiểm tra đủ hàng.
5. Cả hai cùng ghi reservation.

Nếu hệ thống chỉ kiểm tra bằng code trên object đã đọc mà không có concurrency control, cả hai có thể cùng thành công. Kết quả nghiệp vụ là giữ hai sản phẩm trong khi chỉ có một.

Một tình huống khác là client gửi command xác nhận đơn, server commit thành công nhưng response bị mất. Client timeout và gửi lại. Nếu server thực hiện lại tác động mà không có idempotency, hệ thống có thể tạo hai lần thu tiền hoặc hai reservation.

### Những thuộc tính cần chứng minh

| Thuộc tính | Câu hỏi kiểm thử |
| --- | --- |
| Atomicity | Nếu một bước thất bại, các thay đổi thuộc cùng transaction có rollback hết không? |
| Isolation/concurrency control | Hai transaction cạnh tranh có thể vi phạm invariant không? |
| Optimistic locking | Ghi dựa trên version cũ có bị phát hiện không? |
| Idempotency | Cùng một command/request ID gửi lại có tạo thêm tác động không? |
| Delivery reliability | Outbox/inbox có xử lý được publish lỗi và message trùng không? |
| Retry safety | Sau timeout hoặc conflict, retry có dùng trạng thái mới và không lặp side effect không? |

## 2. Chọn đúng cấp độ kiểm thử

Không phải mọi test đều cần Spring context hoặc database. Hãy đặt mỗi kiểm tra ở cấp phù hợp.

| Cấp kiểm thử | Thành phần | Điều cần chứng minh |
| --- | --- | --- |
| Domain unit test | Aggregate, entity, value object | Invariant, chuyển trạng thái và Domain Event đúng. |
| Application unit test | Command/query handler với fake port | Điều phối, quyền, kết quả và hành vi khi dependency lỗi. |
| Persistence integration test | Repository, ORM, database | Mapping, flush, constraint, version và transaction thực tế. |
| Concurrency integration test | Nhiều transaction/connection | Xung đột được phát hiện và invariant vẫn đúng. |
| Messaging integration test | Outbox, publisher, inbox, consumer | Giao nhận lặp, retry, checkpoint và atomicity. |
| API/contract test | HTTP endpoint và DTO | Request lặp, status code, idempotency contract và quyền truy cập. |

### Unit test domain không cần Spring

Ví dụ:

~~~java
@Test
void cannotReserveMoreThanAvailableStock() {
    InventoryItem item = InventoryItem.withStock(productId, 1);

    item.reserve(Quantity.of(1), reservationId);

    assertThrows(
        InsufficientStockException.class,
        () -> item.reserve(Quantity.of(1), anotherReservationId)
    );
}
~~~

Test này kiểm tra invariant trong một instance tuần tự. Nó rất hữu ích, nhưng không mô phỏng hai transaction đọc cùng một phiên bản database.

### Application unit test kiểm tra điều phối

Có thể dùng fake repository và fake outbox để xác nhận handler gọi đúng hành vi, lưu aggregate và ghi event. Test này không chứng minh database transaction rollback thật; nó chỉ xác minh logic application trong điều kiện dependency được thay thế.

### Integration test kiểm tra hành vi persistence thật

Khi cần kiểm tra transaction, lock hoặc constraint, hãy chạy qua Spring proxy và database thực tế (hoặc test database có semantics tương đương). Mock transaction manager không thể chứng minh database đã rollback dữ liệu.

## 3. Kiểm thử commit, rollback và flush

Một transaction có thể thất bại ở nhiều thời điểm:

- Trước khi lưu, do domain từ chối hành vi.
- Khi gọi repository, do lỗi mapping hoặc constraint.
- Khi flush, do SQL được gửi xuống database.
- Khi commit, do optimistic lock, deadlock hoặc constraint deferred.

Không nên chỉ kiểm tra exception được ném ra; hãy đọc lại trạng thái đã lưu để xác nhận transaction có hiệu lực như mong muốn.

### Ví dụ: aggregate và outbox phải cùng commit

Giả sử use case xác nhận đơn lưu aggregate và append Integration Event vào outbox trong cùng transaction:

~~~java
@Service
public class ConfirmOrderHandler {
    private final OrderRepository orders;
    private final IntegrationEventOutbox outbox;

    @Transactional
    public void handle(ConfirmOrder command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.confirm();
        orders.save(order);
        outbox.append(OrderConfirmed.from(order));
    }
}
~~~

Nếu append outbox thất bại, trạng thái đơn cũng phải rollback. Ngược lại, nếu transaction rollback do một bước sau đó thất bại, không được có outbox record để publisher gửi một event không tương ứng với thay đổi đã commit.

### Test rollback với Spring

~~~java
@SpringBootTest
class ConfirmOrderTransactionTest {
    @Autowired ConfirmOrderHandler handler;
    @Autowired OrderRepository orders;
    @Autowired IntegrationEventOutbox outbox;
    @Autowired OutboxFailureSwitch failureSwitch;

    @Test
    void rollsBackOrderWhenOutboxAppendFails() {
        OrderId id = givenAcceptedOrder();
        failureSwitch.failNextAppend();

        assertThrows(
            OutboxWriteException.class,
            () -> handler.handle(new ConfirmOrder(id))
        );

        Order reloaded = orders.findById(id).orElseThrow();
        assertEquals(OrderStatus.ACCEPTED, reloaded.status());
        assertEquals(0, outbox.countFor(id));
    }
}
~~~

Đây là khung minh họa; fixture và failure switch cần được triển khai trong test. Test phải gọi handler qua bean Spring được inject để transaction interceptor hoạt động.

### Vì sao cần flush?

ORM có thể trì hoãn SQL cho đến flush hoặc commit. Một test chỉ gọi repository save rồi kết thúc có thể chưa kích hoạt constraint hoặc optimistic lock.

Với JPA:

~~~java
entityManager.persist(entity);
entityManager.flush();
~~~

Flush buộc persistence context đồng bộ thay đổi xuống database trong transaction hiện tại. Nó giúp phát hiện lỗi SQL sớm trong test, nhưng flush không đồng nghĩa commit. Một số lỗi chỉ xuất hiện tại commit, nhất là constraint deferred hoặc transaction manager/provider cụ thể.

### Clear trước khi đọc lại

Nếu đọc lại từ cùng persistence context, ORM có thể trả instance đang được quản lý thay vì dữ liệu mới từ database. Dùng:

~~~java
entityManager.flush();
entityManager.clear();
OrderEntity reloaded = entityManager.find(OrderEntity.class, id);
~~~

Trong test cần xác minh rollback/commit thực sự, hãy bảo đảm lần đọc không chỉ lấy object còn trong first-level cache. Có thể dùng transaction mới hoặc query qua một connection khác khi phù hợp.

## 4. Cẩn thận với transaction do Spring Test quản lý

Các test dùng @DataJpaTest hoặc @Transactional ở test class thường chạy trong một transaction do Spring Test mở và rollback khi test kết thúc.

Điều này tiện cho việc cô lập dữ liệu, nhưng có thể che giấu hành vi:

- Service method dùng REQUIRED sẽ tham gia transaction test đang mở.
- Test kết thúc bằng rollback, nên không quan sát commit của service.
- Constraint/SQL có thể chưa chạy nếu test không flush.
- Test có thể đọc lại object từ persistence context nên không thấy vấn đề cache.
- Một concurrency test dùng chung transaction test không mô phỏng hai transaction độc lập.

### Khi nào dùng test-managed transaction?

Phù hợp cho repository test đơn giản hoặc test mapping cần dữ liệu tạm. Có thể dùng @DataJpaTest và flush/clear để kiểm tra round-trip.

### Khi nào cần transaction do service sở hữu?

Với test cần chứng minh commit/rollback của use case, hãy cân nhắc không đánh dấu test method @Transactional. Service được gọi qua proxy sẽ mở transaction riêng; sau khi method trả về, test đọc lại dữ liệu bằng transaction mới.

Một lựa chọn khác là dùng TestTransaction để kết thúc transaction test có chủ đích, nhưng cần quản lý rõ thời điểm commit và transaction tiếp theo.

### Tránh preemptive timeout đổi thread khi test transaction

Một số cơ chế timeout chạy test body trên thread khác. Transaction của Spring Test thường gắn với thread hiện tại; nếu test chuyển thread, transaction test có thể không còn áp dụng như dự kiến. Khi kiểm thử concurrency, hãy chủ động tạo transaction riêng cho từng worker thay vì dựa vào transaction bao ngoài của test.

## 5. Kiểm thử rollback rules và propagation

Spring có rollback mặc định cho RuntimeException và Error; checked exception cần rollbackFor nếu chính sách yêu cầu. Test cần xác minh hành vi thực tế chứ không chỉ kiểm tra annotation.

~~~java
@Transactional(rollbackFor = InventoryUnavailableException.class)
public void placeOrder(PlaceOrder command)
        throws InventoryUnavailableException {
    // ...
}
~~~

Các trường hợp cần test:

- RuntimeException sau khi thay đổi aggregate làm transaction rollback.
- Checked exception có rollbackFor làm rollback.
- Checked exception không nằm trong rollback rule có hành vi đúng theo thiết kế.
- noRollbackFor chỉ commit khi đó là chủ ý nghiệp vụ.
- Exception bị catch không làm use case báo thành công giả.
- Inner REQUIRED đánh dấu rollback-only có thể khiến outer commit ném UnexpectedRollbackException.
- REQUIRES_NEW có thể commit độc lập ngay cả khi transaction ngoài rollback.

### Test propagation phải gọi qua proxy

Nếu test gọi method trong cùng object qua self-invocation, proxy không intercept method bên trong. Hãy inject bean và gọi từ bên ngoài, hoặc tổ chức hai bean riêng cho hai transaction boundary.

Không nên test propagation bằng cách tạo class trực tiếp với new; annotation transaction khi đó không được Spring áp dụng.

## 6. Xung đột đồng thời và Optimistic Locking

Optimistic locking phù hợp khi xung đột không xảy ra thường xuyên. Mỗi aggregate/entity có version; khi update, ORM/database chỉ cập nhật nếu version vẫn bằng giá trị đã đọc.

~~~java
@Entity
public class InventoryItemEntity {
    @Id
    private UUID id;

    private int onHand;
    private int reserved;

    @Version
    private long version;

    protected InventoryItemEntity() {}
}
~~~

Nếu hai transaction cùng đọc version 7:

1. A cập nhật thành công và version thành 8.
2. B cố cập nhật với điều kiện version vẫn là 7.
3. Database cập nhật 0 dòng hoặc provider phát hiện conflict.
4. Transaction B rollback và application nhận lỗi optimistic locking.

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: Read item version 7
    B->>DB: Read item version 7
    A->>DB: Update WHERE version = 7
    DB-->>A: Updated, version 8
    B->>DB: Update WHERE version = 7
    DB-->>B: Conflict, zero rows updated
    B-->>B: Rollback
~~~

### Test optimistic locking với hai transaction độc lập

Test cần bảo đảm hai transaction cùng đọc một version trước khi cho phép ghi. Không nên dùng Thread.sleep để hy vọng hai thread đụng nhau đúng thời điểm.

Một cách tiếp cận là dùng TransactionTemplate trong mỗi thread và CountDownLatch làm barrier:

~~~java
@SpringBootTest
class InventoryConcurrencyTest {
    @Autowired PlatformTransactionManager transactionManager;
    @PersistenceContext EntityManager entityManager;

    @Test
    void oneConcurrentUpdateLosesWithOptimisticLock() throws Exception {
        TransactionTemplate tx = new TransactionTemplate(transactionManager);
        UUID itemId = givenInventory(1, 0);

        CountDownLatch bothLoaded = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<Boolean> attempt = () -> {
            try {
                tx.execute(status -> {
                    InventoryItemEntity item =
                        entityManager.find(InventoryItemEntity.class, itemId);
                    bothLoaded.countDown();
                    await(allowWrite);

                    item.reserveOne();
                    entityManager.flush();
                    return null;
                });
                return true;
            } catch (OptimisticLockingFailureException |
                     OptimisticLockException ex) {
                return false;
            }
        };

        Future<Boolean> first = pool.submit(attempt);
        Future<Boolean> second = pool.submit(attempt);

        assertTrue(bothLoaded.await(5, TimeUnit.SECONDS));
        allowWrite.countDown();

        List<Boolean> outcomes = List.of(
            first.get(10, TimeUnit.SECONDS),
            second.get(10, TimeUnit.SECONDS)
        );
        pool.shutdownNow();

        assertEquals(1, outcomes.stream().filter(Boolean::booleanValue).count());
        assertEquals(1, outcomes.stream().filter(v -> !v).count());
        assertEquals(1, readReservedQuantityInNewTransaction(itemId));
    }
}
~~~

Đây là khung minh họa. Helper await phải xử lý InterruptedException và khôi phục interrupt flag; test thực tế cũng cần đóng executor trong finally/try-with-resources và đặt timeout phù hợp. Tùy JPA provider, exception có thể được bọc thành Spring DataAccessException hoặc chỉ xuất hiện lúc commit; hãy kiểm tra cause chain và exception thực tế của stack đang dùng.

EntityManager được inject trong ứng dụng Spring thường là proxy theo transaction context, cho phép mỗi thread lấy persistence context riêng. Không chia sẻ một EntityManager instance thực giữa hai thread.

### Vì sao barrier quan trọng?

Nếu không có barrier, transaction A có thể commit trước khi B đọc. Khi đó B đọc version mới và cả hai có thể thành công tuần tự. Test vẫn pass nhưng không hề tạo ra xung đột mà nó muốn kiểm tra.

Barrier bảo đảm cả hai đã đọc cùng version trước khi cùng tiếp tục. Điều này làm test có tính xác định hơn và ít phụ thuộc tốc độ máy.

### Kiểm tra trạng thái cuối, không chỉ số exception

Test cần xác nhận:

- Có đúng một thao tác thành công.
- Transaction thua không để lại thay đổi một phần.
- Tổng reservation không vượt tồn kho.
- Event/outbox chỉ tồn tại cho thao tác đã commit.
- Version tăng đúng số lần commit thành công.

## 7. Pessimistic locking và kiểm thử lock

Pessimistic locking khóa row hoặc resource trong lúc transaction xử lý, ví dụ JPA:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from InventoryItemEntity i where i.id = :id")
Optional<InventoryItemEntity> findForUpdate(UUID id);
~~~

Transaction thứ hai có thể phải chờ transaction đầu nhả lock, hoặc thất bại khi lock timeout. Cách hành xử phụ thuộc database và cấu hình lock timeout.

### Kiểm thử điều gì?

- Transaction A lấy lock ghi.
- Transaction B yêu cầu cùng lock và phải chờ hoặc timeout theo cấu hình.
- Sau khi A commit, B đọc trạng thái mới và đánh giá lại điều kiện.
- Không có hai reservation vượt invariant.
- Lock được giải phóng khi transaction commit/rollback.

### Không dùng sleep để kiểm tra lock

Dùng latch hoặc tín hiệu đồng bộ để biết A đã lấy lock trước khi B bắt đầu. Nếu cần kiểm tra B đang bị chặn, có thể dùng timeout có giới hạn cho Future, nhưng đừng xem một khoảng sleep cố định là bằng chứng lock hoạt động.

### Chọn optimistic hay pessimistic?

| Tiêu chí | Optimistic | Pessimistic |
| --- | --- | --- |
| Giả định | Xung đột ít | Xung đột có thể thường xuyên |
| Cơ chế | Version/check khi ghi | Khóa trong lúc xử lý |
| Khi conflict | Một transaction thất bại, có thể retry | Request khác chờ hoặc timeout |
| Rủi ro | Retry nhiều khi contention cao | Lock wait, deadlock, giữ tài nguyên |
| Phù hợp | Aggregate ít tranh chấp, thời gian xử lý ngắn | Tài nguyên khan hiếm, quyết định cần tuần tự hóa |

Đừng chọn locking chỉ theo cảm giác. Đo contention và kiểm thử với workload gần thực tế.

## 8. Kiểm thử invariant dưới tải đồng thời

Một invariant quan trọng phải được kiểm tra sau khi nhiều transaction chạy cạnh tranh. Ví dụ tồn kho:

~~~java
assertTrue(item.reserved() <= item.onHand());
assertTrue(item.available() >= 0);
~~~

Hoặc với tài khoản:

~~~java
assertTrue(account.balance().isGreaterThanOrEqualTo(Money.zero(account.currency())));
~~~

Test có thể chạy nhiều request đồng thời, mỗi request yêu cầu một đơn vị. Tổng số thao tác thành công không được vượt lượng hàng ban đầu.

### Kiểm thử property/invariant sau nhiều lệnh

Ngoài một kịch bản cố định, có thể sinh nhiều chuỗi command và kiểm tra invariant sau mỗi lần commit. Cách này hữu ích để tìm lỗi ở ranh giới trạng thái, nhưng phải đảm bảo mỗi command chạy qua transaction thật khi mục tiêu là kiểm tra concurrency.

### Kiểm tra không có cập nhật bị mất

Nếu nhiều request tăng counter, kết quả cuối phải bằng số thao tác commit thành công. Một phép đọc rồi ghi lại giá trị có thể gây lost update nếu không có lock hoặc atomic update. Test phải tạo cạnh tranh đủ rõ để phát hiện lỗi này.

## 9. Yêu cầu lặp và Idempotency

Client có thể gửi lại cùng request vì:

- Response bị mất sau khi server đã commit.
- Gateway timeout hoặc retry tự động.
- Người dùng bấm nút nhiều lần.
- Mobile client chuyển mạng và gửi lại.
- Message broker giao lại message sau khi consumer chưa ack.

Idempotency bảo đảm cùng một ý định được xử lý lặp không tạo thêm tác động ngoài ý muốn.

### Idempotency key

Command có thể chứa key định danh request:

~~~java
public record CapturePayment(
    PaymentId paymentId,
    Money amount,
    String idempotencyKey
) {}
~~~

Key cần có scope rõ ràng, ví dụ tenant + actor/client + operation type. Không nên dùng key toàn cục không có phạm vi nếu các client có thể tự chọn giá trị trùng.

### Lưu request hash

Ngoài key, nên lưu hash của payload chuẩn hóa. Nếu cùng key nhưng payload khác, server cần từ chối conflict thay vì trả kết quả cũ cho một yêu cầu có ý nghĩa khác.

Ví dụ:

| Key | Request hash | Hành vi |
| --- | --- | --- |
| K1 | H1 | Xử lý lần đầu và lưu kết quả. |
| K1 | H1 | Trả lại kết quả đã lưu, không lặp tác động. |
| K1 | H2 | Từ chối vì key đã được dùng cho nội dung khác. |

### Ghi idempotency record cùng thay đổi nghiệp vụ

Với command đồng bộ trong một database, transaction nên bao gồm:

1. Claim/ghi idempotency key.
2. Thực hiện hành vi aggregate.
3. Lưu aggregate.
4. Ghi outbox.
5. Lưu kết quả command.
6. Commit.

Nếu transaction rollback, key chưa được đánh dấu hoàn tất cùng một kết quả thành công giả. Nếu transaction commit, request lặp có thể đọc kết quả đã lưu.

### Unique constraint bảo vệ request cạnh tranh

Hai request đầu tiên có cùng key có thể đến gần như đồng thời. Cả hai cùng kiểm tra “chưa tồn tại” rồi cùng cố tạo record. Chỉ kiểm tra bằng SELECT trước khi INSERT là không đủ.

Đặt unique constraint trên scope + idempotency key để database phân xử cạnh tranh. Khi một request thắng, request còn lại cần đọc lại record đã commit và so sánh request hash.

Nếu INSERT bị unique violation, transaction hiện tại có thể đã bị đánh dấu rollback-only. Không nên bắt lỗi đó bên trong transaction rồi tiếp tục dùng cùng transaction như thể vẫn khỏe. Hãy xử lý ở boundary phù hợp: rollback transaction thất bại, sau đó đọc kết quả trong transaction mới; hoặc dùng upsert/claim primitive được database hỗ trợ.

## 10. Kiểm thử Idempotency cho HTTP command

Một API command có thể nhận Idempotency-Key header:

~~~http
POST /payments/pay-1042/capture
Idempotency-Key: capture-order-1042-attempt-1
Content-Type: application/json

{
  "amount": "250000",
  "currency": "VND"
}
~~~

Các test quan trọng:

- Gửi lần đầu, command được thực hiện và trả kết quả.
- Gửi lại cùng key và payload, nhận kết quả tương đương, không tạo capture thứ hai.
- Gửi cùng key với payload khác, nhận conflict theo API contract.
- Gửi hai request cùng key đồng thời, chỉ một tác động được commit.
- Request đầu rollback giữa chừng, request retry có thể thực hiện theo chính sách.
- Response timeout sau commit, retry vẫn trả kết quả đã lưu.
- Key hết hạn theo policy, hành vi sau thời hạn được định nghĩa rõ.

### Ví dụ test ở cấp API

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CapturePaymentApiTest {
    @Autowired MockMvc mvc;
    @Autowired PaymentRepository payments;

    @Test
    void repeatedRequestWithSameKeyDoesNotCaptureTwice() throws Exception {
        String key = "capture-pay-1042-1";

        mvc.perform(post("/payments/pay-1042/capture")
                .header("Idempotency-Key", key)
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"amount":"250000","currency":"VND"}
                    """))
            .andExpect(status().isOk());

        mvc.perform(post("/payments/pay-1042/capture")
                .header("Idempotency-Key", key)
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"amount":"250000","currency":"VND"}
                    """))
            .andExpect(status().isOk());

        assertEquals(1, payments.countCapturesFor("pay-1042"));
    }
}
~~~

Ví dụ dùng text block Java và lược giản authentication/setup. Assertion quan trọng là số tác động nghiệp vụ được commit, không chỉ hai response có status 200.

## 11. Idempotency cho message consumer và Inbox

Message broker thường cung cấp delivery ít nhất một lần trong nhiều cấu hình phổ biến. Consumer có thể xử lý xong nhưng chết trước khi ack, khiến message được giao lại.

Một Inbox lưu event ID đã xử lý. Việc cập nhật aggregate/projection và đánh dấu Inbox nên cùng transaction nếu cùng database:

~~~java
@Transactional
public void handle(StockReserved event) {
    if (inbox.exists(event.eventId())) {
        return;
    }

    OrderProcess process = processes.get(event.orderId());
    process.recordReservation(event.reservationId());
    processes.save(process);
    inbox.markProcessed(event.eventId());
}
~~~

Nếu transaction commit, cả thay đổi và Inbox marker cùng tồn tại. Nếu rollback, cả hai rollback và broker có thể giao lại để xử lý.

### Test message trùng

1. Gửi event E lần đầu.
2. Xác nhận process state/projection đã thay đổi đúng.
3. Gửi lại đúng event ID E.
4. Xác nhận state không thay đổi thêm.
5. Xác nhận không tạo thêm event/outbox hoặc side effect.

### Event ID và business key khác nhau

Event ID định danh một message cụ thể. Business key định danh một ý định hoặc tài nguyên nghiệp vụ, ví dụ payment capture operation. Hai event khác ID có thể vẫn đại diện cho cùng một business operation. Trong một số use case, cần deduplicate theo cả event ID và business key.

## 12. Retry sau conflict và lỗi tạm thời

Retry không phải cách chữa mọi lỗi. Cần phân loại:

| Loại lỗi | Có nên retry? | Điều kiện |
| --- | --- | --- |
| Optimistic lock conflict | Có thể | Tải lại trạng thái mới và chạy lại logic; không dùng aggregate cũ. |
| Deadlock/serialization failure | Có thể | Retry toàn transaction với giới hạn và backoff. |
| Timeout không rõ kết quả | Có thể sau khi tra cứu hoặc dùng cùng idempotency key | Không tạo operation mới ngoài ý muốn. |
| Domain rule rejection | Thường không | Trạng thái hiện tại không cho phép hành động; cần caller thay đổi yêu cầu hoặc chờ điều kiện. |
| Validation error | Không | Payload cần được sửa. |
| Schema/contract error | Không retry vô hạn | Cần sửa consumer hoặc cách ly message. |
| Service unavailable | Có thể | Retry có giới hạn, backoff và circuit breaker phù hợp. |

### Retry phải chạy lại toàn bộ quyết định dựa trên trạng thái mới

Sau optimistic lock conflict, không nên chỉ gửi lại câu lệnh UPDATE đã tính từ aggregate cũ. Hãy tải lại aggregate, kiểm tra lại quyền và invariant, sau đó quyết định command còn hợp lệ không.

### Retry cần giới hạn

Một chính sách thường có:

- Số lần retry tối đa.
- Exponential backoff.
- Jitter để tránh nhiều worker retry cùng lúc.
- Phân loại lỗi retryable/non-retryable.
- Deadline tổng thể.
- Logging/metrics và dead-letter khi vượt giới hạn.

Không retry trong vòng lặp vô hạn bên trong transaction đang rollback-only. Mỗi lần retry transaction nên có boundary mới nếu database yêu cầu.

## 13. Kiểm thử Transactional Outbox cùng aggregate

Outbox giải quyết dual write giữa database và broker bằng cách ghi message cần gửi trong cùng transaction với aggregate. Test phải xác nhận hai phía cùng commit hoặc cùng rollback.

### Các kịch bản

- Aggregate save thành công và outbox append thành công: cả hai tồn tại.
- Aggregate thay đổi nhưng outbox append lỗi: cả hai rollback.
- Transaction rollback sau khi append outbox: outbox không được publish.
- Publisher gửi message thành công nhưng chết trước khi đánh dấu sent: message có thể được gửi lại; consumer phải idempotent.
- Publisher lỗi broker: record vẫn pending và có thể retry.
- Event được publish hai lần: consumer không lặp tác động.

### Kiểm thử publisher và consumer tách biệt

Không nên dùng một test mock broker để tuyên bố end-to-end exactly-once. Kiểm thử producer/outbox, broker delivery và consumer idempotency theo từng boundary. Hệ thống thường đạt hiệu quả exactly-once ở mức nghiệp vụ bằng durable message + deduplication/idempotent handling, chứ không dựa vào một bảo đảm đơn giản rằng message chỉ được giao một lần.

### Không gọi broker trực tiếp trong transaction test

Test transaction database không thể rollback một message đã được broker nhận. Hãy kiểm tra outbox record trong transaction, sau đó test publisher riêng. Với integration test end-to-end, cần có cách cô lập topic/queue và dọn dữ liệu kiểm thử.

## 14. Test isolation, lost update và phantom behavior

Isolation level có ảnh hưởng đến dữ liệu mà transaction nhìn thấy. Các test có thể tập trung vào anomaly cụ thể:

- Dirty read: đọc dữ liệu chưa commit.
- Non-repeatable read: cùng một row có giá trị khác ở lần đọc sau.
- Phantom read: truy vấn điều kiện trả về tập row khác do transaction khác thêm/xóa.
- Lost update: cập nhật của một transaction ghi đè thay đổi của transaction khác.
- Write skew: hai transaction cập nhật các row khác nhau nhưng cùng vi phạm một invariant liên hàng.

Không phải database nào cũng biểu hiện anomaly giống nhau ở cùng tên isolation level. Cần viết test trên database engine thực tế và dựa vào invariant của ứng dụng.

### Ví dụ write skew

Giả sử quy tắc yêu cầu luôn có ít nhất một bác sĩ trực. Hai transaction cùng đọc thấy hai bác sĩ đang trực. A chuyển bác sĩ 1 sang nghỉ; B chuyển bác sĩ 2 sang nghỉ. Mỗi transaction sửa row khác nhau nên có thể cùng commit ở isolation không đủ mạnh, làm không còn ai trực.

Giải pháp có thể là:

- Mô hình hóa lịch trực thành một aggregate có invariant chung.
- Dùng lock trên một resource đại diện.
- Dùng constraint/atomic update phù hợp.
- Nâng isolation nếu database và workload hỗ trợ.

Test cần chạy hai transaction cùng đọc trạng thái ban đầu rồi cùng cập nhật để xác nhận hệ thống không cho vi phạm invariant.

## 15. Test trên database nào?

In-memory database tiện và nhanh, nhưng không phải lúc nào cũng mô phỏng đúng production:

- Isolation và locking có thể khác.
- Cách phát sinh deadlock/serialization failure khác.
- Kiểu dữ liệu, constraint và SQL dialect khác.
- Behavior của sequence, timestamp và index khác.
- JPA provider có thể tạo SQL khác theo dialect.

### Khi nào H2 hoặc database nhẹ là đủ?

Phù hợp cho mapping đơn giản, repository query cơ bản hoặc test nhanh khi behavior cần kiểm tra không phụ thuộc đặc tính riêng của production database.

### Khi nào nên dùng Testcontainers?

Với PostgreSQL, MySQL, SQL Server hoặc database cụ thể đang chạy production, Testcontainers giúp khởi chạy cùng engine trong integration test. Điều này hữu ích cho optimistic/pessimistic lock, unique constraint, isolation, JSON/array type và SQL đặc thù.

Không cần chạy container cho mọi unit test. Hãy dành database integration test cho những behavior thực sự phụ thuộc database.

## 16. Thiết kế test concurrency ổn định

Concurrency test dễ flaky nếu phụ thuộc thời gian hoặc tải máy. Một số nguyên tắc:

- Dùng CountDownLatch, CyclicBarrier hoặc Phaser để đồng bộ điểm đọc/ghi.
- Mỗi worker có transaction và persistence context riêng.
- Không chia sẻ EntityManager hoặc Hibernate Session giữa thread.
- Đặt timeout cho latch và Future để test không treo vô hạn.
- Dùng dữ liệu riêng cho mỗi test và cleanup rõ.
- Không dựa vào thứ tự scheduler hoặc Thread.sleep.
- Thu thập tất cả Future và kiểm tra exception từ worker.
- Xác nhận trạng thái cuối từ transaction mới.
- Chạy lặp có kiểm soát trong CI để phát hiện flaky behavior, nhưng không dùng số lần chạy thay cho thiết kế đồng bộ đúng.

### Tránh test chỉ kiểm tra một thread thắng

Một test concurrency tốt cần chứng minh cả kết quả thành công lẫn kết quả bị từ chối/conflict, đồng thời xác nhận invariant cuối. Nếu chỉ assert một Future thành công, test có thể bỏ qua việc cả hai cùng thành công.

### Không che exception trong worker

Nếu Callable bắt mọi Exception rồi trả false, test có thể coi lỗi cấu hình, timeout hoặc NullPointerException là một conflict hợp lệ. Chỉ phân loại exception được mong đợi; các lỗi khác phải làm test fail với cause rõ ràng.

## 17. Kiểm thử API retry và double submit

Ngoài test service, cần kiểm tra behavior qua HTTP:

- Hai POST cùng idempotency key và body.
- Cùng key nhưng body khác.
- Hai key khác nhau cho cùng business operation.
- Response mất sau khi commit rồi client retry.
- Người dùng double-click.
- Gateway retry request.
- Caller không có quyền gửi lại command.

Một test có thể kiểm tra response đầu và response lặp có cùng operation/result ID, trong khi số capture/reservation chỉ tăng một lần.

### HTTP status code là một phần hợp đồng

Tùy API design, request trùng đã hoàn tất có thể trả lại response thành công trước đó; key conflict có thể trả 409; request đang xử lý có thể trả 202 hoặc response trạng thái phù hợp. Điều quan trọng là hợp đồng được tài liệu hóa và client biết có nên retry, poll hay sửa request.

Không nên chỉ dựa vào status code để xác nhận idempotency. Phải kiểm tra side effect thực tế trong database hoặc hệ thống đích giả lập.

## 18. Các lỗi thường gặp trong test

- **Chỉ unit test aggregate:** bỏ sót transaction, database constraint và concurrency.
- **Mock transaction manager:** không chứng minh commit/rollback thật.
- **Không flush:** lỗi constraint hoặc optimistic lock chưa xuất hiện.
- **Không clear persistence context:** đọc lại object cũ từ first-level cache.
- **Dùng @Transactional trên test cho concurrency:** các worker có thể không chạy trong transaction độc lập như kỳ vọng.
- **Dùng Thread.sleep:** test phụ thuộc timing và dễ flaky.
- **Chia sẻ EntityManager giữa thread:** vi phạm thread-safety và không mô phỏng persistence context riêng.
- **Chỉ assert exception:** không kiểm tra dữ liệu một phần có bị commit hay không.
- **Không kiểm tra outbox cùng aggregate:** có thể phát event cho transaction rollback hoặc mất event sau commit.
- **Kiểm tra idempotency bằng số lần method gọi:** không chứng minh tác động bên ngoài chỉ xảy ra một lần.
- **Không kiểm tra cùng key khác payload:** key có thể bị tái sử dụng sai.
- **Retry aggregate cũ:** logic được tính trên version đã lỗi thời.
- **Bắt mọi exception trong worker:** che giấu lỗi test thật.
- **Dùng in-memory DB để kết luận về production locking:** semantics có thể khác.
- **Khẳng định exactly-once chỉ từ broker ack:** consumer vẫn có thể xử lý lại sau crash.
- **Không cleanup executor/thread:** test suite có thể treo hoặc rò tài nguyên.

## 19. Quy trình thiết kế bộ test cho một use case

Với mỗi command quan trọng như PlaceOrder, ReserveStock hoặc CapturePayment, hãy thực hiện:

1. **Liệt kê invariant:** số dư không âm, tồn kho không âm, một capture cho mỗi operation.
2. **Xác định transaction boundary:** dữ liệu và outbox nào phải cùng commit?
3. **Viết domain test:** hành vi hợp lệ và không hợp lệ.
4. **Viết application test:** quyền, thứ tự điều phối, kết quả và lỗi dependency.
5. **Viết persistence test:** flush, constraint, version, rollback và round-trip.
6. **Viết concurrency test:** hai transaction cùng đọc và cùng ghi theo barrier.
7. **Viết idempotency test:** request lặp cùng key, key khác payload và request đồng thời.
8. **Viết messaging test:** outbox, retry, duplicate delivery và inbox.
9. **Viết API test:** double submit, timeout/retry contract và authorization.
10. **Chạy trên database phù hợp:** Testcontainers hoặc môi trường tương đương production khi cần.
11. **Kiểm tra trạng thái cuối:** aggregate, reservation, payment, outbox và audit.
12. **Đặt timeout/cleanup:** không để worker hoặc transaction bị treo sau test.

## Checklist rà soát

- [ ] Domain unit test kiểm tra invariant và event.
- [ ] Application test kiểm tra orchestration và quyền.
- [ ] Integration test gọi qua Spring proxy thật.
- [ ] Rollback test đọc lại dữ liệu sau transaction thất bại.
- [ ] Flush/clear được dùng khi cần kiểm tra SQL và trạng thái lưu.
- [ ] Test-managed transaction không che giấu commit của service.
- [ ] Optimistic locking test có hai transaction độc lập cùng đọc một version.
- [ ] Pessimistic locking test xác nhận wait/timeout và trạng thái cuối.
- [ ] Concurrency test dùng barrier/latch thay vì sleep.
- [ ] Test xác nhận invariant sau tất cả transaction.
- [ ] Idempotency key có scope và request hash.
- [ ] Cùng key/cùng payload không lặp tác động; cùng key/khác payload bị từ chối.
- [ ] Request đồng thời cùng key chỉ tạo một operation.
- [ ] Outbox và aggregate cùng commit/rollback.
- [ ] Inbox/consumer xử lý message trùng an toàn.
- [ ] Retry tải lại trạng thái và chạy lại logic, có giới hạn.
- [ ] Test dùng database engine phù hợp cho locking/isolation quan trọng.
- [ ] Executor, latch, test data và transaction được cleanup đúng.

## Kết luận

Kiểm thử transaction, concurrency và yêu cầu lặp phải chứng minh trạng thái nghiệp vụ cuối cùng vẫn đúng khi có lỗi hoặc tranh chấp. Unit test xác nhận aggregate bảo vệ invariant; integration test xác nhận transaction và database thực hiện commit/rollback; concurrency test xác nhận lock/version ngăn cập nhật xung đột; idempotency test xác nhận request hoặc message lặp không tạo thêm tác động. Hãy đồng bộ concurrency test bằng barrier, chạy mỗi worker trong transaction riêng, kiểm tra dữ liệu sau commit và dùng database gần production cho các hành vi phụ thuộc engine. Khi kết hợp outbox/inbox, unique constraint, request hash và retry có giới hạn, hệ thống có thể phục hồi an toàn trước timeout, conflict và delivery lặp.
