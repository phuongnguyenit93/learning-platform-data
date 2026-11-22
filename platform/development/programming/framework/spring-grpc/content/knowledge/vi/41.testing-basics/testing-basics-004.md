# Kiểm tra generated request và response

**Chương:** Testing basics  
**Phạm vi:** Spring gRPC (SPRING_GRPC) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này tập trung vào cách kiểm tra generated protobuf request và response trong unit test, serialization test và in-process gRPC test. Mục tiêu là bảo đảm code ứng dụng tạo, đọc và trao đổi message đúng với contract đã định nghĩa.

## 1. Vì sao cần kiểm tra generated request và response?

Protocol Buffers sinh Java message classes từ file .proto. Generated classes cung cấp builder, getter, parser, enum và API cho repeated/oneof fields. Không cần viết unit test để chứng minh protoc sinh đúng getter hay builder; điều cần kiểm tra là ứng dụng sử dụng generated types đúng semantics của hợp đồng.

Các lỗi thường xuất hiện ở chỗ ứng dụng tạo hoặc đọc message:

- Field proto3 không có presence bị nhầm với field đã gửi giá trị mặc định.
- Optional field có mặt nhưng giá trị rỗng bị coi như không gửi.
- Repeated field bị mất phần tử hoặc thay đổi thứ tự.
- Oneof branch có giá trị false, zero hoặc chuỗi rỗng bị coi như chưa chọn.
- Enum numeric value mới bị đổi âm thầm thành giá trị mặc định.
- Timestamp/Duration bị mất độ chính xác khi chuyển đổi.
- Builder bị sửa sau khi build và người viết test hiểu nhầm message đã build cũng đổi theo.
- Message serialize rồi parse lại không giữ dữ liệu như contract yêu cầu.

Kiểm tra generated request/response giúp bảo vệ contract tại biên gRPC, đặc biệt khi nhiều client/server được triển khai ở các phiên bản khác nhau.

## 2. Chọn đúng tầng kiểm thử

| Loại test | Cần kiểm tra | Có cần gRPC server không? |
| --- | --- | --- |
| Generated message unit test | Default, presence, oneof, repeated, enum, equality và immutability | Không |
| Serialization test | Message encode/decode qua protobuf wire format | Không |
| Mapper test | Application model chuyển thành request/response đúng | Không |
| In-process gRPC test | Generated stub, service base, request/response và status qua gRPC runtime | Có, dùng in-process server |
| Transport integration test | HTTP/2, Netty, TLS, metadata và cấu hình server thực | Có |

Không dùng một in-process test để kết luận TLS, Netty event loop hoặc load balancing hoạt động. Ngược lại, không cần khởi động Spring context để kiểm tra một generated message builder.

## 3. Hợp đồng protobuf dùng trong ví dụ

Ví dụ Catalog service có request với optional field, repeated field và oneof; response có enum, Timestamp, repeated và oneof:

~~~proto
syntax = "proto3";

import "google/protobuf/timestamp.proto";

package catalog.v1;
option java_package = "com.example.catalog.grpc";
option java_multiple_files = true;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (ProductResponse);
}

message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
  repeated string expand = 3;
  oneof selector {
    string sku = 4;
    int64 legacy_id = 5;
  }
}

enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;
}

message ProductResponse {
  string product_id = 1;
  string display_name = 2;
  ProductState state = 3;
  optional string description = 4;
  repeated string tags = 5;
  google.protobuf.Timestamp updated_at = 6;
  oneof source {
    string supplier_code = 7;
    int64 import_batch_id = 8;
  }
}
~~~

Với java_multiple_files, plugin sinh các message class riêng trong package đã khai báo, cùng CatalogServiceGrpc chứa service base và stub. Test nên import generated types thật từ source set của dự án.

## 4. Tạo generated request bằng builder

Generated message là immutable. Tạo message bằng builder, đặt các field rồi gọi build():

~~~java
GetProductRequest request = GetProductRequest.newBuilder()
        .setProductId("product-42")
        .setLocale("vi-VN")
        .addExpand("price")
        .addExpand("inventory")
        .setSku("SKU-42")
        .build();
~~~

