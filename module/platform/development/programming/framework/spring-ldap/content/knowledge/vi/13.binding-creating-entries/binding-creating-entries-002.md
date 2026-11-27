# Bind entry bằng Attributes

Trong LDAP, **tạo một entry mới** thường được gọi là *binding* trong API Java Naming and Directory Interface (JNDI). Với **Spring LDAP**, một cách tạo entry trực tiếp và dễ kiểm soát là dựng đối tượng `javax.naming.directory.Attributes`, xác định Distinguished Name (DN) của entry, rồi gọi:

```java
ldapTemplate.bind(dn, null, attributes);
```

Lời gọi này thêm **một entry mới** vào Directory Information Tree (DIT), chứ không phải thao tác **bind để xác thực mật khẩu**. Sự khác nhau rất quan trọng: người học có thể đang viết đúng phương thức Java nhưng hiểu sai chức năng, tạo DN thiếu parent, quên các thuộc tính bắt buộc của schema, hoặc tạo entry bằng tài khoản không có quyền ghi.

Bài thuộc chương **Bind và tạo entry** của mô-đun **SPRING_LDAP**. Chúng ta sẽ tập trung vào cách sử dụng `BasicAttributes`, `BasicAttribute` và `LdapTemplate.bind(Name, Object, Attributes)` trong ứng dụng Spring, liên hệ với `ContextSource`, DN, schema, kiểm soát lỗi và kiểm thử truy cập thư mục an toàn. Khi cần, bài đối chiếu cách tạo entry bằng `DirContextAdapter`, `LdapClient` và ODM để người học biết lựa chọn phù hợp.

**Sau bài học, bạn có thể:**

- Phân biệt *LDAP Add / tạo entry* với *LDAP bind / xác thực tài khoản*.
- Dựng DN tương đối với `ContextSource.base` bằng `LdapNameBuilder`, có escaping đúng cho giá trị RDN.
- Dựng tập `Attributes` với `BasicAttributes(true)`, `BasicAttribute` và đủ `objectClass`, thuộc tính bắt buộc.
- Tạo người dùng và nhóm thử nghiệm bằng `LdapTemplate.bind(dn, null, attributes)`.
- Phân biệt thêm entry mới với cập nhật bằng `modifyAttributes`, ghi đè bằng `rebind` và di chuyển bằng `rename`.
- Xử lý lỗi DN trùng, parent không tồn tại, thiếu quyền, vi phạm schema và kết nối thất bại.
- Viết unit test cho việc tạo DN/Attributes, integration test cho việc tạo entry thực sự, và tránh các lỗi retry khi trạng thái ghi chưa chắc chắn.

## 1. Tạo entry nghĩa là gì?

Một LDAP directory là cây những entry có DN duy nhất. Ví dụ:

```text
dc=example,dc=org
├── ou=People
│   ├── uid=an
│   └── uid=binh
├── ou=Groups
│   └── cn=Engineering
└── ou=ServiceAccounts
    └── cn=app-writer
```

Nếu ứng dụng cần thêm một người dùng mới `uid=chi`, entry đích sẽ có DN đầy đủ:

```text
uid=chi,ou=People,dc=example,dc=org
```

Ví dụ nội dung entry theo LDIF:

```ldif
dn: uid=chi,ou=People,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: chi
cn: Chi Nguyen
sn: Nguyen
givenName: Chi
mail: chi@example.org
```

Những điều cần bảo đảm:

1. **Parent tồn tại:** `ou=People,dc=example,dc=org` đã được tạo.
2. **DN chưa bị chiếm:** không có entry khác tại `uid=chi,ou=People,...`.
3. **Object classes hợp lệ:** server nhận các `objectClass` phù hợp schema.
4. **Thuộc tính bắt buộc được cung cấp:** với `person`, ví dụ `cn` và `sn` là các thuộc tính bắt buộc theo schema chuẩn.
5. **Giá trị RDN có trong entry:** nếu RDN là `uid=chi` thì entry phải có giá trị phù hợp của `uid`.
6. **Principal có quyền tạo:** account bind được phép thêm entry trong nhánh `ou=People`.
7. **Kết nối an toàn:** LDAPS hoặc StartTLS có xác minh certificate/hostname khi truyền dữ liệu và credentials.

**Tạo entry không phải sửa một entry đã tồn tại.** Nếu DN đã được sử dụng, thao tác Add thường thất bại với `entryAlreadyExists` ở LDAP protocol và exception tương ứng ở Spring LDAP.

## 2. Hai nghĩa khác nhau của từ “bind”

Từ *bind* xuất hiện với hai ý nghĩa:

| Ngữ cảnh | Ý nghĩa | API hoặc thao tác |
| --- | --- | --- |
| **LDAP BindRequest** | Xác thực/kết hợp danh tính với kết nối LDAP | LDAP simple bind, SASL bind; `ContextSource`, `LdapTemplate.authenticate(...)` |
| **JNDI Context.bind** | Liên kết object/attributes với một tên; với LDAP provider là tạo entry | `DirContext.bind(...)`, `LdapTemplate.bind(dn, obj, attrs)` |
| **Spring LDAP bind entry** | Tạo entry mới từ DN và dữ liệu | `LdapTemplate.bind(dn, null, attributes)` |

Ví dụ:

```java
// Tạo entry, không xác thực một người dùng:
ldapTemplate.bind(dn, null, attrs);
```

Khác với:

```java
// Ví dụ ý tưởng: xác thực password của một người dùng.
boolean authenticated = ldapTemplate.authenticate(
    "ou=People",
    "(uid=chi)",
    suppliedPassword
);
```

Đoạn `authenticate(...)` minh họa một overload Spring LDAP thường dùng; khi xử lý đăng nhập thật cần bảo vệ password, kiểm tra phạm vi filter, chống enumeration và lựa chọn phương thức xác thực phù hợp.

**Không nhầm thao tác thêm người dùng với việc cấp quyền đăng nhập.** Tạo một entry `inetOrgPerson` không tự bảo đảm account đó có mật khẩu, trạng thái được phép đăng nhập hoặc được ứng dụng ủy quyền.

## 3. API `LdapTemplate.bind(...)`

JavaDoc Spring LDAP công bố các overload tạo entry:

```java
void bind(Name dn, Object obj, Attributes attributes);
void bind(String dn, Object obj, Attributes attributes);
void bind(DirContextOperations ctx);
```

