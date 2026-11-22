# Tính lũy đẳng, tác dụng phụ và nguy cơ lặp thao tác ghi trong Spring Reactive

Trong Project Reactor và Spring WebFlux, toán tử `retry` hoặc `retryWhen` có thể tự động thử lại một thao tác gặp lỗi. Điều này hữu ích khi mạng chập chờn hoặc dịch vụ phụ trợ tạm thời không sẵn sàng. Nhưng **thử lại một publisher có tác dụng ghi không đồng nghĩa với thử lại an toàn**: yêu cầu trước đó có thể đã thực sự ghi dữ liệu rồi chỉ thất lạc phản hồi. Lần thử tiếp theo có thể ghi thêm một lần, trừ khi phía thực hiện thao tác có cơ chế **idempotency** (tính lũy đẳng) phù hợp.

Ví dụ: dịch vụ trừ 100.000 đồng rồi client mất kết nối trước khi nhận HTTP 200. Nếu client hoặc `retryWhen` gửi lại lệnh “trừ thêm 100.000 đồng” như một giao dịch mới, tài khoản có thể bị trừ hai lần. Tăng thời gian chờ, thêm backoff, hoặc chỉ giới hạn hai lần retry **không giải quyết gốc rễ việc ghi trùng**. Cần xác định *một thao tác nghiệp vụ* bằng mã duy nhất và cho phép phía ghi nhận ra các lần gửi lại cùng thao tác.

Bài học thuộc nhóm **Lỗi và thử lại** trong Spring Framework - reactive. Trọng tâm là mối quan hệ giữa **tín hiệu lỗi, resubscription, side effect, idempotency key, giao dịch dữ liệu và khả năng quan sát**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Giải thích chính xác `retry(n)` và `retryWhen(...)` làm gì với một nguồn cold publisher.
- Phân biệt **thực thi lại** publisher với **phát lại** giá trị từ cache; phân biệt retry với repeat và fallback.
- Nêu được cửa sổ lỗi “**đã ghi thành công nhưng phản hồi bị mất**”, nguyên nhân phổ biến của duplicate write.
- Phân biệt **thao tác lũy đẳng**, **thao tác không lũy đẳng**, **đọc không có side effect** và **ghi có side effect**.
- Thiết kế **idempotency key ổn định**, quy tắc khớp payload, ràng buộc UNIQUE/transaction và cách trả lại kết quả trước đó.
- Biết khi nào có thể dùng `Retry.backoff`, lọc lỗi tạm thời, giới hạn thử lại, đặt timeout và tránh retry có hại.
- Viết ví dụ Java 17+ với Reactor chứng minh retry làm ghi trùng, và test bằng `StepVerifier`.
- Liên hệ tới WebClient, R2DBC, reactive transaction, outbox và các giới hạn của bảo đảm “exactly once”.

## 2. Retry trong Reactor là đăng ký lại upstream

Một `Mono<T>` hay `Flux<T>` là publisher. Với nhiều nguồn lạnh, mỗi lần downstream `subscribe()` có thể kích hoạt lại công việc: một HTTP request, truy vấn DB, luồng tính toán hoặc tác dụng phụ. **`retry(1)` cho phép một lần thử lại sau lần lỗi đầu** (tổng tối đa hai lần đăng ký đối với chuỗi một lỗi rồi thành công). Nó không “tiếp tục ở chỗ lỗi” trong subscription cũ; subscription cũ đã kết thúc bằng `onError`, và Reactor **đăng ký lại upstream**.

~~~text
Subscriber
   |
   v
[retry(1)] -- subscribe lần 1 --> [cold source] --> WRITE đã COMMIT
   ^                                             \
   |                                              \-- ACK bị mất --> onError
   |
   +-- subscribe lần 2 --> [cold source] --> WRITE lần nữa --> onNext/complete
~~~

Nếu upstream bao gồm thao tác ghi, **hai lần subscription có thể dẫn tới hai lần ghi**. Đây là điều đúng theo giao thức: Reactor không thể tự biết phản hồi lỗi đến từ việc “chưa ghi được” hay “ghi được nhưng mất phản hồi”.

### Phân biệt các toán tử

| Cách xử lý | Phản ứng với điều kiện nào? | Điều cần nhớ về side effect |
| --- | --- | --- |
| `retry(1)` | Upstream phát `onError` | Đăng ký lại upstream tối đa một lần; có thể thực thi lại ghi |
| `retryWhen(Retry.max(2))` | Lỗi phù hợp với chính sách Retry | Tối đa hai lần retry sau lần đầu; vẫn resubscribe |
| `retryWhen(Retry.backoff(...))` | Lỗi được phép retry, chờ có khoảng cách | Giảm áp lực khi thử lại, **không tự chống ghi trùng** |
| `repeat(n)` | Upstream hoàn thành bình thường | Đăng ký lại ngay cả khi không có lỗi; có thể lặp side effect |
| `onErrorResume(fn)` | Upstream lỗi | Chuyển sang publisher dự phòng; không mặc nhiên retry nguồn cũ |
| `timeout(duration)` | Không có tín hiệu trong giới hạn theo semantics của toán tử | Tạo lỗi timeout; thao tác bên ngoài có thể vẫn đã hoàn tất |
| `cache()` | Tái sử dụng kết quả/tín hiệu đã lưu theo cấu hình | Có thể tránh subscription lặp trong một phạm vi, nhưng **không phải** cơ chế idempotency bền vững giữa nhiều instance/restart |

Với `Flux` có nhiều phần tử, retry sau một lỗi ở phần tử thứ ba có thể làm **hai phần tử đầu được phát lại** ở subscription tiếp theo. Nếu các phần tử trước đó đã kích hoạt side effect, các tác dụng phụ ấy cũng có nguy cơ bị thực hiện lại.

## 3. Định nghĩa chính xác tính lũy đẳng

Một phép toán `f` là **idempotent** nếu áp dụng nhiều lần có cùng tác động trạng thái như áp dụng một lần: `f(f(state)) = f(state)`. Trong hệ thống phân tán, cách hiểu thực tế là **gửi lại cùng một thao tác logic không tạo thêm hiệu ứng nghiệp vụ ngoài ý muốn**.

Ví dụ so sánh:

| Yêu cầu | Lũy đẳng khi nào? | Nguy cơ khi lặp |
| --- | --- | --- |
| “Đặt trạng thái đơn #42 thành PAID” | Có thể lũy đẳng ở trạng thái cuối nếu lệnh được thiết kế không tạo side effect bổ sung | Audit event, email, callback có thể bị phát lại nếu không kiểm soát |
| “Tăng lượt xem thêm 1” | Không lũy đẳng theo cách tăng thông thường | Mỗi lần retry tăng thêm một lượt |
| “Trừ số dư 100.000” | Không lũy đẳng nếu thực hiện lần nào trừ lần đó | Trừ tiền hai lần |
| “Tạo đơn hàng mới” với ID ngẫu nhiên mỗi lần | Không lũy đẳng | Có hai đơn hàng |
| “Tạo đơn hàng” với cùng operation ID được deduplicate bền vững | Có thể đạt hiệu ứng một lần theo operation ID | Cần chống tranh chấp, lưu kết quả và xử lý crash |
| “Lưu tài liệu theo ID và cùng nội dung” | Có thể lũy đẳng về dữ liệu | Trigger, version và event phát sinh có thể khác |
| Đọc tài khoản không làm thay đổi trạng thái | Thường an toàn để retry hơn | Vẫn có tải, audit và khả năng trả dữ liệu đã thay đổi |

**“Idempotent” không đồng nghĩa “không có tác dụng phụ”.** Một lệnh PUT có thể ghi cùng một giá trị nhiều lần mà trạng thái cuối không đổi, nhưng trigger, message hoặc log có thể tăng theo số lần. Bảo đảm phải được định nghĩa theo **hiệu ứng nghiệp vụ cần bảo vệ**: số lần chuyển tiền, số bản ghi đơn, số hóa đơn hoặc số email thực sự gửi.

Trong HTTP, các phương thức như GET/HEAD thường được coi là safe, còn PUT/DELETE có semantics idempotent theo chuẩn ở mức hiệu ứng được yêu cầu; POST thường không mặc định idempotent. **Không căn cứ riêng HTTP method để kết luận một implementation thực tế có thể retry an toàn.** Một endpoint GET làm thay đổi dữ liệu là thiết kế không đúng kỳ vọng; một POST có idempotency key vẫn có thể được thiết kế để chống ghi trùng.

## 4. Ba mốc khác nhau: gửi, thực thi và nhận phản hồi

Hãy theo dõi một lệnh tạo hóa đơn:

~~~text
Client                           Service                         Database
  | POST /invoices key=K            |                                |
  |-------------------------------->|                                |
  |                                 | INSERT invoice(id=777)         |
  |                                 |------------------------------->|
  |                                 | COMMIT thành công               |
  |                                 |<-------------------------------|
  | X mất mạng / timeout            |                                |
  |<--- không nhận được HTTP 201 --- |                                |
  |                                 |                                |
  | RETRY cùng lệnh                 |                                |
  |-------------------------------->|                                |
  |                                 | Nếu không dedup: INSERT thứ hai |
  |                                 |------------------------------->|
  |                                 | Duplicate invoice #778         |
~~~

Client chỉ biết “không thấy phản hồi”, **không biết** server có commit hay chưa. Timeout ở client là dấu hiệu thời gian chờ đã hết; nó không chứng minh rollback. Tương tự, client cancel subscription có thể ngừng chờ, nhưng database hoặc nhà cung cấp thanh toán vẫn có thể đã thực hiện yêu cầu.

Ba kết quả của lần đầu cần phân biệt:

1. **Chưa thực hiện ghi:** retry có thể cần thiết để hoàn thành nghiệp vụ.
2. **Đã ghi, chưa phản hồi thành công:** retry mù có thể tạo duplicate.
3. **Đang xử lý, trạng thái chưa xác định:** một retry đồng thời có thể tranh chấp với yêu cầu gốc.

Một thiết kế an toàn phải trả lời được cả ba, kể cả sau khi ứng dụng crash hoặc có nhiều replica.

## 5. Vì sao side effect trong các toán tử cũng bị lặp

Một side effect không nhất thiết nằm trong repository. Nó có thể là HTTP call, phát email, ghi message, tăng counter, tạo file hoặc callback trong `doOnNext`.

~~~java
Flux<Order> stream = orders
    .doOnNext(order -> sendEmail(order))
    .map(this::convert)
    .retry(1);
~~~

Đây là fragment minh họa, cần `Order`, `orders`, `sendEmail`, `convert`. Nếu một phần sau `doOnNext` báo lỗi, toàn bộ upstream của `retry` được subscribe lại: **email cho những order đã đi qua có thể gửi thêm lần nữa**. Callback `doOnNext` nên dùng chủ yếu để quan sát/log/metrics theo semantics đúng; nếu cần tác dụng phụ bất đồng bộ phải biểu diễn thành publisher có quản lý lỗi và idempotency.

Thứ tự đặt toán tử có ý nghĩa:

~~~java
// Retry bao trùm cả thao tác ghi upstream:
Mono<Result> a = writeOrder()
    .retryWhen(retryPolicy);

// Retry chỉ bao trùm bước đọc sau ghi; vẫn phải xét lỗi của bước ghi:
Mono<Result> b = writeOrder()
    .flatMap(saved -> readRemoteStatus(saved)
        .retryWhen(retryPolicy));
~~~

Đây là các fragment cần triển khai `writeOrder`/`readRemoteStatus`/`retryPolicy`. Trong trường hợp b, retry của `readRemoteStatus` không tự chạy lại `writeOrder` sau khi ghi thành công. Tuy nhiên nó **không** giúp ghi an toàn nếu `writeOrder` tự bị retry ở nơi khác, hoặc client gửi lại toàn bộ HTTP request. Vị trí retry cần được xem xét ở cả client, gateway, controller, service, repository và job/broker.

**`Mono.just(writeBlocking())` không phải một cách làm side effect được quản lý đúng theo subscription.** `writeBlocking()` được gọi ngay khi dựng publisher, thường chặn thread gọi và có thể che giấu hành vi chạy lại. Dùng API non-blocking, hoặc khi bắt buộc tích hợp blocking thì đặt trong `Mono.fromCallable(...)` với scheduler phù hợp; điều đó làm side effect trì hoãn đến subscription nhưng **không tự biến nó thành lũy đẳng**.

