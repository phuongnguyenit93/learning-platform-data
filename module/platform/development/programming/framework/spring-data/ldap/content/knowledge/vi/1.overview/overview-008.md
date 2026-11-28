# Lộ trình học và các kiến thức cần chuẩn bị

**Spring Data LDAP** giúp ứng dụng Java truy cập dịch vụ thư mục LDAP bằng mô hình repository và ánh xạ entry phân cấp thành đối tượng Java. Để học hiệu quả, người học cần kết hợp kiến thức Java, Spring, mô hình directory, giao thức LDAP, bảo mật kết nối và kiểm thử. Biết viết một câu lệnh search chưa đủ để xây một ứng dụng đáng tin cậy: ứng dụng còn phải hiểu **Distinguished Name (DN)**, **objectClass**, schema, search scope, LDAP filter, quyền bind, TLS và khác biệt giữa các directory server.

Bài tổng quan này xác định **kiến thức đầu vào**, **mục tiêu sau khóa học**, **trình tự học**, môi trường thực hành và một lộ trình dự án mẫu. Người học sẽ biết phần nào cần ôn trước, vì sao các chủ đề được sắp theo thứ tự đó, cách kiểm tra tiến độ và cách kết hợp `LdapRepository` với `LdapTemplate` trong ứng dụng Spring.

## 1. Spring Data LDAP giải quyết bài toán gì?

LDAP (Lightweight Directory Access Protocol) là giao thức truy cập dịch vụ thư mục. Directory thường lưu thông tin có cấu trúc phân cấp như người dùng, nhóm, đơn vị tổ chức, tài khoản dịch vụ và các thuộc tính liên quan.

Ví dụ cây directory:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001
│   └── uid=u1002
├── ou=groups
│   ├── cn=developers
│   └── cn=reviewers
└── ou=service-accounts
    └── cn=svc-reader
```

Một entry người dùng có thể được biểu diễn bằng LDIF:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an.nguyen@example.org
```

Trong đó:

- **DN** xác định vị trí entry trong cây.
- **RDN** là thành phần tên tương đối với entry cha, ở đây là `uid=u1001`.
- **objectClass** mô tả loại entry và các thuộc tính schema cho phép.
- **uid, cn, sn, mail** là LDAP attribute, không phải cột SQL.
- Một thuộc tính có thể không tồn tại hoặc chứa nhiều giá trị.
- Quyền đọc/ghi được directory server kiểm soát bằng bind identity và ACL.

Spring Data LDAP cung cấp abstraction repository và tích hợp Spring LDAP ODM để ánh xạ entry sang Java object. Spring LDAP còn cung cấp `LdapTemplate` cho search, lookup, CRUD và các thao tác cần kiểm soát chi tiết. Ứng dụng vẫn phải hiểu LDAP server và cấu hình đúng phạm vi, filter, bảo mật.

## 2. Mục tiêu sau module

Khi hoàn thành lộ trình, người học cần có khả năng:

1. Giải thích DIT, DN, RDN, naming context, attribute, `objectClass` và schema.
2. Phân biệt LDAP search base, scope, filter và các control như paging.
3. Cấu hình Spring Boot/Spring LDAP với `ContextSource`, `LdapTemplate` và thông tin kết nối được quản lý an toàn.
4. Ánh xạ LDAP entry sang Java entity bằng `@Entry`, `@Id`, `@Attribute` và các annotation ODM phù hợp.
5. Thiết kế repository kế thừa `LdapRepository<T>` cho các thao tác phổ biến.
6. Dùng `LdapTemplate` và filter builder khi cần truy vấn hoặc thao tác chi tiết.
7. Thực hiện CRUD đúng schema, hiểu giới hạn khi rename/move entry và xử lý thuộc tính đa trị.
8. Xây dựng xác thực search-then-bind hoặc tích hợp Spring Security LDAP phù hợp.
9. Bảo vệ kết nối bằng LDAPS/StartTLS, quản lý bind account và giới hạn ACL.
10. Xử lý referral, nhiều naming context, replication và khác biệt giữa LDAP server.
11. Thiết kế đồng bộ tăng dần, checkpoint, đối soát và xử lý xóa/đổi DN theo khả năng server.
12. Kiểm thử mapping, truy vấn, bảo mật, hiệu năng và hành vi lỗi với directory phù hợp.

