# Giữ DN, filter và operation context khi ghi log lỗi

## 1. Vì sao lỗi LDAP cần ngữ cảnh?

Một dịch vụ Java dùng **Spring LDAP** có thể truy vấn người dùng, kiểm tra nhóm, xác thực bằng bind và thay đổi entry qua `LdapTemplate`, `LdapClient` hoặc Object-Directory Mapping (ODM). Các thao tác đó làm việc với những khái niệm riêng của LDAP: **Distinguished Name (DN)**, **search filter**, **base DN**, **search scope**, danh sách thuộc tính, loại thao tác và danh tính tài khoản bind.

Nếu chỉ ghi:

~~~text
ERROR LDAP operation failed: NamingException
~~~

thì người trực vận hành khó xác định lỗi thuộc truy vấn nào, nhánh thư mục nào, máy chủ nào hay thao tác nào. Có thể một lần `SEARCH` ở `ou=people` thất bại do sai filter, trong khi `MODIFY` ở `ou=groups` thất bại vì không đủ quyền; hai lỗi cần cách điều tra hoàn toàn khác nhau.

Trong chương **Exception**, bài học này hướng dẫn **giữ DN, filter và operation context khi ghi log lỗi** để truy vết đúng yêu cầu, đồng thời bảo vệ dữ liệu cá nhân và bí mật LDAP. “Giữ ngữ cảnh” không có nghĩa ghi nguyên toàn bộ yêu cầu: DN và filter có thể chứa tên người, email, số điện thoại, định danh nhân sự hoặc dữ liệu nhạy cảm. Mục tiêu là **ghi đủ tín hiệu để chẩn đoán, trong hình thức đã được kiểm soát**.

Sau bài học, bạn có thể:

- Xác định tập trường log hữu ích cho `SEARCH`, `BIND`, `COMPARE`, `ADD`, `MODIFY`, `DELETE`.
- Bảo toàn **cấu trúc DN và filter** bằng cách ghi phần được phép, template và trạng thái đã che dữ liệu.
- Bổ sung trace ID, endpoint logic, thời lượng, giai đoạn thất bại và nhóm exception.
- Ghi log có cấu trúc trong mã Spring LDAP, ném lại lỗi để không đánh mất nguyên nhân.
- Kiểm thử log vẫn chẩn đoán được lỗi mà không làm rò rỉ mật khẩu, filter value nhạy cảm hoặc thông tin cá nhân.

## 2. Những thông tin có giá trị khi chẩn đoán lỗi

Một sự kiện log nên trả lời được các câu hỏi: **đã làm gì, ở đâu, với điều kiện gì, trên endpoint nào, thất bại ở bước nào và có thể liên hệ tới request nào?**

| Trường ngữ cảnh | Ví dụ đã kiểm soát | Tác dụng | Lưu ý bảo mật |
| --- | --- | --- | --- |
| `event` | `ldap.operation.failed` | Nhận diện sự kiện ổn định để lọc/đếm | Dùng tên cố định |
| `operation` | `SEARCH`, `MODIFY`, `BIND` | Biết loại thao tác đang thất bại | Không biến thông tin xác thực thành tên thao tác |
| `base_dn` hoặc `dn_shape` | `ou=people,dc=example,dc=org` | Biết nhánh thư mục hoặc loại đối tượng | Che RDN chứa tên/email/UID nếu cần |
| `filter_template` | `(uid={value})` | Biết điều kiện truy vấn và thuộc tính được so khớp | Đây là **mẫu ghi log**, không phải filter có thể gửi nguyên văn đến server |
| `filter_fields` | `uid`, `objectClass` | Phân biệt lỗi cấu trúc/truy vấn | Không log giá trị người dùng nếu không được phép |
| `scope` | `SUBTREE` | Phân biệt tìm một entry, một mức và toàn cây | Dùng nhãn theo chính sách ứng dụng |
| `requested_attrs` | `[cn,mail]` | Biết thuộc tính được yêu cầu | Tên thuộc tính cũng có thể nhạy cảm theo chính sách |
| `target` | `primary_directory` | Biết cụm LDAP logic cần điều tra | Không nhất thiết tiết lộ hostname nội bộ trong log công khai |
| `auth_identity_kind` | `service_account` | Phân biệt tài khoản dịch vụ và bind người dùng | Không ghi password hoặc token |
| `stage` | `CONNECT`, `TLS`, `BIND`, `SEARCH` | Phân biệt lỗi hạ tầng và truy vấn | Chỉ ghi stage mà ứng dụng thực sự biết |
| `duration_ms` | `84` | Nhìn thấy độ trễ và timeout | Giá trị số, không chứa payload |
| `error_type` | `CommunicationException` | Phân nhóm nguyên nhân | Tránh tự ghi toàn bộ message chứa payload |
| `trace_id` hoặc `correlation_id` | ID do hệ thống tracing cấp | Nối log LDAP với request và các service khác | Không lấy trực tiếp input chưa chuẩn hóa làm ID |

