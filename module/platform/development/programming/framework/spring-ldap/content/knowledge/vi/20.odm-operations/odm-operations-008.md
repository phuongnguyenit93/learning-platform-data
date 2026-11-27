# Domain object thiếu attribute bắt buộc trong Spring LDAP ODM

## 1. Vấn đề: Java object hợp lệ về cú pháp nhưng LDAP từ chối ghi

Trong **Spring LDAP**, **Object Directory Mapping (ODM)** chuyển các attribute của entry LDAP thành trường của đối tượng Java và ngược lại. Khi gọi các thao tác như `LdapTemplate.create(entity)` hoặc `LdapTemplate.update(entity)`, dữ liệu được ánh xạ phải tuân thủ **schema LDAP** trên máy chủ. Một domain object có thể được khởi tạo bình thường trong Java nhưng lại **thiếu attribute bắt buộc** của object class, khiến thao tác ghi thất bại.

Ví dụ, ứng dụng quản lý danh bạ muốn tạo entry theo object class `inetOrgPerson`. Đối tượng Java có mã người dùng `uid`, tên chung `cn`, họ `sn` và email `mail`. Nếu lập trình viên chỉ đặt `uid` và `cn`, server có thể từ chối do **thiếu `sn`**, dù Java cho phép trường `surname` bằng `null`.

```text
HTTP request / lệnh nghiệp vụ
          │
          ▼
PersonEntry trong Java
  uid = "an"
  commonName = "An Nguyen"
  surname = null          ◄── dữ liệu còn thiếu
          │
          ▼
Spring LDAP ODM
  @Attribute(name = "uid")
  @Attribute(name = "cn")
  @Attribute(name = "sn")
          │
          ▼
LdapTemplate.create(...)
          │
          ▼
LDAP server kiểm tra schema
          │
          └── từ chối nếu entry thiếu attribute MUST
```

Bài thuộc chương **ODM operations** của module **SPRING_LDAP**. Nó tập trung vào cách phát hiện, phòng tránh và xử lý domain object thiếu attribute bắt buộc khi thao tác entry. Các khái niệm `DN`, `RDN`, `objectClass`, `ContextSource`, LDAP filter, xác thực, TLS và xử lý lỗi vẫn là nền tảng của quy trình này.

## 2. “Bắt buộc” có ba ý nghĩa khác nhau

Không phải mọi trường mà ứng dụng coi là bắt buộc đều được LDAP schema yêu cầu; ngược lại, một attribute bắt buộc của schema có thể chưa được ứng dụng mô hình hóa.

| Loại ràng buộc | Ví dụ | Nơi chịu trách nhiệm |
| --- | --- | --- |
| **Schema LDAP — `MUST`** | `person` yêu cầu `cn` và `sn` | LDAP server kiểm tra khi tạo hoặc sửa entry |
| **Quy tắc đặt tên entry** | DN dùng `uid=an` làm RDN, nên giá trị naming phù hợp phải tồn tại trong entry | LDAP server và logic xây DN/RDN |
| **Quy tắc nghiệp vụ** | Ứng dụng yêu cầu email liên hệ dù schema có thể cho phép thiếu `mail` | Validation của ứng dụng trước khi ghi |

Với schema phổ biến của LDAP:

- `person` yêu cầu các attribute `cn` và `sn`.
- `organizationalPerson` kế thừa yêu cầu của `person`.
- `inetOrgPerson` kế thừa từ `organizationalPerson`; vì vậy một entry `inetOrgPerson` theo schema tiêu chuẩn vẫn phải có `cn` và `sn`.
- `mail` thường là attribute **được phép có** (`MAY`), không phải `MUST` của `inetOrgPerson`.
- `uid` thường không thuộc nhóm `MUST` của `inetOrgPerson`, nhưng có thể bị yêu cầu bởi quy tắc nghiệp vụ hoặc bởi việc chọn `uid` làm RDN.

Schema thực tế còn có thể chứa object class hoặc constraint riêng của tổ chức, OpenLDAP, Active Directory hay sản phẩm LDAP khác. **Không kết luận tập attribute bắt buộc chỉ từ tên model Java**; phải kiểm tra schema mà server thực sự áp dụng.

Một ví dụ entry hợp lệ về ý tưởng:

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

