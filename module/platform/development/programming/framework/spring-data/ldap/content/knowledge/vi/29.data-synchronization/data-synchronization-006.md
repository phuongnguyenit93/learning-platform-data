# Giới hạn khi suy luận thay đổi từ `modifyTimestamp` trong đồng bộ dữ liệu LDAP

## 1. Bài toán: đồng bộ tăng dần mà không đọc lại toàn bộ directory

Trong **Spring Data LDAP**, một ứng dụng Java có thể dùng `LdapRepository` và `LdapTemplate` để truy vấn các entry LDAP, ánh xạ thuộc tính và DN thành đối tượng Java rồi lưu bản sao vào cơ sở dữ liệu nội bộ, chỉ mục tìm kiếm hoặc hệ thống IAM. Directory thường có cây phân cấp như:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   └── uid=bob
└── ou=groups
    ├── cn=reviewers
    └── cn=developers
~~~

Khi số lượng entry tăng, một job đồng bộ định kỳ thường muốn hỏi: **“Kể từ lần chạy trước, những entry nào đã thay đổi?”**

Cách tiếp cận dễ nghĩ tới là đọc thuộc tính vận hành `modifyTimestamp`, lưu lại một mốc thời gian (*watermark*), rồi tìm các entry có `modifyTimestamp` từ mốc đó trở đi:

~~~text
(&(objectClass=inetOrgPerson)(modifyTimestamp>=20261126090000Z))
~~~

Đây là kỹ thuật *timestamp-based polling*. Nó có thể giảm chi phí đọc trong một số môi trường, nhưng **không tương đương một change log** và **không mặc định bảo đảm đồng bộ chính xác**. Nếu ứng dụng dựa vào nó như bằng chứng rằng “mọi thay đổi đều đã được nhận”, có thể bỏ sót việc xóa, chuyển OU, cập nhật nhóm hoặc thay đổi chưa xuất hiện trên replica đang đọc.

**Mục tiêu bài học:**

- Hiểu `modifyTimestamp` được định nghĩa thế nào trong LDAP schema và phải đọc nó ra sao.
- Chỉ ra các trường hợp polling theo thời gian có thể bỏ sót hoặc lặp sự kiện.
- Thiết kế watermark với **cận bao gồm (`>=`)**, vùng chồng lấn, idempotency, checkpoint và đối soát.
- Áp dụng `LdapTemplate` để xây dựng filter an toàn, đọc thuộc tính vận hành và xử lý kết quả theo DN/định danh ổn định.
- Biết khi nào phải chuyển sang **LDAP Content Synchronization**, changelog hoặc cơ chế vendor-specific thay vì tiếp tục suy luận từ timestamp.

> **Nguyên tắc:** `modifyTimestamp` là **thuộc tính trạng thái của entry hiện có**; nó không phải chuỗi sự kiện bất biến hay một con trỏ thứ tự toàn cục cho mọi thay đổi trong directory.

## 2. `modifyTimestamp` thực sự cho biết điều gì?

RFC 4512 định nghĩa `modifyTimestamp` là một **operational attribute** phản ánh thời điểm entry được sửa gần nhất thông qua giao thức, ví dụ thao tác Modify. Trong schema chuẩn, nó có những đặc điểm:

| Đặc tính | Ý nghĩa |
| --- | --- |
| Tên | `modifyTimestamp` |
| Attribute type OID | `2.5.18.2` |
| Cú pháp | `GeneralizedTime` — syntax OID `1.3.6.1.4.1.1466.115.121.1.24` |
| Equality matching rule | `generalizedTimeMatch` |
| Ordering matching rule | `generalizedTimeOrderingMatch` |
| Số giá trị | `SINGLE-VALUE` |
| Khả năng sửa bởi client | `NO-USER-MODIFICATION` |
| Phân loại | `USAGE directoryOperation`, thuộc tính vận hành |
| Giá trị | Thời điểm sửa entry gần nhất mà server ghi nhận |

Ví dụ giá trị:

~~~text
modifyTimestamp: 20261126153045Z
~~~

Nghĩa là **26/11/2026 lúc 15:30:45 UTC**, nếu server dùng biểu diễn UTC có giây như trên. `GeneralizedTime` còn có các biểu diễn hợp lệ khác theo RFC 4517, chẳng hạn có phần thập phân hoặc offset; ứng dụng nên dùng parser phù hợp thay vì so sánh chuỗi bằng tay.

Cần hiểu rõ phạm vi của khẳng định:

1. **Thời điểm của entry**, không phải thời điểm mỗi thuộc tính thay đổi riêng.
2. **Giá trị hiện tại**: hai lần Modify xảy ra giữa hai lần polling có thể chỉ để lại timestamp của lần cuối.
3. **Không ghi loại thao tác**: không biết đây là thay email, đổi tên, cập nhật nhóm hay ghi một thuộc tính khác.
4. **Không ghi chi tiết thay đổi**: chỉ từ timestamp không biết giá trị cũ là gì.
5. **Không thay thế lịch sử xóa**: entry bị xóa thường không còn trong kết quả Search thông thường.
6. **Không bảo đảm được hỗ trợ và quan sát như nhau** ở mọi LDAP server, replication topology hoặc quyền ACL.

Theo mô hình LDAP, `modifyTimestamp` xuất hiện trên các entry đã được sửa qua giao thức; **không nên giả định entry mới tạo luôn có `modifyTimestamp`**. `createTimestamp` là một operational attribute khác ghi thời điểm tạo entry nếu server duy trì nó. Các server có thể điền cả hai cho một entry mới theo triển khai của chúng, nhưng job đồng bộ cần kiểm tra thay vì dựa vào giả định này.

### 2.1. `modifyTimestamp` khác `createTimestamp` và `modifiersName`

| Thuộc tính | Thể hiện điều gì? | Giới hạn |
| --- | --- | --- |
| `createTimestamp` | Thời điểm entry được tạo | Không đủ cho các lần sửa tiếp theo; có thể không được trả |
| `modifyTimestamp` | Thời điểm entry được sửa gần nhất | Không biểu diễn entry đã bị xóa hoặc toàn bộ các lần sửa |
| `creatorsName` | DN danh tính tạo entry, nếu server cung cấp | Không phải khóa định danh ổn định cho event |
| `modifiersName` | DN của danh tính sửa entry gần nhất, nếu có | Không giải thích thuộc tính nào đổi; có thể bị ACL giới hạn |

Các thuộc tính này có ích để **đối soát dữ liệu, tra cứu vận hành hoặc lọc ứng viên**, nhưng không thể thay thế hệ thống audit log nếu yêu cầu truy nguyên từng thao tác.

## 3. Đọc operational attributes: đừng nhầm “không được trả” với “không tồn tại”

Khác với những user attributes như `uid`, `cn`, `mail`, operational attributes **không được trả về mặc định** trong nhiều Search. RFC 4512 quy định client cần yêu cầu chúng theo tên hoặc cơ chế được LDAP hỗ trợ.

