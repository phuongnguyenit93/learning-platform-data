# Retry có điều kiện với lỗi mạng tạm thời trong Spring LDAP

## 1. Mục tiêu và bối cảnh vận hành

Một ứng dụng Spring LDAP có thể đang dùng `ContextSource`, `LdapTemplate`, `LdapClient` hoặc ODM để đọc người dùng, kiểm tra nhóm và thay đổi entry trong dịch vụ thư mục. Khi một kết nối TCP bị đóng, LDAP server tạm quá tải hoặc một lần đọc phản hồi hết thời gian chờ, thao tác có thể thất bại dù truy vấn và thông tin xác thực hoàn toàn hợp lệ.

**Retry** là thực hiện lại thao tác sau một lỗi được phân loại là có khả năng hồi phục. Retry hợp lý giúp chịu đựng những gián đoạn ngắn, nhưng retry sai có thể làm tăng tải lên LDAP server, kéo dài latency, lặp thao tác ghi hoặc che giấu sự cố cấu hình.

Bài học thuộc chương **Vận hành** của module **SPRING_LDAP** hướng tới bốn khả năng:

1. Phân biệt lỗi mạng tạm thời với lỗi xác thực, phân quyền, schema và dữ liệu.
2. Chỉ áp dụng retry có điều kiện cho những thao tác đủ an toàn, trước hết là **tìm kiếm/đọc**.
3. Khống chế số lần thử, thời gian chờ, backoff, jitter và deadline tổng thể.
4. Đo lường, kiểm thử và quyết định cách phản ứng khi retry không thể khôi phục truy cập LDAP.

Các ví dụ dùng Spring Boot 3.x, Java 17+, Spring LDAP qua JNDI và một thư mục thử nghiệm với base DN `dc=example,dc=org`. Cấu hình và loại exception cần được đối chiếu với LDAP server, JDK và phiên bản Spring LDAP đang triển khai.

## 2. Khi nào cần retry và khi nào phải dừng ngay?

Không phải mọi exception của `LdapTemplate` đều có nghĩa mạng đang chập chờn. Việc phân loại nên dựa trên **bản chất lỗi, loại thao tác và hợp đồng nghiệp vụ**.

| Nhóm lỗi | Ví dụ tín hiệu | Retry tự động? | Lý do |
| --- | --- | --- | --- |
| Kết nối mạng gián đoạn | TCP reset, `ConnectException`, `javax.naming.CommunicationException` | **Có điều kiện** với phép đọc | Server có thể hoạt động lại ở lần thử tiếp theo |
| Chờ phản hồi quá lâu | `SocketTimeoutException` hoặc `CommunicationException` có nguyên nhân timeout | **Có điều kiện** với phép đọc | Có thể do tải tạm thời; phải xét deadline |
| Server tạm không sẵn sàng | LDAP result code **52** (`unavailable`), `javax.naming.ServiceUnavailableException` | **Có điều kiện** | Có thể do chuyển phiên, restart hoặc quá tải |
| Server bận | LDAP result code **51** (`busy`) khi client/server thể hiện rõ | **Cân nhắc theo chính sách** | Backoff giúp giảm áp lực; không retry dồn dập |
| Sai tài khoản/mật khẩu | LDAP result code **49** (`invalidCredentials`) | **Không** | Retry không sửa được credential và có thể khóa tài khoản |
| Thiếu quyền ACL | LDAP result code **50** (`insufficientAccessRights`) | **Không** | Phải điều chỉnh phân quyền, không tăng số lần gọi |
| Entry không tồn tại | LDAP result code **32** (`noSuchObject`) | **Không mặc định** | Thường là dữ liệu/DN không đúng; không tự coi là lỗi mạng |
| Sai DN/filter/schema | `InvalidNameException`, `SchemaViolationException` | **Không** | Sửa truy vấn hoặc cấu trúc dữ liệu |
| Vi phạm time/size limit | `TimeLimitExceededException`, `SizeLimitExceededException` | **Không mặc định** | Có thể là search quá rộng hoặc giới hạn server |
| Lỗi chứng chỉ TLS | `SSLHandshakeException`, certificate/hostname mismatch | **Không** | Sửa truststore/certificate; thử lại không làm TLS hợp lệ |
| Vi phạm điều kiện nghiệp vụ | Entry trùng, version conflict, thao tác bị từ chối | **Không mặc định** | Cần phân tích dữ liệu và quy tắc cập nhật |

