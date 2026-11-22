# Khi nào nên dùng REST và khi nào nên chọn cách tích hợp khác

REST là một lựa chọn tốt cho nhiều API, nhưng không phải mọi cuộc trao đổi dữ liệu đều nên được thiết kế thành các endpoint REST. Một màn hình cần tổng hợp dữ liệu từ nhiều miền, một luồng video, một phép tính nội bộ cần độ trễ thấp và một quy trình thanh toán kéo dài có những yêu cầu khác nhau.

Trong phạm vi **INTEGRATION_API_REST**, bài học này giúp bạn chọn REST có căn cứ, nhận ra giới hạn của nó và phối hợp với các cách tích hợp khác. Trọng tâm là quyết định kiến trúc ở mức tổng quan; các ví dụ dùng tài nguyên đơn hàng để nối quyết định đó với URI, phương thức HTTP, mã trạng thái và hợp đồng dữ liệu.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Nhận diện tình huống phù hợp với API dựa trên tài nguyên và ngữ nghĩa HTTP.
- So sánh REST với RPC/gRPC, GraphQL, thông điệp, sự kiện, webhook, SSE, WebSocket và trao đổi theo lô.
- Phân biệt yêu cầu cần câu trả lời ngay với công việc có thể hoàn tất sau.
- Giải thích vì sao cache, idempotency, xác thực, phân quyền và khả năng vận hành ảnh hưởng đến lựa chọn tích hợp.
- Đề xuất một phương án kết hợp nhiều cách tích hợp trong cùng hệ thống.

## 2. Hiểu đúng các lựa chọn trước khi so sánh

### 2.1. REST là phong cách kiến trúc, không phải tên khác của HTTP + JSON

REST tổ chức tương tác quanh **tài nguyên** và các **biểu diễn** của tài nguyên. Trong một API HTTP hướng tài nguyên, ví dụ:

```http
GET /orders/ord-1042 HTTP/1.1
Accept: application/json
```

Máy khách yêu cầu biểu diễn của tài nguyên đơn hàng; máy chủ trả trạng thái, header và dữ liệu tương ứng. URI định danh tài nguyên, phương thức biểu đạt loại thao tác, còn mã trạng thái cho biết kết quả xử lý theo ngữ nghĩa HTTP.

REST còn gắn với các ràng buộc như phân tách client–server, tương tác stateless, khả năng khai báo cache, giao diện thống nhất và hệ thống phân lớp. Giao diện thống nhất bao gồm cả việc sử dụng liên kết và điều khiển trong biểu diễn để dẫn dắt tương tác. Vì vậy, chỉ có endpoint, JSON và các phương thức CRUD chưa đủ để khẳng định đã đáp ứng đầy đủ REST.

Trong thực tế, nhiều API được gọi là REST API chỉ áp dụng một phần các ràng buộc trên. Khi chọn giải pháp, hãy mô tả chính xác những đặc tính mình cần: tài nguyên ổn định, ngữ nghĩa HTTP rõ, khả năng cache, liên kết, tính stateless hay hợp đồng dễ sử dụng. Tên gọi không thay thế cho các đặc tính đó.

**Stateless không có nghĩa là máy chủ không được lưu dữ liệu.** Máy chủ vẫn lưu đơn hàng, tài khoản và trạng thái nghiệp vụ. Điều cần tránh là buộc một request phải dựa vào ngữ cảnh hội thoại chỉ tồn tại trong bộ nhớ của một instance từ request trước. Mỗi request phải mang đủ thông tin cần thiết để được xử lý, bao gồm thông tin xác thực thích hợp.

### 2.2. Các lựa chọn nằm trên những trục khác nhau

| Trục quyết định | Câu hỏi | Ví dụ |
|---|---|---|
| Mô hình tương tác | Hai bên giao tiếp theo cách nào? | Request–response, thông điệp bất đồng bộ, publish–subscribe, luồng liên tục, xử lý theo lô |
| Cách mô tả thao tác và dữ liệu | Máy khách nhìn thấy tài nguyên, hàm hay đồ thị? | REST, RPC, GraphQL |
| Cơ chế truyền và phân phối | Dữ liệu đi đến bên nhận bằng cách nào? | HTTP, SSE, WebSocket, broker thông điệp, tệp được chuyển theo lịch |
| Hợp đồng | Hai bên thống nhất cấu trúc và hành vi ra sao? | OpenAPI, schema GraphQL, Protocol Buffers, schema sự kiện, WSDL |

Các nhóm này có thể kết hợp. GraphQL có thể hoạt động trên HTTP; webhook thường gửi HTTP request; SSE dùng HTTP để mở luồng sự kiện từ server tới client. Việc dùng HTTP không tự biến chúng thành REST.

Tương tự, **bất đồng bộ không đồng nghĩa với phải dùng broker**. Một API HTTP có thể nhận công việc, trả tài nguyên theo dõi và cho client truy vấn kết quả sau. Broker chỉ là một lựa chọn cho việc phân phối và xử lý phía sau.

## 3. Khi nào REST thường là lựa chọn phù hợp?

### 3.1. Miền nghiệp vụ có tài nguyên rõ và vòng đời dễ diễn đạt

