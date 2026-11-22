# Kiểm thử cạnh tranh cập nhật và gửi thao tác lặp

Trong ứng dụng Model–View–Controller (MVC), nhiều request có thể cùng đọc và thay đổi một dữ liệu gần như đồng thời. Người dùng có thể mở một đơn hàng ở hai tab, hai nhân viên cùng sửa một hồ sơ, hoặc trình duyệt gửi lại lệnh vì mạng bị gián đoạn. Một thao tác cũng có thể được gửi hai lần khi người dùng nhấn nút liên tiếp, client tự retry hoặc proxy gửi lại request sau timeout.

Những tình huống này không được giải quyết chỉ bằng cách vô hiệu hóa nút trong View. Máy chủ phải bảo vệ dữ liệu ở tầng nghiệp vụ và cơ sở dữ liệu; kiểm thử phải tạo được tình huống cạnh tranh thật để chứng minh chỉ một kết quả hợp lệ được ghi nhận. Bài học này trình bày cách nhận diện race condition, chọn cơ chế đồng bộ và viết kiểm thử đáng tin cậy cho các request cạnh tranh hoặc lặp.

## 1. Hai vấn đề khác nhau: cập nhật cạnh tranh và thao tác lặp

Hai tình huống thường xuất hiện cùng nhau nhưng cần được phân biệt:

- **Cập nhật cạnh tranh (concurrent update):** hai hoặc nhiều request thao tác trên cùng dữ liệu trong khoảng thời gian chồng lấn. Kết quả có thể ghi đè thay đổi của nhau hoặc vi phạm bất biến.
- **Gửi thao tác lặp (duplicate submission):** cùng một ý định nghiệp vụ được gửi nhiều lần. Hệ thống có thể tạo hai đơn, trừ tiền hai lần hoặc gửi nhiều thông báo.

Ví dụ một đơn hàng có trạng thái `DRAFT`:

1. Nhân viên A và B cùng mở trang chi tiết.
2. Cả hai đều nhìn thấy trạng thái `DRAFT`.
3. A xác nhận đơn.
4. B cũng gửi lệnh xác nhận từ trang đã mở trước đó.

Đây là cập nhật cạnh tranh trên cùng trạng thái. Nếu B nhấn nút hai lần hoặc client retry POST của B, hệ thống còn gặp thao tác lặp.

| Tình huống | Rủi ro chính | Cơ chế thường dùng |
|---|---|---|
| Hai người sửa cùng một bản ghi | Lost update, ghi đè dữ liệu mới | Optimistic locking, pessimistic locking |
| Hai request cùng đặt chỗ cuối cùng | Vượt số lượng còn lại | Atomic update, row lock, constraint |
| Cùng một lệnh thanh toán được gửi lại | Trừ tiền hoặc tạo giao dịch hai lần | Idempotency key, mã giao dịch duy nhất |
| Consumer xử lý lại message | Tác động bên ngoài bị lặp | Deduplication, inbox/outbox, idempotent handler |
| Client timeout sau khi server đã commit | Người dùng retry dù thao tác đã thành công | Idempotency và truy vấn trạng thái kết quả |

Một request hợp lệ về cấu trúc và quyền vẫn có thể không còn hợp lệ tại thời điểm ghi. Vì vậy, validation ở Controller không thay thế kiểm soát đồng thời trong application service, Model và database.

## 2. Hiểu race condition và lost update

Race condition xuất hiện khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các thao tác chạy đồng thời. Một ví dụ đơn giản là hai request cùng đọc số lượng tồn kho:

```text
Tồn kho ban đầu: 1

Request A đọc tồn kho = 1
Request B đọc tồn kho = 1
Request A kiểm tra đủ hàng
Request B kiểm tra đủ hàng
Request A ghi tồn kho = 0
Request B ghi tồn kho = 0

Kết quả: hai đơn được chấp nhận dù chỉ có một sản phẩm.
```

Giá trị cuối trong database vẫn là 0 nên có thể không thấy lỗi bằng cách chỉ kiểm tra số tồn. Lỗi nằm ở việc hai đơn đều được chấp nhận dựa trên cùng một giá trị cũ.

### Lost update

