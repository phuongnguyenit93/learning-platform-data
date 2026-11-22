# Giới hạn tài nguyên ngoài bằng Semaphore và pool kết nối khi dùng Virtual Threads

## 1. Vấn đề: nhiều virtual thread không đồng nghĩa nhiều tài nguyên ngoài

Virtual Threads (ổn định từ Java 21) cho phép viết mã đồng bộ, blocking theo kiểu một tác vụ — một luồng, với chi phí luồng thấp hơn platform thread trong các công việc chờ I/O. Tuy nhiên, **virtual thread rẻ không làm database connection, socket, phiên kết nối, quota API hay dịch vụ phía ngoài trở nên vô hạn**.

Giả sử ứng dụng nhận 5.000 yêu cầu cùng lúc. Mỗi yêu cầu chạy trên một virtual thread và phải truy vấn một dịch vụ chỉ cho phép tối đa 20 lời gọi đồng thời. Nếu cứ gọi ngay mà không giới hạn, bên ngoài có thể quá tải, trả lỗi, tăng độ trễ hoặc tự từ chối kết nối. Cần tách hai loại giới hạn:

- **Độ đồng thời của tác vụ Java:** có thể có rất nhiều virtual thread đang sống, bao gồm những luồng đang chờ.
- **Độ đồng thời dùng tài nguyên ngoài:** chỉ cho phép một số hữu hạn tác vụ ở trong đoạn sử dụng tài nguyên tại cùng thời điểm.

**Nguyên tắc:** tạo virtual thread theo tác vụ; dùng `Semaphore` hoặc cơ chế cấp phát của **connection pool** để kiểm soát tài nguyên khan hiếm. Không tạo một “pool virtual threads” chỉ để giới hạn số tác vụ đang truy cập dịch vụ.

## 2. Semaphore là gì, giới hạn được điều gì?

`java.util.concurrent.Semaphore` giữ một số lượng **permit** (giấy phép logic). Mỗi lời gọi `acquire()` xin một permit; khi hết permit, bên gọi phải chờ. `release()` trả permit để một tác vụ khác có thể tiếp tục. Không có đối tượng “permit” vật lý nào được cấp: đây là bộ đếm và cơ chế đồng bộ.

Ví dụ `new Semaphore(3)` cho phép tối đa **ba tác vụ đã lấy permit nhưng chưa trả permit** ở trong đoạn bảo vệ cùng lúc. Một virtual thread bị chặn tại `acquire()` đang chờ quyền truy cập, chứ không giữ một kết nối thật. Đoạn chờ thường phù hợp với mô hình virtual thread vì Java có thể tạm dừng virtual thread và dành carrier cho việc khác.

```text
Nhiều tác vụ trên virtual threads
    ├── tác vụ A ── acquire ──► dùng dịch vụ ngoài ──► release
    ├── tác vụ B ── acquire ──► dùng dịch vụ ngoài ──► release
    ├── tác vụ C ── acquire ──► dùng dịch vụ ngoài ──► release
    ├── tác vụ D ── chờ permit ──────────────────────► ...
    └── tác vụ E ── chờ permit ──────────────────────► ...
                 Semaphore(3)
```

Điều quan trọng là **ranh giới giữ permit phải bao trọn đúng phần sử dụng tài nguyên cần giới hạn**. Nếu lấy permit trước lời gọi I/O nhưng trả ngay khi lời gọi bất đồng bộ vừa được khởi chạy, số thao tác thực sự đang chạy có thể vượt mức giới hạn. Với API bất đồng bộ, trả permit sau khi thao tác hoàn tất, kể cả thất bại hoặc hủy.

Các thao tác nên biết:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `acquire()` | Chờ đến khi lấy được một permit | Có thể ném `InterruptedException`; chưa lấy được thì không được `release()` |
| `tryAcquire()` | Thử lấy ngay, không chờ | Trả `false` khi thiếu permit; bản không timeout có thể vượt thứ tự chờ của semaphore công bằng |
| `tryAcquire(timeout, unit)` | Chờ tối đa một khoảng thời gian | Trả `false` khi hết thời gian, hoặc ném `InterruptedException` khi bị ngắt |
| `release()` | Tăng số permit sẵn có thêm một | `Semaphore` không kiểm tra người gọi có từng `acquire()`; trả thừa phá giới hạn |
| `availablePermits()` | Số permit đang sẵn có tại một thời điểm | Chỉ là ảnh chụp tức thời, không dùng để kiểm tra rồi mới `acquire()` |
| `new Semaphore(n, true)` | Yêu cầu chính sách chọn người chờ công bằng | Cân bằng thứ tự chờ với chi phí/throughput; không bảo đảm thứ tự bắt đầu tuyệt đối |

