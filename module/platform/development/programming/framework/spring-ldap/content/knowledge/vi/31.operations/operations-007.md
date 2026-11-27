# Redaction DN, filter và credential trong log của Spring LDAP

## 1. Bối cảnh: một dòng log LDAP có thể tiết lộ điều gì?

Trong ứng dụng **Spring LDAP**, lỗi tra cứu người dùng hay đăng nhập thường xảy ra ở điểm giao nhau giữa HTTP request, service, `ContextSource`, `LdapTemplate` hoặc `LdapClient` và directory server. Để điều tra, lập trình viên có xu hướng ghi thêm DN, LDAP filter, bind credential hoặc toàn bộ exception. Cách này có thể làm rò rỉ thông tin cá nhân, cấu trúc tổ chức và dữ liệu xác thực ngay cả khi API chỉ trả thông báo chung cho người dùng.

Ví dụ trong môi trường giả lập:

~~~text
# Không được dùng kiểu log này trong production.
operation=search
baseDn=ou=people,dc=example,dc=org
filter=(&(objectClass=person)(mail=student42@example.org))
bindDn=uid=svc-reader,ou=service,dc=example,dc=org
credential=<giá trị bí mật, không hiển thị>
errorMessage=Lookup failed for cn=Student42,ou=people,dc=example,dc=org
~~~

Chỉ riêng `filter` đã có email; `baseDn` và `bindDn` cho biết cách tổ chức directory; `errorMessage` có thể mang họ tên, DN hoặc chi tiết nhạy cảm. Thay mọi mật khẩu bằng `[REDACTED]` vẫn không đủ nếu exception, HTTP tracing hoặc log của thư viện tự ghi lại dữ liệu gốc.

Bài học thuộc chương **Vận hành** của module **SPRING_LDAP** hướng tới việc xây dựng log hữu ích để xử lý sự cố mà bảo vệ thông tin thư mục. Người học sẽ:

1. Phân loại dữ liệu trong DN, filter, credential, LDAP attributes và exception;
2. Thiết kế **log event theo danh sách trường cho phép** thay vì ghi object hoặc câu lệnh LDAP gốc;
3. Sử dụng SLF4J/Spring LDAP để ghi thao tác search, bind, modify an toàn;
4. Kiểm soát log từ JNDI, TLS, thư viện, metrics, traces và các tầng thu thập tập trung;
5. Viết ca kiểm thử chứng minh dữ liệu nhạy cảm không xuất hiện trong log, kể cả khi thao tác thất bại.

Các ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring LDAP và một LDAP test server với dữ liệu giả. Tên package, backend log và cách trả exception phụ thuộc phiên bản triển khai; ví dụ tập trung vào nguyên tắc và đường ghi log do ứng dụng kiểm soát.

## 2. Phân loại dữ liệu trước khi quyết định ghi log

Không phải mọi chuỗi dùng cho LDAP đều là dữ liệu kỹ thuật vô hại. DN và LDAP filter thường chứa dữ liệu nhận dạng trực tiếp hoặc gián tiếp.

| Nhóm dữ liệu | Ví dụ giả lập | Rủi ro khi ghi nguyên văn | Chính sách mặc định |
| --- | --- | --- | --- |
| **User DN** | `uid=person-042,ou=people,dc=example,dc=org` | Tiết lộ định danh, OU, tổ chức, phân cấp thư mục | Không ghi |
| **Service bind DN** | `uid=svc-reader,ou=service,dc=example,dc=org` | Lộ tài khoản dịch vụ và mục tiêu xác thực | Không ghi nguyên văn |
| **Search base DN** | `ou=employees,dc=example,dc=org` | Tiết lộ cấu trúc tổ chức, vị trí tài khoản | Dùng mã vùng truy vấn cố định |
| **LDAP filter** | `(mail=student42@example.org)` | Lộ email/uid/nhóm, có thể chứa dữ liệu được escape | Không ghi nguyên filter |
| **Bind password / token / secret** | Giá trị đến từ secret manager | Có thể dẫn đến truy cập trái phép | Tuyệt đối không ghi, hash hoặc pseudonymize |
| **Entry attributes** | `cn`, `mail`, `telephoneNumber`, `memberOf` | Thông tin cá nhân, tổ chức hoặc quyền hạn | Không ghi giá trị |
| **Đặc biệt nhạy cảm** | `userPassword`, khóa, token, recovery data | Lộ credential và bí mật xác thực | Không ghi trong mọi log thông thường |
| **Exception message / cause** | Thông báo có DN, filter, endpoint | Lộ dữ liệu gián tiếp từ thư viện | Không ghi mặc định; phân loại bằng mã lỗi |
| **Raw BER/ASN.1 traffic** | Gói LDAP bind/search | Có thể gồm credential hoặc dữ liệu entry | Tắt logging thô trong vận hành |
| **Trace/metric attributes** | `ldap.filter`, `ldap.user_dn` | Tạo bản sao dữ liệu tại APM/collector | Chỉ dùng nhóm giá trị hữu hạn |

### 2.1. DN không chỉ là địa chỉ kỹ thuật

DN (Distinguished Name) gồm các RDN (Relative Distinguished Name), có thể chứa `cn`, `uid`, `ou`, `dc` và các thuộc tính tùy schema. Ví dụ `cn=Nguyen Van A,ou=people,...` trực tiếp chứa tên; `uid=a001` có thể liên kết với hồ sơ cá nhân. Dữ liệu được escape trong DN vẫn có thể được giải mã và liên kết với một tài khoản.

Vì thế không mặc định rằng chỉ che `cn` là đủ. Một DN có thể chứa nhiều RDN, escaped comma, quoted value hoặc giá trị nhị phân; việc cắt chuỗi theo dấu phẩy hay regex đơn giản không thể nhận diện đúng mọi cấu trúc DN.

