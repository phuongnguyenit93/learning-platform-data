# Phân biệt abstract feature và named feature

Bài học thuộc chương **Khả năng hệ thống** của module **SPRING_CLOUD_CORE**. Spring Cloud Commons cung cấp endpoint Actuator `/features` để liệt kê những capability mà các module Spring Cloud công bố và cho biết chúng đang được nhận diện là enabled hay disabled trong ApplicationContext. Endpoint phân biệt hai cách mô tả capability: **abstract feature** và **named feature**.

- **Abstract feature** có một interface hoặc abstract class làm contract chung, ví dụ `DiscoveryClient`, `LoadBalancerClient` hoặc `LockService`. Endpoint tìm bean theo contract type để xác định feature có được bật hay không.
- **Named feature** không có một interface/abstract class chung đại diện cho capability. Module khai báo feature bằng tên hiển thị và một class cung cấp metadata, ví dụ Circuit Breaker, API Gateway hoặc Spring Cloud Bus.

Khác biệt này ảnh hưởng trực tiếp đến cách khai báo `HasFeatures`, cách endpoint phân loại kết quả và cách đọc báo cáo. Đặc biệt, named feature được đưa vào danh sách enabled theo khai báo `HasFeatures`; endpoint không thực hiện phép tra cứu bean giống như với abstract feature. Vì vậy, cấu hình khai báo named feature cần được đặt trong `@Configuration` có điều kiện phù hợp.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích mục đích của endpoint `/features` trong Spring Cloud Commons.
2. Phân biệt abstract feature và named feature theo contract và cách nhận diện.
3. Mô tả cách endpoint kiểm tra bean cho abstract feature.
4. Giải thích cách named feature được mô tả bằng tên và class metadata.
5. Đọc hai nhóm `enabled` và `disabled` trong response.
6. Hiểu các trường `name`, `type`, `version` và `vendor`.
7. Khai báo `HasFeatures` bằng `abstractFeatures`, `namedFeatures` hoặc builder.
8. Đặt feature declaration trong cấu hình có điều kiện đúng.
9. Bật, expose và truy vấn endpoint qua Spring Boot Actuator.
10. Nhận biết giới hạn của endpoint và không xem nó như health check hoặc feature flag runtime.
11. Viết test cho feature có bean, thiếu bean và named feature không được khai báo.
12. Dùng endpoint để hỗ trợ chẩn đoán dependency, auto-configuration và khả năng tích hợp của ứng dụng.

## 2. Vì sao cần mô tả capability của hệ thống?

Một ứng dụng Spring Cloud có thể kết hợp nhiều module: discovery, load balancing, circuit breaker, gateway, messaging hoặc bus. Chỉ nhìn dependency trong build file không đủ để biết capability nào đã thực sự được cấu hình trong ApplicationContext.

Ví dụ, dependency của Eureka có thể xuất hiện trong classpath nhưng cấu hình discovery bị loại bởi property hoặc điều kiện auto-configuration. Tương tự, một module có thể khai báo circuit breaker abstraction nhưng chưa có implementation factory phù hợp.

Endpoint `/features` cung cấp một bản kê khai do các module Spring Cloud đóng góp. Mỗi module tạo một hoặc nhiều bean `HasFeatures` để mô tả capability mà module đó cung cấp. Endpoint tổng hợp các khai báo và trả metadata cho công cụ vận hành hoặc người phát triển.

~~~mermaid
flowchart TD
    MODULES["Spring Cloud modules"] --> DECL["HasFeatures beans"]
    DECL --> ENDPOINT["FeaturesEndpoint"]
    CONTEXT["Spring ApplicationContext"] --> ENDPOINT
    ENDPOINT --> ABSTRACT["Abstract features"]
    ENDPOINT --> NAMED["Named features"]
    ABSTRACT --> LOOKUP["Lookup bean by contract type"]
    LOOKUP --> RESULT["enabled / disabled"]
    NAMED --> DECLARED["Use declared name and type metadata"]
    DECLARED --> RESULT
    RESULT --> HTTP["GET /actuator/features"]
~~~

Endpoint giúp trả lời câu hỏi: *những capability nào đã được các module công bố và endpoint nhận diện chúng ra sao?* Nó không tự kiểm tra mọi hành vi runtime của từng capability.

