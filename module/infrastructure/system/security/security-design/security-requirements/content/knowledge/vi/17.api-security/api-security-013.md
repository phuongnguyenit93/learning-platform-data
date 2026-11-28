# Error response contract

## 1. Vì sao phản hồi lỗi cần một hợp đồng bảo mật?

API không chỉ trao đổi dữ liệu ở đường thành công. Request sai định dạng, token hết hạn, quyền không đủ, tài nguyên không tồn tại, giới hạn tốc độ và lỗi dependency đều tạo ra những đường phản hồi riêng.

Nếu các đường này được xử lý tùy hứng, cùng một lỗi có thể lúc trả JSON, lúc trả HTML, lúc trả HTTP 200 chứa thông báo thất bại. Một exception khác có thể làm lộ stack trace, câu truy vấn, token hoặc giá trị dữ liệu không thuộc quyền của client.

**Error response contract** là hợp đồng quy định cách API biểu diễn và xử lý lỗi để client có thể ra quyết định đúng, trong khi hệ thống vẫn giữ ranh giới dữ liệu, danh tính và quyền truy cập.

Một hợp đồng đầy đủ cần trả lời:

1. HTTP status nào thể hiện loại kết quả nào?
2. Client dùng trường nào để phân loại lỗi bằng máy?
3. Thông tin nào được phép công khai và thông tin nào chỉ đi vào kênh chẩn đoán được bảo vệ?
4. Client có thể retry hay cần sửa request, xác thực lại hoặc kiểm tra trạng thái thao tác?
5. Lỗi có cùng hình dạng khi xuất phát từ ứng dụng, gateway và các nhánh xử lý khác không?
6. Dùng định danh nào để đối chiếu một sự cố mà không đưa bí mật vào response?

Trong module yêu cầu bảo mật, mục tiêu không dừng ở việc tạo thông báo dễ đọc. Hợp đồng phải đủ cụ thể để triển khai nhất quán và có thể nghiệm thu cả đường lỗi dự kiến lẫn lỗi bất ngờ.

## 2. Hợp đồng lỗi nằm ở nhiều lớp cùng lúc

Một phản hồi lỗi thường gồm nhiều thành phần:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| HTTP status | Phân loại kết quả theo ngữ nghĩa HTTP | 401, 403, 409, 429, 503 |
| Header | Cung cấp thông tin giao thức và chính sách | Challenge xác thực, Retry-After, Cache-Control |
| Media type | Xác định cách đọc body | `application/problem+json` theo profile của API |
| Mã lỗi ổn định | Cho client phân nhánh bằng máy | `REQUEST_VALIDATION_FAILED` |
| Thông báo công khai | Giải thích trong phạm vi được phép | “Dữ liệu yêu cầu không hợp lệ.” |
| Chi tiết có cấu trúc | Hỗ trợ sửa một lỗi cụ thể | Trường `/items/0/quantity` không đạt ràng buộc công khai |
| Định danh đối chiếu | Liên kết sự kiện với kênh hỗ trợ và quan sát | `requestId`, định danh lần xuất hiện lỗi |

Body có cấu trúc đúng nhưng status sai vẫn tạo ra một hợp đồng sai. Ngược lại, status đúng không đủ nếu body chứa dữ liệu nhạy cảm hoặc client phải phân tích chuỗi thông báo thay đổi theo ngôn ngữ.

Các lớp cũng phải nhất quán. Một body có `status: 422` không được gửi cùng status line 500 do một bộ chuyển đổi khác gây ra. Header cho biết có thể retry không nên mâu thuẫn với hướng dẫn của loại lỗi.

## 3. Mô hình đe dọa ở đường phản hồi lỗi

| Đe dọa | Cách lỗi trở thành vấn đề | Thuộc tính cần bảo vệ |
| --- | --- | --- |
| Lộ dữ liệu nội bộ | Exception được serialize nguyên vẹn | Chỉ công khai thông tin theo danh mục được phép |
| Dò tài khoản hoặc tài nguyên | Thông báo khác nhau làm lộ sự tồn tại | Chính sách tiết lộ nhất quán theo đối tượng và endpoint |
| Client hiểu sai kết quả | Mọi lỗi đều trả 200 hoặc cùng một mã chung | Phân loại có ngữ nghĩa và đủ ổn định |
| Lặp thao tác gây tác dụng trùng | Client retry khi chưa biết thao tác đã thực hiện hay chưa | Tính an toàn khi retry và cơ chế kiểm tra kết quả |
| Phát tán credential | Body, URL hoặc header lỗi chứa token | Giảm thiểu dữ liệu và kiểm soát nơi ghi nhận |
| Gây tải qua lỗi | Response chứa hàng nghìn lỗi hoặc xử lý lỗi tốn tài nguyên | Giới hạn kích thước, số mục và thời gian xử lý |
| Log injection và dữ liệu giả | Request ID hoặc thông báo chứa đầu vào được chép nguyên văn | Dữ liệu chẩn đoán có kiểu, giới hạn và nguồn gốc rõ ràng |
| Đường lỗi bỏ qua kiểm soát | Gateway trả HTML debug hoặc handler lỗi lộ entity | Hợp đồng bao phủ các điểm phát sinh lỗi trong phạm vi hệ thống |

