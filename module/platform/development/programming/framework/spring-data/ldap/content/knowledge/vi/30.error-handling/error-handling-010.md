# Giữ thông tin chẩn đoán nhưng che DN hoặc thuộc tính nhạy cảm

Trong chương **Xử lý lỗi** của **SPRING_DATA_LDAP**, log là công cụ giúp tìm nguyên nhân khi directory không phản hồi, Bind bị từ chối, Search vượt giới hạn hoặc thao tác ghi gặp lỗi schema/ACL. Tuy nhiên, exception LDAP thường mang theo nhiều dữ liệu hơn một mã lỗi: DN đang được truy cập, phần tên còn lại/chưa resolve, filter Search, referral URI, diagnostic message của server hoặc giá trị attribute. Những dữ liệu này có thể chứa tên, email, mã nhân viên, cấu trúc OU, hostname nội bộ và thông tin bảo mật.

Ví dụ, một request tìm nhân viên theo email có thể phát sinh NameNotFoundException. Nếu log toàn bộ exception bằng log.error("LDAP failed", ex), message/cause có thể chứa tên entry, DN hoặc chi tiết do LDAP server trả về. Nếu log raw filter, email người dùng cũng bị lưu trong hệ thống log. Log khi đó trở thành một bản sao dữ liệu directory, thường được gửi tới nhiều hệ thống và được nhiều nhóm người truy cập hơn.

Mục tiêu không phải xóa sạch thông tin chẩn đoán. Ứng dụng vẫn cần biết **operation nào lỗi, lỗi thuộc nhóm nào, result code nào được xác minh, directory alias nào được gọi, mất bao lâu, có retry hay không và request nào liên quan**. Cách làm an toàn là ghi theo allowlist, dùng mã tương quan, tham chiếu DN dạng giả danh có khóa, giữ exception details trong phạm vi kiểm soát và trả thông báo công khai đã chuẩn hóa.

**Mục tiêu:** nhận diện dữ liệu nhạy cảm trong LDAP diagnostics; hiểu exception hierarchy của Spring LDAP và result message theo RFC 4511; tránh ghi raw DN, filter, attribute value, diagnosticMessage và exception message; xây dựng structured log có thể truy vết; dùng HMAC để tương quan DN mà không công khai DN; phân loại lỗi mà không phụ thuộc message text; tách log nội bộ khỏi response API; và kiểm thử redaction, log injection, retry cùng khả năng điều tra sự cố.

## 1. Vì sao lỗi LDAP có thể làm lộ dữ liệu?

Một LDAP result có thể chứa nhiều trường:

| Trường | Ý nghĩa | Rủi ro khi ghi nguyên văn |
| --- | --- | --- |
| resultCode | Mã kết quả protocol | Thường phù hợp để ghi nếu được lấy có cấu trúc |
| matchedDN | DN của entry cuối cùng được dùng khi tìm target/base trong một số lỗi | Có thể tiết lộ tên, UID, OU hoặc sự tồn tại của entry |
| diagnosticMessage | Chuỗi chẩn đoán tùy chọn do server cung cấp | Không chuẩn hóa; có thể chứa DN, tên attribute, giá trị hoặc thông tin server |
| referral | URI/endpoint của server khác | Có thể lộ hostname, port, base DN và topology |
| Exception message/cause | Thông tin do JNDI/provider/Spring bọc lại | Có thể chứa các trường phía trên hoặc chi tiết TLS/network |
| Search filter | Điều kiện truy vấn LDAP | Có thể chứa UID, email, mã nhân viên hoặc dữ liệu người dùng |
| DN đầu vào | Entry mà ứng dụng muốn truy cập | RDN có thể chứa PII hoặc định danh nội bộ |
| Attribute values | Giá trị đọc/ghi | Có thể là email, số điện thoại, group membership, trạng thái tài khoản |

RFC 4511 cho phép server trả diagnosticMessage dạng văn bản, nhưng nội dung này không được chuẩn hóa để client dựa vào xử lý. RFC cũng lưu ý server có thể thay result code để tránh tiết lộ thông tin; matchedDN và diagnosticMessage có thể tiết lộ sự tồn tại hoặc vắng mặt của dữ liệu bị bảo vệ. Vì vậy, không dùng message của server làm API contract và không mặc định message đó an toàn để log.

### 1.1. Ví dụ log nguy hiểm

~~~text
ERROR LDAP search failed:
  dn=uid=nguyen.van.lan,ou=Finance,dc=corp,dc=example
  filter=(&(objectClass=inetOrgPerson)(mail=lan.nguyen@example.org))
  matchedDN=ou=Finance,dc=corp,dc=example
  diagnosticMessage=No such user lan.nguyen@example.org
  exception=javax.naming.NameNotFoundException: ...
~~~

Một dòng log như vậy có thể làm lộ tên và email nhân viên, cấu trúc tổ chức/naming context, quy tắc truy vấn và thông tin về việc một account có tồn tại hay không. Nếu log được gửi sang SIEM, APM, cloud logging hoặc nhà cung cấp bên ngoài, phạm vi người có thể đọc dữ liệu còn rộng hơn.

### 1.2. Ví dụ log hữu ích nhưng đã giảm dữ liệu

~~~text
event=ldap.operation.failed
operation=SEARCH
errorCategory=ENTRY_NOT_RESOLVED
springException=org.springframework.ldap.NameNotFoundException
directory=employee-directory
baseAlias=people
queryId=person-by-email
targetRef=dn-hmac-v3:K4x2Q1p8dA
resultCode=32
durationMs=41
attempt=1
correlationId=01J...
~~~

Log này vẫn giúp điều tra operation, query, directory, base alias, exception class, result code, thời gian và request liên quan. Không cần lưu raw email, raw DN hay message của server để có được các thông tin đó.

## 2. Phân loại dữ liệu trước khi ghi log

Một chính sách thực tế nên chia dữ liệu thành ba nhóm:

| Nhóm | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Cho phép ghi** | Event name cố định, operation enum, duration, attempt, result code, exception class | Ghi theo allowlist |
| **Cần biến đổi** | DN, user identifier, tenant, request ID do client gửi, referral host | Alias, HMAC, pseudonymization hoặc validation |
| **Không ghi** | Password, userPassword, Bind credentials, access token, private key, raw attribute values nhạy cảm | Loại bỏ hoàn toàn |

Không coi mọi DN là dữ liệu vô hại chỉ vì DN là định danh kỹ thuật. Ví dụ:

~~~text
cn=Nguyen Van Lan,ou=Finance,dc=corp,dc=example
uid=lan.nguyen,ou=people,dc=corp,dc=example
mail=lan.nguyen@example.org,ou=users,dc=corp,dc=example
~~~

RDN có thể chứa tên thật, login name, email hoặc mã nhân viên. Các OU cũng có thể tiết lộ bộ phận, chi nhánh hoặc tenant. Hãy coi raw DN là dữ liệu nhạy cảm theo chính sách của tổ chức.

### 2.1. Những trường không đưa vào log thông thường

- Password người dùng và service account.
- Giá trị userPassword, kể cả dạng hash.
- SASL credentials, bearer token và client secret.
- Private key, keystore password và key material.
- Raw Bind request hoặc environment chứa SECURITY_CREDENTIALS.
- Toàn bộ attribute values chưa được đánh giá.
- Raw filter có giá trị do người dùng nhập.
- Raw DN hoặc matchedDN.
- diagnosticMessage chưa được lọc.
- Referral URI chưa được xác minh.

