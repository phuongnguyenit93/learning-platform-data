# Liên kết dấu vết yêu cầu với thao tác LDAP

Trong **Spring Data LDAP**, một HTTP request có thể dẫn tới nhiều thao tác LDAP: tìm người dùng theo `uid`, đọc nhóm bằng `member`, xác thực tài khoản, sửa thuộc tính hoặc cập nhật DN. Khi endpoint phản hồi chậm hoặc báo lỗi, chỉ biết “LDAP thất bại” là chưa đủ; người vận hành cần trả lời được **request nào đã gọi thao tác LDAP nào, tốn bao lâu, lỗi ở tầng nào và phần nào cần tối ưu**.

**Distributed tracing** (theo dõi dấu vết phân tán) cung cấp cấu trúc `trace` và `span` để liên kết các bước này. Trong hệ sinh thái Spring, **Micrometer Observation + Micrometer Tracing** giúp tạo span cho HTTP, ghi nhận thời gian và chuyển thông tin tương quan vào log; **Spring LDAP 3.3 trở lên** còn có hỗ trợ quan sát các lời gọi `DirContext`. Khi cấu hình đúng, một thao tác truy vấn từ `LdapRepository` hoặc `LdapTemplate` có thể xuất hiện như span con của request đang xử lý.

Bài này tập trung vào cách **liên kết trace request với thao tác LDAP**, không chỉ bật logging. Nội dung bao gồm mô hình trace, cấu hình instrumentation, ví dụ Java, chuẩn đặt metadata an toàn, trường hợp bất đồng bộ và cách đối chiếu log ứng dụng với log directory server.

Sau bài học, bạn có thể:

- Phân biệt `traceId`, `spanId`, parent–child span, log correlation và metric.
- Bật quan sát LDAP qua `ContextSourceObservationPostProcessor` hoặc `ObservationContextSource` ở phiên bản Spring LDAP hỗ trợ.
- Tạo observation nghiệp vụ cho lời gọi `LdapTemplate.search(...)` mà không nhân đôi không cần thiết các span mức thấp.
- Thiết kế tên thao tác, tag và log **ít cardinality, không lộ DN/filter/credential nhạy cảm**.
- Giải thích ranh giới: LDAP **không tự mang W3C `traceparent`** như HTTP; chỉ có thể đối chiếu log server bằng cơ chế riêng.
- Kiểm thử trace khi có lỗi xác thực, timeout, pool cạn, thao tác đa bước hoặc chuyển thread.

## 1. Một trace đi từ HTTP đến LDAP như thế nào?

Giả sử client gọi endpoint để xem hồ sơ Lan:

```http
GET /api/directory/users/lan
```

Luồng xử lý có thể là:

```text
Client
  │ GET /api/directory/users/lan
  ▼
Spring MVC Controller
  │
  ▼
DirectoryService.findPerson("lan")
  │
  ├── PersonRepository.findByUid("lan")
  │      └── Spring LDAP / DirContext.search(...)
  │
  └── LdapTemplate.search(...) để kiểm tra nhóm
         └── DirContext.search(...)
                   │
                   ▼
               LDAP server
```

Trong bộ theo dõi trace, mục tiêu là thấy:

```text
TraceId: aaaa1111... (ví dụ giả định)

http.server.requests            180 ms  [server span]
└── directory.get-user          160 ms  [business observation, tùy chọn]
    ├── spring.ldap.dir.context.operations   35 ms  [search]
    └── spring.ldap.dir.context.operations   62 ms  [search]
```

Sơ đồ và thời gian đều **giả định để minh họa**. Một trace mô tả một hành trình logic; mỗi **span** mô tả một công đoạn có thời gian và trạng thái riêng. Các span của cùng trace thường chia sẻ `traceId` nhưng có `spanId` khác nhau. Quan hệ `parentSpanId` giải thích vì sao thao tác LDAP thuộc request ban đầu.

### 1.1. Từ vựng cần phân biệt

| Khái niệm | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| `traceId` | Liên kết các span của một luồng xử lý | Cùng ID trong HTTP span, business span và LDAP span |
| `spanId` | Định danh **một công đoạn** trong trace | Span search LDAP khác span gọi controller |
| Parent span | Cho biết span nào gọi công đoạn hiện tại | LDAP search là con của bước xử lý request |
| Span duration | Đo thời gian một công đoạn | Search LDAP mất 35 ms |
| Span attributes/tags | Mô tả loại thao tác, kết quả, endpoint ở mức an toàn | `ldap.operation=search` |
| Span error/event | Ghi ngoại lệ hoặc sự kiện cần điều tra | Communication error khi search |
| MDC/log correlation | Gắn `traceId`/`spanId` vào dòng log | Tìm log của request tương ứng |
| Metric | Theo dõi xu hướng và phân vị trên nhiều request | p95 thời gian search LDAP |

**Trace không phải audit log**: trace có thể được sampling, không đảm bảo giữ mọi sự kiện ghi/xóa; audit cần luồng ghi sự kiện độc lập, chống chỉnh sửa phù hợp và chính sách bảo quản riêng.

