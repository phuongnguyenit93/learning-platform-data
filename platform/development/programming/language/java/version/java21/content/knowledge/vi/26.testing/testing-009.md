# Kiểm thử giới hạn connection, semaphore và phản ứng khi overload

Khi một dịch vụ có nhiều request đồng thời, cần kiểm tra ba giới hạn riêng: số connection mà pool có thể cấp, số tác vụ được phép đi vào một vùng xử lý cùng lúc và cách hệ thống phản hồi khi không còn capacity. Ba giới hạn này có liên quan nhưng không thể thay thế cho nhau.

Một semaphore có thể giới hạn số tác vụ đang truy cập database, nhưng nó không chứng minh connection pool thực sự không cấp quá số connection đã cấu hình. Tương tự, connection pool có giới hạn vẫn không bảo đảm ứng dụng phản hồi nhanh khi hàng nghìn request đang chờ lấy connection. Bài kiểm thử cần xác minh từng giới hạn và hành vi overload ở đúng tầng sở hữu nó.

## 1. Phân biệt connection limit, concurrency limit và admission control

| Cơ chế | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| Connection pool | Số connection vật lý/logic mà pool cấp đồng thời | HikariCP giới hạn connection JDBC đang được mượn |
| Semaphore | Số tác vụ được vào một vùng xử lý hoặc sử dụng một tài nguyên cùng lúc | Tối đa 20 tác vụ gọi một dịch vụ downstream |
| Admission control | Số công việc được chấp nhận hoặc đưa vào hệ thống | Từ chối request mới khi hết slot, queue đầy hoặc deadline không còn đủ |
| Rate limiter | Số request được phép trong một khoảng thời gian | Giới hạn 100 request mỗi giây theo client |

Connection limit và concurrency limit không nhất thiết bằng nhau. Một request có thể mở nhiều connection; nhiều request có thể dùng chung một connection theo cơ chế multiplexing; hoặc một request có thể không cần connection nào trong phần lớn vòng đời.

Đặc biệt, HTTP/2 có thể multiplex nhiều stream trên cùng một TCP connection. Vì vậy, số request đang chạy không đồng nghĩa với số socket đang mở. Khi kiểm thử HTTP client, cần phân biệt giới hạn request đồng thời ở tầng ứng dụng với giới hạn connection thực tế.

JDK 21 HttpClient không cung cấp API public tiêu chuẩn để đặt trực tiếp kích thước connection pool tối đa. Nếu cần giới hạn số request đồng thời gửi đi, hãy kiểm soát ở tầng ứng dụng bằng semaphore hoặc cơ chế admission control; không xem đó là bằng chứng về số TCP connection.

## 2. Xác định invariant cần kiểm thử

Trước khi viết test, hãy ghi rõ điều hệ thống phải luôn giữ đúng:

- Số connection đang được mượn không vượt maximumPoolSize của pool.
- Số tác vụ đi qua vùng được bảo vệ không vượt số permit của semaphore.
- Khi hết capacity, request mới bị từ chối hoặc chỉ chờ trong một khoảng thời gian có giới hạn.
- Mọi permit và connection được trả lại khi xử lý thành công, thất bại, timeout hoặc bị hủy.
- Hệ thống không giữ một queue không giới hạn làm latency và memory tăng không kiểm soát.
- Response overload có status và header nhất quán với chính sách API.

Các invariant này nên được kiểm tra bằng số liệu có thể quan sát: active connection, active task, peak concurrency, số request bị từ chối, thời gian chờ và kết quả HTTP.

## 3. Dùng Semaphore để giới hạn tác vụ đồng thời

Semaphore quản lý một số permit. Tác vụ phải lấy được permit trước khi đi vào vùng xử lý; sau khi rời vùng đó, permit phải được trả lại trong finally.

~~~java
import java.util.concurrent.Semaphore;

final class DownstreamGate {
    private final Semaphore permits = new Semaphore(20);

    Result callDownstream() throws Exception {
        permits.acquire();
        try {
            return invokeRemoteService();
        } finally {
            permits.release();
        }
    }

    private Result invokeRemoteService() {
        // Gọi dịch vụ downstream.
        return new Result();
    }

    static final class Result {}
}
~~~

Đoạn mã cho phép tối đa 20 tác vụ cùng ở trong vùng gọi downstream. Tác vụ thứ 21 trở đi sẽ chờ permit. Với virtual thread, thao tác chờ trên semaphore có thể park virtual thread và nhường carrier; tuy nhiên, số virtual thread chờ vẫn tiêu thụ bộ nhớ và không thay thế backpressure ở đầu vào.

