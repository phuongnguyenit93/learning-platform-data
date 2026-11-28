# Hệ ngoại lệ của Spring LDAP và nguyên nhân JNDI bên dưới

## 1. Mục tiêu bài học

Khi ứng dụng sử dụng **Spring Data LDAP** để tra cứu hoặc cập nhật directory, lỗi có thể phát sinh tại nhiều tầng: kết nối mạng và TLS, xác thực tài khoản bind, cấu trúc DN, LDAP filter, schema/`objectClass`, quyền truy cập hoặc ánh xạ entry thành đối tượng Java. Hiểu **hệ ngoại lệ của Spring LDAP** giúp phân biệt dữ liệu không tồn tại với lỗi vận hành; hiểu **JNDI** bên dưới giúp tìm nguyên nhân khi thông báo của framework chưa đủ rõ.

Sau bài này, người học có thể:

1. Giải thích tại sao `LdapTemplate` và các repository Spring Data LDAP thường ném **ngoại lệ không kiểm tra** (unchecked) thuộc `org.springframework.ldap`, dù thao tác JNDI bên dưới sử dụng các ngoại lệ `javax.naming` (checked).
2. Nhận diện các nhóm lỗi phổ biến: không tìm thấy DN, trùng entry, xác thực, phân quyền, kết nối, filter, giới hạn tìm kiếm và schema.
3. Đọc chuỗi `cause` để phát hiện lỗi JNDI/TLS/mạng mà không dựa hoàn toàn vào chuỗi thông báo của LDAP server.
4. Chọn cách xử lý phù hợp: kết quả rỗng, báo xung đột, sửa cấu hình, trả lỗi dịch vụ, hoặc retry có giới hạn.
5. Viết mã xử lý lỗi và kiểm thử trên một directory thử nghiệm.

### Một tình huống xuyên suốt

Giả sử ứng dụng có `spring.ldap.base=dc=example,dc=org` và người dùng nằm trong `ou=people`. Entry hoàn chỉnh của Alice:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
```

Nếu tìm `uid=missing`, ứng dụng có thể nhận danh sách rỗng hoặc `NameNotFoundException` **tùy cách truy vấn**: tìm kiếm dưới nhánh `ou=people` đang tồn tại có thể trả về 0 kết quả; `lookup` trực tiếp một DN không tồn tại thường báo không tìm thấy. Không nên kết luận rằng mọi truy vấn không có dữ liệu đều ném exception.

## 2. Các tầng lỗi từ LDAP đến Java

```text
        Service / Controller
                 |
       Spring Data LDAP Repository
                 |
          LdapTemplate / ODM
           |            |
           |            +-- lỗi mapping entity, DN, kiểu dữ liệu
           v
     ContextSource / JNDI
           |
           +-- LDAP provider: javax.naming.NamingException (checked)
           |        \
           |         +-- có thể bọc IOException/SSLHandshakeException
           v
      LDAP / LDAPS server
           |
     LDAP result code + chẩn đoán từ server

  Spring LDAP chuyển nhiều NamingException của JNDI
  thành ngoại lệ runtime tương ứng ở org.springframework.ldap.
