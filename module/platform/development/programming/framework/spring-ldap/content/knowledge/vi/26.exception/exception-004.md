# NameNotFoundException và entry không tồn tại

Khi ứng dụng **Spring LDAP** tìm người dùng, đọc một nhóm, cập nhật thuộc tính hoặc xóa entry, tình huống “không tìm thấy” có thể mang nhiều ý nghĩa khác nhau: một DN cụ thể không tồn tại, không có entry nào khớp filter, OU dùng làm search base bị sai, hoặc tài khoản hiện tại không nhìn thấy dữ liệu vì giới hạn truy cập. Nếu xử lý mọi trường hợp bằng cách trả danh sách rỗng hoặc HTTP `404`, ứng dụng có thể che giấu sự cố cấu hình và làm sai kết quả nghiệp vụ.

Trong chương **Exception** của module **SPRING_LDAP**, bài này giải thích `NameNotFoundException` ở JNDI và Spring LDAP, cách nhận diện lỗi LDAP **`noSuchObject (resultCode 32)`**, và cách phân biệt nó với một truy vấn tìm kiếm hợp lệ nhưng không trả entry. Các ví dụ sử dụng `ContextSource`, `LdapTemplate`, bộ dựng DN/filter, đồng thời liên hệ đến `LdapClient`, ODM, quyền truy cập, TLS, pooling và kiểm thử truy cập thư mục an toàn.

## 1. Mục tiêu học tập và tình huống mở đầu

Sau bài học, người học cần:

1. Phân biệt `javax.naming.NameNotFoundException` với `org.springframework.ldap.NameNotFoundException`.
2. Giải thích vì sao `lookup` một DN không tồn tại thường ném exception, còn `search` với filter không khớp thường trả danh sách rỗng.
3. Chẩn đoán đúng **entry đích**, **parent DN** và **search base** khi gặp LDAP `32`.
4. Quyết định lúc nào chuyển thành `Optional.empty()`, `404`, lỗi cấu hình hoặc lỗi xung đột, thay vì bỏ qua exception.
5. Xây DN và filter an toàn, kiểm tra quyền, xử lý tính nhất quán khi có đồng bộ/replication, và viết kiểm thử phân biệt các trường hợp.

Giả sử dịch vụ LDAP có cây thư mục:

```text
dc=example,dc=org
└── ou=people
    ├── uid=an
    │   ├── cn: An Nguyen
    │   └── sn: Nguyen
    └── uid=binh
        ├── cn: Binh Tran
        └── sn: Tran
```

Tài khoản kỹ thuật được phép đọc `ou=people`. Khi gọi:

- `lookup("uid=an,ou=people")`: entry tồn tại → nhận dữ liệu.
- `lookup("uid=mai,ou=people")`: DN không tồn tại → thường nhận `NameNotFoundException`.
- `search` trong `ou=people` với filter `(uid=mai)`: search base tồn tại, không có entry khớp → thường nhận **danh sách rỗng**.
- `search` trong `ou=staff` khi OU này không tồn tại: server có thể trả **noSuchObject (32)** → `NameNotFoundException`.

Đó là sự khác nhau giữa **không có đối tượng đích** và **không có kết quả phù hợp trong một phạm vi tìm kiếm hợp lệ**.

## 2. `NameNotFoundException` nằm ở lớp nào?

### 2.1. JNDI: `javax.naming.NameNotFoundException`

Trong Java Naming and Directory Interface (JNDI), `javax.naming.NameNotFoundException` kế thừa `javax.naming.NamingException` và là **checked exception**. Nó có thể xuất hiện khi `DirContext.lookup(...)`, `search(...)` hoặc các thao tác với tên không tìm được đối tượng cần thiết.

Ví dụ đơn giản dùng JNDI trực tiếp:

```java
import javax.naming.NameNotFoundException;
import javax.naming.directory.DirContext;

public final class JndiLookupExample {
    public Object lookupRaw(DirContext context, String dn)
            throws javax.naming.NamingException {
        try {
            return context.lookup(dn);
        } catch (NameNotFoundException ex) {
            // Nơi này bắt exception của JNDI (checked).
            throw ex;
        }
    }
}
```

Khi chẩn đoán lỗi JNDI có thể xem `getExplanation()`, `getResolvedName()`, `getRemainingName()` và `getRootCause()` / `getCause()`. Các trường này không bắt buộc có giá trị trong mọi trường hợp; nội dung phụ thuộc provider và phản hồi từ server.

