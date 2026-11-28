# Cài đặt CatalogService cho danh mục lấy từ nguồn dữ liệu động

Trong một service broker thực tế, danh mục dịch vụ thường được quản lý từ cơ sở dữ liệu, hệ thống cấu hình hoặc một dịch vụ quản trị nội bộ. Khi đó, broker cần đọc dữ liệu nguồn, chuyển đổi thành mô hình catalog của Open Service Broker API (OSB API) và trả về cho platform thông qua endpoint **GET /v2/catalog**.

Spring Cloud Open Service Broker (SCOSB) cung cấp abstraction **CatalogService** để xử lý phần này. Thay vì gắn cứng danh sách service offering và plan trong mã nguồn, ta có thể triển khai một **CatalogService** tùy chỉnh, truy vấn nguồn dữ liệu tại thời điểm cần thiết, chuyển bản ghi thành **Catalog**, **ServiceDefinition** và **Plan**, rồi trả kết quả theo kiểu reactive của framework.

Bài học tập trung vào cách tổ chức nguồn dữ liệu, cài đặt **CatalogService**, giữ định danh ổn định, xử lý thay đổi danh mục, cache và kiểm thử. Phạm vi thuộc module **SPRING_CLOUD_SERVICE_BROKER**, nơi broker công bố catalog và quản lý các thao tác provision, update, binding và deprovision theo OSB API.

## 1. CatalogService nằm ở đâu trong luồng xử lý?

Platform không đọc trực tiếp database quản lý catalog của broker. Platform gửi HTTP request đến broker. Controller do SCOSB cung cấp tiếp nhận request, gọi **CatalogService**, rồi chuyển kết quả thành response theo OSB API.

~~~mermaid
flowchart LR
    A["Quản trị viên / hệ thống quản lý dịch vụ"] -->|"Cập nhật offering và plan"| D[("Nguồn dữ liệu catalog")]
    D --> R["CatalogRepository"]
    R --> C["CatalogService tùy chỉnh"]
    C --> M["Catalog / ServiceDefinition / Plan"]
    P["Platform"] -->|"GET /v2/catalog"| H["SCOSB Catalog Controller"]
    H --> C
    C --> H
    H -->|"200 OK + JSON catalog"| P
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| Nguồn dữ liệu catalog | Lưu service offering, plan, trạng thái công bố, mô tả và thuộc tính hiển thị |
| Repository hoặc client | Truy vấn database, config store hoặc API quản trị |
| CatalogService | Điều phối truy vấn, chuyển dữ liệu nguồn sang mô hình SCOSB và xử lý trường hợp không tìm thấy |
| SCOSB controller | Nhận request OSB API, gọi service và tạo HTTP response |
| Platform | Đọc catalog, hiển thị các dịch vụ và plan có thể lựa chọn |

**CatalogService** thuộc lớp nghiệp vụ của broker. Nó không tạo database hay cấp credential cho ứng dụng. Nó chỉ mô tả những offering và plan mà broker công bố. Các thao tác provision, update và binding sẽ sử dụng ID service và plan được định nghĩa trong catalog.

## 2. Hiểu hợp đồng CatalogService

Trong Spring Cloud Open Service Broker, interface **org.springframework.cloud.servicebroker.service.CatalogService** cung cấp hai thao tác chính:

| Phương thức | Kết quả | Mục đích |
|---|---|---|
| **getCatalog()** | **Mono<Catalog>** | Trả về toàn bộ danh mục service offering broker công bố |
| **getServiceDefinition(serviceId)** | **Mono<ServiceDefinition>** | Tra cứu một service definition theo ID |

**getCatalog()** được controller sử dụng để xử lý request lấy catalog. Kết quả gồm danh sách service offering và các plan nằm trong từng offering.

**getServiceDefinition(serviceId)** giúp framework và các phần nghiệp vụ tra cứu service definition tương ứng với ID. Nếu ID không tồn tại, implementation nên trả về publisher rỗng bằng cách để kết quả **Mono.empty()**; không nên tạo một service definition giả để làm request tiếp tục.

Các kiểu dữ liệu chính nằm trong package **org.springframework.cloud.servicebroker.model.catalog**:

- **Catalog**: tập hợp các service offering được broker công bố.
- **ServiceDefinition**: mô tả một loại dịch vụ, gồm ID, tên, mô tả, khả năng binding và danh sách plan.
- **Plan**: mô tả một lựa chọn cấu hình của service offering, gồm ID, tên, mô tả và thuộc tính như plan miễn phí hay tính phí.

Các kiểu trả về của SCOSB sử dụng Reactor. Vì vậy, implementation nên trả về **Mono** và **Flux** theo cách phù hợp với nguồn dữ liệu. Với Spring Data R2DBC hoặc reactive client, có thể ghép trực tiếp các publisher. Với JPA hoặc JDBC blocking, cần đưa thao tác blocking ra scheduler phù hợp, không chạy nó trên event loop của WebFlux.

## 3. Chọn nguồn dữ liệu động

Catalog có thể được nạp từ nhiều nguồn khác nhau. Việc chọn nguồn phụ thuộc vào cách tổ chức quản trị dịch vụ:

| Nguồn | Khi phù hợp | Điểm cần lưu ý |
|---|---|---|
| Cơ sở dữ liệu quan hệ | Offering và plan được quản trị qua trang quản trị hoặc quy trình phê duyệt | Cần transaction, truy vấn hiệu quả và cơ chế công bố dữ liệu |
| Reactive database như R2DBC | Broker dùng WebFlux hoặc muốn xử lý I/O không blocking | Repository cần trả về publisher và quản lý connection pool |
| Config store hoặc file cấu hình | Danh mục nhỏ, thay đổi cùng quy trình phát hành | Cần reload có kiểm soát và xác thực cấu hình trước khi áp dụng |
| API của hệ thống quản trị dịch vụ | Catalog do một control plane khác quản lý | Cần timeout, retry có giới hạn, xác thực và cache |
| Registry nội bộ | Nhiều broker hoặc nhóm sản phẩm chia sẻ dữ liệu offering | Cần quản lý phiên bản schema và tính nhất quán |

Ví dụ trong bài sử dụng một repository reactive làm nguồn dữ liệu. Cấu trúc dữ liệu có thể gồm hai nhóm bản ghi:

| Bản ghi | Trường gợi ý | Ý nghĩa |
|---|---|---|
| Service offering | id, name, description, bindable, published | Một loại dịch vụ mà broker có thể cung cấp |
| Service plan | id, service_id, name, description, free, enabled | Một lựa chọn cấu hình thuộc offering |

Ví dụ dữ liệu:

~~~text
service_offering
+----------------+-------------+-------------------------------+----------+-----------+
| id             | name        | description                   | bindable | published |
+----------------+-------------+-------------------------------+----------+-----------+
| svc-postgresql | postgresql  | Managed PostgreSQL database  | true     | true      |
| svc-redis      | redis       | Managed Redis cache           | true     | true      |
+----------------+-------------+-------------------------------+----------+-----------+

service_plan
+----------------+----------------+-----------+------------------------------+-------+---------+
| id             | service_id     | name      | description                  | free  | enabled |
+----------------+----------------+-----------+------------------------------+-------+---------+
| plan-pg-small  | svc-postgresql | small     | Small PostgreSQL instance    | false | true    |
| plan-pg-large  | svc-postgresql | large     | Large PostgreSQL instance    | false | true    |
| plan-rd-basic  | svc-redis      | basic     | Basic Redis cache            | true  | true    |
+----------------+----------------+-----------+------------------------------+-------+---------+
~~~

ID là định danh nghiệp vụ dùng xuyên suốt vòng đời service. Không nên tạo ID từ tên hiển thị theo cách có thể thay đổi khi người quản trị đổi tên offering hoặc plan. Ví dụ, nếu đổi tên hiển thị từ **postgresql** thành **postgres**, ID **svc-postgresql** vẫn cần được giữ nguyên để các service instance đã tồn tại tiếp tục tham chiếu được.

## 4. Tạo mô hình dữ liệu cho repository

Đầu tiên, định nghĩa kiểu dữ liệu nội bộ biểu diễn offering và plan. Đây là mô hình minh họa; dự án có thể thay bằng entity JPA, entity R2DBC hoặc DTO nhận từ API quản trị.

~~~java
import java.util.List;

public record PlanRecord(
        String id,
        String name,
        String description,
        boolean free
) {
}