Ví dụ kiểm tra một entry bằng tài khoản dịch vụ thực tế:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=app-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" \
  dn uid cn createTimestamp modifyTimestamp modifiersName
~~~

Nếu công cụ/server hỗ trợ bộ chọn thuộc tính operational, cũng có thể kiểm tra với `+`:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=app-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" "*" "+"
~~~

Giải thích:

- `*` yêu cầu **user attributes** thông thường.
- `+` yêu cầu **operational attributes** theo cơ chế LDAP hỗ trợ.
- `1.1` có thể dùng để không yêu cầu thuộc tính nào.
- `dn` là danh tính entry được client hiển thị, không phải một thuộc tính người dùng phải có trong `Attributes`.
- `-W` nhập mật khẩu tương tác; không ghi secret vào command line hoặc log CI.
- LDAPS phải dùng **CA/truststore được xác minh và hostname certificate phù hợp**.

Nếu `modifyTimestamp` không có trong kết quả, phải xét: entry chưa có giá trị theo đặc tính server, thuộc tính không được yêu cầu, account không có quyền đọc, server không duy trì thuộc tính, hoặc ứng dụng đang đọc một replica/endpoint khác. **Không được mặc định thời điểm sửa là `1970-01-01` hay thời điểm chạy job** chỉ để bỏ qua trường hợp thiếu.

### 3.1. Kiểm tra schema và server hỗ trợ lọc theo thời gian

Server cần có **ordering matching rule** phù hợp để xử lý filter `modifyTimestamp>=...`. Với schema chuẩn, `modifyTimestamp` có `generalizedTimeOrderingMatch`, nhưng:

- ACL có thể ảnh hưởng việc đọc hoặc dùng attribute trong Search.
- Directory vendor có thể không cho phép kiểu lọc, tối ưu index hoặc truy vấn này trong cấu hình thực tế.
- Thời gian Search và giới hạn số kết quả vẫn chịu chính sách server.
- Một yêu cầu qua nhiều naming context/referral có thể không có cùng hành vi như một Search ở một server duy nhất.

Nên kiểm thử **trên directory mục tiêu** với các entry có timestamp đã biết, bao gồm trường hợp đúng tại ranh giới.

## 4. `>=` không phải “thay đổi sau thời điểm” tuyệt đối

LDAP filter hỗ trợ toán tử **greater-than-or-equal** (`>=`) cho các thuộc tính có ordering matching rule. Nó không có toán tử `>` độc lập trong cú pháp filter chuẩn.

~~~text
(modifyTimestamp>=20261126090000Z)
~~~

Điều này đưa ra hai vấn đề thường bị bỏ qua:

1. **Ranh giới bao gồm**: một entry có timestamp đúng bằng `20261126090000Z` sẽ xuất hiện lại trong lần poll tiếp theo.
2. **Nhiều entry cùng timestamp**: timestamp không nhất thiết là khóa duy nhất hoặc thứ tự tổng cho các thay đổi.

Ví dụ:

| Entry | Giá trị `modifyTimestamp` |
| --- | --- |
| `uid=alice,ou=people,...` | `20261126090000Z` |
| `uid=bob,ou=people,...` | `20261126090000Z` |
| `uid=carol,ou=people,...` | `20261126090000Z` |

Nếu job chỉ lấy Alice, rồi tăng watermark lên `20261126090001Z` hoặc dùng điều kiện “lớn hơn ranh giới” giả định, Bob và Carol có thể bị bỏ sót.

**Giải pháp cơ bản:** dùng `>=`, chấp nhận đọc lại entry ở ranh giới và xử lý **idempotent** tại downstream. Tuy nhiên, dùng `>=` **chỉ giải quyết một loại lỗi biên**, không tự khắc phục các thay đổi đến muộn do replication hay các lần sửa ở thời điểm cũ hơn watermark.

### 4.1. Không dùng timestamp làm số thứ tự sự kiện

Một `modifyTimestamp` như `20261126090000Z` biểu diễn thời gian, không phải sequence number, transaction ID hay cursor được server cam kết. Hai thao tác có thể có cùng giá trị hiển thị tùy độ chính xác. Bởi vậy:

~~~text
Không nên:
  eventId = modifyTimestamp
  checkpoint = max(modifyTimestamp)
  nextQuery = only timestamp strictly greater than checkpoint
~~~

Ngay cả checkpoint ghép `(timestamp, DN)` cũng **chưa** tạo ra một change stream chính xác nếu:

- DN có thể đổi sau rename.
- Thứ tự Search không được server bảo đảm.
- Entry bị xóa không còn trả về.
- Một thay đổi tới replica muộn mang timestamp cũ hơn checkpoint đã lưu.

## 5. Những thay đổi mà polling bằng timestamp có thể bỏ sót

### 5.1. Delete: entry biến mất, không còn gì để tìm

Giả sử job đã đồng bộ Alice vào bảng nội bộ:

~~~text
Local index:
  uid=alice -> Alice Nguyen
~~~

Sau đó quản trị viên xóa entry Alice trong directory. Lần Search:

~~~text
(modifyTimestamp>=20261126090000Z)
~~~

không tự trả “sự kiện Alice đã bị xóa”, vì entry Alice đã không còn nằm trong tập kết quả hiện tại.

**Hệ quả:** bản sao có thể giữ một user đã bị xóa. Nếu dùng cache này để cấp quyền, hệ thống có thể giữ quyền không còn hợp lệ.

Để phát hiện xóa, cần một trong các cơ chế:

- Change feed/sync control hỗ trợ **delete state**.
- Changelog hoặc tombstone do server/vendor cung cấp, nếu có và được cấu hình đúng.
- Đối soát định kỳ **toàn bộ tập entry trong phạm vi quyền quản lý** và xác minh những mục không còn tồn tại.
- Một luồng sự kiện đáng tin cậy từ hệ thống chịu trách nhiệm vòng đời tài khoản.

Không được “xóa tất cả entry không xuất hiện trong một lần poll tăng dần”: **incremental Search vốn chỉ trả một tập con**, không phải toàn bộ trạng thái directory.

### 5.2. Rename và chuyển OU: DN không phải ID bất biến

Giả sử:

~~~text
Trước: uid=alice,ou=people,dc=example,dc=org
Sau:   uid=alice,ou=contractors,dc=example,dc=org
~~~

LDAP ModifyDN đổi **vị trí/tên** entry. Nếu đồng bộ theo DN như khóa chính:

- Khi entry nằm ở DN mới, job có thể coi nó là **một user mới**.
- Bản ghi DN cũ có thể vẫn nằm trong cache, vì không có event delete rõ ràng.
- Nếu Search chỉ có base `ou=people`, entry đã chuyển sang `ou=contractors` có thể **hoàn toàn biến mất** khỏi phạm vi Search.

