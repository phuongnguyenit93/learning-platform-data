# Thiết lập thời gian chờ kết nối và thời gian chờ đọc

Trong ứng dụng **Spring Data LDAP**, một truy vấn repository như `findByUid("linh")` có thể phải mở kết nối tới LDAP server, xác thực tài khoản dịch vụ, gửi yêu cầu tìm kiếm rồi chờ entry được trả về. Nếu server không thể kết nối hoặc không phản hồi, request của ứng dụng có nguy cơ bị giữ lâu, chiếm thread và làm chậm những request khác. **Connect timeout** và **read timeout** giúp giới hạn hai giai đoạn chờ khác nhau.

Bài học thuộc chương **Kết nối**, hướng dẫn cấu hình thời gian chờ đúng nơi trong **Spring Boot/Spring LDAP/JNDI**, hiểu giới hạn của mỗi loại timeout, phân biệt với thời gian giới hạn tìm kiếm, xử lý lỗi an toàn và kiểm thử với directory. Kiến thức này áp dụng cả khi truy cập LDAP bằng **LdapRepository**, **LdapTemplate** hay JNDI trực tiếp; dữ liệu LDAP vẫn được tổ chức theo **DN, objectClass và schema**, và quyền truy cập vẫn được máy chủ kiểm soát qua ACL.

## 1. Timeout nằm ở đâu trong kiến trúc Spring Data LDAP?

~~~mermaid
flowchart TD
    A["HTTP request / tác vụ nền"] --> B["Service: chính sách deadline, retry"]
    B --> C["Spring Data LDAP: LdapRepository"]
    B --> D["Spring LDAP: LdapTemplate"]
    C --> D
    D --> E["ContextSource: tạo, mượn và trả context"]
    E --> F["JNDI LDAP provider của JDK"]
    F --> G[("LDAP server")]
    H["connect.timeout"] -. "Mở TCP / chờ kết nối từ JNDI pool" .-> F
    I["read.timeout"] -. "Chờ phản hồi LDAP" .-> F
    J["SearchControls / query.timeLimit"] -. "Giới hạn thao tác Search" .-> D
~~~

Các lớp có trách nhiệm khác nhau:

| Tầng | API/cấu hình tiêu biểu | Trách nhiệm |
| --- | --- | --- |
| Ứng dụng | Service, HTTP server, job worker | Chọn **deadline tổng thể**, quy tắc retry, thông báo lỗi và quan sát thời gian thực tế |
| Spring Data LDAP | `LdapRepository`, `@Entry`, `@Attribute` | Chuyển lời gọi repository thành thao tác LDAP và ánh xạ entry sang Java |
| Spring LDAP | `LdapTemplate`, `LdapContextSource` | Lấy context và thực thi tìm kiếm, tạo, sửa, xóa entry |
| JNDI LDAP provider | `com.sun.jndi.ldap.connect.timeout`, `com.sun.jndi.ldap.read.timeout` | Giới hạn một số giai đoạn chờ ở tầng kết nối/đọc phản hồi |
| LDAP server | Chính sách thời gian, ACL, chỉ mục và schema | Thực hiện tìm kiếm trên cây thư mục, có thể áp đặt giới hạn riêng |

**Spring Data LDAP không tạo ra giao thức mạng riêng.** Repository và `LdapTemplate` thông thường đều dùng cấu hình `ContextSource` để truy cập cùng JNDI provider. Vì vậy, đặt timeout tại nguồn context là cách nhất quán để bảo vệ các đường truy cập cùng directory.

## 2. Phân biệt connect timeout và read timeout

Giả sử endpoint LDAP là **ldaps://ldap.example.org:636** và ứng dụng sử dụng tài khoản chỉ đọc để tìm người dùng.

~~~mermaid
sequenceDiagram
    participant App as Java / JNDI
    participant TCP as Mạng / TLS
    participant LDAP as LDAP server
    App->>TCP: Mở kết nối đến host:port
    Note over App,TCP: connect timeout giới hạn nỗ lực mở TCP
    TCP-->>App: TCP connected
    App->>LDAP: Thiết lập TLS và gửi BindRequest
    Note over App,LDAP: Chờ phản hồi LDAP: read timeout có thể áp dụng
    LDAP-->>App: BindResponse
    App->>LDAP: SearchRequest(uid=linh)
    Note over App,LDAP: Chờ phản hồi Search: read timeout
    LDAP-->>App: SearchResultEntry / SearchResultDone
~~~

| Tiêu chí | Connect timeout | Read timeout |
| --- | --- | --- |
| Khóa cấu hình JNDI | `com.sun.jndi.ldap.connect.timeout` | `com.sun.jndi.ldap.read.timeout` |
| Giai đoạn chính | Thiết lập TCP tới LDAP endpoint | Chờ một phản hồi LDAP sau khi đã kết nối |
| Đơn vị | **Mili giây (ms)** | **Mili giây (ms)** |
| Ví dụ | `"3000"` = 3 giây | `"5000"` = 5 giây |
| Nếu không khai báo | Thường để hệ điều hành/TCP quyết định thời gian kết nối | Provider có thể chờ phản hồi mà không có giới hạn đọc riêng |
| Nếu đặt `0` hoặc âm | Dùng timeout mạng mặc định theo provider | Không đặt read timeout theo provider |
| Biểu hiện thường gặp | Host/port không truy cập được, TCP không hoàn tất kết nối | TCP đã mở nhưng bind/search/modify không có phản hồi kịp thời |