Không ghi password ngay cả khi nó đã được che trong một formatter khác. Redaction ở cuối pipeline không thay thế việc ngăn secret xuất hiện tại nguồn.

### 2.2. Attribute name và attribute value là hai loại dữ liệu khác nhau

Có thể cần ghi tên operation hoặc danh sách attribute mà code dự định đọc:

~~~text
requestedAttributes=[uid, cn, mail]
~~~

Nhưng không ghi giá trị:

~~~text
uid=lan.nguyen
cn=Nguyen Van Lan
mail=lan.nguyen@example.org
~~~

Ngay cả tên attribute cũng nên được lấy từ allowlist trong code. Không đưa tên attribute tùy ý từ request vào log, vì nó có thể trở thành log injection hoặc tiết lộ schema nội bộ.

## 3. Spring LDAP exception hierarchy

Spring LDAP chuyển nhiều lỗi JNDI thành các exception runtime thuộc package org.springframework.ldap. Lớp cơ sở org.springframework.ldap.NamingException kế thừa NestedRuntimeException; nhiều lớp con phản chiếu exception JNDI tương ứng.

Một số loại thường gặp:

| Spring LDAP exception | Nhóm lỗi có thể biểu thị | Điều cần lưu ý |
| --- | --- | --- |
| AuthenticationException | Bind bị từ chối | Không ghi DN/password; không tự khẳng định chỉ sai password |
| CommunicationException | Kết nối/network/provider | Cause có thể chứa TLS/socket details |
| ServiceUnavailableException | Directory service không khả dụng | Có thể transient, nhưng phải xét operation/deadline |
| NameNotFoundException | Không resolve được tên/base/entry | Server có thể thay code để tránh disclosure |
| NameAlreadyBoundException | DN đã tồn tại | Có thể là conflict hoặc kết quả Add trước đó không rõ |
| NoPermissionException | Quyền không đủ | Không log entry/attribute bị từ chối |
| SchemaViolationException | Operation vi phạm schema | Không ghi raw attribute values |
| InvalidSearchFilterException | Filter không hợp lệ | Không ghi filter nguyên văn |
| TimeLimitExceededException | Search vượt time limit | Ghi thời gian, query ID và limit |
| SizeLimitExceededException | Search vượt size limit | Không coi partial result là đầy đủ |
| PartialResultException | Chỉ nhận được một phần kết quả | Có thể liên quan referral/topology |
| ReferralException | Server yêu cầu chuyển hướng | Referral URI có thể tiết lộ topology |
| UncategorizedLdapException | Không map được sang loại cụ thể | Giữ category UNKNOWN và điều tra theo cause class |

Danh sách exception và quan hệ kế thừa phụ thuộc phiên bản Spring LDAP. Dùng API/Javadoc của đúng dependency đang chạy. Không phân loại bằng cách tìm chuỗi như "invalid credentials" trong getMessage().

### 3.1. Không ghi toàn bộ exception object theo thói quen

Đoạn code này có thể ghi message, cause và stack trace nguyên bản:

~~~java
try {
    ldapTemplate.search(query, mapper);
} catch (org.springframework.ldap.NamingException ex) {
    log.error("LDAP operation failed", ex);
    throw ex;
}
~~~

SLF4J sẽ nhận Throwable và backend thường in stack trace cùng message/cause. Message đó có thể chứa dữ liệu nhạy cảm từ provider hoặc directory server.

Trong log ứng dụng thông thường, hãy trích xuất các trường đã được cho phép:

~~~java
catch (org.springframework.ldap.NamingException ex) {
    log.error(
        "event=ldap.operation.failed operation={} category={} exceptionClass={} causeClass={} correlationId={}",
        "SEARCH",
        classify(ex),
        ex.getClass().getName(),
        safeRootCauseClass(ex),
        correlationId
    );
    throw ex;
}
~~~

Ví dụ này không truyền ex làm đối số cuối của logger. Nếu cần stack trace để debug, hãy gửi stack frame đã được kiểm soát tới kênh chẩn đoán có quyền truy cập hạn chế; không bật raw exception logging đại trà.

### 3.2. Những accessor có thể chứa dữ liệu nhạy cảm

org.springframework.ldap.NamingException cung cấp các accessor tiện ích như:

- getExplanation()
- getRemainingName()
- getResolvedName()
- getResolvedObj()
- getCause()

Các giá trị này hữu ích khi điều tra trong debugger, nhưng có thể mang theo tên chưa resolve, tên đã resolve, object hoặc nội dung từ exception JNDI gốc. Không tự động serialize chúng vào JSON log hoặc API response.

getMessage(), getLocalizedMessage(), toString() và printStackTrace() cũng không phải API đã được làm sạch. Không dùng chúng làm trường detail trong response công khai.

## 4. LDAP result code không phải toàn bộ nguyên nhân

RFC 4511 định nghĩa LDAPResult với resultCode, matchedDN, diagnosticMessage và referral tùy chọn. Một số mã thường gặp:

| Code | Tên | Hướng phân loại ban đầu |
| ---: | --- | --- |
| 3 | timeLimitExceeded | Search timeout/limit |
| 4 | sizeLimitExceeded | Kết quả vượt giới hạn |
| 8 | strongerAuthRequired | Cần cơ chế/mức xác thực mạnh hơn |
| 10 | referral | Cần xử lý referral |
| 11 | adminLimitExceeded | Giới hạn quản trị |
| 13 | confidentialityRequired | Cần bảo vệ confidentiality |
| 32 | noSuchObject | Không resolve được object/base |
| 34 | invalidDNSyntax | DN không hợp lệ |
| 48 | inappropriateAuthentication | Cơ chế xác thực không phù hợp |
| 49 | invalidCredentials | Bind credentials bị từ chối |
| 50 | insufficientAccessRights | Không đủ quyền |
| 51 | busy | Server đang bận |
| 52 | unavailable | Server không khả dụng |
| 53 | unwillingToPerform | Server từ chối thực hiện |
| 64 | namingViolation | Vi phạm naming rule |
| 65 | objectClassViolation | Vi phạm objectClass/schema |
| 66 | notAllowedOnNonLeaf | Operation không được phép trên entry còn children |
| 68 | entryAlreadyExists | Entry đã tồn tại |
| 80 | other | Lỗi khác |

### 4.1. Server có thể thay result code

Không suy ra chắc chắn một nguyên nhân nghiệp vụ chỉ từ code:

- Server có thể trả noSuchObject thay cho insufficientAccessRights để tránh tiết lộ entry tồn tại.
- Server có thể trả invalidCredentials trong một tình huống mà thông tin quyền không nên bị tiết lộ.
- Các server khác nhau có thể cung cấp diagnostic text khác nhau cho cùng code.
- Extension/vendor có thể định nghĩa result code bổ sung.

Vì vậy, code là một tín hiệu chẩn đoán, không phải bằng chứng duy nhất về sự tồn tại của user hoặc cấu hình ACL.

### 4.2. Không parse result code từ message text nếu có thể tránh

Tránh:

~~~java
String message = ex.getMessage();
if (message != null && message.contains("error code 49")) {
    // Giả định sai password.
}
~~~

