# Thu hồi kết nối hỏng và phản ứng với `CommunicationException` trong pool LDAP

## 1. Vì sao một pool còn kết nối nhưng ứng dụng vẫn báo lỗi?

Trong **Spring Data LDAP**, `LdapRepository` và `LdapTemplate` thực hiện tra cứu, CRUD và ánh xạ entry từ directory. Entry được định danh bằng **DN** (*Distinguished Name*), có `objectClass` và các thuộc tính hợp lệ theo schema. Phần kết nối nằm phía dưới repository: Spring LDAP dùng `ContextSource` để lấy `DirContext`/`LdapContext` của JNDI và giao tiếp với LDAP server.

Để giảm chi phí tạo kết nối và bind lặp lại, ứng dụng có thể dùng **LDAP connection pool**. Nhưng một `DirContext` từng hoạt động không nhất thiết còn dùng được sau vài phút idle. Trong thực tế có thể xảy ra:

- Firewall, load balancer hoặc NAT đóng kết nối TCP không hoạt động.
- LDAP server restart, failover hoặc chủ động đóng phiên.
- Đường mạng bị gián đoạn khi Search/Modify đang chạy.
- DNS hoặc địa chỉ server thay đổi giữa các đợt triển khai.
- Credential, chính sách tài khoản hoặc TLS configuration thay đổi.
- Một tiến trình đã giữ context lâu hơn vòng đời mà pool dự kiến.

Lúc đó, pool có thể có **idle context** nhưng một thao tác kế tiếp mới phát hiện socket đã chết và báo `CommunicationException`.

Bài học tập trung vào hai trách nhiệm tách biệt:

1. **Quản lý kết nối:** phát hiện và **loại bỏ `DirContext` không còn đáng tin**, không cho context hỏng quay về hàng đợi idle để phục vụ request sau.
2. **Quản lý nghiệp vụ:** xử lý kết quả thao tác vừa thất bại một cách đúng đắn, gồm timeout, retry giới hạn, idempotency và tình huống **không biết LDAP server đã ghi thành công hay chưa**.

> **Nguyên tắc cốt lõi:** Loại bỏ kết nối hỏng giúp lần mượn sau có cơ hội nhận kết nối khỏe. Nó **không** chứng minh thao tác trước thất bại trên server và **không** có nghĩa mọi lệnh ghi đều được phép tự động chạy lại.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Trình bày vòng đời `ContextSource` → pool → `LdapTemplate`/repository → JNDI → LDAP server.
- Phân biệt `javax.naming.CommunicationException` và `org.springframework.ldap.CommunicationException`.
- Cấu hình `PooledContextSource` dựa trên Commons Pool 2, tự loại context lỗi và kiểm tra kết nối.
- Hiểu khác biệt giữa `testOnBorrow`, `testOnReturn`, `testWhileIdle` và timeout.
- Quyết định khi nào retry một **Search/Lookup**, và khi nào phải **đối soát trạng thái** trước khi retry CRUD.
- Thiết kế kiểm thử có ngắt kết nối, server restart và quan sát số lượng active/idle context mà không làm rò rỉ dữ liệu.

## 2. Vị trí của pool trong kiến trúc Spring Data LDAP

Một ứng dụng Spring Boot có thể có chuỗi xử lý:

~~~mermaid
flowchart TD
    A["REST API / Batch / Service"] --> B["LdapRepository proxy"]
    A --> C["LdapTemplate"]
    B --> C
    C --> D["ContextSource được pool hóa"]
    D --> E{"Borrow DirContext"}
    E --> F["Pool: idle / active / validation"]
    F --> G["LdapContextSource bên dưới"]
    G --> H["JNDI LDAP provider"]
    H --> I["LDAP server: Search / Modify / Add / Delete"]
    I --> H
    H --> F
    F --> J["Return nếu khỏe, invalidate nếu hỏng"]
~~~

Mỗi tầng có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Không tự bảo đảm |
| --- | --- | --- |
| `LdapRepository` | Repository CRUD, query methods, ODM mapping | Không cung cấp kết nối khỏe vĩnh viễn hay transaction nhiều entry |
| `LdapTemplate` | Gọi thao tác LDAP, quản lý context/callback, chuyển đổi exception | Không tự động thực hiện lại thao tác ghi không an toàn |
| `ContextSource` | Cấp context có cấu hình URL/base DN/bind identity | Không bảo đảm server luôn đang chạy |
| `PooledContextSource` | Cho mượn, nhận lại, validate và loại context hỏng | Không biết nghiệp vụ đã commit hay chưa |
| JNDI `DirContext` | Thực hiện LDAP operation qua kết nối và provider | Không phải một Java object bất biến trước lỗi mạng |
| LDAP server | Áp dụng schema, ACL, giới hạn và state của entry | Không cam kết idempotency chung cho mọi Add/Modify/Delete |

Nếu cấu hình base DN là `dc=example,dc=org`, repository có thể đọc entry `uid=alice,ou=people`. Nhưng pool **không thay đổi DN**, LDAP filter hay quyền truy cập: nó chỉ thay đổi cách một operation lấy và trả kết nối.

### 2.1. Trạng thái kết nối khác trạng thái LDAP entry

Giả sử service đang thay `mail` của Alice:

~~~text
DN: uid=alice,ou=people,dc=example,dc=org

Trước thao tác:
  mail: old@example.org

Yêu cầu Modify:
  REPLACE mail -> new@example.org
~~~

Nếu socket đứt khi chờ response, hai tình huống có thể trông giống nhau ở phía client:

- **Tình huống A:** Request chưa tới server; `mail` chưa đổi.
- **Tình huống B:** Server đã thay `mail` thành công nhưng response bị mất.

Cả hai có thể tạo lỗi giao tiếp. Vì vậy, dù pool đã loại context lỗi, ứng dụng **chưa biết trạng thái nghiệp vụ**. Phải đọc lại hoặc dùng cơ chế đối soát trước khi quyết định chạy lại một thao tác ghi.

## 3. `CommunicationException` xuất hiện ở tầng nào?

### 3.1. JNDI exception và Spring LDAP exception

JNDI dùng:

~~~java
javax.naming.CommunicationException
~~~

Spring LDAP có runtime exception phản chiếu:

~~~java
org.springframework.ldap.CommunicationException
~~~

Trong một đường gọi điển hình, `LdapTemplate` sẽ chuyển đổi exception của JNDI thành exception thuộc hierarchy Spring LDAP. Bởi vậy, service dùng `LdapTemplate` hoặc repository thường bắt **`org.springframework.ldap.CommunicationException`**, còn cơ chế pool kiểm tra lỗi trên **`DirContext` bên dưới** có thể nhìn thấy **`javax.naming.CommunicationException`**.

~~~text
Socket read/write lỗi
  -> JNDI DirContext ném javax.naming.CommunicationException
  -> Pool wrapper thấy lỗi ở context và đánh dấu hỏng
  -> LdapTemplate chuyển lỗi thành Spring LDAP exception
  -> Repository/Service nhận org.springframework.ldap.CommunicationException
~~~

Đây là luồng thường gặp, không phải cam kết mọi exception mạng đều đi qua cùng một đường chính xác. Khi lỗi phát sinh **ngay trong lúc mượn/tạo context**, ứng dụng còn có thể thấy `DataAccessResourceFailureException`, lỗi timeout hoặc exception bọc khác. Khi chẩn đoán, hãy ghi nhận **loại exception ngoài cùng và root cause**, tránh suy luận chỉ từ một tên lớp.

Ví dụ bắt lỗi ở service:

~~~java
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.LdapTemplate;

public final class DirectoryReader {

