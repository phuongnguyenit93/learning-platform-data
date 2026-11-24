# Recovery reconciliation

## 1. Reconciliation giải quyết vấn đề gì?

Một luồng khôi phục tài khoản có thể đi qua dịch vụ tiếp nhận yêu cầu, xác minh danh tính, phê duyệt, quản lý credential, quản lý phiên và thông báo. Những dịch vụ này không nhất thiết cùng thay đổi trạng thái trong một transaction.

Ví dụ, dịch vụ danh tính đã đổi MFA nhưng phản hồi bị mất. Bộ điều phối vẫn ghi “đang thực thi”, còn dịch vụ phiên chưa xác nhận thu hồi các phiên bị ảnh hưởng. Nếu hệ thống coi đây là một lần recovery thất bại rồi cấp quyền thực thi mới, nó có thể thay đổi credential thêm lần nữa.

**Recovery reconciliation** là quá trình đối chiếu những sự thật có thẩm quyền của một operation recovery, xác định phần đã hoàn tất, phần chưa rõ và sai lệch cần xử lý, rồi thực hiện những hành động khắc phục được cho phép.

Mục tiêu không phải làm cho các bảng đều có cùng chuỗi trạng thái. Mục tiêu là đưa hệ thống tới trạng thái đáp ứng những bất biến bảo mật mà không tạo thêm quyền ngoài phạm vi, không làm sống lại token đã dùng và không ghi đè một credential mới bằng dữ liệu cũ.

Reconciliation thường là đường phục hồi bổ sung cho luồng xử lý trực tiếp. Nó không thay thế transaction, idempotency, outbox hoặc phân quyền tại dịch vụ thực thi.

## 2. Phân biệt đối chiếu, retry và một lần recovery mới

| Hoạt động | Ý nghĩa | Ranh giới cần giữ |
|---|---|---|
| Đối chiếu | Đọc và so sánh các kết quả đã được ghi nhận | Không tự tạo căn cứ phê duyệt mới |
| Retry | Thử lại cùng lệnh hoặc bước theo contract | Giữ định danh, nội dung và phạm vi ban đầu |
| Cập nhật bản chiếu | Làm dữ liệu quan sát phản ánh sự thật nguồn | Không biến bản chiếu thành nguồn cấp quyền |
| Khắc phục bảo mật | Thực hiện một hành động bổ sung được cho phép | Có thẩm quyền, phạm vi và dấu vết riêng |
| Recovery mới | Tạo một yêu cầu nghiệp vụ mới | Phải qua những điều kiện xác minh hiện hành |

Nếu credential đã đổi nhưng dashboard chưa cập nhật, việc cập nhật dashboard không phải đổi credential lần nữa. Nếu xử lý phiên còn thiếu, có thể cần tiếp tục operation thu hồi đã được xác định, thay vì cấp một recovery token mới.

Ngược lại, một hành động như thay lại MFA vì phát hiện gian lận là quyết định bảo mật mới. Không nên giấu nó bên trong một job “đồng bộ trạng thái” không có contract phân quyền rõ ràng.

## 3. Xác định nguồn có thẩm quyền của từng sự thật

Một reconciler cần biết dữ liệu nào được phép dùng để kết luận một bước đã xảy ra.

| Sự thật cần xác minh | Nguồn có thẩm quyền minh họa | Nguồn chưa đủ để kết luận |
|---|---|---|
| Nội dung và phiên bản yêu cầu | Kho workflow recovery | Nội dung còn mở trên trình duyệt |
| Bằng chứng đã được chấp nhận | Dịch vụ hoặc sổ quyết định xác minh | Ghi chú hỗ trợ không được xác nhận |
| Quyền thực thi đã được cấp | Nơi quản lý grant và quyết định tương ứng | Bản chiếu chỉ ghi `APPROVED` |
| Credential đã thay đổi | Kết quả operation của dịch vụ credential | Lệnh đã được gửi vào queue |
| Quyền dùng một lần đã tiêu thụ | Ledger hoặc transaction sở hữu việc tiêu thụ | Một lần request bị timeout |
| Phiên bị ảnh hưởng đã bị chặn | Cơ chế thực thi thu hồi hoặc phiên bản bảo mật theo contract | ACK rằng broker đã nhận sự kiện |
| Thông báo đã được gửi hoặc giao | Kết quả của dịch vụ thông báo theo ngữ nghĩa đã công bố | Outbox đã được tạo |

