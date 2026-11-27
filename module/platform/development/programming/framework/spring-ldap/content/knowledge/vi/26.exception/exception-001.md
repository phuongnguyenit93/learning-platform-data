# NamingException và các nhóm lỗi LDAP phổ biến

Khi ứng dụng Java truy cập dịch vụ thư mục LDAP, lỗi có thể xảy ra ở nhiều lớp: kết nối TCP/TLS, bind (xác thực), phân giải distinguished name (DN), tìm kiếm, kiểm tra schema hoặc kiểm soát quyền. `NamingException` giúp biểu diễn những lỗi này trong JNDI; **Spring LDAP** cung cấp một hệ exception tương ứng để xử lý thuận tiện với `ContextSource`, `LdapTemplate`, `LdapClient` hoặc ODM.

Bài này thuộc chương **Exception**. Mục tiêu là biết **lỗi phát sinh ở đâu, nhận diện bằng loại exception nào, nguyên nhân thường gặp là gì và khi nào có thể thử lại một cách an toàn**.

## 1. Phân biệt ba lớp thông tin lỗi

Một lỗi có thể đi qua chuỗi:

```text
LDAP server / kết nối mạng
    │  LDAP resultCode, diagnosticMessage hoặc lỗi socket/TLS
    ▼
JNDI (javax.naming.*)
    │  javax.naming.NamingException và các subclass (checked)
    ▼
Spring LDAP
    │  org.springframework.ldap.NamingException và các subclass (runtime)
    ▼
Service / API ứng dụng
       Quyết định retry, kết quả nghiệp vụ, logging, mã HTTP
```

### 1.1. `javax.naming.NamingException` trong JNDI

- Đây là **checked exception** gốc cho các thao tác `Context` và `DirContext` của JNDI; mã dùng JNDI trực tiếp thường phải `catch` hoặc khai báo `throws`.
- Các subclass cho biết nhóm vấn đề, chẳng hạn `javax.naming.AuthenticationException`, `javax.naming.NameNotFoundException` và `javax.naming.CommunicationException`.
- Khi chẩn đoán có thể xem `getExplanation()`, `getResolvedName()`, `getRemainingName()`, `getRootCause()` / `getCause()`. Không phải trường nào cũng có dữ liệu: điều đó tùy nhà cung cấp JNDI và tình huống lỗi.

### 1.2. `org.springframework.ldap.NamingException` trong Spring LDAP

Spring LDAP chuyển các JNDI checked exception sang **runtime exception** cùng ý nghĩa. Ví dụ:

| Nguồn từ JNDI | Exception bắt ở tầng Spring LDAP |
| --- | --- |
| `javax.naming.AuthenticationException` | `org.springframework.ldap.AuthenticationException` |
| `javax.naming.CommunicationException` | `org.springframework.ldap.CommunicationException` |
| `javax.naming.NameNotFoundException` | `org.springframework.ldap.NameNotFoundException` |
| `javax.naming.directory.SchemaViolationException` | `org.springframework.ldap.SchemaViolationException` |
| Không có loại chuyển đổi chuyên biệt | Có thể thành `org.springframework.ldap.UncategorizedLdapException` |

Cơ chế chuyển đổi được thể hiện qua `LdapUtils.convertLdapException(javax.naming.NamingException)`. `LdapTemplate` lo mở/đóng context, duyệt kết quả và chuyển đổi exception khi thao tác LDAP. Vì vậy, ở mã dùng Spring LDAP, cần **import exception thuộc `org.springframework.ldap`**; hai lớp `NamingException` có tên giống nhau nhưng khác package và khác cơ chế kiểm tra tại thời điểm biên dịch.

> **Lưu ý:** `org.springframework.ldap.AuthenticationException` khác với exception xác thực của Spring Security; đừng đoán package chỉ từ tên lớp. Nếu xử lý ở biên xác thực HTTP, hãy chuyển đổi sang kết quả phù hợp của tầng bảo mật/ứng dụng.

### 1.3. LDAP result code không đồng nghĩa với tên exception

Máy chủ LDAP thường gửi `resultCode` (ví dụ `49`: invalid credentials, `32`: no such object). JNDI ánh xạ mã lỗi thành exception; Spring LDAP lại chuyển sang runtime exception. Tuy nhiên, lỗi socket, DNS, TLS hoặc cú pháp filter có thể xuất hiện **trước khi máy chủ trả result code**. Cùng một sự cố còn có thể cho ra thông điệp khác nhau giữa OpenLDAP, Active Directory và các JNDI provider.

