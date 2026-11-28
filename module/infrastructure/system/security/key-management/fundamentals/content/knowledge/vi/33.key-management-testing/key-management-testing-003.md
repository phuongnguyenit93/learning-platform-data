# Test key access denial

Trong hệ thống quản lý khóa, kiểm thử thành công một thao tác `Encrypt`, `Decrypt` hoặc `Sign` mới chỉ chứng minh đường đi hợp lệ hoạt động. Hệ thống còn phải chứng minh rằng principal không có quyền sẽ bị từ chối, khóa không đúng trạng thái không thể được sử dụng và thao tác bị từ chối không làm lộ key material hay tạo ra side effect ngoài dự kiến. **Test key access denial** là nhóm kiểm thử âm nhằm xác minh các ranh giới quyền truy cập khóa được thực thi đúng trong ứng dụng, IAM/policy engine và KMS/HSM.

Trong module Security Key Management Fundamentals, quyền truy cập cần gắn với toàn bộ vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, export, rotation, thu hồi và hủy. Một bài kiểm thử tốt phải xem xét đồng thời principal, key ID/version, hành động, môi trường, trạng thái khóa và điều kiện ngữ cảnh. Kiểm thử cũng cần xác nhận event từ chối được ghi nhận, log không chứa bí mật và các cache hoặc replica không tiếp tục chấp nhận quyền đã bị thu hồi.

## 1. Mục tiêu của kiểm thử từ chối truy cập khóa

Kiểm thử key access denial trả lời các câu hỏi:

- Principal không được cấp quyền có bị từ chối khi gọi thao tác với khóa không?
- Quyền `Decrypt` có bị tách biệt với `Encrypt`, `Sign`, `Export` và `Unwrap` không?
- Quyền trên một key ID có bị giới hạn khỏi key ID hoặc version khác không?
- Deny rule có được áp dụng khi key bị disable, revoked, compromised hoặc destroyed không?
- Điều kiện môi trường, tenant, region, workload identity và thời hạn có được kiểm tra không?
- Khi policy hoặc KMS/HSM từ chối, ứng dụng có ngăn dữ liệu và key material đi tiếp không?
- Từ chối có được audit mà không ghi password, token, key bytes hoặc plaintext không?
- Quyền vừa bị thu hồi có còn hiệu lực trong cache, session hoặc replica nào không?

Kết quả mong đợi không chỉ là một exception. Hệ thống phải từ chối đúng principal/action/resource, không thực hiện thao tác mật mã, không trả dữ liệu, không thay đổi trạng thái khóa và tạo bằng chứng audit phù hợp.

## 2. Phân biệt các lớp từ chối

Quyền truy cập có thể bị từ chối ở nhiều lớp. Kiểm thử cần biết lớp nào chịu trách nhiệm và event nào chứng minh quyết định đó.

| Lớp | Ví dụ | Điều cần xác minh |
|---|---|---|
| Ứng dụng | Người dùng không có role gọi endpoint giải mã | Ứng dụng từ chối trước khi gọi KMS; không trả plaintext |
| IAM/RBAC/ABAC | Workload thiếu action `kms:Decrypt` hoặc không thỏa condition | Policy engine trả deny; không có thao tác thành công ở KMS |
| KMS/HSM | Principal được xác thực nhưng key policy không cho phép thao tác | KMS/HSM từ chối và phát audit event tương ứng |
| Key state | Khóa bị disabled, pending deletion hoặc không còn hoạt động | Thao tác không được thực hiện theo semantics của dịch vụ |
| Provider/API | Provider không hỗ trợ operation hoặc key usage | Lỗi được phân loại đúng, không bị coi nhầm là authorization success |
| Context | Sai tenant, region, purpose hoặc environment | Request bị từ chối dù principal có quyền ở context khác |

Không gộp mọi lỗi thành `AccessDenied`. Ví dụ, `InvalidCiphertext`, `BadPadding`, lỗi network và `AccessDenied` có nguyên nhân khác nhau. Test cần phân biệt lỗi xác thực quyền với lỗi dữ liệu hoặc lỗi hạ tầng, đồng thời đảm bảo thông tin trả về cho client không tiết lộ chi tiết nhạy cảm.

## 3. Xây dựng ma trận principal, action và key

Trước khi viết test, hãy lập ma trận quyền mong đợi. Ma trận cần bao gồm cả quyền được phép và quyền bị từ chối để kiểm thử không vô tình làm hỏng chức năng hợp lệ.