public record OfferingRecord(
        String id,
        String name,
        String description,
        boolean bindable,
        List<PlanRecord> plans
) {
}
~~~

Repository cung cấp hai cách đọc:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CatalogRepository {

    // Chỉ lấy offering đang được công bố cùng các plan đang bật.
    Flux<OfferingRecord> findPublished();

    // Tra cứu theo ID ổn định, có thể bao gồm offering đã ngừng công bố
    // để hỗ trợ kiểm tra vòng đời của instance cũ.
    Mono<OfferingRecord> findById(String serviceId);
}
~~~

Trong ứng dụng thật, repository có thể ghép offering với danh sách plan bằng join hoặc truy vấn riêng. Cần tránh N+1 query: nếu catalog có nhiều offering, không nên phát sinh thêm một truy vấn cho từng offering mà không có kế hoạch tối ưu. Có thể tải dữ liệu bằng một truy vấn join, batch query theo danh sách service ID hoặc dùng projection đã tổng hợp.

**findPublished()** lọc dữ liệu dùng để công bố ra platform. Chỉ offering được phê duyệt và plan còn hiệu lực mới xuất hiện trong catalog. **findById()** phục vụ tra cứu một service definition theo ID; tùy chính sách vòng đời, nguồn dữ liệu có thể vẫn giữ các offering đã ngừng công bố để broker xử lý những instance cũ.

## 5. Cài đặt CatalogService tùy chỉnh

Khi catalog được lưu trong nguồn dữ liệu động, triển khai một Spring bean thực hiện interface **CatalogService**. Ví dụ dưới đây dùng reactive repository để không chặn luồng xử lý.

~~~java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.model.catalog.Plan;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;
import org.springframework.cloud.servicebroker.service.CatalogService;

import reactor.core.publisher.Mono;

@Service
public class DynamicCatalogService implements CatalogService {

    private final CatalogRepository repository;

    public DynamicCatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<Catalog> getCatalog() {
        return repository.findPublished()
                .map(this::toServiceDefinition)
                .collectList()
                .map(definitions -> Catalog.builder()
                        .serviceDefinitions(definitions)
                        .build());
    }

    @Override
    public Mono<ServiceDefinition> getServiceDefinition(String serviceId) {
        return repository.findById(serviceId)
                .map(this::toServiceDefinition);
    }

    private ServiceDefinition toServiceDefinition(OfferingRecord offering) {
        List<Plan> plans = offering.plans().stream()
                .map(plan -> Plan.builder()
                        .id(plan.id())
                        .name(plan.name())
                        .description(plan.description())
                        .free(plan.free())
                        .build())
                .toList();

        return ServiceDefinition.builder()
                .id(offering.id())
                .name(offering.name())
                .description(offering.description())
                .bindable(offering.bindable())
                .plans(plans)
                .build();
    }
}
~~~

Phân tích implementation:

1. **Constructor injection:** repository được Spring inject vào service. Nhờ đó, phần chuyển đổi catalog có thể được kiểm thử độc lập bằng repository giả hoặc mock.
2. **Đọc dữ liệu công bố:** **findPublished()** chỉ trả các offering đang được phép xuất hiện trên platform.
3. **Chuyển đổi từng offering:** **map(this::toServiceDefinition)** chuyển từng bản ghi nguồn thành **ServiceDefinition**.
4. **Thu thập danh sách:** **collectList()** gom các service definition thành danh sách hoàn chỉnh cho một response catalog.
5. **Tạo Catalog:** **Catalog.builder()** tạo đối tượng response mà controller của SCOSB sẽ serialize thành JSON.
6. **Tra cứu theo ID:** **getServiceDefinition()** dùng cùng hàm chuyển đổi để dữ liệu tra cứu có cùng cấu trúc với dữ liệu trong catalog.

Điểm quan trọng là cả hai phương thức sử dụng cùng quy tắc chuyển đổi. Nếu **getCatalog()** công bố một service definition nhưng **getServiceDefinition()** lại tạo ra plan hoặc thuộc tính khác, platform có thể nhìn thấy một cấu hình trong catalog nhưng broker lại xử lý request theo cấu hình khác.

