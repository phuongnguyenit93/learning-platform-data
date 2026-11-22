# Ưu điểm, chi phí và giới hạn của REST

## Mục tiêu bài học

Trong chương **Tổng quan** của module **INTEGRATION_API_REST**, bài học này giúp bạn đánh giá REST như một lựa chọn kiến trúc có điều kiện áp dụng, lợi ích và chi phí cụ thể.

Sau bài học, bạn cần có khả năng:

- Giải thích vì sao giao diện hướng resource và việc dùng đúng HTTP có thể giúp các hệ thống tích hợp dễ hơn.
- Nhận diện phần công việc vẫn phải tự thiết kế: hợp đồng dữ liệu, phân trang, cache, idempotency, bảo mật, xử lý lỗi và kiểm thử.
- Phân tích chi phí về số request, độ trễ, lượng dữ liệu và vận hành.
- Nhận ra những bài toán cần bổ sung cơ chế bất đồng bộ, giao tiếp thời gian thực hoặc một kiểu giao diện khác.
- Đề xuất một phương án phù hợp với tình huống, thay vì chọn REST chỉ vì quen dùng controller trả JSON.

Các ví dụ xoay quanh một hệ thống bán hàng và có thể triển khai bằng Java/Spring hoặc công nghệ tương đương. Các con số trong bài là giả định để phân tích, không phải kết quả benchmark.

## 1. Cần đánh giá điều gì khi chọn REST?

Một API tốt cần phục vụ nhu cầu của client và vẫn có thể phát triển, vận hành lâu dài. Câu hỏi không chỉ là “REST có dễ viết không?” mà còn là:

1. Client cần đọc hoặc thay đổi những resource nào?
2. Mỗi màn hình hoặc tác vụ cần bao nhiêu lượt trao đổi?
3. Dữ liệu được phép cũ trong bao lâu?
4. Request có thể được gửi lại không, và gửi lại gây hậu quả gì?
5. Có nhiều người cùng cập nhật một resource không?
6. Luồng nghiệp vụ hoàn tất ngay hay kéo dài qua nhiều hệ thống?
7. Ai sử dụng API, ai có quyền xem hoặc sửa từng phần dữ liệu?
8. Client và server có thể nâng cấp độc lập đến mức nào?

REST cung cấp các ràng buộc kiến trúc, trong đó có stateless, cache và uniform interface. Khi triển khai trên HTTP, hệ thống có thể sử dụng phương thức, mã trạng thái, header và cơ chế trung gian của HTTP.

Những thành phần này tạo nền tảng thuận lợi. Chúng không tự giải quyết mọi quyết định về dữ liệu, nghiệp vụ hoặc hệ thống phân tán.

| Đặc điểm | Lợi ích có thể đạt được | Điều kiện và chi phí đi kèm |
|---|---|---|
| Resource có định danh rõ | Client có điểm truy cập ổn định và dễ hiểu | Phải chọn ranh giới resource và hợp đồng phù hợp |
| Giao diện HTTP thống nhất | Tái sử dụng ngữ nghĩa method, status và header | Phải dùng chúng nhất quán, tránh quy ước riêng gây mâu thuẫn |
| Tương tác stateless | Dễ phân phối request giữa các instance hơn | Mỗi request cần đủ ngữ cảnh; dữ liệu và trạng thái dùng chung vẫn phải được quản lý |
| Response có chính sách cache | Giảm tải, giảm độ trễ khi tái sử dụng được dữ liệu | Phải xác định freshness, quyền truy cập, biến thể response và cách cập nhật |
| Trao đổi representation | Client ít phụ thuộc vào cấu trúc lưu trữ bên trong | Phải thiết kế DTO, schema và cách phát triển hợp đồng |
| Khả năng đi qua nhiều lớp | Thuận lợi cho proxy, gateway và cân bằng tải | Tăng yêu cầu về cấu hình, quan sát và xử lý lỗi qua các lớp |

Không phải API nào gắn nhãn REST cũng đạt các lợi ích trong bảng. Ví dụ, một API luôn trả `200` cho cả lỗi hoặc dùng `GET` để ghi dữ liệu sẽ làm suy yếu khả năng tận dụng ngữ nghĩa HTTP.

## 2. Ưu điểm: một giao diện dễ chia sẻ giữa nhiều loại client

### 2.1. Client không phải dùng cùng ngôn ngữ với server

