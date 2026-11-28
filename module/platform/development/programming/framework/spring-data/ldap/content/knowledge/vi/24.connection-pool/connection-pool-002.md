# Phân biệt native JNDI pooling với pooling của Spring LDAP

Trong **Spring Data LDAP**, ứng dụng Java dùng repository hoặc `LdapTemplate` để truy cập entry trong cây thư mục LDAP. Mỗi thao tác cần một ngữ cảnh kết nối thích hợp để gửi yêu cầu như tìm người dùng theo `uid`, đọc nhóm hoặc sửa thuộc tính. Với tải truy cập liên tục, thiết lập TCP, TLS và LDAP bind lặp đi lặp lại có thể tăng độ trễ. **Connection pooling** giúp tái sử dụng tài nguyên đã khởi tạo, nhưng có **hai cơ chế dễ bị nhầm**:

1. **Native JNDI pooling** do LDAP provider của Java/JNDI quản lý.
2. **Spring LDAP pooling** do một `ContextSource` bọc ngoài quản lý, thường dùng Apache Commons Pool 2.

Hai cơ chế khác nhau ở **đối tượng được pool**, **phạm vi cấu hình**, **kiểm tra kết nối**, **quan sát vận hành** và **xử lý danh tính xác thực**. Bài này giải thích sự khác biệt, cách cấu hình, tình huống lựa chọn và cách kiểm chứng trên directory test.

Sau khi học, bạn có thể:

- Mô tả đúng vai trò của `DirContext`, `LdapContextSource`, `PooledContextSource` và socket LDAP.
- Bật native JNDI pooling bằng `setPooled(true)` và phân biệt cấu hình mức JVM với cấu hình bean Spring.
- Tạo pool của Spring LDAP bằng `PoolConfig`, `DefaultDirContextValidator` và `PooledContextSource`.
- Hiểu giới hạn per-identity của native JNDI, per-key/per-pool của Spring và các lựa chọn timeout/validation.
- Tránh các lỗi liên quan đến LDAPS/StartTLS, credentials thay đổi, xác thực từng người dùng và bật chồng hai pool.

## 1. Tầng kết nối trong ứng dụng Spring Data LDAP

Giả sử ứng dụng tra cứu entry:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
```

Một repository có thể cung cấp phương thức `findByUid("lan")`; `LdapTemplate` có thể tìm với filter `(&(objectClass=inetOrgPerson)(uid=lan))`. Cả hai đều cần hạ tầng truy cập directory:

```text
Ứng dụng Java
   ├── Spring Data LDAP: PersonRepository
   └── Spring LDAP: LdapTemplate
                  │
                  ▼
              ContextSource
                  │ cấp phát
                  ▼
          javax.naming.directory.DirContext
                  │ gửi LDAP operation
                  ▼
        JNDI LDAP provider / kết nối mạng
                  │ TCP + LDAPS / StartTLS
                  ▼
              LDAP server
         DN, objectClass, schema, ACL
```

**`DirContext` là đối tượng JNDI dùng để thực hiện thao tác thư mục; kết nối TCP là tài nguyên truyền thông bên dưới.** Tùy provider và cấu hình, việc khởi tạo một context không nhất thiết tương đương mở đúng một socket mới. Pooling của JNDI và Spring can thiệp vào **những tầng khác nhau** trong sơ đồ này.

Một lần tìm kiếm thường cần các yếu tố sau:

| Yếu tố | Ví dụ | Pool có thay đổi không? |
| --- | --- | --- |
| Search base | `ou=people,dc=example,dc=org` | Không |
| Search scope | `ONELEVEL` hoặc `SUBTREE` | Không |
| Search filter | `(uid=lan)` | Không |
| Principal/bind DN | `uid=ldap-reader,ou=services,...` | Phải được giữ đúng ngữ cảnh xác thực |
| `DirContext` và kết nối | Context để gửi search | Có thể được tái sử dụng |

Pool **không cache kết quả tìm kiếm** và không thay thế việc tối ưu filter, index, schema hoặc quyền đọc/ghi. Nó chủ yếu giảm chi phí thiết lập kết nối/bind và quản lý số tài nguyên đồng thời.

## 2. Hai cơ chế pooling nằm ở đâu?

### 2.1. Native JNDI pooling

```text
Repository / LdapTemplate
            │
       LdapContextSource
       setPooled(true)
            │ getReadOnlyContext() / getReadWriteContext()
            ▼
          DirContext
            │
     Java LDAP provider
     ┌──────────────────────────┐
     │ Pool kết nối theo        │
     │ connection identity      │
     │ (trong cùng JVM)         │
     └──────────────────────────┘
            │
         LDAP server
