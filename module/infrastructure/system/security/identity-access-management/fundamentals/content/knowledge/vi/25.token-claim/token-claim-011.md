# Token introspection

Một API nhận access token từ ứng dụng khách. Nếu token là một chuỗi opaque, API không thể đọc các claim từ chuỗi ấy. Nếu token là JWT, kiểm tra chữ ký tại chỗ cũng chưa tự trả lời được liệu hệ thống cấp quyền đã thu hồi token hay chưa. Token introspection cung cấp một cách để API hỏi hệ thống phát hành về trạng thái và thông tin của token.

Trong IAM, introspection giúp đưa thông tin từ hệ thống quản lý vòng đời token vào quyết định truy cập. Tuy nhiên, nó không thay thế toàn bộ phân quyền của ứng dụng và cũng không tự bảo đảm mọi thay đổi quyền được phản ánh tức thời.

## 1. Introspection là một trao đổi giữa các hệ thống

OAuth 2.0 Token Introspection cho phép resource server được cấp quyền hỏi Authorization Server về một token, nhận trạng thái cùng metadata liên quan. Giao thức được định nghĩa trong [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.html).

Các bên trong một triển khai minh họa gồm:

| Thành phần | Trách nhiệm |
|---|---|
| Client | Nhận access token rồi trình token khi gọi API |
| Resource Server | Bảo vệ tài nguyên, gọi introspection và quyết định cho phép thao tác |
| Authorization Server | Kiểm tra trạng thái token và trả thông tin phù hợp cho bên hỏi |
| Người dùng hoặc workload | Chủ thể hoặc bên có quyền liên quan tới luồng cấp token |

Ví dụ, ứng dụng quản lý đơn hàng gửi token tới API đơn hàng. API dùng danh tính dịch vụ của mình để gọi endpoint introspection đã cấu hình. Trình duyệt không cần biết credential nội bộ của API, và không được nhúng credential đó vào mã frontend.

```mermaid
sequenceDiagram
    participant C as Client
    participant R as API đơn hàng
    participant A as Authorization Server
    C->>R: Request kèm access token
    R->>A: Introspection, API xác thực chính mình
    A-->>R: Trạng thái và metadata được phép xem
    R->>R: Kiểm tra scope, tenant và quyền trên tài nguyên
    R-->>C: Dữ liệu hoặc phản hồi từ chối
```

Hai việc cần phân biệt trong sơ đồ là: API xác thực chính nó để được hỏi, còn access token do client gửi là đối tượng đang được hỏi. Không lấy việc API có credential introspection hợp lệ làm bằng chứng rằng access token của người dùng hợp lệ.

## 2. Request và response cơ bản