Mục tiêu không phải ghi nhớ tên mọi class. Mục tiêu là **chọn đúng abstraction, biết dữ liệu được tìm ở đâu, biết ai có quyền đọc/ghi và chứng minh hệ thống hoạt động bằng kiểm thử**.

## 3. Kiến thức Java cần chuẩn bị

Bạn nên có nền tảng Java ở mức có thể đọc và tự viết một ứng dụng nhỏ.

| Chủ đề Java | Cần biết | Sẽ dùng ở đâu |
|---|---|---|
| Class, object, constructor | Khai báo entity, DTO, service | ODM entity và service |
| Interface và generic | Hiểu repository theo kiểu `LdapRepository<T>` | Repository abstraction |
| Annotation | Đọc và khai báo annotation | `@Entry`, `@Id`, `@Attribute` |
| Collections | `List`, `Set`, `Map`, xử lý nhiều giá trị | LDAP multi-valued attributes, batch |
| Exception | Checked/unchecked exception, try/finally | JNDI, lỗi LDAP, đóng context |
| Enum và record | Mô tả trạng thái, DTO | API và kết quả search |
| Stream/Lambda | Mapper, chuyển đổi collection | `AttributesMapper`, `ContextMapper` |
| Resource lifecycle | Quản lý tài nguyên | `DirContext` |
| String và encoding | Unicode, escaping, validation | LDAP filter, DN, dữ liệu đầu vào |

### Những kiểu Java thường gặp

Bạn sẽ gặp các kiểu từ JNDI và Spring LDAP:

- `javax.naming.Name`: biểu diễn tên có cấu trúc, thường dùng cho DN.
- `javax.naming.ldap.LdapName`: implementation LDAP của `Name`.
- `javax.naming.directory.Attributes`: tập LDAP attribute.
- `javax.naming.directory.Attribute`: một attribute, có thể đa trị.
- `javax.naming.directory.DirContext`: context thao tác directory.
- `Optional<T>`: biểu diễn kết quả có thể không tồn tại.
- `List<T>` và `Set<T>`: kết quả search và thuộc tính nhiều giá trị.

Lưu ý: `javax.naming` là API JNDI thuộc Java SE. Không đổi nó thành `jakarta.naming` khi chuyển sang Spring Framework 6/Spring Boot 3. Đồng thời, annotation `@Id` của Spring LDAP ODM khác `jakarta.persistence.Id` của JPA.

### Tự đánh giá đầu vào Java

Bạn đã sẵn sàng nếu có thể:

- Viết class có constructor, field, getter/setter và interface.
- Tạo `List<User>` và `Map<String, Set<String>>`.
- Xử lý exception khi một method gọi tài nguyên bên ngoài.
- Đọc một method nhận `Attributes` rồi chuyển thành DTO.
- Hiểu vì sao cần đóng `DirContext` trong `finally` hoặc cấu trúc quản lý tài nguyên tương đương.

Nếu còn yếu ở generic, collection hoặc exception, hãy ôn lại trước khi đi sâu vào ODM và các thao tác kết nối.

## 4. Kiến thức Spring cần chuẩn bị

Module giả định người học đã biết những thành phần Spring cơ bản:

- **Dependency Injection:** inject service, repository và template qua constructor.
- **Bean và configuration:** hiểu `@Configuration`, `@Bean`, `@Component` và lifecycle do Spring quản lý.
- **Spring Boot configuration:** đọc YAML/properties, profile và biến môi trường.
- **Repository abstraction:** hiểu interface repository và cách Spring tạo implementation.
- **Exception handling:** chuyển lỗi tầng directory thành lỗi nghiệp vụ phù hợp.
- **Testing:** dùng JUnit, Spring test context và mock khi phù hợp.

Một service có thể nhận repository qua constructor:

```java
import org.springframework.stereotype.Service;

@Service
public class DirectoryPeopleService {

    private final DirectoryPersonRepository repository;

    public DirectoryPeopleService(
            DirectoryPersonRepository repository) {
        this.repository = repository;
    }

    // Các nghiệp vụ tìm kiếm/đọc user sẽ được bổ sung
    // sau khi repository và LDAP context đã được cấu hình.
}
```

Không cần biết toàn bộ Spring Security hoặc mọi module Spring trước khi bắt đầu. Tuy nhiên, nếu ứng dụng dùng LDAP để đăng nhập, bạn cần hiểu authentication khác authorization và nên học phần Spring Security LDAP trong giai đoạn bảo mật.

## 5. Kiến thức LDAP cần chuẩn bị

Đây là phần nền tảng chuyên ngành quan trọng nhất. Trước khi học repository, cần nắm các khái niệm sau.

### 5.1 Directory Information Tree và DN

Directory được tổ chức thành cây. Mỗi entry có DN, gồm các RDN theo đường từ entry lên parent/root.

```text
uid=u1001,ou=people,dc=example,dc=org
└──── RDN ────┘└──── parent path ──────┘
```

Bạn cần phân biệt:

- DN đầy đủ với DN tương đối theo context base.
- RDN với LDAP attribute có cùng tên.
- DN hiện tại với định danh nghiệp vụ ổn định.
- Rename/move làm thay đổi DN như thế nào.

### 5.2 Attribute và objectClass

Một entry có các attribute như `uid`, `cn`, `sn`, `mail`. Các object class như `person` và `inetOrgPerson` quy định cấu trúc entry theo schema. Một attribute có thể là bắt buộc, tùy chọn hoặc đa trị.

### 5.3 Schema và matching rule

Schema định nghĩa syntax, object class, MUST/MAY attribute và matching rule. Ví dụ filter equality hoặc substring chỉ hoạt động theo quy tắc của attribute và server. Một biểu thức Java so sánh chuỗi không tự động có cùng ngữ nghĩa với LDAP matching rule.

### 5.4 Search base, scope và filter

Một LDAP search thường cần ba thành phần:

```text
Base DN:  ou=people,dc=example,dc=org
Scope:    SUBTREE
Filter:   (&(objectClass=inetOrgPerson)(uid=u1001))
```

- **Base DN:** điểm bắt đầu tìm kiếm.
- **Scope:** tìm chính entry, con trực tiếp hay toàn cây con.
- **Filter:** điều kiện chọn entry theo cú pháp LDAP.

Cần hiểu AND, OR, NOT, presence, equality, substring và cách escape giá trị. Không nối chuỗi raw filter từ input người dùng.

### 5.5 Bind và ACL

LDAP bind xác lập danh tính của kết nối. ACL quyết định danh tính đó có quyền search, read, add, modify hay delete entry/attribute nào. Biết DN không đồng nghĩa có quyền đọc; search thành công không đồng nghĩa bind password của người dùng đã đúng.

## 6. Kiến thức mạng và bảo mật cần chuẩn bị

LDAP là giao thức mạng. Người học nên biết:

- DNS và hostname của LDAP server.
- TCP connection, port và timeout.
- Chứng chỉ X.509, CA, truststore và hostname verification.
- TLS handshake và sự khác nhau giữa LDAPS với StartTLS.
- Secret management và nguyên tắc least privilege.
- Authentication, authorization, session và audit.
- Network segmentation, firewall và khả năng kết nối tới domain controller.

Một số cổng thường gặp:

| Dịch vụ | Cổng mặc định thường gặp | Ghi chú |
|---|---:|---|
| LDAP | 389 | Có thể nâng cấp bằng StartTLS nếu server/client cấu hình |
| LDAPS | 636 | TLS ngay từ đầu kết nối |
| Global Catalog LDAP (AD) | 3268 | Tìm kiếm GC, có giới hạn attribute |
| Global Catalog LDAPS (AD) | 3269 | GC qua TLS |

Đây là các cổng phổ biến, không phải bảo đảm server của bạn sử dụng chúng. Hãy xác nhận endpoint thực tế với quản trị directory.

