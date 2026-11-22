# Mô hình trưởng thành Richardson và giới hạn khi dùng để đánh giá REST

## Mục tiêu bài học

Trong chương **Ràng buộc REST** của module **INTEGRATION_API_REST**, bài học này giới thiệu **Richardson Maturity Model**, thường viết tắt là **RMM**, như một công cụ mô tả cách API sử dụng resource, ngữ nghĩa HTTP và hypermedia.

Sau bài học, bạn cần:

- Giải thích bốn mức từ 0 đến 3 bằng hành vi giao tiếp cụ thể.
- Phân biệt việc chia URI theo resource, dùng đúng HTTP và cung cấp hypermedia điều hướng ứng dụng.
- Nhận ra vì sao nhiều API được gọi là REST trong thực tế mới thể hiện các đặc điểm của mức 2.
- Tránh dùng mức Richardson làm chứng nhận tuân thủ toàn bộ REST hoặc thước đo duy nhất của chất lượng API.
- Áp dụng mô hình vào việc đọc, thiết kế và kiểm thử API với Java/Spring hoặc công nghệ tương đương.

Ví dụ xuyên suốt là một hệ thống **đặt chỗ phòng họp**. Cùng một nhu cầu nghiệp vụ sẽ được biểu đạt theo những cách khác nhau để thấy mô hình phân loại điều gì và bỏ sót điều gì.

## 1. Mô hình Richardson mô tả điều gì?

RMM thường được trình bày thành bốn mức:

| Mức | Đặc điểm nổi bật | Câu hỏi quan sát |
|---|---|---|
| 0 | Dùng HTTP chủ yếu để chuyển lời gọi hoặc thông điệp | Có một điểm vào nhận nhiều lệnh được mã hóa trong body không? |
| 1 | Nhận diện các resource bằng những URI riêng | Những khái niệm nghiệp vụ đã có định danh tài nguyên rõ ràng chưa? |
| 2 | Sử dụng ngữ nghĩa phương thức và mã trạng thái HTTP | Ý định và kết quả có được thể hiện đúng ở lớp HTTP không? |
| 3 | Sử dụng hypermedia controls | Client có thể theo các liên kết và điều khiển được cung cấp trong representation để thực hiện bước tiếp theo không? |

Cách trình bày này hữu ích khi một nhóm đang nói chung chung rằng “API đã RESTful”. Nó buộc cuộc thảo luận chuyển sang những điều có thể quan sát trong request, response và cách client sử dụng chúng.

Tuy nhiên:

- Đây không phải bốn phiên bản của đặc tả REST.
- Không có một chứng nhận REST tự động chỉ dựa vào việc gán mức 3.
- Các mức không phải lộ trình bắt buộc mà mọi sản phẩm đều phải đi qua.
- Mức cao hơn trong mô hình không tự chứng minh API phù hợp hơn với mọi bài toán.

REST là một phong cách kiến trúc với nhiều ràng buộc. RMM tập trung vào một số khía cạnh của giao diện và cách khai thác HTTP; nó không kiểm tra đầy đủ mọi ràng buộc kiến trúc.

## 2. Bối cảnh ví dụ: đặt chỗ phòng họp

Client cần thực hiện ba việc:

1. Tìm những khung giờ còn trống của một phòng.
2. Đặt chỗ cho một khung giờ.
3. Hủy một lượt đặt chỗ nếu trạng thái và quyền hiện tại cho phép.

Các khái niệm nghiệp vụ gồm:

- Phòng họp: `room`.
- Khung giờ: `slot`.
- Lượt đặt chỗ: `reservation`.
- Yêu cầu hoặc bản ghi hủy: `cancellation`.

Giả sử phòng có ID 17, khung giờ có ID 731 và lượt đặt chỗ được tạo có ID 204.

Các URI, media type và relation mở rộng trong bài là quy ước minh họa của API. Chúng cần được định nghĩa trong hợp đồng thực tế; không phải cứ dùng đúng những tên này thì hệ thống tự đạt một mức nào đó.

## 3. Mức 0: HTTP làm kênh chuyển lời gọi