Nếu bỏ dòng `sn: Nguyen`, entry có thể vi phạm yêu cầu của object class `person`. Nếu bỏ `mail`, entry có thể vẫn hợp lệ theo schema nhưng vi phạm chính sách ứng dụng. Hai trường hợp cần cách báo lỗi và kiểm tra khác nhau.

## 3. ODM mapping không tự thực hiện toàn bộ validation

Các annotation phổ biến của Spring LDAP ODM là:

- `@Entry`: chỉ định một Java class đại diện cho entry LDAP và mô tả các object class.
- `@Id`: ánh xạ trường định danh DN, thường có kiểu `javax.naming.Name`.
- `@Attribute(name = "...")`: xác định attribute LDAP tương ứng với một field.
- `@DnAttribute`: hỗ trợ ánh xạ thành phần của DN/RDN khi thiết kế model phù hợp.

Ví dụ có thể khai báo `@Attribute(name = "sn")` nhưng vẫn tạo đối tượng với trường Java tương ứng là `null`. Annotation này **chỉ mô tả ánh xạ**; nó không có nghĩa ODM đã kiểm tra toàn bộ quy tắc `MUST` của schema hoặc các ràng buộc nghiệp vụ.

Cũng cần phân biệt hai giai đoạn:

1. **Đọc:** một entry được trả về thiếu attribute nào đó có thể tạo ra field `null` hoặc không được điền, tùy kiểu mapping và dữ liệu trả về. Việc đọc không đồng nghĩa có cơ chế bắt lỗi mọi trường hợp thiếu.
2. **Ghi:** khi `create` hoặc `update` tạo ra một thay đổi vi phạm schema, LDAP server có thể trả lỗi. Một số ràng buộc nghiệp vụ như “email phải có” sẽ không được server tự kiểm tra nếu không được cấu hình trong schema/policy.

Vì vậy, cách thiết kế phù hợp là **validation tại biên ứng dụng** và **vẫn xử lý lỗi từ LDAP server**. Validation trước thao tác ghi giúp báo lỗi rõ ràng, trong khi LDAP server là nơi quyết định cuối cùng về schema, quyền và trạng thái dữ liệu.

## 4. Model ODM minh họa trường hợp thiếu `sn`

Giả sử `ContextSource` đã cấu hình base DN là `dc=example,dc=org` và thư mục con `ou=people` đã tồn tại. Một model đơn giản có thể được đặt trong `PersonEntry.java`:

```java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
})
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

    public String getCommonName() {
        return commonName;
    }

    public void setCommonName(String commonName) {
        this.commonName = commonName;
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

Đoạn mã sau **cố tình tạo object chưa hợp lệ** để mô tả lỗi:

```java
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "an")
        .build();

PersonEntry person = new PersonEntry();
person.setDn(relativeDn);
person.setUid("an");
person.setCommonName("An Nguyen");
person.setSurname(null); // Thiếu attribute "sn"
person.setEmail("an@example.org");

// Trên server kiểm tra schema, lời gọi này có thể thất bại.
ldapTemplate.create(person);
```

`relativeDn` là DN **tương đối** với base `dc=example,dc=org` của `ContextSource`; DN đầy đủ trên server là `uid=an,ou=people,dc=example,dc=org`. Nếu tạo entry với `inetOrgPerson` mà thiếu `sn`, server áp dụng schema chuẩn thường từ chối với lỗi dạng **object class violation** (LDAP result code `65`). Lỗi cuối cùng mà ứng dụng nhận được còn phụ thuộc vào LDAP server và cơ chế chuyển đổi exception của Spring LDAP.

Ví dụ tạo thiếu dữ liệu chỉ để giải thích nguyên nhân; không thực hiện thao tác này trên thư mục sản xuất. Một bài kiểm thử tích hợp nên dùng nhánh dữ liệu riêng và tài khoản có quyền giới hạn.

## 5. Cách phòng tránh: kiểm tra domain object trước khi `create`

### 5.1. Xác định quy tắc từ schema và nghiệp vụ

Với ví dụ `inetOrgPerson`, đặt quy tắc:

- `dn` phải được xác định đúng trong cây LDAP.
- `uid` phải có giá trị vì ứng dụng dùng nó làm RDN.
- `cn` và `sn` phải có giá trị để đáp ứng schema `person`.
- `mail` có thể tùy chọn theo schema; nếu ứng dụng muốn bắt buộc email, phải bổ sung validation nghiệp vụ riêng.

Dùng validation tường minh giúp bảo đảm dữ liệu được kiểm tra **trước thao tác mạng** và cho phép trả thông báo cụ thể cho người gọi.

### 5.2. Viết validator đơn giản, dễ kiểm thử

Ví dụ tệp `PersonEntryValidator.java`:

```java
import java.util.Objects;

