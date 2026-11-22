# Đối chiếu bean thực tế với thông tin được công bố

Một ứng dụng Spring Cloud có thể có thư viện discovery, load balancer, circuit breaker hoặc bus trên classpath. Tuy nhiên, dependency có mặt không đồng nghĩa tính năng đã được cấu hình và tạo bean trong ApplicationContext. Một capability cũng có thể được module công bố trong metadata dù thành phần runtime tương ứng chưa tồn tại.

Spring Cloud Commons cung cấp Actuator endpoint **Features** để tổng hợp các tính năng do module khai báo. Endpoint trả về hai nhóm enabled và disabled cùng metadata như tên, kiểu, phiên bản và nhà cung cấp. Muốn đọc kết quả chính xác, cần hiểu cách endpoint đối chiếu từng loại feature với ApplicationContext: **abstract feature** được kiểm tra bằng bean lookup theo kiểu; **named feature** được công bố trực tiếp từ metadata đã khai báo.

Bài học thuộc chương **Khả năng hệ thống** của **SPRING_CLOUD_CORE**. Trọng tâm là dùng endpoint Features để kiểm tra khả năng đã khai báo, đối chiếu với bean thực tế qua Actuator beans và điều kiện auto-configuration qua conditions, từ đó tìm ra trường hợp thiếu bean, metadata khai báo sai hoặc tính năng chưa thực sự hoạt động.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mục đích và cấu trúc kết quả của Spring Cloud Features endpoint.
2. Phân biệt abstract feature với named feature.
3. Mô tả cách FeaturesEndpoint tìm bean cho abstract feature.
4. Giải thích vì sao named feature có thể xuất hiện trong enabled dù bean tương ứng không tồn tại.
5. Khai báo HasFeatures và NamedFeature trong cấu hình Spring phù hợp.
6. Hiểu nguồn gốc của các trường type, version và vendor.
7. Phân biệt classpath, auto-configuration, bean trong context và khả năng vận hành thực tế.
8. Đối chiếu features với các endpoint beans, conditions và health.
9. Chẩn đoán kết quả disabled, feature bị thiếu hoặc metadata không chính xác.
10. Viết kiểm thử xác nhận thông tin được công bố phản ánh đúng trạng thái bean.

## 2. Vì sao cần đối chiếu feature với bean?

Giả sử một ứng dụng có dependency cho service discovery. Build thành công và class EurekaDiscoveryClient có trong classpath. Nhưng cấu hình discovery bị tắt hoặc điều kiện auto-configuration không thỏa mãn, nên không có bean discovery client trong context.

Nếu chỉ kiểm tra dependency, nhóm vận hành có thể kết luận service discovery đã sẵn sàng. Trong khi đó, ứng dụng không có bean để truy vấn danh sách service.

Một tình huống khác: module tự khai báo NamedFeature("Inventory Bus", InventoryBusConfiguration.class). Nếu cấu hình khai báo HasFeatures vẫn được tạo dù bus runtime không được bật, endpoint có thể công bố feature trong danh sách enabled dù bean xử lý bus không tồn tại.

Khi kiểm tra khả năng hệ thống cần phân biệt bốn lớp:

| Lớp | Câu hỏi | Công cụ hoặc nguồn kiểm tra |
| --- | --- | --- |
| Classpath | Thư viện hoặc class có trong ứng dụng không? | Dependency tree, classpath |
| Auto-configuration | Điều kiện tạo cấu hình có thỏa mãn không? | /actuator/conditions |
| ApplicationContext | Bean cần thiết có thực sự tồn tại không? | /actuator/beans, bean lookup |
| Runtime capability | Thành phần có kết nối và hoạt động đúng không? | Health indicator, metrics, integration test |

Features endpoint nằm giữa lớp khai báo tính năng và bean trong context. Nó hữu ích để kiểm tra metadata của Spring Cloud, nhưng không thay thế việc kiểm tra sức khỏe và hành vi của hệ thống.

## 3. Features endpoint của Spring Cloud Commons

Spring Cloud Commons cung cấp endpoint có ID features. Theo mặc định của Spring Boot Actuator, nếu dùng web exposure và không đổi management base path, URL thường là:

```http
GET /actuator/features
```

Tài liệu Spring Cloud thường gọi ngắn là /features vì đó là endpoint ID. Đường dẫn HTTP đầy đủ được tạo theo quy tắc của Actuator. Nếu ứng dụng đổi management.endpoints.web.base-path, đường dẫn cũng thay đổi tương ứng.

Endpoint trả về hai nhóm:

- enabled: danh sách feature được công bố là đã bật.
- disabled: tên các abstract feature được khai báo nhưng không tìm thấy bean phù hợp.

Một response minh họa:

```json
{
  "enabled": [
    {
      "type": "com.example.discovery.EurekaDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "5.0.4",
      "vendor": "Example Vendor"
    },
    {
      "type": "com.example.bus.InventoryBusConfiguration",
      "name": "Inventory Bus",
      "version": "5.0.4",
      "vendor": "Example Vendor"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
```