Tên các dịch vụ có thể khác nhau giữa hệ thống. Điều quan trọng là một sự thật có chủ sở hữu rõ ràng, và các thành phần khác phân biệt kết quả nguồn với những gì chúng mới quan sát được.

Nếu nguồn có thẩm quyền không khả dụng, kết quả phù hợp có thể là chưa xác định. Không dùng một bản sao thuận tiện nhưng lỗi thời để đưa ra kết luận bảo mật chắc chắn.

## 4. Những bất biến cần kiểm tra

Một thiết kế có thể bắt đầu từ các bất biến sau:

1. Mọi tác động gắn với đúng tenant, chủ thể, case, operation và nội dung đã được cho phép.
2. Một grant dùng một lần không tạo nhiều thay đổi credential ngoài phạm vi của nó.
3. Kết quả commit không bị mất chỉ vì bên điều phối không nhận được phản hồi.
4. Trạng thái hủy hoặc thu hồi không bị một sự kiện cũ làm có hiệu lực trở lại.
5. Điều kiện xử lý phiên bắt buộc được đáp ứng trước khi công bố mức hoàn tất tương ứng.
6. Proof, approval và token cũ không được mở lại để sửa một sai lệch hiển thị.
7. Hành động khắc phục có thể được truy vết và không âm thầm thay đổi lịch sử.

Không phải mọi sai lệch đều là vi phạm các bất biến này. Một thông báo đang retry trong giới hạn được chấp nhận có thể chỉ là trạng thái vận hành. Một credential đã thay nhưng phiên của kẻ tấn công còn truy cập trái yêu cầu là vấn đề bảo mật cần được ưu tiên khác.

## 5. Mô hình hóa kết quả theo từng chiều

Một boolean `recoveryCompleted` thường không đủ để đối chiếu. Nên giữ những kết quả hoặc tham chiếu riêng cho các bước quan trọng.

```text
recoveryCaseReference
caseVersion
tenantReference
securitySubjectReference
operationReference
commandDigest
authorizationReference
credentialResultReference
sessionEffectReference
notificationReference
lastObservedSourceVersions
reconciliationState
lastReconciledAt
nextReconcileAt
```

Một trạng thái đối chiếu có thể phân biệt:

- `CONSISTENT_PENDING`: chưa hoàn tất nhưng phù hợp với tiến độ dự kiến.
- `UNKNOWN_SOURCE_RESULT`: chưa lấy được kết quả có thẩm quyền cần thiết.
- `PROJECTION_LAG`: sự thật nguồn đã có nhưng bản chiếu chưa phản ánh.
- `SECURITY_EFFECT_PENDING`: còn tác động bảo mật bắt buộc chưa được xác nhận.
- `CONFLICT_REQUIRES_REVIEW`: có kết quả mâu thuẫn cần xem xét theo thẩm quyền.
- `REMEDIATION_PENDING`: có kế hoạch khắc phục được phép đang chờ thực hiện.
- `RECONCILED`: đạt điều kiện đối chiếu cho phạm vi đã xác định.

`RECONCILED` không nhất thiết là recovery thành công. Một operation bị từ chối ở nguồn, không có tác động và được phản ánh đúng ở mọi nơi vẫn có thể được đối chiếu hoàn tất với kết quả nghiệp vụ là từ chối.

## 6. Xác định operation trước khi hỏi trạng thái

Reconciler cần dùng định danh ổn định, không tìm operation bằng email hiện tại hoặc thời gian gần đúng.

Một lệnh nên được nhận diện cùng những ràng buộc như:

```text
authorityDomain
tenantReference
securitySubjectReference
operationId
action
commandDigest
requestVersion
```

`operationId` đơn lẻ không phải quyền xem kết quả. Dịch vụ tra cứu cần xác thực reconciler và kiểm tra nó được truy vấn đúng phạm vi.

Cùng idempotency key nhưng khác tài khoản, loại hành động hoặc digest phải được xem là xung đột. Không lấy một kết quả đã có rồi gắn sang case khác chỉ vì khóa giống nhau.

