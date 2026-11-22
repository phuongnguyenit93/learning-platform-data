# Giới hạn service reflection

gRPC Server Reflection là giao thức cho phép client khám phá những service và Protobuf descriptor mà server công bố. Công cụ như grpcurl, grpcui và một số IDE dùng reflection để liệt kê service, xem method/request/response schema và gọi thử RPC mà không cần người dùng cung cấp trước file proto. Khả năng này hữu ích khi phát triển, debug và vận hành, nhưng cũng làm lộ cấu trúc API nội bộ cho bất kỳ peer nào truy cập được reflection endpoint.

Trong Spring gRPC, cần quyết định rõ reflection có được bật ở môi trường nào, ai được phép truy cập và descriptor nào được công bố. Chỉ lọc danh sách service là chưa đủ để giới hạn schema: reflection còn hỗ trợ truy vấn descriptor theo symbol, tên file và extension. Với API nhạy cảm, ưu tiên tắt reflection ở production hoặc cô lập trên listener quản trị riêng, bảo vệ bằng mTLS và authorization.

## 1. Service Reflection cung cấp thông tin gì?

Server Reflection cho client khám phá API qua một RPC streaming. Protocol có các phiên bản phổ biến như v1 và v1alpha; client/tool cần dùng phiên bản mà server hỗ trợ.

Thông tin reflection có thể trả về gồm:

- Danh sách service được server đăng ký.
- Tên đầy đủ của service và method.
- Request/response message type của từng method.
- Protobuf file descriptor chứa message, field, enum, service, method và import dependency.
- Extension metadata mà descriptor công bố.

Descriptor giúp client biết cấu trúc message, field number, type, cardinality, enum value và method signature. Điều này không trực tiếp cung cấp dữ liệu runtime hoặc bỏ qua authorization của business RPC, nhưng giúp attacker hiểu bề mặt API, tên tài nguyên, quy ước nội bộ và các method cần thử.

Không mặc định rằng proto schema là bí mật tuyệt đối. Tuy vậy, nếu schema chứa thông tin nội bộ hoặc API chưa công bố, cần xem reflection là một endpoint quản trị và áp dụng access control tương xứng.

## 2. Reflection hoạt động như một RPC riêng

Trong grpc-java, reflection thường được cung cấp bởi ProtoReflectionService thuộc artifact grpc-services. Client gửi các request reflection trên một bidirectional-streaming method:

```text
grpcurl / grpcui
      |
      | ServerReflectionInfo stream
      v
gRPC server listener
      |
      v
Reflection access interceptor
      |
      v
ProtoReflectionService
      |
      +--> list services
      +--> file containing symbol
      +--> file by filename
      +--> extension queries
      |
      v
FileDescriptorProto responses
```

Full method name thường gặp:

- grpc.reflection.v1.ServerReflection/ServerReflectionInfo
- grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo

Đây là method reflection, không phải một business method như OrderService/GetOrder. Vì reflection dùng stream, một client có thể gửi nhiều loại descriptor query trong cùng một RPC. Access control cần áp dụng cho toàn stream; nếu policy lọc theo từng request descriptor thì phải kiểm tra từng message trong stream.

## 3. Rủi ro khi bật reflection rộng rãi

Reflection có thể giúp người ngoài:

- Liệt kê service nội bộ và các method không xuất hiện trong tài liệu công khai.
- Khám phá request/response schema và field names.
- Phát hiện method quản trị, debug hoặc API cũ còn được đăng ký.
- Tìm các message/enum/extension liên quan đến quy trình nghiệp vụ.
- Tạo request hợp lệ về mặt cấu trúc để thử các lỗi authorization hoặc validation.

Reflection tự nó không cấp quyền gọi business RPC. Mỗi method vẫn cần authentication và authorization độc lập. Tuy nhiên, schema discovery làm giảm chi phí reconnaissance và giúp attacker nhắm đúng method hoặc payload.

Không nên dựa vào việc giấu tên service như một biện pháp bảo mật. Bảo vệ thực sự phải nằm ở authentication, authorization, network boundary và việc không đăng ký service không cần thiết.

## 4. Chính sách theo môi trường

Một chính sách mặc định thực tế:

| Môi trường | Chính sách reflection | Mục đích |
| --- | --- | --- |
| Local development | Có thể bật | Hỗ trợ grpcurl/grpcui và debug |
| Automated test | Bật trong test server cô lập | Kiểm tra descriptor và client tooling |
| Shared development | Bật có kiểm soát | Chỉ developer/workload được xác thực |
| Staging | Tắt mặc định hoặc giới hạn như production | Tránh staging trở thành nguồn lộ schema |
| Production | Tắt trên listener public; nếu cần thì chỉ mở trên admin boundary | Giảm bề mặt khám phá API |

Không dùng một cấu hình reflection bật cho mọi profile rồi hy vọng network firewall sẽ luôn chặn đúng. Cấu hình theo profile/deployment phải được kiểm thử để bảo đảm production artifact không vô tình đăng ký reflection.

Nếu production support cần reflection tạm thời, nên có change approval, thời hạn tự hết hiệu lực, danh tính operator được xác minh, audit truy cập và kế hoạch tắt lại sau phiên xử lý.

## 5. Đăng ký ProtoReflectionService trong grpc-java

Ví dụ grpc-java thêm reflection service vào server:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;

Server server = ServerBuilder.forPort(9090)
    .addService(new OrdersService())
    .addService(ProtoReflectionService.newInstance())
    .build()
    .start();
```

Artifact chứa ProtoReflectionService là grpc-services và version phải đồng bộ với grpc-java core. Ví dụ này minh họa server thuần; trong Spring gRPC, đăng ký service qua extension point mà starter đang dùng hỗ trợ.

Không đăng ký reflection service ở production chỉ để tiện chạy grpcurl. Nếu cần reflection trong production support, đặt nó trên server/listener quản trị riêng hoặc bọc service bằng interceptor yêu cầu operator identity.

## 6. Bảo vệ reflection bằng server interceptor

Có thể bọc reflection service với ServerInterceptor để chỉ cho phép caller đã được xác thực và có role vận hành:

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.ServerServiceDefinition;
import io.grpc.ServerInterceptors;
import io.grpc.Status;

final class ReflectionAccessInterceptor implements ServerInterceptor {
    private final ReflectionAuthorizer authorizer;

    ReflectionAccessInterceptor(ReflectionAuthorizer authorizer) {
        this.authorizer = authorizer;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        boolean allowed =
            authorizer.isOperator(headers, call.getAttributes());
        if (!allowed) {
            call.close(
                Status.PERMISSION_DENIED
                    .withDescription("reflection access denied"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }
        return next.startCall(call, headers);
    }
}

ServerServiceDefinition protectedReflection =
    ServerInterceptors.intercept(
        ProtoReflectionService.newInstance(),
        new ReflectionAccessInterceptor(reflectionAuthorizer));

Server server = ServerBuilder.forPort(9090)
    .addService(new OrdersService())
    .addService(protectedReflection)
    .build()
    .start();
```

ReflectionAuthorizer là abstraction của ứng dụng: nó phải xác minh credential hoặc peer identity đã được xác thực, rồi kiểm tra role/policy vận hành. Không tin một header như x-operator: true do caller tự gửi. Với mTLS, có thể liên kết certificate identity từ transport với danh tính operator, nhưng certificate hợp lệ không tự động có nghĩa caller được phép đọc schema.

Ví dụ chặn cả reflection stream khi caller không có quyền. Nó không lọc từng descriptor; caller được phép mở stream có thể gửi các loại reflection query mà implementation hỗ trợ. Nếu cần giới hạn symbol/file cụ thể, cần một reflection implementation/filter có kiểm soát đầy đủ request và response.

## 7. Vì sao chỉ allowlist list_services là chưa đủ?

Reflection protocol không chỉ có request liệt kê service. Các truy vấn quan trọng gồm:

| Loại request | Mục đích |
| --- | --- |
| list_services | Liệt kê service đã đăng ký |
| file_containing_symbol | Lấy descriptor file chứa một symbol |
| file_by_filename | Lấy descriptor theo tên file |
| all_extension_numbers_of_type | Liệt kê extension number của một message type |
| file_containing_extension | Tìm descriptor chứa extension |

Nếu custom filter chỉ xóa service khỏi response list_services, client vẫn có thể hỏi file_containing_symbol hoặc file_by_filename để lấy descriptor. Hơn nữa, một file proto có thể định nghĩa nhiều service/message; cho phép một service có thể vô tình làm lộ các symbol khác cùng file.