    private final LdapTemplate ldapTemplate;

    public DirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readCommonName() {
        try {
            return ldapTemplate.lookup(
                "uid=alice,ou=people",
                new String[] {"cn"},
                attributes -> {
                    var cn = attributes.get("cn");
                    return cn == null ? null : (String) cn.get();
                }
            );
        } catch (CommunicationException ex) {
            // Ghi metadata vận hành có kiểm soát và báo lỗi lên lớp gọi.
            // Không tự coi đây là "entry không tồn tại".
            throw ex;
        }
    }
}
~~~

Ví dụ trên **không tự thực hiện retry**. Nó nhấn mạnh sự khác biệt giữa lỗi giao tiếp và một kết quả Search rỗng hợp lệ.

### 3.2. Không phải mọi LDAP exception đều là kết nối hỏng

| Dấu hiệu | Bản chất thường gặp | Có nên coi là context hỏng? |
| --- | --- | --- |
| JNDI `CommunicationException` | Giao tiếp mạng/kết nối thất bại | **Có**, loại context là hướng xử lý chuẩn của pool |
| LDAP `invalidCredentials` (49) | Bind DN/password hoặc trạng thái account | Không mặc định; cần sửa credential/policy |
| LDAP `insufficientAccessRights` (50) | ACL từ chối Search/Modify | Không; không retry với admin account |
| LDAP `noSuchObject` (32) | DN hoặc search base không tồn tại/không nhìn thấy | Không; xác minh DN/schema/scope |
| LDAP `objectClassViolation` (65) | Entry không phù hợp schema | Không; sửa dữ liệu/`objectClass` |
| LDAP `unavailable` (52) | Server từ chối hoặc chưa sẵn sàng | Cần phân loại và kiểm tra; không đồng nghĩa mọi context hỏng |
| LDAP `busy` (51) | Server đang quá tải | Backoff và kiểm soát tải; không nhất thiết là socket chết |
| SSL handshake/PKIX error | Truststore, CA, hostname, giao thức TLS | Không lặp vô hạn; sửa cấu hình bảo mật |
| Hết thời gian mượn pool | Cạn active contexts hoặc context không trả | Kiểm tra pool saturation/leak; không mặc định LDAP server mất kết nối |
| Lỗi parse/mapping ODM | `@Entry`, `@Attribute`, conversion | Không; cần xử lý mapping, không reset pool |

Pool nên phân loại **lỗi kết nối** ở tầng transport, không loại sạch mọi connection mỗi khi ứng dụng không tìm thấy entry. Ngược lại, thao tác nghiệp vụ không được coi một `CommunicationException` là danh sách rỗng, vì có thể che một sự cố LDAP đang ảnh hưởng phân quyền.

## 4. Pool thực hiện thu hồi kết nối như thế nào?

### 4.1. Borrow → use → return hoặc invalidate

~~~mermaid
stateDiagram-v2
    [*] --> New: Pool tạo context
    New --> Idle: Khởi tạo thành công
    Idle --> Validation: Borrow + testOnBorrow
    Validation --> Active: Hợp lệ
    Validation --> Invalid: Validation thất bại
    Active --> Idle: close() và context còn khỏe
    Active --> Invalid: Lỗi giao tiếp được phân loại non-transient
    Idle --> Invalid: Eviction / validation khi idle
    Invalid --> Closed: Pool loại bỏ và đóng connection
    Closed --> New: Lần cần mượn tiếp, tạo mới
~~~

Trong pool, ứng dụng nhận một **wrapper** của `DirContext`. Khi `LdapTemplate` kết thúc thao tác và giải phóng context, wrapper sẽ **trả context về pool** nếu còn hợp lệ. Với context đã bị đánh dấu lỗi, pool sẽ **không đưa lại vào tập idle hợp lệ**.

Có hai điểm dễ nhầm:

1. `close()` trên **pooled wrapper** thường mang nghĩa **trả đối tượng về pool**, không phải luôn đóng socket vật lý.
2. `close()` sau một lỗi được pool nhận biết có thể dẫn tới **discard/physical close** thay vì reuse.

Không tự đóng connection vật lý nằm bên dưới wrapper bằng một API ngoài luồng mà không hiểu cơ chế pool, cũng không bỏ `close()` vì “đã có pool”: quên trả context gây **leak số active contexts**.

### 4.2. `nonTransientExceptions`: loại hỏng ngay, không cần chờ validation

Spring LDAP cung cấp `PoolingContextSource` (Commons Pool đời cũ) và `PooledContextSource` (Commons Pool 2). Các lớp này cho cấu hình tập **`nonTransientExceptions`**: nếu một thao tác trên pooled `DirContext` ném exception thuộc tập này, wrapper xem context không thể tái sử dụng.

Theo tài liệu Spring LDAP, mặc định có **`javax.naming.CommunicationException`**. Đây là cơ chế *eager invalidation*:

~~~text
context.search(...) -> javax.naming.CommunicationException
        |
        v
Pool wrapper đánh dấu context FAILED
        |
        v
LdapTemplate giải phóng context
        |
        v
Context hỏng bị loại, không trả về idle queue
~~~

Điều này có nghĩa **không cần viết thủ công `catch` ở từng repository method để “xóa socket hỏng”** khi pool và đường gọi được cấu hình đúng. Tuy nhiên:

- Cơ chế nhận biết chỉ áp dụng cho exception mà **pooled wrapper thực sự quan sát được**.
- Một connection có thể chết **khi đang idle** mà chưa phát sinh exception; phải kết hợp validation.
- Nếu ứng dụng giữ context ngoài `LdapTemplate`, phải thực hiện lifecycle/close đúng.
- Tùy phiên bản JDK/provider, một số lỗi có thể xuất hiện dưới lớp exception khác; chỉ mở rộng `nonTransientExceptions` sau khi có **bằng chứng và test**.
- Không cấu hình mọi `NamingException` là non-transient một cách mù quáng, vì lỗi schema/ACL không nói rằng connection không sử dụng được.

### 4.3. Vì sao không chỉ dựa vào một lần `isRunning()`/TCP probe?

Một cổng TCP đang mở không chứng minh rằng:

- Session LDAP đã bind đúng danh tính.
- Context trong pool còn đủ quyền.
- Server có thể thực hiện Search với timeout mong muốn.
- Dữ liệu/schema hoặc nhánh base đã có.
- TLS certificate được tin cậy và kết nối chưa hết hiệu lực.

Kiểm tra tính khả dụng của **một LDAP operation nhỏ** thường cho tín hiệu tốt hơn so với chỉ kiểm tra cổng mạng.

## 5. Chọn loại pool: JDK native hay Spring LDAP?

Java JNDI LDAP provider có pooling nội bộ, Spring LDAP có pooling ở tầng `ContextSource`.

| Tiêu chí | JNDI native pooling | Spring LDAP pooling |
| --- | --- | --- |
| Bật bằng | Thuộc tính JNDI và `AbstractContextSource.setPooled(true)` | Bọc một `ContextSource` bằng pool context source |
| Phạm vi cấu hình | Nhiều phần là system properties của JVM | Có thể cấu hình cho `ContextSource` riêng |
| Validation khi mượn | Khả năng tùy chỉnh hạn chế | `testOnBorrow` qua `DirContextValidator` |
| Kiểm tra idle | Khả năng kiểm soát hạn chế | `testWhileIdle`, eviction interval |
| Loại context khi lỗi | Phụ thuộc JNDI/provider | Có chính sách `nonTransientExceptions` |
| Quan sát pool | Hạn chế theo provider | Active/idle/waiters với Pool 2 |
| TLS/StartTLS | Có hạn chế tương thích đáng kể | Vẫn cần kiểm chứng cấu hình và lifecycle TLS |

