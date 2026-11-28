# Test failure khi KMS unavailable

**Test failure khi KMS unavailable** là hoạt động kiểm thử hành vi của ứng dụng và quy trình vận hành khi Key Management Service không thể phục vụ một hoặc nhiều yêu cầu mật mã. Tình huống này có thể xuất hiện do KMS ngừng hoạt động, mất kết nối mạng, lỗi DNS/TLS, throttling, hết quota, sai quyền, lỗi vùng triển khai hoặc sự cố ở HSM/backend phía sau KMS.

KMS thường nằm trên đường đi của các thao tác tạo data key, unwrap key, giải mã dữ liệu, ký hoặc xác minh. Khi KMS không sẵn sàng, ứng dụng có thể không đọc được dữ liệu cũ, không tạo được dữ liệu mới hoặc không hoàn thành giao dịch. Một thiết kế an toàn cần xác định operation nào được phép tiếp tục bằng tài nguyên đã có, operation nào phải dừng, cách retry có giới hạn, cách chuyển vùng khi được hỗ trợ và cách khôi phục sau outage.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Kiểm thử key management**. Nội dung kết nối kiểm thử KMS outage với vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, backup, restore, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, chữ ký số, envelope encryption, KMS/HSM, kiểm soát truy cập và kiểm toán.

## 1. Vì sao phải kiểm thử KMS unavailable?

KMS là dependency bảo mật và availability. Nếu ứng dụng không xử lý outage đúng cách, hệ thống có thể:

- Mất khả năng giải mã dữ liệu dù ciphertext vẫn còn nguyên.
- Không tạo được DEK mới để mã hóa dữ liệu.
- Không unwrap được DEK đã lưu trong backup hoặc object storage.
- Không ký được giao dịch hoặc artifact bằng private key trong HSM.
- Retry vô hạn, làm tăng tải và kéo dài outage.
- Tự chuyển sang software key hoặc thuật toán yếu để tiếp tục chạy.
- Trả lỗi không rõ ràng, khiến người vận hành không phân biệt outage với lỗi quyền.
- Làm mất dữ liệu do ghi trạng thái nghiệp vụ trước khi operation mật mã hoàn tất.
- Không thể khôi phục vì key version hoặc recovery path đã bị xóa.

Kiểm thử giúp xác định ranh giới giữa tính sẵn sàng và tính bảo mật. Ứng dụng cần tiếp tục các chức năng không phụ thuộc KMS nếu có thể, đồng thời dừng an toàn những operation không thể thực hiện đúng policy.

## 2. KMS unavailable có nhiều dạng

Không nên xem mọi lỗi KMS là cùng một loại outage. Các nhóm thường gặp:

| Nhóm lỗi | Ví dụ | Hành vi cần kiểm tra |
|---|---|---|
| Service outage | Endpoint KMS trả 5xx hoặc không phục vụ | Timeout, retry có giới hạn, alert và recovery |
| Network failure | Mất route, firewall chặn, packet loss | Deadline, connection timeout, circuit breaker |
| DNS/TLS failure | Không resolve endpoint, certificate hoặc handshake lỗi | Phân biệt lỗi kết nối và lỗi xác thực |
| Throttling/quota | Request vượt rate limit hoặc quota | Backoff, jitter, admission control |
| Authentication failure | Token hết hạn, workload identity lỗi | Làm mới identity theo policy; không retry mù |
| Authorization denied | Principal không có quyền hoặc key policy từ chối | Fail closed, cảnh báo cấu hình/quyền |
| Resource/key error | Key ID sai, version không tồn tại, key disabled | Báo lỗi chính xác; không coi là outage |
| Backend/HSM issue | HSM session hết hạn, partition unavailable | Tái lập session hoặc fail theo policy |
| Regional failure | Region hoặc endpoint KMS không truy cập được | Failover chỉ theo kiến trúc đã kiểm thử |
| Partial degradation | Một operation hoặc một key bị lỗi, phần còn lại hoạt động | Xác định phạm vi và tránh mở rộng outage |

Một lỗi AccessDenied không phải bằng chứng KMS đang unavailable. InvalidCiphertext cũng không phải lỗi cần retry. Phân loại đúng exception giúp tránh che giấu lỗi policy hoặc dữ liệu bằng retry vô ích.

## 3. Phân biệt control plane và data plane

