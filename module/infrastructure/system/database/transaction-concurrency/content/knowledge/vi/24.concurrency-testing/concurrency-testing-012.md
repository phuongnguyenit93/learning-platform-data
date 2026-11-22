# Ngăn kiểm thử không ổn định bằng timeout, dọn dữ liệu và ranh giới giao dịch rõ ràng

## Vì sao kiểm thử đồng thời dễ chập chờn?

Một concurrency test thường tạo ra nhiều thread, connection và transaction cùng truy cập dữ liệu. Kết quả phụ thuộc vào lịch chạy thread, tốc độ database, connection pool, tải của máy CI và thời điểm các transaction lấy hoặc nhả khóa. Một test chạy đúng trên máy cá nhân có thể thất bại ngẫu nhiên trên CI nếu nó dựa vào giả định về thời gian hoặc trạng thái dùng chung.

Các nguyên nhân thường gặp gồm:

- Dùng `Thread.sleep()` để đoán khi nào thread khác đã chạy tới một bước.
- Chờ `Future`, latch, barrier hoặc HTTP request mà không đặt timeout.
- Fixture được tạo trong transaction chưa commit nên worker ở thread khác không nhìn thấy.
- Test method được Spring mở transaction tự động, nhưng công việc bất đồng bộ lại commit bằng transaction riêng.
- Các test dùng chung ID, email, account hoặc bảng dữ liệu rồi xóa dữ liệu của nhau.
- Cleanup chạy trong khi worker vẫn còn xử lý hoặc không dọn hết bản ghi phụ thuộc.
- Dùng H2 để suy luận hành vi khóa và isolation của MySQL/PostgreSQL trong production.
- Giữ transaction và connection mở trong lúc test chờ một thread hoặc dịch vụ khác.

Một concurrency test ổn định cần ba ranh giới rõ ràng: **điểm đồng bộ giữa các thread, thời hạn chờ cho mọi thao tác có thể treo, và ranh giới transaction/dữ liệu riêng cho từng test**.

## Điều phối thread bằng tín hiệu, không bằng thời gian đoán

`Thread.sleep()` chỉ làm thread hiện tại tạm dừng. Nó không chứng minh thread khác đã đến một trạng thái cụ thể. Nếu CI chậm, thread kia có thể chưa chạy; nếu CI nhanh, nó có thể đã chạy qua trạng thái cần quan sát. Vì vậy, sleep thường tạo ra test phụ thuộc tốc độ máy.

Hãy dùng các primitive đồng bộ để mô tả chính xác sự kiện cần chờ:

| Primitive | Dùng khi |
| --- | --- |
| `CountDownLatch` | Một hoặc nhiều thread báo đã sẵn sàng, hoặc thread chính chờ một số sự kiện hoàn tất. |
| `CyclicBarrier` | Một nhóm thread cần cùng tới một điểm rồi mới tiếp tục. Có thể tái sử dụng cho nhiều vòng. |
| `Phaser` | Số participant hoặc số phase thay đổi trong quá trình test. |
| `Semaphore` | Giới hạn số thread được vào một vùng xử lý hoặc mô phỏng tài nguyên có số slot hữu hạn. |
| `Future.get(timeout, unit)` | Chờ kết quả của một tác vụ nền trong thời hạn xác định. |

### Ví dụ: cho hai worker bắt đầu cùng lúc

Một cổng bắt đầu (start gate) giúp test không để worker thứ nhất chạy hết trước khi worker thứ hai được tạo:

```java
ExecutorService executor = Executors.newFixedThreadPool(2);
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

Callable<Result> worker = () -> {
    ready.countDown();
    await(start, Duration.ofSeconds(5));
    return service.performConcurrentOperation();
};

Future<Result> first = executor.submit(worker);
Future<Result> second = executor.submit(worker);

try {
    assertTrue(ready.await(5, TimeUnit.SECONDS),
            "Both workers should become ready");
    start.countDown();

    Result firstResult = first.get(5, TimeUnit.SECONDS);
    Result secondResult = second.get(5, TimeUnit.SECONDS);
    assertResults(firstResult, secondResult);
} finally {
    start.countDown(); // Không để worker kẹt ở cổng nếu assertion thất bại.
    executor.shutdownNow();
    assertTrue(executor.awaitTermination(5, TimeUnit.SECONDS),
            "Executor should terminate");
}
```

Hàm `await` trong ví dụ là helper có giới hạn thời gian:

```java
private static void await(CountDownLatch latch, Duration timeout) {
    try {
        if (!latch.await(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
            throw new AssertionError("Timed out waiting for synchronization");
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new AssertionError("Worker was interrupted", e);
    }
}
```

