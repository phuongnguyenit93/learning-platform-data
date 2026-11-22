# Compatibility của generated code

## 1. Mục tiêu

Trong Spring gRPC, file Protobuf là nguồn hợp đồng; từ đó các công cụ sinh Java message, service base class và client stub. Khi nâng cấp schema hoặc dependency, một thay đổi có thể vẫn tương thích trên wire nhưng làm code Java không biên dịch, generated class không khởi tạo được hoặc server không đăng ký đúng method.

**Compatibility của generated code** là khả năng phối hợp đúng giữa schema Protobuf, mã Java được sinh, compiler/plugin sinh mã, thư viện runtime và code ứng dụng sử dụng các class đó. Đây là một lớp riêng bên cạnh wire compatibility và behavioral compatibility.

Sau bài học, bạn có thể:

- Phân biệt Protobuf Java message code với gRPC service/stub code.
- Nhận diện vai trò của `protoc`, `protoc-gen-grpc-java` và runtime dependency.
- Giữ ổn định Java package, class name và generated accessor khi cần tương thích source.
- Quản lý phiên bản generator/runtime có kiểm soát.
- Tránh nhiều phiên bản Protobuf/gRPC runtime cùng xuất hiện trên classpath.
- Tạo quy trình code generation có thể tái lập trong CI.
- Kiểm thử source, binary/runtime và wire compatibility trước khi nâng cấp.

## 2. Những gì được sinh từ một file .proto

Một contract gRPC thường sinh ra hai nhóm mã khác nhau:

| Nhóm generated code | Công cụ chính | Ví dụ |
|---|---|---|
| Protobuf message Java | `protoc` với Java generator tích hợp | `SearchRequest`, `SearchResponse`, enum, builder và descriptor |
| gRPC service Java | Plugin `protoc-gen-grpc-java` | `CatalogServiceGrpc`, `ImplBase`, blocking/async/future stub |

Ví dụ schema:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProtocol";

service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
}

message SearchRequest {
  string query = 1;
}

message SearchResponse {
  repeated string product_ids = 1;
}
```

Java generator sinh các message class và descriptor. gRPC Java plugin sinh service descriptor, method descriptor, stub và base class để server triển khai. Trong ứng dụng, hai nhóm này thường được dùng cùng nhau:

```java
SearchRequest request = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .build();

SearchResponse response = CatalogServiceGrpc
        .newBlockingStub(channel)
        .search(request);
```

Nếu chỉ chạy Java generator mà không chạy gRPC plugin, message class có thể tồn tại nhưng `CatalogServiceGrpc` và stub không được sinh. Nếu plugin gRPC chạy với schema hoặc compiler khác phiên bản dự kiến, generated service code có thể không khớp API/runtime trong project.

## 3. Phân biệt các lớp compatibility

| Lớp | Điều cần tương thích | Ví dụ lỗi |
|---|---|---|
| Wire compatibility | Bytes Protobuf và full method path | Client gọi path cũ nhưng server chỉ đăng ký path mới |
| Generated source compatibility | Tên package, class, method và accessor Java | Đổi `java_package` làm import của caller không còn hợp lệ |
| Runtime compatibility | Generated code chạy được với runtime dependency | Generated class yêu cầu API/version runtime không có |
| Build/codegen compatibility | Compiler và plugin sinh ra mã nhất quán | CI và máy developer sinh class khác nhau |
| Behavioral compatibility | Hành vi server vẫn đúng contract | Getter còn biên dịch nhưng default nghiệp vụ thay đổi |

Một thay đổi có thể tương thích ở một lớp nhưng không tương thích ở lớp khác. Ví dụ, đổi `java_package` không đổi binary Protobuf field hoặc full method path nếu `package` trong proto giữ nguyên, nhưng sẽ làm source code Java dùng package cũ không biên dịch.

Khi review nâng cấp, hãy trả lời riêng từng câu hỏi: wire có giữ nguyên không, generated Java API có thay đổi không, runtime có hỗ trợ generated code không, build có tái lập được không và hành vi caller có được giữ không.

## 4. Vai trò của protoc và gRPC Java plugin

### protoc

`protoc` đọc `.proto`, kiểm tra schema và sinh mã cho ngôn ngữ được yêu cầu. Với Java, nó tạo message classes, enum, builder và descriptor.

Ví dụ lệnh minh họa:

```bash
protoc \
  --proto_path=src/main/proto \
  --java_out=build/generated/source/proto/main/java \
  src/main/proto/catalog.proto