REST phù hợp khi các bên cần làm việc với những khái niệm có danh tính ổn định: khách hàng, đơn hàng, hóa đơn, sản phẩm, tài liệu hoặc yêu cầu xuất báo cáo.

Một thiết kế minh họa:

| Nhu cầu | Tương tác HTTP có thể dùng | Ý nghĩa |
|---|---|---|
| Xem một đơn hàng | `GET /orders/{orderId}` | Đọc biểu diễn hiện tại |
| Tìm đơn hàng | `GET /orders?status=PAID&limit=20` | Đọc một tập tài nguyên có điều kiện và giới hạn |
| Tạo đơn hàng | `POST /orders` | Yêu cầu tạo tài nguyên mới trong collection |
| Thay thế địa chỉ giao hàng | `PUT /orders/{orderId}/shipping-address` | Đặt biểu diễn mới cho tài nguyên địa chỉ, nếu vòng đời cho phép |
| Đề nghị hủy đơn hàng | `POST /orders/{orderId}/cancellations` | Tạo yêu cầu hủy với quy tắc và trạng thái riêng |

Ví dụ cuối cho thấy REST không giới hạn ở CRUD đơn giản. Một hành động nghiệp vụ có thể được mô hình hóa thành tài nguyên yêu cầu, với điều kiện mô hình đó phản ánh đúng ý nghĩa nghiệp vụ. Không nên tạo tài nguyên giả chỉ để mọi URI trông giống danh từ.

### 3.2. Máy khách cần kết quả trong một lượt trao đổi

REST thuận tiện khi client gửi yêu cầu và cần phản hồi đủ nhanh để tiếp tục: hiển thị chi tiết sản phẩm, kiểm tra quyền truy cập, lưu thông tin liên hệ hoặc tạo đơn hàng trong cơ sở dữ liệu.

Cần xác định **ranh giới hoàn tất**. `201 Created` cho việc tạo đơn hàng không có nghĩa là toàn bộ quy trình giao hàng, thanh toán và gửi email đã hoàn thành. Nó chỉ xác nhận kết quả thuộc hợp đồng của thao tác tạo đó.

Nếu yêu cầu phải chờ một chuỗi dịch vụ dài, REST vẫn có thể là giao diện nhận việc, nhưng không nên giữ kết nối chỉ để đợi tất cả công đoạn kết thúc. Cách biểu diễn công việc chạy nền được trình bày ở phần sau.

### 3.3. API có nhiều loại máy khách và cần khả năng tương tác rộng

Một HTTP API với hợp đồng rõ thường dễ tiếp cận từ trình duyệt, ứng dụng di động, hệ thống đối tác, công cụ dòng lệnh và nhiều ngôn ngữ lập trình. Header, mã trạng thái, công cụ kiểm thử và hạ tầng HTTP giúp giảm chi phí tích hợp.

Điều này đặc biệt hữu ích cho API công khai hoặc API đối tác khi bạn không kiểm soát toàn bộ công nghệ của bên gọi. Tuy nhiên, **REST không tự tạo ra tính tương thích**. API vẫn cần:

- Schema request và response rõ, bao gồm kiểu dữ liệu, field bắt buộc và ý nghĩa của giá trị.
- Quy ước phân trang, bộ lọc, thứ tự sắp xếp và định dạng lỗi.
- Quy tắc thay đổi hợp đồng và thời gian hỗ trợ phiên bản.
- Cơ chế xác thực, phạm vi quyền, giới hạn tần suất và tài liệu sử dụng.

OpenAPI giúp mô tả hợp đồng của một HTTP API và hỗ trợ công cụ, nhưng không tự chứng minh API tuân thủ đầy đủ REST hoặc xử lý đúng nghiệp vụ.

### 3.4. Dữ liệu đọc nhiều và có thể hưởng lợi từ cache HTTP

Danh mục sản phẩm công khai, thông tin cấu hình ít thay đổi hoặc nội dung tĩnh có thể hưởng lợi từ cache ở client, proxy hoặc CDN khi response được khai báo phù hợp.

Ví dụ một response dành riêng cho người dùng:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=30
ETag: "order-1042-v7"

