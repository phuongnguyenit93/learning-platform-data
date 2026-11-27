# CrudRepository cho entity LDAP trong Spring LDAP

## 1. Mục tiêu bài học

Trong hệ thống doanh nghiệp, danh bạ LDAP thường lưu tài khoản nhân viên, nhóm, đơn vị tổ chức và các thuộc tính như tên hiển thị, email, mã người dùng. Khi một ứng dụng Java cần đọc hoặc thay đổi những entry này, Spring LDAP cung cấp hai cách tiếp cận phổ biến: thao tác trực tiếp qua `LdapTemplate` và khai báo repository theo phong cách Spring Data.

Bài này tập trung vào **`CrudRepository` cho entity LDAP** trong module **SPRING_LDAP**. Sau khi học, bạn có thể:

- Giải thích một entity LDAP được ánh xạ từ entry và vì sao **Distinguished Name (DN)** là định danh của entity.
- Cấu hình Spring Data LDAP repository với `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và `@EnableLdapRepositories` khi cần.
- Dùng `save`, `findById`, `findAll`, `existsById`, `count`, `deleteById` và `delete` đúng ngữ nghĩa LDAP.
- Phân biệt `CrudRepository<T, Name>` và `LdapRepository<T>`; biết lúc nào cần dùng `LdapQuery`.
- Nhận diện lỗi về DN, schema, quyền truy cập, kết nối bảo mật, kết quả tìm kiếm và giới hạn của repository.

Để thực hành an toàn, ví dụ dùng cây LDAP giả lập có hậu tố `dc=example,dc=org`. Các thao tác ghi và xóa nên chạy trên **LDAP thử nghiệm** với tài khoản chỉ có quyền cần thiết trong nhánh được phép thay đổi.

## 2. Từ entry LDAP đến repository

LDAP lưu dữ liệu thành các **entry** trong cây thư mục. Mỗi entry có một DN và tập thuộc tính tuân theo schema LDAP.

Ví dụ một người dùng:

```ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
mail: an@example.org
```

Các thành phần chính:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `uid=an` | Relative Distinguished Name (RDN), phân biệt entry với các entry cùng cha | `uid=an` |
| `ou=people` | Nhánh chứa người dùng | Organizational Unit `people` |
| `dc=example,dc=org` | Hậu tố của cây thư mục | Tương ứng miền ví dụ `example.org` |
| `objectClass` | Khai báo tập kiểu và ràng buộc thuộc tính | `inetOrgPerson` |
| `cn`, `sn`, `mail` | Thuộc tính dữ liệu | Tên, họ, địa chỉ thư |

Sơ đồ luồng xử lý:

```text
Service của ứng dụng
    |
    |  save / findById / deleteById ...
    v
PersonRepository (Spring Data LDAP)
    |
    v
Spring LDAP + Object-Directory Mapping (ODM)
    |
    v
LdapTemplate / ContextSource
    |
    |  LDAP Add / Search / Modify / Delete
    v
LDAP server: uid=an,ou=people,dc=example,dc=org
```

**`CrudRepository` không biến LDAP thành cơ sở dữ liệu quan hệ.** Các thao tác CRUD vẫn tuân theo DN, schema, ACL, search scope và tính chất giao thức LDAP. Repository chỉ giúp ứng dụng gọi những thao tác thông dụng thông qua một interface nhất quán.

### 2.1. `CrudRepository` hay `LdapRepository`?

Các interface liên quan:

```java
import javax.naming.Name;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.ldap.repository.LdapRepository;

// Chỉ cần API CRUD chung:
interface BasicPersonRepository extends CrudRepository<DirectoryPerson, Name> {
}

// Lựa chọn thường dùng khi làm việc với LDAP:
interface PersonRepository extends LdapRepository<DirectoryPerson> {
}
```

| Đặc điểm | `CrudRepository<DirectoryPerson, Name>` | `LdapRepository<DirectoryPerson>` |
| --- | --- | --- |
| `save`, `findById`, `findAll`, `deleteById` | Có | Có |
| Kiểu khóa | Truyền tường minh `Name` | Được cố định là `Name` |
| Tìm bằng `LdapQuery` | Không có overload LDAP riêng | Có `findOne(LdapQuery)`, `findAll(LdapQuery)` |
| Phân trang/sắp xếp tự động | Không hỗ trợ với LDAP | Không hỗ trợ với LDAP |
| Khi nên dùng | Nhu cầu CRUD rất cơ bản | Ứng dụng LDAP cần thêm bộ lọc/tìm kiếm |

Ở Spring Data LDAP hiện đại, `LdapRepository<T>` kế thừa `ListCrudRepository<T, Name>`, tức là vẫn kế thừa các hợp đồng của `CrudRepository` nhưng những phương thức trả nhiều phần tử dùng `List`. Trong các phiên bản cũ, kiểu trả về của một số phương thức có thể là `Iterable`; khi viết code, đối chiếu API của phiên bản đang dùng.

**Lưu ý bắt buộc:** entity LDAP phải dùng ID kiểu `javax.naming.Name` (hoặc kiểu con phù hợp), không phải `Long`, `UUID` hay `String` như nhiều ví dụ JPA. Annotation `@Id` phải lấy từ `org.springframework.ldap.odm.annotations.Id`, không phải `org.springframework.data.annotation.Id` hoặc `jakarta.persistence.Id`.

## 3. Chuẩn bị kết nối và dữ liệu thực hành

Ví dụ sau giả định LDAP server đã tồn tại nhánh `ou=people,dc=example,dc=org`, có schema hỗ trợ `inetOrgPerson`, và tài khoản bind được cấp quyền tạo, tìm, sửa, xóa entry trong nhánh này.

### 3.1. Khai báo dependency

Với ứng dụng Spring Boot quản lý phiên bản dependency, thêm starter:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
}
```

