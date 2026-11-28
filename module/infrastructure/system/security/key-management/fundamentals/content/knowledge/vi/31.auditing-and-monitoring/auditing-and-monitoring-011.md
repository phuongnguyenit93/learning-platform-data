# Audit record integrity

Audit log chỉ có giá trị khi tổ chức có thể tin rằng bản ghi phản ánh đúng những gì hệ thống đã ghi nhận và không bị sửa đổi trái phép sau đó. **Audit record integrity** là khả năng bảo vệ và kiểm chứng tính toàn vẹn của từng bản ghi cũng như toàn bộ chuỗi sự kiện: phát hiện việc sửa nội dung, chèn bản ghi giả, xóa bản ghi, đổi thứ tự hoặc cắt bỏ phần cuối của log.

Trong quản lý khóa mật mã, audit record thường ghi lại ai đã tạo, truy cập, sử dụng, export, rotate, disable hoặc destroy khóa. Nếu người có quyền quản trị KMS/HSM cũng có thể sửa hoặc xóa log mà không để lại dấu vết, tổ chức sẽ khó phát hiện lạm dụng và khó điều tra sự cố. Vì vậy, log cần có cơ chế kiểm chứng mật mã, lưu trữ chống sửa đổi, phân tách nhiệm vụ và bản sao bằng chứng ở một miền tin cậy độc lập.

Không có một cơ chế đơn lẻ nào làm audit log “không thể bị giả mạo” trong mọi tình huống. Hash chain, chữ ký số, HMAC, WORM storage và checkpoint giải quyết các rủi ro khác nhau; cần kết hợp chúng theo threat model và hiểu rõ giới hạn của từng cơ chế.

## 1. Audit record integrity bảo vệ điều gì?

Tính toàn vẹn của audit record tập trung vào việc phát hiện hoặc ngăn các hành vi sau:

- **Modification:** thay đổi principal, key ID, action, outcome, timestamp hoặc metadata sau khi event đã được ghi.
- **Insertion:** chèn một event giả, ví dụ tạo bản ghi thành công cho một thao tác chưa từng được cho phép.
- **Deletion:** xóa một event bất lợi hoặc một khoảng thời gian trong log.
- **Reordering:** đổi thứ tự event để làm sai lệch timeline.
- **Replay/duplication:** phát lại event cũ hoặc ghi cùng một event nhiều lần để gây hiểu nhầm.
- **Truncation:** cắt bỏ phần cuối của log để che giấu các thao tác mới nhất.
- **Source substitution:** thay nguồn phát log hoặc giả mạo danh tính workload gửi event.

Integrity khác với các thuộc tính khác:

| Thuộc tính | Câu hỏi cần trả lời | Kiểm soát thường dùng |
|---|---|---|
| Integrity | Bản ghi có bị sửa, chèn, xóa hoặc đổi thứ tự không? | Chữ ký số, HMAC, hash chain, immutable storage |
| Authenticity | Bản ghi đến từ nguồn hoặc danh tính nào? | mTLS, workload identity, chữ ký số, xác thực agent |
| Confidentiality | Ai được đọc nội dung log? | Mã hóa khi truyền/lưu, quyền đọc tối thiểu |
| Availability | Log có còn truy xuất được khi điều tra không? | Replication, backup, retention và recovery test |
| Completeness | Có event nào bị mất trước khi đến kho log không? | Sequence number, gap detection, durable queue, reconciliation |

Một chữ ký hợp lệ chứng minh dữ liệu được ký bởi chủ thể giữ khóa ký tương ứng và chưa bị thay đổi sau khi ký; nó không tự chứng minh event là sự thật nếu nguồn phát event đã bị chiếm quyền trước khi ký. Cần bảo vệ cả nguồn event, đường truyền, khóa ký và kho lưu trữ.

## 2. Threat model cho audit log

Trước khi chọn cơ chế, cần xác định attacker có thể kiểm soát thành phần nào:

| Đối tượng tấn công | Rủi ro | Kiểm soát cần cân nhắc |
|---|---|---|
| Người dùng ứng dụng | Tạo request độc hại hoặc làm phát sinh lượng event lớn | Xác thực nguồn, rate limit, ghi nhận cả allow và deny |
| Workload bị xâm nhập | Giả mạo context nghiệp vụ hoặc bỏ qua logger ứng dụng | Audit độc lập tại KMS/HSM và policy engine |
| Người vận hành hệ thống | Sửa file log, xóa event hoặc thay cấu hình collector | Tách nhiệm vụ, quyền tối thiểu, immutable archive |
| Quản trị viên log platform | Sửa/xóa dữ liệu tập trung | WORM/Object Lock, external checkpoint, audit quyền quản trị |
| Kẻ tấn công chiếm máy chủ | Sửa log cục bộ trước khi gửi đi | Gửi log sớm tới miền độc lập, ký event tại nguồn tin cậy |
| Kẻ tấn công chiếm pipeline | Chặn, phát lại, đảo thứ tự hoặc thay event | mTLS, sequence, event ID, hash chain và reconciliation |
| Người có quyền quản lý khóa ký log | Tạo chữ ký hợp lệ cho event giả | HSM, dual control, policy ký, giám sát thao tác ký |

Nếu attacker kiểm soát cả nguồn event, khóa ký, pipeline và kho log, họ có thể tạo ra một lịch sử giả rất khó phân biệt. Thiết kế cần phân tách các miền tin cậy: nguồn phát, hệ thống ký, hệ thống lưu trữ và nơi giữ checkpoint/bằng chứng độc lập.

## 3. Chuẩn hóa bản ghi trước khi kiểm tra integrity

Chữ ký hoặc MAC chỉ bảo vệ chính xác những byte được đưa vào thuật toán. Nếu cùng một event có thể được serialize thành nhiều chuỗi khác nhau, hoặc hai event khác nhau tạo cùng một chuỗi byte do ghép trường không rõ ranh giới, việc kiểm chứng sẽ không đáng tin cậy.

Một định dạng canonical cần quy định:

- Schema version và thứ tự trường cố định.
- Encoding thống nhất, thường là UTF-8.
- Quy tắc biểu diễn timestamp, số, boolean, null và giá trị Unicode.
- Quy tắc xử lý field vắng mặt, field null và field mặc định.
- Cách biểu diễn byte array, enum và identifier.
- Quy tắc loại bỏ hoặc từ chối duplicate JSON keys.
- Quy tắc xử lý trường mở rộng và phiên bản schema mới.

Có thể dùng một định dạng canonical đã được chuẩn hóa, hoặc tự định nghĩa serialization nhị phân có version và length-prefix rõ ràng. Không nên nối chuỗi đơn giản kiểu `principal + keyId + action` vì ranh giới trường có thể mơ hồ. Ví dụ `ab` + `c` và `a` + `bc` đều tạo chuỗi `abc`.

Các trường ảnh hưởng tới ý nghĩa bảo mật phải nằm trong dữ liệu được ký/MAC: event ID, sequence, thời gian, principal, key ID/version, action, authorization decision, outcome, nguồn phát và previous hash. Nếu một trường không được bảo vệ, attacker có thể thay đổi trường đó mà chữ ký vẫn hợp lệ.

## 4. Hash và hash chain

Hash function như SHA-256 nhận dữ liệu đầu vào và tạo digest có độ dài cố định. Nếu event bị thay đổi, digest tính lại thường khác digest đã lưu. Tuy nhiên, chỉ lưu `SHA-256(event)` cạnh event trong cùng một kho không đủ chống attacker có quyền ghi: họ có thể sửa event rồi tính lại digest.

**Hash chain** liên kết mỗi record với record trước đó:

\[
H_0 = H(\text{genesis})
\]

\[
H_i = H(H_{i-1} \parallel C_i)
\]

Trong đó:

- `H` là hash function được lựa chọn, ví dụ SHA-256.
- `H(i-1)` là digest của record trước.
- `C(i)` là biểu diễn canonical của record hiện tại.
- `||` biểu thị phép nối byte theo định dạng đã quy định.

Nếu một record ở giữa bị sửa hoặc xóa, digest của record kế tiếp không còn khớp. Nếu event bị đổi thứ tự, liên kết previous hash cũng bị sai. Mỗi record nên có sequence number tăng dần trong phạm vi một stream/partition để phát hiện gap và duplicate.

Hash chain có một giới hạn quan trọng: người có quyền viết lại toàn bộ chuỗi từ đầu có thể tính lại tất cả digest. Kẻ tấn công cũng có thể cắt bỏ phần cuối nếu không có bằng chứng độc lập ghi nhận digest mới nhất. Vì vậy, hash chain cần được neo bằng checkpoint gửi ra một miền tin cậy khác.

## 5. HMAC và chữ ký số

Hash chain giúp liên kết record; HMAC hoặc chữ ký số giúp xác thực tính toàn vẹn và nguồn ký.

| Cơ chế | Cách hoạt động | Ưu điểm | Giới hạn |
|---|---|---|---|
| SHA-256 digest | Hash nội dung event | Nhanh, phát hiện thay đổi khi digest được bảo vệ | Digest đặt cạnh event trong kho có thể bị attacker tính lại |
| HMAC-SHA-256 | Dùng khóa bí mật chung để tạo MAC | Hiệu năng tốt, xác thực event với bên giữ secret key | Bên có khóa xác minh cũng có thể tạo MAC giả |
| Chữ ký số | Khóa riêng ký, khóa công khai xác minh | Có thể tách quyền ký và quyền xác minh; verifier không cần giữ private key | Cần bảo vệ private key, quản lý chứng thư/key version và kiểm tra trạng thái khóa |

Với audit log quan trọng, chữ ký số bất đối xứng thường hữu ích vì hệ thống lưu trữ và auditor chỉ cần public key để xác minh, không cần quyền tạo chữ ký. Private signing key có thể được giữ trong HSM/KMS; quyền ký cần giới hạn theo workload và loại event.

HMAC phù hợp khi writer và verifier thuộc cùng miền tin cậy hoặc khi hệ thống chấp nhận rằng bên xác minh cũng có khả năng tạo MAC. Nếu dùng HMAC, không phân phối khóa xác minh rộng rãi cho mọi auditor; giữ quyền tạo MAC trong một service riêng và kiểm soát việc truy cập secret.

## 6. Chữ ký số cho audit record

Một quy trình ký event có thể gồm:

1. Tạo event với schema version, event ID, sequence và timestamp.
2. Canonicalize các trường cần bảo vệ thành byte array xác định.
3. Ký byte array bằng private signing key.
4. Gắn chữ ký, key ID của khóa ký và thuật toán chữ ký vào envelope event.
5. Gửi event cùng chữ ký tới collector qua kênh đã xác thực.
6. Collector xác minh chữ ký bằng public key tin cậy trước khi chấp nhận event.
7. Lưu event, chữ ký, key ID và kết quả kiểm tra theo retention policy.

Ví dụ Java dưới đây minh họa việc ký và xác minh một chuỗi byte đã canonicalize. Phần canonicalization cần được triển khai theo schema cố định; không ký trực tiếp một JSON được serialize tùy ý.

```java
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public final class AuditRecordSigner {
    public static byte[] sign(byte[] canonicalRecord, PrivateKey signingKey)
            throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(signingKey);
        signature.update(canonicalRecord);
        return signature.sign();
    }

    public static boolean verify(
            byte[] canonicalRecord,
            byte[] signatureBytes,
            PublicKey verificationKey) throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initVerify(verificationKey);
        signature.update(canonicalRecord);
        return signature.verify(signatureBytes);
    }
}
```

