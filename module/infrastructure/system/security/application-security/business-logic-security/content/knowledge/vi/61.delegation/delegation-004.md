# Delegation end time — Thời điểm kết thúc quyền ủy nhiệm

## 1. Hết thời gian ủy nhiệm phải thực sự hết quyền

Trưởng bộ phận A ủy nhiệm cho B duyệt khoản chi trong phạm vi phòng mua hàng, tối đa 50 triệu VND, từ 08:00 đến 17:00. Lúc 16:59, B mở màn hình duyệt. Lúc 17:01, B gửi yêu cầu xác nhận. Phiên đăng nhập của B vẫn còn, giao diện vẫn mở và token chưa hết hạn. B có được duyệt thay A không?

Câu trả lời phải dựa vào thời điểm thực hiện quyền theo hợp đồng nghiệp vụ, không dựa vào việc người dùng đã mở màn hình trước hạn. **Delegation end time** là thời điểm kết thúc khả năng dùng một quyền ủy nhiệm để tạo quyết định hoặc tác dụng nghiệp vụ mới.

Nếu chỉ ẩn nút sau 17:00 hoặc chờ tác vụ nền đổi trạng thái, B có thể tiếp tục gọi API, phát lại một lệnh, dùng token cũ hoặc để công việc trong hàng đợi chạy sau hạn. Đây là lỗi logic nghiệp vụ: danh tính vẫn hợp lệ nhưng căn cứ được hành động thay người khác đã không còn.

Bài học tập trung vào cách gắn thời hạn ủy nhiệm với quyền theo đối tượng, state machine, nguồn thời gian, giao dịch, token, idempotency và kiểm thử các thứ tự sự kiện đối kháng. Các số tiền và thời gian là ví dụ minh họa, không phải quy định cho mọi tổ chức.

## 2. Phân biệt danh tính, quyền trực tiếp và quyền được ủy nhiệm

Một hành động dùng ủy nhiệm có ít nhất ba thành phần:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Người thực hiện thực tế, actor | B | Danh tính được xác thực đang gửi yêu cầu |
| Người ủy nhiệm, delegator | A | Chủ thể cung cấp căn cứ thẩm quyền |
| Bản cấp quyền, delegation grant | D1 | Giới hạn hành động, đối tượng, thời gian và điều kiện |

B không trở thành A. Audit phải giữ cả actor B và delegator A, thay vì ghi mọi hoạt động thành “A đã duyệt”. Một trường `actingAs=A` do client gửi không chứng minh được quan hệ ủy nhiệm.

Server cần tìm một grant phù hợp, xác nhận B là đúng người nhận, grant thuộc đúng tenant và thao tác nằm trong phạm vi được cấp. Nếu B có quyền trực tiếp độc lập, quyền đó là một căn cứ khác. D1 hết hạn không tự khóa tài khoản B hoặc xóa mọi quyền trực tiếp của B.

Ngược lại, B không được dùng quyền trực tiếp để tạo dấu vết giả rằng A đã thực hiện hay chấp thuận thao tác. Nếu hệ thống cho chuyển sang đường quyền trực tiếp, quyết định và audit phải ghi đúng căn cứ, không âm thầm giữ nhãn “thay mặt A”.

### 2.1. Mô hình grant tham khảo

```text
delegationId, revision
tenantId
delegatorId, delegateId
allowedActions
resourceScope
amountLimit, currency nếu có
startsAt, endsAt
administrativeState
parentDelegationId nếu cho phép ủy nhiệm tiếp
mayRedelegate
issuedAt, issuedBy, approvalReference
```

`endsAt` không được coi là một trường trang trí. Nó phải tham gia quyết định tại nơi có thể tạo tác dụng nghiệp vụ. Phạm vi, hạn mức và thời gian là một bộ điều kiện của cùng grant, không được chọn mỗi phần có lợi từ những grant không liên quan.

Ví dụ D1 cho phòng mua hàng tối đa 50 triệu, còn D2 cho phòng kỹ thuật tối đa 200 triệu. B không được ghép phạm vi phòng mua hàng của D1 với hạn mức 200 triệu của D2 để duyệt khoản chi 100 triệu. Một hành động cần được bao phủ trọn vẹn bởi căn cứ hợp lệ, trừ khi hệ thống có quy tắc kết hợp được thiết kế rõ ràng.

## 3. Định nghĩa ranh giới kết thúc không nhập nhằng

### 3.1. Dùng khoảng nửa mở

Một quy ước phù hợp là:

```text
[startsAt, endsAt)

Grant hợp lệ về thời gian khi:
    startsAt <= authorizationDecisionAt
    và authorizationDecisionAt < endsAt
```

Bắt đầu được tính vào khoảng; kết thúc không được tính. Tại đúng `endsAt`, không được tạo một quyết định mới dựa trên grant đó.

| Thời điểm chốt quyền | Kết quả về thời gian |
| --- | --- |
| Ngay trước `startsAt` | Chưa có hiệu lực |
| Đúng `startsAt` | Có hiệu lực |
| Ngay trước `endsAt` | Còn hiệu lực |
| Đúng `endsAt` | Hết hiệu lực |
| Sau `endsAt` | Hết hiệu lực |

Độ nhỏ của “ngay trước” phải phù hợp độ chính xác hệ thống hỗ trợ. Nếu database lưu micro giây, kiểm thử tích hợp không nên giả định mọi khác biệt nano giây của Java đều được giữ nguyên sau lưu trữ.

### 3.2. Ngày kết thúc khác thời điểm kết thúc

Nếu giao diện cho chọn “ủy nhiệm đến hết ngày 15/12 theo múi giờ văn phòng”, backend cần chuyển thành mốc loại trừ là đầu ngày 16/12 trong múi giờ đó, rồi lưu mốc tuyệt đối dùng để so sánh. Không tạo mốc bằng cách đoán `23:59:59.999` là giá trị cuối ngày.

