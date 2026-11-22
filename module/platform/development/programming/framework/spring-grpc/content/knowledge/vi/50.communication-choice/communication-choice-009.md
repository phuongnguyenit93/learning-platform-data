# Đánh giá client library của hệ sinh thái

Trong hệ sinh thái Spring gRPC, chọn client library ảnh hưởng trực tiếp đến cách ứng dụng tạo stub, quản lý kết nối, truyền metadata, đặt deadline, xử lý lỗi và quan sát RPC. Một lựa chọn phù hợp cần tương thích với Spring Boot và phiên bản grpc-java đang dùng, đồng thời đáp ứng mô hình xử lý của ứng dụng: đồng bộ, bất đồng bộ, reactive hay coroutine.

Không nên đánh giá thư viện chỉ qua số lượng annotation hoặc mức độ ngắn gọn của cấu hình. Hãy xem toàn bộ vòng đời của một lời gọi gRPC: mã được sinh từ Protocol Buffers, channel được tạo và đóng thế nào, credential được cấp ra sao, deadline/retry được áp dụng ở đâu, và lỗi được chuyển thành tín hiệu vận hành như thế nào.

## Nhìn client theo từng lớp

Một ứng dụng Java gọi gRPC thường có nhiều lớp thư viện cùng tham gia:

1. **Protocol Buffers và code generator** đọc file `.proto`, sinh message Java và service stub.
2. **gRPC Java runtime** cung cấp `Channel`, `ManagedChannel`, `CallOptions`, `Metadata`, `Status` và các loại stub.
3. **Transport** thực hiện kết nối mạng, thường là HTTP/2 qua Netty trong ứng dụng Java.
4. **Spring integration** quản lý channel, cấu hình, bean, interceptor và vòng đời ứng dụng theo cách phù hợp với Spring Boot.
5. **Thư viện bổ trợ** có thể cung cấp coroutine, reactive API, tracing, metrics hoặc cơ chế xác thực.

Các lớp này giải quyết những vấn đề khác nhau. Spring integration không thay thế runtime gRPC; reactive wrapper cũng không thay thế HTTP/2 flow control. Khi có lỗi, cần biết lớp nào chịu trách nhiệm để tránh chọn thêm một thư viện không xử lý đúng nguyên nhân.

## Các lựa chọn phổ biến

| Lựa chọn | Phù hợp khi | Điểm cần kiểm tra |
|---|---|---|
| grpc-java với generated stub | Backend Java cần API gRPC chuẩn, khả năng kiểm soát cao và ít lớp trừu tượng | Quản lý channel, cấu hình và tích hợp lifecycle Spring |
| Spring gRPC client integration | Ứng dụng Spring Boot muốn quản lý channel và cấu hình qua hệ sinh thái Spring | Tính năng có trong đúng phiên bản, cách đặt tên channel, autoconfiguration và thứ tự interceptor |
| grpc-kotlin | Ứng dụng Kotlin muốn dùng coroutine và API phù hợp ngôn ngữ | Phiên bản Kotlin/coroutines, tương thích stub sinh mã và cách hủy coroutine khi RPC bị cancel |
| Reactive adapter hoặc Reactor integration | Pipeline hiện có dùng Reactor và cần kết hợp RPC với luồng reactive | Backpressure, cancellation, scheduler và việc adapter có tạo queue không giới hạn hay không |
| gRPC-Web client | Trình duyệt cần gọi dịch vụ gRPC thông qua hạ tầng hỗ trợ gRPC-Web | Proxy/gateway, giới hạn giao thức và khác biệt so với client gRPC native |
| Starter hoặc wrapper bên thứ ba | Dự án cần một tích hợp chuyên biệt mà lớp chính thức chưa đáp ứng | Mức độ bảo trì, tương thích Spring Boot/grpc-java, CVE và khả năng thoát khỏi API riêng |

### grpc-java: nền tảng mặc định cho backend Java

