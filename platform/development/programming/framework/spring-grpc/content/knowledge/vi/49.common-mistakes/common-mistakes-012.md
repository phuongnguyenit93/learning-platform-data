# Mock mọi thứ và bỏ qua contract

Trong dịch vụ `SPRING_GRPC`, Protocol Buffers (`.proto`) định nghĩa hợp đồng giữa client và server. Từ hợp đồng này, hệ thống sinh message Java, service base class và client stub để thực hiện unary hoặc streaming RPC. Nếu bài kiểm thử chỉ dùng Mockito để thay mọi thành phần bằng mock, các bài kiểm thử có thể xanh trong khi client và server vẫn không giao tiếp được khi chạy thật.

Mock rất hữu ích để kiểm tra một đơn vị có gọi dependency đúng cách hay không. Vấn đề xuất hiện khi mock thay luôn ranh giới gRPC: bài kiểm thử không còn kiểm tra service name, method path, serialization, metadata, deadline, status, interceptor, streaming hay cấu hình Spring. Những phần đó chính là contract mà các tiến trình độc lập phải tuân thủ.

Mục tiêu là chọn đúng ranh giới cho từng loại kiểm thử: mock dependency ở unit test, nhưng dùng generated client và gRPC server thật ở contract/integration test. Nhờ vậy, kiểm thử vừa nhanh ở tầng nghiệp vụ vừa phát hiện được lỗi giao tiếp trước khi triển khai.

## 1. Contract của một dịch vụ gRPC gồm những gì?

Contract không chỉ là chữ ký của một method Java. Nó bao gồm nhiều phần mà client và server phải thống nhất:

| Thành phần | Nội dung cần tương thích | Lỗi có thể gặp nếu bỏ qua |
|---|---|---|
| Service và method | `package`, tên service, tên method và đường dẫn RPC đầy đủ. | Client gọi nhầm endpoint hoặc nhận `UNIMPLEMENTED`. |
| Kiểu RPC | Unary, server streaming, client streaming hay bidirectional streaming. | Client và server không thống nhất cách gửi/nhận message hoặc thời điểm kết thúc call. |
| Message protobuf | Field number, wire type, kiểu dữ liệu, enum number, `oneof` và presence. | Dữ liệu bị hiểu sai, mất thông tin hoặc không tương thích giữa phiên bản. |
| Metadata | Header, trailer, authentication token, correlation ID và quy ước metadata riêng. | Request thật bị từ chối dù test gọi trực tiếp service thành công. |
| Deadline và cancellation | Thời hạn xử lý, cách truyền deadline và phản ứng khi client hủy RPC. | Request chờ quá lâu hoặc công việc nền vẫn chạy sau khi client đã bỏ cuộc. |
| Status | Ánh xạ lỗi nghiệp vụ và lỗi hệ thống sang gRPC status. | Client không phân biệt được lỗi đầu vào, không tìm thấy dữ liệu và lỗi tạm thời. |
| Interceptor và transport | Logging, tracing, auth, compression, TLS và cấu hình HTTP/2. | Test bỏ qua cấu hình bảo mật hoặc lỗi kết nối thực tế. |

Tên service và method tạo nên đường dẫn RPC theo dạng `/fully.qualified.Service/Method`. Vì vậy, thay đổi package protobuf, tên service hoặc tên method có thể khiến client cũ không còn gọi được server mới, ngay cả khi Java code nhìn qua vẫn có vẻ tương tự.

File `.proto` là nguồn hợp đồng. Các class Java được sinh ra là biểu diễn phục vụ code Java; không nên sửa tay file sinh mã để che một khác biệt giữa client và server. Khi contract thay đổi, cập nhật `.proto`, sinh lại mã bằng cấu hình code generator thống nhất và đánh giá khả năng tương thích trước khi phát hành.

## 2. Vì sao mock quá nhiều làm kiểm thử mất giá trị?

### 2.1. Mock generated stub chỉ kiểm tra cách gọi method

Ví dụ một client gọi dịch vụ đơn hàng:

```java
OrderServiceGrpc.OrderServiceBlockingStub stub = mock(
        OrderServiceGrpc.OrderServiceBlockingStub.class);

when(stub.getOrder(any(GetOrderRequest.class)))
        .thenReturn(GetOrderResponse.newBuilder()
                .setOrderId("order-42")
                .build());

OrderView result = orderClient.getOrder("order-42");

assertEquals("order-42", result.id());
verify(stub).getOrder(any(GetOrderRequest.class));
```

Đây có thể là unit test hợp lệ cho logic của `orderClient`: nó kiểm tra client adapter xử lý response được trả về như thế nào. Tuy nhiên, không có RPC nào được gửi qua channel. Test không kiểm tra server có đăng ký đúng service hay không, request có serialize được không, metadata có được gửi không, TLS có bắt tay thành công không hoặc server có trả đúng status không.

Nếu dùng test này làm bằng chứng rằng client và server tương thích, phạm vi kết luận đã vượt quá những gì test thực sự xác nhận.

### 2.2. Mock service implementation bỏ qua server runtime

Một test gọi trực tiếp method Java của implementation có thể kiểm tra logic chuyển đổi request/response. Nhưng nó không chạy qua gRPC server, generated method descriptor, interceptor chain, marshaller và transport. Một lỗi đăng ký service hoặc interceptor có thể không xuất hiện trong test gọi trực tiếp.

### 2.3. Mock làm mất khác biệt giữa Java object và protobuf message trên đường truyền

Khi gọi RPC thật, message được serialize và deserialize theo protobuf. Giá trị mặc định, field presence, enum number, field number và các field chưa biết đều có quy tắc riêng. Mock trả về một object Java đã tạo sẵn nên không xác nhận hai phía đang dùng schema tương thích.

Ví dụ, nếu nghiệp vụ cần phân biệt “người dùng không gửi field” với “người dùng gửi giá trị rỗng”, chỉ kiểm tra getter có thể không đủ. Hãy chọn kiểu field và presence phù hợp trong `.proto` rồi kiểm tra hành vi serialize/deserialize bằng test contract.

### 2.4. Metadata, deadline và status bị bỏ qua

Mock stub thường không tự chạy client interceptor hoặc server interceptor. Test có thể không phát hiện token bị thiếu, metadata sai key, deadline không được truyền, exception bị ánh xạ thành `UNKNOWN` hoặc lỗi nghiệp vụ bị trả nhầm `INTERNAL`.

Tương tự, test gọi thẳng method implementation không kiểm tra status cuối cùng mà client nhận. Client thường dựa vào `Status.Code` để quyết định hiển thị lỗi, retry hay dừng request; do đó cần xác nhận status qua generated stub.

### 2.5. Streaming bị rút gọn thành một lần gọi method

Streaming có vòng đời riêng: message có thể đến nhiều lần, client có thể half-close luồng gửi, server có thể hoàn tất bằng trailer, và một phía có thể hủy RPC. Mock một method trả về danh sách hoặc một response không mô phỏng đầy đủ các hành vi này.

Nếu hệ thống dùng streaming, cần test thứ tự message, kết thúc stream, lỗi giữa stream, cancellation và giải phóng tài nguyên. Với stream dài hạn, cũng cần kiểm tra deadline và khả năng reconnect theo giao thức ứng dụng.

## 3. Chọn đúng loại test và đúng chỗ đặt mock

Không cần cấm mock. Cần đặt mock ở ranh giới phù hợp với câu hỏi mà bài kiểm thử muốn trả lời.