Descriptor file còn có thể tham chiếu dependency. Khi trả descriptor cho một symbol, reflection thường cần cung cấp các file dependency để client giải mã schema. Do đó, allowlist theo service name không tự động tương đương allowlist theo descriptor graph.

Nếu phải công bố một tập schema giới hạn, cần kiểm soát mọi request type, symbol, filename, extension query và dependency closure; kiểm tra cả nội dung response. Cách đơn giản và an toàn hơn thường là tách proto nhạy cảm sang file/package riêng hoặc dùng listener riêng chỉ đăng ký các service cần công bố.

## 8. Tách listener quản trị và listener nghiệp vụ

Khi operator cần reflection trong production, tách endpoint quản trị giúp giảm khả năng truy cập từ client thông thường:

```text
Public gRPC listener
  - business services
  - normal authentication/authorization
  - reflection disabled

Private admin listener
  - reflection service
  - mTLS required
  - operator authorization
  - network ACL / VPN / bastion
  - access audit and short-lived enablement
```

Listener quản trị nên có port, firewall rule, DNS/service discovery và certificate riêng. Không expose admin listener qua public ingress. Giới hạn nguồn truy cập ở network layer, sau đó vẫn xác thực và phân quyền ở gRPC layer; network ACL không thay thế identity.

Nếu dùng service mesh hoặc ingress terminate TLS, xác định rõ nơi mTLS được kết thúc và identity nào được chuyển tiếp. Service chỉ tin forwarded identity khi hop proxy-to-service được xác thực và caller bên ngoài không thể giả mạo header.

## 9. Giới hạn reflection theo role và method

Có thể dùng role như SCHEMA_READ hoặc PLATFORM_OPERATOR thay vì cấp reflection cho mọi authenticated workload. Policy cần trả lời:

- Role nào được liệt kê service?
- Role nào được lấy descriptor?
- Có service nào tuyệt đối không được công bố?
- Có cần giới hạn theo environment/tenant không?
- Quyền có thời hạn không và ai phê duyệt?
- Truy cập reflection có tạo audit event không?

Vì Reflection là một bidi stream, interceptor authorization ở cấp call chỉ quyết định caller được mở stream hay không. Nếu cần policy khác nhau cho từng descriptor query trong cùng stream, cần wrapper/filter xử lý từng request message; không thể chỉ kiểm tra một lần ở interceptCall rồi tuyên bố đã enforce symbol-level allowlist.

Đừng trả descriptor một phần theo cách khiến dependency graph không hợp lệ. Nếu response bị lọc, client có thể không resolve được type và tooling sẽ báo schema không đầy đủ. Test bằng client/tool thật với toàn bộ query path dự kiến.

## 10. Cấu hình reflection trong Spring gRPC

Trong Spring, cách đăng ký BindableService hoặc ServerServiceDefinition phụ thuộc starter và phiên bản. Có starter tự phát hiện service bean, có starter yêu cầu server customizer hoặc registration hook. Vì vậy:

1. Xác định đúng extension point đăng ký service của starter đang dùng.
2. Đặt điều kiện theo profile/property để reflection chỉ được đăng ký trong môi trường cho phép.
3. Nếu dùng interceptor, xác minh interceptor thực sự bao quanh reflection service, không chỉ được khai báo thành bean.
4. Kiểm tra server listener thực tế có reflection service hay không bằng probe từ môi trường test.
5. Bảo đảm profile production không vô tình bật cấu hình local/test.

Không giả định bean implement BindableService tự động được đăng ký bởi mọi Spring gRPC starter. Cũng không giả định global interceptor áp dụng như nhau cho business services và reflection service; xác minh chain thực tế.

Nếu listener quản trị là server riêng, quản lý lifecycle, TLS material, health/readiness và shutdown riêng. Không tái sử dụng public channel chỉ vì cấu hình thuận tiện.

## 11. Kiểm thử bằng grpcurl và integration test

grpcurl có thể kiểm tra reflection bằng cách liệt kê service và mô tả descriptor:

```bash
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe acme.orders.v1.OrderService
```

Hai lệnh này chỉ dành cho local/test không TLS. Với TLS, cung cấp CA và target hostname phù hợp; với mTLS, thêm client certificate/key theo cấu hình công cụ. Không tắt certificate verification để làm test pass.

