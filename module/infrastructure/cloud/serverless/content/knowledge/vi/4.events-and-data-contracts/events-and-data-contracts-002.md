# CloudEvents và chuẩn hóa envelope sự kiện

Trong chương **Sự kiện và hợp đồng dữ liệu**, CloudEvents cung cấp một cách biểu diễn thống nhất cho sự kiện trước khi sự kiện đi qua HTTP, hàng đợi hoặc event bus. Khi mỗi service tự đặt cấu trúc message, consumer phải biết nhiều định dạng khác nhau, khó kiểm tra nguồn phát, định danh và thời điểm của sự kiện. Một envelope thống nhất giúp các thành phần trao đổi cùng một ngôn ngữ về ngữ cảnh sự kiện, trong khi payload vẫn mô tả dữ liệu nghiệp vụ của từng loại sự kiện.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function được kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Với FaaS, một function có thể phát sự kiện và nhiều function khác có thể nhận sự kiện đó ở những thời điểm khác nhau. Vì vậy, hợp đồng sự kiện cần làm rõ định danh, nguồn phát, loại sự kiện, schema dữ liệu, khả năng xử lý lặp, phiên bản và cách theo dõi luồng xử lý. Đây là nền tảng để thiết kế retry, idempotency, quyền truy cập và mở rộng có kiểm soát.

## 1. Sự kiện, payload và envelope là ba khái niệm khác nhau

**Sự kiện (event)** là một bản ghi cho biết một việc đã xảy ra trong hệ thống hoặc miền nghiệp vụ. Ví dụ: đơn hàng đã được tạo, hàng đã được giữ, thanh toán đã thành công hoặc một tệp đã được tải lên.

Một sự kiện thường có ba phần:

| Phần | Vai trò | Ví dụ |
|---|---|---|
| Ngữ nghĩa sự kiện | Cho biết việc gì đã xảy ra | OrderPlaced |
| Envelope / context | Cho biết định danh, nguồn, loại và thời điểm của sự kiện | ID, source, type, time |
| Payload / data | Chứa dữ liệu nghiệp vụ mà consumer cần | Mã đơn, khách hàng, các dòng hàng |

**Payload** là nội dung riêng của nghiệp vụ. Ví dụ, payload của OrderPlaced có thể chứa orderId, customerId, các dòng hàng và tổng tiền. Payload không nên phải tự lặp lại mọi thông tin định tuyến hoặc định danh đã có trong envelope.

**Envelope** bao quanh payload, cung cấp ngữ cảnh chung cho mọi loại sự kiện. Một consumer dùng envelope để xác định nguồn, loại, định danh và phiên bản schema trước khi chuyển payload cho logic nghiệp vụ.

Nếu mỗi service tự tạo envelope, một message có thể dùng eventId, messageKey, eventName; service khác lại dùng id, topic, action. Một số message đặt thời gian ở createdAt, số khác đặt ở timestamp. Những khác biệt nhỏ này khiến function phải chứa nhiều nhánh chuyển đổi và làm tăng khả năng hiểu sai hợp đồng.

CloudEvents chuẩn hóa phần ngữ cảnh của sự kiện. Nó không yêu cầu mọi payload có cùng cấu trúc và cũng không thay thế mô hình nghiệp vụ của từng service.

## 2. CloudEvents giải quyết vấn đề gì?

**CloudEvents** là một đặc tả mở của Cloud Native Computing Foundation (CNCF), định nghĩa cách mô tả sự kiện bằng một tập thuộc tính ngữ cảnh chung và các cách ánh xạ sự kiện qua những giao thức khác nhau.

CloudEvents hữu ích khi:

- Nhiều service hoặc function phát và nhận sự kiện qua các nền tảng khác nhau.
- Một event bus có nhiều consumer được phát triển độc lập.
- Hệ thống cần định tuyến theo nguồn hoặc loại sự kiện.
- Consumer cần phát hiện sự kiện trùng và ghi nhận dấu vết xử lý.
- Nhóm phát triển muốn tách logic nghiệp vụ khỏi định dạng riêng của từng message broker.

Một envelope CloudEvents có thể được truyền ở dạng JSON có cấu trúc, hoặc được ánh xạ vào header và body của HTTP. Các binding khác có thể ánh xạ cùng ngữ cảnh vào giao thức message tương ứng. Nhờ đó, producer và consumer có thể dùng cùng một mô hình sự kiện ngay cả khi đường truyền khác nhau.

CloudEvents chuẩn hóa cách mô tả sự kiện, không tự bảo đảm:

- Message được giao đúng một lần.
- Các sự kiện đến đúng thứ tự.
- Message không bị mất.
- Consumer đã xử lý thành công.
- Payload đúng schema nghiệp vụ.
- Nguồn phát đã được xác thực hoặc có quyền phát sự kiện.

Các bảo đảm trên phụ thuộc vào message broker, giao thức, cơ chế lưu trữ, quyền truy cập và cách triển khai producer/consumer. CloudEvents cung cấp hợp đồng ngữ cảnh để những thành phần đó phối hợp rõ ràng hơn.

## 3. Cấu trúc của một CloudEvent

CloudEvents phiên bản 1.0 định nghĩa bốn thuộc tính ngữ cảnh bắt buộc: **specversion**, **id**, **source** và **type**. Những thuộc tính khác có thể được dùng khi phù hợp với sự kiện.

| Thuộc tính | Bắt buộc | Ý nghĩa | Ví dụ |
|---|---|---|---|
| specversion | Có | Phiên bản đặc tả CloudEvents dùng để biểu diễn envelope | 1.0 |
| id | Có | Định danh sự kiện trong phạm vi nguồn phát | evt-8f31 |
| source | Có | URI hoặc URI-reference nhận diện nguồn tạo sự kiện | urn:example:orders |
| type | Có | Loại sự kiện, mô tả sự việc đã xảy ra | com.example.orders.order-placed |
| subject | Không | Đối tượng cụ thể liên quan đến sự kiện trong phạm vi source | orders/ORD-1001 |
| time | Không | Thời điểm xảy ra sự kiện | 2026-11-17T10:15:30Z |
| datacontenttype | Không | Media type của data | application/json |
| dataschema | Không | URI xác định schema mà data tuân theo | https://schemas.example.com/order-placed/v1 |
| data | Không | Payload sự kiện | Đối tượng JSON chứa dữ liệu đơn hàng |
| data_base64 | Không | Dữ liệu nhị phân được mã hóa Base64 trong JSON event format | Chuỗi Base64 |