Múi giờ nghiệp vụ phải được xác định từ cấu hình tin cậy. Không để B đổi múi giờ trình duyệt hoặc offset trong request để kéo dài quyền. Với vùng có chuyển đổi giờ mùa hè, ngày lịch có thể không dài đúng 24 giờ; việc chuyển ngày cần theo quy tắc vùng, không luôn cộng một số giây cố định.

Nên giữ cả thông tin lịch và múi giờ đã được phê duyệt để giải thích quyết định. Quyền thực thi dùng mốc tuyệt đối nhất quán; thay múi giờ mặc định của JVM không được làm D1 có thêm thời gian.

### 3.3. Hết hạn và thu hồi là hai nguyên nhân khác nhau

Hết hạn là đạt `endsAt`. Thu hồi là quyết định làm grant không còn được dùng trước hạn hoặc theo một điều kiện quản trị. Grant chưa tới `endsAt` vẫn phải bị từ chối nếu đã bị thu hồi.

Nếu thu hồi có mốc hiệu lực được lập lịch, phải định nghĩa chính xác cách áp dụng. Với thu hồi tức thời, thứ tự giữa thao tác thu hồi và thao tác sử dụng quyền cần được giải quyết tại nguồn có thẩm quyền. Không suy ra grant còn hợp lệ chỉ vì token chứa bản sao dữ liệu cũ.

## 4. Các bất biến của quyền ủy nhiệm có thời hạn

### 4.1. Bất biến về thẩm quyền

```text
Người cấp có quyền ủy nhiệm và có thẩm quyền trong phạm vi được cấp.
Người nhận là đúng actor được phép sử dụng grant.
Grant và đối tượng nghiệp vụ thuộc đúng tenant/phạm vi được phép.

Không cấp vượt quyền, phạm vi, hạn mức hoặc thời gian của căn cứ cha.
Quyền ủy nhiệm tiếp phải được cho phép rõ ràng.

Một quyết định mới chỉ dùng grant khi:
    trạng thái quản trị cho phép;
    startsAt <= authorizationDecisionAt < effectiveEndsAt;
    các điều kiện nghiệp vụ và quyền đối tượng còn đáp ứng.
```

Một mô hình phổ biến là quyền được ủy nhiệm không vượt quyền hiện hành mà người ủy nhiệm được phép chuyển giao. Khi A mất vai trò hoặc rời tenant, các grant phụ thuộc phải được xử lý theo chính sách đã định nghĩa. Một bản cấp quyền không nên vô tình bảo tồn đặc quyền mà A đã mất.

Một số nghiệp vụ có thể cấp một ủy quyền độc lập đã được tổ chức phê duyệt, với cách xử lý khác khi A đổi vai trò. Nếu có mô hình này, phải biểu diễn và quản trị như một loại thẩm quyền rõ ràng; không để nó phát sinh ngầm từ việc hệ thống quên kiểm tra quan hệ gốc.

### 4.2. Bất biến về kết thúc và tác dụng

```text
Token, phiên đăng nhập và cache không được kéo dài effectiveEndsAt.

Chấp thuận chưa được chốt trước hạn không trở thành hợp lệ
chỉ vì người dùng đã mở màn hình hoặc tạo bản nháp trước đó.

Retry không tạo thêm tác dụng của một operation đã hoàn tất.
Gia hạn không âm thầm viết lại căn cứ của quyết định lịch sử.

Audit giữ actor, delegator, grant/revision, thời điểm chốt quyền
và nội dung nghiệp vụ đã được chấp thuận.
```

Thời gian hợp lệ là điều kiện cần, không đủ. B còn trong hạn nhưng không được duyệt khoản chi ngoài phạm vi, vượt hạn mức hoặc tự duyệt hồ sơ do chính mình tạo nếu quy tắc độc lập cấm điều đó. Ủy nhiệm không phải cách bỏ qua phân tách nhiệm vụ.

## 5. Chọn điểm quyết định: nhận yêu cầu, chốt duyệt hay thực thi?

### 5.1. Không có một timestamp dùng được cho mọi bước

Một thao tác có thể đi qua nhiều mốc:

```text
clientSentAt -> receivedAt -> queuedAt -> authorizationDecisionAt
             -> committedAt -> dispatchedAt -> externalEffectAt
```

`clientSentAt` do client khai không phải bằng chứng quyền còn hạn. `queuedAt` cho biết lúc vào hàng đợi, chưa tự nói rằng một chấp thuận nghiệp vụ đã được chốt. `committedAt` và thời điểm tạo tác dụng ở dịch vụ ngoài cũng không tự đồng nhất với điểm kiểm tra quyền.

Phải định nghĩa quyền ủy nhiệm được dùng để làm gì: tạo một chấp thuận cuối có giá trị bền vững, hay thực hiện một thao tác chỉ khi quyền còn hiện hành ngay lúc chạy.

### 5.2. Hợp đồng minh họa: chốt duyệt sau khi giành khóa

Trong ví dụ, B được phép tạo chấp thuận cuối nếu quyền còn hợp lệ tại `authorizationDecisionAt`, được lấy sau khi giành các khóa cần thiết. Chấp thuận, nội dung hồ sơ và audit được lưu trong cùng giao dịch.

```text
16:59:59.700  Request đến API.
16:59:59.750  Chờ khóa hồ sơ.
17:00:00.020  Giành được các khóa cần thiết.
17:00:00.021  Lấy authorizationDecisionAt.
17:00:00.025  Kiểm tra D1 đã hết hạn -> không tạo chấp thuận.
```

Kiểm tra D1 ở đầu request rồi dùng lại kết quả sau khi chờ khóa sẽ vi phạm hợp đồng này. Không được biến thời điểm bấm nút thành thời điểm chốt bằng một trường gửi từ trình duyệt.

