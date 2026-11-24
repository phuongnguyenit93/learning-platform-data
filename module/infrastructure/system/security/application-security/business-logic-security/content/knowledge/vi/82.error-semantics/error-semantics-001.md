# Business rejection response: Phản hồi từ chối nghiệp vụ

Trong chương **Error Semantics**, phản hồi từ chối nghiệp vụ mô tả một yêu cầu mà hệ thống đã hiểu nhưng không cho phép thực hiện vì quyền hoặc quy tắc nghiệp vụ. Ví dụ: chưa đủ phê duyệt để xác nhận đơn hàng, giá gửi từ client không khớp báo giá hợp lệ, đối tượng đã ở trạng thái kết thúc hoặc cùng khóa idempotency được dùng với nội dung khác.

Đây là một phần của bảo mật logic nghiệp vụ. Một phản hồi mơ hồ có thể khiến client gửi lại một lệnh đã thực hiện, tự bỏ bước phê duyệt hoặc tiết lộ thông tin về đối tượng ngoài quyền. Một phản hồi rõ nghĩa cần đi cùng kiểm soát quyền theo đối tượng, state machine, transaction và idempotency đúng ở máy chủ.

Bài học tập trung vào hợp đồng phản hồi: hệ thống biết chắc điều gì, được phép tiết lộ điều gì và client nên làm gì tiếp theo. Một thông báo lỗi được viết tốt không thay thế việc thực thi invariant.

## 1. Từ chối nghiệp vụ là một kết quả có chủ đích

Giả sử lệnh `CONFIRM_ORDER` chỉ hợp lệ khi:

```text
actor được phép xác nhận đúng đơn hàng
AND order thuộc đúng tenant
AND order.state == APPROVED
AND order.version == command.expectedVersion
AND báo giá được máy chủ chấp nhận
```

Nếu đơn hàng chưa được phê duyệt, hệ thống phải chặn việc xác nhận. Đây là một kết quả dự kiến của mô hình nghiệp vụ, không nhất thiết là lỗi phần mềm và cũng không tự chứng minh có tấn công.

Một phản hồi từ chối tốt cần giúp người có quyền hiểu rằng điều kiện nào chưa được đáp ứng, trong giới hạn thông tin được phép công bố. Nó không nên đưa client vào trạng thái phải đoán liệu đơn hàng đã được xác nhận hay chưa.

Cần phân biệt hai câu hỏi:

- **Lượt yêu cầu hiện tại được xử lý thế nào?** Bị từ chối, nhận lại kết quả cũ, được tiếp nhận hay kết thúc thành công.
- **Lệnh nghiệp vụ đã tạo tác động chưa?** Chưa áp dụng, đã commit, đang xử lý hoặc chưa xác định được.

Hai câu hỏi này không luôn có cùng câu trả lời. Một người dùng có thể bị từ chối đọc lại kết quả vì vừa mất quyền, trong khi lệnh tương ứng đã được thực hiện từ trước. Không được suy từ “request hiện tại bị từ chối” thành “lệnh đó chưa bao giờ thực hiện”.

## 2. Phân biệt từ chối, lỗi kỹ thuật và kết quả chưa xác định

| Tình huống | Điều hệ thống biết | Ngữ nghĩa phản hồi cần giữ |
| --- | --- | --- |
| Chưa có phê duyệt, bị chặn trước khi áp dụng | Quy tắc không cho phép lệnh tại thời điểm kiểm tra | Từ chối nghiệp vụ |
| Không đủ quyền với đối tượng | Lượt truy cập không được phép | Từ chối truy cập; không tiết lộ thêm trạng thái ngoài quyền |
| Database lỗi và rollback đã được xác nhận, chưa có tác động bên ngoài | Lần thực thi này không tạo tác động nghiệp vụ đã commit | Lỗi kỹ thuật với trạng thái thực thi đã biết |
| Kết nối mất đúng lúc commit, chưa đối soát được | Transaction có thể đã commit hoặc chưa | Kết quả thực thi chưa xác định |
| Đã gửi lệnh thanh toán ra ngoài nhưng không nhận được kết quả | Tác động bên ngoài có thể đã xảy ra | Chưa xác định hoặc đang đối soát; không tuyên bố chưa thực hiện |
| Job đã được lưu và sẽ chạy nền | Hệ thống đã tiếp nhận, chưa có kết quả cuối | Đang xử lý, không phải thành công nghiệp vụ cuối cùng |
| Retry trả receipt thành công của cùng lệnh | Lệnh đó đã hoàn tất theo receipt | Replay kết quả, không thực hiện lại |

