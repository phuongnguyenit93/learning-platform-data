# Tạo Catalog bean bằng Java builder

Catalog là danh mục mà service broker công bố cho nền tảng tiêu thụ dịch vụ. Catalog cho biết broker cung cấp những service nào, mỗi service có các plan nào, service có hỗ trợ binding hay không và một số khả năng khác mà nền tảng cần biết trước khi yêu cầu cấp phát tài nguyên. Trong Spring Cloud Open Service Broker, ứng dụng có thể xây dựng mô hình `Catalog`, `ServiceDefinition` và `Plan` bằng Java builder rồi cung cấp catalog đó qua `CatalogService`.

Với module `SPRING_CLOUD_SERVICE_BROKER`, catalog là hợp đồng công khai giữa broker và nền tảng như Cloud Foundry hoặc một nền tảng tương thích OSB. Catalog cần phản ánh đúng năng lực mà broker thực sự triển khai. Nếu khai báo một plan hoặc capability mà backend không thể thực hiện, nền tảng có thể gửi các thao tác hợp lệ theo catalog nhưng broker lại không xử lý được ở bước provision, update hoặc binding.

## 1. Catalog, service definition và plan

OSB API biểu diễn danh mục theo ba cấp chính:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `Catalog` | Tập hợp các service mà broker công bố | Danh mục của broker quản lý database và object storage |
| `ServiceDefinition` | Một loại dịch vụ có định danh và các capability | PostgreSQL Database, Redis Cache |
| `Plan` | Một cấu hình hoặc cấp dịch vụ cụ thể thuộc service | Basic, Standard, High Availability |

Một service definition thường có các thông tin như `id`, `name`, `description`, `bindable`, `plans`, `tags`, `metadata`, `requires` và những capability liên quan. Mỗi plan có định danh, tên, mô tả, thuộc tính `free` và metadata riêng. Những trường này giúp nền tảng hiển thị lựa chọn cho người dùng và biết các thao tác nào được broker hỗ trợ.

Ví dụ một catalog có thể được tổ chức như sau:

```text
Catalog
└── ServiceDefinition: PostgreSQL Database
    ├── id: 8f2f1f8a-...
    ├── bindable: true
    ├── plans
    │   ├── Plan: basic
    │   └── Plan: high-availability
    └── metadata
        ├── displayName
        └── imageUrl
```

`Catalog` không phải nơi lưu trạng thái của từng instance. Nó mô tả những lựa chọn mà broker có thể cung cấp. Trạng thái instance, binding và operation được quản lý ở các thành phần vòng đời riêng. Khi một người dùng chọn service và plan, nền tảng gửi các ID tương ứng trong request provision; broker dùng những ID ổn định đó để xác định cấu hình cần cấp phát.

## 2. Vì sao dùng Java builder

Builder giúp cấu tạo mô hình lồng nhau mà không phải gọi constructor dài với nhiều tham số. Mỗi đối tượng thể hiện rõ thuộc tính đang cấu hình, và `build()` tạo ra đối tượng hoàn chỉnh để đưa vào catalog.

Một cách tổ chức điển hình là:

1. Tạo từng `Plan` với ID, tên, mô tả và metadata.
2. Gom các plan vào một `ServiceDefinition`.
3. Gom các service definition vào `Catalog`.
4. Đăng ký `Catalog` và `CatalogService` trong Spring application context.

Các class model của Spring Cloud Open Service Broker thường nằm trong package `org.springframework.cloud.servicebroker.model.catalog`; `CatalogService` thuộc nhóm service extension của framework. Tên package và builder API cụ thể cần khớp với phiên bản dependency mà ứng dụng đang sử dụng.

## 3. Xây dựng Plan bằng builder

Plan xác định một lựa chọn cung cấp dịch vụ. Ví dụ, hai plan `basic` và `high-availability` có thể khác nhau về dung lượng, số replica, backup hoặc cam kết khả dụng. Các thông số cấp phát thực tế cần được ánh xạ nhất quán sang provisioning logic.

Ví dụ tạo hai plan:

```java
import org.springframework.cloud.servicebroker.model.catalog.Plan;

import java.util.Map;

public final class BrokerPlans {

    private BrokerPlans() {
    }

    public static Plan basic() {
        return Plan.builder()
                .id("3a1f5d2e-9b42-4f50-a31c-000000000001")
                .name("basic")
                .description("Database dùng cho môi trường phát triển và tải nhỏ")
                .free(true)
                .metadata(Map.of(
                        "displayName", "Basic",
                        "bullets", java.util.List.of(
                                "1 database",
                                "Dung lượng khởi tạo 10 GB")))
                .build();
    }

    public static Plan highAvailability() {
        return Plan.builder()
                .id("3a1f5d2e-9b42-4f50-a31c-000000000002")
                .name("high-availability")
                .description("Database có dự phòng cho tải production")
                .free(false)
                .metadata(Map.of(
                        "displayName", "High Availability",
                        "bullets", java.util.List.of(
                                "Primary và standby",
                                "Backup theo chính sách vận hành")))
                .build();
    }
}
```

Các ID ở ví dụ là ID minh họa. Trong hệ thống thật, ID service và plan phải ổn định qua các lần khởi động, triển khai và nâng cấp. Không tạo UUID ngẫu nhiên mỗi lần gọi catalog, vì nền tảng lưu service/plan ID để tham chiếu trong các thao tác tiếp theo. Đổi tên hiển thị thường ít ảnh hưởng hơn đổi ID; đổi ID có thể làm các instance đã tồn tại không còn khớp với định nghĩa catalog hiện tại.

Thuộc tính `free` mô tả plan có miễn phí theo thông tin catalog hay không. Nó không thay thế cơ chế quota, kiểm soát chi phí hoặc authorization. Một plan được đánh dấu miễn phí vẫn có thể tiêu thụ tài nguyên hạ tầng và broker vẫn cần áp dụng giới hạn phù hợp.

Metadata thường được nền tảng hoặc giao diện người dùng sử dụng để hiển thị thêm thông tin như tên thân thiện, biểu tượng, mô tả ngắn hoặc các gạch đầu dòng. Metadata không nên là nơi duy nhất chứa cấu hình bảo mật, secret hay tham số bắt buộc để provision. Broker phải có cấu hình nghiệp vụ rõ ràng cho từng plan và kiểm tra ID plan khi nhận request.

## 4. Xây dựng ServiceDefinition

`ServiceDefinition` đại diện cho một loại dịch vụ. Nó liên kết một ID service ổn định với danh sách plan và công bố các khả năng như binding hoặc cập nhật plan.

```java
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;

import java.util.List;
import java.util.Map;

public final class BrokerServiceDefinitions {

    private BrokerServiceDefinitions() {
    }

    public static ServiceDefinition postgres() {
        return ServiceDefinition.builder()
                .id("8f2f1f8a-5c7b-4d0a-9f30-000000000001")
                .name("postgresql-database")
                .description("Dịch vụ cơ sở dữ liệu PostgreSQL do broker quản lý")
                .bindable(true)
                .planUpdateable(true)
                .tags(List.of("database", "relational", "postgresql"))
                .metadata(Map.of(
                        "displayName", "PostgreSQL Database",
                        "longDescription", "Cơ sở dữ liệu quan hệ được cấp phát theo plan",
                        "providerDisplayName", "Example Platform Team"))
                .plans(List.of(
                        BrokerPlans.basic(),
                        BrokerPlans.highAvailability()))
                .build();
    }
}
```

Các capability phải phản ánh đúng handler mà broker cung cấp:

| Thuộc tính | Ý nghĩa | Điều cần bảo đảm trong broker |
|---|---|---|
| `bindable` | Service có hỗ trợ tạo binding hay không | Có triển khai luồng bind/unbind và quản lý thông tin binding tương ứng |
| `planUpdateable` | Service cho phép cập nhật plan hay không | Có xử lý update và xác định plan chuyển đổi hợp lệ |
| `instancesRetrievable` | Nền tảng có thể yêu cầu thông tin instance hay không | Có khả năng trả thông tin instance theo hợp đồng được hỗ trợ |
| `bindingsRetrievable` | Nền tảng có thể truy xuất thông tin binding hay không | Có khả năng truy xuất binding tương ứng |
| `requires` | Các capability hoặc yêu cầu môi trường mà service cần | Chỉ công bố yêu cầu mà broker và nền tảng tích hợp thực sự đáp ứng |

