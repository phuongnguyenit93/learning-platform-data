# NameAlreadyBoundException và conflict khi tạo

Trong **Spring LDAP**, ứng dụng thường tạo người dùng, nhóm hoặc đơn vị tổ chức (OU) bằng `LdapTemplate.bind(...)`, `LdapClient` hoặc một tầng ánh xạ đối tượng (ODM). Khi một entry đã tồn tại tại distinguished name (**DN**) cần tạo, LDAP server thường trả **`entryAlreadyExists` (resultCode `68`)**. JNDI và Spring LDAP biểu diễn lỗi này bằng `NameAlreadyBoundException`. Đây là tình huống quan trọng vì có thể phản ánh dữ liệu bị trùng, hai request tạo đồng thời, hoặc việc gửi lại lệnh sau khi mất phản hồi mạng.

Bài thuộc chương **Exception** của module **SPRING_LDAP**. Ta sẽ đi từ cách nhận diện ngoại lệ, phạm vi duy nhất của DN, thao tác Add bằng `LdapTemplate`, thiết kế API có ngữ nghĩa xung đột, đến kiểm thử đồng thời và xử lý retry an toàn. Các ví dụ giả định `ContextSource` đã cấu hình kết nối tới LDAP server, base DN và tài khoản có quyền phù hợp. Kiến thức cũng áp dụng khi triển khai với `LdapClient` hoặc ODM, dù chữ ký API cụ thể có thể khác.

## 1. Kết quả mong đợi

Sau bài này, người học có thể:

1. Nhận diện `javax.naming.NameAlreadyBoundException` và `org.springframework.ldap.NameAlreadyBoundException`; biết chúng khác `DuplicateKeyException` của Spring DAO.
2. Giải thích vì sao server trả mã LDAP `68` khi tạo entry có **DN đã tồn tại** và vì sao trùng giá trị `uid` ở OU khác chưa chắc gây `68`.
3. Dùng `LdapNameBuilder` xây DN, chuẩn bị `objectClass`/attributes rồi gọi `LdapTemplate.bind(...)`.
4. Thiết kế xử lý `409 Conflict`, `create-if-absent` và idempotency mà không che lỗi phân quyền, schema hoặc kết nối.
5. Hiểu race condition khi kiểm tra tồn tại trước khi tạo, cũng như trường hợp lệnh Add đã thành công nhưng ứng dụng không nhận được phản hồi.
6. Kiểm thử các lỗi phân biệt `68`, `32`, `50`, `65` và các trường hợp đồng thời.

## 2. “Already bound” nghĩa là gì trong LDAP?

LDAP lưu các entry trong cây thư mục. Mỗi entry có **distinguished name** (DN), là địa chỉ phân biệt nó với các entry khác trong cùng ngữ cảnh thư mục.

Ví dụ:

```text
dc=example,dc=org
└── ou=people
    ├── uid=an
    └── uid=binh
```

Nếu server đã lưu `uid=an,ou=people,dc=example,dc=org`, yêu cầu thêm một entry nữa tại **cùng DN** sẽ bị từ chối. Với LDAP Add, tình huống điển hình là:

```text
Ứng dụng
   │
   │ LDAP AddRequest
   │ DN = uid=an,ou=people,dc=example,dc=org
   ▼
LDAP server
   ├── DN chưa có; parent, schema, ACL hợp lệ → success (0)
   └── DN đã tồn tại                     → entryAlreadyExists (68)
                                              │
                                              ▼
                                    JNDI NameAlreadyBoundException
                                              │
                                              ▼
                                    Spring LDAP NameAlreadyBoundException
```

### 2.1. DN là điểm xung đột, không chỉ là giá trị `uid`

Hai DN dưới đây là **khác nhau**:

```text
uid=an,ou=people,dc=example,dc=org
uid=an,ou=contractors,dc=example,dc=org
```

Vì vậy, chúng có thể cùng tồn tại nếu cấu trúc thư mục và schema cho phép. LDAP **không mặc nhiên đảm bảo `uid` duy nhất trên toàn bộ cây thư mục**. Nếu ứng dụng đòi mỗi `uid` chỉ xuất hiện một lần trên nhiều OU, cần cơ chế duy nhất hóa phù hợp: quy tắc đặt DN, cơ chế kiểm tra/uniqueness do server hỗ trợ hoặc kho định danh có ràng buộc và đồng bộ đáng tin cậy. Một lần `search` trước khi Add không đủ đảm bảo ràng buộc toàn cục trong môi trường có nhiều writer.

Cũng không nên so sánh DN chỉ bằng `String.equals(...)`: cú pháp DN cho phép escaping, dạng biểu diễn tương đương và matching rule tùy schema/server. Sử dụng `javax.naming.ldap.LdapName` hoặc `LdapNameBuilder` và để server thực thi quy tắc tên.

