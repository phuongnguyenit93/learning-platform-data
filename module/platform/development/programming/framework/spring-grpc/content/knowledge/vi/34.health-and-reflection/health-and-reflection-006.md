# Server reflection dùng để khám phá service

Server reflection là giao thức gRPC cho phép client và công cụ vận hành hỏi một server đang cung cấp những service, method và message type nào. Nhờ reflection, công cụ như grpcurl có thể liệt kê API, đọc mô tả service và gọi RPC mà không cần người dùng cung cấp trước các file .proto tương ứng.

Trong Spring gRPC, reflection hữu ích khi phát triển, kiểm thử tích hợp và xử lý sự cố ở môi trường đã triển khai. Nó công bố **descriptor của API đang đăng ký trên server**; nó không tìm địa chỉ server, không xác nhận server khỏe và không thay thế contract source trong repository. Cần hiểu rõ dữ liệu reflection trả về, cách bật nó trong server lifecycle và phạm vi bảo mật trước khi mở endpoint này ở production.

## 1. Reflection giải quyết vấn đề gì?

Thông thường, client được sinh mã từ .proto đã biết. Nhưng khi kiểm tra một server từ xa, người vận hành có thể chưa có đúng phiên bản proto hoặc chưa biết service name. Reflection cho phép truy vấn descriptor trực tiếp từ server:

- Liệt kê các service server công bố.
- Xem service có những RPC method nào.
- Lấy descriptor của file chứa một symbol/service.
- Theo dõi các file proto phụ thuộc để giải mã request/response type.
- Dùng schema được khám phá để tạo request JSON và gọi RPC bằng công cụ CLI.

Ví dụ, thay vì tìm file proto trong repository trước, người vận hành có thể hỏi server:

```text
grpcurl -plaintext localhost:9090 list
grpcurl -plaintext localhost:9090 describe acme.orders.v1.OrderService
```

Lệnh đầu liệt kê service; lệnh sau hiển thị cấu trúc service mà server công bố. Reflection giúp khám phá API đang chạy, rất hữu ích khi so sánh môi trường staging và production hoặc xác minh rollout đã đưa descriptor mới lên server.

## 2. Reflection protocol trả về dữ liệu gì?

gRPC reflection định nghĩa service đặc biệt ServerReflection, trong đó RPC ServerReflectionInfo là một bidirectional streaming call. Client gửi các yêu cầu khám phá; server trả các response tương ứng trong cùng stream.

Các loại yêu cầu thường gặp:

| Yêu cầu | Mục đích |
| --- | --- |
| list_services | Liệt kê service server công bố |
| file_containing_symbol | Tìm file descriptor chứa một service, message hoặc symbol |
| file_by_filename | Lấy descriptor theo tên file proto |
| file_containing_extension | Tìm file định nghĩa extension |
| all_extension_numbers_of_type | Liệt kê extension number của một message type |

Response có thể chứa serialized FileDescriptorProto. Descriptor mô tả package, message, field number/type, enum, service, method, input/output type và dependency tới file proto khác. Công cụ cần xây dựng descriptor graph từ các file được trả về để hiểu đầy đủ kiểu dữ liệu.

Reflection trả về schema/descriptor, không trả về dữ liệu nghiệp vụ của request hoặc database. Nó cũng không bảo đảm khôi phục nguyên văn file .proto như trong repository: định dạng, comment và các chi tiết nguồn có thể không có trong descriptor được công bố.

## 3. Bật server reflection trong grpc-java

Implementation reflection của grpc-java nằm trong artifact grpc-services. Hãy dùng phiên bản tương thích với các thư viện grpc-java còn lại trong ứng dụng; tránh trộn các phiên bản grpc API khác nhau.

Với server được tạo trực tiếp bằng grpc-java:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.protobuf.services.ProtoReflectionService;

Server server = ServerBuilder.forPort(9090)
    .addService(new OrdersService())
    .addService(new InventoryService())
    .addService(ProtoReflectionService.newInstance())
    .build()
    .start();