Trong test, builder làm rõ dữ liệu đầu vào. Không mock generated request vì mock không thể đại diện đầy đủ hành vi parser, default value, field presence, oneof case và unknown fields của protobuf runtime.

## 5. Kiểm tra default value và field presence

Với scalar proto3 thông thường, getter trả giá trị mặc định nếu field không được gửi. Với optional field, generated API cung cấp has-method để phân biệt:

~~~java
@Test
void distinguishesAbsentOptionalFieldFromPresentEmptyValue() {
    GetProductRequest absent = GetProductRequest.newBuilder()
            .setProductId("product-1")
            .build();

    GetProductRequest presentEmpty = absent.toBuilder()
            .setLocale("")
            .build();

    assertFalse(absent.hasLocale());
    assertEquals("", absent.getLocale());

    assertTrue(presentEmpty.hasLocale());
    assertEquals("", presentEmpty.getLocale());
}
~~~

Hai request đều trả chuỗi rỗng từ getLocale(), nhưng chỉ request thứ hai có presence. Nếu API dùng field này để quyết định có ghi đè locale mặc định hay không, khác biệt đó có ý nghĩa.

Với scalar không optional, không có has-method trong proto3 thông thường. Nếu ứng dụng cần phân biệt không gửi với gửi zero/false/empty, hãy thiết kế schema dùng optional hoặc oneof rồi kiểm tra presence tương ứng.

## 6. Kiểm tra repeated field và thứ tự

Repeated field có thể rỗng hoặc chứa nhiều phần tử. Generated API cung cấp list getter và count/index getter:

~~~java
@Test
void preservesRepeatedFieldOrder() {
    GetProductRequest request = GetProductRequest.newBuilder()
            .addExpand("price")
            .addExpand("inventory")
            .addExpand("images")
            .build();

    assertEquals(3, request.getExpandCount());
    assertEquals(
            List.of("price", "inventory", "images"),
            request.getExpandList());
    assertEquals("inventory", request.getExpand(1));
}
~~~

Đừng chỉ assert số phần tử. Test cả nội dung và thứ tự nếu thứ tự có ý nghĩa trong contract. List do generated message cung cấp là immutable; khi cần biến đổi, tạo collection mới.

## 7. Kiểm tra oneof, kể cả giá trị mặc định

Không suy ra nhánh oneof từ getter vì một nhánh có thể được chọn với giá trị rỗng hoặc zero. Hãy kiểm tra generated case enum:

~~~java
@Test
void distinguishesOneofBranchFromUnsetBranch() {
    GetProductRequest unset = GetProductRequest.newBuilder().build();
    GetProductRequest emptySku = GetProductRequest.newBuilder()
            .setSku("")
            .build();
    GetProductRequest zeroLegacyId = GetProductRequest.newBuilder()
            .setLegacyId(0)
            .build();

    assertEquals(
            GetProductRequest.SelectorCase.SELECTOR_NOT_SET,
            unset.getSelectorCase());
    assertEquals(
            GetProductRequest.SelectorCase.SKU,
            emptySku.getSelectorCase());
    assertEquals(
            GetProductRequest.SelectorCase.LEGACY_ID,
            zeroLegacyId.getSelectorCase());
}
~~~

Test này bảo vệ semantics “nhánh đã được chọn” ngay cả khi giá trị bằng default. Protobuf bảo đảm chỉ một nhánh trong cùng oneof có hiệu lực; khi builder đặt nhánh khác, nhánh trước được thay thế.

## 8. Kiểm tra enum và giá trị numeric chưa biết

Proto3 enum có giá trị zero đầu tiên làm default. Generated enum accessor có thể trả UNRECOGNIZED khi wire message mang numeric value mà phiên bản code hiện tại chưa biết. Với Java generated API, numeric accessor giữ giá trị gốc:

~~~java
@Test
void preservesUnknownEnumNumericValue() {
    ProductResponse response = ProductResponse.newBuilder()
            .setStateValue(99)
            .build();

    assertEquals(ProductState.UNRECOGNIZED, response.getState());
    assertEquals(99, response.getStateValue());
}
~~~

Đây là khác biệt giữa enum value chưa biết và unknown field. Enum field vẫn có field number đã khai báo; chỉ numeric enum value chưa được phiên bản server/client nhận diện. Unknown field là field number mà schema hiện tại không khai báo.

