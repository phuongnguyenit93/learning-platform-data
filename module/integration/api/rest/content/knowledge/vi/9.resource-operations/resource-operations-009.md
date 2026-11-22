# Thao tác hàng loạt và kết quả từng phần

## 1. Mục tiêu bài học và bối cảnh

Trong module **INTEGRATION_API_REST**, thiết kế REST API bắt đầu từ resource và URI, dùng đúng phương thức, mã trạng thái HTTP và hợp đồng dữ liệu rõ ràng. Chương **Thao tác tài nguyên** này giải quyết bài toán khi client muốn thực hiện **một thao tác trên nhiều tài nguyên** trong một lần gửi và cần biết **phần tử nào thành công, phần tử nào thất bại**.

Ví dụ: người quản trị chọn 30 tài liệu để xóa; 24 tài liệu được xóa thành công, 3 tài liệu bị khóa, 2 tài liệu đã đổi phiên bản và 1 tài liệu không thuộc phạm vi truy cập. Một phản hồi chung “thành công” hoặc “thất bại” sẽ không giúp giao diện xác định chính xác bước tiếp theo.

Học xong, bạn có thể:

- Phân biệt **bulk request** với hành động một resource và phân biệt **kết quả từng phần** với lỗi toàn request.
- Chọn mô hình **all-or-nothing** hoặc **best-effort** theo nghiệp vụ, khả năng giao dịch và ràng buộc hệ thống.
- Thiết kế endpoint, body, trạng thái HTTP và schema kết quả theo từng item một cách dự đoán được.
- Giải thích vì sao **200 OK**, **202 Accepted** hoặc **207 Multi-Status** có thể xuất hiện trong các API bulk khác nhau; không nhầm **206 Partial Content** với batch partial success.
- Thiết kế **idempotency**, **retry** và xử lý đồng thời để tránh tạo trùng/xóa nhầm.
- Bảo vệ quyền truy cập theo từng tài nguyên, giới hạn số lượng, quan sát hiệu năng và kiểm soát lỗi.
- Viết ví dụ hợp đồng **OpenAPI** và triển khai minh họa bằng **Java/Spring** hoặc framework tương đương.

**Đầu ra thực hành:** một hợp đồng API thao tác hàng loạt có request schema, response schema, ví dụ đầy đủ, quy tắc retry, ma trận lỗi và bộ kiểm thử.

## 2. Vì sao không đơn giản gọi một endpoint nhiều lần?

Client luôn có thể gửi nhiều request đơn lẻ:

~~~http
DELETE /api/v1/documents/d-101
DELETE /api/v1/documents/d-102
DELETE /api/v1/documents/d-103
~~~

Cách đó dễ hiểu và phù hợp khi số lượng nhỏ hoặc client cần kiểm soát độc lập từng thao tác. Tuy nhiên, có thể phát sinh nhiều round-trip, khó điều tiết tải, khó theo dõi tiến độ và khó đưa ra báo cáo tập trung khi người dùng chọn hàng trăm mục.

Một **bulk operation** nhận danh sách mục tiêu hoặc một truy vấn được kiểm soát, rồi xử lý theo hợp đồng thống nhất. Đổi lại, server phải làm rõ nhiều vấn đề mà thao tác đơn lẻ không gặp:

- Nếu 1 mục lỗi và 99 mục thành công thì HTTP status là gì?
- Nếu request có ID trùng lặp, server có xử lý hai lần không?
- Nếu một phần đã commit rồi client timeout, lần gửi lại ảnh hưởng ra sao?
- Nếu user được xóa 99 mục nhưng không được xóa mục thứ 100, có lộ thông tin không?
- Khi nào dùng giao dịch DB chung, khi nào tách theo từng item?
- Nếu job chạy nhiều phút, client kiểm tra tiến độ, lỗi và kết quả như thế nào?
- Có cần giữ thứ tự kết quả như thứ tự request không?

Bulk API là **một hợp đồng nghiệp vụ có nhiều kết quả**, chứ không chỉ là vòng lặp for trên controller.

## 3. Định nghĩa thành công từng phần và ba mức kết quả

Một thao tác hàng loạt có thể được đánh giá tại ba lớp khác nhau:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Request** | HTTP request hợp lệ và được API tiếp nhận/xử lý chưa? | JSON đúng schema, token hợp lệ, vượt hạn mức hay không |
| **Operation** | Toàn bộ batch ở trạng thái gì? | Accepted, running, completed, completed_with_errors, failed |
| **Item** | Một mục tiêu cụ thể đã đạt kết quả gì? | Deleted, forbidden, not_found, version_conflict |

**Partial success** nghĩa là có ít nhất một item hoàn thành theo mục tiêu và ít nhất một item không hoàn thành theo mục tiêu, trong một operation đã có kết quả đủ để đánh giá. Chỉ vì HTTP response có 200 chưa thể suy ra tất cả các item đều thành công.

Ví dụ tổng hợp:

| documentId | Kết quả item | Status tham chiếu | Thao tác tiếp theo |
| --- | --- | --- | --- |
| d-101 | Xóa thành công | 204 | Cập nhật UI |
| d-102 | Tài liệu bị khóa | 409 | Yêu cầu mở khóa hoặc thông báo |
| d-103 | ETag đã thay đổi | 412 | GET lại rồi quyết định |
| d-104 | Không tìm thấy/không được phép thấy | 404 | Không suy ra tài nguyên tồn tại |
| d-105 | Xóa thành công | 204 | Cập nhật UI |

Trong một response JSON, **status của item** là dữ liệu hợp đồng do ứng dụng định nghĩa, thường dùng mã HTTP quen thuộc để người đọc dễ hiểu. Nó không phải năm HTTP response độc lập được truyền trong một TCP/HTTP response.

## 4. Chọn ngữ nghĩa thực hiện: all-or-nothing hay best-effort?

### 4.1. All-or-nothing

**All-or-nothing** yêu cầu mọi mục được xử lý thành công hoặc không mục nào thay đổi. Phù hợp khi mục tiêu nghiệp vụ có tính toàn vẹn chung, ví dụ chuyển giao một nhóm bản ghi phải nhất quán.

Ví dụ: yêu cầu xóa ba thành phần thuộc một cấu hình mà nếu thiếu một thành phần sẽ làm hệ thống không hợp lệ.

Để thật sự bảo đảm tính nguyên tử, thao tác thường phải nằm trong **cùng giao dịch có khả năng rollback** của một hệ quản trị dữ liệu. Khi trải qua nhiều database hoặc dịch vụ bên ngoài, không thể đơn giản đặt annotation giao dịch ở controller rồi tuyên bố all-or-nothing.