### 2.2. Filter là dữ liệu đầu vào, không chỉ là cú pháp truy vấn

LDAP filter hỗ trợ các toán tử `&`, `|`, `!`, equality, substring và extensible match. Filter như `(&(objectClass=person)(uid=person-042))` có cả cấu trúc truy vấn và giá trị do người dùng nhập. Việc filter được escape đúng bằng `EqualsFilter` hoặc `LdapQueryBuilder` giúp truy vấn chống injection, **không khiến filter trở nên an toàn để ghi log**.

Một filter có thể chứa giá trị được mã hóa bằng escape theo RFC 4515, ví dụ biểu diễn byte dạng `\2a`. Redaction dựa trên cách hiển thị bề mặt dễ bỏ sót dữ liệu được escape, nested filter hoặc giá trị không giống email/uid. Không dùng filter gốc làm metric tag hay trace attribute.

### 2.3. Credential và chuỗi cấu hình

Các nguồn credential có thể là password người dùng, password bind service, access token trung gian, secret trong cấu hình, header `Authorization`, cookie hoặc dữ liệu đăng nhập được truyền qua object DTO. **Không log mật khẩu ngay cả khi đã băm SHA-256**, vì giá trị đó có thể bị dò từ danh sách mật khẩu phổ biến; không log chiều dài, tiền tố hoặc vài ký tự cuối của mật khẩu.

Dùng secret manager/biến môi trường theo chính sách của tổ chức; giới hạn người được đọc secret và tránh in cấu hình toàn bộ bằng `toString()`, actuator env endpoint hoặc debug dump. Khi cần xác minh rotation, ghi **mã đợt thay đổi không nhạy cảm** hoặc số phiên bản cấu hình được phép, không ghi giá trị secret.

## 3. Chiến lược bảo vệ: thiết kế log event an toàn ngay từ đầu

Có bốn cách tiếp cận thường bị gọi chung là “redaction” nhưng hiệu quả khác nhau:

| Cách tiếp cận | Ví dụ | Độ an toàn với log LDAP |
| --- | --- | --- |
| **Allowlist / data minimization** | Chỉ ghi operation, query kind, outcome, elapsed time | Ưu tiên cao nhất; dữ liệu gốc không được đưa vào logger |
| **Masking** | Thay một giá trị nhạy cảm bằng `[REDACTED]` | Hữu ích khi bắt buộc phải có field; vẫn phải xác định đúng field |
| **Pseudonymization có kiểm soát** | HMAC DN với khóa bảo vệ để tạo mã tương quan | Chỉ dùng khi có yêu cầu audit và đánh giá rủi ro liên kết danh tính |
| **Regex redaction ở sink** | Tìm mẫu email/DN trong log line | Phòng thủ bổ sung; không đáng tin làm lớp bảo vệ duy nhất |

**Nguyên tắc chính:** thay vì tạo dòng log chứa thông tin bí mật rồi cố xóa trước khi xuất, hãy tạo **log event vốn không có dữ liệu bí mật**.

### 3.1. Thiết kế bộ field được phép

Một event search an toàn có thể như sau:

~~~json
{
  "event": "ldap.search",
  "operation": "search",
  "query_kind": "find_user_by_uid",
  "backend": "primary",
  "search_scope": "one_level",
  "outcome": "success",
  "result_count": 1,
  "duration_ms": 47,
  "trace_id": "trace-generated-id"
}
~~~

Trong đó:

- `query_kind` là **hằng số từ code**; không chứa filter thực tế.
- `backend` là tên cụm logic do cấu hình đặt sẵn, không phải hostname nhạy cảm nếu không cần.
- `search_scope` thuộc tập `base`, `one_level`, `subtree`.
- `result_count` là số kết quả ở mức cần thiết; với một số nghiệp vụ nhạy cảm có thể chỉ ghi nhóm `zero`, `one`, `many`.
- `duration_ms` đo với đồng hồ đơn điệu, không chứa dữ liệu LDAP.
- `trace_id` chỉ là mã tương quan, không phải token xác thực; chỉ truyền qua cơ chế quan sát được quản lý.

Event trên cung cấp đủ thông tin để xem tìm kiếm nào chậm và có trả kết quả không, nhưng không chứa DN, uid, email hay filter.

### 3.2. Mã hóa ý nghĩa truy vấn bằng query kind

Ví dụ một service có ba loại tìm kiếm:

| Tác vụ | `query_kind` an toàn | Không ghi |
| --- | --- | --- |
| Tìm người dùng theo uid | `find_user_by_uid` | Giá trị uid, filter `(uid=...)` |
| Tìm nhóm theo thành viên | `find_groups_by_member` | DN thành viên, danh sách nhóm |
| Đọc một entry kiểm tra | `health_probe_lookup` | Bind credential, entry attributes thực |

Nhóm tên này phải do lập trình viên định nghĩa; không cho client HTTP tự chọn `query_kind` tùy ý. Giữ tên ổn định để so sánh log, metric và trace giữa các phiên bản.

## 4. Ví dụ Spring LDAP: search có log an toàn

Một thao tác search thường cần base DN, filter, SearchControls và mapper. Tất cả đều có thể chứa hoặc trả về dữ liệu riêng tư. Ta chỉ ghi **loại phép tìm kiếm**, số lượng, nhóm kết quả và thời gian.

### 4.1. Search bằng LdapTemplate và EqualsFilter

~~~java
import java.util.List;
import java.util.concurrent.TimeUnit;

