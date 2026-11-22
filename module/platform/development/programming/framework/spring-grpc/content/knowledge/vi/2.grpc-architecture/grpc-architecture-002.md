# Client stub và server implementation

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích trách nhiệm của **client stub**, **ManagedChannel**, **server transport**, bộ định tuyến phương thức và **server implementation** trong gRPC.
- Phân biệt mã Java **được sinh từ Protocol Buffers** với mã nghiệp vụ **do lập trình viên viết**.
- Triển khai và gọi một phương thức unary trong ứng dụng Spring; hiểu chữ ký API cho cả bốn kiểu RPC.
- Sử dụng đúng **StreamObserver**, trạng thái kết thúc, deadline, metadata và xử lý lỗi trên cả hai phía.
- Tổ chức vòng đời client/server bằng Spring, viết kiểm thử tích hợp cơ bản và nhận diện các lỗi kiến trúc thường gặp.

## 1. Vai trò của client và server trong một lời gọi gRPC

Trong hệ sinh thái **SPRING_GRPC**, ta xây dựng hợp đồng bằng **Protocol Buffers**, sinh API Java, rồi kết nối ứng dụng client và server qua gRPC. Spring giúp quản lý đối tượng, dependency injection, cấu hình và vòng đời ứng dụng; còn thư viện gRPC thực hiện mã hóa thông điệp, truyền RPC, điều phối callback và ánh xạ trạng thái lỗi.

Hai thành phần trung tâm là:

- **Client stub**: API Java phía client đại diện cho một dịch vụ ở xa. Caller gọi phương thức như gọi hàm Java, nhưng stub sẽ chuyển lời gọi thành một RPC qua **Channel**.
- **Server implementation**: lớp phía server triển khai các phương thức đã khai báo trong hợp đồng. gRPC nhận dữ liệu, tìm đúng handler rồi gọi phương thức đó.

Client stub **không chứa logic nghiệp vụ của server**. Server implementation cũng **không cần tự phân tích frame HTTP/2**. Hai bên chia sẻ hợp đồng về tên service, tên method và kiểu message.

~~~mermaid
sequenceDiagram
    participant A as Spring client service
    participant S as Generated client stub
    participant C as ManagedChannel
    participant T as gRPC server transport
    participant I as Server implementation
    A->>S: sayHello(HelloRequest)
    S->>C: RPC method descriptor + request
    C->>T: HTTP/2 headers + protobuf data
    T->>I: sayHello(request, responseObserver)
    I-->>T: onNext(HelloReply)
    I-->>T: onCompleted()
    T-->>C: response + grpc-status
    C-->>S: deserialize/finish RPC
    S-->>A: HelloReply
~~~

Với unary RPC, trình tự trên có một request và một response. Với streaming RPC, cùng một lời gọi có thể chứa nhiều message theo một hoặc cả hai hướng; các message đó vẫn thuộc **một HTTP/2 stream**.

### 1.1. Ai sở hữu việc gì?

| Tầng/thành phần | Trách nhiệm | Lập trình viên thường làm gì? |
| --- | --- | --- |
| **File .proto** | Khai báo service, method, message, hướng streaming | Thiết kế và quản lý phiên bản hợp đồng |
| **Code generator** | Sinh lớp message, service descriptor và các loại stub | Cấu hình protoc và plugin gRPC Java, không sửa mã sinh trực tiếp |
| **Client stub** | Cung cấp API Java gọi RPC; chuyển request vào Channel | Chọn blocking/async/future stub và cấu hình từng lời gọi |
| **ManagedChannel** | Phân giải tên, chọn backend, quản lý transport | Tạo/tái sử dụng Channel, cấu hình TLS, deadline, LB khi cần |
| **gRPC server/runtime** | Nhận HTTP/2, giải mã protobuf, tìm đúng RPC handler | Đăng ký service, cấu hình server/interceptor |
| **Server implementation** | Kiểm tra input, thực thi nghiệp vụ, phát response/status | Viết mã xử lý, đảm bảo kết thúc lời gọi đúng cách |

**Điểm phân biệt:** tạo một bean Spring có phương thức tên **sayHello** chưa đủ để client gRPC gọi được. Bean đó phải triển khai service theo API gRPC và được **đăng ký với gRPC server** (thủ công hoặc qua cơ chế auto-registration của tích hợp Spring đang dùng).

## 2. Hợp đồng Protocol Buffers quyết định API hai phía

Ví dụ dịch vụ chào hỏi hỗ trợ đầy đủ bốn kiểu RPC:

~~~proto
syntax = "proto3";