Tài liệu Spring LDAP lưu ý `AbstractContextSource.setPooled(true)` bật **native Java LDAP pooling**, mặc định là `false`, và không phù hợp với các cấu hình TLS mà tài liệu nêu. Với nhu cầu validation/maintenance, thường ưu tiên **Spring LDAP `PooledContextSource`**, có kiểm thử với phiên bản thực tế.

**Không bật cả hai cơ chế pool một cách vô thức.** Một pool lồng trong pool khác làm khó dự đoán lifetime, kiểm tra context, credential rotation và số kết nối đang mở. Khi dùng Spring LDAP pool, hãy để `setPooled(false)` ở `LdapContextSource` bên dưới trừ khi đã có thiết kế được kiểm chứng riêng.

### 5.1. Commons Pool 1 và Commons Pool 2 có API khác nhau

Hai package có tên khá giống:

~~~java
// Spring LDAP pooling cũ, dựa trên Commons Pool 1:
org.springframework.ldap.pool.factory.PoolingContextSource

// Spring LDAP pooling dựa trên Commons Pool 2:
org.springframework.ldap.pool2.factory.PooledContextSource
org.springframework.ldap.pool2.factory.PoolConfig
~~~

Các setter cấu hình **không giống hệt nhau**. Ví dụ:

- `PoolingContextSource` cũ có các setter như `setMaxActive(...)` và `setTestOnBorrow(...)`.
- `PooledContextSource` dùng **`PoolConfig`** với `setMaxTotalPerKey(...)`, `setMaxWaitMillis(...)`, `setTestOnBorrow(...)`, v.v.

Không copy nguyên mã cấu hình của một package sang package kia. Bài này sử dụng **Commons Pool 2** ở phần cấu hình Java.

## 6. Cấu hình Spring Boot + `PooledContextSource` + validation

Giả sử LDAP test/production đã có naming context `dc=example,dc=org`, user ở `ou=people` và một bind identity được cấp quyền phù hợp.

### 6.1. Dependency và thuộc tính kết nối

Trong Gradle Kotlin DSL, với phiên bản Spring LDAP/Boot tương thích:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")

    // Spring LDAP pool2 dựa trên Apache Commons Pool 2.
    implementation("org.apache.commons:commons-pool2")
}
~~~

Hãy xác minh package `org.springframework.ldap.pool2` hiện diện trong phiên bản Spring LDAP đang dùng và phiên bản của Commons Pool 2 tương thích với dependency management. Không ghi cứng một version ngẫu nhiên khi dự án đã dùng Spring Boot BOM.

Ví dụ `application.yml`:

~~~yaml
spring:
  ldap:
    urls: "${LDAP_URL:ldaps://ldap.example.org:636}"
    base: "${LDAP_BASE_DN:dc=example,dc=org}"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Không để mật khẩu thật ở source code hoặc file commit. Kênh cung cấp credential phải phù hợp secret store của môi trường chạy.

### 6.2. Bean configuration minh họa bằng Java

Đây là cấu hình **chủ động tạo** raw `LdapContextSource`, pool và `LdapTemplate` để tránh nhầm về việc bean nào sử dụng pool:

~~~java
import java.util.HashMap;
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
public class LdapPoolingConfiguration {

    @Bean("rawLdapContextSource")
    LdapContextSource rawLdapContextSource(
            @Value("${spring.ldap.urls}") String ldapUrl,
            @Value("${spring.ldap.base}") String baseDn,
            @Value("${spring.ldap.username}") String bindDn,
            @Value("${spring.ldap.password}") String bindPassword) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(ldapUrl);
        source.setBase(baseDn);
        source.setUserDn(bindDn);
        source.setPassword(bindPassword);

        // Tránh vô tình dùng JNDI native pool bên trong Spring pool.
        source.setPooled(false);

        Map<String, Object> environment = new HashMap<>();
        environment.put(
            "com.sun.jndi.ldap.connect.timeout", "3000"
        );
        environment.put(
            "com.sun.jndi.ldap.read.timeout", "5000"
        );
        source.setBaseEnvironmentProperties(environment);

        return source;
    }

    @Bean("pooledContextSource")
    @Primary
    PooledContextSource pooledContextSource(
            @Qualifier("rawLdapContextSource")
            LdapContextSource rawContextSource) {

        PoolConfig config = new PoolConfig();

        // Thông số minh họa, phải đo tải thực tế trước khi chốt.
        config.setMaxTotal(16);
        config.setMaxTotalPerKey(8);
        config.setMaxIdlePerKey(4);
        config.setMinIdlePerKey(0);
        config.setMaxWaitMillis(2000);
        config.setBlockWhenExhausted(true);

        // Phát hiện connection chết trước khi trao cho ứng dụng.
        config.setTestOnBorrow(true);
        config.setTestWhileIdle(true);
        config.setTimeBetweenEvictionRunsMillis(30_000);
        config.setMinEvictableIdleTimeMillis(120_000);

        PooledContextSource pooled = new PooledContextSource(config);
        pooled.setContextSource(rawContextSource);
        pooled.setDirContextValidator(
            new DefaultDirContextValidator()
        );

        // Mặc định đã coi JNDI CommunicationException là non-transient.
        // Không cần tự ghi đè nonTransientExceptions khi chưa có lý do.
        return pooled;
    }

    @Bean("ldapTemplate")
    LdapTemplate ldapTemplate(
            @Qualifier("pooledContextSource")
            ContextSource contextSource) {

        return new LdapTemplate(contextSource);
    }
}
~~~

**Giải thích các quyết định cấu hình:**

1. `LdapContextSource` là nguồn kết nối **bên dưới** và không bật JNDI native pool.
2. `PooledContextSource` bọc nguồn này, quản lý borrowed/idle contexts bằng Commons Pool 2.
3. `@Primary` hỗ trợ injection theo type khi có nhiều `ContextSource`; `@Qualifier` giúp chọn rõ một bean.
4. Bean `ldapTemplate` được khởi tạo **trên pooled context source**, nên repository sử dụng cùng bean template (khi Spring Data LDAP được wiring tương ứng) cũng dùng pool.
5. `DefaultDirContextValidator` thực hiện kiểm tra LDAP nhỏ khi validation được bật.
6. `setMaxWaitMillis(2000)` giới hạn **thời gian đợi pool có context rảnh**, không phải thời gian LDAP Search.
7. `connect.timeout` và `read.timeout` là **môi trường của JNDI LDAP provider**, áp dụng cho tạo kết nối và chờ dữ liệu tương ứng; cần kiểm chứng theo JDK/provider thực tế.
8. Giá trị `maxTotal`, `maxTotalPerKey`, `maxIdlePerKey`, interval và timeout chỉ minh họa, không phải khuyến nghị chung cho mọi tải.

**Điểm cần kiểm tra khi dùng Spring Boot:** Việc tự khai báo `ContextSource`/`LdapTemplate` có thể khiến một phần auto-configuration **back off**. Nếu repository không dùng bean `"ldapTemplate"` này, kiểm tra lại tên bean, `@EnableLdapRepositories(ldapTemplateRef="ldapTemplate")` khi cần, package scan và các cấu hình custom khác. Không để hai `LdapTemplate` kết nối hai directory khác nhau mà thiếu `@Qualifier`.

Đoạn Java giả định dự án đã có Spring Data LDAP và các class pool2 đúng phiên bản; nếu không, điều chỉnh dependency/version theo BOM chứ không đổi import tùy ý để “biên dịch xanh”.

## 7. `testOnBorrow`, `testOnReturn` và `testWhileIdle`

