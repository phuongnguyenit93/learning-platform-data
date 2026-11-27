# Metrics cho search, bind, modify và pool trong Spring LDAP

## 1. Vì sao cần đo riêng từng thao tác LDAP?

Trong hệ thống sử dụng **Spring LDAP**, một API đăng nhập hoặc tra cứu có thể phụ thuộc vào nhiều bước: lấy kết nối, bind, search, lookup và đôi khi modify entry. Khi response chậm hoặc phát sinh lỗi, chỉ nhìn vào health check `UP/DOWN` thường không đủ để trả lời liệu nguyên nhân là kết nối, xác thực, truy vấn thiếu chỉ mục, quyền truy cập hay nghẽn connection pool.

Bài học thuộc chương **Vận hành** của module **SPRING_LDAP** xây dựng một cách đo lường có hệ thống bằng **Micrometer** và **Spring Boot Actuator**, phù hợp khi ứng dụng sử dụng `ContextSource`, `LdapTemplate`, `LdapClient` hoặc ODM. Người học sẽ biết:

1. Định nghĩa metric cho `search`, `bind`, `modify` và pool với đơn vị, phạm vi đo, nhãn và ý nghĩa rõ ràng.
2. Gắn phép đo tại đúng ranh giới thao tác, phân biệt latency toàn bộ lời gọi với latency trên LDAP server.
3. Thiết kế bộ đếm, histogram, gauge và cảnh báo theo triệu chứng thực tế.
4. Tránh lộ thông tin định danh, DN, filter, mật khẩu hoặc các thuộc tính nhạy cảm qua telemetry.
5. Kiểm thử metric khi xảy ra timeout, retry, lỗi ACL, credential sai và pool cạn kết nối.

Các ví dụ giả định Java 17+, Spring Boot 3.x, `spring-ldap-core`, `spring-boot-starter-actuator` và registry Prometheus. Tên metric trong bài là **quy ước minh họa**, không phải tập metric mà Spring LDAP mặc định bảo đảm phát ra.

## 2. Bốn nhóm dữ liệu cần quan sát

| Nhóm | Câu hỏi vận hành | Metric cốt lõi |
| --- | --- | --- |
| **Search / lookup** | Tìm kiếm có chậm, trả quá nhiều entry, gặp lỗi filter/ACL hoặc hết time limit không? | Tổng attempts, latency, error rate, số kết quả và kết quả bị giới hạn |
| **Bind / xác thực** | Bind tới directory có thành công, chậm hoặc bị từ chối không? | Số lần bind, tỷ lệ thành công/thất bại, thời gian bind, lỗi mạng và lỗi credential |
| **Modify / thay đổi entry** | Các thao tác ghi có thất bại, chậm hay không rõ đã commit không? | Attempt count, latency, kết quả quan sát được, lỗi quyền/schema/timeout |
| **Connection pool** | Có đủ connection/context để mượn, có đợi lâu hoặc phải tạo nhiều kết nối mới không? | Active, idle, pending/waiters, max, thời gian borrow, timeout borrow, validation failures |

**Không gộp mọi lỗi thành một nhóm “LDAP down”.** Bind sai mật khẩu và kết nối bị reset có thể cùng làm HTTP request thất bại nhưng cần hành động xử lý hoàn toàn khác nhau. Search trả zero entry là kết quả hợp lệ trong nhiều nghiệp vụ, còn lỗi `noSuchObject` ở base DN có thể là vấn đề cấu hình hoặc quyền.

### 2.1. Metric đo điều gì: Timer, Counter, Gauge, DistributionSummary?

| Kiểu Micrometer | Ví dụ | Cách diễn giải |
| --- | --- | --- |
| `Timer` | `directory.ldap.operation` | Count và thời gian hoàn tất của từng attempt; có thể xuất histogram |
| `Counter` | `directory.ldap.retry.attempts` | Số lần retry phát sinh, tăng đơn điệu |
| `Gauge` | `directory.ldap.inflight`, `directory.ldap.pool.active` | Giá trị hiện tại tại lúc hệ thống scrape metric |
| `DistributionSummary` | `directory.ldap.search.results` | Phân phối số entry được trả cho một lần search thành công |
| `LongTaskTimer` (tùy chọn) | Tác vụ đồng bộ LDAP kéo dài nhiều phút | Theo dõi số job đang hoạt động và thời gian chạy của chúng |

Một `Timer` đã chứa số lượt hoàn tất, tổng thời gian và các giá trị thống kê được cấu hình. Tránh tạo thêm một `Counter` trùng hoàn toàn với count của Timer nếu hệ thống không có lý do đặc biệt: số đo trùng dễ bị cộng nhầm. **Gauge chỉ là ảnh chụp tại thời điểm scrape**; một spike rất ngắn giữa hai lần scrape có thể không xuất hiện.

### 2.2. Phân biệt request, operation và attempt

Một request HTTP có thể thực hiện nhiều LDAP operation. Một operation có thể có nhiều **attempt** nếu hệ thống retry. Cần thống nhất ngữ nghĩa:

~~~mermaid
flowchart LR
    A["1 HTTP request"] --> B["LDAP search logic"]
    B --> C["Attempt 1: timeout"]
    B --> D["Attempt 2: success"]
    A --> E["LDAP bind logic"]
    E --> F["Attempt 1: success"]
~~~

Ví dụ minh họa trên có **một HTTP request, hai operation logic và ba LDAP attempts**. Nếu Timer được đặt **bên trong vòng retry**, nó ghi ba lượt; nếu đặt **bao toàn bộ vòng retry**, nó ghi hai lượt và gồm cả thời gian backoff. Cả hai đều hữu ích nhưng phải có tên khác nhau, chẳng hạn:

- `directory.ldap.operation`: **một LDAP attempt**, tính từ trước khi mượn context đến khi API trả kết quả hoặc ném exception.
- `directory.ldap.request`: toàn bộ một công việc logic dùng LDAP, bao gồm retry/backoff nếu được bọc ở mức đó.
- `directory.ldap.retry.attempts`: chỉ đếm các attempts từ lần thứ hai trở đi.

Không ghi nhãn `outcome=success` cho retry lần đầu thất bại chỉ vì request cuối cùng thành công; khi đó metric sẽ che giấu suy giảm mạng.

## 3. Thiết kế tên metric, đơn vị và nhãn

Nên chuẩn hóa tên metric và tập nhãn trước khi viết code. Một thiết kế khả thi:

| Tên Micrometer | Loại | Tags có thể dùng | Giá trị cần đọc |
| --- | --- | --- | --- |
| `directory.ldap.operation` | Timer | `operation`, `outcome`, `error`, `backend` | Attempts/s, duration p95/p99, error rate |
| `directory.ldap.inflight` | Gauge | `backend` (nếu có) | Số LDAP attempts đang chạy trong JVM |
| `directory.ldap.search.results` | DistributionSummary | `query_type` | Số entry trả về mỗi search |
| `directory.ldap.retry.attempts` | Counter | `operation`, `reason` | Retry amplification |
| `directory.ldap.pool.active` | Gauge | `pool` | Context đang được mượn |
| `directory.ldap.pool.idle` | Gauge | `pool` | Context rỗi |
| `directory.ldap.pool.pending` | Gauge | `pool` | Thread đang chờ borrow |
| `directory.ldap.pool.max` | Gauge | `pool` | Giới hạn connection/context |
| `directory.ldap.pool.borrow` | Timer | `pool`, `outcome` | Latency mượn context |
| `directory.ldap.pool.validation.failures` | Counter | `pool` | Context hỏng bị phát hiện trong validation |

Tập giá trị nhãn nên **nhỏ và hữu hạn**:

- `operation`: `search`, `lookup`, `bind`, `modify`, `delete`... (chỉ những thao tác có thật).
- `outcome`: `success`, `error`.
- `error`: `none`, `auth`, `access`, `network`, `timeout`, `schema`, `server`, `other`.
- `backend` và `pool`: tên logic được cấu hình sẵn như `primary`, `read-replica`, `authentication`; không lấy từ input người dùng.
- `query_type`: nhóm truy vấn đã biết, ví dụ `find_user_by_uid`, `find_groups_by_member`; không đưa nguyên filter LDAP vào nhãn.

**Tuyệt đối không dùng** mật khẩu, user DN, email, `uid`, IP người dùng, filter động, giá trị thuộc tính, số điện thoại hay mã truy vết duy nhất làm metric tag. Những giá trị này có cardinality lớn, làm tăng chi phí lưu trữ và có thể tiết lộ dữ liệu nhạy cảm. Khi cần điều tra cụ thể, dùng log/trace có kiểm soát truy cập, chính sách retention và cơ chế che dữ liệu.

## 4. Chuẩn bị Micrometer và Actuator

Spring Boot Actuator sử dụng Micrometer làm cơ chế đo metric trong ứng dụng. Nếu muốn xuất Prometheus, dự án cần `spring-boot-starter-actuator` và `micrometer-registry-prometheus` tương thích với phiên bản Boot; Spring LDAP không tự xuất đủ các phép đo nghiệp vụ như bảng trên.

Ví dụ cấu hình:

~~~yaml
# application.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: never
  metrics:
    distribution:
      percentiles-histogram:
        "[directory.ldap.operation]": true
      slo:
        "[directory.ldap.operation]": 50ms,100ms,250ms,500ms,1s,2s

# Chỉ là ví dụ; endpoint telemetry phải được bảo vệ bằng cơ chế
# xác thực, network policy và cấu hình quan sát của môi trường.
~~~

Các SLO bucket trong YAML chỉ minh họa độ phân giải; lựa chọn thật phải dựa trên độ trễ quan sát được, yêu cầu người dùng và lưu lượng. Bật histogram làm tăng số time series theo tích số của các tổ hợp tag × bucket; cần tính chi phí và loại bỏ các nhãn không cần thiết.

Sau khi khởi động:

- `GET /actuator/metrics` cho biết các meter đã đăng ký.
- `GET /actuator/metrics/directory.ldap.operation` cho phép xem timer theo tên Micrometer khi đã có mẫu.
- `GET /actuator/prometheus` xuất dữ liệu theo định dạng Prometheus nếu registry được cấu hình và endpoint được bật.

**Bảo vệ endpoint metric:** không công khai Prometheus endpoint ra Internet. Giới hạn quyền truy cập bằng Spring Security, reverse proxy, network policy hoặc kênh giám sát nội bộ. Những thống kê về xác thực thất bại và topology có thể là thông tin vận hành nhạy cảm.

## 5. Viết lớp instrument dùng chung cho LDAP attempt

