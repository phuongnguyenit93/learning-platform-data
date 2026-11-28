# Quan sát pool và thời gian chờ context

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP bằng Spring Data LDAP repository hoặc `LdapTemplate`. Các thao tác tra cứu theo DN (*Distinguished Name*), lọc theo `objectClass`/thuộc tính, CRUD và xác thực đều cần liên hệ với LDAP directory. Một yêu cầu chậm không nhất thiết do LDAP server truy vấn chậm: ứng dụng có thể đang **chờ mượn một `DirContext` từ pool**, mở kết nối TCP/TLS mới hoặc chờ phản hồi của server.

Bài học này tập trung vào **observability** của tầng kết nối: biết lúc nào pool cạn, đo thời gian chờ context, phân biệt các loại timeout, xuất số liệu sang Micrometer/Actuator, đọc log an toàn và kiểm thử tải để phân tích nút thắt. Các ví dụ Java dùng Spring LDAP với Commons Pool 2; hãy kiểm tra API theo phiên bản thư viện đang triển khai.

## 1. Vì sao cần quan sát context?

Trong Spring LDAP, `ContextSource` cung cấp JNDI `DirContext`. Một `LdapTemplate.search(...)` thông thường cần lấy context, thực hiện LDAP search, duyệt kết quả, ánh xạ `Attributes` hoặc ODM entry rồi giải phóng context theo vòng đời template.

Sơ đồ đơn giản:

```text
HTTP request / scheduled sync
            |
            v
Service -> Repository hoặc LdapTemplate
            |
            v
     ContextSource
            |
            +-- Có pool? ----- Có ------> Mượn DirContext
            |                             |         |
            |                             |         +-- Pool rảnh -> trả ngay
            |                             |         +-- Pool cạn -> đợi / timeout
            |                             |
            |                             v
            +-- Không pool ----------> Tạo context / kết nối
                                          |
                                          v
                                LDAP TCP/TLS + bind
                                          |
                                          v
                                  LDAP search/lookup
                                          |
                                          v
                                  Trả hoặc đóng context
```

Ví dụ: ứng dụng nhận 100 yêu cầu đồng thời, pool chỉ cho mượn tối đa 8 context đọc. Nếu các truy vấn giữ context lâu, 92 yêu cầu còn lại có thể phải **xếp hàng**, dù bản thân câu lệnh LDAP trên server không bị chậm tương ứng.

**Quan trọng:** một `DirContext` là đối tượng JNDI đại diện cho ngữ cảnh kết nối/truy cập LDAP; số context đang mượn **không luôn bằng** số socket TCP vật lý. Provider, xác thực, TLS và cơ chế pooling bên dưới có thể ảnh hưởng mối quan hệ này. Đừng đặt tên biểu đồ “số TCP connections” khi thực tế bạn chỉ đọc `getNumActive()` của context pool.

## 2. Tách từng đoạn thời gian thay vì chỉ nhìn tổng latency

Với một thao tác đọc, hãy phân biệt ít nhất bốn đại lượng:

| Chỉ số | Bắt đầu / kết thúc | Nguyên nhân gây tăng |
|---|---|---|
| **Context acquire / borrow latency** | Trước `ContextSource.getReadOnlyContext()` đến khi nhận được context hoặc lỗi | Pool cạn, chờ trả context, tạo/kiểm tra context mới |
| **TCP/TLS connect + bind latency** | Khi provider tạo kết nối mới tới lúc có context sử dụng được | DNS, mạng, TLS handshake, LDAP bind, server |
| **LDAP operation latency** | Gửi yêu cầu search/lookup/modify đến khi xử lý kết quả cần thiết | Filter không có index, dữ liệu lớn, server/đường truyền, referrals |
| **End-to-end application latency** | Từ lúc service nhận yêu cầu đến khi trả kết quả | Tổng các khâu trên, mapping, xử lý nghiệp vụ, queue khác |

Ví dụ một trace minh họa, **không phải số liệu thực tế của hệ thống**:

```text
Request tổng: 850 ms
  ├── Chờ mượn context:       600 ms
  ├── Thao tác LDAP:          180 ms
  ├── Đọc/ánh xạ kết quả:      40 ms
  └── Logic ứng dụng khác:     30 ms
```

Nếu chỉ có timer quanh `PersonRepository.findAll()`, bạn thấy 850 ms nhưng chưa biết 600 ms bị tiêu tốn **trước khi query chạy**. Vì vậy nên có một **timer mượn context** độc lập với timer nghiệp vụ, đồng thời xem gauge của pool và log/lược đồ truy vấn LDAP.