Một pool có thể kiểm tra connection tại ba thời điểm:

| Cơ chế | Kiểm tra khi nào? | Lợi ích | Chi phí/giới hạn |
| --- | --- | --- | --- |
| `testOnBorrow` | Trước khi cấp context cho thao tác | Loại idle context đã chết trước Search | Tăng round-trip LDAP mỗi lần borrow được validate |
| `testOnReturn` | Khi context được trả về pool | Phát hiện lỗi trước khi lưu idle | Tăng chi phí hoàn trả; không thay eager invalidation |
| `testWhileIdle` | Trong đợt kiểm tra idle theo lịch | Dọn dần context chết do server/network timeout | Không bảo đảm phát hiện ngay trước lần borrow |
| `testOnCreate` (Pool 2) | Khi context vừa được tạo | Bảo đảm mới tạo xong có thể chạy validation | Tăng thời gian tạo context |

**Kết hợp thường có lý:** `testOnBorrow=true` để giảm stale connection phát sinh ở request đầu sau idle, và `testWhileIdle=true` để dọn bớt idle trước khi traffic quay lại. Có thể cân nhắc `testOnReturn` theo kết quả đo tải, nhưng không phải cứ bật mọi cờ là luôn tốt hơn.

### 7.1. `DefaultDirContextValidator` thực sự làm gì?

Theo tài liệu Spring LDAP, validator mặc định thực hiện một **LDAP Search nhỏ** với:

- Base rỗng tương đối với context.
- Filter gần dạng `(objectClass=*)`.
- Giới hạn trả về một entry, thuộc tính tối thiểu.
- Timeout ngắn theo `SearchControls` của validator.

Kết quả có entry hoặc một phản hồi phù hợp được validator coi là hợp lệ; exception hoặc không có kết quả có thể khiến validation thất bại.

**Một phép validation không phải thử quyền CRUD.** Nó chỉ kiểm tra context còn tương tác được với directory theo điều kiện validation. Cần đặc biệt chú ý:

- Base DN phải tồn tại và tài khoản dịch vụ **được phép search/read** tại nơi validator kiểm tra.
- Nếu ACL ngăn đọc entry base, validation có thể báo **false negative** dù query nghiệp vụ trên OU khác vẫn hoạt động.
- Một Search ngắn thành công **không bảo đảm** thao tác tiếp theo sẽ thành công; kết nối có thể chết ngay sau validation.
- Các server với referral hoặc schema đặc biệt có thể cần validator tùy chỉnh.

Không “sửa” false negative bằng cách cấp tài khoản ứng dụng quyền quản trị toàn directory. Thay vào đó, điều chỉnh validation base/filter để đọc **một entry sức khỏe cho phép**, hoặc cấu hình quyền đọc tối thiểu được duyệt.

### 7.2. Cấu hình eviction interval theo đặc điểm hạ tầng

Giả sử load balancer đóng idle connection sau 5 phút, còn pool giữ tối đa 30 phút. Nếu không có validation, một connection chết có thể nằm trong idle queue một thời gian dài.

Các lựa chọn:

- `testWhileIdle` kết hợp eviction interval nhỏ hơn idle timeout đã biết.
- `testOnBorrow` để kiểm tra ngay trước request.
- Giới hạn `minEvictableIdleTimeMillis` phù hợp để không giữ idle context quá lâu.
- Giảm số lượng idle contexts nếu traffic không ổn định.

Không tự đặt eviction chạy liên tục với khoảng rất nhỏ: sẽ tạo nhiều LDAP Search validation, tăng tải directory và có thể làm vấn đề nặng hơn. Các thông số cần được xác định từ **latency, số request đồng thời, idle timeout của mạng, giới hạn server và số pod**.

## 8. Ba loại timeout phải được phân biệt

Một request `LdapRepository.findById(Name)` có thể phải chờ ở nhiều tầng.

~~~mermaid
flowchart LR
    A["Gọi repository"] --> B["Đợi mượn context từ pool"]
    B --> C["Tạo TCP/TLS/bind nếu cần"]
    C --> D["LDAP Search/Lookup/Modify"]
    D --> E["Xử lý entry và trả context"]
~~~

| Timeout | Thường cấu hình ở đâu? | Ý nghĩa |
| --- | --- | --- |
| **Pool borrow wait** | `PoolConfig.setMaxWaitMillis(...)` | Đợi context rảnh trong pool khi đã đạt giới hạn |
| **Connect timeout** | `com.sun.jndi.ldap.connect.timeout` | Thời gian thiết lập kết nối JNDI LDAP; kiểm tra TLS/bind tổng thể theo môi trường |
| **Read timeout** | `com.sun.jndi.ldap.read.timeout` | Thời gian chờ phản hồi LDAP theo JNDI provider |
| **SearchControls time limit** | `SearchControls.setTimeLimit(...)` hoặc query builder | Hạn chế thời gian tìm kiếm ở tầng Search, không thay timeout mạng |
| **Deadline nghiệp vụ** | Controller/service/batch runner | Ngân sách thời gian tổng thể của một request/batch |

Ví dụ:

~~~text
Pool borrow wait:        2 s
Connect timeout:         3 s
LDAP read timeout:       5 s
Business deadline:       8 s
~~~

Các con số không được cộng máy móc thành SLA; một request có thể mượn context có sẵn hoặc phải tạo mới, có thể phát sinh validation và retry. Một chuỗi retry có thể vượt deadline nếu không có ngân sách **end-to-end**.

Nếu pool đã cạn, exception **không nhất thiết là `CommunicationException`**; có thể là lỗi acquire/`DataAccessResourceFailureException` hoặc exception của Commons Pool. Đừng xử lý “cạn pool” bằng cách tạo vòng retry vô hạn, vì sẽ tăng số request chờ và làm sập downstream.

### 8.1. Vì sao tăng pool size không chữa được network outage?

Khi LDAP server không truy cập được, tăng `maxTotal` từ 16 lên 160 chỉ khiến **nhiều kết nối mới cùng thất bại**, tăng timeout, FD, CPU và số thread chờ. Cần phân biệt:

- **Saturation do traffic hợp lệ:** active luôn cao, waiting tăng, LDAP latency ổn.
- **Leak context:** active tăng nhưng không giảm khi request hoàn tất.
- **Network/server outage:** communication error tăng, validator fail, tốc độ tạo connection thất bại cao.

Ba trường hợp có phương án xử lý khác nhau; không thể chữa hết bằng một nút tăng pool.

## 9. Retry đúng tầng: read có thể thử lại, write cần đối soát

### 9.1. Phân loại thao tác

| Thao tác | Được phép retry tự động? | Ghi chú |
| --- | --- | --- |
| `lookup`/`findById` | **Có điều kiện**, retry giới hạn | Là phép đọc; vẫn có thể đọc trạng thái mới trên replica khác |
| Search có filter an toàn | **Có điều kiện** | Giới hạn thời gian, kích thước và số lần; không coi lỗi thành kết quả rỗng |
| LDAP Compare | **Có điều kiện** | Không thay đổi state, nhưng phụ thuộc trạng thái và ACL |
| `Add` | **Không retry mù** | Server có thể đã tạo entry; lần hai trả `entryAlreadyExists` |
| `Modify` | **Không retry mù** | Server có thể đã áp dụng; `ADD_ATTRIBUTE` có thể bị lỗi khi lặp |
| `Delete` | **Không retry mù** | Server có thể đã xóa; lần hai trả `noSuchObject` |
| `ModifyDN`/rename | **Không retry mù** | DN cũ/mới có thể đã thay đổi, tham chiếu cần đối soát |
| Nhiều entry hoặc group update | **Cần workflow idempotent/compensation** | Không có transaction nhiều entry mặc định |
| Paged Results với cookie | **Không tự nối tiếp bằng connection mới** | Cookie có thể không hợp lệ nếu connection/server thay đổi |