Ở mức 0, một cách thiết kế thường gặp là gửi nhiều thao tác tới cùng một endpoint, thường dùng `POST`. Tên thao tác và tham số nằm trong body.

Tìm khung giờ:

~~~http
POST /booking-api HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "operation": "findAvailableSlots",
  "roomId": 17,
  "date": "2026-12-01"
}
~~~

Đặt chỗ:

~~~http
POST /booking-api HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "operation": "reserveSlot",
  "slotId": 731
}
~~~

Một kết quả có thể được trả như sau:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": true,
  "result": {
    "reservationId": 204
  }
}
~~~

Trong thiết kế này, phần lớn ý nghĩa giao tiếp nằm trong cấu trúc thông điệp riêng. Client phải biết `operation` nào tồn tại và cách giải mã `success`, `result` hoặc lỗi trong body.

### 3.1. Điều mô hình chỉ ra

- HTTP đang được dùng như kênh chuyển một giao thức lời gọi riêng.
- Các khái niệm nghiệp vụ chưa nhất thiết được nhận diện bằng URI riêng.
- Ngữ nghĩa đọc, tạo và lỗi có thể chưa được tận dụng ở lớp HTTP.

JSON hay XML không quyết định mức. Đổi body từ XML sang JSON vẫn có thể giữ nguyên cách tổ chức này.

### 3.2. Không dùng mức 0 để kết luận “không có giá trị”

Một giao diện RPC có thể có hợp đồng rõ, bảo mật tốt và đáp ứng đúng một nhu cầu tích hợp. RMM mô tả cách giao diện đó liên hệ với một số đặc điểm REST, không phải phán quyết rằng phần mềm vô dụng.

Tương tự, việc thấy một request `POST` không đủ để gán mức 0. Cần nhìn cách tổ chức toàn bộ tương tác: endpoint đích, ngữ nghĩa và representation.

## 4. Mức 1: resource có URI riêng

Ở mức 1, API bắt đầu tách các resource và nhận diện chúng bằng URI.

Ví dụ:

~~~text
/rooms/17
/rooms/17/slots
/slots/731
/reservations/204
~~~

Nhưng API vẫn có thể gửi mọi thao tác qua `POST` và giữ tên lệnh trong body.

Tìm khung giờ:

~~~http
POST /rooms/17/slots HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "operation": "findAvailable",
  "date": "2026-12-01"
}
~~~

Đặt khung giờ:

~~~http
POST /slots/731 HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "operation": "reserve"
}
~~~

Các request này minh họa đặc điểm phân loại của mức 1, không phải đề xuất dùng `POST` cho mọi thao tác trong thiết kế mới.

### 4.1. Giá trị của việc nhận diện resource

Client có thể tham chiếu đến một phòng, một khung giờ hoặc một lượt đặt cụ thể, thay vì chỉ gọi những tên hàm trên một endpoint chung.

Phía server cũng có thể định tuyến, ghi nhận và áp dụng một số chính sách theo resource rõ hơn.

Tuy nhiên, nếu mọi thao tác vẫn được mã hóa trong body, công cụ HTTP và thành phần trung gian chưa tận dụng được đầy đủ ý định đọc hoặc ghi.

### 4.2. Chia nhiều URL chưa đủ để là REST

Tách một endpoint thành hàng chục URL theo tên hàm chưa tự tạo ra một mô hình resource nhất quán.

Ví dụ:

~~~text
/findRoom
/getRoomDetail
/createReservation
/cancelReservation
~~~

Các URL có thể tiện dùng, nhưng chỉ đếm số URL hoặc đổi tên chúng thành danh từ không đủ để đánh giá kiến trúc.

Điều cần xem là resource đại diện cho khái niệm nào, được định danh ra sao và client tương tác với nó bằng hợp đồng gì.

## 5. Mức 2: sử dụng ngữ nghĩa HTTP

Ở mức 2, API tiếp tục sử dụng resource và khai thác phương thức, mã trạng thái cùng những đặc điểm liên quan của HTTP một cách phù hợp.

### 5.1. Đọc khung giờ bằng GET

~~~http
GET /rooms/17/slots?date=2026-12-01 HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "slots": [
    {
      "id": 731,
      "startsAt": "2026-12-01T09:00:00+07:00",
      "endsAt": "2026-12-01T10:00:00+07:00",
      "available": true
    }
  ]
}
~~~

