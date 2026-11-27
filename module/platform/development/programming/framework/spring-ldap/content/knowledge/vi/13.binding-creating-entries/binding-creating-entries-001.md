# Chuẩn bị DN mới và object class trước khi tạo LDAP entry

Tạo một entry trong LDAP không chỉ là gửi tên người dùng và vài thuộc tính lên máy chủ. Trước tiên, ứng dụng phải chọn đúng **vị trí trong Directory Information Tree (DIT)**, tạo **Distinguished Name (DN)** hợp lệ, xác định **object class** theo schema và cung cấp đầy đủ những thuộc tính bắt buộc. Nếu chuẩn bị sai một trong các yếu tố này, yêu cầu tạo entry có thể bị từ chối hoặc tạo entry ở vị trí không như mong muốn.

Trong Spring LDAP, ta thường xây DN bằng `LdapNameBuilder`, chuẩn bị các attribute bằng `DirContextAdapter` và cuối cùng gọi `LdapTemplate.bind(...)`. Bài học thuộc chương **Bind và tạo entry** của module **Spring LDAP**, nằm trong lộ trình thực hành DN, schema, filter, thao tác entry, cấu hình `ContextSource`, kết nối TLS và quyền truy cập thư mục an toàn.

Sau bài học, bạn có thể:

- Chỉ ra sự khác biệt giữa DN, RDN, DN tương đối và base DN của `ContextSource`.
- Chọn một **parent DN đã tồn tại** và xây DN của entry mới bằng API xử lý tên LDAP.
- Giải thích vai trò `objectClass`, structural object class, auxiliary object class, thuộc tính `MUST`/`MAY` và schema inheritance.
- Chuẩn bị một `inetOrgPerson`, một `organizationalUnit` và phân biệt yêu cầu của các object class khác.
- Tạo entry bằng `DirContextAdapter` và `LdapTemplate.bind(...)` mà không nhầm với LDAP Bind để xác thực.
- Xử lý các lỗi thường gặp: DN trùng, thiếu parent, sai RDN, thiếu `cn`/`sn`, lỗi schema và thiếu quyền.
- Thiết kế kiểm thử trước/sau khi tạo, kiểm soát dữ liệu đầu vào và giới hạn đặc quyền ghi.

## 1. Tình huống: thêm một tài khoản vào cây thư mục

Giả sử LDAP server đang có cây:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=developers
└── ou=services
```

Ứng dụng cần tạo người dùng `uid=an` dưới nhánh `ou=people`. DN mới dự kiến:

```text
uid=an,ou=people,dc=example,dc=org
```

Muốn gửi yêu cầu tạo entry thành công, cần xác định:

1. **Entry cha** `ou=people,dc=example,dc=org` đã tồn tại.
2. **RDN mới** `uid=an` hợp lệ với naming policy và schema của server.
3. **DN mới** chưa có entry nào sử dụng trong cùng directory.
4. **Object class** của entry mô tả đúng kiểu người dùng cần tạo.
5. Các **attribute bắt buộc** của object class đã được khai báo.
6. Tài khoản dùng kết nối có **quyền thêm entry** tại nhánh này.

Ví dụ entry mong muốn dưới dạng LDIF:

```ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
givenName: An
mail: an@example.org
```

Các dòng `objectClass` biểu diễn những class tham gia vào hệ phân cấp của entry. `uid` là attribute dùng làm RDN trong ví dụ, `cn` và `sn` là những attribute cần có theo lớp `person`. Tập thuộc tính cuối cùng phải hợp lệ với schema của LDAP server thật.

**Lưu ý thuật ngữ “bind”:** trong giao thức LDAP, **Bind operation** dùng để xác thực một kết nối. Trong JNDI/Spring LDAP, `LdapTemplate.bind(...)` lại được dùng trong quy trình **tạo/bind một entry vào directory** (tương ứng ý nghĩa thêm entry). Hai thao tác khác mục đích: gọi `ldapTemplate.bind(entry)` **không phải đăng nhập một người dùng mới**, và không tự động tạo mật khẩu hoặc quyền đăng nhập cho người đó.

## 2. DN và RDN: xác định đúng địa chỉ của entry mới

Một **DN** là tên xác định vị trí entry trong cây LDAP. Tên được viết từ RDN của chính entry tới các RDN của cấp cha.

```text
DN đầy đủ: uid=an,ou=people,dc=example,dc=org
             │       │           └── suffix / domain components
             │       └── OU cha
             └── RDN của entry mới