Một số KMS tách API quản trị khỏi API thực hiện operation mật mã. Control plane có thể quản lý key, policy, alias hoặc rotation; data plane xử lý encrypt, decrypt, sign, wrap và unwrap. Tùy sản phẩm, hai mặt phẳng có thể có availability và endpoint riêng.

Ví dụ, việc tạo key mới có thể thất bại trong khi một số operation dùng key đã tồn tại vẫn hoạt động; hoặc data plane có thể bị gián đoạn trong khi API quản trị vẫn đọc được metadata. Không được giả định hành vi này giống nhau giữa các nhà cung cấp.

Khi thiết kế test, ghi rõ operation và endpoint nào đang được làm lỗi. Kiểm thử riêng create/rotate/policy change và encrypt/decrypt/sign/unwrap để biết outage ảnh hưởng đến luồng nào.

## 4. Xác định operation phụ thuộc KMS

Lập dependency map cho từng luồng nghiệp vụ:

| Operation | Dependency KMS thường gặp | Tác động nếu unavailable |
|---|---|---|
| GenerateDataKey | Tạo DEK và wrapped DEK | Không thể mã hóa object mới nếu không có DEK hợp lệ |
| Encrypt | Mã hóa trực tiếp bằng KMS key | Không thể hoàn thành encryption request |
| Decrypt | Giải mã ciphertext hoặc wrapped DEK | Không đọc được dữ liệu cần KMS |
| Wrap/unwrap | Bảo vệ hoặc mở bọc key material | Không thể chuyển/khôi phục DEK |
| Sign | HSM/KMS thực hiện chữ ký | Không thể tạo chữ ký mới |
| Verify | Có thể dùng public key local hoặc dịch vụ xác minh | Có thể tiếp tục nếu public key và policy cho phép |
| Rotate | Tạo version hoặc cập nhật key material | Rotation bị chậm; cần theo dõi trạng thái |
| Backup/restore | Backup package, KEK và recovery API | Có thể không tạo hoặc không khôi phục được bản sao |

Không phải mọi verify đều cần KMS. Nếu public key/certificate đã được phân phối và tin cậy, ứng dụng có thể xác minh chữ ký cục bộ. Tương tự, encryption/decryption bằng DEK đã có trong bộ nhớ có thể tiếp tục trong phạm vi policy; điều đó không có nghĩa có thể bỏ qua KMS vô thời hạn.

## 5. Xác định security invariant khi KMS lỗi

Trước khi viết test, định nghĩa điều gì tuyệt đối phải đúng:

- Không export hoặc ghi private/secret key ra file plaintext để né outage.
- Không chuyển từ HSM sang software provider ngoài policy.
- Không hạ thuật toán, key size, padding hoặc xác thực dữ liệu.
- Không bỏ qua authorization, tenant scope hoặc encryption context.
- Không trả plaintext nếu chưa xác thực thành công ciphertext/tag.
- Không ghi password, token, DEK hoặc plaintext vào log.
- Không đánh dấu giao dịch thành công trước khi operation bắt buộc hoàn tất.
- Không xóa key version còn cần cho dữ liệu hoặc backup hợp lệ.
- Mọi fallback, cache hoặc failover phải được định nghĩa và kiểm thử trước.

Các invariant này giúp đánh giá test không chỉ theo tiêu chí “service còn trả response”, mà còn theo việc hệ thống có giữ đúng ranh giới bảo vệ khóa hay không.

## 6. Fail closed và graceful degradation

**Fail closed** nghĩa là từ chối operation nhạy cảm khi không thể xác minh hoặc thực hiện nó theo policy. Ví dụ, nếu cần unwrap DEK để đọc dữ liệu mà KMS không sẵn sàng và không có DEK cache hợp lệ, ứng dụng phải trả lỗi thay vì trả dữ liệu chưa được xác thực.

**Graceful degradation** nghĩa là chỉ tạm ngừng phần phụ thuộc KMS, còn chức năng độc lập vẫn có thể hoạt động. Ví dụ:

- Trang tra cứu dữ liệu công khai vẫn phục vụ.
- Người dùng có thể xem metadata không mã hóa.
- Queue nhận yêu cầu có thể lưu công việc để xử lý sau nếu nghiệp vụ cho phép.
- Verify chữ ký bằng public key đã tin cậy vẫn có thể tiếp tục.
- Dữ liệu đã được giải mã hợp lệ trong session có thể dùng trong giới hạn thời gian và policy.

