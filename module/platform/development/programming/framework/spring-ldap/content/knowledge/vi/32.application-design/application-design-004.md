# Không rò rỉ NamingException ra API nghiệp vụ

## 1. Vấn đề: nghiệp vụ không nên phải hiểu lỗi giao thức LDAP

Trong **Spring LDAP**, ứng dụng thường đọc người dùng, tìm nhóm, xác thực hoặc cập nhật entry thông qua **LdapTemplate**, **LdapClient** và đôi khi **ODM**. Phía dưới là **ContextSource** và JNDI, nơi có các ngoại lệ thuộc **javax.naming**, bao gồm **javax.naming.NamingException**. Spring LDAP chuyển nhiều lỗi này thành các ngoại lệ runtime trong package **org.springframework.ldap**.

Ví dụ ứng dụng quản lý nhân sự đọc danh tính từ **ou=people,dc=example,dc=org** rồi quyết định người đó có được tham gia dự án không. Một thiết kế có vấn đề sẽ đưa exception hạ tầng thẳng vào hợp đồng nghiệp vụ:

~~~java
// KHÔNG NÊN: cổng nghiệp vụ phụ thuộc vào JNDI.
public interface EmployeeDirectory {
    Employee find(String login)
            throws javax.naming.NamingException;
}
~~~

Ngay cả khi port không khai báo **throws**, một **domain service** trực tiếp bắt **org.springframework.ldap.CommunicationException** hay **NameNotFoundException** cũng bị ghép chặt vào LDAP.

Hệ quả là: việc đổi schema hoặc API truy cập LDAP có thể kéo theo sửa lớp nghiệp vụ; sự cố mạng có thể bị hiểu nhầm thành không có tài khoản; API vô tình xuất DN, tên máy chủ, principal hay nội dung lỗi thô; kiểm thử nghiệp vụ phải giả lập exception của thư viện; chính sách retry và trả HTTP status trở nên thiếu nhất quán.

**Mục tiêu:** tất cả ngoại lệ JNDI/Spring LDAP được xử lý trong **LDAP adapter**, rồi chuyển thành **kết quả hoặc lỗi do ứng dụng định nghĩa**. Domain service chỉ hiểu các khái niệm như *không tìm thấy*, *directory không khả dụng*, *dữ liệu không hợp lệ* hoặc *lỗi quyền truy cập tích hợp*.

## 2. Hai NamingException khác nhau

| Tầng | Loại lỗi | Ý nghĩa kỹ thuật |
| --- | --- | --- |
| JNDI thuần | **javax.naming.NamingException** | Checked exception từ một số API như **DirContext** và **Attribute.get()** |
| Spring LDAP | **org.springframework.ldap.NamingException** và các subclass | Runtime exception được Spring LDAP chuyển đổi từ lỗi JNDI |
| Application | Ví dụ **DirectoryFailure** | Lỗi trung lập, có mã ổn định, không gắn với implementation của directory |
| API HTTP | **ProblemDetail** hoặc response lỗi do ứng dụng quy định | Chỉ chứa mã lỗi/thông báo phù hợp với người dùng, không serialize raw exception |

Một số nhóm lỗi đáng phân biệt:

- **CommunicationException**: lỗi giao tiếp, có thể là gián đoạn kết nối; cần xác nhận lỗi timeout cụ thể mà server/driver trả.
- **AuthenticationException**: bind thất bại; nếu principal đang dùng là *tài khoản dịch vụ*, đây là lỗi tích hợp, không có nghĩa người dùng cuối nhập sai mật khẩu.
- **NameNotFoundException**: một DN hoặc search base không còn tồn tại; cách hiểu phụ thuộc thao tác.
- **NoPermissionException** và lỗi quyền tương đương: bind principal không có quyền cần thiết đối với thao tác.
- Lỗi cú pháp DN, vi phạm schema, referral, size limit hoặc dữ liệu attribute không phù hợp: không được tự động xem là *user not found*.

Trong Java 17, package chuẩn của JNDI vẫn là **javax.naming**; không đổi thành **jakarta.naming** chỉ vì dự án chuyển sang Spring Boot 3.