~~~mermaid
flowchart TD
    A[Nhận batch] --> B[Kiểm tra toàn batch]
    B --> C{Dữ liệu, quyền và trạng thái hợp lệ?}
    C -- Không --> D[Từ chối, không thay đổi item]
    C -- Có --> E[Thực hiện trong giao dịch chung]
    E --> F{Commit thành công?}
    F -- Có --> G[Thành công toàn batch]
    F -- Không --> H[Rollback, báo lỗi toàn batch]
~~~

Ưu điểm: client không cần xử lý trạng thái nửa chừng nếu bảo đảm nguyên tử thực sự được thực hiện. Đổi lại, giao dịch dài có thể giữ lock, tăng xung đột và giảm throughput. Cần giới hạn batch, thời gian giao dịch và kiểm thử race.

### 4.2. Best-effort / per-item outcome

**Best-effort** cố gắng xử lý từng item độc lập, ghi nhận kết quả của từng item và không rollback những item đã thành công chỉ vì một item khác thất bại.

~~~mermaid
flowchart TD
    A[Nhận batch hợp lệ] --> B[Duyệt từng item]
    B --> C[Kiểm tra quyền và điều kiện item]
    C --> D{Có thể thực hiện?}
    D -- Có --> E[Thực hiện và commit item]
    D -- Không --> F[Ghi lỗi item]
    E --> G[Cập nhật item result]
    F --> G
    G --> H{Còn item?}
    H -- Có --> B
    H -- Không --> I[Tổng hợp kết quả và trả response]
~~~

Ưu điểm: xử lý được các mục không liên quan, giảm tác động khi một mục lỗi. Đổi lại, client phải nhận và hiển thị kết quả chi tiết, đồng thời xử lý retry một cách có chủ đích.

**Chốt hợp đồng trước khi triển khai:** chế độ atomic hay best-effort phải là quyết định rõ. Không để server đôi khi rollback tất cả, đôi khi commit một phần mà không có quy tắc công bố.

### 4.3. Bảng lựa chọn

| Yếu tố | All-or-nothing | Best-effort |
| --- | --- | --- |
| Item độc lập | Ít phù hợp nếu không cần nguyên tử | Thường phù hợp |
| Nhiều resource chung một DB | Có thể dùng transaction | Có thể tách transaction |
| Nhiều hệ thống bên ngoài | Khó bảo đảm nguyên tử; cần saga/compensation | Dễ mô tả partial outcomes hơn |
| Một item bị khóa | Toàn batch không được thực thi | Các item khác vẫn có thể thành công |
| Thời gian xử lý dài | Có nguy cơ giữ lock lâu | Có thể tách job và kiểm soát concurrency |
| Client | Xử lý trạng thái toàn batch | Cần theo dõi kết quả từng item |

## 5. Thiết kế resource và URI cho thao tác hàng loạt

Có vài lựa chọn có thể bảo vệ được về mặt thiết kế; API cần nhất quán với ý nghĩa resource.

### 5.1. Nhiều request trên URI đơn lẻ

~~~http
DELETE /api/v1/documents/d-101
DELETE /api/v1/documents/d-102
~~~

Lựa chọn này phù hợp cho số lượng nhỏ. Mỗi DELETE có ngữ nghĩa HTTP rõ, có thể dùng If-Match và mã phản hồi riêng; client chịu trách nhiệm tổng hợp.

### 5.2. POST tới resource batch operation

~~~http
POST /api/v1/document-batch-deletions HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>
Idempotency-Key: bulk-req-001

{
  "mode": "best_effort",
  "items": [
    {"documentId": "d-101", "ifMatch": "\"v7\""},
    {"documentId": "d-102", "ifMatch": "\"v4\""}
  ]
}
~~~

Đây là ví dụ mô hình hóa một **tác vụ xóa nhiều tài liệu**. POST phù hợp khi cần body có danh sách item, điều kiện độc lập và trạng thái tổng hợp. Nó không có tính idempotent mặc định theo HTTP; nếu cần retry an toàn phải thiết kế dedup/idempotency ở tầng ứng dụng.

### 5.3. PATCH trên collection hoặc endpoint operations?

PATCH có thể phù hợp nếu body mô tả rõ cách sửa trạng thái một tập resource theo một patch format được định nghĩa và server hỗ trợ. Tuy nhiên, một danh sách các lệnh hỗn hợp “xóa tài liệu A, duyệt tài liệu B, đổi owner tài liệu C” có thể rõ hơn khi mô hình hóa một **batch command/job resource**.

Tránh endpoint mơ hồ như **POST /bulk** mà không cho biết loại resource, loại tác động, quyền và ngữ nghĩa hoàn thành. Dùng tên resource hoặc operation đủ rõ để tài liệu API và chính sách bảo mật có thể đọc độc lập.

### 5.4. Xóa collection bằng DELETE có body

HTTP không định nghĩa ngữ nghĩa chung cho request content trong DELETE. Không nên tự giả định rằng mọi proxy, client hay framework sẽ hỗ trợ một hợp đồng batch như:

~~~http
DELETE /api/v1/documents HTTP/1.1
Content-Type: application/json

{"ids":["d-101","d-102"]}
~~~

Với yêu cầu xóa theo danh sách có nhiều điều kiện, POST tạo resource operation/job thường dễ triển khai và mô tả hơn.

## 6. Mã trạng thái HTTP cho bulk: 200, 202, 207

### 6.1. 200 OK – xử lý request và trả bảng kết quả

Đối với một **bulk operation đồng bộ** theo best-effort, cách phổ biến là trả **200 OK** với body mô tả từng item. 200 thể hiện request đã được xử lý theo hợp đồng của endpoint; **không khẳng định mọi item thành công**.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "operationId": "op-901",
  "state": "completed_with_errors",
  "summary": {
    "total": 3,
    "succeeded": 2,
    "failed": 1
  },
  "results": [
    {"documentId":"d-101","status":204,"outcome":"succeeded"},
    {"documentId":"d-102","status":409,"outcome":"failed",
     "error":{"code":"DOCUMENT_LOCKED","message":"Document is locked"}},
    {"documentId":"d-103","status":204,"outcome":"succeeded"}
  ]
}
~~~

Một API có thể dùng 200 ngay cả khi **tất cả item đều thất bại theo quy tắc nghiệp vụ**, miễn request đã được xử lý hợp lệ và response mô tả đúng kết quả. Tuy nhiên, lựa chọn này phải công bố rõ để client không đánh giá thành công chỉ bằng status ngoài cùng.

### 6.2. 202 Accepted – đã tiếp nhận để xử lý bất đồng bộ

Nếu batch lớn hoặc công việc xử lý lâu, một API có thể nhận job và trả **202 Accepted**:

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/operations/op-902
Retry-After: 3
Content-Type: application/json

