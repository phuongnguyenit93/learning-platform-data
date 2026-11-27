# Kiểm tra dữ liệu trước khi tạo entry trong Spring LDAP

## 1. Từ một yêu cầu API đến một LDAP Add an toàn

Một ứng dụng quản lý danh tính có thể nhận yêu cầu tạo người dùng từ API, hệ thống nhân sự hoặc một tác vụ đồng bộ. Ví dụ:

~~~json
{
  "uid": "training-01",
  "commonName": "Training User",
  "surname": "User",
  "email": "training-01@example.org",
  "phoneNumbers": ["+84 28 1111 2222", "+84 28 3333 4444"]
}
~~~

Với **Spring LDAP**, một lối triển khai là chuyển dữ liệu thành đối tượng **DirContextAdapter** rồi gọi **LdapTemplate.bind(context)**. Tuy nhiên, nếu lập tức gửi dữ liệu chưa kiểm tra, server có thể từ chối vì DN trùng, parent không tồn tại, thiếu thuộc tính bắt buộc, object class không tương thích, ACL không cho phép, hoặc giá trị vi phạm schema.

**Kiểm tra dữ liệu trước khi tạo entry** là bước xác minh hợp đồng đầu vào, định danh/DN, vị trí tạo, tập thuộc tính và những chính sách nghiệp vụ có thể kiểm tra tại client. Nó giúp phát hiện sớm yêu cầu sai, giảm thao tác LDAP không cần thiết và đưa ra phản hồi rõ ràng. Nhưng **pre-validation không thay thế LDAP server**, nơi vẫn quyết định cuối cùng về schema, quyền, trùng DN và trạng thái đồng thời.

Bài học thuộc chương **Bind và tạo entry** của module **Spring LDAP**, liên kết các kiến thức DN, schema, filter, tìm kiếm và thao tác entry bằng **LdapTemplate**, **LdapClient** hoặc ODM với TLS, xác thực, pooling, xử lý lỗi và kiểm thử truy cập thư mục an toàn.

**Mục tiêu sau bài học:** bạn sẽ biết kiểm tra dữ liệu để tạo LDAP entry hợp lệ, phân biệt validation và quyền của server, xây DN an toàn, thiết kế DTO/Bean Validation, hiểu giới hạn của pre-check uniqueness, triển khai thao tác Add, kiểm thử và xử lý các lỗi quan trọng.

### Bind tạo entry và Bind xác thực không giống nhau

Trong ngữ cảnh Spring LDAP/JNDI, `LdapTemplate.bind(context)` dùng để **tạo một entry** tương đương LDAP **Add**. Từ “Bind” trong giao thức LDAP còn chỉ thao tác **xác thực** một danh tính trên kết nối. Không được nhầm hai việc này:

| Công việc | API/khái niệm | Tác dụng |
| --- | --- | --- |
| Tạo entry | `LdapTemplate.bind(context)` | Gửi LDAP Add cho DN mới |
| Xác thực mật khẩu | LDAP Bind, `authenticate(...)` | Kiểm tra danh tính và credentials |
| Sửa entry | `modifyAttributes(...)` | Gửi LDAP Modify |
| Đổi RDN hoặc di chuyển | `rename(oldDn, newDn)` | Gửi LDAP Modify DN |
| Xóa entry | `unbind(dn)` | Gửi LDAP Delete |

Entry có UID, tên và họ hợp lệ **chưa đồng nghĩa tài khoản đã được cấp quyền đăng nhập**. Cấp phát thông tin xác thực và chính sách mật khẩu là quy trình riêng, không nên tự lưu mật khẩu plaintext vào entry chỉ để thao tác Add thành công.

## 2. Một entry hợp lệ cần đáp ứng những điều kiện nào?

Xét cấu trúc thư mục thử nghiệm:

~~~text
dc=example,dc=org
|
+-- ou=people                  <-- OU đã tồn tại
|   +-- uid=alice
|   +-- ou=engineering
|       +-- uid=bob
|
+-- ou=groups
|   +-- cn=developers
|
+-- ou=system
    +-- cn=directory-reader
    +-- cn=directory-editor
~~~

Dữ liệu dự kiến tạo:

~~~ldif
dn: uid=training-01,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: training-01
cn: Training User
sn: User
mail: training-01@example.org
telephoneNumber: +84 28 1111 2222
telephoneNumber: +84 28 3333 4444
~~~

Trước khi gọi Add, cần trả lời:

| Nhóm kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Hợp đồng đầu vào | Trường bắt buộc có mặt, không rỗng, đúng kiểu/độ dài? | `uid`, `cn`, `sn` |
| Định danh | UID hợp chính sách? RDN nhất quán? | `uid=training-01` |
| Vị trí | Parent OU có tồn tại và nằm trong vùng được phép? | `ou=people` |
| Schema | `objectClass`, `MUST`, `MAY` và cú pháp hợp lệ? | `inetOrgPerson` |
| Tính đa trị | Số lượng/phân bố giá trị thuộc tính đúng? | Hai `telephoneNumber` |
| Nghiệp vụ | Cần unique UID trên cả subtree hay chỉ không trùng DN? | Định danh nhân viên |
| Quyền truy cập | Tài khoản dịch vụ có quyền Add tại OU? | `directory-editor` |
| Đồng thời | Request khác có thể tạo trùng trước không? | LDAP result code 68 |

Một số kiểm tra có thể làm trước ở Java. Một số khác phải để **LDAP server** kiểm tra tại thời điểm Add.

### 2.1. Bảng phân quyền trách nhiệm validation

