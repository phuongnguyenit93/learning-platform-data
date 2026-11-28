# Cấu hình số lượng tối đa, số nhàn rỗi và thời gian chờ

Trong **Spring Data LDAP**, lời gọi **LdapRepository.findByUid(...)** hoặc **LdapTemplate.search(...)** cần một LDAP context để kết nối, xác thực và truy vấn các entry theo **DN, objectClass, schema và ACL**. Việc liên tục mở kết nối TCP, thực hiện TLS handshake và LDAP bind làm tăng độ trễ, nhất là khi nhiều request chạy đồng thời. **Connection pool** giữ một số context để tái sử dụng, nhưng nếu chọn sai giới hạn tối đa, mức nhàn rỗi hoặc thời gian đợi mượn context, pool có thể gây tắc nghẽn hoặc tạo quá nhiều kết nối tới directory server.

Bài thuộc chương **Pool kết nối**, hướng dẫn cấu hình và lý giải ba nhóm giá trị: **số lượng tối đa**, **số nhàn rỗi** và **thời gian chờ**. Hai cơ chế được phân tích riêng là **Spring LDAP Pool2** và **native JNDI LDAP pooling**. Các ví dụ dùng Spring Boot, JNDI LDAP provider của JDK và một directory lab minh họa; đồng thời bao quát validation, kết nối LDAPS/StartTLS, trách nhiệm đóng context, tải nhiều pod và kiểm thử.

> **Quy tắc:** Thời gian đợi **mượn context**, thời gian **mở TCP**, thời gian **chờ phản hồi LDAP** và giới hạn thời gian **Search** không phải là một. Không gộp chúng thành một property chung.

## 1. Vòng đời một context khi có pool

~~~mermaid
sequenceDiagram
    participant C as Client / Service
    participant T as Repository / LdapTemplate
    participant P as ContextSource / Pool
    participant D as LDAP directory
    C->>T: findByUid("linh")
    T->>P: Mượn read-only context
    alt Có context idle hợp lệ
        P-->>T: Trả context cũ
    else Được phép tạo connection mới
        P->>D: TCP + TLS + bind
        D-->>P: Sẵn sàng
        P-->>T: Trả context mới
    else Pool đã đầy
        Note over P,T: Chờ trong maxWait
        P-->>T: Được cấp context hoặc nhận lỗi hết chờ
    end
    T->>D: SearchRequest
    D-->>T: SearchResult
    T->>P: close() wrapper -> trả pool
    T-->>C: Java object / DTO
~~~

Các trạng thái cần hiểu:

| Khái niệm | Nghĩa | Ví dụ |
| --- | --- | --- |
| **Active / borrowed** | Context đã mượn, chưa trả về pool | 7 request đang truy vấn |
| **Idle** | Context đã được trả và có thể mượn lại | 3 kết nối chờ sử dụng |
| **Total** | Active cộng idle của pool tại thời điểm quan sát | 7 + 3 = 10 |
| **Maximum total** | Trần số context mà pool có thể duy trì | 12 |
| **Maximum idle** | Số context rảnh tối đa được giữ lại | 4 |
| **Minimum idle** | Số context rảnh mà pool cố duy trì theo chính sách | 1 |
| **Borrow wait** | Chờ khi pool không còn context để cấp | 1500 ms |
| **Eviction** | Thu hồi context idle lâu hoặc bị hỏng | Kiểm tra theo chu kỳ |

Khi lấy context từ **Spring LDAP pool**, gọi **close()** thường trả context wrapper về pool chứ không nhất thiết đóng socket vật lý. **Không close** sẽ giữ context ở trạng thái active, dẫn tới pool hết chỗ dù LDAP server vẫn hoạt động bình thường.

## 2. Chọn đúng cơ chế: Spring LDAP Pool2 hay JNDI native?

| Tiêu chí | Spring LDAP Pool2 | Native JNDI LDAP pooling |
| --- | --- | --- |
| API chính | **PooledContextSource** và **PoolConfig** | LDAP provider trong JDK |
| Phạm vi giới hạn | Theo bean pool, có các key context | Theo **connection identity** trong JVM |
| Số lượng tối đa | **maxTotal**, **maxTotalPerKey** | **com.sun.jndi.ldap.connect.pool.maxsize** |
| Nhàn rỗi | **maxIdlePerKey**, **minIdlePerKey**, eviction | **prefsize**, **pool.timeout**; không có cặp min/max idle tương đương |
| Chờ mượn | **maxWaitMillis** và **blockWhenExhausted** | **com.sun.jndi.ldap.connect.timeout** |
| Kiểm tra connection | **testOnBorrow**, **testWhileIdle**, **DirContextValidator** | Ít tùy chọn validation hơn |
| Cách bật | Bọc ContextSource bằng pool của Spring | **setPooled(true)** hoặc key JNDI của provider |
| Cấu hình kích thước | Java bean / PoolConfig | JVM **system properties** |

**Không bật cả hai cơ chế cùng lúc chỉ vì muốn tăng hiệu năng.** Khi chọn Spring LDAP Pool2, hãy đặt **LdapContextSource.setPooled(false)** để không lồng thêm native JNDI pooling. Pool lồng nhau có thể khiến việc tính số socket và thời gian chờ khó đoán.

Tài liệu cũ có lớp **org.springframework.ldap.pool.factory.PoolingContextSource** dựa trên Commons Pool thế hệ trước. Bài này ưu tiên **org.springframework.ldap.pool2.factory.PooledContextSource** và **PoolConfig** sử dụng **Apache Commons Pool 2**. Các tên setter, giới hạn và default giữa hai đời API không được mặc định giống hệt nhau.

## 3. Các giới hạn của PoolConfig trong Spring LDAP Pool2