```

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| RDN mới | `uid=an` | Tên của entry đối với entry cha |
| Parent DN đầy đủ | `ou=people,dc=example,dc=org` | Entry trực tiếp chứa entry mới |
| DN đầy đủ mới | `uid=an,ou=people,dc=example,dc=org` | Tên entry trên directory server |
| `ContextSource.base` | `dc=example,dc=org` | Gốc tương đối của các thao tác Spring LDAP |
| DN tương đối mới | `uid=an,ou=people` | Tên thường truyền cho `LdapTemplate.bind` |

**Parent DN phải tồn tại trước.** LDAP không tự tạo `ou=people` khi bạn thêm `uid=an`. Nếu nhánh people chưa tồn tại, phải tạo OU cha bằng một yêu cầu riêng trước, có schema và quyền ghi phù hợp.

Tính duy nhất của DN mang tính **cấu trúc cây**: hai entry có cùng RDN `uid=an` nhưng nằm dưới hai OU cha khác nhau vẫn có thể có DN khác nhau, nếu chính sách directory cho phép. Ngược lại, không thể tạo hai entry khác nhau có **cùng DN** trong một directory.

### Đừng nhầm “uid duy nhất” với “DN duy nhất”

Giả sử có:

```text
uid=an,ou=employees,dc=example,dc=org
uid=an,ou=contractors,dc=example,dc=org
```

Hai entry có giá trị `uid=an` nhưng DN khác nhau. LDAP **không mặc định bảo đảm** rằng attribute `uid` phải duy nhất trong toàn bộ cây. Nếu doanh nghiệp cần một mã đăng nhập duy nhất, phải có chính sách và cơ chế kiểm soát riêng; không chỉ dựa vào việc DN mới chưa bị trùng.

## 3. DN tương đối khi ContextSource đã cấu hình base

Một cấu hình Spring Boot minh họa:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Ví dụ trên sử dụng biến môi trường cho URL, bind DN và mật khẩu. Trong hệ thống thật cần cấu hình chứng chỉ/CA tin cậy, xác minh hostname TLS và giữ mật khẩu ngoài repository.

Với `ContextSource.base = "dc=example,dc=org"`:

```text
DN tương đối để gửi vào LdapTemplate:
uid=an,ou=people

ContextSource base:
dc=example,dc=org

DN mà LDAP server định vị:
uid=an,ou=people,dc=example,dc=org
```

| Cấu hình ContextSource base | DN cần đưa vào `LdapTemplate` |
| --- | --- |
| `dc=example,dc=org` | `uid=an,ou=people` |
| `ou=people,dc=example,dc=org` | `uid=an` |
| Base rỗng | `uid=an,ou=people,dc=example,dc=org` |

Nếu template đã có base `dc=example,dc=org` mà bạn lại truyền DN đầy đủ `uid=an,ou=people,dc=example,dc=org`, hậu tố có thể bị áp dụng **hai lần**, khiến thao tác trỏ sai nơi.

**Bind DN của tài khoản dịch vụ** (ví dụ `cn=app-writer,ou=services,dc=example,dc=org`) là danh tính dùng kết nối/xác thực. Nó không phải DN của entry mới và thường được cấu hình riêng.

## 4. Dựng DN an toàn bằng LdapNameBuilder

DN có cấu trúc, không nên tạo từ phép nối chuỗi:

```java
// Tránh:
String dn = "uid=" + suppliedUid + ",ou=people";
```

Nếu `suppliedUid` chứa dấu phẩy, dấu cộng, dấu gạch chéo ngược, ký tự đặc biệt hoặc khoảng trắng ở vị trí cần escape, chuỗi ghép thô có thể trở thành một DN sai cấu trúc hoặc trỏ sang entry khác.

Spring LDAP cung cấp `LdapNameBuilder`:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public static Name newPersonDn(String suppliedUid) {
    if (suppliedUid == null || suppliedUid.isBlank()) {
        throw new IllegalArgumentException("uid must not be blank");
    }

    return LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", suppliedUid)
        .build();
}
```

Với `suppliedUid = "an"`, tên tương đối được biểu diễn là:

```text
uid=an,ou=people
```

Với `suppliedUid = "an,qa"`, builder xử lý dấu phẩy là **một phần của giá trị RDN**, không tách thành RDN mới. Tuy nhiên, **escape đúng không đồng nghĩa dữ liệu được phép sử dụng**: nghiệp vụ vẫn phải kiểm tra độ dài, pattern, chuẩn hóa và quy tắc cho UID. Một ứng dụng có thể chỉ cho phép UID gồm chữ cái, chữ số và dấu gạch ngang; đó là quyết định riêng của ứng dụng/directory.

### Tạo DN có nhiều OU

Nếu entry cần nằm trực tiếp dưới `ou=hanoi,ou=employees,ou=people`:

```java
Name dn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("ou", "employees")
    .add("ou", "hanoi")
    .add("uid", suppliedUid)
    .build();
```

Kết quả tương đối có dạng:

```text
uid=an,ou=hanoi,ou=employees,ou=people
```

Mọi entry cha `ou=people`, `ou=employees` và `ou=hanoi` cần tồn tại đúng đường dẫn. Nếu ứng dụng có nhiều tổ chức/tenant, **không lấy nguyên chuỗi OU từ request để quyết định parent DN không kiểm soát**. Nên ánh xạ quyền/tenant sang một tập nhánh được phép ở phía server ứng dụng.

### RDN có thể không phải uid

