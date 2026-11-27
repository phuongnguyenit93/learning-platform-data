# Kiểm thử vòng đời object qua directory trong Spring LDAP ODM

## 1. Vì sao cần kiểm thử toàn bộ vòng đời object?

Khi sử dụng **Spring LDAP Object-Directory Mapping (ODM)**, ứng dụng làm việc với một entity Java thay vì tự tạo mọi đối tượng `Attributes` hoặc `ModificationItem`. Một ví dụ phổ biến là hồ sơ nhân viên được lưu dưới dạng LDAP entry `inetOrgPerson`. Lập trình viên có thể gọi `create(person)`, `findByDn(dn, Person.class)`, `update(person)` rồi `delete(person)`.

Nhưng việc các lời gọi Java không ném ngoại lệ **chưa đủ để chứng minh toàn bộ cơ chế ánh xạ đúng**. Cần kiểm tra trực tiếp trạng thái trên LDAP directory: DN và object classes có đúng không, thuộc tính đã được lưu chưa, object đọc lại có mang đúng giá trị không, update có giữ các trường không liên quan không, và delete có thực sự loại bỏ entry đích không.

Một kiểm thử vòng đời điển hình:

~~~text
Dữ liệu thử nghiệm có DN riêng
           |
           v
    Xây ODM entity
           |
           v
       CREATE
           |
           v
   READ BACK FROM LDAP
           |
           v
  UPDATE MAPPED ATTRIBUTE
           |
           v
   READ BACK AGAIN
           |
           v
       DELETE
           |
           v
 VERIFY ENTRY IS ABSENT
           |
           v
  CLEANUP / AUDIT RESULT
~~~

Chủ đề này thuộc chương **ODM operations** của module **Spring LDAP**. Kiến thức liên quan gồm DN/RDN, schema và object class, filter/search scope, `LdapTemplate` hoặc `LdapClient`, cấu hình `ContextSource`, TLS, pooling, ACL và phân loại lỗi LDAP.

**Mục tiêu học tập:**

1. Mô tả chính xác vòng đời **Create → Read → Update → Delete** của một LDAP ODM entity.
2. Phân biệt **unit test cho Java mapping** với **integration test trên directory thật**.
3. Viết một entity có `@Entry`, `@Id`, `@Attribute`, `@Transient` và kiểm tra round-trip.
4. Dùng DN riêng và kiểm soát dữ liệu fixture để tránh sửa/xóa nhầm tài khoản khác.
5. Kiểm tra dữ liệu trực tiếp trên LDAP, không chỉ so sánh object trong bộ nhớ.
6. Phân tích thất bại do schema, quyền truy cập, trùng DN, kết nối/TLS và thay đổi đồng thời.
7. Dọn dẹp entry thử nghiệm đúng quyền sở hữu và thiết kế test có thể chạy lặp lại.

> **Phạm vi:** Những ví dụ trong bài dành cho **LDAP server hoặc container thử nghiệm**, không được chạy thao tác tạo/sửa/xóa trên directory production. Kiểm thử tích hợp cần tài khoản chỉ có quyền trong OU dành cho test.

## 2. Chuẩn bị directory và dữ liệu mẫu

Giả sử LDAP server thử nghiệm có cây:

~~~text
dc=example,dc=org
|
+-- ou=people
|   |
|   +-- uid=alice                (entry test hiện có)
|   +-- uid=bob                  (entry test hiện có)
|
+-- ou=groups
|   +-- cn=developers
|
+-- ou=system
    +-- cn=directory-reader
    +-- cn=directory-editor
~~~

Thao tác tạo user mới cần entry cha `ou=people,dc=example,dc=org` **đã tồn tại**. Đừng mặc định LDAP Add tự tạo OU cha.

Một entry `inetOrgPerson` mẫu:

~~~ldif
dn: uid=odmtest01,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: odmtest01
cn: ODM Test User
sn: User
mail: odmtest01@example.org
description: spring-ldap-odm-lifecycle-test
~~~

### 2.1. Chọn DN tương đối và DN đầy đủ

Nếu `ContextSource.base` được cấu hình:

~~~text
dc=example,dc=org
~~~

thì DN tương đối mà ứng dụng truyền cho nhiều API `LdapTemplate` là:

~~~text
uid=odmtest01,ou=people
~~~

DN đầy đủ trên LDAP server là:

~~~text
uid=odmtest01,ou=people,dc=example,dc=org
~~~

Không cộng thêm `dc=example,dc=org` vào DN Java khi nó đã nằm ở base của `ContextSource`; nếu làm vậy, tìm kiếm hoặc ghi có thể nhằm sai vị trí.

**Tạo DN bằng API có cấu trúc:**

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "odmtest01")
        .build();
~~~

Không tự nối DN từ một UID bên ngoài vì dấu phẩy, dấu cộng và các ký tự đặc biệt có ý nghĩa trong DN. `LdapNameBuilder` xử lý escaping RDN, nhưng không thay quy tắc validation UID.

### 2.2. Kiểm thử không dùng UID cố định giữa các lần chạy

Nếu mọi test đều tạo `uid=odmtest01` thì lần chạy sau có thể gặp LDAP result code **68 — entryAlreadyExists** chỉ vì lần trước chưa cleanup. Hai job chạy song song cũng có thể xung đột.

Tạo UID riêng cho mỗi lượt:

~~~java
import java.util.UUID;

String uid = "odm-it-"
        + UUID.randomUUID().toString()
                .replace("-", "")
                .substring(0, 12);
~~~

UID có thể có dạng `odm-it-5fa1c8d42eab`. Đây là định danh **dành riêng cho test**, không phải cách cấp UID cho tài khoản nhân viên thật.

Dù xác suất trùng UUID rất thấp, một test an toàn vẫn cần xử lý trường hợp DN đã tồn tại và **không được xóa entry chưa xác nhận là do test sở hữu**.

### 2.3. Định nghĩa “thành công” cho từng bước

| Bước | Dấu hiệu trong Java | Bằng chứng từ LDAP directory |
| --- | --- | --- |
| Create | `ldapTemplate.create(entity)` trở về bình thường | Entry tồn tại tại đúng DN, object classes và attributes đúng |
| Read | `findByDn(...)` trả object | Những field mapped nhận đúng giá trị server |
| Update | `ldapTemplate.update(entity)` trở về bình thường | Đọc lại từ server thấy giá trị mới và các trường cần giữ không mất |
| Delete | `ldapTemplate.delete(entity)` trở về bình thường | Tìm kiếm/lookup được ủy quyền xác nhận entry đích đã vắng |
| Cleanup | Job hoàn tất hoặc thất bại | Không còn entry thử nghiệm do job tạo, hoặc có bản ghi cần xử lý |
| Failed/Unknown | Có ngoại lệ/timeout | Không tự kết luận trạng thái trước khi xác minh |

Với tình huống **mất kết nối sau khi gửi LDAP Add/Modify/Delete**, ứng dụng có thể không biết server đã thực hiện thao tác hay chưa. Đây là trạng thái **UNKNOWN**, không đồng nghĩa thất bại chắc chắn.

## 3. Entity ODM cần ánh xạ chính xác