Ví dụ sau đặt Timer quanh một thao tác đồng bộ. `System.nanoTime()` được dùng để đo elapsed time; `Timer.record(..., TimeUnit.NANOSECONDS)` ghi nhận cả lượt thành công lẫn lượt ném exception. Tên tag và nhóm lỗi được cố định để tránh cardinality tăng ngoài ý muốn.

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import javax.naming.CommunicationException;
import javax.naming.NameNotFoundException;
import javax.naming.NoPermissionException;
import javax.naming.SchemaViolationException;
import javax.naming.ServiceUnavailableException;
import javax.naming.TimeLimitExceededException;
import javax.net.ssl.SSLHandshakeException;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class DirectoryLdapMetrics {
    private final MeterRegistry registry;
    private final AtomicInteger inflight = new AtomicInteger();

    public DirectoryLdapMetrics(MeterRegistry registry) {
        this.registry = registry;
        Gauge.builder("directory.ldap.inflight", inflight, AtomicInteger::get)
                .description("In-flight LDAP attempts in this JVM")
                .register(registry);
    }

    public <T> T measure(String operation, Supplier<T> ldapAttempt) {
        // operation phải thuộc tập tên cố định do code định nghĩa.
        long started = System.nanoTime();
        String outcome = "success";
        String error = "none";
        inflight.incrementAndGet();

        try {
            return ldapAttempt.get();
        } catch (RuntimeException failure) {
            outcome = "error";
            error = categorize(failure);
            throw failure;
        } finally {
            long elapsedNanos = System.nanoTime() - started;
            Timer.builder("directory.ldap.operation")
                    .description("One client LDAP attempt duration")
                    .tags(
                            "operation", operation,
                            "outcome", outcome,
                            "error", error)
                    .register(registry)
                    .record(elapsedNanos, TimeUnit.NANOSECONDS);
            inflight.decrementAndGet();
        }
    }

    public void recordSearchResults(String queryType, int count) {
        DistributionSummary.builder("directory.ldap.search.results")
                .baseUnit("entries")
                .tag("query_type", queryType)
                .register(registry)
                .record(count);
    }

    public void recordRetry(String operation, String reason) {
        Counter.builder("directory.ldap.retry.attempts")
                .tags("operation", operation, "reason", reason)
                .register(registry)
                .increment();
    }

    private static String categorize(Throwable error) {
        boolean network = false;
        boolean server = false;
        boolean timeout = false;

        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            // Nhóm auth và TLS cần được ưu tiên trước lỗi connection bao ngoài.
            if (cause instanceof javax.naming.AuthenticationException) {
                return "auth";
            }
            if (cause instanceof NoPermissionException) {
                return "access";
            }
            if (cause instanceof SSLHandshakeException) {
                return "tls";
            }
            if (cause instanceof SchemaViolationException
                    || cause instanceof NameNotFoundException) {
                return "schema";
            }
            if (cause instanceof TimeLimitExceededException
                    || cause instanceof SocketTimeoutException) {
                timeout = true;
            }
            if (cause instanceof CommunicationException
                    || cause instanceof ConnectException) {
                network = true;
            }
            if (cause instanceof ServiceUnavailableException) {
                server = true;
            }
        }

        if (timeout) return "timeout";
        if (network) return "network";
        if (server) return "server";
        return "other";
    }
}
~~~

Đoạn mã này minh họa phép đo trực tiếp. Một hệ thống hoàn chỉnh cần kiểm thử mapper lỗi với các exception do **phiên bản Spring LDAP và LDAP provider thực tế** trả về; các exception có thể được chuyển đổi sang kiểu Spring và không luôn chứa JNDI cause. Nếu cần phân biệt result code 49, 50, 51, 52 hoặc các chi tiết của Active Directory, hãy trích xuất từ kiểu dữ liệu có cấu trúc được provider hỗ trợ, không phân tích chuỗi exception message tùy tiện.

**Ranh giới đo:** Timer bắt đầu ngay trước `ldapAttempt.get()` và kết thúc khi lời gọi trở về hoặc ném lỗi, nên có thể bao gồm chờ pool, tạo kết nối, bind dịch vụ ngầm, search, mapping và đóng context. **Không được ghi tên metric này thành “server processing time”**, vì chỉ LDAP server mới biết thời gian xử lý nội bộ chính xác. Muốn biết riêng pool borrow hoặc bind ngầm, cần gắn đo tại tầng tương ứng.

Trong triển khai thật, các tag như `operation`, `reason` và `queryType` phải xuất phát từ **hằng số/enum**, không truyền trực tiếp chuỗi từ request. Với code đồng bộ trên virtual thread hay platform thread, phép đo hoạt động tương tự; gauge chỉ đếm đoạn code thực sự đi qua lớp instrument.

### 5.1. Vì sao không dùng một tag exception lấy nguyên tên class?

Có thể dùng tên class trong log được kiểm soát truy cập để điều tra. Tuy nhiên, tag metric như `error=some.long.CustomExceptionWithUserId...` gây cardinality và báo cáo không ổn định. Bộ phân loại cố định ít nhóm giúp ghép biểu đồ, đặt alert và so sánh các phiên bản. Nhãn `other` cần có cảnh báo điều tra khi chiếm tỷ lệ bất thường.

### 5.2. Lưu ý về số lần retry

Nếu mã nghiệp vụ gọi `metrics.measure("search",...)` **bên trong** vòng retry, Timer đếm từng attempt. Dùng `metrics.recordRetry("search", "network")` chỉ khi thật sự bắt đầu attempt bổ sung; không tăng bộ đếm retry ở lần gốc hoặc chỉ vì đã quyết định retry nhưng deadline ngăn không cho chạy.

Với LDAP modify, tuyệt đối không tự động retry khi socket timeout: server có thể đã commit thay đổi nhưng client mất response. Một timer ghi `outcome=error` có nghĩa **client không nhận được kết quả thành công**, không chứng minh directory chưa cập nhật dữ liệu.