**Hai lưu ý quan trọng:**

- Trong Spring LDAP, exception JNDI thường được dịch sang exception tương ứng của Spring. Tín hiệu nguyên gốc có thể nằm trong chuỗi `getCause()`; không nên retry mọi `RuntimeException` hay mọi `NamingException`.
- LDAP server có thể trả mã 51/52 qua exception hoặc kết quả tùy provider. Không nên suy luận khả năng retry bằng cách phân tích chuỗi thông báo lỗi. Nếu cần nhận diện `busy` riêng, phải triển khai bộ phân loại tin cậy dựa trên exception/result code thực tế đã kiểm chứng.

### 2.1. Retry là quyết định ở từng thao tác

Cùng một lỗi mạng có thể dẫn tới cách xử lý khác nhau:

| Thao tác | Khi mất phản hồi sau khi gửi request | Mặc định |
| --- | --- | --- |
| Search/read bằng filter xác định | Gửi lại truy vấn thường không sửa dữ liệu | Có thể retry trong ngân sách |
| Bind để tạo kết nối mới | Có thể thử lại khi lỗi mạng rõ ràng; không retry credential sai | Có điều kiện |
| Add entry | Server có thể đã thêm entry nhưng client không nhận được response | Không tự động retry |
| Modify thuộc tính | Server có thể đã sửa; lần thứ hai có thể có tác động ngoài ý muốn | Không tự động retry |
| Delete entry | Server có thể đã xóa, nhưng client tưởng là chưa | Không tự động retry |
| Rename/move DN (`modDN`) | DN đích có thể đã thay đổi | Không tự động retry |

Ngay cả thao tác đọc cũng phải cẩn thận nếu callback/mapper ghi dữ liệu, phát sự kiện hoặc cập nhật trạng thái ngoài LDAP. **Một phép đọc chỉ an toàn để retry khi toàn bộ logic được bọc trong retry là không gây tác dụng phụ ngoài ý muốn.**

## 3. Thiết kế chính sách retry: hữu hạn và có giới hạn tải

Một retry policy cho phép đọc thông thường nên có:

- **Bộ phân loại:** chỉ chấp nhận lỗi mạng hoặc server tạm unavailable đã xác minh.
- **Số lần thử tối đa:** ví dụ 3 lần **bao gồm lần đầu**, nghĩa là chỉ có tối đa 2 lần retry.
- **Exponential backoff:** tăng thời gian nghỉ giữa các lần thử để server có cơ hội hồi phục.
- **Jitter:** thêm dao động ngẫu nhiên để nhiều instance không retry cùng một thời điểm.
- **Deadline:** không khởi động lượt thử mới khi ngân sách thời gian còn lại không đủ.
- **Timeout mỗi lượt:** tránh một lần connect/read chặn thread quá lâu.
- **Giới hạn đồng thời:** dùng pool/bulkhead phù hợp để các lần retry không chiếm hết tài nguyên.

Với thời gian cơ sở `b` và giới hạn `d_max`, có thể chọn:

\[
d_k=\min(d_{\max}, b\cdot 2^{k-1}) + U(0,j)
\]

Trong đó `k` là lần retry thứ `k`, `U(0,j)` là khoảng jitter ngẫu nhiên. Ví dụ `b=120 ms`, `d_max=400 ms`, `j=70 ms` tạo khoảng nghỉ xấp xỉ 120–190 ms ở retry thứ nhất và 240–310 ms ở retry thứ hai.

~~~mermaid
flowchart TD
    A["Thực hiện LDAP read"] --> B{"Thành công?"}
    B -->|Có| C["Trả kết quả"]
    B -->|Không| D{"Lỗi thuộc nhóm được retry?"}
    D -->|Không| E["Trả nguyên lỗi cho tầng gọi"]
    D -->|Có| F{"Còn attempt và deadline?"}
    F -->|Không| E
    F -->|Có| G["Backoff có jitter"]
    G --> H{"Còn thời gian và chưa bị interrupt?"}
    H -->|Không| E
    H -->|Có| A
~~~

