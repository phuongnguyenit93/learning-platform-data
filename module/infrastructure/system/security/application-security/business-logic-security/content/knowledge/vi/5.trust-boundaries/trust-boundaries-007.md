# Ranh giới kiểm soát của quản trị viên — Administrator control boundary

## 1. Quyền quản trị có thể làm thay đổi chính điều kiện ra quyết định

Trong chương **Trust Boundaries** của học phần **Business Logic Security**, ranh giới quản trị là nơi công cụ, tài khoản hoặc tác vụ có đặc quyền tác động vào dữ liệu, cấu hình và quyết định nghiệp vụ.

Một hệ thống có thể kiểm tra rất chặt API của khách hàng nhưng vẫn cho phép:

- Nhân viên hỗ trợ đổi trạng thái đơn thành đã thanh toán.
- Người sửa cấu hình tăng ngưỡng hoàn tiền để bỏ qua cấp phê duyệt.
- Job sửa dữ liệu cộng trực tiếp số dư mà không ghi sổ.
- Người vận hành phát lại tác vụ với một mã mới, tạo thêm tác động tài chính.
- Một phiên giả lập khách hàng kế thừa toàn bộ quyền quản trị.
- Công cụ xử lý hàng loạt ghi dữ liệu của tenant ngoài phạm vi được giao.

Các hành động này đi qua ranh giới có mức tin cậy cao hơn, nhưng vẫn cần điều kiện và bằng chứng. Quyền quản trị phải được hiểu là tập các quyền cụ thể, không phải một ngoại lệ cho mọi business invariant.

Sau bài này, bạn cần có khả năng:

- Nhận diện các đường đi từ mặt phẳng quản trị vào trạng thái và quyền lợi nghiệp vụ.
- Tách quyền vận hành kỹ thuật, quyền quyết định nghiệp vụ và quyền thay đổi chính sách.
- Ràng buộc phê duyệt với đúng nội dung, tenant và phiên bản thay đổi.
- Bảo vệ thao tác quản trị trước giả mạo ngữ cảnh, cạnh tranh, retry và xử lý bất đồng bộ.
- Thiết kế kiểm thử chứng minh rằng đặc quyền không trở thành đường bỏ qua quy tắc.

## 2. Ranh giới này nằm ở đâu?

**Mặt phẳng quản trị** gồm những thành phần điều khiển cách hệ thống hoạt động: cổng quản trị, API nội bộ, công cụ dòng lệnh, tác vụ sửa dữ liệu, cấu hình, feature flag và workflow vận hành.

**Mặt phẳng nghiệp vụ** là nơi các quyết định ảnh hưởng đến đơn hàng, tiền, tồn kho, quyền truy cập hoặc dữ liệu của chủ thể.

Hai mặt phẳng có thể dùng chung một ứng dụng hoặc cơ sở dữ liệu. Ranh giới vẫn tồn tại về mặt thẩm quyền, kể cả khi không có một kết nối mạng riêng.

~~~mermaid
flowchart LR
    subgraph CONTROL[Mặt phẳng quản trị]
        ADMIN[Cổng quản trị và API]
        OPS[CLI và job vận hành]
        CONFIG[Chính sách và cấu hình]
    end
    subgraph GUARD[Ranh giới kiểm soát]
        AUTH[Actor và phạm vi]
        APPROVAL[Quyết định cùng nội dung được duyệt]
        RULES[Invariant và điều kiện thực thi]
        AUTH --> APPROVAL
        APPROVAL --> RULES
    end
    subgraph BUSINESS[Mặt phẳng nghiệp vụ]
        DATA[Trạng thái và sổ nghiệp vụ]
        EFFECT[Tác động bên ngoài]
    end
    ADMIN --> AUTH
    OPS --> AUTH
    CONFIG --> AUTH
    RULES --> DATA
    DATA --> EFFECT
~~~

Một feature flag như “bỏ yêu cầu duyệt hoàn tiền” có thể không trực tiếp chuyển tiền. Nó vẫn thay đổi quyền tạo tác động tài chính. Vì vậy, mức kiểm soát phải dựa trên **tác động có thể tạo ra**, không chỉ dựa trên việc thao tác đang sửa bảng cấu hình hay bảng giao dịch.

### 2.1. Các đường vượt ranh giới thường bị bỏ sót

| Đường vào | Tác động có thể xảy ra | Câu hỏi cần trả lời |
| --- | --- | --- |
| API quản trị | Duyệt, hủy, hoàn hoặc điều chỉnh | Ai có quyền trên đối tượng và giá trị cụ thể? |
| Feature flag, bảng chính sách | Bỏ một bước hoặc tăng quyền lợi | Ai được thay đổi quy tắc cấp quyền và ai phải duyệt? |
| Công cụ hỗ trợ | Hành động thay khách hàng | Ai thật sự khởi phát, đang đại diện cho ai, được làm gì? |
| Script sửa dữ liệu | Bỏ qua lớp nghiệp vụ | Invariant, lịch sử và sổ liên quan có còn đúng không? |
| Job replay hoặc backfill | Thực hiện lại tác động cũ | Đang sửa projection hay tạo thêm quyền lợi thật? |
| Batch import | Tạo hoặc sửa nhiều đối tượng | Phạm vi tenant và quyền trên từng dòng được kiểm tra ở đâu? |
| Kết nối cơ sở dữ liệu | Sửa trực tiếp dữ liệu có thẩm quyền | Quyền ghi được giới hạn thế nào và bằng chứng nằm ở đâu? |

Một API “chỉ nội bộ” vẫn phải xác thực caller và kiểm tra quyền. Mạng nội bộ hoặc một header có chữ “admin” không tự chứng minh thẩm quyền.