Dùng một entity Java rõ ràng với các annotation Spring LDAP:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

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

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    @Attribute(name = "description")
    private String description;

    @Transient
    private String displayLabel;

    public DirectoryPerson() {
        // Constructor không tham số cho ODM.
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

    public String getDescription() { return description; }
    public void setDescription(String description) {
        this.description = description;
    }

    public String getDisplayLabel() { return displayLabel; }
    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }
}
~~~

### 3.1. Annotation có ý nghĩa gì?

| Annotation | Ý nghĩa ODM | Điều không được suy ra |
| --- | --- | --- |
| `@Entry` | Gắn entity với base và object classes | Không tự tạo OU, không cấp quyền ghi |
| `@Id` | Field DN của entry | Không phải ID tự tăng như database SQL |
| `@Attribute(name="uid")` | Map UID Java ↔ LDAP `uid` | Không tự bảo đảm uniqueness toàn subtree |
| `@Attribute(name="cn")` | Map commonName ↔ `cn` | Server vẫn kiểm tra syntax/MUST |
| `@Attribute(name="sn")` | Map surname ↔ `sn` | Không thay thế schema của `person` |
| `@Attribute(name="mail")` | Map email ↔ `mail` | Không tự xác minh email nhận được thư |
| `@Attribute(name="description")` | Gắn nhãn ownership/fixture test | Không phải token bảo mật hoặc chứng cứ duy nhất |
| `@Transient` | Bỏ field khỏi mapping LDAP | Không tự ẩn field khỏi JSON hoặc log |

Trong schema thông dụng, `inetOrgPerson` kế thừa `person`, yêu cầu `cn` và `sn`. Ngoài ra, tổ chức có thể triển khai schema mở rộng, naming rules hoặc ACL khác; test phải sử dụng **schema server mục tiêu**, không chỉ tin vào annotation Java.

### 3.2. Vì sao có trường description?

Test tạo một giá trị mô tả riêng, ví dụ:

~~~text
description = "spring-ldap-odm-lifecycle-test:5fa1c8d42eab"
~~~

Nó giúp người vận hành nhận biết entry phục vụ test và hỗ trợ kiểm tra quyền sở hữu trước cleanup. Tuy nhiên, **description không được coi là một khóa xác thực đáng tin cậy**: attribute có thể bị chỉnh bởi tài khoản khác. Kết hợp DN test riêng, OU riêng, quyền ACL hạn chế, token của fixture và quy trình xác minh trước Delete.

### 3.3. @Transient dùng để test mapping không ghi nhầm

`displayLabel` chỉ dùng để hiển thị, được tính từ `commonName` và `uid`. Nó **không** phải attribute LDAP khi thực hiện ODM Create/Update và không được tự nạp từ LDAP qua ODM Find.

Đừng nhầm Spring LDAP `org.springframework.ldap.odm.annotations.Transient` với Java keyword `transient`, JPA `@Transient` hoặc Jackson `@JsonIgnore`. Những cơ chế khác nhau có mục đích khác nhau và cần import đúng.

## 4. Mô hình vòng đời và trạng thái thật

Trong ODM, vòng đời của **Java object** không phải vòng đời của **entry trên server**:

~~~text
new DirectoryPerson()
      |
      | setDn, setUid, setCommonName, ...
      v
Entity mới chỉ trong RAM
      |
      | ldapTemplate.create(entity)
      v
Entry được tạo ở LDAP (nếu server chấp nhận)
      |
      | ldapTemplate.findByDn(dn, DirectoryPerson.class)
      v
Entity mới được nạp từ LDAP
      |
      | đổi mail / description trên entity vừa đọc
      v
Java object đã sửa trong RAM
      |
      | ldapTemplate.update(entity)
      v
Entry LDAP được cập nhật (nếu server chấp nhận)
      |
      | findByDn lần nữa
      v
Entity đọc lại từ trạng thái server
      |
      | ldapTemplate.delete(entity)
      v
LDAP Delete entry theo DN
      |
      | query xác minh vắng entry
      v
Đã kết thúc vòng đời entry thử nghiệm
~~~

**Tất cả lời gọi set field đều diễn ra trong RAM.** Chúng không tự gửi LDAP Modify. Sự khác biệt giữa “đối tượng đã được sửa” và “directory đã cập nhật” phải được thể hiện rõ trong test.

### 4.1. Không nhầm Create, Update và Delete

| Tác vụ | API ODM Spring LDAP | Ý nghĩa LDAP |
| --- | --- | --- |
| Tạo entry mới | `ldapTemplate.create(person)` | Add |
| Đọc theo DN | `ldapTemplate.findByDn(dn, DirectoryPerson.class)` | Lookup/Search phù hợp |
| Ghi thay đổi mapped fields | `ldapTemplate.update(person)` | Modify (tùy cơ chế ODM) |
| Xóa entry từ entity | `ldapTemplate.delete(person)` | Delete |
| Thao tác attribute trực tiếp | `modifyAttributes(...)` | Modify không qua mapping entity |
| Đổi DN/RDN | API rename/Modify DN tương ứng | Không nên diễn giải thành sửa một thuộc tính đơn giản |

`create` **không phải upsert** và `delete` **không phải xóa tất cả entry con**. Cần xác minh sơ đồ DN, schema và quyền trước khi test.

### 4.2. Unit test không thay thế integration test

Một unit test có thể kiểm tra các annotation và setter của `DirectoryPerson` mà **không có LDAP server**. Nó không thể khẳng định server chấp nhận `inetOrgPerson`, duy trì `mail` sau Modify hoặc thực thi ACL.

Một integration test phải truy cập một LDAP directory thật hoặc một test LDAP server được khởi chạy riêng, dùng đúng object classes, quyền và cấu hình kết nối. Nếu chỉ mock `LdapTemplate`, kết quả chỉ chứng minh **Java code gọi đúng method**, không chứng minh dữ liệu đã được tạo/cập nhật/xóa.

## 5. Cấu hình Spring LDAP cho môi trường kiểm thử

