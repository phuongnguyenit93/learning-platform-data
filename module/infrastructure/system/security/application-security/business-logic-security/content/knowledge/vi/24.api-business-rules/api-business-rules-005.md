# API error consistency: nhất quán lỗi API để giữ đúng quy tắc nghiệp vụ

## 1. Mục tiêu bài học

Trong chương **API Business Rules** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **API error consistency** là việc duy trì một hợp đồng lỗi có ý nghĩa thống nhất giữa các endpoint và các đường xử lý.

Nhất quán không chỉ là mọi response đều có field message. Client còn cần hiểu lỗi gì đã xảy ra, có thay đổi nghiệp vụ nào được xác nhận không, có được gửi lại không và phải dùng cùng định danh thao tác hay tạo một ý định mới.

Nếu lỗi bị diễn giải sai, client có thể gửi trùng khoản chi, hiển thị thành công sau rollback, thử lại bằng key mới khi lần trước có thể đã commit hoặc dò dữ liệu ngoài quyền qua các thông báo khác nhau.

Sau bài học, bạn có thể:

- Thiết kế mã lỗi và cấu trúc response ổn định theo ý nghĩa nghiệp vụ.
- Phân biệt lỗi input, quyền, trạng thái, xung đột, phụ thuộc và kết quả chưa xác định.
- Liên kết error response với transaction, idempotency và trạng thái operation.
- Giữ lỗi không làm lộ tenant, đối tượng, policy hoặc dữ liệu nhạy cảm.
- Áp dụng cùng ngữ nghĩa qua sync, async, batch, alias và client khác nhau.
- Kiểm thử cả response lẫn dữ liệu đã commit và hành vi retry của client.

## 2. Vì sao lỗi API là một phần của bảo mật logic?

Xét một command approve refund:

~~~text
Client gửi approve.
Server ghi quyết định và commit.
Response bị mất hoặc quá trình trả response lỗi.
Client nhận timeout/500.
Client tưởng chưa xử lý và gửi lại với key mới.
~~~

Nếu backend cũng thiếu state/idempotency guard, một lỗi báo kết quả có thể trở thành thêm một hiệu ứng nghiệp vụ.

Một số sai lệch khác:

| Lỗi không nhất quán | Hệ quả có thể xảy ra |
|---|---|
| Endpoint A dùng 403, endpoint B trả 200 và danh sách rỗng khi cùng bị chặn | Client hiểu nhầm lỗi quyền thành không có dữ liệu hoặc bỏ kiểm soát |
| Cùng lỗi version nhưng endpoint này nói invalid input, endpoint khác khuyên retry ngay | Client lặp dữ liệu cũ thay vì tải lại |
| Mọi timeout đều ghi “chưa có thay đổi” | Phát sinh yêu cầu mới dù hiệu ứng có thể đã xảy ra |
| Refund không tồn tại và refund ngoài tenant có chi tiết khác nhau | Dò tồn tại và thông tin đối tượng ngoài quyền |
| Batch báo thành công chung dù có phần tử thất bại | Tự động hóa hành động tiếp theo trên kết quả sai |
| Exception phụ thuộc được biến thành lỗi input | Người dùng sửa request vô ích hoặc luồng xử lý bỏ qua kiểm tra đang lỗi |
| Message được dùng như mã máy | Đổi ngôn ngữ hoặc câu chữ làm client chọn sai nhánh xử lý |

Một error contract rõ không thay thế transaction và authorization. Nó giúp các lớp tiếp theo không phá ý nghĩa của những kiểm soát đó.

## 3. Những chiều cần nhất quán

| Chiều | Câu hỏi phải trả lời |
|---|---|
| HTTP status | Kết quả giao tiếp thuộc nhóm nào theo hợp đồng endpoint? |
| Public error code | Điều kiện thất bại ổn định nào được công bố? |
| Safe message | Caller được biết và cần biết gì để xử lý? |
| Field violations | Những lỗi input nào có thể chỉ ra an toàn? |
| Execution outcome | Server biết gì về việc command đã tạo hiệu ứng? |
| Recovery | Client nên dừng, tải lại, đăng nhập lại, chờ hay tra operation? |
| Correlation | Dùng ID nào để nối request, command và operation? |
| Disclosure | Có lộ dữ liệu hoặc sự tồn tại ngoài quyền không? |
| Atomicity | Response có khớp trạng thái đã commit không? |
| Versioning | Code/schema cũ có còn được diễn giải đúng không? |

Không phải mọi lỗi cần có mọi field. Những field xuất hiện phải có nghĩa rõ và không khẳng định điều server chưa biết.

### 3.1. Cùng ngữ nghĩa không bắt buộc byte giống nhau

Message tiếng Việt và tiếng Anh có thể khác. Request ID, field path hoặc operation ID có thể khác.

Một error code dùng cho cùng điều kiện nghiệp vụ nên giữ ý nghĩa ổn định. Client không nên phải so chuỗi message như “Trạng thái đã đổi” để quyết định có tạo lại yêu cầu không.

HTTP status cũng có thể khác giữa response của một command và response đọc một operation đã thất bại, miễn hợp đồng phân biệt rõ hai loại kết quả.

