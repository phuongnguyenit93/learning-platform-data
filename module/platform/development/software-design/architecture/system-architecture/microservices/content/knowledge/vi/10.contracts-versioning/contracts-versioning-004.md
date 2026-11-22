# Tương thích ngược, tương thích xuôi và thay đổi phá vỡ hợp đồng

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Hợp đồng và phiên bản

## 1. Vì sao tương thích hợp đồng quyết định khả năng triển khai độc lập?

Trong kiến trúc microservices, các service hiếm khi được cập nhật cùng lúc. Một API có thể được gọi bởi ứng dụng di động chưa nâng cấp, một phiên bản backend cũ, một batch job chạy theo lịch và một đối tác bên ngoài. Một producer có thể phát sự kiện mới trong khi một consumer vẫn chạy code cũ; các event đã được lưu từ nhiều tháng trước còn có thể được replay sau khi hệ thống đã thay đổi.

Nếu thay đổi hợp đồng khiến các phiên bản này không thể giao tiếp đúng, các nhóm phải phát hành đồng bộ hoặc ngừng hệ thống để chuyển đổi. Khi đó một mục tiêu quan trọng của microservices—**triển khai và phát triển tương đối độc lập**—bị suy giảm.

Ví dụ PaymentService chuyển trường `amount` từ số tiền nguyên theo đơn vị nhỏ nhất sang số tiền thập phân theo đơn vị chính, nhưng vẫn giữ tên field và kiểu số JSON. Client cũ vẫn parse được, nhưng có thể thanh toán sai số tiền. Đây là **thay đổi phá vỡ hợp đồng về ngữ nghĩa** mặc dù cấu trúc dữ liệu vẫn hợp lệ.

Bài học này trả lời:

1. Tương thích ngược (backward compatibility) và tương thích xuôi (forward compatibility) là gì?
2. Phải xét hướng giao tiếp thế nào giữa producer/consumer hoặc client/server?
3. Thay đổi nào có thể an toàn về cú pháp nhưng nguy hiểm về hành vi?
4. Làm sao phát triển HTTP API, gRPC/Protobuf và sự kiện bất đồng bộ mà không buộc tất cả service deploy đồng thời?
5. Khi thật sự cần breaking change, nên lên kế hoạch chuyển đổi, giám sát và ngừng hỗ trợ ra sao?

**Nguyên tắc xuyên suốt:** Không đánh giá “tương thích” chỉ theo tên phiên bản. Hãy nói rõ **ai tạo dữ liệu, ai đọc dữ liệu, phiên bản nào đang chạy và ý nghĩa nghiệp vụ nào phải được giữ nguyên**.

## 2. Hợp đồng gồm nhiều lớp, không chỉ là JSON hoặc schema

Một hợp đồng giao tiếp có thể gồm nhiều loại cam kết:

| Lớp hợp đồng | Ví dụ | Hệ quả khi thay đổi |
| --- | --- | --- |
| Cấu trúc dữ liệu | `orderId` là chuỗi, `items` là mảng | Client không giải mã được, dữ liệu bị mất |
| Ngữ nghĩa | `CONFIRMED` nghĩa là đơn đã được chấp nhận theo điều kiện nào | Consumer xử lý sai dù schema vẫn hợp lệ |
| Hành vi API | HTTP 202 nghĩa là mới tiếp nhận, chưa hoàn tất | Client tưởng đã thanh toán |
| Lỗi | 404, 409, 429, gRPC status hoặc error code | Retry sai hoặc ẩn lỗi nghiệp vụ |
| Thời gian | Deadline, thứ tự sự kiện, mức trễ dữ liệu | Tạo trạng thái chưa rõ hoặc hành động sai thời điểm |
| Tính chất xử lý | Idempotency, at-least-once, replay | Tạo hóa đơn hoặc giao dịch trùng |
| Bảo mật | Scope, authorization, quyền xem field | Lộ dữ liệu hoặc từ chối client hợp lệ |
| Phiên bản | Đường dẫn `/v1`, Protobuf package, schema ID | Các phiên bản không còn cùng hiểu nhau |

Hai cấu trúc có thể khớp hoàn toàn nhưng hợp đồng vẫn bị phá khi nghĩa thay đổi. Chẳng hạn cùng trường `totalAmount` kiểu integer nhưng phiên bản mới không còn bao gồm phí vận chuyển. Ngược lại, đổi tên một property ở mô hình nội bộ không nhất thiết làm thay đổi hợp đồng công khai nếu lớp chuyển đổi DTO vẫn giữ nguyên cấu trúc bên ngoài.

**Entity trong database, class của ORM, DTO nội bộ và contract công khai là các khái niệm khác nhau.** Đừng lấy việc serialize trực tiếp entity làm cách định nghĩa API hoặc integration event.

## 3. Tương thích ngược và tương thích xuôi: định nghĩa có chủ thể

Các thuật ngữ backward/forward đôi khi bị diễn đạt từ góc nhìn khác nhau, vì thế có thể gây nhầm lẫn. Cách nhất quán thường dùng với định dạng dữ liệu là:

- **Tương thích ngược (backward compatibility):** phiên bản **mới** vẫn đọc hoặc sử dụng được dữ liệu/hợp đồng do phiên bản **cũ** tạo ra.
- **Tương thích xuôi (forward compatibility):** phiên bản **cũ** vẫn đọc hoặc chấp nhận được dữ liệu/hợp đồng do phiên bản **mới** tạo ra.

Dạng khái quát:

    Backward:
      Old writer  ---- dữ liệu cũ ----> New reader

    Forward:
      New writer  ---- dữ liệu mới ---> Old reader

Đây là cách giải thích từ góc độ **writer/reader của dữ liệu**. Với API request–response, vai trò writer và reader đổi chiều giữa request và response; vì vậy gọi một API là “backward compatible” mà không nói rõ client/server nào được nâng cấp có thể dẫn tới kết luận sai.

### 3.1. Bốn phép thử cụ thể quan trọng hơn thuật ngữ

| Tình huống | Bên tạo dữ liệu | Bên đọc dữ liệu | Câu hỏi |
| --- | --- | --- | --- |
| Client cũ → server mới | Client cũ viết request | Server mới đọc request | API mới còn chấp nhận lời gọi cũ không? |
| Client mới → server cũ | Client mới viết request | Server cũ đọc request | Client mới có yêu cầu field/tính năng mới mà server cũ chưa hiểu không? |
| Server mới → client cũ | Server mới viết response | Client cũ đọc response | Client cũ có xử lý được response bổ sung hoặc thay đổi không? |
| Server cũ → client mới | Server cũ viết response | Client mới đọc response | Client mới có cần field mà server cũ chưa cung cấp không? |

Một endpoint có thể vượt qua phép thử 1 nhưng thất bại ở phép thử 3. Ví dụ server mới chấp nhận mọi request cũ nhưng trả thêm enum value mà client cũ không biết. **Tương thích hai chiều đòi hỏi xem cả request lẫn response**, không chỉ schema đầu vào.