| Loại kiểm thử | Nên dùng gì? | Xác nhận được điều gì? |
|---|---|---|
| Unit test nghiệp vụ | Mock repository, clock, external API hoặc dependency chậm. | Quy tắc nghiệp vụ, nhánh lỗi và cách xử lý kết quả. |
| Unit test client adapter | Có thể mock generated stub. | Mapping giữa API nội bộ và request/response protobuf, xử lý response ở phía client. |
| Test gRPC service/contract | Generated client stub thật gọi implementation thật qua gRPC server thật; có thể mock dependency nghiệp vụ bên dưới. | Đăng ký service, method descriptor, message, status và hành vi RPC ở ranh giới gRPC. |
| Spring integration test | Khởi tạo Spring context, bean thật, interceptor thật và server trên cổng kiểm thử. | Wiring, component scan, cấu hình starter, lifecycle và cấu hình ứng dụng. |
| Transport/security test | Kết nối qua TCP/HTTP2 với TLS và metadata auth được cấu hình như môi trường chạy. | Bắt tay TLS, certificate, trust, auth interceptor và lỗi transport. |
| Compatibility test | Client/server sinh từ các phiên bản schema khác nhau trong cửa sổ hỗ trợ. | Khả năng tương thích khi deploy độc lập hoặc nâng cấp từng thành phần. |

Một nguyên tắc hữu ích: mock dependency nằm bên trong ranh giới đang kiểm tra, nhưng giữ thật những thành phần tạo nên chính ranh giới đó. Khi kiểm tra gRPC contract, hãy giữ generated stub, gRPC server và implementation thật; có thể mock repository hoặc application service để test ổn định và tập trung.

## 4. Ví dụ: kiểm tra contract bằng generated client và server thật

Giả sử service cung cấp thao tác đọc đơn hàng. Hợp đồng protobuf có thể được khai báo như sau:

```protobuf
syntax = "proto3";

package shop.orders.v1;

option java_package = "com.example.orders.v1";
option java_multiple_files = true;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  OrderState state = 2;
}

enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_PAID = 2;
}
```

Server implementation dùng generated base class và chuyển kết quả từ application service thành protobuf response. Ví dụ rút gọn:

```java
public final class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderQuery orderQuery;

    public OrderGrpcService(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {
        try {
            OrderView order = orderQuery.findById(request.getOrderId());

            GetOrderResponse response = GetOrderResponse.newBuilder()
                    .setOrderId(order.id())
                    .setState(toProtoState(order.state()))
                    .build();

            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (OrderNotFoundException ex) {
            responseObserver.onError(Status.NOT_FOUND
                    .withDescription("Order not found")
                    .asRuntimeException());
        }
    }

    private static OrderState toProtoState(OrderStatus state) {
        return switch (state) {
            case PENDING -> OrderState.ORDER_STATE_PENDING;
            case PAID -> OrderState.ORDER_STATE_PAID;
        };
    }
}
```

`OrderQuery`, `OrderView` và `OrderNotFoundException` đại diện cho kiểu ở tầng ứng dụng. Phần chuyển đổi enum trong dự án cần ánh xạ rõ ràng giữa domain state và protobuf enum; không nên dựa vào thứ tự enum Java nếu hai phía có thể thay đổi độc lập.

Test dưới đây dùng `InProcessServerBuilder` và `InProcessChannelBuilder` của grpc-java. Nó chạy implementation thật qua generated blocking stub; chỉ dependency nghiệp vụ được mock:

```java
class OrderGrpcContractTest {

    private Server server;
    private ManagedChannel channel;
    private OrderQuery orderQuery;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        orderQuery = mock(OrderQuery.class);

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrderGrpcService(orderQuery))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void tearDown() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }

    @Test
    void callsGeneratedContractAndMapsResponse() {
        when(orderQuery.findById("order-42"))
                .thenReturn(new OrderView("order-42", OrderStatus.PAID));

        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId("order-42")
                .build();

        GetOrderResponse response = OrderServiceGrpc
                .newBlockingStub(channel)
                .getOrder(request);

        assertEquals("order-42", response.getOrderId());
        assertEquals(OrderState.ORDER_STATE_PAID, response.getState());
        verify(orderQuery).findById("order-42");
    }

    @Test
    void mapsMissingOrderToNotFoundStatus() {
        when(orderQuery.findById("missing"))
                .thenThrow(new OrderNotFoundException());

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> OrderServiceGrpc.newBlockingStub(channel)
                        .getOrder(GetOrderRequest.newBuilder()
                                .setOrderId("missing")
                                .build()));

        assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
    }
}
```