### 2.2. Spring LDAP: `org.springframework.ldap.NameNotFoundException`

Khi dùng `LdapTemplate`, các lỗi JNDI thường được chuyển thành **runtime exception** trong package `org.springframework.ldap`. Vì vậy, Spring LDAP sử dụng:

```java
import org.springframework.ldap.NameNotFoundException;
```

Lớp này thuộc nhánh `org.springframework.ldap.NamingException` và không trùng với `javax.naming.NameNotFoundException`. Cơ chế chuyển đổi được cung cấp bởi `LdapUtils.convertLdapException(javax.naming.NamingException)`.

```text
LDAP server: noSuchObject (32)
                 │
                 ▼
JNDI provider
javax.naming.NameNotFoundException          (checked)
                 │
                 ▼
Spring LDAP: LdapTemplate / ContextSource
org.springframework.ldap.NameNotFoundException (runtime)
                 │
                 ▼
Service quyết định: not found hợp lệ hay lỗi cấu hình?
```

Một điểm dễ nhầm khác: `org.springframework.dao.EmptyResultDataAccessException` thuộc **Spring DAO**, không phải exception tiêu chuẩn để diễn đạt mọi DN thiếu trong `LdapTemplate`. Nếu dùng repository/ODM hoặc adapter khác, hãy xem chính xác hợp đồng exception của API đang gọi, không suy từ việc cả hai đều là truy cập dữ liệu.

### 2.3. Mã LDAP `32` nói được điều gì?

`noSuchObject` là mã kết quả LDAP **32**, diễn đạt rằng đối tượng cần thiết để xử lý thao tác không có trong phạm vi mà server nhận diện. Nó có thể liên quan:

- DN của entry được `lookup` không tồn tại.
- Search base của truy vấn `search` không tồn tại.
- **Parent DN** của entry định tạo chưa có.
- DN đích của thao tác `modify`, `delete` hoặc `rename` không tồn tại.
- Phạm vi hoặc trạng thái cây thư mục thay đổi giữa các thao tác.

Mã `32` **không chứng minh** người dùng không tồn tại ở mọi server, domain hoặc partition. Nó cũng không có nghĩa tự động rằng mật khẩu sai, TLS hỏng hay thiếu quyền. Một số server có thể hạn chế khả năng nhìn thấy entry; đôi khi quyền và topology khiến kết quả quan sát giống “không tồn tại”. Ngược lại, lỗi truy cập bị từ chối rõ ràng thường là mã `50 (insufficientAccessRights)` và `NoPermissionException`.

## 3. Phân biệt `lookup`, `search` và thao tác ghi

| Thao tác | Đích cần có | Không thấy gì sẽ xảy ra? | Cách hiểu |
| --- | --- | --- | --- |
| `lookup(dn)` | Một entry có DN xác định | Thường `NameNotFoundException` | DN đích chưa tồn tại hoặc không truy cập được theo cách server biểu diễn |
| `search(base, filter)` khi base tồn tại | Search base | Danh sách rỗng nếu filter không khớp | Kết quả hợp lệ: không có entry phù hợp trong phạm vi đó |
| `search(base, filter)` khi base không tồn tại | Search base | Có thể `NameNotFoundException`, mã `32` | Lỗi phạm vi truy vấn / cấu hình |
| `bind(dn, ..., attrs)` để thêm entry | Parent DN cần tồn tại | `NameNotFoundException` nếu thiếu parent | Lỗi cấu trúc cây thư mục, không phải đã có entry đích |
| `modifyAttributes(dn, ...)` | Entry cần sửa | `NameNotFoundException` | Entry bị xóa/đổi DN hoặc dữ liệu stale |
| `unbind(dn)` để xóa entry | Entry cần xóa | `NameNotFoundException` | Entry không còn tồn tại; quyết định semantics idempotent tại service |
| `rename(oldDn, newDn)` | Entry cũ và parent hợp lệ | Có thể `NameNotFoundException` | Kiểm tra DN nguồn và đường dẫn đích |

**Chú ý thuật ngữ:** `LdapTemplate.bind(...)` tạo entry bằng thao tác **LDAP Add**. Nó khác với **authentication bind** dùng principal/password để đăng nhập LDAP. Khi thông tin xác thực không hợp lệ, lỗi thường là `AuthenticationException` (mã `49`), không phải `NameNotFoundException` chỉ vì tài khoản chưa được tìm thấy.

