# Default context factory và class path cần thiết

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **initial context factory** của JNDI là gì và vì sao LDAP provider mặc định trong các bản JDK OpenJDK/Oracle JDK phổ biến có tên `com.sun.jndi.ldap.LdapCtxFactory`.
- Phân biệt **LDAP provider có sẵn trong JDK**, **Spring LDAP core**, **Spring Data LDAP** và **Spring Security LDAP**, từ đó xác định đúng dependency cho từng lớp chức năng.
- Cấu hình `LdapContextSource` và `LdapTemplate` trong Spring thuần hoặc dùng Spring Boot LDAP auto-configuration mà không đăng ký chồng chéo.
- Phân biệt **classpath**, **module path (JPMS)** và runtime image do `jlink` tạo; chẩn đoán lỗi thiếu `java.naming` hoặc thiếu JAR Spring.
- Nhận diện vì sao lỗi `ClassNotFoundException`, bind thất bại, sai base DN, timeout và TLS handshake failure cần các cách khắc phục khác nhau.
- Vận dụng cách cấu hình an toàn về URL, tài khoản bind, secret, chứng chỉ và quyền truy cập.

Bài thuộc chương **Cấu hình ContextSource** của module **SPRING_LDAP**. Khi học `ContextSource`, `LdapTemplate`, `LdapClient`, ODM, xác thực, TLS và pooling, bạn cần hiểu chính xác thành phần nào thực sự mở kết nối LDAP: Spring LDAP cung cấp API và quản lý context, còn **LDAP JNDI provider** chịu trách nhiệm triển khai giao thức.

## 1. Hai đối tượng “factory” nhưng hai vai trò

Trong ứng dụng Spring LDAP có hai lớp rất dễ bị gọi nhầm là một:

| Khái niệm | API / class | Vị trí | Vai trò |
| --- | --- | --- | --- |
| **Initial context factory** của JNDI | `javax.naming.spi.InitialContextFactory`; implementation thường dùng `com.sun.jndi.ldap.LdapCtxFactory` | LDAP provider trong module `java.naming` của JDK | Tạo initial naming/directory context dựa trên môi trường JNDI |
| **Context source** của Spring LDAP | `org.springframework.ldap.core.ContextSource`, `org.springframework.ldap.core.support.LdapContextSource` | Thư viện `spring-ldap-core` | Cung cấp context cho các thao tác LDAP, tổ chức cấu hình kết nối và credentials |
| **Template** thao tác LDAP | `org.springframework.ldap.core.LdapTemplate` | `spring-ldap-core` | Gọi search, lookup, bind, modify, unbind và ánh xạ kết quả |
| **LDAP repository** | `LdapRepository`, `@EnableLdapRepositories` | `spring-data-ldap` | Truy cập entry như entity/repository |
| **LDAP authentication** | Các thành phần LDAP của Spring Security | `spring-security-ldap` | Tích hợp đăng nhập và quyền với Spring Security |

**Phân biệt quan trọng:** `LdapCtxFactory` thuộc hạ tầng JNDI, còn `LdapContextSource` là implementation của **Spring LDAP**. Cả hai có thể cùng tham gia **một thao tác kết nối**, nhưng không phải cùng một class hoặc cùng dependency.

### Luồng tạo context

~~~mermaid
flowchart TB
    App["Ứng dụng Spring"]
    Template["LdapTemplate / LdapClient<br/>Hoặc LDAP repository"]
    ContextSource["Spring LDAP<br/>LdapContextSource"]
    Env["JNDI environment<br/>provider URL · bind DN · credentials"]
    Factory["JNDI LDAP InitialContextFactory<br/>com.sun.jndi.ldap.LdapCtxFactory"]
    LDAP[("LDAP server<br/>LDAP / LDAPS")]
    App --> Template --> ContextSource
    ContextSource --> Env --> Factory --> LDAP
    Sec["Spring Security LDAP"] --> ContextSource
~~~

Ứng dụng thường **không phải tự tạo `InitialDirContext`** trong từng service khi đã dùng `LdapTemplate`. `ContextSource` đảm nhiệm việc khởi tạo context theo cấu hình, còn `LdapTemplate` quản lý cách gọi và giải phóng tài nguyên tương ứng.

## 2. Default context factory thực chất là gì?

JNDI là Java Naming and Directory Interface. Một lời gọi khởi tạo context có thể sử dụng môi trường `Hashtable` chứa cấu hình:

~~~java
import javax.naming.Context;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import java.util.Hashtable;

Hashtable<String, String> env = new Hashtable<>();

