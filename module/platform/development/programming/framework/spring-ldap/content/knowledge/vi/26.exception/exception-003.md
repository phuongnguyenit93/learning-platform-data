# AuthenticationException, InvalidDataAccessApiUsageException và lỗi bind

Khi dùng **Spring LDAP**, chữ *bind* xuất hiện ở hai thao tác khác nhau: **bind để xác thực một danh tính với LDAP server** và **bind để thêm một entry vào cây thư mục**. Chúng có mục đích, tham số và nhóm lỗi khác nhau. Bên cạnh đó, tên `AuthenticationException` tồn tại trong JNDI, Spring LDAP và Spring Security, còn `InvalidDataAccessApiUsageException` lại thuộc hệ Spring DAO. Nếu chỉ nhìn tên lớp mà không kiểm tra package, ứng dụng dễ xử lý sai lỗi đăng nhập, che giấu sự cố kết nối hoặc thử lại một lệnh ghi đã thành công.

Bài thuộc chương **Exception** của module **SPRING_LDAP**, tập trung vào phân loại lỗi xác thực và lỗi bind khi dùng `ContextSource`, `LdapTemplate`, `LdapClient` hoặc ODM, liên hệ với DN, schema, filter, TLS, pooling và kiểm thử truy cập thư mục an toàn.

Sau bài này, người học có thể:

- Phân biệt `javax.naming.AuthenticationException`, `org.springframework.ldap.AuthenticationException`, `org.springframework.security.core.AuthenticationException` và `org.springframework.dao.InvalidDataAccessApiUsageException`.
- Phân biệt **authentication bind** (kiểm tra principal/mật khẩu) với `LdapTemplate.bind(...)` (tạo entry).
- Nhận diện các mã LDAP như `49`, `50`, `68`; xác định đâu là lỗi mật khẩu, quyền, schema, DN, kết nối hoặc cách dùng API.
- Thiết kế xử lý lỗi, trả phản hồi, retry và log an toàn mà không nhầm “đăng nhập thất bại” với “LDAP không hoạt động”.

## 1. Đọc đúng package trước khi bắt exception

### 1.1. Ba lớp mang tên `AuthenticationException`

| Lớp | Nguồn | Đặc điểm | Khi nào gặp |
| --- | --- | --- | --- |
| `javax.naming.AuthenticationException` | JNDI / Java Naming and Directory Interface | **Checked exception**; kế thừa `javax.naming.NamingException` | Code dùng `DirContext` trực tiếp, hoặc nguyên nhân gốc do LDAP provider tạo ra khi bind thất bại |
| `org.springframework.ldap.AuthenticationException` | Spring LDAP | **Runtime exception**; kế thừa `org.springframework.ldap.NamingException` | `ContextSource`, `LdapTemplate` và các API Spring LDAP chuyển đổi lỗi JNDI |
| `org.springframework.security.core.AuthenticationException` | Spring Security | **Runtime exception**; là lớp cha của những lỗi xác thực ở tầng Security, ví dụ `BadCredentialsException` | Filter, authentication manager/provider, Spring Security LDAP tích hợp với ứng dụng |

Hai lớp đầu đại diện cho lỗi ở tầng thư mục; lớp thứ ba là hợp đồng lỗi ở tầng xác thực bảo mật của ứng dụng. Một `AuthenticationException` của Spring LDAP **không tự động** là `AuthenticationException` của Spring Security. Chỉ khi một thành phần tích hợp hoặc code ứng dụng chuyển đổi, tầng Security mới nhận loại lỗi tương ứng.

Trong Java, hai import sau không thể cùng dùng tên đơn `AuthenticationException` trong một file:

```java
// Đây là hai kiểu khác nhau:
javax.naming.AuthenticationException jndiError;
org.springframework.ldap.AuthenticationException ldapError;

// Và đây là kiểu thứ ba, thuộc Spring Security:
org.springframework.security.core.AuthenticationException securityError;
```

Khi truy vết stack trace, hãy xem **fully qualified class name**, thao tác đang chạy và `cause`; không nên kết luận chỉ từ phần tên `AuthenticationException`.

### 1.2. `InvalidDataAccessApiUsageException` nằm ở đâu?

`org.springframework.dao.InvalidDataAccessApiUsageException` là subclass của `NonTransientDataAccessException`, thuộc hệ `DataAccessException` của **Spring DAO**. Ý nghĩa của nó là **bên gọi sử dụng API truy cập dữ liệu không đúng hợp đồng**, chẳng hạn truyền tham số trái điều kiện tiên quyết của một API/adapter cụ thể.

