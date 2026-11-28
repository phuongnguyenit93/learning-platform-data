# Cơ chế quét và tạo triển khai Repository

## Mục tiêu bài học

Trong **Spring Data LDAP**, lập trình viên thường khai báo một **interface** kế thừa **LdapRepository** rồi tiêm interface đó vào service. Không có file Java nào viết lớp triển khai tương ứng, nhưng ứng dụng vẫn gọi được **findByUid**, **findAll**, **save** hay **deleteById**. Điều này xảy ra nhờ **cơ chế quét repository, đăng ký FactoryBean và tạo proxy trong Spring container**.

Bài thuộc chương **LDAP Repository** này giúp bạn hiểu đường đi từ mã nguồn đến câu lệnh LDAP thật, thay vì chỉ ghi nhớ cách khai báo một interface.

Sau bài học, bạn có thể:

- Giải thích **repository scanning** khác gì với quét component thông thường và quét các entry ODM.
- Mô tả những bước Spring Data LDAP tìm interface hợp lệ, đăng ký **LdapRepositoryFactoryBean**, tạo **repository proxy** và gắn **LdapTemplate**.
- Dùng Spring Boot auto-configuration hoặc **@EnableLdapRepositories** để xác định package cần quét.
- Hiểu cách phương thức CRUD, derived query, **@Query** và custom fragment được điều phối khi gọi repository.
- Phân biệt **@Entry**, **@Id**, **@Attribute**, **@Repository** và **@NoRepositoryBean** trong ngữ cảnh LDAP.
- Chẩn đoán lỗi không tìm thấy bean, scan nhầm package, ánh xạ DN sai, kết nối nhầm ContextSource và truy vấn khởi tạo thất bại.
- Thiết kế kiểm thử có cả phần xác minh Spring bean và phần kiểm chứng directory, schema, bảo mật kết nối.

## 1. Repository có hoạt động dù không có lớp *Impl* không?

Giả sử cần tìm người dùng LDAP theo thuộc tính **uid**. Bạn khai báo:

~~~java
package org.example.directory.repository;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.example.directory.entry.PersonEntry;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
}
~~~

Sau đó service dùng constructor injection:

~~~java
package org.example.directory.service;

import java.util.List;
import org.springframework.stereotype.Service;
import org.example.directory.entry.PersonEntry;
import org.example.directory.repository.PersonRepository;

@Service
public class PersonLookupService {
    private final PersonRepository personRepository;

    public PersonLookupService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    public List<PersonEntry> findPeople(String uid) {
        return personRepository.findByUid(uid);
    }
}
~~~

Bạn không viết **PersonRepositoryImpl** cho phương thức trên. Spring Data đọc metadata của interface, kết hợp cấu hình LDAP và tạo ra một **Spring bean là proxy** có thể nhận lời gọi phương thức. Proxy chuyển các lời gọi CRUD đến phần triển khai repository cơ sở, và chuyển các phương thức tìm kiếm phù hợp đến bộ xử lý query của Spring Data LDAP.

Điều quan trọng:

> **Repository proxy không phải LDAP server và cũng không phải bản sao dữ liệu trong bộ nhớ.** Nó là đối tượng Java điều phối lời gọi đến **LdapTemplate**, rồi thông qua **ContextSource/JNDI** gửi yêu cầu LDAP đến directory.

Vì thế, **bean repository tồn tại** chỉ chứng minh cấu hình Spring đã tạo được bean; nó **không chứng minh** LDAP endpoint đang hoạt động, DN đúng, tài khoản đủ quyền hoặc schema có thể chấp nhận dữ liệu.

## 2. Nhìn toàn cảnh: từ @EnableLdapRepositories tới LDAP server

~~~mermaid
flowchart TD
    A["Spring Boot auto-config hoặc @EnableLdapRepositories"] --> B["Xác định base package để quét"]
    B --> C["Phát hiện interface repository hợp lệ"]
    C --> D["Đọc metadata domain class và phương thức"]
    D --> E["Đăng ký LdapRepositoryFactoryBean"]
    E --> F["LdapRepositoryFactory dựng repository proxy"]
    F --> G["CRUD: triển khai cơ sở / Query: bộ phân giải / Fragments"]
    G --> H["LdapTemplate"]
    H --> I["ContextSource -> JNDI"]
    I --> J["LDAP directory: DN, schema, ACL"]
~~~

Có thể phân thành **hai giai đoạn lớn**:

1. **Bootstrap Spring container:** phát hiện interface, tạo bean definition, kết nối các thành phần cần thiết và khởi tạo proxy khi tới giai đoạn phù hợp.
2. **Runtime:** service gọi phương thức trên proxy; Spring Data chọn nhánh thực thi, tạo truy vấn hoặc dùng phương thức CRUD, sau đó truy cập LDAP.

**Không đánh đồng “quét và tạo repository” với “quét directory LDAP”.** Quét repository là quét **các Java interface trong classpath**. LDAP search chỉ xảy ra khi có lời gọi truy vấn thực sự (hoặc khi ứng dụng chủ động kiểm tra kết nối).

## 3. Những thành phần Spring Data LDAP sử dụng

