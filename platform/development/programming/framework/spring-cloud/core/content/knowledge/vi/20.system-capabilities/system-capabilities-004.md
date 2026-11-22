# Đọc tên, phiên bản và nhà cung cấp của implementation

## 1. Vì sao cần đọc metadata của implementation?

Spring Cloud Commons định nghĩa nhiều abstraction để ứng dụng không phụ thuộc trực tiếp vào một nhà cung cấp cụ thể. Ví dụ, consumer có thể dùng `DiscoveryClient` để tìm service, còn implementation thực tế có thể đến từ Eureka, Consul, Zookeeper hoặc một thư viện discovery khác.

Khi vận hành, chỉ biết ứng dụng có bean `DiscoveryClient` đôi khi chưa đủ. Ta còn cần trả lời: feature nào đang được nhận diện, implementation class nào đang cung cấp nó, package công bố version nào và vendor nào.

Spring Cloud Commons cung cấp Actuator endpoint `/features` để công bố thông tin này. Response có hai nhóm `enabled` và `disabled`. Với feature được bật, mỗi phần tử có các trường `name`, `type`, `version` và `vendor`.

Bài học thuộc chương **Khả năng hệ thống** của **SPRING_CLOUD_CORE**. Trọng tâm là cách đọc endpoint, hiểu nguồn gốc của version/vendor metadata, phân biệt hai loại feature mà endpoint hỗ trợ và tự khai báo feature cho module riêng.

## 2. Endpoint `/actuator/features`

`FeaturesEndpoint` là một Spring Boot Actuator endpoint có ID là `features`. Khi endpoint được expose qua HTTP và management base path mặc định là `/actuator`, có thể đọc bằng:

```bash
curl -i http://localhost:8080/actuator/features
```

Endpoint là thao tác đọc. Response mô tả những feature mà các module Spring Cloud đã khai báo thông qua bean `HasFeatures`, cùng trạng thái enabled/disabled theo cách endpoint xử lý từng loại feature.

Để endpoint xuất hiện, ứng dụng thường cần:

1. Có Spring Boot Actuator trên classpath.
2. Có Spring Cloud Commons và các module muốn công bố feature trên classpath.
3. Không tắt tính năng bằng `spring.cloud.features.enabled=false`.
4. Endpoint được Spring Boot xem là available và được expose qua HTTP hoặc JMX theo nhu cầu.

Thêm Actuator dependency nếu dự án chưa có:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Cấu hình expose riêng endpoint cần đọc:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,features
```

Thuộc tính `spring.cloud.features.enabled` mặc định là `true`. Có thể tắt endpoint bằng:

```yaml
spring:
  cloud:
    features:
      enabled: false
