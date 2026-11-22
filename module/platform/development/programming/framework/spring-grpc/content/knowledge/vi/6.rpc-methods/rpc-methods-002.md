# Định nghĩa server streaming RPC trong Spring gRPC

Trong một dịch vụ **Spring gRPC**, **server streaming RPC** cho phép client gửi **một thông điệp yêu cầu**, sau đó server gửi về **một luồng gồm không, một hoặc nhiều thông điệp phản hồi**. Các thông điệp được truyền tuần tự trong cùng một RPC qua gRPC/HTTP/2, và server báo kết thúc bằng trạng thái thành công hoặc lỗi. Hợp đồng được định nghĩa bằng **Protocol Buffers (Protobuf)**, từ đó công cụ sinh mã Java tạo lớp message và stub để hai phía cùng thực hiện.

Bài này thực hành phương thức lấy danh sách sản phẩm theo kho: client yêu cầu một lần, server gửi từng sản phẩm thành các message riêng. Từ ví dụ đó, bạn sẽ hiểu cách khai báo **stream** trong file **.proto**, triển khai server bằng Spring, sử dụng Java stub ở client, và kiểm soát deadline, hủy RPC, status, metadata, TLS, kiểm thử cũng như khả năng giám sát khi đưa dịch vụ vào vận hành.

## 1. Server streaming RPC hoạt động như thế nào?

Xét thao tác tìm các sản phẩm trong kho **hcm-01**. Thay vì đóng gói cả danh sách thành một response, server có thể gửi mỗi sản phẩm dưới dạng một response message. Client bắt đầu xử lý sản phẩm đầu tiên mà không cần đợi toàn bộ danh sách hoàn tất.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as Spring gRPC server
    C->>S: ListProducts(ListProductsRequest)
    S-->>C: ProductView (SKU-001)
    S-->>C: ProductView (SKU-002)
    S-->>C: ProductView (SKU-003)
    S-->>C: onCompleted / gRPC status OK
    Note over C,S: Chỉ có 1 request, có thể có 0..N response
~~~

Các quy tắc cốt lõi:

- Client gửi **đúng một request message** cho một lần gọi phương thức.
- Khi thành công, server có thể phát **0..N response messages**, đúng kiểu message đã khai báo trong hợp đồng Protobuf.
- Server kết thúc luồng bằng **onCompleted()**; lời gọi thành công có trạng thái gRPC **OK**. Luồng rỗng vẫn hợp lệ: server không gửi response nào và chỉ hoàn tất.
- Khi lỗi xảy ra, server gọi **onError(...)** với trạng thái gRPC thích hợp; không gọi **onCompleted()** sau lỗi.
- Thứ tự message được duy trì trong **một** stream gRPC. Không thể mặc nhiên suy ra thứ tự giữa hai RPC riêng biệt hay giữa nhiều client.
- Client có thể nhận được vài message trước khi RPC thất bại. Các message trước đó không bị gRPC tự động thu hồi.

| Kiểu RPC | Request | Response khi thành công | Khai báo Protobuf |
| --- | --- | --- | --- |
| Unary | 1 | 1 | **rpc GetProduct(GetRequest) returns (ProductView);** |
| **Server streaming** | **1** | **0..N** | **rpc ListProducts(ListRequest) returns (stream ProductView);** |
| Client streaming | Nhiều | 1 | **rpc Upload(stream Chunk) returns (UploadResult);** |
| Bidirectional streaming | Nhiều | Nhiều | **rpc Chat(stream Message) returns (stream Message);** |

**Khi nào nên chọn server streaming?** Khi cần chuyển nhiều kết quả theo từng phần, theo dõi các cập nhật do server phát ra, hoặc muốn client xử lý sớm trước khi toàn bộ dữ liệu sẵn sàng. Với danh sách nhỏ, unary trả về một message có trường **repeated** cũng phù hợp. Với truy vấn cần phân trang ổn định, di chuyển giữa các trang độc lập và resume theo cursor, pagination có thể đơn giản hơn một stream dài.