Nếu chốt quyền lúc 16:59:59.990 rồi commit lúc 17:00:00.010, kết quả có thể hợp lệ theo hợp đồng decision-time vừa nêu. Nếu nghiệp vụ yêu cầu tác dụng thực tế phải xảy ra trước 17:00, cần cơ chế kiểm soát tại điểm tác dụng tương ứng. Một lần kiểm tra trước commit không chứng minh commit hoặc dịch vụ bên ngoài đã hoàn thành trước hạn.

### 5.3. Chấp thuận đã chốt khác một công việc chưa được thực hiện

Một chấp thuận cuối được tạo hợp lệ trước hạn có thể tiếp tục là bằng chứng sau khi D1 hết hạn. Hết hạn không mặc định xóa lịch sử hoặc đảo ngược mọi quyết định đã có. Chính sách có thể yêu cầu xét lại trong một số trường hợp, nhưng đó là quy tắc riêng.

Ngược lại, một tác vụ chỉ mang thông tin “B yêu cầu làm sau” chưa chắc đã được cấp quyền hoàn tất trước hạn. Nếu worker là nơi chốt quyền, worker phải kiểm tra D1 tại điểm chốt của nó. Không tin cờ `authorized=true` từ API trước đó để chạy vô thời hạn.

Hai trường hợp cần được biểu diễn khác nhau: sự kiện về một quyết định đã được chốt và lệnh yêu cầu tạo quyết định mới. Việc đặt cả hai vào cùng một hàng đợi không làm chúng có cùng ý nghĩa bảo mật.

## 6. Thực thi kiểm tra ở backend và trong giao dịch

### 6.1. Biểu diễn cửa sổ thời gian bằng Java

Ví dụ sau dùng record và `java.time`, chỉ mô hình hóa phần thời gian của một grant hữu hạn:

```java
import java.time.Instant;
import java.util.Objects;

public record DelegationWindow(Instant startsAt, Instant endsAt) {
    public DelegationWindow {
        Objects.requireNonNull(startsAt, "startsAt");
        Objects.requireNonNull(endsAt, "endsAt");
        if (!startsAt.isBefore(endsAt)) {
            throw new IllegalArgumentException("invalid delegation window");
        }
    }

    public boolean includes(Instant decisionAt) {
        Objects.requireNonNull(decisionAt, "decisionAt");
        return !decisionAt.isBefore(startsAt)
                && decisionAt.isBefore(endsAt);
    }
}
```

Một hàm `includes()` trả `true` chưa có nghĩa được phép duyệt. Vẫn phải kiểm tra actor, tenant, phạm vi đối tượng, hạn mức, trạng thái thu hồi, quan hệ cha và các bất biến nghiệp vụ khác.

Lấy thời gian đúng một lần cho một quyết định. Với unit test, có thể tiêm `Clock` để điều khiển mốc. Với một giao dịch dùng database làm nguồn thời gian có thẩm quyền, lấy timestamp từ database tại vị trí đã chọn, thay vì mỗi lớp lại gọi đồng hồ độc lập.

### 6.2. Phác thảo một thao tác phê duyệt

Mã sau là mã giả theo phong cách Java. Nó minh họa ranh giới bảo vệ; các repository và phương thức không thuộc một framework cụ thể.

```java
ApprovalResult approveAsDelegate(TrustedContext ctx, ApproveCommand command) {
    return transactions.execute(() -> {
        // Bao gồm kiểm tra tenant, actor và các căn cứ cha liên quan.
        AuthorityProof proof = authorities.lockDelegationProof(
                ctx.tenantId(), ctx.actorId(), command.delegationId());

        Payment payment = payments.lockOwned(
                ctx.tenantId(), command.paymentId());
        requireObjectAccess(ctx, payment);

        Operation operation = operations.lockOrCreate(
                ctx.tenantId(), command.idempotencyKey(), command.payloadHash());
        requireSameCanonicalRequest(operation, command);

        if (operation.hasFinalResult()) {
            requireCurrentResultAccess(ctx, operation);
            return operation.savedResult();
        }

        Instant decisionAt = authorityTime.nowForDecision();
        requireLiveDelegation(proof, ctx, payment, decisionAt);
        requireApprovableStateAndRevision(payment, command.objectRevision());
        requireSeparationOfDuties(ctx, proof, payment);

        Approval approval = approvals.append(
                ctx.actorId(), proof, payment, decisionAt);
        payment.applyApproval(approval);
        audit.appendDelegatedDecision(ctx, proof, payment, approval);
        outbox.appendApprovalEvent(approval.id());

        return operation.complete(approval.result());
    });
}
```

`TrustedContext` đến từ danh tính đã xác thực, không từ actor hoặc tenant mà client tự khai. `payloadHash` trong lệnh phải được backend tính hoặc kiểm chứng từ nội dung chuẩn hóa; không tin dấu băm do client gửi để bỏ qua đối chiếu nội dung.

Đối với một operation đã hoàn tất, việc trả lại kết quả không phải một lần dùng quyền duyệt mới. Triển khai cần cho phép phân biệt đường phát lại này: `lockDelegationProof` có thể tải căn cứ lịch sử nhưng không được buộc grant còn hạn chỉ để tìm operation cũ. Quyền xem kết quả hiện hành vẫn phải được kiểm tra; nếu không còn quyền xem thì không trả dữ liệu nhạy cảm và cũng không thực hiện tác dụng mới.

Mọi đường thu hồi, cấp lại và sử dụng quyền cần có thứ tự khóa nhất quán, chẳng hạn căn cứ quản trị, chuỗi grant từ gốc xuống, đối tượng nghiệp vụ rồi operation. Những khóa này phải có hiệu lực giữa các tiến trình. Mã giả chưa bao gồm đầy đủ retry giao dịch, tối ưu khóa hay mô hình nhiều dịch vụ.

### 6.3. Thu hồi đua với thao tác sử dụng quyền

Trong một ranh giới dữ liệu có thẩm quyền chung, có thể phối hợp để thao tác thu hồi và thao tác duyệt có thứ tự nhất quán. Nếu thu hồi đã thắng trước điểm kiểm tra, không được tạo chấp thuận bằng grant cũ. Nếu chấp thuận đã được chốt hợp lệ trước, việc thu hồi sau đó không tự xóa chấp thuận, trừ chính sách có quy tắc xét lại riêng.

