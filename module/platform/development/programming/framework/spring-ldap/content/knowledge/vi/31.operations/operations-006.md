# Trace request qua service và LDAP operation trong Spring LDAP

## 1. Mục tiêu: nhìn thấy đường đi của một request

Trong ứng dụng sử dụng **Spring LDAP**, một lời gọi REST tưởng đơn giản như “xem hồ sơ người dùng” có thể đi qua controller, service, `ContextSource`, thao tác `LdapTemplate.search(...)`, ánh xạ entry sang DTO rồi trả HTTP response. Một request đăng nhập còn có thể gồm tra cứu DN, bind bằng tài khoản người dùng, đọc thuộc tính và kiểm tra nhóm. Nếu API chậm hoặc lỗi, log rời rạc khó cho biết chậm ở đâu và thao tác nào thực sự gặp lỗi.

**Distributed tracing** giúp nối các bước xử lý bằng cùng một **trace ID** và biểu diễn chúng thành các **span** có thời điểm bắt đầu, kết thúc, trạng thái và thuộc tính. Bài này thuộc chương **Vận hành** của module **SPRING_LDAP**, hướng tới người học triển khai và kiểm thử Spring LDAP từ DN, filter, xác thực đến TLS, pooling và xử lý lỗi an toàn.

Sau bài học, người học có thể:

1. Phân biệt trace, span, trace context, log correlation và metrics.
2. Thiết kế cây span có ý nghĩa cho `HTTP → service → LDAP operation`.
3. Dùng Micrometer Observation với Spring Boot để tạo span thủ công quanh `LdapTemplate`, `LdapClient` hoặc ODM.
4. Giữ quan hệ cha–con khi có retry, thread pool hoặc tác vụ bất đồng bộ.
5. Gắn metadata hữu ích mà không làm lộ thông tin định danh, mật khẩu, DN, filter hoặc thuộc tính nhạy cảm.
6. Phân tích latency, lỗi mạng, bind thất bại và trường hợp modify đã gửi nhưng mất phản hồi.

Ví dụ sử dụng **Spring Boot 3.x, Spring Framework 6.x, Java 17+**, Micrometer Observation và một backend trace qua OpenTelemetry/OTLP. API/thuộc tính cấu hình có thể thay đổi theo phiên bản; cần đối chiếu dependency và cấu hình của dự án thực tế trước khi triển khai.

## 2. Trace khác metric và log như thế nào?

| Cơ chế | Trả lời tốt câu hỏi | Ví dụ |
| --- | --- | --- |
| **Metric** | “Bao nhiêu, nhanh hay chậm, tỷ lệ lỗi là bao nhiêu?” | p95 search latency 380 ms trong 5 phút |
| **Log** | “Sự kiện cụ thể nào đã diễn ra, nguyên nhân được ghi nhận là gì?” | LDAP read timeout kèm nhóm lỗi và thời điểm |
| **Trace** | “Một request cụ thể đi qua những bước nào, bước nào chiếm thời gian?” | HTTP 700 ms → service 650 ms → search attempt 530 ms |

Ba loại dữ liệu bổ trợ cho nhau. Một trace bị lấy mẫu chỉ đại diện cho một số request; vì vậy **không tính availability hoặc error rate toàn hệ thống chỉ từ số trace được lưu**. Metrics phải đủ bao phủ traffic và logs cần có quyền truy cập phù hợp.

### 2.1. Khái niệm nền tảng

- **Trace ID:** mã định danh dùng để nối các span thuộc cùng một request hoặc quy trình xử lý.
- **Span ID:** mã định danh một đoạn xử lý, ví dụ `directory.user.lookup` hoặc `directory.ldap.search`.
- **Parent span:** span bao bọc hoặc gọi tới span con. Quan hệ cha–con dùng để dựng cây trace.
- **Span attributes/tags:** thông tin như `ldap.operation=search`, `ldap.query_kind=find_user_by_uid` và `outcome=success`.
- **Trace context:** thông tin về trace/span hiện hành để một lời gọi ở tầng thấp tạo đúng child span.
- **Sampling:** quyết định trace nào được lưu hoặc xuất. Sampling không có nghĩa request không chạy; nó chỉ tác động mức dữ liệu trace quan sát được.
- **Baggage:** metadata có thể lan truyền qua các dịch vụ; chỉ dùng cho dữ liệu được kiểm soát. Không đưa danh tính người dùng, mật khẩu hay DN nhạy cảm vào baggage.

Trong HTTP, trace context thường được truyền qua header chuẩn **W3C Trace Context** như `traceparent` và `tracestate`. **Giao thức LDAP tự thân không bảo đảm truyền được W3C trace context tới LDAP server.** Vì vậy ứng dụng có thể tạo client span quanh lệnh LDAP, nhưng không tự động nhận được một server span LDAP nối vào cùng trace nếu directory server không có cơ chế quan sát bổ sung phù hợp.

## 3. Xác định ranh giới span đúng với Spring LDAP

Với một API tìm tên người dùng, cây span hợp lý có thể là:

~~~mermaid
flowchart TD
    A["HTTP GET /api/users/{id} (SERVER span)"] --> B["directory.user.lookup (service span)"]
    B --> C["directory.ldap.operation / search (CLIENT span logic)"]
    C --> D["LdapTemplate: context, bind nếu cần, search, mapping"]
    B --> E["Ánh xạ DTO hoặc kiểm tra nghiệp vụ"]
    A --> F["Serialize và gửi HTTP response"]
~~~

Các khối D và E trong sơ đồ là **giai đoạn xử lý**, không có nghĩa framework tự sinh ra span riêng cho từng khối. Một span do bạn tạo quanh `LdapTemplate.search(...)` có thể bao gồm:

- Chờ mượn LDAP context từ connection pool;
- Thiết lập TCP, TLS và bind dịch vụ nếu context chưa có;
- Gửi yêu cầu LDAP search, đợi các response và ánh xạ kết quả;
- Đóng hoặc trả context về pool.

Do đó span “LDAP operation” phía ứng dụng phản ánh **thời gian client quan sát**, không tương đương thời gian CPU hoặc thời gian xử lý nội bộ trên directory server.

### 3.1. Ranh giới span theo nghiệp vụ

| Span đề xuất | Phần việc đo | Không nên suy luận |
| --- | --- | --- |
| `HTTP SERVER` (framework tạo) | Nhận request đến khi kết thúc xử lý HTTP theo instrumentation | Không chỉ đo LDAP latency |
| `directory.user.lookup` | Logic nghiệp vụ tra cứu người dùng | Không chỉ đo search trên LDAP server |
| `directory.ldap.operation` với `operation=search` | Một **attempt** gọi `LdapTemplate.search` | Không nhất thiết đã có span bind/TLS/pool riêng |
| `directory.ldap.operation` với `operation=bind` | Một lần bind được ứng dụng thực hiện tường minh | Không tự đếm mọi service bind ngầm trong pool |
| `directory.ldap.operation` với `operation=modify` | Một lời gọi thay đổi entry từ góc nhìn client | Client timeout không chứng minh ghi chưa commit |
| `directory.pool.borrow` (nếu instrument được) | Thời gian mượn kết nối từ pool thật | Không phải thời gian TCP connect |
| `directory.search.logical` (tùy chọn) | Toàn bộ phép tra cứu, kể cả retry/backoff | Không thể cộng span con như những khoản thời gian độc lập |

**Tránh trùng span:** nếu đang dùng Java agent/OpenTelemetry instrumentation hoặc library tự sinh LDAP span, hãy kiểm tra trace thực tế trước khi thêm wrapper. Tracing ở nhiều tầng cho cùng một attempt có thể tạo hai span chồng nhau, khiến người xem tưởng đã có hai lần gửi LDAP request.

### 3.2. Ví dụ hai lần retry

Một request có thể có span như sau:

~~~text
trace_id = 4bc... (minh họa; đã rút gọn)
└─ HTTP GET /api/directory/users/{id} [680 ms]
   └─ directory.user.lookup [620 ms]
      ├─ directory.ldap.operation: search, attempt=1 [180 ms, network error]
      ├─ backoff [140 ms] (có thể không tạo span riêng)
      └─ directory.ldap.operation: search, attempt=2 [230 ms, success]
~~~

**Tổng latency không bằng phép cộng tùy ý mọi duration của span**: parent chứa child, các span có thể chạy song song, và phần còn lại thuộc mapping, queue, backoff hoặc các hoạt động chưa instrument. `attempt` có thể là attribute có giới hạn nhỏ trong trace, nhưng thường không cần là nhãn metric cardinality cao.

## 4. Cấu hình Spring Boot, Micrometer Tracing và OTLP

Spring Boot 3.x thường tự instrument HTTP server/client ở tầng framework khi có các dependency và cấu hình tracing tương ứng. Để các `Observation` thủ công chuyển thành trace/span, cần có tracing bridge và exporter hoặc một tracing backend tương ứng. `ObservationRegistry` **tự nó không bảo đảm dữ liệu được xuất** nếu không đăng ký handler và tracing pipeline.

Ví dụ dependency Maven trong dự án Spring Boot quản lý phiên bản:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.ldap</groupId>
        <artifactId>spring-ldap-core</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ cấu hình với **Spring Boot 3.x dùng đường cấu hình OTLP tương ứng**:

~~~yaml
spring:
  application:
    name: directory-api

management:
  tracing:
    sampling:
      probability: 0.10  # ví dụ: xuất khoảng 10% trace theo chính sách lấy mẫu
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces

# TLS từ ứng dụng đến collector, xác thực endpoint, resource attributes,
# giới hạn batch/queue và retention cần được triển khai theo môi trường.
~~~

Ở đây `otel-collector` là **dịch vụ thu trace minh họa**, không phải LDAP server. Khi cấu hình collector ở môi trường thực, sử dụng kết nối được bảo vệ thích hợp, xác thực và chính sách lưu trữ. Không làm lộ nội dung đăng nhập hay dữ liệu người dùng qua trace exporter.

Hành vi instrumentation, tên cấu hình và sampling có khác biệt giữa các phiên bản Spring Boot 3.x hoặc cấu hình OpenTelemetry SDK tùy chỉnh. Nếu dự án đã dùng OpenTelemetry Java agent, cần xác nhận ai chịu trách nhiệm tạo HTTP span, LDAP span và exporter để không phát sinh hai pipeline hoặc gửi cùng một trace hai lần.

### 4.1. Bắt đầu với một trace HTTP có sẵn

Trước khi tạo span LDAP, kiểm tra:

1. Gọi một endpoint HTTP thử nghiệm và quan sát trace trong backend.
2. Xác định có HTTP server span và tên service hợp lý.
3. Kiểm tra trace ID có xuất hiện trong log correlation khi hệ thống cấu hình logging phù hợp.
4. Xác minh sampling thực sự cho phép hiển thị trace cần kiểm tra; môi trường lab có thể đặt sampling 100%, production cần cân nhắc chi phí.
5. Chỉ thêm child spans khi biết pipeline nhận trace đã hoạt động.

Một trace không xuất hiện không tự chứng minh request không chạy: có thể trace bị sampler bỏ, exporter mất kết nối, queue đầy, collector từ chối hoặc backend chưa index.