Vì thế, nên ưu tiên **loại exception + thao tác đang thực hiện + nguyên nhân gốc**; chỉ xem mã và diagnostic message làm dữ kiện bổ sung.

## 2. Các nhóm lỗi LDAP phổ biến

### 2.1. Kết nối, mạng và khả dụng

| Exception của Spring LDAP | Dấu hiệu / nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `CommunicationException` | Không kết nối được, kết nối bị ngắt, lỗi socket, handshake TLS thất bại; đôi khi lỗi giao thức | Kiểm tra DNS, host/port, firewall, chứng chỉ, truststore, timeout và nguyên nhân `getCause()` |
| `ServiceUnavailableException` | Máy chủ bận/không khả dụng; thường liên quan mã LDAP `51` hoặc `52` | Health của server, giới hạn kết nối, tải hệ thống, chính sách failover |
| `TimeLimitExceededException` | Thời gian dành cho thao tác/tìm kiếm vượt ngưỡng, tương ứng LDAP `3` trong trường hợp server trả mã này | Kiểm tra search base, filter, index, time limit phía client/server |
| `LimitExceededException` | Vượt giới hạn hành chính của server (`11`), hoặc giới hạn đặc thù như referral | Kiểm tra hạn mức theo tài khoản, giới hạn phía server và phạm vi truy vấn |

Không phải `CommunicationException` nào cũng có thể giải quyết bằng retry. Ví dụ truststore sai sẽ thất bại lặp lại; DNS sai hoặc endpoint không tồn tại cũng không được sửa bằng retry. Khi ghi dữ liệu, mất kết nối sau lúc server đã xử lý có thể khiến **không biết thao tác đã thành công hay chưa**.

### 2.2. Xác thực, bảo mật và phân quyền

| Exception | Mã LDAP thường gặp | Nguyên nhân cần phân biệt |
| --- | --- | --- |
| `AuthenticationException` | `49` | Sai DN đăng nhập, sai mật khẩu, hoặc chính sách tài khoản; AD có thể trả thông tin phụ đặc thù |
| `AuthenticationNotSupportedException` | `7`, `8`, `13`, `48` | Phương thức bind không được hỗ trợ; server yêu cầu cơ chế xác thực/bảo mật mạnh hơn hoặc kênh được bảo vệ |
| `NoPermissionException` | `50` | Tài khoản bind có thể xác thực thành công nhưng không có quyền đọc, tạo, sửa hoặc xóa entry |

**Phân biệt quan trọng:** xác thực thành công không đồng nghĩa có quyền đọc mọi OU hoặc mọi attribute. Trả về “sai mật khẩu” khi thực tế là `NoPermissionException` sẽ che khuất lỗi cấu hình ACL.

Trong luồng đăng nhập người dùng, thông điệp gửi ra ngoài nên trung tính, tránh tiết lộ tài khoản có tồn tại hay không. Chỉ ghi chẩn đoán chi tiết trong log được kiểm soát; **không bao giờ log mật khẩu, token hoặc thông tin bí mật của bind**.

### 2.3. DN, tên entry và trạng thái tồn tại

| Exception | Mã LDAP thường gặp | Ví dụ |
| --- | --- | --- |
| `NameNotFoundException` | `32` | `lookup("uid=lan,ou=people")` khi entry không tồn tại; hoặc search base không có thật |
| `NameAlreadyBoundException` | `68` | `bind` tạo entry có DN đã tồn tại |
| `InvalidNameException` | `34`, `64` | DN sai cú pháp hoặc vi phạm quy tắc đặt tên |
| `ContextNotEmptyException` | `66` | Xóa container/OU còn entry con trong khi thao tác không hỗ trợ xóa đệ quy |

**“Không tìm thấy kết quả” và “không tìm thấy search base” là hai tình huống khác nhau:**

- `search` với base hợp lệ, filter không khớp entry nào thường trả **danh sách rỗng** — đây là kết quả bình thường.
- `lookup` một DN không tồn tại thường ném `NameNotFoundException`.
- `search` với base không tồn tại có thể ném `NameNotFoundException`. `LdapTemplate` mặc định **không bỏ qua** lỗi này; có cấu hình `setIgnoreNameNotFoundException(true)` nhưng chỉ nên bật khi chủ động chấp nhận thiếu base như một trạng thái bình thường. Không nên bật để giấu lỗi cấu hình OU/base DN.