Lost update xảy ra khi hai request đọc cùng một phiên bản, mỗi request tính giá trị mới, rồi lần ghi sau ghi đè kết quả của lần ghi trước.

Ví dụ số dư ban đầu là 100:

```text
Request A đọc 100, muốn cộng 20, tính ra 120
Request B đọc 100, muốn trừ 10, tính ra 90
Request A ghi 120
Request B ghi 90

Kết quả cuối: 90
Kết quả đúng nếu cả hai thao tác được áp dụng: 110
```

Đây là lý do không nên dựa vào quy trình “đọc, tính trong Java, ghi lại” nếu có thể có request đồng thời. Phải có cơ chế đảm bảo thao tác dựa trên trạng thái còn hợp lệ.

### Xác định bất biến cần bảo vệ

Trước khi chọn locking, hãy viết rõ điều kiện không được phép bị phá vỡ:

- Số lượng tồn kho không được âm.
- Một mã đặt chỗ chỉ được cấp cho một khách hàng.
- Một đơn hàng chỉ được xác nhận từ trạng thái cho phép.
- Một khóa đăng ký chỉ được sử dụng một lần.
- Một payment intent chỉ tạo tối đa một giao dịch thành công.
- Tổng số chỗ đã xác nhận không vượt sức chứa.

Kiểm thử phải xác minh bất biến và tác động nghiệp vụ cuối cùng, không chỉ kiểm tra HTTP status.

## 3. Optimistic locking với version

Optimistic locking phù hợp khi xung đột không thường xuyên. Mỗi bản ghi có một trường version. Khi đọc, ORM lấy version hiện tại; khi cập nhật, câu lệnh SQL chỉ thành công nếu version vẫn giống giá trị đã đọc. Nếu một request khác đã cập nhật trước, request sau nhận lỗi xung đột thay vì ghi đè âm thầm.

Ví dụ với JPA:

```java
@Entity
public class Order {
    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Version
    private long version;

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new InvalidOrderStateException();
        }
        status = OrderStatus.CONFIRMED;
    }
}
```

Khi flush, JPA provider thường phát lệnh tương đương:

```sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Nếu không có hàng nào được cập nhật vì version đã đổi, provider báo optimistic locking failure. Tùy thời điểm flush và commit, lỗi có thể xuất hiện khi gọi `flush()` hoặc khi transaction commit.

### Xử lý xung đột trong MVC

Application service để transaction rollback khi xảy ra optimistic locking failure. Ở biên HTTP, ứng dụng có thể ánh xạ xung đột thành `409 Conflict` và yêu cầu người dùng tải lại dữ liệu:

```java
@RestControllerAdvice
public class ApiConflictHandler {
    @ExceptionHandler({
        ObjectOptimisticLockingFailureException.class,
        OptimisticLockException.class
    })
    public ResponseEntity<ApiError> handleConcurrentUpdate() {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError(
                "CONCURRENT_UPDATE",
                "Dữ liệu đã được thay đổi. Hãy tải lại trước khi thử lại."
            ));
    }
}
```

Đây là ví dụ rút gọn; trong ứng dụng thực tế cần kiểm tra cả exception được bọc ở tầng transaction và tránh khai báo handler trùng lặp. Không bắt lỗi optimistic lock bên trong transaction rồi tiếp tục ghi như thể transaction vẫn hợp lệ.

Với form HTML, có thể trả lại trang thông báo xung đột kèm đường dẫn tải dữ liệu mới. Nếu dùng ETag và `If-Match`, `412 Precondition Failed` cũng là một lựa chọn phù hợp khi điều kiện phiên bản của HTTP không còn đúng. Hãy giữ một hợp đồng lỗi nhất quán cho client.

## 4. Pessimistic locking và cập nhật nguyên tử

Pessimistic locking khóa bản ghi trong transaction để request khác phải chờ hoặc thất bại khi lấy khóa. Cách này phù hợp với đoạn xử lý có xung đột thường xuyên hoặc cần tuần tự hóa một tài nguyên trong thời gian ngắn.

Ví dụ Spring Data JPA:

```java
public interface InventoryRepository
        extends JpaRepository<Inventory, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findForUpdate(@Param("id") UUID id);
}
```

Application service giữ khóa trong transaction:

```java
@Transactional
public void reserve(UUID inventoryId, int quantity) {
    Inventory inventory = repository.findForUpdate(inventoryId)
        .orElseThrow(InventoryNotFoundException::new);

    inventory.reserve(quantity);
}
```

Pessimistic lock cần được dùng có chủ đích:

- Transaction phải ngắn; không gọi dịch vụ bên ngoài khi đang giữ khóa.
- Các luồng lấy nhiều khóa cần thứ tự nhất quán để giảm deadlock.
- Phải có timeout và xử lý lock timeout/deadlock phù hợp.
- Hành vi khóa phụ thuộc database, isolation level và query thực tế.
- Cần kiểm thử trên cùng loại database được dùng khi triển khai.

### Atomic update

Với thao tác đơn giản như giảm tồn kho, một câu lệnh có điều kiện có thể vừa kiểm tra vừa cập nhật:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE id = :inventoryId
  AND available >= :quantity;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng:

- `1`: cập nhật thành công.
- `0`: không tồn tại bản ghi hoặc không đủ tồn kho; cần phân biệt nếu nghiệp vụ yêu cầu.

Phép kiểm tra và thay đổi nằm trong cùng câu lệnh nên tránh khoảng trống giữa đọc và ghi. Cần bổ sung validation `quantity > 0`, kiểm tra ID và xử lý đúng kết quả update. Atomic update không tự xử lý các tác động liên quan như tạo đơn hàng, ghi lịch sử hoặc phát sự kiện; chúng cần nằm trong transaction hoặc cơ chế nhất quán phù hợp.

### Ràng buộc database là lớp bảo vệ cuối

Các bất biến có thể biểu diễn bằng constraint nên được bảo vệ ở database:

```sql
ALTER TABLE inventory
ADD CONSTRAINT chk_inventory_available_nonnegative
CHECK (available >= 0);

