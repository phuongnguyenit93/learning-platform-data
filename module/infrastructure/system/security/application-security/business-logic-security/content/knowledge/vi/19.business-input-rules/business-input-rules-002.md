# Required business fields — Trường bắt buộc theo quy tắc nghiệp vụ

## 1. Có dữ liệu chưa có nghĩa là đủ điều kiện thực hiện nghiệp vụ

Một API có thể nhận JSON đúng định dạng, các trường đều khác `null`, nhưng yêu cầu vẫn thiếu thông tin cần thiết để được xử lý. Một mã người nhận có thể trỏ sang tenant khác. Một chứng từ đã tải lên có thể chưa được xác minh. Một chuỗi “N/A” có thể vượt kiểm tra không rỗng nhưng không đáp ứng điều kiện giải trình của nghiệp vụ.

**Required business fields** là những thông tin hoặc bằng chứng phải có và phải dùng được để một hành động nghiệp vụ được chấp nhận trong trạng thái, loại hồ sơ và chính sách tương ứng.

Trong bảo vệ logic nghiệp vụ, kiểm tra trường bắt buộc giúp ngăn các đường lạm dụng như:

- Gửi hồ sơ thiếu chứng từ qua API dù giao diện không cho bấm nút.
- Bỏ trường xác định mức rủi ro để né những yêu cầu bổ sung.
- Gửi `approved=true` thay cho một quyết định phê duyệt có thẩm quyền.
- Chọn một ID hợp lệ về cú pháp nhưng không được phép sử dụng.
- Lưu bản nháp chưa đủ dữ liệu rồi gọi thẳng bước thực thi.
- Xóa trường bắt buộc sau khi đã qua một lần kiểm tra trước đó.

Điểm cần bảo vệ là điều kiện nhận hành động nghiệp vụ, không chỉ hình thức của request hoặc dấu sao trên biểu mẫu.

## 2. Bốn lớp kiểm tra cần phân biệt

| Lớp kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Cú pháp và kiểu dữ liệu | Input có parse được và đúng kiểu không? | Một ID có định dạng được hỗ trợ |
| Sự hiện diện | Trường có được cung cấp theo hợp đồng không? | Có `invoiceId`, không chỉ một object rỗng |
| Miền giá trị | Giá trị có nằm trong miền được chấp nhận không? | Số tiền dương, mã tiền tệ được hỗ trợ |
| Tính hợp lệ nghiệp vụ | Giá trị và bằng chứng có đủ dùng cho action này không? | Hóa đơn đã xác minh, đúng tenant, còn dùng được và phù hợp hồ sơ |

Một annotation `@NotNull` có thể hỗ trợ lớp hiện diện, nhưng không chứng minh hóa đơn thuộc người gọi hoặc người nhận vẫn được phép nhận thanh toán.

Tương tự, một khóa ngoại chứng minh bản ghi được tham chiếu tồn tại theo schema. Nó không tự chứng minh bản ghi đó đúng scope, đúng trạng thái hoặc được chủ thể hiện tại sử dụng.

### 2.1. Định nghĩa “đủ” theo action

Không có một tập trường bắt buộc duy nhất cho mọi thao tác trên cùng đối tượng.

```text
required_fields = policy(action, state, request_type, trusted_business_facts)
```

Lưu bản nháp, gửi duyệt, phê duyệt và nhận thực thi có những điều kiện khác nhau. Dùng chung một cờ `isValid` cho cả vòng đời thường làm mất sự khác biệt này.

## 3. Ví dụ xuyên suốt: đề nghị thanh toán từ hóa đơn

Giả sử hệ thống có quy trình:

```text
DRAFT → SUBMITTED → APPROVED → EXECUTING → PAID
```

Người dùng chuẩn bị đề nghị thanh toán với những thông tin như hóa đơn, trung tâm chi phí, mục đích và tài liệu giải trình. Server lấy người nhận, số tiền và tiền tệ từ phiên bản hóa đơn đã được xác minh, theo hợp đồng của ví dụ.

Chính sách minh họa:

1. Bản nháp được phép chưa đủ một số thông tin.
2. Gửi duyệt cần hóa đơn dùng được, trung tâm chi phí được phép và mục đích hợp lệ.
3. Những loại hoặc mức tiền nhất định cần thêm bằng chứng giải trình đã được chấp nhận.
4. Điều kiện bổ sung được xác định từ dữ liệu mà server kiểm tra, không từ cờ rủi ro do client tự khai.
5. Nội dung được gửi duyệt được chốt phiên bản để quyết định phê duyệt gắn với đúng dữ liệu.
6. Bước nhận thực thi phải có phê duyệt và những điều kiện còn hiệu lực theo chính sách.

Đây là ví dụ thiết kế, không phải một danh sách chứng từ pháp lý áp dụng cho mọi hoạt động thanh toán.

### 3.1. Ma trận thông tin theo bước

| Thông tin | Lưu bản nháp | Gửi duyệt | Nhận thực thi |
| --- | --- | --- | --- |
| Tenant, chủ thể tạo, version | Server thiết lập | Phải nhất quán | Phải nhất quán |
| Hóa đơn tham chiếu | Có thể chưa chọn | Bắt buộc và phải dùng được | Phải khớp nội dung đã được duyệt |
| Trung tâm chi phí | Có thể chưa chọn | Bắt buộc và đúng thẩm quyền | Phải thỏa điều kiện áp dụng |
| Mục đích thanh toán | Có thể còn thiếu | Bắt buộc theo quy tắc nội dung | Không được thay ngầm sau duyệt |
| Số tiền, tiền tệ, người nhận | Có thể chỉ hiển thị tạm | Server chốt từ nguồn đã xác minh | Khớp bằng chứng phê duyệt và command |
| Giải trình bổ sung | Theo nhu cầu soạn thảo | Bắt buộc khi rule điều kiện áp dụng | Bằng chứng cần thiết vẫn dùng được |
| Phê duyệt | Chưa yêu cầu | Chưa có quyết định cuối | Bắt buộc theo policy, không lấy từ body |

