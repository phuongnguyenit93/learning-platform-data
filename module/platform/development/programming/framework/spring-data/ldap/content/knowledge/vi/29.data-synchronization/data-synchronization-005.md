# Đồng bộ tăng dần theo khả năng máy chủ

Trong hệ thống dùng **Spring Data LDAP**, ứng dụng Java có thể đọc entry thông qua `LdapRepository` hoặc `LdapTemplate` rồi lưu bản sao cần thiết vào cơ sở dữ liệu ứng dụng, search index hoặc dịch vụ khác. Nếu mỗi lần đồng bộ đều tải toàn bộ cây LDAP, hệ thống dễ gây tải lớn, xử lý trùng lặp và kéo dài thời gian phát hiện thay đổi. **Đồng bộ tăng dần (incremental synchronization)** cố gắng chỉ lấy những entry hoặc sự kiện đã thay đổi sau lần xử lý thành công trước đó.

Tuy nhiên, LDAP **không có một API delta duy nhất mà mọi máy chủ đều hỗ trợ giống nhau**. Tùy server, có thể có **LDAP Content Synchronization (RFC 4533)**, **Active Directory DirSync**, **changelog/change tracking** riêng, hoặc chỉ đủ khả năng **polling theo thuộc tính thời gian** rồi định kỳ đối soát toàn bộ. Bài thuộc chương **Đồng bộ dữ liệu** này hướng dẫn cách đánh giá khả năng server, thiết kế cursor/checkpoint, xử lý thêm–sửa–xóa–đổi DN, kết hợp Spring LDAP với cơ chế đặc thù và kiểm thử tính đúng đắn.

> **Nguyên tắc xuyên suốt:** không coi `modifyTimestamp`, một LDAP search có filter thời gian, hay một lần export LDIF là bằng chứng đã thu nhận **mọi** thay đổi. Cần xác định rõ server cung cấp loại sự kiện nào, cursor có bền vững không, và cách phục hồi khi bị mất trạng thái hoặc kết nối.

## 1. Tình huống thực tế và mục tiêu đồng bộ

Giả sử directory nguồn chứa:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001  → cn=An Nguyen, mail=an@example.org
│   └── uid=u1002  → cn=Binh Tran, mail=binh@example.org
└── ou=groups
    └── cn=developers
```

Ứng dụng cần giữ một bản sao **chỉ đọc** của danh tính trong bảng nội bộ để tìm kiếm nhanh. Trong ngày có thể xuất hiện:

1. **Add:** tạo `uid=u1003,ou=people,...`.
2. **Modify:** đổi `mail` của `u1001`.
3. **Rename:** đổi RDN `uid=u1001` thành `uid=u1001-new`.
4. **Move:** chuyển `u1002` từ `ou=people` sang `ou=contractors`.
5. **Delete:** xóa một entry khỏi directory nguồn.
6. **Change ngoài phạm vi:** một service account ở `ou=service-accounts` được sửa nhưng không thuộc dữ liệu cần đồng bộ.

Bản sao phải phản ánh chính xác **những thay đổi nằm trong phạm vi được phép** và không tự ý xử lý các entry khác.

| Loại thay đổi | Full scan định kỳ | Delta có thông tin thay đổi đủ tốt |
|---|---|---|
| Thêm entry | Phát hiện khi entry xuất hiện trong snapshot mới | Nhận entry mới qua sự kiện/trạng thái |
| Sửa thuộc tính | Phát hiện qua so sánh snapshot | Nhận entry có thuộc tính được cập nhật |
| Rename/move trong phạm vi | Thấy DN thay đổi; cần nhận dạng cùng identity | Dùng stable ID và metadata thay đổi DN nếu server cung cấp |
| Move ra khỏi phạm vi | Thấy entry vắng mặt trong scan đủ tin cậy | Cần sự kiện thoát scope hoặc đối soát |
| Xóa entry | Có thể suy ra bằng so sánh snapshot hoàn chỉnh | Cần delete/tombstone/changelog được hỗ trợ |
| Thay đổi khi client offline | Được phát hiện ở lần scan đầy đủ tiếp theo | Chỉ được bảo đảm nếu server giữ đủ history/cookie hợp lệ |

**Mục tiêu:** tối ưu bằng delta nhưng vẫn có cách **bootstrap** và **reconciliation** (đối soát) để khôi phục tính đúng đắn.

## 2. Phân biệt snapshot, delta và event stream

Ba nguồn dữ liệu này khác nhau:

- **Snapshot:** trạng thái các entry còn tồn tại trong một phạm vi tại thời điểm đọc. Ví dụ `ldapsearch` lấy toàn bộ người dùng dưới `ou=people`.
- **Delta:** những entry/sự kiện cần xử lý kể từ checkpoint đã xác nhận. Có thể là “entry thay đổi” chứ không nhất thiết là mọi thao tác trung gian.
- **Event stream:** chuỗi thông báo thay đổi gần thời gian thực; một số cơ chế không giữ đủ lịch sử để client offline có thể resume.

Ví dụ tài khoản có email A → B → C trong thời gian client ngắt kết nối: một cơ chế delta theo **trạng thái cuối** có thể chỉ trả entry với email C. Nếu nghiệp vụ cần **audit từng lần sửa**, phải dùng cơ chế nhật ký sự kiện có đủ retention/chứng cứ; đồng bộ trạng thái không thay thế nhật ký kiểm toán.

Vì vậy cần trả lời trước: **“Đích cần trạng thái cuối của các entry hay cần toàn bộ lịch sử thao tác?”** Bài tập này chủ yếu xây đồng bộ **trạng thái cuối** với khả năng phát hiện add/modify/delete/rename phù hợp theo server.

### Bất biến quan trọng

- Chỉ có **một nguồn sở hữu** cho mỗi thuộc tính đồng bộ, hoặc có chính sách giải quyết xung đột rõ ràng.
- Không ghi checkpoint trước khi dữ liệu tương ứng đã được xử lý và lưu bền vững.
- Áp dụng lại cùng thay đổi phải không gây sai lệch (**idempotent**).
- Phải biết khi nào delta **không còn đáng tin**, để chuyển sang đối soát hoặc bootstrap lại.
- Không dùng kết quả search bị cắt cụt hoặc bị giới hạn quyền làm căn cứ xóa dữ liệu hàng loạt.

## 3. Chọn khóa danh tính: DN không phải định danh bất biến

Ví dụ entry LDAP:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an@example.org
modifyTimestamp: 20261126100000Z
```