```

Ở đây có **hai lớp ngoại lệ dễ nhầm tên**:

- `javax.naming.NamingException` là ngoại lệ **checked** của JNDI trong Java SE; các lớp con như `javax.naming.NameNotFoundException`, `javax.naming.AuthenticationException` xuất hiện khi làm việc trực tiếp với `DirContext`.
- `org.springframework.ldap.NamingException` là ngoại lệ **runtime** của Spring LDAP. Các lớp con như `org.springframework.ldap.NameNotFoundException`, `org.springframework.ldap.AuthenticationException` được sử dụng khi thao tác qua `LdapTemplate` hoặc repository.

Chúng **không phải cùng một kiểu Java**. Việc import nhầm rất dễ dẫn tới `catch` không bắt được lỗi mong đợi. Khi minh họa hoặc gỡ lỗi, có thể dùng tên lớp đầy đủ để tránh nhầm lẫn. `org.springframework.ldap.AuthenticationException` cũng không phải ngoại lệ xác thực HTTP hay Spring Security.

Spring LDAP cung cấp hàm chuyển đổi `org.springframework.ldap.support.LdapUtils.convertLdapException(...)` để chuyển các `javax.naming.NamingException` phổ biến thành ngoại lệ tương ứng trong hệ Spring LDAP. `LdapTemplate` xử lý phần lớn ngoại lệ JNDI theo cơ chế này. Ngoại lệ runtime không có nguồn gốc JNDI, chẳng hạn lỗi lập trình hoặc lỗi ánh xạ ODM, **không nhất thiết** thuộc cùng một cây exception.

> **Nguyên tắc đọc log:** tên lớp Spring LDAP chỉ cho biết nhóm triệu chứng. Nguyên nhân sâu hơn có thể nằm trong `getCause()`, ngoại lệ JNDI gốc, lỗi TLS hoặc phản hồi chẩn đoán của LDAP server.

## 3. Bảng nhận diện ngoại lệ thường gặp

Các lớp dưới đây là những cặp **thường tương ứng** khi JNDI provider ném ngoại lệ thích hợp và Spring LDAP chuyển đổi. Không phải mọi LDAP server/driver đều ánh xạ cùng một mã LDAP sang đúng một lớp JNDI: có thể gặp kiểu ngoại lệ chung hơn.

| Ngoại lệ JNDI (`javax.naming.*`) | Ngoại lệ Spring LDAP (`org.springframework.ldap.*`) | Ý nghĩa điển hình | Hành động đầu tiên |
| --- | --- | --- | --- |
| `NameNotFoundException` | `NameNotFoundException` | DN hoặc nhánh LDAP được lookup không tồn tại. | Kiểm tra DN tương đối, base DN và việc entry thực sự tồn tại. |
| `NameAlreadyBoundException` | `NameAlreadyBoundException` | Tạo entry có DN đã được sử dụng. | Đối chiếu thao tác tạo/cập nhật và quy tắc duy nhất. |
| `AuthenticationException` | `AuthenticationException` | Bind DN, mật khẩu hoặc chính sách xác thực không hợp lệ. | Kiểm tra danh tính bind và chính sách bảo mật của server. |
| `AuthenticationNotSupportedException` | `AuthenticationNotSupportedException` | Phương thức xác thực không được hỗ trợ. | Kiểm tra cơ chế bind/SASL và cấu hình provider. |
| `NoPermissionException` | `NoPermissionException` | Tài khoản bind không được cấp phép cho thao tác. | Kiểm tra ACL, phạm vi quyền và thao tác thực hiện. |
| `CommunicationException` | `CommunicationException` | Không thể giao tiếp với LDAP server; có thể do mạng/TLS. | Kiểm tra host, port, timeout, chứng chỉ và đường truyền. |
| `ServiceUnavailableException` | `ServiceUnavailableException` | Dịch vụ LDAP tạm thời không đáp ứng. | Kiểm tra tình trạng server, quá tải và chính sách retry. |
| `InvalidNameException` | `InvalidNameException` | DN sai cú pháp. | Xây DN bằng API `LdapName`/`LdapNameBuilder`, không tự ghép chuỗi. |
| `InvalidSearchFilterException` | `InvalidSearchFilterException` | LDAP filter không hợp lệ. | Kiểm tra cú pháp filter và escaping tham số. |
| `InvalidSearchControlsException` | `InvalidSearchControlsException` | Cấu hình search controls không hợp lệ. | Kiểm tra phạm vi, giới hạn và thiết lập tìm kiếm. |
| `InvalidAttributeIdentifierException` | `InvalidAttributeIdentifierException` | Tên attribute không hợp lệ. | Kiểm tra tên thuộc tính trong schema. |
| `InvalidAttributeValueException` | `InvalidAttributeValueException` | Giá trị attribute không phù hợp. | Kiểm tra cú pháp, định dạng và ràng buộc thuộc tính. |
| `SchemaViolationException` | `SchemaViolationException` | Vi phạm `objectClass`/schema directory. | Kiểm tra thuộc tính bắt buộc và object classes. |
| `SizeLimitExceededException` | `SizeLimitExceededException` | Truy vấn vượt giới hạn số kết quả. | Thu hẹp filter, điều chỉnh chiến lược lấy dữ liệu. |
| `TimeLimitExceededException` | `TimeLimitExceededException` | Tìm kiếm vượt giới hạn thời gian. | Kiểm tra filter, index, phạm vi tìm kiếm và tải server. |
| `PartialResultException` | `PartialResultException` | Không nhận được toàn bộ kết quả, thường liên quan referral. | Kiểm tra cơ chế referral và khả năng truy cập máy chủ đích. |

Ngoại lệ JNDI chưa được dịch sang một lớp chuyên biệt có thể trở thành `org.springframework.ldap.UncategorizedLdapException`. Do đó, `catch (org.springframework.ldap.NamingException ex)` là một điểm chặn tổng quát phù hợp cho lỗi truy cập LDAP đã được Spring LDAP chuyển đổi, nhưng không phải là giải pháp thay thế cho việc phân loại lỗi quan trọng.

### Ba lưu ý khi dùng bảng

1. **Cùng triệu chứng, nhiều nguyên nhân:** `CommunicationException` có thể xuất phát từ DNS, firewall, lỗi truststore hoặc server ngắt kết nối. Không thể kết luận đó là sự cố mạng đơn thuần chỉ từ tên class.
2. **Không có một mapping duy nhất cho mọi server:** thông báo `LDAP: error code ...` do provider thêm vào có thể khác giữa OpenLDAP, Active Directory và các triển khai LDAP khác.
3. **Không phải lỗi nào cũng được Spring LDAP chuyển đổi:** lỗi khởi tạo Spring context (ví dụ thiếu bean), lỗi parse cấu hình, lỗi ODM hoặc lỗi lập trình Java có thể xuất hiện dưới `BeanCreationException`, `IllegalArgumentException` hay các kiểu runtime khác.

## 4. Hiểu nguyên nhân JNDI và mã phản hồi LDAP

### 4.1. Lỗi tầng giao thức và mã kết quả

LDAP server có thể trả về **result code** mô tả nguyên nhân ở mức giao thức. Một số mã hay gặp theo LDAPv3:

| LDAP result code | Tên thường gặp | Gợi ý chẩn đoán |
| --- | --- | --- |
| `32` | `noSuchObject` | DN đích hoặc nhánh cha không tồn tại. |
| `49` | `invalidCredentials` | Bind thất bại; đừng tự suy ra chỉ do mật khẩu sai. |
| `50` | `insufficientAccessRights` | Thiếu quyền thực hiện thao tác. |
| `68` | `entryAlreadyExists` | Thử tạo DN đang tồn tại. |
| `65` | `objectClassViolation` | Schema/objectClass không cho phép entry hoặc attribute như đã gửi. |
| `19` | `constraintViolation` | Vi phạm ràng buộc giá trị/chính sách của directory. |
| `17` | `undefinedAttributeType` | Attribute không có trong schema. |
| `21` | `invalidAttributeSyntax` | Giá trị không phù hợp cú pháp thuộc tính. |
| `3` | `timeLimitExceeded` | Tìm kiếm vượt giới hạn thời gian. |
| `4` | `sizeLimitExceeded` | Tìm kiếm vượt giới hạn số entry. |
| `51` | `busy` | Server đang bận. |
| `52` | `unavailable` | Dịch vụ không sẵn sàng. |
| `53` | `unwillingToPerform` | Server từ chối thao tác theo chính sách hoặc trạng thái. |

Ví dụ một thông báo lỗi từ provider có thể chứa `[LDAP: error code 49 - ...]`. Đây là một **chi tiết chẩn đoán**, không phải API ổn định để ứng dụng parse bằng regex rồi quyết định toàn bộ luồng nghiệp vụ. Ưu tiên phân loại theo kiểu ngoại lệ, ngữ cảnh thao tác và chính sách ứng dụng; dùng mã LDAP trong log và điều tra nguyên nhân.

### 4.2. Cách xác định nguyên nhân sâu nhất

Trong JNDI, `javax.naming.NamingException` cung cấp `getRootCause()`, `getResolvedName()`, `getRemainingName()` và `getExplanation()`. Ở phía Spring LDAP, bắt đầu từ `Throwable.getCause()` để truy ngược nguyên nhân. Với lỗi kết nối qua LDAPS, chuỗi nguyên nhân có thể như sau:

```text
org.springframework.ldap.CommunicationException
  caused by javax.naming.CommunicationException
    root cause: javax.net.ssl.SSLHandshakeException
      caused by java.security.cert.CertificateException