**Một retry của phép đọc** không phải “lấy lại dữ liệu đang bị mất”. Nó là một lần Search mới qua một context mới hoặc vừa được xác minh. Kết quả có thể khác nếu directory thay đổi hoặc replication trễ.

### 9.2. Ví dụ read retry giới hạn theo exception

Đây là một ví dụ Java cố tình chỉ retry **lookup read-only** tối đa hai lần, khi nhận **Spring LDAP `CommunicationException`**:

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.LdapTemplate;

public final class RetryingDirectoryLookup {

    private final LdapTemplate ldapTemplate;

    public RetryingDirectoryLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readCn(String uid) throws Exception {
        Name dn = org.springframework.ldap.support.LdapNameBuilder
            .newInstance("ou=people")
            .add("uid", uid)
            .build();

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                return ldapTemplate.lookup(
                    dn,
                    new String[] {"cn"},
                    attrs -> {
                        var cn = attrs.get("cn");
                        return cn == null ? null : (String) cn.get();
                    }
                );
            } catch (CommunicationException ex) {
                if (attempt == 2) {
                    throw ex;
                }

                // Backoff rất nhỏ để minh họa; trong hệ thống thật nên
                // dùng Retry/Circuit Breaker với jitter + deadline.
                try {
                    Thread.sleep(150L);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Lookup bị hủy khi chờ retry", interrupted
                    );
                }
            }
        }

        throw new AssertionError("Vòng retry bất khả đạt");
    }
}
~~~

**Phạm vi ví dụ:**

- Code thực hiện **đọc** từ `LdapTemplate`, không retry Add/Modify/Delete.
- `LdapNameBuilder` dựng DN an toàn; `uid` là dữ liệu DN, không phải raw LDAP filter.
- Một `CommunicationException` từ lần đọc đầu được phép **truyền qua đường giải phóng context của `LdapTemplate`**; pool sẽ loại connection lỗi theo chính sách.
- Lần đọc kế tiếp **mượn context mới/khỏe** từ pool, nhưng vẫn có thể thất bại nếu LDAP server đang outage.
- `Thread.sleep` chỉ để minh họa backoff; tránh chặn quá nhiều request thread trong ứng dụng chịu tải lớn.
- Hệ thống thực cần giới hạn số retry theo **deadline**, thêm jitter, circuit breaker, rate limiting và xử lý gián đoạn (`InterruptedException`).

**Không bắt `Exception` chung rồi retry mọi lỗi.** Lỗi schema, ACL, credential hoặc parse dữ liệu không tự hết nếu thử lại cùng request.

### 9.3. Write timeout: phân biệt trạng thái “không xác định”

Giả sử thực hiện:

~~~java
ldapTemplate.modifyAttributes(
    "uid=alice,ou=people",
    new ModificationItem[] {
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "new@example.org")
        )
    }
);
~~~

Nếu nhận `CommunicationException`, client không biết server đã apply Modify hay chưa. Cách xử lý an toàn hơn:

1. **Đánh dấu kết quả là chưa xác định**, không khẳng định thành công/thất bại.
2. Để pool loại context lỗi và lấy context khỏe ở lần truy cập tiếp theo.
3. **Đọc lại đúng entry** bằng bind identity được phép; chú ý read-after-write có thể bị trễ trên replica.
4. So sánh trạng thái quan sát được với **trạng thái đích** và chính sách đồng bộ.
5. Nếu đã đạt trạng thái đích, có thể xem yêu cầu nghiệp vụ hoàn tất mà không gửi lặp.
6. Nếu chưa đạt hoặc không đọc được chắc chắn, áp dụng retry có kiểm soát, cơ chế assertion/conditional update hoặc chuyển sang hàng đợi đối soát.
7. Ghi audit/trace theo request ID, **không log mật khẩu hoặc dữ liệu nhạy cảm**.

Một `REPLACE_ATTRIBUTE` với cùng giá trị có thể tạo trạng thái cuối tương tự khi chạy hai lần; nhưng không được suy rộng rằng mọi **side effect** và mọi lệnh LDAP đều idempotent. `ADD_ATTRIBUTE`, thay đổi nhóm, rename, quy trình nhiều entry và event downstream có rủi ro khác.

**Pool recovery** và **business reconciliation** là hai bước riêng, kể cả khi cùng xảy ra trong một request.

## 10. Repository CRUD, lỗi và tính nhất quán

Trong Spring Data LDAP, một entity ODM có thể khai báo:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name value) { dn = value; }

    public String getUid() { return uid; }
    public void setUid(String value) { uid = value; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String value) { commonName = value; }

    public String getSurname() { return surname; }
    public void setSurname(String value) { surname = value; }
}
~~~

Repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
}
~~~

Khi gọi:

~~~java
var person = repository.findById(
    new javax.naming.ldap.LdapName("uid=alice,ou=people")
);
~~~

repository sử dụng hạ tầng Spring LDAP, vì vậy **nguyên tắc kiểm soát context lỗi và retry read** ở bài vẫn áp dụng.

Tuy nhiên, cần phân biệt:

- `findById` là lookup **theo DN**, không phải search theo `uid` trên toàn directory.
- `save(entity)` có thể tạo/sửa entry theo trạng thái DN và mapping; không phải SQL upsert tổng quát.
- `deleteById` không tự làm sạch tham chiếu nhóm (`member`, `uniqueMember`).
- `saveAll` không tự có transaction nhiều entry.
- Nếu một lần `save` thất bại vì communication, không biết chắc entry đã được thêm/sửa hay chưa.
- Khi Directory có replica, Search ở node khác sau thao tác ghi có thể thấy dữ liệu cũ do replication.

**Không biến một lỗi giao tiếp thành `Optional.empty()` hoặc `false` cho `existsById`**. Trong hệ thống kiểm tra quyền LDAP group, lỗi mạng không được coi là “người dùng hợp lệ, cứ cho phép”, và một lỗi kiểm tra quyền phải được xử lý theo chính sách fail-safe.

## 11. Một số trường hợp pooling đặc biệt cần chú ý

### 11.1. Pool của service account khác xác thực từng người dùng

`PooledContextSource` giả định các read-only contexts được mượn từ cùng kiểu môi trường/bind identity, và tương tự với read-write contexts. Nếu dùng `AuthenticationSource` thay đổi DN/password theo từng request người dùng, một pool dùng chung có thể **vô tình tái sử dụng context của người đầu tiên cho người khác**.

Ví dụ không an toàn về thiết kế:

~~~text
HTTP request của Alice -> bind credentials Alice -> mượn context
HTTP request của Bob   -> bind credentials Bob   -> mượn lại context Alice?
~~~

Đừng bọc một `LdapContextSource` dùng **per-user dynamic AuthenticationSource** trong shared pool nếu chưa có cơ chế phân tách credential đúng và được thư viện hỗ trợ. Spring LDAP cũng ghi rõ hạn chế này trong tài liệu pooling.

Với service account cố định chỉ search/read danh bạ, pooling có thể phù hợp. Với **end-user authentication**, dùng cơ chế LDAP authentication/Spring Security phù hợp và bảo đảm mỗi credential được xác minh đúng cách, không được tái sử dụng phiên của người khác.

### 11.2. Read-only và read-write contexts

`ContextSource` có:

~~~java
getReadOnlyContext()
getReadWriteContext()
getContext(principal, credentials)
~~~

