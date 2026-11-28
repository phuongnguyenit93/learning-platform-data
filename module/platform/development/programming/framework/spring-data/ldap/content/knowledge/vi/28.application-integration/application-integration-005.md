# Ánh xạ lỗi LDAP sang kết quả nghiệp vụ

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java có thể đọc, tìm kiếm và cập nhật directory bằng **Spring Data LDAP repository** hoặc **LdapTemplate**. Directory có cấu trúc phân cấp theo **DN**, mỗi entry tuân theo **objectClass** và schema; truy vấn chịu ảnh hưởng của base DN, LDAP filter, quyền của tài khoản bind và trạng thái kết nối. Vì thế, khi một thao tác thất bại, ngoại lệ kỹ thuật không phải lúc nào cũng có cùng ý nghĩa đối với nghiệp vụ.

Ví dụ, cùng một lỗi LDAP **noSuchObject (32)** có thể có hai ý nghĩa rất khác: cập nhật một người dùng đã bị xóa, hoặc cố tạo người dùng dưới nhánh **ou=people** chưa được cấu hình. Trường hợp đầu có thể là **USER_NOT_FOUND**; trường hợp sau là **lỗi triển khai directory**, không phải lỗi của người dùng cuối.

Bài thuộc chương **Tích hợp ứng dụng**, tập trung vào việc biến lỗi từ **LDAP/JNDI/Spring LDAP** thành **kết quả nghiệp vụ ổn định**, rồi thành phản hồi HTTP/API, job outcome hoặc event phù hợp. Sau bài học, bạn có thể:

- Phân biệt **LDAP result code**, **Spring LDAP exception**, **lỗi miền nghiệp vụ** và **HTTP status**.
- Ánh xạ các mã phổ biến như **32, 49, 50, 65, 68, 19, 21, 3, 4, 51, 52** theo **loại thao tác**.
- Thiết kế lớp **gateway/adapter** che giấu ngoại lệ hạ tầng và trả lỗi có mã ổn định.
- Xây dựng REST API dùng **ProblemDetail** mà không làm lộ bind DN, mật khẩu, nội dung LDAP diagnostic hoặc tồn tại tài khoản nhạy cảm.
- Phân biệt kết quả rỗng hợp lệ, thao tác ghi không thành công, kết quả không đầy đủ và lỗi có thể retry.
- Kiểm thử translator bằng unit test và xác minh với LDAP directory thật, bao gồm TLS, ACL, schema và xung đột cập nhật.

## 1. Vì sao không trả thẳng LDAP exception cho client?

Xét API:

~~~http
PATCH /api/directory/users/an/email
Content-Type: application/json

{"email":"an@example.org"}
~~~

Trong mã Java, thao tác có thể gọi:

~~~java
ldapTemplate.modifyAttributes(
    userDn,
    modificationItems
);
~~~

Các tình huống lỗi khác nhau cần kết quả khác nhau:

| Tình huống thực tế | Quan sát LDAP/Spring LDAP | Điều client cần hiểu |
| --- | --- | --- |
| User **an** đã bị xóa | **noSuchObject (32)**, thường thành **NameNotFoundException** | Đối tượng cần sửa không tồn tại |
| Service account không được sửa email | **insufficientAccessRights (50)** | Dịch vụ đang gặp lỗi cấu hình/quyền; không quy kết ngay lỗi cho người dùng cuối |
| Field không hợp schema | **objectClassViolation (65)** hoặc lỗi syntax/constraint | Cần kiểm tra validation, schema và cấu hình ứng dụng |
| LDAP server không phản hồi | Lỗi kết nối hoặc **unavailable (52)** | Phụ thuộc backend tạm thời không khả dụng |
| Filter tìm thấy 0 entry | Search thành công và trả danh sách rỗng | Không có kết quả phù hợp; **không phải exception** |

Nếu controller chỉ làm **catch (Exception) → HTTP 500**, client không phân biệt tình huống có thể sửa yêu cầu với sự cố vận hành. Nếu chỉ làm **catch (NamingException) → HTTP 400**, ứng dụng lại đổ lỗi cho client cả khi CA hết hạn, bind password dịch vụ sai hoặc LDAP server sập.

**Mục tiêu là một hợp đồng lỗi theo nghiệp vụ**, không phải phép đổi máy móc từ mỗi mã LDAP sang một mã HTTP cố định.

## 2. Bốn tầng cần tách biệt

~~~mermaid
flowchart TD
    A["LDAP server / kết nối: result code, TLS, referral"] --> B["JNDI + Spring LDAP: runtime exception"]
    B --> C["Directory gateway: ánh xạ theo thao tác và bối cảnh"]
    C --> D["Service/domain: mã lỗi nghiệp vụ ổn định"]
    D --> E["Adapter đầu ra: HTTP ProblemDetail / job outcome / event"]
    E --> F["Client: xử lý theo mã lỗi và hợp đồng"]
~~~

**Tầng 1 — LDAP protocol.** LDAP server có thể trả **resultCode** cùng **diagnosticMessage** trong LDAP response; một số lỗi kết nối/TLS xảy ra **trước khi nhận được LDAP response**, nên không có resultCode từ server để đọc.

**Tầng 2 — JNDI/Spring LDAP.** JNDI thường biểu diễn lỗi bằng các lớp kế thừa **javax.naming.NamingException**. Spring LDAP chuyển chúng thành hệ thống **runtime exception** thuộc **org.springframework.ldap**, giúp code ứng dụng không phải khai báo mọi checked exception. Tên ngoại lệ thực tế và lớp bọc bên ngoài có thể thay đổi theo API, Spring Data repository, thư viện hoặc phiên bản JDK.

**Tầng 3 — Application gateway.** Lớp này biết đang thực hiện **CREATE_USER**, **UPDATE_EMAIL**, **REMOVE_MEMBER** hay **SEARCH_USERS**. Nó đánh giá ngoại lệ cùng ngữ cảnh, chuyển sang mã nghiệp vụ và giữ nguyên nguyên nhân kỹ thuật cho log nội bộ.

**Tầng 4 — Giao tiếp với client.** REST có thể trả **404/409/422/503/500** cùng mã máy đọc được; batch job có thể đánh dấu một bản ghi là **SKIPPED_ALREADY_EXISTS**; event handler có thể chọn retry hoặc dead-letter. **Không đưa object ngoại lệ JNDI/Spring trực tiếp vào JSON response**.

### 2.1. Kết quả nghiệp vụ nên ổn định hơn thông điệp LDAP

Ví dụ các mã do ứng dụng tự định nghĩa:

~~~text
DIRECTORY_USER_NOT_FOUND
DIRECTORY_USER_ALREADY_EXISTS
DIRECTORY_INPUT_INVALID
DIRECTORY_DEPENDENCY_UNAVAILABLE
DIRECTORY_CONFIGURATION_ERROR
DIRECTORY_WRITE_REJECTED
DIRECTORY_OPERATION_FAILED
~~~