| Điều kiện | Kiểm tra ở Java | Server kiểm tra cuối cùng |
| --- | --- | --- |
| Trường không rỗng hoặc giới hạn API | Có | Có thể không áp cùng policy |
| Regex UID nội bộ | Có | Naming constraints có thể khác |
| DN đúng cú pháp | Có, với `LdapNameBuilder` | Có |
| Parent DN tồn tại | Có thể lookup hỗ trợ | **Có tại thời điểm Add** |
| DN chưa tồn tại | Có thể lookup trước | **Có tại thời điểm Add** |
| Object class và thuộc tính MUST/MAY | Có theo kiến thức schema | **Có** |
| Thuộc tính SINGLE-VALUE, format | Có thể kiểm tra trước | **Có** |
| UID duy nhất trên toàn subtree | Có thể search hỗ trợ | Không mặc định; cần chính sách server |
| Quyền Add của bind identity | Có thể dự đoán | **ACL phía server quyết định** |
| Không có request khác tạo đồng thời | Không thể khẳng định bằng một lookup | Add tại server quyết định trùng DN |

**Kết luận quan trọng:** nếu pre-check đều PASS, vẫn cần xử lý ngoại lệ từ `LdapTemplate.bind`. Không nên coi validator là bằng chứng rằng mọi thao tác ghi sau đó chắc chắn thành công.

## 3. Kiểm tra DN và RDN trước khi tạo

DN mới trong ví dụ:

~~~text
uid=training-01,ou=people,dc=example,dc=org
|-------------| |--------| |---------------|
      RDN       OU cha       Hậu tố vùng tên
~~~

Giả sử `LdapContextSource` đã cấu hình:

~~~text
base = dc=example,dc=org
~~~

DN tương đối đưa vào `LdapTemplate` thường là:

~~~text
uid=training-01,ou=people
~~~

Không lặp lại `dc=example,dc=org` vào DN tương đối nếu base đã được đặt trong ContextSource.

### 3.1. Tránh nối DN từ chuỗi đầu vào

**Cách không an toàn:**

~~~java
String unsafeDn = "uid=" + inputUid + ",ou=people";
~~~

Một UID có dấu phẩy, dấu cộng, dấu bằng hoặc các ký tự DN đặc biệt có thể thay đổi cách chuỗi được diễn giải.

**Dùng bộ dựng DN có cấu trúc:**

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", inputUid)
        .build();
~~~

`LdapNameBuilder` xử lý cấu trúc và escaping RDN. Nó **không** thay validation nghiệp vụ: UID có thể được escape đúng nhưng vẫn bị từ chối do quy tắc tên của tổ chức.

### 3.2. Quy tắc UID là chính sách của từng tổ chức

Một ví dụ policy hợp lý trong hệ thống đào tạo:

~~~regex
^[a-z][a-z0-9._-]{2,31}$
~~~

Quy tắc này cho phép UID dài 3–32 ký tự ASCII, bắt đầu bằng chữ thường rồi gồm chữ thường, số, dấu chấm, dấu gạch dưới hoặc gạch ngang. Đây là **ví dụ ứng dụng**, không phải chuẩn bắt buộc cho mọi LDAP directory. Có hệ thống dùng Unicode, hệ thống dùng `cn` làm RDN, hoặc yêu cầu những ký tự khác.

Không tự động `trim()` hoặc chuyển chữ hoa thành chữ thường nếu quy trình không quy định rõ. Nếu có chuẩn hóa, phải thực hiện nhất quán **trước** khi tính DN, kiểm tra uniqueness và đặt thuộc tính.

### 3.3. RDN và thuộc tính phải nhất quán

Với DN `uid=training-01,...`, entry cần có thuộc tính `uid` phù hợp với RDN và naming rules của server. Không dùng một trường bên ngoài để tạo DN nhưng lại ghi giá trị UID khác.

Một số server từ chối entry nếu giá trị RDN không có mặt hoặc bị mâu thuẫn với thuộc tính được khai báo. Việc kiểm tra cùng một biến UID khi dựng DN và đặt attribute giúp phòng lỗi từ ứng dụng.

### 3.4. OU đích phải là giá trị đáng tin cậy

Nếu endpoint chỉ được phép thêm user dưới `ou=people`, hãy cố định hoặc chọn OU từ một **allowlist phía ứng dụng**. Không cho client gửi một chuỗi `baseDn` tùy ý để đặt entry vào những nhánh khác. Escaping DN đúng vẫn không có nghĩa vị trí tạo đó được phép về nghiệp vụ.

## 4. Kiểm tra objectClass và MUST/MAY trong schema

Với schema LDAP thường gặp, `inetOrgPerson` kế thừa:

~~~text
top
  |
person
  |
organizationalPerson
  |
inetOrgPerson
~~~

`person` yêu cầu `cn` và `sn`. `inetOrgPerson` thường cho phép `uid`, `mail` và `telephoneNumber`. Server có thể dùng schema mở rộng hoặc chính sách bổ sung, vì thế schema đang chạy là nguồn xác thực cuối cùng.

| Thuộc tính | Giá trị ví dụ | Ghi chú |
| --- | --- | --- |
| `objectClass` | top, person, organizationalPerson, inetOrgPerson | Thuộc tính đa trị; xác định cấu trúc entry |
| `cn` | Training User | Bắt buộc qua `person` |
| `sn` | User | Bắt buộc qua `person` |
| `uid` | training-01 | Dùng cho RDN và định danh theo policy |
| `mail` | training-01@example.org | Thường tùy chọn theo schema |
| `telephoneNumber` | Hai số điện thoại | Có thể có nhiều giá trị |
| `description` | training | Tùy chọn, có thể nhiều giá trị |

**MUST/MAY khác quy tắc API.** Một thuộc tính MAY theo schema vẫn có thể bắt buộc trong nghiệp vụ, ví dụ một hệ thống chỉ tạo hồ sơ khi có email doanh nghiệp. Khi đó service phải validate email, nhưng không nên nói rằng `mail` là MUST của mọi entry `inetOrgPerson`.

### 4.1. Đừng cho người dùng tự quyết định objectClass

**Nên cấu hình từ code tin cậy:**

~~~java
entry.setAttributeValues("objectClass", new String[] {
        "top", "person", "organizationalPerson", "inetOrgPerson"
});
~~~

**Không nên cho phép:**

~~~java
entry.setAttributeValues(
        "objectClass",
        clientProvidedObjectClasses
);
~~~