Với credential dùng chung nhiều tenant, cần giữ đúng miền chủ thể bảo mật. Một case thuộc tenant A có thể có tham chiếu tới operation ở dịch vụ danh tính nền tảng, nhưng điều đó không cho phép reconciler của A xem hoặc sửa những operation không liên quan của B.

## 7. Quan sát nhiều dịch vụ không tạo snapshot toàn cục

Giả sử reconciler đọc dịch vụ credential lúc T1 và dịch vụ phiên lúc T2. Giữa hai lần đọc, workflow có thể đã tiến thêm một bước. Tập kết quả nhận được chưa chắc từng cùng tồn tại tại một thời điểm.

Do đó cần giữ phiên bản nguồn, định danh kết quả và quan hệ nhân quả. Timestamp giúp đo tuổi hoặc độ trễ nhưng không đủ để suy ra thứ tự quyết định giữa các dịch vụ độc lập.

Những nguyên tắc hữu ích gồm:

- So sánh phiên bản trong đúng miền cấp phiên bản đó.
- Không so sequence của dịch vụ phiên với sequence của dịch vụ credential như cùng một bộ đếm.
- Dùng operation hoặc causation reference để nối tác động với quyết định gốc.
- Đọc lại khi kết quả có thể thay đổi và chưa đủ căn cứ cho hành động.
- Phân biệt trạng thái chưa quan sát được với trạng thái đã được nguồn xác nhận là cuối cùng.

Một operation credential có kết quả bất biến ở phiên bản bảo mật 44 vẫn là sự thật lịch sử dù tài khoản hiện đã ở phiên bản 45 do một thay đổi khác. Không thực hiện lại operation cũ chỉ vì credential hiện tại không còn giống kết quả lúc 44.

Tương tự, một mốc thu hồi mới hơn chỉ đáp ứng tác động cũ khi phạm vi và ngữ nghĩa của cơ chế bảo đảm nó bao phủ các phiên cần chặn. Không chỉ thấy một số lớn hơn rồi kết luận mọi yêu cầu đã đạt.

## 8. Phân biệt kết quả chưa rõ và thất bại chắc chắn

Timeout nghĩa là bên gọi chưa biết kết quả trong khoảng chờ. Nó không chứng minh dịch vụ nhận chưa commit.

Một phản hồi không tìm thấy operation cũng cần được hiểu theo contract. Có thể query nhầm tenant, đọc bản sao chưa cập nhật, hoặc lệnh vẫn đang trong quá trình được tiếp nhận. Chỉ khi nguồn có thẩm quyền có ngữ nghĩa đủ mạnh mới được kết luận một lệnh không được thực hiện hoặc đã bị từ chối cuối cùng.

| Quan sát | Kết luận phù hợp |
|---|---|
| HTTP timeout sau gửi lệnh | Chưa rõ kết quả; tra cứu cùng operation |
| Broker đã nhận command | Đã đạt mốc vận chuyển tương ứng, chưa chứng minh tác động |
| Nguồn xác nhận operation committed | Có thể ghi nhận tác động nguồn theo phạm vi kết quả |
| Nguồn xác nhận terminal rejected, không có tác động theo contract | Ghi nhận kết quả từ chối và đối chiếu những phần liên quan |
| Search index không có operation | Chưa đủ căn cứ nếu index không phải nguồn quyết định |
| Hết số retry tự động | Cần đổi cách xử lý vận hành; không tự suy ra chưa có tác động |

Khi chưa rõ, có thể hạn chế bước tiếp theo và chuyển sang đối soát có thời hạn hoặc can thiệp có thẩm quyền. Không chuyển sang `COMPLETED` chỉ để giải phóng một job mắc kẹt.

## 9. Ma trận sai lệch và hành động được phép

