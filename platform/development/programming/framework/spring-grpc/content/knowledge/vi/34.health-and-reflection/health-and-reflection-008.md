# grpcurl và kiểm tra endpoint

grpcurl là công cụ dòng lệnh để gọi và kiểm tra gRPC endpoint. Nó có thể khám phá service qua server reflection, đọc contract từ file .proto hoặc descriptor set, tạo request JSON rồi gọi RPC. Nhờ đó, người phát triển có thể xác minh một Spring gRPC server đã mở đúng port, công bố đúng service, vượt qua TLS/authentication và thực thi được method nghiệp vụ.

Trong module SPRING_GRPC, endpoint cần được kiểm tra theo nhiều lớp: địa chỉ và transport, service descriptor, health state, quyền truy cập và kết quả RPC. Một lệnh list thành công chỉ chứng minh reflection có thể trả lời; nó không chứng minh business method hoạt động. Tương tự, TCP/TLS kết nối được không bảo đảm client đang gọi đúng service path.

## 1. grpcurl kiểm tra được những gì?

grpcurl là client gRPC tổng quát. Nó sử dụng descriptor để mã hóa request JSON thành Protobuf và giải mã response về JSON. Các công việc thường gặp:

- Kiểm tra kết nối tới host và port gRPC.
- Liệt kê service và method server công bố.
- Xem cấu trúc message, field và kiểu dữ liệu.
- Gọi unary RPC bằng JSON request.
- Gửi metadata phục vụ authentication, tenant hoặc tracing.
- Kết nối plaintext trong local/test hoặc TLS/mTLS trong môi trường bảo mật.
- Gọi health checking RPC nếu server đã đăng ký health service.
- Dùng .proto hoặc descriptor set khi server tắt reflection.

grpcurl không phải công cụ thay thế load test, health monitoring liên tục hay kiểm tra toàn bộ business workflow. Nó phù hợp với smoke test, điều tra lỗi và xác minh một endpoint tại một thời điểm.

## 2. Xác định đúng địa chỉ và service path

Một gRPC endpoint thường được chỉ định bằng hostname/IP và port, ví dụ:

```text
localhost:9090
orders.default.svc.cluster.local:8443
orders.example.internal:443
```

Trong grpcurl, truyền địa chỉ host:port. URI resolver như dns:///orders.default.svc.cluster.local:8443 thường được cấu hình cho ManagedChannel của ứng dụng; khi gọi grpcurl, dùng hostname/port thực tế:

```bash
grpcurl orders.default.svc.cluster.local:8443 list
```

Địa chỉ chỉ xác định nơi kết nối. Tên service và method được hình thành từ contract Protobuf. Ví dụ proto khai báo:

```proto
package acme.orders.v1;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}
```

Tên đầy đủ là acme.orders.v1.OrderService, còn RPC path là:

```text
/acme.orders.v1.OrderService/GetOrder
```

Không dùng Java package trong java_package để thay cho proto package khi gọi RPC. Cũng không dùng DNS name hoặc tên registry thay cho fully qualified service name. Nếu client kết nối được nhưng gọi sai path, server có thể trả UNIMPLEMENTED.

## 3. Khám phá service bằng reflection

Khi server bật reflection, grpcurl có thể lấy descriptor trực tiếp:

```bash
# Liệt kê service
grpcurl -plaintext localhost:9090 list

# Liệt kê method của một service
grpcurl -plaintext localhost:9090 list acme.orders.v1.OrderService

# Xem descriptor service
grpcurl -plaintext localhost:9090 describe acme.orders.v1.OrderService

# Xem descriptor message
grpcurl -plaintext localhost:9090 describe acme.orders.v1.GetOrderRequest
```

-plaintext yêu cầu kết nối không TLS; chỉ dùng cho local hoặc test network đã được kiểm soát. Nếu endpoint dùng TLS, bỏ flag này và cấu hình CA/certificate phù hợp.

Kết quả list cho biết service server đang công bố. describe cho biết method, input/output type và cấu trúc message. Nếu một service có trong file proto nhưng chưa được đăng ký trên server, reflection không tự liệt kê service đó.

## 4. Khi reflection bị tắt: dùng proto hoặc protoset

Production có thể tắt reflection để hạn chế công bố descriptor. grpcurl vẫn gọi được RPC nếu được cung cấp contract:

```bash
# Dùng file proto và import path
grpcurl -plaintext \
  -import-path ./src/main/proto \
  -proto orders.proto \
  localhost:9090 \
  describe acme.orders.v1.OrderService

# Dùng descriptor set đã build
grpcurl -plaintext \
  -protoset orders.protoset \
  localhost:9090 \
  describe acme.orders.v1.OrderService
```

Có thể tạo descriptor set trong build pipeline:

```bash
protoc -I proto \
  --include_imports \
  --descriptor_set_out=orders.protoset \
  orders.proto
```

--include_imports đóng gói các descriptor phụ thuộc để grpcurl có đủ schema khi giải mã message. File protoset cần được version hóa cùng release; dùng descriptor cũ có thể khiến request không khớp API đang chạy.

Reflection và file schema trả lời hai nhu cầu khác nhau: reflection cho biết descriptor server đang công bố; .proto/protoset cho phép kiểm tra theo contract đã được build và review. Nếu hai nguồn không khớp, điều tra contract drift thay vì sửa request theo phỏng đoán.

## 5. Gọi unary RPC bằng JSON

Sau khi có descriptor, gửi request JSON với -d:

```bash
grpcurl -plaintext \
  -d '{"orderId":"ORD-42"}' \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

grpcurl chuyển JSON thành message Protobuf dựa trên descriptor. Một số quy tắc thường gặp:

- Tên field JSON thường là lowerCamelCase tương ứng với field Protobuf snake_case.
- Enum dùng tên symbol theo contract.
- bytes được biểu diễn bằng Base64 trong JSON mapping của Protobuf.
- Message lồng nhau dùng object JSON.
- repeated dùng JSON array.
- Field có presence cần được xử lý đúng với semantics của schema.

Có thể xem request template theo descriptor trước khi gọi:

```bash
grpcurl -plaintext \
  -msg-template \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

Smoke test nên chọn method an toàn, có dữ liệu test xác định và không tạo side effect không mong muốn. Với method ghi dữ liệu, dùng test tenant/database hoặc một request idempotent được thiết kế cho kiểm tra.

## 6. Gửi metadata và credential

Nhiều endpoint yêu cầu bearer token, API key hoặc metadata tenant. grpcurl cho phép thêm header vào RPC:

```bash
grpcurl -plaintext \
  -H 'authorization: Bearer OPERATOR_TOKEN' \
  -H 'x-tenant-id: test-tenant' \
  -d '{"orderId":"ORD-42"}' \
  localhost:9090 \
  acme.orders.v1.OrderService/GetOrder
```

Nếu reflection service cũng yêu cầu authentication, grpcurl có option -reflect-header để gửi metadata cho các request reflection. Header dùng cho reflection và header dùng cho RPC invocation là hai giai đoạn khác nhau; cấu hình đúng theo chính sách server.

Không đặt token dài hạn trực tiếp trong script hoặc commit vào repository. Command line có thể xuất hiện trong shell history hoặc process inspection; dùng token ngắn hạn, secret injection của CI hoặc cơ chế credential được tổ chức phê duyệt. Không ghi authorization metadata vào log.

Metadata không tự tạo danh tính đáng tin cậy. Server phải xác minh credential rồi mới gắn principal/role/tenant vào context. Một x-tenant-id do caller gửi chỉ là input, không phải bằng chứng caller được phép truy cập tenant đó.

## 7. Kiểm tra TLS và mTLS

Với TLS, grpcurl cần tin cậy CA ký certificate server và kết nối bằng hostname khớp SAN:

```bash
grpcurl -cacert ca.pem \
  orders.example.internal:8443 \
  list
```

Nếu server yêu cầu mutual TLS, gửi thêm client certificate và private key:

```bash
grpcurl -cacert ca.pem \
  -cert operator-client.pem \
  -key operator-client-key.pem \
  orders.example.internal:8443 \
  list
```

Nếu kết nối bằng IP hoặc hostname khác SAN, cần cấu hình certificate/authority theo thiết kế PKI của hệ thống; không dùng -insecure để bỏ qua xác minh. -plaintext không phải cách khắc phục TLS handshake failure trong staging/production.

Khi chẩn đoán TLS, kiểm tra:

- CA bundle có chứa trust anchor phù hợp không?
- Certificate server còn hạn và có SAN khớp hostname không?
- Server có yêu cầu client certificate không?
- Client certificate có được CA server tin cậy ký không?
- Proxy/ingress có terminate TLS hay passthrough HTTP/2 không?
- Authority/SNI mà client gửi có phù hợp cấu hình listener không?