### 3.1. Vì sao tìm kiếm không có kết quả không phải exception?

Với LDAP Search, máy chủ có thể trả phản hồi thành công kèm **0 search entry**. `LdapTemplate.search(...)` thường ánh xạ kết quả đó thành một `List` rỗng. Trạng thái này cần được xử lý như dữ liệu nghiệp vụ, ví dụ “không có nhân viên thỏa điều kiện lọc”.

Ngược lại, LDAP yêu cầu một **base object** có thật để bắt đầu search. Nếu base object không tồn tại, server có thể trả `32`. Việc tự động đổi lỗi này thành danh sách rỗng làm mất dấu lỗi cấu hình `ou` hoặc base DN và có thể ảnh hưởng toàn bộ báo cáo.

### 3.2. Vì sao không thể luôn suy ra thiếu entry từ kết quả rỗng?

Kết quả rỗng còn có thể phát sinh khi:

- Filter sai logic, thuộc tính không có giá trị như dự kiến hoặc search scope không bao gồm nhánh cần tìm.
- Tài khoản bind không có quyền nhìn thấy entry hoặc attribute cần lọc.
- Ứng dụng tìm trên một domain/partition khác, hoặc dữ liệu chưa đồng bộ đến LDAP replica đang truy vấn.
- Người dùng có tồn tại nhưng dưới DN khác vì entry đã được chuyển OU/đổi RDN.

Nếu có thông báo về `sizeLimitExceeded`, `timeLimitExceeded` hoặc referral/partial result, cũng không nên suy rằng tập kết quả đã đầy đủ. **Danh sách rỗng là một quan sát tại phạm vi và thời điểm hiện tại**, không nhất thiết là tuyên bố toàn cục về dữ liệu thư mục.

## 4. DN, base DN và nguyên nhân thường gặp

### 4.1. DN tương đối so với `ContextSource`

Giả sử cấu hình `ContextSource` có:

```properties
spring.ldap.base=dc=example,dc=org
spring.ldap.urls=ldaps://ldap.example.org:636
```

Với `LdapTemplate` dùng base này, DN truyền vào thường là tên **tương đối** với `dc=example,dc=org`:

```text
DN tương đối: uid=an,ou=people
Base cấu hình: dc=example,dc=org
DN đầy đủ:    uid=an,ou=people,dc=example,dc=org
```

Nếu nhầm đặt `uid=an,ou=people,dc=example,dc=org` vào API vốn đang dùng base `dc=example,dc=org`, đường dẫn có thể bị ghép sai và tạo ra lỗi không tìm thấy. Cách diễn giải DN phụ thuộc loại API và `ContextSource`: hãy luôn kiểm tra hợp đồng về relative/full DN thay vì áp dụng một quy tắc cho mọi lớp.

### 4.2. Tạo DN đúng và escape an toàn

Không nên tạo DN bằng:

```java
String dn = "uid=" + uidFromRequest + ",ou=people"; // Không an toàn
```

Giá trị `uid` có thể chứa dấu phẩy, dấu cộng, dấu bằng hoặc các ký tự cần escape trong DN. Dùng `LdapNameBuilder`:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uidFromRequest)
        .build();