## 6. Đo search và lookup

Search thường là điểm phát sinh chi phí lớn nhất vì scope rộng, filter không có index hoặc trả nhiều entry. Khi instrument search, cần ít nhất:

- **Latency một attempt** và error category;
- **Số entry trả về** nếu search hoàn tất;
- **Loại truy vấn** hữu hạn, ví dụ `find_user_by_uid`;
- Tỷ lệ **zero result**, **truncated/limit exceeded** nếu nghiệp vụ cần phân biệt;
- Timeout, size limit, referral, page count khi sử dụng các tính năng đó.

Ví dụ truy vấn tìm người dùng theo `uid`:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class DirectorySearchService {
    private static final String QUERY_TYPE = "find_user_by_uid";

    private final LdapTemplate ldapTemplate;
    private final DirectoryLdapMetrics metrics;

    public DirectorySearchService(
            LdapTemplate ldapTemplate,
            DirectoryLdapMetrics metrics) {
        this.ldapTemplate = ldapTemplate;
        this.metrics = metrics;
    }

    public List<String> findCommonNames(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        List<String> names = metrics.measure("search", () -> {
            SearchControls controls = new SearchControls();
            controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
            controls.setReturningAttributes(new String[] {"cn"});
            controls.setCountLimit(5);
            controls.setTimeLimit(1500);  // ms, giới hạn search

            String filter = new EqualsFilter("uid", uid).encode();

            return ldapTemplate.search(
                    "ou=people",
                    filter,
                    controls,
                    (AttributesMapper<String>) attrs -> {
                        Attribute cn = attrs.get("cn");
                        if (cn == null) {
                            throw new IllegalStateException(
                                    "cn attribute is unavailable");
                        }
                        return String.valueOf(cn.get());
                    });
        });

        metrics.recordSearchResults(QUERY_TYPE, names.size());
        return names;
    }
}
~~~

Giá trị tìm kiếm được encode bởi `EqualsFilter`, không ghép raw user input vào LDAP filter. DN gốc tìm kiếm là `ou=people` tương đối với base DN đã thiết lập trong `ContextSource`; `ONELEVEL_SCOPE` chỉ xét các entry con trực tiếp, không tự động tìm dưới mọi OU lồng nhau. Cần chọn scope, filter và index phù hợp DIT/schema thực tế.

### 6.1. Ba trường hợp dễ bị hiểu nhầm

**Trả zero entry hợp lệ:** người dùng không tồn tại hoặc không khớp filter. Đây có thể là `outcome=success` của một search, kèm phân phối result count bằng 0; không nên coi zero result đồng nghĩa LDAP unavailable.

**Bị giới hạn kết quả:** nếu API chỉ yêu cầu 5 entry và nhận đúng 5, điều đó chưa chứng minh thư mục chỉ có 5 entry. Nếu nghiệp vụ cần nhận biết bị cắt cụt, nên thiết kế search và status riêng; không dựa vào số kết quả bằng ngưỡng để khẳng định chắc chắn bị truncate.

**Query chậm nhưng server vẫn khỏe:** một `search` thiếu chỉ mục có thể chậm trong khi lookup theo DN nhanh. So sánh p95 theo `query_type` và server index/search log, tránh kết luận toàn LDAP server bị lỗi.

Nếu dùng tìm kiếm phân trang, đo cả số trang, số entry và tổng thời gian phiên; retry một trang có thể phát sinh dữ liệu trùng khi tập entry thay đổi giữa các lần đọc. Nếu thao tác read chạy qua `LdapClient` hay ODM, áp dụng lớp instrument ở ranh giới nghiệp vụ tương ứng; tránh đo trùng một lần gọi ở nhiều tầng rồi cộng các metric như thể là nhiều request độc lập.

## 7. Đo bind: phân biệt xác thực và kết nối

“Bind” có thể mang hai ý nghĩa vận hành khác nhau:

1. **Service bind:** ứng dụng dùng DN/mật khẩu dịch vụ để tạo context, sau đó search.
2. **User bind:** ứng dụng thử xác thực thông tin đăng nhập của một người dùng.

Khi `LdapTemplate` mượn context và thực hiện một service bind ngầm, thời gian đó có thể được **gộp trong timer search**. Muốn đo riêng mọi service bind thực tế, cần instrument ở `ContextSource`/cơ chế kết nối hoặc thu thập số liệu từ LDAP server; chỉ đặt Timer quanh `LdapTemplate.search` không tự tạo được “bind latency” chính xác.

Có thể đo một lần user bind được gọi tường minh qua `ContextSource`:

~~~java
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;
import org.springframework.stereotype.Service;

@Service
public class DirectoryBindService {
    private final ContextSource contextSource;
    private final DirectoryLdapMetrics metrics;

    public DirectoryBindService(
            ContextSource contextSource,
            DirectoryLdapMetrics metrics) {
        this.contextSource = contextSource;
        this.metrics = metrics;
    }

    public void verify(String userDn, String password) {
        if (userDn == null || userDn.isBlank()
                || password == null || password.isBlank()) {
            throw new IllegalArgumentException("Credentials are required");
        }

        metrics.measure("bind", () -> {
            DirContext context = null;
            try {
                // DN và password không được đưa vào metric hoặc log.
                context = contextSource.getContext(userDn, password);
                return Boolean.TRUE;
            } finally {
                LdapUtils.closeContext(context);
            }
        });
    }
}
~~~

