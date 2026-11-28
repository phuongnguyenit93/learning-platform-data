# Retry theo loại lỗi và tính lũy đẳng của thao tác

## Mục tiêu bài học

Khi ứng dụng **SPRING_DATA_LDAP** gọi LDAP server, lỗi có thể xuất hiện do network chập chờn, server quá tải, credential sai, schema không hợp lệ, ACL từ chối hoặc dữ liệu đã thay đổi đồng thời. Retry giúp vượt qua một số lỗi tạm thời, nhưng retry mọi exception có thể làm tăng tải, khóa tài khoản, tạo duplicate hoặc khiến dữ liệu sai sau một lần ghi đã thành công nhưng response bị mất.

Bài thuộc chương **Xử lý lỗi**, tập trung vào hai câu hỏi trước mỗi lần retry:

1. **Lỗi này có khả năng tự hết không?**
2. **Nếu operation đã chạy thành công nhưng client không nhận response, chạy lại có gây tác dụng phụ không?**

Bạn sẽ phân loại exception của Spring LDAP, chọn operation có thể retry, thiết kế backoff và deadline, xử lý trạng thái ghi không xác định, sau đó cấu hình retry có chọn lọc với Spring Retry.

Sau bài học, bạn có thể:

- Phân biệt lỗi transient, permanent và ambiguous outcome.
- Nhận diện các exception Spring LDAP thường gặp.
- Quyết định operation nào có thể retry trực tiếp và operation nào phải reconcile trước.
- Giải thích vì sao timeout sau Add/Modify/Delete/Rename không chứng minh server chưa ghi dữ liệu.
- Dùng bounded retry, exponential backoff, jitter và deadline.
- Cấu hình RetryTemplate chỉ retry những exception được allowlist.
- Thiết kế idempotency key, read-after-write verification và conflict handling.
- Tránh retry storm, circuit-breaker loops và retry lồng nhau.
- Kiểm thử retry bằng fault injection và kiểm tra trạng thái LDAP sau từng tình huống.

## 1. Retry không phải cách xử lý mọi lỗi

Một request tìm user có thể thất bại vì LDAP server tạm thời unavailable. Retry sau một khoảng nghỉ có thể thành công. Nhưng nếu request bị từ chối vì filter sai hoặc bind password không hợp lệ, gửi lại cùng request không làm lỗi biến mất.

Với operation ghi, vấn đề còn khó hơn. Ví dụ:

1. Ứng dụng gửi AddRequest tạo uid=an.
2. LDAP server tạo entry thành công.
3. Network bị ngắt trước khi response đến ứng dụng.
4. Ứng dụng thấy timeout và không biết entry đã được tạo hay chưa.
5. Nếu gửi lại AddRequest, server trả entryAlreadyExists.

Timeout chỉ cho biết **client không nhận được kết quả đúng hạn**. Nó không chứng minh server chưa thực hiện operation.

~~~mermaid
sequenceDiagram
    participant App as Spring application
    participant LDAP as LDAP server
    App->>LDAP: Add uid=an
    LDAP->>LDAP: Persist entry
    LDAP--xApp: Response bị mất do network
    App->>App: Timeout, outcome chưa rõ
    App->>LDAP: Retry Add uid=an
    LDAP-->>App: entryAlreadyExists
    Note over App,LDAP: Phải reconcile trạng thái trước khi kết luận thất bại
~~~

**Nguyên tắc:** retry chỉ an toàn khi lỗi có khả năng tạm thời, operation được phép lặp lại hoặc ứng dụng có cơ chế xác minh/kết thúc trạng thái chưa rõ.

## 2. Ba nhóm kết quả cần phân biệt

| Nhóm | Ý nghĩa | Ví dụ | Hành động |
| --- | --- | --- | --- |
| **Transient failure** | Khả năng tự hết sau một khoảng ngắn | Connection reset, service unavailable, resource tạm thời cạn | Retry có giới hạn nếu operation an toàn |
| **Permanent failure** | Cần sửa input, quyền hoặc cấu hình | Invalid filter, invalid DN, invalid credentials, schema violation, access denied | Không retry; trả lỗi nghiệp vụ hoặc vận hành |
| **Ambiguous outcome** | Không biết server đã commit operation hay chưa | Timeout/connection lost sau khi gửi Modify/Add/Delete/Rename | Đọc lại trạng thái, reconcile rồi mới quyết định |

Một exception class không luôn cho biết đầy đủ trạng thái commit. Ví dụ CommunicationException có thể xảy ra trước khi request đến server hoặc sau khi server đã thực hiện ghi. Vì vậy, cần kết hợp **loại operation**, **thời điểm lỗi**, **cause**, **server result code** và **read-after-write check**.

### 2.1. Transient không đồng nghĩa chắc chắn retry được

ServiceUnavailableException thường biểu thị server/service tạm thời không sẵn sàng. CommunicationException có thể biểu thị lỗi liên lạc. Tuy nhiên:

- Search có thể chạy lại vì không làm thay đổi directory.
- Add có thể đã tạo entry trước khi response mất.
- Modify có thể đã thêm/xóa value trước khi response mất.
- Delete có thể đã xóa entry trước khi response mất.
- Rename có thể đã đổi DN trước khi response mất.

Do đó, transient classification là điều kiện cần, nhưng với write operation còn phải đánh giá tính lũy đẳng.

### 2.2. Permanent không nên được che bằng retry

Các lỗi như invalid search filter, invalid DN, schema violation hoặc insufficient access rights thường cần sửa code/dữ liệu/ACL. Retry cùng input chỉ lặp lại lỗi và tăng tải.