Một ứng dụng Java/Spring có thể cung cấp API cho trình duyệt, ứng dụng di động, tác vụ tích hợp hoặc một dịch vụ viết bằng ngôn ngữ khác.

Ví dụ, đọc một đơn hàng:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

Client cần hiểu hợp đồng HTTP và dữ liệu, không cần biết server dùng JPA, JDBC hay lưu dữ liệu bằng cách nào.

Sự tách biệt này hỗ trợ thay đổi nội bộ. Server có thể thay cách lưu trữ trong khi giữ nguyên hành vi đã cam kết với client.

Chi phí tương ứng là hợp đồng công khai phải được xem như một sản phẩm cần duy trì. Một thay đổi nhỏ trong mã Java vẫn có thể là thay đổi phá vỡ client, chẳng hạn đổi tên trường JSON hoặc đổi ý nghĩa của một trạng thái đơn hàng.

### 2.2. Ngữ nghĩa thống nhất giúp con người và công cụ hiểu hệ thống

Khi `GET` dùng để đọc và `404` thể hiện không tìm thấy resource theo hợp đồng, client có thể tái sử dụng những cách xử lý quen thuộc.

Tương tự, header cache, mã lỗi, URI và thông tin truy vết giúp các công cụ kiểm thử, giám sát hoặc proxy xử lý request nhất quán hơn.

Tuy nhiên, HTTP không quy định toàn bộ hợp đồng ứng dụng:

- Tên tham số phân trang và cấu trúc trang kết quả vẫn cần được xác định.
- Định dạng lỗi và mã lỗi nghiệp vụ vẫn cần được thống nhất.
- Ý nghĩa của `PENDING`, `CONFIRMED` hoặc `CANCELLED` thuộc nghiệp vụ.
- Quyền của từng người gọi đối với từng resource vẫn phải được kiểm tra.

Dùng cùng HTTP không đồng nghĩa các API tự hiểu được dữ liệu của nhau.

### 2.3. Có thể tận dụng các thành phần trung gian

Một hệ thống có thể đặt gateway, reverse proxy hoặc cân bằng tải trước các instance xử lý API. Việc dùng giao diện HTTP đúng ngữ nghĩa tạo điều kiện cho các lớp này hoạt động mà client không phải biết mọi chi tiết phía sau.

Đổi lại, lỗi có thể phát sinh ở nhiều nơi: client, gateway, ứng dụng hoặc dịch vụ phụ thuộc. Cần có mã tương quan hoặc cơ chế truy vết phù hợp để theo dõi một yêu cầu qua các lớp.

Gateway cũng không thay thế toàn bộ phân quyền nghiệp vụ. Sau khi xác thực người gọi, ứng dụng vẫn cần xác định người đó có được xem đơn hàng cụ thể hay không.

## 3. Ưu điểm có điều kiện: stateless hỗ trợ mở rộng

Với tương tác stateless, mỗi request mang đủ thông tin cần thiết để server xử lý mà không phải nhớ một cuộc hội thoại ngầm với client từ request trước.

Điều này giảm nhu cầu buộc một client luôn quay lại cùng một instance ứng dụng:

~~~text
Client
   |
Bộ cân bằng tải
   |-------------------|
Instance A          Instance B
   |-------------------|
  Dữ liệu và hạ tầng dùng chung
~~~

Nếu A không sẵn sàng, một request khác có thể được định tuyến đến B, miễn là B có đủ khả năng truy cập dữ liệu và thực thi cùng hợp đồng.

Nhưng stateless không có nghĩa là:

- Không cần cơ sở dữ liệu.
- Không cần quản lý đơn hàng, giỏ hàng hoặc bản nháp.
- Không có giới hạn kết nối, CPU hoặc bộ nhớ.
- Không có lỗi đồng thời.
- Thêm instance ứng dụng sẽ tự tăng thông lượng theo cùng tỷ lệ.

Ví dụ, cả A và B cùng chờ một cơ sở dữ liệu đã quá tải thì thêm instance có thể chỉ làm tăng số kết nối và mức tranh chấp.

Việc kiểm tra token, quyền truy cập, giới hạn tần suất hoặc khóa idempotency cũng có thể cần dữ liệu dùng chung. Những dữ liệu đó không tự làm tương tác mất tính stateless; cần xét hệ thống có phụ thuộc vào trạng thái hội thoại riêng để diễn giải request hay không.