| Setter | Đơn vị | Tác dụng |
| --- | --- | --- |
| **setMaxTotal(int)** | Context | Giới hạn tổng context trong pool, gộp mọi key |
| **setMaxTotalPerKey(int)** | Context/key | Giới hạn context của từng loại như READ hoặc WRITE |
| **setMaxIdlePerKey(int)** | Context/key | Giữ tối đa bao nhiêu context idle ở một key |
| **setMinIdlePerKey(int)** | Context/key | Mức idle mục tiêu được cơ chế bảo trì duy trì |
| **setMaxWaitMillis(long)** | Mili giây | Chờ mượn context tối đa khi pool cạn |
| **setBlockWhenExhausted(boolean)** | True/false | Chờ khi pool cạn hay từ chối ngay |
| **setTestOnBorrow(boolean)** | True/false | Kiểm tra context trước khi mượn |
| **setTestOnReturn(boolean)** | True/false | Kiểm tra context khi trả |
| **setTestWhileIdle(boolean)** | True/false | Kiểm tra context idle theo chu kỳ |
| **setTimeBetweenEvictionRunsMillis(long)** | Mili giây | Chu kỳ bảo trì context nhàn rỗi |
| **setMinEvictableIdleTimeMillis(long)** | Mili giây | Tuổi idle tối thiểu để được xét thu hồi |
| **setNumTestsPerEvictionRun(int)** | Số context | Số context xem xét ở mỗi lượt bảo trì |

Các **default** đáng chú ý theo tài liệu Spring LDAP Pool2: **maxTotal=-1** (không giới hạn tổng), **maxTotalPerKey=8**, **maxIdlePerKey=8**, **minIdlePerKey=0**, **maxWait=-1** (chờ không giới hạn khi block), validation mặc định không bật và evictor mặc định không chạy định kỳ. Không nên sao chép nguyên default cho dịch vụ production rồi giả định LDAP server tự chịu được tải vô hạn.

### 3.1. maxTotal khác maxTotalPerKey

Giả sử pool dùng hai key READ và WRITE:

~~~text
maxTotal = 12
maxTotalPerKey = 8

Trạng thái A:
  READ  = 8 context (active + idle)
  WRITE = 4 context (active + idle)
  TOTAL = 12 -> chạm giới hạn toàn pool

Trạng thái B:
  READ  = 8 context
  WRITE = 0 context
  TOTAL = 8, nhưng READ đã chạm giới hạn per-key
~~~

Ở B, request READ tiếp theo có thể phải đợi dù toàn pool còn 4 chỗ. **maxTotal** dùng để kiểm soát ngân sách toàn bean; **maxTotalPerKey** kiểm soát mức dành cho mỗi loại context. Key của Pool2 không tự động tương ứng với mỗi người dùng LDAP có uid khác nhau.

### 3.2. maxIdlePerKey không giới hạn concurrency

Nếu **maxIdlePerKey=4**, **maxTotalPerKey=8**, vẫn có thể có tới 8 context READ active đồng thời khi còn capacity chung. Khi tất cả request kết thúc và context được trả, pool chỉ giữ số idle không vượt giới hạn đã chọn.

**maxIdle quá thấp** khiến context được tạo/đóng liên tục khi tải dao động; **maxIdle quá cao** giữ lại nhiều socket TLS và phiên LDAP không dùng tới. Không suy ra maxIdle là giá trị tối đa của tổng kết nối.

### 3.3. minIdlePerKey là mục tiêu, không phải lời hứa ngay khi start

**minIdlePerKey=1** không có nghĩa ứng dụng luôn có sẵn một socket idle ngay từ lúc Spring context khởi tạo. Việc bổ sung context idle phụ thuộc cách Commons Pool2 bảo trì, nhu cầu sử dụng, lịch evictor và giới hạn tổng. Muốn duy trì idle theo chu kỳ, cần đặt **timeBetweenEvictionRunsMillis** dương và kiểm chứng trên phiên bản pool đang sử dụng.

Với các giới hạn hữu hạn, nên giữ **minIdlePerKey ≤ maxIdlePerKey ≤ maxTotalPerKey**. Cấu hình trái ngược thường không tạo hành vi người viết mong muốn.

## 4. Phân biệt bốn loại thời gian chờ

| Loại | Cấu hình | Ý nghĩa |
| --- | --- | --- |
| **Pool borrow wait** | **PoolConfig.setMaxWaitMillis(1500)** | Thời gian chờ mượn context khi pool cạn |
| **TCP connect timeout** | **com.sun.jndi.ldap.connect.timeout=3000** | Thời gian chờ mở TCP khi tạo kết nối mới |
| **LDAP read timeout** | **com.sun.jndi.ldap.read.timeout=5000** | Thời gian chờ phản hồi của một thao tác LDAP |
| **Search time limit** | **SearchControls.setTimeLimit(4000)** | Giới hạn riêng cho thao tác tìm kiếm |

Một request có thể phải trải qua nhiều giai đoạn:

~~~text
Pool đạt trần              -> đợi borrow wait
Nhận được context bị hỏng  -> validator loại bỏ, có thể tạo cái khác
Mở socket mới              -> TCP connect timeout
LDAP Bind/Search           -> LDAP read timeout
Search quá phức tạp        -> search time limit từ client/server
~~~

Không thể cộng các giá trị này rồi tuyên bố một request luôn kết thúc trong tổng đó. Ứng dụng có thể thử nhiều LDAP URL, thực hiện referral, gọi nhiều truy vấn hoặc retry. **Deadline cấp HTTP/job** phải được tính và giám sát riêng.

Nếu **blockWhenExhausted=false**, pool có thể báo lỗi ngay khi hết chỗ; nếu bật chờ, **maxWaitMillis** cần hữu hạn để tránh tích tụ thread.

## 5. Cấu hình Pool2 trong ứng dụng Spring Boot

Trong Spring Boot dùng **spring-boot-starter-data-ldap**, có thể cấu hình **PooledContextSource** bằng Java. Không mặc định Spring Boot có sẵn property auto-bind tên **spring.ldap.pool.max-total**; dưới đây dùng namespace **directory.ldap.*** do dự án tự định nghĩa.

Ví dụ **application.yml**:

~~~yaml
directory:
  ldap:
    url: "ldaps://ldap.lab.example:636"
    base: "dc=lab,dc=example"
    bind-dn: "uid=reader,ou=services,dc=lab,dc=example"
    bind-password: "${LDAP_BIND_PASSWORD}"
    pool:
      max-total: 12
      max-total-per-key: 8
      max-idle-per-key: 4
      min-idle-per-key: 1
      max-wait-millis: 1500
      eviction-interval-millis: 30000
      min-evictable-idle-millis: 120000
