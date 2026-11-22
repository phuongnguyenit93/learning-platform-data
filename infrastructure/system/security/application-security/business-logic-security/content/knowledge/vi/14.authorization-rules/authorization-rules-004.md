# Contextual authorization — Cấp quyền theo ngữ cảnh nghiệp vụ

## 1. Vì sao có role vẫn chưa đủ?

Giả sử một nhân viên có role xử lý hoàn tiền. Role đó không có nghĩa người này được hoàn bất kỳ giao dịch nào, với bất kỳ số tiền nào, vào bất kỳ thời điểm nào.

Một yêu cầu hoàn tiền còn phụ thuộc vào nhiều điều kiện:

- Giao dịch thuộc tenant và đơn vị mà nhân viên được giao phụ trách hay không?
- Khoản thanh toán đã được ghi nhận thành công chưa?
- Số tiền đề nghị có vượt phần còn được hoàn và hạn mức của người thao tác không?
- Người thao tác có đang tự xử lý một giao dịch mà chính sách yêu cầu người độc lập kiểm tra không?
- Bằng chứng xác thực tăng cường có còn đủ mới không?
- Tín hiệu rủi ro có đủ tin cậy và còn phù hợp với đúng nội dung yêu cầu không?
- Trong lúc chờ xử lý, quyền hoặc trạng thái giao dịch có thay đổi không?

**Contextual authorization** là việc đánh giá quyền thực hiện một hành động bằng ngữ cảnh đáng tin cậy tại điểm cấp quyền, thay vì chỉ dựa vào một role hoặc một quyết định đã được tính từ trước.

Trong bảo vệ logic nghiệp vụ, cách tiếp cận này giúp ngăn việc dùng một quyền hợp lệ trong sai đối tượng, sai trạng thái, sai phạm vi, sai thời điểm hoặc sai điều kiện thực hiện.

## 2. Mô hình quyết định: chủ thể, hành động, đối tượng và môi trường

Một mô hình dễ sử dụng là:

```text
decision = authorize(subject, action, resource, environment, policy)
```

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Chủ thể | Ai đang yêu cầu và hành động thay cho ai? | Nhân viên, dịch vụ gọi thay, quan hệ ủy nhiệm |
| Hành động | Ý định nghiệp vụ chính xác là gì? | `REFUND_REQUEST`, `REFUND_APPROVE`, `REFUND_EXECUTE` |
| Đối tượng | Hành động tác động lên dữ liệu nào? | Payment, tài khoản, hồ sơ hoặc đơn hàng |
| Môi trường | Điều kiện đáng tin cậy tại lúc kiểm tra là gì? | Thời gian server, mức xác thực, tín hiệu rủi ro, kênh truy cập |
| Chính sách | Những điều kiện và nghĩa vụ nào áp dụng? | Phạm vi đơn vị, hạn mức, phân tách nhiệm vụ, audit bắt buộc |

Không phải mọi thuộc tính đều cần cho mọi hành động. Mục tiêu là chọn đủ điều kiện có ý nghĩa nghiệp vụ và xác định rõ nguồn của chúng, không phải gom thật nhiều thông tin rồi viết một biểu thức khó kiểm soát.

### 2.1. Quan hệ với RBAC, ABAC và quyền theo quan hệ

Các cách mô hình hóa có thể bổ sung cho nhau:

- RBAC cho biết chủ thể có nhóm năng lực nào, chẳng hạn nhân viên hoàn tiền.
- Thuộc tính giúp giới hạn theo số tiền, đơn vị, thời gian hoặc trạng thái giao dịch.
- Quan hệ giúp xác định chủ thể có được giao xử lý đối tượng này hay không.
- Quy tắc nghiệp vụ quyết định hành động có hợp lệ trong tình trạng hiện tại không.

Contextual authorization thường kết hợp các nguồn đó. Đổi tên một role thành `ADMIN` không giải quyết được quyền theo đối tượng hoặc điều kiện trạng thái.

### 2.2. Quyền và bất biến nghiệp vụ phải cùng được bảo vệ

“Người này được phép yêu cầu hoàn tiền” và “giao dịch này còn đủ số tiền để hoàn” là hai điều kiện khác nhau. Cả hai phải đúng khi hệ thống nhận nghĩa vụ hoàn tiền.

Có thể tách chúng thành các thành phần code để dễ hiểu, nhưng không được tách thành một lần kiểm tra cũ và một lần ghi dữ liệu không còn được bảo vệ trước thay đổi đồng thời.

## 3. Ví dụ xuyên suốt: nhận yêu cầu hoàn tiền thủ công

Xét nghiệp vụ hoàn tiền cho một payment đã thu thành công. Server luôn hoàn về phương thức gốc theo hợp đồng ví dụ; client không được chỉ định một tài khoản nhận tùy ý.

Chính sách minh họa:

1. Chủ thể phải còn hoạt động và có quyền yêu cầu hoàn tiền trong đơn vị sở hữu payment.
2. Tenant của payment phải nằm trong phạm vi đã xác thực.
3. Payment phải ở trạng thái đã thu thành công, trong ví dụ gọi là `SETTLED`.
4. Số tiền phải dương, đúng tiền tệ, không vượt hạn mức từng lệnh của chủ thể.
5. Tổng tiền đã hoàn cộng tiền đang được nhận xử lý không được vượt khoản được phép hoàn.
6. Nếu thuộc trường hợp cần độc lập, chủ thể không được là người có xung đột nhiệm vụ.
7. Phải có bằng chứng xác thực tăng cường đáp ứng chính sách và còn đủ mới.
8. Bằng chứng rủi ro bắt buộc phải đúng nội dung, đúng đối tượng, còn hạn và có nguồn hợp lệ.
9. Nhận yêu cầu phải giữ chỗ số tiền hoàn, ghi audit và tạo lệnh bền vững trong cùng transaction.

