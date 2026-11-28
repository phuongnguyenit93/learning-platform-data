# Xử lý lỗi từng entry, thử lại và tiếp tục từ điểm kiểm tra

## 1. Vì sao một entry lỗi không nên làm mất cả batch đồng bộ?

Trong **Spring Data LDAP**, ứng dụng thường đọc các entry từ directory bằng `LdapRepository` hoặc `LdapTemplate`, ánh xạ DN và attributes thành object Java, rồi ghi bản sao vào database, search index hoặc một hệ thống IAM. Khi đồng bộ số lượng lớn entry, lỗi có thể xuất hiện do dữ liệu sai schema, ACL, kết nối chập chờn, entry bị rename/xóa giữa lúc quét hoặc downstream tạm thời không hoạt động.

Ví dụ một batch có 1.000 entry:

~~~text
Entry 001 ... 120: xử lý thành công
Entry 121: lỗi chuyển đổi employeeNumber
Entry 122 ... 1000: vẫn có thể xử lý bình thường
~~~

Nếu job dừng toàn bộ tại entry 121 và lần sau luôn bắt đầu lại từ đầu, hệ thống lãng phí tài nguyên và có thể liên tục gặp lại cùng một lỗi. Ngược lại, nếu job bỏ qua entry lỗi rồi đẩy checkpoint qua mốc đó, dữ liệu có thể bị mất đồng bộ vĩnh viễn.

Bài học này trình bày cách thiết kế **xử lý lỗi theo từng entry**, retry có kiểm soát, lưu tiến độ bền vững và resume sau restart. Mục tiêu là đạt khả năng **hội tụ trạng thái** với cơ chế xử lý lặp an toàn, đồng thời giữ lại những lỗi cần con người hoặc quy trình sửa chữa.

Sau bài này, người học có thể:

- Phân biệt lỗi của một entry, lỗi của một trang Search và lỗi toàn bộ nguồn LDAP.
- Phân loại lỗi tạm thời, lỗi dữ liệu/quyền không thể tự retry và kết quả ghi chưa xác định.
- Lưu tiến độ từng entry và checkpoint batch theo cách có thể khôi phục.
- Thiết kế retry với exponential backoff, jitter, giới hạn số lần và deadline.
- Xử lý entry lỗi bằng quarantine/dead-letter có thể phát lại.
- Bảo đảm upsert idempotent, không tạo bản ghi hoặc sự kiện trùng do retry.
- Tiếp tục sau restart mà không bỏ qua entry chưa xử lý.
- Kiểm thử lỗi một phần, lỗi paging, mất response và lỗi downstream.

> **Nguyên tắc:** Chỉ tiến checkpoint khi mọi công việc trước ranh giới đó đã được xử lý thành công hoặc đã được lưu vào một trạng thái lỗi bền vững có thể phát lại theo chính sách. Không lấy timestamp lớn nhất của entry thành công làm checkpoint một cách tùy tiện.

## 2. Phân biệt lỗi ở ba phạm vi

Không phải lỗi nào trong một lần đồng bộ cũng có cùng phạm vi ảnh hưởng.

| Phạm vi | Ví dụ | Phản ứng |
| --- | --- | --- |
| **Entry-level** | Một entry thiếu attribute bắt buộc, DN biến mất giữa lúc xử lý, dữ liệu không parse được | Ghi nhận lỗi cho entry đó; các entry độc lập khác có thể tiếp tục |
| **Page/batch-level** | Paging cookie không hợp lệ, Search bị size/time limit, một trang không được đọc hết | Không đánh dấu scan hoàn tất; resume/re-scan từ cửa sổ an toàn |
| **Source/system-level** | LDAP mất kết nối diện rộng, bind thất bại, certificate hết hạn, database đích không hoạt động | Dừng hoặc giảm tải batch; retry theo policy của hệ thống, giữ checkpoint cũ |

Một lỗi đọc `mail` của Alice không nhất thiết cản trở đồng bộ Bob. Nhưng nếu chính Search enumeration bị đứt giữa trang, job không biết còn entry nào chưa được phát hiện. Đây là lỗi phạm vi lớn hơn và không được xử lý như một entry đơn lẻ.

### 2.1. Tách khâu khám phá entry khỏi khâu áp dụng dữ liệu

Một thiết kế hữu ích chia luồng thành:

~~~text
LDAP scan / discovery
   |
   v
Danh sách candidate: stable ID + DN + source version
   |
   v
Durable batch manifest
   |
   +--> Entry A --> fetch/map --> apply --> SUCCESS
   |
   +--> Entry B --> fetch/map --> RETRY_WAIT
   |
   +--> Entry C --> fetch/map --> QUARANTINED
   |
   +--> Entry D --> fetch/map --> SUCCESS
   |
   v
Kiểm tra batch completion
   |
   v
Commit checkpoint
~~~

Khâu discovery có trách nhiệm xác định đầy đủ tập candidate trong phạm vi và cửa sổ quét. Khâu xử lý từng entry chịu trách nhiệm lấy dữ liệu, chuyển đổi và ghi downstream.

Nếu mapper trong quá trình Search ném exception khiến toàn bộ enumeration dừng, job không thể giả định đã khám phá đủ candidate. Có thể giảm rủi ro bằng cách mapper discovery chỉ lấy thông tin định danh tối thiểu, sau đó fetch/map chi tiết từng DN riêng biệt. Nếu ngay cả việc lấy DN hoặc stable ID cũng lỗi, cần đánh dấu scan chưa hoàn tất hoặc ghi một lỗi discovery có thể truy vết; không được âm thầm bỏ qua.

## 3. Thiết kế trạng thái bền vững cho từng entry

Một job chỉ giữ danh sách entry đã xử lý trong RAM sẽ mất tiến độ khi process restart. Hãy lưu trạng thái từng candidate trong một kho bền vững (thường là database ứng dụng).

### 3.1. Các trạng thái đề xuất

| Trạng thái | Ý nghĩa | Có được tính là hoàn tất batch? |
| --- | --- | --- |
| `DISCOVERED` | Candidate đã được ghi vào manifest | Không |
| `PENDING` | Sẵn sàng xử lý | Không |
| `IN_PROGRESS` | Worker đang xử lý, có lease | Không |
| `RETRY_WAIT` | Lỗi tạm thời, có thời điểm thử lại | Không |
| `SUCCEEDED` | Dữ liệu đích đã được ghi bền vững | Có |
| `QUARANTINED` | Lỗi không tự khắc phục; payload/metadata đã được lưu để xử lý lại | Chỉ khi chính sách batch cho phép hoàn tất với lỗi được lưu bền vững |
| `SKIPPED_BY_POLICY` | Entry được loại theo quy tắc đã được phê duyệt | Chỉ khi quy tắc và lý do được lưu |
| `FAILED_FINAL` | Đã hết retry hoặc lỗi không thể tự khắc phục | Không, trừ khi batch policy định nghĩa rõ việc chấp nhận lỗi này |