Đừng cấu hình retry cho toàn bộ RuntimeException, NamingException hoặc mọi lỗi LDAP rồi hy vọng policy tự phân biệt được.

## 3. Exception hierarchy của Spring LDAP

Spring LDAP cung cấp một hệ exception unchecked trong package org.springframework.ldap, phản chiếu nhiều loại exception của JNDI. Các exception này kế thừa org.springframework.ldap.NamingException của Spring LDAP; không nên nhầm với javax.naming.NamingException.

Một số loại thường gặp:

| Spring LDAP exception | Ý nghĩa thường gặp | Chính sách retry khởi đầu |
| --- | --- | --- |
| **CommunicationException** | Mất kết nối, lỗi network hoặc communication provider | Có thể retry operation an toàn; write cần reconcile |
| **ServiceUnavailableException** | Directory service không sẵn sàng | Có thể retry có giới hạn |
| **InsufficientResourcesException** | Server/provider thiếu tài nguyên | Có thể retry với backoff nếu server hồi phục |
| **TimeLimitExceededException** | Search vượt thời gian giới hạn | Thường tối ưu query/limit trước; không retry liên tục |
| **SizeLimitExceededException** | Kết quả vượt size limit | Không retry cùng query; paging hoặc thu hẹp scope |
| **AuthenticationException** | Bind/authentication thất bại | Không retry cùng credential |
| **AuthenticationNotSupportedException** | Server không hỗ trợ authentication mechanism | Không retry; sửa cấu hình |
| **NoPermissionException** | Operation bị từ chối quyền | Không retry; kiểm tra ACL |
| **InvalidSearchFilterException** | Filter sai cú pháp | Không retry; sửa filter |
| **InvalidNameException** | DN/name không hợp lệ | Không retry; sửa DN |
| **SchemaViolationException** | Entry/attribute vi phạm schema | Không retry; sửa dữ liệu/schema |
| **NameAlreadyBoundException** | DN đã tồn tại khi bind/add | Reconcile entry; không retry add mù |
| **NameNotFoundException** | DN/base không tồn tại | Thường là lỗi nghiệp vụ hoặc stale reference |
| **NoSuchAttributeException** | Attribute/value không tồn tại trong operation | Reconcile nếu là kết quả retry; không retry mù |
| **AttributeInUseException** | Attribute đang được sử dụng hoặc có conflict | Phân tích result code/operation; không mặc định retry |
| **PartialResultException** | Chỉ nhận được một phần kết quả, thường liên quan referral | Xử lý referral/server-specific; không coi là full success |
| **ReferralException / LdapReferralException** | Server trả referral | Cấu hình referral strategy hoặc xử lý referral; không retry vô hạn |
| **UncategorizedLdapException** | Không phân loại được thành exception cụ thể | Xem cause/result code; mặc định không retry |

Đây là chính sách khởi đầu, không phải bảng ánh xạ tuyệt đối. Provider và server có thể trả exception khác nhau cho cùng một tình huống. Hãy ghi nhận exception type, root cause và LDAP result code đã được chuẩn hóa trong môi trường thực tế.

### 3.1. Spring LDAP NamingException khác Spring DAO DataAccessException

org.springframework.ldap.NamingException là unchecked exception hierarchy riêng của Spring LDAP. Nó kế thừa NestedRuntimeException; không phải mọi lỗi LdapTemplate đều tự động trở thành org.springframework.dao.DataAccessException.

Vì vậy, khi cấu hình retry hoặc exception handler, hãy dùng đúng class trong package org.springframework.ldap. Nếu application layer muốn chuẩn hóa lỗi thành domain exception, hãy chuyển đổi ở adapter/service boundary và giữ cause để chẩn đoán nội bộ.

### 3.2. Không phân loại chỉ bằng message text

Tránh:

~~~java
if (ex.getMessage().contains("timeout")) {
    retry();
}
~~~

Message có thể thay đổi theo JDK, provider, server, ngôn ngữ hoặc phiên bản thư viện. Hãy phân loại bằng exception type và cause chain; nếu cần LDAP result code, map code thành enum do ứng dụng kiểm soát.

### 3.3. Một số LDAP result code thường gặp

| Result code | Tên | Ý nghĩa | Hướng xử lý |
| ---: | --- | --- | --- |
| 3 | timeLimitExceeded | Search vượt time limit | Thu hẹp query/điều chỉnh giới hạn; không retry liên tục |
| 4 | sizeLimitExceeded | Search vượt size limit | Paging hoặc giảm phạm vi |
| 16 | noSuchAttribute | Attribute/value không tồn tại | Kiểm tra schema/trạng thái trước khi quyết định |
| 19 | constraintViolation | Vi phạm constraint/schema | Không retry cùng dữ liệu |
| 20 | attributeOrValueExists | Attribute/value đã tồn tại | Reconcile; có thể là write trước đã thành công |
| 21 | invalidAttributeSyntax | Giá trị sai syntax | Sửa dữ liệu/converter |
| 32 | noSuchObject | DN/base không tồn tại | Kiểm tra DN/stale reference; sau delete có thể là desired state |
| 49 | invalidCredentials | Credential không hợp lệ | Không retry cùng credential; tránh account lockout |
| 50 | insufficientAccessRights | Không đủ quyền | Kiểm tra ACL/identity; không retry |
| 51 | busy | Server đang bận | Có thể retry operation an toàn với backoff nếu policy cho phép |
| 52 | unavailable | Server không khả dụng | Có thể retry operation an toàn có giới hạn |
| 53 | unwillingToPerform | Server từ chối thực hiện | Xác minh policy/constraint; không mặc định retry |
| 68 | entryAlreadyExists | DN đã tồn tại | Reconcile entry; không ghi đè |

