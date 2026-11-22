# Kiểm thử yêu cầu trùng và tính lũy đẳng

Trong hệ thống có retry, một request có thể được gửi nhiều lần dù người dùng chỉ tạo một yêu cầu nghiệp vụ. Server có thể đã commit nhưng phản hồi bị mất; client timeout rồi gửi lại; message broker có thể giao lại event; hoặc transaction bị deadlock và ứng dụng chạy lại toàn bộ thao tác. Nếu mỗi lần thực thi tạo ra một hiệu ứng mới, hệ thống có thể tạo hai đơn hàng, trừ tiền hai lần hoặc gửi thông báo lặp.

Kiểm thử tính lũy đẳng (idempotency) phải chứng minh rằng nhiều lần gửi cùng một ý định nghiệp vụ tạo ra **một hiệu ứng nghiệp vụ duy nhất**, kể cả khi các request đến đồng thời hoặc kết quả lần đầu không rõ ràng. Bài kiểm thử cần xác nhận cả hành vi API, ràng buộc database, xử lý transaction và các side effect ngoài database.

## 1. Xác định điều gì phải được bảo vệ

Trước khi viết test, hãy mô tả rõ hợp đồng idempotency của thao tác. Ví dụ API tạo thanh toán:

```http
POST /payments
Idempotency-Key: 9f2c1a1e-7b6a-4d7c-a3c0-4d8f8a2e7c11
Content-Type: application/json

{
  "orderId": "ORD-125",
  "amount": 500000,
  "currency": "VND"
}
```

Nếu client gửi lại cùng key và cùng nội dung, API phải nhận diện đó là cùng một ý định. Kết quả có thể được phát lại từ lần đầu hoặc API có thể trả trạng thái đang xử lý theo hợp đồng đã định nghĩa. Nếu cùng key được dùng với payload khác, API phải từ chối việc tái sử dụng key sai mục đích.

Một test nên xác định trước các điều kiện quan sát được:

- Chỉ có một payment/order nghiệp vụ được tạo cho key trong phạm vi đã quy định.
- Số tiền, đơn hàng và các thuộc tính nghiệp vụ khớp với request ban đầu.
- Các lần gửi lại cùng payload nhận cùng resource ID hoặc cùng kết quả nghiệp vụ đã lưu.
- Request cùng key nhưng khác payload không tạo thêm hiệu ứng và trả lỗi xung đột phù hợp.
- Nếu transaction đầu rollback trước commit, request cạnh tranh có thể trở thành request xử lý thành công.
- Side effect như phát event hoặc gọi nhà cung cấp thanh toán không bị lặp ngoài ý muốn.

Đừng chỉ kiểm tra HTTP status. Hai response đều `200 OK` không chứng minh database chỉ có một payment. Ngược lại, lần đầu trả `201 Created` và lần retry trả `200 OK` vẫn có thể đúng nếu cả hai đại diện cho cùng một payment.

## 2. Phân loại các tình huống cần kiểm thử

| Tình huống | Điều cần chứng minh |
|---|---|
| Cùng key, cùng payload, gửi tuần tự | Lần sau phát lại kết quả; không tạo hiệu ứng mới |
| Cùng key, cùng payload, gửi đồng thời | UNIQUE constraint/logic claim chỉ cho một lần xử lý hiệu quả |
| Cùng key, payload khác | Phát hiện fingerprint không khớp và từ chối request |
| Khác key, cùng payload | Hai yêu cầu độc lập được xử lý theo nghiệp vụ; không tự gộp chỉ vì body giống nhau |
| Transaction đầu commit nhưng response bị mất | Retry tìm được kết quả đã commit |
| Transaction đầu rollback trước commit | Request sau có thể chiếm key và xử lý |
| Request đến khi trạng thái đang xử lý | API trả trạng thái đang xử lý hoặc chờ theo hợp đồng; không chạy side effect lần hai |
| Message được giao lại | Consumer chỉ áp dụng hiệu ứng database một lần cho cùng event ID |
| Worker chết sau publish nhưng trước ACK/đánh dấu hoàn tất | Event có thể được gửi lại nhưng consumer deduplicate |
| Key hết thời hạn lưu | Hành vi khớp chính sách retention và ràng buộc nghiệp vụ dài hạn |

