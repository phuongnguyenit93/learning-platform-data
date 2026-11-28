# Giới hạn log thuộc tính, bộ lọc và thông tin xác thực

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập directory qua **Spring Data LDAP repository**, **LdapTemplate** và các cơ chế bind của LDAP. Khi một truy vấn chậm, bind thất bại hoặc một thuộc tính không được đọc, log giúp đội vận hành tìm nguyên nhân. Nhưng một LDAP request có thể chứa **DN, tên người dùng, email, group membership, search filter và thông tin xác thực**. Ghi nguyên request, toàn bộ Attributes hoặc exception message vào log có thể làm lộ dữ liệu directory và bí mật đăng nhập.

Bài thuộc chương **Quan sát**, tập trung vào giới hạn những gì được ghi log đối với **LDAP attributes, search filters và credentials**. Mục tiêu không phải tắt quan sát, mà là thiết kế telemetry đủ để chẩn đoán mà không biến log, metrics hay trace thành một bản sao của directory.

Sau bài học, bạn có thể:

- Phân loại dữ liệu LDAP theo mức nhạy cảm và xác định thông tin tuyệt đối không ghi log.
- Thiết kế **allowlist** cho log event và **denylist** cho secrets/PII.
- Ghi operation, directory alias, search scope, attribute names, duration và outcome mà không ghi raw DN/filter/attribute values.
- Cấu hình log level Spring Boot/Spring LDAP an toàn cho production.
- Xử lý exception LDAP mà không phát tán diagnostic message, bind DN hoặc dữ liệu trong cause chain.
- Thiết kế metrics/tracing với nhãn có cardinality thấp, không dùng username hoặc DN làm label.
- Phân biệt application log, security audit, metrics, trace và health check.
- Kiểm thử redaction, kiểm soát quyền đọc log, retention và khả năng truy vết qua correlation ID.

## 1. Vì sao log LDAP cần giới hạn?

Một lần tìm user có thể tạo ra dữ liệu quan sát như:

~~~text
Operation: search
Base DN: ou=people,dc=example,dc=org
Filter: (&(objectClass=inetOrgPerson)(uid=an))
Attributes: uid, cn, mail, telephoneNumber
Result:
  dn: uid=an,ou=people,dc=example,dc=org
  mail: an@example.org
  telephoneNumber: +84-28-5550-0101
~~~

Những trường này hữu ích khi debug, nhưng chúng cũng tiết lộ:

- **Cấu trúc tổ chức** qua OU, naming context và DN.
- **Danh tính cá nhân** qua uid, cn, mail, phone và group membership.
- **Quy tắc nghiệp vụ** qua filter, base DN và tên thuộc tính.
- **Bí mật đăng nhập** nếu log cả BindRequest, password, token hoặc cấu hình kết nối.
- **Thông tin hệ thống nội bộ** qua hostname, referral URL, bind identity và diagnostic message.

Log thường được gửi tới nhiều nơi: stdout của container, file, agent thu thập, SIEM, hệ thống APM, kho tìm kiếm và bản sao lưu. Người có quyền đọc log có thể rộng hơn người có quyền đọc LDAP. Vì vậy, **quyền truy cập directory không tự động giới hạn được quyền truy cập log**.

### 1.1. Nguyên tắc quan sát an toàn

1. **Log metadata của operation**, không dump request/response LDAP.
2. **Allowlist field** được ghi; không dựa vào việc “nhớ xóa” từng trường nhạy cảm.
3. **Không ghi credentials** ở bất kỳ mức log nào, kể cả DEBUG/TRACE.
4. **Không ghi raw filter, full DN hoặc attribute values** theo mặc định.
5. **Không đưa dữ liệu cá nhân vào metric labels** hoặc trace baggage.
6. **Phân loại lỗi trước khi ghi**, tránh log trực tiếp exception message chưa kiểm soát.
7. Giữ **correlation ID** để nối các log event của cùng một request mà không phải ghi username.
8. Hạn chế quyền truy cập, retention và export của log/trace/metrics.

## 2. Phân loại dữ liệu LDAP trước khi log

| Dữ liệu | Ví dụ | Rủi ro | Mặc định |
| --- | --- | --- | --- |
| **Bind password / user password** | Password trong BindRequest, userPassword, unicodePwd | Chiếm tài khoản, leo thang quyền | **Tuyệt đối không log** |
| **Access token / client secret / private key** | Bearer token, bind secret | Truy cập hệ thống trái phép | **Tuyệt đối không log** |
| **Raw LDAP filter** | (&(uid=an)(mail=...)) | Lộ danh tính, điều kiện tìm kiếm và input của người dùng | Không log; ghi filter category/template |
| **Full DN** | uid=an,ou=people,dc=example,dc=org | PII và cấu trúc nội bộ | Không log mặc định; dùng directory alias hoặc ID đã bảo vệ |
| **Bind DN / service account DN** | uid=svc-reader,ou=service,... | Lộ tên tài khoản kỹ thuật và cấu trúc OU | Không log; dùng bindProfile/directoryAlias |
| **Attribute values** | mail, telephoneNumber, member, description | PII, quyền truy cập, dữ liệu nội bộ | Không log giá trị |
| **Attribute names** | uid, mail, member | Có thể tiết lộ schema và use case | Có thể log khi cần, qua allowlist |
| **Base DN / naming context** | ou=people,dc=example,dc=org | Lộ topology directory | Dùng alias như people-base |
| **Server hostname / IP** | ldap01.internal.example | Lộ topology mạng | Dùng alias; chi tiết chỉ ở kênh vận hành hạn chế |
| **LDAP result code category** | INVALID_CREDENTIALS, TIMEOUT | Rủi ro thấp nếu đã chuẩn hóa | Có thể log |
| **Duration / result count** | 42 ms / 1 entry | Rủi ro thấp | Có thể log |
| **Correlation ID / operation ID** | UUID ngẫu nhiên | Có thể liên kết hoạt động | Có thể log, không nhúng PII vào ID |