Ví dụ Java Config nhận URL, base và credentials qua property:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapTestConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${test.ldap.url}") String url,
            @Value("${test.ldap.base}") String base,
            @Value("${test.ldap.bind-dn}") String bindDn,
            @Value("${test.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

~~~yaml
# application-test.yml — cấu hình minh họa cho LDAP test
test:
  ldap:
    url: ${LDAP_TEST_URL:ldaps://ldap-test.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_TEST_BIND_DN}
    bind-password: ${LDAP_TEST_BIND_PASSWORD}
~~~

Nhóm `test.ldap.*` trong ví dụ **do ứng dụng tự định nghĩa**, không phải property mặc định chung của Spring Boot. Khi dùng auto-configuration LDAP của Spring Boot, có thể dùng các thuộc tính `spring.ldap.*` phù hợp với dependency; tránh khai báo bean thủ công trùng bean auto-config mà không biết bean nào được inject.

### 5.1. Để test thực sự an toàn

- Dùng **directory test** tách khỏi production hoặc OU sandbox riêng có ACL phù hợp.
- Tài khoản writer được phép Add/Modify/Delete **chỉ entry trong vùng test**.
- Tài khoản reader được cấp quyền Search/Lookup cần thiết để kiểm tra trạng thái.
- Dùng LDAPS với chứng chỉ và hostname tin cậy hoặc StartTLS đúng quy trình trước simple bind.
- Lấy password từ secret manager/biến môi trường, không commit hoặc log.
- Kiểm tra truststore và certificate; không vô hiệu hóa xác thực TLS cho nhanh.
- Không để test tự chạy với cấu hình production nếu biến môi trường test còn thiếu.

**`ContextSource.getReadWriteContext()` không tự cấp quyền ghi.** LDAP server mới là nơi thực thi ACL theo bind identity.

### 5.2. Cẩn thận với caching và pooling

Nếu ứng dụng hoặc test dùng pool, việc gọi `close()` theo framework có thể trả context về pool chứ không đồng nghĩa đóng TCP socket ngay. Điều đó không làm thay đổi kết quả kiểm tra Create/Update/Delete.

Không dùng một LDAP context bị bind bằng danh tính admin để kiểm tra hành vi của reader account. Với StartTLS/pooling, cần xác nhận khả năng tương thích và không để trạng thái session/credentials bị tái sử dụng sai.

## 6. Bước Create: kiểm tra trên server sau khi ghi

Khởi tạo entity với một DN mới và các field cần thiết:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "odm-it-5fa1c8d42eab";

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();

DirectoryPerson person = new DirectoryPerson();
person.setDn(dn);
person.setUid(uid);
person.setCommonName("ODM Test User");
person.setSurname("User");
person.setEmail(uid + "@example.org");
person.setDescription("spring-ldap-odm-lifecycle-test:5fa1c8d42eab");
person.setDisplayLabel("LOCAL PREVIEW");

ldapTemplate.create(person);
~~~

### 6.1. Điều gì cần xác minh sau Create?

**Không chỉ** kiểm tra rằng `create(person)` không ném exception. Đọc lại trực tiếp bằng DN:

~~~java
import org.springframework.ldap.core.DirContextOperations;

DirContextOperations created =
        ldapTemplate.lookupContext(dn);

String actualUid = created.getStringAttribute("uid");
String actualCn = created.getStringAttribute("cn");
String actualMail = created.getStringAttribute("mail");
String actualDescription =
        created.getStringAttribute("description");
~~~

Đối chiếu:

- `uid` trùng UID được dùng để dựng RDN.
- `cn`, `sn` tồn tại và khớp dữ liệu đầu vào.
- `mail` đúng, trừ trường hợp schema/server có quy tắc chuẩn hóa đã được tài liệu hóa.
- `description` chứa marker test đã được đặt.
- `objectClass` chứa những giá trị cần thiết, so sánh theo **tập**, không dựa vào thứ tự.
- `displayLabel` **không được ODM tự ghi thành LDAP attribute**.

Nếu một attribute không đọc được, cần xét ACL và returning attributes; không suy ngay rằng thao tác Create thất bại chỉ vì tài khoản đọc không thấy trường.

### 6.2. Kiểm tra ngoài ODM để tránh test cùng một giả định sai

`ldapTemplate.findByDn` dùng cùng cơ chế ODM; nếu dùng nó để vừa ghi vừa kiểm chứng, có thể cùng che một lỗi mapping. Nên có ít nhất một assertion **độc lập với entity ODM** qua `lookupContext` hoặc `ldapsearch`. Mục đích là xem **dữ liệu thật trên server**.

Đọc bằng identity chỉ có quyền đọc nếu muốn chứng minh hệ thống downstream có thể thấy entry sau Create, thay vì chỉ tài khoản writer nhìn thấy.

## 7. Bước Read: verify mapping vào entity mới

Sau khi Create, dùng ODM Find:

~~~java
DirectoryPerson loaded =
        ldapTemplate.findByDn(dn, DirectoryPerson.class);

if (loaded == null) {
    throw new IllegalStateException("Entry was not loaded");
}

String loadedUid = loaded.getUid();
String loadedName = loaded.getCommonName();
String loadedEmail = loaded.getEmail();
~~~

Những điều cần xác minh:

1. Entity thực sự được **đọc lại từ server**, không chỉ là reference của object `person` vừa tạo.
2. `loaded.getUid()` bằng UID ban đầu và tương ứng DN.
3. `commonName`, `surname` và `email` khớp giá trị LDAP được phép đọc.
4. `getDn()` định vị đúng entry, với semantics DN của ODM được kiểm tra trên phiên bản đang sử dụng.
5. `displayLabel` là `null` nếu service chưa enrich, vì `@Transient` không nạp từ LDAP.

**Lưu ý:** API `findByDn` có hợp đồng xử lý entry không tồn tại phụ thuộc overload/phiên bản; một số đường gọi trả null, một số trường hợp có exception. Test production nên xử lý `NameNotFound` và lỗi mạng/ACL đúng cách, không coi tất cả là “không có account”.

### 7.1. Không dùng field transient làm bằng chứng persist

~~~java
person.setDisplayLabel("LOCAL PREVIEW");

// Mọi object vẫn có thể giữ giá trị LOCAL PREVIEW trong RAM.
assert "LOCAL PREVIEW".equals(person.getDisplayLabel());
~~~

Assertion này **không chứng minh gì về directory**. Cần đọc **object khác** bằng ODM và kiểm tra field tạm chưa được nạp, kết hợp kiểm tra LDAP attributes trực tiếp.

### 7.2. So sánh giá trị đơn trị và đa trị đúng cách

`uid`, `sn` là dữ liệu text đơn trị trong mô hình ví dụ. `objectClass` là thuộc tính đa trị. Với objectClass nên đọc mọi giá trị:

~~~java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

Set<String> classes = Arrays.stream(
        created.getStringAttributes("objectClass")
).map(String::toLowerCase).collect(Collectors.toSet());

boolean hasInetOrgPerson = classes.contains("inetorgperson");
~~~

LDAP attribute names và nhiều giá trị objectClass có matching rules phù hợp; so sánh chữ thường ở đây chỉ phục vụ test minh họa cho class name, không phải bộ so sánh LDAP tổng quát.

Không mặc định thứ tự các `objectClass` hoặc attribute đa trị được giữ ổn định giữa những lần lookup.

## 8. Bước Update: thay dữ liệu mapped và đọc lại

Muốn xác minh ODM Update thực sự hoạt động, hãy dùng entity **đã đọc lại từ server** ở bước trước thay vì tự khẳng định object mới tạo đã đại diện cho trạng thái thực tế.

Ví dụ:

~~~java
DirectoryPerson loaded =
        ldapTemplate.findByDn(dn, DirectoryPerson.class);

String previousName = loaded.getCommonName();
String previousSurname = loaded.getSurname();

loaded.setEmail("odmtest01.updated@example.org");
loaded.setDisplayLabel("Preview only");

ldapTemplate.update(loaded);
~~~

Sau đó mở một lượt đọc **mới**:

~~~java
DirectoryPerson afterUpdate =
        ldapTemplate.findByDn(dn, DirectoryPerson.class);

if (!"odmtest01.updated@example.org"
        .equals(afterUpdate.getEmail())) {
    throw new AssertionError("Email was not persisted");
}

if (!previousName.equals(afterUpdate.getCommonName())) {
    throw new AssertionError("Unexpected cn change");
}

if (!previousSurname.equals(afterUpdate.getSurname())) {
    throw new AssertionError("Unexpected sn change");
}

if (afterUpdate.getDisplayLabel() != null) {
    throw new AssertionError("Transient field was unexpectedly restored");
}
~~~

Ở đây `displayLabel` là field `@Transient`: việc đặt giá trị trong object trước Update **không có nghĩa directory lưu nó**. Nếu test chỉ kiểm tra `loaded.getDisplayLabel()` mà không đọc lại object mới, test có thể thành công dù dữ liệu LDAP chưa thay đổi đúng.

### 8.1. Kiểm tra độc lập bằng lookupContext

Một kiểm tra bổ sung:

~~~java
DirContextOperations afterUpdateRaw =
        ldapTemplate.lookupContext(dn);

String serverMail = afterUpdateRaw.getStringAttribute("mail");
String serverCn = afterUpdateRaw.getStringAttribute("cn");

if (!"odmtest01.updated@example.org".equals(serverMail)) {
    throw new AssertionError("LDAP mail does not match");
}

if (!"ODM Test User".equals(serverCn)) {
    throw new AssertionError("Unrelated cn was modified");
}
~~~

Các field `@Attribute` được ánh xạ hai chiều theo ODM, nhưng server vẫn có thể chuẩn hóa giá trị hoặc từ chối update vì schema/ACL. Thông điệp lỗi Java cần được phân loại, không tự diễn giải mọi exception thành “email không hợp lệ”.

### 8.2. Thay field Java không tự ghi LDAP

~~~java
loaded.setEmail("not-saved-yet@example.org");

// Chỉ sửa một object trong RAM. Chưa có LDAP Modify.

DirectoryPerson independentRead =
        ldapTemplate.findByDn(dn, DirectoryPerson.class);
~~~

`independentRead` phản ánh dữ liệu server được đọc tại thời điểm đó, **không** nhận giá trị mới chỉ vì một biến Java khác đã được sửa. Tuy nhiên, nếu code có thêm cache/shared references ở tầng service, test phải đảm bảo đọc từ LDAP thực sự thay vì từ một cache.

### 8.3. Không mặc định ODM Update chỉ ghi đúng một field

Cách ODM dựng LDAP Modify từ entity tùy API và phiên bản; việc `loaded.setEmail(...)` không tự đảm bảo chỉ `mail` bị ảnh hưởng trong mọi cấu hình. Với bài toán sửa đúng một attribute hoặc cần kiểm soát concurrent modification, có thể sử dụng `LdapTemplate.modifyAttributes(dn, ModificationItem[])` và điều kiện LDAP thích hợp.

Vì vậy test nên **đọc lại cả những field bắt buộc không được phép mất** như `uid`, `cn`, `sn` hoặc attribute quan trọng khác thuộc mô hình.

### 8.4. Tính nguyên tử và cạnh tranh

Một LDAP Modify request trên một entry có ngữ nghĩa nguyên tử đối với danh sách thay đổi của request. Nhưng vòng đời `findByDn → update` là chuỗi thao tác theo thời gian và **không tự bảo đảm isolation**. Một client khác có thể cập nhật entry trong khoảng giữa hai bước.

Nếu nghiệp vụ yêu cầu “update chỉ khi phiên bản dữ liệu chưa thay đổi”, cần thiết kế condition/assertion/locking theo khả năng server. Annotation `@Id` không tự thay cho optimistic locking của một ORM cơ sở dữ liệu quan hệ.

## 9. Bước Delete: xác minh đã xóa đúng entry

Khi test đã kiểm tra Update, tiến hành Delete **entry do test sở hữu**:

~~~java
DirectoryPerson current =
        ldapTemplate.findByDn(dn, DirectoryPerson.class);

ldapTemplate.delete(current);
~~~

Đây là API ODM Delete đối với entity định danh bằng DN, không phải xóa mọi entry trong `ou=people`.

### 9.1. Không chỉ tin vào object cũ trong RAM

Object `current` vẫn có thể tồn tại trong bộ nhớ sau khi LDAP Delete thành công. Điều đó **không có nghĩa LDAP entry vẫn tồn tại**.

Ngược lại, việc xóa reference Java hoặc đặt `current = null` **không xóa** entry LDAP. Delete chỉ xảy ra khi gửi thao tác tới server và được chấp nhận.

### 9.2. Xác minh absence bằng một Search có scope rõ ràng

Sau Delete, có thể tìm lại UID trong OU đã chọn:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery searchForDeletedUid = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid")
        .where("uid").is("odmtest01");

List<String> found = ldapTemplate.search(
        searchForDeletedUid,
        (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("uid").get())
);

if (!found.isEmpty()) {
    throw new AssertionError("Entry still visible after delete");
}
~~~

**Điều kiện để kết luận hợp lệ:**

- Test biết **DN và OU** đã dùng để tạo.
- Search dùng đúng base/scope để bao phủ entry.
- Account đọc có quyền nhìn entry và attribute trước khi Delete.
- Search hoàn tất không có lỗi hoặc giới hạn làm mất kết quả.
- Không lấy dữ liệu từ một replica chưa đồng bộ mà mặc định đã phản ánh Delete mới nhất.
- Kết quả trống cần được diễn giải trong ngữ cảnh LDAP ACL, không coi là bằng chứng tuyệt đối ngoài bối cảnh test đã kiểm soát.

Với UID duy nhất theo fixture và `ONELEVEL` dưới `ou=people`, Search sẽ hướng tới chính entry mới tạo, miễn OU và DN được thiết kế đúng.

### 9.3. Delete entry có con

LDAP Delete thông thường không xóa đệ quy một subtree. Nếu DN cần xóa còn entry con, server thường trả **66 — notAllowedOnNonLeaf**. Test vòng đời của một `inetOrgPerson` thường chỉ xóa **leaf entry**, và không nên thử xóa OU đang chứa những user khác.

### 9.4. Delete lần thứ hai không phải luôn thành công

Sau một Delete thành công, Delete lần hai thường gặp `noSuchObject` (code 32) hoặc exception tương đương. Đây là hành vi cần được xác định trong API test; **không mặc định Delete là idempotent ở mức response** chỉ vì trạng thái đích đều là “không có entry”.

Một HTTP deprovisioning endpoint có thể định nghĩa hành vi idempotent nghiệp vụ riêng, nhưng phải kiểm tra ownership và trạng thái LDAP thực tế.

## 10. Integration test end-to-end với JUnit 5 và Spring Test

Dưới đây là một **khung test tích hợp tương đối hoàn chỉnh**: tạo một entry có UID riêng, đọc bằng ODM, cập nhật email, đọc bằng API LDAP trực tiếp, xóa rồi xác minh không còn trong OU.

Test dùng `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`, nên không giả định dự án bắt buộc dùng Spring Boot. Cần dependency Spring LDAP, Spring Test, JUnit 5 và LDAP server thử nghiệm với schema/ACL phù hợp.

### 10.1. Các import và fixture

~~~java
import java.util.List;
import java.util.UUID;

import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = LdapTestConfiguration.class)
class DirectoryPersonLifecycleIT {

    @Autowired
    private LdapTemplate template;

    private List<String> searchUids(String uid) {
        LdapQuery q = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid")
                .where("uid").is(uid);

        return template.search(q,
                (AttributesMapper<String>) attrs -> {
                    Attribute value = attrs.get("uid");
                    return value == null
                            ? null
                            : String.valueOf(value.get());
                });
    }

    // Phần test chính ở khối mã tiếp theo.
}
~~~

Đây là phần khung minh họa, không thể biên dịch như một tập tin hoàn chỉnh nếu bạn chép **cả hai khối** mà không ghép method test vào lớp. `LdapTestConfiguration` là configuration từ phần 5; Spring Test cần tìm đúng class theo package của dự án.

### 10.2. Phương thức test Create → Read → Update → Delete

Đưa method sau vào class `DirectoryPersonLifecycleIT` ở trên:

~~~java
@Test
void lifecyclePersistsAndRemovesExactlyOneTestEntry() {
    String suffix = UUID.randomUUID().toString()
            .replace("-", "").substring(0, 12);
    String uid = "odm-it-" + suffix;
    String marker = "spring-ldap-odm-lifecycle-test:" + suffix;

    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    DirectoryPerson initial = new DirectoryPerson();
    initial.setDn(dn);
    initial.setUid(uid);
    initial.setCommonName("ODM Test User");
    initial.setSurname("User");
    initial.setEmail(uid + "@example.org");
    initial.setDescription(marker);
    initial.setDisplayLabel("NOT PERSISTED");

    boolean createAttempted = false;
    boolean deleteAcknowledged = false;

    try {
        createAttempted = true;
        template.create(initial);

        // Readback bằng API trực tiếp, tránh chỉ kiểm tra entity cũ.
        DirContextOperations raw = template.lookupContext(dn);
        assertEquals(uid, raw.getStringAttribute("uid"));
        assertEquals("ODM Test User",
                raw.getStringAttribute("cn"));
        assertEquals(marker,
                raw.getStringAttribute("description"));
        assertNull(raw.getStringAttribute("displayLabel"));

        // Readback qua ODM, kiểm tra mapping.
        DirectoryPerson loaded =
                template.findByDn(dn, DirectoryPerson.class);
        assertNotNull(loaded);
        assertEquals(uid, loaded.getUid());
        assertEquals("User", loaded.getSurname());
        assertNull(loaded.getDisplayLabel());

        // Update field mapped + thay transient trong RAM.
        String newEmail = uid + ".updated@example.org";
        loaded.setEmail(newEmail);
        loaded.setDisplayLabel("ONLY JAVA");
        template.update(loaded);

        // Đọc lại từ LDAP, không chỉ assert getter của loaded.
        DirContextOperations rawAfter = template.lookupContext(dn);
        assertEquals(newEmail,
                rawAfter.getStringAttribute("mail"));
        assertEquals("ODM Test User",
                rawAfter.getStringAttribute("cn"));
        assertEquals(marker,
                rawAfter.getStringAttribute("description"));
        assertNull(rawAfter.getStringAttribute("displayLabel"));

        DirectoryPerson updated =
                template.findByDn(dn, DirectoryPerson.class);
        assertEquals(newEmail, updated.getEmail());
        assertNull(updated.getDisplayLabel());

        // Delete bằng ODM.
        template.delete(updated);
        deleteAcknowledged = true;

        // Verify absence trong OU với read identity phù hợp.
        assertTrue(searchUids(uid).isEmpty());

    } finally {
        if (createAttempted && !deleteAcknowledged) {
            // Chỉ dọn nếu entry còn thấy được và đúng marker test.
            LdapQuery ownershipQuery = query()
                    .base("ou=people")
                    .searchScope(SearchScope.ONELEVEL)
                    .attributes("description")
                    .where("uid").is(uid);

            List<String> markers = template.search(
                    ownershipQuery,
                    (AttributesMapper<String>) attrs -> {
                        Attribute description =
                                attrs.get("description");
                        return description == null ? null
                                : String.valueOf(description.get());
                    });

            if (markers.size() == 1
                    && marker.equals(markers.get(0))) {
                template.delete(initial);
            }
        }
    }
}
~~~

### 10.3. Giải thích các quyết định trong test

1. **UID riêng:** tránh test chạy đồng thời tạo DN trùng.
2. **Marker riêng:** giúp đối chiếu entry được tạo bởi fixture, thay vì xóa bất kỳ entry nào có UID trùng.
3. **`createAttempted` đặt trước Create:** nếu Add đã gửi rồi response mất, test vẫn cố kiểm tra có entry test nào cần cleanup hay không.
4. **Đọc lại bằng `lookupContext`:** xác minh trạng thái server không phụ thuộc hoàn toàn vào ODM.
5. **Đọc lại bằng `findByDn`:** xác minh mapping entity.
6. **Cập nhật từ entity mới đọc:** mô phỏng vòng đời object gần thực tế.
7. **Readback sau Update:** xác minh email mới, đồng thời giữ cn và marker ownership.
8. **Delete bằng entity ODM:** kiểm chứng API Delete.
9. **Search lại theo UID:** xác minh absence với base/scope đúng.
10. **Cleanup có điều kiện:** chỉ xóa khi thấy marker fixture khớp.

**Giới hạn của test:** đây là code minh họa tích hợp, cần chỉnh theo package/class, bean và server thực tế. Với `description` có thể đa trị trong LDAP, việc dùng `get()` ở cleanup giả định fixture lưu đúng **một** giá trị description. Nếu server bổ sung giá trị description khác, cần đọc toàn bộ `Attribute.getAll()` và so sánh tập. Việc kiểm tra marker cũng không thay thế sandbox OU/ACL.

### 10.4. Không để cleanup che lỗi chính

Nếu bước Update ném exception, `finally` chạy. Nhưng nếu cleanup tiếp tục gặp lỗi mạng/ACL, ngoại lệ cleanup có thể làm khó nhận ra lỗi ban đầu. Trong test production, nên dùng cơ chế `@AfterEach`/fixture cleanup có log kiểm soát, lưu lại cả **primary failure và cleanup failure**, hoặc gọi `Throwable.addSuppressed(...)` để giữ dấu vết.

Cũng cần có cơ chế **quét dọn orphan test entries** trong OU sandbox theo chính sách retention và ownership đã định nghĩa, vì một process có thể bị kill trước khi `finally` chạy.

### 10.5. Vị trí khẳng định Delete succeeded

`deleteAcknowledged = true` chỉ được gán sau khi `template.delete(updated)` trả về. Nếu server đã Delete nhưng response bị mất, cờ này vẫn false; code cleanup tìm entry có marker trước khi xóa nên không cố Delete mù quáng.

Mặt khác, nếu Delete đã được xác nhận nhưng `searchUids(uid)` vẫn thấy entry, assertion sẽ thất bại. Khi đó cần điều tra replica consistency, ACL, cache hoặc thay đổi do client khác; không tự kết luận Delete chắc chắn rollback.

## 11. Unit test bổ sung cho entity ODM

Không phải mọi kiểm thử phải mở LDAP server. Unit test giúp phát hiện import nhầm annotation, thiếu mapping và lỗi dựng DN trước khi integration test chạy.

### 11.1. Reflection test kiểm tra metadata

~~~java
import java.lang.reflect.Field;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

import static org.junit.jupiter.api.Assertions.*;

class DirectoryPersonMetadataTest {

    @Test
    void dnAndMappedFieldsHaveExpectedAnnotations()
            throws Exception {

        Field dn = DirectoryPerson.class.getDeclaredField("dn");
        Field email = DirectoryPerson.class.getDeclaredField("email");
        Field label = DirectoryPerson.class
                .getDeclaredField("displayLabel");

        assertTrue(dn.isAnnotationPresent(Id.class));
        assertTrue(email.isAnnotationPresent(Attribute.class));
        assertEquals("mail",
                email.getAnnotation(Attribute.class).name());

        assertTrue(label.isAnnotationPresent(Transient.class));
        assertFalse(label.isAnnotationPresent(Attribute.class));
    }
}
~~~

Test này kiểm tra **đúng package annotation** và mapping field, không chứng minh dữ liệu thực sự tồn tại trên server.

### 11.2. Unit test validation đầu vào và DN

~~~java
import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

class DirectoryPersonDnTest {

    @Test
    void buildsExpectedRelativeDn() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "odmtest01")
                .build();

        assertEquals("uid=odmtest01,ou=people", dn.toString());
    }
}
~~~