Khi đánh giá khả năng mở rộng, cần tìm điểm nghẽn thực tế: truy vấn, kết nối, khóa, dịch vụ phụ thuộc, kích thước response hoặc chi phí xử lý, thay vì chỉ đếm số controller.

## 4. Chi phí: thiết kế và duy trì hợp đồng dữ liệu

### 4.1. Resource không phải bản sao của bảng dữ liệu

Một màn hình chi tiết đơn hàng có thể cần:

- Mã và trạng thái đơn hàng.
- Tổng tiền và đơn vị tiền tệ.
- Tên hiển thị của khách hàng.
- Tóm tắt giao hàng.

Những thông tin này có thể đến từ nhiều bảng hoặc dịch vụ. API không bắt buộc chia response theo đúng ranh giới lưu trữ.

Nếu trả trực tiếp entity lưu trữ, hệ thống dễ gặp các vấn đề như lộ trường nội bộ, dữ liệu quá lớn, phụ thuộc quan hệ tải lười hoặc làm client phụ thuộc vào mô hình cơ sở dữ liệu.

Thiết kế DTO và representation riêng giúp kiểm soát hợp đồng, nhưng tạo thêm công việc ánh xạ, kiểm tra quyền truy cập và kiểm thử.

### 4.2. Độc lập triển khai cần được bảo vệ bằng tương thích

Một hợp đồng cần nêu rõ:

- Trường nào bắt buộc, trường nào có thể vắng mặt hoặc nhận `null`.
- Kiểu và phạm vi giá trị của từng trường.
- Cách biểu diễn ngày giờ, tiền tệ và số lượng.
- Cấu trúc lỗi và ý nghĩa mã lỗi.
- Cách phân trang, lọc và sắp xếp.
- Hành vi khi resource không tồn tại hoặc người gọi không có quyền.
- Chính sách đối với các giá trị hoặc trường mới.

Không nên mặc định rằng thêm một trường hoặc một giá trị enum luôn an toàn. Client có bộ giải mã quá chặt, kiểm tra schema nghiêm ngặt hoặc xử lý enum không có nhánh dự phòng vẫn có thể bị ảnh hưởng.

OpenAPI giúp mô tả và trao đổi hợp đồng, nhưng không tự bảo đảm mã triển khai đúng tài liệu hoặc client thật sự tương thích. Cần kết hợp quy trình thay đổi và kiểm thử thích hợp.

REST không bắt buộc một chiến lược versioning duy nhất. Đặt phiên bản trong URI, header hoặc media type đều có chi phí vận hành và tương thích riêng. Trước khi tạo phiên bản mới, cần xác định thay đổi nào thực sự phá vỡ hợp đồng và thời gian hỗ trợ client cũ.

## 5. Giới hạn thực tế: số request, độ trễ và lượng dữ liệu

### 5.1. Giao diện rõ ràng vẫn có thể tạo nhiều lượt trao đổi

Giả sử trang chi tiết đơn hàng cần ba dữ liệu:

1. `GET /orders/42` trả thông tin đơn hàng và các ID liên quan.
2. `GET /customers/15` trả tên hiển thị khách hàng.
3. `GET /shipments/811` trả thông tin giao hàng.

Sau request đầu, hai request còn lại có thể độc lập với nhau.

Giả sử mỗi request có:

- Thời gian khứ hồi mạng: 70 ms.
- Thời gian xử lý tại server: 15 ms.
- Bỏ qua thời gian kết nối ban đầu, truyền body, tranh chấp và các chi phí khác.

Khi đó:

| Cách thực hiện | Ước lượng theo giả định |
|---|---|
| Gọi cả ba request tuần tự | `3 × (70 + 15) = 255 ms` |
| Gọi request đầu, sau đó gọi hai request còn lại song song | `85 + max(85, 85) = 170 ms` |

Đây chỉ là mô hình tính chi phí, không phải cam kết hiệu năng. Nó cho thấy cần phân biệt **số request** và **số lượt trao đổi phụ thuộc nhau**.

Cơ chế truyền nhiều request đồng thời không loại bỏ quan hệ phụ thuộc dữ liệu. Client vẫn phải biết ID khách hàng và giao hàng trước khi tạo được hai request sau.

### 5.2. Có thể thiết kế representation theo nhu cầu sử dụng

Một lựa chọn là cung cấp:

~~~http
GET /orders/42/summary HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "totalAmount": 250000,
  "currency": "VND",
  "customerDisplayName": "Khách hàng A",
  "shipmentStatus": "IN_TRANSIT"
}
~~~