Request introspection dùng POST với dữ liệu form, có tham số `token`; `token_type_hint` là gợi ý tùy chọn. Response thành công ở mức giao thức là JSON với trường boolean `active` bắt buộc. Cấu trúc này được quy định tại [RFC 7662, mục 2.1–2.2](https://www.rfc-editor.org/rfc/rfc7662.html#section-2.1).

Ví dụ dưới đây chỉ minh họa thông điệp; token và credential đều là giá trị giả:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.org
Authorization: Basic BASE64_CREDENTIALS_REDACTED
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=opaque-example-only&token_type_hint=access_token
```

Trong một tích hợp thật, HTTP client phải mã hóa form đúng cách. Không ghép trực tiếp một token tùy ý vào chuỗi request rồi giả định các ký tự đặc biệt không ảnh hưởng nội dung.

Giá trị `token_type_hint=access_token` hỗ trợ tra cứu, không phải bằng chứng token thật sự thuộc loại access token. Bên nhận vẫn phải tuân thủ hợp đồng về loại token; không coi việc gửi một hint là đã xác thực loại token đó.

Một response minh họa:

```json
{
  "active": true,
  "scope": "orders.read orders.update",
  "client_id": "order-portal",
  "sub": "employee-417",
  "aud": "urn:example:api:orders",
  "iss": "https://auth.example.org"
}
```

Ví dụ này cố ý không liệt kê mọi trường có thể xuất hiện. API cần biết hợp đồng dữ liệu của mình: trường nào được bên phát hành trả về, trường nào bắt buộc cho quyết định truy cập và cách xử lý khi thiếu.

Trong trường hợp token không active hoặc bên hỏi không được xem token cụ thể ấy, một response có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

HTTP `200` ở đây nói rằng yêu cầu introspection đã được xử lý, không có nghĩa access token được chấp nhận để truy cập API.

## 3. Diễn giải `active` đúng phạm vi

`active` phản ánh trạng thái token theo dữ liệu và quy tắc của Authorization Server, trong ngữ cảnh bên hỏi. Các kiểm tra có thể liên quan tới thời hạn, thu hồi và nơi token được sử dụng. Các metadata khác là tùy chọn trong chuẩn; không thể mặc định response nào cũng có đầy đủ `sub`, `aud`, `iss` hay `exp`. Xem [RFC 7662, mục 2.2 và 4](https://www.rfc-editor.org/rfc/rfc7662.html#section-2.2).

Khi thiết kế API, hãy xem `active: true` là một đầu vào đã xác thực qua kênh tin cậy, sau đó kiểm tra tiếp theo chính sách ứng dụng. Ví dụ, một token active chỉ có `orders.read` không đủ để sửa đơn hàng.

| Kết quả quan sát | Quyết định của API trong ví dụ |
|---|---|
| `active: false` | Không sử dụng token để cấp quyền |
| `active: true`, có `orders.read` | Có thể tiếp tục kiểm tra thao tác đọc |
| `active: true`, thiếu `orders.update` | Không cho phép thao tác cập nhật |
| `active: true`, dữ liệu tenant không phù hợp | Không truy cập đơn hàng của tenant khác |
| Thiếu `active` hoặc nhận chuỗi `"true"` thay boolean | Không coi là kết quả introspection hợp lệ |
| JSON hỏng hoặc response không đúng hợp đồng | Xử lý lỗi xác thực, không suy ra token active |

Không suy luận lý do cụ thể từ `active: false`. API có thể chưa phân biệt được token hết hạn, bị thu hồi, không tồn tại, gửi sai issuer hoặc nằm ngoài quyền xem của bên hỏi. Giao diện người dùng và log nội bộ không nên tự khẳng định một lý do mà response không cung cấp.

Một số thông tin cần hiểu theo hợp đồng triển khai:

- `scope` là phạm vi được cấp, không phải danh sách mọi quyền nghiệp vụ của người dùng.
- `client_id` nhận diện client liên quan tới việc yêu cầu token, không mặc nhiên là subject người dùng.
- `sub` cần được diễn giải trong đúng miền danh tính; workload không nên bị gắn nhầm thành tài khoản nhân viên.
- `aud` và `iss`, khi được sử dụng, phải phù hợp với resource server và cấu hình tin cậy.
- Các mốc thời gian như `exp` dùng đơn vị theo hợp đồng chuẩn, không được nhầm giây Unix với mili giây của một API lập trình.

Nếu API cần một dữ kiện để phân quyền nhưng Authorization Server không trả nó, hãy sửa hợp đồng tích hợp hoặc tìm nguồn chính sách phù hợp. Không tự điền một quyền mặc định rộng hơn chỉ để request đi tiếp.

## 4. Introspection khác decode và xác minh JWT tại chỗ

Ba thao tác thường bị đánh đồng nhưng có mục đích khác nhau:

| Thao tác | Kết quả chính | Giới hạn |
|---|---|---|
| Decode JWT | Đọc header và payload | Chưa chứng minh nguồn gốc hoặc tính hợp lệ |
| Xác minh JWT tại API | Đánh giá mật mã và ràng buộc token theo cấu hình | Không tự truy vấn mọi thay đổi trạng thái ở hệ thống cấp quyền |
| Introspection | Nhận thông tin trạng thái qua trao đổi với hệ thống có thẩm quyền | Phụ thuộc endpoint, dữ liệu trạng thái và chính sách cache |

Introspection không chỉ dành cho opaque token. Một Authorization Server cũng có thể hỗ trợ introspection cho token có cấu trúc. Ngược lại, không phải issuer phát JWT nào cũng cung cấp endpoint này hoặc theo dõi trạng thái từng token.

Lựa chọn kiến trúc cần dựa vào yêu cầu cụ thể. API có lưu lượng lớn và token ngắn hạn có thể ưu tiên xác minh tại chỗ. Một thao tác quản trị nhạy cảm có thể cần truy vấn trạng thái mới hơn hoặc kiểm tra chính sách trực tuyến. Đây là quyết định thiết kế, không phải quy tắc rằng mọi API phải gọi introspection ở mỗi request.

Nếu kết hợp hai cách, cần định nghĩa rõ vai trò từng kết quả. Không dùng JWT decode chưa xác thực để bổ sung quyền còn thiếu trong response introspection. Cũng không tự chuyển sang một chế độ kiểm tra yếu hơn khi endpoint introspection lỗi, trừ khi có thiết kế thay thế đã được đánh giá rõ về khả năng thu hồi và phạm vi truy cập.

## 5. Endpoint introspection là một phần của ranh giới tin cậy

API gửi token cho endpoint introspection, nên việc chọn đúng endpoint cũng là quyết định bảo vệ credential. Endpoint phải đến từ cấu hình hoặc metadata của hệ thống đã được phê duyệt, không lấy từ tham số request hay một URL do client tự chỉ định.

Các biện pháp triển khai cần phục vụ những mục tiêu rõ ràng:

| Mục tiêu | Biện pháp thiết kế |
|---|---|
| Gửi token tới đúng hệ thống | Cố định nguồn cấu hình endpoint và xác minh kết nối HTTPS |
| Chỉ dịch vụ được phép mới được hỏi | Credential riêng cho API, giới hạn quyền introspection |
| Hạn chế lộ token | Không đặt token trong URL, log hoặc tracing không được kiểm soát |
| Bảo vệ credential của API | Lưu trong hệ thống quản lý secret, có kế hoạch xoay vòng |
| Hạn chế dò token và quá tải | Rate limit, giới hạn kích thước request và kiểm soát concurrency |
| Giảm dữ liệu cá nhân bị lộ | Chỉ trả và chỉ lưu các trường cần cho resource server |

Bearer token cần được bảo vệ cả khi truyền và khi lưu vì bên sở hữu token có thể dùng nó để truy cập tài nguyên. Xem [RFC 6750, mục 5](https://www.rfc-editor.org/rfc/rfc6750.html#section-5).

Không gửi token thật lên công cụ decode hoặc chẩn đoán công cộng. Trong quá trình hỗ trợ sự cố, nên dùng correlation ID và mã lỗi; chỉ thu thập dữ liệu nhạy cảm khi có phạm vi lưu trữ, truy cập và thời hạn rõ ràng.

Quyền được gọi endpoint cũng nên tuân theo nguyên tắc ít quyền nhất. Một API chỉ cần đọc trạng thái token liên quan tới mình không nên được cấp quyền quản trị người dùng hoặc phát hành token mới chỉ để phục vụ introspection.

## 6. Cache tạo ra khoảng trễ nhìn thấy việc thu hồi

Gọi introspection ở mọi request làm tăng số kết nối và độ trễ. Cache kết quả có thể giảm chi phí, nhưng đồng thời kéo dài thời gian API dùng thông tin cũ. Nếu response có `exp`, không được giữ kết quả cache qua thời điểm đó. Xem [RFC 7662, mục 4](https://www.rfc-editor.org/rfc/rfc7662.html#section-4).

Xét một chính sách giả định có thời gian cache tối đa là 30 giây:

```text
10:00:00  API nhận active=true và lưu cache
10:00:05  Authorization Server ghi nhận thu hồi token
10:00:10  API dùng cache còn hạn, chưa biết việc thu hồi
10:00:30  Cache hết hạn; lần kiểm tra mới có thể thấy active=false
```

Khoảng trễ trong ví dụ là hệ quả của thiết kế cache, không phải bằng chứng endpoint introspection bị lỗi. Trong hệ thống phân tán thật, thời gian cập nhật dữ liệu trạng thái còn có thể ảnh hưởng kết quả.

Một công thức minh họa khi có `exp` là:

```text
cacheValidUntil = min(responseReceivedAt + maxCacheTTL, tokenExpiration)
```

Đây là chính sách cache của ví dụ, không phải một TTL cố định do OAuth quy định. Khi không có `exp`, cần một giới hạn cache hữu hạn đã được thiết kế; không được giữ `active: true` vĩnh viễn.

Một số chi tiết triển khai dễ bỏ sót:

- Ràng buộc cache với đúng Authorization Server, danh tính bên hỏi và ngữ cảnh tài nguyên có ảnh hưởng tới response.
- Không chia sẻ một kết quả giữa các tenant chỉ vì token có cùng dạng chuỗi.
- Bảo vệ cache như dữ liệu xác thực; token nguyên vẹn không nên xuất hiện trong metric label hoặc log khóa cache.
- Giới hạn dung lượng và thời gian sống của negative cache để token rác không làm đầy bộ nhớ.
- Gộp các lần tra cứu đồng thời cho cùng ngữ cảnh khi phù hợp để tránh nhiều request cache miss cùng gọi endpoint.
- Không tự gia hạn dữ liệu cache hết hạn chỉ vì mạng đang lỗi.

TTL phải phản ánh mức trễ thu hồi mà nghiệp vụ chấp nhận. Một giá trị hợp lý cho đọc danh mục công khai nội bộ có thể không phù hợp cho thao tác nâng đặc quyền hoặc chuyển tiền.

## 7. Phân biệt introspection, revocation và logout

Introspection hỏi trạng thái; revocation yêu cầu vô hiệu hóa token theo cơ chế được hỗ trợ. RFC 7009 định nghĩa endpoint thu hồi và lưu ý hệ thống phân tán có thể có độ trễ lan truyền trạng thái. Xem [RFC 7009, mục 2.1](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1).

Logout còn có thể chỉ kết thúc phiên tại một ứng dụng hoặc xóa cookie ở trình duyệt. Không thể mặc định một lần logout đã thu hồi mọi access token, mọi refresh token và mọi phiên ở các ứng dụng khác.

Ví dụ, khi nhân viên nghỉ việc, hệ thống cần phối hợp nhiều việc: vô hiệu hóa tài khoản theo chính sách, xử lý phiên và token, cập nhật quyền ở ứng dụng, và kiểm tra thời gian API còn dùng cache. Introspection chỉ giúp API nhìn thấy những thay đổi mà Authorization Server thực sự phản ánh vào trạng thái hoặc metadata.

Tương tự, xóa người dùng khỏi nhóm không chắc lập tức làm mọi access token thành inactive. Nếu hệ thống tiếp tục coi token cũ là active với scope cũ, API không thể tự suy ra quyền mới chỉ nhờ thêm một lời gọi introspection. Hợp đồng về cập nhật quyền phải được thiết kế và kiểm thử riêng.

## 8. Phân biệt token bị từ chối với dịch vụ kiểm tra gặp lỗi

Có ít nhất hai request HTTP trong luồng: client gọi API và API gọi introspection. Mã lỗi ở request thứ hai không được sao chép máy móc sang request thứ nhất.

| Tình huống | Ý nghĩa đối với API |
|---|---|
| Introspection trả `200` và `active: false` | Không dùng token để cấp quyền |
| Introspection từ chối credential của API | API chưa được xác thực đúng để hỏi; cần kiểm tra tích hợp |
| Timeout, DNS lỗi hoặc TLS lỗi | Chưa có kết luận hợp lệ về trạng thái token từ lần gọi này |
| `active: true` nhưng thiếu scope cần thiết | Token có thể active, nhưng thao tác không được cấp quyền |
| JSON response sai cấu trúc | Không thể sử dụng làm kết quả xác thực |

Với Bearer authentication ở API tài nguyên, RFC 6750 phân biệt `invalid_token`, thường đi với `401`, và `insufficient_scope`, thường đi với `403`. Xem [RFC 6750, mục 3.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-3.1). Một lỗi mạng khi hỏi introspection không tự chứng minh token đã bị thu hồi.

Về thiết kế vận hành, API nên giữ nguyên điều kiện xác thực: khi không có kết quả kiểm tra hợp lệ và cũng không có dữ liệu cache còn hiệu lực theo chính sách, không cấp quyền cho request chỉ vì hệ thống kiểm tra đang lỗi. Có thể trả lỗi phụ thuộc dịch vụ, chẳng hạn `503`, theo hợp đồng API; đây là lựa chọn vận hành, không phải giá trị `active: false` do Authorization Server trả về.

Timeout cần nằm trong ngân sách độ trễ của request. Retry phải có giới hạn và chỉ dùng khi phù hợp với loại lỗi; retry liên tục khi credential sai không giúp phục hồi và có thể làm quá tải hệ thống. Circuit breaker có thể hạn chế số lần gọi tới dependency đang lỗi, nhưng không phải lý do để bỏ qua kiểm tra token.

## 9. Áp dụng kết quả vào phân quyền của tài nguyên

Một request cập nhật đơn hàng có thể cần các điều kiện sau:

```text
Token được xác nhận active qua nguồn tin cậy
        AND phạm vi sử dụng phù hợp với API
        AND có scope orders.update
        AND subject thuộc tenant của đơn hàng
        AND chính sách cho phép sửa trạng thái đơn hàng hiện tại
```

Scope phải được xử lý như các giá trị riêng theo hợp đồng, không tìm bằng phép chứa chuỗi tùy ý. Ví dụ, chuỗi `orders.update-any` không được tự coi là `orders.update` chỉ vì có cùng tiền tố.

Một service có quyền đọc đơn hàng cũng không mặc nhiên có quyền đọc đơn hàng của mọi tenant. API cần kiểm tra ràng buộc tài nguyên sau khi đã xác thực token; trạng thái active không thay thế kiểm tra sở hữu, phân tách tenant hoặc yêu cầu phê duyệt.

Đối với thao tác đặc quyền, hãy xác định rõ thông tin nào đến từ token, thông tin nào đến từ nguồn chính sách hiện tại và yêu cầu độ mới của mỗi nguồn. Điều này giúp tránh tình trạng dùng kết quả introspection như một quyết định “allow” chung cho mọi endpoint.

## 10. Tự kiểm tra các trường hợp quan trọng

Với API đơn hàng dùng introspection, một bộ tình huống thiết kế nên bao gồm:

| Tình huống | Hành vi mong đợi |
|---|---|
| Token active, đúng ngữ cảnh, đủ scope và đúng tenant | Cho phép thao tác phù hợp |
| Token inactive nhưng introspection trả HTTP `200` | Từ chối token |
| API dùng credential introspection sai | Báo lỗi tích hợp, không cấp quyền bằng token chưa kiểm tra |
| Token active nhưng thiếu `orders.update` | Từ chối cập nhật |
| Response thiếu `active` hoặc sai kiểu dữ liệu | Không chấp nhận response làm bằng chứng xác thực |
| Token bị thu hồi trong lúc cache còn hạn | Hành vi đúng với khoảng trễ thu hồi đã công bố |
| Cache hết hạn và endpoint timeout | Không tự kéo dài quyền từ cache cũ |
| Response chứa dữ liệu khác nhau cho hai API | Cache không làm lẫn ngữ cảnh bên hỏi |
| Request chứa token rất lớn hoặc nhiều token ngẫu nhiên | Giới hạn tài nguyên xử lý và cache hoạt động |
| Người dùng logout nhưng token chưa được thu hồi | Không tuyên bố token đã vô hiệu nếu hệ thống chưa thực hiện việc đó |

Token introspection có giá trị khi được đặt trong một hợp đồng rõ ràng giữa API và Authorization Server: nguồn trạng thái nào có thẩm quyền, bên nào được hỏi, thông tin nào được trả, cache bao lâu và quyết định truy cập cần thêm những điều kiện gì. Hiểu được các điểm này giúp kiểm soát vòng đời quyền mà vẫn nhìn rõ chi phí về độ trễ và tính sẵn sàng.