Nếu hệ thống cấp UID từ request, cần thêm domain validation cho ký tự, độ dài, danh sách tên bị cấm và escaping DN. `LdapNameBuilder` giúp ngăn lỗi cú pháp DN, nhưng **không chứng minh UID hợp chính sách tổ chức**.

## 12. Negative tests: vòng đời sai phải thất bại đúng cách

Một integration suite tốt không chỉ kiểm tra chuỗi Create/Read/Update/Delete thành công. Các failure modes điển hình:

### 12.1. Create lại cùng DN

Sau khi tạo thành công trong directory test, gọi `create` lần hai với DN giống hệt. Server thường trả LDAP result code **68 — entryAlreadyExists**.

Kỳ vọng:

- Lần thứ hai **không ghi đè** entry cũ.
- Không chuyển ngầm sang Update.
- Không xóa entry sau khi nhận conflict nếu không chứng minh được ownership.
- Sau test, readback vẫn thấy dữ liệu của entry ban đầu.

### 12.2. Thiếu thuộc tính MUST

Ví dụ `inetOrgPerson` kế thừa `person`, yêu cầu `cn` và `sn`. Thử tạo một DN **test riêng** với `surname` null có thể làm server trả code **65 — objectClassViolation**.

Kỳ vọng: Add thất bại, entry sai schema **không tồn tại**. Không cố sửa schema production để làm một negative test đi qua.