## 3. Abstract feature là gì?

### 3.1. Có một contract type chung

Abstract feature là capability có interface hoặc abstract class làm contract. Các implementation có thể khác nhau nhưng cùng cung cấp bean theo contract đó.

Ví dụ:

| Contract type | Capability được biểu diễn |
| --- | --- |
| `DiscoveryClient` | Truy vấn service instance từ discovery provider. |
| `LoadBalancerClient` | Chọn instance để gửi request đến dịch vụ. |
| `LockService` | Cung cấp abstraction cho distributed lock. |

Ứng dụng có thể thay Eureka bằng Consul hoặc Zookeeper mà phần code tiêu thụ `DiscoveryClient` vẫn làm việc qua contract chung. Endpoint dùng chính contract type đó để hỏi ApplicationContext xem có bean phù hợp hay không.

### 3.2. Endpoint kiểm tra bean như thế nào?

Với mỗi abstract feature được khai báo, `FeaturesEndpoint` thực hiện logic khái quát:

1. Lấy class/interface contract từ danh sách abstract features.
2. Lấy tên đơn giản của contract, ví dụ `DiscoveryClient`.
3. Gọi `ApplicationContext.getBean(contractType)` để tìm bean theo type.
4. Nếu tìm được bean, endpoint thêm feature vào danh sách `enabled`.
5. Nếu không tìm được bean theo type, endpoint thêm tên feature vào danh sách `disabled`.
6. Với feature enabled, endpoint dùng class thực tế của bean để lấy metadata package, gồm implementation version và vendor.

Đây là phép kiểm tra sự hiện diện/khả năng resolve bean trong context. Nó không gọi registry, không gửi request tới dịch vụ bên ngoài và không xác nhận mọi method của implementation đều hoạt động.

### 3.3. Ví dụ abstract feature trong Spring Cloud Commons

Spring Cloud Commons khai báo các capability chung như sau:

~~~java
@Bean
public HasFeatures commonsFeatures() {
    return HasFeatures.abstractFeatures(
            DiscoveryClient.class,
            LoadBalancerClient.class
    );
}
~~~

Nếu ApplicationContext có bean `DiscoveryClient` và `LoadBalancerClient` có thể resolve theo type, các feature tương ứng được đưa vào `enabled`. Nếu không tìm được bean cho một contract, tên contract đó xuất hiện trong `disabled`.

Trong các module khác, có thể khai báo một abstract feature riêng:

~~~java
public interface InvoiceClient {
    Invoice findById(String invoiceId);
}

@Configuration(proxyBeanMethods = false)
class InvoiceClientConfiguration {

    @Bean
    InvoiceClient invoiceClient() {
        return new HttpInvoiceClient();
    }

    @Bean
    HasFeatures invoiceClientFeature() {
        return HasFeatures.abstractFeatures(InvoiceClient.class);
    }
}
~~~

`InvoiceClient` là contract của capability. Implementation `HttpInvoiceClient` là bean thực tế được đăng ký trong context. Khi endpoint kiểm tra `InvoiceClient.class`, Spring tìm bean theo contract interface.

### 3.4. Bean vắng mặt có nghĩa là gì?

Nếu abstract feature đã được khai báo trong `HasFeatures` nhưng không có bean tương ứng, endpoint đưa tên feature vào `disabled`.

Một số nguyên nhân thường gặp:

- Provider starter chưa được thêm vào dependency.
- Auto-configuration không được kích hoạt.
- Một property đã tắt capability.
- `@ConditionalOnClass`, `@ConditionalOnBean` hoặc `@ConditionalOnProperty` không thỏa điều kiện.
- Cấu hình người dùng loại bỏ bean hoặc component scan không bao phủ cấu hình.
- Bean được khai báo theo type khác với contract được feature đăng ký.

Hãy xem `disabled` như dấu hiệu để điều tra điều kiện tạo bean. Nó không tự chỉ ra nguyên nhân chính xác.

## 4. Named feature là gì?

### 4.1. Không có một abstraction type chung

Một số capability có ý nghĩa ở cấp sản phẩm/chức năng nhưng không có một interface hoặc abstract class duy nhất để mọi implementation phải triển khai.