## 2. Khai báo hợp đồng bằng Protocol Buffers

Tạo file **src/main/proto/inventory.proto**:

~~~proto
syntax = "proto3";

package demo.inventory.v1;

option java_package = "vn.demo.grpc.inventory.v1";
option java_multiple_files = true;
option java_outer_classname = "InventoryProto";

service Inventory {
  // Một yêu cầu chọn kho; nhiều phản hồi, mỗi phản hồi là một sản phẩm.
  rpc ListProducts(ListProductsRequest) returns (stream ProductView);
}

message ListProductsRequest {
  string warehouse_id = 1;
}

message ProductView {
  string sku = 1;
  int32 available_quantity = 2;
}
~~~

Phần quyết định loại RPC là:

~~~proto
rpc ListProducts(ListProductsRequest) returns (stream ProductView);
~~~

Từ khóa **stream** chỉ đứng trước **kiểu phản hồi**, nên đây là server streaming. Nếu đặt **stream** trước kiểu yêu cầu thì phương thức trở thành client streaming; đặt ở cả hai phía là bidirectional streaming.

Các thành phần khác cần hiểu:

1. **demo.inventory.v1** là namespace của Protobuf; tên phương thức gRPC đầy đủ là **/demo.inventory.v1.Inventory/ListProducts**.
2. **java_package** chỉ định package Java cho mã sinh; **java_multiple_files** tạo các lớp message riêng.
3. Các số **= 1**, **= 2** là field number trong định dạng nhị phân Protobuf. Khi thay đổi hợp đồng đã phát hành, không đổi ý nghĩa của field number và dùng **reserved** cho số hoặc tên field bị loại bỏ.
4. Request vẫn là một message thông thường. Server có thể dựa vào **warehouse_id** để xác định tập dữ liệu cần phát.

Sau khi cấu hình trình biên dịch **protoc** và plugin **protoc-gen-grpc-java** trong hệ thống build, mã Java được sinh thường có **ListProductsRequest**, **ProductView**, **InventoryGrpc.InventoryImplBase**, **InventoryGrpc.InventoryStub** (bất đồng bộ) và **InventoryGrpc.InventoryBlockingStub**. Không sửa trực tiếp các lớp được sinh; hãy chỉnh file **.proto** rồi sinh mã lại. Cả server và client cần dùng các phiên bản hợp đồng tương thích.

## 3. Triển khai server streaming ở Spring

Giả sử dự án Spring Boot đã cấu hình Spring gRPC server, dependency gRPC Java và bước sinh mã từ **inventory.proto**. Ví dụ sau dùng dữ liệu mẫu nhỏ để thể hiện rõ vòng đời của stream:

~~~java
package vn.demo.app;

import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.List;
import org.springframework.stereotype.Service;
import vn.demo.grpc.inventory.v1.InventoryGrpc;
import vn.demo.grpc.inventory.v1.ListProductsRequest;
import vn.demo.grpc.inventory.v1.ProductView;

@Service
public class InventoryService extends InventoryGrpc.InventoryImplBase {

    @Override
    public void listProducts(
            ListProductsRequest request,
            StreamObserver<ProductView> responseObserver) {

        String warehouseId = request.getWarehouseId().trim();
        if (warehouseId.isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("warehouse_id must not be blank")
                    .asRuntimeException());
            return;
        }

        if (!warehouseId.equals("hcm-01")
                && !warehouseId.equals("hn-01")) {
            responseObserver.onError(
                Status.NOT_FOUND
                    .withDescription("warehouse not found")
                    .asRuntimeException());
            return;
        }

        // Dữ liệu ví dụ: kho hn-01 tồn tại nhưng chưa có sản phẩm.
        List<ProductView> products = warehouseId.equals("hcm-01")
            ? List.of(
                ProductView.newBuilder()
                    .setSku("SKU-001")
                    .setAvailableQuantity(12)
                    .build(),
                ProductView.newBuilder()
                    .setSku("SKU-002")
                    .setAvailableQuantity(5)
                    .build())
            : List.of();