### 12.3. Update hoặc Delete một DN không tồn tại

Hãy chọn DN chỉ dành cho test và đảm bảo chưa tồn tại. Tùy API Spring LDAP/LDAP server, operation có thể trả lỗi `noSuchObject` (code **32**) hoặc hành vi cụ thể khác.

Không nên hard-code giả định rằng `findByDn` luôn trả null hay `delete` luôn im lặng khi thiếu entry: kiểm tra phiên bản và hợp đồng API đang dùng.

### 12.4. Thiếu ACL

Dùng reader identity chỉ có quyền Search/Lookup, thử Update hoặc Delete entry test đã được chuẩn bị. Server phải từ chối theo ACL, thường có code **50 — insufficientAccessRights**.

Kỳ vọng: entry vẫn đúng trạng thái cũ, không tự chuyển sang admin credentials để “cho test pass”. Dùng fixture và quyền riêng, tránh thử trên hồ sơ thật.

### 12.5. Đổi RDN qua field UID

Nếu test đổi `uid` trong Java entity, đừng mặc định `update(person)` là tương đương LDAP Modify DN. Đổi RDN cần quy trình `rename`/Modify DN phù hợp và hiểu ảnh hưởng đến group membership.

Đặc biệt, không để test vô tình đổi định danh entry rồi dọn theo DN cũ mà tưởng đã cleanup.