Không được hiểu graceful degradation là bỏ kiểm soát mật mã. Nếu một operation bắt buộc cần private key trong HSM, ứng dụng phải báo chưa thể ký khi HSM unavailable.

## 7. Fail open có thể tạo lỗ hổng

Một anti-pattern là khi KMS lỗi, ứng dụng tự chuyển sang khóa cục bộ:

~~~text
try:
    decrypt_with_kms(ciphertext)
catch KmsUnavailable:
    decrypt_with_local_key(ciphertext)
~~~

Nếu local key không thuộc kiến trúc đã phê duyệt, fallback này có thể làm lộ key material, tạo hai nguồn khóa không đồng bộ hoặc phá vỡ audit. Tương tự, không được bỏ qua GCM tag validation, dùng ECB, tắt hostname verification hoặc chấp nhận chữ ký không xác minh được chỉ để giữ availability.

Fallback chỉ hợp lệ khi có backend dự phòng được thiết kế trước, với key identity, policy, protection level, audit và recovery tương đương. Cơ chế chuyển backend phải được kiểm thử cả chiều chuyển đi lẫn quay về.

## 8. Retry có giới hạn và exponential backoff

Retry hữu ích với lỗi tạm thời như timeout, throttling hoặc 5xx có thể phục hồi. Không retry vô hạn. Một chính sách thường gồm:

- Giới hạn số lần thử.
- Exponential backoff để tăng khoảng chờ sau mỗi lần lỗi.
- Jitter để nhiều instance không retry cùng thời điểm.
- Deadline tổng cho operation, bao gồm thời gian queue và network.
- Phân loại lỗi có thể retry và không thể retry.
- Tôn trọng retry-after nếu dịch vụ trả về và SDK hỗ trợ.
- Ghi attempt count và kết quả mà không ghi dữ liệu bí mật.

Không retry các lỗi như AccessDenied, InvalidCiphertext, invalid parameter hoặc key không tồn tại, trừ khi tài liệu dịch vụ xác định rõ một trường hợp eventual consistency có thể phục hồi.

## 9. Idempotency và retry an toàn

Retry một operation có side effect có thể tạo kết quả trùng lặp. Ví dụ, yêu cầu tạo key hoặc GenerateDataKey có thể tạo nhiều key/data key nếu request trước đã hoàn tất nhưng response bị mất.

Khi API hỗ trợ idempotency token/request token, dùng token ổn định cho cùng một logical request. Nếu API không hỗ trợ, thiết kế workflow để có thể tra cứu kết quả trước khi tạo lại, hoặc chấp nhận và quản lý các artifact trùng lặp theo cách an toàn.

Decrypt thường là operation đọc, nhưng vẫn có thể tạo chi phí và audit event lặp. Sign có thể tạo nhiều chữ ký hoặc audit event. Không giả định mọi operation mật mã đều có thể retry vô điều kiện.

## 10. Timeout, deadline và circuit breaker

Timeout ngăn một request chờ KMS vô hạn. Nên cấu hình riêng:

- Connection timeout.
- TLS/handshake timeout.
- Read/response timeout.
- Deadline tổng của nghiệp vụ.
- Timeout khi lấy token/identity nếu dependency này cũng có thể lỗi.

Circuit breaker có thể ngừng gửi request mới tới KMS sau khi tỷ lệ lỗi vượt ngưỡng, cho phép backend phục hồi và tránh khuếch đại outage. Sau thời gian chờ, half-open probe kiểm tra có thể phục hồi hay chưa.

Circuit breaker không thay thế timeout hoặc retry. Nếu breaker mở, ứng dụng cần trả lỗi có thể phân loại hoặc đưa công việc vào queue có giới hạn. Không giữ request/thread vô hạn trong khi breaker đang mở.

## 11. Bulkhead và kiểm soát tải

Một outage KMS có thể chiếm hết thread pool nếu mọi request đều chờ timeout. Bulkhead tách tài nguyên cho các nhóm operation:

- Pool riêng cho KMS-dependent operation.
- Giới hạn concurrent request và queue length.
- Admission control khi quá tải.
- Hạn chế retry đồng thời trên mọi instance.
- Ưu tiên operation khôi phục hoặc nghiệp vụ quan trọng theo policy.

Không để queue tăng vô hạn. Queue phải có giới hạn, thời gian sống và chính sách từ chối khi quá tải. Công việc bị từ chối cần được trả trạng thái rõ ràng để caller có thể thử lại sau.