{"id":"ord-1042","status":"CONFIRMED"}
```

Client có thể gửi `If-None-Match` khi cần kiểm tra lại; server có thể trả `304 Not Modified` nếu điều kiện phù hợp. Khả năng này làm REST trên HTTP hấp dẫn khi nhiều lần đọc cùng một biểu diễn.

Tuy nhiên:

- Không phải response REST nào cũng được cache hoặc nên cache.
- `private` cho phép cache riêng và ngăn cache dùng chung lưu response; nó không có nghĩa là cấm mọi lưu trữ. Dữ liệu cần cấm lưu phải có chính sách thích hợp, chẳng hạn `no-store`.
- Response chứa dữ liệu cá nhân hoặc phụ thuộc quyền truy cập cần quy tắc cache chặt chẽ. Không áp dụng chính sách cache công khai chỉ để tăng tốc.
- Một hệ thống nhạy với độ mới dữ liệu cần cân nhắc thời gian sống, tái xác thực và các đường cập nhật.

### 3.5. Hệ sinh thái vận hành đã thuận lợi cho HTTP

REST thường hợp lý khi đội ngũ đã có gateway, cơ chế xác thực, theo dõi request, kiểm thử hợp đồng và quy trình quản lý HTTP API. Với Java/Spring hoặc công nghệ tương đương, đây thường là con đường triển khai dễ hiểu đối với cả đội phát triển lẫn đội tích hợp.

Dù vậy, thư viện thuận tiện chỉ là một yếu tố. Hãy tính cả việc quản lý timeout, retry, phân trang, lỗi, quyền theo tài nguyên và tương thích hợp đồng. Một controller trả JSON chưa giải quyết những yêu cầu đó.

## 4. Khi nào nên cân nhắc cách tích hợp khác?

### 4.1. RPC/gRPC: hợp đồng thao tác rõ, kết nối nội bộ được kiểm soát

RPC nhìn hệ thống qua các thao tác có đầu vào và đầu ra, chẳng hạn `CalculateShippingCost` hoặc `EvaluateFraudRisk`. gRPC là một nền tảng RPC với hợp đồng dịch vụ, khả năng sinh mã và các kiểu tương tác một lần hoặc streaming.

Nên cân nhắc khi:

- Hai đầu giao tiếp nằm trong môi trường bạn kiểm soát được và có thể dùng công cụ sinh mã.
- Miền nghiệp vụ tự nhiên giống lời gọi thao tác hơn là quản lý một tập tài nguyên.
- Có nhiều trao đổi nội bộ, cần schema chặt và muốn đánh giá lợi ích của biểu diễn nhị phân.
- Cần client streaming, server streaming hoặc trao đổi hai chiều theo hợp đồng dịch vụ.

Chi phí cần chấp nhận gồm quản lý mã sinh, tương thích schema, hạ tầng proxy/gateway và công cụ quan sát phù hợp. Với trình duyệt, cần kiểm tra đường truy cập như gRPC-Web hoặc gateway thay vì giả định gọi được giống một HTTP API thông thường.

**Không kết luận gRPC luôn nhanh hơn REST.** Kích thước payload, số lượt gọi, chi phí nghiệp vụ, kết nối, nén và điều kiện mạng đều ảnh hưởng. Nếu hiệu năng là lý do chính, hãy đo với tải và payload đại diện.

REST vẫn có thể biểu diễn phép tính bằng tài nguyên yêu cầu tính toán. Điểm quyết định là cách nào tạo hợp đồng tự nhiên và chi phí vận hành hợp lý hơn, không phải một quy tắc cấm động từ tuyệt đối.

### 4.2. GraphQL: nhiều giao diện cần các hình dạng dữ liệu khác nhau

Giả sử trang chi tiết đơn hàng cần tên khách hàng, trạng thái đơn, năm dòng hàng đầu và thông tin giao hàng. Ứng dụng di động chỉ cần mã đơn và trạng thái. Một API có biểu diễn cố định có thể trả thừa dữ liệu hoặc buộc client gọi nhiều lần.

GraphQL đáng cân nhắc khi nhiều client cần lựa chọn các field và quan hệ khác nhau trên một schema dùng chung. Client có thể diễn đạt nhu cầu dữ liệu trong một query thay vì tự ghép nhiều response.

Những điểm phải thiết kế thêm:

- Giới hạn độ sâu, độ phức tạp, số lượng kết quả và thời gian thực thi truy vấn.
- Tránh vấn đề N+1 và kiểm soát số lượt truy cập cơ sở dữ liệu/dịch vụ phía sau.
- Kiểm tra quyền ở mức đối tượng và field theo nhu cầu nghiệp vụ.
- Thiết kế phân trang, tiến hóa schema và khả năng quan sát theo thao tác.
- Xây dựng chiến lược cache phù hợp; không mặc định có cùng cách cache theo URI như các GET đơn giản.

Một query GraphQL không bảo đảm backend chỉ thực hiện một lần gọi, cũng không tự loại bỏ độ trễ. Trước khi chuyển đổi, hãy xem một tài nguyên tổng hợp hoặc lớp backend dành cho từng loại giao diện có giải quyết được vấn đề với ít chi phí hơn không.

### 4.3. Hàng đợi và sự kiện: công việc dài, nhiều bên quan tâm, chịu lỗi độc lập

Khi tạo đơn hàng cần gửi email, cập nhật kho tìm kiếm và ghi nhận điểm thưởng, việc gọi đồng bộ tất cả dịch vụ làm request phụ thuộc vào nhiều hệ thống. Chỉ một dịch vụ chậm cũng có thể làm toàn bộ đường xử lý chậm hoặc thất bại.

Tích hợp qua thông điệp phù hợp khi công việc có thể hoàn tất sau, cần hấp thụ tải đột biến hoặc cần tách vòng đời xử lý của các dịch vụ.

Phân biệt hai ý nghĩa:

| Loại | Ví dụ | Kỳ vọng |
|---|---|---|
| Lệnh | `ReserveInventory` | Yêu cầu một bên chịu trách nhiệm thực hiện công việc |
| Sự kiện | `OrderConfirmed` | Thông báo một sự thật đã xảy ra để các bên quan tâm phản ứng |

Một lệnh có thể bị từ chối. Một sự kiện mô tả việc đã xảy ra; bên nhận có thể xử lý sự kiện đó thất bại, nhưng thất bại này không tự xóa sự thật đã công bố.

Khi chọn bất đồng bộ, phải trả lời thêm:

- Bên gửi biết thông điệp đã được lưu hoặc được tiếp nhận bằng cách nào?
- Nếu gửi trùng hoặc nhận trùng, tác dụng nghiệp vụ được bảo vệ ra sao?
- Thứ tự được bảo đảm trong phạm vi nào: từng đơn hàng, từng partition hay toàn bộ luồng?
- Dữ liệu hiển thị có thể chậm cập nhật bao lâu?
- Thông điệp lỗi sẽ được retry, cách ly, cảnh báo và phát lại như thế nào?
- Schema sự kiện thay đổi mà vẫn hỗ trợ consumer cũ ra sao?

Trong các thiết kế có khả năng phân phối lặp, consumer cần xử lý idempotent. Việc ghi cơ sở dữ liệu và phát sự kiện cũng phải tránh khoảng trống như “đã lưu đơn nhưng chưa gửi sự kiện”; transactional outbox là một mẫu có thể cân nhắc cho vấn đề này.

Một broker không tự bảo đảm toàn bộ nghiệp vụ được thực hiện đúng một lần. Không nên suy từ tên của cơ chế phân phối sang bảo đảm đầu cuối của thanh toán, gửi email hoặc trừ tồn kho.

### 4.4. Webhook: thông báo ra ngoài khi có thay đổi

Webhook phù hợp khi đối tác cần được báo có sự kiện nhưng không muốn liên tục hỏi trạng thái. Ví dụ, hệ thống thanh toán gửi HTTP request tới endpoint do cửa hàng đăng ký khi giao dịch đổi trạng thái.

Thiết kế webhook cần có:

- Cách xác minh nguồn gửi, chẳng hạn chữ ký trên nội dung và quy tắc chống phát lại phù hợp.
- Danh tính sự kiện để xử lý trùng và liên kết với tài nguyên nghiệp vụ.
- Timeout, chính sách retry và thời gian lưu để gửi lại khi phía nhận gặp lỗi.
- Quy tắc phản hồi: ACK là đã nhận bền vững hay đã xử lý xong nghiệp vụ?
- Cách truy vấn trạng thái hiện tại hoặc đối soát khi bỏ lỡ thông báo.

Không giả định webhook đến đúng thứ tự hoặc chỉ đến một lần nếu hợp đồng không quy định và triển khai không bảo đảm điều đó. Một webhook nên giúp bên nhận biết cần cập nhật; REST có thể cung cấp tài nguyên để bên nhận đọc lại trạng thái chính xác theo quyền được cấp.

### 4.5. SSE và WebSocket: cập nhật liên tục

Một màn hình theo dõi tiến độ cần nhận thay đổi thường xuyên. Polling bằng `GET` vẫn là lựa chọn đơn giản nếu độ trễ vài giây hoặc vài chục giây chấp nhận được và tải phù hợp. Khi yêu cầu thay đổi, có thể cân nhắc:

| Nhu cầu | Lựa chọn cần cân nhắc | Điểm chú ý |
|---|---|---|
| Chủ yếu server gửi cập nhật tới client | SSE | Luồng sự kiện qua HTTP, cần xử lý kết nối lại và giới hạn kết nối |
| Hai bên cần gửi dữ liệu liên tục | WebSocket | Kết nối hai chiều, cần giao thức ứng dụng, quản lý kết nối và áp lực tải |
| Có thể chấp nhận cập nhật theo chu kỳ | Polling REST | Dễ vận hành, cần chu kỳ hợp lý và điều kiện cache/tái xác thực khi thích hợp |

SSE và WebSocket không thay thế tự động các tài nguyên quản lý đơn hàng hoặc người dùng. Chúng thường bổ sung đường truyền cập nhật. Khi client kết nối lại, hệ thống vẫn cần cách đồng bộ trạng thái và xác định sự kiện nào đã bỏ lỡ.

SSE có cơ chế định danh sự kiện và hỗ trợ kết nối lại ở client phù hợp, nhưng server vẫn phải lưu và triển khai khả năng phát lại nếu cần khôi phục sự kiện. WebSocket cũng không tự cung cấp lưu trữ bền vững, phát lại hay phân phối đúng một lần.

### 4.6. SOAP hoặc hợp đồng tích hợp có sẵn: ưu tiên khả năng tương tác thực tế

Nếu đối tác chỉ hỗ trợ một dịch vụ SOAP với WSDL và các yêu cầu bảo mật tương ứng, lựa chọn giao thức phải bắt đầu từ hợp đồng đó. Việc REST phổ biến trong một đội không làm hợp đồng của đối tác biến mất.

SOAP là một giao thức thông điệp, không phải phong cách tài nguyên tương đương trực tiếp với REST. Một số hệ sinh thái dùng các đặc tả WS-* cho nhu cầu bổ sung; không phải mọi dịch vụ SOAP đều triển khai toàn bộ các đặc tả này.

Có thể dùng adapter để cách ly chi tiết SOAP ở biên tích hợp, rồi cung cấp giao diện phù hợp hơn cho phần còn lại của hệ thống. Adapter vẫn cần xử lý ánh xạ lỗi, timeout, retry và khả năng tương thích; nó không xóa các ràng buộc của phía đối tác.

### 4.7. Trao đổi theo lô hoặc tệp: dữ liệu lớn, không cần tức thời

Đồng bộ hàng triệu bản ghi mỗi đêm, chuyển báo cáo đối soát hoặc nhập dữ liệu ban đầu không nhất thiết nên thực hiện bằng một request REST cho mỗi bản ghi.

Một luồng xuất/nhập theo lô có thể phù hợp hơn khi chấp nhận độ trễ theo lịch và cần kiểm soát kích thước, checksum, schema tệp, mã đợt xử lý và khả năng chạy lại. Đổi lại, phải quản lý các bản ghi lỗi, phiên bản định dạng, quyền truy cập tệp và đối soát kết quả.

REST có thể quản lý công việc theo lô: tạo đợt xuất, xem trạng thái, lấy vị trí tải kết quả. Dữ liệu thực tế có thể được truyền qua một cơ chế khác phù hợp với dung lượng và hạ tầng.

## 5. Bảng định hướng lựa chọn

Bảng dưới đây là điểm bắt đầu cho thảo luận. Một yêu cầu riêng lẻ không đủ để quyết định toàn bộ kiến trúc.

| Tình huống nổi bật | Lựa chọn nên đánh giá trước | Điều cần kiểm chứng |
|---|---|---|
| API đối tác quản lý khách hàng, đơn hàng, sản phẩm | REST trên HTTP | Hợp đồng, quyền theo tài nguyên, phiên bản và giới hạn tải |
| Đọc cùng một biểu diễn nhiều lần | REST kết hợp cache HTTP | Độ mới dữ liệu, chính sách cache và bảo vệ dữ liệu cá nhân |
| Nhiều giao diện cần dữ liệu với hình dạng rất khác nhau | GraphQL hoặc lớp tổng hợp trên REST | Độ phức tạp query, số lần truy cập backend và phân quyền |
| Lời gọi nội bộ có schema chặt, cần streaming | gRPC | Hạ tầng hỗ trợ, tương thích và kết quả đo thực tế |
| Công việc dài hoặc cần tiếp tục khi một bên tạm ngừng | Hàng đợi/thông điệp, có thể kết hợp REST | Lưu bền vững, retry, trùng lặp và trạng thái công việc |
| Nhiều dịch vụ cùng phản ứng trước một thay đổi | Publish–subscribe với sự kiện | Schema, phạm vi thứ tự và tính nhất quán cuối cùng |
| Đối tác cần nhận thông báo thay đổi | Webhook và API truy vấn/đối soát | Chữ ký, retry, trùng lặp và mất thông báo |
| Màn hình nhận cập nhật một chiều liên tục | SSE | Đồng bộ lại, timeout trung gian và số kết nối |
| Trao đổi tương tác hai chiều liên tục | WebSocket | Giao thức ứng dụng, áp lực tải và quản lý kết nối |
| Đối tác yêu cầu SOAP/WSDL | SOAP qua adapter nếu cần | Hợp đồng thực tế và các yêu cầu bảo mật liên quan |
| Đồng bộ lượng dữ liệu lớn theo lịch | Batch/tệp hoặc cơ chế truyền khối lượng lớn | Khả năng tiếp tục, đối soát và xử lý lỗi từng phần |

## 6. Quy trình ra quyết định từ yêu cầu cụ thể

### Bước 1: Xác định kết quả nghiệp vụ và thời hạn

Thay vì hỏi ngay “dùng REST hay gRPC?”, hãy viết một câu có thể kiểm chứng:

> Khi người dùng gửi đơn hàng, hệ thống phải xác nhận đã tạo đơn trong ngân sách độ trễ đã thỏa thuận; email được gửi sau và có thể retry độc lập.

Câu này tách việc cần trả lời ngay khỏi việc được phép hoàn tất sau. Nếu nghiệp vụ yêu cầu thanh toán được xác nhận trước khi chấp nhận đơn, ranh giới xử lý sẽ khác; không được chọn bất đồng bộ chỉ để bỏ qua yêu cầu đó.

### Bước 2: Xác định bên gọi, bên nhận và môi trường

Hỏi ai kiểm soát client, những ngôn ngữ nào được dùng, có trình duyệt không, proxy/gateway cho phép gì và đối tác đã có hợp đồng nào. Một lựa chọn tốt trong nội bộ chưa chắc phù hợp với API công khai.

### Bước 3: Xem hình dạng dữ liệu và hướng trao đổi

Một tài nguyên được đọc theo URI, một phép tính, một truy vấn đồ thị và một luồng sự kiện có cách diễn đạt khác nhau. Đồng thời xác định bên nào khởi đầu, dữ liệu đi một hay hai chiều và có cần một hay nhiều bên nhận.

### Bước 4: Xác định điều gì xảy ra khi chậm, lỗi hoặc mất kết nối

Với request đồng bộ, timeout tạo ra một tình huống quan trọng: **client không biết kết quả không có nghĩa là server chưa thực hiện thao tác**. Với thông điệp bất đồng bộ, không có ACK cũng không đủ để suy ra thông điệp chắc chắn chưa được nhận.

Thiết kế phải nêu rõ cách retry, phát hiện trùng, truy vấn kết quả và khôi phục. Đừng chờ đến lúc chọn xong giao thức mới bổ sung các câu trả lời này.

### Bước 5: Kiểm tra yêu cầu phi chức năng và năng lực vận hành

So sánh dựa trên payload, lưu lượng, độ trễ, khả năng tăng tải, chi phí hạ tầng, bảo mật, quan sát và kinh nghiệm đội ngũ. Đo mẫu với cùng công việc nghiệp vụ khi cần so sánh hiệu năng.

Cần nhìn toàn bộ đường đi. Thay REST bằng gRPC không sửa được truy vấn cơ sở dữ liệu thiếu chỉ mục; thay nhiều endpoint bằng một query GraphQL cũng không bảo đảm số lần gọi backend giảm.

### Bước 6: Ghi lại lý do chọn và điều kiện xem xét lại

Một quyết định ngắn nên có:

- Yêu cầu và giả định chính.
- Các phương án đã so sánh.
- Lựa chọn, lợi ích và chi phí chấp nhận.
- Dữ liệu cần đo hoặc ngưỡng khiến đội ngũ đánh giá lại.

Ví dụ: chọn REST cho API đối tác vì tài nguyên rõ, nhiều công nghệ client và hạ tầng HTTP sẵn có; gửi email qua hàng đợi vì được phép hoàn tất sau. Chỉ đánh giá gRPC cho một luồng nội bộ khi phép đo cho thấy chi phí trao đổi đóng góp đáng kể vào độ trễ.

## 7. Ví dụ xuyên suốt: hệ thống đặt hàng kết hợp nhiều cách tích hợp

### 7.1. Tách đường tương tác theo trách nhiệm

```text
Web/Mobile/Đối tác
        |
        | HTTP API hướng tài nguyên
        v