Các thuộc tính **`com.sun.jndi.ldap.*` là cấu hình riêng của LDAP provider mặc định trong JDK**, không phải thuộc tính chuẩn của giao thức LDAP. Nếu ứng dụng thay provider, dùng socket factory đặc biệt hoặc một client LDAP khác, cần kiểm tra cấu hình và ngữ nghĩa của chính client đó.

### 2.1. Connect timeout không phải deadline cho toàn bộ request

Khi giá trị connect timeout là `3000`, provider cố giới hạn **lần mở kết nối TCP** trong khoảng 3 giây. Nó không có nghĩa toàn bộ quá trình **DNS → TCP → TLS → bind → search → mapping** hoàn tất trong 3 giây.

Cũng không nên coi thời gian đo bằng đồng hồ của mọi lỗi kết nối sẽ bằng đúng 3000 ms: DNS, lịch lập lịch thread, TLS, cơ chế mạng, provider và các lớp phía ngoài có thể ảnh hưởng. Nếu host phản hồi ngay bằng **connection refused**, lỗi thường xuất hiện sớm hơn timeout.

### 2.2. Read timeout có thể xảy ra ngay khi bind

Sau khi TCP mở thành công, LDAP client vẫn cần nhận **BindResponse** để xác thực. Nếu server chấp nhận kết nối nhưng không trả lời yêu cầu bind, **read timeout** có thể xảy ra trong giai đoạn khởi tạo `InitialDirContext`, trước khi ứng dụng chạy câu lệnh search.

Ngược lại, nếu bind thành công rồi một truy vấn phức tạp không nhận phản hồi, read timeout có thể phát sinh lúc `search(...)` hoặc lúc đọc `NamingEnumeration`. Vì vậy không thể mặc định “connect thành công” cũng có nghĩa “mọi thao tác LDAP đều phản hồi đúng hạn”.

## 3. Cấu hình trong Spring Boot bằng application.yml

Với ứng dụng Spring Boot sử dụng **spring-boot-starter-data-ldap**, các thuộc tính LDAP có thể cấu hình trong `application.yml`. Cơ chế **`spring.ldap.base-environment`** chuyển thêm các cặp key/value vào môi trường JNDI dùng để tạo context.

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "uid=reader,ou=services,dc=example,dc=org"
    password: "${LDAP_BIND_PASSWORD}"
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "3000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

**Đọc cấu hình:**

1. **urls** chỉ tới LDAP endpoint. Dùng `ldaps://` khi server đã cấu hình TLS và JVM tin cậy chứng chỉ máy chủ.
2. **base** là DN gốc chung: `dc=example,dc=org`. Khi gọi `LdapTemplate` dưới nhánh người dùng, có thể dùng base tương đối `ou=people`.
3. **username** là **bind DN** của tài khoản đọc; khác với DN của entry cần tìm.
4. **password** lấy từ biến môi trường **LDAP_BIND_PASSWORD** hoặc hệ thống quản lý secret; không commit mật khẩu thật vào source.
5. Hai giá trị timeout được đưa vào **JNDI environment** dưới dạng chuỗi số mili giây. Dấu ngoặc vuông trong key của ví dụ giúp giữ nguyên tên thuộc tính chứa dấu chấm qua Spring Boot configuration binding.

Các giá trị **3000 ms** và **5000 ms** là **ví dụ khởi đầu**, không phải cấu hình tối ưu cho mọi môi trường. Ứng dụng truy cập LDAP qua mạng nội bộ thường chọn deadline khác hệ thống liên vùng hoặc directory có nhiều referral.

### 3.1. Cùng cấu hình bằng application.properties

~~~properties
spring.ldap.urls=ldaps://ldap.example.org:636
spring.ldap.base=dc=example,dc=org
spring.ldap.username=uid=reader,ou=services,dc=example,dc=org
spring.ldap.password=${LDAP_BIND_PASSWORD}
spring.ldap.base-environment.[com.sun.jndi.ldap.connect.timeout]=3000
spring.ldap.base-environment.[com.sun.jndi.ldap.read.timeout]=5000
~~~

Khi đổi giữa YAML và properties, phải giữ đúng **tên khóa và đơn vị ms**. Hai giá trị này do JNDI provider diễn giải; chúng không nhận cú pháp `3s`, `5s` như một số `Duration` property khác của Spring Boot.

### 3.2. Kiểm tra trường hợp cấu hình không có hiệu lực

Nếu thay giá trị nhưng không thấy thời gian thay đổi, hãy kiểm tra:

- Ứng dụng có thực sự dùng **LDAP auto-configuration** của Spring Boot hay đã tự khai báo một `ContextSource` khác?
- `application.yml` nào đang được tải theo **profile**? Có cấu hình từ môi trường/command line ghi đè không?
- Bean `LdapTemplate` hoặc `LdapRepository` có đang tham chiếu cùng `ContextSource` được cấu hình timeout không?
- LDAP client có đang dùng JNDI provider của JDK hay thư viện khác?
- Kết nối được tái sử dụng từ pool hay đang mở kết nối TCP mới?
- Hành vi thử nghiệm đang là **TCP connect stall** hay **LDAP response stall**?