## 5. Mã Java: tạo span quanh một LDAP attempt

Để tránh phụ thuộc vào bộ aspect tự động, ta dùng **Micrometer Observation API** trực tiếp. Khi `Observation` được tạo trong scope của một observation cha, handler tracing phù hợp sẽ tạo quan hệ cha–con cho span mới.

### 5.1. Lớp instrument LDAP có thể tái sử dụng

~~~java
import java.util.Set;
import java.util.function.Supplier;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class ObservedLdapOperations {

    private static final Set<String> OPERATIONS =
            Set.of("search", "lookup", "bind", "modify");

    private static final Set<String> QUERY_KINDS =
            Set.of("find_user_by_uid", "find_groups_by_member",
                   "user_bind", "replace_description");

    private final ObservationRegistry registry;

    public ObservedLdapOperations(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T execute(
            String operation, String queryKind, Supplier<T> action) {

        // Chỉ nhận nhãn hữu hạn, được định nghĩa trước trong code.
        if (!OPERATIONS.contains(operation)
                || !QUERY_KINDS.contains(queryKind)) {
            throw new IllegalArgumentException(
                    "Unexpected LDAP span classification");
        }

        Observation observation = Observation
                .createNotStarted("directory.ldap.operation", registry)
                .lowCardinalityKeyValue("ldap.operation", operation)
                .lowCardinalityKeyValue("ldap.query_kind", queryKind)
                .lowCardinalityKeyValue("ldap.backend", "primary")
                .start();

        try (Observation.Scope scope = observation.openScope()) {
            T result = action.get();
            observation.lowCardinalityKeyValue("outcome", "success");
            return result;
        } catch (RuntimeException | Error failure) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(failure);
            throw failure;
        } finally {
            observation.stop();
        }
    }
}
~~~

Trong ví dụ này:

- `directory.ldap.operation` là tên observation ổn định để cả metric và trace handler có thể sử dụng.
- `ldap.operation`, `ldap.query_kind` và `ldap.backend` là **tập nhãn cố định**, giúp lọc trace mà không bộc lộ DN, `uid` hay filter.
- `openScope()` kích hoạt observation hiện hành trong thread, để thao tác lồng bên trong có thể được gắn quan hệ cha–con.
- `observation.error(failure)` ghi nhận exception mà caller có thể phân tích; không tự chuyển lỗi credential thành “LDAP infrastructure unavailable”.
- Scope được đóng và observation được stop cả khi thao tác lỗi. Caller vẫn nhận exception ban đầu.
- Không dùng `ThreadLocal` tự chế để chứa trace ID. Thư viện observation/tracing đã có cơ chế context riêng.

Tên method `execute` mang tính minh họa; với mã thực tế nên khai báo các loại thao tác bằng enum/hằng số để không đưa string từ HTTP request vào nhãn. Nếu muốn lưu exception class trong trace, kiểm tra trước chính sách bảo mật: exception message có thể vô tình chứa DN/filter hoặc dữ liệu nhạy cảm.

**Chi tiết quan trọng:** với Micrometer Observation, các key/value thông thường được ghi vào observation context và có thể chuyển thành span attributes/metric tags tùy handler. Không tạo metric tag cho những giá trị có cardinality cao hoặc thông tin nhận dạng.

### 5.2. Gắn child span vào một service span

Ví dụ service tìm thuộc tính `cn` theo `uid`. Giá trị đầu vào chỉ dùng để dựng filter an toàn, **không đi vào trace attribute**.

~~~java
import java.util.List;
import java.util.Optional;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class DirectoryUserService {

    private final LdapTemplate ldapTemplate;
    private final ObservedLdapOperations ldapTrace;
    private final ObservationRegistry observationRegistry;

    public DirectoryUserService(
            LdapTemplate ldapTemplate,
            ObservedLdapOperations ldapTrace,
            ObservationRegistry observationRegistry) {
        this.ldapTemplate = ldapTemplate;
        this.ldapTrace = ldapTrace;
        this.observationRegistry = observationRegistry;
    }

    public Optional<String> findCommonName(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        Observation serviceSpan = Observation
                .createNotStarted(
                        "directory.user.lookup", observationRegistry)
                .lowCardinalityKeyValue("use_case", "user_lookup")
                .start();

        try (Observation.Scope scope = serviceSpan.openScope()) {
            return ldapTrace.execute(
                    "search", "find_user_by_uid",
                    () -> searchOnce(uid));
        } catch (RuntimeException | Error failure) {
            serviceSpan.error(failure);
            throw failure;
        } finally {
            serviceSpan.stop();
        }
    }

    private Optional<String> searchOnce(String uid) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"cn"});
        controls.setCountLimit(2);
        controls.setTimeLimit(1200); // giới hạn search; mili giây

        String filter = new EqualsFilter("uid", uid).encode();

        List<String> names = ldapTemplate.search(
                "ou=people", filter, controls,
                (AttributesMapper<String>) attrs -> {
                    Attribute value = attrs.get("cn");
                    if (value == null) {
                        throw new IllegalStateException(
                                "Expected cn is unavailable");
                    }
                    return String.valueOf(value.get());
                });

        if (names.size() > 1) {
            throw new IllegalStateException("uid is not unique");
        }
        return names.stream().findFirst();
    }
}
~~~

**Dòng chảy observation:** khi `findCommonName(...)` được gọi trong HTTP request có tracing được bật, `directory.user.lookup` trở thành span con của HTTP span, còn `directory.ldap.operation` trở thành con của service span. Nếu service được gọi từ job không có parent trace, service observation có thể trở thành root span.