Một representation tổng hợp như vậy vẫn có thể được thiết kế theo hướng resource. REST không bắt buộc một bảng phải có một endpoint, hay một response chỉ được chứa dữ liệu từ một nguồn.

Lợi ích là client có thể nhận dữ liệu cần dùng trong ít lượt trao đổi hơn. Chi phí chuyển sang server:

- Tổng hợp dữ liệu từ nhiều nguồn.
- Xác định chính sách khi một nguồn không sẵn sàng.
- Tránh tạo quá nhiều representation chỉ khác nhau rất ít.
- Kiểm tra quyền đối với từng thông tin được ghép vào response.
- Xác định mức độ nhất quán giữa các phần dữ liệu.

Đưa việc tổng hợp vào gateway hoặc một backend dành cho nhóm client cũng không làm biến mất các request nội bộ. Cần đo cả độ trễ đầu cuối và tải lên hệ thống phía sau.

### 5.3. Over-fetching và under-fetching là chi phí thiết kế thường gặp

**Over-fetching** xảy ra khi response mang nhiều dữ liệu hơn client cần. Ví dụ, danh sách đơn hàng tải cả lịch sử xử lý chi tiết của từng đơn.

**Under-fetching** xảy ra khi response thiếu dữ liệu cần thiết, buộc client gọi thêm nhiều request.

Có thể giảm các chi phí này bằng cách:

- Thiết kế response danh sách khác response chi tiết.
- Phân trang với kích thước trang có giới hạn.
- Cho chọn trường hoặc mở rộng dữ liệu liên quan theo một hợp đồng được kiểm soát.
- Cung cấp representation tổng hợp cho một nhu cầu phổ biến.
- Dùng thao tác theo lô khi bài toán thực sự cần và đã xác định rõ lỗi từng phần.

Mỗi cách bổ sung thêm độ phức tạp. Chẳng hạn, cho phép tùy chọn trường tự do làm tăng số biến thể response, ảnh hưởng cache, truy vấn và kiểm thử quyền truy cập.

Phân trang cũng không tự bảo đảm một ảnh chụp nhất quán của tập dữ liệu đang thay đổi. Nếu sản phẩm được thêm hoặc xóa giữa hai lần lấy trang, cách sắp xếp và cơ chế phân trang cần được thiết kế để xử lý khả năng trùng hoặc thiếu kết quả.

## 6. Cache: lợi ích lớn đi kèm bài toán freshness và quyền truy cập

Một response được tái sử dụng hợp lệ có thể giúp giảm request tới ứng dụng, giảm truy vấn và rút ngắn thời gian phản hồi.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=30
ETag: "order-42-v7"

{
  "id": 42,
  "status": "CONFIRMED"
}
~~~

Trong ví dụ:

- `private` không cho cache dùng chung lưu response; cache riêng có thể lưu theo các điều kiện áp dụng.
- `max-age=30` xác định khoảng freshness 30 giây theo chính sách này.
- `ETag` là validator của representation, có thể được dùng để kiểm tra lại thay vì truyền lại toàn bộ body.

Khi cần kiểm tra lại:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
If-None-Match: "order-42-v7"
~~~

Nếu representation vẫn phù hợp với validator, server có thể trả `304 Not Modified` không kèm body, để cache sử dụng representation đã lưu theo các quy tắc HTTP.

Cơ chế kiểm tra lại có thể giảm lượng dữ liệu truyền, nhưng vẫn có chi phí mạng và kiểm tra tại server. Nếu server phải chạy một truy vấn đắt tiền mới tính được validator thì lợi ích giảm tải cần được đánh giá thực tế.

Các câu hỏi phải trả lời khi thiết kế cache:

1. Dữ liệu được phép cũ trong bao lâu?
2. Response có phụ thuộc vào danh tính hoặc quyền của người gọi không?
3. Response có thay đổi theo ngôn ngữ, media type hoặc các header khác không?
4. Khi dữ liệu cập nhật, các bản sao liên quan được xử lý thế nào?
5. Sau khi ghi, người dùng có cần nhìn thấy ngay trạng thái mới không?

Nếu response thay đổi theo một header như `Accept-Language`, chính sách cache cần phân biệt biến thể đó, chẳng hạn bằng `Vary` thích hợp. Với dữ liệu cá nhân, chỉ dựa vào URL để chia sẻ cache có thể dẫn đến lộ thông tin.