Một số directory dùng RDN `cn=...` để đặt tên person, `ou=...` cho organizational unit, hoặc RDN nhiều thành phần. Không có một quy tắc toàn cục rằng mọi `inetOrgPerson` đều phải dùng `uid` làm RDN. Hãy tuân theo cấu trúc directory và các **name form / DIT structure rule** được server áp dụng, nếu có.

Khi RDN chứa `uid=an`, entry mới phải mang attribute `uid` với giá trị phù hợp. Không chỉ đặt tên theo RDN rồi bỏ quên giá trị attribute mà schema/naming rule đòi hỏi.

## 5. Object class quyết định mô hình entry

**`objectClass` là một thuộc tính LDAP nhiều giá trị** cho biết entry thuộc các object class nào. Từ schema của từng object class, LDAP server xác định các ràng buộc về loại và số lượng attribute.

Ba nhóm object class quan trọng:

| Loại object class | Vai trò | Ví dụ |
| --- | --- | --- |
| **Abstract** | Làm cơ sở kế thừa, không dùng một mình như loại entry cụ thể | `top` |
| **Structural** | Xác định bản chất cấu trúc của entry và kế thừa các yêu cầu | `person`, `organizationalPerson`, `inetOrgPerson`, `organizationalUnit` |
| **Auxiliary** | Bổ sung tập thuộc tính/hành vi cho structural class nếu schema cho phép | Các auxiliary class được directory triển khai |

Một entry thông thường phải tuân theo quy tắc structural object class hợp lệ. Trong ví dụ:

```text
top (ABSTRACT)
    └── person (STRUCTURAL)
         └── organizationalPerson (STRUCTURAL)
              └── inetOrgPerson (STRUCTURAL)
```

Đây là **một chuỗi kế thừa structural**, không phải bốn structural class độc lập cùng cạnh tranh. Tạo entry có `inetOrgPerson` cần tính cả các yêu cầu được kế thừa từ `person`.

### MUST và MAY

| Khái niệm trong schema | Ý nghĩa |
| --- | --- |
| `MUST` | Thuộc tính bắt buộc phải có để entry tuân schema |
| `MAY` | Thuộc tính được phép có, nhưng không bắt buộc |
| `SINGLE-VALUE` | Attribute type chỉ cho phép tối đa một giá trị |
| Syntax / matching rule | Xác định dạng giá trị hợp lệ và cách so khớp |

Với object class `person`, hai attribute được yêu cầu quan trọng là **`cn` và `sn`**. `inetOrgPerson` kế thừa các yêu cầu này. Một entry chứa `uid`, `mail` hoặc `givenName` có thể dùng chúng nếu schema phù hợp, nhưng không thay thế được `cn` và `sn`.

### Không tự ý chọn object class theo tên nghiệp vụ

“Nhân viên” không nhất thiết là một object class có tên `employee`. Trong nhiều hệ thống, người dùng được mô hình bằng `inetOrgPerson` cùng thuộc tính hoặc auxiliary class riêng. Việc chọn class phải dựa trên **schema thực có** của server, không suy từ tên DTO Java hoặc bảng SQL.

Nếu hệ thống cần một auxiliary class như `posixAccount`, phải bảo đảm class đó thực sự có trong schema và cung cấp các attribute MUST bổ sung. Chỉ thêm tên class mới mà không tạo đủ thuộc tính bắt buộc có thể khiến server trả lỗi `objectClassViolation`.

## 6. Chuẩn bị tập objectClass cho inetOrgPerson

Một cách khai báo rõ ràng khi tạo entry mới:

```java
context.setAttributeValues("objectClass", new String[] {
    "top",
    "person",
    "organizationalPerson",
    "inetOrgPerson"
});
```

Đây là toàn bộ chuỗi lớp kế thừa trong ví dụ. `objectClass` là multi-valued attribute; gọi liên tiếp `setAttributeValue("objectClass", "...")` cho từng class có thể khiến giá trị trước đó bị thay thế, không còn tập lớp mong muốn.

Sau đó cung cấp các attribute:

```java
context.setAttributeValue("uid", "an");       // Tên RDN và attribute UID
context.setAttributeValue("cn", "An Nguyen");  // Bắt buộc theo person
context.setAttributeValue("sn", "Nguyen");     // Bắt buộc theo person
context.setAttributeValue("givenName", "An");  // Tùy chọn trong schema phù hợp
context.setAttributeValue("mail", "an@example.org");
```

**Không chỉ dùng `objectClass: inetOrgPerson` như một lối tắt mà mặc định mọi directory server sẽ xử lý identically**: server có thể suy ra hoặc yêu cầu thể hiện đầy đủ chuỗi class tùy chính sách/triển khai. Khi dùng ví dụ để học hoặc kiểm thử, liệt kê rõ hệ lớp giúp nhìn thấy các yêu cầu kế thừa.

Nếu directory có thêm custom object class, cần đọc định nghĩa schema, các attribute `MUST/MAY`, loại class, super class và ràng buộc naming/DIT trước khi thêm vào entry.

## 7. Tạo một organizationalUnit trước khi tạo entry con

Khi muốn thêm người dùng vào OU mới, hãy tạo **parent OU** trước, theo thứ tự từ trên xuống.

