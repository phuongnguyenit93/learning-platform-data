# Khai báo requires và các khả năng đặc thù của dịch vụ

## Mục tiêu và bối cảnh

Trong Open Service Broker API (OSB API), catalog mô tả những dịch vụ mà broker cung cấp cho nền tảng. Ngoài tên, mô tả, service plan và khả năng binding, một service definition còn có thể khai báo trường `requires` để cho nền tảng biết dịch vụ cần những khả năng tích hợp đặc thù nào.

Trường này có ý nghĩa khi dịch vụ cần platform hỗ trợ một chức năng vượt ra ngoài việc cấp phát tài nguyên thông thường. Ví dụ, một dịch vụ thu thập log có thể cần nhận luồng syslog từ ứng dụng; một dịch vụ định tuyến có thể cần nhận traffic HTTP được chuyển tiếp; một dịch vụ lưu trữ có thể cần gắn volume vào môi trường chạy ứng dụng.

Bài học tập trung vào việc hiểu và khai báo `requires` trong catalog của module Spring Cloud Service Broker. Bạn sẽ phân biệt trường này với các capability khác của service definition, biết ba giá trị OSB thường dùng, mô hình hóa chúng trong Spring Cloud Open Service Broker và kiểm tra catalog trước khi tích hợp với Cloud Foundry hoặc nền tảng hỗ trợ OSB khác.

Sau bài học, bạn có thể:

- Giải thích mục đích của `requires` và cách platform sử dụng thông tin đó.
- Phân biệt `syslog_drain`, `route_forwarding` và `volume_mount`.
- Khai báo các yêu cầu phù hợp trong ServiceDefinition.
- Phân biệt yêu cầu tích hợp đặc thù với `bindable`, `plan_updateable` và các cờ capability khác.
- Kiểm tra tính nhất quán giữa catalog, luồng binding và khả năng thực tế của platform.

## 1. Trường requires trong OSB API

Một service definition mô tả một sản phẩm dịch vụ mà broker cung cấp. Trong response của endpoint GET /v2/catalog, mỗi service có thể chứa trường `requires` là một mảng chuỗi. Mỗi phần tử chỉ ra một khả năng đặc thù mà dịch vụ yêu cầu platform hỗ trợ.

Ví dụ rút gọn:

~~~json
{
  "services": [
    {
      "id": "service-log-001",
      "name": "application-log-sink",
      "description": "Dich vu tiep nhan log tu ung dung",
      "bindable": true,
      "requires": [
        "syslog_drain"
      ],
      "plans": [
        {
          "id": "plan-standard-001",
          "name": "standard",
          "description": "Goi thu thap log tieu chuan"
        }
      ]
    }
  ]
}
~~~

Trong ví dụ, broker công bố dịch vụ tiếp nhận log và khai báo rằng dịch vụ cần khả năng syslog drain của platform. Platform đọc thông tin này khi xử lý catalog và có thể quyết định liệu có thể cung cấp dịch vụ trong môi trường hiện tại hay cần áp dụng quy trình hỗ trợ, cấp quyền hoặc cảnh báo phù hợp.

`requires` là thông tin mô tả yêu cầu tích hợp ở cấp service definition. Nó không tự cài đặt chức năng cho platform, không cấp quyền thay người dùng và cũng không thay thế logic binding ở broker. Broker phải triển khai hành vi tương ứng ở những endpoint và response liên quan.

### 1.1. Ba giá trị OSB thường gặp

Các giá trị tiêu chuẩn thường được dùng cho `requires` gồm:

| Giá trị | Ý nghĩa | Ví dụ dịch vụ |
|---|---|---|
| `syslog_drain` | Platform hỗ trợ chuyển tiếp log của ứng dụng tới dịch vụ | Log sink, log analytics |
| `route_forwarding` | Platform hỗ trợ chuyển tiếp traffic của route qua dịch vụ | API gateway, reverse proxy, web application firewall |
| `volume_mount` | Platform hỗ trợ gắn volume do dịch vụ cung cấp vào môi trường chạy ứng dụng | Shared file storage, persistent volume service |

Đây là các giá trị có ý nghĩa giao thức. Không nên tự tạo chuỗi tùy ý như `custom_network` hoặc `special_storage` rồi đưa vào `requires` và kỳ vọng mọi platform hiểu được. Nếu cần công bố thông tin riêng của nhà cung cấp, hãy dùng cơ chế metadata phù hợp và tài liệu hóa hợp đồng mở rộng riêng; không biến metadata đó thành một giá trị `requires` giả định là tiêu chuẩn.