Request thể hiện ý định đọc. Server không nên tạo một lượt đặt chỗ chỉ vì client đọc danh sách.

Các hoạt động phụ như ghi log không làm `GET` mất tính safe; điều cần tránh là gắn tác động thay đổi nghiệp vụ vào ý định đọc.

### 5.2. Tạo lượt đặt chỗ bằng POST

~~~http
POST /reservations HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "slotId": 731
}
~~~

~~~http
HTTP/1.1 201 Created
Location: /reservations/204
Content-Type: application/json

{
  "id": 204,
  "slotId": 731,
  "status": "CONFIRMED"
}
~~~

Ở đây:

- `POST` yêu cầu tập resource xử lý nội dung để tạo lượt đặt.
- `201` thông báo đã tạo resource.
- `Location` chỉ URI của lượt đặt vừa tạo.
- Body biểu diễn kết quả theo hợp đồng dữ liệu.

Client muốn đọc lại có thể gọi `GET /reservations/204`.

### 5.3. Lỗi có ngữ nghĩa ở lớp HTTP

Nếu khung giờ đã được người khác đặt, API có thể quy định:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "SLOT_ALREADY_RESERVED",
  "message": "Khung giờ đã được đặt. Vui lòng chọn khung giờ khác."
}
~~~

`409` thể hiện xung đột với trạng thái hiện tại trong hợp đồng minh họa. Trường `code` giúp client phân biệt lỗi nghiệp vụ cụ thể.

Việc trả mã này không tự ngăn hai người cùng đặt chỗ. Server vẫn phải bảo vệ thao tác tạo bằng transaction, ràng buộc hoặc cơ chế kiểm soát đồng thời phù hợp.

### 5.4. Mức 2 không bắt buộc dùng đủ mọi phương thức

Một resource không nhất thiết cần cả `GET`, `POST`, `PUT`, `PATCH` và `DELETE`. Chỉ cung cấp những thao tác có ý nghĩa trong hợp đồng.

Nếu nghiệp vụ cần lưu một bản ghi hủy và áp dụng quy tắc hủy riêng, có thể thiết kế:

~~~http
POST /reservations/204/cancellations HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "reason": "Không còn nhu cầu sử dụng phòng."
}
~~~

Đây là một lựa chọn mô hình hóa cancellation thành resource, không phải hành vi bắt buộc cho mọi API.

Không nên ép mọi chuyển trạng thái nghiệp vụ thành CRUD chỉ để làm giao diện trông giống một bảng phương thức.

## 6. Mức 3: hypermedia hướng dẫn các bước tiếp theo

Ở mức 2, client thường biết trước một số mẫu URI và tự quyết định cách gọi bước tiếp theo từ tài liệu hoặc mã đã viết.

Ở mức 3, representation còn cung cấp **hypermedia controls** để client tìm và thực hiện những tương tác phù hợp với trạng thái hiện tại.

Khía cạnh này thường được gọi là **HATEOAS**: Hypermedia as the Engine of Application State.

“Application state” ở đây nói đến tiến trình tương tác của client qua các representation và điều khiển nhận được. Nó không có nghĩa server phải giữ một phiên hội thoại ngầm, cũng không đồng nhất với các dòng dữ liệu nghiệp vụ trong cơ sở dữ liệu.

### 6.1. Liên kết và điều khiển thao tác

Giả sử response lượt đặt chỗ sử dụng một media type mở rộng của API:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.example.reservation+json

{
  "id": 204,
  "status": "CONFIRMED",
  "slotId": 731,
  "links": [
    {
      "rel": "self",
      "href": "/reservations/204"
    },
    {
      "rel": "https://api.example.com/rels/room",
      "href": "/rooms/17"
    }
  ],
  "actions": [
    {
      "rel": "https://api.example.com/rels/cancel-reservation",
      "href": "/reservations/204/cancellations",
      "method": "POST",
      "contentType": "application/json",
      "fields": [
        {
          "name": "reason",
          "type": "string",
          "required": false
        }
      ]
    }
  ]
}
~~~