Start gate đồng bộ thời điểm bắt đầu, nhưng không tự bảo đảm hai thread đã cùng đọc một giá trị hoặc đã tranh chấp cùng một khóa. Nếu cần tái hiện một interleaving cụ thể, hãy đặt thêm latch/barrier ở đúng điểm trong quy trình, chẳng hạn sau khi cả hai transaction đọc xong và trước khi chúng ghi.

### Buộc một interleaving cụ thể

Giả sử muốn chứng minh thuật toán đọc rồi ghi không có khóa có thể làm mất cập nhật. Hai worker cần đọc cùng giá trị trước khi worker nào ghi:

```java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch allowWrite = new CountDownLatch(1);

Callable<Void> unsafeWorker = () -> transactionTemplate.execute(status -> {
    Integer current = jdbcTemplate.queryForObject(
            "SELECT quantity FROM inventory WHERE product_id = ?",
            Integer.class,
            productId);

    bothRead.countDown();
    await(allowWrite, Duration.ofSeconds(5));

    jdbcTemplate.update(
            "UPDATE inventory SET quantity = ? WHERE product_id = ?",
            current - 1,
            productId);
    return null;
});
```

Test gửi hai worker, chờ `bothRead` về 0 rồi mới mở `allowWrite`. Cả hai đã đọc cùng một giá trị cũ; nếu mỗi worker ghi lại `current - 1`, một cập nhật có thể ghi đè cập nhật kia. Đây là đồng bộ theo trạng thái thực tế, không phụ thuộc thời gian ngủ.

Phải mở gate trong `finally` để worker không bị treo khi assertion hoặc thao tác chuẩn bị thất bại:

```java
try {
    Future<Void> first = executor.submit(unsafeWorker);
    Future<Void> second = executor.submit(unsafeWorker);

    assertTrue(bothRead.await(5, TimeUnit.SECONDS));
    allowWrite.countDown();

    first.get(5, TimeUnit.SECONDS);
    second.get(5, TimeUnit.SECONDS);
} finally {
    allowWrite.countDown();
    executor.shutdownNow();
    assertTrue(executor.awaitTermination(5, TimeUnit.SECONDS));
}
```

Đối với `SELECT ... FOR UPDATE`, không đặt barrier sau câu locking read của cả hai worker: worker thứ hai cần chờ worker thứ nhất nhả khóa, nên nó không thể cùng đến barrier. Thay vào đó, đồng bộ trước khi lấy khóa hoặc dùng một latch để giữ transaction thứ nhất trong lúc transaction thứ hai được khởi chạy. Nếu test cần khẳng định transaction thứ hai thực sự đang chờ lock, hãy dùng công cụ quan sát lock của database cụ thể; đừng suy ra điều đó chỉ từ một khoảng sleep.

## Thiết lập timeout ở nhiều tầng

Một test đồng thời có thể treo ở nhiều chỗ: chờ thread, chờ connection, chờ lock, chờ SQL, chờ HTTP hoặc chờ một trạng thái bất đồng bộ. Chỉ đặt timeout ở test method là chưa đủ nếu tác vụ nền vẫn giữ connection hoặc thread sau khi test đã thất bại.

Nên đặt timeout ở các tầng sau:

| Tầng | Cơ chế | Mục đích |
| --- | --- | --- |
| Test method | JUnit `@Timeout` | Bảo đảm toàn bộ test không chạy vô hạn. |
| Đồng bộ thread | `CountDownLatch.await(timeout)` hoặc `CyclicBarrier.await(timeout)` | Phát hiện participant không đến điểm đồng bộ. |
| Tác vụ nền | `Future.get(timeout, unit)` | Phát hiện worker không trả kết quả đúng hạn. |
| Database lock | `lock_timeout`, `innodb_lock_wait_timeout` hoặc cấu hình tương đương | Giới hạn thời gian chờ khóa ở server. |
| SQL statement | JDBC query timeout hoặc statement timeout của database | Giới hạn câu lệnh chạy quá lâu. |
| HTTP | Connect, response/read và overall request timeout | Giới hạn thời gian chờ dịch vụ ngoài. |
| Trạng thái eventual | Awaitility hoặc poll có deadline | Chờ một trạng thái bất đồng bộ xuất hiện trong khoảng cho phép. |

### Timeout bên ngoài phải lớn hơn timeout bên trong

Hãy đặt các giới hạn theo thứ tự để test có thời gian nhận lỗi và cleanup:

```text
Database lock timeout       2 giây
Future.get                  4 giây
JUnit test timeout         10 giây
```