### 1.2. requires không phải danh sách phụ thuộc thư viện

Tên trường có thể khiến người mới nhầm `requires` với dependency của ứng dụng Spring hoặc dependency Maven/Gradle. Hai khái niệm này khác nhau:

- Dependency của ứng dụng mô tả thư viện hoặc module cần có để build và chạy broker.
- `requires` mô tả khả năng của platform mà một dịch vụ được công bố cần sử dụng.

Ví dụ, thêm Spring Security vào build không làm service cần `syslog_drain`. Ngược lại, khai báo `syslog_drain` trong catalog không tự thêm một logging agent hoặc cấu hình forwarding cho platform.

## 2. Hiểu từng khả năng đặc thù

### 2.1. syslog_drain

Một dịch vụ khai báo `syslog_drain` cần platform có khả năng chuyển log của ứng dụng đến một đích do dịch vụ cung cấp. Đây là mô hình thường dùng khi broker cung cấp log aggregation, phân tích log, giám sát bảo mật hoặc lưu trữ log tập trung.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Platform as Platform
    participant Broker as Service Broker
    participant Log as Log Service

    Platform->>Broker: GET /v2/catalog
    Broker-->>Platform: Service requires syslog_drain
    Platform->>Broker: PUT service binding
    Broker-->>Platform: syslog_drain_url
    Platform->>App: Thiết lập log drain theo binding
    App->>Platform: Ghi log
    Platform->>Log: Chuyển tiếp syslog
~~~

Trong quá trình bind, broker cần trả thông tin đích nhận log theo response contract mà OSB API và platform hỗ trợ, thường là trường `syslog_drain_url`. Platform sử dụng giá trị đó để thiết lập luồng chuyển tiếp log. Broker hoặc backend dịch vụ phải có khả năng nhận, xác thực và xử lý dữ liệu log.

Ví dụ response bind minh họa:

~~~json
{
  "syslog_drain_url": "syslog-tls://logs.example.internal:6514"
}
~~~

Đây là response rút gọn để minh họa trường dữ liệu; response thực tế có thể chứa thêm `credentials` hoặc trường khác theo hợp đồng. Endpoint nhận log cần được bảo vệ, có chính sách xoay vòng thông tin xác thực nếu dùng token, giới hạn lưu lượng và tránh ghi dữ liệu nhạy cảm vào log của chính broker.

Một số câu hỏi kiến trúc cần trả lời:

- Platform nào sẽ chuyển log và có hỗ trợ syslog drain không?
- Giao thức và định dạng log nào được chấp nhận?
- Endpoint có yêu cầu TLS hay xác thực riêng không?
- Khi unbind, platform có ngừng chuyển log không?
- Broker xử lý thế nào khi log endpoint tạm thời không sẵn sàng?
- Có giới hạn dung lượng, tốc độ và thời gian lưu log theo plan không?

Không khai báo `syslog_drain` chỉ vì dịch vụ có lưu log nội bộ. Yêu cầu này nói về khả năng tích hợp luồng log của platform với dịch vụ được bind.

### 2.2. route_forwarding

Một dịch vụ khai báo `route_forwarding` cần platform hỗ trợ chuyển tiếp traffic của một route qua service. Mô hình này thường dùng cho route service, API gateway, reverse proxy hoặc dịch vụ bảo vệ ứng dụng web.

Ví dụ, một tổ chức muốn mọi request đến `api.example.com` đi qua một dịch vụ kiểm tra chính sách trước khi tới ứng dụng. Platform cần có khả năng gắn route với dịch vụ và chuyển traffic theo cơ chế route service mà platform hỗ trợ.

Luồng khái quát:

~~~mermaid
flowchart LR
    Client[HTTP Client] --> Route[Platform Route]
    Route --> Service[Route Service]
    Service --> Policy[Kiểm tra chính sách]
    Policy --> App[Ứng dụng đích]
    Service -. Cấu hình từ binding .-> Broker[Service Broker]
~~~

Khi bind, broker có thể trả URL của route service trong trường `route_service_url`, nếu giao thức và platform tích hợp hỗ trợ. Platform sử dụng URL này để cấu hình đường đi của traffic.