grpc-java là runtime Java cốt lõi. Từ channel, ứng dụng tạo các stub được sinh từ `.proto`. Ba kiểu stub thường gặp có mục đích khác nhau:

- `newBlockingStub(channel)` cung cấp lời gọi đồng bộ, dễ đọc trong luồng xử lý tuần tự.
- `newFutureStub(channel)` trả về `ListenableFuture`, phù hợp với mô hình bất đồng bộ dựa trên future.
- `newStub(channel)` sử dụng `StreamObserver`, hỗ trợ callback và các kiểu streaming.

Ví dụ sử dụng blocking stub với deadline:

```java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("catalog.internal", 8443)
    .useTransportSecurity()
    .build();

CatalogGrpc.CatalogBlockingStub stub = CatalogGrpc.newBlockingStub(channel);

CatalogReply reply = stub
    .withDeadlineAfter(2, TimeUnit.SECONDS)
    .getCatalog(CatalogRequest.newBuilder()
        .setCatalogId("books")
        .build());
```

Đây là ví dụ API grpc-java thuần. Trong ứng dụng Spring Boot, channel thường nên được tạo và quản lý như một bean hoặc thông qua cơ chế channel factory của Spring integration đang sử dụng, thay vì tạo mới trong mỗi request. Cần đóng channel khi ứng dụng dừng.

Blocking stub dễ hiểu nhưng chiếm thread trong thời gian chờ response. Nó phù hợp với tác vụ đồng bộ có giới hạn và thread pool được tính toán hợp lý. Với ứng dụng có nhiều lời gọi đồng thời hoặc pipeline không đồng bộ, hãy cân nhắc future/async stub hoặc mô hình coroutine/reactive tương ứng. Không chuyển một lời gọi blocking sang event-loop thread của WebFlux.

### Spring gRPC integration: giảm công việc kết nối với Spring Boot

Spring integration bổ sung cơ chế cấu hình và quản lý tài nguyên theo vòng đời ứng dụng. Tùy phiên bản và starter, nó có thể hỗ trợ tạo channel từ cấu hình, đăng ký channel/stub để inject, áp dụng client interceptor và tích hợp với cấu hình TLS hoặc observability.

Khi đánh giá, hãy kiểm tra:

- Channel có được tái sử dụng trong suốt vòng đời ứng dụng hay bị tạo mới theo mỗi lời gọi?
- Có thể cấu hình nhiều server đích với tên channel rõ ràng không?
- Có hỗ trợ TLS/mTLS, credential, name resolver và load balancing cần thiết không?
- Interceptor có thể được áp dụng theo channel hoặc theo client cụ thể không?
- Channel có được shutdown đúng khi Spring context đóng không?
- Các thuộc tính cấu hình có được kiểm tra và báo lỗi rõ khi thiếu hoặc sai không?

Đừng giả định mọi starter Spring gRPC có cùng API hoặc cùng tên thuộc tính. Kiểm tra tài liệu của đúng phiên bản dependency trong dự án; không sao chép cấu hình của một starter khác hoặc một phiên bản cũ mà chưa xác minh.

### grpc-kotlin và coroutine

Nếu phần lớn client viết bằng Kotlin, grpc-kotlin có thể cung cấp API suspend và flow phù hợp với coroutine. Cách viết này giúp ghép RPC với cấu trúc coroutine, nhưng vẫn cần hiểu deadline, status, cancellation và giới hạn tài nguyên của gRPC.

Khi coroutine bị hủy, hãy xác minh RPC tương ứng cũng được cancel và tài nguyên downstream được giải phóng. Với streaming, kiểm tra cách `Flow` được thu thập, cách exception được chuyển thành gRPC status và việc adapter có giữ các phần tử chưa xử lý trong buffer lớn hay không. Một API trông giống coroutine không tự bảo đảm backpressure ở mọi tầng.

### Reactive adapter và Reactor

Ứng dụng Spring WebFlux có thể muốn chuyển RPC thành `Mono` hoặc `Flux`. Adapter có ích khi nó ánh xạ đúng vòng đời subscription, cancellation và lỗi. Tuy nhiên, cần kiểm tra cụ thể:

- Subscriber cancel có hủy RPC đang chạy không?
- Demand từ downstream có được chuyển thành điều tiết inbound/outbound phù hợp không?
- Có buffer trung gian không, dung lượng và chính sách overflow ra sao?
- Callback gRPC được chạy trên scheduler nào; có vô tình chiếm event loop không?
- Context như trace ID hoặc security principal có được truyền qua ranh giới callback không?

Không chọn một adapter chỉ vì nó trả về `Flux`. Nếu adapter gom toàn bộ response vào bộ nhớ hoặc bỏ qua demand, nó có thể làm hệ thống kém an toàn hơn cách dùng stub gốc.

### gRPC-Web và client trên trình duyệt

gRPC-Web giải quyết trường hợp trình duyệt cần gọi dịch vụ thông qua gateway/proxy hỗ trợ giao thức này. Đây không phải thư viện thay thế trực tiếp cho grpc-java trong backend Spring. Trình duyệt có các giới hạn giao thức và môi trường khác client native; cần kiểm tra unary/server streaming được hỗ trợ đến mức nào trong stack triển khai, cách truyền header, CORS và xác thực.

Nếu chỉ backend Java giao tiếp với backend Java, ưu tiên client gRPC native. Chỉ đưa gRPC-Web vào kiến trúc khi có yêu cầu từ trình duyệt hoặc môi trường không thể sử dụng HTTP/2 gRPC native.

## Tiêu chí đánh giá trước khi chọn

### 1. Tương thích phiên bản và quy trình sinh mã

Đây là điều kiện đầu tiên. Kiểm tra ma trận tương thích giữa:

- Phiên bản Java và Spring Boot.
- Spring gRPC integration/starter.
- `grpc-api`, transport runtime và các module grpc-java liên quan.
- `protobuf-java`, `protoc` và plugin sinh `protoc-gen-grpc-java`.
- Kotlin/coroutines hoặc Reactor nếu ứng dụng dùng các API này.

Giữ các phiên bản grpc-java liên quan nhất quán theo hướng dẫn phát hành. Không tùy tiện trộn runtime từ nhiều phiên bản hoặc dùng generated code được tạo bởi toolchain không tương thích. Nên khóa phiên bản trong build, tái sinh code theo quy trình lặp lại được và kiểm tra dependency tree để phát hiện nhiều phiên bản protobuf/grpc cùng xuất hiện.

### 2. Mô hình lập trình và tải đồng thời

Chọn kiểu stub theo cách ứng dụng quản lý thread:

| Mô hình | Ưu điểm | Rủi ro cần quản lý |
|---|---|---|
| Blocking | Dễ đọc, dễ gỡ lỗi, phù hợp luồng tuần tự | Thread bị giữ trong lúc chờ; nguy cơ cạn thread pool |
| Future | Tách thời gian chờ khỏi luồng gọi | Cần xử lý callback, cancellation và exception đúng cách |
| Async callback | Hỗ trợ streaming và điều khiển sự kiện | Callback khó tổ chức nếu không tuần tự hóa; phải quản lý buffer và readiness |
| Coroutine | Cú pháp tuần tự trên nền bất đồng bộ | Phải kiểm tra cancellation và context propagation |
| Reactive | Ghép với pipeline Reactor | Cần xác minh demand, scheduler, buffer và cancellation xuyên suốt |

Không có mô hình nào luôn nhanh hơn. Hãy đo throughput, p95/p99 latency, CPU, heap, số thread và số RPC đồng thời trên workload đại diện. Nếu ứng dụng dùng Spring MVC, blocking stub có thể là lựa chọn hợp lý khi thread pool và deadline được thiết kế tốt. Với WebFlux, không gọi blocking stub trực tiếp trên event loop.

### 3. Quản lý channel và kết nối

Channel là tài nguyên dài hạn, có thể quản lý nhiều RPC và tái sử dụng kết nối. Thư viện cần cho phép:

- Tạo channel theo địa chỉ hoặc target/name resolver.
- Tái sử dụng channel thay vì tạo một channel cho mỗi request.
- Cấu hình TLS, trust store, client certificate và credential.
- Cấu hình load balancing/service config khi hạ tầng yêu cầu.
- Theo dõi trạng thái kết nối và shutdown có trật tự.

Stub được tạo từ channel thường nhẹ và có thể tạo biến thể với `withDeadlineAfter`, `withInterceptors` hoặc `withCallCredentials` theo từng lời gọi. Channel không nên bị đóng sau mỗi RPC. Khi Spring context đóng, channel cần được shutdown và chờ hoàn tất trong một khoảng thời gian phù hợp.

### 4. Bảo mật và metadata

Kiểm tra thư viện hỗ trợ TLS và mTLS đúng cách, xác minh hostname/certificate, quản lý credential và truyền metadata. Token hoặc thông tin xác thực không nên được hard-code trong interceptor hay log. Nếu token thay đổi theo người dùng hoặc request, cần cơ chế cấp credential phù hợp thay vì gắn một token cố định vào channel dùng chung.

Client interceptor hữu ích để thêm trace ID, correlation ID hoặc metadata dùng chung. Dữ liệu phụ thuộc danh tính nên được lấy từ security context của request hiện tại và không được rò rỉ giữa các request dùng chung channel. Cần kiểm tra thứ tự interceptor, cách xử lý lỗi khi lấy token và cách refresh credential.

### 5. Deadline, retry và status

Một client library tốt phải giúp đặt deadline cho từng RPC và xử lý status có cấu trúc. Deadline cần được đặt rõ theo ngân sách thời gian của request đầu cuối; không nên để lời gọi gRPC chờ vô hạn.

Retry cần được cân nhắc theo mã trạng thái, chính sách service config và tính idempotent của thao tác. Chỉ retry những lỗi có thể phục hồi và thao tác an toàn khi thực hiện lại. Dùng backoff, jitter và giới hạn số lần thử; tính thời gian retry vào deadline tổng. Không retry một payload quá lớn hoặc một request bị từ chối bởi quota cố định mà không có tín hiệu cho biết khi nào có thể thử lại.