**Không thực hành SIMPLE bind với mật khẩu thật trên kết nối LDAP cleartext.** Dùng directory thử nghiệm và LDAPS/StartTLS có xác minh chứng chỉ. Không tắt kiểm tra certificate chỉ để làm cho kết nối thành công.

## 7. Môi trường thực hành cần có

Một môi trường học tập tối thiểu gồm:

1. JDK phù hợp với phiên bản Spring Boot/Spring LDAP của project.
2. IDE hoặc editor hỗ trợ Java.
3. Maven hoặc Gradle.
4. LDAP test server có thể khởi động/dừng và nạp LDIF.
5. LDAP client như `ldapsearch`/`ldapwhoami` hoặc công cụ quản trị tương đương.
6. Truststore/CA test để luyện LDAPS hoặc StartTLS.
7. JUnit và thư viện kiểm thử tương thích với dependency đã chọn.

### Chọn LDAP server cho lab

Có thể dùng OpenLDAP trong container hoặc một directory test chuyên dụng. Nếu học Active Directory, nên có lab AD riêng để kiểm chứng `objectClass`, `sAMAccountName`, `objectGUID`, `memberOf`, Global Catalog và các giới hạn đặc thù.

Không nên coi một embedded/mock LDAP server là đại diện đầy đủ cho mọi sản phẩm. Nó hữu ích cho test mapping và CRUD cơ bản; referral, replication, ACL, password policy và AD controls cần môi trường phù hợp hơn.

### Dữ liệu LDIF ban đầu

Ví dụ tối giản để dựng nhánh test (schema/server phải hỗ trợ các object class này):

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an@example.org
```

LDIF này chỉ là dữ liệu minh họa cho lab. Một số server có schema mặc định khác nhau; entry phải thỏa schema của server và giá trị password test phải được thiết lập theo cơ chế an toàn của server.

## 8. Chuẩn bị project Spring Boot

Khi tạo project, chọn dependency phù hợp với Spring Boot và Spring Data LDAP mà ứng dụng sẽ sử dụng. Với Spring Boot, có thể bắt đầu từ starter quản lý LDAP thay vì tự ghim các version rời rạc.

Ví dụ dependency Maven minh họa:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
```

Nếu project không dùng Spring Boot dependency management, cần quản lý version tương thích cho Spring Data LDAP, Spring LDAP và các dependency liên quan. **Không ghép ngẫu nhiên version** của Spring Data Commons, Spring LDAP và Querydsl.

Ví dụ cấu hình kết nối bằng biến môi trường:

```yaml
spring:
  ldap:
    urls: ldaps://localhost:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Các giá trị này chỉ là mẫu. Hãy đặt URL, base DN, bind DN và secret theo directory test. Không lưu password thật trong repository Git. Với nhiều môi trường, dùng profile và secret manager phù hợp.

## 9. Lộ trình học đề xuất

Học theo thứ tự sau để mỗi phần xây trên kiến thức đã có:

1. **Nền tảng directory và giao thức LDAP.** Học DIT, DN/RDN, naming context, attribute, objectClass, schema, bind, search base/scope/filter. Thực hành đọc LDIF và dùng LDAP client để search một entry.
2. **Cấu hình Spring LDAP.** Tạo `ContextSource`, `LdapTemplate`, cấu hình base DN, bind account, timeout và môi trường kết nối. Kiểm tra kết nối trước khi viết repository.
3. **Entity mapping và ODM.** Khai báo `@Entry`, `@Id Name`, `@Attribute`, hiểu DN tương đối và đa trị. Đọc một entry thành Java object và đối chiếu từng field.
4. **Repository và truy vấn.** Tạo `LdapRepository<T>`, query method, `findById`, search theo thuộc tính. Phân biệt query derivation với filter builder và kiểm chứng API theo version.
5. **LdapTemplate và CRUD.** Dùng `LdapTemplate` khi cần base/scope/filter, mapper, modify attribute, rename hoặc thao tác chi tiết. Hiểu schema, parent DN và quyền ghi.
6. **TLS, bind authentication và Spring Security LDAP.** Cấu hình LDAPS/StartTLS, tìm DN rồi bind, xử lý mật khẩu rỗng, phân loại lỗi và tách authentication khỏi authorization.
7. **Topology, referral và khác biệt server.** Học naming context, replication, referral, RootDSE, AD Global Catalog, ACL và cách truy vấn nhiều nguồn có kiểm soát.
8. **Đồng bộ, hiệu năng và vận hành.** Học incremental sync, checkpoint, reconciliation, connection pool, tránh N+1, paging, metrics và giới hạn server.
9. **Kiểm thử và dự án tổng hợp.** Viết unit/integration test, kiểm tra TLS/ACL, injection, lỗi server và hiệu năng; hoàn thành một dịch vụ directory có thể chạy trong lab.

Thứ tự trên là lộ trình khuyến nghị, không bắt buộc mọi dự án phải triển khai tất cả tính năng. Nếu ứng dụng chỉ đọc danh bạ nội bộ, phần replication hoặc đồng bộ nâng cao có thể học sau; nếu làm xác thực nhiều domain, topology và bảo mật cần được ưu tiên sớm.

## 10. Những câu hỏi cần trả lời trước khi viết code

Trước khi tạo entity hoặc repository, hãy thu thập các thông tin sau từ directory owner hoặc cấu hình môi trường:

| Câu hỏi | Vì sao quan trọng |
|---|---|
| LDAP server là sản phẩm/version nào? | Xác định schema, controls, referral, matching rule |
| Endpoint và TLS mode là gì? | Kết nối đúng và bảo vệ credentials |
| Naming context/base DN là gì? | Tránh search sai cây hoặc mở rộng phạm vi |
| User/group nằm ở OU nào? | Chọn search base và scope |
| Login attribute là `uid`, `cn`, `sAMAccountName` hay UPN? | Không suy luận schema từ username |
| Object class nào được dùng? | Entity/filter phải khớp server |
| Attribute nào bắt buộc/tùy chọn/đa trị? | Mapping và validation chính xác |
| Service account có ACL nào? | Biết thao tác được phép |
| Có nhiều domain/replica/referral không? | Chọn topology và consistency policy |
| Số lượng entry và giới hạn search? | Thiết kế paging, index, timeout |
| Cần đồng bộ hay chỉ đọc trực tiếp? | Chọn nguồn dữ liệu và checkpoint |
| Ai sở hữu dữ liệu? | Tránh ghi đè hoặc đồng bộ sai chiều |

Không đưa password, private key, token hoặc dữ liệu cá nhân thật vào tài liệu học, ticket hoặc log. Với thông tin chưa biết, ghi là **chưa xác nhận** và yêu cầu chủ sở hữu directory cung cấp.

## 11. Chọn đúng công cụ: Repository, ODM hay LdapTemplate?

Ba abstraction thường dùng cùng nhau nhưng giải quyết các nhu cầu khác nhau:

| Công cụ | Khi nên dùng | Ví dụ |
|---|---|---|
| **Spring Data LDAP ODM** | Mô tả mapping giữa LDAP entry và Java entity | `@Entry`, `@Id`, `@Attribute` |
| **LdapRepository<T>** | CRUD và truy vấn repository quen thuộc | `findByUid`, `findById(Name)` |
| **LdapTemplate** | Truy vấn động, mapper riêng, thao tác LDAP chi tiết | `search`, `lookup`, `authenticate`, `modifyAttributes` |

Ví dụ entity:

```java
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
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
```

Service có thể dùng repository cho truy vấn cố định và `LdapTemplate` cho tìm kiếm động hoặc một operation đặc thù. Không nên ép mọi thao tác vào repository nếu điều đó làm mất kiểm soát scope, filter, thuộc tính và lỗi.

## 12. Cách học filter và DN an toàn

Đây là kỹ năng phải có trước khi xây endpoint nhận dữ liệu từ người dùng.

**LDAP filter** và **DN** có cú pháp escaping khác nhau. Không dùng một hàm escape cho cả hai.

Filter equality:

```java
import org.springframework.ldap.filter.EqualsFilter;