Ví dụ response bind minh họa:

~~~json
{
  "route_service_url": "https://route-proxy.example.internal"
}
~~~

URL trong response phải trỏ đến endpoint thực sự xử lý traffic và phải được bảo vệ bằng cơ chế xác thực phù hợp. Broker cần xác định service có thể xử lý lưu lượng dự kiến, timeout, health check, TLS, header forwarding và lỗi upstream như thế nào.

Trước khi công bố `route_forwarding`, hãy xác nhận platform hỗ trợ route service hoặc cơ chế tương đương. Chỉ có một reverse proxy trong backend không có nghĩa platform tự biết cách chuyển route qua proxy đó.

### 2.3. volume_mount

Một dịch vụ khai báo `volume_mount` cần platform hỗ trợ gắn volume do dịch vụ cung cấp vào môi trường chạy ứng dụng. Trường hợp sử dụng điển hình là dịch vụ file storage hoặc persistent storage được quản lý bởi broker.

Luồng tổng quát:

1. Nền tảng đọc catalog và nhận biết service cần volume mount.
2. Người dùng tạo service instance theo một plan.
3. Ứng dụng yêu cầu bind instance.
4. Broker chuẩn bị volume hoặc thông tin tham chiếu đến volume và trả mô tả mount theo hợp đồng.
5. Platform kiểm tra khả năng hỗ trợ driver và cấu hình mount, sau đó gắn volume vào workload.
6. Khi unbind, platform tháo mount theo vòng đời và broker thu hồi quyền hoặc tham chiếu binding.

Response binding có thể chứa mảng `volume_mounts`. Một phần tử mô tả driver, thư mục đích, mode, loại thiết bị và cấu hình thiết bị. Ví dụ khái niệm:

~~~json
{
  "volume_mounts": [
    {
      "driver_type": "example.csi.driver",
      "container_dir": "/var/lib/app-data",
      "mode": "rw",
      "device_type": "shared",
      "device": {
        "volume_id": "volume-123"
      }
    }
  ]
}
~~~

Đây là ví dụ minh họa cấu trúc dữ liệu và không thay thế schema của OSB API phiên bản đang dùng. Giá trị driver_type và nội dung device phải phù hợp với driver, platform và backend cụ thể.

Các vấn đề cần thiết kế:

- Volume là riêng cho một instance hay dùng chung giữa nhiều consumer?
- Nhiều workload có được mount đồng thời không?
- Mode read-only hay read-write được áp dụng như thế nào?
- Ai tạo, xóa và xoay vòng thông tin truy cập?
- Khi instance bị deprovision, dữ liệu có bị xóa ngay hay có retention?
- Platform hỗ trợ driver và volume mount trong loại workload đang chạy hay không?

Không khai báo `volume_mount` nếu broker chỉ trả hostname và credentials của một file API. Dùng volume mount khi platform cần thực hiện thao tác mount vào môi trường chạy ứng dụng.

## 3. Khai báo requires trong Spring Cloud Service Broker

Spring Cloud Open Service Broker biểu diễn catalog bằng các model như `Catalog`, `ServiceDefinition` và `Plan`. Broker triển khai `CatalogService` để cung cấp catalog. Trường `requires` được gắn vào service definition, vì vậy cần khai báo ở đúng cấp này.

Ví dụ một service yêu cầu syslog drain và route forwarding:

~~~java
package com.example.broker.catalog;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.model.catalog.Plan;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;
import org.springframework.cloud.servicebroker.service.CatalogService;

import reactor.core.publisher.Mono;

@Service
public class ExtendedCatalogService implements CatalogService {

    private final Catalog catalog;

    public ExtendedCatalogService() {
        Plan standardPlan = Plan.builder()
                .id("plan-edge-standard")
                .name("standard")
                .description("Plan tieu chuan cho route va log")
                .build();

        ServiceDefinition edgeService = ServiceDefinition.builder()
                .id("service-edge-observability")
                .name("edge-observability")
                .description("Dich vu tiep nhan log va xu ly traffic")
                .bindable(true)
                .requires(List.of("syslog_drain", "route_forwarding"))
                .plans(List.of(standardPlan))
                .build();

        this.catalog = Catalog.builder()
                .serviceDefinitions(List.of(edgeService))
                .build();
    }

    @Override
    public Mono<Catalog> getCatalog() {
        return Mono.just(catalog);
    }
}
~~~

