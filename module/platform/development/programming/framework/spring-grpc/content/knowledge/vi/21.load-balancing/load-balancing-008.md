# Retry kết hợp load balancing

## 1. Một RPC có thể có nhiều lần thử

Trong **SPRING_GRPC**, client dùng `ManagedChannel` và stub được sinh từ hợp đồng Protocol Buffers để gọi một service có thể chạy trên nhiều server instance. Load balancing chọn backend cho một RPC; retry tạo một attempt mới khi attempt trước thất bại theo điều kiện được cho phép. Hai cơ chế phối hợp để tăng khả năng phục hồi, nhưng mỗi cơ chế giải quyết một việc riêng.

Ví dụ client gọi `GetOrder`:

~~~text
Logical RPC: GetOrder(ORD-42)

Attempt 1 -> backend A
              A trả UNAVAILABLE trước khi RPC commit
                 |
                 v
              backoff
                 |
Attempt 2 -> backend B
              B trả response thành công
~~~

**Logical RPC** là lời gọi mà ứng dụng nhìn thấy. Mỗi **attempt** là một lần thực thi trên transport/server. Retry policy quyết định có tạo attempt mới hay không; load balancing policy chọn subchannel cho attempt đó.

Điểm cần nhớ:

- Load balancing không tự retry một RPC đã thất bại.
- Retry không bảo đảm attempt kế tiếp đến một backend khác.
- Một RPC đã commit không thể được gRPC tự động phát lại theo retry policy thông thường.
- Nếu retry có thể lặp side effect, ứng dụng phải bảo đảm idempotency.

## 2. Load balancing được áp dụng cho từng attempt

Một `ManagedChannel` quản lý resolver, subchannel và picker. Khi một attempt mới cần bắt đầu, picker chọn subchannel theo policy và trạng thái sẵn sàng:

~~~mermaid
flowchart TD
    A["Logical RPC"] --> B["Attempt 1"]
    B --> C["Load balancer picker"]
    C --> D["Backend A"]
    D --> E{"Attempt thất bại?"}
    E -- "Không" --> F["Trả kết quả cho ứng dụng"]
    E -- "Có, retryable và chưa commit" --> G["Backoff"]
    G --> H["Attempt 2"]
    H --> I["Picker được gọi lại"]
    I --> J["Backend được chọn"]
    J --> K{"Thành công?"}
    K -- "Có" --> F
    K -- "Không, còn retry" --> G
    K -- "Không còn retry/đã commit" --> L["Trả lỗi cho ứng dụng"]
~~~

Với `round_robin`, các attempt mới có thể được phân phối qua các subchannel `READY`. Với `pick_first`, các attempt thường tiếp tục dùng subchannel đang được chọn nếu nó vẫn sẵn sàng. Vì vậy, cùng một retry policy có thể có kết quả khác nhau tùy load balancing policy và trạng thái backend.

Không nên dựa vào retry để bảo đảm chuyển backend. Nếu backend A vẫn `READY` nhưng trả status `UNAVAILABLE` do dependency nội bộ, picker có thể tiếp tục chọn A. Khi cần loại A khỏi lựa chọn, phải có health checking, outlier detection hoặc cơ chế discovery phù hợp.

## 3. Khi nào gRPC được phép retry?

gRPC Java hỗ trợ retry theo service config. Một retry policy xác định:

- `maxAttempts`: số attempt tối đa, bao gồm attempt đầu tiên.
- `initialBackoff`: thời gian chờ ban đầu trước lần retry.
- `maxBackoff`: giới hạn thời gian chờ.
- `backoffMultiplier`: hệ số tăng backoff sau mỗi lần thất bại.
- `retryableStatusCodes`: các status code cho phép retry.