{
  "operationId": "op-902",
  "state": "queued"
}
~~~

202 **không bảo đảm job sẽ thành công**. Client dùng operation resource để theo dõi đến trạng thái cuối cùng. Nếu endpoint thực sự tạo một job resource và muốn tuân thủ ngữ nghĩa resource creation, **201 Created** cũng có thể phù hợp, tùy hợp đồng; 202 nhấn mạnh xử lý chưa hoàn tất.

### 6.3. 207 Multi-Status – mã mở rộng từ WebDAV

**207 Multi-Status** được định nghĩa trong WebDAV (RFC 4918) để truyền trạng thái của nhiều resource trong một phản hồi. Một API có thể **cố ý áp dụng** ý tưởng đa trạng thái này, nhưng phải tài liệu hóa rõ định dạng body, cách diễn giải, khả năng tương thích client và các mã item.

Không giả định rằng 207 tự động có một JSON schema chuẩn cho mọi REST API. Trong WebDAV, 207 thường dùng body XML theo cấu trúc Multi-Status; nếu một API riêng sử dụng JSON thì đó là **hợp đồng cụ thể của API**, không phải JSON mặc định được RFC 4918 áp đặt.

| Phản hồi ngoài cùng | Ý nghĩa phù hợp | Cảnh báo |
| --- | --- | --- |
| **200** | Bulk đồng bộ đã được xử lý và body chứa kết quả | Phải xem từng item |
| **202** | Chấp nhận công việc, chưa có kết quả cuối | Phải theo dõi operation/job |
| **201** | Một resource job đã được tạo | Tạo job không đồng nghĩa mọi thao tác hoàn thành |
| **207** | Hợp đồng kiểu multi-status, từng mục có trạng thái riêng | WebDAV-defined, cần chốt format và tương thích |

**206 Partial Content không biểu diễn “một nửa batch thành công”.** 206 dùng cho đáp ứng truy vấn dải byte/range của biểu diễn tài nguyên theo HTTP. Tránh sử dụng 206 cho bulk partial success.

**204 No Content** không phù hợp nếu hợp đồng cần trả danh sách kết quả, vì response 204 không có response content. Với batch có item lỗi, mất danh sách chi tiết sẽ khiến client khó xử lý.

## 7. Phân biệt lỗi request với lỗi item

Đây là điểm quyết định khả năng hiểu của API:

| Tình huống | Phạm vi lỗi | Mã ngoài cùng gợi ý |
| --- | --- | --- |
| JSON không parse được | Request | 400 Bad Request |
| Không có token hợp lệ | Request | 401 Unauthorized |
| Caller không có quyền dùng tính năng bulk | Request | 403 Forbidden |
| Danh sách rỗng hoặc vượt giới hạn đã công bố | Request | 400 hoặc 422 theo quy ước API |
| Toàn dịch vụ tạm không nhận xử lý | Request | 503 Service Unavailable |
| Một tài liệu bị khóa, các tài liệu khác hợp lệ | Item | 200 + item status 409 |
| Một tài liệu khác phiên bản | Item | 200 + item status 412 |
| Một tài liệu không tìm thấy/không được phép thấy | Item | 200 + item status 404 |
| Job đã tiếp nhận, chưa xử lý | Operation chưa hoàn tất | 202 |

Nếu server **không thể** thực thi hợp đồng batch ở cấp request, trả lỗi cấp request phù hợp. Nếu đã chấp nhận xử lý từng item và gặp lỗi cá biệt, trả chi tiết theo item.

Đừng “bắt mọi Exception rồi trả 200 với toàn bộ item failed” nếu lỗi thực chất là sự cố nền tảng ảnh hưởng cả request. Cần phân biệt lỗi nghiệp vụ dự đoán được với tình huống hệ thống không bảo đảm kết quả hay không thể ghi nhận trạng thái.

## 8. Thiết kế request schema có thể kiểm chứng

Một request bulk nên có:

- **Định danh từng item:** documentId hoặc resource URI; đủ để đối chiếu response.
- **Điều kiện theo item:** phiên bản/ETag, trạng thái mong đợi hoặc tham số nghiệp vụ cần thiết.
- **Chế độ xử lý:** nếu hệ thống hỗ trợ nhiều mode, phải đặt rõ; nếu chỉ hỗ trợ một mode, đừng thêm tùy chọn vô nghĩa.
- **Giới hạn:** tối đa số item, kích thước request, số lượng ID được phép trùng hoặc không.
- **Phạm vi người gọi:** tenant/organization lấy từ authentication context, không tin giá trị client tự nhập.
- **Dấu nhận dạng retry:** ví dụ Idempotency-Key có scope và TTL được công bố.

Ví dụ hợp đồng yêu cầu danh sách **tối đa 100 item**, không nhận ID trùng, thao tác xóa theo best-effort:

~~~json
{
  "mode": "best_effort",
  "items": [
    {
      "documentId": "d-101",
      "ifMatch": "\"v7\""
    },
    {
      "documentId": "d-102",
      "ifMatch": "\"v4\""
    }
  ]
}
~~~

**Vấn đề ID trùng:** nếu danh sách chứa d-101 hai lần, nên chọn một chính sách rõ, ví dụ từ chối toàn request bằng 400 với thông báo duplicate, hoặc gộp theo ID và trả mapping vị trí ban đầu. Mẫu bài học này **từ chối ID trùng trước khi xử lý** để tránh làm rối số liệu và side effect.

**Vấn đề thứ tự:** có thể bảo đảm results giữ đúng thứ tự request, hoặc dùng **clientItemId** duy nhất để đối chiếu nếu server xử lý song song. Trong mọi trường hợp, client không nên phải đoán kết quả thuộc item nào.

## 9. Thiết kế response schema cho kết quả từng phần

Một response có ích phải giải thích được **đã thử xử lý item nào, item nào không được thử, kết quả và khả năng retry**.

~~~json
{
  "operationId": "op-901",
  "state": "completed_with_errors",
  "summary": {
    "total": 4,
    "succeeded": 2,
    "failed": 2,
    "skipped": 0
  },
  "results": [
    {
      "clientItemId": "row-1",
      "documentId": "d-101",
      "status": 204,
      "outcome": "succeeded"
    },
    {
      "clientItemId": "row-2",
      "documentId": "d-102",
      "status": 409,
      "outcome": "failed",
      "error": {
        "code": "DOCUMENT_LOCKED",
        "message": "Tài liệu đang bị khóa.",
        "retryable": false
      }
    },
    {
      "clientItemId": "row-3",
      "documentId": "d-103",
      "status": 204,
      "outcome": "succeeded"
    },
    {
      "clientItemId": "row-4",
      "documentId": "d-104",
      "status": 412,
      "outcome": "failed",
      "error": {
        "code": "ETAG_MISMATCH",
        "message": "Tài liệu đã thay đổi.",
        "retryable": false
      }
    }
  ]
}
~~~