**Không đồng nhất các timeout:** JNDI `connect.timeout` giới hạn cố gắng kết nối TCP; `read.timeout` giới hạn thời gian chờ phản hồi trên socket; một search có thể phát nhiều response. Chúng **không tạo ra deadline tuyệt đối** cho toàn bộ request HTTP, nhất là khi có pool, nhiều LDAP call hoặc referral. Deadline trong lớp retry chỉ giúp **quyết định có bắt đầu lần thử tiếp theo hay không**; nếu I/O bên dưới đang chặn, cần timeout ở JNDI/pool/search để sớm giải phóng thread.

### 3.1. Tránh hiện tượng “retry storm”

Giả sử một dịch vụ nhận 200 request/giây, mỗi request gọi LDAP một lần. Khi LDAP gặp sự cố, chính sách thử tối đa 3 lượt có thể gây gần **600 yêu cầu LDAP/giây**, chưa kể retry tại gateway, proxy hoặc SDK khác.

Để giới hạn tác động:

1. Quy định **một tầng chịu trách nhiệm retry** cho mỗi loại operation; tránh retry lồng nhau ở repository, service và gateway.
2. Sử dụng backoff, jitter và giới hạn đồng thời; không retry ngay lập tức trên mọi instance.
3. Dừng retry khi circuit breaker mở, khi quá tải rõ ràng hoặc khi ngân sách request đã cạn.
4. Theo dõi tổng số LDAP attempt, không chỉ số request HTTP.
5. Nếu có nhiều endpoint LDAP, chỉ chuyển qua endpoint thay thế đã được cấu hình, cấp quyền và xác minh TLS đúng cách; không tự chọn máy chủ ngoài danh sách tin cậy.

## 4. Cấu hình timeout JNDI cho từng lần thử

Trước khi thêm retry, cần bảo đảm mỗi lượt thử có giới hạn kết nối và đọc hợp lý. Ví dụ Spring LDAP:

~~~yaml
# application.yml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    user-dn: uid=svc-directory-reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
    connect-timeout-ms: 800
    read-timeout-ms: 1200

# Các thông số ví dụ cho chính sách retry đọc:
# tối đa 3 attempts; ngừng bắt đầu lượt mới sau khi hết deadline 3500 ms.
~~~

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryLdapConfig {

    @Bean
    LdapContextSource directoryContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.user-dn}") String userDn,
            @Value("${app.ldap.password}") String password,
            @Value("${app.ldap.connect-timeout-ms}") int connectMs,
            @Value("${app.ldap.read-timeout-ms}") int readMs) {

        if (connectMs <= 0 || readMs <= 0) {
            throw new IllegalArgumentException("LDAP timeout must be positive");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(userDn);
        source.setPassword(password);
        source.setPooled(false);
        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout",
                Integer.toString(connectMs),
                "com.sun.jndi.ldap.read.timeout",
                Integer.toString(readMs)));
        return source;
    }

    @Bean
    LdapTemplate directoryLdapTemplate(
            LdapContextSource directoryContextSource) {
        return new LdapTemplate(directoryContextSource);
    }
}
~~~

Các giá trị là **mili giây**. Spring quản lý lifecycle của bean `LdapContextSource` trong ví dụ. `setPooled(false)` làm rõ hành vi thử nghiệm; nếu dự án dùng pooling thực tế, cần có thêm timeout mượn kết nối, kiểm tra kết nối cũ, eviction và giới hạn kích thước pool. Kết nối trong pool đã mở không nhất thiết chịu thay đổi timeout ngay khi cấu hình mới được nạp.

Chứng chỉ LDAPS phải được JVM tin cậy và hostname phải khớp; không tắt certificate validation để chữa lỗi bị coi là timeout. Nếu môi trường dùng StartTLS, bắt buộc nâng cấp TLS trước khi bind bằng mật khẩu; việc xử lý TLS và pooling cần được thiết kế tương ứng.

## 5. Ví dụ Java: chỉ retry khi lỗi mạng có thể hồi phục

Ví dụ bên dưới cố ý dùng **một lớp thực thi retry nhỏ, tường minh**, không cần Spring Retry. Cách này cho phép thấy rõ điều kiện nào khiến code thử lại. Đối với dự án đã có `RetryTemplate` hoặc `@Retryable`, vẫn phải áp dụng cùng chính sách phân loại, giới hạn và xử lý riêng cho thao tác ghi.

### 5.1. Bộ phân loại lỗi theo chuỗi nguyên nhân