Đối với event:

    Producer mới --> Consumer cũ: phải chịu được event mới
    Producer cũ --> Consumer mới: phải hiểu event cũ
    Event lịch sử --> Consumer mới: phải xử lý được replay

Các cặp này thường xuyên cùng tồn tại trong lúc rollout canary, rolling update, blue/green hoặc khi broker giữ event lâu.

### 3.2. Full compatibility không phải lời hứa vô hạn

Khi một hệ thống hoặc schema registry hỗ trợ chế độ tương thích cả hai chiều, phạm vi thường phải gắn với các **phiên bản được so sánh**. Chính sách kiểm tra bản mới với bản liền trước không đồng nghĩa nó tương thích với mọi version từ khi hệ thống ra đời. Nếu cần đọc lại lịch sử lâu dài, phải xét chính sách transitive hoặc thử nghiệm trên toàn tập schema/record được hỗ trợ.

## 4. Tương thích kỹ thuật và tương thích nghiệp vụ

Có ít nhất năm câu hỏi khác nhau:

1. **Wire compatibility:** byte hoặc JSON có được đọc bởi decoder khác phiên bản không?
2. **Schema compatibility:** dữ liệu mới/cũ có qua các quy tắc kiểu và bắt buộc của schema không?
3. **Source compatibility:** code client khi tái sinh hoặc nâng cấp SDK có còn biên dịch được không?
4. **Behavioral/semantic compatibility:** cùng một hành động có còn tạo kết quả với ý nghĩa đã cam kết không?
5. **Operational compatibility:** các bên có thể cùng hoạt động dưới cơ chế timeout, retry, auth, rate limit và deployment hiện tại không?

Ví dụ Protobuf đổi tên trường nhưng giữ field number có thể giữ tương thích wire đối với binary encoding, trong khi code generated accessor thay đổi làm client cũ không biên dịch khi nâng thư viện. Một API đổi đơn vị tiền nhưng giữ `type: number` có thể giữ schema compatibility mà phá semantic compatibility. Một event có thêm trường optional nhưng consumer strict từ chối thuộc tính lạ có thể phá compatibility khi chạy thật.

**Một thay đổi chỉ được coi là an toàn khi nó bảo vệ những cam kết mà các consumer đang dựa vào**, không phải chỉ vì công cụ lint báo schema hợp lệ.

## 5. Phân loại thay đổi: thêm, sửa, xóa và đổi nghĩa

| Dạng thay đổi | Có thể tương thích khi nào? | Rủi ro chủ yếu |
| --- | --- | --- |
| Thêm field optional vào response | Client cũ bỏ qua unknown fields; client mới có default | Client cũ parse strict hoặc dùng mapping không cho trường lạ |
| Thêm field optional vào request | Server cũ bỏ qua trường lạ hoặc client chỉ gửi tới server hỗ trợ | Server cũ reject request mới |
| Thêm field required vào request | Chỉ nếu mọi client liên quan đã hỗ trợ hoặc có giao diện mới | Client cũ thiếu field bị từ chối |
| Thêm field required vào response | Consumer mới vẫn đọc response cũ được khi có fallback thích hợp | Consumer mới lỗi khi nói chuyện với server cũ hoặc đọc dữ liệu cũ |
| Xóa/đổi tên field | Tất cả consumer đã ngừng dùng, hoặc có hỗ trợ song song | Client cũ không đọc/ghi được |
| Đổi kiểu field | Có quy tắc chuyển đổi đã được kiểm chứng cho mọi cặp | Decoder lỗi hoặc giá trị bị mất/sai |
| Thêm enum value | Reader có chiến lược xử lý unknown value | Client cũ có switch exhaustive hoặc mặc định nguy hiểm |
| Đổi tên endpoint, RPC, topic | Có alias/dual routing trong giai đoạn chuyển tiếp | Consumer gọi địa chỉ cũ bị lỗi |
| Đổi error/status semantics | Chỉ khi client không phụ thuộc hành vi cũ | Retry sai, UX sai, duplicate side effects |
| Đổi ý nghĩa field nhưng giữ type | Hầu như phải coi là phá hợp đồng nếu meaning đã công bố | Sai nghiệp vụ âm thầm |
| Thay quyền truy cập hoặc scope | Có kế hoạch di trú client và authorization | Client hợp lệ cũ bị từ chối hoặc rò rỉ quyền |

Cột “có thể tương thích” luôn là điều kiện. **“Thêm trường là an toàn” không phải chân lý phổ quát.** Một consumer cũ có thể dùng JSON validator `additionalProperties: false`, một client có switch không có nhánh default, hoặc một dịch vụ yêu cầu response chính xác tuyệt đối.

## 6. Ví dụ thực tế: thêm trường vào HTTP response

Ban đầu Catalog API trả:

```json
{
  "productId": "sku-17",
  "name": "Bàn phím",
  "priceMinor": 490000,
  "currency": "VND"
}
```

Phiên bản mới thêm:

```json
{
  "productId": "sku-17",
  "name": "Bàn phím",
  "priceMinor": 490000,
  "currency": "VND",
  "promotionBadge": "Ưu đãi tuần này"
}
```

Nếu client cũ chỉ đọc `productId`, `name`, `priceMinor`, `currency` và bỏ qua thuộc tính chưa biết, response mới thường có thể dùng được. Nhưng nếu client cũ dùng bộ giải mã strict và reject mọi field không có trong DTO, nó có thể thất bại. Đó là lý do tính tương thích phải được kiểm tra **trên consumer thật**, không chỉ từ phía provider.

Ngược lại, client mới muốn hiển thị `promotionBadge` phải chấp nhận server cũ không trả thuộc tính đó trong thời gian rolling deployment. Nếu client mới coi trường là bắt buộc rồi hiển thị lỗi, rollout theo thứ tự server/client có thể gặp vấn đề.

Quy tắc hợp lý:

- Field hiển thị mới thường nên optional trong giai đoạn đầu.
- Client mới cần hành vi khi field vắng mặt hoặc null.
- Provider không âm thầm thay `priceMinor` từ đơn vị nhỏ nhất thành số tiền thập phân.
- Một tính năng không thể hỗ trợ trên server cũ cần được feature-gate, capability-detect hoặc tách contract có chủ đích.

## 7. Thêm trường bắt buộc vào request: ví dụ phá tương thích ngược

Giả sử ban đầu endpoint tạo đơn nhận:

```http
POST /orders
Content-Type: application/json

{"customerId":"cust-7","items":[{"sku":"sku-17","quantity":1}]}
```

Nhóm Ordering cần bổ sung `salesChannel` để áp dụng chính sách theo kênh bán. Nếu server mới ngay lập tức yêu cầu mọi request có `salesChannel`, client cũ đang hoạt động sẽ bị trả 400 và không thể tạo đơn. Đây là breaking change đối với **client cũ → server mới**.