Starter cung cấp tích hợp LDAP với Spring Data. Đối với dự án không dùng Boot, cần cấu hình các dependency tương thích của Spring LDAP/Spring Data LDAP, `ContextSource`, `LdapTemplate` và cơ chế bật repository.

### 3.2. Cấu hình `application.yml`

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

- `urls` là địa chỉ máy chủ LDAP. Ví dụ dùng **LDAPS** với chứng chỉ tin cậy.
- `base` là gốc tương đối của các DN mà ứng dụng thao tác. Khi `base` đã là `dc=example,dc=org`, ứng dụng thường truyền `uid=an,ou=people` cho repository thay vì lặp lại toàn bộ hậu tố.
- `username`/`password` đến từ biến môi trường hoặc hệ thống quản lý bí mật; không đưa mật khẩu thật vào mã nguồn.
- Hệ thống phải tin cậy chứng chỉ máy chủ LDAPS. Không vô hiệu hóa kiểm tra TLS để “chữa” lỗi kết nối.

Spring Boot có thể tự cấu hình `LdapContextSource`, `LdapTemplate` và phát hiện repository trong các package được quét. Nếu package repository nằm ngoài vùng quét mặc định, khai báo cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(basePackages = "com.example.directory.repository")
public class LdapRepositoryConfig {
}
```

Chỉ thêm `@EnableLdapRepositories` khi cần kiểm soát phạm vi quét hoặc cấu hình thủ công; tránh khai báo hai cơ chế quét chồng chéo mà không có chủ đích. Nếu ứng dụng sử dụng nhiều Spring Data module (JPA, MongoDB, LDAP), hãy phân chia package và cấu hình rõ repository thuộc module nào.

### 3.3. Chuẩn bị nhánh cha

Nếu nhánh `ou=people` chưa tồn tại, người quản trị có thể tạo trên server thử nghiệm bằng LDIF:

```ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
```

Ví dụ này chỉ mô tả dữ liệu cần có; cách nạp LDIF tùy OpenLDAP, ApacheDS, UnboundID hoặc dịch vụ LDAP của tổ chức. Nếu nhánh cha thiếu, tạo `uid=an,ou=people,...` thường gặp lỗi LDAP `noSuchObject`.

## 4. Định nghĩa entity LDAP với ODM

Đây là phần quyết định repository có hiểu entry hay không. Spring LDAP dùng **Object-Directory Mapping (ODM)** để ánh xạ trường Java và thuộc tính LDAP.

```java
package com.example.directory.model;

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
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "sn")
    private String sn;

    @Attribute(name = "mail")
    private String mail;

    public DirectoryPerson() {
    }

    public Name getDn() {
        return dn;
    }

    public String getUid() {
        return uid;
    }

    public void setUid(String uid) {
        this.uid = uid;
    }

    public String getCn() {
        return cn;
    }

    public void setCn(String cn) {
        this.cn = cn;
    }

    public String getSn() {
        return sn;
    }

    public void setSn(String sn) {
        this.sn = sn;
    }

    public String getMail() {
        return mail;
    }

    public void setMail(String mail) {
        this.mail = mail;
    }
}
```

Giải thích:

1. **`@Entry`** xác định các `objectClass` mà entity quản lý và nhánh `base` của entity. Thuộc tính bắt buộc của schema, chẳng hạn `cn` và `sn` cho `person`, cần có giá trị hợp lệ trước khi tạo.
2. **`@Id private Name dn`** ánh xạ DN của entry. Trong cấu hình trên, DN tương đối thường là `uid=an,ou=people`. Hậu tố `dc=example,dc=org` đã nằm trong `spring.ldap.base`.
3. **`@Attribute(name = "uid")`** ánh xạ giá trị `uid` của entry. Tên thuộc tính LDAP có thể khác tên field Java, vì thế khai báo tường minh giúp người đọc tránh nhầm lẫn.
4. **`@DnAttribute(value = "uid", index = 0)`** liên kết `uid` với thành phần RDN. Khi DN chưa được đặt và mọi thành phần cần thiết đều có thể suy ra, ODM có thể tạo DN từ thuộc tính DN và `@Entry.base`. Với nhiều tầng RDN bổ sung, `index` biểu diễn vị trí trong phần DN được tạo từ các field.
5. **`@DnAttribute` không thay thế `@Attribute`.** Nếu trường cũng phải được lưu làm thuộc tính LDAP thì giữ mapping thuộc tính; `@Transient` chỉ thích hợp khi trường không cần lưu thành thuộc tính riêng.

Trong ví dụ, trước khi gọi `save` để **tạo mới**, object có `dn == null` và `uid` hợp lệ. Sau thao tác tạo thành công, ODM có thể gán lại DN đã tính vào object. Cách này cho phép repository phân biệt entry mới với entry đã tồn tại.

> **Quan trọng:** `uid`, `cn`, `sn`, `mail` phải phù hợp schema và ACL của directory. Một số server áp dụng schema, kiểu viết thuộc tính, overlay hoặc chính sách riêng; mô hình ở trên là ví dụ thực hành, không phải mô hình phổ quát cho mọi LDAP server.

### 4.1. Chọn DN đúng, tránh nhân đôi hậu tố

Với cấu hình `spring.ldap.base = dc=example,dc=org`, ba chuỗi sau không tương đương:

| Giá trị | Diễn giải |
| --- | --- |
| `uid=an,ou=people` | DN tương đối tới context base: phù hợp ví dụ |
| `uid=an,ou=people,dc=example,dc=org` | DN đầy đủ của server: dùng khi công cụ yêu cầu DN tuyệt đối |
| `uid=an` | RDN thiếu nhánh `ou=people` nếu thao tác theo gốc context |

Đừng ghép DN bằng nối chuỗi từ dữ liệu người dùng, ví dụ `"uid=" + input + ",ou=people"`. Ký tự `,`, `+`, `=` và các ký tự đặc biệt khác có quy tắc escaping trong DN. Sử dụng `LdapNameBuilder` để tạo `Name` hợp lệ:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "an")
    .build();
// DN tương đối: uid=an,ou=people
```