CREATE UNIQUE INDEX uq_reservation_reference
ON reservations (external_reference);
```

Constraint bảo vệ dữ liệu kể cả khi có nhiều instance ứng dụng, script quản trị hoặc một luồng code quên kiểm tra. Kiểm tra trong Java giúp đưa ra thông báo thân thiện; constraint bảo vệ tính đúng đắn cuối cùng.

## 5. Thao tác lặp và idempotency

Một thao tác idempotent có kết quả nghiệp vụ tương đương khi được thực hiện nhiều lần với cùng ý định. Tính idempotent phải được định nghĩa theo nghiệp vụ; không phải cứ trả cùng HTTP status là đã idempotent.

Ví dụ:

- `GET /orders/42` là thao tác đọc và không nên thay đổi trạng thái.
- `PUT /profile/42` có thể idempotent nếu cùng payload đặt tài nguyên về cùng trạng thái.
- `POST /orders` thường tạo tài nguyên mới mỗi lần, nên gửi lại có thể tạo hai đơn.
- `POST /payments` có thể trừ tiền nhiều lần nếu không có cơ chế chống trùng.

### Vì sao vô hiệu hóa nút chưa đủ?

View có thể disable nút sau lần nhấn đầu tiên để tránh người dùng nhấn liên tiếp. Tuy nhiên, request vẫn có thể được gửi lặp bởi:

- Người dùng mở nhiều tab.
- Mạng chập chờn khiến client retry.
- Máy chủ đã commit nhưng response bị mất.
- Client hoặc proxy gửi lại request.
- Một người dùng khác thực hiện cùng hành động.

Do đó, chống gửi trùng phải được thực hiện ở server và database. Disable button chỉ là cải thiện trải nghiệm.

### Idempotency key

Với thao tác tạo tài nguyên hoặc thanh toán, client có thể gửi một key đại diện cho một ý định nghiệp vụ:

```http
POST /api/payments
Idempotency-Key: 6b1b6f8c-7c9a-4e4a-a8b4-...
Content-Type: application/json
```

Server lưu key cùng phạm vi người dùng, loại thao tác, dấu vân tay payload và kết quả. Một cấu trúc tối thiểu có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| actor_id | Người dùng hoặc tenant tạo thao tác |
| operation | Loại hành động, ví dụ CREATE_PAYMENT |
| idempotency_key | Khóa duy nhất client gửi |
| request_hash | Dấu vân tay payload đã chuẩn hóa |
| status | Trạng thái xử lý |
| response_code | HTTP status của kết quả đã ghi nhận |
| response_body | Kết quả có thể phát lại theo hợp đồng |
| created_at / expires_at | Thời gian lưu và thời hạn key |

Database cần unique constraint trên phạm vi key, ví dụ `(actor_id, operation, idempotency_key)`. Nếu cùng key được gửi lại:

1. Cùng payload và thao tác đã hoàn tất: trả lại kết quả đã lưu.
2. Cùng key nhưng payload khác: từ chối vì một key không được đại diện cho hai ý định khác nhau.
3. Request đầu tiên vẫn đang xử lý: chờ kết quả, trả trạng thái đang xử lý hoặc dùng cơ chế phối hợp đã thiết kế.
4. Key đã hết thời hạn: xử lý theo chính sách lưu trữ và khả năng một request cũ xuất hiện lại.

Không chỉ kiểm tra key bằng một câu SELECT rồi mới insert. Hai request có thể cùng thấy key chưa tồn tại và cùng chạy nghiệp vụ. Việc chiếm key cần được bảo vệ bằng unique constraint hoặc thao tác nguyên tử trong database.

Khi một request thua cuộc đua insert do unique constraint, transaction của request đó có thể đã bị đánh dấu rollback-only. Hãy rollback transaction hiện tại rồi đọc kết quả đã lưu trong một transaction mới; không tiếp tục truy vấn hoặc ghi trong transaction đã hỏng.

### Ranh giới transaction của idempotency

Với tác động chỉ nằm trong cùng database, việc ghi nhận key, thay đổi nghiệp vụ và lưu kết quả nên được thiết kế nguyên tử trong một transaction phù hợp. Nếu transaction rollback, không được để lại trạng thái “đã hoàn tất” trong khi nghiệp vụ chưa được commit.

Với tác động bên ngoài như gọi cổng thanh toán, gửi email hoặc phát message, không thể dựa vào một transaction database để bảo đảm mọi hệ thống bên ngoài chỉ thực hiện đúng một lần. Có thể dùng transactional outbox, mã tham chiếu duy nhất và consumer deduplication. Hãy thiết kế retry an toàn ở từng ranh giới.

Không nên hứa hẹn “exactly once” tuyệt đối giữa nhiều hệ thống phân tán. Thực tế thường là giao nhận ít nhất một lần kết hợp idempotent processing và deduplication để đạt hiệu quả nghiệp vụ mong muốn.

## 6. PRG, retry và các HTTP response

Post/Redirect/Get (PRG) giúp refresh trang kết quả không gửi lại POST trong luồng trình duyệt thông thường. PRG không ngăn hai POST đến cùng lúc và không giải quyết timeout sau khi server đã commit.

Một số phản hồi thường gặp:

| Status | Ý nghĩa trong tình huống |
|---|---|
| `200 OK` | Đọc hoặc trả kết quả đã xử lý thành công |
| `201 Created` | Tạo tài nguyên thành công |
| `303 See Other` | Sau POST, trình duyệt tiếp tục bằng GET tới URL đích |
| `409 Conflict` | Xung đột trạng thái hoặc thao tác trùng không được chấp nhận |
| `412 Precondition Failed` | Điều kiện phiên bản/ETag của request không còn đúng |
| `422 Unprocessable Content` | Dữ liệu có cấu trúc hợp lệ nhưng không thể xử lý theo quy tắc ứng dụng, nếu API chọn quy ước này |

Khi client timeout, không nên mặc định gửi một POST mới với key mới. Client cần giữ cùng idempotency key cho cùng một ý định retry. Nếu key không được hỗ trợ, client nên truy vấn trạng thái tài nguyên hoặc hiển thị hướng dẫn kiểm tra trước khi thử lại.

## 7. Thiết kế kiểm thử cạnh tranh đáng tin cậy

Kiểm thử concurrency cần tạo ra sự chồng lấn có chủ đích. Không dùng `Thread.sleep()` để hy vọng hai luồng chạy đúng thời điểm; cách đó không ổn định giữa máy nhanh, máy chậm và CI.

Các công cụ đồng bộ phù hợp trong Java:

- `CountDownLatch`: chờ nhiều worker tới một điểm rồi cùng tiếp tục.
- `CyclicBarrier`: đồng bộ một nhóm worker tại cùng một mốc.
- `Phaser`: điều phối nhiều pha đồng bộ.
- `ExecutorService` hoặc virtual threads: chạy các request/task song song.
- Timeout trong `await` và `Future.get`: tránh test treo vô hạn.

Mỗi worker phải dùng transaction và persistence context riêng. Không chia sẻ một `EntityManager` hoặc một entity JPA mutable giữa các thread. Với test Spring, gọi application service qua proxy hoặc dùng `TransactionTemplate` trong từng worker để transaction thực sự được mở riêng.

### Kiểm thử optimistic locking với hai transaction

Giả sử entity có `@Version`. Mục tiêu là bảo đảm hai transaction cùng đọc một version, cùng cố ghi và chỉ một transaction thành công.

Fixture của test cần được commit trước khi chạy worker, với ghi chú ban đầu khác `updated` và version bằng 0. Như vậy cả hai transaction chắc chắn đọc cùng phiên bản và thao tác thay đổi tạo ra dirty state.

Ví dụ minh họa với JUnit, `TransactionTemplate` và các latch:

```java
@Test
void onlyOneConcurrentUpdateWins() throws Exception {
    CountDownLatch bothLoaded = new CountDownLatch(2);
    CountDownLatch allowWrite = new CountDownLatch(1);

    Callable<Boolean> updateTask = () -> {
        try {
            transactionTemplate.executeWithoutResult(status -> {
                Order order = orderRepository.findById(orderId)
                    .orElseThrow();

                bothLoaded.countDown();
                await(allowWrite);

                order.changeNote("updated");
                entityManager.flush();
            });
            return true;
        } catch (RuntimeException ex) {
            if (hasOptimisticLockCause(ex)) {
                return false;
            }
            throw ex;
        }
    };

    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
        Future<Boolean> first = pool.submit(updateTask);
        Future<Boolean> second = pool.submit(updateTask);

        assertTrue(bothLoaded.await(5, TimeUnit.SECONDS));
        allowWrite.countDown();

        boolean firstWon = first.get(10, TimeUnit.SECONDS);
        boolean secondWon = second.get(10, TimeUnit.SECONDS);

        assertNotEquals(firstWon, secondWon);
    } finally {
        allowWrite.countDown();
        pool.shutdownNow();
    }

    Order saved = orderRepository.findById(orderId).orElseThrow();
    assertEquals(1L, saved.getVersion());
    assertEquals("updated", saved.getNote());
}
```

Đây là khung kiểm thử cần điều chỉnh theo repository, transaction manager và entity của dự án. Hàm `await` phải có timeout và biến timeout thành lỗi test; `hasOptimisticLockCause` cần nhận diện exception gốc có thể được bọc bởi transaction layer. `EntityManager` được inject trong Spring thường là proxy gắn với transaction hiện tại; mỗi worker vẫn phải có transaction riêng.

Ví dụ hai helper có thể được viết như sau:

```java
private static void await(CountDownLatch latch) {
    try {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Timed out waiting for workers");
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Worker interrupted", ex);
    }
}

