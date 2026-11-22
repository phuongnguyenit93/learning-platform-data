# Khác biệt generated API giữa các phiên bản trong Spring gRPC

Trong **Spring gRPC**, cùng một hợp đồng Protocol Buffers có thể tạo ra Java API khác nhau khi thay đổi schema, tùy chọn sinh mã hoặc phiên bản `protoc`/`protoc-gen-grpc-java`. Khác biệt có thể chỉ là annotation và cách trình bày source, nhưng cũng có thể làm mã client/server không biên dịch, bytecode cũ không liên kết được hoặc RPC không còn gọi đúng endpoint.

Để nâng cấp an toàn, cần phân biệt **API Java được sinh**, **wire contract protobuf/gRPC** và **runtime thực thi**. Bài này tập trung vào cách nhận diện khác biệt generated API giữa các phiên bản, đánh giá mức độ tương thích và kiểm thử migration trước khi phát hành.

## 1. Generated API thay đổi từ những nguồn nào?

Generated API không chỉ phụ thuộc nội dung message. Nó được tạo bởi tổ hợp:

- Schema `.proto`: package, message, field, enum, service, RPC và kiểu streaming.
- Java options: `java_package`, `java_multiple_files`, `java_outer_classname`.
- Generator: phiên bản `protoc` và các tùy chọn Java generator.
- gRPC plugin: phiên bản `protoc-gen-grpc-java` và cấu hình plugin.
- Runtime dependencies: `protobuf-java`, `grpc-api`, `grpc-stub`, `grpc-protobuf` và transport.
- Build configuration: proto roots, import graph, source sets và dependency resolution.

Có hai tình huống cần tách biệt:

1. **Schema không đổi, generator đổi:** output Java có thể thay đổi do generator cập nhật API, annotation, import hoặc cách triển khai.
2. **Schema đổi, generator giữ nguyên:** output thay đổi vì hợp đồng đã đổi; đây có thể là thay đổi có chủ đích trong API.

Khi cả schema và generator cùng đổi trong một lần nâng cấp, rất khó biết diff nào do nguyên nhân nào. Hãy tạo baseline và thay đổi từng nhóm riêng khi có thể.

## 2. Bốn lớp tương thích cần đánh giá

| Lớp | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| **Source compatibility** | Mã nguồn client/server cũ có biên dịch với generated API mới không? | Getter hoặc method stub đổi chữ ký |
| **Binary compatibility** | Bytecode đã biên dịch có chạy với JAR generated mới không? | `NoSuchMethodError`, `NoClassDefFoundError` |
| **Wire compatibility** | Client và server phiên bản khác nhau có đọc/gọi đúng qua gRPC không? | RPC path đổi, field number/type không tương thích |
| **Behavioral compatibility** | Ý nghĩa dữ liệu và hành vi RPC có còn như trước không? | Giá trị mặc định hoặc presence thay đổi cách xử lý |

Một thay đổi có thể tương thích ở một lớp nhưng phá vỡ lớp khác. Ví dụ đổi `java_package` có thể giữ nguyên protobuf wire format nhưng làm Java source không còn import được package cũ. Ngược lại, giữ nguyên Java class name nhưng đổi protobuf service package có thể khiến client gọi sai RPC path.

**Compile pass không chứng minh wire compatibility; wire compatibility cũng không đảm bảo behavioral compatibility.**

## 3. Khác biệt ở generated message API

Xét schema:

```proto
syntax = "proto3";

package learning.stock.v1;

option java_package = "vn.example.stock.v1";
option java_multiple_files = true;

message StockReply {
  string sku = 1;
  int64 available = 2;
}
```

Với cấu hình trên, Java generator tạo message class độc lập. API điển hình gồm:

```java
StockReply reply = StockReply.newBuilder()
        .setSku("BOOK-101")
        .setAvailable(12)
        .build();

String sku = reply.getSku();
long available = reply.getAvailable();
StockReply.Builder builder = StockReply.newBuilder();
```

Generated class còn có parser, serialization, descriptor và các interface hỗ trợ builder. Đây là API được generator quản lý; ứng dụng chỉ nên gọi các method công khai đã sinh.

### 3.1. Java package và cách chia file

Thay đổi `java_package`:

```proto
option java_package = "vn.example.inventory.v1";
```

sẽ thay đổi package Java của generated types. Mã nguồn import `vn.example.stock.v1.StockReply` cũ cần được cập nhật, dù protobuf package và field numbers có thể giữ nguyên.