Tên package, chữ ký method và kiểu collection cần khớp phiên bản Spring Cloud Open Service Broker mà ứng dụng đang sử dụng. Đoạn code minh họa cách đặt `requires` trên ServiceDefinition; nếu phiên bản thư viện có thay đổi API, hãy dùng đúng model và builder của phiên bản đã khóa trong dependency management.

Có thể khai báo một service khác cần volume mount:

~~~java
ServiceDefinition storageService = ServiceDefinition.builder()
        .id("service-shared-storage")
        .name("shared-storage")
        .description("Dich vu luu tru file duoc mount vao workload")
        .bindable(true)
        .requires(List.of("volume_mount"))
        .plans(List.of(storagePlan))
        .build();
~~~

Không nên đưa cả ba giá trị vào mọi service để minh họa. Chỉ khai báo những khả năng thật sự cần thiết cho sản phẩm đó. Một dịch vụ database thông thường có thể chỉ cần provision và bind credentials, không cần syslog drain, route forwarding hay volume mount.

### 3.1. Chọn requires theo từng service

Một catalog có nhiều service definition có thể khai báo các yêu cầu khác nhau:

~~~java
ServiceDefinition logService = ServiceDefinition.builder()
        .id("service-log-sink")
        .name("log-sink")
        .description("Dich vu nhan log tu ung dung")
        .bindable(true)
        .requires(List.of("syslog_drain"))
        .plans(List.of(logPlan))
        .build();

ServiceDefinition routeService = ServiceDefinition.builder()
        .id("service-route-proxy")
        .name("route-proxy")
        .description("Dich vu xu ly traffic tren route")
        .bindable(true)
        .requires(List.of("route_forwarding"))
        .plans(List.of(routePlan))
        .build();

ServiceDefinition fileService = ServiceDefinition.builder()
        .id("service-volume-storage")
        .name("volume-storage")
        .description("Dich vu cung cap volume cho workload")
        .bindable(true)
        .requires(List.of("volume_mount"))
        .plans(List.of(storagePlan))
        .build();
~~~

Các biến `logPlan`, `routePlan` và `storagePlan` là những Plan đã được tạo trước đó. Trong ứng dụng thực tế, service definition có thể được khởi tạo từ cấu hình hoặc một nguồn catalog có kiểm soát. Dù chọn cách nào, ID và danh sách requires phải ổn định giữa các lần broker khởi động.

### 3.2. Không trộn capability giữa các service

Giả sử broker cung cấp ba dịch vụ:

| Service | requires | Lý do |
|---|---|---|
| Log Sink | `syslog_drain` | Platform chuyển log ứng dụng tới dịch vụ |
| Route Proxy | `route_forwarding` | Platform chuyển traffic route qua dịch vụ |
| Shared Storage | `volume_mount` | Platform mount volume vào workload |

Nếu service definition của Log Sink khai báo thêm `volume_mount` trong khi sản phẩm không cung cấp volume, platform có thể hiểu sai yêu cầu tích hợp. Catalog vì thế phải phản ánh đặc tính của từng sản phẩm, không phải danh sách tổng hợp mọi tính năng mà broker có thể hỗ trợ ở đâu đó.

## 4. Phân biệt requires với các trường capability khác

Một service definition có nhiều trường mô tả hành vi. Chúng có quan hệ nhưng không thay thế nhau.

| Trường | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| `requires` | Platform cần hỗ trợ tích hợp đặc thù nào? | `syslog_drain` |
| `bindable` | Service có hỗ trợ tạo binding không? | `true` |
| `plan_updateable` | Broker có hỗ trợ thay đổi plan cho instance không? | `true` hoặc `false` |
| `instances_retrievable` | Broker có hỗ trợ truy xuất thông tin instance theo capability OSB không? | `true` hoặc `false` |
| `bindings_retrievable` | Broker có hỗ trợ truy xuất thông tin binding theo capability OSB không? | `true` hoặc `false` |
| `allow_context_updates` | Broker có chấp nhận cập nhật context của instance theo capability OSB không? | `true` hoặc `false` |
| `metadata` | Có thông tin bổ sung nào phục vụ giao diện hoặc tích hợp không? | Icon, display name hoặc thông tin riêng |

