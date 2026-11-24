# Danh sách rỗng, dịch vụ không tồn tại và lỗi truy vấn

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích ý nghĩa của danh sách instance rỗng khi gọi `DiscoveryClient`.
- Phân biệt service ID không có trong registry, service đã biết nhưng chưa có instance và lỗi kết nối registry.
- Chẩn đoán các nguyên nhân thường gặp từ cấu hình, vòng đời đăng ký, cache và mạng.
- Xử lý kết quả discovery an toàn, không nhầm lỗi truy vấn với việc không có instance.
- Thiết kế retry, fallback, log và metric phù hợp cho ứng dụng gọi dịch vụ.

## 1. Hợp đồng của DiscoveryClient

`DiscoveryClient` là abstraction của Spring Cloud để truy vấn các instance theo service ID. Hai phương thức thường dùng là:

- `getInstances(String serviceId)`: trả về danh sách `ServiceInstance` mà client hiện biết cho service ID đó.
- `getServices()`: trả về danh sách service ID mà client hiện biết trong registry.

Khi không có instance nào cho một service ID, cách biểu diễn thông thường của `getInstances` là một danh sách rỗng. Đây là kết quả hợp lệ, không tự nó chứng minh registry bị lỗi và cũng không nhất thiết làm phát sinh exception.

Cần phân biệt ba kết quả:

| Kết quả | Ý nghĩa | Hành động phù hợp |
| --- | --- | --- |
| Danh sách có instance | Client tìm thấy một hoặc nhiều endpoint trong dữ liệu discovery hiện tại. | Chọn endpoint bằng cơ chế load balancing phù hợp và tiếp tục gọi. |
| Danh sách rỗng | Hiện không có instance nào được trả về cho service ID đó. | Kiểm tra service ID, trạng thái đăng ký, registry cache và thời điểm khởi động. |
| Phát sinh exception | Việc truy vấn discovery gặp lỗi ở implementation hoặc tầng kết nối. | Ghi nhận lỗi, phân loại nguyên nhân và áp dụng xử lý lỗi có giới hạn. |

`DiscoveryClient` không quy định một exception duy nhất cho mọi implementation. Eureka, Consul, Kubernetes hoặc implementation tùy chỉnh có thể báo lỗi ở các dạng runtime exception khác nhau. Vì vậy, code gọi cần giữ lại nguyên nhân gốc và không phụ thuộc vào một exception cụ thể nếu abstraction không cam kết loại exception đó.

`ServiceRegistry` chủ yếu phục vụ thao tác đăng ký, hủy đăng ký và cập nhật trạng thái instance. Nó liên quan đến vòng đời đăng ký; truy vấn danh sách instance thuộc vai trò của `DiscoveryClient`.

## 2. Phân biệt service không tồn tại và service chưa có instance

Một danh sách rỗng có thể xuất hiện trong nhiều tình huống:

- Service ID chưa từng được đăng ký.
- Tên service ID bị gõ sai hoặc khác quy ước đặt tên giữa bên gọi và bên cung cấp.
- Ứng dụng cung cấp dịch vụ chưa khởi động hoặc chưa hoàn tất đăng ký.
- Tất cả instance đã deregister, bị loại khỏi registry hoặc hiện không được công bố.
- Client chưa tải registry, hoặc cấu hình tắt việc fetch registry.
- Registry cache của client chưa kịp cập nhật sau khi service vừa đăng ký hoặc thay đổi.
- Client và server đang nhìn thấy các trạng thái khác nhau trong lúc mạng hoặc quá trình đồng bộ bị gián đoạn.

Có thể dùng `getServices()` để hỗ trợ chẩn đoán:

~~~~java
List<String> serviceIds = discoveryClient.getServices();
boolean serviceKnown = serviceIds.contains(serviceId);

List<ServiceInstance> instances =
        discoveryClient.getInstances(serviceId);
~~~~

Nếu service ID có trong `getServices()` nhưng `getInstances(serviceId)` rỗng, registry view hiện tại biết tên dịch vụ nhưng không trả về instance nào cho lần truy vấn đó. Nếu service ID không có trong danh sách, tên đó chưa xuất hiện trong registry view mà client đang nhìn thấy.

Đây chỉ là thông tin chẩn đoán. Hai lời gọi trên không phải một giao dịch nguyên tử; registry có thể thay đổi giữa hai lần đọc. Danh sách service ID cũng có thể đến từ cache cục bộ, vì vậy không nên kết luận rằng dịch vụ chắc chắn không tồn tại ở mọi node hoặc mọi thời điểm.