### 9.1. Những trường cần định nghĩa

| Trường | Ý nghĩa và quy tắc |
| --- | --- |
| operationId | ID truy vết một lần thực hiện logic, hữu ích cho audit/support |
| state | running, completed, completed_with_errors, failed ... theo enum đã công bố |
| summary.total | Số item được chấp nhận trong batch sau validation |
| succeeded / failed / skipped | Tổng item theo outcome, không đếm request HTTP |
| results[].clientItemId | Đối chiếu item với dòng trên UI hoặc dữ liệu gốc |
| results[].status | Mã kết quả tham chiếu HTTP của item, do schema ứng dụng định nghĩa |
| results[].outcome | succeeded, failed, skipped hoặc pending theo trạng thái |
| results[].error.code | Mã lỗi ứng dụng ổn định để xử lý tự động |
| results[].error.message | Thông điệp an toàn cho người dùng/nhóm hỗ trợ |
| results[].error.retryable | Gợi ý cho client; cần công bố điều kiện retry thực tế |

Nếu tài nguyên đã bị xóa từ trước, API phải quy định liệu kết quả item là 404 hay “đã đạt trạng thái đích”, tương tự idempotency của DELETE đơn lẻ.

**Bất biến kiểm chứng:** với response cuối đủ chi tiết, **total = succeeded + failed + skipped** và mỗi item có chính xác một kết quả cuối. Nếu vẫn có pending, dùng state và thống kê nhất quán (ví dụ thêm pending) thay vì cộng sai.

### 9.2. Những điều không nên đưa vào lỗi item

Không trả stack trace, SQL, nội dung tài liệu nhạy cảm, token hoặc thông tin xác nhận sự tồn tại của tài liệu thuộc tenant khác. Có thể dùng 404 ở mức item để che giấu sự tồn tại theo chính sách bảo mật.

## 10. Idempotency và retry khi chỉ vài item thất bại

Với bulk operation được tạo qua POST, **HTTP không bảo đảm tính idempotent của POST**. Nếu client timeout sau khi một phần đã commit, gửi lại batch như một operation mới có thể gây tác dụng lặp.

Hai lớp xử lý bổ sung cho nhau:

1. **Request-level idempotency:** client gửi Idempotency-Key ổn định cho cùng một ý định. Server lưu trạng thái key và fingerprint của request, trong phạm vi caller/tenant/endpoint, rồi trả lại kết quả hoặc trạng thái job tương ứng khi retry.
2. **Item-level idempotency:** từng thao tác nghiệp vụ phải an toàn khi worker retry. Ví dụ xóa cùng document/generation không được xóa nhầm tài liệu mới, và tạo hóa đơn phải có unique key bảo vệ trùng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Bulk API
    participant DB as Operation store
    C->>A: POST batch + Idempotency-Key K
    A->>DB: Ghi K, fingerprint, trạng thái
    A->>DB: Xử lý một số item
    A--xC: Phản hồi bị mất
    C->>A: Retry cùng payload + K
    A->>DB: Tìm K và đối chiếu fingerprint
    DB-->>A: Operation đang có
    A-->>C: Trả operation/result hiện có
~~~

Các quy tắc cần thiết:

- **Cùng key, cùng payload và scope:** trả kết quả trước đó hoặc cùng operation đang chạy; không tạo batch thứ hai.
- **Cùng key, payload khác:** từ chối theo lỗi hợp đồng, thường là **409 Conflict** hoặc lỗi tương đương đã công bố; không âm thầm coi là request mới.
- **Khác key:** là một ý định mới, cần xét tính idempotent của từng item.
- **TTL của key:** phải công bố rõ thời gian còn bảo đảm dedup; không hứa retry vô hạn nếu state đã hết hạn.
- **Concurrency:** hai request với cùng key đến cùng lúc cần cơ chế ghi nhận nguyên tử; tránh cả hai cùng xử lý.

**Retry chỉ các item thất bại:** sau khi có kết quả cuối, client có thể gửi **một batch mới** chỉ chứa các item có lỗi tạm thời. Nhưng lỗi 409 bị khóa hoặc 412 ETag sai cần người dùng giải quyết trạng thái/đọc lại trước khi thử. Lỗi 429/503 có thể retry theo backoff và Retry-After nếu có. Không coi mọi item có outcome failed đều retryable.

Nếu một batch có lỗi hệ thống mà item còn **unknown outcome**, client nên truy vấn operation ID hoặc gửi lại với **cùng Idempotency-Key**, tránh tự tạo request mới ngay.

## 11. Concurrency control, phiên bản và thứ tự

Trong DELETE đơn lẻ, client có thể gửi If-Match trong header. Với **nhiều item có phiên bản khác nhau**, một header If-Match chung không đủ biểu diễn các điều kiện riêng.

Trong ví dụ batch, **ifMatch** nằm trong mỗi item và được server diễn giải theo quy tắc **so sánh phiên bản/ETag của từng tài liệu**. Đây là quy ước của **request JSON ứng dụng**, không phải HTTP tự động áp dụng điều kiện If-Match tới từng phần tử.

~~~json
{
  "items": [
    {"documentId":"d-101","ifMatch":"\"v7\""},
    {"documentId":"d-102","ifMatch":"\"v12\""}
  ]
}
~~~

Khi tài liệu d-102 đã lên v13, kết quả item có thể là **412** còn d-101 vẫn **204** ở chế độ best-effort. Điều kiện kiểm tra phải gắn **nguyên tử** với câu lệnh DB để tránh race giữa SELECT và DELETE.

**Thứ tự xử lý:** nếu các item phụ thuộc nhau, ví dụ xóa parent và child có FK hoặc chuyển trạng thái theo chuỗi, không thể coi chúng độc lập. Cần nhóm phụ thuộc, chốt thứ tự, hoặc chuyển sang giao dịch atomic/batch workflow có quan hệ rõ. Không hứa thứ tự hoàn thành nếu server xử lý song song mà không kiểm soát.

## 12. Xóa bất đồng bộ: job resource, trạng thái và phân trang kết quả

Khi batch hàng nghìn tài nguyên, nhiều dịch vụ liên quan hoặc xử lý vượt timeout HTTP, mô hình job thường phù hợp.

~~~mermaid
flowchart LR
    C[Client] -->|POST batch| API[Bulk API]
    API -->|202 Location| C
    API --> R[(Operation store)]
    R --> Q[Queue]
    Q --> W1[Worker 1]
    Q --> W2[Worker 2]
    W1 --> D[(Data services)]
    W2 --> D
    W1 --> R
    W2 --> R
    C -->|GET operation| API
