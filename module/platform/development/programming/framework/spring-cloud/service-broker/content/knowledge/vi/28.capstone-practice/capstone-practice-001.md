# Xây dựng broker tối thiểu với catalog tĩnh và nhà cung cấp mô phỏng

Trong capstone này, bạn sẽ xây dựng một service broker nhỏ bằng Spring Boot và Spring Cloud Open Service Broker. Broker công bố một dịch vụ PostgreSQL giả lập cùng một service plan tĩnh, nhận yêu cầu tạo service instance, tạo binding chứa credentials, thu hồi binding và deprovision instance. Một lớp provider mô phỏng giữ dữ liệu trong bộ nhớ để bạn quan sát đầy đủ luồng OSB mà chưa cần cài database hoặc kết nối cloud provider thật.

Bài thực hành tập trung vào cách các thành phần phối hợp: catalog mô tả dịch vụ mà platform có thể chọn; ServiceInstanceService quản lý instance; ServiceInstanceBindingService cấp và thu hồi credentials; provider adapter mô phỏng side effect; Spring Security bảo vệ endpoint; và test xác nhận response cùng tính idempotent. Các thao tác trong bài chạy đồng bộ để dễ theo dõi. Khi đã hiểu luồng cơ bản, bạn có thể mở rộng sang database bền vững, asynchronous operation, worker và provider thật.

Kết quả cuối cùng là một ứng dụng có endpoint /v2/catalog và các endpoint lifecycle theo Open Service Broker API (OSB API). Bạn có thể gọi chúng bằng curl, quan sát HTTP status, kiểm tra request lặp và xác nhận tài nguyên giả lập được dọn khi xóa.

## 1. Mục tiêu và phạm vi capstone

Sau khi hoàn thành, bạn có thể:

- Khởi tạo một Spring Boot application có Spring Cloud Open Service Broker.
- Công bố một catalog tĩnh gồm service definition và service plan.
- Triển khai provision và deprovision service instance.
- Triển khai create binding và delete binding cho application consumer.
- Tạo credentials giả lập và trả chúng trong binding response.
- Lưu trạng thái instance/binding trong một provider mô phỏng.
- Xử lý request lặp theo nguyên tắc idempotency.
- Ánh xạ xung đột tài nguyên sang exception OSB phù hợp.
- Bảo vệ /v2/** bằng HTTP Basic cho môi trường thực hành.
- Kiểm tra catalog và toàn bộ vòng đời bằng HTTP request.

Capstone chỉ triển khai các thao tác được catalog công bố. Catalog không bật plan update, instance retrieval hoặc binding retrieval, vì vậy ứng dụng chưa cần triển khai các method tương ứng. Provision, deprovision, bind và unbind đều chạy đồng bộ; không có last_operation trong phiên bản đầu tiên.

### Mô hình dịch vụ giả lập

| Thành phần | Giá trị |
|---|---|
| Service ID | mock-postgres |
| Service name | mock-postgres |
| Plan ID | sandbox |
| Plan name | sandbox |
| Service có thể bind | Có |
| Provider | MockDatabaseProvider |
| Instance state | Map trong bộ nhớ |
| Binding credentials | URI, username và password giả lập |
| Async operation | Chưa bật |
| Persistence | Chỉ tồn tại trong vòng đời process |

Provider không tạo database PostgreSQL thật. URI dùng hostname thuộc miền .invalid, nên credentials trong ví dụ không thể kết nối đến một hệ thống thật. Không dùng mã này để cấp credentials production.

## 2. Kiến trúc và luồng xử lý

Spring Cloud Open Service Broker cung cấp HTTP controller, model và auto-configuration cho OSB API. Bạn tập trung viết các Spring bean triển khai catalog và service interfaces.

~~~mermaid
flowchart TD
    Platform["Platform / curl client"] -->|"GET /v2/catalog"| Catalog["Catalog bean"]
    Platform -->|"PUT /service_instances/{id}"| InstanceService["MockServiceInstanceService"]
    Platform -->|"PUT /service_bindings/{id}"| BindingService["MockServiceInstanceBindingService"]
    Platform -->|"DELETE binding / instance"| BindingService
    InstanceService --> Provider["MockDatabaseProvider"]
    BindingService --> Provider
    Provider --> Instances[("In-memory instances")]
    Provider --> Bindings[("In-memory bindings")]
~~~

Luồng provision:

1. Platform gửi PUT /v2/service_instances/{instance_id} cùng service_id, plan_id và parameters.
2. Spring Cloud Open Service Broker kiểm tra request và resolve service/plan từ catalog.
3. MockServiceInstanceService gọi MockDatabaseProvider.provision().
4. Provider tạo database reference giả lập hoặc nhận diện request đã được thực hiện.
5. Broker trả response đồng bộ.

Luồng binding:

1. Platform gửi PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}.
2. Binding service kiểm tra instance và app GUID.
3. Provider tạo username/password giả lập và lưu theo cặp instance/binding.
4. Broker trả credentials cho platform.
5. Khi unbind, provider xóa đúng credentials của binding đó.

Luồng deprovision:

1. Platform gỡ các binding đang sử dụng.
2. Platform gửi DELETE /v2/service_instances/{instance_id}.
3. Provider xóa instance và dọn binding còn sót của instance đó.
4. Broker trả kết quả hoàn tất.

## 3. Chọn phiên bản và tạo project

Ví dụ dưới đây dùng Java 17, Spring Boot 4.1.2 và Spring Cloud Open Service Broker 5.2.1. Release 5.2.1 được xây dựng với Spring Boot 4.1.2, yêu cầu Java 17 trở lên và hỗ trợ OSB API v2.17. Khi nâng phiên bản, hãy kiểm tra compatibility matrix của Spring Cloud Open Service Broker thay vì nâng riêng starter mà không kiểm tra Spring Boot.

Tạo project Maven với các dependency:

- Spring Web để chạy HTTP server theo Spring MVC.
- Spring Cloud Open Service Broker để cung cấp OSB API.
- Spring Security để bảo vệ endpoint broker.
- Spring Boot Test để viết unit/integration test.

Cấu trúc thư mục:

~~~text
mock-service-broker/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mockbroker/
    │   │   ├── BrokerApplication.java
    │   │   ├── config/
    │   │   │   ├── CatalogConfiguration.java
    │   │   │   ├── BrokerSecurityConfiguration.java
    │   │   │   └── BrokerSecurityProperties.java
    │   │   ├── provider/
    │   │   │   └── MockDatabaseProvider.java
    │   │   └── service/
    │   │       ├── MockServiceInstanceService.java
    │   │       └── MockServiceInstanceBindingService.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/mockbroker/provider/
            └── MockDatabaseProviderTest.java
~~~

### 3.1. Maven dependencies

Tạo pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mock-service-broker</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <name>mock-service-broker</name>
    <description>Minimal OSB broker with a mock database provider</description>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-open-service-broker</artifactId>
            <version>5.2.1</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 3.2. Main application

Tạo BrokerApplication.java:

~~~java
package com.example.mockbroker;

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

@SpringBootApplication kích hoạt component scan và auto-configuration. Starter Open Service Broker đăng ký các controller OSB khi ứng dụng có Spring Web. @ConfigurationPropertiesScan tìm cấu hình security dạng record ở phần sau.

## 4. Khai báo catalog tĩnh

Catalog là metadata platform dùng để hiển thị service offerings và plans. Trong capstone, catalog chỉ có một service và một plan. Vì nội dung không thay đổi theo request hoặc tenant, cung cấp một bean Catalog là cách đơn giản nhất.

Tạo CatalogConfiguration.java:

~~~java
package com.example.mockbroker.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.model.catalog.Plan;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;

@Configuration
public class CatalogConfiguration {

    @Bean
    public Catalog catalog() {
        Plan sandboxPlan = Plan.builder()
                .id("sandbox")
                .name("sandbox")
                .description("Gói PostgreSQL giả lập dành cho thực hành")
                .free(true)
                .build();

        ServiceDefinition postgresService = ServiceDefinition.builder()
                .id("mock-postgres")
                .name("mock-postgres")
                .description("PostgreSQL service được mô phỏng trong bộ nhớ")
                .bindable(true)
                .tags("database", "postgresql", "mock")
                .plans(sandboxPlan)
                .build();

        return Catalog.builder()
                .serviceDefinitions(postgresService)
                .build();
    }
}
~~~

Các trường cần hiểu:

- id của service và plan là định danh ổn định mà platform lưu trong service instance.
- name là tên hiển thị trong marketplace.
- description mô tả chức năng và giới hạn của service.
- bindable(true) cho biết service hỗ trợ application binding.
- plans(...) công bố các lựa chọn cấu hình mà platform có thể cung cấp cho người dùng.
- free(true) khai báo plan không tính phí trong catalog mẫu.

Không bật plan_updateable hoặc instances_retrievable trong bài này. Vì vậy broker không công bố khả năng update plan hoặc fetch service instance. Nếu sau này bật các capability này, phải triển khai các method tương ứng trong service interface và bổ sung test.

Sau khi ứng dụng khởi động, framework cung cấp endpoint GET /v2/catalog. Bạn không cần tự viết controller cho endpoint này.

## 5. Tạo nhà cung cấp PostgreSQL giả lập

Provider adapter đại diện cho hệ thống thật mà broker quản lý. Trong production, adapter có thể gọi API của cloud database, Kubernetes operator, hệ thống cấp phát nội bộ hoặc SDK của nhà cung cấp. Trong capstone, MockDatabaseProvider mô phỏng những side effect đó bằng hai map:

- instances: lưu service instance đã provision.
- bindings: lưu credentials theo cặp instance ID và binding ID.

Các thao tác được đánh dấu synchronized để hai request đồng thời trong cùng JVM không cùng tạo một instance hoặc binding. Đây chỉ là bảo vệ concurrency cho bài thực hành một process; nó không thay thế transaction hoặc distributed lock khi chạy nhiều replica.

Tạo MockDatabaseProvider.java:

~~~java
package com.example.mockbroker.provider;

import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

@Component
public class MockDatabaseProvider {

    private final Map<String, MockInstance> instances = new HashMap<>();
    private final Map<BindingKey, MockBinding> bindings = new HashMap<>();

    public synchronized ProvisionResult provision(
            String instanceId,
            String serviceId,
            String planId,
            Map<String, Object> parameters) {

        Map<String, Object> requestedParameters = immutableCopy(parameters);
        MockInstance existing = instances.get(instanceId);

        if (existing != null) {
            boolean sameRequest =
                    existing.serviceId().equals(serviceId)
                    && existing.planId().equals(planId)
                    && existing.parameters().equals(requestedParameters);

            if (sameRequest) {
                return new ProvisionResult(true, existing.databaseName());
            }

            throw new InstanceConflictException();
        }

        String databaseName = "db_" + randomSuffix();

        MockInstance created = new MockInstance(
                serviceId,
                planId,
                requestedParameters,
                databaseName
        );

        instances.put(instanceId, created);
        return new ProvisionResult(false, databaseName);
    }

    public synchronized boolean deprovision(String instanceId) {
        boolean instanceExisted = instances.remove(instanceId) != null;

        Set<BindingKey> orphanBindings = new HashSet<>();
        for (BindingKey key : bindings.keySet()) {
            if (key.instanceId().equals(instanceId)) {
                orphanBindings.add(key);
            }
        }

        orphanBindings.forEach(bindings::remove);
        return instanceExisted;
    }

    public synchronized BindingResult bind(
            String instanceId,
            String bindingId,
            String appGuid,
            Map<String, Object> parameters) {

        MockInstance instance = instances.get(instanceId);
        if (instance == null) {
            throw new InstanceMissingException();
        }

        BindingKey key = new BindingKey(instanceId, bindingId);
        Map<String, Object> requestedParameters = immutableCopy(parameters);
        MockBinding existing = bindings.get(key);

        if (existing != null) {
            boolean sameRequest =
                    Objects.equals(existing.appGuid(), appGuid)
                    && existing.parameters().equals(requestedParameters);

            if (sameRequest) {
                return new BindingResult(true, existing.credentials());
            }

            throw new BindingConflictException();
        }

        String username = "mock_user_" + randomSuffix();
        String password = UUID.randomUUID().toString();

        Map<String, String> credentials = Map.of(
                "uri", "jdbc:postgresql://mock-db.invalid:5432/"
                        + instance.databaseName(),
                "username", username,
                "password", password
        );

        MockBinding created = new MockBinding(
                appGuid,
                requestedParameters,
                credentials
        );

        bindings.put(key, created);
        return new BindingResult(false, credentials);
    }

    public synchronized boolean unbind(
            String instanceId,
            String bindingId) {

        return bindings.remove(new BindingKey(instanceId, bindingId)) != null;
    }

    public synchronized boolean instanceExists(String instanceId) {
        return instances.containsKey(instanceId);
    }

    public synchronized boolean bindingExists(
            String instanceId,
            String bindingId) {

        return bindings.containsKey(new BindingKey(instanceId, bindingId));
    }

    private static Map<String, Object> immutableCopy(
            Map<String, Object> source) {

        if (source == null || source.isEmpty()) {
            return Map.of();
        }

        return Collections.unmodifiableMap(new HashMap<>(source));
    }

    private static String randomSuffix() {
        return UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, 12);
    }

    public record ProvisionResult(
            boolean instanceExisted,
            String databaseName) {
    }

    public record BindingResult(
            boolean bindingExisted,
            Map<String, String> credentials) {
    }

    private record MockInstance(
            String serviceId,
            String planId,
            Map<String, Object> parameters,
            String databaseName) {
    }

    private record BindingKey(
            String instanceId,
            String bindingId) {
    }

    private record MockBinding(
            String appGuid,
            Map<String, Object> parameters,
            Map<String, String> credentials) {
    }

    public static class InstanceConflictException
            extends RuntimeException {
    }

    public static class InstanceMissingException
            extends RuntimeException {
    }

    public static class BindingConflictException
            extends RuntimeException {
    }
}
~~~

### 5.1. Đọc cách provider xử lý idempotency

provision() dùng instance ID làm khóa. Nếu khóa chưa tồn tại, provider tạo instance và trả instanceExisted=false. Nếu request lặp có cùng service ID, plan ID và parameters, provider trả lại kết quả đã lưu với instanceExisted=true. Nếu cùng ID nhưng nội dung khác, provider ném InstanceConflictException.

bind() dùng cặp instance ID và binding ID làm khóa. Khi request lặp có cùng app GUID và parameters, provider trả lại credentials đã tạo trước đó. Nhờ vậy retry không tạo username/password mới và không làm mất khả năng kết nối của consumer đang dùng binding cũ.

Provider xử lý unbind và deprovision theo cách idempotent ở tầng state: lần đầu xóa resource và lần sau nhận diện resource đã gone. Service layer ánh xạ trường hợp binding hoặc instance đã mất thành exception OSB để framework trả HTTP 410 Gone. deprovision() cũng dọn mọi binding còn sót thuộc instance đó. Trong luồng chuẩn, platform sẽ gọi delete binding trước deprovision; phần dọn bổ sung giúp provider mô phỏng không để lại binding orphan.

### 5.2. Giới hạn của provider trong bộ nhớ

Các map chỉ tồn tại trong JVM. Khi restart ứng dụng, toàn bộ instance và binding biến mất. Nếu chạy hai replica, mỗi replica có map riêng và kết quả sẽ không nhất quán. Vì vậy:

- Chỉ chạy một process khi thực hành capstone.
- Không dùng provider này để đăng ký với platform production.
- Không dùng credentials giả lập cho dữ liệu thật.
- Khi mở rộng bài, thay map bằng repository/database dùng chung và quản lý secret bằng secret manager.

## 6. Triển khai ServiceInstanceService

ServiceInstanceService nhận request provision, update và deprovision. Catalog không bật plan updateable, vì vậy capstone chỉ override createServiceInstance() và deleteServiceInstance().

Tạo MockServiceInstanceService.java:

~~~java
package com.example.mockbroker.service;

import com.example.mockbroker.provider.MockDatabaseProvider;
import org.springframework.cloud.servicebroker.exception.ServiceInstanceExistsException;
import org.springframework.cloud.servicebroker.exception.ServiceInstanceDoesNotExistException;
import org.springframework.cloud.servicebroker.model.instance.CreateServiceInstanceRequest;
import org.springframework.cloud.servicebroker.model.instance.CreateServiceInstanceResponse;
import org.springframework.cloud.servicebroker.model.instance.DeleteServiceInstanceRequest;
import org.springframework.cloud.servicebroker.model.instance.DeleteServiceInstanceResponse;
import org.springframework.cloud.servicebroker.service.ServiceInstanceService;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class MockServiceInstanceService
        implements ServiceInstanceService {

    private final MockDatabaseProvider provider;

    public MockServiceInstanceService(
            MockDatabaseProvider provider) {
        this.provider = provider;
    }

    @Override
    public Mono<CreateServiceInstanceResponse> createServiceInstance(
            CreateServiceInstanceRequest request) {

        return Mono.fromCallable(() -> {
            try {
                MockDatabaseProvider.ProvisionResult result =
                        provider.provision(
                                request.getServiceInstanceId(),
                                request.getServiceDefinitionId(),
                                request.getPlanId(),
                                request.getParameters()
                        );

                return CreateServiceInstanceResponse.builder()
                        .instanceExisted(result.instanceExisted())
                        .build();

            } catch (MockDatabaseProvider.InstanceConflictException ex) {
                throw new ServiceInstanceExistsException(
                        request.getServiceInstanceId(),
                        request.getServiceDefinitionId()
                );
            }
        });
    }

    @Override
    public Mono<DeleteServiceInstanceResponse> deleteServiceInstance(
            DeleteServiceInstanceRequest request) {

        return Mono.fromCallable(() -> {
            boolean deleted = provider.deprovision(
                    request.getServiceInstanceId());
            if (!deleted) {
                throw new ServiceInstanceDoesNotExistException(
                        request.getServiceInstanceId());
            }

            return DeleteServiceInstanceResponse.builder().build();
        });
    }
}
~~~

Điểm cần chú ý:

- Mono.fromCallable() tạo một reactive publisher chứa kết quả của thao tác đồng bộ.
- instanceExisted(false) cho biết provider vừa tạo tài nguyên; framework trả HTTP 201 Created.
- instanceExisted(true) cho biết tài nguyên cùng request đã tồn tại; framework trả HTTP 200 OK.
- ServiceInstanceExistsException biểu diễn trường hợp cùng instance ID nhưng request có service, plan hoặc parameters khác; framework ánh xạ thành HTTP 409 Conflict.
- Deprovision gọi provider để thu hồi tài nguyên trước khi trả response.

Trong ứng dụng thật, deprovision phải xử lý lỗi từ provider và chỉ báo thành công khi trạng thái tài nguyên đã được xác nhận. Không được nuốt exception rồi trả response thành công.

## 7. Triển khai ServiceInstanceBindingService

Binding cung cấp thông tin kết nối cho consumer. Với application binding, broker thường trả credentials trong response. Broker phải lưu credentials đủ lâu để retry cùng binding trả lại đúng bộ credentials đã cấp, đồng thời phải thu hồi chúng khi unbind.

Tạo MockServiceInstanceBindingService.java:

~~~java
package com.example.mockbroker.service;

import com.example.mockbroker.provider.MockDatabaseProvider;
import org.springframework.cloud.servicebroker.exception.ServiceInstanceBindingExistsException;
import org.springframework.cloud.servicebroker.exception.ServiceInstanceBindingDoesNotExistException;
import org.springframework.cloud.servicebroker.exception.ServiceInstanceDoesNotExistException;
import org.springframework.cloud.servicebroker.model.binding.BindResource;
import org.springframework.cloud.servicebroker.model.binding.CreateServiceInstanceAppBindingResponse;
import org.springframework.cloud.servicebroker.model.binding.CreateServiceInstanceBindingRequest;
import org.springframework.cloud.servicebroker.model.binding.CreateServiceInstanceBindingResponse;
import org.springframework.cloud.servicebroker.model.binding.DeleteServiceInstanceBindingRequest;
import org.springframework.cloud.servicebroker.model.binding.DeleteServiceInstanceBindingResponse;
import org.springframework.cloud.servicebroker.service.ServiceInstanceBindingService;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class MockServiceInstanceBindingService
        implements ServiceInstanceBindingService {

    private final MockDatabaseProvider provider;

    public MockServiceInstanceBindingService(
            MockDatabaseProvider provider) {
        this.provider = provider;
    }

    @Override
    public Mono<CreateServiceInstanceBindingResponse>
    createServiceInstanceBinding(
            CreateServiceInstanceBindingRequest request) {

        return Mono.fromCallable(() -> {
            try {
                BindResource bindResource = request.getBindResource();
                String appGuid = bindResource == null
                        ? null
                        : bindResource.getAppGuid();

                MockDatabaseProvider.BindingResult result =
                        provider.bind(
                                request.getServiceInstanceId(),
                                request.getBindingId(),
                                appGuid,
                                request.getParameters()
                        );

                return (CreateServiceInstanceBindingResponse)
                        CreateServiceInstanceAppBindingResponse.builder()
                                .credentials(
                                        "uri",
                                        result.credentials().get("uri")
                                )
                                .credentials(
                                        "username",
                                        result.credentials().get("username")
                                )
                                .credentials(
                                        "password",
                                        result.credentials().get("password")
                                )
                                .bindingExisted(result.bindingExisted())
                                .build();

            } catch (MockDatabaseProvider.InstanceMissingException ex) {
                throw new ServiceInstanceDoesNotExistException(
                        request.getServiceInstanceId()
                );

            } catch (MockDatabaseProvider.BindingConflictException ex) {
                throw new ServiceInstanceBindingExistsException(
                        request.getServiceInstanceId(),
                        request.getBindingId()
                );
            }
        });
    }

    @Override
    public Mono<DeleteServiceInstanceBindingResponse>
    deleteServiceInstanceBinding(
            DeleteServiceInstanceBindingRequest request) {

        return Mono.fromCallable(() -> {
            boolean deleted = provider.unbind(
                    request.getServiceInstanceId(),
                    request.getBindingId()
            );
            if (!deleted) {
                throw new ServiceInstanceBindingDoesNotExistException(
                        request.getBindingId());
            }

            return DeleteServiceInstanceBindingResponse.builder().build();
        });
    }
}
~~~

CreateServiceInstanceAppBindingResponse là response cho application binding. Các credentials được trả về dưới dạng object trong body. Trong thực tế, platform có thể chuyển chúng vào môi trường ứng dụng, chẳng hạn VCAP_SERVICES trên Cloud Foundry.

Framework cung cấp default method cho thao tác fetch binding và last operation. Capstone không quảng cáo bindings_retrievable và không dùng asynchronous binding, nên không cần override hai method đó.

## 8. Bảo vệ endpoint broker bằng Spring Security

Spring Cloud Open Service Broker cung cấp controller OSB nhưng không tự cấu hình authentication/authorization cho broker. Cần thêm Spring Security và áp dụng chính sách bảo vệ cho /v2/**.

### 8.1. Khai báo credentials theo cấu hình

Tạo BrokerSecurityProperties.java:

~~~java
package com.example.mockbroker.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "broker.security")
public record BrokerSecurityProperties(
        String username,
        String password) {
}
~~~

Tạo BrokerSecurityConfiguration.java:

~~~java
package com.example.mockbroker.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BrokerSecurityConfiguration {

    @Bean
    SecurityFilterChain brokerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        return http
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/v2/**").authenticated()
                        .anyRequest().permitAll()
                )
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
                )
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService brokerUserDetailsService(
            BrokerSecurityProperties properties,
            PasswordEncoder passwordEncoder) {

        UserDetails brokerUser = User
                .withUsername(properties.username())
                .password(passwordEncoder.encode(properties.password()))
                .roles("BROKER")
                .build();

        return new InMemoryUserDetailsManager(brokerUser);
    }
}
~~~

### 8.2. Cấu hình local

Tạo application.yml:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: mock-service-broker
  cloud:
    openservicebroker:
      api-version: "2.17"

broker:
  security:
    username: local-broker
    password: change-me-local-only
~~~

Credentials mặc định chỉ phục vụ chạy local. Trước khi expose endpoint ra mạng, hãy override bằng secret riêng, bật HTTPS, thiết lập rotation và giới hạn nguồn truy cập. Không commit password production vào application.yml.

Basic Auth không thay thế TLS. Không truyền credentials broker qua HTTP không mã hóa. Ngoài ra, cần phân biệt credentials platform-to-broker với credentials mà broker trả cho app consumer trong binding response.

## 9. Khởi chạy ứng dụng

Từ thư mục project, chạy:

~~~bash
./mvnw clean test
./mvnw spring-boot:run
~~~

Trên Windows PowerShell dùng Maven Wrapper tương ứng:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd spring-boot:run
~~~

Khi ứng dụng khởi động, kiểm tra log không có lỗi bean hoặc dependency. Broker chạy tại http://localhost:8080; endpoint catalog nằm ở /v2/catalog.

Nếu gặp lỗi ServiceInstanceService hoặc ServiceInstanceBindingService bean không tồn tại, kiểm tra:
- Class implementation có annotation @Service.
- Package của class nằm dưới package gốc được @SpringBootApplication scan.
- Dependency spring-cloud-starter-open-service-broker đã được khai báo.
- Ứng dụng có spring-boot-starter-web để kích hoạt web auto-configuration.

## 10. Kiểm tra catalog

Gọi:

~~~bash
curl -i \
  -u local-broker:change-me-local-only \
  -H "X-Broker-API-Version: 2.17" \
  http://localhost:8080/v2/catalog
~~~

Kết quả cần có một service definition với ID mock-postgres, bindable: true và plan sandbox.

Ví dụ rút gọn:

~~~json
{
  "services": [
    {
      "id": "mock-postgres",
      "name": "mock-postgres",
      "description": "PostgreSQL service được mô phỏng trong bộ nhớ",
      "bindable": true,
      "tags": ["database", "postgresql", "mock"],
      "plans": [
        {
          "id": "sandbox",
          "name": "sandbox",
          "description": "Gói PostgreSQL giả lập dành cho thực hành",
          "free": true
        }
      ]
    }
  ]
}
~~~

Nếu catalog rỗng, kiểm tra bean Catalog có được tạo và trả về đúng Catalog.builder().serviceDefinitions(...). Không tạo REST controller riêng cho /v2/catalog khi đã dùng auto-configuration của framework.

## 11. Provision service instance

Gửi yêu cầu tạo instance có ID inst-orders:

~~~bash
curl -i \
  -u local-broker:change-me-local-only \
  -X PUT \
  -H "X-Broker-API-Version: 2.17" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "mock-postgres",
    "plan_id": "sandbox",
    "parameters": {
      "database": "orders"
    }
  }' \
  "http://localhost:8080/v2/service_instances/inst-orders?accepts_incomplete=false"
~~~

Vì provider mô phỏng hoàn tất ngay trong process, response là synchronous. Lần đầu tạo instance thành công thường trả HTTP 201 Created. Broker không trả async=true và không cần endpoint last_operation.

Gửi lại chính request trên. Provider nhận ra instance ID và parameters đã tồn tại, trả instanceExisted=true; framework trả HTTP 200 OK. Không tạo database giả lập thứ hai.

Nếu gửi cùng instance ID nhưng plan hoặc parameters khác, provider ném InstanceConflictException, service chuyển thành ServiceInstanceExistsException và framework trả HTTP 409 Conflict.

## 12. Tạo service binding

Sau khi provision thành công, tạo binding cho application có GUID giả lập app-orders-api:

~~~bash
curl -i \
  -u local-broker:change-me-local-only \
  -X PUT \
  -H "X-Broker-API-Version: 2.17" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "mock-postgres",
    "plan_id": "sandbox",
    "bind_resource": {
      "app_guid": "app-orders-api"
    }
  }' \
  "http://localhost:8080/v2/service_instances/inst-orders/service_bindings/bind-orders-api?accepts_incomplete=false"
~~~

Response chứa credentials giả lập:

~~~json
{
  "credentials": {
    "uri": "jdbc:postgresql://mock-db.invalid:5432/db_...",
    "username": "mock_user_...",
    "password": "..."
  }
}
~~~

Các giá trị username/password được sinh ngẫu nhiên và lưu trong map của provider. Nếu cùng binding ID và app GUID gửi lại cùng parameters, broker trả lại đúng credentials cũ với binding_existed=true; framework phản hồi HTTP 200 OK. Nếu binding ID giống nhau nhưng request khác, broker trả HTTP 409 Conflict.

Thử bind vào instance không tồn tại. Provider ném InstanceMissingException, service chuyển thành ServiceInstanceDoesNotExistException; framework trả lỗi tài nguyên không tồn tại.

Không đưa credentials vào log, screenshot, ticket hoặc Git. Khi kiểm tra response, chỉ dùng môi trường local và dữ liệu giả lập.

## 13. Unbind và deprovision

### 13.1. Thu hồi binding

Gọi DELETE binding:

~~~bash
curl -i \
  -u local-broker:change-me-local-only \
  -X DELETE \
  -H "X-Broker-API-Version: 2.17" \
  "http://localhost:8080/v2/service_instances/inst-orders/service_bindings/bind-orders-api?service_id=mock-postgres&plan_id=sandbox&accepts_incomplete=false"
~~~

Provider xóa record binding và credentials. Nếu binding đã không còn tồn tại, broker ném ServiceInstanceBindingDoesNotExistException để framework trả HTTP 410 Gone theo OSB. Request xóa lặp vẫn giữ trạng thái tài nguyên đã xóa; platform nhận được tín hiệu chuẩn rằng binding đã gone.

### 13.2. Deprovision instance

Sau khi đã gỡ các binding, xóa instance:

~~~bash
curl -i \
  -u local-broker:change-me-local-only \
  -X DELETE \
  -H "X-Broker-API-Version: 2.17" \
  "http://localhost:8080/v2/service_instances/inst-orders?service_id=mock-postgres&plan_id=sandbox&accepts_incomplete=false"
~~~

Provider xóa instance và các binding còn sót của nó. Trong thực tế, platform phải xóa các binding trước khi deprovision. Nếu instance không tồn tại, broker ném ServiceInstanceDoesNotExistException để framework trả HTTP 410 Gone. Theo OSB, 410 là kết quả đúng khi platform yêu cầu xóa một instance đã gone; không trả 200 cho request DELETE lặp trên resource không tồn tại.

Kiểm tra lại bằng cách thử bind vào instance đã xóa. Request phải nhận lỗi instance không tồn tại. Nếu provision lại cùng instance ID, provider tạo một database name giả lập mới.

## 14. Kiểm thử idempotency và conflict

Các tình huống quan trọng:

| Request | Kết quả mong đợi |
|---|---|
| Provision instance ID mới | HTTP 201, tạo một instance |
| Provision lại cùng ID, service, plan và parameters | HTTP 200, trả instance_existed=true |
| Provision cùng ID nhưng parameters khác | HTTP 409 |
| Bind vào instance tồn tại | HTTP 201, tạo credentials |
| Bind lại cùng instance/binding/app/parameters | HTTP 200, trả credentials đã lưu |
| Bind cùng ID nhưng app hoặc parameters khác | HTTP 409 |
| Bind vào instance không tồn tại | Lỗi resource not found |
| Unbind một binding | HTTP 200, credentials bị xóa |
| Unbind lặp khi binding đã mất | HTTP 410 Gone |
| Deprovision instance | HTTP 200, instance bị xóa |
| Deprovision lặp khi instance đã mất | HTTP 410 Gone |

### 14.1. Unit test cho provider

Tạo MockDatabaseProviderTest.java:

~~~java
package com.example.mockbroker.provider;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class MockDatabaseProviderTest {

    private final MockDatabaseProvider provider =
            new MockDatabaseProvider();

    @Test
    void provisionSameRequestIsIdempotent() {
        var first = provider.provision(
                "instance-1",
                "mock-postgres",
                "sandbox",
                Map.of("database", "orders")
        );

        var retry = provider.provision(
                "instance-1",
                "mock-postgres",
                "sandbox",
                Map.of("database", "orders")
        );

        assertFalse(first.instanceExisted());
        assertTrue(retry.instanceExisted());
        assertEquals(first.databaseName(), retry.databaseName());
    }

    @Test
    void provisionDifferentParametersWithSameIdConflicts() {
        provider.provision(
                "instance-2",
                "mock-postgres",
                "sandbox",
                Map.of("database", "orders")
        );

        assertThrows(
                MockDatabaseProvider.InstanceConflictException.class,
                () -> provider.provision(
                        "instance-2",
                        "mock-postgres",
                        "sandbox",
                        Map.of("database", "billing")
                )
        );
    }

    @Test
    void bindingRetryReturnsTheSameCredentials() {
        provider.provision(
                "instance-3",
                "mock-postgres",
                "sandbox",
                Map.of()
        );

        var first = provider.bind(
                "instance-3",
                "binding-1",
                "app-1",
                Map.of()
        );

        var retry = provider.bind(
                "instance-3",
                "binding-1",
                "app-1",
                Map.of()
        );

        assertFalse(first.bindingExisted());
        assertTrue(retry.bindingExisted());
        assertEquals(first.credentials(), retry.credentials());
    }

    @Test
    void unbindRemovesCredentials() {
        provider.provision(
                "instance-4",
                "mock-postgres",
                "sandbox",
                Map.of()
        );

        provider.bind("instance-4", "binding-1", "app-1", Map.of());
        assertTrue(provider.bindingExists("instance-4", "binding-1"));

        assertTrue(provider.unbind("instance-4", "binding-1"));

        assertFalse(provider.bindingExists("instance-4", "binding-1"));
        assertFalse(provider.unbind("instance-4", "binding-1"));
    }

    @Test
    void deprovisionReturnsFalseWhenInstanceIsAlreadyGone() {
        provider.provision(
                "instance-5",
                "mock-postgres",
                "sandbox",
                Map.of()
        );

        provider.bind("instance-5", "binding-1", "app-1", Map.of());
        assertTrue(provider.bindingExists("instance-5", "binding-1"));

        assertTrue(provider.deprovision("instance-5"));
        assertFalse(provider.instanceExists("instance-5"));
        assertFalse(provider.bindingExists("instance-5", "binding-1"));
        assertFalse(provider.deprovision("instance-5"));
    }
}
~~~

Chạy test:

~~~bash
./mvnw test
~~~

Các test này xác nhận provider mock xử lý idempotency và cleanup. Bạn vẫn cần integration test cho HTTP controller, authentication, catalog JSON và response status nếu muốn kiểm tra cả contract OSB.

## 15. Đọc đường đi của một request

Khi provision được gửi, Spring Cloud Open Service Broker thực hiện phần HTTP protocol:

1. Đọc path và query parameter.
2. Kiểm tra API version và request body.
3. Resolve service definition và plan từ catalog.
4. Gọi MockServiceInstanceService.createServiceInstance().
5. Serialize response và chọn HTTP status theo trường instanceExisted.

Code capstone không cần viết:
- @RestController cho /v2/catalog.
- Controller riêng cho provision/deprovision.
- JSON parser thủ công cho OSB request.
- Logic tự chọn HTTP status cho response thành công.
- Endpoint riêng cho last_operation khi không bật async.

Framework đảm nhiệm những phần protocol này. Code của bạn tập trung vào nghiệp vụ provider.

### 15.1. Phân biệt OSB model và provider model

| OSB model | Provider model trong capstone |
|---|---|
| CreateServiceInstanceRequest | Tham số truyền vào provision() |
| CreateServiceInstanceResponse | ProvisionResult được ánh xạ thành response |
| CreateServiceInstanceBindingRequest | Tham số truyền vào bind() |
| CreateServiceInstanceAppBindingResponse | Credentials từ BindingResult |
| DeleteServiceInstanceBindingRequest | Khóa instance ID + binding ID |
| DeleteServiceInstanceRequest | Instance ID cần deprovision |

Tách hai lớp này giúp sau này thay mock provider bằng API thật mà không phải viết lại toàn bộ phần HTTP protocol.

## 16. Những gì chưa có trong capstone

Bài thực hành được cố ý giữ nhỏ để người học tập trung vào catalog và lifecycle cơ bản. Trước khi đưa một broker vào môi trường thật, cần bổ sung các phần sau:

| Thành phần | Capstone hiện tại | Hướng nâng cấp |
|---|---|---|
| Instance state | HashMap trong JVM | Database bền vững, transaction và migration |
| Binding state | HashMap trong JVM | Repository riêng, ràng buộc instance/binding |
| Credentials | Password ngẫu nhiên trong bộ nhớ | Secret manager, mã hóa và rotation |
| Provider | Database giả lập | Adapter gọi API/SDK thật |
| Idempotency | So sánh ID, plan và parameters trong synchronized method | Unique constraint, request fingerprint và transaction |
| Async operation | Không bật | Operation table, outbox, worker và last_operation |
| Concurrency | Một JVM | Optimistic/pessimistic lock hoặc distributed coordination |
| Authentication | HTTP Basic local | TLS, secret rotation, OAuth2/mTLS nếu platform hỗ trợ |
| Observability | Chưa triển khai | Structured log, correlation ID, metrics và tracing |
| Tenant isolation | Chưa triển khai | Scope theo platform/organization/space/tenant |

Không deploy nhiều replica với provider in-memory. Hai Pod có thể trả credentials hoặc trạng thái instance khác nhau cho cùng một ID. Khi thay provider bằng hệ thống thật, lưu trạng thái broker bền vững và bảo đảm retry đến bất kỳ replica nào cũng nhận diện được cùng operation.

## 17. Mở rộng capstone theo từng giai đoạn

Sau khi các request đồng bộ hoạt động, có thể mở rộng bài theo trình tự:

### Giai đoạn A: Thêm service plan thứ hai

Tạo plan small và standard, thêm thuộc tính capacity vào mock instance. Kiểm tra catalog hiển thị cả hai plan và provider lưu đúng plan ID.

### Giai đoạn B: Thêm validation parameters

Dùng service instance schema trong catalog để mô tả parameters được chấp nhận, chẳng hạn database name hoặc backup policy. Validate lại ở provider layer; không chỉ dựa vào form validation phía platform.

### Giai đoạn C: Thay in-memory map bằng database

Tạo bảng broker_instance và broker_binding. Dùng unique constraint trên instance ID và cặp instance/binding ID. Lưu credential reference, không lưu password dạng plaintext nếu không có yêu cầu rõ ràng.

### Giai đoạn D: Thêm asynchronous provision

Khi provider thật mất nhiều thời gian:
1. Commit instance record, operation record và outbox event.
2. Trả response async=true cùng operation token.
3. Worker xử lý provider call.
4. getLastOperation() trả IN_PROGRESS, SUCCEEDED hoặc FAILED.
5. Platform polling đến khi operation kết thúc.

Nếu request không chấp nhận async, broker phải tuân thủ OSB và trả lỗi phù hợp thay vì trả 202 tùy ý.

### Giai đoạn E: Thêm update

Chỉ bật plan_updateable trong catalog khi broker thực sự hỗ trợ update. Triển khai updateServiceInstance(), kiểm tra previous plan, parameters và trạng thái instance. Xác định rõ instance còn usable hay không nếu update thất bại.

### Giai đoạn F: Tích hợp provider thật

Thay MockDatabaseProvider bằng adapter:
- provision: gọi API tạo database.
- bind: tạo user hoặc credential riêng cho app.
- unbind: revoke credential.
- deprovision: xóa resource theo policy.
- Mọi call có timeout, retry có giới hạn và idempotency key.
- Provider timeout sau side effect phải được reconciliation trước khi retry.

## 18. Lỗi thường gặp và cách xử lý

**GET /v2/catalog trả 404.** Kiểm tra starter dependency, Spring Web dependency và component scan. Không tự viết controller trước khi xác nhận auto-configuration.

**GET /v2/catalog trả 401.** Gửi đúng Basic Auth hoặc kiểm tra cấu hình BrokerSecurityProperties. Nếu không có Spring Security filter chain đúng, endpoint có thể bị bảo vệ theo cấu hình mặc định ngoài dự kiến.

**Request trả 412 Precondition Failed.** Header X-Broker-API-Version không khớp phiên bản broker cấu hình. Dùng v2.17 cho ví dụ 5.2.1 hoặc điều chỉnh cấu hình API version phù hợp.

**Provision trả 409 dù request giống nhau.** Kiểm tra provider có so sánh service ID, plan ID và parameters nhất quán không. Tránh đưa timestamp hoặc random value vào parameters fingerprint.

**Bind trả 404.** Instance chưa được provision hoặc instance ID trong binding path không khớp.

**Bind trả 409 khi retry.** App GUID hoặc binding parameters khác lần đầu. Kiểm tra platform có đang dùng lại binding ID cho consumer khác không.

**Retry bind trả credentials mới.** Provider không lưu credentials theo binding key hoặc đang tạo password trước khi kiểm tra binding tồn tại. Chỉ tạo credentials khi binding mới được tạo thành công.

**Xóa instance nhưng binding còn tồn tại.** Kiểm tra deprovision có cleanup binding theo instance ID và platform có thực hiện unbind trước không.

**Ứng dụng mất toàn bộ service sau restart.** Đây là giới hạn có chủ ý của in-memory provider. Thay state store bằng database trước khi chạy ngoài môi trường thực hành.

**Một replica thấy instance, replica khác không thấy.** Mỗi process có map riêng. Dùng shared database hoặc không scale capstone in-memory.

**Credentials xuất hiện trong log.** Kiểm tra log request/response, debug serialization và exception. Không log binding response hoặc credentials map.

## 19. Tiêu chí hoàn thành capstone

Capstone đạt yêu cầu khi bạn chứng minh được các điều kiện:

- [ ] Ứng dụng Spring Boot khởi động thành công.
- [ ] GET /v2/catalog trả service mock-postgres và plan sandbox.
- [ ] Endpoint /v2/** yêu cầu authentication.
- [ ] Provision instance mới trả HTTP 201.
- [ ] Provision lại cùng request trả HTTP 200 và không tạo instance thứ hai.
- [ ] Cùng instance ID nhưng parameters khác trả HTTP 409.
- [ ] Bind instance hợp lệ trả credentials giả lập.
- [ ] Bind retry trả lại đúng credentials cũ.
- [ ] Binding ID trùng nhưng request khác trả HTTP 409.
- [ ] Bind vào instance không tồn tại trả lỗi resource not found.
- [ ] Unbind xóa credentials của đúng binding.
- [ ] Unbind lặp sau khi binding đã gone trả HTTP 410.
- [ ] Deprovision xóa instance và cleanup binding còn sót.
- [ ] Deprovision lặp sau khi instance đã gone trả HTTP 410.
- [ ] Test provider cho idempotency và cleanup đều pass.
- [ ] Không có password production hoặc credentials thật trong repository/log.

Khi demo, hãy thực hiện theo thứ tự: đọc catalog, provision, provision retry, bind, bind retry, unbind và deprovision. Sau mỗi bước, giải thích service nào xử lý request và dữ liệu nào thay đổi trong provider giả lập.

## 20. Nguyên tắc triển khai trong Spring Cloud Service Broker

Một broker tối thiểu cần có catalog ổn định, service instance service, binding service và provider adapter. Spring Cloud Open Service Broker cung cấp các controller và model OSB; các bean của ứng dụng thực hiện logic nghiệp vụ. Catalog tĩnh phù hợp khi service và plan ít thay đổi. Khi metadata phụ thuộc cấu hình hoặc nguồn dữ liệu bên ngoài, có thể chuyển sang CatalogService.

Trong capstone, provision và binding được thực hiện đồng bộ. Provider mock lưu instance và binding trong bộ nhớ, trả lại kết quả cũ cho request lặp và từ chối request trùng ID nhưng có nội dung khác. Binding response trả credentials giả lập; unbind thu hồi credentials; deprovision dọn instance cùng binding liên quan.

Đây là nền tảng để mở rộng sang provider thật. Khi thay map bằng database, hãy giữ idempotency và tính nhất quán giữa các replica. Khi thao tác dài, ghi operation bền vững trước khi trả asynchronous response và triển khai last_operation. Trước khi expose broker cho platform, bảo vệ endpoint bằng TLS và authentication, quản lý secret riêng, kiểm thử toàn bộ lifecycle và bảo đảm trạng thái broker luôn đối chiếu được với tài nguyên provider.

## Tài liệu tham khảo

- [Spring Cloud Open Service Broker – Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/reference/)
- [Spring Cloud Open Service Broker – Project and version information](https://spring.io/projects/spring-cloud-open-service-broker/)
- [Spring Cloud Open Service Broker – GitHub releases and compatibility matrix](https://github.com/spring-cloud/spring-cloud-open-service-broker/releases)
- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md)
- [Spring Cloud Open Service Broker – ServiceInstanceDoesNotExistException](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/exception/ServiceInstanceDoesNotExistException.html)
- [Spring Cloud Open Service Broker – ServiceInstanceBindingDoesNotExistException](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/exception/ServiceInstanceBindingDoesNotExistException.html)
- [Spring Boot – Building an Application](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Security – HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)

