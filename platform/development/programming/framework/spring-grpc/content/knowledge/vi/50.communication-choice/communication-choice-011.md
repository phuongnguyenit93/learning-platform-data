# Ghi lại lý do chọn gRPC và giới hạn

Khi xây dựng dịch vụ **SPRING_GRPC**, quyết định dùng gRPC cần xuất phát từ yêu cầu giao tiếp của hệ thống và được ghi lại cùng những giới hạn đã chấp nhận. gRPC cung cấp giao tiếp RPC dựa trên HTTP/2, hợp đồng Protocol Buffers và mã client/server được sinh từ `.proto`. Các đặc điểm này phù hợp với nhiều kết nối service-to-service, nhưng không tự động làm gRPC trở thành lựa chọn tốt nhất cho mọi API.

Một quyết định kiến trúc hữu ích phải trả lời được: hệ thống cần trao đổi dữ liệu theo kiểu nào, ai là client, cần unary hay streaming, yêu cầu về độ trễ và thông lượng ra sao, hạ tầng có hỗ trợ HTTP/2 không, đội vận hành có thể quan sát và xử lý giao thức này không, và những giới hạn nào sẽ được chấp nhận. Bài học này hướng dẫn cách đánh giá và ghi lại các câu trả lời đó để nhóm có thể xem lại khi bối cảnh thay đổi.

## 1. Bắt đầu từ yêu cầu giao tiếp

Trước khi chọn giao thức, hãy mô tả luồng giao tiếp bằng ngôn ngữ nghiệp vụ. Không nên bắt đầu bằng câu hỏi “gRPC có nhanh hơn REST không?” vì tốc độ chỉ là một trong nhiều yếu tố. Một số câu hỏi cần làm rõ:

- **Ai gọi ai?** Service nội bộ, ứng dụng di động, trình duyệt, đối tác bên ngoài hay thiết bị hạn chế tài nguyên?
- **Kiểu tương tác nào?** Một request nhận một response, truyền dữ liệu theo luồng, hay gửi sự kiện bất đồng bộ?
- **Hợp đồng có cần sinh mã không?** Các client Java, Go, Kotlin, Python hoặc ngôn ngữ khác có cần chia sẻ schema và stub được sinh từ một nguồn duy nhất không?
- **Tải có đặc điểm gì?** Kích thước payload, tần suất gọi, số kết nối đồng thời, độ trễ mục tiêu, kích thước message và thời gian sống của stream là bao nhiêu?
- **Yêu cầu lỗi ra sao?** Client cần deadline, cancellation, retry, status có cấu trúc và idempotency ở mức nào?
- **Hạ tầng có đáp ứng không?** Gateway, proxy, load balancer, service mesh, ingress, firewall và công cụ giám sát có hỗ trợ HTTP/2/gRPC theo cách cần thiết không?
- **Ai vận hành?** Đội phát triển có kinh nghiệm Protocol Buffers, quản lý schema, certificate, tracing và xử lý lỗi RPC không?

Hãy ghi cả yêu cầu chức năng và yêu cầu vận hành. Ví dụ, “cần cập nhật tồn kho liên tục” chưa đủ để chọn streaming. Cần xác định luồng dữ liệu có thể kéo dài bao lâu, cần resume sau khi mất kết nối hay không, server có thể gửi dữ liệu theo nhu cầu hay phải kiểm soát backpressure, và client có thể mở bao nhiêu stream đồng thời.

## 2. Những lý do hợp lý để chọn gRPC

gRPC thường phù hợp khi một hoặc nhiều đặc điểm sau là yêu cầu quan trọng:

### Hợp đồng API rõ ràng và sinh mã đa ngôn ngữ

Protocol Buffers định nghĩa service, RPC và cấu trúc message trong file `.proto`. Từ hợp đồng đó, công cụ sinh mã tạo message type và client/server stub cho ngôn ngữ được hỗ trợ. Client và server có thể cùng dựa trên một schema, giảm việc tự đồng bộ tên field, kiểu dữ liệu và chữ ký phương thức.

Ví dụ hợp đồng unary đơn giản:

```proto
syntax = "proto3";

package inventory.v1;

option java_multiple_files = true;
option java_package = "com.example.inventory.v1";

service InventoryService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
}

message GetItemRequest {
  string item_id = 1;
}

message GetItemResponse {
  string item_id = 1;
  int64 available_quantity = 2;
  string version = 3;
}
```

