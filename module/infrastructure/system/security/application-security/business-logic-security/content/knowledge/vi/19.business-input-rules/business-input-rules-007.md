# Validation error semantics — Ngữ nghĩa lỗi kiểm tra dữ liệu nghiệp vụ

## 1. Một thông báo lỗi là một phần của hợp đồng nghiệp vụ

Khi API trả lỗi, client cần hiểu không chỉ câu chữ mà cả ý nghĩa xử lý: request đã được nhận chưa, có phải sửa dữ liệu không, có được gửi lại không và lần gửi lại có thể tạo hiệu ứng trùng không.

Ví dụ, ba tình huống sau không thể được biểu diễn an toàn bằng cùng một thông báo “Dữ liệu không hợp lệ”:

- Hồ sơ thiếu mục đích thanh toán, chưa được gửi duyệt.
- Hồ sơ đã được người khác sửa, request đang dùng version cũ.
- Lệnh thanh toán có thể đã được nhận nhưng response bị mất.

Nếu client hiểu tình huống cuối như lỗi dữ liệu, nó có thể tạo request mới với key mới và làm phát sinh lần chi thứ hai. Nếu server trả chi tiết quá sớm, thông báo lỗi cũng có thể tiết lộ hóa đơn, người nhận hoặc trạng thái của đối tượng ngoài quyền truy cập.

**Validation error semantics** là việc định nghĩa chính xác lỗi có nghĩa gì đối với input, quyền truy cập, trạng thái nghiệp vụ, kết quả xử lý và hành động phục hồi.

Bài học dùng quy trình gửi duyệt đề nghị thanh toán làm ví dụ, đồng thời chỉ ra những khác biệt khi có command bất đồng bộ hoặc tác động ra hệ thống bên ngoài.

## 2. Đừng gộp mọi thất bại thành lỗi validation

| Nhóm thất bại | Câu hỏi chính | Ví dụ | Hướng xử lý thường gặp |
| --- | --- | --- | --- |
| Cú pháp hoặc kiểu dữ liệu | Request có đọc được theo hợp đồng không? | JSON hỏng, ID không đúng định dạng | Sửa cách tạo request |
| Xác thực | Đã xác định được danh tính hợp lệ chưa? | Credential không hợp lệ | Xác thực lại theo cơ chế hệ thống |
| Phân quyền | Chủ thể có được thực hiện hoặc biết chi tiết không? | Dùng ID hồ sơ tenant khác | Không truy cập trái phép; không chỉ sửa field để thử lại |
| Validation nghiệp vụ | Candidate có đủ điều kiện theo rule không? | Thiếu giải trình hoặc bằng chứng chưa đạt | Sửa dữ liệu hoặc bổ sung bằng chứng |
| Xung đột trạng thái hoặc version | Request có dựa trên trạng thái còn phù hợp không? | Draft đã bị sửa hoặc hồ sơ đã đóng | Đọc lại tài nguyên và quyết định lại |
| Trùng ý định hoặc dùng key sai | Đang retry cùng command hay tạo command khác? | Cùng key nhưng đổi nội dung | Làm theo hợp đồng idempotency |
| Lỗi tạm thời của nguồn cần thiết | Có thể đánh giá đủ điều kiện không? | Nguồn xác minh không sẵn sàng | Chờ hoặc thử lại theo chính sách |
| Kết quả xử lý chưa xác định | Có thể khẳng định command chưa được nhận không? | Mất kết nối quanh commit hoặc timeout nhà cung cấp | Tra cứu hoặc retry đúng command, không tạo hiệu ứng mới |

Phân loại là để hướng dẫn đúng hành động và giữ bất biến, không phải để gán một mã HTTP cố định cho mọi trường hợp có tên tương tự.

Một lỗi không thể đánh giá policy vì thiếu nguồn không đồng nghĩa input sai. Một timeout sau khi gửi yêu cầu ra ngoài không chứng minh nghiệp vụ đã thất bại.

## 3. Xác định lỗi thuộc action nào và candidate nào

Validation phải gắn với ý định nghiệp vụ cụ thể:

```text
validate(candidate, action, policy_revision, trusted_context)
```

Một bản nháp có thể được lưu khi còn thiếu thông tin nhưng không được gửi duyệt. Một hồ sơ đã gửi không được chỉnh các trường trọng yếu bằng endpoint lưu draft.

Ví dụ:

| Action | Tình huống | Ngữ nghĩa phù hợp |
| --- | --- | --- |
| Lưu draft | Mục đích còn để trống và policy cho phép chuẩn bị dần | Không nhất thiết là lỗi |
| Gửi duyệt | Mục đích bắt buộc nhưng trống | Lỗi điều kiện gửi duyệt |
| Gửi duyệt | Hồ sơ không còn ở `DRAFT` | Xung đột action với trạng thái hiện tại |
| Duyệt | Bằng chứng thuộc content version cũ | Không đủ bằng chứng cho nội dung đang duyệt |
| Nhận thực thi | Phê duyệt hết hiệu lực tại gate | Không còn điều kiện cấp quyền thực thi mới |

Không dùng một cờ `valid=false` mà không biết nó có nghĩa cho bước nào. Cũng không báo lỗi theo bản dữ liệu cũ rồi lưu một candidate khác.

### 3.1. Điều kiện nghiệp vụ và lỗi kỹ thuật cần ranh giới

