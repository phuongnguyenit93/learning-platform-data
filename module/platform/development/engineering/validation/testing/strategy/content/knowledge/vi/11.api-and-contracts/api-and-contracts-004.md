# Đánh giá thay đổi tương thích và thay đổi phá vỡ hợp đồng

Hợp đồng API mô tả cách một hệ thống cung cấp chức năng cho hệ thống khác: endpoint, phương thức, dữ liệu, kiểu, trạng thái, quy tắc xác thực, lỗi và hành vi được cam kết. Khi hợp đồng thay đổi, một phía có thể được cập nhật trước phía còn lại. Nếu thay đổi làm phía đang sử dụng không thể tiếp tục hoạt động theo cách đã cam kết, đó là thay đổi phá vỡ tương thích (breaking change).

Đánh giá tương thích cần được thực hiện trước khi sửa API, schema sự kiện hoặc giao diện giữa các dịch vụ. Nhóm phải xác định ai là consumer, ai là provider, hợp đồng nào đang được sử dụng, phiên bản nào nằm trong phạm vi và cách triển khai diễn ra. Một thay đổi có vẻ nhỏ trong mã nguồn, chẳng hạn đổi tên trường hoặc siết điều kiện xác thực, vẫn có thể phá vỡ tích hợp đang chạy.

Bài học này trình bày cách phân loại thay đổi, đánh giá tác động, xác minh bằng kiểm thử hợp đồng và tổ chức phát hành để các bên có thời gian chuyển đổi an toàn.

## 1. Hiểu hợp đồng và các chiều tương thích

Hợp đồng API là thỏa thuận về giao tiếp giữa bên cung cấp và bên sử dụng. Hợp đồng có thể được mô tả bằng OpenAPI, JSON Schema, AsyncAPI, protobuf, WSDL, tài liệu kỹ thuật hoặc quy ước được thống nhất giữa các nhóm. Dù được lưu ở đâu, hợp đồng cần phản ánh cả cấu trúc lẫn hành vi.

Một hợp đồng thường xác định:

- **Địa chỉ và giao thức:** base URL, path, HTTP method, RPC method, topic hoặc queue.
- **Cấu trúc dữ liệu:** tên trường, kiểu, định dạng, giới hạn, trường bắt buộc và trường tùy chọn.
- **Quy tắc yêu cầu:** header, tham số, xác thực, phân quyền, thứ tự và điều kiện hợp lệ.
- **Quy tắc phản hồi:** mã trạng thái, schema, header, nội dung và cách biểu diễn kết quả.
- **Hành vi lỗi:** loại lỗi, mã lỗi, retry, timeout và điều kiện có thể thử lại.
- **Ngữ nghĩa nghiệp vụ:** ý nghĩa trường, đơn vị đo, trạng thái, thứ tự sự kiện và tác dụng của thao tác.
- **Thuộc tính vận hành:** giới hạn tốc độ, kích thước payload, thời gian phản hồi và chính sách phiên bản.

Tương thích không chỉ có một nghĩa. Cần xác định phía nào cần tiếp tục hoạt động:

- **Tương thích ngược (backward compatibility):** phiên bản provider mới vẫn đáp ứng các consumer cũ đang tuân theo hợp đồng trước đó.
- **Tương thích tiến (forward compatibility):** consumer hiện tại có thể xử lý dữ liệu hoặc phản hồi được tạo bởi provider mới trong phạm vi đã dự kiến, ví dụ bỏ qua trường không nhận biết.
- **Tương thích giữa các phiên bản (cross-version compatibility):** hai phiên bản khác nhau có thể giao tiếp trong một giai đoạn chuyển tiếp.
- **Tương thích nguồn (source compatibility):** mã nguồn consumer có thể biên dịch hoặc được cập nhật mà không phải sửa cách gọi theo hợp đồng công khai.
- **Tương thích nhị phân (binary compatibility):** chương trình đã biên dịch tiếp tục liên kết hoặc chạy với thư viện mới theo cam kết.
- **Tương thích trên đường truyền (wire compatibility):** thông điệp được tuần tự hóa vẫn có thể được đọc và hiểu theo giao thức.

Một API web có thể tương thích trên đường truyền nhưng vẫn phá vỡ ngữ nghĩa. Ví dụ, trường amount vẫn là số nhưng đơn vị thay đổi từ đồng sang nghìn đồng. Schema không đổi, nhưng consumer tính toán sai. Vì vậy, đánh giá phải xem xét cả cấu trúc, hành vi và ý nghĩa dữ liệu.

