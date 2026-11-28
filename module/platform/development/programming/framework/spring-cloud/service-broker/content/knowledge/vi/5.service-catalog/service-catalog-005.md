# Khai báo danh mục bằng YAML hoặc properties

Danh mục dịch vụ (service catalog) là phần mô tả những dịch vụ và gói dịch vụ mà một service broker cung cấp cho platform. Khi platform gọi endpoint catalog của Open Service Broker API (OSB API), broker trả về danh sách service, plan và các khả năng mà platform cần biết trước khi người dùng yêu cầu cấp phát tài nguyên.

Với Spring Cloud Open Service Broker, phần giao tiếp OSB được framework hỗ trợ thông qua các abstraction như Catalog và CatalogService. Trong ứng dụng thực tế, thông tin catalog có thể được quản lý bên ngoài mã nguồn bằng YAML hoặc application.properties. Cách làm này giúp đội vận hành thay đổi tên hiển thị, mô tả, plan hoặc khả năng của dịch vụ theo môi trường mà không phải sửa trực tiếp logic xử lý vòng đời.

Cần phân biệt hai việc: Spring Boot có cơ chế đọc YAML/properties và bind dữ liệu vào bean cấu hình; Spring Cloud Open Service Broker cung cấp hợp đồng để ứng dụng trả catalog qua OSB API. Ứng dụng cần nối hai phần đó bằng một CatalogService hoặc adapter tương ứng. Không nên giả định rằng mọi khóa YAML tự đặt đều tự động trở thành catalog nếu chưa có lớp binding và chuyển đổi.

## 1. Vai trò của service catalog

Service catalog là danh sách những dịch vụ mà broker công bố. Mỗi service mô tả một loại dịch vụ có thể được cấp phát, chẳng hạn PostgreSQL, Redis hoặc RabbitMQ. Mỗi service có thể cung cấp một hoặc nhiều plan để biểu diễn các mức tài nguyên, tính năng hoặc chính sách khác nhau.

Ví dụ, broker cung cấp PostgreSQL với hai plan:

- small: cơ sở dữ liệu dành cho môi trường phát triển hoặc thử nghiệm, giới hạn tài nguyên.
- production: cơ sở dữ liệu dành cho ứng dụng production, có dung lượng lớn hơn và chính sách sao lưu phù hợp.

Platform lấy catalog trước khi hiển thị lựa chọn cho người dùng. Khi người dùng chọn một service và plan, platform gửi các định danh tương ứng trong yêu cầu provision. Vì vậy, catalog chính là hợp đồng mô tả những lựa chọn mà broker chấp nhận.

Luồng tổng quát:

~~~mermaid
flowchart TD
    C[YAML hoặc application.properties] --> B[Spring Boot Configuration Binding]
    B --> P[BrokerCatalogProperties]
    P --> A[Catalog Adapter / CatalogService]
    A --> M[OSB Catalog model]
    M --> E[GET /v2/catalog]
    E --> R[Platform nhận danh sách service và plan]
~~~

Trong kiến trúc này, file cấu hình chứa dữ liệu khai báo; bean cấu hình đại diện dữ liệu đó trong ứng dụng; CatalogService chuyển dữ liệu sang mô hình catalog của framework; framework công bố kết quả qua endpoint OSB.

## 2. Cấu trúc dữ liệu catalog

Một catalog OSB thường có cấu trúc cấp cao gồm thuộc tính services. Mỗi phần tử trong mảng services đại diện cho một service definition. Mỗi service definition có danh sách plans.

Ví dụ JSON rút gọn mà endpoint catalog có thể trả về:

~~~json
{
  "services": [
    {
      "id": "a3f7b20d-9f31-4e83-8b8a-8a3e5d7b1001",
      "name": "postgresql",
      "description": "Dịch vụ cơ sở dữ liệu PostgreSQL",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "b4a8c31e-0a42-4f94-9c9b-9b4f6e8c2001",
          "name": "small",
          "description": "Gói nhỏ dành cho phát triển"
        },
        {
          "id": "c5b9d42f-1b53-40a5-adac-ac507f9d3001",
          "name": "production",
          "description": "Gói dành cho môi trường production"
        }
      ]
    }
  ]
}
~~~

Các trường thường gặp:

| Trường | Cấp | Ý nghĩa |
|---|---|---|
| id | Service | Định danh ổn định của service definition |
| name | Service | Tên service hiển thị trong catalog |
| description | Service | Mô tả chức năng của service |
| bindable | Service | Cho biết service có hỗ trợ tạo binding hay không |
| plan_updateable | Service | Cho biết service có hỗ trợ cập nhật plan hay không |
| plans | Service | Danh sách plan mà service cung cấp |
| id | Plan | Định danh ổn định của plan |
| name | Plan | Tên plan |
| description | Plan | Mô tả tài nguyên hoặc đặc tính của plan |

Định danh service và plan có vai trò quan trọng hơn tên hiển thị. Platform sử dụng các ID này trong các request provision, update và deprovision. Vì vậy, ID cần ổn định giữa các lần triển khai. Nếu đổi ID tùy tiện, các service instance đã được tạo có thể tham chiếu đến một định danh không còn được broker nhận diện.

Tên và mô tả có thể được điều chỉnh để dễ hiểu hơn với người dùng, nhưng cần giữ ý nghĩa nhất quán. Tên plan small không nên được dùng cho một cấu hình production lớn nếu điều đó khiến người dùng hiểu sai khả năng dịch vụ.

## 3. Thiết kế cấu hình catalog bằng YAML

YAML phù hợp khi catalog có cấu trúc lồng nhau như service chứa nhiều plan. Danh sách service và plan được biểu diễn trực quan, dễ rà soát và ít phải lặp lại tên thuộc tính.

Ta có thể tạo một namespace cấu hình riêng của ứng dụng, ví dụ broker.catalog. Namespace này là lựa chọn của dự án để quản lý catalog; nó không phải cam kết rằng framework tự động đọc một thuộc tính có tên như vậy.

Ví dụ file application.yml:

~~~yaml
broker:
  catalog:
    services:
      - id: a3f7b20d-9f31-4e83-8b8a-8a3e5d7b1001
        name: postgresql
        description: Dịch vụ cơ sở dữ liệu PostgreSQL
        bindable: true
        plan-updateable: true
        plans:
          - id: b4a8c31e-0a42-4f94-9c9b-9b4f6e8c2001
            name: small
            description: Gói nhỏ dành cho phát triển
          - id: c5b9d42f-1b53-40a5-adac-ac507f9d3001
            name: production
            description: Gói dành cho môi trường production

      - id: d6cae530-2c64-41b6-bebd-bd6180ae4001
        name: redis
        description: Dịch vụ lưu trữ dữ liệu trong bộ nhớ
        bindable: true
        plan-updateable: false
        plans:
          - id: e7dbf641-3d75-42c7-cfce-ce7291bf5001
            name: cache-small
            description: Gói cache dung lượng nhỏ
~~~

YAML dùng dấu gạch ngang để tạo phần tử trong danh sách. Mỗi service có một danh sách plans riêng. Việc lồng danh sách như vậy giúp người quản trị thấy rõ plan thuộc service nào.

Một số quy tắc nên áp dụng:

- Mỗi service có ID duy nhất trong catalog.
- Mỗi plan có ID duy nhất trong phạm vi catalog và được gắn với đúng service.
- Service có bindable bằng false không nên công bố quy trình binding như thể nó được hỗ trợ.
- Chỉ đặt plan-updateable bằng true khi broker thực sự triển khai khả năng chuyển plan cho service đó.
- Không đưa mật khẩu, token, URL nội bộ nhạy cảm hoặc thông tin kết nối của instance vào catalog.
- Giữ ID ổn định giữa development, staging và production nếu các môi trường biểu diễn cùng một service definition.

Catalog mô tả khả năng mà broker công bố, không phải bằng chứng rằng tài nguyên đã tồn tại. Tài nguyên cụ thể chỉ được tạo khi platform gửi yêu cầu provision.

## 4. Khai báo cùng catalog bằng application.properties

Nếu dự án đang dùng application.properties, Spring Boot hỗ trợ biểu diễn danh sách bằng chỉ số trong dấu ngoặc vuông. Ví dụ tương đương với phần PostgreSQL ở trên:

~~~properties
broker.catalog.services[0].id=a3f7b20d-9f31-4e83-8b8a-8a3e5d7b1001
broker.catalog.services[0].name=postgresql
broker.catalog.services[0].description=Dịch vụ cơ sở dữ liệu PostgreSQL
broker.catalog.services[0].bindable=true
broker.catalog.services[0].plan-updateable=true

