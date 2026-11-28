# Test key revocation

Thu hồi khóa và credential là một thao tác quan trọng trong vòng đời quản lý khóa mật mã. Tuy nhiên, việc đổi trạng thái một bản ghi thành `REVOKED` chưa chứng minh rằng bí mật cũ đã mất hiệu lực trên toàn hệ thống. Token có thể còn được cache, session có thể vẫn hoạt động, service secret cũ có thể vẫn được dịch vụ đích chấp nhận và ciphertext có thể vẫn phụ thuộc vào khóa cũ.

**Test key revocation** là nhóm kiểm thử xác minh rằng khi một credential, chứng thư hoặc khóa bị thu hồi, mọi điểm thực thi liên quan sẽ từ chối việc sử dụng mới theo chính sách; trạng thái thu hồi được lan truyền đúng; các session và cache được xử lý; dữ liệu cần bảo toàn vẫn có thể phục hồi theo thiết kế; và audit ghi lại đầy đủ thao tác mà không làm lộ bí mật.

Trong module Security Key Management Fundamentals, kiểm thử cần gắn với toàn bộ vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, rotation, thu hồi, backup, recovery và destruction. Cần phân biệt thu hồi password, API token, service secret, chứng thư, signing key, KEK và DEK vì mỗi loại có điểm thực thi và hậu quả khác nhau.

## 1. Mục tiêu của kiểm thử key revocation

Một bộ kiểm thử thu hồi cần trả lời các câu hỏi:

- Credential hoặc key version đã bị thu hồi có bị từ chối ở lần sử dụng tiếp theo không?
- Mọi API gateway, resource server, worker, replica và region có nhận trạng thái mới trong thời gian mục tiêu không?
- Access token, refresh token, session cookie hoặc connection đang tồn tại có được xử lý theo chính sách không?
- Credential mới có thể thay thế credential cũ mà không làm gián đoạn workload hợp lệ không?
- Dữ liệu đã mã hóa bằng khóa cũ có còn đọc được trong giai đoạn chuyển tiếp không?
- Một khóa bị compromise có bị ngăn sử dụng cho cả thao tác mới và quy trình thông thường không?
- Revoke lặp lại có an toàn, idempotent và không làm trạng thái bị đảo ngược không?
- Audit event có ghi đúng actor, resource, lý do, thời điểm và kết quả không?
- Log, response và telemetry có tránh chứa key material, password, token hoặc plaintext không?

Kết quả mong đợi không chỉ là API thu hồi trả về HTTP 200. Cần chứng minh credential cũ thực sự bị từ chối ở nơi xác thực hoặc nơi thực hiện thao tác mật mã, trạng thái được lan truyền, và không có đường vòng tiếp tục chấp nhận bản sao credential cũ.

## 2. Phân biệt revoke, disable, expire, rotate và destroy

Trước khi viết test, cần xác định chính xác thao tác đang được kiểm tra:

| Hành động | Ý nghĩa | Bằng chứng cần kiểm tra |
|---|---|---|
| Revoke | Đánh dấu credential/chứng thư không còn được chấp nhận | Validator hoặc relying party từ chối credential |
| Disable | Tạm dừng thao tác với key hoặc secret version | KMS/HSM/provider từ chối action bị vô hiệu hóa |
| Expire | Credential hết hiệu lực theo thời gian | Request sau thời điểm hết hạn bị từ chối |
| Rotate | Tạo giá trị mới và chuyển workload sang dùng giá trị mới | Credential mới hoạt động; credential cũ bị thu hồi tại đúng thời điểm |
| Destroy | Hủy key material hoặc bản sao theo quy trình | Không còn khả năng sử dụng/khôi phục từ các bản sao được quản lý, theo semantics của nền tảng |

Một test chỉ kiểm tra cột `status=REVOKED` là chưa đủ. Ví dụ, xóa token khỏi bảng nội bộ nhưng resource server vẫn xác minh JWT cục bộ mà không hỏi trạng thái thì token có thể tiếp tục hợp lệ đến khi hết hạn. Tương tự, xóa một secret khỏi secret manager không làm database hoặc dịch vụ bên ngoài ngừng chấp nhận password cũ.

