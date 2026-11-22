# Load balancing và name resolution

## Mục tiêu học tập

Sau bài này, bạn có thể:
- Giải thích name resolution và client-side load balancing trong gRPC.
- Phân biệt NameResolver, LoadBalancer, Subchannel và connection.
- Cấu hình DNS target và policy round_robin trong Spring.

## 1. Vì sao gRPC cần name resolution và load balancing?

Ứng dụng Spring thường gọi một target logic như **orders.internal:8443** thay vì gắn cứng IP của một máy chủ. Trong môi trường triển khai, một service có thể có nhiều instance, địa chỉ thay đổi khi scale/restart và một instance có thể tạm thời không sẵn sàng.

Hai cơ chế phối hợp giải quyết vấn đề:

- **Name resolution** tìm các địa chỉ backend hiện có từ target logic, ví dụ DNS hoặc một hệ thống discovery.
- **Load balancing** chọn backend phù hợp cho từng RPC dựa trên danh sách địa chỉ và trạng thái kết nối.

Trong grpc-java, hai cơ chế này được quản lý bên trong **ManagedChannel**. Ứng dụng tạo Channel và stub; mỗi RPC được đưa qua picker của LoadBalancer để chọn một Subchannel/transport có thể phục vụ.

~~~mermaid
flowchart LR
    A["Spring service"] --> B["Generated stub"]
    B --> C["ManagedChannel"]
    C --> D["NameResolver"]
    D --> E["Danh sách backend"]
    E --> F["LoadBalancer"]
    F --> G["Picker chọn Subchannel"]
    G --> H["HTTP/2 connection"]
    H --> I["gRPC server instance"]
~~~

Ví dụ target logic **dns:///orders.internal:8443** có thể được phân giải thành ba địa chỉ:

~~~text
orders.internal:8443
  - 10.20.1.11:8443
  - 10.20.1.12:8443
  - 10.20.1.13:8443
~~~

Danh sách trên là kết quả discovery, chưa phải cam kết rằng cả ba backend đều khỏe. LoadBalancer và transport tiếp tục theo dõi trạng thái để chọn một đường đi phù hợp.

## 2. NameResolver: từ target đến địa chỉ

### 2.1. Target có scheme và authority

Một gRPC Channel được tạo từ target. Target có thể bao gồm **scheme** để chọn NameResolver:

| Target ví dụ | Resolver thường dùng | Ý nghĩa |
| --- | --- | --- |
| **dns:///orders.internal:8443** | DNS resolver | Tra cứu địa chỉ host qua DNS |
| **static/custom target** | Resolver do ứng dụng/framework cung cấp | Dùng danh sách endpoint hoặc service discovery riêng |
| **xds:///orders** | xDS resolver nếu đã tích hợp | Nhận cấu hình endpoint/policy từ control plane |

Cú pháp URI và các scheme được hỗ trợ tùy resolver provider đã được nạp trong runtime. Với grpc-java thông thường, DNS resolver được tích hợp sẵn. Không nên giả định một scheme tùy chỉnh sẽ tự hoạt động chỉ vì nó xuất hiện trong target.

**Authority** là danh tính/đích logic của service. Nó có thể được dùng trong việc xác định resolver và xác minh TLS; không đồng nghĩa với IP của backend được chọn.

### 2.2. Resolver trả về gì?

NameResolver không trực tiếp gọi service. Nó thông báo cho Channel về các địa chỉ đã phân giải và có thể kèm service config:

~~~text
Target: dns:///orders.internal:8443

NameResolver:
  address group A: 10.20.1.11:8443
  address group B: 10.20.1.12:8443
  address group C: 10.20.1.13:8443
  optional service config: round_robin
~~~

Trong grpc-java, kết quả resolution được biểu diễn qua các đối tượng như **EquivalentAddressGroup** và **ResolvedAddresses**. Resolver có thể phát kết quả mới khi địa chỉ thay đổi, thay vì chỉ phân giải một lần lúc tạo Channel.