Không nên coi `modifyTimestamp` chắc chắn được cập nhật như mong đợi sau mọi ModifyDN trên mọi server/replica. Cần kiểm tra hành vi thực tế của directory và cơ chế phát hiện đối tượng **rời khỏi tập dữ liệu**.

Khi server cung cấp một định danh tương đối ổn định qua rename, chẳng hạn `entryUUID` trong một số directory LDAP hoặc `objectGUID` trong Active Directory, có thể dùng định danh đó làm khóa bản sao. **Vẫn phải xử lý biến cố ra khỏi scope và xóa**; ID ổn định không tự sinh sự kiện thay đổi.

### 5.3. Sửa nhóm không đồng nghĩa sửa member

Ví dụ:

~~~text
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: groupOfUniqueNames
uniqueMember: uid=alice,ou=people,dc=example,dc=org
~~~

Khi thêm Bob vào thuộc tính `uniqueMember`, entry thay đổi trực tiếp là **nhóm `cn=reviewers`**, không nhất thiết là Alice hoặc Bob.

Nếu job chỉ Search `ou=people` với:

~~~text
(&(objectClass=inetOrgPerson)(modifyTimestamp>=...))
~~~

nó có thể **không nhìn thấy bất kỳ thay đổi nào**, dù quyền ứng dụng dựa trên membership đã thay đổi.

Đồng bộ quyền nhóm thường cần đọc các **group entries** (`member`, `uniqueMember`, hoặc kiểu vendor khác), cập nhật đồ thị quan hệ, xử lý nested groups và có cơ chế invalidation cache. Thuộc tính ngược như `memberOf` cũng không được bảo đảm trên mọi directory và không tự phản ánh mọi thay đổi group theo cùng ngữ nghĩa.

### 5.4. Một entry bị sửa nhiều lần giữa hai poll

Giả sử:

~~~text
09:00:00  mail của Alice là a@example.org
09:00:05  đổi mail thành temp@example.org
09:00:08  đổi mail thành new@example.org
09:01:00  job đồng bộ chạy
~~~

Job có thể đọc **chỉ trạng thái cuối** `new@example.org`. `modifyTimestamp` không chứa lịch sử hai lần cập nhật, người sửa, nội dung cũ hay lý do nghiệp vụ.

Điều này thường đủ cho mục tiêu **đồng bộ ảnh chụp trạng thái cuối** nhưng **không đủ** cho:

- Hệ thống audit phải lưu mọi thao tác.
- Tái phát sự kiện có thứ tự để gửi notification.
- Điều tra ai đã thay đổi thuộc tính nào.
- Hệ thống downstream cần thực hiện một hành động cho **mỗi lần thay đổi**, kể cả đã bị ghi đè.

### 5.5. Entry mới và `createTimestamp`

RFC 4512 mô tả `createTimestamp` là thời điểm tạo entry, còn `modifyTimestamp` mô tả lần sửa gần nhất. Không được mặc định mọi entry vừa Add đã có `modifyTimestamp` giống `createTimestamp`.

Nếu job chỉ lọc:

~~~text
(modifyTimestamp>=20261126090000Z)
~~~

một entry mới chưa có `modifyTimestamp` theo cách server lưu trữ có thể bị bỏ qua. Trong trường hợp directory hỗ trợ cả hai, có thể xét điều kiện **tạo hoặc sửa**:

~~~text
(|(createTimestamp>=20261126090000Z)
  (modifyTimestamp>=20261126090000Z))
~~~

Dấu xuống dòng ở ví dụ trên chỉ để dễ đọc: filter thực gửi tới server là **một chuỗi LDAP filter hợp lệ**. Cũng phải xác minh quyền đọc/search và ngữ nghĩa schema của `createTimestamp`.

### 5.6. Replication trễ, failover và thời gian máy chủ

Một topology gồm node A và replica B:

~~~mermaid
sequenceDiagram
    participant Writer as LDAP node A
    participant Replica as LDAP replica B
    participant Job as Đồng bộ từ B
    Writer->>Writer: 09:00:03 sửa Alice
    Job->>Replica: 09:00:10 poll thay đổi từ 09:00:05
    Replica-->>Job: Chưa thấy Alice
    Job->>Job: Lưu checkpoint 09:00:10
    Writer-->>Replica: 09:00:20 replicate thay đổi của Alice
    Job->>Replica: 09:01 poll từ 09:00:10
    Replica-->>Job: Alice có timestamp 09:00:03, không khớp
~~~

Trong ví dụ, job đã đẩy checkpoint vượt thời điểm sửa của entry **trước khi replica có thay đổi đó**. Một polling thuần túy có thể bỏ sót Alice vĩnh viễn nếu không có vùng nhìn lại hoặc đối soát.

Các nguồn lệch khác gồm:

- Replica có trạng thái khác nhau ở thời điểm Search.
- Failover làm job chuyển sang node chưa bắt kịp hoặc có cách đánh timestamp khác.
- Đồng hồ server và client có chênh lệch.
- Việc hiển thị/độ chính xác timestamp có thể khác nhau giữa phiên bản directory.
- Search có thể kéo dài khi entry tiếp tục được cập nhật.

**Không có bảo đảm tổng quát** rằng mọi timestamp giữa các node đều cung cấp một thứ tự toàn cục đơn điệu theo thứ tự replicate. Muốn đồng bộ có cam kết mạnh cần một **change cursor/change sequence/sync cookie** có ý nghĩa rõ từ server, không chỉ so UTC string.

## 6. Một bảng quyết định: `modifyTimestamp` trả lời được câu hỏi nào?

| Câu hỏi | Có thể trả lời chỉ bằng `modifyTimestamp`? | Giải thích |
| --- | --- | --- |
| Entry hiện tại này được sửa lần cuối vào khi nào? | **Có, nếu server duy trì và cho đọc** | Đó là ý nghĩa của thuộc tính |
| Có entry nào **đang tồn tại** và có timestamp từ mốc X? | **Có điều kiện** | Cần Search filter và ACL phù hợp |
| Từ mốc X có những entry mới nào? | **Không chắc** | Cần xem `createTimestamp` và hành vi Add của server |
| Những entry nào đã bị xóa? | **Không** | Entry đã xóa không còn trong Search thường |
| Người dùng nào bị chuyển OU? | **Không đầy đủ** | DN thay đổi, có thể ra khỏi scope |
| Thành viên của nhóm đã đổi chưa? | **Chỉ khi kiểm tra entry nhóm phù hợp** | Timestamp của person không đủ |
| Thuộc tính nào đã đổi? | **Không** | Chỉ cho biết thời điểm cuối |
| Có bao nhiêu lần sửa trong khoảng? | **Không** | Các lần sửa trung gian không còn được giữ trong attribute |
| Hai thay đổi trên hai node có đúng thứ tự nào? | **Không bảo đảm** | Timestamp không phải sequence toàn cục |
| Có thể tái dựng audit trail? | **Không** | Cần audit/change log đúng chức năng |