Result code có thể được chuyển thành exception khác nhau tùy JNDI provider. Không viết policy phụ thuộc duy nhất vào số code nếu ứng dụng chỉ nhận được exception type/cause. Hãy ghi nhận mapping thực tế trên server được hỗ trợ.

### 3.4. Cẩn thận với partial results

Một số LDAP server, đặc biệt khi có referral hoặc giới hạn kết quả, có thể trả về một phần kết quả rồi phát sinh **PartialResultException** hoặc **SizeLimitExceededException**. LdapTemplate có các tùy chọn ignore exception để phục vụ một số cấu hình server:

- **ignorePartialResultException**: nếu bật, PartialResultException có thể bị bỏ qua và search trả về những entry đã nhận được.
- **ignoreSizeLimitExceededException**: nếu bật, SizeLimitExceededException có thể bị bỏ qua để trả về phần kết quả đã nhận. API Spring LDAP hiện hành ghi nhận tùy chọn này mặc định là true từ phiên bản 2.0.

ignorePartialResultException mặc định là false trong cấu hình hiện hành. Kiểm tra rõ các setter/configuration của LdapTemplate thay vì dựa vào default của phiên bản khác.

Đây không phải retry và cũng không có nghĩa kết quả đầy đủ. Với use case phân quyền, membership hoặc đồng bộ dữ liệu, partial result có thể khiến ứng dụng kết luận sai rằng user không thuộc group hoặc dữ liệu đã bị xóa. Chỉ bỏ qua exception khi nghiệp vụ chấp nhận kết quả không đầy đủ và response/telemetry vẫn thể hiện trạng thái partial rõ ràng.

## 4. Ma trận retry theo operation

| Operation | Có thể retry trực tiếp? | Điều kiện |
| --- | --- | --- |
| Search | Thường có | Query read-only, scope/limit ổn định, deadline còn đủ |
| Lookup | Thường có | Read-only; kết quả có thể thay đổi do concurrent update |
| Bind service account | Có điều kiện | Chỉ retry lỗi transport/service tạm thời; không retry invalid credentials |
| Bind user để xác thực | Rất thận trọng | Không lặp password sai; tôn trọng lockout/rate limit |
| Add entry | Không retry mù | Re-read DN; nếu entry tồn tại, so sánh state/identity trước khi coi là thành công |
| Add attribute value | Không retry mù | Re-read attribute; duplicate có thể là operation trước đã thành công |
| Remove attribute value | Không retry mù | Re-read attribute; value không còn có thể là đã xóa thành công |
| Replace attribute | Chỉ khi semantics được xác định | Có thể ghi đè cập nhật mới của request khác; cần version/assertion hoặc reconciliation |
| Delete entry | Không retry mù | Kiểm tra DN có còn tồn tại và đúng target không |
| Rename/move DN | Không retry mù | Kiểm tra DN cũ và mới, rồi reconcile references |
| Modify group membership | Không retry mù | Đọc lại đúng member value và xử lý duplicate/missing |

### 4.1. Read operation

Search và lookup không làm thay đổi directory nên thường có thể retry khi gặp lỗi transport/service tạm thời. Tuy nhiên, retry không bảo đảm trả về cùng kết quả: dữ liệu có thể thay đổi giữa hai lần đọc. Nếu cần snapshot nhất quán, LDAP search thông thường không cung cấp snapshot transaction cho toàn cây.

### 4.2. Write operation

Một write có thể đã được server thực hiện dù client nhận timeout. Với write, cần phân biệt:

- **Chưa gửi request:** thường có thể thử lại nếu lỗi transport xảy ra trước khi request được gửi.
- **Đã gửi nhưng không nhận response:** outcome chưa rõ; cần đọc lại trạng thái.
- **Nhận LDAP result code:** server đã trả kết quả; xử lý theo result code thay vì retry mọi lỗi.

Client LDAP thường khó chứng minh request đã đến server hay chưa khi connection đứt. Nếu không có bằng chứng, hãy coi write timeout là **unknown outcome**.

## 5. Tính lũy đẳng và khả năng lặp lại

Một operation lũy đẳng khi thực hiện một lần hay nhiều lần với cùng mục tiêu sẽ đưa hệ thống về cùng trạng thái mong muốn.

Ví dụ về ý định nghiệp vụ:

- “Đảm bảo user An là member của group Developers.”
- “Đảm bảo description của entry bằng giá trị X.”
- “Đảm bảo entry tại DN này không tồn tại.”

Các ý định trên có thể được triển khai theo cách lũy đẳng nếu có bước đọc/trạng thái và xử lý conflict đúng. Nhưng LDAP operation thô không phải lúc nào cũng lũy đẳng.

### 5.1. Bảng đánh giá

| LDAP operation | Retry thô | Vì sao |
| --- | --- | --- |
| Search | Có | Không thay đổi directory |
| Add entry | Không | Lần đầu có thể đã tạo entry; lần sau nhận already exists |
| Modify ADD value | Không mặc định | Lần đầu có thể đã thêm; lần sau duplicate value |
| Modify REMOVE value | Không mặc định | Lần đầu có thể đã xóa; lần sau no such attribute/value |
| Modify REPLACE value | Có điều kiện | Có thể ghi đè cập nhật mới của request khác |
| Delete entry | Không mặc định | Lần đầu có thể đã xóa; lần sau no such object |
| Modify DN/Rename | Không | DN cũ có thể không còn; DN mới có thể đã tồn tại |

### 5.2. Ensure state thay vì lặp operation mù