env.put(
    Context.INITIAL_CONTEXT_FACTORY,
    "com.sun.jndi.ldap.LdapCtxFactory"
);
env.put(
    Context.PROVIDER_URL,
    "ldaps://ldap.example.org:636"
);
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(
    Context.SECURITY_PRINCIPAL,
    "uid=reader,ou=services,dc=example,dc=org"
);
env.put(
    Context.SECURITY_CREDENTIALS,
    System.getenv("LDAP_BIND_PASSWORD")
);

DirContext ctx = new InitialDirContext(env);
try {
    // Thực hiện các thao tác LDAP phù hợp.
} finally {
    ctx.close();
}
~~~

Ý nghĩa của cấu hình:

- `Context.INITIAL_CONTEXT_FACTORY` định danh class factory cho initial context; giá trị quen thuộc của LDAP provider trên các JDK nói trên là `com.sun.jndi.ldap.LdapCtxFactory`.
- `Context.PROVIDER_URL` cung cấp URI server; `ldap://` và `ldaps://` dẫn đến lựa chọn cơ chế bảo vệ kết nối khác nhau.
- `Context.SECURITY_PRINCIPAL` và `Context.SECURITY_CREDENTIALS` mô tả danh tính/tài khoản dùng để bind khi truy cập directory.
- `Context.SECURITY_AUTHENTICATION = "simple"` yêu cầu cơ chế xác thực đơn giản của JNDI; truyền mật khẩu như ví dụ chỉ nên thực hiện trên kết nối đã được bảo vệ và xác minh chứng chỉ.

**Điểm cần nói chính xác về chữ “default”:** `com.sun.jndi.ldap.LdapCtxFactory` thường được gọi là *default context factory* khi nói về cấu hình Spring LDAP dùng provider JNDI mặc định trên JDK phổ biến. Trong **JNDI thuần**, đừng giả định rằng bỏ `Context.INITIAL_CONTEXT_FACTORY` thì mọi môi trường Java sẽ tự chọn LDAP. Initial context factory có thể được lấy từ nhiều nguồn cấu hình hoặc service/provider discovery tùy môi trường; ví dụ JNDI trên nên đặt **tường minh** để tránh nhập nhằng.

### 2.1. Tại sao tên bắt đầu bằng `com.sun`?

Tên `com.sun.jndi.ldap.LdapCtxFactory` là tên implementation của LDAP JNDI provider quen thuộc trên Oracle/OpenJDK. Việc package bắt đầu bằng `com.sun` **không đồng nghĩa** bạn cần tải một thư viện “Sun LDAP” riêng từ Maven.

Trong một **JDK đầy đủ có module `java.naming`**, provider LDAP này thường đi kèm runtime. Đây là lớp implementation do JDK cung cấp, vì vậy cần xét khả năng tương thích của JDK/runtime đang dùng thay vì coi nó là public API ổn định để ứng dụng thao tác trực tiếp.

Ứng dụng nên phụ thuộc vào các interface chuẩn `javax.naming.*` và lớp `ContextSource` của Spring LDAP; không nên import và khởi tạo trực tiếp implementation `com.sun.jndi.ldap.LdapCtxFactory` trong mã nghiệp vụ.

### 2.2. `InitialContextFactory` khác `ObjectFactory`

Các interface JNDI có tên gần giống nhau nhưng phục vụ mục đích khác:

- `InitialContextFactory`: tạo initial context cho việc tiếp cận naming/directory provider.
- `javax.naming.spi.ObjectFactory`: có thể tạo một Java object từ một object/reference mà JNDI cung cấp.
- `javax.naming.spi.DirObjectFactory`: dạng factory dành cho directory, có overload nhận `Attributes`.

Đăng ký `Context.OBJECT_FACTORIES` **không thể thay thế** cấu hình `Context.INITIAL_CONTEXT_FACTORY` khi muốn kết nối LDAP. Ngược lại, chọn LDAP context factory không khiến mọi entry LDAP tự trở thành Java entity. Spring LDAP thường ánh xạ entry bằng `AttributesMapper`, `ContextMapper` hoặc ODM.

## 3. Spring LDAP dùng LDAP JNDI provider như thế nào?

`LdapContextSource` là implementation `ContextSource` của Spring LDAP, dựa trên JNDI. Nó xây môi trường truy cập directory và cung cấp context cho template/LDAP service.

Các khái niệm đáng nhớ:

| Thành phần | Ý nghĩa |
| --- | --- |
| `ContextSource` | Hợp đồng để lấy context phù hợp cho thao tác LDAP |
| `LdapContextSource` | Implementation của Spring LDAP sử dụng JNDI |
| `LdapTemplate` | Tiện ích thực thi thao tác LDAP qua `ContextSource` |
| `base` | Base DN được sử dụng làm ngữ cảnh cho DN/search base tương đối |
| `url` / `urls` | Địa chỉ của LDAP server hoặc các server theo cấu hình hỗ trợ |
| `userDn` / `password` | Tài khoản bind được dùng cho các thao tác dưới danh tính dịch vụ |
| `context factory` | Implementation `InitialContextFactory` mà JNDI dùng để tạo context |