### 3.1. Bốn thuộc tính bắt buộc

**specversion** xác định phiên bản đặc tả CloudEvents được sử dụng. Với CloudEvents 1.0, giá trị là chuỗi 1.0. Đây là phiên bản của envelope CloudEvents, không phải phiên bản schema nghiệp vụ của payload.

**id** nhận diện một lần phát sinh sự kiện. Cặp **source + id** phải xác định duy nhất một sự kiện. Hai service có thể cùng tạo ra giá trị id giống nhau mà không xung đột nếu source khác nhau. Consumer thường dùng cặp này làm khóa chống xử lý trùng.

Khi retry hoặc replay cùng một sự kiện, producer nên giữ nguyên source và id của sự kiện gốc. Nếu một nghiệp vụ mới thực sự xảy ra, cần tạo id mới. Nếu một service chuyển đổi sự kiện thành một sự kiện nghiệp vụ mới, sự kiện mới có id riêng và có thể liên kết với sự kiện nguồn bằng thuộc tính mở rộng như causationid.

**source** xác định ngữ cảnh trong đó sự kiện xảy ra, thường là service hoặc resource nghiệp vụ sở hữu sự kiện. Giá trị này là URI hoặc URI-reference, có thể là URI theo tên miền, đường dẫn hoặc URN ổn định. Ví dụ: urn:example:orders hoặc /services/order-service. Source không nhất thiết là địa chỉ của function cụ thể đang gửi message; nếu nhiều instance của cùng service phát event, source vẫn nên ổn định và không thay đổi theo instance, địa chỉ IP tạm thời hoặc tên máy triển khai.

**type** mô tả loại sự kiện. Giá trị nên phản ánh sự thật nghiệp vụ đã xảy ra, chẳng hạn com.example.orders.order-placed hoặc com.example.payments.payment-succeeded. Type giúp consumer định tuyến đến handler phù hợp mà không cần phân tích payload để đoán ý nghĩa.

### 3.2. Những thuộc tính tùy chọn quan trọng

**subject** mô tả đối tượng cụ thể liên quan đến sự kiện trong phạm vi source. Ví dụ, subject có thể là orders/ORD-1001. Nó hữu ích khi cần lọc hoặc tìm các sự kiện liên quan đến một thực thể.

**time** biểu diễn thời điểm xảy ra sự kiện bằng timestamp RFC 3339, thường được biểu diễn theo UTC. Nếu producer xác định được thời điểm nghiệp vụ xảy ra, hãy dùng thời điểm đó; nếu không thể xác định, có thể dùng thời điểm event được tạo. Đây không phải thời điểm consumer nhận message. Nếu cần thời điểm nhận hoặc xử lý, consumer ghi riêng trong log hoặc dữ liệu vận hành.

**datacontenttype** cho biết media type của payload, ví dụ application/json. Thuộc tính này mô tả cách diễn giải data, không mô tả toàn bộ envelope.

**dataschema** là URI nhận diện schema của payload. Consumer có thể dùng nó để chọn schema validator hoặc kiểu dữ liệu phù hợp. URI nên ổn định và trỏ đến phiên bản schema có thể tra cứu được theo chính sách của tổ chức.

**data** chứa payload. Trong JSON event format, data có thể là đối tượng, mảng, chuỗi, số, boolean hoặc giá trị JSON khác tùy hợp đồng. Nếu payload là dữ liệu nhị phân, CloudEvents JSON event format có thuộc tính data_base64. Không sử dụng đồng thời data và data_base64 trong cùng một event.

### 3.3. Extension attributes

Ngoài các thuộc tính chuẩn, CloudEvents cho phép thêm **extension attributes** để mang ngữ cảnh cần thiết cho một hệ thống hoặc miền nghiệp vụ. Ví dụ:

- correlationid: liên kết nhiều hoạt động trong cùng một quy trình.
- causationid: chỉ ra sự kiện hoặc thông điệp đã gây ra sự kiện hiện tại.
- tenantid: nhận diện tenant trong hệ thống nhiều khách hàng.
- traceparent: truyền ngữ cảnh trace theo quy ước tracing đang dùng.

Extension giúp bổ sung ngữ cảnh mà không nhồi mọi thông tin vào payload. Tuy nhiên, nhóm phát triển cần quản lý tên, kiểu dữ liệu, ý nghĩa và phạm vi sử dụng. Tên extension theo quy tắc CloudEvents dùng chữ cái ASCII viết thường và chữ số, bắt đầu bằng chữ cái viết thường; tên cũng cần ổn định và không trùng với thuộc tính chuẩn. Không tạo extension riêng cho mọi trường hợp nhỏ nếu không có nhu cầu liên hệ giữa các thành phần.

Không nên đưa mật khẩu, access token, khóa bí mật hoặc dữ liệu cá nhân không cần thiết vào extension. Envelope có thể được ghi log, chuyển qua nhiều hệ thống và lưu trong dead-letter queue; mọi thuộc tính đều có thể trở thành dữ liệu bị lộ nếu không kiểm soát.

## 4. Ví dụ một CloudEvent hoàn chỉnh

Giả sử Order Service tạo sự kiện khi một đơn hàng được ghi nhận. Một CloudEvent ở dạng JSON có cấu trúc có thể như sau:

~~~json
{
  "specversion": "1.0",
  "id": "evt-8f31",
  "source": "urn:example:orders",
  "type": "com.example.orders.order-placed",
  "subject": "orders/ORD-1001",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.example.com/orders/order-placed/v1",
  "correlationid": "checkout-7b20",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-2001",
    "currency": "VND",
    "totalAmount": 1250000,
    "lines": [
      {
        "productId": "SKU-01",
        "quantity": 2,
        "unitPrice": 500000
      },
      {
        "productId": "SKU-02",
        "quantity": 1,
        "unitPrice": 250000
      }
    ]
  }
}
~~~

Có thể đọc event này theo thứ tự:

1. Envelope tuân theo CloudEvents 1.0.
2. Sự kiện có id evt-8f31 do source urn:example:orders tạo.
3. Type cho biết đây là sự kiện đơn hàng đã được tạo.
4. Subject chỉ ra đơn hàng cụ thể.
5. Time là thời điểm nghiệp vụ xảy ra.
6. Dataschema xác định hợp đồng payload.
7. Correlationid liên kết sự kiện với quy trình checkout.
8. Data chứa thông tin nghiệp vụ mà Inventory, Payment hoặc Notification có thể cần.

Consumer có thể kiểm tra type trước khi chuyển data sang lớp xử lý đơn hàng. Nó không cần biết producer sử dụng framework Java nào hoặc lưu đơn bằng cơ sở dữ liệu nào.

Lưu ý rằng giá trị dataschema trong ví dụ là URI minh họa. Trong hệ thống thực tế, URI phải được quản lý và truy xuất theo chính sách schema của tổ chức; không nên công bố một URI giả định như thể schema đã tồn tại.

## 5. Hai cách truyền CloudEvents qua HTTP

CloudEvents định nghĩa hai cách ánh xạ phổ biến qua HTTP: **structured mode** và **binary mode**. Cả hai đều truyền cùng một ngữ cảnh sự kiện, nhưng cách đặt envelope và payload khác nhau.

### 5.1. Structured mode

Ở structured mode, toàn bộ CloudEvent được đặt trong body. Header Content-Type cho biết định dạng envelope, thường là application/cloudevents+json khi dùng JSON event format.

Ví dụ:

~~~http
POST /events HTTP/1.1
Host: functions.example.com
Content-Type: application/cloudevents+json

{
  "specversion": "1.0",
  "id": "evt-8f31",
  "source": "urn:example:orders",
  "type": "com.example.orders.order-placed",
  "data": {
    "orderId": "ORD-1001"
  }
}
~~~

Ưu điểm:

- Có thể lưu, phát lại hoặc chuyển tiếp toàn bộ envelope như một tài liệu.
- Dễ quan sát khi kiểm tra message trong log hoặc công cụ quản trị.
- Các thuộc tính chuẩn và extension nằm cùng một cấu trúc JSON.
- Phù hợp khi producer và consumer muốn trao đổi một CloudEvent hoàn chỉnh.

Nhược điểm là consumer cần đọc và phân tích body để lấy cả context lẫn data. Nếu hệ thống trung gian chỉ định tuyến dựa trên HTTP header, nó có thể phải parse body hoặc cần một bước adapter.

### 5.2. Binary mode

Ở binary mode, context attributes được ánh xạ vào HTTP header, còn payload nằm trong body. Các thuộc tính context thường được đặt trong header với tiền tố ce-. Header Content-Type biểu diễn media type của payload.

Ví dụ:

~~~http
POST /events HTTP/1.1
Host: functions.example.com
ce-specversion: 1.0
ce-id: evt-8f31
ce-source: urn:example:orders
ce-type: com.example.orders.order-placed
ce-subject: orders/ORD-1001
ce-time: 2026-11-17T10:15:30Z
ce-correlationid: checkout-7b20
Content-Type: application/json

{
  "orderId": "ORD-1001",
  "customerId": "CUS-2001"
}
~~~

Ưu điểm:

- Gateway hoặc middleware có thể định tuyến theo header mà không cần phân tích payload.
- Body giữ nguyên định dạng dữ liệu gốc.
- Phù hợp với hệ thống HTTP đã có hợp đồng body và cần bổ sung context sự kiện.

Nhược điểm là việc lưu hoặc chuyển tiếp event cần bảo toàn cả header và body. Nếu chỉ lưu body, thông tin định danh và nguồn phát có thể bị mất. Khi chuyển qua proxy hoặc gateway, cần xác minh các header ce- được giữ nguyên.

### 5.3. So sánh hai chế độ

| Tiêu chí | Structured mode | Binary mode |
|---|---|---|
| Vị trí context | Trong JSON envelope ở body | Trong HTTP header |
| Vị trí data | Trường data trong envelope | Body HTTP |
| Content-Type | application/cloudevents+json với JSON format | Media type của payload |
| Định tuyến theo header | Cần adapter hoặc đọc body | Có thể dựa trực tiếp trên ce-type, ce-source |
| Lưu trữ nguyên event | Lưu toàn bộ body envelope | Lưu cả context header và body |
| Trường hợp phù hợp | Chuyển tiếp event như một tài liệu hoàn chỉnh | Tích hợp HTTP cần giữ payload gốc hoặc định tuyến bằng header |

Không nên trộn hai chế độ trong cùng một message. Adapter ở ranh giới HTTP nên xác định rõ chế độ đang nhận, đọc context tương ứng và chuyển về mô hình nội bộ thống nhất.

## 6. Chuẩn hóa quy ước envelope trong một hệ thống

CloudEvents cung cấp bộ thuộc tính chuẩn, nhưng tổ chức vẫn cần quy ước để các producer và consumer sử dụng nhất quán.

### 6.1. Quy ước source

Source phải chỉ ra nguồn nghiệp vụ hoặc thành phần chịu trách nhiệm phát sự kiện. Ví dụ:

- urn:example:orders
- urn:example:inventory
- urn:example:payments

Một source nên có vòng đời ổn định. Không dùng tên pod, container ID hoặc địa chỉ IP ngẫu nhiên làm source nếu các giá trị đó thay đổi theo mỗi lần triển khai. Nếu cần nhận diện instance, hãy dùng thuộc tính vận hành riêng và cân nhắc có thực sự cần đưa nó vào event.