Với yêu cầu thêm thành viên, viết logic theo trạng thái mong muốn:

1. Resolve group và user trong phạm vi được phép.
2. Đọc member attribute hiện tại.
3. Nếu thành viên đã có, trả kết quả already present hoặc success theo contract.
4. Nếu chưa có, gửi Modify ADD đúng một value.
5. Nếu response timeout/connection lost, đọc lại group.
6. Nếu value đã có, coi operation đã đạt trạng thái mong muốn.
7. Nếu value chưa có, có thể thử lại trong retry budget còn lại.
8. Nếu không thể xác minh, trả trạng thái outcome unknown để workflow reconcile tiếp.

Read-before-write không loại bỏ race condition. Hai request đồng thời vẫn có thể cùng đọc chưa có rồi cùng ADD. Hãy xử lý duplicate result code như một conflict có thể reconcile, không biến nó thành lỗi hệ thống không phân loại.

### 5.3. Idempotency key ở application layer

LDAP protocol không có idempotency key chung cho Add/Modify. Nếu request đến từ API hoặc message queue, application có thể tạo một operation record:

~~~text
operationId: opaque UUID
operationType: ADD_GROUP_MEMBER
groupRef: group-opaque-17
memberRef: user-opaque-42
requestedAt: 2026-11-26T10:00:00Z
state: PENDING | APPLIED | FAILED | UNKNOWN
~~~

Lưu operation record ở nơi phù hợp với kiến trúc, kèm unique constraint cho operationId. Khi nhận lại cùng operationId:

- APPLIED: trả kết quả đã lưu.
- PENDING: tiếp tục hoặc khóa xử lý theo workflow.
- FAILED: chỉ cho retry nếu lỗi được phân loại retryable.
- UNKNOWN: reconcile trạng thái LDAP trước khi gửi write lần nữa.

Operation record cần retention và quyền truy cập phù hợp. Không dùng raw DN, password hoặc member list làm idempotency key.

## 6. Backoff, jitter, deadline và retry budget

Retry liên tiếp không nghỉ có thể làm server đang quá tải càng quá tải. Dùng **exponential backoff** để tăng khoảng chờ và **jitter** để tránh nhiều instance cùng retry đúng một thời điểm.

Ví dụ thời gian chờ cơ sở:

\[
d_n = \min(d_0 \times m^n,\ d_{\max})
\]

Trong đó:

- \(d_0\): khoảng chờ ban đầu.
- \(m\): hệ số tăng, thường lớn hơn 1.
- \(n\): số lần retry đã thực hiện.
- \(d_{\max}\): khoảng chờ tối đa.

Jitter có thể chọn ngẫu nhiên trong một khoảng quanh delay cơ sở. Mục tiêu là phân tán request retry giữa các instance.

### 6.1. Ví dụ lịch retry

Với initial delay 200 ms, multiplier 2, max delay 2 giây:

| Lần chờ | Delay cơ sở |
| --- | ---: |
| Retry 1 | 200 ms |
| Retry 2 | 400 ms |
| Retry 3 | 800 ms |
| Retry 4 | 1.600 ms |
| Retry tiếp | Tối đa 2.000 ms |

Đây là lịch cơ sở trước jitter. Số lần retry thực tế phải bị giới hạn bởi deadline của request.

### 6.2. Giới hạn tổng thời gian

Nếu HTTP request có deadline 3 giây, không thể cấu hình retry với backoff có tổng thời gian 10 giây rồi mong caller chờ được. Tổng ngân sách cần tính:

**Tổng thời gian = connection timeout + operation timeout + backoff delays + processing margin.**

Ví dụ:

- Connect timeout: 300 ms.
- Mỗi LDAP operation timeout: 700 ms.
- Tối đa 3 attempts.
- Backoff: 100 ms rồi 200 ms.
- Processing margin: 200 ms.

Tổng worst-case ước tính: **3 × 700 + 300 + 100 + 200 + 200 = 2.900 ms**.

Đây là cách lập ngân sách minh họa; timeout của pool wait, DNS, TLS handshake và provider có thể cần tính riêng.

### 6.3. Retry budget ở nhiều tầng

Nếu API gateway retry 3 lần, service retry 3 lần và message consumer retry 5 lần, một request có thể tạo tối đa 45 LDAP attempts (hoặc hơn nếu có tầng khác). Chỉ một tầng nên là owner chính của retry cho một operation; các tầng khác cần giới hạn hoặc tắt retry trùng lặp.

## 7. Cấu hình retry có chọn lọc với Spring Retry

Spring Retry cung cấp RetryTemplate để bao một operation và cấu hình retry policy/backoff. Thêm dependency theo BOM/version tương thích với Spring Boot của ứng dụng:

~~~groovy
dependencies {
    implementation("org.springframework.ldap:spring-ldap-core")
    implementation("org.springframework.retry:spring-retry")
}
~~~

Trong dự án Spring Boot đã dùng starter LDAP, dependency Spring LDAP core có thể đã được kéo vào transitively. Hãy quản lý version bằng dependency management phù hợp, không pin một version ngẫu nhiên.

### 7.1. Chỉ retry lỗi transport/service tạm thời

Ví dụ cấu hình:

~~~java
package org.example.directory.config;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.InsufficientResourcesException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class DirectoryRetryConfiguration {

    @Bean
    RetryTemplate ldapReadRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(200, 2.0, 2000, true)
                .retryOn(List.of(
                        CommunicationException.class,
                        ServiceUnavailableException.class,
                        InsufficientResourcesException.class))
                .build();
    }
}
~~~

