# Tính bất biến audit trong Java Logging

## 1. Audit logging và yêu cầu bất biến

**Audit logging** ghi lại những hành động cần truy cứu trách nhiệm: ai thao tác, thao tác gì, lên tài nguyên nào, thời điểm và kết quả ra sao. Khác với log chẩn đoán DEBUG/INFO thông thường, audit có thể dùng để điều tra truy cập trái phép, kiểm tra thay đổi quyền, đối soát nghiệp vụ, hỗ trợ kiểm soát nội bộ và cung cấp bằng chứng theo quy trình được phê duyệt.

Một hệ thống audit có thể lưu đầy đủ event nhưng vẫn không đáng tin nếu người có quyền có thể sửa bản ghi cũ, xóa lịch sử, tạo một lịch sử mới hoặc làm mất event trong thời gian sự cố. **Tính bất biến audit** là mục tiêu ngăn hoặc kiểm soát việc thay đổi/xóa các event đã được chấp nhận và tạo cơ chế xác minh độc lập để phát hiện sửa đổi ngoài quy trình.

Cần phân biệt:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **Append-only** | Chỉ thêm sự kiện mới trên đường ghi được hỗ trợ; không cập nhật event cũ |
| **Immutability** | Dữ liệu đã chốt không được sửa/xóa trước thời điểm hợp lệ theo mô hình quyền và retention |
| **Integrity** | Nội dung và quan hệ giữa các event vẫn khớp với bản đã cam kết |
| **Tamper evidence** | Nếu có thay đổi ngoài ý muốn, hệ thống có khả năng phát hiện |
| **Authenticity** | Có bằng chứng một nguồn được ủy quyền đã ký/phát dữ liệu |
| **Completeness** | Không thiếu event đáng lẽ phải có và không có khoảng trống không giải thích |
| **Durability** | Event đã xác nhận không mất khi crash, restart hay lỗi một thành phần |
| **Confidentiality** | Chỉ người được cấp quyền có thể đọc dữ liệu audit nhạy cảm |

Đây là các thuộc tính liên quan nhưng **không thay thế nhau**. Một file chỉ cho phép append có thể bị xóa bởi root. Một chuỗi hash có thể phát hiện sửa đổi nếu giữ mốc chuẩn độc lập, nhưng không tự ngăn attacker tính lại toàn bộ chuỗi. Một object WORM có thể không sửa được nhưng vẫn chứa nội dung sai ngay từ đầu. Một bản ghi được mã hóa vẫn có thể bị xóa hoặc thay thế.

Mục tiêu thiết kế là **chứng minh lịch sử đáng tin trong phạm vi threat model cụ thể**, không tuyên bố “không ai trên thế giới có thể thay đổi audit”.

## 2. Threat model: bảo vệ trước ai và điều gì?

Những đối tượng khác nhau có mức quyền khác nhau:

- **Người dùng cuối:** có thể tìm cách tránh tạo audit event hoặc truyền payload làm nhiễu nội dung.
- **Ứng dụng bị chiếm quyền:** có thể ghi event giả hoặc bỏ qua audit nếu không có ràng buộc bổ sung.
- **Database administrator (DBA):** có thể sửa bảng dù application role chỉ có INSERT.
- **Cluster/root administrator:** có thể xóa file/volume hoặc can thiệp agent/collector.
- **Cloud storage administrator:** có thể thay retention/lifecycle hoặc bypass một số chính sách nếu mode/quyền cho phép.
- **Người giữ signing key:** có thể ký một lịch sử khác nếu khóa bị lạm dụng.
- **Sự cố không cố ý:** mất ACK, retry, crash giữa transaction, clock skew, backup restore và queue đầy.

Bởi vậy cần liệt kê quyền tấn công cụ thể:

| Kịch bản | Biện pháp có giá trị | Điều chưa giải quyết |
| --- | --- | --- |
| User API gửi trùng event | eventId + idempotency | Không ngăn admin sửa storage |
| Application role cố UPDATE/DELETE | INSERT-only + quyền database nhỏ nhất | Chủ bảng/superuser vẫn có thể bypass |
| Sửa một event trong chuỗi | Hash chain và xác minh tuần tự | Nếu attacker tính lại cả chain thì cần anchor ngoài |
| Xóa phần cuối lịch sử | Head checkpoint + lastSequence ở kho độc lập | Không phát hiện event chưa bao giờ được phát nếu thiếu đối soát |
| Xóa file hoặc object | WORM retention, replication, backup | Cần kiểm tra quyền và vùng lưu trữ thực tế |
| Giả mạo xuất xứ event | HMAC/chữ ký số + key management | Không chứng minh event mô tả đúng nghiệp vụ |
| Làm mất log khi outage | Durable outbox, queue/backpressure policy | Cần quan sát lag, retry và khôi phục |

**Separation of duties** là điều kiện quan trọng: nếu cùng một tài khoản được phép phát audit, sửa dữ liệu, xóa bản WORM, thay checkpoint và quản lý khóa thì attacker chiếm tài khoản ấy có thể tạo ra lịch sử khó kiểm chứng. Hãy tách quyền writer, auditor, verifier, key custodian và storage admin khi mức đảm bảo yêu cầu.