import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class SafeDirectorySearchService {
    private static final Logger log =
            LoggerFactory.getLogger(SafeDirectorySearchService.class);

    private static final String QUERY_KIND = "find_user_by_uid";
    private static final String BACKEND = "primary";

    private final LdapTemplate ldap;

    public SafeDirectorySearchService(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<String> findCommonNames(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        // Chỉ dùng đầu vào cho filter; tuyệt đối không đưa uid/filter
        // vào log, trace, MDC hoặc metric.
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"cn"});
        controls.setCountLimit(10);
        controls.setTimeLimit(1200);

        String filter = new EqualsFilter("uid", uid).encode();
        long started = System.nanoTime();

        try {
            List<String> result = ldap.search(
                    "ou=people", filter, controls,
                    (AttributesMapper<String>) attrs -> {
                        Attribute cn = attrs.get("cn");
                        if (cn == null) {
                            throw new IllegalStateException(
                                    "Required attribute unavailable");
                        }
                        return String.valueOf(cn.get());
                    });

            log.info(
                    "event=ldap.search operation=search query_kind={} " +
                    "backend={} outcome=success result_count={} elapsed_ms={}",
                    QUERY_KIND, BACKEND, result.size(), elapsedMs(started));

            return result;
        } catch (RuntimeException failure) {
            // Không log failure, failure.getMessage() hoặc stack trace:
            // nhà cung cấp LDAP có thể chứa DN/filter/giá trị nhạy cảm.
            log.warn(
                    "event=ldap.search operation=search query_kind={} " +
                    "backend={} outcome=error error_category={} elapsed_ms={}",
                    QUERY_KIND, BACKEND,
                    SafeLdapFailureCategory.from(failure),
                    elapsedMs(started));
            throw failure;
        }
    }

    private static long elapsedMs(long started) {
        return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
    }
}
~~~

Các điểm cần kiểm chứng:

- `new EqualsFilter("uid", uid).encode()` xử lý ký tự đặc biệt theo cú pháp LDAP filter, giúp giảm nguy cơ injection. **Không log chuỗi filter trả về**.
- `"ou=people"` là base DN tương đối so với base của `ContextSource`. Tên `QUERY_KIND` thay thế việc xuất base/filter thực tế.
- `SearchControls` giới hạn scope, thuộc tính, số lượng và thời gian search; giới hạn này giảm cả tải directory và lượng dữ liệu được xử lý.
- Logger không nhận `uid`, `filter`, `result`, `failure` hoặc `failure.getMessage()` làm tham số. Kể cả câu log “query failed” cũng phải theo chính sách này.
- Exception gốc vẫn được ném lại để tầng xử lý lỗi phân loại và trả HTTP status phù hợp. Không biến lỗi truy cập thư mục thành danh sách rỗng.
- `elapsed_ms` là latency quan sát ở client, có thể gồm lấy context, bind dịch vụ ngầm và mapping. Nó không phải thời gian xử lý nội bộ của LDAP server.
- `result_count` có thể là số nhạy cảm trong một số use case; thay bằng bucket nếu chính sách dữ liệu không cho phép ghi chính xác.

Đoạn code minh họa cách ghi log ở service; nếu dùng `LdapClient` hoặc ODM, áp dụng cùng nguyên tắc ở ranh giới repository/adapter thực sự gọi directory. Không tạo log song song ở mọi tầng cho cùng một event nếu gây nhiễu và tăng khối lượng dữ liệu.

### 4.2. Tại sao parameterized logging chưa đủ?

SLF4J parameterized logging như `log.info("uid={}", uid)` giúp tránh nối chuỗi và có thể giảm chi phí formatting, **không tự loại bỏ dữ liệu nhạy cảm**. Nhiều log backend vẫn ghi nguyên đối số được truyền vào.

Một quy tắc dễ nhớ: **bất cứ biến nào có nguồn từ người dùng, LDAP entry, cấu hình secret hoặc exception chưa phân loại đều không được truyền trực tiếp vào logger**. Sử dụng tham số nhưng chỉ với các hằng số kỹ thuật đã duyệt, số đo phù hợp hoặc enum lỗi.

## 5. Phân loại lỗi LDAP mà không ghi nguyên exception

Lỗi vận hành vẫn cần có ý nghĩa: hệ thống phải phân biệt sai thông tin xác thực, ACL từ chối, network timeout, server unavailable và DN không hợp lệ. Tuy nhiên, `Exception.toString()`, `getMessage()`, nested cause và stack trace có thể chứa thông tin không được kiểm soát.

### 5.1. Bộ phân loại từ kiểu exception

Đoạn code sau phân loại một số cause của JNDI và TLS theo tập giá trị hữu hạn. Với Spring LDAP, nhiều lỗi JNDI được chuyển thành exception của Spring; nên kiểm tra chuỗi nguyên nhân và mở rộng mapper theo phiên bản thực tế.

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

import javax.naming.AuthenticationException;
import javax.naming.CommunicationException;
import javax.naming.InvalidNameException;
import javax.naming.NameNotFoundException;
import javax.naming.NoPermissionException;
import javax.naming.ServiceUnavailableException;
import javax.naming.SizeLimitExceededException;
import javax.naming.TimeLimitExceededException;
import javax.net.ssl.SSLHandshakeException;

public final class SafeLdapFailureCategory {
    private SafeLdapFailureCategory() {}

    public static String from(Throwable failure) {
        boolean network = false;
        boolean timeout = false;
        boolean unavailable = false;

        // Giới hạn độ sâu để không duyệt vô hạn cause chain bất thường.
        Throwable cause = failure;
        for (int depth = 0; cause != null && depth < 16;
             depth++, cause = cause.getCause()) {
            if (cause instanceof AuthenticationException) return "auth";
            if (cause instanceof NoPermissionException) return "access";
            if (cause instanceof SSLHandshakeException) return "tls";
            if (cause instanceof InvalidNameException) return "invalid_dn";
            if (cause instanceof NameNotFoundException) return "not_found";
            if (cause instanceof SizeLimitExceededException) return "size_limit";
            if (cause instanceof TimeLimitExceededException
                    || cause instanceof SocketTimeoutException) {
                timeout = true;
            }
            if (cause instanceof CommunicationException
                    || cause instanceof ConnectException
                    || cause instanceof UnknownHostException) {
                network = true;
            }
            if (cause instanceof ServiceUnavailableException) {
                unavailable = true;
            }
        }

        if (timeout) return "timeout";
        if (unavailable) return "unavailable";
        if (network) return "network";
        return "other";
    }
}
~~~