| Principal | Encrypt | Decrypt | Sign | Export plaintext | Export wrapped |
|---|---:|---:|---:|---:|---:|
| `billing-writer` | Allow trên DEK billing | Deny | Deny | Deny | Deny |
| `billing-reader` | Deny | Allow trên DEK billing | Deny | Deny | Deny |
| `signing-service` | Deny | Deny | Allow trên signing key | Deny | Deny |
| `key-migration-job` | Deny | Deny mặc định | Deny | Deny | Allow có điều kiện trên key được duyệt |
| `unknown-workload` | Deny | Deny | Deny | Deny | Deny |

Ma trận trên chỉ là ví dụ. Quyền thực tế phải được suy ra từ policy đã phê duyệt. Một principal có quyền decrypt không tự động được quyền export; một key operator có quyền xem metadata cũng không tự động được quyền dùng khóa để ký hoặc giải mã.

Nên kiểm tra cả các trục sau:

- **Principal:** user, service account, workload identity, administrator, unknown identity.
- **Action:** encrypt, decrypt, sign, verify, wrap, unwrap, export, import, rotate, disable, destroy.
- **Resource:** key ID, key version, alias, tenant hoặc key classification.
- **Key state:** active, disabled, decrypt-only, scheduled for deletion, compromised, destroyed.
- **Context:** environment, region, network, time, request purpose, ticket/approval.
- **Decision:** allow, explicit deny, implicit deny, expired permission hoặc policy evaluation failure.

## 4. Kiểm thử default deny và least privilege

Default deny có nghĩa là request không có rule cho phép rõ ràng sẽ bị từ chối. Đây là trường hợp quan trọng khi có key mới, principal mới hoặc action mới được thêm vào hệ thống.

Các test cần có:

1. Principal chưa được cấp policy không thể gọi bất kỳ thao tác nhạy cảm nào.
2. Principal chỉ có `Encrypt` không thể gọi `Decrypt`.
3. Principal chỉ có `Decrypt` không thể gọi `ExportKey` hoặc `UnwrapKey` nếu policy không cấp.
4. Quyền trên `key-A` không cho phép thao tác với `key-B`.
5. Quyền trên version hiện tại không tự động mở rộng sang version mới nếu policy yêu cầu cấp riêng.
6. Policy thiếu condition bắt buộc phải deny.
7. Policy không đọc được hoặc evaluation gặp lỗi phải tuân theo fail-closed đối với thao tác nhạy cảm.

Kiểm thử cần xác minh không có wildcard ngoài ý muốn như `key/*` hoặc `kms:*` trong policy production. Nếu hệ thống dùng policy inheritance, phải kiểm tra quyền kế thừa từ organization, project, folder, account, group và resource policy.

## 5. Kiểm thử explicit deny và policy precedence

Một policy engine có thể hỗ trợ allow rule, deny rule và inheritance. Explicit deny thường phải thắng allow, nhưng semantics phụ thuộc hệ thống IAM. Hãy kiểm thử đúng quy tắc của nền tảng.

Ví dụ các tình huống:

| Policy condition | Allow rule | Deny rule | Kết quả mong đợi |
|---|---|---|---|
| Principal có quyền decrypt | Có | Không | Allow nếu các điều kiện khác hợp lệ |
| Principal có quyền decrypt | Có | Có explicit deny | Deny |
| Principal không có rule | Không | Không | Deny theo default deny |
| Workload ở sai environment | Có | Condition không thỏa | Deny |
| Permission đã hết hạn | Có | Expired | Deny |
| Policy evaluation không xác định | Không rõ | Không rõ | Fail-closed theo chính sách |

Không chỉ test policy document bằng cách đọc nội dung. Cần gửi request thực tế qua policy engine hoặc KMS/HSM trong môi trường test để xác nhận enforcement thực sự giống kỳ vọng.

## 6. Kiểm thử key state và lifecycle

Quyền đúng không đồng nghĩa khóa luôn có thể được sử dụng. Key state có thể làm thao tác bị từ chối hoặc giới hạn action.

| Trạng thái khóa | Test cần thực hiện | Kết quả mong đợi |
|---|---|---|
| Active | Principal không có quyền gọi encrypt/decrypt | Deny do authorization |
| Disabled | Principal có quyền nhưng khóa bị disable | Không thực hiện crypto operation |
| Decrypt-only | Gọi encrypt bằng khóa chỉ cho phép decrypt | Deny; decrypt hợp lệ có thể vẫn được phép |
| Scheduled for deletion | Gọi thao tác theo semantics của KMS trong giai đoạn chờ | Kết quả đúng theo state machine dịch vụ |
| Compromised/revoked | Gọi thao tác mới theo policy ứng phó | Deny hoặc chỉ cho phép quy trình recovery đặc biệt được phê duyệt |
| Destroyed | Gọi bất kỳ thao tác nào cần key material | Không thể sử dụng khóa đã hủy |