Đừng xuất toàn bộ LDAP environment ra log để kiểm tra vì có thể làm lộ **SECURITY_CREDENTIALS**. Chỉ ghi giá trị timeout, tên endpoint đã kiểm soát và thông tin profile không nhạy cảm.

## 4. Cấu hình chương trình với LdapContextSource

Khi dự án không dựa vào Spring Boot auto-configuration hoặc cần một `ContextSource` riêng, có thể đặt timeout qua phương thức **`setBaseEnvironmentProperties(...)`** của Spring LDAP.

Ví dụ Java Configuration, dùng các property riêng của ứng dụng:

~~~java
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
public class LdapConnectionConfiguration {
    @Bean
    LdapContextSource ldapContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.bind-dn}") String bindDn,
            @Value("${directory.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setBaseEnvironmentProperties(Map.of(
            "com.sun.jndi.ldap.connect.timeout", "3000",
            "com.sun.jndi.ldap.read.timeout", "5000"
        ));
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

Các property tương ứng có thể nằm trong một cấu hình riêng, dùng **thay thế** cho cách cấu hình Spring Boot tự động ở phần 3:

~~~yaml
directory:
  ldap:
    url: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    bind-dn: "uid=reader,ou=services,dc=example,dc=org"
    bind-password: "${LDAP_BIND_PASSWORD}"
~~~

Ví dụ giả định **directory.ldap.bind-password** được cấp bằng biến môi trường, secret manager hoặc cấu hình an toàn; không cần ghi giá trị vào mã. Spring quản lý vòng đời bean và gọi bước khởi tạo cần thiết của `LdapContextSource`.

**Lưu ý:** Nếu ứng dụng Spring Boot đã có `LdapContextSource` và `LdapTemplate` được auto-configure, không sao chép cấu hình bean này nguyên xi để tạo hai nguồn context ngoài ý muốn. Hãy chọn **một** cơ chế cấu hình rõ ràng, xác nhận bean nào được repository sử dụng, rồi thử bằng một thao tác LDAP thực.

## 5. Cấu hình trực tiếp trên JNDI

Để hiểu cơ chế nằm dưới Spring LDAP, có thể dùng API **`javax.naming.directory.InitialDirContext`** của JDK. Ví dụ truy vấn một entry bằng filter có tham số và timeout:

~~~java
import java.util.Hashtable;
import java.util.Objects;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public final class DirectJndiLookup {
    public static void main(String[] args) throws NamingException {
        String password = Objects.requireNonNull(
            System.getenv("LDAP_BIND_PASSWORD"),
            "LDAP_BIND_PASSWORD is required");

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL, "ldaps://ldap.example.org:636");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL,
            "uid=reader,ou=services,dc=example,dc=org");
        env.put(Context.SECURITY_CREDENTIALS, password);

        // Mili giây, giá trị dạng chuỗi.
        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
            new String[]{"uid", "cn", "mail"});
        controls.setCountLimit(50);
        controls.setTimeLimit(4000);

        DirContext context = null;
        NamingEnumeration<SearchResult> results = null;
        try {
            context = new InitialDirContext(env);
            results = context.search(
                "ou=people,dc=example,dc=org",
                "(uid={0})",
                new Object[]{"linh"},
                controls
            );
            while (results.hasMore()) {
                SearchResult entry = results.next();
                System.out.println(entry.getNameInNamespace());
            }
        } finally {
            try {
                if (results != null) {
                    results.close();
                }
            } finally {
                if (context != null) {
                    context.close();
                }
            }
        }
    }
}
~~~

Trong ví dụ:

- `Context.PROVIDER_URL` chỉ ra địa chỉ server. `InitialDirContext` tạo context thông qua LDAP provider của JDK.
- **Connect timeout** có thể phát sinh khi thiết lập TCP; **read timeout** có thể phát sinh khi chờ BindResponse hoặc SearchResponse.
- `controls.setTimeLimit(4000)` là **giới hạn riêng cho Search** của JNDI, không trùng với read timeout 5000 ms.
- `controls.setCountLimit(50)` hạn chế số kết quả trả về; nên thu hẹp base và filter theo nhu cầu.
- `(uid={0})` với `new Object[]{"linh"}` cho provider thực hiện escaping của **LDAP filter**, an toàn hơn nối chuỗi đầu vào.
- **NamingEnumeration** có thể tiếp tục đọc từ mạng trong vòng `hasMore()/next()`; timeout không chỉ có thể xảy ra ở dòng gọi `search`.
- **Đóng resources bằng finally** ngay cả khi timeout hoặc ngoại lệ, tránh giữ socket/context đang lỗi.

**JNDI dùng package `javax.naming` trong JDK**, kể cả khi dự án Spring dùng Jakarta API ở những tầng khác. Timeout JNDI không yêu cầu thêm dependency Maven/Gradle ngoài thành phần Spring LDAP/Spring Data LDAP đang dùng.

## 6. Read timeout khác với search time limit

Ba giới hạn sau dễ bị xem là một:

| Cơ chế | Ví dụ | Tác động | Có phải deadline tổng thể? |
| --- | --- | --- | --- |
| **JNDI connect timeout** | `3000` ms | Giới hạn chờ mở kết nối TCP; khi dùng native pooling còn có thể giới hạn chờ lấy kết nối từ pool | **Không** |
| **JNDI read timeout** | `5000` ms | Giới hạn việc chờ một phản hồi LDAP | **Không** |
| **Search time limit** | `4000` ms | Giới hạn thời gian dành cho một thao tác tìm kiếm theo JNDI/Spring LDAP và đặc tính của provider/server | **Không** |
| **Deadline của request ứng dụng** | Ví dụ 8000 ms | Giới hạn thời gian mà HTTP request/job được phép sử dụng | **Phụ thuộc cách triển khai** |

**Read timeout** bảo vệ trường hợp server không trả phản hồi kịp thời. Nó không phải đồng hồ cộng dồn cho toàn bộ `search` nhiều entry, nhiều LDAP response hoặc nhiều lần retry. **Search time limit** áp dụng cho thao tác tìm kiếm, trong khi các thao tác **bind, modify, add, delete** không sử dụng SearchControls time limit.

Theo LDAPv3, SearchRequest còn có trường `timeLimit` để server áp đặt giới hạn tìm kiếm. Cách chuyển đổi thời gian giữa Java API và yêu cầu giao thức, cũng như lỗi trả về, phụ thuộc LDAP provider/server. Vì vậy **đừng cộng trừ ba timeout rồi coi đó là cam kết thời gian thực thi tối đa**.

### 6.1. Thiết lập time limit từ LdapTemplate

Khi Spring LDAP có bean `LdapTemplate`, có thể tạo một query có giới hạn rõ ràng:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class DirectorySearchService {
    private final LdapTemplate ldapTemplate;

    public DirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people")
                   .searchScope(SearchScope.SUBTREE)
                   .timeLimit(4000)
                   .countLimit(50)
                   .attributes("uid", "cn")
                   .where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString()
        );
    }
}
~~~

**`.timeLimit(4000)`** giới hạn tìm kiếm ở mức query Spring LDAP, còn **read timeout** được lấy từ cấu hình JNDI trong `ContextSource`. Query dùng **base tương đối `ou=people`** khi ContextSource đã có base **dc=example,dc=org**. Nếu server không trả `cn` do ACL hoặc entry không có thuộc tính này, mapper mẫu có thể ném lỗi; ứng dụng thật cần chính sách dữ liệu rõ ràng.

Spring LDAP cũng có thể cấu hình giới hạn tìm kiếm mặc định trên `LdapTemplate` (ví dụ `setDefaultTimeLimit` và `setDefaultCountLimit`) để những query không nêu limit dùng giá trị chung. Thiết lập ở từng query sẽ phù hợp khi các thao tác có SLA khác nhau.

### 6.2. Tình huống server trả TimeLimitExceeded

Khi directory không xử lý xong một truy vấn trong giới hạn tìm kiếm, server/client có thể báo **`timeLimitExceeded`** (LDAP result code **3**) hoặc JNDI/Spring LDAP ném **TimeLimitExceededException**. Đây là tín hiệu khác với **TCP connect timeout** hay **LDAP response read timeout**.

Một filter quá rộng như `(objectClass=*)` từ suffix lớn thường cần điều chỉnh **base DN, scope, attributes, phân trang và index của server** trước khi chỉ tăng time limit. Truy vấn trả về ít kết quả do giới hạn chưa chắc là dữ liệu không tồn tại.

## 7. Spring Data LDAP Repository dùng timeout nào?

Ví dụ entity và repository cho người dùng LDAP:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Constructor không tham số, getters/setters được lược bỏ.
}
~~~

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Lời gọi `personRepository.findByUid("linh")` sử dụng cấu hình **Spring Data LDAP → Spring LDAP → ContextSource → JNDI**. Do đó, nếu repository thực sự dùng `ContextSource` đã đặt `com.sun.jndi.ldap.read.timeout=5000`, timeout đọc áp dụng cho yêu cầu LDAP tạo ra từ repository đó.

Điều này **không có nghĩa repository luôn hỗ trợ một property tên `repository.timeout`**, và cũng không có nghĩa một phương thức repository tự thêm SearchControls giống ví dụ ở phần 6. Khi cần kiểm soát riêng `searchScope`, `timeLimit`, thuộc tính trả về hoặc logic filter, **LdapTemplate** cung cấp API trực tiếp hơn.

Ngoài ra, việc `PersonRepository` có bean trong Spring context không chứng minh LDAP endpoint hoạt động. Spring có thể chỉ mở kết nối khi request đầu tiên thực hiện thao tác. Kiểm tra thời gian phải chạy lệnh LDAP thật, không chỉ khởi tạo đối tượng.

## 8. Chọn giá trị timeout theo hành vi thực tế

Không có một cặp số phù hợp cho mọi hệ thống. Nên bắt đầu từ mục tiêu đáp ứng của API, độ trễ mạng, tốc độ directory và độ dài tìm kiếm thực tế.

