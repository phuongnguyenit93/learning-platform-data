# Không tối ưu bằng cách bỏ kiểm tra bảo mật hoặc correctness

Một thao tác **Spring LDAP** có thể chạy nhanh hơn sau khi tắt xác minh chứng chỉ TLS, bỏ qua lỗi search, dùng tài khoản LDAP có quyền cao để tránh kiểm tra ACL, cache kết quả membership vô thời hạn hoặc thay `ADD_ATTRIBUTE` bằng `REPLACE_ATTRIBUTE`. Nhưng đó không phải là tối ưu hiệu năng hợp lệ: hệ thống đã thay đổi **hợp đồng bảo mật hoặc tính đúng đắn (correctness)** để đổi lấy con số latency thấp hơn. Những thay đổi ấy có thể làm rò credential, trả kết quả thiếu, cấp quyền sai hoặc ghi đè dữ liệu.

Bài thuộc chương **Hiệu năng** của module **SPRING_LDAP**. Ta xem cách tối ưu DN, filter, tìm kiếm, thao tác entry qua `LdapTemplate`, `LdapClient` hoặc ODM, cấu hình `ContextSource`, TLS, xác thực, pooling và xử lý lỗi **mà vẫn giữ được các bất biến bảo mật và dữ liệu**. Mục tiêu là giảm chi phí thực sự, không tạo một “benchmark nhanh” bằng cách bỏ công việc bắt buộc.

## 1. Mục tiêu học tập

Sau bài này, người học cần:

1. Xác định **security invariants** và **correctness invariants** trước khi đo tốc độ một truy vấn LDAP.
2. Nhận diện những “tối ưu giả”: tắt TLS/hostname verification, bỏ authorization, nuốt `PartialResultException`, che `SizeLimitExceededException`, cache sai phạm vi, retry thao tác ghi mù quáng.
3. Dùng base DN, search scope, filter được escape, thuộc tính trả về và index để cải thiện truy vấn mà không thay đổi tập kết quả cần tìm.
4. Tối ưu pooling và connection reuse có kiểm soát, đặc biệt phân biệt tài khoản dịch vụ với bind xác thực người dùng và với StartTLS.
5. Thiết kế giới hạn thời gian, paging, retry, cache và failover giữ nguyên ý nghĩa nghiệp vụ khi LDAP chậm hoặc không khả dụng.
6. Đo **latency, throughput, error rate và correctness/security** trên cùng bộ tình huống; kiểm thử hồi quy trước khi chấp nhận một thay đổi.

## 2. Hiệu năng chỉ có ý nghĩa khi kết quả còn đúng

Tối ưu có thể làm giảm số lần round-trip, CPU, lượng dữ liệu truyền, thời gian mở context, độ trễ tìm kiếm hoặc tải LDAP server. Nhưng một kết quả nhanh chỉ có giá trị khi:

- Client thực sự giao tiếp với **LDAP server dự kiến**, bằng kết nối được bảo vệ và xác minh.
- Xác thực và kiểm tra quyền vẫn được thực hiện đúng chính sách.
- DN, search base, search scope và filter vẫn tìm **đúng phạm vi đối tượng**.
- Kết quả rỗng chỉ có nghĩa “không có entry phù hợp” khi search đã hoàn tất trong phạm vi được cam kết.
- Giá trị attribute, group membership và schema vẫn được giữ đúng; không ghi đè cập nhật đồng thời.
- Thất bại mạng/LDAP không bị chuyển thành `false`, `Optional.empty()`, `[]` hoặc “thành công” để tăng tỷ lệ success giả.
- Dữ liệu trong cache được dùng đúng danh tính, tenant, quyền, phiên bản và độ mới cho phép.

### 2.1. Ba loại chi phí cần phân biệt

```text
Thời gian một request nghiệp vụ
          │
          ├── Kết nối: DNS + TCP + TLS + bind / lấy context từ pool
          ├── Truy vấn: server xử lý filter/scope/index + truyền entry
          ├── Xử lý: mapping, validation, authorization, biến đổi dữ liệu
          └── Điều phối: queue, retry, paging, cache miss, failover
```

Giảm thời gian ở một phần nhưng làm tăng lỗi ở phần khác chưa chắc cải thiện hệ thống. Ví dụ: mở rộng pool quá lớn có thể giảm thời gian chờ ở client nhưng làm LDAP server quá tải; query lấy ít attribute hơn có thể nhanh, nhưng nếu bỏ attribute cần cho authorization thì kết quả sai.

### 2.2. Tập bất biến dùng để đánh giá thay đổi

| Lĩnh vực | Bất biến cần giữ | Điều **không** được coi là tối ưu |
| --- | --- | --- |
| TLS | Xác minh chain, hostname, chính sách TLS và đích kết nối | `TrustManager` tin mọi chứng chỉ; bỏ hostname verification |
| Authentication | Xác thực đúng danh tính, credential không bị dùng sai context | Bỏ kiểm tra password vì đã có cache cũ |
| Authorization | Caller chỉ xem/sửa các entry được cấp quyền | Dùng service account admin rồi bỏ kiểm tra quyền ở service |
| Search correctness | Base, scope và filter phản ánh đúng yêu cầu nghiệp vụ | Thu hẹp scope tùy tiện để trả nhanh nhưng mất người dùng |
| Completeness | Không gọi kết quả partial/limited là toàn bộ dữ liệu | Nuốt `PartialResultException` hay `SizeLimitExceededException` mà không công bố giới hạn |
| Data integrity | Modify không làm mất các giá trị khác, tạo/xóa có chính sách xung đột | `REPLACE_ATTRIBUTE` toàn bộ membership chỉ để tránh lỗi trùng |
| Availability | Lỗi thật được báo; retry có giới hạn và deadline | Trả `200 + []` khi thư mục mất kết nối |
| Isolation | Context/cache không làm lẫn tenant hoặc người dùng | Pool một context xác thực rồi tái sử dụng cho danh tính khác |

**Nguyên tắc quyết định:** nếu cách tối ưu mới làm yếu đi một bất biến, nó cần thay đổi rõ ràng về yêu cầu nghiệp vụ và đánh giá rủi ro, **không được lén đưa vào như một cải tiến performance**.

## 3. Những tối ưu giả cần nhận diện ngay