“Không có bằng chứng bắt buộc” khác với “không kết nối được kho bằng chứng”. Trường hợp đầu có thể hướng người dùng bổ sung. Trường hợp sau không nên khiến người dùng tải thêm file hoặc đổi nội dung để vượt một sự cố hệ thống.

## 4. Hợp đồng lỗi gồm những thành phần nào?

Một cấu trúc minh họa:

```json
{
  "code": "PAYMENT_SUBMISSION_INVALID",
  "message": "Chưa thể gửi duyệt. Hãy kiểm tra các thông tin được đánh dấu.",
  "operationOutcome": "NOT_ACCEPTED",
  "recovery": {
    "action": "EDIT_INPUT"
  },
  "violations": [
    {
      "code": "REQUIRED_FOR_SUBMISSION",
      "field": "purpose"
    },
    {
      "code": "USABLE_EVIDENCE_REQUIRED",
      "field": "evidenceReferences"
    }
  ],
  "correlationId": "req-c7c2f04b"
}
```

Đây là hợp đồng ứng dụng được chọn cho bài, không phải một bộ field bắt buộc chung cho mọi API.

| Thành phần | Ý nghĩa |
| --- | --- |
| `code` | Mã ổn định mô tả loại thất bại ở mức action |
| `message` | Giải thích phù hợp cho người dùng, có thể bản địa hóa |
| `operationOutcome` | Điều server biết về việc nhận xử lý ý định tương ứng |
| `recovery.action` | Hướng phục hồi có cấu trúc, không phải một quyền mới |
| `violations` | Những lỗi field hoặc rule được phép tiết lộ |
| `correlationId` | Liên kết lần gọi với dữ liệu điều tra phía server |

Không bắt client phân tích chuỗi `message` để quyết định có retry hoặc có giữ nguyên key không. Chuỗi dịch có thể thay đổi mà ngữ nghĩa xử lý không thay đổi.

### 4.1. Mã lỗi khác với tên exception

Những tên như `NullPointerException`, mã lỗi driver hoặc tên constraint nội bộ không nên tự trở thành hợp đồng công khai.

Server cần ánh xạ những tình huống đã biết sang mã nghiệp vụ ổn định. Một lỗi lập trình không nên bị đổi tên thành lỗi người dùng chỉ để tránh trả lỗi hệ thống.

### 4.2. Tham số thông báo phải có danh sách cho phép

Có thể trả giới hạn hợp lệ nếu người gọi được phép biết, chẳng hạn số phần tử tối đa. Không tự đính kèm toàn bộ giá trị bị từ chối, số tài khoản, token hoặc dữ liệu của đối tượng tham chiếu.

Tham số cần có kiểu, giới hạn kích thước và quy tắc hiển thị. Không truyền thẳng `exception.getMessage()` hoặc cả entity vào response.

## 5. Kết quả nhận xử lý phải được diễn đạt riêng

Một mô hình hữu ích gồm:

| `operationOutcome` | Ý nghĩa cần bảo đảm |
| --- | --- |
| `NOT_ACCEPTED` | Ý định đang được phản hồi chưa được nhận thành công theo hợp đồng của action |
| `ACCEPTED` | Đã có command hoặc thay đổi được nhận bền vững; công việc tiếp theo có thể chưa hoàn tất |
| `UNKNOWN` | Server chưa có đủ bằng chứng để kết luận việc nhận hoặc hiệu ứng liên quan |

Chỉ trả `NOT_ACCEPTED` khi hệ thống thực sự có cơ sở cho khẳng định đó. Không suy từ mã `500`, timeout hay mất kết nối rằng mọi thay đổi chắc chắn đã rollback.

### 5.1. Validation trước ghi dữ liệu

Nếu action chưa tạo command, chưa ghi hiệu ứng và validation đã từ chối candidate trước bước ghi, server thường có thể kết luận không nhận ý định đó.

Nếu đã ghi dữ liệu rồi gặp lỗi, cần biết transaction đã rollback theo bảo đảm nào. Nếu tình trạng commit không rõ hoặc đã có tác động ngoài transaction, phản hồi không được khẳng định kết quả mà hệ thống chưa biết.

### 5.2. Chấp nhận chưa có nghĩa hoàn tất

Một request bất đồng bộ có thể trả `202 Accepted` cùng operation ID hoặc status URL. Điều đó không có nghĩa tiền đã chuyển hoặc mọi bước đã thành công.

Nếu validation nghiệp vụ cuối được thực hiện bởi worker, API cần nói rõ nó mới nhận công việc, chưa kết luận mọi điều kiện của bước sau đều đạt. Kết quả của operation phải thể hiện những thất bại về sau theo mô hình trạng thái đã định nghĩa.

### 5.3. Tránh diễn giải sai lỗi dùng lại key

Khi cùng key được gửi với nội dung khác, việc từ chối nội dung mới không chứng minh command gốc chưa được nhận. Client phải kiểm tra command gốc nếu cần, thay vì đọc một mã lỗi rồi kết luận có thể tạo hiệu ứng mới an toàn.

Phạm vi của mọi phát biểu về kết quả phải rõ: ý định nào, key nào và command nào đang được nói đến.

## 6. Mã HTTP và mã nghiệp vụ hỗ trợ nhau

Một cách ánh xạ nhất quán cho ví dụ:

| Tình huống | HTTP minh họa | Mã nghiệp vụ minh họa |
| --- | --- | --- |
| JSON hoặc kiểu dữ liệu không đọc được | `400` | `INPUT_MALFORMED` |
| Request vượt giới hạn kích thước | `413` | `REQUEST_TOO_LARGE` |
| Danh tính không hợp lệ | `401` | `AUTHENTICATION_REQUIRED` |
| Không có quyền action trên đối tượng được phép nhận biết | `403` | `ACTION_NOT_ALLOWED` |
| Không có đối tượng trong phạm vi được phép tra cứu | `404` | `RESOURCE_NOT_FOUND` |
| Candidate đọc được nhưng không đạt rule gửi duyệt | `422` | `PAYMENT_SUBMISSION_INVALID` |
| Version hoặc trạng thái không còn phù hợp | `409` | `RESOURCE_VERSION_CONFLICT` hoặc `STATE_CONFLICT` |
| Cùng key nhưng khác ý định | `409` | `IDEMPOTENCY_KEY_REUSED` |
| Nguồn bắt buộc tạm thời không sẵn sàng | `503` | `VALIDATION_DEPENDENCY_UNAVAILABLE` |
| Lỗi ngoài dự kiến | `500` | `PROCESSING_FAILED` |

Hệ thống có thể chọn cách phân chia một số lỗi input khác, nhưng phải thống nhất và tài liệu hóa. Không ép mọi lỗi vào `400`, cũng không trả `200` với `success=false` rồi kỳ vọng các thành phần trung gian hiểu cùng một nghĩa.

Mã HTTP không tự cho biết command đã commit hay chưa. Một lỗi `500` có thể xuất hiện trước hoặc sau điểm nhận bền vững. Hướng phục hồi phải dựa thêm trên hợp đồng operation và idempotency.

### 6.1. `403` hay `404` là quyết định về tiết lộ

Có thể dùng phản hồi không tìm thấy cho cả đối tượng không tồn tại và đối tượng ngoài phạm vi tra cứu, nếu chính sách muốn hạn chế xác nhận sự tồn tại.

Không chỉ đổi status rồi vẫn trả `currentState`, owner hoặc lý do “hóa đơn thuộc tenant B”. Cấu trúc, field và chi tiết lỗi cũng phải tuân theo cùng chính sách tiết lộ.

## 7. Field error, cross-field error và lỗi cấp action

### 7.1. Lỗi một field

Ví dụ `purpose` bắt buộc hoặc số lượng phải dương. Field path cần ổn định theo hợp đồng API, không phải tên thuộc tính Java hoặc cột dữ liệu tự động lộ ra ngoài.

```json
{
  "code": "REQUIRED_FOR_SUBMISSION",
  "field": "purpose"
}
```

### 7.2. Lỗi quan hệ nhiều field

Ví dụ một loại yêu cầu cần đúng một trong hai nguồn chứng minh, hoặc ngày kết thúc phải sau ngày bắt đầu. Không nên gắn tùy tiện lỗi vào một field rồi khiến người dùng sửa sai chỗ.

```json
{
  "code": "EXACTLY_ONE_SOURCE_REQUIRED",
  "relatedFields": ["invoiceId", "advanceRequestId"]
}
```

Các field liên quan và mã lỗi phải do rule phía server xác định từ danh sách cho phép. Không lấy một chuỗi đường dẫn tùy ý do client gửi để xây response nội bộ.

### 7.3. Lỗi không có field cần sửa

Một hồ sơ đã đóng hoặc một phiên bản đã cũ không nhất thiết có field nào sửa được để giải quyết. Trả lỗi cấp action cùng hướng đọc lại tài nguyên hoặc quy trình tiếp theo.

Không đánh dấu field số tiền là sai nếu vấn đề thật là quyền không còn hoặc hệ thống xác minh đang lỗi.

### 7.4. Lỗi trong danh sách

Một path như `items[2].quantity` chỉ có ý nghĩa nếu nó tham chiếu đúng thứ tự của candidate đã đánh giá. Với danh sách có thể sắp xếp lại, có thể dùng thêm một `clientItemId` ổn định, được kiểm tra độ dài và tính duy nhất.

`clientItemId` giúp đối chiếu dòng, không phải chứng cứ quyền sở hữu. ID đối tượng và tenant vẫn phải được server kiểm tra riêng.

## 8. Thứ tự kiểm tra ảnh hưởng trực tiếp đến bảo mật

Một luồng phù hợp cho action gửi duyệt có thể là:

```text
Giới hạn request và parse an toàn
  → xác thực
  → xác định tenant và quyền trên đối tượng
  → kiểm tra idempotency đã được nhận
  → kiểm tra version và trạng thái của lần gửi mới
  → dựng candidate từ nguồn được phép
  → đánh giá rule nghiệp vụ
  → nhận thay đổi, ghi audit và outbox
```

Một số kiểm tra cú pháp hoặc giới hạn dữ liệu phải diễn ra trước khi có ngữ cảnh đầy đủ. Điều đó không cho phép đọc đối tượng ngoài quyền để trả lỗi nghiệp vụ chi tiết.

### 8.1. Không biến validation thành công cụ dò đối tượng

Ví dụ nguy hiểm:

```text
Caller không có quyền trên hóa đơn X.
Server trả: X tồn tại, đã xác minh, thiếu một phê duyệt của trưởng phòng Y.
```

Thông tin đó có thể nhạy cảm dù server chưa tạo giao dịch. Kiểm tra phạm vi trước khi dựng hoặc công bố những lỗi phụ thuộc dữ liệu được bảo vệ.