**Không phải thao tác nào cũng có filter.** `BIND`, `ADD`, `MODIFY` và `DELETE` chủ yếu gắn với DN mục tiêu; `SEARCH` còn cần base DN, search scope, filter và thuộc tính yêu cầu. Mọi sự kiện nên có **operation** rõ ràng thay vì một chuỗi lỗi chung chung.

### 2.1. Ví dụ log thiếu và log đủ ngữ cảnh

Log quá ít thông tin:

~~~text
WARN LDAP error
~~~

Log có thể truy vết mà không đưa dữ liệu cá nhân vào message:

~~~text
event=ldap.operation.failed
trace_id=9b20f1d8
operation=SEARCH
target=primary_directory
stage=SEARCH
base_dn=ou=people,dc=example,dc=org
filter_template=(uid={value})
filter_params=[REDACTED]
scope=SUBTREE
duration_ms=84
error_type=CommunicationException
~~~

Các trường có thể được ghi qua structured logger thành JSON thay vì nhiều dòng như ví dụ. Cấu trúc log có thể thay đổi theo framework; yếu tố quan trọng là **tên trường ổn định, giá trị an toàn và đủ thông tin để liên hệ tới thao tác gốc**.

## 3. Ghi DN đủ hữu ích nhưng tránh lộ dữ liệu

DN xác định một entry trong LDAP; ví dụ:

~~~text
uid=an.nguyen,ou=people,dc=example,dc=org
~~~

Các thành phần `ou=people` và `dc=example,dc=org` thường có ích để định vị nhánh lỗi. Nhưng `uid=an.nguyen` là định danh người dùng và có thể thuộc dữ liệu cá nhân; các RDN dạng `cn=Nguyễn Văn A` hoặc `mail=...` còn nhạy cảm hơn.

Hãy chọn mức log theo chính sách dữ liệu:

| Tình huống | Thông tin nên giữ | Thông tin nên che |
| --- | --- | --- |
| Search theo nhánh nhân viên | Base DN ở mức nhánh `ou=people,dc=example,dc=org` nếu được phép | Giá trị UID/email trong RDN hay filter |
| Modify một entry cụ thể | `operation=MODIFY`, `dn_parent`, `rdn_attribute=uid`, correlation ID | `rdn_value` chứa định danh cá nhân |
| Xóa entry nhóm | `operation=DELETE`, loại entry và nhánh nhóm | Tên nhóm nhạy cảm hoặc DN đầy đủ theo phân loại |
| Bind tài khoản dịch vụ | `auth_identity_kind=service_account`, alias được phép | Mật khẩu, secret, DN bind nhạy cảm |
| Bind theo người dùng cuối | `auth_identity_kind=end_user`, trace ID | DN người dùng đầy đủ, mật khẩu và dữ liệu xác thực |

Đối với môi trường nội bộ có quyền truy cập log hạn chế, tổ chức có thể cho phép ghi một số DN đầy đủ để điều tra. Quyết định này cần dựa trên **phân loại dữ liệu, mục đích và thời hạn lưu giữ**, không mặc định rằng “DN không phải mật khẩu nên có thể log tự do”.

### 3.1. DN không phải một chuỗi có thể tách bừa bằng dấu phẩy

DN dùng cú pháp đặc biệt theo RFC 4514. Giá trị RDN có thể chứa dấu phẩy đã escape, ký tự đặc biệt hoặc nhiều thành phần:

~~~text
cn=Doe\, Jane,ou=people,dc=example,dc=org
~~~

Tách DN bằng `split(",")` có thể làm sai cấu trúc và dẫn đến log che dữ liệu không đúng. Khi cần xử lý DN, dùng bộ phân tích phù hợp, chẳng hạn `javax.naming.ldap.LdapName` hoặc tiện ích DN của Spring LDAP, sau đó áp dụng **chính sách cho phép trường cụ thể**. Không giả định parser tự che PII; việc redaction là trách nhiệm riêng.

Nếu không có cơ chế sanitize đáng tin, log `dn_kind=person_entry` và `base_dn` đã được phê duyệt thay vì ghi nguyên `target_dn`. Có thể thêm mã tham chiếu nội bộ được sinh an toàn để tìm bản ghi tương ứng trong hệ thống có thẩm quyền.