### 6.2. Quy ước type

Type nên là định danh ổn định, dễ đọc và mô tả sự kiện nghiệp vụ đã xảy ra. Ví dụ:

- com.example.orders.order-placed
- com.example.orders.order-cancelled
- com.example.inventory.stock-reserved
- com.example.payments.payment-succeeded

Nên thống nhất cách viết, tên miền hoặc namespace, số ít/số nhiều và cách biểu diễn phiên bản. Type không nên mô tả tên class Java hoặc tên method nội bộ vì các chi tiết đó có thể thay đổi khi refactor.

Event thể hiện sự thật đã xảy ra, thường dùng cách diễn đạt quá khứ như OrderPlaced. Nếu message yêu cầu một hành động như ReserveStock, đó thường là command. Phân biệt hai loại giúp consumer hiểu message là thông báo hay yêu cầu thực thi.

### 6.3. Quy ước id và time

Id cần được tạo ổn định cho mỗi lần phát sinh sự kiện. Có thể dùng UUID hoặc một định danh duy nhất phù hợp với hệ thống. Không dùng orderId làm id của mọi event về một đơn hàng, vì một đơn có thể phát sinh nhiều sự kiện khác nhau trong vòng đời.

Time phải nhất quán về múi giờ và ý nghĩa. Nên dùng UTC để tránh nhầm lẫn khi function chạy ở nhiều vùng. Không thay time của sự kiện gốc bằng thời điểm consumer nhận message khi retry hoặc replay.

### 6.4. Quy ước payload

Payload cần có schema rõ ràng, tối thiểu xác định:

- Tên trường và kiểu dữ liệu.
- Trường bắt buộc và trường tùy chọn.
- Ý nghĩa của giá trị null và trường bị lược bỏ.
- Đơn vị đo, tiền tệ và quy ước làm tròn.
- Định dạng ngày giờ và múi giờ.
- Cách biểu diễn trạng thái và enum.
- Quy tắc định danh cho các thực thể liên quan.

Ví dụ, trường totalAmount nên đi cùng currency. Không nên chỉ gửi một số 1250000 rồi để consumer tự đoán đó là VND, USD hay đơn vị nhỏ nhất của một loại tiền. Trường quantity cần có quy ước số lượng nguyên hay thập phân. Timestamp cần có định dạng và ý nghĩa thống nhất.

Payload nên chứa dữ liệu đủ để consumer thực hiện trách nhiệm của mình mà không phải gọi ngược producer chỉ để lấy những trường căn bản. Tuy nhiên, không nên sao chép toàn bộ cơ sở dữ liệu hoặc gửi dữ liệu cá nhân không cần thiết. Cân bằng giữa tính tự chủ của consumer, kích thước message và chính sách dữ liệu.

### 6.5. Quy ước extension

Tổ chức nên có danh sách extension được phê duyệt, định nghĩa kiểu, ý nghĩa và cách truyền qua các transport. Ví dụ:

| Extension | Ý nghĩa | Quy tắc |
|---|---|---|
| correlationid | Liên kết nhiều bước của một quy trình | Giữ nguyên qua các bước thuộc cùng một quy trình |
| causationid | Định danh sự kiện hoặc message gây ra sự kiện hiện tại | Tham chiếu id của sự kiện nguồn |
| traceparent | Ngữ cảnh distributed tracing | Tuân theo định dạng tracing đang áp dụng |
| tenantid | Tenant sở hữu ngữ cảnh nghiệp vụ | Kiểm tra quyền và phạm vi tenant ở consumer |

Không dùng extension để thay thế các thuộc tính CloudEvents đã có. Ví dụ, không tạo eventtype nếu type đã thể hiện loại sự kiện. Không đưa toàn bộ dữ liệu nghiệp vụ vào extension; dữ liệu đó thuộc payload.

## 7. Phân biệt phiên bản CloudEvents và phiên bản schema nghiệp vụ

Một nhầm lẫn phổ biến là coi specversion là phiên bản của payload. Hai phiên bản này giải quyết hai vấn đề khác nhau:

| Phiên bản | Ý nghĩa | Ví dụ |
|---|---|---|
| specversion | Phiên bản đặc tả CloudEvents | 1.0 |
| Phiên bản schema | Phiên bản hợp đồng dữ liệu của loại sự kiện | order-placed/v1 |
| type | Định danh loại sự kiện nghiệp vụ | com.example.orders.order-placed |

Khi thay đổi payload, không tự động đổi specversion. specversion chỉ thay đổi khi cách biểu diễn envelope tuân theo phiên bản CloudEvents khác.

Có thể quản lý phiên bản schema qua dataschema, hoặc dùng một quy ước version trong type. Hai cách đều có thể dùng, nhưng tổ chức phải chọn một chính sách nhất quán và mô tả rõ.

Ví dụ, nếu thêm một trường tùy chọn có giá trị mặc định hợp lý, thay đổi có thể tương thích ngược với consumer đã được thiết kế để bỏ qua trường chưa biết. Nếu đổi kiểu dữ liệu, xóa trường bắt buộc hoặc thay đổi ý nghĩa một trường hiện có, đó thường là thay đổi phá vỡ tương thích và cần một phiên bản hợp đồng mới hoặc một loại sự kiện mới.

Không nên sửa nội dung schema tại cùng một URI version đã phát hành. Consumer cũ có thể đã lưu event để replay; nếu schema tại URI đó thay đổi âm thầm, cùng một event có thể được diễn giải khác nhau theo thời gian.

## 8. Thiết kế schema và khả năng tương thích

Schema mô tả cấu trúc payload. Tổ chức có thể dùng JSON Schema, Avro, Protobuf hoặc định dạng khác tùy hệ sinh thái. CloudEvents không bắt buộc một ngôn ngữ schema cụ thể; dataschema có thể nhận diện schema được chọn.

Một hợp đồng payload tốt cần mô tả:

- Kiểu dữ liệu và giới hạn hợp lệ.
- Trường bắt buộc, tùy chọn và giá trị mặc định.
- Enum và cách consumer xử lý giá trị mới.
- Quy tắc tương thích giữa các phiên bản.
- Ví dụ hợp lệ và ví dụ không hợp lệ.
- Chủ sở hữu và quy trình thay đổi schema.

### 8.1. Thay đổi thường tương thích

Một số thay đổi có thể tương thích nếu consumer được thiết kế phù hợp:

- Thêm trường tùy chọn mà consumer cũ bỏ qua được.
- Thêm metadata không làm thay đổi ý nghĩa trường hiện tại.
- Mở rộng tài liệu mô tả mà không thay đổi hành vi.

Tuy nhiên, thêm giá trị mới vào enum có thể làm consumer cũ lỗi nếu code dùng switch hoặc parser chỉ chấp nhận các giá trị đã biết. Vì vậy, không nên mặc định mọi thay đổi thêm đều an toàn.

### 8.2. Thay đổi có nguy cơ phá vỡ tương thích

Các thay đổi sau thường cần kế hoạch phiên bản:

- Xóa hoặc đổi tên trường bắt buộc.
- Đổi kiểu dữ liệu, ví dụ số nguyên thành chuỗi.
- Thay đổi đơn vị hoặc ý nghĩa của trường.
- Chuyển một trường tùy chọn thành bắt buộc.
- Thay đổi ngữ nghĩa event nhưng vẫn giữ nguyên type.
- Thay đổi cấu trúc lồng nhau khiến consumer cũ không đọc được.

Khi có thay đổi phá vỡ tương thích, có thể phát một type mới hoặc schema version mới. Trong giai đoạn chuyển đổi, producer có thể phát song song hai phiên bản hoặc consumer hỗ trợ cả hai trong một khoảng thời gian. Cách làm cụ thể cần dựa trên khả năng replay, số lượng consumer và mức độ quan trọng của sự kiện.

### 8.3. Consumer nên xử lý trường chưa biết

Consumer nên bỏ qua extension hoặc trường payload chưa biết nếu hợp đồng cho phép. Cách này giúp producer bổ sung metadata mà không buộc mọi consumer triển khai đồng thời.

Tuy nhiên, không nên bỏ qua trường chưa biết khi trường đó ảnh hưởng đến quyết định nghiệp vụ hoặc bảo mật. Ví dụ, một consumer xử lý thanh toán phải kiểm tra currency và amount theo hợp đồng, không thể tự bỏ qua trường currency vì phiên bản code cũ chưa biết nó.

## 9. Tạo và phát CloudEvent từ Java function

Trong kiến trúc serverless, Java function có thể tạo event sau khi một ca sử dụng hoàn tất. Function adapter chịu trách nhiệm chuyển dữ liệu nội bộ sang CloudEvents và gửi qua event bus hoặc message broker.

Ví dụ dưới đây minh họa một mô hình envelope nội bộ cho structured JSON event. Nó không phải một thư viện CloudEvents hoàn chỉnh; ứng dụng thực tế nên dùng SDK hoặc adapter tuân theo CloudEvents để xử lý đầy đủ serialization, extension attributes và binding của transport.

~~~java
import java.net.URI;
import java.time.Instant;

public record OrderPlacedData(
        String orderId,
        String customerId,
        String currency,
        long totalAmount) {
}

public record CloudEventEnvelope<T>(
        String specversion,
        String id,
        URI source,
        String type,
        String subject,
        Instant time,
        String datacontenttype,
        URI dataschema,
        T data) {
}
~~~

Một factory có thể tạo envelope cho sự kiện OrderPlaced:

~~~java
import java.net.URI;
import java.time.Instant;
import java.util.UUID;

public final class OrderEventFactory {
    private static final URI SOURCE =
            URI.create("urn:example:orders");

    private static final URI ORDER_PLACED_SCHEMA =
            URI.create(
                "https://schemas.example.com/orders/order-placed/v1");

    public CloudEventEnvelope<OrderPlacedData> orderPlaced(
            OrderPlacedData data) {

        return new CloudEventEnvelope<>(
                "1.0",
                UUID.randomUUID().toString(),
                SOURCE,
                "com.example.orders.order-placed",
                "orders/" + data.orderId(),
                Instant.now(),
                "application/json",
                ORDER_PLACED_SCHEMA,
                data);
    }
}
~~~

Factory trên tạo id mới cho một lần phát sinh sự kiện và dùng source ổn định cho Order Service. Trong ứng dụng thực tế, thời điểm nên được lấy từ thời điểm nghiệp vụ được commit hoặc được ghi nhận theo quy ước rõ ràng. Nếu cần phát event sau transaction, cần bảo đảm event được lưu bền vững cùng thay đổi nghiệp vụ, chẳng hạn bằng transactional outbox.

Với Jackson, cần đăng ký module hỗ trợ Java Time (jackson-datatype-jsr310) để serialize và deserialize Instant theo định dạng timestamp mong muốn. Record Java cũng cần phiên bản Jackson hỗ trợ record; adapter nên cấu hình rõ định dạng ngày giờ thay vì phụ thuộc vào cấu hình mặc định của từng môi trường.

Record Java ở ví dụ là mô hình nội bộ. Khi serialize thành CloudEvents JSON, extension attributes phải được ghi ở cùng cấp với các thuộc tính chuẩn; không tự đặt chúng trong một object extensions nếu không có một format riêng được thống nhất. Tương tự, khi gửi binary mode, adapter phải ánh xạ context vào header và chỉ đặt payload trong body.

## 10. Nhận và kiểm tra CloudEvent trong Java function

Consumer nên xử lý theo các bước:

1. Nhận message từ HTTP, queue hoặc event bus.
2. Chuyển định dạng transport thành mô hình CloudEvent nội bộ.
3. Kiểm tra các thuộc tính bắt buộc và phiên bản envelope được hỗ trợ.
4. Xác định handler dựa trên type.
5. Kiểm tra payload theo dataschema hoặc schema đã cấu hình.
6. Kiểm tra idempotency và thực hiện nghiệp vụ.
7. Chỉ xác nhận message sau khi kết quả đã được lưu bền vững theo cơ chế của transport.

