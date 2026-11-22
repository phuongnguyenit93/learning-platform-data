# Giới hạn reflection trong production

Server reflection cho phép công cụ vận hành khám phá service, method và Protobuf descriptor mà gRPC server đang công bố. Tính năng này hữu ích khi phát triển và điều tra sự cố, nhưng descriptor cũng tiết lộ cấu trúc API nội bộ, tên method quản trị và kiểu dữ liệu mà hệ thống hỗ trợ. Production cần một quyết định rõ ràng: tắt reflection nếu không có nhu cầu, hoặc chỉ cho phép operator đã xác thực truy cập qua đường kết nối được kiểm soát.

Trong Spring gRPC, chính sách phải được áp dụng tại server thực sự phục vụ RPC, theo profile và lifecycle của ứng dụng. Cần phân biệt ba lớp: TLS bảo vệ kết nối và xác thực server; authentication/authorization quyết định ai được đọc descriptor; network/gateway policy giới hạn nơi reflection có thể được gọi. Chỉ bật TLS không đồng nghĩa reflection đã được bảo vệ.

## 1. Reflection mở ra bề mặt thông tin nào?

Reflection công bố descriptor của các service đã đăng ký trên server. Caller có thể khám phá:

- Tên package và fully qualified service name.
- RPC method, input type và output type.
- Message, field number, field type, enum và nested message.
- Các file descriptor phụ thuộc cần để giải mã contract.
- Các service nội bộ hoặc method quản trị nếu chúng được đăng ký cùng server.

Thông tin này không tự chứa dữ liệu request, dữ liệu database hay credential. Tuy nhiên, tên method quản trị, cấu trúc message và version API có thể giúp người ngoài lập bản đồ hệ thống và chuẩn bị request có chủ đích. Vì vậy reflection là bề mặt thông tin cần quản trị, dù bản thân nó không thực hiện nghiệp vụ.

Reflection cũng không tự cấp quyền gọi service được khám phá. Caller có thể đọc descriptor nhưng vẫn bị authorization của RPC nghiệp vụ từ chối; ngược lại, tắt reflection không bảo vệ được method nếu endpoint vẫn cho phép caller gọi trực tiếp. Hai chính sách cần được thiết kế độc lập.

## 2. Chọn chính sách theo môi trường

Không cần bật reflection ở mọi môi trường:

| Môi trường | Chính sách thường phù hợp | Lý do |
| --- | --- | --- |
| Local development | Bật | Hỗ trợ grpcurl, IDE và debug nhanh |
| CI/integration test | Bật trên test server | Kiểm tra descriptor và service registration |
| Staging | Bật có kiểm soát | QA/operator có thể xác minh API sau deploy |
| Production public-facing | Tắt nếu không có nhu cầu vận hành | Tránh công bố schema nội bộ ra bề mặt public |
| Production nội bộ | Chỉ operator được phép truy cập | Hỗ trợ điều tra và xác minh contract có kiểm soát |

Nếu production không cần reflection, không đăng ký reflection service trên server production. Đây là cách giảm bề mặt API trực tiếp nhất. Nếu cần cho vận hành, bật có điều kiện và yêu cầu identity, authorization, network restriction cùng audit phù hợp.

Đừng dựa vào việc công cụ thông thường không tự gọi reflection. Bất kỳ client nào biết reflection protocol và truy cập được endpoint đều có thể gửi request nếu server cho phép.

## 3. Bật/tắt bằng cấu hình có kiểm soát

Đặt một property do ứng dụng quản lý để quyết định reflection có được đăng ký hay không:

```yaml
# application-local.yml
app:
  grpc:
    reflection:
      enabled: true

---
# application-prod.yml
app:
  grpc:
    reflection:
      enabled: false
```

Đây là property ví dụ của ứng dụng, không phải tên property chuẩn dùng chung cho mọi Spring gRPC starter. Khi starter tự quản lý server, dùng conditional bean hoặc server customizer mà đúng phiên bản starter hỗ trợ; xác minh bean được đăng ký vào chính server production. Nếu ứng dụng tự tạo server bằng grpc-java, chỉ thêm reflection service khi property cho phép.

Ví dụ với server được bootstrap trực tiếp:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;

ServerBuilder<?> builder = ServerBuilder.forPort(8443)
    .addService(new OrdersService())
    .addService(new InventoryService());

if (reflectionEnabled) {
    builder.addService(ProtoReflectionService.newInstance());
}