Ví dụ, `bindable=true` nói rằng service hỗ trợ binding. Nếu service còn cần platform chuyển log, `requires` có thể chứa `syslog_drain`. Hai trường diễn tả hai khía cạnh khác nhau: khả năng bind và yêu cầu tích hợp đặc thù.

Tương tự, `plan_updateable=true` không có nghĩa service yêu cầu route forwarding. Một service có thể cho phép nâng plan mà không dùng bất kỳ tính năng đặc thù nào trong `requires`.

`metadata` cũng không phải nơi thay thế trường `requires`. Metadata thường phục vụ thông tin hiển thị hoặc mở rộng riêng. Nếu một khả năng đã có tên chuẩn trong OSB API, dùng đúng trường chuẩn để platform có thể nhận diện.

## 5. Quan hệ giữa requires và binding response

Catalog công bố khả năng mà service cần; binding response cung cấp dữ liệu để platform thực hiện việc tích hợp cụ thể. Hai phần phải nhất quán.

| requires | Thông tin binding liên quan | Công việc phía platform |
|---|---|---|
| `syslog_drain` | `syslog_drain_url` | Cấu hình chuyển log tới endpoint |
| `route_forwarding` | `route_service_url` | Gắn route với route service |
| `volume_mount` | `volume_mounts` | Chuẩn bị và gắn volume theo driver hỗ trợ |

Các trường response nêu trên là các phần tử chuyên biệt của OSB binding response. Chúng không phải chuỗi được đặt tùy ý trong `credentials`. Platform cần nhận đúng vị trí trường và cấu trúc theo phiên bản API.

Ví dụ, với dịch vụ log sink, broker không thể chỉ khai báo `requires=["syslog_drain"]` rồi trả về một thuộc tính `logUrl` trong credentials và kỳ vọng platform tự hiểu. Broker cần trả trường chuyên biệt theo giao thức mà platform hỗ trợ.

Ngược lại, chỉ trả `syslog_drain_url` cũng chưa đủ nếu platform không biết service yêu cầu syslog drain. Catalog và binding response cần cùng mô tả một luồng tích hợp nhất quán.

## 6. Kiểm tra khả năng tương thích của platform

OSB API tạo ra hợp đồng chung giữa broker và platform, nhưng không có nghĩa mọi platform đều triển khai mọi khả năng đặc thù. Trước khi đưa một giá trị vào `requires`, cần xác minh platform đích hỗ trợ giá trị đó trong phiên bản và loại workload đang dùng.

Một quy trình kiểm tra có thể gồm:

1. Xác định platform và phiên bản mà broker sẽ tích hợp.
2. Kiểm tra tài liệu platform về syslog drain, route service hoặc volume mount.
3. Xác định platform yêu cầu người dùng hoặc quản trị viên cấp quyền bổ sung nào.
4. Kiểm tra luồng bind và response field mà platform chấp nhận.
5. Kiểm tra hành vi khi platform không hỗ trợ tính năng được yêu cầu.
6. Thử nghiệm vòng đời bind/unbind hoặc gắn/tháo volume trên môi trường tích hợp.
7. Chỉ công bố service trong môi trường có khả năng đáp ứng yêu cầu.

Nếu broker được dùng với nhiều platform, catalog có thể phải được cấu hình theo môi trường. Không nên công bố một service có `requires` mà một platform cụ thể không thể đáp ứng. Cách quản lý catalog theo platform phải giữ service ID và plan ID ổn định trong phạm vi mà platform đã lưu các instance.

### 6.1. Tương thích Cloud Foundry

Cloud Foundry có các mô hình tích hợp service broker và service binding cho những khả năng như syslog drain, route service và volume service. Tuy nhiên, khả năng có sẵn phụ thuộc phiên bản Cloud Foundry, cấu hình operator và cách triển khai service cụ thể.

Ví dụ:

- Với `syslog_drain`, xác nhận platform có thể cấu hình log drain từ ứng dụng tới endpoint mà broker trả về.
- Với `route_forwarding`, xác nhận route service và cơ chế gắn route được bật và được quản trị viên cho phép.
- Với `volume_mount`, xác nhận platform hỗ trợ volume service, driver và loại mount cần thiết.

Broker không nên suy luận rằng một khả năng có sẵn chỉ vì platform đã đăng ký broker thành công. Đăng ký broker và đọc catalog là các bước khác với việc platform thực thi một tính năng đặc thù.

### 6.2. Tương thích Kubernetes