Ma trận test:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Reflection tắt | Client không thể list/describe qua reflection |
| Operator hợp lệ | Chỉ truy cập listener/descriptor được policy cho phép |
| Không có credential | Bị từ chối trước khi nhận descriptor |
| Identity hợp lệ nhưng thiếu role | PERMISSION_DENIED |
| Request descriptor ngoài allowlist | Bị từ chối hoặc không được trả theo policy |
| Query file chứa nhiều symbol | Không lộ symbol ngoài phạm vi được phép |
| Descriptor dependency | Chỉ trả dependency cần thiết, không mở rộng ngoài policy |
| v1 và v1alpha | Chỉ expose phiên bản đã được phê duyệt |
| Production profile | Reflection không đăng ký trên listener public |
| Admin listener | Chỉ reachable từ network/operator identity được phép |
| Audit | Có event cho truy cập allow/deny |

Ngoài grpcurl, nên có integration test dùng reflection client generated hoặc công cụ tương đương để gửi từng request type, đặc biệt khi custom filter descriptor. Test chỉ chạy list_services sẽ không chứng minh file_by_filename hay file_containing_symbol đã được giới hạn.

## 12. Giám sát và quy trình bật tạm thời

Theo dõi:

- Số reflection stream được mở theo identity và nguồn mạng.
- Các method/query loại reflection được yêu cầu.
- Số lần bị từ chối và lỗi TLS/authentication.
- Listener/admin endpoint có xuất hiện trên public ingress hay không.
- Thời điểm reflection được bật/tắt và người phê duyệt.

Khi cần bật reflection tạm thời:

1. Tạo change/incident record và xác định operator.
2. Cấp quyền ngắn hạn qua mTLS/role.
3. Chỉ mở admin listener hoặc policy đã giới hạn.
4. Ghi audit cho mỗi stream và các query cần thiết.
5. Tắt reflection hoặc thu hồi quyền khi hết thời gian.
6. Xác minh từ bên ngoài rằng endpoint không còn truy cập được.

Không dựa vào việc operator đóng grpcurl để coi stream đã kết thúc; server cần có idle/maximum stream duration phù hợp và quan sát cancellation.

## 13. Bài tập vận dụng

OrderService và PaymentService chạy trên cùng Spring gRPC server. Schema Payment chứa method quản trị nội bộ; đội vận hành cần dùng grpcurl để debug OrderService ở staging và thỉnh thoảng trong production.

**Yêu cầu:**

1. Định nghĩa môi trường nào được bật reflection và listener nào được expose.
2. Đăng ký ProtoReflectionService theo extension point của starter.
3. Bảo vệ reflection bằng mTLS và role SCHEMA_READ.
4. Viết test chứng minh unauthenticated và authenticated-without-role bị từ chối.
5. Kiểm tra list_services, file_containing_symbol và file_by_filename.
6. Đánh giá nguy cơ OrderService và PaymentService cùng nằm trong một proto file.
7. Nếu cần giới hạn descriptor, thiết kế allowlist bao gồm dependency closure và mọi request type.
8. Viết Spring context test cho registration/interceptor chain và grpcurl test cho staging/admin listener.
9. Tạo quy trình bật tạm thời, audit và tự tắt reflection sau phiên debug.

**Câu hỏi tự kiểm tra:**

- Reflection cung cấp những loại descriptor/schema nào?
- Vì sao reflection không trực tiếp cấp quyền gọi business RPC nhưng vẫn làm tăng rủi ro?
- Full method name của ServerReflectionInfo là gì?
- Vì sao allowlist list_services không đủ?
- file_containing_symbol và file_by_filename có thể làm lộ gì?
- Vì sao descriptor dependency closure cần được xét khi lọc schema?
- Khi nào nên dùng listener quản trị riêng?
- mTLS có thay thế role authorization không?
- Vì sao phải test cả reflection v1 và v1alpha nếu server expose cả hai?
- Làm thế nào xác minh Spring starter thật sự đăng ký interceptor cho reflection service?

**Ghi nhớ:** Reflection là công cụ khám phá schema, không phải cơ chế authorization cho business RPC. Tắt mặc định trên production listener; nếu cần vận hành, cô lập trên admin boundary, yêu cầu mTLS và role phù hợp, audit truy cập. Allowlist phải kiểm soát mọi loại descriptor query và dependency graph; lọc riêng danh sách service không đủ. Kiểm thử bằng grpcurl/client reflection và xác minh cấu hình Spring thực tế theo từng profile.
