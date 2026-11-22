# Barrier và latch để đồng bộ kiểm thử thay vì dựa vào thời gian ngủ

Kiểm thử đồng thời cần tạo ra một thứ tự xen kẽ cụ thể giữa các transaction. Nếu chỉ khởi chạy hai thread rồi gọi `Thread.sleep()` để hy vọng chúng chạy đúng thời điểm, bài kiểm thử có thể lúc thành công, lúc thất bại tùy tốc độ máy, tải CI, connection pool và độ trễ database. Thời gian ngủ không chứng minh một thread đã đọc dữ liệu, đã lấy khóa hoặc đã đi đến đúng điểm trong transaction.

Barrier và latch cho phép các thread báo hiệu khi đã đạt một mốc, rồi chờ cho đến khi điều kiện phối hợp được đáp ứng. Nhờ đó, test có thể buộc hai transaction cùng đọc trước khi ghi, hoặc buộc mỗi transaction giữ một khóa trước khi yêu cầu khóa còn lại. Bài kiểm thử trở nên có chủ đích và dễ tái hiện hơn.

Trong Java, những công cụ thường dùng là `CountDownLatch`, `CyclicBarrier` và `Phaser`. Chúng điều phối thread trong tiến trình kiểm thử; mỗi worker vẫn cần connection database riêng để transaction thực sự chạy đồng thời.

## 1. Vì sao Thread.sleep không phải công cụ đồng bộ?

Một bài kiểm thử thường bắt đầu bằng cách chạy hai tác vụ:

```java
executor.submit(() -> transactionA());
executor.submit(() -> transactionB());
Thread.sleep(100);
```

Test có thể giả định rằng sau 100 ms, cả hai transaction đã bắt đầu hoặc đã đọc xong. Nhưng `sleep()` chỉ yêu cầu thread hiện tại tạm dừng ít nhất khoảng thời gian được chỉ định. Nó không bảo đảm:

- Thread A đã được scheduler chạy.
- Thread B đã lấy được connection từ pool.
- Câu SQL đã đến database và hoàn tất.
- Transaction đã giữ khóa cần thiết.
- Cả hai transaction đã đọc cùng một snapshot.

Trên máy phát triển, 100 ms có thể đủ. Trên CI đang tải cao, một worker có thể chưa chạy. Tăng lên vài giây chỉ làm bài test chậm hơn mà vẫn không chứng minh được trạng thái cần thiết.

`Thread.sleep()` vẫn có thể dùng cho backoff trong retry hoặc mô phỏng một khoảng xử lý khi đó là mục tiêu của thí nghiệm. Nhưng để đồng bộ các thread tại một điều kiện, hãy dùng latch, barrier, semaphore hoặc tín hiệu hoàn tất phù hợp.

## 2. Ba công cụ phối hợp phổ biến

| Công cụ | Cách hoạt động | Phù hợp với tình huống |
|---|---|---|
| `CountDownLatch` | Một hoặc nhiều thread chờ bộ đếm về 0; thread khác gọi `countDown()` để giảm bộ đếm. Không thể reset latch. | Chờ tất cả worker sẵn sàng, mở cổng bắt đầu, chờ các tác vụ hoàn tất. |
| `CyclicBarrier` | Một nhóm cố định thread gặp nhau tại một điểm; khi đủ số bên tham gia, tất cả được đi tiếp. Có thể tái sử dụng cho pha sau. | Buộc nhiều transaction cùng hoàn tất bước đọc trước khi bất kỳ transaction nào ghi. |
| `Phaser` | Đồng bộ theo nhiều phase và cho phép số bên tham gia thay đổi. | Test có nhiều giai đoạn hoặc worker tham gia/rời đi động. |

Các công cụ này đồng bộ thread trong JVM. Chúng không khóa hàng database, không commit transaction và không thay thế cơ chế concurrency control của DBMS. Test phải đặt tín hiệu ở đúng vị trí trong luồng JDBC để chứng minh điều kiện cần kiểm tra đã xảy ra.

## 3. CountDownLatch: chờ worker sẵn sàng rồi mới cho chạy tiếp

`CountDownLatch` có một bộ đếm được khởi tạo trước. Mỗi worker gọi `countDown()` khi đạt mốc của nó. Thread điều phối gọi `await()` để chờ cho đến khi bộ đếm về 0.

Ví dụ đơn giản:

```java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

Callable<Void> worker = () -> {
    ready.countDown();       // Báo rằng worker đã sẵn sàng
    start.await();           // Chờ tín hiệu bắt đầu chung
    performWork();
    return null;
};

executor.submit(worker);
executor.submit(worker);

if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("Workers did not become ready in time");
}

start.countDown();           // Mở cổng cho cả hai worker
```

`ready` dùng để chờ hai worker đến điểm sẵn sàng; `start` là cổng một lần. Sau khi `start.countDown()` được gọi, mọi thread đang chờ trên latch đó có thể tiếp tục. Một latch đã về 0 không thể được đặt lại; nếu cần lặp nhiều vòng đồng bộ, dùng `CyclicBarrier` hoặc tạo latch mới cho mỗi vòng.

Luôn dùng `await(timeout, unit)` trong test thay vì chờ vô hạn. Nếu một worker lỗi trước khi gọi `countDown()`, thread điều phối sẽ hết thời gian và báo lỗi rõ ràng thay vì treo toàn bộ suite.

## 4. Dùng latch để tái hiện deadlock bằng hai transaction

Giả sử bảng thử nghiệm có hai hàng với ID 1 và 2. Mục tiêu là tạo lịch:

1. Transaction A khóa hàng 1.
2. Transaction B khóa hàng 2.
3. Chỉ sau khi cả hai đã giữ khóa đầu tiên, cho A yêu cầu hàng 2 và B yêu cầu hàng 1.

Ta dùng hai latch:

- `bothHaveFirstLock`: bộ đếm 2; mỗi worker giảm bộ đếm sau khi câu `UPDATE` đầu tiên hoàn tất.
- `requestSecondLock`: ban đầu đóng; cả hai worker chờ ở đây. Test chỉ mở cổng khi đã biết cả hai đang giữ khóa đầu tiên.

Ví dụ Java với JDBC (đã lược bớt phần cấu hình datasource):

```java
CountDownLatch bothHaveFirstLock = new CountDownLatch(2);
CountDownLatch requestSecondLock = new CountDownLatch(1);

Callable<Void> transaction(int firstId, int secondId) {
    return () -> {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                updateRow(connection, firstId);

                // UPDATE đầu tiên đã hoàn tất; transaction đang giữ khóa.
                bothHaveFirstLock.countDown();

                if (!requestSecondLock.await(5, TimeUnit.SECONDS)) {
                    throw new TimeoutException("Second-lock gate was not opened");
                }

                // Hai transaction sẽ yêu cầu khóa theo thứ tự đảo ngược.
                updateRow(connection, secondId);
                // Nếu không có deadlock, vẫn rollback để giữ dữ liệu lab sạch.
                connection.rollback();
                return null;
            } catch (Exception error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    };
}

Future<Void> a = executor.submit(transaction(1, 2));
Future<Void> b = executor.submit(transaction(2, 1));

try {
    if (!bothHaveFirstLock.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Both transactions did not acquire first locks");
    }

    requestSecondLock.countDown();

    // Thu thập kết quả bằng timeout; kỳ vọng DBMS phát hiện deadlock.
    observeDeadlockOutcome(a, b);
} finally {
    // Mở cổng kể cả khi phần kiểm thử phía trên thất bại,
    // để worker không mắc kẹt ở latch.
    requestSecondLock.countDown();
}
```

`updateRow` là helper thực thi câu `UPDATE deadlock_lab SET touch_count = touch_count + 1 WHERE id = ?`. `observeDeadlockOutcome` cần đọc exception từ `Future`, xác định transaction nào bị chọn làm nạn nhân và áp dụng timeout. Mã lỗi cụ thể phụ thuộc DBMS và driver.

Điểm quyết định là latch chỉ được giảm sau khi câu `UPDATE` đầu tiên hoàn tất. Khi test mở cổng, cả A và B đều đã giữ khóa riêng. Vì vậy, A không thể lấy hàng 2 trước khi B nhả khóa, và B không thể lấy hàng 1 trước khi A nhả khóa. Hệ quản trị sẽ thấy vòng chờ và chọn nạn nhân.

Trong bài test thực tế, cần bảo đảm executor có ít nhất hai thread và connection pool có ít nhất hai connection. Nếu pool chỉ cấp được một connection, worker thứ hai có thể chờ lấy connection trong khi worker thứ nhất chờ latch; khi đó test treo trước khi tạo được concurrency ở database.