## 3. Xác định điểm thực thi thu hồi

Mỗi loại credential có một hoặc nhiều thành phần quyết định có chấp nhận credential hay không. Kiểm thử phải gọi đúng các điểm đó.

| Loại credential/key | Điểm thực thi chính | Kiểm thử thu hồi |
|---|---|---|
| Password | Authentication service | Password cũ không đăng nhập được; verifier mới hoạt động |
| Opaque API token | Token store hoặc introspection service | Token bị đánh dấu revoked và validator từ chối |
| JWT access token | Resource server, issuer, introspection hoặc denylist | Token bị từ chối theo cơ chế revoke đã thiết kế |
| Refresh token | Authorization server | Không cấp access token mới; token family bị xử lý theo policy |
| Service secret | Hệ thống đích đang xác thực secret | Credential cũ bị từ chối tại database/API/service đích |
| X.509 certificate | CA, CRL/OCSP và relying party | Client kiểm tra trạng thái và từ chối certificate đã revoke |
| Signing key | KMS/HSM, signing service và verifier | Không ký mới bằng khóa bị thu hồi; verifier áp dụng trust policy |
| Encryption key | KMS/HSM/provider và ứng dụng giải mã | Thao tác bị chặn hoặc giới hạn theo decrypt-only/recovery policy |

Nếu có nhiều lớp, test cần chứng minh cả lớp ứng dụng và lớp hạ tầng. Ví dụ, ứng dụng từ chối trước khi gọi KMS là tốt, nhưng KMS/HSM vẫn cần policy riêng để ngăn một workload bị bypass ứng dụng gọi trực tiếp.

## 4. Thiết kế ma trận kiểm thử thu hồi

Ma trận kiểm thử nên bao phủ principal, credential/key, trạng thái trước và sau revoke, action, điểm thực thi và thời gian propagation.

| Trước revoke | Hành động | Sau revoke | Kết quả mong đợi |
|---|---|---|---|
| Token active | Revoke token | Token revoked | Request dùng token cũ bị từ chối |
| Refresh token active | Revoke token family | Family revoked | Không thể refresh bằng bất kỳ token con nào trong family |
| Service secret v1 active | Cấp v2 rồi revoke v1 | v2 active, v1 revoked | Workload dùng v2 thành công; v1 bị dịch vụ đích từ chối |
| Certificate valid | CA revoke certificate | Revoked | Relying party kiểm tra CRL/OCSP và từ chối theo policy |
| Key v1 active | Disable hoặc retire v1 | Disabled/decrypt-only | Action không còn được phép bị từ chối; action được giữ lại vẫn hoạt động |
| KEK v1 đang wrap DEK | Rotate sang KEK v2 | DEK được rewrap | Wrapped DEK cũ/mới được xử lý theo version; không mất khả năng giải mã |
| Principal có quyền | Revoke permission | Permission revoked | Request mới bị từ chối sau propagation mục tiêu |

Nên có các biến thể với request đồng thời, cache chưa hết TTL, replica chậm, timeout, retry và lỗi audit sink. Test phải nêu rõ thời điểm bắt đầu đo và thời điểm kỳ vọng mọi điểm thực thi từ chối credential cũ.

## 5. Kiểm thử idempotency và trạng thái chuyển tiếp

Thu hồi thường được gọi lại do retry, timeout hoặc nhiều operator cùng xử lý. API revoke nên có hành vi idempotent: gọi lại không làm credential hoạt động trở lại và không ghi đè mất thông tin thu hồi ban đầu.

Các ca cần kiểm tra:

- Revoke một credential active lần đầu trả kết quả thành công và lưu `revokedAt`.
- Revoke cùng credential lần thứ hai trả `ALREADY_REVOKED` hoặc kết quả tương đương theo API.
- Revoke credential không tồn tại trả kết quả không tìm thấy theo contract, không tạo record giả.
- Hai request revoke đồng thời không tạo trạng thái mâu thuẫn.
- Retry sau client timeout đọc lại trạng thái trước khi thực hiện lại thao tác.
- Revoke không thể bị một thao tác cập nhật metadata thông thường ghi đè thành active.
- Chỉ quy trình reissue/replacement được ủy quyền mới tạo credential mới; không “unrevoke” bí mật cũ một cách ngầm định.

