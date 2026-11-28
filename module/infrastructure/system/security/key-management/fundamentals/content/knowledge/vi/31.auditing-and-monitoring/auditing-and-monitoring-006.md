# Key revoked event

Key revoked event là sự kiện audit hoặc monitoring ghi nhận một khóa mật mã đã bị thu hồi, bị đánh dấu không còn được tin cậy hoặc không còn được phép sử dụng theo chính sách. Sự kiện này giúp các hệ thống phụ thuộc nhận biết thay đổi trạng thái tin cậy, dừng sử dụng khóa bị ảnh hưởng, đánh giá dữ liệu liên quan và lưu bằng chứng phục vụ điều tra.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, key revoked event kết nối vòng đời khóa với audit và monitoring. Thu hồi khóa có thể xuất phát từ nghi ngờ lộ key material, thay đổi chính sách, hết thời hạn tin cậy hoặc yêu cầu vận hành. Hệ thống phải ghi rõ ai thực hiện, khóa nào bị ảnh hưởng, lý do, thời điểm hiệu lực và các hành động tiếp theo. Sự kiện không được chứa key material, private key, secret hoặc plaintext data key.

## 1. Key revoked event là gì?

Key revoked event là bản ghi có cấu trúc mô tả việc một khóa hoặc một phiên bản khóa bị thu hồi. Đây là một domain/security event có thể được phát ra bởi KMS, HSM, CA, hệ thống quản lý khóa hoặc control plane của ứng dụng.

Một event có thể được tạo khi:

- Quản trị viên thu hồi một key version do nghi ngờ bị lộ.
- CA thu hồi chứng chỉ chứa public key vì private key tương ứng bị compromise.
- Một key không còn được chấp nhận theo chính sách hoặc tiêu chuẩn mật mã.
- Một credential hoặc principal bị xâm nhập khiến tổ chức quyết định vô hiệu hóa key liên quan.
- Một khóa cũ bị thay thế và không còn được phép dùng cho thao tác mới.

Event cần mô tả một thay đổi có ý nghĩa bảo mật. Chỉ ghi một dòng log như “key revoked” mà không có định danh khóa, actor, lý do và thời điểm sẽ không đủ để hệ thống phản ứng hoặc điều tra.

Thu hồi là một quyết định về trạng thái tin cậy và quyền sử dụng. Nó không nhất thiết đồng nghĩa key material đã bị xóa khỏi mọi bản sao, HSM, backup, cache hoặc thiết bị ngoại tuyến.

## 2. Phân biệt revoke, disable, expire và destroy

Các nền tảng KMS/HSM và PKI không dùng cùng một mô hình trạng thái. Cần chuẩn hóa ý nghĩa nghiệp vụ trước khi tạo event:

| Hành động/trạng thái | Ý nghĩa | Khả năng đảo ngược | Hệ quả thường gặp |
|---|---|---|---|
| Revoke | Tuyên bố key hoặc credential không còn được tin cậy/được phép dùng theo chính sách | Tùy hệ thống; quyết định thu hồi thường không nên tự động đảo ngược | Relying systems phải ngừng chấp nhận key theo policy |
| Disable / Deactivate | Tạm ngăn thao tác bằng key trong một dịch vụ hoặc thiết bị | Thường có thể bật lại nếu policy cho phép | Thao tác mật mã mới có thể bị từ chối, dữ liệu cũ vẫn còn |
| Expire | Hết thời hạn hiệu lực được cấu hình | Thường cần gia hạn hoặc cấp phiên bản mới | Không chấp nhận key/certificate sau thời điểm hết hạn |
| Destroy / Delete | Xóa hoặc làm mất khả năng sử dụng key material theo cơ chế của hệ thống | Có thể không thể đảo ngược | Có thể mất khả năng giải mã dữ liệu đã mã hóa bằng key đó |