Cho phép bản nháp chưa đủ không có nghĩa cho phép đưa một hồ sơ chưa đủ điều kiện sang trạng thái tiếp theo.

## 4. “Thiếu” có nhiều dạng

| Dạng input | Có thể gặp ở đâu? | Điều cần quyết định |
| --- | --- | --- |
| Không có key | JSON hoặc bản vá | Không thay đổi hay thiếu dữ liệu cho action? |
| `null` | JSON hoặc nguồn dữ liệu | Có được xóa giá trị hay không? |
| Chuỗi rỗng | Biểu mẫu, CSV | Có được xem là chưa nhập không? |
| Chuỗi chỉ có khoảng trắng | Dữ liệu người dùng nhập | Quy tắc chuẩn hóa và kiểm tra ký tự nào áp dụng? |
| Mảng rỗng | Danh sách bằng chứng | Có cần ít nhất một phần tử dùng được không? |
| Object rỗng | Một cấu trúc lồng nhau | Những trường con nào còn thiếu? |
| `0`, `false` | Kiểu số và boolean | Giá trị hợp lệ hay không đáp ứng yêu cầu cụ thể? |
| Mã sentinel như `UNKNOWN` | Enum hoặc import cũ | Có được dùng ở trạng thái hiện tại không? |
| ID tồn tại nhưng sai phạm vi | Tham chiếu nghiệp vụ | Phải từ chối vì không có quyền hoặc không dùng được |

Không áp dụng một quy tắc chung rằng mọi `0` hoặc `false` đều là thiếu. Số lượng bằng 0 có thể không hợp lệ trong một dòng mua hàng nhưng mức giảm giá bằng 0 có thể hợp lệ. Một lựa chọn boolean `false` có thể là câu trả lời đầy đủ; một xác nhận bắt buộc `accepted=true` lại có yêu cầu khác.

### 4.1. Cẩn thận với giá trị mặc định của kiểu dữ liệu

Nếu một trường số dùng primitive trong DTO và thư viện deserialize đặt giá trị mặc định khi không có key, hệ thống có thể không phân biệt được người dùng gửi 0 với người dùng không gửi.

Với trường cần phân biệt, dùng biểu diễn có trạng thái hiện diện rõ ràng hoặc một kiểu nullable được kiểm tra phù hợp. Không tự chọn một giá trị mặc định có tác dụng cấp quyền, chẳng hạn `riskLevel=LOW` hoặc `approvalRequired=false` khi dữ liệu còn thiếu.

### 4.2. Một giá trị không rỗng chưa chắc có ý nghĩa

Độ dài tối thiểu hoặc danh sách từ bị cấm chỉ hỗ trợ một phần việc kiểm tra. Chúng không chứng minh một đoạn giải trình thực sự đúng hoặc một chứng từ thực sự liên quan.

Hãy chuyển những yêu cầu có thể xác định thành cấu trúc rõ ràng: loại lý do, đối tượng liên quan, số hiệu bằng chứng và trạng thái xác minh. Những nội dung cần đánh giá chuyên môn vẫn phải có bước đánh giá phù hợp, không giả định rằng chuỗi dài là đủ chất lượng.

## 5. Trường bắt buộc không đồng nghĩa trường do client được phép quyết định

Một số dữ liệu bắt buộc phải có trong bản ghi nghiệp vụ nhưng không nên được client gửi như nguồn có thẩm quyền.

| Dữ liệu | Nguồn phù hợp trong ví dụ | Input không được tự thay thế |
| --- | --- | --- |
| Tenant và người tạo | Ngữ cảnh đã xác thực và kiểm tra | `tenantId`, `createdBy` tùy ý |
| Trạng thái hồ sơ | Action và state machine phía server | `state=APPROVED` trong bản vá |
| Số tiền và tiền tệ thanh toán | Phiên bản hóa đơn được chấp nhận theo policy | `totalAmount` tự khai để giảm mức kiểm tra |
| Người nhận | Quan hệ hóa đơn và hồ sơ người nhận đã được kiểm tra | Tài khoản đích bất kỳ do client thêm vào |
| Người duyệt và thời điểm duyệt | Quyết định phê duyệt thật | `approvedBy`, `approvedAt`, `approved=true` |
| Bằng chứng đủ điều kiện | Dữ liệu xác minh hoặc chấp nhận có thẩm quyền | Một cờ `documentVerified=true` |
| Phiên bản và digest nội dung | Server tính và lưu theo mô hình | Digest tự khai không được đối chiếu |

Trong loại nghiệp vụ khác, số tiền đề nghị có thể do người dùng nhập. Khi đó nó là một đề xuất phải kiểm tra và chốt theo policy, không phải một giá trị có thẩm quyền chỉ vì đã xuất hiện trong request.

Đối với giá hàng, chiết khấu hoặc tổng tiền, phải xác định nguồn nghiệp vụ nào quyết định giá trị được nhận. Không lấy tổng tiền trên giao diện làm cơ sở duy nhất cho điều kiện phê duyệt.

## 6. Yêu cầu có điều kiện phải dựa trên dữ liệu đã kiểm tra

Ví dụ một loại đề nghị có số tiền cao cần bằng chứng giải trình bổ sung:

```text
nếu amount_from_verified_invoice >= threshold_for_currency
thì cần bằng chứng HIGH_VALUE_JUSTIFICATION dùng được
```

Một triển khai nguy hiểm là:

```java
// Không an toàn nếu client được tự quyết định điều kiện.
if (request.isHighValue()) {
    require(request.justificationId());
}
```

Kẻ tấn công có thể bỏ cờ hoặc đặt `false`. Server phải xác định điều kiện từ số tiền và loại hồ sơ đã được kiểm tra.

### 6.1. Dữ liệu để chọn nhánh cũng là dữ liệu bắt buộc

Nếu chưa có hóa đơn hoặc chưa xác định được số tiền, hệ thống không thể kết luận rằng hồ sơ không thuộc mức cao. Nó cần báo chưa đủ dữ liệu để đánh giá.

Không dùng mẫu suy luận:

```text
không có amount → không thấy amount lớn → không cần giải trình
```

Tương tự, loại người nhận, khu vực giao dịch hoặc loại đề nghị phải có nguồn phù hợp. Một trường phân loại bị bỏ trống không được tự rơi vào nhánh ít yêu cầu nhất.

### 6.2. Phải ràng buộc điều kiện với giá trị thật được chấp nhận

Nếu rule được tính trên một số tiền nhưng command cuối cùng thực hiện số tiền khác, trường bắt buộc đã không bảo vệ đúng hành động.

Cần dùng cùng candidate hoặc snapshot nội dung cho tính điều kiện, đánh giá dữ liệu và nhận bước chuyển trạng thái. Nếu dữ liệu đổi, phải tăng version và đánh giá lại.

### 6.3. Miễn áp dụng là một kết luận có cơ sở

Nếu một yêu cầu không áp dụng, server có thể lưu lý do theo rule và phiên bản chính sách. Không để client gửi `notApplicable=true` rồi bỏ tất cả bằng chứng cần thiết.

Một ngoại lệ được phép cần action, thẩm quyền, phạm vi và bằng chứng riêng. Nó không phải giá trị thay thế như “N/A” tự có tác dụng miễn rule.

## 7. Trường tham chiếu: có ID chưa đủ

Đối với `invoiceId`, `costCenterId` hoặc `evidenceId`, cần kiểm tra nhiều hơn định dạng:

1. Đối tượng được tham chiếu tồn tại trong phạm vi được phép tra cứu.
2. Nó thuộc đúng tenant và quan hệ nghiệp vụ cần thiết.
3. Chủ thể được phép sử dụng nó cho hồ sơ này.
4. Trạng thái còn cho phép sử dụng.
5. Phiên bản hoặc khoảng hiệu lực đáp ứng policy.
6. Dữ liệu liên quan khớp nội dung đang gửi duyệt.

Ví dụ, một trung tâm chi phí thuộc cùng tenant nhưng nhân viên không có quyền đề nghị chi từ đó vẫn không đáp ứng yêu cầu. Một hóa đơn đã bị hủy hoặc thay thế không trở thành dùng được chỉ vì khóa ngoại còn tồn tại.

### 7.1. Quan hệ nhiều cấp phải khớp

Nếu evidence được đính kèm qua request ID, không đủ để kiểm tra người dùng được sửa request rồi tải evidence theo ID toàn cục. Evidence phải thuộc đúng tenant và được phép gắn với đúng hồ sơ hoặc loại nghiệp vụ.

Một tài liệu của hồ sơ khác không tự đáp ứng yêu cầu chỉ vì cùng tên file hoặc cùng người tải lên.

### 7.2. Có hóa đơn không giải quyết mọi quy tắc chống trùng

Yêu cầu `invoiceId` bắt buộc không ngăn hai hồ sơ cùng thanh toán một hóa đơn. Nếu policy chỉ cho một nghĩa vụ thanh toán cho một nguồn, cần ràng buộc duy nhất hoặc cơ chế giữ chỗ nghiệp vụ tương ứng.

Nếu cho thanh toán từng phần, cần bảo vệ tổng số tiền đã nhận xử lý và đã thực hiện. Đây là bất biến bổ sung, không phải kết quả tự có của việc kiểm tra trường không rỗng.

## 8. Bằng chứng bắt buộc phải là bằng chứng dùng được

Một file đã upload chưa chắc đáp ứng yêu cầu. Nó có thể:

- Chưa hoàn tất xử lý hoặc chưa được chấp nhận.
- Không thuộc hồ sơ đang gửi.
- Không đúng loại bằng chứng mà rule yêu cầu.
- Đã bị thu hồi hoặc hết hiệu lực theo policy.
- Chỉ là tên hoặc nội dung do người dùng tự mô tả, chưa có xác nhận cần thiết.

Một predicate phù hợp có thể là:

```text
có_bằng_chứng_dùng_được(type, request, t) =
    tồn tại evidence đúng tenant và quan hệ request
    AND loại được hệ thống chấp nhận khớp yêu cầu
    AND trạng thái đủ điều kiện
    AND đúng phiên bản nội dung hoặc phạm vi cần chứng minh
    AND còn hiệu lực tại gate nếu policy yêu cầu
```

Đặt tên file `approval.pdf` không tạo ra một quyết định phê duyệt. Upload ảnh chữ ký không tự chứng minh một người có thẩm quyền đã chấp nhận đúng nội dung hiện tại.

Nếu bằng chứng cần xác minh bất đồng bộ, hồ sơ phải ở trạng thái chờ phù hợp. Một ACK đã nhận file hoặc đã xếp hàng xác minh không đồng nghĩa bằng chứng đã đạt điều kiện để gửi bước tiếp theo.