Định dạng trên là minh họa, không phải một chuẩn hypermedia chung. Hợp đồng media type cần định nghĩa cách hiểu `links`, `actions`, `rel`, `fields` và những thành phần liên quan.

Các URI dùng làm relation mở rộng là định danh ý nghĩa quan hệ trong ví dụ; không nên nhầm chúng với URI đích của thao tác. URI thao tác nằm ở `href`.

Client hiểu relation hủy có thể:

1. Đọc representation hiện tại.
2. Tìm action mang relation hủy mà nó hỗ trợ.
3. Lấy URI, method, media type và thông tin input theo hợp đồng.
4. Hiển thị lựa chọn phù hợp cho người dùng.
5. Gửi request đến URI được cung cấp.
6. Tiếp tục dựa trên representation hoặc kết quả nhận được.

Client không phải tự ghép `"/reservations/" + id + "/cancellations"` nếu hợp đồng đã cung cấp đích tương tác.

### 6.2. Controls có thể thay đổi theo trạng thái và quyền

Sau khi lượt đặt bị hủy, representation có thể là:

~~~json
{
  "id": 204,
  "status": "CANCELLED",
  "slotId": 731,
  "links": [
    {
      "rel": "self",
      "href": "/reservations/204"
    }
  ],
  "actions": []
}
~~~

Client không nhận một action hủy nữa vì hành động đó không còn phù hợp trong trạng thái đang được biểu diễn.

Tương tự, cùng một lượt đặt có thể cung cấp các controls khác nhau cho người sở hữu và một người chỉ có quyền xem, nếu hợp đồng cho phép biểu diễn theo quyền.

Điều này hỗ trợ giao diện thích ứng với khả năng hiện tại, nhưng không thay thế kiểm tra quyền tại endpoint. Người gọi vẫn có thể tự tạo request, hoặc action đã được nhận có thể trở nên lỗi thời trước khi được sử dụng.

Server phải kiểm tra lại trạng thái, quyền và điều kiện cạnh tranh khi thực hiện thao tác.

### 6.3. Thêm một mảng links chưa đủ

Những trường hợp sau chưa chứng minh đã có đầy đủ tương tác hypermedia:

- Chỉ thêm `self` rồi client vẫn hard-code mọi URI nghiệp vụ.
- Thêm các link không có relation hoặc quy tắc giải nghĩa rõ ràng.
- Trả một URL hủy nhưng không có cách xác định method và input theo hợp đồng.
- Liệt kê mọi thao tác bất kể trạng thái hiện tại, còn client tự suy diễn toàn bộ quy tắc.
- Trả controls nhưng không có client nào dùng chúng trong luồng đang đánh giá.

Liên kết `self`, link phân trang hoặc `Location` đều hữu ích. Một vài liên kết riêng lẻ không tự chứng minh các chuyển trạng thái ứng dụng được dẫn dắt bằng hypermedia.

Mô tả đánh giá nên chỉ rõ khả năng nào đã có: “có link phân trang”, “có controls hủy theo trạng thái”, hoặc “client theo relation để tiếp tục luồng”, thay vì gắn nhãn mức 3 chỉ vì JSON có trường `links`.

## 7. Hypermedia giảm loại phụ thuộc nào?

Giả sử server thay đổi URI đích hủy từ:

~~~text
/reservations/204/cancellations
~~~

sang:

~~~text
/reservation-workflows/204/cancellation-requests
~~~

Nếu client theo `href` của relation hủy, còn ngữ nghĩa relation và hợp đồng input vẫn tương thích, client có thể không phải thay đổi cách dựng đường dẫn.

Tuy nhiên, client vẫn cần hiểu:

- URI khởi đầu hoặc cách tìm điểm vào API.
- Media type và cấu trúc representation.
- Ý nghĩa các relation mà nó sử dụng.
- Những trường dữ liệu có ý nghĩa nghiệp vụ.
- Cách xác thực, xử lý lỗi và thương lượng nội dung.
- Cách xử lý relation hoặc dữ liệu mới chưa biết.