broker.catalog.services[0].plans[0].id=b4a8c31e-0a42-4f94-9c9b-9b4f6e8c2001
broker.catalog.services[0].plans[0].name=small
broker.catalog.services[0].plans[0].description=Gói nhỏ dành cho phát triển

broker.catalog.services[0].plans[1].id=c5b9d42f-1b53-40a5-adac-ac507f9d3001
broker.catalog.services[0].plans[1].name=production
broker.catalog.services[0].plans[1].description=Gói dành cho môi trường production
~~~

Chỉ số 0 xác định service đầu tiên; plans[0] và plans[1] xác định các plan bên trong service đó. Nếu thêm Redis thành service thứ hai, có thể khai báo ở services[1].

| YAML | application.properties |
|---|---|
| services: phần tử đầu tiên | services[0] |
| plans: phần tử đầu tiên của service | services[0].plans[0] |
| plans: phần tử thứ hai của service | services[0].plans[1] |
| plan-updateable: true | plan-updateable=true |

Properties phù hợp với cấu hình phẳng hoặc môi trường có hệ thống quản lý key-value. Khi danh mục có nhiều service và nhiều plan, số lượng dòng có thể tăng nhanh; YAML thường dễ đọc và rà soát hơn.

Không nên khai báo cùng một catalog ở cả YAML và properties với các giá trị mâu thuẫn. Spring Boot có thứ tự ưu tiên giữa các nguồn cấu hình; nếu hai nguồn cùng định nghĩa một thuộc tính, giá trị cuối cùng phụ thuộc nguồn có độ ưu tiên cao hơn. Hãy quản lý một nguồn chính cho mỗi môi trường.

## 5. Bind cấu hình YAML hoặc properties vào Java

Spring Boot không tự biến cấu trúc broker.catalog thành một đối tượng Catalog của OSB. Cần tạo một lớp cấu hình bằng @ConfigurationProperties để bind dữ liệu vào Java object.

Ví dụ lớp BrokerCatalogProperties:

~~~java
package com.example.broker.catalog;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

@ConfigurationProperties(prefix = "broker.catalog")
@Validated
public class BrokerCatalogProperties {

    @NotEmpty
    @Valid
    private List<ServiceEntry> services = new ArrayList<>();

    public List<ServiceEntry> getServices() {
        return services;
    }

    public void setServices(List<ServiceEntry> services) {
        this.services = services;
    }

    public static class ServiceEntry {

        @NotBlank
        private String id;

        @NotBlank
        private String name;

        @NotBlank
        private String description;

        private boolean bindable;

        private boolean planUpdateable;

        @NotEmpty
        @Valid
        private List<PlanEntry> plans = new ArrayList<>();

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getDescription() {
            return description;
        }

        public void setDescription(String description) {
            this.description = description;
        }

        public boolean isBindable() {
            return bindable;
        }

        public void setBindable(boolean bindable) {
            this.bindable = bindable;
        }

        public boolean isPlanUpdateable() {
            return planUpdateable;
        }

        public void setPlanUpdateable(boolean planUpdateable) {
            this.planUpdateable = planUpdateable;
        }

        public List<PlanEntry> getPlans() {
            return plans;
        }

        public void setPlans(List<PlanEntry> plans) {
            this.plans = plans;
        }
    }

    public static class PlanEntry {

        @NotBlank
        private String id;

        @NotBlank
        private String name;

        @NotBlank
        private String description;

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getDescription() {
            return description;
        }

        public void setDescription(String description) {
            this.description = description;
        }
    }
}
~~~

Lớp trên có ba cấp dữ liệu:

- BrokerCatalogProperties giữ danh sách service.
- ServiceEntry biểu diễn một service definition.
- PlanEntry biểu diễn một plan thuộc service.

Các getter và setter cho phép Spring Boot bind thuộc tính theo JavaBean convention. @ConfigurationProperties xác định prefix cần đọc; @Validated và các annotation validation giúp phát hiện dữ liệu thiếu hoặc rỗng trong lúc khởi tạo ứng dụng.

Ví dụ sử dụng jakarta.validation phù hợp với Spring Boot 3. Với Spring Boot 2, dự án có thể cần namespace javax.validation và phiên bản dependency validation tương ứng. Nếu dùng validation annotation, cần có implementation validation trên classpath, thường được đưa vào qua spring-boot-starter-validation.