Cho client tùy ý chọn class có thể khiến entry sai schema hoặc chạm đến các thuộc tính/quyền không được sản phẩm dự kiến. Nếu có nhiều loại entry, nên ánh xạ một enum/loại hợp lệ sang tập object class đã được phê duyệt.

### 4.2. Không nhầm đa trị với chuỗi có dấu phẩy

**Sai nếu muốn hai giá trị LDAP:**

~~~java
entry.setAttributeValue("telephoneNumber",
        "+84 28 1111 2222, +84 28 3333 4444");
~~~

Đây chỉ là **một giá trị String**. Với thuộc tính cho phép nhiều giá trị, sử dụng:

~~~java
entry.setAttributeValues("telephoneNumber", new String[] {
        "+84 28 1111 2222",
        "+84 28 3333 4444"
});
~~~

Cần kiểm tra danh sách không có null, phần tử rỗng, quá dài, trùng theo policy, hoặc vượt số lượng mà API cho phép. Không coi thứ tự giá trị của attribute đa trị LDAP là thứ tự ưu tiên được bảo đảm.

### 4.3. Thuộc tính nhị phân và do server quản lý

Một số thuộc tính chứa `byte[]` (ảnh/chứng chỉ), không phải text. Các operational attributes như `entryUUID`, `createTimestamp` và `modifyTimestamp` thường được server quản lý, không nên ghi tùy ý lúc Add. Cần xác nhận kiểu dữ liệu, kích thước và quyền với schema cụ thể.

### 4.4. LDAP server vẫn là thẩm quyền schema

Validator Java có thể phản ánh một phần schema để đưa lỗi dễ hiểu, nhưng bản schema trên LDAP server có thể thay đổi hoặc khác giữa môi trường. Nếu cần đối chiếu schema, hãy dùng tài liệu quản trị hoặc cơ chế schema discovery (như `subschemaSubentry`) với quyền phù hợp. Không tự thay schema production chỉ để một request sai được chấp nhận.

## 5. Bean Validation cho dữ liệu đầu vào

Ví dụ Java 17 record với Jakarta Bean Validation, thích hợp trong ứng dụng Spring Boot hiện đại:

~~~java
import java.util.List;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreatePersonRequest(
        @NotBlank
        @Pattern(regexp = "^[a-z][a-z0-9._-]{2,31}$")
        String uid,

        @NotBlank
        @Size(max = 128)
        String commonName,

        @NotBlank
        @Size(max = 128)
        String surname,

        @Email
        @Size(max = 254)
        String email,

        @Size(max = 4)
        List<@NotBlank String> phoneNumbers
) {}
~~~

Những annotation này có ý nghĩa:

- `@NotBlank`: trường bắt buộc không null/rỗng/toàn khoảng trắng.
- `@Pattern`: UID tuân theo **policy minh họa**, không đại diện mọi LDAP server.
- `@Size`: giới hạn độ dài hoặc số phần tử theo hợp đồng API.
- `@Email`: hỗ trợ kiểm tra format cơ bản, **không chứng minh email tồn tại hoặc nhận được thư**; null được chấp nhận khi email tùy chọn.
- `List<@NotBlank String>`: phần tử phone không được rỗng, nhưng chưa chứng minh format số điện thoại đáp ứng yêu cầu một quốc gia.

**Annotation không tự chạy** khi record được khởi tạo. Ứng dụng phải có Bean Validation provider và gọi `Validator.validate(...)`, hoặc cấu hình method validation / `@Valid` tại Spring MVC đúng cách. Với các bản Spring cũ, package có thể là `javax.validation` thay vì `jakarta.validation`.

### 5.1. Quy tắc nhiều trường

Một số yêu cầu cần domain validation riêng:

- Email bắt buộc nếu account thuộc loại nhân viên nhưng tùy chọn với tài khoản thực tập.
- Không cho phép phoneNumbers trùng; nếu cần theo E.164, dùng validator định dạng chuyên biệt.
- UID có thể cần không nằm trong danh sách từ khóa dự trữ.
- Thuộc tính mở rộng nào được ghi phụ thuộc vào loại tài khoản đã được phê duyệt.
- Mọi thao tác cần được người gọi **ủy quyền**, không chỉ có DTO hợp lệ.

Không nên cố chứa mọi quy tắc trong một regex khó đọc; tách class validator và có test riêng.

### 5.2. Email và dữ liệu tùy chọn

Nếu email là optional, chọn chính sách nhất quán: dùng null để biểu diễn không được cung cấp, hoặc chuẩn hóa chuỗi rỗng thành null có chủ đích. Đừng tự ghi giá trị email rỗng vào LDAP và mong server xử lý như “không có thuộc tính”.

Với dữ liệu người dùng nhập, validate giá trị trước khi ghi. `DirContextAdapter.setAttributeValue` không phải công cụ xác thực email, phone, permission hoặc schema.

## 6. Tạo entry sau khi kiểm tra DTO

Sơ đồ xử lý tiêu chuẩn:

~~~text
HTTP / HR source
   |
   v
Kiểm tra authn/authz của người gọi
   |
   v
Bean Validation + domain validation
   |
   v
Chọn OU từ cấu hình/allowlist
   |
   v
LdapNameBuilder tạo DN tương đối
   |
   v
DirContextAdapter nhận objectClass và attributes
   |
   v
LdapTemplate.bind(entry) --> LDAP Add
   |                            |
   |                            +-- schema/MUST/MAY
   |                            +-- parent + DN uniqueness
   |                            +-- ACL/naming policy
   |
   +-- Thành công: readback nếu cần
   +-- Thất bại: phân loại lỗi, không ghi đè
~~~

### 6.1. Cấu hình ContextSource bằng Spring

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

~~~yaml
# application.yml: LDAP test; secrets từ môi trường
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Đây là nhóm property `app.ldap.*` **do ứng dụng tự định nghĩa**. Spring Boot còn có các thuộc tính `spring.ldap.*` khi dùng auto-configuration phù hợp. Chọn một cách cấu hình nhất quán, tránh có hai bean `ContextSource` không rõ bean nào được repository sử dụng.