**Raw filter không trở nên an toàn chỉ vì đã escape đúng.** LdapQueryBuilder giúp tránh LDAP filter injection; nó không che giấu dữ liệu người dùng khỏi log. Tương tự, DN được escape đúng cú pháp vẫn có thể chứa tên và cấu trúc tổ chức nhạy cảm.

### 2.1. Allowlist tốt hơn denylist

Ví dụ event được phép ghi:

~~~json
{
  "event": "ldap.operation",
  "operation": "search",
  "directory": "people-primary",
  "baseAlias": "people",
  "scope": "SUBTREE",
  "filterType": "USER_BY_UID",
  "requestedAttributes": ["uid", "cn"],
  "resultCount": 1,
  "durationMs": 24,
  "outcome": "SUCCESS",
  "correlationId": "6c46e5f7-6c68-4f57-83a7-9e6a4b3a9a12"
}
~~~

Event này trả lời được: thao tác nào, trên directory nào, dùng scope nào, loại truy vấn nào, đọc những attribute nào, mất bao lâu và có thành công không.

Không thêm những trường như:

~~~text
filter=(uid=an)
baseDn=ou=people,dc=example,dc=org
bindDn=uid=svc-reader,ou=service-accounts,...
attributes.mail=an@example.org
password=...
~~~

Không nên xây event bằng cách serialize toàn bộ request object rồi dùng regex xóa vài key. Khi object thêm field mới, secret mới có thể tự động lọt vào log. Hãy **tạo log event từ những trường đã được phê duyệt**.

## 3. Không ghi credentials: quy tắc bắt buộc

Các thông tin sau không được đưa vào log, trace, metric, audit event, exception detail hoặc message trả về client:

- Password của service bind và password do người dùng nhập.
- userPassword, unicodePwd, password hash hoặc credential material lấy từ directory.
- OAuth access token, refresh token, API key, cookie session, private key và secret của TLS client certificate.
- Toàn bộ JNDI environment map hoặc cấu hình ContextSource có chứa secret.
- Raw BindRequest, protocol dump, packet capture chưa được lọc hoặc debug payload chứa credentials.

**Không log password đã hash rồi coi là an toàn.** Hash có thể cho phép dò đoán từ điển, đặc biệt với mật khẩu yếu hoặc hash scheme cũ. Không cần log password để phân biệt lỗi bind; hãy log operation và error category.

### 3.1. Không đưa secret vào source hoặc log cấu hình

Ví dụ cấu hình:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

LDAP_BIND_PASSWORD phải đến từ secret manager hoặc cơ chế cấp secret của môi trường. Không commit .env chứa giá trị thật, không in Environment, ContextSource, LdapContextSource hoặc bean config ra log.

Tránh:

~~~java
log.debug("LDAP config: {}", ldapContextSource);
log.info("LDAP environment: {}", environment.getSystemProperties());
log.debug("Bind user={}, password={}", bindDn, password);
~~~

Ngay cả khi toString() hiện tại không in password, không nên dựa vào implementation detail ấy. Một wrapper, version hoặc custom bean có thể serialize thêm thông tin về sau.

## 4. Giới hạn log ở Spring Boot và Spring LDAP

Spring Boot sử dụng logging facade; ứng dụng thường dùng **SLF4J** và một logging backend như Logback. Spring LDAP và các thư viện JNDI có thể phát sinh log ở các mức khác nhau tùy phiên bản và cấu hình.

Nếu ứng dụng cần metrics và health endpoints, có thể thêm:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Registry Prometheus chỉ cần khi hệ thống thực sự scrape bằng Prometheus; chọn registry phù hợp với nền tảng quan sát của tổ chức. Phiên bản dependency nên được quản lý bởi Spring Boot dependency management/BOM tương thích.

Production nên bắt đầu với mức log ít chi tiết:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.ldap: INFO
    org.springframework.data.ldap: INFO
    org.springframework.security.ldap: INFO
~~~

Tên package logger cụ thể có thể thay đổi theo dependency/version. Hãy kiểm tra logger thực tế trong ứng dụng và test log output. **Không bật DEBUG/TRACE toàn bộ package LDAP trong production theo thói quen**, nhất là khi chưa biết thư viện ghi những gì.

Nếu cần debug tạm thời:

1. Dùng môi trường test hoặc canary có dữ liệu giả.
2. Xác định đúng logger và đúng khoảng thời gian.
3. Kiểm tra output thực tế với dữ liệu kiểm thử có marker bí mật giả.
4. Bảo đảm appender không ghi request/response, filter, password hoặc attribute values.
5. Đặt thời hạn tắt debug và xác minh log level đã trở lại.

### 4.1. Không dump toàn bộ Attributes hoặc Context

Tránh:

~~~java
ldapTemplate.search(query, (ContextMapper<PersonEntry>) context -> {
    log.debug("LDAP result: {}", context);
    return mapper.map(context);
});
~~~

DirContextOperations, Attributes, Attribute, SearchResult và NamingEnumeration có thể chứa dữ liệu directory. Tránh gọi toString() để debug hoặc serialize chúng thành JSON.

Nên ghi metadata:

~~~java
log.debug(
    "LDAP entry mapped operation={} directory={} requestedFields={} outcome={}",
    "user-profile-read",
    "people-primary",
    "uid,cn,mail",
    "SUCCESS");