**Giới hạn của ví dụ:** bộ phân loại không bảo đảm nhận diện mọi LDAP result code từ mọi directory hoặc phiên bản Spring. Chẳng hạn mã 49 (`invalidCredentials`), 50 (`insufficientAccessRights`), 51 (`busy`) và 52 (`unavailable`) có thể xuất hiện qua các kiểu exception riêng hoặc ánh xạ provider-specific. Chỉ bổ sung phân loại khi nhận được mã lỗi **có cấu trúc**, không đọc message theo regex để đoán và ghi thông báo lỗi gốc.

### 5.2. Exception ở các tầng khác

Một exception có thể đi qua controller advice, AOP, gateway hoặc error reporting SDK. Nếu tầng thấp đã log an toàn nhưng controller viết `log.error("LDAP failed", exception)`, cả stack trace và message vẫn có thể bị ghi lại. Cần kiểm tra **toàn bộ đường đi của ngoại lệ**, không chỉ mã repository.

Ví dụ xử lý lỗi ở tầng web có thể trả mã lỗi chung và correlation ID, đồng thời log nhóm lỗi:

~~~java
// Minh họa logic ở tầng xử lý lỗi chung.
String category = SafeLdapFailureCategory.from(failure);
log.warn("event=directory.request_failed category={} operation={}",
        category, "find_user");
return genericFailureResponse();  // API contract của dự án
~~~

`genericFailureResponse()` là hàm giả định, không phải API Spring Boot có sẵn. Với Spring Security LDAP, không trả chi tiết “uid có tồn tại nhưng password sai” cho client nếu hệ thống có chính sách chống dò tài khoản. Phân biệt kết quả xác thực thất bại với LDAP unavailable trong log nội bộ mà vẫn giữ phản hồi bên ngoài phù hợp.

### 5.3. Không ghi stack trace tùy tiện

Trong SLF4J, tham số cuối cùng là `Throwable` có thể khiến backend in toàn bộ stack trace. Vì thế các cách gọi như `log.warn("LDAP failed", exception)` hoặc `log.error("operation={}", operation, exception)` phải được xem xét như thao tác **xuất toàn bộ thông tin exception**, không phải log một enum.

Khi thực sự cần debug lỗi sâu, triển khai cơ chế được cấp quyền và có thời hạn, chỉ cho môi trường thử nghiệm hoặc nguồn log đã được lọc dữ liệu ở **trước sink**, kèm quyết định giữ/không giữ message và stack. Không dựa vào việc người xem “không biết mật khẩu” hoặc log được lưu trong một cluster nội bộ làm biện pháp bảo mật.

## 6. Bind và credential: log kết quả, không log input

Với Spring LDAP, xác thực có thể thông qua `ContextSource.getContext(userDn, password)`, Spring Security LDAP authentication, hoặc các bước bind nội bộ khi `LdapTemplate` lấy context. Mọi kiểu bind đều phải áp dụng chính sách bí mật nhất quán.

Ví dụ an toàn với bind tường minh:

~~~java
import javax.naming.directory.DirContext;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public final class SafeBindOperation {
    private static final Logger log =
            LoggerFactory.getLogger(SafeBindOperation.class);

    private final ContextSource contextSource;

    public SafeBindOperation(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public void verify(String userDn, String credential) {
        long started = System.nanoTime();
        DirContext context = null;

        try {
            // Chỉ truyền credential tới LDAP API; không tạo log chứa DN,
            // credential, DTO hoặc object context.
            context = contextSource.getContext(userDn, credential);
            log.info(
                    "event=ldap.bind purpose=user outcome=success elapsed_ms={}",
                    TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started));
        } catch (RuntimeException ex) {
            log.warn("event=ldap.bind purpose=user outcome=error " +
                    "error_category={} elapsed_ms={}",
                    SafeLdapFailureCategory.from(ex),
                    TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started));
            throw ex;
        } finally {
            LdapUtils.closeContext(context);
        }
    }
}
~~~

Ở đây `started` được dùng để đo duration bằng `System.nanoTime()`, và chỉ độ trễ tính bằng mili giây được đưa vào log. Khi dùng bind để xác thực, cần bảo đảm không có log ở tầng web ghi request body, password hoặc DN khi ném lỗi. Account bind dịch vụ nên có quyền tối thiểu, mật khẩu được quản lý bằng secret manager và kết nối được bảo vệ bằng LDAPS/StartTLS với xác minh chứng chỉ.

Với LDAP URL, tránh đặt thông tin xác thực trong URL hoặc command line. LDAP server thông thường nhận credential qua cơ chế bind; không biến credential thành một phần `ldap://user:pass@host` hay biến thông tin nhạy cảm thành tham số truy vấn trong log.

### 6.1. Log an toàn khi xoay vòng secret

Trong quy trình rotation, cần biết instance nào đã nhận bản cấu hình mới và bind có thành công không. Có thể ghi:

~~~text
event=ldap.service_bind backend=primary
credential_version=config_release_2026_11
outcome=success elapsed_ms=61
~~~

`credential_version` ở đây là mã phiên bản triển khai **không chứa secret**, do hệ thống cấu hình kiểm soát. Không ghi nội dung secret, checksum nhanh của password, chiều dài, vài byte đầu/cuối hoặc token để “đối chiếu” vì thông tin đó có thể hỗ trợ suy đoán credential.

## 7. Redaction DN và filter: chọn kỹ thuật phù hợp

Khi buộc phải hỗ trợ điều tra theo một thực thể, có thể cần cơ chế tương quan an toàn hơn thay vì ghi nguyên DN. Chọn giải pháp dựa trên **mục đích điều tra và chính sách dữ liệu**, không chỉ thay ký tự.