~~~

Ví dụ Java Configuration:

~~~java
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration(proxyBeanMethods = false)
public class LdapPoolConfiguration {

    @Bean("targetLdapContextSource")
    LdapContextSource targetContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.bind-dn}") String bindDn,
            @Value("${directory.ldap.bind-password}") String password) {

        LdapContextSource target = new LdapContextSource();
        target.setUrl(url);
        target.setBase(base);
        target.setUserDn(bindDn);
        target.setPassword(password);
        // Không bật native JNDI pool bên dưới Pool2.
        target.setPooled(false);
        target.setBaseEnvironmentProperties(Map.of(
            "com.sun.jndi.ldap.connect.timeout", "3000",
            "com.sun.jndi.ldap.read.timeout", "5000"
        ));
        return target;
    }

    @Bean("pooledContextSource")
    @Primary
    PooledContextSource pooledContextSource(
            @Qualifier("targetLdapContextSource")
                    LdapContextSource target,
            @Value("${directory.ldap.pool.max-total}") int maxTotal,
            @Value("${directory.ldap.pool.max-total-per-key}") int maxPerKey,
            @Value("${directory.ldap.pool.max-idle-per-key}") int maxIdle,
            @Value("${directory.ldap.pool.min-idle-per-key}") int minIdle,
            @Value("${directory.ldap.pool.max-wait-millis}") long maxWait,
            @Value("${directory.ldap.pool.eviction-interval-millis}")
                    long evictionInterval,
            @Value("${directory.ldap.pool.min-evictable-idle-millis}")
                    long minEvictableIdle) {

        PoolConfig settings = new PoolConfig();
        settings.setMaxTotal(maxTotal);
        settings.setMaxTotalPerKey(maxPerKey);
        settings.setMaxIdlePerKey(maxIdle);
        settings.setMinIdlePerKey(minIdle);
        settings.setMaxWaitMillis(maxWait);
        settings.setBlockWhenExhausted(true);
        settings.setTimeBetweenEvictionRunsMillis(evictionInterval);
        settings.setMinEvictableIdleTimeMillis(minEvictableIdle);
        settings.setNumTestsPerEvictionRun(3);
        settings.setTestOnBorrow(true);
        settings.setTestWhileIdle(true);

        PooledContextSource pool = new PooledContextSource(settings);
        pool.setContextSource(target);
        pool.setDirContextValidator(new DefaultDirContextValidator());
        return pool;
    }

    @Bean("ldapTemplate")
    LdapTemplate ldapTemplate(
            @Qualifier("pooledContextSource") ContextSource pooled) {
        return new LdapTemplate(pooled);
    }
}
~~~

Các giá trị **12/8/4/1** và **1500/30000/120000 ms** là **ví dụ thực hành**, không phải cấu hình phù hợp mọi workload. Trên thực tế, hãy điều chỉnh theo latency và kết nối cho phép của directory.

### 5.1. Kết nối repository qua đúng pool

Trong Spring Data LDAP, repository thông thường tìm bean tên **ldapTemplate**. Nếu tự bật repository, có thể dùng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration(proxyBeanMethods = false)
@EnableLdapRepositories(
    basePackages = "org.example.directory",
    ldapTemplateRef = "ldapTemplate"
)
class LdapRepositoryConfiguration {
}
~~~

Đoạn package **org.example.directory** là minh họa; khi đưa vào dự án, thay bằng package chứa repository thật. Nếu Boot đã phát hiện repository tự động, không khai báo trùng cơ chế scan khi không cần. Bean **targetLdapContextSource** và **pooledContextSource** cùng là ContextSource; **@Primary** và **@Qualifier** xác định template sử dụng đúng wrapper pool.

### 5.2. Dependency Commons Pool2

Ngoài starter Data LDAP, hãy xác nhận classpath chứa **org.springframework.ldap.pool2.factory.PooledContextSource** và **org.apache.commons.pool2**. Với BOM quản lý phiên bản phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-pool2</artifactId>
    </dependency>
</dependencies>
~~~

Hoặc Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.apache.commons:commons-pool2'
}
~~~

Hai ví dụ giả định dự án có **Spring Boot dependency management** phù hợp. Nếu tự cấu hình Spring LDAP không qua starter/BOM, cần dùng bộ phiên bản tương thích, không để nhiều đời Commons Pool và Spring LDAP bị trộn.

### 5.3. Validator không phải tùy chọn khi bật validation

Theo API Spring LDAP, khi bật **testOnBorrow**, **testOnReturn** hoặc **testWhileIdle**, cần **DirContextValidator**. **DefaultDirContextValidator** thực hiện một tìm kiếm LDAP nhẹ, mặc định base rỗng tương đối với context, scope OBJECT, filter **(objectClass=*)**, giới hạn một kết quả và time limit ngắn.

Nếu tài khoản chỉ đọc bị ACL che entry tại base hoặc cấu hình base sai, validator có thể đánh dấu context không hợp lệ ngay cả khi TCP đang mở. Kiểm tra ACL, base DN và filter validation trước khi tắt validator hoặc tăng pool.

## 6. Native JNDI pooling: maxsize, prefsize, initsize, timeout

LDAP provider mặc định trong JDK có pool riêng. Khi chọn cơ chế này, **LdapContextSource.setPooled(true)** yêu cầu native pooling. Các giới hạn kích thước quan trọng là **JVM system properties**, không phải các thuộc tính map thông thường của **spring.ldap.base-environment**.

| System property | Default theo Oracle | Ý nghĩa |
| --- | --- | --- |
| **com.sun.jndi.ldap.connect.pool.initsize** | 1 | Số connection khởi tạo cho một connection identity |
| **com.sun.jndi.ldap.connect.pool.maxsize** | Không giới hạn | Trần connection trên **mỗi identity** |
| **com.sun.jndi.ldap.connect.pool.prefsize** | Không có mức ưu tiên | Số connection ưu tiên duy trì trên mỗi identity |
| **com.sun.jndi.ldap.connect.pool.timeout** | Không đặt idle timeout | Số mili giây connection idle có thể còn trong pool |
| **com.sun.jndi.ldap.connect.pool.protocol** | plain | Loại kết nối có thể pool, như plain hoặc ssl |
| **com.sun.jndi.ldap.connect.pool.authentication** | none simple | Loại xác thực được cho phép pool |