### 2.2. Phân biệt vận hành kỹ thuật và quyết định nghiệp vụ

Người có quyền khởi động lại worker không mặc nhiên có quyền hoàn tiền. Người được xem trạng thái thanh toán không mặc nhiên được sửa kết quả thanh toán. Người được điều tra sai lệch không tự có quyền đặt lại số dư cho khớp một báo cáo.

Ví dụ phân quyền minh họa:

| Vai trò hoặc năng lực | Có thể được cho phép | Không tự kéo theo |
| --- | --- | --- |
| Hỗ trợ khách hàng | Xem hồ sơ được phân công, tạo đề nghị điều chỉnh | Tự duyệt đề nghị của mình |
| Quản lý nghiệp vụ | Duyệt trong hạn mức và phạm vi được giao | Sửa hạn mức để mở rộng quyền của chính mình |
| Quản trị chính sách | Soạn phiên bản chính sách mới | Tự bỏ bước phê duyệt phiên bản đó |
| Vận hành hệ thống | Khởi động, dừng hoặc quan sát job | Tạo lệnh tài chính mới ngoài workflow |
| Quản trị dữ liệu | Thực hiện sửa chữa đã được phê duyệt | Sửa xóa lịch sử để che tác động |
| Kiểm toán hoặc đối soát | Đọc bằng chứng trong phạm vi cần thiết | Thay đổi quyết định hoặc chứng từ gốc |

Tên vai trò có thể khác trong từng tổ chức. Điều quan trọng là quyền có thể mô tả theo hành động, đối tượng, giá trị và quan hệ.

## 3. Xác định actor quản trị và phạm vi có hiệu lực

Một ngữ cảnh quản trị đáng tin cậy có thể cần:

~~~text
danh tính người thực sự thao tác
tài khoản nội bộ
phiên hoặc credential được xác minh
tenant và phạm vi được phép
năng lực hiện hành
quan hệ đại diện nếu có
tham chiếu cấp quyền tạm thời hoặc xác nhận bổ sung
nguồn và mục đích thao tác
~~~

Dữ kiện phải được tạo hoặc xác minh tại ranh giới được kiểm soát. Không nhận nguyên trạng từ JSON các trường như `isAdmin`, `approvedBy`, `scope=ALL_TENANTS` hoặc `skipValidation=true`.

Tenant trong request có thể là đối tượng người quản trị muốn tác động. Máy chủ phải đối chiếu nó với phạm vi hiện hành và phạm vi của quyết định đã được duyệt. Không tự coi việc chọn tenant trên giao diện là bằng chứng được phép.

### 3.1. Quyền mạnh cần điều kiện sử dụng rõ ràng

Một số thao tác có thể yêu cầu:

- Quyền chỉ có hiệu lực trong một khoảng thời gian.
- Xác thực mới hơn hoặc bước xác nhận bổ sung theo chính sách.
- Tham chiếu hồ sơ công việc hoặc lý do có cấu trúc.
- Hạn mức tiền, số lượng bản ghi hoặc số tenant.
- Phê duyệt độc lập trước thực thi.

Các điều kiện đó phải được máy chủ kiểm tra và ràng buộc với hành động. Một cờ `recentlyVerified=true` do frontend gửi không chứng minh đã xác nhận. Một mã hồ sơ công việc bất kỳ cũng không tự cấp quyền.

Không dùng xác thực mạnh để thay thế phân quyền hoặc tách biệt nhiệm vụ. Một tài khoản được xác thực chắc chắn vẫn có thể cố ý tạo yêu cầu vượt thẩm quyền.

### 3.2. Phiên cũ và cache quyền

Quyền quản trị có thể bị thu hồi hoặc hết hạn trong khi phiên còn tồn tại. Chính sách phải xác định điều kiện nào cần kiểm tra lại tại lúc thực thi, đặc biệt với thao tác có tác động lớn.

Cache quyền cần có phạm vi và cơ chế hiệu lực phù hợp. Nếu yêu cầu phải ngăn ngay thao tác mới sau khi thu hồi, một bản quyền cũ trong token hoặc cache không tự đáp ứng được điều kiện đó.

Đồng thời, cần phân biệt một yêu cầu mới với quyết định đã được chấp nhận hợp lệ. Việc có tiếp tục thực hiện quyết định cũ sau khi quyền người khởi phát thay đổi hay không phải do chính sách quy định, không phụ thuộc ngẫu nhiên vào thời điểm worker chạy.

### 3.3. Giả lập hoặc hành động thay khách hàng

Công cụ hỗ trợ có thể cho nhân viên xem giao diện dưới góc nhìn khách hàng. Thiết kế cần giữ riêng:

~~~text
initiatingActor: nhân viên hỗ trợ
effectiveSubject: khách hàng được hỗ trợ
delegationScope: các hành động được cho phép
~~~

Không làm mất dấu người thực sự khởi phát. Không cho phiên giả lập kế thừa mọi quyền quản trị vào endpoint khách hàng hoặc mọi quyền khách hàng vào endpoint đặc quyền.

Có thể chỉ cho xem, hoặc chỉ cho một số hành động được ủy quyền. Quyền thay mặt phải có phạm vi và điều kiện riêng, không được suy ra từ việc mở được màn hình của khách hàng.

## 4. Ví dụ xuyên suốt: thay đổi ngưỡng phê duyệt hoàn tiền

Xét chính sách minh họa của tenant T1:

- Quản lý hỗ trợ được duyệt hồ sơ hoàn tiền đến 2.000.000 VND trong phạm vi được giao.
- Khoản lớn hơn cần bộ phận tài chính phê duyệt.
- Người đề nghị không được tự duyệt.
- Thay đổi ngưỡng phân quyền phải có phê duyệt nghiệp vụ độc lập.
- Phiên bản chính sách đã phát hành phải có nội dung bất biến.

Người được sửa cấu hình đề nghị tăng ngưỡng từ 2.000.000 lên 20.000.000 VND. Đây là thay đổi thẩm quyền, dù giao diện chỉ có một ô số.

Nếu endpoint cấu hình cho ghi trực tiếp giá trị mới, một hồ sơ hoàn 8.000.000 VND có thể đi qua luồng quản lý hỗ trợ mà không cần cấp phê duyệt tài chính như trước.

Điểm vượt ranh giới không nhất thiết nằm ở API hoàn tiền. Nó nằm ở chỗ **quyền thay dữ liệu cấu hình được chuyển thành quyền thay điều kiện cấp phép nghiệp vụ** mà thiếu kiểm soát.

### 4.1. Những câu hỏi cần được trả lời

- Ai được soạn thay đổi và trên tenant nào?
- Ai được duyệt thay đổi thuộc loại và mức tác động này?
- Người soạn có được tự duyệt không?
- Người duyệt đã nhìn thấy đúng nội dung cuối cùng chưa?
- Thay đổi dựa trên phiên bản chính sách hiện hành nào?
- Khi nào thay đổi có hiệu lực và ai có quyền phát hành?
- Những quyết định đang chờ sẽ dùng phiên bản cũ hay cần đánh giá lại?
- Có thể giải thích chính xác phiên bản nào đã cho phép một khoản hoàn không?

Các câu trả lời phải được chuyển thành invariant và điều kiện tại máy chủ. Một dòng mô tả “chỉ quản trị viên mới được sửa” chưa đủ.

## 5. Invariant cho thao tác quản trị có tác động nghiệp vụ

Một số invariant cho ví dụ thay ngưỡng:

~~~text
Actor chỉ tác động trên phạm vi hiện hành được cấp.
Quyết định duyệt phải bao phủ đúng nội dung và tenant cần phát hành.
Người soạn không được tự duyệt nếu chính sách cấm.
Sửa nội dung có ý nghĩa làm mất hiệu lực phê duyệt cũ.
Phiên bản nền phải khớp phiên bản có thẩm quyền khi áp dụng.
Một quyết định phát hành không tạo nhiều lần thay đổi ngoài dự kiến.
Lịch sử phải cho biết ai đề nghị, ai duyệt và ai thực thi.
Các giao dịch tài chính vẫn phải giữ ngân sách và tính duy nhất.
~~~

Việc tăng ngưỡng phê duyệt không có nghĩa được hoàn nhiều hơn tiền có thể hoàn. Thay đổi một chính sách phân quyền không được vô tình vô hiệu hóa các invariant tài chính độc lập.

### 5.1. Phê duyệt phải có binding đủ cụ thể

Một thay đổi có thể được mô tả bằng:

~~~text
changeRequestId
targetTenant
policyType
basePolicyVersion
candidatePolicySnapshot
changeContentRevision
effectiveTime hoặc điều kiện hiệu lực
requestedBy
approvalDecisionId
~~~

Quyết định duyệt phải tham chiếu đúng nội dung này hoặc một snapshot bất biến tương đương. Nếu người soạn đổi tenant, ngưỡng tiền, thời điểm hiệu lực hoặc các điều kiện quan trọng sau khi được duyệt, phải đánh giá lại theo quy trình.

Một cờ `approved=true` gắn với ID yêu cầu nhưng không gắn nội dung dễ cho phép đổi đề bài sau phê duyệt.

Hash có thể hỗ trợ so khớp nội dung với giá trị tham chiếu đáng tin cậy. Hash không tự chứng minh người duyệt có thẩm quyền; người sửa được cả nội dung lẫn hash vẫn có thể tạo một cặp khớp nhau. Khi dùng hash, cần schema và cách chuẩn hóa nhất quán.

### 5.2. Không để đề xuất tự quyết định quy tắc phê duyệt chính nó

Nếu nội dung đề xuất chứa một trường “không cần phê duyệt”, hệ thống không được dùng chính trường đó để bỏ bước duyệt đề xuất.

Các quy tắc kiểm soát việc thay quyền, sửa chính sách và bỏ kiểm tra cần nằm trong một phạm vi quản trị được bảo vệ tương ứng. Thay đổi các quy tắc này cũng cần một quy trình riêng với thẩm quyền phù hợp.

Mục tiêu là tránh vòng lặp: “được phép sửa chính sách, nên có thể sửa chính sách để tự cho phép mọi thứ”. Không giải quyết bằng cách đặt tên vai trò lớn hơn nếu vai trò đó vẫn do chính caller tự cấp qua cùng một đường yếu.

## 6. State machine cho thay đổi quản trị

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_APPROVAL: Gửi đúng nội dung và phạm vi
    PENDING_APPROVAL --> APPROVED: Đủ phê duyệt theo quy tắc kiểm soát
    PENDING_APPROVAL --> REJECTED: Không được duyệt
    PENDING_APPROVAL --> DRAFT: Sửa nội dung cần đánh giá lại
    APPROVED --> DRAFT: Sửa nội dung và vô hiệu phê duyệt cũ
    APPROVED --> PUBLISHED: Phát hành đúng binding và phiên bản nền
    APPROVED --> REVOKED: Thu hồi theo thẩm quyền
~~~