Ví dụ tạo `ou=contractors,ou=people,dc=example,dc=org` khi `ou=people` đã tồn tại:

```ldif
dn: ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: contractors
description: External contractors
```

Khác với `inetOrgPerson`, object class `organizationalUnit` yêu cầu attribute `ou`. Không nên thêm `cn` và `sn` rồi coi OU là một người dùng.

Ví dụ Java:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

Name ouDn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("ou", "contractors")
    .build();

DirContextAdapter ouContext = new DirContextAdapter(ouDn);
ouContext.setAttributeValues("objectClass",
    new String[] {"top", "organizationalUnit"});
ouContext.setAttributeValue("ou", "contractors");
ouContext.setAttributeValue("description", "External contractors");

ldapTemplate.bind(ouContext);
```

Đoạn ví dụ giả định có biến `ldapTemplate` đã được cấu hình và tài khoản service có quyền tạo OU. Đây là thao tác thêm **một entry OU**. Chỉ sau khi OU đó đã tồn tại mới tạo các user nằm trực tiếp dưới nó:

```text
uid=an,ou=contractors,ou=people,dc=example,dc=org
```

Nếu có nhiều OU cần được tạo, các thao tác thêm nhiều entry là những yêu cầu riêng. Không tự coi chuỗi nhiều lần `bind` là một giao dịch LDAP có rollback toàn bộ.

## 8. Viết repository tạo người dùng bằng Spring LDAP

Đoạn ví dụ Java 17+ sau cho thấy quy trình **chuẩn bị DN, object class và các attribute**, rồi mới gửi Add request thông qua `LdapTemplate.bind(...)`. Nó dùng `DirContextAdapter` để tránh tự tạo cấu trúc `Attributes` bằng JNDI.

```java
import java.util.List;
import java.util.Objects;
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonEntryRepository {
    private final LdapTemplate ldapTemplate;

    public PersonEntryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void create(
            String uid,
            String commonName,
            String surname,
            List<String> emails) {

        requireText(uid, "uid");
        requireText(commonName, "commonName");
        requireText(surname, "surname");
        Objects.requireNonNull(emails, "emails");

        // App xác nhận người dùng được tạo dưới ou=people.
        Name relativeDn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();

        // Context mới: chưa có entry nào được ghi lên server.
        DirContextAdapter entry = new DirContextAdapter(relativeDn);
        entry.setAttributeValues("objectClass", new String[] {
            "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", uid);
        entry.setAttributeValue("cn", commonName);
        entry.setAttributeValue("sn", surname);

        // Mail là optional; ví dụ này đặt toàn bộ tập được gửi.
        if (!emails.isEmpty()) {
            entry.setAttributeValues(
                "mail",
                emails.toArray(String[]::new)
            );
        }

        // Chỉ lời gọi này yêu cầu LDAP server tạo entry.
        ldapTemplate.bind(entry);
    }

    private static void requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                fieldName + " must not be blank");
        }
    }
}
```

Giải thích từng quyết định:

1. **Kiểm tra dữ liệu bắt buộc trước khi gửi.** Ví dụ này chỉ kiểm tra rỗng; ứng dụng thật cần policy UID, độ dài, định dạng email và các điều kiện nghiệp vụ.
2. **Dùng `LdapNameBuilder` để tạo DN an toàn.** Chọn parent `ou=people` do ứng dụng kiểm soát thay vì nhận toàn bộ DN từ request.
3. **Tạo `DirContextAdapter(relativeDn)`.** Đây là object trong bộ nhớ chuẩn bị entry mới, không phải kết quả của `lookupContext`.
4. **Thiết lập object classes trước.** Mảng chứa lớp abstract và structural chain phù hợp với người dùng.
5. **Điền các attribute.** `uid` phù hợp với RDN; `cn` và `sn` đáp ứng yêu cầu từ `person`.
6. **Chỉ đặt `mail` khi có giá trị.** Không truyền mảng rỗng để biểu diễn “một email rỗng”.
7. **Gọi `ldapTemplate.bind(entry)`.** Spring LDAP lấy context qua `ContextSource` và gửi yêu cầu tạo entry. Nếu server trả lỗi, đừng ghi nhận tạo thành công.

### Vì sao ví dụ không tạo userPassword?

Tạo entry thư mục và thiết lập **credential đăng nhập** là hai nghiệp vụ liên quan nhưng khác nhau. `userPassword`, chính sách password, cách hash, yêu cầu bảo mật và cách thay đổi password phụ thuộc LDAP server. Không tự thêm mật khẩu dạng plaintext vào LDIF hoặc log. Nếu có yêu cầu tạo tài khoản đăng nhập, hãy thực hiện riêng theo chính sách xác thực, TLS và quản lý secret của directory.

### Còn LdapClient và ODM?

Ở phiên bản Spring LDAP hỗ trợ, `LdapClient` và ODM có thể cung cấp cách diễn đạt thao tác tạo entry hoặc mapping từ model. Dù chọn API nào, **DN, object class, attribute bắt buộc và quyền thêm entry** vẫn phải đúng. `LdapTemplate.bind(...)` được dùng trong bài vì làm rõ nhất quá trình chuẩn bị dữ liệu.

## 9. Trình tự tạo entry và lưu ý về cập nhật

Khi đã chuẩn bị xong, luồng cơ bản:

```text
Yêu cầu nghiệp vụ
      │
      ▼