**LDIF minh họa:** `modifyTimestamp` thường là thuộc tính vận hành do server quản lý; khi nạp dữ liệu test cần tuân theo cách server cấp phát thuộc tính này, không xem đây là trường client tự ý ghi.

Cần tách các loại định danh:

| Giá trị | Ý nghĩa | Điểm cần lưu ý |
|---|---|---|
| DN: `uid=u1001,ou=people,...` | Địa chỉ entry hiện tại trong DIT | Thay đổi khi rename/move |
| `uid=u1001` | Thuộc tính nghiệp vụ | Không nhất thiết duy nhất toàn forest/nhiều suffix hoặc bất biến |
| `entryUUID` (một số LDAP server) | Định danh entry do server quản lý | Thường phù hợp để liên kết trong vòng đời entry; kiểm tra hỗ trợ/ACL |
| `objectGUID` (Active Directory) | GUID nhị phân của AD object | Phải giải mã đúng byte; có ngữ nghĩa vòng đời/migration riêng |
| `modifyTimestamp` | Thời điểm entry được sửa theo server | Không đủ để xác định delete hoặc phân biệt mọi sự kiện |

Mẫu lưu trạng thái ở đích nên có ít nhất:

```text
source_id            ví dụ: ldap-people-prod
directory_object_id  stable ID do nguồn cung cấp (theo khả năng server)
current_dn           DN hiện tại, không coi bất biến
attributes           các trường được phép đồng bộ
last_seen_version    version/metadata nếu server có
last_applied_at      thời điểm đích cập nhật thành công
lifecycle_state      active / out_of_scope / deleted theo quy tắc
```

Nếu server không cung cấp ID bền vững, cần mô tả rõ **giới hạn nhận dạng rename/move**; dùng DN làm khóa tạm không tương đương với việc biết một entry đã chuyển chỗ.

## 4. Ma trận khả năng của LDAP server

| Nguồn thay đổi | Ý nghĩa | Có cursor/resume? | Delete/rename | Tính di động |
|---|---|---|---|---|
| **LDAP Sync – RFC 4533** | Đồng bộ nội dung với `refreshOnly` hoặc `refreshAndPersist` | Cookie/metadata do server cấp | Có trạng thái `present`, `add`, `modify`, `delete` theo giao thức; cần kiểm thử scope | Phụ thuộc server hỗ trợ RFC 4533 |
| **Active Directory DirSync** | LDAP control riêng của AD để lấy thay đổi trong scope | Cookie DirSync | Tùy quyền và hành vi deleted objects/tombstone; cần kiểm tra riêng | Chỉ AD DS/hệ thống tương thích |
| **Changelog/retro changelog** | Nhật ký thao tác theo sản phẩm/cấu hình | Thường có sequence/offset và retention | Có thể chứa add/modify/delete/moddn, tùy sản phẩm | Không có contract chung cho mọi LDAP server |
| **Persistent search / notification** | Theo dõi thay đổi khi kết nối còn sống | Không nhất thiết có cursor bền | Tùy control và server | Phụ thuộc triển khai |
| **Polling `modifyTimestamp`** | Search các entry hiện còn với timestamp mới | Watermark do client tự quản | **Không bảo đảm phát hiện delete/move ra scope** | Có thể áp dụng ở nhiều server nếu hỗ trợ thuộc tính/filter |
| **Full rescan + diff** | Đọc lại tập dữ liệu và so sánh | Checkpoint theo chu kỳ scan | Phát hiện vắng mặt nếu snapshot đầy đủ và quyền đủ | Ít yêu cầu extension, nhưng tốn tài nguyên |

Không suy ra một server “hỗ trợ LDAP” thì tự động hỗ trợ **LDAP Sync**, **DirSync**, mọi thông báo xóa hoặc cùng cơ chế cookie. Đặc biệt:

- **OpenLDAP:** có thể triển khai cơ chế đồng bộ/nhân bản liên quan LDAP Sync và các overlay như accesslog theo cấu hình.
- **Active Directory:** dùng cơ chế/change tracking riêng như DirSync; không mặc định hỗ trợ RFC 4533 theo cùng nghĩa.
- **389 Directory Server và các directory khác:** có cơ chế changelog/replication riêng; phải xác nhận control, retention và quyền với server cụ thể.

Các tính năng nhân bản **server–server** không nhất thiết là API public dành cho mọi ứng dụng client. Đọc tài liệu và chính sách của server đích trước khi chọn cơ chế.

## 5. Khám phá khả năng qua RootDSE

**RootDSE** là entry đặc biệt ở DN rỗng (`""`) cung cấp metadata về LDAP server. Có thể đọc `namingContexts`, `supportedControl`, `supportedExtension` và những trường hợp riêng của từng directory.

Ví dụ dùng OpenLDAP CLI trên **directory được phép truy cập**:

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D 'cn=svc-sync,ou=service-accounts,dc=example,dc=org' -W \
  -b '' -s base '(objectClass=*)' \
  namingContexts supportedControl supportedExtension
```

Ý nghĩa:

- `-b '' -s base` yêu cầu đúng RootDSE, không phải search toàn domain.
- `supportedControl` công bố các LDAP control mà endpoint báo hỗ trợ.
- `namingContexts` cho biết các partition/cây mà server công bố; lựa chọn base đồng bộ phải phù hợp với phạm vi nghiệp vụ.
- `-H ldaps://...` sử dụng TLS; máy client cần tin CA và xác minh hostname, không tắt kiểm tra chứng chỉ.

Ví dụ một LDAP server có hỗ trợ LDAP Sync có thể công bố OID của **Sync Request Control**:

```text
1.3.6.1.4.1.4203.1.9.1.1
```

Active Directory DirSync thường dùng control OID:

```text
1.2.840.113556.1.4.841
```

**OID xuất hiện là tín hiệu để tiếp tục xác minh, không phải bảo đảm đã có quyền và có thể chạy an toàn.** Cần kiểm tra server/version, mức quyền, scope cho phép, cách khởi tạo request control và response, cookie, hành vi xử lý xóa cũng như giới hạn tải.