Giá trị DN có thể trông khác nhau khi in ra do quy tắc escape/canonicalization; nên so sánh bằng đối tượng `Name` và xác nhận trên directory thay vì chỉ so sánh chuỗi thô.

## 5. Khai báo repository cho entity

Tạo interface dưới package được Spring quét:

```java
package com.example.directory.repository;

import com.example.directory.model.DirectoryPerson;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<DirectoryPerson> {
    // Chưa cần viết implementation.
}
```

Spring Data LDAP tạo implementation tại runtime. Chỉ với interface này, ứng dụng đã có các thao tác CRUD: `save`, `saveAll`, `findById`, `findAll`, `findAllById`, `existsById`, `count`, `delete`, `deleteById` cùng các biến thể xóa hàng loạt.

Nếu muốn bám sát đúng API trừu tượng của `CrudRepository`, có thể khai báo:

```java
import javax.naming.Name;
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository extends CrudRepository<DirectoryPerson, Name> {
}
```

**Hãy chọn một trong hai cách định nghĩa**, theo nhu cầu ứng dụng. Ở các phần tiếp theo, bài dùng bản `LdapRepository<DirectoryPerson>` để có cả phương thức CRUD và tìm kiếm bằng `LdapQuery`.

### 5.1. Bảng phương thức CRUD

| Phương thức | Đầu vào/trả về | Ý nghĩa trong LDAP |
| --- | --- | --- |
| `save(person)` | Entity → entity | Tạo hoặc cập nhật entry, tùy trạng thái entity |
| `saveAll(persons)` | Tập entity → tập đã lưu | Lưu từng entity; không mặc định có giao dịch nguyên tử toàn bộ |
| `findById(dn)` | `Name` → `Optional<DirectoryPerson>` | Đọc entry theo DN |
| `findAll()` | Nhiều entity | Lấy các entry thuộc phạm vi và mapping đã cấu hình; có thể tốn tài nguyên |
| `findAllById(dns)` | Nhiều `Name` → nhiều entity | Tìm theo tập DN |
| `existsById(dn)` | `Name` → `boolean` | Kiểm tra entry có tồn tại hay không |
| `count()` | `long` | Đếm entry khớp phạm vi tìm kiếm |
| `deleteById(dn)` | `Name` → `void` | Xóa entry theo DN |
| `delete(person)` | Entity → `void` | Xóa entry được định danh bởi entity |
| `deleteAll()` | → `void` | Xóa hàng loạt entry phù hợp; cực kỳ rủi ro với directory thật |