```

Ở cơ chế này, **JNDI LDAP provider** giữ lại những kết nối vật lý đủ điều kiện và cho context mới tái sử dụng kết nối. Các pool do provider quản lý thuộc **phạm vi JVM**, được chia theo *connection identity* (địa chỉ server, cách kết nối, cơ chế xác thực và thông tin đăng nhập có liên quan). Chúng **không dùng chung giữa các tiến trình/JVM khác nhau**.

Spring LDAP cung cấp cờ `LdapContextSource#setPooled(true)` để yêu cầu cơ chế này khi tạo các context thông thường; mặc định là `false`. Việc bật cờ **không bảo đảm mọi kết nối đều được pool**: LDAP provider còn xét loại kết nối, cơ chế xác thực và những thuộc tính môi trường khiến một kết nối không đủ điều kiện.

### 2.2. Pooling của Spring LDAP

```text
Repository / LdapTemplate
            │
            ▼
    PooledContextSource
    ┌─────────────────────────────┐
    │ Pool DirContext             │
    │  READ:  [ctx-A] [ctx-B]     │
    │  WRITE: [ctx-C]             │
    │  borrow / validate / return │
    └──────────────┬──────────────┘
                   │ context mới khi cần
                   ▼
           LdapContextSource
           setPooled(false)
                   │
           JNDI LDAP provider
                   │
               LDAP server
```

Spring LDAP tạo một **wrapper `ContextSource`** để pool các đối tượng `DirContext`; mỗi wrapper có cấu hình và số liệu riêng. Khi ứng dụng mượn context, dùng xong và gọi `close()` trên wrapper, context hợp lệ được **trả về pool** thay vì luôn đóng ngay kết nối bên dưới.

Triển khai hiện đại dùng `org.springframework.ldap.pool2.factory.PooledContextSource` dựa trên **Apache Commons Pool 2**. Spring LDAP cũng có API `org.springframework.ldap.pool.factory.PoolingContextSource` dựa trên Commons Pool đời cũ; không trộn API/cấu hình của hai loại. Tài liệu này ưu tiên ví dụ **Pool2**.

## 3. Bảng phân biệt nhanh

| Tiêu chí | Native JNDI pooling | Spring LDAP pooling (Pool2) |
| --- | --- | --- |
| Ai quản lý? | JNDI LDAP provider của Java | `PooledContextSource` của Spring LDAP + Commons Pool 2 |
| Đối tượng quản lý | Kết nối LDAP bên dưới các `DirContext` | Các `DirContext` mượn từ `ContextSource` |
| Cách bật | `LdapContextSource#setPooled(true)` hoặc môi trường JNDI phù hợp | Bọc `LdapContextSource` bằng `PooledContextSource` |
| Phạm vi | Pool của provider trong **một JVM**, phân theo connection identity | **Từng bean** `PooledContextSource`, có khóa phân loại read/write |
| Cách cấu hình | JVM system properties `com.sun.jndi.ldap.connect.pool.*` | `PoolConfig`, validator, thuộc tính của bean Spring |
| Giới hạn chính | `maxsize` **cho từng connection identity** | `maxTotal` toàn pool và `maxTotalPerKey` theo loại |
| Kiểm tra context khi mượn | Không có cơ chế validation tương đương để cấu hình từ Spring | Có `testOnBorrow`, `testOnReturn`, `testWhileIdle` |
| Xử lý context hỏng | Provider quản lý kết nối hỏng, có giới hạn quan sát/chủ động kiểm tra | Có validation, loại context lỗi và các ngoại lệ gây invalidation |
| Quan sát hoạt động | Debug provider và quan sát mạng/server, ít số liệu mức bean | `getNumActive()`, `getNumIdle()`, `getNumWaiters()` ... |
| TLS/StartTLS | Cần đặc biệt thận trọng với trạng thái TLS; không dùng native pool cho StartTLS | Hỗ trợ quản lý context linh hoạt hơn; vẫn phải cấu hình TLS và validator đúng |
| Danh tính người dùng | Provider chia theo connection identity, nhưng không thay thế kiểm tra mật khẩu mới | Pool read/write mặc định **giả định cùng môi trường xác thực** trong mỗi loại |
| Mức kiểm soát | Đơn giản, ít nút điều chỉnh | Nhiều lựa chọn về giới hạn, timeout, eviction, validation |

**Quy tắc chọn lựa phổ biến:** nếu cần pooling cho Spring LDAP và muốn kiểm tra context lỗi, khống chế tài nguyên theo ứng dụng hoặc dùng TLS, **ưu tiên Spring LDAP pooling**. Native JNDI pooling vẫn có thể hữu ích trong tình huống đơn giản, nhưng cần hiểu hạn chế và kiểm chứng tại môi trường chạy thật.

## 4. Cấu hình native JNDI pooling