| Bộ điều phối quan sát | Nguồn thực tế | Phản ứng phù hợp |
|---|---|---|
| Đang thực thi | Credential đã commit | Ghi nhận kết quả operation; không đổi credential lần nữa |
| Đã hoàn tất | Tác động phiên bắt buộc còn chờ | Ghi sai lệch, áp dụng quy tắc giới hạn hoặc khắc phục được phép |
| Chờ sự kiện | Outbox có sự kiện chưa chuyển | Tiếp tục giao sự kiện đã lưu theo contract |
| Chưa nhận kết quả | Nguồn tạm không khả dụng | Giữ chưa xác định và lên lịch tra cứu lại |
| Token đã tiêu thụ | Thiếu liên kết tới operation | Điều tra nguồn tiêu thụ; không tự mở lại token |
| Case đã hủy | Credential có kết quả commit | Xác định thứ tự có thẩm quyền và tác động; không giả định hủy đã rollback |
| Thông báo đang chờ | Grant đã hết hạn hoặc bị thu hồi | Chặn việc gửi bí mật không còn phù hợp theo chính sách |
| Phiếu duyệt được cache là hợp lệ | Nguồn đã thu hồi hoặc khác nội dung | Không phát hành quyền mới từ bản chiếu cũ |

Nếu một trạng thái `COMPLETED` đã được ghi sai, có thể cần cập nhật bản chiếu thành trạng thái thể hiện còn việc bảo mật phải hoàn tất, đồng thời thêm sự kiện đính chính hoặc phát hiện sai lệch. Không sửa sự kiện lịch sử để che việc đã công bố hoàn tất quá sớm.

Hành động tiếp tục thu hồi phiên hoặc giới hạn truy cập phải dựa trên chính sách và thẩm quyền cụ thể. Reconciler không mặc nhiên được khóa mọi tài khoản chỉ vì một nguồn chậm phản hồi.

## 10. Lập kế hoạch khắc phục có phạm vi

Tách phát hiện khỏi thực thi giúp kiểm soát những gì automation được phép làm. Một kế hoạch có thể chứa:

```text
reconciliationPlanId
reconciliationRunId
caseReference
operationReference
observationReferences
observedSourceVersions
discrepancyCode
allowedAction
targetEffectReference
expectedWorkflowVersion
actionDigest
policyVersion
approvalReference
expiresAt
```

Các hành động tự động có thể bao gồm cập nhật bản chiếu từ kết quả nguồn, thử giao lại một sự kiện đã lưu hoặc retry một tác động đã được cho phép với cùng định danh. Phạm vi phải được xác định từ operation gốc và chính sách, không từ một trường target tùy ý do client gửi.

Những thay đổi như cấp grant mới, thay lại credential, nới điều kiện proofing hoặc chuyển tài khoản đích thường không phải đồng bộ kỹ thuật đơn thuần. Chúng cần quy trình nghiệp vụ và thẩm quyền tương ứng.

Một kế hoạch phải hết hiệu lực hoặc được đánh giá lại khi các điều kiện liên quan thay đổi. Nếu target hoặc nội dung tác động đổi, không dùng lại approval cũ bằng cách chỉ sửa payload bên dưới.

## 11. Pseudocode cho một lượt đối chiếu

Ví dụ sau minh họa cách giữ ranh giới giữa đọc nguồn, phân loại và ghi kế hoạch. Nó không phải một transaction toàn cục:

```java
ReconcileOutcome reconcile(WorkflowReference reference) {
    WorkflowView workflow = workflows.loadAuthorized(reference);
    SourceObservations observations = sourceReader.readRequiredAuthorities(
        workflow.boundOperationReferences());

    ReconciliationDecision decision = classifier.classify(
        workflow, observations, policies.currentRulesFor(workflow));

    return localTransaction.run(() -> {
        Workflow current = workflows.lockForUpdate(reference);
        if (current.version() != workflow.version()) {
            return ReconcileOutcome.reobserve();
        }

        ObservationRecord record = observationsRepository.append(
            current.reference(), observations, decision);

        if (!decision.hasEnoughEvidenceForAction()) {
            current.recordUnresolvedObservation(record.reference());
            schedules.planNextObservation(current.reference(), decision.retryClass());
            return ReconcileOutcome.unresolved();
        }

        projections.applyAuthoritativeFactsOnly(current, decision);

        if (decision.hasPermittedRemediation()) {
            RemediationPlan plan = planner.bindToCurrentOperation(
                current, record, decision);
            remediationPlans.insertIfAbsent(plan.effectKey(), plan);
            outbox.recordRemediationPlanned(plan);
        }

        audit.recordReconciliationDecision(current, record, decision);
        return ReconcileOutcome.recorded(decision.classification());
    });
}
```