## 12. Envelope encryption khi KMS unavailable

Trong envelope encryption, KMS thường tạo DEK và trả về plaintext DEK tạm thời cùng wrapped DEK. Ứng dụng dùng plaintext DEK để mã hóa dữ liệu, lưu ciphertext và wrapped DEK.

Khi KMS unavailable:

- Không tạo được DEK mới nếu không có nguồn DEK hợp lệ khác đã được phê duyệt.
- Không unwrap được DEK đã lưu để đọc dữ liệu nếu plaintext DEK không có trong cache hợp lệ.
- Có thể tiếp tục xử lý bằng DEK đã cache trong phạm vi TTL, scope và policy cho phép.
- Không được ghi plaintext DEK ra disk hoặc log để kéo dài khả năng hoạt động.
- Khi cache hết hạn hoặc process restart, operation lại phụ thuộc KMS.

~~~mermaid
flowchart TD
    A["Workload cần mã hóa"] --> B["Yêu cầu KMS GenerateDataKey"]
    B --> C{"KMS sẵn sàng?"}
    C -- "Có" --> D["Plaintext DEK + wrapped DEK"]
    D --> E["Mã hóa dữ liệu"]
    E --> F["Lưu ciphertext + wrapped DEK"]
    C -- "Không" --> G["Kiểm tra DEK cache được phép"]
    G --> H{"Cache hợp lệ?"}
    H -- "Có" --> E
    H -- "Không" --> I["Từ chối / queue theo policy"]
~~~

DEK cache cần giới hạn theo thời gian, số lần sử dụng, tenant và data scope. Cache phải được bảo vệ trong memory, không chia sẻ nhầm giữa tenant và được xóa theo best effort khi hết hạn hoặc khi ứng dụng đóng. Cache không thay thế key lifecycle hoặc revocation policy.

## 13. Cân nhắc cache DEK

Cache plaintext DEK giúp giảm latency và cho phép một số operation tiếp tục khi KMS tạm thời không sẵn sàng. Đổi lại, plaintext key tồn tại lâu hơn trong memory và có thể tiếp tục được dùng sau khi quyền ở KMS đã bị revoke.

Trước khi cho phép cache, cần xác định:

- TTL tối đa và idle timeout.
- Giới hạn số object hoặc số operation trên mỗi DEK.
- Scope theo tenant, application và purpose.
- Cách xử lý khi key bị revoke hoặc compromise.
- Có được dùng cache trong outage hay chỉ khi KMS healthy.
- Cách bảo vệ memory, heap dump, crash dump và swap.
- Cách xóa cache và audit việc sử dụng cache.

Nếu policy yêu cầu mọi operation phải được KMS authorize trực tiếp, không được dùng cache để vượt policy đó. Nếu cache được phép, outage test phải xác minh đúng TTL và behavior sau khi cache hết hạn.

## 14. Decrypt dữ liệu cũ khi KMS unavailable

Đối với dữ liệu đã mã hóa, ứng dụng thường cần unwrap DEK bằng KEK trong KMS. Nếu KMS unavailable và không có plaintext DEK cache hợp lệ, ứng dụng không thể giải mã.

Test cần xác minh:

- Ciphertext vẫn nguyên vẹn và không bị ghi đè bằng dữ liệu rỗng.
- Wrapped DEK và key ID/version được giữ lại để thử lại sau.
- Không trả một phần plaintext trước khi xác thực AEAD hoàn tất.
- API trả lỗi tạm thời hoặc trạng thái pending phù hợp.
- Sau khi KMS phục hồi, cùng object có thể giải mã thành công.
- Không có fallback sang key khác không đúng version hoặc tenant.

Với AES-GCM, không trả plaintext cho caller trước khi tag xác thực thành công. Nếu giải mã streaming, phải thiết kế buffer/commit sao cho dữ liệu chưa được xác thực không bị tiêu thụ như kết quả hợp lệ.

## 15. Sign và verify khi HSM/KMS unavailable

Nếu private signing key nằm trong HSM/KMS, sign thường cần backend thực hiện operation. Khi backend unavailable, giao dịch hoặc artifact cần chữ ký phải dừng hoặc chuyển sang queue theo nghiệp vụ. Không dùng private key local dự phòng trừ khi kiến trúc đã phê duyệt.