Đây là JSON minh họa cấu trúc, không phải kết quả cố định của mọi ứng dụng. Số lượng feature và giá trị metadata phụ thuộc các bean HasFeatures do những module có trong context cung cấp.

### 3.1. Endpoint không quét toàn bộ classpath

Features endpoint không tự động liệt kê mọi thư viện có trong dependency. Các module phải khai báo feature thông qua bean HasFeatures. Endpoint chỉ tổng hợp các khai báo mà nó nhận được.

Điều đó có nghĩa:

- Một thư viện có trong classpath nhưng không khai báo HasFeatures có thể không xuất hiện trong kết quả.
- Một abstract feature được khai báo nhưng bean không tồn tại sẽ xuất hiện trong disabled.
- Một named feature được khai báo sẽ được thêm vào enabled theo metadata.
- Nếu cấu hình công bố HasFeatures không được nạp, feature có thể không xuất hiện ở cả hai nhóm.

Không nên diễn giải việc feature không xuất hiện là chắc chắn không có dependency hoặc bean. Hãy kiểm tra cấu hình công bố feature và bean registry.

## 4. Điều kiện để endpoint được tạo và truy cập

Features endpoint được tích hợp với Spring Boot Actuator. Trong Spring Cloud Commons hiện hành, cấu hình endpoint được tạo khi các điều kiện liên quan được thỏa mãn:

1. API Actuator endpoint có mặt trên classpath.
2. Thuộc tính spring.cloud.features.enabled không bị đặt thành false.
3. Endpoint được Spring Boot xem là available theo điều kiện Actuator.
4. Cấu hình exposure và quyền truy cập cho phép client gọi endpoint qua kênh mong muốn.

Thuộc tính spring.cloud.features.enabled mặc định là true. Có thể tắt riêng việc tạo endpoint:

```yaml
spring:
  cloud:
    features:
      enabled: false
```

Thuộc tính này chỉ điều khiển Features endpoint. Nó không tắt tất cả các tính năng discovery, load balancing hoặc circuit breaker trong ứng dụng.

### 4.1. Expose endpoint qua HTTP

Spring Boot chỉ expose endpoint health qua HTTP theo mặc định trong các cấu hình Actuator hiện hành. Để truy cập Features endpoint và các endpoint hỗ trợ đối chiếu, có thể cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - features
          - beans
          - conditions