JNDI LDAP provider có thể ném `javax.naming.CommunicationException` hoặc `ServiceUnavailableException`. Spring LDAP thường bọc/chuyển đổi chúng thành runtime exception và giữ nguyên nhân trong `getCause()`. Bộ phân loại sau chỉ retry tín hiệu network được liệt kê; một lỗi không rõ bản chất sẽ **fail fast**.

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import javax.naming.AuthenticationException;
import javax.naming.CommunicationException;
import javax.naming.InvalidNameException;
import javax.naming.NameNotFoundException;
import javax.naming.NoPermissionException;
import javax.naming.SchemaViolationException;
import javax.naming.ServiceUnavailableException;
import javax.naming.SizeLimitExceededException;
import javax.naming.TimeLimitExceededException;
import javax.net.ssl.SSLHandshakeException;

public final class LdapFailureClassifier {

    private LdapFailureClassifier() {}

    public static boolean mayRetryRead(Throwable failure) {
        boolean transientSignal = false;

        // Xem toàn bộ cause chain trước khi quyết định:
        // một lỗi TLS / auth bị bọc trong communication error vẫn phải fail fast.
        for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            if (cause instanceof AuthenticationException
                    || cause instanceof NoPermissionException
                    || cause instanceof InvalidNameException
                    || cause instanceof NameNotFoundException
                    || cause instanceof SchemaViolationException
                    || cause instanceof SizeLimitExceededException
                    || cause instanceof TimeLimitExceededException
                    || cause instanceof SSLHandshakeException
                    || cause instanceof UnknownHostException) {
                return false;
            }

            if (cause instanceof CommunicationException
                    || cause instanceof ServiceUnavailableException
                    || cause instanceof ConnectException
                    || cause instanceof SocketTimeoutException) {
                transientSignal = true;
            }
        }

        return transientSignal;
    }
}
~~~

**Giới hạn của classifier minh họa:** lớp này dựa vào việc provider giữ nguyên nhân qua `getCause()`; nếu thư viện/vendor không bảo toàn nguyên nhân hoặc trả LDAP result code theo cơ chế riêng, cần bổ sung mapper xác định theo API thực tế. Nó không tự nhận diện mọi biến thể `busy` (mã 51) và không nên thay thế bằng tìm chuỗi `"timeout"` trong thông báo exception. DNS `UnknownHostException` được coi là lỗi cần điều tra, dù trên thực tế một vài sự cố DNS có thể ngắn hạn; đây là lựa chọn bảo thủ để tránh retry cấu hình host sai.

Không biến `AuthenticationException` thành “lỗi mạng tạm thời”: credential sai có thể dẫn đến account lockout nếu tự động thử nhiều lần. Không retry `TimeLimitExceededException` của một truy vấn quá nặng mà chưa phân tích filter, index và giới hạn search.

### 5.2. Retry bounded với backoff và jitter

~~~java
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import org.springframework.stereotype.Component;

@Component
public class LdapReadRetry {

    private static final int MAX_ATTEMPTS = 3; // bao gồm lần đầu
    private static final long TOTAL_BUDGET_MS = 3500L;
    private static final long MIN_NEXT_ATTEMPT_BUDGET_MS = 1200L;

    public <T> T execute(Supplier<T> readOperation) {
        long started = System.nanoTime();
        RuntimeException lastFailure = null;

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            if (attempt > 1
                    && remainingMs(started) < MIN_NEXT_ATTEMPT_BUDGET_MS) {
                throw lastFailure;
            }

            try {
                return readOperation.get();
            } catch (RuntimeException failure) {
                lastFailure = failure;

                if (!LdapFailureClassifier.mayRetryRead(failure)
                        || attempt == MAX_ATTEMPTS) {
                    throw failure;
                }

                long backoffMs = Math.min(
                        400L, 120L * (1L << (attempt - 1)));
                long jitterMs = ThreadLocalRandom.current()
                        .nextLong(0L, 71L);
                long delayMs = backoffMs + jitterMs;

                // Không khởi động lần mới nếu thời gian còn lại quá ít.
                if (remainingMs(started)
                        <= delayMs + MIN_NEXT_ATTEMPT_BUDGET_MS) {
                    throw failure;
                }

                try {
                    Thread.sleep(delayMs);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Interrupted during LDAP retry", interrupted);
                }
            }
        }

        throw new IllegalStateException("Unreachable retry state");
    }

    private static long remainingMs(long started) {
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
        return TOTAL_BUDGET_MS - elapsedMs;
    }
}
~~~

