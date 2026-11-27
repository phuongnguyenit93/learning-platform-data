# Áp dụng ODM và repository cho một mô hình danh bạ

## 1. Bài toán thực hành và kết quả cần đạt

Trong **Spring LDAP**, ta có thể truy cập thư mục qua `LdapTemplate` và tự viết `AttributesMapper`/`ContextMapper` cho từng truy vấn. Khi ứng dụng phải quản lý nhiều đối tượng có cùng cấu trúc, **Object-Directory Mapping (ODM)** giúp ánh xạ LDAP entry thành Java object; **Spring Data LDAP repository** cung cấp giao diện truy vấn và thao tác lưu trữ dựa trên entity đó.

Ở bài **Thực hành tổng hợp** này, ta xây dựng một **danh bạ nội bộ** có khả năng:

1. Tạo contact thuộc nhánh `ou=people` với `uid` duy nhất, họ, tên hiển thị và email.
2. Tra cứu contact theo `uid` hoặc họ `sn`.
3. Đọc danh sách ở một phạm vi phù hợp; cập nhật email/số điện thoại.
4. Xóa contact theo quy trình có kiểm soát.
5. Kiểm thử schema, DN, ODM mapping, repository, lỗi LDAP và an toàn kết nối.

Ví dụ dùng tên miền `example.org`, tài khoản và dữ liệu giả. Đây là **mô hình LDAP thử nghiệm**, không phải khuyến nghị cho phép ghi trực tiếp lên thư mục nhân sự đang vận hành. Các thao tác CRUD phải được giới hạn theo ACL, chính sách danh tính và quy trình cấp quyền của tổ chức.

### Những kết quả học tập

- Phân biệt **DN**, **objectClass**, **LDAP attribute** và **Java field**.
- Khai báo entity bằng `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và `@Transient` của Spring LDAP.
- Định nghĩa `LdapRepository<T>` và bật repository scanning.
- Dùng repository trong service thay vì phát sinh raw LDAP filter từ chuỗi input.
- Hiểu sự khác nhau giữa `repository.save(...)` và các API ODM `ldapTemplate.create/update/delete`.
- Viết kiểm thử tích hợp bảo đảm dữ liệu tạo ra được đọc lại và cleanup đúng.

## 2. Kiến trúc danh bạ và ranh giới các tầng

~~~mermaid
flowchart TD
    HTTP["REST / tác vụ nghiệp vụ"] --> Service["DirectoryContactService"]
    Service --> Repo["ContactRepository extends LdapRepository"]
    Repo --> Mapping["Spring Data LDAP + ODM mapper"]
    Mapping --> Template["LdapTemplate"]
    Template --> Source["LdapContextSource"]
    Source --> TLS["JSSE / LDAPS / StartTLS"]
    TLS --> Directory["LDAP server: ou=people"]
    Entity["@Entry DirectoryContact"] --> Mapping
    Schema["LDAP objectClass / attributes / DN"] --> Directory
~~~

**Phân tách trách nhiệm:**

| Tầng | Công việc |
| --- | --- |
| LDAP server | Lưu cây DN, áp dụng schema, uniqueness/constraint và ACL |
| `LdapContextSource` | Quản lý endpoint, base DN, bind identity và chiến lược kết nối |
| `LdapTemplate` / ODM | Thực hiện LDAP operation và ánh xạ entry thành Java object |
| `LdapRepository<DirectoryContact>` | Cung cấp CRUD và query methods cho entity ODM |
| Service | Kiểm tra input, giới hạn nghiệp vụ, gọi repository, xử lý lỗi |
| API / Controller | Xác thực và phân quyền người gọi, dùng DTO, không trả bí mật/LDAP internals |

**ODM không thay đổi schema LDAP.** Đổi tên Java field không tự tạo attribute mới trên server; thêm annotation không tự tạo nhánh `ou=people` hoặc ACL. Repository không biến LDAP thành cơ sở dữ liệu quan hệ có transaction đa entry, foreign key hoặc phân trang mặc định.

## 3. Thiết kế cây LDAP và schema cho danh bạ

Ta chọn suffix của thư mục và nhánh chứa entry như sau:

~~~text
dc=example,dc=org                 <-- suffix/base của ContextSource
└── ou=people
    ├── uid=contact.a
    └── uid=contact.b
~~~

DN đầy đủ của một contact:

~~~text
uid=contact.a,ou=people,dc=example,dc=org
~~~

Trong cấu hình ứng dụng, `spring.ldap.base` là `dc=example,dc=org`. Với entity dùng `@Entry(base = "ou=people")`, đường nhánh của entity được hiểu **tương đối** theo base DN của nguồn kết nối. Trước khi triển khai, hãy kiểm chứng DN thực sự được ODM tạo ra từ phiên bản thư viện đang dùng.

### 3.1. Chọn objectClass

Sử dụng những object class phổ biến theo schema **inetOrgPerson**:

| Object class | Vai trò chính |
| --- | --- |
| `top` | Lớp nền của nhiều đối tượng LDAP |
| `person` | Thường yêu cầu `cn` và `sn` |
| `organizationalPerson` | Mở rộng thông tin cá nhân/tổ chức |
| `inetOrgPerson` | Có thể bổ sung các attribute như `uid`, `mail`, `telephoneNumber` |

Các thuộc tính danh bạ trong ví dụ:

| LDAP attribute | Java property | Kiểu gợi ý | Quy ước nghiệp vụ |
| --- | --- | --- | --- |
| `uid` | `uid` | `String` | Không rỗng, không đổi trong bài tập, dùng trong RDN |
| `cn` | `displayName` | `String` | Bắt buộc theo schema `person` |
| `sn` | `familyName` | `String` | Bắt buộc theo schema `person` |
| `mail` | `email` | `String` | Tùy chọn theo schema, bắt buộc theo yêu cầu ứng dụng nếu cần |
| `telephoneNumber` | `phone` | `String` | Tùy chọn |
| DN | `dn` | `javax.naming.Name` | Danh tính entry trong cây LDAP |

Mỗi thuộc tính LDAP có cú pháp, quy tắc so khớp và khả năng đa trị theo schema server. Bài tập chọn đơn trị cho `mail`/`telephoneNumber` để đơn giản hóa; khi làm trên thư mục thật, phải điều chỉnh model theo schema và chính sách dữ liệu hiện hữu.

### 3.2. LDIF mẫu để chuẩn bị môi trường lab

Sau khi suffix `dc=example,dc=org` đã được khởi tạo bởi quản trị viên lab, có thể tạo nhánh `ou=people`:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
~~~

Một entry thử nghiệm:

~~~ldif
dn: uid=contact.a,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: contact.a
cn: Contact Alpha
sn: Alpha
mail: contact.alpha@example.org
telephoneNumber: +1 555 0100
~~~

Những LDIF trên là **dữ liệu minh họa**, không phải script cần chạy trên production. Người quản trị lab phải bảo đảm suffix, parent entry, schema và quyền ghi đã tồn tại. Không chèn hai entry có cùng DN; LDAP phân biệt entry theo DN trong cùng naming context.

## 4. Chuẩn bị ứng dụng Spring Boot và kết nối LDAP

### 4.1. Thêm dependency đúng

Với dự án Spring Boot dùng dependency management tương thích, có thể khai báo:

~~~groovy
// build.gradle — minh họa phần dependency
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-data-ldap` cung cấp những dependency liên quan Spring LDAP và Spring Data LDAP để dùng repository. Nếu dự án chỉ có `spring-ldap-core` mà thiếu phần Spring Data LDAP, khai báo `LdapRepository` chưa đủ để hệ thống tự tạo repository bean. Cần dùng một bộ phiên bản **Spring Boot, Spring LDAP và Spring Data LDAP tương thích** với nền tảng dự án.