Dịch vụ đơn hàng ---> Cơ sở dữ liệu đơn hàng + bản ghi outbox
        |                               |
        | Đọc đơn/trạng thái            | Tiến trình chuyển tiếp
        |                               v
        |                         Broker sự kiện
        |                            |       |
        |                            v       v
        |                       Gửi email  Cập nhật dữ liệu đọc
        |
        +--> REST để truy vấn trạng thái hiện tại
        +--> SSE để đẩy thay đổi tới màn hình, nếu cần

Đối tác bên ngoài <--- Webhook có xác minh và retry
```

Sơ đồ biểu đạt trách nhiệm và dòng dữ liệu, không yêu cầu mọi hệ thống phải có đủ thành phần. Outbox giúp phối hợp việc lưu dữ liệu và ghi nhận ý định phát sự kiện trong cùng giao dịch cục bộ; tiến trình chuyển tiếp và consumer vẫn cần xử lý lỗi và trùng lặp.

REST cung cấp bề mặt ổn định cho client. Sự kiện giúp các tác vụ phía sau phản ứng độc lập. SSE phục vụ trải nghiệm cập nhật. Webhook phục vụ đối tác. Không có một giao thức nào phải gánh tất cả nhu cầu.

### 7.2. Tạo đơn và phân biệt kết quả với phản ứng phía sau

Ví dụ request minh họa một **hợp đồng idempotency do API quy định**:

```http
POST /orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json
Idempotency-Key: create-order-7f29