Không nên mặc định rằng `deleteById` với entry không tồn tại sẽ luôn im lặng: cách ném ngoại lệ tùy implementation và tình huống. Với `findById`, dùng `Optional` để biểu diễn trường hợp không có dữ liệu, thay vì ép `get()` ngay.

## 6. Thực hành CRUD hoàn chỉnh

Thiết kế một service nhận `uid` từ tầng ứng dụng, tạo DN bằng builder và thực hiện CRUD qua repository. Service chịu trách nhiệm kiểm tra dữ liệu, quyết định phạm vi thao tác và chuyển lỗi phù hợp cho caller.

```java
package com.example.directory.service;

import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import javax.naming.Name;

import com.example.directory.model.DirectoryPerson;
import com.example.directory.repository.PersonRepository;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryService {

    private final PersonRepository repository;

    public PersonDirectoryService(PersonRepository repository) {
        this.repository = repository;
    }

    // Tạo Name tương đối tới spring.ldap.base.
    private Name dnOf(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }
        return LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();
    }

    // CREATE: dn ban đầu là null; ODM tính DN từ uid + @Entry.base.
    public DirectoryPerson create(String uid, String cn, String sn, String mail) {
        dnOf(uid); // Kiểm tra giá trị uid trước khi ghi.
        if (cn == null || cn.isBlank() || sn == null || sn.isBlank()) {
            throw new IllegalArgumentException("cn và sn là bắt buộc");
        }

        DirectoryPerson person = new DirectoryPerson();
        person.setUid(uid);
        person.setCn(cn);
        person.setSn(sn);
        person.setMail(mail);
        return repository.save(person);
    }

    // READ theo DN.
    public Optional<DirectoryPerson> findByUid(String uid) {
        return repository.findById(dnOf(uid));
    }

    // READ kiểm tra tồn tại.
    public boolean exists(String uid) {
        return repository.existsById(dnOf(uid));
    }

    // UPDATE một thuộc tính không thuộc DN của entry đã có.
    public DirectoryPerson updateMail(String uid, String newMail) {
        DirectoryPerson existing = repository.findById(dnOf(uid))
            .orElseThrow(() -> new NoSuchElementException(
                "Không tìm thấy uid=" + uid
            ));
        existing.setMail(newMail);
        return repository.save(existing);
    }

    // DELETE theo DN.
    public void delete(String uid) {
        repository.deleteById(dnOf(uid));
    }

    // Chỉ gọi trên cây thử nghiệm nhỏ hoặc sau khi đã giới hạn dữ liệu.
    public List<DirectoryPerson> findAllForDemo() {
        return repository.findAll();
    }
}
```

Đối với phiên bản API cũ mà `findAll()` chỉ bảo đảm `Iterable`, cần chuyển phần tử sang `List` trong service hoặc trả về `Iterable`; đoạn code trên giả định nhánh Spring Data LDAP hiện đại hỗ trợ `ListCrudRepository`.

### 6.1. Create: `save()` với entity mới

```java
DirectoryPerson created = service.create(
    "an", "An Nguyen", "Nguyen", "an@example.org"
);
System.out.println(created.getDn());
// Kỳ vọng DN tương đối: uid=an,ou=people
```

Quy trình tạo mới:

1. Ứng dụng tạo `DirectoryPerson`, gán `uid`, `cn`, `sn`, `mail`; chưa gán `dn`.
2. Repository nhận thấy entity mới và gọi thao tác thêm entry tương ứng trên LDAP.
3. ODM dùng `@Entry` và `@DnAttribute` để xác định DN, chuẩn bị `objectClass` và các thuộc tính.
4. LDAP server xác nhận schema, quyền truy cập, tính duy nhất của DN và sự tồn tại của entry cha.
5. Nếu thành công, dữ liệu có thể đọc lại bằng `findById`.

`save()` **không phải phép “upsert” không điều kiện**. Với entity có DN rồi, repository thường đi theo nhánh cập nhật; nếu DN đó chưa tồn tại, cập nhật có thể thất bại thay vì tự tạo. Khi DN cần được cấp sẵn từ đầu, phải kiểm soát trạng thái mới/cũ (ví dụ mô hình `Persistable<Name>` có `isNew()` phù hợp), hoặc thao tác tường minh qua `LdapTemplate.create`. Không gán DN chỉ để ép phương thức `save` tạo entry.

Nếu `uid=an,ou=people,...` đã có, tạo lại cùng DN có thể gặp lỗi `entryAlreadyExists`/`nameAlreadyBound`. Trước khi tạo có thể gọi `existsById` để có thông báo thân thiện, nhưng đó chỉ là kiểm tra trước; **server vẫn phải xử lý trường hợp hai request tạo trùng cùng lúc**.