Ví dụ giả định dự án có dependency `grpc-inprocess` tương thích với phiên bản grpc-java đang dùng, cùng JUnit 5, Mockito và các kiểu domain được khai báo như trên. `directExecutor()` phù hợp cho ví dụ nhỏ, đồng bộ; không nên dùng nó để kết luận về hành vi executor hoặc hiệu năng production.

In-process transport giúp test RPC qua generated stub và server mà không cần mở socket. Nó không thay thế test TCP/HTTP2, TLS, certificate, load balancer hoặc cấu hình triển khai. Nếu các yếu tố đó thuộc contract vận hành của dịch vụ, cần có integration test chạy qua transport thực.

## 5. Kiểm tra protobuf compatibility khi schema thay đổi

Một test gọi RPC thành công với client và server cùng được sinh từ một phiên bản `.proto` chỉ xác nhận hai phía hiện tại khớp nhau. Nó chưa chứng minh client cũ vẫn hoạt động với server mới khi deploy theo từng bước.

Khi cập nhật schema, cần xem xét các quy tắc sau:

- Không đổi số field đã phát hành. Khi xóa field, dùng `reserved` để giữ lại field number và tên đã bỏ; tuyệt đối không tái sử dụng field number cho ý nghĩa khác.
- Thêm field mới theo cách tương thích và hiểu rõ giá trị mặc định của proto3. Nếu nghiệp vụ cần phân biệt field vắng mặt với field mang giá trị mặc định, dùng presence phù hợp, chẳng hạn `optional` hoặc message wrapper theo thiết kế.
- Giữ nguyên numeric value của enum đã phát hành. Khi xóa enum value, reserve số và tên cũ; duy trì giá trị `*_UNSPECIFIED = 0` làm giá trị mặc định có chủ đích.
- Cẩn trọng khi đổi field type, `oneof`, kiểu RPC, request/response message hoặc ý nghĩa nghiệp vụ của field. Một thay đổi có thể biên dịch được nhưng vẫn không tương thích ở wire format hoặc semantics.
- Đổi protobuf package, service name hoặc method name có thể đổi RPC path. Nếu cần thay đổi không tương thích, cân nhắc version package/service, ví dụ `shop.orders.v2`, và lập kế hoạch chuyển đổi client/server.
- Phân biệt `package` trong protobuf với `option java_package`. `package` tham gia tên đầy đủ của service trong contract gRPC; `java_package` quyết định package Java được sinh mã.

Một quy trình phát hành an toàn nên kiểm tra cả schema lẫn hành vi:

1. Chạy code generation từ `.proto` bằng phiên bản compiler/plugin đã khóa trong build.
2. Chạy kiểm tra breaking change cho schema bằng công cụ tương thích mà dự án lựa chọn, nếu có.
3. Chạy integration test với generated client và server của phiên bản hiện tại.
4. Với hệ thống deploy độc lập, chạy ma trận client cũ/server mới và client mới/server cũ trong phạm vi tương thích đã cam kết.
5. Chỉ xóa field hoặc endpoint cũ sau khi các client đã chuyển đổi và thời hạn hỗ trợ phiên bản cũ kết thúc.

Không nên chỉ so sánh generated Java source bằng mắt. Contract protobuf có quy tắc wire compatibility riêng; công cụ kiểm tra schema và test tương thích giữa phiên bản giúp phát hiện thay đổi nguy hiểm sớm hơn.

## 6. Những phần cần test qua Spring context và transport thật

Test in-process ở trên xác nhận đường đi qua gRPC API và generated stub. Nó chưa xác nhận Spring đã lắp đúng toàn bộ ứng dụng. Với một dịch vụ Spring gRPC, nên có một số integration test khởi tạo application context để kiểm tra:

- Bean service được đăng ký vào server và không bị thiếu hoặc đăng ký trùng.
- Interceptor được áp dụng đúng thứ tự, ví dụ auth, logging, tracing và exception mapping.
- Metadata bắt buộc được đọc đúng key và được truyền đến downstream khi cần.
- Deadline được áp dụng và cancellation được chuyển tới công việc nền.
- Spring shutdown đóng server theo lifecycle dự kiến và không đóng dependency trước khi RPC đang chạy hoàn tất.
- Cấu hình port, health check và service discovery khớp với môi trường triển khai.