| Thành phần | Vai trò |
| --- | --- |
| **@EnableLdapRepositories** | Kích hoạt và cấu hình quét các repository LDAP |
| **LdapRepositoriesRegistrar** | Tích hợp đăng ký repository bean definitions vào quá trình cấu hình Spring |
| **LdapRepositoryFactoryBean** | FactoryBean dành cho việc khởi tạo Spring Data LDAP repository |
| **LdapRepositoryFactory** | Tạo repository proxy và cấu hình cách xử lý các lời gọi |
| **SimpleLdapRepository** | Phần triển khai cơ sở cho các thao tác repository phổ biến |
| **LdapMappingContext / ODM mapping** | Quản lý metadata ánh xạ từ Java entry class sang LDAP attributes |
| **LdapTemplate** | Thực thi thao tác LDAP như tìm kiếm, lookup, bind, modify, unbind |
| **ContextSource** | Cung cấp connection/context với URL, base DN, bind DN, credentials và chính sách kết nối |
| **Directory server** | Kiểm tra schema, ACL, phạm vi DN, filter và thực hiện thao tác thật |

Tên các lớp ở bảng là những thành phần cụ thể của Spring Data LDAP; chi tiết nội bộ có thể thay đổi theo phiên bản. Lập trình ứng dụng thông thường chỉ cần quan tâm **@Entry**, repository interface, **@EnableLdapRepositories** khi cần, và cấu hình **LdapTemplate/ContextSource**.

### 3.1. LdapRepository không giống repository JPA

Trong Spring Data LDAP, **LdapRepository<T>** nhận **một** tham số generic cho kiểu entry. ID của các entity LDAP ODM là **javax.naming.Name**, vì danh tính của entry là DN.

~~~java
// Đúng với Spring Data LDAP:
public interface PersonRepository extends LdapRepository<PersonEntry> {
}

// Không phải cách khai báo LdapRepository:
// LdapRepository<PersonEntry, Long> ...
~~~

Bạn có thể gặp ví dụ trên mạng dùng **CrudRepository<T, ID>**, **JpaRepository<T, ID>** hoặc **MongoRepository<T, ID>**. Những repository đó thuộc hạ tầng hoặc datastore khác; không được sao chép nguyên generic, annotation định danh và tính năng phân trang/sắp xếp của chúng rồi giả định LDAP hỗ trợ tương đương.

Theo tài liệu Spring LDAP, **paging và sorting không được hỗ trợ như các tính năng repository LDAP chung**; khi cần paging ở mức LDAP server, phải nghiên cứu thêm LDAP paged-results control và lựa chọn API tương ứng, thường qua LdapTemplate. Đừng tạo phương thức trả **Page<PersonEntry>** chỉ vì Spring Data Commons có kiểu **Page**.

## 4. Ví dụ tự chứa: dự án Spring Boot có repository LDAP

Một cấu trúc package gọn:

~~~text
org.example.directory
├── DirectoryApplication.java
├── entry
│   └── PersonEntry.java
├── repository
│   └── PersonRepository.java
└── service
    └── PersonLookupService.java
~~~

Trong ví dụ, class chạy ứng dụng nằm ở **org.example.directory**; **entry**, **repository** và **service** đều là các package con. Đây là lựa chọn hữu ích vì Spring Boot thường lấy package của class **@SpringBootApplication** làm gốc auto-configuration scanning.

### 4.1. Dependency và kết nối LDAP

Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Ví dụ **application.yml**:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Ví dụ dùng **LDAPS**: JVM phải tin đúng CA của server và xác minh hostname theo certificate; mật khẩu bind lấy từ secret/biến môi trường, không đưa vào Git. **base** là DN gốc của các thao tác tương đối (ví dụ tìm **ou=people** dưới **dc=example,dc=org**).

### 4.2. Khai báo entry ODM

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

    public PersonEntry() {
    }

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

Đây là class Java đại diện cho entry LDAP. Các annotation **@Entry**, **@Id** và **@Attribute** đến từ **org.springframework.ldap.odm.annotations**, không phải annotation JPA.

Trong mô hình này:

- **@Entry** nói class ánh xạ với các objectClass LDAP và gốc tương đối **ou=people**.
- **@Id** giữ DN dưới dạng **javax.naming.Name**, không phải ID số tự tăng.
- **@Attribute** ánh xạ tên field Java như **commonName** sang thuộc tính LDAP **cn**.
- LDAP server vẫn kiểm tra **inetOrgPerson**, **cn/sn**, schema và quyền. Annotation không tạo schema.

### 4.3. Khai báo repository interface

~~~java
package org.example.directory.repository;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.example.directory.entry.PersonEntry;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByUid(String uid);

    List<PersonEntry> findByCommonName(String commonName);
}
~~~

**findByUid** và **findByCommonName** là những phương thức query derivation: Spring Data phân tích tên phương thức, tìm property trên entity và dựng điều kiện tìm kiếm theo ánh xạ LDAP. **findByCommonName** tham chiếu property Java **commonName**, nhưng thuộc tính LDAP thực tế được ánh xạ là **cn**.

Hai hàm trả **List** thay vì hứa luôn tìm được đúng một entry. **uid** không mặc nhiên duy nhất trên toàn cây, còn **cn** càng có thể trùng nhau. Phạm vi tìm kiếm phụ thuộc base DN, base của entry và các tùy chọn truy vấn.