**Bẫy Spring LDAP:** nếu `LdapContextSource` đã đặt base `dc=example,dc=org`, thì `ldapTemplate.lookup("")` thường đọc **entry ở context base**, không phải RootDSE. Muốn đọc RootDSE phải dùng context không áp base hoặc công cụ/API kết nối trực tiếp hỗ trợ truy vấn DN rỗng.

## 6. LDAP Content Synchronization (RFC 4533)

RFC 4533 định nghĩa cách client nhận **nội dung directory đồng bộ** trong scope bằng một tập LDAP control/intermediate response. Hai chế độ quan trọng:

1. **`refreshOnly`:** client lấy tập thay đổi/trạng thái cần thiết rồi hoàn tất vòng đồng bộ. Phù hợp polling theo chu kỳ với cookie.
2. **`refreshAndPersist`:** sau pha refresh, client giữ search đang hoạt động để nhận các thay đổi tiếp theo khi kết nối còn sống.

Client quản lý **cookie** do server cấp để tiếp tục đồng bộ theo trạng thái mà server hiểu. Cookie là **opaque**: không phân tích nội dung rồi tự tăng số, không xem nó là timestamp hoặc số thứ tự toàn cục.

Các trạng thái sync entry thường bao gồm **`present`**, **`add`**, **`modify`**, **`delete`**, cùng metadata để nhận dạng entry. Mức thông tin cụ thể phụ thuộc server và quyền; một client đúng giao thức phải xử lý cả pha refresh/present reconciliation, không chỉ danh sách modify.

```text
Khởi tạo search với sync control
             │
             ▼
      REFRESH PHASE
   present/add/modify/delete
             │
             ▼
  sync done + cookie (nếu có)
             │
       ┌─────┴─────────────┐
       │                   │
   refreshOnly       refreshAndPersist
   kết thúc vòng     giữ search để nhận
   và lưu state      thay đổi tiếp theo
```

### Các rủi ro cần thiết kế

- Nếu server không hỗ trợ control hoặc cookie hết hiệu lực, **không được tiếp tục như thể chưa mất dữ liệu**; phải refresh/reconcile lại.
- Đứt kết nối ở chế độ persist yêu cầu chiến lược **reconnect + resume** theo contract server, không coi thông báo chỉ tồn tại trong RAM là hàng đợi bền vững.
- Phạm vi `base/scope/filter` phải được giữ nhất quán với trạng thái/cookie tương ứng; thay đổi scope có thể yêu cầu bootstrap mới.
- Không dùng cookie của endpoint/partition khác một cách tùy tiện, kể cả khi tên DN giống nhau.
- Thao tác thực thi control trong Java có thể cần **JNDI `LdapContext`, BER encoding và xử lý response control** hoặc client SDK phù hợp, không chỉ derived method của repository.

**LDAP Sync là đồng bộ nội dung, không đồng nghĩa một event log kiểm toán chứa mọi thao tác trung gian.** Nếu đối tượng thay đổi nhiều lần trong khoảng nghỉ, client cần quan tâm trạng thái cuối và cách xử lý tương ứng.

## 7. Active Directory DirSync và giới hạn riêng

Trên **Active Directory Domain Services (AD DS)**, DirSync là một LDAP control dùng cho việc lấy dữ liệu thay đổi trong một phạm vi AD. Client gửi một **DirSync request control**, server trả dữ liệu và **cookie** để dùng cho lượt tiếp theo.

```text
AD Domain Controller
    ├── domain naming context
    ├── directory changes
    └── DirSync response + opaque cookie
                  │
                  ▼
        Ứng dụng lưu checkpoint
                  │
                  ▼
     Lần sau dùng lại cookie phù hợp
```

Khác biệt cần nhớ so với LDAP Sync RFC 4533:

- OID và định dạng control riêng của Microsoft, không sử dụng trực tiếp RFC 4533 request/response.
- DirSync chịu **quyền truy cập và yêu cầu đặc biệt của AD**, trong đó có thể liên quan quyền đọc thay đổi/replication theo cấu hình. Không mặc định tài khoản search bình thường có thể dùng DirSync.
- Dữ liệu có thể có **deleted objects/tombstones** và các hành vi hiển thị đặc thù; cần kiểm thử cách client nhận và xử lý delete theo phiên bản/cấu hình AD, không suy rằng mọi delete đều mang đủ thuộc tính gốc.
- Một AD domain có **domain naming context** riêng; tìm cross-domain trong forest không chỉ là đổi search base của một DC.
- `objectGUID` (binary), `objectSid`, `uSNChanged` và metadata AD có ngữ nghĩa khác `uid`/`entryUUID` trong directory thông thường.

### Vì sao không dùng `uSNChanged` như cursor phổ quát?

`uSNChanged` có thể hữu ích khi theo dõi thay đổi **với một domain controller và mô hình consistency đã xác định**, nhưng số USN là metadata gắn với quá trình cập nhật/replication của DC, không phải một chuỗi toàn cục có thể chuyển nguyên sang bất kỳ DC nào. DC failover, restore, replication lag và đổi nguồn truy vấn làm việc dùng USN làm watermark khó đúng.

Nếu chọn phương án theo USN, phải quản lý danh tính DC/replication metadata, xử lý mất đồng bộ và đối soát theo hướng dẫn AD. Với một ứng dụng thông thường, ưu tiên control/cơ chế được server hỗ trợ cho use case, thay vì tự xây delta dựa trên so sánh `uSNChanged` đơn giản.

## 8. Changelog, notification và khả năng replay

Một số LDAP server cung cấp **changelog**: tập record mô tả add, modify, delete, rename/move với sequence number hoặc marker riêng. Ví dụ (sơ đồ logic, **không phải LDIF chuẩn chung**):

```text
change 101: ADD uid=u1003,ou=people,...
change 102: MODIFY mail of uid=u1001,ou=people,...
change 103: MODDN uid=u1002 → ou=contractors
change 104: DELETE uid=u1003,ou=people,...
```

Nếu changelog có **retention** giới hạn, client offline quá lâu có thể mất những record cũ. Khi phát hiện **gap**, cursor không hợp lệ hoặc sequence bị reset, cần làm full reconciliation hoặc bootstrap phù hợp.

**Persistent search / notification** có thể hữu ích để giảm latency, nhưng phải hỏi:

- Notification có được lưu bền khi client mất kết nối không?
- Có cookie/sequence để **resume từ sự kiện chưa xử lý** không?
- Có phát delete/move ngoài search scope không?
- Có giới hạn phiên, heartbeat hoặc thứ tự sự kiện không?
- Server có cho tài khoản dịch vụ đọc nguồn thay đổi không?