Một lộ trình an toàn hơn:

1. Server mới hỗ trợ cả request chưa có `salesChannel` và request có field mới.
2. Khi không có field, áp dụng một quy tắc chuyển tiếp có nghĩa rõ, ví dụ `UNKNOWN` hoặc suy ra từ loại client nếu đáng tin cậy; không tự gán giá trị làm thay đổi giá hay quyền sai nghiệp vụ.
3. Công bố schema mới với `salesChannel` là optional ở giai đoạn chuyển tiếp.
4. Nâng client theo từng nhóm, đo tỷ lệ gửi field mới.
5. Khi đã xử lý hoặc nâng cấp các client còn lại, cân nhắc chuyển sang contract mới có yêu cầu field bắt buộc.
6. Nếu không thể cung cấp default nghiệp vụ đúng, chọn endpoint/version mới hoặc phản hồi lỗi có kế hoạch chuyển đổi rõ, thay vì giả vờ tương thích.

**Lưu ý:** Một field optional ở syntax vẫn có thể mang tính required về nghiệp vụ trong vài ngữ cảnh. Cần viết rõ điều kiện hợp lệ; “optional” không thay thế business validation.

## 8. Những thay đổi nhỏ vẫn có thể phá hợp đồng HTTP

### 8.1. Đổi HTTP status code

Một API xử lý job trước đây trả 200 kèm kết quả hoàn tất; nay trả 202 với ID của công việc đang chờ. Cả hai response có thể dùng JSON hợp lệ nhưng ý nghĩa khác nhau. Client cũ coi mọi mã 2xx là hoàn tất sẽ hiển thị báo cáo chưa tồn tại hoặc thực hiện bước tiếp theo quá sớm.

Khi chuyển sang xử lý bất đồng bộ, phải định nghĩa endpoint tra cứu trạng thái và chính sách client; có thể cần version mới hoặc giai đoạn hỗ trợ song song.

### 8.2. Thay chính sách phân trang

Một API trước đây trả toàn bộ danh sách, nay chỉ trả trang đầu nếu không gửi `pageSize`. Mọi trường trong JSON vẫn đúng type nhưng client cũ âm thầm thiếu dữ liệu. Đây là thay đổi hành vi có thể phá hợp đồng, không chỉ là “tối ưu performance”.

### 8.3. Thắt chặt validation

Server từng chấp nhận `customerRef` có dấu gạch ngang, nhưng sau cập nhật chỉ cho chữ và số. Nếu có client hợp lệ cũ đang gửi giá trị chứa dấu gạch ngang, hợp đồng đã bị phá dù không thay request schema rõ ràng.

### 8.4. Thay ý nghĩa trường null và vắng mặt

Với một PATCH request, “không gửi field” có thể có nghĩa “giữ nguyên”, còn gửi `null` có nghĩa “xóa giá trị”. Nếu server mới coi hai trường hợp như nhau, có thể xóa dữ liệu ngoài ý muốn. Schema và contract phải định nghĩa rõ absent, null và default.

### 8.5. Đổi cơ chế xác thực

Một endpoint trước đây chấp nhận scope `orders:read`, nay đòi `orders:admin`. Client hiện tại bị 403 dù request/response không đổi. Thay đổi auth là breaking change với những consumer được phép trước đó; cần xác định quyền mới và lộ trình nâng cấp.

## 9. Protobuf: field number quyết định wire compatibility

Với Protocol Buffers, tên field phục vụ người đọc và generated code, trong khi **field number** là một phần quan trọng của dữ liệu nhị phân trên wire. Ví dụ:

```protobuf
syntax = "proto3";

package orders.v1;

message OrderSummary {
  string order_id = 1;
  int64 total_minor = 2;
  string currency = 3;
}
```

Muốn thêm một field optional, có thể bổ sung số chưa dùng:

```protobuf
message OrderSummary {
  string order_id = 1;
  int64 total_minor = 2;
  string currency = 3;
  optional string promotion_code = 4;
}
```

Consumer cũ thường có thể bỏ qua field 4 khi đọc binary message nếu library và hợp đồng được triển khai phù hợp. Consumer mới đọc binary message cũ có thể thấy field 4 vắng mặt và dùng presence semantics để phân biệt. Nhưng cần kiểm tra các client và mapping của chúng, không chỉ dựa vào quy tắc chung.

### 9.1. Không dùng lại tag đã xóa

Giả sử một schema cũ có `string internal_reference = 5;`. Sau khi ngừng sử dụng, không nên gán field 5 cho một `customer_id` mới. Dữ liệu lịch sử có thể chứa tag 5 với nghĩa cũ và bị đọc thành nghĩa mới.

Một cách bảo vệ:

```protobuf
message OrderSummary {
  string order_id = 1;
  int64 total_minor = 2;
  string currency = 3;

  reserved 5;
  reserved "internal_reference";

  optional string promotion_code = 6;
}
```

Cơ chế `reserved` giúp ngăn tái sử dụng số và tên đã loại bỏ, nhưng không sửa dữ liệu đã sai hoặc bảo đảm mọi consumer đủ tương thích. Việc đổi kiểu field cần kiểm tra chính sách wire compatibility cụ thể; không suy ra “cùng là số” thì luôn an toàn.

### 9.2. Source compatibility khác wire compatibility

Đổi tên `order_id` thành `order_reference` và giữ tag 1 có thể không làm thay đổi cách giải mã Protobuf binary ở tầng thấp. Tuy nhiên generated accessor trong Java/Go/Python có thể đổi, gây lỗi biên dịch khi client cập nhật schema hoặc thư viện contract. Khi chuyển qua Protobuf JSON mapping, tên trường còn có thể ảnh hưởng cách map JSON.

Vì vậy phải xét đường đi thật: binary Protobuf, Protobuf JSON, generated code và mapping domain. Không đánh dấu thay đổi “non-breaking” chỉ vì chạy được một kiểm thử round-trip nhị phân.

### 9.3. Proto3 default và presence

Với một scalar không bật explicit presence, dữ liệu thiếu có thể được biểu diễn bằng giá trị mặc định. Ví dụ một `int32 quantity = 4;` không có mặt thường được đọc thành 0 theo API generated thông thường. Nếu 0 mang nghĩa nghiệp vụ khác “không gửi”, cần dùng cơ chế presence như `optional` hoặc thiết kế wrapper/message phù hợp.

Khi thêm field mới, đừng mặc định zero/empty là giá trị an toàn. Một enum nên dành giá trị 0 cho `UNSPECIFIED` thay vì `PAID` hoặc `SUCCESS`.

### 9.4. Enum mới là tình huống cần xử lý

```protobuf
enum PaymentStatus {
  PAYMENT_STATUS_UNSPECIFIED = 0;
  PAYMENT_STATUS_PENDING = 1;
  PAYMENT_STATUS_CAPTURED = 2;
  PAYMENT_STATUS_FAILED = 3;
}
```