Khi dùng `LdapContextSource` thông thường, Spring LDAP đã biết provider JNDI mặc định cho LDAP trong môi trường JDK được hỗ trợ; **bạn thường chỉ cần URL, base DN và thông tin bind**. Không cần viết lại tên `LdapCtxFactory` trong mỗi lời gọi `search`.

Đừng nhầm các giá trị sau:

~~~text
LDAP host URL:
    ldaps://ldap.example.org:636

Directory base DN:
    dc=example,dc=org

Service bind DN:
    uid=reader,ou=services,dc=example,dc=org

Relative search base:
    ou=people
~~~

Ở cấu hình này, tìm với relative search base `ou=people` nghĩa là tìm dưới `ou=people,dc=example,dc=org` (theo ngữ nghĩa API áp dụng). Nếu đưa lại full DN vào tham số yêu cầu DN tương đối, bạn có thể nhân đôi base hoặc nhắm sai entry. Đây là lỗi DN, **không phải lỗi context factory**.

## 4. Classpath: muốn dùng Spring LDAP cần dependency nào?

Trên JVM thông thường, có **hai nguồn class** cần phân biệt:

1. **JDK** cung cấp JNDI API và provider LDAP trong module `java.naming`.
2. **Dependencies của ứng dụng** cung cấp các lớp Spring LDAP và các Spring Framework dependency liên quan.

### 4.1. JNDI và LDAP provider từ JDK

Các class như:

~~~java
javax.naming.Context
javax.naming.directory.DirContext
javax.naming.directory.InitialDirContext
javax.naming.ldap.LdapName
javax.naming.spi.InitialContextFactory
~~~

thuộc Java SE, module **`java.naming`**. Với JDK có module đó, bạn thường không cần dependency Maven/Gradle riêng cho JNDI API.

Trong một JDK OpenJDK/Oracle JDK phổ biến, class `com.sun.jndi.ldap.LdapCtxFactory` cũng được cung cấp bởi implementation trong `java.naming`. Việc có module này trên runtime ảnh hưởng khả năng tạo context LDAP.

**Với Java 9+ và JPMS:** nếu viết ứng dụng dưới dạng *named module* với `module-info.java` và dùng API JNDI trực tiếp, cần khai báo:

~~~java
module example.ldap.client {
    requires java.naming;
}
~~~

Trong dự án dùng Spring trên **module path**, còn cần xử lý các module tương ứng của Spring theo phiên bản thư viện và cách đóng gói. Không nên tự đoán tên `requires` của các thư viện Spring khi chưa xem module descriptor hoặc automatic module name thực tế của artifact.

Đối với ứng dụng Spring Boot triển khai theo **classpath** thông thường, bạn không nhất thiết có `module-info.java`; điều quan trọng là runtime có các module Java cần thiết và JAR Spring được đóng gói đúng.

### 4.2. Spring LDAP core

Để dùng `LdapContextSource`, `LdapTemplate` và đa số API Spring LDAP core, thêm dependency:

~~~gradle
dependencies {
    implementation("org.springframework.ldap:spring-ldap-core")
}
~~~

Ví dụ này giả định ứng dụng có **dependency management** (chẳng hạn Spring Boot BOM hoặc một version catalog) cung cấp phiên bản tương thích. Nếu không có cơ chế quản lý phiên bản, cần chỉ định phiên bản phù hợp với Spring Framework/JDK đang dùng.

Với Maven trong dự án đã quản lý dependency versions:

~~~xml
<dependency>
    <groupId>org.springframework.ldap</groupId>
    <artifactId>spring-ldap-core</artifactId>
</dependency>
~~~

Một ứng dụng **chỉ** dùng `LdapTemplate` để tìm kiếm/modify LDAP không bắt buộc phải có Spring Data LDAP repository hoặc Spring Security LDAP.

### 4.3. Spring Boot starter

Nếu dùng Spring Boot và muốn cấu hình LDAP thông qua application properties cùng hạ tầng Spring Data LDAP, starter thường dùng là:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Starter mang vào Spring LDAP cùng các thành phần Spring Data LDAP liên quan thông qua dependency graph do Spring Boot quản lý. Khi chỉ cần Spring LDAP core, có thể dùng dependency core trực tiếp và dựa trên các điều kiện auto-configuration phù hợp của phiên bản Boot đang dùng.

**Không thêm đồng thời mọi starter chỉ vì thấy có chữ “LDAP”.** Hãy phân loại:

| Nhu cầu | Dependency chính | Có cần thêm lớp khác? |
| --- | --- | --- |
| JNDI thuần | `java.naming` của JDK | Không cần Spring nếu không dùng API Spring |
| `LdapContextSource`, `LdapTemplate`, `LdapClient` | `spring-ldap-core` | Spring Framework dependencies phù hợp do build tool quản lý |
| Repository + ODM | `spring-data-ldap` hoặc starter data LDAP của Boot | Sử dụng hạ tầng Spring LDAP |
| Xác thực qua Spring Security LDAP | `spring-security-ldap` | Spring Security và cấu hình authentication/authorization |
| Spring Boot auto-configuration | Spring Boot + dependency LDAP trên classpath | Auto-config phụ thuộc điều kiện và phiên bản Boot |

Spring Data LDAP và Spring Security LDAP thực hiện các mục đích khác nhau: repository quản lý truy cập entry/entity; Security dùng LDAP cho xác thực/quyền. Chúng không được dùng để thay thế class JNDI `LdapCtxFactory`.

### 4.4. Không nhầm `javax.naming` với `jakarta.naming`

Dù Spring Framework 6/Spring Boot 3 chuyển nhiều API Jakarta EE (như Servlet và Validation), **JNDI trong Java SE vẫn dùng `javax.naming`**. Các ví dụ chính xác vẫn là:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
~~~

Đừng đổi những import này thành `jakarta.naming.*` chỉ vì ứng dụng dùng Spring Boot phiên bản mới.

## 5. Cấu hình Spring Boot bằng application.yml

Với Spring Boot có LDAP support và dependencies phù hợp, cấu hình có thể là:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=reader,ou=services,dc=example,dc=org
    # password: lấy từ biến môi trường / secret manager
~~~

Có thể cung cấp `spring.ldap.password` qua cơ chế externalized configuration của Spring Boot, chẳng hạn environment variable **`SPRING_LDAP_PASSWORD`**, thay vì ghi mật khẩu rõ trong file.

Trong điều kiện auto-configuration phù hợp, Spring Boot có thể tạo bean `LdapContextSource`/`ContextSource` và `LdapTemplate` để ứng dụng inject:

~~~java
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryOuService {
    private final LdapTemplate ldapTemplate;

    public DirectoryOuService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readPeopleOuName() {
        return ldapTemplate.lookup(
            "ou=people",
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("ou").get()
        );
    }
}
~~~

**Giới hạn của ví dụ:** `lookup(...)` đọc entry đã biết DN và ánh xạ thuộc tính `ou`; ví dụ giả định entry tồn tại và tài khoản bind được đọc `ou`. Ứng dụng thực phải xử lý thuộc tính thiếu, `NameNotFoundException`/ngoại lệ của Spring LDAP và quyền truy cập. Service trên minh họa inject bean và đọc dữ liệu, không phải health check toàn diện.

Đối với một thao tác đọc thuộc tính cụ thể, viết rõ:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;

public List<String> findNamesByUid(
        LdapTemplate ldapTemplate, String uid) {

    String filter = new EqualsFilter("uid", uid).encode();

    return ldapTemplate.search(
        "ou=people",
        filter,
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("cn").get()
    );
}
~~~

Ví dụ giả định entry trả về có `cn`, filter được escape bằng `EqualsFilter`, quyền bind đủ để tìm kiếm, và relative base đúng. Khi code production cần xử lý attribute thiếu, giới hạn tìm kiếm và trường hợp nhiều entry khớp.

### 5.1. Khi nào Boot không tự cấu hình được?

Auto-configuration là **có điều kiện**, không phải lời hứa “có YAML là đủ”. Nếu bạn chỉ khai báo `spring.ldap.*` nhưng **không có thư viện LDAP cần thiết trên classpath**, Boot không thể tạo bean sử dụng class mà ứng dụng chưa có.

Tùy phiên bản và cấu hình, việc đã tự tạo `ContextSource` hoặc `LdapTemplate` bean cũng có thể khiến auto-configuration tương ứng **back off** để tránh tạo bean trùng. Khi xảy ra lỗi thiếu bean, hãy kiểm tra dependency, điều kiện auto-config và những bean đã tự khai báo.

## 6. Cấu hình thủ công trong Spring Framework

Nếu không dùng Spring Boot auto-configuration, có thể khai báo bean `LdapContextSource`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryLdapConfiguration {

    @Bean
    LdapContextSource contextSource() {
        LdapContextSource source = new LdapContextSource();

        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn(
            "uid=reader,ou=services,dc=example,dc=org"
        );

        // Ví dụ dùng biến môi trường; production nên dùng secret manager.
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));

        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

Khi Spring quản lý lifecycle, bean `LdapContextSource` có thể được khởi tạo/kiểm tra cấu hình theo các interface khởi tạo của nó. Nếu tạo `LdapContextSource` **ngoài** Spring container, cần tuân thủ hợp đồng khởi tạo của phiên bản thư viện (ví dụ `afterPropertiesSet()`) trước khi gọi context.