package demo.greeter.v1;

option java_package = "dev.example.grpc.greeter";
option java_multiple_files = true;
option java_outer_classname = "GreeterProto";

service Greeter {
  rpc SayHello(HelloRequest) returns (HelloReply);                 // Unary
  rpc ListGreetings(HelloRequest) returns (stream HelloReply);    // Server streaming
  rpc CollectNames(stream HelloRequest) returns (HelloReply);     // Client streaming
  rpc Chat(stream HelloRequest) returns (stream HelloReply);      // Bidirectional
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string text = 1;
}
~~~

Khi chạy **protoc** với bộ sinh Java Protocol Buffers và **protoc-gen-grpc-java**, thông thường ta nhận được:

- **HelloRequest**, **HelloReply**: lớp message protobuf bất biến với **newBuilder()**, getter và khả năng serialize/parse.
- **GreeterGrpc**: lớp chứa descriptor của dịch vụ, phương thức tạo stub và lớp cơ sở cho server.
- **GreeterGrpc.GreeterImplBase**: lớp server có các phương thức để override.
- **GreeterGrpc.GreeterBlockingStub**, **GreeterGrpc.GreeterStub**, **GreeterGrpc.GreeterFutureStub**: các API client khác nhau.

Với cách sinh mã Java thông dụng, method **SayHello** trong file proto xuất hiện thành **sayHello** trong Java. Đường dẫn RPC trên giao thức là **/demo.greeter.v1.Greeter/SayHello**. Tên package của protobuf (**demo.greeter.v1**) phục vụ nhận diện dịch vụ trên giao thức, còn **java_package** quyết định package của lớp Java sinh ra.

Không chỉnh sửa các lớp được sinh: lần chạy generator sau có thể ghi đè toàn bộ. Nếu đổi schema, cập nhật file **.proto**, sinh lại mã ở cả các phía cần thiết và kiểm tra tương thích hợp đồng.

### 2.1. Chữ ký phương thức thay đổi theo kiểu RPC

Bảng sau mô tả API **grpc-java** thường được sinh:

| RPC | Server override trong GreeterImplBase | Client điển hình |
| --- | --- | --- |
| **Unary** | **void sayHello(HelloRequest, StreamObserver<HelloReply>)** | Blocking: trả **HelloReply**; async: truyền response observer |
| **Server streaming** | **void listGreetings(HelloRequest, StreamObserver<HelloReply>)** | Blocking: nhận **Iterator<HelloReply>**; async: nhận từng message qua observer |
| **Client streaming** | **StreamObserver<HelloRequest> collectNames(StreamObserver<HelloReply>)** | Async stub trả về request observer để gửi nhiều request |
| **Bidirectional streaming** | **StreamObserver<HelloRequest> chat(StreamObserver<HelloReply>)** | Async stub trả về request observer, nhận response qua observer |

**StreamObserver<T>** là giao diện callback của gRPC Java để xử lý **message ở tầng ứng dụng**. Nó không phải HTTP/2 stream object, dù các message mà observer nhận/gửi được chuyên chở qua HTTP/2 stream.

Một số phiên bản hoặc tùy chọn code generator có thể sinh thêm biến thể API khác; bảng trên tập trung vào ba loại stub truyền thống của grpc-java.

## 3. Viết server implementation

Ta tạo bean Spring triển khai **GreeterGrpc.GreeterImplBase**. Mỗi method override tương ứng với một method trong hợp đồng.

Ví dụ bên dưới cho thấy đủ bốn kiểu RPC. Các lớp **HelloRequest**, **HelloReply** và **GreeterGrpc** phải được sinh từ file proto ở mục 2.

~~~java
package dev.example.server;

import dev.example.grpc.greeter.GreeterGrpc;
import dev.example.grpc.greeter.HelloReply;
import dev.example.grpc.greeter.HelloRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.StringJoiner;
import org.springframework.stereotype.Component;

@Component
public class GreeterEndpoint extends GreeterGrpc.GreeterImplBase {

    // 1 request -> 1 response
    @Override
    public void sayHello(HelloRequest request,
                         StreamObserver<HelloReply> responseObserver) {
        String name = request.getName().trim();

        if (name.isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("name không được rỗng")
                    .asRuntimeException()
            );
            return;
        }