Nếu muốn từ chối ngay khi đã đủ tải, dùng tryAcquire():

~~~java
if (!permits.tryAcquire()) {
    return overloadedResponse();
}
try {
    return invokeRemoteService();
} finally {
    permits.release();
}
~~~

Nếu muốn cho phép chờ trong một khoảng thời gian giới hạn, dùng tryAcquire(timeout, unit). Chọn timeout theo deadline còn lại của request; không cộng thêm thời gian chờ dài hơn thời gian mà caller có thể chấp nhận.

Không gọi release() ở nhiều nhánh hoặc trước khi tài nguyên thực sự được trả lại. Nếu acquire thành công nhưng nhánh lỗi không release, permit sẽ bị rò rỉ và dịch vụ dần từ chối mọi request. Nếu release nhiều hơn số lần acquire, giới hạn thực tế có thể bị phá vỡ.

Semaphore có thể được tạo với chế độ fair để ưu tiên thread chờ lâu hơn, nhưng fairness có thể giảm throughput và không phải cam kết thứ tự xử lý tuyệt đối của toàn ứng dụng. Chỉ bật fairness khi thứ tự chờ là một yêu cầu cần đo và kiểm thử.

## 4. Kiểm thử semaphore không cho vượt giới hạn

Test nên đồng bộ bằng latch để giữ một nhóm tác vụ bên trong vùng được bảo vệ, thay vì dựa vào Thread.sleep() và hy vọng các thread chạy đúng thời điểm. Java 21 cho phép dùng virtual thread per task trong test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class SemaphoreLimitTest {
    @Test
    void neverRunsMoreTasksThanThereArePermits() throws Exception {
        int limit = 3;
        int taskCount = 12;
        Semaphore permits = new Semaphore(limit);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        CountDownLatch entered = new CountDownLatch(limit);
        CountDownLatch releaseWorkers = new CountDownLatch(1);

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> futures = IntStream.range(0, taskCount)
                    .mapToObj(ignored -> executor.submit(() -> {
                        permits.acquire();
                        try {
                            int now = active.incrementAndGet();
                            peak.accumulateAndGet(now, Math::max);
                            entered.countDown();
                            if (!releaseWorkers.await(10, TimeUnit.SECONDS)) {
                                throw new IllegalStateException("Test timed out");
                            }
                        } finally {
                            active.decrementAndGet();
                            permits.release();
                        }
                        return null;
                    }))
                    .toList();

            try {
                assertTrue(entered.await(5, TimeUnit.SECONDS));
                assertEquals(limit, active.get());
            } finally {
                releaseWorkers.countDown();
            }

            for (Future<?> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }
        }

        assertTrue(peak.get() <= limit);
        assertEquals(0, active.get());
    }
}
~~~

Ba điểm làm cho test này có tính xác định:

1. entered chỉ về 0 khi đủ ba tác vụ đã lấy permit và bước vào vùng được bảo vệ.
2. releaseWorkers giữ các tác vụ đó ở bên trong, để test có thể quan sát active trước khi cho chúng thoát.
3. finally luôn mở latch, kể cả khi assertion thất bại, để các virtual thread không bị bỏ lại chờ trong lúc executor đóng.

peak ghi nhận số tác vụ hoạt động lớn nhất. Test xác nhận peak không vượt limit và không còn tác vụ hoạt động sau khi tất cả future hoàn tất.

## 5. Kiểm thử overload khi không còn permit

Nếu chính sách là từ chối ngay, test phải xác nhận request bị từ chối và công việc downstream không được gọi. Ví dụ một handler nhỏ:

~~~java
import java.util.concurrent.Semaphore;

@FunctionalInterface
interface Work {
    void run() throws Exception;
}

record HttpResult(int status, String retryAfter) {}

final class LimitedHandler {
    private final Semaphore permits;
    private final Work work;

    LimitedHandler(Semaphore permits, Work work) {
        this.permits = permits;
        this.work = work;
    }

    HttpResult handle() throws Exception {
        if (!permits.tryAcquire()) {
            return new HttpResult(503, "1");
        }

        try {
            work.run();
            return new HttpResult(200, null);
        } finally {
            permits.release();
        }
    }
}
~~~

Test giữ trước permit duy nhất để tạo trạng thái bão hòa:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;