Nếu producer mới bổ sung `PAYMENT_STATUS_REQUIRES_ACTION = 4`, consumer cũ có thể nhận một giá trị chưa biết theo cách library của ngôn ngữ tương ứng. Nó không được tự coi trạng thái lạ là CAPTURED hay FAILED. Trong các thao tác tiền, phản ứng an toàn thường là giữ trạng thái chưa rõ, không thực hiện tác dụng phụ và yêu cầu truy vấn/đối soát.

### 9.5. Tách version theo package khi cần breaking change thực sự

Có thể khai báo `orders.v1`, `orders.v2` hoặc service method mới khi một mô hình không thể phát triển tương thích. Tuy nhiên không cần tăng major version cho mọi trường thêm tùy chọn. Version mới phải đi kèm kế hoạch cho các client cũ và độ dài thời gian hỗ trợ song song.

## 10. Event schema: hai chiều tương thích và dữ liệu đã lưu

Giao tiếp bất đồng bộ có một thách thức khác: thông điệp không nhất thiết được tiêu thụ ngay và có thể được replay nhiều lần. Consumer mới phải hiểu cả những event cũ mà hệ thống đã lưu.

Giả sử event v1:

```json
{
  "eventType": "order.confirmed",
  "schemaVersion": 1,
  "eventId": "evt-19",
  "data": {
    "orderId": "ord-19",
    "confirmedAt": "2026-11-11T09:00:00Z"
  }
}
```

Event v2 thêm tổng tiền đã xác nhận:

```json
{
  "eventType": "order.confirmed",
  "schemaVersion": 2,
  "eventId": "evt-20",
  "data": {
    "orderId": "ord-20",
    "confirmedAt": "2026-11-11T09:01:00Z",
    "confirmedTotalMinor": 245000,
    "currency": "VND"
  }
}
```

Cần thử:

- **Consumer v1 đọc event v2:** Có bỏ qua field mới được không? Nếu parser strict sẽ lỗi? Nếu không biết schema v2, có phân biệt bản ghi được phép bỏ qua với bản ghi buộc xử lý không?
- **Consumer v2 đọc event v1:** Có xử lý event lịch sử không chứa `confirmedTotalMinor` không? Không được tự gán 0 nếu 0 có nghĩa “đơn miễn phí”.
- **Consumer v2 xử lý v1 và v2 trong cùng stream:** Có tìm schema đúng theo version/registry ID không? Có lưu được projection nhất quán không?
- **Consumer hiện tại replay toàn bộ lịch sử:** Có đòi dữ liệu mà trước đây chưa từng được ghi? Có dùng giá hiện tại để bù vào giá lúc xác nhận, gây sai dữ liệu lịch sử không?

### 10.1. Event envelope và version khác với business version

Một event có thể chứa `eventId`, `eventType`, `schemaVersion`, `occurredAt`, `aggregateId`, `aggregateVersion`, `correlationId` và `data`.

- `schemaVersion`: phiên bản cấu trúc/hợp đồng.
- `aggregateVersion`: thứ tự thay đổi trạng thái của một aggregate nếu domain có cơ chế tăng phiên bản.
- `serviceRelease`: phiên bản artifact triển khai.

Không dùng `schemaVersion=2` để suy ra event mới hơn trong lịch sử của một đơn hàng. Một sự kiện v1 có thể xảy ra sau một sự kiện v2 nếu rollout hỗn hợp. Khi cần thứ tự nghiệp vụ, phải có khóa và sequence phù hợp.

### 10.2. Event-carried state transfer và coupling dữ liệu

Consumer duy trì một read projection có thể cần event mang vài trường trạng thái đã được công bố để tránh gọi lại producer cho từng event. Điều đó hợp lý nếu payload được thiết kế rõ và tuân thủ bảo mật.

Nhưng phát nguyên entity database lên broker để “chống breaking change” là phản tác dụng: mọi thay đổi ORM/schema vô tình trở thành thay đổi hợp đồng cho hàng loạt consumer. Integration event nên công bố **sự thật nghiệp vụ hoặc dữ liệu được chọn có chủ đích**, không phải bản sao không kiểm soát của nội bộ.

### 10.3. Event không giao đúng một lần chỉ nhờ schema

Định nghĩa JSON Schema/Avro/Protobuf không tạo ra bảo đảm exactly-once của tác dụng phụ nghiệp vụ. Consumer cần chịu được redelivery và replay; producer nên có cách đảm bảo không mất event sau khi commit, ví dụ transactional outbox phù hợp với môi trường. Một event cũ replay không được làm gửi lại email hoặc tạo thêm thanh toán nếu điều đó không được phép.

Tương thích hợp đồng phải bao gồm **hành vi khi nhận lại dữ liệu cũ**, không chỉ khả năng parse nó.

## 11. Schema registry và các mức kiểm tra tương thích

Các hệ thống dùng Avro, Protobuf hoặc JSON Schema có thể tích hợp **schema registry** để lưu schema, gán ID, phân phối cho producer/consumer và kiểm tra quy tắc tương thích cấu trúc.

Một số thuật ngữ chính sách thường gặp:

| Chế độ | Trực giác | Cần kiểm chứng |
| --- | --- | --- |
| Backward | Reader mới đọc dữ liệu writer cũ | Dữ liệu/event lịch sử còn được đọc không? |
| Forward | Reader cũ đọc dữ liệu writer mới | Consumer chưa nâng cấp có xử lý được không? |
| Full | Cần hai chiều | Cả producer/consumer cũ mới có cùng tồn tại được không? |
| Transitive | Kiểm tra so với nhiều phiên bản trong lịch sử | Phạm vi phiên bản hỗ trợ dài tới đâu? |
| None | Không tự động chặn thay đổi cấu trúc | Phải quản lý rủi ro bằng quy trình/kiểm thử khác |

Các nhãn này là **khái niệm tổng quát**. Mỗi registry và mỗi loại schema có quy tắc cụ thể khác nhau; không áp dụng công thức giống hệt cho JSON Schema, Protobuf và Avro.

Ví dụ với Avro, việc thêm field có default phù hợp có thể tạo điều kiện để reader mới đọc record cũ. Với JSON Schema, `required`, `additionalProperties`, `oneOf` hoặc validation rule có thể ảnh hưởng khác. Với Protobuf, field numbers, wire types và các quy tắc evolve schema là trọng tâm. Phải dùng bộ kiểm tra đúng của hệ sinh thái đang triển khai.

**Schema registry thường không nhận biết thay đổi ngữ nghĩa.** Đổi định nghĩa “gross amount” sang “net amount” trong một trường integer có thể vượt qua compatibility check nhưng phá báo cáo kinh doanh.

## 12. Định nghĩa breaking change bằng hành vi consumer, không bằng cảm giác

