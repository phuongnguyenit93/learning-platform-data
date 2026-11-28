# Exception classification

## 1. Phân loại exception để quyết định điều gì?

**Exception classification** là việc chuyển một sự cố được phát hiện trong chương trình thành thông tin có cấu trúc đủ để quyết định cách phản hồi, phục hồi, ghi nhận và bảo vệ hệ thống.

Một tên class như `TimeoutException` hoặc `IllegalArgumentException` chưa trả lời đủ các câu hỏi:

- Sự cố thuộc yêu cầu không hợp lệ, từ chối nghiệp vụ, phụ thuộc không sẵn sàng hay lỗi lập trình?
- Thao tác đã tạo tác động chưa, hay kết quả vẫn chưa xác định?
- Có được thử lại không, ai thử lại và trong ngân sách nào?
- Người gọi được biết thông tin nào?
- Cần log, metric, audit hoặc chuyển người xử lý ở mức nào?

Nếu phân loại sai, hệ thống có thể làm nhiều hơn việc trả nhầm HTTP status. Nó có thể bỏ kiểm quyền, ghi lặp, làm lộ thông tin, dừng sai workflow hoặc che giấu sự cố đang cần điều tra.

Trong chương Error handling của module yêu cầu bảo mật, mục tiêu là đặc tả các quyết định này bằng contract và bằng chứng kiểm thử. Taxonomy, mã lỗi và tham số trong bài là thiết kế minh họa, không phải một tiêu chuẩn đặt tên bắt buộc cho mọi ứng dụng.

## 2. Phân loại của Java khác với phân loại bảo mật

### 2.1. Checked, unchecked và Error