### 2.2. Phân biệt LDAP authentication bind và `LdapTemplate.bind`

Từ *bind* có hai nghĩa dễ nhầm:

| Thao tác | Mục đích | Lỗi điển hình |
| --- | --- | --- |
| **LDAP BindRequest** | Xác thực danh tính bằng principal/DN và credential | `AuthenticationException`, thường mã LDAP `49` khi thông tin xác thực bị từ chối |
| **`LdapTemplate.bind(...)`** | Tạo một entry mới; phía LDAP thực hiện **AddRequest** | `NameAlreadyBoundException`, thường mã `68` khi DN đã tồn tại |

Đừng dùng `LdapTemplate.bind(...)` để xác minh mật khẩu; cũng đừng kết luận `NameAlreadyBoundException` là lỗi đăng nhập. Trước khi thực hiện Add, `ContextSource` có thể đã bind xác thực tài khoản dịch vụ. Lỗi ở bước kết nối/xác thực đó phải được phân loại riêng với lỗi tạo entry.

## 3. Hai lớp `NameAlreadyBoundException`

| Lớp | Phần của hệ | Checked/runtime | Cách xuất hiện |
| --- | --- | --- | --- |
| `javax.naming.NameAlreadyBoundException` | JNDI | **Checked**, kế thừa `javax.naming.NamingException` | Khi gọi `DirContext.bind` hoặc `createSubcontext` trực tiếp |
| `org.springframework.ldap.NameAlreadyBoundException` | Spring LDAP | **Runtime**, kế thừa `org.springframework.ldap.NamingException` | Khi `LdapTemplate` chuyển lỗi JNDI sang hệ Spring LDAP |
| `org.springframework.dao.DuplicateKeyException` | Spring DAO | **Runtime**, thuộc nhánh `DataIntegrityViolationException` | Nếu một adapter/framework dùng hợp đồng DAO và thực sự dịch lỗi trùng định danh sang lớp này |

Khi dùng `LdapTemplate`, cần bắt đúng **`org.springframework.ldap.NameAlreadyBoundException`**:

```java
import org.springframework.ldap.NameAlreadyBoundException;

try {
    ldapTemplate.bind(relativeDn, null, attributes);
} catch (NameAlreadyBoundException ex) {
    // DN đã tồn tại theo kết quả từ LDAP server.
}
```

Nếu viết code JNDI trực tiếp, loại cần bắt là `javax.naming.NameAlreadyBoundException`. Cơ chế chuyển đổi được Spring LDAP cung cấp qua `LdapUtils.convertLdapException(javax.naming.NamingException)`; nó không biến mọi lỗi LDAP thành `org.springframework.dao.DataAccessException`.

**Không suy luận từ tên lớp:** `NameAlreadyBoundException` không đồng nghĩa với `DuplicateKeyException`. Trong một ứng dụng có adapter DAO thống nhất, nhóm phát triển *có thể* chủ động ánh xạ hai loại, nhưng việc này phải là quyết định thiết kế rõ ràng và phải bảo toàn `cause`.

## 4. Tạo entry với `LdapTemplate.bind(...)`

Giả sử:

- `ContextSource` dùng base DN `dc=example,dc=org`.
- OU `ou=people,dc=example,dc=org` đã tồn tại.
- Tài khoản kỹ thuật của ứng dụng có quyền thêm entry trong OU đó.
- Server hỗ trợ schema `inetOrgPerson` (phù hợp với nhiều LDAP server, nhưng schema của Active Directory hoặc nhà cung cấp khác có thể yêu cầu objectClass và thuộc tính riêng).

Ví dụ tạo một người dùng bằng DN tương đối, đồng thời phân loại conflict:

```java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.SchemaViolationException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryPersonWriter {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void create(String uid, String commonName, String surname) {
        if (uid == null || uid.isBlank()
                || commonName == null || commonName.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException(
                    "uid, commonName và surname là bắt buộc");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        Attribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");

        Attributes attrs = new BasicAttributes(true);
        attrs.put(objectClasses);
        attrs.put("uid", uid);
        attrs.put("cn", commonName);
        attrs.put("sn", surname);

        try {
            // "bind" của Spring LDAP: LDAP AddRequest để TẠO entry.
            ldapTemplate.bind(dn, null, attrs);
        } catch (NameAlreadyBoundException ex) {
            throw new PersonAlreadyExistsException(
                    "Entry ở DN được yêu cầu đã tồn tại", ex);
        } catch (SchemaViolationException ex) {
            throw new IllegalStateException(
                    "Dữ liệu không đáp ứng schema LDAP", ex);
        } catch (NoPermissionException ex) {
            throw new IllegalStateException(
                    "Tài khoản ứng dụng không được phép tạo entry", ex);
        }
    }

    public static final class PersonAlreadyExistsException
            extends RuntimeException {
        public PersonAlreadyExistsException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Trong ứng dụng thực tế, có thể định nghĩa `PersonAlreadyExistsException` là một lớp riêng ở tầng miền, thay vì nested class như ví dụ. Tầng HTTP sẽ ánh xạ exception miền thành phản hồi phù hợp; mã bên trong tránh phụ thuộc trực tiếp vào HTTP.

### 4.1. Vì sao sử dụng `LdapNameBuilder`?

Ghép DN từ dữ liệu người dùng bằng chuỗi có thể sai khi `uid` chứa dấu phẩy, dấu cộng, dấu bằng hoặc các ký tự cần escape. `LdapNameBuilder` tạo RDN có escaping phù hợp:

```java
// Không nên:
String dn = "uid=" + uidFromRequest + ",ou=people";