{
  "items": [
    {"productId": "prd-15", "quantity": 2}
  ],
  "shippingAddressId": "addr-81"
}
```

```http
HTTP/1.1 201 Created
Location: /orders/ord-1042
Content-Type: application/json

{
  "id": "ord-1042",
  "status": "PENDING_PAYMENT",
  "links": {
    "self": "/orders/ord-1042"
  }
}
```

Ở đây, `201` xác nhận đơn hàng đã được tạo theo hợp đồng. Trạng thái cho biết thanh toán còn đang chờ. Email hoặc bản sao dữ liệu tìm kiếm không nhất thiết đã cập nhật xong.

`Idempotency-Key` không tự hoạt động chỉ vì được gửi trong header. API phải quy định và triển khai phạm vi khóa, thời hạn lưu, liên hệ giữa khóa với chủ thể gọi và payload, cách xử lý hai request đồng thời, cùng kết quả trả lại khi retry. Những tác dụng phụ ở các dịch vụ phía sau cũng cần cơ chế tránh lặp phù hợp.

Với giao diện HTTP, `GET` phải giữ ngữ nghĩa an toàn; `PUT` và `DELETE` có ngữ nghĩa idempotent nhưng các lần gọi có thể trả mã trạng thái khác nhau. `POST` không mặc nhiên idempotent. Dù phương thức là gì, retry tự động còn phụ thuộc vào hợp đồng và loại lỗi thực tế.

### 7.3. Dùng REST cho công việc chạy nền

Xuất một báo cáo lớn có thể vượt quá thời gian hợp lý của một request. API có thể nhận yêu cầu và trả tài nguyên theo dõi:

```http
POST /order-exports HTTP/1.1
Content-Type: application/json