Với key state, cần kiểm tra state machine hợp lệ. Ví dụ, key `DESTROYED` không thể được chuyển về `ACTIVE` bằng một update metadata; nếu cần phục hồi, phải có backup/restore đúng quy trình và một định danh phiên bản được quản lý rõ ràng.

## 6. Kiểm thử thu hồi password và session

Password reset hoặc password revoke phải được kiểm tra cùng session và token đã phát hành. Thay verifier chỉ ngăn password cũ dùng cho lần đăng nhập mới; session cookie hoặc refresh token đã cấp trước đó có thể vẫn hoạt động.

Kịch bản kiểm thử:

1. Tạo người dùng test và đăng nhập bằng password v1.
2. Xác nhận session và refresh token được cấp.
3. Reset password sang v2 hoặc đánh dấu credential v1 không còn hợp lệ.
4. Thử đăng nhập bằng password v1 và xác minh bị từ chối.
5. Thử đăng nhập bằng password v2 và xác minh thành công.
6. Dùng session cũ gọi endpoint bảo vệ và kiểm tra kết quả theo policy session revocation.
7. Dùng refresh token cũ xin access token mới và xác minh bị từ chối nếu token family đã bị thu hồi.
8. Xác minh recovery code, app password hoặc factor bị lộ được xử lý theo đúng phạm vi.
9. Kiểm tra audit và thông báo bảo mật không chứa password hoặc token.

Nếu sản phẩm chủ đích giữ session đang hoạt động sau password change, test phải phản ánh chính sách đó và kiểm tra các phiên rủi ro cao được yêu cầu xác thực lại. Không tự suy luận rằng password đổi thì mọi session tự động bị thu hồi.

## 7. Kiểm thử opaque token, JWT và refresh token

### Opaque token

Opaque token thường được kiểm tra qua token store hoặc introspection endpoint. Sau khi revoke, validator cần nhận trạng thái `active=false` hoặc kết quả tương đương.

Test nên xác minh:

- Token active trước revoke được chấp nhận.
- Token bị revoke bị từ chối ở request kế tiếp sau propagation mục tiêu.
- Token khác của cùng user/client vẫn hoạt động nếu chỉ revoke một token.
- Revoke toàn bộ client/session chỉ ảnh hưởng đúng phạm vi được yêu cầu.
- Cache introspection không giữ kết quả active quá TTL cho phép.
- Token bị revoke không được tái kích hoạt khi database replica đồng bộ trễ.

### JWT access token

JWT có thể được xác minh cục bộ bằng chữ ký và claim `exp`, `iss`, `aud`. Nếu resource server không kiểm tra trạng thái trực tuyến, việc revoke một JWT đã phát hành không tự động làm chữ ký của nó mất hiệu lực.

Vì vậy, test cần phản ánh chính xác thiết kế:

- Với access token TTL ngắn, kiểm tra token cũ bị từ chối khi hết hạn.
- Với denylist theo `jti`, xác minh mọi resource server kiểm tra denylist và cache được invalidated.
- Với introspection, xác minh issuer trả `active=false` sau revoke.
- Với session/credential version, xác minh token phát hành trước mốc revoke bị từ chối.
- Nếu xoay signing key để xử lý compromise, xác minh ảnh hưởng đến mọi token ký bằng key cũ và khả năng chuyển tiếp key mới.

Không khẳng định JWT có thể bị revoke tức thời nếu kiến trúc chỉ xác minh chữ ký offline và không có denylist, introspection hoặc cơ chế version tương đương.

### Refresh token

Với refresh token rotation, mỗi lần refresh có thể phát hành token mới và vô hiệu hóa token trước. Test cần thử dùng lại token cũ, thu hồi family, revoke client và xử lý race giữa hai request refresh đồng thời. Nếu phát hiện reuse, hệ thống có thể thu hồi cả family/session theo chính sách để ngăn token bị sao chép tiếp tục được dùng.