### 12.6. Side effects và nhiều entry

Nếu một quy trình vừa tạo user vừa thêm vào group, đây là **nhiều LDAP operations** và không tự có transaction chung. Một bước lỗi giữa chừng có thể để lại user nhưng chưa có membership.

Integration test của một entity không tự chứng minh toàn bộ workflow provisioning/deprovisioning nguyên tử. Khi cần, bổ sung test checkpoint, idempotency và compensation cho từng bước.

## 13. Lỗi LDAP và trạng thái không chắc chắn trong vòng đời

Khi Create, Update hoặc Delete ném ngoại lệ, câu hỏi cần trả lời là **server đã trả lỗi từ chối hay client mất phản hồi sau khi gửi yêu cầu?** Hai trường hợp có cách xử lý khác nhau.

| Mã LDAP hoặc sự cố | Tên / nhóm | Tình huống cần kiểm tra |
| --- | --- | --- |
| **68** | `entryAlreadyExists` | DN đã tồn tại; Create không phải upsert |
| **32** | `noSuchObject` | Base/parent/entry DN không tồn tại hoặc không nhìn thấy |
| **34** | `invalidDNSyntax` | DN/RDN sai cú pháp |
| **65** | `objectClassViolation` | Thiếu thuộc tính MUST hoặc object class không hợp |
| **17** | `undefinedAttributeType` | Attribute chưa được định nghĩa trong schema |
| **21** | `invalidAttributeSyntax` | Giá trị không hợp cú pháp của attribute type |
| **19** | `constraintViolation` | Vi phạm ràng buộc server, ví dụ đơn trị |
| **50** | `insufficientAccessRights` | Account bind không có quyền thực hiện thao tác |
| **66** | `notAllowedOnNonLeaf` | Cố xóa entry còn con |
| TLS/bind error | Kết nối và xác thực | Sai truststore, chứng chỉ, hostname hoặc credentials |
| Timeout/connection reset | Outcome **UNKNOWN** | Request có thể đã áp dụng trước khi phản hồi mất |

Spring LDAP ánh xạ nhiều ngoại lệ JNDI thành exception framework; các tên và diagnostic chính xác phụ thuộc LDAP provider/server. Test không nên chỉ bắt mọi `RuntimeException` rồi coi đó là “không có user”.

### 13.1. Mất response sau Create

~~~text
Client                           LDAP server
   |                                   |
   +------------ LDAP Add ----------->|
   |                                   +-- Có thể đã tạo entry
   X <----------- Response -----------|
       Client mất kết nối trước khi nhận
~~~

Nếu lời gọi `create(entity)` gặp lỗi socket, **không được khẳng định server chưa tạo entry**. Hãy tìm theo DN trong directory test với account có quyền đọc, xác nhận UID và marker ownership. Không retry Create mù quáng rồi hiểu code 68 là một request mới thất bại chắc chắn.

### 13.2. Mất response sau Update

Một lần `update(entity)` bị timeout có thể đã làm thay đổi `mail`. Không dựa vào getter của entity đang nằm trong RAM; phải đọc lại `mail` và các field quan trọng từ LDAP. Nếu không đọc được vì mạng hoặc ACL, giữ trạng thái **UNKNOWN** và ghi nhận để đối soát.

Dữ liệu đọc từ replica có thể chưa phản ánh ngay request vừa được gửi tới writer server; nếu cần xác minh mạnh, phải cân nhắc chính sách read-after-write/replication của hạ tầng.

### 13.3. Mất response sau Delete