Một phép đo quanh `getReadOnlyContext()` đo thời gian **cấp context**, nhưng không nhất thiết chỉ đo *thời gian nằm trong hàng đợi*: nếu pool phải tạo kết nối mới hoặc chạy validation `testOnBorrow`, các bước đó cũng nằm trong khoảng đo. Nên gọi chính xác là **acquire duration**, không mặc định đặt tên “queue time”.

## 3. Phân biệt pool JNDI và pool của Spring LDAP

Spring LDAP có hai hướng cấu hình thường gặp:

| Loại | Cơ chế | Khả năng quan sát | Lưu ý |
|---|---|---|---|
| **Native JNDI LDAP pooling** | Cấu hình `AbstractContextSource.setPooled(true)` để dùng pooling của Java LDAP provider | Chủ yếu dựa trên cấu hình/provider và log; **không có** API `PooledContextSource.getNumActive()` cho pool này | Ít tùy chọn validation/maintenance; cấu hình chi tiết qua Java system properties |
| **Spring LDAP context pooling** | Bọc một `ContextSource` bằng `PooledContextSource` (Commons Pool 2) hoặc `PoolingContextSource` (pool cũ) | Có API đếm active/idle/waiters, JMX và khả năng tích hợp metrics | Phải định cấu hình bean, giới hạn, validation và trả context đúng cách |
| **Không pooling** | Mỗi thao tác dùng context theo vòng đời của provider | Không có pool gauge để xem; đo thời gian tạo context/operation | Có thể chịu overhead kết nối lớn hơn |

Tài liệu Spring LDAP khuyến nghị cơ chế pooling linh hoạt của Spring khi cần validation và kiểm soát pool chi tiết. Khi viết bài này, ví dụ đo số context dùng **`org.springframework.ldap.pool2.factory.PooledContextSource`**, không phải class cũ **`org.springframework.ldap.pool.factory.PoolingContextSource`**. Tên hai class dễ nhầm, và các setter cấu hình **không giống nhau**.

Với JNDI native pooling, thuộc tính `setPooled` mặc định là `false` trong Spring LDAP hiện đại. Không mặc định rằng chỉ dùng `spring-boot-starter-data-ldap` là đã có một context pool được bật, hoặc rằng Actuator tự sinh các metric pool LDAP.

**Không bật chồng hai tầng pooling mà không có chủ đích và kiểm thử.** Nếu dùng `PooledContextSource` để quản lý vòng đời mượn/trả, nên để context source bên dưới không bật native pooling để việc quan sát và giới hạn dễ giải thích.

## 4. Những chỉ số pool nên theo dõi

Với Spring LDAP Commons Pool 2, `PooledContextSource` công bố các getter:

| Getter | Ý nghĩa | Cách đọc |
|---|---|---|
| `getNumActive()` | Tổng số context đang được mượn | Liên tục cao gần giới hạn là dấu hiệu áp lực |
| `getNumIdle()` | Tổng số context sẵn có trong pool | Thấp kèm waiters cao có thể là pool cạn |
| `getNumWaiters()` | Số thread hiện đang chờ mượn context | Dương liên tục nghĩa là có hàng đợi |
| `getNumActiveRead()` / `getNumActiveWrite()` | Context đang được mượn theo nhánh đọc/ghi | Cho biết loại workload nào chiếm pool |
| `getNumIdleRead()` / `getNumIdleWrite()` | Context rảnh theo nhánh đọc/ghi | Hữu ích vì pool quản lý các loại context theo key |

Kết hợp với cấu hình:

- `PoolConfig.maxTotal`: giới hạn tổng các object pool có thể cấp; phải xét cả đọc và ghi.
- `PoolConfig.maxTotalPerKey`: giới hạn cho từng loại context (read-only, read-write).
- `PoolConfig.maxIdlePerKey` và `minIdlePerKey`: điều khiển số context rảnh.
- `PoolConfig.maxWaitMillis`: thời gian chờ tối đa khi pool cạn và bật `blockWhenExhausted`.
- `PoolConfig.blockWhenExhausted`: cho phép chờ hay thất bại ngay lúc hết context.
- `testOnBorrow` / `testWhileIdle`: kiểm tra context còn hoạt động; tăng độ tin cậy nhưng có thể thêm network round-trip/chi phí.