Các ngưỡng thời gian hoặc mức tiền cụ thể thuộc cấu hình chính sách của hệ thống. Không lấy các con số trong ví dụ làm chuẩn chung cho mọi dịch vụ.

Một biểu thức tổng quát:

```text
được_nhận_hoàn =
    danh_tính_hợp_lệ
    AND có_quyền_trên_payment
    AND đúng_phạm_vi_tenant_và_đơn_vị
    AND trạng_thái_cho_phép
    AND số_tiền_và_tiền_tệ_hợp_lệ
    AND còn_ngân_sách_hoàn
    AND thỏa_phân_tách_nhiệm_vụ
    AND xác_thực_đủ_mạnh_và_đủ_mới
    AND bằng_chứng_rủi_ro_còn_dùng_được
```

Đây là chính sách của ví dụ, chưa phải biểu thức có thể sao chép nguyên vẹn cho mọi nghiệp vụ hoàn tiền.

## 4. Nguồn gốc của ngữ cảnh quan trọng hơn tên thuộc tính

Một request có thể gửi `trusted=true`, `role=finance` hoặc `risk=low`. Các trường đó không trở thành ngữ cảnh đáng tin cậy chỉ vì có tên giống dữ liệu bảo mật.

| Thuộc tính | Nguồn phù hợp | Nguồn không đủ tin cậy để tự cấp quyền |
| --- | --- | --- |
| Danh tính và tenant | Kết quả xác thực đã được server kiểm tra | `actorId`, `tenantId` tùy ý trong body |
| Quyền hiệu lực | Nguồn cấp quyền và quan hệ được hệ thống tin cậy | Danh sách role do client tự khai |
| Đơn vị sở hữu payment | Dữ liệu nghiệp vụ có thẩm quyền | `departmentId` gửi kèm để được chọn policy nhẹ hơn |
| Trạng thái và số tiền còn được hoàn | Dữ liệu hiện tại được đọc theo giao thức transaction | Snapshot trên trình duyệt |
| Thời điểm kiểm tra | Nguồn thời gian server được chọn rõ ràng | Đồng hồ hoặc timestamp do client gửi |
| Mức và thời điểm xác thực | Bằng chứng xác thực đã được kiểm tra ngữ nghĩa | Header `X-MFA: true` do client đặt |
| Kết quả rủi ro | Dịch vụ đánh giá được tin cậy, ràng buộc đúng input | Một giá trị `riskScore` trong request |
| Kênh truy cập | Ngữ cảnh kết nối hoặc định tuyến đã được xác thực | Header tùy ý như `X-Trusted-Channel` |

Với mỗi thuộc tính quan trọng, nên xác định được:

```text
giá_trị
nguồn_phát_hành
phạm_vi_áp_dụng
thời_điểm_đánh_giá
hạn_sử_dụng
phiên_bản_dữ_liệu_hoặc_chính_sách
cơ_chế_kiểm_tra_tính_toàn_vẹn
```

Nếu một thuộc tính bắt buộc không có hoặc không xác định được nguồn, không nên suy diễn một giá trị thuận lợi để tiếp tục cho phép.

### 4.1. Proxy và header mạng

Địa chỉ IP hoặc thông tin kết nối chỉ có ý nghĩa khi server hiểu rõ đường đi qua proxy. Cần phân biệt metadata do proxy được tin cậy cung cấp với header mà client có thể tự gửi.

Một hệ thống có thể yêu cầu truy cập từ một kênh quản trị được bảo vệ như điều kiện bổ sung. Điều kiện đó không thay thế xác thực người dùng, quyền trên payment và các bất biến tiền tệ.

### 4.2. Không để ngữ cảnh được xác thực cho một đối tượng dùng cho đối tượng khác

Kết quả rủi ro cho payment A không cấp quyền với payment B. Bằng chứng xác thực hoặc phê duyệt cho số tiền nhỏ cũng không mặc nhiên cho phép số tiền lớn hơn.

Các chứng cứ có phạm vi hẹp cần ràng buộc với những dữ liệu quyết định ý nghĩa: hành động, tenant, đối tượng, chủ thể, số tiền, tiền tệ và phiên bản nội dung theo chính sách.

## 5. Mô hình kết quả: cho phép, từ chối và chưa xác định

Một bộ đánh giá nên phân biệt ít nhất:

| Kết quả | Ý nghĩa | Hành vi của đường thực thi |
| --- | --- | --- |
| `PERMIT` | Đã đáp ứng các điều kiện được yêu cầu | Chỉ thực hiện nếu các nghĩa vụ bắt buộc cũng được bảo đảm |
| `DENY` | Có điều kiện rõ ràng không thỏa | Không tạo hiệu ứng nghiệp vụ |
| `INDETERMINATE` | Không thể đánh giá đủ vì thiếu, lỗi hoặc bằng chứng không dùng được | Không thực thi hành động cần điều kiện đó; trả lỗi phù hợp |

Thiếu kết quả rủi ro không tương đương rủi ro thấp. Timeout khi lấy quyền không tương đương còn quyền. Một loại hành động chưa có rule không được tự rơi vào nhánh cho phép.

Nếu có nhiều rule, phải xác định cách kết hợp rõ ràng. Ví dụ có thể yêu cầu mọi điều kiện bắt buộc đều đạt và mọi điều kiện cấm đều không xuất hiện. Không giả định mọi thư viện policy đều có cùng cách xử lý khi một rule cho phép nhưng rule khác từ chối.

### 5.1. Nghĩa vụ đi kèm quyết định

Một quyết định có thể đòi hỏi:

- Giữ chỗ số tiền hoàn trong cùng transaction.
- Ghi audit bắt buộc với bằng chứng đã dùng.
- Chỉ xuất các trường dữ liệu được phép đọc.
- Phải đi qua phê duyệt độc lập trước khi thực thi.

Những yêu cầu này phải được đường thực thi hiểu và thực hiện. Nếu không hỗ trợ một nghĩa vụ bắt buộc, không thể coi `PERMIT` là cho phép bỏ qua nghĩa vụ đó.