## 6. Ví dụ Java 17+ chạy được: retry tạo ghi trùng

Demo này chủ động mô phỏng tình huống: lần đầu **đã ghi thành công**, nhưng chương trình báo `IOException("ACK_LOST")` trước khi trả kết quả. Hai chiến lược được so sánh:

- **Ngây thơ:** mỗi subscription mới ghi lại một lần.
- **Có idempotency key:** dùng cùng khóa để trả về kết quả lần ghi đầu; ví dụ lưu trong `ConcurrentHashMap` để chứng minh nguyên lý trong một JVM.

Tạo một project Maven:

~~~text
reactor-retry-idempotency/
├── pom.xml
├── src/main/java/RetryIdempotencyDemo.java
└── src/test/java/RetryIdempotencyTest.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-retry-idempotency</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>3.6.9</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <version>3.13.0</version>
        <artifactId>maven-compiler-plugin</artifactId>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <version>3.2.5</version>
        <artifactId>maven-surefire-plugin</artifactId>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Nội dung `src/main/java/RetryIdempotencyDemo.java`:

~~~java
import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;

public class RetryIdempotencyDemo {

    private static final AtomicInteger naiveWrites = new AtomicInteger();
    private static final AtomicInteger safeWrites = new AtomicInteger();
    private static final AtomicInteger safeAttempts = new AtomicInteger();
    private static final ConcurrentHashMap<String, String> results =
        new ConcurrentHashMap<>();

    private static Mono<String> unsafeWrite() {
        return Mono.defer(() -> {
            int count = naiveWrites.incrementAndGet(); // đã commit
            if (count == 1) {
                return Mono.error(new IOException("ACK_LOST"));
            }
            return Mono.just("ok");
        });
    }

    private static Mono<String> writeWithKey(String key) {
        return Mono.defer(() -> {
            String value = results.computeIfAbsent(key, ignored -> {
                int serial = safeWrites.incrementAndGet(); // ghi một lần/key
                return "saved-" + serial;
            });

            int attempt = safeAttempts.incrementAndGet();
            if (attempt == 1) {
                return Mono.error(new IOException("ACK_LOST"));
            }
            return Mono.just(value);
        });
    }

    public static void main(String[] args) {
        System.out.println("naive result: "
            + unsafeWrite().retry(1).block());
        System.out.println("naive writes: " + naiveWrites.get());

        System.out.println("safe result: "
            + writeWithKey("order-42").retry(1).block());
        System.out.println("safe writes: " + safeWrites.get());
        System.out.println("safe attempts: " + safeAttempts.get());
    }
}
~~~

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=RetryIdempotencyDemo
~~~

Stdout chính xác từ chương trình:

~~~text
naive result: ok
naive writes: 2
safe result: saved-1
safe writes: 1
safe attempts: 2
~~~

Giải thích cơ chế:

1. `unsafeWrite()` trả một cold `Mono.defer`. Lần đầu được subscribe, biến `naiveWrites` tăng từ 0 lên 1 trước khi lỗi ACK_LOST được phát: mô phỏng **ghi thành công rồi mất xác nhận**.
2. `retry(1)` subscribe lại; lần hai `naiveWrites` tăng lên 2. Về nghiệp vụ, đã có **hai lần ghi**, dù client chỉ nhận kết quả `ok` một lần.
3. `writeWithKey("order-42")` cũng được subscribe hai lần. Nhưng `ConcurrentHashMap.computeIfAbsent` cho cùng khóa chỉ tạo giá trị `saved-1` một lần trong JVM demo, nên `safeWrites=1` còn `safeAttempts=2`.
4. Kết quả `safe result: saved-1` chứng minh ý tưởng “**cùng thao tác logic → cùng key → cùng kết quả đã lưu**”.

**Giới hạn bắt buộc của demo:** `ConcurrentHashMap` chỉ lưu trong bộ nhớ một tiến trình; mất dữ liệu khi restart, không chia sẻ giữa nhiều replica và không bảo đảm tính nguyên tử với database hoặc nhà cung cấp bên ngoài. Vì vậy **không dùng map này làm cơ chế idempotency production**. Mô phỏng “commit” ở đây là tăng bộ đếm, chưa phải một transaction dữ liệu thật.

Ví dụ có `block()` chỉ để in kết quả trong console. Trong WebFlux controller hoặc Netty event loop, hãy **trả về Mono/Flux**; không chờ đồng bộ.

## 7. Idempotency key: định danh một thao tác logic

**Idempotency key** là khóa ổn định được gắn với **một ý định nghiệp vụ**. Khi cùng ý định được gửi lại, server có thể nhận ra và **không thực hiện side effect lần thứ hai**.

Ví dụ người dùng bấm “Thanh toán” cho đơn 42:

~~~text
Logical operation: pay order #42, amount 100000 VND
Idempotency-Key: pay-order-42-attempt-group-8d7f...
       |
       +-- HTTP attempt 1 ──> server
       +-- HTTP attempt 2 ──> server (sau timeout)
       +-- worker redelivery ─> server (nếu cùng logical operation)
       |
       └-- Tất cả phải quy về cùng hiệu ứng nghiệp vụ
~~~

Một thao tác **mới thực sự** phải có key mới. Không sinh key mới mỗi lần retry của cùng thao tác: làm như vậy sẽ phá cơ chế dedup. Ngược lại, không dùng chung một key cho hai lệnh khác nhau.

Quy tắc thiết kế:

- **Phạm vi key:** thường là `tenantId + operationType + key`; chỉ dùng một UUID toàn cục nếu hợp đồng hệ thống đảm bảo namespace phù hợp.
- **Payload fingerprint:** lưu hash/canonical representation của các tham số có ý nghĩa như resource, amount, currency, recipient. Cùng key nhưng payload khác phải bị từ chối rõ ràng, **không trả ngầm kết quả của lệnh cũ**.
- **Kết quả ổn định:** khi lệnh đã thành công, duplicate request nhận lại resource ID, kết quả hoặc trạng thái đã lưu theo hợp đồng; không tạo resource mới.
- **Tác vụ đang xử lý:** yêu cầu đến đồng thời với cùng key có thể nhận 202, 409, trạng thái đang xử lý hoặc chờ kết quả, tùy thiết kế. Không chạy song song hai nghiệp vụ giống nhau.
- **Retention/TTL:** lưu key đủ lâu cho cửa sổ retry, reconnect, redelivery và yêu cầu kiểm toán. Sau khi hết hạn, lệnh cũ có thể bị coi là mới, nên phải tính rõ rủi ro.
- **Không dùng thông tin nhạy cảm làm key thô:** key nên là giá trị ngẫu nhiên đủ khó đoán hoặc định danh được bảo vệ; ràng buộc quyền truy cập theo tenant/chủ sở hữu.
- **Không chỉ tin client:** server cũng có thể có unique business ID như externalOrderId hoặc paymentIntentId để bảo vệ nghiệp vụ.

