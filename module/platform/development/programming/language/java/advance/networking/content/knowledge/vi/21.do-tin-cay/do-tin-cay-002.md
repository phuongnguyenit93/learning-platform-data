# Ngân sách thời gian cho toàn yêu cầu, từng thao tác và thời gian nhàn rỗi trong Java Networking

## 1. Vì sao một request vẫn có thể treo dù đã cấu hình timeout?

Một Java service gọi API bên ngoài. Nhóm phát triển đặt `connectTimeout(2 giây)` rồi cho rằng yêu cầu nào cũng kết thúc trong 2 giây. Trên thực tế, TCP connection có thể được thiết lập chỉ trong 50 ms, nhưng server chậm trả headers, tiếp tục gửi response body từng byte, hoặc ứng dụng mất thời gian parse/đối soát và retry. **Connect timeout không phải tổng thời gian của một yêu cầu.**

Một lỗi ngược lại: đặt `Socket.setSoTimeout(500)` rồi kết luận tải tệp sẽ bị hủy nếu quá 500 ms. Nếu server liên tục gửi thêm byte trong mỗi khoảng dưới 500 ms, mỗi lần `read()` có thể thành công, nhưng cả file mất hàng phút. **Read timeout/idle timeout không phải deadline tổng.**

Ba khái niệm cần được **định nghĩa và phối hợp** rõ:

1. **End-to-end deadline / ngân sách toàn yêu cầu:** một giới hạn thời gian **không được reset** khi qua DNS, connect, TLS handshake, gửi, nhận, parse, cache lookup, retry, backoff hay gọi dịch vụ phụ. Nó bảo vệ trải nghiệm/SLA của caller.
2. **Per-operation timeout / ngân sách thao tác:** giới hạn cho **một hoạt động cụ thể**, ví dụ thiết lập kết nối mới, gửi một HTTP attempt, chờ một lần đọc socket, hoặc gọi một dependency. Nó phát hiện điểm nghẽn ở một công đoạn.
3. **Idle timeout / ngân sách nhàn rỗi:** giới hạn khoảng **không có hoạt động hoặc tiến triển được định nghĩa**. Trong `Socket.setSoTimeout` của Java 17, trường hợp cụ thể là giới hạn thời gian **chờ dữ liệu trong từng lời gọi `InputStream.read()`**. Trong ứng dụng stream, bạn có thể tự đặt idle budget tính từ lần nhận được **tiến triển hữu ích** gần nhất.

Ba giới hạn đó **không thể thay thế nhau**. Một hệ thống đáng tin cậy cần phối hợp chúng, chọn giới hạn có hiệu lực ngắn nhất tại mỗi bước, và vẫn giữ một deadline tổng xuyên suốt các lần retry.

### Sau bài này, bạn sẽ làm được gì?

- Định nghĩa và tính ngân sách thời gian còn lại bằng `System.nanoTime()`/đồng hồ đơn điệu thay vì phụ thuộc `Instant.now()` cho elapsed duration.
- Hiểu `Socket.connect(endpoint, timeout)`, `Socket.setSoTimeout`, `URLConnection.setReadTimeout`, `HttpClient.Builder.connectTimeout` và `HttpRequest.Builder.timeout` trong JDK 17.
- Cắt giảm timeout cho từng thao tác theo **remaining deadline**, tránh tự đặt một timeout mới dài hơn phần ngân sách còn lại.
- Phân biệt request timeout, thời gian đợi HTTP response, read idle, stream dài, connection pool idle và application heartbeat.
- Thiết kế retry có backoff/jitter, cancellation, cleanup và status outcome chưa xác định khi request có tác dụng phụ.
- Chạy **hai ví dụ Java 17 được kiểm thử**: mô phỏng thời gian xác định và TCP loopback chứng minh SO_TIMEOUT chỉ giới hạn blocking read.

## 2. Bảng phân biệt các loại thời gian

| Loại giới hạn | Bắt đầu tính từ đâu? | Điều kiện kết thúc/chạm ngưỡng | Có reset khi có dữ liệu mới? |
|---|---|---|---|
| **Overall deadline** | Đầu **logical request** hoặc deadline caller truyền vào | Tổng thời gian vượt budget, kể cả các attempt/retry | **Không** |
| **Connect timeout** | Lúc thực hiện establishment của connection mới | Kết nối chưa thiết lập đúng hạn | Không; mỗi lần connect mới có một thao tác riêng |
| **Per-request/attempt timeout** | Bắt đầu **một HTTP attempt** theo API | Response không đến trong khoảng được cấu hình theo contract API | Không vì có body chunk (đừng giả định như idle) |
| **Read timeout (`SO_TIMEOUT`)** | Lúc vào **một blocking read()** trên Socket | Lần đọc đó không có dữ liệu đúng hạn | Một `read()` mới lại có window riêng |
| **Application read-idle timeout** | Từ lúc bắt đầu chờ hoặc từ tiến triển hữu ích gần nhất | Không có byte/frame/record **được quy định** trong một khoảng | **Có**, khi có tiến triển đạt tiêu chí |
| **Write/stall timeout** | Khi bắt đầu một thao tác gửi hoặc khi không có tiến triển ghi | Gửi bị chặn/lỗi quá lâu | Theo lớp I/O/streaming được triển khai |
| **Connection-pool idle timeout** | Kết nối nằm nhàn rỗi, không phục vụ request | Đóng/loại kết nối khỏi pool theo chính sách | Đây là **lifecycle pool**, không phải response idle |
| **Retry backoff budget** | Sau một attempt thất bại khi quyết định retry | Phần thời gian chờ + attempt tiếp theo không vượt overall deadline | Không reset overall deadline |
| **Business processing deadline** | Đầu request nghiệp vụ hoặc từ upstream | Không hoàn thành end-to-end công việc đúng hạn | Không reset chỉ vì HTTP call thành công |

Cần phân biệt **deadline (mốc thời gian kết thúc)** với **timeout (độ dài được phép cho một hành động)**:

- Deadline có thể mô tả theo `t_end` trên một đồng hồ đơn điệu.
- Timeout là khoảng `duration` để chuyển vào API.
- Ở thời điểm bắt đầu thao tác, hãy tính `remaining = max(0, deadline - now)` rồi đặt `operationTimeout = min(perOperationLimit, remaining)`.
- Sau bất kỳ công đoạn nào, đo lại `remaining`; không dùng nguyên timeout đã dự tính ở đầu workflow.

### Ví dụ lỗi tính toán

Một request có ngân sách tổng 2 giây. Bạn cấu hình `connectTimeout(2s)`, `readTimeout(2s)`, ba lần retry, mỗi lần backoff 1 giây. Nếu mỗi giai đoạn được cấp **2 giây mới**, cả chuỗi có thể kéo dài vượt xa 2 giây. **Những timeout riêng rẽ không được tự cộng lại thành một deadline tổng.**

## 3. Từ đầu tới cuối: request có nhiều giai đoạn hơn kết nối

Trong một lời gọi HTTP/HTTPS, các giai đoạn có thể gồm:

```text
T0: caller bắt đầu logical request / tạo overall deadline
 |
 +-- Chờ queue, rate limiter, connection-pool slot
 +-- Chuẩn bị body / serializing
 +-- DNS / proxy selection
 +-- TCP connect (nếu không reuse connection)
 +-- TLS handshake (nếu HTTPS)
 +-- Gửi request headers và body
 +-- Chờ server xử lý, nhận response headers / time-to-first-byte
 +-- Đọc response body hoặc stream
 +-- Parse, validate, ghi nhận/cache, xử lý nghiệp vụ
 +-- Có thể retry sau lỗi và backoff
 |
T_done hoặc overall deadline hết hạn
```