Khóa grant không làm thời gian ngừng trôi. Sau khi đã giành các khóa cần thiết, vẫn phải lấy `authorizationDecisionAt` và so sánh với `endsAt`. Nếu nguồn thời gian là database, cần hiểu hàm thời gian đang dùng: có hệ quản trị trả thời gian đầu transaction cho một số hàm, nên một transaction chờ lâu có thể đọc lại mốc cũ thay vì thời điểm sau chờ khóa.

Trong hệ thống nhiều dịch vụ, khóa ở database của dịch vụ thanh toán không tự khóa trạng thái thu hồi ở dịch vụ danh tính. Cần một giao thức kiểm tra và tính nhất quán được định nghĩa, hoặc xác định rõ độ trễ thu hồi được chấp nhận. Không hứa thu hồi tức thời toàn hệ thống chỉ vì một dịch vụ đã commit `REVOKED`.

## 7. Token, phiên và cache không được gia hạn quyền ngầm

### 7.1. Phiên đăng nhập còn sống không làm grant còn sống

Token đăng nhập xác nhận B đang đăng nhập; grant xác định B được làm gì thay A trong khoảng nào. Hai vòng đời khác nhau. B có thể đăng nhập cả ngày nhưng chỉ được duyệt thay A trong một giờ.

Với token chuyên dùng cho ủy nhiệm, một giới hạn hợp lý là:

```text
delegatedTokenExpiresAt <= effectiveDelegationEndsAt
delegatedTokenExpiresAt <= sessionExpiresAt
delegatedTokenExpiresAt <= thời hạn tối đa của loại token
```

Nếu token thông thường có tuổi thọ dài hơn D1, backend vẫn phải kiểm tra grant tại nơi thực hiện hành động được ủy nhiệm. Không kéo dài D1 chỉ để làm thời hạn hai loại dữ liệu giống nhau.

### 7.2. Chữ ký token không chứng minh quyền hiện hành

Một token có chữ ký hợp lệ có thể chứa grant đã bị thu hồi, phạm vi cũ hoặc revision không còn được chấp nhận. Cần quyết định dựa trên trạng thái có thẩm quyền, kiểm tra phiên bản hoặc một mô hình hiệu lực ngắn có giới hạn sai lệch rõ ràng.

Trong cơ chế xác minh hoàn toàn offline, dịch vụ không thể tự biết mọi thu hồi vừa xảy ra ở nơi khác. Tuổi thọ token ngắn giúp giới hạn một số cửa sổ rủi ro nhưng không thay thế cam kết thu hồi tức thời. Độ lệch đồng hồ và cách kiểm tra thời hạn cũng ảnh hưởng mức bảo đảm thực tế.

Một số thành phần xác minh token cho phép dung sai lệch giờ. Nếu dung sai làm chấp nhận token sau `endsAt`, không được mặc định quyền nghiệp vụ cũng được kéo dài tương ứng. Có thể cần kiểm tra hạn grant riêng bằng nguồn thời gian đã chọn; mọi khoảng gia hạn thật sự phải là chính sách được phê duyệt, không là tác dụng phụ của cấu hình thư viện.

### 7.3. Refresh token không cấp quyền mới

Khi B đổi access token bằng refresh token lúc 17:01, hệ thống có thể tiếp tục duy trì phiên đăng nhập theo quyền trực tiếp của B. Nó không được tạo token ủy nhiệm mới có hạn đến 18:00 chỉ bằng cách lấy “bây giờ cộng một giờ” từ thông tin D1 cũ.

Nếu refresh có thể cấp quyền ủy nhiệm, phải tra grant và căn cứ hiện hành, kiểm tra actor, revision, trạng thái, thời gian và giới hạn tuổi thọ. Gia hạn phiên không được coi là gia hạn grant.

### 7.4. Cache phải bị giới hạn bởi hạn thực

Nếu cache lưu kết quả “D1 hợp lệ”, thời hạn sử dụng kết quả dương tính không được vượt `effectiveEndsAt`. Tuy nhiên TTL đến `endsAt` chưa xử lý được thu hồi trước hạn, thay đổi quyền gốc hoặc thay đổi đối tượng.

Cần cơ chế kiểm tra phiên bản, vô hiệu hóa hoặc xác minh cuối phù hợp độ nhất quán yêu cầu. Cache có thể hỗ trợ hiển thị và giảm tải, nhưng không được trở thành nguồn độc lập cấp thêm quyền sau khi dữ liệu có thẩm quyền đã kết thúc.

Giao diện nên hiển thị mốc kết thúc cùng múi giờ và làm mới khả năng thao tác. Màn hình đang mở vẫn phải nhận từ chối đúng nghĩa từ backend khi B gửi lệnh sau hạn. Một nút bị vô hiệu hóa không phải ranh giới bảo mật.

## 8. Chuỗi ủy nhiệm: quyền con không sống lâu hơn quyền cha

### 8.1. Thời hạn hiệu lực là phần giao của các căn cứ bắt buộc

Nếu cho phép A ủy nhiệm cho B, rồi B ủy nhiệm tiếp cho C, quyền của C phụ thuộc cả hai grant và quyền được ủy nhiệm tiếp. Với một chuỗi hợp lệ:

```text
effectiveStartsAt = max(startsAt của các grant trong chuỗi)
effectiveEndsAt   = min(endsAt của các grant trong chuỗi)

Chuỗi có hiệu lực về thời gian khi:
    effectiveStartsAt <= decisionAt < effectiveEndsAt
```

Nếu khoảng giao rỗng, chuỗi không tạo một quyền hợp lệ. Kiểm tra thời gian không thay thế kiểm tra trạng thái và phạm vi của từng mắt xích.

Ví dụ:

```text
D1: A -> B, 08:00 đến 17:00, cho phép ủy nhiệm tiếp có giới hạn
D2: B -> C, 10:00 đến 16:00

C chỉ có thể dùng chuỗi trong [10:00, 16:00).
```

Nếu B xin D2 đến 19:00 trong khi D1 chỉ đến 17:00, một lựa chọn rõ ràng là từ chối cấu hình vượt quyền cha. Nếu hệ thống chọn cắt hạn theo cha, phải lưu và hiển thị hạn thực tế đã được cấp; không để người nhận tưởng được dùng đến 19:00.

Hạn mức và phạm vi cũng phải được thu hẹp theo căn cứ cha. Mức ủy nhiệm tiếp không được tự tăng vì người nhận dùng một token khác hoặc tạo thêm một grant con.

### 8.2. Thu hồi và cấp lại grant cha

Nếu D1 bị thu hồi lúc 15:00, C không được tiếp tục dùng D2 đến 16:00 chỉ vì bản ghi D2 chưa được cập nhật. Quyết định phải xét căn cứ cha hoặc dựa trên cơ chế lan truyền thu hồi có bảo đảm đã được công bố.

Nếu A tạo D3 mới cho B đến 18:00, D2 không tự chuyển từ D1 sang D3. Cần một quan hệ cấp lại hoặc xét lại có chủ đích. Nếu chỉ tìm “bất kỳ grant nào của B còn hạn” rồi ghép vào, hệ thống có thể duy trì quyền con ngoài phạm vi đã được phê duyệt.

Kiểm soát độ sâu, phát hiện vòng lặp và giữ liên kết cha bất biến giúp tránh chuỗi không thể phân tích hoặc chuỗi vòng dùng để lách giới hạn. Mọi grant trong chuỗi phải thuộc cấu trúc tenant và phạm vi được phép.

## 9. Trạng thái hết hạn, gia hạn và cấp lại

### 9.1. Tách trạng thái quản trị khỏi trạng thái thời gian

Một mô hình có thể lưu trạng thái quản trị như `REQUESTED`, `GRANTED`, `REJECTED`, `CANCELLED`, `REVOKED`. Với grant đã được cấp, trạng thái thời gian được suy ra từ `startsAt`, `endsAt` và thời điểm đánh giá:

```text
decisionAt < startsAt             -> NOT_STARTED
startsAt <= decisionAt < endsAt   -> WITHIN_WINDOW
endsAt <= decisionAt              -> EXPIRED

Được sử dụng chỉ khi administrativeState cho phép
và mọi điều kiện thời gian, phạm vi, quyền đều đáp ứng.
```

Tác vụ nền có thể vật chất hóa `EXPIRED` để tìm kiếm, thông báo hoặc dọn token. Việc tác vụ đó chạy trễ không được kéo dài quyền: phép kiểm tra `decisionAt < endsAt` vẫn bắt buộc ở điểm quyết định.

Nếu mô hình lưu trạng thái kết thúc như `REVOKED` hoặc `CLOSED`, đăng nhập lại hay đổi token không được đưa grant đó về hiệu lực. Đồng hồ bị điều chỉnh lùi cũng không được tự phục hồi một grant đã được đóng bằng quyết định quản trị hoặc cơ chế kết thúc có thẩm quyền.

### 9.2. Gia hạn là một lần cấp quyền cần được xét lại

Không nhận một `newEndsAt` rồi sửa trực tiếp D1 chỉ vì B vẫn giữ token từng hợp lệ. Người nhận không mặc nhiên có quyền gia hạn, và quyền dùng D1 đã hết không thể tự làm căn cứ để kéo dài chính nó.

Một cách thiết kế là tạo grant kế nhiệm D2, giữ quan hệ `supersedes=D1` và thực hiện lại kiểm tra cần thiết: quyền người cấp, người nhận, phạm vi, hạn mức, thời gian, phê duyệt và căn cứ cha. Các quyết định lịch sử vẫn trỏ D1 và revision cũ.

Có thể gia hạn trước khi D1 kết thúc hoặc cấp lại sau khi đã hết, nhưng D2 chỉ cho phép hành động trong cửa sổ của D2. Nó không làm một thao tác đã bị từ chối trong khoảng trống trở thành hợp lệ hồi tố, cũng không tự kích hoạt lại các lệnh cũ đang nằm trong hàng đợi.

Nếu nghiệp vụ thật sự cần cấp hiệu lực từ quá khứ, đó là quyền và quy trình điều chỉnh riêng. Không sửa timestamp lịch sử để làm như thao tác đã được ủy nhiệm từ trước.

### 9.3. Rút ngắn hoặc thay thế grant

Muốn kết thúc sớm, dùng thao tác thu hồi hoặc thay thế có audit và quy tắc hiệu lực rõ ràng. Nếu cho phép cập nhật phiên bản grant, các token, cache và chuỗi con phải được xét theo revision; không giữ quyền dựa vào snapshot cũ mà hệ thống đã quyết định vô hiệu hóa.

Một thay đổi thời hạn cần giữ ai yêu cầu, ai chấp thuận, hạn cũ, hạn mới, lý do và thời điểm ghi nhận. Thời điểm hiệu lực, thời điểm ghi nhận và thời điểm các quyết định sử dụng grant là những dữ liệu khác nhau.

## 10. Retry, công việc chạy nền và callback sau hạn

### 10.1. Retry một kết quả cũ không dùng lại quyền để tạo tác dụng

Giả sử B duyệt thành công lúc 16:59:59, nhưng response bị mất. B retry cùng idempotency key lúc 17:00:02. Hệ thống cần phân biệt ba trường hợp:

| Trạng thái lần đầu | Xử lý lần gửi lại |
| --- | --- |
| Đã chốt thành công | Không duyệt lần nữa; trả kết quả đã lưu nếu B còn quyền xem |
| Chưa có quyết định cuối | Kiểm tra grant tại điểm quyết định mới; có thể bị từ chối vì hết hạn |
| Key trùng nhưng nội dung khác | Báo xung đột theo hợp đồng API, không dùng kết quả cũ cho nội dung mới |