        for (ProductView product : products) {
            // Không tiếp tục tạo hoặc gửi dữ liệu khi RPC bị hủy.
            if (Context.current().isCancelled()) {
                return;
            }
            responseObserver.onNext(product);
        }

        if (!Context.current().isCancelled()) {
            responseObserver.onCompleted();
        }
    }
}
~~~

Trong tích hợp Spring gRPC có cơ chế tự đăng ký bean triển khai **BindableService**, bean **InventoryService** sẽ được đăng ký với gRPC server. Cách khai báo và tự cấu hình server/client cụ thể phụ thuộc phiên bản Spring gRPC hoặc starter đang dùng; trong bài học này, **@Service** làm rõ rằng lớp triển khai do Spring quản lý.

Phân tích ba thao tác của **StreamObserver**:

| Lời gọi | Ý nghĩa | Quy tắc dùng |
| --- | --- | --- |
| **onNext(item)** | Đẩy thêm một **ProductView** đến client | Có thể gọi nhiều lần khi stream đang mở |
| **onCompleted()** | Báo đã gửi xong; RPC thành công | Gọi đúng một lần, sau **onNext** cuối cùng; stream có thể không có **onNext** |
| **onError(cause)** | Báo lỗi và kết thúc RPC | Gọi thay cho **onCompleted**, không phát tiếp message |

Trong ví dụ, yêu cầu **hcm-01** nhận hai sản phẩm, **hn-01** nhận luồng thành công nhưng rỗng, còn mã kho không tồn tại trả **NOT_FOUND**. Cần phân biệt *dữ liệu rỗng* với *lỗi không tìm thấy tài nguyên* theo quy tắc nghiệp vụ của API.

**Lưu ý về tính đồng thời:** **StreamObserver** phía server không cho phép nhiều luồng gọi **onNext** cùng lúc một cách tùy tiện. Nếu dữ liệu đến từ nhiều tác vụ bất đồng bộ, ứng dụng phải tuần tự hóa các thao tác gửi trên cùng observer và bảo đảm chỉ có **một** tín hiệu kết thúc. Đoạn ví dụ dùng vòng lặp ngắn, chạy tuần tự để dễ học; không nên sao chép vòng lặp lớn hoặc vô hạn vào luồng xử lý RPC mà không có cơ chế điều tiết.

## 4. Tạo client gRPC trong ứng dụng Spring

Client có thể nhận server streaming qua **async stub**, nơi mỗi message đến được chuyển vào callback. Với server streaming, **blocking stub** cũng hỗ trợ API trả về **Iterator**. Cả hai sử dụng cùng hợp đồng Protobuf.

Ví dụ cấu hình channel và hai stub thành các Spring bean:

~~~java
package vn.demo.app;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import vn.demo.grpc.inventory.v1.InventoryGrpc;

@Configuration
public class InventoryClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel inventoryChannel() {
        // Chỉ dùng plaintext trong môi trường local/dev tin cậy.
        return ManagedChannelBuilder
            .forAddress("localhost", 9090)
            .usePlaintext()
            .build();
    }

    @Bean
    InventoryGrpc.InventoryStub inventoryStub(
            ManagedChannel inventoryChannel) {
        return InventoryGrpc.newStub(inventoryChannel);
    }

    @Bean
    InventoryGrpc.InventoryBlockingStub inventoryBlockingStub(
            ManagedChannel inventoryChannel) {
        return InventoryGrpc.newBlockingStub(inventoryChannel);
    }
}
~~~

Mã trên minh họa trực tiếp gRPC Java. Trong dự án thực tế, cấu hình địa chỉ dịch vụ, TLS và channel bằng cơ chế quản lý client của phiên bản Spring gRPC đang sử dụng. Không tạo một channel mới cho từng sản phẩm hoặc từng request; channel thường được tái sử dụng.

### 4.1. Async stub: xử lý từng message qua callback

