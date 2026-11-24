# Chọn key rotation schedule

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cryptoperiod và vì sao signing key cần được xoay vòng có kế hoạch.
- Chọn lịch rotation dựa trên loại khóa, thời hạn token, lưu lượng ký, mức độ ảnh hưởng khi khóa bị lộ và khả năng phân phối JWKS.
- Thiết kế quy trình rotation bình thường với giai đoạn publish, activate, verify-only và retire.
- Phân biệt planned rotation với emergency rotation khi khóa bị compromise.
- Xác định overlap window, cache behavior, tiêu chí rollback và các phép kiểm thử trước khi áp dụng production.
- Ghi quyết định thiết kế thành policy có chủ sở hữu, bằng chứng và lịch rà soát.

## 1. Key rotation schedule là gì?

**Key rotation schedule** là lịch và quy trình thay thế khóa mật mã đang được sử dụng bằng khóa mới. Trong hệ thống OAuth 2.0/OIDC, lịch này thường áp dụng cho signing key dùng ký JWT, nhưng cũng cần xem xét riêng encryption key, HMAC secret, TLS certificate và các khóa khác.

Khóa ký token bảo vệ tính toàn vẹn và nguồn phát hành của JWT. Nếu private key bị lộ, kẻ tấn công có thể tạo token giả với subject, audience, scope hoặc thời hạn do chúng chọn. Nếu một khóa tồn tại quá lâu, khoảng thời gian mà khóa bị lộ có thể bị khai thác cũng kéo dài. Rotation giới hạn thời gian sử dụng một khóa và giúp tổ chức thay thế khóa trước khi có sự cố.

Rotation không tự động làm token cũ mất hiệu lực. Với JWT, resource server có thể tiếp tục xác minh chữ ký bằng public key cũ và chấp nhận token cho đến khi token hết hạn hoặc bị chặn bởi cơ chế trạng thái. Vì vậy, lịch rotation phải được thiết kế cùng token lifetime, JWKS cache, thời gian đồng bộ và cách revoke.

**Không có một chu kỳ cố định phù hợp với mọi hệ thống.** Quyết định cần dựa trên mục đích sử dụng khóa, thuật toán, mức rủi ro, yêu cầu pháp lý/chuẩn nội bộ, khả năng của KMS/HSM và năng lực vận hành.

## 2. Phân biệt các loại khóa và vòng đời

Không nên dùng một lịch rotation duy nhất cho mọi khóa trong hệ thống:

| Loại khóa | Mục đích | Yếu tố quyết định lịch |
| --- | --- | --- |
| Asymmetric signing key | Private key ký JWT; public key xác minh | Cryptoperiod, token TTL, lượng token, phạm vi issuer, KMS/HSM và JWKS propagation |
| HMAC signing secret | Cùng một secret ký và xác minh token | Số verifier giữ secret, số lần sử dụng, cách phân phối secret và nguy cơ lộ ở từng service |
| Encryption key | Mã hóa dữ liệu hoặc wrapping data key | Loại dữ liệu, lượng dữ liệu mã hóa, yêu cầu lưu trữ lâu dài và khả năng re-encrypt |
| TLS private key/certificate | Bảo vệ kênh truyền và xác thực máy chủ/client | Thời hạn certificate, PKI policy, ACME/CA workflow và khả năng reload |
| Client secret | Client authentication tại token endpoint | Thời hạn credential, khả năng dual-secret rollout và mức độ phơi lộ |
| KMS/HSM root/key-encryption key | Bảo vệ key material hoặc key hierarchy | Policy của provider, compliance, backup/recovery và quyền quản trị |

Bài này tập trung vào signing key của JWT và các thành phần trực tiếp ảnh hưởng đến việc xác minh token. Lịch của encryption key hoặc TLS certificate phải được quản lý theo policy riêng.

### 2.1 Cryptoperiod

**Cryptoperiod** là khoảng thời gian một khóa được phép dùng cho một mục đích mật mã nhất định. Nó có thể được giới hạn theo thời gian, số lần sử dụng, lượng dữ liệu được xử lý hoặc một điều kiện kết hợp.

Khi chọn cryptoperiod, cần trả lời:

- Khóa dùng để ký loại token nào và cho issuer nào?
- Mỗi ngày khóa ký bao nhiêu token?
- Token được phép tồn tại tối đa bao lâu?
- Nếu khóa bị lộ, bao nhiêu ứng dụng và tenant bị ảnh hưởng?
- Khóa có nằm trong KMS/HSM và có kiểm soát quyền sử dụng không?
- Chuẩn, hợp đồng hoặc policy nội bộ yêu cầu thời hạn nào?
- Có thể xoay khóa và cập nhật verifier trong thời gian mục tiêu không?

NIST SP 800-57 cung cấp hướng dẫn quản lý khóa và các yếu tố để xác định cryptoperiod theo loại khóa, mục đích và rủi ro. Không nên trích một con số duy nhất từ tài liệu rồi áp dụng cho mọi signing key; hãy đối chiếu đúng loại khóa và phiên bản hướng dẫn đang áp dụng.

### 2.2 Tách khóa theo mục đích và phạm vi

Tổ chức nên cân nhắc tách khóa theo:

- Môi trường: development, test, staging và production.
- Issuer hoặc trust domain.
- Tenant hoặc nhóm khách hàng khi cần cô lập rủi ro.
- Mục đích: ký access token, ID Token hoặc loại assertion khác.
- Vùng triển khai hoặc boundary quản trị nếu yêu cầu bảo mật đòi hỏi.

Không dùng chung private key production cho test. Không để một signing key dùng cho nhiều issuer không liên quan nếu việc tách khóa giúp giảm blast radius. Việc tách khóa cần cân bằng với số lượng key phải vận hành và khả năng quản lý JWKS.

## 3. Các đầu vào để chọn lịch rotation

Trước khi đặt chu kỳ, thu thập các thông số sau:

| Đầu vào | Câu hỏi | Ảnh hưởng tới quyết định |
| --- | --- | --- |
| Key purpose | Khóa ký loại token nào? | Xác định policy và phạm vi tin cậy |
| Token max lifetime | Token ký bằng key có thể sống tối đa bao lâu? | Xác định thời gian giữ public key cũ để xác minh token hợp lệ |
| Clock skew | Verifier cho phép lệch giờ bao nhiêu? | Cộng vào thời gian giữ key cũ |
| JWKS cache TTL | Verifier cache JWKS trong bao lâu? | Xác định thời gian publish key mới trước khi bắt đầu ký |
| Propagation delay | Bao lâu để mọi verifier nhận cấu hình/key mới? | Xác định publish lead time và tiêu chí rollout |
| Signing volume | Khóa ký bao nhiêu token mỗi ngày? | Có thể tạo giới hạn theo lượng sử dụng |
| Compromise impact | Bao nhiêu API, tenant và client tin khóa? | Blast radius và mức độ cần rotation thường xuyên |
| KMS/HSM capability | Có tạo key, disable, rotate, audit và delete tự động không? | Khả năng vận hành và tốc độ phản ứng |
| Compliance/policy | Có yêu cầu cryptoperiod hoặc bằng chứng kiểm toán không? | Ràng buộc tối thiểu và retention |
| Recovery capability | Có key dự phòng, rollback và quy trình emergency không? | Giảm rủi ro khi rotation lỗi |

### Token lifetime và overlap window

Giả sử issuer chuyển từ key K1 sang K2 tại thời điểm T. Sau T, issuer không ký token mới bằng K1 nữa. Một token cuối cùng được ký bằng K1 có thể còn hợp lệ đến thời điểm expiration của nó.

Thời gian giữ public key K1 để xác minh token hợp lệ cần ít nhất bao phủ:

`last_K1_issue_time + max_token_lifetime + allowed_clock_skew`

Sau thời điểm đó, token hợp lệ được ký bằng K1 phải hết hạn theo policy. Nếu hệ thống có token TTL khác nhau theo client hoặc audience, dùng lifetime lớn nhất thực tế được phép. Đừng chỉ lấy TTL trung bình.

JWKS cache có hai vai trò khác nhau:

- **Trước khi ký bằng K2:** cần publish K2 đủ sớm để verifier tải được public key mới. Lead time phải tính cache TTL, propagation delay và thời gian refresh/retry.
- **Sau khi gỡ K1:** verifier có thể vẫn giữ public key K1 trong cache. Với rotation bình thường, token K1 đã hết hạn sẽ bị chặn bởi kiểm tra expiration. Nếu muốn xác minh key đã bị loại khỏi trust set, cần cache invalidation hoặc chờ cache cũ hết hạn.