### 6.2. Dùng Validator trực tiếp trước LDAP Add

~~~java
import java.util.List;
import java.util.Set;

import javax.naming.Name;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonProvisioningService {

    private final LdapTemplate ldapTemplate;
    private final Validator validator;

    public PersonProvisioningService(
            LdapTemplate ldapTemplate, Validator validator) {
        this.ldapTemplate = ldapTemplate;
        this.validator = validator;
    }

    public Name create(CreatePersonRequest request) {
        if (request == null) {
            throw new IllegalArgumentException(
                    "CreatePersonRequest is required");
        }

        Set<ConstraintViolation<CreatePersonRequest>> violations =
                validator.validate(request);
        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(violations);
        }

        if (request.email() != null
                && request.email().isBlank()) {
            throw new IllegalArgumentException(
                    "email must be null or non-blank");
        }

        List<String> phones = request.phoneNumbers() == null
                ? List.of()
                : request.phoneNumbers();

        if (Set.copyOf(phones).size() != phones.size()) {
            throw new IllegalArgumentException(
                    "duplicate phone numbers");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", request.uid())
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[] {
                "top", "person",
                "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", request.uid());
        entry.setAttributeValue("cn", request.commonName());
        entry.setAttributeValue("sn", request.surname());

        if (request.email() != null) {
            entry.setAttributeValue("mail", request.email());
        }
        if (!phones.isEmpty()) {
            entry.setAttributeValues(
                    "telephoneNumber",
                    phones.toArray(String[]::new));
        }

        ldapTemplate.bind(entry);
        return dn;
    }
}
~~~

Mã minh họa sử dụng Java hiện đại và cần Bean Validation provider, Spring LDAP cùng directory test hợp schema. Hàm `Validator.validate` chạy trước việc dựng entry và mở kết nối LDAP. Các phần tử null trong danh sách phone bị annotation `@NotBlank` của record kiểm tra khi provider hỗ trợ container element constraints.

`Set.copyOf(phones)` kiểm tra trùng theo Java equality, **không có nghĩa kết quả khớp mọi matching rule của LDAP server**. Nếu cần format số điện thoại chuẩn, bổ sung policy chuyên biệt. Việc service trả DN không làm entry được tạo trong bộ nhớ; **lời gọi `ldapTemplate.bind(entry)` mới gửi LDAP Add**.

Ứng dụng vẫn phải kiểm tra **quyền người gọi** và dữ liệu định danh nguồn bên ngoài service. Bản thân việc tạo record và gọi validator không tự là một authentication/authorization policy.

## 7. Kiểm tra parent OU đúng cách

Một LDAP Add tại:

~~~text
uid=training-01,ou=people,dc=example,dc=org
~~~

đòi hỏi entry cha `ou=people,dc=example,dc=org` tồn tại. LDAP Add **không tự tạo OU cha** khi thêm người dùng.

Nếu OU đã được triển khai cố định, không nhất thiết phải lookup parent trước mọi lần Add. Việc đó có thể tăng round trip mà không bảo đảm parent vẫn tồn tại tại thời điểm Add. Tuy nhiên, kiểm tra một lần trong cấu hình/health check có thể giúp phát hiện sai base.

Ví dụ kiểm tra entry cha có thể lookup được:

~~~java
import org.springframework.ldap.core.AttributesMapper;

Boolean parentVisible = ldapTemplate.lookup(
        "ou=people",
        (AttributesMapper<Boolean>) attrs -> Boolean.TRUE
);
~~~

Ví dụ giả định `ContextSource.base = dc=example,dc=org`. **Không thấy parent không luôn chứng minh nó không tồn tại**, vì ACL, sai credentials hoặc lỗi kết nối có thể che khuất. Server vẫn kiểm tra parent và quyền Add tại thời điểm tạo.

Đừng tự thêm chức năng tạo OU thiếu trong endpoint tạo người dùng nếu không có yêu cầu và phê duyệt quản trị. Cấu trúc OU, naming context và ACL thuộc phạm vi quản lý directory.

## 8. Trùng DN và trùng UID không phải cùng một ràng buộc

### 8.1. DN là vị trí duy nhất của entry

Nếu đã tồn tại:

~~~text
uid=training-01,ou=people,dc=example,dc=org
~~~

thì Add thêm một entry vào **đúng DN đó** thường bị từ chối với LDAP result code **68 — entryAlreadyExists**. Đây là nguyên tắc uniqueness của DN trong cùng vùng tên directory.

### 8.2. UID có thể trùng ở hai OU khác nhau

~~~text
uid=alex,ou=engineering,ou=people,dc=example,dc=org
uid=alex,ou=sales,ou=people,dc=example,dc=org
~~~

Hai entry có DN khác nhau. Nếu sản phẩm yêu cầu `uid` duy nhất **trên toàn subtree**, cần chính sách enforce uniqueness hoặc một bộ cấp phát định danh/điều phối đáng tin cậy. LDAP DN uniqueness tự nó **không đảm bảo uniqueness cho UID qua các OU**.

### 8.3. Search trước Add là pre-check hỗ trợ, không phải khóa

Một kiểm tra nghiệp vụ có thể sử dụng query builder:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery existingUidQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid")
        .where("uid").is(request.uid());

boolean uidSeen = !ldapTemplate.search(
        existingUidQuery,
        (org.springframework.ldap.core.AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("uid").get())
).isEmpty();
~~~

Builder escape **giá trị LDAP filter**, khác với escaping **DN/RDN**. Nhưng search vẫn chịu ảnh hưởng ACL, base/scope và replication. Nếu tài khoản không thấy một OU, kết quả “không có UID” không chứng minh UID chưa tồn tại.

### 8.4. Race condition giữa hai request

~~~text
Request A                         Request B
    |                                 |
    +-- Search chưa có UID            +-- Search chưa có UID
    |                                 |
    +-- Add DN mới                    |
    |                                 +-- Add cùng DN
    v                                 v
 Thành công                      Server báo trùng DN