Khóa workflow cục bộ ngăn hai lượt ghi cùng một bản chiếu theo phiên bản cũ. Nó không khóa trạng thái ở dịch vụ credential hoặc dịch vụ phiên. Executor của kế hoạch phải kiểm tra lại những điều kiện hiện hành mà contract yêu cầu tại nơi thực hiện tác động.

`effectKey` cần được thiết kế để nhận diện cùng tác động của cùng operation, có ràng buộc duy nhất phù hợp. Hai lượt quét phát hiện cùng sai lệch không được tạo hai lệnh thay đổi độc lập chỉ vì `reconciliationRunId` khác nhau.

Không giữ transaction cục bộ mở trong suốt những lời gọi mạng tới các nguồn. Các quan sát có phiên bản và kiểm tra lại giúp tránh kéo dài khóa, nhưng không được mô tả như một snapshot nguyên tử xuyên dịch vụ.

## 12. Retry an toàn và kết quả tác động có thể tra cứu

Một executor retry cần giữ cùng operation hoặc effect reference, cùng phạm vi và cùng digest. Nếu nguồn đã có kết quả, nó nhận lại kết quả đó theo quyền, thay vì tạo tác động mới.

Khi retry tác động thu hồi phiên, cần biết tập phiên hoặc thế hệ cần xử lý. Không đổi một lệnh thu hồi có phạm vi thành thu hồi toàn bộ tài khoản mà không có chính sách cho phép.

Khi giao lại outbox, gửi lại sự kiện logic đã lưu với event ID ổn định. Không tự tạo một sự kiện mới nói credential vừa thay đổi nếu reconciler chỉ vừa phát hiện một thay đổi cũ. Nếu cần backfill hoặc sửa lịch sử thiếu, phải dùng cơ chế có thẩm quyền, nêu rõ nguồn và thời điểm ghi nhận bổ sung.

Consumer cũng cần khử trùng và kiểm soát thứ tự theo contract. Việc reconciler đã dùng idempotency key ở phía gửi không tự bảo đảm hệ thống đích xử lý đúng.

Một kết quả operation đã commit có thể được tra cứu mà không tiêu thụ lại grant. Tuy nhiên, truy vấn kết quả vẫn phải được phân quyền và không được dùng việc biết operation ID như quyền truy cập. Điều kiện xem kết quả khác với điều kiện thực thi một thay đổi mới.

## 13. Không mở lại token hoặc rollback credential để làm trạng thái khớp

Nếu grant đã tiêu thụ nhưng bộ điều phối còn ghi “chưa thực thi”, hành động đầu tiên là tìm kết quả có thẩm quyền. Không đặt `usedAt` về rỗng để cho luồng chạy lại.

Nếu credential đã đổi nhưng thông báo lỗi, không khôi phục mật khẩu hoặc MFA cũ chỉ để trả hệ thống về trạng thái trước. Credential cũ có thể đã bị lộ, còn phiên cũ có thể thuộc kẻ tấn công.

Các hành động khắc phục thường cần tiến về một trạng thái an toàn mới:

```text
Credential đã thay đổi có căn cứ
    + tác động phiên còn thiếu
    → ghi nhận kết quả nguồn
    → tiếp tục tác động phiên được phép
    → áp dụng giới hạn theo chính sách khi cần
    → xác nhận những điều kiện hoàn tất còn lại
```

Nếu phát hiện quyết định ban đầu không hợp lệ, cần xử lý như sự kiện bảo mật mới. Có thể cần thu hồi quyền, tạm hạn chế thao tác hoặc xác minh lại bằng quy trình được phép. Không xóa bản ghi commit để tạo cảm giác hành động chưa từng xảy ra.

Hủy một case sau commit cũng không tự hoàn tác tác động. Reconciler phải xác định trạng thái thực và cơ chế xử lý tiếp, thay vì lấy thời gian nhận sự kiện hủy làm căn cứ duy nhất.

## 14. Chạy định kỳ, theo sự kiện và theo phạm vi

Reconciliation có thể được kích hoạt bởi event timeout, một operation mắc kẹt, cảnh báo sai lệch hoặc lịch quét định kỳ. Nhiều đường kích hoạt có thể cùng tìm thấy một trường hợp, nên thiết kế phải chịu được giao trùng.

Một lượt quét cần có checkpoint hoặc cursor và phạm vi tenant rõ. Không giả định quét hết một bảng là đã nhìn thấy một snapshot nhất quán của toàn hệ thống; trạng thái vẫn thay đổi trong lúc quét.