## 5. CyclicBarrier: đồng bộ nhiều transaction sau khi đọc

`CyclicBarrier` phù hợp khi nhiều worker phải cùng hoàn thành một phase trước khi đi sang phase kế tiếp. Ví dụ kinh điển là write skew:

- T1 đọc trạng thái của cả bác sĩ A và B.
- T2 cũng đọc trạng thái của cả A và B.
- Chỉ khi cả hai đã đọc xong, cho phép T1 cập nhật A và T2 cập nhật B.

Barrier đặt ngay sau lần đọc bảo đảm không transaction nào ghi trước khi transaction còn lại đọc xong.

```java
CyclicBarrier afterRead = new CyclicBarrier(2);

Callable<Void> turnOffDoctor(String doctorId) {
    return () -> {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int onCallCount = readOnCallCount(connection);

                // Cả hai transaction phải đọc xong trước khi ghi.
                afterRead.await(5, TimeUnit.SECONDS);

                if (onCallCount > 1) {
                    updateDoctor(connection, doctorId, false);
                }

                connection.commit();
                return null;
            } catch (Exception error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    };
}
```

Hai task được submit với `doctorId` khác nhau. Ở Snapshot Isolation, cả hai có thể đọc cùng snapshot rồi cập nhật hai hàng khác nhau. Ở Serializable, DBMS có thể từ chối một transaction vì phát hiện phụ thuộc đọc–ghi.

Nếu cần bảo đảm cả hai cập nhật hoàn tất trước khi transaction nào commit, có thể thêm một barrier thứ hai sau `updateDoctor`. Cần cân nhắc trường hợp một transaction bị lỗi trước khi tới barrier: thread còn lại sẽ chờ đến timeout hoặc nhận `BrokenBarrierException`. Đây là hành vi hữu ích để test thất bại nhanh và dọn dẹp.

## 6. CountDownLatch và CyclicBarrier khác nhau ở đâu?

| Tiêu chí | CountDownLatch | CyclicBarrier |
|---|---|---|
| Số bên tham gia | Bộ đếm có thể được giảm bởi nhiều thread; số thread chờ không cần bằng số đếm. | Có số lượng parties cố định khi tạo barrier. |
| Ai mở cổng? | Bất kỳ thread nào gọi `countDown()` đủ số lần. | Các parties gọi `await()`; bên cuối cùng đến làm barrier mở. |
| Tái sử dụng | Không; latch chỉ về 0 một lần. | Có; tự chuyển sang phase tiếp theo sau khi parties cùng qua. |
| Timeout/interruption | Thread chờ có thể timeout hoặc bị interrupt; latch vẫn tồn tại. | Timeout hoặc interruption có thể làm barrier bị broken và các bên đang chờ nhận lỗi. |
| Barrier action | Không có. | Có thể chạy một action khi party cuối cùng đến, trước khi các bên được thả. |
| Cách dùng thường gặp | Chờ tất cả worker sẵn sàng, mở cổng, chờ hoàn tất. | Đồng bộ các phase lặp lại giữa cùng nhóm worker. |

Hãy chọn latch khi cần một tín hiệu một lần từ nhóm worker hoặc từ test controller. Chọn barrier khi các worker cần gặp nhau ở cùng một điểm và tiếp tục qua nhiều vòng.

## 7. Barrier action và thứ tự nhìn thấy dữ liệu trong JVM

`CyclicBarrier` có thể nhận một `Runnable` chạy bởi thread cuối cùng đến barrier. Action này hữu ích để ghi nhận mốc hoặc chuẩn bị dữ liệu trong bộ nhớ trước khi tất cả worker tiếp tục:

```java
CyclicBarrier barrier = new CyclicBarrier(2, () -> {
    System.out.println("Both workers reached the checkpoint");
});
```

Barrier action không nên thực hiện một thao tác database dài hoặc chờ một worker khác. Nó chạy trong thread cuối cùng đến barrier; nếu action bị block, mọi party đều bị giữ lại.

Các primitive đồng bộ của Java cũng tạo quan hệ memory visibility. Với `CountDownLatch`, các thao tác trước `countDown()` happen-before các thao tác sau một `await()` thành công tương ứng. Với `CyclicBarrier`, các thao tác trước `await()` của một phase happen-before barrier action, và barrier action happen-before các thao tác sau khi các party qua barrier. Điều này giúp dữ liệu test trong bộ nhớ được nhìn thấy đúng giữa các thread.