### 3.2. Không gộp mọi thất bại vào một lỗi business

Các trường hợp sau cần phân biệt:

~~~text
Input không decode được.
Input đúng kiểu nhưng sai quy tắc field.
Caller không có quyền.
Resource/version đã đổi.
Hạn mức chung không còn đủ.
Nguồn policy không truy cập được.
Có thể đã commit nhưng chưa xác định được kết quả.
~~~

Nếu mọi trường hợp đều thành “Yêu cầu không hợp lệ”, client không có cách chọn hành vi phục hồi đúng và hệ thống mất khả năng phát hiện lỗi kiểm soát.

### 3.3. Lỗi command khác kết quả nghiệp vụ tiêu cực

POST /requests/{id}/reject có thể thực hiện thành công và tạo trạng thái REJECTED. Đây là thành công của command reject, không phải lỗi HTTP chỉ vì kết quả không phải APPROVED.

Tương tự, một operation thanh toán đã được tạo và hoàn tất với kết quả bị từ chối có thể được trả như một tài nguyên operation có trạng thái cuối rõ ràng.

Không gọi mọi trạng thái nghiệp vụ tiêu cực là “API lỗi và không có gì xảy ra”. Việc ghi operation/quyết định có thể chính là hiệu ứng đã được yêu cầu.

## 4. Một hợp đồng lỗi minh họa

Ví dụ dưới đây là schema riêng của bài học, không phải khẳng định một định dạng bắt buộc cho mọi API.

~~~json
{
  "requestId": "req-501",
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "Dữ liệu đã thay đổi. Hãy tải lại trước khi gửi quyết định.",
    "violations": []
  },
  "execution": {
    "outcome": "NOT_APPLIED"
  },
  "recovery": {
    "action": "REFRESH_RESOURCE"
  }
}
~~~

Trong ví dụ, NOT_APPLIED chỉ được dùng khi server có căn cứ command không commit thay đổi nghiệp vụ của lần thử đó, chẳng hạn bị chặn trước mutation hoặc transaction đã rollback được xác nhận.

Security log, attempt log hoặc bằng chứng từ chối vẫn có thể được ghi. NOT_APPLIED không có nghĩa không một byte nào được lưu ở bất kỳ hệ thống nào.

### 4.1. Code và message có vai trò khác nhau

Code là hợp đồng để client xử lý bằng máy. Message là nội dung an toàn cho người dùng và có thể được bản địa hóa.

Không đưa exception message thô thành public code hoặc public message. Nó có thể chứa câu SQL, tên bảng, service account, policy nội bộ hoặc dữ liệu nhạy cảm.

### 4.2. Outcome phải do server xác định

Không nhận execution.outcome hoặc retryable từ body rồi phản ánh như kết luận có thẩm quyền.

Outcome phải dựa trên ranh giới xử lý, bằng chứng commit/rollback, receipt hoặc trạng thái operation đã biết. Chỉ nhìn kiểu exception không luôn đủ để kết luận.

Khi chưa biết, không điền NOT_APPLIED để response trông đơn giản hơn.

## 5. Catalogue mã lỗi theo ý nghĩa

Bảng dưới là lựa chọn hợp đồng minh họa. Một API có thể chọn mapping khác, nhưng phải áp dụng có chủ đích và tài liệu hóa cùng ngữ nghĩa.

| Điều kiện | HTTP minh họa | Public code | Hướng phục hồi chính |
|---|---|---|---|
| JSON/kiểu/field hợp đồng không hợp lệ | 400 | INVALID_REQUEST | Sửa request |
| Vi phạm quy tắc input nghiệp vụ | 422 | INPUT_RULE_VIOLATION | Sửa field/tổ hợp giá trị |
| Chưa có xác thực được chấp nhận | 401 | AUTHENTICATION_REQUIRED | Xác thực lại theo giao thức |
| Actor thiếu quyền action trong ngữ cảnh được phép tiết lộ | 403 | ACTION_FORBIDDEN | Dừng; không tự thử danh tính/quyền khác |
| Không tìm thấy hoặc không được biết sự tồn tại | 404 | RESOURCE_NOT_FOUND | Không tiếp tục với dữ liệu ngoài quyền |
| Trạng thái không cho phép command | 409 | RESOURCE_STATE_CONFLICT | Đọc trạng thái/đường xử lý hợp lệ |
| Version không còn khớp | 409 | VERSION_CONFLICT | Tải lại, xem lại trước quyết định mới |
| Hạn mức hoàn chung không còn đủ | 409 | REFUND_CAPACITY_EXCEEDED | Đối chiếu dữ liệu hiện tại, không lặp vô hạn |
| Cùng idempotency key nhưng khác command | 409 | IDEMPOTENCY_KEY_REUSED | Tra ý định/kết quả gốc, không tự tạo key mới |
| Vượt giới hạn tần suất | 429 | RATE_LIMITED | Chờ theo hướng dẫn hợp lệ |
| Phụ thuộc không sẵn sàng | 503 | DEPENDENCY_UNAVAILABLE | Phục hồi theo outcome và hợp đồng retry |
| Lỗi hệ thống chưa được phân loại công khai | 500 | INTERNAL_ERROR | Dựa outcome/operation, không suy ra rollback |
| Không xác định được kết quả command | Tùy tình huống, có thể 503 | OUTCOME_UNKNOWN | Tra operation hoặc retry an toàn cùng ý định |