### 4.1. Bật trong `LdapContextSource`

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class NativeJndiPoolConfig {

    @Bean
    public LdapContextSource contextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.service-dn}") String bindDn,
            @Value("${app.ldap.service-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase("dc=example,dc=org");
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setPooled(true); // Yêu cầu provider JNDI dùng native pooling
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Các thuộc tính `app.ldap.*` là **ví dụ do ứng dụng tự định nghĩa**, không phải tên property mặc định của Spring Boot. Mật khẩu bind nên lấy từ nơi quản lý secret hoặc môi trường được bảo vệ. Với cấu hình này, repository Spring Data LDAP nào dùng cùng `LdapTemplate`/`ContextSource` cũng sử dụng hạ tầng truy cập đó.

Để thử riêng **native pooling** trong directory phát triển, có thể dùng một server `ldap://localhost:1389` được cô lập. **Không dùng simple bind qua LDAP không mã hóa trong môi trường thực tế**; với kết nối TLS, hãy xem lưu ý ở mục 7.

### 4.2. System properties của JVM khác với environment properties của JNDI

Native JNDI pooling có hai lớp cấu hình:

- **Cờ yêu cầu cho context:** thuộc tính môi trường JNDI `com.sun.jndi.ldap.connect.pool=true`, được `setPooled(true)` đặt vào môi trường khởi tạo context.
- **Chính sách chung trong JVM:** các **system properties** `com.sun.jndi.ldap.connect.pool.*`, thiết lập lúc khởi động tiến trình Java.

Ví dụ tham số JVM cho môi trường thử nghiệm:

```shell
java \
  -Dcom.sun.jndi.ldap.connect.pool.maxsize=12 \
  -Dcom.sun.jndi.ldap.connect.pool.prefsize=4 \
  -Dcom.sun.jndi.ldap.connect.pool.timeout=300000 \
  -jar ldap-learning-app.jar
```

*Lưu ý:* ví dụ trên biểu diễn dòng lệnh kiểu Unix. Trong PowerShell hoặc công cụ chạy khác, cần viết đúng cú pháp truyền JVM options tương ứng. Những option này được thêm **trước** `-jar`, không phải đặt vào file YAML ứng dụng rồi kỳ vọng provider tự đọc.

| System property | Ý nghĩa | Giá trị mặc định theo tài liệu JNDI của Oracle |
| --- | --- | --- |
| `...pool.initsize` | Số connection ban đầu cho **mỗi identity** | `1` |
| `...pool.maxsize` | Số connection tối đa **mỗi identity** | Không có giới hạn tối đa |
| `...pool.prefsize` | Số connection ưu tiên giữ cho **mỗi identity** | Không có mức ưu tiên |
| `...pool.timeout` | Thời gian connection được phép nhàn rỗi (mili giây) | Không có timeout |
| `...pool.authentication` | Các kiểu authentication được phép pool | `none simple` |
| `...pool.protocol` | Các kiểu kết nối được phép pool | `plain` |
| `...pool.debug` | Ghi thông tin tạo/hủy kết nối để chẩn đoán | Tắt |

Tên đầy đủ của thuộc tính ở bảng đều bắt đầu bằng `com.sun.jndi.ldap.connect.pool.`. Chẳng hạn `...pool.maxsize` là `com.sun.jndi.ldap.connect.pool.maxsize`.

**Điểm dễ nhầm:** `maxsize=12` **không** đồng nghĩa cả JVM chỉ có tối đa 12 LDAP connections. JNDI duy trì nhiều nhóm theo identity; mỗi nhóm có thể đạt 12. Nếu ứng dụng truy cập nhiều server hoặc nhiều principal, tổng số kết nối có thể lớn hơn đáng kể.

### 4.3. Provider quyết định kết nối nào đủ điều kiện pool

JNDI provider nhận diện kết nối qua host/port, thông tin bảo mật, principal, credentials và những tùy chọn giao tiếp liên quan. Vì vậy, hai request bind bằng danh tính khác nhau **không mặc định dùng chung** một connection trong native pool.

Theo tài liệu Oracle, native pool mặc định áp dụng cho kết nối **plain** với xác thực `none` hoặc `simple`. Có thể điều chỉnh loại kết nối đủ điều kiện qua `...pool.protocol` (ví dụ cho phép `ssl`) và `...pool.authentication`, nhưng không vì vậy mà StartTLS hay việc thay đổi trạng thái bảo mật sau khi tạo context trở nên an toàn. Một số tùy chọn như custom socket factory hoặc protocol tracing cũng có thể khiến JNDI không pool một kết nối.

Đặc biệt, Spring LDAP cố ý **không dùng native JNDI pooling** cho lời gọi `ContextSource#getContext(String principal, String credentials)` để thay đổi/reset mật khẩu có hiệu lực kịp thời. Không suy luận rằng bật `setPooled(true)` sẽ tăng tốc mọi thao tác xác thực từng người dùng.

## 5. Cấu hình Spring LDAP pooling bằng Pool2

### 5.1. Mô hình bean

Ta tạo một `LdapContextSource` **gốc** dùng thông tin service account cố định, tắt native pooling, sau đó bọc nó trong `PooledContextSource`:

```text
rawLdapContextSource
   - LDAP URL, base DN, service bind DN
   - native pooling = false
          │
          ▼
contextSource = PooledContextSource
   - maxTotal, maxTotalPerKey, maxWaitMillis
   - testOnBorrow, validator
          │
          ▼
LdapTemplate / Spring Data LDAP repository
```

Ví dụ Java Config (theo API Spring LDAP hỗ trợ Commons Pool 2):

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.pool2.factory.PoolConfig;
import org.springframework.ldap.pool2.factory.PooledContextSource;
import org.springframework.ldap.pool2.validation.DefaultDirContextValidator;

@Configuration
public class SpringLdapPoolConfig {

    @Bean("rawLdapContextSource")
    public LdapContextSource rawLdapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.service-dn}") String bindDn,
            @Value("${app.ldap.service-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);   // Ví dụ: ldaps://directory.example.org:636
        source.setBase("dc=example,dc=org");
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setPooled(false); // Tắt JNDI native pooling
        return source;
    }

    @Bean("contextSource")
    @Primary
    public PooledContextSource contextSource(
            @Qualifier("rawLdapContextSource") LdapContextSource raw) {

        PoolConfig config = new PoolConfig();
        config.setMaxTotal(12);          // Tối đa toàn pool
        config.setMaxTotalPerKey(8);    // Tối đa mỗi loại context
        config.setMaxIdlePerKey(4);     // Tối đa context idle mỗi loại
        config.setMinIdlePerKey(0);
        config.setBlockWhenExhausted(true);
        config.setMaxWaitMillis(1500);  // Chờ lấy context tối đa 1,5 giây
        config.setTestOnBorrow(true);

        PooledContextSource pool = new PooledContextSource(config);
        pool.setContextSource(raw);
        pool.setDirContextValidator(new DefaultDirContextValidator());
        return pool;
    }

    @Bean
    public LdapTemplate ldapTemplate(
            @Qualifier("contextSource") PooledContextSource pooled) {
        return new LdapTemplate(pooled);
    }
}
```

Ví dụ giả định project đã khai báo **các module Spring LDAP có lớp Pool2** và dependency Apache Commons Pool 2 tương thích; tên artifact và version cần đối chiếu với dependency management của project. Đây là cấu hình Java tường minh để minh họa; trong Spring Boot, nếu đã có auto-configuration cho `LdapTemplate` hoặc `ContextSource`, phải kiểm tra tên bean, `@Primary`, qualifier và lựa chọn thực tế của repository để tránh tạo hai đường kết nối khác nhau.

**Các số 12, 8, 4 và 1500 ms chỉ là giá trị thử nghiệm.** Chúng không được coi là cấu hình sản xuất mặc định. Khi tạo nhiều `PooledContextSource` độc lập, giới hạn trên từng bean **không tự áp dụng** cho tổng các bean hoặc tổng số pod.

### 5.2. Sử dụng từ `LdapTemplate`

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> namesByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());
    }
}
```