Một thay đổi là **breaking** đối với một tập consumer cụ thể nếu có consumer hợp lệ đang sử dụng contract trước đó mà không thể tiếp tục đạt kết quả theo cam kết sau thay đổi, và không có quy tắc chuyển đổi hoặc thời gian di trú phù hợp.

Có ba cách breaking change xuất hiện:

### 12.1. Phá cấu trúc rõ ràng

- Xóa field bắt buộc khỏi response.
- Đổi JSON array thành object.
- Bỏ một gRPC method hoặc thay signature không tương thích.
- Tái sử dụng Protobuf tag với nghĩa khác.
- Thay tên event/topic mà không hỗ trợ consumer cũ.

Dạng này thường dễ được schema diff hoặc contract test phát hiện.

### 12.2. Phá nghĩa nhưng không phá parser

- `amount` vẫn là số nhưng đổi từ minor units sang major units.
- `OrderConfirmed` trước nghĩa là đã giữ hàng; nay nghĩa là chỉ mới nhận request.
- `isActive=true` trước cho phép sử dụng, nay chỉ nghĩa là tài khoản tồn tại.
- `expiresAt` chuyển từ UTC timestamp sang local time không ghi timezone.
- Thay thứ tự hoặc chính sách ưu tiên giữa các business rule nhưng giữ endpoint.

Dạng này nguy hiểm vì response vẫn có thể là 200, các test chỉ kiểm tra type vẫn thành công, và sai sót xuất hiện ở dữ liệu hoặc hành động downstream.

### 12.3. Phá vận hành

- Hạ rate limit từ 2.000 xuống 100 request/phút mà không có kế hoạch.
- Buộc thêm token/scope mới mà client cũ không thể có.
- Giảm timeout phía server khiến job trước đây hoàn tất nay luôn thất bại.
- Tắt retry hoặc thay ngữ nghĩa idempotency key.
- Rút ngắn retention event khiến consumer chậm không kịp đọc lại.

Đây cũng là thay đổi contract nếu những hành vi được cam kết hoặc là phần thiết yếu để consumer hợp lệ hoạt động.

## 13. Expand → migrate → contract: quy trình tránh khóa phiên bản

Mẫu phát triển thường dùng là **expand → migrate → contract**. Thay vì đổi hợp đồng cho toàn bộ hệ thống trong một lần, trước tiên mở rộng để chấp nhận cũ và mới, chuyển các consumer, rồi mới bỏ phần cũ.

### 13.1. Bước 1 — Expand: cho phiên bản mới cùng tồn tại

Ví dụ Payment API cần chuyển từ `amount` sang `amountMinor`:

- Server mới hỗ trợ cả request cũ và mới trong một giai đoạn.
- Quy tắc chuyển đổi được xác định bởi domain owner; không tùy tiện nhân 100 cho mọi loại tiền.
- Response có thể cung cấp hai trường trong giai đoạn chuyển tiếp, nhưng không để chúng mâu thuẫn.
- OpenAPI hoặc schema được cập nhật với field mới, deprecation và mô tả ý nghĩa.
- Các consumer cũ vẫn có thể dùng hợp đồng trước đó.

Nếu không có cách chuyển đổi chính xác, **không nên giả vờ có compatibility**. Có thể cần `/v2` với contract khác, hoặc một service adapter tạm thời.

### 13.2. Bước 2 — Migrate: chuyển consumer theo từng phần

- Nâng SDK/client, worker hoặc consumer để hiểu cả cũ và mới.
- Triển khai consumer có thể đọc dữ liệu mới **trước** khi producer bắt đầu gửi định dạng mới không tương thích.
- Theo dõi lưu lượng của từng version, request thiếu trường mới và lỗi parse.
- Với message có retention, nâng consumer sao cho đọc được event lịch sử trước khi yêu cầu replay.
- Thử rolling update và canary; không chỉ kiểm thử toàn bộ hệ thống cùng chạy version mới.

### 13.3. Bước 3 — Contract: bỏ hành vi cũ có kiểm soát

- Chỉ bỏ field/endpoint/topic cũ khi đã biết consumer liên quan không còn dùng hoặc đã qua chính sách hỗ trợ được thông báo.
- Với mobile app hoặc đối tác bên ngoài khó buộc nâng cấp, có thể phải duy trì v1 lâu hơn.
- Với event store có replay dài hạn, ngừng phát v1 **không đồng nghĩa** có thể xóa decoder v1.
- Có telemetry trước khi tắt và kế hoạch rollback nếu phát hiện consumer còn phụ thuộc.

Không phải mọi thay đổi cần đủ ba giai đoạn phức tạp. Một trường optional mới có thể đơn giản. Nhưng khi thực sự có breaking change, đây là khung an toàn giúp tránh yêu cầu “deploy tất cả cùng lúc”.

## 14. Thứ tự rollout khác nhau cho request và response

Giả sử có Server S và Client C, cả hai sẽ được nâng cấp từ v1 lên v2.

### 14.1. Thay đổi request

Nếu client mới gửi thêm field mà server cũ không biết, **nâng server trước** thường là lựa chọn hợp lý. Server mới chấp nhận request cũ và mới; sau đó mới bật client gửi field mới.

Tuy nhiên, nếu server cũ bỏ qua field lạ và field không quan trọng, client mới có thể chạy mà không phá cú pháp, nhưng có thể hiểu sai việc server đã xử lý hay chưa. Không được coi “ignore unknown field” là bằng chứng chức năng mới đã được thực hiện.

### 14.2. Thay đổi response

Nếu server mới gửi thêm enum value, **nâng client để hiểu trạng thái mới trước** khi server bắt đầu phát giá trị đó. Một server mới có thể giữ tính năng dưới feature flag tới khi consumer đã sẵn sàng.

Một endpoint có cả request và response thay đổi có thể cần rollout nhiều bước:

    S_v1 + C_v1
       |
       | Triển khai server hỗ trợ cả contract cũ/mới
       v
    S_compatible + C_v1
       |
       | Triển khai client có thể đọc hai kiểu response
       v
    S_compatible + C_compatible
       |
       | Bật producer/server gửi kiểu mới
       v
    S_v2 + C_compatible
       |
       | Khi đủ điều kiện, bỏ hỗ trợ cũ
       v
    S_v2 + C_v2

Đây là sơ đồ nguyên lý, không phải thứ tự bắt buộc duy nhất. Một số thay đổi không thể dùng dual format hoặc có yêu cầu bảo mật không cho phép tiếp tục hành vi cũ; lúc đó cần version song song, adapter hoặc kế hoạch chuyển đổi khác.

## 15. Thay đổi enum: ví dụ thường bị đánh giá thấp

Hãy xét trạng thái đơn hàng:

    CREATED
    CONFIRMED
    CANCELLED

Producer thêm:

    REQUIRES_MANUAL_REVIEW

Một consumer cũ có logic:

    switch (status) {
      case "CREATED": ...
      case "CONFIRMED": releaseToWarehouse();
      case "CANCELLED": ...
      default: throw new Error("Unknown status");
    }