Hypermedia không làm client tự hiểu mọi nghiệp vụ chưa từng được lập trình. Một action mới không tự khiến ứng dụng biết cách thiết kế trải nghiệm người dùng cho tác vụ hoàn toàn mới.

Khả năng tiến hóa cũng có giới hạn. Nếu relation “hủy lượt đặt” bị đổi nghĩa thành “chuyển quyền sở hữu”, giữ nguyên tên relation không bảo vệ được client. Thay đổi ý nghĩa, điều kiện hoặc input vẫn có thể phá vỡ hợp đồng.

## 8. Vì sao mức 3 chưa phải chứng nhận REST đầy đủ?

REST bao gồm những ràng buộc rộng hơn các dấu hiệu mà RMM thường dùng để phân mức.

| Khía cạnh | RMM giúp quan sát đến đâu? | Điều còn phải đánh giá |
|---|---|---|
| Nhận diện resource | Thể hiện rõ từ mức 1 | Ranh giới resource và sự ổn định của định danh có phù hợp không |
| Ngữ nghĩa HTTP | Là trọng tâm mức 2 | Hành vi thực tế có đúng safe, idempotent, status và điều kiện HTTP không |
| Hypermedia | Là trọng tâm mức 3 | Client có thể sử dụng controls đúng hợp đồng trong những luồng nào |
| Thông điệp tự mô tả | Có liên quan tới method, media type và controls | Metadata và hợp đồng có đủ rõ để xử lý thông điệp không |
| Client–server | Không được xác nhận đầy đủ bằng một mức | Trách nhiệm và khả năng phát triển độc lập có rõ không |
| Stateless | Không có mức riêng để kiểm chứng | Mỗi request có đủ ngữ cảnh hay phụ thuộc hội thoại ngầm trên server |
| Cache | Có thể xuất hiện khi tận dụng HTTP | Response có chính sách freshness, validator và quyền lưu phù hợp không |
| Layered system | Không được chứng minh bằng số mức | Client có phụ thuộc topology phía sau hoặc làm mất ngữ nghĩa qua trung gian không |
| Code on demand | Không phải thước đo của các mức | Đây là ràng buộc tùy chọn của REST; không cần có để đạt REST |

Ví dụ, API có những action hypermedia rất rõ nhưng:

- Server bắt buộc nhớ một lựa chọn ngầm trong session từ request trước.
- Proxy làm mất điều kiện cập nhật `If-Match`.
- Response cá nhân bị shared cache trả nhầm người.
- Client phải biết địa chỉ nội bộ của từng service để hoàn tất luồng.

Các vấn đề này cần được đánh giá trực tiếp; một nhãn mức 3 không giải quyết chúng.

Ngược lại, API không cache được một loại dữ liệu nhạy cảm không tự vi phạm REST. Điều quan trọng là có chính sách cache đúng, có thể bao gồm việc cấm lưu, chứ không phải bắt mọi response đều có cache hit.

## 9. Những giới hạn khác của mô hình

### 9.1. Không phải thang điểm chất lượng tổng thể

RMM không trực tiếp chấm:

- Độ trễ và thông lượng.
- Độ tin cậy khi một dịch vụ phụ thuộc lỗi.
- Khả năng chống thao tác trùng do retry.
- Tính đúng đắn của giao dịch và kiểm soát đồng thời.
- Xác thực, phân quyền và bảo vệ dữ liệu.
- Chất lượng tài liệu, vận hành và hỗ trợ client.

Một API mức 2 được thiết kế cẩn thận có thể phục vụ nhu cầu sản phẩm tốt hơn một API có controls hypermedia nhưng hợp đồng khó hiểu, lỗi không nhất quán và phân quyền sai.

Đây không phải lý do bỏ qua hypermedia; nó cho thấy cần đánh giá nhiều chiều.

### 9.2. Không nên gán mức cho toàn hệ thống từ một endpoint

Một API có thể gồm:

- Catalog dùng resource và đúng HTTP.
- Một endpoint nhập dữ liệu hàng loạt theo giao thức riêng.
- Một luồng đặt chỗ có hypermedia.
- Một phần cũ vẫn dùng endpoint lệnh chung.

Gọi cả hệ thống là mức 3 chỉ vì một response có controls sẽ che khuất khác biệt.