### 4.4. Class khởi động

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

Nếu dependency và package được sắp xếp đúng, Spring Boot có thể auto-configure **LdapContextSource**, **LdapTemplate** và **Spring Data LDAP repositories**. Trong cấu trúc này, không cần viết một lớp **PersonRepositoryImpl** hay thêm **@Repository** vào interface.

**Lưu ý:** tự động kích hoạt phụ thuộc classpath, bean đã có, điều kiện auto-configuration và phiên bản Spring Boot. Nếu bạn tự khai báo repository configuration hoặc thay thế ContextSource/LdapTemplate, phải hiểu những thành phần đó được sử dụng như thế nào, không mặc định mọi auto-config luôn chạy.

## 5. Giai đoạn 1: Spring tìm các interface repository hợp lệ

Khi cấu hình Spring Data LDAP có hiệu lực, hạ tầng sẽ quét **base packages** đã xác định và kiểm tra những **interface repository** thích hợp.

Ví dụ, với package:

~~~text
org.example.directory.repository
├── PersonRepository.java
├── GroupRepository.java
└── AuditService.java
~~~

Nếu **PersonRepository** và **GroupRepository** kế thừa đúng interface repository LDAP, chúng là ứng viên. **AuditService** là class thông thường; nó không tự biến thành repository chỉ vì nằm trong cùng package.

### 5.1. @ComponentScan không đồng nghĩa @EnableLdapRepositories

| Cơ chế | Đối tượng chính | Kết quả |
| --- | --- | --- |
| **@ComponentScan** | Các class được đánh dấu component stereotype như **@Component**, **@Service**, **@Repository** | Tạo bean từ class có thể khởi tạo |
| **Repository scanning** | Interface kế thừa loại repository mà Spring Data module hỗ trợ | Đăng ký FactoryBean để sinh proxy repository |
| **Entity/ODM mapping discovery** | Class được ánh xạ thành LDAP entry bằng **@Entry/@Id** | Tạo/thu thập metadata ánh xạ, không phải repository proxy |

Thêm **@Repository** vào **interface PersonRepository** không phải cách thay thế **@EnableLdapRepositories** hoặc auto-configuration. Bởi vì interface không thể được khởi tạo như một class bình thường, Spring Data cần quét và tạo proxy chuyên biệt.

Ngược lại, chỉ thêm **@Entry** vào PersonEntry không tạo ra **PersonRepository**: bạn vẫn phải khai báo interface repository và bật cấu hình repository phù hợp.

### 5.2. Các điều kiện ảnh hưởng phát hiện interface

- Interface phải thuộc **package được quét** (và thông thường các package con).
- Interface phải được nhận diện là một repository của module đang cấu hình. Kế thừa **LdapRepository<PersonEntry>** là lựa chọn rõ ràng.
- Generic domain type phải là class ODM phù hợp, có **@Entry** và trường **@Id** kiểu **Name**.
- Interface được đánh dấu **@NoRepositoryBean** là base interface dùng chung, không được đăng ký như repository cụ thể.
- Bộ lọc **includeFilters/excludeFilters** nếu được cấu hình có thể thu hẹp hoặc loại ứng viên.
- Với repository interface khai báo lồng trong class, việc phát hiện tùy **considerNestedRepositories**; mặc định thường không quét nested repositories.

Đặc biệt, khi ứng dụng có nhiều module Spring Data (ví dụ JPA và LDAP), cần phân tách phạm vi quét và dùng **repository interface đặc thù của datastore**. Nếu khai báo một interface generic **CrudRepository** mà không có metadata nhận diện rõ ràng, Spring Data có thể không biết module nào phải xử lý hoặc báo lỗi trùng/không rõ backend.

## 6. Giai đoạn 2: Spring đăng ký FactoryBean và dựng proxy

Với một interface được nhận diện, Spring Data **không tạo bean bằng new PersonRepository()**. Hạ tầng đăng ký một bean definition dùng **LdapRepositoryFactoryBean** và các metadata liên quan.

Khi factory được khởi tạo, nó sử dụng **LdapRepositoryFactory** để ghép:

1. **Phần triển khai CRUD cơ sở**, chẳng hạn logic trong **SimpleLdapRepository**.
2. **Bộ phân giải các phương thức query** dựa theo tên phương thức, annotation hoặc query đã khai báo.
3. **Custom repository fragments** nếu interface có mở rộng hành vi viết tay.
4. **LdapTemplate** và thông tin ánh xạ để thực thi trên directory.

Bean mà service nhận được là một **repository proxy**, không phải một instance trực tiếp của class PersonRepositoryImpl do bạn viết. Tên bean thông thường được suy ra từ interface: **PersonRepository** thành **personRepository**.

### 6.1. Đường đi của một lời gọi

Ví dụ:

~~~java
personRepository.findByUid("an");
~~~

Luồng logic:

~~~text
PersonLookupService
  -> PersonRepository proxy
      -> nhận diện method findByUid(String)
      -> phân tích property uid, áp dụng metadata @Entry/@Attribute
      -> dựng LDAP search query/filter phù hợp
      -> LdapTemplate.search(...)
      -> ContextSource -> JNDI -> LDAP server
      -> Attributes / ODM mapping -> List<PersonEntry>