| Cách “tăng tốc” sai | Vì sao nhanh hơn | Rủi ro | Thay thế đúng |
| --- | --- | --- | --- |
| Tắt certificate hoặc hostname verification cho LDAPS/StartTLS | Tránh bước kiểm tra TLS bị lỗi | Dễ bị kết nối nhầm đích/MITM, lộ credential | Sửa CA/truststore, certificate SAN, hostname và TLS configuration |
| Tắt TLS, dùng simple bind trên plaintext | Bỏ chi phí mã hóa/handshake | Lộ username/password và dữ liệu LDAP | Dùng LDAPS/StartTLS đúng, tái sử dụng kết nối an toàn khi phù hợp |
| Dùng tài khoản LDAP admin cho mọi truy vấn | Ít gặp lỗi ACL | Quyền quá rộng; ứng dụng có thể đọc/ghi ngoài phạm vi | Least privilege, tách quyền search/update, kiểm tra quyền caller |
| Bỏ kiểm tra mật khẩu hoặc lưu “đăng nhập hợp lệ” mãi | Giảm LDAP bind | Tài khoản đã khóa/đổi password vẫn được chấp nhận | Session có hạn, kiểm tra lại theo chính sách và sự kiện thu hồi |
| Bắt `NamingException` rồi trả danh sách rỗng | Response nhanh và ít lỗi hiển thị | Outage/referral bị hiểu là “không có dữ liệu” | Phân loại exception và biểu diễn trạng thái không đầy đủ |
| Bật `ignorePartialResultException(true)` cho mọi query | Không phải xử lý lỗi referral | Tập người dùng/group có thể bị thiếu | Scope rõ, referral policy an toàn, coverage riêng |
| Bỏ qua size/time limit | Ít request bị báo lỗi | Hiểu nhầm danh sách bị cắt là đầy đủ | Paging, index/filter, khai báo limit và trạng thái kết quả |
| Cache membership/ACL không hết hạn | Không cần query LDAP | Thu hồi quyền chậm, dùng dữ liệu sai user/tenant | Cache ngắn hạn có key/invalidation/nhạy cảm theo nghiệp vụ |
| Retry vô hạn khi LDAP chậm | Một số request có thể thành công | Retry storm, trễ cao, nguy cơ ghi lặp | Backoff, jitter, số lần thử hữu hạn, deadline và circuit breaker |
| Ghép filter/DN từ chuỗi để “đỡ overhead” | Bỏ thao tác escaping | LDAP injection hoặc tìm sai DN | Dùng `LdapQueryBuilder`, `LdapNameBuilder` |

Những sai lầm này thường xuất hiện trong áp lực giảm p95 latency. Cần kiểm chứng **tính đúng của output** cùng lúc với tốc độ; nếu không, hệ thống đã thay đổi sản phẩm chứ không chỉ tối ưu triển khai.

## 4. Đo baseline trước khi thay đổi

Trước khi chỉnh pool size hoặc caching, xác định chính xác request nào chậm. Một mẫu đo có ích:

| Nhóm đo | Metric gợi ý | Vai trò |
| --- | --- | --- |
| Latency | p50/p95/p99 theo `lookup`, `search`, `authenticate`, `modify` | Xác định thao tác/tail latency gây vấn đề |
| Throughput | request/giây, LDAP operations/giây | So sánh với tải thật |
| Kết nối | thời gian lấy context, TCP/TLS handshake, pool wait, connection reuse | Xem overhead của pooling |
| Tìm kiếm | số entry trả về, số attribute, kích thước payload, search base/scope, số trang | Xác định query lãng phí |
| Lỗi | `CommunicationException`, `PartialResultException`, `TimeLimitExceededException`, `SizeLimitExceededException` và lỗi ACL | Không che giá trị đo bằng success giả |
| Retry | số attempt, deadline exceeded, số request nhân lên | Phát hiện retry storm |
| Cache | hit/miss, tuổi dữ liệu, invalidation lag, tỷ lệ kết quả sai | Chứng minh cache vẫn đúng |
| Correctness | tập entry mong đợi, membership, tính đầy đủ, số trường bắt buộc | Ngăn thay đổi nhanh nhưng sai |
| Security | từ chối TLS sai, ACL, tenant isolation, không lộ secret trong log | Chống hồi quy bảo mật |

### 4.1. Đo theo tình huống, không chỉ trung bình

Mỗi bài benchmark nên có cả:

- Người dùng/entry **có thật** và **không tồn tại**.
- Query một entry, tìm kiếm trong OU nhỏ, và truy vấn danh sách có nhiều entry.
- Cache hit, cache miss, sau invalidation và lúc người dùng vừa mất quyền.
- Ổn định mạng, LDAP chậm, node lỗi, referral sang domain khác.
- Cùng số lượng client/connection và cùng dữ liệu trước/sau khi tối ưu.

Ví dụ tiêu chí có thể là: “p95 của tìm người dùng giảm trong cùng tập dữ liệu, còn mọi test quyền, TLS, DN và completeness tiếp tục PASS”. Không có một con số p95 mặc định phù hợp cho mọi LDAP server; ngưỡng phải lấy từ SLO, điều kiện mạng và tải thực tế.

### 4.2. Không đưa dữ liệu bí mật vào telemetry

Log nên có `operation`, `directoryAlias`, `searchScope`, số lượng entry, thời gian, loại exception và correlation ID. Tránh ghi password, bind secret, token, full DN hoặc filter chứa dữ liệu cá nhân. Nếu cần định danh request để so sánh, dùng ID nội bộ hoặc khóa đã được xử lý theo chính sách dữ liệu.

## 5. Tối ưu truy vấn đúng: base, scope, filter, attribute và index

Một truy vấn LDAP nhanh thường nhờ **trả ít dữ liệu cần thiết từ một phạm vi đúng**, không phải nhờ bỏ validation.

### 5.1. Chọn search base theo nghiệp vụ

Giả sử `ContextSource` đã có base `dc=example,dc=org`. Nếu người dùng nằm trực tiếp dưới `ou=people`, truy vấn `uid` trong OU này thường rẻ hơn tìm toàn bộ `dc=example,dc=org`.

```text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
├── ou=contractors
│   └── uid=lan
└── ou=groups
    └── cn=engineering
```

Tuy nhiên, nếu nghiệp vụ yêu cầu cả **people lẫn contractors**, thu hẹp base chỉ còn `ou=people` sẽ bỏ sót `uid=lan`. Hiệu năng tốt hơn trong trường hợp đó là **thiết kế hai truy vấn có phạm vi rõ ràng hoặc xây kiến trúc truy vấn đúng nhiều OU**, không biến output thiếu thành output “nhanh”.

### 5.2. Chọn search scope tối thiểu **nhưng đủ**

| Scope | Ý nghĩa | Lựa chọn khi |
| --- | --- | --- |
| `OBJECT` | Chỉ entry tại base | Cần đọc một đối tượng xác định |
| `ONELEVEL` | Các entry con trực tiếp của base | Người dùng nằm trực tiếp trong OU, không ở OU con |
| `SUBTREE` | Base và toàn bộ entry con | Cần tìm xuyên nhiều cấp OU |

Nếu cấu trúc dữ liệu cho phép, `ONELEVEL` có thể tiết kiệm công việc hơn `SUBTREE`. Nhưng nó không phải thay thế an toàn cho một yêu cầu tìm xuyên OU lồng nhau. Hãy đặt test có entry ở cấp con sâu hơn để phát hiện scope quá hẹp.

### 5.3. Dùng bộ dựng filter và chỉ lấy attribute cần thiết

Ví dụ trả một kết quả tối giản cho giao diện tra cứu, không tải các nhóm, ảnh hoặc attribute không dùng đến:

```java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PeopleDirectorySearch {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectorySearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record PersonSummary(String uid, String cn) {}

    public List<PersonSummary> findDirectPeople(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery ldapQuery = query()
                .base("ou=people") // relative với ContextSource base
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid", "cn")
                .timeLimit(1500)
                .where("uid").is(uid); // escape giá trị filter

        return ldapTemplate.search(ldapQuery,
                (AttributesMapper<PersonSummary>) attrs -> {
                    Attribute uidAttr = attrs.get("uid");
                    Attribute cnAttr = attrs.get("cn");
                    if (uidAttr == null || cnAttr == null) {
                        throw new IllegalStateException(
                                "Entry không đáp ứng hợp đồng attribute");
                    }
                    return new PersonSummary(
                            uidAttr.get().toString(),
                            cnAttr.get().toString());
                });
    }
}
```

Đây là ví dụ cho schema/OU nơi `uid` và `cn` có mặt, tài khoản search có quyền đọc hai thuộc tính và user là **con trực tiếp** của `ou=people`. Nếu dữ liệu thực tế nằm trong OU con, phải đổi sang `SUBTREE` hoặc mô hình search khác. Tăng tốc không được đổi định nghĩa “người dùng hợp lệ” của hệ thống.

**Các lợi ích đúng đắn:**

- `query().where("uid").is(uid)` escape giá trị theo cú pháp filter; không phải tự ghép `"(uid=" + uid + ")"`.
- `.attributes("uid", "cn")` giảm dữ liệu truyền so với nhận tất cả attributes, **nếu** hai trường đủ cho use case này.
- `ONELEVEL` giới hạn công việc, nhưng chỉ an toàn vì hợp đồng nói dữ liệu nằm một cấp.
- `timeLimit(1500)` đặt thời hạn Search; nếu query vượt giới hạn và không đủ kết quả, code phải báo lỗi theo chính sách, không biến thành danh sách đầy đủ.

Không truy vấn ít attribute hơn nếu bước tiếp theo cần thông tin để **kiểm tra quyền**, audit hoặc xác nhận trạng thái tài khoản. Nếu use case cần `memberOf` hoặc thuộc tính trạng thái account, phải đưa chúng vào query hoặc một bước truy vấn tương đương và kiểm thử toàn bộ kết quả.

### 5.4. Tránh injection cả ở filter và DN

Hai đoạn dưới không an toàn:

```java
String filter = "(uid=" + inputUid + ")";
String relativeDn = "uid=" + inputUid + ",ou=people";
```

Giá trị đầu vào có thể chứa ký tự đặc biệt; filter escaping và DN escaping là **hai cú pháp khác nhau**. Nên dùng:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", inputUid)
        .build();

var filterQuery = query().base("ou=people")
        .where("uid").is(inputUid);
```

Việc bỏ escaping để giảm vài thao tác xử lý chuỗi có thể tạo LDAP injection hoặc truy cập nhầm DN; hiệu năng không phải lý do hợp lệ. Cũng cần kiểm tra **chính tên attribute, base DN và scope** do người dùng cung cấp; encoder dành cho **giá trị** không tự biến mọi cấu hình truy vấn thành hợp lệ.

### 5.5. Chỉ mục (index) mới là nơi tối ưu query nặng

Nếu search thường xuyên theo `uid`, `mail` hoặc một attribute định danh, hãy kiểm tra index và query plan/metric của **LDAP server đang dùng**. Thiết kế index phụ thuộc schema, matching rule, tần suất ghi và vendor; thêm quá nhiều index cũng làm tăng chi phí cập nhật.

Một quá trình tối ưu có cơ sở:

1. Đo những filter và scope chậm bằng công cụ giám sát server an toàn.
2. Xem attribute nào được dùng trong equality, substring hoặc ordering filter.
3. Tham khảo cơ chế index và giới hạn của đúng LDAP server.
4. Thử thay đổi trên dữ liệu và tải tương tự production; so sánh p95/p99 cùng tải ghi.
5. Kiểm tra rằng kết quả **không đổi**; index có tác dụng tăng tốc, không thay đổi quy tắc chọn entry.

Đừng thay một filter chính xác bằng filter lỏng hơn “để server dùng index” rồi loại bớt dữ liệu ở client nếu điều đó làm rò dữ liệu ngoài phạm vi hoặc tăng băng thông không cần thiết.

## 6. TLS: tối ưu kết nối, không bỏ xác minh

### 6.1. Tối ưu giả: bỏ kiểm tra certificate

Nếu LDAPS chậm hoặc báo `SSLHandshakeException`, một “cách sửa” nguy hiểm là dùng `TrustManager` tin mọi certificate hoặc tắt hostname verification. Nó không tăng hiệu năng hợp lệ; nó cho phép ứng dụng tin một đầu cuối không được xác thực, thậm chí khi đang truyền credential.

**Giữ nguyên những yêu cầu sau:**

- Chỉ tin CA/certificate được tổ chức chấp thuận.
- Kiểm tra hostname/SAN theo chính sách TLS và provider.
- Từ chối certificate hết hạn/không hợp lệ; tránh hạ cấp bảo mật nếu handshake thất bại.
- Truyền simple-bind credential chỉ qua kết nối được bảo vệ khi chính sách yêu cầu TLS.
- Không gửi credential tới referral endpoint chưa được phê duyệt.

Nếu handshake chiếm tỷ trọng lớn trong latency, hãy đo tỷ lệ **mở kết nối mới** và dùng cơ chế reuse/pooling tương thích với TLS và danh tính. Không bỏ bước xác minh.

### 6.2. Ví dụ `LdapContextSource` với timeout và strict error policy

```java
import java.util.Map;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

public final class SafeLdapConfiguration {
    private SafeLdapConfiguration() {}

    public static LdapTemplate create(
            String ldapsUrl,
            String baseDn,
            String serviceDn,
            String servicePassword) throws Exception {

        if (ldapsUrl == null || !ldapsUrl.startsWith("ldaps://")) {
            throw new IllegalArgumentException(
                    "Ví dụ này yêu cầu LDAPS endpoint được tin cậy");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl(ldapsUrl);
        source.setBase(baseDn);
        source.setUserDn(serviceDn);
        source.setPassword(servicePassword);
        source.setReferral("ignore");

        // Không bật JNDI native pooling chỉ để làm nhanh.
        // Cần đánh giá pool, TLS và loại context riêng.
        source.setPooled(false);

        // Thuộc tính của JNDI LDAP provider phổ biến (Oracle/OpenJDK).
        source.setBaseEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "2500",
                "com.sun.jndi.ldap.read.timeout", "4500"
        ));

        // Khi tự tạo ngoài Spring IoC, phải khởi tạo context source.
        source.afterPropertiesSet();

        LdapTemplate template = new LdapTemplate(source);
        template.setIgnoreNameNotFoundException(false);
        template.setIgnorePartialResultException(false);
        template.setIgnoreSizeLimitExceededException(false);
        return template;
    }
}
```

**Giới hạn của ví dụ:** chỉ kiểm tra tiền tố `ldaps://` không chứng minh endpoint tin cậy hoặc certificate hợp lệ; người triển khai **phải cấu hình truststore/SSL context tin cậy, hostname verification và chính sách TLS** ở JVM/provider. Một URL `ldaps://` không thay thế các kiểm tra đó. Không log `servicePassword`, không commit bí mật vào source, và không dùng nguyên các timeout minh họa cho mọi môi trường.