## 4. Giữ filter và cấu trúc truy vấn mà không làm lộ giá trị

Filter LDAP là thành phần quan trọng khi chẩn đoán lỗi `SEARCH`: dùng sai thuộc tính, sai dấu ngoặc, dùng giá trị rỗng, thiết kế truy vấn quá rộng hoặc filter không phù hợp schema đều có thể gây sự cố.

Ví dụ filter:

~~~text
(&(objectClass=person)(uid=an.nguyen))
~~~

Cấu trúc `(&(objectClass=person)(uid=...))` hữu ích cho người điều tra; nhưng `an.nguyen` có thể là PII. Vì vậy, phân biệt ba loại dữ liệu:

- **Filter thực thi:** filter được thư viện tạo hoặc gửi đến LDAP server, chứa những giá trị cụ thể.
- **Filter template/shape:** cấu trúc dự kiến được ứng dụng định nghĩa để ghi log, ví dụ `(&(objectClass=person)(uid={value}))`.
- **Giá trị tham số:** `uid`, email, số điện thoại hoặc các điều kiện do người dùng cung cấp; được che hoặc xử lý theo chính sách.

**Filter template trong log không phải filter LDAP hợp lệ dùng để thực thi.** Ký hiệu `{value}` chỉ đánh dấu vị trí tham số trong bản ghi chẩn đoán. Khi cần xác nhận lỗi encode/escape, phải tái hiện trong lab với dữ liệu giả và kiểm tra cách API xây filter thực tế.

### 4.1. Dùng API xây filter an toàn

Spring LDAP cung cấp `LdapQueryBuilder` để xây filter từ tên thuộc tính và giá trị. Ví dụ:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

ldapTemplate.search(
    query().base("ou=people").where("uid").is(uid),
    (org.springframework.ldap.core.AttributesMapper<String>)
        attrs -> (String) attrs.get("cn").get()
);
~~~

Với API này, ứng dụng không phải tự nối chuỗi `"(uid=" + uid + ")"` từ input. **Không dùng việc ghi log giá trị đã che để bỏ qua yêu cầu escape/filter validation.** An toàn của quá trình xây truy vấn và an toàn của dữ liệu ghi log là hai việc khác nhau.

Nếu cần ghi đầy đủ filter để điều tra một sự cố đặc biệt, hãy sử dụng **kênh chẩn đoán được kiểm soát** với phân quyền, phạm vi dữ liệu, thời gian bật và retention rõ ràng. Đừng bật raw filter logging mặc định trên hệ thống có thông tin cá nhân; log message exception có thể vô tình lặp lại raw filter.

### 4.2. Tránh log injection và log quá lớn

DN, filter hoặc giá trị từ người dùng có thể chứa dấu xuống dòng, ký tự điều khiển, Unicode bất thường hoặc chuỗi rất dài. Nếu chèn trực tiếp vào log dạng text, attacker có thể làm giả một dòng log mới hoặc gây tăng khối lượng log.

Nên dùng logger có cấu trúc, giới hạn độ dài, redaction dựa trên allowlist và **chuẩn hóa các trường định danh không đáng tin** trước khi ghi. Một dấu `[REDACTED]` an toàn và ổn định có ích hơn việc log ẩn một phần nhưng vẫn đủ để nhận diện người dùng qua nhiều trường.

## 5. Operation context: biết chính xác thao tác đã thất bại

Ngoài DN/filter, cần ghi bối cảnh do ứng dụng biết **tại thời điểm gọi LDAP**. Không chỉ dựa vào `Exception#getMessage()` để khôi phục ngữ cảnh vì exception có thể đã bị translate hoặc message không đủ chi tiết.

| Operation | Trường nên có | Tránh ghi |
| --- | --- | --- |
| `SEARCH` | Base DN, filter template, scope, danh sách attribute name được phép, limit/timeout dự kiến | Giá trị search chứa PII, toàn bộ kết quả |
| `BIND` / xác thực | Loại bind (service/user), TLS mode, target alias, giai đoạn lỗi, trace ID | DN/mật khẩu người dùng, token hoặc password bind |
| `COMPARE` | Entry DN đã sanitize, thuộc tính được so sánh | Giá trị so sánh nhạy cảm |
| `ADD` | Parent DN, object class/loại entry, thao tác, trace ID | Toàn bộ attributes đầu vào, secret |
| `MODIFY` | Entry DN dạng an toàn, tên thuộc tính sửa, loại modification, trace ID | Giá trị cũ/mới, mật khẩu hoặc thông tin nhân sự |
| `DELETE` | DN dạng an toàn, loại entry, trace ID | PII trong DN đầy đủ nếu không được phép |
| `MODIFY DN` / rename | Parent DN cũ/mới được phép, loại thao tác | RDN giá trị nhạy cảm của hai phía |