Message text không có định dạng ổn định giữa provider, server, locale và version. Nếu ứng dụng cần result code có cấu trúc, lấy nó từ API/control/provider cụ thể đã được xác minh. Nếu abstraction hiện tại không cung cấp code, ghi resultCode=UNKNOWN cùng exception class/cause class; không đoán từ chuỗi message.

## 5. Thiết kế một diagnostic event an toàn

Thay vì log object LDAP hoặc request đầy đủ, hãy định nghĩa một event có schema cố định.

| Field | Ví dụ | Quy tắc |
| --- | --- | --- |
| event | ldap.operation.failed | Hằng số do ứng dụng định nghĩa |
| operation | SEARCH, BIND, MODIFY | Enum allowlist |
| errorCategory | TRANSPORT, AUTH_REJECTED, SCHEMA | Enum allowlist |
| exceptionClass | org.springframework.ldap.CommunicationException | Tên class, không phải message |
| causeClass | javax.net.ssl.SSLHandshakeException | Tên class gốc đã kiểm soát |
| resultCode | 52 hoặc UNKNOWN | Chỉ ghi khi lấy có cấu trúc |
| directoryAlias | employee-directory | Alias cấu hình, không phải URL tùy ý |
| baseAlias | people | Alias allowlist thay cho base DN |
| queryId | person-by-uid | ID truy vấn cố định |
| targetRef | dn-hmac-v3:K4x2Q1p8dA | HMAC pseudonym, không phải DN |
| durationMs | 41 | Số không âm |
| attempt | 1 | Số nguyên |
| correlationId | UUID hoặc trace ID đã kiểm tra | Không chứa PII |
| outcome | FAILED | Enum |

Một JSON event minh họa:

~~~json
{
  "event": "ldap.operation.failed",
  "operation": "SEARCH",
  "errorCategory": "TRANSPORT",
  "exceptionClass": "org.springframework.ldap.CommunicationException",
  "causeClass": "javax.net.ssl.SSLHandshakeException",
  "resultCode": "UNKNOWN",
  "directoryAlias": "employee-directory",
  "baseAlias": "people",
  "queryId": "person-by-uid",
  "targetRef": "dn-hmac-v3:K4x2Q1p8dA",
  "durationMs": 41,
  "attempt": 1,
  "correlationId": "8f0a4d2c-...",
  "outcome": "FAILED"
}
~~~

Không thêm dn, filter, attributes, diagnosticMessage, referral, password hoặc exceptionMessage vào event này.

### 5.1. Alias thay cho endpoint và base DN

Thay vì:

~~~text
url=ldaps://ldap-prod-03.internal.example:636
base=ou=employees,dc=corp,dc=example
~~~

hãy ghi:

~~~text
directoryAlias=employee-directory
baseAlias=people
~~~

Alias được cấu hình trong ứng dụng, không lấy từ request. Người vận hành có thể tra alias trong hệ thống cấu hình có quyền truy cập phù hợp.

### 5.2. Query ID thay cho raw filter

Không ghi:

~~~text
filter=(&(objectClass=inetOrgPerson)(uid=lan.nguyen))
~~~

Ghi:

~~~text
queryId=person-by-uid
filterTemplateVersion=2
scope=SUBTREE
countLimit=2
timeLimitMs=2000
~~~

Query ID giúp tìm code path và cấu hình truy vấn. Filter template version giúp xác định phiên bản mà không lưu assertion values.

## 6. Che DN nhưng vẫn tương quan được bằng HMAC

Một cách hữu ích để theo dõi nhiều lỗi liên quan đến cùng một entry là tạo pseudonymous reference từ DN bằng HMAC. HMAC dùng secret key mà chỉ service logging adapter hoặc KMS được phép sử dụng. Cùng một DN và cùng key version sẽ tạo cùng reference, nhưng người đọc log không thể đảo ngược reference thành DN nếu không có key.

### 6.1. Ví dụ HMAC-SHA-256

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class DirectoryReferenceFactory {
    private final SecretKey hmacKey;
    private final String keyVersion;

    public DirectoryReferenceFactory(
            SecretKey hmacKey,
            String keyVersion) {
        this.hmacKey = hmacKey;
        this.keyVersion = keyVersion;
    }

    public String referenceForDn(String dn)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(hmacKey);
        byte[] digest = mac.doFinal(
            dn.getBytes(StandardCharsets.UTF_8)
        );
        byte[] shortDigest = Arrays.copyOf(digest, 12);
        String token = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(shortDigest);

        return "dn-hmac-" + keyVersion + ":" + token;
    }
}
~~~

Ví dụ này chỉ trả reference, không trả DN. Secret key phải được cấp từ secret manager/KMS; không hardcode key, không dùng chung key với mục đích ký token hoặc mã hóa dữ liệu khác.

### 6.2. HMAC là pseudonymization, không phải xóa dữ liệu

HMAC reference vẫn cho phép liên kết các event về cùng một subject. Vì vậy:

- Hạn chế ai được đọc log.
- Đặt retention phù hợp.
- Quản lý key version và rotation.
- Không cung cấp endpoint công khai cho phép thử DN tùy ý rồi nhận HMAC.
- Không dùng HMAC reference làm authorization identity.
- Không coi reference là dữ liệu ẩn danh tuyệt đối.

Nếu không cần tương quan entry qua nhiều event, tốt nhất không ghi bất kỳ reference nào.

### 6.3. Không dùng hash thường cho DN

Không nên dùng Integer.toHexString(dn.hashCode()) hoặc SHA-256 không có secret key. DN thường có entropy thấp và có thể đoán được từ danh sách username/OU. Attacker có thể thử từ điển rồi so sánh hash. HMAC làm cho việc kiểm tra từ điển cần có secret key.

### 6.4. Canonicalization phải được định nghĩa rõ

Hai chuỗi DN có thể biểu diễn cùng tên nhưng khác cách escape/case/format. Nếu HMAC trực tiếp chuỗi đầu vào, chúng có thể cho reference khác nhau. Nếu cần tương quan qua nhiều cách biểu diễn:

- Parse bằng LdapName/Rdn theo quy tắc DN.
- Xác định canonical form phù hợp với naming policy.
- Không lowercase raw DN string theo cách thủ công.
- Không tự decode/re-encode RDN nếu chưa hiểu escaping và matching rules.
- Test DN có comma, plus, backslash, leading/trailing spaces và escaped characters.

Nếu chưa có canonicalization đã được kiểm chứng, hãy coi reference là ổn định cho đúng chuỗi DN đã serialize, không khẳng định hai chuỗi khác nhau sẽ có cùng token.

## 7. Phân loại exception mà không đọc message

Một classifier chỉ nên dùng type information và metadata đã được xác minh. Ví dụ:

~~~java
import org.springframework.ldap.AuthenticationException;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.InvalidSearchFilterException;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.SchemaViolationException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.SizeLimitExceededException;
import org.springframework.ldap.TimeLimitExceededException;
import org.springframework.ldap.PartialResultException;