Không gộp `QUARANTINED` với `SUCCEEDED`. Một batch có thể được phép tiến checkpoint sau khi entry lỗi đã được ghi vào dead-letter queue có thể phát lại, nhưng trạng thái dữ liệu vẫn **chưa đồng bộ thành công**. Dashboard và báo cáo phải thể hiện sự khác biệt đó.

### 3.2. Dữ liệu cần lưu cho mỗi entry

| Trường | Mục đích |
| --- | --- |
| `runId` | Batch/scan đang xử lý |
| `sourceId` | Định danh directory hoặc partition |
| `stableEntryId` | `entryUUID`, `objectGUID` hoặc khóa ổn định theo hợp đồng |
| `currentDn` | DN được quan sát trong lần scan |
| `sourceVersion` | Timestamp/revision quan sát được, nếu có |
| `status` | Trạng thái xử lý |
| `attemptCount` | Số lần xử lý đã thử |
| `nextAttemptAt` | Thời điểm được phép retry |
| `leaseOwner`, `leaseUntil` | Worker đang sở hữu entry và hạn lease |
| `lastErrorCode` | Mã lỗi đã chuẩn hóa |
| `lastErrorAt` | Thời điểm lỗi gần nhất |
| `completedAt` | Thời điểm xử lý thành công hoặc kết thúc theo policy |
| `payloadHash` | Hash trạng thái cần đồng bộ để phát hiện nội dung thay đổi |
| `updatedAt` | Thời điểm record tiến độ được cập nhật |

Không lưu bind password, token, toàn bộ entry nhạy cảm hoặc raw exception chứa thông tin bí mật vào progress table. Nếu cần lưu payload để replay, áp dụng mã hóa, giới hạn quyền và retention.

### 3.3. Java model minh họa

~~~java
import java.time.Instant;
import java.util.UUID;

public record EntryWorkItem(
    UUID runId,
    String sourceId,
    String stableEntryId,
    String currentDn,
    String sourceVersion,
    int attemptCount,
    EntryWorkStatus status,
    Instant nextAttemptAt
) {}

public enum EntryWorkStatus {
    DISCOVERED,
    PENDING,
    IN_PROGRESS,
    RETRY_WAIT,
    SUCCEEDED,
    QUARANTINED,
    SKIPPED_BY_POLICY,
    FAILED_FINAL
}
~~~

Đây là model ứng dụng minh họa; stable ID và source version phụ thuộc directory. Nếu directory không có `entryUUID` hoặc `objectGUID`, DN có thể được dùng làm fallback key nhưng phải ghi nhận hạn chế: rename có thể tạo candidate mới và cần reconciliation để ghép nối.

## 4. Lấy candidate từ LDAP bằng Spring LDAP

### 4.1. Discovery chỉ đọc định danh cần thiết

Ví dụ `ContextSource.base=dc=example,dc=org`, entry nằm trong `ou=people`, server hỗ trợ `entryUUID` và `modifyTimestamp`:

~~~java
import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public record SyncCandidate(
    Name dn,
    String stableId,
    String modifyTimestamp
) {}

public final class LdapCandidateReader {

    private final LdapTemplate ldapTemplate;

    public LdapCandidateReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<SyncCandidate> discover() {
        LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("entryUUID", "modifyTimestamp")
            .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
            ldapQuery,
            (ContextMapper<SyncCandidate>) context -> {
                DirContextOperations entry =
                    (DirContextOperations) context;

                return new SyncCandidate(
                    entry.getDn(),
                    entry.getStringAttribute("entryUUID"),
                    entry.getStringAttribute("modifyTimestamp")
                );
            }
        );
    }
}
~~~

Ví dụ lấy một tập candidate; production cần kết hợp filter incremental, paging, giới hạn thời gian và chính sách xử lý referral phù hợp. Các operational attributes được yêu cầu rõ ràng vì không nên giả định chúng tự xuất hiện cùng user attributes.

`entryUUID` không phải thuộc tính có ở mọi directory. Với Active Directory có thể cần adapter cho `objectGUID` dưới dạng binary. Đừng ép hai loại định danh vào cùng parser chuỗi khi chưa chuẩn hóa.

### 4.2. Nếu mapper discovery lỗi thì sao?

`LdapTemplate.search` gọi mapper trong quá trình duyệt kết quả. Nếu mapper ném exception không được xử lý, Search có thể kết thúc trước khi trả đủ danh sách. Vì vậy:

- Discovery mapper nên thực hiện ít chuyển đổi nhất có thể.
- Kiểm tra DN và stable ID trước khi ghi candidate.
- Không parse tất cả nghiệp vụ phức tạp trong callback discovery.
- Nếu một entry không đọc được định danh, lưu thông tin lỗi discovery nếu có thể xác định được entry; nếu không, đánh dấu scan chưa đầy đủ.
- Chỉ đánh dấu `scanComplete=true` khi mọi trang đã được đọc hết và kết quả Search kết thúc hợp lệ.

Một candidate có DN nhưng thiếu stable ID có thể được đưa vào quarantine hoặc xử lý theo fallback policy. Không tự bỏ qua và coi scan đầy đủ.

## 5. Manifest và checkpoint: tiến độ batch phải có bằng chứng

### 5.1. Phân biệt scan checkpoint và entry progress

Hai loại trạng thái có ý nghĩa khác nhau:

- **Scan checkpoint:** ranh giới nguồn đã được khám phá đầy đủ, ví dụ cửa sổ timestamp đến `upperBound`.
- **Entry progress:** trạng thái xử lý từng candidate thuộc scan đó.

Không nên dùng một trường `lastProcessedTimestamp` cho cả hai. Nếu 100 entry cùng timestamp, 99 thành công và 1 thất bại, việc lưu timestamp đó làm checkpoint có thể khiến entry cuối không bao giờ được đọc lại.

### 5.2. Mô hình batch manifest

Mỗi lần scan tạo một record:

| Trường | Ý nghĩa |
| --- | --- |
| `runId` | ID batch |
| `lowerBound` | Cận dưới của cửa sổ đọc |
| `upperBound` | Cận trên đã chọn trước khi scan |
| `scanStartedAt` | Thời điểm bắt đầu |
| `scanCompletedAt` | Thời điểm đọc đủ trang |
| `scanComplete` | Discovery có hoàn tất không |
| `candidateCount` | Số candidate đã lưu |
| `successCount` | Số entry đã áp dụng |
| `retryCount` | Số entry đang chờ retry |
| `quarantineCount` | Số entry đã cách ly |
| `checkpointStatus` | Chưa commit, committed hoặc blocked |

Một run chỉ được phép commit checkpoint khi:

1. Discovery hoàn tất và không bị cắt bởi size/time limit hoặc lỗi trang.
2. Mọi candidate đã có trạng thái cuối theo policy.
3. Các entry bị quarantine đã được ghi bền vững và có thể replay, nếu policy cho phép tiến checkpoint.
4. Downstream đã commit dữ liệu tương ứng.
5. Không còn worker đang giữ lease chưa kết thúc.
6. Checkpoint được cập nhật nguyên tử theo version/lease để tránh hai job cùng ghi đè nhau.