Ở ví dụ này, xác thực thất bại được ném ra để tầng gọi chuyển thành phản hồi đăng nhập phù hợp theo chính sách bảo mật. Nếu method bắt lỗi credential rồi **trả false bên trong** `metrics.measure`, metric có thể ghi nhầm `outcome=success`. Hãy để instrument nhìn thấy lỗi rồi xử lý ngoại lệ ở tầng cao hơn, hoặc truyền trạng thái xác thực vào một API đo lường thiết kế riêng.

Để tránh tấn công dò tài khoản qua thông báo lỗi, phản hồi tới người dùng nên tổng quát; metric có thể phân biệt `auth` với `network` nhưng vẫn phải bảo vệ quyền truy cập. Không dùng nhãn `userDn`, `uid`, email, password hay thông tin phiên đăng nhập. Nếu ứng dụng dùng Spring Security LDAP AuthenticationManager, đo ở ranh giới xác thực thật và ghi nhận outcome sau khi cơ chế xác thực đã quyết định; không thêm một bind riêng chỉ để lấy metric vì điều đó tạo tải và có thể gây khóa tài khoản.

### 7.1. Phân tích tỷ lệ bind thất bại

Tỷ lệ lỗi `auth` cao có thể do người dùng nhập sai mật khẩu hoặc một secret dịch vụ đã hết hạn. Hai hiện tượng này cần phân loại bằng **loại bind logic**, ví dụ `bind_purpose=service` hoặc `user`, nếu hệ thống có thể gắn nhãn này **mà không tiết lộ danh tính**. Đối chiếu với LDAP server log, chính sách khóa tài khoản, xoay vòng secret và thời điểm deploy.

`auth_failure` không nên mặc định được tính như “LDAP server availability failure” khi lập SLO hạ tầng. Một mật khẩu sai không cho biết directory đang không sẵn sàng.

## 8. Đo modify và các thao tác ghi

`modify`, `add`, `delete` và `modDN` tạo thay đổi trạng thái, do đó phải tách khỏi search và bind khi lập dashboard. Với modify, đo:

- Attempts và latency theo operation;
- Kết quả client quan sát (`success`, `error` và nhóm lỗi);
- Số thao tác bị chặn bởi ACL, schema constraint hoặc optimistic concurrency nếu có;
- Số trường hợp timeout/đứt mạng sau khi request đã gửi mà **trạng thái commit còn chưa rõ**.

Ví dụ modify một thuộc tính duy nhất với DN đã được xây dựng/kiểm soát bởi ứng dụng:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryModifyService {
    private final LdapTemplate ldapTemplate;
    private final DirectoryLdapMetrics metrics;

    public DirectoryModifyService(
            LdapTemplate ldapTemplate,
            DirectoryLdapMetrics metrics) {
        this.ldapTemplate = ldapTemplate;
        this.metrics = metrics;
    }

    public void replaceDescription(Name entryDn, String description) {
        metrics.measure("modify", () -> {
            ModificationItem update = new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("description", description));

            ldapTemplate.modifyAttributes(
                    entryDn, new ModificationItem[] {update});
            return null;
        });
    }
}
~~~

**Yêu cầu trước khi chạy**: `entryDn` phải là DN tương đối hoặc tuyệt đối phù hợp với `ContextSource` mà dự án sử dụng và được xác minh thuộc nhánh cho phép cập nhật; account bind phải có ACL chỉ sửa thuộc tính cần thiết. Không cho phép client HTTP cung cấp tùy ý DN hoặc attribute name để đi vòng kiểm soát truy cập.

Với lỗi mạng sau khi gửi modify, Timer ghi `outcome=error` vì phía client không nhận được thành công. LDAP server có thể đã commit rồi mất response; **không đọc metric lỗi thành “ghi thất bại chắc chắn”**. Cần kiểm tra server audit log, entry state và chiến lược idempotency/compare-and-set nếu phải khôi phục. Không tự retry modify chỉ vì nhận timeout.

## 9. Connection pool: đo đúng tài nguyên thật

Connection pool cho LDAP có thể nằm trong **JNDI provider**, `PoolingContextSource` hoặc pool khác do ứng dụng tự cấu hình. Các loại pool không mặc nhiên có chung API metric.

Các chỉ số vận hành ưu tiên:

| Metric | Ý nghĩa | Khi bất thường |
| --- | --- | --- |
| `active` | Số connection/context đang được mượn | Gần `max` lâu dài có thể là cạn pool hoặc operation chậm |
| `idle` | Số connection/context đang rỗi | Idle bằng 0 liên tục khi tải tăng có thể là thiếu capacity |
| `pending`/`waiters` | Request đang chờ mượn | Pool đã trở thành nút thắt, latency tăng trước khi LDAP call chạy |
| `max` | Giới hạn capacity trong pool | Cần so với số replica và giới hạn LDAP server |
| Borrow latency | Thời gian lấy được context | p95/p99 tăng khi pool bị tranh chấp |
| Borrow timeout/rejection | Không mượn được trước thời hạn | Dấu hiệu cạn pool hoặc policy timeout quá ngắn |
| Create/close/evict/validation failure | Vòng đời context | Pool churn cao, kết nối stale hoặc LDAP/network biến động |

**Ranh giới kỹ thuật quan trọng:** `LdapContextSource.setPooled(true)` bật cơ chế JNDI pooling, nhưng API đó không bảo đảm cung cấp đủ `active`/`pending`/`borrow time` cho Micrometer. Không xây một gauge đặt tên `directory.ldap.pool.active` rồi gán bằng số operation đang chạy; đó là **in-flight LDAP calls**, không phải connection thực sự được pool mượn.