### 1.2. Tại sao log có thời gian mà vẫn khó điều tra?

Các dòng log đơn lẻ:

```text
10:01:00 Search started
10:01:00 Search completed
10:01:00 HTTP request failed
```

không cho biết chúng thuộc request nào khi hàng trăm request đang chạy đồng thời. Với correlation:

```text
traceId=8a7... spanId=1b2... event=http_request_started route=/api/directory/users/{uid}
traceId=8a7... spanId=2c3... event=ldap_search_completed operation=search durationMs=35
traceId=8a7... spanId=1b2... event=http_request_completed status=200
```

Phần `route` nên là **mẫu đường dẫn** chứ không chứa `uid` thật. `traceId` có thể giúp truy hồi log và span, nhưng **không phải bằng chứng danh tính người dùng** và không thay thế quyền kiểm soát truy cập vào log.

## 2. Cấu trúc instrumentation trong Spring Data LDAP

Một ứng dụng có thể sử dụng repository hoặc `LdapTemplate`:

```text
HTTP server observation
        │
        ▼
DirectoryService (tùy chọn observation nghiệp vụ)
        │
        ▼
PersonRepository / LdapTemplate
        │
        ▼
ContextSource
        │
        ▼
DirContext.search / getAttributes / modifyAttributes ...
        │
        ▼
LDAP server
```

**Micrometer Observation** ghi lại lifecycle của công đoạn: bắt đầu, mở scope, kết thúc và lỗi. Khi ứng dụng cấu hình **Micrometer Tracing bridge** và exporter, các observation phù hợp được xuất thành span. Cần có cả hai phần: một `ObservationRegistry` và các handler/tracer để observation trở thành trace có thể xem trong Zipkin, Jaeger hoặc backend OTLP tương thích.

Ở phiên bản **Spring LDAP 3.3+**, thư viện hỗ trợ quan sát thao tác ở tầng `DirContext` thông qua `ObservationContextSource`. Đây là điểm mấu chốt: thay vì phải chèn tracing vào từng phương thức repository, ứng dụng có thể **bọc chính nguồn cấp context** mà repository và template sử dụng.

### 2.1. Spring LDAP tự động tạo span hết chưa?

**Không nên mặc định là có.** Việc ứng dụng đã thêm Spring Data LDAP và Micrometer chưa chứng minh bean `ContextSource` đang được bọc bằng instrumentation.

Kiểm tra cụ thể:

1. Phiên bản Spring LDAP có `ObservationContextSource`/`ContextSourceObservationPostProcessor` hay không (**từ 3.3**).
2. Dự án đã bật Spring Boot Actuator/Tracing và có `ObservationRegistry`/tracing handler/exporter hay chưa.
3. `ContextSource` mà `LdapTemplate` và repository thực sự sử dụng có được bọc đúng không.
4. Request đang được lấy mẫu (sampled) và exporter đang gửi dữ liệu tới backend không.
5. Có thao tác LDAP chạy ngoài request hoặc ở thread khác nên không có parent span hay không.

Ngay cả khi tracing đã bật, **LDAP server không đương nhiên nhận được trace context từ client**. Các span LDAP ở đây trước hết đo **thao tác phía ứng dụng**.

## 3. Cấu hình Spring LDAP Observation với Spring Boot

### 3.1. Cách ngắn nhất: BeanPostProcessor

Tài liệu chính thức của Spring LDAP hướng dẫn đăng ký `ContextSourceObservationPostProcessor`. Với phiên bản Spring LDAP hỗ trợ:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.ContextSourceObservationPostProcessor;

@Configuration(proxyBeanMethods = false)
public class LdapObservationConfiguration {

    @Bean
    static ContextSourceObservationPostProcessor
    ldapContextSourceObservationPostProcessor(
            ObjectProvider<ObservationRegistry> registries) {
        return new ContextSourceObservationPostProcessor(registries);
    }
}
```

**Vì sao bean dùng `static`?** Đó là cách tài liệu Spring LDAP minh họa việc đăng ký một `BeanPostProcessor` sớm trong vòng đời khởi tạo bean. Khi Spring Boot cung cấp `LdapContextSource`, processor có thể bọc nó thành `ObservationContextSource` để các lệnh `DirContext` sinh observation.

Tác dụng mong muốn:

```text
Spring Boot tạo LdapContextSource
            │
            ▼
ContextSourceObservationPostProcessor
            │ wraps
            ▼
ObservationContextSource
            │ cấp DirContext được quan sát
            ▼