Không giả định tất cả KMS/HSM có cùng state machine. Một số dịch vụ có trạng thái `PendingDeletion`, một số dùng `Disabled` hoặc `Deactivated`; một số hỗ trợ decrypt-only thông qua policy riêng thay vì trạng thái gốc. Test phải bám theo semantics của dịch vụ đang dùng.

Đối với khóa cũ còn cần giải mã dữ liệu, test phải xác minh quyền decrypt vẫn hoạt động trong khi encrypt mới bị từ chối. Ngược lại, nếu khóa bị compromise và chính sách yêu cầu chặn hoàn toàn, không được để đường decrypt thông thường tiếp tục hoạt động chỉ vì dữ liệu cũ còn phụ thuộc.

## 7. Kiểm thử ranh giới key ID, version và tenant

Một lỗi phổ biến là kiểm tra quyền ở cấp alias hoặc logical key nhưng không ràng buộc version thực tế được dùng. Điều này có thể khiến principal có quyền trên một khóa vô tình truy cập khóa khác.

Các ca kiểm thử:

- Principal có quyền với `customer-key` không thể dùng `payroll-key`.
- Quyền của tenant A không thể dùng để truy cập key thuộc tenant B.
- Alias được đổi sang version mới không làm quyền cũ tự mở rộng nếu version mới có policy khác.
- Ciphertext chứa key ID không hợp lệ hoặc key ID thuộc tenant khác phải bị từ chối.
- Request sửa key ID trong metadata/AAD phải thất bại hoặc bị policy từ chối.
- Key version đã retired/disabled phải tuân theo chính sách đọc dữ liệu cũ.
- Principal không được dùng wildcard hoặc alias injection để vượt qua resource boundary.

Nên dùng key ID/version cụ thể trong test fixture. Không chỉ kiểm tra chuỗi alias do client gửi; cần xác minh server ánh xạ alias sang resource đúng và áp dụng authorization trên resource thực tế.

## 8. Kiểm thử context và điều kiện ABAC

ABAC có thể quyết định quyền dựa trên thuộc tính principal, resource và request. Test nên thay đổi từng thuộc tính để xác minh condition được áp dụng chính xác.

Ví dụ:

| Thuộc tính | Giá trị hợp lệ | Giá trị cần deny |
|---|---|---|
| Environment | `production` cho workload production được duyệt | `development` hoặc environment không khớp |
| Region | Region được policy cho phép | Region ngoài danh sách |
| Tenant | Tenant sở hữu key | Tenant khác |
| Purpose | `customer-data-decrypt` đã khai báo | Purpose không xác định hoặc không liên quan |
| Approval | Ticket/approval còn hiệu lực | Thiếu, hết hạn hoặc bị thu hồi |
| Network/workload identity | Workload identity đã xác thực | Identity giả, sai namespace hoặc nguồn không tin cậy |
| Time window | Trong thời hạn cấp quyền | Trước thời điểm bắt đầu hoặc sau expiry |

Kiểm thử boundary time, timezone, null/missing attribute và giá trị sai định dạng. Không coi một thuộc tính bị thiếu là hợp lệ nếu policy yêu cầu nó. Với context lấy từ request body, không tin giá trị do client tự khai; phải lấy hoặc xác minh từ identity provider, gateway hay nguồn có thẩm quyền.

## 9. Kiểm thử không có side effect khi bị từ chối

Một request bị deny phải dừng trước khi thực hiện thao tác không được phép. Ngoài mã lỗi, cần kiểm tra:

- KMS/HSM không nhận request crypto operation nếu ứng dụng đã deny ở lớp authorization.
- Không có plaintext, ciphertext mới hoặc chữ ký được trả về.
- Không tạo, rotate, disable hoặc export khóa ngoài ý muốn.
- Không thay đổi key metadata, alias, version, usage counter hoặc migration checkpoint.
- Không ghi một phần dữ liệu xuống database/object storage.
- Không để transaction ở trạng thái dở dang hoặc job tiếp tục chạy sau khi request bị từ chối.
- Không retry tự động bằng principal khác hoặc credential rộng quyền hơn.