Vì vậy, không nên dùng một công thức overlap duy nhất mà bỏ qua hai giai đoạn này. Tính riêng **publish lead time**, **old-key verification window** và **trust-cache convergence**.

## 4. Quy trình planned rotation

Một rotation bình thường nên có các trạng thái rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> PREPARED
    PREPARED --> PUBLISHED: Công bố public key mới
    PUBLISHED --> ACTIVE_SIGNING: Verifier đã nhận key mới
    ACTIVE_SIGNING --> VERIFY_ONLY: Ngừng ký bằng key cũ
    VERIFY_ONLY --> RETIRED: Token cũ hết hạn
    RETIRED --> DESTROYED: Xóa private key theo policy
~~~

### Bước 1: Chuẩn bị key mới

Sinh key mới trong KMS/HSM hoặc môi trường bảo vệ được phê duyệt. Gán key ID (`kid`) duy nhất, ghi nhận thuật toán, issuer, mục đích, thời điểm tạo và owner. Kiểm tra policy key usage và quyền truy cập. Private key không cần export nếu provider có thể ký trực tiếp.

### Bước 2: Publish public key mới

Đưa public JWK K2 lên JWKS cùng với public JWK K1. Chưa chuyển issuer sang ký bằng K2 cho tới khi các verifier có cơ hội nhận key mới. Kiểm tra JWKS response, TLS, cache header, `kid`, `kty`, `use`, `alg` và các trường cần thiết theo profile.

### Bước 3: Xác nhận verifier đã nhận key

Có thể dùng telemetry, probe hoặc test từ nhiều vùng để xác minh resource server đã tải K2. Không chỉ kiểm tra endpoint JWKS trả về K2; cần kiểm tra cache ở verifier thật. Nếu verifier chỉ refresh khi gặp `kid` chưa biết, cần hiểu hành vi và giới hạn retry của nó.

### Bước 4: Chuyển signing key

Issuer bắt đầu ký token mới bằng K2 và đặt header `kid` đúng với public key tương ứng. Giữ K1 ở trạng thái verify-only để xác minh token đã phát hành trước đó. Theo dõi tỉ lệ token mới được xác minh thành công trên các resource server.

### Bước 5: Chờ token K1 hết hạn

Ghi nhận thời điểm cuối cùng K1 được dùng để ký. Giữ public key K1 cho tới khi token hợp lệ cuối cùng đã hết hạn, cộng clock skew và biên an toàn vận hành đã xác định. Nếu issuer có thể phát hành token TTL dài bất thường, phải chặn cấu hình đó trước khi tính thời điểm retire.

### Bước 6: Gỡ key cũ và xác minh

Gỡ K1 khỏi JWKS/trust set, làm mới cache theo khả năng và xác minh:

- Token mới ký bằng K2 vẫn hợp lệ.
- Token K1 đã hết hạn bị từ chối.
- Token có chữ ký giả hoặc `kid` không được tin cậy bị từ chối.
- Không có verifier còn phụ thuộc K1 ngoài kế hoạch.

### Bước 7: Hủy hoặc lưu trữ key theo policy

Sau khi retire, disable/delete private key K1 theo policy KMS/HSM và retention. Nếu cần xác minh chữ ký lịch sử cho audit hoặc hồ sơ lưu trữ, giữ metadata/public key hoặc chứng thư theo quy định; việc giữ public key để kiểm chứng lịch sử không có nghĩa tiếp tục tin key đó cho access token mới.

## 5. Chọn chu kỳ rotation như thế nào?

Không có một lịch chung. Dùng cách tiếp cận sau:

1. Xác định cryptoperiod được policy/chuẩn áp dụng cho loại khóa.
2. Đánh giá blast radius nếu khóa bị lộ và số lượng token được ký.
3. Xác định token lifetime tối đa, clock skew và cache/propagation.
4. Xác nhận năng lực tự động hóa và kiểm soát KMS/HSM.
5. Chọn chu kỳ planned rotation và thời gian chuẩn bị.
6. Đặt trigger rotation sớm hơn lịch khi có dấu hiệu rủi ro.
7. Đo kết quả mỗi lần rotation và điều chỉnh policy.

### Ma trận quyết định gợi ý