Các lựa chọn vận hành có thể gồm:

- Ưu tiên những trường hợp còn tác động bảo mật bắt buộc chưa rõ.
- Chia lô và giới hạn mức song song theo khả năng của nguồn.
- Backoff và jitter khi nguồn lỗi, tránh retry đồng loạt.
- Đặt lịch quan sát tiếp dựa trên loại trạng thái, không chỉ một khoảng cố định.
- Có ngưỡng chuyển người có thẩm quyền khi không thể tự kết luận.

Tuổi của operation là tín hiệu để xem xét, không phải căn cứ cấp quyền. Một job quá hạn không có nghĩa được bỏ qua proof hết hạn hoặc tự gia hạn approval.

Lease có thể giúp tránh nhiều worker cùng xử lý một case, nhưng lease hết hạn không chứng minh worker cũ đã dừng. Việc ghi kế hoạch và thực hiện tác động vẫn cần phiên bản, idempotency hoặc fencing theo ranh giới tương ứng.

## 15. Quyền của reconciler và bảo vệ tenant

Reconciler thường cần đọc nhiều nguồn, nên tài khoản dịch vụ của nó có thể trở thành mục tiêu có giá trị. Cần phân tách quyền quan sát, quyền lập kế hoạch và quyền thực hiện những loại khắc phục cụ thể.

Ví dụ, quyền tra cứu kết quả credential không nên đồng nghĩa quyền đặt lại credential tùy ý. Một executor được retry operation thu hồi phiên đã có cũng không nên nhận một payload bất kỳ rồi thu hồi bất kỳ tenant nào.

Những tham chiếu tenant, chủ thể và operation phải được kiểm tra tại cả nguồn đọc và nơi nhận tác động. Không dựa vào việc queue được gọi là nội bộ để bỏ qua phạm vi.

Quyền hỗ trợ xem một case cũng không tự cấp quyền xem toàn bộ bằng chứng định danh hoặc membership ở tenant khác. Các bản ghi quan sát nên lưu tối thiểu dữ liệu cần thiết, dùng tham chiếu được bảo vệ khi phù hợp.

Không lưu raw recovery token, mật khẩu, secret MFA, recovery code hoặc cookie trong hồ sơ đối chiếu. Một hash của bí mật có không gian nhỏ cũng không tự trở thành dữ liệu an toàn để công khai trong log.

## 16. Audit, đính chính và quan sát chất lượng

Một quyết định reconciliation cần giải thích được đã đọc những nguồn nào, phiên bản nào, phân loại gì và hành động nào được chọn.

Các sự kiện có thể phân biệt:

```text
RECOVERY_RECONCILIATION_STARTED
RECOVERY_AUTHORITATIVE_RESULT_OBSERVED
RECOVERY_STATE_DISCREPANCY_DETECTED
RECOVERY_REMEDIATION_PLANNED
RECOVERY_REMEDIATION_APPLIED
RECOVERY_RECONCILIATION_UNRESOLVED
RECOVERY_RECONCILIATION_COMPLETED
```

`AUTHORITATIVE_RESULT_OBSERVED` có thể ghi thời điểm quan sát và tham chiếu thời điểm commit gốc. Không mô tả việc vừa nhìn thấy một commit cũ thành một commit mới.

Nếu cần sửa trạng thái đã công bố sai, audit nên giữ cả phát hiện và đính chính. Các sự kiện lịch sử không bị viết lại để làm mất dấu vết của khoảng thời gian hệ thống hiển thị hoặc xử lý sai.

Những chỉ số hữu ích gồm số operation chưa rõ kết quả, tuổi của tác động bảo mật còn chờ, số lần đối chiếu lại, tỷ lệ xung đột phiên bản và backlog kế hoạch khắc phục. Không chỉ đo số job được đánh dấu hoàn tất, vì chỉ số đó có thể che việc đóng sai những trường hợp chưa được giải quyết.

Một nguồn lỗi hàng loạt cần được xử lý như vấn đề hệ thống, tránh tạo hàng nghìn lần can thiệp trùng. Ngược lại, việc nguồn đã hoạt động trở lại không tự chứng minh mọi operation mắc kẹt đều đã được đối chiếu xong.