Sơ đồ minh họa việc phát hành có hiệu lực tại nguồn chính sách có thẩm quyền. Nếu hỗ trợ lịch hẹn, rollout từng phần hoặc phê duyệt nhiều cấp, cần thêm trạng thái và điều kiện tương ứng.

Mỗi mũi tên cần kiểm tra actor, phạm vi, phiên bản và điều kiện. Không nhận một trạng thái đích từ request rồi gán trực tiếp.

### 6.1. Rủi ro dùng phiên bản nền cũ

Giả sử hai đề xuất cùng dựa trên chính sách phiên bản 12:

- Đề xuất A thay ngưỡng.
- Đề xuất B thay điều kiện phạm vi và được phát hành trước, tạo phiên bản 13.

Nếu A ghi đè toàn bộ chính sách từ bản cũ, nó có thể xóa thay đổi đã được duyệt của B. Vì vậy, khi phát hành A phải phát hiện phiên bản nền không còn phù hợp.

Có thể yêu cầu cập nhật đề xuất và duyệt lại, hoặc dùng cơ chế hợp nhất có kiểm soát nếu chính sách cho phép. Không tự hợp nhất các trường quan trọng rồi coi phê duyệt cũ đã bao phủ nội dung mới.

### 6.2. Rollback cũng là một quyết định mới

Phát hành lại nội dung cũ có thể khôi phục một ngưỡng nguy hiểm hoặc mở lại quyền đã thu hồi. Quyền rollback không nên là đường bỏ qua quy trình.

Nên tạo một phiên bản mới có tham chiếu nguồn và quyết định phù hợp. Không sửa ngược nội dung phiên bản 12 để làm lịch sử trông như chưa từng đổi.

Nếu thay đổi đã tạo tác động như hoàn tiền, rollback cấu hình không đảo ngược được tiền đã chuyển. Cần một quy trình điều chỉnh riêng cho tác động thực tế nếu có căn cứ.

## 7. Minh họa Java: phát hành chính sách đã được duyệt

Đoạn mã sau là **mã khung kiến trúc**, chưa phải ứng dụng chạy độc lập. Nó minh họa phát hành tại một kho chính sách có thẩm quyền trong transaction cục bộ; không khẳng định mọi dịch vụ đã cập nhật ngay sau khi hàm trả về.

~~~java
record PublishPolicyCommand(
        String changeRequestId,
        long expectedChangeRevision,
        long expectedActivePolicyVersion,
        String idempotencyKey) {}

record PolicyPublicationReceipt(
        String publicationId,
        long policyVersion,
        String status) {}

public PolicyPublicationReceipt publishPolicy(
        AdminActor actor,
        PublishPolicyCommand command) {

    validateCommand(command);

    return transactions.required(() -> {
        var change = changeRequests.lockByTenantAndId(
                actor.activeTenantId(),
                command.changeRequestId());

        permissions.requireCurrentPublishCapability(actor, change.scope());

        var scope = new IdempotencyScope(
                actor.activeTenantId(),
                actor.subjectId(),
                "PUBLISH_POLICY");

        var replay = idempotency.claimOrReplay(
                scope,
                command.idempotencyKey(),
                fingerprints.forPolicyPublication(command));

        if (replay.isPresent()) {
            return replay.get();
        }

        change.requireContentRevision(command.expectedChangeRevision());
        change.requireApprovedAndUnpublished();

        var approval = approvals.loadForChange(change.approvalDecisionId());
        approval.requireValidForExactChange(
                change.approvalBinding(), serverClock.instant());
        separationRules.requireValidParticipants(change, approval);
        publicationGuardrails.requirePermittedCandidate(change, approval);

        var head = activePolicies.lockHead(
                change.tenantId(), change.policyType());

        head.requireVersion(command.expectedActivePolicyVersion());
        change.requireBasePolicyVersion(head.version());

        var version = policyVersions.insertImmutable(change.candidateSnapshot());
        var publication = head.activateNext(version);
        activePolicies.save(head);
        change.markPublished(publication.id(), version.number());
        changeRequests.save(change);

        auditOutbox.appendPolicyPublished(
                actor.auditIdentity(), change, approval, publication);

        var result = new PolicyPublicationReceipt(
                publication.id(),
                version.number(),
                "PUBLISHED_AT_AUTHORITY");

        idempotency.complete(scope, command.idempotencyKey(), result);
        return result;
    });
}
~~~

Các hợp đồng bắt buộc của mã khung:

1. `AdminActor` được tạo từ ranh giới xác thực và quyền quản trị đã kiểm chứng. Tenant đang chọn phải thuộc phạm vi được phép.
2. `requireCurrentPublishCapability` kiểm tra quyền trên loại chính sách và tenant cụ thể. Nó không coi quyền soạn là quyền phát hành.
3. Kiểm tra quyền trước replay bảo vệ dữ liệu kết quả. Các điều kiện chỉ áp dụng cho lần phát hành mới được kiểm tra sau replay, vì lần đầu đã chuyển trạng thái hợp lệ.
4. `claimOrReplay` dùng lưu trữ có ràng buộc duy nhất, so khớp fingerprint và xử lý cạnh tranh theo hợp đồng. Nếu transaction bị hủy vì xung đột, phải kết thúc nó trước khi đọc lại hoặc retry.
5. `approvalBinding` bao phủ nội dung, tenant, loại chính sách, phiên bản nền và điều kiện hiệu lực quan trọng. Bản ghi phê duyệt được tải từ nguồn đáng tin cậy, không nhận từ client.
6. `separationRules` kiểm tra các quan hệ bắt buộc như người soạn khác người duyệt. Ai được phát hành sau phê duyệt là quy tắc riêng; không mặc nhiên yêu cầu hoặc bỏ yêu cầu một người thứ ba.
7. `publicationGuardrails` áp dụng quy tắc kiểm soát có thẩm quyền, độc lập với các giá trị đề xuất có thể tự mở rộng quyền. Ví dụ chỉ áp dụng phát hành tức thời theo luồng này; lịch hẹn cần luồng tương ứng.
8. Khóa head và kiểm tra phiên bản nền ngăn hai đề xuất ghi đè quyết định đã phát hành trước đó. Các đường ghi khác phải dùng cơ chế tương thích và thứ tự khóa nhất quán.
9. Phiên bản mới bất biến, tham chiếu hiện hành, trạng thái yêu cầu, sự kiện kiểm toán và kết quả idempotency cùng commit hoặc rollback.
10. Khóa request mới không cho phép phát hành lại cùng yêu cầu đã được sử dụng. State machine và ràng buộc duy nhất theo quyết định nghiệp vụ vẫn phải có.