Chọn OU được phép, xác minh parent đã tồn tại
      │
      ▼
LdapNameBuilder → DN tương đối hợp lệ
      │
      ▼
Chọn structural object class + attribute MUST/MAY
      │
      ▼
DirContextAdapter → objectClass, uid, cn, sn, ...
      │
      ▼
LdapTemplate.bind(entry)
      │
      ├── Thành công → có entry mới tại DN
      └── Lỗi → phân loại nguyên nhân / quyết định xử lý
```

**`bind` là thao tác tạo, không phải “create-or-update” tự động.** Nếu entry tại DN đã tồn tại, máy chủ có thể trả `entryAlreadyExists`. Khi muốn **sửa** attribute của một entry hiện có, quy trình đúng thường là:

```java
// Ý tưởng cập nhật, không thay thế cho bind khi tạo mới:
var current = ldapTemplate.lookupContext(relativeDn);
current.setAttributeValue("displayName", "An N.");
ldapTemplate.modifyAttributes(current);
```

Khi muốn **chuyển entry sang DN mới**, sử dụng thao tác rename/ModifyDN phù hợp, không tự đổi thuộc tính `uid` rồi coi DN đã đổi.

### “Check tồn tại rồi bind” vẫn có race condition

Ứng dụng đôi khi tìm trước:

```text
lookup(DN) → chưa thấy
bind(DN)   → tạo
```

Giữa hai lời gọi, một request khác có thể đã tạo entry tại cùng DN. Vì vậy, kiểm tra trước chỉ giúp hiển thị thông báo thân thiện; **server vẫn là nơi quyết định tính duy nhất tại thời điểm thêm**. Luôn xử lý trường hợp `entryAlreadyExists` ngay khi gọi `bind`.

Tương tự, nếu kết nối bị mất **sau khi đã gửi** yêu cầu Add nhưng trước khi ứng dụng nhận phản hồi, trạng thái thực tế có thể không rõ. Không retry mù quáng như thể thao tác chắc chắn chưa xảy ra. Có thể tra cứu lại DN với quyền phù hợp, xác minh các thuộc tính nhận dạng và dùng chính sách idempotency của ứng dụng.

## 10. Tạo nhóm hoặc loại entry khác cần schema khác

Chọn `inetOrgPerson` cho một tài khoản cá nhân **không có nghĩa** mọi entry khác dùng cùng tập thuộc tính.

| Loại entry | Structural object class minh họa | Attribute bắt buộc điển hình | RDN hay dùng |
| --- | --- | --- | --- |
| Người dùng | `inetOrgPerson` (kế thừa `person`) | `cn`, `sn` | `uid` hoặc `cn` theo naming policy |
| Organizational unit | `organizationalUnit` | `ou` | `ou` |
| Group of names | `groupOfNames` | `cn`, `member` | `cn` |
| Domain component | `domain` hoặc class tương ứng do server hỗ trợ | Phụ thuộc schema, thường có `dc` | `dc` |

Ví dụ tối giản về nhóm:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
```

Lớp `groupOfNames` thường yêu cầu có ít nhất một giá trị `member`. Nếu nghiệp vụ cần **nhóm rỗng**, không được tự bỏ `member` và giả định server vẫn cho tạo; hãy lựa chọn mô hình group/schema phù hợp với directory server.

Giá trị `member` là **DN của entry thành viên**, không phải DN của chính nhóm. Parent `ou=groups` cũng phải tồn tại. Việc server có kiểm tra member DN thực sự tồn tại không còn phụ thuộc implementation/chính sách, nên ứng dụng cần chính sách kiểm chứng phù hợp.

**Không trộn structural object class không tương thích.** Ví dụ gắn cả `inetOrgPerson` và `organizationalUnit` như hai nhánh structural độc lập vào cùng một entry có thể gây lỗi `objectClassViolation`. Nếu cần gắn thông tin bổ sung, chọn auxiliary class phù hợp và xem schema.

## 11. Những lỗi LDAP thường gặp khi chuẩn bị DN và schema

| Kết quả/lỗi từ server | Ý nghĩa hay gặp | Cách kiểm tra |
| --- | --- | --- |
| `entryAlreadyExists (68)` | DN mới đã được dùng | Kiểm tra tên chuẩn hóa và chính sách xử lý trùng |
| `noSuchObject (32)` | Entry cha hoặc một nhánh cần thiết không tồn tại | Kiểm tra parent DN, base context, tạo OU cha trước |
| `objectClassViolation (65)` | Thiếu `MUST`, attribute không được phép hoặc chuỗi object class sai | Đọc schema; kiểm tra `objectClass`, `cn`, `sn` |
| `invalidAttributeSyntax (21)` | Giá trị không đúng syntax của attribute | Xác minh định dạng và kiểu dữ liệu |
| `namingViolation (64)` | Tên vi phạm naming rule/DIT structure | Kiểm tra RDN và name form server áp dụng |
| `insufficientAccessRights (50)` | Bind account không có quyền Add/ghi tại OU | Kiểm tra ACL và phạm vi service account |
| Lỗi kết nối, bind hoặc TLS | Không tới server, bind sai hoặc chứng chỉ không hợp lệ | Kiểm tra URL, CA/truststore, secret và mạng |