Quan hệ happens-before trong JVM không thay thế commit hoặc visibility của database. Việc một thread nhìn thấy biến Java của thread khác không chứng minh transaction khác đã commit. Muốn kiểm tra trạng thái database, hãy truy vấn qua connection phù hợp và hiểu isolation level đang dùng.

## 8. Phaser cho kiểm thử nhiều phase hoặc số worker thay đổi

`Phaser` hữu ích khi test có nhiều vòng đồng bộ và số worker có thể đăng ký hoặc rời khỏi quá trình:

```java
Phaser phaser = new Phaser(3); // Test controller + hai worker

// Worker A và B:
readInitialState();
phaser.arriveAndAwaitAdvance(); // Phase 0: tất cả đã đọc

performFirstUpdate();
phaser.arriveAndAwaitAdvance(); // Phase 1: tất cả đã cập nhật

verifyOrCommit();
phaser.arriveAndDeregister();
```

`Phaser` cho phép đăng ký thêm party, hủy đăng ký party và tiến qua nhiều phase. Nó phù hợp với test có worker pool thay đổi theo từng vòng hoặc có nhiều mốc đồng bộ hơn một barrier cố định.

Nếu cần timeout hoặc xử lý interruption, dùng các phương thức chờ có thể interrupt/timeout phù hợp, ví dụ `awaitAdvanceInterruptibly`. Cũng như barrier, nếu một party không bao giờ đến phase cần thiết, các party khác có thể chờ mãi nếu test không đặt giới hạn thời gian.

## 9. Đặt checkpoint đúng vị trí trong transaction

Barrier chỉ hữu ích khi được đặt tại điểm chứng minh điều kiện cần kiểm thử đã xảy ra. Một số ví dụ:

| Mục tiêu kiểm thử | Vị trí đặt tín hiệu |
|---|---|
| Hai transaction cùng đọc một snapshot trước khi ghi | Sau khi mỗi transaction hoàn tất tất cả câu `SELECT` liên quan, trước câu `UPDATE` đầu tiên. |
| Tạo deadlock do thứ tự khóa đảo ngược | Sau khi mỗi transaction đã lấy khóa đầu tiên, trước khi yêu cầu khóa thứ hai. |
| Kiểm tra lost update | Sau khi cả hai transaction đọc cùng giá trị, trước khi tính và ghi kết quả. |
| Kiểm tra unique/FK race | Sau bước đọc hoặc chuẩn bị cạnh tranh, trước thao tác `INSERT`/`DELETE` cần được phối hợp. |
| Kiểm tra retry | Sau khi test đã thiết lập điều kiện xung đột, trước khi cho transaction tiếp tục đến câu lệnh có thể bị từ chối. |

Đặt barrier quá sớm, ví dụ ngay sau khi thread bắt đầu, chỉ chứng minh thread đã chạy đến barrier. Nó không chứng minh câu SQL đã hoàn tất hoặc khóa đã được database cấp.

Đặt barrier quá muộn, ví dụ sau `COMMIT`, không thể điều khiển lịch đọc–ghi cần kiểm tra vì các thay đổi đã hoàn tất. Hãy đặt tín hiệu ngay sau thao tác database tạo ra trạng thái cần đồng bộ.

## 10. Dùng timeout để tránh test treo

Mọi điểm chờ trong test đồng thời cần thời hạn hữu hạn:

```java
boolean readyInTime = ready.await(5, TimeUnit.SECONDS);
if (!readyInTime) {
    throw new AssertionError("Worker did not reach ready checkpoint");
}

afterRead.await(5, TimeUnit.SECONDS);
```

Với `CyclicBarrier`, timeout có thể làm barrier chuyển sang trạng thái broken. Các thread khác đang chờ sẽ nhận `BrokenBarrierException`; code test cần coi đây là lỗi phối hợp và dừng các task liên quan.

Timeout của latch/barrier khác timeout database:

- Barrier/latch timeout cho biết thread không đến checkpoint đúng hạn.
- Query timeout giới hạn thời gian thực thi câu SQL.
- Lock timeout giới hạn thời gian chờ khóa.
- Test timeout giới hạn tổng thời gian cho một kịch bản.