public final class PersonEntryValidator {

    private PersonEntryValidator() {
    }

    public static void validateForCreate(PersonEntry person) {
        Objects.requireNonNull(person, "person không được null");
        Objects.requireNonNull(person.getDn(), "dn không được null");

        requireText("uid", person.getUid());
        requireText("cn", person.getCommonName());
        requireText("sn", person.getSurname());

        // Chỉ thêm requireText("mail", ...) khi nghiệp vụ yêu cầu.
    }

    private static void requireText(String attribute, String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu giá trị bắt buộc: " + attribute);
        }
    }
}
```

Đây là **validation ở tầng ứng dụng**. Nó cố ý yêu cầu các giá trị không rỗng, trong khi schema LDAP có thể có các điều kiện cú pháp, độ dài hoặc chính sách khác. Do đó, validation này **không thay thế** kiểm tra từ server.

Nếu dự án dùng **Jakarta Bean Validation**, có thể đặt `@NotBlank` trên những field thích hợp và gọi validator qua cơ chế ứng dụng. Tuy nhiên, cần nhớ:

> `@NotBlank` hoặc `@Valid` chỉ có tác dụng khi ứng dụng thực sự kích hoạt quy trình validation thích hợp. Việc gọi `LdapTemplate.create(entity)` không mặc nhiên đồng nghĩa Spring LDAP ODM sẽ chạy Bean Validation.

Không dựa vào annotation validation một cách ngầm định. Hãy kiểm tra điểm vào của controller/service và đường đi thực sự của đối tượng.

### 5.3. Tạo entry qua service có validation

Ví dụ một lớp service đặt trong file `PersonDirectory.java`:

```java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDirectory {

    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonEntry createPerson(
            String uid,
            String commonName,
            String surname,
            String email) {

        // Kiểm tra tên RDN trước khi xây DN.
        requireText("uid", uid);

        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        PersonEntry person = new PersonEntry();
        person.setDn(relativeDn);
        person.setUid(uid);
        person.setCommonName(commonName);
        person.setSurname(surname);
        person.setEmail(email);

        PersonEntryValidator.validateForCreate(person);
        ldapTemplate.create(person);
        return person;
    }

    private static void requireText(String field, String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu giá trị bắt buộc: " + field);
        }
    }
}
```

Ví dụ sử dụng:

```java
PersonEntry person = directory.createPerson(
        "an",
        "An Nguyen",
        "Nguyen",
        "an@example.org");
```

Tại đây, `cn` và `sn` được kiểm tra trước khi giao object cho ODM. `LdapNameBuilder` giúp xây RDN đúng cú pháp khi `uid` chứa các ký tự đặc biệt cần escape. Ngoài ra, tài khoản LDAP vẫn phải có quyền tạo entry ở nhánh `ou=people` và toàn bộ object class/attribute phải phù hợp schema hiện hành.

**Không chỉ dựa vào việc có getter/setter hoặc constructor rỗng.** Đó là yêu cầu về cấu trúc model phục vụ ánh xạ; nó không khẳng định object đã đầy đủ để ghi xuống directory.

## 6. Khi `update`: thiếu trường do dữ liệu đầu vào không đầy đủ

Trường hợp thường gặp hơn trong ứng dụng là **cập nhật một phần**. Giả sử frontend chỉ gửi:

```json
{
  "mail": "an.new@example.org"
}
```

Nếu service tạo một `PersonEntry` mới chỉ có `dn` và `mail` rồi gọi:

```java
PersonEntry patch = new PersonEntry();
patch.setDn(existingDn);
patch.setEmail("an.new@example.org");