## 2. Xác định consumer, provider và phạm vi sử dụng

Trước khi phân loại thay đổi, hãy lập bản đồ những bên bị ảnh hưởng. Provider có thể có nhiều consumer: ứng dụng web, ứng dụng di động, dịch vụ nội bộ, đối tác, tác vụ batch, hệ thống báo cáo hoặc khách hàng tự tích hợp.

Cần trả lời:

1. Ai đang gọi API hoặc tiêu thụ sự kiện?
2. Consumer đang dùng phiên bản, endpoint, trường hoặc hành vi nào?
3. Consumer có được cập nhật đồng thời với provider không?
4. Có consumer bên ngoài tổ chức mà nhóm không kiểm soát lịch triển khai không?
5. Có phiên bản ứng dụng cũ vẫn còn được sử dụng không?
6. Hợp đồng có được dùng trong SDK, tài liệu công khai, ví dụ mã hoặc môi trường sandbox không?
7. Có yêu cầu riêng theo khách hàng, khu vực hoặc gói dịch vụ không?

Không nên chỉ dựa vào log lưu lượng trong một khoảng thời gian ngắn để kết luận một API không còn consumer. Tác vụ định kỳ, tích hợp ít sử dụng, khách hàng tạm ngừng hoặc ứng dụng cũ có thể chỉ gọi theo mùa hoặc theo sự kiện.

Có thể kết hợp nhiều nguồn:

- Danh mục API và chủ sở hữu.
- Gateway log, telemetry và dữ liệu sử dụng theo client.
- Danh sách SDK hoặc phiên bản ứng dụng đang hoạt động.
- Hợp đồng, tài liệu tích hợp và thông tin khách hàng.
- Mã nguồn consumer và cấu hình triển khai.
- Consumer-driven contract test và lịch sử kiểm thử.

Ghi lại phạm vi và thời điểm của bằng chứng. Nếu không thể xác định đầy đủ consumer, coi đây là một rủi ro của thay đổi và lên kế hoạch chuyển đổi có kiểm soát.

## 3. Phân biệt thay đổi tương thích và thay đổi phá vỡ

Một thay đổi thường được xem là tương thích khi consumer hợp lệ hiện tại vẫn có thể gửi yêu cầu, đọc phản hồi và nhận hành vi đã cam kết. Tuy nhiên, kết luận phụ thuộc vào hợp đồng cụ thể và cách consumer sử dụng API.

### 3.1. Thay đổi thường có khả năng tương thích

Một số thay đổi thường có thể tương thích nếu tuân thủ quy tắc của hợp đồng:

- Thêm một trường tùy chọn vào phản hồi, nếu consumer bỏ qua trường không nhận biết.
- Thêm một endpoint hoặc operation mới mà không thay đổi endpoint cũ.
- Thêm một giá trị mặc định có ý nghĩa tương đương với hành vi hiện tại.
- Thêm một mã lỗi mới nếu consumer được thiết kế để xử lý mã chưa biết theo cách an toàn.
- Tăng giới hạn mà consumer không dựa vào giới hạn cũ như một phần hành vi.
- Bổ sung khả năng mới mà không thay đổi kết quả của yêu cầu hiện có.

Ngay cả các thay đổi này cũng cần xem xét cách sinh mã client, validator nghiêm ngặt và quy tắc schema. Một consumer được sinh từ schema có thể từ chối trường chưa biết, dù một client khác có thể bỏ qua trường đó.

### 3.2. Thay đổi thường phá vỡ tương thích

Các thay đổi sau thường có nguy cơ breaking:

- Xóa hoặc đổi tên endpoint, operation, topic hay trường.
- Đổi kiểu dữ liệu hoặc định dạng theo cách consumer không xử lý được.
- Thêm trường bắt buộc vào request mà consumer cũ không gửi.
- Làm trường phản hồi trước đây luôn có giá trị trở thành null hoặc vắng mặt.
- Thay đổi mã trạng thái hoặc cấu trúc lỗi mà consumer dựa vào.
- Siết validation, giới hạn kích thước hoặc quy tắc định dạng khiến request hợp lệ trước đây bị từ chối.
- Thay đổi ngữ nghĩa, đơn vị, múi giờ, thứ tự hoặc ý nghĩa của trạng thái.
- Thay đổi cơ chế xác thực, quyền hoặc phạm vi token.
- Thay đổi thứ tự sự kiện hoặc bảo đảm giao nhận mà consumer phụ thuộc.
- Giảm giới hạn tốc độ hoặc thời gian timeout đã cam kết.