Đối với TLS, dùng certificate test và kết nối client/server qua TCP. Kiểm tra cả trường hợp thành công lẫn certificate không được tin cậy, hostname không khớp hoặc certificate hết hạn theo phạm vi hệ thống cần hỗ trợ. In-process channel không kiểm tra TLS handshake.

Đối với streaming, dùng client và server thật để kiểm tra nhiều message, thứ tự, half-close, terminal status, cancellation và deadline. Với stream có lưu lượng lớn, bổ sung kiểm thử backpressure và giới hạn tài nguyên. Một test chỉ kiểm tra stream trả về một message không bao phủ các tình huống kết thúc và hủy stream.

## 7. Dấu hiệu nhận biết test đang mock quá sâu

Hãy xem lại chiến lược kiểm thử nếu gặp một trong các dấu hiệu sau:

- Tất cả test đều gọi trực tiếp method Java hoặc mock generated stub; không có test nào khởi động gRPC server.
- Không có test nào dùng request/response class được sinh từ `.proto` qua generated client stub.
- Không có kiểm thử status cho các trường hợp `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAUTHENTICATED`, `PERMISSION_DENIED` hoặc lỗi tạm thời phù hợp với API.
- Test không xác nhận metadata, deadline, interceptor hoặc cancellation dù các phần đó là yêu cầu của dịch vụ.
- Streaming RPC chỉ được kiểm tra bằng một response giả lập.
- Thay đổi `.proto` không kích hoạt code generation, schema compatibility check hoặc integration test.
- Client và server luôn được build cùng lúc, nhưng hệ thống production lại triển khai chúng độc lập mà không có kiểm thử phiên bản chéo.

Khi production xuất hiện `UNIMPLEMENTED`, hãy kiểm tra service/method path và việc đăng ký implementation. Khi xuất hiện `UNAUTHENTICATED` hoặc `PERMISSION_DENIED`, kiểm tra metadata và interceptor. Khi nhận `INVALID_ARGUMENT`, đối chiếu validation và semantics của request. Khi dữ liệu sai hoặc field bị mất, kiểm tra schema, field number, presence và phiên bản generated code. Status chỉ là đầu mối; hãy xác nhận bằng log và contract thực tế.

## 8. Checklist trước khi merge thay đổi gRPC

- [ ] Unit test mock các dependency nghiệp vụ ở đúng ranh giới và kiểm tra các nhánh xử lý cần thiết.
- [ ] Có test dùng generated client stub gọi gRPC server và service implementation thật.
- [ ] Test xác nhận response protobuf và status code cho cả trường hợp thành công lẫn lỗi.
- [ ] Metadata, deadline, cancellation và interceptor được kiểm tra nếu thuộc contract của method.
- [ ] Mỗi kiểu streaming đang được sử dụng có test vòng đời stream và lỗi kết thúc.
- [ ] Thay đổi `.proto` đã được đánh giá về field number, enum number, presence, RPC path và wire compatibility.
- [ ] Spring integration test xác nhận bean registration, cấu hình server và lifecycle.
- [ ] TLS/transport test được chạy khi thay đổi liên quan đến certificate, channel hoặc cấu hình bảo mật.
- [ ] Nếu client/server deploy độc lập, đã kiểm tra tương thích giữa các phiên bản trong cửa sổ hỗ trợ.

Mock giúp unit test tập trung và ít phụ thuộc môi trường. Nhưng contract gRPC chỉ được kiểm chứng khi request đi qua generated client, server và các lớp giao tiếp mà production thực sự sử dụng. Hãy giữ mock ở dependency bên trong, bổ sung test contract và integration theo đúng ranh giới; khi đó bộ kiểm thử mới có thể phát hiện lỗi mà một bộ mock hoàn toàn không nhìn thấy.