Không dùng một timeout duy nhất cho tất cả tầng. Hãy đặt timeout của từng bước ngắn hơn timeout tổng để test còn thời gian rollback, đóng connection và thu thập thông tin lỗi.

## 11. Xử lý interruption và lỗi ở một worker

Một worker có thể ném `SQLException` trước khi đến barrier. Nếu không truyền lỗi về test controller, worker còn lại có thể chờ đến timeout và test chỉ báo một lỗi phụ.

Các nguyên tắc xử lý:

- Giữ lại exception gốc từ worker và đưa nó về test thread qua `Future.get()` hoặc một cơ chế thu thập lỗi.
- Khi một worker thất bại, mở các latch cổng để worker khác không bị giữ mãi.
- Với barrier, xử lý `BrokenBarrierException` như dấu hiệu một party khác đã không hoàn thành phase.
- Khi nhận `InterruptedException`, dọn dẹp transaction và giữ trạng thái interrupt bằng `Thread.currentThread().interrupt()` nếu không ném tiếp exception.
- Không nuốt exception rồi để test tiếp tục như thể checkpoint đã đạt.

Ví dụ xử lý interruption:

```java
try {
    gate.await(5, TimeUnit.SECONDS);
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Worker was interrupted", error);
}
```

Nếu worker bị interrupt khi đang chờ barrier, barrier có thể bị broken và các worker khác cũng nhận lỗi. Test harness phải dừng toàn bộ kịch bản, rollback transaction còn hoạt động và giải phóng executor.

## 12. Quản lý connection và transaction trong test

Để kiểm thử database concurrency thực sự:

1. Mỗi worker dùng một JDBC `Connection` độc lập.
2. Tắt auto-commit nếu kịch bản cần giữ khóa qua nhiều câu lệnh.
3. Bắt đầu transaction và chạy câu SQL tạo trạng thái cần thiết.
4. Chỉ báo `ready` sau khi câu SQL đã hoàn tất thành công.
5. Chờ latch/barrier ở checkpoint đã chọn.
6. Tiếp tục câu SQL cạnh tranh và thu thập kết quả.
7. Commit hoặc rollback rõ ràng trong mọi nhánh.
8. Đóng connection; nếu trạng thái protocol hoặc transaction không thể xác nhận, discard connection theo cơ chế pool.

Không chia sẻ một `Connection`, `Statement` hoặc `ResultSet` giữa hai worker. JDBC connection thường không được thiết kế để nhiều thread đồng thời điều khiển cùng một transaction. Chia sẻ connection sẽ làm test không còn đại diện cho hai session độc lập và có thể tạo lỗi do chính test harness.

Connection pool phải có sức chứa ít nhất bằng số worker cần đồng thời giữ connection. Nếu test dùng ba transaction nhưng pool chỉ cho mượn hai connection, worker thứ ba có thể chờ pool trong khi hai worker còn lại chờ một barrier cần cả ba. Đây là deadlock ở tầng test/pool, không phải deadlock database mà test định tái hiện.

## 13. Kết hợp Future để chờ và thu thập kết quả

`Future` giúp test controller chờ kết quả từng worker và lấy exception mà worker ném ra:

```java
Future<Result> futureA = executor.submit(taskA);
Future<Result> futureB = executor.submit(taskB);

try {
    Result resultA = futureA.get(10, TimeUnit.SECONDS);
    Result resultB = futureB.get(10, TimeUnit.SECONDS);
    assertExpectedResults(resultA, resultB);
} catch (ExecutionException error) {
    Throwable cause = error.getCause();
    assertExpectedConcurrencyError(cause);
} catch (TimeoutException error) {
    futureA.cancel(true);
    futureB.cancel(true);
    throw new AssertionError("Concurrency scenario timed out", error);
}
```

Trong test deadlock, một future có thể hoàn tất bằng exception do DBMS chọn transaction làm nạn nhân; future còn lại có thể hoàn tất sau khi được giải phóng khóa. Không nên giả định future A luôn lỗi và future B luôn thành công. Hãy thu thập cả hai kết quả và kiểm tra tổng thể kịch bản.

Nếu dùng `ExecutorService.invokeAll(tasks, timeout, unit)`, cần kiểm tra các future bị cancel do hết hạn. `cancel(true)` chỉ gửi interrupt đến thread; driver/database có thể cần cơ chế cancel riêng để dừng câu SQL đang chạy. Test vẫn phải rollback và đóng connection trong `finally`.