### 6.2. Read: `findById()`, `existsById()`, `findAll()`

```java
Optional<DirectoryPerson> person = service.findByUid("an");

person.ifPresent(p ->
    System.out.println(p.getCn() + " <" + p.getMail() + ">")
);

boolean found = service.exists("an");
```

`findById` là thao tác phù hợp khi caller đã biết DN. Nó không tương đương tìm theo bất kỳ thuộc tính nào: nếu `uid` không nằm ở RDN hoặc các entry được phân bố ở nhiều nhánh, không thể tự suy một DN duy nhất chỉ từ giá trị `uid`.

`findAll()` và `count()` tiện trong ví dụ nhỏ nhưng có thể dẫn đến tìm kiếm rộng trên directory lớn, trả về nhiều entry, đụng giới hạn kích thước kết quả của server hoặc thiếu quyền xem một số thuộc tính. Trong nghiệp vụ thật, nên dùng truy vấn có phạm vi và bộ lọc, cùng cơ chế giới hạn kết quả phù hợp.

### 6.3. Update: tải entity đang có rồi `save()`

```java
DirectoryPerson changed =
    service.updateMail("an", "an.nguyen@example.org");

System.out.println(changed.getMail());
// an.nguyen@example.org
```

Ở đây repository đọc đúng DN trước khi thay đổi `mail`. Entity đã tải có `dn` nên `save()` đi theo hướng cập nhật. Cách này rõ ràng hơn việc tạo một object mới chỉ chứa `uid` và `mail`: object thiếu các thuộc tính khác có thể làm thay đổi/xóa thuộc tính ngoài dự kiến, tùy hành vi ánh xạ và cập nhật.

**Không tự ý sửa `uid` trong cùng luồng cập nhật email.** `uid` thuộc DN; đổi nó là yêu cầu đổi tên hoặc di chuyển entry, có thể ảnh hưởng tham chiếu DN ở nhóm, ACL và ứng dụng khác. ODM hỗ trợ xử lý thay đổi trường gắn `@DnAttribute` trong một số trường hợp, nhưng hãy xem đây là nghiệp vụ riêng cần kiểm chứng kỹ trên LDAP server thực tế.

### 6.4. Delete: xóa đúng DN

```java
service.delete("an");
boolean stillExists = service.exists("an");
// Kỳ vọng false nếu xóa thành công.
```

Xóa LDAP entry thường yêu cầu entry không còn con. Đối với nhánh `ou=people`, một user leaf thường xóa được nếu ACL cho phép, còn xóa một OU có entry con sẽ thất bại hoặc đòi công cụ/quyền riêng. Trong ứng dụng nghiệp vụ, nên cân nhắc **vô hiệu hóa tài khoản** hoặc quy trình phê duyệt trước khi xóa vĩnh viễn.

Không dùng `deleteAll()` để “dọn dữ liệu” trên directory dùng chung. Phương thức này có thể tác động hàng loạt entry trong phạm vi mà repository được phép nhìn thấy, đồng thời khiến hệ thống khác mất tham chiếu.

## 7. Tìm kiếm ngoài khóa DN bằng `LdapRepository`

`CrudRepository` mạnh khi biết ID. Tuy nhiên, nhiều tác vụ LDAP cần tìm theo thuộc tính, ví dụ “mọi người có họ Nguyen” hoặc “người dùng có email cụ thể”.

`LdapRepository<DirectoryPerson>` có overload nhận `LdapQuery`:

```java
import java.util.List;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery bySurname = LdapQueryBuilder.query()
    .base("ou=people")
    .where("sn").is("Nguyen");

List<DirectoryPerson> results = repository.findAll(bySurname);
```

Giá trị `base("ou=people")` ở đây được hiểu tương đối với context base `dc=example,dc=org`. Tìm kiếm có bộ lọc và phạm vi rõ ràng giúp hạn chế dữ liệu đọc. Nếu đã thiết lập phạm vi ở nơi khác, hãy xác minh cách kết hợp search base của truy vấn với `@Entry.base` theo phiên bản đang dùng để không quét nhầm nhánh.

Tìm một entry:

```java
LdapQuery byUid = LdapQueryBuilder.query()
    .base("ou=people")
    .where("uid").is("an");

Optional<DirectoryPerson> one = repository.findOne(byUid);
```

`findOne(LdapQuery)` thích hợp khi bộ lọc dự kiến khớp tối đa một entry. Nếu nhiều entry cùng khớp, phương thức có thể ném `IncorrectResultSizeDataAccessException`; đừng coi `findOne` như thao tác “lấy phần tử đầu tiên bất kỳ”.