Nên ghi rõ phạm vi:

> Luồng đọc và hủy lượt đặt chỗ có controls theo trạng thái; luồng tìm khung giờ dùng resource và HTTP nhưng client vẫn biết trước cách xây query.

Cách mô tả này hữu ích hơn một số mức không kèm bằng chứng.

### 9.3. Không phải quy tắc chỉ nhìn hình thức URI

URI danh từ không tự bảo đảm resource được thiết kế tốt. URI có một từ mang tính hành động cũng chưa đủ để kết luận toàn bộ hệ thống không theo REST.

Cần xem URI nhận diện điều gì, method có ngữ nghĩa gì, request/response thể hiện hợp đồng ra sao và client sử dụng thông tin đó thế nào.

Tương tự, không nên gán mức 2 chỉ vì source code có đủ annotation `@GetMapping`, `@PostMapping` và `@DeleteMapping`. Một `GET` thay đổi nghiệp vụ vẫn sai ngữ nghĩa dù tên annotation đúng.

### 9.4. Không thay thế quyết định về chi phí

Hypermedia có chi phí:

- Thiết kế và duy trì relation, media type hoặc quy ước controls.
- Tạo representation theo trạng thái và quyền.
- Tăng metadata trong response.
- Phát triển client thực sự tiêu thụ controls.
- Kiểm thử sự tương thích của các luồng.
- Quản lý cache khi controls thay đổi theo người gọi hoặc trạng thái.

Những chi phí này cần được cân nhắc cùng lợi ích giảm phụ thuộc vào cấu trúc URI và hỗ trợ các tương tác được phát hiện khi chạy.

Không cần thêm một lớp `links` chỉ để nâng nhãn nếu nhóm chưa xác định client sẽ dùng nó như thế nào. Cũng không nên giả định hypermedia không có giá trị chỉ vì client hiện tại còn hard-code đường dẫn.

### 9.5. Không thay thế OpenAPI hoặc tài liệu hợp đồng

OpenAPI có thể mô tả đường dẫn, phương thức, schema, lỗi và nhiều thông tin về tương tác. Nó chủ yếu phục vụ việc mô tả hợp đồng; bản thân sự tồn tại của một tài liệu không chứng minh client đang được dẫn dắt bằng controls trong các representation thực tế.

Ngược lại, hypermedia không làm tài liệu trở nên thừa. Client vẫn cần hiểu media type, relation và dữ liệu.

Cần phân biệt thông tin mô tả những khả năng của API với controls phản ánh những tương tác đang được cung cấp trong một representation cụ thể.

## 10. Liên hệ với Java/Spring

Có thể tạo representation bằng DTO thông thường hoặc dùng thư viện hỗ trợ hypermedia. Công cụ có thể giúp biểu diễn link, nhưng không tự quyết định ngữ nghĩa resource, quyền hay trạng thái nghiệp vụ.

Ví dụ dưới đây minh họa một factory dựng DTO theo trạng thái và quyền. Đoạn mã dùng Java có hỗ trợ `record`; các đường dẫn giả định API công khai nằm ở gốc URI.

~~~java
import java.util.List;

public final class ReservationRepresentationFactory {

    private ReservationRepresentationFactory() {
    }

    public static ReservationView create(
        long id,
        String status,
        boolean allowedToCancel
    ) {
        String selfUri = "/reservations/" + id;

        List<LinkView> links =
            List.of(new LinkView("self", selfUri));

        List<ActionView> actions = List.of();

        if ("CONFIRMED".equals(status) && allowedToCancel) {
            actions = List.of(
                new ActionView(
                    "https://api.example.com/rels/cancel-reservation",
                    selfUri + "/cancellations",
                    "POST",
                    "application/json",
                    List.of(new FieldView("reason", "string", false))
                )
            );
        }

        return new ReservationView(id, status, links, actions);
    }

    public record ReservationView(
        long id,
        String status,
        List<LinkView> links,
        List<ActionView> actions
    ) {
    }

    public record LinkView(String rel, String href) {
    }

    public record ActionView(
        String rel,
        String href,
        String method,
        String contentType,
        List<FieldView> fields
    ) {
    }