## 14. Ví dụ một test hoàn chỉnh theo cấu trúc

Pseudocode dưới đây cho thấy cách kết hợp executor, latch, transaction riêng và cleanup:

```java
@Test
void reversedLockOrderProducesDeadlock() throws Exception {
    CountDownLatch firstLocksAcquired = new CountDownLatch(2);
    CountDownLatch continueToSecondLock = new CountDownLatch(1);
    ExecutorService executor = Executors.newFixedThreadPool(2);

    Future<?> a = executor.submit(
        runTransaction(1, 2, firstLocksAcquired, continueToSecondLock));
    Future<?> b = executor.submit(
        runTransaction(2, 1, firstLocksAcquired, continueToSecondLock));

    try {
        assertTrue(firstLocksAcquired.await(5, TimeUnit.SECONDS));
        continueToSecondLock.countDown();

        Outcome outcomeA = getOutcome(a, 10, TimeUnit.SECONDS);
        Outcome outcomeB = getOutcome(b, 10, TimeUnit.SECONDS);

        assertExactlyOneDeadlockVictim(outcomeA, outcomeB);
    } finally {
        continueToSecondLock.countDown();
        a.cancel(true);
        b.cancel(true);
        executor.shutdownNow();
        assertTrue(executor.awaitTermination(5, TimeUnit.SECONDS));
    }

    assertRowsRestoredToInitialValues();
}
```

Đây là khung minh họa; `runTransaction`, `getOutcome` và phần phân loại mã lỗi phải được viết theo driver/DBMS cụ thể. Trong ví dụ deadlock, transaction không bị chọn làm nạn nhân chủ động rollback sau khi hoàn tất bước thứ hai để giữ dữ liệu lab nguyên trạng. Trong một test thực tế, chỉ cancel future không bảo đảm câu SQL dừng; task cần `finally` để rollback, đóng connection và có thể gọi `Statement.cancel()` nếu cancellation được yêu cầu.

Test cũng cần thu thập kết quả trước khi đóng executor một cách bất thường. Nếu `finally` hủy future ngay sau khi test đã đọc kết quả, không có vấn đề; nếu timeout xảy ra, việc hủy phải đi kèm cleanup connection và kiểm tra database không còn transaction giữ khóa.

## 15. Các lỗi đồng bộ thường gặp

### 15.1. Đặt latch sai vị trí

Nếu worker gọi `countDown()` trước câu `UPDATE`, test chỉ biết worker đã bắt đầu chứ chưa biết khóa đã được lấy. Đặt tín hiệu sau khi câu SQL hoàn tất.

### 15.2. Không mở cổng trong finally

Nếu test thất bại trước khi gọi `start.countDown()`, worker có thể mắc kẹt ở `await()`. Luôn mở latch trong `finally` hoặc hủy task có cleanup rõ ràng.

### 15.3. Dùng CyclicBarrier nhưng một party không đến

Một worker ném exception trước barrier khiến worker còn lại chờ. Dùng timeout, xử lý `BrokenBarrierException` và truyền exception gốc về test controller.

### 15.4. Connection pool nhỏ hơn số worker

Worker chờ connection không thể đến checkpoint. Hãy cấp đủ connection hoặc tăng pool cho profile kiểm thử.

### 15.5. Dùng barrier trong khi transaction giữ khóa quá lâu

Barrier có thể cố ý giữ transaction ở trạng thái chờ để tạo lịch. Chỉ làm điều này trong test có timeout và dữ liệu riêng; không áp dụng mô hình chờ thread tùy tiện trong code production khi đang giữ khóa.

### 15.6. Nhầm đồng bộ thread với đồng bộ database

Barrier chỉ cho biết thread đã gọi đến điểm chờ. Nếu đặt trước khi câu SQL hoàn tất hoặc trước khi DB cấp khóa, test không chứng minh điều kiện database. Đặt checkpoint sau kết quả JDBC thành công và kiểm tra thêm bằng log/metadata khi cần.

## 16. Khi nào dùng Semaphore hoặc các công cụ khác?

`Semaphore` hữu ích khi cần giới hạn số worker đồng thời thực hiện một vùng công việc, ví dụ chỉ cho phép tối đa ba transaction chạy một tác vụ nặng. Nó không tự bảo đảm tất cả worker đến cùng một phase.