Các status code không đủ thay outcome. Cùng 503 có thể xảy ra trước hiệu ứng hoặc sau khi hiệu ứng ngoài hệ thống có khả năng đã xảy ra.

### 5.1. Validation và conflict cần tiêu chí ổn định

Trong ví dụ:

~~~text
amount âm:
    INPUT_RULE_VIOLATION.

amount đúng kiểu nhưng phần tiền còn có thể hoàn
đã bị command khác tiêu thụ:
    REFUND_CAPACITY_EXCEEDED.

expectedVersion cũ:
    VERSION_CONFLICT.
~~~

Không để một endpoint dùng “not found” cho mọi validation còn endpoint khác trả internal error từ constraint cho cùng một rule.

Nếu nhiều loại lỗi cùng thuộc một public code, phải giữ nghĩa của nhóm đó đủ rõ để client không chọn sai cách phục hồi.

### 5.2. Duplicate không luôn là cùng một loại lỗi

Cần phân biệt:

- Retry cùng key, cùng command đã hoàn tất: trả kết quả đã lưu theo quyền xem hiện tại.
- Cùng key, khác fingerprint: xung đột sử dụng key.
- Key khác nhưng trạng thái đã APPROVED: xử lý theo hợp đồng state/idempotency nghiệp vụ.
- Callback/event trùng đã áp dụng: không áp hiệu ứng lần nữa; xử lý theo giao thức nhận sự kiện.

Không gộp mọi trường hợp thành “duplicate” rồi lúc thì trả thành công, lúc thì tạo lại thao tác.

Nếu API chủ ý coi một action lặp là cùng kết quả, phải định nghĩa điều kiện nhận diện và giới hạn hiệu ứng. Không trả thành công cho mọi payload khác nhau chỉ vì resource đã có một trạng thái cuối.

### 5.3. Không công bố chi tiết không cần thiết

IDEMPOTENCY_KEY_REUSED không cần trả nguyên payload cũ hoặc thông tin của một target ngoài quyền.

RESOURCE_NOT_FOUND không cần nói đối tượng nằm trong tenant nào. VERSION_CONFLICT chỉ nên kèm dữ liệu hiện tại mà caller có quyền xem.

Public code có thể tổng quát hơn internal reason. Ví dụ nhiều lý do object access bị chặn đều được che dưới cùng một public error theo policy.

## 6. Nói đúng về kết quả thực thi

### 6.1. Ba loại kiến thức về command

Một hợp đồng có thể dùng:

| Outcome | Căn cứ cần có |
|---|---|
| NOT_APPLIED | Xác nhận command chưa tạo thay đổi nghiệp vụ được cam kết, hoặc đã rollback đầy đủ và không có hiệu ứng ngoài chưa giải quyết |
| COMMITTED | Xác nhận thay đổi/việc chấp nhận command theo hợp đồng đã bền vững |
| UNKNOWN | Chưa đủ bằng chứng để kết luận kết quả command trong phạm vi được cam kết |

COMMITTED không tự có nghĩa mọi bước của toàn workflow đã hoàn tất. Nếu API chỉ chấp nhận công việc, operation có thể còn PENDING hoặc RECONCILING.

Hợp đồng endpoint phải nói rõ nó hứa chấp nhận ý định hay hoàn tất một hiệu ứng. Đừng dùng cùng từ “thành công” cho cả tạo job và đã chi trả.

### 6.2. Rollback DB không luôn bằng chưa có hiệu ứng

Nếu đã gọi hệ thống ngoài rồi local transaction lỗi, một khoản chi có thể đã xảy ra.

Không gắn NOT_APPLIED cho toàn command chỉ vì local DB rollback. Cần đối soát operation và biểu diễn đúng mức chưa chắc chắn.

Cách an toàn hơn trong nhiều workflow là lưu ý định/operation bền vững trước hiệu ứng ngoài, dùng định danh ổn định và phục hồi kết quả theo hợp đồng. Điều đó vẫn cần idempotency và kiểm soát trạng thái ở từng ranh giới.

### 6.3. Lỗi trả response sau commit

Server có thể đã commit nhưng lỗi khi tạo hoặc gửi response. Nếu server còn đủ bằng chứng và khả năng phản hồi, nên trả/cho tra cứu kết quả đã ghi, hoặc nêu rõ command đã commit thay vì nói chưa có thay đổi.

Nếu chỉ còn một lỗi transport hoặc response hạ tầng không có body chuẩn, client không thể tự suy ra rollback. Client cần đường tra cứu/replay an toàn.

Một catch-all biến mọi exception thành INTERNAL_ERROR với outcome=NOT_APPLIED là không đúng.

### 6.4. Operation đã được nhận thì có thể trả accepted thay vì lỗi chung

Nếu server biết công việc đã được chấp nhận bền vững và đang chờ kết quả, một response accepted với operationId và trạng thái PENDING có thể rõ nghĩa hơn “thử lại từ đầu”.