Pool có thể duy trì số lượng context theo **loại read-only/read-write**, nhưng cần nhớ:

- `getReadOnlyContext()` không tạo ACL mới trên server; quyền thực tế phụ thuộc **bind account**.
- Nếu cùng một service account có quyền ghi, một read-only context API không tự chứng minh mọi operation ghi bị từ chối.
- Việc pool phân tách read/write **không tự tách credential** khi cả hai cùng dựa vào cùng cấu hình.
- Các phép thử validation phải phù hợp với loại context và chính sách ACL.

Spring LDAP `ContextSource.getContext(principal, credentials)` phục vụ các tình huống xác thực bằng danh tính tường minh và không dùng native JNDI pooling theo mô tả API. Không lấy kết quả của service bind để kết luận credential của người dùng cuối đúng.

### 11.3. LDAP controls và Paged Results cookie

Khi đọc nhiều trang bằng **Simple Paged Results Control** (RFC 2696), cookie do server phát hành có thể cần **cùng underlying LDAP connection** trong chuỗi trang.

Ví dụ sai về tư duy:

~~~text
Search page 1 qua connection A -> cookie X
Connection A lỗi, pool loại A
Search page 2 qua connection B -> gửi cookie X
=> Không được giả định cookie X còn hợp lệ
~~~

Nếu đường kết nối bị hỏng ở giữa, cách an toàn hơn là **hủy chuỗi paging hiện tại** và khởi động lại từ đầu, có idempotency/đối soát khi xử lý batch.

Spring LDAP có `SingleContextSource.doWithSingleContext(...)` để giữ cùng một connection cho chuỗi paging trong callback. Nếu dùng pool cùng LDAP controls, cần kiểm tra API/implementation của từng phiên bản. Spring LDAP cung cấp **`MutablePooledContextSource`** (Commons Pool 2) cho tình huống cần thay đổi request controls như paging; không tự cho rằng mọi `PooledContextSource` wrapper đều hỗ trợ việc thiết lập control giống `LdapContext` thông thường.

**Lưu ý:** Giữ cùng connection không biến paging thành một snapshot transaction. Khi directory thay đổi giữa các trang, kết quả vẫn có thể trùng hoặc thiếu entry tùy server.

### 11.4. LDAPS và StartTLS

- **LDAPS** thường dùng `ldaps://host:636`, thiết lập TLS ngay khi mở socket.
- **StartTLS** nâng cấp một LDAP connection trước khi bind; một URL `ldap://` **không tự bật** StartTLS.
- JNDI native pooling có những hạn chế về TLS; không dùng `setPooled(true)` như cách “tối ưu” chung cho các kết nối TLS.
- Với Spring LDAP pooling, vẫn phải bảo đảm certificate, truststore, hostname, cipher/policy và vòng đời TLS hoạt động đúng.
- Nếu một request thay đổi trạng thái TLS/bind hoặc request controls trên context, phải kiểm tra rằng state đó được **reset phù hợp** trước khi trả context vào pool, hoặc dùng connection không pool cho tình huống này.

**Không tắt xác thực chứng chỉ** hoặc dùng `TrustManager` tin tất cả để giảm lỗi connection. `CommunicationException` phát sinh do lỗi trust/handshake cần được giải quyết bằng cấu hình TLS, không phải bằng retry liên tục.

### 11.5. Đổi mật khẩu service account

Một pool đã thiết lập LDAP bind với credential cũ có thể giữ connection hoạt động trong khi secret đã luân chuyển. Việc thay environment variable hoặc giá trị cấu hình không nhất thiết làm các context đã tồn tại **được bind lại**.

Khi rotate credential:

1. Chuẩn bị thay đổi/secret mới và cửa sổ chuyển đổi được phê duyệt.
2. Bảo đảm `LdapContextSource` nhận cấu hình mới qua **recreate bean/rollout** hoặc cơ chế rotation được thiết kế.
3. Loại hoặc drain các context cũ theo vòng đời quản lý pool.
4. Xác minh bind/search với credential mới trước khi đưa request production.
5. Thu hồi credential cũ theo chính sách, kiểm tra metric lỗi xác thực.

Đừng cố biến `invalidCredentials` thành `CommunicationException` hoặc giữ session với credential cũ mãi mãi để bỏ qua rotation.

## 12. Quan sát pool: không chỉ đo số lần Search thành công

Với `PooledContextSource` của Commons Pool 2, có thể thu thập:

~~~java
int active = pooledContextSource.getNumActive();
int idle = pooledContextSource.getNumIdle();
int waiters = pooledContextSource.getNumWaiters();

int activeRead = pooledContextSource.getNumActiveRead();
int activeWrite = pooledContextSource.getNumActiveWrite();
~~~

Đây là ví dụ **đặt trong bean/monitor có tham chiếu tới `PooledContextSource` được inject**; không phải một API controller cần công khai số kết nối cho mọi người dùng.

Những số liệu hữu ích:

| Metric | Đọc thế nào? | Cảnh báo khi |
| --- | --- | --- |
| `active` | Context đang được mượn | Tăng sát giới hạn và giữ cao bất thường |
| `idle` | Context sẵn sàng trong pool | Cao lâu dù ít traffic hoặc giảm liên tục bất thường |
| `waiters` | Luồng chờ mượn context | Tăng cùng độ trễ API |
| `activeRead` / `activeWrite` | Phân bố loại context | Một loại cạn nhưng loại kia còn rảnh |
| Số lần validation fail | Kết nối idle/borrow không hợp lệ | Đột biến sau network change hoặc restart |
| `CommunicationException` rate | Giao tiếp LDAP thất bại | Tăng trên nhiều pod/server |
| Connect/read timeout rate | Không tạo/đọc connection trong hạn | Spike theo endpoint, AZ hoặc hạ tầng mạng |
| Pool borrow latency | Mất bao lâu để lấy context | Tăng khi saturation hoặc validator chậm |
| LDAP operation latency | Thời gian Search/Modify thực | Tăng do server/load/query |
| JVM threads/FDs | Tài nguyên tiến trình | Tăng không giảm, nghi context leak |

**Chú ý:** Spring LDAP pool cung cấp một số phương thức đếm active/idle/waiters, nhưng metric validation failures, latency và per-exception rate có thể cần thêm instrumentation qua Micrometer/JMX/log. Đừng tuyên bố mặc định mọi metric đã được xuất ra actuator.

### 12.1. Phân biệt ba dạng sự cố khi đọc dashboard

**Pool cạn do tải:**

~~~text
active = maxTotal
idle   = 0
waiters tăng
communication error thấp
LDAP latency tăng hoặc ổn định ở mức cao
~~~

**Stale connections sau idle:**

~~~text
idle nhiều trước giờ cao điểm
request đầu tiên sau idle gặp CommunicationException
invalidated contexts tăng
request kế tiếp qua context mới có thể thành công
~~~

**Directory outage thực sự:**

~~~text
communication/timeout tăng đồng loạt
new connection fail
validation fail
retry cũng thất bại
circuit breaker cần bảo vệ server và request threads
~~~

Những mẫu này chỉ là **dấu hiệu chẩn đoán**, không phải thuật toán phát hiện lỗi tự động. Cần kết hợp log server, network telemetry, trạng thái DNS/LB và chính sách retry.

## 13. Kiểm thử khôi phục sau kết nối hỏng

Unit test một repository được mock **không thể chứng minh** pool thực sự loại socket chết. Muốn kiểm tra, cần LDAP server thật trong môi trường test: embedded LDAP hoặc container với mạng có thể gây lỗi.

### 13.1. Một integration test cơ bản với pool đã cấu hình