~~~java
package vn.demo.app;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import vn.demo.grpc.inventory.v1.InventoryGrpc;
import vn.demo.grpc.inventory.v1.ListProductsRequest;
import vn.demo.grpc.inventory.v1.ProductView;

@Service
public class InventoryClient {

    private final InventoryGrpc.InventoryStub stub;

    public InventoryClient(InventoryGrpc.InventoryStub stub) {
        this.stub = stub;
    }

    public void printProducts(String warehouseId) {
        ListProductsRequest request = ListProductsRequest.newBuilder()
            .setWarehouseId(warehouseId)
            .build();

        stub.withDeadlineAfter(5, TimeUnit.SECONDS)
            .listProducts(request, new StreamObserver<ProductView>() {
                @Override
                public void onNext(ProductView item) {
                    System.out.printf("%s: %d%n",
                        item.getSku(), item.getAvailableQuantity());
                }

                @Override
                public void onError(Throwable error) {
                    Status status = Status.fromThrowable(error);
                    System.err.println(
                        "Stream failed: " + status.getCode());
                }

                @Override
                public void onCompleted() {
                    System.out.println("Đã nhận hết danh sách sản phẩm");
                }
            });
    }
}
~~~

Lời gọi **printProducts(...)** khởi tạo RPC rồi trả quyền điều khiển về bên gọi; các callback được thực thi khi dữ liệu/sự kiện gRPC đến. Trong ứng dụng thật, không nên thực hiện công việc chặn lâu hoặc ném ngoại lệ không được kiểm soát trong **onNext**; nếu xử lý nặng, hãy chuyển công việc sang bộ xử lý phù hợp và giới hạn số tác vụ đang chờ.

Luồng chạy có thể kết thúc theo một trong hai cách: **onCompleted** sau khi nhận hết dữ liệu, hoặc **onError** khi RPC thất bại hay bị hủy. **onCompleted không nhận thêm ProductView**; nó chỉ đánh dấu kết thúc.

### 4.2. Blocking stub: duyệt stream bằng Iterator

~~~java
ListProductsRequest request = ListProductsRequest.newBuilder()
    .setWarehouseId("hcm-01")
    .build();

try {
    var products = blockingStub
        .withDeadlineAfter(5, TimeUnit.SECONDS)
        .listProducts(request);

    while (products.hasNext()) {
        ProductView product = products.next();
        System.out.println(product.getSku());
    }
} catch (io.grpc.StatusRuntimeException ex) {
    System.err.println("RPC failed: " + ex.getStatus().getCode());
}
~~~

Đây là đoạn nằm trong phương thức đã có biến **blockingStub** kiểu **InventoryGrpc.InventoryBlockingStub**. **hasNext()** hoặc **next()** có thể chặn để đợi response mới và có thể ném **StatusRuntimeException** nếu stream lỗi. Chỉ nên dùng blocking stub tại nơi có thể chờ đồng bộ; tránh gọi trực tiếp trên event loop hoặc luồng phản hồi yêu cầu có ràng buộc không chặn.

## 5. Deadline, cancellation và flow control

### Deadline áp dụng cho cả stream

**withDeadlineAfter(5, TimeUnit.SECONDS)** giới hạn **toàn bộ thời gian sống của RPC**, không cấp thêm năm giây sau mỗi **onNext**. Một stream dài liên tục có thể bị kết thúc bằng **DEADLINE_EXCEEDED** dù vẫn phát message đều đặn, nếu deadline tổng đã qua.

Đối với stream hữu hạn, đặt deadline theo ngân sách hoàn tất yêu cầu. Đối với luồng cập nhật kéo dài, thiết kế thời điểm ngắt/kết nối lại, khả năng tiếp tục từ cursor/sequence number và chính sách reconnect. Khi chuyển tiếp một request qua nhiều dịch vụ, phải cân nhắc ngân sách thời gian của RPC cha và các RPC con.

### Hủy RPC khi không cần dữ liệu