LdapTemplate / Spring Data LDAP Repository
```

**Kiểm chứng wiring**, không chỉ nhìn thấy bean trong context. Nếu ứng dụng có nhiều `ContextSource`, pool connection, proxy transaction hoặc custom initialization, cần xác định bean thực tế mà từng `LdapTemplate` sử dụng và bảo đảm **không bọc observation lặp hai lần**.

### 3.2. Với ContextSource tự xây dựng

Khi ứng dụng không dùng Boot auto-configuration hoặc tự cấu hình nhiều nguồn LDAP, có thể bọc trực tiếp một `BaseLdapPathContextSource`:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.core.support.ObservationContextSource;

@Configuration
public class CustomLdapConfiguration {

    @Bean
    public ContextSource contextSource(
            ObservationRegistry registry,
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) throws Exception {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase("dc=example,dc=org");
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.afterPropertiesSet();

        // Chỉ chọn cách bọc thủ công NẾU không dùng post-processor ở trên.
        return new ObservationContextSource(source, registry);
    }

    @Bean
    public LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Các property `app.ldap.*` chỉ là **tên ví dụ của ứng dụng**, không phải những key Spring Boot tự tạo. Cần cấu hình kết nối mã hóa TLS hợp lệ, không hardcode password. Khi bọc nguồn cấp context bằng cách thủ công, xem xét lifecycle của `LdapContextSource` do bạn khởi tạo; ví dụ gọi `afterPropertiesSet()` để thiết lập các giá trị đã cấu hình.

**Chỉ chọn một chiến lược wiring** trong cùng đường gọi: post-processor **hoặc** wrapper thủ công, trừ khi đã chủ động thiết kế cách kết hợp. Nếu cả hai cùng bọc một context, hệ thống có thể tạo các span trùng nhau và làm méo số liệu.

### 3.3. Kết hợp với connection pool

Spring LDAP có thể dùng `PooledContextSource` để tái sử dụng `DirContext`. Khi triển khai pool và observability, cần biết chính xác **thứ tự các wrapper**:

```text
Ứng dụng
  └── LdapTemplate
      └── ObservationContextSource
          └── PooledContextSource
              └── LdapContextSource
                  └── LDAP server