        responseObserver.onNext(
            HelloReply.newBuilder().setText("Xin chào, " + name).build()
        );
        responseObserver.onCompleted();
    }

    // 1 request -> nhiều response
    @Override
    public void listGreetings(HelloRequest request,
                              StreamObserver<HelloReply> responseObserver) {
        String name = request.getName().trim();

        if (name.isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("name không được rỗng")
                    .asRuntimeException()
            );
            return;
        }

        for (int i = 1; i <= 3; i++) {
            responseObserver.onNext(
                HelloReply.newBuilder()
                    .setText("Lời chào " + i + " dành cho " + name)
                    .build()
            );
        }
        responseObserver.onCompleted();
    }

    // Nhiều request -> 1 response
    @Override
    public StreamObserver<HelloRequest> collectNames(
            StreamObserver<HelloReply> responseObserver) {

        return new StreamObserver<HelloRequest>() {
            private final StringJoiner names = new StringJoiner(", ");

            @Override
            public void onNext(HelloRequest request) {
                names.add(request.getName().trim());
            }

            @Override
            public void onError(Throwable error) {
                // Client đã hủy/luồng request lỗi: giải phóng tài nguyên nếu có.
            }

            @Override
            public void onCompleted() {
                responseObserver.onNext(
                    HelloReply.newBuilder()
                        .setText("Đã nhận: " + names)
                        .build()
                );
                responseObserver.onCompleted();
            }
        };
    }

    // Nhiều request <-> nhiều response
    @Override
    public StreamObserver<HelloRequest> chat(
            StreamObserver<HelloReply> responseObserver) {

        return new StreamObserver<HelloRequest>() {
            @Override
            public void onNext(HelloRequest request) {
                responseObserver.onNext(
                    HelloReply.newBuilder()
                        .setText("Echo: " + request.getName())
                        .build()
                );
            }

            @Override
            public void onError(Throwable error) {
                // Kết thúc phía nhận; dọn tài nguyên liên quan nếu có.
            }

            @Override
            public void onCompleted() {
                responseObserver.onCompleted();
            }
        };
    }
}
~~~

Đây là một ví dụ học tập: khi triển khai thực tế, **CollectNames** còn cần giới hạn số message/kích thước dữ liệu, kiểm tra từng phần tử, và hủy xử lý nếu client đã ngắt. Với **ListGreetings**, vòng lặp nhỏ giúp thấy luồng message; một luồng dữ liệu rất lớn cần cơ chế phát dần và backpressure thay vì đẩy tất cả ngay lập tức.

### 3.1. Quy tắc kết thúc lời gọi với StreamObserver

| Phương thức callback | Nghĩa | Ghi chú |
| --- | --- | --- |
| **onNext(message)** | Gửi/nhận thêm một message | Có thể lặp lại nhiều lần trong streaming |
| **onCompleted()** | Kết thúc thành công chiều gửi message | Phía server thường kết thúc response và gửi status OK |
| **onError(cause)** | Kết thúc bất thường với lỗi | Dùng **Status** gRPC phù hợp khi phản hồi lỗi nghiệp vụ |

Đối với response observer ở server, **onCompleted() và onError() là hai nhánh kết thúc loại trừ nhau**: kết thúc đúng một lần, không phát **onNext()** tiếp sau đó. Nếu có lỗi validation, hãy gọi **onError()** rồi **return** để tránh tiếp tục xử lý. Không để exception nghiệp vụ tùy ý rò qua handler; ánh xạ chúng sang **Status.INVALID_ARGUMENT**, **NOT_FOUND**, **PERMISSION_DENIED**, **FAILED_PRECONDITION**, **INTERNAL**... theo ý nghĩa thực tế.

Trong RPC streaming, callback **onError()** ở observer nhận request còn có thể báo việc peer hủy/đứt kết nối. Khi đó cần dọn tài nguyên và không mặc định gửi thêm response vào luồng đã thất bại.

**StreamObserver không tự bảo đảm an toàn khi nhiều thread cùng gọi phương thức ghi.** Nếu các producer bất đồng bộ cùng gửi trên một observer, ứng dụng phải điều phối/đồng bộ các lần ghi và trạng thái kết thúc. Các lời gọi bất đồng bộ cũng cần kiểm soát hủy và backpressure.

### 3.2. Đăng ký implementation với gRPC server

Nếu muốn thấy rõ cách gRPC server nối runtime với implementation, có thể đăng ký service bằng API grpc-java như sau:

~~~java
package dev.example.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfig {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server grpcServer(GreeterEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(endpoint)
                .build();
    }
}
~~~

**.addService(endpoint)** nhận implementation đáp ứng **BindableService**; từ đó gRPC tạo ánh xạ giữa method descriptor và handler Java tương ứng. **initMethod = "start"** yêu cầu Spring mở server khi khởi tạo bean; **destroyMethod = "shutdown"** yêu cầu dừng nhận công việc mới khi context đóng. Với hệ thống sản xuất, cân nhắc chờ các RPC đang xử lý hoàn tất có giới hạn thời gian, thay vì coi gọi **shutdown()** là đã chờ xong mọi RPC.