Giả sử directory test có `dc=example,dc=org` và `ou=people`. Có thể kiểm tra:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.pool2.factory.PooledContextSource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class LdapPoolSmokeIT {

    @Autowired
    LdapTemplate ldapTemplate;

    @Autowired
    PooledContextSource pool;

    @Test
    void readWorksAndContextReturnsToPool() {
        String dc = ldapTemplate.lookup(
            "",
            new String[] {"dc"},
            attrs -> String.valueOf(attrs.get("dc").get())
        );

        assertThat(dc).isEqualTo("example");

        // Với test chạy đơn luồng và không có request LDAP khác:
        assertThat(pool.getNumActive()).isZero();
        assertThat(pool.getNumIdle()).isGreaterThanOrEqualTo(0);
    }
}
~~~

Test này chỉ chứng minh **đường Spring LDAP dùng pooled context source và giải phóng context sau lookup**, không chứng minh thu hồi context hỏng. Môi trường test cần cấu hình `LdapPoolingConfiguration` và có entry root; nếu embedded server tự tạo root, không nạp trùng trong LDIF fixture.

### 13.2. Fault injection: ngắt kết nối khi có idle context

Kịch bản test nên triển khai với **LDAP container + network fault proxy** (ví dụ Testcontainers/Toxiproxy hoặc công cụ kiểm soát TCP test được phê duyệt):

1. Khởi động LDAP container cùng schema và fixture test.
2. Khởi động ứng dụng với `PooledContextSource`, `testOnBorrow=true`.
3. Thực hiện một Lookup thành công rồi trả context về pool, kiểm tra `idle > 0`.
4. Làm cho connection cũ không còn dùng được: restart container hoặc cắt TCP qua proxy.
5. Khôi phục endpoint và mạng, tránh thay đổi hostname/port mà `ContextSource` dùng.
6. Thực hiện Lookup mới; validation có thể **phát hiện và loại stale connection**, rồi pool tạo/mượn context khỏe.
7. Kiểm tra kết quả cuối cùng, exception rate, `active/idle`, và việc không giữ vô hạn context chết.
8. Đảm bảo test chạy trong **môi trường LDAP dành riêng**, không thao tác ngắt kết nối directory dùng chung.

Trong thực tế, một số lỗi chỉ được nhận biết **khi operation bắt đầu**, nên có thể có **một lần thất bại** dù đã bật validation. Không viết assert “không bao giờ có CommunicationException” vì validator không thể ngăn mọi race giữa kiểm tra và thao tác.

### 13.3. Fault injection: cắt kết nối giữa một thao tác ghi

Bài test khó hơn và quan trọng hơn:

~~~text
Thời điểm A: Client gửi Modify mail=updated@example.org
Thời điểm B: Network proxy làm mất response
Thời điểm C: Client nhận CommunicationException
Thời điểm D: Client nhận kết nối mới và đọc lại entry
~~~

Kỳ vọng:

- Context đã lỗi bị **đánh dấu/loại** khỏi pool.
- Service nhận một kết quả **không xác định** nếu không biết thao tác đã được server xử lý.
- Luồng nghiệp vụ đọc lại trạng thái hoặc đưa vào đối soát.
- **Không** tự động gửi lại tất cả `ADD_ATTRIBUTE`, `DELETE`, `ModifyDN` mà không kiểm tra state.
- Khi test kết thúc, các entry test được cleanup đúng và pool không còn active context bị leak.

Có thể mô phỏng lỗi trước/sau server xử lý và chứng minh ứng dụng đưa ra quyết định khác nhau dựa trên **trạng thái quan sát được**. Nếu không kiểm soát được chính xác vị trí mất packet, cần kết hợp test integration với **unit test state machine** cho nhánh “không biết server đã commit”.

### 13.4. Kiểm thử failover, replica và TLS

| Tình huống | Điều cần xác minh |
| --- | --- |
| Server restart trong thời gian idle | Connection cũ bị loại khi borrow/operation, không tái dùng vô hạn |
| Network outage kéo dài | Retry giới hạn, không bão hòa pool và thread |
| Pool maxTotal bị chiếm hết | Borrow timeout và lỗi rõ ràng, không treo vô hạn |
| Lookup trong lúc lỗi mạng | Không bị chuyển thành “không tìm thấy” |
| Modify nhận mất response | Đối soát trạng thái đích trước retry |
| Replica trả dữ liệu cũ | Không kết luận Modify thất bại chỉ từ một lần đọc replica trễ |
| Group membership update | Không tự retry thêm thành viên khi kết quả không xác định |
| Rotation service password | Context cũ được drain/recreate, credential mới được xác minh |
| TLS truststore sai | Thao tác bị từ chối; không cấu hình trust-all |
| Paged Search mất connection | Hủy cookie/page chain và bắt đầu lại có kiểm soát |
| Context leak trong custom JNDI code | `active` được trả về bình thường sau `close()` |
| Validator base không có quyền đọc | Phát hiện false negative, không cấp admin permission để chữa |

## 14. Runbook chẩn đoán `CommunicationException` trong production

Khi rate lỗi tăng, ưu tiên **khoanh vùng theo tầng** trước khi thay cấu hình.

### Bước 1 — Ghi lại mẫu lỗi

Thu thập:

- Thời điểm, endpoint LDAP, pod/instance và loại request.
- Outer Spring exception, **root cause** và thông điệp lỗi đã làm sạch.
- Các thao tác bị ảnh hưởng: chỉ Search hay cả Modify/Bind?
- Latency, timeout, pool active/idle/waiters.
- Có restart LDAP, failover, thay firewall/CA, rotation credential hay deploy gần đây không?

Không log bind password, raw control/cookie, full DN nhạy cảm hoặc toàn bộ entry.

### Bước 2 — Xác minh endpoint và TLS

Kiểm tra DNS, host, port và certificate bằng công cụ vận hành phù hợp. Một lệnh ví dụ cho LDAPS:

~~~bash
openssl s_client \
  -connect ldap.example.org:636 \
  -servername ldap.example.org \
  -CAfile approved-ca.pem \
  -verify_hostname ldap.example.org \
  -verify_return_error
~~~

Lệnh yêu cầu file CA đã được xác minh. TLS handshake thành công **chưa** chứng minh bind/ACL và Search thành công.

### Bước 3 — Kiểm tra bind và LDAP Search thật

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=app-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s base \
  "(objectClass=*)" dn dc objectClass
~~~

Dùng cùng loại danh tính và endpoint mà ứng dụng thực sự sử dụng. Nếu tìm kiếm thành công từ host quản trị nhưng thất bại từ pod, kiểm tra network path, proxy/load balancer, DNS, truststore của JVM và credential được cấp cho pod.

### Bước 4 — Phân loại pool hay server

- **Chỉ hỏng sau idle:** nghi stale connections và validation.
- **Mọi connection mới đều hỏng:** nghi server/network/TLS/credential; tăng pool size không giúp.
- **Active cao, waiters tăng:** nghi pool saturation hoặc context leak.
- **Chỉ lỗi trong một code path:** kiểm tra cách mượn/đóng context, controls và transaction handling.
- **Chỉ lỗi sau failover:** kiểm tra DNS/LB, cổng, cookie paging và consistency giữa replica.

### Bước 5 — Thực hiện biện pháp khắc phục đúng tầng