Verify có thể tiếp tục cục bộ nếu public key/certificate đã có sẵn và còn hợp lệ. Tuy nhiên, kiểm tra certificate status hoặc revocation có thể phụ thuộc OCSP/CRL service riêng; test phải phân biệt lỗi KMS với lỗi PKI/status service.

Không chấp nhận chữ ký chỉ vì KMS không sẵn sàng. Không hạ thuật toán hoặc bỏ qua xác minh certificate chain để hoàn tất giao dịch.

## 16. Multi-region và failover

Một số nền tảng hỗ trợ multi-region key, replica hoặc regional endpoint. Failover chỉ an toàn khi đã xác minh:

- Key ở region dự phòng thực sự tương thích với ciphertext và key version cần dùng.
- Replication đã hoàn tất và policy đồng bộ.
- Principal/role ở region dự phòng có đúng quyền.
- Encryption context, tenant và key purpose không thay đổi.
- Audit event được ghi ở cả hai region và có thể tương quan.
- Quota, latency và network path đã được kiểm thử.
- Quy trình failback không ghi đè hoặc làm mất dữ liệu.

Không giả định hai key cùng alias ở hai region là cùng key material. Cũng không giả định mọi KMS hỗ trợ chuyển ciphertext giữa region. Phải dùng mô hình multi-region/key replication được tài liệu nhà cung cấp hỗ trợ.

## 17. Backup và recovery khi KMS outage

KMS outage có thể làm backup job hoặc restore job thất bại:

- Backup cần KMS để tạo/wrap DEK.
- Restore cần KMS để unwrap DEK hoặc phục hồi key package.
- HSM backup có thể cần quorum/operator và thiết bị tương thích.
- Key version cũ có thể cần giữ suốt thời hạn retention.

Không xóa ciphertext hoặc wrapped DEK khi KMS tạm thời không truy cập được. Không schedule destruction key chỉ để giải phóng tài nguyên trong lúc incident. Recovery plan phải ghi key ID/version, backend, region, owner, approver và phương án khôi phục KMS.

Diễn tập restore cần kiểm tra cả trường hợp KMS healthy, KMS primary unavailable và recovery backend được kích hoạt theo quy trình.

## 18. Java: xử lý lỗi KMS ở lớp ứng dụng

Trong Java, KMS SDK hoặc provider thường bọc lỗi dịch vụ thành exception riêng; JCA engine có thể phát sinh GeneralSecurityException, InvalidKeyException hoặc ProviderException tùy backend. Không phân loại outage chỉ bằng exception message.

Nên ánh xạ lỗi tại adapter KMS thành nhóm rõ ràng:

| Nhóm ứng dụng | Ví dụ | Hướng xử lý |
|---|---|---|
| Transient unavailable | Timeout, connection reset, service 5xx | Retry bounded, breaker và alert |
| Throttled | Rate limit hoặc quota tạm thời | Backoff, giảm tải và queue giới hạn |
| Access denied | IAM/key policy từ chối | Fail closed, sửa quyền qua change process |
| Invalid request | Key ID, context hoặc parameter sai | Không retry mù; sửa request |
| Key state | Disabled, pending deletion hoặc not found | Dừng operation và kiểm tra lifecycle |
| Integrity/authentication | Invalid tag hoặc invalid ciphertext | Không retry sang key khác; xử lý như dữ liệu không hợp lệ |

Adapter không nên trả một exception chung cho mọi lỗi. Caller cần biết operation có thể retry hay không, nhưng không cần nhận secret value hoặc chi tiết credential.

## 19. Ví dụ Java: retry có giới hạn

Đoạn mã sau minh họa adapter với các exception đã được phân loại. Các interface/exception là kiểu ứng dụng giả định; khi triển khai, ánh xạ chúng từ SDK KMS thực tế:

~~~java
import java.util.concurrent.ThreadLocalRandom;

interface KmsClient {
    byte[] decrypt(byte[] wrappedDek) throws KmsException;
}

class KmsException extends Exception {
    KmsException(String message) { super(message); }
}

class KmsUnavailableException extends KmsException {
    KmsUnavailableException(String message) { super(message); }
}

class KmsThrottledException extends KmsException {
    KmsThrottledException(String message) { super(message); }
}

class KmsAccessDeniedException extends KmsException {
    KmsAccessDeniedException(String message) { super(message); }
}

