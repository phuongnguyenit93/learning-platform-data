# Failover khi một server unavailable

Trong hệ thống Spring gRPC có nhiều backend, **failover** là khả năng tiếp tục phục vụ khi một server không còn sẵn sàng. Client cần biết danh sách endpoint, chọn backend đang phục vụ được và xử lý RPC thất bại theo deadline cùng retry policy. Khi một server trả status UNAVAILABLE hoặc mất kết nối, những RPC mới có thể được chuyển sang backend khác nếu resolver và load balancing policy cung cấp endpoint thay thế.

Failover có hai lớp liên quan nhưng khác nhau:

- **Load balancing** chọn một backend đủ điều kiện cho RPC mới.
- **Retry** thử lại một RPC thất bại theo policy, có thể trên backend khác nếu load balancer chọn endpoint khác.

Một RPC streaming đang chạy không thể tự động chuyển phần stream còn lại sang server khác. Nếu connection bị mất, ứng dụng phải mở stream mới và tiếp tục từ checkpoint/sequence đã xác nhận nếu giao thức nghiệp vụ hỗ trợ.

## 1. Điều kiện để failover hoạt động

Client-side failover cần các thành phần sau:

1. **Resolver** cung cấp nhiều địa chỉ backend, ví dụ DNS resolver hoặc resolver riêng.
2. **Load balancing policy** chọn backend, ví dụ pick_first hoặc round_robin.
3. **Channel sống lâu dài** để theo dõi trạng thái kết nối và tái sử dụng transport.
4. **Health signal** nếu muốn loại backend unhealthy trước khi gửi RPC.
5. **Deadline và retry policy** giới hạn thời gian chờ và số lần thử.

Nếu resolver chỉ trả về một địa chỉ, client không có backend thứ hai để failover. Nếu tất cả backend đều unavailable, call có thể trả UNAVAILABLE; bật wait-for-ready chỉ khiến call chờ backend phục hồi cho tới khi deadline hết.

## 2. Resolver và load balancing policy

Resolver chuyển target thành danh sách địa chỉ. Ví dụ target DNS:

~~~text
dns:///orders.internal:9090
~~~

DNS resolver có thể trả nhiều địa chỉ A/AAAA. Load balancing policy sử dụng danh sách đó để tạo và quản lý các subchannel.

| Policy | Cách chọn backend | Hành vi khi một backend lỗi |
| --- | --- | --- |
| pick_first | Thử các địa chỉ theo thứ tự và chọn một subchannel kết nối được | Có thể chuyển sang địa chỉ tiếp theo khi endpoint hiện tại không kết nối được |
| round_robin | Phân phối call mới qua các subchannel đang READY | Backend không READY bị bỏ qua; call mới dùng backend còn READY |

pick_first phù hợp khi muốn một kết nối hoạt động chính và có địa chỉ dự phòng. round_robin phù hợp khi muốn phân phối tải giữa nhiều backend. Cả hai cần resolver trả về danh sách endpoint chính xác; policy không tự phát hiện server mới nếu resolver không cập nhật địa chỉ.

## 3. Cấu hình service config cho client gRPC Java

Service config có thể chỉ định load balancing policy, health checking và retry policy theo service/method. Ví dụ cấu hình client-side round_robin và retry một unary RPC khi nhận UNAVAILABLE:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

Map<String, ?> serviceConfig = Map.of(
    "loadBalancingConfig",
    List.of(Map.of("round_robin", Map.of())),
    "methodConfig",
    List.of(Map.of(
        "name", List.of(Map.of(
            "service", "acme.orders.v1.OrderService",
            "method", "GetOrder")),
        "retryPolicy", Map.of(
            "maxAttempts", 3,
            "initialBackoff", "0.1s",
            "maxBackoff", "1s",
            "backoffMultiplier", 2,
            "retryableStatusCodes", List.of("UNAVAILABLE")))));

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.internal:9090")
    .defaultServiceConfig(serviceConfig)
    .build();

OrderServiceGrpc.OrderServiceBlockingStub stub =
    OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = stub
    .withDeadlineAfter(2, TimeUnit.SECONDS)
    .getOrder(request);
~~~

maxAttempts bao gồm lần gọi đầu tiên. Trong ví dụ, client có tối đa ba attempt, với backoff tăng dần và trần một giây. Deadline hai giây vẫn là giới hạn tổng của logical RPC; retry không được kéo dài call vượt deadline.

defaultServiceConfig là cấu hình mặc định của channel. Nếu resolver cung cấp service config riêng và runtime chấp nhận cấu hình đó, service config từ resolver có thể được ưu tiên. Cần xác minh resolver/DNS và phiên bản gRPC Java đang sử dụng có áp dụng policy mong muốn hay không. Không giả định chỉ viết một map trong Spring là mọi channel trong hệ thống đều dùng cấu hình đó.

## 4. Quản lý channel trong Spring