Một **address group** có thể chứa một hoặc nhiều socket address tương đương. LoadBalancer nhận các group này để tạo hoặc cập nhật Subchannel. Không nên đánh đồng số IP DNS với số RPC hay số connection.

### 2.3. DNS không phải load balancing hoàn chỉnh

DNS có thể trả nhiều địa chỉ, nhưng việc có nhiều IP không tự bảo đảm mỗi RPC được phân phối đều:

- Resolver có thể trả nhiều địa chỉ cho Channel.
- Chính sách LoadBalancer quyết định chọn địa chỉ nào cho một RPC.
- Transport có thể giữ connection lâu dài tới backend đã chọn.
- DNS cache/TTL và chu kỳ refresh ảnh hưởng thời điểm Channel nhìn thấy thay đổi.

Vì vậy, **DNS round-robin** ở tầng phân giải tên và **round_robin policy** ở tầng gRPC client là hai cơ chế khác nhau. DNS cung cấp địa chỉ; policy quyết định cách sử dụng các địa chỉ đó.


## 3. Các thành phần trong client-side load balancing

| Thành phần | Trách nhiệm |
| --- | --- |
| **NameResolver** | Phân giải target và thông báo địa chỉ/service config |
| **LoadBalancer** | Tạo/cập nhật Subchannel và quyết định chiến lược chọn backend |
| **Subchannel** | Đại diện một đường kết nối logic đến một address group |
| **Connection/transport** | Kết nối mạng thực tế, thường là TCP/TLS và HTTP/2 |
| **Picker** | Chọn Subchannel cho một RPC mới dựa trên trạng thái hiện tại |
| **ManagedChannel** | Điều phối resolver, policy, subchannel và vòng đời RPC |

Luồng xử lý khi một RPC mới bắt đầu:

1. Caller gọi phương thức trên generated stub.
2. Stub tạo RPC qua ManagedChannel.
3. Channel dùng picker hiện tại của LoadBalancer.
4. Picker chọn một Subchannel đang sẵn sàng hoặc yêu cầu chờ/lỗi theo policy.
5. RPC đi qua connection của Subchannel tới backend.
6. Khi resolver hoặc trạng thái Subchannel thay đổi, LoadBalancer cập nhật picker cho những RPC tiếp theo.

**Picker không chọn lại backend cho từng message trong một streaming RPC.** Một RPC streaming gắn với một transport/HTTP/2 stream trong suốt vòng đời của nó. Load balancing chủ yếu quyết định backend khi RPC bắt đầu.

## 4. Hai policy cơ bản: pick_first và round_robin

### 4.1. pick_first

**pick_first** thử các địa chỉ theo thứ tự và chọn một đường kết nối sẵn sàng. Khi đường đó hoạt động, các RPC tiếp theo thường tiếp tục dùng backend đang được chọn.

Ưu điểm:

- Mô hình đơn giản, thường duy trì ít connection hơn.
- Phù hợp khi chỉ có một endpoint ổn định hoặc proxy/LB phía trước đã phân phối tải.
- Có thể thử địa chỉ kế tiếp nếu địa chỉ đang chọn không kết nối được, tùy trạng thái và implementation.

Giới hạn:

- Khi nhiều backend đều khỏe, tải có thể dồn vào một backend.
- Một Channel không nhất thiết luân phiên RPC giữa các địa chỉ.
- Nếu backend được chọn vẫn khỏe nhưng quá tải, policy này không tự phân phối sang instance khác.

### 4.2. round_robin

**round_robin** duy trì các Subchannel cho các address group và chọn lần lượt trong số các Subchannel sẵn sàng. Ví dụ khi cả ba backend đều READY:

~~~text
RPC 1 -> backend A
RPC 2 -> backend B
RPC 3 -> backend C
RPC 4 -> backend A
RPC 5 -> backend B
~~~

Khi một backend không sẵn sàng, picker bỏ qua nó và phân phối trên các backend còn lại theo trạng thái hiện có.

Ưu điểm:

- Phân phối các RPC mới trên nhiều backend.
- Hữu ích khi client kết nối trực tiếp tới nhiều instance.
- Không cần mở Channel mới cho từng backend hoặc từng request.

Giới hạn:

- Không bảo đảm tải CPU, thời lượng RPC hay số message streaming bằng nhau.
- RPC dài vẫn chiếm backend đã được chọn cho tới khi kết thúc.
- Cần resolver trả đủ endpoint và các Subchannel thực sự sẵn sàng.
- Không thay thế health check, giới hạn concurrency hoặc admission control ở server.

### 4.3. So sánh nhanh

| Tiêu chí | pick_first | round_robin |
| --- | --- | --- |
| Backend thường dùng | Một Subchannel sẵn sàng được chọn | Luân phiên các Subchannel READY |
| Phân phối RPC mới | Không nhằm chia đều nhiều instance | Có, theo vòng trên các instance sẵn sàng |
| Connection | Thường ít hơn | Có thể duy trì nhiều connection |
| Hợp với | Một endpoint/proxy đã cân bằng tải | Client biết nhiều backend trực tiếp |
| Điều kiện quan trọng | Địa chỉ được phân giải và có thể kết nối | Resolver trả nhiều address group; policy được hỗ trợ |

Không có policy nào luôn tốt hơn. Nếu client chỉ nhìn thấy **một địa chỉ VIP** của proxy, round_robin ở client không thể tự biết các backend ẩn phía sau VIP.

## 5. Cấu hình round_robin trong Spring với grpc-java

Ví dụ dùng DNS resolver và service config để chọn **round_robin**. Channel là bean dùng chung cho các RPC:

~~~java
package dev.example.orders.client;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        Map<String, ?> serviceConfig = Map.of(
                "loadBalancingConfig",
                List.of(Map.of("round_robin", Map.of())));

        return ManagedChannelBuilder
                .forTarget("dns:///orders.internal:8443")
                .defaultServiceConfig(serviceConfig)
                .build();
    }
}
~~~

Các điểm cần lưu ý:

- **forTarget(...)** giữ target logic; DNS resolver phân giải hostname thành địa chỉ.
- **defaultServiceConfig(...)** cung cấp service config mặc định, trong đó **loadBalancingConfig** chọn policy **round_robin**. API và khả năng cấu hình phụ thuộc phiên bản grpc-java; cần dùng dependency tương thích.
- Resolver phải trả nhiều address group thì round_robin mới có nhiều backend để chọn.
- Channel cần được tái sử dụng và đóng khi Spring context dừng.
- Ví dụ chưa cấu hình TLS credentials; môi trường production phải dùng cấu hình bảo mật phù hợp, không dùng plaintext cho endpoint ngoài phạm vi tin cậy.

Nếu không chỉ định policy và resolver cũng không cung cấp service config, grpc-java thường dùng policy mặc định **pick_first**. Xác minh hành vi theo phiên bản và provider được nạp trong ứng dụng.


### 5.1. Service config và phạm vi áp dụng

Service config có thể mô tả load-balancing policy và hành vi theo service/method. Ví dụ cấu hình policy tối thiểu:

~~~json
{
  "loadBalancingConfig": [
    { "round_robin": {} }
  ]
}
~~~

Nếu NameResolver cung cấp service config riêng, cách ưu tiên giữa cấu hình resolver và default service config phụ thuộc API/thiết lập Channel. Hãy xác định nguồn cấu hình được tin cậy, tránh để một nguồn discovery không đáng tin tự ý thay đổi policy hoặc hành vi RPC.

Không cần thêm logic chọn IP thủ công trong business service. Việc đó làm caller phụ thuộc topology và bỏ qua trạng thái Subchannel mà gRPC runtime đang theo dõi.

## 6. Client-side LB và proxy/load balancer phía hạ tầng

Có hai vị trí phổ biến để phân phối lưu lượng:

- **Client-side load balancing:** resolver cung cấp danh sách endpoint cho mỗi client; LoadBalancer của gRPC client chọn backend cho từng RPC mới.
- **Proxy/server-side load balancing:** client kết nối đến một địa chỉ proxy/VIP; proxy hoặc hạ tầng service mesh phân phối các RPC tới backend.