Một số KMS không có trạng thái tên là Revoked cho symmetric key. Nền tảng có thể biểu diễn quyết định thu hồi bằng DisableKey, thay đổi key policy, thu hồi grant hoặc thao tác tương đương. Với chứng chỉ X.509, CA có thể công bố trạng thái thu hồi qua CRL hoặc OCSP. Vì vậy, event chuẩn hóa nên giữ cả sự kiện gốc của nhà cung cấp và trạng thái nghiệp vụ đã ánh xạ.

Không được coi disable là destroy. Disable thường chặn thao tác qua dịch vụ nhưng không xóa key material; destroy có thể làm dữ liệu không thể khôi phục. Cũng không được giả định revoke tự động xóa mọi bản sao key đã xuất hoặc mọi plaintext data key đã được cấp trước đó.

## 3. Vì sao key revoked event quan trọng?

Nếu một khóa bị thu hồi nhưng ứng dụng, gateway, cache hoặc hệ thống xác minh vẫn tiếp tục chấp nhận nó, quyết định bảo mật chưa được thực thi đầy đủ. Event là tín hiệu để các thành phần liên quan cập nhật trạng thái và hành động nhất quán.

Key revoked event hỗ trợ:

- **Phát hiện:** nhận biết một khóa bị thu hồi do compromise, hết hạn hoặc thay đổi chính sách.
- **Phân phối trạng thái:** thông báo cho dịch vụ xác minh chữ ký, giải mã, cấp data key hoặc kiểm tra chứng chỉ.
- **Giới hạn thiệt hại:** ngăn các yêu cầu mới dùng key đã bị thu hồi sau khi trạng thái được áp dụng.
- **Điều tra:** liên kết quyết định thu hồi với actor, ticket, incident và thao tác trước đó.
- **Tuân thủ:** chứng minh thời điểm, lý do và quy trình phê duyệt khi thu hồi.
- **Khôi phục:** kích hoạt chuyển sang key version hoặc credential thay thế.

Event chỉ có ích khi được phát hành đáng tin cậy, truyền tới đúng consumer và được xử lý trong thời gian phù hợp với mức rủi ro.

## 4. Nguồn phát sinh sự kiện thu hồi

Các nguồn có thể phát sinh hoặc cung cấp bằng chứng cho key revoked event:

| Nguồn | Ví dụ tín hiệu | Nội dung cần thu thập |
|---|---|---|
| KMS control plane | Disable key, revoke grant, thay đổi key policy, scheduled deletion | Key ID/version, actor, action, request ID, trạng thái |
| HSM | Thay đổi key object, thu hồi quyền client, disable partition hoặc credential | Device/partition, object reference, principal, thao tác |
| Certificate Authority | Thu hồi certificate do compromise, cessation of operation hoặc lý do chính sách | Serial number, issuer, reason code, revocation time |
| Key management service | Đánh dấu key version bị compromise hoặc ngừng tin cậy | Key version, lý do, thời điểm hiệu lực, kế hoạch thay thế |
| Incident response system | Quyết định thu hồi sau khi phát hiện credential hoặc host bị xâm nhập | Incident ID, phạm vi, người phê duyệt, hành động |
| Policy engine | Một key không còn đáp ứng thuật toán hoặc cryptoperiod | Policy version, key reference, lý do từ chối |

Không phải nguồn nào cũng phát một event có tên “KeyRevoked”. Có hệ thống chỉ cung cấp audit record cho thao tác DisableKey hoặc RevokeCertificate. Lớp tích hợp cần ánh xạ sự kiện gốc sang schema chuẩn mà không làm mất tên hành động ban đầu.

## 5. Vòng đời xử lý key revoked event

~~~mermaid
flowchart TD
    A[Key bị thu hồi hoặc ngừng tin cậy] --> B[Nguồn phát sự kiện]
    B --> C[Chuẩn hóa và xác thực event]
    C --> D[Audit store và event stream]
    D --> E[Alerting và incident workflow]
    D --> F[Consumer cập nhật trust/policy cache]
    D --> G[Workload chuyển sang key thay thế]
    E --> H[Điều tra và đánh giá phạm vi]
    F --> I[Kiểm tra yêu cầu mới bị từ chối]
    G --> J[Theo dõi chuyển đổi]
    H --> K[Đóng incident và lưu bằng chứng]
    I --> K
    J --> K