~~~

Resource job có thể dùng:

~~~http
GET /api/v1/operations/op-902 HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "operationId": "op-902",
  "state": "running",
  "summary": {
    "total": 1000,
    "succeeded": 620,
    "failed": 13,
    "pending": 367
  },
  "resultsUrl": "/api/v1/operations/op-902/results"
}
~~~

Một số trạng thái hợp lý:

| State | Ý nghĩa |
| --- | --- |
| queued | Đã ghi nhận bền vững, chờ worker |
| running | Đang xử lý |
| completed | Đã kết thúc, toàn bộ item thành công |
| completed_with_errors | Đã kết thúc, có item lỗi |
| failed | Operation thất bại ở cấp hệ thống |
| cancelled | Bị hủy theo chính sách; phải nêu cách xử lý item đã commit |

Với số lượng lớn, **đừng đưa hàng nghìn kết quả vào một phản hồi không phân trang**. Có thể cung cấp **GET /operations/{id}/results?cursor=...&limit=...**, lưu trạng thái item đủ lâu để client tra cứu và dùng cursor có thứ tự ổn định.

**Không tự giả định** rằng cancel job có thể rollback mọi item đã commit. API phải mô tả liệu cancel ngăn item chưa bắt đầu, tạm dừng worker hay chạy compensation. Đối với job đã hoàn thành một phần, kết quả từng item vẫn phải có thể truy vết.

**Thời gian lưu operation:** công bố TTL cho job/result và cách client lấy kết quả sau TTL. Giới hạn quyền xem job theo user/tenant, tránh lộ danh sách ID của người khác.

## 13. Bảo mật và quản trị tài nguyên

Bulk API tạo bề mặt rủi ro lớn hơn thao tác đơn lẻ vì một request có thể tác động nhiều resource. Các lớp bảo vệ gồm:

- **Xác thực request:** kiểm tra token/phiên, giới hạn quyền gọi bulk theo vai trò.
- **Phân quyền từng item:** dù caller được dùng endpoint, không có nghĩa được sửa/xóa mọi resource ID trong danh sách.
- **Tenant isolation:** truy vấn DB, job và kết quả phải ràng buộc tenant đã xác thực; không tin tenantId do client tự cung cấp.
- **Không lộ sự tồn tại:** có thể trả item 404 cho tài nguyên ngoài phạm vi theo chính sách, thay vì diễn giải “bị cấm” kèm tên dữ liệu.
- **Hạn mức:** giới hạn số item, kích thước body, số request, số job đang chạy, concurrency và tổng công việc mỗi tenant.
- **Kiểm toán:** lưu operation ID, người gọi, phạm vi, thời điểm, số thành công/thất bại, item được phép ghi audit, tránh lưu payload bí mật.
- **Input validation:** kiểm tra số lượng, định dạng ID, duplicate, điều kiện và payload; không để một phần tử hỏng cú pháp khiến validator bỏ qua âm thầm.
- **Chống lạm dụng:** bulk không được trở thành cách vượt rate limit của endpoint đơn lẻ; tính quota theo cả request và item/tài nguyên.
- **CSRF/CORS:** với cookie authentication, cần chống CSRF; CORS không thay cho phân quyền.

Ngay cả khi một item không được quyền, toàn batch không nhất thiết phải thất bại trong best-effort. Nhưng chiến lược ẩn danh và quy tắc che giấu kết quả cần được quyết định rõ: không trả metadata nhạy cảm của item ngoài phạm vi.

## 14. Hiệu năng, giới hạn batch và quan sát

**Batch lớn hơn** giảm số round-trip nhưng có thể làm tăng thời gian giữ kết nối, lock DB, memory, timeout, queue depth và blast radius khi lỗi.

Những giới hạn nên đo rồi chọn, không mặc định 100 hay 1.000 là tối ưu:

| Giới hạn | Câu hỏi |
| --- | --- |
| Max items | Bao nhiêu ID/request đảm bảo latency hoặc thời gian xử lý chấp nhận được? |
| Max request bytes | Payload có vượt gateway/proxy limit không? |
| Max concurrency | Một tenant có thể tạo bao nhiêu job cùng lúc? |
| Per-item timeout | Item bị treo có làm chặn item khác không? |
| DB transaction scope | Một transaction/item hay transaction/batch? |
| Queue lag | Khi tăng tải, thời gian chờ có vượt SLO không? |
| Result retention | Kết quả được giữ bao lâu, có phân trang không? |

Một giới hạn ban đầu ví dụ **100 item/request** chỉ là điểm khởi đầu để đo; cần thử nghiệm dựa trên tài nguyên thực và tải đồng thời.

**Tránh N+1 không kiểm soát:** một vòng lặp SELECT+UPDATE cho 1.000 item có thể làm số round-trip DB tăng mạnh. Có thể tối ưu bằng cách kiểm tra quyền/trạng thái theo nhóm và update có điều kiện, nhưng phải giữ kết quả đúng cho từng item và bảo đảm transaction semantics. Đừng gộp thành một UPDATE không có cách phân biệt item lỗi nếu hợp đồng cần chi tiết.

**Không dùng retry vô hạn:** worker cần exponential backoff, jitter, giới hạn thử lại và dead-letter queue phù hợp. Một item lỗi kéo dài không nên chặn mãi các item khác.

Các metric nên có:

- Request count, batch size, p50/p95 xử lý batch, HTTP status ngoài cùng.
- Tỷ lệ item succeeded/failed/skipped theo mã lỗi ứng dụng.
- Queue lag, job age, số job pending/running/failed và thời gian hoàn tất.
- Số lần retry, duplicate request bị dedup, xung đột idempotency key.
- Số item bị từ chối phân quyền, số vi phạm quota và chi phí trên item.
- Tracing theo operation ID, correlation ID và tenant ID có kiểm soát.

Một dashboard chỉ đo HTTP 200 rate có thể khiến đội vận hành tưởng tất cả đều thành công trong khi tỷ lệ item failed tăng cao.

## 15. Minh họa Java/Spring Boot: best-effort với kết quả từng item

Ví dụ này biểu diễn cách chia trách nhiệm giữa controller, coordinator và service xử lý item. Giả sử ứng dụng dùng **Java 17+**, Spring Web, Spring Validation, Spring Data/JPA và một TenantContext được xác thực. Các lớp dữ liệu, security và exception mapping là phần cần triển khai theo dự án.

### 15.1. Request/response record

~~~java
public record DeleteItem(
        @NotNull UUID documentId,
        @NotBlank String ifMatch) {}

public record BatchDeleteRequest(
        @NotEmpty @Size(max = 100)
        List<@Valid DeleteItem> items) {}