Trong production, `signingKey` nên là key handle do provider/HSM quản lý nếu yêu cầu bảo vệ cao. Ứng dụng cần kiểm tra provider thực tế, thuật toán và kích thước khóa theo chính sách hiện hành. Không export private key chỉ để ký log; truyền đối tượng khóa tới provider để thao tác ký diễn ra trong ranh giới bảo vệ nếu provider hỗ trợ.

Verifier cần biết public key nào có hiệu lực tại thời điểm ký. Event nên chứa `signingKeyId` và phiên bản thuật toán; kho metadata tin cậy ánh xạ ID sang public key và thời gian hiệu lực. Không tin public key đính kèm event nếu không xác thực được nguồn gốc của nó.

## 7. Kết hợp chữ ký với hash chain

Chữ ký trên từng record bảo vệ nội dung record. Hash chain bổ sung quan hệ thứ tự giữa các record. Một envelope event có thể chứa:

```json
{
  "streamId": "kms-audit-prod-01",
  "sequence": 4821,
  "eventId": "evt-4821",
  "eventTime": "2026-11-28T04:30:00.125Z",
  "keyId": "kms/prod/customer-data-kek",
  "principalId": "workload:customer-api",
  "action": "Decrypt",
  "outcome": "SUCCESS",
  "previousRecordDigest": "base64url(...)",
  "signingKeyId": "audit-signing-key-v4",
  "signatureAlgorithm": "SHA256withRSA",
  "signature": "base64url(...)"
}
```

Trong ví dụ, `previousRecordDigest` là digest của envelope record trước đó theo một định dạng đã quy định, bao gồm nội dung canonical và chữ ký của record trước. Chữ ký hiện tại bao phủ `previousRecordDigest`, `streamId`, `sequence` và các trường event. Nhờ đó, việc sửa hoặc xóa record giữa chuỗi làm hỏng xác minh của record tiếp theo.

Với nhiều writer đồng thời, không nên để các tiến trình tự tăng sequence và cập nhật previous hash mà không có cơ chế đồng bộ. Có thể phân vùng stream theo nguồn hoặc workload, dùng một sequencer/append service, hoặc dùng transactional append bảo đảm một thứ tự duy nhất trong từng partition. Mỗi stream cần có genesis record và quy tắc xử lý khi writer khởi động lại.

## 8. Canonicalization và chống nhập nhằng dữ liệu

Canonicalization là bước thiết yếu nhưng thường bị xem nhẹ. Ví dụ, hai JSON sau có cùng ý nghĩa ở một số parser nhưng khác byte:

```json
{"action":"Decrypt","keyId":"key-1"}
```

```json
{
  "keyId": "key-1",
  "action": "Decrypt"
}
```

Nếu ký trực tiếp chuỗi JSON, hai dạng trên tạo chữ ký khác nhau. Điều này không sai nếu hệ thống ký và xác minh cùng dùng đúng một byte sequence; vấn đề xuất hiện khi mỗi bên tự parse rồi serialize lại theo quy tắc khác nhau.

Các lựa chọn:

- Dùng canonical JSON theo một chuẩn được chỉ định và kiểm thử interoperability.
- Dùng CBOR canonical hoặc định dạng nhị phân có schema cố định.
- Dùng length-prefix cho từng trường, encoding rõ ràng và version format.
- Chuẩn hóa timestamp, Unicode, numeric representation và null handling.
- Từ chối trường trùng tên, field không hợp lệ hoặc cấu trúc không được schema cho phép.

Không nên chỉ ký một tập con trường rồi cho phép những trường khác ảnh hưởng đến quyết định bảo mật. Nếu `authorizationDecision`, `keyVersion` hoặc `principalId` bị bỏ khỏi phần canonical, attacker có thể sửa ý nghĩa event mà chữ ký vẫn hợp lệ.

## 9. Checkpoint và chống cắt bỏ log