Kubernetes cung cấp các primitive như Secret, PersistentVolume, PersistentVolumeClaim, CSI driver, Ingress và Gateway API. Tuy nhiên, các primitive đó không tự động biến một Kubernetes cluster thành một platform OSB hỗ trợ đầy đủ ba giá trị `requires`.

Nếu tích hợp broker với Kubernetes qua controller hoặc adapter riêng, nhóm phát triển cần định nghĩa mapping rõ ràng:

- `syslog_drain`: controller hoặc logging agent nào nhận cấu hình endpoint và chuyển log?
- `route_forwarding`: Ingress/Gateway/controller nào có thể chuyển traffic qua dịch vụ?
- `volume_mount`: CSI driver hoặc cơ chế volume nào đáp ứng cấu trúc mount mà broker trả về?

Mapping này là phần tích hợp riêng giữa controller và broker. Không được tuyên bố Kubernetes hỗ trợ một OSB requirement chỉ dựa trên việc cluster có một resource gần giống về tên gọi.

## 7. Xử lý trường hợp platform không hỗ trợ requires

Nếu service yêu cầu một capability mà platform không có, platform có thể không cho phép người dùng chọn hoặc bind dịch vụ đó. Hành vi cụ thể tùy platform; broker cần dựa trên hợp đồng tích hợp thay vì giả định mọi platform sẽ bỏ qua trường không hiểu.

Một số cách xử lý:

- Không công bố service đó trong catalog dành cho platform không tương thích.
- Dùng cấu hình catalog theo môi trường nếu cùng broker phục vụ nhiều platform.
- Cung cấp một biến thể dịch vụ không cần capability đặc thù nếu backend có thể hỗ trợ hợp lý.
- Tài liệu hóa yêu cầu ở phần mô tả dịch vụ và hướng dẫn onboarding platform.
- Kiểm tra capability trước khi đăng ký hoặc đưa broker vào môi trường dùng chung.

Không nên bỏ trường `requires` chỉ để platform chấp nhận catalog nếu backend thực tế cần khả năng đó. Làm vậy khiến người dùng có thể tạo instance nhưng không thể hoàn tất binding hoặc tích hợp workload.

## 8. Kiểm thử catalog và capability

Kiểm thử cần xác nhận catalog trả đúng các giá trị được cấu hình, không chỉ xác nhận endpoint trả HTTP 200.

### 8.1. Kiểm tra JSON

Sau khi gọi GET /v2/catalog, kiểm tra:

- Service ID và plan ID ổn định.
- `requires` có đúng các giá trị cần thiết.
- Không có giá trị `requires` tự tạo hoặc viết sai chính tả.
- `bindable` phản ánh khả năng binding thật.
- Các service definition không bị gán nhầm requirement của service khác.
- Catalog không trả credentials hoặc dữ liệu bí mật.

Ví dụ một response có hai service với requirements khác nhau:

~~~json
{
  "services": [
    {
      "id": "service-log-sink",
      "name": "log-sink",
      "bindable": true,
      "requires": ["syslog_drain"],
      "plans": [
        {
          "id": "plan-log-standard",
          "name": "standard",
          "description": "Log standard"
        }
      ]
    },
    {
      "id": "service-volume-storage",
      "name": "volume-storage",
      "bindable": true,
      "requires": ["volume_mount"],
      "plans": [
        {
          "id": "plan-volume-shared",
          "name": "shared",
          "description": "Shared volume"
        }
      ]
    }
  ]
}
~~~

### 8.2. Unit test cho CatalogService

Có thể viết unit test để xác nhận service definition chứa đúng yêu cầu:

~~~java
@Test
void catalogContainsExpectedServiceRequirements() {
    ExtendedCatalogService catalogService = new ExtendedCatalogService();

    Catalog catalog = catalogService.getCatalog().block();

    assertThat(catalog).isNotNull();

    ServiceDefinition service = catalog.getServiceDefinitions().stream()
            .filter(item -> item.getId().equals("service-edge-observability"))
            .findFirst()
            .orElseThrow();

    assertThat(service.getRequires())
            .containsExactly("syslog_drain", "route_forwarding");
}
~~~

Đoạn test minh họa cách kiểm tra nội dung catalog. Tên getter và kiểu dữ liệu trả về cần khớp với phiên bản Spring Cloud Open Service Broker được dùng trong project. Nếu `requires` được biểu diễn bằng collection không bảo đảm thứ tự, kiểm tra membership hoặc tập giá trị thay vì phụ thuộc vào thứ tự phần tử.