## 17. Tình huống tổng hợp: thay MFA đã commit nhưng còn thiếu xử lý phiên

Người dùng mất thiết bị MFA và hoàn tất một case recovery. Operation R được cho phép đăng ký lại yếu tố theo đúng phiên bản đề xuất. Dịch vụ credential commit thay đổi, lưu kết quả R và tạo sự kiện trong outbox. Phản hồi tới bộ điều phối bị mất.

Lúc đầu, workflow vẫn ghi đang thực thi. Reconciler tìm R bằng tenant, chủ thể và operation reference gốc. Nguồn credential trả kết quả commit ở phiên bản bảo mật 44. Reconciler ghi nhận kết quả đó mà không yêu cầu đổi MFA lần nữa.

Nó tiếp tục tra cứu tác động phiên đã được kế hoạch gốc yêu cầu. Dịch vụ phiên mới chỉ ghi nhận lệnh, chưa xác nhận điều kiện hoàn tất. Trạng thái phù hợp là còn tác động bảo mật chờ, không phải toàn bộ recovery đã thất bại và cũng chưa phải hoàn tất theo tiêu chí yêu cầu.

Nếu sự kiện vẫn ở outbox, cơ chế giao tiếp tục chuyển chính sự kiện đó. Nếu cần retry operation phiên, executor dùng cùng định danh tác động và phạm vi đã được cho phép, kiểm tra lại những điều kiện hiện hành theo contract.

Trong lúc này, tài khoản có một thay đổi hợp lệ khác đưa phiên bản lên 45. Reconciler không ghi lại credential của R để ép tài khoản trở về 44. Nó đối chiếu kết quả lịch sử của R và xác định tác động phiên cần thiết có được trạng thái mới bao phủ hay còn thiếu theo đúng ngữ nghĩa.

Khi đủ căn cứ về credential và các điều kiện phiên bắt buộc, workflow được cập nhật theo sự thật đã xác nhận. Email có thể vẫn retry riêng nếu chính sách cho phép; retry email không mở lại grant và không gửi một liên kết recovery đã hết hiệu lực.

## 18. Những lỗi đối chiếu thường gặp

| Lỗi | Rủi ro | Hướng xử lý phù hợp |
|---|---|---|
| Timeout được coi là chưa thực thi | Cấp thêm quyền và thay credential lần hai | Tra cứu cùng operation tại nguồn |
| Đặt mọi bảng thành completed | Che phần bảo mật chưa hoàn tất | Đối chiếu theo từng bất biến và thành phần |
| Mở lại token đã dùng để retry | Quyền dùng một lần được phát lại | Giữ ledger và tìm kết quả có thẩm quyền |
| Current credential khác kết quả cũ nên ghi lại | Ghi đè một thay đổi hợp lệ mới hơn | Giữ kết quả lịch sử, kiểm tra phiên bản và mục đích |
| Không tìm thấy ở index là chắc chắn không commit | Kết luận từ bản sao chậm hoặc sai phạm vi | Dùng contract của nguồn quyết định |
| Replay event với ID mới như một commit mới | Consumer hiểu nhầm có thêm tác động | Giữ định danh sự kiện và nguồn gốc kết quả |
| Tự tạo approval để sửa sai lệch | Reconciler trở thành đường cấp quyền | Chỉ khắc phục trong thẩm quyền được định nghĩa |
| Hủy case được coi là rollback mọi tác động | Bỏ sót credential hoặc phiên đã thay đổi | Xác định thứ tự và xử lý hậu quả thực tế |
| So timestamp giữa dịch vụ để quyết định ai đúng | Sai khi clock lệch hoặc quan sát không đồng thời | Kết hợp phiên bản, kết quả nguồn và quan hệ nhân quả |
| Hết retry thì đóng thành công | Mất dấu operation chưa rõ | Giữ trạng thái chưa giải quyết và chuyển tuyến phù hợp |

Recovery reconciliation an toàn dựa trên sự thật có thẩm quyền, nhận diện operation ổn định và hành động khắc phục có giới hạn. Nó giúp hệ thống hoàn tất những phần còn thiếu sau timeout hoặc giao sự kiện lỗi mà không biến việc sửa trạng thái thành một lần cấp lại quyền khôi phục tài khoản ngoài ý định.
