# Giới hạn dung lượng, số lượng và tài nguyên theo từng gói

Service plan mô tả một mức dịch vụ mà người dùng có thể chọn khi yêu cầu cấp phát tài nguyên. Trong một Spring Cloud service broker tuân thủ Open Service Broker API (OSB API), mỗi plan cần gắn với một cấu hình tài nguyên cụ thể và một chính sách quota có thể thực thi được. Ví dụ, plan small có thể giới hạn một database ở 500 millicore CPU, 512 MiB bộ nhớ, 10 GiB dung lượng lưu trữ và 30 kết nối đồng thời; plan production có thể cung cấp giới hạn cao hơn.

Quản lý giới hạn theo plan giúp broker kiểm soát chi phí, tránh một tenant chiếm hết năng lực của nhà cung cấp và bảo đảm người dùng nhận đúng mức dịch vụ đã chọn. Tuy nhiên, việc ghi các con số vào catalog chưa đủ để giới hạn tài nguyên thực tế. Broker phải kiểm tra yêu cầu, đặt trước quota, truyền cấu hình đến backing service hoặc nền tảng hạ tầng, theo dõi trạng thái cấp phát và giải phóng quota khi tài nguyên được thu hồi.

Bài học này trình bày cách phân loại quota, thiết kế giới hạn cho từng plan, khai báo cấu hình trong Spring Boot, kiểm tra và thực thi quota trong luồng provision, cũng như xử lý đồng thời, bất đồng bộ, cập nhật plan và deprovision.

## 1. Vì sao mỗi service plan cần giới hạn tài nguyên?

Một service có thể cung cấp nhiều plan để đáp ứng nhu cầu khác nhau. Nếu tất cả plan đều cấp tài nguyên không giới hạn, broker khó dự đoán chi phí và không thể bảo đảm năng lực phục vụ cho các tenant.

Ví dụ, một broker cung cấp PostgreSQL cho nhiều nhóm phát triển:

| Plan | CPU tối đa mỗi instance | RAM tối đa mỗi instance | Storage tối đa | Kết nối tối đa |
|---|---:|---:|---:|---:|
| small | 500m | 512 MiB | 10 GiB | 30 |
| standard | 1.000m | 2.048 MiB | 50 GiB | 100 |
| production | 2.000m | 8.192 MiB | 200 GiB | 300 |

Các mức trên là ví dụ thiết kế. Broker cần chuyển chúng thành cấu hình tương ứng với nhà cung cấp thực tế, bởi một CPU limit trong Kubernetes, một vCPU trên máy ảo và một đơn vị CPU của dịch vụ database managed không nhất thiết có cùng ngữ nghĩa.

Giới hạn tài nguyên theo plan có một số mục tiêu:

- Bảo đảm mỗi instance chỉ sử dụng tối đa tài nguyên được plan cho phép.
- Giới hạn số instance mà một tenant hoặc toàn broker có thể tạo.
- Kiểm soát tổng tài nguyên mà một tenant đã sử dụng hoặc đang đặt trước.
- Phân biệt gói thử nghiệm, gói tiêu chuẩn và gói production.
- Dự báo năng lực hạ tầng, chi phí và khả năng đáp ứng trước khi nhận yêu cầu mới.
- Ngăn việc gửi tham số provision quá lớn để vượt qua giới hạn của plan.

Plan là một lựa chọn sản phẩm. Quota là chính sách mà broker dùng để thực thi lựa chọn đó. Hai khái niệm liên quan chặt chẽ nhưng không đồng nhất: catalog mô tả plan; hệ thống quản lý quota kiểm soát việc cấp phát và sử dụng tài nguyên.

## 2. Phân biệt các loại giới hạn

Khi thiết kế quota, cần xác định rõ giới hạn áp dụng ở cấp nào. Một con số như 10 GiB có thể là dung lượng tối đa của một database, tổng dung lượng một tenant được sử dụng, hoặc dung lượng còn lại của toàn cluster. Nếu không ghi rõ phạm vi, việc kiểm tra quota rất dễ sai.

### 2.1. Giới hạn trên mỗi service instance

Đây là mức tối đa mà một instance riêng lẻ được phép sử dụng. Ví dụ:

- CPU: tối đa 500 millicore.
- Bộ nhớ: tối đa 512 MiB.
- Storage: tối đa 10 GiB.
- Kết nối đồng thời: tối đa 30.
- Số replica: tối đa 1.
- Số lượng database hoặc schema: tối đa theo chính sách riêng.

Giới hạn này thường được ánh xạ thành cấu hình của backing service. Với Kubernetes, CPU và memory có thể được chuyển thành resource requests/limits trong Pod hoặc workload. Với PostgreSQL managed, broker có thể chọn instance class, storage size và giới hạn connection theo API của nhà cung cấp.

### 2.2. Giới hạn số lượng instance theo tenant

Quota này xác định một tenant được tạo tối đa bao nhiêu service instance của một plan hoặc một service.

Ví dụ:

- Mỗi tenant được tạo tối đa 5 instance PostgreSQL small.
- Mỗi tenant được tạo tối đa 2 instance PostgreSQL production.
- Một tenant được tạo tối đa 10 instance trên tất cả plan của service PostgreSQL.

Cần chọn phạm vi rõ ràng: theo tenant + service + plan, theo tenant + service, hay theo tenant trên toàn broker. Nếu mỗi plan có quota riêng, người dùng có thể tạo số lượng lớn bằng cách phân tán qua nhiều plan. Nếu cần giới hạn tổng thể, hãy bổ sung quota ở cấp service hoặc tenant.