Spring LDAP cung cấp cơ chế chuyển exception kỹ thuật, nhưng **không thể tự quyết định mọi ngữ nghĩa nghiệp vụ**. Ranh giới cuối cùng phải được thiết kế trong adapter và use case của ứng dụng.

## 3. Vị trí ranh giới lỗi

~~~mermaid
flowchart TB
    API["REST API"]
    UC["Use case / Application service"]
    PORT["DirectoryAccountReader (port)"]
    DOMAIN["Domain policy"]
    ADAPTER["SpringLdapAccountReader (adapter)"]
    MAP["LdapFailureTranslator"]
    LDAPAPI["LdapTemplate / LdapClient / ODM"]
    SOURCE["ContextSource, TLS, bind, timeout"]
    DIR[("Directory server")]

    API --> UC
    UC --> PORT
    UC --> DOMAIN
    ADAPTER -. "implements" .-> PORT
    ADAPTER --> MAP
    ADAPTER --> LDAPAPI
    LDAPAPI --> SOURCE --> DIR
~~~

Đường đi thành công: **directory entry → mapper của adapter → DirectoryAccount → use case**.

Đường đi lỗi: **JNDI/Spring LDAP exception → translator → DirectoryFailure hoặc kết quả hợp lệ → use case → API response**.

Tầng **domain/application** không import **javax.naming**, **org.springframework.ldap**, **DirContextOperations**, **Attributes**, **Name**, **LdapQuery** hoặc **LdapTemplate**. Tất cả xử lý DN, schema, filter, bind, pooling và TLS nằm trong hạ tầng.

## 4. Thiết kế kết quả và bảng phân loại lỗi

**Không tìm thấy** chỉ nên là một kết quả bình thường khi thao tác tìm kiếm đã hoàn tất thành công, chứ không phải tên gọi chung của mọi sự cố LDAP.

| Tình huống | Kết quả ở application port | Lý do |
| --- | --- | --- |
| Query thành công, không có entry nào | **Optional.empty()** | Tìm kiếm hợp lệ, không có bản ghi phù hợp |
| Query thành công, đúng một entry hợp lệ | **Optional.of(account)** | Có dữ liệu để xử lý |
| Nhiều entry có cùng khóa được kỳ vọng duy nhất | **AMBIGUOUS_RESULT** | Không được tự chọn phần tử đầu |
| Entry thiếu ID, sai kiểu attribute hoặc vi phạm hợp đồng mapper | **INVALID_DIRECTORY_DATA** | Lỗi schema, dữ liệu hoặc quyền đọc |
| Mất kết nối, LDAP không sẵn sàng | **UNAVAILABLE** | Sự cố hạ tầng có thể tạm thời |
| Service account không bind được/không có quyền | **INTEGRATION_ACCESS_DENIED** | Vấn đề credential/ACL của tích hợp |
| Lỗi directory khác chưa phân loại | **OPERATION_FAILED** | Cần chẩn đoán, không giả làm kết quả rỗng |

Một thao tác **LdapTemplate.search()** trả danh sách rỗng là trường hợp không tìm thấy. Nhưng **NameNotFoundException** từ việc search dưới **ou=people** bị xóa hoặc cấu hình sai có thể là lỗi tích hợp. Không viết quy tắc chung **NameNotFoundException → Optional.empty()** cho mọi thao tác.

## 5. Hợp đồng ứng dụng không phụ thuộc API LDAP

Các ví dụ dưới đây sử dụng Java 17, Spring LDAP, một directory OpenLDAP minh họa và package giả định. Mỗi lớp hoặc interface **public** phải nằm trong file Java riêng đúng tên.

~~~java
// domain/DirectorySubject.java
package com.example.staff.domain;

public record DirectorySubject(String sourceId, String entryId) {}
~~~

~~~java
// domain/DirectoryAccount.java
package com.example.staff.domain;

public record DirectoryAccount(
        DirectorySubject subject,
        String login,
        String displayName
) {}
~~~

~~~java
// application/DirectoryAccountReader.java
package com.example.staff.application;

import com.example.staff.domain.DirectoryAccount;
import java.util.Optional;

public interface DirectoryAccountReader {
    Optional<DirectoryAccount> findByLogin(String login);
}
~~~