```

Hoặc thư viện/bean factory có thể tạo sơ đồ khác. Điểm cần kiểm tra là **mọi lời gọi LDAP mong muốn đều đi qua wrapper quan sát**, không chỉ quá trình mượn context. Một thao tác mượn pool lâu và một truy vấn server chậm có nguyên nhân khác nhau; observation ở `DirContext` chủ yếu đo thao tác LDAP trên context, **không nhất thiết đo đầy đủ thời gian chờ pool hoặc connect/bind**. Cần theo dõi pool riêng.

## 4. Span và tag mà Spring LDAP cung cấp

Theo tài liệu quan sát Spring LDAP, observation có tên:

```text
spring.ldap.dir.context.operations
```

và contextual name minh họa là `perform operation`. Metadata ví dụ của thư viện có:

| Dữ liệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `operation` | `get.attributes` | Loại lời gọi trên `DirContext` |
| `base` | `dc=example,dc=org` | Base DN cấu hình cho directory |
| `urls` | `[ldaps://directory.example.org:636]` | Endpoint LDAP được cấu hình |
| `name` | `uid=lan,ou=people` | Tên entry trong thao tác, có thể nhạy cảm |
| `attribute.ids` | Danh sách attribute nếu có | Thuộc tính được yêu cầu/truy cập |

Các trường phụ thuộc **phiên bản và loại thao tác thực tế**; tài liệu Spring LDAP phân loại một số trường như **low-cardinality** (ví dụ operation/base/urls), một số là **high-cardinality** (ví dụ tên entry). **Không sao chép nguyên cấu hình telemetry vào production mà không rà soát rò rỉ dữ liệu.**

Chẳng hạn, `name=uid=lan,ou=people` chứa định danh người dùng; `base` hoặc `urls` có thể tiết lộ cấu trúc tổ chức/hạ tầng. Số lượng giá trị khác nhau còn ảnh hưởng kích thước và chi phí lưu trữ hệ thống giám sát.

### 4.1. Nếu đã có span mức thấp, có cần thêm span ở service?

Có thể thêm **observation nghiệp vụ** khi cần biết thao tác logic như “tìm hồ sơ” bao gồm hai hay ba LDAP operation:

```text
HTTP GET /api/directory/users/{uid}
└── directory.get-person
    ├── spring.ldap.dir.context.operations  (search user)
    └── spring.ldap.dir.context.operations  (search group)
```

Quan sát nghiệp vụ giúp thấy **toàn bộ thời gian xử lý logic**, còn observation của Spring LDAP đo **từng thao tác LDAP**. Nếu chỉ cần latency của các lệnh LDAP, không nên tạo một span service trùng tên/mục đích với span tự sinh rồi khiến dashboard khó diễn giải.

## 5. Tạo observation nghiệp vụ bằng Micrometer

Ví dụ một service truy vấn theo `uid`. `ObservationRegistry` đã được Spring Boot cấu hình với tracing handlers:

```java
import java.util.List;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryProfileService {
    private final LdapTemplate ldapTemplate;
    private final ObservationRegistry observationRegistry;

    public DirectoryProfileService(
            LdapTemplate ldapTemplate,
            ObservationRegistry observationRegistry) {
        this.ldapTemplate = ldapTemplate;
        this.observationRegistry = observationRegistry;
    }

    public List<String> findNamesByUid(String uid) {
        Observation observation = Observation
                .createNotStarted("directory.get-person", observationRegistry)
                .contextualName("lookup directory person")
                .lowCardinalityKeyValue("directory.operation", "find-person")
                .lowCardinalityKeyValue("directory.branch", "people");

        return observation.observe(() -> {
            LdapQuery query = LdapQueryBuilder.query()
                    .base("ou=people")
                    .attributes("cn")
                    .where("objectClass").is("inetOrgPerson")
                    .and("uid").is(uid);

            return ldapTemplate.search(query,
                    (AttributesMapper<String>) attrs ->
                            (String) attrs.get("cn").get());
        });
    }
}
```

**Điều bài học thể hiện:**

- `Observation.createNotStarted(...)` tạo một observation riêng cho thao tác nghiệp vụ.
- `.observe(() -> ...)` mở scope, thực thi lambda và ghi lỗi/đóng scope/kết thúc observation theo lifecycle Micrometer.
- Trong thread request có **active HTTP observation**, observation nghiệp vụ nằm dưới HTTP span; nếu `ContextSource` được bọc bởi `ObservationContextSource`, các thao tác `DirContext` có thể tạo span con của observation nghiệp vụ.
- `directory.operation=find-person` và `directory.branch=people` là những tag **có tập giá trị hữu hạn**. Không đưa `uid` nhận từ request vào tag low-cardinality.
- `LdapQueryBuilder` escape giá trị `uid` dùng trong equality filter, giảm nguy cơ LDAP filter injection.

Giả định `ContextSource` có base `dc=example,dc=org` nên `.base("ou=people")` là nhánh tương đối. Đoạn mã minh họa mục tiêu tracing, không xử lý đầy đủ các trường hợp attribute `cn` bị ẩn/thiếu; trong ứng dụng thật cần kiểm tra `null` và logic lỗi nghiệp vụ.

**Không tự tạo observation khác ở chính đoạn `ldapTemplate.search`** khi Spring LDAP đã tạo span cho `DirContext.search`, trừ khi bạn cố ý cần một lớp metric độc lập. Dùng hai cấp quan sát chỉ khi có ý nghĩa nghiệp vụ khác nhau.

## 6. Kết nối log với traceId và spanId

Khi Spring Boot cấu hình **Micrometer Tracing**, các context tracing có thể đưa `traceId`/`spanId` vào **Mapped Diagnostic Context (MDC)** của hệ thống logging. Spring Boot có cấu hình correlation ID, nhờ đó log của HTTP request và log do code LDAP service ghi có thể tìm theo cùng trace ID.

Ví dụ logging ở **mức nghiệp vụ**, không ghi dữ liệu cá nhân:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger log =
        LoggerFactory.getLogger(DirectoryProfileService.class);

// Gọi bên trong scope Observation:
log.info("directory_lookup_completed operation=find-person branch=people count={}",
        people.size());
```

Khi MDC được cấu hình và context hiện hành tồn tại, logger có thể ghi một dòng tương tự:

```text
[traceId=aaa... spanId=bbb...] INFO directory_lookup_completed
    operation=find-person branch=people count=1
```

**Không tự đưa `uid`, DN người dùng, full LDAP filter, password, group membership nhạy cảm hoặc LDAP response vào log** chỉ để điều tra nhanh. Nhiều hệ thống log được lưu lâu và cho nhiều nhóm truy cập; cần phân loại dữ liệu, giới hạn retention, masking và quyền xem.

### 6.1. Vì sao log mất traceId?

MDC thường liên kết với **thread hiện hành** hoặc cơ chế truyền context của framework. Khi code chuyển sang `@Async`, executor tự tạo, thread pool, scheduler hoặc Reactor, span cha có thể không được truyền sang thread mới nếu không bật/cấu hình **context propagation**.

```text
Thread HTTP:     trace=A, span=HTTP
    │ submit task
    ▼
Thread worker:   (mất context)
    └── ldap search => tạo trace B hoặc span không có parent
```

Để bảo đảm cùng trace:

- Sử dụng executor hoặc task decorator được framework **instrumented** để truyền context.
- Với code bất đồng bộ tùy chỉnh, dùng khả năng **Micrometer Context Propagation** và quản lý scope rõ ràng.
- Với Reactor, kiểm tra context propagation và cách đưa observation vào chain; không suy ra ThreadLocal tự đi theo mọi scheduler.
- Kiểm thử thực tế `traceId` ở HTTP span, service span và LDAP span; đừng chỉ kiểm tra log ở controller.

Không tự sao chép MDC bằng một map dùng chung toàn ứng dụng hoặc để ThreadLocal tồn tại sau request: sai scope có thể khiến log của hai người dùng mang cùng định danh.

## 7. Trace nào thực sự đi tới LDAP server?

HTTP dùng các header như `traceparent` trong W3C Trace Context để gửi quan hệ trace giữa dịch vụ với nhau. **LDAP protocol theo RFC 4511 không có cơ chế tiêu chuẩn tương đương HTTP header `traceparent` được Micrometer tự chèn vào mọi search/bind/modify**.

Do đó, cần phân biệt:

```text
HTTP client  --traceparent-->  Spring application
                                  │
                                  ├─ HTTP + service + LDAP CLIENT spans
                                  │  cùng một trace trong ứng dụng
                                  │
                                  └─ LDAP request (RFC 4511)
                                          │
                                          ▼
                                     LDAP server
                              (không mặc định nhận traceId)
```

**Spring LDAP observability trước hết quan sát ở client-side.** LDAP server có thể ghi log access riêng về connection ID, message ID, operation, kết quả, thời gian và địa chỉ kết nối tùy sản phẩm/cấu hình. Không thể mặc định mở LDAP server log là thấy `traceId` của request HTTP.

### 7.1. Đối chiếu client trace với server access log

Khi cần điều tra lỗi khó, có thể đối chiếu:

| Thông tin từ ứng dụng | Thông tin phía LDAP server | Độ tin cậy/giới hạn |
| --- | --- | --- |
| Timestamp của LDAP span | Timestamp của LDAP operation trong access log | Cần đồng bộ clock; có nhiều operation cùng lúc |
| Địa chỉ endpoint/port của context | Socket/connection nhận request | Pool có thể tái sử dụng connection cho nhiều request |
| Loại thao tác `search`/`modify` | Operation type và result code | Cần biết backend format log |
| Khoảng thời gian xử lý | Thời gian server thực thi | Client duration còn có network, pool, scheduling |
| DN hoặc search base đã được **bảo vệ phù hợp** | Base DN/filter trong server log nếu chính sách cho phép | Dữ liệu có thể nhạy cảm; không xuất tùy tiện |
| Request/trace ID trong log ứng dụng | Không có theo mặc định | Chỉ gắn trực tiếp khi có integration tùy biến rõ ràng |

Một máy chủ LDAP có thể có **connection ID + message ID** trong log. Hai giá trị này thường giúp đối chiếu operation **bên trong server**, nhưng **không phải** `traceId`. Nếu client có khả năng log cùng identity connection/message một cách an toàn và provider hỗ trợ, việc đối chiếu sẽ tốt hơn; API `LdapTemplate` thông thường không bảo đảm công khai message ID của mọi LDAP request.

### 7.2. Không dùng LDAP filter làm kênh truyền traceId

Không thêm một điều kiện giả như `(traceId=...)` vào LDAP filter hay chèn trace ID vào DN để “truyền trace”: điều này **thay đổi ngữ nghĩa truy vấn**, có thể trả kết quả sai và tạo rủi ro lộ dữ liệu. Nếu server hỗ trợ extension hoặc control riêng để nhận correlation ID, đó là **tính năng đặc thù vendor** phải được tài liệu hóa và kiểm thử độc lập, không phải khả năng mặc định của Spring Data LDAP.

## 8. Chọn metadata an toàn, có cardinality kiểm soát

Một tag được dùng để phân loại metric/trace nên có ít giá trị có thể xuất hiện. Lập kế hoạch cụ thể:

| Thông tin | Nên đưa vào low-cardinality tag? | Ví dụ/khuyến nghị |
| --- | --- | --- |
| Loại thao tác | **Có** | `search`, `lookup`, `add`, `modify`, `delete`, `rename` |
| Loại nhánh nghiệp vụ | **Có nếu hữu hạn** | `people`, `groups`, `services` |
| Nhóm kết quả | **Có nếu phân loại thô** | `success`, `timeout`, `auth-error`, `other-error` |
| LDAP server logical name | Có nếu được allowlist | `directory-primary`, `directory-secondary` |
| DN đầy đủ của entry | **Không** | Có thể chứa tên/email và có số giá trị rất lớn |
| `uid`, `mail`, principal | **Không** | Dữ liệu định danh người dùng |
| Mật khẩu/bind credential | **Tuyệt đối không** | Secret |
| Raw LDAP filter | **Không** | Chứa input, có thể có PII; cardinality cao |
| Danh sách thành viên nhóm | **Không** | Có thể tiết lộ thông tin phân quyền |
| TraceId | Không đưa vào **metric tag** | Vốn nằm trong trace context; mỗi request là giá trị mới |

**Micrometer phân biệt low-cardinality và high-cardinality key-values.** High-cardinality có thể dành cho trace nhưng **không có nghĩa được tự do lưu PII**; trước khi ghi phải có chính sách rõ về quyền riêng tư, retention, truy cập và redaction. Với tên entry và filter, nhiều trường hợp an toàn nhất là **không thu thập**.

### 8.1. Ghi mô tả filter thay vì nguyên filter

Thay vì:

```text
ldap.filter=(&(objectClass=inetOrgPerson)(uid=lan@example.org))
```

có thể dùng:

```text
ldap.operation=search
ldap.query.kind=person-by-uid
ldap.scope=subtree
ldap.branch=people
```

Các tag này mô tả mục đích và cấu trúc, giúp phân tích p95/p99 theo loại truy vấn mà không ghi giá trị đầu vào. Nếu muốn phân biệt lỗi do `uid` không tồn tại, dùng mã kết quả nghiệp vụ phân loại chung thay vì log ID cụ thể.

## 9. Phân biệt LDAP timeout, lỗi mạng, lỗi quyền và pool cạn

Một HTTP endpoint có thể chậm vì nhiều nguyên nhân khác nhau:

```text
HTTP request 500 ms
├── Chờ lấy context từ pool 250 ms
├── Kết nối/bind hoặc TLS 60 ms
├── LDAP search phía client 160 ms
└── Mapping + business logic 30 ms
```

Đây là **ví dụ số liệu giả định**, không phải phân rã mặc định mà Spring LDAP tự thu thập. Một observation quanh phương thức service có thể đo tổng thời gian; observation ở `DirContext` đo thời gian của các method LDAP, nhưng **không chắc bao gồm cả thời gian chờ pool**. Để biết chi tiết, cần có metric/tracing bổ sung tại tầng pool và kết nối.

| Triệu chứng | Điểm cần kiểm tra | Không nên suy luận |
| --- | --- | --- |
| HTTP chậm, LDAP span ngắn | Chờ pool, mapping, HTTP downstream, thread scheduling | “LDAP server chắc chắn chậm” |
| LDAP span chậm | Filter, index, search base/scope, network/read timeout, server tải cao | “Thêm pool sẽ xử lý mọi trường hợp” |
| Không có LDAP span | Thiếu instrumentation, không sampled, async context mất, đường code không gọi LDAP | “Ứng dụng không dùng LDAP” |
| Lỗi `CommunicationException` | Mạng, TLS, server đóng kết nối, read timeout | “Mật khẩu sai” |
| Lỗi xác thực/bind | Credential, trạng thái tài khoản, ACL/chính sách | “Máy chủ hỏng” |
| Timeout mượn context | Pool cạn, context chưa được trả, request đồng thời cao | “Search thiếu index” |
| `NameNotFoundException` | DN/search base/entry không tồn tại hoặc bị chính sách che giấu | “Hạ tầng tracing bị mất” |

**Ghi nhận lỗi theo lớp:** đo trạng thái operation, loại exception và một nhóm error code hữu hạn; không log nguyên stack trace kèm thông tin nhạy cảm theo mặc định. Nếu cần lưu stack trace cho chẩn đoán, áp dụng cơ chế lọc và phân quyền phù hợp.

## 10. Theo dõi nhiều LDAP operation trong cùng một request

Một use case có thể gồm nhiều bước:

```text
GET /api/directory/profiles/{uid}
  1. Search uid → tìm DN người dùng
  2. Lookup DN → đọc attribute hồ sơ
  3. Search groupOfNames → kiểm tra membership
  4. Assemble DTO → phản hồi JSON
```

Trong trace:

- Mỗi thao tác `DirContext` mong muốn có span riêng nếu instrumentation được bật.
- Một observation nghiệp vụ ở service bao phủ **toàn bộ quy trình** nếu muốn phân biệt thời gian logic so với thời gian server/client.
- Nếu bước 3 bị lỗi, HTTP response có thể vẫn thành công một phần theo chính sách sản phẩm, nên **span error và business outcome không tự đồng nghĩa**.
- Dùng span name ổn định; không đặt tên span theo `uid` hoặc DN của từng request.

### 10.1. Trường hợp ghi thay đổi LDAP

Thao tác `Add`, `Modify`, `Delete` và `Modify DN` có thể tạo span riêng, nhưng **trace không làm các thao tác trở thành transaction**. Nếu service thực hiện:

```text
Add user → Modify group member → Rename user
```

và bước cuối thất bại, hai bước trước có thể đã thành công. Trace giúp nhìn thứ tự và nguyên nhân; xử lý phục hồi phải dựa trên **trạng thái directory**, không phải chỉ kết luận từ span thất bại.

Khi `LdapRepository.save(...)` gọi tới `LdapTemplate`/ODM, vẫn cần kiểm tra operation thực tế. Đặc biệt, cập nhật entity có DN thay đổi có thể khác với một Modify DN tường minh. Không đặt tên span `rename` chỉ vì code sửa một field Java mà chưa biết thao tác LDAP được thực thi là gì.

## 11. Sampling và khả năng đối chiếu log

**Sampling** chỉ giữ một phần trace để kiểm soát lượng dữ liệu. Nếu sampling ở mức 10%, phần lớn request sẽ **không có trace đầy đủ trong backend**, dù ứng dụng vẫn hoạt động. Trong môi trường test, có thể tạm tăng tỉ lệ lên 100% để kiểm chứng instrumentation:

```yaml
# Cấu hình mẫu Spring Boot khi kiểm tra, không nên giữ mặc định ở production.
management:
  tracing:
    sampling:
      probability: 1.0
```

Sau kiểm thử, chọn tỉ lệ theo lưu lượng, chi phí, độ nhạy và mục tiêu quan sát. Với ứng dụng lưu lượng lớn, sampling quá cao có thể làm tăng CPU, băng thông và dung lượng backend.

### 11.1. Lưu ý phiên bản và exporter

- Với Spring Boot/Micrometer tương thích, tích hợp tracing có thể dùng **OpenTelemetry/OTLP** hoặc **Brave/Zipkin**; dependency và cấu hình exporter phụ thuộc **phiên bản Spring Boot** đang chạy.
- Không mặc định một dependency hoặc property trong tài liệu mới hoạt động nguyên xi trên mọi bản Boot 3.x/4.x; kiểm tra dependency management và tài liệu đúng phiên bản.
- Có `ObservationRegistry` nhưng không có tracing handler hoặc exporter thì observation có thể được dùng cho metric mà **không hiện trong tracing backend**.
- Trong một số cấu hình test, tracing exporter không được tự bật; cần đăng ký test handler hoặc cấu hình tracing thích hợp để xác minh span.
- Khi một trace không xuất hiện, trước tiên kiểm tra sampling, exporter, collector và cấu hình quyền/truy cập telemetry backend, rồi mới kết luận instrumentation LDAP bị lỗi.

## 12. Quy trình kiểm thử end-to-end

Thiết lập directory test có dữ liệu giả:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=mai
└── ou=groups
    └── cn=backend
```

**Bước 1 — Bật tracing cho HTTP.** Gửi request `GET /api/directory/users/lan` và xác minh HTTP span xuất hiện trong backend.

**Bước 2 — Bật Spring LDAP observability.** Đăng ký `ContextSourceObservationPostProcessor` hoặc wrapper thủ công. Dùng đúng `ContextSource` của `LdapTemplate` và repository rồi gửi lại request.

**Bước 3 — Xác minh parent-child.** Trong cùng trace, phải thấy LDAP span nằm dưới HTTP span hoặc observation nghiệp vụ, với operation phù hợp. So sánh `traceId` trong log và trace backend; `spanId` từng công đoạn khác nhau.

**Bước 4 — Kiểm tra tag.** Xác minh không có raw DN/user principal/filter/password trong tag do ứng dụng tự thêm. Với các tag mặc định do Spring LDAP sinh ra, kiểm tra có cần điều chỉnh/tắt thu thập trường nhạy cảm theo chính sách tổ chức.

**Bước 5 — Mô phỏng lỗi.** Trong directory test, tạo tình huống DN không tồn tại, quyền đọc bị từ chối và server tạm thời không phản hồi. Kiểm tra span trạng thái lỗi, thông tin exception được phân loại và log correlation phù hợp; bảo đảm secret không bị in ra.

**Bước 6 — Kiểm tra pooling.** Tạo nhiều request đồng thời và đo `active/idle/waiters` của Spring LDAP pool nếu dùng. Xác minh lúc chờ pool tăng nhưng thời gian operation LDAP không nhất thiết tăng tương ứng.

**Bước 7 — Kiểm tra async.** Đưa một lời gọi directory vào executor có context propagation rồi thử executor không được instrumented; đối chiếu `traceId` và quan hệ parent-child.

**Bước 8 — Kiểm tra sampling.** Tạm dùng sampling 100% để xác minh, sau đó giảm về mức vận hành và kiểm tra hệ thống không giả định mọi request đều có trace.

**Bước 9 — Đối chiếu server.** Với quyền truy cập log LDAP server phù hợp, so sánh timestamp, operation và connection ID nếu có; **không kỳ vọng server thấy `traceId`** nếu chưa thiết kế integration riêng.

**Bước 10 — Kiểm thử tính đúng.** Tracing không được thay đổi kết quả tìm kiếm, DN, `objectClass`, filter hoặc ACL. Kiểm thử cả thao tác repository và `LdapTemplate`, bao gồm connection pool, TLS và tình huống bị lỗi.

## 13. Các lỗi quan sát thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| HTTP span có, LDAP span không | Chưa bọc `ContextSource`, framework cũ, sampling hoặc exporter | Kiểm tra phiên bản, bean wiring, tracing handler, backend |
| LDAP span xuất hiện riêng một trace | Context mất khi chuyển thread hoặc tạo scope không đúng | Bật context propagation, kiểm tra observation hiện hành |
| Có hai LDAP span trùng operation/duration | Cùng context bị bọc observation hai lần hoặc tự tạo span trùng | Chọn một cơ chế wrap, phân cấp business span rõ ràng |
| Chỉ có metric mà không có trace | Registry có metrics handler nhưng thiếu tracing bridge/exporter | Cấu hình Micrometer Tracing và exporter |
| Trace không có đủ mọi request | Sampling đang bật hoặc collector drop dữ liệu | Kiểm tra tỉ lệ và pipeline telemetry |
| LDAP server log không có traceId | LDAP không tự nhận `traceparent` qua RFC 4511 | Đối chiếu timestamp/connection ID; không giả định truyền trace |
| Trace chứa email hoặc DN đầy đủ | Tag/log ghi dữ liệu nhận dạng; default instrument có high-cardinality | Rà soát instrumentation, tắt/redact trường không được phép |
| p95 HTTP lớn nhưng LDAP span nhỏ | Chờ pool, bind, network ngoài phần đo hoặc xử lý Java | Bổ sung metric cho pool/kết nối và service |
| Log trong `@Async` thiếu traceId | MDC/context không được truyền | Instrument executor hoặc dùng Context Propagation |
| Exception làm service trả lỗi nhưng span LDAP thành công | Lỗi xảy ra **sau** thao tác LDAP, ví dụ mapping/validation | Tách span LDAP và business span, kiểm tra stack trace phù hợp |
| Tìm trace theo `uid` không được | Chính sách không gắn uid vào trace vì PII/cardinality | Tìm theo correlation ID/request ID đã cho phép, khoảng thời gian và operation |

## 14. Câu hỏi tự luyện

**Câu 1.** Một endpoint có HTTP span nhưng không có LDAP span dù gọi `LdapTemplate.search`. Bạn sẽ kiểm tra gì đầu tiên?

*Đáp án gợi ý:* Spring LDAP version, `ContextSource` đã được bọc bằng `ObservationContextSource` hay chưa, `ObservationRegistry`/tracing handler/exporter, sampling và việc context có bị mất qua async không.

**Câu 2.** `traceId` và `spanId` khác nhau thế nào khi một request gọi hai LDAP operation?

*Đáp án gợi ý:* Các span thuộc cùng trace chia sẻ `traceId`; mỗi span (HTTP, nghiệp vụ, LDAP operation) có `spanId` khác và quan hệ parent-child.

**Câu 3.** Có nên thêm `uid=lan` vào `lowCardinalityKeyValue("uid", uid)` để dễ tìm trên dashboard?

*Đáp án gợi ý:* Không. UID có cardinality lớn và là dữ liệu định danh. Dùng loại thao tác, nhóm nhánh nghiệp vụ và một correlation ID được quản lý phù hợp.

**Câu 4.** Có nên coi HTTP span 400 ms, LDAP span 30 ms là bằng chứng LDAP server chỉ mất 30 ms?

*Đáp án gợi ý:* Không hoàn toàn. LDAP span thường là thời gian phía client của một operation; server chỉ là một thành phần. Tổng HTTP còn chờ pool, mapping, network hoặc các thao tác khác.

**Câu 5.** Vì sao LDAP server log không hiển thị `traceparent` của request HTTP?

*Đáp án gợi ý:* LDAP RFC 4511 không có cơ chế tự mang W3C HTTP trace header. Instrumentation Spring LDAP đo ở client; log server phải được đối chiếu riêng hoặc tích hợp đặc thù.

**Câu 6.** Một service thêm người dùng, sửa nhóm và rename rồi bị lỗi bước cuối. Trace có khôi phục hai bước trước không?

*Đáp án gợi ý:* Không. Trace là công cụ quan sát; các LDAP operation độc lập không mặc nhiên nằm trong một transaction phân tán.

**Câu 7.** Vì sao test tracing cần kiểm tra cả case sử dụng `LdapRepository` và `LdapTemplate`?

*Đáp án gợi ý:* Cả hai có thể dùng các bean `ContextSource` khác nhau tùy cấu hình. Chỉ khi đường gọi thực tế đi qua wrapper quan sát mới có LDAP span mong muốn.

## 15. Ghi nhớ

- **Trace** liên kết các span theo `traceId`; `spanId` định danh từng công đoạn. Log correlation dựa vào context truyền đúng qua các layer/thread.
- **Spring LDAP 3.3+** có `ObservationContextSource`/`ContextSourceObservationPostProcessor` để instrument thao tác `DirContext`; cần xác minh đúng bean wiring, tracing bridge, sampling và exporter.
- Observation nghiệp vụ nên bao quát **use case logic**, còn observation LDAP đo **từng thao tác thực tế**. Tránh instrumentation trùng lặp.
- **Không đưa DN, UID, raw filter, password hoặc dữ liệu nhóm nhạy cảm vào metric tags/log/trace một cách tùy tiện**. Ưu tiên metadata loại thao tác và nhánh nghiệp vụ có tập giá trị hữu hạn.
- Trace LDAP phía client **không đồng nghĩa** server LDAP tự nhận `traceparent`; muốn đối chiếu server log phải dùng thông tin và khả năng riêng của directory.
- Quan sát đầy đủ cần ghép **trace + log + metrics** của HTTP, dịch vụ, LDAP context và connection pool, cùng bài kiểm thử lỗi, async và sampling.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — Observability Support](https://docs.spring.io/spring-ldap/reference/observability.html): `ContextSourceObservationPostProcessor`, `ObservationContextSource`, observation `spring.ldap.dir.context.operations`.
- [Spring LDAP API — ObservationContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/ObservationContextSource.html).
- [Spring LDAP API — ContextSourceObservationPostProcessor](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/ContextSourceObservationPostProcessor.html).
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, correlation log, sampling, exporter và custom observations.
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): scope, `ObservationRegistry`, low-/high-cardinality key-values.
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/).
- [OpenTelemetry — Context and Tracing](https://opentelemetry.io/docs/concepts/signals/traces/): trace/span/parent relationship.
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): các LDAP operation, không có HTTP trace header.