## 3. Audit event phải có hợp đồng ngữ nghĩa

Không nên coi mọi dòng INFO/ERROR là audit. Event audit cần phát ở boundary biết được **hành động thực tế và kết quả đã xác nhận**, không chỉ ở helper method chạy trước transaction.

Một số nhóm event điển hình:

- Authentication, MFA, password reset và thay đổi trạng thái tài khoản.
- Phân quyền: cấp, thu hồi role; thay đổi access policy; failed access có ý nghĩa an ninh.
- Thay đổi dữ liệu nghiệp vụ trọng yếu, phê duyệt/hoàn tác, export dữ liệu nhạy cảm.
- Thay cấu hình hệ thống, secret policy, retention hoặc audit collector.
- Thao tác của quản trị viên và thay đổi quyền đọc hoặc ghi kho audit.
- Sự kiện truy cập dữ liệu được chính sách nội bộ bắt buộc ghi nhận.

Schema tham khảo:

| Field | Mục đích |
| --- | --- |
| eventId | ID duy nhất theo event nghiệp vụ; phục vụ deduplication |
| streamId + sequenceNo | Phân đoạn và thứ tự append đã được chấp nhận |
| schemaVersion | Phiên bản cấu trúc/encoding dùng để xác minh |
| eventType | Tên sự kiện chuẩn hóa, không lấy raw input làm event name |
| occurredAt | Thời điểm hành động theo nguồn |
| recordedAt | Thời điểm audit system chấp nhận event |
| actorType/actorRef | Người, service hoặc hệ thống thực hiện |
| action, resourceType, resourceRef | Thao tác và đối tượng |
| outcome, reasonCode | Thành công/thất bại và lý do mã hóa ổn định |
| requestId/traceId/jobId | Context để đối chiếu, nếu có |
| previousHash/recordHash | Liên kết integrity của stream |
| keyId/checkpointRef | Khóa hoặc mốc xác minh, nếu được sử dụng |

Ví dụ audit event có cấu trúc (giá trị và schema minh họa):

~~~json
{
  "eventId": "evt-7f1",
  "streamId": "admin-audit",
  "sequenceNo": 103,
  "schemaVersion": 1,
  "eventType": "ROLE_REVOKED",
  "occurredAt": "2026-11-10T02:40:00Z",
  "recordedAt": "2026-11-10T02:40:01Z",
  "actorRef": "admin-7",
  "resourceRef": "member-8",
  "outcome": "SUCCESS",
  "requestId": "req-42"
}
~~~

**Dữ liệu audit cần tối thiểu hóa từ trước khi ghi**: không đưa raw password, access token, cookie, secret, PAN/CVV, request body không cần thiết hoặc thông tin cá nhân quá mức vào WORM. Bất biến dữ liệu sai chính sách có thể làm việc khắc phục sự cố riêng tư phức tạp hơn.

## 4. Append-only ở lớp ứng dụng và database

Một hệ thống append-only **không sửa lịch sử** để phản ánh trạng thái mới. Thay vào đó, một quyết định đảo ngược tạo event riêng:

~~~text
seq=101 event=ROLE_GRANTED principal=member-8 role=EDITOR
seq=102 event=ROLE_REVOKED principal=member-8 role=EDITOR
~~~

Sự kiện 101 vẫn đúng vì nó cho biết quyền đã từng được cấp. Không UPDATE event 101 thành REVOKED; làm vậy xóa mất dấu vết hành động ban đầu.

Có thể dùng audit table với quyền INSERT/SELECT cho writer, không cấp UPDATE/DELETE. Ví dụ PostgreSQL **phác thảo**, không phải DDL chung mọi database:

~~~sql
CREATE TABLE audit_events (
    stream_id       text NOT NULL,
    sequence_no     bigint NOT NULL,
    event_id        text NOT NULL UNIQUE,
    recorded_at     timestamptz NOT NULL,
    event_type      text NOT NULL,
    actor_ref       text NOT NULL,
    payload         jsonb NOT NULL,
    previous_hash   char(64) NOT NULL,
    record_hash     char(64) NOT NULL,
    PRIMARY KEY (stream_id, sequence_no)
);

GRANT SELECT, INSERT ON audit_events TO audit_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM audit_writer;
~~~

Đây là **kiểm soát quyền đối với role ứng dụng**, không phải bất biến vật lý. Superuser, owner, backup restore và migration vẫn có thể thay dữ liệu hoặc khôi phục trạng thái cũ. Cần xem xét cả table ownership, role inheritance, privileges và các đường can thiệp ngoài ứng dụng.

Nếu audit cần bằng chứng mạnh, xuất bản sao sang **kho retention/WORM với quản trị tách biệt** và có checkpoint độc lập. Việc chỉ cấm UPDATE trong service code không đủ khi hệ thống có nhiều đường ghi vào database.