Ứng dụng định nghĩa loại lỗi với **mã ổn định**, không chứa tên lớp exception của Spring LDAP:

~~~java
// application/DirectoryFailure.java
package com.example.staff.application;

import java.util.Objects;

public final class DirectoryFailure extends RuntimeException {
    public enum Code {
        UNAVAILABLE,
        INTEGRATION_ACCESS_DENIED,
        INVALID_DIRECTORY_DATA,
        AMBIGUOUS_RESULT,
        OPERATION_FAILED
    }

    private final Code code;

    public DirectoryFailure(Code code, String safeMessage) {
        this(code, safeMessage, null);
    }

    public DirectoryFailure(
            Code code, String safeMessage, Throwable cause) {
        super(safeMessage, cause);
        this.code = Objects.requireNonNull(code);
    }

    public Code code() {
        return code;
    }
}
~~~

**DirectoryFailure** là một exception của ứng dụng. Biến **cause** tùy chọn giúp chẩn đoán nội bộ; không buộc caller phải import loại nguyên nhân. **Không đưa ex.getCause(), stack trace hoặc thông báo nguyên thủy của server vào phản hồi API**. Nếu hệ thống dùng exception subtype thay enum, vẫn cần bảo đảm các kiểu được định nghĩa độc lập ở application.

## 6. Một translator ở tầng adapter

Lớp **LdapFailureTranslator** tập trung chuyển các ngoại lệ runtime của Spring LDAP thành lỗi ứng dụng:

~~~java
// infrastructure/ldap/LdapFailureTranslator.java
package com.example.staff.infrastructure.ldap;

import com.example.staff.application.DirectoryFailure;
import com.example.staff.application.DirectoryFailure.Code;

final class LdapFailureTranslator {
    DirectoryFailure translate(org.springframework.ldap.NamingException ex) {
        if (ex instanceof
                org.springframework.ldap.CommunicationException) {
            return new DirectoryFailure(
                    Code.UNAVAILABLE,
                    "Không thể kết nối dịch vụ thư mục", ex);
        }

        if (ex instanceof
                org.springframework.ldap.AuthenticationException) {
            return new DirectoryFailure(
                    Code.INTEGRATION_ACCESS_DENIED,
                    "Directory từ chối xác thực của hệ thống", ex);
        }

        return new DirectoryFailure(
                Code.OPERATION_FAILED,
                "Directory không thực hiện được yêu cầu", ex);
    }
}
~~~

Đây là **mapping tối thiểu có chủ đích**. Khi triển khai thực tế, bổ sung phân loại lỗi thiếu quyền, timeout, LDAP result code, lỗi DN/schema, referral, giới hạn truy vấn và lỗi ghi theo phiên bản Spring LDAP/server đang dùng. Chỉ chuyển sang **UNAVAILABLE** khi có đủ bằng chứng đó là vấn đề khả dụng; nhóm lỗi chưa biết dùng **OPERATION_FAILED** và cần log chẩn đoán.

Tách translator giúp mọi phương thức tìm kiếm, cập nhật, xóa, duyệt nhóm dùng cùng error contract. Khi đổi **LdapTemplate** thành **LdapClient** hoặc **ODM**, application service không phải sửa cách bắt lỗi.

## 7. Adapter ví dụ với LdapTemplate

Giả sử **ContextSource.base = dc=example,dc=org** và nhánh tìm người dùng là **ou=people**. Lớp sau sử dụng **LdapQueryBuilder** để escape filter và **ContextMapper** để chuyển entry thành model ứng dụng:

~~~java
// infrastructure/ldap/SpringLdapAccountReader.java
package com.example.staff.infrastructure.ldap;

import com.example.staff.application.DirectoryAccountReader;
import com.example.staff.application.DirectoryFailure;
import com.example.staff.application.DirectoryFailure.Code;
import com.example.staff.domain.DirectoryAccount;
import com.example.staff.domain.DirectorySubject;
import java.util.List;
import java.util.Optional;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Repository;