Không phải mọi endpoint đều cần che cùng một loại thông tin. Ví dụ, một API danh mục công khai có thể cho biết mặt hàng không tồn tại, trong khi một endpoint liên quan tài khoản cá nhân có thể phải che sự tồn tại trước người không có quyền. Quyết định này phải có trong chính sách, thay vì phụ thuộc exception nào tình cờ phát sinh trước.

## 4. Xây dựng taxonomy lỗi trước khi chọn hình dạng JSON

Nên phân loại lỗi theo điều client cần làm và điều hệ thống có thể công khai, không theo tên lớp Java hoặc tên module nội bộ.

Một taxonomy có thể gồm:

- Request không đúng cú pháp hoặc hợp đồng biểu diễn.
- Dữ liệu không đáp ứng ràng buộc công khai.
- Thiếu hoặc không chấp nhận bằng chứng xác thực.
- Danh tính hợp lệ nhưng không đủ quyền.
- Tài nguyên không có hoặc không được phép tiết lộ sự tồn tại.
- Xung đột với trạng thái hiện tại của tài nguyên.
- Bị giới hạn lưu lượng hoặc tài nguyên.
- Hệ thống hoặc dependency không thể hoàn tất xử lý.
- Kết quả thao tác chưa xác định với client.

Hai exception nội bộ khác nhau có thể cùng ánh xạ sang một lỗi công khai. Ngược lại, một lỗi kỹ thuật chung như timeout có thể cần các hợp đồng khác nhau tùy việc nó xảy ra trước hay sau một tác dụng nghiệp vụ.

Tên lớp như `DatabaseConstraintViolationException` hoặc thông báo của driver không nên tự trở thành mã lỗi API. Những tên đó gắn với implementation, dễ thay đổi và có thể tiết lộ cấu trúc nội bộ.

## 5. Chọn HTTP status có ngữ nghĩa nhất quán

Hợp đồng cần xác định những status được sử dụng trong phạm vi API. Bảng dưới đây là định hướng thiết kế; việc ánh xạ chi tiết phải được công bố cho endpoint tương ứng.

| Status | Ngữ cảnh thường dùng | Điểm cần đặc tả |
| --- | --- | --- |
| 400 | Request sai cú pháp hoặc không theo cách biểu diễn được hỗ trợ | JSON hỏng, tham số không parse được, credential mâu thuẫn theo hợp đồng |
| 401 | Chưa có bằng chứng xác thực được chấp nhận cho tài nguyên được bảo vệ | Challenge phù hợp với cơ chế xác thực; không thay bằng trang đăng nhập HTML ngoài hợp đồng |
| 403 | Đã xác định chủ thể nhưng hành động không được phép | Không lộ chi tiết chính sách hoặc tài nguyên ngoài phạm vi cần thiết |
| 404 | Tài nguyên không có hoặc hệ thống chủ đích không tiết lộ sự tồn tại | Chính sách che sự tồn tại phải nhất quán |
| 405 | Method không được hỗ trợ cho tài nguyên | Header Allow phản ánh các method được hỗ trợ theo giao thức |
| 409 | Request xung đột với trạng thái hiện tại | Client có thể cần đọc trạng thái mới trước khi quyết định bước tiếp theo |
| 412 | Điều kiện tiên quyết của request không thỏa | Ví dụ một điều kiện cập nhật có If-Match không còn đúng |
| 413 | Nội dung request vượt giới hạn cho phép | Cần bao phủ cả nơi chặn ở proxy và ứng dụng |
| 415 | Media type của request không được hỗ trợ | Không trả lỗi parser nội bộ thay cho hợp đồng biểu diễn |
| 422 | Nội dung đã được hiểu nhưng không thể xử lý theo ràng buộc ngữ nghĩa của API | Phân biệt với 400 bằng quy tắc được công bố, không chọn ngẫu nhiên theo framework |
| 429 | Bên gọi vượt giới hạn lưu lượng theo chính sách | Hướng dẫn thử lại nếu có; không lộ danh tính hoặc giới hạn của người khác |
| 500 | Lỗi bất ngờ ở server | Thông báo công khai tổng quát, có mã đối chiếu phù hợp |
| 502 | Thành phần đóng vai trò gateway/proxy nhận phản hồi không hợp lệ từ upstream | Không chuyển nguyên response nội bộ của upstream cho client |
| 503 | Dịch vụ tạm thời không thể xử lý | Phân biệt lỗi khả dụng với credential không hợp lệ |
| 504 | Gateway/proxy không nhận được phản hồi upstream kịp thời | Không mặc định thao tác upstream chưa được thực hiện |

Một dự án có thể chọn 400 cho nhiều lỗi validation, hoặc phân biệt 400 và 422 theo hợp đồng rõ ràng. Điều cần tránh là cùng một loại lỗi đổi status tùy thư viện hoặc controller mà client không thể dự đoán.

Không nên dùng 200 cho một request đồng bộ đã thất bại rồi yêu cầu client tìm từ “error” trong body. Điều đó làm khó xử lý client, cache, retry và quan sát.

Cần phân biệt với API trạng thái tác vụ: một GET lấy trạng thái job có thể thành công với 200 và trả `state: FAILED`, vì request đọc trạng thái đã thành công. Lỗi của job là dữ liệu trạng thái theo hợp đồng bất đồng bộ, không phải một cái cớ để mọi thao tác đồng bộ đều trả 200 khi thất bại.