~~~

Câu lệnh LDAP cụ thể chịu ảnh hưởng của entity mapping, DN/base cấu hình và phiên bản triển khai. Không cần suy đoán một chuỗi filter chính xác để hiểu cơ chế: **Java method được chuyển thành thao tác LDAP qua proxy và template**.

Với **findById(Name dn)**, logic đi theo định danh DN; với **save(entity)**, repository thực hiện những thao tác ghi tương ứng. Việc ghi có thành công hay không vẫn do **schema, quyền bind, dữ liệu bắt buộc và trạng thái directory** quyết định.

### 6.2. Spring có kết nối LDAP ngay trong lúc scan không?

**Scanning** chủ yếu dùng thông tin classpath và bean definitions. Nó không tương đương việc quét entry LDAP. Việc dựng proxy có thể xác minh metadata, mapping và query methods ở thời điểm khởi tạo bean; **LDAP network I/O thường diễn ra khi repository được sử dụng**, hoặc khi một thành phần chủ động kiểm tra kết nối.

Vì thế:

- **Repository bean tạo được** không bảo đảm **LDAP server reachable**.
- **Sai package/mapping** thường lộ ra khi khởi động hoặc khi bean được tạo.
- **Sai bind password, certificate hoặc DN** có thể chỉ xuất hiện khi có thao tác LDAP thực tế.
- Tùy bootstrap mode/lazy initialization và phiên bản cấu hình, thời điểm phát hiện một lỗi có thể khác nhau; không dựa vào “ứng dụng chạy được” để kết luận LDAP tích hợp đúng.

## 7. Ba cách cấu hình phạm vi quét repository

### 7.1. Cách A: dùng auto-configuration của Spring Boot

Với **@SpringBootApplication** nằm ở **org.example.directory**, các repository con trong **org.example.directory.repository** thường được tự động phát hiện theo package auto-configuration.

~~~text
org.example.directory.DirectoryApplication
org.example.directory.entry.PersonEntry
org.example.directory.repository.PersonRepository
~~~

Đây là cách đơn giản khi project nhỏ và toàn bộ module LDAP nằm dưới package gốc. Hãy kiểm tra log repository bootstrap nếu bean không xuất hiện.

Spring Boot cũng cho phép cấu hình vị trí scan repository và domain entry bằng **@EnableLdapRepositories** và **@EntityScan** khi cấu trúc package nằm ngoài phạm vi mặc định. Không đồng nhất việc scan entity với scan interface repository: chúng là hai phạm vi cần xác định riêng.

### 7.2. Cách B: kích hoạt chủ động bằng @EnableLdapRepositories

Nếu muốn chỉ rõ package repository, có thể cấu hình:

~~~java
package org.example.directory.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;
import org.example.directory.repository.PersonRepository;

@Configuration(proxyBeanMethods = false)
@EnableLdapRepositories(
    basePackageClasses = PersonRepository.class,
    ldapTemplateRef = "ldapTemplate"
)
public class LdapRepositoryConfiguration {
}
~~~

**basePackageClasses** lấy package của class/interface được chỉ định làm gốc quét (ở đây là package chứa **PersonRepository**). Cách này tránh lỗi gõ sai chuỗi package.

Nếu dùng dạng chuỗi:

~~~java
@EnableLdapRepositories(
    basePackages = "org.example.directory.repository"
)
~~~

thì Spring quét package đó cùng các package con. Dạng không tham số:

~~~java
@EnableLdapRepositories
~~~

sẽ dùng package của **class đánh dấu annotation** làm cơ sở quét. Nếu class cấu hình nằm ở **org.example.directory.config**, còn repository ở **org.example.directory.repository** là package ngang cấp, mặc định đó **không phải** đúng vị trí để tìm repository.

**Không đồng thời khai báo nhiều cấu hình quét cùng một nhóm repository** trừ khi bạn đã chủ đích phân vùng. Trùng bean definition hoặc hai module cùng nhận một interface sẽ gây lỗi khó theo dõi. Với Spring Boot, thường chọn **auto-configuration** hoặc **@EnableLdapRepositories tường minh** cho phạm vi cần quản lý, thay vì chồng nhiều lệnh scan vô ý.

### 7.3. Cách C: XML namespace trong dự án cũ

Trong các ứng dụng cấu hình Spring XML, repository LDAP có thể được bật qua phần tử **data-ldap:repositories**, với thuộc tính base package và tên bean LdapTemplate:

~~~xml
<data-ldap:repositories
    base-package="org.example.directory.repository"
    ldap-template-ref="ldapTemplate"/>
~~~

Ví dụ trên là **đoạn XML cấu hình**, cần được đặt trong tài liệu Spring XML có namespace và schema location tương ứng. Với project Spring Boot mới, JavaConfig thường dễ bảo trì hơn. XML và annotation là hai cách kích hoạt cùng một loại hạ tầng repository; không cần cấu hình cả hai cho cùng interface.

## 8. Một repository liên kết với LdapTemplate nào?

Một **LdapTemplate** dùng một **ContextSource**, nơi có thông tin:

- LDAP URL, ví dụ **ldaps://ldap.example.org:636**.
- Base DN, ví dụ **dc=example,dc=org**.
- Bind DN, password và chính sách bảo mật kết nối.
- Các lựa chọn timeout, referral, pooling hoặc authentication strategy theo cấu hình.

Theo quy ước Spring Data LDAP, repository thường tìm một bean **LdapTemplate** có tên **ldapTemplate**. Nếu ứng dụng tự đặt tên khác, cần dùng **ldapTemplateRef** để liên kết đúng.

Ví dụ:

~~~java
@Configuration
@EnableLdapRepositories(
    basePackages = "org.example.directory.readrepository",
    ldapTemplateRef = "readLdapTemplate"
)
public class ReadRepositoryConfiguration {
}
~~~

Và:

~~~java
@Bean("readLdapTemplate")
LdapTemplate readLdapTemplate(
        @Qualifier("readContextSource") ContextSource source) {
    return new LdapTemplate(source);
}
~~~

Đoạn Java thứ hai giả định các import **@Bean**, **@Qualifier**, **ContextSource**, **LdapTemplate** và bean **readContextSource** đã có trong một class cấu hình; đây là ví dụ phần liên kết, không phải chương trình hoàn chỉnh độc lập.

Trong hệ thống có **hai directory**, chẳng hạn LDAP nhân sự và AD DS, hãy tạo **phạm vi repository riêng**, **LdapTemplate riêng** và đặt tên bean rõ ràng. Không cho hai cấu hình @EnableLdapRepositories quét chồng cùng package. Với repository cần đọc từ GC và ghi vào domain controller, chỉ thay URL khi gọi repository là không đủ; cần thiết kế truy cập hai endpoint và định tuyến theo vai trò.

## 9. Phương thức query được triển khai tự động ra sao?

Spring Data thường dùng chiến lược **CREATE_IF_NOT_FOUND**: tìm truy vấn được khai báo trước, nếu không có thì cố dựng query từ tên phương thức. Các chiến lược khác như **CREATE** hoặc **USE_DECLARED_QUERY** có thể cấu hình tùy module.

### 9.1. Derived query

~~~java
public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
    List<PersonEntry> findByCommonName(String commonName);
    List<PersonEntry> findByUidAndSurname(String uid, String surname);
}
~~~

Bộ phân giải phương thức nhận diện phần sau **By**, cùng các toán tử như **And/Or** khi được module hỗ trợ. Nó dùng metadata entity để chuyển **commonName** sang **cn**, **surname** sang **sn**. Không cần tạo một class triển khai riêng cho mỗi truy vấn.

**Nếu tên method không khớp một property của entity**, hoặc bạn dùng một keyword không được LDAP module hỗ trợ, có thể gặp lỗi tạo query khi bootstrap repository. Đây khác lỗi do LDAP server không chứa dữ liệu phù hợp.

### 9.2. @Query khai báo filter tường minh

Với filter cần kiểm soát trực tiếp:

~~~java
package org.example.directory.repository;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;
import org.example.directory.entry.PersonEntry;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);

    @Query("(&(objectClass=inetOrgPerson)(mail=:email))")
    List<PersonEntry> findPeopleByEmail(@Param("email") String email);
}
~~~

**@Query** ở đây đến từ **org.springframework.data.ldap.repository.Query**, không phải annotation JPA hoặc MongoDB. Placeholder **:email** được Spring Data ràng buộc với tham số và có xử lý mã hóa giá trị thích hợp cho LDAP filter theo tài liệu module.