**Không lấy mỗi `active / maxTotal` rồi kết luận pool khỏe hoặc yếu.** Ví dụ `maxTotal=20` và `maxTotalPerKey=4`: nếu 4 context đọc đang được mượn hết thì truy vấn đọc có thể phải đợi, **dù tổng active mới là 4/20**. Hãy xem cả limit theo key, read/write và `getNumWaiters()`.

Đồng thời, gauge là **ảnh chụp tức thời**: `waiters=0` ở một lần scrape không chứng minh chưa từng có đợt chờ ngắn. Timer acquire và bộ đếm lỗi giúp bắt những đợt nghẽn xuất hiện giữa hai lần lấy mẫu.

## 5. Cấu hình pool có giới hạn và timeout rõ ràng

Ví dụ cấu hình Spring Framework/Spring Boot có tạo bean thủ công. Phần code dùng `PooledContextSource`, `PoolConfig` của Commons Pool 2, và một `LdapContextSource` làm nguồn tạo context.

**`DirectoryPoolConfiguration.java`**

```java
package com.example.ldap;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;

@Configuration
public class DirectoryPoolConfiguration {

    @Bean("rawDirectoryContextSource")
    LdapContextSource rawDirectoryContextSource(
            @Value("${app.directory.url}") String url,
            @Value("${app.directory.base}") String base,
            @Value("${app.directory.bind-dn}") String bindDn,
            @Value("${app.directory.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setPooled(false); // Không bật thêm native JNDI pooling.
        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "2000",
                "com.sun.jndi.ldap.read.timeout", "4000"));
        return source;
    }

    @Bean("ldapPool")
    PooledContextSource ldapPool(
            @Qualifier("rawDirectoryContextSource")
            LdapContextSource source) {

        PoolConfig config = new PoolConfig();
        config.setMaxTotal(16);
        config.setMaxTotalPerKey(8);
        config.setMaxIdlePerKey(8);
        config.setBlockWhenExhausted(true);
        config.setMaxWaitMillis(500);
        config.setTestOnBorrow(false); // Bật validation cần validator phù hợp.
        config.setJmxEnabled(true);
        config.setJmxNamePrefix("ldapDirectory");

        PooledContextSource pooled = new PooledContextSource(config);
        pooled.setContextSource(source);
        return pooled;
    }

    @Bean("ldapTemplate")
    LdapTemplate ldapTemplate(@Qualifier("ldapPool") ContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Ví dụ `application.yml`:

```yaml
app:
  directory:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=reader,ou=service,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
```

Trong dự án thực, bảo đảm các dependency Spring LDAP, Apache Commons Pool 2, Micrometer (nếu đo metrics) tương thích với phiên bản Spring Boot đang dùng. Mật khẩu bind phải đến từ secret manager hoặc biến môi trường; không ghi mật khẩu thật vào repository. Chứng chỉ và hostname của kết nối LDAPS phải được xác minh.

**Lưu ý về bean:** vì ví dụ tạo cả `rawDirectoryContextSource` và `ldapPool` (đều tương thích `ContextSource`), `ldapTemplate` được nối **rõ ràng** vào `ldapPool` qua `@Qualifier`. Trong ứng dụng có auto-configuration khác, phải xác nhận repository thực tế dùng bean `ldapTemplate` này, tránh vô tình sử dụng context source không qua pool. Không đăng ký hai `ldapTemplate` cạnh tranh mà không có cấu hình rõ ràng.

Các giá trị `16`, `8`, `500 ms`, `2000 ms`, `4000 ms` chỉ là **tham số minh họa**, không phải khuyến nghị chung. Cần hiệu chỉnh dựa trên tải, số replica ứng dụng, giới hạn kết nối của LDAP server và yêu cầu latency.

### 5.1. Đừng nhầm ba loại timeout

| Cấu hình | Thời gian áp dụng | Khi hết hạn |
|---|---|---|
| `PoolConfig.setMaxWaitMillis(500)` | Chờ context từ pool khi pool cạn | Có thể thất bại ở tầng mượn context, được Spring LDAP bao bọc thành lỗi truy cập tài nguyên |
| `com.sun.jndi.ldap.connect.timeout=2000` | Thử kết nối TCP tới LDAP endpoint mới | Có thể báo lỗi kết nối/tạo context |
| `com.sun.jndi.ldap.read.timeout=4000` | Chờ phản hồi LDAP theo provider JNDI | Có thể báo lỗi đọc/communication |
| `LdapQueryBuilder.timeLimit(...)` hoặc search controls | Giới hạn thời gian tìm kiếm ở tầng LDAP query | Có thể tạo kết quả một phần, lỗi limit hoặc behavior tùy server/provider |
| HTTP/request deadline | Giới hạn toàn bộ yêu cầu của ứng dụng | Bảo vệ trải nghiệm người dùng; không tự dừng mọi tác vụ LDAP bên dưới nếu không có cơ chế hủy phù hợp |

`maxWaitMillis` **không phải** connect timeout và cũng **không phải** thời gian LDAP server thực hiện search. Nếu `maxWaitMillis` mặc định âm (pool có thể chờ vô hạn) mà không có deadline phù hợp, yêu cầu có thể bị treo khi pool cạn; đặt giới hạn hữu hạn theo budget của hệ thống.

Đồng thời, thời gian acquire có thể bao gồm **tạo context mới hoặc validation**, không chỉ chờ hàng đợi. Khi cần tìm thủ phạm latency, xem thêm log kết nối, trạng thái server và số lần tạo/invalidate context.

## 6. Xuất metric pool sang Micrometer / Actuator

`PooledContextSource` cung cấp getter nhưng **không phải mọi bản Spring Boot tự xuất LDAP pool gauges**. Có thể đăng ký metric tùy chỉnh qua Micrometer. Ví dụ dưới đây yêu cầu Micrometer trong classpath:

**`DirectoryPoolMetrics.java`**

```java
package com.example.ldap;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.pool2.factory.PooledContextSource;