~~~

Không có lời gọi `lookup` hoặc `search` trước Add nào loại bỏ race condition này. Server quyết định kết quả khi nhận từng Add. Do đó **luôn xử lý lỗi duplicate**, kể cả khi pre-check đều PASS.

### 8.5. Không tự chuyển từ Add lỗi sang Modify

Nếu Add trả conflict, không tự chuyển sang `modifyAttributes(...)` để ghi đè entry cũ. Entry có thể được tạo bởi người dùng hoặc request khác. Một API tạo mới cần trả conflict hoặc dùng **idempotency policy được định nghĩa trước**, có khả năng xác minh đúng owner và trạng thái entry.

Pre-validation giúp có thông báo lỗi sớm; nó không được dùng làm lý do bỏ qua kiểm tra conflict từ LDAP server.

## 9. Bảo mật và quyền truy cập trước khi tạo

### 9.1. Người gọi hợp lệ chưa chắc được phép Add

Endpoint tạo người dùng phải xác minh danh tính và **ủy quyền người gọi** tại tầng ứng dụng. Có JSON hợp lệ không đồng nghĩa người đó được phép cấp phát tài khoản.

Tài khoản bind của service cũng phải theo nguyên tắc least privilege:

| Identity | Công việc | Quyền nên hạn chế |
| --- | --- | --- |
| Reader | Search/lookup | Không Add/Delete/sửa schema |
| Directory editor/provisioner | Thêm entry ở OU đã phê duyệt | Không quyền quản trị toàn directory |
| Admin | Vận hành schema/ACL và cấu trúc thư mục | Không dùng làm credential mặc định của API |

`ContextSource.getReadWriteContext()` **không tự cấp quyền ghi**. LDAP server dựa vào bind identity và ACL để chấp nhận hoặc từ chối Add.

### 9.2. TLS và secrets

- **LDAPS** dùng TLS từ đầu; xác minh chuỗi chứng chỉ và hostname.
- Với `ldap://` và **StartTLS**, phải thực sự nâng cấp TLS **trước** khi gửi simple bind password và dữ liệu nhạy cảm; URL `ldap://` không tự bật StartTLS.
- Không tắt xác minh chứng chỉ để “làm cho môi trường test hoạt động”.
- Mật khẩu dịch vụ từ secret manager hoặc biến môi trường bảo vệ; không hard-code hay ghi log.
- DN và thuộc tính có thể chứa dữ liệu cá nhân; chỉ log những trường được phép và giảm thiểu chi tiết diagnostic.

### 9.3. Allowlist thuộc tính khi xây adapter

**Không nên dùng map attribute tùy ý từ client:**

~~~java
// Rủi ro nếu tên thuộc tính đến từ input chưa kiểm soát:
entry.setAttributeValue(clientAttributeName, clientValue);
~~~

Client có thể cố tạo các thuộc tính nhạy cảm hoặc không được schema cho phép. **Nên map từng trường đã phê duyệt** như `uid`, `cn`, `sn`, `mail` và `telephoneNumber` theo DTO và quyền nghiệp vụ.

Validation cho tên attribute không chỉ là escaping: **tên thuộc tính phải thuộc allowlist**, còn giá trị phải đúng định dạng/kiểu/số lượng. 


## 10. Phân loại lỗi LDAP: validator không thay thế phản hồi của server

Ngay cả khi DTO và adapter hợp lệ tại client, server vẫn có thể từ chối LDAP Add. Các mã thường gặp gồm:

| LDAP result | Tên phổ biến | Nguyên nhân cần điều tra |
| --- | --- | --- |
| **68** | `entryAlreadyExists` | DN đã có entry |
| **32** | `noSuchObject` | Parent/base DN không tồn tại hoặc không được thấy |
| **34** | `invalidDNSyntax` | DN không hợp cú pháp |
| **65** | `objectClassViolation` | Thiếu thuộc tính MUST, object class sai hoặc có thuộc tính không được phép |
| **17** | `undefinedAttributeType` | Attribute type chưa có trong schema |
| **21** | `invalidAttributeSyntax` | Giá trị không hợp syntax của attribute type |
| **19** | `constraintViolation` | Vi phạm SINGLE-VALUE hoặc ràng buộc khác |
| **50** | `insufficientAccessRights` | Tài khoản dịch vụ không được tạo entry trong OU |
| **53** | `unwillingToPerform` | Server từ chối theo chính sách |
| Lỗi kết nối/TLS/bind | Tùy provider | Endpoint, truststore, credentials hoặc mạng không phù hợp |

Mã và diagnostic có thể khác theo sản phẩm LDAP và chính sách che dữ liệu. Spring LDAP chuyển nhiều ngoại lệ JNDI sang hệ ngoại lệ của framework; ứng dụng nên phân loại **theo ý nghĩa lỗi**, không dựa hoàn toàn vào một chuỗi thông báo.

### 10.1. Đầu vào sai, conflict, ACL và lỗi hạ tầng

Các nhóm phản hồi API có thể tách như sau:

- **Validation error:** UID, tên hoặc số điện thoại sai hợp đồng. Đưa danh sách trường cần sửa cho người gọi; không cần gửi LDAP Add.
- **Conflict:** DN tồn tại hoặc quy tắc định danh nghiệp vụ bị vi phạm. Không ghi đè entry không rõ owner.
- **Lỗi schema/quyền:** cần kiểm tra cấu hình object class, thuộc tính và bind identity; không tự cấp thêm quyền.
- **Lỗi TLS/bind/timeout:** phản ánh sự cố kết nối/hạ tầng, không được báo “không tìm thấy người dùng”.

Việc ánh xạ sang HTTP 400, 409, 503 hoặc mã khác tùy thiết kế API. Điểm cần giữ là **không gộp tất cả thành một lỗi validation** và không đưa LDAP diagnostic chứa DN/thuộc tính nhạy cảm ra API công khai.

### 10.2. Một response bị mất không chứng minh Add thất bại