Công đoạn nào **được** bao bởi một API timeout là chi tiết của API và implementation. Ví dụ `HttpClient.Builder.connectTimeout` áp dụng khi **cần tạo kết nối mới**; nếu client **reuse** connection đang có, option này **không có tác dụng** đối với request đó. `HttpRequest.Builder.timeout` kiểm soát thời gian nhận response theo JDK 17 contract, không phải một chính sách độc lập để quản lý toàn bộ workflow nhiều attempt hoặc mọi tài nguyên streaming trong ứng dụng.

Hệ quả:

- **Không chỉ cấu hình connect timeout.** Một connection đã mở vẫn có thể chờ response.
- **Không chỉ cấu hình per-read timeout.** Một server gửi dữ liệu nhỏ đều đặn có thể tránh read timeout nhưng tổng thời gian vô hạn.
- **Không chỉ cấu hình overall deadline trên giấy.** Nếu code không kiểm tra ngân sách còn lại và không có cách hủy/đóng I/O đang block, thread vẫn có thể chờ sau deadline.
- **Không chỉ tính network.** Serialization, queue, backoff, parsing, retries và việc ghi dữ liệu cũng tiêu thụ tổng ngân sách.

Một deadline tổng tốt là **hợp đồng giữa caller và callee** về thời gian hoàn thành, không phải số giây riêng của TCP stack.

## 4. Tính thời gian đúng: monotonic clock thay vì wall clock

Một deadline thường được cài qua:

```java
// Đoạn minh họa: tổng budget vừa phải, không quá lớn để tràn toNanos().
long started = System.nanoTime();
long allowed = Duration.ofSeconds(3).toNanos();

long elapsed = System.nanoTime() - started;
long remaining = Math.max(0L, allowed - elapsed);

if (remaining <= 0) {
    // Từ chối bắt đầu công đoạn mới, hủy/cleanup công việc đang chạy.
}
```

**Vì sao dùng `System.nanoTime()`?**

- Nó được dùng để đo **elapsed time**; không biểu diễn thời gian lịch mà người dùng nhìn thấy.
- Đồng hồ tường như `Instant.now()`/`System.currentTimeMillis()` có thể bị điều chỉnh theo đồng bộ giờ hoặc thay đổi quản trị. Nếu dùng wall clock để đo timeout, clock jump có thể khiến thời hạn chạy sai.
- Hiệu số `nanoTime() - started` là cơ sở phù hợp cho interval; Java documentation lưu ý khi cộng thẳng deadline timestamp cần cẩn thận **overflow**, đặc biệt khi khoảng đo quá dài.

**Không so sánh `System.nanoTime()` với Unix timestamp hoặc `Instant`**. Hai loại thời gian phục vụ hai mục đích: `Instant` để ghi audit/schedule theo UTC, `nanoTime` để đo duration trong tiến trình.

### Chú ý overflow và đơn vị

`Duration.toNanos()` có thể ném `ArithmeticException` nếu duration quá lớn; Java `long` có giới hạn. Với cấu hình timeout thực tế tính bằng milliseconds/seconds, rủi ro nhỏ nhưng thư viện production vẫn nên kiểm tra đầu vào. Đừng viết:

```java
int millis = (int) remainingNanos / 1_000_000;
```

vì cast sang `int` **trước phép chia** có thể tràn; phép chia phải diễn ra trước, sau đó mới clamp về khả năng của API:

```java
long remainingMillis =
        TimeUnit.NANOSECONDS.toMillis(remainingNanos);
```

Với `Socket.setSoTimeout(int)`, số mili giây **0 nghĩa là vô hạn**. Nếu còn dưới 1 ms, phép chia làm tròn xuống ra 0; **không được vô ý truyền 0**, vì điều đó có thể **tắt timeout**. Có thể fail fast khi không đủ một đơn vị chính xác, hoặc dùng giá trị dương tối thiểu kèm cơ chế deadline tổng độc lập, tùy yêu cầu chính xác.

### Deadline tương đối khác absolute timestamp truyền qua dịch vụ

Không nên đưa thẳng giá trị `System.nanoTime()` từ máy A sang máy B: nguồn gốc nanos không đồng bộ giữa hai tiến trình/máy. Khi chuyển deadline qua RPC, ứng dụng thường truyền **remaining budget** được giảm đi theo thời gian hoặc một absolute wall-clock timestamp có xét clock skew, latency và chính sách đồng bộ; receiver xây **deadline đơn điệu cục bộ**. Đừng cộng thời gian "khởi tạo lại" khiến downstream có ngân sách lớn hơn caller thực sự.

## 5. Phân bổ ngân sách theo từng thao tác

Một mô hình phổ biến:

```text
Tổng remaining = 950 ms
Per-connect limit   = 300 ms
Per-read-operation  = 400 ms
Read-idle remaining = 250 ms

Thao tác connect mới: timeout = min(950, 300) = 300 ms
Thao tác read:       timeout = min(950, 400, 250) = 250 ms
```

Sau khi connect thật sự mất 180 ms, **tổng remaining giảm còn 770 ms** (nếu không có chi phí khác). Lúc bắt đầu đọc, bạn phải tính lại. Nếu một giai đoạn trước đã dùng hết ngân sách, không mở request mới chỉ để "thử thêm một lần".

### Ngân sách không phải định mức phải tiêu hết

`connectTimeout(300ms)` là **giới hạn**, không phải lệnh chờ đủ 300 ms. Kết nối thành công sau 30 ms thì khoảng thời gian còn lại vẫn thuộc overall deadline. Ngược lại, kết nối có thể thất bại ngay sau 5 ms vì `ConnectException`; timeout không đảm bảo mọi lỗi chờ đủ ngưỡng.

### Mỗi công đoạn có ngân sách kỹ thuật riêng

| Công đoạn | Ví dụ limit | Cách hiểu |
|---|---:|---|
| Chờ pool slot | 100 ms | Giới hạn thời gian queue / chờ resource |
| TCP connect | 300 ms | Giới hạn thiết lập kết nối mới |
| Read từ socket | 250 ms | Giới hạn **một** blocking read khi không có dữ liệu |
| Một HTTP attempt | 700 ms | Giới hạn request theo API/client |
| Parse JSON | 150 ms | Giới hạn CPU/worker theo ứng dụng, thường cần cancellation cooperatively |
| Overall request | 1.200 ms | Không vượt qua tổng mọi công đoạn và retry |

Những giá trị chỉ là **ví dụ minh họa**: số thực tế phải dựa trên latency distribution, service-level objectives, expected payload size, đường mạng, số downstream calls và chi phí fail/retry.

### Budget song song khác budget tuần tự

Với hai downstream calls chạy **song song**, thời gian tổng thường gần **max** của hai nhánh cộng overhead, không phải tổng đơn giản. Tuy nhiên, cả hai nhánh phải biết cùng deadline tổng và đều bị cancel/cleanup khi caller không còn cần kết quả. Với chuỗi **tuần tự**, mỗi công đoạn tiêu thụ một phần ngân sách trước khi giai đoạn kế bắt đầu.

## 6. Idle timeout: định nghĩa "có tiến triển" mới quan trọng

Idle timeout có ít nhất **ba nghĩa khác nhau** trong networking:

1. **Socket read idle:** `Socket.setSoTimeout(ms)` giới hạn thời gian **một lời gọi `InputStream.read()` chờ dữ liệu**. Nếu lần đọc thành công rồi code gọi lại `read()`, lời gọi mới có một window chờ mới. Khi hết hạn, ném `SocketTimeoutException` nhưng socket **vẫn hợp lệ** theo contract.
2. **Application stream idle:** bộ nhận theo dõi thời điểm gần nhất có **tiến triển hữu ích** như nhận byte, frame hoặc complete business record. Khi quá lâu không có tiến triển, hủy request/stream. Tiêu chí "tiến triển" là do giao thức và ứng dụng định nghĩa.
3. **Keep-alive/pool idle:** kết nối còn mở nhưng **không phục vụ request** và được pool đóng sau khoảng rảnh rỗi. Đây là chính sách tái sử dụng kết nối, **không phải** timeout đọc response của request đang hoạt động.

### Một server "slow drip" đánh lừa idle timeout

Giả sử idle limit 250 ms; server gửi 1 byte mỗi 180 ms:

```text
t=0 ms     bắt đầu đọc
t=180 ms   có 1 byte -> reset idle
t=360 ms   có 1 byte -> reset idle
t=540 ms   có 1 byte -> reset idle
...
```

**Không có khoảng im lặng nào vượt 250 ms**, nhưng một request với **overall deadline 500 ms** đã quá hạn tại t=540 ms. Đây là lý do cần **cả idle window và deadline tổng**. Khi thiết kế stream có thể kéo dài hàng giờ theo chủ đích, hãy quyết định rõ **overall request deadline** áp cho từng logical operation, từng session, hoặc chỉ các đoạn bất biến, thay vì vô thức áp 500 ms cho mọi session dài.

### Tiến triển ở tầng byte chưa chắc là tiến triển nghiệp vụ

Nếu server gửi whitespace đều đặn mà không bao giờ hoàn thành một JSON object, đó có thể là **byte progress** nhưng không phải **message progress**. Với event stream, heartbeat hợp lệ có thể giữ session hoạt động nhưng không hoàn thành job. Hãy định nghĩa:

- `lastByteAt`: lần cuối đọc được byte hợp lệ.
- `lastFrameAt`: lần cuối nhận một protocol frame hợp lệ.
- `lastBusinessProgressAt`: lần cuối hoàn thành record/chunk có ý nghĩa.
- Deadline toàn phiên/operation vẫn **không reset** theo các marker đó.

Không dùng mỗi socket read timeout để chống slowloris/slow-drip; cần min throughput, max size, protocol deadlines hoặc application progress policy phù hợp.

## 7. Java 17: ý nghĩa các API timeout bạn thường gặp

| Java API | Phạm vi cụ thể | Khi chạm ngưỡng |
|---|---|---|
| `Socket.connect(SocketAddress, int timeout)` | Một lần mở TCP connection, thời gian ms dương | `SocketTimeoutException` trong trường hợp hết hạn; lỗi khác có thể xảy ra sớm hơn |
| `Socket.setSoTimeout(int ms)` | Một blocking `InputStream.read()` chờ dữ liệu | `SocketTimeoutException`; socket không tự bị đóng vì read timeout |
| `ServerSocket.setSoTimeout(int ms)` | Một blocking `accept()` chờ client | `SocketTimeoutException`; listening socket vẫn hợp lệ |
| `URLConnection.setConnectTimeout(int ms)` | Thiết lập liên kết theo protocol handler | Có thể ném `SocketTimeoutException` |
| `URLConnection.setReadTimeout(int ms)` | Một read từ InputStream chờ dữ liệu | Có thể ném `SocketTimeoutException` |
| `HttpClient.Builder.connectTimeout(Duration)` | Thiết lập **connection mới**; không có hiệu lực nếu reuse connection | `HttpConnectTimeoutException` khi connect bị quá hạn |
| `HttpRequest.Builder.timeout(Duration)` | **Một request**: chờ response theo Java 17 API | `HttpTimeoutException` nếu không nhận response đúng hạn |
| `CompletableFuture.orTimeout(long, TimeUnit)` | Future chưa hoàn thành sau interval | Future hoàn thành ngoại lệ `TimeoutException`; chưa đồng nghĩa tác vụ ngoài bị stop |
| `Future.get(long, TimeUnit)` | Thời gian caller **đợi** future | `TimeoutException`; future/task vẫn có thể chạy |
| `Thread.sleep(...)` | Một khoảng chờ tự nguyện | **Không** tự chặn tổng retry duration hay cancel network |

**Đặc biệt:** trên `Socket`/`URLConnection`, timeout bằng **0** có ý nghĩa **không giới hạn** (infinite). Trên builders `HttpClient.connectTimeout(Duration)` và `HttpRequest.timeout(Duration)`, `Duration` phải **dương**; không dùng `Duration.ZERO` để nói "đừng chờ" — sẽ ném `IllegalArgumentException`. Nếu remaining đã bằng 0, **fail fast**.

### Về HTTP request timeout và body stream

Theo Java 17 `HttpRequest.Builder.timeout`, khi **response không nhận được** trong thời hạn, `HttpClient.send` ném `HttpTimeoutException` hoặc future `sendAsync` hoàn thành ngoại lệ. **Đừng suy ra** từ đó rằng mọi thao tác ứng dụng với một body streaming như `BodyHandlers.ofInputStream()`, việc parse hàng gigabyte dữ liệu, retry và downstream work đều được giới hạn tới khi bạn kết thúc workflow. Với stream handed-off, application cần riêng timeout đọc và deadline tổng, đóng stream khi không còn cần dữ liệu.

### Connect timeout có tác dụng với TLS handshake không?

Phạm vi connect timeout cụ thể của HTTP client/provider/runtime cần đọc tài liệu JDK và kiểm thử. Java 17 Javadoc nhấn mạnh **khi cần thiết lập connection mới** và không áp dụng khi reuse; không lấy một con số connectTimeout làm bảo đảm cứng về **mọi** giai đoạn DNS, TLS handshake, body, parsing. Với yêu cầu deadline nghiêm ngặt, đặt thêm request budget và external cancellation.

## 8. Hình dung deadline với timeline thực tế

Giả sử tổng budget 1.200 ms:

```text
0             100             280             480             680      940   1200
|--- setup ---|--- connect ----|-- chunk #1 ---|-- chunk #2 ---|--silence--|-----|
                                                ^               ^
                                            progress        progress
                                                                |
  at 940 ms: 260 ms không có byte mới -> idle limit 250 ms đã hết
  at 940 ms: tổng chỉ dùng 940/1200 ms -> overall vẫn còn 260 ms
  at 1200 ms: overall deadline đã hết, không được reset nhờ retry
```

Chẳng hạn:

- Sau setup 100 ms: remaining 1.100 ms.
- Per-connect cap là 300 ms, không phải 1.100 ms.
- Connect thực tế mất 180 ms: remaining 920 ms.
- Per-read cap 350 ms và idle window 250 ms: lần đọc đầu giới hạn 250 ms.
- Chunk #1 tới sau 200 ms: remaining 720 ms, idle reset.
- Chunk #2 tới sau 200 ms: remaining 520 ms, idle reset.
- Im lặng 260 ms nữa: idle expired, **overall còn 260 ms**.

**Đây là hai cách thất bại riêng**. Một lần thao tác có thể timeout do idle trước khi tổng hết hạn. Ngược lại, stream có thể luôn có tiến triển nhưng deadline tổng hết trước. Số liệu này được tạo bằng demo đồng hồ giả bên dưới để test chính xác mà không phụ thuộc scheduling.