**Thông báo gần thời gian thực không tương đương khả năng replay.** Nếu thiếu cursor bền, hãy kết hợp notification với đối soát đầy đủ hoặc nguồn thay đổi có lưu lịch sử.

## 9. Khi không có change feed: polling `modifyTimestamp`

Nhiều directory công bố thuộc tính vận hành `modifyTimestamp`. Có thể tìm những **entry hiện còn tồn tại** với thời điểm thay đổi lớn hơn hoặc bằng watermark client đang giữ:

```ldap
(&(objectClass=inetOrgPerson)(modifyTimestamp>=20261126100000Z))
```

Filter này là ví dụ cho server có hỗ trợ **ordering matching rule** trên `modifyTimestamp` trong phạm vi cần đọc. Không mặc định mọi directory đều hỗ trợ cùng thuộc tính, index hay phép so khớp; phải thử với server thật.

### Các điều kiện phải kiểm tra

1. Server cập nhật `modifyTimestamp` khi những thuộc tính ứng dụng theo dõi thay đổi.
2. Tài khoản bind được quyền đọc/tham chiếu `modifyTimestamp`.
3. So khớp `>=` trên cú pháp GeneralizedTime hoạt động đúng theo schema.
4. Thời gian và timezone được chuẩn hóa; ví dụ `20261126100000Z` là UTC.
5. Phạm vi search cố định, có xử lý size/time limit, paging, trùng và nguồn replication.
6. **Xóa entry không còn có mặt trong search**, nên không thể phát hiện mọi delete chỉ bằng filter này.
7. **Move ra ngoài base** có thể khiến entry biến mất khỏi các query sau đó mà không phát ra bản ghi mới trong scope.

Ngay cả khi có thời gian sửa, **không lấy `Instant.now()` ở client làm checkpoint “an toàn tuyệt đối”**: clock skew, replication lag, timestamp bằng nhau hoặc quá trình phân trang có thể làm lọt thay đổi.

### Overlap window và idempotency

Với polling fallback, có thể cố ý lùi watermark một khoảng:

```text
Checkpoint đã commit: 10:00:00Z
Overlap:             00:05:00
Lần sau query:        modifyTimestamp >= 09:55:00Z
```

Việc lặp lại một số entry là **có chủ đích**. Đích phải upsert theo stable ID và chỉ cập nhật khi version/dữ liệu mới hơn để xử lý duplicate.

**Overlap chỉ giảm rủi ro, không tạo bảo đảm đầy đủ**: replication trễ quá cửa sổ, xóa, rename ra scope, quyền ACL, giới hạn trang và timestamp không được quản lý nhất quán vẫn có thể gây mất thay đổi. Vì vậy phải có **đối soát toàn bộ theo chu kỳ**.

## 10. Ví dụ Java: polling fallback với `LdapTemplate`

Đoạn code này minh họa phần **đọc các entry còn tồn tại** bằng `LdapTemplate`. Nó **không phải** client RFC 4533 hay DirSync, và **không tự phát hiện delete**. Giả định:

- Spring LDAP context base: `dc=example,dc=org`.
- Phạm vi được duyệt: `ou=people`, bao gồm OU con bằng `SUBTREE`.
- Server test hỗ trợ `modifyTimestamp`, filter `>=` và cung cấp `entryUUID`; trên AD phải thay cách lấy stable ID cho `objectGUID` phù hợp.
- `readLdapTemplate` sử dụng tài khoản chỉ đọc, TLS hợp lệ và attribute allowlist.

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.GreaterThanOrEqualsFilter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class TimestampDeltaReader {
    private static final DateTimeFormatter LDAP_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss'Z'")
                    .withZone(ZoneOffset.UTC);

    private final LdapTemplate readLdapTemplate;

    public record DirectoryRow(
            String objectId,
            String relativeDn,
            String uid,
            String mail,
            String modifiedAt
    ) {}

    public TimestampDeltaReader(LdapTemplate readLdapTemplate) {
        this.readLdapTemplate = readLdapTemplate;
    }

    public List<DirectoryRow> readSince(Instant inclusiveLowerBound) {
        // Chỉ nhận timestamp từ checkpoint đáng tin cậy,
        // không nhận filter string do người dùng gửi.
        String generalizedTime = LDAP_TIME.format(inclusiveLowerBound);

        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(new GreaterThanOrEqualsFilter(
                "modifyTimestamp", generalizedTime));

        LdapQuery search = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes(
                        "entryUUID", "uid", "mail", "modifyTimestamp")
                .filter(filter);

        ContextMapper<DirectoryRow> mapper = context -> {
            DirContextOperations entry = (DirContextOperations) context;
            return new DirectoryRow(
                    entry.getStringAttribute("entryUUID"),
                    entry.getDn().toString(),
                    entry.getStringAttribute("uid"),
                    entry.getStringAttribute("mail"),
                    entry.getStringAttribute("modifyTimestamp"));
        };

        return readLdapTemplate.search(search, mapper);
    }
}
```

**Giải thích và giới hạn:**

- `GreaterThanOrEqualsFilter` xây biểu thức so khớp thứ tự, không chèn raw filter. `generalizedTime` là chuỗi do ứng dụng tạo từ `Instant` đã kiểm soát.
- `entry.getDn()` cần được hiểu theo **quy ước DN tương đối của context/query Spring LDAP** đang sử dụng; không coi chuỗi đó tự động là DN đầy đủ có thể trao đổi giữa hệ thống.
- `entryUUID` là ví dụ stable ID chỉ dành cho server có cung cấp. Nếu thiếu ID, **không tự chuyển sang dùng `uid` hoặc DN rồi giả vờ rename đã được xử lý chính xác**.
- `modifyTimestamp` là operational attribute; phải được yêu cầu rõ và tài khoản LDAP có quyền đọc. Không mặc định nó xuất hiện trong query chỉ lấy user attributes.
- Ví dụ cố ý bỏ qua phân trang, size limit và cập nhật checkpoint để tập trung vào **cách truy vấn**, không phải chương trình sync production. Một triển khai thực tế phải bổ sung logic phân trang/limit, checkpoint transaction, retry/idempotency, kiểm soát số lượng và đối soát.

### Vì sao `ContextMapper` được dùng thay `AttributesMapper`?

`AttributesMapper` chỉ nhận tập thuộc tính để tạo DTO. Với sync, ứng dụng thường cần cả **DN hiện tại** của entry; `ContextMapper` có thể đọc thông tin context và tạo bản ghi chứa DN tương ứng. Khi cần DN đầy đủ, hãy chuẩn hóa dựa trên context base đã cấu hình và xác minh với directory đích; không ghép chuỗi DN bằng cách cắt dấu phẩy tùy tiện.

## 11. Client DirSync / LDAP Sync không chỉ là repository method

`LdapRepository.findBy...` và `LdapTemplate.search(...)` được thiết kế thuận tiện cho CRUD/search và ODM mapping. Chúng **không tự biến một query method thành cơ chế change feed có cursor**.

Có thể chia hệ thống thành hai lớp:

```text
                  SyncCoordinator
                         │
            ┌────────────┴────────────┐
            │                         │
     ChangeFeedReader           CheckpointStore
      (server-specific)               │
            │                         ▼
            │                  cookie/watermark
            ▼
      ChangeBatch
     + next cursor
            │
            ▼
   IdentityMapper / Projector
            │
            ▼
    Transactional target store
            │
            ▼
     Commit checkpoint
