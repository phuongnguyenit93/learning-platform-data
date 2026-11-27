# Backoff và giới hạn tải lên directory server trong Spring LDAP

## 1. Vì sao cần kiểm soát tải khi ứng dụng truy cập LDAP?

Trong một hệ thống dùng **Spring LDAP**, những lệnh đọc tưởng chừng nhỏ như tìm `uid`, kiểm tra thành viên nhóm hay tra cứu DN thường nằm trên đường xử lý đăng nhập, cấp quyền và các API có lưu lượng lớn. Khi nhiều instance cùng dùng `LdapTemplate`, `LdapClient` hoặc ODM để truy cập một LDAP directory, tổng số kết nối và truy vấn có thể vượt khả năng phục vụ của directory server.

Hậu quả không chỉ là response chậm. Một lượng lớn request chưa hoàn tất có thể làm đầy connection pool, chiếm các thread HTTP, tăng bộ nhớ phía ứng dụng và khiến LDAP server mất thêm thời gian phục hồi. Nếu mọi instance lập tức **retry** khi kết nối chậm, hệ thống còn khuếch đại tải ngay lúc LDAP đang suy yếu.

Bài học thuộc chương **Vận hành** của module **SPRING_LDAP** giải thích cách phối hợp:

- **Backoff + jitter:** phân tán các lần thử lại sau lỗi tạm thời.
- **Rate limiting:** giới hạn số lần gọi LDAP được phát sinh trong một khoảng thời gian.
- **Concurrency limiting/bulkhead:** giới hạn số thao tác LDAP đang chạy đồng thời.
- **Bounded queue và load shedding:** xử lý có kiểm soát khi ứng dụng nhận nhiều yêu cầu hơn năng lực LDAP.
- **Pool, timeout, search limit và quan sát:** giữ tiêu thụ tài nguyên dự đoán được.

Mục tiêu là bảo vệ cả **directory server** lẫn ứng dụng khi tải tăng, đồng thời giữ đúng chức năng tra cứu, xác thực và quyền truy cập. Các ví dụ minh họa trên Java 17+, Spring Boot 3.x và Spring LDAP; thông số là giả định dành cho học tập và phải được hiệu chỉnh bằng đo đạc trước khi vận hành.

## 2. Hiểu chính xác điều gì tạo ra tải LDAP

Một HTTP request không nhất thiết tương đương một LDAP operation. Một lần đăng nhập có thể tìm DN người dùng, bind để xác thực, tìm nhóm, đọc thuộc tính và kiểm tra một số membership. Một API khác có thể phân trang tìm kiếm nhiều lần.

### 2.1. Ba đại lượng phải theo dõi

| Đại lượng | Định nghĩa | Đơn vị | Ý nghĩa |
| --- | --- | --- | --- |
| **Request rate** | Số HTTP request/giây đến ứng dụng | request/s | Lượng công việc đầu vào |
| **LDAP operation rate** | Tổng bind/search/lookup/modify/… thực gửi tới LDAP | operation/s | Áp lực thao tác lên directory |
| **In-flight LDAP operations** | Số thao tác đang chờ hoặc xử lý tại thời điểm quan sát | operation | Áp lực đồng thời lên connection, thread và server |

Ước lượng ban đầu khi tải ổn định:

\[
\lambda_{\mathrm{LDAP}} \approx
\sum_{i=1}^{N} \lambda_{\mathrm{app},i}
\, k_i \, a_i
\]

Trong đó:

- `N` là số instance ứng dụng;
- `\lambda_{\mathrm{app},i}` là request/s trên instance `i`;
- `k_i` là số LDAP operation **logic** trung bình trên một request;
- `a_i` là số attempt trung bình cho mỗi operation, bao gồm retry.

Nếu mỗi LDAP operation trải qua thời gian trung bình `W` giây, có thể ước lượng số operation đang thực thi bằng định luật Little:

\[
L \approx \lambda_{\mathrm{LDAP}} \times W
\]

Đây là phép ước lượng cho hệ thống ở trạng thái tương đối ổn định, không phải bảo đảm về đỉnh tải hay giới hạn tài nguyên. Giá trị `W` phải là thời gian trung bình được đo đúng phạm vi; dùng p99 thay cho giá trị trung bình trong công thức sẽ không còn là áp dụng trực tiếp định luật Little.

**Ví dụ giả định:** bốn instance, mỗi instance xử lý 40 request/s, mỗi request có trung bình 1,5 LDAP operation và mỗi operation tạo trung bình 1,2 attempt:

\[
\lambda_{\mathrm{LDAP}}=4\times40\times1.5\times1.2=288
\text{ operation/s}.
\]

Nếu thời gian mỗi operation trung bình 0,1 giây, in-flight khoảng `28,8`. Khi LDAP chậm tới trung bình 0,4 giây mà tốc độ đưa việc vào không đổi, in-flight có xu hướng tăng tới `115,2`. Nếu không chặn tải ở ứng dụng, số thao tác chờ còn có thể tăng khi hàng đợi tích tụ.