`Phaser` phù hợp với nhiều phase và số worker động. `CompletableFuture` hữu ích để ghép các tác vụ bất đồng bộ, nhưng không thay thế một barrier nếu test cần bảo đảm tất cả transaction đã đạt cùng checkpoint trước khi tiếp tục.

Chọn primitive theo điều kiện cần biểu đạt:

- “Chờ tất cả worker sẵn sàng”: `CountDownLatch`.
- “Mở cổng bắt đầu cho tất cả”: `CountDownLatch`.
- “Tất cả transaction phải đọc xong trước khi ghi”: `CyclicBarrier` hoặc latch đếm số lần đọc hoàn tất.
- “Nhiều phase lặp lại với nhóm worker cố định”: `CyclicBarrier`.
- “Nhiều phase, số worker thay đổi”: `Phaser`.
- “Giới hạn tối đa N worker cùng vào”: `Semaphore`.
- “Chờ một tác vụ hoàn tất và lấy kết quả/lỗi”: `Future` hoặc `CompletableFuture`.

## 17. Quy trình xây dựng một kiểm thử đồng thời ổn định

1. Viết rõ lịch transaction cần tái hiện: transaction nào đọc hoặc khóa gì trước, rồi làm gì tiếp theo.
2. Xác định checkpoint tương ứng với các sự kiện database đã hoàn tất.
3. Chọn latch/barrier phù hợp với số phase và số worker.
4. Mỗi worker dùng connection riêng và transaction riêng.
5. Đặt timeout cho mọi `await`, `Future.get`, query và toàn bộ test.
6. Mở cổng trong `finally`, thu thập exception từ tất cả worker và không bỏ qua lỗi phụ.
7. Rollback transaction còn mở, đóng/discard connection và dừng executor.
8. Xác nhận trạng thái dữ liệu cuối cùng bằng truy vấn database.
9. Chạy lặp lại trên CI và trên DBMS thực tế được hỗ trợ để kiểm tra tính ổn định.

Đối với test write skew, barrier đặt sau các lần đọc là checkpoint chính. Đối với test deadlock, hai latch giúp chắc chắn mỗi transaction đã giữ khóa đầu tiên trước khi cả hai yêu cầu khóa thứ hai. Đối với test retry, có thể dùng latch để giữ một transaction tại thời điểm xác định, cho transaction khác tạo xung đột rồi mới thả transaction đầu tiếp tục.

## 18. Checklist trước khi dùng barrier/latch trong test database

- [ ] Đã mô tả chính xác lịch đọc–ghi hoặc thứ tự khóa muốn tái hiện.
- [ ] Tín hiệu được đặt sau khi câu SQL cần thiết hoàn tất, không chỉ sau khi thread bắt đầu.
- [ ] Mỗi transaction chạy trên một JDBC connection riêng.
- [ ] Connection pool và executor có đủ capacity cho tất cả worker đồng thời.
- [ ] Dùng `CountDownLatch` cho tín hiệu một lần và `CyclicBarrier` cho phase chung có thể lặp.
- [ ] Dùng `Phaser` khi số worker hoặc số phase thay đổi.
- [ ] Mọi `await()` và `Future.get()` đều có timeout.
- [ ] Latch được mở hoặc task được hủy trong nhánh cleanup để không treo worker.
- [ ] Xử lý `InterruptedException`, `BrokenBarrierException` và exception gốc từ worker.
- [ ] Transaction được commit/rollback rõ ràng; connection không sạch bị loại khỏi pool.
- [ ] Đã kiểm tra dữ liệu cuối cùng trong database, không chỉ dựa vào biến trong JVM.
- [ ] Test chạy lặp lại ổn định mà không dựa vào `Thread.sleep()` để tạo thứ tự.

Barrier và latch biến thời điểm trong kiểm thử đồng thời thành những checkpoint có thể xác nhận. Chúng giúp test tái hiện việc hai transaction cùng đọc, cùng giữ khóa hoặc cùng tiến đến một bước ghi theo đúng thứ tự mong muốn. Khi đặt tín hiệu sau thao tác database thực sự hoàn tất, dùng connection độc lập, giới hạn thời gian chờ và cleanup transaction trong mọi nhánh, bài kiểm thử sẽ ổn định hơn nhiều so với việc phỏng đoán lịch thực thi bằng `Thread.sleep()`.