Test nên phản ánh policy của ứng dụng: giữ numeric value để forward compatibility, hoặc từ chối khi mapping sang application enum. Không âm thầm chuyển UNRECOGNIZED thành PRODUCT_STATE_UNSPECIFIED nếu hai giá trị có semantics khác nhau.

## 9. Kiểm tra Timestamp và response presence

Timestamp protobuf có seconds và nanos. Khi chuyển sang Instant, không đổi qua milliseconds nếu cần giữ độ chính xác nano giây:

~~~java
@Test
void preservesTimestampNanosecondPrecision() {
    Timestamp timestamp = Timestamp.newBuilder()
            .setSeconds(1_800_000_000L)
            .setNanos(123_456_789)
            .build();

    ProductResponse response = ProductResponse.newBuilder()
            .setProductId("product-7")
            .setUpdatedAt(timestamp)
            .setDescription("")
            .build();

    assertTrue(response.hasUpdatedAt());
    assertEquals(timestamp, response.getUpdatedAt());
    assertTrue(response.hasDescription());
    assertEquals("", response.getDescription());
}
~~~

Message field như Timestamp có presence riêng. Optional string cũng phân biệt absent với present-empty. Test response cần xác nhận server trả đúng sự khác biệt này nếu client dựa vào nó.

Nếu chuyển Timestamp sang java.time.Instant, kiểm tra seconds và nanos tường minh. Timestamp không hợp lệ cần được từ chối theo validation policy; generated builder không tự bảo đảm mọi seconds/nanos đều nằm trong phạm vi Timestamp chuẩn.

## 10. Kiểm tra message immutability

Sau khi gọi build(), message không thay đổi khi builder được sửa tiếp:

~~~java
@Test
void builtMessageIsImmutableSnapshot() {
    GetProductRequest.Builder builder =
            GetProductRequest.newBuilder()
                    .setProductId("product-before");

    GetProductRequest first = builder.build();
    builder.setProductId("product-after");
    GetProductRequest second = builder.build();

    assertEquals("product-before", first.getProductId());
    assertEquals("product-after", second.getProductId());
    assertNotEquals(first, second);
}
~~~

Đặc tính này hữu ích khi adapter tạo request/response rồi truyền qua nhiều lớp. Không giữ builder mutable dùng chung giữa các RPC hoặc chia sẻ builder giữa thread.

## 11. Serialization round-trip

Protobuf message được serialize thành wire bytes rồi parse lại bằng parser của generated class. Test round-trip xác nhận dữ liệu contract được giữ:

~~~java
@Test
void requestSurvivesProtobufBinaryRoundTrip() throws Exception {
    GetProductRequest original = GetProductRequest.newBuilder()
            .setProductId("product-42")
            .setLocale("vi-VN")
            .addExpand("price")
            .addExpand("inventory")
            .setLegacyId(0)
            .build();

    byte[] bytes = original.toByteArray();
    GetProductRequest parsed = GetProductRequest.parseFrom(bytes);

    assertEquals(original, parsed);
    assertTrue(parsed.hasLocale());
    assertEquals(
            GetProductRequest.SelectorCase.LEGACY_ID,
            parsed.getSelectorCase());
    assertEquals(0L, parsed.getLegacyId());
}
~~~

Message equality của protobuf so sánh nội dung message, bao gồm field và unknown fields. Test này không cần gRPC channel; nó kiểm tra protobuf wire serialization/parser.

Response cũng cần round-trip nếu ứng dụng có mapping response phức tạp:

~~~java
@Test
void responseSurvivesBinaryRoundTrip() throws Exception {
    ProductResponse original = ProductResponse.newBuilder()
            .setProductId("product-42")
            .setDisplayName("Bàn phím")
            .setState(ProductState.PRODUCT_STATE_ACTIVE)
            .addTags("featured")
            .setSupplierCode("supplier-A")
            .build();

    ProductResponse parsed =
            ProductResponse.parseFrom(original.toByteArray());

    assertEquals(original, parsed);
    assertEquals(
            ProductResponse.SourceCase.SUPPLIER_CODE,
            parsed.getSourceCase());
}
~~~

## 12. Unknown field và forward compatibility