Đặc biệt, `setIgnoreSizeLimitExceededException(false)` thay đổi hành vi mặc định của `LdapTemplate` (mặc định thường là bỏ qua size limit). Đặt false ở đây nhằm minh họa một **hợp đồng cần kết quả đầy đủ**. Với use case cố tình lấy **top N** hoặc danh sách có giới hạn, có thể chọn chính sách khác nhưng API phải khai báo limit/coverage rõ ràng.

### 6.3. Pooling cần giữ nguyên danh tính và bảo mật kênh

Pooling có thể tiết kiệm mở TCP/TLS và bind lặp lại, nhưng cũng gây:

- **Stale connection**: socket bị server hoặc load balancer đóng khi idle, request sau gặp reset/timeout.
- **Pool exhaustion**: request đợi connection quá lâu, timeout tổng vượt SLA.
- **Identity confusion**: context tạo dưới một danh tính bị tái sử dụng cho người khác.
- **TLS/StartTLS state**: trạng thái bảo mật kênh thay đổi sau khi tạo context có thể không được native JNDI pool quản lý đúng.

Spring LDAP cung cấp `PoolingContextSource`/hỗ trợ pooling theo phiên bản, có cơ chế validation connection. Tài liệu Spring LDAP và JNDI cảnh báo **không dùng native JNDI pooling với những context sẽ thực hiện StartTLS hoặc thay đổi thuộc tính xác thực sau khi kết nối đã tạo**. `AbstractContextSource.setPooled(true)` bật cơ chế JNDI native pooling, không phải lựa chọn mặc định an toàn cho mọi cấu hình TLS.

Một chính sách pooling đúng:

1. Tách **context của tài khoản dịch vụ cố định** khỏi **context bind xác thực người dùng**.
2. Dùng pool có validation/invalidation connection khi được thư viện hỗ trợ; kiểm tra idle timeout thực tế của server/LB.
3. Đặt giới hạn active/idle, thời gian chờ lấy connection và deadline tổng; đo tỷ lệ borrow timeout.
4. Không giữ/trả context xác thực theo người dùng vào pool dùng chung không kiểm soát.
5. Chỉ bật reuse cho loại TLS/StartTLS và identity mà tài liệu provider xác nhận hỗ trợ; kiểm thử bảo mật và rotation secret.

**Điểm đặc biệt quan trọng:** `PoolingContextSource` giả định những read-only/read-write context mà nó pool có môi trường xác thực tương ứng ổn định. Khi bọc `ContextSource` dùng `AuthenticationSource` thay đổi theo thread/user, pool có nguy cơ giữ credential của người gọi đầu tiên cho những lần dùng sau; đây là lỗi phân quyền nghiêm trọng, không phải lỗi hiệu năng nhỏ.

## 7. Không bỏ kiểm tra xác thực và phân quyền để tăng throughput

### 7.1. Authentication bind khác LDAP Add

“Bind” có hai nghĩa:

- LDAP **BindRequest** xác thực principal với credential.
- `LdapTemplate.bind(...)` tạo entry bằng LDAP **AddRequest**.

Không nên cắt bước xác thực hoặc tái sử dụng context đã xác thực của người dùng khác chỉ vì muốn giảm số lần bind. Khi login, cần từ chối password rỗng trước simple bind; một số server có thể cho phép anonymous/unauthenticated bind nếu caller không kiểm soát input.

### 7.2. Quyền của service account không thay thế quyền của caller

Giả sử service account có quyền sửa `member` của nhóm LDAP. Điều đó không có nghĩa **mọi HTTP caller** có quyền thêm mình vào nhóm quản trị. Nếu bỏ authorization tại ứng dụng để giảm latency, hệ thống sẽ cho phép thao tác ngoài ý định dù LDAP Add/Modify thành công.

```text
HTTP caller
     │
     ▼
Authentication của ứng dụng
     │
     ▼
Authorization: caller có quyền thao tác với group này không?
     │
     ▼
Service account thực hiện LDAP Modify đúng phạm vi ACL
     │
     ▼
Kiểm chứng kết quả / audit
```

**Tối ưu đúng** có thể là: precompute thông tin quyền ít thay đổi theo chính sách, cache kiểm soát và index lookup; **không** xóa bước kiểm tra quyền hay dùng account admin để “khỏi gặp `NoPermissionException`”.

### 7.3. Cache phiên đăng nhập không phải cache mật khẩu

Ứng dụng có thể duy trì session hoặc token đã được xác thực theo chính sách thay vì bind lại LDAP với mọi HTTP request. Nhưng cần xác định:

- Thời hạn session, idle timeout và điều kiện thu hồi.
- Ảnh hưởng khi tài khoản bị khóa, vô hiệu hóa hoặc đổi password.
- Phương pháp kiểm tra lại group membership hay quyền động.
- Chính sách bảo vệ token, quản lý thiết bị và phân quyền có tính thời điểm.

Không cache `password -> true` vô hạn hoặc lưu password plaintext để giảm tải LDAP. Đặc biệt, không dùng cùng kết quả cache đăng nhập của người A cho người B chỉ vì khóa cache thiếu danh tính.

## 8. Không nuốt exception để trả dữ liệu nhanh hơn

### 8.1. Ba trạng thái phải phân biệt

```text
Search LDAP
  ├── Thành công, không có entry phù hợp → [] (trong scope đã tìm)
  ├── Thành công, có đầy đủ entry      → dữ liệu hợp lệ
  └── Không thể hoàn tất hoặc kết quả không chắc đủ
       ├── PartialResultException   (referral)
       ├── SizeLimitExceededException / TimeLimitExceededException
       ├── CommunicationException / ServiceUnavailableException
       └── NameNotFoundException do search base sai
```

Nếu code:

```java
try {
    return ldapTemplate.search(query, mapper);
} catch (RuntimeException ignored) {
    return java.util.List.of(); // SAI: outage trở thành "không có dữ liệu".
}
```

thì p95 có thể trông tốt hơn, nhưng **error rate đã bị ngụy trang**. Một tiến trình đồng bộ có thể cho rằng tất cả người dùng đã bị xóa và thực hiện cleanup nguy hiểm.

### 8.2. Hiểu ba cờ “ignore” của `LdapTemplate`

Theo Javadoc Spring LDAP:

| Cờ | Mặc định | Điều cần cân nhắc |
| --- | --- | --- |
| `setIgnoreNameNotFoundException` | `false` | Nếu bật có thể che search base/OU không tồn tại |
| `setIgnorePartialResultException` | `false` | Nếu bật có thể trả dữ liệu trong khi chưa theo hết referral |
| `setIgnoreSizeLimitExceededException` | `true` | Phù hợp một số query cố ý đặt count limit; không phù hợp khi ngầm hứa kết quả toàn bộ |