Trong phiên bản có chú thích nullability, hai tham số `obj` và `attributes` có thể là `null` **nhưng không được đồng thời là `null`**. Với bài này, chúng ta dùng:

```java
ldapTemplate.bind(relativeDn, null, attributes);
```

| Tham số | Cách dùng trong bài | Vai trò |
| --- | --- | --- |
| `dn` | `Name` hoặc `String` mô tả DN tương đối | Vị trí entry cần thêm |
| `obj` | `null` | Không cung cấp Java object/DirContext riêng |
| `attributes` | `BasicAttributes` | Thuộc tính tạo entry, bao gồm objectClass và trường bắt buộc |

### 3.1. Vì sao `obj` là `null`?

JNDI `DirContext.bind(Name, Object, Attributes)` cho phép cung cấp một object và một tập attribute. Với LDAP entry thông thường, **Attributes đủ mô tả dữ liệu để tạo**, nên có thể truyền `null` vào `obj`.

Ngược lại, cách gọi này không có ý nghĩa:

```java
// Không hợp lệ theo contract bind: obj và attrs cùng null.
ldapTemplate.bind(relativeDn, null, null);
```

Nếu muốn dùng một object như `DirContextAdapter`, có overload `bind(DirContextOperations)` hoặc các API `LdapClient` tương ứng. Đừng trộn hai cách nếu không cần.

### 3.2. `bind` có trả entry đã tạo không?

`LdapTemplate.bind(...)` trả `void`. Nếu server trả kết quả Add thành công, lời gọi hoàn tất không có exception. Khi cần xác nhận nội dung, gọi `lookup` hoặc `search` trong bước tiếp theo.

Trong môi trường replication nhiều server, việc đọc từ một replica khác **ngay sau khi ghi** có thể thấy trạng thái cũ; cần chọn endpoint/chiến lược kiểm chứng phù hợp với yêu cầu nhất quán.

## 4. Dựng `Attributes` bằng JNDI

JNDI dùng:

```java
javax.naming.directory.Attributes
javax.naming.directory.Attribute
javax.naming.directory.BasicAttributes
javax.naming.directory.BasicAttribute
```

- `Attributes` là tập các loại thuộc tính của một entry.
- `Attribute` chứa một loại thuộc tính và các giá trị.
- `BasicAttributes` là một triển khai phổ biến của `Attributes`.
- `BasicAttribute` là một triển khai phổ biến của `Attribute`.

### 4.1. Ví dụ tạo tập attribute cho `inetOrgPerson`

```java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

public static Attributes newPersonAttributes() {
    // true: tra cứu tên attribute ID không phân biệt hoa/thường.
    Attributes attrs = new BasicAttributes(true);

    BasicAttribute objectClasses = new BasicAttribute("objectClass");
    objectClasses.add("top");
    objectClasses.add("person");
    objectClasses.add("organizationalPerson");
    objectClasses.add("inetOrgPerson");

    attrs.put(objectClasses);
    attrs.put("uid", "chi");
    attrs.put("cn", "Chi Nguyen");
    attrs.put("sn", "Nguyen");
    attrs.put("givenName", "Chi");
    attrs.put("mail", "chi@example.org");

    return attrs;
}
```

Các dòng:

```java
attrs.put("uid", "chi");
attrs.put("cn", "Chi Nguyen");
```

tạo/đặt một `Attribute` cho mỗi tên tương ứng. Còn `BasicAttribute("objectClass")` cho phép thêm nhiều giá trị `top`, `person`, `organizationalPerson`, `inetOrgPerson` trước khi đưa cả attribute vào `attrs`.

**Đừng gọi nhiều lần `attrs.put("objectClass", value)` với ý định thêm nhiều objectClass.** Overload `put(String id, Object value)` có hành vi **đặt lại attribute** tương ứng với giá trị mới, không phải thêm một phần tử vào attribute cũ. Dùng một `BasicAttribute` rồi gọi `add(...)` cho các giá trị.

### 4.2. Tại sao nên dùng `BasicAttributes(true)`?

JNDI `BasicAttributes` có constructor nhận `boolean ignoreCase`:

```java
Attributes attrs = new BasicAttributes(true);
```

`true` cho phép tra cứu **ID của attribute** theo cách không phân biệt chữ hoa/thường trong container JNDI. Ví dụ `attrs.get("CN")` và `attrs.get("cn")` có thể tìm cùng attribute.

Điều này **không** có nghĩa mọi giá trị LDAP trở thành không phân biệt chữ hoa/thường. Matching rule của `uid`, `cn`, DN hoặc attribute tùy chỉnh do **schema của LDAP server** quy định.

### 4.3. Thuộc tính nhiều giá trị

Nếu ứng dụng được phép lưu nhiều địa chỉ email, có thể dùng:

```java
BasicAttribute emails = new BasicAttribute("mail");
emails.add("chi@example.org");
emails.add("chi.work@example.net");
attrs.put(emails);
```

LDAP attribute đa trị thường có ngữ nghĩa **tập giá trị**, không nên dựa vào thứ tự mà code gọi `add` để xác định email chính.

Một số schema hoặc chính sách ứng dụng hạn chế `mail` chỉ có một giá trị. Phải xác nhận schema/validation thực tế trước khi thêm nhiều giá trị.

### 4.4. Attribute nhị phân không phải chuỗi

Một số attribute chứa dữ liệu nhị phân như `jpegPhoto` hoặc chứng chỉ. Nếu server/schema cho phép, giá trị có thể là `byte[]` chứ không phải `String`.

Không tự chuyển `byte[]` bằng `String.valueOf(...)` rồi gửi LDAP, vì kết quả có thể không mang nội dung nhị phân. Với dữ liệu nhạy cảm, phải giới hạn kích thước, quyền đọc/ghi, logging và cơ chế truyền dữ liệu phù hợp.

## 5. DN mới và `ContextSource.base`

Giả sử Spring LDAP đã cấu hình:

```java
contextSource.setBase("dc=example,dc=org");
```

Các lời gọi `LdapTemplate` thường dùng DN **tương đối với base** đó:

| DN cung cấp cho template | DN đầy đủ trên directory |
| --- | --- |
| `uid=chi,ou=People` | `uid=chi,ou=People,dc=example,dc=org` |
| `cn=Engineering,ou=Groups` | `cn=Engineering,ou=Groups,dc=example,dc=org` |
| `ou=People` | `ou=People,dc=example,dc=org` |

Với `ContextSource.base = dc=example,dc=org`, nếu truyền nhầm:

```java
ldapTemplate.bind(
    "uid=chi,ou=People,dc=example,dc=org",
    null,
    attrs
);
```

ứng dụng có thể tạo một đường dẫn bị **nối lặp suffix** khi Spring LDAP xử lý DN tương đối với base. Trường hợp này thường dẫn tới lỗi parent không tồn tại hoặc DN không đúng.

### 5.1. Dựng DN bằng `LdapNameBuilder`

`LdapNameBuilder` giúp ghép các RDN với escaping đúng, thay vì nối chuỗi:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance()
    .add("ou", "People")
    .add("uid", "chi")
    .build();

ldapTemplate.bind(relativeDn, null, attrs);
```

Nếu `uid` đến từ input người dùng và chứa dấu phẩy hoặc dấu cộng:

```text
uid = "chi,qa"
```

builder sẽ xử lý ký tự đặc biệt theo cú pháp DN, tránh trường hợp dấu phẩy trong giá trị bị hiểu thành dấu tách RDN.

**DN escaping khác LDAP filter escaping.** Khi tìm kiếm bằng filter, dùng `LdapQueryBuilder` hoặc API filter có escaping theo **RFC 4515**; khi tạo DN, dùng `LdapNameBuilder` theo quy tắc DN của **RFC 4514**.

### 5.2. RDN phải phù hợp attribute trong entry

Với DN:

```text
uid=chi,ou=People,dc=example,dc=org
```

entry nên có attribute:

```ldif
uid: chi
```

RDN không phải chỉ là “nhãn tùy ý của thư mục”. Schema/naming model yêu cầu giá trị được dùng trong RDN phù hợp nội dung của entry. Nếu dùng `cn=Chi Nguyen` làm RDN, ứng dụng phải có giá trị `cn` tương ứng trong tập attributes và objectClass cho phép.

### 5.3. Parent phải có trước

LDAP Add không tự tạo toàn bộ các parent trong DN.

Nếu chưa có:

```text
ou=People,dc=example,dc=org
```

thì không thể kỳ vọng `bind("uid=chi,ou=People",...)` tự tạo `ou=People` và suffix `dc=example,dc=org`.

Với ứng dụng provisioning, tạo các nhánh OU cần thiết qua quy trình hạ tầng riêng, trong đúng thứ tự và với tài khoản có quyền. Việc tạo cấu trúc directory không nên diễn ra tùy ý chỉ vì một request tạo người dùng muốn một OU chưa tồn tại.

## 6. Ví dụ repository Spring LDAP hoàn chỉnh

Một repository nên nhận dữ liệu đã được kiểm tra ở tầng ứng dụng rồi **chỉ thực hiện nhiệm vụ ánh xạ và tạo entry**. Ví dụ dưới đây sử dụng Java 17+ và `LdapTemplate` được Spring cấu hình.

### 6.1. DTO đầu vào

```java
public record NewPerson(
    String uid,
    String commonName,
    String surname,
    String givenName,
    String email
) {}
```

`uid` là mã dùng trong RDN. `commonName` và `surname` là dữ liệu cho `cn` và `sn` theo schema của `person`.

Ở API thực tế, validate các trường bắt buộc trước khi gọi repository: không rỗng, độ dài chấp nhận được, tên thuộc tính và OU được kiểm soát, các quy tắc nghiệp vụ cụ thể. Escaping DN **không thay** validation dữ liệu.

### 6.2. Repository

```java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class LdapPersonRepository {
    private final LdapTemplate ldapTemplate;

    public LdapPersonRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void create(NewPerson person) {
        if (person.uid() == null || person.uid().isBlank()
                || person.commonName() == null
                || person.commonName().isBlank()
                || person.surname() == null
                || person.surname().isBlank()) {
            throw new IllegalArgumentException(
                "Missing required person fields");
        }

        Name relativeDn = LdapNameBuilder.newInstance()
            .add("ou", "People")
            .add("uid", person.uid())
            .build();

        Attributes attributes = personAttributes(person);

        // Chỉ thao tác này gửi yêu cầu tạo entry lên LDAP.
        ldapTemplate.bind(relativeDn, null, attributes);
    }

    static Attributes personAttributes(NewPerson person) {
        Attributes attrs = new BasicAttributes(true);

        BasicAttribute objectClasses =
            new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");
        attrs.put(objectClasses);

        attrs.put("uid", person.uid());
        attrs.put("cn", person.commonName());
        attrs.put("sn", person.surname());

        if (person.givenName() != null
                && !person.givenName().isBlank()) {
            attrs.put("givenName", person.givenName());
        }
        if (person.email() != null && !person.email().isBlank()) {
            attrs.put("mail", person.email());
        }
        return attrs;
    }
}
```

**Giả định của ví dụ:**

- `ContextSource.base = dc=example,dc=org`.
- Parent `ou=People` đã có.
- Server hỗ trợ object classes `top/person/organizationalPerson/inetOrgPerson` với các attribute tương ứng.
- `uid` là naming attribute được phép cho loại entry này.
- Bind account có quyền thêm entry dưới People.
- Quy định nghiệp vụ chấp nhận tạo entry chưa có password; password và activation được quản lý bằng quy trình riêng.

Mã tạo **một entry mới**, không tự thực hiện các hoạt động phụ như cấp nhóm quyền, gửi email kích hoạt hay ghi vào HR system. Những bước đó phải được tổ chức ở tầng use case, không cài ngầm vào `personAttributes(...)`.

### 6.3. Lệnh gọi từ service

```java
NewPerson person = new NewPerson(
    "chi",
    "Chi Nguyen",
    "Nguyen",
    "Chi",
    "chi@example.org"
);

repository.create(person);
```

Nếu tạo thành công, entry có thể được tra bằng:

```text
uid=chi,ou=People,dc=example,dc=org
```

Ở môi trường thật, nên làm rõ quyền gọi tạo user, cách tránh tạo trùng, nơi lưu audit event và quy tắc kích hoạt tài khoản. Chỉ tạo bản ghi LDAP **không** phải kết thúc toàn bộ quy trình onboarding.

## 7. Schema và `objectClass` quyết định dữ liệu nào hợp lệ

LDAP server kiểm tra entry theo schema. Tập `Attributes` không thể chỉ chứa `uid` và `mail` nếu objectClass yêu cầu các thuộc tính khác.

### 7.1. Chuỗi kế thừa chuẩn thường gặp

```text
top
  └── person
       └── organizationalPerson
            └── inetOrgPerson