Trong dự án dùng một catalog tĩnh, có thể cung cấp một bean **Catalog** và dùng **BeanCatalogService** để bọc catalog đó. Khi cần dữ liệu động từ repository hoặc API, dùng implementation riêng như ví dụ trên. Tránh đăng ký nhiều bean **CatalogService** cạnh tranh nhau; hãy xác định rõ bean nào là nguồn xử lý catalog được controller sử dụng.

## 6. Đọc catalog từ nguồn dữ liệu blocking

Không phải hệ thống nào cũng dùng reactive database. Nếu nguồn dữ liệu hiện tại là JPA/JDBC hoặc SDK blocking, vẫn có thể cung cấp **Mono<Catalog>**, nhưng phải trì hoãn thao tác đọc và đưa nó sang scheduler dành cho blocking I/O.

Ví dụ adapter cho repository blocking:

~~~java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;
import org.springframework.cloud.servicebroker.service.CatalogService;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class BlockingCatalogAdapter implements CatalogService {

    private final BlockingCatalogRepository repository;
    private final CatalogMapper mapper;

    public BlockingCatalogAdapter(
            BlockingCatalogRepository repository,
            CatalogMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public Mono<Catalog> getCatalog() {
        return Mono.fromCallable(repository::findPublished)
                .subscribeOn(Schedulers.boundedElastic())
                .map(mapper::toCatalog);
    }

    @Override
    public Mono<ServiceDefinition> getServiceDefinition(String serviceId) {
        return Mono.fromCallable(() -> repository.findById(serviceId))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(Mono::justOrEmpty)
                .map(mapper::toServiceDefinition);
    }
}
~~~

Trong ví dụ này, **Mono.fromCallable()** trì hoãn lời gọi repository cho đến khi có subscription. **subscribeOn(Schedulers.boundedElastic())** đưa công việc blocking sang scheduler phù hợp. **flatMap(Mono::justOrEmpty)** chuyển kết quả có thể null thành publisher rỗng khi không tìm thấy ID.

Không dùng **Mono.just(repository.findPublished())** cho một lời gọi blocking. Biểu thức repository được thực thi ngay khi tạo Mono, vì vậy công việc blocking vẫn xảy ra trên thread gọi phương thức. Cũng không nên dùng **Schedulers.parallel()** cho JDBC/JPA blocking.

Nếu có thể lựa chọn công nghệ lưu trữ mới cho broker WebFlux, reactive repository thường giúp luồng xử lý nhất quán hơn. Tuy nhiên, không cần chuyển toàn bộ hệ thống sang reactive chỉ để xây dựng catalog; adapter blocking có giới hạn rõ ràng vẫn là một giải pháp hợp lệ.

## 7. Catalog được trả về cho platform

Khi platform gọi **GET /v2/catalog**, controller của SCOSB gọi **CatalogService.getCatalog()** và serialize kết quả thành JSON theo OSB API.

Ví dụ response rút gọn từ dữ liệu ở phần trước:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plans": [
        {
          "id": "plan-pg-small",
          "name": "small",
          "description": "Small PostgreSQL instance",
          "free": false
        },
        {
          "id": "plan-pg-large",
          "name": "large",
          "description": "Large PostgreSQL instance",
          "free": false
        }
      ]
    },
    {
      "id": "svc-redis",
      "name": "redis",
      "description": "Managed Redis cache",
      "bindable": true,
      "plans": [
        {
          "id": "plan-rd-basic",
          "name": "basic",
          "description": "Basic Redis cache",
          "free": true
        }
      ]
    }
  ]
}
~~~

Một số thuộc tính cần được hiểu đúng:

- **id** là định danh ổn định mà platform dùng để tham chiếu offering trong những request sau.
- **name** là tên thân thiện cho CLI hoặc giao diện marketplace. Không dùng tên này làm khóa thay cho ID.
- **bindable** cho biết service có hỗ trợ binding hay không. Chỉ công bố **true** khi broker thực sự triển khai luồng bind và unbind tương ứng.
- **plans** là các lựa chọn thuộc offering. Mỗi plan có ID ổn định và mô tả cấu hình mà broker có thể cấp phát.
- **free** cho biết plan có tính phí hay không theo metadata catalog; trường này không thay thế hệ thống tính giá hoặc kiểm soát quota của broker.

Catalog là dữ liệu công khai cho platform và người dùng có quyền xem marketplace. Không đặt password, token, khóa API, endpoint quản trị nội bộ hoặc thông tin bí mật của provider vào **description**, **metadata**, tên plan hay các trường catalog khác.