Các test này nên được chia thành unit test, integration test với database thật, API test và test cho luồng message. Không cần ép mọi trường hợp vào một test lớn khó chẩn đoán.

## 3. Kiểm thử cùng key và cùng payload theo cách tuần tự

Đây là test nền tảng, xác nhận logic phát lại kết quả trước khi kiểm tra cạnh tranh.

Quy trình:

1. Tạo một idempotency key mới.
2. Gửi request tạo payment lần đầu.
3. Ghi lại payment ID và response nghiệp vụ.
4. Gửi lại cùng key, cùng payload một hoặc nhiều lần.
5. Đọc database và xác nhận chỉ có một payment.
6. So sánh kết quả của các lần gọi.

Ví dụ pseudocode Java/JUnit:

```java
@Test
void replaysResultForSameKeyAndPayload() {
    String key = UUID.randomUUID().toString();
    CreatePaymentRequest request =
        new CreatePaymentRequest("ORD-125", 500_000, "VND");

    PaymentResponse first = paymentClient.create(key, request);
    PaymentResponse second = paymentClient.create(key, request);
    PaymentResponse third = paymentClient.create(key, request);

    assertThat(second.paymentId()).isEqualTo(first.paymentId());
    assertThat(third.paymentId()).isEqualTo(first.paymentId());
    assertThat(paymentRepository.countByOrderId("ORD-125")).isEqualTo(1);
    assertThat(idempotencyRepository.countByKey(key)).isEqualTo(1);
}
```

Đoạn code chỉ minh họa cấu trúc test; tên class và repository tùy dự án. Nếu nghiệp vụ cho phép nhiều payment attempt cho một order, assertion phải đếm theo idempotency key hoặc payment attempt thay vì giả định toàn bộ order chỉ có một payment.

### Kiểm tra response nào?

Nên so sánh những trường thuộc kết quả nghiệp vụ:

- `paymentId` hoặc `orderId`.
- `status` cuối cùng.
- `amount`, `currency` và định danh giao dịch.
- Mã kết quả hoặc response body đã được API cam kết phát lại.

Không nhất thiết phải so sánh timestamp xử lý request, request ID của từng HTTP call hoặc header tracing vì chúng có thể khác giữa các lần gọi. Hợp đồng API phải nói rõ trường nào được phát lại và trường nào được tạo mới cho mỗi lần truyền.

## 4. Kiểm thử cùng key nhưng payload khác

Một idempotency key đại diện cho một ý định nghiệp vụ. Nếu key đã được dùng cho `ORD-125`, request tiếp theo không được dùng lại key đó để tạo `ORD-126` hoặc thay đổi số tiền.

Ví dụ:

```java
@Test
void rejectsDifferentPayloadForSameKey() {
    String key = UUID.randomUUID().toString();

    paymentClient.create(
        key,
        new CreatePaymentRequest("ORD-125", 500_000, "VND")
    );

    ApiException error = catchThrowableOfType(
        () -> paymentClient.create(
            key,
            new CreatePaymentRequest("ORD-126", 900_000, "VND")
        ),
        ApiException.class
    );

    assertThat(error.statusCode()).isEqualTo(409);
    assertThat(paymentRepository.count()).isEqualTo(1);
}
```

Test cần xác nhận:

- Server so sánh fingerprint của payload đã chuẩn hóa.
- Request không khớp bị từ chối theo hợp đồng, thường là `409 Conflict`.
- Không có payment thứ hai.
- Kết quả gốc không bị ghi đè.

Nên có test cho những khác biệt có ý nghĩa và không có ý nghĩa. Ví dụ, nếu thứ tự thuộc tính JSON hoặc khoảng trắng không làm thay đổi nội dung, hai payload đó có thể được chuẩn hóa thành cùng fingerprint. Ngược lại, thay đổi `amount`, `currency`, `orderId` hoặc trường ảnh hưởng nghiệp vụ phải làm fingerprint khác.

## 5. Kiểm thử key khác nhau nhưng payload giống nhau

Không nên vô tình gộp hai yêu cầu độc lập chỉ vì body giống nhau. Nếu khách hàng thật sự tạo hai ý định thanh toán riêng biệt với hai key khác nhau, hệ thống phải áp dụng quy tắc nghiệp vụ tương ứng.