```

### protoc-gen-grpc-java

gRPC Java plugin sinh phần service/stub:

```bash
protoc \
  --proto_path=src/main/proto \
  --plugin=protoc-gen-grpc-java=/path/to/protoc-gen-grpc-java \
  --grpc-java_out=build/generated/source/proto/main/grpc \
  src/main/proto/catalog.proto
```

Đường dẫn plugin phụ thuộc hệ điều hành và cách build tải executable. Trong Gradle/Maven, plugin build thường quản lý việc tải và gọi executable; không nên tự chép một binary plugin không được version hóa vào máy developer.

Hai bước trên minh họa trách nhiệm của generator, không phải khuyến nghị tự viết shell task riêng cho mọi project. Dùng một build plugin được duy trì và cấu hình phiên bản rõ ràng để cả Java generator lẫn gRPC plugin được gọi nhất quán.

## 5. Generated Java API có thể đổi dù wire format không đổi

### java_package

`package` trong Protobuf quyết định namespace service trên wire. `java_package` quyết định package của class được sinh.

```proto
package catalog.v1;
option java_package = "dev.example.catalog.v1";
```

Đổi `java_package` từ `dev.example.catalog.v1` sang `dev.example.api.catalog` có thể giữ nguyên full method path `/catalog.v1.CatalogService/Search`, nhưng các import Java của caller và server sẽ thay đổi. Đây là source compatibility break, không nhất thiết là wire break.

### java_multiple_files

`java_multiple_files = true` khiến message/enum được sinh thành các top-level Java class riêng. Nếu bỏ option này, các type thường được truy cập qua outer wrapper class được sinh từ file proto. Thay đổi tùy chọn này có thể làm đổi tên class và import dù schema field không đổi.

### java_outer_classname

Nếu không khai báo `java_outer_classname`, tên wrapper được suy ra từ tên file theo quy tắc generator. Đổi tên file proto có thể làm thay đổi tên wrapper và phá source code tham chiếu class đó. Khai báo tường minh giúp tên wrapper ổn định.

### Tên field và accessor

Field number quyết định wire identity; tên field tham gia tạo accessor Java:

```proto
message SearchRequest {
  string query_text = 1;
}
```

Generated Java có accessor theo tên field, chẳng hạn `getQueryText()`. Nếu đổi tên thành `query`, giữ tag `1`, bytes cũ vẫn có thể được parse nhưng source code gọi `getQueryText()` sẽ không còn biên dịch sau khi sinh lại code.

Vì vậy:

- Giữ `java_package`, `java_multiple_files` và `java_outer_classname` ổn định nếu caller phụ thuộc vào generated API.
- Tránh đổi tên field chỉ để làm đẹp nếu code Java hoặc JSON mapping đang dùng tên cũ.
- Khi buộc phải đổi, lập migration source riêng và cập nhật toàn bộ caller.
- Không chỉnh sửa trực tiếp file Java generated để khắc phục; thay đổi phải bắt nguồn từ schema hoặc cấu hình generator.

## 6. Generated gRPC service API cũng là source contract

Với service:

```proto
service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
}
```

gRPC Java plugin tạo API có dạng:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub blockingStub =
        CatalogServiceGrpc.newBlockingStub(channel);

SearchResponse response = blockingStub.search(request);
```

Ở server, ứng dụng thường kế thừa:

```java
public final class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void search(
            SearchRequest request,
            StreamObserver<SearchResponse> observer) {
        // Xử lý request và kết thúc observer đúng một lần.
    }
}
```

Đổi package Protobuf, service name hoặc method name sẽ làm thay đổi generated type và có thể thay đổi full method path. Đổi cardinality từ unary sang streaming còn làm thay đổi signature handler/stub. Các thay đổi này cần được review như API migration, không chỉ là chạy lại code generation.

Các loại stub cũng là một phần generated API: blocking, async và future stub có thể được dùng bởi caller khác nhau. Không xóa hoặc đổi cách sinh stub mà chưa tìm các call site phụ thuộc.

