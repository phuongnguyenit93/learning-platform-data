# Khai báo LdapRepository cho lớp thực thể ODM

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP qua Spring Data LDAP, ánh xạ các entry có DN (*Distinguished Name*), `objectClass` và schema sang đối tượng Java. Nếu đã có một lớp thực thể ODM (*Object-Directory Mapping*) biểu diễn entry, ta có thể khai báo **`LdapRepository<T>`** để dùng các thao tác đọc, lưu, xóa và truy vấn theo kiểu Spring Data repository mà không phải viết lại toàn bộ lời gọi `LdapTemplate`.

Bài học này tập trung vào câu hỏi: **cần khai báo entity và repository như thế nào để Spring Data LDAP tự tạo một bean repository hoạt động đúng với directory?** Bạn sẽ nắm được các annotation ODM bắt buộc, generic type của `LdapRepository`, cách cấu hình quét repository, ví dụ sử dụng thực tế, giới hạn của LDAP và cách kiểm thử.

## 1. Vì sao dùng repository với LDAP?

Giả sử directory đang chứa:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    └── uid=binh
```

Một entry minh họa:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
```

Với `LdapTemplate`, mỗi use case có thể phải viết cách xây dựng `LdapQuery`, chọn base DN, gọi `search`/`find`, và tổ chức các phương thức CRUD. Với repository, ta mô tả **entity ODM** một lần rồi khai báo một **interface**. Spring Data tạo implementation tại thời điểm khởi tạo ứng dụng:

```text
             PersonService
                  |
                  v
    PersonRepository extends LdapRepository<PersonEntry>
                  |
        Spring Data tạo repository proxy
                  |
                  v
           LdapTemplate / ODM
                  |
                  v
             ContextSource
                  |
                  v
           LDAP directory
```

Repository hữu ích khi nghiệp vụ làm việc với **thực thể Java gắn với entry LDAP**, cần `findById`, `findAll`, `save`, `deleteById` hoặc các finder đơn giản. Khi cần truy vấn phức tạp, tùy chỉnh search controls, paging kiểu LDAP đặc thù hoặc ánh xạ DTO không phải entity, bạn vẫn có thể phối hợp với `LdapTemplate`.

## 2. Điều kiện để khai báo một LdapRepository

Spring Data LDAP có các ràng buộc khác một số module Spring Data quen thuộc:

| Thành phần | Quy tắc |
|---|---|
| Interface repository | `org.springframework.data.ldap.repository.LdapRepository<T>` |
| Generic type | **Một kiểu** `T` là entity ODM, ví dụ `LdapRepository<PersonEntry>` |
| Kiểu ID | Mặc định là **`javax.naming.Name`**, đại diện cho DN |
| Annotation entity bắt buộc | `@Entry` trên lớp; `@Id` trên trường DN |
| Package annotation ODM | `org.springframework.ldap.odm.annotations` |
| Kết nối | Một `ContextSource` và `LdapTemplate` được Spring cấu hình |
| Kích hoạt repository | Spring Boot tự quét theo package cấu hình, hoặc khai báo `@EnableLdapRepositories` |

**Đúng:**

```java
public interface PersonRepository extends LdapRepository<PersonEntry> {
}
```

**Sai kiểu generic với API `LdapRepository`:**

```java
// Không biên dịch: LdapRepository chỉ khai báo một tham số kiểu.
// public interface PersonRepository
//         extends LdapRepository<PersonEntry, Long> { }
```

Một số tài liệu Spring Data tổng quát dùng `CrudRepository<Entity, Long>` làm ví dụ cho cơ sở dữ liệu khác. Trong LDAP, DN chính là identifier của ODM entity, nên không dùng `Long` hoặc `String` thay cho `Name` chỉ vì chương trình đang có một trường `uid`.

**Dễ nhầm:** `@Id` dùng ở đây là `org.springframework.ldap.odm.annotations.Id`, **không phải** `org.springframework.data.annotation.Id` hay `jakarta.persistence.Id`. Đánh dấu sai annotation có thể khiến Spring LDAP không nhận diện DN của entity.

## 3. Khai báo entity ODM tương ứng với entry