public final class LdapErrorClassifier {
    public String classify(Throwable error) {
        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (current instanceof AuthenticationException) {
                return "AUTH_REJECTED";
            }
            if (current instanceof NoPermissionException) {
                return "ACCESS_DENIED";
            }
            if (current instanceof NameAlreadyBoundException) {
                return "ENTRY_CONFLICT";
            }
            if (current instanceof NameNotFoundException) {
                return "ENTRY_NOT_RESOLVED";
            }
            if (current instanceof InvalidSearchFilterException) {
                return "INVALID_FILTER";
            }
            if (current instanceof SchemaViolationException) {
                return "SCHEMA_VIOLATION";
            }
            if (current instanceof TimeLimitExceededException) {
                return "TIME_LIMIT";
            }
            if (current instanceof SizeLimitExceededException
                    || current instanceof PartialResultException) {
                return "PARTIAL_OR_LIMITED_RESULT";
            }
            if (current instanceof ServiceUnavailableException) {
                return "SERVICE_UNAVAILABLE";
            }
            if (current instanceof CommunicationException) {
                return "COMMUNICATION";
            }
        }
        return "UNKNOWN";
    }
}
~~~

Đây là classifier khởi đầu; hãy điều chỉnh imports và các subclass theo phiên bản Spring LDAP thực tế. Trong production nên giới hạn độ sâu cause chain hoặc dùng tập hợp identity để tránh vòng lặp do exception tự tạo. Nếu cause là SSLHandshakeException, classifier có thể bổ sung category TLS bằng cách kiểm tra class type của cause, không cần log message.

### 7.1. Thứ tự kiểm tra subclass

Một số exception có thể kế thừa từ loại tổng quát hơn. Hãy kiểm tra loại cụ thể trước loại cha, ví dụ ServiceUnavailableException trước CommunicationException, để không mất category chi tiết.

### 7.2. UNKNOWN là kết quả hợp lệ

Không ép mọi exception vào một category gần giống nhất. Khi không đủ thông tin:

~~~text
errorCategory=UNKNOWN
exceptionClass=org.springframework.ldap.UncategorizedLdapException
causeClass=javax.naming.NamingException
~~~

Giữ UNKNOWN giúp tránh đưa ra kết luận sai và cho phép bổ sung classifier sau khi điều tra.

## 8. Chính sách log theo operation và mức độ

Không phải mọi lỗi LDAP đều cần ERROR hoặc stack trace.

| Tình huống | Mức log gợi ý | Ghi chú |
| --- | --- | --- |
| Search không tìm thấy trong use case bình thường | DEBUG hoặc metric | Không ghi raw identifier; không nhất thiết là sự cố |
| User Bind bị từ chối | INFO/security metric theo policy | Chống account enumeration và log flood |
| Service Bind thất bại | ERROR/alert | Có thể ảnh hưởng toàn bộ ứng dụng |
| TLS certificate/hostname failure | ERROR/alert | Không fallback plaintext |
| LDAP unavailable/communication failure | ERROR hoặc WARN theo circuit state | Ghi duration, retry và dependency alias |
| Invalid filter/schema violation | ERROR cho bug hoặc dữ liệu sai | Thường không retry |
| Access denied ngoài dự kiến | WARN/ERROR và security event | Không ghi target DN/attribute |
| Pool exhausted | WARN/ERROR và metric | Theo dõi active/idle/waiters |
| Duplicate DN khi Add | WARN hoặc business conflict | Có thể là idempotent replay hoặc dữ liệu trùng |
| Compensation failure | ERROR/alert mức cao | Cần reconciliation |

Mức log cần phản ánh tác động và hành động cần thiết, không chỉ loại exception. Một lỗi đăng nhập sai lặp lại có thể là security signal nhưng không nên tạo một stack trace dài cho mỗi lần thử.

### 8.1. Rate limit và chống log flooding

Attacker có thể tạo nhiều Bind failure hoặc Search lỗi để làm đầy log. Nên:

- Giới hạn tần suất event lặp theo category/directory.
- Dùng counter/metric cho số lượng lớn, log mẫu cho một phần event.
- Giữ alert cho ngưỡng bất thường.
- Không bỏ hoàn toàn các event bảo mật quan trọng.
- Tránh dùng username/DN làm metric label có cardinality cao.

## 9. Tạo correlation ID và bảo vệ MDC

Correlation ID giúp ghép log của controller, service, LDAP adapter và downstream component. Nó không cần chứa username hoặc DN.

### 9.1. Không tin mù quáng header do client gửi

Nếu nhận X-Correlation-ID từ request:

- Kiểm tra chiều dài tối đa.
- Chỉ chấp nhận tập ký tự allowlist.
- Loại CR, LF, tab và control characters.
- Nếu không hợp lệ hoặc thiếu, tạo UUID mới.
- Không dùng header này làm danh tính người dùng hoặc authorization input.

Ví dụ validator:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIds {
    private static final Pattern SAFE =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

    public static String resolve(String supplied) {
        if (supplied != null && SAFE.matcher(supplied).matches()) {
            return supplied;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

### 9.2. MDC phải được dọn trong finally

~~~java
import org.slf4j.MDC;
import java.util.concurrent.Callable;

public <T> T withCorrelationId(
        String correlationId,
        Callable<T> action) throws Exception {
    MDC.put("correlationId", correlationId);
    try {
        return action.call();
    } finally {
        MDC.remove("correlationId");
    }
}
~~~

Thread pool tái sử dụng thread. Nếu không xóa MDC trong finally, request tiếp theo có thể nhận nhầm correlation ID của request trước. Với async execution, truyền trace context theo cơ chế instrumentation của framework thay vì giả định MDC tự động lan truyền qua mọi executor.

### 9.3. Correlation ID không thay thế trace ID

Distributed tracing có thể cung cấp trace/span IDs. Dùng trace ID để nối các span giữa service nếu hệ thống đã có tracing. Correlation ID ứng dụng có thể được giữ như một business/request reference riêng. Cả hai đều không nên chứa email, login name hoặc DN.

## 10. Log structured fields, không nối chuỗi input

Một logger nên nhận các trường đã được kiểm soát:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ldap.NamingException;

public final class SafeLdapFailureLogger {
    private static final Logger log =
        LoggerFactory.getLogger(SafeLdapFailureLogger.class);

    private static String safeRootCauseClass(Throwable error) {
        Throwable current = error;
        for (int depth = 0;
             depth < 8 && current.getCause() != null;
             depth++) {
            current = current.getCause();
        }
        return current.getClass().getName();
    }

    public void failed(
            String operation,
            String errorCategory,
            String directoryAlias,
            String queryId,
            String targetRef,
            long durationMs,
            int attempt,
            String correlationId,
            NamingException exception) {

        log.error(
            "event=ldap.operation.failed operation={} category={} directory={} queryId={} targetRef={} durationMs={} attempt={} correlationId={} exceptionClass={}",
            operation,
            errorCategory,
            directoryAlias,
            queryId,
            targetRef,
            Math.max(0, durationMs),
            Math.max(1, attempt),
            correlationId,
            exception.getClass().getName()
        );
    }
}
~~~

Các tham số operation, directoryAlias, queryId phải đến từ enum/allowlist hoặc configuration đã kiểm soát. targetRef phải được tạo từ HMAC adapter. Không truyền request object, LdapQuery.toString(), DN hoặc filter trực tiếp vào logger.

Nếu logging backend hỗ trợ structured key-value logging, dùng JSON encoder và trường riêng. Đừng tự ghép JSON bằng string concatenation; ký tự quote, backslash hoặc newline có thể phá cấu trúc log.

### 10.1. Chống log injection

Không ghi trực tiếp chuỗi do người dùng kiểm soát. Kẻ tấn công có thể gửi username chứa newline hoặc ký tự điều khiển để tạo dòng log giả:

~~~text
username = "lan
level=INFO event=login.success"
~~~

Ưu tiên không log username. Nếu một identifier cần xuất hiện, validate theo allowlist hoặc dùng HMAC. JSON encoder phải escape control characters đúng chuẩn; không dựa vào replace thủ công ở một vài ký tự.

### 10.2. Không log toàn bộ LdapQuery

Không dùng:

~~~java
log.debug("LDAP query: {}", query);
~~~

Trừ khi đã xác minh toString() chỉ chứa metadata an toàn. Thông thường, tự ghi queryId, baseAlias, scope, countLimit, timeLimit và tên attribute allowlist là đủ.

## 11. Tách log nội bộ khỏi response API

Client không cần biết DN thật hoặc matched DN, tên OU/naming context, LDAP server hostname/port, raw filter, attribute names nội bộ, diagnosticMessage, exception class/cause chain, referral URL hoặc stack trace.

Một response lỗi ổn định:

~~~json
{
  "code": "DIRECTORY_OPERATION_FAILED",
  "message": "Không thể hoàn tất thao tác directory.",
  "correlationId": "8f0a4d2c-..."
}
~~~

Response cho login failure có thể dùng thông báo chung:

~~~json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Không thể đăng nhập bằng thông tin đã cung cấp.",
  "correlationId": "8f0a4d2c-..."
}
~~~

Không phân biệt công khai username không tồn tại, password sai hoặc entry bị ACL che nếu điều đó cho phép enumeration.

### 11.1. Exception handler tập trung

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.ldap.NamingException;
import org.slf4j.MDC;

@RestControllerAdvice
public class DirectoryExceptionHandler {
    @ExceptionHandler(NamingException.class)
    ProblemDetail handleDirectoryFailure(NamingException exception) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.SERVICE_UNAVAILABLE
        );
        problem.setTitle("Directory operation failed");
        problem.setDetail(
            "Không thể hoàn tất thao tác directory. "
                + "Hãy cung cấp correlation ID khi cần hỗ trợ."
        );
        problem.setProperty("code", "DIRECTORY_OPERATION_FAILED");
        problem.setProperty("correlationId", MDC.get("correlationId"));
        return problem;
    }
}
~~~