Bảng sau cung cấp ví dụ phân loại ban đầu:

| Thay đổi | Đánh giá sơ bộ | Điều cần xác minh |
|---|---|---|
| Thêm trường tùy chọn trong response | Thường tương thích | Consumer và SDK có bỏ qua trường lạ không? |
| Xóa trường response | Thường phá vỡ | Có consumer nào đọc trường đó không? |
| Thêm trường bắt buộc trong request | Phá vỡ với consumer cũ | Có giá trị mặc định hoặc giai đoạn chuyển tiếp không? |
| Đổi string thành integer | Thường phá vỡ | Có chuyển đổi an toàn và thống nhất không? |
| Thêm giá trị enum | Có điều kiện | Consumer có xử lý giá trị chưa biết không? |
| Đổi mã lỗi 404 thành 200 với body khác | Có thể phá vỡ | Consumer có dựa vào status code và xử lý lỗi không? |
| Siết giới hạn độ dài đầu vào | Có điều kiện hoặc phá vỡ | Dữ liệu hợp lệ hiện tại có vượt giới hạn mới không? |
| Thay đổi đơn vị của trường số | Phá vỡ ngữ nghĩa | Consumer có thể nhận biết và chuyển đổi không? |
| Thêm endpoint mới | Thường tương thích | Có ảnh hưởng routing, quyền hoặc giới hạn dùng chung không? |

Không nên gắn nhãn tương thích chỉ dựa trên việc schema vẫn hợp lệ. Cần đánh giá theo consumer thực tế và các cam kết hành vi.

## 4. Đánh giá thay đổi ở request và response

Request và response có hướng tương tác khác nhau. Một thay đổi được xem là an toàn với phía gửi chưa chắc an toàn với phía nhận.

### 4.1. Thay đổi request

Provider nhận request từ consumer. Khi thêm trường bắt buộc, consumer cũ có thể không gửi trường đó và bị từ chối. Khi đổi tên trường, consumer tiếp tục gửi tên cũ nhưng provider không còn đọc được giá trị.

Các thay đổi cần xem xét:

- Thêm trường optional có giá trị mặc định.
- Chuyển optional thành required.
- Thay đổi kiểu, định dạng, đơn vị hoặc giới hạn.
- Thay đổi quy tắc validation.
- Thay đổi ý nghĩa khi trường bị thiếu, null hoặc rỗng.
- Thay đổi header, authentication hoặc idempotency key.

Một trường JSON có thể có ba trạng thái khác nhau: không xuất hiện, xuất hiện với null, hoặc xuất hiện với giá trị rỗng. Consumer và provider phải thống nhất ý nghĩa từng trạng thái.

Ví dụ request trước đây:

~~~json
{
  "customerId": "C-100",
  "quantity": 2
}
~~~

Phiên bản mới muốn yêu cầu currency:

~~~json
{
  "customerId": "C-100",
  "quantity": 2,
  "currency": "VND"
}
~~~

Nếu provider lập tức từ chối request thiếu currency, consumer cũ sẽ thất bại. Có thể triển khai chuyển tiếp bằng cách provider tạm thời dùng giá trị mặc định đã được thống nhất, theo dõi consumer còn thiếu trường, yêu cầu consumer cập nhật, rồi mới chuyển trường thành bắt buộc trong một phiên bản hợp đồng mới.

### 4.2. Thay đổi response

Consumer nhận response từ provider. Khi xóa trường, đổi kiểu hoặc thay đổi trạng thái null, mã client có thể lỗi hoặc xử lý sai dữ liệu.

Ví dụ response cũ:

~~~json
{
  "orderId": "O-250",
  "status": "PAID",
  "total": 150000
}
~~~

Nếu phiên bản mới đổi total thành một object:

~~~json
{
  "orderId": "O-250",
  "status": "PAID",
  "total": {
    "value": 150000,
    "currency": "VND"
  }
}
~~~

Thay đổi này có thể hợp lý hơn về mô hình dữ liệu, nhưng consumer cũ đang kỳ vọng total là số sẽ không đọc được. Một phương án chuyển tiếp là thêm trường mới totalAmount hoặc money, duy trì trường cũ trong thời gian deprecation và công bố kế hoạch loại bỏ.