## 8. Kiểm thử thu hồi service secret

Service secret thường được ứng dụng đọc lại để kết nối tới database hoặc API. Vì thế, thu hồi phải xảy ra tại hệ thống đích chấp nhận secret.

Kịch bản rotation và revocation:

1. Tạo secret v1 và cấu hình workload test sử dụng v1.
2. Xác minh workload kết nối thành công.
3. Tạo secret v2 tại dịch vụ đích và lưu vào secret manager.
4. Cấp workload quyền đọc v2; cập nhật client hoặc connection pool.
5. Xác minh kết nối mới dùng v2 thành công.
6. Thu hồi hoặc disable v1 tại dịch vụ đích.
7. Thử kết nối bằng v1 trực tiếp và xác minh bị từ chối.
8. Xác minh workload không còn lấy v1 từ cache hoặc local configuration.
9. Kiểm tra connection pool cũ được drain/refresh theo policy.
10. Xác minh audit có sự kiện tạo, đọc, rotate và revoke mà không chứa giá trị secret.

Chỉ xóa secret v1 khỏi secret manager không chứng minh credential đã bị thu hồi. Nếu database hoặc API vẫn chấp nhận v1, bản sao bị lộ vẫn có thể được sử dụng. Test phải xác minh ở chính hệ thống đích.

## 9. Kiểm thử certificate revocation

Certificate revocation thường được phân phối qua CRL hoặc OCSP. Việc CA ghi nhận certificate đã revoke không có nghĩa mọi client đều biết trạng thái ngay lập tức; client có thể cache CRL/OCSP response hoặc áp dụng chính sách soft-fail/hard-fail khác nhau.

Các ca kiểm thử:

- Certificate hợp lệ được chấp nhận trước khi revoke.
- CA phát hành trạng thái revoked với đúng serial number và issuer.
- Relying party lấy được CRL/OCSP response mới và từ chối certificate.
- Certificate khác cùng CA vẫn được chấp nhận nếu không bị ảnh hưởng.
- Cache trạng thái cũ hết hiệu lực trong thời gian mục tiêu.
- Khi không truy cập được OCSP/CRL, client hành xử đúng chính sách đã định.
- Certificate mới được cấp và xác minh đúng chain, identity và key usage.

Với hệ thống yêu cầu hard-fail, test phải chứng minh client từ chối khi không xác minh được trạng thái theo policy. Với soft-fail, test cần ghi rõ cửa sổ rủi ro và kiểm tra monitoring cảnh báo khi trạng thái không thể lấy được. Không giả định mọi TLS client đều có cùng hành vi kiểm tra revocation.

## 10. Kiểm thử encryption key, DEK và KEK

Thu hồi encryption key cần cân bằng giữa chặn sử dụng khóa và duy trì khả năng đọc dữ liệu hợp lệ.

### DEK bị thu hồi

DEK mã hóa payload. Nếu DEK bị compromise, test cần xác minh hệ thống dừng sử dụng DEK đó cho dữ liệu mới, tạo DEK mới và chuyển dữ liệu theo kế hoạch. Nếu dữ liệu cũ còn cần đọc, cần xác định rõ có cho phép recovery/decrypt trong môi trường kiểm soát hay phải chặn hoàn toàn theo mức độ compromise.

### KEK bị thu hồi

KEK bảo vệ DEK. Khi KEK cũ được rotate, test cần xác minh DEK được rewrap bằng KEK mới, metadata `wrappingKeyId/version` được cập nhật sau khi thao tác thành công và dữ liệu vẫn giải mã được. Nếu KEK bị compromise, rewrap đơn thuần không xóa được bản sao wrapped DEK và ciphertext mà attacker đã lấy trước đó; cần đánh giá re-encryption theo threat model.

### Các kiểm tra quan trọng

- Encrypt mới bằng key version đã disable/revoked bị từ chối.
- Decrypt dữ liệu cũ được phép hoặc bị chặn đúng theo policy đã định.
- Key ID/version trong metadata luôn trỏ tới đúng khóa.
- Wrapped DEK không bị xóa trước khi xác minh bản mới.
- Không destroy key material khi còn dữ liệu, backup hoặc archive phụ thuộc.
- Khi key đã destroyed, hệ thống không giả vờ khôi phục bằng cách tạo alias cùng tên.
- Audit ghi thao tác disable, revoke, rotate, rewrap, decrypt và destroy.