```

Nếu ứng dụng đã đổi `management.endpoints.web.base-path` hoặc chạy management server ở port riêng, URL thực tế sẽ thay đổi theo cấu hình đó.

**Expose endpoint là bước riêng với việc bật feature.** Một feature có thể đã được khai báo trong context nhưng client không đọc được endpoint nếu Actuator chưa có, endpoint bị tắt hoặc chưa được expose.

## 3. Cấu trúc response

Response có hai mảng:

- `enabled`: danh sách feature được endpoint ghi nhận là đang bật.
- `disabled`: tên những abstract feature không tìm thấy bean tương ứng trong ApplicationContext.

Ví dụ minh họa:

```json
{
  "enabled": [
    {
      "type": "com.example.discovery.ConsulDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "5.0.3",
      "vendor": "Example Vendor"
    },
    {
      "type": "com.example.payment.StripePaymentConnector",
      "name": "Payment Connector",
      "version": null,
      "vendor": null
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
```

Các giá trị version/vendor trong JSON chỉ minh họa hình dạng response. Chúng phụ thuộc manifest metadata thực tế của package đang chạy; không nên mặc định một implementation sẽ luôn có đủ hai giá trị.

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Tên feature do abstraction hoặc `NamedFeature` xác định |
| `type` | Tên đầy đủ (canonical class name) của class dùng để mô tả implementation |
| `version` | `Implementation-Version` lấy từ metadata của package chứa class |
| `vendor` | `Implementation-Vendor` lấy từ metadata của package chứa class |
| `enabled` | Mảng các feature được ghi nhận là bật |
| `disabled` | Mảng tên abstract feature không có bean theo type |

`type` giúp phân biệt hai implementation cùng cung cấp một abstraction. `version` và `vendor` giúp đối chiếu artifact đang chạy với release notes, advisory hoặc SBOM.

## 4. Hai loại feature: abstract và named

Spring Cloud Commons chia feature thành hai loại: **abstract feature** và **named feature**. Cách endpoint xác định trạng thái và lấy metadata của hai loại khác nhau.

### 4.1. Abstract feature

Abstract feature được mô tả bằng một interface hoặc abstract class. Ví dụ:

- `DiscoveryClient`
- `LoadBalancerClient`
- `LockService`

Endpoint dùng class/interface này làm khóa để tìm bean trong ApplicationContext.

Quy trình:

1. Lấy class đã khai báo trong danh sách abstract features.
2. Dùng `ApplicationContext.getBean(type)` để tìm bean theo type.
3. Nếu không tìm thấy bean, thêm `type.getSimpleName()` vào mảng `disabled`.
4. Nếu tìm thấy bean, lấy class thực tế từ `bean.getClass()`.
5. Tạo feature descriptor với tên là simple name của abstraction và class runtime của bean.
6. Đọc canonical name, implementation version và implementation vendor từ package của class runtime.

Ví dụ, module discovery khai báo `DiscoveryClient.class`. Nếu context có bean `ConsulDiscoveryClient` triển khai interface này, response có thể có:

```json
{
  "type": "org.springframework.cloud.consul.discovery.ConsulDiscoveryClient",
  "name": "DiscoveryClient",
  "version": "5.0.3",
  "vendor": "Example Vendor"
}
```

Nếu không có bean nào tương ứng, endpoint đưa `DiscoveryClient` vào mảng `disabled`. Vì vậy, tên trong `disabled` thường là tên abstraction, không phải tên implementation cụ thể.

### 4.2. Named feature

Named feature dùng khi một tính năng không có interface/abstract class chung phù hợp để endpoint tìm bean. Module tự cung cấp tên dễ đọc của feature và class đại diện cho implementation hoặc artifact cần lấy metadata.

Ví dụ:

```java
new NamedFeature(
        "Payment Connector",
        StripePaymentConnector.class
)
```

Với named feature, endpoint lấy `name` và `type` từ descriptor đã khai báo, sau đó đọc package metadata từ class được truyền vào. Nó không thực hiện bước `ApplicationContext.getBean(type)` giống abstract feature.

Điều này có một hệ quả: named feature là **metadata do module khai báo**. Nếu module khai báo feature một cách vô điều kiện trong khi implementation thực tế không được tạo, endpoint vẫn có thể liệt kê nó trong `enabled`. Hãy đặt bean `HasFeatures` trong cấu hình có điều kiện phù hợp với việc feature thực sự được cung cấp.

### 4.3. So sánh hai loại

| Tiêu chí | Abstract feature | Named feature |
| --- | --- | --- |
| Khai báo | Interface hoặc abstract class | Tên và class đại diện |
| Cách endpoint xác định trạng thái | Tìm bean theo type trong context | Dựa trên descriptor đã khai báo |
| Tên hiển thị | Simple name của abstraction | Tên truyền vào `NamedFeature` |
| Class lấy metadata | Class thực tế của bean | Class truyền vào descriptor |
| Khi không có bean | Đưa tên abstraction vào `disabled` | Không tự kiểm tra bean; descriptor vẫn được thêm vào `enabled` |
| Trường hợp phù hợp | Contract có nhiều implementation thay thế | Feature độc lập không có contract chung |

## 5. Version và vendor được lấy từ đâu?

Trong implementation của `FeaturesEndpoint`, metadata của feature được tạo từ package của class implementation:

```java
Package implementationPackage = implementationType.getPackage();

String version = implementationPackage.getImplementationVersion();
String vendor = implementationPackage.getImplementationVendor();
```

Hai method của Java `Package` đọc manifest attributes:

- `getImplementationVersion()` đọc `Implementation-Version`.
- `getImplementationVendor()` đọc `Implementation-Vendor`.

Các thuộc tính này thường được đóng gói trong `META-INF/MANIFEST.MF` của JAR chứa class.

Ví dụ manifest có thể chứa:

```text
Manifest-Version: 1.0
Implementation-Title: Example Discovery Adapter
Implementation-Version: 5.0.3
Implementation-Vendor: Example Vendor
```

Nếu class `ConsulDiscoveryClient` nằm trong một JAR có manifest khai báo `Implementation-Version: 5.0.3`, endpoint có thể trả version tương ứng. Nếu manifest không có trường này, kết quả có thể là `null`.

### 5.1. Đây không phải phiên bản Spring Boot hoặc Spring Cloud release train

Không đồng nhất các giá trị sau:

| Thông tin | Nguồn |
| --- | --- |
| Version của implementation trong `/features` | Package metadata của class implementation |
| Spring Boot version | Dependency/runtime của Spring Boot |
| Spring Cloud release train | BOM/release train quản lý các module Spring Cloud |
| Version ứng dụng | Build metadata do ứng dụng khai báo, ví dụ `BuildProperties` hoặc `/actuator/info` |
| Version khai báo trong dependency management | POM/BOM của quá trình build |

Một ứng dụng có thể chạy Spring Boot version A, Spring Cloud release train B, trong khi implementation adapter cụ thể có version C. Ba giá trị này phục vụ những mục đích khác nhau.

Endpoint `/features` cũng không đọc toàn bộ dependency tree, `pom.xml` hoặc SBOM. Nó chỉ báo cáo những feature đã được đăng ký bằng `HasFeatures`.

### 5.2. Vì sao version/vendor có thể là `null`?

Một số nguyên nhân thường gặp:

- JAR không khai báo `Implementation-Version` hoặc `Implementation-Vendor` trong manifest.
- Quá trình đóng gói/repackage/shading làm mất hoặc không giữ manifest attributes cần thiết.
- Class được nạp từ thư mục class đã biên dịch thay vì JAR có manifest phù hợp.
- Named feature truyền class của ứng dụng nhưng artifact đó không khai báo metadata implementation.
- Abstract feature tìm được bean proxy; class runtime được trả về có package metadata khác với class target hoặc không có metadata.

Vì vậy, `null` không nhất thiết có nghĩa dependency bị thiếu hoặc implementation lỗi. Nó chỉ cho biết package metadata mà endpoint đọc không có giá trị.

Nếu cần version/vendor đáng tin cậy cho mục đích kiểm toán, hãy kết hợp endpoint với artifact manifest, dependency tree, SBOM hoặc build provenance. Không tự suy ra version từ tên class hoặc tên JAR.

## 6. Cách đăng ký feature cho module riêng

Mỗi module có thể khai báo một hoặc nhiều bean `HasFeatures`. Tài liệu Spring Cloud khuyến nghị đặt bean này trong một `@Configuration` được bảo vệ bằng điều kiện phù hợp, để chỉ công bố feature khi module tương ứng có mặt.

Ví dụ module payment có implementation `StripePaymentConnector` và muốn công bố tên, version, vendor của class đó:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import com.example.payment.StripePaymentConnector;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(StripePaymentConnector.class)
public class PaymentFeatureConfiguration {

    @Bean
    HasFeatures paymentFeatures() {
        return HasFeatures.namedFeatures(
                new NamedFeature(
                        "Payment Connector",
                        StripePaymentConnector.class
                )
        );
    }
}
```

Ở ví dụ này:

- `@ConditionalOnClass` tránh đăng ký descriptor nếu class implementation không có trên classpath.
- `NamedFeature` đặt tên hiển thị là `Payment Connector`.
- `StripePaymentConnector.class` là class mà endpoint dùng để đọc canonical name và package metadata.
- `HasFeatures.namedFeatures(...)` đóng gói descriptor để endpoint tổng hợp.

Nếu feature chỉ nên xuất hiện khi một bean đã được tạo thành công, có thể thêm điều kiện `@ConditionalOnBean` hoặc sử dụng abstract feature với contract phù hợp.

### 6.1. Đăng ký abstract feature

Giả sử module payment định nghĩa interface `PaymentConnector` và có bean `StripePaymentConnector` triển khai interface này. Có thể khai báo abstract feature theo contract:

```java
import org.springframework.cloud.client.actuator.HasFeatures;
import com.example.payment.PaymentConnector;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PaymentContractFeatureConfiguration {

    @Bean
    HasFeatures paymentFeatures() {
        return HasFeatures.abstractFeatures(PaymentConnector.class);
    }
}
```

Khi bean `PaymentConnector` tồn tại, endpoint lấy class runtime của bean, ví dụ `StripePaymentConnector`, để báo metadata. Khi không có bean, endpoint đưa `PaymentConnector` vào `disabled`.

Spring Cloud Commons đã tự khai báo một số feature của chính nó, chẳng hạn `DiscoveryClient` và `LoadBalancerClient` trong cấu hình tương ứng. Module tích hợp khác có thể bổ sung feature riêng của mình. Tránh khai báo trùng lặp không cần thiết vì endpoint tổng hợp tất cả `HasFeatures` beans và có thể trả nhiều descriptor cùng tên.

## 7. Đọc metadata trực tiếp từ class

Khi cần kiểm tra manifest trong một unit test hoặc công cụ chẩn đoán, có thể đọc package metadata bằng Java:

```java
public record ImplementationMetadata(
        String className,
        String version,
        String vendor
) {
}

public final class ImplementationMetadataReader {

    private ImplementationMetadataReader() {
    }

    public static ImplementationMetadata read(Class<?> implementationType) {
        Package implementationPackage = implementationType.getPackage();

        return new ImplementationMetadata(
                implementationType.getCanonicalName(),
                implementationPackage.getImplementationVersion(),
                implementationPackage.getImplementationVendor()
        );
    }
}
```

Cách này minh họa cùng nguồn dữ liệu mà `FeaturesEndpoint` sử dụng. Nếu cần xử lý class không có package hoặc môi trường đặc biệt, bổ sung null-check phù hợp trước khi gọi các method trên package.

Ví dụ sử dụng:

```java
ImplementationMetadata metadata =
        ImplementationMetadataReader.read(StripePaymentConnector.class);

System.out.println("Class: " + metadata.className());
System.out.println("Version: " + metadata.version());
System.out.println("Vendor: " + metadata.vendor());
```

Không nên dùng code này để tự đoán version Maven từ classpath. Nó chỉ đọc manifest metadata của package.

## 8. Bật, đọc và kiểm tra endpoint trong môi trường chạy

### 8.1. Cấu hình tối thiểu

Ứng dụng cần Actuator và Spring Cloud Commons. Sau đó expose endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,features

spring:
  cloud:
    features:
      enabled: true
```

`spring.cloud.features.enabled` mặc định là `true`, nên có thể bỏ property này nếu không cần ghi rõ. Phần quan trọng để truy cập qua HTTP là danh sách exposure có ID `features`.

### 8.2. Gọi endpoint có xác thực

Trong môi trường có authentication, dùng tài khoản chỉ có quyền đọc management endpoint:

```bash
curl -u monitor-user:REDACTED \
  http://localhost:8080/actuator/features
```

Không ghi password thật vào shell history hoặc tài liệu. Nếu management server dùng port hoặc base path riêng, thay URL cho đúng môi trường.

### 8.3. Đọc kết quả

Giả sử response có:

```json
{
  "enabled": [
    {
      "type": "org.springframework.cloud.consul.discovery.ConsulDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "5.0.3",
      "vendor": "Example Vendor"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
```

Có thể đọc theo thứ tự:

1. `name` cho biết abstraction/feature được công bố.
2. `type` cho biết class implementation được endpoint dùng để mô tả feature.
3. `version` cho biết package implementation công bố version nào.
4. `vendor` cho biết package implementation công bố vendor nào.
5. `disabled` cho biết abstract feature nào không có bean tương ứng trong context.

Ví dụ này không có nghĩa tất cả implementation Consul đều có cùng version/vendor. Hãy đối chiếu giá trị trả về với artifact thực tế của ứng dụng.

## 9. Phân biệt `/features` với các Actuator endpoint khác

Các endpoint phục vụ những câu hỏi vận hành khác nhau:

| Endpoint | Câu hỏi chính | Nội dung |
| --- | --- | --- |
| `/actuator/features` | Implementation feature nào được khai báo và metadata của nó là gì? | Feature name/type/version/vendor và danh sách abstract feature không có bean |
| `/actuator/health` | Ứng dụng hoặc dependency hiện có khỏe không? | Health status và các health contributor |
| `/actuator/info` | Ứng dụng muốn công bố thông tin gì? | Metadata do build/app cấu hình, có thể chứa build version hoặc git commit |
| `/actuator/conditions` | Vì sao một auto-configuration được áp dụng hoặc bỏ qua? | Condition evaluation report |
| `/actuator/beans` | Bean nào đang tồn tại trong context? | Danh sách bean và dependency |

`/features` không phải health check. Một implementation có thể xuất hiện trong `enabled` nhưng kết nối registry đang lỗi. Ngược lại, một health contributor có thể báo trạng thái tốt trong khi endpoint không có descriptor cho implementation đó.

Endpoint cũng không thay thế `/actuator/conditions`. Feature metadata cho biết module công bố implementation nào; condition report giải thích điều kiện auto-configuration nào match hoặc không match.

## 10. Bảo mật và vận hành

Thông tin implementation có ích cho inventory và troubleshooting nhưng cũng có thể tiết lộ cấu trúc công nghệ của ứng dụng.

Tên class, version và vendor có thể giúp người vận hành xác định artifact đang chạy. Đồng thời, chúng có thể giúp người ngoài nhận diện dependency cũ hoặc thành phần có lỗ hổng đã công bố.

Khi expose endpoint:

- Chỉ mở endpoint trên management network hoặc qua gateway quản trị.
- Bảo vệ bằng authentication và authorization phù hợp.
- Không expose toàn bộ Actuator bằng wildcard nếu không có lý do rõ ràng.
- Chỉ cấp quyền đọc endpoint cho monitoring/support role cần thiết.
- Không đưa response chứa classpath inventory lên log công khai hoặc ticket không kiểm soát.
- Đối chiếu version/vendor với dependency tree và SBOM trước khi kết luận về bản vá bảo mật.
- Theo dõi việc thay đổi implementation sau deploy để phát hiện dependency bị thay thế ngoài dự kiến.

Nếu endpoint trả `null` ở version/vendor, đừng tự điền giá trị phỏng đoán vào báo cáo. Hãy kiểm tra manifest của artifact, build pipeline hoặc SBOM để có nguồn xác thực.

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `/actuator/features` trả 404 | Chưa có Actuator, endpoint không available, bị tắt hoặc chưa expose | Kiểm tra dependency, `spring.cloud.features.enabled`, endpoint availability và web exposure |
| `features` không xuất hiện trong response | Không có `HasFeatures` bean hoặc module chưa khai báo feature | Kiểm tra module auto-configuration và điều kiện đăng ký `HasFeatures` |
| Feature nằm trong `disabled` | Abstract type đã khai báo nhưng context không có bean theo type đó | Kiểm tra starter, conditional bean, property bật module và classpath |
| Feature nằm trong `enabled` nhưng implementation không hoạt động | Named feature được khai báo metadata; endpoint không xác minh bean hoặc health | Kiểm tra bean thực tế, health indicator và kết nối dependency |
| `version` hoặc `vendor` là `null` | Manifest không có `Implementation-Version`/`Implementation-Vendor` | Kiểm tra `META-INF/MANIFEST.MF` của JAR chứa class |
| `type` là class proxy hoặc package không mong đợi | Abstract feature lấy `bean.getClass()` làm class runtime | Kiểm tra proxy strategy và metadata của target/artifact |
| Có hai feature cùng tên | Nhiều `HasFeatures` beans khai báo cùng abstraction/name | Kiểm tra các module auto-configuration đã đăng ký descriptor |
| Endpoint bị từ chối truy cập | Security rule của management endpoint | Kiểm tra role, request matcher, management port và network policy |

## 12. Quy trình xác minh implementation sau mỗi lần triển khai

1. Xác nhận phiên bản Spring Cloud Commons và starter implementation được quản lý đồng bộ qua BOM tương ứng.
2. Xác nhận Actuator có trên runtime classpath.
3. Kiểm tra `spring.cloud.features.enabled` không bị tắt.
4. Expose riêng `features` trên management interface phù hợp.
5. Gọi endpoint bằng tài khoản có quyền đọc.
6. Lưu response vào hệ thống inventory nội bộ nếu chính sách vận hành cho phép.
7. So sánh `name` và `type` với implementation mong đợi.
8. Đối chiếu `version` và `vendor` với manifest, dependency tree hoặc SBOM.
9. Nếu feature ở `disabled`, kiểm tra bean contract và điều kiện auto-configuration.
10. Nếu feature ở `enabled` nhưng dependency không hoạt động, kiểm tra health/connection riêng.
11. Lặp lại sau khi nâng cấp starter, thay provider hoặc đổi packaging pipeline.

Nên lưu lịch sử response theo release/deployment ID để có thể so sánh implementation trước và sau một lần rollout. Tránh dùng riêng version/vendor từ endpoint làm bằng chứng duy nhất về tính an toàn của dependency.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `/features` liệt kê mọi dependency trên classpath | Nó tổng hợp các feature được module khai báo qua `HasFeatures` |
| `version` là Spring Boot version | Đây là `Package.getImplementationVersion()` của class implementation |
| `vendor` là nhà cung cấp registry đang chạy | Đây là `Package.getImplementationVendor()` từ package metadata |
| `enabled` đồng nghĩa health UP | Nó chỉ phản ánh logic khai báo/lookup feature của endpoint |
| Named feature luôn kiểm tra bean có tồn tại | Named feature được thêm theo descriptor, không lookup bean như abstract feature |
| `disabled` là mọi module chưa cài | Nó chỉ liệt kê abstract feature được khai báo nhưng không tìm thấy bean theo type |
| `null` version có nghĩa JAR không được nạp | Thường chỉ có nghĩa manifest/package không công bố metadata tương ứng |
| Endpoint tự đọc Maven dependency tree | Nó không đọc POM/BOM/SBOM; chỉ dùng class và package metadata |
| Expose Actuator đồng nghĩa an toàn | Cần giới hạn network và quyền truy cập vì endpoint tiết lộ implementation inventory |

## 14. Câu hỏi tự kiểm tra

1. Spring Cloud Commons cung cấp endpoint nào để đọc feature name, type, version và vendor?
2. Endpoint trả về hai nhóm dữ liệu nào?
3. Abstract feature được xác định enabled bằng cách nào?
4. Named feature khác abstract feature ở bước kiểm tra bean nào?
5. Trường `type` được tạo từ class nào trong hai loại feature?
6. `Package.getImplementationVersion()` đọc metadata từ đâu?
7. Vì sao version của feature không nhất thiết bằng Spring Boot version?
8. Những lý do nào khiến version/vendor có giá trị `null`?
9. Vì sao feature có thể nằm trong `enabled` nhưng service vẫn không khỏe?
10. Cần bảo vệ endpoint như thế nào khi dùng trong production?

## 15. Tài liệu tham khảo chính thức

- [Spring Cloud Commons — Common Abstractions, Enabled Features](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html) — hai loại feature, nội dung endpoint và cách khai báo `HasFeatures`.
- [FeaturesEndpoint.java — Spring Cloud Commons](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/actuator/FeaturesEndpoint.java) — cách endpoint phân loại enabled/disabled và đọc package metadata.
- [CommonsClientAutoConfiguration.java — Spring Cloud Commons](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/CommonsClientAutoConfiguration.java) — điều kiện tạo endpoint và các feature Commons được đăng ký.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html) — thuộc tính `spring.cloud.features.enabled`.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — expose, access control và bảo vệ endpoint quản trị.
- [Java `Package` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Package.html) — `getImplementationVersion()` và `getImplementationVendor()`.

*Tài liệu tập trung vào metadata mà Spring Cloud Commons công bố qua Actuator. Hãy dùng `/features` như một nguồn inventory của các feature đã đăng ký, sau đó đối chiếu manifest, dependency tree và health signal khi cần kết luận về implementation đang vận hành.*