Timeout không tự chứng minh rollback. Một exception từ kết nối cũng không luôn cho biết transaction đã commit hay chưa. Chỉ trả trạng thái “chưa áp dụng” khi có căn cứ từ ranh giới thực thi và các tác động thuộc phạm vi lệnh.

Tương tự, “không đánh giá được quyền vì dịch vụ quyền lỗi” khác với “chính sách xác định người này không có quyền”. Cả hai có thể khiến thao tác bị chặn, nhưng cần mã và dấu vết nội bộ khác nhau để client, người vận hành và hệ thống cảnh báo không hiểu sai nguyên nhân.

## 3. Thiết kế hợp đồng phản hồi có cấu trúc

Một phản hồi nên có tập trường nhỏ, ổn định và được tạo bởi máy chủ. Ví dụ dưới đây dành cho người đã có quyền xem trạng thái phê duyệt của đơn hàng:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json
Cache-Control: no-store
```

```json
{
  "code": "ORDER_APPROVAL_REQUIRED",
  "message": "Đơn hàng cần được phê duyệt trước khi xác nhận.",
  "requestOutcome": "REJECTED",
  "operationState": "NOT_APPLIED",
  "recovery": {
    "action": "REFRESH_STATE",
    "automaticRetry": false
  },
  "correlationId": "srv-corr-7f2a"
}
```

Đây là hợp đồng minh họa của một API, không phải một định dạng bắt buộc cho mọi hệ thống. Điều quan trọng là các trường không mâu thuẫn và giữ đúng ngữ nghĩa đã công bố.

| Trường | Vai trò | Ràng buộc thiết kế |
| --- | --- | --- |
| `code` | Mã để client phân nhánh | Ổn định theo ý nghĩa; không lấy từ tên exception động |
| `message` | Thông báo cho con người | Có thể dịch; không phải căn cứ duy nhất để chương trình quyết định |
| `requestOutcome` | Kết quả xử lý lượt yêu cầu này | Không đánh đồng với lịch sử thực thi của lệnh |
| `operationState` | Trạng thái thực thi nếu biết và được phép tiết lộ | Có thể không cung cấp khi thiếu căn cứ hoặc thiếu quyền |
| `recovery` | Hướng xử lý tiếp theo được hỗ trợ | Là hướng dẫn, không cấp quyền hay bỏ qua guard |
| `correlationId` | Tham chiếu hỗ trợ điều tra | Không chứa bí mật, không thay thế quyền xem log |
| `operationId` nếu có | Tra cứu một lệnh đang xử lý hoặc chưa rõ kết quả | Phải kiểm tra quyền khi tra cứu |
| `details` nếu cần | Chi tiết theo mã lỗi | Danh sách trường cho phép, không serialize dữ liệu nội bộ tùy ý |

### 3.1. Mã lỗi là một phần của hợp đồng nghiệp vụ

Ví dụ các mã ổn định:

```text
ORDER_APPROVAL_REQUIRED
ORDER_STATE_CONFLICT
OBJECT_VERSION_CONFLICT
QUOTE_NOT_ACCEPTED
IDEMPOTENCY_PAYLOAD_CONFLICT
RESOURCE_UNAVAILABLE
EXECUTION_STATE_UNKNOWN
DEPENDENCY_UNAVAILABLE
```

Một mã nên biểu diễn một ngữ nghĩa đủ rõ để client chọn hành vi phục hồi. Không dùng một mã duy nhất `BUSINESS_ERROR` cho mọi trường hợp nếu các trường hợp cần hành vi khác nhau.

Ngược lại, không tạo mã bằng cách ghép mã đơn hàng, tenant hoặc nội dung exception. Những giá trị đó làm mã mất tính ổn định và có thể tiết lộ dữ liệu. Các chi tiết được phép, nếu cần, nằm trong cấu trúc riêng có kiểm soát.

### 3.2. Trạng thái thực thi chỉ xuất hiện khi có căn cứ

`operationState = NOT_APPLIED` là một cam kết về phạm vi tác động nghiệp vụ của lệnh được nói tới. Nó không có nghĩa hệ thống không ghi security log, không tăng bộ đếm hay không cập nhật hạn mức chống lạm dụng.

Với lỗi quyền, có thể chỉ trả:

```json
{
  "code": "RESOURCE_UNAVAILABLE",
  "message": "Không thể thực hiện yêu cầu với tài nguyên này.",
  "requestOutcome": "REJECTED",
  "recovery": {
    "action": "NONE",
    "automaticRetry": false
  },
  "correlationId": "srv-corr-82d1"
}
```

Không có `operationState` ở đây: người gọi không được suy ra một lệnh cũ đã thành công, thất bại hay tồn tại. Phản hồi chỉ cho biết lượt yêu cầu hiện tại không được thực hiện theo quyền truy cập hiện có.

Nếu trạng thái là `UNKNOWN`, phải nói rõ theo hợp đồng thay vì bỏ trường một cách mơ hồ rồi mong client tự đoán. Trường hợp không cung cấp vì quyền và trường hợp biết rằng chưa xác định kết quả có thể cần hình chiếu công khai khác nhau.

## 4. Chọn HTTP status theo ngữ nghĩa, không suy kết quả từ status đơn lẻ

HTTP status hỗ trợ phân loại ở tầng giao thức; mã nghiệp vụ và trạng thái thực thi bổ sung chi tiết. Ví dụ một dự án có thể chọn:

| Nhóm tình huống | Status minh họa | Điều cần giữ trong hợp đồng |
| --- | --- | --- |
| Yêu cầu sai cú pháp hoặc không qua kiểm tra đầu vào cơ bản | 400 | Không nhầm với một lệnh nghiệp vụ đã được đánh giá đầy đủ |
| Cần xác thực theo cơ chế của API | 401 | Tuân thủ đầy đủ hợp đồng xác thực, không thay bằng mã nghiệp vụ tùy tiện |
| Không có quyền thực hiện hành động | 403 | Không trả thêm chi tiết về đối tượng ngoài phạm vi |
| Không tồn tại hoặc được che sự tồn tại theo hợp đồng | 404 | Áp dụng nhất quán chính sách công bố tài nguyên |
| Xung đột trạng thái, phiên bản hoặc idempotency payload | 409 | Client cần giải quyết xung đột, không chỉ gửi lại nguyên trạng vô hạn |
| Đầu vào có cấu trúc hợp lệ nhưng không đáp ứng quy tắc được API phân loại ở nhóm này | 422 | Mã nghiệp vụ giải thích điều kiện bị từ chối |
| Vượt giới hạn tần suất request | 429 | Không mặc định mọi hạn mức nghiệp vụ đều là rate limit |
| Phụ thuộc hoặc hạ tầng không sẵn sàng | Nhóm 5xx phù hợp | Không tự suy ra lệnh chưa được thực hiện |
| Tiếp nhận xử lý bất đồng bộ | 202 | Không khẳng định kết quả nghiệp vụ đã thành công |

Bảng là lựa chọn minh họa, không quy định rằng mọi từ chối nghiệp vụ phải dùng 409 hay 422. Cần chọn cách ánh xạ nhất quán cho API cụ thể và giữ các yêu cầu của giao thức tương ứng.

Không trả một response trông như thành công trong khi đã từ chối tác động, trừ khi API đã có hợp đồng kết quả chi tiết rõ ràng, chẳng hạn endpoint xử lý batch. Client và lớp trung gian không nên phải phân tích chuỗi `message` để biết yêu cầu có thành công hay không.

Một mã 5xx cũng không đủ để bật retry an toàn. Cần xem trạng thái thực thi và cơ chế idempotency của chính lệnh đó. Việc chỉ cấu hình “gặp lỗi server thì đổi key và thử lại” có thể tạo thanh toán hoặc hoàn tiền trùng.

## 5. Đưa invariant và transaction vào ý nghĩa của phản hồi

Xét một lệnh xác nhận đơn hàng. Để phản hồi `ORDER_APPROVAL_REQUIRED` thực sự có nghĩa chưa áp dụng xác nhận, luồng thực thi có thể được thiết kế như sau:

1. Xác thực tác nhân, kiểm tra đầu vào cơ bản và phân giải tenant từ ngữ cảnh tin cậy.
2. Bắt đầu transaction; tìm và khóa đúng đơn hàng trong tenant hoặc dùng cơ chế kiểm soát phiên bản tương đương.
3. Kiểm tra quyền theo đối tượng trước khi công bố chi tiết trạng thái.
4. Kiểm tra idempotency theo hợp đồng, expected version, phê duyệt, trạng thái và báo giá hợp lệ.
5. Nếu có điều kiện từ chối, không tạo thay đổi xác nhận; rollback mọi thay đổi nghiệp vụ thuộc lần thử cần rollback.
6. Nếu hợp lệ, cập nhật trạng thái, ghi sự kiện và lưu receipt thành công trong cùng transaction.
7. Nếu cần phát tác vụ ra ngoài, ghi outbox trong cùng transaction; chỉ xử lý sau commit.
8. Chỉ dựng response thành công sau khi commit được xác nhận.

Quy tắc không chỉ nằm ở thứ tự các dòng code. Nếu trạng thái được đọc trước, sau đó có transaction khác thay đổi rồi lệnh vẫn thực thi theo kết quả cũ, phản hồi có thể không còn phù hợp. Khóa, expected version và điều kiện cập nhật phải bảo vệ ranh giới quyết định thực tế.

Đối với báo giá, máy chủ phải xác định giá hợp lệ từ dữ liệu và quy tắc của mình. Không được nhận giá tùy ý rồi chỉ trả lỗi khi có người phát hiện bất thường. Tương tự, một trường `approved = true` trong body không thay thế bản ghi phê duyệt được kiểm soát.

### 5.1. Tránh gây tác động trước khi biết có được phép hay không

Một luồng nguy hiểm là gọi bên thanh toán trước, sau đó mới kiểm tra phê duyệt và trả `NOT_APPLIED` vì đơn hàng chưa được duyệt. Local transaction rollback không thu hồi một khoản tiền đã được hệ thống ngoài chấp nhận.

Các điều kiện có thể kiểm tra trước cần được kiểm tra trước khi tạo tác động. Với quy trình nhiều hệ thống, cần có trạng thái lệnh bền vững, định danh chống lặp và giao thức đối soát hoặc bù trừ phù hợp.

Nếu đã có một phần tác động và đang bù trừ, không mô tả tình huống là từ chối đơn giản chưa áp dụng. Client cần thấy trạng thái quy trình phù hợp, chẳng hạn đang xử lý hoặc đang đối soát theo hợp đồng. Chỉ tuyên bố đã bù trừ xong khi đã có căn cứ.

### 5.2. Atomic và partial phải được phân biệt

Một lệnh nguyên tử bị từ chối không nên để lại một phần thay đổi nghiệp vụ của chính lệnh đó. Nếu endpoint batch cho phép từng phần tử có kết quả riêng, response phải biểu diễn kết quả từng phần tử và tổng thể một cách rõ ràng.

Không trả `NOT_APPLIED` cho toàn bộ batch khi ba phần tử đã commit và hai phần tử bị từ chối. Mỗi phần tử cần định danh, trạng thái và hướng phục hồi phù hợp. Nếu batch được định nghĩa là nguyên tử, phải rollback toàn bộ theo đúng thiết kế đó.

## 6. Ánh xạ lỗi ở ngoài ranh giới thực thi

Mã giả dưới đây minh họa trách nhiệm của lớp tạo response:

```text
handleRequest(input, trustedContext):
    try:
        result = commandService.executeAndCompleteTransaction(
            input, trustedContext
        )
        return successOrReplayProjection(result, trustedContext)

    catch BusinessRejection rejection:
        if not rejection.hasKnownExecutionState:
            return unresolvedProjection(rejection, trustedContext)

        return safeBusinessRejectionProjection(
            rejection.code,
            rejection.knownExecutionState,
            trustedContext
        )

    catch CommitOutcomeUnknown unknown:
        return unresolvedProjection(unknown, trustedContext)

    catch TechnicalFailure failure:
        return safeTechnicalFailureProjection(
            failure.knownExecutionStateIfAny,
            trustedContext
        )