Đây chỉ là ví dụ. Giá trị thực tế cần phù hợp với tải CI, kích thước dữ liệu, startup container và thời gian phản hồi dự kiến. Test timeout nên lớn hơn timeout của tác vụ con để test có thể thu thập lỗi, rollback và đóng tài nguyên trước khi bị dừng.

Không đặt timeout quá ngắn chỉ để test chạy nhanh. Một timeout sát thời gian phản hồi bình thường sẽ biến biến động nhỏ của CI thành false failure. Mục tiêu là giới hạn chờ vô hạn và phát hiện deadlock, không phải buộc hệ thống hoàn tất trong một khoảng phi thực tế.

### JUnit 5

Có thể đặt timeout cho test:

```java
@Test
@Timeout(value = 10, unit = TimeUnit.SECONDS)
void concurrentRequestsShouldPreserveInventory() {
    // Arrange, coordinate workers, assert and clean up.
}
```

Trong test phụ thuộc transaction gắn với thread, cần thận trọng với các API timeout chạy test trên thread khác. `assertTimeoutPreemptively` thực thi đoạn mã trong thread riêng; transaction của Spring thường gắn với thread hiện tại qua `ThreadLocal`, nên transaction test có thể không còn bao quanh thao tác được thực thi. Hãy hiểu thread mode của JUnit đang dùng và ưu tiên timeout không đổi thread cho test transaction-bound.

### Timeout cho database

Với PostgreSQL, có thể đặt giới hạn trong transaction:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '4s';

SELECT *
FROM inventory
WHERE product_id = 42
FOR UPDATE;

COMMIT;
```

`lock_timeout` giới hạn thời gian chờ khóa; `statement_timeout` giới hạn tổng thời gian statement. Đặt `SET LOCAL` trong transaction để giá trị chỉ áp dụng cho transaction đó.

Với MySQL, `innodb_lock_wait_timeout` giới hạn thời gian chờ InnoDB row lock theo session. Có thể thiết lập ở cấp session cho connection dùng trong test:

```sql
SET SESSION innodb_lock_wait_timeout = 2;
```

Đừng nhầm lock wait timeout với query timeout: một câu SQL có thể chạy lâu do scan hoặc xử lý khác mà không chờ lock. Hãy dùng thêm JDBC `Statement.setQueryTimeout(...)` hoặc cơ chế statement timeout phù hợp khi cần giới hạn thời gian thực thi.

### Timeout cho công việc bất đồng bộ

Nếu service ghi job vào outbox rồi worker xử lý sau, test không nên gọi `Thread.sleep(1000)` rồi đoán job đã xong. Có thể dùng Awaitility:

```java
await()
    .atMost(Duration.ofSeconds(5))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        Job job = jobRepository.findById(jobId).orElseThrow();
        assertEquals(JobStatus.COMPLETED, job.getStatus());
    });
```

Polling vẫn có khoảng thời gian chờ, nhưng nó kiểm tra điều kiện thực tế và dừng ngay khi điều kiện đúng. Đặt deadline hữu hạn và đảm bảo worker có thể dừng khi test kết thúc. Nếu hệ thống có callback hoặc event test hook đáng tin cậy, tín hiệu trực tiếp còn tốt hơn polling.

## Ranh giới transaction trong concurrency test

Một concurrency test thường cần ít nhất ba giai đoạn transaction riêng:

1. **Setup:** tạo dữ liệu fixture và commit để mọi worker có thể nhìn thấy.
2. **Execution:** mỗi worker chạy transaction độc lập trên connection riêng, cùng tranh chấp dữ liệu theo kịch bản test.
3. **Assertion và cleanup:** đọc kết quả đã commit, sau đó xóa đúng dữ liệu do test tạo.

Không để transaction của test method vô tình bao quanh toàn bộ các giai đoạn này nếu worker chạy ở thread khác.

### Vì sao `@Transactional` trên test có thể gây lỗi?

Spring Test thường mở transaction cho test method và rollback transaction đó sau khi test kết thúc. Transaction được gắn với thread thực thi test. Một worker chạy trong `ExecutorService` là thread khác, nên nó thường dùng connection và transaction khác.

Điều này tạo ra hai vấn đề:

- **Fixture chưa commit:** test tạo account hoặc job trong transaction của thread chính, sau đó worker truy vấn bằng connection khác. Worker không nhìn thấy dữ liệu chưa commit đó.
- **Worker commit độc lập:** worker có thể commit dữ liệu của nó. Khi test method kết thúc, Spring rollback transaction của thread chính nhưng không rollback transaction đã commit trong worker. Dữ liệu worker để lại có thể làm test sau thất bại.

Vì vậy, concurrency integration test nên chủ động quản lý transaction setup và cleanup. Thông thường, không gắn `@Transactional` mặc định lên test method; dùng `TransactionTemplate` hoặc connection riêng để commit fixture và từng worker.

### Mỗi worker cần transaction và connection riêng

Ví dụ với Spring `TransactionTemplate` và `JdbcTemplate`:

```java
Callable<Void> worker = () -> transactionTemplate.execute(status -> {
    jdbcTemplate.update(
            "UPDATE inventory SET quantity = quantity - 1 " +
            "WHERE product_id = ? AND quantity > 0",
            productId);
    return null;
});
```

`TransactionTemplate` dùng transaction manager đã cấu hình và bắt đầu transaction theo thread đang gọi. Khi hai task chạy đồng thời, mỗi thread tham gia một transaction riêng. Cần bảo đảm connection pool có đủ connection cho số worker đồng thời cộng với connection mà test thread hoặc worker phụ cần dùng.

Nếu pool chỉ có một connection nhưng test giữ connection chính trong lúc chờ worker, worker có thể không lấy được connection và test bị treo. Timeout giúp phát hiện vấn đề; cấu hình pool phù hợp và không giữ connection không cần thiết giúp tránh nó.

### Setup phải commit trước khi worker chạy

Một fixture nên được tạo trong transaction ngắn và commit trước khi mở start gate:

```java
UUID testRunId = UUID.randomUUID();