## 9. Lưu bản nháp, PATCH và thay đổi sau khi gửi

### 9.1. Lưu bản nháp không nhất thiết phải hoàn tất mọi trường

Cho lưu thiếu có thể cần thiết để người dùng chuẩn bị dần. Điều quan trọng là trạng thái `DRAFT` không được dùng như bằng chứng hồ sơ đã sẵn sàng gửi hoặc thực hiện.

Tách hợp đồng:

```text
saveDraft: dữ liệu có thể chưa đủ, nhưng các giá trị đã cung cấp vẫn phải an toàn
submit: candidate phải đáp ứng toàn bộ yêu cầu của bước gửi
approve: đánh giá đúng nội dung đã chốt và điều kiện phê duyệt
execute: có đủ bằng chứng cấp quyền và các bất biến thực thi
```

Bản nháp cũng không được chứa các trường do client tự đặt để mở quyền, chẳng hạn tenant khác, trạng thái đã duyệt hoặc người phê duyệt giả.

### 9.2. Phân biệt bỏ qua và xóa giá trị trong bản vá

Với PATCH, có thể cần ba trạng thái:

```text
Unchanged      : không sửa trường
Clear          : yêu cầu xóa giá trị hiện tại
Set(value)     : yêu cầu đặt giá trị mới
```

Không tự coi key vắng mặt và key có `null` là giống nhau nếu hợp đồng cần phân biệt. Cũng không mặc định thư viện deserialize hoặc một kiểu `Optional` bất kỳ đã giữ đúng ba trạng thái này.

Khi cho sửa nhiều trường cùng lúc, kiểm tra candidate sau khi áp dụng toàn bộ bản vá. Không kiểm tra hồ sơ cũ đã đủ rồi mới áp dụng một bản vá làm thiếu dữ liệu.

### 9.3. Sau khi gửi hoặc duyệt

Những trường ảnh hưởng quyết định phải được khóa hoặc sửa qua action làm mất hiệu lực bằng chứng liên quan và yêu cầu đánh giá lại.

Không cho một endpoint cập nhật chung xóa hóa đơn, thay người nhận hoặc bỏ giải trình sau khi đã ghi `SUBMITTED`. Nếu nghiệp vụ cho rút về bản nháp, đó là transition riêng với điều kiện và audit, không phải một cách lén sửa dữ liệu đã được duyệt.

## 10. Ví dụ Java: kiểm tra đầy đủ khi gửi duyệt

### 10.1. Giả định

Ví dụ dùng một cơ sở dữ liệu và Spring transaction. Những dữ liệu cần đọc ổn định hoặc kiểm tra hiện tại được bảo vệ bởi giao thức khóa hoặc snapshot có phiên bản phù hợp:

- Quyền và policy cục bộ có guard quyết định tương ứng.
- Bản nháp được khóa trước khi dựng candidate.
- Phiên bản hóa đơn xác minh và các bằng chứng được lấy từ nguồn có thẩm quyền.
- Trạng thái dùng được của các tham chiếu không bị đổi ngoài giao thức đã chọn.
- Không gọi mạng bên ngoài trong transaction này.

Thứ tự khóa trên các đường liên quan phải nhất quán. Nếu một nguồn ngoài không tham gia transaction, cần mô hình bằng chứng, phiên bản và giới hạn độ mới rõ ràng thay vì tuyên bố có nguyên tử xuyên hệ thống.

### 10.2. Service minh họa

Các repository, validator và kiểu dữ liệu dưới đây cần được triển khai. Constructor injection được lược bỏ; ví dụ không phải ứng dụng chạy độc lập.

```java
@Service
public class PaymentRequestSubmissionService {
    private final SubmissionDecisionGuard decisionGuard;
    private final PaymentRequestRepository requests;
    private final VerifiedInvoiceRepository invoices;
    private final CostCenterRepository costCenters;
    private final BusinessEvidenceRepository evidence;
    private final SubmissionPolicyRepository policies;
    private final SubmissionAuthorization authorization;
    private final RequiredBusinessFields requiredFields;
    private final SubmissionCandidateFactory candidates;
    private final DatabaseTimeSource databaseTime;
    private final IdempotencyRepository idempotency;
    private final WorkflowAuditRepository audits;
    private final OutboxRepository outbox;
    private final CommandFingerprint fingerprints;

    @Transactional(rollbackFor = Exception.class)
    public SubmissionReceipt submit(
            VerifiedActor actor,
            SubmitPaymentRequestCommand command) {

        actor.requireAuthenticated();
        command.validateSyntaxAndLimits();

        decisionGuard.lockForSubmission(actor.tenantId());

        PaymentRequest draft = requests.lockForUpdate(
                actor.tenantId(), command.requestId())
            .orElseThrow(PaymentRequestNotFoundException::new);

        // Quyền trên đối tượng, không chỉ quyền gọi endpoint.
        // Guard trạng thái cho lần gửi mới nằm bên dưới.
        authorization.requireSubmissionAuthority(actor, draft);

        CommandScope scope = new CommandScope(
                actor.tenantId(), draft.id(),
                actor.canonicalSubjectId(),
                "SUBMIT_PAYMENT_REQUEST", command.idempotencyKey());
        String fingerprint = fingerprints.forSubmission(command);

        var previous = idempotency.find(scope);
        if (previous.isPresent()) {
            if (!previous.get().fingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException();
            }
            return previous.get().receipt();
        }

        draft.requireDraft(command.expectedVersion());

        // Kiểm tra điều kiện nền trước khi dùng ID để chọn nhánh policy.
        SubmissionBaseline baseline =
                requiredFields.requireSubmissionBaseline(draft);

        VerifiedInvoiceSnapshot invoice = invoices.lockUsableSnapshot(
                actor.tenantId(), baseline.invoiceId())
            .orElseThrow(BusinessReferenceNotUsableException::new);

        CostCenterSnapshot costCenter = costCenters.lockForSubmission(
                actor.tenantId(), baseline.costCenterId())
            .orElseThrow(BusinessReferenceNotUsableException::new);

        EvidenceBundle proof = evidence.loadForSubmissionUnderGuard(
                actor.tenantId(), draft.id(), draft.evidenceReferences());

        authorization.requireCanUseReferences(
                actor, draft, invoice, costCenter, proof);

        Instant checkedAt = databaseTime.currentInstant();
        SubmissionRuleSet ruleSet = policies.resolveFor(
                actor.tenantId(), draft.requestType(),
                invoice, costCenter, checkedAt);

        SubmissionCandidate candidate = candidates.build(
                draft, invoice, costCenter, proof, checkedAt);

        ValidationResult validation = requiredFields.validateForSubmission(
                candidate, ruleSet);
        if (!validation.isValid()) {
            throw new SubmissionRequirementsNotMetException(
                    validation.safeViolations());
        }

        int changed = requests.markSubmitted(
                actor.tenantId(), draft.id(), draft.version(),
                candidate.snapshot(), ruleSet.revision(), checkedAt);
        if (changed != 1) {
            throw new ConcurrentPaymentRequestChangeException();
        }

        audits.appendPaymentRequestSubmitted(
                actor, draft, candidate, ruleSet, checkedAt);
        outbox.appendPaymentRequestSubmitted(
                UUID.randomUUID(), actor.tenantId(),
                draft.id(), draft.version() + 1);

        SubmissionReceipt receipt = new SubmissionReceipt(
                draft.id(), PaymentRequestState.SUBMITTED,
                draft.version() + 1, ruleSet.revision());
        idempotency.insert(scope, fingerprint, receipt);
        return receipt;
    }
}
```