### 5.1. Đăng ký lớp cấu hình

Có thể dùng @ConfigurationPropertiesScan ở lớp ứng dụng:

~~~java
package com.example.broker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class BrokerApplication {

    public static void main(String[] args) {
        SpringApplication.run(BrokerApplication.class, args);
    }
}
~~~

Hoặc đăng ký cụ thể bằng @EnableConfigurationProperties:

~~~java
@Configuration
@EnableConfigurationProperties(BrokerCatalogProperties.class)
public class BrokerCatalogConfiguration {
}
~~~

Chọn một cách phù hợp với cấu trúc dự án. Nếu đã dùng configuration properties scanning, không cần đăng ký lặp lại cùng một class bằng nhiều cơ chế.

## 6. Chuyển cấu hình thành mô hình Catalog của framework

Sau khi bind, ứng dụng cần chuyển BrokerCatalogProperties thành các đối tượng Catalog, ServiceDefinition và Plan mà Spring Cloud Open Service Broker sử dụng.

Một CatalogService có thể đọc dữ liệu từ bean cấu hình và tạo catalog:

~~~java
package com.example.broker.catalog;

import java.util.List;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.model.catalog.Plan;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;
import org.springframework.cloud.servicebroker.service.CatalogService;

import reactor.core.publisher.Mono;

@Service
public class ConfiguredCatalogService implements CatalogService {

    private final BrokerCatalogProperties properties;

    public ConfiguredCatalogService(BrokerCatalogProperties properties) {
        this.properties = properties;
    }

    @Override
    public Mono<Catalog> getCatalog() {
        List<ServiceDefinition> definitions = properties.getServices()
                .stream()
                .map(this::toServiceDefinition)
                .collect(Collectors.toList());

        Catalog catalog = Catalog.builder()
                .serviceDefinitions(definitions)
                .build();

        return Mono.just(catalog);
    }

    private ServiceDefinition toServiceDefinition(
            BrokerCatalogProperties.ServiceEntry source) {

        List<Plan> plans = source.getPlans()
                .stream()
                .map(plan -> Plan.builder()
                        .id(plan.getId())
                        .name(plan.getName())
                        .description(plan.getDescription())
                        .build())
                .collect(Collectors.toList());

        return ServiceDefinition.builder()
                .id(source.getId())
                .name(source.getName())
                .description(source.getDescription())
                .bindable(source.isBindable())
                .planUpdateable(source.isPlanUpdateable())
                .plans(plans)
                .build();
    }
}
~~~

Các import và builder method cụ thể cần khớp với phiên bản Spring Cloud Open Service Broker mà dự án sử dụng. Mẫu trên thể hiện cách nối dữ liệu cấu hình với contract CatalogService; khi nâng cấp framework, hãy đối chiếu API model và method của phiên bản đang dùng.

Vai trò của các thành phần:

1. Spring Boot nạp application.yml hoặc application.properties.
2. ConfigurationProperties binder tạo BrokerCatalogProperties.
3. ConfiguredCatalogService đọc dữ liệu cấu hình.
4. Adapter chuyển từng ServiceEntry thành ServiceDefinition và từng PlanEntry thành Plan.
5. CatalogService trả về Catalog trong Mono.
6. Spring Cloud Open Service Broker phục vụ catalog qua endpoint OSB.

Tách bước chuyển đổi thành method riêng giúp dễ kiểm thử và bổ sung trường catalog trong tương lai. Khi cần thêm metadata hoặc tags, có thể mở rộng cấu hình DTO và mapper mà không phải thay đổi cách đọc file của Spring Boot.

## 7. Đồng bộ catalog với các thao tác vòng đời

Một catalog hợp lệ về mặt JSON vẫn có thể gây lỗi vận hành nếu không khớp với các handler provision, update hoặc binding.

Ví dụ, catalog công bố service PostgreSQL có ID A và plan small có ID B. Khi platform gửi provision, request sẽ chứa chính hai ID này. Broker phải nhận diện được chúng và ánh xạ đến đúng logic cấp phát.

Cần giữ nhất quán các mối quan hệ sau:

| Catalog khai báo | Nghiệp vụ broker phải hỗ trợ |
|---|---|
| Service ID | Nhận diện loại backing service cần cấp phát |
| Plan ID | Chọn cấu hình tài nguyên tương ứng |
| bindable = true | Có thể xử lý yêu cầu tạo binding cho service |
| plan-updateable = true | Có thể xử lý cập nhật plan theo hợp đồng |
| Service description | Mô tả đúng chức năng được cung cấp |
| Plan description | Phản ánh đúng giới hạn và đặc tính của plan |

Nếu khai báo bindable bằng true nhưng không có logic binding, platform có thể hiển thị lựa chọn mà broker không thể hoàn thành. Nếu plan-updateable là true nhưng handler update không hỗ trợ chuyển plan, platform có thể cho người dùng thực hiện một thao tác thất bại.

Do đó, mỗi lần thêm hoặc sửa một service hay plan trong file cấu hình cần được xem xét cùng các thao tác vòng đời liên quan. Catalog không phải một danh sách quảng cáo độc lập; nó mô tả năng lực thật của broker.

## 8. Quản lý catalog theo môi trường

Một broker có thể chạy ở development, staging và production. Các môi trường có thể công bố cùng service nhưng khác plan hoặc giới hạn tài nguyên.

Ví dụ, application-dev.yml có thể chỉ công bố plan small, trong khi application-prod.yml công bố thêm plan production:

~~~yaml
# application-dev.yml
broker:
  catalog:
    services:
      - id: a3f7b20d-9f31-4e83-8b8a-8a3e5d7b1001
        name: postgresql
        description: PostgreSQL cho môi trường phát triển
        bindable: true
        plan-updateable: false
        plans:
          - id: b4a8c31e-0a42-4f94-9c9b-9b4f6e8c2001
            name: small
            description: Gói nhỏ dành cho phát triển
~~~

~~~yaml
# application-prod.yml
broker:
  catalog:
    services:
      - id: a3f7b20d-9f31-4e83-8b8a-8a3e5d7b1001
        name: postgresql
        description: PostgreSQL cho môi trường production
        bindable: true
        plan-updateable: true
        plans:
          - id: b4a8c31e-0a42-4f94-9c9b-9b4f6e8c2001
            name: small
            description: Gói nhỏ
          - id: c5b9d42f-1b53-40a5-adac-ac507f9d3001
            name: production
            description: Gói production
~~~

Ví dụ này giữ service ID và ID plan small nhất quán, đồng thời bổ sung một plan production ở môi trường production. Trong thực tế, việc cùng một service ID có catalog khác nhau giữa môi trường cần được quản trị có chủ đích. Platform và người dùng phải biết catalog nào thuộc môi trường nào.

Nếu dùng Spring Profiles, hãy xác định profile đang kích hoạt ở từng deployment. Không nên vô tình chạy profile development trong production khiến platform chỉ nhìn thấy plan thử nghiệm.

Có thể dùng biến môi trường để điều chỉnh thuộc tính cụ thể, nhưng với danh sách nhiều cấp, quản lý toàn bộ catalog bằng YAML profile thường dễ đọc hơn. Một lựa chọn khác là nạp catalog từ nguồn cấu hình tập trung hoặc kho dữ liệu riêng khi cần quản trị động.

## 9. Catalog tĩnh và catalog động

Catalog tĩnh được nạp từ file cấu hình khi ứng dụng khởi động. Đây là lựa chọn phù hợp khi danh sách service và plan ít thay đổi, cần review qua Git và triển khai cùng phiên bản ứng dụng.

Ưu điểm của catalog tĩnh:

- Dễ review thay đổi qua pull request.
- Dễ kiểm soát khác biệt giữa các môi trường.
- Có thể kiểm tra cấu hình trước khi triển khai.
- Ít phụ thuộc vào hệ thống dữ liệu bổ sung trong lúc phục vụ request catalog.

Catalog động được đọc từ database, configuration service hoặc hệ thống quản trị riêng. Cách này phù hợp khi cần bật/tắt plan, quản lý catalog tập trung hoặc thay đổi dữ liệu mà không phát hành lại ứng dụng.

Tuy nhiên, catalog động cần giải quyết thêm:

- Cache để tránh truy vấn nguồn dữ liệu quá nhiều khi platform polling catalog.
- Tính nhất quán khi nhiều replica cùng đọc catalog.
- Kiểm tra dữ liệu trước khi công bố.
- Cách xử lý khi nguồn catalog tạm thời không truy cập được.
- Chính sách tương thích với service instance đang tồn tại khi plan bị ngừng công bố.

Dù tĩnh hay động, ID service và plan đã được sử dụng trong các instance đang tồn tại cần được duy trì hoặc có lộ trình chuyển đổi. Xóa một plan khỏi catalog không đồng nghĩa các instance đã được tạo từ plan đó tự động biến mất. Broker vẫn cần xử lý các request vòng đời của instance hiện có theo chính sách tương thích.

## 10. Kiểm tra catalog qua endpoint OSB

Sau khi ứng dụng khởi động, platform hoặc người vận hành có thể gọi endpoint catalog để xem kết quả đã được chuyển đổi.

Ví dụ:

~~~bash
curl -i \
  -H "X-Broker-API-Version: 2.14" \
  -u broker-user:broker-password \
  http://localhost:8080/v2/catalog
~~~

Request này minh họa endpoint mặc định. Nếu ứng dụng đã tùy chỉnh base path, thay /v2 bằng đường dẫn đang cấu hình. Trong môi trường thực tế, dùng HTTPS và thông tin xác thực được quản lý an toàn.

Response thành công cần có cấu trúc catalog theo OSB API. Ví dụ rút gọn:

~~~json
{
  "services": [
    {
      "id": "a3f7b20d-9f31-4e83-8b8a-8a3e5d7b1001",
      "name": "postgresql",
      "description": "Dịch vụ cơ sở dữ liệu PostgreSQL",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "b4a8c31e-0a42-4f94-9c9b-9b4f6e8c2001",
          "name": "small",
          "description": "Gói nhỏ dành cho phát triển"
        }
      ]
    }
  ]
}
~~~

Có thể kiểm tra:

- Response có danh sách services hay không.
- Mỗi service có ID, name, description và plans hợp lệ.
- ID của service và plan có ổn định, duy nhất và đúng định dạng mà OSB API yêu cầu.
- bindable và plan_updateable có phản ánh đúng handler thực tế.
- Không có trường nhạy cảm hoặc thông tin kết nối của instance trong catalog.
- Catalog trả về đúng nội dung của profile hoặc nguồn cấu hình đang hoạt động.

Không nên chỉ kiểm tra ứng dụng đã khởi động mà kết luận catalog chính xác. Cần đọc response HTTP thực tế và đối chiếu với dữ liệu cấu hình dự kiến.

## 11. Lỗi thường gặp khi khai báo catalog

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Catalog không có service nào | Prefix cấu hình sai hoặc danh sách services rỗng | Kiểm tra broker.catalog.services và nguồn cấu hình đang được nạp |
| Ứng dụng lỗi khi khởi động | Thiếu ID, name, description hoặc plans bắt buộc | Bổ sung dữ liệu và kiểm tra validation |
| Chỉ service đầu tiên xuất hiện | Sai chỉ số danh sách hoặc YAML thụt lề sai | Kiểm tra cấu trúc danh sách và các index trong properties |
| Plan không xuất hiện dưới service | Plan đặt sai cấp thụt lề hoặc mapper không chuyển danh sách | Kiểm tra cấu trúc plans và method chuyển đổi |
| Platform provision báo service không tồn tại | Service ID trong request không khớp ID catalog | Giữ ID ổn định và đối chiếu handler |
| Platform báo plan không tồn tại | Plan ID trong request không được broker nhận diện | Kiểm tra plan ID trong catalog và logic provision/update |
| Platform cho phép bind nhưng broker không xử lý được | bindable khai báo true nhưng handler binding chưa hoàn chỉnh | Đồng bộ catalog với năng lực binding |
| Platform cho phép update plan nhưng thao tác thất bại | plan-updateable khai báo true nhưng broker không hỗ trợ | Chỉ công bố khả năng đã triển khai |
| Môi trường production thấy catalog development | Profile hoặc nguồn cấu hình bị chọn sai | Kiểm tra active profile và biến môi trường |
| Catalog khác nhau giữa các replica | Các instance chạy với cấu hình khác nhau | Đồng bộ cấu hình và rollout nhất quán |

