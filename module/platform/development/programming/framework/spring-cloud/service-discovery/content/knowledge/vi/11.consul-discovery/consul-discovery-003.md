# Khởi tạo Consul cục bộ và giới hạn của chế độ phát triển

Consul cung cấp service discovery thông qua agent và catalog. Trong môi trường local, có thể chạy một Consul agent ở chế độ phát triển để thử đăng ký service, health check, tra cứu qua HTTP API và tích hợp với Spring Cloud Consul.

Lệnh `consul agent -dev` giúp khởi động nhanh một node dùng cho học tập và kiểm thử. Chế độ này dùng cấu hình đơn giản, dữ liệu tạm thời và không tạo cụm có tính sẵn sàng cao. Nó phù hợp để hiểu luồng discovery trên máy cá nhân, nhưng không phải cấu hình triển khai production.

## 1. Consul agent và các thành phần cơ bản

Consul không chỉ là một tiến trình server nhận danh sách service. Mỗi node chạy một **Consul agent**. Agent có thể hoạt động ở chế độ server hoặc client:

- **Server agent:** tham gia cụm Consul, duy trì catalog và trạng thái cluster, tham gia Raft consensus để quản lý dữ liệu nhất quán.
- **Client agent:** chạy trên node có workload, thực hiện health check, đăng ký service và chuyển tiếp truy vấn tới server.
- **Service:** ứng dụng hoặc tiến trình mà Consul cần công bố để consumer tìm thấy.
- **Health check:** phép kiểm tra tình trạng service hoặc node, ví dụ HTTP, TCP, TTL hoặc script check theo cấu hình.
- **Catalog:** tập hợp service và node mà Consul biết; consumer có thể tra cứu qua HTTP API, DNS hoặc thư viện tích hợp.

Trong một hệ thống thực tế, client agent thường chạy gần workload và kết nối tới một hoặc nhiều server agent. Trong chế độ local dev, một agent đơn lẻ kết hợp vai trò server với giao diện client để việc thử nghiệm không cần dựng cả cụm.

## 2. Cài đặt và kiểm tra Consul CLI

Cần có Consul binary trên máy phát triển. Sau khi cài đặt, mở terminal và kiểm tra:

```bash
consul version
```

Lệnh hiển thị phiên bản CLI. Nếu terminal báo không tìm thấy lệnh, hãy kiểm tra Consul đã được cài đặt và thư mục chứa binary đã nằm trong PATH hay chưa.

Có thể chạy Consul trực tiếp từ terminal đang mở. Khi dùng môi trường local, hãy giữ tiến trình agent hoạt động trong lúc thử nghiệm; nhấn Ctrl+C tại terminal đó để dừng agent sau khi hoàn tất.

## 3. Khởi động Consul ở chế độ phát triển

Chạy lệnh:

```bash
consul agent -dev -ui -client=127.0.0.1
```

Ý nghĩa các tham số:

- `agent`: khởi chạy Consul agent.
- `-dev`: bật cấu hình phát triển đơn node, thuận tiện cho học tập và kiểm thử cục bộ.
- `-ui`: bật giao diện web quản trị.
- `-client=127.0.0.1`: giới hạn các giao diện client như HTTP API/UI ở loopback, để chỉ máy local truy cập được.

Trong chế độ dev, Consul tự thiết lập một server đơn và dùng dữ liệu tạm thời. Không cần cấu hình bootstrap cluster hay các peer server cho bài thực hành này.

Sau khi agent khởi động, có thể truy cập giao diện:

```text
http://127.0.0.1:8500/ui/
```

HTTP API mặc định thường lắng nghe trên cổng `8500`. DNS interface của Consul thường dùng cổng `8600`. Các cổng và địa chỉ bind có thể thay đổi theo cấu hình; hãy kiểm tra log startup nếu giao diện không truy cập được.

### Kiểm tra agent

Mở terminal thứ hai và chạy:

```bash
consul members
```

Lệnh hiển thị các member mà agent biết. Trong chế độ dev đơn node, thường chỉ thấy một member local ở trạng thái alive.

Có thể kiểm tra leader:

```bash
curl http://127.0.0.1:8500/v1/status/leader
```

Trong cấu hình dev server đơn, API trả về địa chỉ leader hiện tại. Nếu phản hồi rỗng hoặc không truy cập được, kiểm tra agent còn chạy và log khởi động.

## 4. Khám phá giao diện và HTTP API

Consul UI giúp quan sát service, node và health check. Có thể mở tab Services để xem những service đã đăng ký. Khi chưa có ứng dụng nào đăng ký, danh sách service nghiệp vụ có thể trống; đây là trạng thái bình thường.