```

Đây là thuật toán minh họa, không phải mã Java hoàn chỉnh. Một số điểm cần chú ý khi hiện thực:

- `executeAndCompleteTransaction` chỉ trả thành công sau ranh giới commit thực sự. Nếu dùng transaction qua proxy, lớp dựng response phải quan sát được cả lỗi commit xảy ra sau khi phương thức nghiệp vụ trả về.
- Không ánh xạ mọi exception thành `BUSINESS_REJECTED`. Lỗi lập trình, phụ thuộc và kết quả commit chưa rõ cần nhánh riêng.
- Không lấy `exception.getMessage()` làm body công khai. Thông báo nội bộ có thể chứa SQL, stack trace, tên dịch vụ hoặc dữ liệu đối tượng khác.
- Danh sách mã công khai, message template và trường chi tiết nên do máy chủ quản lý. Mã không nhận diện được phải đi về một phản hồi an toàn, kèm dấu vết điều tra phù hợp.
- Việc rollback đã xác nhận hay chưa phải đến từ cơ chế thực thi, không phải một cờ mà client được phép gửi.

Một lớp xử lý lỗi chung giúp phản hồi nhất quán, nhưng không được biến nó thành nơi tự đoán nghiệp vụ từ text exception. Quy tắc cần tạo kết quả hoặc lỗi miền có cấu trúc; lớp biên chỉ công bố hình chiếu được phép.

## 7. Không để phản hồi lỗi thành kênh dò thông tin

Một người không có quyền xem đơn hàng không nên nhận thông báo như “đơn đang chờ phê duyệt bởi trưởng nhóm A, giá trị 800 triệu”. Dù thao tác đã bị chặn, dữ liệu vẫn bị lộ.

Thứ tự và mức chi tiết cần tuân theo chính sách công bố:

```text
Nếu không đủ quyền biết tài nguyên:
    trả hình chiếu công khai không tiết lộ sự tồn tại hoặc trạng thái