### 5.3. Vì sao không lấy timestamp lớn nhất đã thành công?

Giả sử các candidate:

~~~text
Alice  modifyTimestamp=10:00:00  SUCCEEDED
Bob    modifyTimestamp=10:00:00  RETRY_WAIT
Carol  modifyTimestamp=10:00:01  SUCCEEDED
~~~

Nếu checkpoint được đặt thành `10:00:01`, lần sau filter `modifyTimestamp > checkpoint` sẽ bỏ Bob. LDAP filter chuẩn thường dùng ordering `>=`; dù dùng `>=`, nếu checkpoint tiến lên và có các replica trễ, vẫn có thể bỏ sót dữ liệu.

**Checkpoint phải biểu diễn một ranh giới đã xử lý đầy đủ**, không phải timestamp lớn nhất của một record bất kỳ. Khi dùng timestamp polling, hãy giữ cận bao gồm và overlap, đồng thời manifest hóa candidate để theo dõi các entry cùng timestamp.

### 5.4. Ví dụ tính cửa sổ an toàn

Giả sử checkpoint đã commit là `10:00`, overlap là 5 phút, settle lag là 2 phút và job bắt đầu lúc `10:10`:

~~~text
lowerInclusive = 09:55
upperExclusive = 10:08

Search candidate từ lowerInclusive
Manifest ghi candidate thuộc cửa sổ đã chốt
Lưu manifest của run
Commit upperExclusive sau khi run đạt policy completion
~~~

Overlap giúp đọc lại vùng biên; idempotency xử lý candidate trùng. Settle lag giảm nguy cơ đọc thay đổi quá mới khi replica chưa kịp hội tụ. Các khoảng này cần được đo từ topology thực tế và không tạo bảo đảm tuyệt đối nếu replication lag vượt overlap.

Khi worker fetch entry theo DN sau thời điểm discovery, entry có thể đã được sửa thêm và `modifyTimestamp` mới hơn `upperExclusive`. Với mục tiêu đồng bộ **trạng thái mới nhất**, có thể upsert snapshot mới hơn nhưng phải lưu đúng version thực tế đã đọc; lần scan sau có thể nhìn thấy lại candidate và idempotency sẽ xử lý trùng. Nếu yêu cầu snapshot nhất quán tại đúng `upperExclusive`, cần stage payload trong lúc scan hoặc dùng cơ chế snapshot/change feed có semantics phù hợp; một Search LDAP thông thường không tự tạo snapshot giao dịch.

## 6. Xử lý từng entry và cô lập lỗi

### 6.1. Không để lỗi một entry dừng cả vòng lặp

Sau khi candidate đã được lưu bền vững, worker xử lý từng entry độc lập:

~~~java
import java.util.UUID;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.LdapTemplate;

public final class EntryProcessor {

    private final LdapTemplate ldapTemplate;
    private final EntryProgressStore progressStore;
    private final EntryApplier entryApplier;
    private final RetryPolicy retryPolicy;

    public EntryProcessor(
            LdapTemplate ldapTemplate,
            EntryProgressStore progressStore,
            EntryApplier entryApplier,
            RetryPolicy retryPolicy) {
        this.ldapTemplate = ldapTemplate;
        this.progressStore = progressStore;
        this.entryApplier = entryApplier;
        this.retryPolicy = retryPolicy;
    }

    public void process(SyncCandidate candidate, UUID runId) {
        try {
            PersonEntry person = ldapTemplate.findByDn(
                candidate.dn(), PersonEntry.class
            );

            // EntryApplier ghi snapshot và SUCCEEDED trong cùng DB transaction.
            entryApplier.applyAndMarkSucceeded(runId, candidate, person);

        } catch (CommunicationException ex) {
            progressStore.scheduleRetry(
                runId,
                candidate.stableId(),
                retryPolicy.nextAttempt(ex)
            );

        } catch (PermanentEntryException ex) {
            progressStore.quarantine(
                runId,
                candidate.stableId(),
                ex.getSafeErrorCode()
            );

        } catch (RuntimeException ex) {
            progressStore.recordUnexpectedFailure(
                runId,
                candidate.stableId(),
                ex
            );
        }
    }
}
~~~

Các abstraction `EntryProgressStore`, `EntryApplier`, `RetryPolicy`, `PermanentEntryException` và `PersonEntry` cần được triển khai theo hệ thống thực tế. Ví dụ tập trung vào nguyên tắc: **lỗi được gắn với candidate cụ thể**, không biến thành kết quả rỗng cho toàn batch.

Trong code production, phải bảo đảm `recordUnexpectedFailure` không âm thầm đánh dấu thành công. Lỗi chưa phân loại nên giữ trạng thái chưa hoàn tất theo chính sách và phát cảnh báo.

### 6.2. Cẩn thận với lỗi trong callback mapper

Nếu `findByDn` hoặc mapper ném exception, chỉ bắt quanh từng candidate sau khi discovery đã ghi manifest. Nếu mapper của một Search lớn ném lỗi khi đang enumeration, đó là lỗi discovery/batch và có thể làm Search dừng.

Có thể tách:

1. Search để lấy DN và stable ID.
2. Ghi toàn bộ candidate vào manifest.
3. Worker fetch chi tiết từng DN.
4. Map/validate từng entry và áp dụng downstream.
5. Ghi trạng thái từng entry.

Như vậy một entry có attribute lỗi có thể được quarantine mà không ngăn các candidate khác tiếp tục. Nhưng nếu Search không thể đọc DN/stable ID hoặc bị cắt, batch discovery vẫn chưa hoàn tất.

## 7. Phân loại lỗi để quyết định retry

Retry chỉ hữu ích khi nguyên nhân có thể tạm thời biến mất. Lặp lại lỗi schema hoặc credential không làm dữ liệu đúng hơn.

| Nhóm lỗi | Ví dụ | Chính sách |
| --- | --- | --- |
| **Transient transport** | `CommunicationException`, socket reset, timeout | Retry giới hạn sau khi context lỗi được loại và connection mới được cấp |
| **Server temporarily unavailable** | LDAP result `unavailable`, `busy` | Backoff, giảm concurrency, retry trong deadline |
| **Pool/resource** | Không mượn được context, pool exhausted | Kiểm tra saturation/leak; không tạo vòng retry làm tăng tải |
| **Authentication/configuration** | Invalid credentials, TLS trust/hostname failure | Dừng hoặc mở circuit; sửa secret/certificate |
| **Authorization** | Insufficient access rights | Quarantine/blocked và yêu cầu sửa ACL |
| **Schema/data** | Object class violation, invalid attribute syntax, conversion error | Quarantine; sửa dữ liệu hoặc mapping |
| **Conflict/race** | Entry đã tồn tại, DN đã đổi, attribute value đã thay | Đọc lại state và phân giải; không retry nguyên lệnh mù quáng |
| **Not found** | DN biến mất hoặc đã move | Re-resolve theo stable ID và policy; có thể là delete/move hợp lệ |
| **Downstream transient** | Database timeout, HTTP 503, queue unavailable | Retry downstream độc lập; không đọc lại LDAP nếu snapshot đã lưu an toàn |
| **Unknown** | Exception chưa phân loại | Giữ trạng thái chưa hoàn tất, log an toàn và điều tra |