**Kết luận vận hành:** mức tối đa nên dựa trên khả năng thực tế của các LDAP node, SLA, loại operation, cấu hình replica và chi phí tìm kiếm; không lấy số thread HTTP hay số connection tối đa của ứng dụng làm chỉ tiêu năng lực directory server.

### 2.2. Không phải mọi LDAP operation tiêu tốn như nhau

| Operation | Những yếu tố ảnh hưởng chi phí | Cách giảm tải |
| --- | --- | --- |
| Bind/xác thực | TLS, cơ chế xác thực, chính sách account, số kết nối mới | Tái sử dụng connection khi phù hợp; tránh bind phụ không cần thiết |
| Lookup một DN cụ thể | Kích thước entry, thuộc tính trả về, ACL | Chỉ lấy thuộc tính cần thiết |
| Search theo `uid` | Filter, chỉ mục, scope, giới hạn kết quả | Filter đúng chỉ mục, base DN hẹp, giới hạn số entry |
| Search nhóm nhiều tầng | Số nhóm, alias/referral, độ sâu | Thiết kế query và cache hợp lý theo nghiệp vụ |
| Paged search | Số trang và kích thước trang | Cân đối page size; có giới hạn tổng số trang và thời gian |
| Add/modify/delete/modDN | Ghi đồng bộ, index update, replication | Tránh ghi lặp; kiểm soát đồng thời và ngữ nghĩa retry |

Đọc một thuộc tính của một entry đã biết và tìm kiếm toàn bộ subtree có thể có chi phí rất khác nhau. Vì vậy cần phân nhóm metric theo **loại thao tác**, không chỉ đếm “số lần gọi LDAP”.

## 3. Phân biệt rate limit, concurrency limit, queue và backoff

Bốn cơ chế giải quyết bốn dạng rủi ro khác nhau:

| Cơ chế | Điều tiết điều gì? | Khi nào tác động? | Khi hết ngân sách |
| --- | --- | --- | --- |
| **Rate limiter** | Số operation được phát đi trong một khoảng thời gian | Trước khi gọi LDAP | Từ chối, chờ có giới hạn hoặc chuyển sang fallback hợp lệ |
| **Bulkhead / semaphore** | Số operation đang thực thi đồng thời | Trước khi mượn context/kết nối LDAP | Từ chối hoặc chờ trong hàng đợi hữu hạn |
| **Bounded queue** | Số request đang đợi tới lượt | Trước hoặc tại hàng đợi task | Load shed: không giữ thêm công việc |
| **Backoff** | Thời điểm gửi **lại** sau lỗi tạm thời | Sau một attempt thất bại | Dừng khi hết attempt, deadline hoặc server quá tải |

Giảm rate không tự giới hạn số operation đang chạy nếu response trở nên rất chậm. Giới hạn concurrency cũng không tự ngăn được nhiều operation rất nhanh trên mỗi giây. Backoff chỉ có tác dụng với retry, không chặn lượng yêu cầu gốc đang đổ vào.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ"] --> B{"Còn ngân sách request?"}
    B -->|Không| Z["Trả kết quả quá tải/timeout theo API contract"]
    B -->|Có| C{"Còn slot đồng thời?"}
    C -->|Không| Z
    C -->|Có| D{"Còn rate token?"}
    D -->|Không| E["Release slot, xử lý quá tải"]
    D -->|Có| F["LDAP attempt với timeout & search limit"]
    F --> G["Release slot"]
    G --> H{"Thành công?"}
    H -->|Có| I["Trả dữ liệu"]
    H -->|Không| J{"Lỗi tạm thời, read an toàn, còn attempt/deadline?"}
    J -->|Không| K["Truyền lỗi có phân loại"]
    J -->|Có| L["Backoff + jitter, không giữ slot"]
    L --> B
~~~

**Quy tắc tổ chức:** mỗi lần gọi LDAP thực tế, kể cả retry, phải đi qua chính sách giới hạn tải. Nếu retry được thực hiện ngoài rate limiter thì khi gặp sự cố, nhiều request có thể nhân tải lên LDAP dù request ban đầu đã được giới hạn.

Không giữ connection hay semaphore trong lúc ngủ backoff: hành vi đó làm cạn tài nguyên và chặn các request đang có khả năng thành công.

## 4. Backoff có jitter: phục hồi mà không gây retry storm

Giả sử LDAP server trả lỗi mạng tạm thời. Nếu 100 instance đều retry sau đúng 500 ms, các lần thử tiếp theo lại tạo đỉnh tải đồng loạt. **Jitter** làm lệch thời điểm retry giữa các instance.

### 4.1. Các kiểu backoff thường gặp