@Configuration
public class DirectoryPoolMetrics {

    @Bean
    MeterBinder ldapPoolMetrics(
            @Qualifier("ldapPool") PooledContextSource pool) {
        return registry -> {
            Gauge.builder("ldap.pool.active", pool, PooledContextSource::getNumActive)
                    .description("Số DirContext đang được mượn")
                    .tag("pool", "directory-main")
                    .register(registry);

            Gauge.builder("ldap.pool.idle", pool, PooledContextSource::getNumIdle)
                    .description("Số DirContext rảnh")
                    .tag("pool", "directory-main")
                    .register(registry);

            Gauge.builder("ldap.pool.waiters", pool, PooledContextSource::getNumWaiters)
                    .description("Số thread đang chờ mượn DirContext")
                    .tag("pool", "directory-main")
                    .register(registry);

            Gauge.builder("ldap.pool.active.read", pool,
                            PooledContextSource::getNumActiveRead)
                    .tag("pool", "directory-main")
                    .register(registry);

            Gauge.builder("ldap.pool.active.write", pool,
                            PooledContextSource::getNumActiveWrite)
                    .tag("pool", "directory-main")
                    .register(registry);
        };
    }
}
```

Những tên như `ldap.pool.active` là **tên metric do ứng dụng tự đặt**, không phải một chuẩn metric LDAP có sẵn. Với Spring Boot Actuator, cần cấu hình registry/exporter phù hợp để xem chúng trên hệ thống quan sát. Ví dụ Prometheus có thể chuyển dấu chấm sang dấu gạch dưới trong tên metric; kiểm tra dữ liệu exporter thực tế.

**Không đưa** DN người dùng, login, email, filter chứa dữ liệu cá nhân hoặc endpoint referral chưa làm sạch vào **metric tag**. Tag có cardinality cao làm tăng chi phí bộ nhớ và lưu trữ, đồng thời có nguy cơ rò rỉ dữ liệu. Dùng tag ổn định như tên pool, môi trường và loại thao tác đã kiểm soát.

### 6.1. Đọc dashboard theo cặp tín hiệu

| Tín hiệu | Diễn giải ban đầu | Cần kiểm tra thêm |
|---|---|---|
| `active` cao, `idle=0`, `waiters>0` | Pool có thể cạn | `maxTotalPerKey`, acquire p95/p99, truy vấn dài |
| `active` thấp, acquire p95 tăng | Context mới được tạo/validate chậm | Connect/TLS/bind latency, test-on-borrow, server |
| `active` tăng liên tục, không trở về baseline | Context bị giữ quá lâu hoặc không trả | Đóng `DirContext`/enumeration, long-running query |
| `idle` cao nhưng truy vấn chậm | Nút thắt có thể không ở pool | Search filter/index, read timeout, LDAP server |
| `waiters` tăng cùng lỗi borrow timeout | Chờ vượt `maxWaitMillis` | Giảm thời gian giữ context, tải đồng thời, sizing |
| Chỉ `active.read` cao | Workload đọc là nguồn áp lực | Tối ưu search, scope, sizeLimit, cache an toàn |

Hãy nhìn **p95/p99 acquire latency** bên cạnh gauge; trung bình thấp không loại trừ các đợt nghẽn ngắn nhưng nghiêm trọng.

## 7. Đo thời gian mượn context mà không trộn với thời gian query

Micrometer `Timer` có thể đo một lời gọi `getReadOnlyContext()`. Ví dụ helper sau **chỉ instrument các lời gọi đi qua helper**, không tự động đo mọi `LdapTemplate.search(...)`. Nếu cần phủ toàn bộ ứng dụng, phải nối instrumentation vào đường cấp context mà template/repository thực sự sử dụng, bảo đảm decorator giữ đúng hợp đồng `ContextSource`/base DN.

**`ContextBorrowProbe.java`**

```java
package com.example.ldap;