byte[] decryptWithRetry(KmsClient kms, byte[] wrappedDek)
        throws KmsException, InterruptedException {
    final int maxAttempts = 3;
    KmsException lastFailure = null;

    for (int attempt = 0; attempt < maxAttempts; attempt++) {
        try {
            return kms.decrypt(wrappedDek);
        } catch (KmsUnavailableException | KmsThrottledException ex) {
            lastFailure = ex;
            if (attempt == maxAttempts - 1) {
                break;
            }

            long ceilingMillis = 100L * (1L << attempt);
            long delayMillis = ThreadLocalRandom.current()
                    .nextLong(ceilingMillis / 2, ceilingMillis + 1);
            Thread.sleep(delayMillis);
        }
    }

    throw lastFailure;
}
~~~

Ví dụ chỉ retry lỗi tạm thời và có số lần thử hữu hạn. Trong ứng dụng thực tế, cần thêm deadline tổng, timeout cho từng request, metric và cancellation. AccessDenied, invalid ciphertext, invalid parameter và key state error không được đưa vào nhóm retryable. Caller phải xử lý failure cuối cùng theo policy, không chuyển sang local key.

## 20. Không dùng JCA provider fallback để né outage

Nếu ứng dụng yêu cầu HSM provider để ký, lỗi HSM không nên khiến code tự chọn provider phần mềm:

~~~java
Provider hsmProvider = Security.getProvider("ApprovedHsmProvider");
if (hsmProvider == null) {
    throw new GeneralSecurityException("Required HSM provider unavailable");
}

Signature signer =
        Signature.getInstance("SHA256withRSA", hsmProvider);
signer.initSign(hsmPrivateKey);
signer.update(payload);
byte[] signature = signer.sign();
~~~

Tên provider và thuật toán là ví dụ. Nếu provider không sẵn sàng hoặc operation thất bại, ứng dụng phải trả lỗi có phân loại. Provider dự phòng chỉ được dùng nếu đã được phê duyệt và có key, policy, audit, protection level cùng quy trình chuyển đổi rõ ràng.

## 21. Health check và readiness

Không nên gọi KMS liên tục từ liveness probe của mọi instance. Điều đó có thể tạo tải lớn, gây throttling và làm outage nặng hơn.

Phân biệt:

- **Liveness:** process còn sống và event loop/thread pool hoạt động.
- **Readiness:** instance có thể nhận loại traffic hiện tại theo dependency và policy.
- **Dependency health:** trạng thái KMS endpoint, latency và error rate từ probe có giới hạn.

Một instance có thể còn sống nhưng không ready cho endpoint cần decrypt. Nếu ứng dụng có cả endpoint không phụ thuộc KMS và endpoint phụ thuộc KMS, có thể dùng readiness theo capability hoặc trả trạng thái unavailable riêng cho nhóm operation đó.

Probe nên có timeout, tần suất thấp, jitter và cache trạng thái ngắn. Không dùng một health probe thành công để bảo đảm operation tiếp theo chắc chắn thành công.

## 22. Observability trong outage

Trong thời gian KMS unavailable, cần ghi và đo:

- Số request theo operation và outcome.
- Timeout, 5xx, throttling, AccessDenied và invalid request riêng biệt.
- Retry attempt, retry exhaustion và circuit breaker state.
- KMS latency p50/p95/p99.
- Queue depth, rejected request và bulkhead saturation.
- DEK cache hit/miss, TTL và số operation dùng cache.
- Key ID/version ở dạng metadata, không có key material.
- Region/backend đang được dùng.
- Thời điểm bắt đầu, phục hồi và thời gian ổn định sau phục hồi.

Log không được chứa plaintext DEK, KEK, password, token, plaintext dữ liệu hoặc ciphertext nhạy cảm không cần thiết. Dùng request ID để nối event ứng dụng với audit KMS.

## 23. Fault injection và môi trường kiểm thử

Có thể mô phỏng KMS outage bằng nhiều cách:

- Mock/fake KMS trả timeout, 5xx, throttling hoặc AccessDenied.
- Test double cho KMS client để kiểm soát thứ tự lỗi và phục hồi.
- Proxy test có thể reset connection, delay hoặc drop packet.
- DNS test environment trả lỗi resolve hoặc endpoint không hợp lệ.
- HSM simulator hoặc test partition để kiểm tra session/backend behavior.
- Chaos test trên staging với giới hạn blast radius.
- Regional endpoint test theo quy trình failover đã phê duyệt.