~~~

Quy trình tổng quát gồm:

1. Một hệ thống có thẩm quyền thực hiện hoặc xác nhận quyết định thu hồi.
2. Nguồn sự kiện phát audit record hoặc domain event.
3. Bộ tiếp nhận xác thực nguồn, kiểm tra schema và chuẩn hóa metadata.
4. Event được lưu bền vững và phân phối tới consumer.
5. Monitoring đánh giá mức độ nghiêm trọng và tạo cảnh báo phù hợp.
6. Consumer cập nhật trạng thái tin cậy, từ chối thao tác mới hoặc chuyển sang key thay thế.
7. Đội vận hành kiểm tra phạm vi dữ liệu, credential và bản sao key có thể bị ảnh hưởng.
8. Kết quả xử lý và bằng chứng được liên kết với event gốc.

Không nên để một consumer không đáng tin cậy tự phát lệnh thu hồi key chỉ bằng cách gửi một message. Quyết định thu hồi phải đến từ control plane hoặc quy trình được ủy quyền; event stream dùng để phân phối và ghi nhận quyết định đó.

## 6. Thiết kế schema cho key revoked event

Một event cần có định danh duy nhất và đủ metadata để consumer xác định key, actor, phạm vi và thời điểm. Schema khái niệm:

~~~json
{
  "eventId": "evt-7f82a9",
  "eventType": "key.revoked",
  "schemaVersion": "1.0",
  "occurredAt": "2026-11-28T04:30:00Z",
  "effectiveAt": "2026-11-28T04:30:00Z",
  "source": "kms-control-plane",
  "key": {
    "keyId": "key-prod-signing-01",
    "keyVersion": "v7",
    "algorithm": "RSA-3072",
    "usage": "SIGN"
  },
  "actor": {
    "principal": "workload://security/key-admin",
    "type": "service"
  },
  "reason": {
    "code": "COMPROMISE_SUSPECTED",
    "description": "Private key exposure investigation"
  },
  "scope": {
    "environment": "production",
    "tenant": "billing"
  },
  "correlationId": "incident-2026-1042",
  "sourceEvent": {
    "action": "DisableKeyVersion",
    "requestId": "req-91a4"
  }
}
~~~

Đây là schema minh họa, không phải định dạng chuẩn của một KMS cụ thể. Các trường quan trọng:

- **eventId:** định danh duy nhất để deduplicate và truy vết.
- **eventType/schemaVersion:** loại event và phiên bản schema.
- **occurredAt/effectiveAt:** thời điểm hành động xảy ra và thời điểm quyết định có hiệu lực.
- **source/sourceEvent:** hệ thống phát event và hành động gốc.
- **keyId/keyVersion:** xác định chính xác khóa hoặc phiên bản bị ảnh hưởng.
- **actor:** principal hoặc người đã thực hiện hành động, nếu nguồn cung cấp.
- **reason:** mã lý do chuẩn hóa và mô tả ngắn.
- **scope:** môi trường, tenant hoặc miền dữ liệu liên quan.
- **correlationId:** liên kết với incident, change request hoặc workflow vận hành.

Không đưa key bytes, private key, secret, password, access token hoặc plaintext data key vào event. Event nên mang reference và metadata cần thiết, không mang vật liệu bí mật.

## 7. Lý do thu hồi và mức độ nghiêm trọng

Lý do thu hồi cần được chuẩn hóa để alert và quy trình phản ứng có thể phân loại nhất quán:

| Reason code | Ý nghĩa | Mức độ phản ứng gợi ý |
|---|---|---|
| COMPROMISE_CONFIRMED | Đã xác nhận key material hoặc môi trường bảo vệ bị lộ | Khẩn cấp; đánh giá phạm vi và thay key |
| COMPROMISE_SUSPECTED | Có dấu hiệu nghi ngờ lộ khóa | Cao; giới hạn sử dụng và điều tra ngay |
| POLICY_VIOLATION | Key vi phạm policy hoặc yêu cầu mật mã | Theo mức độ và loại dữ liệu |
| CRYPTOPERIOD_ENDED | Kết thúc thời hạn sử dụng theo chính sách | Theo kế hoạch rotation |
| SUPERSEDED | Đã thay bằng key version mới | Theo dõi chuyển đổi và dữ liệu cũ |
| CERTIFICATE_REVOKED | Certificate chứa public key bị CA thu hồi | Cập nhật trạng thái PKI và relying systems |
| OWNER_REQUEST | Chủ sở hữu hoặc quản trị viên yêu cầu ngừng sử dụng | Theo quy trình phê duyệt |

Reason code là phân loại vận hành; không phải bằng chứng rằng key đã bị lộ. Ví dụ COMPROMISE_SUSPECTED thể hiện nghi ngờ cần điều tra, còn COMPROMISE_CONFIRMED yêu cầu đánh giá phạm vi ảnh hưởng mạnh hơn.

Nên tách lý do kỹ thuật với mô tả tự do. Mô tả không nên chứa dữ liệu nhạy cảm hoặc thông tin điều tra bị giới hạn. Tham chiếu incident có thể dùng để tra cứu chi tiết trong hệ thống có phân quyền.

## 8. Audit log, event stream và alert khác nhau thế nào?

Ba thành phần phục vụ mục đích liên quan nhưng không thay thế nhau:

| Thành phần | Mục đích | Yêu cầu chính |
|---|---|---|
| Audit log | Bằng chứng về hành động đã xảy ra | Bền vững, toàn vẹn, truy cập hạn chế, có thể tra cứu |
| Event stream/message bus | Phân phối sự kiện cho consumer | Giao nhận tin cậy, retry, quản lý schema và duplicate |
| Alert/notification | Thu hút sự chú ý khi cần hành động | Đúng mức độ, có owner, có thời hạn phản hồi và tránh alert fatigue |

Một key revoked event nên được lưu trong audit log trước hoặc đồng thời với việc phân phối. Nếu event bus gặp sự cố, hệ thống vẫn phải có nguồn audit để phát lại hoặc tái dựng trạng thái. Không coi notification gửi email/chat là bằng chứng audit duy nhất.

Audit store nên có quyền ghi/đọc tách biệt, retention theo chính sách và khả năng phát hiện sửa/xóa. Với yêu cầu cao, dùng lưu trữ append-only hoặc immutable/WORM, đồng bộ thời gian và kiểm soát quyền quản trị log.

## 9. Xử lý event trùng, trễ và sai thứ tự

Event pipeline thường có thể giao nhận ít nhất một lần (at-least-once). Vì vậy, consumer có thể nhận cùng một event nhiều lần. Mạng, retry, replay hoặc nhiều nguồn audit cũng có thể làm event đến trễ hoặc sai thứ tự.

Thiết kế consumer cần:

- Dùng eventId để nhận diện và bỏ qua event đã xử lý.
- Thực hiện handler theo hướng idempotent; xử lý lặp không tạo tác động phụ mới.
- Giữ thời điểm occurredAt và effectiveAt, không chỉ dựa vào thời điểm nhận.
- Dùng keyId/keyVersion làm khóa phân vùng nếu cần giữ thứ tự event theo từng key.
- Kiểm tra schemaVersion và từ chối hoặc đưa vào quarantine event không hiểu được.
- Retry lỗi tạm thời với backoff; chuyển event lỗi kéo dài vào dead-letter queue để điều tra.
- Hỗ trợ replay từ audit store và ghi nhận trạng thái xử lý.

Không được bỏ qua một event thu hồi chỉ vì event khác đến trước hoặc sau. Consumer nên so sánh phiên bản trạng thái, sequence number hoặc nguồn sự thật có thẩm quyền để tránh một event cũ khôi phục trạng thái tin cậy đã bị thu hồi.