TLS thành công xác nhận một phần transport identity; vẫn cần authentication/authorization ở tầng RPC nếu ứng dụng yêu cầu.

## 8. Kiểm tra gRPC health service

gRPC có health checking protocol chuẩn trong package grpc.health.v1. Nếu server đăng ký health service, có thể gọi Check để hỏi trạng thái của toàn server hoặc một service cụ thể:

```bash
# Kiểm tra trạng thái toàn server
grpcurl -plaintext \
  -d '{"service":""}' \
  localhost:9090 \
  grpc.health.v1.Health/Check

# Kiểm tra một service cụ thể
grpcurl -plaintext \
  -d '{"service":"acme.orders.v1.OrderService"}' \
  localhost:9090 \
  grpc.health.v1.Health/Check
```

Response thường chứa trạng thái như SERVING hoặc NOT_SERVING. Với RPC Check, service name không được health manager biết thường được trả về dưới dạng status NOT_FOUND; trạng thái SERVICE_UNKNOWN được dùng trong phản hồi Watch. Nếu server không đăng ký health service, grpcurl sẽ không tìm thấy method health dù business service vẫn có thể hoạt động.

Health SERVING là tín hiệu readiness theo logic health manager, không chứng minh mọi RPC nghiệp vụ đều thành công. Hãy kết hợp health check với một smoke RPC có quyền và dữ liệu phù hợp.

## 9. Phân biệt endpoint reachability, readiness và business behavior

Một endpoint có thể vượt qua một lớp kiểm tra nhưng thất bại ở lớp khác:

| Lớp | Cách kiểm tra | Điều được chứng minh |
| --- | --- | --- |
| DNS/network | Phân giải hostname, mở được TCP connection | Địa chỉ có thể tiếp cận |
| TLS/transport | grpcurl kết nối bằng TLS và hoàn tất HTTP/2 handshake | Transport và trust cơ bản hoạt động |
| Reflection | list/describe | Reflection service trả descriptor |
| Health | grpc.health.v1.Health/Check | Health service công bố trạng thái |
| Authentication | Gọi với credential hợp lệ/không hợp lệ | Identity policy hoạt động |
| Business RPC | Gọi method thực tế với request hợp lệ | Routing, handler và dependency cần thiết hoạt động cho ca đó |

Service discovery tìm endpoint; health checking báo trạng thái; reflection mô tả API; grpcurl kết hợp chúng thành các phép kiểm tra chủ động. Không xem list thành công là bằng chứng readiness, và không dùng một health response thay cho kiểm thử nghiệp vụ.

Với Kubernetes, DNS service thường trỏ tới ClusterIP hoặc endpoint do cluster quản lý. grpcurl từ máy developer, pod trong cluster và runner CI có thể có network path khác nhau. Khi endpoint chỉ truy cập nội bộ, chạy kiểm tra từ đúng network boundary hoặc một operator pod được kiểm soát.

## 10. Đọc status và chẩn đoán lỗi

Kết quả grpcurl thường giúp khoanh vùng lỗi theo tầng:

| Triệu chứng/status | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Connection refused | Không có listener tại host/port hoặc port mapping sai | Service port, target port, pod/listener |
| DNS lookup failure | Tên host sai hoặc DNS không phân giải được | Namespace, service DNS, resolver/network |
| TLS handshake/certificate error | CA, SAN, expiry, client certificate hoặc SNI sai | Trust chain và TLS configuration |
| Reflection not supported | Reflection chưa được đăng ký hoặc bị chặn | Dùng proto/protoset hoặc kiểm tra policy |
| UNIMPLEMENTED | Sai service/method path hoặc server không đăng ký method | Proto package, service name, deployed version |
| UNAUTHENTICATED | Thiếu hoặc sai credential | Token, metadata key, expiry và auth interceptor |
| PERMISSION_DENIED | Identity hợp lệ nhưng thiếu quyền | Role, scope, tenant policy |
| INVALID_ARGUMENT | JSON/request không phù hợp contract hoặc validation | Field name/type, presence semantics và validation |
| NOT_FOUND | Resource nghiệp vụ không tồn tại | Test data và resource identifier |
| DEADLINE_EXCEEDED | RPC vượt deadline hoặc queue/network quá lâu | Deadline, latency, dependency và server load |
| UNAVAILABLE | Server/backend/transport không sẵn sàng | Endpoint, health, reconnect và load balancer |
| RESOURCE_EXHAUSTED | Quota, message limit hoặc capacity limit | Payload size, rate limit, concurrency và heap |