~~~

Ở đây requestedFields là danh sách tên attribute đã được allowlist, không phải giá trị attribute. Nếu schema field names cũng nhạy cảm trong môi trường của bạn, thay bằng projection alias như user-basic.

### 4.2. Không log raw filter

Tránh:

~~~java
String filter = "(&(objectClass=inetOrgPerson)(uid=" + uid + "))";
log.debug("LDAP search filter={}", filter);
~~~

Ngay cả khi filter được xây bằng LdapQueryBuilder, đừng ghi query.toString() hoặc filter string để tiện debug. Thay bằng **filterType** do code định nghĩa:

~~~java
log.info(
    "LDAP search started directory={} filterType={} scope={} projection={}",
    "people-primary",
    "USER_BY_UID",
    "SUBTREE",
    "USER_BASIC");
~~~

USER_BY_UID mô tả mục đích query, không chứa giá trị uid. Khi cần điều tra một request cụ thể, dùng correlation ID và hệ thống audit có kiểm soát.

## 5. Thiết kế event log cho LDAP operation

Một log event hữu ích nên có các trường:

| Field | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| event | Tên event | ldap.operation |
| operation | Loại thao tác | search, lookup, bind, modify, rename, delete |
| directory | Alias cấu hình | people-primary |
| baseAlias | Alias của search base | people |
| filterType | Tên truy vấn trong code | USER_BY_UID |
| scope | Phạm vi tìm | OBJECT, ONELEVEL, SUBTREE |
| projection | Bộ attribute đã được phê duyệt | USER_BASIC |
| resultCount | Số kết quả | 1 |
| durationMs | Thời gian | 24 |
| outcome | Kết quả chuẩn hóa | SUCCESS, FAILURE, TIMEOUT |
| errorCategory | Nhóm lỗi | INVALID_CREDENTIALS, ACCESS_DENIED |
| correlationId | Liên kết với HTTP request/job | UUID ngẫu nhiên |
| attempt | Lần thử | 1 |

Không cần mọi event phải có tất cả field. **Bind** không có search scope; **modify** có thể có loại modification nhưng không cần giá trị trước/sau; **health check** có operation name riêng.

### 5.1. Event cho search

~~~json
{
  "event": "ldap.operation",
  "operation": "search",
  "directory": "people-primary",
  "baseAlias": "people",
  "filterType": "USER_BY_UID",
  "scope": "SUBTREE",
  "projection": "USER_BASIC",
  "resultCount": 1,
  "durationMs": 24,
  "outcome": "SUCCESS"
}
~~~

### 5.2. Event cho bind

~~~json
{
  "event": "ldap.operation",
  "operation": "bind",
  "directory": "people-primary",
  "bindProfile": "end-user-auth",
  "durationMs": 37,
  "outcome": "FAILURE",
  "errorCategory": "INVALID_CREDENTIALS"
}
~~~

Không ghi bind DN, username, password hoặc toàn bộ LDAP result diagnostic. bindProfile là alias do ứng dụng định nghĩa, không phải chuỗi DN của principal.

### 5.3. Event cho modify

~~~json
{
  "event": "ldap.operation",
  "operation": "modify",
  "directory": "people-primary",
  "targetType": "PERSON_ENTRY",
  "changeSet": "CONTACT_FIELDS",
  "attributeNames": ["mail", "telephoneNumber"],
  "durationMs": 18,
  "outcome": "SUCCESS"
}
~~~

changeSet là nhãn nghiệp vụ; event không chứa DN, old values, new values hoặc credentials. Với dữ liệu nhạy cảm hơn, chỉ ghi changeSet và số attribute, không ghi tên attribute.

## 6. Ghi log an toàn trong service Spring

Ví dụ service dưới đây tìm người dùng theo uid. Nó chỉ log metadata đã chọn trước:

- Operation là **search**.
- Directory alias là **people-primary**.
- Filter type là **USER_BY_UID**.
- Scope là **SUBTREE**.
- Projection là **USER_BASIC**.
- Thời gian, số kết quả, outcome và error category.

Nó không log giá trị uid, raw filter, DN, attribute values hoặc exception message.

~~~java
package org.example.directory.service;