Với cấu trúc thư mục ví dụ, đặt base DN của kết nối là `dc=example,dc=org` và dùng `ou=people` làm base của loại entity. Để ánh xạ `inetOrgPerson`, entity khai báo đầy đủ các `objectClass` mà ví dụ dự kiến quản lý:

**`PersonEntry.java`**

```java
package com.example.ldap.model;

import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
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
    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {
    }

    public Name getDn() {
        return dn;
    }

    public void setDn(Name dn) {
        this.dn = dn;
    }

    public String getUid() {
        return uid;
    }

    public void setUid(String uid) {
        this.uid = uid;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getSurname() {
        return surname;
    }

    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Ý nghĩa các annotation:

- **`@Entry`** xác định loại entry bằng `objectClasses` và nhánh dự kiến của entity bằng `base`. Các `objectClass` phải phù hợp schema trên server; khi tạo entry, Spring LDAP dùng các objectClass đã khai báo. Ví dụ dùng `inetOrgPerson`, nên bao gồm các lớp `top`, `person` và `organizationalPerson` theo mô hình schema thông dụng.
- **`@Id`** đánh dấu DN, kiểu `Name`. Giá trị có thể là `uid=lan,ou=people` tương đối với `ContextSource.base = dc=example,dc=org`. Không tự gắn thêm hậu tố `dc=example,dc=org` khi thao tác qua context đã có base này.
- **`@Attribute(name = "...")`** ánh xạ trường Java sang thuộc tính LDAP tương ứng. `fullName` không trùng tên thuộc tính LDAP `cn`, vì vậy cần chỉ rõ. Những trường có tên trùng thuộc tính LDAP cũng có thể được ánh xạ theo quy ước mặc định.
- **`@DnAttribute(value = "uid", index = 0)`** ánh xạ thành phần `uid` của DN vào trường `uid`. Chỉ số `index` cho phép ODM tính DN khi tạo entity mới; với `@Entry.base = ou=people`, DN tương đối có dạng `uid=<giá trị>,ou=people`. `@DnAttribute` dùng cho trường `String`.
- **Constructor không tham số** và getter/setter giúp lớp dễ được ánh xạ, dùng trong service và kiểm thử.

Trong schema `person`, `cn` và `sn` là các thuộc tính bắt buộc. `mail` thường tùy chọn và trong nhiều directory có thể đa trị; ví dụ này dùng `String` để phục vụ bài học khai báo repository. Nếu ứng dụng cần nhiều email, hãy chọn kiểu collection và quy tắc ánh xạ phù hợp. Không mặc định mọi directory đều dùng cùng schema hoặc mức độ bắt buộc của `uid`.

**Phân biệt DN và ID nghiệp vụ:** `uid` là giá trị thuộc tính LDAP, còn `dn` là danh tính của entry trong cây. `uid` có thể trùng ở hai container khác nhau; DN cũng có thể thay đổi khi rename/move. Nếu cần khóa bất biến xuyên hệ thống, hãy nghiên cứu thuộc tính chuyên biệt của server (ví dụ `entryUUID`) thay vì mặc định dùng `uid`.

## 4. Khai báo interface LdapRepository

**`PersonRepository.java`**

```java
package com.example.ldap.repository;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import com.example.ldap.model.PersonEntry;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByUid(String uid);

    List<PersonEntry> findBySurname(String surname);
}
```

Không cần tự viết `PersonRepositoryImpl`. Khi repository scanning hoạt động, Spring Data sẽ sinh proxy và cung cấp các phương thức có sẵn. Tên các finder `findByUid`/`findBySurname` tham chiếu **thuộc tính Java của entity**; mapper biết `surname` được ánh xạ thành thuộc tính LDAP `sn` nhờ `@Attribute(name = "sn")`.

Những phương thức đáng chú ý:

| Phương thức | Ý nghĩa |
|---|---|
| `findById(Name dn)` | Đọc một entry theo DN, kết quả `Optional<PersonEntry>` |
| `existsById(Name dn)` | Kiểm tra entry có tồn tại ở DN |
| `findAll()` | Lấy các entity phù hợp phạm vi repository; cần cẩn thận khi nhánh lớn |
| `save(PersonEntry entity)` | Lưu entity mới hoặc cập nhật theo cơ chế repository/ODM |
| `deleteById(Name dn)` | Xóa entry theo DN; cần quyền directory tương ứng |
| `findAll(LdapQuery q)` | Tìm các entity theo `LdapQuery` |
| `findOne(LdapQuery q)` | Tìm một entity theo `LdapQuery`; lỗi nếu có nhiều entry phù hợp |
| `findByUid(String uid)` | Finder khai báo theo tên method, có thể trả nhiều entry |

Các phương thức LDAP riêng như `findAll(LdapQuery)` và `findOne(LdapQuery)` là lý do nên kế thừa `LdapRepository` thay vì chỉ dùng `CrudRepository`. `LdapRepository<T>` mở rộng khả năng CRUD kiểu Spring Data nhưng **không cung cấp phân trang và sắp xếp repository theo cách của Spring Data JPA**.

Nếu chỉ có một entry phù hợp trong phạm vi tìm kiếm, bạn có thể chọn phương thức trả về `Optional<T>`; tuy nhiên phải bảo đảm điều kiện thực sự là duy nhất và có cách xử lý nếu directory chứa nhiều entry trùng `uid`. Với tìm kiếm không đảm bảo duy nhất, `List<PersonEntry>` làm rõ hợp đồng hơn.

## 5. Bật repository scanning và cấu hình kết nối

Với Spring Boot, phụ thuộc thường dùng là `org.springframework.boot:spring-boot-starter-data-ldap`. Ví dụ Maven, phiên bản do Spring Boot BOM quản lý:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
```