Các mã trong bảng là result code của giao thức LDAP; thư viện Spring LDAP thường biểu diễn lỗi qua exception tương ứng. **Tên lớp exception chính xác phụ thuộc version và cách dịch lỗi**, nên không nên bắt một `Exception` duy nhất rồi coi mọi tình huống là “đã tồn tại”.

Hai vấn đề dễ nhầm:

- **Entry cha không tồn tại:** không thể tạo entry con trực tiếp dù DN của con trông hợp lệ.
- **Entry con đã tồn tại:** cần trả lỗi trùng hoặc thực hiện luồng cập nhật có chủ đích, không gọi Add lặp lại để cố “upsert”.

Với kết nối bị lỗi giữa chừng, phải ghi nhận trạng thái **chưa xác định** khi không nhận được phản hồi cuối cùng. Không chỉ dựa vào việc client ném exception để khẳng định server chắc chắn chưa tạo entry.

## 12. Checklist an toàn trước khi tạo entry

Đối với một endpoint cho phép thêm người dùng, hãy kiểm tra:

| Điều cần kiểm tra | Vì sao quan trọng |
| --- | --- |
| **Nhánh đích đã được phê duyệt** | Tránh request tự tạo entry ở OU/tenant không được phép |
| **Parent DN tồn tại** | LDAP Add không tạo tự động toàn bộ đường dẫn cha |
| **RDN có kiểu thuộc tính phù hợp** | Tên đúng naming policy, schema và dữ liệu của entry |
| **Giá trị RDN được escape** | Không dùng phép nối chuỗi DN không kiểm soát |
| **DN chưa bị trùng** | Trả lỗi rõ khi `entryAlreadyExists`, tránh giả định UID unique toàn cây |
| **Object class tồn tại trong schema** | Không gửi custom class chưa đăng ký trên server |
| **MUST/MAY và syntax hợp lệ** | Bao gồm các thuộc tính kế thừa và ràng buộc đơn/đa trị |
| **ACL của account tạo entry** | Chỉ cấp quyền Add ở những nhánh cần thiết |
| **TLS và secret an toàn** | LDAPS/StartTLS, chứng chỉ tin cậy, bind password không nằm trong log |
| **Không gửi dữ liệu nhạy cảm ngoài nhu cầu** | Giảm bề mặt rủi ro và tránh attribute không được phép |
| **Xử lý lỗi tạo entry rõ ràng** | Phân biệt trùng DN, thiếu parent, thiếu quyền, schema và outage |
| **Chiến lược xử lý retry** | Không tạo trùng hoặc báo sai trong tình huống phản hồi không xác định |

Một tài khoản dịch vụ **chỉ cần đọc** không nên được cấp quyền tạo entry. Nếu ứng dụng có cả thao tác đọc và ghi, có thể tách quyền bind hoặc giới hạn ACL theo chức năng/OU; không sử dụng tài khoản quản trị directory cho mọi request thông thường.

Đối với môi trường doanh nghiệp, cần thiết lập timeout, quan sát tỷ lệ lỗi Add và khả năng phục hồi kết nối. Pooling hoặc `ContextSource` proxy có thể hỗ trợ vận hành nhưng **không thay thế schema validation, ACL hoặc quyết định vị trí DN**.

## 13. Kiểm tra thao tác tạo bằng công cụ dòng lệnh

Lệnh OpenLDAP client `ldapadd` có thể dùng để đối chiếu với Spring LDAP trên môi trường thử nghiệm đã được phép ghi. Tệp `new-person.ldif` là dữ liệu minh họa theo phần 1, không bao gồm password.

```bash
ldapadd -x -H ldaps://ldap.example.org:636 \
  -D "cn=app-writer,ou=services,dc=example,dc=org" -W \
  -f new-person.ldif
```

Sau khi tạo, đọc lại đúng entry:

```bash
ldapsearch -x -LLL -H ldaps://ldap.example.org:636 \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "uid=an,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn objectClass uid cn sn mail
```

Chú ý: `ldapadd` và `ldapsearch -b` thường dùng **DN đầy đủ** trong LDIF và command line, khác với **DN tương đối** truyền vào `LdapTemplate` khi `ContextSource.base` đã được đặt.

Trong thực tế, tài khoản tạo và tài khoản đọc có thể khác nhau. Nếu một entry vừa được thêm nhưng tài khoản reader không có quyền xem, không nên kết luận ngay rằng lệnh Add thất bại; cần phân biệt quyền truy cập và kết quả ghi.