Khi giá trị lọc đến từ người dùng, dùng API như `.where("uid").is(userInput)` để framework xử lý escape giá trị. Tránh nội suy trực tiếp vào chuỗi lọc như `"(uid=" + userInput + ")"`, vì ký tự đặc biệt có thể làm sai bộ lọc hoặc dẫn đến **LDAP filter injection**. Phải kiểm soát cả tên thuộc tính và nhánh được phép tìm; việc escape giá trị không thay thế phân quyền.

### 7.1. Repository không cung cấp phân trang và sắp xếp như JPA

Mặc dù Spring Data có `PagingAndSortingRepository` và `Pageable` cho nhiều loại kho dữ liệu, **Spring Data LDAP repository không hỗ trợ paging/sorting theo hợp đồng chung này**. Đừng thêm `Pageable` vào API rồi kỳ vọng kết quả hoạt động như cơ sở dữ liệu quan hệ.

Với tập dữ liệu lớn, cần thiết kế riêng theo khả năng của LDAP server và giao thức (ví dụ các LDAP controls cho server-side sorting/paged results nếu server hỗ trợ), thường dùng `LdapTemplate` hoặc API ở mức thấp hơn. Cần kiểm chứng cách xử lý cookie, giới hạn truy vấn và ACL trên server đích.

## 8. Cơ chế `save` và các tình huống cần đặc biệt chú ý

`save` là phương thức quan trọng nhất và cũng dễ gây nhầm lẫn nhất khi chuyển từ JPA sang LDAP.

| Trạng thái entity khi gọi `save` | Hành vi thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| `dn == null`, có `@DnAttribute` đủ tạo DN | Tạo entry | `@Entry.base`, RDN, schema, entry cha |
| `dn != null`, entry thực sự tồn tại | Cập nhật entry | Quyền `modify`, thuộc tính bắt buộc, dữ liệu cũ |
| `dn != null`, entry không tồn tại | Có thể thử cập nhật rồi báo lỗi | Đừng giả định tự upsert |
| Tạo mới nhưng ứng dụng đã tự gán DN | Có thể bị hiểu là entity cũ | Kiểm soát `isNew` hoặc gọi `LdapTemplate.create` |
| Entity đổi giá trị thuộc RDN | Có khả năng cần rename/move entry | Tham chiếu DN, ACL, đồng bộ, tác động tới nhóm |

Trong trường hợp cần gán ID thủ công nhưng vẫn dùng repository để thêm mới, `Spring Data` cung cấp interface `Persistable<Name>` với `getId()` và `isNew()`. Đây là cách biểu diễn vòng đời entity khi `dn != null` không đủ để quyết định tạo hay sửa. Cờ trạng thái `isNew` phải được quản lý đúng sau khi lưu/tải entity và **không** được ánh xạ thành thuộc tính LDAP ngoài ý muốn; nếu thiết kế sai, lần lưu sau có thể tiếp tục cố tạo entry trùng.

Khi cần thao tác rõ ràng hơn:

```java
// Các API ODM mức thấp hơn, có thể dùng khi nghiệp vụ cần phân biệt
// create và update một cách tường minh:
ldapTemplate.create(newPerson);
ldapTemplate.update(existingPerson);
ldapTemplate.delete(existingPerson);
```

Mã trên minh họa các phương thức của `LdapTemplate`, giả định đã inject bean và ánh xạ entity hợp lệ. Repository và `LdapTemplate` là hai lớp trừu tượng bổ sung cho nhau; một ứng dụng có thể dùng cả hai theo yêu cầu nghiệp vụ.

## 9. Kiểm thử CRUD trên directory cô lập

Một bài kiểm tra thực sự phải gửi lệnh tới LDAP server thử nghiệm có schema, OU và tài khoản bind phù hợp. Mock repository chỉ chứng minh logic service; nó không kiểm tra DN mapping, attribute mapping, lỗi schema, SSL hay ACL.