// Nên:
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uidFromRequest)
        .build();
```

DN từ `LdapNameBuilder` cũng phải được kiểm tra theo quy tắc định danh của ứng dụng: escape đúng cú pháp **không thay thế** validation độ dài, character policy hoặc tính duy nhất theo nghiệp vụ.

### 4.2. DN tương đối và base DN

Với `ContextSource` base `dc=example,dc=org`, DN truyền vào `LdapTemplate.bind(...)` thường là **`uid=an,ou=people`**, tức DN tương đối với base. Nếu tự truyền cả `dc=example,dc=org` trong trường hợp API đã áp base, có thể tạo tên sai hoặc không tìm thấy parent.

Ngược lại, các API như `ContextSource.getContext(principal, credentials)` khi bind xác thực thường sử dụng **DN đầy đủ của principal** theo hợp đồng cụ thể. Luôn kiểm tra kiểu API và quy ước base của `ContextSource` thay vì dùng một biểu diễn DN cho mọi thao tác.

### 4.3. Schema và thuộc tính bắt buộc

Ví dụ dùng chuỗi objectClass:

```text
top → person → organizationalPerson → inetOrgPerson
```

Trong schema phổ biến, `person` yêu cầu `cn` và `sn`, còn `uid` có thể dùng làm RDN với `inetOrgPerson` nếu phù hợp cấu hình server. Khi thiếu thuộc tính bắt buộc hoặc vi phạm quy tắc schema, server có thể trả `objectClassViolation (65)` và Spring LDAP có thể ném `SchemaViolationException`.

**Không xử lý `SchemaViolationException` như một duplicate**. Nếu server không có objectClass hoặc giới hạn RDN khác, phải điều chỉnh mô hình entry cho đúng server. Với Active Directory, tạo đối tượng người dùng là một quy trình khác biệt về schema/attribute và không thể sao chép nguyên xi ví dụ `inetOrgPerson` rồi kết luận thao tác sẽ hoạt động.

## 5. Xung đột lúc tạo: không chỉ một kiểu

Khi gọi Add, những lỗi dưới đây dễ bị gộp sai thành “trùng người dùng”:

| LDAP result code / nhóm lỗi | Exception Spring LDAP thường gặp | Ý nghĩa thực tế | Hướng xử lý |
| --- | --- | --- | --- |
| `68` — `entryAlreadyExists` | `NameAlreadyBoundException` | DN đích đã được sử dụng | Xử lý conflict; kiểm tra nghiệp vụ và idempotency |
| `32` — `noSuchObject` | `NameNotFoundException` | Parent DN hoặc phần cây cần thiết không tồn tại | Kiểm tra OU, base DN, thứ tự provisioning |
| `50` — `insufficientAccessRights` | `NoPermissionException` | Bind identity không có quyền Add | Sửa ACL hoặc tài khoản kỹ thuật |
| `65` — `objectClassViolation` | `SchemaViolationException` | Sai `objectClass` hoặc thiếu thuộc tính bắt buộc | Sửa schema/payload |
| `19` / `21` — constraint/syntax | `InvalidAttributeValueException` | Giá trị attribute vi phạm ràng buộc | Sửa/validate giá trị |
| `34` — invalid DN syntax | `InvalidNameException` | DN không hợp lệ | Dùng bộ dựng DN và kiểm tra input |
| `49` — invalid credentials | `AuthenticationException` | Không bind được tài khoản dùng để thao tác | Kiểm tra principal/credential và account policy |
| Lỗi socket, TLS hoặc server không sẵn sàng | `CommunicationException` / `ServiceUnavailableException` | Không thể xác nhận kết quả Add một cách chắc chắn | Kiểm tra kết nối và trạng thái trước retry |

Cùng một thao tác có thể vi phạm nhiều điều kiện, chẳng hạn DN đã tồn tại và tài khoản không có quyền Add. **Server quyết định mã lỗi thực tế** theo kiểm tra và chính sách của nó. Không được giả định tất cả server đều ưu tiên trả `68` trong mọi tình huống.

### 5.1. `68` và `32` là hai hướng xử lý trái ngược

```text
Add uid=an,ou=people,dc=example,dc=org
         │
         ├── ou=people chưa tồn tại
         │      └── noSuchObject (32), thường NameNotFoundException
         │
         └── ou=people tồn tại
                ├── uid=an chưa có → có thể tạo nếu schema/ACL hợp lệ
                └── uid=an đã có  → entryAlreadyExists (68)