Không vô hiệu hóa KMS production hoặc chặn mạng production để thử nghiệm nếu chưa có change/chaos plan được phê duyệt. HSM simulator không chứng minh đầy đủ behavior của thiết bị thật; vẫn cần test tương thích trên môi trường phần cứng phù hợp.

## 24. Ma trận test failure

Một ma trận cơ bản:

| Tình huống | Kết quả mong đợi | Bằng chứng cần thu |
|---|---|---|
| KMS trả 5xx | Retry bounded rồi báo unavailable | Attempt count, latency, outcome |
| Network timeout | Deadline được tôn trọng | Timeout metric, request ID |
| DNS/TLS failure | Không bypass TLS hoặc endpoint validation | Error class, endpoint metadata |
| Throttling | Backoff/jitter và admission control | Retry-after, queue depth |
| AccessDenied | Fail closed, không retry mù | Principal, key ID, policy decision |
| Key disabled/not found | Báo key state error | Key ID/version, lifecycle event |
| InvalidCiphertext/tag | Không trả plaintext, không đổi key fallback | Integrity failure, request ID |
| KMS outage khi GenerateDataKey | Không tạo dữ liệu mới bằng key không được duyệt | Job state, idempotency token |
| KMS outage khi unwrap DEK | Chỉ dùng cache nếu policy cho phép; nếu không thì fail | Cache state, key version |
| HSM session hết hạn | Tái xác thực theo policy hoặc fail | Session event, backend result |
| Primary region unavailable | Failover theo cấu hình đã kiểm thử | Region, key identity, audit |
| Recovery | Operation hoạt động lại và dữ liệu cũ đọc được | End-to-end test, audit trail |

Mỗi test cần kiểm tra cả response API, dữ liệu lưu trữ, audit event và trạng thái nghiệp vụ. Không chỉ xác nhận HTTP 503 hoặc exception đã được ném ra.

## 25. Kiểm thử recovery và phục hồi sau outage

Khi KMS phục hồi, ứng dụng cần trở lại hoạt động mà không tạo thêm lỗi:

1. Xác nhận endpoint và identity đã hoạt động.
2. Kiểm tra circuit breaker chuyển sang half-open rồi closed theo policy.
3. Chạy probe hoặc operation thử với key test được phép.
4. Xử lý queue theo tốc độ giới hạn, tránh dồn tải.
5. Xác minh request cũ có idempotency và không tạo duplicate.
6. Giải mã dữ liệu được tạo trước outage.
7. Hoàn tất operation đã pending hoặc báo trạng thái thất bại rõ ràng.
8. Kiểm tra audit event không bị mất hoặc đảo thứ tự nghiêm trọng.
9. Xác minh DEK cache hết hạn và được làm sạch theo policy.
10. Theo dõi error rate sau khi breaker đóng lại.

Không mở toàn bộ traffic cùng lúc nếu KMS vừa phục hồi nhưng quota hoặc HSM capacity còn hạn chế. Dùng gradual ramp-up và theo dõi latency.

## 26. Kiểm thử rotation trong thời gian outage

Nếu rotation job bắt đầu đúng lúc KMS unavailable, cần xác định:

- Key version mới đã được tạo hay chưa.
- Version nào đang active.
- Consumer đã nhận version mới chưa.
- Job có thể resume an toàn hay phải rollback.
- Có tạo key trùng do retry hay không.
- Key version cũ có còn khả năng decrypt dữ liệu lịch sử không.
- Rotation schedule có được cập nhật sai thành công hay không.

Không đánh dấu rotation thành công chỉ vì job đã bắt đầu. Chỉ cập nhật trạng thái hoàn tất sau khi xác minh version mới hoạt động và consumer đã chuyển theo kế hoạch.

## 27. Runbook vận hành khi KMS unavailable

Một runbook nên có:

1. Xác định KMS service, region, endpoint và operation bị ảnh hưởng.
2. Phân biệt outage với throttling, authentication, authorization và key state error.
3. Kiểm tra status từ nguồn provider và telemetry nội bộ.
4. Kích hoạt incident owner và thông báo theo quy trình nội bộ.
5. Bật circuit breaker hoặc giảm traffic nếu cần.
6. Giữ nguyên fail-closed cho operation nhạy cảm.
7. Chỉ dùng cache/failover đã được policy cho phép.
8. Không export key hoặc chuyển sang software provider tùy tiện.
9. Theo dõi queue, retry, quota và HSM session.
10. Sau phục hồi, chạy recovery verification và xử lý pending job.
11. Kiểm tra audit, key version, backup và rotation state.
12. Ghi timeline, tác động và hành động cải thiện sau incident.

