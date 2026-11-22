# Breaking change check trong CI

## 1. Vì sao cần kiểm tra breaking change?

Trong **Spring gRPC**, Protocol Buffers định nghĩa contract giữa client và server: package, service, RPC method, request/response message, field number, kiểu dữ liệu và enum. Nhiều client có thể được triển khai độc lập với server. Khi một thay đổi schema được merge mà không kiểm tra tương thích, client cũ có thể không gọi được server mới, hoặc message cũ bị diễn giải sai.

Breaking change check trong CI so sánh schema của nhánh đang thay đổi với một baseline đã chọn. Nếu thay đổi phá vỡ quy tắc tương thích, pipeline dừng trước khi schema được merge hoặc phát hành.

Mục tiêu không phải ngăn mọi thay đổi. Mục tiêu là phát hiện thay đổi nguy hiểm sớm, yêu cầu người phát triển chọn cách tiến hóa contract an toàn hoặc chủ động lập kế hoạch migration.

## 2. Phân biệt wire compatibility và source/API compatibility

Protobuf có nhiều lớp tương thích:

- **Wire compatibility:** bytes được serialize theo schema mới có thể được parser theo schema cũ hoặc ngược lại mà không đổi ý nghĩa dữ liệu đã có.
- **JSON compatibility:** tên field, enum và quy tắc JSON mapping vẫn tương thích với client dùng ProtoJSON hoặc gateway.
- **Generated source compatibility:** code Java được sinh ra vẫn giữ API mà source client/server đang dùng.
- **Behavioral compatibility:** service vẫn giữ semantics nghiệp vụ, quyền truy cập, validation và ý nghĩa response.

Một thay đổi có thể wire-compatible nhưng vẫn phá source code hoặc behavior. Ví dụ thêm enum value thường không làm hỏng wire format, nhưng code Java dùng switch exhaustive hoặc client giả định chỉ có một tập enum cố định có thể cần cập nhật.

Vì vậy, CI cần ít nhất hai lớp kiểm tra: schema breaking check và build/test trên generated code. Với API quan trọng, bổ sung compatibility test giữa client/server ở các phiên bản khác nhau.

## 3. Các thay đổi Protobuf thường gây breaking change

| Thay đổi | Rủi ro | Cách xử lý an toàn |
| --- | --- | --- |
| Đổi field number | Parser cũ đọc sai hoặc bỏ qua dữ liệu | Không đổi field number đã phát hành |
| Dùng lại field number đã xóa | Dữ liệu cũ có thể bị hiểu thành field mới | Reserve cả number và name đã bỏ |
| Đổi wire type | Parser cũ không giải mã đúng | Thêm field mới, migrate rồi bỏ field cũ |
| Đổi package của service | Full RPC method path thay đổi | Giữ package; nếu cần API mới, tạo service/version mới |
| Xóa hoặc rename RPC | Client cũ gọi method không còn tồn tại | Giữ method cũ trong giai đoạn migration |
| Đổi request/response type | Generated API và wire contract có thể thay đổi | Tạo method mới hoặc message mới có kế hoạch |
| Đổi unary thành streaming hoặc ngược lại | RPC shape và generated stub thay đổi | Tạo RPC mới |
| Đổi tên field | Có thể phá generated Java API và ProtoJSON name | Giữ tên hoặc tạo field mới có migration |
| Đổi Java package option | Generated Java package thay đổi | Chỉ đổi khi chấp nhận source migration |
| Đổi semantics của field mà không đổi schema | Client hiểu dữ liệu khác trước | Version hóa contract hoặc thêm field với semantics rõ |

### 3.1. Field number là định danh wire

Field number được mã hóa trong Protobuf tag. Không đổi number của field đã được phát hành:

~~~proto
message GetOrderRequest {
  string order_id = 1;
}
~~~

Nếu đổi order_id từ number 1 sang 2, client cũ gửi field 1 và server mới chỉ đọc field 2 sẽ không nhận được giá trị như mong muốn.

Khi bỏ field, reserve number và name:

~~~proto
message GetOrderRequest {
  reserved 1;
  reserved "order_id";

  string resource_id = 2;
}
~~~

Ví dụ này minh họa việc bỏ field order_id cũ và thêm resource_id với semantics mới. Number 2 phải chưa từng được dùng. Nếu mục tiêu chỉ là đổi number của cùng một field order_id, không làm vậy; hãy giữ field cũ ở number 1 hoặc thiết kế migration có field mới và semantics rõ ràng.

### 3.2. Đổi type có thể nguy hiểm dù wire type giống nhau

Một số Protobuf type dùng cùng wire type nhưng vẫn có semantics khác. Ví dụ int32 và sint32 đều dùng varint, nhưng sint32 dùng ZigZag encoding. Đổi giữa chúng có thể làm giá trị cũ bị diễn giải sai.