Với `MODIFY`, danh sách **tên thuộc tính** có thể đủ để chẩn đoán một lỗi schema hoặc ACL mà không cần ghi nội dung sửa đổi. Ví dụ:

~~~text
event=ldap.operation.failed
operation=MODIFY
target=primary_directory
entry_kind=person
dn_parent=ou=people,dc=example,dc=org
rdn_attribute=uid
rdn_value=[REDACTED]
changed_attributes=[telephoneNumber,displayName]
error_type=NoSuchAttributeException
trace_id=c5e19a40
~~~

Kể cả tên thuộc tính cũng có thể tiết lộ hoạt động nhạy cảm (ví dụ thay đổi quyền hoặc nhóm đặc biệt); cần phân loại và giới hạn truy cập log tương ứng.

### 5.1. Trace ID, endpoint và thời gian

Một trace ID do hệ thống tạo giúp liên hệ lỗi LDAP với yêu cầu HTTP, background job, message hoặc tác vụ batch mà không cần đặt tên người dùng vào log. Ghi thêm `target=primary_directory` hoặc alias cấu hình giúp phân biệt LDAP chính với endpoint dự phòng. Nếu phải phân biệt node thật, có thể lưu hostname đầy đủ trong **log hạ tầng được phân quyền**, còn log ứng dụng chung dùng alias.

`duration_ms` giúp phát hiện timeout hoặc chậm bất thường. Nếu có retry, cần thêm `attempt` hoặc `retry_count` và kết quả cuối cùng để không hiểu nhầm nhiều lần thử là nhiều sự cố độc lập.

Không ghi endpoint alias một cách tuỳ ý từ input của người dùng; dùng tên cố định được cấu hình. Nếu trace ID đến từ client, phải kiểm tra định dạng và giới hạn độ dài, hoặc dùng ID nội bộ do tầng tracing cấp.

## 6. Ví dụ ghi log có ngữ cảnh trong Spring LDAP

Đoạn code sau ghi **tên operation, base DN được phép, filter template, trạng thái tham số bị che, endpoint alias, độ trễ và loại exception**, sau đó ném lại exception để tầng trên xử lý. Ví dụ giả định `LdapTemplate` đã được cấu hình dùng `LdapContextSource` an toàn (LDAPS hoặc StartTLS bắt buộc).

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectorySearchService {
    private static final Logger LOG =
        LoggerFactory.getLogger(DirectorySearchService.class);

    private static final String LOGGED_BASE_DN =
        "ou=people,dc=example,dc=org";
    private static final String FILTER_TEMPLATE =
        "(uid={value})";

    private final LdapTemplate ldapTemplate;

    public DirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        long startNanos = System.nanoTime();

        try {
            return ldapTemplate.search(
                query()
                    .base("ou=people")
                    .where("uid").is(uid),
                (AttributesMapper<String>) attributes ->
                    (String) attributes.get("cn").get()
            );
        } catch (org.springframework.ldap.NamingException ex) {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNanos
            );

            // MDC traceId do hệ thống tracing quản lý và chuẩn hóa.
            String traceId = MDC.get("traceId");

            LOG.warn(
                "event={} operation={} target={} base_dn={} " +
                "filter_template={} filter_params={} duration_ms={} " +
                "error_type={} trace_id={}",
                "ldap.operation.failed",
                "SEARCH",
                "primary_directory",
                LOGGED_BASE_DN,
                FILTER_TEMPLATE,
                "[REDACTED]",
                elapsedMs,
                ex.getClass().getSimpleName(),
                traceId
            );

            // Không nuốt lỗi, không làm mất exception/cause gốc.
            throw ex;
        }
    }
}
~~~

Ở đây `LOGGED_BASE_DN` là **nhánh được chính sách cho phép ghi log**, không phải chuỗi DN do người dùng nhập. Tương tự, `FILTER_TEMPLATE` do mã ứng dụng khai báo và được duy trì đồng bộ với cấu trúc truy vấn; tham số `uid` không xuất hiện trong log. Trong thực tế, khi filter phức tạp hoặc được xây động, cần một cơ chế biểu diễn shape/metadata nhất quán để log không mô tả sai truy vấn thật.