`EqualsFilter` encode giá trị `uid`, giúp tránh nối trực tiếp dữ liệu người dùng vào LDAP filter. `ou=people` là DN tương đối so với base DN của `ContextSource`. `ONELEVEL_SCOPE` chỉ tìm entry con trực tiếp; nếu người dùng ở OU lồng nhau, cần chọn scope và giới hạn tìm kiếm phù hợp với mô hình thư mục.

**Giới hạn quan sát:** mã này chỉ tạo một span cho **một lời gọi search**. Nó không tự chia thành DNS/TCP/TLS/bind/pool/search/result mapping spans; muốn quan sát các tầng đó phải instrument tại API thực tương ứng hoặc đối chiếu số liệu server.

### 5.3. Khi service có nhiều LDAP operations

Một chức năng đăng nhập có thể:

1. Search DN người dùng bằng tài khoản dịch vụ;
2. Bind dùng thông tin đăng nhập người dùng;
3. Search nhóm liên quan;
4. Tạo kết quả xác thực cho HTTP response.

Nếu mỗi bước cần phân tích độc lập, tạo ba child spans `search`, `bind`, `search` cùng nằm dưới một service span. Bước bind có thể được instrument bằng cách bao lời gọi `ContextSource.getContext(userDn, password)` rồi **đóng context** sau khi xác thực. Không đưa password, DN người dùng hay thông tin group membership cụ thể vào trace.

Đừng tạo một “bind span” giả nếu chỉ quan sát được `LdapTemplate.search(...)`, bởi `LdapTemplate` có thể sử dụng context đã được bind trước đó từ pool. Trong trường hợp đó, span đúng là **client operation search**, còn việc bind ngầm phải được đo tại cơ chế tạo context hoặc từ log LDAP server.

## 6. Ghi nhận bind, modify và kết quả mơ hồ

### 6.1. Bind do ứng dụng thực hiện tường minh

Ví dụ cấu trúc cho user bind:

~~~java
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public final class BindExample {
    private final ContextSource contextSource;
    private final ObservedLdapOperations observed;

    public BindExample(
            ContextSource contextSource,
            ObservedLdapOperations observed) {
        this.contextSource = contextSource;
        this.observed = observed;
    }

    public void verifyCredentials(String userDn, String password) {
        observed.execute("bind", "user_bind", () -> {
            DirContext context = null;
            try {
                context = contextSource.getContext(userDn, password);
                return Boolean.TRUE;
            } finally {
                LdapUtils.closeContext(context);
            }
        });
    }
}
~~~

Trong production, validation của `userDn` và `password` phải do luồng xác thực an toàn thực hiện; DN phải được xác định phù hợp với tài khoản đang xác thực. Không thêm một bind phụ chỉ để tăng số span, vì điều đó làm tăng tải LDAP và có thể kích hoạt khóa tài khoản.

- **Invalid credentials** là kết quả xác thực thất bại, không mặc định có nghĩa directory server down.
- **Network timeout** là vấn đề liên lạc; phân tích cùng với TLS, connect/read timeout và pool.
- **TLS certificate error** cần sửa truststore/chứng chỉ thay vì retry.
- **ACL bị từ chối** cần điều tra quyền tối thiểu chứ không thử lại liên tục.

Observation phía client có thể đánh dấu một exception là lỗi; dashboard availability nên lọc và phân loại lỗi theo nguyên nhân nghiệp vụ, tránh tính tất cả login sai mật khẩu thành sự cố hạ tầng LDAP.

### 6.2. Modify và thao tác ghi

Khi ứng dụng gọi `LdapTemplate.modifyAttributes(...)`, một span đo latency và client outcome là hữu ích:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public final class ModifyExample {
    private final LdapTemplate ldap;
    private final ObservedLdapOperations observed;

    public ModifyExample(
            LdapTemplate ldap, ObservedLdapOperations observed) {
        this.ldap = ldap;
        this.observed = observed;
    }

    public void replaceDescription(Name allowedDn, String description) {
        observed.execute("modify", "replace_description", () -> {
            ModificationItem update = new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("description", description));
            ldap.modifyAttributes(
                    allowedDn, new ModificationItem[] {update});
            return null;
        });
    }
}
~~~

Ví dụ chỉ dùng với **DN và thuộc tính đã được ứng dụng kiểm soát**, danh tính dịch vụ có ACL phù hợp và dữ liệu giả trong môi trường thử nghiệm. Không lấy DN/attribute tùy ý do người dùng gửi để đưa thẳng vào modify.

Nếu kết nối bị cắt **sau khi server đã thực thi modify nhưng trước khi client nhận response**, span của client có thể kết thúc bằng lỗi. Điều này chỉ có nghĩa **client chưa xác nhận được kết quả**, không chứng minh thay đổi đã rollback hoặc chưa được ghi. Không tự động retry modify khi status chưa rõ; kiểm tra server log/entry state với quy tắc đồng thời và replication phù hợp.

Để điều tra thao tác ghi, có thể gắn `client_outcome=unknown` cho nhóm lỗi timeout/connection **theo chính sách của hệ thống**, nhưng đừng đoán chắc server đã commit hay chưa chỉ từ exception. Việc đối chiếu phải dựa vào dữ liệu thực tế và các nguồn có thẩm quyền.

## 7. Context propagation qua thread pool và luồng bất đồng bộ

Một span LDAP chỉ trở thành con của HTTP/service span nếu **trace context hiện hành** được duy trì tại thời điểm span được tạo. Trong mã đồng bộ cùng thread, `Observation.Scope` thường đủ. Nhưng khi công việc chuyển sang thread khác, task executor, message consumer hoặc Reactor pipeline, có thể mất mối liên hệ nếu không truyền context đúng cách.