Với yêu cầu xác thực tăng cường, thường cần lấy thêm bằng chứng rồi đánh giá lại. Không trả `PERMIT` chỉ vì đã gửi một thông báo yêu cầu xác thực nhưng người dùng chưa hoàn tất.

## 6. Xác thực đủ mới khác với token mới được cấp

Một access token vừa được làm mới không chứng minh người dùng vừa thực hiện xác thực tăng cường. Cần dựa trên bằng chứng và ngữ nghĩa của hệ thống xác thực, không chỉ thời điểm phát hành token.

Ví dụ chính sách yêu cầu một phương thức xác thực đủ mạnh được thực hiện trong khoảng thời gian gần đây. Điều kiện có thể có dạng:

```text
phương_thức_xác_thực_thỏa_chính_sách
AND authn_time <= checked_at
AND checked_at - authn_time <= max_authn_age
```

Server phải kiểm tra nguồn và cách diễn giải bằng chứng. Một tên phương thức hoặc mức bảo đảm trong claim chỉ có ý nghĩa theo hợp đồng với bên phát hành đã được cấu hình tin cậy.

Nếu thời điểm xác thực nằm trong tương lai ngoài giới hạn sai lệch cho phép, không được coi tuổi xác thực âm là bằng chứng rất mới. Cần xử lý như dữ liệu không hợp lệ hoặc chưa xác định theo chính sách.

Độ mới cũng cần kiểm tra ở đúng điểm nhận hành động. Người dùng có thể hoàn tất xác thực rồi để màn hình mở rất lâu; UI vẫn hiện biểu tượng đã xác thực không giữ quyền mãi.

## 7. Thời điểm quyết định và tính nhất quán

### 7.1. Đừng kiểm tra một ngữ cảnh rồi ghi trên ngữ cảnh khác

Một cuộc đua đơn giản:

```text
T1 đọc payment còn được hoàn 1 triệu.
T2 nhận một khoản hoàn khác, giữ hết 1 triệu.
T1 dùng kết quả cũ để nhận thêm 1 triệu.
```

Người dùng có quyền hợp lệ ở cả hai request, nhưng bất biến tài chính bị phá. Contextual authorization không giải quyết concurrency nếu dữ liệu và quyền không được bảo vệ tại lúc nhận hiệu ứng.

Một cuộc đua khác:

```text
T1 kiểm tra nhân viên thuộc đơn vị A.
T2 chuyển payment sang đơn vị B hoặc thu hồi phạm vi quyền.
T1 vẫn ghi thay đổi dựa trên kết quả cũ.
```

Cần xác định phần ngữ cảnh nào được giữ ổn định bằng transaction, khóa, phiên bản hoặc giao thức kiểm tra lại.

### 7.2. Điểm cấp quyền phải được định nghĩa

Trong ví dụ của bài, quyền được đánh giá tại một gate cục bộ: sau khi khóa trạng thái cấp quyền và payment, service lấy thời gian kiểm tra mới, đánh giá policy và nhận yêu cầu trong cùng transaction.

Nếu transaction commit thành công, một refund command bền vững được tạo. Nếu transaction thất bại, không có lần nhận hoàn tiền thành công.

Đây không phải cam kết rằng mọi thuộc tính tiếp tục đúng mãi về sau. Cần định nghĩa command đã được nhận được phép tiếp tục trong điều kiện nào, có deadline riêng hay phải đánh giá lại trước dispatch.

### 7.3. Ngữ cảnh từ hệ thống ngoài có giới hạn nhất quán

Một annotation transaction không làm cơ sở dữ liệu nghiệp vụ, IAM và dịch vụ rủi ro trở thành một transaction chung.

Với mỗi nguồn ngoài, cần chọn rõ:

- Snapshot đã xác thực nào được chấp nhận và trong bao lâu.
- Những trường nào phải khớp dữ liệu hiện tại.
- Thay đổi hoặc thu hồi có độ trễ tối đa theo hợp đồng nào.
- Khi không đáp ứng được giới hạn đó thì từ chối hay chuyển bước xác minh khác.

Nếu yêu cầu bắt buộc thu hồi quyền có hiệu lực tức thời tại mọi điểm thực thi, một role cũ trong token tự chứa không tự đáp ứng yêu cầu ấy. Phải có cơ chế cấp quyền và thu hồi phù hợp với mức bảo đảm mong muốn.

## 8. Chuẩn bị ngữ cảnh mà không giữ transaction qua lời gọi mạng

Một quy trình thực tế có thể tách thành hai giai đoạn:

```text
Trước transaction:
  lấy hoặc chuẩn bị bằng chứng rủi ro từ nguồn được tin cậy
  kiểm tra nguồn phát hành và lưu bằng chứng bất biến nếu cần

Trong transaction:
  khóa dữ liệu quyền và đối tượng theo thứ tự thống nhất
  đọc dữ liệu hiện tại
  kiểm tra bằng chứng vẫn khớp input và còn hiệu lực
  đánh giá policy
  nhận hiệu ứng, ghi audit và outbox
```

Nếu payment thay đổi sau khi đánh giá rủi ro, bằng chứng cũ có thể không còn dùng được. Server phải yêu cầu đánh giá lại thay vì giữ kết quả “rủi ro thấp” cho một nội dung khác.

Một bằng chứng rủi ro minh họa:

```text
RiskEvidence = {
    evidence_id,
    issuer,
    tenant_id,
    subject_id,
    action,
    payment_id,
    input_digest,
    evaluated_at,
    not_after,
    assessment,
    assessment_revision
}
```

`input_digest` do server tính từ dữ liệu canonical cần bảo vệ. Nếu thời hạn của bằng chứng hoặc hạn tuổi dữ liệu không còn thỏa tại gate, bằng chứng phải bị từ chối dù chữ ký vẫn đúng.

Kết quả rủi ro là một đầu vào của quyết định, không phải một quyền tổng quát có thể thay thế tenant, quan hệ đối tượng hoặc hạn mức.