Đừng ghép dữ liệu từ request trực tiếp vào chuỗi filter, chẳng hạn nối **(mail=** với raw input. Với **SpEL expressions** hoặc property placeholders trong filter, việc escaping có khác biệt: **giá trị SpEL/property expressions không tự được LDAP-escaped như parameter binding thông thường**; chỉ sử dụng khi hiểu và kiểm soát đầu vào. Truy vấn tự động cũng không thay thế quyền ACL và giới hạn search base.

### 9.3. Phương thức mặc định, custom fragment và lớp Impl

Không phải phương thức nào nằm trong repository interface cũng do query derivation xử lý:

- **Phương thức CRUD** của LdapRepository chuyển đến triển khai cơ sở.
- **Derived query** và **@Query** chuyển đến bộ xử lý query LDAP.
- **default method** trong Java interface có thân hàm của chính nó.
- **Custom fragment** có interface và class triển khai do bạn viết, được ghép vào repository proxy khi cấu hình/đặt tên phù hợp.

Ví dụ cần kiểm tra **thành viên trực tiếp** trong một nhóm **groupOfNames** có thể dùng fragment. Giả sử ContextSource có base **dc=example,dc=org**, người dùng nằm ở **ou=people**, nhóm ở **ou=groups**:

~~~java
package org.example.directory.repository;

public interface PersonDirectoryOperations {
    boolean isDirectMemberOfGroup(String groupCn, String uid);
}
~~~

~~~java
package org.example.directory.repository;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonDirectoryOperationsImpl
        implements PersonDirectoryOperations {
    private final LdapTemplate ldapTemplate;

    public PersonDirectoryOperationsImpl(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Override
    public boolean isDirectMemberOfGroup(String groupCn, String uid) {
        validateIdentifier(groupCn);
        validateIdentifier(uid);

        String fullUserDn = LdapNameBuilder
                .newInstance("dc=example,dc=org")
                .add("ou", "people")
                .add("uid", uid)
                .build().toString();

        List<String> matchedGroups = ldapTemplate.search(
                query().base("ou=groups")
                        .attributes("cn")
                        .where("objectClass").is("groupOfNames")
                        .and("cn").is(groupCn)
                        .and("member").is(fullUserDn),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
        return !matchedGroups.isEmpty();
    }

    private static void validateIdentifier(String value) {
        if (value == null || !value.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Định danh không hợp lệ");
        }
    }
}
~~~

~~~java
package org.example.directory.repository;

import org.springframework.data.ldap.repository.LdapRepository;
import org.example.directory.entry.PersonEntry;

public interface PersonRepository extends
        LdapRepository<PersonEntry>, PersonDirectoryOperations {
}
~~~

Theo quy ước fragment, **PersonDirectoryOperationsImpl** là triển khai do lập trình viên cung cấp cho **PersonDirectoryOperations**. Spring Data tìm và ghép fragment này khi nó nằm trong phạm vi phát hiện phù hợp; hậu tố mặc định thường là **Impl**, và có thể được cấu hình. Trong ví dụ, **LdapTemplate.search** kết hợp các điều kiện **objectClass**, **cn** và **member** bằng filter builder, tránh ghép trực tiếp dữ liệu request vào filter. Phép kiểm tra chỉ áp dụng cho **thành viên trực tiếp** của groupOfNames; nó không tự suy ra thành viên nhóm lồng nhau hoặc quyền hiệu lực. Hãy thay base DN, mô hình nhóm và giới hạn định danh theo directory thật, sau đó kiểm thử với ACL/schema tương ứng.

**Không nhầm custom fragment với lớp PersonRepositoryImpl bắt buộc.** Với các phương thức CRUD và findByUid đơn giản, **không cần** class Impl; custom fragment chỉ dùng khi có hành vi riêng mà hạ tầng repository không cung cấp.

## 10. @NoRepositoryBean cho interface chung

Giả sử một module muốn khai báo interface nền cho các LDAP repository:

~~~java
package org.example.directory.repository;

import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseDirectoryRepository<T> extends LdapRepository<T> {
    // Các quy ước chung, không phải repository của một entry cụ thể.
}
~~~

~~~java
package org.example.directory.repository;

import org.example.directory.entry.PersonEntry;

public interface PersonRepository
        extends BaseDirectoryRepository<PersonEntry> {
}
~~~

**@NoRepositoryBean** đánh dấu **BaseDirectoryRepository** là interface nền, không cần tạo một proxy riêng từ generic **T** chưa được xác định. **PersonRepository** vẫn là repository cụ thể và được phát hiện bình thường. Không lạm dụng annotation này lên interface mà service cần inject trực tiếp.

## 11. Các lỗi scanning/bootstrap thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xác minh/khắc phục |
| --- | --- | --- |
| **No qualifying bean of type PersonRepository** | Repository nằm ngoài phạm vi scan; chưa bật repository support; thiếu dependency | Kiểm tra package của @SpringBootApplication, @EnableLdapRepositories và dependency |
| **Found 0 LDAP repository interfaces** | Base package quá hẹp/sai, interface không kế thừa repository phù hợp | Kiểm tra đường package thực và generic/interface |
| **BeanDefinitionOverrideException / duplicate bean** | Quét cùng repository nhiều lần hoặc trùng tên bean | Đặt một vùng scan rõ ràng, tránh cấu hình chồng |
| **Not a managed type / mapping error** | Entity thiếu @Entry/@Id, dùng sai annotation Id hoặc DN không phải Name | Kiểm tra ODM annotations của Spring LDAP |
| **PropertyReferenceException** | Tên method findBy... không khớp property trên entity | Kiểm tra Java property và ánh xạ @Attribute |
| **No bean named ldapTemplate / wiring error** | FactoryBean tìm LdapTemplate mặc định nhưng bean không có hoặc mang tên khác | Khai báo LdapTemplate, đặt đúng ldapTemplateRef |
| Có nhiều template mà truy vấn nhầm server | Repository được gắn với ContextSource khác mong đợi | Xác minh ldapTemplateRef, URL/base của bean thực |
| Bean repository tồn tại nhưng **PKIX/SSLHandshakeException** | LDAPS certificate chain/SAN không hợp lệ | Kiểm tra truststore, hostname, endpoint và TLS |
| Bean tồn tại nhưng **LDAP result 49** | Bind DN/password sai hoặc tài khoản bị hạn chế | Kiểm tra kết nối/xác thực riêng |
| **No such object (32)** khi findById | DN tương đối/base DN sai; entry hoặc parent không tồn tại | So DN đầy đủ với ContextSource base; kiểm tra cây LDAP |
| **Object class violation (65)** khi save | Thiếu cn/sn hoặc schema không chấp nhận objectClasses/thuộc tính | Kiểm tra MUST/MAY, schema và dữ liệu entry |
| **Insufficient access rights (50)** | Tài khoản không được phép đọc/ghi | Kiểm tra ACL và tách quyền read/write |

**Ba cấp lỗi cần phân biệt**:

1. **Scan/bean-definition:** Spring chưa tạo ra repository bean.
2. **Mapping/query bootstrap:** bean hoặc query không dựng được vì metadata Java/ODM không hợp lệ.
3. **LDAP runtime:** kết nối, TLS, bind, search base, ACL hoặc schema của directory khiến lời gọi thất bại.

Không sửa DN hoặc mật khẩu LDAP để giải quyết lỗi **No qualifying bean**; ngược lại, thêm **@EnableLdapRepositories** không sửa được certificate đã hết hạn hoặc attribute bắt buộc bị thiếu.

## 12. Debugging: quan sát repository được tạo và dùng đúng bean

### 12.1. Đọc log bootstrap

Trong môi trường phát triển, có thể bật mức log phù hợp:

~~~yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
    org.springframework.data.ldap: DEBUG
    org.springframework.ldap: INFO
~~~

Đối chiếu số lượng repository được phát hiện, package quét, lỗi tạo query và tên bean đã đăng ký. Khi cần chẩn đoán TLS, bật log JSSE tạm thời trong môi trường kiểm soát thay vì bật logging directory nhạy cảm toàn thời gian.

**Không bật log ghi credentials**, dữ liệu thuộc tính bí mật hoặc LDAP filter có thông tin cá nhân trong production. Log debug phải có hạn lưu trữ và quyền truy cập phù hợp.

### 12.2. Kiểm tra bean trong Spring context

Một bài test cho phần quét repository có thể kiểm tra bean đã được đăng ký:

~~~java
package org.example.directory;

import org.example.directory.repository.PersonRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class RepositoryBootstrapTest {
    @Autowired
    ApplicationContext context;

    @Autowired
    PersonRepository personRepository;

    @Test
    void repositoryBeanIsRegisteredOnce() {
        assertNotNull(personRepository);
        assertEquals(
            1,
            context.getBeanNamesForType(PersonRepository.class).length
        );
    }
}
~~~

Test trên xác minh **Spring tạo được repository bean**, không chứng minh LDAP server chấp nhận truy vấn. Tùy cấu hình, Spring context có thể cần bean ContextSource hợp lệ và có thể phát sinh kiểm tra kết nối sớm. Để kiểm chứng cả LDAP, cần một integration test riêng.

### 12.3. Kiểm thử với directory thật hoặc directory nhúng

Chuẩn bị fixture LDIF hợp lệ:

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

Nếu dùng server LDAP nhúng qua Spring Boot test support, hãy đọc tài liệu phiên bản về **spring.ldap.embedded.base-dn** và LDIF initialization; không cần test bằng một directory production. Directory nhúng và OpenLDAP/AD DS thực có thể khác schema, ACL, referral và quy tắc đặt tên, nên cần thêm integration test trên server tương đương đích.

Ví dụ test có kết nối LDAP thực:

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
class PersonRepositoryIntegrationTest {
    @Autowired
    PersonRepository repository;

    @Test
    void findsPersonByUidThroughGeneratedProxy() {
        List<PersonEntry> people = repository.findByUid("an");

        assertFalse(people.isEmpty());
        assertEquals("an", people.get(0).getUid());
    }
}
~~~

Test này yêu cầu dữ liệu **uid=an** đã được seed đúng và test profile cấu hình ContextSource thích hợp. Dùng fixture riêng cho từng ca; khi chạy test CRUD, nhớ xóa dữ liệu test sau khi hoàn thành. Không để tài khoản thử nghiệm có quyền sửa toàn bộ directory.

### 12.4. Ma trận kiểm thử quét và tạo triển khai

| Ca | Thay đổi có chủ đích | Kết quả cần kiểm tra |
| --- | --- | --- |
| Repo trong package được quét | PersonRepository nằm dưới base package | Có đúng một bean PersonRepository |
| Repo ngoài package | Dời package ra ngoài phạm vi scan trong fixture | Bean không được đăng ký hoặc injection thất bại như dự kiến |
| @EnableLdapRepositories đúng package | Chỉ định basePackageClasses | Repo được phát hiện |
| Config đặt trong package ngang cấp mà không có basePackages | Dùng @EnableLdapRepositories không tham số | Không tìm được repo ở package khác |
| Interface nền | BaseDirectoryRepository có @NoRepositoryBean | Không có bean riêng cho base, repo con vẫn chạy |
| Entity thiếu @Entry hoặc @Id | Thử fixture entity thiếu ODM metadata | Lỗi mapping/bootstrap được phát hiện |
| Sai tên derived query | Định nghĩa findByUnknownProperty | Query không được tạo hợp lệ |
| Nhiều LdapTemplate | Chọn ldapTemplateRef khác nhau cho các vùng scan | Truy vấn đi đúng directory |
| Thành công qua LDAP thật | Seed user, gọi findByUid | Nhận entity được ánh xạ đúng |
| Sai base DN | Cấu hình base khác fixture | Truy vấn không thấy entry hoặc nhận lỗi LDAP |
| TLS / ACL lỗi | Server certificate hoặc account quyền sai | Lời gọi tới directory thất bại an toàn |

## 13. Các hiểu nhầm thường gặp

**“Có @Repository trên interface thì Spring tự tạo LDAP repository.”** Chưa đủ. Hạ tầng Spring Data LDAP phải quét interface và đăng ký factory/proxy phù hợp; cách ổn định nhất là kế thừa **LdapRepository** và cấu hình scanning đúng.

**“@Entry tự động tạo bean repository.”** Không. **@Entry** chỉ mô tả entity LDAP để mapping; cần khai báo một repository interface nếu muốn truy cập qua repository.

**“Spring Boot luôn quét toàn bộ classpath.”** Không. Spring Boot dùng các package auto-configuration hoặc cấu hình tường minh. Repository nằm ngoài vùng đó có thể không được phát hiện.

**“Tên class phải là PersonRepositoryImpl để Spring Data chạy.”** Không. Phần triển khai cơ sở và query được dựng tự động. Hậu tố **Impl** chủ yếu liên quan tới custom implementation/fragment do bạn viết.

**“Được tạo bean nghĩa là kết nối LDAP thành công.”** Không. Bootstrap repository và network I/O LDAP là hai công đoạn; cần kiểm thử kết nối/bind/truy vấn thật.

**“LdapRepository<PersonEntry, Long> giống JPA.”** Không. LdapRepository của Spring Data LDAP nhận entity type và sử dụng **Name** làm ID theo cơ chế ODM.

**“Repository quét nhầm package có thể sửa bằng thêm LDAP filter.”** Không. Scan là việc của Spring classpath, không liên quan cú pháp LDAP filter.

**“Dùng cùng repository proxy sẽ tự đổi giữa hai LDAP server.”** Không. Repository được gắn với template/context đã cấu hình, trừ khi có một cơ chế định tuyến chủ động được thiết kế.

## 14. Tổng kết và câu hỏi tự luyện

**Cơ chế quét và tạo triển khai Repository** của Spring Data LDAP gồm: **phát hiện interface repository trong package cấu hình → đăng ký FactoryBean → khởi tạo repository proxy → ghép CRUD/query/custom fragments → sử dụng LdapTemplate/ContextSource để gọi LDAP**. Nhờ vậy, lập trình viên có thể khai báo **LdapRepository<PersonEntry>** mà không phải viết tất cả phương thức CRUD hoặc finder bằng tay.

Để cơ chế hoạt động đúng, phải hiểu **package scanning**, metadata **@Entry/@Id**, ID kiểu **Name**, cách cấu hình **ldapTemplateRef**, tên phương thức query, và sự khác nhau giữa lỗi bootstrap với lỗi runtime của directory. Vấn đề bảo mật vẫn áp dụng bình thường: kết nối **LDAPS/StartTLS** có xác minh certificate, tài khoản bind quyền tối thiểu, DN/filter an toàn và kiểm thử schema/ACL.

**Bài tập:**

1. Mô tả bằng sơ đồ đường đi từ **@SpringBootApplication** đến bean **PersonRepository**, và từ **findByUid** đến LDAP server.
2. Di chuyển **PersonRepository** ra package ngang cấp với class cấu hình. Dự đoán điều gì xảy ra nếu chỉ dùng **@EnableLdapRepositories** không tham số; sau đó sửa bằng **basePackageClasses**.
3. Giải thích vai trò riêng của **@Entry**, **@Id**, **LdapRepositoryFactoryBean** và **LdapTemplate**.
4. Tạo interface nền dùng **@NoRepositoryBean** và một repository con. Tại sao Spring không nên tạo bean cho interface nền generic?
5. Thêm **findByUnknownProperty** vào repository. Lỗi thuộc giai đoạn nào: classpath scan, mapping/query bootstrap hay LDAP runtime?
6. Khai báo hai **LdapTemplate** cho hai ContextSource khác nhau. Hãy thiết kế hai package repository không trùng vùng scan và dùng **ldapTemplateRef** đúng.
7. Dựng integration test với **uid=an**, chứng minh vừa có bean repository vừa chạy được **findByUid**, và nêu cách kiểm tra ACL/schema khi đổi sang server thật.
8. Vì sao không nên dùng **Page<PersonEntry>** trong Spring Data LDAP chỉ vì kiểu Page có sẵn ở Spring Data Commons?

### Tài liệu tham khảo

- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html) — @EnableLdapRepositories, LdapTemplate, ODM và kết nối bean.
- [Spring Data LDAP — Creating Repository Instances](https://docs.spring.io/spring-data/ldap/reference/repositories/create-instances.html) — scanning package, FactoryBean và proxy.
- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html) — derived queries, @Query và quy tắc parameter encoding.
- [Spring Data LDAP — Custom Repository Implementations](https://docs.spring.io/spring-data/ldap/reference/repositories/custom-implementations.html) — cách ghép custom fragment.
- [Spring Data LDAP — EnableLdapRepositories Javadoc](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/config/EnableLdapRepositories.html) — basePackages, basePackageClasses và ldapTemplateRef.
- [Spring Boot — Working with NoSQL Technologies: LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html) — auto-configuration và phạm vi scan repository.
- [Spring LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html) — đặc điểm của LdapRepository, ID kiểu Name và giới hạn theo LDAP protocol.