~~~mermaid
flowchart TB
    subgraph ClientSide["Client-side load balancing"]
      C1["Spring client"] --> CH["ManagedChannel"]
      CH --> R["Resolver: A, B, C"]
      R --> LB["round_robin picker"]
      LB --> A["Backend A"]
      LB --> B["Backend B"]
      LB --> C["Backend C"]
    end
    subgraph ProxySide["Proxy / server-side load balancing"]
      C2["Spring client"] --> VIP["Proxy / VIP"]
      VIP --> D["Backend A"]
      VIP --> E["Backend B"]
      VIP --> F["Backend C"]
    end
~~~

| Tiêu chí | Client-side | Proxy/server-side |
| --- | --- | --- |
| Client biết backend | Có, resolver cung cấp endpoint | Thường chỉ biết proxy/VIP |
| Thành phần quyết định | gRPC LoadBalancer trong client | Proxy, gateway hoặc service mesh |
| Quan sát trạng thái backend | Theo Subchannel mà client quản lý | Theo health/endpoint state của proxy |
| Vận hành | Cần resolver/config nhất quán trên client | Cần vận hành proxy và cấu hình route |
| Trường hợp hợp lý | Client truy cập trực tiếp nhiều endpoint | Muốn tập trung policy, auth hoặc routing tại hạ tầng |

gRPC thường giữ HTTP/2 connection lâu dài. Một **L4 load balancer** chỉ phân phối kết nối TCP có thể gắn một Channel lâu dài với một backend, nên không nhất thiết chia đều từng RPC bên trong connection. Nếu cần phân phối theo RPC, dùng client-side LB hoặc proxy hiểu gRPC/HTTP2 ở tầng phù hợp.

Hai mô hình có thể cùng tồn tại, nhưng cần tránh cân bằng tải hai lần thiếu chủ đích. Ví dụ client round_robin trên nhiều proxy endpoint, rồi mỗi proxy lại chọn backend, có thể làm khó quan sát và dự đoán đường đi.

## 7. Resolver cập nhật địa chỉ và trạng thái kết nối

Name resolution không phải thao tác một lần rồi kết thúc. Khi DNS record hoặc service registry thay đổi, resolver có thể phát danh sách địa chỉ mới. LoadBalancer so sánh danh sách đó với Subchannel hiện có để thêm, cập nhật hoặc loại bỏ đường kết nối.

Các trạng thái kết nối thường gặp trong grpc-java:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **IDLE** | Chưa có hoạt động cần kết nối hoặc đang nghỉ |
| **CONNECTING** | Đang thiết lập transport |
| **READY** | Subchannel có connection sẵn sàng |
| **TRANSIENT_FAILURE** | Kết nối tạm thời thất bại; có thể thử lại theo backoff |
| **SHUTDOWN** | Channel/Subchannel đang hoặc đã đóng |

Khi một backend biến mất khỏi kết quả resolver, LoadBalancer có thể ngừng chọn Subchannel tương ứng và dọn tài nguyên sau khi các RPC liên quan kết thúc hoặc bị đóng theo policy. RPC streaming đang chạy không tự chuyển sang backend khác giữa chừng; nếu connection bị mất, stream đó thường kết thúc lỗi và ứng dụng phải quyết định có mở RPC mới hay không.

### 7.1. DNS TTL, cache và thời gian hội tụ

Đổi DNS record không có nghĩa mọi client nhìn thấy địa chỉ mới ngay lập tức. Thời gian hội tụ phụ thuộc:

- TTL và cache của DNS resolver/hệ điều hành/runtime.
- Tần suất resolver refresh và cách resolver phát kết quả mới.
- DNS negative caching khi hostname chưa tồn tại.
- Backoff khi truy vấn DNS hoặc kết nối backend thất bại.
- Cache/route của proxy hoặc service mesh ở các tầng khác.