Cũng cần phân biệt:

- `no-cache`: response có thể được lưu, nhưng phải được xác thực lại thành công trước khi tái sử dụng theo quy tắc áp dụng.
- `no-store`: chỉ thị không lưu request/response tương ứng trong cache theo phạm vi của chỉ thị.

Không phải endpoint nào cũng phù hợp để cache, và REST không yêu cầu mọi response đều phải được lưu. Chính sách đúng có thể là không cho lưu đối với một loại dữ liệu cụ thể.

## 7. Retry và cập nhật đồng thời: HTTP cung cấp công cụ, ứng dụng vẫn phải triển khai

### 7.1. Idempotency không tự xuất hiện khi dùng REST

Xét tình huống tạo đơn hàng:

~~~text
1. Client gửi POST /orders.
2. Server lưu đơn hàng thành công.
3. Kết nối bị đứt trước khi client nhận response.
4. Client không biết kết quả và gửi lại request.
~~~

Nếu server xử lý lần gửi lại như một yêu cầu mới, có thể tạo hai đơn hàng. Timeout ở client chỉ cho biết client chưa nhận được kết quả trong thời gian chờ, không chứng minh server chưa thực hiện thao tác.

Một API có thể định nghĩa cơ chế khóa idempotency:

~~~http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Idempotency-Key: checkout-attempt-7d4f

{
  "cartId": 91
}
~~~

Header ở đây là một phần hợp đồng mà API cần định nghĩa và triển khai; chỉ gửi header không tạo ra khả năng chống lặp.

Server còn phải xác định:

- Khóa có hiệu lực trong phạm vi người gọi và thao tác nào.
- Khóa tồn tại trong bao lâu.
- Hai request đồng thời dùng cùng khóa được xử lý ra sao.
- Cùng khóa nhưng payload khác nhau sẽ bị từ chối thế nào.
- Kết quả hoặc lỗi nào được lưu để trả lại cho lần gửi sau.
- Việc ghi nhận khóa và thực hiện tác động nghiệp vụ có đủ tính nguyên tử trong phạm vi cần thiết không.

Nếu thao tác còn gọi một hệ thống thanh toán bên ngoài, khóa tại API tạo đơn chưa tự bảo đảm phía thanh toán không thực hiện hai lần. Cần thiết kế xuyên suốt các ranh giới có tác động nghiệp vụ.

Các phương thức có ngữ nghĩa idempotent như `PUT` và `DELETE` hỗ trợ việc suy luận khi retry, nhưng ứng dụng phải thực thi đúng ngữ nghĩa đó và client vẫn cần chính sách timeout, retry và giới hạn phù hợp.

### 7.2. REST không tự tránh mất cập nhật

Hai nhân viên có thể cùng đọc phiên bản 7 của một đơn hàng. Người thứ nhất cập nhật trước; người thứ hai gửi dữ liệu cũ sau và vô tình ghi đè thay đổi mới.

Một cách kiểm soát là cập nhật có điều kiện:

~~~http
PUT /orders/42 HTTP/1.1
Host: api.example.com
Content-Type: application/json
If-Match: "order-42-v7"

{
  "status": "CONFIRMED",
  "deliveryNote": "Giao trong giờ hành chính"
}
~~~

Ví dụ này giả định body đáp ứng hợp đồng thay thế representation của endpoint `PUT`; một API chỉ sửa một phần dữ liệu có thể cần hợp đồng `PATCH` phù hợp.

Nếu representation hiện tại không còn khớp validator, server có thể trả `412 Precondition Failed`.

Để ngăn mất cập nhật, bước kiểm tra phiên bản và bước ghi phải được bảo vệ trước cạnh tranh đồng thời, chẳng hạn bằng optimistic locking hoặc cơ chế nguyên tử phù hợp trong tầng lưu trữ. Kiểm tra trước rồi ghi không có bảo vệ vẫn có cửa sổ xảy ra xung đột.

Đây là chi phí triển khai cần thiết; bản thân URI hướng resource không giải quyết được vấn đề.

## 8. Giới hạn: các luồng kéo dài và giao tiếp thời gian thực

### 8.1. Công việc dài không nhất thiết phải giữ một request mở

Xuất một báo cáo lớn có thể mất nhiều phút. Giữ kết nối chờ toàn bộ công việc có thể gây timeout và chiếm tài nguyên.