Đây **không phải mã lỗi chuẩn LDAP**. Chúng là mã của ứng dụng, được kiểm soát version và tài liệu hóa cho consumer. Nếu chuyển từ OpenLDAP sang Active Directory hoặc thay cách dùng LdapTemplate bằng repository, client vẫn có thể xử lý cùng một bộ mã.

## 3. LDAP result code: bản đồ tham khảo, không phải quy tắc 1–1

| Mã LDAP | Tên thường dùng | Ý nghĩa giao thức thường gặp | Hướng ánh xạ, tùy ngữ cảnh |
| --- | --- | --- | --- |
| **0** | success | Operation thành công | Trả kết quả thành công; search có thể trả 0 entry |
| **3** | timeLimitExceeded | Server hết ngân sách thời gian tìm kiếm | Kết quả tìm kiếm **không đầy đủ**, đánh dấu lỗi/giới hạn; cân nhắc 503 |
| **4** | sizeLimitExceeded | Vượt giới hạn số entry kết quả | Không coi tập đã trả là đầy đủ; thu hẹp query/paging |
| **8** | strongerAuthRequired | Server yêu cầu cơ chế xác thực mạnh hơn | Sự cố cấu hình transport/authentication |
| **10** | referral | Server chỉ ra directory/naming context khác | Xử lý theo chính sách referral và endpoint tin cậy |
| **16** | noSuchAttribute | Thuộc tính cần thao tác không tồn tại | Có thể là thiếu thành viên, yêu cầu không hợp lệ hoặc no-op theo hợp đồng |
| **19** | constraintViolation | Vi phạm ràng buộc directory | Kiểm tra policy/schema; không mặc định là dữ liệu client sai |
| **20** | attributeOrValueExists | Giá trị/thuộc tính đã tồn tại | Conflict hoặc idempotent success **chỉ sau khi kiểm tra** |
| **21** | invalidAttributeSyntax | Giá trị không đúng cú pháp attribute | Validation hoặc schema integration error |
| **32** | noSuchObject | DN đích hoặc một phần đường dẫn không tồn tại | UPDATE/LOOKUP có thể 404; CREATE dưới parent sai có thể 500 |
| **34** | invalidDNSyntax | DN request không hợp lệ | Kiểm tra cách tạo DN, tránh ghép chuỗi |
| **49** | invalidCredentials | Thông tin bind không được chấp nhận | User login: 401 chung chung; service bind: lỗi phụ thuộc |
| **50** | insufficientAccessRights | Bind identity thiếu quyền thao tác | Xem ai đang bind; service account thường là lỗi hạ tầng |
| **51** | busy | Server đang bận | Có thể retry có kiểm soát nếu thao tác an toàn |
| **52** | unavailable | Dịch vụ LDAP không sẵn sàng | 503/phụ thuộc không khả dụng |
| **53** | unwillingToPerform | Server từ chối theo chính sách | Kiểm tra policy; không tự suy lý do từ mã này |
| **65** | objectClassViolation | Entry vi phạm quy tắc objectClass/schema | Thường là lỗi schema/mapping hoặc validation |
| **68** | entryAlreadyExists | DN đã có một entry | CREATE: conflict 409, trừ khi có quy tắc idempotency |
| **80** | other | Lỗi server khác | Lưu diagnostic nội bộ, client nhận mã ổn định |

Các tên/mã thuộc LDAP result code theo RFC 4511. Một số thư viện cũng có **mã lỗi cục bộ của client** để chỉ mạng/TLS; không nhầm chúng với resultCode thực sự nhận từ LDAP response. **diagnosticMessage không phải hợp đồng công khai**: server có thể đổi câu chữ, mã phụ hoặc ngôn ngữ mà không thay ý nghĩa giao thức.

### 3.1. Những ngoại lệ Spring LDAP thường thấy

| Ngoại lệ Spring LDAP (gói **org.springframework.ldap**) | Ngữ cảnh thường gặp |
| --- | --- |
| **NameNotFoundException** | Lookup/modify dùng DN không tồn tại hoặc sai base/parent |
| **NameAlreadyBoundException** | Bind/tạo entry tại DN đã tồn tại |
| **AuthenticationException** | LDAP bind không thành công |
| **NoPermissionException** | Tài khoản hiện tại không được thực hiện thao tác |
| **SchemaViolationException** | Vi phạm schema/objectClass |
| **InvalidAttributeValueException** | Dữ liệu không đáp ứng cú pháp/ràng buộc attribute |
| **CommunicationException** | Mất kết nối, mạng hoặc lỗi giao tiếp với LDAP |
| **ServiceUnavailableException** | Dịch vụ directory không khả dụng |
| **SizeLimitExceededException / TimeLimitExceededException** | Search bị giới hạn; không được coi là complete success |
| **PartialResultException** | Một phần kết quả/referral hoặc hành vi provider tùy server |

**Không xem bảng là ánh xạ tuyệt đối cho mọi server và mọi thao tác.** JNDI có thể tạo ngoại lệ tổng quát, Spring Data có thể chuyển tiếp/bọc ngoại lệ, và lỗi TLS có thể nằm sâu ở **root cause**. Nếu cần nguyên nhân chính xác, quan sát **exception class + cause chain + LDAP result code khi có + loại thao tác**, không parse một chuỗi message duy nhất.

## 4. Cùng một lỗi LDAP, hai kết quả nghiệp vụ khác nhau

### 4.1. noSuchObject (32) trong UPDATE và CREATE

Khi gọi:

~~~java
ldapTemplate.modifyAttributes(
    personDn,
    modifications
);
~~~

nếu dịch vụ đã biết **ou=people,dc=example,dc=org** tồn tại và **personDn** được xây từ một UID hợp lệ, **NameNotFoundException** có thể được ánh xạ thành **DIRECTORY_USER_NOT_FOUND**.

Nhưng khi tạo:

~~~java
ldapTemplate.bind(personDn, null, attributes);
~~~

nếu chính **ou=people** chưa tồn tại, lỗi **noSuchObject (32)** thường phản ánh **thiếu parent/container trong directory**, không phải “người dùng không tồn tại” (đó là điều bình thường trước CREATE). Phản hồi phù hợp là lỗi cấu hình/hạ tầng, kèm alert cho người vận hành.

### 4.2. LDAP 49 trong đăng nhập và service bind

**Trường hợp A — người dùng đang đăng nhập bằng LDAP bind.** Nếu ứng dụng đã thiết lập TLS an toàn và thử bind với thông tin mà người dùng vừa cung cấp, thất bại vì credentials có thể dẫn tới **HTTP 401**, thông điệp chung: “Tên đăng nhập hoặc mật khẩu không hợp lệ”. Không trả chi tiết khóa tài khoản, có tồn tại DN hay không, hoặc mã nội bộ của Active Directory cho người ngoài.