Lưu ý về thiết kế ví dụ:

- `org.springframework.ldap.NamingException` đại diện cho nhóm ngoại lệ LDAP đã được Spring LDAP chuyển đổi từ JNDI; các lỗi runtime khác hoặc lỗi từ mapper cần được phân loại ở ranh giới phù hợp. Không mặc định mọi `RuntimeException` là lỗi LDAP.
- Bắt lỗi ở **vị trí biết operation và tham số** giúp tránh ghi log chung chung ở tầng HTTP khi ngữ cảnh đã mất.
- `LOG.warn(...)` ở đây chủ động không đưa `ex` làm đối số cuối: stack trace và `ex.getMessage()` có thể chứa dữ liệu nhạy cảm. Với log chẩn đoán hạn chế, có thể chọn ghi stack trace sau khi đánh giá rủi ro rò rỉ và kiểm soát truy cập.
- `throw ex` giữ nguyên exception để tầng gọi quyết định xử lý hoặc chuyển thành lỗi nghiệp vụ; log không thay thế exception propagation.
- Nếu dự án đã có structured logging/JSON encoder, nên dùng các trường có tên ổn định thay vì parse lại message text. Không đặt dữ liệu chưa sanitize vào MDC dùng chung cho cả request.

### 6.1. Khi filter hoặc DN được tạo động

Đừng ghi một template cố định nếu truy vấn có thể dùng `AND`, `OR`, thêm điều kiện nhóm hoặc chuyển base DN theo tenant. Hãy xây metadata ở **cùng nơi** xây query: operation, nhánh đã xác thực, loại filter và các attribute name được phép. Nếu một trường nhạy cảm không thể redaction an toàn, lưu nhãn `[REDACTED]` cùng mã truy vết nội bộ. Log phải phản ánh đường code thực sự chạy, tránh suy đoán từ thông báo exception.

### 6.2. Không ghi một lỗi nhiều lần ở mọi tầng

Nếu `DirectorySearchService` đã ghi sự kiện có trace ID, tầng HTTP/service phía trên có thể chuyển lỗi thành phản hồi thích hợp mà **không lặp toàn bộ log stack**. Việc log trùng ở các tầng làm tăng dữ liệu nhạy cảm, khó đếm sự cố và có thể khiến alert báo nhiều lỗi cho cùng một request.

Một quy ước hữu ích là: **tầng biết ngữ cảnh LDAP ghi sự kiện kỹ thuật**, tầng ngoài ghi kết quả nghiệp vụ hoặc HTTP status với cùng trace ID. Hai tầng không cần cùng in lại DN/filter.

## 7. Bảo toàn nguyên nhân lỗi khi dịch ngoại lệ

Java JNDI có nhóm `javax.naming.NamingException` và các ngoại lệ con. Spring LDAP chuyển nhiều lỗi JNDI thành runtime exception thuộc hệ phân cấp ngoại lệ Spring LDAP. Vì vậy, thông điệp tại tầng controller có thể khác lỗi gốc từ server; nếu chỉ ghi tên lỗi ngoài cùng, người xử lý mất dấu giai đoạn thất bại.

Trong log, ngoài `error_type` có thể dùng một **mã lỗi chuẩn hóa theo ứng dụng**:

| Nhóm sự cố | Tín hiệu thường gặp | Ngữ cảnh bổ sung có ích | Hướng xử lý |
| --- | --- | --- | --- |
| Không tìm thấy entry | `NameNotFoundException` | Operation, base DN, filter shape | Kiểm tra DN/filter; đôi khi là kết quả nghiệp vụ bình thường |
| Schema hoặc attribute | `NoSuchAttributeException`, lỗi schema | Operation, loại entry, tên thuộc tính | Kiểm tra schema và cấu trúc thao tác |
| Không đủ quyền | `NoPermissionException` hoặc LDAP insufficient access | Operation, target alias, auth identity kind | Kiểm tra ACL và danh tính bind |
| Sai thông tin xác thực | `AuthenticationException` / invalid credentials | `stage=BIND`, service/user bind | Kiểm tra DN, credential, chính sách; không ghi password |
| Mạng hoặc server ngắt | `CommunicationException`, `ServiceUnavailableException` | `stage=CONNECT/SEARCH`, target, duration, attempt | Xem network/timeout/server; đánh giá retry |
| TLS/certificate | Lỗi JSSE/PKIX nằm trong cause chain | `stage=TLS`, TLS mode, target | Kiểm tra truststore, SAN/hostname, chain |
| Filter không hợp lệ | LDAP filter parse error hoặc schema-related error | Filter template và field names | Xác minh filter builder và dữ liệu giả để tái hiện |