`Semaphore` giới hạn **số lượt sử dụng đồng thời**, không tự tạo, tái sử dụng, đóng hoặc kiểm tra tình trạng kết nối thật. Một semaphore cũng không phải cơ chế giới hạn **số request trên giây**: 10 permit có thể phục vụ nhiều hơn 10 request/giây nếu mỗi request hoàn tất rất nhanh.

## 3. Ví dụ Java 21+: 12 virtual threads, tối đa 3 lời gọi ngoài

Ví dụ độc lập dưới đây mô phỏng một dịch vụ I/O bằng `Thread.sleep(100)`. Trong ứng dụng thực tế, thay đoạn giả lập bằng lời gọi JDBC, HTTP client hoặc thao tác I/O cần giới hạn. Mọi tác vụ vẫn có virtual thread riêng; chỉ **ba** tác vụ tối đa được ở trong “vùng tài nguyên ngoài” cùng lúc.

Lưu thành `LimitExternalCalls.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class LimitExternalCalls {
    private static final int LIMIT = 3;
    private static final Semaphore GATE = new Semaphore(LIMIT, true);

    private static final AtomicInteger IN_FLIGHT = new AtomicInteger();
    private static final AtomicInteger PEAK = new AtomicInteger();
    private static final AtomicInteger COMPLETED = new AtomicInteger();

    private static void callExternalService() throws InterruptedException {
        // Nếu đang chờ mà bị interrupt, chưa sở hữu permit nào.
        GATE.acquire();
        try {
            int now = IN_FLIGHT.incrementAndGet();
            PEAK.accumulateAndGet(now, Math::max);
            try {
                // Mô phỏng một lời gọi I/O blocking.
                Thread.sleep(100);
                COMPLETED.incrementAndGet();
            } finally {
                IN_FLIGHT.decrementAndGet();
            }
        } finally {
            // Chỉ chạy sau khi acquire() đã thành công.
            GATE.release();
        }
    }

    public static void main(String[] args) throws Exception {
        List<Future<?>> futures = new ArrayList<>();

        try (ExecutorService executor =
                 Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 12; i++) {
                futures.add(executor.submit(() -> {
                    callExternalService();
                    return null;
                }));
            }

            // Nhận lỗi từ từng tác vụ, không chỉ chờ executor kết thúc.
            for (Future<?> future : futures) {
                future.get();
            }
        }

        System.out.println("completed=" + COMPLETED.get());
        System.out.println("active=" + IN_FLIGHT.get());
        System.out.println("peak<=3: " + (PEAK.get() <= LIMIT));
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac LimitExternalCalls.java
java LimitExternalCalls
```

```text
completed=12
active=0
peak<=3: true
```

Ba dòng trên là kết quả xác định khi chương trình kết thúc bình thường. Giá trị thực tế của `PEAK` có thể từ 1 đến 3 tùy cách lập lịch; điều cần chứng minh là **không bao giờ lớn hơn 3**. `Future.get()` đợi tác vụ và chuyển lỗi của tác vụ thành `ExecutionException` tại luồng gọi, tránh tình trạng tưởng rằng tất cả thành công dù có tác vụ lỗi. `ExecutorService` trong `try-with-resources` đóng sau khi các tác vụ hoàn thành.

Phân tích đoạn bảo vệ:

1. Lấy permit **trước** khi tăng `IN_FLIGHT` hoặc truy cập dịch vụ ngoài.
2. Dùng `try/finally` để giảm bộ đếm hoạt động ngay cả khi I/O lỗi hoặc bị ngắt.
3. Dùng `try/finally` bên ngoài để trả permit **đúng một lần** sau một `acquire()` thành công.
4. Không đặt `release()` vào `finally` bao cả lời gọi `acquire()` theo cách có thể chạy khi `acquire()` ném `InterruptedException` trước khi lấy được permit.