Protobuf binary format cho phép parser giữ unknown fields để message có thể được chuyển tiếp giữa các phiên bản schema khác nhau. Có thể tạo một field number chưa khai báo trong schema bằng CodedOutputStream:

~~~java
import com.google.protobuf.CodedOutputStream;
import java.io.ByteArrayOutputStream;
import java.util.Arrays;

@Test
void retainsUnknownFieldWhenParsingAndReserializing() throws Exception {
    GetProductRequest known = GetProductRequest.newBuilder()
            .setProductId("product-9")
            .build();

    ByteArrayOutputStream unknownBytes = new ByteArrayOutputStream();
    CodedOutputStream coded = CodedOutputStream.newInstance(unknownBytes);
    coded.writeUInt64(99, 7L);
    coded.flush();

    byte[] knownBytes = known.toByteArray();
    byte[] wireBytes = Arrays.copyOf(
            knownBytes,
            knownBytes.length + unknownBytes.size());
    System.arraycopy(
            unknownBytes.toByteArray(),
            0,
            wireBytes,
            knownBytes.length,
            unknownBytes.size());

    GetProductRequest parsed = GetProductRequest.parseFrom(wireBytes);
    assertTrue(parsed.getUnknownFields().hasField(99));
    assertEquals(
            7L,
            parsed.getUnknownFields()
                    .getField(99)
                    .getVarintList()
                    .get(0));

    GetProductRequest reparsed =
            GetProductRequest.parseFrom(parsed.toByteArray());
    assertTrue(reparsed.getUnknownFields().hasField(99));
}
~~~

Không xóa unknown fields nếu message đóng vai trò proxy/relay và cần chuyển tiếp dữ liệu từ client mới tới service mới. Ngược lại, nếu ứng dụng map message sang application model rồi tạo message mới, unknown fields có thể không được giữ; hãy xác định rõ component nào cần forward compatibility.

Unknown fields trong binary protobuf không có nghĩa JSON parser phải giữ mọi key lạ theo cùng cách. Quy tắc JSON mapping và binary wire format khác nhau; test theo đúng serialization format mà hệ thống sử dụng.

## 13. Payload malformed và parser failure

Generated parser từ chối payload không đúng wire format. Ví dụ length-delimited field khai báo dài hơn số byte thực tế:

~~~java
@Test
void rejectsTruncatedProtobufPayload() {
    byte[] truncated = new byte[] {
            0x0A, // field 1, wire type 2
            0x05, // length declares five bytes
            0x41  // only one byte follows
    };

    assertThrows(
            InvalidProtocolBufferException.class,
            () -> GetProductRequest.parseFrom(truncated));
}
~~~

Đây là parser test. Trong RPC thực, gRPC runtime parse message trước khi gọi service handler; payload malformed có thể khiến RPC thất bại mà adapter không được gọi. Không dùng parser failure để thay thế validation cho message đã parse thành công nhưng chứa giá trị sai.

## 14. Kiểm tra generated stub với in-process gRPC server