### 8.2. Không gom lỗi qua mọi lớp một cách mù quáng

Có thể gom nhiều lỗi field sau khi đã xác định người gọi được biết nội dung candidate. Không gom cả lỗi quyền, dữ liệu của đối tượng tham chiếu ngoài scope và nội dung nội bộ vào một response “tiện cho frontend”.

Một thông báo chung có thể là lựa chọn đúng cho lỗi tham chiếu không dùng được, trong khi audit giữ reason code chi tiết theo quyền điều tra.

### 8.3. Không hứa che giấu hoàn toàn chỉ bằng đổi câu chữ

Thông báo, status và dữ liệu trả về nhất quán giúp giảm rò rỉ. Thời gian xử lý, đường cache hoặc số lượng kết quả cũng có thể tạo khác biệt. Cần kiểm tra các đường đó theo mô hình đe dọa, không tuyên bố rằng dùng cùng chuỗi lỗi đã loại bỏ mọi khả năng suy đoán.

## 9. Ngữ nghĩa thời điểm và phiên bản của lỗi

Validation phản ánh candidate và policy tại lần đánh giá cụ thể, không phải một phán quyết vĩnh viễn.

Ví dụ:

- Evidence chưa đạt hôm nay có thể được chấp nhận sau khi xác minh.
- Hạn mức có thể thay đổi trước lần gửi tiếp theo.
- Bản nháp có thể được người khác sửa ngay sau khi API trả lỗi.
- Policy mới có thể yêu cầu thêm thông tin.

Client cần gắn lỗi với phiên bản biểu mẫu đã gửi. Không giữ lỗi trên field mà người dùng đã sửa rồi cho rằng đó là kết luận của candidate mới.

### 9.1. Bản xem trước không phải quyền thực thi

Endpoint kiểm tra trước có thể giúp hiển thị lỗi sớm. Đến lúc nhận hành động, server vẫn phải kiểm tra dữ liệu hiện tại hoặc xác minh snapshot được phép dùng.

Một response “validation passed” không được biến thành bearer token cho bất kỳ nội dung nào về sau. Nếu phát hành permit, nó cần ràng buộc action, đối tượng, version, nội dung, thời hạn và các nghĩa vụ theo một cơ chế riêng.

### 9.2. Lỗi version không nên bị tự sửa ngầm

Khi expected version đã cũ, không lấy version mới rồi thực hiện lại mà không xem người dùng có đang xác nhận đúng nội dung hay không. Đặc biệt với giá, số tiền, người nhận và điều kiện phê duyệt, tải lại có thể dẫn đến một ý định khác cần được xác nhận lại.

## 10. Transaction: báo lỗi phải đi cùng trạng thái dữ liệu đúng

### 10.1. Response lỗi không tự rollback dữ liệu

Ví dụ dễ gây lỗi:

```java
@Transactional
public SubmitResult submit(Command command) {
    repository.changeSomething(command);
    try {
        validator.requireBusinessRules(command);
    } catch (BusinessValidationException ex) {
        return SubmitResult.invalid(ex.publicViolations());
    }
    return SubmitResult.accepted();
}
```

Nếu ngoại lệ bị bắt và method trả bình thường, transaction có thể commit những thay đổi trước đó. Một số lỗi cơ sở dữ liệu có thể đánh dấu rollback-only, nhưng không được dựa vào hành vi đó để sửa một thiết kế bắt và nuốt lỗi nghiệp vụ.

Nên kiểm tra candidate trước khi tạo hiệu ứng khi có thể. Với các thao tác bắt buộc phải ghi rồi mới phát hiện xung đột, ngoại lệ và cấu hình transaction phải bảo đảm rollback toàn bộ phần không được chấp nhận.

### 10.2. Không gọi hệ thống ngoài rồi báo validation thất bại như chưa làm gì

Nếu đã gửi lệnh chuyển tiền hoặc tạo hiệu ứng bên ngoài, rollback cơ sở dữ liệu cục bộ không làm hiệu ứng đó biến mất. Một lỗi sau đó không thể tự được mô tả là `NOT_ACCEPTED` nếu chưa có bằng chứng phù hợp.

Dùng command bền vững, outbox, idempotency và đối soát theo ranh giới nghiệp vụ. Validation dữ liệu cần thiết nên hoàn tất trước bước nhận hiệu ứng, còn thất bại trong xử lý command phải đi theo state machine của command đó.

### 10.3. Không ghi sự kiện thành công trước commit

Một lỗi gửi duyệt không được để lại notification hoặc audit bên ngoài khẳng định đã gửi thành công trong khi transaction đã rollback.

Nhật ký thành công bắt buộc và outbox nên nằm cùng transaction với thay đổi cục bộ. Lần thử thất bại cần một loại sự kiện và đường ghi phù hợp riêng nếu hệ thống yêu cầu theo dõi.

## 11. Ví dụ Java: tách lỗi domain khỏi biểu diễn HTTP

### 11.1. Ngoại lệ chỉ chứa dữ liệu công khai đã kiểm soát

```java
public record PublicViolation(
        String code,
        String field,
        List<String> relatedFields) {
}

public final class SubmissionValidationException extends RuntimeException {
    private final List<PublicViolation> violations;

    public SubmissionValidationException(
            List<PublicViolation> safeViolations) {
        super("Submission requirements were not met");
        this.violations = List.copyOf(safeViolations);
    }

    public List<PublicViolation> violations() {
        return violations;
    }
}
```