import java.util.List;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class ObservableDirectorySearchService {
    private static final Logger log =
            LoggerFactory.getLogger(ObservableDirectorySearchService.class);

    private static final String DIRECTORY = "people-primary";
    private static final long SLOW_QUERY_MS = 500;

    private final LdapTemplate ldapTemplate;
    private final MeterRegistry meterRegistry;

    public ObservableDirectorySearchService(
            LdapTemplate ldapTemplate,
            MeterRegistry meterRegistry) {
        this.ldapTemplate = ldapTemplate;
        this.meterRegistry = meterRegistry;
    }

    public List<UserSummary> findByUid(
            String uid, String correlationId) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
        String safeCorrelationId =
                correlationId != null
                && correlationId.matches(
                    "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                    + "[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    + "[0-9a-fA-F]{12}")
                ? correlationId
                : "unavailable";

        long started = System.nanoTime();
        String outcome = "SUCCESS";
        String errorCategory = "NONE";
        int resultCount = 0;

        try {
            List<UserSummary> results = ldapTemplate.search(
                    query()
                        .base("ou=people")
                        .searchScope(SearchScope.SUBTREE)
                        .attributes("uid", "cn")
                        .countLimit(100)
                        .timeLimit(2000)
                        .where("objectClass").is("inetOrgPerson")
                        .and("uid").is(uid),
                    (ContextMapper<UserSummary>) raw -> {
                        DirContextOperations entry =
                                (DirContextOperations) raw;
                        return new UserSummary(
                                entry.getStringAttribute("uid"),
                                entry.getStringAttribute("cn"));
                    });

            resultCount = results.size();
            return results;
        } catch (RuntimeException ex) {
            outcome = "FAILURE";
            // Không ghi ex.getMessage(), stack trace hoặc cause chain.
            errorCategory = "LDAP_OPERATION_FAILED";
            throw ex;
        } finally {
            long elapsedNanos = System.nanoTime() - started;
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

            Timer.builder("ldap.operation")
                    .description("Duration of LDAP operations")
                    .tag("operation", "search")
                    .tag("directory", DIRECTORY)
                    .tag("outcome", outcome)
                    .register(meterRegistry)
                    .record(elapsedNanos, TimeUnit.NANOSECONDS);

            if ("FAILURE".equals(outcome)) {
                log.warn(
                    "LDAP operation failed operation={} directory={} "
                        + "filterType={} scope={} errorCategory={} "
                        + "durationMs={} correlationId={}",
                    "search", DIRECTORY, "USER_BY_UID", "SUBTREE",
                    errorCategory, elapsedMs, safeCorrelationId);
            } else if (elapsedMs >= SLOW_QUERY_MS) {
                log.warn(
                    "LDAP operation slow operation={} directory={} "
                        + "filterType={} scope={} resultCount={} "
                        + "durationMs={} correlationId={}",
                    "search", DIRECTORY, "USER_BY_UID", "SUBTREE",
                    resultCount, elapsedMs, safeCorrelationId);
            } else {
                log.debug(
                    "LDAP operation completed operation={} directory={} "
                        + "filterType={} scope={} resultCount={} "
                        + "durationMs={} correlationId={}",
                    "search", DIRECTORY, "USER_BY_UID", "SUBTREE",
                    resultCount, elapsedMs, safeCorrelationId);
            }
        }
    }

    public record UserSummary(String username, String displayName) {}
}
~~~

Đây là mẫu instrumentation minh họa; ứng dụng thật nên lấy **correlationId** từ middleware/tracing context đáng tin cậy, hoặc tự tạo UUID nếu chưa có. Không lấy giá trị tùy ý từ query string rồi ghi nguyên văn. Nếu lỗi cần điều tra sâu, hãy gắn một **internal incident/reference ID** và gửi diagnostic đã được lọc tới kênh vận hành có quyền hạn riêng.

### 6.1. Vì sao không log exception trực tiếp?

Tránh:

~~~java
catch (RuntimeException ex) {
    log.error("LDAP search failed filter={} uid={}", filter, uid, ex);
    throw ex;
}
~~~

Throwable có thể chứa message, nested cause và stack context. Một số exception/provider có thể đính kèm DN, URL, filter, referral hoặc thông tin server. Nếu đưa cả exception vào logger, backend thường ghi stack trace và message.

Mẫu an toàn hơn:

~~~java
catch (RuntimeException ex) {
    log.warn(
        "LDAP operation failed operation={} directory={} "
            + "errorCategory={} correlationId={}",
        "search",
        "people-primary",
        "LDAP_OPERATION_FAILED",
        correlationId);
    throw ex;
}
~~~

**Không có nghĩa là bỏ mọi khả năng chẩn đoán.** Có thể phân loại lỗi theo loại exception/result code đã được allowlist, ví dụ INVALID_CREDENTIALS, ACCESS_DENIED, TIMEOUT, COMMUNICATION_FAILURE, NO_SUCH_OBJECT hoặc SCHEMA_REJECTED. Chỉ ghi category đã chuẩn hóa; không ghi diagnostic text do server trả về.

Nếu cần stack trace để điều tra sự cố, hãy cân nhắc một **restricted diagnostic sink** có quyền đọc hẹp, retention ngắn, redaction đã kiểm thử và quy trình bật/tắt được phê duyệt. Không chuyển nguyên exception sang sink chung chỉ vì nó được đánh dấu “debug”.

### 6.2. Không tự tạo correlation ID từ dữ liệu cá nhân

Correlation ID nên là UUID ngẫu nhiên hoặc ID do gateway tạo. Không dùng:

~~~text
correlationId = username
correlationId = fullDn
correlationId = email
correlationId = hash(username)
~~~

Hash của username/email có thể bị dò ngược bằng dictionary khi không gian giá trị nhỏ. Nếu cần liên kết cùng một subject qua nhiều hệ thống, dùng **opaque identifier** được thiết kế riêng và kiểm soát quyền; không tự hash PII để đưa vào log.

## 7. Metrics: theo dõi sức khỏe mà không dùng dữ liệu người dùng làm nhãn

Metrics giúp trả lời những câu hỏi như:

- Tỷ lệ LDAP operation thành công/thất bại đang thay đổi thế nào?
- Search, bind và modify mất bao lâu?
- Có bao nhiêu timeout, communication failure hoặc access denied?
- Connection pool có cạn kết nối hoặc chờ quá lâu không?
- Directory nào có latency tăng bất thường?

Với **Micrometer**, một timer có thể đo thời gian operation:

~~~java
Timer.builder("ldap.operation")
    .description("Duration of LDAP operations")
    .tag("operation", "search")
    .tag("directory", "people-primary")
    .tag("outcome", "SUCCESS")
    .register(meterRegistry)
    .record(elapsedNanos, TimeUnit.NANOSECONDS);
~~~

Các tag trên có số lượng giá trị giới hạn, do ứng dụng kiểm soát. Timer cũng có thể cung cấp số lần gọi và phân phối thời gian theo cấu hình registry.