| Chiến lược | Công thức cho retry thứ `k` | Tác động |
| --- | --- | --- |
| Fixed delay | `d_k=b` | Dễ hiểu nhưng có thể tạo đỉnh retry đồng pha |
| Exponential | `d_k=\min(d_{\max}, b2^{k-1})` | Giảm dần tần suất retry, nhưng có thể vẫn đồng pha |
| Full jitter | `U(0,\min(d_{\max},b2^{k-1}))` | Tán rộng thời điểm thử lại |
| Equal jitter | `d_k/2 + U(0,d_k/2)` | Giữ khoảng nghỉ tối thiểu và thêm dao động |
| Decorrelated jitter | Phụ thuộc delay trước đó và giới hạn trần | Tránh chuỗi delay cứng; cần giới hạn hợp lý |

`b` là delay cơ sở, `d_{\max}` là trần backoff, `k` bắt đầu từ 1 cho lần **retry đầu tiên**, và `U` là giá trị ngẫu nhiên trong khoảng. Các chiến lược đều cần số lượt retry tối đa và hạn chót tổng thể.

**Ví dụ (chỉ minh họa):** `b=100 ms`, `d_{\max}=800 ms`, equal jitter:

| Lần retry | Exponential ceiling | Khoảng delay equal jitter |
| ---: | ---: | ---: |
| 1 | 100 ms | 50–100 ms |
| 2 | 200 ms | 100–200 ms |
| 3 | 400 ms | 200–400 ms |
| 4 | 800 ms | 400–800 ms |
| 5 | 800 ms | 400–800 ms |

Các khoảng trên chưa kể thời gian LDAP attempt. Không đặt trần lớn hơn ngân sách request nếu tác vụ cần trả kết quả nhanh.

### 4.2. Ví dụ Java cho delay equal jitter

~~~java
import java.util.concurrent.ThreadLocalRandom;

public final class LdapBackoff {
    private static final long BASE_MS = 100L;
    private static final long MAX_MS = 800L;

    private LdapBackoff() {}

    // retryNumber = 1 nghĩa là lần retry đầu tiên; giới hạn <= 4 ở ví dụ này.
    public static long delayMs(int retryNumber) {
        if (retryNumber < 1 || retryNumber > 4) {
            throw new IllegalArgumentException("Unsupported retry number");
        }

        long ceiling = Math.min(
                MAX_MS, BASE_MS * (1L << (retryNumber - 1)));
        long lower = ceiling / 2L;
        return ThreadLocalRandom.current().nextLong(lower, ceiling + 1L);
    }
}
~~~

Ví dụ chỉ sinh delay; caller cần kiểm tra đủ ngân sách và thực hiện chờ có thể bị ngắt. Trên đường xử lý đồng bộ, `Thread.sleep` tiêu tốn thread trong lúc chờ; khi tải lớn, nên dùng cơ chế scheduling/bất đồng bộ có giới hạn phù hợp kiến trúc ứng dụng.

### 4.3. Trường hợp được thử lại và trường hợp phải dừng

- **Có điều kiện với phép đọc:** `CommunicationException`, `ServiceUnavailableException`, `ConnectException`, `SocketTimeoutException` hoặc LDAP result code 51 (`busy`), 52 (`unavailable`) được nhận diện tin cậy từ provider/server; chỉ retry nếu dữ liệu còn hữu ích và deadline cho phép.
- **Fail fast:** bind sai credential (mã 49), ACL từ chối (mã 50), DN/filter không hợp lệ, lỗi schema, chứng chỉ TLS, hostname không khớp; retry không giải quyết nguyên nhân.
- **Không tự retry thao tác ghi:** sau timeout, server có thể đã thực hiện `modify`, `add`, `delete` hoặc `modDN` nhưng phản hồi bị mất. Cần cơ chế idempotency, xác minh trạng thái và xử lý concurrency trước khi cân nhắc gửi lại.

Spring LDAP có thể chuyển đổi các exception JNDI thành exception runtime của Spring. Bộ phân loại nên kiểm tra cause chain và result code có cấu trúc nếu provider hỗ trợ; không tìm chữ “timeout” trong thông báo lỗi để quyết định retry.

LDAP không cung cấp một `Retry-After` phổ quát cho mọi phản hồi `busy/unavailable` như một số giao thức HTTP. Nếu directory hoặc hạ tầng trả gợi ý chờ cụ thể qua cơ chế được hỗ trợ, có thể dùng gợi ý đó trong giới hạn deadline; không tự giả định server đã chỉ định khoảng chờ.

## 5. Giới hạn đồng thời và tốc độ gọi bằng Java

Một cách thực dụng khi dùng `LdapTemplate` là đặt **gate tại boundary LDAP**. Gate sử dụng `Semaphore` để giới hạn in-flight operation và token bucket để giới hạn operation/s.

Ví dụ dưới đây chỉ minh họa **giới hạn trong một JVM**; nếu triển khai 4 instance, mỗi instance có hạn mức riêng thì tổng giới hạn toàn cụm có thể gấp 4. Mọi LDAP operation từ instance đó cần đi qua gate hoặc một cơ chế tương đương thì giới hạn mới có ý nghĩa.