Nếu hai event mâu thuẫn, ví dụ một event disable và một event enable đến sai thứ tự, consumer cần dựa trên version hoặc revision của key/policy và trạng thái hiện tại từ control plane. Không suy ra trạng thái mới chỉ từ thứ tự message đến.

## 10. Phản ứng của consumer khi nhận key revoked event

Hành động phụ thuộc loại key và vai trò của consumer:

- **Dịch vụ ký:** ngừng tạo chữ ký mới bằng key version bị thu hồi; chuyển sang key version đã được phê duyệt.
- **Dịch vụ xác minh chữ ký:** cập nhật trust status; quyết định chấp nhận chữ ký cũ theo timestamp, thời điểm compromise và policy xác minh.
- **Dịch vụ giải mã:** ngừng yêu cầu decrypt bằng key bị thu hồi nếu policy yêu cầu; đánh giá phương án re-encryption hoặc key migration.
- **Certificate validator:** cập nhật CRL/OCSP hoặc trust cache và từ chối certificate đã bị thu hồi theo policy.
- **KMS client/gateway:** xóa cache metadata/quyền liên quan, làm mới policy và từ chối yêu cầu không còn được phép.
- **Monitoring/SIEM:** tạo cảnh báo, liên kết incident và theo dõi consumer đã áp dụng trạng thái mới.

Với dữ liệu đã mã hóa, không phải mọi lần thu hồi đều yêu cầu mã hóa lại ngay. Nếu key bị thu hồi do hết cryptoperiod nhưng không bị compromise, tổ chức có thể giữ khả năng giải mã dữ liệu cũ trong một giai đoạn kiểm soát. Nếu key material đã bị lộ, cần đánh giá re-encryption và nguy cơ dữ liệu đã bị giải mã trước đó.

## 11. Cache, offline verifier và giới hạn lan truyền thu hồi

Một key revoked event không tự động làm mọi hệ thống ngừng tin cậy ngay lập tức. Các ứng dụng có thể cache public key, certificate status, policy hoặc kết quả xác minh; thiết bị offline có thể không nhận event; một số session có thể tiếp tục dùng key đã nạp trước đó.

Cần xác định:

- TTL của cache key metadata, certificate status và authorization decision.
- Cơ chế push event hay polling để cập nhật trạng thái.
- Thời gian tối đa một consumer được phép hoạt động khi không liên hệ được nguồn trạng thái.
- Hành vi fail-open/fail-closed khi không kiểm tra được revocation status.
- Cách xử lý thiết bị offline hoặc hệ thống khôi phục từ backup.
- Cơ chế thu hồi session, token và key handle đang được giữ trong tiến trình.

Với thao tác có rủi ro cao, cần cân nhắc fail-closed nếu không xác minh được trạng thái thu hồi theo policy. Tuy nhiên, lựa chọn này có thể ảnh hưởng availability; phải định nghĩa theo loại dữ liệu, loại key và yêu cầu nghiệp vụ.

Đối với certificate, CRL/OCSP có thể có độ trễ cập nhật và cache. Relying party phải thực hiện kiểm tra trạng thái theo chính sách và không giả định certificate bị revoke sẽ bị mọi client từ chối ngay tức thì.

## 12. Tích hợp với Java và hệ thống monitoring

Ứng dụng Java có thể nhận event từ message broker, webhook hoặc SDK của nhà cung cấp. Nên chuẩn hóa event vào một model nội bộ trước khi đưa đến các consumer nghiệp vụ.

Ví dụ model event Java (Java 17 trở lên):

~~~java
import java.time.Instant;

public record KeyRevokedEvent(
        String eventId,
        String keyId,
        String keyVersion,
        String reasonCode,
        String actor,
        Instant occurredAt,
        Instant effectiveAt,
        String correlationId,
        String sourceEventAction) {
}
~~~

Handler khái niệm:

~~~java
public void handle(KeyRevokedEvent event) {
    if (processedEventStore.contains(event.eventId())) {
        return;
    }

    keyStatusRepository.markRevoked(
            event.keyId(),
            event.keyVersion(),
            event.reasonCode(),
            event.effectiveAt());

    alertService.publishKeyRevokedAlert(event);
    processedEventStore.markProcessed(event.eventId());
}
~~~