Đây là ví dụ cho lỗi dependency tổng quát. Không map mọi NamingException thành HTTP 503 nếu ứng dụng có business conflict, invalid request hoặc authentication failure riêng. Hãy phân loại ở service/adapter và trả status phù hợp; điểm chung là không đưa raw exception message vào response.

### 11.2. Không biến lỗi kỹ thuật thành lỗi nghiệp vụ sai

- AuthenticationException trong user login có thể thành response authentication failure chung.
- CommunicationException/ServiceUnavailableException có thể thành dependency unavailable.
- NameAlreadyBoundException khi tạo entry có thể thành conflict sau khi kiểm tra trạng thái.
- SchemaViolationException thường là lỗi dữ liệu/configuration cần điều tra, không phải user không tồn tại.
- TimeLimitExceededException là timeout, không phải empty result.

Response mapping cần giữ đúng ý nghĩa mà client có thể hành động, nhưng không tiết lộ thông tin directory.

## 12. Chẩn đoán referral và matchedDN an toàn

### 12.1. Referral URL

Referral có thể chứa:

~~~text
ldap://ldap-east.internal.example:389/ou=people,dc=corp,dc=example
~~~

Không ghi URL này vào log phổ thông. Nó có thể tiết lộ hostname, port, naming context và topology. Thay bằng:

~~~text
referralState=PRESENT
referralTargetAlias=people-replica-east
~~~

Chỉ tạo alias nếu referral đã được xác minh và map tới endpoint allowlist. Nếu không thể map an toàn, ghi referralState=UNMAPPED và category phù hợp.

### 12.2. matchedDN

matchedDN có thể hữu ích khi một DN không resolve hoàn toàn, nhưng giá trị này có thể tiết lộ entry cha hoặc OU. Dùng HMAC reference nếu cần tương quan; nếu không, chỉ ghi matchedDnPresent=true.

### 12.3. diagnosticMessage

Không dùng diagnosticMessage để xây API response, tạo metric label, quyết định retry bằng cách tìm từ khóa, tạo alert title chứa raw text hoặc ghi log nguyên văn.

Nếu cần vendor-specific diagnostic, viết adapter riêng:

1. Nhận đúng kiểu exception/control từ provider đã xác minh.
2. Trích xuất các field có cấu trúc và được allowlist.
3. Loại DN, attribute values, account names, host nội bộ và control characters.
4. Chuyển phần còn lại thành category/enum đã định nghĩa.
5. Test với các message có PII và chuỗi CR/LF.

Không giả định một regex chung có thể làm sạch mọi diagnostic message của OpenLDAP, Active Directory và các directory server khác.

## 13. Retry, fail-fast và fallback mà không lộ dữ liệu

Chính sách retry phải dựa trên category, loại operation, tính idempotent và deadline. Không retry chỉ vì message chứa chữ temporary.

| Category | Retry tự động? | Hành động |
| --- | --- | --- |
| AUTH_REJECTED | Không | Trả login failure chung; chống thử password liên tục |
| ACCESS_DENIED | Không | Kiểm tra ACL/service identity |
| INVALID_FILTER | Không | Sửa query/code; kiểm tra injection |
| SCHEMA_VIOLATION | Không | Sửa schema hoặc payload |
| ENTRY_NOT_RESOLVED | Thường không | Xác minh base/scope và policy |
| ENTRY_CONFLICT | Không mù quáng | Read-back để xác định Add trước đó đã thành công chưa |
| TIME_LIMIT | Không retry y nguyên vô hạn | Thu hẹp query, paging hoặc tăng limit có kiểm soát |
| PARTIAL_OR_LIMITED_RESULT | Không coi là complete | Xử lý paging/referral/size limit |
| COMMUNICATION | Có thể, nếu operation an toàn | Retry hữu hạn với backoff và jitter |
| SERVICE_UNAVAILABLE | Có thể, nếu operation an toàn | Retry theo deadline/circuit breaker |
| TLS_FAILURE | Không downgrade | Fail-fast và sửa certificate/trust/protocol |
| POOL_EXHAUSTED | Không lặp borrow trong vòng lặp | Backpressure, sizing, kiểm tra context leak |
| UNKNOWN | Mặc định không | Điều tra trước khi cho retry |

### 13.1. Search

Search thường có thể retry khi lỗi transport/service transient:

- Giới hạn số lần thử.
- Dùng exponential backoff có jitter.
- Tôn trọng request deadline.
- Không retry invalidCredentials, ACL, invalid filter hoặc TLS trust failure.
- Ghi attempt và retryReason dạng enum.

Kết quả Search ở lần retry có thể khác lần đầu vì directory tiếp tục thay đổi hoặc replica đồng bộ trễ. LDAP Search không tự cung cấp snapshot transaction cho nhiều lần thử.

### 13.2. Add

Nếu connection mất sau khi gửi Add, không biết chắc server đã tạo entry hay chưa. Trước khi thử lại:

1. Tạo kết nối hợp lệ.
2. Lookup DN dự kiến trong phạm vi được phép.
3. So sánh trạng thái với các field không nhạy cảm theo policy.
4. Nếu entry đã tồn tại và tương ứng operation trước, coi là outcome cần đối soát/idempotent replay.
5. Nếu entry tồn tại nhưng nội dung khác, xử lý conflict.

Không log nội dung entry khi so sánh.

### 13.3. Modify, Delete và Rename