```

**DN escaping và filter escaping là hai vấn đề khác nhau.** Khi search, nên dùng `LdapQueryBuilder` hoặc bộ dựng filter của Spring LDAP để escape giá trị filter, không dùng `LdapNameBuilder` để xây trực tiếp chuỗi `(uid=...)`.

### 4.3. Checklist xác định sai DN

Khi nghi DN không tồn tại, kiểm tra:

1. `ContextSource` trỏ đúng host/port, tenant/domain/partition và base DN chưa?
2. OU có tồn tại tại LDAP server được truy vấn không? Có khác chữ hoa/thường theo quy tắc matching của schema hoặc khác ký tự/escape không?
3. DN truyền vào là **tương đối** hay **đầy đủ**, có bị lặp phần base không?
4. Search scope là `OBJECT`, `ONELEVEL` hay `SUBTREE`; có bao gồm entry mong muốn không?
5. RDN của entry có được đổi tên hoặc chuyển OU gần đây không?
6. Tài khoản bind có quyền thấy nhánh và các thuộc tính cần dùng trong filter không?
7. Có referral, replication lag hoặc thay đổi topology không? Có tìm nhầm replica/domain không?

Không log toàn bộ DN chứa thông tin định danh nhạy cảm vào mọi log. Nên ghi mã hệ thống, thao tác, loại lỗi và correlation ID; chỉ lưu DN đã được che phù hợp với chính sách nội bộ.

## 5. Ví dụ `lookup`: coi thiếu DN là một kết quả nghiệp vụ

Giả sử một service nhận `uid`, đọc `cn` và trả `Optional<String>`. Chúng ta chỉ chuyển **`NameNotFoundException`** thành “không có entry”; lỗi kết nối, quyền và schema không được tự động chuyển thành `Optional.empty()`.

```java
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryPersonLookup {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> findCommonNameByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            String cn = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs -> {
                        Attribute attribute = attrs.get("cn");
                        if (attribute == null || attribute.size() == 0) {
                            throw new IllegalStateException(
                                    "Entry có DN hợp lệ nhưng thiếu cn");
                        }
                        return attribute.get().toString();
                    }
            );
            return Optional.ofNullable(cn);
        } catch (NameNotFoundException ex) {
            // Chính sách của service: DN không tồn tại => Optional.empty().
            return Optional.empty();
        }
    }
}
```

**Vì sao chỉ bắt một loại exception?** `NameNotFoundException` được xử lý thành một kết quả nghiệp vụ cụ thể. Các exception khác của `org.springframework.ldap.NamingException` được giữ nguyên để một tầng xử lý lỗi riêng phân loại và báo vấn đề hạ tầng/dữ liệu.

Trong ví dụ, `cn` được coi là bắt buộc với hợp đồng truy cập dữ liệu. Nếu entry có thật nhưng thiếu `cn`, đó **không phải** là `NameNotFoundException`. Service ném một lỗi riêng để dễ phát hiện dữ liệu không phù hợp.

Lưu ý: `Optional.ofNullable(cn)` chỉ dành cho đường trả về null nếu API hoặc mapper thực tế có trường hợp đó; tránh dùng `null` để che các ngoại lệ nghiêm trọng. Quy tắc xử lý chính xác còn phụ thuộc cấu hình và đường gọi của `LdapTemplate`.

### 5.1. Chuyển thành HTTP `404` như thế nào?

Giả sử endpoint `GET /people/{uid}` cam kết trả một người dùng cụ thể hoặc `404`:

```java
Optional<String> name = directoryPersonLookup.findCommonNameByUid(uid);

