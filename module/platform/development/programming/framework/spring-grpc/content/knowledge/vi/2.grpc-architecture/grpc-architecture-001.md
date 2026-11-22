# Kênh, connection và HTTP/2 stream

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **Channel**, **connection (kết nối TCP/TLS)** và **HTTP/2 stream** khi xây dựng dịch vụ gRPC bằng Java và Spring.
- Giải thích một lời gọi RPC đi từ stub qua bộ phân giải tên, cân bằng tải, transport đến máy chủ như thế nào.
- Đọc được các thành phần chính của một trao đổi gRPC trên HTTP/2: headers, DATA, message framing, trailers và status.
- Hiểu cách multiplexing, flow control, deadline, hủy lời gọi và tái kết nối ảnh hưởng đến hiệu năng, độ tin cậy.
- Quản lý vòng đời kênh trong Spring và nhận diện một số lỗi vận hành thường gặp.

## 1. Ba khái niệm ở ba tầng khác nhau

gRPC là giao thức gọi thủ tục từ xa (RPC). Ứng dụng Java thường làm việc với **stub** được sinh từ Protocol Buffers; thư viện gRPC chịu trách nhiệm chuyển lời gọi thành trao đổi trên mạng. Trong gRPC Java, ba thuật ngữ sau không đồng nghĩa:

| Khái niệm | Vai trò | Phạm vi và vòng đời |
| --- | --- | --- |
| **Channel** (thường là **ManagedChannel** ở client) | Đối tượng logic để gửi RPC đến một đích; phối hợp name resolution, chọn địa chỉ, cân bằng tải và quản lý kết nối | Thường sống lâu, dùng chung cho nhiều lời gọi và nhiều stub |
| **Connection / transport** | Một kết nối mạng thực tế, thường là TCP kèm TLS, chạy giao thức HTTP/2 | Được thiết lập, gián đoạn hoặc thay thế theo trạng thái mạng và quyết định của channel |
| **HTTP/2 stream** | Luồng hai chiều độc lập ở tầng HTTP/2 để chở **một RPC** cụ thể | Được mở khi RPC bắt đầu và kết thúc khi trao đổi hoàn tất, bị hủy hoặc gặp lỗi |

Một Channel **không bắt buộc tương ứng với đúng một TCP connection**. Tùy bộ phân giải tên, chính sách cân bằng tải và transport, nó có thể dùng nhiều subchannel/connection đến các địa chỉ backend khác nhau. Ngược lại, **một HTTP/2 connection có thể mang nhiều HTTP/2 stream đồng thời**.

Sơ đồ mô hình hóa một tình huống có hai backend:

~~~mermaid
flowchart TD
    A["Spring service"] --> B["Stub sinh từ .proto"]
    B --> C["ManagedChannel: name resolver + load balancer"]
    C --> D["Subchannel A"]
    C --> E["Subchannel B"]
    D --> F["HTTP/2 connection A<br/>TCP + TLS"]
    E --> G["HTTP/2 connection B<br/>TCP + TLS"]
    F --> H["Stream 1: RPC A"]
    F --> I["Stream 3: RPC B"]
    G --> J["Stream 1: RPC C"]
~~~

Các số 1 và 3 ở đây minh họa **stream ID** trên cùng connection A. Không gian stream ID thuộc từng connection, vì vậy connection B có thể cũng sử dụng stream ID 1 mà không xung đột.

> **Quy tắc nhớ:** Stub phát lệnh gọi; Channel quyết định vận chuyển lời gọi; connection truyền các frame HTTP/2; stream gom các frame thuộc **một** RPC.

## 2. Một RPC đi qua các tầng ra sao?

Giả sử Spring service gọi phương thức **SayHello** trên một gRPC service ở máy chủ khác.