## 7. Xây dựng truy vấn ứng viên an toàn bằng `LdapTemplate`

### 7.1. Search với `>=` và explicit operational attributes

Spring LDAP cung cấp **`LdapQueryBuilder`**, hỗ trợ `.gte(String)` để biểu diễn `>=` với escaping phù hợp. Có thể kết hợp `AndFilter`, `OrFilter` và `GreaterThanOrEqualsFilter` để biểu diễn:

~~~text
(&(objectClass=inetOrgPerson)
  (|(createTimestamp>=CUT_OFF)
    (modifyTimestamp>=CUT_OFF)))
~~~

Dưới đây là ví dụ Java trong một ứng dụng Spring Boot có `LdapTemplate` đã cấu hình `ContextSource.base=dc=example,dc=org`:

~~~java
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
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class LdapChangeCandidateReader {

    private static final DateTimeFormatter UTC_SECONDS =
        DateTimeFormatter.ofPattern("uuuuMMddHHmmss'Z'")
            .withZone(ZoneOffset.UTC);

    private final LdapTemplate ldapTemplate;

    public LdapChangeCandidateReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record Candidate(
        String relativeDn,
        String stableId,
        String uid,
        String createdAtRaw,
        String modifiedAtRaw
    ) {}

    public List<Candidate> findSince(Instant lowerInclusive) {
        String boundary = UTC_SECONDS.format(lowerInclusive);

        OrFilter changes = new OrFilter()
            .or(new GreaterThanOrEqualsFilter(
                "createTimestamp", boundary))
            .or(new GreaterThanOrEqualsFilter(
                "modifyTimestamp", boundary));

        AndFilter filter = new AndFilter()
            .and(new EqualsFilter("objectClass", "inetOrgPerson"))
            .and(changes);

        LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes(
                "uid", "createTimestamp", "modifyTimestamp", "entryUUID"
            )
            .timeLimit(5000)
            // Chỉ dùng như giới hạn an toàn trong ví dụ.
            // Production cần paging + kiểm soát tính đầy đủ.
            .countLimit(500)
            .filter(filter);

        return ldapTemplate.search(
            ldapQuery,
            (ContextMapper<Candidate>) context -> {
                DirContextOperations entry =
                    (DirContextOperations) context;

                return new Candidate(
                    entry.getDn().toString(),
                    entry.getStringAttribute("entryUUID"),
                    entry.getStringAttribute("uid"),
                    entry.getStringAttribute("createTimestamp"),
                    entry.getStringAttribute("modifyTimestamp")
                );
            }
        );
    }
}
~~~

**Cách hiểu chính xác ví dụ:**

- `createTimestamp` và `modifyTimestamp` được **yêu cầu rõ ràng** vì là operational attributes; không giả định chúng tự có khi `attributes("*")`.
- `entryUUID` là một định danh thường gặp trên một số server LDAP, nhưng **không mặc định có ở mọi directory**. Active Directory có thể dùng `objectGUID`; adapter phải chọn theo server thực tế.
- `relativeDn` không phải khóa bất biến qua rename. Tên DN được trả trong ngữ cảnh Spring LDAP cần kiểm tra theo base của `ContextSource`.
- `GreaterThanOrEqualsFilter` và các filter builder giúp mã hóa giá trị assertion. **Không nối input chưa tin cậy** thành filter.
- `.countLimit(500)` là **giới hạn minh họa**, **không được** dùng kết quả bị giới hạn như bằng chứng đã xử lý hết. Job sản xuất phải biết số trang và trạng thái đầy đủ hoặc đánh dấu batch **chưa hoàn tất**.
- `.timeLimit(5000)` là giới hạn tìm kiếm ở tầng JNDI; vẫn phải cấu hình connect/read timeout và xử lý lỗi server.
- Một server có thể không hỗ trợ/không cấp quyền cho `entryUUID` hoặc operational attributes; nên khởi động bằng smoke test capability và điều chỉnh adapter.
- Lưu ý Search này chỉ lấy entry **đang nằm trong nhánh `ou=people`**, không thể phát hiện tự nó một entry đã chuyển đi hoặc bị xóa.

**Ví dụ còn là candidate reader, chưa phải một hệ đồng bộ hoàn chỉnh.** Nó không quyết định checkpoint, retry, xóa, phân trang an toàn hay phản ứng với schema/ACL thay đổi.

### 7.2. Kiểm tra filter bằng `ldapsearch`

Với một mốc cố định đã biết:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=app-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(|(createTimestamp>=20261126090000Z)(modifyTimestamp>=20261126090000Z)))" \
  dn uid createTimestamp modifyTimestamp entryUUID
~~~

Ở đây dấu `>=` được hiểu bởi **matching rule của server**, không phải Java so sánh lexicographic hai string. Với `GeneralizedTime`, các biểu diễn có timezone hoặc độ chính xác khác nhau có thể không sắp thứ tự đúng khi so trực tiếp dưới dạng chuỗi.

Khi phát triển, tạo các entry có thời điểm đã biết (hoặc sửa chúng trong directory test) để kiểm tra đúng ranh giới bằng cùng tài khoản bind. Nếu server không cho filter theo thuộc tính, cần chọn cơ chế hỗ trợ chính thức, không lạm dụng tải hết directory rồi lọc bằng Java khi dữ liệu lớn.

## 8. Vì sao `createTimestamp OR modifyTimestamp` vẫn chưa đủ?

Kết hợp hai timestamp chỉ giúp giảm nguy cơ **bỏ sót entry mới hiện còn tồn tại**. Nó không giải quyết:

- **Delete và rename ra khỏi search base**.
- **Nhiều thay đổi trên cùng entry** giữa hai poll.
- **Giới hạn số kết quả**, kết quả bị cắt hoặc trang bị bỏ qua.
- **Replication trễ hơn vùng nhìn lại**.
- **Đồng hồ/timestamp không đồng nhất** giữa các node.
- **ACL thay đổi** khiến một phần directory không còn được nhìn thấy.
- **Khóa bản sao là DN** và không xử lý rename.
- **Entry không còn mang objectClass** trước đây dùng để lọc: nó có thể rời khỏi tập kết quả mà không tạo event delete trên truy vấn này.
- **Thuộc tính đổi nhưng timestamp không được cập nhật như dự kiến** trong một cơ chế nội bộ/vendor-specific.

Vì vậy, đừng mô tả kết quả của query trên là “mọi thay đổi từ mốc X”. Cách gọi chính xác là **“các entry hiện còn truy cập được, thỏa filter và có timestamp ở vùng thời gian quan tâm”**.

## 9. Thiết kế watermark có chồng lấn và checkpoint an toàn hơn

Một cơ chế polling thực dụng có thể **giảm rủi ro mất dữ liệu** bằng cách nhìn lại một khoảng thời gian, xử lý lặp được và chỉ xác nhận mốc sau khi hoàn tất.