### 7.1. Không trích RDN bằng cách cắt chuỗi

Ví dụ `cn=Doe\, Jane,ou=people,dc=example,dc=org` chứa dấu phẩy được escape bên trong `cn`. Code như `dn.split(",")` sẽ xử lý sai. DN có thể có nhiều giá trị RDN, chuỗi escape hex và thuộc tính binary.

Nếu thực sự cần **phân tích DN cho nghiệp vụ**, dùng parser phù hợp như `javax.naming.ldap.LdapName` / `Rdn` hoặc API DN của Spring LDAP; sau đó áp dụng chính sách chỉ xuất các nhóm **không định danh**. Việc parse đúng chỉ giúp hiểu cấu trúc, không tự làm dữ liệu an toàn để log.

### 7.2. Dùng tên vùng logic thay cho DN

Thay vì ghi `baseDn=ou=people,dc=example,dc=org`, dùng `search_area=users` hoặc `query_kind=find_user_by_uid` do code định nghĩa. Khi điều tra thay đổi đường đi, mapping giữa tên vùng và DN thực có thể nằm trong cấu hình quản trị có quyền truy cập riêng.

Đối với tìm kiếm ở nhiều OU khác nhau, dùng một danh mục cố định như `users`, `groups`, `service_accounts`, `other`; không tạo nhãn từ toàn bộ DN gốc.

### 7.3. Khi thật sự cần correlation giữa các lần truy vấn

Có thể tạo mã tương quan bằng **HMAC-SHA256 với khóa bí mật** cho một DN đã chuẩn hóa theo quy tắc nghiệp vụ, kèm scope/rotation key rõ ràng. HMAC được khóa giúp chống dò danh sách DN phổ biến tốt hơn hash không khóa, nhưng **mã này vẫn có thể liên kết các lần truy cập và có thể được coi là dữ liệu cá nhân**.

Chỉ triển khai khi có yêu cầu kiểm toán cụ thể; khóa phải nằm trong secret manager, không log key, không log DN trước khi HMAC, có retention và quyền truy cập rõ ràng. Không dùng HMAC này cho mật khẩu hoặc credential. Hãy cân nhắc việc thay bằng request correlation ID hoặc audit record có quyền truy cập riêng nếu mục tiêu chỉ là điều tra một request.

### 7.4. Redact bằng regex là lớp dự phòng

Regex có thể nhận diện vài pattern đã biết như email hoặc phần `password=...` trong log của một thư viện, nhưng khó bảo đảm xử lý đủ:

- DN có escaped comma, escaped equal, Unicode, multi-valued RDN;
- Nested filter, substring, LDAP hex escaping, binary attribute;
- Exception lồng nhiều tầng hoặc log được format lại bởi framework;
- Dữ liệu đã được mã hóa base64, URL encode hoặc JSON escape;
- Raw BER bytes, binary payload và log nhiều dòng.

Vì vậy **đừng lấy regex redaction ở collector làm lý do cho phép application in DN/filter/credential thô**. Khi hệ thống bắt buộc phải scrub log từ library, kiểm tra bằng tập dữ liệu giả có nhiều biểu diễn, giám sát lỗi scrub và giới hạn nguồn phát sinh log nguyên văn trước tiên.

## 8. Kiểm soát logging từ Spring LDAP, JNDI và TLS

Ngay cả khi code ứng dụng ghi log an toàn, các framework và thành phần vận hành có thể tạo log ngoài ý muốn. Khi bật debug để điều tra LDAP, cần nhận diện nguồn thực sự phát sinh dữ liệu.

| Nguồn | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Log application/service | DN, filter, credential, entry attributes từ log argument | Chỉ dùng field allowlist và nhóm lỗi |
| Spring LDAP/Spring Security DEBUG | Context, DN, filter hoặc thông báo xác thực chi tiết tùy phiên bản | Chỉ tăng log level sau khi kiểm tra output trên lab |
| JNDI LDAP provider | Log network, referral, bind/search; một số cơ chế trace mức giao thức | Tắt raw protocol tracing trong production |
| BER tracing (`com.sun.jndi.ldap.trace.ber`) | Có thể lộ bản tin LDAP và dữ liệu nhạy cảm ở cấp thấp | Không bật trong vận hành; chỉ dùng lab cô lập khi thật cần |
| TLS debug (`javax.net.debug`) | Certificate/handshake và chi tiết kênh TLS | Giới hạn thời gian, đầu ra và quyền truy cập khi điều tra |
| HTTP logging/filter/APM | Request body, Authorization, cookie, query params | Cấu hình exclude/masking từ đầu |
| Exception reporting SDK | Stack trace, breadcrumbs, HTTP context | Giảm trường thu thập, kiểm tra SDK masking |
| Log aggregator/collector | Bản sao dữ liệu nhạy cảm từ mọi nguồn | Pipeline lọc dự phòng, kiểm soát truy cập, retention |

Đặc biệt, `com.sun.jndi.ldap.trace.ber` là cơ chế trace mức BER của JNDI LDAP provider; không đặt property này trỏ vào output stream ghi log khi chạy production. Log dạng giao thức có thể tiết lộ giá trị bind/search và dữ liệu LDAP mà lớp log service đã cố tình loại bỏ.

Các logger cụ thể và mức chi tiết có thể khác nhau giữa Spring LDAP, Spring Security, JDK/JNDI và hệ thống logging đang dùng. Không giả định đặt riêng một logger Logback ở `WARN` sẽ vô hiệu hóa mọi luồng debug từ Java Util Logging hay output stream của JNDI. **Cần kiểm tra cấu hình và kết quả thu thập ở từng runtime thật**.

### 8.1. Kiểm tra cấu hình log theo môi trường

Quy trình gợi ý:

1. Liệt kê các logger ở tầng ứng dụng, Spring LDAP, Spring Security, JNDI và HTTP; xác định nơi thiết lập mức log.
2. Chạy các ca tìm kiếm và xác thực với dữ liệu giả trong môi trường thử nghiệm.
3. Kiểm tra **dòng log cuối cùng đi vào collector**, không chỉ console của service.
4. Xác minh không có DN/filter/credential/entry attributes trong log kể cả khi bật WARN/ERROR.
5. Chỉ bật DEBUG hoặc protocol tracing theo phiếu điều tra có thời hạn, người được phép và cơ chế xóa dữ liệu sau khi điều tra.
6. Khôi phục log level trước khi đưa lại môi trường vận hành thông thường.

Không cần tạo log cấp DEBUG bằng cách ghi thẳng user/password vào logger. Hầu hết vấn đề timeout, ACL, TLS hoặc pooling có thể được chẩn đoán bằng loại lỗi, độ trễ, số lần thử, result code an toàn và server-side metrics.

## 9. Logging, tracing và metrics phải dùng cùng chính sách dữ liệu

Một lỗi phổ biến là đã che DN ở log nhưng lại gắn nguyên DN vào **trace span**, **metric tag**, **MDC** hoặc một header nội bộ; kết quả vẫn rò rỉ qua hệ thống telemetry.

### 9.1. Mapping field theo nguồn quan sát

| Trường | Application log | Trace attribute | Metric label |
| --- | --- | --- | --- |
| `ldap.operation` | Có | Có | Có |
| `ldap.query_kind` | Có | Có | Có, nếu số loại nhỏ |
| `ldap.backend` | Có, tên logic | Có | Có |
| `outcome` / `error_category` | Có | Có | Có |
| `duration_ms` | Có, số đo | Span duration | Histogram/Timer |
| `trace_id` | Có khi cần tương quan | Thuộc metadata của trace | **Không** tạo label riêng |
| User DN / service bind DN | Không | Không | Không |
| LDAP filter / search values | Không | Không | Không |
| Password / token | Không | Không | Không |
| Entry attributes / group membership | Không mặc định | Không | Không |
| Exception message nguyên văn | Không mặc định | Kiểm tra exporter/SDK trước | Không |

Micrometer, OpenTelemetry hoặc APM có thể có instrumentation tự động. Dù ứng dụng không đặt field, thư viện khác vẫn có thể thu thập chúng. Kiểm tra các span attributes, log correlation, request/response capture và exception events ở **backend lưu trữ cuối cùng**.

Trong distributed tracing, dùng `traceparent` theo chuẩn propagation, không dùng DN hoặc filter làm correlation ID. Trace ID không phải credential, nhưng vẫn cần chính sách truy cập vì trace có thể tiết lộ topology.

### 9.2. MDC và structured logging

MDC là nơi chứa context log xuyên suốt một luồng xử lý. Chỉ đưa các giá trị an toàn như `traceId`, mã ứng dụng, component hoặc operation kind. **Không đặt `uid`, `userDn`, `filter`, `password` trong MDC**: chúng có thể xuất hiện trên mọi dòng log của thread.

Khi dùng thread pool hoặc `@Async`, phải bảo đảm cleanup context và propagation phù hợp; không copy toàn bộ request object vào logging context chỉ để tìm log của một người dùng.

## 10. Audit bảo mật khác log vận hành thông thường

Có trường hợp hệ thống phải trả lời câu hỏi “ai đã sửa entry nào vào thời điểm nào?”. Đó là nhu cầu **audit** có thể đòi hỏi một số định danh, nhưng **không có nghĩa được đưa DN hoặc tên người dùng vào log ứng dụng chung**.

| Log vận hành | Audit bảo mật |
| --- | --- |
| Phục vụ đo latency, error rate, saturation và điều tra hệ thống | Phục vụ trách nhiệm giải trình, điều tra thay đổi và đáp ứng yêu cầu bảo mật |
| Mặc định dùng query kind và nhóm lỗi | Có thể lưu danh tính đã được phê duyệt theo yêu cầu |
| Nhiều người vận hành và hệ thống quan sát có quyền đọc | Quyền truy cập chặt, có lưu vết đọc/xuất |
| Retention tối ưu cho troubleshooting | Retention theo chính sách audit/pháp lý cụ thể |
| Không lưu credential/DN/filter nhạy cảm | Vẫn **không** lưu mật khẩu, token hoặc secret |

Nếu audit cần DN đích của một modify, lưu trong hệ thống audit riêng được mã hóa, phân quyền, kiểm toán truy cập và có hạn lưu trữ. Có thể lưu mã định danh nội bộ hoặc liên kết tới bản ghi có quyền truy cập thay vì ghi nguyên DN. Tránh copy các audit record sang hệ thống metric/trace rộng quyền.

Trong hệ thống đa replica hoặc replicated directory, log client “modify sent” và “client received success” không tự chứng minh trạng thái toàn cụm; cần đối chiếu LDAP server audit, cơ chế replication và cách xác minh dữ liệu khi phản hồi bị mất.

## 11. Kiểm thử không rò rỉ dữ liệu nhạy cảm

Kiểm thử redaction phải bắt đầu từ **dữ liệu giả đã biết rõ là nhạy cảm**, rồi xác minh không có giá trị nào xuất hiện trong log được thu thập ở nhiều tầng. Chỉ unit test helper masking không chứng minh framework, JNDI hay collector đã an toàn.

### 11.1. Bộ dữ liệu giả để thử

Tạo các marker duy nhất dành cho lab, ví dụ:

~~~text
TEST_DN=cn=Audit Fixture,ou=people,dc=example,dc=org
TEST_FILTER=(&(objectClass=person)(mail=fixture42@example.org))
TEST_PASSWORD=TEST_ONLY_SECRET_NEVER_USE_IN_PRODUCTION
TEST_ATTRIBUTE=fixture-sensitive-note
TEST_ESCAPED_DN=cn=Doe\, Jane,ou=people,dc=example,dc=org
~~~

