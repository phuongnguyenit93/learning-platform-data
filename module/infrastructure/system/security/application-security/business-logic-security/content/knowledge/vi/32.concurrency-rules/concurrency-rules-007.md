# Concurrency conflict message

## Mục tiêu bài học

Concurrency conflict message là thông báo cho phía gọi biết một thao tác không thể được xử lý theo giả định ban đầu vì dữ liệu, trạng thái hoặc một yêu cầu liên quan đã thay đổi trong quá trình thực thi.

Trong bảo mật logic nghiệp vụ, thông báo xung đột là một phần của hợp đồng thực thi. Nó phải cho biết kết quả nào đã được xác nhận và bước tiếp theo nào an toàn. Một câu “Có lỗi, hãy thử lại” có thể khiến người dùng gửi lại lệnh đã commit, phê duyệt nội dung chưa xem hoặc ghi đè thay đổi của người khác.

Sau bài học, bạn có thể:

- Phân biệt xung đột phiên bản, xung đột trạng thái, yêu cầu đang xử lý và kết quả chưa xác định.
- Thiết kế mã lỗi máy đọc được cùng thông báo tiếng Việt rõ ràng.
- Chỉ khẳng định “chưa áp dụng” khi có đủ bằng chứng từ luồng thực thi.
- Đưa ra hướng khôi phục phù hợp với version checking, transaction và idempotency.
- Tránh tiết lộ dữ liệu ngoài quyền qua thông tin xung đột.
- Kiểm thử thông báo cùng hiệu ứng nghiệp vụ, thay vì chỉ so sánh chuỗi hiển thị.

## 1. Thông báo xung đột phải bảo vệ ý định nghiệp vụ

Giả sử một người mở đơn hàng ở version 12 để sửa số lượng. Một người khác thay nội dung và lưu thành version 13. Yêu cầu đầu tiên vẫn gửi `expectedVersion=12` nên bị từ chối theo điều kiện cập nhật.

Thông báo phù hợp cần giúp người dùng hiểu:

1. Đơn hàng đã thay đổi so với lúc họ xem.
2. Lệnh sửa lần này chưa được áp dụng, nếu transaction thực sự đã rollback hoặc chưa từng tạo hiệu ứng.
3. Họ cần tải lại để xem trạng thái mới trước khi quyết định gửi một lệnh khác.
4. Phần nhập cục bộ có thể được giữ để đối chiếu, nhưng không được tự ghi đè lên dữ liệu mới.

Nếu giao diện chỉ hiện “Không lưu được, thử lại”, người dùng có thể bấm nhiều lần. Nếu frontend tự đọc version mới rồi gửi lại nguyên biểu mẫu, cơ chế chống mất cập nhật bị vô hiệu hóa ở tầng trải nghiệm.

Thông báo không thay thế kiểm tra phía máy chủ. Dù giao diện đã khóa nút hoặc hiện cảnh báo, server vẫn phải kiểm tra quyền, trạng thái, version và idempotency trên mỗi thao tác tạo hiệu ứng.

## 2. Bắt đầu từ kết quả đã biết, không bắt đầu từ exception

Một lỗi kỹ thuật không luôn tương ứng với một kết quả nghiệp vụ duy nhất. Đặc biệt, mất kết nối gần thời điểm commit không đủ để kết luận rằng dữ liệu chưa được ghi.

Có thể dùng bốn nhóm kết quả:

| Kết quả | Ý nghĩa | Điều có thể thông báo |
|---|---|---|
| `NOT_APPLIED` | Đã xác nhận lệnh đang xét chưa tạo thay đổi nghiệp vụ, hoặc mọi thay đổi của lệnh đã rollback | Có thể nói “Thay đổi lần này chưa được áp dụng” |
| `COMMITTED` | Đã có kết quả bền vững chứng minh lệnh được commit | Trả kết quả thành công hoặc kết quả idempotency đã lưu |
| `IN_PROGRESS` | Hệ thống có bản ghi đáng tin cậy cho biết thao tác đang được xử lý | Hướng dẫn chờ hoặc kiểm tra tiến độ, không tạo lệnh thay thế tùy ý |
| `UNKNOWN` | Chưa xác định được lệnh đã commit hay chưa | Nói rõ chưa xác nhận kết quả và hướng dẫn kiểm tra theo định danh thao tác |

`NOT_APPLIED` có phạm vi là lệnh nghiệp vụ được mô tả, không có nghĩa mọi tài nguyên tạm đã biến mất. Ví dụ, một file ứng viên vẫn có thể tồn tại trong vùng staging dù thao tác kích hoạt phiên bản mới đã rollback.

`UNKNOWN` không phải một loại xung đột version. Không nên trả `STALE_VERSION` chỉ vì lỗi xảy ra trong đoạn mã đang xử lý đồng thời.