Hash chain có thể phát hiện sửa đổi ở giữa nhưng không tự phát hiện việc xóa phần cuối nếu verifier không biết chuỗi trước đó phải dài đến đâu. **Checkpoint** giải quyết vấn đề này bằng cách ghi digest mới nhất, sequence và stream ID ra một miền tin cậy độc lập theo chu kỳ hoặc sau mỗi batch.

Checkpoint có thể được:

- Gửi tới tài khoản lưu trữ độc lập với tài khoản quản trị log.
- Ghi vào dịch vụ transparency log hoặc hệ thống append-only khác.
- Ký bằng khóa riêng audit và gửi cho auditor hoặc hệ thống giám sát độc lập.
- Đưa vào kho lưu trữ có retention lock và timestamp tin cậy.
- Đối chiếu định kỳ giữa nguồn phát, collector và archive.

Ví dụ checkpoint:

```json
{
  "streamId": "kms-audit-prod-01",
  "lastSequence": 5000,
  "lastRecordDigest": "base64url(...)",
  "checkpointTime": "2026-11-28T04:35:00Z",
  "signingKeyId": "audit-checkpoint-key-v2",
  "signature": "base64url(...)"
}
```

Nếu kho log sau đó chỉ có đến sequence 4990 nhưng checkpoint độc lập đã ghi 5000, hệ thống có bằng chứng rằng ít nhất 10 record cuối đã bị mất hoặc bị cắt. Checkpoint cần được tạo và chuyển ra ngoài miền có thể bị cùng một attacker kiểm soát với log chính.

## 10. WORM storage và immutable retention

WORM (Write Once, Read Many) hoặc immutable object storage giúp ngăn sửa/xóa object trong thời gian retention được khóa. Cơ chế này bổ sung cho chữ ký và hash chain:

- Chữ ký giúp kiểm chứng ai ký và nội dung có bị thay đổi không.
- Hash chain giúp kiểm tra liên kết và thứ tự record.
- Checkpoint giúp phát hiện cắt bỏ phần cuối.
- WORM/retention lock giúp ngăn hoặc hạn chế việc sửa/xóa bản lưu trong thời hạn đã cấu hình.

Khi cấu hình immutable storage, cần xác định retention period, legal hold, quyền tạo object, quyền đọc, quyền quản trị retention và quy trình hết hạn. Người có quyền quản trị tài khoản lưu trữ không nên đồng thời có thể rút ngắn retention hoặc xóa audit evidence mà không có kiểm soát độc lập.

WORM không chứng minh event gốc là đúng. Nếu nguồn gửi event giả trước khi object được khóa, WORM chỉ bảo vệ bản ghi giả khỏi bị sửa sau đó. Vì vậy cần xác thực nguồn, ký event và kiểm soát pipeline trước khi lưu bất biến.

## 11. Trusted timestamp và thứ tự sự kiện

Timestamp giúp dựng timeline nhưng không tự bảo vệ integrity. Một host bị xâm nhập có thể đặt đồng hồ sai hoặc tạo event với thời gian tùy ý. Nên lưu cả:

- `eventTime`: thời điểm nguồn ghi nhận thao tác.
- `ingestTime`: thời điểm collector nhận event.
- `sequence`: thứ tự trong một stream/partition.
- `checkpointTime`: thời điểm digest chuỗi được neo độc lập.

Đồng bộ đồng hồ bằng nguồn thời gian tin cậy và giám sát clock drift. Với hệ thống cần bằng chứng thời gian mạnh hơn, có thể dùng dịch vụ timestamp authority theo chuẩn phù hợp. Tuy nhiên, timestamp token cũng cần được xác minh chữ ký và chuỗi tin cậy.

Không sắp xếp log chỉ bằng timestamp khi điều tra. Clock skew, mạng trễ và event đến không theo thứ tự có thể khiến thứ tự hiển thị khác thứ tự xử lý. Sequence và correlation ID giúp tái dựng quan hệ chính xác hơn trong phạm vi được bảo đảm.

## 12. Bảo vệ khóa dùng để ký audit

Khóa ký audit là một tài sản mật mã đặc biệt: nếu bị lộ, attacker có thể tạo event giả có chữ ký hợp lệ. Vì vậy:

- Tạo khóa ký audit riêng, không tái sử dụng khóa ký ứng dụng hoặc khóa dữ liệu.
- Ưu tiên private key non-exportable trong HSM/KMS nếu phù hợp.
- Chỉ cấp quyền ký cho audit agent hoặc signing service được kiểm soát.
- Tách quyền ký khỏi quyền xác minh; auditor chỉ cần public key.
- Ghi audit riêng cho việc sử dụng, export, rotate và thay đổi policy của khóa ký audit.
- Bảo vệ public key, certificate chain, key ID và metadata hiệu lực để verifier chọn đúng khóa.
- Có kế hoạch backup/recovery phù hợp; không tạo bản sao plaintext ngoài ranh giới bảo vệ.
- Xoay vòng khóa ký có overlap để verifier vẫn kiểm tra được record cũ.

Khi khóa ký bị xâm phạm, cần xác định khoảng thời gian và record có thể bị ký giả. Thu hồi khóa ký hiện tại không làm chữ ký cũ tự động mất hiệu lực; verifier cần biết trạng thái tin cậy của khóa tại thời điểm ký, thời điểm phát hiện compromise và checkpoint đã được neo trước sự cố.

## 13. Quy trình xác minh audit record

Một verifier có thể thực hiện các bước sau:

1. Kiểm tra schema version và parse event theo quy tắc nghiêm ngặt.
2. Xác minh nguồn gửi và kênh truyền đã được xác thực.
3. Tạo lại canonical bytes từ các trường được quy định.
4. Tìm public key tin cậy theo `signingKeyId` và thời gian hiệu lực.
5. Xác minh chữ ký số hoặc HMAC.
6. Kiểm tra `streamId`, sequence và `previousRecordDigest` với record trước.
7. Đối chiếu digest mới nhất với checkpoint độc lập.
8. Kiểm tra duplicate event ID, gap sequence, event đến trễ và replay.
9. Đưa record không hợp lệ vào quarantine; không tự động bỏ qua lỗi hoặc ghi đè bằng bản mới.
10. Ghi lại kết quả verification và cảnh báo nếu phát hiện sai lệch.

Kết quả xác minh nên phân biệt `VALID`, `INVALID_SIGNATURE`, `CHAIN_MISMATCH`, `SEQUENCE_GAP`, `CHECKPOINT_MISMATCH`, `UNKNOWN_SIGNING_KEY` và `SCHEMA_ERROR`. Không gộp mọi lỗi thành một trạng thái “log không hợp lệ” vì cách xử lý và mức độ nghiêm trọng khác nhau.

## 14. Xử lý event trùng, mất và đến sai thứ tự

Pipeline phân tán có thể retry khi collector timeout, vì vậy một event có thể được gửi nhiều lần. Dùng `eventId` duy nhất và idempotent ingestion để không tạo nhiều bản ghi nghiệp vụ cho cùng một event. Nếu cần lưu lần gửi lại, ghi nhận riêng delivery attempt thay vì nhân đôi event gốc.

Sequence number nên được cấp tại một nguồn có thứ tự rõ ràng. Với nhiều partition, sequence chỉ có ý nghĩa trong từng partition; không giả định có một thứ tự toàn cục nếu kiến trúc không cung cấp. Khi phát hiện gap, hệ thống cần yêu cầu resend hoặc đánh dấu khoảng thiếu để điều tra.

Không tự động sắp xếp lại record rồi ký lại để “sửa” chain. Việc phục hồi cần giữ nguyên bằng chứng gốc, ghi nhận thao tác sửa pipeline và tạo checkpoint mới theo quy trình được phê duyệt.

## 15. Giới hạn của các cơ chế integrity