1. **Ứng dụng gọi stub.** Mã Java tạo request Protocol Buffers rồi gọi phương thức trên stub. Stub sử dụng Channel bên dưới.
2. **Channel chọn đích.** gRPC có thể phân giải tên dịch vụ thành địa chỉ backend và để chính sách cân bằng tải chọn subchannel. Khi chưa có transport sẵn sàng, Channel có thể khởi tạo kết nối.
3. **Thiết lập transport.** Client thiết lập TCP; nếu dùng TLS, hai phía bắt tay TLS và thương lượng HTTP/2 qua ALPN với giá trị **h2**. Trong môi trường phát triển, HTTP/2 dạng cleartext (**h2c**) có thể được dùng nếu hai đầu hỗ trợ.
4. **Mở HTTP/2 stream.** Client gửi request headers và các DATA frame chứa thông điệp protobuf. Mỗi RPC sử dụng một HTTP/2 stream; các message của RPC streaming vẫn đi trên **cùng stream đó**.
5. **Máy chủ xử lý.** gRPC server định tuyến phương thức từ đường dẫn RPC, giải mã request, chạy handler, sau đó ghi response và trạng thái kết thúc.
6. **Client nhận kết quả.** Thư viện gRPC ghép các DATA frame thành thông điệp, kiểm tra status cuối cùng rồi trả kết quả hoặc phát sinh lỗi cho caller.

Channel được tạo thường **không đồng nghĩa kết nối TCP đã mở ngay lập tức**: gRPC Java có thể kết nối theo nhu cầu khi RPC đầu tiên xuất hiện hoặc khi ứng dụng chủ động yêu cầu kết nối.

## 3. HTTP/2 stream chở nội dung gRPC như thế nào?

HTTP/2 phân chia dữ liệu thành **frame** và gán mỗi frame cho một stream. Các frame quan trọng với RPC thông thường là:

- **HEADERS:** mang phương thức, đường dẫn RPC và metadata ban đầu.
- **DATA:** mang các gRPC message đã được đóng khung.
- **HEADERS ở cuối stream (trailers):** mang trạng thái kết thúc, đặc biệt là **grpc-status**; đôi khi lỗi được trả ngay theo kiểu *trailers-only*, không có DATA.
- **RST_STREAM:** kết thúc bất thường một stream, chẳng hạn khi lời gọi bị hủy.
- **SETTINGS, WINDOW_UPDATE, PING, GOAWAY:** điều khiển connection, luồng dữ liệu và quá trình ngừng nhận stream mới.

### 3.1. Ví dụ trao đổi unary

Giả sử file Protocol Buffers khai báo dịch vụ:

~~~proto
syntax = "proto3";

package demo.hello;
option java_package = "demo.hello";
option java_multiple_files = true;