Status chỉ là tín hiệu để bắt đầu điều tra. Ví dụ UNAVAILABLE có thể phát sinh từ client transport, proxy hoặc server; cần đối chiếu server logs, metrics và trace. Không tự động retry mọi lỗi: RPC ghi dữ liệu có thể đã được xử lý trước khi response bị mất.

## 11. Tạo endpoint smoke test có thể lặp lại

Một smoke test sau deploy nên có thứ tự và tiêu chí rõ:

1. Kết nối đúng hostname/port từ network boundary của caller.
2. Xác minh TLS/mTLS và credential operator.
3. Khám phá service qua reflection hoặc dùng descriptor set đúng release.
4. Xác nhận service/method bắt buộc tồn tại.
5. Gọi health Check cho service name đầy đủ nếu health service được bật.
6. Gọi một unary RPC an toàn với dữ liệu test.
7. Kiểm tra status, response và thời gian hoàn thành.
8. Ghi lại endpoint, release/version, thời điểm, status và correlation ID; không ghi token hoặc payload nhạy cảm.

Ví dụ shell script tối giản cho local plaintext:

```bash
#!/usr/bin/env bash
set -euo pipefail

TARGET="localhost:9090"
SERVICE="acme.orders.v1.OrderService"

grpcurl -max-time 5 -plaintext "$TARGET" list
grpcurl -max-time 5 -plaintext "$TARGET" describe "$SERVICE"
grpcurl -max-time 5 -plaintext \
  -d '{"service":"'"$SERVICE"'"}' \
  "$TARGET" grpc.health.v1.Health/Check
```

Đây chỉ là skeleton: cần thay endpoint, auth, schema và smoke method theo môi trường. CI production-like nên dùng TLS, secret ngắn hạn, timeout hữu hạn và descriptor/version đã được pin. Đảm bảo script trả exit code khác 0 khi một bước thất bại để pipeline không đánh dấu deploy thành công giả.

Không gọi method có side effect chỉ để chứng minh endpoint sống. Nếu cần kiểm tra business path, tạo một method health/smoke chuyên dụng hoặc dữ liệu test có thể dọn dẹp an toàn.

## 12. Bài tập vận dụng

Một ứng dụng Spring gRPC triển khai OrderService trên Kubernetes. Local dùng plaintext và reflection; staging dùng TLS cùng bearer token; production tắt reflection và chỉ operator qua mTLS được phép kiểm tra endpoint. Sau deploy, nhóm QA cần xác nhận đúng service version, health state và một unary method an toàn.

**Yêu cầu:**

1. Viết lệnh grpcurl list và describe cho local dùng reflection.
2. Tạo descriptor set có imports để kiểm tra staging/production khi reflection bị tắt.
3. Gọi GetOrder với JSON request và metadata authentication/tenant phù hợp.
4. Gọi health Check với fully qualified service name.
5. Cấu hình grpcurl qua CA và mTLS; xác minh hostname/SAN.
6. Phân loại các lỗi UNIMPLEMENTED, UNAUTHENTICATED, PERMISSION_DENIED, DEADLINE_EXCEEDED và UNAVAILABLE.
7. Tạo smoke test sau deploy có timeout, exit code, release identifier và không log secret.
8. Xác minh kiểm tra được chạy từ network boundary giống operator/client thực tế.

**Câu hỏi tự kiểm tra:**

- grpcurl dùng reflection để làm gì?
- Khi reflection bị tắt, cần cung cấp nguồn descriptor nào?
- Vì sao proto service name khác DNS target?
- list thành công có chứng minh business RPC sẵn sàng không?
- Health SERVING khác một unary smoke call thế nào?
- -H và -reflect-header phục vụ hai giai đoạn nào?
- Vì sao không dùng -insecure để sửa lỗi TLS?
- Khi nhận UNIMPLEMENTED, cần kiểm tra service path nào?
- Vì sao endpoint test phải chạy từ đúng network boundary?

**Ghi nhớ:** grpcurl giúp kiểm tra gRPC endpoint từ kết nối và descriptor tới health và business RPC. Dùng reflection khi được phép, hoặc pin .proto/protoset theo release; gửi metadata đúng contract; xác minh TLS/mTLS và hostname; gọi health cùng một smoke method an toàn. Đọc status theo từng lớp và tự động hóa kiểm tra với timeout, exit code, version và audit phù hợp.