class OverloadResponseTest {
    @Test
    void rejectsImmediatelyWhenCapacityIsExhausted() throws Exception {
        Semaphore permits = new Semaphore(1);
        AtomicBoolean workCalled = new AtomicBoolean();
        LimitedHandler handler =
                new LimitedHandler(permits, () -> workCalled.set(true));

        assertEquals(1, permits.availablePermits());
        permits.acquire();
        try {
            HttpResult result = handler.handle();

            assertEquals(503, result.status());
            assertEquals("1", result.retryAfter());
            assertFalse(workCalled.get());
        } finally {
            permits.release();
        }
    }
}
~~~

Trong HTTP server thật, handler cần chuyển HttpResult thành status code và header tương ứng. 503 Service Unavailable phù hợp khi chính dịch vụ tạm thời không đủ capacity; Retry-After có thể hướng dẫn caller thời điểm thử lại. Nếu đang áp dụng quota hoặc rate limit cho một client cụ thể, 429 Too Many Requests thường phù hợp hơn.

Không trả 200 OK rồi âm thầm bỏ request khi overload. Nếu từ chối, hãy trả lỗi có ý nghĩa, ghi metric và để client có chính sách retry với backoff cùng jitter. Retry ngay lập tức từ tất cả client có thể làm hệ thống quá tải nặng hơn.

## 6. Kiểm thử permit được trả lại khi xử lý lỗi

Test overload cần đi cùng test bảo đảm permit không bị rò rỉ khi công việc ném exception:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.util.concurrent.Semaphore;
import org.junit.jupiter.api.Test;

class SemaphoreReleaseTest {
    @Test
    void releasesPermitWhenWorkThrows() {
        Semaphore permits = new Semaphore(1);
        LimitedHandler handler = new LimitedHandler(
                permits,
                () -> {
                    throw new IOException("downstream failed");
                }
        );

        assertThrows(IOException.class, handler::handle);
        assertTrue(permits.tryAcquire());
        permits.release();
    }
}
~~~

Test này xác nhận permit được trả lại ngay cả khi downstream thất bại. Nên bổ sung các trường hợp tương tự cho timeout và interruption nếu code có đường xử lý riêng cho chúng. finally vẫn là vị trí phù hợp để release permit sau khi acquire thành công.

Nếu semaphore đại diện cho một connection đang được mượn, permit phải được trả sau khi connection đã đóng hoặc được trả về pool. Không release permit ngay khi bắt đầu đóng connection trong khi tài nguyên vẫn chưa sẵn sàng để tác vụ khác dùng.

## 7. Kiểm thử giới hạn connection pool thực tế

Muốn kiểm thử maximumPoolSize, hãy kiểm thử chính pool đang được ứng dụng sử dụng. Không thể thay test pool bằng một test semaphore vì hai thành phần có vòng đời và hành vi timeout khác nhau.

Ví dụ sau dùng HikariCP với H2 trong test. Hãy thêm HikariCP, H2 và JUnit Jupiter vào test dependencies theo dependency management của dự án:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.SQLTransientConnectionException;
import org.junit.jupiter.api.Test;

class ConnectionPoolLimitTest {
    @Test
    void doesNotLeaseMoreConnectionsThanConfigured() throws Exception {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:h2:mem:pool-limit;DB_CLOSE_DELAY=-1");
        config.setMaximumPoolSize(2);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(500);

        try (HikariDataSource dataSource = new HikariDataSource(config);
             Connection first = dataSource.getConnection();
             Connection second = dataSource.getConnection()) {

            assertEquals(
                    2,
                    dataSource.getHikariPoolMXBean().getActiveConnections()
            );

            assertThrows(
                    SQLTransientConnectionException.class,
                    () -> dataSource.getConnection()
            );

            assertEquals(
                    2,
                    dataSource.getHikariPoolMXBean().getActiveConnections()
            );
        }
    }
}
~~~

Test giữ hai connection chưa đóng để pool không thể cấp chúng cho request thứ ba. Request thứ ba chờ tối đa theo connectionTimeout; khi hết thời gian, HikariCP ném SQLTransientConnectionException. Sau đó test xác nhận số connection active vẫn không vượt hai.

Timeout trong test chỉ để làm test kết thúc nhanh, không phải cấu hình khuyến nghị cho production. Trong ứng dụng thực, hãy chọn connectionTimeout dựa trên deadline request, thời gian phản hồi database và ngân sách chờ tổng thể.