Những giá trị này **không phải credential thật**. Chỉ sử dụng chúng trên LDAP test environment. Với lỗi cố tình tạo ra, có thể mô phỏng exception chứa chuỗi DN/filter trong message để xác minh tầng bắt lỗi không ghi nguyên exception.

### 11.2. Ma trận kiểm thử

| Ca | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| S1 | Search thành công với uid giả | Log chỉ có query kind, outcome, count, latency |
| S2 | Search trả zero entry | Outcome phản ánh tìm kiếm hợp lệ, không ghi uid/filter |
| S3 | Search filter có escaped special characters | Log không chứa dữ liệu đầu vào hoặc filter đã encode |
| S4 | DN có escaped comma và Unicode | Không log DN dù chứa cú pháp đặc biệt |
| S5 | Bind đúng credential thử nghiệm | Log thành công, không có password/user DN |
| S6 | Bind sai credential | Error category `auth`, không ghi exception message chứa DN |
| S7 | LDAP server từ chối quyền | Error category `access` hoặc `other`, không có entry DN |
| S8 | TCP/reset/timeout | Log lỗi mạng/timeout, không có endpoint URL chứa thông tin nhạy cảm |
| S9 | TLS certificate error | Không log private key, secret hay raw handshake details |
| S10 | Modify entry giả thành công | Ghi operation/outcome, không có DN hoặc giá trị thuộc tính |
| S11 | Mất response sau modify | Client outcome không chắc chắn; không ghi raw entry hoặc tự retry |
| S12 | Exception lồng nhiều cause chứa marker | Tổng log vẫn không chứa marker |
| S13 | Một HTTP request lỗi qua controller advice | Không có request body/credential/exception nguyên văn |
| S14 | Tracing và metrics bật đồng thời | Span/label không chứa DN/filter/uid hoặc marker |
| S15 | Tăng log level trong lab | Phát hiện log phát sinh từ framework/JNDI trước production |
| S16 | Collector và archive lưu log | Không còn marker trong dữ liệu lưu cuối và bản sao được phép |

**Kiểm tra theo hành trình:** nhớ lấy dữ liệu **cuối pipeline**, ví dụ log backend mà người vận hành thực sự dùng. Nhiều tầng có thể thêm exception message hoặc HTTP context sau khi ứng dụng đã tạo log an toàn.

### 11.3. Kiểm thử unit với appender

Nếu dự án dùng Logback làm backend thử nghiệm, có thể gắn `ListAppender<ILoggingEvent>` vào logger mục tiêu, gọi service bằng dependency giả và kiểm tra formatted message không chứa marker. Sau đó cần test tích hợp với collector vì unit test này không theo dõi mọi nguồn log.

~~~java
// Minh họa assertion ở test; không phải mã production.
String emitted = capturedEvents.stream()
        .map(event -> event.getFormattedMessage())
        .collect(java.util.stream.Collectors.joining("\n"));

org.junit.jupiter.api.Assertions.assertFalse(
        emitted.contains("TEST_ONLY_SECRET_NEVER_USE_IN_PRODUCTION"));
org.junit.jupiter.api.Assertions.assertFalse(
        emitted.contains("fixture42@example.org"));
org.junit.jupiter.api.Assertions.assertFalse(
        emitted.contains("cn=Audit Fixture"));
~~~

`capturedEvents` là tập sự kiện được thu thập bởi appender trong test setup; phải cấu hình appender, chạy use case, tháo appender sau test và kiểm tra thêm exception/throwable proxy nếu logger có thể xuất stack trace. Assertions ở trên là khởi đầu, không phải một bài kiểm tra hoàn chỉnh của mọi đường ghi dữ liệu.

### 11.4. Dùng lỗi có chứa giá trị nhạy cảm để thử vòng catch

Một test quan trọng là tạo exception trong lớp LDAP adapter có message **chứa marker giả** rồi đi qua service/controller/logger. Nếu event ghi `error_category=other` mà không có message, đây là kỳ vọng an toàn. Nếu SDK báo lỗi tự động đính kèm stack trace/cause, cần cấu hình chặn hoặc làm sạch **trước khi xuất**.

Hãy ghi nhận cả **thành công, thất bại, retry, timeout và authentication reject**. Rò rỉ thường xuất hiện ở nhánh xử lý lỗi hiếm, nhất là khi nhà phát triển thêm log debugging.

## 12. Playbook xử lý khi phát hiện rò rỉ trong log

Nếu một kiểm thử hoặc cuộc kiểm toán phát hiện DN/filter/credential nhạy cảm trong log, cần xử lý theo trình tự phù hợp với mức độ và quy trình sự cố của tổ chức:

1. **Xác định nguồn phát:** logger/call site, library debug, trace exporter, collector, HTTP request logging hoặc exception reporter.
2. **Ngừng luồng phát sinh:** tắt log nguy hiểm hoặc vô hiệu hóa capture dữ liệu nhạy cảm, ưu tiên khắc phục tại nơi dữ liệu bắt đầu được ghi.
3. **Đánh giá phạm vi:** dữ liệu nào đã xuất, khoảng thời gian, đối tượng có quyền đọc, số bản sao, retention và các kho lưu trữ liên quan.
4. **Nếu có credential bị lộ:** thực hiện quy trình thu hồi/xoay vòng secret, đánh giá sử dụng trái phép và quản lý incident theo chính sách bảo mật.
5. **Xử lý bản ghi đã phát sinh:** xóa/redact ở các nơi có thể theo quy định, quản lý backup/archive và thông tin cho bên chịu trách nhiệm khi cần.
6. **Bổ sung kiểm thử:** tạo test marker tái hiện lỗi, xác minh đã chặn tại code và collector, giám sát regression sau deploy.