Nếu ứng dụng dùng **Apache Commons Pool 2** và **có quyền truy cập tới `GenericObjectPool<?>` thật**, có thể đăng ký gauge qua API của pool:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.commons.pool2.impl.GenericObjectPool;

public final class CommonsPoolLdapMeters {
    private CommonsPoolLdapMeters() {}

    public static void bind(
            MeterRegistry registry,
            String poolName,
            GenericObjectPool<?> pool) {

        Gauge.builder("directory.ldap.pool.active",
                        pool, p -> p.getNumActive())
                .tag("pool", poolName)
                .register(registry);

        Gauge.builder("directory.ldap.pool.idle",
                        pool, p -> p.getNumIdle())
                .tag("pool", poolName)
                .register(registry);

        Gauge.builder("directory.ldap.pool.pending",
                        pool, p -> p.getNumWaiters())
                .tag("pool", poolName)
                .register(registry);

        Gauge.builder("directory.ldap.pool.max",
                        pool, p -> p.getMaxTotal())
                .tag("pool", poolName)
                .register(registry);
    }
}
~~~

Đoạn mã trên **đòi hỏi một pool thật có API `GenericObjectPool` và dependency `commons-pool2`**. Nó không phải API mặc định để truy cập internal JNDI pool. Nếu wrapper `PoolingContextSource` không expose pool hoặc dùng thư viện khác, hãy dùng API/JMX metric được thư viện hỗ trợ hoặc instrument việc mượn/trả context ở tầng được phép. Không sửa cấu trúc pool chỉ để có một gauge, và không báo một giá trị suy đoán như số liệu thực.

### 9.1. Gauge và vòng đời đối tượng

Micrometer thường giữ tham chiếu yếu đến đối tượng được đo bằng gauge. Đối tượng pool phải có vòng đời lâu dài và còn tham chiếu mạnh từ container/bean; nếu để pool bị garbage collect, gauge có thể biến mất hoặc trả `NaN`. Không tạo pool mới chỉ để bind metric: phải bind **chính instance đang phục vụ LDAP**.

### 9.2. Độ trễ mượn pool khác với connect/read timeout

Một call có thể chờ 900 ms để mượn context, thêm 100 ms thực hiện search, tổng 1 giây. Timer bao toàn bộ service method sẽ cho thấy 1 giây, nhưng nếu thiếu borrow metric thì người vận hành có thể tối ưu sai filter LDAP. Đo riêng borrow cần instrument tại API borrow thực, gồm thành công, timeout và rejection; không lấy hiệu giữa Timer search và một con số latency LDAP server không cùng tập mẫu để suy ra borrow.

Khi dùng pooling, connection cũ có thể bị firewall đóng trong thời gian rỗi. Theo dõi validation failures, cách eviction/close hoạt động và tỷ lệ lỗi ở lần thao tác đầu tiên sau idle. Không cho rằng tăng `maxTotal` sẽ luôn giúp: nhiều connection hơn còn có thể làm LDAP server quá tải.

## 10. Từ metric đến dashboard và cảnh báo

Một dashboard tối thiểu nên đặt cạnh nhau:

1. **Throughput:** search/bind/modify attempts/s, chia theo outcome.
2. **Latency:** p50/p95/p99 theo operation và `query_type` khi đủ dữ liệu.
3. **Failure:** auth, ACL, network, timeout, server error; phân biệt lỗi cấu hình với sự cố LDAP.
4. **Load:** in-flight attempts, pool active/idle/pending, kết nối LDAP server và CPU.
5. **Retries:** attempt amplification, retry exhaustion và end-to-end latency.
6. **Data volume:** search result count, số trang và những giới hạn bị chạm.
7. **Business impact:** login error rate hoặc các API thất bại do LDAP, tách lỗi credential do người dùng nhập sai.

### 10.1. Ví dụ truy vấn PromQL

Khi Micrometer `Timer` tên `directory.ldap.operation` được xuất qua Prometheus registry, một kiểu tên phổ biến là `directory_ldap_operation_seconds_count` và `directory_ldap_operation_seconds_bucket`. Hãy xác nhận tên metric thực từ `/actuator/prometheus`: khác biệt phiên bản Micrometer, cách cấu hình registry, histogram và metric filter có thể làm tên/series khác với ví dụ.

~~~promql
# Throughput LDAP search attempts/s (tất cả outcomes).
sum(rate(directory_ldap_operation_seconds_count{
  operation="search"
}[5m]))

# Tỷ lệ error của search attempts trong 5 phút.
sum(rate(directory_ldap_operation_seconds_count{
  operation="search",outcome="error"
}[5m]))
/
clamp_min(sum(rate(directory_ldap_operation_seconds_count{
  operation="search"
}[5m])), 1e-9)

# p95 latency của search attempts, chỉ khi histogram được bật.
histogram_quantile(
  0.95,
  sum by (le) (
    rate(directory_ldap_operation_seconds_bucket{
      operation="search"
    }[5m])
  )
)

# Trung bình số LDAP attempt đang thực thi (giá trị tức thời theo JVM).
sum(directory_ldap_inflight)
~~~

PromQL trên là mẫu cho dashboard; biểu đồ p95 tổng hợp đúng cách cần histogram buckets có cùng định nghĩa và được cấu hình. **Không lấy trung bình các giá trị p95 của nhiều instance để suy ra p95 toàn cụm.** Nếu không bật histogram, có thể theo dõi count, tổng thời gian và tính average; không tự tạo p95 từ các giá trị trung bình.