## 8. Xử lý thay đổi danh mục theo thời gian

Ưu điểm của catalog động là quản trị viên có thể thêm offering, bật/tắt plan hoặc cập nhật mô tả mà không cần build lại broker. Tuy nhiên, thay đổi catalog phải được quản lý như thay đổi hợp đồng mà platform và broker cùng sử dụng.

### Thêm service offering hoặc plan

Quy trình công bố có thể gồm:

1. Quản trị viên tạo offering và một hoặc nhiều plan trong hệ thống quản lý.
2. Hệ thống kiểm tra ID không trùng, tên hợp lệ, plan thuộc đúng offering và các thuộc tính bắt buộc đã có.
3. Offering được chuyển sang trạng thái **published** sau khi được phê duyệt.
4. **getCatalog()** đọc snapshot mới và đưa offering vào response.
5. Platform truy vấn lại catalog theo lịch hoặc quy trình đồng bộ của nó, sau đó hiển thị service và plan mới.

### Ngừng công bố một plan hoặc offering

Khi plan không còn được cung cấp cho instance mới, có thể đặt **enabled=false** để loại plan khỏi catalog. Khi offering ngừng nhận provision mới, đặt **published=false** để không tiếp tục quảng bá offering.

Không nên xóa vật lý ngay các bản ghi đang được service instance cũ tham chiếu. Một instance có thể được tạo từ plan đã ngừng công bố và vẫn cần được fetch, update theo chính sách hoặc deprovision. Hãy giữ lịch sử ID và thông tin plan cần thiết để xử lý vòng đời của tài nguyên đã tồn tại. Phần nghiệp vụ provision phải kiểm tra trạng thái công bố để từ chối yêu cầu tạo mới từ offering đã ngừng nhận đăng ký.

### Cập nhật mô tả và cấu hình plan

Có thể cập nhật các trường hiển thị như description hoặc metadata, nhưng cần cân nhắc tác động đến platform đang cache catalog. Không đổi ID chỉ vì đổi tên hiển thị. Nếu thay đổi mang ý nghĩa cấu hình không tương thích, hãy cân nhắc tạo plan ID mới và ngừng công bố plan cũ theo một lộ trình có thời hạn.

Theo OSB API, platform có thể truy vấn catalog định kỳ. Khi so sánh các phiên bản catalog, platform phải dùng ID của service offering và service plan để nhận diện tài nguyên; các trường mô tả và tên có thể thay đổi. Vì vậy, ID cần ổn định qua các lần công bố. [Open Service Broker API Specification — Catalog Management](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md).

## 9. Cache catalog và tính nhất quán

Truy vấn database hoặc API quản trị ở mỗi request có thể làm tăng độ trễ của **GET /v2/catalog**. Catalog thường thay đổi ít hơn tần suất platform đọc nó, vì vậy có thể cache một snapshot đã xác thực.

Một chiến lược thường dùng:

~~~mermaid
flowchart TD
    A["Nguồn dữ liệu catalog"] --> B["Tải dữ liệu và kiểm tra"]
    B --> C{"Snapshot hợp lệ?"}
    C -->|"Có"| D["Tạo Catalog snapshot mới"]
    D --> E["Thay snapshot đang phục vụ một cách nguyên tử"]
    C -->|"Không"| F["Ghi nhận lỗi, giữ snapshot tốt gần nhất theo chính sách"]
    P["GET /v2/catalog"] --> G["CatalogService"]
    G --> H["Đọc snapshot hiện hành"]
    E --> H
    F --> H
    H --> R["Response catalog"]
~~~

Có thể triển khai cache bằng Caffeine, một cache phân tán hoặc một snapshot trong bộ nhớ được cập nhật từ event quản trị. Dù dùng công cụ nào, cần xác định rõ:

- **TTL hoặc chu kỳ refresh:** catalog được làm mới sau bao lâu.
- **Invalidation:** sự kiện nào làm cache mất hiệu lực khi offering hoặc plan thay đổi.
- **Snapshot nguyên tử:** request đang chạy chỉ nhìn thấy một phiên bản catalog hoàn chỉnh, không thấy nửa dữ liệu cũ và nửa dữ liệu mới.
- **Last known good:** khi nguồn dữ liệu tạm lỗi, có được phép tiếp tục trả snapshot tốt gần nhất hay phải báo lỗi.
- **Observability:** ghi nhận thời điểm refresh thành công gần nhất, tuổi snapshot, số offering/plan và số lần refresh lỗi.