Có thể biểu diễn công việc thành resource:

~~~http
POST /export-jobs HTTP/1.1
Host: api.example.com
Content-Type: application/json

{
  "reportType": "MONTHLY_ORDERS",
  "month": "2026-10"
}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /export-jobs/81
Content-Type: application/json

{
  "id": 81,
  "status": "QUEUED",
  "statusUrl": "/export-jobs/81"
}
~~~

Trong hợp đồng minh họa này, `Location` chỉ đến resource theo dõi công việc. Client có thể đọc resource đó để biết trạng thái.

`202 Accepted` cho biết yêu cầu đã được chấp nhận xử lý, không khẳng định công việc cuối cùng sẽ thành công. API phải định nghĩa thêm các trạng thái, cách báo lỗi, thời hạn giữ kết quả và khả năng hủy nếu có.

Chi phí mới là quản lý hàng đợi, worker, lưu trạng thái và cơ chế kiểm tra kết quả. Nếu rất nhiều client polling với tần suất cao, phần kiểm tra trạng thái có thể trở thành tải đáng kể.

Có thể bổ sung callback hoặc cơ chế sự kiện khi phù hợp, nhưng cần giải quyết giao nhận lặp, xác thực bên gửi, retry và thứ tự xử lý.

### 8.2. Tương tác liên tục có nhu cầu khác với đọc resource theo request

Một màn hình xem đơn hàng thỉnh thoảng thường phù hợp với request/response. Một ứng dụng cần nhận cập nhật liên tục hoặc trao đổi hai chiều với độ trễ thấp có thêm nhu cầu về vòng đời kết nối và luồng dữ liệu.

HTTP và các công nghệ liên quan có thể phục vụ streaming; không nên kết luận rằng một hệ thống dùng REST không thể có cập nhật trực tiếp.

Tuy vậy, chỉ có một bộ endpoint đọc/ghi resource thông thường chưa giải quyết đầy đủ:

- Phát thông tin mới tới client khi trạng thái thay đổi.
- Duy trì hoặc khôi phục kết nối.
- Tiếp tục từ vị trí đã nhận.
- Điều tiết tốc độ gửi và xử lý dữ liệu.
- Phân phối sự kiện tới nhiều client.

Tùy hướng trao đổi, có thể cân nhắc SSE, WebSocket hoặc một cơ chế thông điệp bổ sung. Hệ thống vẫn có thể dùng REST cho việc quản lý resource và dùng cơ chế khác cho việc phân phối cập nhật.

## 9. Giới hạn: nhất quán dữ liệu và giao dịch phân tán

Một luồng đặt hàng có thể liên quan đến:

~~~text
Tạo đơn → giữ hàng → thanh toán → giao hàng
~~~

Các bước có thể do nhiều dịch vụ và cơ sở dữ liệu quản lý. Việc mọi dịch vụ đều có REST API không làm toàn bộ chuỗi trở thành một giao dịch nguyên tử.

Ví dụ, thanh toán thành công nhưng cập nhật đơn hàng thất bại. Cần quyết định:

- Hệ thống sẽ thử lại bước nào?
- Người dùng nhìn thấy trạng thái gì trong lúc chưa đồng bộ?
- Khi nào cần hoàn tiền hoặc giải phóng hàng?
- Cách nhận biết và xử lý sự kiện gửi lặp là gì?
- Làm sao đối soát khi trạng thái giữa các hệ thống khác nhau?

Đây là bài toán giao dịch phân tán và quy trình nghiệp vụ. Có thể cần cơ chế bù trừ, thông điệp bền vững, đối soát hoặc các mẫu phối hợp khác tùy yêu cầu.

Không nên gọi eventual consistency là thuộc tính bắt buộc của REST. Một API REST vẫn có thể thực hiện giao dịch nhất quán mạnh trong phạm vi một kho dữ liệu. Giới hạn xuất hiện khi yêu cầu nhất quán vượt qua những ranh giới mà hệ thống có thể bảo đảm.

## 10. Chi phí bảo mật, kiểm thử và vận hành

REST không tự cung cấp chính sách xác thực hay phân quyền. HTTPS bảo vệ dữ liệu trên đường truyền theo cơ chế của nó, nhưng không thay thế kiểm tra quyền trong ứng dụng.

Ví dụ, một người dùng đăng nhập hợp lệ gọi:

~~~http
GET /orders/43 HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
~~~

