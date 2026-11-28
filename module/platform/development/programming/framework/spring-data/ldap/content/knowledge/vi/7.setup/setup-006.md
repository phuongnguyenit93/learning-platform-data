# Cơ chế tự cấu hình ContextSource, LdapTemplate và Repository

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập LDAP directory qua **repository** hoặc **LdapTemplate**. Dữ liệu LDAP được tổ chức thành các entry có **distinguished name (DN)**, **objectClass**, schema và các thuộc tính có thể ánh xạ sang đối tượng Java. Khi dùng Spring Boot, nhiều dự án chỉ cần thêm starter, đặt thông tin kết nối trong **application.yml**, rồi inject repository mà không tự tạo từng đối tượng hạ tầng.

Điều này không có nghĩa Spring Boot “đoán” tất cả cấu trúc directory. Framework chỉ **tạo và nối các bean theo điều kiện cấu hình**; directory server vẫn quyết định DN có tồn tại không, objectClass nào hợp lệ, filter có khớp không, tài khoản bind có quyền gì và kết nối TLS có an toàn hay không.

Bài thuộc chương **Khởi tạo**, giải thích **cơ chế tự cấu hình ContextSource, LdapTemplate và Repository**. Sau bài, bạn có thể:

- Vẽ được chuỗi **LDAP properties → ContextSource → LdapTemplate → repository factory/proxy → LDAP server**.
- Hiểu **auto-configuration** của Spring Boot phụ thuộc classpath, cấu hình, bean hiện có và phạm vi package quét như thế nào.
- Phân biệt việc **tạo ContextSource**, **tạo LdapTemplate**, **quét repository** và **ánh xạ LDAP entry**.
- Dùng **spring-boot-starter-data-ldap** và **spring.ldap.*** để cấu hình kết nối an toàn.
- Dùng **@EnableLdapRepositories** và **ldapTemplateRef** khi không muốn phụ thuộc vào package scan mặc định.
- Biết khi nào cần khai báo bean thủ công, đặc biệt khi có **nhiều directory/ContextSource**.
- Chẩn đoán lỗi không có repository bean, bean trùng, DN sai, mật khẩu bind sai, schema lỗi và chứng chỉ TLS không hợp lệ.
- Viết kiểm thử tách riêng **khởi tạo Spring context** khỏi **truy cập LDAP thật**.

## 1. Ba thành phần chính và trách nhiệm riêng

Một ứng dụng đọc người dùng có thể được biểu diễn:

~~~mermaid
flowchart TD
    A["application.yml / cấu hình tin cậy"] --> B["Spring Boot LDAP auto-configuration"]
    B --> C["ContextSource"]
    C --> D["LdapTemplate"]
    B --> E["Repository auto-configuration"]
    E --> F["Repository factory / proxy"]
    D --> F
    G["Service của ứng dụng"] --> F
    G --> D
    F --> D
    D --> C
    C --> H["JNDI / LDAP connection"]
    H --> I["LDAP server: DN, schema, ACL"]
~~~

| Thành phần | Nó làm gì? | Nó **không** làm gì? |
| --- | --- | --- |
| **ContextSource** | Cung cấp LDAP context/kết nối theo URL, base DN, bind DN, mật khẩu, cấu hình môi trường và TLS | Không phải DAO, không tự ánh xạ entry thành domain object |
| **LdapTemplate** | Quản lý vòng đời LDAP context và cung cấp lookup, search, bind, modify, unbind | Không tự biết nghiệp vụ nào được phép sửa, cũng không định nghĩa schema của LDAP server |
| **Spring Data LDAP repository** | Sinh bean proxy từ interface, ánh xạ entry qua ODM và thực hiện CRUD/query bằng hạ tầng LDAP | Không tạo schema, không tự chuyển sang server khác theo DN, không bảo đảm directory đang kết nối được |

**ContextSource** trong Spring LDAP là một abstraction cung cấp LDAP context; triển khai phổ biến là **LdapContextSource**. **LdapTemplate** dùng ContextSource cho các thao tác LDAP. **LdapRepository** là interface thuộc Spring Data LDAP, được Spring Data tạo proxy và thường thực thi trên cơ sở LdapTemplate cùng metadata **@Entry/@Id/@Attribute**.

Nhờ tách tầng, một ứng dụng có thể dùng đồng thời:

- Repository để tìm **PersonEntry** theo uid, lưu entry hoặc lấy theo DN.
- LdapTemplate để tìm với **SearchScope** cụ thể, lấy một tập thuộc tính nhỏ hoặc sửa chính xác một giá trị **member** của nhóm.
- ContextSource để cấu hình URL, thông tin xác thực, TLS và chính sách kết nối cho cả hai.

**Không nhầm LDAP ContextSource với ApplicationContext của Spring.** ApplicationContext là container chứa Spring beans; ContextSource là một bean cung cấp context kết nối LDAP.

## 2. Spring Boot auto-configuration thực chất hoạt động ra sao?

**Auto-configuration** là việc Spring Boot thêm cấu hình có điều kiện khi thấy các thư viện và môi trường phù hợp. Nó không đồng nghĩa với một chương trình cứng luôn tạo mọi bean.

Khi ứng dụng dùng Spring Boot và các thư viện LDAP cần thiết:

1. Spring Boot đọc cấu hình và phát hiện các thư viện có trên **classpath**.
2. Nếu điều kiện LDAP auto-configuration phù hợp, Boot tạo hoặc dùng **ContextSource** đã có.
3. Nếu điều kiện tương ứng phù hợp, Boot tạo hoặc dùng **LdapTemplate/LdapOperations** đã có.
4. Nếu module Spring Data LDAP khả dụng và repository support được bật, hạ tầng Spring Data tìm **repository interfaces** trong các base package đã đăng ký.
5. Với mỗi interface hợp lệ, Spring Data đăng ký factory bean và tạo **repository proxy** dựa trên LdapTemplate, domain metadata và các phương thức đã khai báo.
6. Khi service gọi phương thức, proxy/template mới gửi thao tác LDAP thật theo cấu hình (trừ các thành phần nào đó chủ động kiểm tra kết nối sớm).

**Cần nhớ tính có điều kiện:** ví dụ tên lớp auto-configuration, điều kiện **@ConditionalOnClass**, **@ConditionalOnMissingBean**, cơ chế bật repository và package đăng ký có thể khác giữa các phiên bản Spring Boot. Phân tích cấu hình thực tế bằng **condition evaluation report** và tài liệu đúng phiên bản đang triển khai; không mặc định một cấu hình tự động luôn thắng mọi bean người dùng khai báo.

### 2.1. Điều kiện quan trọng

| Điều kiện | Nếu đáp ứng | Nếu không đáp ứng |
| --- | --- | --- |
| Có **Spring LDAP** trên classpath | Boot có thể cấu hình ContextSource/Template | Không thể tự cấu hình thành phần LDAP nếu thiếu thư viện |
| Có **Spring Data LDAP** | Có thể kích hoạt repository infrastructure | Chỉ dùng LdapTemplate/JNDI, không có repository proxy của module này |
| Có thông tin **spring.ldap.*** thích hợp | ContextSource có cơ sở để tạo kết nối | Có thể thiếu thông số URL/bind; lỗi cấu hình hoặc runtime |
| Chưa có bean thủ công phù hợp với điều kiện back-off | Boot có thể tạo bean mặc định | Boot thường **back off** và để bean được khai báo xử lý |
| Repository scanning được bật và chọn đúng package | Interface repository được đăng ký | Service có thể gặp lỗi không tìm thấy repository bean |
| Domain class có ODM metadata hợp lệ | Có thể tạo mapping cho repository | Có thể lỗi metadata/query khi bootstrap hoặc lúc thực thi |

Đây là **sơ đồ điều kiện khái niệm**, không thay cho việc kiểm tra annotation/source của một Spring Boot version cụ thể. Đặc biệt, một ContextSource do bạn tự định nghĩa có thể ảnh hưởng tới việc Boot quyết định tạo ContextSource mặc định, trong khi LdapTemplate cũng có thể được cấu hình thủ công.

### 2.2. Hai loại “quét” khác nhau

**Quét repository** tìm các **Java interface trên classpath** để tạo bean. Nó khác hoàn toàn với **LDAP search** quét các entry trong directory:

~~~text
Bootstrap:
  org.example.directory.repository.PersonRepository
      -> repository candidate -> factory bean -> proxy bean

Runtime:
  repository.findByUid("an")
      -> LDAP Search trong ou=people,dc=example,dc=org
      -> ánh xạ attributes -> PersonEntry
~~~

**@ComponentScan** tìm các lớp component như **@Service**, còn cơ chế Spring Data repository chuyên xử lý **interface**. **@Entry** mô tả LDAP object-directory mapping, không tự tạo repository bean và không thay thế **@EnableLdapRepositories** khi phạm vi quét cần được cấu hình rõ ràng.

## 3. Khởi tạo ứng dụng tối thiểu

Một ví dụ project Java 17+ dùng Spring Boot có cấu trúc:

~~~text
org.example.directory
├── DirectoryApplication.java
├── entry
│   └── PersonEntry.java
├── repository
│   └── PersonRepository.java
└── service
    └── PersonService.java
~~~

Khi class **@SpringBootApplication** ở **org.example.directory**, các package **entry**, **repository** và **service** là package con của nó. Cấu trúc này phù hợp với cơ chế xác định base packages mặc định của Spring Boot.

### 3.1. Dependency

Gradle (Groovy DSL):

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Starter cung cấp hạ tầng liên quan đến Spring LDAP/Spring Data LDAP theo dependency management của phiên bản Spring Boot được chọn. Thông thường **không cần tự gắn các phiên bản spring-ldap-core và spring-data-ldap khác nhau** khi đang dùng một Spring Boot BOM đã kiểm thử tương thích.

Nếu dự án chỉ cần **LdapTemplate** mà không dùng repository, có thể sử dụng dependency Spring LDAP thích hợp thay cho toàn bộ starter data LDAP, tùy cấu trúc build và phiên bản Boot. Nhưng bài này dùng starter để minh họa **đủ cả ba thành phần**.

### 3.2. Cấu hình kết nối

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-directory,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

| Property | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| **spring.ldap.urls** | LDAP endpoint được phép kết nối | **ldaps://** dùng TLS ngay khi kết nối; hostname phải khớp certificate SAN |
| **spring.ldap.base** | Base DN mặc định cho những thao tác tương đối | Không phải URL server hay bind DN |
| **spring.ldap.username** | DN được ứng dụng dùng để bind/xác thực | Cần đầy đủ và có quyền tối thiểu |
| **spring.ldap.password** | Bí mật của bind identity | Lấy từ secret manager/biến môi trường; không commit |

Trong ví dụ:

~~~text
Server URL:     ldaps://ldap.example.org:636
Base DN:        dc=example,dc=org
Bind DN:        uid=svc-directory,ou=service-accounts,dc=example,dc=org
Entry đầy đủ:   uid=an,ou=people,dc=example,dc=org
DN tương đối:   uid=an,ou=people
~~~