Runbook phải chỉ rõ người có quyền kích hoạt failover, key nào được dùng, vùng đích nào hợp lệ và cách quay lại primary.

## 28. Các lỗi kiểm thử thường gặp

- Chỉ test KMS trả 5xx mà không test DNS, TLS, throttling và AccessDenied.
- Retry vô hạn hoặc retry mọi exception.
- Không đặt deadline tổng cho request.
- Không kiểm tra duplicate khi response bị mất sau khi operation đã hoàn tất.
- Cho phép fallback sang software key hoặc provider mặc định.
- Cache plaintext DEK không có TTL hoặc scope.
- Không kiểm tra dữ liệu sau outage có thể giải mã lại.
- Không kiểm thử KMS/HSM regional failover.
- Health check gọi KMS quá thường xuyên.
- Không test queue saturation và recovery traffic spike.
- Không kiểm tra audit event và key version sau rotation bị gián đoạn.
- Chỉ kiểm tra exception mà không kiểm tra side effect và dữ liệu lưu.

## 29. Checklist thiết kế test

Trước khi phát hành hệ thống phụ thuộc KMS, hãy xác nhận:

- [ ] Đã lập dependency map cho GenerateDataKey, encrypt, decrypt, sign, unwrap, backup và restore.
- [ ] Đã phân loại outage, network, DNS/TLS, throttling, auth, authorization và key state.
- [ ] Đã định nghĩa security invariant và fail-closed behavior.
- [ ] Không có fallback ngoài policy sang software key hoặc thuật toán yếu.
- [ ] Retry có giới hạn, exponential backoff, jitter và deadline.
- [ ] Lỗi không retry được như AccessDenied/InvalidCiphertext được phân loại riêng.
- [ ] Operation có side effect dùng idempotency hoặc cơ chế chống duplicate.
- [ ] Circuit breaker, bulkhead và queue có giới hạn.
- [ ] DEK cache có TTL, scope, memory protection và revocation policy.
- [ ] Multi-region/failover dùng key identity và policy đã được kiểm thử.
- [ ] Backup/restore giữ đúng key version và recovery path.
- [ ] Java adapter ánh xạ exception theo loại, không dựa vào message.
- [ ] Health check không tạo tải KMS quá mức.
- [ ] Metrics và audit không chứa key material hoặc plaintext.
- [ ] Có fault injection cho timeout, 5xx, throttling, DNS/TLS và HSM session.
- [ ] Có recovery test sau outage, gồm queue drain và dữ liệu cũ.
- [ ] Có runbook và owner cho failover/incident.

## 30. Checklist đánh giá một lần KMS outage

Khi outage xảy ra, hãy xác nhận:

- [ ] Operation và key ID/version nào bị ảnh hưởng?
- [ ] Lỗi là unavailable, throttled, denied, invalid request hay key state?
- [ ] Ứng dụng có retry trong giới hạn và breaker hoạt động đúng không?
- [ ] Có operation nào đã hoàn tất nhưng caller mất response không?
- [ ] Có duplicate key/data key hoặc giao dịch không?
- [ ] Cache DEK có được dùng đúng TTL, tenant và policy không?
- [ ] Có fallback trái phép hoặc key material bị ghi ra disk/log không?
- [ ] Ciphertext, wrapped DEK và key version có còn nguyên vẹn không?
- [ ] Failover có đúng key identity, policy và audit không?
- [ ] Sau phục hồi, dữ liệu cũ giải mã được và queue xử lý đúng không?
- [ ] Rotation/backup/restore job có trạng thái nhất quán không?
- [ ] Audit evidence, timeline và hành động khắc phục đã được lưu chưa?

Kiểm thử KMS unavailable phải chứng minh ứng dụng giữ được ranh giới bảo vệ khóa khi dependency gặp sự cố. Hệ thống có thể giảm chức năng, retry có giới hạn hoặc dùng cache/failover đã được phê duyệt, nhưng không được tự ý hạ mức bảo mật để tiếp tục hoạt động. Test cần bao phủ từng operation, các loại lỗi, hành vi khi outage và quá trình phục hồi; đồng thời xác minh dữ liệu, key version, audit và trạng thái nghiệp vụ sau mỗi kịch bản.