### 4.2. Kết nối bảo mật và base DN

~~~yaml
# application.yml
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: cn=directory-editor,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Ở đây:

- `ldaps://` yêu cầu TLS ngay từ đầu kết nối.
- `base` là suffix được định nghĩa cho `LdapContextSource`.
- `username` và `password` chỉ dành cho **tài khoản lab** có quyền thao tác giới hạn trong `ou=people`.
- Biến môi trường `${LDAP_BIND_PASSWORD}` tránh ghi mật khẩu vào repository mã nguồn.

Ứng dụng phải xác minh **certificate chain và SAN/hostname** của server qua truststore Java thích hợp. Có thể truyền các thuộc tính JVM `javax.net.ssl.trustStore` và `javax.net.ssl.trustStoreType` khi dùng JSSE mặc định, nhưng phải kiểm tra ảnh hưởng tới các kết nối TLS khác trong JVM. Không tắt certificate validation để làm bài lab chạy nhanh.

Nếu hệ thống dùng StartTLS thay LDAPS, cần một `LdapContextSource`/authentication strategy **thực sự nâng cấp TLS trước simple bind**; chỉ thay URL thành `ldap://` không bảo đảm an toàn.

### 4.3. Repository scanning

Spring Boot có thể tự phát hiện repository trong các package ứng dụng. Khi muốn xác định rõ phạm vi quét, khai báo:

~~~java
package com.example.directory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@SpringBootApplication
@EnableLdapRepositories(basePackages = "com.example.directory.repo")
public class DirectoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectoryApplication.class, args);
    }
}
~~~