**Trường hợp B — ứng dụng đọc directory bằng tài khoản dịch vụ.** Bind thất bại do mật khẩu của **uid=svc-reader** bị xoay vòng mà ứng dụng chưa cập nhật. Đây **không phải lỗi 401 của người gọi API**; không yêu cầu họ nhập lại mật khẩu. Hãy báo **directory dependency/configuration failure**, trả lỗi 503 hoặc 500 theo quy ước hệ thống và cảnh báo người vận hành.

**Bài học:** mã LDAP 49 không đủ để biết HTTP status. Phải xét **định danh đang được LDAP xác thực** và **ngữ cảnh nghiệp vụ**.

### 4.3. LDAP 50: quyền LDAP không đồng nghĩa HTTP 403

LDAP server đánh giá ACL cho **bind identity** được dùng trong thao tác. HTTP 403 chỉ hợp lý khi **người gọi đã được ứng dụng xác thực, có quyền được kiểm tra nhưng không được phép thao tác** theo chính sách ứng dụng.

Nếu HTTP user là quản trị viên có quyền **DIR_USER_WRITE** nhưng tài khoản dịch vụ LDAP bị mất quyền ghi **mail** sau thay đổi ACL, LDAP result 50 là **lỗi tích hợp**, không nên đổ lỗi cho HTTP user bằng 403. Cần xử lý như sự cố cấu hình phụ thuộc, audit và alert.

### 4.4. LDAP 65/19/21: lỗi client hay lỗi mapping?

Ví dụ tạo **inetOrgPerson** nhưng không có **sn** sẽ vi phạm schema. Nếu request có trường surname bắt buộc nhưng client bỏ qua, ứng dụng nên **validate trước khi gọi LDAP** rồi trả lỗi 400/422 ổn định. Nếu request đủ dữ liệu nhưng gateway mapping sai objectClass, đó là **bug nội bộ**, thích hợp với 500 và alert.

Các ràng buộc khác nhau giữa OpenLDAP, AD DS hoặc schema tùy chỉnh. Không quy tắc hóa rằng **mọi objectClassViolation đều là HTTP 422**; có thể đây là lỗi triển khai phần mềm.

### 4.5. LDAP 68 và idempotent CREATE

Nếu client tạo **uid=an** hai lần, server có thể trả **entryAlreadyExists (68)**. Kết quả mặc định cho POST tạo mới là **409 Conflict**.

Nếu hệ thống hỗ trợ **idempotency key**, lần gọi lặp có cùng khóa và cùng nội dung có thể trả lại kết quả đã lưu theo hợp đồng. **Không tự coi LDAP 68 là thành công**: entry hiện có có thể thuộc một yêu cầu khác hoặc có dữ liệu khác.

## 5. Thiết kế hợp đồng lỗi nghiệp vụ

Trước khi viết Java code, định nghĩa **kết quả nào là thành công**, **lỗi nào được client sửa**, **lỗi nào cần vận hành xử lý** và **lỗi nào có thể retry**.

| Mã nghiệp vụ của API | Mô tả ngắn, an toàn | HTTP thường chọn | Retry từ client? |
| --- | --- | --- | --- |
| **DIRECTORY_USER_NOT_FOUND** | Người dùng cần sửa không tồn tại | **404** | Không, trừ khi client kiểm tra lại trạng thái |
| **DIRECTORY_USER_ALREADY_EXISTS** | Đã có đối tượng với định danh yêu cầu | **409** | Không, cần thay định danh/đối soát |
| **DIRECTORY_INPUT_INVALID** | Request không hợp lệ theo hợp đồng ứng dụng | **400/422** | Không, cần sửa request |
| **DIRECTORY_DEPENDENCY_UNAVAILABLE** | Directory tạm không phục vụ request | **503** | Có điều kiện, backoff và ngân sách retry |
| **DIRECTORY_CONFIGURATION_ERROR** | Service bind/ACL/base/schema cấu hình không đúng | **500** hoặc **503** theo hợp đồng | Không retry mù; cần vận hành |
| **DIRECTORY_WRITE_REJECTED** | Directory từ chối ghi vì chính sách hoặc schema | **500/422** tùy lỗi thuộc phía server hay client | Không retry mù |
| **DIRECTORY_OPERATION_FAILED** | Lỗi directory chưa được phân loại | **500** | Không, cần điều tra |

Các HTTP status trên là **lựa chọn thiết kế gợi ý**, không phải trạng thái bắt buộc trong RFC LDAP. Hãy nhất quán giữa tài liệu OpenAPI, service và consumer. Nếu hệ thống dùng **RFC 9457 Problem Details**, luôn trả trường mã nghiệp vụ ổn định để client không phải đọc chuỗi tiếng Việt/tiếng Anh trong **detail**.

**Một quy tắc có ích:** chỉ công khai mã **USER_NOT_FOUND/USER_ALREADY_EXISTS** cho caller có quyền phù hợp để biết sự tồn tại của account. Trong luồng login hoặc tra cứu danh tính nhạy cảm, có thể cần **thông điệp đồng nhất** để tránh account enumeration.

## 6. Ví dụ xuyên tầng: gateway LDAP → lỗi miền → HTTP

Ví dụ dùng Java 17+, Spring Boot 3/Spring Framework 6 và Spring LDAP. Directory có suffix **dc=example,dc=org** và nhánh **ou=people**. Tài khoản dịch vụ được cấp quyền chỉ trong vùng nghiệp vụ phù hợp và kết nối **LDAPS**.

### 6.1. Cấu hình kết nối

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-directory,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Cấu hình trên cần CA trong truststore JVM và xác minh hostname SAN. Không tắt TLS verification để tránh lỗi **PKIX** hoặc **SSLHandshakeException**. Trong production, thường tách tài khoản **read-only** khỏi writer và quản lý secret qua secret manager/biến môi trường.

### 6.2. Định nghĩa mã lỗi và exception thuộc ứng dụng

~~~java
package org.example.directory;

public enum DirectoryErrorCode {
    USER_NOT_FOUND,
    USER_ALREADY_EXISTS,
    DEPENDENCY_UNAVAILABLE,
    CONFIGURATION_ERROR,
    WRITE_REJECTED,
    OPERATION_FAILED
}
~~~

~~~java
package org.example.directory;

public final class DirectoryFailure extends RuntimeException {
    private final DirectoryErrorCode code;

    public DirectoryFailure(
            DirectoryErrorCode code, Throwable cause) {
        super(code.name(), cause);
        this.code = code;
    }

    public DirectoryErrorCode code() {
        return code;
    }
}
~~~

~~~java
package org.example.directory;

public final class DirectoryInputException
        extends RuntimeException {
    public DirectoryInputException(String message) {
        super(message);
    }
}
~~~

Ở đây, **DirectoryFailure** là exception **của ứng dụng**, không nằm trong gói Spring LDAP. Nó giữ **cause** để vận hành phân tích nhưng chỉ cung cấp **code** ổn định cho tầng HTTP. **DirectoryInputException** dành riêng cho validation dữ liệu do client nhập; tránh bắt mọi **IllegalArgumentException** trên toàn hệ thống rồi mặc định trả 400 (một lỗi lập trình bên trong cũng có thể là IllegalArgumentException).