```

Các implementation của `ChangeFeedReader` có thể là:

- `LdapSyncReader`: dùng client LDAP có hỗ trợ RFC 4533 request/response control.
- `AdDirSyncReader`: dùng AD DirSync control, xử lý cookie và metadata theo AD.
- `ChangelogReader`: lấy các record từ changelog riêng của server.
- `TimestampPollingReader`: dùng `LdapTemplate.search` như phần 10, đồng thời chấp nhận các giới hạn đã mô tả.

Trong Java, cơ chế control có thể cần làm việc với **`javax.naming.ldap.LdapContext`**, `Control` và thông điệp BER hoặc SDK LDAP chuyên dụng. Vì các contract này **khác theo server**, không nên tự tạo một phương thức `repository.findChangedSince(cookie)` rồi xem nó là đồng bộ chuẩn cho tất cả LDAP directory.

Một interface ứng dụng có thể tách công việc một cách dễ kiểm thử:

```java
import java.util.List;

public interface ChangeFeedReader {
    ChangeBatch readNext(Checkpoint checkpoint);
}

public record Checkpoint(
        String sourceId,
        String scopeVersion,
        byte[] opaqueCookie,
        String timeWatermark
) {}

public record ChangeBatch(
        List<DirectoryChange> changes,
        byte[] nextCookie,
        boolean requiresReconciliation
) {}