Trong dự án Boot thông thường, auto-configuration cũng tạo `LdapContextSource` và `LdapTemplate` từ `spring.ldap.*`. Nếu dự án đã tự khai báo bean hoặc có nhiều LDAP endpoints, phải đảm bảo repository dùng **đúng `LdapTemplate`**, source và bind identity mong muốn. Tránh giữ đồng thời hai cấu hình `ContextSource` mâu thuẫn rồi tin rằng repository sẽ tự chọn endpoint an toàn.

## 5. Tạo entity ODM DirectoryContact

Ví dụ sau dùng các annotation trong package **`org.springframework.ldap.odm.annotations`**, không dùng `@Id` của Spring Data JPA hoặc Spring Data Commons. LDAP định danh entry bằng **DN**, nên `@Id` đặt trên field kiểu `javax.naming.Name`.

~~~java
package com.example.directory.model;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    },
    base = "ou=people"
)
public class DirectoryContact {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String displayName;

    @Attribute(name = "sn")
    private String familyName;

    @Attribute(name = "mail")
    private String email;

    @Attribute(name = "telephoneNumber")
    private String phone;

    @Transient
    private String displayLabel;

    public DirectoryContact() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getFamilyName() { return familyName; }
    public void setFamilyName(String familyName) {
        this.familyName = familyName;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }

    public String getDisplayLabel() { return displayLabel; }
    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }
}
~~~

### 5.1. Ý nghĩa các annotation

| Annotation | Tác dụng trong ví dụ | Lỗi hay gặp |
| --- | --- | --- |
| `@Entry(objectClasses=..., base=...)` | Khai báo các objectClass và nhánh chứa contact | Thiếu object class chứa attribute được ghi; nhánh base không tồn tại |
| `@Id` | Đánh dấu DN của entry, kiểu `Name` | Dùng `Long`/`String` như khóa quan hệ hoặc import nhầm `@Id` |
| `@Attribute(name="cn")` | Ánh xạ `displayName` của Java với LDAP `cn` | Không khai báo tên khác Java field và kết quả thiếu attribute |
| `@DnAttribute(..., index=0)` | Gắn `uid` với thành phần DN dùng khi tạo/xác định entry | Index hoặc thứ tự thành phần DN không phù hợp cây LDAP |
| `@Transient` | Loại `displayLabel` khỏi ánh xạ LDAP | Vô tình lưu trường chỉ dành cho UI thành LDAP attribute |

**Hai điểm dễ nhầm:**

1. `@DnAttribute` **không tự làm field trở thành transient**. Field `uid` trong ví dụ có thể đồng thời là attribute của LDAP entry và là một thành phần DN. Ta giữ `@Attribute(name="uid")` để thể hiện rõ dữ liệu cần lưu.
2. `@DnAttribute(index=0)` có vai trò khi ODM tính DN cho entity mới. Với cây có một RDN `uid=...` dưới `ou=people`, đó là cấu hình phù hợp để thực hành; với cây phức tạp nhiều RDN, phải kiểm tra lại thứ tự index. Khi cung cấp cả `value` và `index`, việc xác định thành phần DN theo index được ưu tiên theo quy tắc của Spring LDAP.

### 5.2. Quy ước DN phải nhất quán

Giả sử entity mới có:

~~~text
uid=contact.c
displayName=Contact Charlie
familyName=Charlie
email=contact.charlie@example.org
~~~

DN **dự kiến** sẽ là:

~~~text
uid=contact.c,ou=people,dc=example,dc=org
~~~

Trong đó `dc=example,dc=org` thuộc base của `ContextSource`; `ou=people` thuộc `@Entry(base=...)`; `uid=contact.c` được tính từ field đánh dấu `@DnAttribute`. Đây là giả định cốt lõi cần được xác nhận bằng **bài test tạo, đọc lại và kiểm tra DN thật** trên LDAP server lab; không cộng chuỗi base thêm lần nữa ở service.

DN không nên tự dựng bằng phép cộng chuỗi từ input người dùng. Khi cần thao tác DN thủ công, dùng `LdapNameBuilder`/`LdapName` hoặc API DN của LDAP để xử lý escape ký tự đặc biệt. Với bài này, việc tạo DN được giao cho ODM theo metadata.

## 6. Định nghĩa Spring Data LDAP repository

Tạo interface trong package đã khai báo scan:

~~~java
package com.example.directory.repo;

import java.util.List;
import java.util.Optional;
import com.example.directory.model.DirectoryContact;
import org.springframework.data.ldap.repository.LdapRepository;

public interface ContactRepository
        extends LdapRepository<DirectoryContact> {

    Optional<DirectoryContact> findByUid(String uid);

    List<DirectoryContact> findByFamilyName(String familyName);
}
~~~

`LdapRepository<T>` chỉ cần **một type parameter** là entity; ID mặc định là `javax.naming.Name`. Các phương thức `findByUid` và `findByFamilyName` là **query methods được Spring Data suy từ tên Java property**; `@Attribute(name="sn")` ở entity ánh xạ property `familyName` sang LDAP `sn`.