private static boolean hasOptimisticLockCause(Throwable error) {
    for (Throwable cause = error; cause != null; cause = cause.getCause()) {
        if (cause instanceof OptimisticLockException
                || cause instanceof ObjectOptimisticLockingFailureException) {
            return true;
        }
    }
    return false;
}
```

Điểm quan trọng của test:

1. Hai worker tải cùng bản ghi trước khi được phép ghi.
2. Latch bảo đảm cả hai đã đọc xong trước khi mở cổng ghi.
3. Mỗi worker flush trong transaction riêng để lỗi version xuất hiện sớm.
4. Một kết quả thành công và một kết quả xung đột được mong đợi.
5. Đọc lại sau khi cả hai transaction kết thúc để xác minh version và trạng thái cuối.

Connection pool của test phải có ít nhất hai connection khả dụng. Không để test method mở một transaction bao trùm toàn bộ test nếu các worker cần transaction độc lập; dữ liệu khởi tạo nên được commit trước khi chạy worker.

### Không khẳng định thứ tự thắng

Test không nên giả định worker A luôn thắng worker B. Scheduler và database quyết định thứ tự thực tế. Điều cần kiểm tra là chỉ một cập nhật được commit và cập nhật còn lại bị xử lý theo chính sách xung đột.

Nếu cả hai cập nhật đều có thể thành công theo nghiệp vụ, chẳng hạn hai thao tác cộng dồn được thiết kế nguyên tử, hãy kiểm tra kết quả tổng hợp mong đợi thay vì bắt buộc một worker thất bại.

## 8. Kiểm thử thao tác lặp với idempotency key

Với endpoint tạo payment, hãy gửi đồng thời hai request có cùng actor, operation, key và payload. Kết quả cần chứng minh:

- Chỉ có một payment nghiệp vụ được tạo.
- Tác động bên ngoài hoặc outbox event chỉ được tạo theo quy tắc một lần.
- Hai response có kết quả nhất quán theo hợp đồng.
- Request cùng key nhưng payload khác bị từ chối.
- Request với key khác đại diện ý định mới có thể tạo tài nguyên mới nếu nghiệp vụ cho phép.

Một bài kiểm thử tích hợp có thể dùng hai HTTP client hoặc hai task gọi application service. Dùng barrier để cả hai cùng bắt đầu; kiểm tra unique constraint và số bản ghi sau khi hoàn tất. Nếu test qua service, cần bảo đảm cả hai lời gọi đi qua transaction boundary thật.

Không chỉ mock repository để kiểm thử idempotency. Mock có thể xác minh nhánh xử lý nhưng không chứng minh unique constraint, transaction isolation hoặc hành vi khi hai insert cạnh tranh. Hãy có integration test chạy với database thật hoặc container của cùng hệ quản trị.

### Kiểm thử cùng key nhưng payload khác

```java
@Test
void rejectsReusingKeyForDifferentPayload() {
    PaymentResult first = paymentService.create(
        actorId, idempotencyKey, new CreatePaymentCommand(100_000)
    );

    assertThrows(IdempotencyPayloadMismatchException.class, () ->
        paymentService.create(
            actorId, idempotencyKey, new CreatePaymentCommand(200_000)
        )
    );

    assertEquals(1, paymentRepository.countByActorId(actorId));
}
```

Test này xác minh key gắn với payload đã chuẩn hóa. Cần bảo đảm count chỉ tính đúng phạm vi dữ liệu được tạo bởi test và transaction đầu tiên đã commit trước khi kiểm tra.

## 9. Kiểm thử atomic update và ràng buộc dữ liệu

Với tồn kho, test nên tạo hai request cùng đặt một đơn vị khi chỉ còn một đơn vị. Nếu dùng atomic update có điều kiện, chỉ một request nhận số hàng cập nhật bằng 1.

Các assertion quan trọng:

- Chỉ một reservation được tạo.
- `available` cuối cùng bằng 0, không âm.
- Request còn lại nhận kết quả hết hàng hoặc xung đột theo hợp đồng.
- Không có order/line nào được tạo dở dang nếu reservation thất bại.
- Transaction rollback toàn bộ phần ghi liên quan khi có lỗi.

Ngoài test đồng thời, cần test trực tiếp constraint bằng cách thử ghi dữ liệu vi phạm trong integration test. Constraint database là lớp bảo vệ cuối và không thể được xác minh chỉ bằng unit test Model.

## 10. Kiểm thử ở các tầng MVC

Không phải mọi loại test đều cần chạy song song. Chọn tầng kiểm thử theo hành vi cần chứng minh:

| Tầng | Điều cần kiểm tra | Công cụ/gợi ý |
|---|---|---|
| Unit test Model | Bất biến, trạng thái hợp lệ, hành động lặp theo quy tắc miền | JUnit, assertion |
| Unit test policy/service | Quyền và orchestration | Mockito khi phù hợp |
| Repository integration | `@Version`, lock, unique/check constraint, atomic query | Spring Boot Test, Testcontainers |
| Application service concurrency | Hai transaction thật cùng cập nhật | ExecutorService, latch/barrier |
| Controller test | Mapping lỗi thành `409`, `412`, redirect hoặc response đúng | MockMvc |
| HTTP integration | Hai request thực cùng đi qua security, filter và transaction | Test server + HTTP client |
| End-to-end | Người dùng nhấn lặp, hai tab và phản hồi khi xung đột | Browser automation |

### Kiểm thử Controller cho conflict

MockMvc có thể xác minh exception được ánh xạ đúng:

```java
mockMvc.perform(post("/api/orders/{id}/confirm", orderId)
        .with(user("employee"))
        .with(csrf()))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$.code").value("CONCURRENT_UPDATE"));