Một key có thể được gửi bằng HTTP header `Idempotency-Key` hoặc trường trong body/message theo giao thức; tên header không tự tạo tính lũy đẳng. **Bên nhận phải thực thi** việc so sánh, lock/unique constraint, ghi trạng thái và trả kết quả cũ.

## 8. Chống ghi trùng bền vững bằng database

Thiết kế production thường dùng **bảng ghi nhận thao tác lũy đẳng** (idempotency record) hoặc **UNIQUE constraint trên khóa nghiệp vụ**. Ví dụ lược đồ PostgreSQL:

~~~sql
CREATE TABLE idempotent_operation (
    tenant_id          TEXT NOT NULL,
    operation_type     TEXT NOT NULL,
    idempotency_key    TEXT NOT NULL,
    request_hash       TEXT NOT NULL,
    status             TEXT NOT NULL,
    resource_id        TEXT,
    response_payload   JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, operation_type, idempotency_key)
);
~~~

Đây là **một phác thảo schema**, chưa phải toàn bộ chương trình xử lý đồng thời hoặc migration production. Nguyên tắc:

1. Nhận request, xác thực quyền, tạo/kiểm tra operation key và hash payload.
2. Cố gắng **claim key bằng thao tác nguyên tử** (ví dụ insert với UNIQUE/`ON CONFLICT`, hoặc row lock phù hợp). Không dùng “SELECT thấy chưa có rồi INSERT” không khóa, vì hai request đồng thời đều có thể đọc “chưa có”.
3. Nếu đã có key, kiểm tra tenant, operation type, hash. Nếu payload khác, báo xung đột; nếu trạng thái thành công, trả lại kết quả đã lưu; nếu đang xử lý, thực hiện chính sách đang-chờ; nếu thất bại, áp dụng quy tắc retry đã định nghĩa.
4. Thực hiện nghiệp vụ và lưu kết quả theo **cùng giao dịch DB khi khả thi**. Phải đảm bảo việc ghi idempotency record và hiệu ứng dữ liệu liên quan có cùng boundary nguyên tử.
5. Commit, rồi trả response. Nếu response mất, request lặp sẽ đi theo nhánh trả kết quả đã lưu.

### Điều gì nếu hai request mang cùng key đến cùng lúc?

Dựa vào `if (!exists(key)) { write(); }` **không an toàn** khi có concurrency: cả hai có thể kiểm tra chưa tồn tại. Cần cơ chế server-side có tính nguyên tử, ví dụ UNIQUE index và transaction xử lý tranh chấp. Với PostgreSQL, có thể dùng `INSERT ... ON CONFLICT DO NOTHING` để claim nhưng **vẫn phải quyết định vòng đời transaction, lock, status và cách phục hồi**; riêng câu SQL này chưa bảo đảm mọi side effect một lần.

### Nếu crash sau khi ghi dữ liệu nhưng trước khi cập nhật bản ghi key?

Nếu hai ghi nằm trong **một transaction DB thật**, có thể commit/rollback cùng nhau. Nếu ghi nằm ở hai hệ thống khác nhau (DB + email, DB + payment gateway), một transaction DB thông thường **không bao trùm** hệ thống ngoài. Khi đó cần một chiến lược khác: provider-side idempotency key, transactional outbox, trạng thái reconciliation hoặc saga/compensation. Không tuyên bố “bọc `@Transactional`” là đủ để xử lý mọi call bên ngoài.

Một hệ thống đạt **hiệu ứng nghiệp vụ một lần** trong phạm vi có bảo vệ không có nghĩa mọi tầng mạng chỉ phát request một lần. Retry và redelivery có thể vẫn xảy ra; server phải xử lý chúng thành nhiều lần quan sát cùng **một operation ID**.

## 9. Giao dịch reactive và giới hạn của transaction

Spring hỗ trợ `ReactiveTransactionManager` và `TransactionalOperator` cho các thao tác dữ liệu reactive có driver/transaction manager tương ứng. Một transaction có thể bao trùm các thao tác DB tham gia cùng transaction; không tự bảo vệ request HTTP gửi tới service khác.

Mảnh ghép minh họa bên trong service có repository reactive và transactional operator:

~~~java
Mono<Receipt> createReceipt(CreateCommand cmd, String key) {
    Mono<Receipt> action = repository
        .insertOrReadExistingByOperationKey(key, cmd)
        .flatMap(record -> repository.loadReceipt(record.receiptId()));

    return action.as(transactionalOperator::transactional);
}
~~~

**Đây không phải chương trình Java độc lập**: cần định nghĩa `Receipt`, `CreateCommand`, repository và `TransactionalOperator`. Phương thức `insertOrReadExistingByOperationKey` là **hợp đồng cần tự triển khai đúng với UNIQUE/transaction/hash**, không phải API có sẵn của Spring. Chỉ một transaction mà không có logic idempotency cũng có thể **commit hai transaction khác nhau** khi hai lần retry đều hợp lệ.

### Đặt retry so với ranh giới transaction

- Khi `retryWhen` ở **ngoài** publisher đã được transaction hóa, một lần retry có thể bắt đầu **transaction mới**. Nếu lần trước đã commit nhưng mất phản hồi, có nguy cơ ghi lần nữa nếu không dedup.
- Khi retry được đặt **bên trong** pipeline transaction, tùy lỗi và trạng thái transaction, việc tái dùng transaction đã thất bại có thể không hợp lệ. Không “chữa” bằng cách di chuyển toán tử ngẫu nhiên; hãy xác định có thể thử lại toàn bộ giao dịch và đảm bảo idempotency.
- Nếu source bị cancel do client rời kết nối, Spring reactive transaction có semantics rollback đối với cancellation khi transaction còn mở theo quản lý của framework; nhưng **cancellation sau khi commit không thể hoàn tác bản ghi đã commit**, và transaction DB không rollback một lời gọi bên ngoài độc lập.