### 5.1. Gate đồng thời + token bucket

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public final class LdapLoadGate {
    private final Semaphore slots;
    private final double tokensPerSecond;
    private final double burstCapacity;

    private double availableTokens;
    private long lastRefillNanos;

    public LdapLoadGate(
            int maxConcurrent,
            double tokensPerSecond,
            int burstCapacity) {

        if (maxConcurrent <= 0 || tokensPerSecond <= 0 || burstCapacity <= 0) {
            throw new IllegalArgumentException("Limits must be positive");
        }

        this.slots = new Semaphore(maxConcurrent, true);
        this.tokensPerSecond = tokensPerSecond;
        this.burstCapacity = burstCapacity;
        this.availableTokens = burstCapacity;
        this.lastRefillNanos = System.nanoTime();
    }

    // Bao một LDAP attempt, không bao gồm thời gian chờ backoff.
    public <T> T executeOnce(Supplier<T> ldapOperation) {
        if (!slots.tryAcquire()) {
            throw new LdapCapacityRejectedException(
                    "LDAP concurrency budget exhausted");
        }

        try {
            if (!tryTakeToken()) {
                throw new LdapCapacityRejectedException(
                        "LDAP rate budget exhausted");
            }
            return ldapOperation.get();
        } finally {
            slots.release();
        }
    }

    private synchronized boolean tryTakeToken() {
        long now = System.nanoTime();
        long elapsedNanos = Math.max(0L, now - lastRefillNanos);

        availableTokens = Math.min(
                burstCapacity,
                availableTokens +
                        ((double) elapsedNanos / TimeUnit.SECONDS.toNanos(1))
                                * tokensPerSecond);

        lastRefillNanos = now;
        if (availableTokens < 1.0) {
            return false;
        }

        availableTokens -= 1.0;
        return true;
    }

    public static final class LdapCapacityRejectedException
            extends RuntimeException {
        public LdapCapacityRejectedException(String message) {
            super(message);
        }
    }
}
~~~

**Giải thích thiết kế:**

- `slots.tryAcquire()` không chờ; khi hết slot, request bị từ chối ngay. Đây là **load shedding**, giúp không tích tụ vô hạn công việc đang chờ.
- `tryTakeToken()` đồng bộ hóa một trạng thái token bucket nhỏ. Sau thời gian nhàn rỗi, bucket có thể tích lũy tối đa `burstCapacity` token.
- Một token được tiêu thụ cho **một LDAP attempt thực sự được cho phép**. Kể cả attempt lỗi mạng, token không được hoàn lại; nếu hoàn lại sẽ mất tác dụng giới hạn tải khi server hỏng.
- Semaphore được nhả trong `finally` cả khi LDAP operation hoặc rate gate ném lỗi.
- Từ chối do giới hạn nội bộ **không phải lỗi mạng LDAP tạm thời** và không nên gửi vào vòng retry mạng; nếu nghiệp vụ cho phép chờ thì cần một cơ chế hàng đợi **hữu hạn** riêng.
- Gate này không giới hạn số socket TLS/BIND theo toàn cụm, không thay thế cấu hình pool và không biết trạng thái tải của directory server.

Có thể khởi tạo gate bằng bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LdapTrafficConfiguration {
    @Bean
    LdapLoadGate ldapLoadGate() {
        // Mỗi JVM: tối đa 8 attempts đồng thời, 30 attempts/s,
        // cho phép burst tạm thời tối đa 12 tokens.
        return new LdapLoadGate(8, 30.0, 12);
    }
}
~~~

**Không áp dụng nguyên xi các số 8/30/12:** cần kiểm thử năng lực server và căn theo tổng số replica/worker. Nếu tăng số instance từ 4 lên 8 mà giữ nguyên token bucket, tổng phép gọi được phép cũng tăng gấp đôi.

### 5.2. Dùng gate tại LdapTemplate

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldap;
    private final LdapLoadGate gate;

    public DirectoryLookupService(LdapTemplate ldap, LdapLoadGate gate) {
        this.ldap = ldap;
        this.gate = gate;
    }

    public List<String> findCommonNames(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        return gate.executeOnce(() -> findCommonNamesOnce(uid));
    }

    private List<String> findCommonNamesOnce(String uid) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"cn"});
        controls.setCountLimit(2);
        controls.setTimeLimit(1000); // ms, giới hạn cho search

        String filter = new EqualsFilter("uid", uid).encode();

        return ldap.search(
                "ou=people",
                filter,
                controls,
                (AttributesMapper<String>) attrs -> {
                    Attribute cn = attrs.get("cn");
                    if (cn == null) {
                        throw new IllegalStateException(
                                "Expected cn is not readable");
                    }
                    return String.valueOf(cn.get());
                });
    }
}
~~~

Ở đây `uid` được encode qua `EqualsFilter` để tránh ghép trực tiếp filter từ dữ liệu người dùng. Scope `ONELEVEL_SCOPE` chỉ tìm các entry con trực tiếp dưới `ou=people`. Nếu mô hình DIT thực tế đặt người dùng ở nhiều OU con, cần sửa scope hoặc chiến lược truy vấn có giới hạn đúng với schema.