Nếu Delete được server thực hiện nhưng response mất, lần Delete tiếp theo có thể trả code 32. Điều này có thể do thao tác trước thành công, hoặc DN sai/entry đã bị tác nhân khác xóa. Test cần xác minh trạng thái theo DN và marker nếu còn entry, không bắt mọi lỗi rồi tự tuyên bố Delete thành công.

### 13.4. Không retry vô hạn

Giới hạn timeout, số lần thử và thời gian chờ. Với thao tác ghi, chỉ retry khi đã xác minh trạng thái và đánh giá idempotency. Những workflow có nhiều entry hoặc cập nhật cả SQL/LDAP cần checkpoint và bù trừ; integration test một entity không chứng minh transaction xuyên hệ thống.

## 14. Kiểm chứng độc lập bằng ldapsearch và LDIF

Đôi khi cần xác nhận trạng thái directory **không qua cùng mapper ODM**. Với công cụ CLI và directory thử nghiệm:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap-test.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "uid=odmtest01,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" \
  dn objectClass uid cn sn mail description
~~~

`-H` chọn endpoint LDAPS; `-D` chọn bind DN; `-W` nhập mật khẩu tương tác; `-b` là DN đầy đủ dùng cho search. `-s base` giới hạn kiểm tra chính entry đó.

Kết quả sau Create, trước Update có thể giống:

~~~ldif
dn: uid=odmtest01,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: odmtest01
cn: ODM Test User
sn: User
mail: odmtest01@example.org
description: spring-ldap-odm-lifecycle-test
~~~

Kết quả thực có thể khác thứ tự các attribute hoặc thêm operational attributes tùy server; không dùng thứ tự dòng làm điều kiện kiểm thử.

### 14.1. Sau Update

Chạy lại base search. Kiểm tra `mail` đã đổi theo yêu cầu, đồng thời `uid`, `cn`, `sn` và marker test còn nguyên. Nếu một thuộc tính đa trị, so sánh **tập giá trị** chứ không chỉ `Attribute.get()`.

### 14.2. Sau Delete

Dùng cùng DN và account đọc phù hợp để kiểm tra entry không còn. Không coi một lỗi kết nối, thiếu ACL hoặc kết quả từ replica chậm là bằng chứng entry đã xóa.

### 14.3. Không trộn thao tác CLI với integration test đang chạy

Nếu đã dùng ODM để Create một DN, **không** chạy `ldapadd` với cùng DN; server sẽ báo conflict. Không chạy `ldapdelete` thủ công trong lúc test đang Update/Read vì điều này đưa vào tác nhân thứ ba và làm kết quả không còn tái lập.

## 15. Đảm bảo test chạy lặp lại và cleanup an toàn

Một suite integration test tốt phải giữ **isolation**, **ownership** và khả năng quan sát lỗi:

1. **DN duy nhất mỗi ca:** dùng UID riêng, không dùng chung `uid=alice` giữa các test chạy song song.
2. **OU sandbox:** giới hạn account test trong nhánh được phê duyệt; không trỏ sang production.
3. **Marker nhận diện:** dùng một giá trị mô tả/định danh test theo policy để hỗ trợ đối soát.
4. **Readback thật:** kiểm tra trạng thái directory sau Create/Update/Delete thay vì object RAM.
5. **Cleanup có guard:** chỉ Delete nếu DN và marker khớp, quyền sở hữu được xác minh.
6. **Không nuốt lỗi cleanup:** nếu không dọn được, báo suite còn dữ liệu tồn dư và lưu thông tin xử lý.
7. **Không phụ thuộc thứ tự Search:** dùng Set của UID/DN đã xác minh, không dựa thứ tự mặc định.
8. **Bảo vệ secrets:** không log password, token, toàn bộ entry hoặc raw LDAP diagnostic nhạy cảm.
9. **Tách writer/reader:** khi test khả năng hiển thị với người dùng thực, dùng read-only identity riêng.
10. **So sánh môi trường:** ghi rõ khác biệt schema, ACL, TLS và replication giữa test và production.

### 15.1. Chỉ xóa entry test sở hữu

Không dùng một filter rộng như `(uid=odm*)` để xóa hàng loạt khi chỉ muốn dọn một entry. Tên có thể vô tình trùng một tài khoản hợp lệ. Chỉ xóa **DN cụ thể đã được tạo** sau khi xác minh marker và vùng sandbox; kiểm tra trước khi chạy cleanup trên mọi môi trường.

### 15.2. Khi cleanup cũng lỗi

Một lần LDAP Delete trong `finally` có thể ném exception, làm che ngoại lệ chính của bước Create/Update. Test production cần giữ cả hai lỗi, có thể ghi nhận cleanup failure riêng hoặc gắn vào primary error bằng `addSuppressed`.

Nếu process bị kill trước khi `finally`, cleanup không chạy. Vì vậy có thể cần công việc dọn orphan test entries có audit, giới hạn thời gian giữ và xác minh ownership.

### 15.3. Tính đầy đủ của kết quả Search

Nếu kiểm tra nhiều entry bằng LDAP Search, phải xem xét base DN, scope, filter, attributes, paging/size limits, quyền ACL và thứ tự kết quả. Không coi list rỗng do request timeout hoặc ACL che dữ liệu là bằng chứng xóa thành công.

## 16. Ma trận kiểm thử vòng đời ODM

| Kịch bản | Điều kiện | Kết quả cần xác minh |
| --- | --- | --- |
| Create thành công | Parent tồn tại, DN mới, schema/ACL đúng | Lookup có uid/cn/sn/mail và DN đúng |
| Read qua ODM | `findByDn` sau Create | Field entity có đúng giá trị trên server |
| Transient field | Đặt displayLabel trước Create/Update | Không thành LDAP attribute; object đọc lại không mang giá trị cũ |
| Update thành công | Đổi email của entity đã đọc | Mail mới được lưu, cn/sn/uid giữ nguyên |
| Chỉ sửa object Java | Đổi field nhưng chưa gọi Update | Trạng thái server không đổi |
| Delete thành công | Xóa entry test không có con | Không còn entry trong Search đúng DN/scope |
| Create trùng DN | Add lại cùng DN | Duplicate, entry ban đầu không bị ghi đè |
| Parent không tồn tại | Tạo ở OU sai | Add thất bại, không tự tạo parent |
| Thiếu `sn` | Entry `person` không đủ MUST | Schema từ chối |
| Schema sai attribute | Field không được object class cho phép | LDAP Add/Modify từ chối |
| Reader cố Update/Delete | Identity chỉ có ACL đọc | Server từ chối, dữ liệu không đổi |
| DN có ký tự đặc biệt | Dùng `LdapNameBuilder` | Không làm thay đổi cấu trúc DN |
| Delete DN không tồn tại | DN riêng chưa tạo | Phân loại lỗi/contract đúng |
| Delete OU có con | Sandbox OU có child | Server thường từ chối code 66 |
| Concurrent Update | Hai client sửa cùng entry | Có chiến lược xử lý lost update |
| Timeout sau Create | Mất response sau Add | Readback trước retry, không xóa bừa |
| Timeout sau Delete | Mất response sau Delete | Đối soát trạng thái, không coi chắc chắn thất bại |
| Replica chậm | Đọc từ server khác sau ghi | Không kết luận sai do replication lag |
| Cleanup thất bại | ACL hoặc network có lỗi | Test báo tồn dư hoặc cần đối soát |
| TLS/certificate không hợp lệ | Hostname/truststore sai | Kết nối thất bại an toàn |