Ví dụ dưới đây đọc structured JSON event bằng Jackson. Mô hình rút gọn chỉ thể hiện các thuộc tính chuẩn và payload JSON; extension attributes chưa được giữ trong record.

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.JsonNode;
import java.net.URI;
import java.time.Instant;

@JsonIgnoreProperties(ignoreUnknown = true)
public record IncomingCloudEvent(
        String specversion,
        String id,
        URI source,
        String type,
        String subject,
        Instant time,
        String datacontenttype,
        URI dataschema,
        JsonNode data) {
}
~~~

Kiểm tra envelope trước khi gọi nghiệp vụ:

~~~java
public final class CloudEventValidator {
    public void validate(IncomingCloudEvent event) {
        if (event == null) {
            throw new IllegalArgumentException("Event is required");
        }

        if (!"1.0".equals(event.specversion())) {
            throw new IllegalArgumentException(
                    "Unsupported CloudEvents specversion");
        }

        if (event.id() == null || event.id().isBlank()) {
            throw new IllegalArgumentException("Event id is required");
        }

        if (event.source() == null) {
            throw new IllegalArgumentException("Event source is required");
        }

        if (event.type() == null || event.type().isBlank()) {
            throw new IllegalArgumentException("Event type is required");
        }

        if (event.data() == null || event.data().isNull()) {
            throw new IllegalArgumentException("Event data is required");
        }
    }
}
~~~

Một handler có thể dispatch theo type rồi chuyển payload sang kiểu nghiệp vụ:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public final class OrderEventHandler {
    private static final String ORDER_PLACED =
            "com.example.orders.order-placed";

    private final ObjectMapper mapper;
    private final CloudEventValidator validator;
    private final OrderPlacedUseCase useCase;

    public OrderEventHandler(
            ObjectMapper mapper,
            CloudEventValidator validator,
            OrderPlacedUseCase useCase) {
        this.mapper = mapper;
        this.validator = validator;
        this.useCase = useCase;
    }

    public void handle(IncomingCloudEvent event) throws Exception {
        validator.validate(event);

        if (!ORDER_PLACED.equals(event.type())) {
            throw new UnsupportedOperationException(
                    "Unsupported event type: " + event.type());
        }

        OrderPlacedData data =
                mapper.treeToValue(event.data(), OrderPlacedData.class);

        String eventKey =
                event.source().toString() + "|" + event.id();

        useCase.processOnce(eventKey, data);
    }
}
~~~

Phương thức processOnce là ranh giới nghiệp vụ chịu trách nhiệm chống xử lý trùng. Không nên chỉ lưu eventKey trong biến toàn cục hoặc bộ nhớ của function vì instance có thể bị thay thế và nhiều instance có thể xử lý cùng message đồng thời.

Ví dụ này cố ý minh họa structured JSON event có data. Một adapter binary HTTP cần đọc các header ce- và Content-Type, sau đó chuẩn hóa chúng thành cùng mô hình nội bộ. Nếu cần giữ extension attributes, adapter phải trích xuất và lưu chúng thay vì bỏ qua như record rút gọn ở trên. Nếu payload là nhị phân, adapter cần xử lý theo data_base64 hoặc binding tương ứng, không ép mọi body thành JSON.

Handler minh họa giả định subscription đã lọc đúng loại event. Trong production, nếu nhận type không được hỗ trợ, consumer cần phân loại đó là lỗi hợp đồng hoặc định tuyến vĩnh viễn để chuyển dead-letter, cảnh báo hoặc bỏ qua theo chính sách subscription; không nên retry vô hạn như thể đây là lỗi mạng tạm thời.

## 11. Idempotency, retry và replay khi dùng CloudEvents

CloudEvents cung cấp id và source để consumer nhận diện một sự kiện, nhưng không tự thực hiện chống trùng. Consumer cần lưu dấu vết xử lý bền vững.

### 11.1. Khóa chống trùng

Một khóa phổ biến là cặp source và id. Có thể tạo bảng lưu các event đã xử lý:

~~~sql
CREATE TABLE processed_events (
    source VARCHAR(500) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source, event_id)
);
~~~

Khi xử lý, consumer ghi khóa vào bảng và cập nhật dữ liệu nghiệp vụ trong cùng transaction nếu cùng một cơ sở dữ liệu hỗ trợ:

~~~sql
BEGIN;

INSERT INTO processed_events (source, event_id, processed_at)
VALUES ('urn:example:orders', 'evt-8f31', CURRENT_TIMESTAMP);

UPDATE inventory
SET reserved_quantity = reserved_quantity + 2
WHERE product_id = 'SKU-01';

COMMIT;
~~~

Đây là ví dụ minh họa; cú pháp xử lý xung đột unique key khác nhau giữa các hệ quản trị cơ sở dữ liệu. Trong triển khai thực tế, nếu insert gặp khóa đã tồn tại thì consumer nhận biết event đã xử lý và kết thúc an toàn. Cần bảo đảm thao tác nghiệp vụ và dấu vết idempotency được commit nguyên tử để tránh trường hợp đánh dấu đã xử lý nhưng nghiệp vụ chưa hoàn tất.

### 11.2. Retry

Retry phù hợp với lỗi tạm thời như timeout, giới hạn tốc độ hoặc dịch vụ phụ thuộc tạm thời không khả dụng. Nên có giới hạn số lần thử, khoảng chờ tăng dần và jitter.

Không nên retry vô hạn với lỗi schema, payload sai hoặc type không được hỗ trợ. Các lỗi này thường cần đưa vào dead-letter queue hoặc luồng xử lý lỗi riêng để điều tra. Khi replay sau khi sửa lỗi, giữ nguyên source và id của sự kiện gốc để consumer có thể nhận diện cùng một sự kiện; nếu muốn chạy lại nghiệp vụ đã xử lý, phải có quy trình replay được kiểm soát và quyết định rõ cách xử lý dấu vết idempotency.

### 11.3. Thứ tự sự kiện