**Điều kiện để giới hạn thật sự có hiệu lực:** tất cả caller đọc LDAP phải dùng cùng gate; những nhánh xác thực, ODM, `LdapClient` hoặc job nền truy cập trực tiếp khác cần chính sách chung hoặc hạn mức riêng được tính trong ngân sách server. Không đặt một gate chỉ quanh một repository rồi kết luận toàn ứng dụng đã được bảo vệ.

### 5.3. Phối hợp gate và backoff

Đường đi của một phép đọc có retry nên là:

~~~text
for attempt in [1 .. maxAttempts]:
    if requestDeadlineExceeded: stop
    try:
        return gate.executeOnce(ldapRead)
    catch LdapCapacityRejectedException:
        stop or use an explicitly bounded queue (do not network-retry)
    catch otherError:
        if not transientNetworkError(otherError) or not safeRead: fail
        if no time for another attempt: fail
        sleep/backoff with jitter (without holding gate slot/context)
fail with the last meaningful LDAP error
~~~

Mỗi lần quay lại đầu vòng lặp phải xin **slot và token mới**. Ví dụ nếu `maxAttempts=3`, một HTTP request có thể tiêu thụ tới ba token, dù cuối cùng chỉ trả một response.

Một deadline tại ứng dụng chỉ chặn việc **bắt đầu thêm** attempt; nó không chắc chắn ngắt JNDI I/O đang chặn. Bởi vậy phải phối hợp timeout kết nối, timeout đọc, thời gian mượn context từ pool và search time limit.

## 6. Cấu hình timeout và connection pool không được bỏ qua

Một số hướng dẫn chỉ giới hạn số LDAP request/s mà quên rằng mỗi kết nối còn tiêu tốn socket, TLS state, thread và tài nguyên LDAP server.

Ví dụ cấu hình `LdapContextSource` dùng JNDI (mỗi giá trị timeout là mili giây):

~~~java
import java.util.Map;

import org.springframework.ldap.core.support.LdapContextSource;

public final class DirectoryContextFactory {
    private DirectoryContextFactory() {}

    public static LdapContextSource create(
            String url,
            String baseDn,
            String bindDn,
            String bindPassword) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(baseDn);
        source.setUserDn(bindDn);
        source.setPassword(bindPassword);

        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "1000",
                "com.sun.jndi.ldap.read.timeout", "1800"));

        source.setPooled(false);
        return source;
    }
}
~~~

Trong Spring, hãy đăng ký `LdapContextSource` thành bean để container gọi lifecycle khởi tạo; đoạn factory minh họa cấu hình thuộc tính, không hướng dẫn gọi trực tiếp một object chưa được khởi tạo như bean. Với ứng dụng có nhiều `ContextSource`, xác minh instance nào thực sự được `LdapTemplate` sử dụng.

Khi triển khai pool:

| Thành phần | Giới hạn cần kiểm tra | Lỗi nếu bỏ qua |
| --- | --- | --- |
| JNDI connect timeout | Thời gian tạo socket mới | Một lần kết nối có thể giữ thread quá lâu |
| JNDI read timeout | Thời gian chờ phản hồi socket | Request treo khi server không phản hồi |
| Pool max size | Số LDAP context/connection cho một JVM | Nhiều replica mở quá nhiều connection tới server |
| Pool borrow wait | Thời gian đợi khi hết connection | Hàng đợi ngầm trong pool gây latency khó đoán |
| Idle eviction / validation | Loại bỏ kết nối cũ/hỏng | Lỗi dồn vào request đầu tiên sau thời gian nhàn rỗi |
| Search size/time limit | Khối lượng của từng truy vấn | Một truy vấn rộng tiêu thụ phần lớn ngân sách |

`LdapContextSource.setPooled(true)` kích hoạt cơ chế pooling JNDI của provider, khác với các wrapper như `PoolingContextSource` có chính sách mượn/trả và validation riêng. Cấu hình capacity và cách kiểm tra connection phải tương ứng với loại pool đang dùng. Với StartTLS, cần đặc biệt kiểm chứng việc tái sử dụng connection không làm sai ngữ nghĩa TLS/bind; đừng mặc định mọi cấu hình pool đều an toàn cho StartTLS.

Một giới hạn concurrency ở client không bảo đảm LDAP server có thể xử lý từng operation nhanh: search thiếu index, follow referral hoặc trả hàng nghìn entry vẫn có thể tiêu thụ tài nguyên lâu. Tối ưu query là bước giảm tải đầu tiên.

### 6.1. Chọn giới hạn dựa trên tải đo được

Giả sử tổng mức thao tác mong muốn của toàn cụm là `B` operation/s và có `N` instance ngang nhau. Phân bổ ban đầu có thể là:

\[
r_{\mathrm{per-instance}} \leq \frac{B}{N}.
\]