Hợp đồng này giúp client Java sử dụng kiểu `GetItemRequest` và `GetItemResponse` thay vì tự tạo JSON string hoặc tự ánh xạ field. Tuy nhiên, sinh mã không thay thế việc quản lý phiên bản schema: thay đổi `.proto` vẫn phải tuân thủ quy tắc tương thích ngược và xuôi.

### Giao tiếp service-to-service có cấu trúc

gRPC định nghĩa phương thức RPC và status code rõ ràng. Với hệ thống có nhiều service, một hợp đồng thống nhất có thể giúp quản lý interface, sinh stub, áp deadline, truyền metadata và thống nhất cách diễn giải lỗi. Java service trong hệ sinh thái Spring có thể dùng generated stub để gọi service khác, đồng thời tích hợp interceptor và hệ thống quan sát ở tầng gRPC.

### Cần streaming hai chiều hoặc luồng dữ liệu liên tục

gRPC hỗ trợ bốn dạng RPC:

| Dạng RPC | Client gửi | Server trả | Ví dụ phù hợp |
| --- | --- | --- | --- |
| Unary | Một message | Một message | Tra cứu sản phẩm, xác nhận giao dịch |
| Server streaming | Một message | Nhiều message | Theo dõi trạng thái xử lý, nhận cập nhật liên tục |
| Client streaming | Nhiều message | Một message | Tải lô dữ liệu, gửi chuỗi mẫu đo |
| Bidirectional streaming | Nhiều message | Nhiều message | Kết nối tương tác hai chiều, đồng bộ phiên làm việc |

Streaming giúp duy trì một RPC trong khi trao đổi nhiều message, tránh phải mô hình hóa mọi phần dữ liệu thành một chuỗi request độc lập. Đổi lại, ứng dụng phải quản lý cancellation, deadline, backpressure, giới hạn thời lượng, reconnect và trạng thái stream.

### Payload nhị phân và chi phí serialization quan trọng

Protocol Buffers thường có biểu diễn nhị phân gọn và serialization hiệu quả hơn JSON trong một số kiểu dữ liệu và workload. Điều này có thể giảm kích thước payload hoặc CPU serialize/deserialize. Kết quả thực tế phụ thuộc cấu trúc message, tần suất gọi, kích thước dữ liệu, compression, mạng và triển khai. Cần đo trên workload đại diện thay vì ghi trong quyết định rằng gRPC “luôn nhanh hơn REST”.

### Cần HTTP/2 và các đặc tính RPC

gRPC sử dụng HTTP/2 cho framing, multiplexing và truyền message. Một channel có thể phục vụ nhiều RPC đồng thời trên kết nối HTTP/2, đồng thời hỗ trợ metadata, deadline và status của gRPC. Những đặc điểm này hữu ích cho giao tiếp nội bộ có tần suất cao, miễn là proxy và hạ tầng mạng được cấu hình đúng.

## 3. Khi gRPC không phải lựa chọn phù hợp

Một giao thức khác có thể phù hợp hơn nếu những yêu cầu chính của hệ thống nằm ngoài thế mạnh của gRPC:

- **API công khai cho trình duyệt:** trình duyệt không hỗ trợ đầy đủ giao thức gRPC native như client gRPC thông thường. Có thể cần gRPC-Web, proxy chuyển đổi hoặc HTTP/JSON gateway. Nếu client chính là web browser và API cần dễ truy cập, REST/JSON thường đơn giản hơn.
- **Tích hợp đối tác không kiểm soát được client:** đối tác có thể cần curl, SDK phổ biến, tài liệu OpenAPI và khả năng debug trực tiếp bằng HTTP/JSON. REST có thể giảm rào cản tích hợp.
- **Cần cache HTTP/CDN hoặc thao tác tài nguyên qua URL:** REST với semantics HTTP chuẩn, cache headers và URL tài nguyên thường phù hợp hơn cho nội dung có thể cache hoặc tải trực tiếp.
- **Giao tiếp bất đồng bộ, cần lưu bền và phát lại:** message broker/event streaming phù hợp hơn cho sự kiện cần tách rời thời gian sống của producer và consumer, lưu trữ, replay hoặc xử lý eventual consistency. gRPC streaming không tự cung cấp hàng đợi bền vững.
- **Hạ tầng chưa hỗ trợ HTTP/2 end-to-end:** nếu proxy, ingress hoặc firewall chỉ xử lý HTTP/1.1 hay không hỗ trợ trailer/streaming theo yêu cầu, việc triển khai gRPC có thể phát sinh nhiều lớp chuyển đổi và điểm lỗi.
- **Đội ngũ chưa thể vận hành schema và RPC:** nếu chưa có quy trình sinh mã, quản lý tương thích `.proto`, certificate, deadline và observability, chi phí chuyển đổi có thể lớn hơn lợi ích.