{"fromDate":"2026-11-01","toDate":"2026-11-16"}
```

```http
HTTP/1.1 202 Accepted
Location: /order-exports/exp-73
Content-Type: application/json

{
  "id": "exp-73",
  "status": "QUEUED",
  "statusUrl": "/order-exports/exp-73"
}
```

`202 Accepted` cho biết yêu cầu đã được chấp nhận để xử lý, chưa khẳng định công việc hoàn tất thành công. Hợp đồng cần chỉ rõ cách theo dõi và nhận kết quả; ví dụ này dùng `Location` và `statusUrl` theo quy ước của API.

Sau đó:

```http
GET /order-exports/exp-73 HTTP/1.1
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "exp-73",
  "status": "SUCCEEDED",
  "result": {
    "downloadUrl": "/order-exports/exp-73/file"
  }
}
```

Nếu xuất thất bại, việc đọc tài nguyên công việc vẫn có thể trả `200 OK` cùng `status: FAILED` và dữ liệu lỗi phù hợp, bởi request đọc đã thành công. Hợp đồng phải phân biệt lỗi của lần gọi HTTP với kết quả của công việc chạy nền.

Tài nguyên công việc cần quy định quyền đọc, trạng thái kết thúc, thời gian lưu, thời hạn tải kết quả và cách báo tiến độ. Worker phía sau có thể dùng hàng đợi, nhưng phía client không cần biết chi tiết đó để sử dụng API.

## 8. Những yêu cầu không biến mất khi đổi cách tích hợp

### 8.1. Xác thực và phân quyền

Xác thực trả lời “ai đang gọi?”, còn phân quyền trả lời “người đó có được thực hiện thao tác này với dữ liệu này không?”. Một người có token hợp lệ chưa chắc được đọc mọi `orderId`.

REST cần kiểm tra quyền theo tài nguyên và thao tác. GraphQL có thể cần quyền theo field và đối tượng. RPC cần quyền theo phương thức và dữ liệu đầu vào. Sự kiện và thông điệp cần kiểm soát quyền phát/nhận, phạm vi dữ liệu và danh tính kết nối. Giao thức được chọn không thay thế thiết kế bảo mật.

### 8.2. Hợp đồng lỗi và retry

Client cần biết lỗi nào có thể sửa bằng cách thay request, lỗi nào cần xác thực lại và lỗi nào có thể retry theo chính sách. Với HTTP, lựa chọn mã trạng thái phải đi cùng nội dung lỗi ổn định; với RPC hoặc sự kiện, cần quy ước tương đương theo cơ chế đang dùng.

Không ánh xạ mọi lỗi thành `200`, cũng không retry mọi lỗi server một cách vô hạn. Retry có giới hạn, backoff và phân tán thời điểm thử lại giúp kiểm soát tải, nhưng thao tác có tác dụng phụ vẫn phải có bảo vệ idempotency và cách đối soát khi kết quả không rõ.

### 8.3. Quan sát và kiểm thử

Dù chọn cách nào, hệ thống vẫn cần liên kết các bước của cùng một nghiệp vụ, đo độ trễ, đếm lỗi và phát hiện dữ liệu chưa được xử lý.

Với Java/Spring hoặc nền tảng tương đương, việc kiểm thử nên bám vào hợp đồng: trạng thái HTTP, header, schema, phân trang, quyền truy cập và hành vi khi retry. Nếu có sự kiện hoặc webhook, cần kiểm chứng xử lý trùng, xử lý chậm và khả năng khôi phục sau lỗi. Không chỉ kiểm tra hàm xử lý trả đúng dữ liệu trong trường hợp thuận lợi.

## 9. Những lập luận dễ dẫn đến quyết định sai

| Lập luận | Vấn đề | Cách đánh giá tốt hơn |
|---|---|---|
| “Có JSON qua HTTP là REST.” | Bỏ qua mô hình tài nguyên và các ràng buộc kiến trúc | Nêu rõ đặc tính API áp dụng và hợp đồng tương tác |
| “Dùng REST thì mọi việc phải CRUD.” | Làm méo các quy trình nghiệp vụ | Đánh giá tài nguyên yêu cầu, tài nguyên kết quả hoặc giao diện thao tác phù hợp |
| “Thêm broker là hết phụ thuộc.” | Bỏ qua phụ thuộc schema, ngữ nghĩa và dữ liệu | Thiết kế tương thích, retry, thứ tự, quan sát và quyền sở hữu sự kiện |
| “GraphQL giải quyết hiệu năng vì chỉ có một request.” | Không phản ánh số truy cập và chi phí phía sau | Đo toàn bộ đường xử lý và giới hạn truy vấn |
| “gRPC luôn nhanh hơn.” | Bỏ qua workload và hạ tầng cụ thể | Đo cùng payload, nghiệp vụ và điều kiện tải |
| “WebSocket thay thế mọi API.” | Tăng nghĩa vụ quản lý kết nối và giao thức ứng dụng | Dùng khi thực sự cần luồng hai chiều; giữ các tài nguyên thích hợp |
| “Stateless nghĩa là không lưu trạng thái đơn hàng.” | Nhầm trạng thái phiên với trạng thái tài nguyên | Lưu nghiệp vụ bền vững và để request có đủ ngữ cảnh xử lý |
| “Client timeout thì tạo lại chắc chắn an toàn.” | Có thể tạo tác dụng phụ lặp | Dùng idempotency, truy vấn kết quả và đối soát |
| “REST an toàn hơn các cách khác.” | Đồng nhất giao thức với kiểm soát bảo mật | Đánh giá xác thực, phân quyền, mã hóa và bề mặt tấn công thực tế |

## 10. Bài tập tự đánh giá

Với mỗi tình huống, hãy chọn phương án ban đầu và nêu một điều kiện có thể làm bạn thay đổi quyết định.

### Tình huống A: API danh mục cho đối tác

Đối tác dùng nhiều ngôn ngữ, chủ yếu đọc sản phẩm và thỉnh thoảng cập nhật thông tin được cấp quyền. Dữ liệu công khai có thể chậm vài phút; một số giá lại phụ thuộc từng đối tác.

**Gợi ý phân tích:** REST là ứng viên tốt nhờ tài nguyên rõ và khả năng tương tác rộng. Tách chính sách cache cho dữ liệu công khai và giá riêng; thiết kế phân trang, quyền cập nhật và hợp đồng lỗi. Không cache dùng chung dữ liệu riêng chỉ vì cùng là sản phẩm.

### Tình huống B: Sau khi đơn được xác nhận, năm hệ thống cùng xử lý

Gửi email, cộng điểm và cập nhật báo cáo được phép chậm; việc xác nhận đơn cần phản hồi nhanh.

**Gợi ý phân tích:** Dùng REST cho thao tác liên quan trực tiếp đến client và sự kiện cho các phản ứng phía sau. Xác định rõ thời điểm đơn đã được xác nhận, độ trễ được phép, cách phát sự kiện đáng tin cậy và cách consumer xử lý trùng. Nếu một công đoạn bắt buộc phải thành công trước khi xác nhận, phải đưa điều kiện đó vào ranh giới nghiệp vụ.

### Tình huống C: Màn hình điều hành nhận trạng thái máy liên tục

Server đẩy trạng thái; người dùng chỉ thỉnh thoảng gửi một lệnh cấu hình.

**Gợi ý phân tích:** Có thể dùng SSE cho cập nhật và HTTP API cho cấu hình. Nếu cần luồng tương tác liên tục theo cả hai chiều, đánh giá WebSocket. Trong cả hai trường hợp cần cách lấy trạng thái đầy đủ sau khi kết nối lại.

### Tình huống D: Nhiều giao diện cần tổng hợp dữ liệu khác nhau

Một trang web, một ứng dụng di động và một màn hình nội bộ dùng các tập field khác nhau từ nhiều miền dữ liệu.

**Gợi ý phân tích:** So sánh GraphQL với các endpoint tổng hợp hoặc backend riêng theo nhu cầu giao diện. Dựa vào số lượt gọi, khả năng tái sử dụng, quy tắc quyền và chi phí vận hành. Chỉ đếm số request từ client là chưa đủ để chọn.

### Tình huống E: Dịch vụ nội bộ liên tục gửi nhiều kết quả trung gian

Hai bên được cùng tổ chức quản lý, cần hợp đồng kiểu dữ liệu chặt và gửi kết quả dần trong một tác vụ.

**Gợi ý phân tích:** gRPC streaming là ứng viên đáng đánh giá. Kiểm tra hỗ trợ của thư viện và hạ tầng, giới hạn luồng, khả năng hủy, timeout, tương thích schema và khôi phục khi kết nối đứt. Đối chiếu với cách chia công việc thành tài nguyên nếu cần lưu và truy vấn kết quả lâu dài.

## 11. Checklist trước khi chốt phương án

- [ ] Đã xác định tài nguyên hoặc thao tác nghiệp vụ và ranh giới hoàn tất.
- [ ] Đã tách kết quả cần ngay khỏi công việc được phép xử lý sau.
- [ ] Đã xác định loại client, hướng trao đổi và số bên nhận.
- [ ] Đã so sánh ít nhất một lựa chọn phù hợp khác khi REST có dấu hiệu bất lợi.
- [ ] Đã mô tả quyền truy cập, hợp đồng dữ liệu và cách thay đổi hợp đồng.
- [ ] Đã quy định timeout, retry, xử lý trùng và cách xác định kết quả khi mất phản hồi.
- [ ] Đã tính đến cache, phân trang hoặc dữ liệu khối lượng lớn khi có liên quan.
- [ ] Đã tính chi phí vận hành, quan sát và kiểm thử cho cả đường lỗi.
- [ ] Đã ghi rõ giả định và bằng chứng cần thu thập nếu hiệu năng quyết định lựa chọn.

REST thường là lựa chọn vững cho một giao diện HTTP hướng tài nguyên, có hợp đồng rõ và cần phục vụ nhiều loại client. Khi yêu cầu chuyển sang thao tác nội bộ, truy vấn linh hoạt, công việc dài, phân phối sự kiện, cập nhật liên tục hoặc dữ liệu theo lô, hãy chọn và kết hợp cơ chế tương ứng dựa trên ngữ nghĩa, độ trễ, bảo đảm xử lý và chi phí vận hành của bài toán.