## 9. Ví dụ Java 17 #1: mô phỏng deadline và idle window với đồng hồ chủ động

Để học các phép tính một cách **xác định, không phụ thuộc jitter của OS**, chương trình `TimeBudgetSimulation.java` dùng một đồng hồ giả `FakeTicker`. Nó mô phỏng các khoảng thời gian trôi qua, chứ **không tạo traffic thật**. Do đó stdout chính xác, kiểm tra được cả hai tình huống "idle hết trước" và "overall hết trước".

`Deadline` giữ **start + total** ổn định, method `capMillis` lấy min của per-operation limit và remaining. `IdleWindow` giữ timestamp của tiến triển gần nhất, chỉ `progress()` mới làm reset idle. Các assertion báo lỗi nếu trạng thái không đúng.

**Chương trình đầy đủ:**

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class TimeBudgetSimulation {
    static final class FakeTicker {
        private long nowNanos;

        long now() {
            return nowNanos;
        }

        void advanceMillis(long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative advance");
            }
            nowNanos += TimeUnit.MILLISECONDS.toNanos(amount);
        }
    }

    static final class Deadline {
        private final FakeTicker ticker;
        private final long start;
        private final long totalNanos;

        Deadline(FakeTicker ticker, Duration total) {
            if (total.isZero() || total.isNegative()) {
                throw new IllegalArgumentException("total must be positive");
            }
            this.ticker = ticker;
            this.start = ticker.now();
            this.totalNanos = total.toNanos();
        }

        long remainingNanos() {
            long elapsed = ticker.now() - start;
            return Math.max(0L, totalNanos - elapsed);
        }

        boolean expired() {
            return remainingNanos() == 0;
        }

        long capMillis(Duration operation) {
            if (operation.isZero() || operation.isNegative()) {
                throw new IllegalArgumentException("operation must be positive");
            }
            long left = remainingNanos();
            if (left == 0) {
                throw new IllegalStateException("overall deadline expired");
            }
            return TimeUnit.NANOSECONDS.toMillis(
                    Math.min(left, operation.toNanos()));
        }
    }

    static final class IdleWindow {
        private final FakeTicker ticker;
        private final long limitNanos;
        private long lastProgress;

        IdleWindow(FakeTicker ticker, Duration idleLimit) {
            if (idleLimit.isNegative() || idleLimit.isZero()) {
                throw new IllegalArgumentException("idle limit must be positive");
            }
            this.ticker = ticker;
            this.limitNanos = idleLimit.toNanos();
            this.lastProgress = ticker.now();
        }

        void progress() {
            lastProgress = ticker.now();
        }

        boolean expired() {
            return ticker.now() - lastProgress >= limitNanos;
        }

        long remainingMillis() {
            return TimeUnit.NANOSECONDS.toMillis(
                    Math.max(0L, limitNanos - (ticker.now() - lastProgress)));
        }
    }

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected time budget state");
        }
    }

    public static void main(String[] args) {
        FakeTicker t = new FakeTicker();
        Deadline total = new Deadline(t, Duration.ofMillis(1200));

        System.out.println("Initial total: "
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos()) + " ms");

        t.advanceMillis(100); // setup / DNS model
        System.out.println("After setup: "
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos()) + " ms");
        System.out.println("Connect operation cap: "
                + total.capMillis(Duration.ofMillis(300)) + " ms");

        t.advanceMillis(180); // successful connect
        System.out.println("After connect: "
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos()) + " ms");

        IdleWindow idle = new IdleWindow(t, Duration.ofMillis(250));
        System.out.println("First read cap: "
                + Math.min(total.capMillis(Duration.ofMillis(350)),
                           idle.remainingMillis()) + " ms");

        t.advanceMillis(200);
        idle.progress(); // first chunk arrived
        check(!idle.expired());
        System.out.println("Chunk 1: totalLeft="
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos())
                + " ms, idleExpired=" + idle.expired());

        t.advanceMillis(200);
        idle.progress(); // second chunk arrived
        check(!idle.expired());
        System.out.println("Chunk 2: totalLeft="
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos())
                + " ms, idleExpired=" + idle.expired());

        t.advanceMillis(260); // no new data
        check(idle.expired() && !total.expired());
        System.out.println("Silence: idleExpired=" + idle.expired()
                + ", overallExpired=" + total.expired()
                + ", totalLeft="
                + TimeUnit.NANOSECONDS.toMillis(total.remainingNanos()) + " ms");

        t.advanceMillis(260);
        check(total.expired());
        System.out.println("Deadline expired: " + total.expired());

        FakeTicker dripTicker = new FakeTicker();
        Deadline dripDeadline =
                new Deadline(dripTicker, Duration.ofMillis(500));
        IdleWindow dripIdle =
                new IdleWindow(dripTicker, Duration.ofMillis(250));
        for (int i = 0; i < 3; i++) {
            dripTicker.advanceMillis(180);
            dripIdle.progress(); // progress prevents idle timeout
        }
        check(!dripIdle.expired() && dripDeadline.expired());
        System.out.println("Slow drip: idleExpired=" + dripIdle.expired()
                + ", overallExpired=" + dripDeadline.expired());

        FakeTicker retryTicker = new FakeTicker();
        Deadline retryBudget =
                new Deadline(retryTicker, Duration.ofMillis(1000));
        System.out.println("Attempt 1 cap: "
                + retryBudget.capMillis(Duration.ofMillis(450)) + " ms");
        retryTicker.advanceMillis(400);
        System.out.println("Attempt 2 cap: "
                + retryBudget.capMillis(Duration.ofMillis(450)) + " ms");
        retryTicker.advanceMillis(400);
        System.out.println("Attempt 3 cap: "
                + retryBudget.capMillis(Duration.ofMillis(450)) + " ms");
    }
}
```

Biên dịch/chạy (Java 17+):

```bash
javac --release 17 -encoding UTF-8 TimeBudgetSimulation.java
java TimeBudgetSimulation
```

**Stdout chính xác:**

```text
Initial total: 1200 ms
After setup: 1100 ms
Connect operation cap: 300 ms
After connect: 920 ms
First read cap: 250 ms
Chunk 1: totalLeft=720 ms, idleExpired=false
Chunk 2: totalLeft=520 ms, idleExpired=false
Silence: idleExpired=true, overallExpired=false, totalLeft=260 ms
Deadline expired: true
Slow drip: idleExpired=false, overallExpired=true
Attempt 1 cap: 450 ms
Attempt 2 cap: 450 ms
Attempt 3 cap: 200 ms
```

### Phân tích từng kết quả

- `1200 → 1100 → 920`: tổng budget không được reset vì setup hay connect thành công.
- `Connect operation cap: 300ms`: một connect không chiếm toàn bộ 1100ms còn lại nếu policy chỉ cho 300ms.
- `First read cap: 250ms`: min của remaining overall, limit một read 350ms và idle window 250ms.
- Hai chunk cách 200ms reset idle nhưng vẫn tiêu thụ **400ms** của tổng budget.
- Sau 260ms không có tiến triển, idle hết nhưng overall còn 260ms: **timeout nhàn rỗi xảy ra trước overall timeout**.
- Slow drip cứ cách 180ms có tiến triển nên idle không hết, trong khi **tổng 500ms đã vượt**.
- Các retry attempt có cap 450, 450, **200ms**: attempt cuối bị cắt theo remaining, không nhận nguyên 450ms mới.

**Giới hạn cần nói rõ:** `FakeTicker` là mô phỏng; nó **không tự hủy một socket đang block**. `Deadline.capMillis` trả số mili giây chỉ để minh họa budget. Trong production, phải xử lý phần ngân sách dưới 1ms/overflow, chọn timeout API dương phù hợp, có cơ chế cancel/close I/O và kiểm thử với đồng hồ thật. Không lấy output test làm đo độ chính xác của hệ điều hành.

## 10. Ví dụ Java 17 #2: `Socket.setSoTimeout` chỉ giới hạn một blocking read

Ví dụ thứ hai dùng **TCP loopback thật**, không Internet và không cần thư viện ngoài. Chương trình dựng một `ServerSocket`, cho server gửi chữ `A` một lần rồi **cố ý im lặng**. Client:

1. Gọi `Socket.connect(..., 2000)` với **connect timeout 2000ms**.
2. Gọi `setSoTimeout(3000)` để chờ byte đầu trong tối đa 3000ms.
3. Nhận `A` thành công.
4. Chuyển sang `setSoTimeout(300)` rồi gọi `read()` lần nữa.
5. Server không gửi thêm byte và cũng không đóng connection cho tới khi client báo đã xong → `SocketTimeoutException` trên lần đọc thứ hai.
6. Bắt exception và chứng minh **timeout đọc không tự đóng đối tượng Socket**.

Dùng `CountDownLatch` để server chỉ kết thúc **sau khi client test xong**, không dựa vào `Thread.sleep` hoặc jitter scheduling để tạo kết quả. Một guard 5 giây ngăn test server chờ vô hạn nếu client lỗi.

File **`SocketIdleReadDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class SocketIdleReadDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] { 127, 0, 0, 1 });
        CountDownLatch releaseServer = new CountDownLatch(1);
        AtomicReference<Throwable> serverFailure = new AtomicReference<>();

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            Thread server = new Thread(() -> {
                try (Socket peer = listener.accept()) {
                    peer.getOutputStream().write('A');
                    peer.getOutputStream().flush();
                    if (!releaseServer.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("server release timeout");
                    }
                } catch (Throwable error) {
                    serverFailure.set(error);
                }
            }, "loopback-test-server");
            server.start();
            try {
                try (Socket client = new Socket()) {
                    client.connect(
                            new InetSocketAddress(
                                    loopback, listener.getLocalPort()),
                            2000);
                    client.setSoTimeout(3000); // initial read
                    InputStream in = client.getInputStream();
                    int firstByte = in.read();
                    if (firstByte != 'A') {
                        throw new AssertionError("Unexpected first byte");
                    }

                    client.setSoTimeout(300); // each blocking read
                    boolean timedOut = false;
                    try {
                        in.read(); // server deliberately waits, sends no bytes
                    } catch (SocketTimeoutException expected) {
                        timedOut = true;
                    }
                    if (!timedOut) {
                        throw new AssertionError("Missing read timeout");
                    }

                    System.out.println("First byte: " + (char) firstByte);
                    System.out.println("Read idle timed out: " + timedOut);
                    System.out.println(
                            "Socket closed by timeout: " + client.isClosed());
                }
            } finally {
                releaseServer.countDown();
                server.join(2000);
                if (server.isAlive()) {
                    throw new AssertionError("Server thread did not finish");
                }
            }
        }
        if (serverFailure.get() != null) {
            throw new AssertionError("Server failed", serverFailure.get());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 SocketIdleReadDemo.java
java SocketIdleReadDemo
```

**Stdout chính xác khi môi trường cho phép TCP loopback:**

```text
First byte: A
Read idle timed out: true
Socket closed by timeout: false
```

### Diễn giải chính xác

- Connect thành công **không chứng minh** toàn bộ response sẽ đến đúng hạn.
- Client nhận byte đầu nên lần đọc thứ nhất thành công.
- Lần đọc thứ hai chờ dữ liệu; vì server giữ TCP mở nhưng im lặng, một khoảng 300ms không có dữ liệu dẫn tới `SocketTimeoutException`.
- `Socket closed by timeout: false` được in **trước try-with-resources đóng client**: exception do read timeout **không tự đóng socket**. Điều này **không** chứng minh phía peer còn hoạt động khỏe mạnh hay có thể nhận dữ liệu vô hạn.
- Khi thoát `try`, socket client được **đóng chủ động**; latch giải phóng server và các tài nguyên test được thu dọn.

**Không suy luận đây là overall deadline 300ms.** Nếu server cứ gửi dữ liệu đủ nhanh, mỗi lần `read()` có thể không timeout, nhưng loop đọc hàng triệu lần vẫn vượt quá deadline nghiệp vụ. Muốn giới hạn tổng, phải đo thêm elapsed time, giới hạn bytes/chunks và có cách hủy/đóng socket khi hết ngân sách.

## 11. Từ bài mô phỏng sang code thực: cap timeout cho HttpClient

Một ứng dụng Java 17 dùng `java.net.http.HttpClient` có thể đặt **connect timeout ở client** và **request timeout trên từng HttpRequest**:

```java
// Mã minh họa: đặt trong method có URI, deadline helper.
// deadline.remaining() trả Duration dương hoặc Duration.ZERO.
// Không phải chương trình đầy đủ, vì helper do ứng dụng định nghĩa.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

Duration remaining = deadline.remaining();
if (remaining.isZero() || remaining.isNegative()) {
    throw new TimeoutException("overall deadline exhausted");
}

Duration perAttempt = Duration.ofMillis(700);
Duration allowedAttempt = remaining.compareTo(perAttempt) < 0
        ? remaining : perAttempt;

HttpRequest req = HttpRequest.newBuilder(uri)
        .timeout(allowedAttempt)
        .GET()
        .build();

HttpResponse<String> response = client.send(
        req,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
```

**Các điểm chính:**

1. `connectTimeout(300ms)` áp cho **connection mới** của client; không có hiệu lực nếu một kết nối từ pool được reuse.
2. `req.timeout(allowedAttempt)` là **timeout của attempt cụ thể**. `allowedAttempt` được chọn **không lớn hơn** tổng remaining tại lúc bắt đầu.
3. Sau khi `send` trả, bạn vẫn cần kiểm tra **deadline còn bao nhiêu** trước khi parse JSON, gọi dependency khác hoặc retry; một request timeout không quản lý thay toàn workflow.
4. Nếu cần retry, tính `deadline.remaining()` **lại** cho attempt mới. **Không** bắt đầu attempt với `remaining == 0`.
5. Nếu ứng dụng cần deadline "hard" cho các thao tác sau response, phải dùng cancellation/cooperative checks và resource cleanup, không mặc định `HttpResponse<String>` bao tất cả mọi business processing.

### HttpTimeoutException và HttpConnectTimeoutException

`HttpConnectTimeoutException` kế thừa `HttpTimeoutException`. Nếu muốn phân biệt khi bắt:

```java
// Đoạn minh họa; client và request được cấu hình như bên trên.
try {
    HttpResponse<String> r = client.send(
            request, HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
    // Đánh giá status/header/body.
} catch (HttpConnectTimeoutException ex) {
    // Kết nối mới chưa được thiết lập đúng hạn.
} catch (HttpTimeoutException ex) {
    // Request không nhận response kịp hạn theo API.
} catch (IOException ex) {
    // Các lỗi transport/TLS/I/O khác.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Hủy workflow và giải phóng tài nguyên.
}
```

Nếu bắt `HttpTimeoutException` trước `HttpConnectTimeoutException` thì nhánh subclass phía sau không còn tới được, Java compiler báo lỗi unreachable catch. **Timeout là một loại lỗi I/O, không phải HTTP status code.** Một server trả `504 Gateway Timeout` là **HTTP response từ gateway**, khác với việc client tự ném `HttpTimeoutException` vì không nhận response trong thời hạn.

### Với API URLConnection cổ điển

`HttpURLConnection`/`HttpsURLConnection` có:

```java
// Mã minh họa: URL và connection phải được đóng theo lifecycle.
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();
conn.setConnectTimeout(300);
conn.setReadTimeout(250);
conn.setInstanceFollowRedirects(false);
```

`setConnectTimeout` giới hạn connection phase theo handler; `setReadTimeout` giới hạn chờ dữ liệu của read. **Không hứa** `connectTimeout+readTimeout` cộng lại là deadline tổng. `0` nghĩa vô hạn; khai báo timeout **trước khi kết nối implicit** qua `getResponseCode`/`getInputStream`.

## 12. Cách áp deadline tổng vào một vòng đọc streaming

Một stream rất dài cần ít nhất ba lớp bảo vệ:

- **Overall deadline** (nếu business operation được yêu cầu kết thúc): deadline monotonic của logical request.
- **Per-read/idle timeout**: nếu không có dữ liệu hoặc tiến triển hợp lệ quá một khoảng, dừng.
- **Size / progress quota**: hạn chế số byte, số message, tốc độ quá thấp, và nội dung không hợp protocol.

Một vòng xử lý socket có thể theo **thuật toán** sau:

```text
overallDeadline = monotonicStart + 1200ms
idleLimit = 250ms
perReadLimit = 350ms
lastProgress = monotonicStart

while chưa hoàn thành response:
    remainingTotal = deadline - now
    remainingIdle  = idleLimit - (now - lastProgress)
    readWait = min(remainingTotal, remainingIdle, perReadLimit)

    nếu readWait <= 0: abort/close và báo đúng loại timeout
    setSoTimeout(millis_dương_phù_hợp(readWait))
    n = input.read(buffer)

    nếu n == -1: xử lý EOF theo protocol
    nếu n > 0:
        lastProgress = monotonicNow
        bytes += n
        nếu vượt quota: abort/close và báo lỗi
        parse bounded chunks / apply backpressure
```

**Đây là pseudocode**, không phải class runnable. Trong code thực, cần thêm điều kiện kết thúc theo protocol (Content-Length/chunked/framing), tránh overflow, không dùng `0` khi chuyển ns→ms và có watchdog/hard cancellation nếu một blocking operation không tôn trọng deadline.

### Tại sao cần kiểm tra cả sau lần đọc?

Hãy tính lại `now` và deadline **sau khi đọc xong**. Nếu read hoàn thành ngay khi tổng đã hết, ứng dụng không được tiếp tục parse/commit một nghiệp vụ có deadline chặt chẽ. Với nhu cầu chỉ là "return before deadline", timeout gần thời điểm cuối là race có chủ đích: phải định nghĩa rõ response quá hạn được loại bỏ/ghi nhận thế nào.

### Timeout của từng read khác timeout của toàn nội dung

Ví dụ file dài 10.000 chunks, mỗi chunk có byte sau 100ms. Per-read timeout 250ms **không** giới hạn toàn file; mất gần 1.000 giây vẫn không có một read riêng nào hết hạn. Overall budget hoặc mức tiến triển tối thiểu là cơ chế bổ sung.

## 13. Retry và backoff phải dùng chung một deadline

### Anti-pattern: mỗi attempt khởi tạo deadline mới

```text
Sai:
attempt1: tạo timeout 1s
  fail sau 900ms
backoff 500ms
attempt2: tạo timeout mới 1s
  fail sau 900ms
backoff 500ms
attempt3: tạo timeout mới 1s

Tổng ~= 4.8s dù caller chỉ cho 1s.
```

Thiết kế đúng:

```text
t0: overall budget 1000ms
attempt1 cap 450ms, thực dùng 400ms
  remaining = 600ms
attempt2 cap 450ms, thực dùng 400ms
  remaining = 200ms
attempt3 cap min(450, 200) = 200ms
không có attempt4 sau khi remaining <= 0
```

Nếu có backoff 100ms giữa các attempt, nó cũng **ăn vào overall deadline**. Không cộng thêm "ngoại lệ" 100ms cho mỗi retry nếu caller đã đặt deadline chặt chẽ.

### Quy tắc quyết định retry

1. **Chỉ retry khi có đủ remaining** cho một attempt có ý nghĩa; có thể trừ reserve cho cleanup/response serialization.
2. **Không retry vô hạn.** Có retry budget, backoff với jitter và tôn trọng `Retry-After`/rate limit khi phù hợp.
3. **Không retry POST side effect mù quáng** sau I/O timeout: server có thể đã xử lý thanh toán/đơn hàng nhưng response bị mất. Cần idempotency key do server hỗ trợ hoặc tra cứu/đối soát.
4. **HTTP 429/503** có thể gợi ý retry theo contract; `504` từ gateway không tự chứng minh origin chưa commit.
5. Với **body publisher không replay được**, redirect/auth/retry cần chính sách riêng; stream đã tiêu thụ có thể không gửi lại được.
6. **Hủy attempt cũ** và cleanup trước khi tái sử dụng tài nguyên, tránh nhiều attempt còn chạy song song ngoài chủ ý.

### Hedged requests cũng tiêu budget

Hedging gửi một request phụ khi primary chậm có thể giảm tail latency cho thao tác đọc an toàn, nhưng tăng tải, chi phí và race. Cả hai nhánh phải thuộc cùng deadline; khi có kết quả, phải cancel/close nhánh thừa, không tạo side effect trùng khi operation không idempotent.

## 14. Cancellation và deadline: giới hạn logic chưa chắc dừng hệ thống

Một deadline chỉ được lưu trong biến `long` **không tự hủy thread/socket đang block**. Muốn bảo đảm trả về và thu hồi tài nguyên:

- Sử dụng timeout tích hợp của API khi có.
- Với `Socket`, **đóng socket** khi cần buộc một blocking read/write kết thúc; chỉ gọi `Thread.interrupt()` không được coi là bảo đảm chung cho mọi blocking I/O trên Java 17.
- Với `HttpClient.sendAsync`, có thể quản lý `CompletableFuture` và cancellation, nhưng phải hiểu đây là nỗ lực hủy (best effort) và response/server-side side effect có thể đã xảy ra.
- Với `Future.get(timeout)`, khi chờ quá hạn chỉ caller ném `TimeoutException`; worker có thể vẫn chạy nếu bạn không cancel task/cooperatively terminate.
- Với streaming `BodyHandlers.ofInputStream()`, đóng InputStream khi hủy và không giữ connection/body subscriber vô hạn.
- Với task parse/CPU-bound, dùng cancellation flag/interruption/cooperative checks; deadline tổng không tự dừng vòng lặp dài.
- Khi business callback/transaction đã commit, hủy network response không tự rollback trạng thái. Phải dùng idempotency, saga/compensation hoặc đối soát riêng.

### Cẩn thận `CompletableFuture.orTimeout`

`future.orTimeout(500, TimeUnit.MILLISECONDS)` khiến future hoàn thành ngoại lệ nếu chưa hoàn thành đúng hạn. Nó **không** tự chứng minh worker thread/server đã dừng; cũng không biến deadline logic qua ba lần retry thành một giới hạn tổng nếu bạn tạo future mới với thời hạn mới mỗi attempt.

### Phân biệt timeout exception với cancellation

`CancellationException` biểu thị một future/task được cancel; `TimeoutException` là quá thời hạn chờ/hoàn tất theo API; `SocketTimeoutException` là một dạng I/O timeout; `HttpTimeoutException` liên quan HTTP client deadline. Đừng gộp thành một string "network error" rồi quyết định retry giống nhau.

## 15. Giám sát, đặt SLO và chọn timeout thực tế

Tối ưu độ tin cậy cần số liệu thực, không chỉ đặt mọi timeout 30 giây:

| Quan sát | Vì sao cần |
|---|---|
| End-to-end latency (p50/p95/p99) | Biết request thật mất bao lâu và tail latency |
| DNS + connect + TLS timing | Tách chi phí thiết lập connection khỏi xử lý server |
| Time-to-first-byte / response headers | Phân biệt server chậm phản hồi với body truyền chậm |
| Response streaming throughput | Phát hiện slow-drip và tắc nghẽn downstream |
| Per-attempt timeout counts | Xem thao tác nào thường hết budget |
| Overall deadline exhausted | Đếm request vượt hợp đồng SLO |
| Read-idle timeout counts | Phát hiện ngắt quãng hoặc peer im lặng |
| Retries, backoff, remaining budget | Biết retry có thực sự giúp hay chỉ tăng tải |
| Cancellation completion and leaks | Xem socket/stream/task có được giải phóng đúng hạn không |
| Late-response discarded | Thấy request phía server hoàn thành sau caller deadline |

**Không xem "timeout" là một nguyên nhân đơn nhất.** Ví dụ `HTTP 504` có thể do gateway, `SocketTimeoutException` có thể do read thiếu byte, `HttpConnectTimeoutException` liên quan establishment; một endpoint đã nhận request nhưng client timeout còn tạo **outcome unknown**. Metrics nên có tag `phase`/`attempt`/`elapsed`/`remaining`, nhưng tránh cardinality vô hạn (URL chứa user IDs, query ngẫu nhiên) và không log secrets.

### Cách chọn budget

- Xuất phát từ **SLO/UX deadline** toàn request, không lấy connect timeout làm chuẩn.
- Dùng latency thực tế của từng dependency để cấp per-operation cap.
- Đặt lower bound hợp lý tránh timeout quá sát khiến traffic bình thường bị thất bại; upper bound tránh giữ tài nguyên vô hạn.
- Đặt **budget riêng cho long-lived streams** như WebSocket/SSE, vì một session có thể được phép tồn tại lâu; vẫn cần heartbeat/idle và operation deadlines bên trong.
- Cân nhắc burst, cold start, DNS, proxy, TLS, retry storm, scheduled maintenance và backpressure.
- Dành quỹ thời gian cho **response serialization, cleanup** để upstream còn nhận kết quả khi mình sắp hết hạn.

## 16. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| `connectTimeout=2s` nghĩa cả request ≤ 2s | Server đọc/gửi chậm vẫn treo | Overall deadline riêng |
| `setSoTimeout(500)` nghĩa file tải xong trong 500ms | Slow drip mỗi 400ms tránh read timeout | Overall deadline + size/throughput quota |
| `readTimeout=0` để "không chờ" | 0 là **vô hạn** ở Socket/URLConnection | Fail fast hoặc timeout dương |
| `HttpRequest.timeout(Duration.ZERO)` | `IllegalArgumentException` | Kiểm tra remaining, không khởi tạo attempt khi 0 |
| Mỗi retry tạo timeout tổng mới | Vượt ngân sách caller | Giữ một immutable deadline từ request đầu |
| Không tính backoff vào deadline | Thời gian ngủ retry ăn vượt budget | Tính remaining trước/sau backoff |
| Dùng `Instant.now()` để tính elapsed | Clock có thể đổi | `System.nanoTime()` / monotonic ticker |
| Truyền `nanoTime()` từ máy A sang B | Không cùng hệ quy chiếu | Truyền remaining budget/deadline protocol |
| Tính `(int) remainingNanos / 1_000_000` | Overflow do cast sớm | Chia `long` rồi clamp |
| Đổi nanoseconds sang milliseconds còn <1ms thành 0 | Vô tình vô hiệu socket timeout | Fail fast / timeout dương tối thiểu |
| Đặt cùng per-operation limit cho mọi giai đoạn | Chi phí/tail khác nhau không được phân biệt | Connect/read/parse/upload có cap riêng |
| Bỏ qua queue và serialization | Chậm trước khi gửi chưa tính budget | Đếm toàn workflow từ đầu |
| Nghĩ `HttpClient.connectTimeout` áp cho connection reuse | Không có effect khi reuse | Request/per-operation deadline |
| Nghĩ `get(timeout)` đã hủy worker | Task vẫn chạy và tiêu tài nguyên | Cancel/cooperative stop + cleanup |
| Dùng `Thread.interrupt` làm giải pháp duy nhất cho Socket | Không bảo đảm unblock blocking I/O phổ quát trên Java 17 | Close socket và quản lý lifecycle |
| Nghĩ một byte là tiến triển nghiệp vụ | Stream có thể gửi whitespace/heartbeat mãi | Protocol/business progress timeout |
| Reset deadline tổng khi nhận heartbeat | Request không bao giờ hết hạn | Reset idle nếu hợp lệ, không reset overall |
| Không limit response size | Body có thể vượt heap dù có timeout | Bounded stream/size quota |
| Không xử lý error stream/status | Nhầm HTTP error với timeout I/O | Xem HTTP response riêng |
| Retry POST thanh toán khi mất response | Có thể tạo side effect trùng | Idempotency key/đối soát |
| Chỉ theo dõi số lần timeout | Không biết giai đoạn nghẽn | Metrics theo phase, elapsed, budget left |
| Không xác định tính long-lived của stream | Chọn overall 1s cho WebSocket sống hàng giờ | Session idle, heartbeat, sub-operation deadline |
| Bỏ qua connection pool idle | Kết nối cũ giữ tài nguyên quá lâu | Pool lifecycle riêng với request budget |
| Thấy `SocketTimeoutException` rồi bỏ connection mà không cleanup | Rò rỉ socket/stream | `try-with-resources` hoặc close/cancel đúng |

## 17. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Có connect timeout 2s, read timeout 2s, retry 3 lần. Request chắc chắn kết thúc trong 2s không?

**Đáp án:** Không. Mỗi giới hạn áp cho một giai đoạn/operation khác nhau; nếu không có deadline tổng thì nhiều giai đoạn và retry có thể vượt xa 2s.

**Câu 2.** `Socket.setSoTimeout(200)`, server gửi một byte mỗi 150ms. Tải 5 MiB có thể kéo dài hơn 200ms không?

**Đáp án:** Có. Mỗi blocking read có thể nhận dữ liệu trước hạn riêng. Cần overall deadline và throughput/size quota khi cần.

**Câu 3.** Tổng budget 1.000ms, attempt1 dùng 400ms, attempt2 dùng 400ms. Per-attempt limit 450ms. Cap attempt3 là bao nhiêu?

**Đáp án:** `min(450, 200) = 200ms`, trước khi trừ mọi overhead/backoff tiếp theo.

**Câu 4.** Một attempt hết hạn vì server gửi chậm, có nên reset tổng budget ở attempt kế tiếp không?

**Đáp án:** Không. Retry là phần của **cùng logical request** và tiêu thụ ngân sách còn lại.

**Câu 5.** Vì sao dùng `System.nanoTime()` để đo elapsed thay `System.currentTimeMillis()`?

**Đáp án:** `nanoTime` phù hợp interval/monotonic elapsed, không phải wall clock bị điều chỉnh. Nó không dùng làm Unix timestamp.

**Câu 6.** Tại sao `remainingMillis = (int)remainingNanos / 1_000_000` dễ sai?

**Đáp án:** Cast trước chia có thể tràn `int`. Chia `long` trước, kiểm tra giới hạn API, và tránh 0 gây infinite timeout.

**Câu 7.** `Socket.setSoTimeout(0)` nghĩa là đọc xong ngay không?

**Đáp án:** Không. 0 **tắt** read timeout, tương đương chờ vô hạn, có thể block nếu không có dữ liệu.

**Câu 8.** `HttpClient.Builder.connectTimeout` có hiệu lực với request reuse connection sẵn không?

**Đáp án:** Không. Java 17 mô tả connect timeout chỉ có hiệu lực khi phải thiết lập **connection mới**.

**Câu 9.** `HttpRequest.Builder.timeout` có thay thế deadline chung của cả chuỗi retry + parse không?

**Đáp án:** Không. Nó áp cho một HTTP request theo contract; ứng dụng vẫn cần điều phối ngân sách end-to-end.

**Câu 10.** Nếu `Future.get(300, MILLISECONDS)` ném `TimeoutException`, task chắc chắn đã dừng?

**Đáp án:** Không. Đó là timeout khi chờ của caller; phải quản lý cancellation/cleanup riêng.

**Câu 11.** Nếu `Socket.getInputStream().read()` hết hạn, socket có tự bị đóng không?

**Đáp án:** Không theo API `SO_TIMEOUT`; `SocketTimeoutException` được ném nhưng socket vẫn valid. Demo loopback kiểm chứng đối tượng socket chưa bị đóng.

**Câu 12.** `HTTP 504` và `HttpTimeoutException` có giống nhau?

**Đáp án:** Không. `504` là HTTP response từ gateway; `HttpTimeoutException` là exception của Java HTTP client khi không nhận response kịp hạn.

**Câu 13.** Một SSE stream gửi heartbeat đều đặn nhưng không tạo record nghiệp vụ trong 15 phút. Có cần timeout không?

**Đáp án:** Tùy contract: heartbeat có thể reset **transport idle**, nhưng ứng dụng có thể cần riêng **business progress deadline**. Không reset overall operation deadline nếu chưa có kết quả bắt buộc.

**Câu 14.** Có nên hủy một POST payment ngay khi deadline hết rồi tự động gửi lại POST mới?

**Đáp án:** Không. Server có thể đã commit trước khi response bị mất. Cần idempotency key/đối soát; cancellation client không rollback server.

**Câu 15.** Vì sao long-lived WebSocket cần nhiều loại giới hạn?

**Đáp án:** Session có thể sống lâu theo chủ đích, nhưng vẫn cần idle/heartbeat, hạn chế tài nguyên, timeout cho mỗi command, business progress deadline và cancellation chính xác.

**Câu 16.** Idle timeout chỉ cần xem `Socket.setSoTimeout` là đủ cho mọi protocol?

**Đáp án:** Không. SO_TIMEOUT chỉ giới hạn từng blocking read; application có thể cần frame/record progress timeout, upload write stall timeout hoặc connection pool idle policy riêng.

**Câu 17.** Nếu deadline còn 0.4ms và chuyển sang `setSoTimeout(int)` bằng millis sẽ ra 0, phải làm sao?

**Đáp án:** Không truyền 0 khi muốn giới hạn. Thường fail fast, hoặc dùng timeout dương tối thiểu cùng external monotonic deadline/cancellation, tùy tính chính xác của contract.

**Câu 18.** Nếu hai downstream calls chạy song song, deadline có phải cộng timeout của cả hai?

**Đáp án:** Không nhất thiết. Chúng có thể trùng thời gian, nhưng cùng chia sẻ overall deadline và đều cần cancellation/resource cleanup.

**Câu 19.** Backoff 200ms nằm ngoài hay trong request budget?

**Đáp án:** Trong budget của **logical request**, trừ khi contract caller quy định tường minh một thời hạn khác. Không tự cấp thêm thời gian cho mỗi backoff.

**Câu 20.** Nếu API socket đã cho read timeout, vì sao còn phải đo thời gian sau mỗi chunk?

**Đáp án:** Read timeout chỉ biết khoảng chờ dữ liệu ở từng lần đọc. Tổng elapsed vẫn tăng qua mọi chunk và có thể chạm deadline, nên phải đo/giới hạn toàn chuỗi.

## 18. Checklist triển khai timeout cho Java networking

1. **Chốt overall deadline theo SLO**, tính từ đầu logical request, không reset qua retry/redirect/parse.
2. **Dùng monotonic time** cho elapsed; có abstraction `Ticker/Clock` để unit test các ranh giới dễ dàng.
3. **Tính remaining trước từng bước**; nếu đã hết thì fail fast, không gọi mạng.
4. **Cap operation timeout = min(perPhaseLimit, remaining)**; không cấp timeout dài hơn còn lại.
5. **Phân loại connect/request/read idle/write stall riêng**; không gọi chung là “2s timeout” trong docs.
6. **Nhớ 0 là vô hạn** trong `Socket/URLConnection` và Duration phải dương trong các HttpClient builders.
7. **Giới hạn streaming bytes và tiến triển nghiệp vụ**, chống slow drip/slowloris; heartbeat không đồng nghĩa complete result.
8. **Đặt cancel/close phù hợp** để deadline không chỉ tồn tại trong biến mà còn giải phóng thread/socket/stream.
9. **Đưa retry/backoff/jitter vào cùng budget**, có idempotency/đối soát và số attempt tối đa.
10. **Không coi timeout là server chưa xử lý**, đặc biệt với POST/side effects.
11. **Kiểm thử trong cả đồng hồ giả và loopback network**; test overall trước, idle trước, race sát ngưỡng, không có dữ liệu, partial response, slow stream và cancellation.
12. **Quan sát theo giai đoạn**, đo p95/p99, percent timeout, retry count, remaining budget và task leaks.
13. **Xử lý HTTP status khác I/O exception**: 504 server/gateway response không đồng nghĩa client-side timer ném exception.
14. **Có cleanup khi hủy**, bảo đảm stream/file/connection đóng đúng lifecycle, không giữ task muộn vô hạn.
15. **Điều chỉnh budget theo kiểu request**: upload lớn, stream dài, request đọc nhỏ, thanh toán cần profile khác nhau.

**Ghi nhớ cuối:** **Overall deadline** bảo đảm giới hạn cho **cả logical request**; **per-operation timeout** giới hạn **một giai đoạn hoặc attempt**; **idle timeout** giới hạn khoảng **thiếu tiến triển theo một tiêu chí**. Với Java 17, `connectTimeout` không thay read timeout, `SO_TIMEOUT` không thay overall deadline, và `HttpRequest.timeout` không thay toàn bộ retry/business workflow. Giữ một deadline monotonic, cấp cho mỗi operation không quá remaining, kết hợp kiểm soát stream và cancellation — đó mới là nền tảng thiết kế networking đáng tin cậy.

### Tài liệu tham khảo chính thức

- [Java SE 17 — System.nanoTime (elapsed time)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime())
- [Java SE 17 — Socket.connect và setSoTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java SE 17 — ServerSocket.setSoTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [Java SE 17 — URLConnection.setConnectTimeout và setReadTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html)
- [Java SE 17 — HttpClient.Builder.connectTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 17 — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 17 — HttpTimeoutException / HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [Java SE 17 — CompletableFuture.orTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [RFC 9110 — HTTP semantics, errors and retries](https://www.rfc-editor.org/rfc/rfc9110)