### Kiểm tra service ID

Service ID phải được thống nhất giữa bên cung cấp và bên gọi. Với Spring Boot, giá trị thường bắt nguồn từ `spring.application.name`. Hãy kiểm tra:

- Tên trong cấu hình mặc định và các profile đang kích hoạt.
- Biến môi trường ghi đè cấu hình, ví dụ `SPRING_APPLICATION_NAME`.
- Tên service được dùng trong code gọi `getInstances`.
- Quy tắc chuẩn hóa chữ hoa/chữ thường của implementation registry đang dùng.

Không nên dựa vào việc một registry hiển thị tên viết hoa hay viết thường trên dashboard để tự suy ra cách so sánh chuỗi trong mọi implementation. Dùng một service ID thống nhất và kiểm tra đúng giá trị mà client nhận được.

## 3. Vì sao getInstances có thể trả về danh sách rỗng?

### Service chưa đăng ký

Nếu ứng dụng cung cấp dịch vụ chưa khởi động, chưa kết nối được registry hoặc cấu hình đăng ký bị tắt, registry sẽ chưa có instance để trả về. Với Eureka Client, hãy kiểm tra URL server, trạng thái đăng ký và log khởi động. Với Consul, kiểm tra agent/server, service registration và health state.

### Chưa fetch registry hoặc cache chưa cập nhật

Một ứng dụng có thể đăng ký chính nó nhưng không tải danh sách dịch vụ khác nếu cấu hình fetch registry bị tắt. Tùy implementation, dữ liệu discovery có thể được cache và làm mới theo chu kỳ. Vì vậy, một service vừa khởi động có thể chưa xuất hiện ngay trong kết quả truy vấn của client khác.

Đừng dùng một khoảng chờ cố định làm bảo đảm rằng registry đã đồng bộ. Hãy quan sát log, cấu hình refresh và trạng thái registry của implementation đang dùng.

### Không còn instance khả dụng

Instance có thể đã deregister khi shutdown, bị đánh dấu unhealthy hoặc bị loại khỏi registry sau khi heartbeat/lease hết hạn. Cơ chế health check và eviction có thể có độ trễ. Registry phản ánh trạng thái discovery, không phải phép đo tức thời cho mọi chức năng nghiệp vụ của instance.

### Service ID không khớp

Sai tên, sai profile, khoảng trắng thừa hoặc khác biệt quy ước đặt tên có thể khiến truy vấn không khớp. Nên log service ID đã nhận sau khi cấu hình được nạp, đồng thời dùng hằng số hoặc cấu hình tập trung cho các tên dịch vụ quan trọng.

## 4. Phân biệt kết quả rỗng với lỗi truy vấn

Danh sách rỗng và exception cần được xử lý riêng.

| Tình huống | Dấu hiệu thường gặp | Hướng điều tra |
| --- | --- | --- |
| Service ID chưa có trong registry view | Trả về danh sách rỗng; ID có thể không nằm trong `getServices()`. | Kiểm tra tên dịch vụ, đăng ký và profile. |
| Service đã biết nhưng chưa có instance | ID xuất hiện trong danh sách service; instance list rỗng. | Kiểm tra readiness, health check, deregistration và đồng bộ. |
| Registry không truy cập được | Có thể phát sinh timeout, lỗi kết nối hoặc runtime exception tùy implementation. | Kiểm tra DNS, network, port, TLS, xác thực và trạng thái server. |
| Cấu hình endpoint sai | Lỗi phân giải hostname, kết nối thất bại hoặc truy vấn đến nhầm môi trường. | Kiểm tra URL registry và cấu hình theo môi trường. |
| Lỗi phía implementation | Exception khi đọc hoặc chuyển đổi dữ liệu discovery. | Ghi lại stack trace, phiên bản thư viện và lỗi gốc. |

Một số client có thể tiếp tục dùng dữ liệu cache khi registry tạm thời mất kết nối; implementation khác có thể báo lỗi ngay. Không được giả định mọi lỗi kết nối đều biến thành danh sách rỗng. Ngược lại, không được tự kết luận registry đã hỏng chỉ vì một service ID trả về list rỗng.

## 5. Viết code xử lý kết quả rõ ràng

Ví dụ service wrapper kiểm tra đầu vào, giữ nguyên sự khác biệt giữa list rỗng và lỗi truy vấn, đồng thời bảo toàn nguyên nhân gốc:

~~~~java
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceLookup {

    private static final Logger log =
            LoggerFactory.getLogger(ServiceLookup.class);

    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        if (serviceId == null || serviceId.trim().isEmpty()) {
            throw new IllegalArgumentException("serviceId must not be blank");
        }

        try {
            List<ServiceInstance> instances =
                    discoveryClient.getInstances(serviceId);

            if (instances.isEmpty()) {
                log.info("No instances currently discovered for serviceId={}",
                        serviceId);
            }

            return instances;
        } catch (RuntimeException ex) {
            log.warn("Discovery query failed for serviceId={}", serviceId, ex);
            throw new IllegalStateException(
                    "Unable to query discovery for serviceId=" + serviceId, ex);
        }
    }
}
~~~~

Ở đây, danh sách rỗng được trả về như một kết quả nghiệp vụ có thể xử lý. Exception được ghi log rồi truyền tiếp dưới dạng lỗi có nguyên nhân gốc. Trong ứng dụng thực tế, có thể dùng exception chuyên biệt của domain thay cho `IllegalStateException` để tầng gọi phân loại lỗi rõ hơn.

Không nên viết code bắt mọi exception rồi trả về `Collections.emptyList()`. Cách đó biến lỗi kết nối, lỗi xác thực hoặc lỗi lập trình thành thông báo giả rằng dịch vụ không có instance. Khi ấy hệ thống rất khó phân biệt một service thực sự chưa được đăng ký với registry đang gặp sự cố.

### Không tự chọn phần tử đầu tiên làm load balancing

Không nên dùng `instances.get(0)` như một thuật toán cân bằng tải. Thứ tự danh sách không phải cam kết phân phối tải, độ khỏe hoặc locality. Khi cần gọi bằng service ID, hãy tích hợp Spring Cloud LoadBalancer với HTTP client tương ứng, để cơ chế chọn instance được quản lý theo cấu hình và chiến lược đã chọn.

Nếu tự chọn instance vì một yêu cầu đặc biệt, cần xác định rõ chiến lược, xử lý danh sách rỗng, loại endpoint không phù hợp và cập nhật danh sách khi registry thay đổi.

## 6. Quy trình chẩn đoán khi không tìm thấy instance

~~~~mermaid
flowchart TD
    A[Nhận serviceId] --> B{serviceId hợp lệ?}
    B -->|Không| C[Báo lỗi cấu hình đầu vào]
    B -->|Có| D[Gọi DiscoveryClient]
    D --> E{Truy vấn phát sinh exception?}
    E -->|Có| F[Kiểm tra registry, mạng, TLS, auth]
    E -->|Không| G{Danh sách có instance?}
    G -->|Có| H[Chuyển cho LoadBalancer / caller]
    G -->|Không| I[Đọc getServices và kiểm tra registry view]
    I --> J{Service ID có trong view?}
    J -->|Không| K[Kiểm tra tên, đăng ký, fetch và môi trường]
    J -->|Có| L[Kiểm tra readiness, health, cache và deregistration]
~~~~

Thực hiện theo thứ tự sau:

1. **Xác nhận đầu vào:** ghi lại service ID sau khi cấu hình được nạp; kiểm tra null, rỗng, khoảng trắng và tên sai.
2. **Kiểm tra service list:** đọc `getServices()` để biết client hiện nhìn thấy những service ID nào.
3. **Kiểm tra instance list:** gọi `getInstances(serviceId)` và ghi nhận số lượng instance.
4. **Kiểm tra phía provider:** xác nhận ứng dụng đã khởi động, đăng ký đúng service ID và đang ở trạng thái sẵn sàng.
5. **Kiểm tra registry:** xác nhận client kết nối đúng server/agent, đã fetch dữ liệu và không bị chặn bởi xác thực hoặc TLS.
6. **Kiểm tra thời gian:** xem thời điểm đăng ký, heartbeat, health check, deregistration và chu kỳ refresh cache.
7. **Kiểm tra mạng:** thử phân giải DNS và kết nối đến endpoint từ đúng môi trường chạy caller.

Dashboard hoặc CLI của registry giúp đối chiếu trạng thái phía server. Tuy nhiên, kết quả trên dashboard không thay thế việc kiểm tra registry view mà chính ứng dụng caller đang sử dụng.

## 7. Retry, timeout và fallback

Không phải trường hợp không tìm thấy instance nào cũng nên retry.