Cấu hình trên là một ví dụ **grpc-java thuần được quản lý bằng Spring**. Nếu dùng thư viện tích hợp **Spring gRPC** có cơ chế tự tạo server và tự phát hiện service bean, hãy theo cơ chế đó để tránh mở thêm server trùng cổng. Tên annotation và thuộc tính cấu hình cụ thể có thể khác nhau giữa các phiên bản thư viện tích hợp.

## 4. Client stub: chọn API phù hợp với cách gọi

gRPC Java thường có ba loại stub:

| Stub | Kiểu sử dụng | Lời gọi phù hợp |
| --- | --- | --- |
| **BlockingStub** | Chặn thread gọi cho đến khi nhận kết quả hoặc lỗi | Unary, server streaming (qua Iterator) |
| **FutureStub** | Trả future cho kết quả đến sau | Thường cho unary, phù hợp khi cần kết hợp future |
| **Stub** (asynchronous) | Đăng ký callback StreamObserver, không chờ đồng bộ | Cả bốn kiểu RPC, nhất là client/bidirectional streaming |

Tất cả các stub đều sử dụng **Channel**. Stub thường nhẹ, có thể tạo và chia sẻ hợp lý; điều quan trọng là **tái sử dụng ManagedChannel** trong thay vì dựng connection mới sau mỗi lời gọi.

### 4.1. Ví dụ client unary trong Spring

Ví dụ sau biểu diễn **ứng dụng client Spring riêng** kết nối đến server đang chạy trên cổng 9090:

~~~java
package dev.example.client;

import dev.example.grpc.greeter.GreeterGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel greeterChannel() {
        // Demo local; triển khai thật cần TLS và xác thực phù hợp.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterBlockingStub(
            ManagedChannel greeterChannel) {
        return GreeterGrpc.newBlockingStub(greeterChannel);
    }

    @Bean
    GreeterGrpc.GreeterStub greeterAsyncStub(
            ManagedChannel greeterChannel) {
        return GreeterGrpc.newStub(greeterChannel);
    }
}
~~~

~~~java
package dev.example.client;

import dev.example.grpc.greeter.GreeterGrpc;
import dev.example.grpc.greeter.HelloReply;
import dev.example.grpc.greeter.HelloRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class GreetingClientService {
    private final GreeterGrpc.GreeterBlockingStub greeter;

    public GreetingClientService(
            GreeterGrpc.GreeterBlockingStub greeter) {
        this.greeter = greeter;
    }

    public String greet(String name) {
        HelloRequest request = HelloRequest.newBuilder()
                .setName(name)
                .build();

        try {
            HelloReply response = greeter
                    .withDeadlineAfter(2, TimeUnit.SECONDS)
                    .sayHello(request);

            return response.getText();
        } catch (StatusRuntimeException ex) {
            Status.Code code = ex.getStatus().getCode();
            // Tại đây ánh xạ mã gRPC sang lỗi ứng dụng phù hợp.
            throw new IllegalStateException(
                    "Greeter RPC thất bại: " + code, ex);
        }
    }
}
~~~

**Điểm cốt lõi:**

- **ManagedChannel** là tài nguyên cần quản lý vòng đời. Channel có thể chưa mở kết nối ngay khi **build()**; transport thường được thiết lập theo nhu cầu.
- **GreeterBlockingStub** giữ cấu hình gọi RPC (channel, credentials, interceptors, deadline/call options). Phương thức **withDeadlineAfter(...)** trả **một stub cấu hình mới**, không sửa stub gốc. Gắn deadline gần lúc gọi để tránh tái sử dụng deadline đã hết hạn.
- **StatusRuntimeException** mang mã trạng thái và đôi khi metadata trailers. Client nên phân biệt lỗi dữ liệu như **INVALID_ARGUMENT** với lỗi hạ tầng như **UNAVAILABLE** và thời gian chờ **DEADLINE_EXCEEDED**.
- **usePlaintext()** chỉ phù hợp với demo hoặc hạ tầng nội bộ được kiểm soát cụ thể; production cần cấu hình TLS/trust và xác thực theo triển khai.

Khi ứng dụng dùng cơ chế Spring gRPC auto-configuration, Channel và stub có thể được framework tạo từ cấu hình, nhưng kiến trúc vẫn là **Spring client service → generated stub → Channel → remote gRPC server**.