Các tên exception và lỗi thực tế tùy phiên bản Spring LDAP, nhà cung cấp JNDI và máy chủ thư mục. **Không suy đoán retryability chỉ từ một tên lớp**: cần biết operation, trạng thái kết nối và việc server có thể đã thực hiện thao tác hay chưa.

### 7.1. Giữ cause chain nhưng kiểm soát nội dung log

Để phục vụ xử lý lỗi, có thể **ném lại exception gốc** hoặc bao bọc bằng exception nghiệp vụ có `cause` thay vì tạo một exception trống:

~~~java
try {
    performDirectoryOperation();
} catch (org.springframework.ldap.NamingException ex) {
    // Mã ví dụ: ghi context đã được sanitize ở ranh giới LDAP.
    throw new DirectoryUnavailableException(
        "Directory operation failed; use trace ID for diagnostics",
        ex
    );
}
~~~

`DirectoryUnavailableException` và `performDirectoryOperation()` trong ví dụ là **thành phần giả định của ứng dụng**, không phải lớp/API dựng sẵn của Spring LDAP. Khi triển khai, phải định nghĩa lớp exception nghiệp vụ và chỉ bọc lỗi phù hợp; lỗi như không tìm thấy entry không nên bị chuyển thành “directory unavailable” một cách máy móc.

**Giữ cause trong exception không có nghĩa phải in toàn bộ cause chain ra log chung.** `NamingException#getMessage()`, `getResolvedName()` hoặc `getRemainingName()` có thể chứa DN, tên entry hay dữ liệu cần che. Log ở mức truy cập rộng nên dùng thông tin allowlist; stack/cause đầy đủ chỉ được xử lý trong kênh chẩn đoán hạn chế nếu chính sách cho phép.

## 8. Ghi log và retry phải gắn với operation

Ngữ cảnh của `SEARCH` và `MODIFY` khác nhau cả về cách retry:

- Một `SEARCH` chỉ đọc có thể được retry có giới hạn sau lỗi kết nối tạm thời, khi chính sách cho phép và kết nối mới có TLS hợp lệ.
- Một `MODIFY`, `ADD` hoặc `DELETE` có thể đã được server áp dụng trước khi phản hồi bị mất. Retry mù quáng có thể gây thao tác lặp, kết quả sai hoặc lỗi cạnh tranh.
- Lỗi `invalidCredentials`, thiếu quyền hoặc filter không hợp lệ thường **không** nên xử lý bằng retry liên tục.

Do đó, log cần ghi `operation`, `attempt`, `duration_ms` và tình trạng xử lý mà ứng dụng thực sự biết. Với thao tác ghi, tránh tự tuyên bố `applied=false` nếu chỉ biết phía client bị timeout.

### Ví dụ phân biệt hai tình huống

~~~text
event=ldap.operation.failed operation=SEARCH target=primary_directory
filter_template=(uid={value}) attempt=1 error_type=CommunicationException
retry_decision=bounded_retry

event=ldap.operation.failed operation=MODIFY target=primary_directory
dn_kind=person_entry attempt=1 error_type=CommunicationException
outcome=unknown retry_decision=manual_or_reconcile
~~~

Đây là nhãn minh họa. Trong hệ thống thật, quyết định retry phải dựa trên **ngữ nghĩa thao tác, khả năng xảy ra side effect, trạng thái kết nối và chính sách idempotency**, không chỉ dựa vào `error_type`.

## 9. Thiết kế log an toàn và hữu ích trong vận hành

### 9.1. Phân lớp dữ liệu và quyền xem log

Một tổ chức có thể phân log thành:

1. **Log ứng dụng mặc định:** các trường an toàn như event, operation, filter shape, base DN cho phép, endpoint alias, thời lượng và exception type.
2. **Trace/metrics:** trace ID, tỷ lệ lỗi theo operation/endpoint, p95 latency, tỷ lệ timeout/retry. Không đưa UID/email hay raw filter vào label metric vì **cardinality cao** và rủi ro PII.
3. **Chẩn đoán hạn chế:** khi thật sự cần phân tích raw DN/filter, chỉ mở theo quy trình phê duyệt, giới hạn người xem, scope, thời gian lưu và redaction. Không bật mặc định trong production.

Thông điệp gốc từ LDAP server có thể chứa dữ liệu ngoài dự kiến; không tin `ex.getMessage()` đã được sanitize. Nếu cần log nội dung trả về của server để phân tích một lỗi đặc biệt, phải xử lý như dữ liệu không đáng tin và có thể nhạy cảm.