CloudEvents không bảo đảm thứ tự giao nhận. Một consumer có thể nhận OrderCancelled trước OrderPlaced nếu broker, retry hoặc nhiều partition khiến thứ tự thay đổi.

Nếu nghiệp vụ phụ thuộc thứ tự, cần thiết kế ở tầng domain và transport:

- Đưa aggregateId hoặc partition key vào payload hoặc extension theo quy ước.
- Dùng sequence number hoặc aggregate version để phát hiện sự kiện đến thiếu hoặc sai thứ tự.
- Chọn partition key theo thực thể cần giữ thứ tự nếu broker hỗ trợ.
- Consumer kiểm tra phiên bản trước khi áp dụng thay đổi.
- Có chính sách chờ, retry, lưu sự kiện đến sớm hoặc xử lý bù.

Không dùng time để suy ra thứ tự tuyệt đối giữa các service vì đồng hồ có thể lệch và sự kiện có thể được phát trễ. Nếu thứ tự là yêu cầu nghiệp vụ, hãy biểu diễn rõ bằng version hoặc sequence.

### 11.4. Replay

Replay là phát lại một sự kiện đã lưu để khôi phục consumer, xây dựng lại read model hoặc xử lý một luồng mới. Khi replay, cần giữ định danh và nội dung gốc để bảo đảm tính truy vết.

Consumer cần phân biệt replay có chủ đích với event mới. Có thể dùng metadata vận hành riêng để ghi nhận replay run, nhưng không thay đổi id của event gốc nếu mục tiêu là phát lại đúng sự kiện đó. Nếu chuyển đổi payload sang hợp đồng mới và phát ra một event mới, phải tạo id mới và liên kết với event nguồn qua causationid hoặc quan hệ tương đương.

## 12. Transactional outbox và phát CloudEvents đáng tin cậy

Một tình huống thường gặp là Order Service ghi đơn hàng thành công nhưng gửi event thất bại. Nếu service gửi event trước rồi transaction ghi đơn rollback, consumer có thể nhận một OrderPlaced không tồn tại trong cơ sở dữ liệu.

Transactional outbox giúp ghi dữ liệu nghiệp vụ và ý định phát event trong cùng transaction:

~~~sql
BEGIN;

INSERT INTO orders (order_id, status)
VALUES ('ORD-1001', 'PENDING');