```

Không nên tạo parent tự động khi nhận `32` trừ khi workflow provisioning có quyền và chính sách tạo container rõ ràng. Cũng không nên xóa entry hiện có để “giải quyết” `68`; entry có thể thuộc một người dùng hoặc quy trình khác.

### 5.2. Conflict khi đổi DN

Ngoài Add, việc đổi tên hoặc chuyển một entry bằng `rename(oldDn, newDn)` có thể gặp xung đột nếu **DN đích đã tồn tại**. Server có thể trả mã `68`. Trường hợp DN nguồn hoặc parent đích không tồn tại lại liên quan mã `32`. Cần xem cả DN nguồn và DN đích, không mặc định mọi `NameAlreadyBoundException` đều đến từ thao tác tạo mới.

## 6. Kiểm tra tồn tại trước khi tạo có đủ không?

Một cách viết thường thấy là:

```text
1. lookup("uid=an,ou=people")  → không có
2. bind("uid=an,ou=people")    → tạo mới
```

Cách này có thể giúp hiển thị thông tin sớm, nhưng **không đảm bảo tránh xung đột** vì có race condition (*time-of-check to time-of-use*, TOCTOU).

```text
Thời điểm      Request A                      Request B
────────      ─────────                      ─────────
T1            lookup(uid=an) → chưa có
T2                                           lookup(uid=an) → chưa có
T3            LDAP Add(uid=an) → success (0)
T4                                           LDAP Add(uid=an) → 68
T5            Trả created                     Trả conflict
```

Cả hai request đều nhìn thấy “chưa tồn tại”, nhưng chỉ một Add có thể thành công tại cùng DN. Vì vậy:

- **Quyết định cuối cùng phải dựa trên kết quả của LDAP Add**, không chỉ trên kết quả `lookup` hoặc `search` trước đó.
- Bắt `NameAlreadyBoundException` là hành vi dự kiến trong hệ thống có nhiều request hoặc nhiều instance cùng tạo dữ liệu.
- Không dựa vào `synchronized` trong một JVM để bảo vệ toàn cục: ứng dụng có thể chạy nhiều instance, hoặc có writer khác ngoài ứng dụng.
- Nếu cần uniqueness **theo thuộc tính `uid` trên nhiều OU**, Add cùng DN không đảm bảo yêu cầu đó. Cần thiết kế chính sách duy nhất hóa ở cấp phù hợp.

Một bước precheck vẫn có ích để giảm số request không cần thiết và đưa ra thông điệp rõ ràng; tuy nhiên phải có xử lý `68` **ngay tại lệnh tạo thực tế**.

## 7. Thiết kế hai hợp đồng: create-only và create-if-absent

Cùng một lỗi `NameAlreadyBoundException` có thể được xử lý khác nhau, tùy yêu cầu nghiệp vụ. Hai hợp đồng sau cần được phân biệt rõ.

### 7.1. Create-only: entry tồn tại là conflict

Ví dụ một endpoint `POST /people` với định danh `uid` do client chọn:

1. Khi tạo thành công: trả **`201 Created`** và tham chiếu đến tài nguyên mới.
2. Khi DN đã tồn tại, không rõ có phải cùng một ý định tạo hay không: trả **`409 Conflict`**.
3. Không tự động trả `201` khi nhận `68`; thực tế yêu cầu hiện tại có thể chưa tạo gì.

Một lớp controller có thể nhận `PersonAlreadyExistsException` từ service và ánh xạ thành `409`. Không trả nguyên thông báo LDAP hoặc DN nhạy cảm:

```json
{
  "code": "PERSON_ALREADY_EXISTS",
  "message": "Định danh người dùng đã được sử dụng",
  "requestId": "req-7f2a"
}
```

`requestId` là ví dụ của mã theo dõi request, không chứa password, DN đầy đủ hoặc thông tin định danh không cần công bố. Chỉ trả chi tiết conflict khi người gọi có quyền biết; trong một số luồng đăng ký tài khoản, thông điệp quá cụ thể có thể hỗ trợ dò sự tồn tại của người dùng.

### 7.2. Create-if-absent: entry tồn tại có thể là kết quả hợp lệ

Một tiến trình đồng bộ định kỳ có thể yêu cầu **“đảm bảo entry tồn tại”** thay vì “phải tạo mới”:

```java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.core.LdapTemplate;