## 7. Runtime dependency phải tương thích với generated code

Generated source không tự mang toàn bộ implementation của Protobuf hoặc gRPC. Khi chạy, classpath cần các runtime phù hợp:

| Thành phần | Vai trò |
|---|---|
| `protobuf-java` | Runtime cho generated Protobuf message |
| `grpc-protobuf` | Tích hợp Protobuf với gRPC |
| `grpc-stub` | API stub, base service và call abstraction |
| `grpc-api` | API nền của gRPC Java |
| Transport implementation | Ví dụ Netty hoặc Netty shaded để tạo channel/server |
| Spring gRPC starter | Tích hợp lifecycle, bean registration và cấu hình với Spring |

Generated Protobuf Java code có liên hệ chặt với runtime API. Không giả định mọi tổ hợp generated code và `protobuf-java` đều tương thích tùy ý. Quy tắc an toàn là pin compiler/generator và runtime theo một bộ phiên bản đã được xác nhận tương thích; ưu tiên dùng cùng release line theo hướng dẫn của Protobuf Java.

Tương tự, gRPC generated service code cần API từ gRPC Java runtime. Giữ các artifact `grpc-*` cùng một release line bằng dependency management/BOM của gRPC Java nếu project sử dụng. Phiên bản Spring gRPC starter cũng phải nằm trong dải tương thích mà starter công bố.

Một lỗi thường gặp là compile thành công vì một dependency kéo phiên bản runtime mới, nhưng môi trường triển khai lại nạp runtime khác qua dependency transitive hoặc classloader. Vì vậy cần kiểm tra dependency graph và chạy smoke/integration test trên classpath gần với production.

## 8. Quản lý phiên bản toolchain và runtime

Một bộ toolchain có ít nhất các phiên bản cần quản lý:

- Protobuf compiler `protoc`.
- gRPC Java codegen plugin `protoc-gen-grpc-java`.
- Protobuf Java runtime.
- Các thư viện `grpc-*`.
- Spring gRPC starter và Spring Boot/Spring Framework tương ứng.
- JDK và cấu hình source/target của Java.

Không cập nhật riêng một thành phần mà bỏ qua các thành phần liên quan. Ví dụ, nâng `protoc` nhưng giữ plugin gRPC quá cũ có thể làm build sinh message và service code từ hai thế hệ toolchain khác nhau.

Một bảng version policy trong build hoặc tài liệu kỹ thuật có thể giúp reviewer nhìn thấy bộ phiên bản:

| Thành phần | Cách quản lý |
|---|---|
| `protoc` | Pin version cụ thể trong build |
| `protoc-gen-grpc-java` | Pin version cụ thể; nâng cùng đợt gRPC Java |
| `protobuf-java` | Chọn runtime tương thích với Java code đã sinh |
| `grpc-*` | Dùng BOM hoặc dependency constraints để giữ đồng bộ |
| Spring gRPC starter | Theo ma trận tương thích của starter |
| JDK | Dùng toolchain version thống nhất trong CI và local |

Tránh `latest`, dynamic version hoặc phụ thuộc vào phiên bản tình cờ có trên máy developer. Nếu version thay đổi theo thời gian mà build không khóa, cùng một commit có thể sinh code khác nhau ở hai lần build.

## 9. Quản lý dependency graph để tránh runtime trùng lặp

Một ứng dụng có thể nhận `protobuf-java` từ nhiều dependency transitive. Nếu classpath chứa nhiều version, build tool thường chọn một version theo resolution rule; version được chọn có thể không phải version mà generated code hoặc starter đã được kiểm thử.

Kiểm tra:

- Có đúng một version hiệu lực của `protobuf-java` trong runtime classpath không?
- Các artifact `grpc-api`, `grpc-stub`, `grpc-protobuf` và transport có cùng release line không?
- Có dependency cũ kéo `grpc-*` hoặc Protobuf runtime xuống phiên bản thấp hơn không?
- Có library đóng gói/shade runtime Protobuf hoặc gRPC riêng không?
- Test và production có resolve cùng dependency graph không?

Ví dụ lệnh kiểm tra với Gradle:

```bash
./gradlew dependencyInsight --dependency protobuf-java --configuration runtimeClasspath
./gradlew dependencyInsight --dependency grpc-stub --configuration runtimeClasspath
```

Với Maven, dùng `mvn dependency:tree` và kiểm tra các nhánh transitive liên quan. Khi cần ép version, ưu tiên dependency management/BOM hoặc constraint tập trung; tránh thêm nhiều exclusion rời rạc mà không hiểu dependency nào đang cần API đó.

Không đưa đồng thời `grpc-netty` và `grpc-netty-shaded` vào runtime nếu ứng dụng không có chủ đích sử dụng cả hai transport. Chọn transport mà Spring gRPC starter hỗ trợ và cấu hình một cách nhất quán.

## 10. Sinh code có thể tái lập

Generated code cần giống nhau khi cùng schema và cùng toolchain được chạy trong CI hoặc máy developer. Quy trình nên:

1. Lưu `.proto` trong thư mục nguồn được quản lý version.
2. Pin version của compiler và mọi plugin sinh code.
3. Để build tool gọi generator theo cùng một cấu hình cho mọi môi trường.
4. Đưa generated output vào thư mục build riêng, không trộn với source viết tay.
5. Không sửa generated file thủ công.
6. Nếu repository commit generated code, luôn regenerate bằng toolchain đã pin và review diff cùng schema.
7. Nếu repository generate khi build, bảo đảm CI thực sự chạy codegen trước compile/test.

Chọn một chính sách rõ ràng:

| Chính sách | Ưu điểm | Điều cần bảo đảm |
|---|---|---|
| Generate khi build | Schema là nguồn chuẩn; tránh diff generated lớn trong review | Build/CI phải có compiler và plugin đúng version |
| Commit generated source | Consumer có thể xem hoặc dùng source đã sinh | Mọi thay đổi schema phải regenerate; không chỉnh tay |

Không vừa commit generated code vừa để một số module tự sinh lại bằng version khác. Điều đó dễ tạo hai nguồn sự thật và làm lỗi chỉ xuất hiện trên một môi trường.

Khi thay đổi generator, diff generated source có thể rất lớn dù `.proto` không đổi. Review cần xác định phần nào là thay đổi định dạng nội bộ của generator, phần nào đổi public API hoặc runtime requirement. Không xóa toàn bộ diff mà chưa hiểu tác động.

## 11. Java annotation và JDK compatibility

Generated code có thể tham chiếu annotation hoặc API phụ thuộc JDK và thư viện annotation. Ví dụ một số phiên bản gRPC Java generator sinh `@javax.annotation.Generated`; JDK mới không nhất thiết cung cấp annotation đó trong module chuẩn như các JDK cũ.

Nếu compile báo thiếu annotation:

- Kiểm tra chính xác import trong generated source.
- Xác định generator version đang được dùng.
- Thêm dependency annotation tương ứng nếu generator yêu cầu và dependency đó phù hợp với ứng dụng.
- Hoặc nâng generator theo kế hoạch để dùng cách sinh code tương thích với toolchain hiện tại.

Không thay hàng loạt `javax` thành `jakarta` trong generated source bằng script thủ công. `javax.annotation` và `jakarta.annotation` là các package khác nhau; thay tên không bảo đảm annotation API tương thích.

Đặt Java toolchain thống nhất trong build để generator output và source compile trên cùng baseline JDK. Nâng JDK cũng cần kiểm tra plugin, annotation processor và Spring gRPC starter.

## 12. Nâng cấp generated code an toàn

Một lần nâng cấp nên có các bước:

1. **Chụp baseline:** lưu schema, generated source API quan trọng và dependency graph hiện tại.
2. **Xác định phạm vi:** thay đổi `.proto`, compiler, gRPC plugin, runtime hay JDK?
3. **Kiểm tra release notes/compatibility:** xác nhận generator/runtime và Spring starter có hỗ trợ tổ hợp dự kiến.
4. **Nâng cấp đồng bộ có kiểm soát:** thay version trong dependency management/build plugin, không sửa từng module tùy tiện.
5. **Regenerate:** tạo message và service code từ schema bằng toolchain mới.
6. **Review source diff:** kiểm tra package, class, accessor, stub, annotation và descriptor.
7. **Compile caller:** xác minh source code ứng dụng và module phụ thuộc còn dùng được.
8. **Chạy runtime tests:** khởi tạo generated message, server và client trên classpath thực tế.
9. **Kiểm thử wire:** xác minh old/new message và client/server vẫn giao tiếp theo contract.
10. **Triển khai theo rollout:** giữ server/caller tương thích trong giai đoạn chuyển đổi.