Một số API thường dùng:

| API | Mục đích |
|---|---|
| `GET /v1/agent/self` | Đọc cấu hình và thông tin agent local |
| `GET /v1/agent/services` | Liệt kê service đã đăng ký trên agent local |
| `GET /v1/catalog/services` | Liệt kê service trong catalog của cluster |
| `GET /v1/health/service/{service}` | Đọc instance và health check của một service |
| `GET /v1/status/leader` | Đọc địa chỉ leader của Consul server cluster |

Ví dụ xem các service trong catalog:

```bash
curl http://127.0.0.1:8500/v1/catalog/services
```

Kết quả là JSON map tên service với danh sách tag. Nếu chưa đăng ký service nào ngoài service hệ thống, kết quả có thể chưa có service ứng dụng mong muốn.

Đọc health của service cụ thể:

```bash
curl http://127.0.0.1:8500/v1/health/service/inventory-service
```

API trả về các instance và trạng thái check liên quan. Có thể yêu cầu chỉ trả về instance đang passing bằng tham số `passing=true`:

```bash
curl "http://127.0.0.1:8500/v1/health/service/inventory-service?passing=true"
```

Lưu ý: `/v1/agent/services` phản ánh các registration mà agent local quản lý; `/v1/catalog/services` là góc nhìn catalog cluster. Hai API có phạm vi khác nhau và không nên thay thế cho nhau khi điều tra lỗi.

## 5. Đăng ký service thử nghiệm trực tiếp qua agent

Có thể đăng ký một service đơn giản bằng HTTP API của agent. Ví dụ đăng ký service tên `demo-api` tại cổng `8081` với HTTP health check:

```bash
curl --request PUT \
  --data '{
    "Name": "demo-api",
    "ID": "demo-api-local-1",
    "Address": "127.0.0.1",
    "Port": 8081,
    "Check": {
      "HTTP": "http://127.0.0.1:8081/actuator/health",
      "Interval": "10s",
      "Timeout": "2s"
    }
  }' \
  http://127.0.0.1:8500/v1/agent/service/register
```

Ví dụ giả định ứng dụng demo đang chạy tại cổng `8081` và cung cấp endpoint health tương ứng. Nếu endpoint chưa tồn tại hoặc ứng dụng chưa chạy, check sẽ thất bại và service có thể mang trạng thái critical.

Sau khi đăng ký, kiểm tra:

```bash
curl http://127.0.0.1:8500/v1/agent/services
curl http://127.0.0.1:8500/v1/health/service/demo-api
```

Để hủy registration thử nghiệm:

```bash
curl --request PUT \
  http://127.0.0.1:8500/v1/agent/service/deregister/demo-api-local-1
```

API deregister cần ID của registration trên agent. Không nhầm ID này với service name; một service có thể có nhiều registration/instance ID khác nhau.

## 6. Kết nối Spring Boot với Consul local

Spring Cloud Consul cung cấp discovery integration để ứng dụng Spring Boot đăng ký và tra cứu service thông qua Consul agent. Trong dự án, cần có dependency discovery tương ứng với phiên bản Spring Cloud đang dùng, thường là starter Consul Discovery, cùng Spring Boot Actuator nếu sử dụng HTTP health check.

Ví dụ cấu hình provider:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: 127.0.0.1
      port: 8500
      discovery:
        register: true
        service-name: ${spring.application.name}
        health-check-path: /actuator/health
        health-check-interval: 10s

server:
  port: 8081

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Khi ứng dụng khởi động, discovery integration có thể đăng ký `inventory-service` với Consul agent local. Agent thực hiện health check theo cấu hình và cập nhật trạng thái trong catalog.

Các giá trị cần khớp với môi trường:

- `spring.application.name` xác định tên ứng dụng logic.
- `spring.cloud.consul.host` và `port` chỉ tới HTTP API của Consul agent.
- `service-name` là tên service được đăng ký; nếu override, consumer phải tra cứu đúng tên này.
- `health-check-path` phải tồn tại và truy cập được từ agent.
- `server.port` là cổng ứng dụng mà provider quảng bá, không phải cổng Consul.

Nếu chạy ứng dụng trong container, `127.0.0.1` bên trong container là chính container đó, không phải máy host. Khi ấy, cần cấu hình hostname hoặc địa chỉ mà container có thể truy cập tới Consul agent, đồng thời điều chỉnh địa chỉ service được quảng bá để consumer kết nối được.

### Ví dụ endpoint health

Với dependency Spring Boot Actuator, endpoint health mặc định thường là `/actuator/health`. Có thể kiểm tra trực tiếp:

```bash
curl http://127.0.0.1:8081/actuator/health
```

Nếu Consul health check không truy cập được endpoint, hãy kiểm tra ứng dụng đã khởi động, cổng, path, network và cấu hình exposure. Không mở rộng exposure endpoint quản trị quá mức chỉ để làm cho bài thử nghiệm chạy được.

## 7. Tra cứu service từ ứng dụng consumer

Consumer cũng cần cấu hình kết nối tới Consul agent. Ví dụ:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: 127.0.0.1
      port: 8500
      discovery:
        register: true
```

Consumer có thể sử dụng `DiscoveryClient` để lấy danh sách instance:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

Kết quả là danh sách instance mà discovery client nhìn thấy. Nếu danh sách rỗng, hãy kiểm tra service name, registration, health check và góc nhìn catalog.

Nếu muốn gọi HTTP theo service name, có thể dùng client tích hợp Spring Cloud LoadBalancer. Cần thêm dependency LoadBalancer tương ứng và cấu hình client phù hợp; chỉ có Consul Discovery starter không tự bảo đảm mọi HTTP client đều hiểu hostname service như một service ID.

## 8. Những gì chế độ dev giúp kiểm thử

Consul local dev mode phù hợp để thực hành:

- Khởi động agent và xem UI/API.
- Đăng ký service thủ công hoặc qua Spring Cloud Consul.
- Quan sát service ID, instance ID, address, port và tags.
- Khai báo HTTP/TCP/TTL health check.
- Tra cứu catalog và health endpoint.
- Thử đăng ký, cập nhật và deregister service.
- Kiểm tra cách consumer dùng DiscoveryClient và LoadBalancer.

Có thể thử một luồng đầy đủ:

1. Khởi động Consul agent ở chế độ dev.
2. Khởi động `inventory-service` với cấu hình Consul.
3. Xác minh service xuất hiện trong UI hoặc `/v1/catalog/services`.
4. Xác minh health check passing bằng `/v1/health/service/inventory-service?passing=true`.
5. Khởi động `order-service` và gọi tra cứu qua DiscoveryClient.
6. Dừng provider và quan sát health check hoặc registration được cập nhật, tùy cách shutdown và cấu hình deregistration.

Các bước này giúp hiểu vòng đời service trong một môi trường đơn giản trước khi làm việc với cluster nhiều node.

## 9. Giới hạn của chế độ phát triển

`-dev` được thiết kế để thử nghiệm cục bộ. Các giới hạn chính:

### Dữ liệu tạm thời, không dùng làm nơi lưu trữ bền vững

Consul dev mode dùng dữ liệu trong bộ nhớ và môi trường tạm thời. Khi agent dừng, dữ liệu đăng ký và trạng thái thử nghiệm có thể mất. Không dùng chế độ này làm catalog bền vững cho hệ thống cần khôi phục sau restart.

### Một server duy nhất, không có HA

Một agent dev đơn node không có server peer để duy trì quorum hoặc tiếp tục phục vụ khi node gặp sự cố. Nếu agent dừng, API discovery local cũng dừng. Cache của consumer có thể còn giữ dữ liệu cũ trong một khoảng thời gian, nhưng điều đó không biến dev agent thành cụm HA.

### Không mô phỏng failure domain thực tế

Một node local không thể đại diện đầy đủ cho các tình huống như mất mạng giữa các server, mất một availability zone, lỗi quorum, replication chậm hoặc client agent mất kết nối tới server. Những hành vi đó cần môi trường cluster và kịch bản kiểm thử riêng.

### Cấu hình đơn giản không đại diện bảo mật production

Không nên giả định các thiết lập mặc định của dev mode đáp ứng yêu cầu ACL, TLS, gossip encryption, network segmentation hay quản trị token trong production. Dev mode thường được cấu hình để giảm bước thiết lập, vì vậy cần chủ động thiết lập bảo mật đầy đủ khi xây dựng môi trường thật.

### Không dùng chung cho nhiều người hoặc môi trường

Dữ liệu local có thể bị thay đổi bởi các bài thực hành, tiến trình và ứng dụng chạy trên cùng máy. Một service test có thể trùng tên với service khác, health check có thể trỏ nhầm cổng hoặc người học có thể dừng agent trong khi ứng dụng khác vẫn đang phụ thuộc nó.

### Không phản ánh chính xác tải và quy mô

Một agent đơn không cho biết năng lực của cluster nhiều server khi số lượng registration, health check và truy vấn tăng cao. Không dùng kết quả benchmark trên dev mode để kết luận năng lực production.

## 10. Từ local dev tới cấu hình production

Khi chuyển từ học tập sang môi trường thật, cần thay đổi cách triển khai:

| Khía cạnh | Local dev | Production |
|---|---|---|
| Số server | Một agent dev | Cụm nhiều server, thường 3 hoặc 5 server để duy trì quorum |
| Dữ liệu | Tạm thời, trong bộ nhớ | Data directory bền vững và quy trình backup/snapshot |
| Bootstrap | `consul agent -dev` | Cấu hình cluster, bootstrap expectation và join peer có kiểm soát |
| Client agent | Có thể gộp trong tiến trình local | Agent client trên node/workload hoặc mô hình kết nối phù hợp |
| Bảo mật | Loopback và thiết lập tối giản | ACL, token, TLS, gossip encryption và network policy |
| Health check | Check local để học | Check phản ánh readiness, timeout và dependency thực tế |
| Quan sát | UI và CLI local | Metrics, log, audit, alert và giám sát quorum |
| Khôi phục | Khởi động lại và đăng ký lại | Snapshot/restore, nâng cấp có kiểm soát và diễn tập sự cố |

Cụm Consul server dùng Raft consensus nên cần quorum để thực hiện các thay đổi nhất quán. Với số server là 3, cluster có thể chịu mất một server; với 5 server, có thể chịu mất hai server, nếu các node còn lại vẫn liên lạc và đạt quorum. Tăng số server quá nhiều không tự động làm cluster tốt hơn; cần chọn số node và vị trí triển khai phù hợp.

Không dùng `-dev` để triển khai production. Hãy tạo cấu hình agent riêng, đặt data directory bền vững, khai báo địa chỉ bind/advertise chính xác, thiết lập server/client role, ACL/TLS/gossip encryption, giới hạn network và kiểm thử backup/restore.

## 11. Lỗi thường gặp khi chạy Consul local

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Lệnh `consul` không chạy | Binary chưa cài hoặc PATH chưa đúng | Kiểm tra cài đặt và `consul version` |
| Cổng 8500 đã được sử dụng | Một Consul agent hoặc tiến trình khác đang nghe cổng | Kiểm tra tiến trình và cấu hình port |
| Không mở được UI | Agent chưa chạy, UI chưa bật hoặc client bind khác loopback | Kiểm tra log, `-ui` và địa chỉ client |
| Service không xuất hiện | Provider chưa đăng ký hoặc trỏ sai agent | Kiểm tra `spring.cloud.consul.host/port` và agent services |
| Health check critical | Endpoint sai, provider chưa chạy hoặc agent không truy cập được | Kiểm tra URL check từ góc nhìn agent và log ứng dụng |
| Consumer nhận danh sách rỗng | Sai service name, service chưa passing hoặc catalog chưa cập nhật | Kiểm tra catalog, health API và tên đăng ký |
| Ứng dụng trong container không kết nối được | Dùng `127.0.0.1` trỏ vào chính container | Dùng hostname/địa chỉ host có thể route tới agent |
| Dữ liệu biến mất sau khi dừng agent | Đang dùng dev mode với dữ liệu tạm thời | Đây là giới hạn dự kiến; không dùng dev mode cho dữ liệu cần giữ |

Khi debug, kiểm tra lần lượt agent có chạy không, API local có truy cập được không, provider có đăng ký không, health check có passing không và consumer có tra cứu đúng tên không. Cách này giúp xác định lỗi nằm ở Consul agent, provider registration, health check hay consumer lookup.

## 12. Checklist thực hành

1. `consul version` hiển thị phiên bản CLI.
2. Agent khởi động với `consul agent -dev -ui -client=127.0.0.1`.
3. UI mở được tại `http://127.0.0.1:8500/ui/`.
4. `consul members` hiển thị agent local.
5. API `/v1/status/leader` trả về leader.
6. Provider Spring Boot kết nối đúng Consul host và port.
7. Service xuất hiện trong catalog với đúng tên.
8. Health check passing khi ứng dụng sẵn sàng.
9. Consumer lấy được instance qua DiscoveryClient.
10. Đã hiểu dữ liệu dev mode không bền vững và agent đơn không có HA.

Consul local dev mode là cách nhanh để học agent, service catalog, health check và tích hợp Spring Cloud. Giá trị của nó nằm ở việc giúp kiểm chứng luồng đăng ký và tra cứu trên một máy. Khi cần dữ liệu bền vững, bảo mật, khả năng chịu lỗi và quy mô thực tế, phải chuyển sang cấu hình Consul cluster được thiết kế và vận hành riêng.