Unit test message không xác nhận generated client stub gọi đúng service method. Một in-process test có thể kết hợp generated request, generated stub và service base mà không mở socket:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class CatalogGeneratedStubTest {

    @Test
    void generatedStubExchangesGeneratedRequestAndResponse()
            throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        ProductResponse expected = ProductResponse.newBuilder()
                .setProductId("product-42")
                .setDisplayName("Mechanical keyboard")
                .setState(ProductState.PRODUCT_STATE_ACTIVE)
                .build();

        CatalogServiceGrpc.CatalogServiceImplBase service =
                new CatalogServiceGrpc.CatalogServiceImplBase() {
                    @Override
                    public void getProduct(
                            GetProductRequest request,
                            StreamObserver<ProductResponse> observer) {
                        assertEquals("product-42", request.getProductId());
                        observer.onNext(expected);
                        observer.onCompleted();
                    }
                };

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(service)
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder
                .forName(serverName)
                .directExecutor()
                .build();

        try {
            GetProductRequest request = GetProductRequest.newBuilder()
                    .setProductId("product-42")
                    .build();
            ProductResponse actual =
                    CatalogServiceGrpc.newBlockingStub(channel)
                            .getProduct(request);

            assertEquals(expected, actual);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

In-process test xác nhận generated stub, method binding và message exchange qua gRPC runtime. Nó không thay thế Netty/HTTP2/TLS integration test vì transport in-process không mở TCP socket.

## 15. Tổ chức JUnit 5 test

Generated message test thường là test thuần Java:

~~~java
import org.junit.jupiter.api.Test;

class GeneratedProductMessageTest {
    // Tạo generated messages bằng builder và assert semantics.
}
~~~

Không cần \`@SpringBootTest\` hoặc Mockito nếu chỉ kiểm tra builder, parser và equality. Khi test mapper, khởi tạo mapper thật. Khi test stub/service registration, dùng in-process gRPC server. Giữ mỗi test tập trung vào một contract behavior để lỗi dễ xác định.

Các dependency test thường gồm:

- JUnit Jupiter cho test lifecycle/assertions.
- Protobuf Java runtime được dùng bởi generated code.
- gRPC in-process transport nếu kiểm tra generated stub.
- Mockito chỉ khi cần mock application dependency ở adapter test.

Version protobuf runtime, protoc plugin và gRPC artifacts phải tương thích với BOM/build convention của module. Không tự nâng riêng protobuf runtime chỉ để một test compile.

## 16. Ma trận kiểm thử generated request và response

| Nhóm | Các ca quan trọng |
| --- | --- |
| Scalar/default | Không gửi, gửi giá trị mặc định, gửi giá trị thông thường |
| Optional | Absent, present-empty, present-non-empty |
| Repeated | Empty, một phần tử, nhiều phần tử và thứ tự |
| Oneof | Chưa chọn, từng nhánh, nhánh có giá trị zero/empty |
| Enum | Mỗi enum đã biết, unspecified, unknown numeric value |
| Timestamp/Duration | Presence, seconds/nanos, giá trị biên |
| Immutability | Builder đổi sau build không làm đổi message cũ |
| Serialization | Request/response binary round-trip |
| Unknown field | Parse và reserialize vẫn giữ field chưa biết khi cần |
| Malformed payload | Parser từ chối wire bytes không hợp lệ |
| Generated stub | Request tới đúng service method, response trả đúng kiểu |

Chọn các ca theo schema thật. Không cần test từng getter generated nếu không có semantics đặc biệt; tập trung vào field presence, compatibility và chuyển đổi có nguy cơ làm mất dữ liệu.

## 17. Anti-pattern thường gặp

- **Mock generated message:** không kiểm tra được protobuf builder/parser semantics.
- **Chỉ assert getter value:** bỏ sót khác biệt giữa absent và present-default.
- **Chỉ assert repeated count:** không phát hiện sai thứ tự hoặc nội dung.
- **Không kiểm tra oneof case:** nhầm giá trị false/zero/empty với nhánh chưa chọn.
- **Đổi Timestamp qua milliseconds:** mất độ chính xác nano giây.
- **Bỏ unknown fields trong relay:** làm hỏng forward compatibility.
- **Test parser rồi kết luận validator đúng:** parsing và semantic validation là hai việc khác nhau.
- **Dùng in-process test để kết luận TLS hoạt động:** transport này không thực hiện TLS handshake qua TCP.
- **Khởi động toàn bộ Spring context cho message test:** làm test chậm mà không tăng độ tin cậy.

## 18. Tự luyện tập

1. Vì sao generated protobuf message nên được tạo bằng builder thật trong unit test?
2. Phân biệt optional field absent với present-empty bằng những assertion nào?
3. Viết test chứng minh oneof branch có giá trị zero vẫn được chọn.
4. Làm thế nào kiểm tra Timestamp không mất nano giây khi serialize/parse?
5. Phân biệt unknown enum numeric value với unknown field number.
6. Khi nào cần test unknown field được giữ qua parse và reserialize?
7. In-process gRPC test xác nhận được điều gì và không xác nhận được điều gì?

**Ghi nhớ:** Kiểm tra generated request và response bằng message thật được tạo từ builder; xác nhận default/presence, repeated, oneof, enum, timestamp, immutability và binary serialization. Dùng parser test cho malformed payload, unknown-field test cho forward compatibility và in-process gRPC test cho generated stub/service exchange. Tách rõ message semantics, validation của ứng dụng và behavior của transport.