### 6.3. Gateway cho CREATE và UPDATE

~~~java
package org.example.directory;

import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryUserGateway {
    private final LdapTemplate ldapTemplate;

    public DirectoryUserGateway(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    private enum Operation { CREATE, UPDATE }

    public void createUser(
            String uid, String commonName, String surname) {
        validateUid(uid);
        requireText(commonName, "commonName", 200);
        requireText(surname, "surname", 100);

        Name dn = userDn(uid);
        Attributes attrs = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);
        attrs.put("uid", uid);
        attrs.put("cn", commonName);
        attrs.put("sn", surname);

        execute(Operation.CREATE,
                () -> ldapTemplate.bind(dn, null, attrs));
    }

    public void updateEmail(String uid, String email) {
        validateUid(uid);
        requireText(email, "email", 254);
        // Kiểm tra định dạng email theo chính sách sản phẩm ở lớp
        // validation; kiểm tra độ dài một mình chưa đủ.

        Name dn = userDn(uid);
        ModificationItem[] modifications = {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", email))
        };
        execute(Operation.UPDATE,
                () -> ldapTemplate.modifyAttributes(dn, modifications));
    }

    private void execute(Operation operation, Runnable action) {
        try {
            action.run();
        } catch (org.springframework.ldap.NamingException ex) {
            throw translate(ex, operation);
        }
    }

    private DirectoryFailure translate(
            org.springframework.ldap.NamingException ex,
            Operation operation) {

        DirectoryErrorCode code;
        if (ex instanceof org.springframework.ldap.NameAlreadyBoundException
                && operation == Operation.CREATE) {
            code = DirectoryErrorCode.USER_ALREADY_EXISTS;

        } else if (ex instanceof org.springframework.ldap.NameNotFoundException
                && operation == Operation.UPDATE) {
            code = DirectoryErrorCode.USER_NOT_FOUND;

        } else if (ex instanceof org.springframework.ldap.CommunicationException
                || ex instanceof org.springframework.ldap.ServiceUnavailableException) {
            code = DirectoryErrorCode.DEPENDENCY_UNAVAILABLE;

        } else if (ex instanceof org.springframework.ldap.AuthenticationException
                || ex instanceof org.springframework.ldap.NoPermissionException) {
            // Ở đây LDAP bind dùng service account, không phải
            // credentials của HTTP caller.
            code = DirectoryErrorCode.CONFIGURATION_ERROR;

        } else if (ex instanceof org.springframework.ldap.SchemaViolationException
                || ex instanceof org.springframework.ldap.InvalidAttributeValueException) {
            code = DirectoryErrorCode.WRITE_REJECTED;

        } else if (ex instanceof org.springframework.ldap.NameNotFoundException) {
            // CREATE thất bại vì parent DN không tồn tại;
            // không được trả USER_NOT_FOUND.
            code = DirectoryErrorCode.CONFIGURATION_ERROR;

        } else {
            code = DirectoryErrorCode.OPERATION_FAILED;
        }
        return new DirectoryFailure(code, ex);
    }

    private static Name userDn(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new DirectoryInputException("uid không hợp lệ");
        }
    }

    private static void requireText(
            String value, String field, int maxLength) {
        if (value == null || value.isBlank()
                || value.length() > maxLength) {
            throw new DirectoryInputException(
                    field + " không hợp lệ");
        }
    }
}
~~~

**Ý nghĩa của mẫu gateway:**

1. **Không để controller biết lớp ngoại lệ Spring LDAP.** Nó chỉ biết **DirectoryInputException** và **DirectoryFailure**.
2. **Bối cảnh Operation quyết định cách hiểu NameNotFoundException.** UPDATE có thể là user missing; CREATE có thể là parent missing.
3. **LDAP bind thực hiện bằng service account.** Lỗi 49/50 được phân loại là sự cố cấu hình/quyền, không biến thành 401/403 cho HTTP caller.
4. **LdapNameBuilder** tạo DN an toàn, không nối chuỗi UID vào DN. Trong config này, DN truyền vào template là **uid=...,ou=people** tương đối với **dc=example,dc=org**.
5. **Schema vẫn nằm ở LDAP server.** CREATE phải có **cn**, **sn** theo objectClass chain và cần parent tồn tại; account phải đủ quyền.
6. **WRITE_REJECTED** trong mẫu phản ánh một lỗi tích hợp chung. Trong hệ thống thật, chỉ chuyển nó thành mã input invalid nếu xác định chắc nguyên nhân thuộc dữ liệu caller, không chỉ dựa trên tên exception.

Mẫu tập trung vào các exception thông dụng. Nếu ứng dụng có retry, audit, tracing hoặc nhận exception qua một lớp wrapper khác, cần bổ sung translation tại **ranh giới gateway**, thay vì bắt **RuntimeException** rồi giả vờ mọi lỗi đều từ LDAP.

### 6.4. Ánh xạ sang HTTP ProblemDetail

Spring Framework 6 có **ProblemDetail**, thích hợp cho phản hồi lỗi có cấu trúc:

~~~java
package org.example.directory;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DirectoryErrorHandler {

    @ExceptionHandler(DirectoryInputException.class)
    public ResponseEntity<ProblemDetail> badInput(
            DirectoryInputException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Dữ liệu yêu cầu không hợp lệ");
        problem.setTitle("Invalid directory request");
        problem.setProperty("code", "DIRECTORY_INPUT_INVALID");
        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(DirectoryFailure.class)
    public ResponseEntity<ProblemDetail> directoryFailure(
            DirectoryFailure ex) {

        HttpStatus status = switch (ex.code()) {
            case USER_NOT_FOUND -> HttpStatus.NOT_FOUND;
            case USER_ALREADY_EXISTS -> HttpStatus.CONFLICT;
            case DEPENDENCY_UNAVAILABLE -> HttpStatus.SERVICE_UNAVAILABLE;
            case CONFIGURATION_ERROR, WRITE_REJECTED, OPERATION_FAILED ->
                    HttpStatus.INTERNAL_SERVER_ERROR;
        };

        String publicCode = switch (ex.code()) {
            case USER_NOT_FOUND -> "DIRECTORY_USER_NOT_FOUND";
            case USER_ALREADY_EXISTS -> "DIRECTORY_USER_ALREADY_EXISTS";
            case DEPENDENCY_UNAVAILABLE ->
                    "DIRECTORY_DEPENDENCY_UNAVAILABLE";
            case CONFIGURATION_ERROR, WRITE_REJECTED, OPERATION_FAILED ->
                    "DIRECTORY_OPERATION_FAILED";
        };

        String detail = switch (ex.code()) {
            case USER_NOT_FOUND -> "Không tìm thấy người dùng";
            case USER_ALREADY_EXISTS ->
                    "Định danh người dùng đã tồn tại";
            default -> "Không thể hoàn thành thao tác thư mục";
        };

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(status, detail);
        problem.setTitle("Directory operation failed");
        problem.setProperty("code", publicCode);

        // Không sử dụng ex.getMessage() hoặc LDAP diagnostic
        // làm nội dung công khai.
        return ResponseEntity.status(status).body(problem);
    }
}
~~~

Ở ví dụ này, những sự cố hạ tầng chi tiết như bind configuration, ACL và schema đều được **gộp thành mã công khai DIRECTORY_OPERATION_FAILED**, hạn chế lộ chi tiết nội bộ. Log nội bộ có thể ghi mã **DirectoryErrorCode** đầy đủ hơn. Hệ thống production nên gắn thêm **traceId/correlationId** vào ProblemDetail nếu đã có cơ chế tracing, thay vì tự sinh chuỗi tùy tiện.

Ví dụ phản hồi khi tạo một UID đã tồn tại:

~~~json
{
  "type": "about:blank",
  "title": "Directory operation failed",
  "status": 409,
  "detail": "Định danh người dùng đã tồn tại",
  "code": "DIRECTORY_USER_ALREADY_EXISTS"
}
~~~

Phản hồi trên chỉ thích hợp khi caller **có quyền biết việc định danh đó đã tồn tại**. Trong endpoint tự đăng ký tài khoản công khai, cần cân nhắc phản hồi không tiết lộ account existence và xử lý chống enumeration riêng.

### 6.5. Một REST controller dùng gateway

~~~java
package org.example.directory;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/directory/users")
public class DirectoryUserController {

    private final DirectoryUserGateway gateway;

    public DirectoryUserController(DirectoryUserGateway gateway) {
        this.gateway = gateway;
    }

    public record CreateUserRequest(
            String uid, String commonName, String surname) {}

    public record EmailRequest(String email) {}

    @PostMapping
    public ResponseEntity<Void> create(
            @RequestBody CreateUserRequest request) {
        gateway.createUser(
                request.uid(), request.commonName(), request.surname());
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    @PatchMapping("/{uid}/email")
    public ResponseEntity<Void> changeEmail(
            @PathVariable String uid,
            @RequestBody EmailRequest request) {
        gateway.updateEmail(uid, request.email());
        return ResponseEntity.noContent().build();
    }
}
~~~

**Ví dụ controller chưa bao gồm cơ chế xác thực/ủy quyền HTTP**. Khi tích hợp thực tế, phải áp dụng Spring Security hoặc gateway policy, chỉ cho caller có quyền quản trị thích hợp được phép CREATE/UPDATE và kiểm soát CSRF theo loại client. **ACL LDAP và quyền HTTP là hai lớp khác nhau**: service account có quyền sửa LDAP không có nghĩa mọi người gọi HTTP API đều được quyền đó.

Không triển khai POST công khai cho thao tác cấp tài khoản nếu chưa có quy tắc định danh, phê duyệt và chống lạm dụng.

## 7. Search và lookup: không tìm thấy có phải lỗi?

### 7.1. Tìm danh sách thành công nhưng rỗng

~~~java
List<String> names = ldapTemplate.search(
        query().base("ou=people")
                .where("uid").is("unknown"),
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

Nếu LDAP search thực thi thành công và không có entry nào khớp, kết quả thường là **danh sách rỗng**. Đây là kết quả nghiệp vụ hợp lệ: API tìm kiếm có thể trả **200 OK** với **items: []**.

Không ném **USER_NOT_FOUND** mỗi khi một truy vấn danh sách không có kết quả. Sự phân biệt giữa **GET một resource cụ thể** và **GET danh sách theo filter** nên là một phần hợp đồng API.

### 7.2. Lookup đúng DN nhưng entry không tồn tại

Khi thực hiện **ldapTemplate.lookup(dn, mapper)** để lấy một resource cụ thể, **NameNotFoundException** thường phù hợp với **404** khi base DN đã được xác minh. Nếu client truyền một DN tùy ý, phải kiểm tra scope và quyền trước, không để lỗi LDAP tự quyết định liệu client có được biết sự tồn tại của entry.

### 7.3. Giới hạn tìm kiếm không đồng nghĩa trả rỗng

**TimeLimitExceededException**, **SizeLimitExceededException** hoặc **PartialResultException** cần được xử lý khác với search hoàn tất:

- Có thể server đã xét một phần entry hoặc đã trả dữ liệu một phần.
- Các trang kết quả chưa được lấy đủ, referral chưa được xử lý hoặc directory có giới hạn riêng.
- Không được biến lỗi thành **Collections.emptyList()** rồi trả 200 “không tìm thấy”, vì consumer có thể đưa ra kết luận nghiệp vụ sai.

Nếu API chỉ cần tối đa 50 kết quả, hãy thiết kế **giới hạn hợp lệ ngay từ đầu** và trả metadata như **truncated** khi ứng dụng thực sự xác định được kết quả bị giới hạn. Không tự suy luận **truncated=false** chỉ vì chưa nhận exception.

## 8. Lỗi thành viên nhóm và thao tác có thể lặp

Ở nhóm **groupOfNames**, thuộc tính **member** chứa nhiều DN; ở **groupOfUniqueNames** là **uniqueMember**. Giả sử cần thêm:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

vào **cn=backend,ou=groups,dc=example,dc=org**.

Các kết quả có thể gặp:

| Tình huống | Lỗi LDAP thường gặp | Kết quả nghiệp vụ tùy API |
| --- | --- | --- |
| Thêm DN thành viên chưa có | success | **MEMBER_ADDED** |
| Thêm DN đã có | **attributeOrValueExists (20)** | **MEMBER_ALREADY_PRESENT** hoặc no-op success nếu hợp đồng yêu cầu |
| Xóa DN không nằm trong nhóm | **noSuchAttribute (16)** hoặc kết quả khác theo server | **MEMBER_NOT_PRESENT** hoặc no-op success |
| Xóa thành viên cuối của groupOfNames | **objectClassViolation (65)** do member là MUST | **CANNOT_REMOVE_LAST_MEMBER** nếu được xác định chắc |
| Nhóm không tồn tại | **noSuchObject (32)** | **GROUP_NOT_FOUND** nếu parent/base hợp lệ |
| Server từ chối do ACL | **insufficientAccessRights (50)** | Sự cố quyền của bind identity hoặc lỗi ủy quyền, tùy bối cảnh |

**Idempotency không phải là “nuốt mọi exception”.** Với API **ensureMember(group, person)**, nếu LDAP báo **attributeOrValueExists**, service có thể đọc lại để xác minh đúng DN thành viên rồi trả thành công. Với API **addMember** mang nghĩa “phải tạo quan hệ mới”, mã **MEMBER_ALREADY_PRESENT** có thể thích hợp hơn.

Một giá trị LDAP kiểu DN có thể được so sánh theo quy tắc matching rule của directory; đừng chỉ so String thô khi đối chiếu các thành viên. Khi xóa thành viên cuối, phải hiểu schema không cho phép nhóm rỗng; không dùng DN giả để lách rule nếu nhóm đó tham gia cấp quyền.

## 9. Retry: phân biệt lỗi tạm thời và kết quả ghi không chắc chắn

Không phải mọi lỗi LDAP đều phù hợp retry:

| Nhóm lỗi | Có nên retry tự động? | Lý do |
| --- | --- | --- |
| **busy (51)**, **unavailable (52)** | Có thể, với backoff/jitter và giới hạn | Server tạm bận hoặc không sẵn sàng |
| **CommunicationException / timeout** ở truy vấn đọc | Có thể với ngân sách thời gian hữu hạn | Đọc thường an toàn để lặp, nhưng vẫn tạo tải |
| **CommunicationException** sau thao tác ghi | **Không retry mù** | Request có thể đã được server áp dụng trước khi mất phản hồi |
| **entryAlreadyExists (68)** | Không retry nguyên trạng | Xung đột trạng thái, trừ quy trình idempotency đã xác minh |
| **invalidCredentials (49)** cho service account | Không | Cần sửa secret/tài khoản, retry có thể gây lockout |
| **insufficientAccessRights (50)** | Không | Quyền LDAP chưa đổi thì retry vô ích |
| **objectClassViolation (65)** | Không | Cần sửa schema/mapping/dữ liệu |
| **invalidDNSyntax (34)** | Không | Cần sửa cách tạo DN/request |

### 9.1. Vấn đề “unknown outcome” của thao tác ghi

~~~mermaid
sequenceDiagram
    participant App as Spring service
    participant LDAP as LDAP server
    App->>LDAP: Add uid=an
    LDAP->>LDAP: Tạo entry thành công
    LDAP--xApp: Mất kết nối trước response
    Note over App: Client thấy CommunicationException
    Note over LDAP: Entry có thể đã tồn tại
~~~

Nếu App lập tức gửi lại **Add**, LDAP có thể trả **entryAlreadyExists (68)**. Điều đó **không chứng minh lần đầu thất bại**. Với những thao tác ghi có hậu quả đáng kể, cân nhắc:

1. Dùng **idempotency key** trong tầng ứng dụng nếu API hỗ trợ, lưu được trạng thái request và kết quả đã ghi.
2. Khi nhận lỗi mạng sau ghi, **đọc lại trạng thái** theo DN/thuộc tính để xác minh mong đợi, nếu chính sách quyền và nhất quán cho phép.
3. Phân biệt **“đã hoàn thành”**, **“chưa hoàn thành”** và **“chưa xác định”**, nhất là khi dữ liệu sẽ được đồng bộ sang hệ thống khác.
4. Chỉ retry theo chính sách riêng cho thao tác có thể lặp an toàn và có **backoff, jitter, tối đa số lần/thời gian**.
5. Đừng coi **@Transactional** của JDBC tự động bao trùm LDAP và database quan hệ trong một transaction phân tán.

Với quy trình nhiều entry hoặc vừa ghi LDAP vừa ghi database, hãy thiết kế **compensation/outbox/reconciliation** theo yêu cầu nghiệp vụ. LDAP Modify trên một entry không đồng nghĩa mọi bước xuyên hệ thống đều atomic.

## 10. Lỗi xác thực và tránh rò rỉ thông tin

Ứng dụng có thể gặp hai cách làm việc khác nhau với credentials:

- **Service bind:** ứng dụng dùng một DN/mật khẩu kỹ thuật để đọc hoặc ghi LDAP.
- **User bind/authentication:** ứng dụng thử xác thực credentials mà một người dùng cung cấp.

### 10.1. Service bind thất bại

LDAP **invalidCredentials (49)** của service bind là lỗi phụ thuộc/cấu hình, không nên trả 401 chỉ vì HTTP request đã được xác thực. Cần ghi cảnh báo an toàn và sửa secret, thời hạn mật khẩu, trạng thái tài khoản hoặc cơ chế xác thực.

### 10.2. User bind thất bại

Đối với API đăng nhập, trả **401** hoặc một kết quả xác thực chung là lựa chọn thông dụng, nhưng phải **không tiết lộ thông tin đủ để liệt kê tài khoản**. Một số Active Directory server có các **mã phụ trong diagnosticMessage** về mật khẩu, khóa tài khoản hoặc chính sách. Những mã phụ có thể hữu ích cho vận hành theo chính sách nhưng **không được coi là hợp đồng LDAP portable** và không nên đưa thẳng ra public API.

Các biện pháp bổ sung:

- Áp dụng rate limit, chính sách chống brute-force và kiểm soát account lockout.
- Không log mật khẩu, LDAP simple-bind credentials, Authorization header hoặc toàn bộ exception message có thể chứa thông tin nhạy cảm.
- Thực hiện bind có mật khẩu qua **LDAPS/StartTLS xác minh chứng chỉ**; không fallback sang simple bind không mã hóa.
- Đối chiếu quyền API của caller với ACL LDAP; không mặc định một lỗi ACL tương đương lỗi HTTP authorization.

## 11. Logging, observability và khả năng vận hành

Một bản ghi sự cố hữu ích cần đủ ngữ cảnh để truy nguyên nhưng không lộ bí mật. Các trường nên xem xét:

| Trường nội bộ | Ví dụ | Vì sao cần |
| --- | --- | --- |
| **operation** | UPDATE_USER_EMAIL | Biết nghiệp vụ đang thực hiện |
| **errorCode** | CONFIGURATION_ERROR | Nhóm nguyên nhân ổn định |
| **ldapResultCode** nếu có | 50 | Đối chiếu server LDAP |
| **exceptionType** | NoPermissionException | Xác định tầng lỗi |
| **directoryAlias** | people-primary | Biết ContextSource nào được sử dụng mà không lộ endpoint nhạy cảm |
| **correlationId/traceId** | Một ID từ tracing | Ghép log request, service, LDAP |
| **durationMs** | Thời gian đo của thao tác | Nhận biết timeout/gián đoạn |
| **resourceRef** | Hash hoặc định danh đã mask | Tìm đúng entry mà không in toàn bộ DN/PII |

Không log **password**, raw bind request, thông tin chứng chỉ private key, access token hoặc toàn bộ LDAP attributes. DN, search filter và diagnosticMessage có thể chứa thông tin cá nhân; cần phân loại dữ liệu trước khi ghi log.

**Chỉ số vận hành** nên bao gồm: tỷ lệ lỗi theo mã nghiệp vụ/loại thao tác, timeout, connection failures, bind failures của service account, LDAP result code phổ biến, p95/p99 latency và retry count. Với **CONFIGURATION_ERROR** hoặc **WRITE_REJECTED** tăng đột ngột sau deployment, cần alert đội vận hành chứ không chỉ chờ client báo lỗi.

## 12. Kiểm thử ánh xạ lỗi bằng unit test

Không nhất thiết phải dựng directory thật cho **mọi trường hợp translator**. Vì kết quả phụ thuộc vào **exception + loại thao tác**, có thể dùng **Mockito** giả lập LdapTemplate ném lỗi rồi kiểm tra trực tiếp **DirectoryUserGateway**. Ví dụ dùng JUnit Jupiter và Mockito (thường có trong **spring-boot-starter-test**):

~~~java
package org.example.directory;

import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NameNotFoundException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class DirectoryFailureMappingTest {
    @Test
    void mapsCreateDuplicateToConflict() {
        LdapTemplate template = mock(LdapTemplate.class);
        doThrow(new NameAlreadyBoundException(
                new javax.naming.NameAlreadyBoundException("exists")))
                .when(template)
                .bind(any(Name.class), isNull(), any(Attributes.class));

        DirectoryFailure error = assertThrows(
                DirectoryFailure.class,
                () -> new DirectoryUserGateway(template)
                        .createUser("an", "An Tran", "Tran"));

        assertEquals(DirectoryErrorCode.USER_ALREADY_EXISTS,
                error.code());
    }

    @Test
    void mapsUpdateMissingToNotFound() {
        LdapTemplate template = mock(LdapTemplate.class);
        doThrow(new NameNotFoundException(
                new javax.naming.NameNotFoundException("missing")))
                .when(template)
                .modifyAttributes(
                        any(Name.class), any(ModificationItem[].class));

        DirectoryFailure error = assertThrows(
                DirectoryFailure.class,
                () -> new DirectoryUserGateway(template)
                        .updateEmail("missing", "test@example.org"));

        assertEquals(DirectoryErrorCode.USER_NOT_FOUND, error.code());
    }

    @Test
    void doesNotMistakeMissingCreateParentForMissingUser() {
        LdapTemplate template = mock(LdapTemplate.class);
        doThrow(new NameNotFoundException(
                new javax.naming.NameNotFoundException("no parent")))
                .when(template)
                .bind(any(Name.class), isNull(), any(Attributes.class));

        DirectoryFailure error = assertThrows(
                DirectoryFailure.class,
                () -> new DirectoryUserGateway(template)
                        .createUser("an", "An Tran", "Tran"));

        assertEquals(DirectoryErrorCode.CONFIGURATION_ERROR,
                error.code());
    }
}
~~~

Ví dụ kiểm thử **đúng gateway đã viết ở phần 6**, không tạo một thuật toán mapping khác chỉ để test. Nó minh họa nguyên tắc **cùng NameNotFoundException, khác operation → mã khác nhau**. Chuỗi **"exists"**, **"missing"** hoặc **"no parent"** chỉ là message giả trong JNDI cause; translator dựa trên **loại ngoại lệ và bối cảnh thao tác**, không parse nội dung message. Phép thử này chưa thay thế kiểm thử tích hợp với server thực.

### 12.1. Test tầng REST contract

Ở tầng HTTP, có thể unit-test **DirectoryErrorHandler** với DirectoryFailure và kiểm tra:

- **USER_NOT_FOUND** → 404 + **DIRECTORY_USER_NOT_FOUND**.
- **USER_ALREADY_EXISTS** → 409 + **DIRECTORY_USER_ALREADY_EXISTS**.
- **DEPENDENCY_UNAVAILABLE** → 503 + **DIRECTORY_DEPENDENCY_UNAVAILABLE**.
- **CONFIGURATION_ERROR/WRITE_REJECTED** → 500 + mã công khai chung.
- **DirectoryInputException** → 400 + **DIRECTORY_INPUT_INVALID**.
- **Không có LDAP password, DN đầy đủ hoặc ex.getMessage()** trong ProblemDetail.

Nếu backend cho phép user login, kiểm thử luồng **401 chung** và không tiết lộ account existence riêng với gateway cập nhật người dùng của ví dụ.

## 13. Kiểm thử tích hợp với LDAP directory

Một integration test cần dùng **LdapTemplate/Repository thực** và server có schema phù hợp. Chuẩn bị nhánh:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
~~~

Các tài khoản bind test nên tách **writer** và **reader**, dùng dữ liệu test độc lập với production. Trước khi chạy các ca lỗi mạng hoặc chứng chỉ, cô lập môi trường để không ảnh hưởng directory dùng chung.

| Ca kiểm thử | Thiết lập/tác vụ | Kết quả nghiệp vụ kỳ vọng |
| --- | --- | --- |
| **CREATE thành công** | Tạo uid=an với cn/sn và schema đúng | Thành công, entry tồn tại |
| **CREATE trùng DN** | Gọi tạo lại uid=an | **USER_ALREADY_EXISTS**, không overwrite |
| **UPDATE user không tồn tại** | Sửa uid=khongco, parent hợp lệ | **USER_NOT_FOUND** |
| **CREATE thiếu parent** | Cấu hình base/OU sai trong fixture | **CONFIGURATION_ERROR**, không 404 |
| **Bind service sai password** | Dùng credentials test không hợp lệ | **CONFIGURATION_ERROR** hoặc lỗi hạ tầng theo chính sách |
| **Writer thiếu ACL** | Bind bằng tài khoản chỉ đọc | Lỗi quyền của service; không mặc nhiên trả HTTP 403 |
| **Thiếu cn/sn** | Gửi dữ liệu trống tới validation | **DIRECTORY_INPUT_INVALID**, không gửi LDAP Add |
| **Schema/mapping sai** | Cố tạo entry vi phạm objectClass trên test server | **WRITE_REJECTED**, alert về integration |
| **LDAP không khả dụng** | Dừng test LDAP server hoặc chặn kết nối | **DEPENDENCY_UNAVAILABLE** nếu được phân loại đúng |
| **TLS sai CA/SAN** | Dùng certificate test không đáng tin | Kết nối thất bại an toàn, không tự tắt verify |
| **Search không có kết quả** | Tìm uid chưa có dưới OU hợp lệ | Danh sách rỗng hợp lệ |
| **Search size/time limit** | Truy vấn bị giới hạn trong fixture | Không trả false-success có tập kết quả không đầy đủ |
| **Thêm member đã có** | Lặp LDAP Modify ADD với giá trị đã tồn tại | Conflict hoặc no-op có xác minh, tùy hợp đồng |
| **Lỗi mạng sau ghi** | Mô phỏng mất response sau khi server áp dụng | Trạng thái “chưa xác định”, đối soát trước retry |

**Điểm cần cảnh giác khi thử lỗi 32:** một **noSuchObject** có thể phát sinh do entry bị thiếu hoặc base DN/parent bị sai. Fixture phải phân biệt hai tình huống này, nếu không unit test có thể cho cảm giác translator đúng nhưng integration vẫn trả sai 404.

### 13.1. Kiểm tra tương thích directory

Với **OpenLDAP**, policy của attribute uniqueness, index và schema phụ thuộc cấu hình. Với **Active Directory**, thao tác tạo user, đổi mật khẩu, objectClass và quyền có quy tắc đặc thù; **unwillingToPerform (53)** hay **constraintViolation (19)** có thể chứa các nguyên nhân khác nhau theo chính sách AD. Không chuẩn hóa mọi message của nhà cung cấp thành một mã nghiệp vụ chỉ bằng regex.

Đối với Spring Data LDAP repository, cùng một lỗi có thể xuất hiện qua một lớp exception wrapper khác với khi gọi LdapTemplate trực tiếp. Test phải đi qua **API thật mà service sử dụng**, không chỉ test các ngoại lệ được ném giả định.

## 14. Những phản mẫu phổ biến

| Phản mẫu | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| **catch (Exception) → HTTP 500** | Mất ý nghĩa 404, 409 và retry | Translator theo operation + domain error |
| **catch (NamingException) → HTTP 400** | Đổ lỗi cho client khi LDAP server/TLS lỗi | Phân biệt client validation và lỗi phụ thuộc |
| **LDAP 49 → HTTP 401** trong mọi API | Dịch vụ bind sai bị xem là lỗi người dùng | Phân biệt service bind và user bind |
| **LDAP 50 → HTTP 403** trong mọi API | Lộ cấu hình ACL và trả sai ý nghĩa quyền | Ánh xạ theo bind identity và policy HTTP |
| **LDAP 32 → 404** cho mọi thao tác | CREATE thiếu parent bị nhận sai | Dùng operation context |
| **LDAP 65 → 422** vô điều kiện | Bug ánh xạ schema bị đổ cho client | Validate trước, xem nguyên nhân thuộc ai |
| **Search exception → []** | Trả false-success khi timeout/size limit | Trả lỗi/partial theo hợp đồng rõ ràng |
| **Retry mọi lỗi LDAP** | Tăng tải, lockout hoặc tạo bản ghi trùng | Retry phân loại, có backoff và idempotency |
| **Đưa LDAP diagnosticMessage vào JSON** | Rò rỉ account state, DN hoặc topology | Mã công khai ổn định; log nội bộ hạn chế |
| **Log mật khẩu trong exception** | Lộ bí mật và PII | Redact log, policy lưu trữ và quyền đọc |
| **Dùng String concat cho DN/filter** | LDAP injection, truy vấn sai phạm vi | LdapNameBuilder và LdapQueryBuilder |
| **Nhầm Spring bean khởi động với LDAP healthy** | Runtime mới thấy lỗi bind/TLS | Health check phù hợp và integration test |

## 15. Checklist áp dụng trong hệ thống thật

1. **Xác định nghiệp vụ:** CREATE, UPDATE, GET một entry, LIST, ADD/REMOVE member, AUTHENTICATE có hợp đồng lỗi khác nhau.
2. **Ghi rõ bối cảnh LDAP:** URL/ContextSource nào, base DN, schema và bind identity nào được dùng.
3. **Validate trước khi gửi:** allowlist attribute, schema nghiệp vụ, ký tự, chiều dài, DN/filter escaping.
4. **Dùng translator tại gateway:** phân loại exception/cause + operation; giữ cause nội bộ, không đưa ra API.
5. **Định nghĩa mã công khai:** ổn định qua các directory implementation, không dựa vào diagnostic message.
6. **Phân biệt 401/403 của HTTP với 49/50 của LDAP:** caller identity và bind identity có thể khác nhau.
7. **Xử lý kết quả không đầy đủ:** search time/size limit, referral, paging và lỗi mạng không tương đương danh sách rỗng.
8. **Retry có điều kiện:** chỉ thao tác phù hợp, có ngân sách, backoff/jitter, xác minh kết quả ghi không chắc chắn.
9. **Bảo mật:** TLS xác minh CA/SAN, bind account quyền tối thiểu, không lộ credentials/PII trong log.
10. **Đo và kiểm thử:** unit test translator, HTTP contract, integration test LDAP schema/ACL/TLS, alert vận hành cho lỗi cấu hình.

## 16. Tổng kết và câu hỏi tự luyện

**Ánh xạ lỗi LDAP sang kết quả nghiệp vụ** là một phần thiết yếu của tích hợp ứng dụng. LDAP result code và Spring LDAP exception giúp biết **thao tác directory đã gặp điều gì**; nhưng chỉ khi kết hợp với **mục đích thao tác, người đang bind và hợp đồng ứng dụng**, ta mới xác định được lỗi nào là **404, 409, 400/422, 503 hay 500**.

Với **Spring Data LDAP repository/LdapTemplate**, hãy đặt ranh giới chuyển đổi lỗi trong **gateway/adapter**, dùng **domain error codes** để service và consumer không phụ thuộc cấu trúc exception của nhà cung cấp. Áp dụng cùng nguyên tắc cho tìm kiếm, CRUD, thao tác thành viên nhóm, kiểm soát DN/schema/filter và xử lý hạ tầng TLS/ACL. **Không đánh dấu một request thành công nếu thực tế chỉ nhận kết quả một phần hoặc trạng thái ghi chưa chắc chắn**.

**Câu hỏi tự luyện:**

1. Khi UPDATE user gặp **noSuchObject (32)**, bạn sẽ kiểm tra điều gì trước khi trả 404? Trường hợp CREATE dưới parent không tồn tại nên trả thế nào?
2. Tại sao **invalidCredentials (49)** của service bind không có nghĩa HTTP caller phải đăng nhập lại?
3. Phân biệt LDAP **insufficientAccessRights (50)** với HTTP 403. Khi nào caller được phép biết trạng thái ACL?
4. Tại sao **objectClassViolation (65)** có thể là bug của ứng dụng thay vì lỗi request của client?
5. Tạo bảng mapping cho **addMember**: thành công, member đã có, group không có, xóa member cuối và thiếu quyền ghi.
6. Vì sao cần phân biệt **search trả []** với **timeLimitExceeded/sizeLimitExceeded**?
7. Trong tình huống gửi LDAP Add thành công rồi mất response, retry vô điều kiện có thể làm gì sai? Hãy thiết kế một quy trình đối soát.
8. Đề xuất cấu trúc ProblemDetail có mã lỗi ổn định nhưng không lộ password, DN đầy đủ, LDAP diagnostic và thông tin tài khoản.
9. Nếu di chuyển từ OpenLDAP sang AD DS, lớp nào nên chịu trách nhiệm giữ nguyên hợp đồng lỗi với consumer?

### Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — LDAP operations, result codes, referrals và điều kiện lỗi.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513) — LDAP bind, yêu cầu bảo vệ kết nối và xác thực.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457) — hợp đồng phản hồi lỗi HTTP có cấu trúc.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — LdapTemplate, chuyển đổi ngoại lệ, ContextSource và các thao tác LDAP.
- [Spring LDAP API](https://docs.spring.io/spring-ldap/docs/current/api/) — các exception và LdapTemplate.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — repository, ODM và integration pattern.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html) — ProblemDetail và @ExceptionHandler trong Spring MVC.