Không nên biến lỗi nguồn dữ liệu thành catalog rỗng. Một response rỗng có thể khiến platform hiểu rằng broker đã chủ động rút toàn bộ offering. Nếu nguồn dữ liệu không truy cập được, hãy áp dụng chính sách rõ ràng: trả snapshot hợp lệ gần nhất nếu vẫn còn trong giới hạn stale cho phép, hoặc trả lỗi server phù hợp để platform thử lại. Ghi log và metric để đội vận hành nhận biết catalog đang cũ.

## 10. Bảo đảm catalog nhất quán với provision và plan

Catalog không chỉ là dữ liệu hiển thị. Platform dùng ID trong catalog để gửi request provision, update và binding. Vì vậy, broker cần bảo đảm dữ liệu mà **CatalogService** công bố phù hợp với các service xử lý vòng đời.

Một số nguyên tắc:

- ID service và plan phải ổn định, không tái sử dụng ID cũ cho một sản phẩm có ý nghĩa khác.
- Mỗi plan phải thuộc đúng service offering; repository không được ghép plan nhầm service.
- Offering công bố **bindable=true** phải có implementation binding tương ứng.
- Chỉ công bố plan mà broker có khả năng thực hiện provision theo cấu hình đã mô tả.
- Khi ngừng công bố, giữ dữ liệu lịch sử cần thiết để nhận diện các instance đã được tạo trước đó.
- Phần provision phải kiểm tra lại trạng thái offering/plan ở thời điểm thực thi; không chỉ tin vào catalog mà platform đã cache.
- Nếu cấu hình plan thay đổi, xác định rõ thay đổi áp dụng cho instance mới hay cả instance đang tồn tại.

Ví dụ: plan **plan-pg-small** có giới hạn 20 GB tại thời điểm provision. Nếu quản trị viên thay đổi mô tả plan thành 50 GB nhưng không thay ID, broker cần quyết định chính sách nâng cấp. Nếu 50 GB chỉ áp dụng cho instance mới, dữ liệu instance cũ phải lưu cấu hình thực tế đã cấp. Nếu thay đổi làm thay đổi ý nghĩa hoặc chi phí của plan, tạo ID mới thường giúp platform và broker tránh hiểu nhầm.

## 11. Kiểm thử CatalogService

Có thể kiểm thử service độc lập bằng mock repository và Reactor Test. Các ca quan trọng gồm catalog có dữ liệu, catalog rỗng, service ID không tồn tại, offering bị ẩn và nguồn dữ liệu phát sinh lỗi.

Ví dụ kiểm thử bằng JUnit và StepVerifier:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class DynamicCatalogServiceTest {

    private final CatalogRepository repository =
            Mockito.mock(CatalogRepository.class);

    private final DynamicCatalogService service =
            new DynamicCatalogService(repository);

    @Test
    void shouldReturnOnlyPublishedOfferings() {
        OfferingRecord offering = new OfferingRecord(
                "svc-postgresql",
                "postgresql",
                "Managed PostgreSQL database",
                true,
                List.of(new PlanRecord(
                        "plan-pg-small",
                        "small",
                        "Small PostgreSQL instance",
                        false))
        );

        when(repository.findPublished()).thenReturn(Flux.just(offering));

        StepVerifier.create(service.getCatalog())
                .assertNext(catalog -> {
                    assertThat(catalog.getServiceDefinitions()).hasSize(1);
                    assertThat(catalog.getServiceDefinitions().get(0).getId())
                            .isEqualTo("svc-postgresql");
                    assertThat(catalog.getServiceDefinitions().get(0).getPlans())
                            .hasSize(1);
                })
                .verifyComplete();
    }

    @Test
    void shouldReturnEmptyWhenServiceIdDoesNotExist() {
        when(repository.findById("unknown-service")).thenReturn(Mono.empty());

        StepVerifier.create(service.getServiceDefinition("unknown-service"))
                .verifyComplete();
    }
}
~~~