Giả sử `ContextSource` có base `dc=example,dc=org`, truy vấn trên tìm trong `ou=people` tương đối với base. `LdapTemplate` phụ trách lấy và đóng context quanh mỗi lần thao tác; với context đến từ Spring pool, thao tác đóng trên wrapper thường **trả context về pool**. Dùng builder cho filter thay vì nối `uid` từ input giúp tránh LDAP filter injection.

Các repository Spring Data LDAP dùng cùng `LdapTemplate`/`ContextSource` đã cấu hình sẽ nhận lợi ích của pool mà không phải sửa annotation `@Entry`, `@Id` hoặc `@Attribute` của entity.

### 5.3. Khi tự mượn `DirContext`, luôn trả lại

```java
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.ContextSource;

public void inspect(ContextSource source) throws NamingException {
    DirContext context = source.getReadOnlyContext();
    try {
        // Đọc entry hoặc thực hiện search.
    } finally {
        context.close();
    }
}
```

Nếu quên `close()`, pool coi context vẫn đang được mượn. Khi tất cả context đã hết, request sau có thể phải chờ tới `maxWaitMillis` và cuối cùng thất bại. Không chia sẻ một context đang được mượn cho nhiều request/thread độc lập.

## 6. Các giới hạn và cách kiểm tra kết nối của Spring pool