Không khai báo `bindable=true` chỉ vì database có username và password. Broker còn phải có quy trình tạo binding, lưu trạng thái binding, cấp thông tin kết nối an toàn và thu hồi quyền khi unbind. Tương tự, `planUpdateable=true` yêu cầu broker thực hiện được cập nhật plan theo chính sách, bao gồm kiểm tra khả năng chuyển đổi và xử lý lỗi.

Tên builder method có thể thay đổi giữa các phiên bản thư viện. Hãy đối chiếu model API của dependency thực tế trước khi sử dụng các capability tùy chọn; không tự thêm thuộc tính mà phiên bản framework hoặc hợp đồng OSB đang triển khai không hỗ trợ.

## 5. Ghép các service definition thành Catalog

Sau khi có các service definition, tạo `Catalog` bằng builder:

```java
import org.springframework.cloud.servicebroker.model.catalog.Catalog;

import java.util.List;

public final class BrokerCatalogFactory {

    private BrokerCatalogFactory() {
    }

    public static Catalog create() {
        return Catalog.builder()
                .serviceDefinitions(List.of(
                        BrokerServiceDefinitions.postgres()))
                .build();
    }
}
```

Catalog ở ví dụ chỉ có một service definition. Khi broker cung cấp thêm Redis, object storage hoặc message queue, có thể thêm các service definition tương ứng vào danh sách. Mỗi service có ID riêng và có danh sách plan của chính nó.

Một nguyên tắc quan trọng là không để hai service dùng chung một ID hoặc hai plan trong cùng service có ID trùng nhau. ID là khóa mà nền tảng dùng để tham chiếu; tên hiển thị không thay thế được ID. Có thể duy trì ID trong cấu hình có version hoặc một vùng định nghĩa catalog tập trung để tránh vô tình tạo ID mới khi đổi tên class hay package.

## 6. Đăng ký Catalog bean và CatalogService trong Spring

Tạo `Catalog` trong một lớp `@Configuration` để Spring quản lý như bean. Sau đó cung cấp `CatalogService` sử dụng bean catalog đó. `CatalogService` là điểm tích hợp mà Spring Cloud Open Service Broker gọi khi nền tảng yêu cầu catalog.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.service.CatalogService;
import reactor.core.publisher.Mono;

@Configuration
public class BrokerCatalogConfiguration {

    @Bean
    public Catalog brokerCatalog() {
        return BrokerCatalogFactory.create();
    }