### 2.3. Giới hạn tổng tài nguyên theo tenant

Một tenant có thể tạo nhiều instance. Vì vậy, chỉ giới hạn số instance là chưa đủ. Ví dụ một tenant có thể tạo 5 database small, nhưng tổng storage của chúng vẫn có thể vượt ngân sách nếu mỗi instance được cấu hình gần mức tối đa.

Có thể đặt giới hạn tổng như:

| Phạm vi | Quota ví dụ |
|---|---:|
| Tổng CPU đã cấp cho tenant | 4.000 millicore |
| Tổng RAM đã cấp cho tenant | 8.192 MiB |
| Tổng storage đã cấp cho tenant | 100 GiB |
| Tổng số instance PostgreSQL | 10 |
| Tổng số kết nối dự kiến | 500 |

Quota tổng cần tính theo mức tài nguyên đã đặt trước hoặc đã cấp phát, không chỉ theo mức sử dụng tức thời. Nếu chỉ đo CPU đang dùng tại một thời điểm, nhiều tenant có thể cùng tạo tài nguyên vượt quá năng lực dự kiến dù mức sử dụng hiện tại thấp.

### 2.4. Giới hạn tổng thể của broker hoặc nhà cung cấp

Broker cũng cần giới hạn tổng số tài nguyên có thể tạo trên toàn hệ thống. Ví dụ, nhà cung cấp chỉ cho phép broker tạo tối đa 100 database nhỏ trong một tài khoản cloud, hoặc cluster chỉ còn 500 GiB storage có thể cấp phát.

Giới hạn này thường được quản lý ở cấp broker, tài khoản cloud, cluster, region hoặc một nhóm tài nguyên. Nó khác quota tenant: dù tenant còn quota riêng, broker vẫn phải từ chối hoặc xếp hàng khi năng lực tổng thể đã hết.

### 2.5. Giới hạn mềm và giới hạn cứng

| Loại | Hành vi | Ví dụ |
|---|---|---|
| Hard limit | Không cho phép vượt ngưỡng | Không cấp database nếu tenant đã đạt 5 instance |
| Soft limit | Cảnh báo khi tiến gần hoặc vượt ngưỡng được phép tạm thời | Gửi cảnh báo khi storage đạt 80% |
| Burst limit | Cho phép tăng ngắn hạn trong phạm vi xác định | Cho phép CPU burst trong giới hạn của hạ tầng |
| Rate limit | Giới hạn tốc độ gửi yêu cầu | Tối đa 10 lần provision mỗi phút |

Quota tài nguyên và rate limit giải quyết những vấn đề khác nhau. Một tenant có thể còn quota nhưng gửi hàng trăm request trong vài giây; rate limit giúp bảo vệ broker và nhà cung cấp khỏi lưu lượng đột biến.

## 3. Chọn đơn vị đo nhất quán

Một trong những nguồn lỗi phổ biến nhất là không thống nhất đơn vị. Cấu hình ghi 10 GB nhưng API nhà cung cấp hiểu là 10 GiB; hệ thống quota cộng byte nhưng báo cáo lại hiển thị gigabyte thập phân.

Nên quy định đơn vị chuẩn cho từng loại tài nguyên:

| Tài nguyên | Đơn vị khuyến nghị trong cấu hình | Ví dụ |
|---|---|---|
| CPU | millicore hoặc vCPU | 500m hoặc 2 vCPU |
| Memory | MiB hoặc byte | 512 MiB |
| Storage | GiB hoặc byte | 10 GiB |
| Kết nối | số nguyên | 30 connections |
| Replica | số nguyên | 2 replicas |
| Request mỗi giây | request/second | 100 RPS |
| Băng thông | MiB/s hoặc Mbps | 50 Mbps |

CPU millicore thường tiện khi ánh xạ tới Kubernetes: 1.000 millicore tương đương 1 CPU core theo cách biểu diễn Kubernetes. Với storage và memory, cần phân biệt GB/GiB và MB/MiB. Một GiB bằng 1.024 MiB; một GB theo hệ thập phân bằng 1.000 MB.

Không nên dùng số thực không có quy ước đơn vị cho tài nguyên quan trọng. Ví dụ, lưu storage dưới dạng số nguyên GiB hoặc byte giúp so sánh và cộng quota chính xác hơn. Khi chuyển sang API nhà cung cấp, adapter chịu trách nhiệm đổi đơn vị theo hợp đồng của API đó.

Cũng cần phân biệt resource request, resource limit và quota tiêu thụ:

- Request là mức tài nguyên được yêu cầu hoặc dùng để scheduler đặt chỗ.
- Limit là ngưỡng tối đa mà workload được phép sử dụng theo cơ chế của nền tảng.
- Quota là giới hạn tổng hoặc giới hạn cấp phát được áp dụng cho một tenant, plan hay broker.

Không thể dùng ba khái niệm này thay thế cho nhau. Ví dụ Kubernetes ResourceQuota giới hạn tổng tài nguyên trong namespace, còn container resource limit áp dụng cho từng container.

## 4. Thiết kế ma trận quota cho các plan

Trước khi viết cấu hình, hãy lập bảng thể hiện mỗi plan cấp bao nhiêu tài nguyên và quota được áp dụng ở phạm vi nào.

Ví dụ cho dịch vụ PostgreSQL:

| Thuộc tính | small | standard | production |
|---|---:|---:|---:|
| CPU mỗi instance | 500m | 1.000m | 2.000m |
| Memory mỗi instance | 512 MiB | 2.048 MiB | 8.192 MiB |
| Storage mỗi instance | 10 GiB | 50 GiB | 200 GiB |
| Kết nối tối đa | 30 | 100 | 300 |
| Replica tối đa | 1 | 1 | 2 |
| Instance tối đa mỗi tenant | 5 | 3 | 2 |
| Instance tối đa toàn broker | 100 | 60 | 20 |
| Tổng storage tối đa mỗi tenant | 50 GiB | 150 GiB | 400 GiB |

Khi đọc bảng, cần hiểu rõ các quota có cùng phạm vi hay độc lập. Ví dụ quota tổng storage theo plan trong bảng có thể được tính riêng cho từng nhóm plan. Nếu một tenant dùng đồng thời small và production, cần thêm một quota tổng ở cấp service hoặc tenant để kiểm soát toàn bộ lượng storage.

Không phải plan nào cũng cần mọi chiều tài nguyên. Với dịch vụ cache, giới hạn memory và số connection có thể quan trọng hơn storage. Với object storage, dung lượng và số object quan trọng hơn CPU. Hãy chọn các chiều có ý nghĩa với backing service và có cách thực thi thực tế.

## 5. Khai báo giới hạn trong YAML

Có thể quản lý quota bằng một namespace cấu hình riêng của ứng dụng, ví dụ broker.plan-limits. Đây là cấu trúc nội bộ do dự án lựa chọn để quản lý chính sách; OSB API không quy định các key này phải có tên như vậy.

Ví dụ application.yml:

~~~yaml
broker:
  plan-limits:
    - service-id: postgres-service-id
      plan-id: postgres-small-plan-id
      max-instances-per-tenant: 5
      max-instances-global: 100
      max-total-storage-gib-per-tenant: 50
      resources:
        cpu-millis: 500
        memory-mib: 512
        storage-gib: 10
        max-connections: 30
        max-replicas: 1

    - service-id: postgres-service-id
      plan-id: postgres-standard-plan-id
      max-instances-per-tenant: 3
      max-instances-global: 60
      max-total-storage-gib-per-tenant: 150
      resources:
        cpu-millis: 1000
        memory-mib: 2048
        storage-gib: 50
        max-connections: 100
        max-replicas: 1

    - service-id: postgres-service-id
      plan-id: postgres-production-plan-id
      max-instances-per-tenant: 2
      max-instances-global: 20
      max-total-storage-gib-per-tenant: 400
      resources:
        cpu-millis: 2000
        memory-mib: 8192
        storage-gib: 200
        max-connections: 300
        max-replicas: 2
~~~

Mỗi phần tử ánh xạ một cặp service ID và plan ID. Cặp này là khóa để broker tìm chính sách quota khi nhận provision hoặc update. Các ID trong ví dụ chỉ mang tính minh họa; trong hệ thống thật, phải dùng đúng ID mà catalog công bố.

Cấu trúc trên có hai nhóm dữ liệu:

- Quota số lượng và tổng dung lượng: giới hạn số instance và storage cộng dồn của tenant hoặc toàn broker.
- Resource profile: giới hạn tài nguyên của từng instance như CPU, memory, storage, connections và replicas.

Có thể mở rộng resource profile theo loại backing service. Ví dụ Redis có thể thêm max-memory-policy; RabbitMQ có thể thêm max-queues hoặc max-connections; object storage có thể thêm max-objects và max-object-size. Không nên đưa một trường chung vào tất cả plan nếu trường đó không có ý nghĩa hoặc không thể thực thi.

## 6. Khai báo cùng cấu hình bằng application.properties

Spring Boot hỗ trợ bind danh sách lồng nhau từ application.properties bằng chỉ số phần tử.

Ví dụ cấu hình plan small:

~~~properties
broker.plan-limits[0].service-id=postgres-service-id
broker.plan-limits[0].plan-id=postgres-small-plan-id
broker.plan-limits[0].max-instances-per-tenant=5
broker.plan-limits[0].max-instances-global=100
broker.plan-limits[0].max-total-storage-gib-per-tenant=50
broker.plan-limits[0].resources.cpu-millis=500
broker.plan-limits[0].resources.memory-mib=512
broker.plan-limits[0].resources.storage-gib=10
broker.plan-limits[0].resources.max-connections=30
broker.plan-limits[0].resources.max-replicas=1
~~~

Plan standard có thể được khai báo ở chỉ số 1:

~~~properties
broker.plan-limits[1].service-id=postgres-service-id
broker.plan-limits[1].plan-id=postgres-standard-plan-id
broker.plan-limits[1].max-instances-per-tenant=3
broker.plan-limits[1].max-instances-global=60
broker.plan-limits[1].max-total-storage-gib-per-tenant=150
broker.plan-limits[1].resources.cpu-millis=1000
broker.plan-limits[1].resources.memory-mib=2048
broker.plan-limits[1].resources.storage-gib=50
broker.plan-limits[1].resources.max-connections=100
broker.plan-limits[1].resources.max-replicas=1
~~~

| YAML | application.properties |
|---|---|
| Phần tử đầu tiên trong plan-limits | plan-limits[0] |
| service-id | service-id |
| resources.cpu-millis | resources.cpu-millis |
| resources.memory-mib | resources.memory-mib |
| max-instances-per-tenant | max-instances-per-tenant |