## 11. Kiểm thử propagation, cache và replica

Trong hệ thống phân tán, trạng thái revoke có thể được lưu ở token store, database replica, API gateway, authorization service, local cache, process memory và thiết bị người dùng. Test phải đo được thời gian từ khi trạng thái được ghi nhận tại nguồn đến khi mọi điểm thực thi từ chối credential cũ.

Định nghĩa **revocation latency**:

\[
T_{revoke} = t_{last\_accept} - t_{revoke\_commit}
\]

Trong đó `t_revoke_commit` là thời điểm trạng thái revoke được commit tại nguồn có thẩm quyền, còn `t_last_accept` là thời điểm cuối cùng bất kỳ điểm thực thi nào vẫn chấp nhận credential cũ. Mục tiêu SLA cần quy định `T_revoke` tối đa cho từng loại credential.

Test nên:

- Gửi request hợp lệ trước revoke để xác nhận baseline.
- Commit revoke và ghi nhận timestamp tại nguồn.
- Gửi request lặp lại tới tất cả node, region, gateway và đường truy cập.
- Kiểm tra cache invalidation event đã được nhận và xử lý.
- Kiểm tra replica lag, consumer bị lỗi và event bị mất.
- Kiểm tra restart workload không nạp lại trạng thái active cũ từ local cache.
- Đo thời điểm cuối cùng request dùng credential cũ được chấp nhận.
- Cảnh báo nếu propagation vượt SLA.

Không chỉ kiểm tra một instance hoặc chờ một TTL cố định rồi giả định toàn bộ hệ thống đã đồng bộ. Cần quan sát mọi điểm thực thi có quyền chấp nhận credential.

## 12. Kiểm thử concurrency, race condition và retry

Thu hồi có thể xảy ra đồng thời với request sử dụng credential. Hệ thống cần định nghĩa điểm hiệu lực: request đã được authorization trước thời điểm revoke có được phép hoàn tất hay phải bị hủy nếu thao tác chưa bắt đầu?

Các tình huống cần kiểm thử:

- Decrypt bắt đầu đồng thời với key disable.
- Hai refresh request dùng cùng refresh token trước khi token family bị revoke.
- Service secret v1 bị thu hồi trong lúc connection pool tạo kết nối mới.
- Revoke token đồng thời với request đang xác thực qua cache.
- Hai operator gửi cùng một lệnh revoke.
- Client timeout sau khi revoke đã commit rồi retry.
- Event invalidation đến sai thứ tự hoặc bị gửi trùng.

Test phải xác minh không có trạng thái cuối mâu thuẫn, không có quyền được khôi phục ngoài ý muốn và audit ghi được cả request ban đầu lẫn retry. Với thao tác có side effect, dùng transaction, compare-and-set, idempotency key hoặc state machine để xử lý concurrency.

## 13. Kiểm thử lỗi và fail-closed

Nếu hệ thống không thể xác định credential có còn hợp lệ hay không, hành vi cần theo policy đã phê duyệt. Với thao tác nhạy cảm, thường phải fail-closed thay vì mặc định cho phép.

Các fault injection test nên gồm:

- Token store hoặc introspection service timeout.
- KMS/HSM không khả dụng.
- Policy engine trả lỗi hoặc không xác định được decision.
- Database replica chậm hoặc không đồng bộ.
- Cache invalidation queue bị đầy hoặc consumer dừng.
- CRL/OCSP endpoint không truy cập được.
- Audit sink lỗi hoặc không ghi được event revoke.
- Credential metadata thiếu version, owner hoặc trạng thái.

Test phải xác minh ứng dụng không tự chuyển sang credential cũ, không bypass policy, không log secret và không trả thành công giả. Nếu có chế độ degraded operation, cần xác định rõ loại thao tác nào được phép, trong bao lâu và cách ghi nhận rủi ro.