Một key được tạo trước hạn không tự giữ quyền duyệt. Bản ghi `IN_PROGRESS` chỉ thể hiện tiến trình, không phải chấp thuận cuối hay giấy phép thao tác mãi sau đó.

Idempotency cần phạm vi phù hợp, chẳng hạn tenant, loại thao tác, actor và key, hoặc một namespace có kiểm tra sở hữu tương đương. Cùng key không được làm lộ kết quả của người khác. Kết quả phải gắn với grant/revision, hồ sơ/revision và nội dung đã chuẩn hóa; thay số tiền hoặc đối tượng không còn là cùng ý định.

Thời gian lưu chống trùng phải phù hợp cửa sổ retry và phát lại sự kiện. Nếu bản ghi chống trùng bị xóa sớm, cần định danh operation hoặc ràng buộc nghiệp vụ đủ để không tạo chấp thuận trùng cho một hành động đã hoàn tất.

### 10.2. Công việc nền không được biến thành kho giữ quyền quá hạn

Một thiết kế nguy hiểm là lưu token của B trong hàng đợi rồi để worker dùng token đó bất cứ lúc nào. Worker có thể chạy sau `endsAt`, token có thể bị lộ, và việc refresh có thể vô tình kéo dài quyền.

Cần chọn đúng mô hình:

- Nếu worker sẽ tạo quyết định được ủy nhiệm mới, nó phải kiểm tra quyền tại điểm quyết định theo hợp đồng.
- Nếu worker thực thi tác dụng của một quyết định đã chốt hợp lệ, nó cần tham chiếu quyết định bền vững, nội dung đã chốt và trạng thái nghiệp vụ được phép thực thi.
- Nếu công việc cần quyền hiện hành suốt nhiều bước, phải thiết kế điểm kiểm tra hoặc cấp quyền từng bước; một kiểm tra ở lúc bắt đầu không tự bao phủ mọi bước tương lai.

Ví dụ chính sách cho phép gửi thanh toán sau một chấp thuận cuối hợp lệ:

```text
16:59:59  B chốt chấp thuận bằng D1; lưu approval và sự kiện outbox.
17:00:00  D1 hết hạn cho mọi quyết định ủy nhiệm mới.
17:00:05  Dịch vụ thực thi đọc approval đã chốt, kiểm tra trạng thái khoản chi.
17:00:06  Dịch vụ gửi đúng lệnh thanh toán của operation đó bằng quyền hệ thống.
```

Đây không phải cách cho B tiếp tục duyệt sau hạn. Dịch vụ thực thi chỉ được làm tác dụng đã được chốt theo quy tắc, không cho B đổi số tiền, người nhận hay đối tượng thông qua payload mới. Một message tự khai `alreadyApproved=true` không đủ; phải tham chiếu bằng chứng và nội dung có thẩm quyền.

Nếu chính sách yêu cầu xét lại khi grant bị thu hồi hoặc trước lúc gửi tiền, bước thực thi vẫn phải áp dụng quy tắc đó. Gắn nhãn “system job” không miễn trừ kiểm soát nghiệp vụ và không tạo quyền vô hạn cho consumer.

### 10.3. Callback muộn không phải lệnh dùng quyền của B

Kết quả từ nhà cung cấp có thể đến sau khi D1 hết hạn. Nếu lệnh đã được gửi hợp lệ, callback cần được xác minh nguồn, đối chiếu operation, số tiền, trạng thái và chống trùng. Không bỏ kết quả chỉ vì B đã hết thời gian ủy nhiệm, vì như vậy trạng thái tiền thực tế và trạng thái hệ thống có thể lệch nhau.

Callback hợp lệ cũng không cho phép tạo một lệnh mới hoặc đổi người nhận. Nó là bằng chứng để cập nhật đúng operation đã có. Nếu cần bù trừ, đó là một hành động có căn cứ, quyền và idempotency riêng; không mượn lại D1 đã hết hạn để hợp thức hóa thao tác.

## 11. Audit và phát hiện sử dụng quyền sau hạn

### 11.1. Giữ được căn cứ của từng quyết định

Một bản ghi audit nên đủ để tái dựng:

```text
operationId, action
actorId, delegatorId, tenantId
delegationId, revision, chuỗi căn cứ cha liên quan
resourceId, resourceRevision
startsAt, endsAt, effectiveEndsAt
authorizationDecisionAt, timeSource
scope, hạn mức và chính sách quản trị liên quan
kết quả, mã lý do
receivedAt, executedAt nếu cần phân tích các bước sau
```

Audit phải thể hiện actor thực tế, không chỉ người ủy nhiệm. Grant lịch sử và nội dung đã chốt cần còn đủ để giải thích quyết định khi quyền hiện tại đã thay đổi.

`DELEGATION_EXPIRED`, `DELEGATION_REVOKED`, `OUT_OF_SCOPE` hoặc lý do tương đương giúp phân biệt lỗi. Cách trả lỗi ra ngoài phải phù hợp quyền của người gọi, không dùng thông báo chi tiết để lộ grant hoặc đối tượng ở tenant khác. Không ghi token, mật khẩu hay bí mật xác thực vào log.

Chấp thuận và audit nghiệp vụ nên được lưu nguyên tử tại nguồn có thẩm quyền. Nếu phải gửi sang kho khác, có thể dùng outbox và khử trùng phía nhận. Lần thử thất bại cũng có thể được ghi nhận, nhưng không để log nói “đã duyệt” khi transaction đã rollback.

### 11.2. Dấu hiệu cần rà soát