ldapTemplate.update(patch); // Không nên giả định an toàn
```

thì các trường `cn`, `sn` và `uid` đang ở trạng thái `null` trên object Java. Không nên mặc định mọi phiên bản hoặc cấu hình ODM sẽ hiểu `null` là “giữ nguyên attribute trên server”. Việc ánh xạ và áp dụng thay đổi phải được kiểm tra theo API đang dùng; nếu thao tác cuối cùng loại bỏ attribute `MUST`, server có thể từ chối.

Có hai cách xử lý phổ biến.

### 6.1. Tải đối tượng hiện có trước khi sửa

```java
PersonEntry person = ldapTemplate.findByDn(
        existingDn, PersonEntry.class);

person.setEmail("an.new@example.org");
PersonEntryValidator.validateForCreate(person);
ldapTemplate.update(person);
```

Cách này phù hợp khi muốn dùng ODM cho toàn bộ vòng đời object. Tuy nhiên:

- `findByDn` phải đọc đủ dữ liệu mà phép cập nhật/validation cần.
- Nếu ACL hoặc cấu hình truy vấn khiến một số attribute không được trả về, field `null` có thể phản ánh **thiếu quyền/thiếu projection**, không nhất thiết là entry thiếu attribute.
- Dữ liệu có thể bị sửa giữa bước đọc và ghi; cần chính sách đồng thời nếu hệ thống có nhiều tác nhân cập nhật.
- Validation dành cho tạo mới có thể quá chặt với các thao tác chỉ sửa một số trường; tách `validateForCreate` và `validateForUpdate` nếu yêu cầu nghiệp vụ khác nhau.

### 6.2. Sửa đúng attribute bằng `DirContextOperations`

Nếu chỉ thay email, phương án dùng API mức entry có thể rõ ràng hơn:

```java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

public final class PersonEmailUpdater {

    private final LdapTemplate ldapTemplate;