| Môi trường minh họa | Connect timeout | Read timeout | Nhận xét |
| --- | ---: | ---: | --- |
| Lab cục bộ, server gần ứng dụng | 1000–2000 ms | 2000–5000 ms | Giúp phát hiện dịch vụ treo; có thể quá ngắn nếu máy lab khởi động chậm |
| Directory nội bộ ổn định | 2000–3000 ms | 3000–8000 ms | Giá trị khởi đầu để đo và điều chỉnh |
| Kết nối liên vùng/qua WAN | 3000–5000 ms | 5000–15000 ms | Phải dựa trên độ trễ p95/p99 và yêu cầu nghiệp vụ thực tế |

**Các khoảng trên chỉ là ví dụ để thực hành**, không phải tiêu chuẩn SLA hoặc khuyến nghị áp dụng nguyên xi cho production. Những yếu tố cần đo:

1. **TCP connect latency** trên đúng endpoint.
2. **Bind latency** của tài khoản dịch vụ và chính sách xác thực.
3. **Thời gian search** với filter, base, scope và số entry thực tế.
4. Độ trễ **TLS, DNS, LDAP referral, load balancer** và việc thử nhiều URL.
5. Số lượng request đồng thời, connection pool và khả năng quá tải directory.
6. Deadline HTTP/job, số lần retry được phép và yêu cầu của các hệ thống gọi phía trên.

### 8.1. Ví dụ xây một ngân sách thời gian

Giả sử API cần trả lời trong khoảng **8 giây** và LDAP chỉ là một trong các dependency:

~~~text
HTTP request deadline (ví dụ):          8000 ms
    ├─ TCP connect timeout LDAP:        2000 ms
    ├─ LDAP response read timeout:      4000 ms
    ├─ Search time limit:               3000 ms
    └─ Xử lý Java + dependency khác:    ngân sách còn lại
~~~

Đây là **các giới hạn của từng giai đoạn**, không phải một phép cộng bảo đảm tổng thời gian là 8 giây. Nếu provider chuyển qua nhiều URL, thử lại nhiều lần hoặc nhận nhiều phản hồi, tổng độ trễ có thể khác đáng kể. Deadline cấp ứng dụng cần được thực thi riêng và quan sát thực tế, đồng thời không nên giả định hủy tác vụ Java lập tức hủy mọi request đã tới server.

## 9. Nhiều LDAP URL, kết nối dự phòng và pooling

### 9.1. Khi có nhiều LDAP endpoint

Ví dụ:

~~~yaml
spring:
  ldap:
    urls:
      - "ldaps://ldap-a.example.org:636"
      - "ldaps://ldap-b.example.org:636"
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "3000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

Provider có thể thử **nhiều URL** theo cơ chế failover. Theo hướng dẫn JNDI của Oracle, connect timeout có thể áp dụng **cho từng lần thử endpoint**, vì vậy hai URL với connect timeout 3 giây có thể khiến thời gian chờ tích lũy vượt quá 3 giây. Cần đo thực tế và xét tổng ngân sách request.

Failover cũng đặt ra vấn đề **directory replication**: node dự phòng có thể chưa nhận bản ghi mới nhất. Timeout giải quyết vấn đề thời gian chờ, nhưng không bảo đảm dữ liệu LDAP nhất quán giữa các replica.

### 9.2. Connect timeout và connection pooling

Khi sử dụng **native JNDI LDAP connection pooling**, `com.sun.jndi.ldap.connect.timeout` còn có thể giới hạn **thời gian chờ mượn kết nối từ pool** nếu pool đã đạt số lượng kết nối tối đa và mọi kết nối đang bận. Điều này khác với một lần TCP connect tới server.

Không nhầm với thuộc tính hệ thống **`com.sun.jndi.ldap.connect.pool.timeout`**: thuộc tính này dùng để quản lý **thời gian idle của pooled connection**, không thay thế connect timeout cho request. Các giới hạn pool, số lượng kết nối và thời gian chờ cần được đặt và đo cùng nhau.

**Cảnh báo quan trọng:** Native JNDI pooling không phù hợp với mọi trường hợp **StartTLS** hoặc thao tác thay đổi trạng thái bảo mật của context. Tài liệu Oracle khuyến cáo tránh pool context có thay đổi trạng thái kết nối vì provider không nhất thiết theo dõi những thay đổi đó. Nếu dùng Spring LDAP pooling, cần xem hướng dẫn pool cụ thể và kiểm thử kết hợp TLS/authentication.

### 9.3. Pool không loại bỏ read timeout

Khi có kết nối TCP sẵn trong pool, truy vấn vẫn phải chờ LDAP server phản hồi. Vì vậy một hệ thống “đã warm up pool” vẫn cần **read timeout**. Mặt khác, timeout có thể khiến kết nối không còn dùng được; client/pool phải loại bỏ hoặc kiểm chứng kết nối lỗi trước khi tái sử dụng.

## 10. Nhận diện lỗi timeout trong ứng dụng Java

Các hiện tượng có thể có:

| Quan sát | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Connect timed out` hoặc lỗi mở socket | TCP không mở được trong thời gian kết nối | Kiểm tra DNS, host, port, firewall, routing, TLS endpoint |
| `Connection refused` xuất hiện ngay | Máy đích từ chối TCP | Kiểm tra dịch vụ và cổng, không mặc định tăng timeout |
| `LDAP response read timed out` | Provider đã chờ phản hồi LDAP quá giới hạn | Kiểm tra bind/search/modify, tải server, mạng, log LDAP |
| `TimeLimitExceededException` hoặc LDAP code 3 | Giới hạn thời gian tìm kiếm bị vượt | Thu hẹp base/filter, kiểm tra server search limit và index |
| `AuthenticationException` / code 49 | Bind DN hoặc credentials không hợp lệ | Kiểm tra xác thực; tăng read timeout không sửa mật khẩu sai |
| `NameNotFoundException` / code 32 | Search base hoặc DN đích không tồn tại/không thấy | Kiểm tra DN tương đối, suffix, ACL |
| `SizeLimitExceededException` / code 4 | Search bị giới hạn số entry | Dùng filter hẹp, paging khi cần; không coi là 0 kết quả |
| `SSLHandshakeException` trong cause | Vấn đề TLS/certificate hoặc handshake | Kiểm tra truststore, hostname, CA và cấu hình TLS |

Ở tầng JNDI, các lỗi liên lạc có thể xuất hiện dưới **`javax.naming.CommunicationException`**, **`ServiceUnavailableException`** hoặc một **NamingException** mang thông điệp/cause thích hợp, tùy giai đoạn và provider.

Ở tầng Spring LDAP, các exception JNDI thường được dịch thành các runtime exception như **`org.springframework.ldap.CommunicationException`** hoặc **`org.springframework.ldap.TimeLimitExceededException`**. Không nên cứng nhắc rằng **mọi read timeout** đều chuyển thành **một** loại exception cố định trong mọi phiên bản và mọi tình huống. Đọc **cause chain**, thông điệp và mã LDAP gốc khi có.

### 10.1. Xử lý lỗi trong service

Ví dụ service với `LdapTemplate` phân biệt lỗi truy cập LDAP với một kết quả tìm kiếm hợp lệ không có entry:

~~~java
import java.util.List;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.TimeLimitExceededException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        try {
            return ldapTemplate.search(
                query().base("ou=people")
                       .timeLimit(3000)
                       .where("uid").is(uid),
                (AttributesMapper<String>) attrs ->
                    attrs.get("cn").get().toString()
            );
        } catch (TimeLimitExceededException ex) {
            throw new DirectoryTemporarilyUnavailableException(
                "LDAP search exceeded its allowed time", ex);
        } catch (CommunicationException ex) {
            throw new DirectoryTemporarilyUnavailableException(
                "LDAP connection or response failed", ex);
        }
    }

    public static final class DirectoryTemporarilyUnavailableException
            extends RuntimeException {
        public DirectoryTemporarilyUnavailableException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Đây là mẫu **phân loại lỗi ở tầng service**. Nó chưa bao phủ mọi ngoại lệ LDAP/TLS/timeout; ứng dụng thật cần chính sách error handling thích hợp và giữ cause ở log nội bộ. **Không trả `List.of()` trong catch timeout** vì làm người gọi tưởng rằng tài khoản chắc chắn không tồn tại.

## 11. Retry: khi nào an toàn và khi nào nguy hiểm?

Timeout không luôn có nghĩa server chưa thực hiện lệnh. Ví dụ:

~~~text
Client gửi LDAP Modify để thay mail
LDAP server nhận và ghi thành công
Mạng đứt trước khi Client nhận LDAP ModifyResponse
Client bị read timeout
~~~

Nếu client tự gửi lại cùng lệnh, hiệu ứng có thể lặp, gây lỗi hoặc ghi đè cập nhật đồng thời. Vì vậy:

| Loại thao tác | Retry gợi ý | Rủi ro cần kiểm tra |
| --- | --- | --- |
| **Search/read** | Có thể retry giới hạn theo chính sách | Tổng thời gian tăng, quá tải server, dữ liệu replica khác nhau |
| **Add entry** | Chỉ retry khi xác minh trạng thái/đảm bảo idempotency | Entry đã được tạo có thể trả `entryAlreadyExists` |
| **Modify attributes** | Xem lại trạng thái mới rồi quyết định | Có thể ghi đè dữ liệu hoặc áp dụng lại thay đổi |
| **Delete entry** | Kiểm tra trạng thái sau timeout | Lệnh đầu có thể đã xóa entry; retry nhận `noSuchObject` |
| **Rename / Move DN** | Không retry mù quáng | DN nguồn có thể đã thay đổi dù client chưa nhận phản hồi |

Một chiến lược retry tốt có **giới hạn số lần**, **backoff có jitter**, deadline cấp request và thống kê lỗi; không retry vô hạn hoặc retry tất cả LDAP exception. Đặc biệt không retry lỗi **invalidCredentials**, **invalidDNSyntax**, **schemaViolation** như thể chúng là lỗi mạng tạm thời.

## 12. Bảo mật kết nối khi cấu hình timeout

Timeout và bảo mật hỗ trợ nhau nhưng là hai mục tiêu khác nhau:

1. **Dùng LDAPS hoặc StartTLS** khi truyền simple bind credentials và dữ liệu LDAP; đảm bảo xác minh certificate chain và tên máy chủ.
2. **Không tắt kiểm tra chứng chỉ** chỉ vì thao tác TLS có vẻ chậm hoặc thất bại.
3. **Không hardcode bind password** vào `application.yml`, Java source, command line hoặc log; dùng biến môi trường/secret manager.
4. **Giới hạn quyền bind DN** theo nghiệp vụ. Tài khoản chỉ cần tìm kiếm không nên được cấp quyền quản trị để “sửa” lỗi timeout.
5. **Giới hạn base DN, filter và attributes** để giảm tải server, đồng thời dùng filter builder/parameters nhằm tránh **LDAP injection**.
6. **Giới hạn kết quả và thời gian tìm kiếm**, đặc biệt khi truy vấn cả subtree có nhiều entry.
7. Khi sử dụng **referral hoặc nhiều endpoint**, kiểm soát hành vi xác thực tới server đích và xác minh từng endpoint.

Một kết nối có timeout hợp lý nhưng dùng `ldap://` với simple bind credentials qua mạng không an toàn vẫn là triển khai không đạt yêu cầu bảo mật.