### 9.1. Ví dụ chọn khoảng thời gian

Giả sử:

~~~text
Checkpoint đã commit: 10:00:00 UTC
Overlap (nhìn lại):  5 phút
Settle lag:          2 phút
Giờ job bắt đầu:     10:10:00 UTC

lowerInclusive = 09:55:00 UTC
upperExclusive = 10:08:00 UTC
~~~

Lần poll mới tìm **ứng viên từ 09:55**, nhưng chỉ xử lý những entry có thời điểm hiệu lực trong **vùng chưa quá mới** (trước 10:08). Các entry có timestamp từ 10:08 trở đi sẽ để lần poll sau xử lý.

Sơ đồ:

~~~text
09:55               10:00               10:08     10:10
  |-------------------|--------------------|---------|
   overlap đọc lại      vùng cần hoàn tất    chờ ổn định
                   checkpoint cũ          giờ hiện tại
~~~

**Không có con số overlap/settle lag đúng cho mọi directory.** Nó cần dựa trên độ trễ replication được đo, số node, mức clock skew, thời gian quét, giới hạn tải và SLA. Nếu mất đồng bộ kéo dài hơn overlap, chỉ một overlap cố định **không bảo đảm** đầy đủ.

### 9.2. Thuật toán polling có kiểm soát

~~~mermaid
flowchart TD
    A["Đọc checkpoint đã commit"] --> B["Tính lower=checkpoint-overlap và upper=now-settle"]
    B --> C["Search create/modifyTimestamp >= lower"]
    C --> D{"Đọc đủ tất cả trang và không lỗi?"}
    D -->|Không| E["Không cập nhật checkpoint; retry và cảnh báo"]
    D -->|Có| F["Lọc ứng viên theo upper và parse timestamp"]
    F --> G["Upsert bản sao theo stable ID + trạng thái"]
    G --> H{"Downstream đã lưu bền vững?"}
    H -->|Không| E
    H -->|Có| I["Commit checkpoint/tiến độ"]
    I --> J["Đối soát định kỳ và phát hiện delete/move"]
~~~

Các bước:

1. **Lấy checkpoint đã commit** ở kho bền vững, không chỉ biến RAM của một pod.
2. Tính `lowerInclusive = checkpoint - overlap`; trong một lần poll, dùng cùng mốc từ đầu đến cuối.
3. Chọn một **upper fence** thận trọng cho batch; không coi thời gian client là thời gian server chính xác tuyệt đối.
4. Search ứng viên theo `createTimestamp` hoặc `modifyTimestamp` với `>= lowerInclusive`. Với tập lớn, dùng cơ chế phân trang được server hỗ trợ.
5. Parse timestamp đúng chuẩn, xử lý **boundary inclusion** và entry thiếu thuộc tính theo chính sách.
6. **Upsert idempotent** vào bản sao bằng một khóa định danh ổn định nếu có; giữ cả DN hiện tại làm thuộc tính có thể thay đổi.
7. Chỉ khi tất cả trang và downstream thành công mới commit checkpoint. Nếu Search bị size/time limit, cookie sai hoặc trang không đọc hết, **không advance** checkpoint.
8. Thực hiện **đối soát toàn phần** hoặc sử dụng change feed có delete state để phát hiện xóa, rename ra scope và thay đổi mà polling bỏ lỡ.

Nếu checkpoint và bản ghi downstream cùng ở một database, có thể commit chúng trong **một transaction nội bộ**. Nếu chúng ở hai hệ thống khác nhau, cần cơ chế idempotency, transactional outbox hoặc xử lý retry có đối soát; không tự coi hai bước là một transaction phân tán.

### 9.3. Ví dụ Java tính cửa sổ theo UTC

~~~java
import java.time.Duration;
import java.time.Instant;

public record PollWindow(
    Instant lowerInclusive,
    Instant upperExclusive
) {
    public static PollWindow from(
            Instant committedCheckpoint,
            Instant now,
            Duration overlap,
            Duration settleLag) {

        if (committedCheckpoint == null || now == null
                || overlap.isNegative() || settleLag.isNegative()) {
            throw new IllegalArgumentException("Polling window không hợp lệ");
        }

        Instant lower = committedCheckpoint.minus(overlap);
        Instant upper = now.minus(settleLag);

        if (!upper.isAfter(lower)) {
            throw new IllegalArgumentException(
                "Cửa sổ không hợp lệ: upper phải lớn hơn lower");
        }

        return new PollWindow(lower, upper);
    }
}
~~~

Đây là code **tính khung thời gian**, không tự thực hiện đồng bộ. Khi đem vào production, cần xét overflow nếu checkpoint ở cực trị, tính nhất quán giữa các lần chạy đồng thời và chính sách retry nếu giờ client thay đổi.

### 9.4. Xử lý dữ liệu bị lặp

Ví dụ Alice được trả lại hai lần do overlap:

~~~text
Poll 1: id=abc, DN=uid=alice,..., mail=a@example.org, t=10:00:00
Poll 2: id=abc, DN=uid=alice,..., mail=a@example.org, t=10:00:00
~~~

Cách xử lý đúng là **upsert** cùng trạng thái hoặc kiểm tra version của bản sao, không gửi hai thông báo “Alice đã thay đổi” nếu nghiệp vụ chỉ cần một notification cho một thay đổi. Nếu cần exactly-once event semantics, `modifyTimestamp` đơn lẻ không thể bảo đảm vì nhiều lần sửa trong cùng độ phân giải thời gian có thể có cùng timestamp.

Một **idempotency key** có thể chứa `(stableEntryId, observedVersion)` khi server cung cấp revision phù hợp. Nhưng `(DN, modifyTimestamp)` chỉ là **heuristic**: DN đổi theo rename, timestamp có thể trùng, và không phải unique event ID. Nếu không có version đáng tin, dùng **so sánh nội dung/snapshot hash** cho mục tiêu hội tụ trạng thái cuối và chấp nhận rằng không tái tạo được mọi event trung gian.

## 10. Paging và giới hạn Search làm watermark nguy hiểm hơn

Khi một Search trả hơn số entry server cho phép, LDAP server có thể áp dụng **size limit**, time limit, hoặc chỉ trả kết quả một phần kèm lỗi. Dù job có đọc được 100 entry, **không được coi chúng là tất cả ứng viên**.

### 10.1. Paged Results Control không phải snapshot

LDAP Simple Paged Results Control (RFC 2696) dùng **cookie** để tiếp tục Search. Đây là cách quét kết quả nhiều trang nhưng không mặc định giữ nguyên snapshot của directory trong khi đang cập nhật.

Các rủi ro:

- Entry mới được tạo/sửa hoặc di chuyển giữa các trang.
- Cookie gắn với kết nối/trạng thái server; chuyển node/failover có thể làm cookie không hợp lệ.
- Một số server không hỗ trợ paging hoặc giới hạn session paging đồng thời.
- Page size và tổng số kết quả **không phải** guarantee rằng mọi entry chỉ xuất hiện đúng một lần.
- Không có sort ổn định thì không thể suy từ thứ tự kết quả rằng đã duyệt xong mọi timestamp.