| Mức rủi ro | Đặc điểm | Cách chọn lịch |
| --- | --- | --- |
| Thấp | Ít verifier, token TTL ngắn, key trong KMS/HSM, blast radius nhỏ | Có thể dùng cryptoperiod dài hơn theo policy; vẫn kiểm thử rotation định kỳ |
| Trung bình | Nhiều API/client, nhiều replica, token TTL vừa phải | Rotation định kỳ tự động; đo propagation và đặt overlap có kiểm soát |
| Cao | Nhiều tenant, dữ liệu nhạy cảm, signing volume lớn hoặc nhiều hệ thống tin issuer | Cryptoperiod ngắn hơn theo risk assessment; tự động hóa, tách key và diễn tập emergency |
| Rất cao | Hạ tầng trọng yếu hoặc hậu quả compromise nghiêm trọng | Policy chuyên biệt, giới hạn usage, HSM/dual control, giám sát liên tục và diễn tập thường xuyên |

Các mức trên là phân loại tương đối, không phải lịch số ngày bắt buộc. Quyết định cuối cùng phải có lý do, owner, approver và bằng chứng kiểm thử.

### Ví dụ schedule minh họa

Một tổ chức có thể bắt đầu PoC với policy giả định:

~~~yaml
tokenSigning:
  algorithm: RS256
  plannedRotationDays: 90
  publishLead:
    jwksCacheMaxAgeSeconds: 3600
    propagationBudgetSeconds: 300
    safetyMarginSeconds: 300
    publishBeforeActivationSeconds: 4200
  tokenPolicy:
    maxAccessTokenLifetimeSeconds: 600
    allowedClockSkewSeconds: 60
  oldKey:
    retainForVerification: true
    retireAfterLastIssuePlusSeconds: 960
  emergency:
    compromisedKeyAction: immediate_reject
    purgeVerifierCaches: required
~~~

Đây là ví dụ cấu hình để minh họa cách biểu diễn policy, **không phải khuyến nghị 90 ngày cho mọi hệ thống**. Trong ví dụ, 960 giây tương ứng 10 phút token lifetime + 60 giây clock skew + 5 phút biên an toàn vận hành. `publishBeforeActivationSeconds` là 4.200 giây, tương ứng JWKS cache tối đa 3.600 giây + propagation budget 300 giây + safety margin 300 giây. Publish lead là giai đoạn để key mới lan tới verifier; nó được tính riêng với old-key verification window. Môi trường thật phải thay số bằng cache TTL, propagation đo được, cryptoperiod và mức rủi ro của chính hệ thống.

## 6. Planned rotation và emergency rotation

Hai loại rotation có mục tiêu khác nhau:

| Nội dung | Planned rotation | Emergency rotation |
| --- | --- | --- |
| Nguyên nhân | Đến cryptoperiod hoặc lịch policy | Private key nghi bị lộ, quyền KMS bị chiếm, thuật toán bị phá vỡ hoặc sự cố nghiêm trọng |
| Mục tiêu | Thay khóa có kiểm soát, không gián đoạn | Chặn khả năng giả mạo token càng nhanh càng tốt |
| Overlap | Có thể giữ old key verify-only trong thời gian token cũ còn hạn | Có thể phải loại old key ngay, không duy trì overlap tin cậy |
| Token cũ | Chấp nhận đến khi hết hạn theo policy | Có thể phải từ chối toàn bộ token ký bằng key bị compromise |
| Cache | Cập nhật theo lịch và theo dõi | Purge/invalidate khẩn cấp, xác nhận từng verifier |
| Phê duyệt | Theo change management bình thường | Theo incident response/emergency change |

Khi private key bị compromise, giữ public key cũ trong JWKS để “chờ token hết hạn” có thể cho phép attacker tiếp tục ký token giả. Cần chặn `kid` bị xâm phạm tại verifier, purge cache, thu hồi token liên quan và đánh giá phạm vi giả mạo. Nếu không thể bảo đảm mọi verifier nhận lệnh chặn, có thể cần cô lập resource server hoặc chuyển sang chế độ từ chối token từ issuer bị ảnh hưởng cho tới khi tin cậy được khôi phục.

## 7. Xử lý JWKS cache và nhiều verifier

JWKS là tập hợp public key mà verifier sử dụng để xác minh chữ ký. Rotation chỉ thành công khi các verifier thực sự có key cần thiết và ngừng tin key đã retire.

Kiểm tra:

- Cache-Control/ETag và cách verifier thực hiện conditional request.
- Thời gian refresh định kỳ và hành vi khi nhận `kid` chưa biết.
- Có stale-if-error hoặc cache fallback không; fallback kéo dài bao lâu?
- Có cơ chế purge cache từ xa hoặc event push không?
- Mỗi replica/region có cache độc lập hay dùng chung?
- Nếu JWKS endpoint lỗi, verifier fail closed hay dùng cache cũ theo policy nào?
- Verifier có cho phép thuật toán khác với allowlist của issuer không?

Không tải key từ URL do JWT header cung cấp. `kid` chỉ là selector để chọn key trong JWKS của issuer đã được cấu hình và xác minh; nó không phải bằng chứng tin cậy và không được dùng để tạo đường dẫn hoặc truy vấn tùy ý.

### Kiểm tra trạng thái sau rollout

Nên có telemetry theo:

- Issuer và `kid` đang ký token mới.
- Số verifier đã xác nhận nhận key mới.
- Tỉ lệ xác minh token theo `kid`.
- Lỗi unknown key, invalid signature và invalid issuer/audience.
- Replica còn dùng cache version cũ.
- Token ký bằng key cũ còn được sử dụng sau thời điểm dự kiến.

Nếu verifier vẫn nhận token K1 sau thời điểm retire, cần phân biệt token chưa hết hạn hợp lệ, cache cũ, issuer còn ký bằng K1 hoặc token giả mạo. Không xóa key trước khi biết nguyên nhân nếu đó là planned rotation; với compromise, ưu tiên containment và chấp nhận gián đoạn có kiểm soát.

## 8. HMAC và asymmetric key rotation

### Asymmetric signing

Với RSA hoặc EC, issuer giữ private key để ký; resource server chỉ cần public key để xác minh. Điều này giúp giảm số nơi chứa khả năng ký token. Khi rotate:

- Publish public key mới.
- Chuyển issuer sang private key mới.
- Giữ public key cũ trong thời gian xác minh token cũ.
- Gỡ public key cũ sau khi hết cửa sổ hợp lệ.

Đây thường là lựa chọn phù hợp cho hệ thống nhiều resource server độc lập.

### HMAC signing

Với HMAC, mọi verifier cần secret để xác minh và do đó cũng có khả năng tạo chữ ký. Rotation yêu cầu phân phối secret mới tới toàn bộ verifier an toàn:

1. Đưa secret mới tới verifier theo cơ chế dual-key.
2. Xác minh tất cả verifier đã có secret mới.
3. Chuyển issuer sang ký bằng secret mới.
4. Giữ secret cũ chỉ để xác minh token cũ trong overlap đã tính.
5. Gỡ secret cũ khỏi tất cả verifier và secret store.

Nếu một microservice không cần quyền ký, việc cấp HMAC secret cho service đó làm tăng blast radius. Hãy cân nhắc asymmetric key để tách quyền ký và quyền xác minh.

## 9. Rollback và failure handling

Rotation có thể lỗi do KMS unavailable, JWKS không cập nhật, replica chưa nhận key hoặc issuer phát hành token bằng `kid` không được công bố. Xác định trước:

- Điều kiện dừng rollout: tỉ lệ verify fail, unknown kid hoặc replica chưa cập nhật vượt ngưỡng.
- Ai có quyền dừng và ai phê duyệt rollback.
- Có thể chuyển issuer trở lại key cũ hay không và key cũ còn được bảo vệ không.
- Không rollback về key đã compromise hoặc key bị vô hiệu hóa.
- Cách giữ token đã phát hành bằng key mới trong khi xử lý sự cố.
- Cách thông báo ứng dụng phụ thuộc và ghi audit event.

Với planned rotation, rollback có thể tạm chuyển issuer về K1 nếu K1 vẫn an toàn và còn trong cryptoperiod. Với emergency rotation do K1 bị compromise, tuyệt đối không khôi phục K1 làm signing key để giải quyết lỗi rollout.

## 10. Kiểm thử schedule trước production

Tạo môi trường test với issuer, JWKS và nhiều verifier/replica. Dùng key test riêng, không dùng private key production.