Ví dụ khởi động JVM với giới hạn:

~~~bash
java \
  -Dcom.sun.jndi.ldap.connect.pool.initsize=2 \
  -Dcom.sun.jndi.ldap.connect.pool.maxsize=12 \
  -Dcom.sun.jndi.ldap.connect.pool.prefsize=4 \
  -Dcom.sun.jndi.ldap.connect.pool.timeout=120000 \
  -Dcom.sun.jndi.ldap.connect.pool.protocol=ssl \
  -jar application.jar
~~~

Trong bean cấu hình **chỉ dùng native JNDI pooling**:

~~~java
LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap.lab.example:636");
source.setBase("dc=lab,dc=example");
source.setUserDn("uid=reader,ou=services,dc=lab,dc=example");
source.setPassword(bindPassword);
source.setPooled(true);
// 'bindPassword' nhận từ nguồn secret được bảo vệ.
~~~

**setPooled(true)** không bảo đảm mọi context đều dùng pool: loại giao thức, phương thức xác thực, custom socket factory và các điều kiện của provider có thể khiến một kết nối không đủ điều kiện tái sử dụng.

### 6.1. prefsize KHÔNG tương đương minIdle

Theo tài liệu Oracle, **prefsize** là số connection ưu tiên duy trì **tính cả in-use và idle**, không phải “ít nhất n idle”. Nếu tổng connection hiện thấp hơn prefsize, provider có thể tạo connection mới ngay cả khi có idle. Khi tổng connection vượt prefsize và connection được trả về, provider có thể đóng phần dư.

Vì vậy **prefsize=4** không có nghĩa luôn có bốn connection rảnh và không phải bản dịch trực tiếp của **maxIdlePerKey=4** hoặc **minIdlePerKey=4** trong Pool2.

### 6.2. maxsize là theo connection identity

Một connection identity của JNDI gồm các thông tin như endpoint, protocol, cơ chế xác thực và (với simple bind) principal/credentials. Nếu một JVM kết nối nhiều LDAP host hoặc dùng nhiều tài khoản bind, **maxsize=12** có thể tương ứng với nhiều pool riêng, dẫn tới **tổng socket vượt 12**.

Native JNDI pool hoạt động trong **mỗi JVM**, không chia sẻ trực tiếp với các JVM/pod khác. Vì thế cần tính cả replication của ứng dụng.

### 6.3. Hai property có chữ timeout khác nhau

**com.sun.jndi.ldap.connect.timeout** là **JNDI environment property** để giới hạn mở TCP; khi native pool đầy, nó còn có thể giới hạn thời gian chờ mượn connection.

**com.sun.jndi.ldap.connect.pool.timeout** là **JVM system property** biểu thị thời gian idle trước khi connection có thể bị thu hồi. Không đổi chỗ hai giá trị này khi điều tra pool cạn hoặc socket idle quá lâu.

## 7. Idle eviction và validation giữ pool khỏe

LDAP server, firewall, proxy hoặc load balancer có thể đóng một socket TCP sau thời gian không hoạt động. Pool chưa chắc nhận ra ngay và vẫn giữ một context ở trạng thái idle. Request mượn lại context đó sẽ gặp lỗi liên lạc nếu không có kiểm tra.

~~~mermaid
flowchart TD
    A["Context trả về pool"] --> B["Idle trong một khoảng thời gian"]
    B --> C{"Socket đã bị server / mạng đóng?"}
    C -->|Không| D["Có thể mượn lại"]
    C -->|Có| E{"Có validation?"}
    E -->|Có| F["Loại context hỏng, tìm/tạo context hợp lệ"]
    E -->|Không| G["Request nghiệp vụ có thể nhận CommunicationException"]
~~~

Các thiết lập hỗ trợ:

- **testOnBorrow=true:** kiểm tra context trước khi cấp, giảm nguy cơ mượn socket chết nhưng tăng một round trip kiểm tra.
- **testWhileIdle=true:** kiểm tra context idle trong lượt bảo trì. Cần evictor được bật qua **timeBetweenEvictionRunsMillis** dương.
- **minEvictableIdleTimeMillis:** ngưỡng thời gian idle để xét thu hồi theo eviction rule; đặt theo thực tế timeout của load balancer/firewall.
- **numTestsPerEvictionRun:** giới hạn số context được kiểm tra trong mỗi vòng.
- **nonTransientExceptions:** với các lỗi như **javax.naming.CommunicationException**, pool có thể chủ động đánh dấu context lỗi không được tái sử dụng.

**Validation không phải bảo đảm socket sẽ sống suốt nghiệp vụ.** Mạng có thể ngắt ngay sau lần kiểm tra. Do đó vẫn cần read timeout, xử lý lỗi và retry có điều kiện.

Kiểm tra validation bằng cùng tài khoản dịch vụ:

~~~bash
ldapsearch -LLL -x -H 'ldaps://ldap.lab.example:636' \
  -D 'uid=reader,ou=services,dc=lab,dc=example' -W \
  -b 'dc=lab,dc=example' -s base \
  '(objectClass=*)' objectClass
~~~

Lệnh này chỉ giúp xác minh DN/filter/ACL của phép kiểm tra theo LDAP, **không chứng minh trực tiếp** Spring đã bật **testOnBorrow**. Khi root entry bị che bởi ACL, cần xem lại chính sách validation query cho đúng môi trường.

## 8. Sizing pool trong môi trường nhiều pod

Một giá trị **maxTotal** là giới hạn của **một bean pool ở một ứng dụng**, không phải ngân sách của cả hệ thống microservice.

~~~text
Số pod Spring Boot:                  4
maxTotal mỗi pod:                   12
Tổng giới hạn lý thuyết:    4 x 12 = 48 context

Service khác cũng dùng LDAP:        20 context
Tổng cần dự phòng:                  ~68 context
~~~

Con số trên chỉ tính **pool giới hạn theo ứng dụng**; số socket thực còn tùy traffic, context không pooled, nhiều endpoint, cách xác thực và những client LDAP khác.