```

Chỉ expose những endpoint cần thiết cho môi trường vận hành. beans và conditions cung cấp thông tin nội bộ về cấu trúc ứng dụng, vì vậy cần giới hạn network, xác thực và phân quyền phù hợp. Nếu management base path hoặc management port được tùy chỉnh, hãy sử dụng URL tương ứng với cấu hình thực tế.

### 4.2. Phân biệt endpoint không được tạo và endpoint chưa được expose

Nếu gọi /actuator/features nhận HTTP 404, chưa thể kết luận feature bị disabled. Có thể xảy ra một trong các trường hợp:

- Spring Cloud Commons không tạo Features endpoint vì thiếu Actuator API.
- spring.cloud.features.enabled=false.
- Endpoint không available theo cấu hình access của Actuator.
- Endpoint chưa được expose qua HTTP.
- Management base path hoặc port khác với URL đang gọi.
- Security hoặc gateway che giấu endpoint bằng response không cho biết nguyên nhân.

Hãy kiểm tra cấu hình Actuator, điều kiện auto-configuration và log khởi động trước khi kết luận.

## 5. Hai loại feature: abstract và named

Spring Cloud Commons phân loại feature thành hai loại. Cách phân loại quyết định việc endpoint có kiểm tra bean thực tế hay chỉ công bố metadata.

| Loại | Dữ liệu khai báo | Cách endpoint xử lý | Kết quả |
| --- | --- | --- | --- |
| Abstract feature | Một interface hoặc abstract class | Tìm bean theo kiểu trong ApplicationContext | Có bean thì enabled; không tìm được bean thì disabled |
| Named feature | Tên hiển thị và một class đại diện | Thêm trực tiếp metadata vào enabled | Không thực hiện bean lookup cho class được khai báo |

Ví dụ, DiscoveryClient phù hợp với abstract feature vì nó là abstraction mà ứng dụng có thể có một bean triển khai. Một capability như Spring Cloud Bus có thể được công bố dưới dạng named feature, dùng tên dễ hiểu và class cấu hình đại diện.

### 5.1. Abstract feature

Một module khai báo:

```java
@Bean
HasFeatures commonsFeatures() {
    return HasFeatures.abstractFeatures(
        DiscoveryClient.class,
        LoadBalancerClient.class
    );
}
```

Khi endpoint được gọi, nó lấy từng class trong danh sách abstract features và tìm bean tương ứng trong ApplicationContext. Nếu tìm thấy bean, endpoint lấy class thực tế của object rồi đưa feature vào enabled. Nếu lookup ném NoSuchBeanDefinitionException, tên đơn giản của kiểu khai báo được đưa vào disabled.

Ví dụ:

- DiscoveryClient.class được khai báo.
- Context có bean triển khai EurekaDiscoveryClient.
- Endpoint công bố feature tên DiscoveryClient trong enabled.
- Trường type dùng tên lớp triển khai thực tế EurekaDiscoveryClient.

Nếu context không có bean nào phù hợp với LoadBalancerClient.class, endpoint thêm LoadBalancerClient vào disabled.

### 5.2. Named feature

Module có thể khai báo:

```java
@Bean
HasFeatures inventoryBusFeatures() {
    return HasFeatures.namedFeatures(
        new NamedFeature(
            "Inventory Bus",
            InventoryBusConfiguration.class
        )
    );
}
```

Endpoint thêm named feature vào enabled bằng metadata của NamedFeature. Nó không gọi ApplicationContext.getBean(InventoryBusConfiguration.class) để xác nhận có bean hay không.

Vì vậy, named feature cần được khai báo trong một cấu hình có điều kiện phù hợp với tính năng thực tế. Nếu bean HasFeatures tồn tại trong khi feature bị tắt, endpoint vẫn có thể công bố named feature là enabled.

Đây là khác biệt quan trọng nhất khi đối chiếu thông tin được công bố với bean thực tế.

## 6. Cách FeaturesEndpoint xử lý abstract feature

Implementation hiện hành thực hiện logic khái quát sau:

```java
private void addAbstractFeature(
        Features features,
        Class<?> type) {

    String featureName = type.getSimpleName();

    try {
        Object bean = this.context.getBean(type);
        Class<?> beanClass = bean.getClass();

        addFeature(
            features,
            new NamedFeature(featureName, beanClass)
        );
    }
    catch (NoSuchBeanDefinitionException ex) {
        features.getDisabled().add(featureName);
    }
}
```

Đây là đoạn mã rút gọn để giải thích luồng xử lý; tên biến và chi tiết lớp có thể khác theo phiên bản.

Có ba điều cần chú ý:

1. Lookup dùng kiểu được khai báo trong abstract feature.
2. Tên feature trong response lấy từ type.getSimpleName(), không lấy từ tên bean trong registry.
3. Metadata class được tạo từ bean.getClass(), tức class của object được tìm thấy.

### 6.1. Một bean có thể đại diện cho abstract feature

Ví dụ:

```java
public interface InventoryClient {
    InventoryItem findById(String id);
}

@Component
class HttpInventoryClient implements InventoryClient {

    @Override
    public InventoryItem findById(String id) {
        // Gọi inventory service.
        return null;
    }
}
```

Khai báo feature:

```java
@Bean
HasFeatures inventoryFeatures() {
    return HasFeatures.abstractFeatures(InventoryClient.class);
}
```

Nếu context có một bean phù hợp với InventoryClient, endpoint có thể công bố:

- name: InventoryClient.
- type: class thực tế của bean, ví dụ HttpInventoryClient.
- version/vendor: metadata package của class thực tế đó.

### 6.2. Nhiều bean cùng implement một kiểu

ApplicationContext.getBean(Class) cần tìm được một bean phù hợp duy nhất. Nếu có nhiều bean cùng implement interface mà không có lựa chọn primary rõ ràng, Spring có thể ném NoUniqueBeanDefinitionException.

Trong Spring Framework, NoUniqueBeanDefinitionException kế thừa NoSuchBeanDefinitionException. Vì implementation FeaturesEndpoint bắt NoSuchBeanDefinitionException, trường hợp lookup không đơn nhất cũng có thể bị đưa vào disabled dù thực tế có nhiều bean phù hợp.

Khi thấy abstract feature ở disabled nhưng endpoint beans cho thấy có nhiều implementation, hãy kiểm tra:

- Có bao nhiêu bean cùng kiểu.
- Có bean nào được đánh dấu @Primary không.
- Có cần khai báo một abstraction khác cụ thể hơn không.
- Cấu hình feature có đang mô tả đúng contract cần kiểm tra không.

Không nên vội kết luận thư viện chưa được nạp khi nguyên nhân thực tế là bean lookup không đơn nhất.

## 7. Cách NamedFeature được công bố

Với named feature, endpoint sử dụng tên và class được truyền trong NamedFeature:

```java
private void addFeature(
        Features features,
        NamedFeature feature) {

    Class<?> type = feature.getType();

    features.getEnabled().add(
        new Feature(
            feature.getName(),
            type.getCanonicalName(),
            type.getPackage().getImplementationVersion(),
            type.getPackage().getImplementationVendor()
        )
    );
}
```

Không có bước truy vấn bean trong đoạn xử lý này. Class được truyền vào chủ yếu cung cấp kiểu và metadata package cho thông tin công bố.

Ví dụ:

```java
@Bean
HasFeatures paymentFeatures() {
    return HasFeatures.namedFeatures(
        new NamedFeature(
            "Payment Integration",
            PaymentAutoConfiguration.class
        )
    );
}
```

Nếu paymentFeatures được tạo, endpoint sẽ đưa Payment Integration vào enabled. Việc bean PaymentClient có tồn tại hay không phải được bảo đảm bởi điều kiện cấu hình phù hợp hoặc kiểm tra riêng.

### 7.1. Guard named feature bằng điều kiện giống feature thật

Một cách khai báo tốt:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(PaymentClient.class)
@ConditionalOnProperty(
    prefix = "app.payment",
    name = "enabled",
    havingValue = "true"
)
class PaymentFeatureMetadataConfiguration {

    @Bean
    HasFeatures paymentFeatures() {
        return HasFeatures.namedFeatures(
            new NamedFeature(
                "Payment Integration",
                PaymentAutoConfiguration.class
            )
        );
    }
}
```