Đọc operation có thể trả response thành công của truy vấn, trong đó operation đang FAILED hoặc RECONCILING. HTTP thành công của truy vấn không đổi kết quả nghiệp vụ bên trong.

Nếu kết quả thật sự chưa biết, không biến nó thành một lần thành công giả hoặc một lần thất bại chắc chắn.

## 7. Hướng dẫn retry phải đi cùng điều kiện

### 7.1. Một boolean retryable thường quá ít

Có thể dùng các hành động có định nghĩa:

~~~text
NONE:
  không tự động lặp.

REFRESH_RESOURCE:
  đọc lại và yêu cầu xem xét dữ liệu mới.

REAUTHENTICATE:
  xử lý xác thực theo giao thức, sau đó kiểm tra lại quyền.

BACKOFF_SAME_COMMAND:
  chờ và gửi lại cùng ý định;
  giữ idempotency key nếu endpoint dùng key.

QUERY_OPERATION:
  tra operation/kết quả gốc theo quyền hiện tại.
~~~

Đây là hướng dẫn của hợp đồng, không phải yêu cầu client bỏ các giới hạn retry, quyền hoặc thời hạn.

### 7.2. Retry theo status code là chưa đủ

~~~text
409 VERSION_CONFLICT:
    không lặp ngay payload cũ vô hạn.

409 IDEMPOTENCY_KEY_REUSED:
    không tự đổi key để ép request mới đi qua.

503 trước khi có hiệu ứng:
    có thể chờ và gửi cùng command theo hợp đồng.

Timeout khi hiệu ứng có thể đã xảy ra:
    tra cứu hoặc replay an toàn, không tạo ý định mới.
~~~

Nếu dùng hướng dẫn chờ như Retry-After theo tình huống, client vẫn phải giữ cùng ý định và tuân thủ state machine. Chờ xong không tự có thêm quyền.

### 7.3. Giữ key và fingerprint của ý định gốc

Client cần lưu đủ thông tin của command đang chờ để không tạo key mới mỗi lần bấm lại.

Server phải giới hạn key theo tenant/caller/action phù hợp và so fingerprint. Chống trùng không được trở thành đường đọc receipt ngoài quyền.

Nếu một command đã thất bại dứt khoát và người dùng chủ ý tạo yêu cầu mới sau khi sửa dữ liệu, đó là một ý định mới theo hợp đồng, không phải hành vi retry tự động không phân biệt.

### 7.4. Mất body lỗi là một tình huống được hỗ trợ

Gateway có thể trả body khác định dạng, kết nối có thể ngắt hoặc response không đến client.

Client cần có nhánh xử lý lỗi transport/không parse được response. Không coi thiếu error.code là success hoặc là bằng chứng chưa xử lý.

Đối với command nhạy cảm, trạng thái chờ xác minh và đường tra operation thường cần được thiết kế từ đầu.

## 8. Thứ tự kiểm tra và chính sách tiết lộ

### 8.1. Không để lỗi nghiệp vụ tiết lộ đối tượng ngoài quyền

Một caller ngoài scope không nên biết refund tồn tại, đang APPROVED hay có số tiền còn lại bao nhiêu chỉ vì chọn một endpoint khác.

Một thứ tự logic minh họa:

~~~text
Decode đủ để xử lý request an toàn.
Xác thực và resolve tenant theo hợp đồng.
Nạp/kiểm tra đối tượng trong phạm vi cho phép.
Kiểm tra quyền action.
Kiểm tra version, state và các điều kiện nghiệp vụ.
Tạo hiệu ứng trong ranh giới đã bảo vệ.
~~~

Framework có thể tổ chức khác. Một lỗi cú pháp được phát hiện sớm không nhất thiết phải chờ mọi kiểm tra quyền. Điều quan trọng là không sử dụng/tiết lộ facts nhạy cảm ngoài thẩm quyền.

### 8.2. Cùng chính sách che giấu trên các đường vào

Nếu GET che object ngoài tenant bằng RESOURCE_NOT_FOUND, endpoint approve, attachment hoặc operation lookup không nên tự trả một thông báo đầy đủ về chính object đó.

Cần xem cả:

~~~text
status và public code
message và field violations
links/operationId đính kèm
response headers/metadata liên quan
count, list và endpoint tra cứu phụ
~~~

Làm giống message không tự tạo bảo đảm chống mọi side channel. Cache, truy vấn và hành vi quan sát khác vẫn cần thiết kế phù hợp.

### 8.3. Chọn lỗi chính có chủ đích

Một request có thể vừa sai version vừa không còn ở trạng thái SUBMITTED. Hợp đồng nên có quy tắc chọn primary code ổn định.

Không dựa vào thứ tự ngẫu nhiên của collection validator. Có thể gom nhiều lỗi input an toàn, nhưng không trả mọi lý do nội bộ chỉ để response trông đầy đủ.

Thông báo phải dựa trên những kiểm tra đã thực sự chạy. Nếu không đọc được nguồn policy, không nói actor chắc chắn thiếu role hoặc input chắc chắn sai.

## 9. Mapper lỗi tập trung, domain giữ ngữ nghĩa nghiệp vụ

### 9.1. Tránh mỗi controller tự đoán status và retry

Một thiết kế có thể tách:

~~~text
Domain/application:
  phát failure có reason được định nghĩa,
  giữ dữ kiện và nguồn gốc cần thiết.

Error catalogue:
  định nghĩa public code, nhóm status và message key.

Disclosure policy:
  chọn thông tin caller được phép thấy.

Execution evidence:
  cung cấp kiến thức về commit/rollback/operation.

Transport adapter:
  dựng response và headers theo giao thức.
~~~

Domain không cần biết câu thông báo tiếng Việt hay cấu trúc HTTP cụ thể. HTTP adapter cũng không được suy ra kết quả tài chính chỉ từ tên exception.

### 9.2. Java minh họa mapper

Mã dưới đây dùng các kiểu giả định, không phải chương trình độc lập hoặc cấu hình của một framework cụ thể.

~~~java
ApiErrorResponse toApiError(
        Failure failure,
        ErrorContext context,
        ExecutionEvidence evidence) {

    var outcome = evidence.forCommand(context.commandId())
            .verifiedOutcomeOrUnknown();

    var publicFailure = disclosure.toPublicFailure(
            failure, context);

    var definition = catalogue.forCodeOrInternalError(
            publicFailure.code());

    var violations = fieldErrors.forCaller(
            publicFailure, context);

    var operationReference = operations.referenceIfAllowed(
            evidence, context);

    var recovery = recoveryRules.choose(
            definition, outcome,
            operationReference, context);

    var body = new ErrorEnvelope(
            context.serverRequestId(),
            new ErrorBody(
                    definition.code(),
                    messages.safeMessage(
                            definition.messageKey(),
                            context.locale()),
                    violations),
            new ExecutionInfo(
                    outcome, operationReference),
            recovery);

    return new ApiErrorResponse(
            definition.httpStatus(), body);
}
~~~

Các điểm quan trọng:

- Failure đến từ đường xử lý tin cậy, không lấy public code/status do client tự khai.
- Outcome không mặc định NOT_APPLIED khi thiếu bằng chứng.
- Disclosure có thể đổi nhiều lý do truy cập nội bộ thành một lỗi công khai chung.
- Message dùng dữ liệu/tham số được cho phép, không chèn exception text thô.
- Operation reference chỉ xuất hiện khi caller có quyền biết/tra cứu.
- Recovery phụ thuộc outcome, không chỉ mã HTTP.

Nếu code không được nhận diện, fallback phải là lỗi hệ thống an toàn với outcome đúng mức đã biết. Không phản chiếu nguyên tên class/stack trace.

### 9.3. Mapper không được nói trái bằng chứng

VERSION_CONFLICT của lần thử chưa ghi mà lại gắn một receipt đã commit của command khác là dấu hiệu binding lỗi.

Cần liên kết evidence với đúng command/attempt. Không lấy “operation mới nhất của user” để suy ra outcome của mọi request.

Nếu dữ liệu mâu thuẫn, cần ghi sự kiện chẩn đoán được bảo vệ và trả kết quả thận trọng phù hợp. Đừng sửa reason hoặc outcome tùy ý để chúng trông nhất quán.

### 9.4. Hợp đồng HTTP vẫn phải được tôn trọng

Cấu trúc JSON chung không có nghĩa mọi response đều có body. Ví dụ HEAD không trả response body; status và metadata liên quan vẫn cần nhất quán theo giao thức.

Adapter cũng cần giữ các header mà tình huống/giao thức yêu cầu, như cơ chế xác thực, method được hỗ trợ hoặc hướng dẫn chờ phù hợp.

Error consistency không phải ép mọi endpoint và mọi transport dùng cùng một đoạn JSON bất kể ngữ nghĩa.

## 10. Lỗi phải khớp ranh giới transaction

### 10.1. Không catch rồi trả lỗi như một giá trị thành công của transaction

Mẫu nguy hiểm:

~~~text
Bắt đầu transaction.
Sửa entity.
Bắt lỗi validation và return error response bình thường.
Transaction wrapper thấy không có tín hiệu rollback.
Dữ liệu vẫn có thể được commit.
~~~

Chọn cơ chế để failure làm rollback khi hợp đồng yêu cầu. Thông thường response được dựng sau khi transaction đã kết thúc với kết quả được biết.

Không phụ thuộc vào việc response có status lỗi để nghĩ DB sẽ tự rollback.

### 10.2. Kiểm tra trước khi ghi và rollback khi bước bắt buộc thất bại

Quyền, trạng thái, version và bất biến cần được kiểm tra trên dữ liệu được bảo vệ. Nếu audit/outbox bắt buộc lỗi, toàn bộ thay đổi cục bộ liên quan phải rollback theo thiết kế.

Chỉ sau khi biết rollback có hiệu lực và không có hiệu ứng ngoài chưa giải quyết mới công bố NOT_APPLIED.

Một lỗi serialization sau commit cần cách xử lý khác một lỗi validation trước commit, dù cả hai có thể xuất hiện như HTTP 500 ở một lớp ngoài.

### 10.3. Log từ chối và audit thành công không cùng nghĩa

Có thể cần lưu security/attempt event ngay cả khi command bị rollback.