## 14. Kiểm thử audit và bằng chứng thu hồi

Một lần revoke cần tạo audit event đủ để điều tra:

- Credential/key ID và version.
- Loại credential và owner.
- Actor hoặc workload yêu cầu thu hồi.
- Người phê duyệt nếu cần dual control.
- Lý do và ticket/incident reference.
- Thời điểm yêu cầu, commit và propagation hoàn tất.
- Kết quả, lỗi và các điểm thực thi chưa xác nhận.
- Thao tác thay thế, rotation, disable hoặc destroy liên quan.

Test cần xác minh audit không chứa password, token, private key, DEK, KEK hoặc plaintext. Kiểm tra cả event thành công, từ chối, retry và lỗi. Nếu revoke API trả success nhưng một replica vẫn chấp nhận credential cũ, audit/monitoring cần thể hiện propagation chưa hoàn tất thay vì đánh dấu toàn bộ quy trình đã xong.

## 15. Ví dụ Java: kiểm thử idempotent revoke cho API token

Ví dụ sau dùng JUnit 5 và Mockito để xác minh service thu hồi token gọi repository với thời điểm xác định và xử lý lần gọi lặp lại. Các domain type là minh họa; repository production cần thực hiện cập nhật nguyên tử trong transaction.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TokenRevocationServiceTest {
    @Mock TokenRepository repository;

    @Test
    void revokeRecordsStatusAtControlledTime() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T04:00:00Z"), ZoneOffset.UTC);
        TokenRevocationService service = new TokenRevocationService(repository, clock);

        when(repository.revokeIfActive("token-123", clock.instant(), "COMPROMISED"))
                .thenReturn(RevokeResult.REVOKED);

        RevokeResult result = service.revoke("token-123", "COMPROMISED");

        assertEquals(RevokeResult.REVOKED, result);
        verify(repository).revokeIfActive(
                "token-123", Instant.parse("2026-11-28T04:00:00Z"), "COMPROMISED");
    }

    @Test
    void repeatedRevokeDoesNotReactivateToken() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T04:00:00Z"), ZoneOffset.UTC);
        TokenRevocationService service = new TokenRevocationService(repository, clock);

        when(repository.revokeIfActive("token-123", clock.instant(), "COMPROMISED"))
                .thenReturn(RevokeResult.ALREADY_REVOKED);

        assertEquals(
                RevokeResult.ALREADY_REVOKED,
                service.revoke("token-123", "COMPROMISED"));
    }
}
```

Ví dụ tập trung vào thời gian xác định và contract idempotent. Cần bổ sung test quyền của actor, token không tồn tại, hai request đồng thời và việc validator từ chối token sau commit. Không dùng `Clock.systemUTC()` trực tiếp trong logic cần test thời gian; inject `Clock` giúp test expiry và propagation có thể lặp lại.

Một interface tối thiểu có thể là:

```java
import java.time.Instant;

public interface TokenRepository {
    RevokeResult revokeIfActive(String tokenId, Instant revokedAt, String reason);
}

public enum RevokeResult {
    REVOKED, ALREADY_REVOKED, NOT_FOUND
}

public final class TokenRevocationService {
    private final TokenRepository repository;
    private final java.time.Clock clock;