```java
@Test
void differentKeysRepresentDifferentRequests() {
    CreatePaymentRequest request =
        new CreatePaymentRequest("ORD-125", 500_000, "VND");

    PaymentResponse first = paymentClient.create(
        UUID.randomUUID().toString(), request);
    PaymentResponse second = paymentClient.create(
        UUID.randomUUID().toString(), request);

    assertThat(first.paymentId()).isNotEqualTo(second.paymentId());
}
```

Assertion cụ thể phụ thuộc nghiệp vụ. Nếu hệ thống có `UNIQUE(order_id)` và không cho thanh toán một order lần hai, request thứ hai có thể bị từ chối bởi constraint nghiệp vụ khác. Mục tiêu của test là phân biệt hai lớp bảo vệ: idempotency key nhận diện retry của cùng request; constraint trên order/payment bảo vệ quy tắc “một order chỉ có một payment” nếu quy tắc đó tồn tại.

## 6. Kiểm thử hai request cùng key đến đồng thời

Đây là test quan trọng nhất cho tính lũy đẳng trong môi trường concurrent. Hai request cùng key phải thực sự chạy qua hai transaction và hai kết nối database độc lập.

### Dùng barrier để bắt đầu cùng lúc

Có thể dùng `CyclicBarrier` hoặc `CountDownLatch` để đồng bộ các thread trước khi gọi service:

```java
@Test
void concurrentRequestsWithSameKeyCreateOnePayment() throws Exception {
    String key = UUID.randomUUID().toString();
    CreatePaymentRequest request =
        new CreatePaymentRequest("ORD-125", 500_000, "VND");

    int workers = 2;
    ExecutorService pool = Executors.newFixedThreadPool(workers);
    CountDownLatch ready = new CountDownLatch(workers);
    CountDownLatch start = new CountDownLatch(1);

    try {
        List<Future<PaymentResponse>> futures = new ArrayList<>();

        for (int i = 0; i < workers; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();
                start.await();
                return paymentService.create(key, request);
            }));
        }

        assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
        start.countDown();

        PaymentResponse first = futures.get(0).get(10, TimeUnit.SECONDS);
        PaymentResponse second = futures.get(1).get(10, TimeUnit.SECONDS);

        assertThat(first.paymentId()).isEqualTo(second.paymentId());
        assertThat(paymentRepository.countByOrderId("ORD-125")).isEqualTo(1);
        assertThat(idempotencyRepository.countByKey(key)).isEqualTo(1);
    } finally {
        start.countDown();
        pool.shutdownNow();
        assertThat(pool.awaitTermination(5, TimeUnit.SECONDS)).isTrue();
    }
}
```

Barrier chỉ đồng bộ thời điểm bắt đầu, không bảo đảm tuyệt đối hai thread cùng chạm vào câu INSERT ở cùng một nano giây. Nó vẫn hữu ích để tạo cạnh tranh lặp lại mà không dựa vào `Thread.sleep`. Để kiểm soát chính xác hơn, có thể đặt một test hook hoặc latch ở ranh giới repository sau khi transaction thứ nhất đã claim key nhưng trước commit, rồi cho request thứ hai đi vào. Hook chỉ dùng trong test và phải được tháo khỏi đường chạy production.

### Điều cần bảo đảm trong test

- Mỗi thread dùng một transaction riêng và một connection riêng.
- Không chia sẻ một EntityManager/session không thread-safe giữa các thread.
- Test không chạy trong transaction bao ngoài của test framework nếu các thread cần commit độc lập.
- Connection pool phải đủ connection cho các worker, nếu không test có thể chờ ở pool thay vì kiểm tra lock cạnh tranh.
- Có timeout cho `Future.get` và `await` để test không treo vô hạn.
- Dùng key mới cho mỗi lần chạy để dữ liệu của test trước không làm thay đổi kết quả.

Với Spring Test, một transaction được mở bởi `@Transactional` trên test thread không tự lan sang các thread trong `ExecutorService`. Test concurrent thường nên để mỗi lời gọi service tự mở transaction qua transaction manager, rồi truy vấn kết quả sau khi các Future hoàn tất.

## 7. Kiểm thử tình huống request đầu rollback

