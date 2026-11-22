# Versioning contract test

Trong Spring gRPC, contract versioning bảo đảm client và server có thể được phát hành, nâng cấp và rollback ở các thời điểm khác nhau mà vẫn giao tiếp đúng. Contract không chỉ gồm file .proto; nó còn gồm tên service/method trên wire, kiểu message, semantics của field, status/error detail và hành vi mà client mong đợi.

**Versioning contract test** kiểm tra các cặp phiên bản client/server quan trọng trước khi phát hành. Mục tiêu là phát hiện thay đổi phá vỡ tương thích sớm, đặc biệt trong triển khai rolling hoặc khi nhiều consumer chưa thể nâng cấp cùng lúc.

## 1. Phân biệt phiên bản wire và phiên bản Java

Tên package Protobuf xác định tên đầy đủ của message và gRPC service trên wire. gRPC method path được tạo từ package, service và method:

~~~text
/acme.catalog.v1.CatalogService/GetProduct
~~~

Các thành phần có vai trò khác nhau:

| Thành phần | Ảnh hưởng |
| --- | --- |
| package trong .proto | Tên Protobuf đầy đủ và gRPC service path; đổi có thể làm client không tìm thấy method |
| service hoặc rpc name | Thành phần của gRPC method path; đổi là thay endpoint trên wire |
| java_package | Package Java sinh ra; không tự thay gRPC method path |
| java_multiple_files | Cách sinh class Java; không thay wire contract |
| Field number và wire type | Cách encode/decode message Protobuf |

Có thể đổi java_package để tổ chức lại mã nguồn nếu giữ nguyên proto package, service, method và message semantics. Đổi package từ acme.catalog.v1 sang acme.catalog.v2 tạo service path khác; hãy xem đó là API version mới và duy trì v1 trong thời gian consumer chuyển đổi.

## 2. Quy tắc tiến hóa Protobuf an toàn

Khi mở rộng message, ưu tiên thêm field mới với field number chưa từng dùng. Ví dụ:

~~~proto
// Contract v1
message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string name = 2;
}
~~~

Phiên bản mở rộng có thể thêm field:

~~~proto
// Contract hiện tại, vẫn giữ proto package/service/method của v1
message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
}

message GetProductResponse {
  string product_id = 1;
  string name = 2;
  optional string display_name = 3;
}
~~~

Các quy tắc quan trọng:

- Không đổi field number đã phát hành.
- Không tái sử dụng field number hoặc tên của field đã xóa; dùng reserved.
- Thêm field mới thường tương thích ở wire level, nhưng consumer vẫn cần xử lý giá trị mặc định và presence.
- Không đổi type chỉ vì một số type có cùng wire type; semantics, miền giá trị và encoding có thể khác.
- Không đổi singular thành repeated, chuyển field vào/ra oneof, hoặc thay đổi ý nghĩa field đang dùng.
- Thêm enum value cần bảo đảm client cũ xử lý giá trị chưa biết.
- Không đổi tên service/method hoặc proto package trong cùng version path nếu cần giữ client cũ.

Khi xóa field, giữ số và tên đã dùng ở trạng thái reserved:

~~~proto
message GetProductResponse {
  string product_id = 1;
  string name = 2;
  optional string display_name = 3;

  reserved 4;
  reserved "legacy_description";
}
~~~

reserved ngăn người phát triển vô tình gán lại tag cũ trong một thay đổi tương lai. Đây là bảo vệ lâu dài cho dữ liệu được serialize, lưu trữ hoặc truyền qua những phiên bản khác nhau.

## 3. Thay đổi nào cần version mới?