Một rollback được xác nhận trước khi commit có thể chứng minh lần thực thi không tạo hiệu ứng trong transaction đó. Ngược lại, nếu kết nối mất trong lúc commit, một lệnh rollback trên kết nối khác hoặc sau khi kết nối lại không chứng minh transaction trước chưa commit.

## 3. Phân loại nguyên nhân và hướng khôi phục

| Tình huống | Mã nghiệp vụ minh họa | Kết quả của lệnh đang xét | Hướng khôi phục |
|---|---|---|---|
| Version kỳ vọng không còn khớp | `STALE_ORDER_VERSION` | `NOT_APPLIED` sau xác nhận không ghi hoặc rollback | Tải lại, xem khác biệt, quyết định lại |
| Đơn hàng đã chuyển sang trạng thái không cho sửa | `ORDER_STATE_CHANGED` | `NOT_APPLIED` | Tải trạng thái mới; dùng thao tác đúng với trạng thái đó |
| Hạn mức thay đổi trước khi giữ chỗ | `LIMIT_CHANGED` | `NOT_APPLIED` nếu không giữ chỗ | Xem lại điều kiện; không tự chọn thay người dùng |
| Cùng khóa idempotency nhưng nội dung khác | `IDEMPOTENCY_KEY_REUSED` | Lệnh có nội dung mới không được áp dụng | Dừng và xử lý sai lệch ý định hoặc lỗi tích hợp |
| Cùng một thao tác còn đang xử lý | `OPERATION_IN_PROGRESS` | `IN_PROGRESS` | Chờ hoặc kiểm tra chính thao tác đó |
| Cạnh tranh tạm thời, các lần thực thi đã rollback | `TEMPORARY_CONTENTION` | `NOT_APPLIED` | Có thể retry cùng lệnh theo hợp đồng, với giới hạn |
| Mất phản hồi hoặc kết nối khi commit | `OPERATION_OUTCOME_UNKNOWN` | `UNKNOWN` | Tra kết quả bền vững hoặc retry cùng khóa theo giao thức idempotency |
| Retry của thao tác đã commit | Không phải lỗi xung đột mới | `COMMITTED` | Trả kết quả đã lưu sau kiểm tra quyền và fingerprint |

Với `IDEMPOTENCY_KEY_REUSED`, không diễn giải “lệnh lần này chưa áp dụng” thành “chưa từng có thao tác nào thành công với khóa này”. Một nội dung khác trước đó có thể đã commit. Không tiết lộ nội dung đó nếu người gọi không được quyền xem.

Các mã trên là ví dụ cho một hợp đồng API. Khi chọn tên mã thực tế, cần giữ ý nghĩa ổn định để frontend và client không phụ thuộc vào câu chữ dành cho con người.

## 4. Mỗi thông báo nên trả lời bốn câu hỏi

### 4.1. Điều gì đã thay đổi?

Chỉ nêu nguyên nhân đã được xác định và người gọi được phép biết. Ví dụ: “Đơn hàng đã thay đổi kể từ khi bạn mở” hoặc “Hồ sơ đã được gửi duyệt nên không thể sửa lúc này”.

Không nói “Người khác vừa sửa” nếu thay đổi có thể do job nền hoặc một yêu cầu trước đó của chính người dùng. Không nêu tên người sửa, số tiền hoặc nội dung mới chỉ để làm thông báo có vẻ cụ thể.

### 4.2. Thao tác lần này có được áp dụng không?

Thông báo cần phân biệt rõ:

- “Thay đổi lần này chưa được áp dụng” khi có xác nhận tương ứng.
- “Yêu cầu đang được xử lý” khi có trạng thái xử lý đáng tin cậy.
- “Chưa xác nhận được kết quả” khi hệ thống không biết commit đã hoàn tất hay chưa.

Không dùng một câu phủ định chắc chắn cho kết quả `UNKNOWN`. Điều này đặc biệt quan trọng với phê duyệt, giữ chỗ, tạo đơn và các thao tác có hiệu ứng khó đảo ngược.

### 4.3. Người dùng nên làm gì tiếp theo?

Hướng dẫn phải gắn với hành động thực sự có trong sản phẩm:

- Tải lại để xem và đối chiếu thay đổi.
- Giữ bản nháp cục bộ để sao chép phần nhập cần thiết.
- Kiểm tra tiến độ hoặc kết quả theo định danh thao tác.
- Thử lại cùng lệnh khi hợp đồng cho phép.
- Dùng quy trình rút hồ sơ, yêu cầu sửa hoặc điều chỉnh nếu trạng thái đã đổi.

Không hướng dẫn tự tạo khóa idempotency mới để “thử lại” một lệnh chưa rõ kết quả. Điều đó có thể tạo ra một ý định mới và dẫn tới hiệu ứng trùng.

### 4.4. Có thông tin nào cần giữ lại để hỗ trợ?