public final class DirectoryCreateIfAbsent {
    private final LdapTemplate ldapTemplate;

    public DirectoryCreateIfAbsent(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public enum Outcome { CREATED, ALREADY_PRESENT }

    public Outcome ensureCreated(Name dn, Attributes attributes) {
        try {
            ldapTemplate.bind(dn, null, attributes);
            return Outcome.CREATED;
        } catch (NameAlreadyBoundException ex) {
            // Chỉ phù hợp khi yêu cầu thực sự là "có entry ở DN này".
            // Chưa khẳng định nội dung hiện có giống nội dung yêu cầu.
            return Outcome.ALREADY_PRESENT;
        }
    }
}
```

Đoạn mã này **không xác minh nội dung của entry hiện có**. Chỉ nên dùng khi hợp đồng thực sự chấp nhận *bất kỳ entry hợp lệ nào tại DN đó* hoặc khi có bước kiểm tra/đối chiếu riêng.

Nếu nghiệp vụ cần đảm bảo cùng một người và cùng dữ liệu, phải đọc lại và **so sánh các trường định danh/thuộc tính có ý nghĩa**; đồng thời kiểm tra quyền sở hữu và nguồn tạo. Hai entry có cùng `uid` hoặc cùng `cn` chưa chắc đại diện cùng một yêu cầu. Đừng ghi đè dữ liệu hiện có để làm cho chúng “giống nhau” nếu caller không có quyền cập nhật.

### 7.3. Xây idempotency thực sự

**Idempotency** nghĩa là thực hiện lặp lại **cùng một yêu cầu hợp lệ** không tạo tác dụng phụ trùng lặp ngoài tác dụng của lần đầu. Điều đó **không đồng nghĩa** rằng mọi `NameAlreadyBoundException` có thể được coi là thành công.

Có hai tình huống:

- **Gửi lại cùng request:** Client timeout, gửi lại một `POST` với cùng idempotency key và cùng payload. Nếu hệ thống có cơ chế lưu trạng thái request/key nhất quán, có thể trả lại kết quả của lần tạo đầu tiên.
- **Hai request khác nhau dùng cùng DN:** Hai actor có payload hoặc quyền sở hữu khác nhau. Đây có thể là xung đột thật; không được coi là thành công chỉ vì DN đã xuất hiện.

Một thiết kế bền vững thường dùng:

```text
Client request + idempotency key
                 │
                 ▼
Kiểm tra key với kho trạng thái nhất quán
                 │
        ┌────────┴────────┐
    Đã xử lý          Chưa xử lý
        │                 │
  Trả lại kết quả      Ghi nhận request
  đã biết             và thực hiện LDAP Add
                          │
                   ┌──────┴───────┐
                 success          68
                   │               │
            Lưu kết quả       Xác minh trạng thái/
            theo key          phân biệt conflict
```

Việc lưu key và tạo LDAP entry thường **không có transaction ACID chung**. Do đó, kiến trúc phải xử lý trạng thái “đã tạo LDAP nhưng chưa lưu kết quả request” bằng đối soát hoặc workflow bù trừ phù hợp. Không hứa exactly-once chỉ bằng một kho key đơn giản nếu hai hệ thống không có cơ chế phối hợp nhất quán.

Nếu không có nhu cầu xử lý request lặp lại phức tạp, bắt `68` và trả `409` là lựa chọn rõ ràng hơn cho API create-only.

## 8. Lỗi mạng sau Add: đừng retry mù quáng

Trường hợp khó nhất không phải server chủ động trả `68`, mà là **ứng dụng gửi Add xong rồi mất kết nối trước khi nhận phản hồi**:

```text
Ứng dụng                       LDAP server
    │                               │
    ├────── Add(uid=an) ───────────>│
    │                               ├─ Tạo entry thành công
    │<───── phản hồi bị mất ─────────X
    │
    ├─ CommunicationException
    │
    └─ Nếu gửi lại Add(uid=an) ─────> 68 (đã tồn tại)
```

Một `CommunicationException` hoặc timeout **không chứng minh** server chưa tạo entry. Nếu retry ngay, lần hai có thể nhận `NameAlreadyBoundException`. Khi đó vẫn chưa đủ cơ sở để khẳng định entry hiện có là kết quả của request đầu tiên: cũng có thể một writer khác đã tạo cùng DN.

Cách xử lý an toàn:

1. Phân loại thao tác đã **gửi** hay lỗi phát sinh **trước khi gửi**; không phải lúc nào ứng dụng cũng biết chắc.
2. Khi kết quả không xác định, đọc lại trạng thái DN nếu có quyền, theo đúng cơ chế nhất quán/replication mà hệ thống hỗ trợ.
3. Đối chiếu thông tin định danh, ownership, version hoặc idempotency key đáng tin cậy (nếu mô hình dữ liệu hỗ trợ).
4. Nếu xác định chắc là chính yêu cầu trước đã tạo entry, có thể trả kết quả thành công nhất quán theo hợp đồng.
5. Nếu dữ liệu khác hoặc không thể chứng minh nguồn gốc, xử lý conflict hoặc trạng thái cần đối soát; tránh ghi đè im lặng.

Đặc biệt, **LDAP read trên replica khác** có thể tạm thời chưa nhìn thấy entry vừa được tạo do replication lag. Việc lookup thấy “chưa có” ngay sau timeout không bảo đảm lần Add trước thất bại. Chính sách retry cần xem khả năng đọc-sau-ghi, định tuyến server và thời hạn chờ.

### 8.1. Khi nào retry hợp lý?

| Tình huống | Retry nguyên lệnh Add? | Giải thích |
| --- | --- | --- |
| Server trả `68` rõ ràng | **Không** | DN đã tồn tại; đây là conflict hoặc trạng thái đã có |
| Server trả `32` vì thiếu parent DN | **Không** | Phải sửa cây thư mục hoặc quy trình provisioning |
| Server trả `65` vì schema sai | **Không** | Cần sửa payload hoặc schema |
| Server trả `50` vì thiếu quyền | **Không** | Cần xử lý ACL/identity |
| Lỗi kết nối **trước khi gửi** và được xác nhận không có tác dụng phụ | Có điều kiện | Retry giới hạn, có backoff/timeout |
| Mất kết nối **sau khi gửi** hoặc không biết server đã nhận chưa | Không tự động | Cần xác minh trạng thái/idempotency trước |
| Cùng request được gửi lại với key đã hoàn tất | Không thực hiện Add mới | Trả kết quả được ghi nhận theo idempotency key |

Không cấu hình retry vô hạn cho `NameAlreadyBoundException`. Một lỗi xác định là duplicate sẽ không được sửa bằng việc lặp lại cùng Add.

## 9. Chẩn đoán conflict trong vận hành

Một thông điệp như `LDAP: error code 68 - entryAlreadyExists` chỉ là điểm bắt đầu. Hãy phân tích có thứ tự:

1. **Xác định thao tác thực tế:** Add hay rename; thao tác auth bind không phải Add.
2. **Xác nhận loại exception:** `javax.naming.NameAlreadyBoundException` (JNDI) hay `org.springframework.ldap.NameAlreadyBoundException` (Spring LDAP).
3. **Kiểm tra server và base DN:** host/port, OU, `ContextSource` base, DN tương đối hay tuyệt đối, replication và referral. DN bị ghép sai có thể gây lỗi ở vị trí khác dự kiến.
4. **Xem định danh nghiệp vụ:** `uid`, key nội bộ, source system, ai sở hữu DN. Trùng DN ở một OU không nhất thiết chứng minh trùng định danh trên toàn bộ hệ thống.
5. **Kiểm tra tính đồng thời:** có nhiều request, batch provisioning, scheduler hay nhiều instance cùng tạo entry không?
6. **Xác định khả năng request lặp lại:** client timeout, gateway retry, message broker redelivery hoặc workflow retry sau sự cố?
7. **Đưa ra quyết định:** `409`, `ALREADY_PRESENT` theo hợp đồng, đối soát idempotency, hoặc điều chỉnh cơ chế tạo/routing.

Nên ghi log có cấu trúc: `operation=ldap-add`, loại exception, LDAP resultCode nếu có, hệ thống thư mục, id request, thời gian và trạng thái retry/đối soát. **Không log password, token, bind secret, thuộc tính nhạy cảm hoặc nguyên vẹn DN chứa PII nếu không cần thiết.** Nếu cần truy vết DN, dùng ID nội bộ hoặc giá trị đã che theo chính sách.

### 9.1. Conflict do DN hay do uniqueness theo thuộc tính?

Một LDAP server có thể được cấu hình plugin/overlay hoặc ràng buộc riêng buộc một thuộc tính như `uid` duy nhất trên một phạm vi. Khi vi phạm cơ chế đó, mã lỗi **có thể khác `68`**, tùy implementation và quy tắc server. Không nên xây logic dựa trên giả định rằng mọi xung đột `uid` đều trả `NameAlreadyBoundException`.

**Thiết kế phạm vi uniqueness từ đầu:** nếu dùng `uid` làm RDN dưới một OU cố định, xung đột cùng `uid` trong OU đó sẽ thành xung đột DN. Nếu tồn tại nhiều OU, hãy quy định cơ chế nhận diện toàn cục khác hoặc có constraint ở server/kho đáng tin cậy.

### 9.2. Conflict và quyền truy cập

Không được dùng một account có quyền cao để tự động ghi đè entry do account khác tạo chỉ để xử lý lỗi `68`. ACL vẫn phải được thực thi đối với cập nhật hoặc xóa. Ngoài ra, người gọi HTTP không nhất thiết được phép biết rằng một username hoặc DN cụ thể đã tồn tại. Với API đăng ký công khai, phản hồi có thể cần trung tính để giảm nguy cơ enumeration; tầng nội bộ vẫn phân loại conflict chính xác.

TLS/StartTLS và pooling vẫn phải được cấu hình an toàn. Lỗi chứng chỉ không phải duplicate, còn tái sử dụng sai context xác thực giữa request có thể làm thao tác Add chạy dưới danh tính không mong muốn.

## 10. Kiểm thử đúng hành vi conflict

Unit test hữu ích để xác minh service map đúng exception và không che các lỗi khác. Integration test với LDAP server hoặc môi trường test cô lập giúp kiểm tra behavior thật của server, schema, ACL, DN normalization và concurrency.

| Ca kiểm thử | Hành vi mong đợi |
| --- | --- |
| Tạo DN mới, schema/ACL hợp lệ | Add thành công; xác minh entry có mặt |
| Tạo lại **cùng DN** | Nhận `NameAlreadyBoundException` hoặc kết quả conflict tương đương |
| Hai request tạo đồng thời cùng DN | Tối đa một Add thành công trên server; request còn lại nhận conflict |
| Cùng `uid` trong hai OU khác nhau | Không mặc định xem là trùng DN; tùy chính sách uniqueness của server/ứng dụng |
| Tạo entry dưới OU chưa tồn tại | Lỗi parent thiếu (thường `NameNotFoundException`), không nhầm `68` |
| Tạo entry thiếu `cn` / `sn` trong schema yêu cầu | Lỗi schema/validation; không retry mù quáng |
| Tạo entry bằng tài khoản thiếu quyền | Lỗi ACL; không trả “người dùng đã tồn tại” |
| Credential tài khoản kỹ thuật không hợp lệ | Lỗi xác thực/kết nối; không nhầm với Add conflict |
| Create-only gặp `68` | Trả exception miền/conflict phù hợp; không ghi đè entry |
| Create-if-absent gặp `68` | Chỉ chấp nhận `ALREADY_PRESENT` theo hợp đồng; đối chiếu khi cần |
| Timeout sau Add thành công | Đối soát trạng thái, không phát lại lệnh ghi vô điều kiện |
| Retry request với idempotency key khác | Không gộp hai ý định tạo chỉ vì payload giống nhau |

### 10.1. Ví dụ unit test cho chính sách create-only

Dùng Mockito minh họa rằng **exception Spring LDAP được bắt và chuyển thành lỗi miền**; các exception LDAP khác vẫn đi qua. Ví dụ bỏ qua phần khởi tạo và import chung của JUnit/Mockito:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

import javax.naming.Name;
import javax.naming.directory.Attributes;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.core.LdapTemplate;

class DirectoryPersonWriterTest {
    @Test
    void duplicateDnIsMappedToDomainConflict() {
        LdapTemplate template = mock(LdapTemplate.class);
        // LdapTemplate.bind(...) trả void trong API sử dụng ở ví dụ.
        doThrow(new NameAlreadyBoundException(
                new javax.naming.NameAlreadyBoundException("Entry already exists")))
                .when(template)
                .bind(any(Name.class), isNull(), any(Attributes.class));

        DirectoryPersonWriter writer = new DirectoryPersonWriter(template);

        assertThrows(
                DirectoryPersonWriter.PersonAlreadyExistsException.class,
                () -> writer.create("an", "An Nguyen", "Nguyen")
        );
    }
}
```

Unit test trên không kiểm chứng atomicity ở LDAP server; điều đó cần integration test với **hai tác vụ Add đồng thời** và xác nhận số entry thực tế sau khi hoàn thành. Không tạo LDAP entry trên thư mục sản xuất để thử lỗi `68`.

## 11. Bài tập thực hành

Giả sử hệ thống có `ou=people` và `ou=contractors`. Hai tiến trình đồng thời nhận yêu cầu tạo `uid=lan`:

**Bài tập 1 — Nhận diện loại conflict.** Tiến trình A Add `uid=lan,ou=people` thành công, B Add cùng DN nhận `68`. Hãy xác định exception JNDI và Spring LDAP tương ứng.

**Đáp án gợi ý:** `javax.naming.NameAlreadyBoundException` được Spring LDAP chuyển thành `org.springframework.ldap.NameAlreadyBoundException`.

**Bài tập 2 — Phạm vi duy nhất.** Nếu B thêm `uid=lan,ou=contractors`, liệu bắt buộc có `68` không?

**Đáp án gợi ý:** Không. Hai DN khác nhau. Nếu hệ thống cấm trùng `uid` trên nhiều OU, cần cơ chế uniqueness riêng theo phạm vi nghiệp vụ.

**Bài tập 3 — Precheck và race.** Cả A/B đều lookup thấy DN chưa tồn tại. Vì sao B vẫn có thể nhận `68`?

**Đáp án gợi ý:** Kết quả kiểm tra trở nên cũ trước khi B Add; server xử lý Add trên trạng thái hiện tại.

**Bài tập 4 — Phân biệt `32` và `68`.** Thêm `uid=lan,ou=missing` khi `ou=missing` chưa tồn tại sẽ là conflict DN đã có hay thiếu parent?

**Đáp án gợi ý:** Thường là thiếu parent (`noSuchObject` / `NameNotFoundException`), không phải `NameAlreadyBoundException`.

**Bài tập 5 — Mất phản hồi sau Add.** Client timeout, gửi lại cùng request và nhận `68`. Có thể lập tức trả “đã tạo thành công trước đó” không?

**Đáp án gợi ý:** Không tự động; phải xác minh trạng thái, nguồn gốc và idempotency của request để tránh nhận nhầm entry do writer khác tạo.

**Bài tập 6 — Xử lý HTTP.** Vì sao một endpoint public signup có thể không trả thông điệp “uid=lan đã tồn tại” dù backend phát hiện `68`?

**Đáp án gợi ý:** Phản hồi quá chi tiết có thể cho phép dò tài khoản; cần tuân thủ chính sách bảo mật và hợp đồng API, trong khi backend vẫn giữ chẩn đoán chính xác.

## 12. Những sai lầm phổ biến

1. **Nhầm `LdapTemplate.bind` với bind xác thực.** Một API là LDAP Add, còn authentication bind kiểm tra credential.
2. **Chỉ kiểm tra tồn tại trước khi tạo.** Race condition vẫn có thể phát sinh `68`.
3. **Coi mọi `uid` giống nhau là cùng DN.** DN còn phụ thuộc OU và nhánh thư mục.
4. **Bắt `org.springframework.dao.DuplicateKeyException` quanh `LdapTemplate`** rồi tưởng đã xử lý hết lỗi `68`. Spring LDAP thông thường ném `org.springframework.ldap.NameAlreadyBoundException`.
5. **Gặp `68` thì update hoặc delete entry hiện có.** Có thể làm mất dữ liệu của actor khác.
6. **Gặp `68` thì trả thành công mà không đối soát.** Duplicate chưa chứng minh request trước đã thành công.
7. **Mất kết nối sau Add thì retry ngay.** Server có thể đã xử lý, nên phải kiểm tra trạng thái.
8. **Gộp `32`, `50`, `65` thành lỗi duplicate.** Đó là các nhóm lỗi khác nhau về parent, ACL và schema.
9. **Ghép DN bằng chuỗi thô từ input.** Dễ sai escaping hoặc mở ra nguy cơ injection.
10. **Log toàn bộ DN, credential và diagnostic message.** Có thể làm lộ dữ liệu người dùng và cấu trúc thư mục.

## 13. Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): quy tắc Add/ModifyDN, resultCode `entryAlreadyExists (68)`, `noSuchObject (32)` và các mã lỗi.
- [Java SE API — `javax.naming.NameAlreadyBoundException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/NameAlreadyBoundException.html): exception checked của JNDI khi tên đã được bind.
- [Spring LDAP API — `NameAlreadyBoundException`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/NameAlreadyBoundException.html): runtime exception của Spring LDAP.
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `bind`, `lookup`, `rename`, chuyển đổi exception.
- [Spring LDAP API — `LdapNameBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): tạo DN từ RDN được escape.
- [Spring LDAP API — `LdapUtils`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapUtils.html): chuyển `javax.naming.NamingException` sang exception Spring LDAP.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): cấu hình `ContextSource`, thao tác với `LdapTemplate`, tìm kiếm và ODM.

**Ghi nhớ:** `NameAlreadyBoundException` là tín hiệu điển hình khi **DN đích đã tồn tại** trong một yêu cầu Add hoặc đổi DN. Server có thẩm quyền quyết định xung đột tại thời điểm ghi; precheck không thay thế việc bắt exception. Khi chuyển lỗi thành `409 Conflict`, `ALREADY_PRESENT` hoặc kết quả idempotent, phải dựa trên hợp đồng nghiệp vụ và bằng chứng về trạng thái thật, đặc biệt sau lỗi mạng hoặc request được gửi lặp lại.