**LDAPS phải xác minh certificate chain và hostname**, không cấu hình trust-all để vượt qua lỗi TLS. Nếu LDAP server dùng CA riêng, JVM cần tin CA phù hợp qua truststore được quản trị. **StartTLS trên ldap:// không tự bật chỉ nhờ đổi URL**: phải có cấu hình authentication strategy/ContextSource thật sự nâng cấp kết nối và từ chối simple bind nếu TLS thất bại.

### 3.3. Class khởi động

~~~java
package org.example.directory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DirectoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectoryApplication.class, args);
    }
}
~~~

Không cần tự khai báo **LdapContextSource**, **LdapTemplate** và **@EnableLdapRepositories** trong trường hợp Spring Boot auto-configuration nhận diện được toàn bộ dependency, có thông tin kết nối hợp lệ và các repository nằm đúng vùng scan.

**Mặc định cần được kiểm tra, không được giả định:** nếu ứng dụng có custom ContextSource/LdapTemplate hoặc chủ động thêm **@EnableLdapRepositories**, việc tạo bean và vùng quét có thể thay đổi. Hãy chỉ dùng **một chiến lược rõ ràng** cho cùng một nhóm repository.

## 4. Từ ContextSource đến LdapTemplate

### 4.1. ContextSource quản lý thông tin kết nối

**org.springframework.ldap.core.ContextSource** là giao diện cung cấp các **DirContext** dùng cho LDAP operations. Triển khai phổ biến:

~~~java
org.springframework.ldap.core.support.LdapContextSource
~~~

Trong trường hợp auto-configuration, bạn thường **inject bean**, không cần new thủ công:

~~~java
package org.example.directory.service;

import org.springframework.ldap.core.ContextSource;
import org.springframework.stereotype.Component;

@Component
public class DirectoryConnectionInspector {
    private final ContextSource contextSource;