public record ItemResult(
        UUID documentId,
        int status,
        String outcome,
        String errorCode) {}

public record BatchDeleteResponse(
        String operationId,
        int total,
        int succeeded,
        int failed,
        List<ItemResult> results) {}
~~~

Để đơn giản, ví dụ sử dụng UUID thật (dạng 36 ký tự) thay cho ID d-101 ngắn trong phần giải thích. **ifMatch** chỉ biểu diễn một strong ETag phù hợp với hợp đồng riêng; nếu API chấp nhận danh sách ETag theo cú pháp HTTP, cần parser đúng chuẩn.

### 15.2. Controller

~~~java
@RestController
@RequestMapping("/api/v1/document-batch-deletions")
public class BatchDeleteController {
    private final BatchDeleteCoordinator coordinator;
    private final TenantContext tenantContext;

    public BatchDeleteController(BatchDeleteCoordinator coordinator,
                                 TenantContext tenantContext) {
        this.coordinator = coordinator;
        this.tenantContext = tenantContext;
    }

    @PostMapping
    public ResponseEntity<BatchDeleteResponse> execute(
            @Valid @RequestBody BatchDeleteRequest request,
            @RequestHeader("Idempotency-Key") String idempotencyKey) {

        UUID tenantId = tenantContext.requireAuthorizedTenant();
        // Một IdempotencyService thực tế phải dedup key trước khi xử lý.
        BatchDeleteResponse response =
                coordinator.execute(tenantId, request);
        return ResponseEntity.ok(response);
    }
}
~~~

**Quan trọng:** controller trên chỉ minh họa luồng request/response. Nó **chưa triển khai dedup Idempotency-Key**, dù đã khai báo header; không được dùng như API retry-safe ở production. Thành phần idempotency cần lưu key, fingerprint, operation/result, scope và TTL, đồng thời xử lý request trùng đến đồng thời trước khi gọi coordinator.

### 15.3. Coordinator xử lý từng item

~~~java
@Service
public class BatchDeleteCoordinator {
    private final DocumentDeleteItemService itemService;

    public BatchDeleteCoordinator(DocumentDeleteItemService itemService) {
        this.itemService = itemService;
    }

    public BatchDeleteResponse execute(UUID tenantId,
                                       BatchDeleteRequest request) {
        // Trước khi gọi đây, phải kiểm tra ID trùng và mọi giới hạn.
        List<ItemResult> results = new ArrayList<>();

        for (DeleteItem item : request.items()) {
            try {
                itemService.deleteOne(
                        tenantId, item.documentId(), item.ifMatch());
                results.add(new ItemResult(
                        item.documentId(), 204, "succeeded", null));
            } catch (DocumentNotFoundException ex) {
                results.add(new ItemResult(
                        item.documentId(), 404, "failed", "NOT_FOUND"));
            } catch (DocumentLockedException ex) {
                results.add(new ItemResult(
                        item.documentId(), 409, "failed", "DOCUMENT_LOCKED"));
            } catch (VersionConflictException ex) {
                results.add(new ItemResult(
                        item.documentId(), 412, "failed", "ETAG_MISMATCH"));
            }
        }

        int succeeded = (int) results.stream()
                .filter(r -> "succeeded".equals(r.outcome()))
                .count();

        return new BatchDeleteResponse(
                UUID.randomUUID().toString(),
                results.size(),
                succeeded,
                results.size() - succeeded,
                results);
    }
}
~~~

### 15.4. Giao dịch cho từng item

~~~java
@Service
public class DocumentDeleteItemService {
    private final DocumentRepository repository;

    public DocumentDeleteItemService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void deleteOne(UUID tenantId, UUID documentId, String ifMatch) {
        Document d = repository.findByTenantIdAndId(tenantId, documentId)
                .orElseThrow(DocumentNotFoundException::new);

        // Phải kiểm tra quyền thao tác trên chính tài liệu này.
        if (d.isLocked()) {
            throw new DocumentLockedException();
        }

        String currentEtag = "\"v" + d.getVersion() + "\"";
        if (!currentEtag.equals(ifMatch)) {
            throw new VersionConflictException();
        }

        int affected = repository.markDeletedIfVersionMatches(
                tenantId, documentId, d.getVersion());

        if (affected != 1) {
            throw new VersionConflictException();
        }

        // Nếu cần cleanup bất đồng bộ, ghi outbox trong cùng giao dịch.
    }
}
~~~

Repository cần có **UPDATE có điều kiện theo (tenantId, documentId, version)** và chỉ tác động tài liệu chưa xóa. Đây là cơ chế bảo vệ race sau khi đọc; không phải chỉ SELECT phiên bản rồi UPDATE vô điều kiện.

**REQUIRES_NEW** hoạt động như mong đợi khi phương thức được gọi qua bean Spring khác, như ví dụ coordinator → itemService. Tự gọi phương thức có annotation từ chính object đó có thể không đi qua proxy Spring và bỏ qua cơ chế transaction.

**Giới hạn cần hoàn thiện:** kiểm tra duplicate toàn request; tạo operation ID ổn định và lưu kết quả; dedup Idempotency-Key; exception classes; quyền theo resource; mapping lỗi hệ thống; xử lý transaction commit failure; outbox; tenant scope; metrics; kiểm thử concurrency. Trong code ví dụ, lỗi không được liệt kê sẽ lan ra ngoài và có thể khiến request-level error dù một số item đã commit; đây chính là lý do production cần lưu operation và outcome bền vững, nhất là khi yêu cầu retry sau timeout.

## 16. OpenAPI 3.1: định nghĩa contract bulk

Đoạn OpenAPI sau mô tả **một hợp đồng đồng bộ** với **200 + kết quả từng item**. Đây là skeleton để hoàn thiện security và schema lỗi toàn request:

~~~yaml
openapi: 3.1.0
info:
  title: Document Bulk API
  version: 1.0.0