### 7.1. Không dùng high-cardinality labels

**Không** tạo metric như:

~~~text
ldap.operation{uid="an"}
ldap.operation{dn="uid=an,ou=people,..."}
ldap.search{filter="(uid=an)"}
ldap.bind{username="an"}
ldap.operation{correlationId="..."}
~~~

Mỗi username, DN, filter hoặc correlation ID có thể tạo một time series mới. Điều này làm metrics backend phình lớn, tăng chi phí và đồng thời lưu PII. **Không dùng giá trị người dùng, DN, filter, email, exception message hoặc request ID làm metric tag.**

Các tag thường phù hợp nếu tập giá trị nhỏ và được kiểm soát:

| Tag | Giá trị ví dụ | Điều kiện |
| --- | --- | --- |
| operation | search, bind, modify, rename | Enum cố định trong code |
| directory | people-primary, groups-read | Alias cấu hình hữu hạn |
| outcome | success, failure, timeout | Enum cố định |
| errorCategory | access_denied, unavailable | Chỉ category chuẩn hóa, số loại giới hạn |
| scope | object, onelevel, subtree | Enum LDAP |

Không đưa baseDn hoặc serverHost làm tag nếu hệ thống có nhiều giá trị thay đổi theo tenant/request. Dùng alias cấu hình có số lượng hữu hạn.

### 7.2. Result count có thể nhạy cảm

Số lượng kết quả không phải secret đăng nhập, nhưng trong một số use case nó có thể tiết lộ quy mô nhóm hoặc số người trong tổ chức. Nếu count nhạy cảm, ghi bucket:

~~~text
ZERO
ONE
TWO_TO_TEN
MORE_THAN_TEN
~~~

Không ghi danh sách DN/uid để giải thích vì sao kết quả có số lượng đó. Dùng filter type, base alias, scope, latency và mã lỗi chuẩn hóa.

## 8. Distributed tracing: trace operation, không trace payload

Trace giúp nối HTTP request, application service và LDAP operation. Một span có thể ghi:

| Trace attribute | Giá trị an toàn |
| --- | --- |
| Span name | ldap.search |
| Operation | search |
| Directory alias | people-primary |
| Filter type | USER_BY_UID |
| Search scope | SUBTREE |
| Result count/bucket | ONE |
| Duration | Giá trị do tracing SDK đo |
| Error category | TIMEOUT hoặc ACCESS_DENIED |

Không thêm:

- Raw LDAP filter hoặc base DN.
- Full DN, username, email, group members.
- Bind identity, password hoặc token.
- Toàn bộ attributes/result objects.
- Những giá trị trên vào **trace baggage** hoặc span events.

Trace thường được chia sẻ với APM, đội vận hành và dịch vụ bên ngoài. Quyền xem trace có thể khác quyền xem LDAP. **Bật auto-instrumentation không đồng nghĩa payload được tự động redacted**; cần kiểm tra instrumentation agent và exporter thực tế.

### 8.1. Correlation ID và trace ID

Ưu tiên dùng trace ID/correlation ID do middleware tạo để liên kết log. Nếu cần truyền correlation ID qua service, hãy:

1. Chỉ chấp nhận định dạng được kiểm soát (ví dụ UUID).
2. Không nhúng username, DN hoặc email vào ID.
3. Không đưa ID vào metric labels.
4. Không nhận giá trị tùy ý từ HTTP header rồi ghi trực tiếp nếu gateway chưa validate.
5. Giới hạn phạm vi và retention theo chính sách observability.

Nếu dùng MDC của SLF4J, chỉ đưa correlation ID đã xác thực vào MDC và xóa nó sau request để tránh rò context sang thread/reused executor. Không đưa toàn bộ request headers hoặc security principal object vào MDC.

## 9. Phân biệt application log, audit log và diagnostic log

Ba loại log phục vụ các mục đích khác nhau:

| Loại | Câu hỏi cần trả lời | Dữ liệu phù hợp | Kiểm soát |
| --- | --- | --- | --- |
| **Application log** | Operation có thành công/chậm/lỗi không? | Operation, alias, duration, outcome, error category | Quyền vận hành, retention theo môi trường |
| **Security audit** | Ai thực hiện hành động nào, vào lúc nào, kết quả gì? | Actor ID được kiểm soát, action, target reference được bảo vệ, approval/correlation ID | Quyền hẹp, chống sửa, retention theo policy |
| **Restricted diagnostic** | Vì sao một lỗi kỹ thuật cụ thể xảy ra? | Thông tin kỹ thuật tối thiểu đã redaction, stack trace được kiểm soát | Chỉ nhóm hỗ trợ được cấp quyền, bật theo thời hạn |

Audit có thể cần định danh actor/target để đáp ứng yêu cầu truy vết, nhưng **không vì thế mà được phép ghi password, token hoặc toàn bộ LDAP attributes**. Nếu cần liên kết target, ưu tiên opaque ID hoặc tham chiếu được mã hóa/quản lý khóa, không dùng DN raw trong log phổ thông.

### 9.1. Ví dụ audit event

~~~json
{
  "event": "directory.user.contact.updated",
  "actorRef": "actor-opaque-17",
  "targetRef": "directory-object-opaque-42",
  "action": "UPDATE_CONTACT",
  "changedFieldSet": "CONTACT_FIELDS",
  "approvalRef": "approval-2026-041",
  "outcome": "SUCCESS",
  "correlationId": "6c46e5f7-6c68-4f57-83a7-9e6a4b3a9a12"
}
~~~