Sau timeout hoặc connection drop, operation có thể đã được server áp dụng. Đọc lại trạng thái trước khi retry:

- Với Replace attribute, kiểm tra giá trị đích theo policy.
- Với Add/Remove attribute value, kiểm tra value đã tồn tại hay đã bị xóa.
- Với Delete, xác minh DN đã vắng mặt trong phạm vi có thể đọc.
- Với Rename, kiểm tra cả DN cũ và DN mới.

Nếu ACL không cho phép read-back, không đoán kết quả. Đánh dấu OUTCOME_UNKNOWN và chuyển reconciliation.

### 13.4. Fallback sang replica

Fallback chỉ nên xảy ra khi endpoint dự phòng được cấu hình allowlist; TLS certificate và hostname được xác minh; credential/ACL áp dụng đúng policy; operation có semantics phù hợp với replica và consistency model; referral/failover không làm lộ credential sang endpoint không tin cậy.

Không fallback từ LDAPS/StartTLS sang plaintext, từ user Bind sang anonymous Bind, hoặc từ service account bị từ chối sang account quyền rộng hơn. Với write, cần hiểu multi-master/replication conflict trước khi tự động chuyển endpoint.

### 13.5. Cache fallback

Cache có thể giúp một số chức năng đọc tiếp tục hoạt động khi LDAP unavailable, nhưng chỉ dùng cho dữ liệu được phép stale; kiểm tra authorization bằng nguồn đáng tin cậy; không dùng cache để xác minh password hoặc trạng thái account hiện tại; gắn rõ dataSource=CACHE và tuổi dữ liệu; không dùng cache fallback cho provisioning/write.

Nếu dữ liệu LDAP quyết định quyền truy cập, fail closed theo policy thay vì dùng một bản cache cũ để cấp quyền.

## 14. Tách diagnostics, audit và metrics

| Loại | Dùng để | Ví dụ |
| --- | --- | --- |
| Diagnostic log | Điều tra lỗi kỹ thuật | Operation, exception class, duration, error category |
| Security/business audit | Truy vết hành động có ý nghĩa | Actor pseudonym, target reference, operation, outcome |
| Metrics | Theo dõi xu hướng và cảnh báo | Số lần Bind failure, timeout, pool exhaustion |

Không dùng log debug làm audit trail. Không dùng metric label chứa DN/email vì cardinality cao và lộ định danh.

### 14.1. Audit event cho thay đổi LDAP

~~~json
{
  "event": "directory.account.membership.changed",
  "actorRef": "principal-hmac-v2:9kF...",
  "targetRef": "dn-hmac-v3:K4x...",
  "operation": "ADD_GROUP_MEMBER",
  "directoryAlias": "employee-directory",
  "outcome": "SUCCESS",
  "correlationId": "8f0a4d2c-..."
}
~~~

Audit có thể cần actor/target reference để đáp ứng điều tra và compliance, nhưng vẫn phải có chính sách retention, access control, key management và căn cứ thu thập phù hợp.

### 14.2. Metric label có cardinality thấp

~~~text
ldap_operations_total{operation="SEARCH", outcome="FAILED"}
ldap_failures_total{category="COMMUNICATION"}
ldap_retry_total{category="SERVICE_UNAVAILABLE"}
ldap_pool_exhausted_total{pool="employee-read"}
ldap_operation_duration_seconds{operation="MODIFY"}
~~~

Không dùng DN, email hoặc username làm metric label. Mỗi định danh mới tạo label mới, làm metric store phình to và làm lộ dữ liệu.

## 15. Quản trị log như một kho dữ liệu nhạy cảm

Redaction đúng ở ứng dụng là bước đầu. Hệ thống log vẫn cần phân quyền theo vai trò và nhu cầu công việc, mã hóa khi truyền và khi lưu, retention/deletion policy, audit truy cập log, giới hạn export/download, tách môi trường production và non-production, kiểm soát dữ liệu gửi tới bên thứ ba và giám sát log pipeline bị ngắt hoặc bị flood.

Không giữ log vô thời hạn chỉ vì có thể cần điều tra sau này. Retention phải phù hợp mục đích, pháp luật và chính sách nội bộ.

### 15.1. Redaction tại nguồn

Ưu tiên loại bỏ dữ liệu ngay tại logger/adapter. Pipeline phía sau chỉ nên là lớp bảo vệ bổ sung:

~~~text
LDAP exception
    -> classify by exception type
    -> extract allowlisted metadata
    -> HMAC or alias identifiers when needed
    -> structured event
    -> access-controlled log backend
~~~

Nếu raw DN đã được ghi vào file trước khi pipeline mask, bản sao file, buffer, crash dump hoặc backup vẫn có thể giữ dữ liệu đó.

### 15.2. Kiểm tra logger framework khi bật DEBUG/TRACE

Khi bật log level chi tiết cho Spring LDAP, JNDI provider hoặc TLS stack:

- Xem trước output trong môi trường test với dữ liệu giả.
- Kiểm tra filter, DN, attribute values, endpoint và exception messages.
- Bật logger theo package và thời gian có giới hạn.
- Không bật TRACE rộng trên production như biện pháp mặc định.
- Có quy trình tắt log level sau điều tra.

Không giả định framework logger đã tự redaction dữ liệu của ứng dụng.

## 16. Ví dụ adapter ghi log hoàn chỉnh

Một adapter có thể kết hợp classifier, HMAC reference và allowlisted fields:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ldap.NamingException;

public final class DirectoryDiagnostics {
    private static final Logger log =
        LoggerFactory.getLogger(DirectoryDiagnostics.class);

    private final LdapErrorClassifier classifier;
    private final DirectoryReferenceFactory references;

    public DirectoryDiagnostics(
            LdapErrorClassifier classifier,
            DirectoryReferenceFactory references) {
        this.classifier = classifier;
        this.references = references;
    }

    public void recordFailure(
            String operation,
            String directoryAlias,
            String baseAlias,
            String queryId,
            String rawDn,
            long durationMs,
            int attempt,
            String correlationId,
            NamingException exception) {

        String category = classifier.classify(exception);
        String targetRef = "UNAVAILABLE";

        try {
            if (rawDn != null && !rawDn.isBlank()) {
                targetRef = references.referenceForDn(rawDn);
            }
        } catch (Exception referenceFailure) {
            // Không log referenceFailure object hoặc message.
            log.warn(
                "event=ldap.dn_reference.failed directory={} queryId={} correlationId={} failureClass={}",
                directoryAlias,
                queryId,
                correlationId,
                referenceFailure.getClass().getName()
            );
        }

        log.error(
            "event=ldap.operation.failed operation={} category={} directory={} baseAlias={} queryId={} targetRef={} durationMs={} attempt={} correlationId={} exceptionClass={}",
            operation,
            category,
            directoryAlias,
            baseAlias,
            queryId,
            targetRef,
            Math.max(0, durationMs),
            Math.max(1, attempt),
            correlationId,
            exception.getClass().getName()
        );
    }
}
~~~

Đây là ví dụ cấu trúc, cần bổ sung validation enum/alias và quản lý key trong ứng dụng thật. Nếu việc tạo HMAC thất bại, adapter vẫn ghi được event với targetRef=UNAVAILABLE; không ghi raw DN để bù cho lỗi HMAC.

### 16.1. Không để adapter nhận raw request tùy ý