    public PersonEmailUpdater(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void changeEmail(Name relativeDn, String newEmail) {
        if (newEmail == null || newEmail.isBlank()) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }

        DirContextOperations context =
                ldapTemplate.lookupContext(relativeDn);

        context.setAttributeValue("mail", newEmail);
        ldapTemplate.modifyAttributes(context);
    }
}
```

Ở đây service tải entry, thay attribute `mail` rồi gửi các thay đổi qua `modifyAttributes`. Với thay đổi cần kiểm soát chi tiết hơn, có thể sử dụng các `ModificationItem` theo thao tác thêm/thay thế/xóa. Cách này giúp biểu diễn rõ **trường nào được cập nhật**. Dù vậy, server vẫn kiểm tra ACL và schema đối với mọi sửa đổi.

Không xóa `sn` hoặc `cn` chỉ để biểu diễn “không sửa” khi dùng patch. Đặc biệt, nếu muốn **xóa** một attribute tùy chọn, hãy sử dụng thao tác xóa rõ ràng; đừng tự coi chuỗi rỗng hay `null` là một quy tắc chung cho mọi directory server.

## 7. Không phải mọi `null` đều có nghĩa entry thực sự thiếu attribute

Khi thao tác đọc hoặc nhận dữ liệu từ API, cần xác định **nguồn gốc của giá trị thiếu** trước khi sửa.

| Quan sát | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| Domain object vừa tạo có `surname == null` | DTO/input không có `sn` hoặc code quên gán | Kiểm tra luồng tạo object và validator |
| LDAP entry thực sự không có `sn` | Dữ liệu cũ không hợp schema, schema khác, server chưa kiểm tra hoặc nhập liệu sai | Kiểm tra object class, schema và entry trên server thử nghiệm |
| ODM model có `sn == null` sau truy vấn | Attribute không được trả về vì projection hoặc ACL, hoặc chưa được ánh xạ đúng | Kiểm tra query, annotation, quyền và attributes trả về |
| Có `sn` nhưng chuỗi chỉ chứa khoảng trắng | Dữ liệu không đạt quy tắc nghiệp vụ hoặc syntax/policy server | Validate `isBlank()` và kiểm tra quy tắc server |
| Attribute có nhiều giá trị nhưng model dùng `String` | Kiểu Java không thể hiện đầy đủ ngữ nghĩa đa trị | Dùng kiểu phù hợp và đọc toàn bộ giá trị khi cần |
| Code cập nhật một object chỉ có vài field | Một số field chưa tải, không có nghĩa phải xóa chúng | Dùng read-modify-write có kiểm soát hoặc cập nhật theo attribute |
| Entry bị từ chối dù `cn` và `sn` đã có | Có thể thiếu attribute của object class khác, vi phạm syntax, ACL, DN hoặc constraint | Kiểm tra diagnostic và schema thực tế |

**Attribute không được trả về** không nhất thiết đồng nghĩa **attribute không tồn tại**. Ví dụ truy vấn chỉ yêu cầu `uid` và `mail`, hoặc tài khoản kết nối không được đọc `sn`. Khi đó, validator chạy trên object kết quả có thể phát hiện `null`, nhưng kết luận “dữ liệu trên server thiếu `sn`” sẽ không đủ cơ sở.

Vì vậy, đối với một quy trình ghi, ứng dụng nên biết rõ model của mình là **object đầy đủ** hay **projection/patch** và chỉ áp dụng validation tương ứng.

## 8. Phân tích lỗi từ LDAP server

Khi ghi dữ liệu, nếu server từ chối, Spring LDAP thường chuyển lỗi JNDI/LDAP thành exception thuộc hệ sinh thái Spring LDAP. Loại exception và diagnostic cụ thể còn phụ thuộc server, driver và phiên bản thư viện. Một số mã LDAP có ích khi chẩn đoán:

| LDAP result code | Tên thường gặp | Ý nghĩa trong ngữ cảnh này |
| --- | --- | --- |
| `65` | `objectClassViolation` | Có thể thiếu một attribute `MUST`, hoặc tập attribute/object class không đúng schema |
| `19` | `constraintViolation` | Vi phạm constraint do server thực thi, ví dụ chính sách về giá trị |
| `21` | `invalidAttributeSyntax` | Giá trị không phù hợp cú pháp của attribute |
| `50` | `insufficientAccessRights` | Tài khoản không đủ quyền thực hiện thao tác |
| `68` | `entryAlreadyExists` | DN muốn tạo đã tồn tại |
| `32` | `noSuchObject` | DN/nhánh cha hoặc entry đích không tồn tại |

Mã `65` là dấu hiệu mạnh để xem lại object class và các attribute bắt buộc; **không kết luận 100% là thiếu `sn`**. Nó còn có thể phát sinh khi ghi attribute không được phép, thiếu một attribute bắt buộc khác hoặc cấu trúc object class sai.

### Các bước chẩn đoán theo thứ tự

1. **Xem thao tác:** đang gọi `create`, `update` hay `modifyAttributes`? DN mục tiêu có đúng và có base phù hợp không?
2. **Kiểm tra object class:** model khai báo `@Entry(objectClasses = ...)` nào, entry trên server có object class nào?
3. **Đối chiếu schema:** lập danh sách `MUST`, `MAY` cùng các rule do server thêm; với `inetOrgPerson` chuẩn, kiểm tra `cn` và `sn` trước.
4. **Kiểm tra attribute cuối cùng:** xác định giá trị được ánh xạ thành entry/thay đổi, phân biệt `null`, vắng mặt và chuỗi trống.
5. **Kiểm tra quyền và kết nối:** tài khoản bind có quyền ghi attribute và nhánh đúng không? TLS/LDAPS, base DN, timeout và kết nối có hoạt động không?
6. **Thử trên directory kiểm thử:** dùng cùng schema và dữ liệu mẫu để tái hiện, quan sát diagnostic và đọc lại kết quả sau thao tác.

Khi ghi log, ưu tiên loại thao tác, tên attribute và mã lỗi; tránh đưa `userPassword`, token, dữ liệu nhạy cảm hoặc toàn bộ entry người dùng vào log. Nếu cần ghi DN phục vụ hỗ trợ vận hành, cần tuân thủ chính sách bảo vệ dữ liệu và ẩn định danh phù hợp.

## 9. Khi dùng Jakarta Bean Validation

Ở ứng dụng Spring hiện đại, có thể đặt validation trên input DTO rồi chuyển sang model ODM:

```java
import jakarta.validation.constraints.NotBlank;