### 7.1. Phân biệt `CommunicationException` với lỗi dữ liệu

JNDI có `javax.naming.CommunicationException`; Spring LDAP có `org.springframework.ldap.CommunicationException`. Khi dùng `LdapTemplate`, exception JNDI thường được chuyển thành hierarchy Spring LDAP.

Một lỗi giao tiếp không nói rõ LDAP server đã xử lý thao tác ghi hay chưa. Với read, có thể retry có giới hạn. Với Add/Modify/Delete, phải xem kết quả là **có thể chưa xác định** và đối soát trước.

Ngược lại, `insufficientAccessRights`, `invalidCredentials`, `objectClassViolation` và lỗi parse dữ liệu không nên được retry liên tục cùng request. Chúng cần sửa quyền, secret, schema hoặc dữ liệu.

### 7.2. Phân loại dựa trên cause chain

Exception có thể được bọc nhiều lớp. Hệ thống nên chuẩn hóa lỗi dựa trên:

- Loại exception ngoài cùng.
- Root cause/cause chain.
- LDAP result code nếu có.
- Operation đang thực hiện (Search, Add, Modify, Delete).
- Tình trạng connection và pool.
- Việc downstream đã commit hay chưa.

Không chỉ so khớp thông điệp exception vì message có thể thay đổi theo JDK/provider và có thể chứa dữ liệu nhạy cảm.

## 8. Retry với exponential backoff, jitter và deadline

### 8.1. Công thức backoff

~~~text
cap(n) = min(maxDelay, baseDelay * 2^n)
delay  = random(0, cap(n))
~~~

Ví dụ `baseDelay=500ms`, `maxDelay=30s`:

| Lần retry | Cap trước jitter | Khoảng delay |
| --- | ---: | ---: |
| 1 | 0,5 s | 0–0,5 s |
| 2 | 1 s | 0–1 s |
| 3 | 2 s | 0–2 s |
| 4 | 4 s | 0–4 s |
| 5 | 8 s | 0–8 s |
| 6 | 16 s | 0–16 s |
| 7 trở đi | 30 s | 0–30 s |

Jitter giúp nhiều worker không cùng retry tại một thời điểm sau outage. Không để backoff tăng vô hạn; đặt **max attempts**, **max elapsed time** và **job deadline**.

### 8.2. Java tính backoff có jitter

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class ExponentialBackoff {

    private final Duration baseDelay;
    private final Duration maxDelay;

    public ExponentialBackoff(
            Duration baseDelay,
            Duration maxDelay) {
        this.baseDelay = baseDelay;
        this.maxDelay = maxDelay;
    }

    public Duration delayForRetry(int retryNumber) {
        if (retryNumber < 1) {
            throw new IllegalArgumentException("retryNumber phải >= 1");
        }

        long base = baseDelay.toMillis();
        long cap = maxDelay.toMillis();

        int exponent = Math.min(retryNumber - 1, 30);
        long exponential = base * (1L << exponent);
        long bounded = Math.min(cap, exponential);

        long jitter = ThreadLocalRandom.current()
            .nextLong(Math.max(1L, bounded + 1L));

        return Duration.ofMillis(jitter);
    }
}
~~~

Đoạn code đơn giản hóa việc tính toán cho các giá trị delay thông thường. Implementation production cần kiểm tra overflow khi cấu hình `Duration` cực lớn, tránh `base * multiplier` tràn số và có thể dùng thư viện retry đã được dự án chuẩn hóa.

### 8.3. Không retry khi hết deadline

Một entry có thể có:

- Tối đa 5 lần retry.
- Tổng thời gian retry tối đa 10 phút.
- Thời gian mỗi lần LDAP Search tối đa 3 giây.
- Thời điểm retry tiếp theo được lưu vào database.

Nếu deadline batch đã hết, giữ `RETRY_WAIT` và để scheduler/run sau tiếp tục. Không giữ thread ngủ nhiều phút cho từng entry; lưu `nextAttemptAt` rồi đưa entry trở lại hàng đợi khi đến hạn.

### 8.4. Giới hạn concurrency

Khi LDAP server đang chậm, tăng số worker có thể làm outage nặng hơn. Hãy giới hạn:

- Số candidate đang `IN_PROGRESS`.
- Số connection LDAP được mượn đồng thời.
- Số request retry mỗi giây.
- Số lần retry cùng một source/partition.
- Số worker đang cập nhật cùng stable ID.

Kết hợp circuit breaker hoặc pause switch cho source khi tỷ lệ lỗi hệ thống vượt ngưỡng. Circuit breaker bảo vệ nguồn LDAP; nó không được đánh dấu các entry đang chờ thành công.

## 9. Idempotency: xử lý lặp mà không tạo bản sao trùng

### 9.1. Vì sao retry tạo ra xử lý ít nhất một lần?

Giả sử worker ghi dữ liệu đích thành công nhưng process dừng trước khi cập nhật progress:

~~~text
1. Upsert Alice vào database: SUCCESS
2. Process crash
3. progress vẫn là IN_PROGRESS
4. Worker khác nhận lại lease và xử lý Alice lần nữa
~~~

Đây là hành vi **at-least-once**: một entry có thể được xử lý nhiều lần. Nếu downstream chỉ có lệnh insert, có thể tạo bản ghi trùng.

Giải pháp là **idempotent upsert** theo stable ID và source version hoặc so sánh nội dung. Ghi trạng thái thành công và dữ liệu đích trong cùng transaction database khi có thể.

### 9.2. Transaction nội bộ cho dữ liệu đích và progress

Ví dụ service dùng database đích:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EntryApplier {

    private final LocalDirectoryRepository localRepository;
    private final EntryProgressStore progressStore;

    public EntryApplier(
            LocalDirectoryRepository localRepository,
            EntryProgressStore progressStore) {
        this.localRepository = localRepository;
        this.progressStore = progressStore;
    }

    @Transactional
    public void applyAndMarkSucceeded(
            UUID runId,
            SyncCandidate candidate,
            PersonEntry person) {

        localRepository.upsert(
            candidate.stableId(),
            candidate.dn(),
            person
        );

        progressStore.markSucceeded(
            runId,
            candidate.stableId()
        );
    }
}
~~~

Hai thao tác trên chỉ nguyên tử nếu chúng dùng **cùng transaction manager/database transaction**. LDAP Search đã diễn ra bên ngoài transaction này; không có distributed transaction tự động giữa LDAP và database.