### 4.2. Ví dụ client server-streaming bằng async stub

Với server-streaming, client nhận từng **HelloReply** qua callback. Đoạn mã sau minh họa luồng bất đồng bộ; nó **không** chờ cho RPC hoàn tất trước khi return:

~~~java
package dev.example.client;

import dev.example.grpc.greeter.GreeterGrpc;
import dev.example.grpc.greeter.HelloReply;
import dev.example.grpc.greeter.HelloRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class GreetingStreamClient {
    private final GreeterGrpc.GreeterStub stub;

    public GreetingStreamClient(GreeterGrpc.GreeterStub stub) {
        this.stub = stub;
    }

    public void printGreetings(String name) {
        HelloRequest request = HelloRequest.newBuilder()
                .setName(name)
                .build();

        stub.withDeadlineAfter(5, TimeUnit.SECONDS)
            .listGreetings(request, new StreamObserver<HelloReply>() {

                @Override
                public void onNext(HelloReply value) {
                    System.out.println(value.getText());
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println(
                        "RPC lỗi: " + Status.fromThrowable(error).getCode()
                    );
                }

                @Override
                public void onCompleted() {
                    System.out.println("Server stream đã hoàn tất");
                }
            });
    }
}
~~~

Với ứng dụng thật, nên chuyển kết quả/lỗi vào một abstraction thích hợp (ví dụ future, callback của tầng nghiệp vụ hoặc một luồng reactive có tích hợp đúng), thay vì ghi console. Không được giả định dữ liệu đã sẵn sàng ngay sau khi gọi **printGreetings()**.

### 4.3. Client-streaming và bidirectional-streaming

Với client-streaming, async stub trả về **request observer**. Caller gửi nhiều message bằng **onNext()** rồi gọi **onCompleted()** để báo đã gửi xong. Kết quả được nhận qua **response observer**:

~~~java
StreamObserver<HelloReply> responseObserver =
        new StreamObserver<HelloReply>() {
    @Override
    public void onNext(HelloReply value) {
        System.out.println(value.getText());
    }

    @Override
    public void onError(Throwable error) {
        System.err.println(Status.fromThrowable(error).getCode());
    }

    @Override
    public void onCompleted() {
        System.out.println("CollectNames hoàn tất");
    }
};

StreamObserver<HelloRequest> requests =
        asyncStub.collectNames(responseObserver);

requests.onNext(HelloRequest.newBuilder().setName("Lan").build());
requests.onNext(HelloRequest.newBuilder().setName("Minh").build());
requests.onCompleted();
~~~

Trong đoạn mã trên, **asyncStub** là biến kiểu **GreeterGrpc.GreeterStub** đã được khởi tạo từ Channel. Với phương thức **chat(responseObserver)**, client cũng nhận về một request observer, nhưng server có thể gửi response xen kẽ ngay khi client còn đang gửi request. Vì thế, **không cần đợi gọi onCompleted() phía gửi mới có thể nhận message phía trả lời** trong bidirectional streaming.

Gọi **onCompleted()** nghĩa là đã kết thúc **chiều gửi của client**, không nhất thiết là toàn bộ RPC đã kết thúc. Client còn phải chờ **onCompleted()** hoặc **onError()** của response observer để biết kết quả cuối cùng.

## 5. Từ lời gọi stub đến handler trên server

Giả sử client gọi:

~~~java
HelloReply reply = blockingStub.sayHello(
    HelloRequest.newBuilder().setName("Lan").build()
);
~~~

Các bước chính dưới lớp API Java là:

1. **Stub xác định method descriptor**, tên dịch vụ/method, kiểu request và response; bổ sung call options như deadline, credentials, message limits.
2. **Channel tạo một client call**, chọn transport/backend theo name resolver và load-balancer. Nếu cần, Channel mở hoặc tái kết nối TCP/TLS.
3. **gRPC client** mã hóa message thành protobuf, bọc thêm gRPC message framing và gửi trên HTTP/2 stream cùng headers/metadata.
4. **gRPC server** nhận headers với đường dẫn **/demo.greeter.v1.Greeter/SayHello**, giải mã request và tìm handler đã đăng ký.
5. **Implementation** thực hiện **sayHello()**, kiểm tra dữ liệu, gọi **responseObserver.onNext()** và kết thúc với **onCompleted()** hoặc **onError()**.
6. **Runtime server** gửi response và trailers chứa **grpc-status**. Runtime client giải mã message và status, rồi hoàn thành lời gọi blocking/async/future theo API tương ứng.