**Ý nghĩa của mã:**

- `MAX_ATTEMPTS = 3` nghĩa là một lượt gốc cộng tối đa hai lượt retry.
- Mỗi retry có backoff tăng dần và jitter nhằm giảm khả năng các instance đồng loạt gọi LDAP lại.
- `remainingMs` tính bằng `System.nanoTime()` để đo elapsed time; không phụ thuộc việc đồng hồ hệ thống được chỉnh.
- `MIN_NEXT_ATTEMPT_BUDGET_MS` là ngưỡng quyết định **không bắt đầu thêm một lượt**. Đây không phải một cơ chế cắt đứt lời gọi JNDI đang chạy khi hết 3.500 ms.
- Nếu thread bị ngắt khi đợi backoff, giữ lại interrupt flag và dừng ngay.
- Nếu đã hết lượt hoặc lỗi không hợp lệ để retry, ném lại chính exception gốc của lần thất bại cuối, không biến lỗi truy cập thư mục thành `Optional.empty()` hay danh sách rỗng.

`Thread.sleep` chặn thread trong ví dụ đồng bộ. Ở tải lớn, nên xét đến executor có giới hạn, backoff bất đồng bộ hoặc cơ chế resilience được dự án sử dụng, nhưng vẫn phải giữ giới hạn số lượt và tổng tải. Không tạo vô hạn thread hoặc task chỉ để retry.

### 5.3. Bọc duy nhất thao tác đọc LDAP

Ví dụ tra cứu tên hiển thị theo `uid`. Scope được giới hạn ở các entry con trực tiếp dưới `ou=people`, filter do `EqualsFilter` tạo ra để mã hóa dữ liệu đầu vào, và chỉ yêu cầu thuộc tính `cn`.

~~~java
import java.util.List;
import java.util.Optional;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class DirectoryReader {

    private final LdapTemplate ldap;
    private final LdapReadRetry retry;

    public DirectoryReader(
            @Qualifier("directoryLdapTemplate") LdapTemplate ldap,
            LdapReadRetry retry) {
        this.ldap = ldap;
        this.retry = retry;
    }

    public Optional<String> findDisplayName(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }
        return retry.execute(() -> lookupOnce(uid));
    }

    private Optional<String> lookupOnce(String uid) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"cn"});
        controls.setCountLimit(2);
        controls.setTimeLimit(900); // giới hạn cho một search (ms)

        String filter = new EqualsFilter("uid", uid).encode();

        List<String> names = ldap.search(
                "ou=people", filter, controls,
                (AttributesMapper<String>) attrs -> {
                    Attribute cn = attrs.get("cn");
                    if (cn == null) {
                        throw new IllegalStateException(
                                "cn attribute unavailable");
                    }
                    return String.valueOf(cn.get());
                });

        if (names.size() > 1) {
            throw new IllegalStateException("uid is not unique");
        }
        return names.stream().findFirst();
    }
}
~~~

Kết quả trống khi `uid` không tồn tại là **kết quả nghiệp vụ hợp lệ**, không phải lý do để retry. Exception do schema/thuộc tính thiếu hoặc entry trùng được giữ nguyên và classifier từ chối retry. Một mapper chỉ nên đọc dữ liệu và tạo kết quả; không gửi email, ghi audit bên ngoài hoặc thay đổi DB trong `lookupOnce` vì có thể chạy lại nhiều lần.

Ba lớp giới hạn trong ví dụ là:

1. `SearchControls.setTimeLimit(900)` cho search ở mức JNDI/provider.
2. `read.timeout = 1200 ms` và `connect.timeout = 800 ms` cho kết nối/phản hồi LDAP.
3. `TOTAL_BUDGET_MS = 3500` để **không khởi động** retry mới khi đã gần cạn ngân sách.

Không thể suy ra phép gọi này chắc chắn kết thúc dưới 3.500 ms: kết nối mới, TLS, bind và các phản hồi trung gian có thể cộng dồn thời gian. Nếu SLO yêu cầu deadline cứng, cần kiến trúc hủy I/O có hỗ trợ, giới hạn ở tầng network/gateway và đo latency end-to-end; `Future.get(timeout)` chỉ ngừng chờ của caller chứ không chắc dừng I/O LDAP đang thực hiện.