import java.util.concurrent.TimeUnit;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.ldap.core.ContextSource;

public class ContextBorrowProbe {
    private final ContextSource contextSource;
    private final Timer acquired;
    private final Timer failed;

    public ContextBorrowProbe(
            ContextSource contextSource, MeterRegistry registry) {
        this.contextSource = contextSource;
        this.acquired = Timer.builder("ldap.context.acquire")
                .tag("mode", "read")
                .tag("outcome", "success")
                .register(registry);
        this.failed = Timer.builder("ldap.context.acquire")
                .tag("mode", "read")
                .tag("outcome", "failure")
                .register(registry);
    }

    public DirContext borrowReadOnly() throws NamingException {
        long start = System.nanoTime();
        boolean success = false;
        try {
            DirContext context = contextSource.getReadOnlyContext();
            success = true;
            return context;
        } finally {
            long elapsed = System.nanoTime() - start;
            (success ? acquired : failed)
                    .record(elapsed, TimeUnit.NANOSECONDS);
        }
    }
}
```

Cách dùng trong một đoạn code JNDI chủ động:

```java
// probe được tạo với ContextSource thực sự dùng pool và MeterRegistry.
DirContext context = probe.borrowReadOnly();
try {
    // Gọi các thao tác JNDI đã được cấp quyền.
    // Nếu tìm kiếm trả NamingEnumeration, cần duyệt và đóng enumeration.
} finally {
    context.close(); // Với pooled context, đóng để trả context về pool.
}
```

Timer thu được **phân phối thời gian acquire**, kể cả khi pool phải tạo hoặc validate context. Đoạn ví dụ không có retry và không can thiệp hoạt động của `LdapTemplate`. Khi áp dụng cho các lời gọi thật, bảo đảm context được trả về pool ngay cả khi search/mapping ném ngoại lệ.

Không ghi thời gian bằng `System.currentTimeMillis()` cho đoạn đo ngắn; dùng `System.nanoTime()` để đo **khoảng thời gian đơn điệu**, không bị ảnh hưởng bởi chỉnh đồng hồ hệ thống. Không gắn URL, DN, password hoặc giá trị filter làm tag của timer.

### 7.1. Đặt timer end-to-end ở tầng service

Thêm một timer riêng cho `PersonDirectoryService.searchPeople(...)` (hoặc dùng quan sát Micrometer/Actuator trên lời gọi nghiệp vụ) để thu **service latency**. Khi có tracing:

```text
trace request_id=...
  service.searchPeople                     620 ms
    context.acquire                        420 ms
    ldap.search + read results             170 ms
    map DTO                                 30 ms