Quy trình chọn giới hạn:

1. Xác nhận **LDAP server capacity** và hạn mức kết nối với quản trị directory.
2. Tính **số pod tối đa khi scale-out**, không chỉ số pod hiện có.
3. Dành ngân sách cho service khác, job đồng bộ và công cụ quản trị.
4. Chọn **maxTotal** và **maxTotalPerKey** để bảo vệ LDAP server khi tất cả pod đồng thời tăng tải.
5. Chọn **maxIdlePerKey/minIdlePerKey** theo mức tải nền và chi phí TLS/bind.
6. Chọn **maxWaitMillis** theo SLA API, bên cạnh connect/read timeout.
7. Đo **p95/p99 LDAP latency**, active, idle, waiters, tạo connection và tỷ lệ lỗi, rồi điều chỉnh dựa trên bằng chứng.

**Tăng pool không làm query kém tối ưu trở nên nhanh.** Nếu search base rộng, filter không có index hoặc quyền ACL phức tạp khiến server tốn tài nguyên, mở thêm kết nối có thể chỉ làm máy chủ LDAP quá tải hơn.

## 9. Chờ hay từ chối khi pool hết kết nối?

Giả sử **maxTotalPerKey=8**, tám request READ giữ context quá lâu, chưa context nào được trả. Request thứ chín không thể mượn từ cùng key.

| Chính sách | Lợi ích | Rủi ro |
| --- | --- | --- |
| **Block + maxWait ngắn** | Hấp thụ tăng tải ngắn hạn, không tạo socket vô hạn | Request có thể bị từ chối khi tải duy trì cao |
| **Block + maxWait vô hạn** | Có vẻ ít lỗi ngay | Hàng đợi tăng, chiếm thread và dễ vượt deadline |
| **Không block** | Trả lỗi nhanh, dễ bảo vệ hệ thống | Cần backpressure và thông báo bận rõ ràng |
| **Tăng maxTotal quá cao** | Nhiều request được cấp context hơn | Directory quá tải, latency tăng, có thể gặp giới hạn server |
| **Giới hạn concurrency ở service** | Chặn áp lực trước khi đến pool | Phải thiết kế ngưỡng phù hợp và chính sách từ chối |

Spring LDAP Pool2 có thể bọc lỗi mượn context thành **DataAccessResourceFailureException**, cause từ Commons Pool có thể thể hiện pool exhausted hoặc hết maxWait. Không coi mọi lỗi đó là **invalidCredentials**, và không chuyển thành danh sách rỗng như thể LDAP không có người dùng.

## 10. Pool và các thao tác Spring Data LDAP

Một entity/repository mẫu:

~~~java
import java.util.Optional;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.data.ldap.repository.LdapRepository;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
class DirectoryPerson {
    @Id
    Name dn;

    @Attribute(name = "uid")
    String uid;

    @Attribute(name = "cn")
    String cn;

    @Attribute(name = "sn")
    String sn;
}

interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Truy vấn **findByUid** và những thao tác **save/delete** sử dụng các context theo API Spring LDAP. Pool có thể tách loại context read-only/read-write thành các key; việc phân bổ maxTotalPerKey cần phù hợp tải thực.

**Pool không thay đổi schema hay semantics LDAP:** DN phải nằm đúng nhánh, objectClass và thuộc tính phải hợp lệ, filter cần escape đúng cách, ACL vẫn quyết định quyền đọc/ghi. Pooling cũng **không biến nhiều thao tác LDAP thành một transaction ACID**. Hai writer cùng đọc snapshot cũ và REPLACE toàn bộ thuộc tính vẫn có thể gây **lost update**.

Sau một **read timeout khi ghi**, server có thể đã thực thi Modify/Delete rồi mất phản hồi trước khi client nhận. Không retry mù quáng thao tác ghi bằng snapshot cũ; cần đối chiếu trạng thái thực và idempotency trước khi thực hiện lại.

## 11. Trả context về pool đúng cách

**LdapTemplate** thông thường quản lý việc lấy và giải phóng context của từng thao tác. Khi dùng **ContextSource** trực tiếp, lập trình viên phải đóng context trong **finally** kể cả khi lookup/search thất bại.

~~~java
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.ContextSource;

public final class ContextBorrowExample {
    private final ContextSource contextSource;