if (name.isEmpty()) {
    // Tầng HTTP có thể trả 404 theo hợp đồng endpoint.
    // Không lấy kết luận này cho lỗi LDAP khác.
}
```

Với endpoint liệt kê `GET /people?uid=...`, việc không có kết quả có thể được biểu diễn thành `200 OK` và `[]`. Cách trả `404` hay danh sách rỗng là **hợp đồng API**, không phải ánh xạ một-một từ LDAP resultCode.

Ngoài ra, đối với những hệ thống có quy tắc chống dò tài khoản, phản hồi có thể cần thống nhất hơn giữa tài khoản không tồn tại và tài khoản người gọi không được phép xem. Không đưa thông điệp chẩn đoán LDAP gốc ra ngoài API.

## 6. Ví dụ `search`: danh sách rỗng và search base thiếu

Truy vấn bên dưới tìm theo attribute `uid` trong một base đã biết:

```java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryPersonSearch {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> searchCommonNames(String uid) {
        return ldapTemplate.search(
                query().base("ou=people").where("uid").is(uid),
                (AttributesMapper<String>) attrs -> {
                    Attribute cn = attrs.get("cn");
                    return cn == null ? null : cn.get().toString();
                }
        );
    }
}
```

Khi `ou=people` **tồn tại**, nhưng không có `uid` phù hợp, kết quả thường là `List` rỗng. Một phần tử được map thành `null` (vì `cn` thiếu) lại là vấn đề chất lượng dữ liệu khác; code sản xuất nên quyết định rõ cần bỏ qua, báo lỗi hay dùng giá trị thay thế theo hợp đồng.

Khi `ou=people` **không tồn tại**, server có thể trả `noSuchObject (32)` và Spring LDAP có thể ném `NameNotFoundException`. Nếu bắt exception đó rồi trả `List.of()`, ứng dụng sẽ không phát hiện mất OU hoặc cấu hình base sai.

### 6.1. `setIgnoreNameNotFoundException(true)` có nên bật?

`LdapTemplate` cung cấp cấu hình `setIgnoreNameNotFoundException(boolean)` để cho phép bỏ qua `NameNotFoundException` trong ngữ cảnh tìm kiếm mà lớp hỗ trợ. Với những phiên bản và đường gọi hỗ trợ hành vi này, bật cờ có thể khiến một số tình huống base không tồn tại được coi giống như không có kết quả.

Đây là quyết định phải được ghi rõ trong nghiệp vụ, chẳng hạn **một nhánh thư mục tùy chọn** có thể vắng mặt hợp lệ. Tránh bật toàn cục để “chữa” lỗi `32` vì nó có thể che nhầm OU bị đổi tên hoặc base cấu hình sai. Đặc biệt, đừng giả định cờ này biến **mọi** thao tác `lookup`, `modify` hay `unbind` thành kết quả rỗng; phạm vi tác dụng cần được kiểm tra theo phiên bản và phương thức cụ thể.

Mặc định nên để lỗi thiếu search base hiện rõ trong quá trình triển khai hoặc giám sát, sau đó chỉ bỏ qua ở nơi có một **lý do nghiệp vụ cụ thể**.

### 6.2. Filter an toàn, scope và ACL

Trong search, `uid` là giá trị do người dùng cung cấp. Bộ dựng `query().where("uid").is(uid)` xử lý escape filter phù hợp; không ghép chuỗi:

```java
// Tránh:
String filter = "(uid=" + uid + ")";
```

Ngay cả filter an toàn về cú pháp vẫn có thể trả kết quả sai nếu chọn nhầm thuộc tính, dùng scope không đúng hoặc tài khoản bind thiếu quyền đọc. Nếu dữ liệu nghiệp vụ yêu cầu kết quả duy nhất, hãy kiểm tra số lượng và định nghĩa quy tắc khi search trả hơn một entry.

## 7. Cùng `NameNotFoundException` nhưng xử lý khác nhau theo thao tác ghi

### 7.1. Tạo entry: thiếu **parent DN**

Khi tạo `uid=mai,ou=people,dc=example,dc=org`, entry `uid=mai` **chưa có** là điều bình thường: mục tiêu của lệnh Add là tạo nó. Nhưng parent `ou=people,dc=example,dc=org` thường **phải tồn tại**.

```text
Add uid=mai,ou=people,dc=example,dc=org
                   │
                   ▼
Parent ou=people,dc=example,dc=org
      ├── Có thật     → tiếp tục kiểm tra quyền, schema, trùng DN
      └── Không có   → noSuchObject (32), có thể NameNotFoundException
```

Nếu Add thất bại vì parent thiếu, việc tạo lại cùng DN thường không giải quyết vấn đề. Cần kiểm tra cấu trúc OU, base của `ContextSource` hoặc chính sách tạo container. Trong một quy trình provisioning được phép tạo OU, phải thực hiện rõ theo quyền và quy tắc nghiệp vụ; không để một thao tác tạo người dùng bất ngờ tự tạo cả cây thư mục.

Lỗi **entry đích đã tồn tại** lại thường là mã `68` / `NameAlreadyBoundException`, khác với mã `32`.

### 7.2. Sửa entry: đối tượng vừa bị xóa hoặc đổi DN

`modifyAttributes(dn, mods)` yêu cầu entry ở `dn` tồn tại khi server áp dụng sửa đổi. Nếu đọc trước rồi sửa sau, một tiến trình khác có thể xóa hoặc chuyển entry trong khoảng giữa:

```text
T1: đọc uid=mai thành công
T2: xóa/đổi DN uid=mai
T1: modifyAttributes(uid=mai, ...)
      → NameNotFoundException
