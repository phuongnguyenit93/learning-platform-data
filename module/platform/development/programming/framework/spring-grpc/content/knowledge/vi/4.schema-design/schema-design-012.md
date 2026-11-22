# Kiểm tra schema bằng lint và breaking change check

Một file Protocol Buffers biên dịch thành công chưa có nghĩa hợp đồng gRPC an toàn để phát hành. Compiler chủ yếu xác nhận cú pháp và kiểu; nó không tự cảnh báo mọi thay đổi có thể làm client cũ không gọi được service, parse sai dữ liệu hoặc hiểu khác ý nghĩa field. Với **Spring gRPC**, nên đưa hai bước kiểm tra vào quy trình phát triển schema: **lint** để giữ quy ước và phát hiện cấu trúc đáng ngờ, **breaking change check** để so sánh schema đang sửa với một phiên bản đã tồn tại.

Bài này tập trung vào cách cấu hình và vận hành hai kiểm tra bằng **Buf**, chọn baseline Git phù hợp, đọc kết quả và đưa chúng vào CI. Các ví dụ dùng protobuf package shop.catalog.v1; nguyên tắc áp dụng tương tự cho request/response unary và message trong streaming RPC.

## 1. Lint và breaking change check giải quyết hai vấn đề khác nhau

| Kiểm tra | Câu hỏi | Dữ liệu cần có | Ví dụ phát hiện |
| --- | --- | --- | --- |
| **Lint** | Schema hiện tại có tuân theo quy ước và cấu trúc hợp lý không? | File .proto đang có | Tên enum không theo suffix, thiếu giá trị zero UNSPECIFIED, import không cần thiết hoặc cách đặt tên không nhất quán |
| **Breaking change check** | Schema hiện tại có phá hợp đồng so với phiên bản trước không? | Schema hiện tại và baseline cũ | Đổi field number, xóa field đã phát hành, đổi kiểu hoặc đổi tên service làm thay đổi RPC path |

Lint thường chạy ngay khi lập trình hoặc tạo pull request. Breaking check cần một **mốc so sánh** như nhánh main hoặc tag phát hành. Nếu không có baseline, công cụ không thể biết một field vừa bị xóa đã từng được client sử dụng hay chưa.

Hai bước bổ sung cho nhau:

- Một schema có thể lint sạch nhưng vẫn breaking vì đổi package hoặc field number.
- Một thay đổi tương thích wire vẫn có thể không đạt lint vì vi phạm quy ước tên hoặc enum zero.
- Cả hai đều không thay thế kiểm thử generated Java, behavior của server, authorization, deadline hay tính đúng đắn nghiệp vụ.

## 2. Cấu hình Buf cho module protobuf

Giả sử source nằm trong thư mục proto của dự án Spring Boot. Đặt file buf.yaml tại thư mục gốc repository để Buf và Git cùng dùng một root:

```yaml
version: v2

modules:
  - path: proto

lint:
  use:
    - STANDARD

breaking:
  use:
    - FILE
```

Giải thích lựa chọn:

- version v2 dùng định dạng cấu hình Buf v2.
- modules xác định thư mục chứa các file .proto; ở ví dụ này, buf.yaml nằm ngay trong proto nên module path là dấu chấm.
- STANDARD bật bộ quy tắc lint tiêu chuẩn, giúp tên, package, import và cách khai báo nhất quán.
- FILE chọn chính sách breaking nghiêm ngặt theo phạm vi file/API sinh ra. Với public contract, đây là điểm bắt đầu an toàn; nhóm có thể chọn category khác nếu đã hiểu rõ mức bảo vệ cần thiết.

Nếu dự án dùng import từ module bên ngoài, khai báo dependency trong deps của cấu hình Buf v2 và chạy buf dep update tại thư mục gốc để tạo/cập nhật buf.lock. Không sao chép các file .proto phụ thuộc vào source của mình chỉ để lint được; hãy quản lý dependency theo phiên bản.

### Chọn breaking category theo phạm vi tương thích