Nếu transaction đầu đã claim key nhưng rollback trước commit, request thứ hai phải có cơ hội thực hiện thao tác. Điều này kiểm tra rằng một key không bị giữ vĩnh viễn bởi một transaction thất bại.

Thiết kế test có thể dùng một hook trong service/repository:

1. T1 bắt đầu transaction và insert idempotency record.
2. T1 dừng tại test hook trước khi tạo payment/commit.
3. T2 gửi cùng key và chờ xung đột unique.
4. Test cho T1 ném exception để rollback.
5. T2 tiếp tục, insert key và tạo payment.
6. Xác nhận T2 thành công và chỉ có một payment.

```text
T1: INSERT key K ── test hook ── ROLLBACK
                         │
T2: INSERT key K ────────┴── chờ ── insert thành công
                                      tạo payment
                                      COMMIT
```

Test này đặc biệt quan trọng nếu implementation dựa vào unique index để điều phối cạnh tranh. Nếu T1 rollback, DBMS phải bỏ claim chưa commit để T2 có thể tiếp tục.

Không nên dùng `sleep(500)` để hy vọng T2 đã chờ ở đúng vị trí. Dùng latch, barrier hoặc tín hiệu test hook để xác định trạng thái. Đồng thời, hook phải bảo đảm được giải phóng trong `finally`, kể cả khi assertion thất bại.

## 8. Kiểm thử timeout sau commit nhưng trước response

Đây là tình huống thường gây thanh toán lặp trong thực tế:

1. Server tạo payment và lưu idempotency response.
2. Database commit thành công.
3. Một lỗi giả lập làm mất response trước khi client nhận được.
4. Client gửi lại cùng key và payload.
5. Server trả lại payment đã tồn tại.

Nên đặt fault injection ở ranh giới **sau khi transaction commit nhưng trước khi HTTP response được gửi**. Có thể dùng một decorator, interceptor hoặc test-only hook để lần gọi đầu ném lỗi mô phỏng mất kết nối sau commit.

Assertions:

- Lần đầu phía client thấy timeout hoặc lỗi truyền tải.
- Database vẫn có một payment đã commit.
- Request retry cùng key nhận lại cùng payment ID.
- Số payment và số idempotency record vẫn bằng một.
- Các event nghiệp vụ chỉ có một event ID logic cho payment đó.

Không nên giả lập timeout bằng cách làm transaction rollback. Hai tình huống khác nhau: timeout có thể xảy ra sau commit, trong khi rollback nghĩa là thay đổi chưa được xác nhận. Test cần kiểm tra cả hai.

## 9. Kiểm thử lỗi trước commit và sau commit

Một test fault-injection có thể đặt lỗi ở các điểm khác nhau của transaction:

| Điểm phát sinh lỗi | Trạng thái mong đợi |
|---|---|
| Trước khi insert idempotency record | Không có record, không có payment |
| Sau insert key nhưng trước insert payment | Rollback cả key và thay đổi nghiệp vụ |
| Sau insert payment nhưng trước lưu response | Rollback cả payment và key nếu cùng transaction |
| Sau lưu response nhưng trước commit | Rollback toàn bộ transaction |
| Sau commit nhưng trước HTTP response | Record và payment tồn tại; retry phát lại kết quả |
| Sau commit nhưng trước ACK message | Message có thể giao lại; consumer deduplicate |

Với mô hình atomic transaction, các lỗi trước commit phải để lại trạng thái như chưa xử lý. Lỗi sau commit không được làm mất dấu vết idempotency. Hai nhóm test này giúp xác nhận ranh giới nguyên tử được đặt đúng.

## 10. Kiểm thử UNIQUE constraint ở database thật

Unit test với mock repository có thể xác nhận nhánh code xử lý duplicate key, nhưng không chứng minh unique index thật sự điều phối hai transaction đồng thời. Cần integration test với cùng loại DBMS và phiên bản phù hợp với môi trường triển khai.

Ví dụ DDL:

```sql
CREATE TABLE idempotency_requests (
    tenant_id BIGINT NOT NULL,
    operation_name VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(120) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL,
    response_body TEXT,
    CONSTRAINT uq_idempotency_key
        UNIQUE (tenant_id, operation_name, idempotency_key)
);
```

Integration test nên xác nhận:

- Hai insert cùng key không thể cùng commit thành hai record.
- Một transaction đang insert key chưa commit có thể làm transaction thứ hai chờ.
- Nếu transaction đầu commit, transaction thứ hai xử lý duplicate theo thiết kế.
- Nếu transaction đầu rollback, transaction thứ hai có thể insert thành công.
- Unique scope hoạt động đúng theo tenant và operation.
- `NULL`, collation, case sensitivity hoặc composite key tuân theo cấu hình thực tế nếu những yếu tố đó thuộc nghiệp vụ.

### Dùng Testcontainers

Với Java, Testcontainers có thể khởi động database thật cho integration test. Ví dụ có thể dùng PostgreSQL container nếu production chạy PostgreSQL. Test nên khởi tạo schema và unique constraint thực tế, sau đó dùng nhiều connection để chạy cạnh tranh.

H2 hoặc database in-memory khác hữu ích cho test nhanh, nhưng không nên là bằng chứng duy nhất cho concurrency. Locking, unique-index conflict, isolation level và error code có thể khác DBMS. Testcontainers cũng không thay thế test trên cấu hình production nếu production dùng extension, isolation hoặc tính năng đặc thù.

## 11. Kiểm thử mã lỗi và trạng thái transaction

Khi cùng key bị chèn trùng, database có thể trả duplicate-key error; khi dùng `ON CONFLICT DO NOTHING`, repository có thể nhận kết quả không có hàng được insert. Khi serialization hoặc deadlock xảy ra, transaction có thể chuyển sang trạng thái lỗi.

Test cần xác nhận ứng dụng phân loại đúng lỗi:

| Tình huống database | Hành vi ứng dụng cần kiểm tra |
|---|---|
| Unique conflict cùng key, cùng hash | Đọc record hiện có và phát lại kết quả hoặc báo đang xử lý |
| Unique conflict cùng key, khác hash | Trả lỗi xung đột payload |
| Unique conflict trên business key khác | Xử lý đúng quy tắc nghiệp vụ riêng, không nhầm với idempotency replay |
| Deadlock victim | Rollback và retry toàn bộ transaction theo giới hạn |
| Serialization failure | Transaction mới, snapshot mới, đọc và kiểm tra lại |
| Connection lost sau commit | Retry cùng key và tra cứu kết quả đã commit |

Không nên bắt mọi `DataIntegrityViolationException` rồi coi là request lặp. Một lỗi unique trên `email`, `order_id` hoặc khóa ngoại có ý nghĩa khác với unique conflict trên `idempotency_key`. Hãy phân biệt constraint hoặc SQLSTATE/error code cụ thể.

## 12. Kiểm thử outbox và consumer deduplication

Nếu thao tác tạo payment còn phát `PaymentCreated`, cần kiểm thử cả outbox và consumer.

### Kiểm thử outbox

- Payment và outbox event được insert trong cùng transaction.
- Nếu transaction rollback, cả payment và outbox event đều không tồn tại.
- Nếu transaction commit, có một event logic cho payment.
- Retry cùng idempotency key không tạo thêm payment event.

### Kiểm thử consumer nhận message lặp

Giả lập broker giao cùng `event_id` hai lần:

```text
Message 1: event_id = EVT-9001
Message 2: event_id = EVT-9001 (redelivery)
```

Consumer nên insert `event_id` vào bảng inbox có unique constraint và cập nhật dữ liệu nghiệp vụ trong cùng transaction. Sau hai lần giao, số hiệu ứng nghiệp vụ vẫn bằng một.

### Kiểm thử crash sau khi xử lý nhưng trước ACK

Đây là cửa sổ lỗi quan trọng:

1. Consumer nhận event.
2. Consumer insert inbox và cập nhật dữ liệu.
3. Transaction commit.
4. Consumer chết trước khi ACK broker.
5. Broker giao lại event.
6. Consumer thấy event ID đã được xử lý và bỏ qua hiệu ứng lần hai.

Nếu consumer ACK trước khi commit database, crash có thể làm mất event mà không có thay đổi nghiệp vụ. Nếu commit xong nhưng ACK thất bại, redelivery là bình thường; inbox phải xử lý được trường hợp này.

## 13. Kiểm thử nhà cung cấp ngoài và side effect