### 9.2. Không đưa những nội dung sau vào log thường

- Mật khẩu simple bind, secret của tài khoản dịch vụ, client certificate private key, token và thông tin xác thực đầu cuối.
- Giá trị `userPassword`, thuộc tính cá nhân, toàn bộ `SearchResultEntry` hoặc danh sách nhóm nhạy cảm.
- Raw search filter chứa email, UID, mã nhân viên, số điện thoại hoặc thông tin người dùng nhập, nếu không có chính sách cho phép.
- DN đầy đủ với RDN cá nhân khi mục đích truy vết có thể đạt bằng base DN và loại entry.
- Chứng từ cấu hình TLS chứa mật khẩu truststore/keystore hoặc các trường nhạy cảm từ exception message.

Giới hạn độ dài mỗi trường, che dữ liệu trước khi ghi, cấu hình retention và quyền xem log theo chính sách. **Bảo vệ log là một phần của bảo vệ dữ liệu LDAP**.

### 9.3. Chuẩn hóa tên trường

Nên thống nhất trong toàn module những tên như `ldap.operation`, `ldap.target`, `ldap.base_dn`, `ldap.filter_shape`, `ldap.stage`, `ldap.error_type` và `trace.id`. Nếu sử dụng JSON logger hoặc OpenTelemetry, ánh xạ sang convention thống nhất của tổ chức để dễ tìm kiếm. Dùng giá trị hữu hạn cho operation/stage/target thay vì chuỗi do người dùng điều khiển.

Không cần mọi log đều chứa tất cả trường. `SEARCH` có filter, `MODIFY` có danh sách tên thuộc tính sửa và DN mục tiêu đã che; điều quan trọng là **tên trường và chính sách redaction được áp dụng nhất quán**.

## 10. Kiểm thử để log có ích mà không rò rỉ dữ liệu

Một bài test chỉ xác nhận “có gọi `logger.warn`” không đủ. Cần kiểm tra nội dung có **đúng ngữ cảnh**, không lộ bí mật, exception vẫn được propagate và log không bị giả mạo bởi input.

| Ca kiểm thử | Cách dựng | Kết quả mong đợi |
| --- | --- | --- |
| Search thất bại | Dùng một LDAP server/fake context gây lỗi mạng | Có `operation=SEARCH`, base DN và filter template đúng, cùng trace ID |
| Modify thất bại | Mô phỏng lỗi ACL hoặc schema | Có `operation=MODIFY` và loại/tên thuộc tính được phép; không chứa giá trị cũ/mới |
| Filter chứa email/UID | Input thử nghiệm có PII giả | Log có filter shape, không có giá trị định danh |
| DN chứa RDN nhạy cảm | `cn=Nguyễn Văn A,ou=people,...` | Log chỉ có nhánh/loại entry hoặc DN đã sanitize |
| Input chứa newline/ký tự điều khiển | UID giả với `\r`, `\n` và chuỗi dài | Không tạo log event giả, nội dung được che/giới hạn |
| Lỗi TLS | Server test trả chứng chỉ không đáng tin | `stage=TLS` nếu có dữ kiện, trace ID và error type; không log secret |
| LDAP authentication thất bại | Bind sai mật khẩu thử nghiệm | Không ghi mật khẩu; phân biệt lỗi BIND với lỗi SEARCH |
| Một lỗi đi qua nhiều tầng | Gọi service và handler của request | Không lặp nguyên văn DN/filter ở nhiều log |
| Exception từ LDAP | Mô phỏng ngoại lệ được Spring LDAP translate | Exception hoặc cause phù hợp vẫn tới tầng xử lý |
| Retry request | Lỗi đọc tạm thời, có attempt | Có attempt/trace ID và outcome đúng, không retry vô hạn |

### 10.1. Kiểm thử giá trị ghi ra thật

Trong kiểm thử, có thể dùng test appender của logging framework để lấy **sự kiện thực đã ghi**; khẳng định:

~~~text
contains("operation=SEARCH") = true
contains("filter_template=(uid={value})") = true
contains("trace_id=") = true
contains("nguyen@example.org") = false
contains("secret-test-password") = false
contains("cn=Nguyễn Văn A") = false
~~~

Đây là **mẫu điều kiện kiểm thử**, không phải mã test của một thư viện cụ thể. Bên cạnh đó, hãy kiểm tra đúng exception/response được chuyển tiếp và mã sự kiện log không bị nhân đôi. Để thử công cụ giám sát, dùng dữ liệu giả và endpoint test thay vì mật khẩu hoặc thư mục thật.