Cấu hình metadata nên được bật cùng điều kiện với integration mà nó mô tả. Nếu feature còn phụ thuộc một bean khác, hãy đưa điều kiện bean vào đúng cấu hình hoặc tổ chức auto-configuration để metadata và integration có cùng lifecycle.

### 7.2. Khi nào nên chọn abstract, khi nào chọn named?

| Nhu cầu | Kiểu nên dùng |
| --- | --- |
| Muốn xác nhận một bean contract có mặt trong context | Abstract feature |
| Muốn công bố một capability có tên thân thiện, không có một interface bean duy nhất | Named feature |
| Có một interface đại diện rõ ràng cho integration | Abstract feature |
| Một nhóm auto-configuration tạo nhiều bean và cần một nhãn tổng hợp | Named feature, được guard theo điều kiện của nhóm |
| Cần chứng minh component đang kết nối thành công | Health check hoặc integration test, không chỉ Features endpoint |

Không chọn named feature chỉ để tránh bean lookup nếu mục tiêu thật sự là xác nhận bean tồn tại. Ngược lại, không dùng abstract feature cho một capability không có một kiểu bean đại diện phù hợp.

## 8. Hiểu các trường metadata

Features endpoint công bố bốn trường trong mỗi phần tử enabled:

| Trường | Nguồn | Cách diễn giải |
| --- | --- | --- |
| name | Abstract: simple name của kiểu khai báo; Named: tên do module đặt | Nhãn hiển thị |
| type | Abstract: class thực tế của bean; Named: class được truyền vào NamedFeature | Kiểu Java đại diện |
| version | type.getPackage().getImplementationVersion() | Implementation version trong package metadata |
| vendor | type.getPackage().getImplementationVendor() | Implementation vendor trong package metadata |

### 8.1. Version không nhất thiết là version của toàn bộ ứng dụng

Trường version lấy từ package của class được dùng trong metadata. Nó không phải:

- Phiên bản Spring Boot của toàn ứng dụng.
- Phiên bản Spring Cloud release train.
- Phiên bản dependency được khai báo trong build file.
- Phiên bản image/container đang chạy.

Với abstract feature, class được dùng là class thực tế trả về từ bean lookup. Với named feature, class được dùng là class đã truyền vào NamedFeature.

### 8.2. Version hoặc vendor có thể null

Package.getImplementationVersion() và getImplementationVendor() đọc thông tin package metadata, thường đến từ manifest của JAR. Nếu package không có trường tương ứng, kết quả có thể là null.

Điều này thường gặp khi chạy từ output thư mục build, môi trường test hoặc artifact không đóng gói manifest metadata như mong đợi. Không nên coi version null là bằng chứng bean không tồn tại.

Khi cần xác định chính xác dependency version, hãy đối chiếu dependency tree, artifact metadata hoặc SBOM. Features endpoint cung cấp thông tin thuận tiện để chẩn đoán, không phải nguồn kiểm kê dependency đầy đủ.

### 8.3. Proxy có thể ảnh hưởng class được công bố

Bean có thể được bọc bằng proxy do AOP, transaction, refresh scope hoặc cơ chế khác. Khi endpoint gọi bean.getClass(), class quan sát được có thể là proxy class.

Trong trường hợp đó, trường type và package metadata có thể phản ánh class proxy thay vì class triển khai gốc mà người đọc mong đợi. Nếu version/vendor không rõ ràng, hãy xem bean trong endpoint beans, kiểm tra proxy target bằng công cụ phù hợp hoặc log class thực tế trong test.

## 9. Đăng ký HasFeatures trong module

Một module có thể khai báo nhiều bean HasFeatures. Spring Cloud Commons sử dụng danh sách này để tổng hợp response.