Test với H2 xác nhận hành vi giới hạn của HikariCP trong môi trường test; nó không thay thế integration test với database engine và JDBC driver production. Với pool khác, dùng API metrics và loại exception tương ứng của pool đó. Cần xác nhận cả số connection active, số connection idle, số thread đang chờ và thời gian lấy connection; chỉ kiểm tra số connection tối đa chưa đủ để đánh giá overload.

## 8. Phân biệt giới hạn pool với giới hạn request HTTP

Một connection pool JDBC thường cấp một connection cho mỗi borrower trong một khoảng thời gian. HTTP client có thể tái sử dụng keep-alive connection hoặc multiplex nhiều stream trên HTTP/2. Vì vậy:

- maximumPoolSize = 10 của JDBC có ý nghĩa là pool không cho mượn quá 10 connection cùng lúc.
- Semaphore(10) quanh lời gọi HTTP có ý nghĩa là tối đa 10 tác vụ đi qua vùng đó cùng lúc.
- Semaphore(10) không khẳng định có đúng tối đa 10 TCP socket; HTTP client có thể dùng ít socket hơn nhờ reuse hoặc multiplexing.
- Giới hạn số request được nhận tại ingress là một chính sách admission control khác nữa.

Nếu dùng java.net.http.HttpClient, hãy đo request đang in-flight, latency, timeout và số connection quan sát được ở tầng server/network. Đừng dựa vào thuộc tính nội bộ không được public API cam kết để kiểm soát pool connection của JDK.

## 9. Kiểm thử bounded waiting thay vì queue vô hạn

Semaphore.acquire() chờ cho đến khi có permit hoặc thread bị interrupt. Nếu hệ thống nhận request không giới hạn và tất cả request đều chờ acquire, số tác vụ đang chờ có thể tăng cao. Virtual thread giúp mỗi tác vụ chờ rẻ hơn platform thread, nhưng không làm bộ nhớ và deadline trở nên vô hạn.

Nếu muốn chờ có giới hạn:

~~~java
boolean acquired = permits.tryAcquire(100, TimeUnit.MILLISECONDS);
if (!acquired) {
    return new HttpResult(503, "1");
}

try {
    return processRequest();
} finally {
    permits.release();
}
~~~

Test nên xác nhận:

- Request lấy được permit khi permit được trả trong khoảng chờ cho phép.
- Request bị từ chối khi hết thời gian chờ.
- Thời gian chờ không vượt quá ngân sách hợp lý của endpoint, có xét sai số scheduling.
- Interruption được truyền hoặc xử lý theo hợp đồng của tầng gọi.

Không kiểm thử timeout bằng cách yêu cầu thời gian thực thi phải bằng chính xác 100 ms. Scheduling, tải CI và độ phân giải clock có thể làm thời gian đo dao động. Hãy kiểm tra kết quả timeout và dùng biên dung sai hợp lý khi cần đo latency.

## 10. Kiểm thử overload ở cấp HTTP

Khi đã kiểm tra lớp admission controller, cần có integration test cho endpoint để xác nhận trạng thái HTTP thực sự được gửi:

1. Giữ toàn bộ permit bằng một request test đang chờ trong handler.
2. Gửi request thứ hai tới endpoint.
3. Xác nhận request thứ hai nhận 503 Service Unavailable (hoặc 429 nếu chính sách là quota theo client).
4. Kiểm tra header Retry-After nếu endpoint công bố header đó.
5. Xác nhận downstream mock không nhận request thứ hai.
6. Nhả latch để request đầu tiên kết thúc và xác nhận permit được trả lại.
7. Gửi request mới và xác nhận endpoint phục hồi, trả response thành công.

Giữ request đầu tiên bằng CountDownLatch hoặc test double có điều khiển thay vì sleep. Nhờ vậy, test tạo được trạng thái saturation một cách xác định và không phụ thuộc timing ngẫu nhiên.

Với HTTP server tích hợp, cần kiểm tra cả body lỗi, content type, status, header và việc đóng response body. Đừng chỉ gọi trực tiếp method handler rồi suy luận rằng HTTP layer sẽ ánh xạ kết quả đúng.

## 11. Kiểm thử dưới tải và theo dõi các chỉ số

Unit test chứng minh invariant ở quy mô nhỏ; load test giúp tìm giới hạn của toàn hệ thống. Tăng dần số client/request đồng thời và theo dõi:

| Chỉ số | Điều cần quan sát |
|---|---|
| Active/idle connections | Pool có giữ đúng giới hạn và có connection bị giữ quá lâu không |
| Pending borrowers / waiters | Có bao nhiêu request đang chờ connection hoặc permit |
| Semaphore active permits | Số tác vụ đi vào vùng giới hạn có vượt capacity không |
| Rejected requests | Tỷ lệ 503/429 khi hệ thống bão hòa |
| Request latency | p50, p95, p99 và thời gian chờ permit/connection |
| Throughput | Số request hoàn tất mỗi giây |
| Timeout và lỗi downstream | Hệ thống có chuyển lỗi tài nguyên thành lỗi API phù hợp không |
| Heap và thread | Queue/waiter có làm tăng bộ nhớ hoặc số virtual thread quá mức không |

Một kịch bản load test hữu ích gồm:

- Tải dưới capacity: request được xử lý bình thường, không có reject ngoài dự kiến.
- Tải gần capacity: latency tăng trong giới hạn cho phép, số active connection/permit chạm ngưỡng.
- Tải vượt capacity: số active không vượt ngưỡng, request dư bị chờ có giới hạn hoặc bị từ chối.
- Downstream chậm hoặc lỗi: permit/connection cuối cùng được trả, hệ thống phục hồi sau khi dependency khỏe lại.
- Burst ngắn: hệ thống xử lý được burst trong queue budget hoặc từ chối có kiểm soát, không tạo backlog vô hạn.

Không chỉ nhìn throughput trung bình. Một hệ thống có throughput cao nhưng p99 latency tăng vô hạn hoặc queue không giảm sau burst vẫn có thể đang overload.

## 12. Những lỗi thường gặp khi viết test

| Lỗi trong test | Vì sao không đáng tin | Cách sửa |
|---|---|---|
| Dùng Thread.sleep() để hy vọng đủ task đã chạy | Timing phụ thuộc máy và tải test | Dùng CountDownLatch, CyclicBarrier hoặc test double có điều khiển |
| Chỉ kiểm tra availablePermits() một lần | Không chứng minh peak concurrency dưới tải | Đếm active/peak trong vùng được bảo vệ |
| Không test đường exception | Permit có thể bị leak khi downstream lỗi | Dùng test xác nhận permit được release trong finally |
| Dùng semaphore thay cho test connection pool | Không xác nhận pool thực tế giữ đúng maximum size | Giữ connection thật từ pool và kiểm tra lần mượn tiếp theo |
| Giả định request đồng thời bằng số TCP connection | HTTP/2 multiplexing và keep-alive làm hai số khác nhau | Đo từng tầng riêng |
| Chỉ test unit handler, bỏ qua HTTP integration | Status/header/body có thể ánh xạ sai | Gửi request thật tới endpoint test |
| Retry liên tục ngay khi nhận 503 | Có thể tạo retry storm | Dùng backoff, jitter và giới hạn retry |
| Chỉ đo throughput | Bỏ qua queue và tail latency | Theo dõi p95/p99, wait time, reject và backlog |

## 13. Checklist trước khi phát hành

- [ ] Xác định rõ giới hạn connection pool, semaphore và admission control.
- [ ] Kiểm thử connection pool thật với số connection đang được mượn đạt maximum.
- [ ] Dùng latch để chứng minh peak concurrency không vượt permit limit.
- [ ] Kiểm thử overload khi không còn permit và xác nhận downstream không bị gọi.
- [ ] Kiểm thử permit được trả khi thành công, exception, timeout và interruption.
- [ ] Xác nhận thời gian chờ connection/permit nằm trong deadline của request.
- [ ] Kiểm tra HTTP status, body và Retry-After khi bị từ chối.
- [ ] Kiểm tra endpoint phục hồi sau khi tải giảm và tài nguyên được trả.
- [ ] Chạy load test dưới, gần và vượt capacity.
- [ ] Theo dõi p95/p99 latency, throughput, active connection, waiter, reject và timeout.
- [ ] Đảm bảo queue và retry có giới hạn để tránh overload lan truyền.

Kiểm thử giới hạn tài nguyên phải xác minh cả capacity lẫn hành vi khi capacity cạn. Connection pool bảo vệ số connection được cấp; semaphore giới hạn vùng xử lý đồng thời; admission control quyết định request nào được nhận hoặc bị từ chối. Khi test riêng từng tầng bằng cơ chế đồng bộ xác định và sau đó kiểm thử tích hợp dưới tải, hệ thống có thể giữ giới hạn, trả lỗi overload nhất quán và phục hồi an toàn khi dependency chậm hoặc ngừng hoạt động.