Trong Spring Retry, **maxAttempts(3)** có nghĩa tối đa ba lần thực thi tổng cộng, tính cả lần đầu. Exponential backoff có randomization để phân tán thời gian retry. Policy chỉ liệt kê ba exception được chọn; các exception khác không tự động được retry.

Đây là template cho read operation hoặc operation đã có cơ chế reconcile. Không áp dụng nguyên bean này cho mọi write operation.

### 7.2. Bao một search read-only

~~~java
package org.example.directory.service;

import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;
    private final RetryTemplate ldapReadRetryTemplate;

    public DirectoryLookupService(
            LdapTemplate ldapTemplate,
            RetryTemplate ldapReadRetryTemplate) {
        this.ldapTemplate = ldapTemplate;
        this.ldapReadRetryTemplate = ldapReadRetryTemplate;
    }

    public List<PersonSummary> search(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .where("uid").is(uid);

        return ldapReadRetryTemplate.execute(context ->
                ldapTemplate.search(
                        ldapQuery,
                        (ContextMapper<PersonSummary>) raw -> {
                            DirContextOperations entry =
                                    (DirContextOperations) raw;
                            return new PersonSummary(
                                    entry.getStringAttribute("uid"),
                                    entry.getStringAttribute("cn"));
                        }));
    }

    public record PersonSummary(String uid, String commonName) {}
}
~~~

Query phải được xây với base/scope/filter đã validate. Retry callback chỉ thực hiện read; không tạo side effect trong callback như gửi email, phát event hoặc ghi database nếu các side effect đó không có idempotency riêng.

### 7.3. Không dùng retry mặc định cho mọi exception

Tránh cấu hình không có retry classifier:

~~~java
RetryTemplate.builder()
        .maxAttempts(5)
        .build();
~~~

Nếu policy mặc định retry mọi Exception, các lỗi invalid filter, invalid credentials, schema violation hoặc access denied có thể bị gửi lặp. Cấu hình allowlist rõ ràng giúp retry policy có thể review và kiểm thử.

### 7.4. Retry với cause chain

Một số lớp trung gian có thể wrap exception. Nếu policy cần xét exception lồng bên trong, Spring Retry builder có tùy chọn **traversingCauses()**. Chỉ bật khi đã xác định loại wrapper thực tế; không dùng predicate rộng kiểu mọi IOException hoặc RuntimeException nếu điều đó làm retry cả lỗi permanent.

## 8. Reconcile write sau timeout

Với write operation, tạo một flow riêng thay vì bọc thẳng modifyAttributes trong RetryTemplate.

### 8.1. Ví dụ đảm bảo một member tồn tại

Ví dụ dưới đây minh họa **groupOfNames** có attribute member chứa DN. Code dùng LdapTemplate để đọc trạng thái, sau đó thêm đúng một value:

~~~java
package org.example.directory.service;

import java.util.ArrayList;
import java.util.List;
import javax.naming.Name;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMembershipService {
    private final LdapTemplate ldapTemplate;
    private final RetryTemplate ldapReadRetryTemplate;

    public GroupMembershipService(
            LdapTemplate ldapTemplate,
            RetryTemplate ldapReadRetryTemplate) {
        this.ldapTemplate = ldapTemplate;
        this.ldapReadRetryTemplate = ldapReadRetryTemplate;
    }

    public void ensureMember(Name groupDn, Name userDn) {
        if (containsMember(groupDn, userDn)) {
            return;
        }

        try {
            ldapTemplate.modifyAttributes(
                    groupDn,
                    new ModificationItem[] {
                        new ModificationItem(
                            DirContext.ADD_ATTRIBUTE,
                            new BasicAttribute("member", userDn.toString()))
                    });
        } catch (CommunicationException | ServiceUnavailableException ex) {
            // Write có thể đã thành công dù response bị mất.
            if (containsMember(groupDn, userDn)) {
                return;
            }
            throw ex;
        } catch (org.springframework.ldap.AttributeInUseException ex) {
            // Duplicate value: xác minh trạng thái thực tế.
            if (containsMember(groupDn, userDn)) {
                return;
            }
            throw ex;
        }
    }

    private boolean containsMember(Name groupDn, Name userDn) {
        List<String> members = ldapReadRetryTemplate.execute(context ->
                ldapTemplate.lookup(
                        groupDn,
                        new String[] {"member"},
                        (AttributesMapper<List<String>>) attrs -> {
                            List<String> values = new ArrayList<>();
                            Attribute member = attrs.get("member");
                            if (member == null) {
                                throw new IllegalStateException(
                                        "Không thể xác minh member attribute của group");
                            }
                            NamingEnumeration<?> all = member.getAll();
                            try {
                                while (all.hasMore()) {
                                    values.add(String.valueOf(all.next()));
                                }
                            } finally {
                                all.close();
                            }
                            return values;
                        }));

        return members.stream().anyMatch(value -> sameDn(value, userDn));
    }

    private boolean sameDn(String value, Name expected) {
        try {
            return new LdapName(value)
                    .equals(new LdapName(expected.toString()));
        } catch (javax.naming.InvalidNameException ex) {
            return false;
        }
    }
}
~~~

Đây là ví dụ minh họa flow reconcile. Với schema khác, thay attribute và representation tương ứng (uniqueMember hoặc memberUid). Không dùng cùng code cho mọi server. Trong ứng dụng thực tế, xử lý rõ group không tồn tại, lỗi ACL khi đọc lại và kết quả xác minh không xác định.

Ví dụ chỉ thực hiện một lần ADD và read-back sau lỗi. Nếu read-back xác nhận member chưa có, method ném lại exception ban đầu; coordinator có thể quyết định thêm một attempt nếu lỗi retryable và deadline còn đủ. Không bọc toàn bộ method bằng retry policy rộng vì như vậy sẽ lặp cả bước ghi mà không kiểm soát trạng thái.