Không nên vừa khai báo cấu hình thủ công này, vừa phụ thuộc mặc định vào các bean Boot auto-config mà không xác định rõ nguồn cấu hình. Bạn cần biết bean nào đang được inject và credentials/base URL nào đang có hiệu lực.

### 6.1. Có cần tự set context factory không?

Với provider JNDI mặc định của JDK và `LdapContextSource`, thường **không cần** cấu hình lại context factory. Hãy để Spring LDAP sử dụng cách khởi tạo mặc định đã thiết kế cho LDAP.

Chỉ tùy biến lựa chọn initial context factory khi đã có yêu cầu kỹ thuật rõ ràng: provider LDAP đặc biệt, Java runtime tùy biến hoặc môi trường JNDI do ứng dụng quản lý. Nếu phải làm vậy, cần xác minh setter/thuộc tính môi trường được hỗ trợ bởi **phiên bản Spring LDAP thực tế**, lớp factory có trên classpath/module path và hành vi của provider không bị thay đổi ngoài ý muốn.

### 6.2. LdapContextSource và LdapTemplate không tự làm TLS an toàn

Sử dụng URL:

~~~text
ldaps://ldap.example.org:636
~~~

không miễn trách nhiệm xác minh certificate chain, hostname và truststore. Đối với StartTLS, yêu cầu nâng cấp kết nối, lifecycle và khả năng pooling có những đặc thù riêng; không thể chỉ đổi URL và tự động coi mọi kết nối đã được bảo vệ đúng cách.

Không dùng mẹo “trust all certificates” để giải quyết sự cố `SSLHandshakeException` trong production. Việc xác thực TLS phải dựa trên truststore/chứng chỉ hợp lệ và chính sách bảo mật tổ chức.

## 7. Classpath, module path và runtime image

### 7.1. Classpath là nơi tìm thư viện ứng dụng

Trong ứng dụng Java truyền thống, JVM tìm class của ứng dụng và các dependencies trong **classpath**. Ví dụ `LdapContextSource` đến từ artifact `spring-ldap-core`; nếu thiếu artifact hoặc đóng gói lỗi, JVM sẽ không load được class này.

Thông điệp điển hình:

~~~text
java.lang.NoClassDefFoundError:
  org/springframework/ldap/core/support/LdapContextSource
~~~

Khả năng cao là dependency `spring-ldap-core` bị thiếu, không được đóng gói hoặc có xung đột phiên bản/classloader. Cần kiểm tra dependency tree và artifact triển khai thực tế.

### 7.2. `java.naming` đến từ JDK, không phải từ Maven Central

Trong Java 9+ khi dùng **module path** hoặc **custom runtime image** (ví dụ tạo bằng `jlink`), module `java.naming` có thể không nằm trong tập module được đóng gói. Khi đó ứng dụng JNDI có thể gặp lỗi tải class chuẩn `javax.naming.*` hoặc provider.

Một số lệnh chẩn đoán hữu ích:

~~~bash
java --version
java --list-modules
java --describe-module java.naming
~~~

Trên runtime hỗ trợ các lệnh này, bạn cần thấy module `java.naming` tồn tại. Với custom runtime image, hãy xem cấu hình `jlink` hoặc launcher đã chọn đủ module cần thiết chưa. Thư viện Spring LDAP trong classpath **không thể tự bổ sung** module JDK đã bị loại bỏ khỏi runtime image.

Ví dụ mô tả ý tưởng khi thiết kế một runtime image:

~~~text
Ứng dụng cần JNDI/LDAP
    -> java.naming phải có trong tập runtime modules
    -> thư viện spring-ldap-core và các dependency đi cùng được đóng gói
    -> URL / TLS / bind DN / password mới có thể được kiểm tra ở thời gian chạy
~~~

Không nên tự sao chép các class `com.sun.jndi.ldap.*` ra một JAR khác để chữa lỗi runtime. Hãy sửa runtime image hoặc dùng một JDK có LDAP JNDI provider phù hợp.

### 7.3. Đóng gói Spring Boot executable JAR

Một executable JAR Spring Boot thông thường đặt thư viện phụ thuộc trong cấu trúc đóng gói mà Spring Boot launcher có thể tải được. Nếu build chạy được trong IDE nhưng bản triển khai lỗi `ClassNotFoundException`, cần kiểm tra:

- Artifact triển khai có phải **executable/fat JAR** đúng loại không?
- `spring-ldap-core` có bị đánh dấu sai scope, chẳng hạn **`compileOnly`** hoặc `provided`, khiến runtime không có dependency không?
- Có xung đột phiên bản Spring LDAP/Spring Framework do tự ép version không?
- Ứng dụng có chạy bằng **JRE/JDK khác** với lúc development không?
- Container image hoặc `jlink` image có loại bỏ `java.naming` không?