transactionTemplate.executeWithoutResult(status -> {
    jdbcTemplate.update(
            "INSERT INTO inventory_test_data(test_run_id, product_id, quantity) " +
            "VALUES (?, ?, ?)",
            testRunId.toString(),
            productId,
            10);
}); // Transaction commit khi executeWithoutResult hoàn tất.

// Chỉ sau điểm này mới submit và mở các worker.
```

Nếu fixture chưa commit, worker ở transaction khác có thể không nhìn thấy. Đừng dùng `flush()` của ORM như bằng chứng rằng dữ liệu đã commit; flush chỉ gửi SQL trong transaction hiện tại.

## Ví dụ kiểm thử hai cập nhật đồng thời bằng SQL nguyên tử

Một cách tốt để kiểm tra cập nhật tồn kho là dùng điều kiện trong chính câu `UPDATE`, thay vì đọc giá trị rồi ghi lại từ ứng dụng. Giả sử ban đầu số lượng là `10`, hai worker cùng giảm một đơn vị:

```java
@Test
@Timeout(value = 10, unit = TimeUnit.SECONDS)
void twoConcurrentDecrementsShouldNotLoseAnUpdate() throws Exception {
    UUID testRunId = UUID.randomUUID();
    int productId = createCommittedInventory(testRunId, 10);
    ExecutorService executor = Executors.newFixedThreadPool(2);
    CountDownLatch ready = new CountDownLatch(2);
    CountDownLatch start = new CountDownLatch(1);

    Callable<Integer> decrement = () -> {
        ready.countDown();
        await(start, Duration.ofSeconds(4));

        return transactionTemplate.execute(status ->
                jdbcTemplate.update(
                        "UPDATE inventory_test_data " +
                        "SET quantity = quantity - 1 " +
                        "WHERE test_run_id = ? " +
                        "AND product_id = ? " +
                        "AND quantity > 0",
                        testRunId.toString(),
                        productId));
    };

    try {
        Future<Integer> first = executor.submit(decrement);
        Future<Integer> second = executor.submit(decrement);

        assertTrue(ready.await(4, TimeUnit.SECONDS),
                "Workers did not become ready");
        start.countDown();

        assertEquals(1, first.get(4, TimeUnit.SECONDS));
        assertEquals(1, second.get(4, TimeUnit.SECONDS));
        assertEquals(8, readCommittedQuantity(testRunId, productId));
    } finally {
        start.countDown();
        executor.shutdownNow();
        boolean terminated = executor.awaitTermination(4, TimeUnit.SECONDS);
        if (terminated) {
            deleteTestData(testRunId);
        } else {
            throw new AssertionError(
                    "Workers did not terminate; defer cleanup to the test-data janitor");
        }
    }
}
```

Các helper `createCommittedInventory`, `readCommittedQuantity` và `deleteTestData` cần dùng transaction rõ ràng. Mỗi worker cập nhật `quantity = quantity - 1` trực tiếp trên database. InnoDB hoặc PostgreSQL điều phối khóa ghi để cả hai cập nhật được áp dụng; kết quả cuối là `8`.

Đây là ví dụ cấu trúc cho một integration test, cần điều chỉnh kiểu ID, schema và API transaction theo dự án. Nếu assertion của `Future.get` ném exception, test phải giữ nguyên exception gốc trong khi vẫn giải phóng gate, executor và dữ liệu.

## Kiểm thử locking read với thứ tự có kiểm soát

Nếu muốn kiểm tra `SELECT ... FOR UPDATE`, hãy làm rõ transaction nào giữ khóa và khi nào khóa được nhả. Ví dụ về trình tự:

```text
Test thread                     Worker A                 Worker B
-----------                     --------                 --------
Tạo fixture và COMMIT
                                BEGIN
                                SELECT ... FOR UPDATE
                                (đã giữ khóa)