Không kết luận tương thích chỉ vì hai type có cùng wire type. Kiểm tra encoding, miền giá trị, signedness, default/presence và cách generated code biểu diễn dữ liệu.

### 3.3. Enum và unknown value

Không đổi numeric value của enum đã phát hành. Khi thêm enum value, wire format thường vẫn tương thích, nhưng client cũ có thể không có nhánh xử lý cho giá trị mới. Code Java, ProtoJSON gateway và database mapping cần có cách xử lý unknown value.

~~~proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_CONFIRMED = 2;
  ORDER_STATE_CANCELLED = 3;
}
~~~

Giữ giá trị 0 làm unspecified/default theo convention của API. Khi xóa enum value, reserve cả số và tên để tránh tái sử dụng.

## 4. Thay đổi service và RPC method

Địa chỉ RPC gRPC được hình thành từ package, service và method, ví dụ:

~~~text
/orders.v1.OrderService/GetOrder
~~~

Đổi package từ orders.v1 sang orders.v2 hoặc đổi tên OrderService/GetOrder làm thay đổi full method name. Client cũ tiếp tục gọi path cũ và có thể nhận UNIMPLEMENTED.

Khi cần API mới có semantics không tương thích:

- Tạo package/version mới như orders.v2.
- Hoặc thêm RPC mới trong service hiện tại nếu contract và policy versioning cho phép.
- Duy trì RPC cũ trong thời gian client migration.
- Theo dõi usage theo method để biết khi nào có thể ngừng method cũ.

Không thay đổi RPC unary thành server-streaming chỉ vì muốn gửi thêm kết quả. Generated stub, flow control, terminal semantics và client code đều khác nhau. Tạo method mới với response contract phù hợp.

## 5. Cấu hình Buf để kiểm tra schema

Buf cung cấp lint và breaking change detection cho Protobuf. Ví dụ cấu hình workspace Buf v2:

~~~yaml
version: v2

modules:
  - path: proto

lint:
  use:
    - STANDARD

breaking:
  use:
    - FILE
~~~

Với cấu hình trên:

- Module schema nằm trong thư mục proto.
- Lint kiểm tra convention và lỗi schema phổ biến.
- Breaking check dùng rule set FILE để phát hiện thay đổi không tương thích theo phạm vi file.

Rule set cần chọn theo chính sách API. FILE thường nghiêm ngặt hơn WIRE và có thể phát hiện cả thay đổi source-level. Nếu tổ chức chỉ muốn bảo đảm binary wire compatibility, có thể chọn WIRE; nếu client sử dụng ProtoJSON, cân nhắc WIRE_JSON hoặc rule set nghiêm ngặt hơn. Đọc tài liệu Buf của phiên bản đang pin để hiểu chính xác phạm vi từng rule.

Không chọn rule set chỉ để pipeline xanh. Quyết định phải dựa trên loại client thực tế: Java gRPC stub, gateway ProtoJSON, mobile app hoặc consumer được sinh code từ schema.

## 6. Chạy breaking check trên máy phát triển

Sau khi cài và pin phiên bản Buf trong toolchain dự án, chạy:

~~~bash
buf lint
buf breaking --against '.git#branch=main'
~~~

Lệnh thứ hai so sánh schema hiện tại với schema ở branch main. Khi chạy trong CI, checkout phải có đủ Git history/ref cần thiết để Buf đọc baseline. Nếu dùng shallow checkout chỉ có một commit, cần fetch branch baseline trước khi chạy.

Đối với repository có nhiều module, chạy lệnh ở workspace root và xác định rõ module nào được so sánh. Không để thay đổi schema của một module vô tình được so với baseline của module khác.

Trong dự án dùng Buf Schema Registry, baseline có thể là một commit/schema version đã publish thay vì Git branch. Điều quan trọng là baseline phải đại diện cho contract đã được phát hành hoặc được nhánh đích chấp nhận.

## 7. Tích hợp vào CI pipeline

Một pipeline gợi ý:

~~~mermaid
flowchart TD
    A[Pull request] --> B[Checkout with baseline history]
    B --> C[Pin and install Buf]
    C --> D[buf lint]
    D --> E[buf breaking against target baseline]
    E --> F[Generate Java sources]
    F --> G[Check generated diff]
    G --> H[Compile and unit tests]
    H --> I[Client/server compatibility tests]
    I --> J[Merge allowed]
~~~

Breaking check nên chạy sớm, trước các bước build/test tốn thời gian. Tuy vậy, pass breaking check không thay thế compile, generated code check hoặc integration test.

Ví dụ GitHub Actions ở mức minh họa:

~~~yaml
name: protobuf-contract