### 2.4. Schema, attribute và filter

LDAP schema quy định `objectClass`, attribute bắt buộc, kiểu giá trị, thuộc tính đa trị và các giới hạn khác.

| Exception | Mã LDAP thường gặp | Tình huống |
| --- | --- | --- |
| `SchemaViolationException` | `65`, `67`, `69` | Thiếu attribute bắt buộc, vi phạm objectClass; sửa thuộc tính thuộc RDN hoặc objectClass không hợp lệ |
| `InvalidAttributeIdentifierException` | `17` | Dùng attribute type không có trong schema |
| `InvalidAttributeValueException` | `19`, `21` | Giá trị không đáp ứng constraint/cú pháp schema |
| `NoSuchAttributeException` | `16` | Yêu cầu sửa/xóa attribute không tồn tại |
| `AttributeInUseException` | `20` | Thêm giá trị đã có vào thuộc tính không cho phép trùng |
| `InvalidSearchFilterException` | Có thể xuất hiện trước khi gửi yêu cầu; `18` là một trường hợp ánh xạ liên quan | Filter sai cú pháp hoặc phép so khớp không hợp lệ cho attribute |

Ví dụ: tạo entry với `objectClass=inetOrgPerson` nhưng thiếu `sn` có thể dẫn tới `SchemaViolationException`; sửa thuộc tính có giá trị sai định dạng có thể nhận `InvalidAttributeValueException`. Chi tiết tùy schema và quy tắc được cài trên server.

Khi nhận lỗi schema, không nên retry nguyên yêu cầu. Hãy kiểm tra `objectClass`, định nghĩa attribute, kiểu dữ liệu và quyền sửa entry. Đối với DN và filter được tạo từ dữ liệu người dùng, dùng `LdapNameBuilder` và bộ dựng query/filter của Spring LDAP để tránh lỗi escape và nguy cơ LDAP injection.

### 2.5. Kích thước kết quả, referral và giới hạn tìm kiếm

| Exception | Mã LDAP thường gặp | Ý nghĩa |
| --- | --- | --- |
| `SizeLimitExceededException` | `4` | Server/cơ chế tìm kiếm giới hạn số entry được trả |
| `TimeLimitExceededException` | `3` | Tìm kiếm quá thời gian cho phép |
| `PartialResultException` | `9` trong một số ngữ cảnh | Kết quả không hoàn chỉnh; gặp trong các tình huống referral, đặc biệt với Active Directory |
| `ReferralException` / `LdapReferralException` | `10` trong ngữ cảnh referral | Máy chủ yêu cầu tiếp tục truy vấn tại LDAP server khác, tùy chế độ xử lý referral |

`LdapTemplate` cung cấp các tùy chọn như `setIgnorePartialResultException(boolean)` và `setIgnoreSizeLimitExceededException(boolean)`. Theo tài liệu API, giá trị mặc định tương ứng là **`false`** và **`true`**. Bỏ qua exception có thể cho phép tiếp tục dùng phần kết quả đã nhận, nhưng cũng có thể khiến ứng dụng hiểu nhầm **dữ liệu một phần** là kết quả đầy đủ.

Đối với truy vấn cần toàn bộ dữ liệu, cần xem xét giới hạn và **paged results** (khi server hỗ trợ), thay vì chỉ tăng limit hoặc âm thầm bỏ qua lỗi. Với Active Directory, xử lý referral cần quyết định rõ: cần truy vấn sang domain/partition khác hay được phép chấp nhận phạm vi cục bộ.

## 3. Bảng tra nhanh LDAP result code và hướng xử lý

Các mã sau là những mã gặp nhiều trong vận hành; bảng chỉ mô tả **ánh xạ điển hình của JNDI**, không cam kết mọi server/provider luôn đưa ra cùng loại exception.