public record CreatePersonRequest(
        @NotBlank String uid,
        @NotBlank String commonName,
        @NotBlank String surname,
        String email) {
}
```

Trong controller hoặc service, khi cơ chế Bean Validation được **cấu hình và thực sự gọi**, các trường `uid`, `commonName` và `surname` có thể được báo lỗi trước khi xây `PersonEntry`. Điều này có lợi hơn việc đợi LDAP server trả mã `65` vì người dùng nhận được thông báo tại đúng trường nhập liệu.

Tuy nhiên, các rule của DTO và rule của server vẫn có thể khác nhau:

- DTO có thể bắt buộc `mail` vì nghiệp vụ; LDAP schema lại cho phép không có `mail`.
- Server có thể yêu cầu attribute do object class mở rộng mà DTO không biết.
- `@NotBlank` không kiểm tra hết cú pháp DN, filter, ACL hay mọi constraint LDAP.

Đối với Spring sử dụng `javax.validation` ở phiên bản cũ, namespace annotation có thể khác `jakarta.validation`. Chọn đúng thư viện theo phiên bản ứng dụng; không trộn namespace một cách tùy tiện.

Một thiết kế hữu ích là: **request DTO validation → chuyển sang ODM model → domain validation theo thao tác → gọi `LdapTemplate` → xử lý kết quả/error LDAP**.

## 10. Kiểm thử trường hợp thiếu attribute bắt buộc

### 10.1. Unit test cho validation trước khi gọi server

Logic validation như `PersonEntryValidator` có thể được kiểm thử mà không cần LDAP server. Ví dụ minh họa JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class PersonEntryValidatorTest {

    @Test
    void rejectsMissingSurname() {
        PersonEntry person = new PersonEntry();
        person.setDn(
                org.springframework.ldap.support.LdapNameBuilder
                        .newInstance("ou=people")
                        .add("uid", "an")
                        .build());
        person.setUid("an");
        person.setCommonName("An Nguyen");
        // person.setSurname(...) cố tình bỏ qua

        assertThrows(
                IllegalArgumentException.class,
                () -> PersonEntryValidator.validateForCreate(person));
    }
}
```

Test này chứng minh **ứng dụng phát hiện dữ liệu thiếu trước khi gọi LDAP**. Nó không khẳng định schema server nào đang được áp dụng, cũng không xác minh ODM thực sự gửi những attribute nào.

### 10.2. Integration test với directory thử nghiệm

Để xác nhận toàn bộ đường đi ODM, tạo môi trường LDAP kiểm thử có object class `inetOrgPerson` và nhánh `ou=people`, sau đó thực hiện các tình huống:

| Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- |
| `cn`, `sn`, `uid` hợp lệ; có hoặc không có `mail` | Tạo entry theo schema và chính sách ứng dụng |
| Không đặt `cn` hoặc `sn` khi dùng `create` trực tiếp | Server áp dụng schema chuẩn từ chối |
| Thiếu `cn` hoặc `sn` qua service có validator | Ứng dụng từ chối trước khi gọi LDAP |
| Thiếu email trong nghiệp vụ cho phép | Tạo được entry nếu các constraint khác hợp lệ |
| Cập nhật chỉ `mail` qua `DirContextOperations` | `cn` và `sn` vẫn được giữ nguyên |
| Cố gắng xóa `sn` từ entry `inetOrgPerson` | Server có schema chuẩn từ chối |
| Đọc bằng tài khoản hạn chế | Ứng dụng xử lý đúng trường bị ẩn và lỗi quyền |
| Tạo với DN trùng | Xử lý lỗi tồn tại entry một cách rõ ràng |

Dùng DN riêng cho test và dọn dữ liệu trong phạm vi được cấp quyền. Khi kiểm tra thao tác ghi, hãy **đọc lại entry từ LDAP server** để đối chiếu thay vì chỉ nhìn object Java trong bộ nhớ.

## 11. Các lỗi thiết kế thường gặp

### Chỉ tin rằng annotation đã bảo đảm schema

`@Attribute(name = "sn")` chỉ là ánh xạ tên; không có nghĩa giá trị `surname` luôn khác `null` hoặc luôn hợp lệ. Hãy tạo validator nghiệp vụ và tiếp tục xử lý lỗi của server.

### Dùng cùng một model cho create, patch và API response

