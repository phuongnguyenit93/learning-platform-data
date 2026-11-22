# Dùng grpcurl để thu hẹp nguyên nhân

`grpcurl` là công cụ dòng lệnh gửi request gRPC trực tiếp đến một endpoint. Công cụ này có thể đọc hợp đồng Protocol Buffers từ server thông qua reflection hoặc từ các file `.proto`/descriptor do dự án cung cấp. Nhờ vậy, ta có thể kiểm tra kết nối, TLS, service, method, metadata, deadline và phản hồi RPC mà không cần viết thêm một chương trình Java client.

Trong một dịch vụ Spring gRPC, `grpcurl` giúp xác định lỗi nằm ở đường truyền, cấu hình server, hợp đồng protobuf, xác thực hay phần xử lý nghiệp vụ. Kết quả của nó là một lát cắt tại thời điểm gọi; hãy ghép kết quả với log, trace và metric của ứng dụng để tìm nguyên nhân gốc.

## 1. Xác định đúng endpoint trước khi gọi

Một ứng dụng Spring có thể đồng thời mở cổng HTTP cho REST/Actuator và cổng riêng cho gRPC. Hai cổng này không thể thay thế cho nhau. Hãy lấy địa chỉ và cổng gRPC thực tế từ cấu hình đang có hiệu lực, log khởi động, manifest triển khai hoặc cấu hình Service/Ingress của môi trường.

Không mặc định cổng gRPC là `9090`: giá trị này chỉ xuất hiện trong nhiều ví dụ. Các thư viện tích hợp Spring gRPC có thể dùng tên thuộc tính và giá trị mặc định khác nhau. Cũng cần kiểm tra địa chỉ bind: server chỉ lắng nghe trên loopback sẽ không nhận kết nối từ container hoặc máy khác.

Ví dụ dưới đây giả sử server đang nghe plaintext tại `localhost:9090`. Hãy thay địa chỉ này bằng endpoint của môi trường cần kiểm tra.

```bash
grpcurl -plaintext localhost:9090 list
```

Lệnh trên đồng thời kiểm tra kết nối gRPC và yêu cầu server cung cấp danh sách service qua reflection. Nếu server dùng TLS, bỏ `-plaintext` và cấu hình chứng chỉ phù hợp ở bước tiếp theo.

Nên chạy phép thử từ cùng vị trí mạng với client đang gặp lỗi. Kết quả chạy trên laptop có thể khác kết quả chạy trong pod Kubernetes, container hoặc máy chủ ứng dụng vì DNS, route, firewall và service discovery khác nhau.

## 2. Phân biệt lỗi kết nối, HTTP/2 và TLS

gRPC sử dụng HTTP/2. Một cổng mở TCP chưa đủ để chứng minh endpoint phục vụ gRPC: proxy có thể định tuyến sai, chỉ hỗ trợ HTTP/1.1 ở upstream hoặc chuyển request sang cổng REST.

### Server plaintext

Với endpoint nội bộ không bật TLS:

```bash
grpcurl -plaintext localhost:9090 list
```

`-plaintext` yêu cầu grpcurl dùng kết nối không mã hóa. Chỉ dùng cách này khi endpoint thực sự được cấu hình plaintext, chẳng hạn một kết nối nội bộ trong môi trường phát triển. Nếu server yêu cầu TLS, lệnh này sẽ thất bại ở tầng transport.

### Server dùng TLS

Nếu server sử dụng chứng chỉ do CA nội bộ cấp, truyền CA tin cậy:

```bash
grpcurl -cacert ./certs/ca.pem api.example.internal:443 list
```

Nếu server yêu cầu mutual TLS (mTLS), truyền thêm chứng chỉ và private key của client:

```bash
grpcurl \
  -cacert ./certs/ca.pem \
  -cert ./certs/client.pem \
  -key ./certs/client.key \
  api.example.internal:443 list
```

Khi đi qua ingress hoặc proxy định tuyến theo host, có thể cần chỉ định authority:

```bash
grpcurl -authority api.example.internal api.example.internal:443 list
```

`-authority` đặt giá trị authority của request gRPC. Hãy dùng đúng hostname mà cấu hình proxy mong đợi; không dùng tùy chọn này để che lỗi DNS hoặc chứng chỉ sai.