Repository còn thừa hưởng thao tác CRUD như `save`, `findById(Name)`, `findAll`, `delete`, `deleteById`. Khi cần truy vấn linh hoạt hơn, `LdapRepository` có các phương thức nhận `LdapQuery`; không phải mọi đặc trưng repository của SQL/JPA đều được hỗ trợ trong LDAP.

### 6.1. Khi nào dùng LdapQuery?

Trong một số chức năng, query có nhiều tiêu chí hoặc base/scope đặc biệt. Nếu dùng `LdapQueryBuilder`, hãy tách việc tạo điều kiện khỏi việc chuyển input thành chuỗi filter:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Query tương đối theo nguồn LDAP; kiểm tra base với @Entry(base=...)
var ldapQuery = query()
    .where("sn").is("Alpha")
    .and("objectClass").is("inetOrgPerson");

var contacts = contactRepository.findAll(ldapQuery);
~~~

Đoạn này là **mảnh code minh họa trong một service có biến `contactRepository`**. Khi có `@Entry(base="ou=people")` và `ContextSource.base`, cần thử nghiệm query base để tránh quét nhầm nhánh hoặc lặp base DN. Đừng tự nối input thành `"(sn=" + userInput + ")"`; dùng query builder hoặc repository parameter binding để tránh lỗi escaping/filter injection.

### 6.2. Giới hạn của repository LDAP

Khác với JPA:

- **Không có khóa chính số tự tăng**: DN (`Name`) định danh entry.
- **Không hỗ trợ paging/sorting theo cơ chế repository tương đương RDBMS** trong Spring Data LDAP theo tài liệu; nếu cần phân trang hoặc sắp xếp phía server, phải khảo sát LDAP controls và khả năng server riêng.
- **Không có transaction đa entry theo ngữ nghĩa JDBC/JPA mặc định**; thay đổi nhóm và người liên quan có thể không nguyên tử.
- **Không có lazy relation/JPA join**: danh sách nhóm và liên kết DN phải được thiết kế theo cách LDAP biểu diễn.
- **Không có schema migration tự động** chỉ bằng sửa entity Java.

Tránh đưa `Pageable` hoặc kỳ vọng `@GeneratedValue` vào bài tập này theo thói quen từ Spring Data JPA.

## 7. Viết service cho CRUD danh bạ

Service nhận input đã kiểm tra, gọi repository và trả entity hoặc DTO cần thiết. Không cho controller/HTTP request tự cung cấp DN tuyệt đối để xóa/sửa entry ngoài nhánh được phép.

### 7.1. Tạo contact

~~~java
package com.example.directory.service;

import com.example.directory.model.DirectoryContact;
import com.example.directory.repo.ContactRepository;
import org.springframework.stereotype.Service;

@Service
public class DirectoryContactService {
    private final ContactRepository repository;

    public DirectoryContactService(ContactRepository repository) {
        this.repository = repository;
    }

    public DirectoryContact create(
            String uid, String displayName, String familyName,
            String email) {
        validateUid(uid);
        requireText(displayName, "displayName");
        requireText(familyName, "familyName");
        requireText(email, "email");

        if (repository.findByUid(uid).isPresent()) {
            throw new IllegalArgumentException("Contact UID already exists");
        }

        DirectoryContact contact = new DirectoryContact();
        contact.setUid(uid);
        contact.setDisplayName(displayName);
        contact.setFamilyName(familyName);
        contact.setEmail(email);

        // ODM dùng @DnAttribute + @Entry để xác định DN entity mới.
        return repository.save(contact);
    }

    public DirectoryContact getByUid(String uid) {
        validateUid(uid);
        return repository.findByUid(uid)
            .orElseThrow(() ->
                new IllegalArgumentException("Contact not found"));
    }

    public DirectoryContact changeEmail(String uid, String newEmail) {
        requireText(newEmail, "email");
        DirectoryContact existing = getByUid(uid);
        existing.setEmail(newEmail);
        return repository.save(existing);
    }

    public void deleteByUid(String uid) {
        DirectoryContact existing = getByUid(uid);
        repository.delete(existing);
    }

    private static void validateUid(String uid) {
        if (uid == null ||
            !uid.matches("[a-z][a-z0-9._-]{2,39}")) {
            throw new IllegalArgumentException("Invalid contact UID");
        }
    }

    private static void requireText(String text, String field) {
        if (text == null || text.isBlank() || text.length() > 200) {
            throw new IllegalArgumentException("Invalid field: " + field);
        }
    }
}
~~~

Giải thích luồng:

1. `validateUid(...)` giới hạn tập ký tự đầu vào nhằm đơn giản hóa quy ước định danh của **lab**, không phải quy tắc UID LDAP phổ quát. Trong production phải thiết kế validation phù hợp dữ liệu thật và DN escaping.
2. `repository.findByUid(uid)` kiểm tra trùng ở mức ứng dụng để báo lỗi dễ hiểu.
3. `save(contact)` trên một entity mới được repository/ODM chuyển thành thao tác tạo LDAP entry theo metadata.
4. `getByUid(...)` phân biệt không tìm thấy entry với lỗi kết nối/LDAP. Không tự nuốt mọi ngoại lệ repository thành “not found”.
5. `changeEmail(...)` đọc entry đã tồn tại, chỉ thay trường được phép rồi `save(...)`. Không tạo một entity thiếu các field bắt buộc và tùy tiện `save` đè lên entry đang có.
6. `deleteByUid(...)` luôn tải entry theo nhánh repository quản lý trước khi xóa, không nhận DN trực tiếp từ caller.

**Giới hạn của ví dụ:** Kiểm tra `findByUid` rồi `save` **không phải phép ghi nguyên tử**. Hai request có thể cùng không tìm thấy UID và đồng thời tạo. Sự duy nhất của **DN** phải được LDAP server thực thi; service cần bắt và phân loại lỗi entry tồn tại khi có cạnh tranh. Nếu ứng dụng cần uniqueness của một attribute ở nhiều DN khác nhau, phải xem cơ chế ràng buộc/schema/plugin của server.

Validation `email` trong ví dụ chỉ kiểm tra cơ bản. Trong ứng dụng thật cần validation cú pháp, độ dài, chính sách miền và xử lý canonicalization phù hợp. Không ghi raw email/UID vào log lỗi ở nơi không được phép.

### 7.2. Tìm theo họ và điều kiện nghiệp vụ

~~~java
public List<DirectoryContact> findByFamilyName(String familyName) {
    requireText(familyName, "familyName");
    return repository.findByFamilyName(familyName);
}
~~~

Mảnh code trên giả định nằm trong `DirectoryContactService` đã định nghĩa ở mục 7.1. Truy vấn có thể trả nhiều contact; không mặc định một họ là duy nhất. Đối với UI tìm kiếm tự do có ký tự wildcard, thiết kế query semantics và limit rõ ràng; không lấy tất cả entry của directory rồi lọc ở Java.

### 7.3. Không trả entity ODM trực tiếp lên API công khai

Entity chứa DN nội bộ và metadata dùng cho lưu trữ. Controller nên trả **DTO** giới hạn những trường mà caller được xem:

~~~java
// Java 17+; dùng class DTO tương đương nếu dự án ở Java cũ.
public record ContactView(
    String uid,
    String displayName,
    String email
) {
    public static ContactView from(DirectoryContact entity) {
        return new ContactView(
            entity.getUid(),
            entity.getDisplayName(),
            entity.getEmail()
        );
    }
}
~~~

Không đặt `dn`, `userPassword`, mật khẩu bind, membership nội bộ hoặc thuộc tính bí mật vào response chỉ vì entity có getter. Hạn chế cả dữ liệu đọc từ LDAP và dữ liệu ghi vào LDAP theo phân quyền người dùng gọi API.

## 8. ODM và repository so với LdapTemplate thuần

Spring LDAP có thể ánh xạ entity ngay cả khi không có Spring Data repository:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Trong một service có bean LdapTemplate template:
DirectoryContact one = template.findOne(
    query().where("uid").is("contact.a"),
    DirectoryContact.class
);

// Các thao tác ODM tương ứng có thể dùng:
template.create(contact);
template.update(contact);
template.delete(contact);
~~~

Các mảnh code trên minh họa **API ODM của `LdapTemplate`**, không phải một file Java hoàn chỉnh. Các lệnh create/update/delete chỉ nên được gọi trong lab đã có ACL và entity hợp lệ. Khi dùng repository, các thao tác nghiệp vụ tương đương thường được thể hiện qua `save` và `delete`.

| Tình huống | Repository ODM | LdapTemplate trực tiếp |
| --- | --- | --- |
| CRUD entity đã có mapping | Gọn với `save`/`findById`/`delete` | `create`/`update`/`delete` entity |
| Query đơn giản theo property | `findByUid`, `findByFamilyName` | `find(query, Entity.class)` |
| Search filter rất động | `findAll(LdapQuery)` khi phù hợp | `LdapQueryBuilder` và `find`/`search` |
| LDAP controls, paging, thao tác đặc thù | Có giới hạn theo API repository | Thường cần `LdapTemplate` hoặc JNDI nâng cao |
| Mapping các entry khác schema | Cần entity chính xác | Có thể dùng `AttributesMapper`/`ContextMapper` linh hoạt hơn |