### 6.1. Pool read-only và read-write

`PooledContextSource` quản lý các nhóm `DirContext` theo **loại đọc** và **loại đọc/ghi**, thay vì tự động tạo một nhóm cho từng người đăng nhập. Vì vậy có hai lớp giới hạn:

- `maxTotal`: giới hạn số context đang được quản lý bởi **toàn bộ pool**.
- `maxTotalPerKey`: giới hạn cho **mỗi loại** context.

Giả sử `maxTotal=12`, `maxTotalPerKey=8`, tại cùng thời điểm đã có 8 context đọc đang được mượn thì nhóm đọc đã đạt giới hạn theo loại, dù tổng pool còn chỗ cho nhóm ghi. Request đọc tiếp có thể phải đợi hoặc thất bại theo cấu hình, chứ không tự lấy phần còn trống của nhóm ghi.

Tình huống này khác native JNDI với `maxsize=12`: native giới hạn **theo connection identity**, không phải theo loại read/write hay một bean.

### 6.2. Các lựa chọn timeout

Đừng gộp các loại timeout thành một:

| Timeout | Chi phối điều gì? | Ví dụ |
| --- | --- | --- |
| **Pool wait timeout** | Chờ mượn context khi pool cạn | `PoolConfig#setMaxWaitMillis(1500)` |
| **Connect timeout** | Thời gian thiết lập kết nối TCP LDAP | `com.sun.jndi.ldap.connect.timeout` |
| **Read timeout** | Thời gian chờ phản hồi LDAP trên socket | `com.sun.jndi.ldap.read.timeout` |
| **Search time limit** | Giới hạn thời gian tìm kiếm phía operation/server | `SearchControls#setTimeLimit(...)` |
| **Idle eviction** | Khi nào kiểm tra/loại context nằm trong pool quá lâu | Cấu hình evictor của `PoolConfig` |

Pool wait timeout **không** xử lý được tất cả tình huống socket treo hoặc server phản hồi chậm. Cần cấu hình timeout mạng và retry có kiểm soát riêng cho LDAP client.

### 6.3. Validation và context hỏng

Một kết nối nằm idle có thể bị firewall, load balancer hoặc server đóng. Spring pool có các chế độ:

| Tùy chọn | Khi nào kiểm tra? | Đổi lại |
| --- | --- | --- |
| `testOnBorrow` | Trước khi giao context cho ứng dụng | Giảm dùng context hỏng, nhưng tăng chi phí mỗi lần mượn |
| `testOnReturn` | Khi context được trả về | Tăng thời gian trả/kiểm tra |
| `testWhileIdle` | Theo chu kỳ evictor khi idle | Phát hiện kết nối chết sớm; cần bật chu kỳ kiểm tra |
| `testOnCreate` | Sau khi tạo context mới | Kiểm chứng context trước khi nhập pool |

`DefaultDirContextValidator` mặc định thực hiện một truy vấn LDAP rất nhỏ, với filter kiểu `(objectClass=*)`, giới hạn một kết quả và timeout ngắn. **Validator chỉ hiệu quả nếu tài khoản bind được phép thực hiện truy vấn kiểm tra** trong directory tương ứng. Nếu search base kiểm tra không phù hợp ACL hoặc directory, context khỏe mạnh vẫn có thể bị đánh giá lỗi; khi đó cần điều chỉnh cấu hình validator.

Spring pool còn có thể **vô hiệu context sớm** khi gặp các ngoại lệ không tạm thời, chẳng hạn `javax.naming.CommunicationException`, để tránh trả lại context đã hỏng. Tuy nhiên validation không thể bảo đảm mạng sẽ không ngắt **sau** lúc context được kiểm tra.

### 6.4. Theo dõi pool

Với Pool2, `PooledContextSource` có API quan sát:

```java
int active  = pooledContextSource.getNumActive();
int idle    = pooledContextSource.getNumIdle();
int waiters = pooledContextSource.getNumWaiters();

int activeRead  = pooledContextSource.getNumActiveRead();
int activeWrite = pooledContextSource.getNumActiveWrite();
```

Theo dõi thêm **thời gian chờ pool**, tỷ lệ timeout, lỗi bind, timeout mạng, số kết nối đang mở trên LDAP server và phân vị latency của ứng dụng. Số context đang active tăng không nhất thiết là lỗi; nhưng **active luôn chạm trần, idle bằng 0 và waiters tăng liên tục** thường báo hiệu thiếu dung lượng pool, thao tác LDAP chậm hoặc context không được trả đúng cách.

## 7. Bảo mật và những tình huống không nên pooling tùy tiện

### 7.1. LDAPS và StartTLS