Trong lúc khoanh vùng, `-insecure` có thể giúp xác định liệu lỗi có liên quan đến bước xác minh chứng chỉ hay không:

```bash
grpcurl -insecure api.example.internal:443 list
```

Tùy chọn này bỏ qua xác minh chứng chỉ máy chủ. Chỉ dùng trong phép thử ngắn, có kiểm soát; không đưa nó vào cấu hình client hoặc quy trình vận hành lâu dài. Nếu lệnh chỉ thành công khi có `-insecure`, hãy sửa chuỗi CA, SAN/hostname, thời hạn chứng chỉ hoặc cấu hình TLS thay vì giữ nguyên tùy chọn đó.

### Đọc lỗi transport

| Dấu hiệu | Tầng cần kiểm tra tiếp |
| --- | --- |
| `connection refused` | Không có tiến trình lắng nghe tại host/port đó, sai cổng, sai port mapping hoặc server chưa khởi động xong. |
| Lỗi phân giải hostname | DNS, tên service, namespace hoặc cấu hình resolver của môi trường chạy grpcurl. |
| Timeout hoặc `Unavailable` trước khi nhận status từ server | Route mạng, firewall, load balancer, endpoint không khỏe hoặc proxy không chuyển tiếp được kết nối. |
| Lỗi handshake, unknown authority hoặc hostname mismatch | CA tin cậy, SAN của chứng chỉ, hostname truy cập, chứng chỉ hết hạn và cấu hình mTLS. |
| HTTP status bất thường như 404/415 | Có thể đang gọi nhầm cổng HTTP, proxy định tuyến sai hoặc upstream không nói HTTP/2 theo cách gRPC yêu cầu. |

Nếu TLS kết thúc tại ingress nhưng kết nối ingress-to-service dùng plaintext, hãy kiểm tra riêng từng chặng. Thành công khi gọi trực tiếp pod chưa chứng minh đường đi qua ingress hoạt động, và ngược lại.

## 3. Kiểm tra service và mô tả method

Khi server bật gRPC reflection, có thể liệt kê service:

```bash
grpcurl -plaintext localhost:9090 list
```

Sau đó xem các method và kiểu request/response của một service:

```bash
grpcurl -plaintext localhost:9090 describe acme.greeter.v1.Greeter
```

Tên đầy đủ của service được tạo từ `package` trong file `.proto` và tên service. Tên này không nhất thiết trùng với Java package, tên class implementation hay tên bean Spring. Method được gọi bằng dạng `package.Service/Method`, phân biệt chữ hoa chữ thường.

Ví dụ hợp đồng:

```protobuf
syntax = "proto3";

package acme.greeter.v1;

service Greeter {
  rpc SayHello (HelloRequest) returns (HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
```

Với hợp đồng trên, tên RPC là `acme.greeter.v1.Greeter/SayHello`.

### Khi reflection không được bật

Thông báo server không hỗ trợ reflection không chứng minh service bị dừng hoặc chưa đăng ký. Reflection là một service riêng, có thể bị tắt trong cấu hình hoặc bị chặn bởi chính sách bảo mật. Khi đó, đưa file `.proto` của đúng phiên bản API vào grpcurl:

```bash
grpcurl \
  -plaintext \
  -import-path . \
  -proto proto/greeter/v1/greeter.proto \
  localhost:9090 \
  list
```

`-import-path` chỉ định thư mục gốc để phân giải các câu lệnh `import`; `-proto` chỉ định file mô tả service. Nếu file phụ thuộc vào nhiều proto khác, thêm các import path hoặc file proto cần thiết.

Có thể đóng gói descriptor cùng các dependency bằng `protoc`:

```bash
protoc -I . \
  --include_imports \
  --descriptor_set_out=build/api.protoset \
  proto/greeter/v1/greeter.proto
```

Sau đó dùng descriptor set:

```bash
grpcurl -plaintext \
  -protoset build/api.protoset \
  localhost:9090 \
  describe acme.greeter.v1.Greeter
```

Descriptor phải tương ứng với phiên bản server đang chạy. Nếu dùng proto cũ, grpcurl có thể tạo request thiếu field, dùng sai kiểu dữ liệu hoặc gọi method không còn tồn tại. Hãy lấy proto/protoset từ đúng commit hoặc artifact đã triển khai.