## 13. Đo và kiểm thử connect/read timeout

**Không nên kiểm chứng bằng cách nhìn cấu hình YAML rồi kết luận timeout đang hoạt động.** Cần thực hiện request thật với đúng bean `ContextSource` và đúng loại tình huống lỗi.

### 13.1. Ma trận kiểm thử

| Kịch bản | Cách mô phỏng có kiểm soát | Kỳ vọng |
| --- | --- | --- |
| Kết nối bình thường | Directory test trả bind và search nhanh | Truy vấn thành công, trả đúng entry |
| TCP connect không hoàn tất | Endpoint lab hoặc proxy mạng cố ý làm trễ TCP handshake | Kết nối lỗi theo connect timeout; đo thực tế với từng môi trường |
| Port đóng | Endpoint lab không có listener | Lỗi kết nối sớm, có thể **connection refused** |
| TCP đã nhận nhưng không có BindResponse | LDAP test double nhận TCP rồi không trả LDAP response | Read timeout xuất hiện trong giai đoạn bind |
| Bind OK nhưng search chậm | Server/proxy test cố ý làm chậm SearchResponse | Read timeout hoặc search time limit theo ngưỡng nào đến trước |
| Search vượt giới hạn server | Query nặng trong directory test có giới hạn time | Nhận code 3 hoặc exception tương ứng khi server thực thi giới hạn |
| Nhiều URL failover | Endpoint A không kết nối được, B hoạt động | Thử endpoint theo cơ chế provider và đo tổng latency |
| Pool hết kết nối | Cấu hình pool giới hạn và nhiều client đồng thời | Kiểm tra thời gian chờ mượn connection và lỗi tương ứng |
| Modify thành công nhưng mất phản hồi | Proxy test bỏ ModifyResponse sau khi server áp dụng | Client không retry mù quáng; service đối chiếu trạng thái |

**Chú ý tính xác định:** một IP “không dùng” không bảo đảm gây **TCP timeout**; hệ điều hành có thể trả ngay `No route to host` hoặc `Connection refused`. Để kiểm thử ngưỡng thời gian đáng tin cậy, nên dùng một **test proxy/fault injector** kiểm soát được việc chấp nhận, giữ hoặc trì hoãn kết nối/LDAP response.

Nếu dùng LDAP nhúng (ví dụ UnboundID) để kiểm tra mapping và query, nên bổ sung integration test với **OpenLDAP hoặc directory server mục tiêu** khi cần xác minh pooling, TLS, ACL hoặc các đặc tính provider/server khác.

### 13.2. Đo thời gian tại service

Ví dụ đo duration của một lời gọi repository:

~~~java
long started = System.nanoTime();
try {
    personRepository.findByUid("linh");
} finally {
    long elapsedMs =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started);
    // Gửi elapsedMs vào metric/telemetry, không log mật khẩu.
}
~~~

Code minh họa nằm trong phương thức có `personRepository` đã được inject. **System.nanoTime()** thích hợp để đo thời gian đã trôi qua, nhưng chỉ đo tổng duration: muốn biết nghẽn ở **TCP connect**, **bind**, **search**, **pool wait** hay **mapping**, phải bổ sung metric hoặc instrumentation tương ứng.

Các metric nên quan sát: tỉ lệ timeout theo loại, p50/p95/p99 latency, số lần retry, tỉ lệ lỗi LDAP theo endpoint, pool utilization và lượng request đang đợi. Khi điều tra, dùng **trace/request ID** và che dữ liệu cá nhân như uid/email nếu chính sách yêu cầu.

### 13.3. Đối chiếu bằng ldapsearch

Lệnh `ldapsearch` hữu ích để xác minh directory có dữ liệu và tìm kiếm có hoạt động:

~~~bash
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "uid=reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=linh)" dn uid cn
~~~

Tuy nhiên, `ldapsearch` là **client khác JNDI**; các tham số timeout của nó, cách xử lý TLS và connection pooling có thể khác ứng dụng Java. Việc câu lệnh thành công chỉ giúp xác nhận **endpoint, bind identity, base/filter, ACL và dữ liệu**, chưa chứng minh property `com.sun.jndi.ldap.read.timeout` đã được ứng dụng Spring nhận.

## 14. Cách chẩn đoán theo triệu chứng