**Không chạy lệnh thử trên production**, không dùng tài khoản quản trị nếu không có quy trình cấp phép, và không đưa mật khẩu trực tiếp vào tham số để tránh lộ qua lịch sử shell hoặc danh sách tiến trình.

## 14. Kiểm thử tạo DN và object class trong Spring LDAP

Nên tách kiểm thử thành hai tầng: **unit test chuẩn bị dữ liệu** không cần LDAP server và **integration test kiểm tra Add thật**.

### 14.1. Unit test cách dựng DN

Java 17 + JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class PersonDnTest {
    @Test
    void buildsExpectedRelativeDn() {
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "an")
            .build();

        assertEquals("uid=an,ou=people", dn.toString());
    }

    @Test
    void commaInsideUidDoesNotCreateAnotherRdn() {
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "an,qa")
            .build();

        assertEquals(2, dn.size());
        assertTrue(dn.toString().contains("\\,"));
    }
}
```

Test thứ hai quan trọng ở chỗ giá trị `an,qa` vẫn chỉ tạo **một RDN uid** dưới `ou=people`; dấu phẩy được escape trong DN. Nếu chính sách UID không cho phép dấu phẩy, tầng validation vẫn phải từ chối giá trị này, dù builder tạo được tên hợp lệ.

### 14.2. Unit test tập thuộc tính của entry mới

Không cần gửi Add request để xác minh object đã điền `objectClass`, `cn` và `sn` đúng:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

class NewPersonAttributesTest {
    @Test
    void preparesRequiredAttributesBeforeBind() {
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "an")
            .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[] {
            "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", "an");
        entry.setAttributeValue("cn", "An Nguyen");
        entry.setAttributeValue("sn", "Nguyen");

        assertEquals("uid=an,ou=people", entry.getDn().toString());
        assertEquals("an", entry.getStringAttribute("uid"));
        assertEquals("An Nguyen", entry.getStringAttribute("cn"));
        assertEquals("Nguyen", entry.getStringAttribute("sn"));
        assertEquals(4, entry.getStringAttributes("objectClass").length);
    }
}
```

Các test này xác minh **bộ dữ liệu cục bộ** của adapter. Chúng không chứng minh parent DN tồn tại, server chấp nhận schema hoặc account có quyền Add.

### 14.3. Integration test với LDAP server thử nghiệm

Chuẩn bị subtree riêng (ví dụ `ou=people,dc=test,dc=example,dc=org`) và account có quyền được cấp trước. Các trường hợp cần xác minh:

1. **Parent đã tồn tại:** `bind` tạo được user ở nhánh test.
2. **DN chính xác:** `lookup` theo DN tương đối trả đúng entry, không lặp hậu tố base.
3. **Object classes:** đọc lại thấy structural chain và những attribute theo schema của server.
4. **Thiếu `cn` hoặc `sn`:** server từ chối entry không hợp lệ.
5. **Parent thiếu:** Add không tự tạo OU và trả lỗi tương ứng.
6. **DN đã tồn tại:** lần tạo thứ hai bị từ chối; không tạo entry thứ hai tại cùng tên.
7. **RDN chứa ký tự đặc biệt:** nếu naming policy cho phép, builder tạo tên đúng; server giải quyết tên được escape chính xác.
8. **ACL:** account chỉ đọc không thể Add; account ghi chỉ có quyền trong OU test được phép.
9. **TLS/credential:** kết nối sai chứng chỉ hoặc bind credential sai phải thất bại rõ ràng.
10. **Kết quả không chắc chắn sau timeout:** ứng dụng có cách kiểm tra entry trước khi retry, không báo chắc “chưa tạo”.

Test dữ liệu thật chỉ thực hiện trong môi trường thử nghiệm phù hợp. Nếu cần cleanup, xóa các entry thử nghiệm theo đúng quyền và thứ tự con-trước-cha; không thao tác lên entry thuộc người dùng thật.

## 15. Các hiểu nhầm cần tránh

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| `LdapTemplate.bind` là thao tác đăng nhập | Trong ngữ cảnh tạo entry, nó yêu cầu **thêm entry**; đăng nhập LDAP Bind là thao tác riêng |
| Chỉ cần `uid` và `mail` là đủ để tạo `inetOrgPerson` | `cn`, `sn` cũng bắt buộc do kế thừa từ `person` |
| `objectClass` chỉ cần chọn theo tên DTO Java | Phải theo schema và loại structural/auxiliary hợp lệ |
| DN có thể dựng bằng nối chuỗi thoải mái | Phải escape RDN và kiểm soát OU/tenant |
| `ContextSource.base` và DN của entry mới phải đều là DN đầy đủ | Khi đã có base context, template thường nhận DN tương đối |
| LDAP tự tạo OU cha nếu DN đủ dài | LDAP Add không tạo các parent còn thiếu |
| `uid` luôn là RDN của mọi người dùng | RDN phụ thuộc naming policy; có thể là `cn` hoặc thuộc tính khác |
| DN mới chưa trùng nghĩa là uid unique toàn cây | UID có thể trùng ở những OU khác nhau nếu không có policy riêng |
| Dùng `bind` lần nữa để cập nhật entry hiện có | Thay đổi entry đã có phải dùng Modify; đổi DN phải dùng ModifyDN |
| Gọi `setAttributeValue` là dữ liệu đã lưu trên server | Setter chỉ sửa adapter trong bộ nhớ; `bind` mới gửi yêu cầu Add |
| Timeout chắc chắn nghĩa là Add chưa được thực hiện | Server có thể đã tạo entry trước khi phản hồi bị mất |
| Có quyền search đồng nghĩa có quyền Add | LDAP ACL có thể cấp quyền đọc nhưng từ chối thêm entry |