Khi dùng Spring LDAP, có thể áp dụng `PagedResultsControlExchangeDirContextProcessor` trong các phiên bản hỗ trợ và `SingleContextSource.doWithSingleContext(...)` để giữ cùng connection trong chuỗi trang. Tuy nhiên, **giữ connection không biến polling thành snapshot transaction**.

### 10.2. Checkpoint phải phụ thuộc vào trạng thái hoàn tất

**Sai:**

~~~text
read page 1 -> lưu checkpoint = max(modifyTimestamp(page 1))
read page 2 -> timeout
restart từ checkpoint vừa lưu
~~~

Vì không có sort đảm bảo và các entry cùng timestamp, những entry chưa được đọc có thể nằm **trước** checkpoint vừa lưu theo giá trị timestamp.

**Tốt hơn:** lưu tiến độ trang như trạng thái tạm nếu cơ chế cookie hỗ trợ/được server cho phép; chỉ nâng **watermark nghiệp vụ đã commit** sau khi toàn bộ batch hoàn tất và dữ liệu downstream đã được ghi an toàn. Nếu lần chạy bị hỏng, bắt đầu lại từ lowerInclusive đã commit và xử lý lặp có kiểm soát.

Đừng dùng page cookie như token có thể lưu dài hạn để chuyển tự do giữa các LDAP server. Nếu cơ chế yêu cầu resume bền vững, chọn loại change feed/cookie có bảo đảm riêng từ server.

## 11. Chọn khóa định danh để giữ bản sao nhất quán

DN là **vị trí entry**, không phải mã nhận dạng bất biến. Khi rename:

~~~text
id=abc, DN trước = uid=alice,ou=people,dc=example,dc=org
id=abc, DN sau   = uid=alice,ou=contractors,dc=example,dc=org
~~~

Nếu nguồn cung cấp ID ổn định:

- Ghi bản sao dưới khóa ID đó.
- Xem DN là một thuộc tính cập nhật được.
- Nếu entry đổi sang OU ngoài search base, vẫn cần **tín hiệu rời scope** hoặc đối soát để biết phải loại khỏi tập dữ liệu nội bộ.
- Không tự coi `entryUUID` và `objectGUID` có cùng kiểu Java/byte order/khả năng truy vấn. Ánh xạ theo định nghĩa của directory đang dùng.
- Nếu ID không được expose, phải xác định giải pháp nghiệp vụ có thể chấp nhận rename và delete hay không; **không** biến `uid` thành ID bất biến theo giả định.

Một mô hình lưu cục bộ:

| Cột | Nội dung |
| --- | --- |
| `sourceDirectory` | Tên directory/partition đã được chuẩn hóa |
| `sourceStableId` | ID server đáng tin cậy nếu có |
| `currentDn` | DN hiện tại, có thể thay đổi |
| `uid`, `cn`, `mail` | Thuộc tính nghiệp vụ cần đồng bộ |
| `observedModifyTimestamp` | Metadata để theo dõi, không phải change ID |
| `lastSeenAt` | Thời điểm job quan sát entry |
| `reconciliationState` | Active, nghi ngờ thiếu, xác minh đã biến mất, ... |

`lastSeenAt` do **client đồng bộ** quản lý và `modifyTimestamp` do **directory** quản lý. Hai giá trị phục vụ mục đích khác nhau và không được đổi chỗ cho nhau.

## 12. Đối soát toàn phần: lớp bảo vệ cần thiết khi chỉ có timestamp

Dù polling tăng dần hoạt động trong nhiều ngày, vẫn nên có một cơ chế phát hiện sự khác biệt với **trạng thái hiện tại** của directory.

Ví dụ định kỳ:

1. Quét toàn bộ entry trong phạm vi được phép với paging/control phù hợp, thu **stable ID, DN, thuộc tính cần thiết**.
2. Đối chiếu với bản sao nội bộ theo stable ID.
3. Với một ID không thấy, **không xóa ngay**. Xác minh Search hoàn chỉnh, ACL, topology, size/time limit, lỗi node và tình huống move out-of-scope.
4. Chỉ đánh dấu đã xóa/rời scope sau bước xác minh theo chính sách.
5. Cập nhật DN nếu ID còn tồn tại nhưng DN thay đổi.
6. Đối soát riêng **nhóm và thuộc tính membership** nếu quyền phụ thuộc nhóm.
7. Ghi số entry đọc được, số entry thiếu, tỷ lệ lỗi và thời điểm scan.

### Vì sao không xóa theo “không thấy trong một lần quét”?

Quá trình đọc có thể không đầy đủ vì:

- Bind identity mất quyền đọc một OU.
- Một node directory lỗi hoặc referral không được xử lý.
- Server trả kết quả bị cắt do limit.
- Paging bị timeout, một trang chưa hoàn tất.
- Replication khác nhau giữa các node.
- Search filter theo `objectClass`/attribute loại bỏ một số entry ngoài dự kiến.

Bởi vậy, **absence trong kết quả không tự chứng minh deletion**. Với bản sao phục vụ authorization, nên có chính sách fail-safe khi nguồn không chắc chắn, thay vì tiếp tục cho quyền dựa trên dữ liệu cũ vô thời hạn.

## 13. Khi nào nên dùng LDAP Sync/DirSync/changelog thay vì `modifyTimestamp`?

Các cơ chế chuyên dụng có thể cung cấp **change state** hoặc cursor phía server, thường phù hợp hơn nếu cần phát hiện xóa, rename hoặc đồng bộ liên tục.

| Cơ chế | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| `modifyTimestamp` polling | Quét các entry hiện tại có thời gian sửa/tạo phù hợp | Không có event delete/history/cursor; cần overlap & reconciliation |
| **RFC 4533 LDAP Content Synchronization** | Sync Request/State/Done controls, `syncCookie`, trạng thái add/modify/delete/present | Server hỗ trợ, phạm vi, cookie và refresh yêu cầu |
| **Changelog/Retro Changelog của server** | Lưu một phần lịch sử thay đổi nếu được cấu hình | Schema, retention, thứ tự, quyền truy cập, khả năng replay |
| **Microsoft AD DirSync** | Cơ chế thay đổi chuyên biệt của AD dùng cookie/control | Quyền, partition, schema, các hạn chế/cách xử lý delete của AD |
| **Hệ thống IAM/SCIM/event feed** | Nguồn sự kiện nghiệp vụ với ID/cursor được thiết kế riêng | Độ tin cậy, SLA, idempotency, chính sách và phạm vi dữ liệu |
| **Full reconciliation định kỳ** | So sánh snapshot trạng thái hiện tại | Chi phí, completeness, cách xác minh absence |