    @Bean
    public CatalogService catalogService(Catalog brokerCatalog) {
        return () -> Mono.just(brokerCatalog);
    }
}
```

Trong cấu hình này:

- `brokerCatalog()` tạo một catalog và đăng ký nó trong Spring context.
- Spring inject cùng bean đó vào phương thức `catalogService(...)`.
- `CatalogService` trả catalog dưới dạng `Mono<Catalog>`, phù hợp với API reactive của framework.
- Khi framework xử lý endpoint catalog của OSB, nó gọi `CatalogService` và chuyển model thành response giao thức.

Đoạn mã minh họa cách tổ chức bean phổ biến. Nếu phiên bản Spring Cloud Open Service Broker đang dùng yêu cầu một cách triển khai `CatalogService` khác hoặc có sẵn auto-configuration cụ thể, hãy tuân theo API của phiên bản đó. Không đăng ký đồng thời nhiều `CatalogService` không có chủ đích, vì Spring có thể không xác định được bean nào cần dùng hoặc ứng dụng có thể công bố catalog ngoài dự kiến.

Một cách khác là tạo catalog ngay trong `CatalogService`. Tuy nhiên, tách `Catalog` thành bean riêng giúp tái sử dụng trong kiểm thử, kiểm tra cấu hình và các thành phần nội bộ cần đọc catalog. Dù chọn cách nào, cần có một nguồn định nghĩa catalog rõ ràng để tránh nội dung khác nhau giữa catalog endpoint và logic provision.

## 7. Catalog tĩnh và catalog động

Catalog tĩnh phù hợp khi danh sách service và plan thay đổi theo phiên bản triển khai. Ứng dụng tạo catalog một lần khi khởi động rồi trả cùng cấu trúc cho các request catalog. Cách này đơn giản, dễ kiểm thử và tránh việc catalog thay đổi giữa hai lần nền tảng đọc.

Catalog động phù hợp khi broker cần bật/tắt service hoặc plan theo tenant, vùng triển khai, quota hay cấu hình vận hành. Khi đó, `CatalogService` có thể lấy định nghĩa từ repository hoặc một nguồn cấu hình rồi xây dựng `Catalog` tương ứng. Tuy nhiên, cần quản lý tính nhất quán:

- Cùng một tổ hợp platform/tenant phải nhìn thấy một định nghĩa ổn định trong khoảng thời gian đã xác định.
- Không loại bỏ plan đang được instance hiện hữu sử dụng nếu chưa có chính sách tương thích và vòng đời rõ ràng.
- Không truy vấn hệ thống hạ tầng đồng bộ trong mỗi request catalog chỉ để xác định service có tồn tại hay không.
- Dùng cache có thời hạn hoặc snapshot có version nếu nguồn catalog có độ trễ.
- Khi catalog thay đổi, ghi nhận phiên bản hoặc thời điểm cập nhật để hỗ trợ điều tra và tương thích.

Ví dụ khái niệm cho catalog động:

```java
@Bean
CatalogService dynamicCatalogService(CatalogRepository repository,
                                     CatalogMapper mapper) {
    return () -> repository.findEnabledDefinitions()
            .map(mapper::toCatalog);
}
```

Đây là ví dụ minh họa; kiểu trả về của repository và mapper cần được thiết kế theo API thực tế. Nếu repository là blocking, không nên gọi trực tiếp trên event-loop của ứng dụng reactive. Có thể dùng reactive repository hoặc chuyển công việc blocking sang scheduler phù hợp. Cũng cần tránh để mỗi lần đọc catalog tạo một tập ID mới hoặc làm thay đổi plan một cách không dự đoán được.

## 8. Giữ catalog nhất quán với provisioning logic

Catalog chỉ có giá trị khi broker thực hiện được những gì catalog công bố. Nên dùng ID service và plan trong catalog làm khóa tra cứu cho nghiệp vụ provision thay vì viết lại tên plan rải rác ở nhiều nơi.

Ví dụ, định nghĩa plan nội bộ có thể ánh xạ sang cấu hình tài nguyên:

| Plan ID | Cấu hình nội bộ ví dụ | Kết quả mong đợi |
|---|---|---|
| `...0001` | 1 instance, 10 GB, backup cơ bản | Database cho môi trường phát triển hoặc tải nhỏ |
| `...0002` | Primary/standby, backup theo lịch | Database có dự phòng cho production |

Khi nhận provision request, broker cần:

1. Kiểm tra `service_id` có trong catalog hiện hành hoặc catalog snapshot được phép hay không.
2. Tìm `plan_id` trong đúng service definition.
3. Kiểm tra plan còn được phép cấp phát cho tenant, vùng và trạng thái vận hành hiện tại.
4. Chuyển plan ID thành cấu hình nghiệp vụ có kiểu rõ ràng.
5. Gọi application service để cấp phát tài nguyên và lưu lại service ID, plan ID cùng phiên bản định nghĩa cần thiết vào instance state.

Không nên lấy `displayName` hoặc description để quyết định loại tài nguyên. Những trường đó phục vụ hiển thị và có thể thay đổi theo ngôn ngữ. Logic provision phải dựa trên ID ổn định và cấu hình được kiểm soát.

Nếu một plan bị ngừng cung cấp, có thể ẩn plan đó khỏi catalog cho yêu cầu tạo mới nhưng vẫn cần giữ khả năng đọc, cập nhật hoặc thu hồi các instance đã tạo theo plan cũ theo chính sách tương thích. Vì vậy, vòng đời catalog cần tính đến dữ liệu instance đang tồn tại, không chỉ danh sách lựa chọn mới.

## 9. Kiểm tra catalog trước khi công bố

Trước khi broker phục vụ nền tảng, cần xác nhận các bất biến cơ bản của catalog. Có thể viết unit test cho factory hoặc cấu hình bean:

```java
class BrokerCatalogFactoryTest {