Đây là pseudocode; các repository và service cần được triển khai bằng cơ chế lưu trữ/event broker của hệ thống. Trong production, cập nhật trạng thái và ghi dấu event đã xử lý nên nằm trong một transaction hoặc dùng transactional inbox/outbox pattern phù hợp để tránh tình huống cập nhật thành công nhưng consumer chết trước khi đánh dấu event.

Không gọi alert trước khi có cơ chế idempotency nếu retry có thể tạo nhiều cảnh báo. Có thể dùng eventId làm idempotency key cho cả cập nhật trạng thái và thông báo. Cần kiểm soát quyền của consumer để nó chỉ cập nhật key inventory/trust cache được phân công, không có quyền tùy tiện thay đổi key policy hoặc xóa key.

## 13. Alert và chỉ số cần theo dõi

Không phải mọi key revoked event đều có cùng mức độ nghiêm trọng. Alert cần xét reason code, loại key, môi trường, dữ liệu phụ thuộc, actor và phạm vi:

- Key production bị thu hồi do compromise confirmed: cảnh báo khẩn cấp tới đội security và owner dịch vụ.
- Key signing hoặc CA certificate bị thu hồi: theo dõi các dịch vụ phát hành/xác minh chữ ký và trạng thái certificate.
- Key hết cryptoperiod được thu hồi theo lịch: cảnh báo vận hành theo kế hoạch, không nhất thiết là incident.
- Key staging bị thu hồi: cảnh báo ở phạm vi môi trường tương ứng.
- Event do actor không mong đợi hoặc ngoài change window: tăng mức độ ưu tiên và kiểm tra authorization.

Các chỉ số hữu ích:

| Metric | Ý nghĩa |
|---|---|
| Revocation events by reason | Số event theo từng lý do |
| Event delivery latency | Độ trễ từ lúc phát đến lúc consumer nhận |
| Revocation propagation time | Thời gian từ quyết định đến khi consumer áp dụng |
| Consumer processing failures | Số event xử lý lỗi hoặc vào dead-letter queue |
| Revoked-key operation attempts | Số yêu cầu dùng key đã bị thu hồi |
| Active consumers behind | Số consumer chưa xác nhận trạng thái mới |
| Unauthorized revocation attempts | Số yêu cầu thu hồi không được phép |

Đặt ngưỡng cảnh báo dựa trên baseline và yêu cầu dịch vụ. Một event thu hồi key production do compromise có thể cần cảnh báo ngay cả khi chỉ có một event; một đợt thu hồi định kỳ có thể được tổng hợp theo change window.

## 14. Ứng phó sự cố khi nhận event thu hồi

Khi event cho biết key bị thu hồi do compromise hoặc nghi ngờ compromise:

1. Xác minh event đến từ nguồn có thẩm quyền và đối chiếu request ID/audit record gốc.
2. Xác định key ID, key version, thuật toán, mục đích sử dụng, principal và các hệ thống phụ thuộc.
3. Ngăn thao tác mới bằng key bị ảnh hưởng theo policy; kiểm tra cache, session, token và thiết bị offline.
4. Tạo hoặc kích hoạt key thay thế theo quy trình được phê duyệt; xác minh quyền truy cập của workload.
5. Đánh giá ciphertext, data key, backup, bản sao key và plaintext có thể đã bị truy cập.
6. Nếu key dùng để mã hóa và có nguy cơ lộ, lập kế hoạch re-encryption hoặc thay wrapping key theo mức độ ảnh hưởng.
7. Nếu key dùng để ký, đánh giá chữ ký được tạo trong khoảng thời gian nghi vấn và policy xác minh chữ ký lịch sử.
8. Rà soát audit log để tìm thao tác bất thường trước và sau thời điểm thu hồi.
9. Ghi nhận thời gian từng consumer nhận và áp dụng event; xử lý consumer chưa cập nhật.
10. Đóng incident khi phạm vi ảnh hưởng, hành động khắc phục và bằng chứng đã được xác nhận.