**Không kết luận** bật `ignorePartialResultException(true)` sẽ theo referral thành công. Nó chỉ làm search có thể trả về khi `PartialResultException` bị bỏ qua; caller có thể không biết dữ liệu ở naming context khác đã bị thiếu.

Khi một endpoint **cố ý** trả “danh sách tối đa 50 entry”, giới hạn là một phần hợp đồng. Khi endpoint hứa “toàn bộ thành viên của nhóm”, **cùng một giới hạn** là mất correctness nếu không công bố incomplete/paging state.

### 8.3. Phân biệt exception LDAP và Spring DAO

Các exception như `org.springframework.ldap.PartialResultException`, `CommunicationException` và `NameNotFoundException` thuộc hệ `org.springframework.ldap.NamingException`, **không tự động thuộc** `org.springframework.dao.DataAccessException`.

Đừng bắt `DataAccessException` rồi giả định mọi lỗi LDAP đã được xử lý. Nếu adapter tự ánh xạ exception sang hợp đồng DAO, phải làm rõ và giữ nguyên `cause`. Unit test cần chứng minh lỗi mạng không bị đổi thành “không có entry” hoặc “sai mật khẩu”.

## 9. Paging, count limit và tính đầy đủ

Tải toàn bộ hàng trăm nghìn entry vào một `List` có thể gây áp lực bộ nhớ và mạng; ngược lại, chỉ lấy 100 entry rồi gọi là “tất cả” là sai.

### 9.1. Phân biệt top N và full scan

| Hợp đồng | Chiến lược đúng | Điều phải công bố |
| --- | --- | --- |
| Giao diện chọn gợi ý ≤ 20 người | Query scope/filter hẹp, `countLimit` hợp lý | Giới hạn hiển thị và cách tìm tiếp |
| Trang danh sách với điều hướng | Paging khi server hỗ trợ | Cookie/hasMore, trạng thái tiếp tục |
| Export toàn bộ người dùng | Paged results tới khi hoàn tất | Completion, số nguồn/domain, lỗi và consistency |
| Kiểm kê membership dùng cho phân quyền | Bảo đảm nguồn và phạm vi đủ theo mô hình quyền | Không dùng kết quả partial để kết luận quyền |

LDAP **Simple Paged Results** (RFC 2696) cho phép lấy từng trang qua cookie; muốn nói đã duyệt hết theo cơ chế đó cần hoàn tất đúng quy trình cookie. Lấy hết trang từ một LDAP server **không** có nghĩa đã theo mọi referral sang server khác, và không mặc định là snapshot nhất quán khi dữ liệu thay đổi giữa các trang.

### 9.2. Stream không tự bảo đảm completeness hoặc đóng tài nguyên

Các API dạng stream (`LdapClient` hoặc `LdapTemplate.searchForStream` ở phiên bản có hỗ trợ) có thể giảm việc gom toàn bộ dữ liệu vào bộ nhớ, nhưng phải kiểm tra **vòng đời tài nguyên** và quy tắc đóng stream/context theo Javadoc phiên bản đang dùng. Việc stream nhanh hơn cũng không làm biến mất size/time limit, paging, referral hay ACL.

Khi dùng ODM, mapper có thể truy xuất nhiều attribute hoặc biến đổi object phức tạp. Hãy profile phần mapping, chỉ tải dữ liệu cần thiết, nhưng không bỏ validation, objectClass hoặc thuộc tính dùng để xác thực tính hợp lệ của entry.

## 10. Cache có điều kiện: giảm LDAP round-trip nhưng giữ correctness

Caching có thể là tối ưu lớn nhất khi nhiều request đọc cùng dữ liệu; nó cũng là nguồn rủi ro lớn nếu dữ liệu liên quan quyền bị cũ.

### 10.1. Đặt câu hỏi trước khi cache

- Dữ liệu là **public directory metadata**, thông tin hồ sơ, hay **membership/authorization**?
- Cache được phép stale trong bao lâu? Một thay đổi group cần có hiệu lực ngay hay sau vài phút?
- Key có bao gồm **tenant/domain, base DN, scope, filter, identity và quyền của caller** khi cần không?
- Có invalidation hoặc version khi entry đổi DN, user bị khóa, group bị thay đổi?
- Kết quả `not found` có thể bị stale vì entry vừa được tạo không?
- Kết quả partial/error có bị cache như thành công không?

### 10.2. Bảng quyết định cache

| Dữ liệu | Mức rủi ro stale | Chính sách gợi ý |
| --- | --- | --- |
| Tên hiển thị công khai, ít đổi | Thường thấp | TTL có giới hạn, key đúng tenant |
| Thông tin hồ sơ người dùng | Trung bình | TTL/invalidation, kiểm soát dữ liệu riêng tư |
| Membership nhóm có quyền cao | Cao | TTL rất ngắn hoặc đọc trực tiếp; thu hồi quyền phải có hiệu lực theo chính sách |
| Trạng thái khóa/vô hiệu hóa tài khoản | Cao | Không dùng cache cũ để vượt qua chính sách thu hồi |
| Không có entry (negative cache) | Có thể sai ngay khi provisioning | TTL thận trọng, invalidation khi tạo |
| Kết quả `PartialResultException`/timeout | Không phải dữ liệu hợp lệ để cache | Không ghi thành cache hit “danh sách rỗng” |

**Cache stampede** cũng cần xử lý, ví dụ các request cùng miss một key có thể làm LDAP server chịu tải đột ngột. Có thể dùng single-flight, TTL jitter và giới hạn đồng thời, nhưng không được cho một tenant nhận dữ liệu từ key thuộc tenant khác.

### 10.3. Quyền truy cập trong cache phải là một phần thiết kế

Giả sử account dịch vụ có thể nhìn thấy mọi OU, còn caller A chỉ được xem OU phòng ban A. Nếu cache theo `uid` đơn thuần rồi trả lại entry mà service account tìm được, caller B có thể nhận dữ liệu không được phép thấy. Vì vậy:

- Chỉ cache dữ liệu đã được **phân loại phạm vi công bố** hoặc đã được kiểm tra theo caller.
- Nếu kết quả phụ thuộc quyền, key/lookup phải xét identity, tenant hoặc permission version theo chính sách.
- Thay đổi ACL, group hoặc trạng thái tài khoản phải kích hoạt invalidation hoặc giới hạn độ cũ có thể chấp nhận.
- Kiểm thử truy cập chéo user/tenant và trường hợp revoke quyền.

Đừng bỏ kiểm tra authorization tại thời điểm đọc cache chỉ vì cache hit nhanh.

## 11. Correctness khi ghi: không đổi hành vi Modify để chạy nhanh hơn

### 11.1. Thêm một giá trị không phải thay toàn bộ attribute

Ví dụ một nhóm LDAP có:

```text
member = {A, B}
```

Hai request cùng thêm C và D:

```text
Đúng: ADD_ATTRIBUTE member:C, ADD_ATTRIBUTE member:D
      → nếu hợp lệ, có thể được {A, B, C, D}

Nguy hiểm:
    T1 đọc {A, B} → REPLACE {A, B, C}
    T2 đọc {A, B} → REPLACE {A, B, D}
      → cập nhật cuối có thể làm mất C
```