Server vẫn phải kiểm tra người đó có quyền đọc đơn hàng 43 hay không. Không thể chỉ kiểm tra token hợp lệ rồi trả mọi đơn hàng có ID được gửi vào.

Ngoài chức năng chính, một API thực tế cần ngân sách cho:

| Hạng mục | Công việc tiêu biểu |
|---|---|
| Xác thực và phân quyền | Kiểm tra danh tính, quyền trên resource và quyền trên trường dữ liệu |
| Kiểm soát dữ liệu vào | Giới hạn kích thước body, kích thước trang, kiểu và miền giá trị |
| Xử lý lỗi | Mã HTTP phù hợp, mã lỗi ổn định, tránh lộ stack trace và thông tin nội bộ |
| Kiểm thử hợp đồng | Kiểm tra method, URI, status, header, schema và tính tương thích |
| Kiểm thử hành vi | Kiểm tra quyền, retry, xung đột cập nhật và lỗi từng phần |
| Quan sát hệ thống | Độ trễ theo phân vị, tỷ lệ lỗi, lưu lượng, truy vết và mức sử dụng tài nguyên |
| Quản lý vòng đời | Tài liệu, thay đổi hợp đồng, ngừng hỗ trợ và hỗ trợ client chuyển đổi |

Khi ghi log, không nên ghi nguyên token hoặc toàn bộ dữ liệu cá nhân chỉ để thuận tiện gỡ lỗi. Khả năng quan sát cần được thiết kế cùng việc bảo vệ thông tin.

Các chi phí này không chỉ tồn tại ở REST. Chuyển sang một kiểu API khác thường chuyển hình thức triển khai chứ không xóa nhu cầu bảo mật, tương thích hay vận hành.

## 11. Áp dụng với Java/Spring: đừng lấy số dòng controller làm thước đo

Trong Java/Spring, ánh xạ `@GetMapping` hoặc trả JSON thường khá ngắn. Phần quyết định chất lượng nằm ở hợp đồng, tầng nghiệp vụ và cách truy cập dữ liệu.

Ví dụ representation tổng hợp có thể được khai báo:

~~~java
public record OrderSummary(
    long id,
    String status,
    long totalAmount,
    String currency,
    String customerDisplayName,
    String shipmentStatus
) {
}
~~~

Đây là DTO minh họa với Java có hỗ trợ `record`. Trong hợp đồng của ví dụ, `totalAmount` là số tiền nguyên theo đơn vị VND, còn `currency` là `"VND"`; không nên mặc định cùng một cách biểu diễn phù hợp với mọi loại tiền và phép tính.

Đằng sau DTO này, nhóm phát triển vẫn cần quyết định:

- Truy vấn có lấy đủ dữ liệu mà không gây N+1 hay không.
- Tên khách hàng có được phép lộ cho người gọi không.
- Nếu thông tin giao hàng tạm thời không lấy được, trả lỗi hay một trạng thái thiếu dữ liệu được định nghĩa rõ.
- Có thể cache toàn bộ summary không và trong bao lâu.
- Thay đổi DTO có ảnh hưởng client cũ không.

Có hai dạng N+1 cần phân biệt:

1. Client gọi một request lấy danh sách rồi gọi thêm từng resource để bổ sung dữ liệu.
2. Server xử lý một request nhưng chạy thêm một truy vấn cho mỗi phần tử vì cách tải quan hệ dữ liệu.

Giảm số request của client không bảo đảm đã giảm số truy vấn tại server. Khi tối ưu, cần đo cả hai phía và giữ nguyên kiểm tra quyền.

Một bài thực hành nhỏ có thể so sánh cách lấy dữ liệu tách rời với endpoint summary, đo số request, số truy vấn, kích thước response và độ trễ khi một nguồn bị chậm. Kết quả đo mới là cơ sở để chọn cách triển khai cho tình huống đó.

## 12. Chọn cách giao tiếp theo nhu cầu