YAML dễ đọc hơn khi có nhiều plan và nhiều trường lồng nhau. Properties phù hợp khi hệ thống triển khai quản lý cấu hình theo key-value. Dù dùng định dạng nào, cần bảo đảm các trường bắt buộc có giá trị và không khai báo cùng một chính sách ở nhiều nguồn cấu hình với giá trị mâu thuẫn.

## 7. Bind quota vào Java bằng ConfigurationProperties

Spring Boot có thể bind cấu hình broker.plan-limits vào Java object thông qua @ConfigurationProperties. Ví dụ sau dùng record và validation annotation theo phong cách Spring Boot 3, Java 17:

~~~java
package com.example.broker.quota;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "broker")
@Validated
public record BrokerQuotaProperties(
        @NotEmpty List<@Valid PlanLimit> planLimits) {

    public record PlanLimit(
            @NotBlank String serviceId,
            @NotBlank String planId,
            @Positive int maxInstancesPerTenant,
            @Positive int maxInstancesGlobal,
            @Positive long maxTotalStorageGibPerTenant,
            @NotNull @Valid ResourceLimits resources) {
    }

    public record ResourceLimits(
            @Positive long cpuMillis,
            @Positive long memoryMib,
            @Positive long storageGib,
            @Positive int maxConnections,
            @Positive int maxReplicas) {
    }
}
~~~

Đăng ký class cấu hình bằng @ConfigurationPropertiesScan:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class BrokerApplication {

    public static void main(String[] args) {
        SpringApplication.run(BrokerApplication.class, args);
    }
}
~~~

Hoặc đăng ký cụ thể bằng @EnableConfigurationProperties(BrokerQuotaProperties.class) trong một class cấu hình. Chọn một cơ chế phù hợp với ứng dụng.

Các annotation validation giúp phát hiện danh sách rỗng, ID thiếu hoặc giới hạn bằng 0 hay số âm khi ứng dụng khởi động. Với Spring Boot 3, ví dụ sử dụng jakarta.validation; dự án Spring Boot 2 có thể cần namespace javax.validation và phiên bản dependency tương ứng. Cần có validation implementation trên classpath, thường qua spring-boot-starter-validation.

Validation cơ bản không tự kiểm tra ID trùng lặp giữa các phần tử. Có thể bổ sung bước kiểm tra khi khởi tạo để bảo đảm mỗi cặp serviceId và planId chỉ có một cấu hình quota.

## 8. Tra cứu chính sách theo service ID và plan ID

Khi platform gửi yêu cầu provision, broker nhận service_id và plan_id trong request. Broker phải tra cứu đúng cấu hình quota tương ứng. Không nên chọn plan chỉ dựa vào tên hiển thị vì tên có thể thay đổi hoặc không duy nhất.

Ví dụ một thành phần tra cứu:

~~~java
package com.example.broker.quota;

import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Component;

@Component
public class PlanLimitRegistry {

    private final Map<PlanKey, BrokerQuotaProperties.PlanLimit> limits;

    public PlanLimitRegistry(BrokerQuotaProperties properties) {
        this.limits = properties.planLimits().stream()
                .collect(Collectors.toUnmodifiableMap(
                        limit -> new PlanKey(
                                limit.serviceId(), limit.planId()),
                        Function.identity()));
    }

    public BrokerQuotaProperties.PlanLimit require(
            String serviceId, String planId) {

        var key = new PlanKey(serviceId, planId);
        var limit = limits.get(key);

        if (limit == null) {
            throw new IllegalArgumentException(
                    "No quota policy configured for service and plan");
        }

        return limit;
    }

    private record PlanKey(String serviceId, String planId) {
    }
}
~~~

Collectors.toUnmodifiableMap sẽ phát hiện khóa trùng lặp trong lúc tạo registry. Trong ứng dụng production, lỗi cấu hình này nên khiến ứng dụng không khởi động hoặc không sẵn sàng nhận request, thay vì chọn ngẫu nhiên một chính sách.

Khi service ID hoặc plan ID không được nhận diện, broker cần trả lỗi theo hợp đồng OSB phù hợp. Không được mặc định dùng plan small hoặc một quota rộng hơn, vì hành vi đó có thể cấp phát tài nguyên ngoài chính sách.

## 9. Kiểm tra tham số người dùng so với giới hạn plan

Ngoài quota cố định của plan, platform có thể gửi parameters trong request provision. Ví dụ người dùng muốn chọn database name, storage size hoặc số replica. Broker cần phân biệt:

- Giá trị mặc định của plan: cấu hình mà broker sử dụng khi người dùng không yêu cầu tùy chỉnh.
- Giá trị người dùng yêu cầu: tham số gửi trong request provision.
- Giới hạn tối đa của plan: ngưỡng không được vượt qua.
- Giới hạn quota còn lại: lượng tài nguyên tenant hoặc broker còn có thể cấp.

Ví dụ plan small có storage tối đa 10 GiB. Người dùng yêu cầu 8 GiB thì có thể chấp nhận nếu tenant còn đủ quota. Nếu yêu cầu 20 GiB, broker phải từ chối hoặc yêu cầu chọn plan phù hợp hơn.

Một quy tắc kiểm tra đơn giản:

~~~java
public long resolveStorageGiB(
        Long requestedGiB,
        long planMaxStorageGiB) {

    long effectiveGiB = requestedGiB == null
            ? planMaxStorageGiB
            : requestedGiB;

    if (effectiveGiB <= 0 || effectiveGiB > planMaxStorageGiB) {
        throw new IllegalArgumentException(
                "Requested storage exceeds the selected plan");
    }

    return effectiveGiB;
}
~~~