String safeFilter =
        new EqualsFilter("uid", userInput).encode();
```

DN builder:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name userDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", userInput)
        .build();
```

Quy tắc:

- Tên attribute và base DN nên do ứng dụng cấu hình/allowlist kiểm soát.
- Giá trị người dùng nhập phải được escape theo đúng ngữ cảnh filter hoặc DN.
- Không nhận raw LDAP filter hoặc arbitrary base DN từ HTTP request.
- Giới hạn độ dài và ký tự theo quy tắc nghiệp vụ.
- Dùng scope nhỏ nhất đáp ứng yêu cầu.
- Đặt timeout/size limit và xử lý kết quả bị cắt.
- Kiểm thử ký tự `*`, `(`, `)`, backslash, Unicode và trường hợp rỗng.

Escaping ngăn dữ liệu đầu vào thay đổi cú pháp; nó **không cấp quyền** cho người gọi truy cập entry. Authorization và ACL vẫn phải được kiểm tra độc lập.

## 13. Kiểm thử là một phần của lộ trình, không phải bước cuối cùng

Nên kiểm thử theo tầng:

| Loại test | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test | Logic validation, DN/filter builder, mapper | Escape username, build DN |
| Repository test | Mapping ODM và query method | `findByUid`, `findById` |
| Integration test | Kết nối và hành vi LDAP thật | Search, add, modify, delete |
| Security test | Bind, TLS, ACL, injection | Password sai, empty password, cert sai |
| Topology test | Referral, nhiều NC, replica | Partial result, failover |
| Performance test | Số operations và latency | Tránh N+1, paging, pool |

Mock hữu ích cho unit test, nhưng không chứng minh directory server hỗ trợ schema, matching rule, referral, control hoặc password policy. Các tính năng đặc thù phải được kiểm thử trên đúng loại server/phiên bản mục tiêu.

### Checklist test cơ bản

- DN tương đối và đầy đủ được xử lý đúng theo context base.
- Entry thiếu attribute tùy chọn không làm mapper lỗi ngoài dự kiến.
- Thuộc tính đa trị không bị mất phần tử.
- Search scope không vượt OU được duyệt.
- Username có ký tự đặc biệt không gây LDAP injection.
- Service account chỉ đọc không thể thực hiện modify/delete.
- Bind sai mật khẩu và bind với mật khẩu rỗng đều thất bại.
- TLS certificate không hợp lệ làm kết nối thất bại an toàn.
- Search bị size/time limit không bị coi là kết quả đầy đủ.
- Rename/move không làm cache hoặc khóa DN bị dùng sai.

## 14. Lộ trình thực hành theo từng giai đoạn

Một kế hoạch học có thể chia thành năm giai đoạn. Thời lượng dưới đây là **ước lượng**, phụ thuộc nền tảng Java/Spring và thời gian lab.

| Giai đoạn | Nội dung | Sản phẩm cần hoàn thành |
|---|---|---|
| 1. Nền tảng | Java, Spring DI, LDAP tree, DN, schema, filter | Vẽ DIT và đọc/viết LDIF test |
| 2. Kết nối và mapping | ContextSource, LdapTemplate, ODM | Đọc một entry thành Java entity |
| 3. Repository và CRUD | LdapRepository, query, create/modify/delete | Service quản lý user trong OU test |
| 4. Bảo mật và topology | TLS, bind, ACL, referral, multi-domain | Đăng nhập test và xử lý lỗi an toàn |
| 5. Vận hành và tổng hợp | Sync, paging, performance, integration test | Dịch vụ directory có kiểm thử và quan sát |

### Ví dụ lịch học 5 buổi

- **Buổi 1:** đọc LDIF, xác định DN/RDN, schema, objectClass và thực hành search bằng LDAP client.
- **Buổi 2:** tạo Spring Boot project, cấu hình context source và đọc entry bằng LdapTemplate.
- **Buổi 3:** khai báo ODM entity, repository và triển khai CRUD trong OU test.
- **Buổi 4:** cấu hình TLS, bind authentication, ACL và test injection.
- **Buổi 5:** viết integration test, đo LDAP operations, xử lý paging/referral theo phạm vi dự án.