Đây là schema audit minh họa. Nếu chính sách tổ chức bắt buộc lưu danh tính thật, phải đặt audit store trong vùng kiểm soát tương ứng và hạn chế quyền truy cập. Không dùng application log thay cho audit trail bất biến.

## 10. Health check và readiness cho LDAP

Một ứng dụng có thể đang sống nhưng không truy cập được directory. Nên phân biệt:

- **Liveness:** JVM/process còn hoạt động; không nên restart app chỉ vì LDAP tạm thời mất kết nối.
- **Readiness:** ứng dụng có thể phục vụ những request cần LDAP hay không.
- **Dependency health:** directory có thể được kết nối bằng cách kiểm tra nhẹ, có timeout và giới hạn tần suất.

Health check LDAP nên:

1. Dùng operation nhẹ, timeout rõ ràng và tài khoản kiểm tra có quyền tối thiểu.
2. Không thực hiện search toàn subtree hoặc bind với password người dùng.
3. Không log DN/bind credentials trong health response.
4. Không expose health detail công khai; giới hạn endpoint theo network/role.
5. Tránh chạy probe quá thường xuyên làm tăng tải LDAP hoặc tạo cảnh báo giả.
6. Phân biệt lỗi tạm thời, lỗi cấu hình secret và certificate/TLS.

Nếu dùng Spring Boot Actuator, chỉ expose những endpoint cần thiết và bảo vệ bằng network policy/authentication. Không công khai endpoint như env, configprops, loggers, heapdump hoặc các endpoint có thể tiết lộ cấu hình, log level hay dữ liệu nhạy cảm. Tên endpoint/khả năng phụ thuộc version và cấu hình Actuator.

### 10.1. Không để health check trở thành một lần xác thực người dùng

Health probe không nên dùng username/password thật của một nhân viên để thử bind. Dùng service identity riêng, giới hạn quyền và vòng đời secret. Nếu probe chỉ cần biết kết nối directory còn sẵn sàng, hãy dùng một phép kiểm tra nhẹ được server và chính sách vận hành chấp nhận.

## 11. Redaction và chuẩn hóa log

**Redaction phải xảy ra trước khi dữ liệu rời application boundary.** Đừng đợi tới SIEM hoặc log search mới thay thế một số chuỗi, vì dữ liệu đã có thể được sao chép sang file, queue, backup hoặc APM.

### 11.1. Những cách redaction không đủ an toàn

- Chỉ che chuỗi có tên password, nhưng để lọt userPassword, unicodePwd, credentials hoặc authorization.
- Regex xóa DN theo dấu phẩy; DN có escaping và attribute values có thể chứa dấu phẩy.
- Hash username/email rồi ghi làm correlation ID; giá trị dễ dò bằng từ điển.
- Che raw filter sau khi filter đã được ghi vào exception message hoặc stack trace.
- Xóa trường nhạy cảm khỏi JSON response nhưng vẫn log nguyên entity trước khi mapping.
- Bật TRACE rồi dựa vào log processor lọc payload sau khi thu thập.

### 11.2. Cách làm có kiểm soát

1. Định nghĩa một DTO/event class chỉ có các trường an toàn.
2. Không đưa LDAP object, raw query, Attributes hoặc credentials vào event.
3. Dùng enum/alias cố định cho operation, directory, scope, filter type và outcome.
4. Nếu có giá trị cần liên kết, dùng opaque ID được tạo ở application layer và được quản lý như dữ liệu nhạy cảm.
5. Kiểm thử serialized output của log appender, trace exporter và metrics endpoint.
6. Dùng marker giả như SECRET_MARKER_DO_NOT_LOG_42 trong test; xác minh marker không xuất hiện trong bất kỳ output nào.

### 11.3. Tránh log injection

Nếu log một trường do caller cung cấp, ký tự newline/control có thể tạo log line giả hoặc làm hỏng parser. Tốt nhất **không log raw input**. Nếu một field đầu vào thực sự cần xuất hiện, validate theo allowlist, giới hạn độ dài và encode bằng structured logging; không nối trực tiếp chuỗi vào log message.

Correlation ID, directory alias, operation và filter type nên được sinh/chọn bởi ứng dụng, không phải lấy nguyên văn từ người dùng.

## 12. Cấu hình Actuator và endpoint quan sát

Ví dụ cấu hình expose một số endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when-authorized
~~~

Prometheus endpoint chỉ có nếu ứng dụng đã thêm registry/exporter tương ứng. Endpoint **health**, **info** và **prometheus** vẫn cần được bảo vệ theo network policy, authentication và phân quyền của môi trường. Không expose rộng tất cả endpoint chỉ để thuận tiện debug.

Một số quy tắc:

- Không public endpoint hiển thị environment, configuration properties, loggers hoặc heap dump.
- Không để health detail chứa hostname, DN, bind principal, secret hoặc exception diagnostic.
- Không cấp quyền thay đổi log level cho người dùng API thông thường.
- Nếu cho phép thay đổi logger level khi sự cố, giới hạn operator, audit thao tác và tự khôi phục sau thời gian được phê duyệt.
- Không expose metrics endpoint ra Internet nếu không có authentication/network control phù hợp.

## 13. Runbook: điều tra lỗi mà không cần dump LDAP payload

### 13.1. Search chậm

Thu thập:

- Directory alias và base alias.
- Filter type, search scope, projection alias.
- Duration, result count hoặc count bucket.
- Outcome, error category, connection pool wait time nếu có.
- Trace/correlation ID.

Điều tra:

1. So sánh latency theo directory alias và filter type.
2. Xác minh search scope có rộng hơn use case không.
3. Kiểm tra projection có yêu cầu quá nhiều attribute không.
4. Kiểm tra index của attribute được tìm kiếm và tải LDAP server qua dashboard vận hành.
5. Kiểm tra connection pool, DNS, TLS handshake và network latency.
6. Nếu cần dữ liệu cụ thể, dùng công cụ LDAP có quyền hạn riêng trên môi trường phù hợp; không yêu cầu bật raw filter logging trên production.

### 13.2. Bind thất bại

Ghi operation bind, bindProfile, directory alias, duration và error category đã chuẩn hóa. Phân biệt:

| Category | Hướng điều tra |
| --- | --- |
| INVALID_CREDENTIALS | Kiểm tra secret/version của service bind hoặc kết quả xác thực user theo luồng được phép |
| ACCESS_DENIED | Kiểm tra ACL và quyền của bind identity |
| TIMEOUT | Kiểm tra network, server load và timeout |
| TLS_FAILURE | Kiểm tra truststore, certificate chain, hostname và thời hạn chứng chỉ |
| COMMUNICATION_FAILURE | Kiểm tra DNS, route, connection pool và tình trạng server |

Không yêu cầu người vận hành gửi password vào ticket/chat hoặc chụp màn hình secret. Nếu service secret nghi bị lộ, dùng quy trình rotate secret và kiểm tra nơi đã thu thập log.

### 13.3. Entry không tìm thấy

Chỉ ghi operation, base alias, filter type, scope và outcome NO_SUCH_OBJECT/NOT_FOUND. Kiểm tra:

- Entry có thể đã rename/move hay bị xóa.
- Base alias và naming context có đúng không.
- Search scope có bao phủ OU hiện tại không.
- Service account có quyền đọc entry không.
- Ứng dụng có dùng DN cache đã stale không.

Không ghi full DN cũ và mới vào application log phổ thông. Nếu cần so sánh, dùng công cụ quản trị directory có quyền truy cập phù hợp và ghi kết quả đã bảo vệ vào incident record.

### 13.4. Access denied hoặc schema error

Ghi error category và operation; kiểm tra ACL, objectClass, MUST/MAY attributes, loại operation và identity được chọn. Không ghi toàn bộ entry để “xem thiếu field nào”. Nếu cần kiểm tra schema, sử dụng công cụ quản trị với quyền phù hợp và chỉ trích xuất thuộc tính liên quan.

## 14. Retention, quyền truy cập và xử lý sự cố lộ log

Log, trace và metrics là các bản sao dữ liệu vận hành. Cần áp dụng:

1. **Least privilege:** chỉ nhóm cần thiết mới đọc log LDAP; phân tách quyền đọc application log, security audit và restricted diagnostics.
2. **Encryption:** bảo vệ dữ liệu khi truyền tới collector và khi lưu trữ.
3. **Retention:** đặt thời hạn theo mục đích; không giữ log chi tiết vô hạn.
4. **Access audit:** ghi lại ai truy cập/export dữ liệu log nhạy cảm.
5. **Masking:** che dữ liệu ở nguồn và kiểm tra cả bản sao, archive, alert, dashboard.
6. **Integrity:** audit log cần chống sửa/xóa theo yêu cầu quản trị.
7. **Data minimization:** tránh log payload ngay từ đầu; retention ngắn không biến việc thu thập secret thành an toàn.

Nếu phát hiện password/token hoặc dữ liệu LDAP nhạy cảm đã bị ghi:

- Hạn chế ngay quyền truy cập và export tới log store bị ảnh hưởng.
- Xác định khoảng thời gian, service, appender, collector và các bản sao có thể đã nhận dữ liệu.
- Thực hiện rotate/revoke credential nếu secret có nguy cơ bị lộ.
- Làm sạch hoặc expire dữ liệu theo khả năng và chính sách của log platform, bao gồm index, archive, backup và bản export.
- Kiểm tra access audit để xác định phạm vi truy cập.
- Sửa nguồn phát sinh, thêm regression test và xác minh lại tất cả sink.

Xóa một document khỏi dashboard không chứng minh dữ liệu đã biến mất khỏi archive hoặc backup. Ghi lại quyết định và kết quả xử lý theo quy trình incident của tổ chức.

## 15. Kiểm thử log safety

Kiểm thử phải bao phủ **toàn bộ đường đi của telemetry**, không chỉ kiểm tra một dòng logger:

1. Application log và console output.
2. File appender/rolling archive.
3. JSON log encoder và collector agent.
4. Exception handler và error response.
5. Metrics endpoint/exporter.
6. Trace exporter, baggage và span events.
7. Security audit và restricted diagnostic sink.

### 15.1. Marker test

Dùng giá trị giả, không phải secret thật:

~~~text
uid: secret-marker-user-42
mail: secret-marker-mail@example.invalid
password: SECRET_MARKER_PASSWORD_DO_NOT_LOG
filter: (uid=secret-marker-user-42)
dn: uid=secret-marker-user-42,ou=people,dc=example,dc=org
~~~

Thực hiện một search, một bind thất bại và một modify thất bại trong môi trường test. Thu thập mọi log/trace/metric output, rồi xác nhận các marker nhạy cảm không xuất hiện. Đặc biệt kiểm tra:

- Log event do service tự tạo.
- Log ở mức DEBUG/TRACE của thư viện khi thử trong test.
- Exception message và nested cause.
- Response body trả cho HTTP client.
- Log được serialize thành JSON.

Không dùng password thật trong test chỉ để chứng minh redaction.

### 15.2. Test allowlist event

Một cách kiểm tra là serialize event class chuyên dụng rồi xác nhận chỉ các field được phê duyệt tồn tại. Không serialize trực tiếp đối tượng LDAP:

~~~java
package org.example.directory.observability;

public record LdapOperationEvent(
        String operation,
        String directory,
        String filterType,
        String scope,
        String outcome,
        String errorCategory,
        long durationMs,
        String correlationId) {
}
~~~

Event class không có property cho password, bind DN, raw filter, full DN hoặc attribute values. Khi cần thêm trường mới, review phải xác nhận mục đích, mức nhạy cảm và cardinality trước khi thêm.

### 15.3. Ma trận kiểm thử

| Ca | Dữ liệu/điều kiện | Kết quả cần xác minh |
| --- | --- | --- |
| Search thành công | uid giả và projection cơ bản | Log chỉ có filterType, alias, scope, count, duration |
| Search chậm | Giả lập latency | Có slow-operation event, không có raw filter |
| Bind thất bại | Password marker giả | Marker không xuất hiện ở log/trace/response |
| Service bind lỗi | Secret test sai | Error category phù hợp, không log bind DN/password |
| LDAP timeout | Fault injection test | Timeout được phân loại, không dump exception message |
| Entry không tồn tại | DN test không tồn tại | Log NOT_FOUND/NO_SUCH_OBJECT và base alias |
| ACL từ chối | Service account thiếu quyền | Log ACCESS_DENIED, không dump Attributes |
| Attribute nhiều giá trị | Mail/phone có nhiều value | Không log các value |
| DEBUG/TRACE trong test | Logger thư viện được bật có kiểm soát | Kiểm tra payload không chứa marker |
| Metrics | Nhiều uid khác nhau | Số time series không tăng theo uid |
| Trace | Nhiều request khác nhau | Không có DN/filter/credential trong span/baggage |
| Correlation ID | Header sai định dạng | Bị thay thế/từ chối; không log raw header |
| Actuator | Request từ caller không đủ quyền | Endpoint detail/metrics không bị lộ |
| Log injection | Input có newline/control | Không tạo log line giả |
| Secret incident | Marker xuất hiện ở test sink | Alert/quy trình xử lý xác định được sink và retention |

## 16. Checklist triển khai production

- [ ] Log level mặc định phù hợp; không bật DEBUG/TRACE toàn bộ LDAP package.
- [ ] Không log password, token, key, JNDI environment hoặc raw BindRequest.
- [ ] Không log raw filter, full DN, bind DN hoặc attribute values theo mặc định.
- [ ] Log event được xây từ allowlist, không serialize LDAP object.
- [ ] Exception được phân loại; không ghi message/cause chain chưa redaction vào log chung.
- [ ] Correlation ID được validate và không chứa PII.
- [ ] Metric labels có cardinality thấp; không chứa uid, DN, filter hoặc request ID.
- [ ] Trace spans không có payload, credentials hoặc PII trong baggage.
- [ ] Health/readiness operation nhẹ, timeout rõ và không dùng credential người dùng.
- [ ] Actuator/metrics endpoint được bảo vệ; không expose cấu hình/secret.
- [ ] Log store có access control, encryption, retention và access audit.
- [ ] Có marker tests kiểm tra log, trace, metrics, error response và archive.
- [ ] Có runbook xử lý secret đã bị log và quy trình rotate/revoke.

## 17. Tổng kết và bài tập tự luyện

Quan sát LDAP cần đủ thông tin để tìm ra **operation nào chậm, lỗi ở bước nào, directory nào bị ảnh hưởng và kết quả ra sao**. Những thông tin đó thường có thể lấy từ **operation name, directory alias, filter type, search scope, projection, duration, outcome, error category và correlation ID**. Không cần ghi password, raw filter, full DN hoặc toàn bộ LDAP attributes để đạt khả năng chẩn đoán tốt.

**Credentials tuyệt đối không được log.** Raw filter, DN và attribute values cũng cần được coi là dữ liệu nhạy cảm. Dùng allowlist event, exception classification, metrics labels có cardinality thấp, trace không chứa payload, health check có kiểm soát và restricted audit/diagnostic sink khi thực sự cần. Bảo vệ log bằng quyền truy cập, encryption, retention và kiểm thử marker trên toàn bộ telemetry pipeline.

**Bài tập:**

1. Liệt kê những trường có thể xuất hiện trong một LDAP SearchRequest và phân loại trường nào được log, trường nào không.
2. Thiết kế một log event cho search theo uid mà không chứa uid, raw filter hoặc DN.
3. Vì sao log exception bằng cách truyền cả Throwable vào logger có thể làm lộ dữ liệu directory?
4. Viết metric timer cho search, bind và modify với tag có cardinality thấp.
5. Giải thích vì sao hash username không phải correlation ID an toàn.
6. Phân biệt application log, security audit và restricted diagnostic log.
7. Thiết kế health check LDAP có timeout và tài khoản tối thiểu; giải thích vì sao không nên restart app khi directory tạm thời unavailable.
8. Viết test marker để xác minh password giả không xuất hiện trong log, trace, metrics hoặc HTTP response.
9. Khi cần bật DEBUG để điều tra lỗi, bạn sẽ giới hạn môi trường, thời gian và quyền truy cập như thế nào?
10. Nếu phát hiện bind password đã được ghi vào archive, những bản sao và hành động nào cần được xem xét?

### Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) — cấu hình logging và log levels.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — exposure và bảo vệ endpoint.
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — tích hợp Micrometer và metrics.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — Timer, MeterRegistry, tags và cardinality.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — LdapTemplate, query builder và LDAP operations.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — dữ liệu không nên log, kiểm soát truy cập và xử lý log.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — lưu trữ, truy cập và xoay vòng secrets.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — LDAP Bind/Search requests và response.