    public DirectoryConnectionInspector(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public boolean isContextSourceConfigured() {
        return contextSource != null;
    }
}
~~~

Phương thức trên chỉ xác minh **có bean được inject**; nó **không kiểm tra server đang online** hoặc credentials có đúng. Dùng nó để hiểu DI, **không sử dụng như health check thực tế**.

Trong Spring LDAP, ContextSource cung cấp context cho thao tác với **username/password** được cấu hình hoặc cho một nhu cầu xác thực cụ thể. Spring LDAP quản lý cách lấy và đóng context; ứng dụng thông thường nên gọi **LdapTemplate** thay vì tự mở, đóng DirContext khắp service.

### 4.2. LdapTemplate loại bỏ mã JNDI lặp lại

Nếu dùng JNDI trực tiếp, mã nguồn phải tự lấy LDAP context, đóng search results/NamingEnumeration và xử lý ngoại lệ. **LdapTemplate** tập trung các bước này trong một API nhất quán:

~~~java
package org.example.directory.service;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class DirectorySearchService {
    private final LdapTemplate ldapTemplate;

    public DirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNamesByUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        return ldapTemplate.search(
            query().base("ou=people")
                   .attributes("cn")
                   .where("objectClass").is("inetOrgPerson")
                   .and("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
    }
}
~~~

**LdapQueryBuilder** mã hóa giá trị filter, giúp tránh nối chuỗi raw input thành LDAP filter. **attributes("cn")** giới hạn dữ liệu cần đọc; **base("ou=people")** là DN tương đối so với ContextSource base. Filter dùng objectClass phù hợp với schema entry, nhưng **server vẫn chịu trách nhiệm quyền đọc, matching rule và tính hợp lệ của dữ liệu**.

Với Spring Boot thông thường, **bean LdapTemplate được inject** từ cấu hình tự động mà không cần tự gọi **new LdapTemplate(...)**. Khi bạn muốn tạo LdapTemplate thủ công, nó phải tham chiếu đúng **ContextSource**.

### 4.3. LDAP operation chỉ thành công khi directory cho phép

LdapTemplate có các thao tác:

| Nhóm thao tác | Ví dụ | Ràng buộc thực tế |
| --- | --- | --- |
| **Đọc một entry** | **lookup(dn, mapper)** | DN thực sự tồn tại, tài khoản có quyền đọc |
| **Tìm kiếm** | **search(query, mapper)** | Base, scope, filter, index và ACL ảnh hưởng kết quả |
| **Tạo** | **bind(dn, null, attrs)** | Parent tồn tại, schema hợp lệ, DN chưa trùng |
| **Sửa** | **modifyAttributes(dn, items)** | Quyền ghi thuộc tính, ràng buộc schema, DN đúng |
| **Xóa** | **unbind(dn)** | Quyền xóa, chính sách server, child entries |
| **Đổi tên** | **rename(oldDn, newDn)** | Điều kiện naming, quyền đổi RDN/di chuyển |

Không phải vì có bean **LdapTemplate** là mọi phương thức CRUD có thể thực hiện. LDAP server luôn kiểm tra schema/objectClass, DN, ACL và chính sách sản phẩm.

## 5. Tự cấu hình repository: interface được biến thành bean ra sao?

Một Java interface không thể khởi tạo bằng **new**; tuy nhiên Spring Data có **repository infrastructure** để đăng ký factory bean rồi sinh proxy từ metadata của interface.

### 5.1. Domain class theo LDAP ODM

~~~java
package org.example.directory.entry;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
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

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
~~~

Ở đây **@Entry** cho biết những objectClass LDAP được dùng, **@Id** chứa **DN kiểu javax.naming.Name**, còn **@Attribute** ánh xạ property Java sang tên LDAP attribute. **@Entry không tự tạo entry LDAP**, không đưa schema lên server và không đăng ký một repository bean.

Ví dụ LDIF phù hợp:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
~~~

**cn** và **sn** là các thuộc tính bắt buộc qua objectClass **person**. Nếu mapping sai hoặc thiếu thuộc tính khi tạo, LDAP server có thể trả lỗi schema ngay cả khi Spring context khởi tạo thành công.

### 5.2. Repository interface

~~~java
package org.example.directory.repository;

import java.util.List;
import org.example.directory.entry.PersonEntry;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
    List<PersonEntry> findByCommonName(String commonName);
}
~~~

Khác với **JpaRepository<T, ID>**, **LdapRepository<T>** chỉ nhận kiểu domain class; danh tính LDAP được thể hiện bằng DN kiểu **Name**. Không khai báo nhầm **LdapRepository<PersonEntry, Long>**.

**findByUid** và **findByCommonName** là derived query methods. Spring Data phân tích tên property Java, dùng ODM metadata để dịch **commonName** sang LDAP attribute **cn**, rồi tạo search phù hợp. Hãy trả **List** khi dữ liệu có thể không duy nhất trong phạm vi tìm kiếm. **uid** không tự có ràng buộc duy nhất trên toàn directory nếu server/chính sách không đặt ra.

### 5.3. Proxy được tạo từ đâu?

Ở mức khái niệm:

~~~mermaid
flowchart LR
    A["Quét PersonRepository interface"] --> B["Đăng ký repository bean definition"]
    B --> C["LdapRepositoryFactoryBean"]
    C --> D["LdapRepositoryFactory"]
    D --> E["Repository proxy"]
    F["LdapTemplate + ODM metadata"] --> D
    E --> G["findByUid / save / findById"]
    G --> H["LdapTemplate -> ContextSource -> LDAP"]
~~~

Những lớp hạ tầng như **LdapRepositoryFactoryBean**, **LdapRepositoryFactory** và triển khai CRUD cơ sở **SimpleLdapRepository** xử lý phần mà bạn không viết tay. Khi service inject **PersonRepository**, Spring trả về một proxy cung cấp các method của interface.

**Proxy không nằm trong LDAP server**. Đây là bean Java trong Spring container; nó gọi LDAP qua LdapTemplate khi có yêu cầu. Cơ chế query derivation và ODM không bảo đảm một query có index, không thay thế validation của LDAP server và không tự gán quyền đọc/ghi cho tài khoản bind.

## 6. Những package nào được quét tự động?

Spring Boot thường dựa vào package của class **@SpringBootApplication** và các package được cấu hình như **auto-configuration packages**. Ví dụ:

~~~text
org.example.directory.DirectoryApplication       <- package gốc
org.example.directory.repository.PersonRepository <- được quét
org.example.directory.entry.PersonEntry           <- model
org.example.directory.service.PersonService       <- component
~~~

Nếu thay bằng:

~~~text
org.example.app.DirectoryApplication
org.example.shared.ldap.PersonRepository
~~~

thì **PersonRepository không nằm dưới package gốc org.example.app**. Việc ứng dụng khởi động bình thường không chứng minh interface này sẽ được phát hiện; service inject repository có thể thất bại do không tồn tại bean.

### 6.1. Component scan và repository scan là hai cơ chế

| Cơ chế | Thường phát hiện | Điều cần có |
| --- | --- | --- |
| **@ComponentScan** (bao hàm trong @SpringBootApplication) | **@Service**, **@Component**, **@Configuration** và stereotype tương ứng | Class có thể tạo Spring bean |
| **Spring Data repository scanning** | Interface kế thừa **LdapRepository** hoặc repository được module nhận diện | Hạ tầng Spring Data LDAP, package scan đúng |
| **ODM mapping** | Class **@Entry**, thuộc tính **@Id/@Attribute** | Metadata ánh xạ và domain class hợp lệ |

**@Repository đặt trên một interface không tự thay thế repository scanning.** Ngược lại, đặt **@Entry** trên domain class không làm Spring tự tạo một PersonRepository nếu chưa khai báo interface.

### 6.2. Nhiều Spring Data modules

Nếu cùng ứng dụng có JPA, MongoDB và LDAP, Spring Data có thể phải xác định interface nào thuộc datastore nào. Kế thừa **LdapRepository<PersonEntry>** và dùng **@Entry** là tín hiệu rõ ràng cho LDAP. Không mặc định một interface **CrudRepository** generic sẽ luôn được xử lý bởi đúng module khi có nhiều Spring Data implementations.

Các repository JPA, MongoDB và LDAP nên có **package riêng** nếu hệ thống phức tạp. Việc phân vùng giúp giảm các trường hợp scan trùng hoặc Spring Data không biết module nào chịu trách nhiệm.

## 7. Khi nào cần @EnableLdapRepositories?

Ở ứng dụng Spring Boot đơn giản, auto-configuration thường đủ. **@EnableLdapRepositories** hữu ích khi:

- Repository nằm ngoài package được auto scan.
- Bạn muốn **chỉ rõ basePackages** hoặc **basePackageClasses**.
- Cần gắn repository với **LdapTemplate** có tên riêng.
- Có nhiều directory, nhiều ContextSource hoặc vùng repository khác nhau.
- Không dùng Spring Boot auto-configuration hoặc cần cấu hình hạ tầng rõ ràng.

Ví dụ JavaConfig:

~~~java
package org.example.directory.config;

import org.example.directory.repository.PersonRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration(proxyBeanMethods = false)
@EnableLdapRepositories(
    basePackageClasses = PersonRepository.class,
    ldapTemplateRef = "ldapTemplate"
)
public class LdapRepositoryConfiguration {
}
~~~

**basePackageClasses** dùng package chứa **PersonRepository** làm gốc quét, tránh gõ nhầm string package. **ldapTemplateRef** chọn bean LdapTemplate có tên tương ứng.

Một dạng khác:

~~~java
@EnableLdapRepositories(
    basePackages = "org.example.directory.repository"
)
~~~

**@EnableLdapRepositories không có tham số** dùng package của class khai báo annotation làm cơ sở quét. Nếu class cấu hình nằm trong **org.example.directory.config** mà repository nằm ở **org.example.directory.repository**, hai package là anh em: mặc định có thể không quét repository như bạn kỳ vọng.

**Tránh bật nhiều lần cùng một phạm vi repository**. Không cấu hình auto scan, một @EnableLdapRepositories thủ công và thêm @Enable khác cùng quét một interface nếu không có chủ đích phân vùng; các cấu hình chồng lấn có thể dẫn đến bean definition trùng hoặc factory bị gắn nhầm template.

### 7.1. Có thể tắt auto-configuration repository

Spring Boot cung cấp cơ chế điều khiển repository auto-configuration, ví dụ thuộc tính thường gặp:

~~~yaml
spring:
  data:
    ldap:
      repositories:
        enabled: false
~~~

Thuộc tính này dùng để **tắt repository auto-configuration** của Boot khi được phiên bản tương ứng hỗ trợ; nó **không phải lệnh tắt mọi LdapTemplate hoặc ContextSource**. Đồng thời, nếu bạn chủ động khai báo **@EnableLdapRepositories**, annotation đó vẫn có thể kích hoạt repository scanning độc lập với việc tắt cơ chế tự cấu hình của Boot.

Không nên coi property này là một cách sửa lỗi scan thiếu package. Trước hết phải xác định bạn muốn **không có repository** hay **có repository nhưng cần quét đúng phạm vi**.

## 8. Khi bạn tự khai báo ContextSource hoặc LdapTemplate

Trong Spring Boot, auto-configuration thường có điều kiện **back off** khi đã tồn tại bean cùng vai trò. Cách viết rõ ràng khi cần cấu hình thủ công là cung cấp ContextSource và LdapTemplate chính xác, sau đó chọn nó cho repository.

Ví dụ một directory riêng có base DN và service account:

~~~yaml
app:
  directory:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

~~~java
package org.example.directory.config;

import org.example.directory.repository.PersonRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
@EnableLdapRepositories(
    basePackageClasses = PersonRepository.class,
    ldapTemplateRef = "peopleLdapTemplate"
)
public class PeopleDirectoryConfiguration {