Nếu mới học LDAP, hãy dành thêm thời gian cho buổi 1. Nếu đã vận hành AD/OpenLDAP, có thể rút ngắn phần cơ bản và tập trung vào Spring mapping, security và test.

## 15. Dự án tổng hợp đề xuất

Một bài tập xuyên suốt là xây dựng **Directory People Service** với các chức năng:

1. Tìm một người dùng theo login attribute trong OU được duyệt.
2. Đọc thông tin cơ bản: UID, tên hiển thị, email.
3. Tạo và cập nhật một user trong directory test với quyền phù hợp.
4. Đọc nhóm trực tiếp của user theo schema thực tế.
5. Kiểm tra thông tin đăng nhập bằng bind authentication.
6. Từ chối filter injection và password rỗng.
7. Trả lỗi rõ ràng khi LDAP server timeout hoặc TLS thất bại.
8. Ghi metric số LDAP search và latency.
9. Có test cho thuộc tính thiếu, đa trị, rename/move và ACL.
10. Viết tài liệu triển khai gồm endpoint, base DN, schema, TLS, quyền bind và quy trình vận hành.

### Sơ đồ kiến trúc mục tiêu

```text
HTTP API
   │
   ▼
Application Service
   │
   ├── DirectoryPersonRepository
   │       │
   │       └── ODM mapping
   │
   ├── LdapTemplate
   │       └── Search/filter/modify operations
   │
   └── Authentication component
           └── Search DN + user bind
                   │
                   ▼
              ContextSource
                   │
             LDAPS / StartTLS
                   │
                   ▼
               LDAP Server
            schema + ACL + DIT
```

Tách service nghiệp vụ khỏi chi tiết LDAP để có thể test dễ hơn. Không để controller tự ghép DN hoặc filter. Không trả toàn bộ LDAP attributes ra API; chuyển thành DTO chỉ chứa dữ liệu được phép.

## 16. Tiêu chí hoàn thành module

Bạn có thể coi mình đã đạt mục tiêu khi tự làm được các việc sau mà không phải sao chép mù quáng ví dụ:

- [ ] Giải thích DN, RDN, naming context, objectClass và schema bằng một cây directory cụ thể.
- [ ] Viết LDIF hợp lệ theo schema của LDAP test server.
- [ ] Cấu hình Spring LDAP với endpoint, base, bind identity và TLS.
- [ ] Tạo entity ODM có `@Entry`, `@Id Name` và `@Attribute` đúng.
- [ ] Viết repository và phân biệt tìm theo DN với tìm theo thuộc tính.
- [ ] Dùng LdapTemplate/filter builder cho search và thao tác chi tiết.
- [ ] Giải thích khác biệt giữa filter escaping và DN escaping.
- [ ] Thực hiện search-then-bind an toàn và phân biệt authentication với authorization.
- [ ] Nhận diện referral, partial result, naming context và replication lag.
- [ ] Chọn cách đồng bộ hoặc đối soát phù hợp với khả năng server.
- [ ] Đo và giảm LDAP operations không cần thiết, đặc biệt N+1.
- [ ] Viết integration test chứng minh schema, ACL, TLS và kết quả query.
- [ ] Biết dừng lại và hỏi directory owner khi chưa rõ schema, base DN hoặc quyền.