`AtomicInteger` chỉ giúp phép đo an toàn giữa các luồng; **`Semaphore` mới là cơ chế bảo vệ tài nguyên**. Đặt semaphore trong một đối tượng được chia sẻ giữa mọi tác vụ truy cập cùng hạn mức. Nếu mỗi yêu cầu tự tạo `new Semaphore(3)`, mỗi yêu cầu có quota riêng và giới hạn toàn hệ thống không còn hiệu lực.

## 4. Chờ có hạn, xử lý timeout và ngắt đúng cách

`acquire()` có thể chờ vô thời hạn nếu không permit nào trở lại. Trong đường xử lý yêu cầu, hãy cân nhắc ngân sách thời gian chờ, giới hạn tải và chính sách báo lỗi. Ví dụ dưới đây là **phương thức minh họa**, giả định đã có một `Semaphore gate` dùng chung và phương thức blocking `callRemote()` cần bảo vệ:

```java
String callWithTimeout(Semaphore gate) throws InterruptedException {
    boolean acquired = gate.tryAcquire(500, java.util.concurrent.TimeUnit.MILLISECONDS);
    if (!acquired) {
        throw new IllegalStateException("Dich vu dang qua tai: het thoi gian cho permit");
    }
    try {
        return callRemote(); // Phương thức do ứng dụng cung cấp.
    } finally {
        gate.release();
    }
}
```

`callRemote()` ở đây không được khai báo nên đoạn mã này **không phải chương trình chạy độc lập**. Trong chương trình thật, lời gọi đó có thể ném ngoại lệ đặc thù của HTTP/JDBC; `finally` vẫn phải trả permit. Nếu bị interrupt trong lúc `tryAcquire(...)` đang chờ, Java ném `InterruptedException` và **không có permit nào cần trả**. Khi tác vụ xử lý `InterruptedException` thay vì truyền tiếp, thường cần khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` và kết thúc sớm thay vì tiếp tục làm I/O.

Timeout chờ permit không thay cho timeout kết nối, truy vấn hay HTTP. Chúng là các thời hạn độc lập: hết thời gian chờ permit, thời gian tạo kết nối và thời gian thực thi lệnh đều cần được quản lý riêng. Cũng không nên retry vô hạn sau khi hết permit; mỗi lần retry làm tăng lượng tác vụ chờ.

## 5. Connection pool đã quản lý số kết nối thật

**Connection pool** quản lý tập hữu hạn kết nối vật lý để tái sử dụng. Mượn một kết nối từ pool thường làm giảm số kết nối rảnh; khi trả lại, kết nối có thể phục vụ tác vụ khác. Pool có các chính sách riêng như số kết nối tối đa, timeout khi mượn, kiểm tra kết nối, vòng đời và thu hồi.

Với JDBC, ứng dụng thường lấy kết nối từ `javax.sql.DataSource`; **bản thân interface `DataSource` không bảo đảm có pool** — phải cấu hình một implementation pooling thực sự. Ví dụ minh họa:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

long countUsers(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement("SELECT COUNT(*) FROM users");
         ResultSet resultSet = statement.executeQuery()) {
        resultSet.next();
        return resultSet.getLong(1);
    }
}
```

Đây là **phương thức minh họa**, không phải lớp chạy độc lập; cần bảng `users` và một `DataSource` đã cấu hình. Khi dùng connection pool, `connection.close()` thông thường **trả kết nối về pool**; đóng tài nguyên qua `try-with-resources` là bắt buộc để pool không cạn kiệt. `DataSource.getConnection()` có thể chờ một kết nối rảnh hoặc lỗi khi hết thời hạn, tùy pool. Mỗi tác vụ cần mượn và trả kết nối trong phạm vi ngắn nhất có thể; không gắn một kết nối suốt vòng đời virtual thread chỉ vì luồng nhẹ.

**Một pool có kích thước tối đa 10 vốn đã giới hạn số kết nối mà nó cấp cùng lúc.** Không mặc định bọc thêm `Semaphore(10)` quanh việc mượn connection: sẽ có hai hàng chờ và hai cơ chế timeout, có thể làm hệ thống khó điều chỉnh và chẩn đoán. Chỉ thêm semaphore nếu nó bảo vệ **một giới hạn độc lập** mà pool không nắm được, chẳng hạn DB chỉ cho phép 10 truy vấn nặng đồng thời dù pool có 30 kết nối, hoặc API đi kèm còn giới hạn số yêu cầu xử lý.