Ví dụ cho một module tự xây dựng:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(InventoryClient.class)
class InventoryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    InventoryClient inventoryClient() {
        return new DefaultInventoryClient();
    }

    @Bean
    HasFeatures inventoryFeatures() {
        return HasFeatures.abstractFeatures(
            InventoryClient.class
        );
    }
}
```

Cả bean nghiệp vụ và bean metadata nằm trong cùng một cấu hình được guard bởi classpath condition. Khi cấu hình được nạp, feature được khai báo; endpoint tiếp tục kiểm tra bean contract trong ApplicationContext.

Với module có nhiều integration độc lập, có thể tách từng nhóm metadata để mỗi nhóm có điều kiện riêng. Không nên gom mọi capability vào một bean HasFeatures không điều kiện nếu một số integration có thể bị tắt theo môi trường.

### 9.1. Ví dụ kết hợp abstract và named

```java
@Bean
HasFeatures applicationFeatures() {
    return HasFeatures.builder()
        .abstractFeature(InventoryClient.class)
        .abstractFeature(PaymentClient.class)
        .namedFeature(
            new NamedFeature(
                "Event Publishing",
                EventPublisherAutoConfiguration.class
            )
        )
        .build();
}
```

Trong ví dụ:

- InventoryClient được đối chiếu với bean thực tế.
- PaymentClient được đối chiếu với bean thực tế.
- Event Publishing được công bố theo metadata named feature.

Nếu một module chỉ bật inventory nhưng tắt payment, cần bảo đảm cấu hình HasFeatures và danh sách feature phản ánh được trạng thái mong muốn. Nếu cùng khai báo cả hai abstract features, payment sẽ xuất hiện trong disabled khi bean không có.

## 10. Đối chiếu với endpoint beans

Endpoint /actuator/beans cung cấp danh sách bean của ApplicationContext. Đây là nơi kiểm tra tên bean, kiểu bean và context chứa bean.

Có thể expose hai endpoint để đối chiếu:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features
          - beans
```

Quy trình:

1. Gọi /actuator/features và ghi lại feature đang enabled/disabled.
2. Gọi /actuator/beans và tìm kiểu hoặc tên bean tương ứng.
3. Với abstract feature ở disabled, kiểm tra có bean nào assignable với kiểu được khai báo không.
4. Với named feature ở enabled, xác nhận cấu hình metadata đã được guard đúng và bean nghiệp vụ thực tế có mặt.
5. Kiểm tra bean có nằm trong context con hay parent context phù hợp với nơi endpoint đang chạy hay không.

beans hiển thị tên và kiểu bean, còn features cung cấp nhãn capability. Hai endpoint trả lời các câu hỏi khác nhau nên cần đọc kết hợp.

### 10.1. Bean nằm trong child ApplicationContext

Một số hệ thống Spring Cloud tạo child context riêng, ví dụ context theo service ID trong LoadBalancer hoặc named context. Endpoint features đang chạy trong một ApplicationContext cụ thể.

Nếu bean nằm trong context con nhưng không được nhìn thấy từ context chứa FeaturesEndpoint, hoặc ngược lại, kết quả lookup có thể khác với kỳ vọng. Hãy kiểm tra context ownership và quan hệ parent-child khi chẩn đoán bean không xuất hiện.

## 11. Đối chiếu với endpoint conditions

Endpoint /actuator/conditions hiển thị các điều kiện auto-configuration đã được đánh giá và lý do match hoặc không match.

Khi abstract feature ở disabled:

1. Xem class cấu hình nào dự kiến tạo bean.
2. Tìm class đó trong conditions.
3. Kiểm tra @ConditionalOnClass, @ConditionalOnBean, @ConditionalOnProperty và các condition khác.
4. Đối chiếu property thực tế với profile và property source đang hoạt động.
5. Kiểm tra auto-configuration có bị exclude hoặc thứ tự cấu hình ảnh hưởng không.

Ví dụ, class của discovery client có thể nằm trong classpath nhưng @ConditionalOnProperty("spring.cloud.discovery.enabled") không match. Khi đó auto-configuration có thể không đăng ký bean DiscoveryClient.

Features endpoint cho biết contract bị thiếu trong context; conditions endpoint giúp giải thích vì sao auto-configuration không tạo bean.

## 12. Đối chiếu với health và khả năng vận hành

Một bean tồn tại không đồng nghĩa capability hoạt động tốt. Ví dụ, DiscoveryClient bean có thể được tạo thành công nhưng registry đang không truy cập được.

Hãy phân biệt:

| Công cụ | Xác minh điều gì? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| /actuator/features | Feature đã được khai báo; abstract feature có bean lookup thành công | Kết nối ngoài hoặc nghiệp vụ hoạt động |
| /actuator/beans | Bean hiện diện trong context và kiểu bean | Bean có thể phục vụ request thành công |
| /actuator/conditions | Lý do condition của auto-configuration match/không match | Runtime dependency khỏe |
| /actuator/health | Trạng thái của health contributors đã cấu hình | Mọi feature đều được công bố hoặc mọi đường nghiệp vụ đều thành công |
| Metrics/logs | Hoạt động quan sát được trong runtime | Đầy đủ mọi trạng thái nếu instrumentation chưa có |