## 9. Ví dụ Java: nhận hoàn tiền bằng ngữ cảnh đáng tin cậy

### 9.1. Giả định

Ví dụ dùng Spring transaction và một cơ sở dữ liệu chung cho dữ liệu cấp quyền cục bộ, payment, refund command, audit và outbox.

- Mọi thay đổi quyền cục bộ của chủ thể tuân theo giao thức khóa tương ứng.
- Mọi thao tác nhận hoặc thay đổi số tiền hoàn của payment khóa cùng bản ghi payment.
- Thứ tự khóa nhất quán là quyền chủ thể trước, payment sau; các đường liên quan phải tuân thủ để giảm nguy cơ deadlock.
- Risk evidence đã được lấy và xác thực trước; trong transaction chỉ kiểm tra bản bất biến và mức phù hợp hiện tại.
- Ví dụ có hạn mức từng lệnh và ngân sách hoàn của payment; chưa triển khai hạn mức tổng theo ngày.
- Số tiền dùng đơn vị nhỏ nhất cùng mã tiền tệ, không dùng số thực nhị phân để so sánh hạn mức.

### 9.2. Trình tự xử lý

```text
BEGIN
  1. Khóa trạng thái cấp quyền cục bộ của chủ thể.
  2. Khóa payment trong tenant.
  3. Kiểm tra quyền đọc lại kết quả của request thuộc phạm vi này.
  4. Nếu có idempotency thành công cùng nội dung: trả biên nhận cũ.
  5. Kiểm tra version và dựng ngữ cảnh từ dữ liệu hiện tại.
  6. Lấy thời điểm gate và đánh giá policy.
  7. Nếu cho phép và hỗ trợ đủ nghĩa vụ:
       giữ chỗ số tiền hoàn
       tạo refund command
       ghi audit, outbox và biên nhận idempotency
COMMIT
```

### 9.3. Service minh họa

Các repository, policy và kiểu dữ liệu trong ví dụ cần được triển khai cho hệ thống cụ thể. Constructor injection được lược bỏ; đây không phải ứng dụng hoàn chỉnh có thể chạy độc lập.

```java
@Service
public class ContextualRefundService {
    private final SubjectAuthorizationRepository authorizations;
    private final PaymentRepository payments;
    private final RiskEvidenceRepository riskEvidence;
    private final RefundRepository refunds;
    private final IdempotencyRepository idempotency;
    private final DatabaseTimeSource databaseTime;
    private final RefundContextFactory contexts;
    private final RefundAuthorizationPolicy policy;
    private final RefundObligationSupport obligations;
    private final WorkflowAuditRepository audits;
    private final OutboxRepository outbox;
    private final CommandFingerprint fingerprints;

    @Transactional(rollbackFor = Exception.class)
    public RefundReceipt requestRefund(
            VerifiedActor actor,
            RequestRefundCommand command) {

        actor.requireAuthenticated();
        command.validateSyntaxAndLimits();

        SubjectAuthorization authorization =
                authorizations.lockForUpdate(
                        actor.tenantId(), actor.canonicalSubjectId());

        Payment payment = payments.lockForUpdate(
                actor.tenantId(), command.paymentId())
            .orElseThrow(PaymentNotFoundException::new);

        // Quyền đọc biên nhận hiện tại khác với việc cấp quyền
        // nhận một khoản hoàn mới. Cả hai đều kiểm tra theo đối tượng.
        policy.requireReceiptAccess(actor, authorization, payment);

        CommandScope scope = new CommandScope(
                actor.tenantId(), payment.id(),
                actor.canonicalSubjectId(),
                "REQUEST_REFUND", command.idempotencyKey());
        String fingerprint = fingerprints.forRefund(command);

        var previous = idempotency.find(scope);
        if (previous.isPresent()) {
            if (!previous.get().fingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException();
            }
            return previous.get().receipt();
        }

        if (payment.version() != command.expectedVersion()) {
            throw new StalePaymentVersionException();
        }

        RiskEvidence evidence = riskEvidence.loadImmutable(
                command.riskEvidenceId());

        // Lấy thời gian sau khi đã qua các điểm chờ khóa cần thiết.
        Instant checkedAt = databaseTime.currentInstant();

        RefundContext context = contexts.fromTrustedSources(
                actor, authorization, payment,
                command, evidence, checkedAt);

        AuthorizationDecision decision = policy.evaluate(context);
        if (decision.outcome() != DecisionOutcome.PERMIT) {
            throw new RefundAuthorizationException(
                    decision.safeReasonCode());
        }

        obligations.requireAllSupported(decision.obligations());

        UUID refundId = UUID.randomUUID();
        int changed = payments.reserveRefundAmount(
                actor.tenantId(), payment.id(), payment.version(),
                command.amountMinor(), command.currency(), checkedAt);
        if (changed != 1) {
            throw new RefundBudgetConflictException();
        }

        refunds.insertAccepted(
                refundId, payment, command, decision, checkedAt);
        audits.appendRefundAccepted(
                actor, refundId, payment, context, decision);
        outbox.appendExecuteRefund(
                UUID.randomUUID(), refundId,
                actor.tenantId(), payment.id());

        RefundReceipt receipt = new RefundReceipt(
                refundId, payment.id(),
                payment.version() + 1, checkedAt);
        idempotency.insert(scope, fingerprint, receipt);
        return receipt;
    }
}
```

Các dependency `final` phải được khởi tạo qua constructor trong mã thực tế. Với Spring transaction qua proxy thông thường, lời gọi phải đi qua bean được quản lý để annotation có hiệu lực. Tất cả repository phải tham gia đúng transaction manager đã giả định.

`fromTrustedSources()` không có nghĩa mọi trường trong command đều đáng tin. Command cung cấp ý định như số tiền đề nghị; factory phải kiểm tra phạm vi evidence, lấy dữ liệu sở hữu từ payment và không cho client ghi đè thuộc tính do server quản lý.