Điều đó không mâu thuẫn với NOT_APPLIED đã được định nghĩa cho hiệu ứng nghiệp vụ của command. Nhưng log cần ghi rõ denied, failed hoặc rolled back; không tạo một audit “approved” chỉ vì đã đi qua một nhánh kiểm tra.

Nếu bằng chứng thành công là bắt buộc, cần được commit nhất quán với thay đổi. Log từ xa nhận được một dòng không tự chứng minh DB đã commit.

## 11. Cùng ngữ nghĩa qua sync, async và batch

### 11.1. Command đồng bộ và đọc operation

Ví dụ cùng một xung đột revision:

~~~text
Command đồng bộ:
  response 409, error.code=VERSION_CONFLICT.

Công việc đã nhận bất đồng bộ:
  POST trả accepted và operationId.
  GET operation trả thành công của truy vấn,
  operation.state=FAILED,
  operation.error.code=VERSION_CONFLICT.
~~~

Hai response không cần cùng HTTP status. Public code và cách diễn giải điều kiện nghiệp vụ vẫn nhất quán.

Không trả HTTP lỗi của truy vấn chỉ vì operation mà truy vấn đang đọc có kết quả FAILED, nếu bản thân việc đọc tài nguyên thành công theo hợp đồng.

### 11.2. Callback/message có kết quả giao nhận riêng

ACK của một message hoặc response nhận callback có ý nghĩa theo giao thức giao nhận, không tự chứng minh toàn workflow thành công.

Chỉ xác nhận xử lý theo điều kiện bền vững mà giao thức yêu cầu. Kết quả nghiệp vụ phải được lưu vào operation/event liên quan và không mất vì một retry.

Callback không xác thực hoặc binding sai không được ghi nhận như kết quả nghiệp vụ hợp lệ. Không dùng “luôn trả 2xx” để che mọi lỗi và bỏ qua đối soát.

### 11.3. Batch toàn bộ hoặc từng phần phải rõ ràng

Nếu batch là all-or-nothing:

~~~text
Một lỗi làm batch bị từ chối/rollback.
Không công bố các item đã thành công nếu transaction không commit.
~~~

Nếu batch cho phép từng phần:

~~~text
Mỗi item có result/error/outcome và định danh phù hợp.
Summary phản ánh số thành công, thất bại và chưa xác định.
Client biết item nào được tra/retry.
~~~

Một response envelope thành công của batch không được hiển thị “mọi item thành công” khi thực tế có lỗi. Không gắn NOT_APPLIED cho toàn batch nếu có item đã commit.

Không trả item/resource ID ngoài quyền chỉ để giải thích lỗi. Scope vẫn được kiểm tra từng mục tiêu và ràng buộc tổng.

### 11.4. Alias, phiên bản API và client

Cùng command qua REST route khác, mobile hoặc công cụ nội bộ nên giữ cùng nghĩa lỗi nghiệp vụ, dù transport adapter khác nhau.

Đổi status/recovery hoặc dùng lại code cũ cho điều kiện mới có thể làm client đổi hành vi retry. Cần quản lý như thay đổi hợp đồng, không chỉ sửa câu chữ.

Client gặp code mới phải có fallback an toàn: hiển thị thông báo phù hợp, giữ kết quả chưa biết và tra cứu khi cần. Không coi code không nhận diện được là success hoặc tự thử lại bằng key mới.

## 12. Kiểm thử hợp đồng lỗi và hậu quả thực tế

### 12.1. Fixture nên có các ranh giới rõ

Chuẩn bị:

~~~text
Hai tenant có dữ liệu riêng.
Actor được đọc nhưng không được approve.
Reviewer đủ thẩm quyền trên một số đối tượng.
Resource có nhiều state và version.
Một hạn mức dùng chung cho các request cạnh tranh.
Receipt/operation/audit/outbox có thể quan sát.
Phụ thuộc giả lập có thể commit hiệu ứng rồi làm mất response.
~~~

Cần kiểm thử cả những lỗi chắc chắn không tạo hiệu ứng và những lỗi kết quả chưa biết.

### 12.2. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| JSON sai hoặc field ngoài hợp đồng | Code/status/field errors theo catalogue, không có hiệu ứng |
| Input đúng kiểu nhưng sai rule | Phân loại theo quy tắc input, không thành lỗi DB thô |
| Actor không đủ quyền action | Không đổi state; public error không lộ policy/role ngoài quyền |
| Object không tồn tại và object ngoài tenant | Cùng chính sách che giấu được áp dụng trên các endpoint |
| State không cho phép và version cũ | Primary code theo thứ tự đã đặc tả |
| Hai request tranh hạn mức chung | Command thua nhận lỗi conflict đúng ngữ nghĩa; invariant không hỏng |
| Cùng key/cùng payload sau commit | Trả kết quả gốc an toàn, không thêm hiệu ứng |
| Cùng key/khác payload | IDEMPOTENCY_KEY_REUSED; không công bố payload cũ ngoài quyền |
| Policy/dependency lỗi trước mutation | Không biến thành input sai hoặc default allow |
| Timeout sau khi hệ thống ngoài có thể đã thực hiện | Không tuyên bố NOT_APPLIED nếu thiếu bằng chứng |
| Transaction rollback được xác nhận, không có hiệu ứng ngoài | Outcome phản ánh đúng NOT_APPLIED |
| Lỗi trả response sau commit | Không nói command đã rollback; client có đường phục hồi |
| Job accepted nhưng xử lý còn pending | Không gọi đã hoàn tất; operation tra được trong scope |
| Operation đã FAILED được đọc thành công | Phân biệt HTTP của truy vấn với kết quả operation |
| Batch từng phần | Per-item error/outcome đúng, summary không che phần đã commit |
| Batch all-or-nothing lỗi một item | Không có item commit ngoài hợp đồng |
| Message/locale đổi | Public code và recovery giữ cùng ngữ nghĩa |
| Exception có dữ liệu nội bộ | Không lộ stack, SQL, secret hoặc đối tượng ngoài quyền |
| Gateway trả body không theo schema | Client không coi là success hoặc chắc chắn chưa xử lý |
| Client gặp public code mới | Fallback an toàn, không tự tạo key mới để retry |