Khi thêm trường response, hãy kiểm tra consumer có parser nghiêm ngặt hay không. Khi thêm trường enum hoặc trạng thái, consumer cần có hành vi mặc định an toàn cho giá trị chưa biết, ví dụ ghi nhận và không thực hiện hành động nguy hiểm.

## 5. Đánh giá thay đổi schema và ngữ nghĩa dữ liệu

Schema mô tả cấu trúc dữ liệu, nhưng hợp đồng còn chứa quy tắc về ý nghĩa và vòng đời dữ liệu.

Các câu hỏi quan trọng:

- Trường có thay đổi tên, kiểu, độ dài hoặc định dạng không?
- Trường có đổi từ required sang optional hoặc ngược lại không?
- Giá trị null, rỗng và vắng mặt có cùng ý nghĩa không?
- Đơn vị đo, múi giờ, độ chính xác hoặc quy tắc làm tròn có thay đổi không?
- Giá trị enum có được thêm, bỏ hoặc đổi tên không?
- Dữ liệu cũ có thể được đọc bởi phiên bản mới không?
- Dữ liệu mới có thể được consumer cũ xử lý không?
- Việc chuyển đổi có mất thông tin hoặc làm thay đổi ý nghĩa không?

### 5.1. Thay đổi enum

Thêm một giá trị enum có thể phá vỡ consumer dùng switch exhaustive hoặc parser chỉ chấp nhận danh sách đã biết.

Ví dụ, trạng thái đơn hàng trước đây chỉ gồm:

~~~json
{
  "status": "PENDING"
}
~~~

Sau đó provider thêm REFUND_PENDING. Consumer cũ có thể rơi vào nhánh mặc định không an toàn hoặc lỗi khi deserialize.

Nên thiết kế consumer với nhánh xử lý giá trị chưa biết, và cân nhắc thêm giá trị mới theo lộ trình có thông báo. Không được giả định rằng thêm enum luôn là thay đổi tương thích.

### 5.2. Thay đổi kiểu và định dạng

Đổi số nguyên sang chuỗi, đổi timestamp sang ngày địa phương, thay precision số thập phân hoặc thay đơn vị tiền tệ đều có thể ảnh hưởng consumer. Cần định nghĩa định dạng chuẩn, múi giờ, đơn vị và quy tắc chuyển đổi.

Với timestamp, ưu tiên biểu diễn có múi giờ hoặc quy ước UTC rõ ràng. Với số tiền, tránh dựa vào số thực nhị phân nếu yêu cầu độ chính xác tài chính; hợp đồng cần chỉ rõ đơn vị và cách biểu diễn.

### 5.3. Tương thích schema sự kiện

Trong hệ thống event-driven, consumer có thể xử lý sự kiện được tạo từ phiên bản trước đó hoặc mới hơn. Cần xác định:

- Consumer có bỏ qua trường chưa biết không?
- Provider có giữ nguyên field number hoặc tag theo quy tắc serialization không?
- Có tái sử dụng field number đã xóa không?
- Consumer có xử lý sự kiện đến trễ hoặc sai thứ tự không?
- Sự kiện có thể được phát lại sau khi schema đã thay đổi không?
- Có registry và chính sách compatibility cho schema không?

Với Protocol Buffers, không tái sử dụng field number đã xóa; có thể dành riêng số và tên field đã bỏ để tránh xung đột khi schema tiến hóa. Với JSON Schema hoặc Avro, cách kiểm tra tương thích phụ thuộc dialect, reader/writer schema và cấu hình registry; cần dùng đúng quy tắc của hệ thống đang triển khai.

## 6. Đánh giá thay đổi hành vi, lỗi và bảo mật

Một hợp đồng có thể giữ nguyên cấu trúc nhưng vẫn thay đổi hành vi theo cách phá vỡ consumer.

Ví dụ:

- Endpoint trước đây trả kết quả đồng bộ, nay trả 202 Accepted và yêu cầu polling.
- API trước đây sắp xếp kết quả theo thời gian, nay không bảo đảm thứ tự.
- Một thao tác trước đây idempotent, nay tạo tác dụng phụ khi gọi lại.
- Lỗi validation trước đây trả 400, nay trả 422 hoặc đổi cấu trúc body.
- Token trước đây có quyền đọc, nay yêu cầu thêm scope.
- API trước đây cho phép lọc rộng, nay giới hạn trường truy vấn hoặc page size.
- Webhook trước đây gửi một lần, nay có thể gửi lại nhiều lần hoặc thay đổi thời gian retry.