| Tình huống | Công cụ chính | Lý do |
| --- | --- | --- |
| API ngoài chỉ nhận 8 tác vụ cùng lúc | `Semaphore(8)` dùng chung | Giới hạn lời gọi logic; không sở hữu kết nối |
| Database chỉ cấp tối đa 20 kết nối | Pool có `maximumPoolSize=20` (tên tùy implementation) | Pool quản lý, tái sử dụng và cấp phát kết nối thật |
| 20 DB connections nhưng chỉ được chạy 5 truy vấn nặng cùng lúc | Pool 20 + semaphore 5 **riêng cho đường truy vấn nặng** | Hai giới hạn độc lập, cần đo timeout ở cả hai chỗ |
| Bên ngoài quy định 100 request/giây | Rate limiter | Semaphore giới hạn concurrent in-flight, không đặt quota theo thời gian |
| Nguồn phát sinh tác vụ vượt quá khả năng chờ của hệ thống | Bounded admission/queue và backpressure | Semaphore không tự giới hạn số virtual thread đang chờ |

## 6. Chọn giới hạn phù hợp với tài nguyên

Giới hạn phải dựa trên **năng lực và quota thật** của bên ngoài, không dựa trên số virtual thread có thể tạo hoặc số core của máy Java. Những câu hỏi cần trả lời:

- Dịch vụ/DB cho phép tối đa bao nhiêu connection, request đang xử lý hoặc phiên hoạt động? Hạn mức này được chia sẻ với những ứng dụng nào?
- Mỗi tác vụ giữ tài nguyên trong bao lâu, tỷ lệ request lỗi/timeout bao nhiêu, và lượng tác vụ xếp hàng tăng ra sao khi tải tăng?
- Cùng một yêu cầu có thể chiếm đồng thời bao nhiêu tài nguyên khác nhau? Có nguy cơ hai đường xử lý giữ A chờ B và giữ B chờ A hay không?
- Hệ thống cần phản hồi “đang bận” sau bao lâu thay vì chờ mãi?

Định luật Little cho hệ ổn định cho trực giác: **số tác vụ trung bình đang xử lý ≈ throughput × thời gian xử lý trung bình**. Ví dụ dịch vụ cần 0,2 giây mỗi lời gọi ở mức 50 lời gọi/giây thì trung bình khoảng 10 lời gọi đang chạy. Đây là phép ước lượng để bắt đầu đo đạc, **không phải công thức tự động chọn permit**, vì còn giới hạn dịch vụ, phân bố đuôi độ trễ, số replica và đường đi của request.

Giữ permit trong đoạn thực sự cần quota: không nên khóa slot khi đang parse JSON độc lập, đọc cache hay chuẩn bị dữ liệu dài dòng. Ngược lại, nếu một workflow gồm hai I/O đều tiêu thụ cùng hạn mức trong toàn bộ khoảng thời gian, phải xác định rõ lúc nào slot thực sự được giữ. Nếu cấu hình nhiều instance, **mỗi instance có semaphore riêng**: 5 replica × 8 permit có thể gây 40 tác vụ đồng thời lên một dịch vụ chỉ cho phép 8. Khi quota là toàn hệ thống, cần chia ngân sách cho replica hoặc một cơ chế phối hợp phân tán; semaphore nội bộ JVM không tự phối hợp giữa các process.

## 7. Tình huống lỗi và cách khắc phục

**Quên trả permit.** Một số lần ném exception hoặc return sớm làm rò permit; sau đủ lần, toàn bộ tác vụ tiếp theo chờ vô hạn. Khắc phục bằng `try/finally` ngay sau lần lấy permit thành công, gói việc mượn/trả tài nguyên thật trong `try-with-resources`.

**Trả permit khi chưa lấy hoặc trả hai lần.** `Semaphore.release()` không buộc caller là người sở hữu permit và không chặn việc trả thừa. Kết quả có thể cho phép vượt qua hạn mức ban đầu. Không viết `release()` trong nhánh timeout/interrupt chưa acquire thành công; không trao trách nhiệm release cho hai tầng cùng lúc.

**Dùng `availablePermits() > 0` để quyết định vào.** Giá trị có thể thay đổi ngay khi kiểm tra; một tác vụ khác đã lấy permit. Hãy gọi trực tiếp `acquire()` hoặc `tryAcquire()` để thao tác lấy permit được đồng bộ.