Không nhất thiết phải dùng một giao thức duy nhất cho toàn hệ thống. Một kiến trúc có thể dùng REST cho public API, gRPC cho các lời gọi nội bộ cần hợp đồng mạnh và message broker cho sự kiện bất đồng bộ. Điều quan trọng là xác định ranh giới và trách nhiệm của từng kiểu giao tiếp, tránh tạo nhiều lớp chuyển đổi không có lý do.

## 4. So sánh các lựa chọn

Bảng dưới đây dùng để định hướng thảo luận. Kết quả cuối cùng vẫn phụ thuộc client, hạ tầng và yêu cầu cụ thể của dự án.

| Tiêu chí | gRPC | REST/HTTP JSON | Messaging / Event streaming |
| --- | --- | --- | --- |
| Mô hình | RPC đồng bộ; hỗ trợ streaming | Tài nguyên và thao tác HTTP; thường request/response | Producer/consumer bất đồng bộ |
| Hợp đồng | `.proto`, sinh mã | OpenAPI/JSON Schema có thể dùng để mô tả và sinh mã | Schema sự kiện, registry hoặc hợp đồng message |
| Payload | Thường là Protobuf nhị phân | Thường là JSON dễ đọc | Phụ thuộc format, có thể Protobuf/JSON/Avro |
| Browser | Cần gRPC-Web hoặc gateway cho nhiều trường hợp | Hỗ trợ trực tiếp | Cần backend hoặc SDK phù hợp |
| Streaming | Unary và ba dạng streaming RPC | Có thể dùng SSE/WebSocket hoặc chunked transfer tùy nhu cầu | Consumer nhận message theo cơ chế broker |
| Cache HTTP | Không thuận tiện như REST resource | Hỗ trợ semantics cache HTTP phổ biến | Không phải mô hình cache HTTP |
| Lưu bền/replay | Không tự cung cấp | Không tự cung cấp | Có thể có tùy broker và cấu hình retention |
| Độ phức tạp vận hành | HTTP/2, schema, stub, status, stream | HTTP semantics, auth, API versioning | Broker, partition, offset, retry, dead-letter và schema |
| Phù hợp điển hình | Giao tiếp service-to-service có hợp đồng và/hoặc streaming | Public API, browser, tích hợp đơn giản | Sự kiện, xử lý nền, tách rời producer/consumer |

Đừng so sánh chỉ bằng benchmark serialization. Một API public có thể cần cache, khả năng gọi từ trình duyệt và tài liệu dễ tiếp cận; một pipeline sự kiện có thể cần replay; một RPC nội bộ có thể cần deadline ngắn và kiểu dữ liệu sinh mã. Những khác biệt đó thường quan trọng hơn vài microsecond trong một benchmark cô lập.

## 5. Ghi lại giới hạn và rủi ro của gRPC

Chọn gRPC đồng nghĩa chấp nhận các giới hạn sau và có kế hoạch xử lý tương ứng.

### Khả năng tương thích client và proxy

gRPC yêu cầu đường truyền hỗ trợ HTTP/2 và các đặc tính giao thức cần thiết. Một số proxy có thể terminate HTTP/2 rồi chuyển tiếp theo cách riêng; điều đó không có nghĩa mọi cấu hình đều hỗ trợ streaming hoặc trailer. Cần xác minh ingress, service mesh, load balancer, firewall, timeout idle connection và giới hạn kích thước message trong môi trường thật.