```

ProtoReflectionService.newInstance() đăng ký reflection service trên server. Các service nghiệp vụ cũng phải được đăng ký trên chính server đó thì descriptor của chúng mới xuất hiện trong danh sách. Service chỉ tồn tại trong file proto nhưng chưa được đăng ký không tự động trở thành service đang phục vụ.

Nếu ứng dụng dùng Spring gRPC starter quản lý server, đăng ký reflection qua cơ chế thêm BindableService hoặc server customizer mà phiên bản starter hỗ trợ. Không tạo một server thứ hai chỉ để bật reflection; việc đó có thể mở thêm port, dùng TLS/auth khác và làm công cụ khám phá nhầm endpoint. Nên để server và reflection service cùng lifecycle, cấu hình transport và chính sách truy cập.

## 4. Khám phá service bằng grpcurl

Khi reflection đã được bật và server local dùng plaintext:

```bash
# Liệt kê service
grpcurl -plaintext localhost:9090 list

# Liệt kê method của một service
grpcurl -plaintext localhost:9090 list acme.orders.v1.OrderService

# Xem descriptor của service
grpcurl -plaintext localhost:9090 describe acme.orders.v1.OrderService

# Xem cấu trúc message
grpcurl -plaintext localhost:9090 describe acme.orders.v1.GetOrderRequest
```

Để gọi một unary method, grpcurl có thể dựng message từ JSON:

```bash
grpcurl -plaintext \
  -d '{"orderId":"ORD-42"}' \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

Tên JSON thường dùng lowerCamelCase tương ứng với field Protobuf snake_case. grpcurl dùng descriptor để xác định field, kiểu dữ liệu và method signature, rồi encode request thành Protobuf wire format.

Nếu server bật authentication, công cụ phải gửi credential hợp lệ theo chính sách của server:

```bash
grpcurl -plaintext \
  -H 'authorization: Bearer TOKEN' \
  localhost:9090 list
```

Không dùng plaintext ngoài môi trường local/test được kiểm soát. Khi dùng production, cấu hình TLS trust và hostname đúng với certificate.

## 5. Dùng reflection qua TLS và mTLS

Reflection là một RPC trên cùng gRPC server nên chịu ảnh hưởng của transport security và interceptor/authentication mà server áp dụng. TLS bảo vệ đường truyền và xác thực server; TLS tự nó không quyết định caller nào được phép đọc descriptor.

Ví dụ truy vấn server dùng certificate được CA tin cậy:

```bash
grpcurl -cacert ca.pem \
  orders.example.internal:8443 \
  list
```

Nếu server yêu cầu client certificate (mTLS), cung cấp certificate và private key theo cấu hình của grpcurl:

```bash
grpcurl -cacert ca.pem \
  -cert client.pem \
  -key client-key.pem \
  orders.example.internal:8443 \
  list
```

Hostname dùng để kết nối cần khớp SAN trong certificate hoặc authority được cấu hình có chủ đích. Không dùng -insecure, tắt hostname verification hoặc chuyển sang plaintext để vượt qua lỗi certificate. Nếu reflection bị authentication interceptor bảo vệ, gửi thêm metadata credential được cấp cho công cụ vận hành.

## 6. Reflection khác service discovery và health checking

Ba cơ chế này trả lời ba câu hỏi khác nhau:

| Cơ chế | Câu hỏi | Dữ liệu cung cấp |
| --- | --- | --- |
| Service discovery | Kết nối tới instance nào? | DNS name, địa chỉ IP/port hoặc endpoint từ registry |
| Health checking | Service có sẵn sàng nhận RPC không? | Trạng thái như SERVING hoặc NOT_SERVING |
| Server reflection | Server cung cấp API nào? | Service/method/message descriptors |

Reflection không tìm endpoint và không báo readiness. DNS phân giải thành công không chứng minh server có service mà client cần; reflection liệt kê service cũng không chứng minh business dependency đang khỏe. Khi điều tra lỗi, kiểm tra riêng target/transport, health state và service descriptor.

Reflection cũng không thay thế generated stub. Ứng dụng production thường tiếp tục dùng client được sinh từ contract đã version hóa; reflection phù hợp hơn cho khám phá động, CLI, debug và công cụ quản trị.

## 7. Bảo mật và quyết định bật reflection ở production

Descriptor có thể tiết lộ tên service nội bộ, method quản trị, cấu trúc request/response và các capability mà hệ thống cung cấp. Thông tin đó hữu ích cho người vận hành nhưng cũng hỗ trợ reconnaissance nếu endpoint công khai.

Trước khi bật reflection ở production, xác định:

- Ai được phép liệt kê service và tải descriptor?
- Reflection có nằm sau TLS/mTLS và authentication không?
- Authorization có giới hạn theo nhóm vận hành hoặc môi trường không?
- Reflection có cần được mở trên listener/port nội bộ riêng không?
- Audit có ghi lại caller, thời điểm và hoạt động khám phá cần thiết không?
- Công cụ health probe có bị interceptor bảo vệ reflection ảnh hưởng không?