Client có thể hủy RPC khi người dùng rời màn hình hoặc không còn cần kết quả. Ở phía gRPC Java, server có thể kiểm tra **Context.current().isCancelled()** như ví dụ, hoặc sử dụng **ServerCallStreamObserver** để nhận tín hiệu hủy. Với async client, **ClientResponseObserver** cung cấp **ClientCallStreamObserver** trong **beforeStart(...)** để quản lý lời gọi, bao gồm **cancel(...)**.

Nếu server đang đọc cơ sở dữ liệu, xử lý hàng đợi hoặc chạy công việc nền, cần dừng các tác vụ đó khi stream bị hủy. **Hủy RPC không tự động hoàn tác thay đổi dữ liệu** đã được server thực hiện; hãy thiết kế tính idempotent và giao dịch cho các hành động có tác dụng phụ.

### Điều tiết tốc độ và backpressure

Khi client nhận chậm, việc gọi **onNext** liên tục có thể làm tăng lượng dữ liệu chờ được truyền. gRPC Java cung cấp hỗ trợ **flow control** và **ServerCallStreamObserver.isReady()**, **setOnReadyHandler(...)** để server điều tiết việc phát message.

Một quy trình an toàn cho luồng lớn là:

1. Lấy dữ liệu theo từng phần nhỏ hoặc từ một nguồn có thể tạm dừng; không tải toàn bộ dữ liệu cực lớn vào bộ nhớ.
2. Chỉ gửi thêm message khi observer sẵn sàng, đồng thời giới hạn bộ đệm ứng dụng.
3. Khi observer không còn sẵn sàng, dừng phát và đợi sự kiện **onReady** để tiếp tục.
4. Đảm bảo các lần gọi **onNext**, **onError** và **onCompleted** trên cùng stream được tuần tự hóa; xử lý riêng trường hợp client hủy giữa chừng.

**isReady()** là tín hiệu để điều tiết áp lực truyền dữ liệu, không phải lời hứa rằng message vừa gửi đã được client xử lý xong. Với stream chỉ chứa vài phần tử như ví dụ, vòng lặp tuần tự là đủ để minh họa; với stream dài, cần kiểm soát nguồn dữ liệu và tốc độ phát.

## 6. Status, dữ liệu từng phần và xử lý lỗi

Giả sử server gửi hai sản phẩm rồi gặp lỗi khi truy vấn sản phẩm thứ ba:

~~~text
Client nhận SKU-001
Client nhận SKU-002
Server gặp lỗi truy vấn
Server kết thúc RPC với status INTERNAL
Client nhận onError(INTERNAL)
~~~

Hai sản phẩm đã được nhận vẫn nằm trong ứng dụng client, nhưng **cả RPC kết thúc lỗi**. Vì thế, không được mặc định rằng mọi dữ liệu đã nhận là một danh sách hoàn chỉnh. Nếu nghiệp vụ yêu cầu snapshot nhất quán hoặc xử lý nguyên tử, cần có quy ước rõ ràng: snapshot/version, sequence number, tổng số dự kiến, marker xác nhận, hoặc chuyển sang unary nếu khối dữ liệu phù hợp.

| Status | Trường hợp điển hình | Cách client phản ứng |
| --- | --- | --- |
| **OK** | Stream hoàn tất thành công | Sử dụng toàn bộ kết quả |
| **INVALID_ARGUMENT** | **warehouse_id** rỗng hoặc sai định dạng | Sửa request trước khi gọi lại |
| **NOT_FOUND** | Kho không tồn tại theo quy ước API | Hiển thị không tìm thấy kho |
| **UNAUTHENTICATED** | Thiếu/sai thông tin xác thực | Làm mới thông tin xác thực nếu được phép |
| **PERMISSION_DENIED** | Client không có quyền đọc kho | Dừng và xử lý quyền truy cập |
| **DEADLINE_EXCEEDED** | Vượt ngân sách thời gian toàn RPC | Quyết định giữ/bỏ dữ liệu từng phần |
| **CANCELLED** | RPC bị hủy | Giải phóng tài nguyên liên quan |
| **UNAVAILABLE** | Mất kết nối/dịch vụ tạm không sẵn sàng | Có thể kết nối lại theo chính sách |
| **INTERNAL** | Server gặp lỗi ngoài dự kiến | Ghi nhận mã lỗi và điều tra phía server |