**LDAPS** tạo kết nối LDAP có TLS ngay từ đầu (thường dùng `ldaps://...:636`). **StartTLS** bắt đầu từ LDAP rồi nâng cấp kết nối sang TLS bằng thao tác mở rộng. Hai đường đi có hành vi quản lý trạng thái khác nhau.

Oracle cho phép JNDI native pool được cấu hình để xét cả kết nối kiểu `ssl` thay vì chỉ `plain`, nhưng **StartTLS thay đổi trạng thái kết nối sau khi đã tạo context**. Tài liệu JNDI khuyến cáo không pooling context có StartTLS hoặc thay đổi các thuộc tính bảo mật khi đang dùng; Spring LDAP cũng cảnh báo cần tắt native pooling khi làm việc với TLS. Do đó:

- Với ứng dụng có TLS, **tắt `setPooled(true)`** và ưu tiên cơ chế pooling được Spring LDAP hỗ trợ, sau khi kiểm tra chiến lược TLS thực tế.
- Không dùng native pool để chia sẻ kết nối StartTLS đã thay đổi trạng thái.
- Không bỏ qua kiểm tra chứng chỉ, hostname hoặc truststore để làm pooling hoạt động.
- Việc bật SSL trong `com.sun.jndi.ldap.connect.pool.protocol` **không** khắc phục nguy cơ stateful StartTLS.

### 7.2. Service account cố định khác với danh tính từng người dùng

Ví dụ API chỉ đọc dữ liệu hồ sơ thường có một tài khoản dịch vụ `uid=ldap-reader,...` với quyền tối thiểu. Pool của Spring LDAP phù hợp hơn trong trường hợp mỗi nhóm context được tạo với **một môi trường xác thực ổn định**.

Ngược lại, nếu ứng dụng lấy principal/password từ người dùng đang đăng nhập qua một `AuthenticationSource`, **không** đặt `PooledContextSource` thông thường lên trên `LdapContextSource` đó. Spring LDAP chỉ phân loại các context read-only/read-write, **không** tự tách từng principal do `AuthenticationSource` cung cấp; request mới có thể mượn context đã xác thực bằng quyền của người trước.

Các thao tác kiểm tra mật khẩu riêng nên đi theo luồng xác thực phù hợp của Spring LDAP/Spring Security. `getContext(principal, credentials)` được thiết kế để không dùng native pooling, nhằm tránh mật khẩu cũ vẫn có hiệu lực ngoài ý muốn trên connection đã xác thực trước đó. Đừng giả định rằng một `PooledContextSource` sẽ pool an toàn mọi lời gọi xác thực động.

Khi service account đổi/thu hồi credential, context đã bind và đang nằm trong pool có thể cần được tái tạo theo chính sách vận hành. Việc mật khẩu bị đổi ở server **không tự bảo đảm** mọi kết nối đã xác thực cũ bị vô hiệu ngay theo cách bạn mong muốn.

### 7.3. Không bật hai tầng pooling theo phản xạ

Nếu vừa cấu hình `rawLdapContextSource.setPooled(true)` vừa bọc nó bằng `PooledContextSource`, ứng dụng có thể có **hai tầng tái sử dụng độc lập**. Điều này làm khó việc xác định kết nối thực tế, tác dụng của giới hạn, timeout và validation. Khi chọn Spring pool, cấu hình `setPooled(false)` cho `ContextSource` bên trong để mỗi tầng có trách nhiệm rõ ràng.

## 8. Chọn cơ chế nào theo tình huống?

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| Ứng dụng Spring Data LDAP có lưu lượng đọc thường xuyên bằng service account | **Spring LDAP Pool2** | Giới hạn theo bean, validation và số liệu dễ quan sát |
| LDAP server/firewall thường đóng kết nối idle | **Spring LDAP Pool2** | Có `testOnBorrow` và `testWhileIdle` để giảm lỗi tái sử dụng |
| Muốn giới hạn số context mỗi instance ứng dụng | **Spring LDAP Pool2** | `maxTotal` và `maxTotalPerKey` của từng bean |
| Ứng dụng Java JNDI rất đơn giản, không dùng Spring | Có thể xem xét **native JNDI** | Ít thành phần bổ sung, nhưng cấu hình toàn JVM và kiểm soát hạn chế |
| Môi trường cần LDAPS/StartTLS, chứng chỉ kiểm tra đầy đủ | **Spring LDAP Pool2**, xác minh TLS strategy | Tránh những ràng buộc nguy hiểm khi thay đổi trạng thái kết nối trong native pool |
| Bind từng người dùng để xác thực mật khẩu | **Luồng xác thực riêng** | Không reuse context của người này cho người khác |
| Truy cập LDAP rất hiếm hoặc chỉ chạy batch ngắn | Đo trước khi bật pool | Chi phí giữ idle connections có thể vượt lợi ích |
| Search chậm do filter rộng, thiếu index, ACL | Tối ưu truy vấn/server trước | Pool không tăng tốc xử lý filter hay thay schema |