Ví dụ, discovery feature ở enabled chỉ cho biết bean lookup thành công. Để xác nhận registry truy cập được, hãy xem discovery health indicator hoặc kiểm tra truy vấn service trong integration test.

## 13. Chẩn đoán các kết quả thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| /actuator/features trả 404 | Actuator thiếu, feature endpoint bị tắt, chưa expose hoặc base path khác | Kiểm tra dependency, spring.cloud.features.enabled và Actuator exposure |
| Feature không xuất hiện ở enabled lẫn disabled | Module không khai báo HasFeatures hoặc cấu hình metadata không được nạp | Kiểm tra auto-configuration và điều kiện tạo HasFeatures |
| Abstract feature ở disabled nhưng class có trên classpath | Bean chưa được đăng ký hoặc lookup không đơn nhất | Kiểm tra beans và conditions |
| Named feature ở enabled nhưng bean không tồn tại | Metadata được công bố trực tiếp, không có bean lookup | Guard HasFeatures theo điều kiện của capability và kiểm tra beans |
| Version hoặc vendor là null | Package manifest không chứa Implementation-Version/Vendor | Kiểm tra JAR manifest hoặc dependency metadata |
| Type là class proxy | Bean bị AOP hoặc scope proxy | Kiểm tra bean type và target class |
| Feature báo enabled nhưng service không hoạt động | Bean tồn tại nhưng dependency hoặc runtime path lỗi | Kiểm tra health, logs, metrics và gọi thử integration |
| Abstract feature bị disabled dù có nhiều implementation | Lookup theo Class không chọn được một bean duy nhất | Kiểm tra NoUniqueBeanDefinitionException, @Primary hoặc kiểu feature |

### 13.1. Khi feature không xuất hiện

Features endpoint chỉ xử lý các feature đã được đưa vào danh sách HasFeatures. Nếu feature không xuất hiện ở cả hai nhóm, đừng bắt đầu bằng cách kiểm tra bean. Trước hết hãy xác minh:

- Cấu hình khai báo HasFeatures có được tạo không.
- Điều kiện classpath/property/bean có match không.
- Module có khai báo feature trong phiên bản đang chạy không.
- Cấu hình metadata có bị loại bởi profile hoặc exclude không.

### 13.2. Khi named feature báo enabled sai thực tế

Đây thường là vấn đề điều kiện công bố metadata. Ví dụ, HasFeatures được tạo vô điều kiện trong khi integration client chỉ được tạo khi app.payment.enabled=true.

Hãy đưa bean metadata vào cùng cấu hình được guard bởi điều kiện của integration hoặc thêm condition phù hợp. Kiểm thử cả trường hợp bật và tắt để đảm bảo danh sách enabled phản ánh đúng ý định.

## 14. Kiểm thử FeaturesEndpoint

Không cần chạy service registry thật để kiểm tra logic công bố feature. Có thể tạo một ApplicationContext test nhỏ với một bean thực, một abstract feature không có bean và một named feature.

Ví dụ dưới đây minh họa test trong package phù hợp để truy cập kiểu kết quả của endpoint:

```java
@Configuration(proxyBeanMethods = false)
class FeatureTestConfiguration {

    @Bean
    InventoryClient inventoryClient() {
        return new StubInventoryClient();
    }

    @Bean
    HasFeatures declaredFeatures() {
        return HasFeatures.builder()
            .abstractFeature(InventoryClient.class)
            .abstractFeature(PaymentClient.class)
            .namedFeature(
                new NamedFeature(
                    "Inventory Bus",
                    InventoryBusConfiguration.class
                )
            )
            .build();
    }
}
```

Test:

```java
@Test
void publishesAbstractAndNamedFeatures() {
    try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(
                 FeatureTestConfiguration.class
             )) {

        List<HasFeatures> declarations =
            new ArrayList<>(
                context.getBeansOfType(HasFeatures.class).values()
            );

        FeaturesEndpoint endpoint =
            new FeaturesEndpoint(declarations);

        endpoint.setApplicationContext(context);

        FeaturesEndpoint.Features result =
            endpoint.features();

        assertThat(result.getEnabled())
            .extracting(FeaturesEndpoint.Feature::getName)
            .contains("InventoryClient", "Inventory Bus");

        assertThat(result.getDisabled())
            .contains("PaymentClient");
    }
}
```

Test minh họa ba kết quả:

- InventoryClient được khai báo và bean tồn tại nên xuất hiện trong enabled.
- PaymentClient được khai báo nhưng bean không tồn tại nên xuất hiện trong disabled.
- Inventory Bus là named feature nên xuất hiện trong enabled theo metadata, dù test không đăng ký bean InventoryBusConfiguration.

Đây là cách kiểm chứng trực tiếp khác biệt giữa abstract và named feature.

### 14.1. Kiểm thử metadata version/vendor

Có thể kiểm tra type và metadata:

```java
FeaturesEndpoint.Feature feature =
    result.getEnabled().stream()
        .filter(item -> item.getName().equals("InventoryClient"))
        .findFirst()
        .orElseThrow();

assertThat(feature.getType())
    .isEqualTo(StubInventoryClient.class.getCanonicalName());
```

Giá trị version/vendor phụ thuộc manifest của artifact chạy test. Không nên hard-code một giá trị nếu test đang chạy từ output thư mục build không có package metadata. Có thể kiểm tra null hoặc chuẩn bị test JAR có manifest xác định nếu cần xác minh version cụ thể.

### 14.2. Kiểm thử named feature khi điều kiện tắt

Tạo hai ApplicationContext hoặc hai cấu hình test:

- Trường hợp condition bật: bean HasFeatures được tạo và named feature xuất hiện trong enabled.
- Trường hợp condition tắt: bean HasFeatures không được tạo và named feature không xuất hiện.

Test này xác nhận metadata được guard đúng với lifecycle của capability.

### 14.3. Kiểm thử bean lookup không đơn nhất

Nếu abstract feature dùng interface có nhiều implementation, hãy kiểm tra rõ hành vi khi không có primary candidate. Kết quả lookup không đơn nhất có thể bị endpoint đưa vào disabled do exception được bắt trong implementation.

Có thể viết test riêng để chứng minh hành vi này, sau đó quyết định dùng kiểu feature cụ thể hơn hoặc cấu hình một candidate chính.

## 15. Bảo mật và vận hành endpoint

Features endpoint là endpoint chỉ đọc, nhưng metadata có thể tiết lộ:

- Thành phần tích hợp đang được sử dụng.
- Tên implementation class.
- Phiên bản thư viện.
- Nhà cung cấp artifact.
- Những capability đang được khai báo hoặc thiếu.

Trong production:

1. Chỉ expose endpoint khi có nhu cầu vận hành.
2. Giới hạn management port hoặc network truy cập.
3. Yêu cầu xác thực và phân quyền.
4. Không expose toàn bộ Actuator chỉ để dùng Features endpoint.
5. Tránh đưa metadata nội bộ nhạy cảm vào tên feature.
6. Đảm bảo các endpoint beans/conditions cũng được bảo vệ nếu được expose để chẩn đoán.

Nếu dùng Spring Security với custom SecurityFilterChain, hãy xác nhận rule dành cho Actuator endpoint vẫn được áp dụng. Không giả định cấu hình bảo vệ mặc định tiếp tục hoạt động sau khi ứng dụng định nghĩa security chain riêng.

## 16. Quy trình đối chiếu khi triển khai

Khi một capability không hoạt động như mong đợi, có thể thực hiện theo trình tự:

1. Gọi /actuator/features để xác định feature được công bố hay không.
2. Xác định feature là abstract hay named theo cách module khai báo.
3. Với abstract feature, kiểm tra bean type trong /actuator/beans.
4. Với named feature, kiểm tra điều kiện tạo bean HasFeatures và bean nghiệp vụ thực tế.
5. Nếu bean thiếu, xem /actuator/conditions để tìm condition không match.
6. Kiểm tra property, profile, dependency và auto-configuration exclude.
7. Xem /actuator/health để xác minh dependency runtime có khỏe không.
8. Dùng log, metrics và integration test để xác nhận đường nghiệp vụ.
9. Kiểm tra version/vendor metadata nếu cần xác minh artifact đang chạy.
10. Sửa cấu hình công bố feature và kiểm thử lại cả trường hợp enabled lẫn disabled.

Quy trình này giúp tránh nhầm lẫn giữa “được khai báo”, “được tạo bean” và “đang hoạt động”.

## 17. Những hiểu lầm thường gặp

**“Có dependency trên classpath thì feature luôn xuất hiện.”** Features endpoint tổng hợp các khai báo HasFeatures. Classpath presence một mình không đủ.

**“Enabled nghĩa là mọi named feature đều có bean tương ứng.”** Named feature được công bố từ metadata mà không thực hiện bean lookup. Cấu hình khai báo cần được guard đúng.

**“Disabled nghĩa là class không có trong classpath.”** Với abstract feature, disabled cho biết lookup bean theo kiểu không thành công trong context đang xét; class vẫn có thể nằm trong classpath.

**“Version là phiên bản Spring Cloud của toàn ứng dụng.”** Version lấy từ package metadata của class đại diện cho feature.

**“Version null nghĩa là feature lỗi.”** Manifest có thể không chứa Implementation-Version hoặc Implementation-Vendor.

**“Bean có mặt nghĩa là service đã khỏe.”** Bean có thể tồn tại nhưng không kết nối được registry hoặc dependency.

**“Feature không xuất hiện nghĩa là bean không tồn tại.”** Module có thể chưa khai báo feature trong HasFeatures.

**“Một abstract feature luôn tìm thấy bean nếu có ít nhất một implementation.”** Lookup theo Class có thể không đơn nhất khi nhiều bean cùng kiểu và không có candidate chính.