Đặt cạnh hệ exception LDAP:

```text
java.lang.Exception
└── javax.naming.NamingException                         (JNDI, checked)
    └── javax.naming.AuthenticationException

java.lang.RuntimeException
├── org.springframework.core.NestedRuntimeException
│   ├── org.springframework.ldap.NamingException
│   │   ├── org.springframework.ldap.AuthenticationException
│   │   ├── org.springframework.ldap.NameNotFoundException
│   │   ├── org.springframework.ldap.CommunicationException
│   │   └── ...
│   └── org.springframework.dao.DataAccessException
│       └── NonTransientDataAccessException
│           └── InvalidDataAccessApiUsageException
└── org.springframework.security.core.AuthenticationException
    └── BadCredentialsException
```

Sơ đồ cho thấy **`org.springframework.ldap.AuthenticationException` không phải subclass của `DataAccessException`**. Vì vậy, đoạn mã sau không phải là bộ xử lý lỗi bind chung:

```java
try {
    ldapTemplate.lookup("uid=an,ou=people");
} catch (org.springframework.dao.InvalidDataAccessApiUsageException ex) {
    // Không bắt được org.springframework.ldap.AuthenticationException
    // hoặc org.springframework.ldap.CommunicationException thông thường.
}
```

**Nguyên tắc:** nếu API hiện tại sử dụng Spring LDAP trực tiếp, ưu tiên các exception trong `org.springframework.ldap.*`. Chỉ bắt `InvalidDataAccessApiUsageException` khi một thành phần thực sự ném loại đó (ví dụ adapter DAO do ứng dụng viết hoặc một API Spring Data có hợp đồng tương ứng). Không được mặc định coi lỗi LDAP `49` là “invalid data access API usage”.

## 2. Hai nghĩa của “bind” trong LDAP

| Tiêu chí | Bind để **xác thực** | Bind để **tạo entry** |
| --- | --- | --- |
| Mục tiêu | Thiết lập danh tính cho kết nối LDAP | Thêm một entry mới vào cây thư mục |
| Giao thức LDAP | **BindRequest** | **AddRequest** |
| Tham số chính | Principal/bind DN, credential, phương thức xác thực | DN mới, objectClass, các attribute |
| API thường gặp | `ContextSource.getContext(principal, credentials)`; `LdapTemplate.authenticate(...)` | `LdapTemplate.bind(dn, obj, attrs)` |
| Thành công | Server chấp nhận danh tính hoặc `authenticate(...)` trả `true` | Entry được tạo tại DN chỉ định |
| Lỗi điển hình | `AuthenticationException`; lỗi phương thức bind; TLS/mạng | `NameAlreadyBoundException`; `SchemaViolationException`; `NoPermissionException`; lỗi DN |

> Tên phương thức `LdapTemplate.bind(...)` dễ gây hiểu nhầm: nó tạo entry theo LDAP Add, **không dùng để kiểm tra mật khẩu người dùng**. Ngược lại, bind xác thực có thể diễn ra khi khởi tạo `ContextSource` hoặc khi tìm/kiểm tra người dùng, dù ứng dụng không gọi phương thức tên `bind`.

### 2.1. Luồng đăng nhập thường gặp

```text
Client gửi username + password
                 │
                 ▼
Ứng dụng từ chối password rỗng, kiểm tra input
                 │
                 ▼
Kết nối tìm kiếm bằng tài khoản dịch vụ (nếu dùng search-before-bind)
                 │
                 ▼
Tìm DN người dùng bằng filter đã escape
                 │
                 ▼
Thử bind xác thực bằng DN người dùng + password
            ┌────┴─────┐
          Đúng         Sai
            │            │
        Xác thực     Không xác thực
        thành công    (thông điệp chung)
```

Kết quả này còn phụ thuộc chính sách tài khoản, quyền search, TLS và tình trạng kết nối. **Không tìm được DN** không nhất thiết chứng minh sai mật khẩu: tài khoản dịch vụ có thể không thấy entry do ACL, hoặc search base/filter bị cấu hình sai.

### 2.2. Luồng tạo entry

```text
Service với quyền ghi vào OU
             │
             ▼
Tạo DN tương đối + objectClass + attributes
             │
             ▼
LdapTemplate.bind(dn, null, attrs)
             │
             ▼
Server xử lý LDAP AddRequest
       ┌─────┼───────────┐
       │     │           │
    Thành   DN đã      Schema / ACL /
     công   tồn tại    parent DN sai
```