| LDAP code | Ý nghĩa | JNDI exception điển hình | Hướng xử lý chính |
| --- | --- | --- | --- |
| `3` | Time limit exceeded | `TimeLimitExceededException` | Tối ưu filter/index; xem time limit |
| `4` | Size limit exceeded | `SizeLimitExceededException` | Giảm scope, phân trang, xem tính đầy đủ |
| `7` / `8` / `13` | Auth method/strength/confidentiality | `AuthenticationNotSupportedException` | Kiểm tra bind mechanism, TLS/StartTLS, chính sách server |
| `11` | Administrative limit exceeded | `LimitExceededException` | Điều chỉnh search và hạn mức |
| `16` / `17` | Attribute không tồn tại/không định nghĩa | `NoSuchAttributeException` / `InvalidAttributeIdentifierException` | Đối chiếu schema |
| `19` / `21` | Constraint/attribute syntax | `InvalidAttributeValueException` | Kiểm tra kiểu và giá trị |
| `32` | No such object | `NameNotFoundException` | Kiểm tra DN, base, OU |
| `34` | Invalid DN syntax | `InvalidNameException` | Tạo DN có escape chuẩn |
| `49` | Invalid credentials | `AuthenticationException` | Kiểm tra bind DN, secret, account policy |
| `50` | Insufficient access rights | `NoPermissionException` | Kiểm tra ACL và bind identity |
| `51` / `52` | Busy / unavailable | `ServiceUnavailableException` | Kiểm tra trạng thái server; retry có giới hạn nếu phù hợp |
| `53` | Unwilling to perform | `OperationNotSupportedException` | Kiểm tra chính sách server và loại thao tác |
| `65` | Object class violation | `SchemaViolationException` | Kiểm tra objectClass và MUST/MAY attributes |
| `66` | Not allowed on non-leaf | `ContextNotEmptyException` | Xem entry con trước khi xóa |
| `68` | Entry already exists | `NameAlreadyBoundException` | Đối chiếu DN, xử lý duplicate |

Lỗi `0` là thành công. LDAP `5`/`6` cho kết quả compare false/true thường không ném exception như lỗi. Một số code có nhiều cách diễn giải theo ngữ cảnh referral và provider. Không nên viết logic nghiệp vụ dựa vào việc tìm chuỗi `"error code 49"` trong thông điệp exception.

## 4. Ví dụ: xử lý exception ở Spring LDAP

Giả sử `ContextSource` đã được cấu hình base DN `dc=example,dc=org`, ứng dụng đọc thông tin người dùng dưới `ou=people`. Dùng `LdapNameBuilder` để tạo DN tương đối một cách an toàn; không ghép chuỗi với `uid` chưa escape.

```java
import java.util.Optional;
import javax.naming.Name;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class LdapPersonRepository {
    private final LdapTemplate ldapTemplate;

    public LdapPersonRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> findCommonName(String uid) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            String cn = ldapTemplate.lookupContext(dn)
                    .getStringAttribute("cn");
            return Optional.ofNullable(cn);
        } catch (NameNotFoundException ex) {
            // Với lookup theo DN, entry không tồn tại là kết quả hợp lệ.
            return Optional.empty();
        } catch (CommunicationException | ServiceUnavailableException ex) {
            // Không biến sự cố thư mục thành "không tìm thấy người dùng".
            throw new IllegalStateException("LDAP tạm thời không khả dụng", ex);
        } catch (NoPermissionException ex) {
            // Cần sửa ACL hoặc tài khoản bind, retry nguyên trạng không giúp ích.
            throw new IllegalStateException("Không đủ quyền đọc LDAP", ex);
        }
    }
}
```

**Giải thích:** `Optional.empty()` ở đây chỉ dành cho `lookup` khi DN không tồn tại; lỗi kết nối, giới hạn và thiếu quyền phải được phân loại riêng. Ví dụ dùng `IllegalStateException` làm exception ứng dụng tối giản; trong hệ thống thực tế có thể tạo các exception miền riêng và ánh xạ chúng tại tầng API.

Nếu chuyển sang `search`, hãy phân biệt kết quả rỗng với lỗi base không tồn tại:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// uid do người dùng cung cấp; query builder xử lý escape giá trị filter.
List<String> names = ldapTemplate.search(
        query().base("ou=people").where("uid").is(uid),
        (AttributesMapper<String>) attrs ->
                attrs.get("cn") == null ? "" : attrs.get("cn").get().toString()
);