on:
  pull_request:
    paths:
      - "proto/**"
      - "buf.yaml"
      - "buf.lock"
      - "build.gradle"
      - ".github/workflows/protobuf-contract.yml"

jobs:
  contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install pinned Buf CLI
        run: |
          # Install the Buf version pinned by this repository.
          buf --version

      - name: Lint Protobuf
        run: buf lint

      - name: Check breaking changes
        run: buf breaking --against '.git#branch=main'

      - name: Build and test
        run: ./gradlew test
~~~

Đây là skeleton workflow: bước cài Buf phải được thay bằng action hoặc installation script đã pin version trong repository. Không dùng version mới nhất trôi nổi trong CI vì cùng một schema có thể nhận kết quả khác khi rule set/tool version thay đổi.

Nếu pull request nhắm vào release branch khác main, baseline phải là target branch thực tế. Pipeline cần lấy đúng base ref thay vì luôn so sánh với main.

## 8. Generated Java code cũng cần được kiểm tra

Schema pass không bảo đảm code Java compile. Các thay đổi như java_package, java_multiple_files, outer class name hoặc plugin option có thể thay đổi generated API dù wire format không đổi.

CI nên:

1. Sinh Java sources từ schema bằng đúng protoc và plugin version đã pin.
2. Nếu generated code được commit, kiểm tra working tree không có diff ngoài dự kiến sau generation.
3. Compile server và client module.
4. Chạy unit test cho mapper, enum handling và validation.
5. Kiểm tra code sử dụng field mới có xử lý default/presence đúng.

Không chỉnh sửa generated Java source bằng tay. Sửa file .proto hoặc generator configuration rồi generate lại.

## 9. Compatibility test giữa client và server

Breaking check là kiểm tra cấu trúc schema. Compatibility test kiểm tra ứng dụng thực tế có giao tiếp được giữa các phiên bản hay không.

Một ma trận cơ bản:

| Client | Server | Câu hỏi |
| --- | --- | --- |
| Client cũ | Server mới | Server mới còn phục vụ client đang triển khai không? |
| Client mới | Server cũ | Client mới có gửi field/method mà server cũ không hiểu theo cách gây lỗi không? |
| Client mới | Server mới | Phiên bản cùng release có hoạt động không? |
| Client cũ | Server cũ | Baseline trước thay đổi vẫn chạy như cũ không? |

Không phải mọi tổ hợp đều phải được hỗ trợ vô thời hạn. Chính sách cần xác định rõ thời gian tương thích, ví dụ server mới hỗ trợ client cũ trong ít nhất hai chu kỳ release.

Với Protobuf, unknown field thường được parser bỏ qua hoặc giữ tùy API/runtime và cách message được xử lý. Do đó thêm field optional thường có thể tương thích wire, nhưng application code không được giả định server cũ hiểu field mới.

## 10. Thêm field an toàn theo chiến lược expand-contract

Khi cần thêm thông tin vào request:

~~~proto
message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
}
~~~

Trước khi phát hành field mới:

1. Chọn field number chưa từng dùng và không nằm trong reserved range.
2. Chọn semantics rõ ràng; xác định optional/default behavior.
3. Triển khai server chấp nhận cả request cũ không có field và request mới có field.
4. Phát hành server tương thích trước nếu client mới sẽ gửi field.
5. Phát hành client mới sau khi server hỗ trợ.
6. Chỉ bỏ field cũ sau khi mọi client đã migration và policy cho phép.

Với field có presence quan trọng, dùng optional hoặc message wrapper phù hợp thay vì dựa vào default value. Phân biệt “không gửi” với “gửi giá trị mặc định” nếu nghiệp vụ cần hai trạng thái khác nhau.

## 11. Khi nào breaking check không đủ?

Buf không thể hiểu toàn bộ semantics nghiệp vụ. Các thay đổi sau có thể không bị phát hiện là schema breaking nhưng vẫn làm client hỏng:

- Giữ nguyên field nhưng đổi đơn vị từ milliseconds sang seconds.
- Giữ enum value nhưng đổi ý nghĩa nghiệp vụ.
- Bắt đầu yêu cầu một field trước đây optional.
- Siết validation khiến request hợp lệ trước đây bị INVALID_ARGUMENT.
- Đổi authorization policy hoặc tenant scope.
- Thay đổi ordering, consistency hoặc side effect của method.
- Giảm deadline nội bộ khiến RPC thường xuyên DEADLINE_EXCEEDED.

Những thay đổi này cần contract test, consumer-driven test, integration test hoặc behavioral test. Với API quan trọng, lưu test case đại diện cho client đang triển khai và chạy chúng với server candidate.

## 12. Xử lý breaking change có chủ đích

Đôi khi breaking change là cần thiết, ví dụ thay đổi model dữ liệu hoặc bỏ API không còn phù hợp. Không nên lách CI bằng cách tắt rule hoặc xóa baseline.