### 8.2. Đọc lại cần xác minh đúng trạng thái

Chỉ thấy group tồn tại là chưa đủ. Cần xác minh:

- Đúng group DN và đúng naming context.
- Đúng member DN/uid.
- Đúng attribute chứa membership.
- Không có duplicate hoặc giá trị sai encoding.
- Caller/service vẫn có quyền đọc để xác minh.

Service identity phải có quyền đọc attribute membership. Nếu attribute không xuất hiện trong response, không tự coi đó là danh sách rỗng: có thể do ACL, projection hoặc entry sai schema. Ví dụ trên fail closed khi không thấy member attribute. Nếu read-back timeout hoặc bị ACL từ chối, outcome vẫn là UNKNOWN. Đừng coi lỗi xác minh là bằng chứng write thất bại.

### 8.3. Xử lý Add entry

Khi Add entry timeout:

1. Lookup DN đích.
2. Nếu không tồn tại, retry Add khi budget còn và lỗi ban đầu là transient.
3. Nếu tồn tại, so sánh objectClass và các attribute thuộc operation.
4. Nếu entry khớp state mong muốn, trả success/already applied.
5. Nếu entry khác, trả conflict; không overwrite entry hiện có.

Không dùng rebind như cách retry Add nếu có nguy cơ ghi đè dữ liệu hoặc objectClass ngoài phạm vi request.

### 8.4. Xử lý Delete và Rename

**Delete:** sau timeout, lookup DN. Nếu entry không còn, có thể xem desired state đã đạt; nếu vẫn tồn tại, xác minh đúng target rồi mới retry. Nếu ACL không cho lookup, outcome unknown.

**Rename:** sau timeout, kiểm tra DN cũ và DN mới:

- Old DN tồn tại, new DN không tồn tại: operation có thể chưa chạy; cân nhắc retry.
- Old DN không tồn tại, new DN tồn tại và entry identity khớp: rename có thể đã thành công.
- Cả hai tồn tại hoặc cả hai không tồn tại: conflict/unknown; cần điều tra.

Không retry rename chỉ vì nhận CommunicationException; có thể tạo rename conflict hoặc thao tác nhầm entry.

### 8.5. Conditional update với LDAP Assertion Control

Nếu server hỗ trợ **LDAP Assertion Control (RFC 4528)**, có thể gắn điều kiện vào Modify/Delete để operation chỉ thành công khi entry vẫn ở trạng thái mong đợi. Ví dụ kiểm tra một attribute hoặc version marker trước khi thay đổi.

Assertion control giúp phát hiện concurrent update và giảm race giữa read với write. Nó không phải idempotency key và không tự giải quyết response bị mất sau commit. Khi retry, ứng dụng vẫn phải đọc lại trạng thái hoặc dùng operation record để xác định write trước đã áp dụng chưa.

Hỗ trợ control và quyền sử dụng phụ thuộc LDAP server; kiểm thử trên đúng provider/version trước khi dùng làm cơ chế bảo vệ chính.

## 9. Timeout, retry và giới hạn tài nguyên LDAP

Retry policy không thay thế timeout của từng LDAP operation. Nếu operation đầu tiên treo quá lâu, retry không thể bắt đầu cho đến khi attempt đó kết thúc hoặc bị hủy.

Thiết lập riêng:

- **Connection timeout:** thời gian chờ thiết lập TCP/TLS connection.
- **Read/response timeout:** thời gian chờ LDAP response nếu provider hỗ trợ.
- **Search time limit:** giới hạn server xử lý search.
- **Search count limit:** giới hạn số entry được trả về.
- **Pool wait timeout:** thời gian chờ lấy connection nếu dùng pool.
- **Application deadline:** thời gian tổng caller cho phép.

Giá trị cụ thể phụ thuộc ContextSource/provider và phiên bản JDK/Spring LDAP. Kiểm tra cấu hình thực tế và test timeout bằng môi trường test; đừng giả định timeLimit của search tự động giới hạn mọi LDAP operation.

### 9.1. Deadline phải được truyền xuyên các tầng

Một retry attempt không nên bắt đầu nếu thời gian còn lại của request không đủ cho connect + operation + xử lý kết quả. Khi caller hủy request, không tiếp tục retry ở background trừ khi operation đã được chuyển sang durable job với deadline riêng.

Nếu operation được thực hiện qua message consumer, deadline cần tính theo thời gian xử lý message và visibility/ack timeout. Nếu quá deadline, lưu outcome để reconcile thay vì giữ thread chờ vô hạn.

## 10. Circuit breaker và retry storm

Retry xử lý lỗi ngắn hạn; circuit breaker ngăn ứng dụng tiếp tục gọi một dependency đang lỗi kéo dài.

~~~mermaid
flowchart TD
    A["LDAP request"] --> B{"Circuit open?"}
    B -->|Yes| C["Fail fast / fallback"]
    B -->|No| D["Execute attempt"]
    D --> E{"Success?"}
    E -->|Yes| F["Return result"]
    E -->|No| G{"Retryable + budget left?"}
    G -->|Yes| H["Backoff + jitter"]
    H --> D
    G -->|No| I["Record failure"]
    I --> J{"Failure threshold reached?"}
    J -->|Yes| K["Open circuit"]
    J -->|No| L["Return classified error"]
~~~

Các nguyên tắc:

- Circuit breaker đặt quanh operation boundary phù hợp, không mở/đóng riêng cho từng exception lẻ tẻ.
- Retry chỉ chạy khi circuit đang cho phép request.
- Không để retry callback gọi một service khác cũng có retry độc lập mà không tính tổng attempts.
- Dùng bulkhead/concurrency limit để không tạo quá nhiều LDAP connection hoặc request đồng thời.
- Half-open probe nên nhẹ và có giới hạn.
- Không fallback bằng cách cấp quyền rộng hơn hoặc bỏ qua kiểm tra membership khi LDAP unavailable.

### 10.1. Chọn failure signal đúng

Không tính invalid credentials, invalid filter hoặc schema violation như bằng chứng LDAP server unavailable. Nếu mọi lỗi đều tăng failure rate, circuit breaker có thể mở dù directory vẫn khỏe. Chỉ xem các lỗi liên quan dependency availability/latency là tín hiệu phù hợp, theo policy đã kiểm thử.

## 11. Quan sát retry trong production

Mỗi logical operation nên có telemetry riêng:

| Field | Ví dụ | Mục đích |
| --- | --- | --- |
| operation | search, add-member, rename | Nhận biết loại operation |
| directoryAlias | people-primary | Phân biệt endpoint cấu hình |
| attempt | 1, 2, 3 | Biết retry count |
| outcome | success, failure, unknown | Kết quả cuối |
| errorCategory | communication, unavailable, schema | Phân loại lỗi |
| delayMs | 200, 400 | Đánh giá backoff |
| durationMs | 350 | Đo latency |
| correlationId | UUID opaque | Nối các log cùng operation |

Metrics nên dùng tag cardinality thấp như operation, directory alias, outcome và error category. Không dùng DN, uid, username, raw filter hoặc operationId làm metric tag.

Log retry phải cho biết **đây là attempt thứ mấy**, vì sao retry, delay bao nhiêu và tổng operation kết thúc ra sao. Không log bind password, token hoặc raw LDAP payload.

### 11.1. Những metric nên theo dõi

- ldap.operation.attempts: số attempt theo operation.
- ldap.operation.retries: số lần retry.
- ldap.operation.exhausted: số operation hết retry budget.
- ldap.operation.unknown: write có outcome chưa xác định.
- ldap.operation.duration: latency tổng và mỗi attempt.
- ldap.connection.failures: lỗi mở/kết nối lại connection.
- ldap.circuit.state: trạng thái circuit breaker.

Tên metric cụ thể phụ thuộc convention của Micrometer/registry; quan trọng là tách logical operation khỏi individual attempt.

## 12. Kiểm thử retry và lũy đẳng

Không chỉ test rằng RetryTemplate gọi callback ba lần. Phải kiểm tra **trạng thái LDAP cuối cùng** và side effect bên ngoài.

### 12.1. Test retry read khi server tạm unavailable

Mock hoặc fault-injection server:

1. Lần đầu ném ServiceUnavailableException.
2. Lần hai ném CommunicationException.
3. Lần ba trả kết quả.
4. Xác minh số attempt bằng 3 và kết quả đúng.
5. Xác minh backoff/deadline không vượt ngân sách test.

### 12.2. Test permanent failure không retry

Với InvalidSearchFilterException hoặc AuthenticationException:

- Callback chỉ chạy một lần.
- Không có delay/retry tiếp.
- Exception được map sang lỗi phù hợp.
- Không log secret hoặc raw filter.

### 12.3. Test write đã thành công nhưng response bị mất

Fault injection cần mô phỏng:

1. Server thực hiện Add/Modify.
2. Test proxy làm rơi response.
3. Client nhận CommunicationException/timeout.
4. Service thực hiện read-after-write.
5. Service nhận ra desired state đã tồn tại.
6. Không gửi thêm write gây duplicate.

### 12.4. Ma trận test

| Ca | Fault | Hành vi cần xác minh |
| --- | --- | --- |
| Search transient | ServiceUnavailable trước khi trả kết quả | Retry trong budget, trả kết quả |
| Search permanent | InvalidSearchFilter | Một attempt, trả lỗi |
| Bind invalid password | AuthenticationException | Không retry |
| Add timeout sau commit | Response bị drop sau Add | Lookup DN, không ghi duplicate |
| Modify ADD timeout sau commit | Response bị drop sau Modify | Read member, xác nhận đã có |
| Modify ADD duplicate | Value đã tồn tại | Reconcile và trả trạng thái phù hợp |
| Modify REMOVE timeout sau commit | Response bị drop | Read member, xác nhận đã vắng |
| Delete timeout sau commit | Response bị drop | Lookup DN, desired state absent |
| Rename timeout sau commit | Response bị drop | Kiểm tra old/new DN và identity |
| ACL denied | Insufficient access | Không retry |
| Schema violation | Attribute không hợp lệ | Không retry |
| Retry exhausted | Server unavailable mọi attempt | Trả lỗi cuối, metric exhausted tăng |
| Deadline exhausted | Tổng thời gian vượt request budget | Dừng retry |
| Concurrent add | Hai request cùng thêm member | Không mất member; duplicate được reconcile |
| Nested retry | Gateway và service cùng retry | Attempts bị giới hạn theo policy |
| Circuit open | LDAP liên tục unavailable | Fail fast, không tạo retry storm |

### 12.5. Test không dùng sleep thật