Đánh giá tương thích phải xét cả điều kiện lỗi. Consumer có thể dựa vào status code, mã lỗi, thứ tự sự kiện hoặc thời gian phản hồi để điều khiển quy trình.

Thay đổi bảo mật cũng có thể là breaking change có chủ đích. Ví dụ, thu hồi cơ chế xác thực yếu hoặc siết quyền có thể làm consumer cũ ngừng hoạt động, nhưng vẫn cần thiết để giảm rủi ro. Khi đó, nhóm cần lập kế hoạch chuyển đổi credential, scope hoặc chứng chỉ, thông báo bên tích hợp và có mốc ngừng cơ chế cũ.

Không nên duy trì một lỗ hổng chỉ để giữ tương thích. Hãy đánh giá rủi ro bảo mật, nghĩa vụ và phương án chuyển đổi, sau đó quyết định phát hành có điều kiện, phiên bản mới hoặc thời điểm ngừng hỗ trợ phù hợp.

## 7. Dùng kiểm thử hợp đồng để xác minh tương thích

Kiểm thử hợp đồng xác minh rằng provider và consumer tuân thủ các giả định giao tiếp đã thống nhất. Nó giúp phát hiện sai lệch ở ranh giới dịch vụ trước khi lỗi xuất hiện trong kiểm thử đầu cuối hoặc production.

Có hai cách tiếp cận thường gặp:

- **Provider-driven contract:** provider công bố schema hoặc đặc tả làm nguồn chuẩn; kiểm thử xác minh implementation đáp ứng hợp đồng đó.
- **Consumer-driven contract:** consumer ghi lại những tương tác và giả định mà nó thực sự cần; provider chạy kiểm thử để xác minh vẫn đáp ứng các consumer đã đăng ký.

Hai cách có thể phối hợp. Đặc tả công khai giúp các bên hiểu API; contract test của consumer giúp phát hiện những giả định thực tế chưa được mô tả đầy đủ.

Một quy trình kiểm thử hợp đồng có thể gồm:

1. Lưu hợp đồng hiện tại và xác định phiên bản baseline.
2. Tạo thay đổi trên schema hoặc implementation.
3. Chạy công cụ diff để phát hiện thay đổi cấu trúc.
4. Phân loại thay đổi theo request, response, schema và hành vi.
5. Chạy provider contract test.
6. Chạy consumer contract test cho các consumer quan trọng.
7. Kiểm tra các trường hợp lỗi, enum, null, trường tùy chọn và giới hạn.
8. Lưu báo cáo diff, kết quả test và quyết định phê duyệt.

Ví dụ với OpenAPI, một công cụ diff có thể báo rằng một response field bị xóa hoặc một request field mới trở thành required. Kết quả này là tín hiệu để rà soát, không thay thế phân tích ngữ nghĩa. Công cụ không luôn biết consumer có phụ thuộc vào trường đó hoặc việc đổi đơn vị làm sai kết quả nghiệp vụ.

### 7.1. Ví dụ contract test cho consumer

Giả sử consumer đặt hàng cần nhận orderId, status và total. Hợp đồng tiêu dùng có thể mô tả phần tối thiểu mà consumer cần:

~~~json
{
  "orderId": "O-250",
  "status": "PAID",
  "total": 150000
}
~~~

Contract test nên xác minh provider vẫn trả các trường cần thiết với kiểu và ngữ nghĩa đúng. Nếu provider thêm paymentMethod, consumer có thể bỏ qua trường mới. Nếu provider đổi total thành object, test sẽ thất bại và yêu cầu nhóm đánh giá thay đổi.

### 7.2. Giới hạn của contract test

Contract test không chứng minh toàn bộ nghiệp vụ đầu cuối đúng. Nó có thể xác minh cấu trúc và tương tác được mô tả, nhưng không luôn phát hiện:

- Công thức tính toán sai nhưng vẫn đúng schema.
- Dữ liệu trả về thuộc nhầm khách hàng.
- Hiệu năng không đáp ứng tải.
- Thứ tự sự kiện sai nếu hợp đồng không mô tả.
- Consumer chưa đăng ký hoặc chưa có contract test.
- Hành vi thực tế khác môi trường kiểm thử.

Vì vậy, cần kết hợp contract test với kiểm thử tích hợp, kiểm thử chức năng, bảo mật và giám sát phù hợp.