Khai báo thông tin kết nối trong `application.yml`:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Ứng dụng thực tế cần tài khoản bind có quyền phù hợp; nếu dùng các thao tác `save`/`delete`, tài khoản cần quyền ghi trong vùng được phép. `LDAP_BIND_PASSWORD` nên được cấp qua biến môi trường hoặc secret manager, không commit giá trị thật vào repo. Kết nối LDAPS hoặc StartTLS phải xác thực chứng chỉ và hostname của server.

Spring Boot thường tự quét repository và entity nằm trong các package bên dưới package của lớp ứng dụng. Khi cần chỉ định rõ package hoặc khi cấu hình Spring không dùng Boot auto-configuration, khai báo:

**`LdapRepositoryConfiguration.java`**

```java
package com.example.ldap.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;
import com.example.ldap.repository.PersonRepository;

@Configuration
@EnableLdapRepositories(basePackageClasses = PersonRepository.class)
public class LdapRepositoryConfiguration {
}
```

`@EnableLdapRepositories` chỉ định package để quét interface repository, **không tự mở kết nối LDAP**. Trong ví dụ Spring Boot, `LdapContextSource` và `LdapTemplate` được auto-configure từ `spring.ldap.*`. Nếu dùng Spring Framework thuần, bạn phải cung cấp bean `ContextSource`/`LdapTemplate` và cấu hình phù hợp.

Nếu ứng dụng có nhiều `LdapTemplate`, cần thiết lập chính xác template được repository sử dụng và định tuyến theo nguồn LDAP; tránh để repository đọc nhầm directory. Tùy phiên bản và phương thức cấu hình, hạ tầng repository mặc định tìm bean tên `ldapTemplate`.

## 6. Gọi repository từ service

Một service chỉ cần inject interface:

**`PersonService.java`**

```java
package com.example.ldap.service;

import java.util.List;
import java.util.Optional;
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

import com.example.ldap.model.PersonEntry;
import com.example.ldap.repository.PersonRepository;

@Service
public class PersonService {
    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    public Optional<PersonEntry> findByUidDn(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return people.findById(relativeDn);
    }

    public List<PersonEntry> findBySurname(String surname) {
        if (surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("surname không được rỗng");
        }
        return people.findBySurname(surname);
    }
}
```

Với `spring.ldap.base = dc=example,dc=org`, `findById` nhận DN **tương đối với base** của context: `uid=lan,ou=people`. `LdapNameBuilder` escape giá trị RDN, ví dụ dấu phẩy hoặc dấu cộng xuất hiện trong `uid`. Nếu truyền DN đầy đủ `uid=lan,ou=people,dc=example,dc=org` như một tên tương đối trong context đã có base, ứng dụng có thể ghép lặp hậu tố và tìm sai entry.