@Repository
public final class SpringLdapAccountReader
        implements DirectoryAccountReader {

    private final LdapTemplate ldap;
    private final LdapFailureTranslator translator =
            new LdapFailureTranslator();

    public SpringLdapAccountReader(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    @Override
    public Optional<DirectoryAccount> findByLogin(String login) {
        if (login == null || login.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên đăng nhập không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "entryUUID")
                .where("uid").is(login);

        try {
            List<DirectoryAccount> rows = ldap.search(
                    query, (ContextMapper<DirectoryAccount>) this::mapEntry);

            if (rows.isEmpty()) {
                return Optional.empty();
            }
            if (rows.size() > 1) {
                throw new DirectoryFailure(
                        Code.AMBIGUOUS_RESULT,
                        "Directory có nhiều entry cùng định danh");
            }
            return Optional.of(rows.get(0));
        } catch (org.springframework.ldap.NamingException ex) {
            throw translator.translate(ex);
        }
    }

    private DirectoryAccount mapEntry(Object ctx) {
        DirContextOperations entry = (DirContextOperations) ctx;
        String uid = entry.getStringAttribute("uid");
        String uuid = entry.getStringAttribute("entryUUID");
        if (uid == null || uid.isBlank()
                || uuid == null || uuid.isBlank()) {
            throw new DirectoryFailure(
                    Code.INVALID_DIRECTORY_DATA,
                    "Entry thiếu attribute định danh bắt buộc");
        }
        return new DirectoryAccount(
                new DirectorySubject("corp-openldap", uuid),
                uid, entry.getStringAttribute("cn"));
    }
}
~~~

Điểm mấu chốt của thiết kế:

1. **Không tìm thấy** là kết quả **Optional.empty()**, chỉ phát sinh sau khi search trả danh sách rỗng.
2. **Mất kết nối** được chuyển qua **LdapFailureTranslator**, không biến thành kết quả rỗng.
3. **Entry trùng hoặc sai dữ liệu** tạo **DirectoryFailure** thuộc ứng dụng, không cần ném **NamingException**.
4. **Filter** được tạo bằng query builder thay vì nối chuỗi **"(uid=" + login + ")"**; tránh lỗi ký tự đặc biệt và LDAP injection.
5. **entryUUID** chỉ là lựa chọn cho schema OpenLDAP được giả định. Active Directory thường dùng **objectGUID** (nhị phân), cần mapper khác; không dùng DN hoặc email làm định danh bền vững.
6. **Search base** là **ou=people** tương đối với base DN trong ContextSource; tránh thêm **dc=example,dc=org** lần thứ hai.

Mã ví dụ tập trung vào ranh giới exception, chưa bao gồm cơ chế phân trang, caching, metrics, timeout và cấu hình nhiều nguồn directory. Những phần đó được bổ sung trong adapter/configuration mà không làm thay đổi interface nghiệp vụ.

## 8. Xử lý NamingException checked khi dùng JNDI trực tiếp

Một số thư viện cũ hoặc mapper đặc biệt còn đọc trực tiếp **javax.naming.directory.Attributes**. Ví dụ **Attribute.get()** có thể ném **javax.naming.NamingException**. Hãy bắt ngoại lệ đó trong hạ tầng thay vì khai báo **throws** trên port:

~~~java
// infrastructure/ldap/JndiAttributeReader.java
package com.example.staff.infrastructure.ldap;

import com.example.staff.application.DirectoryFailure;
import com.example.staff.application.DirectoryFailure.Code;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

final class JndiAttributeReader {

    String readOptionalString(Attributes attrs, String attributeName) {
        Attribute attribute = attrs.get(attributeName);
        if (attribute == null) {
            return null;
        }

        try {
            Object raw = attribute.get();
            if (raw == null) {
                return null;
            }
            if (!(raw instanceof String value)) {
                throw new DirectoryFailure(
                        Code.INVALID_DIRECTORY_DATA,
                        "Kiểu attribute không phù hợp schema");
            }
            return value;
        } catch (NamingException ex) {
            throw new DirectoryFailure(
                    Code.INVALID_DIRECTORY_DATA,
                    "Không đọc được attribute của LDAP entry", ex);
        }
    }
}
~~~

Trong ví dụ trên, context là **đọc giá trị một attribute từ entry đã có**, nên lỗi được xem là vấn đề đọc dữ liệu. Nếu thao tác là **DirContext.search()**, **bind()** hoặc **modifyAttributes()**, ngoại lệ checked có thể phản ánh mất kết nối, xác thực, permission hoặc schema. Khi đó phải phân loại theo **subtype và ngữ cảnh thao tác**, không gán tất cả **javax.naming.NamingException** vào **INVALID_DIRECTORY_DATA**.

Nguyên tắc chung: **giữ thông tin kỹ thuật để chẩn đoán ở tầng hạ tầng**, nhưng chỉ đưa kết quả và kiểu lỗi trung lập qua port.

## 9. Vì sao NameNotFoundException không đồng nghĩa với 404?

Trên thực tế, tên của exception không đủ để kết luận một **tài khoản nghiệp vụ** không tồn tại.

| Thao tác LDAP | Điều gì xảy ra? | Cách hiểu |
| --- | --- | --- |
| Search dưới nhánh hợp lệ | Trả 0 entry | **Optional.empty()** |
| Search với search base sai | Ném lỗi tên không tồn tại | Lỗi cấu hình hoặc cấu trúc directory |
| Lookup theo DN cụ thể | Entry bị xóa | Có thể biểu diễn “không có entry” nếu hợp đồng lookup cho phép |
| Modify theo DN vừa được tìm thấy | Entry bị rename/move OU trước lúc ghi | Lỗi xung đột/thay đổi đồng thời, có thể phải tra cứu lại |
| Principal không có quyền đọc vùng directory | Server che kết quả hoặc từ chối thao tác | Không kết luận tài khoản đã bị xóa |

Tránh xử lý như sau trong một helper dùng chung cho mọi thao tác:

~~~java
// SAI nếu áp dụng không xét ngữ cảnh:
catch (org.springframework.ldap.NameNotFoundException ex) {
    return Optional.empty();
}
~~~

Nếu một use case **lookup DN trực tiếp** quy định không tồn tại là kết quả hợp lệ, đặt xử lý exception cụ thể ngay cạnh lời gọi lookup và có kiểm thử. Với **search**, hãy ưu tiên phân biệt kết quả rỗng hợp lệ và lỗi search base/cấu hình.

## 10. Tách lỗi xác thực người dùng khỏi lỗi bind dịch vụ

Hai tình huống trông giống nhau nhưng có ý nghĩa hoàn toàn khác:

**A. Tài khoản dịch vụ không bind được.** Backend sử dụng **ContextSource** với service account để đọc **uid**, **cn**, nhóm LDAP. Nếu credential hết hạn hoặc ACL thiếu, sự cố thuộc về tích hợp. Không trả HTTP **401 Unauthorized** như thể người dùng cuối đã nhập sai mật khẩu.

**B. Người dùng nhập sai mật khẩu.** Ứng dụng dùng một cổng xác thực riêng, có thể được hiện thực bằng bind người dùng hoặc **Spring Security LDAP**. Sai credential là kết quả xác thực thông thường và không nên lộ tài khoản có tồn tại hay không. Nếu server không khả dụng, đó lại là lỗi hạ tầng; không được âm thầm coi là mật khẩu sai.

Hai hợp đồng nên tách nhau:

~~~java
// Minh họa hai port độc lập, đặt trong các file riêng.
public interface DirectoryAccountReader {
    Optional<DirectoryAccount> findByLogin(String login);
}

public interface DirectoryCredentialVerifier {
    boolean verify(String login, char[] password);
}
~~~

Đoạn trên chỉ minh họa chữ ký, giả định các kiểu đã được import. Trong sản phẩm thực, **DirectoryCredentialVerifier** có thể trả kiểu kết quả xác thực giàu thông tin hơn để phân biệt *credential sai* và *directory unavailable*. Không lưu mật khẩu hoặc **userPassword** trong domain model, không log credential, và cần quản lý bộ nhớ chứa password phù hợp.

## 11. Application service và REST chỉ nhận lỗi ứng dụng

Khi adapter hoạt động đúng, use case không cần biết trường LDAP nào bị lỗi. Nó chỉ nhận model hoặc lỗi đã phân loại.

~~~java
// application/AccountNotFound.java
package com.example.staff.application;

public final class AccountNotFound extends RuntimeException {
    public AccountNotFound() {
        super("Không tìm thấy tài khoản");
    }
}
~~~

~~~java
// application/GetAccount.java
package com.example.staff.application;

import com.example.staff.domain.DirectoryAccount;
import org.springframework.stereotype.Service;

@Service
public final class GetAccount {
    private final DirectoryAccountReader directory;

    public GetAccount(DirectoryAccountReader directory) {
        this.directory = directory;
    }

    public DirectoryAccount execute(String login) {
        return directory.findByLogin(login)
                .orElseThrow(AccountNotFound::new);
    }
}
~~~

Phần HTTP có thể dùng **ProblemDetail** từ Spring Framework 6 / Spring Boot 3:

~~~java
// api/DirectoryErrorAdvice.java
package com.example.staff.api;

import com.example.staff.application.AccountNotFound;
import com.example.staff.application.DirectoryFailure;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public final class DirectoryErrorAdvice {

    @ExceptionHandler(AccountNotFound.class)
    public ResponseEntity<ProblemDetail> notFound(AccountNotFound ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Tài khoản không tồn tại");
        problem.setProperty("code", "ACCOUNT_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(DirectoryFailure.class)
    public ResponseEntity<ProblemDetail> onDirectoryFailure(
            DirectoryFailure ex) {
        HttpStatus status = switch (ex.code()) {
            case UNAVAILABLE -> HttpStatus.SERVICE_UNAVAILABLE;
            case INTEGRATION_ACCESS_DENIED,
                 INVALID_DIRECTORY_DATA,
                 AMBIGUOUS_RESULT,
                 OPERATION_FAILED -> HttpStatus.BAD_GATEWAY;
        };
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status, "Tạm thời không xử lý được dữ liệu thư mục");
        problem.setProperty("code", ex.code().name());
        return ResponseEntity.status(status).body(problem);
    }
}
~~~

Chọn **502 Bad Gateway** hoặc **503 Service Unavailable** ở đây là **chính sách minh họa**. Tùy loại dịch vụ và quy ước API, một số lỗi tích hợp có thể được ánh xạ thành 500/503. Điểm bất biến là **HTTP 404 chỉ đại diện cho tài nguyên thực sự không tìm thấy theo hợp đồng**, còn lỗi bind/tắt server không bị biến thành 404. Mã **401/403** dùng cho chính sách xác thực/phân quyền của người dùng cuối, không gán máy móc cho lỗi service account.

Không gửi **ex.getCause()**, raw server message, DN, filter, bind DN hoặc stack trace trong phản hồi. Dùng **correlation ID** để liên kết thông báo công khai với bản ghi giám sát nội bộ.

## 12. Retry, timeout và thao tác ghi

Phân loại exception giúp quyết định nên thử lại hay dừng, nhưng **không làm cho mọi thao tác LDAP trở nên idempotent**.

| Tình huống | Chính sách gợi ý |
| --- | --- |
| Search bị lỗi giao tiếp tạm thời | Có thể retry có giới hạn, backoff/jitter và timeout |
| Search thành công, trả danh sách rỗng | Xử lý theo kết quả vắng mặt; không retry như outage |
| Credential service account không hợp lệ | Không retry dồn dập; cảnh báo quản trị secret/ACL |
| Entry thiếu attribute bắt buộc | Kiểm tra schema, dữ liệu, quyền; không retry vô hạn |
| LDAP write bị timeout | Kết quả có thể đã được ghi; kiểm tra trạng thái trước khi lặp thao tác |
| Modify theo DN cũ sau rename/move | Có thể tra cứu lại bằng ID bền vững và xử lý conflict |
| Outage kéo dài | Circuit breaker, giới hạn đồng thời và thông điệp API phù hợp |

Ví dụ **LdapTemplate.modifyAttributes()** có thể đã sửa entry nhưng client mất kết nối trước khi nhận phản hồi. Nếu tự động retry thao tác thêm thành viên vào nhóm hoặc ghi nhiều hệ thống, có thể xảy ra tác dụng phụ ngoài dự kiến. Với các thao tác ghi, cần cân nhắc **idempotency**, cơ chế kiểm tra lại và nguồn dữ liệu nào sở hữu trạng thái.

**@Transactional** của JPA không tự mở transaction chung cho LDAP. Khi một use case vừa ghi SQL vừa sửa directory, application service cần chính sách nhất quán, retry hoặc bù trừ riêng.

Đối với kết quả LDAP ảnh hưởng đến **quyền truy cập**, một outage không được tự chuyển thành “cho phép truy cập”. Tùy mức nhạy cảm có thể áp dụng chính sách fail-closed và quy định độ tuổi tối đa của cache.

## 13. ContextSource, TLS, pooling và quan sát lỗi

Tầng hạ tầng nên cấu hình kết nối tập trung, ví dụ trong Spring Boot:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Hãy xác minh **LDAPS** hoặc **StartTLS** được sử dụng đúng với truststore, chứng chỉ và hostname validation; tuyệt đối không tắt kiểm tra TLS để xử lý tạm lỗi handshake trong production. Cấp account đọc LDAP quyền tối thiểu và quản lý secret bên ngoài source.

Thiết lập **connect/read timeout**, giới hạn quy mô truy vấn, chính sách referral và **pooling** theo server và thư viện. Kết nối có trạng thái bind cần được tái sử dụng đúng nguyên tắc; không chia sẻ bừa bãi kết nối của các principal khác nhau. Nếu ứng dụng có nhiều **ContextSource**, error metric nên có mã directory source (không cần log credential).

Nên quan sát tối thiểu:

- Số request tra cứu và thời gian phản hồi theo loại thao tác.
- Tỷ lệ **UNAVAILABLE**, **INTEGRATION_ACCESS_DENIED**, **INVALID_DIRECTORY_DATA** và **OPERATION_FAILED**.
- Số lần retry, kết quả cuối cùng và cảnh báo khi LDAP chậm hoặc mất kết nối.
- **Correlation ID**, tên thao tác và source ID đủ để truy vết mà không log thông tin nhạy cảm.

Thông báo gốc của LDAP đôi khi chứa DN, filter hoặc thông tin hệ thống. Nếu cần ghi chi tiết để chẩn đoán, áp dụng chính sách bảo vệ log và hạn chế truy cập; response cho client vẫn chỉ dùng thông điệp an toàn.

## 14. Chiến lược kiểm thử ranh giới lỗi

**Unit test application service** không cần LDAP server. Port có thể được thay bằng fake chỉ trả giá trị ứng dụng hoặc ném **DirectoryFailure**:

~~~java
// Đặt trong một phương thức @Test của JUnit 5.
DirectoryAccountReader failingDirectory = login -> {
    throw new DirectoryFailure(
            DirectoryFailure.Code.UNAVAILABLE,
            "Không thể kết nối dịch vụ thư mục");
};
GetAccount useCase = new GetAccount(failingDirectory);

DirectoryFailure error = org.junit.jupiter.api.Assertions.assertThrows(
        DirectoryFailure.class,
        () -> useCase.execute("lan"));
org.junit.jupiter.api.Assertions.assertEquals(
        DirectoryFailure.Code.UNAVAILABLE, error.code());
~~~

**Unit test translator và adapter** nên bao phủ:

| Tình huống mô phỏng | Kỳ vọng |
| --- | --- |
| Search trả danh sách rỗng | **Optional.empty()** |
| Search trả một entry hợp lệ | **DirectoryAccount** có ID và login |
| Search trả hai entry trùng login | **AMBIGUOUS_RESULT** |
| Thiếu **entryUUID** hoặc **uid** | **INVALID_DIRECTORY_DATA** |
| Spring LDAP **CommunicationException** | **UNAVAILABLE** |
| Spring LDAP **AuthenticationException** từ service account | **INTEGRATION_ACCESS_DENIED** |
| **NameNotFoundException** do search base sai | Lỗi tích hợp, không phải empty |
| **javax.naming.NamingException** phát sinh trong JNDI mapper | Chuyển thành lỗi ứng dụng |
| Login chứa dấu sao, dấu ngoặc, backslash | Filter escape đúng, không lấy sai entry |

**Integration test** với LDAP server phù hợp schema (OpenLDAP test container hoặc test directory) cần xác nhận: cấu hình base/search base, entry có đủ và thiếu attribute, bind thiếu quyền, TLS/certificate sai, ngắt kết nối/timeout, DN đổi OU, thao tác sửa entry, và error response ở REST boundary. Với Active Directory, cần kiểm thử riêng **objectGUID**, **sAMAccountName** và các thuộc tính/ACL đặc thù.

Có thể thêm kiểm tra kiến trúc bằng ArchUnit hoặc review import: các package **domain** và **application** tuyệt đối không tham chiếu **javax.naming**, **org.springframework.ldap** hoặc các loại mapper/persistence của hạ tầng.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Port có **throws NamingException** | Business code phụ thuộc JNDI | Port chỉ trả model và exception ứng dụng |
| Domain service bắt **CommunicationException** | Logic hạ tầng lan rộng | Translator trong LDAP adapter |
| Bắt mọi lỗi rồi trả **Optional.empty()** | Outage bị coi như account không tồn tại | Chỉ empty cho search hoàn tất không có kết quả |
| Mọi **NameNotFoundException** đều trả 404 | Sai base/DN bị che | Phân loại theo ngữ cảnh thao tác |
| Lỗi bind service account trả HTTP 401 | Người dùng cuối hiểu nhầm mật khẩu của họ sai | Trả lỗi tích hợp 5xx theo chính sách API |
| Phản hồi chứa **ex.getMessage()** hoặc cause thô | Lộ thông tin hệ thống | Mã lỗi ổn định, thông điệp an toàn, correlation ID |
| Retry mọi lỗi và mọi thao tác ghi | Tăng tải, ghi lặp không an toàn | Retry có giới hạn và kiểm tra idempotency |
| Mapper đọc attribute sai kiểu nhưng bỏ qua | Dữ liệu domain không nhất quán | Trả **INVALID_DIRECTORY_DATA** |
| Đổi LDAP client phải sửa service nghiệp vụ | Không có ranh giới kiến trúc thực sự | Giữ port/error contract độc lập thư viện |

## 16. Bài tập ứng dụng

Một hệ thống có endpoint **GET /employees/{login}**, hiện bắt **Exception** rồi trả HTTP 404 bất kể lỗi gì. Khi LDAP timeout, nhân viên đang tồn tại lại bị hiển thị “đã xóa”; khi thao tác sửa nhóm thất bại, response JSON chứa nguyên thông báo JNDI.

Hãy thực hành:

1. Thiết kế **DirectoryAccountReader** không chứa DN, **NamingException** hoặc class của Spring LDAP.
2. Phân loại các trường hợp directory unavailable, bind thất bại, thiếu ACL, entry thiếu attribute, search 0 entry và nhiều entry trùng login.
3. Viết **LdapFailureTranslator** và chỉ rõ lúc nào một **NameNotFoundException** được xem là kết quả vắng mặt hợp lệ.
4. Xây REST error handler phân biệt **404** với lỗi tích hợp **5xx**, không lộ chi tiết kỹ thuật.
5. Viết unit test application bằng fake port, test translator và integration test LDAP với timeout, sai chứng chỉ, sai ACL, filter có ký tự đặc biệt.
6. Giải thích vì sao thao tác ghi LDAP có timeout không nên retry mù khi client chưa biết server đã ghi thành công hay chưa.

Khi tự đánh giá thiết kế, kiểm tra đủ sáu yếu tố: **port độc lập**, **absence khác outage**, **error code rõ ràng**, **mapping nằm trong adapter**, **response an toàn**, **kiểm thử các loại lỗi**.

**Kết luận:** Không rò rỉ **NamingException** ra API nghiệp vụ là giữ mọi chi tiết ngoại lệ JNDI/Spring LDAP trong tầng truy cập directory. Adapter chuyển chúng thành lỗi ứng dụng được phân loại, domain service xử lý theo ý nghĩa nghiệp vụ, còn API trả kết quả nhất quán và an toàn. Thiết kế này tiếp tục có giá trị khi thay schema, ContextSource, **LdapTemplate**, **LdapClient**, ODM hoặc directory server.