| Triệu chứng | Kiểm tra ưu tiên |
| --- | --- |
| Request chờ lâu trước khi bind | DNS, firewall, endpoint, TCP connect timeout, TLS và nhiều URL |
| Kết nối mở nhưng bind chậm | LDAP BindResponse, read timeout, server authentication, TLS |
| Bind nhanh nhưng search chậm | Search base/scope/filter, index, search time limit và read timeout |
| Tăng connect timeout mà search vẫn treo | Read timeout, server search limit, phản hồi từng phần, client enumeration |
| Read timeout rất ngắn gây lỗi ngẫu nhiên | Độ trễ mạng thực, tải server, p99 và ngưỡng đang chọn |
| Chỉ lỗi khi số request tăng | Pool exhaustion, giới hạn connection server, thread saturation, query tải cao |
| Một endpoint chậm, endpoint khác nhanh | Per-endpoint latency, failover và tình trạng replica |
| Repository trả rỗng thay vì timeout | Filter/base DN/ACL hoặc code đang nuốt exception; kiểm tra result code gốc |
| TLS handshake thất bại | Truststore, certificate, tên host; không sửa bằng tăng timeout mù quáng |
| Sau timeout, thao tác Modify có kết quả bất ngờ | Request có thể đã thành công trên server; đối chiếu trạng thái trước khi retry |

### Quy trình xử lý có thể lặp lại

1. **Xác định loại lỗi** bằng thông điệp và cause chain, tránh coi tất cả là `CommunicationException`.
2. **Chốt endpoint, bind DN và ContextSource** mà ứng dụng thực sự sử dụng.
3. **Xác nhận hai property JNDI** có hiệu lực trong môi trường chạy đúng profile.
4. **Phân biệt connect stall với read stall**, kiểm tra TLS/pool nếu có.
5. **Đối chiếu câu lệnh search** bằng base DN đầy đủ, filter và tài khoản có quyền tương đương.
6. **Đo latency thực**, đối chiếu với deadline ứng dụng và số lần retry.
7. **Điều chỉnh giá trị và truy vấn**, sau đó chạy lại integration test có kịch bản failure được kiểm soát.

## 15. Câu hỏi tự kiểm tra

1. Vì sao `com.sun.jndi.ldap.connect.timeout=3000` không bảo đảm mỗi lần `findByUid` hoàn tất trong 3 giây?
2. Một TCP socket đã mở, nhưng server không gửi **BindResponse**. Thuộc tính timeout nào phù hợp nhất và vì sao?
3. Khi `LdapTemplate.search` nhận nhiều entry chậm, **read timeout** khác **SearchControls time limit** như thế nào?
4. Nếu một ứng dụng có 2 LDAP URL, connect timeout có luôn là trần cho tổng thời gian tìm endpoint không?
5. Tại sao nên dùng `spring.ldap.base-environment` khi ứng dụng Spring Boot sử dụng JNDI provider mặc định?
6. Nếu dùng native LDAP connection pool, `connect.timeout` còn có thể giới hạn thời gian chờ nào?
7. Vì sao không thể mặc định retry `save`, `delete`, `rename` sau một read timeout?
8. Làm sao xác minh timeout thực sự được áp dụng cho chính `LdapRepository` đang chạy?
9. Những khác biệt quan trọng khi thử timeout bằng `ldapsearch` và khi chạy qua Spring LDAP là gì?
10. Nếu lỗi đến từ chứng chỉ TLS không được tin cậy, bạn sẽ kiểm tra gì trước khi điều chỉnh timeout?

## 16. Ghi nhớ

**Connect timeout** và **read timeout** bảo vệ hai giai đoạn khác nhau của thao tác LDAP. Với JNDI LDAP provider của JDK, hãy cấu hình **`com.sun.jndi.ldap.connect.timeout`** và **`com.sun.jndi.ldap.read.timeout`** bằng **số mili giây dương dạng chuỗi**, thường qua **`spring.ldap.base-environment`** trong Spring Boot hoặc **`LdapContextSource.setBaseEnvironmentProperties(...)`** khi tự khai báo context.

Để một dịch vụ Spring Data LDAP phản hồi ổn định, cần kết hợp timeout kết nối/đọc với **search time limit**, **scope/filter hiệu quả**, chính sách **deadline/retry**, quản lý **pool**, bảo vệ TLS và integration test trên directory. **Không coi một timeout là deadline tổng của toàn bộ request**, cũng không suy diễn lỗi timeout nghĩa là thao tác ghi chắc chắn chưa xảy ra.

## Tài liệu tham khảo

- [JDK 21 — Module java.naming](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/module-summary.html): định nghĩa hai property `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout`.
- [Oracle — JNDI/LDAP Service Provider](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html): thời gian chờ, đa URL và hành vi native LDAP pooling.
- [Oracle — JNDI read timeout](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html): timeout chờ LDAP response, kể cả trong lúc bind.
- [Oracle — SearchControls](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/SearchControls.html): `setTimeLimit`, `setCountLimit`, scope và returning attributes.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.ldap.base-environment.*` và các thiết lập LDAP.
- [Spring LDAP — ContextSource Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): custom environment properties, pooling, template search defaults.
- [Spring LDAP — AbstractContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): `setBaseEnvironmentProperties(Map)`.
- [Spring LDAP — LdapQueryBuilder](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): `timeLimit`, `countLimit` và filter an toàn.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ánh xạ entry LDAP.