Thay đổi `java_multiple_files` từ `true` sang `false` có thể chuyển message thành nested types trong outer class. Ví dụ cách tham chiếu Java có thể chuyển từ `StockReply` sang `StockProto.StockReply`. Điều này tác động source/binary API, dù message trên wire vẫn cùng schema.

`java_outer_classname` quyết định tên outer class chứa descriptor và các nested types khi dùng chế độ phù hợp. Đổi option này có thể phá các import hoặc tham chiếu trực tiếp đến outer class.

### 3.2. Field name, type và presence

Tên field trong proto thường được chuyển thành Java accessor theo quy tắc camelCase:

| Proto declaration | Java API điển hình |
| --- | --- |
| `string sku = 1;` | `getSku()`, `setSku(...)` |
| `int64 available = 2;` | `getAvailable()`, `setAvailable(...)` |
| `repeated string tags = 3;` | `getTagsList()`, `addTags(...)` |
| `map<string, int64> quantities = 4;` | `getQuantitiesMap()`, các builder method tương ứng |

Đổi tên field nhưng giữ nguyên field number thường có thể giữ cách giải mã wire cho protobuf binary, nhưng **Java accessor đổi tên** và mã nguồn phụ thuộc getter cũ có thể không biên dịch. Tên field cũng có thể ảnh hưởng JSON name và các hệ thống phản chiếu.

Đổi field type hoặc field number có thể làm thay đổi wire format. Không xem việc generated Java compile thành công là bằng chứng thay đổi đó an toàn với client đã phát hành.

Proto3 scalar field thông thường có giá trị mặc định và không luôn cung cấp presence accessor như message field. Khi khai báo `optional` cho scalar, Java API có thể có thêm `hasX()` để phân biệt “không được gửi” với “được gửi giá trị mặc định”:

```proto
message UpdateStockRequest {
  optional int64 reorder_point = 1;
}
```

`hasReorderPoint()` và `getReorderPoint()` có ngữ nghĩa khác nhau: getter có thể trả về giá trị mặc định khi field vắng mặt; presence method cho biết field có được đặt hay không. Thay đổi presence cần review logic ứng dụng, không chỉ review chữ ký Java.

### 3.3. Enum và oneof

Generated enum thường có các thành phần như enum constant, numeric value, `forNumber` và trạng thái không nhận diện được tùy API generator/runtime. Khi thêm enum value, client cũ có thể nhận giá trị chưa biết; code cần có nhánh xử lý phù hợp thay vì giả định mọi giá trị đều nằm trong danh sách đã biết.

`oneof` sinh API để kiểm tra nhánh đang được chọn, ví dụ `getPayloadCase()`, cùng các getter/setter cho từng lựa chọn. Thêm, xóa hoặc đổi field trong oneof có thể làm thay đổi enum case và cách ứng dụng đọc dữ liệu. Hãy kiểm tra cả generated API lẫn semantics khi field vắng mặt hoặc nhánh khác được chọn.

## 4. Khác biệt ở generated gRPC service API

Xét service:

```proto
service StockService {
  rpc GetStock(StockRequest) returns (StockReply);
  rpc WatchStock(StockRequest) returns (stream StockReply);
}
```

Plugin gRPC Java sinh lớp `StockServiceGrpc` với service descriptor, method descriptor, server base và các họ client stub. API điển hình có dạng:

```java
// Server extension point:
public static abstract class StockServiceImplBase
        implements io.grpc.BindableService {
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        // Hành vi mặc định thường trả UNIMPLEMENTED.
    }

    public void watchStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        // Server streaming.
    }
}

// Blocking client:
StockServiceGrpc.StockServiceBlockingStub blocking =
        StockServiceGrpc.newBlockingStub(channel);

// Async client:
StockServiceGrpc.StockServiceStub async =
        StockServiceGrpc.newStub(channel);
```

Đây là hình dạng minh họa của API grpc-java phổ biến; cần đối chiếu source thực tế do phiên bản plugin đang dùng sinh ra. Không tự giả định mọi version có đúng cùng nested types, method modifier hoặc helper API.

### 4.1. Cardinality quyết định chữ ký RPC

Thay đổi kiểu RPC sẽ thay đổi generated API:

| RPC type | Server method điển hình | Client API điển hình |
| --- | --- | --- |
| Unary | Một request, observer cho một response | Blocking trả một response; async nhận response observer |
| Server streaming | Một request, observer cho nhiều response | Blocking trả iterator; async nhận observer |
| Client streaming | Trả request observer để nhận nhiều request, observer cho response cuối | Async client gửi nhiều request |
| Bidirectional streaming | Request observer và response observer độc lập | Async client gửi/nhận nhiều message |