Khi `bind(...)` tạo entry bị từ chối, lỗi thường là vấn đề **ràng buộc dữ liệu, DN hoặc quyền**, không phải sai mật khẩu của người dùng mới. Nếu tài khoản dịch vụ đã không thể xác thực khi mở kết nối, yêu cầu Add thậm chí chưa tới bước kiểm tra schema.

## 3. `AuthenticationException` và lỗi của authentication bind

### 3.1. LDAP result code `49`: Invalid Credentials

LDAP server thường trả mã `49` khi bind không được chấp nhận; JNDI thường ánh xạ thành `javax.naming.AuthenticationException`, rồi Spring LDAP chuyển thành `org.springframework.ldap.AuthenticationException`. Tuy nhiên, *invalid credentials* không luôn có nghĩa duy nhất là “nhập sai mật khẩu”.

Nguyên nhân có thể bao gồm:

- Bind DN hoặc thông tin xác thực không đúng.
- Tài khoản bị khóa, vô hiệu hóa, hết hạn hoặc chịu chính sách đăng nhập của server.
- Cấu hình danh tính chưa đúng OU/DN hoặc đang bind bằng tài khoản dịch vụ sai secret.
- Một số trường hợp máy chủ như Active Directory bổ sung mã chẩn đoán riêng cho trạng thái tài khoản. **Các mã phụ này không phải chuẩn LDAP dùng chung** và không nên đem nguyên văn ra API công khai.

Việc phân biệt cần dựa vào **ngữ cảnh bind**:

| Ngữ cảnh | Khi gặp `AuthenticationException` | Cách xử lý |
| --- | --- | --- |
| Bind người dùng cuối để kiểm tra mật khẩu | Thử xác thực không thành công | Trả phản hồi trung tính, không lộ tài khoản có tồn tại |
| Bind tài khoản dịch vụ để search/update | Secret hoặc DN cấu hình hạ tầng có vấn đề | Cảnh báo vận hành, cập nhật cấu hình/secret; không quy cho người dùng cuối |
| Bind phát sinh trong Spring Security LDAP | Lỗi có thể được provider dịch sang exception Security | Kiểm tra loại exception tại ranh giới authentication manager và chính sách phản hồi |

Mã `49` **không nên được retry liên tục** với cùng username/password: vừa không sửa được dữ liệu xác thực, vừa dễ kích hoạt khóa tài khoản hoặc tăng tải vô ích.

### 3.2. Những exception khác liên quan đến xác thực

| Lớp / nhóm lỗi Spring LDAP | Mã LDAP thường gặp | Ý nghĩa vận hành |
| --- | --- | --- |
| `AuthenticationException` | `49` | Credential hoặc chính sách tài khoản làm bind thất bại |
| `AuthenticationNotSupportedException` | `7`, `8`, `13`, `48` tùy tình huống/provider | Phương thức xác thực không được hỗ trợ; cần auth mạnh hơn hoặc kênh được bảo vệ |
| `CommunicationException` | Không nhất thiết có LDAP code | Lỗi socket, DNS, TLS, kết nối bị đóng; có thể chưa nhận phản hồi từ server |
| `ServiceUnavailableException` | `51` hoặc `52` trong các trường hợp server trả về | Máy chủ bận hoặc không sẵn sàng |
| `NameNotFoundException` | `32` | DN/search base không tồn tại; không đồng nghĩa mật khẩu sai |
| `NoPermissionException` | `50` | Bind có thể đã thành công, nhưng danh tính hiện tại không đủ quyền search/đọc/sửa |
| `InvalidNameException` | `34` | DN không đúng cú pháp; lỗi cách xây DN hoặc dữ liệu đầu vào |

Các ánh xạ là **điển hình**, có thể thay đổi theo server, provider và giai đoạn lỗi. Ví dụ TLS certificate không tin cậy có thể biểu hiện bằng `CommunicationException` bọc một nguyên nhân SSL; không có LDAP resultCode vì kênh chưa thiết lập xong.

### 3.3. Phân biệt “sai mật khẩu” với lỗi “không thể xác thực”

Một API đăng nhập có ít nhất ba trạng thái nội bộ:

1. **Được chấp nhận:** server xác nhận mật khẩu/danh tính.
2. **Bị từ chối:** server trả kết quả xác thực không thành công hoặc không có người dùng phù hợp theo quy tắc đã thiết kế.
3. **Không thể kiểm tra:** dịch vụ thư mục, TLS, search base hoặc tài khoản dịch vụ gặp sự cố.