Không đặt TTL quá ngắn với kỳ vọng nó lập tức làm mọi client đổi backend; refresh quá thường xuyên cũng tăng tải DNS. Với môi trường cần discovery nhanh và health state chi tiết, resolver/service discovery chuyên dụng có thể phù hợp hơn DNS thuần.

### 7.2. Khi backend lỗi

Nếu Subchannel đang READY mất connection, gRPC có thể chuyển nó sang trạng thái lỗi tạm thời, thử reconnect theo backoff và cập nhật picker. Với round_robin, những Subchannel READY còn lại vẫn có thể nhận RPC mới.

Tuy nhiên, reconnect không đồng nghĩa retry tự động mọi RPC đã gửi. Một unary RPC có thể đã được server xử lý trước khi connection mất; một streaming RPC có thể đã trao đổi nhiều message. Việc gọi lại cần dựa trên tính idempotent, trạng thái nghiệp vụ và policy retry.

## 8. Health checking và readiness

**Connection READY** chỉ cho biết transport có thể gửi RPC; nó không bảo đảm ứng dụng backend đang phục vụ đúng nghiệp vụ. Một server có thể mở cổng nhưng database phụ thuộc đang hỏng.

gRPC có **Health Checking Protocol** với service chuẩn như **grpc.health.v1.Health**. Client hoặc load-balancing policy có thể dùng health state để quyết định endpoint nào được chọn nếu client, server và resolver/policy hỗ trợ cơ chế đó.

Cần phân biệt:

- **Transport readiness:** có connection/HTTP2 transport.
- **Application health:** server báo trạng thái SERVING cho service cụ thể.
- **Readiness của hạ tầng:** orchestration/proxy cho phép endpoint nhận traffic.
- **Liveness:** tiến trình còn sống và có thể cần restart nếu bị treo.

Không tự coi READY của Subchannel là kết quả health check. Khi dùng health checking, cần bật service health tương ứng và kiểm tra cấu hình policy; chỉ thêm dependency hoặc khai báo service không tự khiến client lọc backend không khỏe.

## 9. Tích hợp với Spring: vòng đời Channel và cấu hình

Trong ứng dụng Spring, **ManagedChannel** nên được quản lý như một bean dùng chung. Stub được tạo từ Channel và inject vào service nghiệp vụ. Không tạo Channel cho từng HTTP request hoặc từng RPC vì sẽ tăng số connection, TLS handshake và chi phí discovery.

Ví dụ wiring stub:

~~~java
@Bean
OrderServiceGrpc.OrderServiceBlockingStub orderStub(
        ManagedChannel orderChannel) {
    return OrderServiceGrpc.newBlockingStub(orderChannel);
}
~~~

Bean Channel ở mục 5 có **destroyMethod = "shutdown"** để yêu cầu đóng khi Spring context dừng. Trong production, có thể cần chờ RPC đang chạy hoàn tất trong thời gian giới hạn trước khi buộc đóng.

Nếu sử dụng Spring gRPC starter, hãy cấu hình target, name resolver, load-balancing policy và TLS theo đúng API của phiên bản starter. Ví dụ grpc-java ở trên mô tả cơ chế Channel nền tảng; không giả định mọi starter dùng cùng tên property hoặc tự động đăng ký resolver tùy chỉnh.

### 9.1. Khi nào cần custom NameResolver?

DNS phù hợp khi hostname/record đủ để mô tả endpoint. Có thể cần custom resolver khi địa chỉ đến từ:

- Service registry nội bộ.
- Control plane hoặc hệ thống discovery có metadata riêng.
- Danh sách endpoint động trong môi trường test.
- Nguồn cấu hình cần gắn attributes cho LoadBalancer.

Custom resolver cần phát kết quả địa chỉ theo API grpc-java, thông báo lỗi resolution, refresh khi dữ liệu thay đổi và giải phóng tài nguyên khi shutdown. Nó **không nên** tự chọn backend cho từng RPC; đó là trách nhiệm của LoadBalancer.