Ví dụ đổi:

```proto
rpc Upload(UploadRequest) returns (UploadReply);
```

thành:

```proto
rpc Upload(stream UploadRequest) returns (UploadReply);
```

không chỉ là sửa một từ trong schema. Server method chuyển từ nhận một `UploadRequest` sang trả `StreamObserver<UploadRequest>` để nhận chuỗi request. Client cũng cần chuyển từ lời gọi unary sang luồng request. Đây là thay đổi source API và RPC semantics; phải có kế hoạch migration cho cả hai phía.

### 4.2. Tên service/method ảnh hưởng RPC path

Tên RPC đầy đủ có dạng:

```text
/<protobuf-package>.<ServiceName>/<MethodName>
```

Đổi protobuf package, service name hoặc method name sẽ làm thay đổi method path mà client gọi. Đổi riêng `java_package` thường chỉ đổi package Java, không tự đổi protobuf RPC path. Vì vậy cần đánh giá riêng Java API và wire endpoint.

## 5. Generator version có thể đổi API dù schema không đổi

Khi nâng `protoc` hoặc `protoc-gen-grpc-java`, generated output có thể thay đổi ở:

- Annotation và import được thêm, bỏ hoặc đổi.
- Chữ ký, visibility hoặc helper method trong lớp generated.
- Cách triển khai descriptor và method handler.
- Các nested types hoặc interface hỗ trợ server API.
- Cảnh báo deprecation và yêu cầu runtime API mới.
- Formatting/comment/version marker trong generated source.

Không phải mọi diff đều là breaking change. Một thay đổi comment có thể không ảnh hưởng Java API; thay đổi chữ ký public method có thể làm mã ứng dụng không compile; thay đổi method descriptor có thể ảnh hưởng dispatch. Cần phân loại dựa trên **public API và hành vi**, không dựa trên số lượng dòng diff.

Quy trình so sánh generator:

1. Giữ nguyên toàn bộ schema và import dependencies.
2. Sinh mã bằng toolchain hiện tại, lưu output baseline.
3. Chỉ đổi version generator cần đánh giá.
4. Xóa generated output cũ và sinh lại.
5. So sánh file thay đổi; tập trung vào public classes, constructors, methods, nested types và descriptor.
6. Chạy compile/test với runtime được đề xuất cho generator mới.

Nếu schema và generator cùng thay đổi, hãy tách thành hai lượt review để biết thay đổi nào đến từ nguồn nào.

## 6. Cách review generated API diff

Đầu tiên xem diff source:

```bash
git diff -- build/generated/source/proto
```

Nếu generated source không được commit, có thể tạo output ở hai thư mục tạm riêng hoặc tạo hai worktree/build checkout với cùng schema nhưng khác toolchain. Không ghi đè baseline trước khi lưu kết quả cũ.

Dùng `javap` để kiểm tra public API của class đã biên dịch:

```bash
javap -classpath build/classes/java/main vn.example.stock.v1.StockReply
javap -classpath build/classes/java/main vn.example.stock.v1.StockServiceGrpc
```

`javap` cho thấy chữ ký class/method mà Java compiler tạo ra. Nó hữu ích khi diff source quá lớn, nhưng không thay thế kiểm tra protobuf descriptor hoặc wire compatibility.

Với thư viện contract được phát hành thành JAR, có thể dùng công cụ kiểm tra binary/source API như **Revapi** hoặc **japicmp** để so sánh artifact cũ và mới. Cấu hình công cụ theo policy của dự án; phân loại kết quả theo mức độ ảnh hưởng và xác nhận bằng compile tests với client cũ.

## 7. Kiểm thử tương thích khi nâng generated API

Một bộ kiểm thử tốt bao gồm nhiều lớp:

### 7.1. Compile client cũ với contract mới

Nếu client là mã nguồn có thể build lại, thử biên dịch client cũ với JAR contract mới. Lỗi getter, package, stub hoặc chữ ký method sẽ xuất hiện ở compile time.

Điều này kiểm tra **source compatibility**, chưa kiểm tra bytecode cũ hoặc wire behavior.

### 7.2. Kiểm tra binary compatibility

Nếu client đã được biên dịch và phát hành, kiểm tra khả năng liên kết với JAR mới. Dùng API comparison tool và chạy một smoke test bằng bytecode client cũ trên runtime classpath mới. Chú ý lỗi như `NoSuchMethodError` và `NoClassDefFoundError`.

### 7.3. Kiểm tra wire compatibility