Server server = builder.build().start();
```

Không tạo một server thứ hai ngoài lifecycle Spring chỉ để bật reflection. Cách đó có thể mở thêm port, sử dụng TLS/authentication khác và làm cấu hình production khó kiểm soát. Hãy để service nghiệp vụ và reflection tuân theo lifecycle, transport và shutdown policy đã được ứng dụng quản lý.

## 4. Bảo vệ reflection bằng authentication và authorization

Reflection protocol dùng một bidirectional streaming RPC. Interceptor có thể kiểm tra identity ở cấp call và chỉ cho phép operator truy cập reflection service. Trong grpc-java, có thể bọc riêng service definition:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;
import io.grpc.protobuf.services.ProtoReflectionService;

ServerServiceDefinition reflectionDefinition =
    ServerInterceptors.intercept(
        ProtoReflectionService.newInstance().bindService(),
        operatorAuthorizationInterceptor);

Server server = ServerBuilder.forPort(8443)
    .addService(new OrdersService())
    .addService(new InventoryService())
    .addService(reflectionDefinition)
    .build()
    .start();
```

Đây là ví dụ grpc-java cho server tự cấu hình. Trong Spring gRPC, đưa logic tương tự vào server customizer/registration hook của starter hoặc cấu hình service definition trước khi đăng ký. Nếu starter tự động đăng ký mọi BindableService bean, cần xác nhận cách áp dụng interceptor riêng cho reflection theo API của phiên bản đang dùng.

Reflection là một service riêng có method như /grpc.reflection.v1.ServerReflection/ServerReflectionInfo; các bản triển khai tương thích v1alpha có thể dùng method path tương ứng trong package v1alpha. Authorization ở cấp reflection call thường cho phép hoặc từ chối toàn bộ stream khám phá. Nếu cần chỉ công bố một tập descriptor, phải dùng reflection implementation có lọc descriptor hoặc một service khám phá tùy chỉnh; chỉ kiểm tra tên RPC reflection không đủ để lọc từng service được hỏi trong payload.

Authentication cần xác minh credential thực sự, ví dụ token operator hoặc workload identity. Không tin role, user ID hay tenant do caller tự gửi trong metadata nếu chưa được xác minh. Nếu authentication dependency không khả dụng, áp dụng fail-closed cho reflection thay vì mở truy cập tạm thời.

## 5. TLS, mTLS và giới hạn mạng

TLS bảo vệ nội dung reflection trên đường truyền và giúp client xác minh server qua certificate. mTLS bổ sung xác thực certificate của client, nhưng server vẫn cần authorization để quyết định certificate identity nào được phép đọc descriptor.

Một lệnh grpcurl qua TLS có thể dùng CA tin cậy:

```bash
grpcurl -cacert operator-ca.pem \
  orders.internal.example:8443 \
  list
```

Nếu listener yêu cầu mTLS, cung cấp client certificate và private key:

```bash
grpcurl -cacert operator-ca.pem \
  -cert operator-client.pem \
  -key operator-client-key.pem \
  orders.internal.example:8443 \
  list
```

Hostname kết nối phải khớp SAN trong certificate hoặc authority override đã được cấu hình có chủ đích. Không dùng plaintext, bỏ hostname verification hoặc chấp nhận certificate không tin cậy để khắc phục lỗi cấu hình.

Network policy nên giới hạn nguồn truy cập reflection:

- Chỉ cho phép từ operator network, bastion hoặc workload quản trị được xác định.
- Dùng ingress/gateway allowlist theo identity và đường dẫn RPC nếu gateway hỗ trợ gRPC.
- Không route reflection tới public listener nếu chỉ cần quản trị nội bộ.
- Giới hạn egress/ingress giữa công cụ vận hành và server theo đúng port.
- Giữ business RPC authorization độc lập, kể cả khi reflection chỉ được mở nội bộ.

Nếu dùng gateway để chặn reflection, kiểm tra cả reflection v1 và v1alpha path mà server/tool hỗ trợ. Đừng chỉ chặn một package version rồi vô tình để biến thể khác mở.

## 6. Tách endpoint quản trị khi cần

Một số hệ thống cần reflection ở production nhưng không muốn công bố nó trên listener public. Có thể thiết kế endpoint quản trị nội bộ riêng, với các điều kiện:

1. Listener quản trị chỉ bind vào network/interface nội bộ và không được publish ra public ingress.
2. Transport dùng TLS/mTLS và trust material riêng phù hợp với operator.
3. Reflection chỉ được đăng ký trên listener quản trị.
4. Service descriptor được công bố phải lấy từ cùng contract/version với server nghiệp vụ.
5. Lifecycle, port, readiness, shutdown và monitoring của listener quản trị được quản lý rõ ràng.