Không nên khắc phục những lỗi trên bằng cách viết thêm `Context.INITIAL_CONTEXT_FACTORY` nếu JNDI provider class thực sự vắng mặt.

## 8. Khác biệt giữa lỗi factory, kết nối và xác thực

Bảng chẩn đoán nhanh:

| Lỗi / triệu chứng | Nhóm nguyên nhân có thể | Bước xác minh phù hợp |
| --- | --- | --- |
| `ClassNotFoundException: com.sun.jndi.ldap.LdapCtxFactory` hoặc factory không tải được | Runtime thiếu LDAP provider/`java.naming`, class loader sai, custom JDK | Kiểm tra JDK/runtime image, `java.naming`, provider và cấu hình factory |
| `NoClassDefFoundError: org/springframework/ldap/...` | Thiếu/mismatch `spring-ldap-core` ở runtime | Dependency tree, JAR được đóng gói, phiên bản |
| `ClassNotFoundException: javax.naming.Context` | Runtime không có phần API JNDI cần thiết | Kiểm tra `java.naming` và module resolution |
| `CommunicationException` / không kết nối được | Host/port, DNS, firewall, server down hoặc timeout | Kiểm tra địa chỉ, mạng, port và thời gian |
| `SSLHandshakeException` | Chứng chỉ, hostname, truststore hoặc TLS negotiation | Kiểm tra TLS theo chính sách bảo mật, không tắt xác minh chứng chỉ |
| `AuthenticationException` hoặc lỗi bind | Sai bind DN/password, account policy, cơ chế xác thực | Kiểm tra credentials qua kênh an toàn và cấu hình server |
| `NameNotFoundException` | Base DN hoặc relative DN sai, entry không tồn tại hoặc chính sách hiển thị | Kiểm tra DN, cấu trúc cây và quyền |
| `PartialResultException` | Có thể liên quan đến referrals hoặc đặc tính provider | Xác định hướng referral, server trả về gì và cấu hình provider |
| Không có `LdapTemplate` bean | Điều kiện auto-config không thỏa hoặc bean chưa được khai báo | Kiểm tra dependencies, bean configuration và auto-config |
| Search trả rỗng dù bind thành công | Sai base/scope/filter/schema/ACL | Kiểm tra từng thành phần của search request |

**Không phải mọi lỗi gọi LDAP đều là “thiếu context factory”.** Nếu runtime đã tạo được JNDI context nhưng bind thất bại, việc bổ sung JAR provider hoặc đổi factory thường không giúp gì. Phải xác định đúng lớp gây lỗi.

### 8.1. Đọc nguyên nhân gốc của exception

Spring LDAP chuyển nhiều exception JNDI thành exception thuộc hệ thống Spring LDAP. Khi chẩn đoán, nên xem **cause chain** để biết lỗi đến từ:

1. Tải class/provider (classpath/module/runtime).
2. Tạo kết nối TCP hoặc TLS.
3. Bind bằng tài khoản dịch vụ.
4. Tìm kiếm theo DN/filter/scope.
5. Map thuộc tính thành object.
6. Đóng/thu hồi context hoặc giới hạn tìm kiếm.

Trong log, không ghi mật khẩu và hạn chế hiển thị DN/thuộc tính nhạy cảm. Kết quả lỗi chi tiết có thể được ghi ở kênh vận hành có kiểm soát; thông báo trả cho người dùng cuối nên tuân thủ chính sách bảo mật và trải nghiệm của ứng dụng.

## 9. Tác động đến pooling và xác thực người dùng

### 9.1. Tài khoản dịch vụ và tài khoản người dùng khác nhau

`LdapContextSource` thường được cấu hình với **service bind DN** để đọc directory. Trong một luồng Spring Security LDAP bind authentication, việc kiểm tra mật khẩu có thể cần một context sử dụng **DN và mật khẩu của người đăng nhập**.

Không vì dùng chung `ContextSource` mà giả định mọi context sẽ có cùng danh tính:

~~~text
Tìm hồ sơ:
  ContextSource -> service bind -> đọc uid/cn/mail

Đăng nhập:
  Spring Security LDAP -> tìm DN -> bind bằng credential của người dùng
  -> Authentication / authorities theo cấu hình
~~~

Spring LDAP core cung cấp khả năng thao tác với context, nhưng Spring Security LDAP đảm nhiệm tích hợp authentication và authorization cho ứng dụng. Không lấy sự tồn tại của entry làm bằng chứng người dùng đã đăng nhập.

### 9.2. Pooling không thay đổi classpath