## 17. Những lỗi học tập thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| DN giống username | Username là giá trị đăng nhập; DN là tên entry trong cây |
| `uid` luôn duy nhất | Uniqueness phụ thuộc schema, scope và quy tắc nghiệp vụ |
| `@Id` là `Long` như JPA | LDAP ODM thường dùng `javax.naming.Name` để giữ DN |
| `@Entry` tạo objectClass trên server | Annotation mô tả mapping; server schema vẫn phải tồn tại |
| Repository tự xử lý mọi filter | Query capability phụ thuộc module/version và server |
| LDAP search giống SQL JOIN | LDAP filter tìm entry; liên kết DN cần xử lý riêng |
| SUBTREE tìm cả forest | Scope chỉ áp dụng trên dữ liệu server phục vụ |
| Replica luôn có dữ liệu mới nhất | Replication có thể trễ |
| Referral là replica | Referral là chỉ dẫn sang endpoint khác |
| Search thấy user nghĩa là password đúng | Phải bind bằng DN người dùng và credential |
| HTTPS bảo vệ LDAP phía sau | Kết nối ứng dụng–LDAP cũng cần TLS |
| Kết quả rỗng nghĩa entry không tồn tại | Có thể do ACL, base/scope, timeout hoặc kết quả từng phần |
| Tăng pool giải quyết N+1 | Cần giảm số LDAP operations trước |
| Mock pass chứng minh server thật hỗ trợ | Cần integration test với server/schema phù hợp |

## 18. Cách sử dụng tài liệu và ví dụ trong module

Trong từng bài:

1. Đọc mục tiêu và các thuật ngữ trước khi chạy code.
2. Xác nhận version dependency của project đang dùng.
3. Đối chiếu tên attribute/objectClass với directory test.
4. Chạy ví dụ trong môi trường test, không copy endpoint hoặc secret production.
5. Đọc cả phần giới hạn và lỗi thường gặp, không chỉ phần code thành công.
6. Viết thêm một test âm: input sai, quyền thiếu, DN sai, server lỗi hoặc kết quả bị giới hạn.
7. Ghi lại hành vi khác nhau giữa server của bạn và ví dụ trong bài.

Các ví dụ trong module dùng naming context giả lập như `dc=example,dc=org` và OU `people`/`groups`. Đây là dữ liệu minh họa, không phải cấu hình mặc định của mọi LDAP server. Đối với Active Directory, cần điều chỉnh object class, login attribute, DN, group membership và các control đặc thù.

## 19. Tài liệu nền tảng nên tham khảo

Khi cần kiểm tra hành vi ở mức giao thức hoặc API, ưu tiên tài liệu chính thức:

- [RFC 4511 — Lightweight Directory Access Protocol: The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513).
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515).
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/).
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/).
- [Spring Security LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html).
- [Microsoft Learn — Active Directory Domain Services](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/).

Tài liệu và API có thể thay đổi theo phiên bản. Khi một method hoặc tính năng được dùng trong dự án, hãy mở reference/Javadoc của **đúng version đã resolve**, đồng thời chạy test xác nhận.

## 20. Checklist chuẩn bị trước khi bắt đầu

- [ ] Tôi có thể viết và đọc class/interface Java, generic và collection.
- [ ] Tôi hiểu Spring DI, bean configuration, repository và application properties.
- [ ] Tôi phân biệt được DN, RDN, attribute, objectClass và schema.
- [ ] Tôi hiểu base DN, search scope và LDAP filter.
- [ ] Tôi biết bind identity và ACL có vai trò gì.
- [ ] Tôi có LDAP test server và dữ liệu LDIF giả lập.
- [ ] Tôi biết cách kết nối bằng LDAPS/StartTLS và xác minh certificate.
- [ ] Tôi có JUnit và môi trường integration test.
- [ ] Tôi biết endpoint, base, schema và quyền nào cần hỏi directory owner.
- [ ] Tôi hiểu ví dụ phải được điều chỉnh theo server/version thực tế.

**Kết luận:** để học **Spring Data LDAP** vững chắc, hãy bắt đầu từ Java và Spring cơ bản, tiếp theo nắm cây directory, DN, schema, filter và bind, rồi mới học ODM, repository, `LdapTemplate`, bảo mật, topology, đồng bộ và hiệu năng. Thứ tự này giúp bạn hiểu cả **cách Spring ánh xạ entry** lẫn **những gì LDAP server thực sự cho phép**. Hoàn thành dự án tổng hợp và integration test trên directory phù hợp là dấu hiệu tốt nhất cho thấy bạn đã sẵn sàng áp dụng kiến thức vào một ứng dụng thực tế.