Quy trình có kiểm soát:

1. Ghi rõ lý do và client/consumer bị ảnh hưởng.
2. Tạo API version mới hoặc method mới.
3. Triển khai server hỗ trợ cả API cũ và mới.
4. Migration client theo nhóm, theo dõi usage và error rate của method cũ.
5. Công bố thời điểm deprecation và sunset.
6. Chỉ xóa API cũ khi usage đã về 0 hoặc đã được owner chấp thuận.
7. Giữ breaking check bật; nếu có exception, yêu cầu review của API owner và ghi nhận phạm vi/expiry.

Một breaking change được phê duyệt vẫn cần rollout plan và compatibility evidence. Approval không tự làm client cũ tương thích.

## 13. Cách đọc kết quả Buf breaking

Khi CI báo breaking change:

- Xem file, message, field hoặc RPC mà rule chỉ ra.
- Xác định đó là wire, JSON hay source-level incompatibility theo rule set.
- Kiểm tra baseline đang so sánh có đúng branch/schema release không.
- Nếu thay đổi không chủ ý, khôi phục contract cũ.
- Nếu cần thay đổi, thêm field/method/version mới và triển khai expand-contract.
- Nếu cho rằng rule không phù hợp, yêu cầu API owner xem xét rule set; không xóa rule chỉ để pipeline xanh.

Không xử lý bằng cách cập nhật baseline sang chính schema mới trong cùng pull request. Làm vậy sẽ khiến phép so sánh mất ý nghĩa và có thể che breaking change trước khi nó được review.

## 14. Những lỗi thường gặp

1. **Chỉ compile generated code.** Code compile không chứng minh client cũ tương thích với server mới.
2. **Chỉ chạy Buf lint.** Lint kiểm tra style/schema quality, không thay thế breaking check.
3. **Đổi field number hoặc tái sử dụng number.** Có thể làm dữ liệu cũ bị diễn giải sai.
4. **Chỉ kiểm tra wire compatibility.** Java source hoặc ProtoJSON client vẫn có thể bị ảnh hưởng.
5. **Không pin Buf/protoc/plugin version.** Kết quả CI và generated code có thể thay đổi ngoài ý muốn.
6. **So sánh sai baseline.** Pull request nhắm release branch nhưng lại so với main.
7. **Không fetch Git history trong CI.** Breaking command không truy cập được branch baseline.
8. **Cho rằng thêm enum value luôn an toàn.** Client cũ có thể không xử lý unknown value.
9. **Không test behavior.** Schema không đổi nhưng semantics hoặc validation vẫn có thể phá client.
10. **Tắt breaking check để merge.** Mất lớp bảo vệ quan trọng cho contract đã phát hành.

## 15. Bài tập vận dụng

Với contract orders.v1.OrderService:

1. Cấu hình Buf v2 cho thư mục proto và chọn breaking rule set phù hợp với Java gRPC client cùng ProtoJSON gateway.
2. Tạo baseline schema trên branch main hoặc release tag.
3. Thử thêm field optional với number mới và xác minh CI chấp nhận.
4. Thử đổi field number, xóa RPC và đổi package; xác minh CI từ chối.
5. Thử xóa field rồi reserve cả number và name; xác minh rule set và review policy cho kết quả mong muốn.
6. Thử thêm enum value và viết test chứng minh client cũ xử lý unknown value an toàn.
7. Generate Java code bằng toolchain đã pin, kiểm tra diff và compile client/server.
8. Chạy compatibility test client cũ với server mới.
9. Viết migration plan cho một breaking change có chủ đích và giữ CI gate hoạt động.

**Tiêu chí hoàn thành:** người học cấu hình được Buf breaking check trong CI, chọn baseline đúng, phân biệt wire/JSON/source/behavioral compatibility, nhận diện thay đổi nguy hiểm trong Protobuf/gRPC, và thiết kế được migration có kiểm chứng thay vì bỏ qua gate.

### Tài liệu tham khảo

- [Buf Breaking](https://buf.build/docs/breaking/): phát hiện thay đổi không tương thích trong Protobuf schema.
- [Buf Configuration](https://buf.build/docs/configuration/v2/buf-yaml/): cấu hình module, lint và breaking rule set.
- [Buf CLI Reference](https://buf.build/docs/reference/cli/buf/breaking/): lệnh breaking và baseline input.
- [Protocol Buffers Editions and Language Guide](https://protobuf.dev/programming-guides/proto3/): field number, presence, enum và schema evolution.
- [Protocol Buffers Best Practices](https://protobuf.dev/best-practices/dos-donts/): không đổi/reuse field number và cách reserve field.
- [gRPC Documentation](https://grpc.io/docs/): service definition, generated code và RPC contract.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