Với `LdapTemplate.modifyAttributes(Name, ModificationItem[])`, nên chọn đúng `DirContext.ADD_ATTRIBUTE`, `REMOVE_ATTRIBUTE` hoặc `REPLACE_ATTRIBUTE`. `REPLACE_ATTRIBUTE` thay **toàn bộ tập giá trị được đưa vào cho thuộc tính đó**, không phải thêm một giá trị. Không thay một thuật toán “chậm nhưng đúng” bằng replace thiếu kiểm soát chỉ để giảm số lượt request.

### 11.2. Precheck trước Add không loại bỏ race condition

```text
Request A: lookup DN → chưa có
Request B: lookup DN → chưa có
Request A: LdapTemplate.bind(DN, ...) → success
Request B: LdapTemplate.bind(DN, ...) → NameAlreadyBoundException (68)
```

Server là nơi phân xử Add tại thời điểm ghi. Một bước precheck có thể giúp UI, nhưng **không bảo đảm uniqueness** khi có nhiều writer. Nếu bỏ bắt `NameAlreadyBoundException` để giảm code hoặc gộp thành thành công, ứng dụng có thể nhận nhầm entry do request khác tạo.

### 11.3. Mất phản hồi sau ghi không đồng nghĩa lệnh chưa chạy

```text
Client → LDAP Add/Modify/Delete → server xử lý thành công
Client ← phản hồi bị mất / socket timeout
Client nhận CommunicationException
```

Nếu retry mù quáng:

- Add có thể nhận `NameAlreadyBoundException` vì entry đã được tạo lần đầu.
- Modify có thể ghi lại, tạo xung đột hoặc thay thế dữ liệu mới của writer khác.
- Delete có thể nhận `NameNotFoundException` vì entry đã bị xóa.

Do đó, với write outcome unknown, phải **đối soát trạng thái**, có idempotency key/quy trình riêng khi cần và kiểm tra phiên bản/ownership trước khi retry. Không áp cùng chính sách retry read-only cho những lệnh ghi.

## 12. Timeout, retry và circuit breaker: bảo vệ cả tốc độ lẫn tính đúng

### 12.1. Chọn đúng loại timeout

| Loại | Mục đích | Lưu ý |
| --- | --- | --- |
| `com.sun.jndi.ldap.connect.timeout` | Giới hạn chờ mở kết nối trong JNDI LDAP provider phổ biến | Không phải deadline của toàn service |
| `com.sun.jndi.ldap.read.timeout` | Giới hạn chờ phản hồi theo provider | Timeout không chứng minh server chưa ghi |
| `LdapQueryBuilder.timeLimit(...)` | Giới hạn tìm kiếm (mili giây) | Không thay cho read timeout |
| HTTP/request deadline | Ngân sách tổng bao gồm pool, bind, query, retry, mapping | Phải tính từ trên xuống |

Tăng mọi timeout để “giảm tỷ lệ lỗi” có thể làm **p99 latency cao hơn** và giữ connection chờ quá lâu. Hạ timeout xuống quá thấp có thể tạo lỗi giả; cần đo trên tải, kích thước response và điều kiện mạng phù hợp.

### 12.2. Retry có điều kiện

Một chiến lược hiệu năng đúng thường gồm số lần thử hữu hạn, backoff, jitter, timeout tổng và bộ phân loại lỗi:

| Lỗi | Retry cùng request? | Giải thích |
| --- | --- | --- |
| Mạng gián đoạn khi thực hiện **đọc** | Có điều kiện | Có thể hồi phục, nhưng phải theo deadline |
| Server bận/tạm không khả dụng | Có điều kiện | Tránh làm nặng thêm outage |
| TLS certificate hoặc hostname không hợp lệ | Không | Phải sửa cấu hình bảo mật |
| Bind credential sai | Không | Retry có thể gây khóa tài khoản |
| Thiếu quyền LDAP `50` | Không | Không phải lỗi tạm thời |
| DN/search base không tồn tại `32` | Thường không | Kiểm tra cấu hình, trạng thái và quy trình provisioning |
| Referral không theo được do policy | Không retry mù quáng | Sửa coverage/referral policy |
| Mất phản hồi **sau khi gửi write** | Không tự động | Kết quả ghi chưa xác định |

Circuit breaker và bulkhead hữu ích khi LDAP chậm kéo dài: chúng giúp hệ thống tránh dồn tải. Nhưng **fallback** khi breaker mở phải tuân thủ ngữ nghĩa bảo mật. Đối với quyết định cấp quyền, “LDAP chưa kiểm tra được” **không phải** “người dùng không cần được kiểm tra”; thường cần từ chối cấp quyền mới hoặc báo không thể xác minh, theo policy đã thiết kế.

## 13. Ví dụ chống anti-pattern: exception không bị nuốt thành kết quả rỗng

Service dưới đây phân biệt “entry không có” và “LDAP không thể được kiểm tra”. Một `lookup` tới DN hợp lệ có thể trả `Optional.empty()` khi `NameNotFoundException` xảy ra; các lỗi mạng được giữ như lỗi hạ tầng.

```java
import java.util.Optional;
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class SafePersonLookup {
    private final LdapTemplate template;

    public SafePersonLookup(LdapTemplate template) {
        this.template = template;
    }

    public Optional<String> findCn(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            String cn = template.lookup(dn,
                    (AttributesMapper<String>) attrs -> {
                        Attribute value = attrs.get("cn");
                        if (value == null || value.size() == 0) {
                            throw new IllegalStateException(
                                    "Entry tồn tại nhưng thiếu cn");
                        }
                        return value.get().toString();
                    });
            return Optional.ofNullable(cn);
        } catch (NameNotFoundException ex) {
            return Optional.empty(); // Theo hợp đồng riêng của lookup.
        } catch (CommunicationException | ServiceUnavailableException ex) {
            throw new DirectoryUnavailableException(ex);
        }
    }

    public static final class DirectoryUnavailableException
            extends RuntimeException {
        public DirectoryUnavailableException(Throwable cause) {
            super("LDAP không khả dụng", cause);
        }
    }
}
```

Với `search`, cần thêm chính sách riêng cho `PartialResultException`, `TimeLimitExceededException`, `SizeLimitExceededException` và search base không tồn tại. Không dùng kết quả rỗng từ một search bị lỗi làm chứng cứ “không có membership” hoặc “không có tài khoản”.

## 14. Bộ kiểm thử hồi quy bắt buộc trước khi nhận tối ưu

### 14.1. Ma trận kiểm thử hiệu năng và an toàn