Nếu nó nhận trạng thái mới, có thể lỗi. Nếu một client khác thay `default` bằng `releaseToWarehouse()`, hệ thống có thể giao hàng sai. Vì vậy xử lý enum lạ không phải chỉ là sửa parser. **Fallback phải có nghĩa nghiệp vụ an toàn.**

Với màn hình đọc, có thể hiển thị “Đang xử lý” và giữ nguyên dữ liệu nếu hợp đồng cho phép. Với thao tác chi tiền hoặc giao hàng, có thể phải ngừng quyết định và tra cứu trạng thái authoritative. Cần xác định nhánh unknown trong contract và test.

## 16. Null, optional, default và “không có dữ liệu” khác nhau

Giả sử một event `PaymentAuthorized` v1 không có `capturedAt`; v2 bổ sung field này.

Các giá trị khác nhau có thể mang những nghĩa khác nhau:

- Field **không tồn tại**: phiên bản cũ không biết đến thông tin hoặc producer chưa công bố.
- Field `null`: producer chủ động không cung cấp/không có giá trị, tùy contract.
- Field `""`: chuỗi rỗng, có thể là dữ liệu không hợp lệ.
- Field có timestamp: một sự kiện đã xảy ra tại mốc thời gian.
- Field được đặt mặc định bởi decoder: không nhất thiết là sự thật nghiệp vụ.

Consumer không được suy luận rằng event cũ thiếu `capturedAt` nghĩa là “chưa bao giờ captured”. Có thể event cũ không ghi nhận thông tin đó. Nếu cần tính toán lịch sử, có thể sử dụng trạng thái `UNKNOWN`, schema upcaster, data migration có kiểm chứng hoặc đối soát. **Không bịa giá trị lịch sử từ dữ liệu hiện tại.**

Điều tương tự áp dụng với tiền: nếu `discountMinor` chưa từng được gửi, mặc định 0 chỉ đúng khi hợp đồng thực sự cam kết “không gửi nghĩa là không giảm giá”; nếu không, 0 có thể làm sai báo cáo.

## 17. Versioning: không phải mọi breaking change đều cần thay URL

Các chiến lược phổ biến:

| Chiến lược | Khi có thể phù hợp | Chi phí |
| --- | --- | --- |
| Phát triển tương thích trong cùng endpoint | Thêm field optional, cải thiện không phá hợp đồng | Cần kiểm tra consumer và semantic |
| API path `/v1`, `/v2` | Hai hợp đồng thật sự khác và cần chạy song song | Vận hành hai phiên bản, deprecation |
| Header/media type version | Cần giữ resource URL, chọn cách biểu diễn | Gateway/client/tooling phức tạp hơn |
| RPC method/package v2 | Thay đổi interface Protobuf không thể tương thích | Duy trì namespace và mapping |
| Topic/event type mới | Thay đổi business meaning hoặc schema lớn | Consumer migration, dual publication |
| Adapter/anti-corruption layer | Cần cách ly hệ thống/đối tác cũ | Chi phí chuyển đổi và duy trì |

**Đổi `/v1` thành `/v2` không tự làm hệ thống tương thích.** Nó chỉ tạo một bề mặt hợp đồng mới; vẫn phải xác định ai dùng v1, khi nào v1 ngừng, dữ liệu giữa hai phiên bản được chuyển thế nào và những client nào chưa thể cập nhật.

Ngược lại, tăng `info.version` trong OpenAPI từ 1.2 sang 1.3 chưa chắc là breaking change. Phiên bản tài liệu, version của service build và major version của API là những khái niệm cần quản lý riêng.

## 18. Di trú lược đồ sự kiện không giống di trú HTTP API

HTTP response có vòng đời ngắn và client thường gọi server hiện tại. Event có thể được giữ lâu và tiêu thụ trễ, tạo ra ba kiểu đồng tồn tại:

1. **Producer cũ và mới cùng phát** trong thời gian rolling deployment.
2. **Consumer cũ và mới cùng chạy** hoặc dùng consumer group/partition khác nhau.
3. **Record cũ vẫn nằm trong broker hoặc event store** và có thể được đọc lại về sau.

Một kế hoạch sự kiện v1 → v2 có thể gồm:

- Định nghĩa v2 với schema và semantic rõ.
- Consumer mới hiểu cả v1 và v2; với event cũ có trường thiếu, xử lý bằng optional/upcaster mà không bịa nghĩa.
- Producer chỉ bắt đầu phát v2 khi có đủ consumer được phép đọc v2.
- Nếu cần dual-publish v1 và v2, thiết kế correlation và deduplication để không tính cùng một business fact hai lần.
- Khi ngừng phát v1, vẫn giữ decoder v1 nếu event store còn replay v1.
- Theo dõi consumer lag, lỗi schema, DLQ và tỷ lệ replay thành công.

**Dual-publish cần kiểm soát tác dụng phụ.** Nếu một consumer vô tình đăng ký cả hai topic và xử lý v1/v2 như hai event nghiệp vụ độc lập, nó có thể cộng doanh thu hai lần hoặc gửi hai email. Event identity/business idempotency phải phản ánh cùng một sự thật, không chỉ ID kỹ thuật của từng bản ghi phát ra.

## 19. Thiết kế kiểm thử contract theo ma trận phiên bản

Một bộ test chỉ chạy C_v2 với S_v2 không phát hiện lỗi trong giai đoạn nâng cấp. Hãy mô tả các kết hợp thật sự có thể xảy ra.

| Client/Consumer | Server/Producer | Mục tiêu kiểm tra |
| --- | --- | --- |
| v1 | v1 | Hành vi đang được cam kết |
| v1 | v2 | Server mới vẫn phục vụ client cũ; producer mới không phá consumer cũ |
| v2 | v1 | Client mới có fallback với server cũ; consumer mới đọc event cũ |
| v2 | v2 | Tính năng mới hoạt động đúng |
| v2 | Event lịch sử v1 | Replay và dựng projection đúng khi thiếu field mới |

Không phải lúc nào hệ thống cũng cần hỗ trợ cả bốn kết hợp. Có thể có một hướng nâng cấp được thiết kế rõ và chặn hướng chưa hỗ trợ. Quan trọng là **ghi nhận điều được hỗ trợ và kiểm thử theo kế hoạch rollout**, thay vì cho rằng version khác nhau luôn phải hoạt động.

### 19.1. Schema diff và static checks

- OpenAPI: kiểm tra thay đổi path/method, request required field, response field, status code và security scheme.
- Protobuf: kiểm tra field number, reserved fields, wire type, enum và service method.
- JSON Schema/Avro/event: kiểm tra kiểu, default, required, unknown field policy và compatibility với các schema được hỗ trợ.
- Định nghĩa deprecation và version theo quy ước của hệ thống.

Kiểm tra tự động giúp phát hiện các dạng breaking change cấu trúc, nhưng không thể hiểu đầy đủ nghĩa doanh nghiệp.