Có thể trả request ID hoặc mã tham chiếu hỗ trợ không chứa bí mật. Nếu có operation ID, máy chủ vẫn phải kiểm tra quyền khi tra kết quả; biết định danh không đồng nghĩa có quyền truy cập.

Không đưa stack trace, tên bảng, câu SQL, token, URL có chữ ký hoặc dữ liệu tenant khác vào thông báo công khai.

## 5. Hợp đồng API: tách mã ổn định khỏi câu chữ

Một phản hồi xung đột version có thể có dạng:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store
```

```json
{
  "type": "https://api.example.test/problems/stale-order-version",
  "title": "Dữ liệu đã thay đổi",
  "status": 409,
  "code": "STALE_ORDER_VERSION",
  "detail": "Đơn hàng đã thay đổi kể từ khi bạn mở. Thay đổi lần này chưa được áp dụng. Hãy tải lại để xem trước khi lưu.",
  "instance": "/request-errors/err-a12",
  "requestId": "req-a12",
  "outcome": "NOT_APPLIED",
  "recovery": {
    "mode": "REVIEW_REQUIRED",
    "actions": ["RELOAD", "KEEP_LOCAL_DRAFT"]
  },
  "expectedVersion": 12
}
```

Địa chỉ `type` là định danh ví dụ thuộc hợp đồng của dịch vụ; không phải nội dung cần gọi để xác định kết quả thao tác. Tương tự, `instance` chỉ nên là đường tra cứu nếu dịch vụ thực sự triển khai nó với kiểm soát truy cập phù hợp.

Các trường có trách nhiệm khác nhau:

| Trường | Trách nhiệm |
|---|---|
| `code` | Mã ổn định để client chọn luồng xử lý |
| `title` | Tóm tắt ngắn, có thể dịch |
| `detail` | Giải thích trường hợp cụ thể bằng ngôn ngữ người dùng |
| `status` | Phù hợp với HTTP status của phản hồi |
| `outcome` | Mức xác nhận về hiệu ứng của lệnh |
| `recovery.mode` | Kiểu khôi phục được dịch vụ hỗ trợ |
| `recovery.actions` | Gợi ý hành động cho giao diện, không phải quyền mới được cấp |
| `requestId` | Đối chiếu một lần gọi với log nội bộ |
| `operationId`, nếu có | Liên kết tới một ý định nghiệp vụ có thể tồn tại qua nhiều lần gọi |
| `expectedVersion`, nếu cần | Phiên bản mà lệnh đã sử dụng, không phải version để ghi đè |

Không buộc client phân tích chuỗi `detail` để nhận biết xung đột. Câu chữ có thể thay đổi hoặc được dịch trong khi mã và ngữ nghĩa xử lý cần ổn định.

Không đưa `currentVersion` vào phản hồi như một giá trị để frontend tự thay thế rồi gửi lại toàn bộ biểu mẫu. Nếu được phép trả, đó chỉ là phiên bản quan sát tại một thời điểm; dữ liệu vẫn có thể thay đổi tiếp trước lần gọi sau.

## 6. HTTP status cần phản ánh đúng hợp đồng

Các lựa chọn thường gặp cần được dùng có chủ đích:

| Trạng thái | Trường hợp phù hợp trong một hợp đồng được thiết kế rõ |
|---|---|
| `409 Conflict` | Lệnh xung đột với trạng thái hiện tại, như version trong body đã cũ hoặc chuyển trạng thái không còn hợp lệ |
| `412 Precondition Failed` | Điều kiện HTTP như `If-Match` không được thỏa mãn |
| `202 Accepted` | Yêu cầu đã được tiếp nhận theo mô hình bất đồng bộ, chưa có kết quả hoàn tất |
| `503 Service Unavailable` | Dịch vụ tạm thời không thể hoàn tất xử lý; body phải nói rõ kết quả đã biết hay còn chưa xác định |
| `403` hoặc `404` theo chính sách | Từ chối truy cập hoặc che giấu sự tồn tại của tài nguyên ngoài quyền |
| `500 Internal Server Error` | Lỗi hệ thống chưa được phân loại thành nguyên nhân nghiệp vụ đã biết |

Không ánh xạ mọi exception ở tầng database thành `409`. Lỗi kết nối, sai truy vấn, lỗi lập trình và vi phạm constraint không được nhận diện rõ không tự trở thành xung đột nghiệp vụ.

Một update count bằng 0 cũng không tự chứng minh version đã cũ. Câu lệnh có thể không khớp tenant, đối tượng, trạng thái hoặc điều kiện quyền. Chỉ trả nguyên nhân cụ thể khi service có đủ thông tin và được phép công bố.

`202` cần đi cùng cơ chế theo dõi thực sự. Không trả “đang xử lý” chỉ vì không biết điều gì đã xảy ra. Ngược lại, không coi một thao tác được tiếp nhận hợp lệ là lỗi chỉ vì kết quả chưa có ngay.

HTTP status không đủ để quyết định retry. Cùng là `503`, một trường hợp có thể đã xác nhận rollback, còn trường hợp khác chưa biết kết quả commit. Client cần dùng hợp đồng kết quả và idempotency tương ứng.

## 7. Không tiết lộ dữ liệu ngoài quyền qua thông báo xung đột

Một thông báo như “Đơn hàng của công ty B hiện ở version 18, tổng tiền 50 triệu” đã tiết lộ thông tin ngay cả khi thao tác cập nhật bị từ chối.

Các nguyên tắc cần giữ:

1. Xác định tenant từ ngữ cảnh xác thực, không từ payload tùy ý.
2. Kiểm tra quyền trên đối tượng và trên kết quả thao tác trước khi trả chi tiết.
3. Không phân biệt đối tượng không tồn tại với đối tượng ngoài quyền nếu chính sách yêu cầu che giấu sự tồn tại.
4. Chỉ trả version, trạng thái, người sửa hoặc dữ liệu khác biệt trong phạm vi được phép đọc.
5. Không trả toàn bộ dữ liệu hiện tại chỉ để tiện xử lý lỗi; có thể dùng API đọc có kiểm soát riêng.

Nếu quyền vừa bị thu hồi, một lần tra operation có thể bị từ chối dù thao tác trước đó đã thành công. Phản hồi từ chối truy cập không phải bằng chứng rằng thao tác cũ chưa commit. Giao diện không được suy ra `NOT_APPLIED` chỉ từ một lần tra cứu trả `403` hoặc `404`.

Request ID và operation ID phải được kiểm tra độ dài, hình thức và quyền sử dụng khi đi qua các hệ thống. Không phản chiếu tùy ý nội dung correlation header do client gửi vào log hoặc HTML.

## 8. Phân biệt xung đột cần xem lại với cạnh tranh có thể retry

### 8.1. Cần xem lại khi quyết định phụ thuộc snapshot

Ví dụ, người duyệt đã xem tổng tiền và tài liệu ở version 12. Sau đó dữ liệu thay đổi thành version 13. Thông báo nên yêu cầu xem lại; không có nút “Duyệt lại ngay” tự thay version mà không hiển thị nội dung mới.

Tương tự, việc lưu một biểu mẫu cũ có thể ghi đè nhiều trường đã được thay đổi. Frontend có thể giữ dữ liệu người dùng đã nhập, nhưng phải phân biệt rõ đó là bản cục bộ chưa được áp dụng.

Thông báo minh họa:

> Đơn hàng đã thay đổi. Quyết định duyệt lần này chưa được áp dụng. Hãy mở bản mới và kiểm tra lại trước khi duyệt.

Chỉ dùng câu này khi service đã xác nhận quyết định lần này không commit.

### 8.2. Retry cùng lệnh khi đó là hợp đồng an toàn

Một lỗi cạnh tranh tạm thời có thể được retry nếu lần thực thi trước đã rollback và hệ thống có giao thức bảo vệ hiệu ứng phù hợp.

Thông báo minh họa:

> Hệ thống đang xử lý nhiều thay đổi cùng lúc. Thao tác lần này chưa được áp dụng. Bạn có thể thử lại cùng yêu cầu.

“Cùng yêu cầu” nghĩa là giữ đúng ý định, payload và khóa idempotency theo hợp đồng. Server vẫn phải kiểm tra lại quyền, trạng thái và mọi bất biến. Nếu dữ liệu đã thay đổi, retry có thể chuyển thành lỗi cần xem lại.

Không biến `retryable=true` thành lời hứa rằng thao tác chắc chắn thành công sau khi gửi lại. Nên mô tả kiểu khôi phục rõ hơn như `RETRY_SAME_COMMAND`, `REVIEW_REQUIRED` hoặc `CHECK_OPERATION`.

### 8.3. Chờ khi cùng thao tác đang chạy

Nếu hệ thống có bản ghi operation đang xử lý, phản hồi có thể chỉ dẫn kiểm tra cùng operation sau một khoảng thời gian. Khoảng chờ là gợi ý tải hệ thống, không phải thời điểm chắc chắn hoàn tất.

Client cần giới hạn tần suất và thời gian theo dõi, có trạng thái chờ rõ ràng và không tạo khóa mới sau mỗi lần kiểm tra. Đóng trình duyệt không được mặc định hủy một nghiệp vụ mà máy chủ vẫn đang chạy.

## 9. Khi chưa biết kết quả: không dùng thông báo xung đột thay cho phục hồi

Xét lịch thực thi:

```text
Client gửi lệnh với idempotency key K.
Server thực hiện và commit transaction.
Kết nối mất trước khi client nhận phản hồi.
Client không biết lệnh đã thành công.
```

Ở phía client, timeout không chứng minh thao tác thất bại. Ở phía server, lỗi trả phản hồi cũng không làm transaction đã commit quay trở lại.

Thông báo phù hợp:

> Chưa xác nhận được kết quả yêu cầu. Hãy kiểm tra trạng thái trước khi tạo yêu cầu mới.

Giao thức phục hồi cần dựa vào kết quả bền vững, chẳng hạn:

- Kết quả idempotency được ghi cùng transaction với dữ liệu nghiệp vụ.
- Operation ID đã được thiết lập để phía gọi có thể tra cứu có xác thực.
- Retry cùng khóa được service đối chiếu fingerprint và trả lại kết quả đã lưu.

Một lần đọc chưa thấy kết quả chưa đủ để kết luận `NOT_APPLIED`: request có thể còn đang chạy, đọc có thể chưa quan sát được nguồn chuẩn hoặc kết quả chưa được quyết định. Hệ thống cần cơ chế xác lập trạng thái kết thúc, quyền thực thi và phục hồi trước khi cho một lần chạy mới tạo hiệu ứng.

Nếu operation đã commit, trả kết quả gốc thay vì chạy lại điều kiện version cũ rồi báo xung đột. Nếu dữ liệu về sau lại đổi, kết quả operation cũ vẫn mô tả lần thực thi đó; nó không có quyền đưa trạng thái hiện tại quay lùi.

## 10. Thiết kế một lớp ánh xạ thông báo an toàn

Luồng xử lý nên tách các trách nhiệm:

```text
Repository / transaction coordinator
    -> xác định cập nhật có khớp, transaction đã commit/rollback hay chưa