| Mã test | Tình huống | Kết quả cần giữ |
| --- | --- | --- |
| SEC-01 | LDAPS cert do CA tin cậy cấp, SAN đúng | Thành công |
| SEC-02 | Cert không được tin, hết hạn hoặc hostname sai | Từ chối; không dùng trust-all |
| SEC-03 | StartTLS thất bại | Không simple bind bằng plaintext |
| SEC-04 | User A/B có quyền khác nhau | Không lẫn context/cache hoặc trả dữ liệu ngoài quyền |
| SEC-05 | Account bị khóa hoặc quyền vừa bị thu hồi | Không cấp quyền nhờ cache stale ngoài chính sách |
| LDAP-01 | Search filter có dấu `*`, `(`, `)`, backslash | Được escape đúng; không LDAP injection |
| LDAP-02 | DN có dấu phẩy hoặc ký tự cần escape | `LdapNameBuilder` tạo đúng DN |
| LDAP-03 | Entry nằm trong OU con sâu | Search scope không bỏ sót dữ liệu nghiệp vụ |
| LDAP-04 | Base hợp lệ, filter không khớp | Trả danh sách rỗng hợp lệ |
| LDAP-05 | Search base/OU sai | Không lặng lẽ bỏ qua `NameNotFoundException` |
| LDAP-06 | Có referral sang domain B | Không gọi dữ liệu domain A là toàn bộ dữ liệu |
| LDAP-07 | Size/time limit bị chạm | Không trả dữ liệu bị cắt như đã đầy đủ |
| DATA-01 | Hai writer cùng Add DN | Một Add thành công, conflict được nhận diện |
| DATA-02 | Hai writer cùng thêm group member | Không mất thành viên do REPLACE toàn bộ |
| DATA-03 | Mất phản hồi sau Add đã thành công | Không retry write mù quáng |
| PERF-01 | Tải bình thường, cache hit/miss | p95/p99 và số LDAP operations được đo |
| PERF-02 | Pool stale connection | Connection hỏng được loại bỏ, deadline được tôn trọng |
| PERF-03 | LDAP outage, nhiều request đồng thời | Retry hạn chế, không tăng tải vô hạn |
| PERF-04 | Cache invalidation sau đổi quyền | Độ trễ thu hồi phù hợp với policy đã định |

Một thay đổi chỉ được xem là **cải thiện** khi metric performance tốt lên theo tiêu chí đã đặt **và** các test bảo mật/correctness vẫn đạt.

### 14.2. Unit test minh họa: lỗi mạng không biến thành “không có người dùng”

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

class SafePersonLookupTest {
    @Test
    @SuppressWarnings("unchecked")
    void networkFailureCannotBeOptimizedIntoEmptyResult() {
        LdapTemplate template = mock(LdapTemplate.class);
        when(template.lookup(
                any(Name.class), any(AttributesMapper.class)))
                .thenThrow(new CommunicationException(
                        new javax.naming.CommunicationException(
                                "Simulated network failure")));

        SafePersonLookup service = new SafePersonLookup(template);

        assertThrows(
                SafePersonLookup.DirectoryUnavailableException.class,
                () -> service.findCn("an"));
    }
}
```

Unit test này kiểm chứng **quyết định xử lý lỗi**, không chứng minh timeout thực tế của socket. Cần integration/fault test riêng với LDAP test server hoặc network proxy được phép để kiểm tra connect/read timeout, TLS validation, referral và mất phản hồi sau write.

### 14.3. Test query optimization bằng so sánh tập kết quả

Giả sử đang thay query `SUBTREE` toàn thư mục bằng nhiều query có base hẹp hơn. Cần tạo dữ liệu thử có user ở:

```text
ou=people,dc=example,dc=org
ou=engineering,ou=people,dc=example,dc=org
ou=contractors,dc=example,dc=org
```

Định nghĩa **tập user mong đợi theo nghiệp vụ** rồi so sánh set/identity ổn định giữa thuật toán cũ và mới. Không chỉ so sánh `size()`: hai danh sách có số phần tử bằng nhau vẫn có thể chứa người khác nhau hoặc bị trùng. Phải xét server referral/replication và các attribute dùng để quyết định điều kiện lọc.

### 14.4. Test pooling và cache với danh tính khác nhau

- Tạo user A/B có ACL và dữ liệu đọc được khác nhau; interleave các request để phát hiện identity leakage.
- Thử context sau idle timeout của LDAP server/load balancer; đo tỉ lệ stale connection và hành vi invalidation.
- Thử thay đổi membership ngay sau cache hit; xác minh giới hạn thời gian dữ liệu cũ được dùng.
- Thử cache miss đồng thời để đo liệu nhiều request có tạo thành stampede không.
- Thử logout, khóa account hoặc rotate secret service; bảo đảm không có đường dùng credential/context cũ ngoài chính sách.

Đây là những kiểm thử **correctness trước, performance sau**. Tắt chúng để benchmark “xanh” sẽ khiến kết quả đo không đáng tin.

## 15. Quy trình tối ưu 7 bước

1. **Viết hợp đồng**: truy vấn cần trả dữ liệu gì, trong phạm vi nào, quyền nào, chính sách completeness và staleness nào?
2. **Đặt SLO/metric**: p95/p99 theo thao tác, tải đỉnh, error rate, số connection và số byte/entry.
3. **Đo baseline**: lấy workload đại diện, cả trường hợp bình thường và lỗi mạng/referral.
4. **Định vị nút thắt**: TLS handshake quá nhiều, pool wait, search không có index, filter quá rộng, mapper nặng, cache miss hoặc retry storm.
5. **Chọn thay đổi có cơ sở**: thu hẹp search **đúng scope**, chỉ yêu cầu attribute cần thiết, index, paging, cache an toàn, validation pool, deadline phù hợp.
6. **Chạy test correctness + security**: TLS âm tính, ACL/tenant isolation, kết quả đầy đủ, concurrent write, lỗi mạng và cache invalidation.
7. **So sánh cùng tải và rollout có giám sát**: đo trước/sau, quan sát error/partial ratio và rollback khi bất biến bị phá vỡ.

Ví dụ biểu đồ quyết định:

```text
Có vấn đề latency?
       │
       ▼
Đã đo được nút thắt thực?
       ├── Chưa → profiling/metrics trước
       └── Có
            │
            ▼
Thay đổi có giữ TLS/auth/ACL, scope, completeness và data integrity?
       ├── Không → từ chối phương án; chọn cách tối ưu khác
       └── Có
            │
            ▼
Benchmark tốt hơn và security/correctness tests đều PASS?
       ├── Không → điều tra hoặc rollback
       └── Có   → triển khai có giám sát