Theo RFC 4533, LDAP Content Synchronization hỗ trợ các trạng thái như `add`, `modify`, `delete`, `present` và cookie để tiếp tục phiên đồng bộ. Đây là **một cơ chế riêng**, không phải tính năng tự sinh chỉ từ thuộc tính `modifyTimestamp`.

### 13.1. Sync cookie khác mốc thời gian

- **Timestamp** diễn tả một thời điểm; client phải tự suy luận dữ liệu nào đã qua thời điểm đó.
- **Sync cookie** là token trạng thái do server phát hành cho cơ chế đồng bộ, thường **opaque** và có ngữ nghĩa riêng với server/partition.
- Khi cookie không còn hợp lệ hoặc server yêu cầu refresh lại, client cần **làm mới trạng thái** theo đặc tả; không tự tăng timestamp rồi bỏ qua lỗi.
- Không dùng cookie của RFC 2696 Paged Results thay thế sync cookie của RFC 4533; đây là **hai control khác nhau**.

### 13.2. Đọc `supportedControl` trước khi chọn kiến trúc

Root DSE có thể công bố control mà server hỗ trợ:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -b "" -s base "(objectClass=*)" supportedControl
~~~

OID Sync Request Control của RFC 4533 là `1.3.6.1.4.1.4203.1.9.1.1`. Tuy nhiên, sự xuất hiện của OID trong `supportedControl` **chưa chứng minh** service account có quyền dùng nó, server duy trì lịch sử đủ lâu, hay cookie được bảo toàn qua failover. Cần kiểm thử bằng kết nối, quyền và topology thực tế.

## 14. Kiểm thử các tình huống dễ bỏ sót

Một suite kiểm thử tốt cần **thực sự thao tác với directory nhúng/container** thay vì chỉ mock repository.

| Test case | Trạng thái ban đầu | Thao tác | Kỳ vọng |
| --- | --- | --- | --- |
| Update đơn giản | Có Alice | Sửa `mail` | Poll nhận entry hiện tại và cập nhật bản sao |
| Tạo mới | Chưa có Carol | Add Carol | Job không bỏ sót dù `modifyTimestamp` lúc Add khác `createTimestamp` |
| Trùng timestamp | Alice và Bob cùng mốc | Sửa cả hai trong cùng giây | `>=` + idempotency xử lý cả hai |
| Thay đổi liên tiếp | Alice đổi `mail` hai lần | Poll sau thay đổi | Có trạng thái cuối, **không** kỳ vọng có đủ hai event |
| Delete | Bob đã được sync | Xóa Bob | Timestamp poll không phát hiện trực tiếp; reconciliation/change feed phải xử lý |
| Rename trong scope | Alice đổi RDN | ModifyDN | Update DN theo stable ID, không nhân đôi |
| Move ra khỏi scope | Alice chuyển sang OU khác | ModifyDN | Quét `ou=people` không nhìn thấy; xử lý rời scope |
| Group membership | Reviewers có Alice | Thêm Bob vào `uniqueMember` | Poll person không đủ; phải poll/sync group |
| Replica lag | Node A vừa sửa, node B chưa thấy | Poll B, sau đó replication | Không mất update chỉ vì checkpoint vượt timestamp |
| Search size limit | Có nhiều entry hơn cap | Giới hạn kết quả | Batch không được đánh dấu hoàn tất |
| Paging gián đoạn | Cookie/page giữa bị lỗi | Timeout/restart | Checkpoint không bị đẩy tới trạng thái dở dang |
| ACL thay đổi | Job mất quyền đọc một OU | Scan lại | Không hiểu toàn bộ OU đã bị xóa |
| Clock skew | Client/server lệch giờ | Poll với upper fence | Chỉ bảo đảm theo chính sách đã kiểm thử, có giám sát |
| Failover | Chuyển từ LDAP A sang B | Poll tiếp | Phát hiện sai lệch và có phương án refresh/reconciliation |

### 14.1. Test cho cận `>=`

Giả sử fixture/test directory cho phép quan sát hai entry có cùng `modifyTimestamp` tại độ phân giải giây. Kiểm tra:

~~~text
Checkpoint = 20261126090000Z
Query      = (modifyTimestamp>=20261126090000Z)

Cần giữ:
  uid=alice, modifyTimestamp=20261126090000Z
  uid=bob,   modifyTimestamp=20261126090000Z
~~~

Nếu server tự cấp timestamp và test không thể gán giá trị operational tùy ý, hãy thực hiện các Modify gần nhau rồi quan sát timestamp thật, hoặc tách một **unit test thuật toán checkpoint** khỏi **integration test server**. Không yêu cầu client trực tiếp ghi `modifyTimestamp`, vì thuộc tính này có `NO-USER-MODIFICATION`.

### 14.2. Test ranh giới replication bằng mô phỏng

Đối với unit test chiến lược polling, mô phỏng tình huống:

~~~text
Đã commit checkpoint: 10:00
Replica chưa có thay đổi Alice lúc 09:58
Poll lúc 10:10 từ checkpoint-overlap=09:55
Replica nhận Alice trước poll kế tiếp
Poll kế tiếp từ checkpoint mới-overlap=10:03
~~~

Nếu Alice chỉ xuất hiện lúc 10:12 với `modifyTimestamp=09:58`, polling **vẫn bỏ sót**. Đây là bằng chứng rằng overlap 5 phút chỉ **giảm** rủi ro chứ không thể đưa ra cam kết tuyệt đối nếu replication bị trễ quá lâu.

Khi yêu cầu đúng tuyệt đối, cần chọn một cơ chế có sync state/cursor hoặc reconciliation đủ mạnh theo nhu cầu nghiệp vụ.

### 14.3. Kiểm thử xử lý lỗi downstream

Dù LDAP trả kết quả đầy đủ, việc lưu vào database/queue có thể thất bại:

1. Giả lập lỗi database ngay sau khi đã ghi một phần ứng viên.
2. Xác minh **checkpoint chưa advance**.
3. Chạy lại batch với cùng cửa sổ thời gian.
4. Chứng minh upsert không tạo trùng user hoặc notification không cần thiết.
5. Kiểm tra log/cảnh báo và số lần retry được giới hạn.

Không log toàn bộ nội dung LDAP entry, mật khẩu bind hoặc raw cookie để debug; chỉ cần metadata theo chính sách vận hành.

## 15. Quan sát và cảnh báo trong production

Một job đồng bộ tốt phải biết **mình đã đọc được bao nhiêu và có chắc đã đọc đủ không**.

Các chỉ số hữu ích:

- `last_successful_checkpoint` và thời gian kể từ lần commit cuối.
- `poll_started_at`, `poll_finished_at`, `batch_duration`.
- Số entry được đọc, số entry upsert, số entry được skip do vượt upper fence.
- Số trang, lỗi paging, server size/time limit, referral và lỗi ACL.
- Tỷ lệ entry thiếu `createTimestamp`/`modifyTimestamp` hoặc stable ID.
- Độ trễ quan sát thay đổi thực tế từ các node và chênh lệch so với SLO.
- Số record khác nhau khi full reconciliation và tỷ lệ “nghi ngờ đã xóa”.
- Số lần failover, retry, lỗi certificate/bind và trạng thái health của LDAP source.