- Có quyết định mới ghi `authorizationDecisionAt >= effectiveEndsAt` nhưng vẫn dùng căn cứ ủy nhiệm đó.
- Token chuyên dùng cho D1 có thời hạn vượt grant hoặc được refresh sau khi grant kết thúc.
- Grant con có hạn dài hơn cha, hoặc vẫn được dùng sau khi cha bị thu hồi.
- Nhiều lần gia hạn ngay sát hạn, đổi người nhận hoặc đổi phạm vi trong khi giữ nguyên dấu đã duyệt.
- Quyết định dùng revision cũ sau khi hệ thống đã yêu cầu vô hiệu hóa revision đó.
- Actor và delegator trong audit không khớp quan hệ của grant.
- Consumer tạo tác dụng mới chỉ dựa vào thời điểm enqueue hoặc một cờ hợp lệ đã cũ.

Không đánh dấu mọi sự kiện có `executedAt > endsAt` là lạm dụng. Cần xét loại tác dụng và hợp đồng: nó có thể là thực thi một quyết định đã chốt trước hạn, phản hồi từ dịch vụ ngoài, hoặc một thao tác hệ thống độc lập. Điểm cần chứng minh là căn cứ thẩm quyền ở đúng bước, không chỉ sự tương quan timestamp.

## 12. Kiểm thử ranh giới và các lịch sự kiện đối kháng

### 12.1. Kiểm tra cửa sổ thời gian bằng đồng hồ điều khiển được

Với `s = startsAt`, `e = endsAt` và `epsilon` phù hợp độ chính xác được hỗ trợ:

| Mốc hoặc cấu hình | Kết quả mong đợi |
| --- | --- |
| `s - epsilon` | Chưa có hiệu lực |
| `s` | Hợp lệ về thời gian |
| `e - epsilon` | Hợp lệ về thời gian nếu vẫn không trước `s` |
| `e` | Hết hạn |
| `e + epsilon` | Hết hạn |
| `s == e` | Cấu hình không hợp lệ |
| `s > e` | Cấu hình không hợp lệ |

Ví dụ chuẩn bị một đồng hồ cố định tại đúng mốc kết thúc:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Instant start = Instant.parse("2026-12-15T01:00:00Z");
Instant end = Instant.parse("2026-12-15T10:00:00Z");
DelegationWindow window = new DelegationWindow(start, end);
Clock clock = Clock.fixed(end, ZoneOffset.UTC);

// Bộ kiểm thử cần xác nhận giá trị này là false.
boolean allowedByTime = window.includes(clock.instant());
```

Không dùng `sleep` để chờ đúng 17:00. Unit test kiểm soát đồng hồ; kiểm thử tích hợp kiểm soát thêm thứ tự khóa, commit, message và callback. Cần có phép thử round-trip qua nơi lưu trữ để phát hiện mất độ chính xác hoặc đổi múi giờ.

### 12.2. Kiểm thử hành vi lạm dụng

| Tình huống | Cách dựng | Điều cần xác nhận |
| --- | --- | --- |
| Mở màn hình trước hạn | Mở lúc 16:59, gọi API lúc 17:01 | Backend từ chối quyết định ủy nhiệm mới |
| Client lùi đồng hồ | Gửi `clientSentAt` trước hạn | Không thay thế thời gian có thẩm quyền |
| Đổi múi giờ | Thay offset, múi giờ trình duyệt hoặc mặc định JVM | Không kéo dài mốc thực của grant |
| Token còn hạn | Dùng token đăng nhập còn sống sau `endsAt` | Token không làm D1 còn hiệu lực |
| Refresh sau hạn | Đổi access token lúc D1 đã hết | Không cấp thêm quyền ủy nhiệm từ D1 |
| Cache cũ | Giữ kết quả hợp lệ trong cache qua hạn | Điểm quyết định vẫn từ chối |
| Thu hồi trước hạn | Cache hoặc token vẫn chứa grant cũ | Tuân thủ cam kết nhất quán và thu hồi đã định nghĩa |
| Chờ khóa qua hạn | Request vào trước hạn, giành khóa sau hạn | Không dùng thời gian kiểm tra trước chờ |
| Grant con vượt cha | Cấp con đến 19:00 trong khi cha đến 17:00 | Bị từ chối hoặc được cấp hạn thực tế rõ ràng không vượt cha |
| Cấp lại cha | D1 hết, tạo D3 cho B | Grant con của D1 không tự chuyển sang D3 |
| Tự gia hạn | B dùng token cũ sửa `endsAt` | Không gia hạn nếu thiếu quyền và quy trình cấp mới |
| Retry sau hạn | Lần đầu đã chốt nhưng response mất | Không tạo thêm approval; trả kết quả theo quyền xem hiện hành |
| Chưa chốt trước hạn | Key tồn tại nhưng operation còn xử lý | Không coi key là giữ quyền |
| Đổi payload khi retry | Cùng key, thay khoản chi hoặc số tiền | Xung đột; không dùng chấp thuận cũ cho nội dung mới |
| Sai actor hoặc tenant | C gửi delegation ID của B hoặc tenant khác | Không dùng được grant và không lộ dữ liệu trái quyền |
| Trộn nhiều grant | Lấy scope D1, hạn mức D2, hạn D3 | Không tạo căn cứ hỗn hợp ngoài chính sách |
| Mất quyền gốc | A bị thu hồi quyền khi D1 còn thời gian | D1 được xử lý theo mô hình phụ thuộc đã công bố |
| Callback muộn | Kết quả lệnh hợp lệ đến sau hạn | Đối soát đúng operation, không tạo lệnh mới |

### 12.3. Kiểm thử một lịch sự kiện đầy đủ

```text
Given:
    D1 cho B duyệt thay A đến 17:00, kết thúc không được tính
    điểm chốt quyền là sau khi giành khóa hồ sơ và căn cứ cần thiết
    khoản chi X thuộc đúng phạm vi, chưa có approval

When:
    B gửi yêu cầu lúc 16:59:59
    yêu cầu chờ khóa X cho đến 17:00:01
    worker hoặc API lấy authorizationDecisionAt rồi xử lý
    B retry cùng key bằng timestamp client trước 17:00

Then:
    không tạo approval dựa trên D1
    không đổi trạng thái X thành được duyệt
    timestamp client không thay điểm quyết định
    audit ghi đúng lần thử hết hạn, không ghi thành công giả