Với thao tác nhiều bước, ví dụ unwrap DEK rồi decrypt payload, test phải xác minh nếu bước authorization bị deny thì các bước sau không được thực hiện. Nếu lỗi xảy ra sau một side effect không thể đảo ngược, ứng dụng cần có transaction/state machine và audit để xác định trạng thái cuối.

## 10. Kiểm thử thông tin lỗi và chống rò rỉ dữ liệu

Thông báo lỗi cho client nên đủ để xử lý nhưng không tiết lộ chi tiết có thể hỗ trợ attacker dò tìm khóa hoặc policy.

Ví dụ, client có thể nhận lỗi chung `403 Forbidden` hoặc mã nghiệp vụ `KEY_OPERATION_NOT_ALLOWED`. Nội bộ audit có thể ghi reason cụ thể như `PRINCIPAL_NOT_AUTHORIZED`, `KEY_DISABLED` hoặc `CONDITION_NOT_MET` theo quyền truy cập log.

Test cần xác minh response không chứa:

- Key material, private key encoding hoặc secret bytes.
- Password, PIN, API token, access token hoặc credential.
- Plaintext hoặc một phần dữ liệu đã giải mã.
- Policy document đầy đủ, tên nhóm nội bộ hoặc thông tin IAM nhạy cảm không cần thiết.
- Stack trace, đường dẫn file, thông tin HSM slot hoặc cấu hình hạ tầng nhạy cảm.

Không nên dùng cùng một thông báo lỗi chi tiết cho client và audit. Client response có thể được chuẩn hóa, trong khi audit record nội bộ giữ reason code có kiểm soát để hỗ trợ điều tra.

## 11. Kiểm thử audit event khi access bị deny

Từ chối truy cập cũng là một sự kiện bảo mật cần quan sát. Test phải xác minh event được ghi ở đúng lớp:

- Nếu ứng dụng từ chối trước khi gọi KMS, application/policy audit phải ghi `DENY` và KMS không có crypto request tương ứng.
- Nếu request tới KMS/HSM và bị key policy từ chối, audit tại KMS/HSM phải ghi principal, key ID, action, decision và reason/result theo khả năng dịch vụ.
- Nếu policy engine lỗi hoặc timeout, hệ thống cần ghi nhận lỗi quyết định và không mặc định cho phép thao tác.
- Nếu audit sink tạm thời không khả dụng, hành vi phải theo chính sách đã định; thao tác nhạy cảm có thể phải fail-closed.

Audit event cần có event ID, timestamp, principal, key ID/version, action, decision, outcome, request/correlation ID và reason code. Không ghi giá trị bí mật. Kiểm thử cũng cần xác minh event không bị ghi trùng vô hạn khi retry và có thể tương quan với request gốc.

## 12. Ví dụ Java: unit test xác minh KMS không được gọi khi bị deny

Ví dụ dùng JUnit 5 và Mockito để kiểm tra authorization xảy ra trước crypto operation. Đây là kiểm thử ở lớp ứng dụng; nó không thay thế integration test với IAM/KMS/HSM thật.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class KeyAccessServiceTest {
    @Mock KeyAuthorizer authorizer;
    @Mock KmsClient kmsClient;

    @Test
    void deniesDecryptBeforeCallingKms() {
        Principal principal = new Principal("workload:reporting-job");
        KeyRef key = new KeyRef("customer-data-key", "v4");

        when(authorizer.isAllowed(principal, key, KeyAction.DECRYPT))
                .thenReturn(false);

        KeyAccessService service = new KeyAccessService(authorizer, kmsClient);

        assertThrows(
                KeyAccessDeniedException.class,
                () -> service.decrypt(principal, key, new byte[] {1, 2, 3}));

        verify(kmsClient, never()).decrypt(eq(key), any(byte[].class));
    }
}
```

Các kiểu `Principal`, `KeyRef`, `KeyAction`, `KeyAuthorizer`, `KmsClient`, `KeyAccessService` và `KeyAccessDeniedException` là domain type minh họa cần được định nghĩa theo ứng dụng. Dùng matcher `eq(key)` và `any(byte[].class)` để xác minh không có lời gọi `decrypt` với key đó mà không phụ thuộc vào identity của mảng byte.

Một service đơn giản có thể triển khai theo nguyên tắc:

```java
public final class KeyAccessService {
    private final KeyAuthorizer authorizer;
    private final KmsClient kmsClient;