### 7.1. Lỗi phổ biến khi dùng executor

~~~text
HTTP thread:
  trace A → service span
       submit(() -> ldap.search(...))   // task được đẩy sang worker thread

worker thread:
  nếu không truyền context → tạo trace B độc lập
  nếu truyền context đúng → tạo child span trong trace A
~~~

Trường hợp thứ hai là điều mong muốn nếu tác vụ con thực sự thuộc cùng yêu cầu. Tuy nhiên, nếu đã hoàn tất HTTP response mà job chạy thêm trong thời gian dài, cần quyết định rõ đó là một công việc nền độc lập có liên kết qua span link hoặc nghiệp vụ khác, thay vì luôn ép nó là child của HTTP span đã kết thúc.

### 7.2. Spring TaskDecorator cho executor (Spring Framework 6.1+)

Ví dụ khi dùng `ThreadPoolTaskExecutor` trong dự án Spring Boot phù hợp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ObservedExecutorConfig {

    @Bean(name = "directoryTaskExecutor")
    ThreadPoolTaskExecutor directoryTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("directory-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

`ContextPropagatingTaskDecorator` giúp truyền các context đã được tích hợp với Micrometer Context Propagation qua ranh giới task. Dùng nó với **executor thực sự chạy công việc LDAP**, không chỉ tạo một bean rồi mặc định mọi `@Async` hoặc tác vụ khác đều sử dụng bean này. Các ứng dụng cần kiểm tra cấu hình `@Async`, task scheduling và thread pool được chọn.

Một queue hữu hạn giúp tránh giữ công việc quá lâu khi LDAP chậm; cần kết hợp connect/read timeout và giới hạn concurrent LDAP operation. Context propagation không thay thế timeout hoặc kiểm soát tải.

### 7.3. Reactor, WebFlux và các tác vụ khác

Trong WebFlux, trace context liên quan Reactor Context và cơ chế instrumentation tích hợp của framework; `ThreadLocal` scope của Java không tự lan truyền qua mọi operator hoặc scheduler. Khi gọi API LDAP đồng bộ từ reactive service, **không chặn event-loop thread**: chuyển lời gọi sang scheduler phù hợp với số worker hữu hạn, bảo đảm context propagation và kiểm tra latency/capacity.

Khi gửi message sang queue hoặc gọi HTTP tới service khác, dùng propagation mechanism của transport được framework hỗ trợ. Không tự thêm trace ID vào LDAP DN hoặc LDAP filter để “truyền trace”; điều đó làm đổi ý nghĩa truy vấn, có thể phá ACL và tiết lộ metadata.

### 7.4. Vì sao đôi khi trace bị tách?

| Biểu hiện | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| HTTP và LDAP span có trace ID khác nhau | Mất context khi qua executor, callback hoặc Reactor scheduler | Kiểm tra scope hiện hành và propagation tại đúng ranh giới async |
| LDAP span không có parent | Gọi ngoài HTTP, root observation chưa được mở hoặc instrumentation thiếu | Kiểm tra caller, initialization và handler |
| Span xuất hiện hai lần | Instrumentation thủ công trùng Java agent/framework | Xác minh vị trí tạo span và pipeline export |
| Log có trace ID nhưng collector không có trace | Sampling, exporter queue, endpoint hoặc quyền gửi | Kiểm tra sampling decision và trạng thái exporter |
| Trace có HTTP span nhưng không có LDAP | Nhánh code không đi qua wrapper hoặc trace handler chưa hoạt động | Gọi đúng use case, kiểm tra registry và trace backend |

## 8. Chọn span attributes hữu ích và an toàn

Một trace tốt chứa **ngữ nghĩa thao tác**, không chứa dữ liệu LDAP của người dùng.

| Dữ liệu | Có nên đưa vào span? | Cách làm |
| --- | --- | --- |
| `ldap.operation=search/bind/modify` | Có | Tập giá trị cố định |
| `ldap.query_kind=find_user_by_uid` | Có | Enum/hằng số của code |
| `ldap.backend=primary` | Có | Tên cụm logic được cấu hình |
| `outcome=success/error` | Có | Kết quả client quan sát |
| `error.category=network/auth/access/tls/schema` | Có, sau khi phân loại | Giá trị hữu hạn, không dùng exception message |
| `retry.attempt=1/2/3` | Có thể | Số lượt hữu hạn trong trace; không thêm vào tag metric nếu không cần |
| `ldap.base_dn` hoặc entry DN thực | Tránh theo mặc định | Có thể lộ cấu trúc directory và danh tính |
| `ldap.filter` chứa `uid` hoặc email | Không | Dùng `query_kind` thay cho filter thực |
| Password, token, cookie, certificate private key | Tuyệt đối không | Không thu thập hoặc ghi log/trace |
| Thuộc tính `cn`, `mail`, `memberOf`, `userPassword` | Không mặc định | Chỉ thu thập qua quy trình xử lý dữ liệu bảo mật riêng nếu thật sự cần |
| Full exception message/stack trace | Không mặc định | Có thể chứa DN và thông tin kết nối nhạy cảm; kiểm soát nguồn ghi |

Để giảm rủi ro, nên có **allowlist** của span attributes. Nếu thư viện tự gắn exception event, log hoặc SQL/LDAP-like query raw vào trace, cần kiểm tra exporter và masking thực tế. Trace IDs là mã tương quan, không nên được coi là token xác thực hoặc bằng chứng quyền truy cập.

### 8.1. High cardinality và dữ liệu nhạy cảm

Micrometer có sự phân biệt giữa low-cardinality và high-cardinality key values. Một số tracing backend có thể lưu high-cardinality attributes mà metrics không dùng làm nhãn; nhưng **không vì thế mà được đưa `uid`, DN hay email vào trace**. Trace vẫn được xuất, lưu trữ và truy cập bởi các hệ thống khác nhau, nên phải tuân thủ chính sách dữ liệu như log.

Baggage càng cần cẩn trọng vì có thể lan truyền sang các service downstream. Thay vì đặt danh tính người dùng vào baggage, hãy dùng trace context chuẩn để nối telemetry và hệ thống phân quyền riêng để truyền thông tin xác thực.

## 9. Sampling, exporter và chi phí vận hành

Tracing có chi phí CPU, bộ nhớ, network và lưu trữ. Một hệ thống có hàng nghìn LDAP requests/giây mà tạo span cho mỗi lookup, bind và modify cần chính sách sampling hợp lý.

**Các cơ chế thường dùng:**

- **Head sampling:** quyết định lưu trace từ đầu dựa trên tỷ lệ hoặc quy tắc đã chọn. Dễ kiểm soát chi phí, nhưng có thể bỏ lỡ các request lỗi hiếm.
- **Tail sampling:** quyết định sau khi quan sát nhiều span, có thể ưu tiên trace lỗi/chậm; cần collector hoặc backend hỗ trợ và có chi phí bộ nhớ/độ trễ riêng.
- **Adaptive sampling:** thay đổi tỷ lệ theo lưu lượng hoặc chính sách hệ thống; cần bảo đảm kết quả điều tra có thể diễn giải.
- **Metrics đầy đủ:** dù lấy mẫu trace thấp, vẫn đo operation count, error rate và latency histogram để giám sát toàn bộ traffic theo khả năng registry.

Ví dụ sampling probability `0.10` trong cấu hình nghĩa là một tỷ lệ trace được chọn theo cơ chế sampling; không có nghĩa chính xác 10% span của mọi operation sẽ hiển thị trong mọi khoảng thời gian nhỏ. Header trace từ upstream, sampler và policy của collector có thể ảnh hưởng kết quả.

### 9.1. Exporter không được làm hỏng luồng xác thực

Khi collector chậm hoặc mất kết nối, telemetry pipeline cần hành vi suy giảm có kiểm soát: queue/batch hữu hạn, timeout export và ghi nhận số span bị drop. Không để một thao tác đăng nhập phải chờ hệ thống lưu trace hoàn tất trước khi trả kết quả. Vì vậy cần theo dõi:

- Số span xuất, bị drop hoặc retry (nếu SDK/exporter cung cấp);
- Dung lượng buffer, lỗi kết nối collector và độ trễ export;
- Tỷ lệ sampling, storage retention và quyền truy cập backend;
- Tải CPU/bộ nhớ tăng thêm khi instrument nhiều spans hoặc attributes.

Nếu dùng Java agent và Micrometer cùng lúc, xác định người tạo observation, người tạo span và người export để tránh **double instrumentation**. Tracing tự thân phải được kiểm thử tải, không chỉ đúng hình dạng cây span.

## 10. Đọc waterfall trace để tìm nút thắt

Xét một trace giả định của API tra cứu nhóm:

| Span / giai đoạn | Bắt đầu tương đối | Kết thúc | Duration |
| --- | ---: | ---: | ---: |
| HTTP GET /api/groups | 0 ms | 850 ms | 850 ms |
| `directory.groups.lookup` | 30 ms | 790 ms | 760 ms |
| LDAP search attempt 1 | 45 ms | 260 ms | 215 ms |
| Backoff giữa hai attempts | 260 ms | 410 ms | 150 ms |
| LDAP search attempt 2 | 410 ms | 745 ms | 335 ms |
| Mapping / authorization sau search | 745 ms | 790 ms | 45 ms |

Dữ liệu chỉ để minh họa. Kết luận đáng tin cậy từ waterfall:

1. LDAP attempt đầu thất bại, attempt thứ hai hoàn tất sau một khoảng backoff.
2. Thời gian **service span** gồm nhiều đoạn, nên không được cộng service 760 ms + LDAP 215 ms + LDAP 335 ms để giải thích tổng.
3. HTTP span còn phần thời gian ngoài service (định tuyến, xử lý controller, serialization, middleware...).
4. Nếu LDAP attempt 2 dài 335 ms, chưa thể khẳng định 335 ms do LDAP server tính toán: có thể gồm pool borrow, TLS, network và mapping.
5. Nếu retry được đặt trong service nhưng không tạo span riêng cho mỗi attempt, một span lớn có thể che giấu khoảng backoff và nguyên nhân tăng p95.

### 10.1. Ma trận chẩn đoán

| Quan sát trong trace | Giả thuyết ưu tiên | Cách kiểm chứng độc lập |
| --- | --- | --- |
| HTTP chậm, service span nhỏ | Delay ở lớp HTTP, queue, serialization hoặc logic khác | HTTP metrics, thread dump, profiler, log |
| Service chậm, LDAP span ngắn | Logic nghiệp vụ, cache lock, gọi dịch vụ khác hoặc khoảng chờ chưa instrument | Trace các đoạn có ý nghĩa, log thời gian |
| LDAP span chậm; pool pending cao | Chờ borrow context hoặc pool saturation | Metric pool borrow/active/pending thật |
| LDAP span chậm; server search cũng chậm | Filter, index, search scope hoặc server quá tải | LDAP server log/search metrics, query plan nếu hỗ trợ |
| Bind error; network vẫn ổn | Credential bị từ chối, tài khoản bị khóa hoặc secret rotation | Authentication result code, audit log được bảo vệ |
| Search error nhưng không phải `not found` | ACL, schema, base DN, TLS hoặc mạng | Exception cause/result code + server log |
| Modify span error sau mất kết nối | Commit state phía server chưa xác định | Đọc lại entry có kiểm soát và kiểm tra audit/replication |
| Traces bị tách sau `@Async` | Thiếu context propagation | Kiểm tra executor và context decorator |

Những hành động này sử dụng trace như **đầu mối điều tra**, sau đó xác minh bằng metric và log đúng tầng. Trace một request không thay thế thống kê trên nhiều instance hoặc một phép kiểm thử quyền truy cập.

## 11. Đồng bộ tracing với timeout, retry và connection pool

Một lời gọi LDAP có nhiều giới hạn độc lập:

- `com.sun.jndi.ldap.connect.timeout`: thời gian cố gắng tạo kết nối TCP mới ở JNDI provider.
- `com.sun.jndi.ldap.read.timeout`: thời gian chờ đọc phản hồi LDAP trên socket.
- `SearchControls.setTimeLimit(...)`: giới hạn thời gian cho search theo provider/server.
- Pool borrow timeout: thời gian mượn context/connection nếu pool hỗ trợ.
- Application deadline: hạn chót của một công việc nghiệp vụ hoặc HTTP request.

Không có một giá trị nào trong danh sách trên tự bảo đảm **tổng thời gian service call** tuyệt đối. Tracing giúp phát hiện giai đoạn nào sử dụng ngân sách, nhưng không thay thế timeout thật tại những tầng đó.

### 11.1. Retry: mỗi attempt cần quan sát riêng

Nếu thao tác tìm kiếm thất bại vì lỗi mạng tạm thời rồi được thử lại, ghi nhận:

- Một service span cho toàn bộ công việc;
- Một LDAP span cho mỗi attempt thực tế;
- Outcome và nhóm lỗi của attempt đầu;
- Khoảng backoff (có thể là annotation/event có giới hạn hoặc khoảng trống trên waterfall);
- Số attempts tổng cộng và kết quả cuối;
- Thời gian end-to-end phục vụ SLO.

Chỉ retry khi lỗi có khả năng hồi phục và thao tác an toàn. Ví dụ search chỉ đọc có thể retry có giới hạn; `modify` hoặc `delete` có thể đã commit trước khi client gặp timeout nên không được tự động gửi lại. Không xem `invalidCredentials`, ACL denied, TLS certificate mismatch hoặc schema error là lỗi mạng tạm thời để retry.

### 11.2. Connection pool và trace context

Khi LDAP operation đi qua pool, việc mượn context có thể là nút thắt. Nếu có API pool thực sự, đo borrow latency ở ranh giới đó và tạo span `directory.pool.borrow` khi cần phân tích. **Không đặt tên span là “TCP connect” nếu thực tế bạn đang đo pool borrow**.

Với JNDI pooling qua `LdapContextSource.setPooled(true)`, thư viện không mặc nhiên cung cấp chi tiết active/pending/borrow cho trace. Nếu dùng `PoolingContextSource` hoặc một pool cụ thể, hãy instrument API của chính pool đó hoặc sử dụng telemetry do nó cung cấp. Không ghi số liệu giả bằng cách suy đoán số kết nối từ số LDAP operations đang chạy.

Connection cũ bị đóng sau idle có thể gây lỗi ở attempt đầu. Trace có thể cho thấy attempt đầu chậm rồi retry thành công, nhưng cần server log/pool metrics để chứng minh stale connection là nguyên nhân.

## 12. Bài thực hành: quan sát request từ HTTP tới LDAP

**Bối cảnh:** một ứng dụng Spring Boot có endpoint `GET /api/users/{id}` dùng Spring LDAP để tìm `cn` và endpoint test riêng cho xác thực bằng bind. Một luồng có thể thực hiện modify trên entry dữ liệu giả trong môi trường thử nghiệm. Tracing được xuất tới OpenTelemetry Collector và hiển thị ở backend có waterfall như Jaeger hoặc Grafana Tempo.

**Chuẩn bị:**

1. Tạo directory test với LDAPS/StartTLS hợp lệ, dữ liệu giả, ACL tối thiểu và secret được quản lý an toàn.
2. Bật Actuator và tracing bridge/exporter tương thích với phiên bản Boot.
3. Chọn sampling 100% **chỉ ở môi trường lab có lưu lượng thấp**, bảo vệ collector/backend.
4. Tích hợp `ObservedLdapOperations` và `DirectoryUserService` trong một HTTP endpoint.
5. Gọi endpoint và tìm trace có HTTP → service → LDAP child span.
6. Thêm một tác vụ dùng `directoryTaskExecutor` nếu cần kiểm tra context propagation.

### 12.1. Ma trận kiểm thử

| Ca | Kịch bản | Kết quả quan sát mong đợi |
| --- | --- | --- |
| T1 | Search theo `uid` tồn tại | Một trace HTTP, child service và LDAP search; outcome success |
| T2 | Search hợp lệ trả zero entry | Search success; nghiệp vụ có thể trả not found, không tự coi LDAP down |
| T3 | DN/base/filter sai trong lab | Span error được ghi; loại lỗi được xác định từ exception/result code |
| T4 | LDAP TCP timeout | LDAP span có error và latency tương ứng; HTTP outcome theo contract |
| T5 | Chứng chỉ TLS không được tin cậy | Lỗi TLS hiện diện; không đưa certificate private key vào span |
| T6 | Bind sai credential | Bind span ghi client error; không ghi password/DN người dùng |
| T7 | Bind thành công | Span bind thành công và context được đóng đúng |
| T8 | Modify entry giả thành công | Span modify thành công; dữ liệu thực sự thay đổi |
| T9 | Mất response sau modify trong lab | Span có client error; commit status chưa rõ, phải đối chiếu |
| T10 | Search lỗi tạm thời rồi retry thành công | Một logical trace chứa hai LDAP attempt spans cùng trace ID |
| T11 | Dùng `ThreadPoolTaskExecutor` nhưng bỏ decorator | Có thể mất context; thấy span con bị tách trace |
| T12 | Bật context propagation đúng | Span trong worker thread gắn vào trace theo thiết kế |
| T13 | Trace sampler 10% | Một số request không có trace lưu; metrics tổng thể vẫn hoạt động |
| T14 | Collector tạm không sẵn sàng | Ứng dụng vẫn xử lý LDAP theo hợp đồng; exporter ghi lỗi/drop phù hợp |
| T15 | Gọi với 500 `uid` khác nhau | Trace attributes không chứa `uid` hay filter; tập nhãn ổn định |
| T16 | Java agent và Micrometer cùng bật instrumentation | Kiểm tra không tạo hai span trùng cùng một attempt |

**Lưu ý an toàn:** mọi tình huống cố tình gây timeout, mất kết nối, sửa entry hoặc chứng chỉ lỗi phải diễn ra trong môi trường thử nghiệm được kiểm soát; không thao tác lên thư mục production để tạo lỗi phục vụ tracing.

### 12.2. Cách kiểm tra tính đầy đủ

Với một trace mẫu, lập bảng:

| Thuộc tính kiểm tra | Mục tiêu |
| --- | --- |
| Trace ID | HTTP span, service span và LDAP attempt thuộc cùng một trace |
| Parent/child | Quan hệ thể hiện đúng call stack hoặc context được truyền qua async |
| Span name | Ngắn, ổn định và phản ánh ranh giới xử lý |
| Duration | Không âm, có thể đối chiếu với metrics/logs ở đúng tầng |
| Outcome | Phân biệt search zero result, auth failed và network error |
| Attributes | Không chứa danh tính, DN, filter, password hay dữ liệu LDAP nhạy cảm |
| Retry attempts | Đếm đúng số lần thử thực tế, không cộng nhầm parent span |
| Collector/export | Traces chỉ lưu theo sampling và policy được cấu hình |

### 12.3. Tự đánh giá

1. Vì sao span bao `LdapTemplate.search(...)` không chứng minh LDAP server xử lý search trong đúng bằng duration của span?
2. Nếu HTTP span và LDAP span có trace ID khác nhau sau `@Async`, điều gì cần kiểm tra?
3. Có nên gắn nguyên LDAP filter `(uid=alice@example.org)` vào span để dễ tìm trace không? Vì sao?
4. Vì sao một modify span error không bảo đảm entry chưa đổi?
5. Nếu sampling chỉ lưu 10% trace, bạn sẽ dùng nguồn dữ liệu nào để tính tỷ lệ lỗi và p95 toàn dịch vụ?
6. Khi xuất hiện hai child spans cùng tên `directory.ldap.operation` với cùng thời gian bắt đầu, làm sao phân biệt retry thật với double instrumentation?

**Tiêu chí hoàn thành:** quan sát được đường đi HTTP → service → LDAP; tracing context còn nguyên qua thread/executor cần dùng; lỗi được thể hiện đúng ý nghĩa; payload nhạy cảm không bị ghi; trace giúp xác định đoạn chậm và được kiểm chứng bằng metric/log server; hoạt động exporter không chặn đường xử lý nghiệp vụ.

## 13. Checklist vận hành

- [ ] Cấu hình tracing pipeline và xác minh HTTP server span thực sự xuất tới backend.
- [ ] Có service span và LDAP operation span tại đúng ranh giới được đo.
- [ ] Phân biệt bind tường minh với service bind ngầm do `ContextSource`/pool thực hiện.
- [ ] Mỗi retry attempt có span riêng; không nhân đôi span do instrumentation trùng.
- [ ] Các label/attributes thuộc allowlist cố định: operation, query kind, backend và outcome.
- [ ] Không ghi password, cookie, token, DN cá nhân, email, filter thực hoặc LDAP attributes nhạy cảm.
- [ ] Traces được bảo vệ bằng quyền truy cập, retention và sampling phù hợp.
- [ ] Bảo đảm context propagation qua `@Async`, executor, Reactor và các transport khi thực sự sử dụng.
- [ ] Không giả định LDAP server có thể đọc/tiếp nhận W3C trace context nếu giao thức/hạ tầng không hỗ trợ.
- [ ] Đo pool borrow thực tế nếu có API; không gọi tổng thời gian client là server-side latency.
- [ ] Xác nhận timeout, retry, referral và paging tạo số spans phù hợp với số thao tác thực.
- [ ] Không retry write khi commit status chưa rõ; đối chiếu entry/server audit log.
- [ ] Exporter có batch/queue/timeout và cách suy giảm an toàn khi collector lỗi.
- [ ] Đã so sánh trace waterfall với metrics SLO và log LDAP server khi chẩn đoán.
- [ ] Các bài thử lỗi chỉ chạy trên LDAP test environment với dữ liệu giả.

Khi tracing **Spring LDAP**, thiết kế hữu ích nhất là **một trace cho luồng nghiệp vụ**, các span có ranh giới thực và metadata đã kiểm soát, đồng thời biết rõ phần nào client quan sát được và phần nào cần số liệu từ directory server. Cách tiếp cận này giúp khoanh vùng chậm trễ, kết nối lỗi và sai lệch trong luồng xác thực hoặc cập nhật dữ liệu mà vẫn giữ an toàn thông tin thư mục.