### 19.2. Provider và consumer contract tests

Provider phải chứng minh implementation thật thực hiện đúng contract công bố. Consumer có thể ghi lại các kỳ vọng cụ thể của mình: trạng thái nào được phép, field nào được dùng và khi lỗi được xử lý ra sao.

Ví dụ consumer InvoiceService cần số tiền và `currency` từ event `PaymentCaptured`. Contract test phải phát hiện khi producer bỏ `currency`, đổi đơn vị tiền hoặc phát `PaymentAuthorized` thay cho `PaymentCaptured`. Trường hợp đổi đơn vị có thể cần test hành vi/fixture, vì schema type check không thấy khác biệt.

### 19.3. Integration tests dưới rollout trộn phiên bản

- Server mới nhận request từ client cũ.
- Client mới nhận response thiếu field mới khi server cũ còn chạy.
- Consumer cũ nhận event từ producer mới.
- Consumer mới replay event v1.
- Protobuf binary và JSON mapping được kiểm tra theo đường truyền thật.
- Thay đổi enum, null/absent và error code có hành vi an toàn.
- Retry, redelivery và idempotency không tạo tác dụng phụ trùng.
- Canary gặp cả hai phiên bản của dependency trong rolling deployment.

Không cần mọi test phải là end-to-end khổng lồ; có thể dùng schema checks, component tests, consumer contract tests và một số integration tests trọng điểm để phủ các rủi ro khác nhau.

## 20. Bài toán thực hành: chuyển từ số tiền thập phân sang minor units

Một hệ thống có Ordering, Pricing, Payment và Reporting. Hợp đồng v1 dùng:

```json
{"orderId":"ord-52","amount":99.95,"currency":"USD"}
```

Nhóm muốn chuyển thành:

```json
{"orderId":"ord-52","amountMinor":9995,"currency":"USD"}
```

### 20.1. Vì sao đổi trực tiếp là breaking change?

- Client v1 vẫn gửi `amount` nhưng server v2 yêu cầu `amountMinor`.
- Client v2 có thể gửi `amountMinor` đến server v1 không hiểu field này.
- Reporting đang đọc `amount` nhưng event mới không còn trường đó.
- Nếu thử dùng lại tên `amount` và chỉ đổi đơn vị, parser có thể không lỗi nhưng số tiền sai 100 lần.
- Với tiền tệ có số chữ số thập phân khác nhau, không thể dựa vào quy tắc nhân 100 chung cho mọi `currency`.
- Event lịch sử chưa có `amountMinor`; consumer mới cần biết cách đọc bản cũ và tính toán đúng từ snapshot.

### 20.2. Lộ trình chuyển đổi gợi ý

**Giai đoạn mở rộng:** Provider chấp nhận contract cũ và mới theo quy tắc xử lý không mơ hồ; thêm `amountMinor` rõ đơn vị và tránh cho hai trường mâu thuẫn trong cùng request.

**Giai đoạn consumer:** Nâng Reporting để có thể đọc event v1 và v2, Payment để có thể chấp nhận cả hai dạng request nếu được phép, và các lớp mapping từ contract vào domain money type nội bộ.

**Giai đoạn producer:** Nâng Ordering/Pricing tạo dữ liệu mới; nếu cần dual response, định nghĩa một nguồn tính toán duy nhất để tránh hai trường khác giá trị.

**Giai đoạn ngừng cũ:** Kiểm tra telemetry, hợp đồng đối tác, job chạy định kỳ, event retention và các client chưa nâng cấp trước khi bỏ `amount`.

**Tình huống cần xem xét:** Nếu amount cũ được lưu bằng floating-point và đã bị mất độ chính xác, một phép chuyển đổi công thức đơn giản không nhất thiết khôi phục được giá trị gốc. Có thể cần đối soát dữ liệu đã lưu theo chính sách được chủ domain chấp thuận.

## 21. Quan sát tương thích trong production

Các chỉ số giúp trả lời “đã an toàn để ngừng v1 chưa?” gồm:

- Tỷ lệ request theo API version, đường dẫn và client identifier được phép ghi nhận.
- Tỷ lệ request còn dùng field cũ hoặc thiếu field mới.
- Số response dùng enum/status code mới và lỗi của client tương ứng.
- Lỗi giải mã/deserialization theo schema version ở consumer.
- Consumer lag, retry, DLQ, poison messages và lỗi replay.
- Số event v1/v2 phát trong rollout; số consumer còn cần decoder cũ.
- Tỷ lệ 4xx/5xx do validation, auth hoặc phiên bản không tương thích.
- Business mismatch: đơn bị từ chối sai, giao dịch trùng, số tiền sai, báo cáo lệch.
- Những client ngoại tuyến/dùng version cũ chưa thể đo trực tiếp; cần chính sách hỗ trợ ngoài telemetry hiện có.

Với external API, không phải mọi đối tác đều cung cấp số liệu theo phiên bản hoặc nâng cấp theo lịch của mình. Quyết định bỏ v1 nên dựa trên hợp đồng hỗ trợ và cam kết thông báo, không chỉ việc “7 ngày qua không có request”.

Khi làm canary, giám sát cả lỗi kỹ thuật lẫn hành vi: 200 OK tăng không chứng minh tiền, tồn kho hoặc trạng thái nghiệp vụ vẫn đúng.

## 22. Checklist trước khi chấp nhận một thay đổi

### Xác định ranh giới

- Ai sở hữu hợp đồng? Ai là producer/provider và ai là consumer?
- Đang đổi HTTP request, HTTP response, RPC message, event hay hành vi vận hành?
- Có client mobile, batch job, partner hoặc event lịch sử nào không thể nâng đồng thời không?
- Field đang đổi là business value, metadata hay chi tiết nội bộ?
- Có bất biến về tiền, quyền, trạng thái hoặc thứ tự cần bảo vệ không?

### Kiểm tra chiều tương thích

- Client cũ có gửi request tới server mới được không?
- Client mới có nói chuyện với server cũ khi rolling deployment không?
- Client cũ có đọc response mới được không?
- Consumer cũ có xử lý event mới được không?
- Consumer mới có giải mã event cũ và replay lịch sử không?
- Unknown field, enum, null, default và missing field được xử lý thế nào?

### Quyết định kế hoạch chuyển đổi

- Có thể mở rộng contract trước khi buộc consumer đổi không?
- Có cần một endpoint, RPC method, topic hoặc schema version mới không?
- Nếu dual-write/dual-publish, có nguy cơ xử lý cùng business fact hai lần không?
- Khi nào ngừng phiên bản cũ; theo bằng chứng và chính sách nào?
- Nếu rollback server sau khi client mới triển khai, client mới có tiếp tục chạy không?
- Có bộ kiểm thử gồm các cặp version quan trọng và business fixtures không?