`requireAllSupported()` chỉ kiểm tra khả năng thực hiện các nghĩa vụ. Service vẫn phải thực hiện chúng thật sự. Trong mẫu này, giữ chỗ, ghi audit và tạo outbox là những bước bắt buộc trong cùng transaction; nếu một bước thất bại, toàn bộ lần nhận hoàn phải rollback.

### 9.4. Cập nhật ngân sách hoàn có điều kiện

Ví dụ SQL minh họa:

```sql
UPDATE payment
SET refund_reserved_minor = refund_reserved_minor + :amountMinor,
    version = version + 1,
    updated_at = :checkedAt
WHERE tenant_id = :tenantId
  AND id = :paymentId
  AND state = 'SETTLED'
  AND currency = :currency
  AND version = :expectedVersion
  AND :amountMinor > 0
  AND :amountMinor <=
      captured_minor - refunded_minor - refund_reserved_minor;
```

Các dấu `:` biểu diễn tham số bind của lớp truy cập dữ liệu. Số dòng cập nhật phải bằng 1. Schema và các đường ghi liên quan phải giữ các số tiền không âm, giới hạn biểu diễn hợp lệ và nhất quán với số tiền đã thu.

Điều kiện SQL này bảo vệ ngân sách của payment. Nó không thay thế kiểm tra quyền theo đơn vị, độ mới xác thực, phân tách nhiệm vụ hoặc risk evidence. Ngược lại, một kết quả `PERMIT` cũng không thay thế điều kiện ngân sách tại cập nhật.

### 9.5. Giới hạn của ví dụ

Hai refund command khác key vẫn có thể cùng hợp lệ nếu còn ngân sách. Nếu nghiệp vụ quy định chỉ một khoản hoàn cho một yêu cầu hỗ trợ hoặc một refund intent, cần thêm định danh nghiệp vụ ổn định, kiểm tra quan hệ và ràng buộc duy nhất tương ứng.

Không được suy ra “không hoàn trùng theo mọi ý nghĩa nghiệp vụ” chỉ từ idempotency key của API. Idempotency chống retry của một command; quy tắc duy nhất theo vụ việc là một bất biến khác.

## 10. Hạn mức, tiền tệ và ngữ cảnh sử dụng chung

### 10.1. Hạn mức của chủ thể phải có phạm vi và đơn vị

Một giá trị `limit=1000000` thiếu mã tiền tệ hoặc loại hành động có thể bị áp dụng sai. Cần biết hạn mức dành cho hành động nào, trong đơn vị nào, theo loại tiền nào và tại phiên bản chính sách nào.

Nếu hệ thống hỗ trợ chuyển đổi tiền tệ, cần nguồn tỷ giá và quy tắc làm tròn theo chính sách. Không lấy tỷ giá từ client để so sánh hạn mức nhạy cảm.

### 10.2. Hạn mức tổng không chỉ là một thuộc tính để đọc

Giả sử một người còn được nhận xử lý 5 triệu trong ngày. Hai request đồng thời cùng thấy số còn lại là 5 triệu có thể nhận tổng cộng 10 triệu nếu không giữ chỗ hạn mức.

Khi áp dụng hạn mức tổng, việc nhận command cần giữ chỗ phần sử dụng trong cùng giao thức concurrency với các request khác. Việc hoàn trả quota sau thất bại cũng phải có điều kiện và chống xử lý lặp.

### 10.3. Ranh giới kỳ hạn mức phải được xác định

“Theo ngày” cần múi giờ hoặc kỳ tính cụ thể. Nếu giao dịch chờ khóa qua nửa đêm, phải biết nó thuộc bucket nào tại gate, và kiểm tra lại khi bucket hoặc chính sách không còn khớp.

Không chọn bucket theo thời gian client gửi rồi dùng một mốc server khác để cấp quyền mà không kiểm tra sự nhất quán.

## 11. Quyền của dịch vụ và quyền được ủy nhiệm

Khi dịch vụ gọi thay người dùng, có ít nhất hai câu hỏi:

- Dịch vụ có được phép thực hiện loại lời gọi này không?
- Người dùng hoặc chủ thể ủy nhiệm có quyền trên đối tượng và hành động cụ thể không?

Trong mô hình gọi thay, quyền kết quả thường cần bị giới hạn bởi cả hai phạm vi, thay vì lấy hợp của quyền người dùng và toàn bộ quyền của service account.

Ví dụ một worker có quyền kỹ thuật gọi nhà cung cấp hoàn tiền không được dùng quyền đó để chấp nhận tùy ý một refund request từ người không có quyền trên payment.

Một thông điệp bền vững nên tham chiếu refund command đã được nhận và dữ liệu được ràng buộc. Không để payload queue tùy ý thay amount, currency hoặc payment ID rồi dựa vào quyền rộng của worker để thực thi.

Nếu phát hành một decision token hoặc permit nội bộ, cần giới hạn rõ:

```text
chủ thể và chuỗi gọi thay
dịch vụ được phép dùng
hành động
tenant và đối tượng
digest hoặc version nội dung
thời hạn
policy revision
command hoặc intent liên quan
các nghĩa vụ bắt buộc
```

Chữ ký hợp lệ chỉ bảo vệ những gì được ký theo hợp đồng; nó không tự biến permit thành quyền dùng trên mọi đối tượng hoặc mọi thời điểm.

## 12. Công việc bất đồng bộ: đánh giá ở lúc nhận hay lúc chạy?

Một refund command có thể được nhận lúc người dùng còn quyền nhưng được worker xử lý sau đó. Chính sách phải trả lời việc thu hồi quyền trong khoảng đó ảnh hưởng ra sao.

### 12.1. Quyền được xác lập khi nhận command

Theo lựa chọn này, command đã được nhận hợp lệ trở thành nghĩa vụ hệ thống. Worker xử lý đúng command trong phạm vi được cấp, dù phiên đăng nhập người dùng đã kết thúc.