Nên kiểm tra và trả lỗi đầu vào **trước** khi phát bất kỳ message nào. Với lỗi phát sinh sau khi đã gửi dữ liệu, hãy phát **onError** một lần và cho client quyết định cách xử lý dữ liệu từng phần. Không trả lỗi bằng một **ProductView** có giá trị giả như **sku = "ERROR"**, vì điều đó làm mất ý nghĩa của hợp đồng dữ liệu.

Việc retry từ đầu có thể tạo các sản phẩm trùng nếu client đã xử lý một phần stream. Đối với danh sách biến động, nên có ID ổn định, số thứ tự hoặc cursor để client khử trùng và tiếp tục, đồng thời quy định rõ cách lấy snapshot nếu yêu cầu nhất quán.

## 7. Metadata, interceptor và TLS cho streaming

**gRPC metadata** truyền thông tin về lời gọi, thường ở header/trailer, ví dụ token xác thực, request ID hoặc trace ID. **Interceptor** ở client/server có thể áp dụng nhất quán cho toàn bộ RPC: kiểm tra quyền truy cập, tạo span truy vết, ghi nhận thời gian, đếm số message hoặc gắn correlation ID. Với server streaming, một RPC có **một lần bắt đầu/kết thúc** nhưng **nhiều sự kiện gửi message**; metric cần phân biệt số lời gọi và số message.

Metadata header thường được gửi lúc bắt đầu lời gọi; không nên giả định có thể gắn metadata khác nhau cho từng **ProductView** ở giữa một stream. Nếu mỗi phần tử cần timestamp, sequence number hoặc thông tin nghiệp vụ riêng, khai báo chúng thành field của response Protobuf.

Mã cấu hình channel phía trên dùng **usePlaintext()** để minh họa local/dev. Trong triển khai thực tế, bảo vệ đường truyền bằng **TLS**, kiểm tra danh tính server và cân nhắc **mTLS** nếu hai dịch vụ phải xác thực lẫn nhau. Áp dụng xác thực/phân quyền trước khi cung cấp dữ liệu của kho và không đưa token hoặc nội dung nhạy cảm vào log; interceptor hoặc tầng bảo mật phải chặn các stream trái phép.

## 8. Kiểm thử server streaming RPC

Với gRPC Java, **in-process server/channel** cho phép kiểm tra việc phát nhiều message, luồng rỗng và gRPC status mà không cần mở cổng mạng. Đoạn kiểm thử minh họa sau giả định lớp **InventoryService** ở ví dụ đã được tạo:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import org.junit.jupiter.api.Test;
import vn.demo.grpc.inventory.v1.InventoryGrpc;
import vn.demo.grpc.inventory.v1.ListProductsRequest;
import vn.demo.grpc.inventory.v1.ProductView;

class InventoryServiceTest {

    @Test
    void streamsProductsAndHandlesEmptyAndInvalidRequests()
            throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(new InventoryService())
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