```

Tài khoản cá nhân dùng `inetOrgPerson` có thể khai báo nhiều objectClass trong hệ kế thừa này. Theo schema chuẩn:

| ObjectClass/loại | Ví dụ yêu cầu hoặc khả năng |
| --- | --- |
| `top` | Superclass cơ bản, objectClass cần có |
| `person` | Yêu cầu `cn` và `sn` |
| `organizationalPerson` | Mở rộng `person` với thuộc tính tổ chức |
| `inetOrgPerson` | Mở rộng để hỗ trợ các thuộc tính thường dùng cho người dùng Internet như `uid`, `mail` |

**Không phải mọi directory sử dụng đúng schema mặc định.** Active Directory, OpenLDAP có extension và schema tùy chỉnh có thể có thêm các ràng buộc hoặc objectClass khác. Trước khi tạo entry trên production, cần kiểm tra schema của server và chính sách provisioning của tổ chức.

### 7.2. Có thể chỉ gửi `objectClass=inetOrgPerson` không?

Một số LDAP server có thể suy ra superclasses hoặc chấp nhận danh sách objectClass cụ thể, nhưng không nên tự giả định mọi server xử lý giống nhau. Ví dụ ở bài này liệt kê đầy đủ `top/person/organizationalPerson/inetOrgPerson` để dễ quan sát.

**Schema inheritance** khác việc người viết mã tự đặt một chuỗi tên tùy ý. Nếu một structural objectClass không hợp lệ hoặc thiếu thuộc tính MUST, server có thể trả `objectClassViolation` và Spring LDAP chuyển thành exception liên quan schema.

### 7.3. RDN không nên là trường không được phép theo schema

Nếu xây DN bằng `uid=chi` nhưng attributes lại thiếu `uid: chi`, entry có thể bị từ chối. Nếu đặt `cn` sai kiểu, `sn` trống không hợp lệ theo rule, hoặc thêm thuộc tính không thuộc nhóm MUST/MAY của các objectClass đã khai báo, server cũng có thể từ chối.

Nên tạo một hàm helper **duy nhất** dựng DN và attributes từ cùng input đã validate để giảm nguy cơ RDN và attribute không khớp.

## 8. Ví dụ khác: tạo nhóm với `groupOfNames`

Để thấy rõ một attribute đa trị, xét việc thêm nhóm Engineering dưới `ou=Groups`.

Một nhóm `groupOfNames` thường có những thuộc tính MUST:

- `cn` — common name của nhóm.
- `member` — ít nhất một DN thành viên theo schema chuẩn.

Ví dụ:

```java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.support.LdapNameBuilder;

Name groupDn = LdapNameBuilder.newInstance()
    .add("ou", "Groups")
    .add("cn", "Engineering")
    .build();

Attributes groupAttrs = new BasicAttributes(true);

BasicAttribute classes = new BasicAttribute("objectClass");
classes.add("top");
classes.add("groupOfNames");
groupAttrs.put(classes);

groupAttrs.put("cn", "Engineering");

BasicAttribute members = new BasicAttribute("member");
members.add("uid=an,ou=People,dc=example,dc=org");
members.add("uid=chi,ou=People,dc=example,dc=org");
groupAttrs.put(members);

ldapTemplate.bind(groupDn, null, groupAttrs);
```

Trong ví dụ:

- `groupDn` là DN tương đối với `ContextSource.base`.
- Các giá trị của `member` là **DN đầy đủ** của thành viên, không phải DN tương đối với base của Spring LDAP.
- `member` đa trị được xây bằng một `BasicAttribute` chứa nhiều giá trị.
- Entry People của An và Chi phải phù hợp với policy dữ liệu; kiểm tra tồn tại và ACL tùy quy định server.

**Không cố tạo nhóm `groupOfNames` trống bằng cách bỏ `member`** nếu schema vẫn yêu cầu MUST. Nếu ứng dụng cần nhóm chưa có thành viên, hãy chọn model nhóm/schema phù hợp (nếu server cho phép) thay vì phá quy tắc.

### 8.1. DN được dùng làm attribute value không tự động áp dụng base

Đừng nhầm:

```java
// Đường dẫn tới entry cần tạo: tương đối với ContextSource.base
Name groupDn = LdapNameBuilder.newInstance()
    .add("ou", "Groups")
    .add("cn", "Engineering")
    .build();

// Giá trị attribute member: DN đầy đủ theo directory schema
String memberValue =
    "uid=an,ou=People,dc=example,dc=org";
```

Việc chọn đúng loại DN sẽ quan trọng hơn khi organization có nhiều OU lồng nhau, nhiều suffix hoặc nhóm thuộc nhiều naming context.

## 9. Dùng `Attributes` hay `DirContextAdapter`?

Cả hai đều có thể phục vụ việc tạo entry. Nhưng mục tiêu của bài này là **bind entry bằng Attributes thuần**.

| Tiêu chí | `BasicAttributes` + `bind(dn,null,attrs)` | `DirContextAdapter` + `bind(ctx)` |
| --- | --- | --- |
| Mô hình dữ liệu | JNDI `Attributes`/`Attribute` | Spring LDAP `DirContextOperations` |
| Cách đặt giá trị | `put(...)`, `BasicAttribute.add(...)` | `setAttributeValue(s)`, `addAttributeValue` |
| DN truyền ở đâu? | Đối số `dn` của bind | DN gắn với context |
| Tập attributes | Tự tạo rõ ràng trước lệnh bind | Tạo trong adapter |
| Thích hợp | Nắm cơ chế JNDI, dữ liệu đơn giản | Mã Spring LDAP cần API tiện dụng hơn |
| Update entry đang có | Dùng `modifyAttributes` riêng | `lookupContext` rồi `modifyAttributes(ctx)` |

Một cách tạo bằng adapter:

```java
import org.springframework.ldap.core.DirContextAdapter;

DirContextAdapter ctx = new DirContextAdapter(relativeDn);