    public KeyAccessService(KeyAuthorizer authorizer, KmsClient kmsClient) {
        this.authorizer = authorizer;
        this.kmsClient = kmsClient;
    }

    public byte[] decrypt(Principal principal, KeyRef key, byte[] ciphertext) {
        if (!authorizer.isAllowed(principal, key, KeyAction.DECRYPT)) {
            throw new KeyAccessDeniedException("KEY_OPERATION_NOT_ALLOWED");
        }
        return kmsClient.decrypt(key, ciphertext);
    }
}
```

Trong production, authorization phải lấy principal từ identity đã xác thực, không nhận một chuỗi principal tùy ý do client gửi. `KeyAuthorizer` cần đánh giá cả resource, action và context; KMS/HSM vẫn cần policy độc lập để bảo vệ trường hợp ứng dụng bị bypass hoặc bị xâm nhập.

## 13. Integration test với KMS/HSM hoặc provider

Unit test chứng minh code ứng dụng gọi đúng thứ tự, nhưng không chứng minh policy được triển khai đúng trên KMS/HSM. Integration test cần dùng một key test và principal test trong account/project/partition cô lập.

Một kịch bản integration test:

1. Tạo key test với key ID và version xác định.
2. Tạo principal test không có quyền `Decrypt` trên key đó.
3. Xác thực principal bằng workload identity hoặc credential test.
4. Gọi API KMS/HSM `Decrypt` trực tiếp, bỏ qua lớp ứng dụng.
5. Xác minh dịch vụ trả lỗi authorization/state tương ứng.
6. Truy vấn audit source và xác minh event `DENY` có principal, key ID, action và timestamp đúng.
7. Xác minh không có plaintext hoặc crypto result được trả về.
8. Cấp đúng quyền trong một test riêng và xác minh thao tác hợp lệ hoạt động, nhằm chứng minh test deny không phải do cấu hình key hỏng.
9. Thu hồi quyền và xác minh request tiếp theo bị từ chối trong giới hạn propagation đã định.

Không dùng khóa production hoặc dữ liệu khách hàng trong test deny. Dùng key test, ciphertext test và principal có vòng đời riêng; sau test, thu hồi credential và dọn tài nguyên theo quy trình. Nếu KMS/HSM có chi phí hoặc giới hạn API, kiểm soát retry để test không tạo tải không cần thiết.

## 14. Kiểm thử cache, session và propagation sau khi thu hồi quyền

Một policy vừa bị thu hồi có thể chưa có hiệu lực tức thời ở mọi nơi. Ứng dụng có thể cache quyết định allow, gateway cache token introspection hoặc worker giữ session cũ.

Test nên xác minh:

- Sau khi revoke role/permission, request mới bị deny trong thời gian propagation mục tiêu.
- Cache invalidation được phát và xử lý thành công.
- Replica hoặc region không tiếp tục dùng policy cũ quá TTL đã quy định.
- Token/session được cấp trước khi revoke có bị vô hiệu hóa theo chính sách không.
- Workload restart không khôi phục credential hoặc policy cũ từ local cache.
- Nếu policy service không khả dụng, thao tác nhạy cảm không chuyển sang allow theo mặc định.

Đo **revocation latency** từ thời điểm policy có hiệu lực tại nguồn đến thời điểm tất cả điểm thực thi từ chối request. Đừng chỉ kiểm tra một instance hoặc một request ngay sau khi cập nhật policy; cần test trên các node, region và đường truy cập khác nhau.

## 15. Kiểm thử race condition và request đồng thời

Authorization có thể thay đổi trong lúc request đang xử lý. Ví dụ, principal được cấp quyền lúc bắt đầu nhưng bị revoke trước khi KMS thực hiện thao tác. Chính sách cần xác định điểm tuyến tính hóa: quyết định allow được xem là có hiệu lực tại thời điểm nào và một request đã bắt đầu có được hoàn tất không.

Các tình huống cần kiểm tra:

- Hai request cùng lúc khi permission bị revoke.
- Rotation hoặc disable key xảy ra giữa authorization và crypto operation.
- Alias đổi version khi request đang xử lý.
- Policy cache được refresh trong lúc nhiều worker đang dùng.
- Request retry sau timeout khi kết quả lần đầu không rõ.

Tùy kiến trúc, có thể cần short-lived authorization decision, fencing/version token, policy revision hoặc để KMS/HSM đánh giá lại quyền tại thời điểm thực hiện. Không giả định một lần kiểm tra quyền ở đầu request bảo đảm quyền vẫn hợp lệ ở mọi bước sau.

## 16. Mutation testing và regression testing cho policy

Mutation testing giúp đánh giá test suite có phát hiện được lỗi policy hay không. Có thể tạo các biến thể policy trong môi trường test:

- Xóa điều kiện `tenantId`.
- Đổi `Deny` thành `Allow`.
- Mở rộng resource từ một key ID sang wildcard.
- Thêm action `ExportKey` vào role chỉ cần decrypt.
- Bỏ điều kiện environment hoặc approval.
- Đổi default deny thành default allow.

Test suite phải thất bại với các mutation làm mở rộng quyền trái phép. Với policy-as-code, lưu policy và test cùng version control, yêu cầu review độc lập và chạy test mỗi khi policy thay đổi.

Regression suite nên giữ các trường hợp deny đã từng gây incident. Mỗi lần thay đổi role, key policy, provider, KMS configuration hoặc cách resolve key ID đều cần chạy lại các test liên quan.

## 17. Ma trận kiểm thử tối thiểu

| Nhóm | Ca kiểm thử | Kết quả cần xác nhận |
|---|---|---|
| Identity | Principal không xác thực | Deny trước khi truy cập khóa |
| Least privilege | Có encrypt nhưng không có decrypt | Decrypt bị deny |
| Resource boundary | Có quyền key A, gọi key B | Deny |
| Action boundary | Có decrypt, gọi export plaintext | Deny |
| Explicit deny | Allow và explicit deny cùng khớp | Theo precedence, thường là deny |
| Context | Sai tenant/environment/region | Deny |
| Key state | Key disabled hoặc destroyed | Crypto operation không thành công |
| Version | Alias trỏ sang version không được cấp quyền | Deny theo resource/version policy |
| Side effect | Request bị deny | Không có crypto result hay metadata mutation |
| Audit | Access bị deny | Có event deny, không có bí mật trong log |
| Error handling | Policy/KMS unavailable | Fail-closed theo chính sách |
| Propagation | Permission vừa bị revoke | Request bị từ chối trong SLA propagation |
| Concurrency | Revoke chạy đồng thời với decrypt | Hành vi đúng theo điểm hiệu lực được định nghĩa |
| Regression | Policy mutation mở rộng quyền | Test suite phát hiện và thất bại |

## 18. Checklist triển khai Test key access denial

- Xây dựng ma trận principal × action × key ID/version × context.
- Kiểm tra default deny và explicit deny precedence.
- Kiểm tra least privilege giữa encrypt, decrypt, sign, wrap, unwrap và export.
- Kiểm tra key state: active, disabled, decrypt-only, pending deletion, compromised và destroyed.
- Kiểm tra tenant, environment, region, purpose, approval và thời hạn.
- Xác minh deny ở ứng dụng xảy ra trước khi gọi KMS/HSM khi phù hợp.
- Kiểm thử trực tiếp policy KMS/HSM để tránh chỉ dựa vào unit test.
- Xác minh không có plaintext, key material, chữ ký hoặc side effect khi bị deny.
- Kiểm tra response client không làm lộ policy, key existence hoặc thông tin hạ tầng nhạy cảm.
- Kiểm tra audit event deny có đủ context nhưng không chứa secret.
- Kiểm tra cache, session, replica và propagation sau khi revoke quyền.
- Kiểm tra race condition giữa authorization, key state change và crypto operation.
- Dùng key/principal/ciphertext test trong môi trường cô lập.
- Chạy regression và policy mutation test khi thay đổi IAM hoặc key policy.
- Lưu bằng chứng test, policy version, key ID, principal, timestamp và kết quả.

Test key access denial là kiểm thử bắt buộc cho ranh giới bảo vệ khóa. Một hệ thống chỉ đáng tin khi quyền được cấp đúng cho principal và resource, còn mọi request ngoài phạm vi đều bị từ chối nhất quán. Kết quả kiểm thử cần chứng minh cả quyết định deny, việc không có thao tác mật mã hoặc side effect, audit đầy đủ và khả năng lan truyền thu hồi quyền tới mọi workload. Kết hợp unit test, integration test KMS/HSM, kiểm thử context, concurrency và regression policy sẽ giúp phát hiện sớm lỗi phân quyền trước khi chúng trở thành sự cố lộ khóa hoặc dữ liệu.

## Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Rev. 5: Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-53 Rev. 5: Security and Privacy Controls for Information Systems and Organizations](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Java SE API: `java.security.Provider`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Provider.html)