### 12.3. Kiểm tra các quan hệ ổn định

Không cần buộc mọi request ID hoặc câu message phải giống nhau. Cần xác nhận:

~~~text
public code đúng với điều kiện được phép tiết lộ
HTTP status đúng catalogue/hợp đồng transport
outcome khớp bằng chứng của đúng command
recovery không khuyên hành động trái outcome
operation link chỉ xuất hiện trong scope được phép
field violations không chứa dữ liệu hoặc field nội bộ ngoài hợp đồng
~~~

Một test chỉ kiểm tra JSON có message chưa phát hiện lỗi retry hoặc tiết lộ.

### 12.4. Kiểm thử rollback bằng đọc lại

Với lỗi version, quyền hoặc bước bắt buộc thất bại trước khi có hiệu ứng ngoài, đọc lại bằng transaction mới:

~~~text
state và version không phản ánh thay đổi thành công
không có decision/reservation của command bị chặn
không có outbox/job thực hiện ý định bị từ chối
không có receipt thành công giả
audit thành công không xuất hiện ngoài hợp đồng
~~~

Attempt/security event có thể được lưu riêng.

Đừng chỉ assert response 409 hoặc 500. Một handler có thể trả lỗi nhưng vẫn commit vì exception đã bị nuốt.

### 12.5. Hai điểm gây lỗi phải được kiểm thử riêng

**Điểm A: trước commit**

~~~text
Thực hiện mutation trong transaction.
Gây lỗi tại bước bắt buộc.
Xác nhận rollback và không có hiệu ứng ngoài.
Kết quả cho command có thể là NOT_APPLIED.
~~~

**Điểm B: sau commit nhưng trước response đến client**

~~~text
Command đã commit cùng receipt/operation.
Chặn hoặc làm mất response.
Client chạy đường tra cứu/replay.
Xác nhận không có thêm decision/operation/hiệu ứng.
~~~

Không dùng cùng một mock “ném exception” để đại diện cả hai mà không mô phỏng trạng thái đã commit.

### 12.6. Phụ thuộc đã tạo hiệu ứng nhưng response bị mất

Dùng fake provider có trạng thái độc lập:

~~~text
1. Server gửi operation P với định danh ổn định.
2. Fake provider ghi hiệu ứng cho P.
3. Response bị ngắt trước khi server kết luận kết quả.
4. Server giữ trạng thái chưa xác định/đối soát theo hợp đồng.
5. Client tra cứu hoặc retry cùng ý định.
~~~

Kết quả cần kiểm chứng:

- Không có thông báo chắc chắn “chưa thực hiện” khi chưa đủ căn cứ.
- Không có một operation mới chỉ vì timeout.
- Đối soát liên kết đúng P và dữ liệu có thẩm quyền.
- Một lần provider đã thực hiện không biến thành hai hiệu ứng do client làm theo hướng dẫn lỗi.
- Khi có kết quả cuối, operation và dữ liệu nội bộ được cập nhật nhất quán.

Chỉ cho hàm gọi provider ném exception trước khi ghi gì không phát hiện được tình huống này.

### 12.7. Kiểm thử che giấu thông tin trên nhiều đường

Cùng một caller ngoài scope, thử đọc, sửa, approve, attachment và tra operation liên quan một object không được phép biết.

Kiểm tra sự nhất quán của public code/status theo policy, đồng thời không có tên tenant, chủ sở hữu, số tiền hoặc state bị lộ trong message/violations/link.

Đối với caller có quyền xem nhưng thiếu quyền action, lỗi có thể cụ thể hơn theo hợp đồng. Không cần làm mọi lỗi giống nhau bất kể quyền xem.

## 13. Tình huống thực hành: retry theo lỗi đã làm đổi ý định

Một client gửi command nhạy cảm với key K1. Server đã commit nhưng response không đến client.

Một handler lỗi phía client có quy tắc:

~~~text
Nếu timeout hoặc 5xx:
    tạo key mới;
    gửi lại cùng dữ liệu.
~~~

Nếu nghiệp vụ cho phép nhiều request độc lập, K2 có thể trông như một ý định mới hợp lệ. Idempotency theo key không tự biết K1 và K2 là cùng lần bấm ban đầu.

Thiết kế phù hợp:

1. Giữ K1 và nội dung command gốc trong khi kết quả chưa rõ.
2. Tra operation/receipt bằng đường có kiểm tra quyền.
3. Nếu retry được hỗ trợ, gửi cùng ý định và key theo hợp đồng.
4. Chỉ tạo ý định mới sau một quyết định nghiệp vụ rõ ràng, không do generic error handler tự chọn.
5. Server vẫn có state machine, bất biến và business key phù hợp cho những trường hợp cần chống trùng ở mức nghiệp vụ.

Error consistency giúp client hành xử đúng; nó không tự ngăn được mọi ý định trùng có key mới hoặc thay thế các bất biến phía server.

### 13.1. Lỗi của lần thử mới không hủy kết quả gốc

Giả sử client dùng lại K1 nhưng vô tình sửa payload. Server trả IDEMPOTENCY_KEY_REUSED và NOT_APPLIED cho lần thử không khớp.

Điều này không nói command gốc K1 chưa xảy ra. Kết quả gốc có thể đã commit.

Response và recovery cần hướng tới tra ý định gốc; không khuyên đổi key để “sửa lỗi” mà chưa xác định kết quả. UI cũng không được ghi đè một lịch sử thành công bằng trạng thái “không có gì xảy ra” chỉ từ lỗi của lần thử mới.

### 13.2. Version conflict cần xem lại, không chỉ cập nhật số version

Nếu server trả VERSION_CONFLICT, client không nên lấy version mới rồi tự gửi lại cùng một quyết định trên nội dung có thể đã đổi.

Reviewer có thể đã xem số tiền 10 triệu, trong khi revision mới là 100 triệu. Cần quy trình xem/xác nhận lại theo nghiệp vụ.

Một mã lỗi ổn định chỉ có ích khi hướng dẫn phục hồi giữ đúng ý nghĩa của quyết định ban đầu.

## 14. Quan sát lỗi để phát hiện sai lệch

Có thể tổng hợp theo action, public code, internal reason, outcome và giai đoạn xử lý.

Các mẫu cần điều tra gồm:

- Outcome NOT_APPLIED nhưng có event/operation đã commit của cùng attempt.
- Command bị từ chối quyền nhưng dữ liệu vẫn thay đổi.
- Lỗi version tăng cao đi kèm retry tự động liên tục.
- Nhiều key mới ngay sau OUTCOME_UNKNOWN.
- Endpoint alias có code/recovery khác cho cùng điều kiện.
- Batch báo thành công nhưng có item không được thực hiện.
- Tỷ lệ lỗi phụ thuộc tăng nhưng client lại nhận INPUT_RULE_VIOLATION.
- Thông tin nội bộ xuất hiện trong public message.

ID phục vụ nối sự kiện cần được quản lý và kiểm tra quyền khi tra cứu. Một requestId do caller biết không phải quyền xem log.

Tránh đưa mọi resourceId/requestId thành nhãn metric không giới hạn. Log có cấu trúc và công cụ tra cứu theo quyền thường phù hợp hơn cho điều tra chi tiết.

## 15. Quản lý hợp đồng lỗi như một phần API

Catalogue có thể ghi:

~~~text
Public code:
Điều kiện có nghĩa gì:
Điều kiện không thuộc code này:
HTTP mapping theo loại endpoint:
Message key và các tham số an toàn:
Violations được phép công bố:

Outcome nào có thể đi kèm:
Bằng chứng cần để chọn outcome:
Recovery được phép:
Scope và quyền tra operation:
Tính tương thích khi thêm/sửa code:
Ca kiểm thử response và dữ liệu bền vững:
~~~

Không đổi nghĩa một code đang dùng chỉ để tái sử dụng tên. Không để mỗi client phải duy trì một danh sách ngoại lệ theo endpoint mà không có lý do nghiệp vụ.

Cần nói rõ response nào do application kiểm soát và cách client xử lý lỗi transport hoặc hạ tầng nằm ngoài schema.

Tài liệu và test nên bao quát cả hành vi không được làm, chẳng hạn không retry key mới khi kết quả chưa biết.

## 16. Câu hỏi tự kiểm tra

1. API của bạn phân biệt lỗi input, quyền, state và dependency bằng điều kiện nào?
2. HTTP 500/timeout có đủ chứng minh command chưa commit không?
3. NOT_APPLIED được chọn từ bằng chứng nào và có bao phủ hiệu ứng ngoài không?
4. COMMITTED của command có đồng nghĩa toàn workflow đã hoàn tất không?
5. Client có tự đổi idempotency key sau lỗi chung không?
6. Lỗi của lần retry có thể bị hiểu nhầm thành trạng thái của command gốc như thế nào?
7. Object ngoài tenant có bị lộ qua error code, field details hoặc operation link không?
8. Operation thất bại và truy vấn operation thất bại đang được phân biệt ra sao?
9. Test nào chứng minh error response khớp dữ liệu đã commit và không chỉ có JSON đúng dạng?

Một hợp đồng lỗi đáng tin cậy phải giữ thống nhất **điều kiện thất bại, mức kết quả được biết và hành động phục hồi được phép**. Client chỉ có thể retry và tiếp tục workflow đúng khi API không khẳng định quá những gì hệ thống thực sự biết.