~~~text
Client                             LDAP server
   |                                   |
   +----------- Add(entry) ----------->|
   |                                   +-- Có thể đã tạo thành công
   X <--------- Response --------------|
 Kết nối đứt trước khi client nhận
~~~

Nếu mất kết nối sau khi gửi yêu cầu, client **không biết chắc** server đã tạo entry hay chưa. Trước khi tự retry, hãy **tra cứu lại DN** bằng danh tính được phép và xác minh nội dung, chính sách ownership và request identifier nếu hệ thống có lưu.

Retry mù quáng có thể tạo lỗi duplicate; việc nhận code 68 ở lần thử lại không chứng minh lần đầu không thành công. Một quy trình idempotent cần được thiết kế rõ thay vì tự giả định.

### 10.3. LDAP Add không tạo transaction xuyên nhiều hệ thống

Tạo entry LDAP, thêm người dùng vào một nhóm, ghi bản ghi SQL và gửi email chào mừng là **nhiều thao tác riêng**. Nếu bước hai thất bại, Spring LDAP không tự rollback bước một hoặc những side effect khác.

Với một luồng provisioning nhiều bước, cần mô tả thứ tự, trạng thái trung gian, retry, bù trừ và giám sát. Không nên dùng pre-validation làm lời hứa rằng mọi bước chắc chắn cùng thành công.

## 11. Đối chiếu validation bằng LDIF và ldapadd

Một cách xác nhận giả định về schema là dùng **LDAP directory thử nghiệm**, chuẩn bị LDIF và gửi Add bằng công cụ LDAP.

### 11.1. Entry hợp lệ minh họa

~~~ldif
dn: uid=training-01,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: training-01
cn: Training User
sn: User
mail: training-01@example.org
telephoneNumber: +84 28 1111 2222
telephoneNumber: +84 28 3333 4444
~~~

Lưu thành `training-01.ldif` rồi chạy **một lần** nếu DN chưa được Spring tạo:

~~~bash
ldapadd -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-editor,ou=system,dc=example,dc=org" -W \
  -f training-01.ldif
~~~

`-H` chỉ endpoint LDAPS, `-D` là bind DN, `-W` nhập mật khẩu tương tác và `-f` trỏ tới file LDIF. Đừng để mật khẩu trong lịch sử shell hoặc commit file secrets.

### 11.2. Entry sai schema minh họa

Nếu bỏ thuộc tính `sn` bắt buộc của `person`:

~~~ldif
dn: uid=bad-example,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bad-example
cn: Bad Example
~~~

server LDAP tuân schema thông thường sẽ từ chối Add vì thiếu thuộc tính MUST. Chỉ dùng DN dữ liệu giả trong môi trường test, không thử gây lỗi trên tài khoản thật.

Một trường hợp khác: DN là `uid=training-01,...` nhưng attribute `uid` bị đặt thành `different`; đây là vi phạm tính nhất quán naming mà application validator cần ngăn trước khi gửi.

### 11.3. Kiểm tra kết quả bằng ldapsearch

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "uid=training-01,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" \
  dn objectClass uid cn sn mail telephoneNumber
~~~

Đây là một **base search** cho chính entry tại DN đích. Nếu dùng `ContextSource.base = dc=example,dc=org`, Java truyền DN tương đối `uid=training-01,ou=people`, còn `ldapsearch -b` nhận DN đầy đủ. Đừng lẫn hai cách biểu diễn.

Nếu không thấy `mail` dù Add trả thành công, cần xét ACL và returning attributes. Việc không nhìn thấy một thuộc tính **không tự chứng minh** nó không tồn tại trên server.

## 12. Đọc lại trạng thái bằng LdapTemplate

Sau khi gọi `bind`, service có thể lookup entry để xác minh một vài thuộc tính:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

String createdUid = ldapTemplate.lookup(
        dn,
        (AttributesMapper<String>) attrs -> {
            Attribute uid = attrs.get("uid");
            return uid == null ? null : String.valueOf(uid.get());
        }
);
~~~

Biến `dn` ở đây là DN tương đối đã dùng để Add; `ldapTemplate` là bean đã cấu hình. Nếu đọc được thuộc tính UID, có thể đối chiếu nó với request và DN được dựng.

Với thuộc tính đa trị như `telephoneNumber` hoặc `objectClass`, phải đọc toàn bộ bằng `Attribute.getAll()`, đóng `NamingEnumeration` đúng cách và so sánh **tập giá trị** thay vì dựa vào thứ tự.

### 12.1. Cần đọc lại khi nào?

Readback hữu ích khi:

- Cần xác minh các giá trị được server chuẩn hóa, bổ sung hoặc biến đổi.
- Gặp lỗi mạng không chắc request đã được áp dụng hay chưa.
- Muốn xác nhận trạng thái của một batch hoặc workflow provisioning.
- Test schema, ACL hoặc dữ liệu đa trị.

Tuy nhiên, một lookup thất bại có thể do quyền đọc bị hạn chế hoặc hạ tầng; không nên tự kết luận Add thất bại rồi xóa hoặc gửi lại một yêu cầu khác khi chưa xác minh nguyên nhân.

## 13. Kiểm thử đơn vị các quy tắc đầu vào

Unit test giúp phát hiện lỗi nhanh mà không cần mở kết nối LDAP. Trọng tâm là policy UID, thuộc tính bắt buộc, chiều dài, danh sách đa trị và dựng DN.

### 13.1. Test Jakarta Bean Validation

~~~java
import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CreatePersonRequestTest {

    private final Validator validator =
            Validation.buildDefaultValidatorFactory()
                    .getValidator();

    @Test
    void invalidUidAndMissingSurnameAreRejected() {
        CreatePersonRequest request = new CreatePersonRequest(
                "bad,uid",
                "Training User",
                "",
                "training@example.org",
                List.of("+84 28 1111 2222")
        );

        Set<ConstraintViolation<CreatePersonRequest>> violations =
                validator.validate(request);

        assertTrue(violations.stream().anyMatch(v ->
                v.getPropertyPath().toString().equals("uid")));

        assertTrue(violations.stream().anyMatch(v ->
                v.getPropertyPath().toString().equals("surname")));
    }
}
~~~