Client gRPC thường duy trì channel lâu dài. Load balancer phân phối kết nối TCP ở tầng L4 có thể phân phối channel thay vì từng RPC; một channel có nhiều RPC multiplexed có thể tạo tải không đều giữa các backend. Cần đánh giá load balancing ở tầng hiểu gRPC hoặc chính sách client-side phù hợp, đồng thời quan sát số RPC trên từng instance.

### Quản lý tương thích Protocol Buffers

Schema `.proto` là hợp đồng được chia sẻ, vì vậy thay đổi field cần tuân thủ quy tắc tương thích:

- Không thay đổi field number đã phát hành để dùng cho ý nghĩa khác.
- Không tái sử dụng field number hoặc tên field đã xóa; dùng `reserved` để đánh dấu vùng đã bỏ.
- Thêm field mới với field number mới và thiết kế default/presence phù hợp.
- Khi xóa field, xóa cả field name và number khỏi schema đang dùng, rồi reserve chúng.
- Không thay đổi kiểu dữ liệu một cách tùy tiện; một số thay đổi có thể gây lỗi parse hoặc thay đổi ý nghĩa dữ liệu dù code vẫn sinh được.
- Với enum, giữ giá trị số đã phát hành ổn định; cân nhắc giá trị `UNSPECIFIED = 0` và cách client cũ xử lý giá trị enum chưa biết.
- Kiểm tra tương thích bằng công cụ lint/breaking-change trong pipeline trước khi phát hành.

Ví dụ reserve field đã xóa:

```proto
message GetItemResponse {
  reserved 4, 7;
  reserved "legacy_code", "old_description";

  string item_id = 1;
  int64 available_quantity = 2;
  string version = 3;
}
```

Không phải mọi thay đổi đều tương thích trong mọi chiều. Hãy kiểm tra cả trường hợp client mới gọi server cũ và client cũ gọi server mới nếu các phiên bản có thể cùng tồn tại trong quá trình rolling deployment.

### Deadline, retry và trạng thái nghiệp vụ

Deadline cần được truyền và chọn theo ngân sách end-to-end. Nếu client không đặt deadline, lời gọi có thể tồn tại lâu hơn dự kiến. Deadline quá ngắn làm tăng lỗi giả; deadline quá dài giữ tài nguyên khi dependency đã chậm.

Retry cũng cần chính sách rõ ràng. Một status như `UNAVAILABLE` có thể phù hợp để thử lại trong một số tình huống, nhưng không chứng minh server chưa thực hiện thao tác. Với thao tác ghi, hãy dùng idempotency key hoặc thiết kế idempotent trước khi bật retry tự động. Phân biệt lỗi transport, lỗi deadline, lỗi xác thực và lỗi nghiệp vụ để client phản ứng đúng.

### Streaming và giới hạn tài nguyên

Stream lâu dài có thể giữ connection, memory, state và tài nguyên xử lý. Cần xác định giới hạn số stream đồng thời, kích thước message, tốc độ message, thời lượng stream, deadline và hành vi khi client hủy. Với stream có thể reconnect, thiết kế sequence number hoặc resume token nếu nghiệp vụ yêu cầu không mất dữ liệu. Không xem streaming RPC như một hàng đợi bền vững.

### Bảo mật và metadata

gRPC không tự bật bảo mật ứng dụng chỉ vì dùng Protobuf hoặc HTTP/2. Cần cấu hình TLS; cân nhắc mTLS cho service-to-service khi cần xác thực danh tính ở tầng kết nối; áp authentication và authorization theo phương thức; kiểm soát kích thước và nội dung metadata. Không đưa access token, dữ liệu cá nhân hoặc bí mật vào log, trace attribute hay metric label.

### Observability và vận hành

Log HTTP thông thường có thể không đủ để giải thích lỗi RPC. Cần thu thập full method name, gRPC status, latency, deadline, trace context và các tín hiệu streaming cần thiết. Metric label phải có cardinality được kiểm soát; không dùng request ID, user ID hoặc token làm nhãn metric. Dashboard cần thể hiện tỷ lệ lỗi và latency theo phương thức, số RPC đang hoạt động và phân bố tải giữa instance.

### Hiệu năng không tự động tốt hơn