Chờ A báo đã giữ khóa
                                                        Bắt đầu transaction
                                                        SELECT ... FOR UPDATE
                                                        (chờ khóa A)
Cho A tiếp tục
                                UPDATE quantity - 1
                                COMMIT
                                                        Lấy được khóa
                                                        Đọc giá trị hiện hành
                                                        UPDATE quantity - 1
                                                        COMMIT
Đọc kết quả cuối và cleanup
```

Test có thể dùng latch để A báo sau khi đã lấy khóa và một latch khác để giữ A trong transaction. Worker B bắt đầu locking read khi A còn giữ khóa. Sau khi A commit, B tiếp tục. Cần đặt lock timeout đủ lớn để B có cơ hội chờ trong CI nhưng vẫn hữu hạn.

Khi kiểm tra kết quả, hãy xác nhận cả trạng thái cuối và các bất biến nghiệp vụ. Ví dụ, nếu số lượng ban đầu là `2` và hai worker cùng giảm một, kết quả phải là `0`; nếu ban đầu là `1`, chỉ một worker được phép giảm thành công và worker còn lại phải nhận kết quả không đủ hàng.

Nếu mục tiêu của test là chứng minh B đã thực sự bị block bởi lock, cần quan sát trạng thái lock từ database (ví dụ PostgreSQL `pg_stat_activity`/`pg_locks` hoặc MySQL Performance Schema). Một latch đặt trước câu SQL chỉ chứng minh B đã chuẩn bị gọi truy vấn, không chứng minh server đã bắt đầu chờ khóa.

## Dọn dữ liệu test theo phạm vi sở hữu

Cleanup là một phần của thiết kế concurrency test. Dữ liệu test cần có định danh riêng để test chỉ xóa những gì nó tạo ra.

### Tạo namespace cho mỗi lần chạy

Sinh `testRunId` bằng UUID và gắn nó vào các dòng fixture hoặc bảng liên kết:

```sql
CREATE TABLE inventory_test_data (
    test_run_id CHAR(36) NOT NULL,
    product_id  BIGINT NOT NULL,
    quantity    INTEGER NOT NULL,
    PRIMARY KEY (test_run_id, product_id)
);
```

Trong schema ứng dụng, có thể dùng ID chính của thực thể test hoặc một `correlation_id` riêng thay vì tạo bảng test chuyên dụng. Mục tiêu là truy vấn cleanup có điều kiện chính xác theo ID của lượt test hiện tại.

Không dùng các ID cố định như `product_id = 1` hoặc email `test@example.com` nếu nhiều test có thể chạy song song hoặc cùng dùng một database. UUID hoặc mã có namespace giúp tránh va chạm giữa worker, test class và CI job.

### Cleanup trong `finally` sau khi worker kết thúc

Thứ tự cleanup nên là:

1. Ngăn gửi thêm công việc mới hoặc mở start gate để worker đang chờ có thể thoát.
2. Chờ worker kết thúc trong thời hạn hữu hạn; hủy task còn chờ nếu cần.
3. Đóng hoặc rollback transaction còn mở và trả connection về pool.
4. Xóa dữ liệu phụ thuộc theo thứ tự khóa ngoại: bảng con trước, bảng cha sau.
5. Chỉ xóa các dòng mang `testRunId` của test hiện tại.

Ví dụ:

```java
private void deleteTestData(UUID testRunId) {
    transactionTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
                "DELETE FROM order_items WHERE test_run_id = ?",
                testRunId.toString());
        jdbcTemplate.update(
                "DELETE FROM orders WHERE test_run_id = ?",
                testRunId.toString());
        jdbcTemplate.update(
                "DELETE FROM inventory_test_data WHERE test_run_id = ?",
                testRunId.toString());
    });
}
```

Các câu lệnh và thứ tự phải khớp schema thực tế. Nếu worker chưa kết thúc, cleanup có thể chạy đua với worker và tạo lỗi khó tái hiện. Hãy kết thúc worker trước khi xóa fixture.

### Vì sao nên tránh TRUNCATE trong cleanup transaction?

`TRUNCATE` có semantics khác nhau giữa các database. Trên MySQL, `TRUNCATE TABLE` là DDL và gây implicit commit; nó không hoạt động như `DELETE` có thể rollback cùng transaction. Trên PostgreSQL, `TRUNCATE` có thể rollback trong transaction nhưng lấy khóa mạnh và có thể ảnh hưởng các test khác. Với test dùng chung database, `TRUNCATE` dễ xóa dữ liệu của test song song.

Ưu tiên `DELETE ... WHERE test_run_id = ?` trong transaction cleanup. Nếu dùng database/container riêng cho từng test suite, có thể hủy toàn bộ schema hoặc container sau khi suite kết thúc.

### Xử lý cleanup khi test thất bại hoặc process bị dừng

`finally` chạy khi test kết thúc theo luồng điều khiển bình thường, nhưng không bảo đảm chạy nếu JVM bị kill hoặc máy CI mất điện. Với database dùng chung lâu dài, nên có job dọn fixture cũ theo `test_run_id`, thời điểm tạo và nhãn môi trường. Với Testcontainers, database/container dùng riêng cho suite thường được hủy khi suite hoàn tất.

Không xóa dữ liệu dựa trên tiền tố chung quá rộng như `test_%` nếu nhiều job dùng chung database. Cleanup định kỳ phải có namespace riêng của CI run và giới hạn môi trường rõ ràng.

## Test transaction của Spring và công việc bất đồng bộ

Spring test-managed transaction thường bắt đầu trước test method và rollback sau test. Cơ chế này thuận tiện cho test repository tuần tự, nhưng không tự bao trùm thread do executor hoặc message listener tạo ra.

### Tránh để worker đọc fixture chưa commit

Ví dụ dễ sai:

```java
@Test
@Transactional
void workerShouldProcessJob() throws Exception {
    Job job = jobRepository.save(new Job("READY"));

    workerExecutor.submit(() -> jobService.process(job.getId())).get();
}
```

Nếu `jobRepository.save` chỉ flush trong transaction của test mà chưa commit, worker thread dùng transaction khác có thể không tìm thấy job. Test có thể thất bại dù production path commit job trước khi phát tín hiệu cho worker.

Một cách phù hợp hơn là không mở transaction test-managed cho concurrency test. Commit job trước, sau đó gọi worker và kiểm tra trạng thái đã commit:

```java
@Test
@Timeout(value = 10, unit = TimeUnit.SECONDS)
void workerProcessesCommittedJob() throws Exception {
    UUID testRunId = UUID.randomUUID();
    Long jobId = transactionTemplate.execute(status ->
            jobRepository.save(new Job(testRunId, "READY")).getId());

    try {
        Future<?> future = workerExecutor.submit(() -> jobService.process(jobId));
        future.get(5, TimeUnit.SECONDS);

        assertEquals("COMPLETED", readCommittedJobStatus(jobId));
    } finally {
        deleteJobsByTestRunId(testRunId);
    }
}
```

Trong ví dụ, transaction tạo job kết thúc trước khi submit worker. Worker có thể đọc dữ liệu đã commit bằng connection riêng. Cleanup chỉ xóa job thuộc lượt test.

### Worker commit không bị rollback cùng test method

Nếu worker commit thành công, transaction test của thread chính rollback cũng không thể hoàn tác commit của worker. Vì vậy, không dựa vào rollback tự động của `@Transactional` để dọn dữ liệu do worker tạo. Hãy xóa bằng `testRunId` trong cleanup hoặc dùng database riêng có thể hủy sau test.

### Test async nên đợi điều kiện nghiệp vụ

Nếu production dùng message broker hoặc scheduler, test cần đợi trạng thái cuối của job hoặc nhận một tín hiệu hoàn tất. Không chỉ đợi thread gửi message kết thúc: message có thể mới được publish, consumer chưa xử lý xong.

Ví dụ, sau khi publish event, dùng polling có deadline để chờ projection hoặc trạng thái job cập nhật. Cần kiểm tra rằng worker thực sự đã commit thay đổi trước khi assertion đọc bằng connection khác.

## Chạy test trên đúng database engine

Concurrency semantics phụ thuộc engine và phiên bản. H2 có thể hữu ích cho test repository cơ bản, nhưng không thay thế được MySQL InnoDB hoặc PostgreSQL khi kiểm tra:

- `SELECT ... FOR UPDATE`, `NOWAIT`, `SKIP LOCKED` và phạm vi khóa.
- Gap lock, next-key lock và phantom behavior.
- Deadlock detection, lock wait timeout và phạm vi rollback sau lỗi.
- Isolation level mặc định và thời điểm tạo snapshot.
- Implicit commit của DDL và cách migration hoạt động.
- Cú pháp upsert, unique constraint và foreign key.

Nếu production dùng MySQL, hãy chạy test tích hợp trên cùng major/minor version hoặc phiên bản tương thích đã được xác định bằng Testcontainers. Nếu production dùng PostgreSQL, dùng PostgreSQL container. Không kết luận rằng một test chạy trên H2 chứng minh behavior của InnoDB.

Ví dụ khởi tạo MySQL bằng Testcontainers:

```java
@Testcontainers
class InventoryConcurrencyIT {
    @Container
    static final MySQLContainer<?> mysql =
            new MySQLContainer<>("mysql:8.4")
                    .withDatabaseName("concurrency_test")
                    .withUsername("test")
                    .withPassword("test");