| Cơ chế | Phát hiện tốt | Không tự giải quyết |
|---|---|---|
| Hash đơn | Thay đổi nội dung khi digest đáng tin cậy | Attacker có thể tính lại digest nếu sửa được cả event và digest |
| Hash chain | Sửa, xóa giữa chuỗi, đổi thứ tự | Viết lại toàn chuỗi hoặc cắt đuôi nếu không có checkpoint |
| HMAC | Sửa nội dung bởi người không có MAC key | Người có MAC key có thể tạo event giả; không tách quyền verify khỏi sign |
| Chữ ký số | Sửa nội dung và giả mạo chữ ký nếu private key được bảo vệ | Nguồn bị chiếm quyền có thể ký event giả; private key compromise làm mất tin cậy |
| WORM storage | Sửa/xóa object trong thời hạn retention | Event giả được ghi từ đầu; cấu hình retention hoặc quyền quản trị sai |
| External checkpoint | Cắt bỏ phần log sau checkpoint | Event bị giả trước khi checkpoint; checkpoint không thường xuyên tạo cửa sổ rủi ro |
| Trusted timestamp | Bằng chứng thời điểm gắn với dữ liệu đã ký | Tính đúng đắn của event và completeness của nguồn |

Không nên mô tả một hệ thống là “tamper-proof” chỉ vì dùng hash chain hoặc WORM. Cách diễn đạt chính xác hơn là hệ thống có khả năng phát hiện hoặc ngăn một số kiểu sửa đổi theo threat model đã xác định.

## 16. Checklist triển khai Audit record integrity

- Xác định threat model và các miền tin cậy: nguồn event, signing service, pipeline, storage và checkpoint.
- Chuẩn hóa schema, encoding và canonicalization; ký tất cả trường ảnh hưởng tới ý nghĩa bảo mật.
- Dùng event ID, sequence và stream/partition ID để phát hiện duplicate, gap và reorder.
- Liên kết record bằng hash chain hoặc Merkle structure theo quy mô và yêu cầu.
- Dùng HMAC hoặc chữ ký số; hiểu rõ ai có thể tạo MAC/chữ ký và ai chỉ có thể verify.
- Bảo vệ signing key trong KMS/HSM; tách key audit khỏi key ứng dụng và dữ liệu.
- Neo checkpoint định kỳ vào miền lưu trữ độc lập để phát hiện truncation.
- Dùng WORM/immutable retention cho audit archive và bảo vệ quyền quản trị retention.
- Xác thực nguồn event bằng workload identity/mTLS và bảo vệ agent/collector.
- Đồng bộ thời gian, lưu eventTime/ingestTime và giám sát clock drift.
- Xử lý duplicate, out-of-order, gap, retry và event bị drop có kiểm soát.
- Có quy trình verify, quarantine, alert và điều tra khi chữ ký/chain/checkpoint sai.
- Kiểm thử khả năng phát hiện sửa, chèn, xóa, reorder, replay và truncate.
- Diễn tập key compromise, key rotation, recovery và xác minh chữ ký lịch sử.

Audit record integrity cần bảo vệ cả nội dung từng event lẫn quan hệ giữa các event và bằng chứng về sự tồn tại của log theo thời gian. Canonicalization giúp mọi bên kiểm tra cùng một dữ liệu; chữ ký hoặc HMAC xác thực nội dung; hash chain phát hiện thay đổi thứ tự; checkpoint và immutable storage giúp phát hiện hoặc ngăn cắt bỏ, sửa xóa. Khi khóa ký, nguồn phát, pipeline và kho log được tách biệt và kiểm toán, tổ chức có thể tin cậy hơn vào bằng chứng phục vụ giám sát, điều tra và quản trị vòng đời khóa.

## Tài liệu tham khảo

- [NIST SP 800-92: Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
- [NIST SP 800-53 Rev. 5: Security and Privacy Controls for Information Systems and Organizations](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [RFC 9162: Certificate Transparency Version 2.0](https://www.rfc-editor.org/rfc/rfc9162)
- [RFC 8785: JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785)
- [Java SE API: `java.security.Signature`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html)
- [Java SE API: `java.security.MessageDigest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