Các trường `final` phải được khởi tạo bằng constructor trong mã thực tế. Với Spring transaction qua proxy thông thường, lời gọi phải đi qua bean được quản lý và các repository phải dùng đúng transaction manager.

`requireSubmissionBaseline()` kiểm tra những thông tin nền như loại hồ sơ hợp lệ, hóa đơn, trung tâm chi phí và mục đích trước khi dùng chúng để dựng candidate. Nó không tự điền giá trị giả để làm hồ sơ đủ.

`validateForSubmission()` phải kiểm tra bằng chứng theo loại và điều kiện áp dụng, không chỉ đếm số attachment. Nếu policy không xác định được hoặc nguồn cần thiết chưa dùng được, không được coi hồ sơ là đủ để gửi.

`markSubmitted()` cần cập nhật có điều kiện theo trạng thái `DRAFT`, version và những điều kiện bảo vệ tương ứng, đồng thời tăng version. Nó lưu đúng snapshot đã qua kiểm tra, gồm dữ liệu nguồn và policy revision cần cho các bước sau.

### 10.3. Vì sao command gửi duyệt có thể rất nhỏ?

Trong mô hình này, người dùng sửa dữ liệu qua action lưu bản nháp; command gửi duyệt chỉ xác định hồ sơ, expected version và ý định gửi. Server đọc lại dữ liệu có thẩm quyền thay vì tin một bản sao đầy đủ trên trình duyệt.

Một API khác có thể cho cập nhật và gửi trong cùng request. Khi đó vẫn phải dựng và kiểm tra candidate cuối trong cùng giao thức, không kiểm tra một bản rồi lưu bản khác.

## 11. Annotation, domain validation và ràng buộc dữ liệu

### 11.1. Annotation hữu ích ở lớp phù hợp

Trong Java, các constraint như `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Positive` và kiểm tra cấu trúc lồng nhau có thể phát hiện nhiều lỗi sớm khi được cấu hình và gọi đúng.

Chúng không thay thế:

- Kiểm tra quyền dùng invoice hoặc cost center.
- Điều kiện theo số tiền đã được xác minh.
- Trạng thái bằng chứng và vòng đời hồ sơ.
- Sự nhất quán với dữ liệu thay đổi đồng thời.

Có thể dùng nhóm validation theo action, nhưng mọi điểm vào nghiệp vụ phải gọi đúng nhóm. Nếu chỉ controller web chạy nhóm gửi duyệt còn consumer hoặc import bỏ qua, cùng một action sẽ có đường bảo vệ yếu hơn.

### 11.2. Ràng buộc cơ sở dữ liệu hỗ trợ phòng vệ

Ví dụ check tối thiểu cho những trạng thái đã vượt bản nháp:

```sql
CHECK (
    state NOT IN ('SUBMITTED', 'APPROVED', 'EXECUTING', 'PAID')
    OR (
        invoice_id IS NOT NULL
        AND verified_invoice_snapshot_id IS NOT NULL
        AND cost_center_id IS NOT NULL
        AND purpose IS NOT NULL
        AND char_length(trim(purpose)) > 0
        AND amount_minor IS NOT NULL
        AND amount_minor > 0
        AND currency IS NOT NULL
    )
)
```

Đây là minh họa một phần schema; `state` cũng cần có ràng buộc không null và miền giá trị phù hợp. Trong SQL, một check đơn giản như `amount_minor > 0` không tự thay thế `IS NOT NULL` vì ngữ nghĩa giá trị chưa xác định.

Kiểm tra `trim()` ở cơ sở dữ liệu có thể khác quy tắc khoảng trắng hoặc Unicode của ứng dụng. Cần thống nhất chính sách canonical hóa và không coi check minh họa này là kiểm tra đầy đủ mọi chuỗi có vẻ trống.