Đây là tiêu chí lựa chọn kiến trúc, không phải quy tắc tuyệt đối. Quyết định cuối cùng phải căn cứ vào JDK/JNDI provider, phiên bản Spring LDAP, directory server, đặc điểm TLS và số liệu tải thật.

## 9. Ví dụ phân tích khi pool chạm giới hạn

Giả sử một REST API có hai luồng chính: **đọc** `inetOrgPerson` theo `uid` và **ghi** thuộc tính `mail` cho người dùng đã được phân quyền. Ứng dụng dùng Spring pool:

```text
maxTotal = 10
maxTotalPerKey = 6
maxWaitMillis = 1500

Thời điểm T:
  6 context READ đang được mượn
  2 context WRITE đang được mượn
  Tổng active = 8
```

Khi thêm một request READ:

- Nhóm READ đã ở mức `6` nên không được tạo thêm context READ theo giới hạn per-key, dù tổng active chưa đạt 10.
- Nếu chưa có context READ idle phù hợp, request phải chờ một context READ trả về (với `blockWhenExhausted=true`); chờ quá 1500 ms sẽ dẫn tới lỗi mượn pool.
- Một request WRITE vẫn có thể được cấp context WRITE khác nếu còn quota chung và quota của loại WRITE.

Nếu thay bằng native JNDI và `maxsize=6`, kết luận sẽ khác: giới hạn `6` nằm ở **mỗi connection identity** mà provider tạo ra, **không phải** read/write key của Spring. Hai nhóm cấu hình không thể so sánh bằng cách chỉ nhìn vào con số `6`.

## 10. Kiểm thử, đo lường và xác minh cấu hình

Hãy thực hiện trên **directory test** hoặc staging có dữ liệu giả, cùng mạng và schema gần với production:

1. **Đường cơ sở:** đo cùng một tập truy vấn bằng `LdapTemplate`/repository khi không bật pooling. Ghi p50, p95, p99, thông lượng và số kết nối server.
2. **Native JNDI:** bật `setPooled(true)` trong điều kiện đủ điều kiện pool; đặt JVM properties trước khi khởi động. So sánh số kết nối sau nhiều lần lấy/đóng context, không suy từ số request.
3. **Spring pool:** tắt native, bọc bằng `PooledContextSource`, bật giới hạn và validator; theo dõi `getNumActive()`, `getNumIdle()`, `getNumWaiters()`.
4. **Tải đồng thời:** tạo nhiều request hơn `maxTotalPerKey`. Xác minh thời gian chờ, exception và HTTP response phù hợp khi pool cạn.
5. **Kết nối chết khi idle:** trong môi trường kiểm thử, ngắt kết nối từ directory hoặc mô phỏng firewall idle timeout; xác minh context lỗi được loại và request tiếp theo có thể khôi phục theo chính sách.
6. **TLS:** dùng chứng chỉ test hợp lệ, truststore đúng; không kiểm thử thành công bằng cách tắt kiểm tra chứng chỉ.
7. **Thay đổi mật khẩu:** thay/thu hồi credential của service account và kiểm tra quy trình refresh pool. Với xác thực người dùng, bảo đảm mật khẩu cũ không được chấp nhận qua kết nối đã bind cũ.
8. **Kết quả nghiệp vụ:** so sánh DN, `objectClass`, thuộc tính và nội dung entry được trả về ở hai chế độ. Pool không được làm thay đổi kết quả filter hoặc quyền truy cập.