Tùy kiến trúc, listener quản trị có thể cần một reflection registry/descriptor source dùng chung hoặc một tập service definition tương ứng. Không giả định một reflection service đặt trên server phụ sẽ tự biết descriptor của server nghiệp vụ khác. Kiểm tra danh sách và mô tả service trên endpoint quản trị để bảo đảm nó trả đúng service đang chạy.

Nếu việc nhân đôi service registration khiến các RPC nghiệp vụ vô tình lộ trên listener quản trị, hãy dùng gateway/proxy chỉ cho phép reflection method hoặc một implementation descriptor-only phù hợp. Đánh giá riêng các đường truy cập và không để endpoint quản trị trở thành một bản sao public server không được kiểm soát.

## 7. Không nhầm reflection authorization với business authorization

Reflection cho biết một method tồn tại và có kiểu request/response nào. Nó không cấp quyền gọi method đó. Mọi RPC nghiệp vụ vẫn phải kiểm tra identity và quyền ở server:

| Bề mặt | Chính sách cần có |
| --- | --- |
| Reflection service | Ai được liệt kê service và tải descriptor? |
| Business service | Ai được gọi từng service/method và trên tài nguyên nào? |
| Health service | Probe nào được đọc trạng thái và trạng thái nào được công bố? |
| Admin RPC | Operator nào được thực hiện thao tác quản trị? |

Không dùng reflection disabled như bằng chứng rằng API đã được bảo vệ. Client có thể gọi method bằng generated stub hoặc descriptor set đã có. Authorization phải nằm trên từng RPC hoặc service/method group theo contract bảo mật.

Tương tự, không mở toàn bộ server cho operator chỉ vì họ cần đọc reflection. Nếu operator chỉ cần descriptor, giới hạn quyền ở reflection service và giữ quyền gọi business/admin RPC theo nguyên tắc least privilege.

## 8. Audit, logging và rate limiting

Reflection thường được dùng trong các phiên điều tra, CI và automation. Cần ghi nhận đủ để truy vết mà không lưu dữ liệu nhạy cảm:

- Identity đã xác thực và nguồn mạng của operator.
- Thời điểm, endpoint và môi trường được truy cập.
- Reflection protocol version và loại hoạt động nếu telemetry có thể phân biệt.
- Kết quả allow/deny và status cuối.
- Correlation ID hoặc trace ID để liên kết với audit gateway.

Không ghi access token, private key, toàn bộ metadata hoặc payload nhạy cảm vào log. Reflection stream có thể gửi nhiều request liên tiếp; áp dụng rate limit/concurrency limit phù hợp để tránh một client tạo tải không cần thiết. Rate limit nên theo operator identity hoặc nguồn tin cậy, không chỉ theo IP nếu nhiều operator dùng chung NAT.

Alert khi có truy cập reflection từ nguồn ngoài allowlist, số lần deny tăng đột biến hoặc production reflection được bật ngoài cấu hình dự kiến. Việc bật reflection nên là thay đổi cấu hình có review và có thể audit.

## 9. Fallback khi reflection bị tắt

Tắt reflection không ngăn nhóm vận hành kiểm tra contract. Có thể cung cấp descriptor set đã build và version hóa cùng release:

```bash
grpcurl -cacert operator-ca.pem \
  -protoset orders-release.protoset \
  orders.internal.example:8443 \
  acme.orders.v1.OrderService/GetOrder
```

Hoặc dùng file proto và import path:

```bash
grpcurl -cacert operator-ca.pem \
  -import-path ./proto \
  -proto orders.proto \
  orders.internal.example:8443 \
  describe acme.orders.v1.OrderService
```

Descriptor set nên được tạo trong build pipeline, lưu cùng artifact/release metadata và có version/checksum. Nó giúp công cụ dùng contract đã review mà không cần server công bố reflection. Tuy nhiên, descriptor set chỉ mô tả contract của bản build đó; cần kiểm tra release version để tránh dùng schema cũ cho server mới.

Nếu cần xác minh API đang chạy mà reflection bị tắt, dùng health/metrics và smoke RPC đã được cấp quyền, hoặc thực hiện kiểm tra qua một môi trường staging có reflection được kiểm soát. Không bật reflection public tạm thời chỉ để thuận tiện cho một lần debug.

## 10. Cấu hình Spring và kiểm tra profile

Với Spring, quản lý reflection như một tính năng cấu hình có điều kiện. Property ví dụ:

```yaml
app:
  grpc:
    reflection:
      enabled: false
      operator-only: true
```

operator-only ở đây là property do ứng dụng định nghĩa để điều khiển cách đăng ký/bảo vệ reflection, không phải property chuẩn của mọi starter. Ứng dụng cần kiểm tra startup configuration: nếu reflection bật mà thiếu TLS hoặc operator authorization bean, fail startup thay vì tự động mở truy cập.