Đoạn code trên minh họa một chính sách trong đó giá trị mặc định sử dụng toàn bộ mức storage của plan. Một broker khác có thể chọn giá trị mặc định nhỏ hơn. Điều quan trọng là phải định nghĩa rõ semantics của tham số và kiểm tra cả giới hạn mỗi instance lẫn quota tổng còn lại.

Nếu OSB catalog công bố schema cho parameters, schema có thể giúp platform kiểm tra kiểu dữ liệu và hiển thị biểu mẫu nhập liệu. Tuy nhiên, schema không thay thế kiểm tra ở broker. Client có thể gửi request trực tiếp hoặc bỏ qua giao diện người dùng; broker vẫn phải xác thực mọi tham số tại server.

## 10. Thực thi quota trong luồng provision

Một luồng provision an toàn cần thực hiện theo thứ tự:

1. Xác thực request và định danh tenant từ context đã được platform xác thực.
2. Tra cứu service ID và plan ID trong catalog cùng registry quota.
3. Kiểm tra tham số người dùng nằm trong giới hạn của plan.
4. Tính lượng tài nguyên cần đặt trước.
5. Kiểm tra quota tenant và năng lực tổng thể của broker.
6. Đặt trước quota một cách nguyên tử và ghi nhận trạng thái instance.
7. Gọi API nhà cung cấp để tạo tài nguyên.
8. Khi tài nguyên sẵn sàng, chuyển reservation thành usage đã cấp phát.
9. Nếu thao tác thất bại, thực hiện bù trừ và giải phóng reservation đúng cách.

~~~mermaid
flowchart TD
    A[Nhận provision request] --> B[Xác thực tenant và request]
    B --> C[Tra cứu service / plan]
    C --> D[Kiểm tra parameters]
    D --> E{Còn quota?}
    E -->|Không| F[Từ chối theo OSB error]
    E -->|Có| G[Đặt trước quota nguyên tử]
    G --> H[Gọi nhà cung cấp]
    H --> I{Provision thành công?}
    I -->|Có| J[Ghi nhận instance và usage]
    I -->|Không| K[Compensate và release reservation]
    J --> L[Trả kết quả hoặc async operation]
~~~

Không nên gọi API nhà cung cấp trước rồi mới kiểm tra quota. Nếu nhà cung cấp đã tạo tài nguyên mà quota bị từ chối sau đó, broker phải xóa tài nguyên hoặc chấp nhận trạng thái vượt quota. Việc đặt trước trước khi gọi provider giúp tránh tình trạng nhiều request cùng nhìn thấy một lượng quota còn lại và cùng tiêu thụ nó.

### 10.1. Đặt trước quota

Giả sử tenant có quota tổng storage 50 GiB và đã dùng hoặc đặt trước 45 GiB. Một request mới cần 10 GiB. Broker phải từ chối vì tổng dự kiến là 55 GiB.

Phép kiểm tra cần tính cả reservation đang xử lý:

~~~text
available = quota_limit - allocated - reserved

accept khi:
requested <= available
~~~

Trong đó:

- quota_limit là giới hạn tổng.
- allocated là tài nguyên của instance đã cấp phát.
- reserved là tài nguyên đang được giữ cho các thao tác provision chưa hoàn tất.
- requested là lượng tài nguyên của yêu cầu mới.

Nếu bỏ qua reserved, nhiều request đồng thời có thể cùng vượt qua kiểm tra dựa trên một số dư chưa được cập nhật.

### 10.2. Reservation phải có định danh

Mỗi reservation nên gắn với service instance ID và operation ID. Khi platform retry cùng yêu cầu, broker có thể nhận ra reservation đã tồn tại và tiếp tục xử lý thay vì đặt trước lần thứ hai.

Reservation nên lưu ít nhất:

- Tenant hoặc scope sở hữu quota.
- Service ID và plan ID.
- Service instance ID.
- CPU, memory, storage và các đơn vị tài nguyên đã giữ.
- Trạng thái reservation: pending, committed, released hoặc trạng thái tương đương.
- Thời điểm tạo và thời hạn xử lý.
- Operation ID để liên kết với tác vụ bất đồng bộ.

Khi provision thành công, reservation được chuyển thành allocated usage. Khi thất bại chắc chắn, reservation được giải phóng. Nếu broker mất kết nối và chưa biết provider đã tạo tài nguyên hay chưa, không được giải phóng ngay; cần đối soát hoặc tiếp tục truy vấn trạng thái trước khi quyết định.

## 11. Chống vượt quota khi có nhiều request đồng thời

Một lỗi thường gặp là kiểm tra quota bằng cách đọc số liệu rồi ghi lại bằng hai thao tác tách rời:

~~~text
Đọc used = 40 GiB
Kiểm tra 40 + 10 <= 50
Ghi used = 50 GiB
~~~

Nếu hai request cùng chạy, cả hai có thể cùng đọc used = 40 GiB, cùng thấy còn đủ quota và cùng cấp thêm 10 GiB. Kết quả thực tế là 60 GiB, vượt giới hạn 50 GiB.

Để tránh race condition, thao tác kiểm tra và đặt trước cần nguyên tử. Một số cách triển khai:

- Dùng transaction cơ sở dữ liệu với khóa hàng quota theo tenant và scope.
- Dùng câu lệnh cập nhật có điều kiện, chỉ tăng usage nếu tổng mới không vượt quota.
- Dùng optimistic locking với version và retry khi có xung đột.
- Dùng một hệ thống reservation có cơ chế atomic compare-and-set.
- Phân vùng quota theo tenant hoặc resource pool để giảm tranh chấp.