Check cục bộ cũng không tự đánh giá mọi rule cần đọc bảng khác hoặc nguồn ngoài. Khóa ngoại ghép theo tenant, ràng buộc số tiền và các kiểm tra domain vẫn cần được thiết kế tương ứng.

### 11.3. Không ép schema bản nháp thành một hồ sơ giả đầy đủ

Nếu mọi trường đều `NOT NULL` ngay khi tạo draft nhưng nghiệp vụ cho chuẩn bị dần, lập trình viên dễ chèn các giá trị như chuỗi rỗng, ID mặc định hoặc số tiền 0 để qua schema.

Hãy mô hình hóa đúng trạng thái chưa đủ, hoặc tách cấu trúc draft và snapshot gửi duyệt. Không dùng dữ liệu giả để che sự khác biệt giữa đang soạn và đã sẵn sàng.

## 12. Chuẩn hóa dữ liệu mà không thay đổi ý nghĩa ngầm

Chuẩn hóa có thể giúp phát hiện chuỗi chỉ có khoảng trắng, mã định danh có khoảng trống ngoài ý muốn hoặc biểu diễn số không thống nhất. Tuy nhiên, không nên dùng một phép biến đổi chung cho mọi trường.

Ví dụ:

- Một mô tả có thể được chuẩn hóa khoảng trắng theo chính sách.
- Một mã tham chiếu hoặc định danh bên ngoài có thể phân biệt ký tự hoặc có quy tắc riêng.
- Nội dung chứng từ cần giữ bản gốc cùng kết quả trích xuất nếu nghiệp vụ yêu cầu đối chiếu.
- Số tiền cần được parse và biểu diễn theo quy tắc tiền tệ, không cắt chuỗi để được một số có vẻ hợp lệ.

Không tự thay một trường không nhận diện được thành giá trị được phép. Một enum không hỗ trợ cần báo lỗi hoặc xử lý tương thích được định nghĩa, không tự đổi thành loại ít yêu cầu nhất.

Nếu tạo digest nội dung hoặc fingerprint idempotency, dùng cách canonical hóa ổn định và có phiên bản phù hợp. Hai biểu diễn được coi là cùng ý định phải được xử lý nhất quán; hai nội dung có nghĩa khác nhau không được bị gộp do chuẩn hóa quá mức.

## 13. Lỗi phản hồi cần giúp sửa dữ liệu mà không mở đường vượt quyền

Một phản hồi minh họa:

```json
{
  "code": "SUBMISSION_REQUIREMENTS_NOT_MET",
  "requestId": "request-123",
  "violations": [
    {
      "field": "purpose",
      "code": "REQUIRED_FOR_SUBMISSION"
    },
    {
      "field": "evidence.HIGH_VALUE_JUSTIFICATION",
      "code": "USABLE_EVIDENCE_REQUIRED"
    }
  ]
}
```

Client có thể dùng field path và reason code để hướng người dùng sửa. Backend vẫn là nguồn quyết định yêu cầu; client không được gửi lại một danh sách “đã sửa đủ” làm bằng chứng.

### 13.1. Không tiết lộ đối tượng ngoài phạm vi qua lỗi chi tiết

Với ID sai tenant hoặc không được phép dùng, một mã như `REFERENCE_NOT_USABLE` có thể phù hợp hơn việc tiết lộ hóa đơn tồn tại, thuộc ai và đang ở trạng thái nào. Chính sách phản hồi cần nhất quán với quyền đọc của người gọi.

### 13.2. Phân biệt lỗi dữ liệu với xung đột phiên bản

Thiếu mục đích khác với bản nháp đã được người khác sửa. Client cần biết khi nào bổ sung dữ liệu, khi nào tải lại phiên bản hiện tại và khi nào chờ xác minh bằng chứng.

Không tự retry vô hạn một lỗi nghiệp vụ thiếu trường. Retry mạng dùng cùng định danh command; sửa nội dung hoặc thay expected version cần tuân theo hợp đồng idempotency đã định nghĩa.

## 14. Policy thay đổi, client cũ và dữ liệu lịch sử

### 14.1. Draft cũ có thể cần bổ sung khi gửi

Một bản nháp được tạo trước khi policy yêu cầu thêm bằng chứng không tự được miễn khi gửi sau đó. Server cần xác định revision nào áp dụng cho action và trả các yêu cầu còn thiếu phù hợp.

UI có thể lấy metadata để hiển thị đúng trường theo phiên bản, nhưng API vẫn phải tự kiểm tra. Client cũ hoặc script không có trường mới không được mặc nhiên đi qua vì form chưa biết yêu cầu.

### 14.2. Không âm thầm viết lại bằng chứng lịch sử

Một hồ sơ đã được chấp nhận hợp lệ theo policy cũ cần giữ revision và snapshot đã dùng. Nếu policy mới đòi tái xác nhận trước bước tiếp theo, đó là một quy trình được xác định rõ, không phải sửa timestamp hoặc chèn bằng chứng giả vào hồ sơ cũ.

Không dùng nhánh `legacy=true` như một quyền bỏ qua mọi kiểm tra. Cơ chế tương thích phải có phạm vi và điều kiện cụ thể.

### 14.3. Mọi đường vào phải dùng cùng ý nghĩa nghiệp vụ

Web, mobile, CSV import, batch, API hỗ trợ và queue có thể có cấu trúc request khác nhau, nhưng action gửi duyệt phải đạt cùng những điều kiện bắt buộc theo policy.