if (names.isEmpty()) {
    // Không có entry khớp filter; đây không phải NamingException.
}
```

Ví dụ giả định `cn` là thuộc tính hợp lệ trong schema. Với dữ liệu thực, hãy quyết định rõ có chấp nhận giá trị thiếu, đa trị hoặc kiểu nhị phân hay không; đừng trả chuỗi rỗng để che lỗi dữ liệu nếu nghiệp vụ yêu cầu bắt buộc phải có `cn`.

## 5. Chính sách xử lý lỗi theo loại

Không nên bắt toàn bộ `NamingException` rồi trả về một giá trị mặc định như `null` hoặc danh sách rỗng. Cách đó làm dịch vụ khó giám sát và có thể dẫn đến quyết định quyền truy cập sai.

| Nhóm lỗi | Thử lại? | Hành vi đề xuất tại tầng service/API |
| --- | --- | --- |
| `NameNotFoundException` khi `lookup` | Không | Trả kết quả không tồn tại nếu đó là tình huống nghiệp vụ hợp lệ |
| `NameAlreadyBoundException` | Không tự động | Phân biệt request trùng lặp với xung đột; có thể map thành `409 Conflict` |
| `AuthenticationException` | Không lặp với cùng thông tin xác thực | Trả lỗi xác thực phù hợp, không lộ chi tiết về tài khoản |
| `NoPermissionException` | Không | Báo lỗi phân quyền/cấu hình, rà soát bind identity và ACL |
| `InvalidNameException`, lỗi schema/filter | Không | Sửa dữ liệu, schema, cách dựng DN hoặc filter |
| `CommunicationException`, `ServiceUnavailableException` | Có điều kiện | Retry ít lần với backoff và giới hạn thời gian, chỉ khi có cơ sở nghĩ lỗi tạm thời |
| `TimeLimitExceededException`, `SizeLimitExceededException` | Thường không theo yêu cầu y nguyên | Thu hẹp search, dùng index, phân trang; quyết định có chấp nhận dữ liệu một phần |
| `PartialResultException`, referral | Tùy chính sách | Xác định có cần kết quả từ domain/partition khác; tránh âm thầm bỏ sót |

Đối với **thao tác ghi** (`bind`, `modifyAttributes`, `unbind`), retry sau timeout/mất kết nối cần đặc biệt cẩn thận: phản hồi có thể thất lạc dù server đã áp dụng thay đổi. Trước khi retry phải kiểm tra trạng thái thực tế hoặc thiết kế thao tác có tính idempotent, có kiểm soát trùng lặp.

Đối với **thao tác đọc**, có thể retry giới hạn với lỗi kết nối thoáng qua nếu không làm chậm yêu cầu quá mức; dùng exponential backoff, jitter, timeout tổng và cơ chế ngắt khi server đang lỗi diện rộng. Không được retry không giới hạn trên mỗi request.

## 6. Quy trình chẩn đoán trong vận hành

1. **Xác định bước hỏng:** mở kết nối, TLS/StartTLS, bind, lookup, search hay cập nhật entry. Ví dụ `LDAP 49` lúc bind khác hoàn toàn `LDAP 50` lúc sửa attribute.
2. **Đọc loại exception và cause:** xem `org.springframework.ldap.*` và exception gốc trong `getCause()`; khi làm việc với JNDI trực tiếp xem `javax.naming.*`. Nhận diện lỗi socket/TLS khác lỗi trả về từ LDAP server.
3. **Kiểm tra phạm vi truy vấn:** endpoint, base DN, DN tương đối/tuyệt đối, search scope, filter, attribute cần đọc, trạng thái objectClass; dùng môi trường kiểm thử và dữ liệu giả lập khi tái hiện.
4. **Kiểm tra quyền và giới hạn:** bind account có quyền gì trên OU/attribute đó, server có giới hạn size/time không, referral có khiến thiếu kết quả không.
5. **Quyết định cách xử lý:** sửa cấu hình, sửa input/schema, trả kết quả nghiệp vụ, hoặc retry có giới hạn nếu sự cố tạm thời.
6. **Ghi nhận có cấu trúc:** loại thao tác, hệ thống thư mục, nhóm lỗi, kết quả retry, thời lượng và correlation ID. Che hoặc băm thông tin định danh khi cần; tuyệt đối không log credential và tránh xuất toàn bộ DN/attribute nhạy cảm.

Ví dụ tình huống vận hành:

**A. Đăng nhập thất bại**

- Quan sát: JNDI `AuthenticationException` hoặc Spring LDAP `AuthenticationException`; mã server thường là `49`.
- Kiểm tra: DN của bind account, thông tin đăng nhập, account policy, cấu hình TLS; nếu server yêu cầu kênh bảo mật mạnh hơn có thể nhận `AuthenticationNotSupportedException`.
- Xử lý: không retry liên tục với cùng mật khẩu; thông điệp bên ngoài không xác nhận người dùng có tồn tại.

**B. Tìm kiếm không trả entry**

- `search` trả danh sách rỗng: filter không khớp trong một base hợp lệ.
- `NameNotFoundException`: có thể base `ou=people` chưa được tạo, hoặc DN tra cứu sai.
- Xử lý: xác nhận base, cách build DN, scope và ACL. Một số server có thể ẩn entry không có quyền đọc, vì vậy kết quả rỗng không luôn chứng minh không tồn tại.

**C. Tạo người dùng bị từ chối**

- `NameAlreadyBoundException` (`68`): DN đã tồn tại; tránh lặp `bind` mù quáng.
- `SchemaViolationException` (`65`): thiếu attribute bắt buộc hoặc objectClass sai.
- `NoPermissionException` (`50`): bind account không có quyền tạo dưới OU.
- Xử lý: xác định từng nguyên nhân rồi thay đổi input, schema hoặc ACL tương ứng.

**D. Tìm kiếm nhiều người dùng bị cắt kết quả**

- `SizeLimitExceededException` hoặc cảnh báo phân trang: kết quả không đầy đủ.
- Xử lý: filter hẹp hơn, chỉ lấy attribute cần thiết, phân trang nếu server hỗ trợ; định nghĩa rõ API trả tổng số chính xác hay trang kết quả.

**E. Kết nối LDAPS lỗi sau khi thay chứng chỉ**

- `CommunicationException` bọc nguyên nhân SSL/TLS có thể xuất hiện.
- Xử lý: xem thời hạn/tên máy chủ, chuỗi tin cậy, truststore và TLS negotiation. Tăng số lần retry không giải quyết truststore cấu hình sai.

## 7. Kiểm tra hiểu bài

1. Một `lookup` tới DN không tồn tại và một `search` có filter không khớp entry nào có nhất thiết dẫn đến cùng exception không? **Không**: lookup thường ném `NameNotFoundException`, search base hợp lệ thường trả danh sách rỗng.
2. Vì sao bắt `javax.naming.AuthenticationException` quanh `LdapTemplate` có thể sai? Vì `LdapTemplate` thường chuyển đổi sang `org.springframework.ldap.AuthenticationException` (runtime).
3. Thấy `LDAP 50` trong log sau khi bind thành công thì kiểm tra gì? Quyền của bind identity đối với thao tác/OU/attribute, thay vì chỉ kiểm tra mật khẩu.
4. Vì sao không nên bỏ qua mọi `SizeLimitExceededException`? Vì ứng dụng có thể trả kết quả thiếu mà người dùng tưởng là đầy đủ.
5. Khi ghi entry xong bị mất kết nối, có nên gửi lại `bind` ngay không? Không mặc định; cần xác minh server đã tạo entry hay chưa và bảo đảm xử lý trùng lặp.

## 8. Tài liệu tham khảo

- [Java SE API — `javax.naming.NamingException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/javax/naming/NamingException.html): checked exception và các thông tin nguyên nhân.
- [Oracle JNDI — LDAP status codes và ánh xạ exception](https://docs.oracle.com/javase/jndi/tutorial/ldap/models/exceptions.html): bảng LDAP resultCode → JNDI exception.
- [Spring LDAP — danh mục exception `org.springframework.ldap`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/package-summary.html): các runtime exception theo từng nhóm lỗi.
- [Spring LDAP — `LdapUtils.convertLdapException`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapUtils.html): chuyển JNDI checked exception thành Spring runtime exception.
- [Spring LDAP — `LdapTemplate`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): xử lý exception trong tìm kiếm, tùy chọn bỏ qua partial result/size limit/missing base.
- [Spring LDAP — `LdapNameBuilder`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html): tạo DN bằng các RDN được escape đúng quy tắc.

**Ghi nhớ:** phân loại `NamingException` theo ngữ cảnh thao tác; chỉ retry lỗi thực sự tạm thời và kiểm soát tính đầy đủ của dữ liệu tìm kiếm. Lỗi về DN, quyền, schema và xác thực cần được xử lý tại đúng nguyên nhân.