**“Features endpoint thay thế beans và conditions endpoint.”** Mỗi endpoint cung cấp một góc nhìn khác nhau; cần kết hợp khi chẩn đoán.

## 18. Bài tập áp dụng

### Bài tập 1. Đọc response

Một response có:

```json
{
  "enabled": [
    {
      "name": "DiscoveryClient",
      "type": "com.example.EurekaDiscoveryClient",
      "version": "5.0.4",
      "vendor": "Example"
    },
    {
      "name": "Inventory Bus",
      "type": "com.example.InventoryBusConfiguration",
      "version": null,
      "vendor": null
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
```

Hãy giải thích:

1. Vì sao DiscoveryClient nằm trong enabled?
2. Vì sao Inventory Bus có thể enabled dù version/vendor null?
3. Cần kiểm tra gì để xác nhận Inventory Bus bean thực tế tồn tại?
4. LoadBalancerClient disabled có chứng minh dependency không có trên classpath không?

### Bài tập 2. Guard named feature

Một module khai báo named feature Payment Integration vô điều kiện, trong khi payment client chỉ được tạo khi app.payment.enabled=true.

Hãy sửa cấu hình để metadata chỉ được tạo khi payment integration được bật. Viết test cho cả hai giá trị true và false.

### Bài tập 3. Nhiều implementation

Một interface MessageTransport có hai bean KafkaTransport và RabbitTransport. Abstract feature được khai báo bằng MessageTransport.class, nhưng endpoint đưa feature vào disabled.

Hãy giải thích nguyên nhân có thể xảy ra và đề xuất cách cấu hình hoặc kiểu feature để kết quả có ý nghĩa.

### Bài tập 4. Đối chiếu auto-configuration

Features endpoint báo DiscoveryClient disabled. Hãy xây dựng quy trình kiểm tra từ beans đến conditions, property spring.cloud.discovery.enabled, dependency và health indicator.

### Bài tập 5. Thiết kế metadata module

Một module có ba capability: HTTP inventory client, event publisher và background scheduler. Hãy chọn abstract/named feature cho từng capability, viết các bean HasFeatures và xác định điều kiện cần guard.

## 19. Câu hỏi tự kiểm tra

1. Features endpoint có ID là gì và URL HTTP mặc định thường là gì?
2. Hai nhóm enabled và disabled chứa dữ liệu gì?
3. Abstract feature được kiểm tra bằng cơ chế nào?
4. Named feature có thực hiện ApplicationContext bean lookup không?
5. Vì sao named feature cần được khai báo trong configuration có điều kiện?
6. Trường type của abstract feature đến từ class nào?
7. Version và vendor được lấy từ đâu?
8. Vì sao version/vendor có thể null?
9. NoUniqueBeanDefinitionException có thể ảnh hưởng kết quả abstract feature như thế nào?
10. Vì sao feature không xuất hiện chưa chắc là bean không tồn tại?
11. Khi nào nên đối chiếu với endpoint beans?
12. Conditions endpoint giúp tìm nguyên nhân gì?
13. Features endpoint có xác nhận kết nối registry thành công không?
14. Làm thế nào kiểm thử một named feature bị công bố khi bean thực tế vắng mặt?
15. Vì sao không nên expose toàn bộ Actuator chỉ để kiểm tra features?

## 20. Nguồn tham chiếu

- [Spring Cloud Commons Reference — Enabled Features](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): hai loại feature, cách khai báo HasFeatures và ý nghĩa thông tin được công bố.
- [FeaturesEndpoint.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/actuator/FeaturesEndpoint.java): cách endpoint đối chiếu abstract feature với ApplicationContext và xây dựng danh sách enabled/disabled.
- [CommonsClientAutoConfiguration.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/CommonsClientAutoConfiguration.java): điều kiện tạo Features endpoint và khai báo feature của Spring Cloud Commons.
- [FeaturesEndpointTests.java — Spring Cloud Commons tests](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/test/java/org/springframework/cloud/client/actuator/FeaturesEndpointTests.java): ví dụ kiểm thử abstract feature có bean, abstract feature thiếu bean và named feature.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): điều kiện endpoint available, exposure, access control và các endpoint beans/conditions/health.
- [NoUniqueBeanDefinitionException — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/beans/factory/NoUniqueBeanDefinitionException.html): ngoại lệ khi bean lookup theo kiểu có nhiều candidate.

## Ghi nhớ

Features endpoint công bố các feature mà module khai báo qua HasFeatures. Abstract feature được kiểm tra bằng bean lookup theo kiểu trong ApplicationContext; named feature được đưa vào enabled từ metadata và không tự xác minh bean tương ứng. Vì vậy, hãy guard named feature bằng điều kiện của capability thật, đối chiếu abstract feature với endpoint beans, dùng conditions để giải thích auto-configuration và dùng health/integration test để xác minh runtime. Metadata version/vendor lấy từ package của class đại diện và có thể null khi artifact không cung cấp manifest fields.