Đây là code minh họa cho JUnit 5/Bean Validation có provider phù hợp, **không** yêu cầu LDAP server. Nên thêm test giá trị null, UID quá dài, email không đúng, danh sách điện thoại quá nhiều và phần tử phone rỗng.

### 13.2. Test adapter được dựng đúng

~~~java
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

class EntryConstructionTest {

    @Test
    void rdnAndAttributesAreConsistent() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "training-01")
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[] {
                "top", "person",
                "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", "training-01");
        entry.setAttributeValue("cn", "Training User");
        entry.setAttributeValue("sn", "User");

        assertEquals("training-01",
                entry.getStringAttribute("uid"));
        assertEquals("Training User",
                entry.getStringAttribute("cn"));
        assertEquals(4,
                entry.getStringAttributes("objectClass").length);
    }
}
~~~

Test này chỉ kiểm tra đối tượng Java: nó **không thể khẳng định** LDAP server chấp nhận DN, schema, ACL hoặc TLS. Tách các ca test client và server sẽ giúp báo cáo chất lượng chính xác hơn.

### 13.3. Chứng minh dữ liệu sai không gửi Add

Khi test service, sử dụng mock `LdapTemplate` và validator hoặc fixture phù hợp để xác minh:

- Với UID sai policy, service từ chối trước khi gọi `bind`.
- Với commonName/surname rỗng, cũng không gọi `bind`.
- Với nhiều phoneNumbers trùng, logic domain từ chối trước Add.
- Với dữ liệu hợp lệ, adapter được dựng từ một allowlist thuộc tính.

Một mock chỉ chứng minh sự tương tác Java mong muốn, không chứng minh server sẽ cho phép tạo entry. Đó là mục đích của kiểm thử tích hợp tiếp theo.

## 14. Kiểm thử tích hợp với directory thử nghiệm

Một LDAP server test với schema/ACL tương tự môi trường mục tiêu là cần thiết vì JNDI/provider và server mới xác định các quy tắc thật.

### 14.1. Ma trận kiểm thử

| Ca kiểm thử | Tiền điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| Add người dùng hợp lệ | Parent có sẵn, DN mới, editor có ACL | Tạo thành công, lookup đúng |
| DTO thiếu `uid` | Null/rỗng | Validation từ chối trước LDAP |
| UID có dấu phẩy trái policy | `bad,uid` | Java validator từ chối |
| Thiếu `sn` trong LDIF test | `person` cần `sn` | Schema server từ chối |
| Trùng DN | Entry đã tồn tại | LDAP code 68/conflict |
| Trùng UID hai OU | DN khác nhau | Chỉ bị chặn nếu có policy uniqueness phù hợp |
| Parent OU không tồn tại | `ou=missing` | LDAP Add thất bại |
| ObjectClass sai | Thiếu class hoặc class không cho phép | Server từ chối |
| Attribute chưa định nghĩa | Tên trường không có schema | Server từ chối |
| Thuộc tính SINGLE-VALUE có hai giá trị | Vi phạm schema | Server từ chối |
| Reader cố Add | Bind DN không có ACL ghi | LDAP từ chối; entry không xuất hiện |
| Hai request Add đồng thời | Cùng DN | Xung đột được xử lý; không ghi đè |
| Sai chứng chỉ TLS | Truststore hoặc hostname không hợp lệ | Kết nối thất bại an toàn |
| Mất mạng sau gửi Add | Test mô phỏng mất response | Phải đọc lại trước retry |
| Hai phoneNumbers | Schema cho phép đa trị | Đọc được đủ hai giá trị, không phụ thuộc thứ tự |

Các mã lỗi cụ thể phụ thuộc LDAP server. Test nên so sánh **trạng thái cuối thực tế** của entry, không chỉ bắt một exception bất kỳ.

### 14.2. Khung integration test JUnit

Giả sử dự án có `LdapTemplate` trỏ tới LDAP server **thử nghiệm**, parent `ou=people` tồn tại và fixture cung cấp quyền Add:

~~~java
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CreateEntryIntegrationTest {
    private final LdapTemplate template;

    // Spring Test/fixture phải cung cấp template này.
    CreateEntryIntegrationTest(LdapTemplate template) {
        this.template = template;
    }

    @Test
    void createsAndReadsTrainingEntry() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "training-integration-01")
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[] {
                "top", "person",
                "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", "training-integration-01");
        entry.setAttributeValue("cn", "Integration User");
        entry.setAttributeValue("sn", "User");

        template.bind(entry);

        String value = template.lookup(
                dn,
                (AttributesMapper<String>) attrs ->
                        String.valueOf(attrs.get("uid").get())
        );

        assertEquals("training-integration-01", value);
    }
}
~~~

Đây là **khung minh họa**: cần cấu hình Spring Test/LDAP server, inject template, tạo dữ liệu và dọn dẹp. Dùng DN test riêng cho mỗi ca, tránh hai test chạy cùng DN song song và **chỉ xóa entry do chính test tạo** khi đã xác minh sở hữu. Không chuyển logic xóa thử nghiệm sang thư mục production.

## 15. Quy trình triển khai và giám sát trong production

Trước khi bật chức năng tạo entry, đội vận hành nên chốt các quyết định sau:

1. **Cấu trúc DN:** OU nào được dùng, attribute nào làm RDN, quy tắc chuẩn hóa UID nào được phép.
2. **Schema contract:** object classes, MUST/MAY, tập attribute được hỗ trợ, giới hạn đa trị và định dạng dữ liệu.
3. **Business contract:** trường bắt buộc, giới hạn đầu vào, uniqueness, ownership và hành vi khi trùng.
4. **Authorization:** danh tính người gọi và tài khoản bind có quyền Add đúng nhánh.
5. **TLS/secrets:** chứng chỉ tin cậy, hostname được xác minh, mật khẩu từ nguồn bảo mật.
6. **Timeout/pooling:** timeout kết nối/đọc phù hợp; pooling không được lẫn bind identity hoặc trạng thái TLS.
7. **Lỗi và retry:** phân biệt validation, schema, ACL, duplicate, lỗi hạ tầng và trạng thái không chắc sau khi gửi.
8. **Kiểm toán:** correlation ID, loại thao tác, mã kết quả và DN đã lược bỏ dữ liệu nhạy cảm.
9. **Kiểm thử:** directory test, ACL hạn chế, trường hợp đồng thời, timeout và cleanup.