## 5. WORM storage: khóa phiên bản đã cam kết

**WORM (Write Once, Read Many)** là mô hình lưu trữ mà object/version đã chốt không thể sửa hoặc xóa trong thời hạn giữ theo chính sách cụ thể. Một số nền tảng object storage cung cấp retention lock, versioning hoặc legal hold. Không mặc định mọi chế độ WORM đều có cùng mức bảo vệ.

Trước khi chọn, cần xác minh:

1. Đối tượng bất biến là **một version cụ thể**, một file, hay một key logic?
2. Retention tính từ thời điểm nào; thời hạn là bao lâu?
3. Người có quyền quản trị có thể **rút ngắn hoặc bypass** thời hạn trong mode được sử dụng không?
4. Có quyền nào có thể xóa key mã hóa khiến dữ liệu không thể đọc dù object còn?
5. Có versioning, replication, backup và phục hồi khi region lỗi?
6. Audit được chính các thay đổi retention, hold, policy và quyền admin không?
7. Có kiểm thử API overwrite/delete bị từ chối ở staging không?

**WORM không chứng minh event đúng ngay từ nguồn.** Một publisher phát event sai cũng có thể được lưu bất biến. Phải xác thực writer, kiểm tra schema, quy trình business transaction và đối chiếu.

**WORM cũng không có nghĩa phải lưu mãi mãi.** “Không được sửa/xóa trước hạn retention” và “vĩnh viễn không bao giờ được xóa” là hai yêu cầu khác nhau, đặc biệt khi có nghĩa vụ bảo vệ dữ liệu cá nhân.

## 6. Hash chain giúp phát hiện sửa lịch sử như thế nào?

Một **hash chain** gắn hash của record trước vào dữ liệu được băm của record hiện tại:

~~~text
genesisHash
    |
    v
event 1 -> hash1
            |
            v
         event 2 -> hash2
                     |
                     v
                  event 3 -> hash3
~~~

Một cách mô hình hóa:

~~~text
previousHash[1] = genesisHash
previousHash[i] = recordHash[i-1]

recordHash[i] = SHA-256(
    canonical(schemaVersion, streamId, sequenceNo, eventPayload,
              previousHash[i])
)
~~~

Nếu attacker sửa một event cũ nhưng giữ hash cũ, verifier tính lại sẽ thấy mismatch. Nếu xóa record giữa chuỗi, sequence hoặc liên kết previousHash có thể không còn khớp. Nếu đổi thứ tự event mà không tính lại chain, kết quả cũng bị phát hiện.

Tuy nhiên cần nhận thức giới hạn:

- **SHA-256 là hàm băm không khóa**, ai cũng có thể tính lại digest sau khi sửa event.
- Attacker kiểm soát toàn bộ kho có thể **viết lại cả lịch sử và tất cả hash**.
- **Xóa phần đuôi** có thể để lại một prefix hợp lệ, nên verify nội bộ của prefix vẫn trả true.
- Một event không bao giờ được tạo sẽ không xuất hiện để phép kiểm tra hash thấy được.
- Hash chain không tự chứng minh actor của event là người đúng hoặc outcome đã commit nghiệp vụ.

Muốn phát hiện việc **viết lại toàn bộ hoặc cắt đuôi**, cần kiểm tra **headHash và lastSequence** so với một **checkpoint/anchor được bảo vệ ở nơi độc lập**, hoặc kết hợp chữ ký/HMAC, cùng đối soát từ nguồn nghiệp vụ.

## 7. Canonical encoding là điều kiện để verify chính xác

Nếu hai hệ thống serialize cùng event ra bytes khác nhau, hash sẽ khác dù dữ liệu logic giống nhau. Ví dụ một Map trong Java không được coi là có thứ tự field cố định cho mọi serializer hoặc mọi phiên bản.

Một canonical encoding cần định nghĩa:

- Thứ tự trường và schemaVersion cố định.
- Biểu diễn sequence, số nguyên, số thực và boolean.
- UTF-8, length prefix, biểu diễn null, Unicode normalization nếu có.
- Timestamp UTC và độ chính xác được chọn.
- JSON key ordering/escaping nếu dùng canonical JSON thực sự.
- Cách biểu diễn previousHash, eventId, streamId.
- Quy tắc khi schema được nâng cấp hoặc có trường mới.

**Không hash Map.toString(), log text formatter hay JSON tự nối mà chưa định nghĩa canonical bytes.** Một thay đổi phiên bản thư viện, timezone, dấu cách hoặc thứ tự key có thể gây false integrity failure.

Có thể dùng binary format theo hợp đồng với byte length rõ ràng, hoặc serializer hỗ trợ deterministic/canonical encoding và được kiểm thử. Cần giữ mã verify cho các schemaVersion cũ để xác minh lịch sử nhiều năm.

## 8. Java 17 runnable: hash chain với canonical bytes