Chạy client phiên bản cũ với server mới, sau đó chạy client mới với server cũ trong môi trường kiểm thử. Kiểm tra:

- RPC path và method type có còn khớp không.
- Field number/type có được giải mã đúng không.
- Field mới, enum value mới và unknown fields có được xử lý an toàn không.
- Status và metadata có giữ đúng contract không.

### 7.4. Kiểm tra hành vi

Test các trường hợp có ý nghĩa nghiệp vụ: field vắng mặt so với giá trị mặc định, enum chưa biết, oneof chưa chọn nhánh, request streaming rỗng, cancellation và deadline. Generated API có thể compile nhưng semantics mới vẫn làm ứng dụng xử lý sai.

## 8. Quy trình nâng cấp an toàn

Khi cần cập nhật generated API trong module **SPRING_GRPC**, thực hiện theo trình tự:

1. **Ghi baseline:** version schema, protoc, gRPC plugin, protobuf/grpc-java runtime và Spring starter.
2. **Phân loại thay đổi:** schema change, generator-only change hay runtime change.
3. **Sinh mã riêng:** giữ schema không đổi khi đang đánh giá generator; lưu generated output cũ và mới.
4. **Review API:** package, class, public method, RPC descriptor, method cardinality và presence semantics.
5. **Compile consumers:** thử client/server hiện tại với contract mới.
6. **Kiểm tra wire:** chạy ma trận client cũ/mới với server cũ/mới nếu deployment độc lập.
7. **Chạy integration tests:** unary, streaming, status, metadata, deadline và TLS theo phạm vi ứng dụng.
8. **Phát hành có version:** contract JAR và server/client release phải có version rõ ràng, migration notes và kế hoạch tương thích.

Không nâng generator chỉ vì thấy version mới hơn. Cần mục tiêu rõ, đánh giá diff và kiểm thử runtime trước khi phát hành.

## 9. Ví dụ checklist cho một thay đổi cụ thể

Giả sử đổi `java_package` từ `vn.example.stock.v1` sang `vn.example.inventory.v1` nhưng giữ nguyên protobuf package, service, method và field numbers.

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Java imports | Phải cập nhật package trong client/server source |
| Generated class names | Giữ tên message tương đối nhưng nằm trong Java package mới |
| Protobuf field numbers/types | Không đổi |
| gRPC full method path | Không đổi nếu protobuf package/service/method giữ nguyên |
| Binary compatibility | Có nguy cơ phá vỡ nếu class Java cũ không còn được cung cấp |
| Wire compatibility | Thường giữ nguyên với protobuf binary/gRPC path không đổi |
| Application behavior | Cần chạy integration tests để xác nhận mapping và runtime wiring |

Ví dụ này cho thấy một thay đổi có thể **breaking với Java consumers nhưng tương thích ở wire level**. Nếu thư viện contract được nhiều ứng dụng Java sử dụng, cần version major hoặc migration strategy phù hợp dù server/client trên mạng vẫn có thể giao tiếp.

## 10. Bài tập thực hành

1. Sinh `StockReply` từ schema mẫu, ghi lại package, getter, builder và descriptor.
2. Đổi `java_package` nhưng giữ protobuf package; phân loại ảnh hưởng source, binary và wire.
3. Đổi `java_multiple_files`; quan sát cách tham chiếu message và outer class thay đổi.
4. Đổi tên field nhưng giữ field number; xác định getter Java, JSON name và wire decoding.
5. Thêm `optional` scalar; kiểm tra `hasX()` và cách phân biệt field vắng mặt với giá trị mặc định.
6. Đổi unary RPC thành client-streaming; so sánh server base method và client stub signature.
7. Nâng riêng `protoc-gen-grpc-java`, giữ schema nguyên trạng và review diff public API.
8. Dùng `javap` hoặc Revapi/japicmp so sánh contract JAR trước và sau nâng cấp.
9. Build client cũ với contract mới, rồi chạy client/server hai phiên bản trong integration test.
10. Viết migration note chỉ rõ thay đổi source API, binary API, RPC path và wire semantics.

### Ghi nhớ

**Khác biệt generated API phải được đánh giá ở cả Java source, binary, protobuf/gRPC wire contract và hành vi.** Schema options có thể đổi tên/package Java mà không đổi wire; protobuf package/service/method hoặc field number/type có thể ảnh hưởng giao tiếp; nâng generator có thể đổi public API dù schema giữ nguyên. Hãy giữ baseline, nâng từng thành phần, review generated diff, kiểm tra descriptor và compile cả consumer cũ lẫn mới, rồi chạy integration tests trước khi phát hành.