Điều cần nhớ: **transaction bảo đảm nguyên tử trong phạm vi quản lý**, còn **idempotency xử lý việc cùng yêu cầu logic được gửi lại nhiều lần**. Hai cơ chế bổ sung cho nhau.

## 10. HTTP client WebClient: retry có điều kiện

Khi WebClient gọi một endpoint đọc trạng thái, retry các lỗi kết nối tạm thời có thể phù hợp. Khi gọi **POST tạo giao dịch**, phải có hợp đồng idempotency từ server trước khi bật tự động retry.

Ví dụ tích hợp:

~~~java
Mono<PaymentReceipt> submit(PaymentCommand command, String operationKey) {
    return webClient.post()
        .uri("/payments")
        .header("Idempotency-Key", operationKey)
        .bodyValue(command)
        .retrieve()
        .bodyToMono(PaymentReceipt.class)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(this::isTransient));
}
~~~

Đây là **fragment** cần `webClient`, `PaymentCommand`, `PaymentReceipt` và `isTransient(Throwable)` từ ứng dụng. Cũng cần import `java.time.Duration` và `reactor.util.retry.Retry`. Nó chỉ an toàn nếu endpoint `/payments` **thực sự deduplicate cùng key và payload**, không phải chỉ vì header xuất hiện.

Cần xác định rõ `isTransient` (ví dụ lỗi mạng hoặc HTTP 503 được adapter chuyển thành exception thích hợp) và loại trừ lỗi không nên retry như validation fail, quyền truy cập bị từ chối, trùng key với payload khác, lỗi bảo mật hoặc yêu cầu không lũy đẳng. Với HTTP 4xx, quyết định retry phải dựa từng status và hợp đồng. Không retry vô hạn.

`Retry.backoff(2, ...)` nghĩa là tối đa **hai lần thử lại sau lần đầu**, không phải hai request tổng cộng. Backoff có thể có jitter để tránh nhiều client retry đồng thời; không nên viết test giả định thời gian giữa lần thử luôn chính xác 200 ms.

**Một timeout được đặt ở đâu cũng quan trọng:** timeout cho mỗi attempt khác với deadline toàn operation. Nếu mỗi attempt có timeout riêng và có hai lần retry, tổng thời gian có thể vượt timeout của một attempt. Thiết kế budget thời gian từ client/gateway đến server; khi deadline hết, không tự suy ra thao tác đã rollback.

## 11. Những lỗi nào nên retry?

| Loại thất bại | Thường nên làm gì? | Vì sao |
| --- | --- | --- |
| Lỗi kết nối tạm thời trước lúc biết kết quả | Có thể retry **nếu thao tác an toàn với duplicate** | Có thể chưa gửi/đã gửi; kết quả mơ hồ |
| HTTP 502/503/504 từ downstream | Retry có giới hạn theo chính sách và idempotency | Có thể là lỗi gateway sau khi server xử lý |
| HTTP 429 (rate limit) | Tôn trọng `Retry-After`/quota và giới hạn | Tránh làm quá tải thêm |
| Validation 400 | Không retry nguyên payload | Dữ liệu sai sẽ vẫn sai |
| Unauthorized/Forbidden | Không retry mù | Cần sửa auth/quyền |
| Conflict do cùng key khác payload | Không retry cùng yêu cầu sai | Đây là xung đột nghiệp vụ/contract |
| DB unique violation với operation ID trùng | Tìm và trả kết quả đã lưu nếu payload khớp; xử lý race | Không coi duplicate là “tạo mới lần nữa” |
| Deadlock/serialization failure DB | Có thể retry toàn transaction theo điều kiện, idempotency rõ | Giao dịch trước có thể rollback, nhưng phải xác nhận phạm vi |
| Timeout sau khi gọi payment/external service | Không giả định chưa ghi; reconcile/provider idempotency | Có thể đã commit tại hệ thống bên ngoài |

**Không gom mọi exception thành “transient”.** Một retry policy tốt chỉ retry lỗi được cho phép, có số lần tối đa, backoff có jitter, deadline tổng, chỉ số đo và cơ chế circuit breaker/rate limit nếu phù hợp. Dù vậy, **policy retry không thay thế thiết kế lũy đẳng của bên nhận**.

## 12. Outbox và message delivery: tác dụng phụ ngoài transaction

Một luồng kinh điển: tạo đơn trong DB rồi publish event `OrderCreated`. Nếu commit DB thành công nhưng publish thất bại, retry toàn handler có thể tạo đơn thứ hai. Nếu publish thành công nhưng ứng dụng crash trước khi xác nhận, event có thể được gửi lại khi phục hồi.

**Transactional outbox** là một hướng xử lý:

1. Trong **cùng một transaction DB**, ghi/order update và ghi một outbox event có `eventId` hoặc operation ID duy nhất.
2. Commit transaction: dữ liệu nghiệp vụ và outbox record được bảo toàn cùng nhau.
3. Worker đọc outbox và publish tới broker. Worker có thể retry publish nếu không nhận ack.
4. Consumer dùng event ID và dedup/unique constraint để tránh lặp side effect khi event được giao lại.
5. Đánh dấu outbox đã xử lý theo cơ chế phù hợp và có job dọn/giám sát backlog.

~~~text
HTTP command (operationKey=K)
     |
     v