| Tình huống | Vai trò phù hợp của REST trên HTTP | Điều cần cân nhắc thêm |
|---|---|---|
| API quản lý sản phẩm, đơn hàng cho nhiều client | Resource và hợp đồng ổn định thường là điểm bắt đầu phù hợp | Phân trang, quyền, tương thích và lỗi |
| Dữ liệu danh mục đọc nhiều, chấp nhận cũ trong một khoảng | Có thể tận dụng cache và validator | Freshness, cập nhật và phân biệt biến thể |
| Màn hình cần nhiều dữ liệu liên quan | Có thể dùng representation tổng hợp hoặc mở rộng có kiểm soát | Số lượt trao đổi, tải truy vấn và độ phức tạp hợp đồng |
| Công việc xuất báo cáo kéo dài | REST quản lý resource công việc và kết quả | Worker, lưu trạng thái, polling hoặc thông báo |
| Cập nhật trực tiếp liên tục | REST quản lý dữ liệu nền, có thể kết hợp kênh cập nhật | Vòng đời kết nối, tiếp tục luồng và điều tiết tốc độ |
| Client cần lựa chọn linh hoạt nhiều dạng dữ liệu liên quan | Cần đánh giá chi phí của các endpoint và tùy chọn biểu diễn | Có thể so sánh với GraphQL, đồng thời xét phân quyền và giới hạn độ phức tạp truy vấn |
| Giao tiếp nội bộ có yêu cầu đặc thù về lời gọi, kiểu dữ liệu hoặc streaming | Có thể dùng REST nếu đáp ứng yêu cầu đo được | Có thể so sánh với gRPC hoặc cơ chế thông điệp; tính cả công cụ và vận hành |

Bảng này không thiết lập một công nghệ thắng trong mọi tình huống. Một hệ thống có thể phối hợp nhiều kiểu giao tiếp, miễn là ranh giới, trách nhiệm và hợp đồng đủ rõ.

## 13. Tự kiểm tra

### Câu hỏi

1. API stateless có ba instance ứng dụng nhưng vẫn chậm khi tải tăng. Có thể kết luận REST không mở rộng được không?
2. Một trang cần ba request. Có luôn được phép tính độ trễ bằng ba lần độ trễ một request không?
3. Client timeout sau khi gửi `POST /orders`. Vì sao gửi lại ngay có thể tạo đơn trùng?
4. `Cache-Control: no-cache` có đồng nghĩa với việc cấm lưu response không?
5. Hai client cùng cập nhật một đơn hàng. Chỉ dùng `PUT` có đủ để tránh mất cập nhật không?
6. Một response summary đã ghép dữ liệu từ ba dịch vụ. Có thể khẳng định dữ liệu luôn được đọc tại cùng một thời điểm không?
7. API trả `202 Accepted` cho một tác vụ xuất báo cáo. Điều đó có bảo đảm báo cáo sẽ được tạo thành công không?
8. Cung cấp endpoint trả JSON và file OpenAPI có làm mất nhu cầu kiểm thử tương thích và phân quyền không?

### Gợi ý trả lời

1. Chưa. Cần đo điểm nghẽn như cơ sở dữ liệu, số kết nối, truy vấn hoặc dịch vụ phụ thuộc. Stateless hỗ trợ phân phối request nhưng không xóa các giới hạn dùng chung.
2. Không. Cần xem request nào phụ thuộc dữ liệu của request trước và request nào có thể thực hiện đồng thời.
3. Server có thể đã tạo đơn nhưng response bị mất. Cần cơ chế idempotency với phạm vi và cách xử lý đồng thời được thiết kế rõ.
4. Không. `no-cache` yêu cầu xác thực lại trước khi tái sử dụng theo quy tắc áp dụng; `no-store` mới là chỉ thị không lưu trong cache.
5. Không. Idempotency khác với kiểm soát cạnh tranh. Cần cơ chế như điều kiện phiên bản và kiểm tra/ghi nguyên tử.
6. Không. Tổng hợp một response không tự tạo snapshot nhất quán xuyên nhiều nguồn dữ liệu.
7. Không. Nó báo đã chấp nhận xử lý; kết quả cuối cùng phải được theo dõi và có thể thất bại.
8. Không. Tài liệu và định dạng dữ liệu không chứng minh triển khai đúng hợp đồng, đúng quyền hoặc không phá vỡ client.

Khi bảo vệ một quyết định dùng REST, hãy nêu lợi ích mong đợi, điều kiện để đạt lợi ích đó và chi phí phải chấp nhận. Ví dụ: “Dùng resource đơn hàng với hợp đồng HTTP ổn định để nhiều client tích hợp; thêm summary để giảm lượt trao đổi của màn hình; thiết kế idempotency cho tạo đơn và phiên bản cho cập nhật; tách công việc dài sang resource tác vụ.” Một quyết định cụ thể như vậy có thể được triển khai, kiểm thử và đánh giá bằng số liệu.