Các lựa chọn phổ biến:

| Môi trường | Cách triển khai thường phù hợp |
| --- | --- |
| Local development | Bật reflection để grpcurl và IDE/tool khám phá dễ dàng |
| CI/integration test | Bật trên test server để xác minh descriptor và contract được đăng ký |
| Staging | Bật có kiểm soát cho nhóm phát triển/QA, dùng TLS và authentication giống production |
| Production public-facing | Tắt nếu không có nhu cầu vận hành; nếu cần thì giới hạn truy cập chặt chẽ |
| Production nội bộ | Có thể bật trên endpoint nội bộ, yêu cầu identity và audit phù hợp |

Không coi việc ẩn reflection là biện pháp bảo vệ API thay cho authentication/authorization. Client vẫn có thể gọi method đã biết nếu endpoint cho phép; mọi RPC nghiệp vụ phải tự áp dụng chính sách truy cập.

## 8. Khi reflection không khả dụng

Reflection có thể bị tắt, bị chặn bởi authentication hoặc không tương thích phiên bản công cụ. Khi đó grpcurl vẫn có thể dùng file proto hoặc descriptor set đã build:

```bash
# Dùng file proto và import path
grpcurl -plaintext \
  -import-path ./src/main/proto \
  -proto orders.proto \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder

# Dùng descriptor set đã biên dịch
grpcurl -plaintext \
  -protoset orders.protoset \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

Descriptor set hữu ích cho CI và môi trường production không bật reflection. Nó cũng giúp công cụ dùng đúng contract version đã được build và review. Tuy nhiên, file descriptor set phải được quản lý/version hóa cùng client; descriptor cũ có thể không phản ánh API thực tế đang chạy.

Reflection protocol có các phiên bản API khác nhau theo hệ sinh thái và thời điểm phát hành. Hãy kiểm tra grpc-java grpc-services và grpcurl tương thích với nhau. Nếu server và công cụ không thống nhất reflection protocol version, dùng proto/protoset là phương án rõ ràng để tiếp tục kiểm thử.

## 9. Kiểm tra descriptor và contract drift

Reflection rất hữu ích để so sánh API đang chạy với contract mong đợi. Có thể tự động hóa smoke test sau khi deploy:

1. Kết nối tới endpoint bằng TLS và credential của test operator.
2. Gọi list và xác nhận các service bắt buộc xuất hiện.
3. Gọi describe cho service quan trọng.
4. Xác nhận method name, input type và output type mong đợi.
5. Kiểm tra imported descriptor cần thiết có thể được truy vấn.
6. Gọi một RPC smoke test an toàn để xác minh route và behavior.

Ví dụ kiểm tra bằng CLI:

```bash
grpcurl -cacert ca.pem \
  -H 'authorization: Bearer TEST_OPERATOR_TOKEN' \
  orders.example.internal:8443 \
  describe acme.orders.v1.OrderService