## 6. Một profile JSON cho lỗi công khai

API có thể sử dụng Problem Details với media type `application/problem+json`, hoặc một schema lỗi khác được định nghĩa rõ. Điều quan trọng là nhất quán và có các quy tắc bảo mật cụ thể.

Ví dụ một profile cho lỗi validation:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-demo-7f3

{
  "type": "https://api.example.test/problems/request-validation",
  "title": "Dữ liệu yêu cầu không hợp lệ",
  "status": 422,
  "detail": "Kiểm tra các trường được liệt kê rồi gửi lại yêu cầu.",
  "instance": "/error-occurrences/err-demo-7f3",
  "code": "REQUEST_VALIDATION_FAILED",
  "requestId": "req-demo-7f3",
  "errors": [
    {
      "pointer": "/items/0/quantity",
      "code": "OUT_OF_RANGE",
      "message": "Số lượng phải lớn hơn 0."
    }
  ]
}
```

Tên miền, định danh và dữ liệu trong ví dụ chỉ là dữ liệu minh họa. URI của loại lỗi là một định danh ổn định trong thiết kế; client không cần gọi URL do lỗi chỉ ra để xác định cách xử lý mỗi response.

### Trách nhiệm của từng trường

| Trường | Ý nghĩa trong profile minh họa | Ràng buộc bảo mật và ổn định |
| --- | --- | --- |
| `type` | Định danh loại vấn đề | Do server chọn từ danh mục, không lấy tùy ý từ request hoặc exception |
| `title` | Tiêu đề ngắn của loại lỗi | Có thể dịch theo ngôn ngữ; không dùng làm điều kiện phân nhánh của client |
| `status` | Status tương ứng của phản hồi | Phải nhất quán với HTTP status thực tế |
| `detail` | Giải thích công khai cho lần lỗi này | Chỉ chứa nội dung đã được cho phép, không nối thông báo exception thô |
| `instance` | Định danh lần xuất hiện vấn đề | Không tự chứa URL request đầy đủ, query nhạy cảm hoặc secret |
| `code` | Mã lỗi ứng dụng để client xử lý | Tập mã hữu hạn, ý nghĩa ổn định, không là tên lớp nội bộ |
| `requestId` | Định danh đối chiếu request | Không phải credential hoặc quyền truy cập vào dữ liệu chẩn đoán |
| `errors` | Các lỗi chi tiết được phép công khai | Có giới hạn số lượng, độ dài, tên trường và loại thông báo |

Profile của dự án cần nói rõ trường nào bắt buộc. Không nên giả định mọi field minh họa đều bắt buộc trong mọi cách dùng Problem Details.

`instance` không mặc nhiên là một endpoint công khai cho phép tải toàn bộ thông tin lỗi. Nếu hệ thống có endpoint tra cứu, nó cần xác thực và phân quyền riêng; biết một request ID không đủ để đọc log hoặc dữ liệu của người khác.

### Mã máy ổn định, thông báo cho người có thể thay đổi

Client nên xử lý bằng `code` hoặc `type` theo hợp đồng, không so sánh `detail == "Token expired"`. Nội dung có thể được dịch, sửa lỗi chính tả hoặc diễn giải lại mà không thay ý nghĩa mã máy.

Một mã như `ORDER_STATE_CONFLICT` nên giữ ý nghĩa đã công bố. Không tái sử dụng nó cho lỗi thanh toán hoặc lỗi dữ liệu khác chỉ để giảm số lượng mã. Cũng không tạo mã động chứa ID người dùng, tên bảng hoặc giá trị request.

## 7. Chính sách thông tin công khai và thông tin chẩn đoán

Một lỗi cần hai góc nhìn khác nhau:

```text
Nguyên nhân nội bộ đã phân loại
    → ánh xạ sang mã, status và thông báo công khai an toàn
    → ghi sự kiện chẩn đoán được kiểm soát trong kênh có quyền truy cập