Trong phản hồi cho client, trạng thái (2) thường chỉ cần thông điệp “Thông tin đăng nhập không hợp lệ”; trạng thái (3) nên được ghi nhận là lỗi dịch vụ nội bộ. **Không biến (3) thành (2)** vì việc đó làm người dùng liên tục đổi mật khẩu khi LDAP đang không khả dụng.

## 4. Ví dụ xác thực bằng `LdapTemplate.authenticate`

Ví dụ giả định `ContextSource` đã được cấu hình base DN `dc=example,dc=org` và dùng tài khoản kỹ thuật có quyền tìm entry dưới `ou=people`. `LdapTemplate.authenticate` tìm DN dựa trên filter rồi kiểm tra password với LDAP server.

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.core.LdapTemplate;

public final class LdapLoginVerifier {
    private final LdapTemplate ldapTemplate;

    public LdapLoginVerifier(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean verify(String uid, String password) {
        // Đừng bao giờ thực hiện simple bind bằng mật khẩu rỗng:
        // server có thể chấp nhận anonymous/unauthenticated bind.
        if (uid == null || uid.isBlank()
                || password == null || password.isEmpty()) {
            return false;
        }

        try {
            return ldapTemplate.authenticate(
                    query().base("ou=people").where("uid").is(uid),
                    password
            );
        } catch (CommunicationException | ServiceUnavailableException ex) {
            // Không coi lỗi hạ tầng là "người dùng sai mật khẩu".
            throw new IllegalStateException(
                    "Không thể kiểm tra thông tin đăng nhập với LDAP", ex);
        }
    }
}
```

Điểm cần nắm:

- `authenticate(...)` trả boolean; trong luồng thông thường, thông tin người dùng không được chấp nhận cho kết quả `false`. Các lỗi kết nối/tìm kiếm/cấu hình có thể vẫn ném exception.
- `query().where("uid").is(uid)` dùng **filter builder** để escape giá trị theo cú pháp filter. Không tạo filter bằng ghép chuỗi `"(uid=" + uid + ")"`: giá trị đầu vào có thể chứa ký tự đặc biệt gây sai cú pháp hoặc LDAP injection.
- `query().base("ou=people")` xác định search base **tương đối** với base đã cấu hình trong `ContextSource`. Không gắn `dc=example,dc=org` thêm lần nữa khi API đã xử lý base.
- `uid` phải được chọn/đảm bảo đủ duy nhất trong phạm vi search; nếu một filter trả nhiều DN, chính sách chọn người dùng sẽ không còn rõ ràng.
- Ví dụ dùng `IllegalStateException` để minh họa đường lỗi hạ tầng. Trong ứng dụng lớn có thể dùng exception miền riêng và xử lý tại tầng API hoặc tích hợp Spring Security.

Nếu cần truy cập **nguyên nhân `AuthenticationException` một cách trực tiếp**, có thể gọi `ContextSource.getContext(principal, credentials)` với DN đầy đủ. Ví dụ:

```java
import javax.naming.directory.DirContext;
import org.springframework.ldap.AuthenticationException;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public final class DirectBindVerifier {
    private final ContextSource contextSource;

    public DirectBindVerifier(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public boolean verifyFullDn(String fullUserDn, String password) {
        if (fullUserDn == null || fullUserDn.isBlank()
                || password == null || password.isEmpty()) {
            return false;
        }

        DirContext ctx = null;
        try {
            // Ví dụ DN: uid=an,ou=people,dc=example,dc=org
            // DN phải được tạo/kiểm tra an toàn, không ghép trực tiếp từ input.
            ctx = contextSource.getContext(fullUserDn, password);
            return true;
        } catch (AuthenticationException ex) {
            // Đã liên hệ được server nhưng xác thực bị từ chối.
            return false;
        } finally {
            LdapUtils.closeContext(ctx);
        }
    }
}
```

Lưu ý: cách này **không tự tìm DN từ username**. Bên gọi phải có DN được xây bằng `LdapNameBuilder` hoặc lấy từ kết quả tìm kiếm đáng tin cậy. Khi nhận lỗi TLS/mạng/quyền/cấu hình, phương thức không được tùy tiện trả `false`; các runtime exception khác sẽ tiếp tục được ném để tầng trên xử lý. Tài nguyên `DirContext` phải được đóng sau sử dụng.

## 5. Lỗi khi tạo entry bằng `LdapTemplate.bind(...)`

`LdapTemplate.bind(...)` thực hiện LDAP AddRequest. Nó khác hoàn toàn với kiểm tra mật khẩu: tham số không phải principal/password mà là **DN của entry mới và các attribute**.

Ví dụ tạo một entry `inetOrgPerson`; `ContextSource` đã được cấu hình base `dc=example,dc=org`:

```java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.SchemaViolationException;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class LdapPersonWriter {
    private final LdapTemplate ldapTemplate;

    public LdapPersonWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson(String uid, String cn, String sn) {
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");

        Attributes attributes = new BasicAttributes(true);
        attributes.put(classes);
        attributes.put("uid", uid);
        attributes.put("cn", cn);
        attributes.put("sn", sn);

        try {
            ldapTemplate.bind(relativeDn, null, attributes);
        } catch (NameAlreadyBoundException ex) {
            throw new IllegalStateException("DN của người dùng đã tồn tại", ex);
        } catch (SchemaViolationException ex) {
            throw new IllegalStateException(
                    "Thuộc tính hoặc objectClass không hợp lệ", ex);
        } catch (NoPermissionException ex) {
            throw new IllegalStateException(
                    "Tài khoản LDAP không được phép tạo entry", ex);
        }
    }
}
```

**Điểm thiết kế:** `uid` được thêm qua `LdapNameBuilder` để escape RDN; `cn` và `sn` là các thuộc tính bắt buộc của `person` trong schema thông dụng. Ví dụ chưa bao gồm kiểm tra input nghiệp vụ, quy tắc trùng lặp hoặc attribute bổ sung của server. Tài khoản `ContextSource` phải có quyền Add dưới `ou=people`. Không thêm mật khẩu người dùng vào log khi thao tác ghi.

Các lỗi thường gặp khi tạo entry:

| Mã LDAP | Exception Spring LDAP điển hình | Tình huống |
| --- | --- | --- |
| `68` | `NameAlreadyBoundException` | Entry ở DN đích đã tồn tại |
| `65` | `SchemaViolationException` | Thiếu `sn` / `cn`, objectClass không phù hợp, hoặc sai quy tắc schema |
| `50` | `NoPermissionException` | Tài khoản kỹ thuật không có quyền Add trong OU |
| `32` | `NameNotFoundException` | Parent DN hoặc nhánh thư mục đích không tồn tại |
| `34` | `InvalidNameException` | DN đích sai cú pháp |
| `19` / `21` | `InvalidAttributeValueException` | Giá trị không đáp ứng ràng buộc/kiểu của attribute |
| `51` / `52` | `ServiceUnavailableException` | Server bận hoặc không sẵn sàng |

Khi kết nối bị mất **sau khi gửi lệnh Add**, ứng dụng có thể không biết server đã tạo entry hay chưa. Không được thực hiện lại `bind(...)` một cách mù quáng; trước tiên cần xác minh DN hoặc dùng quy trình tạo có kiểm soát trùng lặp. Nếu thử lại và nhận `NameAlreadyBoundException`, có thể đó là dấu hiệu lần ghi trước đã thành công, nhưng phải kiểm tra dữ liệu thực tế trước khi khẳng định.

## 6. `InvalidDataAccessApiUsageException`: dùng sai API, không phải sai credential

Mục đích của `InvalidDataAccessApiUsageException` là phân biệt **lỗi sử dụng API truy cập dữ liệu của code bên gọi** với lỗi server. Nó thường gợi ý cần sửa logic/tập tham số gọi API. Ví dụ:

- Một adapter truy cập dữ liệu tự quy định tham số `personDn` không được `null`, nhưng code gọi vi phạm hợp đồng.
- API repository được gọi với tham số hoặc tổ hợp thao tác không được API đó hỗ trợ và **chính implementation** lựa chọn ném `InvalidDataAccessApiUsageException`.
- Code ứng dụng chủ động chuyển một lỗi dùng sai hợp đồng thành exception Spring DAO vì adapter của mình cam kết sử dụng hệ `DataAccessException`.

**Không được gán mặc định** `InvalidDataAccessApiUsageException` cho các tình huống LDAP như mật khẩu sai (`49`), DN trùng (`68`), search base không có (`32`), hoặc schema sai (`65`). Những lỗi này cần được phân loại dựa trên exception LDAP và ngữ cảnh, không dựa vào tên “DataAccess”.

Ví dụ *do chính ứng dụng thiết kế* một adapter có hợp đồng chỉ nhận DN không `null`:

```java
import javax.naming.Name;
import org.springframework.dao.InvalidDataAccessApiUsageException;
import org.springframework.ldap.core.LdapTemplate;

public final class PersonDirectoryDao {
    private final LdapTemplate ldapTemplate;

    public PersonDirectoryDao(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Object findByDn(Name personDn) {
        if (personDn == null) {
            // Ngoại lệ do adapter tự ném theo hợp đồng riêng.
            throw new InvalidDataAccessApiUsageException(
                    "personDn không được null");
        }

        // Các lỗi LDAP ở đây vẫn thuộc org.springframework.ldap.*.
        return ldapTemplate.lookup(personDn);
    }
}
```

Đoạn mã **không chứng minh `LdapTemplate` tự ném** `InvalidDataAccessApiUsageException`. Nó chứng minh ứng dụng *có thể lựa chọn* dùng exception Spring DAO khi tạo một lớp thích nghi để các caller có hợp đồng truy cập dữ liệu chung.

Trong đa số service đơn giản, nếu tham số sai do code bên gọi, `IllegalArgumentException` hoặc kiểm tra tham số trước khi gọi LDAP cũng là lựa chọn rõ ràng. Nếu input đến từ HTTP request thì xác định lỗi đầu vào và phản hồi `400` tại tầng API, thay vì coi mọi lỗi `InvalidDataAccessApiUsageException` là phản hồi `400` mặc định: đây có thể là lỗi lập trình nội bộ.

### 6.1. Bắt exception thế nào cho đúng?

```java
try {
    personDirectoryDao.findByDn(personDn);
} catch (org.springframework.dao.InvalidDataAccessApiUsageException ex) {
    // Chỉ áp dụng khi adapter/caller vi phạm hợp đồng đã định.
    throw ex;
} catch (org.springframework.ldap.AuthenticationException ex) {
    // Bind của tài khoản hiện tại bị từ chối.
    throw ex;
} catch (org.springframework.ldap.CommunicationException ex) {
    // Lỗi LDAP/kết nối, không cùng nghĩa với dùng sai API.
    throw ex;
}
```

Nếu một hệ thống dùng **Spring Data LDAP repository** hay thành phần tích hợp khác, hãy kiểm tra Javadoc và cấu trúc exception của đúng phiên bản đang chạy. Không tự suy từ annotation `@Repository` rằng mọi exception từ `LdapTemplate` tự động được chuyển thành `DataAccessException`.

## 7. Phân loại để xử lý lỗi hợp lý và an toàn

| Nhóm lỗi | Có nên retry? | Phản ứng ứng dụng |
| --- | --- | --- |
| `AuthenticationException` khi bind người dùng | Không với cùng credential | Thông báo đăng nhập không hợp lệ, hạn chế thử sai |
| `AuthenticationException` khi bind service account | Không với cùng cấu hình | Kiểm tra secret, principal, account policy; báo vận hành |
| `AuthenticationNotSupportedException` | Không với cấu hình cũ | Sửa phương thức xác thực/TLS/StartTLS theo chính sách server |
| `InvalidDataAccessApiUsageException` | Không | Sửa cách gọi API hoặc hợp đồng dữ liệu |
| `InvalidNameException` / `SchemaViolationException` | Không | Sửa DN, objectClass, attribute hoặc schema |
| `NameAlreadyBoundException` | Không mặc định | Kiểm tra duplicate và trạng thái entry, có thể xử lý xung đột |
| `NoPermissionException` | Không | Rà soát ACL và bind identity |
| `CommunicationException` / `ServiceUnavailableException` | Có điều kiện, giới hạn | Kiểm tra sự cố mạng/server; retry có backoff, timeout tổng |
| Timeout/mất kết nối sau thao tác ghi | Không retry ngay | Kiểm tra xem thay đổi đã được áp dụng chưa |

**Phản hồi HTTP chỉ là ánh xạ theo nghiệp vụ**, không suy ra trực tiếp từ LDAP code:

- Với luồng xác thực người dùng, credential sai thường tương ứng `401 Unauthorized` hoặc phản hồi đăng nhập chung.
- Nếu caller không đủ quyền dùng tài nguyên ứng dụng, có thể dùng `403 Forbidden`. Nhưng tài khoản kỹ thuật thiếu ACL LDAP thường là **lỗi hạ tầng/cấu hình** của backend, không chứng minh người gọi HTTP bị cấm.
- Nếu truy vấn/chèn entry có xung đột định danh, có thể dùng `409 Conflict`.
- Nếu LDAP tạm thời không khả dụng, có thể trả `503 Service Unavailable` tùy hợp đồng API.
- Nếu code bên trong gọi sai API, cần điều tra lỗi lập trình; không tự động biến thành lỗi người dùng cuối.

### 7.1. TLS, pooling và credential

Do simple bind truyền thông tin xác thực qua kết nối, ưu tiên **LDAPS hoặc StartTLS được cấu hình và xác minh chứng chỉ** theo chính sách môi trường. Không dùng cấu hình bỏ qua xác minh server certificate để xử lý nhanh lỗi `CommunicationException`; cách này có thể tạo rủi ro lộ credential.

Khi dùng pooling, cần phân biệt kết nối của **tài khoản dịch vụ** với context bind tạm thời của **người dùng**. Không giữ `DirContext` đã xác thực bằng tài khoản người dùng trong singleton, cache tự tạo hoặc chia sẻ giữa request. Với các cách xác thực bằng bind trực tiếp, phải đóng context sau khi dùng; bảo đảm mỗi lần kiểm tra không vô tình tái sử dụng trạng thái xác thực của danh tính khác.

Chẩn đoán kết nối có thể dựa trên loại exception, `cause`, thời gian chờ, server logic, thao tác và correlation ID. **Không log password, token, credential, giá trị attribute nhạy cảm**, và không gửi toàn bộ DN hay diagnostic message từ server về client. Một số mã phụ của Active Directory có thể tiết lộ trạng thái tài khoản, chỉ dùng nội bộ khi thực sự cần.

## 8. Kịch bản thực tế để chẩn đoán

### Tình huống A: người dùng nhập mật khẩu đúng nhưng đăng nhập vẫn thất bại

Quan sát: `LdapTemplate.authenticate(...)` trả `false` hoặc có `AuthenticationException`. Không kết luận ngay rằng mật khẩu sai. Kiểm tra search base, search filter, tính duy nhất của `uid`, quyền search của service account, trạng thái tài khoản và chính sách bind/TLS. Nếu search không nhìn thấy người dùng do ACL, bước user bind sẽ không diễn ra như dự kiến.

### Tình huống B: mọi đăng nhập cùng thất bại sau khi đổi secret dịch vụ

Quan sát: lỗi phát sinh khi mở `ContextSource` để tìm user, trước bước bind theo DN người dùng. Đây có thể là `AuthenticationException` của **service account**. Cần kiểm tra secret/principal cấu hình, thay vì bắt người dùng cuối đổi mật khẩu hoặc trả cùng thông điệp sai mật khẩu cho mọi trường hợp.

### Tình huống C: sau khi bật LDAPS, toàn bộ bind báo lỗi kết nối

Quan sát: `CommunicationException` với nguyên nhân TLS/SSL. Kiểm tra certificate chain, hostname verification, truststore, thời hạn chứng chỉ và endpoint/port. Không retry không giới hạn và không tắt xác minh chứng chỉ.

### Tình huống D: tạo người dùng trả lỗi `68`

Quan sát: `NameAlreadyBoundException` trong `LdapTemplate.bind(...)`; đây là **entry DN đã tồn tại** chứ không phải `AuthenticationException`. Kiểm tra cấu trúc DN, `uid`, request trùng lặp và trạng thái của lần Add trước.

### Tình huống E: tạo người dùng báo `65` hoặc `50`

- `65` → `SchemaViolationException`: xem objectClass, attribute bắt buộc (ví dụ `cn`, `sn`) và định nghĩa schema.
- `50` → `NoPermissionException`: tài khoản kỹ thuật không được phép Add trong OU đó; bind đã có thể thành công.

### Tình huống F: service nhận `InvalidDataAccessApiUsageException` trước khi liên hệ LDAP

Quan sát: stack trace trỏ vào adapter/repository validator. Kiểm tra hợp đồng tham số, giá trị `null`, cách dùng API; sửa caller hoặc code adapter. Đây **không phải** một mã bind LDAP và không nên khắc phục bằng đổi mật khẩu/TLS.

## 9. Kiểm thử những trường hợp quan trọng

Các bài kiểm thử nên phân biệt **kết quả xác thực**, **ngoại lệ truy cập thư mục**, **ngoại lệ do dùng sai API** và **kết quả Add**. Chọn mock để kiểm tra chính sách xử lý trong unit test; dùng LDAP test server hoặc môi trường tích hợp được kiểm soát cho lỗi schema, ACL, certificate và thao tác server thực tế.

| Ca thử | Kỳ vọng |
| --- | --- |
| `authenticate` với mật khẩu hợp lệ | `true`; không log secret |
| `authenticate` với mật khẩu sai | `false` trong luồng auth thông thường, thông điệp bên ngoài trung tính |
| Username / password rỗng | Bị từ chối **trước** khi thử simple bind |
| `ContextSource` dùng sai service-account secret | Lỗi hạ tầng, không gán thành người dùng cuối sai mật khẩu |
| LDAP mất kết nối | Lỗi hạ tầng được phân biệt khỏi `false`/not found |
| DN tạo entry đã tồn tại | `NameAlreadyBoundException`, xử lý xung đột |
| Tạo entry thiếu `sn` bắt buộc | Nhận lỗi schema/validation, không retry cùng payload |
| Service account thiếu quyền Add | Nhận lỗi ACL, không kết luận user credential sai |
| Adapter nhận `personDn == null` | `InvalidDataAccessApiUsageException` từ adapter theo hợp đồng riêng |
| Lỗi kết nối ngay sau Add | Không gửi lặp request ghi trước khi kiểm tra trạng thái |

Đối với kiểm thử đăng nhập, cần đảm bảo người dùng và DN thử nghiệm được tạo riêng; không sử dụng mật khẩu thật hoặc chia sẻ log chứa credential. Trong kiểm thử pooling, quan sát rằng mỗi yêu cầu xác thực độc lập và không rò trạng thái người dùng giữa các luồng.

## 10. Câu hỏi tự đánh giá

1. **`LdapTemplate.bind(...)` có phải API kiểm tra mật khẩu không?** Không. Đây là thao tác Add để tạo entry. Xác thực có thể dùng `LdapTemplate.authenticate(...)` hoặc `ContextSource.getContext(principal, credentials)`.
2. **LDAP `49` có luôn là lỗi người dùng cuối nhập sai mật khẩu không?** Không. Có thể liên quan bind service account, principal sai hoặc chính sách tài khoản; phải dựa vào bước đang xảy ra.
3. **`catch (InvalidDataAccessApiUsageException)` có bắt được `org.springframework.ldap.AuthenticationException` không?** Không. Chúng nằm ở hai nhánh exception khác nhau, trừ khi đã có adapter dịch lỗi có chủ đích.
4. **Lỗi LDAP `50` trong lúc tạo entry có cho thấy tài khoản đã đăng nhập sai không?** Không. Đây là thiếu quyền thực hiện thao tác; tài khoản có thể đã bind thành công.
5. **Vì sao phải từ chối password rỗng trước khi simple bind?** Một số server có thể cho phép cơ chế anonymous/unauthenticated bind; ứng dụng không được nhận kết quả đó là xác thực người dùng thành công.
6. **Có thể retry `LdapTemplate.bind(...)` ngay sau khi mất phản hồi mạng không?** Không mặc định. Server có thể đã tạo entry; cần đọc lại trạng thái hoặc quy trình idempotent.
7. **`InvalidDataAccessApiUsageException` do adapter tự ném có phải mã LDAP không?** Không. Đây là cách ứng dụng biểu diễn việc caller vi phạm hợp đồng truy cập dữ liệu.

## 11. Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, truy vấn và xác thực.
- [Spring LDAP API — `AuthenticationException`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/AuthenticationException.html): loại exception LDAP runtime.
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `authenticate`, `bind`, lookup và chuyển đổi exception.
- [Spring LDAP API — `ContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextSource.html): tạo context với principal và credentials.
- [Spring Framework API — `InvalidDataAccessApiUsageException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/InvalidDataAccessApiUsageException.html): lỗi sử dụng sai API của hệ Spring DAO.
- [Java SE JNDI — `javax.naming.AuthenticationException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/AuthenticationException.html): exception xác thực ở tầng JNDI.
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): tích hợp xác thực LDAP vào Spring Security.

**Ghi nhớ:** Luôn phân biệt **authentication bind** với **Add entry qua `LdapTemplate.bind`**, kiểm tra chính xác package của exception và bối cảnh bind. `AuthenticationException` báo vấn đề xác thực, `InvalidDataAccessApiUsageException` báo code dùng sai hợp đồng API khi thực sự được ném bởi thành phần phù hợp; lỗi LDAP về ACL, schema, DN hoặc hạ tầng cần hướng xử lý riêng. 