### 10.2. Cách đặt cảnh báo có ý nghĩa

| Dấu hiệu | Cảnh báo gợi ý | Hành động ưu tiên |
| --- | --- | --- |
| Network/timeout error rate tăng kéo dài | Cảnh báo phụ thuộc LDAP suy giảm | Kiểm tra DNS, mạng, LDAP server, TLS, pool và timeout |
| Bind auth failure tăng đột ngột | Cảnh báo riêng cho xác thực | Đối chiếu secret rotation, brute force protection và account lockout |
| Search p95 tăng, result count tăng | Cảnh báo search chậm | Xem filter, index, scope, paging và kích thước entry |
| Pool pending tăng, active gần max | Cảnh báo nghẽn pool | Xem borrow time, leak, idle validation, concurrency và server capacity |
| Modify timeout tăng | Cảnh báo trạng thái ghi chưa rõ | Đối chiếu audit log và entry trước khi retry |
| Retry attempts tăng nhưng request cuối thành công | Cảnh báo suy giảm bị retry che khuất | Điều tra lỗi nền và ảnh hưởng p95 toàn API |

Ngưỡng cụ thể phải xuất phát từ SLO và baseline; tránh khẳng định mọi LDAP search phải dưới một ngưỡng chung cho tất cả hệ thống. Với biểu đồ lỗi khi tải thấp, cần điều kiện **mẫu tối thiểu** trong khoảng đo để tránh một lỗi trên một request gây tỷ lệ 100% thiếu ý nghĩa. Tách paging/search dài hạn khỏi lookup ngắn nếu chi phí khác nhau.

## 11. Metrics, timeout, retry và độ an toàn

Khi dùng `LdapContextSource` với JNDI, hai thuộc tính phổ biến là `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout` (đơn vị mili giây). Search có thể có `SearchControls.setTimeLimit(...)`; pool có thể thêm borrow timeout. Chúng có phạm vi khác nhau và không bảo đảm hạn chót tuyệt đối cho toàn bộ HTTP request.

Các hệ quả đối với metric:

- `directory.ldap.operation` ở tầng service có thể bao gồm connect, TLS, bind ngầm, borrow wait, search và mapping; đặt tên `client attempt latency`.
- `directory.ldap.pool.borrow` chỉ đo thời gian mượn nếu instrument ở đúng API pool.
- `directory.ldap.request` nên bao gồm retry và backoff nếu mục tiêu là đo latency nghiệp vụ.
- Khi một lời gọi bị timeout, metric client phản ánh **kết quả quan sát được**. Với modify, server có thể đã commit dù client báo lỗi.
- Khi backend server chuyển hướng referral hoặc search nhiều trang, cần đếm riêng các sub-operation nếu muốn phân tích toàn diện.

Nếu retry được bật cho đọc:

~~~mermaid
flowchart LR
    A["Request logic"] --> B["LDAP attempt 1"]
    B -->|Lỗi mạng| C["Timer: error; retry counter +1 khi sắp retry"]
    C --> D["Backoff + jitter"]
    D --> E["LDAP attempt 2"]
    E -->|Thành công| F["Timer: success"]
    F --> G["Request Timer: tổng thời gian"]
~~~

Phép đo nên ghi nhận **một Timed attempt cho mỗi lần thử**, không tăng count cả ở wrapper và bên trong cùng một attempt nếu dùng cùng metric. Khi retry bị hủy vì đã hết deadline, chỉ ghi retry attempt nếu thực sự bắt đầu lần thử; tách metric `retry.skipped` nếu cần đo những quyết định bị bỏ qua.

Không retry tự động các lỗi `invalidCredentials`, `insufficientAccessRights`, schema hoặc TLS certificate. Không tăng retry vì thấy tỷ lệ lỗi bind: hành động này có thể làm account lockout và tăng tải server. Khi pool đã đầy, backoff và rate limiting cần phối hợp với giới hạn đồng thời, thay vì để mọi thread xếp hàng vô hạn.

## 12. Thực hành: triển khai và kiểm chứng metric

**Bối cảnh:** một service Spring Boot tra cứu người dùng từ LDAP, xác thực qua bind và có chức năng thay đổi thuộc tính `description` trên môi trường thử nghiệm. Dịch vụ dùng LDAPS với tài khoản service chỉ có quyền phù hợp; môi trường có test LDAP server, dữ liệu giả và quyền truy cập metric nội bộ.

### 12.1. Chuẩn bị

1. Thêm Actuator, Micrometer Prometheus registry tương thích với Spring Boot.
2. Bật `/actuator/prometheus` chỉ trong phạm vi giám sát được bảo vệ.
3. Áp dụng `DirectoryLdapMetrics` tại ranh giới các thao tác search/bind/modify thực tế.
4. Nếu pool cung cấp API metric, gắn gauge vào **instance pool đang chạy**; nếu chưa có, ghi rõ metric chưa thu thập được thay vì tạo số liệu giả.
5. Tạo dashboard gồm count, error rate, p95 latency, retry count, inflight và pool saturation.

### 12.2. Ma trận kiểm thử