## 6. Xử lý an toàn thao tác ghi khi kết quả không chắc chắn

Một lỗi mạng sau khi client gửi `modify` **không chứng minh modify thất bại**. LDAP server có thể đã commit thay đổi rồi connection bị ngắt trước khi phản hồi tới client.

~~~mermaid
sequenceDiagram
    participant App as Spring LDAP client
    participant Server as LDAP server
    App->>Server: Modify DN (thay đổi thuộc tính)
    Server->>Server: Thực thi và lưu thay đổi
    Server--xApp: Response bị mất do đứt mạng
    Note over App: Client thấy timeout, trạng thái server chưa rõ
    App->>Server: Không tự động gửi lại modify
    App->>Server: Tra cứu/xác minh kết quả trên nguồn có thẩm quyền
~~~

Ví dụ, thực hiện `increment` một thuộc tính số hoặc thay đổi membership thông qua thao tác không idempotent có thể tạo dữ liệu sai nếu lặp. Ngay cả `replace` cùng một giá trị trông có vẻ idempotent, các plugin/audit hooks hoặc phiên bản entry có thể khiến thử lại mang tác dụng phụ.

Nếu có yêu cầu retry thao tác ghi, thiết kế cần nêu rõ:

- **Tính idempotent:** cùng một yêu cầu gửi nhiều lần phải tạo ra trạng thái hợp lệ như một lần, bao gồm tác dụng phụ.
- **Kiểm soát đồng thời:** dùng assertion control/compare-and-set theo khả năng LDAP server và schema, hoặc phiên bản/entry state phù hợp, để tránh ghi đè thay đổi từ tác nhân khác.
- **Đối chiếu sau timeout:** đọc trạng thái thực tế bằng danh tính đủ quyền và từ nơi có độ nhất quán phù hợp trước khi quyết định gửi lại.
- **Replication:** với LDAP đa máy chủ, đọc ngay từ replica khác có thể chưa thấy write đã được commit. Không tự nhận kết quả “chưa có” là bằng chứng an toàn để ghi lại.
- **Giới hạn tối đa:** ngay cả thao tác đã bảo đảm idempotent vẫn cần backoff, deadline và giám sát.

Không bọc toàn bộ service method gồm cả LDAP write, cập nhật SQL, gửi event và email trong một chính sách retry chung. Retry phải nằm sát ranh giới tác vụ và theo hợp đồng lỗi của riêng tác vụ đó.

## 7. Phối hợp retry với TLS, pool, failover và giao dịch

### 7.1. Kết nối và xác thực

- **LDAPS/StartTLS** phải xác minh server certificate và hostname. Lỗi `SSLHandshakeException` không nên retry; tăng số lần thử không khắc phục truststore hay chứng chỉ hết hạn.
- Nếu LDAP trả `invalidCredentials`, không retry để tránh làm khóa account; kiểm tra DN bind, secret rotation và trạng thái tài khoản.
- Khi server restart, một connection trong pool có thể trở nên stale. Loại bỏ connection lỗi trước khi thử lại theo cơ chế pool; retry trên cùng connection chết có thể lặp lại cùng một lỗi.
- Retry sang LDAP server khác chỉ khi endpoint đó thuộc danh sách được quản trị, có TLS tin cậy, schema tương thích và chính sách ACL phù hợp.

### 7.2. Pooling và nguồn lực

Một lượt thử có thể cần **mượn** connection từ pool trước khi search. Nếu pool đã cạn, request có thể chờ ở pool mà không tiêu thụ connect timeout JNDI. Cần đặt pool borrow timeout, max size, idle validation và eviction theo thư viện dùng trong dự án.

Không coi `LdapContextSource.setPooled(true)` là cấu hình đầy đủ cho mọi dạng connection pool. Nếu dự án dùng `PoolingContextSource` hoặc thư viện pool bên ngoài, xem policy validation và exception của riêng pool. Một số exception như pool exhaustion có thể cần fail fast hoặc circuit breaker, thay vì lập tức tạo thêm retry.

### 7.3. Referral, phân trang và retry ở nhiều tầng