Các code và field trong `PublicViolation` phải được tạo từ rule đã kiểm soát, không phải dữ liệu thô hoặc đường dẫn tùy ý của người gọi. Trong mã thực tế, có thể dùng kiểu enum hoặc các kiểu giá trị để giảm lỗi cấu hình và giới hạn phần được serialize.

Ví dụ này giả định `relatedFields` được tạo bất biến và hợp lệ bởi bộ ánh xạ. `List.copyOf()` ở exception không tự làm mọi object lồng nhau bất biến hoặc an toàn.

### 11.2. Service giữ ngữ nghĩa nghiệp vụ

```java
@Transactional(rollbackFor = Exception.class)
public SubmissionReceipt submit(
        VerifiedActor actor,
        SubmitCommand command) {

    PaymentRequest request = requests.lockForUpdate(
            actor.tenantId(), command.requestId())
        .orElseThrow(ResourceNotFoundException::new);

    authorization.requireSubmissionAccess(actor, request);

    var previous = idempotency.findAccepted(actor, command, request);
    if (previous.isPresent()) {
        previous.get().requireSameFingerprint(command);
        return previous.get().receipt();
    }

    request.requireDraftAtVersion(command.expectedVersion());

    SubmissionCandidate candidate = candidates.fromTrustedSources(
            actor, request, command);
    ValidationResult validation = rules.validateForSubmission(candidate);

    if (!validation.isValid()) {
        throw new SubmissionValidationException(
                publicViolations.allowedFor(actor, request, validation));
    }

    // Từ đây mới nhận thay đổi nghiệp vụ của command.
    SubmissionReceipt receipt = requests.submit(candidate);
    audits.appendSubmitted(actor, candidate, receipt);
    outbox.appendSubmitted(candidate, receipt);
    idempotency.recordAccepted(actor, command, receipt);
    return receipt;
}
```

Các repository và helper là thành phần cần triển khai, không phải một ứng dụng hoàn chỉnh. Ví dụ giả định actor đã được xác thực, command đã được kiểm tra cú pháp, dữ liệu cần thiết được bảo vệ đúng giao thức transaction và không có lời gọi tạo hiệu ứng ngoài transaction.

Service phải được gọi qua cơ chế quản lý transaction có hiệu lực. Với Spring proxy thông thường, lời gọi nội bộ trong cùng instance không tự tạo ranh giới transaction mới.

Ngoại lệ validation ở mẫu này phát sinh trước khi command tạo thay đổi nghiệp vụ. Những lỗi khác sau khi bắt đầu ghi cần cơ chế rollback và ánh xạ riêng, không được tự gọi tất cả là validation trước nhận.

### 11.3. Lớp HTTP ánh xạ những lỗi đã biết

```java
@RestControllerAdvice(assignableTypes = PaymentSubmissionController.class)
public class SubmissionErrorHandler {
    private final CorrelationIds correlationIds;

    public SubmissionErrorHandler(CorrelationIds correlationIds) {
        this.correlationIds = correlationIds;
    }

    @ExceptionHandler(SubmissionValidationException.class)
    public ResponseEntity<ApiError> invalidSubmission(
            SubmissionValidationException ex) {

        ApiError error = new ApiError(
                "PAYMENT_SUBMISSION_INVALID",
                "Chưa thể gửi duyệt. Hãy kiểm tra thông tin hồ sơ.",
                OperationOutcome.NOT_ACCEPTED,
                RecoveryAction.EDIT_INPUT,
                ex.violations(),
                correlationIds.current());

        return ResponseEntity.unprocessableEntity().body(error);
    }

    @ExceptionHandler(StaleResourceVersionException.class)
    public ResponseEntity<ApiError> staleVersion(
            StaleResourceVersionException ex) {

        ApiError error = new ApiError(
                "RESOURCE_VERSION_CONFLICT",
                "Hồ sơ đã thay đổi. Hãy tải lại trước khi gửi.",
                OperationOutcome.NOT_ACCEPTED,
                RecoveryAction.REFRESH_RESOURCE,
                List.of(),
                correlationIds.current());

        return ResponseEntity.status(HttpStatus.CONFLICT).body(error);
    }
}
```

`ApiError`, enum và controller là các kiểu minh họa cần định nghĩa; cấu trúc serialize phải thống nhất với hợp đồng API được chọn. Lỗi xác thực và phân quyền của framework cần được xử lý ở đường phù hợp, không mặc định đi qua chính handler này.

`NOT_ACCEPTED` trong hai handler dựa trên hợp đồng rằng các ngoại lệ tương ứng xảy ra trước lần nhận thay đổi của command hiện tại và chỉ được công bố sau kiểm tra quyền phù hợp. Không tái sử dụng chúng cho lỗi commit chưa xác định hoặc timeout hệ thống ngoài.

Lỗi ngoài dự kiến cần handler riêng với thông tin công khai tối thiểu. Nếu không xác định được kết quả xử lý, hướng phục hồi phải phản ánh sự chưa xác định thay vì khẳng định đã rollback.

## 12. Ánh xạ lỗi cơ sở dữ liệu có kiểm soát

Một số ràng buộc chỉ có thể được quyết định chắc chắn ở cơ sở dữ liệu khi có concurrency, chẳng hạn nguồn nghiệp vụ đã được nhận bởi request khác.