    public record FieldView(
        String name,
        String type,
        boolean required
    ) {
    }
}
~~~

DTO được rút gọn để tập trung vào controls, không lặp lại toàn bộ dữ liệu phòng và khung giờ.

Trong ứng dụng Spring MVC:

- Tầng nghiệp vụ xác định trạng thái và quyền từ dữ liệu tin cậy.
- Factory dựng representation; `allowedToCancel` không được lấy trực tiếp từ tham số do người gọi tùy ý khai báo.
- Controller trả dữ liệu cùng mã HTTP và `Content-Type` phù hợp với hợp đồng.
- Endpoint thực hiện hủy vẫn kiểm tra quyền, trạng thái và cạnh tranh đồng thời.
- Cách tạo URI phải phù hợp host/tiền tố công khai khi đi qua proxy hoặc gateway.

`@RestController`, một lớp có tên `Resource` hay một thư viện tạo link không tự xác nhận mức 3. Cần xem representation thực tế và hành vi client.

Nếu response có controls theo quyền, chính sách cache cũng phải được thiết kế để không tái sử dụng controls hoặc dữ liệu của người này cho người khác.

## 11. Cách dùng RMM để đánh giá một luồng cụ thể

Có thể thực hiện một đánh giá ngắn theo trình tự sau.

### Bước 1: xác định phạm vi

Chọn một hành trình, chẳng hạn tìm khung giờ → đặt chỗ → xem → hủy. Nêu rõ loại client và người dùng được khảo sát.

Không bắt đầu bằng việc tìm một con số cho cả hệ thống.

### Bước 2: ghi lại bằng chứng request/response

Với mỗi bước, ghi:

- URI đích.
- Method.
- Mã trạng thái.
- Header có ý nghĩa.
- Schema và media type.
- Link, relation hoặc action được cung cấp.
- Cách client biết bước tiếp theo.

Không chỉ xem tên controller hoặc ảnh chụp giao diện tài liệu.

### Bước 3: đối chiếu với những đặc điểm của mô hình

Ví dụ:

| Quan sát | Nhận xét có thể đưa ra |
|---|---|
| Mọi lệnh vào `POST /booking-api` | Có đặc điểm mức 0 trong luồng đang xem |
| Từng phòng, khung giờ và lượt đặt có URI riêng | Đã thể hiện đặc điểm resource của mức 1 |
| Đọc bằng GET, tạo trả 201, lỗi thể hiện qua HTTP phù hợp | Có những đặc điểm mức 2 |
| Client tìm action hủy theo relation và dùng URI được trả về | Có bằng chứng về tương tác hypermedia của mức 3 |

Kết luận cần theo đúng phạm vi bằng chứng. Không suy từ “có URI resource” sang “đã tuân thủ mọi ngữ nghĩa HTTP”.

### Bước 4: đánh giá riêng các ràng buộc REST còn lại

Kiểm tra stateless, cache, layered system và những khía cạnh khác của uniform interface. Những nội dung này không thể bỏ qua chỉ vì đã nhận diện hypermedia.

### Bước 5: đánh giá chất lượng phù hợp sản phẩm

Xem quyền truy cập, hợp đồng dữ liệu, độ trễ, phân trang, retry, concurrency, lỗi và khả năng kiểm thử.

Kết quả nên dẫn tới một thay đổi cụ thể, ví dụ:

> Giữ luồng đọc hiện tại; sửa thao tác ghi qua GET; chuẩn hóa lỗi 409; bổ sung controls hủy theo quyền cho client có nhu cầu dùng; kiểm tra độc lập chính sách cache.

Đây là kết quả có thể triển khai và kiểm chứng, thay vì mục tiêu mơ hồ “nâng API lên mức 3”.

## 12. Kiểm thử những điều mô hình dễ bị dùng sai