```

Không nên tạo response bằng cách serialize exception hoặc trả `exception.getMessage()` trực tiếp. Nội dung đó có thể chứa chi tiết của truy vấn, địa chỉ dịch vụ, dữ liệu đầu vào hoặc thông tin từ một thư viện không thuộc hợp đồng API.

### Dữ liệu không được công khai theo mặc định

- Stack trace, tên lớp, số dòng và đường dẫn file trên server.
- Câu SQL, tên bảng nội bộ hoặc cấu trúc lưu trữ không thuộc API.
- Authorization header, access token, refresh token, session token và API key.
- Password, password hash, private key hoặc bí mật tích hợp.
- Request body đầy đủ hay response nguyên gốc của nhà cung cấp.
- Thông tin của một tài nguyên hoặc tenant mà người gọi chưa được phép biết.
- Quy tắc chống gian lận hoặc chi tiết kiểm soát nội bộ có thể hỗ trợ né tránh.

“Chỉ ghi vào log” cũng không có nghĩa là được ghi mọi dữ liệu. Log, trace và hệ thống hỗ trợ cần chính sách dữ liệu, quyền đọc, lưu giữ và redaction riêng. Một stack trace có thể hữu ích cho chẩn đoán nhưng các giá trị nhạy cảm đi kèm vẫn cần được xử lý.

### Không echo dữ liệu chỉ vì đó là dữ liệu client đã gửi

Một request có thể chứa credential, dữ liệu cá nhân hoặc thông tin do người dùng khác cung cấp qua một luồng trung gian. Việc trả lại toàn bộ nội dung khi validation thất bại có thể đưa dữ liệu vào client log, proxy hoặc công cụ hỗ trợ ngoài dự kiến.

Thông thường, client chỉ cần biết trường nào không hợp lệ và mã ràng buộc công khai. Nếu phải echo một giá trị, phải có quyết định rõ về kiểu dữ liệu, giới hạn và nơi giá trị sẽ được sử dụng.

JSON serializer vẫn phải được dùng để tạo body. Một thông báo công khai có chứa ký tự đặc biệt không được ghép thủ công vào JSON, và giá trị nhận từ error body không được client tự động đưa vào `innerHTML`.

## 8. Validation error: đủ để sửa request nhưng không lộ mô hình nội bộ

Lỗi validation có cấu trúc giúp client đánh dấu trường và hướng dẫn người dùng. Tuy nhiên, cấu trúc đó cần được thiết kế theo schema công khai của request.

Những ràng buộc nên có:

1. Đường dẫn trường tham chiếu request công khai, không tham chiếu entity hoặc tên biến nội bộ.
2. Mã lỗi nằm trong danh mục ổn định như `REQUIRED`, `INVALID_FORMAT`, `OUT_OF_RANGE`.
3. Không chứa giá trị đã bị từ chối nếu giá trị có thể nhạy cảm.
4. Không liệt kê các trường bí mật hoặc trường mà người gọi không được phép sử dụng.
5. Có giới hạn số lỗi và tổng kích thước response.
6. Thứ tự lỗi hoặc quy tắc cắt bớt được xác định khi client cần hiển thị ổn định.

Ví dụ `/items/0/quantity` có thể hữu ích khi request công khai định nghĩa `items` và `quantity`. Ngược lại, một đường dẫn như `paymentEntity.processorCredential.secretValue` có thể làm lộ mô hình nội bộ không thuộc hợp đồng.

Nếu client gửi một key không được hỗ trợ, API không nhất thiết phải chép nguyên key đó vào response. Tên trường không hợp lệ cũng là dữ liệu không đáng tin, có thể rất dài hoặc chứa ký tự gây vấn đề ở log và giao diện.

### Giới hạn lỗi phải là một yêu cầu cụ thể

Một request có hàng nghìn mục sai không nên khiến server tạo ra response lỗi lớn hơn nhiều lần request. Dự án cần xác định số mục tối đa, giới hạn độ dài và cách thông báo rằng danh sách đã được rút gọn nếu chức năng cần.

Không có một con số phù hợp cho mọi API. Giá trị giới hạn cần phản ánh kích thước request hợp lệ, trải nghiệm client và ngân sách tài nguyên của hệ thống.

## 9. Lỗi xác thực, phân quyền và che sự tồn tại

### 9.1. Thiếu hoặc không chấp nhận bằng chứng xác thực

Với API dùng bearer token, phản hồi thiếu credential có thể là:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/authentication-required",
  "title": "Cần xác thực",
  "status": 401,
  "code": "AUTHENTICATION_REQUIRED",
  "requestId": "req-demo-auth-01"
}
```

Challenge cần phù hợp với cơ chế và tình huống xác thực thực tế. Hợp đồng cũng phải xác định client được làm gì khi token không còn được chấp nhận, thay vì tự giả định mọi 401 đều có thể giải quyết bằng lặp lại request vô hạn.

### 9.2. Không đủ quyền

Một 403 không cần giải thích chi tiết danh sách role nội bộ hoặc tên rule bị thiếu. Client có thể cần biết hành động không được phép, còn thông tin chẩn đoán chi tiết phải được cân nhắc theo quyền đọc và mục đích hỗ trợ.

### 9.3. Không tiết lộ sự tồn tại

Với một tài nguyên cần che sự tồn tại trước người không có quyền, API có thể sử dụng phản hồi tương đương trường hợp không tìm thấy. Cần xác định chính sách cho cả status, body và các tín hiệu phụ có liên quan.

Ví dụ, không nên che bằng 404 nhưng vẫn trả `detail: "Đơn hàng thuộc khách hàng khác"`. Tương tự, header, số lỗi hoặc một đường endpoint khác có thể tiếp tục làm lộ điều mà thông báo chính đang che.

Một response chung không tự chứng minh mọi kênh suy luận đã được loại bỏ. Với chức năng nhạy cảm, cần kiểm tra sự khác biệt quan sát được như thông báo, metadata và hành vi xử lý, đồng thời tránh đưa ra cam kết tuyệt đối về thời gian xử lý nếu thiết kế không đáp ứng.

Đối với đăng nhập, đăng ký hoặc khôi phục tài khoản, thông báo về tài khoản tồn tại hay không cần chính sách riêng. Không tái sử dụng chi tiết validation thông thường để vô tình mở một kênh dò tài khoản.

## 10. Retry phải gắn với trạng thái thao tác

Một mã 5xx hoặc timeout không luôn chứng minh rằng thao tác chưa xảy ra. Server có thể đã ghi dữ liệu hoặc dependency đã xử lý thanh toán trước khi phản hồi bị mất.