Mã khung chưa triển khai cập nhật cache của mọi dịch vụ. `PUBLISHED_AT_AUTHORITY` phản ánh bước đã hoàn tất tại nguồn có thẩm quyền, không phải xác nhận triển khai đồng bộ toàn hệ thống.

## 8. Phiên bản chính sách phải đi đến đúng nơi tạo tác động

Một thay đổi được duyệt đúng nhưng dịch vụ tiếp tục dùng bản cũ ngoài chính sách có thể vẫn tạo quyết định sai.

Cần xác định:

- Nơi có thẩm quyền chọn phiên bản cho một quyết định mới.
- Dữ liệu nào được chụp cùng quyết định.
- Khi nào phải kiểm tra lại phiên bản hoặc trạng thái thu hồi.
- Những quyết định đang chờ được giữ hiệu lực hay phải đánh giá lại.
- Nếu consumer chưa nhận bản mới, có được tiếp tục xử lý hay phải chờ?

Trong một thiết kế, tác vụ nhạy cảm lấy hoặc xác nhận tham chiếu phiên bản từ nguồn có thẩm quyền trước khi tạo quyết định. Cache cung cấp nội dung bất biến của phiên bản đó, không tự chọn một bản cũ chỉ vì đọc nhanh hơn.

Thiết kế khác có thể có giai đoạn chuyển tiếp được định nghĩa rõ. Khi đó phải biết chính sách nào áp dụng tại mỗi mốc; không mô tả rollout bất đồng bộ như một thời điểm đổi nguyên tử trên mọi dịch vụ.

Message cập nhật chính sách cần chống áp dụng trùng và cũ. Phiên bản 14 đến sau 15 không được làm tham chiếu hiện hành quay về 14. Khôi phục backup cũng cần phục hồi các thay đổi có hiệu lực trước khi tiếp tục xử lý theo chính sách.

Nếu một điều kiện hiện hành bắt buộc không thể được kiểm chứng, không tự mặc định cho phép thao tác đặc quyền. Cách chờ, từ chối hoặc xử lý khẩn cấp phải có hợp đồng riêng.

## 9. Job sửa dữ liệu, replay và tác động bên ngoài

### 9.1. Sửa dữ liệu không được phá sổ và quan hệ

Công cụ quản trị không nên cung cấp một lệnh “đặt số dư mới” mà không biết giao dịch nào tạo thay đổi. Với tài sản tiền tệ, cần giao dịch điều chỉnh có căn cứ, quyền, mục đối ứng phù hợp và lịch sử.

Tương tự, đổi `PAID` trong bảng đơn không chứng minh đã nhận tiền. Sửa `REFUNDED` không tự hoàn tiền ở nhà cung cấp. Công cụ phải phân biệt sửa projection, sửa trạng thái cần đối soát và tạo tác động thực sự.

Nếu cần sửa trực tiếp, phải xác định các invariant liên quan, phạm vi bản ghi, phiên bản kỳ vọng và bằng chứng trước–sau. Không chỉ dựa vào việc người chạy biết SQL.

### 9.2. Replay phải giữ đúng ý nghĩa

Có ít nhất hai việc khác nhau:

- Xây lại projection từ sự kiện đã có.
- Thực hiện lại lệnh có thể tạo tác động bên ngoài.

Xây lại một màn hình báo cáo không nên phát lại lệnh hoàn tiền. Tác vụ replay tác động thật cần dùng mã lệnh ổn định và tính duy nhất nghiệp vụ, thay vì tạo ID mới để tránh lỗi trùng.

Một cờ `force` chỉ được có nghĩa trong một hợp đồng hẹp. Nó không được mặc nhiên bỏ kiểm tra quyền, ngân sách, phê duyệt, trạng thái và chống trùng cùng lúc.

### 9.3. Transaction cục bộ không bao trùm nhà cung cấp

Outbox giúp không bỏ mất ý định đã commit trước khi gọi dịch vụ ngoài. Nó không tự bảo đảm tác động bên ngoài xảy ra đúng một lần.

Cần kết hợp mã lệnh ổn định, idempotency theo hợp đồng nhà cung cấp, điều kiện chuyển trạng thái và đối soát. Nếu timeout, không tạo lệnh nghiệp vụ mới hoặc giải phóng khoản giữ chỉ vì chưa nhận được kết quả.

Người vận hành xử lý một lệnh chưa rõ kết quả cần nhìn thấy bằng chứng tương ứng. Một nút “thử lại” không được biến tình trạng chưa rõ thành quyền thực hiện thêm lần nữa.

## 10. Thao tác hàng loạt cần một phạm vi được duyệt có thể kiểm chứng