**Đo đúng chi phí:** pooling có thể giảm TCP/TLS/bind, nhưng validator trên mỗi lần mượn cũng tạo thêm LDAP request. Nếu directory search vốn chậm nhiều giây, tối ưu pool có thể chỉ cải thiện nhỏ. Ngược lại, nếu server ngắt idle connection thường xuyên, validation có thể giảm lỗi nhưng cần được đo với tải thật.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `setPooled(true)` nhưng số socket không giảm | Kết nối không đủ điều kiện JNDI pool; mỗi request có identity khác | Kiểm tra `protocol`/`authentication`, principal, TLS, cấu hình provider |
| Đặt `maxsize=10` mà toàn JVM có nhiều hơn 10 socket | Native JNDI giới hạn **theo identity**, không phải cả JVM | Phân tích identity và quan sát server; dùng pool Spring nếu cần giới hạn theo bean |
| Spring pool vẫn mở nhiều kết nối | Vô tình tạo nhiều pool hoặc để native pooling bật trong raw source | Xác minh bean đang được repository dùng, tắt native trên raw source |
| Request treo khi tải cao | Pool đã cạn và timeout mượn quá lớn/không giới hạn | Đặt `maxWaitMillis` phù hợp, đo latency và active/waiters |
| Mượn context thì validator báo lỗi | Base/filter của validator không phù hợp ACL hoặc context đã hỏng | Kiểm tra quyền tìm kiếm và cấu hình validator |
| Đọc LDAP lỗi sau thời gian idle | Socket bị server/network đóng | Bật validation/eviction, kiểm tra timeout phía server |
| Quyền truy cập bị nhầm giữa người dùng | Pool Spring bọc `AuthenticationSource` động | Tách luồng xác thực người dùng; dùng pool chỉ với identity ổn định |
| Thay mật khẩu nhưng thao tác vẫn dùng phiên cũ | Context đang giữ trạng thái xác thực trước đó | Làm mới hoặc hủy pool/kết nối theo quy trình đổi credential |
| Cấu hình timeout nhưng request vẫn chờ lâu | Nhầm pool wait với connect/read/search timeout | Cấu hình từng lớp timeout riêng biệt |
| Test localhost nhanh, production vẫn chậm | Khác độ trễ mạng, TLS, tải LDAP server hoặc schema/index | Đo trên hạ tầng đại diện và tối ưu truy vấn |

## 12. Tự luyện tập

**Bài 1.** Một dịch vụ đã gọi `source.setPooled(true)`, đồng thời khởi động JVM với `-Dcom.sun.jndi.ldap.connect.pool.maxsize=8`. Có thể khẳng định tổng số LDAP socket của ứng dụng không quá 8 không?

*Gợi ý:* Không. `maxsize` giới hạn mỗi connection identity trong native JNDI; có thể có nhiều identity, và còn các kết nối không đủ điều kiện pool.

**Bài 2.** Khi `PooledContextSource` có `maxTotal=10` và `maxTotalPerKey=6`, 6 context READ đang active, 2 context WRITE đang active. Tại sao request READ thứ bảy có thể chờ dù tổng mới là 8?

*Gợi ý:* Giới hạn nhóm READ đã chạm `maxTotalPerKey`. Context WRITE không thay thế READ.

**Bài 3.** Một `AuthenticationSource` trả credential theo từng người dùng đăng nhập. Có nên dùng chung một `PooledContextSource` mặc định cho tất cả người dùng?

*Gợi ý:* Không. Pool read/write không được thiết kế để tự phân tách credential theo người dùng; có nguy cơ tái sử dụng context với quyền sai.

**Bài 4.** Tại sao đặt `testOnBorrow=true` có thể tăng một chút latency nhưng vẫn giảm lỗi từ các connection bị firewall ngắt khi idle?

*Gợi ý:* Validation phát sinh kiểm tra trước thao tác, đổi lại có thể phát hiện và loại context lỗi.

**Bài 5.** Ứng dụng dùng LDAPS và `LdapTemplate`, cần theo dõi số request chờ pool và phân biệt READ/WRITE. Chọn cơ chế nào?

*Gợi ý:* Spring LDAP Pool2 cung cấp `getNumWaiters()`, `getNumActiveRead()` và `getNumActiveWrite()`, đồng thời có cơ chế validation theo `ContextSource`.

## 13. Ghi nhớ

- **Native JNDI pooling** quản lý kết nối trong JVM theo **connection identity**, bật bằng `setPooled(true)` và cấu hình chính bằng **JVM system properties**.
- **Spring LDAP pooling** quản lý `DirContext` qua `PooledContextSource`, giới hạn theo **pool và loại READ/WRITE**, hỗ trợ **validation, eviction và số liệu quan sát**.
- Native JNDI không có validation chủ động linh hoạt như Spring pool; Spring LDAP khuyến nghị cơ chế pool riêng khi cần pooling trong ứng dụng Spring.
- **TLS/StartTLS, credential và danh tính người dùng** là ràng buộc bảo mật thiết yếu; không dùng chung pool mặc định cho context có principal thay đổi theo request.
- Nếu chọn Spring pooling, **tắt native pooling ở `ContextSource` bên trong**, cấu hình đủ timeout, luôn trả context và kiểm chứng với directory test.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): validation, per-context-source configuration, Pool2 và các vấn đề xác thực.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `native-pooling`, `ContextSource`, TLS và xác thực.
- [Spring LDAP API — PooledContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html): các phương thức Pool2 và lifecycle.
- [Spring LDAP API — PoolConfig](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PoolConfig.html): giới hạn, wait, validation, eviction.
- [Oracle JNDI — Connection Pooling](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/pool.html): phạm vi pooling và những trường hợp không nên dùng.
- [Oracle JNDI — Connection Pooling Configuration](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/config.html): system properties, identity và giới hạn theo connection.