Database không thể rollback email, SMS hoặc khoản thanh toán đã được nhà cung cấp xử lý. Nếu service gọi nhà cung cấp ngoài, cần test ranh giới đó riêng.

Với payment provider hỗ trợ idempotency:

- Hai lần gọi cùng payment intent dùng cùng provider idempotency key.
- Timeout sau khi provider đã xử lý rồi retry không tạo charge thứ hai.
- Cùng provider key nhưng payload khác bị từ chối theo hợp đồng của provider.
- Key nội bộ được ánh xạ nhất quán sang key của provider.
- Hệ thống có cách truy vấn/reconcile trạng thái nếu kết quả call không rõ.

Mock server có thể kiểm tra ứng dụng truyền đúng key và xử lý response. Nhưng để chứng minh hành vi của nhà cung cấp, cần sandbox hoặc contract test với API provider; mock không thể chứng minh server ngoài thật sự deduplicate.

Với email/SMS provider không hỗ trợ idempotency, test phải thừa nhận giới hạn: worker có thể gửi lại nếu mất phản hồi sau khi provider nhận request. Có thể giảm rủi ro bằng outbox, deduplication nội bộ, trạng thái gửi và đối soát, nhưng không nên tuyên bố đảm bảo gửi đúng một lần nếu nhà cung cấp không có cơ chế tương ứng.

## 14. Kiểm thử trạng thái PROCESSING và phục hồi lease

Nếu xử lý ngắn trong một transaction, request trùng key thường chờ transaction đầu kết thúc rồi đọc kết quả. Nếu hệ thống commit trạng thái `PROCESSING` để worker xử lý nhiều bước, cần kiểm thử thêm:

- Request trùng key khi job còn `PROCESSING` nhận phản hồi đúng hợp đồng, chẳng hạn `202 Accepted` hoặc trạng thái đang chạy.
- Hai worker không thể cùng claim một job đang còn lease hợp lệ.
- Worker sở hữu job có thể gia hạn lease theo cơ chế nguyên tử.
- Worker chết, lease hết hạn và job được claim lại.
- Worker cũ quay lại sau khi lease đã hết không được ghi đè kết quả của owner mới; có thể dùng fencing token hoặc version tăng dần.
- Khi job hoàn tất, mọi request cùng key nhận cùng kết quả cuối.
- Lỗi cuối cùng được phân biệt với lỗi có thể retry.

Không nên chỉ test đường thành công của `PROCESSING`. Phục hồi sau worker crash và cạnh tranh claim mới là nơi dễ tạo hai side effect nhất.

## 15. Kiểm thử tải và lặp lại ngẫu nhiên

Sau các test xác định, có thể chạy stress test với nhiều request cùng key để tăng xác suất phát hiện race condition.

Ví dụ test mục tiêu:

```text
Số worker: 20
Số lần gửi: 100
Idempotency key: một key chung
Payload: giống nhau

Kỳ vọng:
  - Mọi response thành công hoặc replay cùng payment ID
  - Một payment record
  - Một idempotency record
  - Một event logic trong outbox
```

Sau đó chạy một nhóm khác với nhiều key độc lập để bảo đảm hệ thống không vô tình tuần tự hóa tất cả request hoặc dùng nhầm phạm vi key.

Stress test bổ sung cho test deterministic nhưng không thay thế nó. Một race hiếm có thể không xuất hiện trong 100 lần chạy; test cần điều khiển điểm đồng bộ để tái hiện cửa sổ cạnh tranh một cách ổn định.

### Chỉ số nên quan sát

- Số request nhận lần đầu, số replay và số payload conflict.
- Số payment/order thực tế được tạo.
- Số duplicate-key conflict và serialization/deadlock retry.
- Số event được ghi vào outbox và số lần consumer nhận lại.
- Thời gian chờ unique index/row lock và latency p95/p99.
- Số job `PROCESSING` quá hạn hoặc lease hết hạn.

Log và metric không thay thế assertion trong test, nhưng giúp giải thích vì sao test tải thất bại hoặc vì sao hệ thống chậm khi nhiều request cùng key.

## 16. Tránh test concurrency không ổn định

Test đồng thời dễ flaky nếu phụ thuộc vào thời gian lập lịch thread hoặc tốc độ máy. Một số nguyên tắc:

- Dùng `CountDownLatch`, `CyclicBarrier` hoặc test hook thay cho `Thread.sleep` để điều khiển thứ tự.
- Dùng database thật và connection riêng cho mỗi transaction cạnh tranh.
- Không chia sẻ session/EntityManager giữa các thread.
- Đặt timeout hữu hạn cho latch, future và test tổng thể.
- Giải phóng latch và shutdown executor trong `finally`.
- Tạo key và dữ liệu riêng cho từng test; tránh test phụ thuộc thứ tự chạy.
- Không dùng một transaction bao ngoài cho test mà các thread con phải nhìn thấy commit độc lập.
- Chờ mọi Future hoàn tất trước khi truy vấn assertion cuối cùng.
- Khi test thất bại, ghi nhận SQLSTATE, transaction ID và log lock nếu có thể, nhưng không biến log thành điều kiện duy nhất để pass.

Nếu cần xác nhận T2 thật sự đang chờ unique conflict, test hook nên phát tín hiệu ngay trước hoặc sau điểm claim có kiểm soát. Hook phải chỉ tồn tại trong cấu hình test; không đưa latch hoặc sleep vào production code.

## 17. Bộ test mẫu theo tầng

| Tầng test | Phạm vi | Ví dụ assertion |
|---|---|---|
| Unit | Chuẩn hóa request, tạo fingerprint, phân loại trạng thái | Payload tương đương có hash giống; payload nghiệp vụ khác có hash khác |
| Repository integration | UNIQUE constraint, insert conflict, transaction rollback | Hai insert cùng key không thể cùng commit |
| Service integration | Claim key, tạo payment, lưu response trong transaction | Chỉ một payment và một idempotency record |
| Concurrent integration | Nhiều transaction cùng key | Các response cùng resource ID; không có hiệu ứng trùng |
| API integration | Timeout, replay, payload mismatch, trạng thái PROCESSING | Status/body đúng hợp đồng; không tạo tài nguyên mới |
| Outbox/consumer integration | Publish, redelivery, inbox | Một hiệu ứng database dù event giao nhiều lần |
| Provider contract/sandbox | Idempotency của dịch vụ ngoài | Cùng provider key không tạo charge thứ hai |
| Load/resilience | Retry đồng thời, lỗi tạm thời, crash injection | Không vi phạm invariant dưới tải và phục hồi |

Một pipeline có thể chạy unit test nhanh ở mọi commit, integration test database trong CI, và stress/resilience test ở lịch riêng hoặc môi trường staging. Những test có thể gây tải lớn hoặc cần sandbox ngoài nên được tách khỏi bộ test nhanh.

## 18. Checklist assertion cho một payment idempotent

Với một thao tác thanh toán, sau mỗi kịch bản test quan trọng hãy xác nhận trạng thái ở nhiều lớp:

| Lớp | Điều cần kiểm tra |
|---|---|
| API | Response, mã lỗi và resource ID đúng hợp đồng |
| Idempotency table | Một record cho phạm vi key; request hash và trạng thái đúng |
| Payment table | Một payment logic, đúng order và amount |
| Ledger | Không có hai bút toán ghi nợ cho cùng payment intent |
| Outbox | Một event logic cho payment đã commit |
| Consumer inbox | Event ID chỉ được áp dụng một lần |
| Provider | Provider key được giữ ổn định qua retry; trạng thái được đối soát |
| Retry | Cùng key được giữ nguyên; lỗi nghiệp vụ không bị retry vô hạn |

Nếu payment table chỉ có một hàng nhưng ledger ghi nợ hai lần, test vẫn phải thất bại. Tính lũy đẳng cần được kiểm tra tại nơi tạo ra hiệu ứng nghiệp vụ cuối cùng, không chỉ tại bảng lưu key.

## 19. Những lỗi kiểm thử thường gặp