Khi unit test backoff, dùng clock/sleeper có thể kiểm soát hoặc mock policy để tránh test kéo dài và không ổn định. Integration test mới cần kiểm chứng timeout/network thực tế; không cố chứng minh retry behavior bằng cách chờ các khoảng sleep dài trong mọi test.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| LDAP quá tải khi server down | Retry không backoff hoặc retry mọi exception | Allowlist exception, exponential backoff, jitter, circuit breaker |
| Invalid credentials bị gửi lặp | AuthenticationException bị coi là transient | Không retry credential failure; kiểm tra secret và lockout policy |
| Add retry báo already exists | Lần đầu đã commit nhưng response mất | Lookup DN, so sánh state và reconcile |
| Modify retry báo duplicate value | ADD đã thành công ở attempt trước | Đọc lại attribute trước khi gửi write |
| Delete retry báo no such object | Delete trước đã thành công | Xác minh DN vắng và trả success theo desired-state contract |
| Rename retry thất bại | DN đã được chuyển ở attempt trước | Kiểm tra old/new DN trước khi retry |
| Retry vẫn timeout | Timeout mỗi attempt quá dài hoặc server quá tải | Giới hạn operation timeout và tổng deadline |
| Nhiều tầng retry nhân số lần gọi | Retry lồng nhau ở gateway/service/consumer | Chọn một retry owner và tính tổng attempts |
| Circuit breaker luôn open | Threshold thấp hoặc probe không phù hợp | Điều chỉnh theo traffic, failure rate và recovery window |
| Retry che lỗi schema | Retry policy bắt mọi RuntimeException | Dùng exception allowlist |
| Search trả kết quả không đầy đủ | PartialResult/referral bị bỏ qua hoặc size limit | Xử lý referral/paging rõ ràng; không coi partial là full success |

## 14. Checklist thiết kế retry cho LDAP

- [ ] Phân loại lỗi transient, permanent và ambiguous.
- [ ] Dùng Spring LDAP exception type/cause thay vì so sánh message.
- [ ] Không retry invalid credentials, invalid filter, invalid DN, ACL hoặc schema violation.
- [ ] Chỉ retry operation read-only trực tiếp khi lỗi transient.
- [ ] Write timeout phải có read-after-write/reconciliation.
- [ ] Định nghĩa idempotency cho Add/Modify/Delete/Rename.
- [ ] Giới hạn max attempts và exponential backoff.
- [ ] Bật jitter để phân tán retry.
- [ ] Tổng retry nằm trong application deadline.
- [ ] Tính retry budget giữa gateway, service, job và message consumer.
- [ ] Có circuit breaker/bulkhead nếu tải và availability yêu cầu.
- [ ] Không fallback bằng cách bỏ qua authorization.
- [ ] Log attempt/error category/outcome an toàn.
- [ ] Có integration test mô phỏng response mất sau commit.
- [ ] Theo dõi unknown outcome và có reconciliation workflow.

## 15. Bài tập tự luyện

1. Phân loại CommunicationException, ServiceUnavailableException, AuthenticationException và SchemaViolationException thành transient/permanent/ambiguous theo từng operation.
2. Vì sao Search thường có thể retry trực tiếp nhưng Add entry thì không?
3. Mô tả tình huống server đã Modify thành công nhưng client nhận timeout.
4. Viết RetryTemplate chỉ retry CommunicationException và ServiceUnavailableException, tối đa ba attempts, có exponential backoff và jitter.
5. Thiết kế ensureMember cho groupOfNames; xử lý duplicate add và timeout sau commit.
6. Làm thế nào phân biệt Delete chưa chạy với Delete đã chạy nhưng response bị mất?
7. Vì sao không nên retry bind user với password sai?
8. Tính tổng attempts khi gateway retry 3 lần và service retry 4 lần. Đề xuất một retry owner.
9. Thiết kế deadline khi connect timeout 300 ms, operation timeout 500 ms và tối đa ba attempts.
10. Viết fault-injection test làm rơi response sau khi LDAP server đã commit Modify.
11. Vì sao read-after-write có thể vẫn không xác minh được nếu ACL không cho đọc?
12. Thiết kế metrics/log cho retry mà không ghi raw DN, username hoặc filter.

## 16. Tổng kết

Retry đúng bắt đầu bằng việc **phân loại lỗi và xác định trạng thái operation**, không phải bọc mọi lời gọi LDAP trong một vòng lặp. Lỗi transport/service tạm thời có thể retry nếu operation an toàn và còn retry budget. Lỗi credential, filter, DN, ACL hoặc schema thường cần sửa nguyên nhân và không nên retry.

Search/lookup thường có thể retry trực tiếp. Add, Modify, Delete và Rename có thể đã được server commit dù client nhận timeout; hãy coi đó là **ambiguous outcome**, đọc lại trạng thái và reconcile trước khi gửi write lần nữa. Tính lũy đẳng phải được thiết kế ở application layer bằng desired-state operation, operation ID, conflict handling và workflow phục hồi.

Sử dụng allowlist exception với Spring Retry, exponential backoff, jitter, timeout và deadline. Kết hợp circuit breaker khi cần bảo vệ hệ thống khỏi retry storm. Cuối cùng, kiểm thử không chỉ số lần gọi mà cả trạng thái directory sau lỗi và response bị mất.

### Tài liệu tham khảo

- [Spring LDAP — Exception API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/package-summary.html) — exception hierarchy và các loại NamingException.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html) — LDAP operations, exception handling và search behavior.
- [Spring Retry — RetryTemplate API](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/support/RetryTemplate.html) — programmatic retry.
- [Spring Retry — RetryTemplateBuilder API](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/support/RetryTemplateBuilder.html) — maxAttempts, retryOn, exponentialBackoff, jitter và cause traversal.
- [Spring Framework — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html) — RetryTemplate và retry policy trong Spring Framework.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — Add, Modify, Delete, Modify DN và LDAP result codes.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528) — assertion control để thực hiện update có điều kiện khi server hỗ trợ.