```

Mức `javax.net.ssl.SSLHandshakeException` cho thấy ứng dụng không hoàn tất bắt tay TLS; cần kiểm tra chứng chỉ, truststore và hostname. Không nên xử lý như lỗi nhập sai mật khẩu.

Một hàm tiện ích nhỏ giúp tìm exception JNDI trong chuỗi cause:

```java
import javax.naming.NamingException;

public final class LdapErrorCauses {
    private LdapErrorCauses() {}

    public static NamingException findJndiCause(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof NamingException naming) {
                return naming;
            }
            current = current.getCause();
        }
        return null;
    }
}
```

Ví dụ dùng Java 17 trở lên vì có pattern matching cho `instanceof`. Khi đã tìm được JNDI exception, có thể xem `getRootCause()` nếu cần điều tra thêm. Không nên đưa `getExplanation()`, DN đầy đủ hoặc stack trace chưa lọc ra response API: các giá trị này có thể tiết lộ cấu trúc directory hoặc thông tin vận hành nội bộ.

### 4.3. Lỗi xuất hiện ở bước nào?

| Giai đoạn | Dấu hiệu | Nơi cần kiểm tra |
| --- | --- | --- |
| Khởi tạo Spring context | Không tạo được repository, thiếu `LdapTemplate` hoặc cấu hình bean. | Package scan, `@EnableLdapRepositories`, `ldapTemplateRef`, dependency và bean. |
| Thiết lập kết nối | `CommunicationException`, lỗi DNS, timeout hoặc TLS. | `spring.ldap.urls`, mạng, cổng, chứng chỉ, timeout. |
| Bind | `AuthenticationException` hoặc không đủ quyền bind. | Bind DN, secret, loại authentication, quyền tài khoản. |
| Search/lookup | DN không có, filter sai, vượt giới hạn hoặc referral. | Base DN, phạm vi search, filter, index, referral. |
| Add/modify/delete | Entry trùng, ACL từ chối, schema sai, DN cha thiếu. | Quyền ghi, schema, objectClass, RDN, DN tương đối. |
| Ánh xạ ODM | Lỗi ánh xạ thuộc tính/kiểu, entry không đúng schema mong đợi. | `@Entry`, `@Attribute`, `@DnAttribute`, `@Id`, kiểu dữ liệu Java. |

Một ứng dụng có thể khởi động thành công nhưng thất bại ở truy vấn đầu tiên do kết nối LDAP thường được thiết lập theo nhu cầu. Vì vậy, kiểm tra khởi tạo repository không thay thế được integration test thực sự kết nối directory.

## 5. Những nguyên nhân dễ gây nhầm lẫn

### DN và base DN

Giả sử `ContextSource` đã đặt base DN là `dc=example,dc=org`. Đường dẫn truyền cho `LdapTemplate` thường là DN **tương đối với base này**. Nếu muốn lookup Alice, DN tương đối là `uid=alice,ou=people`; tự nối lại `dc=example,dc=org` có thể làm truy vấn sai chỗ.

Ngoài ra, `lookup` trực tiếp entry không có có thể tạo `NameNotFoundException`, trong khi `search` dưới `ou=people` đang tồn tại, với filter `(uid=missing)`, thường trả về danh sách rỗng. Hãy phân biệt **không có entry khớp filter** với **base DN tìm kiếm không tồn tại**.

### Schema và objectClass

Ví dụ entry `inetOrgPerson` thiếu `sn`, dùng thuộc tính không được schema cho phép hoặc giá trị sai syntax có thể bị server từ chối bằng `SchemaViolationException`, `InvalidAttributesException` hoặc kiểu lỗi khác tùy provider. Kiểm tra những thuộc tính bắt buộc theo `objectClass`, cú pháp attribute và chính sách của máy chủ. Không nên sửa lỗi bằng cách bắt mọi exception rồi bỏ qua.

### Filter và DN chưa được escape

Đầu vào người dùng không được ghép thẳng vào filter:

```java
// Không an toàn: uid có thể chứa ký tự đặc biệt của LDAP filter.
String unsafeFilter = "(uid=" + uid + ")";