Lưu ý sự khác biệt:

- `findById(relativeDn)` dùng **địa chỉ DN xác định**; không phải finder theo trường `uid`.
- `findByUid(uid)` là **truy vấn trên thuộc tính** `uid`, không cần biết trước container chính xác của entry trong phạm vi repository.
- `findBySurname(surname)` chuyển điều kiện trên trường Java `surname` thành filter trên thuộc tính LDAP `sn` theo mapping.

Không tự ghép chuỗi LDAP filter như `"(uid=" + uid + ")"` từ dữ liệu người dùng. Finder theo tên method và `LdapQueryBuilder` thực hiện việc xây dựng filter/escape giá trị; khi viết `@Query` thủ công phải dùng binding tham số hợp lệ và lưu ý cách escape cho biểu thức đặc biệt.

## 7. Truy vấn với LdapQuery mà không cần viết repository mới

Ngoài finder theo tên, `LdapRepository` còn hỗ trợ trực tiếp `LdapQuery`:

```java
import java.util.List;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Ví dụ nằm trong một service đã inject PersonRepository people.
LdapQuery ldapQuery = query()
        .base("ou=people")
        .attributes("uid", "cn", "sn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("sn").is("Nguyen");

List<PersonEntry> matches = people.findAll(ldapQuery);
```

Trong truy vấn, `base("ou=people")` là base tìm kiếm tương đối với `ContextSource.base`. Nếu ứng dụng cấu hình `dc=example,dc=org`, vùng thực tế được tìm là `ou=people,dc=example,dc=org`. Phần `attributes(...)` phải chứa các thuộc tính entity cần ánh xạ; nếu không trả `sn`, `cn` hoặc `mail` thì object có thể thiếu dữ liệu mong muốn.

`LdapQueryBuilder.where(...).is(...)` là một cách xây filter LDAP an toàn với giá trị đầu vào. Để điều chỉnh phạm vi, sử dụng `searchScope(...)` khi tạo truy vấn; để tránh trả quá nhiều dữ liệu có thể đặt `countLimit(...)`/`timeLimit(...)`. Đặt các tùy chọn xây dựng truy vấn **trước** `where(...)`.

**Cần thận trọng:** LDAP có thể có giới hạn kích thước kết quả phía server và không bảo đảm sắp xếp thứ tự. `findAll()` hoặc `findAll(query)` trên nhánh nhiều người dùng không phải mặc nhiên là giải pháp phân trang. Nếu cần cơ chế paging thực sự, hãy nghiên cứu LDAP paged-results control và hành vi directory qua `LdapTemplate`/JNDI.

## 8. Tạo/cập nhật entity và giới hạn của save

Sau khi khai báo ODM và repository đúng, có thể làm việc với entry thông qua `save`. Ở ví dụ `PersonEntry`, `uid` được đánh dấu `@DnAttribute(index = 0)` và `@Entry.base = ou=people`, cho phép ODM tính DN khi tạo entity mới trong vùng này.

Ví dụ dữ liệu đầu vào **đã được kiểm tra và cho phép**:

```java
PersonEntry person = new PersonEntry();
person.setUid("lan");
person.setFullName("Lan Nguyen");
person.setSurname("Nguyen");
person.setEmail("lan@example.org");

PersonEntry saved = people.save(person);
// Với base kết nối dc=example,dc=org, DN dự kiến của entity:
// uid=lan,ou=people,dc=example,dc=org
```

Khi `@Id` đã có `Name`, đó là DN mà ODM sẽ dùng cho thao tác tương ứng; khi `@Id` rỗng, ODM có thể tính DN từ `@DnAttribute(index = ...)` và `@Entry.base` nếu cấu hình đủ. Đừng trộn DN tuyệt đối với DN tương đối hoặc tùy tiện thay đổi `uid` (thuộc thành phần RDN) trong thao tác cập nhật.

Lưu ý các điều kiện trước khi dùng `save`:

1. Entry cha như `ou=people` **phải tồn tại** và tài khoản bind phải có quyền tạo/sửa entry tại nhánh đó.
2. Những thuộc tính schema yêu cầu như `cn`, `sn` phải có giá trị hợp lệ; objectClasses phải phù hợp với server.
3. DN có thể đã tồn tại; tùy trạng thái entity và cơ chế repository, thao tác là tạo hoặc cập nhật. Không coi `save` là phép *upsert* an toàn trước xung đột đồng thời.
4. Thay đổi trường tham gia DN có thể kéo theo rename/move; hãy thiết kế thao tác đổi DN riêng khi cần và kiểm tra quyền/khả năng server.
5. LDAP không mặc nhiên hỗ trợ transaction ACID nhiều entry như một hệ quản trị cơ sở dữ liệu quan hệ. Không đặt kỳ vọng rằng nhiều lời gọi `save`/`delete` được rollback đồng loạt.

Nếu ứng dụng chỉ cần tìm kiếm người dùng hoặc đồng bộ danh tính dạng chỉ đọc, không cần cấp quyền ghi chỉ để sử dụng `LdapRepository`.

## 9. Lỗi khai báo thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lỗi generic type khi `extends LdapRepository<PersonEntry, Long>` | `LdapRepository` chỉ nhận một kiểu entity | Dùng `LdapRepository<PersonEntry>` |
| Lỗi tạo ODM entity / không nhận biết ID | Import sai `@Id` (Spring Data/JPA), DN dùng `String` | Import `org.springframework.ldap.odm.annotations.Id` và dùng `javax.naming.Name` |
| Không inject được `PersonRepository` | Repository chưa được quét, thiếu starter hoặc thiếu bean LDAP | Kiểm tra package scanning, `@EnableLdapRepositories`, `ContextSource`/`LdapTemplate` |
| Finder tìm không thấy dù entry tồn tại | Sai `@Entry.base`, context base, scope, tên thuộc tính hoặc filter | Đối chiếu base tương đối và DN đầy đủ trên directory |
| Tạo entry bị schema violation | Thiếu `cn`/`sn`, sai `objectClass` hoặc thuộc tính không hợp lệ | So sánh entity với LDAP schema đang triển khai |
| `save` báo entry exists/permission denied | DN trùng hoặc tài khoản không có quyền | Kiểm tra DN và ACL, tách rõ tạo/cập nhật |
| Trường Java nhận `null` bất ngờ | Tên `@Attribute` sai, thuộc tính không có hoặc bị ACL/filter trả về thiếu | Kiểm tra mapping, thuộc tính được yêu cầu và quyền đọc |
| Cần `Pageable` nhưng không hoạt động | LDAP repository không hỗ trợ paging/sorting như Spring Data JPA | Sử dụng API và LDAP control phù hợp, có thể qua `LdapTemplate` |
| Query trả nhiều entry dù chỉ mong một | Chưa bảo đảm tính duy nhất của thuộc tính | Dùng `List` hoặc xác định phạm vi và xử lý nhiều kết quả |

Đặc biệt tránh copy ví dụ Spring Data JPA và đổi tên repository sang LDAP mà giữ nguyên `@Entity`, `@Table`, `@Id Long`, `JpaRepository`. Spring LDAP ODM có mô hình và annotation riêng.

## 10. Kiểm thử repository với một directory thật hoặc dành cho test

Kiểm thử `LdapRepository` cần một LDAP directory có schema và dữ liệu mẫu để kiểm tra cả query lẫn ánh xạ. Có thể dùng một LDAP server thử nghiệm/embedded directory được hỗ trợ, với DIT tối thiểu gồm `dc=example,dc=org` và `ou=people`, sau đó nạp entry `uid=lan,...` như ví dụ đầu bài.

Một bài kiểm thử tích hợp (JUnit 5 + Spring Boot Test), giả sử test profile đã cấu hình URL/base/credentials tới **directory thử nghiệm** và đã nạp entry mẫu:

**`PersonRepositoryIT.java`**