### 8.3. Integration test với platform

Unit test chỉ xác nhận broker xây dựng catalog đúng. Nó không chứng minh platform có thể thực hiện syslog drain, route forwarding hoặc volume mount.

Integration test cần kiểm tra luồng thật trong platform tương ứng:

- Đăng ký broker và đọc catalog.
- Chọn service và plan.
- Tạo instance nếu service hỗ trợ provision.
- Bind để nhận trường response chuyên biệt.
- Xác nhận platform đã cấu hình tính năng.
- Thử dữ liệu hoặc traffic thực tế đi qua tích hợp.
- Unbind và xác nhận quyền, route hoặc volume được thu hồi theo chính sách.

Với volume mount, cần kiểm tra cả quyền truy cập file, mode read/write và hành vi khi workload được tạo lại. Với route forwarding, cần xác nhận request thực tế đi qua service. Với syslog drain, cần xác nhận log đến được backend và có thể truy vết nguồn gửi.

## 9. Các lỗi khai báo thường gặp

- **Dùng giá trị không chuẩn:** platform không hiểu chuỗi tự tạo trong `requires`.
- **Đặt requires ở cấp plan:** requirement được mô tả ở service definition; không nhầm với tham số hoặc metadata riêng của plan.
- **Khai báo nhưng không triển khai:** catalog nói cần syslog drain nhưng binding không trả endpoint tương ứng.
- **Nhầm requires với bindable:** một trường mô tả platform requirement, trường kia mô tả khả năng binding.
- **Công bố service trên platform không hỗ trợ:** người dùng thấy dịch vụ nhưng không thể hoàn tất tích hợp.
- **Dùng credentials thay trường response chuyên biệt:** platform không diễn giải được dữ liệu binding theo OSB API.
- **Trả URL hoặc volume không thể sử dụng:** platform đã cấu hình nhưng workload không kết nối hoặc mount được.
- **Không thu hồi khi unbind:** quyền, route hoặc volume reference có thể còn tồn tại sau khi consumer ngừng sử dụng.
- **Thay đổi requires tùy tiện:** hành vi tích hợp của service thay đổi nhưng platform và instance hiện tại không được quản lý tương thích.

## 10. Quy trình quyết định trước khi công bố requires

Trước khi đưa service definition vào catalog, hãy trả lời các câu hỏi sau:

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Dịch vụ thực sự cần khả năng đặc thù nào? | Có use case cụ thể cho syslog drain, route forwarding hoặc volume mount |
| Platform đích có hỗ trợ không? | Phiên bản, cấu hình và quyền cần thiết đã được xác minh |
| Binding response có đúng cấu trúc không? | Trả đúng trường chuyên biệt và dữ liệu hợp lệ |
| Backend có thực hiện được không? | Endpoint, route hoặc volume thực sự hoạt động |
| Vòng đời có đầy đủ không? | Bind, unbind và deprovision xử lý nhất quán |
| Có kiểm thử tích hợp không? | Đã kiểm tra với platform thật hoặc môi trường tương thích |

Nếu chưa thể trả lời các câu hỏi trên, chưa nên công bố requirement như một khả năng sẵn sàng sử dụng. Có thể giữ service ở trạng thái chưa phát hành trong cấu hình catalog nội bộ cho đến khi hoàn thiện.

## Kết luận

Trường `requires` trong OSB API cho phép service definition khai báo các khả năng đặc thù mà platform cần hỗ trợ để tích hợp dịch vụ. Ba giá trị thường gặp là `syslog_drain`, `route_forwarding` và `volume_mount`, tương ứng với chuyển tiếp log, chuyển tiếp traffic route và gắn volume vào workload.

Trong Spring Cloud Service Broker, khai báo các yêu cầu này ở ServiceDefinition để chúng xuất hiện trong GET /v2/catalog. Catalog chỉ có ý nghĩa khi nó khớp với binding response, backend và khả năng thực tế của platform. Vì vậy, hãy chọn requirement theo use case, xác minh tương thích Cloud Foundry hoặc adapter Kubernetes, kiểm thử luồng tích hợp và giữ service ID, plan ID cùng capability ổn định trong suốt vòng đời dịch vụ.