```

Chạy một biến thể trong đó approval đã được chốt trước 17:00 nhưng response mất. Khi ấy kết quả mong đợi khác: không tạo lần duyệt thứ hai; bản ghi thành công cũ vẫn tồn tại và có căn cứ trước hạn. Hai phép thử này giúp tránh cách sửa quá đơn giản là từ chối mọi request sau hạn, kể cả thao tác chỉ lấy lại kết quả đã chốt.

Một biến thể khác cho thu hồi đua với phê duyệt cần điều khiển thứ tự giành khóa để chứng minh cả hai thứ tự hợp lệ. Chỉ gửi hai request tuần tự không kiểm tra được khoảng hở cạnh tranh.

## 13. Đồng hồ, trạng thái kết thúc và khả năng phục hồi

### 13.1. UTC không tự đồng bộ thời gian

Lưu mốc theo UTC giúp thống nhất biểu diễn. Nó không làm các máy tự có đồng hồ giống nhau. Nếu mỗi instance tự đọc thời gian đang lệch, cùng một grant có thể được chấp nhận trên máy này và từ chối trên máy khác.

Cần chọn nguồn thời gian cho quyết định, theo dõi độ lệch và quy định hành vi khi nguồn không còn đủ tin cậy. Không mặc định cho qua khi không tra được grant hoặc không biết grant đã hết chưa. Có thể tạm từ chối thao tác ủy nhiệm nhạy cảm theo chính sách, trong khi quyền trực tiếp khác vẫn được đánh giá độc lập.

Đồng hồ thời gian thực có thể bị điều chỉnh lùi. Với yêu cầu bảo đảm chặt, cần xem xét cách duy trì quyết định đóng grant, nguồn thời gian và phục hồi sao cho grant đã kết thúc không bị mở lại ngoài ý muốn. Một trạng thái đóng chỉ hỗ trợ sau khi đã được ghi nhận; nó không tự giải quyết mọi trường hợp lệch giờ trước đó.

Đồng hồ đơn điệu dùng đo thời lượng cục bộ có thể hữu ích cho timeout, nhưng không thay thế timestamp tuyệt đối của grant. Không đem giá trị bộ đếm đơn điệu lưu rồi so sánh tùy ý giữa các máy hoặc sau khởi động lại.

### 13.2. Không phụ thuộc vào cron để hết quyền

Tác vụ hết hạn có thể bị dừng hoặc chạy trễ. Nó nên hỗ trợ thông báo, dọn cache, thu hồi token theo cơ chế đã chọn và lập chỉ mục trạng thái. Quyền phải kết thúc dựa vào điều kiện tại điểm quyết định dù tác vụ nền chưa kịp chạy.

Khởi động lại dịch vụ, nạp lại cache hay phục hồi bản sao không được đặt lại cửa sổ bằng “bây giờ cộng thời lượng ban đầu”. Phải giữ mốc kết thúc tuyệt đối đã được cấp. Việc phục hồi hệ thống cũng cần đối soát trạng thái thu hồi và các phiên bản, không chỉ tải danh sách grant từng có hiệu lực.

### 13.3. Hết hạn không đồng nghĩa được xóa hết bằng chứng

Xóa grant ngay tại `endsAt` có thể làm mất căn cứ giải thích các approval lịch sử, gây khó cho retry và đối soát. Có thể chuyển grant sang kho lịch sử hoặc hạn chế khả năng sử dụng, nhưng cần giữ tham chiếu và dữ liệu cần thiết theo chính sách lưu giữ.

Không lưu thông tin nhạy cảm dư thừa chỉ để phục vụ audit. Giữ định danh và snapshot đủ giải thích, giới hạn quyền đọc, và phân biệt dữ liệu quyết định với bí mật token có vòng đời ngắn hơn.

## 14. Bài tập áp dụng

Thiết kế tính năng ủy nhiệm phê duyệt cho nền tảng nhiều tenant với các yêu cầu:

1. A cấp cho B quyền duyệt trong một bộ phận, có hạn mức và thời gian kết thúc theo múi giờ văn phòng.
2. B có thể có quyền trực tiếp khác và một phiên đăng nhập dài hơn thời gian ủy nhiệm.
3. Có hàng đợi, refresh token, callback thanh toán và retry khi mất response.
4. Tổ chức cho phép một mức ủy nhiệm tiếp với thời hạn không vượt grant cha.
5. A có thể thu hồi sớm hoặc đề xuất cấp lại sau khi grant hết hạn.

Hãy viết ra grant schema, điểm chốt quyền ở từng bước, quy tắc token/cache, điều kiện chuỗi cha, cơ chế gia hạn và dữ liệu audit. Nêu rõ trường hợp nào là hành động được ủy nhiệm mới và trường hợp nào chỉ thực thi hay lấy kết quả của một quyết định đã chốt.

Sau đó dựng ba lịch sự kiện: chờ khóa qua hạn, thu hồi đua với duyệt, và refresh token sau hạn trong khi vẫn có grant con. Mỗi lịch phải xác định được tác dụng nào được phép, tác dụng nào bị từ chối và bằng chứng nào giúp giải thích kết quả.

## 15. Ghi nhớ

Thời điểm kết thúc ủy nhiệm giới hạn căn cứ được hành động thay người khác, độc lập với việc tài khoản còn đăng nhập hay token còn sống. Cần thống nhất khoảng `[startsAt, endsAt)`, điểm quyết định và nguồn thời gian có thẩm quyền.

Backend phải kết hợp thời hạn với actor, tenant, phạm vi, trạng thái, căn cứ cha và nội dung nghiệp vụ. Giao dịch bảo vệ quyết định; idempotency bảo vệ tác dụng khi retry; audit giữ được căn cứ đã dùng. Gia hạn là một lần cấp quyền được kiểm soát, còn tác vụ nền, cache và refresh token không được tự tạo thêm thời gian ủy nhiệm.