```

Đây là ví dụ minh họa cấu trúc trace. **Không mặc nhiên** Spring LDAP cung cấp sẵn span `context.acquire`; bạn phải cấu hình instrumentation tương ứng mới có phân đoạn này. Timer service đo tổng thể, không tự suy ra thời gian chờ mượn context từ hiệu số nếu còn retry hoặc các khâu đồng thời.

## 8. Quy tắc trả context, validation và các điểm dễ gây nghẽn

### 8.1. Trả context đúng vòng đời

Nếu bạn tự lấy context qua `ContextSource`, hãy luôn đóng trong `finally` (hoặc cấu trúc quản lý tài nguyên phù hợp):

```java
DirContext ctx = contextSource.getReadOnlyContext();
try {
    // Thực hiện việc đọc LDAP.
} finally {
    ctx.close();
}
```

Với context được trả từ pool, `close()` trên wrapper thường có ý nghĩa **trả lại pool**, không phải ứng dụng tự đóng socket vật lý ngay lập tức. Nếu bỏ qua `close()`, active có thể tăng và gây đợi vô hạn hoặc lỗi pool exhausted.

Khi thao tác search trả `NamingEnumeration<SearchResult>` ở tầng JNDI, hãy đóng enumeration đúng cách; kết quả chưa được duyệt/đóng hết có thể giữ tài nguyên mạng. `LdapTemplate` quản lý vòng đời context/enumeration cho các phương thức thông thường, nhưng callback tùy biến vẫn cần tuân theo hợp đồng của API.

### 8.2. Validation giúp tránh context chết nhưng có giá

`testOnBorrow` có thể phát hiện context không còn hoạt động **trước khi cấp cho request**, nhưng việc kiểm tra có thể tạo yêu cầu LDAP bổ sung. Khi bật các chế độ validation, phải cấu hình `DirContextValidator` phù hợp với loại `PooledContextSource`/phiên bản:

```text
Pool có context idle
        |
        v
Request mượn context
        |
        +-- testOnBorrow? -- Có --> LDAP validation
        |                             |
        |                     Thất bại -> loại context
        |                             |
        |                         Tạo/mượn cái khác
        |
        v
Trả context cho request
```

Nếu acquire p95 tăng nhưng `waiters` thấp, xem lại validation và tuổi thọ context. Nếu nhiều context chết sau một lần LDAP server restart, số context bị invalidate/tạo mới cũng có thể tăng. Thực nghiệm với môi trường test trước khi tăng `minIdlePerKey` hoặc bật đồng thời mọi chế độ validation.

**Đặc biệt với xác thực người dùng:** pool dùng chung service-account context không phải nơi lưu và tái sử dụng tùy tiện context xác thực bằng credential của từng người dùng. Spring LDAP cảnh báo pooling với nguồn credential thay đổi theo thread có thể dẫn tới tái sử dụng sai identity. Cần tách pool thao tác dịch vụ khỏi luồng kiểm tra mật khẩu/bind người dùng, theo cơ chế xác thực phù hợp.

### 8.3. Paged results và context có trạng thái

Một số LDAP control (ví dụ paged-results control) cần đặt request controls trên `LdapContext`. Với cơ chế pooled context cần cân nhắc `MutablePooledContextSource` (Commons Pool 2) theo tài liệu Spring LDAP, vì class này hỗ trợ các trường hợp yêu cầu thay đổi request controls. Không mặc định một pooled context bất kỳ sẽ phù hợp với mọi thao tác stateful, cũng không để control của request trước rò sang request sau.

## 9. Quy trình chẩn đoán pool bị cạn

Khi ứng dụng báo timeout hoặc chậm:

1. **Xác nhận tầng lỗi.** Lỗi xảy ra khi mượn context, kết nối, bind, LDAP search hay ánh xạ dữ liệu? Lấy exception class/stack trace đã làm sạch và phân tách log thời gian.
2. **Đọc metrics tại cùng khoảng thời gian.** Xem `active`, `idle`, `waiters`, p95/p99 acquire và lỗi borrow; đối chiếu `maxTotal`/`maxTotalPerKey`.
3. **Tìm context giữ lâu.** Quan sát operation latency, truy vấn `SUBTREE` rộng, filter không có index, search trả quá nhiều entry, callback/logic giữ context và enumeration chưa đóng.
4. **Kiểm tra kết nối mới.** Nếu acquire cao nhưng waiters thấp, xem DNS, TLS, bind, connect timeout, read timeout, validator; thử LDAP server test/health check có phạm vi hẹp.
5. **Xem trạng thái directory.** Giới hạn kết nối server, ACL, referral, quá tải mạng, số replica, time limit/size limit có thể làm operation kéo dài.
6. **Điều chỉnh dựa trên tải.** Giảm thời gian giữ context, tối ưu query và giới hạn concurrency trước; sau đó điều chỉnh pool size nếu server còn năng lực. Tăng pool liên tục chỉ chuyển nghẽn sang directory.
7. **Kiểm thử lại và so sánh.** Chạy cùng kịch bản tải trước/sau khi thay đổi; theo dõi latency, lỗi, CPU và số kết nối trên server LDAP.

Ví dụ cách đọc số liệu minh họa:

| active | idle | waiters | Acquire p95 | Nhận xét ban đầu |
|---:|---:|---:|---:|---|
| 2 | 6 | 0 | 3 ms | Còn dư pool; nếu request chậm, cần xem LDAP operation |
| 8 | 0 | 12 | 480 ms | Pool đọc có thể cạn gần `maxWaitMillis=500` |
| 1 | 0 | 0 | 900 ms | Có thể đang tạo context/kết nối hoặc validation chậm |

Đây chỉ là **số giả định để luyện phân tích**, không phải số liệu nên đặt làm ngưỡng cảnh báo cho mọi hệ thống.

## 10. Thiết kế dashboard và cảnh báo hữu ích

Một dashboard vận hành nên có tối thiểu:

| Panel | Chỉ số | Mục tiêu |
|---|---|---|
| Pool utilization | `active` / giới hạn phù hợp theo key, `idle` | Thấy mức sử dụng và headroom |
| Contention | `waiters`, acquire p50/p95/p99 | Phát hiện pool cạn hoặc borrow chậm |
| Failures | Số lần borrow thất bại, connection/read/search timeout | Phân biệt lỗi của pool với lỗi directory |
| Workload | QPS search/lookup/modify, số entry trả về | Hiểu tải ảnh hưởng context |
| LDAP latency | Operation p95/p99, connection/bind latency khi đo được | Tìm nút thắt ngoài pool |
| JVM/service | Thread pool, HTTP latency, GC, số replica | Tránh kết luận sai từ một chỉ số |

Cảnh báo nên gắn với **hậu quả thật**: chẳng hạn acquire p95 tăng đáng kể *đồng thời* có waiters liên tục và tỷ lệ lỗi borrow tăng. `active` cao một mình chưa chắc là sự cố nếu pool trả context nhanh và latency vẫn đạt SLO.

Khi ghi log, ưu tiên:

```text
event=ldap_context_borrow_failed
pool=directory-main
operation=search
elapsed_ms=503
reason=pool_exhausted
correlation_id=<id-da-duoc-lam-sach>
```

Không ghi password bind, giá trị thuộc tính người dùng, toàn bộ DN nhạy cảm, raw filter chứa input cá nhân hay referral URL chưa kiểm tra. Cũng tránh bật DEBUG chứa dữ liệu xác thực của JNDI trong môi trường production lâu dài.

## 11. Kiểm thử tình huống pool cạn và timeout

Kiểm thử timing cần **LDAP test directory** thật hoặc test double hỗ trợ hành vi giữ/trả context, không chỉ mock `AttributesMapper`. Với `PooledContextSource` được cấu hình riêng cho test:

```java
PoolConfig config = new PoolConfig();
config.setMaxTotal(1);
config.setMaxTotalPerKey(1);
config.setBlockWhenExhausted(true);
config.setMaxWaitMillis(200);