```

Đây là một **race condition**. Không nên kết luận code dựng DN sai chỉ vì trước đó đã lookup thành công. Khi xây API cập nhật, việc trả `404` (đối tượng không còn) hoặc `409` (xung đột trạng thái) phụ thuộc hợp đồng và cơ chế kiểm soát đồng thời.

### 7.3. Xóa entry: có thể cần idempotency

`LdapTemplate.unbind(dn)` xóa entry. Nếu DN không tồn tại, mặc định thường phát sinh `NameNotFoundException`; một API xóa có thể lựa chọn diễn giải “đã không còn tồn tại” là thành công theo tính **idempotent**.

Tuy nhiên, một lệnh xóa có thể thất bại vì parent/base sai, quyền không đủ hoặc endpoint LDAP không đúng. Chỉ nên bỏ qua `NameNotFoundException` khi đối tượng đích và phạm vi đã được xác định đáng tin cậy; vẫn giữ nguyên các lỗi khác.

Ví dụ chính sách xóa idempotent được định nghĩa tại service:

```java
import javax.naming.Name;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;

public final class DirectoryPersonRemoval {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonRemoval(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void removeIfPresent(Name relativeDn) {
        try {
            ldapTemplate.unbind(relativeDn);
        } catch (NameNotFoundException ex) {
            // Chỉ hợp lệ nếu API định nghĩa "đã vắng mặt" là thành công
            // và relativeDn đã được xác nhận nằm trong phạm vi được phép.
        }
    }
}
```

Với thông tin đầu vào thiếu tin cậy, phải kiểm tra hoặc giới hạn DN trước khi truyền cho thao tác xóa. Không dùng pattern “bắt tất cả rồi bỏ qua” để thực hiện xóa người dùng hoặc nhóm.

### 7.4. Đổi tên/chuyển OU

`rename(oldDn, newDn)` yêu cầu DN nguồn còn tồn tại. Với DN đích, server còn phải kiểm tra parent và xung đột. Do vậy, lỗi `NameNotFoundException` có thể liên quan **nguồn hoặc parent của đích**; cần ghi lại hai DN ở dạng đã che thông tin nhạy cảm và phân biệt với `NameAlreadyBoundException` khi đích trùng.

## 8. Chẩn đoán `32` có hệ thống

Khi một service báo `org.springframework.ldap.NameNotFoundException`, hãy đi theo trình tự:

1. **Xác định thao tác:** `lookup`, `search`, Add (`bind`), `modify`, `unbind` hay `rename`. Thao tác quyết định “đối tượng bắt buộc tồn tại” là DN nào.
2. **Kiểm tra package:** JNDI checked exception hay Spring LDAP runtime exception? Xem `cause` nếu lỗi đã được bọc bởi lớp API/adapter.
3. **Xác minh server/partition:** endpoint, port, base DN, tenant/domain, replica được chọn, trạng thái kết nối và TLS. Lỗi TLS thường biểu hiện bằng `CommunicationException` thay vì `32`.
4. **Xây lại DN một cách an toàn:** kiểm tra escape, relative/full DN, OU, RDN, parent và việc thay đổi vị trí entry. Không so sánh DN bằng cách xử lý chuỗi tùy tiện.
5. **Tách search base với filter:** nếu base không tồn tại, sửa cấu hình; nếu base tồn tại và filter không khớp, kiểm tra nghiệp vụ, scope và ACL.
6. **Kiểm tra quyền và nhất quán dữ liệu:** tài khoản bind có quyền đọc/search không; entry có nằm ở server khác hoặc replica chưa cập nhật không?
7. **Quyết định phản hồi và quan sát:** thiếu DN có hợp lệ theo nghiệp vụ không, có nên trả `Optional.empty()`/`404`, hay phải báo lỗi cấu hình? Ghi correlation ID, loại thao tác và nhóm lỗi.

LDAP response có thể cung cấp `matchedDN` (tên tổ tiên gần nhất mà server có thể xác định) trong một số trường hợp `noSuchObject`. Đây là dữ kiện hữu ích để biết DN bị thiếu ở cấp nào, nhưng có thể rỗng/không xuất hiện do server và quyền truy cập. Không dựa hoàn toàn vào `matchedDN` hoặc parse thông điệp lỗi không ổn định để quyết định nghiệp vụ.

### 8.1. Bảng phân loại nhanh

| Quan sát | Nguyên nhân nên kiểm tra | Hành động chính |
| --- | --- | --- |
| `lookup` DN báo `32` | RDN sai, entry bị xóa/đổi DN, khác replica | Kiểm tra DN, parent và thời điểm thay đổi |
| `search` filter không khớp nhưng không có lỗi | Filter/scope, entry chưa có, ACL | Trả kết quả rỗng nếu hợp đồng cho phép |
| `search` base báo `32` | OU/base không có hoặc trỏ nhầm partition | Sửa base/config; không âm thầm bỏ qua |
| Add báo `32` | Parent DN chưa tồn tại | Kiểm tra thứ tự provisioning và cấu trúc OU |
| Add báo `68` | Entry đích đã tồn tại | Kiểm tra duplicate, xử lý xung đột |
| Update/delete báo `32` | Entry đã xóa/đổi DN hoặc stale ID | Xem cơ chế cập nhật và tính đồng thời |
| Mã `50` hoặc `NoPermissionException` | Bind identity thiếu quyền | Rà soát ACL; không đổi thành `404` một cách máy móc |
| `CommunicationException` | DNS/TCP/TLS/server mất kết nối | Báo lỗi hạ tầng, kiểm tra network/TLS |
| Nhiều truy vấn đột ngột “không thấy” sau failover | Nhầm server/replica, replication lag | Kiểm tra routing và trạng thái đồng bộ |

## 9. Retry, đồng bộ dữ liệu và độ tin cậy của kết quả

Thông thường `NameNotFoundException` **không phải lỗi tạm thời**: nếu DN hoặc search base sai, retry với cùng input sẽ lặp lại thất bại. Có một số tình huống ngoại lệ, ví dụ:

- Một thao tác ghi vừa thành công ở replica A nhưng thao tác đọc tiếp theo tới replica B chưa nhận đồng bộ (*replication lag*).
- Dữ liệu được tạo bất đồng bộ trong một workflow provisioning đã có trạng thái chờ rõ ràng.
- Entry được chuyển OU theo quy trình mà client chưa cập nhật vị trí.

Khi hệ thống **biết rõ** đang chờ đồng bộ, có thể dùng retry **giới hạn** với backoff và timeout tổng, đồng thời đo độ trễ thực tế. Không dùng retry đại trà trên mọi lỗi `32`. Nếu cần nhất quán đọc-sau-ghi, cân nhắc định tuyến về cùng server phù hợp hoặc thiết kế workflow chờ trạng thái hoàn tất.

Với thao tác ghi, mất kết nối sau khi gửi lệnh không chứng minh server chưa thực hiện. Hãy xác minh trạng thái trước khi thử lại để tránh Add trùng, xóa nhầm hoặc cập nhật hai lần.

## 10. Kiểm thử nghiệp vụ “entry không tồn tại”

Unit test với mock của `LdapTemplate` có thể kiểm tra chính sách xử lý exception. Integration test trên LDAP test server hoặc môi trường cô lập được cấu hình đúng schema/ACL giúp xác minh hành vi thực tế của provider và server.

| Ca thử | Kết quả mong đợi |
| --- | --- |
| `lookup` tới DN có thật | Trả dữ liệu đúng |
| `lookup` tới DN không tồn tại | Service trả `Optional.empty()` nếu hợp đồng như ví dụ |
| `lookup` tới entry có thật nhưng thiếu attribute bắt buộc | Báo lỗi dữ liệu; không giả làm not found |
| `search` trong OU có thật, filter không khớp | Danh sách rỗng |
| `search` trong OU không tồn tại | Exception được nhìn thấy, trừ khi có quyết định bỏ qua rõ ràng |
| `search` sai scope hoặc filter | Phát hiện sai phạm vi/logic thay vì mặc định coi là thiếu entry |
| Add dưới parent DN chưa tồn tại | Báo thiếu parent; không retry nguyên trạng |
| Add vào DN đã tồn tại | `NameAlreadyBoundException`, không nhầm với `NameNotFoundException` |
| Xóa entry đã không tồn tại | Tuân thủ chính sách idempotent hoặc trả not found |
| `CommunicationException` / `NoPermissionException` | Không bị chuyển thành `Optional.empty()` |
| Đọc ngay sau ghi trên nhiều replica | Kiểm chứng nhất quán và retry giới hạn nếu hệ thống cho phép |

Không nên dùng dữ liệu LDAP thực hoặc credential thật trong ví dụ/kiểm thử. Đối với tích hợp với Active Directory hay thư mục có referral, hãy kiểm tra chính sách truy vấn và dấu hiệu kết quả một phần; tránh khẳng định “không tồn tại” khi còn domain hoặc partition chưa truy vấn.

## 11. Các lỗi thiết kế thường gặp

1. **`catch (Exception)` rồi trả danh sách rỗng.** Nó che lỗi kết nối, ACL, schema hoặc filter.
2. **Bắt nhầm `javax.naming.NameNotFoundException` quanh `LdapTemplate`.** Spring LDAP thường chuyển sang `org.springframework.ldap.NameNotFoundException`.
3. **Dùng `lookup` như `search`.** `lookup` truy cập DN cụ thể, không dùng filter để tìm nhiều entry.
4. **Bật `ignoreNameNotFoundException` toàn cục** chỉ để “hết lỗi”, khiến search base thiếu bị hiểu sai thành kết quả rỗng.
5. **Ghép chuỗi DN hoặc filter từ input** gây sai escape và nguy cơ LDAP injection.
6. **Đoán sai relative DN/full DN**, nhất là khi `ContextSource` đã có base.
7. **Nhầm LDAP `32` với `49` hoặc `50`.** Không tồn tại, xác thực thất bại và thiếu quyền cần xử lý khác nhau.
8. **Retry vô hạn sau `32`** khi OU/config sai, thay vì sửa nguyên nhân.
9. **Xóa idempotent nhưng nuốt mọi exception.** Chỉ có thể coi DN thiếu là thành công khi nghiệp vụ và phạm vi thao tác cho phép.
10. **Xem kết quả rỗng là bằng chứng toàn cục.** Tìm nhầm scope, quyền hạn chế hoặc replica chưa đồng bộ có thể dẫn tới quan sát tương tự.

## 12. Tự kiểm tra

**Câu 1.** `lookup("uid=mai,ou=people")` và `search` ở `ou=people` với filter `(uid=mai)` có cùng kết quả khi `uid=mai` không tồn tại không?

**Đáp án:** Không nhất thiết. `lookup` thường ném `NameNotFoundException`; `search` với base hợp lệ thường trả danh sách rỗng.

**Câu 2.** `search` trong `ou=staff` báo LDAP `32` có thể nói gì?

**Đáp án:** Search base `ou=staff` hoặc một phần DN cần thiết không tồn tại trên server/partition đang truy vấn; cần xác minh base và cấu hình trước khi quyết định là không có người dùng.

**Câu 3.** Lệnh Add một người mới báo `NameNotFoundException`: entry mới chưa có có phải là lỗi không?

**Đáp án:** Không; thiếu entry mới là điều bình thường trước Add. Cần kiểm tra **parent DN** và đường dẫn được tạo.

**Câu 4.** Có nên tự động map mọi `NameNotFoundException` thành `404`?

**Đáp án:** Không. Lookup một resource có thể phù hợp với `404`, nhưng search base/OU bị xóa là lỗi cấu hình, còn thao tác ghi cần semantics riêng.

**Câu 5.** Khi nào retry `NameNotFoundException` có thể hợp lý?

**Đáp án:** Khi có bằng chứng rõ ràng về dữ liệu tạo bất đồng bộ hoặc replication lag, với thời hạn và số lần retry hữu hạn; không retry mặc định trên mọi mã `32`.

**Câu 6.** Vì sao phải dùng `LdapNameBuilder` và query/filter builder?

**Đáp án:** DN và search filter có quy tắc escape khác nhau; dùng đúng bộ dựng giúp tránh sai đường dẫn và giảm nguy cơ injection.

## 13. Tài liệu tham khảo

- [Java SE JNDI — `NameNotFoundException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/NameNotFoundException.html): checked exception khi một tên không được phân giải.
- [Java SE JNDI — `NamingException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/NamingException.html): thông tin resolved/remaining name và root cause.
- [Spring LDAP API — `NameNotFoundException`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/NameNotFoundException.html): runtime exception tương ứng.
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): lookup, search, bind, modify, unbind và ignore name-not-found.
- [Spring LDAP API — `LdapNameBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): tạo DN, escape giá trị RDN.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): cấu hình `ContextSource`, tìm kiếm bằng query builder, ODM và truy cập thư mục.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Add, Modify, Delete và `resultCode` `noSuchObject`.

**Ghi nhớ:** `NameNotFoundException` biểu thị một đối tượng hoặc phần tên cần thiết không được tìm thấy, nhưng **ý nghĩa nghiệp vụ phụ thuộc thao tác**. Phân biệt DN đích với search base và parent DN; chỉ chuyển thành “không tồn tại” khi điều đó thực sự nằm trong hợp đồng, đồng thời giữ nguyên tín hiệu lỗi cấu hình, quyền và kết nối.