## 4. Gọi thử một unary RPC

Sau khi đã xác định đúng service, method và descriptor, gửi một request nhỏ có dữ liệu hợp lệ:

```bash
grpcurl -plaintext \
  -import-path . \
  -proto proto/greeter/v1/greeter.proto \
  -d '{"name":"An"}' \
  localhost:9090 \
  acme.greeter.v1.Greeter/SayHello
```

Nếu reflection đang bật và không cần file proto cục bộ, có thể bỏ `-import-path` và `-proto`:

```bash
grpcurl -plaintext \
  -d '{"name":"An"}' \
  localhost:9090 \
  acme.greeter.v1.Greeter/SayHello
```

grpcurl nhận request ở dạng JSON theo quy tắc ánh xạ JSON của Protocol Buffers. Tên field thường dùng lowerCamelCase; enum dùng tên enum; `bytes` được biểu diễn bằng Base64; các kiểu số nguyên 64-bit thường được biểu diễn dưới dạng chuỗi trong JSON protobuf. Hãy đối chiếu schema khi gặp lỗi parse hoặc lỗi kiểu dữ liệu.

Khi kết quả trả về là một gRPC status hợp lệ, request đã đi đủ xa để nhận phản hồi từ một gRPC peer. Lúc đó hãy tập trung vào status, metadata, descriptor và log xử lý thay vì tiếp tục thay đổi DNS hoặc port một cách ngẫu nhiên.

## 5. Thử metadata và xác thực

Nhiều dịch vụ cần token, tenant ID hoặc metadata định tuyến. Truyền metadata bằng `-H`; có thể lặp lại tùy chọn này cho nhiều header:

```bash
grpcurl -plaintext \
  -H 'authorization: Bearer <access-token>' \
  -H 'x-tenant-id: team-a' \
  -d '{"name":"An"}' \
  localhost:9090 \
  acme.greeter.v1.Greeter/SayHello
```

Thử cùng một request với và không có metadata giúp phân biệt lỗi xác thực với lỗi nghiệp vụ. `UNAUTHENTICATED` thường chỉ ra thông tin xác thực thiếu, sai hoặc hết hạn; `PERMISSION_DENIED` thường cho biết danh tính đã được nhận diện nhưng không có quyền thực hiện hành động.

Nếu reflection cũng bị bảo vệ, lệnh `list` hoặc `describe` có thể cần cùng metadata xác thực. Một phép thử reflection thất bại vì thiếu token không đồng nghĩa RPC nghiệp vụ không tồn tại.

Không ghi token thật vào tài liệu, log chia sẻ hoặc lịch sử lệnh dùng chung. Dùng credential thử nghiệm có thời hạn ngắn và thu hồi sau khi kiểm tra.

## 6. Kiểm tra deadline và thời gian phản hồi

Client gRPC nên đặt deadline để giới hạn thời gian chờ. grpcurl hỗ trợ `-max-time`; ví dụ sau giới hạn phép gọi ở mức năm giây:

```bash
grpcurl -plaintext \
  -max-time 5s \
  -d '{"name":"An"}' \
  localhost:9090 \
  acme.greeter.v1.Greeter/SayHello
```

Nếu request thất bại với `DEADLINE_EXCEEDED`, đối chiếu thời gian xử lý ở server, thời gian chờ dependency, hàng đợi executor, kết nối database và deadline mà gateway/client phía trước truyền xuống. Thử một deadline dài hơn có thể giúp xác định request chỉ cần thêm thời gian hay bị treo; đừng coi việc tăng deadline là cách sửa lỗi hiệu năng.

Deadline hết hạn ở client cũng không tự chứng minh server đã dừng công việc. Handler hoặc lời gọi blocking có thể tiếp tục chạy nếu không kiểm tra trạng thái hủy và không truyền deadline/cancellation xuống dependency. Đối chiếu log và trace để biết request còn tiêu tốn tài nguyên sau khi client ngắt chờ hay không.

## 7. Kiểm tra server streaming và client streaming

Với server-streaming RPC, gửi request một lần rồi quan sát từng message trả về:

```bash
grpcurl -plaintext \
  -d '{"topic":"news"}' \
  localhost:9090 \
  acme.feed.v1.Feed/Subscribe
```

Nếu stream không kết thúc, dùng `-max-time` để giới hạn thời gian quan sát trong phép thử. Phân biệt trường hợp server chưa phát message, server đang chờ sự kiện mới và server đã kết thúc bằng status lỗi.

Với client-streaming RPC, `-d @` cho phép đọc request từ standard input. Ví dụ trong shell kiểu Unix, truyền các message JSON theo từng dòng:

```bash
printf '%s\n' '{"id":"a"}' '{"id":"b"}' |
  grpcurl -plaintext \
    -d @ \
    localhost:9090 \
    acme.batch.v1.Batch/Upload
```

Với bidirectional streaming, kiểm tra cả hai chiều: server có nhận đủ message, có phát response trước khi client kết thúc input hay không, và status cuối stream là gì. Cách tương tác với stdin có thể khác theo phiên bản grpcurl và shell; kiểm tra `grpcurl -help` của phiên bản đang cài khi cần gửi chuỗi message tương tác.

Nếu unary thành công nhưng streaming thất bại, tập trung kiểm tra loại method trong `.proto`, cách client gửi/đóng input, logic điều khiển luồng, timeout, giới hạn message và proxy có giữ kết nối HTTP/2 đủ lâu hay không.

## 8. Dùng health check đúng cách

Nếu server đã đăng ký gRPC Health Checking Protocol, có thể gọi `Check`:

```bash
grpcurl -plaintext \
  -d '{"service":"acme.greeter.v1.Greeter"}' \
  localhost:9090 \
  grpc.health.v1.Health/Check
```

Health service là thành phần tùy chọn. `UNIMPLEMENTED` ở đây có thể chỉ có nghĩa ứng dụng chưa đăng ký health service; nó không chứng minh service nghiệp vụ bị lỗi. Nếu health service tồn tại, kiểm tra trạng thái `SERVING`/`NOT_SERVING` và cách ứng dụng cập nhật trạng thái khi dependency gặp sự cố.

## 9. Diễn giải gRPC status

Khi đã kết nối được đến gRPC server, status là manh mối quan trọng để phân loại lỗi. Bảng dưới đây là hướng điều tra ban đầu; ý nghĩa cuối cùng còn phụ thuộc cách ứng dụng ánh xạ exception sang gRPC status.

| Status | Hướng kiểm tra |
| --- | --- |
| `UNAVAILABLE` | Server tạm thời không sẵn sàng, kết nối bị đóng, proxy/upstream lỗi hoặc server đang khởi động/dừng. Kiểm tra endpoint và log transport. |
| `UNAUTHENTICATED` | Token hoặc thông tin xác thực thiếu, sai, hết hạn; kiểm tra metadata và interceptor xác thực. |
| `PERMISSION_DENIED` | Danh tính không có quyền; kiểm tra policy, role, tenant và interceptor phân quyền. |
| `INVALID_ARGUMENT` | Payload không hợp lệ hoặc không qua validation; đối chiếu schema protobuf và quy tắc nghiệp vụ. |
| `NOT_FOUND` | Tài nguyên hoặc đối tượng nghiệp vụ không tồn tại; kiểm tra dữ liệu và định danh trong request. |
| `FAILED_PRECONDITION` | Trạng thái hiện tại chưa đáp ứng điều kiện để thực hiện thao tác; kiểm tra vòng đời và trạng thái domain. |
| `UNIMPLEMENTED` | Method/service chưa được triển khai hoặc không được đăng ký, hoặc client đang dùng sai tên/descriptor. Reflection không được bật là một tình huống riêng. |
| `DEADLINE_EXCEEDED` | Deadline hết hạn trước khi hoàn tất; kiểm tra latency, dependency, hàng đợi và truyền deadline. |
| `RESOURCE_EXHAUSTED` | Hạn mức, quota, kích thước message, bộ nhớ hoặc năng lực xử lý đã chạm giới hạn. |
| `CANCELLED` | Client hoặc tầng trung gian đã hủy request; kiểm tra thao tác hủy, đóng stream và vòng đời client. |
| `INTERNAL` | Lỗi nội bộ hoặc exception chưa được ánh xạ rõ; dùng request ID/trace để tìm stack trace phía server. |