```

Ví dụ này giả định service được cấu hình để ném lỗi xung đột. Nó kiểm tra hợp đồng HTTP; nó không chứng minh race condition thực sự xảy ra. Phần đó cần test ở application service/repository với transaction và database thực.

### Kiểm thử hành vi giao diện

Ở browser test, có thể kiểm tra:

- Nút chuyển sang trạng thái đang gửi sau lần nhấn đầu.
- Người dùng được thông báo khi server trả xung đột.
- Dữ liệu mới được tải lại trước khi người dùng thử lại.
- Client giữ nguyên idempotency key khi retry cùng ý định.
- Client tạo key mới khi người dùng bắt đầu một ý định nghiệp vụ mới.

Không coi việc nút bị disable là bằng chứng thao tác chỉ chạy một lần. Browser test cần quan sát số request và trạng thái cuối ở server.

## 11. Chọn database test phù hợp

Locking, isolation, unique constraint và câu lệnh atomic có thể khác nhau giữa hệ quản trị. H2 in-memory tiện cho test nhanh nhưng không đảm bảo mô phỏng đúng PostgreSQL, MySQL, SQL Server hoặc Oracle trong mọi tình huống.

Với test phụ thuộc hành vi database:

- Dùng Testcontainers chạy đúng engine và phiên bản gần môi trường triển khai.
- Dùng schema migration giống ứng dụng thực tế.
- Không dùng transaction bao ngoài test nếu nó khiến worker không nhìn thấy dữ liệu đã tạo.
- Cấu hình connection pool đủ cho số transaction chạy đồng thời.
- Đặt timeout rõ ràng để phát hiện deadlock hoặc test treo.
- Dọn dữ liệu sau test bằng cách cô lập schema/database hoặc xóa theo ID test.

Testcontainers làm test chậm hơn unit test nhưng cung cấp bằng chứng phù hợp hơn cho các thuộc tính phụ thuộc database. Có thể chạy số lượng test tích hợp vừa đủ trong CI và giữ phần lớn logic nghiệp vụ ở unit test nhanh.

## 12. Tránh kiểm thử concurrency không ổn định

Một số lỗi thường làm test chập chờn:

- Dùng `Thread.sleep()` để đoán thời điểm hai luồng cùng đọc dữ liệu.
- Dùng chung entity hoặc EntityManager giữa các thread.
- Chạy hai task nhưng vô tình dùng chung một transaction.
- Không flush nên xung đột chỉ xuất hiện sau khi test đã kết thúc phần assertion.
- Dùng database in-memory khác với production cho lock semantics.
- Chỉ assert status HTTP mà không kiểm tra số bản ghi và bất biến.
- Giả định một thread cụ thể luôn thắng.
- Không giải phóng latch trong `finally`, khiến worker bị treo khi assertion thất bại.
- Chỉ chạy test một lần; không chạy lặp trong CI để phát hiện tính không ổn định.

Hãy đồng bộ tại một điểm có ý nghĩa trong luồng, dùng timeout hữu hạn và kiểm tra trạng thái cuối sau khi tất cả worker đã kết thúc.

## 13. Kiểm thử deadlock, lock timeout và retry

Nếu transaction lấy nhiều khóa theo thứ tự khác nhau, có thể xảy ra deadlock. Ví dụ transaction A khóa bản ghi X rồi Y, trong khi B khóa Y rồi X. Database thường chọn một transaction làm nạn nhân và rollback.

Kiểm thử cần xác minh:

- Deadlock hoặc lock timeout được nhận diện và chuyển thành lỗi phù hợp.
- Transaction bị rollback hoàn toàn.
- Retry chỉ thực hiện với lỗi có thể retry và có giới hạn số lần.
- Mỗi lần retry bắt đầu transaction mới.
- Không retry mù quáng thao tác không idempotent.
- Người dùng nhận phản hồi có thể hành động, chẳng hạn thử lại sau hoặc tải dữ liệu mới.

Không nên giữ transaction mở trong lúc chờ người dùng hoặc gọi dịch vụ mạng. Điều đó kéo dài thời gian giữ khóa và làm tăng nguy cơ contention.

## 14. Các tình huống kiểm thử cần có

| Kịch bản | Kết quả mong đợi |
|---|---|
| Hai người sửa cùng version | Một cập nhật thành công, cập nhật còn lại nhận conflict |
| Hai thao tác cùng đặt đơn vị tồn cuối | Chỉ một reservation thành công, tồn kho không âm |
| Cùng idempotency key và payload đồng thời | Một tác động nghiệp vụ, kết quả được trả nhất quán |
| Cùng key nhưng payload khác | Từ chối request thứ hai |
| Hai key khác nhau cho hai ý định mới | Cả hai có thể thành công nếu nghiệp vụ cho phép |
| Client retry sau timeout | Không tạo tác động trùng |
| Hai request xác nhận cùng một đơn | Trạng thái cuối hợp lệ, side effect không lặp |
| Unique reference được insert đồng thời | Database chỉ chấp nhận một giá trị duy nhất |
| Transaction lỗi sau khi cập nhật một phần | Rollback toàn bộ thay đổi trong transaction |
| Deadlock/lock timeout | Lỗi được xử lý, không để lại dữ liệu dở dang |
| Client gửi version cũ | Server trả conflict/precondition failure theo hợp đồng |
| Request không đủ quyền | Không có thay đổi dữ liệu dù request hợp lệ về cấu trúc |

## 15. Checklist thiết kế và kiểm thử

- Đã viết rõ bất biến dữ liệu cần giữ khi có nhiều request chưa?
- Đã phân biệt xung đột cập nhật với gửi lặp cùng một ý định chưa?
- Cơ chế optimistic lock, pessimistic lock, atomic update hay constraint có phù hợp không?
- Transaction có ngắn và giữ đúng ranh giới ghi không?
- Có unique/check constraint bảo vệ những bất biến quan trọng không?
- Thao tác có tác động phụ đã có idempotency key hoặc cơ chế deduplication chưa?
- Cùng key nhưng payload khác có bị từ chối không?
- Client có giữ key khi retry cùng ý định không?
- Kiểm thử có dùng transaction và persistence context riêng cho từng worker không?
- Có dùng latch/barrier thay cho sleep để đồng bộ test không?
- Có kiểm tra số bản ghi, version, tồn kho và side effect sau khi tất cả worker kết thúc không?
- Integration test có chạy trên database tương đương môi trường triển khai không?
- Controller/API có trả conflict và thông báo nhất quán không?
- Có kiểm thử cả retry, timeout, deadlock và rollback không?

## Kết luận

Kiểm thử cạnh tranh cập nhật và thao tác lặp phải chứng minh tính đúng đắn của dữ liệu khi nhiều request cùng đến, kể cả khi trình duyệt hoặc client retry. Optimistic locking phát hiện ghi đè dựa trên version; pessimistic locking tuần tự hóa truy cập khi cần; atomic update và constraint bảo vệ bất biến tại database; idempotency key ngăn cùng một ý định tạo tác động nhiều lần. Hãy dùng transaction riêng, latch hoặc barrier để tạo cạnh tranh có kiểm soát, rồi kiểm tra trạng thái và side effect cuối cùng. MockMvc xác minh hợp đồng HTTP, còn integration test trên database phù hợp mới chứng minh được locking và constraint hoạt động như dự kiến.