Payload nhị phân và multiplexing có thể có lợi, nhưng bottleneck có thể nằm ở database, business logic, lock contention, network hop hoặc cách phân phối connection. Benchmark phải đo end-to-end trên dữ liệu và tải gần thực tế, bao gồm p50/p95/p99 latency, throughput, CPU, memory, kích thước payload, số connection và chi phí vận hành.

## 6. Quy trình ra quyết định có thể kiểm chứng

Một quy trình ngắn nhưng có bằng chứng giúp tránh chọn giao thức theo cảm tính:

1. **Mô tả use case:** xác định producer, consumer, dữ liệu, tần suất, kiểu RPC, thời gian sống và yêu cầu lỗi.
2. **Liệt kê ràng buộc:** browser, ngôn ngữ client, API public, cache, HTTP/2, gateway, compliance và năng lực vận hành.
3. **So sánh ít nhất các phương án phù hợp:** gRPC, REST/JSON và messaging nếu bài toán có thể bất đồng bộ.
4. **Đặt tiêu chí đo:** latency p95/p99, throughput, CPU, memory, payload size, tỷ lệ lỗi, thời gian phát triển client và chi phí vận hành.
5. **Làm proof of concept:** triển khai một luồng đại diện qua hạ tầng gần production; đo cả trường hợp lỗi, retry, rolling deployment và stream bị ngắt.
6. **Ghi quyết định và đánh đổi:** nêu phương án được chọn, lý do, phương án bị loại, rủi ro, biện pháp giảm thiểu và điều kiện xem xét lại.
7. **Định kỳ xem lại:** cập nhật khi xuất hiện client browser, đối tác mới, hạ tầng thay đổi, tải tăng hoặc yêu cầu độ tin cậy thay đổi.

Không cần tạo một bảng điểm phức tạp nếu một vài tiêu chí đã quyết định lựa chọn. Nhưng các tiêu chí quan trọng phải được viết rõ, ví dụ: “client đều là service nội bộ bằng Java/Go, cần streaming hai chiều, toàn bộ ingress hỗ trợ HTTP/2, và nhóm đã có pipeline kiểm tra tương thích Protobuf”. Những bằng chứng này có thể được kiểm tra lại sau này.

## 7. Ví dụ Architecture Decision Record (ADR)

ADR là tài liệu ngắn ghi lại bối cảnh, quyết định và hệ quả. Ví dụ sau minh họa cách ghi quyết định cho một hệ thống Spring gRPC nội bộ; các con số và điều kiện phải được thay bằng dữ liệu của dự án thực tế.

```markdown
# ADR-007: Dùng gRPC cho giao tiếp inventory nội bộ

## Trạng thái
Accepted

## Bối cảnh
- Inventory và Order là các service nội bộ.
- Client chủ yếu là Java và Go, được triển khai cùng nền tảng.
- Một số luồng cần server streaming để gửi cập nhật trạng thái.
- Public API cho browser được cung cấp qua API edge riêng.
- Ingress nội bộ hỗ trợ HTTP/2 và có dashboard theo dõi RPC.

## Quyết định
Dùng gRPC với Protocol Buffers cho các RPC đồng bộ giữa Inventory
và Order. Dùng unary cho truy vấn/cập nhật ngắn và server streaming
cho luồng cập nhật có thời lượng được giới hạn.

## Lý do
- Hợp đồng .proto là nguồn schema dùng chung cho client Java/Go.
- Generated stub giảm code ánh xạ và sai khác chữ ký phương thức.
- gRPC hỗ trợ deadline, status và streaming theo hợp đồng.
- Đường truyền nội bộ đã hỗ trợ HTTP/2.

## Phương án đã cân nhắc
- REST/JSON: dễ debug và phổ biến, nhưng cần thêm cơ chế streaming
  riêng cho use case cập nhật liên tục.
- Messaging: phù hợp event bất đồng bộ và replay, nhưng không thay
  thế được truy vấn đồng bộ cần response ngay.

## Giới hạn và rủi ro
- Browser không gọi trực tiếp gRPC native; public API tiếp tục dùng
  REST/JSON tại API edge.
- Phải quản lý tương thích schema và phiên bản generated code.
- Stream dài có thể giữ tài nguyên; cần deadline và giới hạn thời lượng.
- Load balancer phải phân phối RPC phù hợp với channel HTTP/2 lâu dài.

## Biện pháp giảm thiểu
- CI kiểm tra breaking change của .proto.
- Đặt deadline, message size limit và chính sách retry có kiểm soát.
- Dùng idempotency cho thao tác ghi có thể retry.
- Theo dõi latency, status, active calls và số stream trên từng instance.
- Kiểm thử rolling deployment và reconnect trước khi phát hành.

## Điều kiện xem xét lại
- Có client browser/đối tác cần API trực tiếp.
- Hạ tầng không còn hỗ trợ HTTP/2 theo yêu cầu.
- Use case chuyển thành event bất đồng bộ cần retention/replay.
- Đo đạc cho thấy chi phí vận hành lớn hơn lợi ích giao tiếp.
```