Một người được phép sửa một hồ sơ không tự có quyền sửa một triệu hồ sơ. Batch làm tăng phạm vi thiệt hại và tạo thêm khoảng cách giữa lúc xem trước với lúc thực thi.

Một kế hoạch thay đổi có thể cần:

~~~text
batchId
tenant và phạm vi đối tượng
hành động cùng giá trị thay đổi
danh sách hoặc snapshot tập mục tiêu
phiên bản kỳ vọng của các đối tượng quan trọng
giới hạn số lượng và tổng giá trị
người đề nghị và quyết định phê duyệt
điều kiện dừng, retry và xử lý từng phần
~~~

### 10.1. Xem trước không tự bảo đảm tập dữ liệu lúc chạy

Nếu bản preview dùng một bộ lọc rồi nhiều giờ sau job chạy lại bộ lọc đó, tập kết quả có thể đã đổi. Người duyệt có thể đã duyệt 100 hồ sơ nhưng job tác động 150 hồ sơ.

Có thể đóng băng danh sách và phiên bản cần thiết, hoặc định nghĩa rõ quyền áp dụng cho một tập động cùng giới hạn và điều kiện. Không tự coi preview cũ đã phê duyệt mọi bản ghi tương lai khớp bộ lọc.

Mỗi đối tượng vẫn cần đúng tenant, quan hệ và trạng thái. Quyền trên dòng đầu tiên không bao phủ phần còn lại.

### 10.2. Batch từng phần phải có trạng thái từng phần

Nếu xử lý theo nhiều transaction, toàn bộ batch không còn nguyên tử. Cần biết mục nào đã hoàn tất, thất bại hoặc chưa rõ kết quả.

Retry phải dùng định danh ổn định cho từng ý định con, không chạy lại toàn bộ bằng mã mới rồi tạo tác động trùng. Hủy job không tự rollback các tác động đã commit hoặc đã xảy ra bên ngoài.

Response và báo cáo phải phản ánh đúng trạng thái đó. Không báo thành công toàn bộ chỉ vì job đã được đưa vào queue.

## 11. Quyền khẩn cấp cần được thiết kế trước

**Break-glass** là cơ chế dùng đặc quyền trong tình huống khẩn cấp theo một chính sách đã xác định. Nó không nên là một tham số bí mật cho phép bỏ mọi kiểm soát.

Một thiết kế có thể quy định:

- Ai đủ điều kiện kích hoạt và phải xác thực như thế nào.
- Hành động, tenant, đối tượng và hạn mức nào được bao phủ.
- Thời gian hiệu lực và cơ chế tự hết hạn.
- Điều kiện cần phê duyệt trước hoặc quy trình kiểm tra sau theo loại sự cố.
- Dấu vết, cảnh báo và người có trách nhiệm xem xét.
- Những invariant hoặc loại tác động nào vẫn không được bỏ qua.

Tùy tình huống, chính sách có thể cho phép quy trình khẩn cấp khác quy trình thông thường. Sự khác biệt phải được biểu diễn bằng một quyền và quyết định có phạm vi, không bằng việc tắt toàn bộ validation.

Ví dụ, quyền khẩn cấp dừng một luồng hoàn tiền không tự cho phép ghi thêm tiền vào ví. Quyền giải phóng một số tác vụ không tự cho phép sửa lịch sử chứng minh tác vụ đã được duyệt.

Quyền hết hạn cần được thực thi tại nơi tạo tác động mới, không chỉ ẩn nút trong giao diện. Credential hoặc bản sao quyền được cấp trong sự cố cũng cần nằm trong cơ chế thu hồi phù hợp.

Cổng quản trị chạy trong trình duyệt vẫn cần bảo vệ phiên và chống giả mạo yêu cầu theo kiến trúc. Việc yêu cầu đến từ một trang quản trị cùng origin không thay thế điều kiện đặc quyền nêu trên.

## 12. Dấu vết kiểm toán và giới hạn của mô hình tin cậy

Đối với một thay đổi có tác động nghiệp vụ, cần trả lời được:

~~~text
Ai khởi phát?
Ai soạn nội dung?
Ai duyệt nội dung nào?
Ai phát hành hoặc thực thi?
Phạm vi tenant và đối tượng là gì?
Phiên bản trước và sau là gì?
Quyết định nào cho phép tác động?
Kết quả thực tế và tác động bên ngoài là gì?
~~~

Một chuỗi tương quan cho ví dụ:

~~~text
adminRequestId
  -> changeRequestId + contentRevision
  -> approvalDecisionId
  -> publicationId + policyVersion
  -> refundDecisionId
  -> refundExecutionId
  -> externalTransactionId
~~~

Không cần sao chép bí mật hoặc toàn bộ dữ liệu cá nhân vào log. Có thể lưu snapshot được bảo vệ, mã lý do và tham chiếu cần thiết. Quyền đọc bằng chứng cũng phải theo phạm vi.

### 12.1. Ghi log trong cùng transaction chưa tạo bằng chứng chống mọi sửa đổi

Audit outbox bảo đảm ý định kiểm toán đi cùng thay đổi cục bộ khi cơ chế transaction hoạt động đúng. Nó không ngăn một tài khoản có quyền ghi trực tiếp toàn bộ cơ sở dữ liệu sửa cả dữ liệu lẫn outbox.

Tùy mô hình đe dọa, có thể cần lưu bằng chứng ở miền quyền riêng, hạn chế quyền sửa xóa và theo dõi việc chuyển giao. Người thao tác nghiệp vụ không nên đồng thời có quyền xóa dấu vết của chính thao tác đó.