ctx.setAttributeValues(
    "objectClass",
    new String[] {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
);
ctx.setAttributeValue("uid", "chi");
ctx.setAttributeValue("cn", "Chi Nguyen");
ctx.setAttributeValue("sn", "Nguyen");

ldapTemplate.bind(ctx);
```

Chọn **một** cách làm rõ ràng. Đừng đồng thời tạo `BasicAttributes` và `DirContextAdapter` chỉ để làm cùng một việc khi không có nhu cầu đặc biệt.

### 9.1. `LdapClient` và ODM

Spring LDAP còn cung cấp API `LdapClient` dạng fluent, ví dụ bind một context đã được tạo, và ODM có `create(Object entry)` khi entity được ánh xạ bằng annotation thích hợp.

Những API đó vẫn phải thỏa các điều kiện của LDAP server: DN mới, parent tồn tại, objectClass/schema đúng và quyền ghi. **Chọn API không làm biến mất giới hạn hay ràng buộc của LDAP.**

## 10. `bind`, `rebind`, `modifyAttributes` và `rename` khác nhau

| Phương thức | Ý nghĩa chính | Trường hợp sử dụng |
| --- | --- | --- |
| `bind(dn, null, attrs)` | **Tạo entry mới** tại DN | Onboarding entry mới |
| `rebind(dn, null, attrs)` | Thay thế entry đã tồn tại theo contract API | Cân nhắc kỹ: có thể thay nhiều dữ liệu |
| `modifyAttributes(dn, items)` | Sửa các attribute của entry đang có | Sửa mail, phone, description |
| `modifyAttributes(ctx)` | Áp dụng các thay đổi do adapter tính | Cập nhật context đã lookup |
| `rename(oldDn, newDn)` | Đổi RDN hoặc chuyển vị trí entry | Đổi UID trong DN, chuyển OU |
| `unbind(dn)` | Xóa entry theo điều kiện API | Hủy một entry không còn dùng |

**Không dùng `rebind` như “tạo nếu chưa có”** khi mục tiêu là chống trùng. JavaDoc Spring LDAP mô tả `rebind` theo hướng thay thế entry đã tồn tại; thay thế nhầm có thể làm mất các thuộc tính không nằm trong payload.

**Không dùng `bind` để cập nhật giá trị** của entry đang tồn tại. Một yêu cầu tạo mới ở DN đã chiếm thường thất bại — đó là hành vi bảo vệ dữ liệu, không phải lỗi cần lách bằng cách ghi đè.

### 10.1. Tạo entry không tự cập nhật quan hệ bên ngoài

Nếu ứng dụng tạo một người dùng mới rồi cần đưa người dùng vào nhóm `member`, đó là **thao tác thứ hai**: sửa attribute của entry nhóm.

```text
Bước A: Add người dùng uid=chi
Bước B: Modify nhóm cn=Engineering, thêm member=DN_Chi
Bước C: Kiểm tra trạng thái và audit
```

Đây không phải một transaction LDAP xuyên nhiều entry có tính nguyên tử được bảo đảm trong mọi server. Nếu bước A thành công nhưng B thất bại, cần kế hoạch phục hồi hoặc đối soát, không tự xem toàn bộ quy trình đã hoàn tất.

## 11. Kiểm tra entry trước và sau khi tạo

### 11.1. Có nên kiểm tra DN đã tồn tại trước khi bind?

Có thể thực hiện lookup để đưa thông điệp thân thiện, nhưng **kiểm tra trước không loại bỏ race condition**:

```text
Request A: lookup(uid=chi) -> chưa tồn tại
Request B: lookup(uid=chi) -> chưa tồn tại
Request A: bind(uid=chi) -> thành công
Request B: bind(uid=chi) -> NameAlreadyBoundException
```

Ứng dụng vẫn phải bắt lỗi trùng DN ở thao tác bind thực tế.

Đối với API provisioning có tính idempotent, có thể sử dụng business key và kiểm tra trạng thái hiện tại sau xung đột; nhưng đừng **im lặng coi trùng DN là thành công** nếu entry có dữ liệu khác với request.

### 11.2. Lookup để xác minh

Sau khi bind, có thể kiểm tra:

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;

Name dn = LdapNameBuilder.newInstance()
    .add("ou", "People")
    .add("uid", "chi")
    .build();

Object created = ldapTemplate.lookup(dn);
```

`lookup(dn)` thường trả một object hoặc context adapter tùy `ContextSource` và `DirObjectFactory` được cấu hình. Nếu chỉ cần xác nhận vài attribute, nên dùng overload mapping phù hợp:

```java
import org.springframework.ldap.core.AttributesMapper;

String createdUid = ldapTemplate.lookup(
    dn,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("uid").get()
);
```

Mapper phải xử lý trường hợp attribute không xuất hiện (do projection, ACL hoặc dữ liệu), thay vì coi `NullPointerException` là lỗi user không tồn tại.

**Nếu đọc qua replica dự phòng**, entry có thể chưa xuất hiện ngay do replication lag. Với nghiệp vụ đòi hỏi read-after-write, cần lựa chọn server/đường đọc và cơ chế xác nhận phù hợp.

### 11.3. Dùng `ldapsearch` để kiểm chứng

Ví dụ công cụ OpenLDAP:

```bash
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=ServiceAccounts,dc=example,dc=org" -W \
  -b "uid=chi,ou=People,dc=example,dc=org" -s base \
  "(objectClass=*)" uid cn sn objectClass
```

`-b` ở CLI nhận **DN đầy đủ**, khác với DN tương đối thường truyền vào `LdapTemplate` khi đã cấu hình `ContextSource.base`.

`-W` yêu cầu nhập password qua prompt thay vì đặt password trực tiếp trên command line. Dùng TLS và kiểm tra chứng chỉ theo chính sách của hệ thống.

## 12. Các lỗi thường gặp khi bind entry

Spring LDAP chuyển nhiều lỗi checked `javax.naming.NamingException` của JNDI thành exception runtime thuộc `org.springframework.ldap`.

| Tình huống | Exception/result thường gặp | Cách xử lý |
| --- | --- | --- |
| DN đã tồn tại | `NameAlreadyBoundException` / `entryAlreadyExists` | Xử lý conflict, kiểm tra dữ liệu và idempotency |
| Parent DN không tồn tại | `NameNotFoundException` / `noSuchObject` | Tạo parent theo quy trình, xác minh base DN |
| DN sai cú pháp | `InvalidNameException` / `invalidDNSyntax` | Dựng bằng `LdapNameBuilder` |
| Thiếu `cn`/`sn` hoặc objectClass sai | `SchemaViolationException` / `objectClassViolation` | Sửa payload theo schema |
| Attribute không được phép hoặc syntax sai | `InvalidAttributesException` / lỗi schema | Kiểm tra MAY/MUST, giá trị, cú pháp |
| Tài khoản bind không có quyền thêm | `NoPermissionException` / `insufficientAccessRights` | Sửa ACL/role đúng phạm vi, không dùng tài khoản quản trị tràn lan |
| Server không sẵn sàng | `ServiceUnavailableException` | Theo dõi hạ tầng và retry có chính sách |
| Mạng/TLS có lỗi | `CommunicationException` | Kiểm tra socket, timeout, TLS và trạng thái thao tác |
| Server không cho thao tác | `OperationNotSupportedException` hoặc result code khác | Kiểm tra chính sách và khả năng LDAP server |

**Loại exception cụ thể phụ thuộc server và JNDI provider**. Đừng viết code suy đoán mọi lỗi schema luôn trả một class duy nhất hoặc mọi lỗi mạng đều có thể retry an toàn.

### 12.1. Xử lý conflict theo nghiệp vụ

```java
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.SchemaViolationException;
import org.springframework.ldap.NoPermissionException;

public void provision(NewPerson person) {
    try {
        repository.create(person);
    } catch (NameAlreadyBoundException ex) {
        throw new IllegalStateException(
            "An LDAP entry already uses this DN", ex
        );
    } catch (SchemaViolationException ex) {
        throw new IllegalArgumentException(
            "Entry attributes do not satisfy LDAP schema", ex
        );
    } catch (NoPermissionException ex) {
        throw new IllegalStateException(
            "Provisioning account lacks LDAP permissions", ex
        );
    }
}
```

Trong ứng dụng thật, thay các exception ví dụ bằng loại lỗi service/domain phù hợp và ánh xạ ở API layer. Không đưa nguyên bind DN, password, schema chi tiết hoặc stack trace ra phản hồi công khai.

### 12.2. Lỗi mất kết nối không chứng minh Add thất bại

```text
Client gửi AddRequest uid=chi
LDAP server tạo entry thành công
Mạng đứt trước AddResponse
Client nhận CommunicationException
```

Không được tự khẳng định **“entry chưa được tạo”**. Retry ngay có thể gặp `NameAlreadyBoundException`; nếu client chuyển sang replica chưa cập nhật, lại có thể tạo xung đột hoặc nhìn thấy dữ liệu cũ.

Cần có quy trình **đối chiếu trạng thái**: tra DN đích trên nguồn có tính nhất quán phù hợp, kiểm tra business key/attributes kỳ vọng, ghi audit/correlation ID, và chỉ retry khi đã đánh giá idempotency. Đặc biệt tránh retry vô hạn trên sự cố hạ tầng.

## 13. Bảo mật khi tạo entry

Thao tác tạo entry có thể cấp danh tính mới và ảnh hưởng hệ thống xác thực, nhóm hoặc phân quyền. Vì vậy cần nhiều lớp bảo vệ.

### 13.1. Quyền tối thiểu

Tài khoản `app-writer` chỉ nên được phép thêm/sửa các object và nhánh cần thiết. Nếu API chỉ tạo người dùng dưới `ou=People`, đừng cấp quyền ghi toàn suffix `dc=example,dc=org`.

Chính sách quyền cần được thực thi tại **LDAP server ACL**. Validation ở ứng dụng hữu ích nhưng không thay thế ACL.

### 13.2. Không nhúng password vào mã nguồn

Các ví dụ tạo `inetOrgPerson` trong bài **không đặt `userPassword`**. Đây là lựa chọn có chủ đích để tránh khuyến khích ghi mật khẩu cleartext vào source/log hoặc cho rằng chỉ cần đặt một attribute là đã có quy trình xác thực an toàn.

Nếu nghiệp vụ cần tạo credentials, phải tuân thủ quy trình provisioning mật khẩu của directory:

- Dùng TLS được xác minh trên toàn đường truyền.
- Không lưu/ghi password ra file log hoặc exception message.
- Tôn trọng chính sách password và cơ chế hash/update mà server hỗ trợ.
- Với Active Directory hoặc server đặc thù, thao tác đặt password có thể dùng thuộc tính/API riêng và yêu cầu connection security/ACL khác.
- Việc kích hoạt tài khoản, reset password và ủy quyền thường là bước nghiệp vụ riêng.

### 13.3. Kiểm tra dữ liệu từ người dùng

Dù `LdapNameBuilder` escape các ký tự đặc biệt trong DN, vẫn cần validate:

- Những ký tự và độ dài được phép cho `uid`.
- Các trường `cn`, `sn`, `mail` có hợp đồng dữ liệu phù hợp.
- Tập `objectClass` được cố định theo use case, không nhận tùy ý từ request.
- Parent/OU được phép tạo entry.
- Nhóm hoặc quyền mặc định phải được policy quyết định, không lấy thẳng từ input.
- Không cho tạo service account hoặc administrative entry qua endpoint người dùng bình thường.

**Escaping bảo vệ cú pháp; authorization quyết định có được thực hiện thao tác hay không.**

### 13.4. Logging và audit

Nên ghi sự kiện provisioning có correlation ID, kết quả và principal nghiệp vụ được phép lưu. Hạn chế ghi nguyên DN người dùng, email, đặc biệt password và attributes nhạy cảm.

Một lỗi `SchemaViolationException` có thể cần thông tin kỹ thuật để điều tra, nhưng API công khai chỉ nên hiển thị thông báo phù hợp; log nội bộ phải được bảo vệ theo chính sách dữ liệu.

## 14. Unit test cho DN và `Attributes`

Không cần LDAP server để kiểm tra **cách ứng dụng xây DN và tập thuộc tính**. Có thể tạo `BasicAttributes` và kiểm tra các field cần thiết bằng JUnit.

### 14.1. Kiểm tra tập thuộc tính

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.directory.Attributes;
import javax.naming.directory.Attribute;
import org.junit.jupiter.api.Test;

class PersonAttributesTest {

    @Test
    void includesRequiredClassesAndAttributes() throws Exception {
        NewPerson p = new NewPerson(
            "chi", "Chi Nguyen", "Nguyen", "Chi", "chi@example.org"
        );

        Attributes attrs = LdapPersonRepository.personAttributes(p);

        Attribute classes = attrs.get("objectClass");
        assertTrue(classes.contains("top"));
        assertTrue(classes.contains("person"));
        assertTrue(classes.contains("organizationalPerson"));
        assertTrue(classes.contains("inetOrgPerson"));

        assertEquals("chi", attrs.get("uid").get());
        assertEquals("Chi Nguyen", attrs.get("cn").get());
        assertEquals("Nguyen", attrs.get("sn").get());
        assertEquals("chi@example.org", attrs.get("mail").get());
    }

    @Test
    void omitsOptionalBlankEmail() {
        NewPerson p = new NewPerson(
            "chi", "Chi Nguyen", "Nguyen", "Chi", ""
        );

        Attributes attrs = LdapPersonRepository.personAttributes(p);
        assertNull(attrs.get("mail"));
    }

    @Test
    void attributeNamesAreCaseInsensitiveLocally() {
        NewPerson p = new NewPerson(
            "chi", "Chi Nguyen", "Nguyen", "Chi", null
        );
        Attributes attrs = LdapPersonRepository.personAttributes(p);

        assertNotNull(attrs.get("OBJECTCLASS"));
        assertNotNull(attrs.get("CN"));
    }
}
```

Những test này xác nhận **payload client tạo ra**, không xác nhận server có schema/ACL giống kỳ vọng. `BasicAttribute.contains(...)` cũng chỉ kiểm tra giá trị trong object local, không chứng minh matching rule server.

### 14.2. Kiểm tra DN có ký tự đặc biệt

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance()
    .add("ou", "People")
    .add("uid", "chi,qa")
    .build();

// Tên này phải chứa đúng một RDN uid và một RDN ou.
assertEquals(2, dn.size());
assertEquals(
    "uid=chi\\,qa,ou=People",
    dn.toString()
);
```

Test này cho thấy dấu phẩy của `uid` được escape như **ký tự dữ liệu**, không trở thành RDN phân cách. Dấu gạch chéo trong Java literal phải được escape thành `\\`.

### 14.3. Kiểm tra repository gọi `bind`

Dùng mock `LdapTemplate` trong unit test để xác minh:

1. DN được truyền là `uid=chi,ou=People`, không nối lặp suffix.
2. Tham số `obj` là `null`.
3. `Attributes` chứa object classes và giá trị `uid`, `cn`, `sn`.
4. Không gọi `rebind` hoặc `modifyAttributes` khi mục đích là tạo mới.
5. Input thiếu trường bắt buộc bị chặn trước khi gửi LDAP request.

Tùy framework mock, có thể dùng argument captor cho `Name` và `Attributes`, sau đó kiểm tra trạng thái. Không cần khởi động LDAP server cho kiểm thử cấu trúc lời gọi.

## 15. Integration test với LDAP server

Integration test nên dùng directory test gần với schema/ACL thực tế. Một số server nhúng có thể không mô phỏng chính xác Active Directory hoặc hạn mức/schema của production.

| Kịch bản | Chuẩn bị | Kết quả cần kiểm tra |
| --- | --- | --- |
| Tạo user mới hợp lệ | Parent `ou=People` tồn tại, DN chưa có | Add thành công; lookup được entry |
| Tạo lại cùng DN | Entry đã tồn tại | Báo conflict/`NameAlreadyBoundException` |
| Parent không tồn tại | Dùng `ou=Unknown` | Báo lỗi parent/DN thích hợp |
| Thiếu `sn` | Schema `person` yêu cầu `sn` | Server từ chối payload |
| RDN `uid` không có trong attrs | Cố tạo thiếu `uid` | Server từ chối theo naming/schema |
| Cú pháp DN có dấu phẩy | `uid=chi,qa` | DN parse đúng, không bị tách RDN sai |
| ObjectClass thiếu hoặc sai | Payload không đạt schema | Không tạo entry không hợp lệ |
| User account không có quyền thêm | Bind principal chỉ có read | Add bị từ chối |
| Attribute đa trị | Tạo nhóm có nhiều `member` | Đọc lại đầy đủ giá trị theo quyền |
| Đọc lại trên replica | Tạo trên A, lookup trên B | Nhận diện replication lag |
| Mạng ngắt sau Add | Mô phỏng trong staging được phép | Không retry ghi mù; đối chiếu trạng thái |
| TLS handshake fail | Server test có certificate sai | Fail closed, không vô hiệu hóa TLS verification |

### 15.1. Quy trình teardown dữ liệu test

Nếu test thực sự tạo entry, phải dùng **DN thử nghiệm riêng** và dọn dẹp có kiểm soát, ví dụ `uid=test-create-...` dưới OU thử nghiệm.

Không viết teardown bằng `unbind` trên toàn `ou=People` hoặc nhánh production. Chỉ xóa đúng entry test đã tạo, với identity/quyền phù hợp, và xử lý trường hợp test thất bại giữa chừng khiến entry chưa xuất hiện.

Nếu lệnh tạo gặp lỗi kết nối, teardown cũng cần kiểm tra trạng thái thực tế để tránh để lại entry rác hoặc xóa nhầm dữ liệu.

## 16. Checklist triển khai tạo entry an toàn

Trước khi gọi `ldapTemplate.bind(...)`, hãy tự hỏi:

| Kiểm tra | Câu hỏi |
| --- | --- |
| DN | Đã dựng bằng `LdapNameBuilder`, đúng RDN và base? |
| Parent | OU cha có tồn tại trên server đang ghi? |
| Schema | ObjectClass, MUST, MAY, syntax và naming attribute có hợp lệ? |
| Attributes | Đã dùng `BasicAttributes(true)` và `BasicAttribute` đúng cho đa trị? |
| Uniqueness | DN hoặc business key có thể trùng? Đã chuẩn bị xử lý race condition? |
| Security | Bind principal có quyền tối thiểu? TLS có xác minh certificate? |
| Password | Có tách quy trình provisioning credential và không log bí mật? |
| Intent | Đây thực sự là **tạo mới**, không phải update/replace/rename? |
| Error handling | Có phân biệt trùng DN, lỗi schema, ACL, network và trạng thái chưa biết? |
| Verification | Có thể lookup entry trên nguồn phù hợp sau khi tạo? |
| Audit | Có correlation ID và dấu vết theo chính sách bảo mật? |
| Testing | Unit test payload và integration test schema/ACL đầy đủ? |

**Không nên chỉ dựa vào một phép lookup kiểm tra trước để quyết định việc tạo không có cạnh tranh đồng thời.** Chỉ kết quả bind và cơ chế xử lý conflict mới xác định thao tác tạo entry được server chấp nhận hay không.

## 17. Bài tập thực hành

Giả sử `ContextSource.base = dc=example,dc=org`, có sẵn OU `ou=People` và `ou=Groups`. Tài khoản bind có quyền tạo entry thử nghiệm.

**Bài 1.** Tạo entry `uid=chi` dưới `ou=People`. Khi dùng `LdapTemplate.bind(Name, Object, Attributes)`, tham số `obj` nên là gì nếu đã có đầy đủ `Attributes`?

**Bài 2.** Liệt kê tối thiểu các objectClass và attribute cần thiết của `inetOrgPerson` theo ví dụ trong bài. Vì sao thiếu `sn` có thể làm thao tác thất bại?

**Bài 3.** Với `ContextSource.base = dc=example,dc=org`, phải truyền DN đầy đủ `uid=chi,ou=People,dc=example,dc=org` hay DN tương đối `uid=chi,ou=People` cho template?

**Bài 4.** Trong code sau, tại sao chỉ còn một giá trị `objectClass`?

```java
attrs.put("objectClass", "top");
attrs.put("objectClass", "person");
attrs.put("objectClass", "inetOrgPerson");
```

**Bài 5.** Hai request cùng kiểm tra `uid=chi` chưa tồn tại rồi cùng tạo. Loại lỗi có thể xảy ra ở request thứ hai là gì? Cách kiểm tra trước đã đủ chống race condition chưa?

**Bài 6.** Ứng dụng muốn tạo nhóm `groupOfNames` chưa có thành viên. Có thể bỏ `member` mặc định không? Cần làm gì nếu nghiệp vụ muốn nhóm trống?

**Bài 7.** Tại sao không nên gọi `rebind` để tránh exception khi DN đã tồn tại?

**Bài 8.** Client nhận `CommunicationException` khi thêm user nhưng server có thể đã trả kết quả thành công trước khi đường truyền đứt. Cách xử lý đúng hơn retry ngay là gì?

**Bài 9.** Trong một entry người dùng, `mail` có hai giá trị. Nên dùng `attrs.put("mail", value)` hai lần hay một `BasicAttribute("mail")` rồi `add` hai giá trị?

**Bài 10.** Một người dùng có `uid = "chi,qa"`. Tại sao không được ghép trực tiếp `"uid=" + uid + ",ou=People"`? API nào nên dùng?

**Bài 11.** Một entry đã tồn tại, ứng dụng chỉ muốn thay số điện thoại. Nên dùng `bind`, `modifyAttributes` hay `rename`?

**Bài 12.** Mã `ldapTemplate.bind(dn, null, attrs)` đã chạy xong, nhưng đọc trên LDAP B không thấy entry; vừa ghi ở LDAP A. Có thể kết luận thao tác tạo thất bại không?

### Đáp án gợi ý

1. `obj = null`; cung cấp `attrs` không null. Đây là thao tác **tạo entry**, không phải xác thực user.
2. Ví dụ liệt kê `top`, `person`, `organizationalPerson`, `inetOrgPerson` với `cn`, `sn` và `uid` dùng cho RDN. `person` yêu cầu `cn` và `sn` theo schema chuẩn.
3. Truyền **DN tương đối** `uid=chi,ou=People` vì suffix đã cấu hình trong `ContextSource.base`.
4. `Attributes.put(String,Object)` **đặt/thay attribute** cùng ID, không bổ sung từng giá trị. Dùng `BasicAttribute("objectClass")` rồi `add(...)`.
5. `NameAlreadyBoundException` hoặc result code trùng DN tương ứng. Lookup trước không ngăn được race condition.
6. `groupOfNames` có `member` là MUST trong schema chuẩn. Cần chọn loại nhóm/schema phù hợp hoặc quy trình khởi tạo khác theo chính sách server.
7. `rebind` có semantics thay thế entry, có thể ghi đè dữ liệu không có chủ đích; conflict cần được xử lý tường minh.
8. Đối chiếu DN và payload trên nguồn có tính nhất quán phù hợp, ghi nhận trạng thái và áp dụng retry có kiểm soát/idempotency.
9. Dùng một `BasicAttribute("mail")` rồi `add` các giá trị. Gọi `put` nhiều lần có thể thay giá trị trước.
10. Dấu phẩy có ý nghĩa phân cách RDN; dùng `LdapNameBuilder` để escape theo DN syntax.
11. Dùng `modifyAttributes` trên entry đang tồn tại; `rename` chỉ dùng khi DN thay đổi.
12. **Không.** Replica B có thể chưa nhận replication. Cần kiểm tra nguồn đã ghi và độ trễ đồng bộ.

## 18. Ghi nhớ

- **`LdapTemplate.bind(dn, null, attributes)` tạo một LDAP entry mới**, khác với *LDAP bind request* để xác thực.
- **DN phải duy nhất, parent phải tồn tại, RDN phải hợp lệ** và attributes phải đáp ứng schema/objectClass.
- Dùng **`BasicAttributes(true)`** cho tập thuộc tính; dùng **`BasicAttribute.add(...)`** để xây attribute đa trị như `objectClass` hoặc `member`.
- Khi `ContextSource.base` đã đặt, **DN truyền cho template thường là tương đối**. Dùng `LdapNameBuilder` để escape giá trị RDN.
- **`bind` không phải update/upsert**; để sửa entry dùng `modifyAttributes`, đổi DN dùng `rename`, và cân nhắc kỹ rủi ro của `rebind`.
- **Không retry thao tác Add mù quáng sau lỗi mạng**, vì server có thể đã tạo entry. Phải xử lý DN trùng, schema/ACL và trạng thái chưa xác định theo nghiệp vụ.
- Kiểm thử cả **payload local** và **server thực**; dùng TLS, quyền ghi tối thiểu, tránh lộ credentials/dữ liệu nhạy cảm.

### Tài liệu tham khảo

- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): các overload `bind`, `rebind`, `lookup` và `modifyAttributes`.
- [Spring LDAP — Basic Operations](https://docs.spring.io/spring-ldap/reference/basic-operations.html): thêm entry bằng `Attributes`, sửa/xóa entry và DN.
- [Spring LDAP — Simplifying Attribute Access with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html): bind với adapter, mapping attributes và update.
- [Java SE — Attributes](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/Attributes.html): contract của tập thuộc tính.
- [Java SE — BasicAttributes](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/BasicAttributes.html): cách dùng `put` và `ignoreCase`.
- [Java SE — BasicAttribute](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/BasicAttribute.html): thêm giá trị vào thuộc tính đa trị.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): AddRequest, BindRequest, DN và result code.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): objectClass, thuộc tính MUST/MAY và naming.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): cú pháp DN và escaping.
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): escaping dữ liệu filter.