Cần bảo vệ nội dung command, định danh hiệu ứng, thời hạn riêng nếu có và điều kiện hủy. Việc token người dùng hết hạn không tự chứng minh phải bỏ một khoản hoàn đã được nhận.

### 12.2. Bắt buộc đánh giá lại trước bước nhạy cảm

Một số nghiệp vụ yêu cầu quyền, hạn mức hoặc tín hiệu rủi ro phải còn phù hợp trước dispatch. Khi đó worker phải lấy ngữ cảnh mới theo giao thức, xử lý trường hợp thiếu quyền và theo dõi việc giải phóng reservation an toàn.

Không tạo command mới chỉ vì phải đánh giá lại. Nếu lệnh trước đã được gửi nhưng chưa rõ kết quả, phải đối soát trước khi mở đường thực hiện một hiệu ứng khác.

### 12.3. Đánh giá lại cũng có ranh giới

Kiểm tra trạng thái rồi gọi HTTP vẫn có khoảng đua với thay đổi quyền hoặc hủy. Nếu hợp đồng cần kiểm soát đến điểm bên ngoài chấp nhận, cần giao thức hỗ trợ ở ranh giới đó, không chỉ một kiểm tra thêm trong worker.

Không tuyên bố một lần `authorize()` làm cho mọi hệ thống liên quan giữ nguyên ngữ cảnh đến khi xử lý hoàn tất.

## 13. Cache, phiên bản chính sách và điểm thực thi

### 13.1. Không cache quyết định quá rộng

Cache theo `userId + role` có thể tái sử dụng quyết định cho tenant, payment, số tiền hoặc hành động khác. Cache theo user và object nhưng bỏ qua version cũng có thể giữ một quyền đã không còn phù hợp.

Nếu cache một phần quyết định, cần xác định đầy đủ khóa, thời hạn và cách xử lý thay đổi quyền, nội dung, risk evidence hoặc policy revision. Chỉ giảm TTL không bảo đảm thu hồi tức thời.

Đường nhận hiệu ứng nhạy cảm thường cần kiểm tra nguồn dữ liệu có mức nhất quán phù hợp. Cache để hiển thị nút không được trở thành bằng chứng cuối cùng cho việc thực thi.

### 13.2. Chính sách cũng là dữ liệu cần được quản lý

Thay rule có thể làm tăng hoặc giảm quyền thực tế. Cần quản lý phiên bản, kiểm tra trước khi áp dụng, phân quyền thay đổi và ghi audit.

Một decision nên ghi policy revision đã dùng. Nếu đang triển khai nhiều phiên bản service, cần xác định phiên bản policy nào có thẩm quyền tại gate; không để hai đường thực hiện cùng một hành động dùng các mặc định trái nhau.

Nếu thuộc tính hoặc obligation mới chưa được phiên bản cũ hiểu, phải có hành vi tương thích an toàn theo thiết kế. Không bỏ qua dữ liệu chưa hiểu rồi coi như đã đáp ứng điều kiện.

### 13.3. Điểm áp dụng quyết định phải bao phủ mọi đường vào

Controller HTTP không phải đường vào duy nhất. Cần bảo vệ cả API quản trị, consumer queue, batch job, import và công cụ hỗ trợ có thể tạo cùng hiệu ứng nghiệp vụ.

Không cho một đường “nội bộ” tự bỏ kiểm tra chỉ vì request đến từ một service account có quyền rộng. Phạm vi và ngữ cảnh ủy nhiệm vẫn phải được xác thực theo hợp đồng của đường đó.

## 14. Batch, danh sách và dữ liệu đầu ra

### 14.1. Không cấp quyền cả batch bằng một phần tử đại diện

Một batch có thể chứa payment thuộc nhiều tenant, đơn vị, trạng thái hoặc mức tiền. Quyền trên payment đầu tiên không bao phủ phần còn lại.

Cần định nghĩa batch thành công toàn bộ hay cho kết quả từng phần. Với mỗi phần tử vẫn phải kiểm tra đối tượng và ngữ cảnh; với hạn mức tổng còn phải bảo vệ tổng phần được nhận theo cơ chế concurrency phù hợp.

Không kiểm tra toàn bộ batch ở một thời điểm rồi ghi từng phần rất lâu sau đó mà không kiểm tra lại điều kiện cần thiết.

### 14.2. Quyền đọc có thể phụ thuộc loại dữ liệu được trả

Một chủ thể có thể được xem trạng thái hoàn tiền nhưng không được xem toàn bộ thông tin thanh toán. Có thể mô hình hóa hành động riêng như `READ_REFUND_SUMMARY` và `READ_PAYMENT_DETAILS`, hoặc nghĩa vụ lọc trường do server thực thi.

Không tải toàn bộ dữ liệu nhạy cảm về client rồi chỉ ẩn bằng CSS. Bộ đếm, export và endpoint tìm kiếm cũng phải tuân thủ phạm vi, nếu không người dùng có thể suy ra hoặc tải dữ liệu ngoài quyền qua đường khác.

### 14.3. Phản hồi từ chối không nên làm lộ ngữ cảnh nhạy cảm

Backend cần đủ reason code để điều tra, nhưng không nhất thiết trả toàn bộ rule, risk score hoặc thông tin đối tượng của người khác cho client.

Có thể trả thông tin hành động được phép tiếp theo cho người có quyền, chẳng hạn yêu cầu xác thực lại. Với truy cập sai đối tượng, phản hồi phải theo chính sách không tiết lộ của hệ thống.

## 15. Audit quyết định theo ngữ cảnh

Một dấu vết hữu ích nên liên kết được:

- Chủ thể chuẩn hóa, tài khoản, dịch vụ gọi thay và bằng chứng ủy nhiệm liên quan.
- Action, tenant, đối tượng và version dữ liệu đã đánh giá.
- Số tiền và tiền tệ theo mức cần cho audit, tránh sao chép dữ liệu nhạy cảm không cần thiết.
- Policy revision, thời điểm gate và decision ID.
- Tham chiếu risk evidence và bằng chứng xác thực, không ghi token nguyên văn.
- Kết quả, reason code và những nghĩa vụ đã được thực hiện.
- Refund command hoặc business intent được nhận nếu có.