Buf có các category để chọn mức kiểm tra. Cần thống nhất chính sách trong nhóm thay vì tùy tiện giảm mức kiểm tra khi có lỗi:

| Category | Phạm vi khái quát | Khi cân nhắc |
| --- | --- | --- |
| FILE | Mức nghiêm ngặt, bảo vệ tương thích ở phạm vi file và API sinh ra | Public API cần kiểm soát thay đổi source/descriptor chặt |
| PACKAGE | Kiểm tra theo phạm vi package, ít ràng buộc hơn ở một số thay đổi cấp file | Schema được quản lý theo package và có quy ước tổ chức file rõ |
| WIRE_JSON | Tập trung vào tương thích protobuf wire và JSON | API có cả gRPC binary và ProtoJSON/JSON gateway |
| WIRE | Tập trung vào tương thích protobuf binary trên wire | Chỉ dùng khi hợp đồng thực sự không có consumer JSON và đã chấp nhận phạm vi hẹp hơn |

Không nên chọn WIRE chỉ để làm CI xanh nếu consumer có dùng ProtoJSON, HTTP transcoding hoặc dữ liệu enum/field được trao đổi bằng JSON. Với public contract, dùng category nghiêm ngặt phù hợp thường dễ bảo trì hơn việc thêm ngoại lệ không có thời hạn.

## 3. Chạy lint và breaking check

Chạy lệnh tại thư mục gốc repository, nơi đặt buf.yaml:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

buf lint phân tích schema hiện tại theo cấu hình. buf breaking so sánh schema làm việc với schema ở nhánh main; khi mở pull request, nhánh baseline nên là nhánh đích mà thay đổi sẽ hợp nhất vào.

Khi phát hành một phiên bản chính thức, có thể so với tag:

```bash
buf breaking --against '.git#tag=v1.4.0'
```

Baseline phải đại diện cho schema đã được chấp nhận và có consumer. Nếu so nhầm với nhánh đã chứa chính thay đổi đang kiểm tra, công cụ có thể không phát hiện breaking change. Nếu repository dùng shallow clone, CI cần lấy đủ lịch sử Git để Buf truy cập được nhánh/tag baseline.

### Lint không phải formatter

Lint báo vi phạm quy tắc; nó không đồng nghĩa với việc mọi thay đổi đều có thể tự động sửa. Khi một quy tắc yêu cầu đổi tên field hoặc package, hãy đánh giá tác động API trước khi chỉnh. Không đổi field number hay rename public symbol chỉ để làm lint sạch mà không có kế hoạch tương thích.

## 4. Đọc lỗi breaking check qua ví dụ

Giả sử baseline có:

```proto
syntax = "proto3";

package shop.catalog.v1;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
}
```

Một thay đổi như sau có thể gây breaking:

```proto
package shop.catalog.v1;

service CatalogService {
  rpc FetchProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 5;
}
```

Có hai vấn đề độc lập:

1. Đổi tên RPC từ GetProduct sang FetchProduct làm thay đổi full method path. Client stub cũ vẫn gọi /shop.catalog.v1.CatalogService/GetProduct; server chỉ đăng ký method mới có thể trả UNIMPLEMENTED.
2. Đổi field number của product_id từ 1 sang 5 làm payload cũ không còn được diễn giải như trước. Giữ tên field không giữ được wire identity.

Một số thay đổi khác cần kiểm tra:

| Thay đổi | Vì sao cần chú ý | Hướng xử lý thường gặp |
| --- | --- | --- |
| Xóa field đã phát hành | Client cũ có thể vẫn gửi hoặc đọc field | Giữ field deprecated trong giai đoạn chuyển; khi xóa thì reserve cả số và tên |
| Đổi kiểu field | Có thể đổi wire type hoặc ngữ nghĩa dữ liệu | Thêm field mới hoặc tạo message/API version mới |
| Đổi protobuf package | Đổi full message/service name và RPC path | Duy trì v1 và công bố package v2 |
| Đổi tên service/method | Client gọi đường dẫn cũ không còn khớp | Đăng ký service cũ song song trong migration |
| Xóa enum value hoặc tái sử dụng số | Giá trị cũ có thể bị hiểu thành trạng thái khác | Reserve số và tên đã phát hành |
| Thêm enum value | Client cũ có thể không hiểu giá trị mới | Kiểm tra nhánh UNRECOGNIZED và hành vi fallback |