Ví dụ logic SQL minh họa:

~~~sql
UPDATE tenant_quota
SET reserved_storage_gib = reserved_storage_gib + :requested
WHERE tenant_id = :tenant
  AND allocated_storage_gib
      + reserved_storage_gib
      + :requested <= storage_limit_gib;
~~~

Sau câu lệnh, broker kiểm tra số hàng được cập nhật. Nếu là 1, reservation thành công; nếu là 0, quota đã hết hoặc tenant không có bản ghi quota phù hợp. Trong thực tế, cần transaction bao gồm cả các chiều quota liên quan và khóa nhất quán để không xảy ra tình trạng storage được đặt trước nhưng CPU hoặc instance count không được đặt trước.

Nếu quota được lưu trong nhiều hệ thống khác nhau, chẳng hạn database broker và API quota của cloud provider, không thể giả định một transaction ACID bao phủ cả hai. Khi đó cần thiết kế reservation, trạng thái trung gian, retry và thao tác bù trừ.

## 12. Xử lý quota trong provision bất đồng bộ

Provision một database hoặc cluster có thể mất vài phút. Broker có thể trả phản hồi bất đồng bộ khi platform cho phép, sau đó cập nhật trạng thái qua last_operation.

Trong thời gian thao tác đang chạy, reservation phải tiếp tục được giữ. Nếu giải phóng quota ngay sau khi trả phản hồi đang xử lý, một request khác có thể sử dụng cùng phần tài nguyên đã hứa cho instance đầu tiên.

Một vòng đời minh họa:

| Trạng thái instance | Trạng thái quota | Ý nghĩa |
|---|---|---|
| REQUESTED | Chưa giữ | Request mới nhận |
| RESERVING | Đang đặt trước | Broker kiểm tra và giữ quota |
| PROVISIONING | RESERVED | Provider đang tạo tài nguyên |
| SUCCEEDED | ALLOCATED | Tài nguyên đã sẵn sàng |
| FAILED | RELEASED | Thao tác thất bại và reservation đã được giải phóng |
| DEPROVISIONING | ALLOCATED hoặc RELEASING | Tài nguyên đang được xóa |
| DEPROVISIONED | RELEASED | Đã xác nhận thu hồi và giải phóng quota |

Tên trạng thái là ví dụ cho state machine nội bộ; có thể khác với tên trạng thái của framework. Điều quan trọng là reservation và allocated usage có vòng đời rõ ràng, không bị mất khi broker restart.

Nếu provider timeout, broker cần xác định thao tác đã thất bại hay chỉ chưa nhận được phản hồi. Có thể truy vấn provider bằng operation ID hoặc external resource ID. Nếu chưa xác định được kết quả, giữ reservation trong trạng thái pending và chạy cơ chế đối soát. Cần có timeout và quy trình xử lý reservation treo để quota không bị chiếm vô thời hạn.

## 13. Giải phóng quota khi deprovision và unbind

Deprovision xóa service instance, vì vậy quota của instance chỉ nên được giải phóng khi broker xác nhận tài nguyên đã được xóa hoặc đã chuyển sang trạng thái không còn tiêu thụ tài nguyên theo định nghĩa của nhà cung cấp.

Không nên giảm usage ngay khi nhận request deprovision. Nếu provider xóa thất bại, tài nguyên vẫn tồn tại nhưng quota đã được trả lại cho tenant; một instance mới có thể được cấp phát khiến tổng tài nguyên thực tế vượt mức cho phép.

Unbind có ý nghĩa khác. Unbind thu hồi một binding hoặc credential; thông thường nó không xóa service instance và không giải phóng CPU, memory hay storage của instance. Nếu binding tạo ra tài nguyên riêng, chẳng hạn user hoặc connection pool, broker có thể có quota riêng cho loại tài nguyên binding đó. Cần phân biệt quota instance với quota binding.

Quy trình deprovision nên có các bước:

1. Đánh dấu instance đang thu hồi để chặn các thao tác xung đột.
2. Gọi API provider để xóa hoặc thu hồi tài nguyên.
3. Kiểm tra kết quả thực tế và xử lý thao tác bất đồng bộ nếu cần.
4. Chỉ khi xác nhận đã thu hồi, chuyển usage sang released.
5. Ghi nhận thời điểm và kết quả để retry deprovision không giải phóng quota hai lần.

Thao tác giải phóng cũng phải idempotent. Một instance chỉ được trả quota một lần, kể cả khi platform retry DELETE hoặc broker nhận lại callback.

## 14. Cập nhật plan và thay đổi mức tài nguyên

OSB API có thể cho phép platform yêu cầu update service instance khi service công bố khả năng plan update. Trong catalog, khả năng này được mô tả ở cấp service theo thuộc tính plan_updateable. Việc khai báo khả năng không có nghĩa mọi chuyển đổi plan đều an toàn hoặc luôn thực hiện được.

Khi update từ small lên production, broker cần:

- Xác định plan hiện tại và plan đích bằng ID.
- Kiểm tra service có cho phép update plan.
- Tính phần tài nguyên tăng thêm và kiểm tra quota còn lại.
- Đặt trước phần quota chênh lệch trước khi nâng cấp tài nguyên.
- Gọi provider để thay đổi cấu hình hoặc di chuyển tài nguyên.
- Khi thành công, cập nhật usage theo plan mới.
- Nếu thất bại, giữ hoặc phục hồi quota theo trạng thái tài nguyên thực tế.