// Ưu tiên API query để mã hóa giá trị cho filter.
var query = org.springframework.ldap.query.LdapQueryBuilder.query()
    .base("ou=people")
    .where("uid").is(uid);
```

Với DN, dùng `LdapNameBuilder` và phương thức `add("uid", uid)` để xây RDN đúng cách. **Escape filter và escape DN là hai quy tắc khác nhau**; không thay thế lẫn nhau. Lỗi filter do dữ liệu chưa escape có thể biểu hiện thành `InvalidSearchFilterException`; nghiêm trọng hơn, chuỗi ghép trực tiếp có thể làm truy vấn bị thay đổi ý nghĩa.

### Giới hạn tìm kiếm và referral

`SizeLimitExceededException`, `TimeLimitExceededException` và `PartialResultException` không có nghĩa là người dùng không tồn tại. Với Active Directory, referral hoặc cách tìm kiếm qua nhiều naming context có thể làm kết quả một phần; cần điều chỉnh cơ chế referral, phạm vi tìm kiếm hoặc tài khoản truy vấn sau khi hiểu hành vi máy chủ. Không mặc nhiên bỏ qua `PartialResultException` vì có thể bỏ sót dữ liệu.

## 6. Chính sách xử lý lỗi trong tầng service

Mục tiêu của tầng service là chuyển một lỗi kỹ thuật thành **ý nghĩa nghiệp vụ ổn định**, đồng thời giữ nguyên cause để phục vụ chẩn đoán.

| Tình huống | Cách xử lý gợi ý | Có retry không? |
| --- | --- | --- |
| Không tìm thấy DN khi thực hiện lookup một đối tượng tùy chọn. | Trả `Optional.empty()` hoặc lỗi nghiệp vụ `not found`. | Không. |
| Tạo entry mà DN đã tồn tại. | Báo xung đột/đã tồn tại, không âm thầm ghi đè. | Không; giải quyết vấn đề trùng định danh. |
| Tài khoản kỹ thuật bind bị từ chối. | Báo lỗi vận hành/cấu hình; giữ bí mật bind credentials. | Không retry liên tục bằng cùng secret. |
| ACL từ chối thao tác. | Kiểm tra quyền tài khoản và ngữ cảnh gọi; không tự tăng quyền. | Không. |
| Mạng/LDAP server tạm thời mất kết nối. | Trả lỗi dịch vụ, theo dõi tình trạng; có thể retry đọc ngắn hạn. | Có điều kiện, giới hạn số lần và thời gian. |
| Sai DN/filter/schema. | Sửa logic, dữ liệu hoặc cấu hình; kiểm thử lại. | Không tự động retry. |
| Vượt giới hạn search. | Thu hẹp filter, tối ưu search base/index, dùng cơ chế tìm kiếm phù hợp. | Không lặp vô hạn cùng truy vấn. |

Không nên chuyển lỗi bind của **tài khoản dịch vụ** thành HTTP `401 Unauthorized` cho người dùng cuối: người dùng có thể đã đăng nhập thành công, còn directory backend mới là thành phần bị lỗi. Tương tự, `NoPermissionException` của LDAP không tự động đồng nghĩa với quyền truy cập HTTP của người dùng; cần xét danh tính nào đang thực hiện bind.

### 6.1. Mẫu code service: phân loại ngoại lệ

Ví dụ đọc thuộc tính `cn` của entry theo DN; dùng Spring LDAP và Java 17+:

```java
package com.example.directory;