Service nghiệp vụ
    -> xác định nguyên nhân, phạm vi quyền và kiểu khôi phục hợp lệ
Lớp ánh xạ phản hồi
    -> tạo mã ổn định, câu chữ và HTTP status phù hợp
Client
    -> hiển thị và thực hiện hành động được hỗ trợ
```

Lớp thông báo không tự đoán kết quả chỉ từ tên exception. Ví dụ, exception optimistic locking đã được nhận diện vẫn cần được xử lý trong transaction đúng cách trước khi khẳng định không có phần nghiệp vụ nào được ghi.

Chỉ ánh xạ một vi phạm constraint thành mã nghiệp vụ khi đã nhận diện đúng constraint và ngữ cảnh. Không trả tên constraint nội bộ cho phía gọi.

### Ví dụ Java 17

Mã sau minh họa ánh xạ từ quyết định đã được service xác minh. `VerifiedDecision` là dữ liệu nội bộ, không được bind trực tiếp từ request hoặc tạo chỉ bằng cách nhìn tên exception. Các kiểm tra quyền và việc lọc dữ liệu công bố đã diễn ra trước bước ánh xạ.

```java
import java.util.Objects;

public final class ConflictMessageMapper {
    public enum Outcome {
        NOT_APPLIED, IN_PROGRESS, UNKNOWN
    }