DB transaction: [Order #42] + [Outbox Event E42]   (một commit)
     |
     v
Outbox publisher --> Broker --> Consumer
                       |            |
                  có thể gửi lại     +-- dedup eventId trước side effect
~~~

Outbox không cam kết “mạng chỉ gửi đúng một message”. Nó giúp tránh mất thông báo giữa **ghi DB và ghi outbox**, còn downstream vẫn cần dedup khi delivery là at-least-once. Nếu consumer gửi email hoặc gọi API thanh toán, event ID/correlation ID phải được ánh xạ tới idempotency key của tác dụng phụ đó.

**Sự khác biệt giữa idempotency và dedup:** dedup xác định nhiều thông điệp là cùng một operation; idempotent processing bảo đảm việc thực hiện lặp không gây thêm hiệu ứng không mong muốn. Một cache “đã thấy message ID” nếu đánh dấu **trước** side effect rồi crash có thể làm **mất xử lý**; nếu đánh dấu **sau** side effect rồi crash có thể gây **lặp xử lý**. Cần nguyên tử hóa trong DB hoặc dùng provider-side idempotency/reconciliation.

## 13. Reactor Retry và những vị trí đặt side effect nguy hiểm

### Retry toàn Flux có thể phát lại item đã thành công

~~~java
Flux<Integer> result = Flux.just(1, 2, 3)
    .doOnNext(n -> System.out.println("received " + n))
    .map(n -> {
        if (n == 3) throw new IllegalStateException("boom");
        return n;
    })
    .retry(1);
~~~

Nếu subscriber yêu cầu đủ dữ liệu, stdout của `doOnNext` có thể ghi `received 1`, `received 2`, `received 3` **hai lượt**, vì mỗi subscription mới bắt đầu lại từ phần tử 1. Nếu `doOnNext` là insert, email hay debit, phần tử 1 và 2 có thể bị xử lý trùng. Luồng cuối vẫn báo lỗi sau khi hết retry.

Để xử lý lỗi riêng **mỗi phần tử**, có thể đưa recovery/retry vào publisher con của phần tử đó:

~~~java
Flux<Result> results = orders
    .concatMap(order ->
        processOneIdempotently(order)
            .retryWhen(perItemPolicy)
            .onErrorResume(error -> Mono.just(
                Result.failed(order.id(), error.getClass().getSimpleName()))));
~~~

Fragment cần `Order`, `Result`, `orders`, `processOneIdempotently` và `perItemPolicy`. Đây là minh họa về **phạm vi retry**: chỉ subscription của item tương ứng được thử lại, nhưng `processOneIdempotently` vẫn phải thiết kế đủ an toàn với trùng thao tác. Với yêu cầu xử lý đồng thời, có thể cân nhắc `flatMapSequential` theo giới hạn; thứ tự đầu ra **không** đảm bảo side effect xảy ra tuần tự.

### Không dùng side effect trong doOnNext thay cho publisher

Sai về semantics composition:

~~~java
Mono<Order> result = repository.save(order)
    .doOnNext(saved -> webClient.post()
        .uri("/notify")
        .bodyValue(saved)
        .retrieve()
        .bodyToMono(Void.class));  // tạo Mono nhưng không subscribe/compose!
~~~

Đoạn này là fragment, cần repository/webClient/Order. Hàm callback `doOnNext` tạo publisher của request notify nhưng **không đưa publisher đó vào pipeline**, nên có thể không gửi notify. Cách compose:

~~~java
Mono<Order> result = repository.save(order)
    .flatMap(saved ->
        sendNotificationWithIdempotency(saved).thenReturn(saved));
~~~

Hàm `sendNotificationWithIdempotency` phải trả Mono và tự định nghĩa cơ chế chống duplicate. Tuy đã compose, nếu toàn chuỗi bị retry, cả save và notify vẫn có thể chạy lại; cần đặt retry đúng phạm vi và bảo vệ cả hai side effect. Có thể dùng outbox thay cho việc giữ HTTP call trong transaction khi cần tính nhất quán.

## 14. Kiểm thử bằng StepVerifier: đếm hiệu ứng, không chỉ đếm kết quả

Trong project Maven ở phần 6, tạo `src/test/java/RetryIdempotencyTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryIdempotencyTest {

    @Test
    void retryResubscribesAndRepeatsUnsafeSideEffect() {
        AtomicInteger writes = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            int count = writes.incrementAndGet();
            if (count == 1) {
                return Mono.error(new IOException("ack lost"));
            }
            return Mono.just("ok");
        });

        StepVerifier.create(source.retry(1))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(2, writes.get());
    }

    @Test
    void sameKeySuppressesDuplicateEffectInOneProcess() {
        ConcurrentHashMap<String, String> store = new ConcurrentHashMap<>();
        AtomicInteger writes = new AtomicInteger();
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            String result = store.computeIfAbsent("invoice-7", key -> {
                writes.incrementAndGet();
                return "committed";
            });

            if (attempts.incrementAndGet() == 1) {
                return Mono.error(new IOException("ack lost"));
            }
            return Mono.just(result);
        });

        StepVerifier.create(source.retry(1))
            .expectNext("committed")
            .verifyComplete();

        assertEquals(2, attempts.get());
        assertEquals(1, writes.get());
    }

    @Test
    void doNotRetryBusinessValidationFailures() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.error(new IllegalArgumentException("invalid"));
        });

        StepVerifier.create(
                source.retryWhen(
                    Retry.max(2).filter(IOException.class::isInstance)))
            .expectError(IllegalArgumentException.class)
            .verify();

        assertEquals(1, attempts.get());
    }
}
~~~

Chạy:

~~~bash
mvn -q test
~~~

Khi ba test pass, Maven trả exit code 0; tùy cấu hình `-q` có thể không in dòng kết quả chi tiết. Các kiểm thử tập trung vào **số lần thực sự thực hiện side effect**:

- Test đầu cho thấy source được subscribe hai lần và thao tác “ghi” tăng hai lần.
- Test thứ hai chứng minh cùng key trong một JVM chỉ tạo một hiệu ứng mặc dù có hai attempts; không xem map in-memory là cơ chế production.
- Test thứ ba chứng minh filter trong `Retry.max(2)` không retry `IllegalArgumentException`, nên không làm lại yêu cầu lỗi nghiệp vụ.

Với database thật, cần thêm **integration test về concurrency và crash**: hai request cùng key đến đồng thời; key giống nhau nhưng payload khác; server chết trước/sau commit; response bị mất; retry từ nhiều instance; duplicate message từ broker; TTL hết hạn. Unit test mock repository không chứng minh được nguyên tử dữ liệu thực tế.

### Kiểm thử tránh lỗi do thời gian

Backoff với jitter làm thời gian thử lại thay đổi. Unit test nên kiểm tra **số attempts, loại lỗi được retry, kết quả và số hiệu ứng nghiệp vụ**; nếu cần kiểm tra logic timing, dùng virtual time và đừng khẳng định mốc thời gian tuyệt đối của scheduler thực. Tránh `Thread.sleep` để “đợi retry” trong test reactive.

## 15. Bốn cấp độ an toàn khác nhau

**Cấp 1 — Không retry:** chỉ gửi một lần. Vẫn có thể có duplicate từ client double-click, gateway, broker hoặc người dùng gửi lại. “Không có `retry` trong source code này” chưa đủ chứng minh không bao giờ ghi trùng.

**Cấp 2 — Retry có lọc lỗi/backoff:** giảm lỗi tạm thời và tránh spam. Nhưng nếu operation không idempotent, duplicate write vẫn có thể xảy ra.

**Cấp 3 — Một tiến trình nhớ key:** cache/ConcurrentHashMap hoặc state trong memory có thể ngăn duplicate trong phạm vi hẹp. Không sống qua restart, scaling, eviction; không bảo đảm với side effect bên ngoài.

**Cấp 4 — Idempotent business operation bền vững:** key có phạm vi rõ ràng, hash payload, unique constraint/locking, transaction và trạng thái kết quả, chính sách xử lý đang chạy/crash, TTL, reconciliation; tích hợp hệ thống ngoài bằng provider key hoặc outbox/dedup phù hợp. Đây là cấp độ phù hợp cho nghiệp vụ ghi quan trọng.

Không nên nói “đạt exactly once end-to-end” nếu vẫn có hệ thống độc lập không chia sẻ transaction. Mục tiêu thực tiễn là **at-least-once delivery có dedup/idempotency để chỉ tạo một hiệu ứng nghiệp vụ trong phạm vi bảo vệ được xác định**.

## 16. Khả năng quan sát và đối soát

Những chỉ số nên đo:

- **Logical operations:** số operation key mới được tạo thành công.
- **Attempts:** tổng số lần yêu cầu được thử, tách lần đầu và lần retry.
- **Duplicate detected:** số lần key đã tồn tại và kết quả cũ được trả lại.
- **Conflicts:** số lần cùng key nhưng payload hash khác.
- **In-progress collisions:** số yêu cầu trùng key đang chờ xử lý.
- **Outcome:** committed, rejected, failed, unknown/reconciling.
- **Retry causes:** timeout, connection, 5xx, rate limit, DB transient error.
- **Outbox:** backlog, tuổi event lâu nhất, retry publish, dedup tại consumer.
- **End-to-end effect:** số bản ghi thanh toán/đơn hàng thực sự tạo so với số operation key hợp lệ.

Dùng correlation ID để nối logs của cùng logical operation qua các attempts. Đừng dùng số attempts làm số lượng “đơn mới”, và tránh ghi raw token, thông tin thanh toán hay payload nhạy cảm vào log. Nếu operation ID có cardinality cao, không đưa từng ID thành nhãn metric thô; dùng log/tracing để tra cứu chi tiết và metric tổng hợp theo trạng thái.

Một tình huống cần **reconciliation**: provider đã thanh toán nhưng service chưa ghi trạng thái DONE. Nếu chỉ đọc local status rồi thử lại mà không xác minh bên ngoài, bạn có thể tạo khoản thanh toán thứ hai. Cần tra trạng thái theo provider operation ID hoặc tái gửi **cùng idempotency key được provider hỗ trợ**, và quyết định trạng thái kết quả theo hợp đồng thực tế.

## 17. Những lỗi triển khai thường gặp

1. **Bật `retry(3)` lên POST ghi tiền mà không có idempotency key.** Có thể tạo bốn lần tác dụng phụ.
2. **Tạo key mới ở mỗi attempt.** Bên nhận coi mỗi attempt là một operation khác.
3. **Chỉ kiểm tra “đã tồn tại?” rồi mới INSERT.** Hai request đồng thời có thể cùng đi qua; cần unique constraint/atomic claim.
4. **Dùng Redis/in-memory marker không có quy tắc nguyên tử với side effect.** Marker và hiệu ứng có thể lệch khi crash.
5. **Coi HTTP timeout là chắc chắn chưa ghi.** Phản hồi có thể bị mất sau commit.
6. **Đặt `doOnNext` để gửi email rồi retry cả Flux.** Các item đã xử lý có thể gửi lại.
7. **Retry mọi exception, kể cả 400/validation/auth.** Lặp yêu cầu không thể thành công nếu input/quyền không thay đổi.
8. **Dùng backoff rồi tin rằng đủ chống duplicate.** Backoff chỉ điều chỉnh thời điểm thử lại.
9. **Không ràng buộc key với payload.** Client có thể tái dùng key cho yêu cầu khác, gây nhầm kết quả hoặc lỗi bảo mật.
10. **Lưu kết quả key nhưng không xử lý trạng thái IN_PROGRESS.** Hai request đồng thời có thể đua nhau ghi.
11. **Đánh dấu DONE trước khi hiệu ứng ngoài hoàn thành.** Crash sau marker có thể làm mất hiệu ứng.
12. **Đánh dấu DONE sau hiệu ứng ngoài nhưng không có provider key.** Crash trước marker có thể khiến retry phát hiệu ứng lần nữa.
13. **Cho rằng DB transaction bao trùm email/payment gateway.** Chỉ có tài nguyên tham gia transaction được bảo vệ.
14. **Không kiểm tra retention.** Key hết hạn trước cửa sổ redelivery có thể tạo operation mới ngoài ý muốn.
15. **Quên retry ở tầng khác.** Client library, load balancer, gateway, scheduled job và broker consumer đều có thể gửi lại.
16. **Dùng `collectList().block()` trong WebFlux handler.** Chặn event loop, làm tăng độ trễ và khó kiểm soát cancellation.
17. **Không test hai request cùng key chạy song song.** Demo tuần tự không chứng minh bảo vệ race condition.
18. **Lẫn lộn thứ tự kết quả với thứ tự hiệu ứng.** `flatMapSequential` giữ thứ tự phát downstream, không bắt ghi vào DB theo đúng thứ tự.
19. **Dùng `cache()` để chống trùng giao dịch toàn hệ thống.** Cache nằm trong phạm vi publisher/process và có chính sách sống riêng.
20. **Không có cách đối soát trạng thái không xác định.** Khi mất ack cần reconcile, không chỉ retry mù.

## 18. Bài tập tình huống

**Bài 1.** `Mono.defer(this::saveOrder).retry(2)` có thể gọi `saveOrder` bao nhiêu lần khi hai lần đầu phát lỗi?  
**Đáp án:** Tối đa ba subscription/call khi lỗi tiếp diễn đủ điều kiện: một lần đầu và hai lần thử lại. Nếu mỗi lần ghi đã commit trước khi lỗi, có thể có ba side effect.

**Bài 2.** Client POST tạo đơn được HTTP timeout. Có thể suy ra server chưa tạo đơn?  
**Đáp án:** Không. Timeout là không nhận kết quả đúng hạn, không phải bằng chứng rollback. Cần key và tra cứu/replay kết quả đã lưu.

**Bài 3.** Tại sao cùng idempotency key phải đi kèm so khớp payload?  
**Đáp án:** Để tránh một key bị tái dùng cho amount/resource khác mà server trả kết quả sai hoặc bỏ thao tác mới. Phải phân biệt duplicate hợp lệ với key conflict.

**Bài 4.** Hai request cùng key đến đồng thời. Lệnh “nếu không tồn tại thì INSERT” với SELECT trước có đủ không?  
**Đáp án:** Không. Cần UNIQUE constraint/atomic claim và chính sách transaction/locking để tránh race.

**Bài 5.** Một transaction DB ghi order rồi gọi email bên ngoài. Transaction rollback có tự xóa email đã gửi không?  
**Đáp án:** Không. Email không nằm trong transaction DB; cần outbox/idempotency và chiến lược xử lý lỗi phù hợp.

**Bài 6.** `Retry.backoff(3, Duration.ofMillis(100))` có chống ghi trùng không?  
**Đáp án:** Không. Nó giảm tốc độ và giới hạn ba lần thử lại, nhưng vẫn resubscribe nguồn ghi.

**Bài 7.** Publisher đã phát item 1 và 2 kèm side effect, lỗi ở item 3 rồi retry toàn Flux. Item 1/2 có thể xử lý lần nữa không?  
**Đáp án:** Có, nếu nguồn lạnh phát lại từ đầu. Muốn tránh phải thiết kế idempotency theo item/operation hoặc đặt retry trong nhánh xử lý từng item phù hợp.

**Bài 8.** Cùng mã giao dịch đã được xử lý ở replica A. Sau khi A restart, replica B nhận lại request. Map in-memory có bảo vệ được không?  
**Đáp án:** Không. Cần trạng thái bền vững/chia sẻ với unique constraint và cơ chế thực thi nguyên tử theo phạm vi.

**Bài 9.** Một outbox message đã publish nhưng worker crash trước khi đánh dấu sent. Điều gì xảy ra?  
**Đáp án:** Nó có thể được publish lại. Consumer cần dedup theo event ID hoặc xử lý lũy đẳng.

**Bài 10.** Một yêu cầu tạo lệnh thanh toán “mới” có cùng amount và user với lệnh cũ. Có nên dùng lại key cũ?  
**Đáp án:** Không nếu đó là **ý định nghiệp vụ khác**. Key phải gắn với logical operation, không đơn giản là hash của amount + user.

**Bài 11.** Trong WebFlux, gọi `subscribe()` để “chắc chắn DB write chạy”, sau đó return `Mono.just("ok")` có an toàn không?  
**Đáp án:** Không. Nó tách tác vụ ghi khỏi lifecycle, kết quả và lỗi của response. Trả publisher đã compose để WebFlux quản lý, kết hợp idempotency/transaction phù hợp.

**Bài 12.** Dùng `retryWhen` nhưng chọn một filter chỉ retry `IOException`; một lỗi validation xảy ra thì sao?  
**Đáp án:** Lỗi validation được phát xuống downstream theo chính sách, không có retry; đó là hành vi mong muốn nếu payload không hợp lệ.

## 19. Checklist triển khai thao tác ghi có retry

Trước khi triển khai hoặc bật tự động thử lại, hãy trả lời:

- **Logical operation là gì?** Đơn hàng, thanh toán, chuyển khoản, email hay ghi bản ghi nào?
- **Ai tạo key và khi nào?** Key tồn tại xuyên qua tất cả attempts, retry từ gateway và redelivery từ broker chưa?
- **Scope key là gì?** Tenant, loại thao tác, resource, phiên bản API?
- **Cùng key nhưng payload khác được xử lý thế nào?**
- **Ai sở hữu side effect?** Repository DB, service ngoài, broker, gateway hay nhiều nơi?
- **Đã có ràng buộc bền vững chống race?** UNIQUE/transaction/locking phù hợp chưa?
- **Có lưu kết quả cũ và trạng thái đang xử lý không?**
- **Nếu crash giữa hai hệ thống, có reconcile/outbox/provider idempotency không?**
- **Lỗi nào thực sự transient?** Có giới hạn retry, jitter/backoff và deadline tổng không?
- **Retry nằm ở đâu trong chuỗi Reactor?** Nó có vô tình bao trùm việc ghi đã thành công không?
- **Lần thử lặp của Flux có thể phát lại những item nào?**
- **Có test hai request đồng thời, mất ACK sau commit, restart, duplicate delivery và key conflict không?**
- **Có metrics tách số attempts khỏi số logical operations không?**
- **TTL của key có đủ cho cửa sổ retry, đối soát và yêu cầu nghiệp vụ không?**

**Nguyên tắc cốt lõi:** `retry`/`retryWhen` chỉ quản lý **cơ chế thử lại khi có lỗi**. Tính lũy đẳng phải được thiết kế tại **ranh giới thực thi side effect**, bằng operation ID ổn định và bảo vệ bền vững phù hợp. Dù client nhận một response duy nhất, hệ thống có thể đã nhận nhiều attempts; mục tiêu là nhiều attempts ấy vẫn tạo **một hiệu ứng nghiệp vụ đúng theo hợp đồng**.

### Tài liệu tham khảo

- Project Reactor, [Reactor Reference – Error Handling and Retrying](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- Project Reactor, [Retry API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html).
- Spring Framework, [Programmatic Transaction Management – TransactionalOperator](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).
- Spring Framework, [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- MDN, [HTTP Idempotency-Key header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Idempotency-Key).
- [Reactive Streams Specification](https://www.reactive-streams.org/).