| Test case | Hành động | Kỳ vọng |
| --- | --- | --- |
| Publish key mới | Thêm K2 vào JWKS nhưng chưa ký bằng K2 | Verifier có thể tải K2 mà token K1 vẫn hợp lệ |
| Switch signing | Issuer ký token mới bằng K2 | Token mới có `kid=K2` và được mọi verifier chấp nhận |
| Old token overlap | Dùng token K1 còn hạn | Token hợp lệ vẫn được chấp nhận trong overlap |
| Old token expired | Tiến clock qua `exp` + skew | Token K1 hết hạn bị từ chối |
| Retire old key | Gỡ K1 và refresh cache | Verifier không còn tin K1 theo policy |
| Unknown kid | Gửi token có kid không có trong JWKS | Từ chối; không fetch URL tùy ý |
| Stale JWKS cache | Giữ một replica chưa refresh | Phát hiện replica cũ và không đánh dấu rollout hoàn tất |
| KMS unavailable | Làm gián đoạn signing operation | Không phát hành token bằng key không rõ trạng thái |
| Concurrent rotation | Khởi động hai rotation cùng lúc | Lock/coordination ngăn đổi trạng thái sai |
| Emergency compromise | Đánh dấu K1 bị lộ và phát lệnh chặn | Mọi verifier từ chối token K1 sau SLA khẩn cấp |
| Rollback | Giả lập K2 không được verifier nhận | Chỉ rollback nếu K1 còn an toàn và được phép |
| Audit | Thực hiện create/publish/activate/retire | Có actor, thời gian, key ID và kết quả; không log private key |

Kiểm thử phải bao gồm cả token có chữ ký đúng nhưng issuer/audience sai. Rotation không thay thế validation các claims này.

## 11. Ví dụ Java: kiểm tra thời điểm retire

Ví dụ sau tính thời điểm sớm nhất có thể retire public key cũ dựa trên thời điểm ký token cuối cùng. Nó chỉ là logic lập lịch; không thay thế việc xác minh trạng thái của từng verifier.

~~~java
import java.time.Duration;
import java.time.Instant;

final class KeyRetirementSchedule {
    static Instant earliestRetirement(
            Instant lastOldKeyIssueTime,
            Duration maxTokenLifetime,
            Duration allowedClockSkew,
            Duration operationalSafetyMargin) {

        if (maxTokenLifetime.isNegative()
                || allowedClockSkew.isNegative()
                || operationalSafetyMargin.isNegative()) {
            throw new IllegalArgumentException(
                    "Durations must not be negative");
        }

        return lastOldKeyIssueTime
                .plus(maxTokenLifetime)
                .plus(allowedClockSkew)
                .plus(operationalSafetyMargin);
    }
}
~~~

Ví dụ unit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class KeyRetirementScheduleTest {
    @Test
    void includesTokenLifetimeClockSkewAndSafetyMargin() {
        Instant lastIssue =
                Instant.parse("2030-01-01T00:00:00Z");

        Instant result = KeyRetirementSchedule.earliestRetirement(
                lastIssue,
                Duration.ofMinutes(10),
                Duration.ofSeconds(60),
                Duration.ofMinutes(5));

        assertEquals(
                Instant.parse("2030-01-01T00:16:00Z"),
                result);
    }
}
~~~

Hàm này giả định issuer đã ngừng ký bằng key cũ tại `lastOldKeyIssueTime` và không tồn tại token lifetime ngoại lệ. Nếu token được phát hành từ nhiều node, cần xác định thời điểm cuối cùng trên tất cả node. Nếu hệ thống có verifier-specific clock skew hoặc token TTL khác nhau, dùng giá trị lớn nhất được cho phép. JWKS publish lead và cache invalidation sau khi retire phải được tính riêng.

## 12. Ghi quyết định thiết kế

Một ADR/policy rotation nên ghi:

- Phạm vi issuer, token type, thuật toán và key purpose.
- Nguồn policy cryptoperiod và lý do chọn chu kỳ.
- Max token lifetime, clock skew, JWKS cache TTL và propagation budget.
- Thời gian publish lead, old-key verification window và trust-cache convergence.
- KMS/HSM, key owner, quyền sử dụng, dual control và audit.
- Quy trình planned rotation, emergency rotation và rollback.
- Người phê duyệt, lịch review và trigger ngoài lịch.
- Test evidence, metrics và kết quả diễn tập gần nhất.

Mẫu quyết định minh họa:

~~~yaml
keyRotationDecision:
  issuer: https://identity.example
  keyPurpose: jwt-access-token-signing
  algorithm: RS256
  keyStore: managed-kms
  plannedCryptoperiodDays: 90
  maxTokenLifetimeSeconds: 600
  allowedClockSkewSeconds: 60
  jwksCacheMaxAgeSeconds: 3600
  publishBeforeActivationSeconds: 4200
  oldKeyRetirement:
    fromLastIssueSeconds: 960
    requiresVerifierConvergence: true
  emergency:
    compromisedKey: reject-immediately
    cachePurge: mandatory
  owner: identity-platform-team
  reviewCadence: quarterly
~~~

Các con số là dữ liệu mẫu, cần thay bằng số liệu và policy thật. Đặc biệt, `publishBeforeActivationSeconds` phải bao phủ cache TTL + propagation + margin; `oldKeyRetirement.fromLastIssueSeconds` phải bao phủ max token lifetime + skew + margin. Điều kiện verifier convergence là một gate vận hành bổ sung.

## 13. Những sai lầm thường gặp

1. **Chọn rotation theo một con số phổ biến:** bỏ qua cryptoperiod, token TTL, key usage và mức rủi ro thực tế.
2. **Gỡ key cũ ngay sau khi chuyển signing:** token hợp lệ đã ký bằng key cũ có thể bị từ chối sớm.
3. **Ký bằng key mới trước khi publish public key:** verifier không có key để xác minh token mới.
4. **Chỉ kiểm tra JWKS endpoint:** cache ở replica/region có thể chưa cập nhật.
5. **Dùng overlap trong sự cố compromise:** attacker vẫn có thể ký token giả bằng key cũ.
6. **Xem xóa private key là revoke mọi JWT:** verifier còn public key cache có thể tiếp tục chấp nhận token.
7. **Không ghi thời điểm ký cuối cùng:** không tính được thời điểm retire chính xác.
8. **Cho phép token TTL tùy ý:** một token có lifetime dài có thể kéo dài overlap ngoài dự kiến.
9. **Dùng chung HMAC secret quá rộng:** mọi verifier có thể trở thành nơi ký token.
10. **Không có rollback/emergency drill:** khi rotation lỗi, đội vận hành không biết cách khôi phục an toàn.

## 14. Checklist chọn key rotation schedule

- [ ] Đã xác định loại khóa, mục đích, issuer và phạm vi tin cậy.
- [ ] Cryptoperiod có căn cứ từ risk assessment, tiêu chuẩn và policy.
- [ ] Đã đo signing volume và đánh giá blast radius khi key compromise.
- [ ] Đã xác định max token lifetime và allowed clock skew.
- [ ] Đã đo JWKS cache TTL, propagation delay và hành vi refresh của verifier.
- [ ] Publish lead đủ để mọi verifier nhận public key mới trước khi ký.
- [ ] Old key chỉ được giữ verify-only trong thời gian cần thiết cho token hợp lệ.
- [ ] Có thời điểm cuối cùng ký bằng old key và công thức retire rõ ràng.
- [ ] Emergency rotation có thể chặn key bị compromise, purge cache và revoke token liên quan.
- [ ] KMS/HSM, key access, dual control và audit đã được xác minh.
- [ ] Có rollback chỉ dành cho key cũ còn an toàn.
- [ ] Có test nhiều replica/region, cache stale, unknown kid và failure mode.
- [ ] Có metrics, owner, approver và lịch review policy.

## Ghi nhớ

**Chọn key rotation schedule bằng cách cân bằng cryptoperiod, thời hạn token, khả năng phân phối key và mức độ thiệt hại khi compromise.** Planned rotation cần publish key mới trước khi ký, giữ key cũ để xác minh token còn hạn rồi retire sau thời điểm an toàn. Emergency rotation phải chặn key bị xâm phạm và cập nhật mọi verifier nhanh nhất có thể. Lịch số ngày chỉ là một phần của policy; khả năng xác minh, revoke, giám sát và diễn tập mới quyết định rotation có an toàn trong production hay không.

### Tài liệu tham khảo

- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- IETF RFC 7517 — JSON Web Key (JWK), JWKS và key identifiers: https://www.rfc-editor.org/rfc/rfc7517
- IETF RFC 7519 — JSON Web Token (JWT), claims và expiration: https://www.rfc-editor.org/rfc/rfc7519
- IETF RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700
- OWASP Key Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html