Adapter nên nhận operation enum, directoryAlias/baseAlias từ cấu hình, queryId cố định, rawDn chỉ dùng nội bộ để tạo HMAC rồi bỏ, và correlationId đã validate.

Không truyền một Map tùy ý chứa toàn bộ request hoặc Attributes. Điều đó khiến allowlist dễ bị phá vỡ khi code mới thêm field.

## 17. Ma trận kiểm thử redaction và diagnostics

Kiểm thử phải xác minh log **không chứa** dữ liệu nhạy cảm, chứ không chỉ xác minh logger được gọi.

| ID | Đầu vào/kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| LOG01 | CommunicationException | Log có category và exception class |
| LOG02 | AuthenticationException | Không có password hoặc raw DN |
| LOG03 | Exception message chứa email | Email không xuất hiện trong log |
| LOG04 | Cause chứa SSLHandshakeException | Cause class được phân loại, message không bị ghi |
| LOG05 | matchedDN có tên thật | Chỉ có target reference hoặc presence flag |
| LOG06 | diagnosticMessage chứa UID | Không xuất hiện trong log/API |
| LOG07 | Referral URL chứa hostname nội bộ | Chỉ ghi alias hoặc UNMAPPED |
| LOG08 | Filter có email | Log chỉ có query ID/template version |
| LOG09 | Attribute userPassword | Giá trị không xuất hiện ở bất kỳ log level nào |
| LOG10 | Attributes có mail/telephone | Không ghi raw values |
| LOG11 | DN có comma/plus/backslash | HMAC không làm lộ DN và xử lý ổn định theo policy |
| LOG12 | Hai event cùng DN và cùng key version | Tạo cùng HMAC reference |
| LOG13 | HMAC key version thay đổi | Reference có key version mới; rotation được quản lý |
| LOG14 | HMAC key không khả dụng | Ghi targetRef=UNAVAILABLE, không fallback raw DN |
| LOG15 | Username có CR/LF | Correlation/identifier bị reject hoặc thay bằng ID mới |
| LOG16 | Correlation ID quá dài | Sinh ID mới |
| LOG17 | Correlation ID có control characters | Không xuất hiện dòng log giả |
| LOG18 | Exception được log ở ERROR | Logger không nhận Throwable raw |
| LOG19 | DEBUG/TRACE bật trong test | Kiểm tra framework/provider không phát raw secrets |
| LOG20 | API nhận NamingException | Response không có message, DN hoặc stack trace |
| LOG21 | LDAP code 49 | Không khẳng định công khai username/password cụ thể |
| LOG22 | LDAP code 32 | Không khẳng định entry chắc chắn không tồn tại toàn directory |
| LOG23 | Unknown result code | Ghi UNKNOWN, không crash hoặc parse message |
| LOG24 | Invalid filter | Fail-fast, không retry |
| LOG25 | Schema violation | Không retry tự động |
| LOG26 | Communication failure khi Search | Retry hữu hạn nếu deadline còn và policy cho phép |
| LOG27 | Communication failure sau Add | Read-back/reconcile trước khi retry |
| LOG28 | Timeout sau Modify | Outcome unknown nếu chưa xác minh state |
| LOG29 | Pool exhausted | Không phân loại thành authentication failure |
| LOG30 | Referral không allowlist | Không follow và không chuyển credential |
| LOG31 | Cache fallback | Chỉ dùng cho use case được phép stale, có source/age marker |
| LOG32 | Log flood từ Bind failure | Rate limit/metrics vẫn giữ được tín hiệu |
| LOG33 | MDC với thread pool | Correlation ID được xóa sau request |
| LOG34 | Concurrent requests | Không lẫn correlation ID giữa thread |
| LOG35 | Log backend unavailable | Ứng dụng có policy fail-open/fail-closed rõ ràng, không làm lộ dữ liệu |

### 17.1. Test bằng captured log output

~~~java
@Test
void doesNotLogSensitiveDirectoryDetails() {
    String rawDn =
        "uid=lan.nguyen,ou=Finance,dc=corp,dc=example";
    String rawEmail = "lan.nguyen@example.org";
    String rawPassword = "test-only-secret";

    // Gọi service với LDAP test double ném exception có message giả
    // chứa DN, email và password test.
    invokeFailingDirectoryOperation(rawDn, rawEmail, rawPassword);

    String captured = testLogAppender.contents();

    assertFalse(captured.contains(rawDn));
    assertFalse(captured.contains(rawEmail));
    assertFalse(captured.contains(rawPassword));
    assertTrue(captured.contains("ldap.operation.failed"));
    assertTrue(captured.contains("correlationId"));
}
~~~

testLogAppender và invokeFailingDirectoryOperation là helper do test project cung cấp. Dùng secret giả riêng cho test; không đưa production secret vào fixture.

### 17.2. Test kiểm tra cả backend và sink phụ

Ngoài appender chính, hãy kiểm tra console output, file appender, async logging queue, error reporting/exception tracker, APM span attributes, audit stream và crash/diagnostic dump nếu có. Redaction ở một logger không bảo đảm dữ liệu không xuất hiện ở một sink khác.

## 18. Quy trình điều tra sự cố với log đã che

Khi nhận một correlationId, người vận hành có thể:

1. Tìm toàn bộ event theo correlation/trace ID.
2. Xem directoryAlias, baseAlias, queryId và operation.
3. Xem error category, exception class, cause class và result code nếu có.
4. So sánh duration, attempt và pool metrics.
5. Kiểm tra deployment/configuration version tại thời điểm xảy ra lỗi.
6. Nếu cần tìm entry cụ thể, dùng targetRef qua quy trình tra cứu được phân quyền, có audit và không cung cấp HMAC oracle công khai.
7. Nếu vẫn chưa đủ, bật diagnostic có kiểm soát trong môi trường phù hợp, với dữ liệu giả hoặc quyền truy cập hạn chế.

Không yêu cầu người vận hành copy DN/email/password vào ticket công khai để điều tra. Có thể dùng correlation ID, query ID và directory alias để bắt đầu.

### 18.1. Quy trình elevated diagnostics

Trong một số sự cố, cần thêm thông tin sâu hơn. Quy trình nên có người phê duyệt hoặc incident role phù hợp; chỉ bật cho directory alias/query cụ thể; có thời hạn tự tắt; dùng test account hoặc dữ liệu đã giả danh nếu có thể; không log password, private key hoặc Bind credentials trong mọi trường hợp; lưu output ở sink có quyền truy cập hạn chế và retention ngắn; rà soát/xóa artifact sau incident theo policy.

Elevated diagnostics không phải lý do để bật raw LDAP protocol tracing vô thời hạn trên production.