    public TokenRevocationService(TokenRepository repository, java.time.Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public RevokeResult revoke(String tokenId, String reason) {
        return repository.revokeIfActive(tokenId, clock.instant(), reason);
    }
}
```

Trong triển khai thật, repository nên cập nhật có điều kiện, ví dụ `UPDATE ... WHERE status = 'ACTIVE'`, để lần revoke thứ hai không ghi đè thời điểm/lý do đầu tiên. Service cũng phải kiểm tra authorization của actor và phát audit event sau khi trạng thái đã commit.

## 16. Integration test end-to-end

Một kịch bản end-to-end nên đi qua các thành phần thật trong môi trường cô lập:

1. Provision key hoặc credential test và cấp quyền cho workload test.
2. Gửi request hợp lệ và lưu request ID, key ID/token ID cùng kết quả.
3. Gọi revoke API bằng actor được phép.
4. Xác minh trạng thái đã commit tại nguồn có thẩm quyền.
5. Gửi request mới dùng credential cũ tới từng endpoint/node/region.
6. Xác minh tất cả bị từ chối trong SLA propagation.
7. Nếu có credential mới, xác minh workload hợp lệ dùng credential mới thành công.
8. Kiểm tra session, refresh token, connection pool, cache và batch job cũ.
9. Truy vấn audit log và đối chiếu event với request ID.
10. Kiểm tra backup/recovery hoặc khả năng đọc ciphertext nếu test liên quan encryption key.
11. Thu hồi credential test, dọn key test theo lifecycle và xác minh không còn tài nguyên ngoài ý muốn.

Integration test phải chạy với principal ít quyền và một principal được cấp quyền hợp lệ để phân biệt lỗi policy với lỗi cấu hình key. Không dùng production key, production credential hoặc dữ liệu khách hàng thật.

## 17. Mutation testing và regression testing

Mutation testing giúp xác minh test suite có phát hiện được lỗi trong logic thu hồi hay không. Trong môi trường test, thử các thay đổi:

- Bỏ kiểm tra `revokedAt` khi xác thực token.
- Bỏ cache invalidation sau khi commit revoke.
- Đổi default deny thành default allow khi introspection lỗi.
- Cho phép refresh token cũ được dùng lại.
- Chỉ xóa secret khỏi secret manager mà không revoke tại dịch vụ đích.
- Bỏ kiểm tra CRL/OCSP trong relying party.
- Cho phép encrypt bằng key version đã retired.
- Cho phép chuyển key state từ `DESTROYED` về `ACTIVE` bằng cập nhật metadata.
- Bỏ audit event hoặc ghi event trước khi transaction commit.

Test suite phải thất bại khi mutation làm credential cũ được chấp nhận hoặc làm mất bằng chứng audit. Regression suite nên giữ các ca từng gây sự cố và chạy lại khi thay đổi IAM, token validator, KMS/HSM policy, cache, certificate client hoặc rotation workflow.

## 18. Checklist triển khai Test key revocation

- Xác định loại credential/key và điểm thực thi có thẩm quyền.
- Phân biệt revoke, disable, expire, rotate và destroy trong test case.
- Kiểm tra credential cũ bị từ chối ở lần sử dụng tiếp theo theo SLA.
- Kiểm tra session, access token, refresh token và connection đang tồn tại.
- Kiểm tra service secret bị từ chối tại chính dịch vụ đích.
- Kiểm tra CRL/OCSP, cache và hành vi soft-fail/hard-fail của relying party.
- Kiểm tra DEK/KEK, wrapped key, key version và khả năng đọc dữ liệu cũ.
- Kiểm tra idempotency, concurrency, retry và state transition.
- Đo revocation latency trên mọi node, region, gateway và replica.
- Fault-inject lỗi token store, KMS/HSM, policy engine, cache và audit sink.
- Xác minh không có fallback sang credential cũ hoặc quyền rộng hơn.
- Xác minh audit có actor, resource, reason, timestamp và kết quả nhưng không chứa secret.
- Kiểm thử rotation/replacement và recovery trong môi trường cô lập.
- Chạy mutation và regression tests cho logic thu hồi.
- Lưu bằng chứng test, version policy, ID tài nguyên, request ID và kết quả propagation.

Test key revocation chỉ hoàn tất khi hệ thống chứng minh credential cũ không còn được chấp nhận tại mọi điểm thực thi theo mục tiêu thời gian, đồng thời workload hợp lệ có thể tiếp tục bằng credential mới hoặc quy trình recovery được phê duyệt. Với token và session, trọng tâm là validator và cache; với service secret, phải kiểm tra tại dịch vụ đích; với certificate, phải kiểm tra hành vi của relying party; với encryption key, phải bảo toàn metadata và dữ liệu phụ thuộc trong khi ngăn sử dụng khóa đã bị thu hồi. Audit và bằng chứng propagation là một phần của kết quả kiểm thử, không phải bước ghi nhận tùy chọn.

## Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Rev. 5: Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [RFC 7009: OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662: OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 5280: Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Java SE API: `java.time.Clock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)