Trong một ứng dụng, có thể **dùng cả repository lẫn `LdapTemplate`** nhưng phải dùng cùng chính sách `ContextSource`, TLS, bind và ACL. Không để repository đi qua LDAPS còn tác vụ template thủ công lại dùng LDAP không mã hóa.

## 9. Kiểm thử tích hợp và điều kiện hoàn thành

Chỉ test getter/setter của entity không đủ. Cần xác nhận Spring LDAP thực sự tính DN đúng, server chấp nhận objectClass, và repository đọc lại được dữ liệu.

### 9.1. Dựng lab có cây LDAP độc lập

Chuẩn bị server LDAP thử nghiệm (ví dụ một container LDAP hoặc LDAP nhúng được hỗ trợ bởi bộ công cụ của dự án), suffix và `ou=people`. Tạo tài khoản lab với quyền:

- Search và read trong `ou=people`.
- Add/modify/delete **chỉ trong nhánh lab** cho ca CRUD.
- Không có quyền quản trị suffix hoặc dữ liệu ngoài lab.

Trong test độc lập, người học có thể sử dụng tài khoản khác nhau cho phép đọc và ghi để chứng minh ACL. Không dùng cùng cấu hình tài khoản write cho production chỉ vì code service đã chạy thành công trong lab.

### 9.2. JUnit test create → read → update → delete

Ví dụ tích hợp (yêu cầu một LDAP server lab được chuẩn bị và application context cấu hình đúng):

~~~java
package com.example.directory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import com.example.directory.model.DirectoryContact;
import com.example.directory.repo.ContactRepository;
import com.example.directory.service.DirectoryContactService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ContactRepositoryIntegrationTest {

    @Autowired DirectoryContactService service;
    @Autowired ContactRepository repository;

    @Test
    void createReadUpdateDeleteContact() {
        String uid = "t" + UUID.randomUUID().toString()
            .replace("-", "").substring(0, 12);
        DirectoryContact created = null;

        try {
            created = service.create(
                uid, "Lab Contact", "Contact", "lab@example.org"
            );

            DirectoryContact loaded = service.getByUid(uid);
            assertEquals(uid, loaded.getUid());
            assertEquals("Lab Contact", loaded.getDisplayName());
            assertTrue(loaded.getDn() != null);

            DirectoryContact updated =
                service.changeEmail(uid, "updated@example.org");
            assertEquals("updated@example.org",
                         updated.getEmail());
            assertEquals("updated@example.org",
                         service.getByUid(uid).getEmail());

            service.deleteByUid(uid);
            assertFalse(repository.findByUid(uid).isPresent());
        } finally {
            // Cleanup dùng entry thực sự được tạo trong lab;
            // không xóa dữ liệu có trước nếu create thất bại.
            if (created != null) {
                repository.findByUid(uid).ifPresent(repository::delete);
            }
        }
    }
}
~~~

Test cần chạy **chỉ trên lab**; hậu tố random giảm khả năng trùng nhưng không thay uniqueness phía server. Nếu thao tác `save` thất bại sau khi server đã tạo entry nhưng client mất phản hồi, cleanup chỉ dựa vào `created != null` có thể bỏ sót entry; test nâng cao nên có dữ liệu lab riêng và cơ chế cleanup/reconcile an toàn. Với thao tác ghi trong production, cũng không retry mù quáng khi chưa biết server đã áp dụng thay đổi hay chưa.

Đừng bọc bài test này bằng `@Transactional` rồi kỳ vọng LDAP có rollback giống cơ sở dữ liệu quan hệ. Kiểm tra DN đầy đủ và các trường thực lưu qua `ldapsearch` hoặc một phép đọc dùng quyền lab tương ứng.

### 9.3. Ma trận kiểm thử cần thực hiện

| Trường hợp | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Tạo contact hợp lệ | `uid/cn/sn` và email hợp lệ | Server nhận entry, DN đúng, đọc lại được |
| Thiếu `cn` hoặc `sn` | Dữ liệu không hợp lệ | Service hoặc schema từ chối; không tạo entry lỗi |
| Tạo trùng DN | Hai request cùng UID | Chỉ một entry; lỗi cạnh tranh được xử lý |
| UID chứa dấu phẩy/ký tự ngoài quy ước lab | Input không được chấp nhận | Validation từ chối; không tự nối DN nguy hiểm |
| Repository tìm theo `uid` | Dữ liệu thử nghiệm tồn tại | `findByUid` trả đúng entry |
| Tìm theo `familyName` | Nhiều contact cùng `sn` | Trả danh sách, không giả định duy nhất |
| Cập nhật `mail` | Entry tồn tại, quyền write đúng | Thuộc tính đổi, DN/UID không đổi |
| Xóa entry | Lab entry do test tạo | Entry không còn khi tìm lại |
| Thiếu quyền ghi | Bind identity chỉ đọc | Add/modify/delete bị ACL từ chối |
| Sai objectClass hoặc attribute | Mapping không hợp schema | Lỗi schema rõ ràng |
| Sai `@Entry(base)` hoặc `@DnAttribute(index)` | Lệch base/index | Test phát hiện DN không đúng |
| TLS certificate không hợp lệ | Endpoint lab với CA/SAN sai | Kết nối bị từ chối trước bind |
| Referral, server restart hoặc pool stale | Sự cố trong lab | Không hạ cấp TLS; log và xử lý context lỗi |