Khi xử lý sự cố, hãy lần theo đường đi của dữ liệu: file YAML/properties, bean cấu hình, mapper, CatalogService, endpoint catalog và response mà platform nhận được. Cách này giúp xác định lỗi nằm ở bước bind, chuyển đổi hay công bố API.

## 12. Bảo mật và quản trị thay đổi

Catalog là dữ liệu mô tả công khai cho platform đã được xác thực. Nó có thể chứa tên dịch vụ, mô tả, plan và metadata, nhưng không nên chứa secret của từng service instance.

Thông tin như username, password, token, JDBC URL chứa credential hoặc địa chỉ quản trị nội bộ cần được cấp theo binding và lưu trữ bằng cơ chế bảo vệ phù hợp. Không dùng catalog làm nơi phát tán thông tin kết nối dùng chung cho mọi consumer.

Mỗi thay đổi catalog cần được đánh giá theo ảnh hưởng tới người dùng và instance hiện hữu:

- Thay đổi description thường chỉ ảnh hưởng nội dung hiển thị.
- Thêm plan mới thường mở rộng lựa chọn cho người dùng.
- Ngừng công bố plan có thể ảnh hưởng các yêu cầu provision mới, nhưng instance hiện hữu vẫn cần được quản lý.
- Thay đổi ID service hoặc plan có thể phá vỡ khả năng nhận diện các instance đã tạo.
- Thay đổi bindable hoặc plan-updateable có thể làm thay đổi thao tác platform cho phép.

Nên review thay đổi catalog như một phần của thay đổi API sản phẩm. Nếu catalog được quản lý bằng Git, pull request nên thể hiện rõ service hoặc plan nào được thêm, sửa hay ngừng công bố, cùng lý do và kế hoạch tương thích.

## 13. Quy trình triển khai một catalog mới

Có thể áp dụng trình tự sau khi bổ sung service hoặc plan:

1. Xác định service cần công bố và các plan mà tổ chức thực sự có thể cung cấp.
2. Tạo ID ổn định cho service và từng plan.
3. Khai báo dữ liệu trong YAML hoặc properties theo namespace cấu hình của ứng dụng.
4. Bind dữ liệu bằng @ConfigurationProperties và bật validation.
5. Chuyển DTO cấu hình thành các đối tượng Catalog, ServiceDefinition và Plan.
6. Cung cấp CatalogService để framework trả catalog qua endpoint OSB.
7. Kiểm tra response catalog và đối chiếu với file cấu hình.
8. Xác nhận các ID được sử dụng nhất quán trong provision, update và các handler liên quan.
9. Kiểm tra catalog trên từng profile và môi trường triển khai.
10. Phát hành thay đổi cùng tài liệu mô tả plan và chính sách tương thích.

## 14. Checklist rà soát

- [ ] Namespace cấu hình catalog đã được chọn và tài liệu hóa.
- [ ] YAML hoặc properties có cấu trúc services và plans đúng.
- [ ] Mỗi service có ID, name, description hợp lệ.
- [ ] Mỗi plan có ID, name, description hợp lệ.
- [ ] ID service và plan ổn định, không bị tái sử dụng cho dịch vụ khác.
- [ ] Cấu hình được bind vào bean bằng @ConfigurationProperties.
- [ ] Lớp cấu hình được đăng ký bằng scan hoặc EnableConfigurationProperties.
- [ ] Validation phát hiện dữ liệu bắt buộc bị thiếu.
- [ ] CatalogService chuyển cấu hình thành đúng mô hình của framework.
- [ ] bindable và plan-updateable khớp với năng lực thực tế.
- [ ] Các handler vòng đời nhận diện đúng service ID và plan ID.
- [ ] Profile và nguồn cấu hình đúng với môi trường đang chạy.
- [ ] Endpoint catalog trả response hợp lệ theo OSB API.
- [ ] Catalog không chứa secret hoặc credential của instance.
- [ ] Có quy trình review và tương thích khi thay đổi hoặc ngừng một plan.

Khai báo catalog bằng YAML hoặc properties giúp tách dữ liệu mô tả service khỏi mã xử lý vòng đời. Spring Boot đảm nhiệm việc bind cấu hình vào bean; CatalogService chuyển bean đó thành mô hình catalog mà Spring Cloud Open Service Broker công bố. Khi thiết kế đúng, platform luôn nhận được danh sách service và plan ổn định, phản ánh chính xác những thao tác mà broker thực sự hỗ trợ.