Nếu được xem tài nguyên nhưng không được thực hiện hành động:
    trả lý do trong phạm vi được phép
Nếu được thực hiện hành động nhưng điều kiện nghiệp vụ chưa đạt:
    trả mã và hướng phục hồi thích hợp
```

Cần kiểm soát cả:

- Mã lỗi, message và field-level details.
- Phiên bản hiện tại, số dư, giá, hạn mức và điều kiện phê duyệt.
- Tên người duyệt, mã tài liệu, đường dẫn bằng chứng và các đối tượng liên quan.
- Header, response schema và metadata có thể khác nhau giữa tài nguyên tồn tại và không tồn tại.
- Log hoặc đường dẫn hỗ trợ được response liên kết tới.

Phản hồi bên ngoài có thể dùng mã chung trong khi log nội bộ lưu reason cụ thể cho người được phép điều tra. Tuy nhiên, cần bảo vệ quyền đọc log; chuyển dữ liệu nhạy cảm từ response sang log không tự giải quyết vấn đề nếu log mở cho mọi người.

Các biện pháp như kiểm soát tần suất và phát hiện dò tài nguyên có thể bổ sung. Không hứa rằng chỉ dùng cùng một message là đã loại bỏ mọi kênh suy luận qua thời gian hoặc hành vi hệ thống.

## 8. Hướng phục hồi phải an toàn và có thể thực hiện

Thay vì một cờ `retryable` thiếu ngữ cảnh, có thể dùng hành động phục hồi hữu hạn:

| Recovery action minh họa | Ý nghĩa | Điều client không được tự làm |
| --- | --- | --- |
| `REFRESH_STATE` | Đọc lại dữ liệu trong quyền hiện tại | Không tự sửa trạng thái để vượt guard |
| `REFRESH_AND_REVIEW` | Đọc bản mới và yêu cầu người dùng xem lại ý định | Không tự tăng expected version rồi gửi một thao tác nhạy cảm |
| `REQUEST_APPROVAL` | Đi qua luồng phê duyệt nếu tác nhân có quyền | Không tự gắn cờ đã duyệt vào request |
| `REFRESH_QUOTE` | Lấy báo giá mới và xác nhận lại nếu cần | Không tự chấp nhận mọi giá thay người dùng |
| `CHECK_OPERATION_STATUS` | Tra cứu lệnh đã có định danh | Không đổi idempotency key để thực hiện lại khi kết quả còn mơ hồ |
| `RETRY_SAME_COMMAND` | Thử lại cùng lệnh theo điều kiện đã công bố | Không đổi payload hoặc tạo thêm ý định thanh toán |
| `NONE` | Không có hành động tự động được hỗ trợ | Không lặp request vô hạn |

Chỉ công bố `REQUEST_APPROVAL` nếu người gọi được phép biết và sử dụng luồng tương ứng. Một recovery action không phải token cấp quyền. Máy chủ vẫn phải kiểm tra lại quyền, trạng thái, phiên bản và invariant khi request tiếp theo đến.

Với lỗi kỹ thuật đã biết an toàn để retry, hợp đồng có thể cho phép gửi lại cùng key và payload, dùng backoff và giới hạn số lần. Không suy ra điều này chỉ từ nhãn “lỗi tạm thời”. Cần biết lệnh có idempotency thế nào và tác động đã được xác định đến đâu.

Với từ chối do trạng thái, nguyên request thường không tự trở nên hợp lệ nếu chỉ đợi vài mili giây. Đọc lại trạng thái và xác nhận lại ý định có thể là điều kiện cần trước khi tạo một lệnh mới.

## 9. Idempotency và phản hồi từ chối

### 9.1. Cùng key, khác payload là xung đột

Giả sử key `K1` đã được ràng buộc với lệnh hoàn 100 đơn vị tiền cho giao dịch A. Client gửi lại `K1` nhưng đổi thành 200 hoặc đổi sang giao dịch B. Hệ thống cần xử lý theo hợp đồng xung đột idempotency, không coi đây là retry tương đương.

Phản hồi `IDEMPOTENCY_PAYLOAD_CONFLICT` không nên trả toàn bộ payload gốc. Người gọi phải được xác thực và kiểm tra quyền trước khi nhận metadata của lệnh đã lưu. Phạm vi khóa cần tránh giao thoa giữa tenant hoặc tác nhân không liên quan.

Thông báo không nên khuyên “đổi key rồi gửi lại” một cách vô điều kiện. Nếu lệnh gốc có thể đã commit, cách làm đó có thể tạo tác động trùng. Trước hết phải xác định kết quả lệnh cũ và ý định mới có thật sự độc lập hay không.

### 9.2. Receipt cũ không mô tả trạng thái đối tượng hiện tại

Một lệnh xác nhận đã thành công ở version 12. Sau đó đơn hàng chuyển tiếp sang một trạng thái khác. Retry lệnh cũ có thể trả receipt thành công của chính lệnh đó, không phải một lần xác nhận mới và cũng không có nghĩa đơn hàng hiện vẫn ở version 12.

Client cần phân biệt thông tin về kết quả lệnh với snapshot hiện tại. Nếu cần hiển thị trạng thái hiện tại, phải đọc qua API tương ứng với quyền hiện tại.

### 9.3. Công bố rõ có lưu kết quả từ chối hay không

Hai hợp đồng có thể dẫn tới hành vi khác nhau sau khi điều kiện nghiệp vụ thay đổi:

- **Lưu kết quả từ chối như một kết quả cuối của lệnh:** retry cùng key và payload có thể nhận lại từ chối cũ. Sau một lần từ chối chắc chắn chưa áp dụng, người dùng có thể cần tạo ý định mới theo quy tắc của sản phẩm.
- **Cho phép đánh giá lại một số từ chối phụ thuộc trạng thái:** sau khi đã có phê duyệt, cùng lệnh có thể được đánh giá lại. Cần quy định rõ điều kiện, cách ràng buộc fingerprint, thời hạn và xử lý đồng thời.

Không trộn hai cách một cách ngẫu nhiên giữa các endpoint. Nếu lưu receipt từ chối, phải thiết kế cách lưu bền vững sau khi rollback nghiệp vụ và không nhầm nó với receipt thành công. Nếu không lưu hoặc không giữ ràng buộc key sau từ chối, phải công bố giới hạn bảo đảm về việc nhận diện payload đã từng bị từ chối.

Dù dùng cách nào, mỗi lần truy cập kết quả vẫn phải kiểm tra quyền hiện tại. Một rejection hoặc approval trong quá khứ không trở thành quyền vĩnh viễn của người gọi.

## 10. Khi kết quả chưa xác định hoặc đang xử lý

Giả sử server đã gửi yêu cầu thanh toán tới hệ thống ngoài, sau đó mất kết nối trước khi biết kết quả. Phản hồi an toàn cho người có quyền có thể mang cấu trúc:

```json
{
  "code": "EXECUTION_STATE_UNKNOWN",
  "message": "Chưa xác định được kết quả của lệnh. Hãy kiểm tra trạng thái trước khi gửi lệnh mới.",
  "requestOutcome": "UNRESOLVED",
  "operationState": "UNKNOWN",
  "operationId": "op-4c7e",
  "recovery": {
    "action": "CHECK_OPERATION_STATUS",
    "automaticRetry": false
  },
  "correlationId": "srv-corr-b302"
}
```

Chỉ cung cấp `operationId` khi hệ thống đã có tham chiếu đủ bền vững để tra cứu. Endpoint trạng thái phải kiểm tra tenant, tác nhân và quyền với lệnh; biết mã lệnh không đủ để đọc kết quả.

Nếu công việc đã được tiếp nhận rõ ràng và còn đang chạy, phản hồi cần thể hiện trạng thái chờ, kèm cơ chế theo dõi phù hợp. Không dùng “đang xử lý” để che việc hệ thống thực sự không biết lệnh có tồn tại hoặc đã được tiếp nhận hay chưa.

Việc tra cứu có thể tiếp tục trả trạng thái chưa rõ cho đến khi đối soát xong. Client không nên xem “chưa có kết quả trong projection” là “chắc chắn chưa thực hiện”, nhất là khi nguồn trạng thái cập nhật chậm.

Trong quy trình có bù trừ, cần phân biệt đang bù trừ với đã khôi phục trạng thái theo cam kết. Một phản hồi từ chối cuối cùng không được xóa dấu vết rằng trước đó đã có tác động bên ngoài.

## 11. Hành vi client và dấu vết quan sát

### 11.1. Client xử lý theo mã và trạng thái, không theo câu chữ

Thông báo tiếng Việt có thể thay đổi để dễ hiểu hơn mà không làm đổi ý nghĩa mã lỗi. Client nên phân nhánh theo `code`, `requestOutcome` và các trường đã công bố, không kiểm tra xem message có chứa từ “phê duyệt” hay không.

Các hành vi cần tránh:

- Tự sửa giá, hạn mức hoặc cờ phê duyệt để gửi lại cho qua lỗi.
- Tự tăng expected version mà không đọc và xem lại trạng thái mới.
- Đổi idempotency key mỗi lần gặp timeout.
- Coi việc nút đã bị vô hiệu hóa là đủ để ngăn gửi trùng.
- Xóa trạng thái thành công hiện tại chỉ vì một response từ request cũ đến muộn.

Giao diện nên liên kết phản hồi với đúng lượt thao tác và lệnh tương ứng. Nếu response đến lệch thứ tự, cần tránh để lỗi của một lần thử cũ ghi đè kết quả mới hơn. Khi chưa rõ kết quả, hiển thị tình trạng chờ kiểm tra thay vì mời người dùng bấm thanh toán lại.

### 11.2. Ghi đủ dữ liệu điều tra, tránh sao chép dữ liệu nhạy cảm

Dấu vết nội bộ có thể gồm mã quyết định, correlation ID, tác nhân tin cậy, tenant, hành động, reason nội bộ, phiên bản quy tắc và trạng thái transaction đã biết. Chỉ lưu tham chiếu đối tượng và chi tiết cần thiết theo quyền và chính sách lưu trữ.

Không ghi nguyên token, cookie, stack trace vào response. Không sao chép toàn bộ body vào log chỉ vì request bị từ chối. Nội dung reason tự nhập cần được xử lý có cấu trúc để tránh giả mạo dòng log hoặc đưa dữ liệu không cần thiết vào hệ thống quan sát.

Một từ chối nghiệp vụ bình thường không nhất thiết là sự cố mức cao. Tuy nhiên, chuỗi request liên tục thử bỏ qua phê duyệt, đổi đối tượng hoặc xung đột idempotency có thể cần cảnh báo. Metric dùng mã reason hữu hạn; dữ liệu định danh phục vụ điều tra nằm trong kho log hoặc audit được phân quyền phù hợp.

Việc ghi nhận denied phải phản ánh quyết định thực sự, còn thành công phải phản ánh đúng ranh giới commit. Không ghi sự kiện nghiệp vụ thành công chỉ vì handler đã tạo một response dự kiến trước khi transaction hoàn tất.

## 12. Kiểm thử hợp đồng phản hồi cùng kịch bản lạm dụng

Kiểm thử cần quan sát response và cả dữ liệu, receipt, sự kiện, outbox hoặc tác động bên ngoài. Response đẹp nhưng trạng thái đã bị sửa trái phép vẫn là một lỗi bảo mật.

| Kịch bản | Kỳ vọng phản hồi | Điều phải kiểm chứng ở hệ thống |
| --- | --- | --- |
| Chưa phê duyệt nhưng gọi xác nhận | Mã phê duyệt cần thiết, không hướng dẫn bỏ bước | Không xác nhận, không có outbox thực thi trái phép |
| Sửa giá từ client | Mã báo giá không được chấp nhận | Máy chủ không dùng giá tùy ý |
| Truy cập đối tượng khác tenant | Hình chiếu không tiết lộ ngoài quyền | Không lộ giá, trạng thái, phiên bản hoặc người duyệt |
| Biết ID nhưng không có quyền hành động | Từ chối theo hợp đồng | ID không trở thành quyền truy cập |
| Hai lệnh cùng expected version | Một lệnh thắng, lệnh còn lại xung đột | Không ghi đè thay đổi mới; response khớp kết quả commit |
| Guard từ chối sau một thay đổi tạm trong transaction | Chỉ tuyên bố chưa áp dụng khi rollback đã được xác nhận | Không để lại thay đổi nghiệp vụ một phần |
| Lỗi xảy ra lúc commit | Lỗi kỹ thuật hoặc chưa xác định theo căn cứ | Không trả thành công trước commit, không đoán rollback |
| Mất response sau commit | Retry trả kết quả cũ theo quyền hiện tại | Không tạo tác động lần hai |
| Cùng key nhưng đổi payload | Xung đột idempotency, không lộ payload gốc | Không thực hiện nội dung mới dưới khóa đã ràng buộc |
| Quyền bị thu hồi trước retry | Không trả dữ liệu ngoài quyền | Receipt không cấp lại quyền cũ |
| Điều kiện đổi sau một rejection | Hành vi đúng chính sách lưu hoặc đánh giá lại rejection | Không có khác biệt ngầm giữa tài liệu và thực thi |
| Timeout sau khi gửi lệnh ra ngoài | Không tuyên bố NOT_APPLIED khi chưa đối soát | Có đường tra cứu và chống lặp phù hợp |
| Job chỉ mới vào hàng đợi | Trạng thái chờ, không giả thành công cuối | Operation ID tra cứu được trong quyền hiện tại |
| Batch có kết quả từng phần | Kết quả từng phần tử rõ ràng | Không báo cả batch chưa áp dụng khi đã có phần commit |
| Exception chứa SQL hoặc dữ liệu nhạy cảm | Phản hồi công khai đã lọc | Không serialize nguyên exception hoặc entity |
| Chuyển ngôn ngữ message | Mã và ý nghĩa phục hồi giữ nguyên | Client không phụ thuộc câu chữ |
| Response cũ đến sau response mới | Giao diện gắn đúng lượt thao tác | Không hướng người dùng thực hiện lại lệnh đã hoàn tất |
| Người không có quyền tra cứu operation | Phản hồi an toàn theo chính sách công bố | Không lộ kết quả qua endpoint trạng thái |

Các kiểm thử transaction cần đi qua ranh giới thực tế đang dùng. Chỉ gọi trực tiếp một hàm rồi giả định annotation sẽ rollback hoặc commit đúng có thể bỏ sót lỗi ở proxy, callback và thời điểm dựng response.

Với fault injection, đặt lỗi tại các mốc cụ thể: trước commit, trong lúc chưa biết kết quả commit, sau commit nhưng trước khi gửi response, và sau khi tác động ngoài đã được tiếp nhận. Các mốc này có ngữ nghĩa khác nhau, không nên bị gom thành một tình huống “server error”.

## 13. Tiêu chí hoàn thành một thiết kế phản hồi

Một hợp đồng từ chối nghiệp vụ cần trả lời được:

- Mã nào biểu diễn quy tắc bị từ chối, mã nào là lỗi kỹ thuật và mã nào là kết quả chưa xác định?
- Phản hồi nói về lượt request hiện tại hay trạng thái thực thi của một lệnh đã có định danh?
- Căn cứ nào cho phép tuyên bố chưa áp dụng hoặc đã commit?
- Người gọi được phép biết những lý do và chi tiết nào của đối tượng?
- Client cần đọc lại trạng thái, xin phê duyệt, kiểm tra lệnh cũ hay thực hiện một ý định mới?
- Retry cùng key, khác payload và rejection được lưu có hành vi nhất quán không?
- Transaction, outbox, receipt và dấu vết quan sát có khớp với điều response khẳng định không?

Một phản hồi từ chối đúng nghĩa giúp người dùng sửa được điều kiện hợp lệ, giúp client tránh tạo tác động trùng và giúp người vận hành điều tra bằng chứng thực tế. Cam kết đó chỉ đáng tin khi được bảo đảm bởi quyền theo đối tượng, invariant, state machine và ranh giới transaction của chính nghiệp vụ.