## 16. Bài tập tự kiểm tra

Cho cây thư mục:

```text
dc=example,dc=org
├── ou=people
│   └── ou=employees
└── ou=groups
```

Ứng dụng sử dụng `ContextSource.base = "dc=example,dc=org"`, cần tạo người dùng `uid=mai` dưới `ou=employees,ou=people`. Giả định LDAP server hỗ trợ `inetOrgPerson`, RDN `uid` và tài khoản service có quyền tạo trong OU đó.

**Câu hỏi:**

1. DN đầy đủ của Mai phải là gì?
2. DN tương đối nào truyền cho `new DirContextAdapter(dn)`?
3. Dùng `LdapNameBuilder` theo thứ tự nào để tạo DN tương đối?
4. `objectClass` nên chứa các tên nào trong chuỗi kế thừa `inetOrgPerson`?
5. Hai attribute bắt buộc nào được kế thừa từ `person`?
6. Vì sao không thể tạo ngay `uid=mai,ou=contractors,ou=people,...` nếu chưa có `ou=contractors`?
7. Hai entry `uid=mai,ou=employees,...` và `uid=mai,ou=contractors,...` có cùng DN không?
8. Nếu `bind` được gọi hai lần với cùng DN thì điều gì thường xảy ra?
9. Khi user vừa được tạo, muốn đổi `displayName` thì có gọi lại `bind` không?
10. Nếu client timeout sau khi gửi Add, có thể khẳng định server chưa tạo entry không?

### Đáp án và giải thích

1. `uid=mai,ou=employees,ou=people,dc=example,dc=org`.
2. `uid=mai,ou=employees,ou=people` vì ContextSource đã chứa `dc=example,dc=org`.
3. `newInstance().add("ou","people").add("ou","employees").add("uid","mai").build()`.
4. `top`, `person`, `organizationalPerson` và `inetOrgPerson`.
5. `cn` và `sn`; phải cung cấp chúng với giá trị hợp lệ.
6. LDAP không tạo parent tự động; cần tạo/đảm bảo `ou=contractors` trước.
7. Không. Hai DN khác nhau vì parent OU khác nhau, dù cùng giá trị UID.
8. Lần đầu có thể thành công; lần sau thường bị từ chối vì DN đã tồn tại. Không coi `bind` là upsert.
9. Không; dùng thao tác Modify/`LdapTemplate.modifyAttributes` phù hợp.
10. Không. Yêu cầu có thể đã đến server và tạo thành công trước khi kết nối lỗi; cần kiểm tra lại trạng thái theo quy trình.

## 17. Tổng kết và tài liệu tham khảo

Trước khi gọi `LdapTemplate.bind(...)` để tạo entry, cần chuẩn bị **DN mới** theo cấu trúc DIT và **object class** phù hợp với schema. DN phải có parent tồn tại, RDN hợp lệ, không trùng tên và được xây an toàn bằng `LdapNameBuilder`. Nếu `ContextSource` đã có base DN, thao tác Spring LDAP thường dùng **DN tương đối** chứ không phải DN đầy đủ.

Với `inetOrgPerson`, cần khai báo chuỗi class hợp lệ và điền các attribute bắt buộc kế thừa như `cn`/`sn`. `DirContextAdapter` chuẩn bị attribute trong bộ nhớ, còn `LdapTemplate.bind` mới yêu cầu LDAP server tạo entry. Thành công cuối cùng luôn phụ thuộc schema, naming policy, ACL, TLS và kết quả Add từ server. Các thao tác Modify/ModifyDN là bước khác, không được thay thế bằng Add lặp lại.

Tài liệu tham khảo:

- [Spring LDAP — Reference Documentation](https://docs.spring.io/spring-ldap/reference/): thao tác bind/create entry, `DirContextAdapter`, `LdapTemplate` và `ContextSource`.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): overload `bind`, lookup, modify và rename.
- [Spring LDAP — DirContextAdapter API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html): tạo context chứa các attribute của entry mới.
- [Spring LDAP — LdapNameBuilder API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): dựng DN/RDN có escape.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DN, object classes, `MUST`/`MAY` và schema.
- [RFC 4514 — LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn và escaping DN/RDN.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Bind, Add, Modify, ModifyDN và mã lỗi LDAP.
- [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798): định nghĩa `inetOrgPerson`.