Ví dụ kiểm thử tích hợp với JUnit 5 và Spring Boot (giả định `PersonRepository` trỏ đến LDAP thử nghiệm và đã có nhánh `ou=people`):

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PersonRepositoryIntegrationTest {

    @Autowired PersonDirectoryService service;
    @Autowired PersonRepository repository;

    @Test
    void createReadUpdateDelete() {
        String uid = "test" + UUID.randomUUID()
            .toString().replace("-", "").substring(0, 10);
        Name dn = null;

        try {
            DirectoryPerson created =
                service.create(uid, "Test User", "User", "old@example.org");
            dn = created.getDn();

            assertThat(dn).isNotNull();
            assertThat(repository.existsById(dn)).isTrue();
            assertThat(service.findByUid(uid)).isPresent();

            DirectoryPerson updated =
                service.updateMail(uid, "new@example.org");
            assertThat(updated.getMail()).isEqualTo("new@example.org");
            assertThat(service.findByUid(uid)).get()
                .extracting(DirectoryPerson::getMail)
                .isEqualTo("new@example.org");

            service.delete(uid);
            assertThat(service.findByUid(uid)).isEmpty();
        } finally {
            // Chỉ xóa entry có uid ngẫu nhiên do test này tạo.
            if (dn != null && repository.existsById(dn)) {
                repository.deleteById(dn);
            }
        }
    }
}
```

Các trường hợp nên kiểm tra thêm trong môi trường tích hợp:

1. **Tạo trùng DN**: thử lưu entry mới với cùng `uid`; xác nhận thông báo lỗi và trạng thái directory sau thất bại.
2. **Không có quyền ghi**: bind tài khoản chỉ đọc; `findById` có thể thành công nhưng `save`/`deleteById` phải bị từ chối.
3. **Thiếu thuộc tính bắt buộc**: bỏ `sn` hoặc `cn`; server phải từ chối entry không hợp schema.
4. **DN chứa ký tự đặc biệt**: dùng `uid` có dấu phẩy hoặc dấu cộng trong môi trường thử nghiệm; xác nhận builder tạo DN hợp lệ.
5. **Kết quả không tồn tại**: `findById` trả `Optional.empty()`; kiểm tra ngoại lệ từ thao tác ghi/xóa tương ứng.
6. **Phạm vi tìm kiếm**: bảo đảm repository không đọc hoặc sửa entry ngoài `ou=people` mà ứng dụng được phép quản lý.

Test thật nên sử dụng LDAP cô lập như máy chủ test container hoặc LDAP embedded có nạp LDIF, sử dụng dữ liệu riêng và dọn dẹp sau test. Không chạy các ca `deleteAll`, sửa DN hàng loạt hoặc thử quyền phá hoại trên directory chia sẻ.

## 10. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `No qualifying bean of type PersonRepository` | Chưa kích hoạt hoặc quét sai package repository | Kiểm tra starter, phạm vi quét, `@EnableLdapRepositories` |
| Entity không map được | Thiếu `@Entry`/`@Id`, dùng nhầm `@Id` của Spring Data/JPA | Kiểm tra annotation từ `org.springframework.ldap.odm.annotations` |
| `save` của người mới báo `noSuchObject` | Thử update DN chưa tồn tại; hoặc OU cha chưa có | Kiểm tra trạng thái entity mới, DN và cây LDAP |
| Tạo báo `entryAlreadyExists` | DN đã có | Xác minh RDN duy nhất, luồng tạo đồng thời |
| Báo `objectClassViolation` | Thiếu thuộc tính bắt buộc hoặc khai báo objectClass sai | Đối chiếu schema server và `@Entry` |
| Báo `insufficientAccessRights` | Tài khoản bind thiếu quyền `add`, `modify`, `delete` hoặc `search` | Kiểm tra ACL của DN đích và quyền theo thao tác |
| Không tìm thấy entry dù LDAP có dữ liệu | Dùng DN tuyệt đối khi context đã có base; sai OU, search scope hoặc filter | So sánh DN tương đối, DN đầy đủ và phạm vi query |
| `findAll` chậm hoặc trả thiếu dữ liệu | Truy vấn rộng, giới hạn server, thiếu quyền xem, bộ lọc chưa có index | Giới hạn base/filter, xem log server, thiết kế truy vấn phù hợp |
| Lỗi bắt tay LDAPS | Chứng chỉ không tin cậy hoặc sai hostname | Kiểm tra truststore, hostname và chứng chỉ máy chủ |
| Xóa OU báo `notAllowedOnNonLeaf` | Entry có entry con | Xem cấu trúc cây; không xóa đệ quy tùy tiện |

Spring LDAP có cơ chế chuyển đổi nhiều lỗi JNDI/LDAP thành hệ ngoại lệ của Spring. Nghiệp vụ nên bắt và chuyển các lỗi **dự kiến** thành thông báo phù hợp (không tìm thấy, trùng DN, thiếu quyền); tránh `catch (Exception)` rồi bỏ qua lỗi ghi dữ liệu. Ghi log mã lỗi và ngữ cảnh thao tác ở mức vừa đủ; không ghi mật khẩu bind, credential của người dùng, mã thông báo hay thông tin cá nhân không cần thiết.

## 11. Quy tắc triển khai an toàn và có hiệu năng

### 11.1. Quyền và kết nối

- Tách tài khoản bind đọc/ghi theo yêu cầu nghiệp vụ và áp dụng **least privilege**. Một API chỉ để tra cứu danh bạ không nên có quyền xóa entry.
- Dùng LDAPS hoặc StartTLS theo hạ tầng hiện có; yêu cầu chứng chỉ được xác thực, quản lý secret bên ngoài repository mã nguồn.
- Chặn hoặc kiểm soát các lệnh xóa rộng, đặc biệt `deleteAll`, `deleteAllById` với danh sách không đáng tin cậy.
- Chỉ chấp nhận nhánh DN và tập thuộc tính được nghiệp vụ cho phép; kiểm tra đầu vào trước khi tạo DN hoặc truy vấn.

### 11.2. Hiệu năng và tính nhất quán

- Giới hạn nhánh tìm kiếm và dùng filter cụ thể; tránh gọi `findAll()` trong request phục vụ người dùng trên thư mục lớn.
- Xem xét thuộc tính đã được lập index tại LDAP server cho các bộ lọc xuất hiện thường xuyên, ví dụ `uid` hoặc `mail`.
- Không giả định `saveAll()` và `deleteAll()` là một transaction toàn cục. LDAP có thể hoàn tất một phần rồi thất bại; nếu cần quy trình nhiều bước, thiết kế cơ chế bù trừ hoặc phục hồi rõ ràng.
- LDAP là nguồn dữ liệu dùng chung. Dữ liệu có thể bị hệ thống khác thay đổi giữa `findById` và `save`; nếu yêu cầu chống ghi đè đồng thời, cần chiến lược kiểm soát thích hợp với LDAP server, không tự suy diễn có optimistic locking như JPA.
- Trước khi sửa RDN hoặc di chuyển entry, kiểm tra quan hệ thành viên nhóm, chính sách truy cập, dữ liệu cache và ứng dụng đang tham chiếu DN cũ.

### 11.3. Ranh giới của repository

Repository phù hợp nhất với CRUD entity được ánh xạ rõ ràng, thao tác theo DN và các tìm kiếm LDAP phổ biến. Cần đến `LdapTemplate`, `LdapClient` hoặc API LDAP khác khi phải điều khiển chi tiết search scope, controls, đổi tên entry, thao tác thuộc tính đa trị, cập nhật theo điều kiện hoặc xử lý server-specific behavior. Không cố ép mọi nghiệp vụ thư mục thành các phương thức repository chung.

## 12. Bài thực hành tự kiểm tra

**Bối cảnh:** Nhánh `ou=people,dc=example,dc=org` đã tồn tại. Bạn được cấp tài khoản bind với quyền tạo, đọc, sửa, xóa một nhóm tài khoản thử nghiệm.

**Yêu cầu:**

1. Tạo `uid=lan` với `cn=Lan Tran`, `sn=Tran`, `mail=lan@example.org` thông qua `PersonRepository.save`.
2. Dùng `findById` với một đối tượng `Name` hợp lệ để đọc lại và kiểm tra `sn`.
3. Đổi `mail` thành `lan.tran@example.org` mà không đổi `uid` hoặc DN.
4. Dùng `LdapRepository.findAll(LdapQuery)` để tìm người có `sn=Tran` trong `ou=people`.
5. Xóa entry thử nghiệm bằng `deleteById`; xác nhận `existsById` trả `false`.

**Kết quả mong đợi:** Khi kiểm tra bằng LDAP client, entry được tạo có DN đầy đủ `uid=lan,ou=people,dc=example,dc=org`, thuộc tính hợp schema và được cập nhật/xóa chính xác. Trường `dn` trong entity dùng dạng DN phù hợp với context base. Nếu bất kỳ bước nào thất bại, sử dụng bảng lỗi ở mục 10 để xác định vấn đề trước khi thử lại.

**Câu hỏi suy ngẫm:**

- Tại sao `CrudRepository<DirectoryPerson, Long>` không đúng cho Spring Data LDAP?
- Điều gì xảy ra nếu bạn gán sẵn `dn` cho một entity mới rồi gọi `save`?
- Vì sao `findById(dn)` và tìm theo `mail` là hai bài toán khác nhau?
- Vì sao `saveAll` không đồng nghĩa với ghi nguyên tử cả danh sách?
- Khi nào cần dùng `LdapTemplate` thay vì repository?

## 13. Tổng kết

`CrudRepository` cung cấp cách thao tác CRUD nhất quán cho entity LDAP, nhưng **DN là ID**, **ODM quyết định ánh xạ**, và **LDAP server quyết định quy tắc dữ liệu, quyền, tìm kiếm và cập nhật**. Trong Spring LDAP, lựa chọn thực tế thường là `LdapRepository<Entity>`: nó thừa hưởng API CRUD và có thêm truy vấn LDAP chuyên biệt. Muốn triển khai đáng tin cậy, hãy kiểm soát rõ DN tương đối, trạng thái mới/cũ khi `save`, search base, schema, TLS, ACL và phạm vi thao tác hàng loạt.

### Tài liệu tham khảo chính thức

- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring Data LDAP — Usage](https://docs.spring.io/spring-data/ldap/reference/ldap/usage.html)
- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html)
- [Spring LDAP — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html)
- [Spring Boot — LDAP and Spring Data LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html)