Nếu có background jobs, ứng dụng khác hoặc failover sang cùng directory, phải dành phần ngân sách cho chúng. Khi các instance không ngang nhau hoặc autoscale liên tục, có thể chọn **global rate limiter** được quản lý tập trung, hoặc cấp token theo tỷ lệ tải với giới hạn tổng. Bộ đếm ở Redis hay dịch vụ điều phối có thể phù hợp, nhưng độ sẵn sàng, thời gian đồng bộ và chế độ fail-open/fail-closed của bộ giới hạn phải được quyết định tường minh.

**Không tự khẳng định LDAP chịu được B operation/s** khi chưa có baseline và kiểm tra từ quản trị viên directory. Dưới tải lớn, server có thể chịu nhiều phép lookup nhỏ nhưng rất ít phép search phức tạp; khi cần, dùng hạn mức riêng theo nhóm operation.

## 7. Giảm số request trước khi phải từ chối tải

Rate limit và load shedding là hàng rào cuối. Hiệu quả hơn là giảm số LDAP operation phát sinh từ đầu:

1. **Search đúng DN và filter:** dùng `EqualsFilter` và thuộc tính đã được index. Giới hạn subtree, số kết quả, time limit, danh sách thuộc tính trả về.
2. **Batch hợp lý:** khi có thể, lấy các thuộc tính cần thiết bằng một lookup thay vì gọi lại nhiều lần cho cùng DN. Không xây batch quét toàn directory.
3. **Cache dữ liệu đọc ít thay đổi:** ví dụ các thuộc tính hiển thị không nhạy cảm, TTL ngắn và kích thước cache có giới hạn; quản lý invalidation khi dữ liệu thay đổi.
4. **Chống cache stampede:** gộp các request đồng thời đang tìm cùng khóa thành một phép lấy dữ liệu có giới hạn thay vì cùng cache miss rồi gọi LDAP hàng loạt.
5. **Giảm các thao tác thừa:** không lặp search nhóm nếu thông tin đã có trong context được xác thực và còn hiệu lực theo policy.
6. **Giới hạn job đồng bộ hóa:** chạy theo trang, tạm dừng giữa các batch và ưu tiên traffic đăng nhập theo khả năng server.

**Cảnh báo bảo mật:** không tự cache mật khẩu, kết quả xác thực hoặc membership/quyền lâu hơn thời gian chính sách cho phép. ACL có thể được thu hồi ngay lập tức ở LDAP trong khi cache của ứng dụng vẫn giữ quyền cũ. Một “negative cache” cho người dùng không tồn tại cũng phải có TTL rất ngắn và cơ chế xử lý dữ liệu vừa được tạo; không trả “không tìm thấy” khi thực chất LDAP đang bị từ chối tải hoặc timeout.

### 7.1. Ưu tiên tải theo tính chất nghiệp vụ

| Nhóm truy cập | Chính sách gợi ý | Lý do |
| --- | --- | --- |
| Bind/xác thực trên đường đăng nhập | Ngân sách latency và quota riêng; timeout rõ ràng | Cần phản hồi nhanh, nhưng không phá khả năng phục vụ LDAP |
| Search người dùng ngắn | Hạn mức rate/concurrency, cache hợp lệ nếu có thể | Lưu lượng lớn, chi phí thấp nếu query tốt |
| Đồng bộ danh bạ nền | Giới hạn batch, page size, pause và khả năng tạm dừng | Có thể dịch thời điểm thực hiện để nhường tài nguyên |
| Báo cáo/quét nhóm lớn | Chạy ngoài peak, có giới hạn tổng thời gian và số entry | Dễ tiêu tốn CPU/index/memory |
| Modify/delete | Hạn mức và cơ chế xác minh kết quả riêng | Không retry vô điều kiện khi response bị mất |

Nếu hệ thống phân luồng ưu tiên, bảo đảm vẫn có giới hạn cho traffic ưu tiên cao: không cho phép một loại operation vượt toàn bộ khả năng của LDAP server trong sự cố.

## 8. Tránh hàng đợi vô hạn và xử lý quá tải đúng cách

Khi gate từ chối một request, ứng dụng cần hành vi rõ ràng theo hợp đồng API, chẳng hạn:

- Với API chỉ phục vụ được khi LDAP sẵn sàng, trả một lỗi phụ thuộc dịch vụ (ví dụ HTTP 503 cho lỗi quá tải tạm thời) hoặc trạng thái thích hợp theo chuẩn API, có correlation ID.
- Với nghiệp vụ có thể trì hoãn, đưa vào hàng đợi **có giới hạn**, ghi nhận trạng thái và thực hiện sau trong ngân sách phù hợp.
- Với trường hợp có dữ liệu cache được phép sử dụng, trả dữ liệu cache có thời hạn và thể hiện tính stale khi cần; tránh dùng thông tin quyền cũ để cho phép truy cập mới.

Tách rõ **local capacity rejection** (hết quota/bulkhead) với **LDAP network failure** (đã gửi attempt, gặp lỗi). Local rejection không nên được giả lập như LDAP “không tìm thấy entry”; làm vậy khiến người dùng bị từ chối đăng nhập sai nguyên nhân hoặc hệ thống bỏ sót sự cố.