Ví dụ Java SE 17 sau dùng SHA-256, DataOutputStream, UTF-8 và HexFormat. Chương trình mô phỏng hai sự kiện audit trong bộ nhớ; sau đó sửa event đầu mà không tính lại hash để chứng minh verifier phát hiện mismatch.

Tạo file **AuditIntegrityDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;

public class AuditIntegrityDemo {
    private static final String GENESIS = "0".repeat(64);

    record Entry(long sequence, String action, String actor,
                 String previousHash, String hash) {}

    private static void field(DataOutputStream out, String value)
            throws IOException {
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    private static byte[] canonical(long sequence, String action,
                                    String actor, String previousHash) {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(1);  // schema version
            out.writeLong(sequence);
            field(out, action);
            field(out, actor);
            field(out, previousHash);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return buffer.toByteArray();
    }

    private static String hash(long sequence, String action,
                               String actor, String previousHash) {
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            byte[] bytes = canonical(sequence, action, actor, previousHash);
            return HexFormat.of().formatHex(sha.digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static void append(List<Entry> entries,
                               String action, String actor) {
        long next = entries.size() + 1L;
        String prior = entries.isEmpty()
                ? GENESIS : entries.get(entries.size() - 1).hash();
        entries.add(new Entry(next, action, actor, prior,
                hash(next, action, actor, prior)));
    }

    private static boolean verify(List<Entry> entries) {
        String prior = GENESIS;
        long expected = 1L;
        for (Entry e : entries) {
            if (e.sequence() != expected
                    || !e.previousHash().equals(prior)
                    || !e.hash().equals(
                            hash(e.sequence(), e.action(),
                                 e.actor(), e.previousHash()))) {
                return false;
            }
            prior = e.hash();
            expected++;
        }
        return true;
    }

    public static void main(String[] args) {
        List<Entry> entries = new ArrayList<>();
        append(entries, "ROLE_GRANTED", "admin-7");
        append(entries, "ROLE_REVOKED", "admin-7");

        System.out.println("events=" + entries.size());
        System.out.println("chainValid=" + verify(entries));

        Entry first = entries.get(0);
        entries.set(0, new Entry(first.sequence(), "ROLE_CHANGED",
                first.actor(), first.previousHash(), first.hash()));

        System.out.println("tamperDetected=" + !verify(entries));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AuditIntegrityDemo.java
java AuditIntegrityDemo
~~~

Stdout dự kiến chính xác khi chương trình chạy thành công:

~~~text
events=2
chainValid=true
tamperDetected=true
~~~

Giải thích:

1. **DataOutputStream** ghi version dưới dạng int, sequence dưới dạng long và mỗi String UTF-8 được prefix bằng độ dài byte. Hash được tính trên bytes theo quy ước rõ ràng.
2. **MessageDigest.getInstance("SHA-256")** tính digest; **HexFormat** tạo hex string.
3. **verify** so sequence liên tục, previousHash đúng và hash tính lại đúng.
4. Thay action trong event đầu nhưng giữ hash cũ làm phép verify thất bại; đó là điều kiện để in tamperDetected=true.
5. Chương trình **không sử dụng file, database, WORM, signature hoặc checkpoint ngoài**. Nó chỉ chứng minh nguyên lý tamper evidence đối với chuỗi đang có, không chứng minh bất biến storage.
6. Nếu attacker thay event và tính lại toàn bộ hash, hoặc xóa event cuối, **verify có thể vẫn true**. Đối chiếu head hash cùng expected sequence với checkpoint độc lập mới phát hiện được các tình huống này.
7. Trong hệ thống thật cần ràng buộc thêm **streamId, eventId, actor/action/resource/outcome, timestamps và schema version** vào canonical payload. Ví dụ cố ý tối giản số field để dễ học.

**Không coi digest không khóa lưu ngay trong cùng bảng là bằng chứng bất biến mạnh.** Nếu một actor có thể sửa cả dữ liệu lẫn digest chuẩn, phép verify nội bộ không phân biệt được lịch sử gốc và lịch sử đã bị viết lại.

## 9. Checkpoint độc lập, HMAC và chữ ký số

Khi cần tăng mức bảo đảm, thiết kế thường bổ sung:

| Thành phần | Mục tiêu |
| --- | --- |
| **Head checkpoint** | Lưu streamId, lastSequence và headHash ở nơi ngoài quyền writer |
| **HMAC-SHA-256** | Xác nhận dữ liệu được tạo bởi bên có secret key |
| **Digital signature** | Ký record/checkpoint bằng private key; bên khác verify bằng public key |
| **WORM archive** | Hạn chế sửa/xóa các segment đã đóng trong thời hạn retention |
| **Independent verifier** | Kiểm chứng từ bản ghi gốc đến checkpoint, không tin kết quả writer tự báo |

Một checkpoint có thể mang các trường sau (giá trị rút gọn, **không phải digest/chữ ký thật**):

~~~json
{
  "streamId": "audit-admin-prod",
  "lastSequence": 10425,
  "headHash": "<full-sha256-hex-in-real-system>",
  "schemaVersion": 1,
  "createdAt": "2026-11-10T03:00:00Z",
  "keyId": "audit-signer-v3"
}
~~~

Ở production, headHash phải có **đủ byte và format chính xác**; checkpoint cần kênh lưu đáng tin, signature/MAC khi thích hợp và kiểm soát quyền tách khỏi writer.

**HMAC không đồng nghĩa non-repudiation giữa nhiều bên cùng biết secret.** Ai nắm HMAC key có thể tạo MAC; chữ ký số với private/public key thích hợp hơn nếu các bên verify không nên nắm khả năng ký. Dù vậy chữ ký vẫn không chứng minh nội dung event do ứng dụng ghi là sự thật; phải bảo vệ quá trình tạo event.

Quản lý khóa cần có KMS/HSM khi phù hợp, keyId/version, rotation, quyền sử dụng, theo dõi và thu hồi theo policy. Không ghi private key/HMAC key vào log, không lưu cùng chỗ để một principal có thể vừa sửa audit vừa sửa checkpoint và key.

## 10. Concurrent writers, sequence và thứ tự sự kiện

Trong nhiều thread hoặc nhiều instance, hai writer có thể cùng lấy headHash cũ rồi tạo **hai nhánh fork** nếu không có đồng bộ. Vì thế:

- Dùng **transactional stream-head lock**, optimistic compare-and-swap hoặc một sequencer có thỏa thuận rõ.
- Không đơn giản SELECT MAX(sequence_no)+1 ngoài transaction rồi hy vọng không collision.
- Áp unique constraint cho (streamId, sequenceNo) và eventId.
- Atomic update stream head cùng event append trong transaction khi có thể.
- Xác định rõ stream: toàn service, từng tenant hoặc từng aggregate.
- Nếu cần thứ tự toàn cục giữa nhiều region, phải thiết kế coordinator/consensus; chỉ sort timestamp không tạo total order đáng tin.

**occurredAt** do node phát event ghi nhận có thể khác **recordedAt** lúc audit store commit do network delay và clock skew. Timestamp UTC có ích để tra cứu, nhưng không đủ làm bằng chứng duy nhất về thứ tự.

Các event trong hai stream riêng biệt không nhất thiết so sánh được bằng sequenceNo. Khi cần quan hệ nhân quả, dùng parentEventId, requestId/traceId hoặc causal metadata theo contract.

## 11. Audit và transaction nghiệp vụ: tránh mất hoặc ghi sai event

Một hệ thống có thể gặp hai lỗi đối xứng:

- Business transaction commit thành công nhưng audit event bị mất → **thiếu lịch sử**.
- Audit event được ghi SUCCESS trước khi business transaction rollback → **lịch sử nói sai kết quả**.

Vì thế phải định nghĩa **thời điểm event được coi là hoàn thành** và quan hệ với transaction:

| Kiến trúc | Điểm mạnh | Cần lưu ý |
| --- | --- | --- |
| Cùng DB transaction: business + audit row | Có thể commit atomically khi cùng database/transaction | DB table chưa chắc bất biến với DBA |
| **Transactional outbox** | Ghi business state và outbox trong một transaction, publish sau commit | Cần retry, dedup và quản lý lag; outbox không phải WORM |
| Ghi audit bền vững trước khi trả thành công | Độ bảo đảm cao cho hành động nhạy cảm | Tăng latency và phụ thuộc audit service |
| Async best-effort logger | Tách đường xử lý nóng | Có thể mất event; không mặc định phù hợp audit bắt buộc |

**Transactional outbox không tự đem lại exactly-once end-to-end**. Worker có thể publish xong nhưng mất ACK rồi publish lại; cần eventId ổn định, dedup tại consumer và giao thức ghi ledger rõ ràng. Bản audit đã được chấp nhận cần có sequence/headHash do audit writer cấp, không đơn giản lấy thứ tự của các callback ứng dụng.

Một job retry tạo hai **attempt** nhưng có thể chỉ có một **event nghiệp vụ logic** hoặc hai event nếu hành vi cần audit từng nỗ lực. Phải phân biệt eventId, attemptId và sequenceNo.

## 12. Durable delivery và xử lý outage

Không thể coi **logger.info(...)** hay một lời gọi publish async trả về thành công là bằng chứng event đã được lưu bền vững. Một logger queue hoặc collector có thể mất dữ liệu khi crash, kill, mất disk hoặc full queue.

Cần xác định:

1. Event được ACK sau khi vào memory, WAL, DB commit hay immutable archive?
2. Nếu audit backend không hoạt động, business service **fail-closed** hay **fail-open với bộ đệm bền vững**?
3. Queue có giới hạn; khi đầy áp dụng backpressure hoặc từ chối hành động nào?
4. Event còn trong outbox sau crash sẽ được replay thế nào?
5. Nếu ACK bị mất, eventId có giúp ngăn duplicate không?
6. Nếu một audit sink gặp lỗi, đã có alert và cơ chế phục hồi/truy xuất bằng chứng chưa?

**Fail-closed** có thể hợp lý với thao tác cấp quyền quản trị, truy cập dữ liệu cực nhạy cảm hoặc hành động bắt buộc audit trước khi cho phép. **Fail-open với durable outbox** có thể phù hợp với hệ thống cần availability cao, nếu đã có cam kết phục hồi và đối soát. Diagnostic logs best effort thường không thỏa mãn audit compliance.

Không có policy chung cho mọi hành động. Hãy phân loại sự kiện theo độ rủi ro, yêu cầu tuân thủ, thời điểm ACK và giới hạn latency được phê duyệt.

## 13. Rotation, segment và phát hiện truncation

Audit volume lớn thường được lưu thành nhiều segment:

~~~text
Segment A: sequence 1..1000, headHash=H1000
Segment B: sequence 1001..2000, initialPreviousHash=H1000
Segment C: sequence 2001..3000, initialPreviousHash=H2000
~~~

Mỗi segment nên mô tả streamId, start/end sequence, schemaVersion, first previousHash, last headHash, thời gian đóng, storage object version và checkpoint reference. Segment/manifest đã chốt cần được bảo vệ khỏi sửa/xóa ngoài policy.

Một verifier cần:

- Xác nhận manifest chứa đủ segment dự kiến.
- Kiểm tra không có sequence gap, duplicate, fork hoặc đảo thứ tự bất hợp lệ.
- Tính lại hash của từng record bằng đúng canonical version.
- Kiểm tra previousHash nối xuyên segment.
- So **headHash + lastSequence** với checkpoint ký hoặc lưu ngoài.
- Kiểm tra retention/lock và trạng thái phân phối tới các replica.

**Truncation attack**: nếu xóa segment C, hash chain A+B vẫn có thể nội bộ hợp lệ. So với checkpoint độc lập có expected lastSequence=3000 mới phát hiện lịch sử bị thiếu.

Nếu attacker có khả năng rehash toàn bộ A+B+C, so với checkpoint đã ký hoặc được giữ độc lập sẽ thấy mismatch. Nếu không có anchor độc lập, phép verify true không có nghĩa lịch sử chưa từng bị thay đổi.

## 14. Đối soát tính đầy đủ với nguồn nghiệp vụ

Ngay cả khi WORM, hash chain và chữ ký hoạt động đúng, **event chưa từng được tạo sẽ không được phát hiện** bằng cách hash lại các event đã lưu. Ví dụ một lỗi code khiến hành động cấp quyền bỏ qua audit publisher: không có record nào bị sửa, nhưng lịch sử vẫn thiếu.

Giải pháp bổ sung:

- Đối soát số business transactions commit với số audit/outbox records theo category.
- Theo dõi outbox unprocessed count, age, retry count và dead-letter.
- Kiểm tra sequence đã cấp và những khoảng chưa cam kết.
- So eventId được business subsystem ghi nhận với eventId vào ledger.
- Cảnh báo pipeline pause, collector drop, key error hoặc signing failure.
- Thử phục hồi backup và so với checkpoint độc lập.
- Audit các thay đổi cấu hình khiến event không còn được phát.

**Hash chain bảo vệ quan hệ giữa các bản ghi hiện có; reconciliation phát hiện sự kiện lẽ ra phải có nhưng không xuất hiện.** Hai lớp này bổ sung cho nhau.

## 15. Security và separation of duties

Mô hình role gợi ý:

| Role | Có thể làm | Không nên được làm |
| --- | --- | --- |
| Business service | Tạo event theo schema, gửi vào audit writer | Sửa/xóa event đã chốt |
| Audit writer | Append, cấp sequence, tạo hash theo contract | Thay retention/key của kho độc lập |
| Audit reader | Tra cứu trong phạm vi phân quyền | Ghi lại lịch sử hoặc thay checkpoint |
| Storage admin | Vận hành capacity, replication | Có khả năng bypass WORM mà không có kiểm soát |
| Key custodian | Quản lý vòng đời khóa và policy ký | Sửa database audit + checkpoint |
| Independent verifier | Đọc và xác minh hash/signature/sequence | Sửa dữ liệu gốc hoặc dấu mốc tin cậy |

Nên log các thao tác bảo mật đối với chính hệ thống audit: đổi quyền, vô hiệu collector, thay retention, legal hold, export, key rotation, backup/restore và truy cập dữ liệu nhạy cảm. Các kênh audit-of-audit cũng cần quyền và lưu giữ phù hợp; không để tất cả phụ thuộc một cơ chế có thể bị tắt đồng thời.

Kiểm tra **least privilege** bằng phép thử được ủy quyền trong staging: application writer không thể UPDATE/DELETE; read-only verifier không có quyền sửa; những thao tác overwrite/delete object đã khóa phải bị từ chối theo mode retention đang áp dụng.

## 16. Sửa sai nghiệp vụ bằng correction event, không ghi đè

Một audit event cũ không nên bị chỉnh thành sự kiện khác chỉ vì trạng thái hiện tại đã thay đổi.

Ví dụ:

~~~text
seq=401 event=ROLE_GRANTED actor=admin-7 principal=member-8
seq=402 event=ROLE_REVOKED actor=admin-7 principal=member-8
seq=403 event=INCIDENT_REVIEWED actor=security-2 ref=case-19
~~~

Nếu phần mềm ghi sai outcome do bug, cần thiết kế **correction event** có reference tới eventId gốc, reason, actor và approval phù hợp. Bản gốc phải được giữ để người kiểm toán thấy lịch sử và quá trình sửa lỗi, thay vì thay event cũ mà không còn dấu vết.

Tuy nhiên correction event không tự chữa một audit pipeline bị mất dữ liệu. Khi phát hiện sự kiện chưa từng được ghi, cần đối soát nguồn nghiệp vụ, ghi nhận incident về gap và xác định rõ event được dựng lại sau sự cố, không ngụy tạo như thể nó đã được ghi đúng thời điểm ban đầu.

## 17. Quyền riêng tư, retention và kho bất biến

Audit log có thể chứa dữ liệu cá nhân, tài chính hoặc business secrets. Khóa WORM quá lâu trước khi phân loại dữ liệu sẽ khó xử lý hơn khi một sự kiện bị phát ra sai.

- **Data minimization:** chỉ ghi event code, actorRef/resourceRef và field cần thiết; không lưu raw password, token, private key, authorization header hoặc full payload.
- **Privacy:** actorRef đôi khi vẫn có thể liên kết tới danh tính; đừng gọi mọi opaque ID là dữ liệu ẩn danh hoàn toàn.
- **Retention:** xác định thời hạn theo loại event và quy định áp dụng; không lưu mãi mãi theo mặc định.
- **Encryption:** bảo vệ khi lưu và truyền, nhưng dữ liệu được mã hóa có thể giải mã bằng khóa; đây không phải redaction hay immutability.
- **Legal hold:** kiểm soát người có thể đặt/bỏ hold và lưu dấu quyết định.
- **Key erasure/crypto-shredding:** chỉ áp dụng khi phù hợp policy, vì có thể làm dữ liệu không thể giải mã nhưng cũng ảnh hưởng verify/khôi phục; không tự coi đó là xóa dữ liệu hợp lệ trong mọi trường hợp.
- **Deletion workflows:** khi hết retention hợp lệ, dữ liệu có thể được hủy theo lifecycle đã duyệt; phải hiểu quy tắc trong cloud mode sử dụng.

Nếu lỡ ghi credential vào kho bất biến, xử lý như **sự cố lộ dữ liệu**: rotate/revoke credential, giảm quyền đọc, xác định mọi bản sao và thực hiện quy trình pháp lý/bảo mật phù hợp. Thay đổi log level sau đó không làm secret đã ghi mất hiệu lực.

## 18. Chạy verifier độc lập

Một verifier nên hoạt động với principal và failure domain khác với audit writer; không chỉ đọc dòng INFO “write succeeded” do writer tự phát.

Quy trình gợi ý:

1. Lấy streamId, segment list và mốc checkpoint từ nơi đã xác thực.
2. Đọc event với quyền read-only, kiểm tra schemaVersion/encoding version.
3. Tính lại hash theo canonical bytes; so hash lưu và previousHash.
4. Xác minh sequence liên tục, không fork, gap hoặc duplicate.
5. So headHash và lastSequence với external checkpoint.
6. Verify HMAC hoặc digital signature bằng keyId và verified keys theo chính sách.
7. Đối chiếu với business/outbox để phát hiện sự kiện không được phát.
8. Kiểm tra retention lock, ingest lag, archival, replication và lịch sử thay đổi quyền.
9. Ghi kết quả, thời điểm, phạm vi, người thực hiện và bằng chứng vào kênh được bảo vệ.

Ví dụ report (minh họa dữ liệu, không phải bằng chứng thật):

~~~json
{
  "streamId": "admin-audit-prod",
  "range": "10401-10425",
  "hashChainValid": true,
  "headCheckpointValid": true,
  "sequenceComplete": true,
  "businessReconciliation": "matched",
  "verifiedAt": "2026-11-10T03:15:00Z"
}
~~~

**hashChainValid=true đơn lẻ không chứng minh đầy đủ tính bất biến.** Phải có anchor/khóa độc lập, kiểm tra completeness và bằng chứng storage policy theo threat model.

## 19. Kiểm thử khi có lỗi và tấn công

| Nhóm | Kịch bản kiểm thử ở môi trường được phép | Kỳ vọng |
| --- | --- | --- |
| Append-only | Application role UPDATE/DELETE bản ghi | Bị chặn |
| Hash chain | Sửa action/actor nhưng giữ hash | Verify phát hiện mismatch |
| Rehash | Sửa nội dung rồi tính lại mọi hash | Trusted anchor/signature không khớp |
| Truncation | Cắt event cuối | Head checkpoint/lastSequence phát hiện |
| Missing event | Publisher bỏ qua event bắt buộc | Business reconciliation phát hiện |
| Concurrency | Nhiều writer cùng append một stream | Sequence duy nhất, không có fork không hợp lệ |
| Crash | Crash giữa commit và publish | Outbox/recovery giữ dữ liệu theo contract |
| Retry | Mất ACK và publish trùng eventId | Dedup/idempotency đúng |
| Storage | Thử overwrite/delete object đã khóa | Storage từ chối theo retention policy |
| Key rotation | Verifier đọc event cũ sau khi đổi key | Xác minh theo keyId và key policy |
| Restore | Restore backup cũ | So checkpoint phát hiện rollback |
| Outage | Collector/queue/WORM storage unavailable | Alert, backpressure/fail mode đúng |
| Privacy | Input chứa token/PII thử nghiệm | Không lưu raw secret ngoài policy |
| Audit-of-audit | Đổi retention hoặc quyền ký | Có dấu vết và phê duyệt |

**Không chạy thử xóa hoặc bypass retention trên dữ liệu production thật ngoài kế hoạch được ủy quyền.** Dùng staging/test object và cấu hình riêng; xác nhận kết quả bằng API/storage logs.

Đối với chương trình Java 17 ở mục 8, smoke test là: hai event ban đầu hợp lệ, sửa action event đầu nhưng giữ hash làm verify false. Nó kiểm tra **tính phát hiện sửa trong bộ nhớ**, không kiểm tra WORM, durable commit, key protection hoặc quyền database.

## 20. Những ngộ nhận phổ biến

| Ngộ nhận | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| “Có SHA-256 là bất biến” | Attacker có thể rehash | Independent anchor, signing, storage controls |
| “Cấm UPDATE là chặn mọi admin” | DBA/owner vẫn có thể thay dữ liệu | Tách quyền, archive ngoài |
| “WORM bảo đảm event đúng” | Writer có thể lưu sự kiện giả | Xác thực nguồn và đối soát |
| “Timestamp tạo thứ tự tuyệt đối” | Clock skew và network delay | Sequence theo stream/causal metadata |
| “Log append thành công là durable” | Async queue có thể mất event | ACK/commit contract, durable outbox |
| “Chain verify true thì không mất event” | Tail truncation và missing event | Checkpoint + reconciliation |
| “HMAC chứng minh mọi cá nhân đã ký” | Ai biết secret đều tạo MAC được | Ký số và key separation khi cần |
| “Audit bất biến phải giữ vĩnh viễn” | Privacy/retention có vòng đời | Khóa theo hạn, xóa theo policy |
| “Có backup nên không cần verify” | Backup cũng có thể sai/cũ | Restore drill + checkpoint |
| “Xóa event sai rồi ghi lại” | Mất lịch sử thay đổi | Correction event kèm reference |
| “Không có quyền DELETE ở API là đủ” | Có đường DB/storage ngoài API | Kiểm tra privilege và threat model |
| “Exactly once do broker đảm bảo hết” | ACK loss/retry ở nhiều boundary | eventId, idempotency, outbox |

## 21. Checklist triển khai tính bất biến audit

| Thành phần | Điều kiện tối thiểu |
| --- | --- |
| Event semantics | Định nghĩa hành động phải audit và thời điểm outcome được coi là thật |
| Audit schema | eventId, streamId, sequence, actor/action/resource/outcome và schemaVersion |
| Privacy | Không có credential/payload không cần thiết; retention được duyệt |
| Append-only write | Role ứng dụng không thể UPDATE/DELETE lịch sử |
| Durable delivery | Cam kết ACK rõ, outbox/retry/backpressure/failure mode được kiểm thử |
| Canonical bytes | Có version, field order, encoding và tests tương thích |
| Hash chain | Liên kết previousHash và verify toàn stream |
| Trusted checkpoint | lastSequence + headHash lưu ngoài quyền writer |
| HMAC/signature | Nếu có, quản lý keyId, rotation, signer/verifier roles |
| WORM/retention | Lock/versioning/mode và quyền bypass được xác minh |
| Concurrency | Atomic sequence/head, không sinh fork ngoài policy |
| Verification | Verifier độc lập kiểm tra content, chain, anchor và completeness |
| Monitoring | Alert về ingest gap, mismatch, drop, signing failure, pipeline pause |
| Restore | Backup/replication và đối chiếu checkpoint khi restore |
| Correction | Sự kiện mới ghi nhận reversal/sửa sai thay vì overwrite |
| Security operations | Thay đổi audit policy, quyền và khóa cũng được audit |

**Kết luận:** tính bất biến audit không chỉ là hạn chế câu lệnh UPDATE. Một audit trail đáng tin cần **event đúng và đầy đủ, append-only/WORM theo đúng quyền và retention, hash chain với canonical encoding, checkpoint hoặc signature ở vùng tin cậy độc lập, delivery bền vững, xác minh thường xuyên và chính sách privacy**. Trong Java, MessageDigest và các API database/transaction là những công cụ xây dựng, nhưng mức bảo đảm cuối cùng đến từ toàn bộ kiến trúc và cách vận hành.