Connection pooling liên quan đến tái sử dụng context/kết nối để giảm chi phí mở kết nối. Nó không giải quyết lỗi thiếu `java.naming` hoặc thiếu `spring-ldap-core`.

Khi pooling, cần phân biệt context của tài khoản dịch vụ với những lần bind theo danh tính người dùng, cũng như tác động của StartTLS, timeout và server-side connection limits. Chỉ bật pooling khi biết rõ cơ chế và chính sách bảo mật của provider/thư viện đang dùng.

### 9.3. Giới hạn quyền của service bind

Tài khoản `uid=reader,...` trong ví dụ nên chỉ có quyền cần thiết để đọc dữ liệu theo nghiệp vụ. Nếu cần thao tác modify entry hoặc quản lý group, hãy sử dụng chính sách ACL và quyền ghi phù hợp, tránh dùng một tài khoản toàn quyền cho mọi request.

Khi bị từ chối thao tác, cần kiểm tra **ACL và DN của context đang thực hiện**; đổi context factory không khiến server tự cho phép quyền ghi.

## 10. Bài thực hành: phân biệt lỗi dependency và lỗi LDAP

### 10.1. Môi trường chuẩn bị

Dùng ứng dụng Java/Spring Boot có dependency `spring-ldap-core` hoặc starter LDAP tương ứng, cùng một LDAP server test qua LDAPS/StartTLS với chứng chỉ hợp lệ. Chuẩn bị base `dc=example,dc=org`, một OU `ou=people` và một tài khoản bind chỉ có quyền đọc.

Đầu tiên kiểm tra runtime:

~~~bash
java --version
java --list-modules
~~~

Với Java 9+ và runtime chuẩn, bạn cần xác minh `java.naming` xuất hiện. Tiếp theo xác minh Gradle/Maven dependency thực sự bao gồm `spring-ldap-core` và ứng dụng đã tải các class cần thiết.

### 10.2. Các trường hợp cần kiểm thử

| Tình huống | Thao tác | Kết luận cần rút ra |
| --- | --- | --- |
| Thiếu `spring-ldap-core` | Loại dependency ở môi trường thử nghiệm | Spring class không được tải; lỗi không phải do LDAP server |
| Thiếu `java.naming` trong runtime tùy biến | Chạy image đã loại bỏ module | JNDI API/provider không sẵn có; sửa runtime image |
| Provider URL sai host | Cấu hình URL không truy cập được | Lỗi kết nối hoặc DNS, không phải lỗi thiếu class |
| Port LDAPS sai | Trỏ `ldaps://` tới endpoint không hỗ trợ TLS tương ứng | TLS/connection failure |
| Bind DN sai | Giữ URL đúng, đổi bind principal | Lỗi xác thực hoặc tra cứu danh tính |
| Password sai | Giữ bind DN đúng, đổi password thử nghiệm | Server từ chối bind |
| Base DN sai | Giữ URL/credentials đúng, đổi base | Search/lookup lỗi hoặc trả rỗng theo cấu hình |
| Base và scope đúng | Tìm một entry test bằng `EqualsFilter` | Xác thực end-to-end cấu hình Spring LDAP |
| Thiếu truststore | Không tin cậy server certificate | TLS handshake failure; khắc phục chain/truststore |
| Pooling cấu hình sai | Dùng nhiều danh tính kết nối | Xác minh không có context sai credentials được tái sử dụng |

### 10.3. Kiểm tra trên một LDAP test server thực

Ví dụ truy vấn với `LdapTemplate`:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.core.AttributesMapper;

long matches = ldapTemplate.search(
    "ou=people",
    new EqualsFilter("uid", "lan").encode(),
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("uid").get()
).size();

System.out.println("Matches: " + matches);
~~~

Đây là một **smoke test chức năng** đơn giản, không phải kiểm thử tải hoặc toàn bộ bảo mật. Một kết quả thành công xác nhận một đường đi từ cấu hình Spring LDAP qua provider JNDI, TLS, bind, search và mapping cho dữ liệu thử nghiệm. Nó không chứng minh server không có lỗi khác, schema toàn diện đúng hoặc ACL ghi đã được thiết kế tốt.

### 10.4. Khắc phục khi ứng dụng chạy trong container

Nếu ứng dụng chạy trong container hoặc cloud runtime:

- Kiểm tra image sử dụng JDK/JRE nào, có `java.naming` hay không.
- Kiểm tra truststore có chứa CA cấp chứng chỉ cho LDAP server và hostname khớp certificate.
- Kiểm tra DNS, firewall, egress policy, port 389/636 hoặc port do hệ thống quy định.
- Kiểm tra secrets có thật sự được inject khi process khởi động; không in credentials ra console.
- Kiểm tra deployment artifact chứa dependencies cần thiết và không khác với bản đã chạy qua integration test.
- Khi dùng nhiều LDAP URL, xác định thứ tự thử kết nối, chính sách failover và behavior của provider đang sử dụng.