## 8. Áp dụng chiến lược phiên bản và deprecation

Khi thay đổi phá vỡ không thể tránh, nhóm cần chọn cách quản lý phiên bản và chuyển đổi.

### 8.1. Phiên bản API

Một số cách phổ biến:

- **Phiên bản trong URL:** /v1/orders, /v2/orders.
- **Phiên bản qua header:** client gửi header chỉ định phiên bản.
- **Phiên bản qua media type:** dùng content negotiation để chọn biểu diễn.
- **Tiến hóa không tạo phiên bản mới:** thêm trường và hành vi theo quy tắc tương thích đã công bố.

Không có một cách duy nhất phù hợp cho mọi API. Phiên bản URL dễ quan sát và định tuyến; header hoặc media type có thể giữ URL ổn định nhưng cần công cụ và quy trình rõ. Điều quan trọng là định nghĩa cách chọn phiên bản, thời gian hỗ trợ, cách thông báo và chính sách bảo trì.

Không nên tạo phiên bản mới cho mọi thay đổi nhỏ. Nếu mọi bổ sung đều tạo /v2, chi phí vận hành và số lượng phiên bản cần hỗ trợ sẽ tăng nhanh. Ngược lại, cố giữ một phiên bản duy nhất dù hợp đồng đã thay đổi phá vỡ có thể làm consumer hỏng bất ngờ.

### 8.2. Deprecation và sunset

Deprecation là thông báo một phần API sẽ không còn được khuyến nghị hoặc sẽ bị loại bỏ trong tương lai. Sunset là mốc hoặc giai đoạn kết thúc cung cấp phần API đó theo chính sách đã công bố.

Một kế hoạch deprecation nên có:

- Thành phần hoặc hành vi bị deprecate.
- Lý do và tác động.
- API hoặc cách sử dụng thay thế.
- Ngày bắt đầu thông báo.
- Mốc kết thúc hỗ trợ hoặc sunset.
- Hướng dẫn chuyển đổi và ví dụ mã.
- Cách theo dõi consumer còn sử dụng.
- Kênh hỗ trợ và người liên hệ.
- Quy trình ngoại lệ cho consumer chưa thể chuyển đổi.

Có thể dùng cảnh báo trong tài liệu, response header hoặc dashboard tích hợp để thông báo. Nếu dùng header tiêu chuẩn như Deprecation hoặc Sunset, cần tuân theo định dạng và ý nghĩa được định nghĩa cho header đó.

### 8.3. Giai đoạn chuyển tiếp

Một lộ trình thường dùng:

1. Công bố hợp đồng mới và hướng dẫn chuyển đổi.
2. Provider hỗ trợ song song cách cũ và mới.
3. Consumer cập nhật và chạy contract test.
4. Theo dõi telemetry để xác nhận consumer đã chuyển.
5. Nhắc các consumer còn sử dụng phiên bản cũ.
6. Ngừng nhận yêu cầu mới trên API cũ theo kế hoạch.
7. Loại bỏ phiên bản cũ sau khi đáp ứng điều kiện sunset.

Không nên tắt API cũ chỉ vì phần lớn lưu lượng đã chuyển. Cần xác minh các consumer còn lại, nghĩa vụ hợp đồng và các tác vụ ít xảy ra. Với đối tác bên ngoài, có thể cần thời gian thông báo dài hơn và quy trình phê duyệt riêng.

## 9. Triển khai thay đổi an toàn với chiến lược expand-and-contract

Expand-and-contract là cách triển khai thay đổi schema hoặc API theo nhiều bước để phiên bản cũ và mới có thể cùng tồn tại trong giai đoạn chuyển tiếp.

Ví dụ cần đổi trường customerName thành displayName:

**Bước 1 – Expand:** thêm displayName và tiếp tục hỗ trợ customerName. Provider có thể đọc cả hai, xác định quy tắc ưu tiên rõ ràng và ghi dữ liệu theo cách giữ được khả năng tương thích.

**Bước 2 – Migrate:** cập nhật consumer để đọc displayName; chuyển dữ liệu hoặc ghi đồng thời nếu cần. Theo dõi consumer nào vẫn sử dụng trường cũ.

**Bước 3 – Verify:** chạy contract test cho cả consumer cũ và mới, kiểm tra dữ liệu, log và telemetry. Xác nhận không còn phụ thuộc vào trường cũ trong phạm vi đã xác định.