Khi Buf báo rule và vị trí cụ thể, hãy xem đó là bằng chứng về thay đổi schema so với baseline. Đọc tên rule, file, message/field bị ảnh hưởng và quyết định sửa schema hay chủ động chuyển sang version mới. Không xóa rule hoặc hạ category chỉ để bỏ qua cảnh báo.

## 5. Những breaking change mà schema checker không thể hiểu thay bạn

Breaking check dựa trên descriptor/schema; nó không biết toàn bộ ý nghĩa nghiệp vụ. Ví dụ các thay đổi sau có thể không bị nhận diện là breaking ở tầng wire:

- price_minor_units trước đây là tiền đồng, nay được diễn giải thành xu nhưng vẫn giữ cùng kiểu và field number.
- Server bắt đầu yêu cầu locale dù field mới có thể vắng mặt trong request cũ.
- false trước đây có nghĩa tắt tính năng, nay được hiểu là chưa cấu hình.
- Một query trước đây trả dữ liệu nhất quán mạnh, nay đọc projection bất đồng bộ mà không công bố thay đổi.
- Server thêm quyền lọc mới nhưng vô tình làm lộ sản phẩm ngoài phạm vi caller.

Do đó, review phải kết hợp:

1. Lint và breaking check tự động.
2. Review semantics của request, response, status và field presence.
3. Biên dịch mã Java sinh ra và các module đang sử dụng generated classes.
4. Test client cũ với server mới và client mới với server cũ khi cần tương thích nhiều phiên bản.
5. Test tích hợp cho validation, authorization, deadline, retry và streaming nếu method có dùng.

Buf không thay thế protoc/plugin build, compile Java hoặc integration test. Một schema qua breaking check vẫn có thể khiến code Java không biên dịch sau khi đổi java_package, hoặc khiến client xử lý sai một giá trị mặc định.

## 6. Đưa kiểm tra vào CI

Trong pull request, CI cần lấy đầy đủ Git history, cài phiên bản Buf đã được nhóm chốt và chạy hai lệnh tại thư mục module protobuf. Ví dụ job shell tối giản:

```yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4
    with:
      fetch-depth: 0

  # Cài Buf bằng action/toolchain đã được dự án phê duyệt trước bước này.

  - name: Lint protobuf
    run: buf lint

  - name: Check breaking changes against main
    run: buf breaking --against '.git#branch=main'
```

Đây là phần steps minh họa; workflow thật cần có bước cài Buf và bảo đảm ref main tồn tại trong checkout. Vì buf.yaml nằm ở repository root và khai báo module path proto, các lệnh được chạy tại root. Với pull request từ fork hoặc CI không có quyền fetch nhánh đích, hãy cấu hình checkout/fetch baseline phù hợp thay vì bỏ qua breaking check.

### Khi CI báo lỗi

Xử lý theo thứ tự:

1. Xác nhận Buf đang đọc đúng module và đúng buf.yaml.
2. Xác nhận baseline là nhánh/tag trước thay đổi, không phải snapshot đã cập nhật.
3. Với lint, sửa schema theo quy ước nếu không làm thay đổi hợp đồng ngoài ý muốn.
4. Với breaking, xác định consumer nào bị ảnh hưởng; giữ tương thích hoặc tạo v2/endpoint mới.
5. Nếu tổ chức cho phép ngoại lệ, ghi rõ rule, lý do, phạm vi và thời hạn; không bỏ qua toàn bộ category.

Một pull request chỉ nên được thông qua khi thay đổi được hiểu và có kế hoạch migration, không phải vì cảnh báo đã bị che đi.