    @Bean("peopleContextSource")
    LdapContextSource peopleContextSource(
            @Value("${app.directory.url}") String url,
            @Value("${app.directory.base}") String base,
            @Value("${app.directory.bind-dn}") String bindDn,
            @Value("${app.directory.password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        // Spring quản lý vòng đời bean; không cần tự gọi
        // afterPropertiesSet() bên trong method @Bean.
        return source;
    }

    @Bean("peopleLdapTemplate")
    LdapTemplate peopleLdapTemplate(
            @Qualifier("peopleContextSource") ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

**Đoạn này là một phương án THAY THẾ** cho ví dụ tự cấu hình mặc định ở phần 3, không phải cấu hình cần thêm chồng lên nguyên trạng project tối thiểu. Nếu dùng nó, phải đánh giá auto-configuration đang tạo bean nào, liệu có bean ContextSource/LdapTemplate mặc định khác không và repository đã được quét đúng một lần chưa.

Ở đây:

- **@Bean("peopleContextSource")** khai báo hạ tầng kết nối LDAP.
- **@Bean("peopleLdapTemplate")** chỉ rõ template sử dụng ContextSource nào.
- **@EnableLdapRepositories(ldapTemplateRef=...)** gắn repository proxy với template đó.
- **@Qualifier** tránh tình huống có nhiều ContextSource mà Spring không biết chọn bean nào.

Thông tin **bind DN** là DN đầy đủ của service account, còn **base** là suffix cho các DN tương đối trong thao tác. Cấu hình manual không tự làm chứng chỉ TLS hợp lệ; JVM vẫn cần truststore được quản trị và hostname phải khớp SAN.

### 8.1. Một ứng dụng có hai directory

Ví dụ tổ chức có:

~~~text
People LDAP  -> ldaps://people-ldap.example.org:636
Groups LDAP  -> ldaps://groups-ldap.example.org:636
~~~

Khi đó không nên inject một **LdapTemplate** không được phân biệt vào tất cả repository rồi hy vọng nó tự chọn endpoint. Một phương án:

~~~text
org.example.directory.people.repository  -> peopleLdapTemplate
org.example.directory.groups.repository  -> groupsLdapTemplate
~~~

Mỗi vùng có một cấu hình **@EnableLdapRepositories** với **basePackages** và **ldapTemplateRef** tách biệt, cùng ContextSource tương ứng. Không để hai annotation quét chồng cùng một package.

Với Active Directory, có thể cần GC qua **3269** để đọc tìm kiếm toàn forest và DC qua **636** để đọc chi tiết/ghi vào domain. Một repository gắn với template GC **không tự đổi sang DC khi gọi save**. Cần phân quyền và định tuyến rõ ở service/gateway; không viết thiết kế CRUD trên giả định GC tương đương một writable domain DC.

### 8.2. Cẩn thận khi có nhiều bean cùng kiểu

Khi có nhiều ContextSource hoặc LdapTemplate:

~~~java
public PersonService(
        @Qualifier("peopleLdapTemplate") LdapTemplate template) {
    this.template = template;
}
~~~

Hãy đảm bảo **tên @Qualifier khớp** với bean thực tế. Nếu repository cần một template cụ thể, dùng **ldapTemplateRef** của vùng repository ấy; chỉ @Qualifier trên service **không thay đổi template mà repository proxy đã được gắn**.

Việc khai báo bean thủ công có thể khiến một phần auto-configuration **không tạo bean mặc định** theo chính sách @ConditionalOnMissingBean; nên ghi lại rõ **bean nào là nguồn sự thật** và tránh trộn config không có chủ đích.

## 9. Tách biệt khởi tạo ứng dụng và kết nối LDAP thành công

Một ngộ nhận phổ biến là: “Ứng dụng đã start nên LDAP chắc chắn hoạt động.” Thực tế phải xét các giai đoạn:

| Thời điểm | Điều có thể xác minh | Điều chưa chắc chắn |
| --- | --- | --- |
| **Đọc properties** | URL, base, tên bean được bind hợp lệ | Server online hay offline |
| **Tạo ContextSource** | Có bean và thông tin cấu hình | TLS/bind đã thành công hay chưa |
| **Tạo LdapTemplate** | Inject được ContextSource | Mọi thao tác LDAP có thể chạy |
| **Quét repository** | Interface đã được phát hiện | Entry được tìm đúng, schema hợp lệ |
| **Dựng repository proxy** | Metadata/query có thể được tạo | Account có quyền, DN tồn tại |
| **Thực hiện query thật** | Kết nối, TLS, bind, scope/filter và mapping | Mọi thao tác ghi khác cũng được cho phép |

Khi auto-configure bean, framework **thường không bắt buộc liên hệ network LDAP ngay**. Một phần mã tùy chỉnh, connection pool, health checker hoặc khởi tạo sớm có thể làm kết nối xảy ra ngay lúc startup. Vì vậy không có quy tắc “mọi lỗi LDAP chỉ xuất hiện sau startup”, cũng không có quy tắc “startup PASS chứng minh directory khỏe”.

### 9.1. Không gửi LDAP request tùy ý trong constructor

Tránh đặt thao tác tìm kiếm rộng hoặc bind thử với dữ liệu production vào **constructor/@PostConstruct** chỉ để “chắc chắn repository đã sẵn sàng”. Điều đó có thể:

- Làm mọi instance fail startup khi LDAP chậm hoặc đang bảo trì.
- Tăng tải lên directory khi nhiều pod khởi động cùng lúc.
- Kéo theo vòng phụ thuộc bean hoặc lỗi cấu hình khó chẩn đoán.

Nếu cần readiness/health check, hãy định nghĩa một thao tác **nhẹ, giới hạn thời gian, có quyền tối thiểu** và phân biệt **liveness** của ứng dụng với **readiness** phụ thuộc LDAP. Không để dữ liệu cá nhân xuất hiện trong health response.

## 10. Debug auto-configuration theo từng tầng

### 10.1. Xem condition evaluation report

Khi không rõ vì sao Boot tạo hoặc không tạo bean, có thể chạy ứng dụng trong môi trường phát triển với báo cáo auto-configuration:

~~~text
--debug
~~~

Hoặc bật logging có kiểm soát:

~~~yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
    org.springframework.data.repository.config: DEBUG
    org.springframework.data.ldap: DEBUG
    org.springframework.ldap: INFO
~~~

Xem **positive/negative matches** của LDAP auto-configuration và repository auto-configuration, số repository tìm được, cùng lỗi query/mapping. Log này dùng để xác định **điều kiện cấu hình**, không thay thế integration test network.

**Không bật LDAP debug quá chi tiết trong production** nếu nó ghi DN, filter, thuộc tính nhạy cảm hoặc mật khẩu; luôn đặt chính sách redact/retention phù hợp.

### 10.2. Quan sát bean qua ApplicationContext

Ví dụ một test xác minh ContextSource, template và repository đều có bean:

~~~java
package org.example.directory;

import org.example.directory.repository.PersonRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class LdapBootstrapTest {

    @Autowired ContextSource contextSource;
    @Autowired LdapTemplate ldapTemplate;
    @Autowired PersonRepository repository;

    @Test
    void springCreatesLdapInfrastructure() {
        assertNotNull(contextSource);
        assertNotNull(ldapTemplate);
        assertNotNull(repository);
    }
}
~~~

**Test này cần profile có cấu hình beans phù hợp**, nhưng chỉ kiểm tra DI và bootstrap. Nó chưa chứng minh kết nối LDAP thực sự thành công; cũng không bảo đảm chỉ có một bean nếu bạn cấu hình nhiều ContextSource/Template.

Nếu có nhiều bean, hãy bổ sung **@Qualifier** và kiểm tra định danh bean cụ thể thay vì inject theo type rồi để việc chọn bean phụ thuộc vào sự trùng hợp cấu hình.

## 11. Kiểm thử LDAP thật sau khi bootstrap

Một integration test cần **directory đã cấu hình**, schema và dữ liệu seed. Ví dụ LDAP thử nghiệm có suffix **dc=example,dc=org**:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
~~~

Nếu LDAP server đã có suffix và OU, không nạp trùng những entry đó. Directory thử nghiệm có thể dùng container hoặc server nhúng phù hợp, nhưng **schema/ACL/TLS của LDAP nhúng không luôn giống production**.

Test repository:

~~~java
package org.example.directory;

import java.util.List;
import org.example.directory.entry.PersonEntry;
import org.example.directory.repository.PersonRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest
class LdapRepositoryIntegrationTest {
    @Autowired PersonRepository repository;

    @Test
    void findByUidReachesDirectory() {
        List<PersonEntry> users = repository.findByUid("an");

        assertFalse(users.isEmpty());
        assertEquals("an", users.get(0).getUid());
    }
}
~~~

**Test này có điều kiện:** phải có LDAP server test, cấu hình ContextSource và fixture **uid=an**. Nếu LDAP dùng LDAPS, CA/SAN phải hợp lệ trong truststore của môi trường test. Không dùng tài khoản production hoặc tắt TLS verification để test chạy.

Một test qua LdapTemplate:

~~~java
package org.example.directory;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class LdapTemplateIntegrationTest {
    @Autowired LdapTemplate template;

    @Test
    void readsKnownDnUsingConfiguredBase() {
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "an").build();

        String cn = template.lookup(
                relativeDn,
                (AttributesMapper<String>) attributes ->
                    (String) attributes.get("cn").get());

        assertEquals("An Tran", cn);
    }
}
~~~

Hai test sử dụng **cùng directory/fixture** nhưng đi qua các API khác nhau. Nếu test repository thất bại trong khi test LdapTemplate thành công, hãy điều tra **repository scanning, ODM metadata và query derivation** trước khi sửa URL hoặc bind password.

### 11.1. Ma trận kiểm thử thiết lập

| Ca | Thiết lập | Kết quả cần quan sát |
| --- | --- | --- |
| Starter và package đúng | Classpath đủ, repository dưới package gốc | Có ContextSource, LdapTemplate và repository proxy |
| Thiếu Spring Data LDAP | Chỉ có API Spring LDAP | Có thể dùng LdapTemplate, không có repository tự tạo |
| Repository ngoài vùng scan | Interface nằm ở package khác | Bean repository không được đăng ký |
| EnableLdapRepositories đúng package | Dùng **basePackageClasses** | Interface được phát hiện |
| Nhiều scan trùng | Hai config cùng chọn một interface | Phát hiện xung đột bean/sai template, sửa phạm vi |
| Custom ContextSource | Khai báo bean thủ công | Kiểm tra Boot back-off và template dùng đúng source |
| Hai directory | Hai template và hai vùng repository | Mỗi repository gọi đúng endpoint và base |
| Invalid bind password | Dùng service credentials sai | Operation LDAP thất bại, không nhầm với lỗi scan |
| Certificate CA/SAN sai | LDAPS certificate không hợp lệ | Kết nối bị từ chối an toàn |
| Base DN sai | ContextSource base không khớp cây | Search/lookup lỗi hoặc không trả dữ liệu |
| Thiếu objectClass/required attribute | Entry test vi phạm schema | Ghi bị từ chối dù bean tồn tại |
| ACL read-only | Dùng tài khoản không có quyền ghi | Truy vấn đọc có thể thành công, ghi bị từ chối |
| Repo query sai property | Khai báo **findByUnknownField** | Lỗi tạo query/metadata trong quá trình bootstrap hoặc gọi |
| Directory tạm unavailable | Tắt server test sau khởi tạo | Context vẫn có bean nhưng LDAP operation thất bại |

## 12. Những lỗi dễ nhầm trong dự án thật

| Triệu chứng | Tầng đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| **No qualifying bean of type ContextSource** | Auto-config classpath hoặc custom bean | Kiểm tra dependency, điều kiện cấu hình và @Bean |
| **No qualifying bean of type LdapTemplate** | Template auto-config/back-off | Kiểm tra bean ContextSource, bean template và thứ tự cấu hình |
| **No qualifying bean of type PersonRepository** | Repository scanning | Kiểm tra package, dependency Spring Data LDAP, @EnableLdapRepositories |
| **Found 0 LDAP repository interfaces** | Scan base không đúng | Đặt @SpringBootApplication ở package bao phủ hoặc khai báo basePackageClasses |
| **Duplicate bean / bean override conflict** | Nhiều vùng scan đè nhau | Dùng một chiến lược scan cho mỗi repository |
| **No bean named ldapTemplate** | ldapTemplateRef hoặc tên bean | Sửa tên template mà repository factory tham chiếu |
| **NoUniqueBeanDefinitionException** | Nhiều template/context source cùng kiểu | Dùng @Qualifier hoặc tên bean rõ ràng |
| **PropertyReferenceException** | Derived query gọi property không có trên ODM entity | Sửa tên Java property hoặc @Attribute mapping |
| **No such object (32)** | LDAP DN/base hoặc parent không tồn tại | So DN tương đối, full DN và subtree thực tế |
| **Invalid credentials (49)** | Bind identity/password | Kiểm tra secret và trạng thái service account |
| **Insufficient access rights (50)** | ACL LDAP | Cấp quyền tối thiểu theo thao tác cần thiết |
| **Object class violation (65)** | Schema/objectClass | Kiểm tra cn/sn, attribute MUST/MAY và loại entry |
| **SSLHandshakeException/PKIX** | TLS truststore/certificate | Sửa CA/hostname, không tắt verification |
| **Directory unavailable / timeout** | Network, server, DNS, firewall | Kiểm tra endpoint và timeout/retry có kiểm soát |

### 12.1. Quy trình chẩn đoán theo thứ tự

1. **Có bean chưa?** Xem condition report và log scan để xác định ContextSource/Template/Repository.
2. **Bean có đúng cấu hình không?** Xác nhận URL, base DN, tên template và ldapTemplateRef, nhưng không log password.
3. **TLS có hợp lệ không?** Kiểm tra CA, SAN, hostname, protocol/cổng và policy của JVM.
4. **Bind đúng danh tính không?** Kiểm tra service account và quyền cụ thể.
5. **LDAP tree có đúng không?** So root/suffix, DN, RDN, objectClass và thuộc tính thực.
6. **Repository mapping/query đúng không?** Kiểm tra @Entry/@Id/@Attribute, tên property và filter.
7. **Có kiểm thử với directory thật chưa?** Seed fixture, gọi lookup/search, xác minh kết quả và dọn dữ liệu.

Phân lớp lỗi như vậy giúp tránh việc sửa **LDAP password** để chữa lỗi **repository không được scan**, hoặc thêm **@EnableLdapRepositories** để chữa lỗi **chứng chỉ server đã hết hạn**.

## 13. Bảo mật và vận hành của lớp cấu hình

Việc tự tạo ContextSource làm cho kết nối thuận tiện hơn, nhưng cũng tạo ra trách nhiệm kiểm soát:

- **TLS:** dùng LDAPS hoặc StartTLS, luôn xác minh certificate chain và hostname.
- **Bí mật:** đặt bind password trong hệ thống secrets; tránh hardcode và không in Environment hay toàn bộ cấu hình ra log.
- **Quyền tối thiểu:** reader/writer có quyền khác nhau; ContextSource cho mỗi vai trò có thể dùng account khác nhau.
- **Endpoint allowlist:** không nhận LDAP URL, base DN, bind DN hoặc password từ request ngoài rồi chuyển thẳng thành ContextSource.
- **Filter/DN:** xây DN bằng **LdapNameBuilder**, filter bằng **LdapQueryBuilder**; không nối chuỗi từ input.
- **Giới hạn truy vấn:** base/scope, attributes, count/time limits, paging khi cần và rate limiting cho API.
- **Kết nối/pool:** nếu có pooling, kiểm soát số kết nối, timeout, idle và cách tái tạo khi rotate TLS certificate/credentials.
- **Theo dõi phụ thuộc:** đo latency, lỗi bind/TLS, timeouts và kích hoạt cảnh báo theo mức độ ảnh hưởng.
- **Tính nhất quán:** LDAP và database quan hệ không tự nằm trong cùng transaction chỉ vì một Spring @Transactional bao quanh các method.

Trong ứng dụng nhiều người dùng, **không khởi tạo ContextSource mới cho mỗi HTTP request** với URL/credentials từ client. ContextSource là cấu hình hạ tầng do ứng dụng sở hữu, được Spring quản lý vòng đời; nếu cần xác thực một người dùng LDAP, hãy dùng cơ chế xác thực được thiết kế riêng và có kiểm soát bảo mật.

## 14. Tổng kết và câu hỏi tự luyện

**Spring Boot tự cấu hình ContextSource, LdapTemplate và Repository** bằng cách kết hợp **dependency trên classpath**, **các điều kiện auto-configuration**, **properties**, **bean do lập trình viên khai báo** và **phạm vi quét repository**. ContextSource là nền tảng kết nối; LdapTemplate thực hiện LDAP operations; Spring Data LDAP tạo proxy cho **LdapRepository** và dùng ODM để ánh xạ entry sang Java.

Hiểu thứ tự phụ thuộc này giúp bạn quyết định **khi nào để Boot làm mặc định**, khi nào cần **@EnableLdapRepositories**, **ldapTemplateRef** hay cấu hình thủ công nhiều directory. Việc Spring container tạo bean thành công không đồng nghĩa directory đã chấp nhận kết nối, xác thực, schema hoặc CRUD: những điều đó chỉ được xác minh khi có LDAP operation/test thực tế.

**Câu hỏi tự luyện:**

1. Vẽ đường đi từ **spring.ldap.urls** và **spring.ldap.base** đến **PersonRepository.findByUid("an")**. Bean nào phụ thuộc vào bean nào?
2. Vì sao **@Entry** không tự động tạo PersonRepository? Vì sao **@ComponentScan** không hoàn toàn tương đương quét repository?
3. Nếu **DirectoryApplication** nằm ở **org.example.app** và repository ở **org.example.shared.ldap**, bạn sẽ thay đổi cấu hình quét thế nào?
4. Hai bean **LdapTemplate** được khai báo cho hai ContextSource. **@Qualifier** trên service và **ldapTemplateRef** trên @EnableLdapRepositories khác nhau ở điểm nào?
5. Điều gì xảy ra khi một ContextSource do ứng dụng khai báo khiến auto-configuration quyết định back off? Cách xác minh bằng condition report?
6. Vì sao Spring Boot khởi động thành công nhưng lần đầu gọi repository lại nhận **invalidCredentials (49)** hoặc **SSLHandshakeException**?
7. Phân biệt **DN đầy đủ**, **DN tương đối**, **base DN** và **bind DN** trong ví dụ **uid=an,ou=people,dc=example,dc=org**.
8. Dựng kiểm thử bootstrap và kiểm thử thực với LDAP. Test nào chứng minh có repository bean, test nào chứng minh LDAP server đã trả đúng uid=an?
9. Tại sao một repository trỏ vào Active Directory Global Catalog không nên mặc định được dùng để ghi vào bất kỳ domain nào?
10. Nếu ứng dụng kết nối LDAPS bằng service account, những kiểm soát nào vẫn cần có ngoài việc cấu hình URL và password?

### Tài liệu tham khảo

- [Spring Boot Reference — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html) — cấu hình Spring LDAP và Spring Data LDAP repositories trong Boot (đối chiếu theo phiên bản sử dụng).
- [Spring Boot Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html) — tra cứu nhóm **spring.ldap.*** và **spring.data.ldap.***.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — ContextSource, LdapTemplate và kết nối/truy vấn LDAP.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — repository configuration, ODM và query methods.
- [Spring Data LDAP — Creating Repository Instances](https://docs.spring.io/spring-data/ldap/reference/repositories/create-instances.html) — repository scanning, factory bean và proxy.
- [Spring Data LDAP — EnableLdapRepositories Javadoc](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/config/EnableLdapRepositories.html) — basePackages, basePackageClasses và ldapTemplateRef.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) và [RFC 4513 — Authentication and Security](https://www.rfc-editor.org/rfc/rfc4513) — thao tác LDAP, bind và bảo mật truyền tải.