| Thay đổi | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Thêm field optional mới | Thường tương thích wire | Kiểm tra default/presence ở consumer cũ |
| Xóa field nhưng không reserve | Có nguy cơ tái sử dụng tag | Reserve số và tên |
| Đổi field number | Breaking | Giữ tag cũ; thêm field mới nếu cần |
| Đổi int32 sang sint32 | Cùng wire type nhưng encoding khác | Không đổi trực tiếp; thêm field mới |
| Đổi string sang bytes | Có thể parse nhưng semantics thay đổi | Thêm field mới và migration |
| Đổi tên RPC hoặc service | gRPC method path thay đổi | Giữ endpoint cũ hoặc tạo version mới |
| Đổi proto package | Full service/message name thay đổi | Duy trì v1 và tạo v2 song song |
| Thêm enum value | Client cũ có thể gặp giá trị lạ | Yêu cầu client xử lý unknown enum |
| Đổi streaming shape | Thay đổi giao thức call | Tạo RPC/version mới |

Không đánh giá compatibility chỉ bằng việc schema có compile. Một thay đổi có thể wire-compatible nhưng phá vỡ business semantics, ví dụ đổi ý nghĩa price từ đơn vị đồng sang đơn vị xu mà vẫn giữ int64.

## 4. Kiểm thử hai chiều giữa client cũ và server mới

Rolling deployment thường có server mới chạy trong khi một số client vẫn dùng generated stub cũ. Contract test cần chứng minh:

1. Client v1 gọi server mới được.
2. Client mới gọi server v1 được nếu thay đổi được thiết kế tương thích.
3. Field mới không làm client cũ lỗi khi parse response.
4. Server cũ bỏ qua field request mới và client mới xử lý giá trị thiếu theo default/presence.

Ví dụ test fixture có hai bản .proto giữ nguyên package, service, rpc và field cũ, nhưng dùng java_package khác để cùng tồn tại trong test module:

~~~proto
// Fixture client v1: java_package = "com.acme.catalog.client.v1"
syntax = "proto3";
package acme.catalog.v1;
option java_multiple_files = true;
option java_package = "com.acme.catalog.client.v1";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
message GetProductRequest {
  string product_id = 1;
}
message GetProductResponse {
  string product_id = 1;
  string name = 2;
}
~~~

~~~proto
// Fixture server hiện tại: java_package = "com.acme.catalog.server.current"
syntax = "proto3";
package acme.catalog.v1;
option java_multiple_files = true;
option java_package = "com.acme.catalog.server.current";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
}
message GetProductResponse {
  string product_id = 1;
  string name = 2;
  optional string display_name = 3;
}
~~~

java_package khác nhau để tránh trùng tên class Java; package Protobuf vẫn là acme.catalog.v1, do đó full gRPC method path giữ nguyên. Trong repository thực tế, đặt fixture cũ ở test source set riêng hoặc lấy generated artifact từ release trước, không tự sửa file generated.

## 5. Contract test: client cũ gọi server mới

Server mới hiểu field locale và trả thêm display_name. Client cũ chỉ biết các field v1:

~~~java
import io.grpc.Server;
import io.grpc.ManagedChannel;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OldClientNewServerContractTest {

    @Test
    void oldClientCanReadResponseFromNewServer() throws Exception {
        String name = InProcessServerBuilder.generateName();

        var service =
            new com.acme.catalog.server.current.CatalogServiceGrpc
                .CatalogServiceImplBase() {
                @Override
                public void getProduct(
                    com.acme.catalog.server.current.GetProductRequest request,
                    StreamObserver<
                        com.acme.catalog.server.current.GetProductResponse>
                            observer) {
                    observer.onNext(
                        com.acme.catalog.server.current.GetProductResponse
                            .newBuilder()
                            .setProductId(request.getProductId())
                            .setName("Keyboard")
                            .setDisplayName("Bàn phím")
                            .build());
                    observer.onCompleted();
                }
            };

        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(service)
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

        try {
            var oldStub =
                com.acme.catalog.client.v1.CatalogServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(1, TimeUnit.SECONDS);

            var response = oldStub.getProduct(
                com.acme.catalog.client.v1.GetProductRequest.newBuilder()
                    .setProductId("p-42")
                    .build());

            assertEquals("p-42", response.getProductId());
            assertEquals("Keyboard", response.getName());
            // Client v1 không có getter display_name; field mới được xem là unknown.
            assertTrue(response.getUnknownFields().asMap().containsKey(3));
        } finally {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }
}
~~~

Test chứng minh response mới vẫn được client cũ parse: field cũ giữ nguyên tag và kiểu; field mới được giữ như unknown field trong Protobuf Java. Ứng dụng cũ có thể không sử dụng field mới, nhưng vẫn đọc được dữ liệu cần thiết.

## 6. Contract test: client mới gọi server cũ

Server cũ không biết locale và display_name. Client mới phải chấp nhận response không có field mới:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class NewClientOldServerContractTest {

    @Test
    void newClientAcceptsResponseFromOldServer() throws Exception {
        String name = InProcessServerBuilder.generateName();

        var legacyService =
            new com.acme.catalog.client.v1.CatalogServiceGrpc
                .CatalogServiceImplBase() {
                @Override
                public void getProduct(
                    com.acme.catalog.client.v1.GetProductRequest request,
                    StreamObserver<
                        com.acme.catalog.client.v1.GetProductResponse>
                            observer) {
                    observer.onNext(
                        com.acme.catalog.client.v1.GetProductResponse
                            .newBuilder()
                            .setProductId(request.getProductId())
                            .setName("Keyboard")
                            .build());
                    observer.onCompleted();
                }
            };

        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(legacyService)
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

        try {
            var currentStub =
                com.acme.catalog.server.current.CatalogServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(1, TimeUnit.SECONDS);

            var response = currentStub.getProduct(
                com.acme.catalog.server.current.GetProductRequest.newBuilder()
                    .setProductId("p-42")
                    .setLocale("vi-VN")
                    .build());

            assertEquals("p-42", response.getProductId());
            assertEquals("Keyboard", response.getName());
            assertFalse(response.hasDisplayName());
            assertEquals("", response.getDisplayName());
        } finally {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }
}
~~~

Server cũ bỏ qua field locale không nhận diện và trả response không có tag 3. Client mới phải có fallback hợp lý khi display_name không có mặt. Dùng optional nếu ứng dụng cần phân biệt field vắng mặt và giá trị mặc định; với field không có presence, giá trị mặc định có thể không phân biệt được hai tình huống.

Hai test trên dùng in-process transport để kiểm tra protobuf serialization, gRPC method path và generated stub. Nếu fixture cũ và mới được build trong module khác nhau, có thể chạy cùng contract test qua loopback Netty để xác minh transport thật và dependency artifact đã publish.

## 7. Enum, oneof và field presence

Thêm enum value là thay đổi thường có thể tương thích wire, nhưng client cũ phải xử lý giá trị không nhận diện:

~~~proto
enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;
  // Phiên bản mới thêm:
  PRODUCT_STATE_PENDING_REVIEW = 3;
}
~~~

Java client cũ có thể nhận enum numeric chưa biết dưới dạng UNRECOGNIZED. Không viết switch giả định chỉ có các giá trị đã biết mà không có nhánh fallback. Nếu enum là dữ liệu lưu trữ lâu dài, giữ nguyên numeric value và không tái sử dụng giá trị đã xóa.

Với oneof, chỉ một member có thể hiện diện tại một thời điểm. Thêm member mới có thể khiến client cũ không nhận ra lựa chọn mới; client cần xử lý trường hợp getChoiceCase() là CHOICE_NOT_SET hoặc unknown field. Không chuyển field đang tồn tại vào/ra oneof một cách âm thầm vì semantics presence thay đổi.

Với proto3 scalar, dùng optional khi cần phân biệt field vắng mặt và giá trị mặc định. Contract test phải kiểm tra cả hasField() và getter value nếu business logic phụ thuộc presence.

## 8. Kiểm tra schema breaking trong CI

Runtime contract test chứng minh các cặp client/server thực tế. Bổ sung schema diff để phát hiện breaking change trước khi compile hoặc deploy. Buf có thể so sánh schema hiện tại với baseline đã phát hành:

~~~bash
buf lint proto
buf breaking proto --against '.git#branch=main'
~~~

Lệnh buf breaking dùng cấu hình breaking rules của repository và schema trên branch baseline. CI nên pin phiên bản Buf, kiểm tra đúng thư mục module và bảo đảm baseline là contract đã phát hành, không chỉ là một commit tùy ý.

Schema check không thay thế integration contract test: nó không chứng minh Spring wiring, interceptor, authorization, status mapping, TLS, proxy trailers hoặc semantics nghiệp vụ.

## 9. Version hóa gRPC service path

Khi cần breaking change thật sự, tạo package version mới:

~~~proto
package acme.catalog.v2;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
~~~

Method path v2 trở thành:

~~~text
/acme.catalog.v2.CatalogService/GetProduct
~~~

Server có thể đăng ký đồng thời service v1 và v2 trong giai đoạn chuyển đổi. Client nâng cấp theo từng đợt; theo dõi traffic v1 và chỉ ngừng v1 khi không còn consumer hợp lệ. Không tái sử dụng tên v1 cho schema có semantics không tương thích.

## 10. Error detail cũng là một phần contract

Nếu API dùng google.rpc.Status và Any để trả rich error, versioning test cần kiểm tra:

- Status code giữ đúng semantics qua phiên bản.
- Type URL của detail vẫn ổn định nếu detail type được giữ lại.
- Field number trong detail message không bị đổi hoặc tái sử dụng.
- Client cũ bỏ qua detail type mới và vẫn xử lý status cơ bản.
- Thêm field optional vào detail không làm client cũ lỗi khi parse.

Đổi proto package hoặc tên message của detail có thể đổi type URL trong Any; client cũ có thể không unpack được. Khi cần đổi detail schema, giữ type cũ trong thời gian tương thích hoặc phát hành type/version mới và duy trì fallback status.

## 11. Ma trận versioning contract test

| Client | Server | Kiểm tra chính |
| --- | --- | --- |
| v1 | v1 | Baseline contract và semantics hiện tại |
| v1 | mới/additive | Client cũ parse response mới, bỏ qua field mới |
| mới/additive | v1 | Client mới chấp nhận field response vắng mặt |
| v1 | breaking v2 | Không giả định tương thích; v1 path phải còn được phục vụ hoặc migration được công bố |
| mới | mới | Field presence, enum, oneof và error detail semantics |
| Client cũ | Server có detail mới | Fallback status khi detail type không biết |

Ngoài status và response, kiểm tra deadline, metadata, authentication/authorization và behavior của retry nếu chúng thuộc contract công khai của RPC.

## 12. Ghi nhớ và tự kiểm tra

**Versioning contract test** xác minh client và server ở các phiên bản khác nhau vẫn tuân thủ cùng wire contract. Giữ nguyên proto package, service/method path, field number và semantics của field cũ; thêm field mới theo hướng additive, reserve tag đã xóa và xử lý enum/detail type chưa biết. Dùng test hai chiều old-client/new-server và new-client/old-server, kết hợp schema breaking check trong CI.

Tự kiểm tra:

1. java_package khác package Protobuf như thế nào đối với gRPC method path?
2. Vì sao không được tái sử dụng field number đã xóa?
3. Hai chiều old-client/new-server và new-client/old-server phát hiện hai nhóm lỗi nào?
4. Vì sao thêm enum value vẫn cần client fallback?
5. Khi nào nên tạo package v2 thay vì sửa v1?
6. Vì sao Buf breaking check không thay thế contract test qua generated stub?

Versioning contract test giúp Spring gRPC triển khai rolling upgrade an toàn, phát hiện thay đổi phá vỡ wire/API contract và giữ client/server tương thích trong suốt quá trình nâng cấp.