## 19. Các lỗi thiết kế thường gặp

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| log.error("LDAP failed", ex) cho mọi lỗi | Cause/message có thể chứa DN/diagnostic | Ghi exception class và field allowlist |
| Log getMessage() | Nội dung không ổn định, có thể chứa PII | Dùng error category |
| Log getResolvedName()/getRemainingName() | Lộ DN | Dùng HMAC reference hoặc bỏ |
| Log matchedDN | Lộ entry cha/OU | Ghi presence flag hoặc HMAC |
| Log diagnosticMessage | Server text không chuẩn hóa và có thể nhạy cảm | Không ghi raw text |
| Log raw Search filter | Lộ username/email và query values | Ghi query ID/template version |
| Log toàn bộ Attributes | Lộ PII, group membership, password hash | Chỉ ghi metadata allowlist |
| Dùng SHA-256 không key cho DN | Có thể dò từ điển | HMAC với secret key |
| HMAC key hardcode | Mất khả năng bảo vệ reference | Secret manager/KMS và rotation |
| Ghi correlation ID không validate | Log injection hoặc log giả | Allowlist, length limit, generate mới |
| Trả LDAP exception message qua API | Enumeration và disclosure topology | Response code/message chuẩn hóa |
| Parse result code từ message | Phụ thuộc provider/locale | Dùng structured result hoặc UNKNOWN |
| Retry mọi exception | Lockout, load amplification, duplicate writes | Policy theo category/operation |
| Retry Add/Modify sau timeout ngay | Operation có thể đã được áp dụng | Read-back/reconciliation |
| Fallback plaintext/anonymous | Lộ credential hoặc vượt ACL | Fail closed |
| Cache fallback để xác minh quyền | Dữ liệu stale cấp quyền sai | Fail closed theo authorization policy |
| Log DN/email làm metric label | Cardinality cao và lộ dữ liệu | Enum/category/alias |
| Chỉ mask ở log backend | Raw data đã xuất hiện tại source/sink khác | Redact trước khi ghi |

## 20. Checklist triển khai

1. **Lập data inventory:** xác định DN, filter, attributes, diagnostic, referral và cause có thể chứa gì.
2. **Chọn allowlist:** operation, error category, exception class, result code, duration, attempt, alias và correlation ID.
3. **Không ghi secrets:** password, userPassword, token, private key và Bind credentials.
4. **Che DN:** bỏ raw DN hoặc tạo HMAC reference bằng key quản lý an toàn.
5. **Không ghi raw filter:** dùng query ID/template version và scope/limit đã kiểm soát.
6. **Không ghi attribute values:** chỉ ghi attribute names đã allowlist nếu thực sự cần.
7. **Không ghi diagnostic raw:** bỏ diagnosticMessage, matchedDN và referral URI.
8. **Phân loại bằng type:** dùng Spring LDAP exception classes và cause class, không parse message.
9. **Cho phép UNKNOWN:** không đoán result code hoặc nguyên nhân.
10. **Tách response:** API không trả exception message, DN, referral hoặc stack trace.
11. **Correlation an toàn:** validate header, giới hạn độ dài và dọn MDC trong finally.
12. **Chống log injection:** JSON encoder và allowlist cho mọi giá trị có nguồn từ request.
13. **Retry có policy:** chỉ retry transient operation an toàn, có backoff/jitter/deadline.
14. **Read-back khi outcome chưa rõ:** không retry write mù.
15. **Fallback có điều kiện:** endpoint allowlist, TLS và consistency phù hợp; không downgrade.
16. **Metrics cardinality thấp:** không dùng DN, email hoặc username làm label.
17. **Bảo vệ log store:** access control, encryption, audit và retention.
18. **Kiểm tra mọi sink:** console, file, APM, error tracker, audit và async queue.
19. **Test redaction:** đưa DN/email/password giả vào exception message rồi xác minh không xuất hiện.
20. **Elevated diagnostics có thời hạn:** có quyền, audit và tự tắt.

## 21. Câu hỏi tự kiểm tra

1. **Vì sao DN có thể là dữ liệu nhạy cảm?** RDN có thể chứa tên, UID, email hoặc mã nhân viên; OU tiết lộ cấu trúc tổ chức.
2. **Có nên log toàn bộ NamingException bằng Throwable trong production không?** Không mặc định; message/cause có thể chứa DN hoặc diagnostic nhạy cảm.
3. **diagnosticMessage có phải API ổn định để parse không?** Không; RFC 4511 không chuẩn hóa nội dung này.
4. **matchedDN có thể tiết lộ gì?** Entry cha, OU hoặc sự tồn tại/vắng mặt của dữ liệu.
5. **Vì sao result code không phải bằng chứng đầy đủ?** Server có thể thay code để tránh disclosure và extension có thể thêm code mới.
6. **Spring LDAP NamingException kế thừa lớp nào?** org.springframework.core.NestedRuntimeException.
7. **getResolvedName() có an toàn để log không?** Không mặc định; nó có thể chứa DN đã resolve.
8. **Tại sao không parse code 49 từ exception message?** Message phụ thuộc provider/server/locale và không có contract ổn định.
9. **HMAC DN dùng để làm gì?** Tạo pseudonymous reference ổn định theo key version để tương quan event mà không ghi DN.
10. **HMAC có làm dữ liệu hoàn toàn anonymous không?** Không; nó vẫn liên kết các event và cần access/retention controls.
11. **Vì sao hash thường yếu hơn HMAC?** DN có thể đoán được; hash không key dễ bị dò từ điển.
12. **Nên ghi raw Search filter không?** Không; ghi query ID, scope và giới hạn.
13. **Attribute name có giống attribute value về rủi ro không?** Không; value thường nhạy cảm hơn, nhưng tên attribute cũng nên allowlist.
14. **Correlation ID do client gửi có cần validate không?** Có; giới hạn độ dài/ký tự và loại control characters để tránh log injection.
15. **Vì sao phải xóa MDC trong finally?** Thread pool tái sử dụng thread và có thể làm lẫn correlation giữa request.
16. **Có retry AuthenticationException không?** Không tự động; có thể làm tăng lockout counter.
17. **Nếu Add timeout sau khi gửi request thì làm gì?** Read-back để xác định entry đã được tạo chưa trước khi retry.
18. **Pool exhaustion có phải sai password không?** Không; đó là lỗi tài nguyên/borrow, cần phân loại riêng.
19. **Có fallback từ LDAPS sang plaintext khi TLS lỗi không?** Không; phải fail closed.
20. **Có thể dùng cache cũ để xác minh quyền khi LDAP unavailable không?** Chỉ khi policy cho phép dữ liệu stale; không dùng cache cũ để cấp quyền nhạy cảm.
21. **Nên ghi gì khi không lấy được LDAP result code có cấu trúc?** resultCode=UNKNOWN, exception class và cause class đã kiểm soát.
22. **Log backend có thể thay thế redaction tại nguồn không?** Không; raw data có thể đã vào file, queue hoặc sink khác trước khi mask.

## Tài liệu tham khảo

- [Spring LDAP — Exception package summary](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/package-summary.html)
- [Spring LDAP — NamingException API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/NamingException.html)
- [Spring LDAP — AuthenticationException API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/AuthenticationException.html)
- [Spring LDAP — CommunicationException API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/CommunicationException.html)
- [RFC 4511 — LDAP Protocol, Result Message and Result Codes](https://datatracker.ietf.org/doc/html/rfc4511)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/how-to/logging.html)

**Ghi nhớ:** Giữ khả năng điều tra bằng event name, operation, error category, exception class, result code đã xác minh, directory/base alias, query ID, duration, attempt và correlation ID. DN có thể chứa PII; nếu cần tương quan, dùng HMAC reference có key version và quản lý secret, không dùng hash thường. Không ghi raw filter, attribute values, matchedDN, referral URI, diagnosticMessage, exception message hoặc Bind credentials. Phân loại lỗi bằng exception type và metadata có cấu trúc; nếu không đủ thông tin, dùng UNKNOWN thay vì đoán. API response phải được chuẩn hóa, retry phải dựa trên category và tính idempotent, còn log store cần quyền truy cập, retention và kiểm thử redaction trên mọi sink.