    public ContextBorrowExample(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public void validateAccessibleBase() throws NamingException {
        DirContext ctx = contextSource.getReadOnlyContext();
        try {
            // Mẫu lookup entry tại base tương đối của context.
            ctx.getAttributes("");
        } finally {
            // Với PooledContextSource, close trả wrapper về pool.
            ctx.close();
        }
    }
}
~~~

**getAttributes("")** trong ví dụ chỉ dùng để minh họa một thao tác; nó có thể thất bại nếu base không tồn tại hoặc ACL không cấp quyền đọc. Khi triển khai, nên thay bằng thao tác nghiệp vụ thực hoặc dùng **LdapTemplate** để tránh phải quản lý context thủ công.

Không giữ **DirContext** trong field singleton dùng chung cho mọi request. Context có trạng thái kết nối, xác thực và có thể không an toàn khi chia sẻ tùy tiện giữa thread. Pool cung cấp cách **mượn–sử dụng–trả** đúng vòng đời.

Nếu mã quên gọi close ở một nhánh exception, số **active** tăng dần dù request đã kết thúc. Sau một thời gian, mọi thread khác chờ maxWait rồi lỗi. Đó là **connection leak**, không nhất thiết là directory server quá tải.

### 11.1. Đóng ApplicationContext để giải phóng pool

**PooledContextSource** triển khai **DisposableBean**, cho phép Spring gọi **destroy()** trong quá trình hủy bean để đóng pool. Trong môi trường có tự tạo/dừng context liên tục như integration test, phải đảm bảo mỗi ApplicationContext được đóng phù hợp. Một pool bị bỏ lại sau redeploy hoặc test teardown có thể giữ socket và thread bảo trì.

Các context đã mượn mà ứng dụng không trả kịp có thể ảnh hưởng tốc độ shutdown; không dựa vào garbage collector để giải phóng tài nguyên thay cho code cleanup đúng.

## 12. Bảo mật: không dùng pool dịch vụ cho bind động theo người dùng

Một rủi ro nghiêm trọng là nhầm **tài khoản dịch vụ cố định** với **tài khoản LDAP của từng người dùng**:

~~~text
Request A: user A được bind theo ACL của A
Request B: user B cần bind theo ACL của B

Nếu cùng pool trả lại context đã bind theo A cho request B:
  B có thể thao tác với danh tính và quyền không đúng.
~~~

Theo cảnh báo của Spring LDAP, **PoolingContextSource** kiểu pool READ/WRITE giả định context từ cùng nhánh lấy có environment ổn định. Khi bọc **LdapContextSource** dùng **AuthenticationSource** thay đổi credentials theo từng request, pool có thể tái sử dụng một context đã bind bằng credentials của request trước. Vì vậy:

- Dùng pool được cấu hình ở phần 5 **cho một service bind identity cố định** khi đọc/ghi directory theo quyền dịch vụ.
- Với xác thực người dùng, cân nhắc luồng **Spring Security LDAP authentication** đúng thiết kế; không lấy context service để thử mật khẩu của từng user.
- Nếu phải có nhiều danh tính bind dịch vụ, thiết kế ContextSource/pool riêng biệt hoặc cơ chế phân tách danh tính đã được kiểm chứng; không coi pool key READ/WRITE là user ID.
- Dùng **LDAPS hoặc StartTLS** có kiểm tra CA và hostname. Không truyền simple bind credentials qua **ldap://** không mã hóa trên mạng thiếu tin cậy.
- Không hardcode **LDAP_BIND_PASSWORD** hay in **Context.SECURITY_CREDENTIALS**, pooled context environment hoặc biến secret ra log.
- Bind DN đọc cần **ACL quyền tối thiểu**; getReadOnlyContext không thay thế ACL do server kiểm tra.

### 12.1. Native pool và StartTLS

**StartTLS** nâng cấp kết nối LDAP sang TLS sau khi một context đã được khởi tạo. Oracle lưu ý rằng native JNDI pooling **không theo dõi an toàn mọi thay đổi trạng thái kết nối**, như StartTLS hoặc việc thay đổi security properties sau khi tạo context. Không dùng native pooling trên context có thao tác làm thay đổi trạng thái bảo mật mà provider không thể quản lý.

Đối với **LDAPS**, native pooling chỉ áp dụng cho giao thức SSL khi cấu hình protocol cho phép, và vẫn cần xác minh TLS đúng cách. Nếu dùng Pool2, phải kiểm thử lifecycle TLS, validator và chính sách xoay mật khẩu bind trên từng server, không suy ra rằng hai loại pool có hành vi bảo mật giống nhau.

### 12.2. Xoay vòng mật khẩu dịch vụ

Nếu password của bind DN thay đổi, context idle có thể giữ trạng thái authenticated đã tạo trước đó. Không mặc định sửa secret ở application properties khiến mọi connection sẵn có tự **rebind** bằng mật khẩu mới ngay lập tức.

Một quy trình vận hành có thể cần **thay thế/recreate pool**, loại context cũ, cập nhật secret và xác minh login/truy vấn với danh tính mới. Khi làm việc với directory dùng nhiều replica, còn phải tính thời gian đồng bộ mật khẩu và chính sách xác thực phía server.

## 13. Quan sát active, idle và waiters

Spring LDAP **PooledContextSource** cung cấp một số getter giúp chẩn đoán:

| Getter | Số liệu |
| --- | --- |
| **getNumActive()** | Tổng context đang được mượn |
| **getNumIdle()** | Tổng context nhàn rỗi |
| **getNumWaiters()** | Thread đang đợi mượn context |
| **getNumActiveRead()** | Context READ active |
| **getNumActiveWrite()** | Context WRITE active |
| **getNumIdleRead()** | Context READ idle |
| **getNumIdleWrite()** | Context WRITE idle |

Một DTO snapshot nhỏ:

~~~java
import org.springframework.ldap.pool2.factory.PooledContextSource;

public record LdapPoolSnapshot(
        int active,
        int idle,
        int waiting,
        int activeRead,
        int activeWrite,
        int idleRead,
        int idleWrite) {

    public static LdapPoolSnapshot capture(PooledContextSource pool) {
        return new LdapPoolSnapshot(
            pool.getNumActive(),
            pool.getNumIdle(),
            pool.getNumWaiters(),
            pool.getNumActiveRead(),
            pool.getNumActiveWrite(),
            pool.getNumIdleRead(),
            pool.getNumIdleWrite()
        );
    }
}
~~~

Các getter được gọi lần lượt nên đây là **snapshot gần đúng**, không phải giao dịch chụp đồng thời tất cả bộ đếm. Chúng vẫn hữu ích khi đưa vào hệ thống metric, log vận hành nội bộ hoặc JMX có kiểm soát.

### 13.1. Đọc metric để tìm nguyên nhân

| Quan sát | Cần kiểm tra |
| --- | --- |
| Active thường chạm maxTotal | Pool nhỏ hoặc tác vụ LDAP chiếm context lâu |
| Active READ chạm maxTotalPerKey nhưng total còn dư | Giới hạn per-key đang chặn workload READ |
| Waiters tăng liên tục | Quá nhiều request tranh context; cần backpressure và kiểm tra query latency |
| Idle luôn 0, số TLS handshake lớn | maxIdle quá thấp hoặc context bị loại thường xuyên |
| Idle nhiều trong thời gian dài | maxIdle/minIdle quá cao so với nhu cầu |
| Sau request active không giảm | Có thể leak context, request chưa hoàn tất hoặc thread bị treo |
| Validation thất bại liên tục | Socket idle chết, ACL/base validator sai hoặc LDAP server bất ổn |
| Sau tăng pool, LDAP server chậm hơn | Có thể đã tăng contention/tải vượt capacity phía server |

Nên thu thập đồng thời **p50/p95/p99 LDAP latency**, số bind/TLS handshake, số timeout theo loại, LDAP error code, connection count phía server và số pod hiện có. Không chỉ nhìn idle cao hay thấp mà kết luận pool đã được tối ưu.

### 13.2. Metric không được làm lộ dữ liệu nhạy cảm

Ghi nhãn metric theo service, environment và endpoint đã được duyệt; tránh dùng **uid/email của người dùng** làm label có số lượng giá trị cực lớn. Không đưa password hoặc full connection environment vào metric/trace. Giới hạn quyền xem nội dung log chứa DN và tên nhóm khi cần tuân thủ chính sách dữ liệu nội bộ.

## 14. Kiểm thử giới hạn và hết thời gian chờ

Cấu hình không thể được xác nhận chỉ bằng việc đọc YAML. Cần chạy **integration test** với directory lab hoặc test double/proxy hỗ trợ mô phỏng chậm và ngắt kết nối.

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Mượn–trả bình thường | Chạy nhiều search tuần tự | Active trở lại 0, có idle tùy giới hạn |
| Chạm maxTotalPerKey | Giữ đủ context READ, mượn thêm READ | Chờ hoặc lỗi, không tạo vượt trần |
| Chạm maxTotal | Giữ đủ context READ/WRITE để đầy pool | Không cấp thêm context khi hết capacity chung |
| **maxWaitMillis** | Giữ toàn bộ context quá thời gian wait | Borrow thất bại thay vì đợi vô hạn |
| **blockWhenExhausted=false** | Mượn khi pool hết chỗ | Fail fast |
| **maxIdlePerKey** | Mượn nhiều context rồi trả hết | Idle giữ lại không vượt giới hạn |
| **minIdlePerKey** | Bật evictor và đợi chu kỳ bảo trì | Pool cố duy trì idle mục tiêu khi có capacity |
| Socket idle bị ngắt | Proxy đóng socket sau khi trả pool | Validator loại bỏ kết nối hỏng khi được kiểm tra |
| Validator bị ACL chặn | Dùng reader không thể tìm base entry | Xác định lỗi validation; không hiểu nhầm là pool size nhỏ |
| Nhiều instance | Chạy tải với số pod cực đại | Tổng connection trên LDAP server được theo dõi và giới hạn |
| Shutdown | Đóng Spring context | Pool được destroy, không để lại thread/socket |

### 14.1. Kiểm thử pool exhausted có tính xác định

Đặt pool test:

~~~text
maxTotal = 1
maxTotalPerKey = 1
maxIdlePerKey = 1
minIdlePerKey = 0
maxWaitMillis = 200
blockWhenExhausted = true
~~~

Thực hiện lần lượt:

1. Thread A gọi **pool.getReadOnlyContext()**, giữ context và **chưa close**.
2. Sau khi A đã mượn xong, thread B cũng gọi **pool.getReadOnlyContext()**.
3. B phải đợi và sau đó thất bại vì không có context cùng key được trả trong khoảng borrow wait.
4. Xác minh cause liên quan **pool exhaustion**, không phải lỗi password hoặc search base.
5. Thread A luôn close trong **finally**; sau đó mượn lại được context.

Để đồng bộ hai thread, dùng **CountDownLatch** hoặc barrier thay vì **Thread.sleep** ngẫu nhiên. Phép đo thời gian thực tế có thể chịu ảnh hưởng scheduling; test nên dùng một khoảng dung sai thay vì đòi chính xác 200 ms từng mili giây.

### 14.2. Kiểm thử idle socket bị đóng

Một LDAP test double hoặc network proxy có thể mô phỏng:

~~~text
T0: Client mượn context, search thành công.
T1: Context trả về pool -> idle.
T2: Proxy/server đóng TCP socket nhưng client chưa nhận biết.
T3: Client mượn lại.
T4: Validation phát hiện lỗi, loại context và tạo/mượn cái hợp lệ.
~~~

So sánh test với **testOnBorrow=false/true** và ghi số lần lỗi, connection được tạo lại và latency. Không nên cắt kết nối hoặc gây tải vào directory production để thực hiện loại thử nghiệm này. Nếu môi trường dùng LDAPS, giữ nguyên bước xác minh chứng chỉ.

### 14.3. Thử nghiệm với server nhúng và server thật

Server nhúng (ví dụ UnboundID) có thể giúp kiểm tra **DN, objectClass, filter, CRUD và tương tác context**. Tuy nhiên, các đặc tính **OpenLDAP ACL**, timeout sau load balancer, StartTLS hay replication không nhất thiết giống với UnboundID. Cần integration test bổ sung với chính loại directory/server mục tiêu nếu các đặc tính đó quan trọng cho vận hành.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có khả năng | Hướng xử lý |
| --- | --- | --- |
| Pool luôn hết connection | Giới hạn thấp, leak context hoặc LDAP request chậm | Đo active/waiters, kiểm tra close và query latency |
| maxIdle=4 nhưng thấy 8 active | Nhầm giới hạn idle với giới hạn active | Xem maxTotal/maxTotalPerKey |
| minIdle=2 nhưng lúc start thấy 0 | Min idle là mục tiêu bảo trì, không bảo đảm tạo ngay | Kiểm tra chu kỳ evictor và nhu cầu mượn |
| Pool vẫn chờ rất lâu dù connect.timeout nhỏ | Pool2 dùng maxWaitMillis riêng | Kiểm tra blockWhenExhausted và maxWaitMillis |
| JNDI maxsize=12 nhưng hơn 12 socket | Có nhiều connection identities | Đếm endpoint/credentials/instance |
| pool.timeout hiểu nhầm là borrow wait | Đây là idle timeout của native JNDI | Dùng connect.timeout cho native wait |
| Đặt JNDI maxsize trong Spring base-environment nhưng không có hiệu lực | maxsize là JVM system property | Đặt -D trước khi JVM khởi tạo pool |
| testOnBorrow bật thì liên tục lỗi | Validator thiếu hoặc query bị ACL/base chặn | Cấu hình validator, kiểm tra chính quyền của bind DN |
| Repository dùng pool nhưng LdapTemplate không | Bean ContextSource/template khác nhau | Xem @Primary, @Qualifier và ldapTemplateRef |
| Nhiều người dùng thấy quyền lẫn nhau | Pool với AuthenticationSource động | Cách ly danh tính; không dùng pool service chung |
| StartTLS gặp lỗi khó đoán | Native pool và connection security state không tương thích | Theo hướng dẫn provider; kiểm tra TLS lifecycle |
| Read timeout khi Modify gây dữ liệu bất ngờ | Lệnh ghi có thể đã thành công trên server | Đối chiếu trạng thái trước khi retry |
| Số socket tăng mạnh sau scale-out | Mỗi pod có pool riêng | Tính ngân sách theo tổng số instance |
| close context nhưng socket chưa biến mất | Context đã trả pool để tái sử dụng | Đúng behavior; kiểm tra idle eviction |

**Phân biệt lỗi LDAP và lỗi pool:** **invalidCredentials (49)**, **noSuchObject (32)**, **insufficientAccessRights (50)** và **objectClassViolation (65)** liên quan bind, DN, ACL hoặc schema. Tăng maxTotal không giải quyết các lỗi đó.

## 16. Bài thực hành có dữ liệu LDAP

Chuẩn bị directory lab với cây:

~~~text
dc=lab,dc=example
├── ou=people
│   └── uid=linh
└── ou=services
    └── uid=reader
~~~

Ví dụ entry người dùng:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
~~~

Directory lab cần root, các OU và tài khoản reader đã được tạo hợp lệ, có ACL cần thiết, kết nối LDAPS và chứng chỉ được tin cậy. Không đặt mật khẩu thật vào dữ liệu mẫu.

Mã LdapTemplate để tạo tải truy vấn minh họa:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PeopleLookup {
    private final LdapTemplate ldapTemplate;

    public PeopleLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        return ldapTemplate.search(
            query().base("ou=people")
                   .where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );
    }
}
~~~