Nếu job gặp các trường hợp sau, nên **dừng advance checkpoint và cảnh báo**:

- Không đọc đủ tất cả trang hoặc kết quả bị cắt.
- Thời gian parser không nhận được theo schema đã xác minh.
- Số lượng entry bất thường giảm đột ngột do lỗi ACL/endpoint.
- Replica bị trễ hơn giới hạn an toàn đã đặt.
- Có nhiều thay đổi về topology, base DN hoặc quyền mà chưa được kiểm tra.
- Không commit được kết quả downstream một cách bền vững.

## 16. Bảo mật và phân quyền cho job đồng bộ

- Dùng **LDAPS hoặc StartTLS** có xác minh certificate, không gửi bind password dưới LDAP plaintext trên mạng không tin cậy.
- Tài khoản dịch vụ chỉ cần quyền **search/read** trên OU và attribute cần đồng bộ; tránh cấp quyền write/admin chỉ vì job cần `modifyTimestamp`.
- Operational attributes như `modifyTimestamp`, `createTimestamp`, `entryUUID` có thể cần quyền đọc riêng.
- Chỉ đồng bộ dữ liệu cá nhân thực sự cần: `uid`, `cn`, `mail` hoặc nhóm theo nhu cầu; không mặc định tải `userPassword`, ảnh hay certificate.
- Dùng `LdapQueryBuilder` hoặc các `Filter` của Spring LDAP để mã hóa giá trị, không nối raw input thành filter.
- Nếu bản sao phục vụ **authorization**, khi sync thất bại phải có chính sách fail-safe, TTL và quy tắc thu hồi phù hợp; không cho phép quyền cũ kéo dài vô thời hạn.
- Quản lý checkpoint/cookie và nhật ký vận hành theo quyền truy cập phù hợp; những giá trị này có thể tiết lộ cấu trúc directory hoặc trạng thái hạ tầng.
- Thử nghiệm delete/move/group change phải chạy trên **LDAP test directory**, không chạy trên production bằng tài khoản quản trị.

## 17. Câu hỏi tự kiểm tra

1. Vì sao `modifyTimestamp` không phải event ID hoặc change sequence number?
2. Theo RFC 4512, `modifyTimestamp` là user attribute hay operational attribute? Khi nào nó được trả về?
3. Vì sao một entry mới có thể cần được phát hiện qua `createTimestamp`?
4. Trong filter LDAP, vì sao thường dùng `>=` thay vì `>`? Điều này ảnh hưởng checkpoint thế nào?
5. Khi Alice và Bob có cùng timestamp, một job dùng watermark thuần số giây có thể bỏ sót ai?
6. Khi xóa entry Alice, vì sao `(modifyTimestamp>=X)` không tự trả một sự kiện delete?
7. Khi Alice chuyển từ `ou=people` sang `ou=contractors`, vì sao đồng bộ theo DN có nguy cơ nhân đôi hoặc bỏ sót?
8. Một thao tác thêm Bob vào `uniqueMember` cập nhật entry nào? Job chỉ quét person có đủ không?
9. Vì sao hai lần sửa `mail` trong cùng một phút có thể chỉ tạo một trạng thái quan sát được?
10. Hãy mô tả tình huống replica B nhận thay đổi trễ với timestamp nhỏ hơn checkpoint.
11. Vùng overlap và settle lag giúp điều gì? Vì sao chúng không đảm bảo chính xác tuyệt đối?
12. Tại sao `countLimit(500)` không được dùng để kết luận “đã đồng bộ hết” khi query trả 500 entry?
13. Vì sao cookie Simple Paged Results không tương đương sync cookie của RFC 4533?
14. Khi nào nên dùng LDAP Content Synchronization hoặc vendor changelog thay vì timestamp polling?
15. Vì sao checkpoint chỉ được commit sau khi toàn bộ batch và downstream đã hoàn tất?
16. Nếu full scan không nhìn thấy một OU do ACL bị thay đổi, tại sao không nên xóa ngay các local record tương ứng?
17. Nếu directory có `entryUUID`/`objectGUID`, dùng nó cải thiện xử lý rename như thế nào? Còn giới hạn nào?
18. Một ứng dụng dùng cache group cho quyền admin phải phản ứng ra sao nếu LDAP tạm ngừng hoạt động?
19. Hãy đề xuất test phân biệt kết quả hợp lệ không có thay đổi với Search thất bại vì size/time limit.
20. Nếu cần lưu lịch sử **mọi lần thay đổi thuộc tính**, tại sao không thể chỉ dùng `modifyTimestamp` và polling?

## 18. Tổng kết

**`modifyTimestamp` cho biết lần sửa gần nhất của một LDAP entry đang tồn tại**, khi server duy trì và cho phép truy cập thuộc tính đó. Nó **không** cho biết entry nào đã bị xóa, không chứa lịch sử thay đổi, không tự phản ánh tác động lên các entry liên quan, và không bảo đảm một thứ tự thay đổi toàn cục qua replica.

Đối với đồng bộ tăng dần trong Spring Data LDAP, có thể dùng `LdapTemplate` với filter `>=` trên `createTimestamp`/`modifyTimestamp` để tìm **ứng viên thay đổi**, nhưng phải đi cùng **đọc đủ kết quả, checkpoint bền vững, idempotency, overlap, xử lý lỗi và full reconciliation**. Những biện pháp này giúp tăng khả năng hội tụ trạng thái, **không** biến timestamp polling thành change feed chính xác tuyệt đối.

Nếu yêu cầu nghiệp vụ đòi hỏi phát hiện xóa/rename nhất quán, xử lý liên tục hoặc lưu lịch sử thao tác, cần cân nhắc **LDAP Content Synchronization (RFC 4533)**, DirSync/changelog của server hoặc một nguồn sự kiện được thiết kế cho mục đích đó. Thiết kế đúng bắt đầu từ việc xác định rõ mức bảo đảm mà dữ liệu LDAP và cơ chế đồng bộ thực sự cung cấp.

### Tài liệu tham khảo

- [RFC 4512 — LDAP Directory Information Models: operational attributes](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4517 — LDAP Syntaxes and Matching Rules: Generalized Time](https://www.rfc-editor.org/rfc/rfc4517).
- [RFC 4511 — LDAPv3 Protocol: Search and controls](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4533 — LDAP Content Synchronization Operation](https://www.rfc-editor.org/rfc/rfc4533).
- [RFC 2696 — Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696).
- [RFC 4530 — entryUUID LDAP Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530).
- [Spring LDAP Reference — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html).
- [Spring LDAP Reference — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