| Ca | Cách tạo tình huống trong môi trường test | Metric hoặc hành vi mong đợi |
| --- | --- | --- |
| M1 | Search trả một entry | Timer `search/success` +1; search results ghi 1 |
| M2 | Search hợp lệ không tìm thấy entry | Timer `search/success` +1; results ghi 0 |
| M3 | Search base/filter sai | Error group được ghi, không báo dữ liệu rỗng giả |
| M4 | Lỗi read timeout | `search/error/timeout` tăng nếu classifier nhận diện đúng |
| M5 | Bind credential sai | `bind/error/auth` tăng; không có password/DN trong tags |
| M6 | Bind thành công | `bind/success` tăng, latency được ghi |
| M7 | Modify được cấp quyền trong lab | `modify/success` tăng; kiểm tra entry thực sự đổi |
| M8 | Modify bị ACL từ chối | `modify/error/access` tăng; dữ liệu không đổi |
| M9 | Mất response sau modify | Ghi client error; xác minh commit bằng server log/đọc lại |
| M10 | Pool gần max và có waiters | Gauge active/pending và borrow latency tăng nếu pool expose |
| M11 | Pool trả connection cũ hỏng | Metric validation/borrow failure theo khả năng pool |
| M12 | Retry một search thất bại rồi thành công | Hai attempts được đo; một request logic, một retry |
| M13 | 500 user khác nhau gọi cùng loại search | Số time series **không** tăng theo số uid |
| M14 | Tắt LDAP server test | Lỗi mạng, latency, inflight và readiness phản ánh đúng tình huống |

Chỉ thực hiện thao tác modify với entry giả ở môi trường lab; không tạo lỗi bằng cách tắt directory production. Với ca M9, có thể mô phỏng response bị mất bằng fault proxy trong lab, rồi đối chiếu entry; không được xem exception client là bằng chứng modify chưa chạy.

### 12.3. Bài tập diễn giải dashboard

Giả sử trong 5 phút hệ thống ghi:

| Operation | Attempts | Success | Errors | Avg latency | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Search | 12.000 | 11.880 | 120 | 80 ms | 420 ms |
| Bind | 3.000 | 2.820 | 180 | 120 ms | 650 ms |
| Modify | 500 | 490 | 10 | 140 ms | 500 ms |

Các số liệu là giả định phục vụ bài tập. Hãy tính error rate:

- Search: `120 / 12.000 = 1%`.
- Bind: `180 / 3.000 = 6%`.
- Modify: `10 / 500 = 2%`.

**Câu hỏi phân tích:** 6% bind errors có nghĩa directory availability chỉ là 94% không? Không thể kết luận như vậy khi chưa tách auth failure do mật khẩu sai khỏi lỗi mạng, ACL và server. Vì sao search p95 lớn hơn nhiều average? Cần xem histogram, query type, pool wait và index thay vì chỉ nhìn average. Modify có 2% lỗi thì bao nhiêu trường hợp server thực sự không commit? Chỉ metric phía client chưa đủ xác định.

### 12.4. Tiêu chí hoàn thành

Bài thực hành đạt yêu cầu khi:

- Các thao tác thực tế tạo metric với tên, đơn vị và tập tag nhất quán;
- Timer phản ánh đúng số **attempt**, không chỉ request cuối cùng;
- Tỷ lệ bind auth error được phân biệt với lỗi LDAP unavailable;
- Search results và query type đo được mà không lộ `uid` hay LDAP filter;
- Modify timeout được trình bày là client error có khả năng commit chưa rõ;
- Pool metric phản ánh API đo **pool thật** hoặc được ghi nhận là chưa có;
- Prometheus endpoint được bảo vệ và dashboard không lộ dữ liệu người dùng;
- Các tình huống timeout, retry, lỗi ACL và tải cao được kiểm chứng trên lab.

## 13. Checklist vận hành

- [ ] Đã định nghĩa ranh giới đo riêng cho search, bind, modify, pool borrow và HTTP request.
- [ ] Đã phân biệt **attempt** với **logical operation**, nhất là khi có retry.
- [ ] Dùng Timer, Counter, Gauge, DistributionSummary đúng semantics; không đếm trùng.
- [ ] Có metric throughput, p95/p99 latency, error rate và result count cho search.
- [ ] Có phân loại bind authentication failure với network/TLS/server error.
- [ ] Có metric cho modify và quy trình xử lý kết quả ghi không chắc chắn.
- [ ] Pool metric lấy từ chính pool đang chạy, có active/idle/pending/max và borrow latency nếu hỗ trợ.
- [ ] Tập tags nhỏ, cố định; không chứa `uid`, email, DN, filter, password, IP hoặc mã phiên duy nhất.
- [ ] Histogram/percentiles được cấu hình theo SLO và chi phí time series có kiểm soát.
- [ ] Dashboard gắn metric client với server log, SLO nghiệp vụ và cảnh báo có mẫu tối thiểu.
- [ ] Readiness và liveness phản ánh đúng quan hệ phụ thuộc LDAP; không restart hàng loạt vì directory tạm chậm.
- [ ] Endpoint Actuator/Prometheus được bảo vệ bằng quyền truy cập và network policy.
- [ ] Các phép kiểm tra trên test environment có dữ liệu giả và không gây sửa đổi ngoài phạm vi.

Khi đo **Spring LDAP**, nguyên tắc quan trọng nhất là **metric phải nói đúng điều mình đã đo**. Timer bao một lời gọi `LdapTemplate` cho biết thời gian client chờ thao tác đó; nó không tự chứng minh thời gian xử lý nội bộ của LDAP server. Gauge in-flight của ứng dụng không phải gauge active connection trong pool, còn client báo lỗi modify không có nghĩa dữ liệu chưa được ghi. Phân biệt đúng các ranh giới này giúp giám sát LDAP có ích cho vận hành, bảo mật và điều tra sự cố.