Retry chỉ có thể tiếp tục khi RPC chưa bị **committed** và attempt kết thúc bằng status được policy cho phép. RPC thường được xem là committed khi client nhận response headers từ server hoặc khi dữ liệu request vượt giới hạn retry buffer. Sau thời điểm đó, client không thể giả định một attempt mới là an toàn vì server có thể đã bắt đầu xử lý.

Điều này đặc biệt quan trọng với server streaming. Server thường gửi response headers khi bắt đầu stream; khi client nhận headers, RPC đã committed. Nếu stream sau đó đứt sau một số event, retry policy không tự mở stream mới để phát lại các event còn thiếu. Ứng dụng cần reconnect/resume bằng cursor hoặc sequence.

Ngoài retry policy, gRPC có thể thực hiện một số transparent retry trong tình huống transport thất bại rất sớm, trước khi server application xử lý lời gọi. Không nên dựa vào transparent retry để phục hồi một RPC đã được server xử lý hoặc đã phát response.

## 4. Chọn status code có thể retry

Retry chỉ nên áp dụng cho lỗi có khả năng tạm thời và thao tác có thể thực hiện lại an toàn. Một số định hướng:

| Status | Cách cân nhắc |
|---|---|
| `UNAVAILABLE` | Thường phù hợp cho lỗi backend/transport tạm thời; cần kiểm tra RPC chưa commit |
| `RESOURCE_EXHAUSTED` | Chỉ retry khi có chính sách phục hồi/quota rõ và có khoảng chờ phù hợp |
| `ABORTED` | Có thể thử lại toàn bộ transaction ở tầng ứng dụng nếu hợp đồng yêu cầu |
| `DEADLINE_EXCEEDED` | Chỉ thử lại nếu còn ngân sách thời gian và thao tác idempotent; server có thể đã hoàn thành |
| `CANCELLED` | Không retry khi caller chủ động hủy |
| `INVALID_ARGUMENT` | Sửa request; retry nguyên trạng không có ích |
| `PERMISSION_DENIED` | Sửa quyền hoặc policy; không retry liên tục |
| `UNAUTHENTICATED` | Làm mới credentials theo luồng xác thực rồi quyết định gọi lại |
| `NOT_FOUND` | Thường là kết quả nghiệp vụ, không phải lỗi backend tạm thời |

Không đưa mọi status vào `retryableStatusCodes`. Ví dụ server có thể trả `UNAVAILABLE` vì một dependency tạm thời lỗi, nhưng nếu server đã gửi response headers thì RPC đã commit và retry tự động không còn áp dụng. Ngược lại, một lỗi transport trước khi server nhận request có thể được xử lý bằng transparent retry.

## 5. Cấu hình retry policy trong service config

Ví dụ cấu hình retry cho method `GetOrder`:

~~~json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "orders.v1.OrdersService",
          "method": "GetOrder"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "2s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [
          "UNAVAILABLE"
        ]
      }
    }
  ]
}
~~~

Trong ví dụ này, tối đa bốn attempt được thực hiện: một attempt đầu và tối đa ba lần retry. Backoff tăng theo hệ số 2 và không vượt quá 2 giây. Runtime có thể áp dụng jitter cho thời gian backoff để nhiều client không retry đồng loạt.

Service config có thể được resolver cung cấp hoặc đặt làm cấu hình mặc định của channel. Ví dụ minh họa cách tạo cấu hình mặc định trong gRPC Java:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

java.util.Map<String, Object> retryPolicy = java.util.Map.of(
        "maxAttempts", 4.0,
        "initialBackoff", "0.2s",
        "maxBackoff", "2s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", java.util.List.of("UNAVAILABLE")
);

java.util.Map<String, Object> methodConfig = java.util.Map.of(
        "name", java.util.List.of(java.util.Map.of(
                "service", "orders.v1.OrdersService",
                "method", "GetOrder")),
        "retryPolicy", retryPolicy
);