**Bước 4 – Contract:** sau thời gian chuyển tiếp và khi đủ điều kiện, loại bỏ customerName trong phiên bản hoặc mốc sunset đã công bố.

Quy trình này cần được thiết kế cẩn thận nếu dữ liệu được ghi bởi nhiều phiên bản ứng dụng hoặc có migration không thể đảo ngược. Hãy xác định khả năng rollback, cách đồng bộ hai trường và nguồn dữ liệu chuẩn trong giai đoạn ghi kép.

## 10. Quản lý thay đổi phá vỡ ở hệ thống sự kiện và thư viện

API đồng bộ không phải loại hợp đồng duy nhất. Schema sự kiện, message queue, SDK và thư viện dùng chung cũng có consumer phụ thuộc.

Với event-driven systems, hãy xem xét:

- Thêm trường optional có được consumer cũ bỏ qua không?
- Consumer mới có đọc được sự kiện cũ không?
- Producer cũ có tạo đủ dữ liệu cho consumer mới không?
- Thay đổi enum hoặc thứ tự sự kiện có làm consumer lỗi không?
- Có cần giữ schema cũ để replay sự kiện không?
- Registry đang áp dụng chế độ backward, forward hay full compatibility?

Với thư viện hoặc SDK, cần kiểm tra source và binary compatibility, thay đổi method signature, constructor, exception, visibility, dependency và hành vi mặc định. Thay đổi public method có thể yêu cầu major version theo chính sách Semantic Versioning của dự án, nhưng nhãn phiên bản không tự chứng minh rằng mọi consumer tương thích.

Với database schema dùng chung, cân nhắc thứ tự triển khai giữa ứng dụng và schema. Ứng dụng cũ có thể tiếp tục đọc cột cũ trong khi ứng dụng mới ghi cột mới; vì vậy migration cần tương thích trong giai đoạn chuyển tiếp.

## 11. Đánh giá tác động và phê duyệt thay đổi

Trước khi phê duyệt thay đổi hợp đồng, hãy lập hồ sơ tác động. Hồ sơ cần cho biết thay đổi nào, ai bị ảnh hưởng, rủi ro nào tăng, bằng chứng nào đã có và kế hoạch chuyển đổi ra sao.

Một ma trận đánh giá:

| Hạng mục | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Cấu trúc | Trường, kiểu, endpoint, enum hoặc schema nào thay đổi? | Diff hợp đồng |
| Ngữ nghĩa | Đơn vị, ý nghĩa, trạng thái hoặc quy tắc nghiệp vụ có đổi không? | Đặc tả và rà soát nghiệp vụ |
| Consumer | Ai sử dụng phần bị thay đổi? | Danh mục consumer, telemetry và hợp đồng |
| Tương thích | Consumer cũ và mới có tiếp tục hoạt động không? | Contract test và integration test |
| Bảo mật | Quyền, token, scope hoặc dữ liệu nhạy cảm có thay đổi không? | Rà soát bảo mật và kiểm thử phân quyền |
| Vận hành | Timeout, retry, rate limit hoặc thứ tự sự kiện có đổi không? | Kiểm thử lỗi, tải và tài liệu vận hành |
| Triển khai | Có giai đoạn chạy song song, rollback hoặc migration không? | Kế hoạch rollout và kiểm thử chuyển đổi |
| Truyền thông | Ai cần thông báo, trước bao lâu và qua kênh nào? | Kế hoạch deprecation và hướng dẫn |
| Phê duyệt | Ai chấp nhận rủi ro và điều kiện phát hành? | Quyết định có người chịu trách nhiệm |

Một thay đổi phá vỡ có thể được chấp nhận nếu có lý do rõ ràng, chẳng hạn sửa lỗi bảo mật, loại bỏ hành vi sai hoặc thay đổi nghiệp vụ đã được thống nhất. Tuy nhiên, quyết định phải xem xét thời gian chuyển đổi, khách hàng bị ảnh hưởng và chi phí duy trì phiên bản cũ.

## 12. Ví dụ: đổi hợp đồng API của dịch vụ đơn hàng

Giả sử API GET /orders/{id} hiện trả về:

~~~json
{
  "id": "O-250",
  "status": "PAID",
  "total": 150000
}
~~~

Nhóm muốn cải thiện mô hình tiền tệ bằng cách trả total dưới dạng object:

~~~json
{
  "id": "O-250",
  "status": "PAID",
  "total": {
    "amount": 150000,
    "currency": "VND"
  }
}
~~~