- **Service ID sai hoặc service chưa được triển khai:** đây thường là lỗi cấu hình hoặc trạng thái dài hạn. Retry liên tục chỉ tạo thêm tải và log nhiễu.
- **Ứng dụng đang khởi động:** có thể áp dụng số lần thử giới hạn với backoff ngắn nếu quy trình triển khai cho phép service đăng ký muộn.
- **Registry tạm thời mất kết nối:** dùng timeout hữu hạn và retry có giới hạn, backoff cùng jitter. Kết hợp circuit breaker nếu phù hợp để tránh mọi request cùng dồn vào registry đang lỗi.
- **Không có instance khỏe mạnh:** trả lỗi có ý nghĩa cho caller, dùng fallback đã được thiết kế hoặc đưa công việc vào hàng đợi nếu nghiệp vụ cho phép.

Retry nên được đặt tại một tầng có trách nhiệm rõ ràng. Nếu HTTP client, gateway và service mesh đều retry độc lập, số request thực tế có thể tăng theo cấp số nhân. Hãy đặt deadline tổng cho request và giới hạn tổng số lần thử.

Fallback không được giả vờ rằng request đã thành công. Nếu trả dữ liệu cache, cần xác định thời hạn và mức độ cũ được chấp nhận. Nếu từ chối request, hãy trả trạng thái lỗi phù hợp với hợp đồng API và cung cấp thông tin để caller có thể thử lại sau.

## 8. Log, metric và cảnh báo

Để phát hiện sớm sự cố discovery, nên theo dõi:

- Số lần lookup theo service ID và kết quả: found, empty, error.
- Độ trễ truy vấn discovery và tỷ lệ exception.
- Số instance được trả về theo service ID.
- Số request thất bại vì không chọn được instance.
- Trạng thái kết nối đến Eureka/Consul hoặc nguồn discovery đang sử dụng.
- Thời gian từ lúc provider đăng ký đến khi caller nhìn thấy instance.

Log nên có service ID, kết quả, môi trường, thời điểm và exception gốc khi có lỗi. Tránh ghi username, password, token hoặc thông tin nhạy cảm. Với metric, dùng service ID ổn định làm label; tránh dùng URL đầy đủ, instance ID ngẫu nhiên hoặc dữ liệu đầu vào không giới hạn vì sẽ tạo cardinality lớn.

Cần phân biệt cảnh báo “không có instance” với “không truy vấn được registry”. Hai sự kiện có nguyên nhân và cách xử lý khác nhau.

## 9. Kiểm thử các tình huống biên

| Tình huống thử | Kết quả cần xác nhận |
| --- | --- |
| Truy vấn service ID hợp lệ có hai instance | Trả về hai instance và caller chọn đích bằng load balancer. |
| Truy vấn service ID không tồn tại | Nhận list rỗng; không coi đó là exception mặc định. |
| Provider chưa khởi động | Caller xử lý trạng thái chưa có instance mà không crash hoặc retry vô hạn. |
| Provider deregister hoặc bị đánh dấu unhealthy | Số instance trong registry view giảm theo chu kỳ cập nhật. |
| Registry bị ngắt kết nối | Hệ thống ghi nhận lỗi truy vấn hoặc hành vi cache đúng với implementation; không âm thầm biến lỗi thành list rỗng. |
| Sai service ID do cấu hình profile | Log chỉ ra tên thực tế đang được truy vấn và hỗ trợ tìm ra cấu hình sai. |
| Registry phục hồi sau gián đoạn | Client cập nhật lại registry và có thể tìm thấy instance sau khi đồng bộ. |

## Ghi nhớ

- `getInstances(serviceId)` thường trả về list rỗng khi hiện không có instance; đây là kết quả hợp lệ.
- `getServices()` giúp chẩn đoán service ID có trong registry view hay không, nhưng không phải bằng chứng tuyệt đối về trạng thái toàn hệ thống.
- Service ID không tồn tại, service chưa có instance và lỗi truy vấn registry là ba trường hợp cần phân biệt.
- Không bắt exception rồi chuyển thành list rỗng; hãy giữ nguyên nguyên nhân để chẩn đoán.
- Không dùng phần tử đầu tiên của danh sách như thuật toán load balancing.
- Retry phải có giới hạn, timeout và backoff; không retry vô hạn cho service ID sai hoặc không có instance lâu dài.
- Theo dõi riêng kết quả empty và error để vận hành discovery chính xác.