Một thay đổi không có câu trả lời cho những câu hỏi trọng yếu chưa đủ điều kiện gọi là non-breaking chỉ vì một thư viện serialization nói nó tương thích.

## 23. Bài tập tình huống: phân loại và đề xuất lộ trình

Xét một hệ thống có Catalog, Ordering, Payment và Notification.

**Tình huống 1.** Catalog thêm `thumbnailUrl` vào response JSON, nhưng một ứng dụng di động cũ reject unknown properties. Đây có phải breaking change không? Có thể thay đổi client hoặc policy response như thế nào khi ứng dụng cũ chưa nâng cấp?

**Tình huống 2.** Ordering thêm `deliveryWindow` bắt buộc vào request tạo đơn. Server mới được triển khai trước client. Những client cũ sẽ gặp vấn đề gì? Có thể dùng contract mới hoặc default nghiệp vụ hợp lý không?

**Tình huống 3.** Payment đổi nghĩa `AUTHORIZED` thành “đã thu tiền”. Generated Protobuf code và schema registry không báo lỗi. Vì sao đây vẫn là breaking change?

**Tình huống 4.** Producer thêm enum value `REQUIRES_ACTION`, consumer cũ xử lý mọi unknown value thành `SUCCESS`. Có thể gây hậu quả gì, và safe fallback nên được định nghĩa theo business thế nào?

**Tình huống 5.** Event `OrderConfirmed` v2 thêm `confirmedTotalMinor` nhưng hệ thống còn dữ liệu v1 được replay mỗi cuối tháng. Consumer v2 có được mặc định tổng tiền bằng 0 khi field thiếu không? Cần có phương án nào?

**Tình huống 6.** Nhóm gRPC xóa field tag 6 rồi dùng lại tag 6 cho một field khác có cùng wire type. Vì sao vẫn nguy hiểm? `reserved` có vai trò gì?

**Tình huống 7.** Một API trước đây trả 200 sau khi hoàn tất, nay trả 202 sau khi chỉ xếp hàng. Các client cần đổi hiểu biết gì về trạng thái thành công?

**Tình huống 8.** Producer dual-publish sự kiện v1/v2 sang hai topic, một consumer đăng ký cả hai. Cơ chế nào cần có để tránh hai hóa đơn cho cùng một giao dịch?

**Tình huống 9.** Đội muốn tắt `/v1` vì các dashboard không thấy request trong một tháng. Nhưng một đối tác chạy batch theo quý vẫn có quyền sử dụng. Dữ liệu nào và cam kết nào phải được xem xét trước khi tắt?

**Tình huống 10.** Một thay đổi được ghi “backward compatible” trong ticket. Hãy viết lại thành câu kiểm chứng cụ thể nêu rõ writer, reader, version và hành vi mong đợi.

### Câu trả lời định hướng

Với mỗi tình huống, trước tiên chỉ ra **ai sẽ đọc dữ liệu do ai tạo ra**. Sau đó kiểm tra cấu trúc, ý nghĩa và hành vi; chỉ cuối cùng mới chọn cách triển khai. Nếu consumer cũ không thể hiểu dữ liệu mới, cần nâng consumer trước, giữ producer chưa phát kiểu mới hoặc cung cấp version riêng. Nếu consumer mới không đọc dữ liệu cũ, phải giữ fallback/decoder cũ hoặc có cách migrate dữ liệu lịch sử được kiểm chứng.

## 24. Các ngộ nhận cần tránh

1. **“Thêm field luôn non-breaking.”** Sai nếu client parse strict, field mới làm đổi nghĩa hoặc producer/client triển khai sai thứ tự.
2. **“Không thay type là tương thích.”** Sai nếu đơn vị tiền, trạng thái, timezone hoặc business invariant thay đổi.
3. **“Có v2 là đã xử lý xong.”** Version mới vẫn cần hỗ trợ consumer cũ, migration, telemetry và deprecation.
4. **“Protobuf tự bảo đảm mọi tương thích.”** Nó hỗ trợ các quy tắc wire evolution; source, JSON mapping, semantic và hành vi RPC vẫn cần kiểm chứng.
5. **“Schema registry báo PASS thì nghiệp vụ đúng.”** Registry không hiểu tiền đã thu hay chỉ được ủy quyền.
6. **“Consumer mới chỉ cần đọc event mới.”** Replay, lag hoặc rolling deployment có thể buộc đọc event lịch sử.
7. **“Client cũ đọc được field mới nên tính năng mới đã hoạt động.”** Bỏ qua unknown field không có nghĩa server cũ hiểu yêu cầu mới.
8. **“Có thể đổi event type bằng cách rename.”** Hai tên có thể phản ánh hai sự thật khác nhau; đổi nghĩa là thay contract.
9. **“Tất cả client sẽ nâng trong một lần deploy.”** Mobile, partner, batch và rolling updates thường không cho phép giả định đó.
10. **“Thêm default 0 để hợp lệ là đủ.”** Một giá trị kỹ thuật hợp lệ có thể là sự thật nghiệp vụ sai.
11. **“Rollback chỉ việc đưa server cũ lên.”** Client mới hoặc dữ liệu mới có thể không tương thích với server rollback.
12. **“Breaking chỉ là xóa endpoint/field.”** Lỗi hành vi, security policy, status code và delivery semantics cũng có thể phá consumer.

## 25. Tóm tắt thực hành

- **Backward compatibility** theo góc độ dữ liệu: reader mới đọc được dữ liệu do writer cũ tạo.
- **Forward compatibility** theo góc độ dữ liệu: reader cũ đọc được dữ liệu do writer mới tạo.
- Với request–response, luôn viết rõ các cặp **client cũ/server mới**, **client mới/server cũ**, **server mới/client cũ** và **server cũ/client mới**; đừng dùng nhãn backward/forward một cách mơ hồ.
- Một thay đổi có thể hợp schema nhưng **không hợp ngữ nghĩa**; đây là rủi ro lớn với tiền, trạng thái, quyền và thời điểm.
- API HTTP, Protobuf/gRPC và event stream có đặc thù khác nhau: unknown field, tag, enum, status code, event replay và consumer lag.
- **Expand → migrate → contract** giúp nâng phiên bản theo từng bước, tránh lockstep deployment.
- Test phải xét **nhiều phiên bản cùng tồn tại**, dữ liệu lịch sử và hành vi business; không chỉ kiểm tra code mới với code mới.
- Để ngừng phiên bản cũ, cần bằng chứng sử dụng, cam kết hỗ trợ và kế hoạch khôi phục; không đoán từ sự im lặng của log.

Trong microservices, tương thích hợp đồng không đơn giản là “không lỗi khi deserialize”. Nó là khả năng để các bên thay đổi ở những thời điểm khác nhau mà vẫn giữ **ý nghĩa, tính đúng đắn và kỳ vọng vận hành**. Thiết kế contract rõ, giới hạn bề mặt công khai và triển khai theo lộ trình là nền tảng cho tính độc lập thực sự giữa các service.