    public enum Reason {
        STALE_VERSION,
        STATE_CHANGED,
        IDEMPOTENCY_KEY_REUSED,
        TEMPORARY_CONTENTION,
        UNCLASSIFIED
    }

    public enum Recovery {
        REVIEW_REQUIRED,
        WAIT_FOR_OPERATION,
        RETRY_SAME_COMMAND,
        CHECK_OPERATION,
        STOP
    }

    public record VerifiedDecision(
            Outcome outcome,
            Reason reason,
            String requestId,
            String operationId,
            Long expectedVersion) {}

    public record ClientMessage(
            int httpStatus,
            String code,
            String title,
            String detail,
            Outcome outcome,
            Recovery recovery,
            String requestId,
            String operationId,
            Long expectedVersion) {}

    public static ClientMessage map(VerifiedDecision decision) {
        Objects.requireNonNull(decision.outcome());
        Objects.requireNonNull(decision.reason());
        Objects.requireNonNull(decision.requestId());

        // Không tuyên bố thất bại chắc chắn khi kết quả còn chưa xác định.
        if (decision.outcome() == Outcome.UNKNOWN) {
            return message(decision, 503, "OPERATION_OUTCOME_UNKNOWN",
                    "Chưa xác nhận được kết quả",
                    "Hãy kiểm tra trạng thái trước khi tạo yêu cầu mới.",
                    Recovery.CHECK_OPERATION, null);
        }

        if (decision.outcome() == Outcome.IN_PROGRESS) {
            if (decision.operationId() == null) {
                throw new IllegalArgumentException("Operation ID is required");
            }
            return message(decision, 202, "OPERATION_IN_PROGRESS",
                    "Yêu cầu đang được xử lý",
                    "Hãy theo dõi yêu cầu hiện tại trước khi gửi yêu cầu mới.",
                    Recovery.WAIT_FOR_OPERATION, null);
        }

        // Các nhánh còn lại chỉ chạy khi NOT_APPLIED đã được xác nhận.
        return switch (decision.reason()) {
            case STALE_VERSION -> message(decision, 409,
                    "STALE_ORDER_VERSION", "Dữ liệu đã thay đổi",
                    "Thay đổi lần này chưa được áp dụng. Hãy tải lại để xem trước khi lưu.",
                    Recovery.REVIEW_REQUIRED, decision.expectedVersion());
            case STATE_CHANGED -> message(decision, 409,
                    "ORDER_STATE_CHANGED", "Trạng thái đã thay đổi",
                    "Thao tác lần này chưa được áp dụng. Hãy kiểm tra trạng thái mới.",
                    Recovery.REVIEW_REQUIRED, null);
            case IDEMPOTENCY_KEY_REUSED -> message(decision, 409,
                    "IDEMPOTENCY_KEY_REUSED", "Khóa yêu cầu đã được sử dụng",
                    "Khóa này đã gắn với nội dung khác. Nội dung gửi lần này chưa được áp dụng.",
                    Recovery.STOP, null);
            case TEMPORARY_CONTENTION -> message(decision, 503,
                    "TEMPORARY_CONTENTION", "Chưa thể hoàn tất lúc này",
                    "Thao tác lần này chưa được áp dụng. Có thể thử lại cùng yêu cầu theo hướng dẫn.",
                    Recovery.RETRY_SAME_COMMAND, null);
            case UNCLASSIFIED -> message(decision, 500,
                    "INTERNAL_ERROR", "Không thể hoàn tất yêu cầu",
                    "Hãy giữ mã tham chiếu để kiểm tra hoặc nhận hỗ trợ.",
                    Recovery.STOP, null);
        };
    }