public record DirectoryChange(
        String sourceObjectId,
        String currentDn,
        Kind kind
) {
    public enum Kind {
        UPSERT, DELETE, OUT_OF_SCOPE
    }
}
```

Đây là **API abstraction minh họa**, không phải một API Spring LDAP có sẵn. Trong code thật cần kiểm soát `byte[]` mutable khi lưu cookie, trạng thái transaction và thông tin thay đổi thuộc tính được lấy theo schema/ACL. Không truyền cookie tùy ý từ HTTP client và không gán cookie của nguồn A cho nguồn B.

## 12. Thiết kế checkpoint để không mất thay đổi

**Sai lầm nghiêm trọng:** nhận batch, lưu cookie mới, rồi mới upsert dữ liệu. Nếu process chết sau khi lưu cookie nhưng trước khi ghi dữ liệu, lần chạy sau bỏ qua batch chưa áp dụng.

Thiết kế đúng hơn:

```text
1. Đọc checkpoint C đã commit
2. Dùng C đọc một batch từ LDAP
3. Validate change records, scope và identity
4. Upsert/tombstone xuống DB đích (idempotent)
5. Lưu checkpoint C' sau khi áp dụng thành công
6. Commit cùng transaction của đích nếu có thể
7. Lặp tiếp; nếu lỗi, giữ C và replay batch khi resume
```

Nếu DB đích hỗ trợ transaction, ưu tiên **data changes + checkpoint cùng một transaction**. Với đích phân tán (DB + message broker + search index), không thể giả định có atomic transaction chung; cần **outbox/inbox**, event id, idempotency key, version kiểm soát hoặc cơ chế bù trừ.

### Ví dụ timeline crash

| Thời điểm | Tình huống | Quy tắc |
|---|---|---|
| T0 | Checkpoint C đã lưu | Có thể resume từ C |
| T1 | Nhận change A, B và cookie C' | Chưa được commit C' |
| T2 | Áp dụng A thành công, B lỗi | Không commit checkpoint; cần retry/bù trừ |
| T3 | Process restart từ C | A có thể xuất hiện lần nữa; xử lý **idempotent** |
| T4 | A và B đều áp dụng + checkpoint C' được commit | Có thể chuyển sang batch tiếp |

**At-least-once + idempotency** là mục tiêu thực tế phổ biến. **Exactly-once toàn tuyến** không tự được bảo đảm chỉ nhờ cookie; cần chứng minh thuộc tính của server, pipeline và lưu trữ đích.

### Những gì cần lưu cùng checkpoint

- Nguồn/endpoint hoặc danh tính logical source.
- Naming context/base DN, filter, scope và **version cấu hình đồng bộ**.
- Loại change mechanism (RFC 4533, DirSync, changelog, timestamp).
- Cookie/offset opaque và thông tin DC/server affinity nếu cơ chế yêu cầu.
- Thời gian nhận/commit, batch id, version triển khai, trạng thái bootstrap/reconcile.
- Lỗi cuối, số lần retry; metadata được bảo vệ, không chứa secret bind.

Khi **đổi base/filter/scope, server/DC hoặc version mapping**, hãy coi đó là một thay đổi đáng kể: xác minh tính hợp lệ của cookie và có thể cần bootstrap lại.

## 13. Xử lý add, modify, delete, rename và move

Đây là phần phân biệt hệ thống delta “chạy được” với hệ thống delta **đúng dữ liệu**.

### Add / modify

Khi nhận entry mới hoặc được sửa:

1. Dùng **stable object ID từ server** làm khóa upsert tại đích nếu có.
2. Cập nhật các thuộc tính nằm trong **allowlist và phạm vi được phép**.
3. Ghi lại DN hiện tại và metadata version/timestamp.
4. Không ghi đè giá trị mới bằng sự kiện cũ đến muộn; dùng quy tắc version/order phù hợp server.

Ví dụ: `entryUUID=E1001` có mail từ `a@example.org` đổi sang `b@example.org`. Đích upsert bản ghi có `sourceObjectId=E1001`, không tạo thêm user chỉ vì mail đã đổi.

### Rename / move trong phạm vi

```text
Trước: uid=u1001,ou=people,dc=example,dc=org
Sau:   uid=u1001,ou=staff,ou=people,dc=example,dc=org
```

Nếu stable ID không đổi, đích cập nhật `currentDn` theo sự kiện mới. Dùng DN làm primary key có thể gây **bản ghi “ma” ở DN cũ và bản ghi mới ở DN mới**.

### Move ra ngoài phạm vi

```text
Trước: uid=u1002,ou=people,dc=example,dc=org
Sau:   uid=u1002,ou=contractors,dc=example,dc=org
```

Ứng dụng chỉ được đồng bộ `ou=people`. Sau move, nguồn có thể không còn trả entry trong scope. Nếu change control **không phát sự kiện rời phạm vi**, client cần so sánh snapshot được xác minh đủ tin cậy hoặc dùng cơ chế khác để đánh dấu `OUT_OF_SCOPE`. Không tự mở rộng scope tới `ou=contractors` nếu chưa được ủy quyền.

### Delete

Một entry đã bị xóa không còn hiện diện trong search thông thường. Để nhận delete cần:

- Sync state/delete event theo RFC 4533 khi server hỗ trợ.
- Tombstone/deleted-object hoặc changelog theo chính sách của AD/server khác.
- Hoặc so sánh **full snapshot hoàn chỉnh** với tập đích đã lưu, trong phạm vi và quyền tương đương.

**Không xóa cứng ngay** chỉ vì entry không xuất hiện trong một lượt polling. Search có thể sai base, bị cắt bởi size/time limit, thiếu quyền, gặp referral hoặc lỗi phân trang. Với hệ thống nhạy cảm, có thể chuyển bản ghi sang trạng thái `pending_delete`, yêu cầu xác minh nhiều lần hoặc có thời gian giữ trước khi xóa thật.

## 14. Full reconciliation: lưới an toàn cho incremental sync

Một **đợt đối soát** đọc lại toàn bộ các entry còn tồn tại trong phạm vi đã duyệt và so sánh với trạng thái đích. Nó có thể bù cho các thiếu sót của polling, gap của changelog hoặc lỗi xử lý trước đó.

Quy trình đề xuất:

1. **Đóng băng định nghĩa scope:** endpoint, base, search scope, filter, attributes, ACL; gắn một `scopeVersion`.
2. **Scan đủ toàn bộ dữ liệu:** xử lý paging, size/time limit, referral, quyền và lỗi. Nếu không thể chứng minh đủ, đánh dấu run **incomplete**.
3. **Chuẩn hóa identity:** sử dụng stable ID, giữ mapping giữa object ID và DN hiện tại.
4. **So sánh với đích:** phân nhóm new, changed, unchanged, missing, duplicate/collision.
5. **Chỉ xử lý missing khi scan hoàn chỉnh:** cần xem xét rename/move, ACL và độ trễ nhân bản.
6. **Áp dụng thay đổi theo chính sách:** upsert/tombstone, ghi audit, không tự xóa hàng loạt.
7. **Khôi phục cursor:** dùng cơ chế do server hỗ trợ, có thể phải bootstrap new cookie trước khi chuyển lại delta.

Một full scan LDAP **không nhất thiết là snapshot atomic của toàn directory**. Trong lúc quét nhiều trang, dữ liệu có thể tiếp tục đổi; cần phối hợp với change feed/cookie hoặc lặp đối soát để hội tụ, không khẳng định một lần quét luôn phản ánh một thời điểm nhất quán tuyệt đối.

### Phân biệt “không thấy” và “đã xóa”

| Nguyên nhân không thấy entry | Có được đánh dấu DELETE ngay? |
|---|---|
| Server phát deletion event hợp lệ theo contract đã kiểm thử | Có thể chuyển `deleted` theo chính sách |
| Full scan đã hoàn chỉnh, cùng scope/ACL/identity | Có thể coi missing sau đối chiếu và bảo vệ bổ sung |
| LDAP search trả 0 vì sai base hoặc tài khoản bị đổi ACL | **Không** |
| Scan bị cắt bởi size/time limit | **Không** |
| Referral hoặc lỗi một trang | **Không** |
| Polling `modifyTimestamp` không trả entry | **Không** |
| Entry bị move ra scope mà chưa có sự kiện rõ | Cần phân biệt `out_of_scope` với delete |

## 15. Bảo mật, schema và giới hạn quyền khi đồng bộ

Một dịch vụ đồng bộ danh tính thường có khả năng đọc số lượng entry lớn, nên cần xem nó là thành phần **nhạy cảm**:

- **TLS:** dùng LDAPS/StartTLS, xác minh certificate chain và hostname, không fallback SIMPLE bind cleartext.
- **Least privilege:** tài khoản đồng bộ chỉ có quyền đọc các entry/attribute và change control được duyệt. DirSync có thể cần quyền đặc biệt; phê duyệt và đánh giá riêng vì một số quyền replication rộng hơn quyền search thông thường.
- **Attribute allowlist:** ví dụ `uid`, `cn`, `sn`, `mail`, stable ID và metadata cần thiết. Không mặc định đồng bộ `userPassword`, `unicodePwd`, `objectSid`, ACL hoặc thuộc tính nhạy cảm.
- **Filter an toàn:** dùng builder như `LdapQueryBuilder`, `EqualsFilter`, `GreaterThanOrEqualsFilter` và kiểm soát giá trị; không ghép raw filter từ input ngoài.
- **Phạm vi:** base DN và scope cố định theo hợp đồng nghiệp vụ. Cursor của scope A không được tái sử dụng bừa bãi cho scope B.
- **Phân quyền đích:** bản sao chỉ được phục vụ người dùng được phép, không vì service account LDAP đọc được mà mọi API cũng được trả dữ liệu.
- **Cookie/checkpoint:** dù không phải mật khẩu, chúng thể hiện trạng thái truy cập/offset nội bộ, cần bảo vệ và có cơ chế sao lưu theo yêu cầu hệ thống.
- **Audit và lưu giữ:** log số batch, count, mã lỗi, nguồn/đích, không log password hoặc toàn bộ thông tin cá nhân.

Trong Spring Data LDAP, các annotation như `@Entry`, `@Id Name` và `@Attribute` mô tả mapping ODM; chúng **không cấp quyền**. `@Id` giữ DN của entry nên có thể thay đổi khi rename/move. Nếu nguồn là Active Directory, phải xây mapping theo **schema AD thực tế**, không dùng mô hình `uid=...` chung cho mọi user.

## 16. Vận hành: metric, retry, backpressure và giới hạn tải

Nên theo dõi riêng các chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| `sync_lag_seconds` | Độ trễ giữa thay đổi nguồn và lúc đích áp dụng thành công, khi đo được đáng tin |
| `checkpoint_age_seconds` | Thời gian từ lần commit checkpoint cuối |
| Số event/entry mỗi batch | Phát hiện tăng đột biến, batch quá lớn |
| Số duplicate/replayed changes | Đánh giá retry và idempotency |
| Số delete/move/out-of-scope | Theo dõi thay đổi nguy hiểm hoặc khác thường |
| Số lỗi cookie invalid/gap | Cảnh báo cần reconciliation/bootstrap |
| LDAP search latency p95/p99 | Nhận diện tải LDAP hoặc pool/connect |
| Số trang, size/time limit, referral errors | Xác minh tính đầy đủ của scan |
| Reconciliation mismatch count | Đánh giá delta có hội tụ đúng không |
| Số lỗi ACL/TLS/schema | Phân biệt lỗi bảo mật và dữ liệu |

**Retry có giới hạn:** mạng chập chờn hoặc LDAP server timeout có thể dẫn tới retry, nhưng không nên liên tục poll nhanh hơn khi đang bị lỗi. Dùng exponential backoff với jitter theo chính sách vận hành, giới hạn concurrency và ngân sách kết nối/pool.

**Backpressure:** nếu đích xử lý chậm hơn nguồn, tăng queue không giới hạn có thể làm mất khả năng resume vì server hết retention. Cần cảnh báo sớm khi checkpoint age gần ngưỡng retention; có kế hoạch resync thay vì lặng lẽ bỏ batch.

**Không suy luận một batch = một LDAP request:** có thể có search, paged results, control response, truy vấn bổ sung để lấy thuộc tính hoặc retry. Đo operation thực tế ở client/server khi tối ưu.

## 17. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Polling không thấy user vừa bị xóa | Delete không còn entry để match `modifyTimestamp` | Dùng delete-capable feed hoặc full reconciliation |
| Rename tạo hai user ở đích | Dùng DN thay vì stable ID làm khóa | Mapping theo `entryUUID`/`objectGUID` phù hợp |
| Cursor bị server từ chối | Cookie hết hiệu lực, sai scope, server đổi trạng thái | Không tăng cookie thủ công; bootstrap/reconcile |
| AD switch DC rồi USN “lùi” | USN không phải counter toàn forest | Ràng buộc DC/invocation metadata hoặc chọn DirSync phù hợp |
| Kết quả scan ít bất thường | Size/time limit, ACL, paging/referral lỗi | Đánh dấu scan incomplete, tuyệt đối không mass-delete |
| Apply duplicate làm dữ liệu bị lùi | Thiếu version/order hoặc idempotency | Dùng stable ID + version và checkpoint atomic |
| Thay filter/base nhưng vẫn dùng cookie cũ | Cursor gắn với scope cũ | Tăng `scopeVersion`, xác nhận khả năng resume hoặc bootstrap |
| Đồng bộ được nhưng không đọc được `entryUUID` | Attribute vận hành/ACL hoặc server không hỗ trợ | Xác minh RootDSE/schema, thiết kế ID tương thích server |
| DirSync request bị từ chối | Thiếu quyền control/replication hoặc policy AD | Xác minh quyền được duyệt với admin, không dùng domain admin tùy tiện |
| Modify timestamp nhìn như “trễ” | Replication lag, clock skew, index/format khác | Overlap + đối soát; đo delay thực tế |
| Sync persist chết sau mất mạng | Chưa thiết kế reconnect/resume | Phát hiện disconnect, đánh giá cookie và restart an toàn |
| Đích thấy dữ liệu nhạy cảm | Attribute allowlist hoặc ACL sai | Thu hồi quyền/điều tra rò rỉ, lọc dữ liệu ngay từ nguồn |

Cần phân loại lỗi **transport/TLS**, **bind/authentication**, **authorization**, **LDAP control**, **scope/filter**, **schema** và **target storage**. Không gộp mọi lỗi vào “không có thay đổi”: như vậy hệ thống có thể giữ checkpoint sai hoặc hiểu nhầm người dùng đã bị xóa.

## 18. Kiểm thử tích hợp với directory

Unit test có thể kiểm tra mapper và thuật toán checkpoint, nhưng **mock `LdapTemplate` không chứng minh server hỗ trợ LDAP Sync/DirSync hoặc trả đúng sự kiện delete**. Cần một môi trường test phù hợp với **server và phiên bản thực tế**, tài khoản bind và ACL tương đương production.

| Ca thử | Thiết lập | Kỳ vọng |
|---|---|---|
| Bootstrap ban đầu | Đích trống, directory có `u1001` và `u1002` | Hai object được tạo theo stable ID |
| Add | Tạo `u1003` sau checkpoint | Đích thêm một bản ghi |
| Modify | Đổi `mail` của `u1001` | Cập nhật đúng object, không tạo trùng |
| Rename | Đổi RDN, stable ID không đổi | Cập nhật `currentDn`, không nhân đôi identity |
| Move trong scope | Di chuyển sang OU con được phép | Vẫn thuộc scope nếu searchScope phù hợp |
| Move ra scope | Chuyển tới OU ngoài phạm vi | Đánh dấu out-of-scope theo contract/reconcile |
| Delete | Xóa một entry test | Chỉ đánh dấu deleted khi có bằng chứng tin cậy |
| Thuộc tính bị thiếu | `mail` vắng mặt hoặc không được ACL cho đọc | Mapper và chính sách sync xử lý đúng |
| Cùng timestamp | Hai entry sửa trong cùng giây | Không bỏ sót vì dùng `>` thiếu overlap |
| Mất mạng | Đứt kết nối giữa batch | Retry từ checkpoint đã commit |
| Crash sau apply trước checkpoint | Dữ liệu lưu, cookie chưa lưu | Replay idempotent, không nhân đôi |
| Crash sau checkpoint giả định sai | Cookie lưu nhưng dữ liệu chưa ghi | Test phát hiện thiết kế không atomic |
| Cookie invalid | Server từ chối cookie cũ | Chuyển sang reconciliation/bootstrap |
| Changelog hết retention | Client offline quá lâu | Phát hiện gap, không báo sync thành công |
| Size limit/paging | Nhiều entry hơn giới hạn một trang | Scan không đầy đủ phải bị đánh dấu lỗi |
| ACL bị giảm | Tài khoản không còn đọc một nhánh | Không suy dữ liệu bị xóa |
| TLS certificate sai | Endpoint chứng chỉ không hợp lệ | Fail closed, checkpoint giữ nguyên |
| Thay scopeVersion | Đổi `ou=people` sang phạm vi khác | Không dùng cursor cũ nếu không tương thích |
| DC failover | Chuyển AD domain controller | Tuân theo cookie/USN semantics; reconcile nếu cần |

**Tiêu chí pass quan trọng:** sau nhiều vòng delta và ít nhất một lần full reconciliation, tập stable ID và thuộc tính được phép ở đích phải hội tụ về trạng thái nguồn trong phạm vi đã thống nhất. Với hệ thống eventual consistency, phải định nghĩa độ trễ chấp nhận và cách xác nhận trạng thái ổn định.

## 19. Bài tập thiết kế

Một công ty có hai directory:

- **OpenLDAP A:** dự kiến hỗ trợ LDAP Sync, chứa `dc=example,dc=org` và OU `people`.
- **Active Directory B:** có domain `corp.example.com`, user thường có RDN `CN=...`, đội vận hành cho biết có khả năng DirSync.
- Đích là cơ sở dữ liệu nội bộ cần `objectId`, `currentDn`, `displayName`, `mail` và trạng thái `active/deleted`. Đích chỉ được nhận thông tin nhân viên đã duyệt.

Hãy giải:

1. Cần hỏi RootDSE và người quản trị từng server những gì trước khi chọn cơ chế delta?
2. Tại sao không dùng chung một parser cookie giữa LDAP Sync và AD DirSync?
3. Với OpenLDAP A, `refreshOnly` và `refreshAndPersist` phù hợp hai kiểu vận hành nào? Nếu connection persist bị ngắt, xử lý ra sao?
4. Với AD B, vì sao dùng `uSNChanged` từ DC này làm watermark khi chuyển sang DC khác có thể gây sai lệch?
5. Nếu chỉ có polling `modifyTimestamp`, làm sao phát hiện delete và move ra khỏi OU?
6. Nếu batch chứa hai thay đổi, một đã apply nhưng thao tác thứ hai lỗi, khi nào được lưu cookie mới?
7. Khi một user đổi CN/OU, phải dùng trường nào để tránh bản ghi trùng ở đích?
8. Nếu scan bị cắt bởi size limit hoặc ACL thay đổi, có được tự đánh dấu mọi entry không xuất hiện là deleted không?
9. Phải cấp quyền và bảo vệ secret/cookie như thế nào để không biến đồng bộ thành kênh trích xuất toàn bộ danh tính?
10. Hãy đề xuất ít nhất năm ca kiểm thử chứng minh recovery, idempotency và correctness.

**Gợi ý đối chiếu:** khả năng control và naming context phải được xác nhận theo endpoint; LDAP Sync và DirSync có protocol riêng. Chỉ commit cursor sau khi áp dụng bền vững. Stable ID từ directory giúp liên kết qua rename, còn DN là vị trí có thể đổi. Polling theo timestamp không đủ để xử lý delete, cần feed phù hợp và full reconciliation. Khi scan incomplete hoặc cookie invalid, **không** tự xóa dữ liệu; phải điều tra và khôi phục từ nguồn tin cậy.

## 20. Checklist và tổng kết

Trước khi công bố chức năng đồng bộ tăng dần, đối chiếu:

- [ ] Đã xác định **source of truth**, chiều đồng bộ và phạm vi DN/base/filter/attribute được phép.
- [ ] Đã kiểm tra **RootDSE, supportedControl, quyền bind**, version và khả năng change tracking thật của server.
- [ ] Đã chọn phương án đúng: **LDAP Sync / AD DirSync / changelog / notification + reconcile / timestamp fallback**.
- [ ] Đã có **bootstrap** ban đầu, checkpoint/cookie phù hợp nguồn, `scopeVersion` và khả năng nhận biết cursor invalid/gap.
- [ ] Có khóa object ổn định, tách khỏi DN có thể đổi khi rename/move.
- [ ] Xử lý **add, modify, delete, rename, move trong/ngoài scope** theo sự kiện hoặc reconciliation đáng tin.
- [ ] **Data changes và checkpoint** được commit có kiểm soát; retry idempotent, không giả định exactly-once.
- [ ] Polling timestamp có overlap, kiểm tra pagination/limit/ACL và **không được xem là delete-complete**.
- [ ] Có kế hoạch **full reconciliation**, chỉ xét missing khi scan đầy đủ và đúng quyền.
- [ ] Kết nối dùng TLS có xác minh server; tài khoản change feed/LDAP chỉ có quyền tối thiểu, dữ liệu đích được phân quyền.
- [ ] Có metric lag/checkpoint age/gap, alert retention, retry/backpressure và test mất kết nối.
- [ ] Đã kiểm thử tích hợp trực tiếp với directory/version đích, bao gồm cookie invalid, rename, delete, failover, ACL và crash.

### Tài liệu chuẩn để đọc tiếp

- [RFC 4533 — LDAP Content Synchronization Operation](https://www.rfc-editor.org/rfc/rfc4533).
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515).

**Kết luận:** đồng bộ tăng dần trong Spring Data LDAP không bắt đầu từ một filter thời gian mà bắt đầu từ **khả năng cụ thể của LDAP server và hợp đồng dữ liệu**. Dùng LDAP Sync, DirSync hoặc changelog khi thực sự được hỗ trợ; chỉ dùng `modifyTimestamp` như một fallback có giới hạn và đối soát. Thiết kế checkpoint/cookie bền vững, stable ID, xử lý delete/rename và kiểm thử lỗi sẽ giúp hệ thống Java đồng bộ an toàn, có thể phục hồi và đúng phạm vi được phép.