Có thể ánh xạ một constraint đã biết thành lỗi nghiệp vụ ổn định nếu:

- Xác định chính xác constraint và tình huống mà nó bảo vệ.
- Transaction được xử lý đúng sau thất bại.
- Người gọi được phép biết nội dung được công bố.
- Mã lỗi không tiết lộ entity, câu SQL hoặc dữ liệu của người khác.

Ví dụ có thể trả `SOURCE_ALREADY_IN_USE` cho một nguồn mà người gọi có quyền quản lý, thay vì lộ ID và chủ sở hữu của hồ sơ đang dùng nguồn đó.

Không đổi mọi lỗi integrity thành “invoiceId không hợp lệ”. Một lỗi khóa ngoại có thể là dữ liệu tham chiếu thay đổi, một đường ghi sai tenant hoặc một lỗi lập trình. Đánh đồng chúng làm mất tín hiệu điều tra và hướng người dùng sửa sai input.

Không gửi nguyên thông báo từ driver, stack trace hoặc tên bảng nội bộ cho client.

## 13. Retry, idempotency và lỗi chưa rõ kết quả

### 13.1. Sửa input khác với retry cùng command

| Tình huống | Ý định phục hồi |
| --- | --- |
| Validation không đạt và chắc chắn chưa nhận | Sửa dữ liệu; tạo ý định và key theo hợp đồng API |
| Version cũ | Đọc lại, xem thay đổi và xác nhận lại ý định nếu cần |
| Cùng key và cùng nội dung đã được nhận | Đọc lại receipt hoặc trạng thái của command cũ |
| Cùng key nhưng nội dung khác | Không tái diễn giải key cũ; kiểm tra command gốc và dùng hợp đồng cho ý định mới |
| Timeout hoặc kết quả chưa xác định | Tra cứu hoặc retry cùng command với cùng key theo cơ chế được hỗ trợ |
| Command đang xử lý | Theo dõi operation, không tạo command tương đương bằng key mới |

Không để client tự đổi key mỗi khi nhận một lỗi chung. Điều đó có thể biến một retry thành một hiệu ứng mới.

### 13.2. Một cờ `retryable` thường chưa đủ

`retryable=true` không nói retry cùng nội dung hay đã sửa nội dung, cùng key hay key mới, ngay lập tức hay sau khi đọc trạng thái.

Nên có hướng phục hồi có cấu trúc hoặc tài liệu đủ rõ. Ví dụ `RETRY_SAME_COMMAND` khác `REFRESH_RESOURCE`, và cả hai khác `CHECK_OPERATION_STATUS`.

Ngay cả với lỗi tạm thời, retry cần có giới hạn, thời gian chờ phù hợp và giữ định danh hiệu ứng. Đối với lỗi nghiệp vụ xác định như thiếu field, retry không đổi dữ liệu thường không giúp gì.

### 13.3. Quyền truy cập vẫn được kiểm tra khi đọc kết quả cũ

Biết idempotency key hoặc operation ID không thay thế quyền đọc. Nếu quyền đã bị thu hồi, việc trả receipt hoặc trạng thái phải tuân theo chính sách hiện tại của endpoint đọc đó.

Mặt khác, quyền đọc kết quả không tự cấp quyền tạo lại một hành động mới. Hai quyết định này cần được phân biệt trong service và hợp đồng client.

## 14. Gom lỗi, thứ tự lỗi và giới hạn tài nguyên

### 14.1. Gom lỗi sau những hàng rào phù hợp

Với một candidate mà caller được phép xem, gom nhiều lỗi field giúp người dùng sửa một lần. Tuy nhiên, không cần tiếp tục chạy những kiểm tra tốn kém hoặc không thể đánh giá khi dữ liệu nền còn thiếu.

Ví dụ chưa có hóa đơn dùng được thì không thể đánh giá chính xác rule dựa trên số tiền của hóa đơn. Có thể trả lỗi nguồn nền mà không bịa thêm kết luận “không cần bằng chứng giá trị cao”.

### 14.2. Giới hạn kích thước response lỗi

Một mảng rất lớn có thể tạo hàng chục nghìn lỗi. Cần giới hạn request, số phần tử, chi phí đánh giá và số violation trả về.

Nếu cắt bớt lỗi, có thể có cờ như `violationsTruncated=true`. Điều đó nói danh sách hiển thị chưa đầy đủ, không nói những field không xuất hiện chắc chắn đã hợp lệ.

Khi đã xác định input không đạt, có thể dừng những kiểm tra không cần thiết theo thiết kế. Nhưng đường cho phép vẫn phải đáp ứng mọi điều kiện bắt buộc; không được biến giới hạn đánh giá thành cho phép từ kết quả một phần.

### 14.3. Thứ tự và khử trùng

Có thể sắp xếp lỗi theo thứ tự field hoặc ưu tiên được công bố để kết quả ổn định. Không để thứ tự phụ thuộc ngẫu nhiên vào hash map hoặc query khiến UI và test khó hiểu.

Khử trùng theo code, field và đối tượng liên quan phù hợp. Không gộp hai lỗi khác nhau chỉ vì message tiếng Việt hiện đang giống nhau.

## 15. Batch và kết quả từng phần

Một batch cần hợp đồng rõ:

| Chế độ | Ý nghĩa |
| --- | --- |
| Toàn bộ hoặc không nhận | Một lỗi bắt buộc làm batch không tạo các hiệu ứng bị loại trừ bởi hợp đồng nguyên tử |
| Chấp nhận từng phần | Mỗi item có kết quả nhận, từ chối hoặc chưa xác định riêng |
| Nhận xử lý bất đồng bộ | API nhận batch, kết quả cuối được tra cứu ở operation tương ứng |

Ví dụ kết quả từng phần có thể dùng envelope:

```json
{
  "batchId": "batch-123",
  "mode": "PARTIAL",
  "results": [
    {
      "clientItemId": "row-1",
      "operationOutcome": "ACCEPTED",
      "operationId": "op-456"
    },
    {
      "clientItemId": "row-2",
      "operationOutcome": "NOT_ACCEPTED",
      "error": {
        "code": "PAYMENT_SUBMISSION_INVALID",
        "violations": [
          {"code": "REQUIRED_FOR_SUBMISSION", "field": "purpose"}
        ]
      }
    }
  ]
}
```

Client không được retry toàn bộ batch với những key mới chỉ vì một item thất bại. Cần định danh và idempotency tương ứng với đơn vị hiệu ứng của thiết kế.

Nếu có hạn mức dùng chung, việc từng item hợp lệ riêng lẻ không chứng minh cả tập đều được nhận. Phải giữ bất biến tổng khi nhận các item cạnh tranh.

Nếu quá trình dừng trước một số item, phân biệt chúng chưa được xử lý với item đã bị validation từ chối. Không tạo một danh sách lỗi giả cho dữ liệu mà server chưa đánh giá.

## 16. Bản địa hóa, audit và vận hành

### 16.1. Message phục vụ người dùng, code phục vụ hợp đồng

Có thể thay đổi câu chữ tiếng Việt hoặc ngôn ngữ khác mà giữ code và recovery action ổn định. Client không nên quyết định logic bằng cách so chuỗi “thiếu”, “đã tồn tại” hoặc “hãy thử lại”.

Khi đổi tên field trong API, cần chiến lược tương thích cho error path. Không để một refactor entity nội bộ tự đổi hợp đồng lỗi công khai.

### 16.2. Audit cần nhiều hơn response công khai

Log nội bộ được phân quyền có thể ghi action, actor, tenant, object ID, version, policy revision, rule đã đánh giá, kết quả operation và correlation ID.

Không vì cần điều tra mà ghi toàn bộ body, token hoặc chứng từ nhạy cảm. Correlation ID nên do hệ thống quản lý theo chính sách, không để một chuỗi tùy ý từ client phá cấu trúc log hoặc thay danh tính request khác.

### 16.3. Phân biệt lỗi người dùng với dấu hiệu hệ thống

| Tín hiệu | Điều cần xem xét |
| --- | --- |
| Nhiều lỗi bắt buộc ở cùng một client version | UI hoặc client có thể không biết policy mới |
| Nhiều tham chiếu ngoài tenant | Có thể đang dò đối tượng hoặc có lỗi scope |
| Tăng lỗi version | Có cạnh tranh, dữ liệu cũ hoặc cơ chế cập nhật chưa phù hợp |
| Nhiều key trùng với fingerprint khác | Client đang tái dùng key sai hoặc đổi ý định không đúng hợp đồng |
| Tăng lỗi nguồn validation không sẵn sàng | Không nên bị che thành input sai |
| `UNKNOWN` tăng quanh commit hoặc provider | Cần kiểm tra khả năng tra cứu, retry và đối soát |
| Response báo lỗi nhưng có sự kiện thành công | Có thể có vấn đề ranh giới transaction hoặc phát event trước commit |

Khi cảnh báo, cần giữ ngữ cảnh đủ để phân biệt sự cố client, thay đổi policy và hành vi lạm dụng; không kết luận mọi validation failure đều là tấn công.

## 17. Kiểm thử ngữ nghĩa lỗi như một phần của bảo mật

### 17.1. Kiểm thử hợp đồng

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| JSON hỏng hoặc kiểu sai | Mã cú pháp ổn định, không đi vào nghiệp vụ |
| Thiếu trường bắt buộc ở bước gửi | Lỗi field đúng action và `NOT_ACCEPTED` có cơ sở |
| Bản nháp được phép thiếu | Không bị từ chối sai chỉ vì dùng validator của bước gửi |
| Field đơn, cross-field và lỗi action | Đường dẫn và cấp lỗi phản ánh đúng chỗ cần xử lý |
| Thay ngôn ngữ message | Code, outcome và recovery không đổi ngữ nghĩa |
| Violation rất nhiều | Response bị giới hạn theo hợp đồng, không cấp quyền từ kiểm tra một phần |
| Giá trị nhạy cảm bị từ chối | Không bị phản chiếu vào response hoặc log ngoài chính sách |

### 17.2. Kiểm thử không tiết lộ ngoài quyền

So sánh truy cập tới ID không tồn tại và ID ngoài scope theo chính sách phản hồi của hệ thống. Kiểm tra cả body, code, metadata và những chi tiết phụ thuộc đối tượng.

Một caller không có quyền không được biết hóa đơn đã xác minh, tên owner, số tiền hoặc thiếu người duyệt nào thông qua validation. Đồng thời, người có quyền hợp lệ vẫn cần nhận được hướng dẫn sửa phù hợp trong phạm vi được phép.

Kiểm tra các đường batch, tìm kiếm, import và endpoint xem trước, không chỉ API gửi chính.