ADR cần ghi lý do thật của dự án, không sao chép ví dụ như một quyết định mặc định. Nếu quyết định chỉ dùng gRPC cho một ranh giới cụ thể, hãy ghi rõ service nào nằm trong phạm vi và những giao tiếp nào tiếp tục dùng giao thức khác.

## 8. Cách lượng hóa lựa chọn trong proof of concept

Khi còn phân vân, hãy chọn một luồng nghiệp vụ đại diện và triển khai hai phương án có cùng logic, cùng dependency và cùng điều kiện tải. Tránh benchmark chỉ đo serialization vì nó bỏ qua nhiều chi phí thực tế.

| Nhóm đo | Chỉ số gợi ý | Câu hỏi cần trả lời |
| --- | --- | --- |
| Hiệu năng | p50/p95/p99 latency, throughput | Giao thức có đáp ứng SLO ở tải mục tiêu không? |
| Tài nguyên | CPU, heap, allocation, network bytes | Chi phí mỗi request và chi phí khi tăng tải là bao nhiêu? |
| Độ tin cậy | status/error rate, timeout, retry, reconnect | Hệ thống phản ứng ra sao khi backend chậm hoặc kết nối bị ngắt? |
| Streaming | active streams, message rate, stream duration | Có kiểm soát được stream dài và tài nguyên không? |
| Phát triển | thời gian tạo client, thay đổi schema, debug | Đội ngũ có triển khai và hỗ trợ được không? |
| Vận hành | dashboard, trace coverage, rollout behavior | Có thể điều tra lỗi và triển khai an toàn không? |

Đo ở cùng điều kiện: cùng dữ liệu, số client, số backend, network topology, TLS, compression và giới hạn tài nguyên. Chạy đủ lâu để quan sát warm-up, connection reuse và biến động tải. Lưu cấu hình, phiên bản code và kết quả cùng ADR để người khác có thể lặp lại phép đo.

## 9. Checklist trước khi chốt lựa chọn

- [ ] Use case, client và ranh giới service được mô tả rõ.
- [ ] Đã xác định unary, streaming hoặc giao tiếp bất đồng bộ cần dùng.
- [ ] Đã đánh giá REST/JSON và messaging ở những nơi phù hợp.
- [ ] Client, gateway, proxy, load balancer và firewall hỗ trợ giao thức cần thiết.
- [ ] Có kế hoạch quản lý `.proto`, generated code và kiểm tra breaking change.
- [ ] Có chính sách deadline, cancellation, retry và idempotency.
- [ ] Có giới hạn message, stream và tài nguyên.
- [ ] Có TLS/authentication/authorization và quy tắc bảo vệ metadata.
- [ ] Có metrics, logs, traces và dashboard để vận hành.
- [ ] Có kết quả POC đại diện hoặc nêu rõ vì sao chưa cần POC.
- [ ] ADR ghi rõ lý do chọn, phương án đã cân nhắc, giới hạn, biện pháp giảm thiểu và điều kiện xem xét lại.

Chọn gRPC có trách nhiệm nghĩa là chọn nó cho đúng ranh giới giao tiếp, dựa trên yêu cầu và bằng chứng, đồng thời ghi rõ chi phí phải chấp nhận. Trong hệ sinh thái Spring, Protocol Buffers và generated stub tạo nền tảng hợp đồng mạnh cho client/server; deadline, status, interceptor, TLS, kiểm thử tích hợp và observability giúp biến lựa chọn đó thành một giải pháp có thể vận hành. ADR giữ lại bối cảnh và lý do để nhóm có thể đánh giá lại khi hệ thống phát triển.