| Tình huống kiểm thử | Điều cần xác nhận |
|---|---|
| Gọi GET danh sách nhiều lần | Không tạo lượt đặt hoặc gây tác động nghiệp vụ của thao tác ghi |
| Tạo lượt đặt hợp lệ | Mã 201 và Location nhất quán với resource đã tạo |
| Hai người cùng đặt một slot | Quy tắc chống đặt trùng được bảo vệ ở server |
| Đọc lượt đặt còn được phép hủy | Có control hủy theo hợp đồng |
| Đọc lượt đặt đã hủy hoặc không có quyền | Controls phản ánh khả năng theo hợp đồng, không làm lộ dữ liệu trái quyền |
| Tự gửi request hủy dù không có action | Server vẫn thực thi kiểm tra quyền và nghiệp vụ |
| Client nhận action rồi trạng thái thay đổi | Thao tác được kiểm tra lại, lỗi xung đột được xử lý rõ |
| Đổi URI hủy nhưng giữ relation và input tương thích | Client theo link vẫn hoạt động nếu không phụ thuộc mẫu URI cũ |
| Thêm relation mới | Client xử lý phần chưa biết theo chính sách tương thích của hợp đồng |
| Gửi lại request tạo sau timeout | Cơ chế idempotency hoạt động theo thiết kế, độc lập với nhãn RMM |

Nếu muốn chứng minh lợi ích của hypermedia, phép thử đổi URI đích có giá trị hơn việc chỉ kiểm tra trường `links` không rỗng.

Nếu muốn chứng minh tuân thủ REST rộng hơn, vẫn cần kiểm tra các ràng buộc kiến trúc khác. Nếu muốn chứng minh hệ thống an toàn và đáng tin cậy, cần thêm những phép thử tương ứng; mô hình không thay thế chúng.

## 13. Tự kiểm tra

### Câu hỏi

1. API dùng một endpoint POST và JSON có trường `operation`. Chỉ đổi JSON sang XML có làm mức Richardson tăng không?
2. API có nhiều URI resource nhưng mọi thao tác đều dùng POST. Nó đã thể hiện đầy đủ đặc điểm mức 2 chưa?
3. API dùng GET để đọc, POST để tạo, trả mã HTTP phù hợp và có Location. Chỉ từ đó có thể khẳng định đã đạt hypermedia mức 3 không?
4. Response có link `self`, nhưng client hard-code toàn bộ URI của những bước tiếp theo. Vì sao chưa đủ bằng chứng về HATEOAS?
5. Có action hủy trong response có thay thế kiểm tra phân quyền khi thực hiện hủy không?
6. API có hypermedia nhưng vẫn cần session hội thoại ngầm để diễn giải request. Mức 3 có xóa vấn đề stateless này không?
7. Một endpoint có controls phong phú. Có nên gán cả hệ thống mức 3 ngay không?
8. OpenAPI và một thư viện tạo link có tự chứng nhận toàn bộ hệ thống tuân thủ REST không?

### Gợi ý trả lời

1. Không. Định dạng dữ liệu khác với cách tổ chức resource, ngữ nghĩa HTTP và hypermedia.
2. Chưa. Việc nhận diện resource là một bước; cần đánh giá ngữ nghĩa phương thức và kết quả ở HTTP.
3. Không. Location hữu ích cho resource mới, nhưng cần xem các chuyển trạng thái tiếp theo có được dẫn dắt bằng controls theo hợp đồng hay không.
4. Vì sự tồn tại của một link không chứng minh client sử dụng hypermedia để điều hướng luồng ứng dụng.
5. Không. Action có thể cũ hoặc người gọi có thể tự tạo request; server vẫn phải kiểm tra lại.
6. Không. Stateless là ràng buộc phải đánh giá riêng; nhãn mức không sửa hành vi phụ thuộc hội thoại ngầm.
7. Không. Cần xác định phạm vi và đánh giá các luồng tương tác thực tế, có thể tồn tại nhiều cách thiết kế trong cùng hệ thống.
8. Không. Công cụ và tài liệu hỗ trợ triển khai; sự tuân thủ cần được đánh giá từ kiến trúc và hành vi thực tế.

Khi dùng RMM trong một cuộc review, hãy nêu rõ **luồng nào đang được xem, bằng chứng nào thể hiện từng đặc điểm, và những vấn đề nào nằm ngoài mô hình**. Cách dùng đó giúp nhóm bàn về thiết kế REST chính xác hơn mà vẫn giữ trọng tâm ở nhu cầu và chất lượng thực tế của API.