Không kết hợp nhiều thay đổi lớn trong cùng một lần nếu không thể xác định nguyên nhân khi có lỗi. Ví dụ, nâng JDK, đổi Spring Boot, nâng protoc và đổi schema đồng thời khiến việc khoanh vùng compatibility regression khó hơn.

## 13. Ma trận compatibility cần kiểm thử

### Client/server version

| Client generated code | Server generated code | Điều cần xác minh |
|---|---|---|
| Cũ | Cũ | Baseline hoạt động |
| Cũ | Mới | Request cũ được parse và semantics cũ được giữ |
| Mới | Mới | Contract mới hoạt động |
| Mới | Cũ | Field mới bị bỏ qua hoặc method mới trả status đã dự kiến |

Ma trận này là kiểm tra wire/service compatibility; vẫn cần kiểm tra runtime dependency riêng.

### Generated code/runtime

Không nên giả định mọi tổ hợp version cũ/mới đều được hỗ trợ. Tạo ma trận dựa trên compatibility policy của Protobuf Java và gRPC Java:

| Tổ hợp | Cách đánh giá |
|---|---|
| Generated code và runtime cùng release line đã chọn | Tổ hợp chuẩn để kiểm thử và phát hành |
| Generated code mới hơn runtime | Không dùng nếu runtime chưa cung cấp API/version mà code sinh yêu cầu |
| Runtime mới hơn generated code | Chỉ dùng khi chính sách tương thích của runtime cho phép; vẫn cần test |
| gRPC plugin mới với grpc runtime cũ | Kiểm tra API được generated service code tham chiếu |
| Generated code được sinh từ compiler khác trong CI | Không chấp nhận nếu toolchain chưa được pin và kiểm chứng |

Với Protobuf Java, generated code có thể chứa kiểm tra runtime version. Hãy để runtime kiểm tra và build policy phát hiện mismatch; đừng tắt hoặc lách kiểm tra chỉ để ứng dụng khởi động. Cách an toàn là dùng bộ compiler/generator/runtime đã được xác nhận tương thích.

## 14. Các test cụ thể

### Source compatibility test

Biên dịch các module caller quan trọng với generated artifact mới. Test này phát hiện:

- Package/class đã đổi.
- Accessor đã đổi do rename field.
- Stub method hoặc signature đã đổi.
- `java_multiple_files`/outer class thay đổi cách import.

Nếu tổ chức phát hành generated proto như một thư viện riêng, nên có một consumer fixture nhỏ phụ thuộc artifact đó để xác nhận API Java thực tế.

### Descriptor test

Kiểm tra full method name và message type:

```java
var descriptor = CatalogServiceGrpc.getServiceDescriptor();
var method = descriptor.getMethods().stream()
        .filter(candidate ->
                candidate.getBareMethodName().equals("Search"))
        .findFirst()
        .orElseThrow();

assertEquals(
        "catalog.v1.CatalogService/Search",
        method.getFullMethodName());
```

Ví dụ duyệt danh sách method trong gRPC Java `ServiceDescriptor` và tìm theo bare method name. Điều cần bảo vệ là full method path cùng request/response descriptor đã công bố; API descriptor cụ thể cần khớp với phiên bản gRPC Java trong dự án.

### Wire test

Serialize message bằng generated code cũ, parse bằng code mới và kiểm tra field đã cam kết:

```java
byte[] oldBytes = oldRequest.toByteArray();
NewSearchRequest parsed = NewSearchRequest.parseFrom(oldBytes);

assertEquals("keyboard", parsed.getQuery());
```

Test ngược chiều cũng cần thiết khi server cũ phải đọc message do client mới gửi. Unknown field có thể được runtime Protobuf xử lý, nhưng không nên giả định server cũ thực thi semantics của field mới.

### Runtime integration test