Ví dụ, instance đang dùng 10 GiB storage và chuyển sang plan có mức tối đa 50 GiB. Broker không nhất thiết phải cấp ngay 50 GiB nếu provider hỗ trợ mở rộng theo yêu cầu; nhưng cần bảo đảm giới hạn mới không vượt quota tổng của tenant.

Khi downgrade từ production xuống small, broker phải kiểm tra tài nguyên thực tế. Nếu database đang dùng 30 GiB mà plan small chỉ cho phép 10 GiB, việc đổi plan có thể cần giảm dữ liệu, di chuyển hoặc từ chối. Không nên chỉ đổi plan ID trong database broker trong khi backing service vẫn sử dụng cấu hình cũ.

## 15. Ánh xạ quota vào Kubernetes hoặc cloud provider

Quota trong broker chỉ có tác dụng thực tế khi được ánh xạ xuống hệ thống tạo tài nguyên.

### 15.1. Kubernetes

Với backing service được triển khai trên Kubernetes, broker có thể chuyển resource profile thành cấu hình workload:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
~~~

Đoạn YAML trên minh họa resource requests và limits của container. Broker cần tạo workload với cấu hình tương ứng, đồng thời cân nhắc ResourceQuota, LimitRange và quota storage của namespace hoặc cluster.

Một số điểm cần phân biệt:

- Container resource limit kiểm soát tài nguyên của container.
- Namespace ResourceQuota kiểm soát tổng tài nguyên được yêu cầu hoặc cấp phát trong namespace.
- PersistentVolumeClaim có thể yêu cầu storage; StorageClass và quota của cluster quyết định khả năng cấp phát.
- Số replica làm tăng tổng tài nguyên của workload.
- Network policy và giới hạn kết nối cần được xử lý ở lớp phù hợp.

Không nên chỉ ghi CPU/memory trong catalog mà không cấu hình chúng vào workload. Cũng không nên tin rằng đặt resource limit sẽ tự động giới hạn storage hoặc số connection của database.

### 15.2. Cloud provider

Với database managed hoặc dịch vụ cloud, broker cần ánh xạ plan ID sang cấu hình sản phẩm của nhà cung cấp. Ví dụ:

| Resource profile của broker | Cấu hình provider có thể tương ứng |
|---|---|
| CPU 2.000m, memory 8.192 MiB | Instance class hoặc compute tier |
| Storage 200 GiB | Allocated storage |
| Max connections 300 | Database parameter hoặc connection policy |
| Max replicas 2 | Số node hoặc replica được phép |
| Backup retention 14 ngày | Backup retention policy |

Các mapping này phụ thuộc sản phẩm và API của provider. Không thể suy ra một cấu hình instance class chỉ từ số CPU và memory nếu provider có các lớp máy với tỷ lệ tài nguyên hoặc đặc tính khác nhau.

Nên đặt mapping trong adapter riêng để thay đổi nhà cung cấp không làm thay đổi chính sách plan ở lớp nghiệp vụ. Broker có thể giữ một mô hình resource profile chung, sau đó adapter chuyển profile sang tham số cụ thể của provider.

## 16. Quan sát quota và cảnh báo

Quản lý quota cần có số liệu để người vận hành biết tài nguyên nào đang được cấp phát, còn bao nhiêu khả năng và reservation nào bị treo.

Các metric hữu ích:

- quota_limit theo tenant, service, plan và loại tài nguyên.
- allocated_usage theo cùng các chiều.
- reserved_usage cho thao tác đang chạy.
- available_quota.
- số lần từ chối do hết quota.
- thời gian trung bình từ reservation tới commit hoặc release.
- số reservation quá hạn.
- chênh lệch giữa trạng thái broker và tài nguyên thực tế ở provider.

Có thể tính:

~~~text
available = limit - allocated - reserved

usage_percent = (allocated + reserved) / limit * 100
~~~

Metric cần có nhãn phù hợp nhưng tránh tạo cardinality quá lớn. Không nên đưa secret, credentials hoặc dữ liệu nhạy cảm vào metric label. Với hệ thống nhiều tenant, cần cân nhắc cách phân quyền truy cập dashboard để người dùng không xem được quota của tenant khác.

Cảnh báo có thể được đặt khi usage vượt 80%, khi reservation tồn tại quá lâu hoặc khi provider có tài nguyên nhưng broker không có bản ghi tương ứng. Cảnh báo giúp phát hiện sai lệch trước khi tenant bị từ chối provision hoặc chi phí tăng bất thường.

## 17. Ví dụ tình huống: hai request cạnh tranh quota

Giả sử tenant A có quota storage 50 GiB. Tenant đã cấp phát 30 GiB và đang có reservation 10 GiB. Số dư khả dụng là 10 GiB.

Hai request provision cùng đến, mỗi request yêu cầu thêm 8 GiB:

- Request thứ nhất kiểm tra và đặt trước 8 GiB thành công.
- Request thứ hai thực hiện kiểm tra sau khi reservation thứ nhất đã được ghi nhận. Lúc này chỉ còn 2 GiB nên bị từ chối.
- Tổng allocated + reserved là 48 GiB, vẫn trong quota 50 GiB.

Nếu hai request chỉ đọc quota mà không đặt trước nguyên tử, cả hai có thể cùng thấy 10 GiB còn lại và cùng được chấp nhận. Tổng dự kiến khi đó là 56 GiB. Đây là lý do kiểm tra và reservation phải được thực hiện trong một thao tác có tính nguyên tử.