    private static ClientMessage message(
            VerifiedDecision decision,
            int status,
            String code,
            String title,
            String detail,
            Recovery recovery,
            Long expectedVersion) {
        return new ClientMessage(status, code, title, detail,
                decision.outcome(), recovery, decision.requestId(),
                decision.operationId(), expectedVersion);
    }
}
```

Giới hạn và điều kiện áp dụng của ví dụ:

- Đây là mapper minh họa cho API dùng version trong body. Nếu dùng điều kiện HTTP như `If-Match`, nhánh tương ứng cần ánh xạ theo hợp đồng đó.
- `COMMITTED` được xử lý ở luồng thành công hoặc replay idempotency, không đưa vào mapper lỗi này.
- Phản hồi `202` là biểu diễn trạng thái xử lý bình thường, không tự động dùng cùng media type lỗi với phản hồi `409`.
- `RETRY_SAME_COMMAND` chỉ được phát khi service thực sự hỗ trợ giao thức retry an toàn; không suy ra điều đó chỉ từ lỗi lock timeout.
- Operation ID và request ID phải là định danh đã được kiểm tra để công bố. Trường `expectedVersion` không thay thế version thực ở database.
- Mapper không chứa logic commit, rollback, truy vấn quyền hoặc tìm trạng thái hiện tại. Những phần đó cần nguồn sự thật riêng.

## 11. Giữ dữ liệu người dùng mà không ghi đè thay đổi mới

Khi xung đột xuất hiện trên biểu mẫu, giao diện có thể giữ ba phần để đối chiếu:

```text
Bản gốc mà người dùng đã xem
Phần thay đổi cục bộ chưa được áp dụng
Bản hiện tại được tải lại có kiểm soát quyền
```

Chỉ hiển thị hoặc gộp dữ liệu mà người dùng còn quyền truy cập. Nếu quyền đã mất, không cố tải và hiển thị bản hiện tại để phục vụ tiện ích gộp.

Không tự gộp các trường có ý nghĩa nghiệp vụ chỉ vì tên trường khác nhau. Ví dụ, người này sửa số lượng còn người khác sửa chiết khấu; hai thay đổi tác động cùng tổng tiền và có thể cần xác nhận lại.

Đối với tài liệu phê duyệt, giá, hạn mức hoặc trạng thái, ưu tiên yêu cầu xem lại nội dung kết quả. Nếu hỗ trợ gộp tự động cho một số trường an toàn, phải có quy tắc rõ ràng, kiểm tra bất biến phía máy chủ và điều kiện version cho lần ghi mới.

Các nút cần diễn đạt đúng hành động. “Tải lại” không được đồng thời tự lưu bản cục bộ. “Gửi lại” không được âm thầm thay khóa idempotency. “Giữ bản nháp” không được hiển thị như một lần lưu thành công trên máy chủ.

## 12. Tránh bão retry và hiệu ứng trùng

Một thông báo có hành động retry còn tạo ra tải hệ thống. Nếu mọi client gửi lại ngay khi gặp tranh chấp, chúng có thể liên tục xung đột và làm thời gian chờ tăng.

Hợp đồng retry nên quy định:

- Giới hạn số lần hoặc thời gian retry.
- Khoảng chờ tăng dần và độ lệch ngẫu nhiên khi phù hợp.
- Giữ khóa idempotency và fingerprint của cùng ý định.
- Kiểm tra lại quyền, trạng thái và điều kiện version khi thực thi.
- Dừng retry khi gặp mã cần xem lại hoặc bị từ chối quyền.
- Tra kết quả thay vì tạo lệnh mới khi outcome chưa xác định.

Nếu server trả gợi ý thời gian chờ hoặc header `Retry-After` theo hợp đồng, frontend nên tôn trọng nó. Gợi ý đó không phải cam kết dữ liệu vẫn giữ nguyên sau khoảng chờ.

Một response bị mất vẫn có thể dẫn tới retry, nên việc “lần trước chắc chắn rollback” không thay thế hoàn toàn idempotency của giao thức. Cần nghĩ tới cả lần gọi kế tiếp có thể commit rồi mất phản hồi.

Thông báo, email, event và callback phát sinh từ lệnh cũng cần thiết kế chống trùng. Version checking chỉ bảo vệ điều kiện thay đổi dữ liệu; nó không tự chống việc gửi thông báo hai lần sau retry hoặc xử lý message lại.

## 13. Quan sát hệ thống và audit

Có thể theo dõi số lượng theo mã lỗi, loại thao tác và kết quả đã xác nhận, chẳng hạn:

| Chỉ số | Câu hỏi hỗ trợ chẩn đoán |
|---|---|
| Tần suất `STALE_ORDER_VERSION` | Người dùng làm việc trên snapshot quá cũ hay aggregate đang tranh chấp mạnh? |
| Tần suất `IDEMPOTENCY_KEY_REUSED` | Client có đang dùng một khóa cho nhiều ý định khác nhau? |
| Thời gian `IN_PROGRESS` | Worker có bị chậm hoặc operation mắc kẹt? |
| Số lượng `UNKNOWN` và thời gian phục hồi | Có vấn đề ở commit, mạng hoặc lưu kết quả idempotency? |
| Tỷ lệ retry kết thúc thành công hoặc yêu cầu xem lại | Chính sách retry có phù hợp với nghiệp vụ? |

Tránh dùng order ID, user ID hoặc request ID làm nhãn metric không giới hạn vì chúng tạo số lượng nhãn quá lớn. Các định danh chi tiết phù hợp hơn với log hoặc trace có kiểm soát truy cập.

Log nội bộ nên phân biệt nguyên nhân kỹ thuật với mã đã công bố. Có thể lưu constraint được nhận diện, version kỳ vọng, trạng thái transaction và correlation ID trong phạm vi cho phép, nhưng không đưa dữ liệu đó thẳng ra response.

Audit thành công cần nhất quán với hiệu ứng nghiệp vụ. Một lần xung đột đã rollback có thể được ghi nhận là lần thử thất bại ở kênh riêng, không được để lại quyết định phê duyệt hoặc bản ghi thành công giả.

Không coi mọi xung đột là hành vi tấn công. Tuy nhiên, một client liên tục thay version, khóa idempotency hoặc đối tượng đích để né lỗi cần được xem xét theo quy tắc giám sát lạm dụng của hệ thống.

## 14. Ma trận kiểm thử thông báo và hiệu ứng nghiệp vụ

Kiểm thử cần xác nhận response phản ánh đúng trạng thái thực, không chỉ có câu tiếng Việt mong muốn.

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Hai lệnh sửa cùng version, một lệnh thắng | Lệnh thua không ghi đè; thông báo yêu cầu xem lại và chỉ nói chưa áp dụng khi đã xác nhận |
| Trạng thái đổi sang không cho sửa trước khi ghi | Không phát thông báo retry mù; hướng dẫn thao tác phù hợp trạng thái |
| Update count bằng 0 vì sai tenant | Không trả current version hoặc nội dung của tài nguyên ngoài quyền |
| Lỗi SQL chưa được nhận diện | Không tự ánh xạ thành xung đột nghiệp vụ cụ thể |
| Có lỗi sau cập nhật đầu tiên nhưng trước commit | Rollback toàn bộ; response không giấu một thay đổi còn sót |
| Mất kết nối trong lúc commit | Không khẳng định chưa lưu nếu không có bằng chứng |
| Thao tác commit nhưng mất response | Retry cùng khóa trả kết quả đã lưu, không báo stale version của lần mới |
| Tra operation chưa thấy bản ghi kết thúc | Không tự kết luận thất bại nếu thao tác còn có thể đang chạy |
| Cùng khóa nhưng đổi payload hoặc expected version | Báo xung đột fingerprint; không tự tạo khóa mới và thực thi |
| Cùng thao tác đang chạy | Có đường theo dõi thực sự, không tạo hiệu ứng song song |
| Quyền bị thu hồi trước khi tra kết quả | Không lộ dữ liệu; lỗi truy cập không bị diễn giải thành thất bại của thao tác cũ |
| Thông báo được dịch sang ngôn ngữ khác | Client vẫn xử lý theo mã ổn định, không theo chuỗi |
| Người dùng chọn tải lại | Không tự ghi bản cục bộ lên version mới |
| Người dùng giữ bản nháp | Không hiển thị rằng dữ liệu đã lưu trên máy chủ |
| Retry gặp xung đột cần xem lại | Dừng vòng retry và chuyển đúng luồng phục hồi |
| Dữ liệu thay đổi tiếp sau response xung đột | Không coi version trả về là quyền ghi chắc chắn cho lần sau |
| Nhiều client cùng nhận lỗi tạm thời | Có giới hạn và khoảng chờ retry, không tạo vòng lặp vô hạn |
| Payload lỗi chứa dữ liệu nhạy cảm | Không phản chiếu stack trace, token, thông tin tenant khác hoặc URL có chữ ký |

Đối với kiểm thử đồng thời, dùng hai transaction độc lập và điểm đồng bộ sau khi đọc snapshot để tạo lịch cạnh tranh thực sự. Không chỉ gọi hai lần nối tiếp rồi kết luận hệ thống đã kiểm thử xung đột.

Đối với kết quả chưa xác định, cần mô phỏng mất phản hồi sau commit hoặc sự cố ở ranh giới commit, rồi kiểm tra đường khôi phục idempotency. Một mock trả exception trước khi chạm database không thể đại diện cho tình huống đã commit nhưng client chưa biết.

## 15. Những thông báo cần tránh

| Thông báo hoặc hành vi | Vấn đề | Cách diễn đạt hoặc xử lý phù hợp |
|---|---|---|
| “Có lỗi, thử lại” cho mọi trường hợp | Không cho biết hiệu ứng và hành động an toàn | Phân loại outcome và kiểu khôi phục |
| “Chưa lưu” sau một timeout gần commit | Có thể sai sự thật, dẫn tới lệnh trùng | Thông báo chưa xác nhận và tra kết quả |
| “Hãy bấm lại để duyệt bản mới” | Có thể chấp thuận nội dung chưa xem | Tải lại và xem lại trước khi duyệt |
| “Tạo request ID mới rồi thử lại” cho kết quả chưa rõ | Có thể né idempotency và nhân đôi hiệu ứng | Giữ định danh ý định hoặc dùng đường tra kết quả |
| Trả toàn bộ bản hiện tại trong lỗi | Có thể lộ dữ liệu hoặc vượt quyền trường | Chỉ công bố dữ liệu được phép, dùng API đọc có kiểm soát |
| Tự thay expected version rồi gửi lại | Vô hiệu hóa kiểm tra snapshot | Yêu cầu xem lại hoặc gộp theo quy tắc tường minh |
| “Đang xử lý” khi chỉ không biết kết quả | Tạo kỳ vọng sai và có thể chờ vô hạn | Dùng `UNKNOWN` cùng cơ chế xác minh |
| Phân tích câu detail để quyết định retry | Dễ hỏng khi đổi câu chữ hoặc dịch | Dùng code, outcome và recovery có hợp đồng |
| Trả tên constraint hoặc stack trace | Lộ cấu trúc nội bộ, thông báo khó hiểu | Mã nghiệp vụ ổn định và request ID hỗ trợ |

## 16. Thiết kế thông báo cho một thao tác mới

Trước khi công bố một thông báo xung đột, cần trả lời:

1. Lệnh đang xét là ý định nào, và định danh nào nối các lần retry của cùng ý định?
2. Service có bằng chứng gì về trạng thái `NOT_APPLIED`, `COMMITTED`, `IN_PROGRESS` hoặc `UNKNOWN`?
3. Nguyên nhân nào đã được xác định, và thông tin nào chủ thể được phép biết?
4. Phía gọi cần xem lại, chờ, retry cùng lệnh hay tra kết quả?
5. Thông báo có vô tình khiến frontend thay version, tạo khóa mới hoặc phê duyệt nội dung chưa xem không?
6. Hiệu ứng dữ liệu, audit, outbox và kết quả idempotency có nhất quán với điều response tuyên bố không?
7. Kiểm thử nào chứng minh thông báo vẫn đúng khi transaction cạnh tranh hoặc phản hồi bị mất?

Một thông báo xung đột tốt giúp người dùng và client đưa ra bước tiếp theo dựa trên kết quả đã được xác nhận. Nó giữ nguyên ranh giới quyền, điều kiện phiên bản và ý định nghiệp vụ trong quá trình khôi phục, thay vì biến thao tác “thử lại” thành đường bỏ qua các kiểm soát đó.