Một import “chỉ dùng nội bộ” không được chèn trực tiếp trạng thái đã gửi hoặc đã duyệt với các trường placeholder để vượt service nghiệp vụ.

## 15. Concurrency, retry và audit

### 15.1. Kiểm tra và nhận bước chuyển phải cùng bảo vệ một candidate

Các cuộc đua cần xét:

```text
T1 kiểm tra draft đã đủ dữ liệu.
T2 xóa invoice hoặc đổi purpose.
T1 đặt state=SUBMITTED dựa trên lần đọc cũ.
```

Hoặc:

```text
T1 tính rule trên phiên bản hóa đơn có số tiền nhỏ.
T2 thay phiên bản nguồn thành số tiền lớn.
T1 nhận hồ sơ mà không có bằng chứng bổ sung.
```

Khóa, version và snapshot nguồn phải bảo đảm dữ liệu nhận chính là dữ liệu được đánh giá, hoặc làm thao tác cạnh tranh thất bại để được kiểm tra lại.

### 15.2. Idempotency không thay việc kiểm tra điều kiện

Key mới không cho phép gửi một hồ sơ còn thiếu. Cùng key của một lần gửi đã commit có thể trả receipt cũ sau kiểm tra quyền đọc hoặc truy cập phù hợp, không gửi hồ sơ lần nữa.

Nếu lần gửi thất bại và transaction rollback, không ghi một receipt thành công. Nếu request đã commit nhưng response bị mất, lần retry phải nhận diện được kết quả đã có theo hợp đồng.

### 15.3. Audit cần giữ lý do hồ sơ được coi là đủ

Audit có thể ghi action, actor, tenant, request ID, version trước và sau, policy revision, snapshot nguồn và tham chiếu bằng chứng đã được chấp nhận.

Không chỉ ghi `validationPassed=true` mà không thể xác định dữ liệu và rule nào đã được dùng. Đồng thời, không cần sao chép toàn bộ tài liệu nhạy cảm vào log; tham chiếu bất biến và quyền truy cập phù hợp thường dễ quản lý hơn.

Một lần thử bị từ chối cần được phân biệt với hồ sơ đã gửi thành công. Nếu transaction rollback, bản ghi audit cùng transaction cũng có thể mất; đường ghi sự kiện thất bại cần được thiết kế riêng nếu có yêu cầu theo dõi.

## 16. Kiểm thử các tình huống tấn công logic

### 16.1. Hiện diện, miền giá trị và trạng thái

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Lưu draft thiếu một trường được phép để sau | Draft được lưu nhưng không bị coi là đã sẵn sàng gửi |
| Gửi duyệt thiếu từng trường bắt buộc | Không chuyển trạng thái và không tạo sự kiện thành công |
| Gửi `null`, chuỗi rỗng hoặc chỉ khoảng trắng | Xử lý đúng định nghĩa từng trường |
| Object con có mặt nhưng các trường con thiếu | Không qua chỉ nhờ object khác null |
| Mảng evidence không rỗng nhưng không có phần tử dùng được | Vẫn bị từ chối khi rule cần bằng chứng |
| Giá trị 0 hoặc false hợp lệ cho một trường cụ thể | Không bị báo thiếu sai vì kiểm tra chung quá rộng |
| Giá trị 0 không hợp lệ cho khoản phải thanh toán dương | Bị chặn theo miền giá trị |
| Body thêm `approved=true`, `createdBy` hoặc trạng thái đích | Không thay nguồn quyền hoặc state machine |

### 16.2. Tham chiếu và yêu cầu có điều kiện

1. Hóa đơn đúng cú pháp nhưng thuộc tenant khác.
2. Trung tâm chi phí tồn tại nhưng actor không được đề nghị chi từ đó.
3. Hóa đơn đã bị hủy, thay thế hoặc chưa được chấp nhận.
4. Evidence thuộc hồ sơ khác hoặc mới chỉ upload xong.
5. Bỏ trường dùng để xác định nhánh có yêu cầu bổ sung.
6. Đặt cờ rủi ro thấp trong khi số tiền nguồn thuộc nhánh phải giải trình.
7. Đổi loại hồ sơ để tìm nhánh ít yêu cầu hơn mà không đáp ứng điều kiện đổi loại.
8. Gửi một file tên như bằng chứng phê duyệt nhưng không có quyết định thật.
9. Thay tiền tệ hoặc tỷ giá do client khai để tránh ngưỡng điều kiện.

Kết quả cần kiểm tra là policy dựa trên dữ liệu có thẩm quyền và bằng chứng thật sự dùng được, không chỉ một danh sách trường xuất hiện trong JSON.

### 16.3. PATCH, version và concurrency

Dùng transaction độc lập với barrier hoặc latch để điều khiển lịch, không dùng `sleep` làm bằng chứng đã kiểm thử cuộc đua.

```text
A. Một request gửi duyệt, request khác xóa trường bắt buộc của draft.
   Kết quả: không commit được trạng thái SUBMITTED thiếu điều kiện.

B. Một request gửi duyệt, nguồn hóa đơn thay version hoặc số tiền.
   Kết quả: candidate và rule khớp cùng nguồn được bảo vệ,
   hoặc thao tác bị từ chối để đánh giá lại.

C. Bản vá bỏ qua field và bản vá chủ động xóa field.
   Kết quả: hai ý định được phân biệt theo hợp đồng PATCH.

D. Rule thay đổi trong khi bản xem trước còn mở.
   Kết quả: commit dùng revision có thẩm quyền theo policy,
   không coi bản xem trước là một quyền miễn kiểm tra.
```

Kiểm tra thêm endpoint cập nhật chung sau gửi duyệt để chứng minh không thể xóa dữ liệu nền hoặc thay nội dung mà giữ nguyên phê duyệt cũ.