Theo [Java Language Specification, Chương 11](https://docs.oracle.com/javase/specs/jls/se25/html/jls-11.html), `RuntimeException` và `Error` thuộc các nhóm unchecked; checked exception chịu kiểm tra khai báo/xử lý ở thời điểm biên dịch. `Error` được tách khỏi `Exception` để phản ánh những điều kiện mà chương trình thông thường không được kỳ vọng phục hồi như exception thông thường.

Sự phân chia này hữu ích cho contract ngôn ngữ, nhưng không quyết định trực tiếp mức rủi ro, HTTP status hoặc quyền retry.

| Cách phân loại | Nó mô tả điều gì? | Không tự chứng minh điều gì? |
|---|---|---|
| Checked/unchecked | Quy tắc kiểm tra của ngôn ngữ Java | Có nguy hiểm hay không; ai có lỗi; có nên retry không |
| Domain/technical | Sự cố thuộc nghiệp vụ hay thành phần kỹ thuật theo thiết kế | Người gọi được biết bao nhiêu; tác động đã xảy ra chưa |
| Expected/unexpected | Có thuộc một tình huống đã được thiết kế hay không | Expected luôn ít nghiêm trọng hoặc unexpected luôn là tấn công |
| Transient/persistent | Nhận định về khả năng điều kiện lỗi thay đổi | Thử lại thao tác có an toàn hay không |
| Security-relevant | Sự cố có liên quan tới kiểm soát hoặc tín hiệu an toàn | Nó chắc chắn là hành vi xâm nhập |

Ví dụ, `IllegalArgumentException` tại bước parse input đã được kiểm soát có thể liên quan một yêu cầu không hợp lệ. Cùng tên class phát sinh do gọi sai API nội bộ có thể là lỗi lập trình. Không ánh xạ mọi `IllegalArgumentException` thành lỗi của client.

Tương tự, một nhóm exception mang ý nghĩa “transient” ở thư viện chỉ là đầu vào cho quyết định phục hồi. Nó không biết toàn bộ tác động nghiệp vụ hoặc lời gọi tới dịch vụ khác đã xảy ra.

### 2.2. Không dùng catch rộng để xóa ý nghĩa sự cố

Một boundary có thể cần xử lý exception chưa biết để tạo phản hồi an toàn, nhưng không nên bắt rộng rồi trả cùng một lỗi validation cho mọi tình huống.

Không viết policy chung “bắt mọi `Throwable` và tiếp tục chạy bình thường”. Với lỗi tài nguyên hoặc runtime nghiêm trọng, cần quy trình của ứng dụng, runtime và hạ tầng phù hợp; việc trả được một response không chứng minh process còn đủ tin cậy để phục vụ.

## 3. Mô hình đe dọa khi phân loại sai

| Mã | Sai lệch phân loại | Hậu quả cần ngăn |
|---|---|---|
| R1 | Không gọi được hệ thống phân quyền bị coi là người dùng có quyền | Fail-open, truy cập trái phép |
| R2 | Exception kỹ thuật được chuyển nguyên sang lỗi công khai | Lộ SQL, token, stack trace, topology hoặc dữ liệu khác tenant |
| R3 | Timeout được gắn retry mà không xét tác động | Tạo tác động lặp hoặc nhiều giao dịch |
| R4 | Lỗi chưa biết bị gắn lỗi client hoặc lỗi nghiệp vụ thông thường | Che lỗi lập trình, hỏng dữ liệu hoặc sự cố hệ thống |
| R5 | Từ chối truy cập thông thường luôn bị gắn là tấn công nghiêm trọng | Nhiễu cảnh báo, khó phát hiện sự cố thật |
| R6 | Wrapper hoặc lỗi cleanup làm mất ngữ cảnh ban đầu | Phản hồi, bù trừ hoặc retry sai |
| R7 | Cancellation/deadline bị coi là lỗi cần thử lại vô hạn | Lãng phí tài nguyên, tiếp tục xử lý ngoài ý định |
| R8 | Các protocol hoặc worker dùng taxonomy/mapping khác nhau | Contract không nhất quán, có đường vòng bảo mật |

Bất biến của thiết kế minh họa:

1. Không phân loại một điều kiện chưa biết thành chấp thuận quyền hoặc xác nhận thành công.
2. Quyết định retry phải xét tác động và contract của thao tác, không chỉ tên exception.
3. Response công khai chỉ dùng thông tin đã được duyệt theo ngữ cảnh và quyền.
4. Chưa xác định, không có dữ liệu, bị từ chối và đã thất bại chắc chắn là các trạng thái khác nhau.
5. Mỗi quyết định phân loại có rule, phiên bản và bằng chứng ngữ cảnh đủ để điều tra.

## 4. Dùng nhiều trục phân loại thay vì một nhãn duy nhất

### 4.1. Category nội bộ

Category mô tả ý nghĩa của thất bại trong ứng dụng, chẳng hạn `VALIDATION_FAILURE`, `ACCESS_DENIED` hoặc `DEPENDENCY_UNAVAILABLE`.

Đây không nhất thiết là tên class và không nhất thiết được gửi cho client. Nhiều class kỹ thuật có thể cùng thuộc một category, trong khi một class có thể được phân loại khác nhau theo nguồn phát sinh và giai đoạn xử lý.

### 4.2. Trạng thái tác động của thao tác

| Outcome minh họa | Ý nghĩa | Bằng chứng cần có |
|---|---|---|
| `NOT_APPLIED` | Tác động thuộc phạm vi thao tác chưa được áp dụng | Bằng chứng từ giai đoạn xử lý hoặc nguồn có thẩm quyền |
| `APPLIED` | Tác động đã được xác nhận | Kết quả bền vững hoặc xác nhận thích hợp |
| `PARTIALLY_APPLIED` | Một số tác động đã xảy ra, một số chưa | Kết quả từng phần, ví dụ trong workflow hoặc batch |
| `UNKNOWN` | Chưa đủ bằng chứng kết luận | Ghi rõ nguồn thiếu xác nhận và cách đối soát |

Outcome phải gắn với phạm vi. Rollback một transaction database cục bộ không chứng minh email chưa gửi hoặc dịch vụ thanh toán chưa xử lý. Nếu những tác động đó thuộc thao tác nghiệp vụ, không được tự gán toàn bộ là `NOT_APPLIED`.

`UNKNOWN` là một trạng thái có ý nghĩa, không phải giá trị cần xóa cho dashboard đẹp hơn. Nó có thể yêu cầu đối soát hoặc truy vấn trạng thái trước khi quyết định tiếp tục.

### 4.3. Hành động phục hồi

Có thể dùng các hành động như:

- `NO_RETRY`: không tự thử lại theo điều kiện hiện tại.
- `CORRECT_REQUEST`: người gọi sửa input theo contract.
- `REAUTHENTICATE`: thực hiện lại bước xác thực phù hợp.
- `RETRY_WITHIN_BUDGET`: chỉ thử lại khi đủ điều kiện an toàn và còn ngân sách.
- `RECONCILE_STATUS`: kiểm tra kết quả thao tác trước khi quyết định.
- `CANCEL_OR_STOP`: dừng theo cancellation/deadline.
- `ESCALATE`: chuyển owner xử lý vì chưa có quy tắc phục hồi an toàn.

Một hành động là gợi ý của policy, không phải quyền bỏ qua kiểm soát. Retry hoặc bù trừ vẫn phải giữ tenant, danh tính, phân quyền và điều kiện nghiệp vụ.

### 4.4. Mức công bố và quan sát

Phân loại còn cần quyết định public code, thông điệp, dữ liệu được phép, loại sự kiện và mức ưu tiên vận hành. Không gộp tất cả thành một boolean `fatal` hay `retryable`.

Ví dụ, một lần từ chối quyền là sự kiện có thể cần audit nhưng không mặc nhiên cần đánh thức trực vận hành. Một chuỗi từ chối bất thường, kết hợp bằng chứng khác, có thể trở thành tín hiệu an ninh đáng chú ý.

## 5. Taxonomy minh họa và cách dùng

| Category | Ví dụ ngữ cảnh | Quyết định cần đặc tả |
|---|---|---|
| `VALIDATION_FAILURE` | Input không đáp ứng schema/ràng buộc công khai | Thông tin giúp sửa, field an toàn và không retry nguyên input |
| `AUTHENTICATION_FAILURE` | Credential không hợp lệ hoặc không đủ điều kiện | Contract xác thực, hạn chế enumeration và không lộ credential |
| `ACCESS_DENIED` | Policy có kết quả từ chối với tài nguyên trong scope | Dừng hành động, công bố theo policy, ghi nhận phù hợp |
| `DOMAIN_REJECTION` | Chuyển trạng thái không được phép theo nghiệp vụ | Code nghiệp vụ ổn định, không lộ cách lưu trữ |
| `CONCURRENCY_CONFLICT` | Phiên bản tài nguyên đã thay đổi | Đọc lại/giải quyết xung đột hoặc retry có điều kiện |
| `DEPENDENCY_UNAVAILABLE` | Phụ thuộc không sẵn sàng, mất kết nối | Fail-closed nếu phụ thuộc bảo mật; kiểm outcome trước retry |
| `RESOURCE_LIMIT` | Vượt quota hoặc thiếu tài nguyên xử lý | Phân biệt giới hạn của người gọi với quá tải hệ thống |
| `DATA_INTEGRITY_ANOMALY` | Dữ liệu vi phạm invariant không phải xung đột đã biết | Dừng luồng nguy hiểm, điều tra và không đổ lỗi mặc định cho client |
| `CANCELLED_OR_DEADLINE` | Caller hủy hoặc ngân sách xử lý đã hết | Dừng/cancel theo khả năng thực tế; không tự tạo chuỗi retry mới |
| `DEFECT_OR_UNCLASSIFIED` | Lỗi lập trình hoặc sự cố chưa có rule tin cậy | Fallback an toàn, không tự chấp thuận, có triage |

Đây là điểm khởi đầu cho một service. Không cần tạo hàng trăm category chỉ để phản ánh từng class thư viện. Ngược lại, gộp mọi tình huống thành `SYSTEM_ERROR` làm mất thông tin cần cho các quyết định khác nhau.

Một lỗi unique constraint là ví dụ cần ngữ cảnh: nó có thể thể hiện xung đột nghiệp vụ đã biết, hoặc một bất thường do bug/migration. Không ánh xạ mọi lỗi integrity thành `DOMAIN_REJECTION` và cho client biết dữ liệu đang tồn tại.

Category nội bộ cũng không phải một HTTP status. Hai sự cố trong cùng category có thể cần response khác theo route, người gọi và contract; các giao thức khác có mapping riêng.

## 6. Quy trình quyết định và thứ tự rule

### 6.1. Thu thập ngữ cảnh tin cậy

Classifier cần biết boundary, thao tác, giai đoạn, danh tính workload, phạm vi quyền và bằng chứng về tác động. Không lấy các giá trị quyết định như `trusted=true`, `retryable=true` hoặc category từ payload client chưa được kiểm tra.

Ngữ cảnh hữu ích gồm:

```text
operation: CREATE_ENROLLMENT
phase: WAITING_FOR_COMMIT_ACK
boundary: HTTP_REQUEST
authorizationState: VERIFIED
sideEffectEvidence: NO_AUTHORITATIVE_RESULT_YET
deadlineState: STILL_WITHIN_BUDGET
idempotencyProfile: ENROLLMENT_COMMAND_V2
```

Các giá trị này do luồng xử lý thực tế tạo ra. `WAITING_FOR_COMMIT_ACK` không tự kết luận commit thất bại; nó cho classifier biết đang thiếu xác nhận ở đâu.

### 6.2. Rule cụ thể trước, fallback an toàn sau

Một quy trình có thể là:

1. Nhận biết cancellation/deadline và các điều kiện runtime cần xử lý riêng theo boundary.
2. Xác định exception nghiệp vụ tin cậy hoặc kết quả policy đã được xác lập.
3. Dùng adapter phù hợp để hiểu lỗi phụ thuộc và ngữ cảnh nguồn phát sinh.
4. Đánh giá outcome theo bằng chứng, giữ `UNKNOWN` khi không đủ dữ liệu.
5. Chọn hành động phục hồi dựa trên thao tác, quyền, deadline và idempotency.
6. Chọn public response theo mức công bố được phép.
7. Ghi sự kiện và bằng chứng chẩn đoán đã được kiểm soát.
8. Nếu không có rule đáng tin cậy, dùng fallback; không tự hạ thành lỗi client hoặc cho phép tiếp tục.

Thứ tự cụ thể phải phù hợp service. Yêu cầu cốt lõi là các rule có tính xác định, có phạm vi và không bị một catch rộng ở ngoài làm mất kết quả.

### 6.3. Không suy nghĩa bằng message tự do

Match chuỗi “denied”, “duplicate” hoặc “timeout” trong message có thể sai do ngôn ngữ, phiên bản, input hoặc nguồn phát sinh. Một `access denied` từ database credential không đồng nghĩa người dùng cuối đã bị policy từ chối.

Ưu tiên loại exception, mã cấu trúc và contract của adapter đã được kiểm chứng cho nguồn tương ứng. Nếu cần mapping riêng theo provider, lưu nó ở adapter, không lan truyền vendor code thành contract công khai.

Một input độc hại có thể xuất hiện trong message; không để nội dung đó khiến classifier đổi mức ưu tiên, mở debug hoặc tự bật retry.

## 7. Wrapper, cause và mô hình dữ liệu minh họa trong Java

### 7.1. Không phải cause sâu nhất luôn có ý nghĩa nhất

Exception bất đồng bộ có thể được bọc; lỗi tài nguyên khi cleanup có thể xuất hiện dưới dạng thông tin bổ sung. Nếu chỉ lấy message ngoài cùng, có thể mất nguyên nhân hữu ích. Nếu chỉ lấy cause sâu nhất, có thể mất context nghiệp vụ ở lớp ngoài.

Quy tắc unwrap cần chỉ rõ wrapper nào được nhận diện, giữ metadata nào và khi nào dừng. Nếu tự duyệt đồ thị cause/suppressed, phải có giới hạn độ sâu/số node và xử lý tham chiếu lặp để tránh classifier bị treo hoặc tốn tài nguyên.

Không coi mọi suppressed exception là nguyên nhân chính. Lỗi đóng kết nối cần được quan sát nhưng không tự ghi đè trạng thái đã commit hay lỗi nghiệp vụ đã được xác lập.

### 7.2. Tách classification nội bộ khỏi response công khai

Ví dụ mô hình Java:

```java
enum FailureCategory {
    VALIDATION_FAILURE,
    ACCESS_DENIED,
    DEPENDENCY_UNAVAILABLE,
    DEFECT_OR_UNCLASSIFIED
}

enum OperationOutcome {
    NOT_APPLIED,
    APPLIED,
    PARTIALLY_APPLIED,
    UNKNOWN
}

enum RecoveryAction {
    NO_RETRY,
    RETRY_WITHIN_BUDGET,
    RECONCILE_STATUS,
    ESCALATE
}

record ClassifiedFailure(
    FailureCategory category,
    OperationOutcome outcome,
    RecoveryAction recovery,
    String ruleId,
    int policyVersion
) {}

record PublicFailure(
    String code,
    String message,
    String requestId
) {}
```

Các enum trên chỉ lấy một phần taxonomy để minh họa cấu trúc; record chưa tự kiểm mọi tổ hợp hợp lệ. Chẳng hạn, policy vẫn cần ngăn một failure có `UNKNOWN` được gắn retry không điều kiện.

Không thêm `Throwable`, SQL, token hoặc vendor message vào `PublicFailure`. Internal record và public DTO là hai contract khác nhau, kể cả khi code có thể serialize cả hai.

Mã giả kết nối các quyết định:

```text
handleFailure(error, trustedContext):
    classification = classify(error, trustedContext, activePolicy)
    action = authorizeRecovery(classification, trustedContext)
    publicFailure = choosePublicContract(classification, trustedContext)

    recordSanitizedEvidence(classification, action, trustedContext)
    executeOnlyPermittedRecovery(action, trustedContext)
    return serializeApprovedPublicFields(publicFailure)
```

Thứ tự gửi response và thực hiện phục hồi phụ thuộc contract đồng bộ/bất đồng bộ. Mã giả không có nghĩa mọi retry phải được thực hiện bên trong handler HTTP hoặc phải chặn request cho đến khi đối soát xong.

## 8. Cùng một timeout nhưng quyết định khác nhau

### 8.1. Tình huống đăng ký khóa học

Một lệnh đăng ký có thể đi qua xác thực, phân quyền, kiểm điều kiện, ghi dữ liệu và phát hành sự kiện. Mất thời gian chờ tại mỗi điểm có ý nghĩa khác nhau.

| Vị trí và bằng chứng | Category/outcome minh họa | Hành vi phù hợp |
|---|---|---|
| Chưa gửi lệnh tới phụ thuộc, có bằng chứng không có tác động nào khác | `DEPENDENCY_UNAVAILABLE` / `NOT_APPLIED` | Có thể retry trong ngân sách nếu contract cho phép |
| Không lấy được quyết định phân quyền | Lỗi phụ thuộc bảo mật, chưa có quyết định cho phép | Không tiếp tục hành động được bảo vệ; không giả thành xác thực thành công |
| Đang chờ xác nhận commit của lệnh ghi | `DEPENDENCY_UNAVAILABLE` / `UNKNOWN` | Đối soát bằng operation ID/idempotency contract, không gửi lại mù quáng |
| Truy vấn đọc không có tác động nghiệp vụ bị timeout | Lỗi phụ thuộc trong thao tác đọc | Chỉ retry nếu còn ngân sách và giữ scope truy cập |
| Client hủy sau khi dữ liệu đã được xác nhận ghi | Cancellation với outcome đã xác nhận `APPLIED` | Không suy rằng thao tác bị rollback chỉ vì caller không nhận kết quả |
| Transaction bị hủy do xung đột, có bằng chứng rollback và không có tác động ngoài transaction | Conflict với `NOT_APPLIED` trong phạm vi đó | Có thể thử lại theo policy nghiệp vụ, giới hạn số lần |

Bảng dùng thông tin về luồng thật và bằng chứng, không suy kết quả chỉ từ class exception. Nếu chưa biết tác động ngoài database đã xảy ra hay chưa, phải giữ sự không chắc chắn đó.

### 8.2. Tách từ chối quyền khỏi không thể quyết định quyền

`ACCESS_DENIED` nên biểu thị một quyết định từ chối đã được hệ thống quyền xác lập theo contract. Không gọi được policy service là điều kiện khác, dù cả hai có thể đều khiến thao tác bị dừng.

Việc giữ khác biệt nội bộ giúp vận hành biết có người dùng thiếu quyền hay có phụ thuộc đang hỏng. Response công khai có thể được giới hạn theo policy để tránh tiết lộ ngoài nhu cầu, nhưng không được biến sự cố phụ thuộc thành chấp thuận.

Nguyên tắc fail-closed ở đây là không thực hiện hành động được bảo vệ khi thiếu điều kiện cho phép bắt buộc. Nó không đồng nghĩa mọi lỗi hệ thống phải được trả cho client như lỗi quyền của chính họ.

## 9. Mapping ra contract công khai là một quyết định riêng

### 9.1. Không xuất taxonomy kỹ thuật nguyên vẹn

Người gọi thường cần một code ổn định, giải thích an toàn và bước tiếp theo phù hợp. Họ không cần biết tên driver, class exception hoặc rule chẩn đoán nội bộ.

[OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) mô tả cách trả phản hồi phù hợp cho lỗi bất ngờ và giữ chẩn đoán phía server. Với một service, điều này cần được cụ thể hóa thành catalog công khai và policy dữ liệu chẩn đoán, không chỉ một catch mặc định.

Ví dụ public payload cho kết quả chưa được xác nhận:

```json
{
  "code": "OPERATION_STATUS_UNCONFIRMED",
  "message": "Chưa thể xác nhận kết quả. Vui lòng kiểm tra trạng thái bằng mã thao tác.",
  "operationId": "operation-demo-42",
  "requestId": "request-demo-918"
}
```

Ví dụ chỉ phù hợp khi API thật sự có mã thao tác và đường kiểm tra trạng thái được phân quyền. Operation ID không được tự tạo quyền đọc trạng thái hoặc dữ liệu. Không công bố một hướng dẫn mà sản phẩm không thực hiện được.

Không tự trả HTTP 202 cho mọi kết quả chưa biết: trạng thái chấp nhận xử lý bất đồng bộ phải phản ánh việc yêu cầu đã thực sự được tiếp nhận theo contract tương ứng. Tương tự, không khẳng định ghi thất bại chỉ vì handler đang giữ exception.

### 9.2. HTTP status không thay thế category hoặc outcome

Với HTTP, các lựa chọn như lỗi validation 4xx, xung đột 409, lỗi server 500 hoặc phụ thuộc tạm thời không sẵn sàng 503 cần được áp theo ngữ nghĩa route. Không dùng công thức cứng “exception unchecked là 500, checked là 400”.

Nếu chọn Problem Details, [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) cho phép mô tả lỗi theo định dạng chuẩn và extension. Nội dung vẫn phải kiểm soát: `type`, `detail` và extension không được tự chứa message, cause hay dữ liệu nhạy cảm của thư viện. Giá trị status trong body, nếu có, phải khớp status do server tạo.

Một category có thể có mapping khác nhau cho HTTP, RPC hoặc job bất đồng bộ. Điều cần nhất quán là ý nghĩa, quyền công bố và chính sách phục hồi, không phải ép mọi protocol dùng cùng một con số.

### 9.3. Expected không có nghĩa là được tiết lộ

Lỗi email trùng hoặc tài nguyên không tồn tại có thể là tình huống đã biết nhưng vẫn tạo nguy cơ enumeration. Catalog phải xét người gọi và tài nguyên trong scope.

Không gửi giá trị của người khác, dữ liệu tenant khác hoặc tên constraint chỉ để giải thích vì sao nghiệp vụ bị từ chối. Một rule nội bộ càng chính xác không có nghĩa response công khai càng phải chi tiết.

## 10. Từ classification tới policy phục hồi

### 10.1. “Transient” chưa đủ để cho phép retry

Một quyết định retry tối thiểu cần xét:

- Điều kiện lỗi có khả năng thay đổi trong thời gian còn lại hay không.
- Outcome và bằng chứng về tác động thuộc toàn bộ thao tác cần bảo vệ.
- Contract idempotency hoặc khả năng chứng minh lệnh chưa được áp dụng.
- Quyền, tenant, credential và policy còn hiệu lực khi thử lại.
- Deadline, số lần thử, tốc độ, mức tải và trạng thái cancellation.

[RFC 9110, mục 9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) phân biệt phương thức idempotent và hạn chế tự retry request không idempotent nếu không có cơ sở an toàn tương ứng. Trong ứng dụng, cần nối nguyên tắc này với tác động nghiệp vụ cụ thể, không chỉ nhìn tên phương thức HTTP.

Backoff, jitter và giới hạn số lần có thể giúp tránh dồn tải, nhưng không sửa được một retry vốn không an toàn. Thử lại chậm hơn vẫn có thể ghi trùng nếu lệnh trước đã commit.

### 10.2. Phải có một nơi chịu trách nhiệm ngân sách

Nếu SDK, service, worker và gateway đều retry độc lập, số lần gọi có thể nhân lên. Contract cần chỉ rõ tầng nào được retry tình huống nào, ngân sách toàn thao tác và cách truyền deadline.

Ví dụ minh họa có thể chọn tối đa 3 lần thử cho một truy vấn đọc trong ngân sách 2 giây, với điều kiện giữ nguyên scope và dừng khi caller đã hủy. Đây là tham số thiết kế của ví dụ, không phải ngưỡng mặc định cho mọi hệ thống.

Lệnh ghi có outcome `UNKNOWN` không tự hưởng cùng policy với truy vấn đọc. Nó có thể cần `RECONCILE_STATUS`, dùng cùng idempotency key đã ràng buộc đúng nội dung, hoặc chuyển xử lý có kiểm soát.

### 10.3. Cancellation, interruption và bù trừ

Cancellation là một tín hiệu về việc không nên tiếp tục theo contract, không phải bằng chứng mọi tác động đã được hoàn tác. Cần phân biệt dừng tạo công việc mới với hủy được thao tác đang chạy ở hệ thống khác.

Trong Java, khi xử lý interruption, không nuốt tín hiệu rồi tiếp tục retry vô hạn. Cần truyền tiếp hoặc bảo toàn tín hiệu theo contract của tầng xử lý. Một vòng phục hồi phải còn tôn trọng deadline và khả năng dừng.

Bù trừ là một thao tác nghiệp vụ mới có thể thất bại và có quyền riêng. Không coi “đã bắt exception” là đã rollback mọi hệ thống; không dùng quyền rộng hơn hoặc bỏ kiểm tra để thực hiện bù trừ cho nhanh.

## 11. Quan sát và bảo đảm classifier không tạo đường lỗi mới

### 11.1. Tách severity, security signal và category

Các trường này trả lời những câu hỏi khác nhau:

| Thuộc tính | Câu hỏi |
|---|---|
| Category | Sự cố có ý nghĩa gì trong ứng dụng? |
| Outcome | Tác động đã được xác nhận đến đâu? |
| Severity | Mức ưu tiên vận hành của sự cố này là gì? |
| Security signal | Có thông tin nào liên quan kiểm soát hoặc hành vi an toàn cần ghi nhận? |
| Owner | Nhóm nào chịu trách nhiệm điều tra/phục hồi? |

Một `ACCESS_DENIED` có thể là kết quả đúng của hệ thống. Một `DEPENDENCY_UNAVAILABLE` ở kho khóa hoặc hệ thống quyền có thể cần ưu tiên cao dù không có bằng chứng tấn công. Không gắn nghi phạm cho người dùng chỉ vì một dependency hỏng.

Sự kiện minh họa:

```yaml
eventType: FAILURE_CLASSIFIED
operation: CREATE_ENROLLMENT
category: DEPENDENCY_UNAVAILABLE
outcome: UNKNOWN
recoveryAction: RECONCILE_STATUS
ruleId: enrollment.commit-ack-missing
policyVersion: 4
publicCode: OPERATION_STATUS_UNCONFIRMED
requestId: request-demo-918
correlationId: trace-demo-117
```

Dữ liệu audit không bao gồm raw input, SQL, secret hoặc toàn bộ exception message. Quyền đọc trace hoặc thông tin đối soát vẫn cần được kiểm soát; request ID không phải credential.

### 11.2. Đừng làm mất dấu vết bằng cách log ở mọi lớp

Một thất bại được ghi lặp ở repository, service, handler và worker có thể thành nhiều cảnh báo cho cùng một sự cố. Cần quy định nơi ghi sự kiện chính, nơi bổ sung context và cách tương quan.

Metric dùng tập category và outcome hữu hạn, không dùng từng message/stack trace làm label. Theo dõi tỷ lệ fallback có thể giúp phát hiện mapping chưa đủ, nhưng cần đánh giá tác động và bối cảnh để ưu tiên.

Một lỗi nghiệp vụ lặp với số lượng bất thường cũng có thể đáng quan tâm. Không loại bỏ mọi sự kiện expected khỏi quan sát chỉ vì chúng không phải lỗi server.

### 11.3. Fallback của chính classifier

Classifier nên có giới hạn xử lý và phụ thuộc tối thiểu. Không gọi ngược dịch vụ vừa hỏng để quyết định có nên gọi lại nó, trừ khi đó là một quy trình phục hồi riêng có kiểm soát.

Nếu rule không tìm thấy, dữ liệu context thiếu hoặc policy phân loại không tải được, cần fallback an toàn. Không dùng “không phân loại được” làm lý do xác nhận quyền, báo thành công hoặc phát sinh retry vô hạn.

Logger hoặc serializer lỗi cũng không được làm public response rơi sang stack trace mặc định. Hành vi khi runtime không đủ tài nguyên để xử lý bình thường cần được giao rõ cho boundary và hạ tầng phù hợp.

## 12. Bộ yêu cầu bảo mật mẫu có thể nghiệm thu

| ID | Yêu cầu | Rủi ro và bằng chứng |
|---|---|---|
| CLASS-01 | Taxonomy tách category, outcome, recovery và mức công bố; có định nghĩa, owner và phiên bản | R3, R4; catalog cùng ví dụ/điều kiện từng trục |
| CLASS-02 | Rule dùng ngữ cảnh tin cậy và contract nguồn; không chỉ dựa vào message hoặc nhãn client tự khai | R1, R2; ca giả metadata, đổi message và cùng class khác ngữ cảnh |
| CLASS-03 | Không có kết quả phân quyền hợp lệ thì không thực hiện hành động được bảo vệ; từ chối và không quyết định được được phân biệt nội bộ | R1, R4; policy denial, timeout và mất phụ thuộc |
| CLASS-04 | Outcome được gắn với bằng chứng và phạm vi tác động; thiếu xác nhận giữ `UNKNOWN` | R3, R6; mất kết nối quanh commit và workflow nhiều hệ thống |
| CLASS-05 | Retry được cấp theo idempotency, outcome, quyền, deadline và ngân sách; không cấp chỉ vì exception transient | R3, R7; fault injection, lệnh ghi/đọc và retry nhiều tầng |
| CLASS-06 | Wrapper được xử lý có giới hạn, giữ context cần thiết; cause/cleanup không tự ghi đè kết quả đã xác lập | R4, R6; wrapper lồng, đồ thị cause và lỗi cleanup |
| CLASS-07 | Public response được dựng từ catalog được duyệt, không serialize exception hoặc classification nội bộ nguyên vẹn | R2; schema, canary trong message/cause và các protocol |
| CLASS-08 | Cancellation/deadline dừng tạo retry mới theo contract; không bị chuyển thành retry không giới hạn | R7; hủy trước, trong và sau tác động |
| CLASS-09 | Severity và security signal được xác định theo tác động/bằng chứng; không mặc định expected là vô hại hoặc denied là tấn công | R4, R5; kiểm rule sự kiện và luồng escalation |
| CLASS-10 | Fallback cho lỗi chưa biết không fail-open, không báo thành công sai và không lộ chi tiết | R1, R2, R4; exception mới, thiếu context và classifier lỗi |
| CLASS-11 | Các boundary đồng bộ, bất đồng bộ, transaction và giao thức dùng cùng ý nghĩa classification và contract công bố tương ứng | R6, R8; lỗi tại commit, serialization, callback, bulk và job |
| CLASS-12 | Thay thư viện, taxonomy hoặc mapping có kiểm tra hồi quy và lịch sử rule; audit giữ bằng chứng tối thiểu có kiểm soát | R2, R4, R8; migration policy, regression và rà telemetry |

Ví dụ đặc tả chi tiết cho retry:

```yaml
id: CLASS-05
asset: enrollment-command
trigger: A dependency failure occurs during command execution
requiredBehavior:
  - Determine operation outcome from trusted execution evidence
  - Preserve UNKNOWN if the commit result cannot be established
  - Authorize retry only under the operation idempotency profile
  - Recheck authorization, cancellation and remaining budget
forbiddenBehavior:
  - Retry solely because the exception class is marked transient
  - Report NOT_APPLIED without evidence for the relevant effects
measurement:
  retriesOutsideApprovedPolicy: 0
  failureDecisionsWithRuleAndPolicyVersionPercent: 100
evidence:
  - Commit-acknowledgment loss test
  - Reconciliation and idempotency test
  - Layered-retry and deadline test
owner: application-platform
```

Các số liệu trên áp dụng cho phạm vi kiểm thử và điểm quyết định đã xác định. Có `ruleId` trong log không tự chứng minh rule đúng; phải đối chiếu với trạng thái thực và tác động ở nguồn có thẩm quyền.

## 13. Ma trận kiểm thử theo thuộc tính

Đây là tiêu chí thiết kế kiểm thử, chưa phải kết quả QA của một triển khai cụ thể. Dùng dữ liệu tổng hợp và fault injection trong môi trường có thẩm quyền.

| Tình huống | Kết quả mong đợi |
|---|---|
| Input sai tại boundary validation đã thiết kế | Phân loại validation, phản hồi an toàn, không tự retry nguyên request |
| Cùng `IllegalArgumentException` phát sinh do bug nội bộ | Không mặc định đổ lỗi cho client |
| Policy có kết quả từ chối | Dừng hành động, category và audit theo contract |
| Không gọi được policy service | Không cho phép; phân biệt với kết quả policy từ chối ở nội bộ |
| Database hoặc dịch vụ lỗi trước dispatch có bằng chứng | Outcome theo bằng chứng, retry chỉ khi đủ điều kiện |
| Mất xác nhận sau commit | Giữ chưa xác định hoặc đối soát; không tự khẳng định rollback |
| Local transaction rollback nhưng remote side effect đã xảy ra | Không gắn toàn workflow là `NOT_APPLIED` |
| Exception transient trên lệnh ghi không có idempotency contract | Không retry tự động chỉ theo tên class |
| SDK, gateway và worker cùng có retry | Tổng lần thử và deadline không vượt policy toàn thao tác |
| Caller hủy hoặc deadline hết khi đang backoff | Không tạo lần thử mới trái contract |
| Client hủy sau tác động đã được xác nhận | Không biến cancellation thành bằng chứng chưa áp dụng |
| Wrapper chứa exception nghiệp vụ có context quan trọng | Giữ đúng ý nghĩa; không chỉ chọn cause sâu nhất |
| Lỗi cleanup/suppressed xuất hiện sau một kết quả đã rõ | Không tự ghi đè outcome bằng phỏng đoán |
| Đồ thị cause dài hoặc có tham chiếu lặp được tạo trong test | Classifier kết thúc trong giới hạn và fallback an toàn |
| Message chứa SQL, token hoặc chuỗi giống tên category | Không điều khiển classification hoặc lọt vào public response |
| Lỗi integrity mới chưa có mapping nghiệp vụ | Không tự công bố dữ liệu trùng hoặc tên constraint |
| Expected denial lặp bất thường | Có tín hiệu theo policy, không mặc định bỏ qua hoặc gắn tấn công cho mọi lần |
| Lỗi xuất hiện tại commit, async callback hoặc serialization | Ý nghĩa và mức công bố vẫn nhất quán qua boundary |
| Classifier, catalog hoặc sink chẩn đoán lỗi | Không fail-open, không lộ lỗi thứ cấp, không báo thành công sai |
| Thay driver, wrapper hoặc phiên bản rule | Hành vi của các ca còn thuộc contract được giữ hoặc đổi có phê duyệt |

Bằng chứng cần bao phủ kết quả phân loại, hành động thực sự đã chạy, response công khai, trạng thái dữ liệu và sự kiện quan sát. Chỉ assert một enum trả về chưa chứng minh classifier không gây retry thừa hoặc công bố sai.

Với ca `UNKNOWN`, cần mô phỏng đúng vị trí mất xác nhận và kiểm nguồn có thẩm quyền. Một test chỉ ném timeout trước khi làm gì không chứng minh hệ thống xử lý đúng timeout sau tác động.

Với lỗi quyền, cần thử cả từ chối hợp lệ, không có quyết định và quyết định hết hiệu lực. Ba tình huống không được vô tình đi chung một nhánh cho phép.

## 14. Quản trị taxonomy trong vòng đời phát triển

Mỗi rule nên có định nghĩa, nguồn exception hoặc mã phụ thuộc được nhận diện, context bắt buộc, outcome có thể kết luận, recovery được phép, public mapping, sự kiện và owner. Thay đổi một trục cần đánh giá những nơi dùng trục đó để ra quyết định.

Ví dụ, đổi category của một lỗi không chỉ thay tên trên dashboard. Nó có thể kích hoạt retry, đổi HTTP status hoặc làm một workflow chuyển sang bù trừ. Vì vậy, policy phân loại cần được version hóa và kiểm theo tác động, không sửa tùy ý như nhãn hiển thị.

Theo dõi nhóm chưa phân loại giúp cải thiện coverage, nhưng không cố ép mọi sự cố mới vào một category cũ để giảm số liệu. Cần giữ fallback an toàn trong thời gian điều tra và bổ sung rule khi đã có đủ bằng chứng.

Những lỗi đặc tả thường gặp:

- **“Checked là lỗi client, unchecked là lỗi server.”** Nhầm quy tắc ngôn ngữ với ý nghĩa và trách nhiệm của thao tác.
- **“Transient thì retry.”** Bỏ qua outcome, idempotency và tác động đã xảy ra.
- **“Bị timeout nghĩa là chưa ghi.”** Nhầm không nhận được xác nhận với không có tác động.
- **“Expected không cần quan sát.”** Bỏ qua số lượng, mẫu hành vi và sự kiện kiểm soát quan trọng.
- **“Mọi denied đều là tấn công.”** Gây nhiễu và đánh giá sai bằng chứng.
- **“Cause sâu nhất luôn đúng nhất.”** Làm mất ngữ cảnh nghiệp vụ, transaction hoặc wrapper.
- **“Một catch Exception là hoàn tất.”** Chưa đặc tả fallback, phục hồi, cancellation và các boundary khác.
- **“Code nội bộ càng chi tiết thì client càng nên thấy.”** Nhầm khả năng chẩn đoán với quyền công bố.

Phân loại exception có giá trị khi nó dẫn tới quyết định đúng và kiểm chứng được. Một đặc tả tốt tách bản chất sự cố, trạng thái tác động, quyền phục hồi và mức công bố; giữ sự chưa biết khi thiếu bằng chứng; rồi nối từng quyết định với owner, policy và ca nghiệm thu phù hợp.