service Greeter {
  rpc SayHello(HelloRequest) returns (HelloReply);
  rpc WatchGreetings(HelloRequest) returns (stream HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
~~~

Ở mức khái niệm, yêu cầu unary có thể trông như sau (đây là cách biểu diễn dễ đọc; trên dây là các frame nhị phân HTTP/2):

~~~text
Client -> Server, stream 1:
  HEADERS
    :method: POST
    :scheme: https
    :path: /demo.hello.Greeter/SayHello
    :authority: greeter.example:443
    content-type: application/grpc
    te: trailers
    grpc-timeout: 1S
  DATA
    [compressed flag: 1 byte][message length: 4 bytes][HelloRequest protobuf]
  END_STREAM (client đã gửi xong request)

Server -> Client, vẫn trên stream 1:
  HEADERS
    :status: 200
    content-type: application/grpc
  DATA
    [compressed flag][message length][HelloReply protobuf]
  HEADERS (trailers)
    grpc-status: 0
  END_STREAM
~~~

**Một gRPC message** được thêm tiền tố 5 byte: 1 byte cờ nén và 4 byte độ dài thông điệp theo thứ tự byte lớn trước (*big-endian*). Phần còn lại là protobuf đã tuần tự hóa, hoặc dữ liệu được nén khi thương lượng nén. Một message có thể bị chia qua nhiều HTTP/2 DATA frame, và một DATA frame có thể chứa dữ liệu từ nhiều gRPC message. Vì vậy, **không được giả định “một DATA frame = một message”**.

Đường dẫn **/demo.hello.Greeter/SayHello** kết hợp tên service đầy đủ với tên method. **grpc-timeout** biểu diễn deadline còn lại bằng một giá trị thời gian tương đối; 1S nghĩa là một giây. **grpc-status: 0** tương ứng với **OK**.

HTTP status 200 chỉ cho biết trao đổi ở tầng HTTP có thể đã diễn ra; RPC vẫn có thể thất bại với **grpc-status** khác 0 trong trailers. Khi xử lý lỗi gRPC, phải xem **gRPC status** thay vì chỉ xem HTTP status.

### 3.2. Một stream cho từng kiểu RPC

| Kiểu RPC | Request và response | Số HTTP/2 stream cho một lời gọi |
| --- | --- | --- |
| **Unary** | 1 request → 1 response | 1 |
| **Server streaming** | 1 request → nhiều response | 1 |
| **Client streaming** | Nhiều request → 1 response | 1 |
| **Bidirectional streaming** | Nhiều request ↔ nhiều response, hai chiều có thể xen kẽ | 1 |

Với streaming, mỗi phía có thể đóng **nửa gửi** (*half-close*) khi không còn message để gửi; phía còn lại vẫn có thể tiếp tục gửi cho đến khi RPC kết thúc. **StreamObserver** trong gRPC Java là API ứng dụng để phát/nhận message; đừng nhầm nó với đối tượng HTTP/2 stream bên dưới.

## 4. Multiplexing: dùng chung connection mà vẫn có các RPC riêng

HTTP/2 cho phép frame từ nhiều stream được **xen kẽ** trên cùng connection:

~~~text
Một TCP/TLS connection
  -> HEADERS(stream 1)
  -> HEADERS(stream 3)
  -> DATA(stream 1)
  -> DATA(stream 3)
  -> DATA(stream 1)
  -> trailers(stream 3)
  -> trailers(stream 1)
~~~

Client không cần mở một TCP connection cho từng RPC. Điều này giảm chi phí bắt tay, tái sử dụng TLS và giúp nhiều RPC cùng tiến triển qua một transport. Tuy nhiên, multiplexing **không có nghĩa băng thông hay số RPC đồng thời là vô hạn**:

- Phía peer có thể công bố giới hạn **SETTINGS_MAX_CONCURRENT_STREAMS**; stream mới có thể phải chờ tài nguyên, tùy client và cấu hình.
- **Flow control** hoạt động ở cả mức **stream** lẫn **connection**, theo từng chiều truyền. Khi cửa sổ nhận cạn, bên gửi phải chờ **WINDOW_UPDATE**.
- Các HTTP/2 stream độc lập về frame ở tầng giao thức, nhưng vẫn cùng chạy trên TCP. Mất gói TCP vẫn có thể ảnh hưởng đến tiến độ của nhiều stream đang dùng chung connection (*TCP head-of-line blocking*).
- Việc tạo thêm connection hoặc chia tải sang backend khác phụ thuộc chính sách Channel/transport; không thể suy từ số lượng RPC.

**Ví dụ thực tế:** một server-streaming RPC phát hàng nghìn bản ghi nhưng client xử lý chậm. Nếu phía nhận không tiêu thụ đủ nhanh, cửa sổ flow control có thể làm phía gửi chậm hoặc tạm dừng. Nếu nhiều stream chia sẻ cùng connection, giới hạn tại mức connection cũng có thể ảnh hưởng đến các stream còn lại.

Ở API streaming bất đồng bộ của gRPC Java, ứng dụng nên chú ý **backpressure** và tín hiệu sẵn sàng ghi như **isReady/onReady** khi phù hợp; việc liên tục đẩy message không kiểm soát có thể làm tăng bộ đệm và độ trễ. Flow control ở transport không thay thế hoàn toàn việc quản lý tốc độ ở tầng ứng dụng.

## 5. Quản lý Channel trong ứng dụng Spring

Trong ứng dụng Spring, nên tạo Channel như một **bean dùng chung**, tiêm stub vào service và để Spring quản lý vòng đời. Không tạo rồi đóng Channel sau mỗi request HTTP hoặc mỗi lần gọi RPC, vì làm vậy lặp lại chi phí phân giải tên, kết nối và bắt tay.

Ví dụ sau dùng API **grpc-java** cơ bản; các lớp **GreeterGrpc**, **HelloRequest** và **HelloReply** được sinh từ file proto ở trên. Nó phù hợp để minh họa cơ chế bên dưới một ứng dụng Spring, không phụ thuộc tên thuộc tính cấu hình của một phiên bản Spring gRPC cụ thể.

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel greeterChannel() {
        // Chỉ dùng plaintext cho demo local đã được kiểm soát.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterStub(ManagedChannel greeterChannel) {
        return GreeterGrpc.newBlockingStub(greeterChannel);
    }
}
~~~

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class GreetingClient {
    private final GreeterGrpc.GreeterBlockingStub stub;

    public GreetingClient(GreeterGrpc.GreeterBlockingStub stub) {
        this.stub = stub;
    }

    public String greet(String name) {
        HelloRequest request = HelloRequest.newBuilder()
                .setName(name)
                .build();

        HelloReply reply = stub
                .withDeadlineAfter(1, TimeUnit.SECONDS)
                .sayHello(request);

        return reply.getMessage();
    }
}
~~~

Điểm cần hiểu từ ví dụ:

- **Bean ManagedChannel** tồn tại xuyên suốt nhiều lần gọi **greet**; bên dưới có thể mở, khôi phục hoặc thay thế connection.
- **Stub** là đối tượng cấu hình lời gọi, có thể dùng lại; các phương thức cấu hình như **withDeadlineAfter** tạo stub mới cho lời gọi cụ thể. Với deadline, nên gắn ngay trước RPC thay vì tái sử dụng mãi một stub đã gắn deadline hết hạn.
- **@Bean(destroyMethod = "shutdown")** giúp Spring yêu cầu Channel dừng khi context đóng. Với ứng dụng có yêu cầu shutdown chặt chẽ, có thể bổ sung cơ chế chờ lời gọi đang thực hiện hoàn tất trong thời hạn phù hợp.
- **usePlaintext()** chỉ dành cho ví dụ phát triển có môi trường tin cậy. Khi triển khai thực tế, cấu hình TLS, trust chain và xác thực theo hạ tầng; server/proxy phải hỗ trợ HTTP/2 cho gRPC.
- **Blocking stub** làm thread gọi phải chờ. Với streaming hoặc tải cao, cân nhắc async stub và quản lý việc tiêu thụ/đẩy message đúng cách.

Khi dùng tính năng tự động cấu hình của Spring gRPC, có thể để framework tạo Channel/stub theo cấu hình tương ứng. Dù cách tạo khác nhau, ranh giới kiến trúc **stub → Channel → HTTP/2 transport → stream** không đổi.

### 5.1. Trạng thái Channel và tái kết nối

gRPC Java có các trạng thái kết nối như:

| Trạng thái | Ý nghĩa vận hành |
| --- | --- |
| **IDLE** | Chưa chủ động kết nối hoặc đang nghỉ khi không có hoạt động |
| **CONNECTING** | Đang thiết lập kết nối đến đích |
| **READY** | Có transport sẵn sàng nhận lời gọi |
| **TRANSIENT_FAILURE** | Kết nối gặp lỗi tạm thời; có thể thử lại với backoff |
| **SHUTDOWN** | Channel đã được yêu cầu ngừng hoạt động |

**READY** không phải cam kết rằng mọi RPC tiếp theo đều thành công: mạng, backend, deadline hoặc quyền truy cập vẫn có thể thay đổi giữa lúc quan sát trạng thái và lúc gửi RPC. Tương tự, một Channel ở **IDLE** không nhất thiết là lỗi.

Khi kết nối mất, Channel thường xử lý thử tái kết nối theo cơ chế backoff. RPC có thể thất bại với **UNAVAILABLE** hoặc chờ khả dụng tùy thiết lập (ví dụ **wait-for-ready**) và deadline. Không coi tái kết nối là bảo đảm tự động thực thi lại mọi thao tác đã gửi: với retry, phải xét chính sách được cấu hình, khả năng lặp an toàn (*idempotency*) và trạng thái xử lý thực tế ở server.

## 6. Deadline, hủy và lỗi tác động lên tầng nào?

Cần phân biệt **vòng đời RPC/stream** với **vòng đời Channel/connection**:

| Sự kiện | Phạm vi ảnh hưởng thường gặp | Điều client quan sát |
| --- | --- | --- |
| **Một RPC vượt deadline** | Lời gọi đó bị kết thúc/hủy; connection dùng chung vẫn có thể phục vụ RPC khác | **DEADLINE_EXCEEDED** |
| **Client hủy một RPC** | Stream của lời gọi bị hủy, thường bằng tín hiệu kết thúc stream như **RST_STREAM** | **CANCELLED** tại phía hủy, tùy thời điểm |
| **Mất TCP/TLS connection** | Nhiều stream đang dùng connection đó có thể bị ảnh hưởng; Channel có thể thiết lập transport khác | Thường thấy **UNAVAILABLE** hoặc lỗi liên quan |
| **Server gửi grpc-status lỗi** | Kết thúc RPC tương ứng; không nhất thiết đóng connection | Mã **Status** của RPC, ví dụ **INVALID_ARGUMENT** |
| **Server/proxy gửi GOAWAY** | Connection không tiếp nhận stream mới theo giới hạn được thông báo; thực hiện drain/chuyển kết nối | Các RPC mới/đang chạy được xử lý tùy thời điểm và chính sách |

**Deadline** giới hạn thời gian của từng RPC, gồm cả thời gian chờ kết nối, chuyển dữ liệu và xử lý. **Keepalive PING** lại giúp phát hiện tình trạng connection và giữ hoạt động khi được phép; nó **không thay thế deadline**. Đặt keepalive quá dày có thể bị server hoặc proxy từ chối, thậm chí dẫn đến GOAWAY.

Metadata của một RPC thường đi trong headers/trailers, trong khi trạng thái connection được điều khiển bởi HTTP/2/TCP/TLS. Interceptor của gRPC thích hợp để gắn metadata, truyền context hoặc ghi log/tracing ở **mức RPC**; không nên suy luận rằng mỗi interceptor sẽ nhìn thấy từng frame HTTP/2.

## 7. Triệu chứng và hướng chẩn đoán

| Triệu chứng | Tầng nên kiểm tra | Cách tiếp cận |
| --- | --- | --- |
| Client không gọi được service khi chạy sau reverse proxy | TLS/ALPN/HTTP/2, định tuyến | Kiểm tra đường đi có hỗ trợ gRPC qua HTTP/2 và cấu hình proxy; xác minh host, cổng, certificate |
| Một thời điểm xuất hiện nhiều RPC chờ dù CPU còn trống | Stream concurrency, pool, flow control | Kiểm tra giới hạn concurrent streams, số RPC in-flight và tình trạng tiêu thụ dữ liệu streaming |
| Unary RPC thường xuyên timeout | Deadline, backend latency, DNS/LB | Tách thời gian chờ kết nối với thời gian xử lý; đối chiếu traces và metrics theo phương thức |
| Streaming lúc đầu nhanh nhưng về sau chậm dần | Backpressure và flow-control windows | Kiểm tra phía đọc/ghi có xử lý chậm, có hàng đợi hoặc bộ đệm tăng không |
| Sau khi backend restart, một số RPC thất bại tạm thời | Connection/Channel/reconnection | Quan sát trạng thái, mã UNAVAILABLE, backoff và hành vi graceful shutdown/GOAWAY |
| HTTP 200 nhưng application vẫn báo lỗi | Trailers/gRPC status | Kiểm tra **grpc-status** và message, không dựa riêng vào HTTP status |

Trong triển khai Spring gRPC, nên theo dõi tối thiểu **số RPC đang chạy**, **latency theo phương thức**, **tỉ lệ lỗi theo gRPC status**, **deadline exceeded**, **cancellation**, cùng số lượng connection/subchannel khi transport cung cấp metric. Tracing phân tán giúp liên hệ độ trễ ở client với handler server; log metadata phải tránh lộ token và dữ liệu nhạy cảm.

Không nên tự động tăng số connection để khắc phục mọi vấn đề. Trước hết cần xác định tắc nghẽn nằm ở **Channel/LB**, **HTTP/2 stream limit**, **flow control**, **network** hay **backend xử lý**.

## 8. Bài thực hành kiểm chứng mô hình

Giả sử có server gRPC trên **localhost:9090** và Spring client như ví dụ ở mục 5.

1. **Tái sử dụng Channel.** Tạo một Channel cho nhiều lời gọi **SayHello** chạy đồng thời; so sánh với trường hợp tạo Channel mới cho từng lời gọi. Quan sát chi phí kết nối và độ trễ. Số kết nối thực tế tùy transport/chính sách, nên kiểm tra bằng metric hoặc công cụ mạng thay vì giả định luôn bằng 1.
2. **Đổi từ unary sang server streaming.** Gọi **WatchGreetings** trả nhiều thông điệp. Quan sát rằng một RPC có nhiều DATA/message nhưng chỉ một HTTP/2 stream.
3. **Thử deadline ngắn.** Chủ động làm server xử lý lâu hơn deadline. Xác nhận lời gọi nhận **DEADLINE_EXCEEDED**, rồi gửi lời gọi khác trên Channel còn tồn tại.
4. **Mô phỏng bên nhận chậm.** Cho streaming client xử lý dữ liệu chậm; quan sát mức tiêu thụ bộ nhớ, tốc độ phát message và tín hiệu backpressure.
5. **Khởi động lại backend.** Theo dõi sự thay đổi trạng thái kết nối và gRPC status, sau đó xác minh Channel có thể tiếp tục phục vụ RPC khi backend sẵn sàng trở lại.

### Câu hỏi tự kiểm tra

**1. Một Channel chứa bao nhiêu connection và một connection chứa bao nhiêu RPC?**  
Channel có thể quản lý nhiều connection tùy chính sách và đích. Mỗi HTTP/2 connection có thể chở nhiều RPC đồng thời dưới dạng các stream khác nhau, nhưng chịu giới hạn tài nguyên và flow control.

**2. Một server-streaming RPC phát 500 message thì tạo bao nhiêu HTTP/2 stream?**  
**Một** stream cho toàn bộ RPC; các message được đóng khung và gửi qua nhiều DATA frame trên stream đó.

**3. Khi một RPC hết deadline, có nên đóng Channel dùng chung không?**  
Thông thường **không**. Deadline là giới hạn của từng RPC; Channel và connection dùng chung vẫn có thể phục vụ các lời gọi khác.

## Tổng kết

Với Spring gRPC, hãy quản lý **ManagedChannel** như tài nguyên dùng chung và để stub tạo ra từng lời gọi RPC. Channel phụ trách tìm và duy trì đường đi đến server; một **HTTP/2 connection** truyền nhiều **stream**, mỗi stream tương ứng một RPC, kể cả RPC streaming nhiều message. Khi gặp lỗi hiệu năng hoặc độ tin cậy, phân tích đúng tầng — Channel, connection, stream hay handler — sẽ giúp lựa chọn giải pháp có căn cứ.