PooledContextSource pooled = new PooledContextSource(config);
pooled.setContextSource(testRawLdapContextSource);
```

Kịch bản kiểm thử:

1. Mượn một context đọc và **giữ tạm**, chưa gọi `close()`. Xác nhận `getNumActiveRead()` tăng.
2. Từ thread thứ hai yêu cầu mượn context đọc. Với `maxTotalPerKey=1`, không có context rảnh; kiểm tra có waiters và lần mượn thứ hai thất bại sau khoảng chờ phù hợp với `maxWaitMillis` (cho phép sai số do scheduler).
3. Đóng context thứ nhất trong `finally`. Thử mượn lại; quan sát `active`/`idle` quay về trạng thái bình thường và không có leak.
4. Giữ nguyên pool nhưng giả lập server LDAP không phản hồi/không kết nối: phân biệt lỗi `connect.timeout`, `read.timeout` và `maxWaitMillis` theo class/log thực tế.
5. Bật `testOnBorrow` với validator phù hợp và đóng server sau khi trả context idle; xác minh context chết bị phát hiện/loại ra, không trả kết quả sai.
6. Kiểm tra Micrometer timer có mẫu success/failure, pool gauges có thay đổi, log không chứa DN/password/credential.
7. Thử tải đồng thời với `maxTotalPerKey` lớn hơn, đo throughput và p95/p99; không chỉ xác minh test “không ném exception”.

**Không nên** dùng một assertion `elapsed == 200 ms` vì độ trễ scheduler, JVM warm-up và network có thể khiến kết quả không chính xác tuyệt đối. Hãy assert khoảng cho phép, số lượng lỗi và xu hướng metric; với JUnit, dùng timeout tổng phù hợp để ngăn test bị treo.

Với test tích hợp Spring, bảo đảm bean `ldapTemplate` và repository đã kết nối qua **chính bean `ldapPool`** trong test; nếu vô tình đi qua raw context source, kiểm thử không phản ánh hành vi pool.

## 12. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “`ldapTemplate.search` mất 1 giây nghĩa là LDAP server tìm 1 giây.” | Tổng thời gian có thể gồm chờ mượn context, connect/bind, query và mapping |
| “`getNumActive()` đếm socket TCP.” | Đây là số pooled `DirContext` đang được mượn, không bảo đảm trùng socket |
| “`active < maxTotal` thì chắc chắn không phải đợi.” | Có thể đạt giới hạn `maxTotalPerKey` đối với read/write |
| “`waiters=0` nghĩa là không có contention.” | Gauge lấy mẫu tức thời có thể bỏ lỡ các đợt nghẽn ngắn |
| “Tăng `maxTotal` luôn làm hệ thống nhanh hơn.” | Có thể khiến LDAP server quá tải; cần tối ưu query và thời gian giữ context |
| “`maxWaitMillis` là timeout LDAP search.” | Nó giới hạn thời gian chờ mượn object khi pool cạn |
| “Bật pool tự động có metric trong Actuator.” | Cần xác nhận bean/exporter; thường phải đăng ký metric tùy chỉnh |
| “Context được đóng sẽ luôn đóng TCP socket ngay.” | Pooled wrapper thường trả context về pool để dùng lại |
| “Pool dùng cho service bind có thể tái sử dụng cho mọi user login.” | Credential thay đổi theo user cần cơ chế xác thực riêng; tránh tái sử dụng sai identity |

## 13. Câu hỏi tự kiểm tra

1. `getNumActive()`, `getNumIdle()` và `getNumWaiters()` biểu diễn những trạng thái nào của pool?
2. Vì sao `active=4` trên `maxTotal=20` vẫn có thể xảy ra pool contention khi `maxTotalPerKey=4`?
3. Đo từ trước tới sau `getReadOnlyContext()` có phải luôn là thời gian **chỉ đứng trong queue** không? Vì sao?
4. Phân biệt `maxWaitMillis`, `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout`.
5. Khi acquire p95 tăng nhưng waiters không tăng, bạn sẽ kiểm tra những nguyên nhân nào?
6. Vì sao `LdapTemplate` cần được nối với đúng `PooledContextSource` trước khi những gauge pool có giá trị để chẩn đoán lời gọi thật?
7. Để phát hiện context leak, những số liệu và phép thử nào là hữu ích?
8. Tại sao không dùng DN, email hay filter nguyên văn làm tag Micrometer?
9. Khi bật `testOnBorrow`, cần chuẩn bị thêm thành phần gì và đánh đổi latency ra sao?

**Ghi nhớ:** quan sát LDAP pool phải đi cùng **thời gian mượn context**, số context active/idle, số thread chờ, giới hạn theo read/write và timeout kết nối/đọc. Đừng coi tổng thời gian repository là thời gian tìm kiếm của server. Hãy dùng metrics, trace/log đã làm sạch và kiểm thử pool cạn để phân biệt nghẽn tại ứng dụng với sự cố directory; điều chỉnh dựa trên tải thực và bảo mật kết nối.

### Tài liệu tham khảo

- Spring LDAP Reference — [Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): cơ chế pool, validation, cấu hình `max-total-per-key`/`max-wait`, các lưu ý về authentication.
- Spring LDAP API — [`PooledContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html): `getNumActive`, `getNumIdle`, `getNumWaiters`, read/write gauges.
- Spring LDAP API — [`PoolConfig`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PoolConfig.html): giới hạn, `setMaxWaitMillis`, validation và JMX.
- Spring LDAP Reference — [Configuration / Native Java LDAP Pooling](https://docs.spring.io/spring-ldap/reference/configuration.html): `setPooled` và các giới hạn của JNDI pooling.
- Oracle Java SE — [JNDI LDAP provider properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/module-summary.html): `com.sun.jndi.ldap.connect.timeout`, `com.sun.jndi.ldap.read.timeout`.
- Micrometer — [Meters and Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo khoảng thời gian, phân phối latency và metric tags.