    // Cấu hình DataSource dùng JDBC URL, username và password
    // do container cung cấp; chạy migration trước khi test.
}
```

Tag image nên được pin theo phiên bản production đã chọn thay vì dùng `latest`. Chạy migration thật để test schema, index và constraint giống môi trường ứng dụng.

## Kiểm soát test chạy song song

Chạy test song song có thể làm lộ race condition thật, nhưng cũng làm tăng khả năng test tự va chạm nếu fixture dùng chung.

Các nguyên tắc hữu ích:

- Mỗi test dùng UUID hoặc namespace riêng cho mọi dữ liệu có thể xung đột.
- Không dùng một hàng singleton chung để tất cả test cùng cập nhật nếu mục tiêu test không phải cạnh tranh trên chính hàng đó.
- Không dùng một tài khoản dùng chung cho nhiều test có cleanup độc lập.
- Connection pool phải đủ cho số worker và thao tác điều phối của test.
- Giới hạn số test concurrency chạy đồng thời để tránh làm cạn database CI.
- Nếu dùng schema/database riêng theo test class hoặc CI worker, hãy tạo và hủy chúng theo vòng đời rõ ràng.
- Không tắt test parallel globally chỉ để che một lỗi chia sẻ dữ liệu; xác định và cô lập tài nguyên trước.

Một test cần hai transaction cùng tranh chấp một dòng có thể cố ý dùng chung `product_id` bên trong test đó. Nhưng ID đó phải thuộc namespace của test, không được chia sẻ với test khác.

## Kiểm thử retry và lỗi không xác định

Trong hệ thống có HTTP hoặc message queue, timeout có thể xảy ra sau khi dịch vụ đích đã xử lý request. Test cần mô phỏng đúng tình huống đó thay vì chỉ làm server không phản hồi từ đầu.

Một HTTP stub có thể:

1. Nhận request và ghi nhận idempotency key.
2. Đánh dấu thao tác đã được xử lý trong state của stub.
3. Cố ý làm client timeout hoặc đóng kết nối trước khi gửi response.
4. Khi client retry cùng key, trả lại kết quả đã lưu mà không tăng số lần áp dụng hiệu ứng.

Test nên xác nhận số hiệu ứng nghiệp vụ bằng một bộ đếm hoặc record trong stub, không chỉ xác nhận HTTP status của lần retry. Nếu test dùng WireMock hoặc MockWebServer, hãy cấu hình timeout và kịch bản lỗi tường minh; không dựa vào độ trễ ngẫu nhiên.

Với message queue, có thể mô phỏng consumer commit database rồi dừng trước ACK. Broker giao lại message và consumer phải bỏ qua hiệu ứng trùng nhờ inbox/dedup record. Một test khác mô phỏng lỗi trước commit để xác nhận cả dấu xử lý lẫn cập nhật nghiệp vụ rollback.

## Chẩn đoán test bị treo hoặc thất bại ngẫu nhiên

Khi concurrency test fail, log cần đủ dữ kiện để xác định thứ tự xảy ra:

- `testRunId`, test method, worker name và thread ID.
- ID transaction hoặc connection nếu driver/framework cho phép quan sát.
- ID bản ghi, trạng thái trước/sau và số dòng bị ảnh hưởng.
- Isolation level, timeout cấu hình và thời điểm bắt đầu/kết thúc từng bước.
- SQLState, vendor error code và thông tin deadlock/lock wait.
- Lỗi gốc của từng `Future`, không chỉ lỗi timeout ở thread chính.

Không ghi dữ liệu nhạy cảm hoặc toàn bộ payload vào log chỉ để debug. Dùng correlation ID và các trường cần thiết để tái dựng interleaving.

Nếu `Future.get` timeout, hãy thu thập trạng thái worker và database trước khi hủy task nếu môi trường cho phép. `Future.cancel(true)` gửi interrupt nhưng không bảo đảm driver JDBC dừng câu SQL đang chờ. Database lock timeout, query timeout và việc đóng connection có kiểm soát giúp giải phóng tài nguyên tốt hơn.

## Mẫu tổ chức một concurrency integration test

Một test có thể theo bố cục sau:

```text
Arrange
  Tạo testRunId duy nhất.
  Tạo fixture trong transaction riêng và COMMIT.
  Khởi tạo executor, latches và timeout.