Một health check chỉ cần kiểm tra một thao tác LDAP đọc nhẹ phù hợp. **Không tạo một entry thật trong mỗi lần health check**, vì sẽ làm bẩn directory và tiêu hao tài nguyên.

### 15.1. Pooling không thay thế validation

Pool có thể giảm chi phí thiết lập kết nối nhưng **không kiểm tra schema, UID, ACL hoặc duplicate**. Khi sử dụng nhiều bind identity hay StartTLS, phải xác minh khả năng tương thích và cách trả context. Với `LdapTemplate`, framework quản lý vòng đời context cho thao tác thông thường; khi lấy `DirContext` trực tiếp, người gọi phải đóng đúng cách.

### 15.2. Kiểm soát dữ liệu cá nhân trong log

Không log nguyên request JSON nếu nó chứa thông tin cá nhân, credentials hoặc các trường mở rộng nhạy cảm. Với lỗi validation, chỉ hiển thị tên trường và lý do an toàn cho người gọi. Với lỗi LDAP, dùng mã lỗi, loại thao tác và correlation ID để điều tra, đồng thời hạn chế lộ DN và diagnostic thô.

## 16. Bài thực hành và tự đánh giá

**Bối cảnh:** tạo tài khoản `training-01` trong `ou=people`, schema `inetOrgPerson`, email tùy chọn và tối đa ba số điện thoại.

### 16.1. Thực hành từng bước

1. Chuẩn bị LDAP directory test, OU cha có sẵn và editor identity chỉ có quyền Add trong OU này.
2. Cấu hình `LdapContextSource` với LDAPS đã xác minh chứng chỉ, base DN và credentials từ nguồn an toàn.
3. Viết DTO dùng Bean Validation cho UID, commonName, surname, email và phoneNumbers.
4. Xác định đâu là quy tắc API, đâu là yêu cầu MUST/MAY của schema.
5. Dùng `LdapNameBuilder` tạo DN tương đối; giải thích vì sao không nối DN từ UID trực tiếp.
6. Dùng `DirContextAdapter` gắn object classes cố định, UID, cn, sn và các thuộc tính tùy chọn đã qua validation.
7. Gọi `LdapTemplate.bind(entry)` một lần; lookup lại và so sánh giá trị sau tạo.
8. Thử UID rỗng, quá dài, chứa dấu phẩy và hai số điện thoại trùng; xác nhận không gửi Add cho dữ liệu sai.
9. Thử Add cùng DN lần hai, kiểm tra conflict và không ghi đè entry cũ.
10. Tạo hai entry với cùng UID ở OU khác nhau để đánh giá uniqueness theo policy.
11. Thử thiếu sn trong LDIF, parent DN không tồn tại và reader identity thiếu quyền; phân loại lỗi.
12. Thực hiện hai request Add song song, xác minh pre-check không thay thế kiểm tra duplicate của server.
13. Mô phỏng mất response sau khi gửi Add trong test; đọc lại trạng thái trước retry.
14. Chỉ dọn dữ liệu do chính bài thực hành tạo và kiểm tra log không chứa secrets.

### 16.2. Câu hỏi tự kiểm tra

1. Vì sao Bean Validation PASS vẫn chưa đủ để đảm bảo LDAP Add sẽ thành công?
2. `LdapTemplate.bind(context)` khác LDAP Bind xác thực ở điểm nào?
3. Với ContextSource base `dc=example,dc=org`, DN tương đối nào tạo user ở `ou=people`?
4. Vì sao `LdapNameBuilder` không thay được validation UID?
5. Thuộc tính nào là MUST của `person` trong chuỗi kế thừa `inetOrgPerson`?
6. Tại sao `mail` có thể optional theo schema nhưng bắt buộc theo nghiệp vụ?
7. Một chuỗi hai số điện thoại phân cách dấu phẩy có tương đương hai LDAP attribute values không?
8. Vì sao ứng dụng không nên cho client chọn objectClass hoặc OU tùy ý?
9. Khác biệt giữa duplicate DN và duplicate UID xuyên hai OU là gì?
10. Vì sao search trước Add không phòng được race condition?
11. Khi Add timeout sau khi gửi, tại sao cần đọc lại entry trước khi retry?
12. Vì sao unit test adapter không chứng minh schema/ACL server hoạt động đúng?
13. Nếu parent OU không tồn tại, Add có tự tạo OU không?
14. Vì sao không được tự chuyển lỗi duplicate sang Modify ghi đè entry có sẵn?
15. TLS, bind identity và logging ảnh hưởng an toàn của thao tác tạo thế nào?

## 17. Tổng kết

**Kiểm tra dữ liệu trước khi tạo entry** trong Spring LDAP là quy trình từ **ủy quyền người gọi, validate DTO, dựng DN/RDN an toàn, xác định objectClass/attributes hợp schema đến gửi LDAP Add bằng `LdapTemplate.bind(DirContextAdapter)`**. Client giúp phát hiện lỗi sớm nhưng **LDAP server vẫn phán quyết cuối cùng** về parent, DN trùng, schema, ACL và trạng thái đồng thời. Không coi pre-check uniqueness là transaction, không tự cho client chọn OU/objectClass, không ghi đè entry khi bị conflict và không retry mù quáng sau khi mất response. Kết hợp quyền tối thiểu, LDAPS/StartTLS được xác minh, chính sách dữ liệu rõ ràng, giám sát và kiểm thử tích hợp sẽ giúp tính năng tạo LDAP entry chính xác, an toàn và dễ vận hành.