Không chỉ ghi `allowed=true`. Khi điều tra một khoản hoàn sai, cần giải thích vì sao quyền được cấp theo dữ liệu nào tại thời điểm đó.

Audit thành công bắt buộc cần commit cùng transaction nhận hiệu ứng. Lần thử bị từ chối hoặc lỗi xác thực có thể cần đường ghi riêng, vì transaction nghiệp vụ bị rollback sẽ hủy các bản ghi cùng transaction.

Các tín hiệu có ích gồm:

| Tín hiệu | Điều cần kiểm tra |
| --- | --- |
| Nhiều request sai tenant hoặc đơn vị | Dò ID, client lỗi hoặc nguồn scope sai |
| Risk evidence liên tục không khớp digest | Người dùng đổi nội dung sau đánh giá hoặc cố tái sử dụng chứng cứ |
| Nhiều lần dùng xác thực quá cũ | UX giữ phiên quá lâu hoặc có replay |
| Nhiều `INDETERMINATE` | Nguồn thuộc tính đang lỗi, quá hạn hoặc cấu hình policy thiếu |
| Nhiều xung đột ngân sách sau `PERMIT` | Có đường ghi cạnh tranh hoặc thiếu giao thức khóa |
| Một service account gọi nhiều đối tượng ngoài chuỗi ủy nhiệm | Có thể có quyền quá rộng hoặc hành vi lạm dụng dịch vụ gọi thay |
| Khác biệt quyết định giữa các phiên bản service | Policy rollout hoặc điểm thực thi chưa nhất quán |

## 16. Kiểm thử tình huống tấn công logic

### 16.1. Kiểm thử nguồn thuộc tính và phạm vi

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Role đúng nhưng payment thuộc tenant khác | Không đọc hoặc nhận hoàn ngoài phạm vi |
| Cùng tenant nhưng khác đơn vị được giao | Không coi role chung là quyền trên mọi payment |
| Client tự gửi `risk=low`, `mfa=true` hoặc `trusted=true` | Không làm thay đổi ngữ cảnh tin cậy |
| Risk evidence của payment A dùng cho B | Không cấp quyền |
| Evidence cho số tiền nhỏ được dùng cho số tiền lớn | Bị từ chối vì không khớp input hoặc policy |
| Evidence đúng chữ ký nhưng quá hạn | Không cấp quyền chỉ vì tính toàn vẹn còn đúng |
| Action chưa có policy hoặc có obligation chưa hỗ trợ | Không tự cho phép |
| IAM hoặc nguồn thuộc tính bắt buộc không có dữ liệu | Không mặc định thành đủ quyền |
| Service account gọi thay người không có quyền | Không dùng quyền kỹ thuật để vượt phạm vi người ủy nhiệm |

### 16.2. Kiểm thử xác thực và thời gian

Kiểm tra các mốc ngay trước, đúng và sau hạn theo độ chính xác của hệ thống. Với logic thuần Java, dùng `Clock` hoặc abstraction thời gian có thể điều khiển; không dựa vào đồng hồ thật và `sleep`.

Các trường hợp quan trọng:

1. Access token được refresh nhưng xác thực tăng cường đã quá cũ.
2. Thời điểm xác thực hoặc đánh giá rủi ro nằm trong tương lai ngoài mức cho phép.
3. Request bắt đầu khi bằng chứng còn hạn nhưng chờ khóa đến sau hạn.
4. Đồng hồ client đổi hoặc client gửi timestamp lùi về quá khứ.
5. Giao dịch đi qua ranh giới kỳ hạn mức hoặc khung giờ nghiệp vụ.

Nếu dùng PostgreSQL, lưu ý `now()` và `CURRENT_TIMESTAMP` phản ánh thời điểm bắt đầu transaction. Một gate yêu cầu thời gian thực sau chờ khóa cần chọn nguồn thời gian phù hợp, chẳng hạn lấy một mốc mới từ `clock_timestamp()` sau khi đã lấy các khóa cần thiết. Test tích hợp cần kiểm tra đúng ngữ nghĩa thời gian của cơ sở dữ liệu, không chỉ mock `Clock` ở Java.

### 16.3. Kiểm thử concurrency

Dùng hai transaction độc lập và barrier hoặc latch để điều khiển lịch:

```text
A. Hai request cùng muốn nhận phần ngân sách hoàn còn lại.
   Kết quả: tổng đã hoàn và đang giữ chỗ không vượt số được phép.

B. Quyền cục bộ bị thu hồi cạnh tranh với nhận hoàn.
   Kết quả: theo thứ tự hợp lệ của giao thức khóa;
   không dùng một snapshot cũ ngoài hợp đồng đã định nghĩa.

C. Payment đổi trạng thái hoặc đơn vị trong lúc request chờ.
   Kết quả: gate đánh giá dữ liệu hiện tại sau khi lấy khóa.

D. Risk evidence hết hạn trong lúc chờ khóa.
   Kết quả: không dùng mốc thời gian lấy trước khi chờ để cấp quyền.
```

Không chỉ kiểm tra số tiền cuối cùng; cần kiểm tra refund command, reservation, audit, outbox và lý do từ chối hoặc xung đột liên quan.