### 9.4. Cách kiểm tra bằng ldapsearch trong lab

~~~bash
ldapsearch -H ldaps://directory.example.org:636 \
  -x -D "cn=directory-editor,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(uid=contact.a)" uid cn sn mail telephoneNumber
~~~

`-W` yêu cầu nhập mật khẩu tương tác. Tool LDAP CLI có cấu hình CA/trust riêng với JVM; hãy đảm bảo hostname verification và trust CA được bật. Kết quả `ldapsearch` phù hợp giúp đối chiếu **giá trị thực trong LDAP** với entity ODM. Không đưa mật khẩu hoặc dữ liệu thực vào câu lệnh, log hay tài liệu công khai.

## 10. Các lỗi thường gặp khi ghép ODM với repository

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và sửa |
| --- | --- | --- |
| Không tạo được repository bean | Thiếu dependency `spring-data-ldap` hoặc scan package sai | Dùng starter đúng; kiểm tra `@EnableLdapRepositories` và package |
| Entity không được nhận diện | Thiếu `@Entry` hoặc `@Id` ODM; import nhầm annotation | Sửa import `org.springframework.ldap.odm.annotations.*` |
| Không tạo được entry | Thiếu `cn`/`sn`, objectClass sai, parent `ou=people` chưa có, quyền write thiếu | Kiểm tra schema, LDIF parent, ACL |
| DN tạo không như dự kiến | `@Entry.base` và `ContextSource.base` không nhất quán, index DN sai | In/đọc DN ở lab; tránh nối DN bằng chuỗi |
| Search trả rỗng | Sai base/scope/filter hoặc ACL không cho đọc | Kiểm tra `findByUid`, data fixture và bind identity |
| Mapping thất bại | Thuộc tính không tồn tại/sai kiểu, field Java khác tên LDAP | Rà `@Attribute`, schema, dữ liệu thực |
| `findById` không tìm thấy | DN truyền vào không đúng phạm vi/cách biểu diễn | Kiểm tra `Name` tương ứng với context base |
| `save` hoặc `delete` bị từ chối | ACL hoặc server constraint | Kiểm tra quyền theo nhánh, không cấp quyền admin vô tội vạ |
| `PKIX path building failed` | Truststore/chain/CA không phù hợp | Sửa CA và server chain; không bỏ TLS validation |
| `No subject alternative DNS name matching` | SAN không khớp hostname | Sửa URL/certificate, không tắt hostname verification |
| Update làm mất thuộc tính | Model thiếu field hoặc xử lý null không phù hợp | Đọc entity hiện hữu, cập nhật có chủ đích, test dữ liệu ngoài model |

**Lưu ý với `save`:** Cách xác định thao tác tạo/cập nhật và cách ODM xử lý attributes phụ thuộc metadata entity và implementation. Một entity chỉ chứa một phần dữ liệu của entry thật có thể gây hậu quả không mong muốn khi lưu. Hãy bảo toàn trường hiện có, dùng mô hình đúng schema và test dữ liệu có các attribute ngoài phạm vi DTO. Nếu cần cập nhật từng thuộc tính với độ chính xác cao, cân nhắc `LdapTemplate.modifyAttributes` hoặc một thao tác chuyên biệt thay vì mặc định `save` như bản cập nhật một phần.

### 10.1. Khi nào tránh dùng ODM cho toàn bộ dữ liệu?

Một thư mục doanh nghiệp có thể chứa objectClass mở rộng, thuộc tính binary, multi-valued và các trường chỉ một hệ thống khác được phép quản lý. Trong trường hợp ứng dụng chỉ đọc hai attribute, ánh xạ cả entry rồi lưu lại là không cần thiết và có thể tăng rủi ro. Lúc đó, `LdapTemplate.search(...)` với một `AttributesMapper` nhỏ có thể đơn giản, minh bạch hơn.

Kết hợp ODM cho entity ổn định với `LdapTemplate` cho tác vụ chuyên biệt là lựa chọn hợp lý; điều kiện là **mọi đường truy cập cùng tuân thủ TLS, ACL và quy trình quản lý DN/filter**.

## 11. Bài tập nâng cao: thêm nhóm danh bạ

Mở rộng bài tập bằng nhánh:

~~~text
ou=groups,dc=example,dc=org
└── cn=directory-editors
~~~