Một hàng đợi vô hạn là hình thức giấu quá tải vào bộ nhớ. Nếu tốc độ tới `\lambda` cao hơn tốc độ xử lý `\mu` trong thời gian dài, hàng đợi tăng xấp xỉ theo `(\lambda-\mu)t`. Khi đã đạt kích thước hoặc thời gian chờ tối đa, cần load shed sớm để bảo vệ dịch vụ.

## 9. Quan sát hệ thống: xác định giới hạn có hoạt động hay không

Đo cả phía ứng dụng và directory server. Số metric đề xuất:

| Metric | Diễn giải |
| --- | --- |
| `ldap_attempts_total` theo operation, outcome và loại lỗi | Tổng phép gọi thực, gồm retry |
| `ldap_request_total` theo nghiệp vụ | So sánh số request với số LDAP attempts |
| `ldap_retry_total`, `ldap_retry_exhausted_total` | Mức khuếch đại tải do retry và số lỗi không khôi phục |
| `ldap_rate_rejected_total` | Lượng attempt bị từ chối do hết rate token |
| `ldap_concurrency_rejected_total` | Lượng attempt bị từ chối do hết slot |
| `ldap_inflight` | Số operation đang chạy trong gate |
| `ldap_attempt_duration_seconds` | Latency mỗi LDAP attempt, xem p50/p95/p99 |
| `ldap_service_duration_seconds` | Latency end-to-end của logic có retry |
| `ldap_pool_active`, `ldap_pool_idle`, `ldap_pool_wait` | Mức sử dụng pool và thời gian chờ kết nối |
| LDAP server CPU, connection count, search rate, bind failures | Xem liệu app có chuyển gánh nặng sang server hay không |

Ví dụ dashboard có thể hiển thị đồng thời `rate of LDAP attempts`, `rate of capacity rejections`, `LDAP p95 latency`, `pool active/max` và `server CPU`. Khi tăng giới hạn, chỉ nâng nếu latency, lỗi, tài nguyên và SLO đều có bằng chứng cho thấy còn dư địa.

Cảnh báo không nên chỉ dựa trên một request thất bại. Theo dõi tỉ lệ lỗi/retry/rejection duy trì trong một khoảng thời gian, đồng thời phân biệt việc từ chối tải hợp lệ với hệ thống LDAP thực sự bị lỗi.

**Bảo vệ dữ liệu trong log:** không đặt mật khẩu, full DN người dùng, filter chứa dữ liệu cá nhân hoặc thuộc tính nhạy cảm vào tag metric. Sử dụng các tag cardinality thấp như `operation=search`, `error=network_transient`, `backend=primary`, và giữ log điều tra theo chính sách bảo mật.

## 10. Thực hành: kiểm tra giới hạn tải và backoff trong lab

**Bối cảnh:** một Spring Boot service tra cứu thông tin tài khoản bằng Spring LDAP. Ứng dụng có bốn replica và LDAP test server được cấu hình TLS hợp lệ; mỗi replica có gate ban đầu giới hạn 8 in-flight và 30 attempts/s.

**Chuẩn bị:** dùng dữ liệu giả, tài khoản bind chỉ đọc, entry/test OU đã tạo trước, bộ tạo tải có kiểm soát và công cụ quan sát phía LDAP. Không thử gây quá tải hoặc cắt kết nối trên thư mục production.

### 10.1. Các phép thử

| Ca | Điều kiện thử nghiệm | Dấu hiệu đạt |
| --- | --- | --- |
| L1 | Tải thấp, LDAP bình thường | Không bị từ chối; latency và số attempts ổn định |
| L2 | Một instance phát hơn quota rate | `ldap_rate_rejected_total` tăng; LDAP attempts không vượt ngân sách dài hạn |
| L3 | Đồng thời vượt số slot | `ldap_concurrency_rejected_total` tăng; in-flight không vượt hạn mức |
| L4 | Nhiều instance burst cùng lúc | Có thể burst ngắn trong ngưỡng; không hình thành hàng đợi vô hạn |
| L5 | LDAP test chậm phản hồi | In-flight được chặn; timeout và load shedding hoạt động |
| L6 | Một LDAP read lỗi mạng rồi hồi phục | Retry xảy ra sau backoff có jitter và xin token/slot mới |
| L7 | LDAP trả lỗi credential/ACL/TLS | Dừng ngay; không retry mạng |
| L8 | LDAP luôn unavailable | Số attempts hữu hạn; circuit breaker hoặc hạn mức giúp ngăn retry storm |
| L9 | Tăng số replica từ 4 lên 8 | Nhìn thấy tổng quota cũng tăng; điều chỉnh ngân sách cụm |
| L10 | Job đồng bộ nền chạy cùng login traffic | Job có giới hạn riêng và không chiếm hết năng lực của login |
| L11 | Pool trả về kết nối stale sau idle | Kết nối lỗi bị loại bỏ, không giữ slot và kết nối hỏng vô hạn |
| L12 | Cache miss hàng loạt cùng một khóa | Chống stampede giảm số phép tra cứu trùng |