INSERT INTO outbox (
    event_id,
    event_source,
    event_type,
    payload,
    created_at
)
VALUES (
    'evt-8f31',
    'urn:example:orders',
    'com.example.orders.order-placed',
    '{"orderId":"ORD-1001"}',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Một publisher riêng đọc outbox, chuyển bản ghi thành CloudEvent và gửi đến broker. Khi gửi thành công, publisher đánh dấu bản ghi đã phát hoặc lưu trạng thái tương ứng. Nếu publisher bị lỗi sau khi broker đã nhận message nhưng trước khi cập nhật trạng thái outbox, message có thể được gửi lại. Consumer vẫn phải idempotent.

Outbox bảo đảm thay đổi dữ liệu và ý định phát sự kiện được lưu cùng nhau. Nó không tạo ra exactly-once delivery xuyên suốt toàn bộ hệ thống. Cần kết hợp id ổn định, retry, consumer idempotent và theo dõi trạng thái publisher.

## 13. Bảo mật và quyền truy cập của event

Một envelope hợp lệ về cú pháp không chứng minh người gửi có quyền phát event. Consumer phải xác thực nguồn thông qua cơ chế của nền tảng, chẳng hạn IAM, quyền publish/subscribe, xác thực kết nối, chữ ký hoặc cơ chế bảo vệ tương ứng.

Các nguyên tắc cần áp dụng:

- Chỉ cấp quyền publish cho service được phép phát loại sự kiện đó.
- Chỉ cấp quyền subscribe cho function cần nhận sự kiện.
- Xác minh tenant và quyền truy cập trước khi thực hiện nghiệp vụ.
- Không tin dữ liệu do producer gửi chỉ vì message đến từ broker nội bộ.
- Không đưa token, mật khẩu hoặc khóa bí mật vào envelope hay payload.
- Hạn chế dữ liệu cá nhân; chỉ phát trường cần thiết cho consumer.
- Kiểm tra kích thước payload và giới hạn tài nguyên trước khi parse.

Extension tenantid có thể giúp định tuyến hoặc lọc sự kiện, nhưng không thay thế kiểm tra quyền. Một consumer không được cho phép truy cập dữ liệu tenant chỉ dựa vào giá trị tenantid trong message nếu nguồn phát hoặc quyền của message chưa được xác thực.

## 14. Quan sát và vận hành luồng sự kiện

Một quy trình serverless có thể đi qua nhiều function và broker. Nếu chỉ ghi log nội dung payload mà không có định danh thống nhất, việc tìm nguyên nhân một đơn bị treo sẽ khó khăn.

Nên ghi nhận tối thiểu:

- CloudEvents source và id.
- Event type và subject khi có.
- Correlation ID và trace context.
- Function hoặc consumer đã xử lý.
- Thời điểm nhận, bắt đầu, hoàn tất và retry.
- Kết quả xử lý, số lần thử và lý do thất bại.

Không ghi toàn bộ payload nếu chứa thông tin nhạy cảm. Log nên có cấu trúc, có thể tìm theo source, id, type và correlationid. Metric nên theo dõi số event nhận, số event xử lý thành công, độ trễ xử lý, retry, dead-letter và độ trễ outbox.

Khi một event đi qua nhiều service, correlationid giúp liên kết các bước trong cùng quy trình; traceparent giúp công cụ tracing nối các span. Hai giá trị có mục đích khác nhau và không nên dùng thay thế cho nhau.

## 15. Quy trình xây dựng một hợp đồng CloudEvents

Có thể áp dụng quy trình sau khi thiết kế event mới:

1. **Xác định sự thật nghiệp vụ:** Viết rõ việc gì đã xảy ra và service nào chịu trách nhiệm phát thông tin đó.
2. **Đặt type:** Chọn định danh sự kiện ổn định, có namespace và tuân theo quy ước tên của tổ chức.
3. **Chọn source:** Xác định nguồn nghiệp vụ ổn định, không phụ thuộc instance triển khai.
4. **Thiết kế payload:** Chọn trường cần thiết cho consumer, kiểu dữ liệu, đơn vị, trường bắt buộc và quy tắc null.
5. **Định nghĩa schema:** Chọn JSON Schema, Avro, Protobuf hoặc định dạng được hệ thống hỗ trợ; công bố URI schema nếu dùng dataschema.
6. **Chọn extension:** Chỉ thêm correlation, causation, tenant hoặc trace context khi có nhu cầu xuyên hệ thống.
7. **Chọn binding:** Quyết định structured hay binary mode cho HTTP, hoặc binding phù hợp với broker.
8. **Định nghĩa tương thích:** Xác định cách thêm trường, thay đổi enum, phát hành phiên bản mới và thời gian hỗ trợ consumer cũ.
9. **Thiết kế vận hành:** Xác định idempotency, retry, dead-letter, replay, thứ tự và transactional outbox.
10. **Kiểm thử hợp đồng:** Kiểm tra producer phát đúng envelope, payload tuân schema và consumer xử lý được phiên bản được hỗ trợ.

Một hợp đồng chỉ hoàn chỉnh khi cả producer và consumer hiểu cùng một ý nghĩa. Việc tài liệu hóa JSON mẫu là hữu ích nhưng chưa đủ; cần có kiểm thử tự động hoặc quy trình xác minh hợp đồng trong pipeline phát triển.

## 16. Những lỗi thường gặp khi chuẩn hóa envelope

**Dùng specversion làm phiên bản payload:** specversion thuộc đặc tả CloudEvents. Phiên bản schema nghiệp vụ cần được quản lý riêng qua dataschema hoặc quy ước type.

**Dùng id của thực thể làm event id:** Một đơn hàng có thể phát sinh nhiều event. Hãy tạo id riêng cho mỗi sự kiện và dùng source + id để nhận diện.

**Đặt source theo instance tạm thời:** Pod hoặc container mới có thể làm source thay đổi liên tục. Chọn định danh nguồn ổn định ở cấp service hoặc miền nghiệp vụ.

**Đặt dữ liệu nghiệp vụ vào extension:** Extension là ngữ cảnh bổ sung, không phải nơi thay thế payload. Dữ liệu cần được kiểm tra theo schema nên nằm trong data.

**Cho rằng CloudEvents bảo đảm exactly-once:** Envelope có id không tự ngăn message được giao lặp. Consumer cần lưu dấu vết idempotency bền vững.

**Chỉ lưu body ở binary mode:** Context nằm trong header. Nếu chỉ lưu body, source, id và type có thể bị mất. Cần lưu toàn bộ envelope sau khi chuẩn hóa.

**Đổi schema mà không đổi phiên bản:** Consumer cũ có thể diễn giải sai dữ liệu. Mọi thay đổi phá vỡ tương thích phải có kế hoạch phiên bản và chuyển đổi.

**Dùng time để bảo đảm thứ tự:** Đồng hồ lệch và giao nhận trễ có thể làm thứ tự quan sát khác thứ tự nghiệp vụ. Dùng sequence hoặc version khi cần thứ tự.

**Không xác thực nguồn phát:** Một message đúng định dạng vẫn có thể đến từ producer không được phép. Bảo vệ quyền publish/subscribe và xác minh danh tính.

**Đưa dữ liệu nhạy cảm vào event:** Event thường được lưu lâu, phát lại và chuyển qua nhiều consumer. Chỉ phát dữ liệu tối thiểu và kiểm soát quyền truy cập.

## 17. Checklist trước khi công bố event contract

- [ ] Event mô tả một sự thật nghiệp vụ đã xảy ra và có service sở hữu rõ ràng.
- [ ] specversion là phiên bản CloudEvents được hỗ trợ.
- [ ] source ổn định và nhận diện được nguồn phát.
- [ ] id duy nhất trong phạm vi source; retry giữ nguyên cặp source + id.
- [ ] type rõ nghĩa, có namespace và không phụ thuộc tên class hoặc method.
- [ ] time có định dạng và ý nghĩa thống nhất.
- [ ] subject được dùng khi cần nhận diện đối tượng cụ thể.
- [ ] datacontenttype và dataschema phù hợp với payload.
- [ ] Payload có schema, đơn vị, trường bắt buộc và quy tắc tương thích.
- [ ] Extension có tên, kiểu và chủ sở hữu rõ ràng.
- [ ] Structured hoặc binary mode được chọn và mô tả rõ.
- [ ] Producer và consumer thống nhất cách xử lý event lặp, retry và dead-letter.
- [ ] Có chính sách thứ tự, replay và phiên bản khi nghiệp vụ cần.
- [ ] Quyền publish/subscribe và xác thực nguồn phát đã được cấu hình.
- [ ] Có correlation, trace, metric và log để theo dõi mà không lộ dữ liệu nhạy cảm.

## Kết luận

CloudEvents chuẩn hóa ngữ cảnh của sự kiện bằng các thuộc tính như specversion, id, source và type, đồng thời cho phép bổ sung subject, time, schema và extension khi cần. Envelope giúp function và service trao đổi sự kiện nhất quán qua HTTP, message hoặc event bus; payload vẫn giữ cấu trúc theo hợp đồng nghiệp vụ riêng.

Để sử dụng hiệu quả, nhóm phát triển cần thống nhất source, type, id, schema, extension và binding; phân biệt phiên bản CloudEvents với phiên bản payload; đồng thời thiết kế idempotency, retry, replay, thứ tự, bảo mật và quan sát. Khi những quy ước này được áp dụng nhất quán, Java function có thể xử lý sự kiện từ nhiều nguồn với adapter rõ ràng, giảm phụ thuộc vào transport và hỗ trợ mở rộng hệ thống serverless có kiểm soát.