Nếu database upsert thành công nhưng progress ghi lỗi trong cùng transaction, cả hai phải rollback. Nếu dùng hai database hoặc hai dịch vụ khác nhau, cần outbox/saga và idempotency key.

### 9.3. Khóa idempotency

Một khóa thường dùng:

~~~text
(sourceId, stableEntryId)
~~~

Nếu cần phát hiện một trạng thái cụ thể đã áp dụng, có thể lưu:

~~~text
(sourceId, stableEntryId, sourceVersion, payloadHash)
~~~

Tuy nhiên:

- `modifyTimestamp` không phải event ID duy nhất; nhiều lần sửa có thể cùng timestamp.
- DN thay đổi qua rename, nên không phải khóa ổn định.
- Stable ID có thể khác giữa hai directory hoặc bị tái tạo khi export/import.
- Nếu mục tiêu là đồng bộ snapshot hiện tại, có thể so sánh payload hash.
- Nếu yêu cầu lưu **mọi lần thay đổi**, timestamp polling và snapshot hash không đủ; cần change log/sync mechanism có cursor và event semantics phù hợp.

### 9.4. Không phát event hai lần

Nếu sau upsert còn phải gửi notification, ghi message vào **transactional outbox** cùng transaction với bản sao và progress. Consumer sử dụng idempotency key để tránh gửi hoặc áp dụng tác động trùng.

Không gửi email/notification trực tiếp giữa transaction ghi database và cập nhật checkpoint rồi hy vọng process không crash. Có thể gặp trường hợp notification đã gửi nhưng progress chưa ghi, dẫn đến gửi lại sau restart.

## 10. Entry lỗi không thể tự sửa: quarantine và dead-letter

### 10.1. Khi nào đưa vào quarantine?

Các ví dụ:

- Entry thiếu attribute bắt buộc theo mapping nghiệp vụ.
- Giá trị ngày giờ không parse được theo schema/vendor đã xác nhận.
- Stable ID không đọc được hoặc không duy nhất theo hợp đồng.
- Schema violation hoặc objectClass không phù hợp.
- DN chứa tham chiếu không hợp lệ.
- ACL không cho phép đọc một attribute cần thiết.
- Lỗi lặp lại quá số lần cho phép và cần người vận hành điều tra.

Không quarantine lỗi hệ thống diện rộng như toàn bộ LDAP endpoint đang down rồi đánh dấu mọi candidate là dữ liệu hỏng. Lỗi nguồn cần dừng/hold batch.

### 10.2. Record dead-letter nên chứa gì?

| Trường | Mục đích |
| --- | --- |
| `deadLetterId` | Định danh record lỗi |
| `sourceId`, `stableEntryId` | Nguồn và đối tượng |
| `observedDn` | DN khi lỗi xảy ra |
| `runId` | Batch phát hiện lỗi |
| `errorCategory`, `errorCode` | Phân loại lỗi đã chuẩn hóa |
| `attemptCount` | Số lần đã thử |
| `firstFailedAt`, `lastFailedAt` | Lịch sử lỗi |
| `sourceVersion`, `payloadHash` | Version/hash để đối soát |
| `replayStatus` | Pending, replaying, resolved, rejected |
| `safeDiagnostic` | Thông tin kỹ thuật đã loại secret/dữ liệu nhạy cảm |

Lưu raw payload chỉ khi thật sự cần cho replay và được chính sách dữ liệu cho phép. Nếu không, lưu stable ID, DN, version và lý do; khi replay thì đọc lại LDAP để lấy trạng thái mới nhất.

### 10.3. Replay sau khi sửa dữ liệu

Quy trình replay:

1. Người vận hành sửa schema, ACL, dữ liệu hoặc mapping.
2. Dead-letter chuyển sang `REPLAY_PENDING`.
3. Worker lấy record với lease.
4. Đọc lại entry theo stable ID/DN hiện tại.
5. Kiểm tra version/state mới; không mặc định payload cũ còn đúng.
6. Áp dụng upsert idempotent.
7. Đánh dấu `RESOLVED` và ghi audit.
8. Chạy reconciliation nếu record thuộc batch cũ đã qua checkpoint.

Replay phải dùng cùng quy tắc bảo mật và giới hạn retry như xử lý bình thường. Không tạo một endpoint tùy ý cho phép caller gửi raw DN và payload để ghi thẳng vào directory.

## 11. Resume sau restart: thuật toán tổng thể

Một worker có thể dừng do deploy, process crash, node restart hoặc mất kết nối. Khi khởi động lại, không nên luôn bắt đầu từ timestamp mới nhất.

~~~mermaid
flowchart TD
    A["Đọc checkpoint và run chưa hoàn tất"] --> B["Lấy lease cho run/partition"]
    B --> C["Kiểm tra scanComplete và manifest"]
    C --> D{"Manifest đầy đủ?"}
    D -->|Không| E["Re-scan từ cửa sổ an toàn, upsert candidates"]
    D -->|Có| F["Lấy PENDING / RETRY_WAIT đến hạn / lease hết"]
    E --> F
    F --> G["Claim từng entry bằng lease"]
    G --> H["Fetch LDAP + validate + map"]
    H --> I{"Kết quả xử lý"}
    I -->|Thành công| J["Upsert + mark SUCCEEDED nguyên tử"]
    I -->|Transient| K["Lưu RETRY_WAIT và nextAttemptAt"]
    I -->|Permanent| L["Lưu QUARANTINED / FAILED_FINAL"]
    J --> M{"Còn entry chưa terminal?"}
    K --> M
    L --> M
    M -->|Có| F
    M -->|Không| N["Đánh giá batch completion policy"]
    N --> O{"Scan đủ và progress hợp lệ?"}
    O -->|Không| P["Giữ checkpoint; cảnh báo"]
    O -->|Có| Q["Commit checkpoint bằng compare-and-set"]
~~~

Các bước cụ thể:

1. Đọc checkpoint đã commit và các run chưa hoàn tất.
2. Lấy lease theo source/partition để tránh hai scheduler cùng tiến checkpoint.
3. Nếu manifest chưa đầy đủ, khởi động lại discovery từ lower bound an toàn và upsert candidate theo khóa ổn định.
4. Claim candidate bằng thao tác atomic (ví dụ update status nếu đang `PENDING` hoặc lease đã hết).
5. Fetch entry từ LDAP, map/validate, áp dụng dữ liệu đích.
6. Ghi `SUCCEEDED` cùng transaction với upsert downstream khi có thể.
7. Với transient error, lưu `RETRY_WAIT` và `nextAttemptAt`; không giữ thread ngủ.
8. Với lỗi permanent, quarantine và tạo alert/ticket theo policy.
9. Khi mọi candidate terminal, đánh giá batch policy; `QUARANTINED` chỉ cho phép tiến checkpoint nếu record dead-letter đã được lưu bền vững và có replay process.
10. Commit checkpoint bằng compare-and-set hoặc optimistic version để không ghi đè checkpoint mới hơn từ worker khác.
11. Giải phóng lease và ghi metric.