java.util.Map<String, Object> serviceConfig = java.util.Map.of(
        "loadBalancingConfig", java.util.List.of(
                java.util.Map.of("round_robin", java.util.Map.of())),
        "methodConfig", java.util.List.of(methodConfig)
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultServiceConfig(serviceConfig)
        .useTransportSecurity()
        .build();
~~~

Ví dụ kết hợp `round_robin` với retry policy cho một method. Cấu hình thực tế còn phụ thuộc provider `round_robin`, phiên bản gRPC Java và service config mà resolver có thể cung cấp. Service config do resolver gửi có thể được ưu tiên hơn cấu hình mặc định của channel. Cần xác minh policy/provider được nạp trong runtime đang triển khai.

## 6. Backoff, deadline và giới hạn tổng thời gian

Retry không được phép kéo dài vô hạn. Một logical RPC nên có deadline tổng thể; thời gian backoff và các attempt đều tiêu thụ ngân sách này.

~~~java
GetOrderReply reply = ordersStub
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

Nếu deadline là 3 giây, client không có thêm 3 giây cho từng attempt. Ví dụ attempt đầu mất 1 giây, backoff mất 200 ms và attempt thứ hai cần 2 giây, logical RPC có thể hết deadline trước khi attempt thứ hai hoàn tất.

Backoff tăng dần giúp giảm áp lực khi backend đang phục hồi:

~~~text
Attempt 1 thất bại
  -> chờ khoảng 0.2 giây
Attempt 2 thất bại
  -> chờ khoảng 0.4 giây
Attempt 3 thất bại
  -> chờ khoảng 0.8 giây
...
  -> không vượt maxBackoff và deadline tổng thể
~~~

Jitter làm lệch thời điểm retry giữa các client. Nếu hàng nghìn client cùng nhận `UNAVAILABLE` rồi retry đúng một thời điểm, cụm backend có thể bị retry storm ngay khi bắt đầu phục hồi.

## 7. Retry và idempotency của thao tác nghiệp vụ

Transport error không chứng minh server chưa thực hiện side effect. Ví dụ:

~~~text
Client -> CreatePayment
Server -> ghi nhận thanh toán thành công
Network -> response bị mất
Client -> nhận UNAVAILABLE/DEADLINE_EXCEEDED
Client -> retry CreatePayment
~~~

Nếu lần retry tạo một khoản thanh toán mới, khách hàng có thể bị tính tiền hai lần. Với thao tác tạo/cập nhật dữ liệu, gửi lệnh hoặc phát sinh giao dịch, cần thiết kế idempotency:

1. Client tạo một idempotency key ổn định cho logical operation.
2. Mọi attempt của cùng operation dùng lại key đó.
3. Server lưu key cùng kết quả xử lý trong transaction hoặc kho idempotency.
4. Nếu nhận lại key đã xử lý, server trả kết quả cũ thay vì thực hiện side effect lần nữa.

Ví dụ request:

~~~proto
message CreatePaymentRequest {
  string idempotency_key = 1;
  string order_id = 2;
  int64 amount_minor = 3;
}
~~~

`idempotency_key` phải được giữ nguyên qua các attempt. Nếu client tạo key mới cho mỗi lần retry, server không thể nhận diện đó là cùng một operation.

Với thao tác đọc như `GetOrder`, retry thường dễ an toàn hơn. Tuy vậy, nếu kết quả đọc phụ thuộc snapshot hoặc backend khác nhau có dữ liệu chưa đồng bộ, cần xác định consistency yêu cầu trước khi cho phép retry qua instance khác.

## 8. Retry có thể gửi lại đến cùng backend

Giả sử resolver trả A, B và C:

| Tình trạng | Policy | Hệ quả có thể xảy ra |
|---|---|---|
| A, B, C đều `READY` | `round_robin` | Các attempt mới có thể được phân phối qua nhiều subchannel |
| A, B, C đều `READY` | `pick_first` | Các attempt có thể tiếp tục đến A |
| Chỉ B `READY` | `round_robin` | Attempt mới chỉ có thể chọn B |
| A vẫn `READY` nhưng trả `UNAVAILABLE` ở tầng ứng dụng | `pick_first` | A vẫn có thể được chọn lại |
| A mất kết nối | B hoặc C sẵn sàng | Picker có thể chọn backend còn hoạt động cho attempt mới |

Vì vậy, retry và failover là hai hành vi khác nhau. Retry policy quyết định **có thử lại không**; load balancer quyết định **attempt mới đi đâu** dựa trên trạng thái hiện tại. Muốn loại backend có lỗi lặp lại, cần health checking, outlier ejection hoặc cập nhật resolver, không chỉ tăng `maxAttempts`.

## 9. Retry cho server streaming và giới hạn commitment

Server streaming có thể phát nhiều response trong một RPC. Khi server đã gửi response headers, client nhận headers và RPC được commit, retry policy không thể tự khởi động lại stream để tiếp tục từ response cuối.

~~~text
Attempt 1:
  Client -> WatchEvents
  Server -> headers
  Server -> Event #1
  Server -> Event #2
  Server -> UNAVAILABLE

RPC đã commit sau headers:
  gRPC không tự retry để tiếp tục từ #3

Application resume:
  Client -> WatchEvents(after_sequence = 2)
  Server/backend mới -> Event #3, #4, ...
~~~

Nếu cần stream có khả năng phục hồi, hợp đồng ứng dụng cần cursor/sequence ổn định. Client chỉ checkpoint sau khi event được xử lý bền vững; khi stream lỗi, tạo RPC mới và gửi cursor. Backend mới phải đọc lại dữ liệu từ nguồn dùng chung. Đây là resume ở tầng ứng dụng, không phải retry tự động của gRPC.

## 10. Tránh retry storm và khuếch đại tải

Retry làm tăng số request thực tế so với số logical RPC mà ứng dụng khởi tạo. Khi backend quá tải, retry không kiểm soát có thể làm tình trạng xấu hơn:

~~~text
Backend quá tải
   -> trả lỗi cho nhiều RPC
   -> client retry đồng loạt
   -> số attempt tăng
   -> backend càng quá tải
~~~

Các biện pháp kiểm soát:

- Đặt `maxAttempts` thấp và chỉ retry status thật sự có khả năng tạm thời.
- Dùng exponential backoff và jitter.
- Giới hạn deadline tổng thể của logical RPC.
- Dùng retry throttling nếu runtime/service config hỗ trợ.
- Đặt quota/admission control và giới hạn concurrency ở server.
- Không chồng retry policy của gRPC với vòng lặp retry không giới hạn trong ứng dụng.
- Không retry lỗi validation, authorization hoặc lỗi nghiệp vụ không thể tự phục hồi.

Một số gRPC runtime hỗ trợ `retryThrottling` trong service config để giảm retry khi tỷ lệ thất bại tăng. Khả năng và cách hoạt động phụ thuộc phiên bản; cần kiểm tra runtime thay vì giả định cấu hình đó luôn được áp dụng.

## 11. Quan sát logical RPC và từng attempt

Nếu chỉ đếm số lần method được gọi ở tầng ứng dụng, có thể không thấy số attempt nội bộ do gRPC retry tạo ra. Nên quan sát cả logical call và attempt:

- Số logical RPC theo method.
- Số attempt trung bình và phân bố số attempt trên mỗi logical RPC.
- Status của từng attempt và status cuối cùng trả về caller.
- Backend/instance nhận từng attempt.
- Tổng thời gian logical RPC, thời gian từng attempt và thời gian backoff.
- Tỷ lệ RPC thành công sau retry.
- Số lần retry bị chặn do RPC đã commit hoặc hết deadline.
- Tỷ lệ duplicate/idempotency hit ở server.

Không ghi payload, access token hoặc idempotency key nhạy cảm vào log. Có thể dùng trace/span liên kết các attempt với một logical operation ID và gắn instance ID không nhạy cảm để phân tích phân phối.

Nếu retry nhiều lần nhưng tất cả attempt đến cùng một backend, kiểm tra policy (`pick_first` hay `round_robin`), số subchannel `READY` và health status. Nếu retry không xảy ra, kiểm tra status code, commitment, service config có đến channel không và provider/runtime có hỗ trợ retry không.

## 12. Kiểm thử retry kết hợp load balancing

Một test chỉ xác minh RPC cuối cùng thành công là chưa đủ. Cần điều khiển status từng attempt và ghi nhận backend nhận request:

| Kịch bản | Điều cần xác minh |
|---|---|
| A trả `UNAVAILABLE` trước khi commit, B thành công | Có attempt mới trong giới hạn policy; kết quả cuối thành công |
| A trả `INVALID_ARGUMENT` | Không retry theo policy chỉ cho `UNAVAILABLE` |
| A trả `UNAVAILABLE` sau khi response headers đã được gửi | RPC đã commit; không kỳ vọng retry tự động |
| A và B đều `READY`, policy `round_robin` | Các attempt mới có thể được chọn qua picker và backend khác |
| `pick_first` giữ A `READY` nhưng A trả lỗi ứng dụng | Không giả định retry sẽ chuyển sang B |
| Attempt đầu tiêu thụ gần hết deadline | Logical RPC kết thúc theo deadline tổng thể |
| Nhiều client cùng gặp lỗi | Backoff/jitter và throttling hạn chế retry storm |
| Side effect được gửi lại | Idempotency key ngăn xử lý trùng |
| Server stream lỗi sau event đầu tiên | Không tự resume; client tạo RPC mới với cursor |
| Resolver gỡ backend lỗi | Attempt mới không chọn endpoint đã bị loại sau khi cập nhật áp dụng |

Nên dùng nhiều test server có instance ID, custom resolver hoặc môi trường test tương đương để quan sát backend. In-process test hữu ích cho retry/status logic; TCP/TLS và DNS cần integration test riêng nếu hành vi phụ thuộc transport hoặc resolver thực tế.

## 13. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ retry luôn chuyển sang backend khác | Nhiều attempt vẫn có thể đến cùng instance | Chọn policy phù hợp và kiểm tra subchannel readiness |
| Retry mọi status | Lặp lỗi request, quyền hoặc nghiệp vụ | Chỉ khai báo status có khả năng phục hồi |
| Đặt `maxAttempts` quá cao | Khuếch đại tải và kéo dài latency | Giới hạn attempt, backoff và deadline |
| Không đặt deadline | Logical RPC có thể chờ quá lâu | Đặt deadline theo ngân sách nghiệp vụ |
| Retry thao tác tạo side effect không idempotent | Tạo giao dịch hoặc dữ liệu trùng | Dùng idempotency key và deduplication |
| Cho rằng server stream tự tiếp tục sau lỗi | Mất phần dữ liệu sau điểm ngắt | Thiết kế cursor/checkpoint và application resume |
| Chỉ expose health service | Backend lỗi vẫn có thể được picker chọn | Cấu hình client health checking/discovery |
| Chồng retry ở gRPC và application loop | Số attempt tăng ngoài dự tính | Chọn một tầng điều phối chính và đặt giới hạn rõ |

**Ghi nhớ:** Retry policy quyết định có tạo attempt mới; load balancing policy chọn backend cho attempt đó. Retry chỉ hoạt động khi status phù hợp và logical RPC chưa commit; deadline bao trùm toàn bộ attempt cùng thời gian backoff. `round_robin` có thể phân phối attempt qua nhiều backend, còn `pick_first` có thể tiếp tục chọn cùng backend. Với side effect cần idempotency key; với server stream đã commit cần reconnect/resume bằng cursor ở tầng ứng dụng.