Vì vậy, không nên mặc định mọi error body có một trường `retryable: true` đủ để client quyết định gửi lại bất kỳ request nào.

Cần phân biệt ít nhất:

- Request bị từ chối trước khi thực hiện thao tác theo bằng chứng của hệ thống.
- Thao tác chắc chắn không được áp dụng theo thiết kế giao dịch hoặc kết quả đã biết.
- Trạng thái kết quả chưa xác định với client hoặc với thành phần đang trả lỗi.

Chỉ công bố trạng thái “chưa thực hiện” khi hệ thống thực sự có cơ sở đảm bảo. Handler bắt exception không thể tự suy ra điều đó chỉ từ loại exception.

### Hướng dẫn client theo nhóm lỗi

| Nhóm phản hồi | Hành động client có thể cần | Giới hạn cần nêu |
| --- | --- | --- |
| 400 hoặc 422 | Sửa request theo hợp đồng | Không tự lặp nguyên request hỏng |
| 401 | Thực hiện luồng xác thực/làm mới đã được hỗ trợ | Có giới hạn số lần, không tạo vòng lặp refresh |
| 403 | Dừng thao tác hoặc thực hiện quy trình cấp quyền phù hợp | Không retry với cùng quyền chỉ để hy vọng thành công |
| 409 hoặc 412 | Đọc trạng thái mới, giải quyết xung đột hoặc điều kiện cập nhật | Không ghi đè mù thông tin mới |
| 429 | Chờ theo chính sách và dùng backoff phù hợp | Tôn trọng Retry-After khi có, giới hạn số lần thử |
| 503 hoặc 504 | Có thể thử lại khi thao tác và hợp đồng cho phép | Xét tính idempotent và khả năng kết quả chưa xác định |
| 500 không dự kiến | Hành vi theo loại thao tác và hợp đồng phục hồi | Không coi mọi 500 là bằng chứng rollback |