Nếu cần custom policy, triển khai **LoadBalancerProvider** và đăng ký provider phù hợp với cơ chế service loader/runtime. Không nên tự viết resolver/policy nếu DNS hoặc policy tích hợp đã đáp ứng yêu cầu.

## 10. Bảo mật khi phân giải và chọn backend

Name resolution ảnh hưởng trực tiếp tới nơi client gửi dữ liệu. Một resolver bị cấu hình sai hoặc nguồn discovery không đáng tin có thể đưa client tới endpoint không mong muốn.

- Dùng nguồn DNS/service registry thuộc vùng tin cậy, kiểm soát quyền cập nhật record.
- Cấu hình TLS để xác minh danh tính server; đừng tắt xác minh hostname chỉ vì backend có IP động.
- Khi kết nối đến IP được resolver trả về, cần giữ đúng **authority/hostname** cho xác minh certificate và routing theo kiến trúc.
- Không coi địa chỉ IP được phân giải là bằng chứng backend được phép truy cập.
- Nếu resolver nhận service config từ control plane, xác thực nguồn và giới hạn các policy được chấp nhận.
- Tránh ghi token hoặc dữ liệu nhạy cảm vào log resolution/endpoint attributes.

Trong môi trường có mTLS, certificate identity và authorization vẫn phải được kiểm tra ở server/gateway. LoadBalancer chỉ quyết định đường đi, không thay thế xác thực và phân quyền.


## 11. Chẩn đoán các vấn đề load balancing

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Nhiều RPC đều vào một backend | Policy pick_first; resolver chỉ trả một address group; hoặc client chỉ thấy VIP | Kiểm tra target, kết quả resolver và service config |
| round_robin không chia tải | Chỉ một Subchannel READY; policy không được nạp; resolver không trả nhiều endpoint | Kiểm tra service config, provider và trạng thái từng Subchannel |
| DNS đổi nhưng client vẫn gọi IP cũ | DNS cache/TTL hoặc resolver chưa refresh | Quan sát kết quả resolution và chu kỳ refresh |
| Backend lỗi vẫn nhận traffic | Chưa có health checking/readiness hoặc trạng thái connection chưa cập nhật | Phân biệt transport READY với application health |
| Mất một backend làm nhiều RPC lỗi | Các RPC đang gắn với connection đó; retry chưa phù hợp | Quan sát status, reconnect và tính idempotent |
| Thay backend làm stream đang chạy bị ngắt | Streaming RPC không migrate giữa backend | Thiết kế resume/cursor và reconnect ở tầng ứng dụng |
| Kết nối TLS lỗi sau khi DNS trả IP mới | Authority/certificate không khớp hoặc trust chain sai | Kiểm tra hostname xác minh, SAN và TLS config |
| CPU/tài nguyên client tăng khi dùng round_robin | Quá nhiều endpoint/connection hoặc refresh liên tục | Kiểm soát kích thước endpoint, refresh và Channel lifecycle |

Nên theo dõi **số địa chỉ được phân giải**, **số Subchannel theo trạng thái**, **RPC theo backend nếu có instrumentation**, **connection churn**, **reconnect/backoff**, latency và status code. Không dùng riêng CPU server để kết luận policy có phân phối đều; một backend có thể nhận ít RPC nhưng xử lý các stream rất dài.

## 12. Kiểm thử name resolution và load balancing

Một kiểm thử hữu ích cần xác minh cả hai lớp:

1. **Resolver test:** target logic trả đúng danh sách endpoint khi nguồn discovery thay đổi; xử lý lỗi DNS và refresh.
2. **Policy test:** khi nhiều Subchannel READY, picker chọn theo policy; khi một Subchannel lỗi, RPC mới không tiếp tục được gửi vào đường không sẵn sàng.
3. **Integration test:** khởi chạy nhiều server test, gọi qua Channel và quan sát phân phối; không suy ra chỉ từ một lần gọi.
4. **Failure test:** dừng một backend, quan sát status/reconnect và xác minh các backend còn lại tiếp tục nhận RPC mới.
5. **Streaming test:** ngắt backend đang giữ stream, kiểm tra client nhận lỗi và resume bằng cursor nếu use case yêu cầu.
6. **TLS test:** xác minh mỗi backend có identity/certificate hợp lệ theo authority được sử dụng.