Với ContextSource base **dc=lab,dc=example**, query base **ou=people** là DN tương đối. Thao tác tìm kiếm vẫn phụ thuộc LDAP filter, schema và ACL; pool không tạo dữ liệu LDAP.

**Quy trình thực hành:**

1. Cấu hình Pool2 nhỏ: maxTotal=2, maxTotalPerKey=2, maxIdlePerKey=1, minIdlePerKey=0, maxWaitMillis=500.
2. Chạy **findCommonNames("linh")** và xác nhận trả đúng **cn**.
3. Ghi snapshot **active/idle/waiters** trước/sau nhiều lượt search.
4. Mượn hai context READ và giữ chúng, cho thread khác thử mượn context thứ ba.
5. Đối chiếu lỗi borrow wait, rồi đóng hai context trong **finally**.
6. Trả nhiều context và kiểm tra số idle giữ lại không vượt giới hạn đã chọn.
7. Bật testOnBorrow cùng validator; trong lab, thử để proxy ngắt một socket idle.
8. Dùng nhiều worker tạo tải có kiểm soát; đo p95/p99, số connection server, lỗi và waiters.
9. Làm một phép thử **riêng** với native JNDI pooling để so sánh; không lồng hai pool.
10. Ghi lại lý do chọn giới hạn và những thay đổi cần làm trước khi vận hành production.