### 16.4. Lỗi transaction, retry và các đường vào khác

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Lỗi audit hoặc outbox bắt buộc | State, snapshot và receipt không commit nửa vời |
| Mất response sau commit | Retry cùng key không tạo thêm lần gửi |
| Cùng key nhưng đổi ý định hoặc expected version theo hợp đồng | Xung đột, không tái diễn giải request cũ |
| Client cũ không biết trường mới | Không tự được miễn policy hiện hành áp dụng |
| CSV hoặc batch thiếu trường | Không chèn thẳng hồ sơ đã gửi với placeholder |
| Queue gọi action tương đương | Cùng kiểm tra domain và quyền theo đối tượng |
| Policy không xác định được hoặc nguồn xác minh lỗi | Không mặc định hồ sơ đã đủ |
| Chỉ thiếu dữ liệu của một phần tử trong batch | Hành vi nguyên tử hoặc từng phần đúng hợp đồng, không báo toàn bộ thành công sai |

### 16.5. Kiểm thử theo biến đổi một yếu tố

Từ một candidate hợp lệ, lần lượt xóa, làm trống hoặc làm mất hiệu lực từng dữ liệu mà rule đang yêu cầu. Kết quả phải chặn bước gửi tương ứng mà không làm phát sinh hiệu ứng thành công.

Sau đó thử các trường không bắt buộc hoặc những trường có giá trị 0, false hợp lệ để phát hiện việc từ chối quá mức. Mục tiêu là đúng chính sách, không phải càng nhiều lỗi validation càng tốt.

Kiểm tra cả trạng thái, version, snapshot nguồn, bằng chứng, audit và outbox. Mock repository không chứng minh được khóa, constraint và ranh giới commit của cơ sở dữ liệu thực.

## 17. Các lỗi thiết kế cần tránh

| Cách làm | Vì sao tạo lỗ hổng logic | Hướng thay thế |
| --- | --- | --- |
| Chỉ đặt `required` trên giao diện | Caller có thể gửi HTTP trực tiếp | Kiểm tra ở service nhận action |
| Mọi trường khác null là đủ | Không kiểm tra nghĩa, scope hoặc trạng thái | Validator nghiệp vụ trên candidate có thẩm quyền |
| Dữ liệu chọn nhánh thiếu thì chọn nhánh nhẹ | Có thể né yêu cầu có điều kiện | Báo chưa đủ thông tin để đánh giá |
| Client tự khai đã duyệt hoặc đã xác minh | Biến dữ liệu đầu vào thành bằng chứng quyền | Nguồn quyết định và xác minh do server kiểm tra |
| Chấp nhận ID vì đúng UUID | Có thể tham chiếu sai tenant hoặc sai quan hệ | Tra cứu và cấp quyền theo đối tượng |
| Đếm số file thay kiểm tra bằng chứng | File có thể không liên quan hoặc chưa đủ điều kiện | Loại, quan hệ, trạng thái và version bằng chứng |
| Điền placeholder để qua schema | Hồ sơ có vẻ đầy đủ nhưng không có thông tin thật | Mô hình draft hoặc snapshot theo trạng thái |
| Kiểm tra bản cũ rồi lưu bản mới | Candidate được nhận chưa qua rule | Kiểm tra đúng dữ liệu cuối trong giao thức concurrency |
| Cho cập nhật chung xóa field sau duyệt | Giữ bằng chứng cũ trên nội dung mới | Action sửa đổi hoặc rút hồ sơ có điều kiện riêng |
| Có idempotency nên không cần constraint nghiệp vụ | Key mới vẫn có thể tạo nghĩa vụ trùng | Ràng buộc theo nguồn hoặc intent khi policy yêu cầu |
| Import nội bộ được bỏ validation | Tạo đường đi tắt vào trạng thái được bảo vệ | Cùng invariant ở mọi điểm vào |
| Policy mới làm tự điền dữ liệu lịch sử | Viết lại bằng chứng thay vì tái xác nhận | Revision và quy trình chuyển đổi minh bạch |

## 18. Bài tập thiết kế

Thiết kế chức năng gửi duyệt đề nghị thanh toán từ hóa đơn đã xác minh. Draft được phép thiếu dữ liệu; gửi duyệt cần invoice, cost center, purpose và bằng chứng bổ sung khi policy theo loại hồ sơ hoặc số tiền áp dụng.

Hãy mô tả:

1. Những trường nào do người dùng đề nghị, những dữ liệu nào phải do server xác định?
2. Điều kiện đủ khác nhau giữa lưu draft, gửi duyệt, duyệt và thực thi như thế nào?
3. Không có dữ liệu phân loại hoặc số tiền nguồn thì policy có được chọn nhánh ít yêu cầu không?
4. Một evidence ID phải qua những kiểm tra nào để đáp ứng yêu cầu?
5. PATCH phân biệt không sửa và xóa giá trị ra sao?
6. Candidate, hóa đơn nguồn và rule revision được giữ nhất quán khi có thay đổi đồng thời thế nào?
7. Sau khi gửi hoặc duyệt, những trường nào bị khóa và những sửa đổi nào buộc đánh giá lại?
8. Những test nào chứng minh web, import, batch và queue đều không thể gửi hồ sơ thiếu điều kiện?

Một thiết kế đạt yêu cầu phải xác định rõ thông tin nào thật sự bắt buộc cho từng hành động, nguồn nào chứng minh thông tin đó và điều gì ngăn hệ thống nhận một bước nghiệp vụ trên dữ liệu còn thiếu, sai phạm vi hoặc đã mất hiệu lực.