Nếu một chủ thể kiểm soát cả ứng dụng, cơ sở dữ liệu và toàn bộ nơi lưu bằng chứng, một kiểm tra nằm hoàn toàn trong các thành phần đó không thể tự chứng minh độc lập rằng mọi thứ chưa bị thay đổi. Cần xác định rõ những thành phần và người vận hành nào vẫn được tin, cùng ranh giới kiểm soát bên ngoài nếu mục tiêu yêu cầu.

Đây là cách đặt mục tiêu bảo vệ có thể kiểm chứng. Không nên hứa rằng một cột chỉ ghi thêm hoặc một bảng audit thông thường tự chống được mọi cấp quản trị hạ tầng.

### 12.2. Các tín hiệu đáng điều tra

- Cấp quyền tạm thời rồi lập tức thay chính sách mở rộng cùng quyền đó.
- Thay đổi ngưỡng hoặc feature flag gần thời điểm có tác động giá trị lớn.
- Nhiều lần dùng cờ ép chạy hoặc replay trên cùng giao dịch.
- Thao tác khác tenant so với phạm vi công việc được ghi nhận.
- Phiên bản chính sách được dùng nhưng không có publication tương ứng.
- Tác động tài chính không nối được tới quyết định có thẩm quyền.
- Khoảng trống lịch sử hoặc thay đổi qua đường ghi không phát dấu vết.

Các tín hiệu này hỗ trợ điều tra, không tự chứng minh gian lận. Giám sát cũng không thay thế việc chặn quyền và invariant trước khi tác động xảy ra.

## 13. Kiểm thử ranh giới quản trị

Thực hiện trên môi trường và dữ liệu được phép. Kiểm thử phải bao phủ API, công cụ vận hành, batch và worker, không chỉ thao tác trên màn hình quản trị.

| Tình huống | Thao tác kiểm thử | Điều cần chứng minh |
| --- | --- | --- |
| Giả đặc quyền | Gửi cờ admin, header vai trò hoặc tenant tự chọn | Không thay thế context và quyền có thẩm quyền |
| Sai phạm vi | Actor quản trị T1 tác động dữ liệu T2 | Không tạo tác động hoặc tiết lộ dữ liệu trái quyền |
| Vượt loại hành động | Người soạn gọi endpoint phát hành | Quyền soạn không tự thành quyền phát hành |
| Tự duyệt | Người soạn dùng tài khoản hoặc vai trò khác của cùng danh tính khi chính sách cấm | Không thỏa điều kiện độc lập |
| Sửa sau duyệt | Duyệt ngưỡng 2 lên 5 triệu rồi đổi nội dung thành 20 triệu | Phê duyệt cũ không áp dụng |
| Đổi tenant hoặc thời điểm | Giữ decisionId nhưng thay phạm vi hoặc điều kiện hiệu lực | Binding bị phát hiện không khớp |
| Tự bỏ bước kiểm soát | Đề xuất chứa cờ không cần duyệt rồi thử dùng cờ đó để phát hành | Quy tắc kiểm soát không bị đề xuất tự vô hiệu |
| Quyền bị thu hồi | Giữ phiên cũ sau khi mất năng lực quản trị cần thiết | Thao tác mới tuân theo chính sách hiệu lực |
| Phiên bản nền cũ | Hai đề xuất cùng nền, một bản được phát hành trước | Bản sau không ghi đè thay đổi mới ngoài quy trình |
| Retry cùng request | Mất phản hồi rồi gửi lại cùng khóa và nội dung | Cùng publication, không thêm tác động |
| Khóa mới | Gửi khóa khác cho thay đổi đã phát hành | Không nhân bản quyết định phát hành |
| Lỗi trong transaction | Gây lỗi sau lưu phiên bản nhưng trước cập nhật head hoặc outbox | Không commit trạng thái cục bộ dở dang |
| Consumer nhận bản cũ | Gửi thông báo phiên bản mới rồi cũ | Không quay lùi tham chiếu hiện hành |
| Batch đổi tập mục tiêu | Thêm bản ghi khớp filter sau preview | Chỉ tác động đúng phạm vi và giới hạn được duyệt |
| Job replay | Chạy lại projection và lệnh tài chính | Không phát tác động thật từ luồng chỉ xây lại dữ liệu đọc |
| Kết quả ngoài chưa rõ | Tác động đã xảy ra nhưng worker nhận timeout | Không tạo lệnh mới hoặc giải phóng quyền lợi sai |
| Quyền khẩn cấp hết hạn | Thực hiện sau thời hạn hoặc ngoài phạm vi đã cấp | Không tạo tác động đặc quyền mới |
| Can thiệp lịch sử | Dùng quyền nghiệp vụ thử sửa hoặc xóa bằng chứng | Bị chặn trong mô hình quyền đã thiết kế |

Với cạnh tranh, cần cho các transaction thật sự tranh chấp trên cùng head, thay đổi hoặc ngân sách. Hai request tuần tự không chứng minh được tính nguyên tử. Mock repository không chứng minh khóa, uniqueness hoặc rollback.

Sau mỗi kịch bản, kiểm tra:

- Nội dung và trạng thái của yêu cầu thay đổi.
- Phê duyệt có đúng binding và người tham gia không.
- Số publication, phiên bản bất biến và head hiện hành.
- Bản ghi outbox, kết quả idempotency và lịch sử.
- Quyết định nghiệp vụ phía sau đã dùng phiên bản nào.
- Số tác động tài chính thực tế hoặc mô phỏng bên ngoài.