Act
  Submit các worker dùng connection/transaction riêng.
  Chờ tất cả worker sẵn sàng bằng latch có timeout.
  Mở start gate hoặc tạo interleaving cần kiểm tra.
  Chờ từng Future bằng timeout hữu hạn.

Assert
  Đọc trạng thái đã commit bằng connection mới.
  Kiểm tra kết quả, số dòng ảnh hưởng và bất biến nghiệp vụ.

Finally
  Mở mọi gate để giải phóng worker.
  Cancel task còn lại và shutdown executor.
  Chờ executor dừng trong thời hạn.
  Đóng tài nguyên và rollback transaction còn mở.
  Xóa dữ liệu theo testRunId, đúng thứ tự khóa ngoại.
```

Có thể đóng gói executor và cleanup trong JUnit extension hoặc helper dùng chung, nhưng helper phải giữ nguyên nguyên tắc: timeout hữu hạn, lỗi gốc không bị che, và cleanup chỉ xóa dữ liệu thuộc test hiện tại.

## Checklist trước khi đưa concurrency test vào CI

- [ ] Các thread được đồng bộ bằng latch/barrier hoặc điều kiện quan sát được, không bằng `Thread.sleep()` tùy tiện.
- [ ] Mọi `await`, `Future.get`, HTTP call và chờ trạng thái đều có timeout.
- [ ] Timeout của tác vụ con nhỏ hơn timeout toàn test để còn thời gian cleanup.
- [ ] Mỗi worker dùng transaction/connection độc lập khi đang kiểm tra cạnh tranh database.
- [ ] Fixture đã commit trước khi worker cần đọc.
- [ ] Test không dựa vào rollback của test-managed transaction để dọn commit từ worker.
- [ ] Test data có namespace riêng và cleanup theo ID cụ thể.
- [ ] Worker đã kết thúc trước khi cleanup dữ liệu.
- [ ] Executor, latch, connection và container được đóng trong `finally` hoặc lifecycle hook.
- [ ] Test chạy trên đúng database engine và phiên bản cần kiểm tra.
- [ ] Connection pool đủ cho mức đồng thời của test.
- [ ] Assertion kiểm tra bất biến nghiệp vụ và dữ liệu đã commit, không chỉ kiểm tra thread đã chạy.
- [ ] Log có correlation ID, thread và thông tin lỗi cần thiết để chẩn đoán.

## Bài tập vận dụng

Một integration test khởi tạo một hàng tồn kho có `quantity = 1`, sau đó submit hai worker để cùng đặt một sản phẩm. Test đôi khi treo trên CI và đôi khi để lại dữ liệu khiến test tiếp theo thất bại.

1. Vì sao `Thread.sleep(500)` sau khi submit hai worker không bảo đảm cả hai đã đến điểm đọc tồn kho?
2. Có thể dùng `CountDownLatch` hoặc `CyclicBarrier` ở đâu để điều phối hai worker?
3. Những timeout nào cần có ở test method, latch, future và database lock?
4. Vì sao fixture cần commit trước khi worker chạy nếu mỗi worker dùng connection riêng?
5. Vì sao `@Transactional` trên test method không tự rollback các thay đổi mà worker đã commit?
6. Thiết kế `testRunId` và cleanup thế nào để hai test chạy song song không xóa dữ liệu của nhau?
7. Nếu test cần xác nhận worker thứ hai thực sự chờ `SELECT ... FOR UPDATE`, cần quan sát gì ngoài việc thread đã bắt đầu?

Một thiết kế ổn định tạo fixture trong transaction đã commit, dùng hai worker có transaction riêng, đồng bộ bằng latch ở điểm cần kiểm soát, đặt timeout hữu hạn cho mọi lần chờ và đọc kết quả sau khi cả hai transaction hoàn tất. Mỗi lượt test có `testRunId` riêng; cleanup đợi worker dừng rồi xóa các bản ghi phụ thuộc theo đúng thứ tự. Nếu cần chứng minh lock wait thực sự xảy ra, test quan sát lock qua metadata của database mục tiêu thay vì dựa vào sleep hoặc suy luận từ lịch chạy thread.