Spring Cloud đưa ra ví dụ:

- Circuit Breaker.
- API Gateway.
- Spring Cloud Bus.

Các capability này có thể được triển khai bằng nhiều class hoặc nhiều module khác nhau. Vì vậy, thay vì tìm một contract type chung trong ApplicationContext, module công bố feature bằng:

- Một **tên** để người đọc nhận biết capability.
- Một **class type** để cung cấp metadata về loại, version và vendor.

### 4.2. NamedFeature gồm tên và class type

Ví dụ theo cấu trúc Spring Cloud:

~~~java
new NamedFeature(
        "Spring Cloud Bus",
        ConsulBusAutoConfiguration.class
)
~~~

Tên `Spring Cloud Bus` là nhãn feature được hiển thị. `ConsulBusAutoConfiguration.class` là class được dùng làm metadata type.

Với một module ứng dụng tự phát triển, có thể khai báo:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
class PaymentGatewayFeatureConfiguration {

    @Bean
    PaymentGatewayClient paymentGatewayClient() {
        return new HttpPaymentGatewayClient();
    }

    @Bean
    HasFeatures paymentGatewayFeature() {
        return HasFeatures.namedFeatures(
                new NamedFeature(
                        "Payment Gateway",
                        PaymentGatewayFeatureConfiguration.class
                )
        );
    }
}
~~~

Khi property `app.payment.enabled=true`, cấu hình được kích hoạt và bean `HasFeatures` công bố named feature. Khi property là false hoặc không thỏa điều kiện, cấu hình không đóng góp feature declaration này.

### 4.3. Named feature được endpoint xử lý ra sao?

Khác với abstract feature, endpoint không gọi `ApplicationContext.getBean(namedFeature.getType())` để xác minh named feature.

Endpoint lấy từng `NamedFeature` đã được khai báo trong `HasFeatures` và thêm trực tiếp vào danh sách `enabled`, sử dụng:
- Tên feature từ `NamedFeature`.
- Canonical class name từ type.
- Implementation version của package chứa type.
- Implementation vendor của package chứa type.

Vì vậy, sự hiện diện của named feature trong `enabled` phản ánh rằng module đã công bố nó qua `HasFeatures`. Việc công bố đó phải được đặt trong cấu hình có điều kiện phù hợp để không báo capability enabled khi chức năng thực tế đã bị tắt.

### 4.4. Named feature không có mục disabled tự động

Endpoint không tự thêm named feature bị thiếu vào `disabled`. Nếu cấu hình không tạo bean `HasFeatures` khai báo một named feature, feature đó đơn giản không xuất hiện trong response.

Đây là khác biệt quan trọng khi đọc kết quả:

- Abstract feature đã khai báo nhưng không tìm thấy bean: có tên trong `disabled`.
- Named feature có declaration: xuất hiện trong `enabled`.
- Named feature không có declaration: không xuất hiện trong danh sách nào.

Không suy luận rằng một named feature vắng mặt trong response đồng nghĩa endpoint đã kiểm tra và xác nhận nó disabled.

## 5. So sánh abstract feature và named feature

| Tiêu chí | Abstract feature | Named feature |
| --- | --- | --- |
| Cơ sở nhận diện | Interface hoặc abstract class contract. | Tên feature và class type cung cấp metadata. |
| Ví dụ | DiscoveryClient, LoadBalancerClient, LockService. | Circuit Breaker, API Gateway, Spring Cloud Bus. |
| Khai báo | `HasFeatures.abstractFeatures(Type.class)`. | `HasFeatures.namedFeatures(new NamedFeature(name, Type.class))`. |
| Kiểm tra bean | Endpoint tìm bean theo contract type trong ApplicationContext. | Endpoint không tra bean theo named feature type. |
| Khi được xem là enabled | Có thể resolve bean theo contract type. | Có declaration trong `HasFeatures` được nạp vào endpoint. |
| Khi không enabled | Tên contract xuất hiện trong `disabled` nếu lookup không thành công. | Không có declaration thì feature không xuất hiện; endpoint không tự thêm vào `disabled`. |
| Metadata version/vendor | Lấy từ class thực tế của bean được tìm thấy. | Lấy từ class type được truyền vào `NamedFeature`. |