**In-process transport** hữu ích để test service và status, nhưng không chứng minh DNS, TCP, TLS hay proxy hoạt động đúng. Để kiểm tra load balancing qua mạng, cần nhiều endpoint thực hoặc một resolver test có thể điều khiển và instrumentation để xác định backend đã nhận từng RPC.

## 13. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo một Spring client dùng **dns:///orders.internal:8443** và một ManagedChannel dùng chung.
2. Cấu hình **pick_first**, sau đó **round_robin** bằng service config. Ghi lại khác biệt khi resolver trả một và nhiều address group.
3. Chạy ba backend có cùng service, gửi nhiều unary RPC và quan sát backend nhận từng call. Đảm bảo các Subchannel đã READY trước khi đánh giá phân phối.
4. Dừng một backend; theo dõi trạng thái Subchannel, RPC lỗi và việc round_robin tiếp tục chọn những backend còn lại.
5. Đổi DNS record hoặc kết quả custom resolver; đo thời gian client nhìn thấy địa chỉ mới thay vì giả định TTL là thời gian hội tụ chính xác.
6. Mở server-streaming RPC rồi dừng backend đang phục vụ stream. Xác minh stream không tự chuyển backend và thiết kế cursor/reconnect nếu cần.
7. Bật TLS với hostname/authority phù hợp và kiểm tra certificate trên tất cả backend.

### Câu hỏi tự kiểm tra

**1. NameResolver và LoadBalancer khác nhau thế nào?**  
NameResolver tìm endpoint từ target; LoadBalancer chọn endpoint/Subchannel để phục vụ RPC mới.

**2. DNS trả ba IP có nghĩa mỗi RPC sẽ được gửi tới IP khác nhau không?**  
Không. Còn phụ thuộc policy. Với **pick_first**, nhiều RPC có thể tiếp tục dùng một backend; **round_robin** mới phân phối giữa các Subchannel sẵn sàng.

**3. round_robin có chia đều CPU hoặc thời gian xử lý không?**  
Không. Nó luân phiên RPC mới trên các Subchannel READY; thời lượng và chi phí mỗi RPC có thể khác nhau.

**4. Vì sao L4 load balancer có thể không chia đều RPC gRPC?**  
Vì gRPC thường dùng HTTP/2 connection dài hạn. L4 LB phân phối connection TCP, không nhất thiết phân phối từng RPC bên trong connection.

**5. Channel có tự migrate một streaming RPC sang backend khác khi backend hiện tại chết không?**  
Không. Stream đang chạy thường kết thúc lỗi. Ứng dụng cần mở RPC mới và resume bằng cursor/sequence nếu nghiệp vụ hỗ trợ.

**6. Subchannel READY có đồng nghĩa backend khỏe về nghiệp vụ không?**  
Không. READY phản ánh transport; health checking/readiness ở tầng ứng dụng là tín hiệu riêng.

**7. Vì sao không tạo ManagedChannel mới cho từng request?**  
Việc đó tăng số connection, handshake và discovery, đồng thời làm mất lợi ích tái sử dụng transport và quản lý LB liên tục.

## Tổng kết

**Name resolution** biến target logic thành các địa chỉ backend; **LoadBalancer** dùng danh sách đó và trạng thái Subchannel để chọn đường đi cho mỗi RPC mới. Trong grpc-java, **ManagedChannel** phối hợp resolver, policy, picker và connection; Spring nên quản lý Channel dùng chung và cấu hình policy có chủ đích. **pick_first** thường giữ một backend đang sẵn sàng, còn **round_robin** phân phối RPC mới trên các Subchannel READY khi resolver cung cấp nhiều endpoint. DNS, health checking, proxy, TLS và vòng đời streaming đều ảnh hưởng tới kết quả thực tế, vì vậy cần kiểm thử failure/reconnect và đo phân phối trên hệ thống đang chạy.