Client cần phân biệt `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `UNAUTHENTICATED`, `PERMISSION_DENIED` và các status khác để đưa ra hành vi phù hợp. Không dùng nội dung description tự do làm giao thức điều khiển máy đọc.

### 6. Quan sát và vận hành

Đánh giá khả năng tích hợp với tracing và metrics của hệ thống. Tối thiểu cần theo dõi:

- Số RPC theo method và status code.
- Latency phân vị, deadline exceeded và retry count.
- Số kết nối/channel, trạng thái kết nối và lỗi TLS.
- Kích thước request/response nếu có thể đo an toàn.
- Số stream hoạt động, thời lượng stream và queue/buffer nếu dùng streaming.

Kiểm tra OpenTelemetry hoặc cơ chế observability mà tổ chức đang dùng có tương thích với phiên bản runtime và Spring integration không. Tránh ghi payload, bearer token hoặc metadata nhạy cảm vào span/log. Metric label không nên chứa user ID, request ID hoặc giá trị có cardinality không giới hạn.

### 7. Kiểm thử và khả năng bảo trì

Client library cần hỗ trợ kiểm thử dễ dàng mà không buộc mọi test phải gọi một hệ thống bên ngoài. grpc-java có transport in-process cho kiểm thử client/server trong cùng tiến trình; ngoài ra vẫn cần integration test qua transport thực để xác minh TLS, proxy, name resolution và cấu hình kết nối.

Kiểm tra thêm:

- Có thể thay endpoint hoặc channel trong test mà không sửa code nghiệp vụ không?
- Có thể kiểm tra metadata, deadline, status và interceptor không?
- Có thể giả lập server chậm, server ngắt kết nối và stream bị cancel không?
- Dự án có release đều, tài liệu cập nhật, quy trình xử lý CVE và tương thích với phiên bản Java/Spring đang dùng không?
- API có dựa quá nhiều vào abstraction riêng khiến việc chuyển về grpc-java khó khăn không?

## Quy trình chọn thư viện trong dự án Spring

1. Liệt kê yêu cầu: Java hay Kotlin, MVC hay WebFlux, unary hay streaming, TLS/mTLS, xác thực, load balancing và tracing.
2. Xác định phiên bản Java, Spring Boot và grpc-java mà dự án có thể hỗ trợ.
3. Bắt đầu với grpc-java generated stub; xác định chính xác phần Spring integration nào cần để quản lý channel và cấu hình.
4. Chỉ thêm grpc-kotlin, reactive adapter hoặc wrapper khác khi có yêu cầu lập trình cụ thể mà stub hiện tại chưa đáp ứng tốt.
5. Viết một client mẫu cho RPC đại diện, bao gồm deadline, metadata, lỗi, cancellation và channel shutdown.
6. Chạy benchmark và integration test trên môi trường gần với triển khai thật.
7. Kiểm tra dependency tree, bảo mật, release cadence và chi phí nâng cấp trước khi chuẩn hóa thư viện.

## Ma trận quyết định tham khảo

| Bối cảnh | Điểm bắt đầu hợp lý | Khi nào bổ sung thư viện khác |
|---|---|---|
| Spring Boot, Java, backend-to-backend, unary | grpc-java stub cùng Spring gRPC integration | Khi cần cơ chế channel/configuration hoặc observability bổ sung |
| Java, server/client streaming | grpc-java async stub và flow control | Khi cần adapter chuyên biệt nhưng đã xác minh cancellation/backpressure |
| Kotlin service | grpc-kotlin cùng runtime tương thích | Khi cần tích hợp thêm context hoặc framework coroutine |
| Spring WebFlux | API bất đồng bộ hoặc adapter reactive đã kiểm chứng | Chỉ dùng wrapper Reactor nếu demand và cancellation được ánh xạ đúng |
| Browser gọi backend | gRPC-Web qua gateway phù hợp | Khi cần hỗ trợ giao thức khác, đánh giá riêng gateway và API boundary |

Ma trận này là điểm bắt đầu để thử nghiệm, không phải bảng xếp hạng hiệu năng. Quyết định cuối cùng phụ thuộc vào phiên bản thư viện, topology triển khai, mô hình tải và khả năng vận hành của đội ngũ.

## Checklist trước khi chuẩn hóa

- [ ] Phiên bản Spring Boot, Spring gRPC, grpc-java và protobuf tương thích.
- [ ] Code generator và generated stub được quản lý bằng build có thể tái lập.
- [ ] Channel được tái sử dụng, cấu hình tập trung và đóng đúng lifecycle.
- [ ] Stub style phù hợp với MVC/WebFlux và mô hình thread của ứng dụng.
- [ ] TLS/mTLS, credential và metadata được quản lý an toàn.
- [ ] Deadline có giá trị rõ; retry có giới hạn và phù hợp tính idempotent.
- [ ] Streaming có flow control, cancellation và buffer hữu hạn.
- [ ] Metrics/tracing không làm lộ dữ liệu nhạy cảm hoặc tạo cardinality quá lớn.
- [ ] Có unit/in-process test và integration test qua transport thực.
- [ ] Có chủ sở hữu dependency, theo dõi CVE và kế hoạch nâng cấp.

Với backend Spring viết bằng Java, grpc-java là nền tảng tự nhiên để bắt đầu vì nó cung cấp trực tiếp các API channel, stub, metadata, status và streaming. Spring gRPC integration nên được chọn để giải quyết nhu cầu cấu hình và quản lý vòng đời trong Spring Boot. Chỉ thêm lớp coroutine, reactive hoặc wrapper bên thứ ba khi lợi ích của nó được chứng minh bằng yêu cầu thực tế và các kiểm thử về deadline, cancellation, backpressure, bảo mật và hiệu năng.