Một response tạm thời có thể dùng:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/service-unavailable",
  "title": "Dịch vụ tạm thời không khả dụng",
  "status": 503,
  "code": "SERVICE_TEMPORARILY_UNAVAILABLE",
  "requestId": "req-demo-availability-01"
}
```

Giá trị 30 giây là minh họa cho một quyết định của hệ thống, không phải cam kết mọi sự cố sẽ hết sau khoảng đó. Chỉ gửi hướng dẫn thử lại khi nó phù hợp với chính sách, và không để header mâu thuẫn với một trường hướng dẫn khác trong body.

### Idempotency và tra cứu kết quả

Với thao tác như tạo thanh toán hoặc tạo đơn hàng, hợp đồng có thể cần idempotency key hoặc mã thao tác để client tra cứu kết quả. Cần xác định phạm vi key theo chủ thể, thời gian giữ trạng thái, hành vi khi cùng key đi với dữ liệu khác và cách xử lý request đồng thời.

Key không phải quyền truy cập. Người biết một key hoặc mã thao tác không được mặc nhiên đọc kết quả của người khác. Response của lần gọi lặp cũng phải tuân theo chính sách dữ liệu hiện hành của thiết kế.

Các quy tắc này cần được giải quyết ở mức thao tác, không thể bổ sung chỉ bằng một thông báo “hãy thử lại” trong error handler.

## 11. Request ID và thông tin đối chiếu

Request ID giúp nối phản hồi công khai với sự kiện quan sát. Nó nên có kích thước giới hạn, định dạng phù hợp và không chứa dữ liệu cá nhân hay credential.

Nếu hệ thống nhận định danh do client gửi, cần xác định cách kiểm tra định dạng, giới hạn độ dài, tránh nhầm lẫn và cách tách nó khỏi định danh nội bộ đáng tin. Không phản chiếu nguyên một header tùy ý vào response header hoặc log.

Những yêu cầu cần nêu rõ:

- Định danh được tạo ở đâu và có được truyền qua các tầng không.
- Trường trong body và header có cùng giá trị hay quan hệ gì.
- Client nên cung cấp định danh nào khi liên hệ hỗ trợ.
- Dữ liệu tra cứu theo định danh được bảo vệ ra sao.
- Định danh không được sử dụng như một bearer credential.

Một thông báo có thể nói “Liên hệ hỗ trợ và cung cấp mã yêu cầu”, nhưng không nên gắn đường link công khai chứa toàn bộ log hoặc stack trace. Nếu có giao diện tra cứu, quyền xem dữ liệu và các trường công khai phải được thiết kế riêng.

## 12. Bao phủ ứng dụng, gateway và các đường xử lý đặc biệt

Một exception handler trong ứng dụng không kiểm soát được mọi phản hồi. Request có thể bị chặn vì kích thước ở reverse proxy, rate limit tại gateway hoặc timeout trước khi controller chạy.

Do đó, cần lập danh mục nơi phát sinh lỗi:

| Nơi phát sinh | Ví dụ | Điều cần thống nhất |
| --- | --- | --- |
| Gateway hoặc reverse proxy | 413, 429, 502, 503, 504 | Status, media type, body tối thiểu, request ID và dữ liệu công khai |
| Lớp đọc request | JSON hỏng, media type không hỗ trợ | Không lộ lỗi parser thô hoặc nội dung body |
| Xác thực và phân quyền | Thiếu token, token không hợp lệ, quyền không đủ | Challenge, chính sách che sự tồn tại, thông báo ổn định |
| Validation và nghiệp vụ | Trường không hợp lệ, xung đột trạng thái | Mã lỗi và chi tiết công khai đúng schema |
| Tích hợp dependency | Timeout hoặc response upstream không hợp lệ | Không chuyển tiếp secret và body upstream nguyên vẹn |
| Handler lỗi cuối cùng | Exception không được phân loại | Lỗi công khai tổng quát và sự kiện chẩn đoán được kiểm soát |

Nếu một tầng không hỗ trợ đầy đủ schema, hợp đồng cần mô tả profile tối thiểu hoặc giới hạn thực tế của tầng đó. Không tuyên bố “mọi lỗi đều có body JSON” khi một thành phần vẫn trả HTML ngoài dự kiến.

### Content negotiation và method

API cần công bố các media type lỗi và hành vi khi Accept không phù hợp hoặc request không thể parse. Không để việc tạo lỗi content negotiation lại gây một vòng lỗi mới.

Client có thể được hướng dẫn gửi Accept hỗ trợ cả biểu diễn thành công lẫn biểu diễn lỗi. Một giao diện trình duyệt có trang HTML riêng vẫn cần escaping và chính sách dữ liệu riêng; không lấy exception thô rồi nội suy vào HTML.

Đối với HEAD, hợp đồng phải tuân theo việc không gửi message body; không được coi thiếu body lỗi ở HEAD là tự động vi phạm schema JSON. Các header và status tương ứng vẫn cần nhất quán theo giao thức và phạm vi tài nguyên.

### Cache và lưu giữ

Lỗi có thể chứa thông tin theo người dùng hoặc làm lộ sự tồn tại tài nguyên. Những response không được phép lưu cần có chính sách cache phù hợp, chẳng hạn `no-store` cho nhóm lỗi nhạy cảm đã xác định.

Không mặc định mọi 4xx hoặc 5xx sẽ không bao giờ được cache. Phải xét ngữ nghĩa status, header và cấu hình các tầng thực tế. Một phản hồi 404 có nội dung theo quyền không được tái sử dụng sai chủ thể chỉ vì body trông tổng quát.

## 13. Khi đã gửi response hoặc khi thao tác chạy bất đồng bộ

### 13.1. Response đã được commit

Sau khi header và một phần body được gửi, server thường không thể đổi lại status để tạo một response lỗi mới hoàn chỉnh. Nếu đang stream JSON mà cuối luồng lỗi, việc nối một object lỗi vào cuối không tự biến body thành một tài liệu hợp lệ.

Hợp đồng streaming phải xác định cách biểu diễn thất bại trong giao thức đã chọn hoặc cách client nhận biết luồng không hoàn tất. Đối với giao thức có thông điệp lỗi trong luồng, thông điệp đó vẫn cần schema và chính sách dữ liệu riêng.

Nếu cần một tài liệu JSON nguyên vẹn và kích thước phù hợp, thiết kế có thể chuẩn bị phản hồi trước khi commit. Với dữ liệu lớn, phải cân nhắc cách truyền và hành vi lỗi thay vì hứa rằng handler luôn thay được response.

### 13.2. Tác vụ bất đồng bộ

Một request tạo job có thể trả 202 khi công việc mới được nhận, chưa hoàn tất. Cần tách:

- Lỗi khi tiếp nhận request tạo job.
- Trạng thái thực thi của job.
- Lỗi khi đọc trạng thái hoặc tải kết quả.

Mỗi phần có hợp đồng phù hợp. Thông tin thất bại của job không được chứa stack trace hoặc dữ liệu dependency chỉ vì nó nằm trong một object trạng thái thay vì một HTTP error response.

Quyền đọc trạng thái và kết quả job phải được kiểm tra. Một mã job hoặc request ID không tự thay thế quyền truy cập.

## 14. Thiết kế ánh xạ lỗi và phương án dự phòng

Một thành phần xử lý lỗi có thể sử dụng danh mục ánh xạ được kiểm soát:

```text
Loại lỗi nội bộ đã phân loại
    → HTTP status
    → public code và problem type
    → mẫu thông báo công khai
    → header cần thiết
    → chính sách cache
    → chi tiết được phép
    → mức ghi nhận sự kiện và reason code chẩn đoán
```

Mã giả minh họa:

```text
renderFailure(failure, requestContext):
    classification = classifyWithinTrustedCatalog(failure)

    if classification is unknown:
        classification = INTERNAL_ERROR_PUBLIC_PROFILE

    occurrenceId = createBoundedOpaqueIdentifier()

    recordDiagnosticEvent(
        classification,
        occurrenceId,
        redactAndLimitDiagnostics(failure, requestContext)
    )

    publicProblem = createProblemFromApprovedTemplate(
        classification,
        occurrenceId,
        approvedPublicDetails(failure)
    )

    return encodeAndWriteAccordingToContract(publicProblem)