## 11. Bài thực hành: lỗi tra cứu nhóm người dùng

**Bối cảnh:** Ứng dụng phân quyền nội bộ dùng Spring LDAP. Mỗi lần đăng nhập, dịch vụ tìm người dùng bằng `uid` rồi đọc `memberOf` để xác định nhóm. Một sự cố mạng khiến truy vấn LDAP thất bại. Hiện tại chỉ có log:

~~~text
ERROR LDAP failed: CommunicationException
~~~

Mã truy vấn tạo filter tương đương:

~~~text
(&(objectClass=person)(uid=an.nguyen))
~~~

Ứng dụng kết nối qua `ldaps://directory.example.org:636` với tài khoản bind dịch vụ và search base `ou=people,dc=example,dc=org`. Hệ thống có trace ID do gateway cấp.

**Câu hỏi:**

1. Cần bổ sung những trường ngữ cảnh nào để phân biệt sự cố này với một lỗi `MODIFY` nhóm?
2. Có nên log nguyên `uid=an.nguyen`, mật khẩu bind hoặc `memberOf` không? Vì sao?
3. Nếu thay thành `stage=BIND` chỉ vì cùng lỗi `CommunicationException`, log có chính xác không?
4. Viết một ví dụ log đã sanitize mà vẫn đủ để tìm đúng request và endpoint.
5. Nếu lỗi xuất hiện ngay sau một thao tác `MODIFY` làm mất phản hồi, có nên tự retry ngay không?

**Gợi ý lời giải:**

1. Ghi `operation=SEARCH`, `target`, `base_dn` đã được phép, `filter_template`, search scope, tên attribute cần đọc, `duration_ms`, `error_type` và `trace_id`.
2. Không ghi mặc định UID cá nhân, mật khẩu bind hay toàn bộ danh sách nhóm; chúng có thể là PII, bí mật xác thực hoặc dữ liệu phân quyền nhạy cảm. Giữ `uid={value}` và `filter_params=[REDACTED]`.
3. Không. `stage` phải phản ánh bước thực tế đã lỗi. Nếu không xác định được stage, ghi `UNKNOWN` hoặc bỏ trường này thay vì đoán.
4. Ví dụ:

   ~~~text
   event=ldap.operation.failed trace_id=9b20f1d8 operation=SEARCH
   target=primary_directory stage=SEARCH
   base_dn=ou=people,dc=example,dc=org
   filter_template=(&(objectClass=person)(uid={value}))
   filter_params=[REDACTED] scope=SUBTREE
   requested_attrs=[memberOf] error_type=CommunicationException
   ~~~

5. Không retry mù quáng thao tác ghi: có thể server đã áp dụng thay đổi trước khi phản hồi mất. Cần xác minh trạng thái thực tế và cơ chế retry/idempotency phù hợp.

## 12. Checklist và tổng kết

- [ ] Mỗi lỗi LDAP có **operation** và **trace ID** để liên hệ tới request hoặc tác vụ.
- [ ] `SEARCH` lưu đúng **base DN, filter template, scope** và các thuộc tính được phép log; `MODIFY` ghi DN dạng an toàn và tên thuộc tính sửa.
- [ ] Các RDN/filter value chứa PII, mật khẩu bind, token, attribute nhạy cảm và dữ liệu entry đã được **redact** trước khi ghi.
- [ ] Endpoint, TLS mode, stage và thời lượng được ghi theo dữ kiện thực, không suy đoán.
- [ ] Lỗi giữ được **exception/cause** để tầng trên xử lý; không log stack/message nhạy cảm lên kênh công khai.
- [ ] Retry được quyết định theo **operation và outcome**, đặc biệt thận trọng với `ADD`, `MODIFY` và `DELETE`.
- [ ] Logger bảo vệ trước CR/LF injection, chuỗi dài, input chưa được kiểm soát và các trường metric cardinality cao.
- [ ] Test có cả trường hợp **log đủ ngữ cảnh** và **không xuất hiện dữ liệu bí mật** trong output thực.

**Ghi log lỗi Spring LDAP hiệu quả là giữ lại mối liên hệ giữa DN, filter, loại thao tác và nguyên nhân lỗi ở ranh giới gọi LDAP.** Cùng lúc, phải giới hạn nội dung về những trường được phép, che dữ liệu nhạy cảm và giữ exception propagation để người xử lý có thể điều tra chính xác mà không biến log thành một nguồn lộ thông tin thư mục.