- Search theo **referral** có thể tạo kết nối LDAP khác; mỗi máy chủ có timeout và ACL riêng. Không follow referral tới máy chủ ngoài phạm vi tin cậy.
- Search **phân trang** gồm nhiều lần request. Khi lỗi giữa chừng, việc lặp cả phiên có thể trả dữ liệu thay đổi hoặc trùng nếu tập entry biến động. Dùng cursor/paged-results control và thiết kế xử lý trùng/mất kết quả phù hợp.
- Nếu gateway và client HTTP cũng retry trong khi service lại retry LDAP, số lượt thực tế có thể là tích số: 2 lượt ở gateway nhân 3 lượt LDAP thành tối đa **6 LDAP attempts** cho một yêu cầu ban đầu.
- Circuit breaker có thể mở khi tỉ lệ lỗi cao để tránh dồn tải, nhưng phải phân biệt lỗi LDAP tạm thời với lỗi cấu hình mãi không khỏi; không gộp tất cả loại lỗi vào cùng một metric mà không phân loại.

## 8. Quan sát kết quả retry và điều tra sự cố

Ghi nhận cả **request cấp nghiệp vụ** và **LDAP attempts thực tế**. Nếu chỉ nhìn phần trăm HTTP request cuối cùng thành công, có thể bỏ lỡ việc LDAP đang suy giảm nhưng retry vẫn che được lỗi.

| Chỉ số/nhật ký | Mục đích |
| --- | --- |
| `ldap_attempts_total` theo read/lookup/search, kết quả và nhóm lỗi | Đo tải thực tế tới LDAP, kể cả retry |
| `ldap_retry_attempts_total` | Biết tỉ lệ request phải thử thêm |
| `ldap_retry_exhausted_total` | Phát hiện lúc retry không đủ để hồi phục |
| `ldap_operation_duration_seconds` | Đo latency của từng LDAP attempt |
| `ldap_request_end_to_end_duration_seconds` | Đo tổng latency của logic có retry |
| `ldap_pool_wait_duration_seconds` (nếu có pool) | Phân biệt nghẽn pool với LDAP server chậm |
| LDAP server logs/result codes | Xác nhận lỗi mạng, authentication, ACL và tình trạng server |

Lấy mẫu metric theo loại thao tác, tên kết nối/cluster đã được chuẩn hóa và nhóm lỗi. **Không đưa mật khẩu, uid thực, filter có dữ liệu cá nhân, DN đầy đủ hay exception message chứa dữ liệu nhạy cảm thành metric label** vì nguy cơ lộ thông tin và tạo cardinality quá cao.

Ví dụ lập bản ghi audit vận hành an toàn:

~~~text
ldap.operation=search
ldap.attempt=2
ldap.maxAttempts=3
ldap.failureCategory=NETWORK_TRANSIENT
ldap.retryDelayMs=247
ldap.terminalOutcome=SUCCESS
ldap.elapsedMs=1230
~~~

Trường dữ liệu là minh họa, không phải kết quả đã đo. Nếu retry thành công ở attempt thứ hai, biểu đồ “availability” có thể vẫn tốt trong khi p95 latency tăng mạnh. Cảnh báo nên xét cả tỉ lệ retry, tỉ lệ exhausted, độ trễ và số request đang chờ.

## 9. Kiểm thử retry có điều kiện

Trước khi áp dụng production, dùng LDAP test server chứa dữ liệu giả, account có quyền đọc tối thiểu, TLS hợp lệ và proxy lỗi mạng trong môi trường thử nghiệm (ví dụ Toxiproxy). Chỉ tạo lỗi trong lab được kiểm soát; không cố làm ngắt mạng hoặc gây quá tải cho thư mục đang phục vụ người dùng thật.

### 9.1. Ma trận ca kiểm thử

| Ca | Cách mô phỏng | Kết quả mong đợi |
| --- | --- | --- |
| R1 | Search thành công ngay | Một attempt, không ngủ backoff |
| R2 | Lỗi connect tạm thời ở attempt 1; attempt 2 thành công | Hai attempts, có backoff và jitter |
| R3 | Lỗi đọc ở hai attempts đầu, sau đó hồi phục | Tối đa ba attempts, trả dữ liệu đúng |
| R4 | Lỗi mạng xảy ra cả ba lần | Dừng sau ba attempts; giữ nguyên exception cuối |
| R5 | Credential sai/mã 49 | Dừng ngay attempt 1, không retry |
| R6 | ACL từ chối/mã 50 | Dừng ngay attempt 1 |
| R7 | Lỗi TLS/certificate | Dừng ngay, không bỏ xác minh chứng chỉ |
| R8 | DN không tồn tại, search hợp lệ trả 0 entry | Trả kết quả rỗng; không retry |
| R9 | Search vượt size/time limit | Dừng theo chính sách mặc định; điều tra search |
| R10 | Deadline còn quá ít cho attempt mới | Không bắt đầu attempt tiếp theo |
| R11 | Thread bị interrupt trong backoff | Giữ interrupt flag và dừng |
| R12 | Modify đã commit nhưng response mất | Không tự động gửi lại write; đối chiếu trạng thái |
| R13 | Cả pool đang cạn connection | Kiểm tra giới hạn borrow và hành vi overload |
| R14 | 100 request đồng thời cùng gặp lỗi mạng | Tổng attempt và load nằm trong ngưỡng cho phép |