```

`approvedPublicDetails` không có nghĩa là chuyển mọi thuộc tính exception vào một map. Nó phải chỉ tạo các trường đã biết từ dữ liệu được cho phép cho loại lỗi đó.

Lớp xử lý lỗi cũng có thể lỗi vì serialization, thiếu bộ nhớ hoặc cấu hình. Khi response chưa được gửi, hệ thống nên có phương án tối thiểu phù hợp với hợp đồng: status đúng và body công khai nhỏ, không phụ thuộc dữ liệu phức tạp hoặc dịch vụ đang lỗi. Không fallback sang trang debug hoặc serialize nguyên exception.

Nếu response đã bắt đầu, áp dụng hợp đồng luồng tương ứng. Không báo một lần thành công mới hoặc ghép thêm JSON tùy ý để che việc truyền thất bại.

## 15. Quan sát và giới hạn tài nguyên

Hợp đồng công khai không cần mang toàn bộ dữ liệu chẩn đoán. Các sự kiện vận hành có thể sử dụng mã loại lỗi, route template, mã đối chiếu, tầng phát sinh và mức độ phù hợp.

Một số điểm cần thiết kế:

- Không dùng toàn bộ URL, user ID hoặc request ID làm nhãn metric không giới hạn số giá trị.
- Phân biệt lỗi đầu vào dự kiến, dấu hiệu lạm dụng và lỗi hệ thống để cảnh báo có ý nghĩa.
- Không ghi token hoặc body request chỉ vì status thuộc nhóm lỗi.
- Giới hạn kích thước thông báo, số lỗi validation và dữ liệu đính kèm.
- Xử lý đầu vào log theo định dạng có cấu trúc và giới hạn, tránh tạo dòng log giả.
- Có chỉ tiêu và owner cho những sai lệch hợp đồng như trả HTML ngoài dự kiến hoặc status/body không khớp.

Lỗi 4xx không tự động là vấn đề của client theo nghĩa trách nhiệm vận hành; một rollout sai schema có thể khiến hàng loạt client hợp lệ bị từ chối. Tương tự, không phải mỗi lỗi dự kiến đều nên phát cảnh báo riêng. Cần quan sát theo mẫu, tỷ lệ và tác động của hệ thống.

## 16. Mẫu yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| ERROR-01 | Các nhóm lỗi trong phạm vi API có ánh xạ status, mã công khai, schema và header được định nghĩa | Đối chiếu danh mục lỗi với phản hồi thực tế theo từng nhánh |
| ERROR-02 | Mã máy ổn định và không lấy từ tên lớp hoặc thông báo exception | Đổi ngôn ngữ hoặc nguyên nhân nội bộ tương đương không làm thay ý nghĩa mã công khai |
| ERROR-03 | Body không chứa stack trace, credential, dữ liệu nội bộ hoặc giá trị nhạy cảm ngoài danh mục | Gây lỗi có dữ liệu kiểm thử dễ nhận diện và kiểm tra các kênh đầu ra |
| ERROR-04 | HTTP status và trường status trong body nhất quán khi profile có trường này | Kiểm tra ở mức HTTP qua các tầng triển khai thuộc phạm vi |
| ERROR-05 | Lỗi validation dùng schema request công khai và có giới hạn tài nguyên | Gửi request sai tại nhiều mức, kiểm tra đường dẫn trường, số lỗi và kích thước |
| ERROR-06 | Lỗi xác thực và phân quyền tuân theo cơ chế giao thức cùng chính sách tiết lộ | Kiểm tra challenge, status và các tín hiệu công khai với người không có quyền |
| ERROR-07 | Hướng dẫn retry không khẳng định sai kết quả nghiệp vụ | Mô phỏng timeout trước/sau tác dụng và kiểm tra hành vi client theo loại thao tác |
| ERROR-08 | Request ID được tạo hoặc kiểm tra có giới hạn, không là credential | Gửi định danh không hợp lệ và kiểm tra response, log, quyền tra cứu |
| ERROR-09 | Gateway, proxy và ứng dụng đáp ứng profile lỗi đã cam kết | Kiểm tra lỗi kích thước, rate limit, timeout và lỗi ứng dụng qua đường gọi thực tế |
| ERROR-10 | Response lỗi có chính sách cache và content negotiation phù hợp | Kiểm tra dữ liệu theo chủ thể, Accept không hỗ trợ và HEAD |
| ERROR-11 | Lỗi trong streaming và tác vụ bất đồng bộ có hợp đồng riêng | Gây lỗi giữa luồng, kiểm tra trạng thái job và quyền đọc kết quả |
| ERROR-12 | Phương án xử lý lỗi dự phòng không lộ chi tiết hoặc mở rộng output | Gây lỗi handler/serialization theo cách có kiểm soát và kiểm tra phản hồi tối thiểu |

Một yêu cầu chỉ có thể nghiệm thu đầy đủ khi phạm vi triển khai được chỉ rõ. Kiểm tra exception handler trong unit test không đủ để xác nhận gateway không trả một trang HTML debug khi upstream timeout.

## 17. Kịch bản chấp nhận minh họa

### 17.1. Request sai dữ liệu công khai

```text
Given:
  API định nghĩa quantity phải lớn hơn 0.
  Profile validation công bố status 422 và mã REQUEST_VALIDATION_FAILED.

When:
  Client gửi quantity không đạt ràng buộc.

Then:
  HTTP status và body status đều là 422.
  Mã máy không phụ thuộc ngôn ngữ của thông báo.
  Chi tiết chỉ tham chiếu trường trong schema công khai.
  Body không chứa request đầy đủ hoặc thông tin entity nội bộ.