Hai kiểu đều được tổng hợp qua `HasFeatures` và hiển thị ở cùng endpoint. Khác biệt nằm ở cách module chứng minh capability của mình.

## 6. Đọc response của /features

### 6.1. Bật endpoint

Spring Cloud Commons cung cấp Actuator endpoint có ID `features`. Endpoint được bật mặc định khi điều kiện auto-configuration phù hợp và thuộc tính `spring.cloud.features.enabled` không bị tắt.

Thuộc tính hiện hành:

~~~yaml
spring:
  cloud:
    features:
      enabled: true
~~~

Có thể tắt việc tạo endpoint bằng:

~~~yaml
spring:
  cloud:
    features:
      enabled: false
~~~

Giá trị mặc định của `spring.cloud.features.enabled` là `true`.

### 6.2. Expose endpoint qua HTTP

Nếu ứng dụng dùng Spring Boot Actuator, thêm `features` vào danh sách endpoint được expose:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,features
~~~

Đường dẫn HTTP mặc định:

~~~text
GET /actuator/features
~~~

Nếu ứng dụng đổi `management.endpoints.web.base-path` hoặc dùng management port riêng, URL thực tế sẽ thay đổi tương ứng. Exposure chỉ quyết định endpoint có được công bố qua HTTP; vẫn cần bảo vệ bằng authentication, authorization và network policy.

### 6.3. Gọi endpoint

~~~bash
curl --request GET \
  http://localhost:8080/actuator/features
~~~

Endpoint là read-only. Nó trả danh sách feature đã được khai báo và phân loại theo khả năng nhận diện.

### 6.4. Cấu trúc response

Ví dụ response minh họa:

~~~json
{
  "enabled": [
    {
      "type": "com.example.payment.PaymentGatewayFeatureConfiguration",
      "name": "Payment Gateway",
      "version": "1.4.0",
      "vendor": "Example Team"
    },
    {
      "type": "com.example.discovery.EurekaDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "5.0.4",
      "vendor": "Broadcom"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
~~~

Ý nghĩa các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `enabled` | Danh sách feature được endpoint nhận diện là enabled. |
| `disabled` | Danh sách tên abstract feature đã khai báo nhưng không resolve được bean. |
| `name` | Tên hiển thị của feature. |
| `type` | Canonical class name của type dùng để mô tả feature. |
| `version` | Package implementation version nếu metadata có sẵn. |
| `vendor` | Package implementation vendor nếu metadata có sẵn. |

Các giá trị trong ví dụ chỉ để minh họa cấu trúc. Version và vendor thực tế phụ thuộc manifest metadata của JAR; chúng có thể là null nếu package không cung cấp thông tin đó.

### 6.5. Không nhầm version của contract với version implementation

Với abstract feature, endpoint lấy class thực tế của bean được tìm thấy rồi đọc package implementation version. Vì vậy, version được hiển thị phản ánh implementation class, không nhất thiết là version của interface contract.

Với named feature, endpoint dùng class type đã truyền vào `NamedFeature` để lấy canonical name, version và vendor. Chọn một class phù hợp với module cung cấp capability để metadata có ý nghĩa.

## 7. Khai báo HasFeatures trong module

### 7.1. Một bean có thể khai báo nhiều feature

Một module có thể công bố nhiều abstract và named feature trong một bean `HasFeatures`.

~~~java
@Bean
HasFeatures localFeatures() {
    return new HasFeatures(
            List.of(InvoiceClient.class, PricingClient.class),
            List.of(
                    new NamedFeature(
                            "Invoice Export",
                            InvoiceExportConfiguration.class
                    ),
                    new NamedFeature(
                            "Pricing Rules",
                            PricingRulesConfiguration.class
                    )
            )
    );
}
~~~

Cấu trúc này giúp module tập trung metadata feature. Nếu dùng constructor trực tiếp, truyền danh sách abstract class và danh sách named feature theo đúng thứ tự constructor của phiên bản Spring Cloud đang dùng.

### 7.2. Dùng builder

Có thể dùng builder để khai báo xen kẽ các feature:

~~~java
@Bean
HasFeatures billingFeatures() {
    return HasFeatures.builder()
            .abstractFeature(InvoiceClient.class)
            .abstractFeature(PricingClient.class)
            .namedFeature(
                    new NamedFeature(
                            "Invoice Export",
                            InvoiceExportConfiguration.class
                    )
            )
            .build();
}
~~~

Builder phù hợp khi danh sách có cả hai loại và cần thể hiện rõ từng khai báo.

### 7.3. Tách cấu hình theo module/provider

Mỗi module nên công bố feature trong cấu hình phù hợp với điều kiện của module đó:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(DiscoveryClient.class)
@ConditionalOnBean(DiscoveryClient.class)
class DiscoveryFeatureConfiguration {

    @Bean
    HasFeatures discoveryFeatures() {
        return HasFeatures.abstractFeatures(DiscoveryClient.class);
    }
}
~~~

Ví dụ này minh họa việc chỉ khai báo feature khi contract có mặt và bean tương ứng được tạo. Trong auto-configuration thực tế, có thể dùng thêm điều kiện theo property, provider, discovery mode hoặc phiên bản.

Không gom tất cả feature của mọi module vào một cấu hình luôn được bật. Điều đó dễ khiến named feature được báo enabled dù module thực tế không được kích hoạt.

## 8. Điều kiện cấu hình và tính chính xác của báo cáo

### 8.1. Abstract feature phải khớp contract bean

Khi khai báo abstract feature, chọn đúng interface/abstract class mà bean thực tế triển khai.

Ví dụ:
- Khai báo `DiscoveryClient.class` nếu muốn kiểm tra bean theo contract discovery.
- Không khai báo class implementation cụ thể nếu mục đích là xác minh abstraction chung.
- Nếu module có nhiều implementation, kiểm tra cách Spring resolve bean theo type và cấu hình primary/qualifier phù hợp.

Một abstract feature được khai báo nhưng bean không resolve được sẽ xuất hiện trong `disabled`. Hãy dùng condition report và bean inspection để tìm lý do.

### 8.2. Named feature phải được guard đúng

Named feature không được endpoint xác minh bằng bean lookup. Vì vậy, điều kiện tạo bean `HasFeatures` chính là phần quyết định feature có được công bố hay không.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.gateway",
        name = "enabled",
        havingValue = "true"
)
class GatewayFeatureConfiguration {

    @Bean
    HasFeatures gatewayFeature() {
        return HasFeatures.namedFeatures(
                new NamedFeature(
                        "API Gateway",
                        GatewayFeatureConfiguration.class
                )
        );
    }
}
~~~

Nếu property tắt gateway, cấu hình không được nạp và named feature không được công bố. Nếu cấu hình luôn được nạp, endpoint sẽ báo named feature trong `enabled` ngay cả khi một bean runtime khác đã bị tắt bằng điều kiện riêng.

### 8.3. Tách điều kiện dependency và điều kiện property

Một feature có thể cần đồng thời:
- Thư viện/provider có mặt trên classpath.
- Bean implementation được tạo.
- Property bật capability.
- Module khác cung cấp dependency cần thiết.

Có thể kết hợp điều kiện Spring Boot:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(GatewayClient.class)
@ConditionalOnBean(GatewayClient.class)
@ConditionalOnProperty(
        prefix = "app.gateway",
        name = "enabled",
        havingValue = "true"
)
class GatewayFeatureConfiguration {
    // Bean HasFeatures được khai báo tại đây.
}
~~~

Các điều kiện phải phản ánh đúng semantics của feature. Không thêm điều kiện chỉ để endpoint có kết quả đẹp; cần bảo đảm feature declaration phản ánh trạng thái cấu hình thật.

## 9. Ví dụ các feature của Spring Cloud

### 9.1. Discovery và LoadBalancer

Spring Cloud Commons khai báo abstract features cho các contract chung như `DiscoveryClient` và `LoadBalancerClient`.

Điều này giúp endpoint thể hiện các abstraction nền tảng có được resolve trong ApplicationContext hay không. Các implementation như Eureka, Consul hoặc Zookeeper có thể cung cấp bean theo contract discovery.

### 9.2. Reactive discovery và reactive LoadBalancer

Các module reactive có thể công bố contract riêng như `ReactiveDiscoveryClient` hoặc `ReactiveLoadBalancer`. Đây vẫn là abstract features vì có type chung để endpoint tìm bean.

Không nhầm blocking và reactive feature. Một ứng dụng có thể có một loại client nhưng không có loại còn lại tùy provider, dependency và điều kiện auto-configuration.

### 9.3. Circuit Breaker, API Gateway và Spring Cloud Bus

Đây là những ví dụ named feature trong tài liệu Spring Cloud Commons. Chúng đại diện capability cấp chức năng và không nhất thiết có một interface chung duy nhất để endpoint tìm bean.

Module triển khai nên công bố các named feature này trong `HasFeatures` bean được guard theo điều kiện thực tế của module.

## 10. Features endpoint khác gì health và compatibility verification?

| Cơ chế | Câu hỏi chính | Cách hoạt động |
| --- | --- | --- |
| `/actuator/features` | Capability nào được module khai báo và được endpoint nhận diện? | Tổng hợp `HasFeatures`; abstract feature dùng bean lookup, named feature dùng declaration. |
| Health indicator | Thành phần có đang khỏe hoặc truy cập được không? | Gọi health contributor/probe và tổng hợp trạng thái. |
| Compatibility verifier | Spring Boot version có tương thích với Spring Cloud release train không? | Kiểm tra version và báo lỗi nếu cấu hình không tương thích. |
| Application startup condition | Auto-configuration có được kích hoạt không? | Đánh giá classpath, bean, property và các condition. |

Ví dụ, `DiscoveryClient` có thể xuất hiện trong `enabled` vì bean tồn tại, nhưng registry từ xa có thể đang không truy cập được. Health indicator mới là thành phần phù hợp để kiểm tra khả năng truy vấn discovery theo cách provider hỗ trợ.

Tương tự, endpoint features không xác nhận request đi qua LoadBalancer thành công, circuit breaker có đang mở hay API Gateway route có hoạt động đúng. Hãy kết hợp feature inventory với health, metrics, logs và integration tests.

## 11. Bảo vệ và sử dụng endpoint trong vận hành

Endpoint `/features` là read-only, nhưng response vẫn có thể tiết lộ:
- Tên module và capability nội bộ.
- Canonical class name.
- Version của implementation.
- Vendor metadata.
- Sự hiện diện hoặc vắng mặt của một số integration.

Chỉ expose endpoint ở môi trường và mạng phù hợp. Trong production:
1. Chỉ thêm `features` vào actuator exposure nếu đội vận hành thực sự cần.
2. Bảo vệ endpoint bằng authentication và authorization.
3. Giới hạn truy cập qua management network hoặc network policy.
4. Không public tất cả actuator endpoints chỉ để đọc features.
5. Không dùng response làm danh sách quyền truy cập hoặc quyết định bảo mật.
6. Kiểm soát việc công bố tên class nếu metadata nội bộ cần được giữ kín.

Ví dụ cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,features
~~~

Nếu muốn tắt hẳn endpoint ở một profile:

~~~yaml
spring:
  cloud:
    features:
      enabled: false
~~~

Tắt endpoint chỉ làm mất khả năng truy vấn feature inventory qua Actuator; nó không tự tắt các capability như discovery hoặc load balancing.

## 12. Kiểm thử abstract và named feature

### 12.1. Kiểm thử abstract feature có bean

Chuẩn bị một interface và bean implementation:

~~~java
public interface StockQuery {
    int available(String sku);
}

@Component
class DefaultStockQuery implements StockQuery {
    @Override
    public int available(String sku) {
        return 10;
    }
}
~~~

Khai báo feature:

~~~java
@Bean
HasFeatures stockFeatures() {
    return HasFeatures.abstractFeatures(StockQuery.class);
}
~~~

Sau khi context khởi động, gọi `/actuator/features` và xác minh `StockQuery` nằm trong `enabled`.

### 12.2. Kiểm thử abstract feature thiếu bean

Giữ khai báo `HasFeatures` nhưng không tạo bean `StockQuery`. Kết quả mong đợi là tên `StockQuery` nằm trong `disabled`.

Test này giúp xác minh endpoint thực hiện lookup theo contract type.

### 12.3. Kiểm thử named feature có điều kiện

Tạo named feature trong cấu hình có `@ConditionalOnProperty`. Chạy hai context:

| Cấu hình | Kết quả mong đợi |
| --- | --- |
| `app.payment.enabled=true` | Named feature `Payment Gateway` xuất hiện trong `enabled`. |
| `app.payment.enabled=false` | Declaration không được nạp; feature không xuất hiện trong `enabled` hoặc `disabled`. |

Kết quả thứ hai rất quan trọng: named feature không có declaration không tự được thêm vào `disabled`.

### 12.4. Kiểm thử HTTP endpoint

Ví dụ test Spring Boot với Actuator endpoint đã expose:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "management.endpoints.web.exposure.include=features"
)
class FeaturesEndpointIntegrationTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void featuresEndpointReturnsEnabledAndDisabledGroups() {
        ResponseEntity<Map> response =
                restTemplate.getForEntity("/actuator/features", Map.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .containsKeys("enabled", "disabled");
    }
}
~~~

Đây là khung integration test. Bổ sung assertion cho tên feature và type theo fixture của ứng dụng. Nếu endpoint được bảo vệ bằng Spring Security, cấu hình test principal có quyền đọc actuator endpoint.

### 12.5. Ma trận kiểm thử

| ID | Tình huống | Kết quả cần xác minh |
| --- | --- | --- |
| F1 | Abstract feature có bean đúng contract. | Feature nằm trong `enabled`. |
| F2 | Abstract feature được khai báo nhưng thiếu bean. | Tên contract nằm trong `disabled`. |
| F3 | Named feature được khai báo trong HasFeatures. | Feature nằm trong `enabled`. |
| F4 | Named feature configuration bị tắt bằng property. | Feature không xuất hiện trong hai danh sách. |
| F5 | Named feature type có package metadata. | `type`, `version` và `vendor` phản ánh class đã khai báo. |
| F6 | Package không có implementation version/vendor. | Metadata tương ứng có thể null. |
| F7 | `spring.cloud.features.enabled=false`. | Features endpoint không được auto-configure. |
| F8 | Endpoint chưa được HTTP exposure. | URL không truy cập được qua HTTP dù endpoint có thể tồn tại trong context. |
| F9 | Principal không có quyền. | Security policy từ chối request. |
| F10 | Discovery bean tồn tại nhưng registry ngừng hoạt động. | Feature có thể vẫn enabled; health/registry test mới phát hiện lỗi kết nối. |

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/actuator/features` trả 404. | Actuator thiếu, endpoint chưa được expose hoặc `spring.cloud.features.enabled=false`. | Kiểm tra dependency, exposure và property. |
| Feature abstraction nằm trong disabled. | Không có bean resolve được theo contract type. | Kiểm tra starter, condition report, component scan và bean type. |
| Abstract feature có implementation nhưng vẫn disabled. | Bean được đăng ký dưới type khác, nhiều bean gây lookup không xác định hoặc proxy/configuration không đúng. | Kiểm tra bean theo contract type và cách resolve trong ApplicationContext. |
| Named feature xuất hiện enabled dù service chưa hoạt động. | `HasFeatures` declaration luôn được tạo, không guard theo điều kiện capability. | Đưa declaration vào cấu hình có điều kiện đúng. |
| Named feature không xuất hiện trong disabled khi property tắt. | Named feature không được khai báo nên endpoint không có mục để đánh dấu disabled. | Đây là hành vi mong đợi; kiểm tra điều kiện tạo HasFeatures bean. |
| Version hoặc vendor là null. | JAR/package không có Implementation-Version hoặc Implementation-Vendor metadata. | Kiểm tra manifest/build packaging; không coi null là lỗi endpoint. |
| Feature bị lặp trong response. | Nhiều HasFeatures bean khai báo cùng một feature hoặc nhiều module công bố tên trùng. | Rà soát declaration và thống nhất owner/name. |
| Endpoint có feature nhưng request thật thất bại. | Feature inventory chỉ kiểm tra bean/declaration, không kiểm tra toàn bộ hành vi. | Kiểm tra health indicator, logs, metrics và integration tests. |
| Tắt endpoint nhưng discovery vẫn hoạt động. | `spring.cloud.features.enabled` chỉ tắt feature inventory endpoint. | Dùng công tắc discovery riêng nếu mục tiêu là tắt discovery. |
| Endpoint tồn tại trong context nhưng HTTP 404. | Chưa expose Actuator endpoint qua web. | Bổ sung `features` vào management exposure. |
| Response tiết lộ class nội bộ. | Endpoint được expose rộng hoặc thiếu security policy. | Giới hạn management network và quyền truy cập. |

## 14. Nguyên tắc triển khai

1. **Chọn đúng loại feature.** Có contract interface/abstract class thì dùng abstract feature; capability không có contract chung thì dùng named feature.
2. **Dùng contract ổn định.** Abstract feature nên trỏ đến interface mà consumer thực sự phụ thuộc, không trỏ tùy tiện đến implementation class.
3. **Guard named feature.** Chỉ tạo HasFeatures declaration khi capability thực sự được kích hoạt.
4. **Chọn type metadata có ý nghĩa.** Named feature type nên thuộc module cung cấp capability để version/vendor phản ánh đúng nguồn.
5. **Không suy luận quá mức từ response.** Enabled không đồng nghĩa remote dependency đang khỏe; absent không đồng nghĩa đã được endpoint kiểm tra disabled.
6. **Đọc hai danh sách riêng.** Abstract feature có thể xuất hiện trong enabled hoặc disabled; named feature được khai báo sẽ xuất hiện trong enabled.
7. **Kiểm tra manifest metadata.** Version/vendor phụ thuộc package implementation metadata.
8. **Kết hợp health và metrics.** Dùng công cụ phù hợp để kiểm tra kết nối, latency và lỗi runtime.
9. **Giới hạn endpoint.** Features có thể tiết lộ thông tin về cấu trúc ứng dụng.
10. **Đối chiếu release train.** Kiểm tra API HasFeatures, NamedFeature và auto-configuration theo Spring Cloud version thực tế.

## 15. Checklist hoàn thành

- [ ] Giải thích được mục đích của Spring Cloud Features endpoint.
- [ ] Biết endpoint ID là `features` và HTTP path mặc định là `/actuator/features`.
- [ ] Phân biệt abstract feature có interface/abstract class contract.
- [ ] Phân biệt named feature được mô tả bằng name và type.
- [ ] Hiểu abstract feature được endpoint kiểm tra bằng bean lookup theo type.
- [ ] Hiểu named feature được thêm vào enabled từ HasFeatures declaration.
- [ ] Biết abstract feature thiếu bean có thể xuất hiện trong disabled.
- [ ] Biết named feature không có declaration không tự xuất hiện trong disabled.
- [ ] Đọc được enabled, disabled, name, type, version và vendor.
- [ ] Hiểu version/vendor của abstract feature lấy từ runtime bean class.
- [ ] Hiểu version/vendor của named feature lấy từ class type đã khai báo.
- [ ] Khai báo HasFeatures bằng abstractFeatures, namedFeatures hoặc builder.
- [ ] Đặt named feature declaration trong cấu hình có điều kiện.
- [ ] Bật/tắt endpoint bằng spring.cloud.features.enabled.
- [ ] Expose endpoint qua Actuator và bảo vệ bằng security policy.
- [ ] Phân biệt features endpoint với health indicator và compatibility verifier.
- [ ] Có test cho abstract enabled/disabled và named feature có/không có declaration.
- [ ] Không dùng feature inventory làm bằng chứng duy nhất về sức khỏe runtime.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): Enabled Features, abstract/named feature và cách khai báo HasFeatures.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): thuộc tính `spring.cloud.features.enabled` và giá trị mặc định.
- [Spring Cloud Commons – FeaturesEndpoint source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/actuator/FeaturesEndpoint.java): cách endpoint tìm bean cho abstract feature và thêm named feature vào response.
- [Spring Cloud Commons – FeaturesEndpoint tests](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/test/java/org/springframework/cloud/client/actuator/FeaturesEndpointTests.java): ví dụ kiểm thử enabled và disabled feature.

Endpoint, metadata và auto-configuration có thể thay đổi theo release train. Hãy kiểm tra Spring Cloud BOM đang dùng, xác minh các HasFeatures declaration và đọc response thực tế của endpoint trong môi trường kiểm thử.