Khởi động Spring application context hoặc test server với dependency thực tế:

- Bean service được đăng ký.
- Generated stub tạo call thành công.
- Message được serialize/deserialize.
- Status và deadline hoạt động đúng.
- Không có `NoSuchMethodError`, `NoClassDefFoundError`, `LinkageError` hoặc lỗi runtime version khi khởi động.

Test unit trên mapper không thể phát hiện mọi lỗi classpath hoặc service registration.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không có `CatalogServiceGrpc` | Chỉ chạy Java Protobuf generator | Cấu hình và chạy gRPC Java plugin |
| Caller không tìm thấy generated class | Đổi `java_package` hoặc `java_multiple_files` | Giữ Java options hoặc migration import có kế hoạch |
| `NoSuchMethodError` khi chạy | Runtime dependency không khớp generated code hoặc thư viện khác | Kiểm tra dependency graph và version alignment |
| Runtime version validation thất bại | Generated code và Protobuf runtime không tương thích | Dùng toolchain/runtime đã được xác nhận |
| Máy developer và CI sinh code khác nhau | Không pin compiler/plugin | Khóa version và dùng build plugin thống nhất |
| Compile thiếu `javax.annotation.Generated` | Generated code tham chiếu annotation không có trên classpath | Kiểm tra generator và dependency annotation phù hợp |
| Stub thiếu method mới | Client dùng generated artifact/schema cũ | Nâng proto artifact và regenerate client |
| Full method path thay đổi ngoài ý muốn | Đổi Protobuf package/service/method | Giữ path cũ hoặc phát hành versioned service |
| Generated diff rất lớn | Đổi generator hoặc formatter | Review public API/runtime impact, không chỉ số dòng |
| Runtime có nhiều bản Protobuf | Dependency transitive kéo version khác nhau | Dùng BOM/constraints và kiểm tra runtimeClasspath |

## 16. Bài tập thực hành

**Tình huống:** Một Spring gRPC module phát hành thư viện `catalog-proto` cho nhiều service client. Nhóm muốn thêm field `page_size` vào `SearchRequest`, đồng thời nâng phiên bản Protobuf và gRPC Java toolchain. Một số service vẫn build bằng generated artifact cũ.

Hãy thực hiện:

1. Ghi lại `package`, `java_package`, `java_multiple_files`, `java_outer_classname`, full method path và generated API hiện tại.
2. Chọn version `protoc`, `protoc-gen-grpc-java`, `protobuf-java`, `grpc-*` và Spring gRPC starter theo một bộ tương thích đã xác nhận.
3. Pin version trong build; không dùng dynamic/latest version.
4. Thêm `optional int32 page_size` với tag chưa dùng; giữ nguyên field cũ và Java options.
5. Regenerate message/service code bằng build tool; không sửa generated source thủ công.
6. Kiểm tra dependency graph để tránh nhiều runtime version.
7. Compile một consumer fixture dùng generated API cũ và mới; ghi nhận source changes cần migration.
8. Chạy descriptor, wire và Spring gRPC integration tests.
9. Kiểm thử client cũ/server mới và client mới/server cũ; xác minh default và unknown-field behavior.
10. Chỉ phát hành artifact mới sau khi CI tái lập được code generation và runtime tests thành công.

**Tiêu chí hoàn thành:** toolchain được pin; generated code có thể tái lập; source API thay đổi được nhận diện; runtime dependency tương thích; full method path giữ nguyên; old/new client-server có hành vi đã kiểm thử.

## 17. Ghi nhớ

Generated code là một phần của API Java mà ứng dụng thực sự biên dịch và chạy. `protoc` sinh Protobuf message; `protoc-gen-grpc-java` sinh service, stub và base class. Giữ ổn định `java_package`, `java_multiple_files`, `java_outer_classname` và tên field khi cần source compatibility; phân biệt các tùy chọn Java này với Protobuf `package` quyết định full method path. Pin compiler/plugin/runtime, đồng bộ các artifact gRPC, tránh nhiều runtime version trên classpath và để build sinh code theo một quy trình tái lập. Kiểm tra source, descriptor, wire và runtime integration trước khi phát hành; wire compatibility riêng lẻ không chứng minh generated code tương thích.