Trong gRPC truyền thống qua HTTP/2, **một RPC ứng với một HTTP/2 stream**; việc dùng streaming ở cấp RPC thay đổi số message đi qua stream, không tự động tạo một connection hoặc stream mới cho mỗi message.

### 5.1. Khác biệt giữa lỗi HTTP và lỗi gRPC

Một RPC thất bại có thể vẫn nhận HTTP status **200**, vì mã trạng thái ứng dụng được truyền qua **grpc-status** ở trailers. Những mã thường gặp:

| Mã gRPC | Tình huống minh họa | Cách xử lý phía client |
| --- | --- | --- |
| **INVALID_ARGUMENT** | Trường **name** rỗng, dữ liệu sai định dạng | Sửa request, thường không retry nguyên request |
| **NOT_FOUND** | Tài nguyên nghiệp vụ không tồn tại | Trả thông tin phù hợp cho caller |
| **UNAUTHENTICATED** | Thiếu/sai thông tin xác thực | Kiểm tra credentials và phiên làm việc |
| **PERMISSION_DENIED** | Có danh tính nhưng thiếu quyền | Xử lý phân quyền; không tự retry |
| **UNAVAILABLE** | Backend, connection hoặc proxy tạm thời không khả dụng | Retry có kiểm soát khi thao tác an toàn |
| **DEADLINE_EXCEEDED** | RPC không hoàn thành trước deadline | Xem latency và deadline; thận trọng với kết quả có thể đã được server xử lý |
| **INTERNAL** | Lỗi nội bộ không mong muốn | Ghi log/tracing ở server và trả thông tin lỗi an toàn |

Server nên dùng **Status** có ngữ nghĩa rõ ràng; client không nên dựa vào chuỗi **description** để điều khiển nghiệp vụ vì mô tả có thể đổi theo phiên bản hoặc ngôn ngữ. Với lỗi chưa biết, không trả stack trace hoặc bí mật từ server ra client.

## 6. Metadata, deadline, interceptor và bảo mật

Mặc dù stub che giấu HTTP/2, mỗi lời gọi vẫn có **ngữ cảnh vận hành** cần quản lý:

- **Metadata**: key-value đi trong headers/trailers của RPC. Thường dùng cho định danh request, correlation ID, token hoặc thông tin tracing. Tránh log toàn bộ metadata nếu có thông tin bí mật.
- **Deadline**: giới hạn thời gian của lời gọi; có thể truyền sang server qua **grpc-timeout**. Server có thể hủy việc còn dang dở khi deadline hết hạn, nhưng logic nghiệp vụ cần phối hợp hủy đúng cách.
- **Interceptor**: chèn logic quanh lời gọi để ghi metric, xác thực, truyền metadata, tracing. Có interceptor ở **client** và **server**; interceptor ở mức RPC không phải công cụ để can thiệp từng frame HTTP/2.
- **TLS**: bảo vệ kênh truyền, xác minh danh tính máy chủ và có thể hỗ trợ mTLS. TLS cần cấu hình đúng certificate, trust chain và HTTP/2/ALPN trong đường truyền thực tế.

**Phân chia trách nhiệm hợp lý:** interceptor dùng cho quan ngại chung như xác thực/observability; handler xử lý nghiệp vụ và xác thực điều kiện của dữ liệu; client service quyết định timeout, hành vi lỗi và retry cho từng use case.

Deadline của client là **giới hạn cuối cùng cho caller**; không nên coi nó là cơ chế đảm bảo rollback. RPC có thể đã tác động dữ liệu ở server trước khi client nhận **DEADLINE_EXCEEDED**. Khi cần retry các thao tác ghi, thiết kế **idempotency key** hoặc cơ chế khử trùng lặp phù hợp.

## 7. Threading, backpressure và vòng đời

### 7.1. Callback không đồng nghĩa với luồng xử lý riêng

Với blocking stub, thread phía client chờ kết quả. Với async stub, lời gọi trở về sớm và callback sẽ chạy theo executor/runtime được cấu hình. Ở server, phương thức implementation cũng thường được runtime gọi trên các thread thực thi; vì vậy cần:

- Tránh chặn thread xử lý bằng các tác vụ nặng kéo dài nếu hạ tầng chưa thiết kế để chạy chúng; khi cần, chuyển việc sang executor phù hợp.
- Không dùng **StreamObserver** làm vùng nhớ dùng chung thiếu đồng bộ khi nhiều thread cùng phát message.
- Hủy công việc không còn cần thiết khi peer hủy, deadline hết hoặc server đang shutdown.
- Thiết lập giới hạn message, kiểm soát tốc độ gửi và bộ đệm ở các RPC streaming để tránh sử dụng bộ nhớ quá mức.