```

## 16. Tình huống thực tế

### A. “Tắt xác minh certificate giúp query nhanh hơn”

**Đánh giá:** Sai hướng. Nếu handshake chậm, đo số connection mới, cấu hình pooling tương thích, đường mạng và TLS session reuse (nếu provider hỗ trợ). Sửa truststore/hostname khi chứng chỉ lỗi. Không được chấp nhận đầu cuối chưa xác thực.

### B. “Bỏ qua `PartialResultException` để trang danh sách luôn có dữ liệu”

**Đánh giá:** Có thể là quyết định nghiệp vụ **chỉ khi** endpoint thực sự chấp nhận kết quả cục bộ hoặc chưa đầy đủ, có metadata minh bạch và không dùng cho cấp quyền/đối soát. Không thể áp dụng chung cho quy trình đồng bộ toàn forest hay tìm tất cả group.

### C. “Tăng pool lên vô hạn để giảm pool wait”

**Đánh giá:** Có thể làm server cạn connection/thread; đồng thời tăng số context stale. Chọn giới hạn active/idle, timeout borrow, validation và load test cả client lẫn server; giữ tách biệt danh tính xác thực.

### D. “Cache group membership 24 giờ để khỏi hỏi LDAP”

**Đánh giá:** Chỉ hợp lệ nếu chính sách quyền chấp nhận thu hồi chậm tương ứng, điều này thường không phù hợp với quyền nhạy cảm. Cần TTL, invalidation, version/quy tắc recheck và thử tình huống bị thu hồi quyền.

### E. “Thay 2 Modify bằng 1 REPLACE để giảm round-trip”

**Đánh giá:** Nếu REPLACE được xây từ trạng thái stale hoặc từ tập attribute không đầy đủ, có thể mất update khác. Dùng `ModificationItem` thích hợp hoặc cơ chế concurrency control đáng tin cậy; đo lợi ích sau khi kiểm chứng dữ liệu không bị thay đổi ngoài ý định.

### F. “LDAP timeout thì trả `[]` cho endpoint phân quyền”

**Đánh giá:** Không được. `[]` thể hiện không có dữ liệu trong một search hợp lệ, còn timeout là không thể xác minh. Cần chính sách lỗi và fail-closed theo nghiệp vụ, không biến outage thành một quyết định quyền có vẻ chắc chắn.

## 17. Checklist trước khi đưa tối ưu vào production

- [ ] Phạm vi query, kiểu filter, DN và matching rule được mô tả rõ, không thay đổi trái nghiệp vụ.
- [ ] TLS/LDAPS hoặc StartTLS được cấu hình đúng, kiểm tra CA/hostname; không trust-all.
- [ ] Service account dùng least privilege, authorization của HTTP caller vẫn được thực hiện.
- [ ] Bind xác thực của từng người dùng không bị cache/chia sẻ context sai danh tính.
- [ ] Pool có giới hạn, validation và timeout; không native pool cho StartTLS/context thay đổi trạng thái nếu không được hỗ trợ.
- [ ] Search base/scope/attribute chỉ được thu hẹp khi vẫn tìm đúng toàn bộ đối tượng cần thiết.
- [ ] Filter và DN đều được escape bằng builder thích hợp; có test input đặc biệt.
- [ ] Query có count/time limit hoặc paging thể hiện rõ completeness và lỗi.
- [ ] Không bỏ qua referral/partial result âm thầm khi dùng kết quả cho thống kê, đồng bộ hoặc phân quyền.
- [ ] Cache có key phù hợp identity/tenant/ACL, TTL và invalidation; không cache outage thành kết quả rỗng.
- [ ] Retry có deadline/backoff, kiểm soát tải và không retry write outcome unknown mù quáng.
- [ ] Test schema, ACL, concurrent Add/Modify và trạng thái không xác định sau mất kết nối vẫn PASS.
- [ ] Có baseline và so sánh p50/p95/p99, throughput, error rate cùng correctness/security regressions.
- [ ] Log/trace không chứa password, token, DN nhạy cảm hoặc filter PII; có correlation ID để điều tra.

## 18. Câu hỏi tự đánh giá

**Câu 1.** Vì sao `setIgnorePartialResultException(true)` không phải một cách tối ưu tổng quát cho truy vấn đa domain?

**Trả lời:** Nó có thể làm search trả kết quả khi referral chưa được theo; danh sách thiếu dữ liệu không được coi là toàn bộ phạm vi nghiệp vụ.

**Câu 2.** Nếu `LDAP p95` giảm sau khi giảm scope từ `SUBTREE` xuống `ONELEVEL`, kết quả đã chắc đúng chưa?

**Trả lời:** Chưa. Nếu có entry trong OU con, `ONELEVEL` bỏ sót chúng. Phải đối chiếu tập kết quả trên dữ liệu đại diện.

**Câu 3.** Có nên dùng một tài khoản LDAP quyền admin để bỏ hết lỗi ACL, qua đó tăng hiệu năng?

**Trả lời:** Không. Đây là mở rộng quyền, không phải tối ưu. Dùng least privilege và phân quyền caller rõ ràng.

**Câu 4.** Vì sao pooled context dùng cho authentication theo từng người dùng nguy hiểm?

**Trả lời:** Context có trạng thái danh tính; pooling không đúng có thể dùng credential của request trước cho request sau và gây rò quyền.

**Câu 5.** Cache `memberOf` có giúp tăng tốc không? Điều kiện để dùng đúng là gì?

**Trả lời:** Có thể giúp giảm truy vấn, nhưng phải kiểm soát TTL, revocation, key theo identity/tenant, mức độ nhạy cảm quyền và invalidation.

**Câu 6.** Vì sao một `CommunicationException` sau lệnh Add không được retry lập tức?

**Trả lời:** Server có thể đã thêm entry và phản hồi bị mất. Cần kiểm tra trạng thái/idempotency trước khi thực hiện lại.

**Câu 7.** Tại sao bật `setIgnoreSizeLimitExceededException(true)` có thể là đúng với `top 20` nhưng sai với `export all`?

**Trả lời:** Với top 20, giới hạn là hợp đồng đã công bố; với export all, bỏ qua giới hạn có thể làm báo cáo thiếu dữ liệu mà caller tưởng đầy đủ.

**Câu 8.** Tăng pool size có tự động giảm latency không?

**Trả lời:** Không. Pool lớn có thể tăng tải server và số connection stale. Cần đo pool wait, server saturation, validation, giới hạn và tail latency.

## 19. Tài liệu tham khảo

- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `base`, `searchScope`, `attributes`, `countLimit`, `timeLimit` và filter.
- [Spring LDAP API — `LdapQueryBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): escaping của giá trị filter và cấu hình truy vấn.
- [Spring LDAP API — `LdapNameBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html): xây DN/RDN an toàn.
- [Spring LDAP API — `LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): search, modify và các cờ bỏ qua exception.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): giới hạn pool, validation, sự cố connection và custom authentication.
- [Spring LDAP API — `AbstractContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): `setPooled`, `setReferral`, cấu hình context.
- [Oracle JNDI LDAP — Connection Pooling](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/pool.html): cảnh báo về pooling với StartTLS và thay đổi trạng thái xác thực.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, `LdapTemplate` và `LdapClient`.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): tìm kiếm, Modify, referrals, limits và result codes.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): bảo vệ quá trình xác thực LDAP.
- [RFC 2696 — Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696): phân trang kết quả LDAP.

**Ghi nhớ:** Tối ưu Spring LDAP là **giảm chi phí mà vẫn giữ nguyên ý nghĩa và mức bảo vệ của thao tác**. Hãy đo bottleneck thật, thu hẹp truy vấn đúng phạm vi, chọn pool/cache/paging có kiểm soát và giữ đầy đủ TLS, xác thực, phân quyền, exception, completeness và data integrity. Một kết quả nhanh nhưng thiếu dữ liệu hoặc mất an toàn không phải là cải thiện hiệu năng.