Cần ghi lại số **attempt thực tế** tại client/server, không chỉ số HTTP request. Kiểm tra lần fail/success của từng loại và thời gian chờ; khi có lỗi kết nối, xác minh code không ngủ backoff trong khi vẫn giữ semaphore permit.

### 10.2. Tính ngân sách toàn cụm

Giả sử LDAP test server được đo an toàn ở một mốc `B=240` operation/s cho **loại truy vấn ngắn** đang thử, và đã dành `40` operation/s cho hệ thống khác. Ngân sách còn lại của ứng dụng là `200` operation/s.

Với bốn replica tải ngang nhau, phân bổ danh nghĩa:

\[
r_{\mathrm{replica}}\leq \frac{200}{4}
=50\ \text{operation/s}.
\]

Nếu cần thêm headroom cho burst và retry, chọn mức thực tế thấp hơn giá trị danh nghĩa dựa trên load test và SLA. Khi tự động scale lên 8 replica, nếu vẫn dùng `50` operation/s mỗi replica thì tổng danh nghĩa tăng tới `400` operation/s, vượt ngân sách giả định. Một lựa chọn là giảm quota theo số replica hoặc dùng điều phối quota toàn cụm.

Làm bài tập tương tự cho **concurrency**: biết LDAP operation latency trung bình là 120 ms, nếu app gửi 180 operation/s thì ước lượng in-flight trung bình `L ≈ 21,6`. Nếu latency tăng lên 450 ms, ước lượng tăng lên `81`. Hãy xem các bulkhead hiện tại có cho phép vượt năng lực server hay không và cách load shedding phản ứng.

### 10.3. Thảo luận sau khi thử

1. Với `retry maxAttempts=3`, một yêu cầu đọc có thể tiêu thụ tối đa bao nhiêu rate token?
2. Nếu rate limiter từ chối ngay tại ứng dụng, có nên retry lỗi đó như lỗi mạng không? Vì sao?
3. Nếu read timeout được đặt 2 giây và HTTP deadline chỉ 1 giây, việc backoff có thể giúp đáp ứng SLO không?
4. Lý do nào khiến một `search` theo filter thiếu index cần quota riêng so với `lookup` một DN?
5. Khi LDAP server vừa phục hồi sau sự cố, vì sao jitter và giới hạn concurrency quan trọng ngay cả khi retry đã được giới hạn số lần?

**Tiêu chí hoàn thành:** gate giới hạn được attempt rate/in-flight trong từng JVM; truy vấn giới hạn DN/filter/scope/attributes; backoff có jitter và không giữ slot; các lỗi cấu hình/auth/ACL/TLS không retry; khi tăng replica, ngân sách toàn cụm được tính lại; dashboard phản ánh attempts, rejections, latency và tải server.

## 11. Checklist trước khi triển khai

- [ ] Ước lượng request/s, LDAP operations/request và retry amplification trên **toàn cụm**.
- [ ] Có baseline năng lực directory theo loại operation, tải nền và SLO thực tế.
- [ ] Mỗi LDAP attempt, kể cả retry và background job, chịu một chính sách giới hạn tải thích hợp.
- [ ] Có giới hạn **rate**, **concurrency** và hàng đợi hữu hạn; xác định cách xử lý khi bị từ chối.
- [ ] Backoff có jitter, số attempts tối đa, deadline và ngăn retry storm.
- [ ] Chỉ retry lỗi mạng tạm thời cho thao tác an toàn; không tự lặp thao tác ghi mơ hồ.
- [ ] Cấu hình connect/read timeout, giới hạn search, pool borrow/max size, validation và eviction.
- [ ] Truy vấn có base DN, filter an toàn, thuộc tính trả về và size/time limit phù hợp.
- [ ] Không cache thông tin xác thực/quyền quá mức chính sách cho phép; có cơ chế invalidation phù hợp.
- [ ] Hạn mức theo instance được điều chỉnh khi autoscale; không vô tình nhân tải directory.
- [ ] Monitoring gồm retries, rate/concurrency rejection, p95/p99, pool và LDAP server resources.
- [ ] Đã diễn tập burst, outage, recovery và cạnh tranh với background jobs trong test environment.
- [ ] Không ghi secret, filter/DN nhạy cảm hay thông tin cá nhân thành metric labels.

**Nguyên tắc vận hành:** backoff giúp giảm nhịp *thử lại*, còn rate limiter, bulkhead và load shedding mới giới hạn tải mà ứng dụng gửi tới directory server. Khi phối hợp với truy vấn hiệu quả, timeout hữu hạn, cache đúng chính sách và chỉ số đo lường, Spring LDAP có thể phục vụ ổn định hơn trước burst, suy giảm mạng và các đợt phục hồi sau sự cố.