Việc thu hồi một key ký số không tự động chứng minh mọi chữ ký trước đó đều không hợp lệ. Cần xem thời điểm ký đáng tin cậy, thời điểm compromise ước tính, timestamp, certificate status và chính sách chấp nhận chữ ký lịch sử.

Với key mã hóa, thu hồi quyền sử dụng không thể làm biến mất plaintext đã được giải mã trước đó. Nếu attacker đã lấy plaintext hoặc data key, cần xử lý như sự cố lộ dữ liệu/khóa theo quy trình riêng.

## 15. Rủi ro và lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Event không có key ID/version | Consumer không xác định được tài nguyên cần cập nhật | Đưa định danh key và version vào schema |
| Ghi event nhưng không lưu audit bền vững | Mất bằng chứng hoặc không thể replay | Lưu audit append-only và kiểm tra giao nhận |
| Nhầm disable với destroy | Có thể đánh giá sai khả năng khôi phục hoặc dữ liệu còn truy cập được | Chuẩn hóa state/action và giữ source action |
| Event chứa private key hoặc plaintext data key | Log/event bus trở thành nơi rò rỉ key material | Chỉ truyền reference và metadata không bí mật |
| Consumer xử lý event nhiều lần | Gửi alert lặp hoặc thực hiện side effect nhiều lần | Dùng eventId và handler idempotent |
| Event đến sai thứ tự | Trạng thái cũ có thể ghi đè trạng thái thu hồi mới | Dùng version/sequence và nguồn trạng thái có thẩm quyền |
| Consumer không nhận event | Workload tiếp tục tin cậy key bị thu hồi | Theo dõi delivery, propagation và consumer lag |
| Chỉ dựa vào event bus, không có audit source | Không thể đối chiếu hoặc phục hồi event bị mất | Giữ audit log gốc và hỗ trợ replay |
| Coi revoke là xóa mọi bản sao key | Bỏ sót key đã export, cache hoặc plaintext đã cấp | Đánh giá riêng key material và data key đã phát hành |
| Không kiểm tra trạng thái chữ ký lịch sử | Chấp nhận chữ ký tạo trong thời gian key đã bị compromise | Áp dụng timestamp và chính sách xác minh lịch sử |

## 16. Checklist triển khai

- [ ] Định nghĩa rõ ý nghĩa nghiệp vụ của revoke, disable, expire và destroy.
- [ ] Xác định các nguồn phát event và ánh xạ source action sang event type chuẩn.
- [ ] Ghi eventId, schemaVersion, keyId/keyVersion, actor, reason, occurredAt và effectiveAt.
- [ ] Liên kết event với request ID, change request hoặc incident ID.
- [ ] Không đưa key material, credential hoặc plaintext data key vào event/log.
- [ ] Lưu audit event bền vững, hạn chế quyền sửa/xóa và đồng bộ thời gian.
- [ ] Phân phối event có retry, dead-letter queue, replay và kiểm soát schema.
- [ ] Thiết kế consumer idempotent, xử lý duplicate, delay và out-of-order.
- [ ] Theo dõi event delivery latency và thời gian propagation tới consumer.
- [ ] Cập nhật trust cache, certificate status và authorization policy theo đúng loại key.
- [ ] Kiểm thử cả consumer online, offline, cache cũ và event bị phát lại.
- [ ] Có quy trình incident response, key replacement và re-encryption khi cần.
- [ ] Lưu bằng chứng xác nhận principal/workload đã ngừng dùng key bị thu hồi.

Key revoked event là tín hiệu quan trọng để biến quyết định thu hồi thành hành động nhất quán trên toàn hệ thống. Thiết kế tốt cần phân biệt rõ trạng thái key, ghi event có định danh và lý do, bảo vệ audit, xử lý message an toàn và xác minh các consumer đã ngừng tin cậy key đúng thời điểm.