### 11.1. Lease và worker chết giữa chừng

Nếu worker claim entry rồi crash, trạng thái `IN_PROGRESS` không được giữ vĩnh viễn. Dùng lease:

~~~text
status = IN_PROGRESS
leaseOwner = worker-07
leaseUntil = 10:05:00Z
~~~

Khi lease hết hạn, worker khác có thể claim lại sau khi kiểm tra trạng thái downstream. Không chỉ dựa vào heartbeat trong RAM.

Lease cần có owner token/version để worker cũ không thể ghi đè kết quả của worker mới sau khi lease đã được cấp lại. Có thể dùng optimistic locking/fencing token trong progress store.

### 11.2. Checkpoint commit có điều kiện

Ví dụ logic:

~~~text
UPDATE sync_checkpoint
SET value = :newUpperBound,
    version = version + 1
WHERE source_id = :sourceId
  AND version = :expectedVersion
  AND value = :expectedPreviousBound;
~~~

Nếu số hàng cập nhật bằng 0, checkpoint đã bị một worker khác thay đổi hoặc version không còn đúng. Worker phải đọc lại state và không được ghi đè mốc mới hơn.

Đây là **compare-and-set** ở kho checkpoint, không phải thao tác LDAP. Transaction DB nên bảo vệ việc kiểm tra batch completion và cập nhật checkpoint theo cùng một nguồn sự thật.

## 12. Paging, cookie và resume

### 12.1. Page cookie không phải checkpoint nghiệp vụ

LDAP Simple Paged Results Control (RFC 2696) cung cấp cookie để tiếp tục Search qua nhiều trang. Cookie phục vụ **một chuỗi Search/paging**; nó không tự mô tả rằng dữ liệu downstream đã được ghi thành công.

Phân biệt:

- **Paging cookie:** tiếp tục lấy trang LDAP tiếp theo.
- **Entry progress:** candidate nào đã được áp dụng.
- **Batch checkpoint:** cửa sổ nguồn nào đã được xử lý theo policy.
- **RFC 4533 sync cookie:** trạng thái của LDAP Content Synchronization khi server hỗ trợ, khác paging cookie.

Nếu process restart hoặc connection đổi, cookie có thể không còn hợp lệ theo server/session. Không lưu cookie rồi mặc định có thể dùng lại qua bất kỳ node/connection nào.

### 12.2. Chiến lược resume khi cookie mất hiệu lực

Với timestamp polling:

1. Giữ checkpoint đã commit gần nhất.
2. Tính lower bound có overlap.
3. Re-run discovery từ lower bound tới upper bound đã chọn.
4. Upsert candidate theo stable ID và run ID.
5. Dedupe candidate trùng.
6. Xử lý lại các entry chưa terminal.
7. Chỉ commit upper bound khi manifest mới đầy đủ và entry progress đạt policy.

Với RFC 4533, cookie sync có semantics riêng. Nếu server từ chối cookie hoặc yêu cầu refresh, client phải thực hiện refresh theo đặc tả và cập nhật snapshot; không chuyển cookie thành timestamp tùy ý.

### 12.3. Scan không hoàn tất thì checkpoint giữ nguyên

Một Search có thể bị:

- `SizeLimitExceededException`.
- `TimeLimitExceededException`.
- Referral không được xử lý.
- Paging cookie lỗi.
- `CommunicationException`.
- Server trả kết quả một phần.
- Mapper lỗi trước khi candidate được ghi đủ.

Trong các trường hợp đó, không đánh dấu `scanComplete=true`. Có thể giữ những candidate đã phát hiện để tiết kiệm công sức, nhưng checkpoint batch vẫn **chưa được tiến** cho tới khi discovery được hoàn tất hoặc re-scan bù đầy đủ.

## 13. Xử lý delete và entry biến mất trong lúc đồng bộ

### 13.1. Không tìm thấy entry không phải lúc nào cũng là delete đã xác nhận

Candidate được phát hiện ở thời điểm T1, nhưng khi worker fetch tại T2, entry có thể đã:

- Bị xóa.
- Được rename/move sang DN mới.
- Chuyển ra ngoài search scope.
- Không còn được tài khoản bind nhìn thấy do ACL.
- Chưa được replica đang đọc cập nhật.

Nếu `findById(oldDn)` không tìm thấy, không tự động xóa bản sao nội bộ theo DN đó. Hãy resolve theo stable ID trên nguồn có thẩm quyền hoặc ghi trạng thái `SOURCE_NOT_FOUND_PENDING_RECONCILIATION`.

### 13.2. Tombstone và deletion feed

Để đồng bộ delete chính xác, cần cơ chế ghi nhận deletion như tombstone, changelog, RFC 4533 sync state hoặc vendor-specific DirSync. Polling `modifyTimestamp` trên các entry đang tồn tại không tự sinh sự kiện xóa.

Nếu không có delete feed, dùng full reconciliation có xác minh:

1. Quét đầy đủ phạm vi nguồn.
2. Ghi nhận stable IDs đã nhìn thấy trong run.
3. Xác minh scan không bị cắt, ACL không thay đổi và mọi partition/referral cần thiết đã được đọc.
4. Chỉ đánh dấu bản sao không thấy là nghi ngờ thiếu.
5. Xác minh lại trên nguồn có thẩm quyền hoặc qua lần quét tiếp theo.
6. Sau chính sách grace period, mới áp dụng trạng thái deleted/removed theo nghiệp vụ.

### 13.3. Không để lỗi ACL biến thành hàng loạt delete

Nếu service account đột nhiên mất quyền đọc `ou=people`, full scan có thể trả ít hoặc không có entry. Không được hiểu rằng mọi user đã bị xóa. Theo dõi số lượng kết quả, quyền, endpoint, paging và baseline để phát hiện scan bất thường.

## 14. Xử lý đồng thời và thứ tự cập nhật

### 14.1. Không xử lý cùng một stable ID đồng thời tùy tiện

Hai worker có thể nhận cùng candidate do overlap hoặc re-scan. Dùng:

- Unique key trên `(sourceId, stableEntryId)`.
- Lease hoặc atomic claim.
- Optimistic version khi ghi progress.
- Idempotent upsert ở downstream.
- Fencing token để worker cũ không ghi đè kết quả mới.

Nếu nhiều run cùng xử lý một stable ID, nên serialize theo key hoặc dùng compare-and-set theo source version. Không dùng DN làm lock key nếu rename có thể làm DN đổi trong lúc lock.

### 14.2. Out-of-order update

Giả sử worker A đọc Alice ở version cũ, worker B đọc version mới rồi ghi trước. Nếu A ghi sau, bản sao có thể bị lùi dữ liệu.