## 7. Quy trình review schema cho Spring gRPC

Một thay đổi .proto có thể theo quy trình ngắn:

1. **Sửa schema:** cấp field number mới, giữ tag cũ và cập nhật message/service theo semantics đã thống nhất.
2. **Chạy buf lint:** xử lý quy tắc đặt tên, package, enum và import.
3. **Chạy buf breaking:** so với nhánh đích hoặc tag phát hành.
4. **Sinh mã và compile Java:** xác minh generated class, stub, import và Spring gRPC endpoint vẫn tương thích với source.
5. **Chạy test contract/integration:** kiểm tra request cũ, response mới, gRPC status và hành vi nghiệp vụ.
6. **Review rollout:** nếu có client/server nhiều phiên bản, xác định thứ tự server-first, feature flag và thời điểm ngừng v1.

Với streaming RPC, kiểm tra schema của từng message trong luồng và cả semantics khi thêm field/event mới. Một thay đổi không phá wire vẫn có thể khiến consumer cũ không hiểu event hoặc xử lý sai thứ tự. Lint và breaking check không thay thế test hủy stream, flow control hay consumer xử lý unknown event.

## 8. Checklist trước khi merge

- [ ] Buf được cố định phiên bản trong toolchain của dự án.
- [ ] buf.yaml xác định đúng module, lint category và breaking category.
- [ ] buf lint chạy thành công trên toàn bộ schema liên quan.
- [ ] buf breaking so với baseline đúng (nhánh đích hoặc tag phát hành).
- [ ] Field number và enum number đã phát hành không bị đổi hoặc tái sử dụng.
- [ ] Field/enum value đã xóa được reserve cả số và tên.
- [ ] Đổi package/service/method đã có kế hoạch duy trì RPC path cũ hoặc version mới.
- [ ] Các thay đổi semantics không thể được phát hiện bằng descriptor đã được review thủ công.
- [ ] Generated Java compile và integration tests chạy thành công.
- [ ] Ngoại lệ breaking rule (nếu có) được giải thích, giới hạn và có thời hạn.

**Tự kiểm tra**

**Câu 1.** buf lint thành công có chứng minh schema không phá client cũ không?

*Đáp án:* Không. Lint kiểm tra quy ước và cấu trúc của schema hiện tại. Cần buf breaking so với baseline để phát hiện thay đổi không tương thích.

**Câu 2.** Vì sao buf breaking cần --against?

*Đáp án:* Công cụ cần schema cũ làm mốc so sánh. Không có baseline thì không thể xác định field, enum, package hoặc RPC đã thay đổi so với hợp đồng nào.

**Câu 3.** Đổi tên RPC nhưng giữ nguyên request/response có thể phá client không?

*Đáp án:* Có. Full method path thay đổi theo package, service và method name; client cũ vẫn gọi path cũ.

**Câu 4.** Buf breaking pass có bảo đảm thay đổi semantics không gây lỗi nghiệp vụ không?

*Đáp án:* Không. Descriptor không thể biết price_minor_units đã đổi đơn vị hoặc server đã thay đổi quy tắc validation. Cần review semantics và integration test.

**Câu 5.** Khi nào nên dùng tag phát hành làm baseline thay vì nhánh main?

*Đáp án:* Khi muốn xác nhận một schema vẫn tương thích với hợp đồng của một release cụ thể, chẳng hạn trước khi phát hành major/minor mới hoặc kiểm tra nhiều nhánh hỗ trợ. Baseline phải là phiên bản đã được chấp nhận và có ý nghĩa với consumer.

Lint giữ schema nhất quán; breaking check bảo vệ hợp đồng trước những thay đổi cấu trúc không tương thích. Đặt cả hai trong CI, chọn baseline đúng và vẫn kiểm tra generated Java cùng hành vi nghiệp vụ sẽ giúp nhóm Spring gRPC phát hiện rủi ro trước khi client đang chạy gặp lỗi.