| Lỗi trong test | Vì sao chưa đủ | Cách cải thiện |
|---|---|---|
| Chỉ gọi API hai lần tuần tự | Không tạo cạnh tranh giữa transaction | Thêm test concurrent với connection riêng |
| Chỉ assert status code | Hai request có thể đều thành công nhưng tạo hai hàng | Đếm hiệu ứng nghiệp vụ và so sánh resource ID |
| Mock repository hoàn toàn | Không kiểm tra UNIQUE index hoặc locking thật | Thêm integration test với DBMS thật |
| Dùng `Thread.sleep` để tạo race | Thời gian phụ thuộc máy và scheduler | Dùng barrier, latch hoặc test hook |
| Test concurrent có `@Transactional` bao ngoài | Thread con có transaction riêng và không thấy dữ liệu test như dự kiến | Để service mở transaction độc lập; seed/cleanup riêng |
| Cùng key nhưng không kiểm tra payload | Có thể âm thầm trả kết quả cũ cho request khác | Test fingerprint mismatch |
| Chỉ test transaction đầu commit | Không kiểm tra khả năng request sau tiếp quản khi rollback | Thêm test first transaction rollback |
| Chỉ test database, bỏ qua outbox/provider | Side effect ngoài có thể vẫn lặp | Test inbox, provider key và crash window |
| Retry vô hạn trong test | Có thể che giấu deadlock hoặc serialization failure lặp | Giới hạn retry và assert số lần thử |
| Xóa idempotency record ngay sau test | Không kiểm tra hành vi retention/replay | Test chính sách lưu và hết hạn riêng |

## 20. Tự kiểm tra

**Tình huống 1:** Một test gửi cùng key và cùng payload hai lần, cả hai response đều `200 OK`. Có thể kết luận thao tác idempotent chưa?

**Đáp án:** Chưa. Cần xác nhận cả hai response đại diện cùng resource ID/kết quả, đồng thời database chỉ có một hiệu ứng nghiệp vụ. Status code một mình không chứng minh không có duplicate.

**Tình huống 2:** Hai thread cùng gửi một key. Vì sao không nên dùng chung một EntityManager hoặc connection?

**Đáp án:** EntityManager/session thường không thread-safe và cùng một connection không đại diện cho hai transaction độc lập. Test cần hai transaction và connection riêng để tái hiện cạnh tranh thực tế.

**Tình huống 3:** Server commit payment rồi mất response. Test nên đặt lỗi giả lập ở đâu?

**Đáp án:** Sau khi transaction commit thành công nhưng trước khi HTTP response đến client. Khi retry cùng key, test xác nhận server phát lại payment cũ và không tạo payment thứ hai.

**Tình huống 4:** T1 insert idempotency key rồi rollback trước commit, trong khi T2 đang chờ cùng key. Kết quả mong đợi là gì?

**Đáp án:** Sau khi T1 rollback, T2 có thể insert key và thực hiện thao tác. Test xác nhận không còn record/payment từ T1 và chỉ có một kết quả do T2 commit.

**Tình huống 5:** Một test chỉ dùng H2 pass, nhưng production dùng PostgreSQL. Có đủ bằng chứng về cạnh tranh unique index chưa?

**Đáp án:** Chưa. Hành vi khóa và transaction có thể khác giữa DBMS. Cần integration test trên PostgreSQL thật hoặc container cùng phiên bản/cấu hình phù hợp.

**Tình huống 6:** Outbox worker publish event rồi chết trước khi đánh dấu đã gửi. Test cần xác nhận điều gì ở consumer?

**Đáp án:** Khi broker giao lại cùng event ID, consumer phải nhận ra event đã xử lý và không áp dụng hiệu ứng database lần hai. Dấu inbox và thay đổi nghiệp vụ cần cùng transaction.

**Tình huống 7:** Cùng key được gửi với hai amount khác nhau. Test chỉ xác nhận không có payment thứ hai đã đủ chưa?

**Đáp án:** Chưa. Cần xác nhận API trả lỗi payload conflict theo hợp đồng, kết quả gốc không bị thay đổi và request khác payload không được coi là replay hợp lệ.

Khi kiểm thử tính lũy đẳng, hãy mô phỏng cả việc gửi lặp tuần tự, cạnh tranh đồng thời và những điểm mất kết nối quanh commit. Dùng database thật để kiểm tra UNIQUE và transaction, đồng bộ thread bằng latch/barrier thay vì thời gian giả định, rồi xác nhận hiệu ứng ở payment, ledger, outbox và consumer. Một test chỉ chứng minh response thành công chưa đủ; điều cần chứng minh là cùng một ý định nghiệp vụ chỉ tạo ra một kết quả được xác nhận.