ManagedChannel là tài nguyên dài hạn, nên được tạo một lần và tái sử dụng qua các RPC. Ví dụ cấu hình bean:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forTarget("dns:///orders.internal:9090")
            .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel ordersChannel) {
        return OrderServiceGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

Đoạn bean trên minh họa lifecycle tối thiểu. Trong cấu hình production, áp dụng service config đã chọn ở phần trước và cấu hình TLS/trust material theo môi trường. Nếu starter đã cung cấp channel hoặc channel factory, dùng cơ chế đó thay vì tạo channel thứ hai tới cùng target.

Không tạo mới rồi đóng channel cho từng request. Channel dùng chung giúp resolver cập nhật endpoint, theo dõi subchannel state, tái sử dụng HTTP/2 connection và thực hiện load balancing.

## 5. Health checking để loại backend không phục vụ

Load balancer có thể chỉ dựa vào trạng thái kết nối, hoặc theo dõi gRPC Health Checking Protocol. Khi server triển khai grpc.health.v1.Health, client-side load balancing có thể bật healthCheckConfig:

~~~json
{
  "healthCheckConfig": {
    "serviceName": "acme.orders.v1.OrderService"
  },
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
~~~

Server cần đăng ký health service và cập nhật trạng thái:

- SERVING: backend có thể nhận RPC cho service được hỏi.
- NOT_SERVING: backend không nên được chọn cho service đó.

Khi một backend chuyển NOT_SERVING, health-aware load balancer có thể loại backend khỏi lựa chọn cho service tương ứng. Khi backend phục hồi và báo SERVING, nó có thể được đưa lại vào pool.

Health checking phải được hỗ trợ bởi client runtime/policy và server phải công bố đúng tên service đầy đủ. Nếu không bật health checking, client vẫn có thể phát hiện lỗi transport khi call được gửi, nhưng không nhất thiết loại backend trước request tiếp theo.

## 6. Điều gì xảy ra khi một backend trả UNAVAILABLE?

Giả sử resolver cung cấp ba backend A, B và C:

1. Channel tạo subchannel tới các địa chỉ được resolver công bố.
2. Load balancer chọn backend đang READY theo policy.
3. Backend A dừng hoặc connection bị đóng.
4. Subchannel A chuyển khỏi trạng thái READY; policy ngừng chọn A cho call mới.
5. round_robin tiếp tục chọn B hoặc C nếu chúng READY.
6. Nếu call đang chạy trên A thất bại với UNAVAILABLE, retry policy có thể tạo attempt mới trong deadline còn lại.

Không phải mọi lỗi đều kích hoạt retry. Retry chỉ áp dụng khi status thuộc retryableStatusCodes, policy còn attempt và deadline còn đủ. Một UNAVAILABLE do service handler chủ động trả cũng có thể được xem là retryable nếu cấu hình cho phép; chỉ bật retry khi semantics nghiệp vụ an toàn.

## 7. Phân biệt failover, retry và wait-for-ready

| Cơ chế | Mục đích | Giới hạn |
| --- | --- | --- |
| Failover qua load balancer | Chọn backend khác cho call mới | Cần endpoint thay thế và policy hỗ trợ |
| Retry policy | Thực hiện lại call thất bại | Có thể lặp side effect nếu operation không idempotent |
| Wait-for-ready | Chờ channel có backend sẵn sàng | Có thể chờ tới khi deadline hết; không tạo backend mới |

withWaitForReady() hữu ích khi gián đoạn ngắn và caller chấp nhận chờ. Với call không bật wait-for-ready, nếu không có transport sẵn sàng thì client thường nhận UNAVAILABLE nhanh hơn. Cả hai cách vẫn cần deadline hữu hạn để request không treo vô thời hạn.

Không dùng wait-for-ready để thay thế load balancing hoặc health checking. Nó không làm backend unhealthy trở nên healthy và cũng không đảm bảo có endpoint dự phòng.

## 8. Giới hạn của failover với RPC đang chạy

Load balancing thường chọn backend khi call bắt đầu. Nếu một unary RPC thất bại trước khi hoàn tất, retry có thể gửi attempt mới qua backend khác. Nhưng nếu một server-streaming, client-streaming hoặc bidirectional stream đã bắt đầu rồi connection bị mất:

- Stream cũ kết thúc; không thể chuyển các message đã trao đổi sang backend khác tự động.
- Client cần mở stream mới nếu nghiệp vụ cho phép.
- Giao thức ứng dụng nên có sequence number, cursor, offset hoặc checkpoint để tiếp tục từ vị trí đã xác nhận.
- Server cần hỗ trợ resume/idempotency nếu client có thể gửi lại message.

Với streaming upload, đừng chỉ reconnect rồi gửi lại toàn bộ bytes nếu thao tác không có cơ chế chống ghi trùng. Thiết kế chunk ID và acknowledgement để client biết chunk cuối cùng đã được server commit.

## 9. Idempotency khi retry unary RPC

Retry một RPC ghi có thể tạo side effect lặp nếu backend đầu tiên đã commit nhưng response bị mất. Ví dụ CreateOrder:

1. Client gửi request tới A.
2. A ghi order thành công.
3. A dừng trước khi response tới client.
4. Client thấy UNAVAILABLE và retry tới B.
5. Nếu B không nhận diện request trùng, hệ thống có thể tạo order thứ hai.

Đối với command có side effect, dùng idempotency key ổn định qua mọi attempt. Server lưu key cùng kết quả và trả lại kết quả trước đó khi nhận lại cùng operation. Không tạo key mới cho từng retry.

Các RPC đọc thuần túy thường dễ retry hơn. Với RPC ghi, cần tài liệu hóa semantics idempotency, transaction boundary và cách caller tra cứu kết quả khi response bị mất.

## 10. Deadline và backoff phải nằm trong ngân sách tổng

Retry policy có backoff tăng dần để tránh mọi client cùng dồn request vào backend vừa phục hồi. Ví dụ initialBackoff = 0.1s, maxBackoff = 1s, backoffMultiplier = 2 tạo khoảng chờ tăng dần, nhưng attempt chỉ được chạy nếu deadline tổng còn đủ.

Nguyên tắc:

- Đặt deadline cho logical RPC, không cấp lại toàn bộ timeout ở mỗi attempt.
- Giới hạn maxAttempts và tổng thời gian.
- Chỉ retry status đã được xác định là tạm thời.
- Dùng jitter nếu retry được triển khai ở tầng ứng dụng để tránh đồng bộ hóa tải.
- Không retry INVALID_ARGUMENT, UNAUTHENTICATED hoặc PERMISSION_DENIED như lỗi availability.
- Theo dõi retry amplification: số attempt tăng có thể làm backend còn sống quá tải hơn.

Nếu mọi backend đều unavailable, retry liên tục không tạo thêm capacity. Circuit breaker, retry throttling và backoff giúp hệ thống phục hồi có kiểm soát.

## 11. Kiểm thử failover với nhiều backend

Một test chỉ gọi trực tiếp một server không chứng minh failover. Integration test cần hai hoặc nhiều backend cùng implement service, một resolver trả về tất cả địa chỉ và một channel client dùng load balancing policy thực tế.

Ma trận kiểm thử:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| A và B đều READY | Call được phân phối theo policy |
| A dừng, B vẫn READY | Call mới tiếp tục thành công qua B |
| Call trên A nhận UNAVAILABLE | Retry chỉ xảy ra theo retry policy và deadline |
| A báo NOT_SERVING | Health-aware LB ngừng chọn A |
| A phục hồi và báo SERVING | A được đưa lại vào pool |
| A và B đều unavailable | Call trả UNAVAILABLE hoặc chờ tới deadline nếu wait-for-ready |
| RPC ghi mất response sau commit | Idempotency key ngăn tạo bản ghi trùng |
| Streaming RPC mất kết nối | Client resume theo checkpoint hoặc báo lỗi rõ ràng |

Để test ổn định, dùng cổng động cho từng server và resolver test trả chính xác các địa chỉ. Sau khi dừng A, chờ tín hiệu channel/subchannel hoặc health state cập nhật thay vì dựa vào Thread.sleep() cố định. Xác minh request thực sự tới B bằng backend identity trong response hoặc test counter.

## 12. Quan sát failover trong production

Theo dõi các chỉ số:

- Số subchannel ở READY, CONNECTING và TRANSIENT_FAILURE.
- Số backend được resolver công bố và số backend đủ điều kiện phục vụ.
- Tỷ lệ RPC UNAVAILABLE, DEADLINE_EXCEEDED và thành công.
- Số retry attempt trên mỗi logical RPC.
- Retry success rate và thời gian phục hồi sau backend outage.
- Phân phối request theo backend trước và sau failover.
- Số stream bị gián đoạn và số lần resume thành công.

Log cần có method, backend/peer nếu có, status code, attempt number, deadline remaining và request/operation ID. Không ghi token hoặc payload nhạy cảm. Khi thấy retry tăng nhưng success không tăng, kiểm tra resolver, health status, policy và khả năng backend còn lại đang bị quá tải.

## 13. Ghi nhớ và tự kiểm tra

**Failover khi một server unavailable** dựa trên resolver cung cấp nhiều endpoint và load balancing policy chọn backend còn READY. round_robin phân phối call mới giữa các backend khỏe; retry policy có thể thử lại unary RPC thất bại với UNAVAILABLE trong deadline tổng. Health checking giúp loại backend NOT_SERVING trước khi gửi call mới. Streaming RPC đang chạy không tự di chuyển; cần checkpoint/resume ở tầng ứng dụng.

Tự kiểm tra:

1. Vì sao resolver chỉ trả một địa chỉ thì client không thể failover sang backend khác?
2. pick_first và round_robin chọn backend khác nhau như thế nào?
3. Failover qua load balancer khác retry policy ở điểm nào?
4. Vì sao retry CreateOrder cần idempotency key?
5. wait-for-ready xử lý ra sao khi không còn backend READY?
6. Vì sao streaming RPC cần checkpoint/resume thay vì trông chờ channel tự chuyển server?

Thiết kế failover đúng giúp Spring gRPC tiếp tục phục vụ qua backend còn khỏe, giới hạn retry trong ngân sách latency và tránh tạo side effect trùng khi một server dừng giữa request.