Không sử dụng kết quả chạy thành công trên máy phát triển như bằng chứng container production sẽ có cùng JDK modules và truststore.

## 11. Những hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “Có `spring-ldap-core` thì tự có `LdapCtxFactory`” | `LdapCtxFactory` thường do JDK LDAP provider trong `java.naming` cung cấp |
| “Có JDK nên không cần `spring-ldap-core`” | JNDI API có sẵn; `LdapContextSource`/`LdapTemplate` vẫn cần Spring LDAP |
| “Muốn dùng LDAP phải tải riêng `com.sun.jndi.ldap` từ Maven” | Không phải nhu cầu bình thường trên JDK hỗ trợ LDAP provider |
| “Không khai báo factory trong YAML nên không có provider” | Spring LDAP thường dùng default provider; kiểm tra cấu hình/context thực tế |
| “JNDI thuần luôn tự chọn LDAP khi không có factory” | Không nên giả định vậy; đặt factory tường minh hoặc kiểm tra môi trường đã cung cấp |
| “Lỗi login nghĩa là thiếu JAR LDAP” | Có thể đã kết nối được nhưng bind credential bị từ chối |
| “Dùng Spring Boot 3 phải đổi `javax.naming` thành `jakarta.naming`” | Java SE JNDI vẫn ở `javax.naming` |
| “Count limit, pooling và LDAPS là nhiệm vụ của context factory” | Chúng thuộc các lớp vận hành/LDAP khác nhau; factory chỉ là một phần của khởi tạo context |
| “ObjectFactory JNDI cũng chính là initial context factory” | Đây là hai SPI khác nhau |
| “Dùng `ldap://` cũng an toàn vì mật khẩu nằm trong secret manager” | Secret manager bảo vệ khi lưu/cấp secret, không tự mã hóa truyền qua mạng |

## 12. Checklist trước khi triển khai

- [ ] Ứng dụng chạy với JDK/runtime có `java.naming` và LDAP provider phù hợp.
- [ ] Dependencies có `spring-ldap-core` nếu dùng `LdapContextSource`/`LdapTemplate`.
- [ ] Chỉ thêm Spring Data LDAP repository hoặc Spring Security LDAP khi bài toán cần.
- [ ] Không trộn lẫn việc Boot auto-config và bean cấu hình tay mà không kiểm soát.
- [ ] URL, port và scheme `ldap://`/`ldaps://` phù hợp với server.
- [ ] Base DN và service bind DN được xác định chính xác, phân biệt full DN và relative DN.
- [ ] Credentials được cấp từ nguồn bảo mật, không đưa vào Git/log.
- [ ] LDAPS/StartTLS sử dụng chứng chỉ hợp lệ và truststore chính xác.
- [ ] Kiểm tra lỗi tải class riêng với lỗi mạng/TLS/bind/schema/search.
- [ ] Có integration test sử dụng LDAP test server với filter, DN và ACL thực tế.
- [ ] Với container/jlink runtime, kiểm tra modules và JAR thực tế trong artifact.
- [ ] Pooling và kết nối theo danh tính người dùng được cấu hình/kiểm thử phù hợp.
- [ ] Theo dõi timeout và kết quả tìm kiếm, không che mọi exception thành “không có dữ liệu”.

## 13. Ghi nhớ

**“Default context factory” là phần JNDI LDAP provider mà Spring LDAP có thể sử dụng ở tầng thấp; “classpath cần thiết” gồm phần Java SE `java.naming` trong runtime và các thư viện Spring LDAP đúng phiên bản trong ứng dụng.** Trong một JDK hỗ trợ LDAP provider, bạn thường không cần tìm thêm JAR cho `com.sun.jndi.ldap.LdapCtxFactory`; bạn vẫn phải có dependency `spring-ldap-core` để gọi `LdapContextSource` hoặc `LdapTemplate`.

Khi có lỗi, hãy xác định nó ở **giai đoạn tải class, khởi tạo context, mở kết nối, TLS, bind, search hay mapping**. Cấu hình factory không thay thế cấu hình base DN, quyền, chứng chỉ, timeout hoặc matching rule của LDAP server.

### Tài liệu tham khảo

- [Java SE — InitialContextFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/spi/InitialContextFactory.html)
- [Java SE — Context (environment properties)](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html)
- [Java SE — InitialDirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/InitialDirContext.html)
- [Java SE — java.naming module](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/module-summary.html)
- [Oracle JNDI LDAP Provider Guide](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html)
- [Spring LDAP Reference — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring Boot Reference — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap)