paths:
  /api/v1/document-batch-deletions:
    post:
      operationId: deleteDocumentsBatch
      summary: Xóa nhiều tài liệu theo best-effort
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema:
            type: string
            minLength: 1
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [items]
              properties:
                items:
                  type: array
                  minItems: 1
                  maxItems: 100
                  items:
                    type: object
                    required: [documentId, ifMatch]
                    properties:
                      documentId:
                        type: string
                        format: uuid
                      ifMatch:
                        type: string
      responses:
        '200':
          description: Đã xử lý batch; xem outcome của từng item
          content:
            application/json:
              schema:
                type: object
                required: [operationId, total, succeeded, failed, results]
                properties:
                  operationId:
                    type: string
                  total:
                    type: integer
                    minimum: 0
                  succeeded:
                    type: integer
                    minimum: 0
                  failed:
                    type: integer
                    minimum: 0
                  results:
                    type: array
                    items:
                      type: object
                      required: [documentId, status, outcome]
                      properties:
                        documentId:
                          type: string
                          format: uuid
                        status:
                          type: integer
                        outcome:
                          type: string
                          enum: [succeeded, failed]
                        errorCode:
                          type: string
        '400':
          description: Request sai cấu trúc hoặc chứa ID trùng
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền dùng bulk operation
        '409':
          description: Idempotency-Key được dùng với payload khác
        '429':
          description: Vượt giới hạn request hoặc quota
        '503':
          description: Dịch vụ tạm không nhận xử lý
      security:
        - bearerAuth: []
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Hợp đồng thực cần bổ sung: kiểm tra request body không có field trái hợp đồng nếu cần; schema error chi tiết bằng **application/problem+json**; định nghĩa key TTL; trật tự results; cơ chế nhận diện lỗi item; và cách client xử lý kết quả chưa biết khi mất phản hồi. Nếu hỗ trợ job, bổ sung POST trả 202/201 và GET operation/result, gồm phân trang.

## 17. Kiểm thử contract và lỗi thực tế

### 17.1. Ma trận kiểm thử đề xuất

| Trường hợp | Hành động | Kết quả cần xác minh |
| --- | --- | --- |
| Toàn bộ thành công | 3 item đủ quyền và phiên bản | HTTP 200, succeeded=3, failed=0, đúng thứ tự |
| Thành công từng phần | 2 item hợp lệ, 1 item locked | HTTP 200, item 204/204/409, tổng đúng |
| Toàn bộ item lỗi nghiệp vụ | 3 item đều bị khóa | HTTP 200 + 3 lỗi item, không giả báo thành công |
| JSON sai | Body thiếu dấu hoặc sai kiểu | 400; không item nào thay đổi |
| Danh sách rỗng | items=[] | 400/422 theo hợp đồng; không thay đổi |
| Vượt max 100 | 101 item | Từ chối toàn request; không xử lý 100 đầu |
| ID trùng | Một ID xuất hiện hai lần | Từ chối theo chính sách trước commit |
| Không có quyền gọi batch | Token không cho phép chức năng bulk | 403 toàn request |
| Item không thuộc tenant | Một ID thuộc tenant khác | Item 404/403 theo chính sách, không rò dữ liệu |
| Version mismatch | ifMatch v7 nhưng hiện tại v8 | Item 412; tài liệu vẫn còn |
| Race | Update và batch delete cùng thời điểm | Không xóa nhầm phiên bản mới |
| Timeout sau commit một phần | Phản hồi bị mất rồi retry cùng key | Không tạo operation hoặc tác dụng lặp |
| Cùng key khác payload | Đổi danh sách nhưng giữ key | 409 hoặc lỗi hợp đồng; không xử lý mới |
| Concurrent same key | Hai POST cùng key/payload song song | Một logical operation, kết quả/trạng thái thống nhất |
| Lỗi hệ thống giữa batch | Worker/DB tạm lỗi sau vài item | Outcome đã ghi bền vững; item chưa rõ được phân biệt |
| Job theo thời gian | POST trả 202 và polling | Queued→running→terminal, kết quả truy vấn được |
| Hủy job đang chạy | Cancel sau khi vài item đã commit | Không tuyên bố rollback nếu không có compensation |
| Tải lớn | Nhiều tenant gửi batch 100 item | Quota, concurrency, SLO và retry có giới hạn |
| Bảo mật operation URL | User B GET job của A | Không xem được ID/kết quả của A |

### 17.2. Vì sao test retry đặc biệt quan trọng?

Một test chỉ gọi POST hai lần liên tiếp có thể chưa bắt được lỗi quan trọng. Hãy mô phỏng:

1. Client gửi batch có **Idempotency-Key K**.
2. Server commit item 1 và 2; trước khi trả response, kết nối bị ngắt.
3. Client gửi lại **đúng request và key K**.
4. API tìm lại logical operation, không thực hiện thêm thao tác gây hại.
5. Client đọc kết quả cuối, xác định item 3 cần xử lý hay chưa.
6. Kiểm tra DB, event/outbox, queue, audit, billing và các tác dụng phụ.

Đó là tình huống thực tế khi mạng không phân biệt được “request chưa tới server” và “server đã xử lý nhưng response mất”.

## 18. Tình huống thực tế: xóa 12 tài liệu

Một nhóm vận hành chọn **12 tài liệu** để xóa trong hệ thống dùng nhiều tenant. Request hợp lệ, caller được sử dụng bulk endpoint. Sau khi xử lý best-effort, hệ thống ghi nhận:

- **8** tài liệu được gỡ thành công.
- **2** tài liệu bị khóa bởi quy trình duyệt.
- **1** tài liệu có version không khớp.
- **1** tài liệu nằm ngoài phạm vi caller có thể nhìn thấy.

Kết quả tổng hợp nên ghi:

~~~json
{
  "operationId": "op-930",
  "state": "completed_with_errors",
  "summary": {
    "total": 12,
    "succeeded": 8,
    "failed": 4,
    "skipped": 0
  },
  "resultsUrl": "/api/v1/operations/op-930/results"
}
~~~

**HTTP 200** có thể hợp lý nếu đây là thao tác đồng bộ và response hoặc đường results trả đủ dữ liệu item; không dùng 206. Nếu server chỉ mới nhận job, trả **202** và một operation URL. Nếu API chủ đích hỗ trợ JSON multi-status với 207, phải nêu rõ định dạng đó trong hợp đồng.

Client nên hiển thị **“Đã xóa 8/12 tài liệu; 4 mục cần xử lý”**. Không cho phép người dùng bấm “Thử lại 12 mục” một cách thiếu kiểm soát; cần giữ operation ID và:

- Cho phép mở khóa hoặc giải quyết trạng thái của 2 tài liệu rồi thử lại.
- Đọc bản mới của tài liệu khác phiên bản và yêu cầu quyết định lại.
- Không hiển thị metadata của tài liệu ngoài phạm vi quyền.
- Chỉ gửi batch mới cho item được phép retry, dùng key mới cho ý định mới.

## 19. Bài thực hành thiết kế API

**Bối cảnh:** hệ thống quản lý đơn hàng cho phép nhân viên cập nhật trạng thái nhiều đơn sang **ready_for_shipping**. Trong danh sách 50 đơn:

- 36 đơn hợp lệ để chuyển trạng thái.
- 7 đơn đã hủy, không được đổi.
- 4 đơn vừa được xử lý bởi nhân viên khác.
- 3 đơn không thuộc chi nhánh được phép quản lý.