Một số LDAP server hỗ trợ object class `groupOfUniqueNames` với thuộc tính `uniqueMember` chứa tập DN thành viên. Nếu schema lab có object class này, có thể hình dung entity:

~~~java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    objectClasses = {"top", "groupOfUniqueNames"},
    base = "ou=groups"
)
public class DirectoryGroup {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    @DnAttribute(value = "cn", index = 0)
    private String name;

    @Attribute(name = "uniqueMember")
    private Set<Name> members;

    public DirectoryGroup() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public Set<Name> getMembers() { return members; }
    public void setMembers(Set<Name> members) {
        this.members = members;
    }
}
~~~

Trong schema `groupOfUniqueNames`, `uniqueMember` thường là thuộc tính bắt buộc và có thể yêu cầu tối thiểu một DN thành viên; không tạo group rỗng nếu schema server không cho phép. Việc sử dụng `Set<Name>` giúp ODM làm việc với các giá trị DN như đối tượng có ngữ nghĩa DN, thay vì ghép chuỗi thủ công.

**Câu hỏi mở rộng:**

1. Cần thêm bean/repository nào để tìm group theo `cn`?
2. Có nên trả toàn bộ `uniqueMember` lên REST API nếu caller chỉ cần tên nhóm?
3. Nếu một contact bị xóa nhưng vẫn xuất hiện trong `uniqueMember` của group, có transaction tự động xóa tham chiếu không?
4. Khi group cần thuộc tính khác `groupOfUniqueNames`, nên làm gì với schema và mapping?

**Gợi ý:** Có thể khai báo `LdapRepository<DirectoryGroup>`, chỉ trả DTO công khai cần thiết, và thực hiện xử lý tham chiếu thành viên theo quy trình nghiệp vụ/LDAP server cụ thể. Không giả định LDAP tự cascade delete hoặc bảo đảm transaction đa entry. Mỗi thay đổi phải tuân thủ ACL và được kiểm thử với schema thật.

## 12. Bài tập tổng kết và tiêu chí nghiệm thu

### Đề bài

Cho một LDAP lab đã có suffix `dc=example,dc=org` và nhánh `ou=people`. Hãy:

1. Cấu hình ứng dụng Spring Boot kết nối **LDAPS** và dùng truststore hợp lệ.
2. Tạo entity ODM `DirectoryContact` với objectClass `inetOrgPerson`, DN dựa trên `uid`.
3. Khai báo repository dùng `LdapRepository<DirectoryContact>` để truy vấn theo UID/họ.
4. Viết service tạo contact, đọc, đổi email và xóa theo UID.
5. Chạy integration test bảo đảm **DN thật** và các thuộc tính trên server đúng.
6. Chứng minh tài khoản chỉ đọc không thể cập nhật hoặc xóa.
7. Kiểm tra ứng dụng từ chối TLS server certificate có CA/SAN không hợp lệ.

### Tiêu chí đạt

| Hạng mục | Bằng chứng tối thiểu |
| --- | --- |
| DN và schema | Entry có DN đúng nhánh, `top/person/organizationalPerson/inetOrgPerson` và `cn/sn` |
| ODM | `@Id Name`, `@Entry`, `@Attribute`, `@DnAttribute` ánh xạ đúng |
| Repository | Bean được khởi tạo; `findByUid` và `findByFamilyName` có kết quả phù hợp |
| CRUD | Create/read/update/delete hoạt động trên lab; cleanup không tác động entry khác |
| Security | TLS xác minh máy chủ, bind identity có quyền tối thiểu, không log secret |
| Negative tests | Từ chối UID sai, DN trùng, lỗi schema, không có quyền và CA/SAN sai |
| Observability | Log operation/trace ID/target và lỗi đã sanitize; không lộ mật khẩu hoặc dữ liệu nhân sự |

### Ghi nhớ

- **ODM** ánh xạ schema/DN LDAP sang Java entity; **repository** cung cấp API lưu/truy vấn dựa trên mapping đó.
- Dùng `@Id` của **Spring LDAP** trên `Name`; không coi UID text hoặc ID số của JPA là khóa LDAP.
- `ContextSource.base`, `@Entry.base` và các thành phần `@DnAttribute` phải được kiểm chứng với **DN thực tế** khi tạo entry.
- `LdapRepository<DirectoryContact>` có một generic type parameter; query derivation theo Java property và mapping LDAP attribute.
- Repository đơn giản hóa CRUD nhưng không tự tạo schema, ACL, uniqueness toàn cục hay transaction đa entry.
- Luôn kiểm tra **TLS, bind identity, quyền truy cập, exception và dữ liệu nhạy cảm** cùng với logic CRUD.

**Tài liệu tham khảo chính thức**

- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring Data LDAP — Repository configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring Data LDAP — Query methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html)
- [Spring Boot — LDAP auto-configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html)