Một checklist khi khởi động:

- Profile đang chạy có đúng với môi trường deploy không?
- Reflection có được đăng ký khi và chỉ khi policy cho phép không?
- Interceptor/operator identity có được gắn vào reflection service không?
- Listener có dùng TLS/mTLS và trust material đúng không?
- Gateway/network policy có giới hạn reflection path không?
- Audit và rate limit có được bật không?
- Shutdown có dừng reflection listener và tài nguyên liên quan không?

Nếu dùng Spring gRPC starter, viết integration test trên đúng server do starter tạo. Một test tự dựng ServerBuilder độc lập chỉ chứng minh grpc-java configuration; nó không chứng minh conditional bean hoặc customizer của Spring đã chạy.

## 11. Kiểm thử bảo mật reflection trong production

Kiểm thử cần xác minh cả cấu hình được phép và đường truy cập bị cấm:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Production reflection disabled | Reflection method không được đăng ký hoặc bị gateway chặn |
| Local/staging reflection enabled | Operator test có thể list và describe |
| Không có credential | Reflection bị từ chối |
| Token sai/hết hạn | Bị từ chối, không lộ thông tin credential |
| Identity hợp lệ nhưng không có role operator | PERMISSION_DENIED |
| Operator hợp lệ qua TLS | Có thể đọc descriptor theo policy |
| Client certificate không tin cậy | TLS handshake thất bại |
| Gọi qua public ingress | Reflection không truy cập được nếu policy yêu cầu internal-only |
| Reflection v1/v1alpha | Tất cả path được server hỗ trợ đều tuân thủ cùng policy |
| Business RPC không có quyền | Vẫn bị từ chối dù caller có thể đọc descriptor |
| Descriptor fallback | Protoset đúng release dùng được khi reflection tắt |
| Spring profile switch | Server đăng ký đúng service theo profile và không có listener phụ ngoài ý muốn |
| Audit/rate limit | Ghi identity/status đúng và giới hạn stream/request bất thường |

Sau mỗi deploy, có thể chạy smoke test từ operator network: xác minh endpoint production không công khai reflection, endpoint quản trị yêu cầu identity, và descriptor trả về đúng release. Đồng thời kiểm tra một business RPC không được phép vẫn bị từ chối.

## 12. Bài tập vận dụng

Một Spring gRPC service chạy trên Kubernetes. Nhóm phát triển muốn dùng grpcurl để điều tra staging; production có các service nội bộ như AdminService và OrderService. Security yêu cầu chỉ operator qua mTLS được xem descriptor, còn caller ứng dụng chỉ được gọi business method theo role.

**Yêu cầu:**

1. Đề xuất profile/configuration để bật reflection ở local/staging và tắt trên public production listener.
2. Nếu production cần reflection, thiết kế endpoint quản trị nội bộ và xác định descriptor source phải đồng bộ với server nghiệp vụ.
3. Gắn authorization riêng cho reflection service; phân biệt quyền operator với quyền gọi AdminService/OrderService.
4. Cấu hình TLS/mTLS, SAN, trust chain và network allowlist.
5. Xác định reflection v1/v1alpha paths cần được gateway kiểm soát.
6. Thiết kế audit, rate limit và cảnh báo khi có truy cập trái phép.
7. Tạo descriptor set trong build pipeline để dùng khi reflection bị tắt.
8. Viết integration test theo production profile để xác minh reflection không public, operator access hoạt động và business authorization vẫn độc lập.

**Câu hỏi tự kiểm tra:**

- Reflection tiết lộ loại thông tin nào và vì sao nó có thể hỗ trợ reconnaissance?
- Vì sao TLS không thay thế authentication/authorization?
- Reflection authorization ở cấp call khác việc lọc descriptor theo service như thế nào?
- Vì sao tắt reflection không đồng nghĩa business RPC đã an toàn?
- Khi nào cần endpoint quản trị riêng và phải chú ý gì về descriptor source?
- Làm thế nào bảo vệ cả reflection v1 và v1alpha qua gateway?
- Descriptor set giúp vận hành ra sao khi reflection bị tắt?
- Test nào chứng minh production không vô tình công khai reflection?

**Ghi nhớ:** Production nên tắt reflection nếu không cần; nếu cần thì chỉ cấp cho operator qua TLS/mTLS, authentication, authorization và network policy. Bảo vệ reflection service riêng, giữ business RPC authorization độc lập, audit truy cập và kiểm soát mọi protocol path được hỗ trợ. Trong Spring gRPC, quản lý việc đăng ký theo profile/lifecycle, kiểm thử trên server thực do starter tạo và version hóa descriptor set làm phương án khám phá contract khi reflection không được mở.