Đối với kiểm thử classifier độc lập, có thể tạo exception Java có cause là một trong các JNDI exception trong bảng rồi khẳng định `mayRetryRead` trả đúng boolean. Đối với kiểm thử tích hợp, cần **quan sát số request thực đi qua LDAP/proxy**; mock chỉ gọi lại supplier không chứng minh timeout JNDI, TLS hay xử lý connection pool đúng.

### 9.2. Bài thực hành tính thời gian

Giả sử các lượt đọc khi LDAP chậm đều chờ `read.timeout=1200 ms` trước khi thất bại. Có ba attempts, backoff cơ sở lần lượt 120 ms và 240 ms, chưa tính jitter hay TLS/bind:

\[
3\times1200 + 120 + 240 = 3960\ \text{ms}.
\]

Tổng đã là **3.960 ms**, vượt deadline HTTP 3.500 ms. Việc cài `TOTAL_BUDGET_MS=3500` ở lớp retry minh họa giúp **bỏ qua lượt thử mới nếu không còn đủ thời gian ước tính**, nhưng không thể bảo đảm ngắt attempt đang chờ. Hãy giải thích khi nào dịch vụ nên bỏ attempt thứ ba, giảm read timeout, tối ưu truy vấn hoặc thay đổi API deadline.

**Tiêu chí hoàn thành thực hành:** với tìm kiếm đọc, lỗi mạng đã xác minh được retry có giới hạn; lỗi auth/ACL/TLS không retry; elapsed time và số attempts được đo; dữ liệu trả về không bị nhân đôi; thao tác ghi có kết quả mơ hồ được xử lý qua đối chiếu chứ không gửi lại vô điều kiện.

## 10. Checklist triển khai

- [ ] Xác định rõ thao tác nào là read-only và idempotent; không đưa write vào retry chung.
- [ ] Có classifier cho lỗi mạng/`unavailable`, và danh sách lỗi phải fail fast (auth, ACL, schema, TLS).
- [ ] Số lượt thử bao gồm lần đầu được giới hạn; không có vòng lặp retry vô hạn.
- [ ] Có exponential backoff và jitter; không retry ngay đồng thời trên mọi instance.
- [ ] Configured connect/read timeout JNDI hợp lệ, search time limit hợp lý và ngân sách end-to-end được giám sát.
- [ ] Kiểm tra hành vi của pool, referral, TLS và nhiều LDAP endpoint.
- [ ] Tránh retry lồng nhau giữa gateway, API service, repository và LDAP SDK.
- [ ] Có giới hạn đồng thời/circuit breaker để tránh retry storm khi thư mục suy giảm.
- [ ] Khi hết attempts, lỗi được truyền rõ ràng; không biến lỗi LDAP thành “không tìm thấy người dùng”.
- [ ] Test lỗi mạng, TLS, auth, ACL, deadline và trạng thái ghi không chắc chắn trên môi trường thử nghiệm.
- [ ] Dashboard và alert theo số attempts, exhausted retry, end-to-end latency và tải LDAP.
- [ ] Nhật ký không chứa secret, DN nhạy cảm hoặc thông tin định danh người dùng không cần thiết.

Retry có điều kiện trong **Spring LDAP** phải dựa trên **loại lỗi + tính an toàn của thao tác + ngân sách thời gian còn lại**. Một chính sách nhỏ, rõ ràng, có giới hạn thường đáng tin cậy hơn retry mọi lỗi: nó khôi phục được gián đoạn mạng ngắn mà không tạo thêm rủi ro cho dữ liệu thư mục và hệ thống đang quá tải.