**Lưu ý:** sửa logger hôm nay không tự xóa dữ liệu đã được ghi trong log archive, tracing backend hay bản sao phục vụ sự cố. Cần giải quyết vòng đời dữ liệu đã tồn tại theo chính sách lưu trữ, bảo mật và nghĩa vụ liên quan.

## 13. Bài thực hành: thiết kế chính sách log an toàn cho directory

**Bối cảnh:** ứng dụng Spring Boot tra cứu nhân viên qua `LdapTemplate`, xác thực bằng LDAP bind và thỉnh thoảng sửa `description` trong môi trường thử nghiệm. Nhóm vận hành muốn phân tích lỗi timeout và quyền truy cập mà không tiết lộ DN, filter hoặc credential.

### 13.1. Yêu cầu thực hành

1. Chuẩn bị LDAP test server có TLS hợp lệ, account dịch vụ quyền tối thiểu và các entry dữ liệu giả.
2. Xây dựng `SafeDirectorySearchService` có `query_kind` cố định, scope/attributes/size limit hợp lý.
3. Thêm logger an toàn cho bind và modify: chỉ ghi operation, purpose, outcome, error category, elapsed time khi cần.
4. Viết mapper lỗi dùng cause/result code có cấu trúc, không in exception object hoặc message.
5. Bật Micrometer/trace nếu môi trường có; kiểm tra không có trường `uid`, DN/filter, password trong các tag/attributes.
6. Chạy các ca S1–S16 và kiểm tra log cuối pipeline bằng các marker giả.
7. Ghi nhận một trường hợp lỗi `invalidCredentials` và một lỗi network timeout; đối chiếu hai loại lỗi qua metric/log mà không thấy giá trị credential.
8. Lập tài liệu quy trình bật DEBUG ngắn hạn trong lab và cách tắt/kiểm tra sau điều tra.

### 13.2. Mẫu bảng kết quả

| Trường | Nội dung cần ghi |
| --- | --- |
| `test_id` | Mã ca, ví dụ `S6` |
| `operation` | Search/bind/modify |
| `input_class` | DN/filter/credential/attribute giả lập |
| `expected_log_fields` | Query kind, outcome, elapsed time, error category |
| `forbidden_markers_found` | Số marker nhạy cảm xuất hiện |
| `collector_checked` | Có/không và backend đã kiểm tra |
| `status` | PASS/FAIL kèm ghi chú nguyên nhân |

Một bài thực hành chỉ đạt khi **không có marker cấm** trong tất cả nguồn log/trace/metric đang kiểm thử, đồng thời operator vẫn xác định được loại lỗi và request liên quan qua trace ID hoặc event correlation thích hợp.

### 13.3. Câu hỏi tự đánh giá

1. Vì sao `log.info("filter={}", filter)` vẫn có thể làm lộ dữ liệu dù dùng SLF4J parameterized logging?
2. Vì sao `dn.split(",")` không phải cách parse DN hợp lệ?
3. Một exception `invalidCredentials` nên ghi gì để phục vụ vận hành nhưng không tạo điều kiện dò tài khoản?
4. Vì sao không dùng `uid`, email hoặc DN làm metric label?
5. HMAC DN có phải cách “ẩn danh tuyệt đối” không? Điều kiện nào khiến việc dùng mã tương quan này còn rủi ro?
6. Khi log service đã sạch nhưng collector vẫn nhận credential, bạn sẽ kiểm tra những nguồn phát nào?
7. Nếu `LdapTemplate.modifyAttributes` gặp network timeout, một dòng log `outcome=error` có chứng minh entry chưa được sửa không?

## 14. Checklist trước khi đưa vào vận hành

- [ ] Có inventory các loại dữ liệu LDAP nhạy cảm: DN, filter, password, token, entry attributes và exception message.
- [ ] Ghi log vận hành theo **allowlist**: operation, query kind, backend logic, outcome, error category, latency và count hợp lệ.
- [ ] Không log DN/filter thô hoặc thông tin xác thực, kể cả khi search/bind/modify thất bại.
- [ ] Không dùng `toString()` cho LDAP context, request DTO, entry object hoặc cấu hình chứa secret.
- [ ] Không ghi exception object/message/stack trace chưa qua chính sách vào log chung.
- [ ] Dùng loại lỗi có cấu trúc và ổn định thay cho nội dung exception; không parse message bằng regex để quyết định mã lỗi.
- [ ] Filter được tạo bằng builder/encoder phù hợp; việc encode không được coi là redaction.
- [ ] MDC, span attributes, metric labels và baggage cũng tuân thủ cùng quy tắc dữ liệu.
- [ ] Raw BER trace/JNDI protocol dump và debug chi tiết được tắt khi vận hành thông thường.
- [ ] Spring LDAP/Spring Security/HTTP logging/APM đã được kiểm tra ở từng môi trường.
- [ ] Event log và audit bảo mật được tách phạm vi truy cập và retention theo mục đích.
- [ ] Test có marker cho success/error/retry/timeout và data escaping, kiểm tra cả collector/archive.
- [ ] Credential rotation và xử lý dữ liệu đã lộ có quy trình sự cố rõ ràng.
- [ ] Không dùng regex ở sink làm biện pháp bảo vệ duy nhất.
- [ ] Người phát triển có ví dụ logger an toàn và quy tắc review tránh log request/body/filter/exception trực tiếp.

**Nguyên tắc kết thúc:** redaction hiệu quả nhất trong **Spring LDAP** là **không đưa DN, filter và credential vào telemetry ngay từ đầu**. Những gì đội vận hành thật sự cần là loại thao tác, định danh truy vấn cố định, thời gian, kết quả và nhóm lỗi. Từ đó có thể chẩn đoán timeout, TLS, pooling, ACL và sự cố truy cập directory mà vẫn bảo vệ dữ liệu người dùng và thông tin xác thực.