import java.util.Optional;
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryUserReader {
    private final LdapTemplate ldapTemplate;

    public DirectoryUserReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> findCommonName(String uid) {
        // DN tương đối với ContextSource base = dc=example,dc=org.
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

        try {
            DirContextOperations entry = ldapTemplate.lookupContext(relativeDn);
            return Optional.ofNullable(entry.getStringAttribute("cn"));

        } catch (org.springframework.ldap.NameNotFoundException ex) {
            // Entry được lookup không tồn tại.
            return Optional.empty();

        } catch (org.springframework.ldap.CommunicationException
                 | org.springframework.ldap.ServiceUnavailableException ex) {
            throw new DirectoryUnavailableException(
                "LDAP tạm thời không sẵn sàng", ex);

        } catch (org.springframework.ldap.AuthenticationException
                 | org.springframework.ldap.NoPermissionException ex) {
            throw new DirectoryConfigurationException(
                "Không xác thực hoặc không đủ quyền truy cập LDAP", ex);

        } catch (org.springframework.ldap.NamingException ex) {
            throw new DirectoryOperationException(
                "Không thực hiện được thao tác LDAP", ex);
        }
    }

    public static class DirectoryUnavailableException
            extends RuntimeException {
        public DirectoryUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class DirectoryConfigurationException
            extends RuntimeException {
        public DirectoryConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class DirectoryOperationException
            extends RuntimeException {
        public DirectoryOperationException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Điểm đáng chú ý:

- Chỉ biến `NameNotFoundException` thành `Optional.empty()` vì API này dùng `lookup` một entry tùy chọn. Không áp dụng quy tắc đó cho lỗi không tìm thấy **base DN bắt buộc** trong cấu hình hệ thống.
- Thứ tự `catch` đi từ lỗi chuyên biệt tới `org.springframework.ldap.NamingException` tổng quát.
- DN được tạo bằng `LdapNameBuilder` để xử lý thành phần RDN theo quy tắc DN, không tự nối `"uid=" + uid`.
- Giữ `ex` làm cause khi chuyển sang ngoại lệ tầng nghiệp vụ. Nếu bỏ cause, đội vận hành mất chứng cứ quan trọng về lỗi JNDI/TLS/schema.
- Nếu thiếu thuộc tính `cn`, đoạn code trả kết quả rỗng; hệ thống có yêu cầu `cn` bắt buộc nên kiểm tra invariant và xử lý dữ liệu không hợp lệ rõ ràng hơn.

Khi dùng `LdapRepository`, vẫn có thể áp dụng chính sách xử lý tương tự ở service bao quanh `repository.findBy...()`, `save()` hoặc `deleteById()`. Tuy nhiên, truy vấn `findByUid` trả về `Optional.empty()` thường là một trạng thái dữ liệu bình thường và không nhất thiết có exception.

### 6.2. Retry có chọn lọc

Retry chỉ hợp lý khi lỗi thực sự **có khả năng tạm thời**. Với truy vấn đọc có thể lặp lại an toàn, cân nhắc retry ngắn, có backoff/jitter, giới hạn tổng thời gian và chỉ áp dụng cho `CommunicationException`/`ServiceUnavailableException` sau khi đánh giá hệ thống.

Không tự động retry thao tác ghi `bind` (tạo entry), `modify` hoặc `delete` sau khi mất kết nối mà chưa xác định trạng thái: server có thể đã thực hiện thao tác nhưng phản hồi bị thất lạc. Ví dụ retry tạo cùng DN có thể tiếp tục gặp `NameAlreadyBoundException`; retry xóa có thể gặp `NameNotFoundException`. Hãy xác minh trạng thái thực tế và thiết kế tính idempotent cho nghiệp vụ trước khi retry.

## 7. Logging, giám sát và bảo mật

Khi ghi nhận lỗi LDAP, tối thiểu nên biết **loại thao tác** (`search`, `lookup`, `add`, `modify`, `delete`), **nhóm ngoại lệ**, định danh tương quan của yêu cầu, thời gian truy vấn, kết nối được cấu hình tới hệ thống nào, và liệu đang ở môi trường thử nghiệm hay production.

Ví dụ log với SLF4J:

```java
// Không ghi mật khẩu, raw filter hoặc DN chứa dữ liệu cá nhân.
log.warn("LDAP lookup failed: type={}, requestId={}",
    ex.getClass().getSimpleName(), requestId);
```

Ở môi trường log bảo mật phù hợp, có thể lưu stack trace và cause để điều tra; hãy kiểm soát quyền truy cập và thời hạn lưu trữ. Tránh đưa `ex.getMessage()` vào lỗi API trả cho người dùng nếu thông báo có thể chứa địa chỉ nội bộ, tên tài khoản bind, DN hoặc filter.

Theo dõi số lỗi theo nhóm sẽ hữu ích hơn tổng số lỗi chung: tỷ lệ `CommunicationException` tăng có thể phản ánh sự cố mạng, trong khi `SchemaViolationException` tăng sau khi triển khai có thể phản ánh thay đổi mapping hoặc schema. Đặt timeout kết nối/tìm kiếm để tránh thread bị giữ quá lâu khi máy chủ gặp sự cố.

**Bảo mật kết nối:** với LDAP chứa thông tin người dùng, dùng LDAPS hoặc StartTLS và xác minh chứng chỉ máy chủ. Không tắt kiểm tra TLS để “chữa” `CommunicationException` hay `SSLHandshakeException`. Kiểm tra hostname, truststore và chuỗi chứng chỉ thay vì bỏ xác thực.

## 8. Kiểm thử lỗi với directory thật hoặc directory thử nghiệm

Kiểm thử đơn vị có thể xác minh service phân loại ngoại lệ theo quy tắc đã chọn bằng cách mock `LdapTemplate`. Kiểm thử tích hợp cần **LDAP server thử nghiệm** (ví dụ server nhúng hoặc container) có schema và dữ liệu mẫu để xác minh mapping thực tế từ LDAP response → JNDI → Spring LDAP.

### Ma trận ca kiểm thử

| Ca | Chuẩn bị | Kỳ vọng |
| --- | --- | --- |
| Lookup entry tồn tại | Tạo `uid=alice` trong `ou=people`. | Trả về `cn` mong đợi. |
| Lookup DN không tồn tại | `ou=people` tồn tại nhưng `uid=missing` không có. | Spring LDAP báo `NameNotFoundException` hoặc service chuyển sang `Optional.empty()`. |
| Tạo trùng DN | Bind entry `uid=alice` lần thứ hai. | Lỗi trùng entry; không ghi đè dữ liệu đã có. |
| Bind sai mật khẩu | Dùng tài khoản thử nghiệm với secret sai. | Xác thực thất bại khi thực hiện kết nối/bind; nhận diện đúng nhóm lỗi. |
| Ghi bằng tài khoản chỉ đọc | Dùng bind account bị giới hạn ACL. | Không đủ quyền; không thực hiện ghi. |
| Entry vi phạm schema | Thử tạo entry `inetOrgPerson` thiếu `sn`. | Thao tác bị từ chối theo schema. |
| Search filter sai | Gửi filter không hợp lệ qua API phù hợp. | Xác định nhóm lỗi filter theo provider; không thay thế bằng “không tìm thấy”. |
| Ngắt LDAP/đổi port trong môi trường test | Server không thể kết nối. | Lỗi kết nối/dịch vụ; không coi là kết quả rỗng. |

Ví dụ một integration test đọc DN không tồn tại với `LdapTemplate`. Giả định base DN `dc=example,dc=org`, OU `ou=people` đã được tạo và server test đang sẵn sàng:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class LdapErrorIT {
    @Autowired
    private LdapTemplate ldapTemplate;

    @Test
    void lookupMissingDnIsNotFound() {
        Name missingDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", "missing")
            .build();

        assertThatThrownBy(() -> ldapTemplate.lookupContext(missingDn))
            .isInstanceOf(org.springframework.ldap.NameNotFoundException.class);
    }
}
```

Test này cần dữ liệu và kết nối thử nghiệm riêng. Nếu `ou=people` bị xóa, test có thể vẫn ném `NameNotFoundException` nhưng không còn chứng minh đúng tình huống mong muốn. Khi kiểm thử lỗi bind, network, TLS hoặc ACL, nên dùng cấu hình tách biệt và **không gây gián đoạn** directory dùng chung.

### Quy trình điều tra sự cố

1. Xác định thao tác lỗi (`lookup`, `search` hay ghi) và môi trường, tránh kết luận từ một thông báo rời rạc.
2. Xác nhận exception là của `org.springframework.ldap`, JNDI hay Spring context; kiểm tra package đầy đủ.
3. Đọc `getCause()` và khi có `javax.naming.NamingException` thì xem `getRootCause()`, mã LDAP và chẩn đoán an toàn.
4. Đối chiếu DN đầy đủ, base DN, filter, schema, quyền tài khoản và kết nối TLS theo nhóm lỗi.
5. Tái hiện trên directory thử nghiệm bằng thao tác nhỏ nhất, kiểm tra fix rồi bổ sung integration test hồi quy.

## 9. Câu hỏi tự luyện

1. Tại sao bắt `javax.naming.NameNotFoundException` trực tiếp quanh `LdapTemplate.lookupContext(...)` thường không phải cách bắt lỗi thích hợp? Nêu package exception cần bắt.
2. Một truy vấn `findByUid("missing")` trả `Optional.empty()`, nhưng `lookup("uid=missing,ou=people")` ném `NameNotFoundException`. Vì sao hai kết quả không mâu thuẫn?
3. Ứng dụng có `CommunicationException` với cause `SSLHandshakeException`. Bạn kiểm tra điều gì trước khi cân nhắc retry?
4. Vì sao lỗi LDAP bind của tài khoản dịch vụ không nên tự động biến thành HTTP 401 của người dùng?
5. Sau một lần `save` bị lỗi kết nối, thao tác đã thực sự được ghi hay chưa? Làm sao xác minh trước khi thử lại?
6. Một entry `inetOrgPerson` bị từ chối với result code `65`. Cần kiểm tra những thành phần nào của schema và đối tượng ODM?

## 10. Tài liệu tham khảo

- [Spring LDAP — Reference Documentation](https://docs.spring.io/spring-ldap/reference/): thao tác với `LdapTemplate`, DN, filter, ODM và hành vi ngoại lệ.
- [Spring LDAP — API: `LdapUtils`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapUtils.html): phương thức chuyển đổi ngoại lệ JNDI.
- [Spring LDAP — API: `NamingException`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/NamingException.html): ngoại lệ runtime cơ sở của Spring LDAP.
- [Java SE — `javax.naming.NamingException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/NamingException.html): chuỗi nguyên nhân, `getRootCause()` và thông tin DN.
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): ý nghĩa các LDAP result codes và hành vi ở tầng giao thức.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, query methods và tích hợp với Spring LDAP.