```java
package com.example.ldap;

import java.util.List;
import javax.naming.Name;

import com.example.ldap.model.PersonEntry;
import com.example.ldap.repository.PersonRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class PersonRepositoryIT {

    @Autowired
    PersonRepository repository;

    @Test
    void findsExistingEntryByRelativeDn() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lan")
                .build();

        PersonEntry person = repository.findById(dn).orElseThrow();

        assertEquals("lan", person.getUid());
        assertEquals("Lan Nguyen", person.getFullName());
        assertEquals("Nguyen", person.getSurname());
    }

    @Test
    void findsEntriesByMappedSurnameAttribute() {
        List<PersonEntry> people = repository.findBySurname("Nguyen");

        assertTrue(people.stream()
                .anyMatch(person -> "lan".equals(person.getUid())));
    }
}
```

Lỗi đầu tiên cần loại trừ khi test không tìm thấy entry là **sai base DN**: `spring.ldap.base`, `@Entry.base` và DN truyền cho `findById` phải nhất quán. Kiểm thử có dữ liệu phụ thuộc nhiều server nên tạo môi trường độc lập và dọn dữ liệu theo từng test nếu có thao tác ghi.

Nên mở rộng kiểm thử theo các trường hợp:

- Có entry hợp lệ và không có entry; `findById` trả `Optional.empty()` khi không tồn tại.
- `findBySurname` phản ánh đúng mapping `surname → sn` và không lấy ngoài vùng `@Entry.base`.
- Tạo entity mới, kiểm tra DN được tính từ `@DnAttribute` và `@Entry.base`; thử trùng DN.
- Cập nhật một thuộc tính hợp lệ; xác minh schema/ACL và trạng thái đọc lại.
- Xóa một entry thử nghiệm; xác minh không xóa nhầm entry thật.
- Dữ liệu có ký tự đặc biệt trong giá trị RDN/filter; bảo đảm dựng DN/filter an toàn.
- Directory bị mất kết nối, bind sai hoặc chứng chỉ TLS không tin cậy; kiểm tra thông báo lỗi phù hợp.

Kiểm thử với `Mockito` cho service có thể xác nhận logic gọi `repository.findById(...)`, nhưng **không chứng minh** ODM mapping, filter LDAP hoặc kết nối hoạt động. Các hành vi đó cần integration test.

## 11. Câu hỏi tự kiểm tra

1. Vì sao interface đúng là `LdapRepository<PersonEntry>` thay vì `LdapRepository<PersonEntry, Long>`?
2. Annotation `@Id` nào phải import và vì sao DN lại có kiểu `Name`?
3. Với `spring.ldap.base = dc=example,dc=org` và `@Entry.base = ou=people`, DN tương đối của `uid=lan` nên được xây như thế nào?
4. Vai trò của `@DnAttribute(value="uid", index=0)` khác vai trò của `@Attribute(name="uid")` ra sao?
5. Có những cách nào để Spring tạo bean repository, và khi nào cần `@EnableLdapRepositories`?
6. `findById` khác `findByUid` về ý nghĩa của điều kiện tìm kiếm như thế nào?
7. Tại sao `findAll()` không nên dùng tùy tiện với directory lớn, và vì sao không áp dụng trực tiếp `Pageable` kiểu JPA?

**Ghi nhớ:** để có một repository LDAP hoạt động, trước hết cần **entity ODM hợp lệ với `@Entry` và `@Id Name`**, sau đó khai báo **`LdapRepository<Entity>`** và bảo đảm Spring có `ContextSource`/`LdapTemplate` cùng cơ chế quét repository. Hãy nhất quán DN tương đối với base đã cấu hình, định nghĩa ánh xạ thuộc tính theo schema thực, giới hạn phạm vi truy vấn và kiểm chứng với LDAP directory thử nghiệm.

### Tài liệu tham khảo

- Spring Data LDAP Reference: [Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html), quy tắc `LdapRepository<T>`, ID kiểu `Name` và `@EnableLdapRepositories`.
- Spring Data LDAP API: [`LdapRepository<T>`](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapRepository.html), các phương thức CRUD và `findOne/findAll(LdapQuery)`.
- Spring LDAP Reference: [Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html), `@Entry`, `@Id`, `@Attribute` và `@DnAttribute`.
- Spring Data LDAP Reference: [Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html), finder theo method name và truy vấn tùy chỉnh.
- Spring Boot Reference: [LDAP và Spring Data LDAP repositories](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap), starter, kết nối và auto-configuration.