### 16.1. PASS phải dựa trên trạng thái thực

Một test chỉ kiểm tra các setter Java hoặc verify mock gọi `create/update/delete` chưa đủ. Với integration test, PASS cần có bằng chứng từ **directory thật**:

- Entry đúng DN sau Create.
- Dữ liệu readback qua LDAP đúng các field bắt buộc và mapped fields.
- Entity mới được nạp bằng ODM có ánh xạ chính xác.
- Update thể hiện trên server sau một lần đọc mới.
- Delete được xác minh qua lookup/Search có quyền và scope đúng.
- Không còn fixture thử nghiệm ngoài dự kiến, hoặc có báo cáo rõ lỗi cleanup.

### 16.2. ACL có thể ảnh hưởng đến assertion

Nếu account đọc không có quyền thấy `mail`, một giá trị null khi lookup không tự chứng minh entry không có mail. Test cần kiểm soát ACL của reader. Tương tự, nếu account writer tạo được entry nhưng account reader không thấy, có thể đây là lỗi cấu hình quyền đọc chứ không phải Create thất bại.

### 16.3. Có thể tách suite theo mục tiêu

Với ứng dụng lớn, tách thành:

- **Unit tests:** annotation, validation, DN builder, DTO mapping.
- **ODM mapping integration tests:** Create/Find/Update/Delete và readback.
- **Security integration tests:** writer vs reader, TLS, ACL.
- **Reliability tests:** timeout, concurrent Update, retry và cleanup/orphan handling.
- **Workflow tests:** user + group + SQL cùng checkpoint/compensation riêng.

Cách tách này giúp biết chính xác lỗi thuộc Java mapping, schema, hạ tầng hay concurrency.

## 17. Bài thực hành: CRUD entity ODM qua LDAP test

**Bối cảnh:** một nền tảng nội bộ dùng Spring LDAP ODM quản lý hồ sơ người dùng dưới `ou=people`. Bạn cần chứng minh các thao tác Create, Read, Update, Delete đúng trên server mà không ảnh hưởng các account ngoài test.

1. **Chuẩn bị:** tạo LDAP directory test riêng, `ou=people` có sẵn, schema `inetOrgPerson` và reader/editor identities với ACL phù hợp.
2. **Cấu hình:** thiết lập `LdapContextSource`, base DN, LDAPS/truststore và credentials từ secret manager/biến môi trường.
3. **Entity:** viết `DirectoryPerson` dùng `@Entry`, `@Id`, `@Attribute` cho `uid`, `cn`, `sn`, `mail` và `@Transient` cho nhãn hiển thị.
4. **Fixture:** sinh UID/DN riêng cho mỗi lần chạy bằng `UUID`; tạo marker nhận diện trong attribute `description` nếu schema cho phép.
5. **Create:** gọi `ldapTemplate.create(person)`, đọc lại bằng `lookupContext` và xác minh DN/attributes/objectClasses.
6. **ODM Read:** gọi `findByDn`, kiểm tra mapping đúng và field transient không được phục hồi.
7. **Update:** sửa `mail` trên object đã đọc, gọi `update` và đọc lại server. Kiểm tra `cn`, `sn` và UID vẫn giữ nguyên.
8. **Chưa Update:** sửa một field trên Java object nhưng không gọi LDAP, xác nhận đọc lại server vẫn thấy dữ liệu cũ.
9. **Delete:** xóa entry bằng `ldapTemplate.delete`, tìm lại theo đúng UID, base và scope để xác minh vắng entry.
10. **Duplicate:** thử Create lại cùng DN trong một test riêng, xem server báo conflict và entry cũ không bị ghi đè.
11. **Schema:** thử thiếu `sn` hoặc sử dụng object class không phù hợp trên DN test khác, kiểm tra server từ chối.
12. **ACL:** dùng reader identity thử Update/Delete và xác minh server ngăn thao tác.
13. **Concurrency:** hai client đọc cùng entry rồi cập nhật, phân tích lost update và biện pháp cần có.
14. **Unknown result:** mô phỏng mất response sau Create/Update/Delete, thiết kế readback trước retry.
15. **Cleanup:** chỉ xóa entry có DN và marker đúng, không xóa tài khoản không thuộc fixture.
16. **Báo cáo:** trình bày bằng chứng server sau mỗi bước, gồm cả trạng thái incomplete nếu network/cleanup lỗi.

### Câu hỏi tự kiểm tra

1. Vì sao cần kiểm thử trọn vòng Create → Read → Update → Delete thay vì chỉ mock `LdapTemplate`?
2. `@Entry`, `@Id` và `@Attribute` có vai trò gì trong mapping?
3. Với base `dc=example,dc=org`, DN tương đối cho `uid=odmtest01` tại `ou=people` là gì?
4. Tại sao `LdapNameBuilder` tốt hơn việc nối DN từ UID?
5. Vì sao test không nên tạo cùng một DN cố định qua nhiều lần chạy?
6. `create` có tự tạo OU cha hay tự upsert DN trùng không?
7. Tại sao cần `lookupContext` hoặc `ldapsearch` sau khi Create thành công?
8. Khi sửa email ở Java object nhưng chưa gọi Update, server đã đổi chưa?
9. Vì sao phải đọc lại các field không liên quan sau Update?
10. Field `@Transient` có được nạp/ghi qua ODM không?
11. Tại sao annotation ODM không thể chặn raw `modifyAttributes`?
12. Khi xác nhận Delete, tại sao Search base/scope và ACL quan trọng?
13. Vì sao Delete lần hai có thể báo lỗi dù entry đã vắng?
14. Khi timeout sau Add, tại sao không thể nói chắc entry chưa được tạo?
15. `@Id` có tự ngăn lost update giữa hai client không?
16. Vì sao một cleanup thiếu ownership marker có thể gây hậu quả nghiêm trọng?
17. Unit test metadata khác integration test LDAP ở đâu?
18. TLS, pooling và schema/ACL có ảnh hưởng đến kết quả dù Java mapping đúng không?

## 18. Tổng kết

**Kiểm thử vòng đời object qua directory** trong **Spring LDAP ODM** phải có bằng chứng rằng thao tác tạo, đọc, cập nhật và xóa thực sự thay đổi **LDAP server**, không chỉ những field Java trong RAM. Quy trình đáng tin cậy là **entity có DN riêng → Create → readback trực tiếp → Find bằng ODM → Update → readback → Delete → verify absence**.

Annotation mô tả ý định mapping, nhưng server vẫn là nơi quyết định schema, DN, ACL và kết quả ghi. Để kiểm thử đáng tin, cần fixture độc lập, UID duy nhất, quyền tối thiểu, xác minh TLS, kiểm tra giá trị mới sau một lần đọc từ directory, không xóa entry lạ và xử lý trạng thái **UNKNOWN** khi mất phản hồi. Unit test bảo vệ code Java; integration test, negative tests và đối soát cleanup mới giúp khẳng định vòng đời ODM đúng, an toàn và có thể chạy lặp lại.