Yêu cầu: giữ lịch sử thay đổi, tránh cập nhật nhầm phiên bản, công bố kết quả theo item và bảo đảm retry sau timeout không tạo sự kiện nghiệp vụ trùng.

### Nhiệm vụ A – Hợp đồng tài nguyên

Thiết kế URI và phương thức để tạo một **batch status transition operation**, giải thích lý do dùng resource thay vì một endpoint hành động không có mô hình. Định nghĩa request schema với order ID, expected version và idempotency key.

### Nhiệm vụ B – Phản hồi từng phần

Thiết kế bảng mã item cho **36 thành công, 7 xung đột trạng thái, 4 version mismatch và 3 ngoài quyền**. Chọn HTTP status ngoài cùng và giải thích tại sao không dùng 206. Định nghĩa cách trả kết quả nếu job chạy hơn 30 giây.

### Nhiệm vụ C – Nhất quán và retry

Chọn atomic hay best-effort và giải thích bằng yêu cầu nghiệp vụ. Mô tả transaction boundary, dedup event theo item/operation, idempotency key, cách kiểm tra version nguyên tử và khả năng phục hồi sau khi worker dừng.

### Nhiệm vụ D – Bảo mật, hiệu năng và kiểm thử

Đặt giới hạn batch, quyền theo đơn/chi nhánh, audit và rate limit. Viết tối thiểu 8 test, trong đó có concurrent same key, cross-branch authorization, timeout sau commit một phần và queue retry.

### 19.1. Hướng giải tham khảo

Một phương án khả thi là **POST /api/v1/order-status-transition-jobs** tạo operation resource; worker xử lý best-effort theo từng order, với câu lệnh chuyển trạng thái có điều kiện **(order_id, branch_id, expected_version, current_status)**. Cùng transaction DB ghi outbox event có unique logical transition ID để ngăn thông báo hoặc tác động nghiệp vụ trùng.

| Nhóm | Số lượng | Item status ví dụ | Cách xử lý |
| --- | ---: | --- | --- |
| Chuyển trạng thái thành công | 36 | 200 hoặc 204 theo hợp đồng item | Đánh dấu succeeded |
| Đã hủy, không thể chuyển | 7 | 409 | Cần quyết định nghiệp vụ |
| Version đã đổi | 4 | 412 | Đọc lại trước khi thử |
| Ngoài quyền xem/chuyển | 3 | 404 theo chính sách che giấu | Không tiết lộ chi tiết |

**36 + 7 + 4 + 3 = 50**, nên summary succeeded=36 và failed=14. Nếu job mới được chấp nhận, HTTP ngoài cùng trả **202** kèm Location. Khi trạng thái operation đạt completed_with_errors, client đọc kết quả và xử lý 14 mục theo nguyên nhân.

Với cập nhật đơn hàng, **không nên retry vô điều kiện 14 mục**: 409/412 thường cần kiểm tra lại trạng thái/phiên bản; 404 có thể là ngoài quyền và không nên làm lộ thêm dữ liệu. Các item lỗi tạm thời mới phù hợp để retry tự động theo chính sách.

## 20. Những lỗi thiết kế cần tránh

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ trả status 200 không có kết quả item | Client hiểu sai đã hoàn thành tất cả | Response có per-item outcome |
| Dùng 206 cho partial batch success | Sai ngữ nghĩa HTTP Range | Dùng 200+body, 202/job hoặc 207 khi quy định |
| Dùng 207 nhưng nghĩ JSON đã chuẩn hóa sẵn | Client không tương thích | Công bố schema và semantics rõ |
| Trả 202 rồi không có job resource | Không biết cuối cùng item nào lỗi | Operation ID, polling, result retention |
| Bọc toàn bộ vòng lặp bằng một transaction nhưng hứa partial commit | Một lỗi rollback mất mọi thành công | Quy định transaction scope đúng mode |
| Bắt lỗi hệ thống rồi trả 200 với mọi item failed | Che giấu tình trạng chưa xác định | Phân biệt request/operation failure và item failure |
| Retry POST bằng key mới sau timeout | Có thể nhân đôi hiệu ứng | Dùng idempotency key và trạng thái đã lưu |
| Chỉ bảo vệ key ở request, không bảo vệ side effect item | Worker retry gây trùng event | Item-level idempotency và outbox |
| Dựa vào client truyền tenantId để định quyền | Truy cập chéo tenant | Tenant context đã xác thực |
| Không giới hạn items/job/concurrency | Quá tải và noisy-neighbor | Quota theo request, item và tenant |
| Kết quả không có ID đối chiếu | UI gắn lỗi sai hàng | clientItemId hoặc kết quả theo đúng thứ tự |
| Ghi dữ liệu nhạy cảm vào item error | Lộ dữ liệu/chi tiết hệ thống | Error code ổn định, message an toàn |
| Chạy song song item có quan hệ phụ thuộc | Vi phạm thứ tự và trạng thái | Nhóm phụ thuộc hoặc atomic/workflow |

## 21. Checklist trước khi công bố API

- [ ] Đã xác định thao tác đơn lẻ hay batch, resource và mục tiêu nghiệp vụ.
- [ ] Đã chọn **all-or-nothing** hoặc **best-effort** và nêu transaction boundary.
- [ ] Request có schema, max items, định danh item và quy tắc ID trùng.
- [ ] Phản hồi phân biệt request-level, operation-level và item-level outcome.
- [ ] HTTP 200/202/207 được chọn đúng với ngữ nghĩa và hợp đồng.
- [ ] Không dùng 206 để biểu đạt một phần item thành công.
- [ ] Dùng 204 chỉ khi không cần response content.
- [ ] Kết quả có mã item, error code, ID đối chiếu và summary nhất quán.
- [ ] Có Idempotency-Key, phạm vi, fingerprint, TTL, xử lý concurrent duplicate.
- [ ] Side effect từng item có thể retry an toàn, không tạo dữ liệu/event trùng.
- [ ] Có version/concurrency check khi item có thể bị sửa đồng thời.
- [ ] Có authorization từng item, tenant isolation, audit và error không lộ dữ liệu.
- [ ] Có rate limit, quota, giới hạn job và chính sách retry/backoff.
- [ ] Nếu bất đồng bộ, có operation resource, trạng thái cuối và pagination kết quả.
- [ ] Có OpenAPI, test lỗi HTTP và test timeout sau khi commit một phần.

**Ghi nhớ:** Một bulk request có thể được **xử lý thành công ở cấp HTTP** trong khi **một số item không đạt mục tiêu**. Thiết kế REST API tốt phải công bố rõ ý nghĩa của mỗi lớp kết quả, cách từng item được commit, và cách client biết phải làm gì sau lỗi hoặc timeout.