    @Test
    void shouldExposePostgresServiceAndItsPlans() {
        Catalog catalog = BrokerCatalogFactory.create();

        assertThat(catalog.getServiceDefinitions())
                .hasSize(1);

        ServiceDefinition service = catalog.getServiceDefinitions().get(0);
        assertThat(service.getId())
                .isEqualTo("8f2f1f8a-5c7b-4d0a-9f30-000000000001");
        assertThat(service.isBindable()).isTrue();
        assertThat(service.getPlans())
                .extracting(Plan::getName)
                .containsExactly("basic", "high-availability");
    }
}
```

Tên accessor trong test cần khớp model của phiên bản thư viện đang dùng. Mục đích của test là khóa các thuộc tính công khai quan trọng: ID ổn định, danh sách service/plan, thứ tự nếu có ý nghĩa và capability được công bố. Ngoài unit test, nên có kiểm thử HTTP qua endpoint catalog để xác nhận framework serialize model thành JSON OSB như mong đợi.

Các kiểm tra nên bao gồm:

- Catalog không rỗng nếu broker được cấu hình phải cung cấp ít nhất một service.
- ID service và ID plan không rỗng, ổn định và không trùng trong phạm vi tương ứng.
- Mỗi service có plan hợp lệ theo yêu cầu triển khai.
- `bindable`, `planUpdateable` và các capability khác khớp với handler thực tế.
- Metadata có kiểu dữ liệu và kích thước hợp lý, không chứa credential hoặc thông tin nội bộ.
- Endpoint catalog không làm lộ cấu hình backend, địa chỉ quản trị hoặc secret.
- Catalog mà endpoint trả về tương thích với service/plan ID mà provisioning logic chấp nhận.

## 10. Lỗi thường gặp khi tạo Catalog bằng builder

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Sinh ID ngẫu nhiên mỗi lần khởi động | Nền tảng nhìn thấy service hoặc plan mới sau mỗi lần deploy | Dùng ID ổn định trong cấu hình |
| Trùng ID giữa các plan | Nền tảng không phân biệt được lựa chọn hoặc broker ánh xạ sai | Kiểm tra tính duy nhất trong catalog test |
| Khai báo `bindable=true` nhưng chưa có binding handler | Nền tảng gửi yêu cầu bind mà broker không hỗ trợ đúng | Chỉ công bố capability đã triển khai |
| Khai báo plan updateable nhưng không xử lý update | Nền tảng có thể yêu cầu chuyển plan nhưng broker không thực hiện được | Đồng bộ catalog với ServiceInstanceService và chính sách update |
| Đưa thông tin bí mật vào metadata | Dữ liệu nhạy cảm bị công bố cho nền tảng hoặc người dùng | Metadata chỉ chứa thông tin hiển thị công khai |
| Dùng tên hiển thị để định tuyến provision | Đổi tên hoặc dịch ngôn ngữ làm thay đổi hành vi | Dùng service ID và plan ID ổn định |
| Catalog động đọc backend blocking trên event-loop | Request catalog làm nghẽn xử lý reactive | Dùng reactive access hoặc scheduler phù hợp và cache |
| Đăng ký nhiều `CatalogService` ngoài ý muốn | Bean không rõ ràng hoặc catalog trả về không nhất quán | Chỉ định một nguồn catalog có chủ đích |

## Kết luận

Tạo Catalog bean bằng Java builder là cách rõ ràng để định nghĩa hợp đồng dịch vụ mà Spring Cloud Open Service Broker công bố cho nền tảng. Hãy xây dựng `Plan` trước, ghép chúng vào `ServiceDefinition`, rồi đưa các service definition vào `Catalog`. Đăng ký catalog và `CatalogService` trong Spring context, giữ ID ổn định và chỉ công bố capability mà broker thực sự hỗ trợ. Khi catalog được đồng bộ với logic provision, update và binding, nền tảng có thể lựa chọn service/plan một cách nhất quán và broker có thể quản lý vòng đời tài nguyên dựa trên cùng một định nghĩa.