Ba thao tác có quy tắc dữ liệu khác nhau. `CreatePersonRequest` có thể yêu cầu `cn`, `sn`; `UpdateEmailRequest` chỉ cần `mail`; `PersonEntry` mô tả entry LDAP; `PersonView` là DTO trả ra. Tách trách nhiệm giúp tránh gửi object thiếu field vào `update`.

### “Chữa” lỗi thiếu `sn` bằng một giá trị giả

Điền `sn = "-"` hoặc `sn = "unknown"` có thể giúp qua một số kiểm tra cú pháp, nhưng tạo dữ liệu không chính xác và gây vấn đề tìm kiếm hoặc đồng bộ. Nên yêu cầu thông tin thực hoặc có chính sách dữ liệu thiếu được tổ chức phê duyệt rõ ràng.

### Giả định `null` luôn có nghĩa xóa attribute

Với update, `null` trên domain object có thể do form không gửi, do projection chỉ chọn vài attribute, do ACL hoặc do thực sự muốn xóa. Hãy mô hình hóa ý nghĩa thao tác rõ ràng, nhất là với attribute `MUST`.

### Chỉ bắt một exception chung rồi trả thông báo “thiếu field”

Lỗi ghi LDAP có thể đến từ schema, ACL, DN, trùng entry, kết nối hoặc TLS. Quy trình xử lý lỗi nên dựa vào mã và ngữ cảnh thực tế, đồng thời tránh làm lộ dữ liệu nhạy cảm.

## 12. Quy trình khuyến nghị trước khi vận hành

1. Xác định object class và các `MUST`/`MAY` theo schema thật của server.
2. Khai báo model ODM với `@Entry`, `@Id`, `@Attribute` phù hợp; chọn rõ quy ước DN tương đối với `ContextSource`.
3. Dùng DTO riêng cho create và patch; kiểm tra đầy đủ trường bắt buộc của từng thao tác.
4. Ở service, validate domain object trước `LdapTemplate.create` hoặc thao tác cập nhật.
5. Khi cập nhật một phần, đọc đủ dữ liệu hoặc sửa attribute có chủ đích; không suy diễn ý nghĩa `null`.
6. Gọi LDAP với tài khoản có ACL phù hợp, kết nối TLS/LDAPS và cơ chế xử lý exception rõ ràng.
7. Kiểm thử thiếu `cn`, `sn`, trường tùy chọn và dữ liệu bị ẩn bởi ACL; sau ghi phải đọc lại từ server để xác nhận.

## 13. Câu hỏi tự kiểm tra

1. Vì sao `@Attribute(name = "sn")` không đủ để bảo đảm một `PersonEntry` có thể ghi bằng `create`?
2. Với object class `inetOrgPerson` tiêu chuẩn, `cn` và `sn` bắt buộc vì lý do nào?
3. `uid` có thể là attribute không bắt buộc của schema nhưng lại cần có trong ví dụ này vì sao?
4. Khi một object ODM đọc từ LDAP có `surname == null`, cần phân biệt những nguyên nhân nào trước khi kết luận entry thiếu `sn`?
5. Vì sao không nên dựng một `PersonEntry` mới chỉ có `dn` và `mail` rồi gọi `update` mà không kiểm tra?
6. Mã lỗi LDAP `65` có luôn chứng minh thiếu `sn` không? Cần đối chiếu những thông tin nào?
7. Có thể kết hợp Bean Validation, validation nghiệp vụ và kiểm tra schema trên LDAP server như thế nào?

## 14. Kết luận

Trong **Spring LDAP ODM**, domain object thiếu attribute bắt buộc là vấn đề giao nhau giữa **model Java**, **quy tắc nghiệp vụ** và **LDAP schema**. Phương thức `create` hoặc `update` không biến object thiếu dữ liệu thành entry hợp lệ: khi yêu cầu vi phạm schema, server có quyền từ chối.

Cách giải quyết bền vững là xác định `MUST` từ object class, validate trước khi ghi, phân biệt object đầy đủ với patch, kiểm soát thay đổi attribute và xử lý đúng lỗi LDAP. Với ví dụ `inetOrgPerson` tiêu chuẩn, hãy đặc biệt chú ý `cn` và `sn`, đồng thời nhớ rằng `uid`, `mail` và các ràng buộc khác còn phụ thuộc quy ước DN cùng chính sách ứng dụng.