Thay đổi này giúp biểu diễn tiền rõ hơn nhưng làm consumer cũ không thể đọc total như một số. Nhóm thực hiện đánh giá:

1. Tìm các consumer đang đọc total, gồm ứng dụng web, mobile, báo cáo và đối tác.
2. Kiểm tra SDK và contract test để xác định giả định về kiểu dữ liệu.
3. Phân loại đây là thay đổi phá vỡ ở response schema.
4. Quyết định tạo phiên bản API mới hoặc thêm trường mới trong giai đoạn chuyển tiếp.
5. Cập nhật consumer theo từng nhóm và chạy contract test.
6. Theo dõi telemetry để biết consumer cũ còn sử dụng không.
7. Công bố thời điểm deprecation và sunset.
8. Chỉ loại trường cũ sau khi đạt điều kiện chuyển đổi và được phê duyệt.

Một response chuyển tiếp có thể là:

~~~json
{
  "id": "O-250",
  "status": "PAID",
  "total": 150000,
  "money": {
    "amount": 150000,
    "currency": "VND"
  }
}
~~~

Trong giai đoạn này, hai trường phải có quy tắc nhất quán. Nhóm cần xác định trường nào là nguồn chuẩn, cách xử lý khi dữ liệu không khớp và thời điểm ngừng trả total. Nếu không kiểm soát điều đó, consumer có thể nhận hai giá trị khác nhau và đưa ra quyết định sai.

## 13. Checklist đánh giá tương thích hợp đồng

Trước khi merge hoặc phát hành thay đổi API, hãy kiểm tra:

- Đã xác định provider, consumer và phiên bản đang được sử dụng chưa?
- Hợp đồng nguồn có phiên bản và chủ sở hữu rõ ràng không?
- Thay đổi đã được phân loại theo request, response, schema, hành vi và ngữ nghĩa chưa?
- Trường required, optional, null, enum, kiểu, định dạng và giới hạn có thay đổi không?
- Mã trạng thái, cấu trúc lỗi, xác thực, quyền, retry và timeout có thay đổi không?
- Consumer có thể xử lý trường hoặc giá trị chưa biết không?
- Có thay đổi đơn vị, múi giờ, thứ tự, idempotency hoặc semantics không?
- Contract test của provider và consumer có bao phủ giả định quan trọng không?
- Đã chạy integration test hoặc kiểm tra hành vi trên môi trường phù hợp chưa?
- Có kế hoạch versioning, deprecation, sunset và hướng dẫn chuyển đổi không?
- Giai đoạn chạy song song và cách rollback đã được kiểm thử chưa?
- Telemetry có thể xác định consumer còn dùng hợp đồng cũ không?
- Người chịu trách nhiệm và quyết định chấp nhận rủi ro đã được ghi lại chưa?

Sơ đồ sau tóm tắt quy trình đánh giá và xử lý thay đổi hợp đồng:

~~~mermaid
flowchart TD
    A["Đề xuất thay đổi API hoặc schema"] --> B["Xác định provider, consumer và baseline"]
    B --> C["Phân tích cấu trúc, hành vi và ngữ nghĩa"]
    C --> D["Chạy diff và contract test"]
    D --> E{"Có phá vỡ tương thích?"}
    E -->|Không| F["Xác minh hồi quy và phê duyệt"]
    E -->|Có| G["Chọn versioning hoặc lộ trình chuyển đổi"]
    G --> H["Expand: hỗ trợ cách cũ và mới"]
    H --> I["Migrate consumer và theo dõi sử dụng"]
    I --> J["Verify: kiểm tra hợp đồng và dữ liệu"]
    J --> K{"Đủ điều kiện sunset?"}
    K -->|Chưa| I
    K -->|Có| L["Contract: loại bỏ hợp đồng cũ"]
    F --> M["Phát hành và giám sát"]
    L --> M
~~~

Đánh giá tương thích hợp đồng giúp nhóm dự đoán tác động trước khi consumer bị gián đoạn. Một thay đổi chỉ nên được xem là an toàn khi cấu trúc, hành vi và ngữ nghĩa vẫn đáp ứng các bên sử dụng trong phạm vi đã xác định. Khi thay đổi phá vỡ là cần thiết, versioning, deprecation, kiểm thử hợp đồng và lộ trình chuyển đổi giúp các bên cập nhật có kiểm soát, giữ được bằng chứng và giảm rủi ro trong quá trình phát hành.