Các test trên kiểm tra mapping cơ bản và trường hợp không tìm thấy service. Trong dự án thực, nên bổ sung:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Không có offering được công bố | Catalog hợp lệ với danh sách services rỗng |
| Offering có nhiều plan | Tất cả plan hợp lệ xuất hiện đúng offering |
| Plan đã tắt | Không xuất hiện trong catalog công bố |
| ID offering trùng | Dữ liệu bị từ chối khi publish hoặc validation báo lỗi |
| Plan tham chiếu service không tồn tại | Không publish snapshot sai |
| Nguồn dữ liệu timeout | Lỗi được ghi nhận; áp dụng chính sách cache đã định |
| Offering đã ngừng công bố nhưng còn instance | Catalog không quảng bá mới; vòng đời instance cũ vẫn tra cứu được |
| Catalog thay đổi trong lúc request | Mỗi response nhận một snapshot nhất quán |

Ngoài unit test, nên kiểm thử HTTP integration qua **GET /v2/catalog** để xác minh controller SCOSB serialize đúng response, header API version được kiểm tra và lỗi nguồn dữ liệu được ánh xạ phù hợp. Một contract test với platform hoặc bộ test OSB API giúp phát hiện khác biệt giữa catalog và hành vi provision thật.

## 12. Lỗi thường gặp khi triển khai catalog động

**Catalog thay đổi ID khi đổi tên.** Platform có thể xem offering cũ và mới là hai dịch vụ khác nhau. Giữ ID ổn định và chỉ cập nhật trường tên/mô tả khi phù hợp.

**Chỉ lọc dữ liệu trong getCatalog() nhưng tra cứu ID từ một nguồn khác.** Hai phương thức có thể trả cấu hình không đồng nhất. Dùng chung quy tắc mapping và nguồn dữ liệu có thẩm quyền.

**Dùng blocking repository trên WebFlux event loop.** Điều này có thể làm giảm throughput và gây nghẽn request. Dùng reactive repository hoặc offload blocking I/O bằng bounded elastic scheduler.

**Trả catalog rỗng khi database lỗi.** Platform có thể hiểu nhầm broker không còn cung cấp dịch vụ nào. Trả snapshot tốt gần nhất theo chính sách hoặc báo lỗi server có kiểm soát.

**Xóa plan ngay khi ngừng công bố.** Instance đã provision có thể vẫn cần dữ liệu plan để fetch, update hoặc deprovision. Dùng trạng thái retired/disabled và lưu lịch sử cần thiết.

**Đặt credential trong metadata.** Catalog có thể được platform cache và hiển thị cho nhiều người dùng. Chỉ đưa thông tin mô tả không nhạy cảm vào catalog; credential chỉ được cấp qua luồng binding có kiểm soát.

**Không kiểm tra dữ liệu trước khi publish.** ID trùng, plan mồ côi hoặc offering bindable nhưng chưa hỗ trợ binding có thể khiến platform nhận catalog không thể sử dụng. Validation cần chạy trước khi thay snapshot hiện hành.

## Kết luận

Để cài đặt **CatalogService** với nguồn dữ liệu động, hãy tách nguồn dữ liệu, repository, lớp chuyển đổi mô hình và interface SCOSB. **getCatalog()** tải các offering được công bố và chuyển thành **Catalog**; **getServiceDefinition()** tra cứu theo ID ổn định để các thao tác vòng đời sử dụng cùng định nghĩa. Khi dữ liệu thay đổi, quản lý trạng thái công bố, giữ lịch sử cho instance cũ, cache snapshot nhất quán và xác minh catalog bằng unit test cùng HTTP contract test. Nhờ vậy, broker có thể cập nhật danh mục theo dữ liệu quản trị mà vẫn giữ hợp đồng ổn định với platform.

## Tài liệu tham khảo

- [Spring Cloud Open Service Broker — Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/)
- [Spring Cloud Open Service Broker — CatalogService API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/service/CatalogService.html)
- [Spring Cloud Open Service Broker — BeanCatalogService API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/service/BeanCatalogService.html)
- [Spring Cloud Open Service Broker — Catalog model API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/model/catalog/Catalog.html)
- [Spring Cloud Open Service Broker — ServiceDefinition model API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/model/catalog/ServiceDefinition.html)
- [Open Service Broker API Specification — Catalog Management](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md)