```

### 17.2. Exception bất ngờ có dữ liệu nhạy cảm

```text
Given:
  Một lỗi nội bộ trong môi trường kiểm thử có thông báo chứa chuỗi đánh dấu nhạy cảm.
  Nguyên nhân chưa có ánh xạ công khai chi tiết.

When:
  Lỗi đến handler cuối cùng trước khi response được commit.

Then:
  Client nhận lỗi công khai tổng quát theo hợp đồng.
  Chuỗi đánh dấu và stack trace không xuất hiện trong response.
  Có định danh đối chiếu phù hợp.
  Kênh chẩn đoán xử lý dữ liệu theo chính sách redaction và quyền đọc riêng.
```

### 17.3. Tài nguyên cần che sự tồn tại

```text
Given:
  Chính sách không cho chủ thể A biết tài nguyên của chủ thể B có tồn tại hay không.

When:
  A truy cập tài nguyên ngoài phạm vi và tài nguyên không tồn tại.

Then:
  Các phản hồi công khai tuân theo cùng chính sách che sự tồn tại.
  Không có detail, header hoặc mã phụ làm lộ sự khác biệt bị cấm.
  Sự kiện nội bộ vẫn hỗ trợ chẩn đoán theo quyền truy cập phù hợp.
```

### 17.4. Timeout với thao tác có tác dụng

```text
Given:
  API tạo thao tác có hợp đồng idempotency hoặc tra cứu kết quả.
  Có thể xảy ra timeout sau khi dependency đã thực hiện tác dụng.

When:
  Client không nhận được kết quả hoàn chỉnh.

Then:
  Phản hồi và tài liệu không khẳng định thao tác chưa xảy ra nếu không có bằng chứng.
  Client dùng cơ chế phục hồi được công bố thay vì gửi lặp một thao tác mới tùy ý.
  Việc tra cứu hoặc lấy lại kết quả vẫn kiểm tra quyền.
```

## 18. Ma trận kiểm chứng cho hợp đồng lỗi

| Nhóm tình huống | Điều cần quan sát |
| --- | --- |
| JSON hỏng, body rỗng không hợp lệ, tham số sai kiểu | Status, media type, mã lỗi và không lộ parser internals |
| Trường thiếu, giá trị vượt giới hạn, nhiều mục sai | Danh sách lỗi có cấu trúc, không echo bí mật, giới hạn kích thước |
| Thiếu token, token không hợp lệ, không đủ quyền | Ngữ nghĩa status, challenge và chính sách tiết lộ |
| Tài nguyên không có hoặc ngoài phạm vi | Không có tín hiệu công khai trái chính sách |
| Xung đột cập nhật và điều kiện If-Match không đúng | Client biết cách phục hồi mà không ghi đè mù |
| Rate limit và dịch vụ tạm thời không khả dụng | Retry-After nếu có và hành vi backoff theo hợp đồng |
| Upstream lỗi, timeout trước/sau tác dụng | Không chuyển nguyên body upstream; không hứa sai trạng thái thao tác |
| Gateway chặn request | Profile tối thiểu, request ID và không trả HTML ngoài cam kết |
| Accept không hỗ trợ, HEAD và các method không hợp lệ | Hành vi giao thức rõ ràng, không lỗi lặp trong handler |
| Request ID hoặc đầu vào rất dài | Giới hạn và không phản chiếu nội dung nguy hiểm |
| Cache và nhiều chủ thể | Lỗi chứa ngữ cảnh riêng không được phát lại sai người |
| Exception handler hoặc serialization lỗi | Phương án tối thiểu an toàn khi còn có thể tạo response |
| Streaming và job thất bại | Client nhận biết kết quả theo hợp đồng của luồng/tác vụ |
| Thay ngôn ngữ hoặc phiên bản client | Mã máy ổn định, client không phụ thuộc thông báo tự nhiên |

Bằng chứng nên lấy từ HTTP response thực tế đi qua các thành phần thuộc phạm vi, cùng sự kiện quan sát được phép kiểm tra. Chỉ đọc source code hoặc chụp một thông báo trên màn hình chưa chứng minh mọi đường lỗi giữ đúng hợp đồng.

## 19. Duy trì hợp đồng khi hệ thống thay đổi

Mỗi khi thêm endpoint, loại dependency, điều kiện phân quyền hoặc lỗi nghiệp vụ mới, nhóm cần quyết định ánh xạ công khai trước khi dựa vào hành vi mặc định của framework. Một lỗi chưa biết phải rơi vào profile tổng quát an toàn, không tự mở rộng chi tiết gửi ra ngoài.

Thay đổi mã máy, status hoặc ý nghĩa retry có thể ảnh hưởng client đang hoạt động. Cần quản lý tương thích, tài liệu và thời gian chuyển đổi phù hợp. Việc sửa câu thông báo cho người dùng không nên buộc client thay logic nếu client tuân theo mã máy đã công bố.

Hợp đồng lỗi đạt mục tiêu khi client nhận đủ thông tin để hành động đúng, thông tin chẩn đoán không vượt ranh giới công khai và hệ thống không biến thất bại thành một đường bỏ qua bảo mật. Các quyết định về dữ liệu, quyền, cache và kết quả thao tác phải giữ nguyên ý nghĩa ngay cả khi đường thành công không thể hoàn tất.