**Dùng fixed thread pool để điều tiết virtual threads.** Giới hạn worker thread không diễn đạt trực tiếp số lượt dùng dịch vụ. Một pool virtual threads cũng phá mục tiêu mỗi tác vụ một virtual thread. Dùng semaphore ngay quanh đoạn I/O; giữ executor tạo virtual threads theo tác vụ.

**Đặt semaphore trùng kích thước với connection pool ở mọi nơi.** Thừa hàng chờ và timeout, khó hiểu chỗ nào cạn trước. Kiểm tra xem pool đã áp đúng giới hạn kết nối chưa; chỉ thêm gate nếu có quota nghiệp vụ/ngoài riêng.

**Tăng permit để giảm hàng chờ mà không đo hệ thống ngoài.** Có thể biến hàng chờ trong Java thành hàng chờ lâu hơn ở DB/API, tăng timeout và lỗi. Giới hạn là công cụ bảo vệ phía ngoài; cần đồng thời kiểm soát lượng công việc đầu vào.

**Cho rằng FIFO luôn tuyệt đối.** `new Semaphore(n, true)` cấp permit cho người chờ theo điểm xếp hàng nội bộ, nhưng không hứa thứ tự bắt đầu/thành công của các thao tác I/O. `tryAcquire()` không timeout có thể giành permit trước người chờ ngay cả khi `fair=true`; xem yêu cầu fairness thực tế trước khi dùng.

**Giữ permit khi làm việc không liên quan.** Nếu chờ lock khác, chờ phản hồi không dùng tài nguyên hoặc làm CPU dài trong đoạn bảo vệ, thông lượng hữu ích giảm. Đo thời gian giữ permit và thu hẹp phạm vi theo quota cần bảo vệ; tránh nhiều gate với thứ tự khóa không nhất quán.

## 8. Quan sát và kiểm chứng khi vận hành

Theo dõi riêng **lượng công việc**, **thời gian chờ**, và **tài nguyên thật**:

- Semaphore: số slot đang dùng, thời gian chờ `acquire`, số lần `tryAcquire` timeout, số tác vụ đang chờ; `getQueueLength()` chỉ là **ước lượng**, không phải bộ đếm chính xác để điều tiết.
- Connection pool: active/idle/max connections, số yêu cầu chờ mượn connection, timeout khi mượn, thời gian giữ connection, rò connection.
- Dịch vụ ngoài: số lời gọi đang chạy, throughput, timeout, tỷ lệ lỗi, p95/p99 latency, throttling do quota.
- Tải đầu vào: số tác vụ đang chờ ở cổng nhận request, lượng bộ nhớ dành cho tác vụ/đầu vào chưa được xử lý. Virtual thread nhẹ nhưng không vô hạn bộ nhớ.

Một bài kiểm tra tốt là phát sinh đồng thời nhiều hơn số permit, đo `inFlight` của chính đoạn thao tác ngoài và khẳng định `peak <= limit`. Sau đó cố ý tạo exception, interrupt, timeout để kiểm tra permit vẫn trở về mức ban đầu và connection được trả. Nếu thử với pool, kiểm tra số connection vật lý không vượt cấu hình. Không dùng số lượng virtual thread đang sống để suy ra số connection đang sử dụng.

## 9. Ghi nhớ

- Virtual thread giúp giữ mô hình code blocking dễ đọc khi có nhiều tác vụ I/O; **nó không tăng quota của database/API**.
- Semaphore bảo vệ một **đoạn công việc có giới hạn concurrent in-flight**; `acquire` thành công mới được `release`, đúng một lần, trong `finally`.
- Connection pool quản lý **kết nối thật** và đã có cơ chế chặn/timeout cấp phát; thường không cần thêm semaphore có cùng nhiệm vụ.
- Timeout, ngắt, backpressure, giới hạn toàn hệ thống và observability là những phần cần thiết để giới hạn tài nguyên vận hành an toàn.

## Tài liệu tham khảo

- Oracle, [Virtual Threads — Java SE 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): hướng dẫn virtual threads, semaphore và connection pools.
- Oracle, [`Semaphore` Java API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): các thao tác và bảo đảm của semaphore.
- Oracle, [`Executors` Java API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor()`.