**Backpressure** là khả năng giảm hoặc tạm dừng phát dữ liệu khi bên nhận chưa sẵn sàng. Với gRPC Java, các observer chuyên biệt như **ServerCallStreamObserver** hoặc **ClientCallStreamObserver** cung cấp tín hiệu **isReady()** và **setOnReadyHandler(...)** để điều tiết đầu ra. Cần thiết kế cẩn thận để xử lý thay đổi trạng thái sẵn sàng, hủy và yêu cầu phát tiếp; flow control của HTTP/2 không thay thế hoàn toàn kiểm soát hàng đợi ở tầng ứng dụng.

### 7.2. Quy tắc quản lý tài nguyên

| Tài nguyên | Khuyến nghị |
| --- | --- |
| **ManagedChannel** | Dùng lại giữa nhiều RPC/stub; quản lý bằng bean hay cấu hình framework; đóng khi ứng dụng dừng |
| **Client stub** | Có thể tái sử dụng; tạo biến thể cấu hình mới bằng các phương thức **with...** khi cần |
| **Server** | Đăng ký service một lần; theo dõi trạng thái, shutdown và thời gian drain RPC |
| **StreamObserver** | Gắn với từng RPC streaming; không dùng lại sau terminal event |
| **Executor / background jobs** | Giới hạn tải, dọn tài nguyên và xử lý cancellation |

Một lỗi phổ biến là **tạo ManagedChannel mới cho mỗi request**. Điều này làm tăng chi phí bắt tay, kết nối, quản lý tài nguyên và có thể gây nghẽn khi tải cao. Lỗi ngược lại là **giữ một StreamObserver sau khi RPC đã kết thúc** rồi cố gửi tiếp; kết quả có thể là lỗi callback hoặc hành vi không xác định.

## 8. Kiểm thử client/server qua in-process transport

Kiểm thử tích hợp ở mức gRPC có thể dùng **InProcessServerBuilder** và **InProcessChannelBuilder**. Chúng cho phép gọi qua runtime gRPC mà không cần chiếm cổng TCP, giúp kiểm chứng service registration, protobuf serialization theo API, lời gọi và status.

Ví dụ JUnit 5:

~~~java
package dev.example.server;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import dev.example.grpc.greeter.GreeterGrpc;
import dev.example.grpc.greeter.HelloReply;
import dev.example.grpc.greeter.HelloRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

class GreeterEndpointTest {

    @Test
    void shouldReturnGreetingAndRejectBlankName() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new GreeterEndpoint())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        try {
            GreeterGrpc.GreeterBlockingStub stub =
                    GreeterGrpc.newBlockingStub(channel);

            HelloReply result = stub.sayHello(
                    HelloRequest.newBuilder().setName("Lan").build()
            );
            assertEquals("Xin chào, Lan", result.getText());

            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.sayHello(
                        HelloRequest.newBuilder().setName("").build()
                    )
            );
            assertEquals(
                    Status.Code.INVALID_ARGUMENT,
                    error.getStatus().getCode()
            );
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Kiểm thử này cần thư viện hỗ trợ **grpc-inprocess** tương thích với phiên bản grpc-java và JUnit 5. **directExecutor()** phù hợp với ví dụ đơn giản vì callback được thực thi trực tiếp, nhưng không nên dùng để mô phỏng hệ thống có xử lý chặn hoặc tương tranh phức tạp.

**Giới hạn của kiểm thử in-process:** nó kiểm tra API service và xử lý RPC, nhưng **không chứng minh** cấu hình TLS, HTTP/2 proxy, DNS, load balancing hay hành vi trên mạng thật đã đúng. Các khía cạnh đó cần kiểm thử tích hợp riêng với transport thực và cấu hình hạ tầng tương ứng.

Khi tăng độ bao phủ, nên kiểm tra thêm unary thành công/lỗi, bốn kiểu streaming, deadline, hủy giữa chừng, metadata/interceptor, giới hạn message và graceful shutdown.

## 9. Những lỗi dễ gặp khi triển khai