### 16.4. Kiểm thử retry và ranh giới commit

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Cùng key và nội dung được gửi lại | Trả command cũ, không giữ chỗ thêm |
| Cùng key nhưng số tiền hoặc payment khác trong cùng phạm vi key | Xung đột theo hợp đồng idempotency, không diễn giải thành ý định mới |
| Key mới nhưng cùng intent nghiệp vụ chỉ được hoàn một lần | Ràng buộc intent ngăn tạo hiệu ứng trùng |
| Audit hoặc outbox bắt buộc ghi lỗi | Không commit phần nhận hoàn còn lại |
| Response mất sau commit | Retry tìm được biên nhận đã lưu |
| Provider timeout khi hoàn | Không giải phóng rồi tạo lệnh mới khi kết quả cũ chưa rõ |
| Quyền thực thi mới bị mất nhưng còn quyền đọc biên nhận | Replay chỉ đọc kết quả cũ theo chính sách, không tạo quyền mới |
| Quyền đọc biên nhận cũng bị mất | Key không trở thành đường truy cập trái phép |

Trong ví dụ, key có phạm vi theo payment. Nếu cùng chuỗi key dùng trên payment khác, đó là phạm vi khác. Nếu API chọn phạm vi rộng hơn, ràng buộc và test phải phản ánh đúng lựa chọn đó.

### 16.5. Kiểm thử bằng cách chỉ thay một yếu tố

Từ một ngữ cảnh được cho phép, thay lần lượt từng điều kiện bắt buộc:

- Đổi sang tenant hoặc đơn vị không được giao.
- Tăng số tiền vượt hạn mức trong khi giữ các yếu tố khác.
- Làm bằng chứng xác thực hoặc risk evidence quá hạn.
- Thay phiên bản nội dung của đối tượng.
- Bỏ một nghĩa vụ bắt buộc hoặc làm nó thất bại.

Kết quả phải thay đổi theo chính sách mong đợi. Cách kiểm tra này giúp phát hiện rule bị bỏ quên hoặc nhánh `OR` vô tình cho phép một điều kiện yếu thay thế các điều kiện bắt buộc khác.

Không phải mọi policy đều đơn điệu trên mọi thuộc tính; ví dụ có thể có phân tầng quyền theo số tiền. Điều cần chứng minh là hành vi phù hợp quy tắc được công bố, không tự đặt một tính chất chung trái với chính sách.

## 17. Các lỗi thiết kế cần tránh

| Cách làm | Vì sao tạo lỗ hổng logic | Hướng thay thế |
| --- | --- | --- |
| Chỉ kiểm tra role | Không giới hạn đối tượng, trạng thái hoặc điều kiện | Đánh giá chủ thể, action, resource và môi trường |
| Tin thuộc tính do client tự khai | Người gọi tự tạo điều kiện được phép | Nguồn thuộc tính có thẩm quyền và kiểm tra phạm vi |
| Xác thực mới bằng cách nhìn thời điểm phát hành token | Token mới không chứng minh người dùng vừa xác thực tăng cường | Bằng chứng xác thực có ngữ nghĩa được kiểm tra |
| Lỗi lấy policy thì cho chạy tiếp | Thiếu dữ liệu bị biến thành đủ quyền | Kết quả chưa xác định không thực thi hành động cần dữ liệu đó |
| Kiểm tra một lần trước khi chờ khóa | Ngữ cảnh có thể đã thay đổi tại lúc ghi | Gate với dữ liệu và thời gian phù hợp |
| `PERMIT` rồi bỏ qua nghĩa vụ | Quyết định bị tách khỏi điều kiện bảo đảm | Thực hiện bắt buộc hoặc từ chối |
| Cache theo user và role | Tái dùng quyền cho đối tượng hoặc số tiền khác | Khóa cache, version và giới hạn hiệu lực đúng phạm vi |
| Quyền service account thay mọi quyền người dùng | Dịch vụ trở thành đường vượt quyền | Ràng buộc chuỗi gọi thay và đối tượng |
| Dùng bằng chứng rủi ro của input cũ | Quyết định thuận lợi áp dụng lên nội dung mới | Digest, version và hạn hiệu lực được đối chiếu |
| Chỉ kiểm tra refund đã hoàn tất | Lệnh đồng thời vượt ngân sách | Tính cả phần đang được nhận xử lý |
| Cho rằng idempotency là mọi quy tắc chống trùng | Key mới có thể tạo thêm ý định tương đương | Ràng buộc nghiệp vụ theo intent hoặc vụ việc |
| Bảo vệ controller nhưng bỏ consumer hoặc batch | Cùng hiệu ứng đi vào qua đường yếu hơn | Cùng chính sách và giao thức ở mọi điểm thực thi |

## 18. Bài tập thiết kế

Thiết kế API hoàn tiền thủ công cho một hệ thống nhiều tenant. Nhân viên chỉ xử lý các payment của đơn vị được giao, có hạn mức từng lệnh và tổng hạn mức theo kỳ. Khoản nhạy cảm cần xác thực tăng cường gần đây và một đánh giá rủi ro ràng buộc với nội dung hoàn.

Hãy mô tả:

1. Những thuộc tính nào dùng để cấp quyền, nguồn nào có thẩm quyền cho từng thuộc tính?
2. Action yêu cầu, phê duyệt và thực thi hoàn tiền khác nhau ra sao?
3. Gate nằm ở đâu và những dữ liệu nào phải được giữ nhất quán tại gate?
4. Risk evidence được ràng buộc với payment, số tiền và phiên bản dữ liệu như thế nào?
5. Hạn mức tổng được giữ chỗ và giải phóng an toàn ra sao khi có concurrency hoặc timeout?
6. Worker được xử lý command đã nhận theo quyền tại lúc nhận hay phải đánh giá lại? Chính sách xử lý thu hồi quyền là gì?
7. Retry được phép đọc biên nhận trong điều kiện nào và điều gì ngăn nó tạo một khoản hoàn mới?
8. Những test nào chứng minh thay tenant, đổi số tiền hoặc dùng bằng chứng quá hạn không thể đi qua một đường nhập khác như batch hoặc queue?

Một thiết kế đạt yêu cầu phải giải thích được vì sao đúng chủ thể được phép làm đúng hành động trên đúng đối tượng trong đúng điều kiện, đồng thời giữ các điều kiện cần thiết nhất quán khi hệ thống thực sự nhận hiệu ứng nghiệp vụ.