- Điều chỉnh `testOnBorrow`, idle eviction và timeouts **sau khi** xác định stale connection là nguyên nhân.
- Áp dụng retry có giới hạn cho read, không retry write mù quáng.
- Khởi tạo lại pool/pod nếu credential/truststore hoặc endpoint thay đổi mà các context cũ không thể cập nhật.
- Sửa ACL/schema riêng biệt nếu LDAP server trả lỗi logic; không xóa toàn bộ pool mỗi khi gặp `noSuchObject`.
- Khi outage kéo dài, dùng circuit breaker/giảm tải và cảnh báo; không tạo bão kết nối.
- Sau khi phục hồi, kiểm tra dữ liệu downstream đã ghi dở và reconciliation.

## 15. Những sai lầm dễ mắc

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ bật pool và tin connection luôn khỏe | Idle context chết được mượn lại | Dùng validation và eager invalidation |
| Bắt Spring exception rồi tự `close()` mọi raw context khác | Lifecycle bị rối hoặc đóng nhầm context | Để `LdapTemplate`/pool quản lý wrapper đúng |
| Coi lỗi LDAP 49/50 là communication | Retry vô ích, che vấn đề credential/ACL | Phân loại theo error type/result code |
| Retry mọi `save()`/`delete()` ngay sau timeout | Trùng thao tác, xóa sai hoặc state không xác định | Đối soát trạng thái đích và idempotency |
| `catch(Exception)` trả list rỗng | Che outage thành không có dữ liệu | Chuyển lỗi đến policy nghiệp vụ |
| `setPooled(true)` cùng Spring pool không kiểm chứng | Hai lớp pooling, khó kiểm soát TLS và lifecycle | Chọn chiến lược pooling rõ ràng |
| Dùng `PoolingContextSource` Pool 1 setter cho Pool 2 | Lỗi API/config | Dùng `PooledContextSource` + `PoolConfig` |
| Bật validation nhưng không cấu hình validator | Validation không hoạt động hoặc setup sai | `setDirContextValidator(...)` |
| Validation Search vào DN bị ACL chặn | False negative, loại context khỏe | Điều chỉnh validation base/quyền tối thiểu |
| Tăng `maxTotal` khi server outage | Tăng request đang treo và tài nguyên | Timeout, backoff, circuit breaker |
| Dùng shared pool cho per-user credentials | Rủi ro tái sử dụng danh tính không đúng | Tách luồng xác thực người dùng |
| Dùng cookie paging sau connection đổi | Dữ liệu thiếu hoặc Search lỗi | Restart paging có kiểm soát |
| Đổi secret nhưng giữ pool cũ vô hạn | Session bind không đồng bộ credential | Drain/recreate pool theo quy trình rotation |
| Bỏ qua metrics active/idle/waiters | Không phát hiện leak hoặc saturation | Giám sát pool và request latency |

## 16. Bài tập thực hành và câu hỏi tự kiểm tra

1. Tại sao một `DirContext` đang idle có thể hỏng dù `PooledContextSource` vẫn báo `idle > 0`?
2. `javax.naming.CommunicationException` khác `org.springframework.ldap.CommunicationException` ở tầng nào?
3. Trong Spring LDAP pooling, vì sao `CommunicationException` nằm trong `nonTransientExceptions` mặc định?
4. Khi wrapper nhận lỗi được phân loại non-transient, context hỏng có được trả về idle queue không?
5. Vì sao `close()` trên pooled wrapper không nhất thiết đóng TCP socket?
6. Khi nào dùng `testOnBorrow` và `testWhileIdle`? Những chi phí bổ sung là gì?
7. Một validator báo lỗi do ACL chặn entry base: vì sao tăng số retry không giải quyết được?
8. `setMaxWaitMillis(2000)` là read timeout, connect timeout hay thời gian đợi mượn context?
9. Vì sao tăng `maxTotal` có thể làm sự cố LDAP outage tệ hơn?
10. Sự khác biệt giữa JNDI native pooling và Spring LDAP Pool 2 là gì?
11. Vì sao không nên bật native `setPooled(true)` trong một cấu hình Spring LDAP pool mà chưa kiểm tra tác động?
12. Một Search gặp `CommunicationException`: những điều kiện nào cho phép thử lại, và khi nào phải dừng?
13. Một `Modify` mất response: ứng dụng đã biết entry được cập nhật hay chưa?
14. Vì sao retry lệnh `ADD_ATTRIBUTE` vào `uniqueMember` có thể tạo lỗi dù lần đầu đã thành công?
15. Tại sao token Simple Paged Results không được tự động dùng với connection khác sau failover?
16. Vì sao `PooledContextSource` dùng cho một `AuthenticationSource` thay đổi theo từng người có thể không an toàn?
17. Hãy đề xuất cách đo pool saturation khác với stale connection.
18. Test nào có thể chứng minh một connection hỏng bị loại mà không gây gián đoạn LDAP production?
19. Trong quy trình đổi mật khẩu service account, vì sao cần drain/recreate pooled contexts?
20. Vì sao một kết quả `findById()` không tìm thấy không được dùng thay cho lỗi `CommunicationException`?
21. Nếu `testOnBorrow` thành công nhưng Search ngay sau đó vẫn lỗi, lý do hợp lệ nào có thể xảy ra?
22. Hãy đề xuất policy retry/backoff cho directory read-only API với giới hạn latency 1 giây.
23. Khi một request Update user và Update group thất bại giữa chừng, tại sao cần bù trừ và đối soát?
24. Một LDAP server hỗ trợ LDAPS nhưng Java nhận PKIX error: thay đổi gì là đúng, thay đổi gì làm mất bảo mật?

## 17. Tổng kết

**Thu hồi kết nối hỏng** trong Spring Data LDAP không thực hiện tại `LdapRepository` mà ở **hạ tầng Spring LDAP/JNDI pooling**. Khi pooled `DirContext` gặp `javax.naming.CommunicationException`, Spring LDAP có thể đánh dấu context không thể tái sử dụng và loại nó khỏi pool. Các cơ chế `testOnBorrow` và `testWhileIdle` giúp phát hiện kết nối hỏng trong thời gian idle; `DefaultDirContextValidator` cung cấp một phép LDAP Search nhỏ để xác minh context.

Tuy nhiên, loại socket hỏng **không giải quyết tính đúng đắn của thao tác vừa lỗi**. Search/Lookup có thể retry giới hạn trên connection mới, còn Add/Modify/Delete/rename cần xem kết quả **không xác định**, đối soát trạng thái và chỉ retry theo hợp đồng idempotency. Khi dùng LDAP controls, StartTLS, nhiều bind identities hoặc đọc dữ liệu qua replica, phải xác minh vòng đời context, cookie và tính nhất quán riêng.

Một cấu hình đáng tin cậy cần có: **timeout phân tầng, pool size có giới hạn, connection validation, eager invalidation, retry có kiểm soát, bảo mật TLS/credential và đo active/idle/waiters**. Các yếu tố này giúp repository và `LdapTemplate` truy cập directory ổn định mà không che giấu lỗi schema, ACL hoặc nghiệp vụ.

### Tài liệu tham khảo

- [Spring LDAP Reference — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html).
- [Spring LDAP Reference — Connection Configuration và JNDI Native Pooling](https://docs.spring.io/spring-ldap/reference/configuration.html).
- [Spring LDAP API — `PooledContextSource` (Commons Pool 2)](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html).
- [Spring LDAP API — `PoolConfig`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PoolConfig.html).
- [Spring LDAP API — `DefaultDirContextValidator`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/validation/DefaultDirContextValidator.html).
- [Spring LDAP API — `MutablePooledContextSource` (request controls)](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/MutablePooledContextSource.html).
- [Spring LDAP API — `CommunicationException` hierarchy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/CommunicationException.html).
- [Spring LDAP API — `ContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextSource.html).
- [RFC 4511 — LDAPv3 Protocol, operations và result codes](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 2696 — Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696).