| Biểu hiện | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Client nhận **UNIMPLEMENTED** | Server chưa đăng ký implementation hoặc triển khai sai version/method của proto | Kiểm tra service descriptor, path RPC, registration và tương thích hợp đồng |
| Client không kết nối được dù bean Spring đã khởi tạo | Chưa mở gRPC server hoặc sai cổng/TLS/HTTP2 | Kiểm tra bean lifecycle, socket, proxy và thiết lập TLS |
| RPC unary treo đến deadline | Handler không gọi **onCompleted()** hoặc **onError()**; có công việc bị chặn | Bảo đảm terminal event đúng một lần, đo thời gian handler |
| Streaming mất message hoặc gặp callback lỗi | Nhiều thread ghi cùng observer; kết thúc sớm hoặc ghi sau terminal | Điều phối ghi và vòng đời observer |
| Client-streaming không nhận response | Client chưa gọi **onCompleted()** trên request observer | Gửi half-close và chờ callback kết thúc ở phía response |
| CPU/memory tăng khi tải streaming | Không giới hạn dữ liệu, hàng đợi lớn, thiếu backpressure | Theo dõi buffer, giới hạn inflight và xử lý **isReady()** |
| Thử lại làm phát sinh thao tác ghi trùng | Retry RPC không idempotent khi kết quả chưa rõ | Dùng idempotency key/chính sách retry theo nghiệp vụ |
| HTTP 200 nhưng lời gọi lỗi | Đánh giá HTTP status thay vì **grpc-status** | Xử lý **StatusRuntimeException** và mã gRPC |

Để giám sát hiệu năng và độ tin cậy, nên ghi nhận **RPC latency**, **gRPC status theo method**, **RPC đang thực hiện**, **deadline exceeded**, **cancellation** và đặc điểm tải streaming. Kết hợp client/server tracing giúp xác định chậm trễ nằm ở hàng đợi, kết nối, interceptor hay handler.

## 10. Bài thực hành và câu hỏi tự kiểm tra

Thực hiện theo thứ tự sau trên hai ứng dụng Spring hoặc môi trường test phù hợp:

1. Sinh mã Java từ file proto của mục 2. Xác định **GreeterGrpc**, lớp message, ba loại stub và lớp **GreeterImplBase**; không sửa file được sinh.
2. Chạy gRPC server có **GreeterEndpoint**, gọi **SayHello** từ blocking stub. Xác nhận tên phương thức/response và thử request rỗng để nhận **INVALID_ARGUMENT**.
3. Gọi **ListGreetings** bằng async stub và quan sát ba lần **onNext()**, sau đó một lần **onCompleted()**.
4. Gọi **CollectNames** bằng cách gửi nhiều request qua request observer, rồi half-close. Gọi **Chat** và quan sát response có thể đến trước khi phía client hoàn tất gửi.
5. Áp deadline ngắn, mô phỏng server chậm và quan sát mã **DEADLINE_EXCEEDED**. Kiểm tra client có thể dùng lại Channel cho lời gọi khác.
6. Thêm interceptor ghi trace ID/latency và chạy kiểm thử in-process. Khi chuyển sang transport thật, xác minh riêng TLS/proxy, hủy và shutdown.

**Câu hỏi 1: Lớp nào phải sửa khi logic chào hỏi thay đổi nhưng hợp đồng .proto không đổi?**  
Thông thường sửa **server implementation**. Client stub và message được sinh vẫn giữ nguyên nếu hợp đồng không đổi.

**Câu hỏi 2: Vì sao một bean Spring có hàm sayHello không tự động trở thành gRPC endpoint?**  
gRPC runtime cần service implementation đáp ứng hợp đồng đã sinh và **đăng ký** nó với gRPC server. Cơ chế đăng ký có thể trực tiếp hoặc do thư viện tích hợp Spring thực hiện.

**Câu hỏi 3: Trong client-streaming, gọi onCompleted() ở request observer có nghĩa đã nhận xong kết quả chưa?**  
**Chưa.** Nó chỉ báo client đã ngừng gửi request. Kết quả cuối cùng đến qua response observer.

**Câu hỏi 4: Có nên dùng blocking stub cho bidirectional streaming?**  
Với API grpc-java truyền thống trong bài, **không**; sử dụng async stub, request observer và response observer để giao tiếp hai chiều.

## Tổng kết

Kiến trúc **client stub và server implementation** giúp hai ứng dụng Spring giao tiếp bằng một hợp đồng Protocol Buffers rõ ràng. **Mã sinh** đảm trách message và API gọi RPC; **client service** chọn cách gọi, deadline và xử lý lỗi; **ManagedChannel** vận chuyển RPC; **server implementation** xác thực yêu cầu, thực thi nghiệp vụ và hoàn tất đúng luồng response. Khi xây dựng unary hoặc streaming RPC, cần quản lý chặt vòng đời observer, Channel, tài nguyên và các trạng thái lỗi để hệ thống hoạt động ổn định.