        try {
            var stub = InventoryGrpc.newBlockingStub(channel);

            Iterator<ProductView> products = stub.listProducts(
                ListProductsRequest.newBuilder()
                    .setWarehouseId("hcm-01").build());
            List<String> skus = new ArrayList<>();
            products.forEachRemaining(p -> skus.add(p.getSku()));
            assertEquals(List.of("SKU-001", "SKU-002"), skus);

            Iterator<ProductView> emptyStream = stub.listProducts(
                ListProductsRequest.newBuilder()
                    .setWarehouseId("hn-01").build());
            assertFalse(emptyStream.hasNext());

            StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> {
                    Iterator<ProductView> invalid = stub.listProducts(
                        ListProductsRequest.newBuilder()
                            .setWarehouseId(" ").build());
                    invalid.hasNext(); // Lỗi có thể phát sinh khi duyệt.
                });
            assertEquals(Status.Code.INVALID_ARGUMENT,
                error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Kiểm thử trên cần dependency **grpc-inprocess** và JUnit phù hợp với phiên bản gRPC Java đang dùng. Nó kiểm tra hợp đồng và vòng đời server streaming ở mức gRPC Java, nhưng chưa xác nhận cơ chế đăng ký bean Spring hoặc bảo mật kênh.

Trong kiểm thử tích hợp với **Spring context** đang chạy, hãy bổ sung trường hợp service thực sự được đăng ký, kết nối tới server qua cấu hình gRPC của dự án và kiểm tra **deadline**, **cancellation**, **interceptor**, **TLS**. Với stream dài, nên giả lập client đọc chậm và kiểm tra rằng bộ đệm không tăng vô hạn; với stream có lỗi sau vài message, xác minh client xử lý dữ liệu từng phần đúng quy định.

## 9. Giám sát và vận hành

Vì server streaming có thể kéo dài lâu hơn unary RPC, nên theo dõi riêng các nhóm chỉ số:

- **Số RPC đang mở**, tổng RPC bắt đầu/kết thúc và số stream bị hủy.
- **Độ trễ đến message đầu tiên** (*time to first message*), tổng thời lượng stream và các phân vị độ trễ.
- **Số message/byte gửi trên mỗi RPC** và tốc độ phát theo thời gian.
- **Tỷ lệ lỗi theo gRPC status** như **UNAVAILABLE**, **DEADLINE_EXCEEDED**, **INTERNAL**.
- **Áp lực bộ nhớ, kích thước hàng đợi, số nguồn dữ liệu đang mở** và mức sử dụng luồng xử lý.

Kết hợp metric với distributed tracing để biết stream chậm ở truy vấn cơ sở dữ liệu, bộ đệm hay mạng. Một log chỉ có “RPC started” không đủ để nhận biết stream bị treo hoặc không bao giờ hoàn tất. Nên giới hạn thời gian và tài nguyên hợp lý, phát hiện stream tồn tại bất thường, và xác định rõ chiến lược đóng kết nối khi ứng dụng dừng.

## 10. Tổng kết và câu hỏi tự kiểm tra

Để định nghĩa **server streaming RPC**, khai báo phương thức Protobuf theo cú pháp **rpc Method(Request) returns (stream Response)**. Trong Java server, ghi từng phản hồi bằng **onNext**, rồi kết thúc bằng **onCompleted** hoặc **onError**. Ở client, dùng **async stub** để nhận callback hoặc **blocking stub** để duyệt **Iterator**. Khi đưa vào ứng dụng Spring, kết hợp đăng ký dịch vụ, quản lý channel, deadline, cancellation, flow control, TLS, kiểm thử và đo lường để stream hoạt động ổn định.

Tự kiểm tra bằng các câu hỏi:

1. Khác biệt duy nhất trong phần khai báo **.proto** giữa unary RPC và server streaming RPC là gì?
2. Server cần gọi gì khi kho tồn tại nhưng không có sản phẩm? Điều gì khác với tình huống kho không tồn tại?
3. Nếu client đã nhận 20 message rồi RPC trả **UNAVAILABLE**, có thể mặc định dữ liệu đã đầy đủ không? Thiết kế resume như thế nào?
4. Vì sao **withDeadlineAfter(5, SECONDS)** không thích hợp nếu stream được kỳ vọng chạy hàng giờ?
5. Khi client đọc chậm, **isReady()** và bộ đệm giới hạn giúp bảo vệ server như thế nào?

Khi trả lời được các câu hỏi này và chạy được ví dụ, bạn đã nắm cơ chế của server streaming RPC, sẵn sàng phân biệt nó với client streaming và bidirectional streaming trong các dịch vụ Spring gRPC lớn hơn.