### 17.3. Kiểm thử transaction và kết quả chưa rõ

Chèn lỗi có kiểm soát tại các điểm:

```text
A. Validation từ chối trước bước ghi.
   Kết quả: không có thay đổi, command hay sự kiện thành công mới.

B. Sau khi đổi state nhưng trước audit hoặc outbox bắt buộc.
   Kết quả: transaction rollback toàn bộ thay đổi cục bộ bắt buộc;
   response không được dựa vào một success record chưa commit.

C. Commit thành công nhưng response bị mất.
   Kết quả: retry cùng key tìm được command cũ, không tạo hiệu ứng mới.

D. Đã gửi provider nhưng chưa biết kết quả.
   Kết quả: không báo input sai và hướng tạo command mới;
   đi theo tra cứu hoặc đối soát đúng định danh hiệu ứng.
```

Nếu tình trạng commit không xác định, test phải kiểm tra rằng hợp đồng không khẳng định `NOT_ACCEPTED` thiếu cơ sở. Mock repository không chứng minh được hành vi rollback hoặc sự cố kết nối quanh commit thực tế.

### 17.4. Kiểm thử retry, version và batch

1. Cùng key và nội dung đã nhận trả lại receipt, không kiểm tra lại như một lần tạo hiệu ứng mới.
2. Cùng key nhưng nội dung khác trả xung đột mà không làm mất dấu command gốc.
3. Lỗi version yêu cầu đọc lại, không tự thay expected version rồi thực thi âm thầm.
4. Sửa input sau một lỗi chắc chắn chưa nhận tuân theo hợp đồng key của API.
5. Batch từng phần không khiến item thành công bị thực hiện lại vì item khác lỗi.
6. Item chưa đánh giá không bị ghi thành validation đã thất bại.
7. Quyền đọc receipt bị thu hồi thì key không thành đường lấy dữ liệu trái phép.
8. Parser, validator và mapper không lộ stack trace, SQL hoặc entity nội bộ.

### 17.5. Những assertion quan trọng

Không chỉ assert status `422` hoặc chuỗi message. Hãy kiểm tra code, field path, operation outcome, recovery action, quyền được tiết lộ và trạng thái dữ liệu sau request.

Với nội dung đa ngôn ngữ, ưu tiên assert mã và tham số có cấu trúc cho logic xử lý. Test thông điệp hiển thị phục vụ mục tiêu riêng, không nên là nền tảng duy nhất của hợp đồng API.

## 18. Các lỗi thiết kế cần tránh và bài tập

| Cách làm | Vì sao gây lỗi nghiệp vụ | Hướng thay thế |
| --- | --- | --- |
| Mọi thất bại là “invalid input” | Client sửa sai chỗ hoặc tạo lại hiệu ứng | Phân loại theo input, quyền, trạng thái và kết quả xử lý |
| Trả lỗi đồng nghĩa chắc chắn chưa làm gì | Có thể đã commit hoặc có hiệu ứng ngoài transaction | Outcome có cơ sở và cơ chế tra cứu |
| Retry bằng key mới sau mọi lỗi | Có thể nhân đôi command đã được nhận | Retry cùng ý định đúng key khi kết quả chưa rõ |
| Response lỗi tự động rollback | Method trả bình thường vẫn có thể commit | Ranh giới exception và transaction rõ ràng |
| Hiển thị nguyên exception | Lộ schema, dữ liệu hoặc bí mật | Mã công khai ổn định và chi tiết nội bộ được phân quyền |
| Gom lỗi trước kiểm tra quyền đối tượng | Tạo công cụ dò dữ liệu | Chỉ công bố lỗi trong phạm vi caller được biết |
| Thông báo chuỗi quyết định retry | Bản địa hóa hoặc đổi câu chữ làm sai logic | Code, outcome và recovery có cấu trúc |
| Dùng preview làm quyền thực thi | Candidate hoặc policy có thể đã đổi | Kiểm tra lại tại gate hoặc permit ràng buộc chặt |
| Mọi SQL constraint là lỗi một field | Che lỗi hệ thống và dễ tiết lộ dữ liệu | Ánh xạ chính xác các trường hợp đã biết |
| Một lỗi batch khiến retry tất cả | Thực hiện lại những item đã nhận | Kết quả và idempotency đúng đơn vị hiệu ứng |

Thiết kế hợp đồng lỗi cho action gửi duyệt đề nghị thanh toán với các trường hợp: thiếu mục đích, hóa đơn không dùng được, bằng chứng chưa xác minh, version cũ, key bị tái sử dụng, nguồn policy lỗi và kết quả commit chưa xác định.

Với từng trường hợp, hãy xác định:

1. Caller được phép biết những chi tiết nào?
2. Mã lỗi, field path và HTTP status được chọn là gì?
3. Server có thể khẳng định outcome nào và dựa trên bằng chứng nào?
4. Client phải sửa dữ liệu, tải lại tài nguyên, retry cùng command hay tra cứu trạng thái?
5. Transaction và audit để lại trạng thái gì?
6. Test nào chứng minh response không làm phát sinh hiệu ứng trùng hoặc rò rỉ đối tượng ngoài quyền?

Một hợp đồng lỗi đạt yêu cầu phải giúp người dùng sửa đúng vấn đề, giúp client phục hồi đúng ý định và không làm mất sự thật về quyền truy cập hoặc trạng thái xử lý của nghiệp vụ.