Status code có thể đi kèm message, details và trailing metadata. Dùng chế độ verbose nếu cần xem thêm thông tin:

```bash
grpcurl -v -plaintext localhost:9090 list
```

Không đưa nguyên văn message lỗi nội bộ ra client nếu nó chứa thông tin nhạy cảm. Với môi trường production, log phía server nên giữ đủ chi tiết để điều tra nhưng phải kiểm soát dữ liệu bí mật.

## 10. Khoanh vùng lỗi trong ứng dụng Spring

Khi grpcurl đã gọi được endpoint, hãy lần lượt đối chiếu các lớp trong ứng dụng:

1. **Server và đăng ký service:** kiểm tra log khởi động, cổng bind, implementation/service bean có được tạo và đăng ký hay không. Một class Java tồn tại trong source chưa đảm bảo service đã được gắn vào gRPC server đang chạy.
2. **Hợp đồng protobuf:** so sánh package, tên service, method và descriptor của grpcurl với artifact thực tế đã triển khai. Java package có thể khác `package` trong `.proto`.
3. **Interceptor và metadata:** xác nhận interceptor xác thực, phân quyền, tracing hoặc tenant nhận đúng metadata. Nếu gọi trực tiếp thành công nhưng qua gateway thất bại, so sánh header và authority ở hai đường đi.
4. **Xử lý nghiệp vụ và dependency:** dùng status, log có request ID và trace để xác định handler đã chạy đến đâu; kiểm tra database, HTTP client, message broker hoặc dịch vụ phụ thuộc.
5. **Deadline và tài nguyên:** đối chiếu thời gian ở từng span, executor/thread pool, giới hạn message và trạng thái cancellation. Với streaming, kiểm tra thời gian sống của kết nối và cách proxy xử lý HTTP/2.

Một phép so sánh hữu ích là gọi cùng một RPC bằng cùng descriptor và metadata tại ba điểm: localhost trong tiến trình/máy chủ, địa chỉ service nội bộ và endpoint qua ingress. Nếu chỉ một điểm thất bại, phạm vi điều tra thường nằm ở ranh giới mạng hoặc cấu hình của chặng đó. Nếu cả ba cùng trả một status nghiệp vụ, hãy tập trung vào handler, dữ liệu và dependency.

## 11. Quy trình điều tra ngắn gọn

Khi tiếp nhận một lỗi gRPC, có thể ghi lại kết quả theo thứ tự sau:

| Bước | Phép thử | Kết luận cần ghi nhận |
| --- | --- | --- |
| 1 | Kết nối đúng host/port bằng `-plaintext` hoặc TLS phù hợp | TCP/TLS/HTTP2 có thiết lập được không? |
| 2 | `list` hoặc nạp proto/protoset cục bộ | Reflection có hoạt động? Descriptor có đúng phiên bản? |
| 3 | `describe` service và method | Tên RPC, request/response có khớp hợp đồng không? |
| 4 | Gọi unary với payload tối thiểu | Server trả response hay gRPC status nào? |
| 5 | Thêm metadata và deadline | Lỗi có phụ thuộc xác thực, quyền hoặc thời gian chờ không? |
| 6 | Gọi streaming/health nếu có | Lỗi chỉ xuất hiện ở stream hoặc health service? |
| 7 | Đối chiếu log, trace, metric tại cùng thời điểm | Thành phần Spring/dependency nào tạo ra status hoặc độ trễ? |

Khi chia sẻ kết quả điều tra, ghi endpoint (đã ẩn thông tin nhạy cảm), thời điểm, phiên bản grpcurl, phiên bản proto, lệnh đã chạy, status/message, metadata không nhạy cảm và request ID/trace ID. Những dữ liệu này giúp người khác tái hiện phép thử và đối chiếu đúng log.

`grpcurl` giúp thu hẹp phạm vi lỗi bằng cách kiểm tra từng lớp của một lời gọi gRPC. Kết luận đáng tin cậy nhất đến từ việc giữ nguyên request và descriptor, thay đổi từng yếu tố một, rồi đối chiếu phản hồi của grpcurl với log và trace ở server Spring.