Cần bảo vệ bằng source version nếu directory cung cấp revision có thể so sánh. `modifyTimestamp` có thể hỗ trợ kiểm tra trạng thái trong một số directory nhưng không phải unique event ID hoặc thứ tự toàn cục qua replica. Nếu không có version đáng tin, serialize theo stable ID hoặc đọc lại nguồn trước khi áp dụng kết quả cũ.

### 14.3. Downstream độc lập với LDAP retry

Nếu đã fetch và lưu snapshot bền vững vào staging table, database đích tạm thời lỗi thì có thể retry **chỉ bước apply downstream** mà không cần query LDAP lại. Điều này giảm tải và giữ cùng payload giữa các lần retry.

Nếu không lưu snapshot, retry sẽ đọc trạng thái mới nhất; đây có thể là lựa chọn đúng cho mục tiêu hội tụ trạng thái cuối, nhưng không đảm bảo tái tạo payload ban đầu. Hãy xác định rõ hệ thống cần **latest state** hay **event history**.

## 15. Quan sát, cảnh báo và runbook

Các chỉ số nên theo dõi:

| Metric | Ý nghĩa |
| --- | --- |
| `sync_run_started_total`, `sync_run_completed_total` | Số batch bắt đầu/hoàn tất |
| `sync_scan_complete` | Discovery đã đọc đủ chưa |
| `sync_candidate_total` | Số candidate phát hiện |
| `sync_entry_success_total` | Số entry áp dụng thành công |
| `sync_entry_retry_total` | Số lần retry |
| `sync_entry_quarantine_total` | Số entry cần xử lý riêng |
| `sync_entry_in_progress` | Số lease đang hoạt động |
| `sync_checkpoint_lag_seconds` | Độ trễ checkpoint so với nguồn |
| `sync_oldest_retry_age_seconds` | Entry retry chờ lâu nhất |
| `sync_dead_letter_pending` | Số lỗi chưa replay |
| `ldap_search_latency` | Độ trễ Search |
| `ldap_communication_exception_total` | Lỗi giao tiếp LDAP |
| `ldap_size_limit_total` | Search bị giới hạn kết quả |
| `sync_reconciliation_mismatch_total` | Sai khác phát hiện qua đối soát |

Cảnh báo khi:

- Run chưa hoàn tất quá thời gian SLA.
- Checkpoint đứng yên trong khi source có thay đổi.
- Tỷ lệ lỗi hoặc quarantine tăng đột biến.
- Retry queue tăng nhanh hơn tốc độ xử lý.
- Một partition liên tục bị size/time limit.
- `IN_PROGRESS` lease hết hạn tăng.
- Số candidate giảm bất thường so với baseline.
- Downstream ghi thành công nhưng progress không được commit.

### 15.1. Runbook khi lỗi tăng đột biến

1. Xác định lỗi tập trung ở LDAP source, mapper, quyền, hay downstream.
2. Kiểm tra `scanComplete`, số trang và checkpoint; nếu scan chưa đủ thì giữ checkpoint.
3. Phân loại cause chain và LDAP result code.
4. Nếu communication outage, giảm concurrency, backoff và kiểm tra pool/TLS/DNS/server.
5. Nếu lỗi schema/mapping, quarantine các entry lỗi và sửa adapter; không retry vô hạn.
6. Nếu ACL, xác minh bind identity và quyền tối thiểu.
7. Nếu downstream lỗi, tạm dừng apply nhưng giữ staging/progress đã lưu.
8. Sau phục hồi, replay theo stable ID và idempotency key.
9. Chạy reconciliation để phát hiện entry bị bỏ sót hoặc trạng thái lùi.
10. Chỉ commit checkpoint khi batch đạt policy completion.

Không log mật khẩu bind, raw token, toàn bộ LDAP entry hoặc payload nhạy cảm chỉ để debug. Log error code, operation ID, source ID và stable ID đã được xử lý theo chính sách bảo vệ dữ liệu.

## 16. Kiểm thử lỗi từng entry và resume

Unit test mock có ích cho retry policy và state machine, nhưng cần integration test với LDAP directory để xác minh Search, DN, schema, ACL và paging thực tế.

### 16.1. Ma trận kiểm thử

| Kịch bản | Mô phỏng | Kết quả mong đợi |
| --- | --- | --- |
| Một entry lỗi parse | Một attribute có giá trị sai | Entry vào quarantine; candidate khác vẫn chạy |
| Lỗi giao tiếp tạm thời | Ngắt mạng một lần | Context lỗi bị loại, entry vào retry wait |
| LDAP outage diện rộng | Dừng server | Batch giữ checkpoint, circuit breaker/pause |
| Invalid credentials | Đổi bind password sai | Dừng retry lặp, cảnh báo cấu hình |
| Insufficient access | Bỏ quyền đọc một OU | Scan không được đánh dấu đầy đủ |
| Downstream timeout | Database tạm lỗi | Retry apply hoặc giữ staging, không đọc lại không cần thiết |
| Crash sau upsert | Dừng process trước progress commit | Retry không tạo duplicate |
| Crash sau progress claim | Worker chết khi IN_PROGRESS | Lease hết hạn, worker khác claim |
| Paging cookie lỗi | Làm cookie không còn hợp lệ | Re-scan cửa sổ an toàn, dedupe manifest |
| Size limit | Server cắt Search | `scanComplete=false`, checkpoint không tiến |
| Duplicate candidate | Overlap tạo cùng stable ID | Unique key/upsert không nhân bản |
| Same timestamp | Nhiều entry cùng timestamp | Manifest theo stable ID không bỏ entry |
| Rename trong lúc fetch | DN cũ không còn tồn tại | Resolve theo stable ID/reconciliation |
| Delete | Entry biến mất sau discovery | Chờ delete feed hoặc reconciliation |
| Poison entry | Lỗi dữ liệu không thể tự sửa | Dead-letter có thể replay |
| Hai worker cùng claim | Cùng một candidate | Lease/atomic claim chỉ cho một worker hợp lệ |
| Worker cũ ghi muộn | Lease đã được cấp lại | Fencing/version ngăn ghi đè |
| Replay thành công | Sửa schema/mapping rồi phát lại | Record chuyển resolved, không tạo duplicate |

### 16.2. Test idempotency khi crash

Một kịch bản quan trọng:

~~~text
1. Candidate Alice được claim
2. Upsert database thành công
3. Process crash trước khi mark SUCCEEDED
4. Lease hết hạn
5. Worker mới claim lại Alice
6. Upsert theo stable ID
7. Mark SUCCEEDED trong cùng transaction với upsert
~~~

Kỳ vọng chỉ có **một bản ghi logic** cho Alice. Nếu có outbox event, consumer cũng phải dedupe theo idempotency key.

### 16.3. Test checkpoint không bỏ qua entry lỗi

Fixture:

~~~text
Alice: 10:00:00Z -> SUCCEEDED
Bob:   10:00:00Z -> RETRY_WAIT
Carol: 10:00:01Z -> SUCCEEDED
~~~

Kỳ vọng:

- Checkpoint không được tiến qua run nếu Bob chưa thành công hoặc chưa được lưu vào quarantine theo policy.
- Nếu policy cho phép commit khi quarantine, dead-letter của Bob phải tồn tại bền vững và replay được.
- Khi Bob được replay thành công, trạng thái lỗi được đóng và reconciliation xác nhận downstream đã đúng.
- Không dùng `max(modifyTimestamp)` của Alice/Carol làm bằng chứng rằng Bob đã hoàn tất.

### 16.4. Test scan không đầy đủ

Giả lập Search trả hai trang rồi lỗi ở trang ba:

- Candidate ở hai trang đầu vẫn được lưu manifest.
- Run giữ `scanComplete=false`.
- Checkpoint không được advance.
- Sau phục hồi, job re-scan từ lower bound hoặc resume bằng cookie còn hợp lệ theo server.
- Candidate trùng được dedupe theo stable ID.
- Chỉ khi toàn bộ Search hoàn tất mới đánh dấu scan complete.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dừng toàn batch khi một entry lỗi | Các entry độc lập bị chậm theo | Cô lập lỗi theo candidate sau discovery |
| Bỏ qua entry lỗi và tăng checkpoint | Mất đồng bộ vĩnh viễn | Retry hoặc lưu dead-letter bền vững |
| Checkpoint = timestamp lớn nhất thành công | Bỏ entry cùng timestamp hoặc đến trễ | Batch manifest + contiguous completion |
| Chỉ lưu tiến độ trong RAM | Restart mất trạng thái | Durable progress store |
| Retry mọi exception | Tạo tải và lặp lỗi schema/ACL | Phân loại transient/permanent/ambiguous |
| Retry write ngay sau timeout | Trùng Add/Modify side effect | Đọc lại state và idempotency |
| Insert thay vì upsert | Duplicate sau crash/replay | Unique stable ID + upsert |
| Ghi progress trước khi ghi dữ liệu đích | Checkpoint tiến nhưng dữ liệu thiếu | Cùng transaction hoặc outbox |
| Đánh dấu scan complete sau trang đầu | Bỏ candidate ở trang sau | Xác nhận đủ mọi trang và Search result |
| Lưu paging cookie làm checkpoint vĩnh viễn | Cookie có thể hết hiệu lực | Re-scan overlap hoặc sync cookie đúng giao thức |
| Coi DN là stable ID | Rename tạo duplicate | `entryUUID`/`objectGUID` hoặc khóa nghiệp vụ |
| Quarantine mọi lỗi LDAP | Che outage thành lỗi dữ liệu | Phân biệt lỗi source-wide và entry-level |
| Coi entry không thấy là deleted | Xóa nhầm do ACL/scope/replica | Tombstone hoặc reconciliation đầy đủ |
| Worker cũ tiếp tục sau lease expiry | Ghi đè kết quả mới | Fencing token/optimistic version |
| Không có replay process | Dead-letter thành nơi lưu lỗi vĩnh viễn | Quy trình sửa, replay và audit |

## 18. Câu hỏi tự kiểm tra

1. Vì sao một lỗi mapping ở một entry không nhất thiết phải dừng toàn bộ batch?
2. Phân biệt entry-level failure, page-level failure và source-level failure.
3. Vì sao cần tách discovery khỏi việc fetch/map chi tiết từng entry?
4. Những trạng thái nào nên có trong progress record của một entry?
5. Khi nào một entry ở `QUARANTINED` có thể cho phép batch tiến checkpoint?
6. Vì sao không dùng timestamp lớn nhất của entry thành công làm checkpoint?
7. Manifest khác checkpoint như thế nào?
8. `entryUUID` và `objectGUID` có thể dùng làm khóa ổn định trong trường hợp nào?
9. Vì sao DN không phải khóa tốt khi có rename/move?
10. Khi nào `CommunicationException` có thể retry? Khi nào cần đối soát?
11. Vì sao `invalidCredentials` và `insufficientAccessRights` không nên retry liên tục?
12. Exponential backoff và jitter giúp tránh retry storm như thế nào?
13. Vì sao retry phải có max attempts, deadline và concurrency limit?
14. At-least-once processing có thể tạo duplicate trong trường hợp crash nào?
15. Idempotent upsert cần khóa và version nào?
16. Vì sao progress và dữ liệu đích nên commit trong cùng transaction database?
17. Nếu dùng hai hệ thống lưu trữ khác nhau, outbox/saga giải quyết vấn đề gì?
18. Dead-letter record cần thông tin nào để replay an toàn?
19. Vì sao paging cookie không phải checkpoint nghiệp vụ?
20. Nếu Search bị size limit hoặc lỗi ở trang cuối, checkpoint phải xử lý thế nào?
21. Khi candidate biến mất giữa discovery và fetch, vì sao không tự xóa bản sao ngay?
22. Lease và fencing token ngăn lỗi gì khi worker restart?
23. Làm sao ngăn worker cũ ghi đè snapshot mới hơn?
24. Khi nào nên dùng RFC 4533 sync cookie thay timestamp polling?
25. Hãy thiết kế test chứng minh batch không bỏ qua một entry `RETRY_WAIT`.

## 19. Tổng kết

Đồng bộ directory đáng tin cậy cần **tách scan, tiến độ từng entry và checkpoint batch**. Discovery phải được xác nhận đầy đủ; mỗi candidate có trạng thái bền vững; lỗi tạm thời được retry với backoff/jitter; lỗi dữ liệu hoặc quyền được quarantine; dữ liệu đích được upsert idempotent; và checkpoint chỉ tiến khi batch đạt completion policy.

Sau restart, worker đọc manifest và progress để tiếp tục từ entry chưa hoàn tất, thu hồi lease hết hạn và dedupe candidate được phát hiện lại. Nếu paging cookie không còn hợp lệ, có thể re-scan cửa sổ an toàn với overlap; không nhầm cookie trang với cursor nghiệp vụ. Delete cần tombstone/change feed hoặc reconciliation có xác minh.

**Không có exactly-once tự động chỉ nhờ repository, checkpoint hay retry.** Mục tiêu thực tế là at-least-once execution với idempotent effect, durable state, replay, fencing và quan sát lỗi. Với cách thiết kế này, một entry lỗi không làm mất tiến độ của các entry độc lập, và hệ thống có thể phục hồi sau restart hoặc outage mà không âm thầm bỏ sót dữ liệu.

### Tài liệu tham khảo

- [Spring LDAP Reference — Basic Usage and LdapTemplate](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
- [Spring LDAP Reference — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html).
- [Spring LDAP Reference — Paging and Controls](https://docs.spring.io/spring-ldap/reference/).
- [Spring Data LDAP Reference — Repository Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html).
- [RFC 4511 — LDAPv3 Protocol: Search and Controls](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 2696 — LDAP Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696).
- [RFC 4533 — LDAP Content Synchronization Operation](https://www.rfc-editor.org/rfc/rfc4533).
- [RFC 4530 — entryUUID LDAP Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530).