```

Output cần được so sánh với contract hoặc descriptor set đã review. Không nên so sánh toàn bộ output text theo byte nếu grpcurl có thể thay đổi format; hãy kiểm tra các service/method/type cần thiết hoặc so sánh descriptor có cấu trúc.

Reflection cho biết server đang công bố descriptor nào, nhưng không chứng minh tất cả method hoạt động đúng. Một service có thể được đăng ký và xuất hiện trong list trong khi method trả UNIMPLEMENTED, UNAVAILABLE hoặc lỗi nghiệp vụ. Cần kết hợp descriptor check với integration/smoke test.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| grpcurl list báo reflection không hỗ trợ | Chưa đăng ký reflection service hoặc server tắt reflection | Kiểm tra server registration và đúng endpoint |
| Reflection service xuất hiện nhưng service nghiệp vụ không có | Service chưa được đăng ký trên server đang hỏi | Kiểm tra server instance, port và service registration |
| describe không tìm thấy symbol | Sai fully qualified name hoặc descriptor dependency không được công bố | Đối chiếu proto package/service và imported files |
| TLS handshake thất bại | CA, SAN, authority hoặc client certificate sai | Kiểm tra trust chain và hostname |
| UNAUTHENTICATED/PERMISSION_DENIED | Reflection chịu interceptor/auth policy | Gửi credential phù hợp hoặc kiểm tra quyền operator |
| list thành công nhưng gọi method lỗi | Descriptor có nhưng handler/backend lỗi hoặc request sai | Kiểm tra method path, status và service logs |
| Local chạy được, staging không | Reflection tắt, network policy hoặc phiên bản protocol khác | Kiểm tra cấu hình theo profile và compatibility |
| Reflection làm lộ API nội bộ | Endpoint mở rộng hơn nhóm operator | Giới hạn listener, identity và authorization |

Luôn xác nhận đúng hostname/port đang kiểm tra. Một lệnh grpcurl thành công ở local chỉ chứng minh local server đã đăng ký reflection; nó không chứng minh staging/production có cùng cấu hình.

## 11. Kiểm thử reflection trong Spring gRPC

Nên kiểm thử cả việc đăng ký reflection lẫn nội dung descriptor:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Reflection được đăng ký | list_services trả reflection service và các service nghiệp vụ dự kiến |
| Service registration | Service không đăng ký không xuất hiện |
| Descriptor lookup | describe/symbol lookup trả đúng service, method và message type |
| Imported proto | Descriptor dependency có thể được truy vấn đầy đủ |
| Unary smoke call | Method đã khám phá có thể được gọi bằng đúng path/request |
| Reflection disabled | Công cụ nhận lỗi reflection rõ ràng; proto/protoset vẫn dùng được |
| Authentication | Caller thiếu credential bị từ chối theo policy |
| Authorization | Operator có quyền khám phá; caller không có quyền không tải được descriptor nếu policy yêu cầu |
| TLS/mTLS | Trust chain và client identity được kiểm tra đúng |
| Spring lifecycle | Reflection service được đăng ký trên server do Spring quản lý và dừng cùng server |
| Version compatibility | grpc-java reflection và công cụ CLI tương thích |

In-process server test phù hợp để kiểm tra registration và descriptor protocol. Thêm TCP/TLS integration test khi cần xác minh certificate, ingress, service mesh hoặc authentication metadata qua network. Không dùng test tự dựng một ServerBuilder riêng để kết luận Spring starter production đã đăng ký reflection đúng; hãy gọi endpoint qua server/channel do Spring context tạo.

## 12. Bài tập vận dụng

Một nhóm vận hành cần kiểm tra OrderService trong staging sau mỗi lần deploy. Hiện nhóm phải tìm file .proto đúng phiên bản trong nhiều repository; một số lần grpcurl gọi nhầm method do service package thay đổi. Production chỉ cho phép operator đã xác thực xem API descriptor.

**Yêu cầu:**

1. Bật ProtoReflectionService trên server staging thông qua lifecycle/configuration hook của Spring gRPC.
2. Dùng grpcurl liệt kê service và mô tả acme.orders.v1.OrderService.
3. Gọi một unary smoke method bằng JSON request dựa trên descriptor.
4. Cấu hình production reflection sau TLS/mTLS và authorization dành cho operator.
5. Kiểm tra health checking và service discovery vẫn được vận hành độc lập với reflection.
6. Tạo smoke test xác minh service/method/type sau deploy và phát hiện contract drift.
7. Chuẩn bị descriptor set làm phương án kiểm tra khi reflection bị tắt hoặc công cụ không tương thích.

**Câu hỏi tự kiểm tra:**

- Reflection giải quyết vấn đề gì khi người vận hành không có file proto đúng phiên bản?
- ServerReflectionInfo hỗ trợ những loại truy vấn descriptor nào?
- Vì sao reflection chỉ liệt kê service đã đăng ký trên server?
- Reflection khác service discovery và health checking ra sao?
- TLS có tự động giới hạn ai được tải descriptor không?
- Khi nào nên tắt hoặc giới hạn reflection trong production?
- Khi reflection không khả dụng, grpcurl có thể dùng những nguồn schema nào?
- Vì sao list/describe thành công chưa chứng minh RPC nghiệp vụ hoạt động?

**Ghi nhớ:** Server reflection cho phép công cụ khám phá service và descriptor đang được gRPC server công bố. Trong Spring gRPC, đăng ký reflection trên đúng server lifecycle, dùng grpcurl để list/describe/smoke call, và bảo vệ descriptor bằng TLS cùng authentication/authorization phù hợp. Reflection không thay service discovery, health checking hay contract source; hãy kiểm thử descriptor sau deploy và duy trì proto/protoset làm nguồn contract có version.