Có thể bổ sung kiểm thử sinh chuỗi thao tác: soạn, sửa, gửi duyệt, duyệt, thu hồi, phát hành, retry và rollback. Sau mỗi bước commit, không được xuất hiện một phiên bản có hiệu lực mà thiếu quyết định phù hợp hoặc dùng phê duyệt cho nội dung khác.

## 14. Những cách triển khai dễ biến đặc quyền thành đường tắt

| Cách triển khai | Điều còn thiếu | Hướng hoàn thiện |
| --- | --- | --- |
| Có vai trò admin thì bỏ mọi kiểm tra | Không giới hạn tác động theo hành động và đối tượng | Quyền cụ thể, phạm vi và invariant độc lập |
| Feature flag không cần duyệt vì chỉ là cấu hình | Flag có thể thay quyền hoặc bỏ quy trình | Phân loại theo tác động và kiểm soát thay đổi tương ứng |
| Cờ đã duyệt gắn với ID yêu cầu | Nội dung có thể đổi sau duyệt | Binding nội dung, phạm vi và phiên bản |
| Người sửa được tự đổi quy tắc duyệt | Đề xuất có thể tự mở quyền | Quy tắc kiểm soát nằm trong phạm vi được bảo vệ riêng |
| Direct SQL được coi là ngoại lệ mặc định | Bỏ qua sổ, quan hệ và trạng thái | Sửa chữa có kế hoạch, invariant và bằng chứng |
| Replay bằng ID mới để tránh lỗi trùng | Có thể tạo thêm tác động thật | Giữ định danh ý định và tính duy nhất nghiệp vụ |
| Log nằm cùng quyền sửa dữ liệu | Cùng chủ thể có thể sửa cả bằng chứng | Tách quyền và miền lưu theo mô hình đe dọa |
| Rollback tự động không cần đánh giá | Có thể mở lại quyền nguy hiểm | Quyết định mới có tham chiếu và điều kiện |
| Preview batch được coi là phê duyệt mọi kết quả tương lai | Tập đối tượng có thể thay đổi | Snapshot hoặc quyền tập động có giới hạn rõ |
| Outbox phát xong thì báo mọi nơi đã đổi | Consumer có thể trễ hoặc lỗi | Theo dõi phiên bản và trạng thái lan truyền phù hợp |

## 15. Bài tập tự kiểm tra

### Bài 1: người cấu hình không trực tiếp hoàn tiền

Một quản trị viên không có quyền hoàn tiền nhưng có thể tắt yêu cầu duyệt tài chính. Sau đó một luồng thông thường hoàn khoản vượt ngưỡng cũ.

**Gợi ý trả lời:** khả năng thay điều kiện cấp phép là một quyền có tác động nghiệp vụ. Cần kiểm soát việc sửa chính sách, phê duyệt độc lập khi áp dụng và truy nguyên phiên bản đã cho phép tác động. Không chỉ bảo vệ endpoint trực tiếp chuyển tiền.

### Bài 2: yêu cầu đã duyệt nhưng nội dung được sửa

Người duyệt chấp thuận thay đổi cho T1. Trước phát hành, người soạn đổi tenant đích sang T2 nhưng giữ nguyên decisionId.

**Gợi ý trả lời:** phê duyệt phải ràng buộc tenant cùng toàn bộ nội dung có ảnh hưởng. Thay phạm vi làm binding không còn phù hợp và cần xử lý lại theo workflow. Quyền phát hành cũng phải được kiểm tra trên đúng tenant đích.

### Bài 3: lệnh hoàn treo và nút ép chạy

Nhà cung cấp có thể đã hoàn tiền nhưng worker timeout. Người vận hành bấm “force retry”, công cụ tạo mã lệnh mới và gửi tiếp.

**Gợi ý trả lời:** chưa rõ kết quả không phải một quyết định cho hoàn thêm. Cần dùng mã lệnh ổn định, truy vấn hoặc retry theo hợp đồng, giữ ngân sách và đối soát. Cờ ép chạy không được bỏ tính duy nhất của tác động nghiệp vụ.

### Bài 4: một bảng audit có đủ không?

Người vận hành có thể sửa toàn bộ bảng nghiệp vụ và bảng audit trong cùng cơ sở dữ liệu. Thiết kế tuyên bố bảng audit bảo đảm mọi thay đổi đều không thể che giấu.

**Gợi ý trả lời:** tuyên bố vượt quá mô hình quyền. Nếu cùng chủ thể sửa được dữ liệu và bằng chứng, cần giới hạn quyền hoặc bằng chứng ở một ranh giới độc lập phù hợp. Cũng phải xác định rõ mức quản trị hạ tầng nào được tin; một kiểm tra nội bộ không tự bảo vệ trước mọi chủ thể kiểm soát toàn bộ môi trường.

## 16. Các điểm cần ghi nhớ

Ranh giới quản trị bảo vệ nơi đặc quyền kỹ thuật và khả năng sửa cấu hình trở thành quyền thay đổi kết quả nghiệp vụ. Tên vai trò hoặc vị trí trong mạng không đủ xác định một thao tác có được phép hay không.

Một thiết kế có thể kiểm chứng cần quyền theo hành động và đối tượng, phạm vi tenant, tách biệt nhiệm vụ, phê duyệt gắn nội dung, phiên bản bất biến và ranh giới thực thi nhất quán. Job, batch, direct SQL, quyền khẩn cấp và tác vụ replay đều phải được đặt trong mô hình đó.

Câu hỏi cốt lõi là: **Đặc quyền này cho phép tác động gì, trong phạm vi nào, dựa trên quyết định nào, và điều gì ngăn nó tự mở rộng thành quyền bỏ qua chính các quy tắc đang bảo vệ nghiệp vụ?**