Nếu request thứ nhất thất bại khi provider tạo tài nguyên, broker xác nhận thất bại rồi giải phóng 8 GiB reservation. Tenant có thể thử lại request mới sau đó.

## 18. Lỗi thường gặp khi thiết kế quota

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Tenant tạo nhiều instance hơn giới hạn | Chỉ kiểm tra quota trước khi gọi provider, không đặt trước nguyên tử | Dùng transaction hoặc conditional update |
| Tổng tài nguyên vượt quota dù số instance hợp lệ | Chỉ giới hạn số lượng, không cộng tổng CPU/RAM/storage | Theo dõi quota tổng theo tenant và service |
| Provider tạo tài nguyên nhưng broker báo hết quota | Kiểm tra quota sau khi tạo tài nguyên hoặc reservation không bền vững | Đặt trước trước khi gọi provider và lưu trạng thái |
| Quota bị giữ mãi sau khi provision thất bại | Không có bù trừ hoặc reconciliation | Quản lý reservation state và quy trình hết hạn |
| Deprovision thất bại nhưng quota đã được trả | Giải phóng quota ngay khi nhận DELETE | Chỉ release sau khi xác nhận provider đã thu hồi |
| Retry làm tăng usage nhiều lần | Commit hoặc release không idempotent | Gắn reservation với instance ID và operation ID |
| Một plan có thể yêu cầu tài nguyên vượt cấu hình | Không kiểm tra parameters ở server | Validate request với hard limit của plan |
| Quota khác nhau giữa các replica | Cấu hình hoặc cache không đồng nhất | Dùng nguồn cấu hình và kho quota nhất quán |
| Upgrade plan làm vượt quota tenant | Chỉ kiểm tra quota lúc provision | Kiểm tra và reserve phần chênh lệch trong update |
| Số liệu dashboard không khớp provider | Không đối soát tài nguyên ngoài hệ thống | Thực hiện reconciliation định kỳ và lưu external resource ID |

## 19. Quy trình thiết kế và vận hành quota

Khi thêm một plan mới hoặc thay đổi giới hạn, có thể thực hiện theo quy trình:

1. Xác định các loại tài nguyên có ý nghĩa đối với backing service.
2. Chọn đơn vị chuẩn và định nghĩa rõ phạm vi quota.
3. Lập ma trận resource profile cho từng plan.
4. Định nghĩa quota theo instance, tenant và toàn broker.
5. Khai báo cấu hình trong YAML hoặc properties.
6. Bind và validate cấu hình khi ứng dụng khởi động.
7. Ánh xạ plan ID sang resource profile và provider configuration.
8. Thực thi kiểm tra, reservation và commit trong provision/update.
9. Giải phóng quota đúng thời điểm trong luồng deprovision.
10. Kiểm thử retry, request đồng thời, provider timeout và lỗi giữa các bước.
11. Theo dõi metric, cảnh báo và đối soát quota với tài nguyên thực tế.
12. Review thay đổi quota như một phần của thay đổi plan và chính sách sản phẩm.

Khi điều chỉnh giới hạn của một plan đang được sử dụng, cần quyết định thay đổi chỉ áp dụng cho instance mới hay cả instance hiện có. Nếu áp dụng cho instance hiện có, broker có thể cần một quy trình migration hoặc reconciliation. Không nên tự động hạ tài nguyên của instance đang chạy mà không đánh giá ảnh hưởng tới ứng dụng.

## 20. Checklist trước khi công bố plan

- [ ] Mỗi plan có resource profile được định nghĩa rõ.
- [ ] CPU, memory, storage, connections và replica dùng đơn vị nhất quán.
- [ ] Đã phân biệt giới hạn mỗi instance, quota tenant và quota toàn broker.
- [ ] Đã xác định quota hard limit, soft limit và rate limit khi cần.
- [ ] Service ID và plan ID ánh xạ đúng tới cấu hình quota.
- [ ] Cấu hình YAML hoặc properties được bind và validate.
- [ ] Tham số provision được kiểm tra ở phía broker.
- [ ] Reservation được tạo nguyên tử trước khi gọi provider.
- [ ] Retry không tạo reservation hoặc usage trùng lặp.
- [ ] Reservation được giữ trong khi thao tác bất đồng bộ còn chạy.
- [ ] Deprovision chỉ release quota sau khi xác nhận tài nguyên đã thu hồi.
- [ ] Update plan kiểm tra phần tài nguyên tăng hoặc giảm.
- [ ] Resource profile được ánh xạ đúng tới Kubernetes hoặc cloud provider.
- [ ] Có metric cho allocated, reserved và available quota.
- [ ] Có quy trình reconciliation và xử lý reservation treo.
- [ ] Đã kiểm thử nhiều request đồng thời và tình huống provider timeout.

Giới hạn dung lượng, số lượng và tài nguyên theo từng plan là chính sách vận hành cốt lõi của service broker. Catalog giúp platform hiểu các lựa chọn dịch vụ; cấu hình plan xác định mức tài nguyên; quota service kiểm tra và đặt trước năng lực; provider adapter thực thi cấu hình lên hạ tầng. Khi các bước này được nối với nhau bằng trạng thái bền vững, reservation nguyên tử và xử lý retry an toàn, broker có thể cung cấp nhiều mức dịch vụ mà vẫn kiểm soát được năng lực và chi phí.