## 17. Câu hỏi tự kiểm tra, ghi nhớ và tài liệu

**Câu hỏi tự kiểm tra:**

1. Vì sao **maxIdlePerKey=4** không có nghĩa tối đa bốn request LDAP đồng thời?
2. **maxTotal** khác **maxTotalPerKey** khi có cả read/write contexts ra sao?
3. **minIdlePerKey=1** có bảo đảm một socket sẵn có ngay khi JVM khởi động không?
4. **maxWaitMillis** khác connect timeout, read timeout và search time limit ở đâu?
5. **JNDI prefsize** có tương đương **minIdlePerKey** của Pool2 không?
6. Vì sao **JNDI maxsize=12** vẫn có thể dẫn đến hơn 12 LDAP socket trên một JVM?
7. Tại sao phải cấu hình **DirContextValidator** khi bật testOnBorrow/testWhileIdle?
8. Nếu waiters cao và LDAP server CPU cũng cao, có nên tăng maxTotal ngay không?
9. **close()** trên context pool khác đóng socket TCP vật lý như thế nào?
10. Tại sao không pooling một cách mù quáng context bind theo người dùng?
11. Vì sao một timeout của Modify không chứng minh server chưa ghi dữ liệu?
12. Với bốn pod cùng cấu hình, bạn tính ngân sách kết nối phía server thế nào?

**Ghi nhớ:** Chọn **một cơ chế pooling** rồi cấu hình đúng phạm vi. Với **Spring LDAP Pool2**, dùng **PooledContextSource + PoolConfig** để đặt **maxTotal**, **maxTotalPerKey**, **maxIdlePerKey**, **minIdlePerKey** và **maxWaitMillis**, đồng thời cấu hình validator/idle eviction. Với **native JNDI pool**, kích thước **maxsize/prefsize/initsize** và idle timeout là **JVM system properties** theo connection identity, không phải tên tương đương của Pool2. Pooling giúp tái sử dụng kết nối nhưng không thay thế timeout mạng, kiểm soát ACL/schema, TLS, concurrency hay deadline ứng dụng.

### Tài liệu tham khảo

- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): hai cơ chế pool, giới hạn, validation và lưu ý authentication.
- [Spring LDAP — PoolConfig API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PoolConfig.html): các setter giới hạn số lượng, idle, maxWait và eviction.
- [Spring LDAP — PooledContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html): pool wrapper, thống kê active/idle/waiters và lifecycle.
- [Spring LDAP — DefaultDirContextValidator API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/validation/DefaultDirContextValidator.html): validation query và giới hạn.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): cách bật native JNDI pooling và điều kiện dùng.
- [Oracle — JNDI Connection Pooling Configuration](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/config.html): maxsize, initsize, prefsize, timeout và connection identity.
- [Oracle — JNDI LDAP Connection Pooling](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/pool.html): borrow wait, chờ TCP và cảnh báo StartTLS.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): repository sử dụng LdapTemplate.
- [Apache Commons Pool 2 — GenericKeyedObjectPool](https://commons.apache.org/proper/commons-pool/apidocs/org/apache/commons/pool2/impl/GenericKeyedObjectPool.html): cơ chế keyed pool.
