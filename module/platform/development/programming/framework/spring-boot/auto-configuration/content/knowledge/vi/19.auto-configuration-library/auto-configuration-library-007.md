# Thiết kế trường hợp không có dependency hoặc người dùng tắt tính năng

## 1. Mục tiêu: thư viện phải hoạt động tốt khi tính năng không khả dụng

Một thư viện Spring Boot có thể tích hợp SDK của nhà cung cấp, client gửi mail, bộ xử lý ảnh, adapter cloud hoặc module tìm kiếm. Không phải ứng dụng nào cũng cần các chức năng này. Có ứng dụng không đưa dependency tương ứng vào classpath; có ứng dụng có dependency nhưng chủ động tắt tính năng trong một môi trường cụ thể.

Một auto-configuration tốt phải xử lý được cả hai tình huống:

1. **Không có dependency tùy chọn:** Spring Boot không cố nạp các class chỉ tồn tại trong SDK đó, không làm ứng dụng lỗi với `NoClassDefFoundError`/`ClassNotFoundException`, và không tạo bean của tính năng.
2. **Người dùng tắt tính năng:** dù SDK có mặt, điều kiện property không cho phép cấu hình tính năng được áp dụng; các bean tùy chọn không được đăng ký.
3. **Ứng dụng cung cấp bean thay thế:** nếu thư viện có extension point phù hợp, auto-configuration nhường quyền bằng `@ConditionalOnMissingBean`.
4. **Phần còn lại của ứng dụng vẫn khởi động:** code tiêu thụ tính năng tùy chọn không được bắt buộc inject một bean có thể vắng mặt.

Bài này tập trung vào thiết kế auto-configuration cho một integration có SDK tùy chọn. Ví dụ dùng namespace `acme.catalog` và class SDK `demo.catalog.sdk.CatalogClient`. Các kiểu minh họa được định nghĩa trong dự án demo; trong thư viện thật, `CatalogClient` đến từ dependency bên ngoài.

Sau bài này, bạn có thể thiết kế điều kiện classpath và property đúng chỗ, cô lập các tham chiếu tới optional class, chọn default bật/tắt có chủ đích, kiểm thử classpath thiếu dependency bằng `FilteredClassLoader`, và cho phép ứng dụng tự thay thế bean.

## 2. Hai câu hỏi độc lập: có dependency không, và tính năng có được bật không?

Không nên gộp hai câu hỏi thành một:

- **Classpath condition:** thư viện có đủ class cần thiết để tích hợp không?
- **Feature condition:** ứng dụng có cho phép tính năng hoạt động trong môi trường này không?

Mô hình điều kiện:

```text
Catalog SDK có trên classpath?
         |
      Không +------> Không đăng ký integration
         |
        Có
         |
acme.catalog.enabled có cho phép?
         |
      Không +------> Không đăng ký integration
         |
        Có
         |
Kiểm tra bean thay thế của ứng dụng
         |
Đăng ký bean mặc định nếu chưa có bean phù hợp
```

Hai điều kiện classpath và property kết hợp theo phép **AND**: phải có dependency **và** feature flag phải cho phép thì nhánh cấu hình mới được áp dụng. Sau đó `@ConditionalOnMissingBean` quyết định thư viện có cần tạo implementation mặc định hay nhường cho ứng dụng.

| SDK trên classpath | `acme.catalog.enabled` | Kết quả mong muốn |
|---|---|---|
| Không | Thiếu | Không tạo bean integration; ứng dụng vẫn chạy |
| Không | `true` | Vẫn không tạo bean; bật cờ không thể thay thế dependency |
| Không | `false` | Không tạo bean |
| Có | Thiếu | Phụ thuộc chính sách default được chọn |
| Có | `true` | Có thể đăng ký bean mặc định |
| Có | `false` | Không đăng ký nhánh integration |
| Có | `true` và user đã cung cấp bean service | Auto-configuration nhường quyền cho user bean |

**Property không cài dependency.** Việc đặt `acme.catalog.enabled=true` không thể làm class `CatalogClient` xuất hiện trên classpath. Ngược lại, chỉ thêm SDK vào Maven/Gradle cũng không bắt buộc ứng dụng phải bật tính năng.

## 3. @ConditionalOnClass: chỉ đăng ký integration khi dependency tồn tại

Spring Boot cung cấp `@ConditionalOnClass` để kiểm tra class có thể được tải từ classpath hay không.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "demo.catalog.sdk.CatalogClient")
class CatalogSdkConfiguration {
    // Các bean cần CatalogClient đặt trong class này
}
```

Có thể dùng thuộc tính `value` với class reference khi dependency luôn có ở compile time:

```java
@ConditionalOnClass(CatalogClient.class)
```

Với dependency thực sự tùy chọn, thuộc tính `name` thường phù hợp hơn vì biểu diễn tên class dưới dạng chuỗi. Quan trọng hơn, **các method signature, field, constructor và superclass trong lớp cấu hình ngoài không nên tham chiếu trực tiếp tới optional type**.

### 3.1. Vì sao nên dùng nested configuration?

Giả sử viết:

```java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "demo.catalog.sdk.CatalogClient")
    CatalogService catalogService(CatalogClient client) {
        return client::findById;
    }
}
```

Đoạn trên có vẻ hợp lý vì bean method có `@ConditionalOnClass`. Nhưng phương thức vẫn chứa optional type trong chữ ký. Trong một số đường introspection/đọc metadata, JVM hoặc Spring có thể cần phân giải kiểu đó trước khi điều kiện trên method bảo vệ được phần cấu hình. Kết quả có thể là lỗi class loading khi SDK không có mặt.

Spring Boot khuyến nghị cô lập các bean phụ thuộc class tùy chọn trong **một nested static configuration class riêng**, rồi đặt `@ConditionalOnClass` trên chính nested class đó:

```java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "demo.catalog.sdk.CatalogClient")
    static class CatalogSdkConfiguration {

        // Chỉ các method trong nhánh này mới tham chiếu CatalogClient.
    }
}
```

Spring đọc metadata điều kiện của nested configuration trước khi xử lý nội dung phụ thuộc SDK. Khi class không có, nested configuration bị bỏ qua và các method signature chứa optional type không cần được xử lý như một nhánh bean đang hoạt động.

**Đây là ranh giới quan trọng:** giữ outer auto-configuration an toàn khi không có SDK; đặt tất cả tham chiếu optional type bên trong nested class đã được bảo vệ.

### 3.2. Những nơi không nên để optional type rò ra ngoài

Khi dependency có thể vắng mặt, tránh đặt type đó trong:

- Constructor hoặc field của outer auto-configuration.
- Kiểu trả về/tham số của method `@Bean` thuộc outer class.
- Superclass hoặc interface mà outer class phải load.
- Static field initializer hoặc static block của outer class.
- Annotation attribute dùng class literal của dependency tùy chọn trên lớp ngoài.
- Component scan hoặc cấu hình import trực tiếp làm nested class được nạp độc lập ngoài điều kiện.

Hãy giữ optional type bên trong nested configuration có điều kiện classpath. Nếu helper class cũng tham chiếu SDK, chỉ gọi/nạp helper đó từ nhánh được bảo vệ.

### 3.3. Dùng class name khi dependency không có lúc runtime

Với thư viện có optional SDK, dạng:

```java
@ConditionalOnClass(name = "com.vendor.catalog.CatalogClient")
```

không yêu cầu annotation phải chứa class literal `CatalogClient.class`. Thư viện vẫn có thể biên dịch với SDK trong compile classpath, nhưng ứng dụng sử dụng thư viện không nhất thiết nhận SDK đó ở runtime.

Trong Maven, thư viện có thể đánh dấu dependency là optional:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>catalog-sdk</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

Dependency optional có ý nghĩa với dependency propagation: nó có trong classpath khi build chính thư viện, nhưng Maven không tự truyền dependency đó sang project tiêu thụ. Ứng dụng nào cần integration phải tự thêm SDK. Với Gradle, dùng cấu hình dependency phù hợp với mục tiêu công bố module, ví dụ `compileOnly`/runtime dependency theo cách đóng gói và phân phối thực tế.

Một thiết kế khác là tách integration thành starter riêng, ví dụ `acme-catalog-spring-boot-starter` phụ thuộc cả thư viện auto-config và SDK. Khi ứng dụng thêm starter, các class cần thiết cùng xuất hiện. Dù chọn cách nào, `@ConditionalOnClass` vẫn là hàng rào runtime hữu ích nếu dependency có thể bị loại hoặc thay đổi.

## 4. @ConditionalOnProperty: cho phép người dùng tắt tính năng

Sau khi SDK có mặt, feature flag quyết định có đăng ký nhánh cấu hình hay không.

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

Khóa hoàn chỉnh là `acme.catalog.enabled`. Điều kiện khớp khi giá trị tồn tại và bằng chuỗi `true` không phân biệt chữ hoa/thường. Với `matchIfMissing=false`, thiếu khóa cũng có nghĩa feature không được bật.

Cấu hình:

```yaml
acme:
  catalog:
    enabled: true
```

Khi người dùng muốn tắt trong một môi trường:

```yaml
acme:
  catalog:
    enabled: false
```

Hoặc dùng command line:

```bash
java -jar app.jar --acme.catalog.enabled=false
```

Giá trị từ nguồn cấu hình ưu tiên cao hơn có thể ghi đè file YAML. Do đó, khi debug, cần xem giá trị cuối trong Environment thay vì chỉ đọc một file.

### 4.1. Chọn default: opt-in hay opt-out?

Có hai hợp đồng hợp lệ; thư viện phải chọn một và ghi rõ trong tài liệu.

| Chính sách | Annotation | Khi thiếu property | Khi user đặt false | Phù hợp khi |
|---|---|---|---|---|
| **Opt-in** | `havingValue="true", matchIfMissing=false` | Tắt | Tắt | Tính năng có chi phí, side effect, gọi dịch vụ ngoài hoặc cần cấu hình rõ |
| **Opt-out** | `havingValue="true", matchIfMissing=true` | Bật nếu dependency có mặt | Tắt | Tính năng tương thích ngược, mong muốn tự hoạt động khi đã thêm integration |

Bài demo chọn **opt-in**: không có property thì feature không hoạt động. Đây là default an toàn cho một integration bên ngoài có thể cần endpoint, credential, quota hoặc network. Nếu sản phẩm có yêu cầu tương thích ngược và muốn tự bật khi SDK có mặt, có thể đổi `matchIfMissing=true` nhưng phải kiểm thử trường hợp thiếu key.

Không nhầm `matchIfMissing=true` với “bỏ qua giá trị false”. Nó chỉ áp dụng khi **không tìm thấy key**. Nếu người dùng đặt `false`, điều kiện `havingValue="true"` vẫn không khớp.

### 4.2. Vì sao không nên chỉ dùng havingValue mặc định?

Nếu bỏ `havingValue`, giá trị mặc định là chuỗi rỗng. Khi đó condition khớp với giá trị có mặt khác `false`. Những chuỗi như `yes`, `1` hoặc lỗi gõ có thể khiến feature bị bật ngoài dự kiến.

Với một công tắc Boolean, hãy viết rõ:

```java
havingValue = "true",
matchIfMissing = false
```

Khi đó bảng hành vi đơn giản:

| Giá trị | Opt-in trong demo | Opt-out nếu matchIfMissing=true |
|---|---|---|
| Không có key | Không khớp | Khớp |
| `true` | Khớp | Khớp |
| `TRUE` | Khớp | Khớp |
| `false` | Không khớp | Không khớp |
| Chuỗi rỗng | Không khớp | Không khớp |
| `yes` / `1` / `truue` | Không khớp | Không khớp |

### 4.3. Đặt property condition ở đúng cấp

Nếu mọi bean của integration đều phải tắt khi người dùng đặt false, đặt `@ConditionalOnProperty` trên nested configuration chứa toàn bộ bean liên quan. Như vậy các bean trong nhánh cùng được bật/tắt.

Nếu chỉ một bean là tùy chọn, có thể đặt condition trên phương thức `@Bean` tương ứng. Nhưng phải kiểm tra các bean khác có còn inject bắt buộc kiểu đó hay không; nếu service A vẫn yêu cầu bean B trong khi B bị tắt, context có thể fail vì thiếu dependency.

Một nhánh tính năng nên có ranh giới rõ: các bean chỉ phục vụ feature cùng nằm trong nhánh condition, hoặc các dependency tiêu thụ chúng cũng có cách xử lý optional.

## 5. @ConditionalOnMissingBean: nhường quyền cho ứng dụng

Một thư viện không nên buộc người dùng phải dùng implementation mặc định. Nếu application muốn cung cấp service hoặc client riêng, auto-configuration có thể dùng:

```java
@Bean
@ConditionalOnMissingBean(CatalogService.class)
CatalogService catalogService(CatalogClient client) {
    return client::findById;
}
```

Khi ứng dụng đã có một bean `CatalogService` phù hợp, bean mặc định không được đăng ký. Đây là **back-off behavior** thường gặp trong Spring Boot auto-configuration.

Ba điều kiện trong thiết kế có vai trò riêng:

| Condition | Câu hỏi |
|---|---|
| `@ConditionalOnClass` | SDK cần thiết có trên classpath không? |
| `@ConditionalOnProperty` | Ứng dụng có cho phép feature chạy không? |
| `@ConditionalOnMissingBean` | Ứng dụng đã cung cấp implementation thay thế chưa? |

Điều kiện missing-bean không thay thế hai điều kiện trước. Nếu SDK thiếu, không nên cố tạo service chỉ vì chưa có bean service. Nếu feature bị tắt, user bean có thể vẫn tồn tại theo cấu hình riêng của ứng dụng; việc feature flag có nên vô hiệu hóa cả user bean hay chỉ bean mặc định là **hợp đồng cần thiết kế rõ**.

### 5.1. Cho phép thay cả SDK client hoặc service

Nếu muốn extension point rộng hơn, có thể dùng `@ConditionalOnMissingBean` cho cả client và service:

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient() {
    return new CatalogClient();
}

@Bean
@ConditionalOnMissingBean(CatalogService.class)
CatalogService catalogService(CatalogClient client) {
    return client::findById;
}
```

Các method này phải nằm trong nested configuration đã bảo vệ bởi classpath và property conditions. Ứng dụng có thể thay client để dùng transport khác, hoặc thay service để đổi nghiệp vụ.

Lưu ý về thứ tự: auto-configuration được thiết kế để bean người dùng thường được xử lý trước bean mặc định. Nếu auto-config phụ thuộc vào bean do auto-config khác tạo, hãy khai báo quan hệ thứ tự phù hợp và kiểm thử; đừng dựa vào thứ tự method tình cờ.

## 6. Thiết kế ứng dụng tiêu thụ: bean tùy chọn thì inject tùy chọn

Ngay cả khi auto-configuration xử lý đúng trường hợp dependency thiếu, ứng dụng vẫn có thể tự làm mình fail nếu một component bắt buộc inject service tùy chọn:

```java
@Service
public class OrderService {
    private final CatalogService catalogService;

    public OrderService(CatalogService catalogService) {
        this.catalogService = catalogService;
    }
}
```

Nếu `CatalogService` không được đăng ký khi SDK thiếu hoặc flag tắt, Spring không thể tạo `OrderService` theo constructor này.

### 6.1. ObjectProvider khi tính năng thật sự tùy chọn

```java
@Service
public class OrderService {
    private final ObjectProvider<CatalogService> catalogProvider;

    public OrderService(ObjectProvider<CatalogService> catalogProvider) {
        this.catalogProvider = catalogProvider;
    }

    public String describe(String id) {
        CatalogService service = catalogProvider.getIfAvailable();
        if (service == null) {
            return "Catalog integration is unavailable";
        }
        return service.findById(id);
    }
}
```

`ObjectProvider` cho phép hỏi bean có sẵn hay không tại thời điểm cần dùng. Ứng dụng vẫn khởi động khi bean vắng mặt. Cần quyết định rõ hành vi nghiệp vụ khi không có service: trả kết quả thay thế, bỏ qua bước tùy chọn, hoặc báo lỗi chỉ khi người dùng gọi chức năng phụ thuộc integration.

### 6.2. Optional injection

Một lựa chọn khác là constructor nhận `Optional<CatalogService>`:

```java
public OrderService(Optional<CatalogService> catalogService) {
    this.catalogService = catalogService;
}
```

Cách này phù hợp nếu ứng dụng chỉ cần biết service có hay không khi khởi tạo. Nếu cần truy vấn động theo thời điểm, `ObjectProvider` linh hoạt hơn.

### 6.3. Tách module hoặc tách component theo feature

Nếu phần lớn code không cần biết SDK tồn tại, tách adapter/catalog integration thành module riêng và chỉ đăng ký component khi feature condition khớp. Các controller hoặc job phụ thuộc integration cũng nên có condition tương ứng hoặc được gọi thông qua interface optional.

Không nên tạo một bean giả chỉ để làm ứng dụng khởi động nếu implementation giả trả dữ liệu sai hoặc che giấu việc feature đang tắt. Nếu cần fallback, hãy định nghĩa hành vi fallback như một phần hợp đồng sản phẩm.

## 7. Ví dụ hoàn chỉnh: optional SDK và feature flag

Ví dụ dưới đây dùng **Java 17+**, Spring Boot 3.3.13 và Maven. Nó tạo ba trạng thái:

- SDK có mặt và flag bật: đăng ký client/service.
- SDK có mặt nhưng flag tắt: không đăng ký client/service.
- SDK không có mặt: nested configuration bị bỏ qua, ứng dụng không lỗi vì thiếu class SDK.

Để chạy độc lập, dự án định nghĩa một class giả lập vendor SDK trong package riêng. Trong thư viện thực tế, class đó đến từ dependency Maven optional hoặc starter integration riêng.

### 7.1. Cấu trúc thư mục

```text
optional-catalog-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/catalog/
    │   │   ├── api/CatalogService.java
    │   │   ├── sdk/CatalogClient.java
    │   │   ├── autoconfigure/CatalogAutoConfiguration.java
    │   │   └── app/CatalogDemoApplication.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/catalog/
        └── CatalogAutoConfigurationTest.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>optional-catalog-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
```

### 7.3. API mà ứng dụng tiêu thụ: CatalogService.java

```java
package demo.catalog.api;

public interface CatalogService {
    String findById(String id);
}
```

Interface này không phụ thuộc vendor SDK. Các module nghiệp vụ có thể compile chỉ với API của thư viện, kể cả khi optional SDK không có.

### 7.4. SDK giả lập: CatalogClient.java

```java
package demo.catalog.sdk;

public class CatalogClient {

    public String findById(String id) {
        return "catalog-item:" + id;
    }
}
```

Trong dự án demo, class này mô phỏng dependency ngoài. Trong thư viện thật, class giả lập nằm trong artifact riêng; ứng dụng không cần SDK sẽ không thêm artifact đó. Test dùng `FilteredClassLoader` để mô phỏng context không thể tải class này.

### 7.5. Auto-configuration: CatalogAutoConfiguration.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.api.CatalogService;
import demo.catalog.sdk.CatalogClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "demo.catalog.sdk.CatalogClient")
    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    static class CatalogSdkConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient() {
            return new CatalogClient();
        }

        @Bean
        @ConditionalOnMissingBean(CatalogService.class)
        CatalogService catalogService(CatalogClient client) {
            return client::findById;
        }
    }
}
```

Có bốn quyết định thiết kế:

1. Outer class chỉ có type API ổn định và không có method/constructor nào cần khởi tạo SDK.
2. Nested configuration giữ toàn bộ tham chiếu tới optional type.
3. `@ConditionalOnClass(name=...)` bảo vệ nhánh khi SDK không có trên classpath.
4. `@ConditionalOnProperty(... matchIfMissing=false)` yêu cầu ứng dụng bật tường minh; `@ConditionalOnMissingBean` cho phép ứng dụng thay client hoặc service.

Nếu người dùng đặt `acme.catalog.enabled=false`, cả hai bean trong nested configuration đều không được đăng ký. Nếu key thiếu, demo cũng tắt theo chính sách opt-in.

### 7.6. Công bố auto-configuration

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung duy nhất:

```text
demo.catalog.autoconfigure.CatalogAutoConfiguration
```

Đây là cách Spring Boot 3.x khám phá auto-configuration của thư viện. Đặt lớp auto-config ở package riêng không nằm dưới package component scan chính của ứng dụng. Không component scan hoặc `@Import` thủ công auto-configuration này thêm lần nữa.

### 7.7. Ứng dụng tiêu thụ: CatalogDemoApplication.java

```java
package demo.catalog.app;

import demo.catalog.api.CatalogService;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogDemoApplication implements CommandLineRunner {

    private final ObjectProvider<CatalogService> catalogProvider;

    public CatalogDemoApplication(
            ObjectProvider<CatalogService> catalogProvider) {
        this.catalogProvider = catalogProvider;
    }

    public static void main(String[] args) {
        SpringApplication.run(CatalogDemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        CatalogService catalog = catalogProvider.getIfAvailable();

        if (catalog == null) {
            System.out.println("catalogFeature=unavailable");
            return;
        }

        System.out.println("catalogResult=" + catalog.findById("42"));
    }
}
```

Ứng dụng dùng `ObjectProvider` vì service có thể vắng mặt. Khi bật feature:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--acme.catalog.enabled=true
```

Dòng output do ứng dụng in:

```text
catalogResult=catalog-item:42
```

Khi tắt feature:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--acme.catalog.enabled=false
```

Output:

```text
catalogFeature=unavailable
```

Nếu bỏ tham số `--acme.catalog.enabled=true`, demo dùng opt-in nên cũng in `catalogFeature=unavailable`. Log startup của Spring Boot có thể xuất hiện thêm; các dòng trên là output của ứng dụng.

### 7.8. Kiểm thử bằng ApplicationContextRunner và FilteredClassLoader

File `CatalogAutoConfigurationTest.java`:

```java
package demo.catalog;

import demo.catalog.api.CatalogService;
import demo.catalog.autoconfigure.CatalogAutoConfiguration;
import demo.catalog.sdk.CatalogClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void featureIsDisabledWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean("catalogClient");
            assertThat(context).doesNotHaveBean("catalogService");
        });
    }

    @Test
    void featureIsEnabledWhenDependencyExistsAndFlagIsTrue() {
        runner.withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context).hasSingleBean(CatalogService.class);
                    assertThat(context.getBean(CatalogService.class)
                            .findById("42"))
                            .isEqualTo("catalog-item:42");
                });
    }

    @Test
    void userCanDisableFeatureEvenWhenDependencyExists() {
        runner.withPropertyValues("acme.catalog.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                    assertThat(context).doesNotHaveBean("catalogService");
                });
    }

    @Test
    void missingOptionalSdkDoesNotFailContext() {
        runner.withClassLoader(
                new FilteredClassLoader(CatalogClient.class))
                .withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                    assertThat(context).doesNotHaveBean("catalogService");
                });
    }

    @Test
    void applicationServiceOverridesDefaultService() {
        runner.withPropertyValues("acme.catalog.enabled=true")
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogService.class);
                    assertThat(context.getBean(CatalogService.class)
                            .findById("42"))
                            .isEqualTo("custom-item:42");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogService customCatalogService() {
            return id -> "custom-item:" + id;
        }
    }
}
```

Chạy kiểm thử:

```bash
mvn test
```

Với đúng năm test trong lớp trên, kết quả mong đợi là **5 tests, 0 failures, 0 errors**. Đây là kết quả kỳ vọng; số liệu thực tế phải lấy từ Maven Surefire khi chạy dự án.

### 7.9. Ý nghĩa của từng test

| Test | Input | Kết quả mong đợi |
|---|---|---|
| `featureIsDisabledWhenPropertyIsMissing` | SDK có, property thiếu | Context thành công; không có client/service |
| `featureIsEnabledWhenDependencyExistsAndFlagIsTrue` | SDK có, enabled=true | Có CatalogClient và CatalogService |
| `userCanDisableFeatureEvenWhenDependencyExists` | SDK có, enabled=false | Context thành công; hai bean không có |
| `missingOptionalSdkDoesNotFailContext` | SDK bị FilteredClassLoader ẩn, enabled=true | Context vẫn thành công; không có hai bean |
| `applicationServiceOverridesDefaultService` | SDK có, enabled=true, user service đã đăng ký | Chỉ dùng service do ứng dụng cung cấp |

Test `missingOptionalSdkDoesNotFailContext` là quan trọng nhất để chứng minh classpath condition. Chỉ kiểm tra `doesNotHaveBean` khi dependency vẫn có trên classpath chưa chứng minh ứng dụng chịu được dependency bị thiếu. `FilteredClassLoader` làm class SDK không thể được tải trong context đang kiểm tra.

## 8. Thiết kế dependency trong thư viện Maven/Gradle

### 8.1. Maven optional dependency

Một thư viện có thể biên dịch với SDK nhưng không bắt buộc mọi ứng dụng tiêu thụ phải nhận SDK:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>catalog-sdk</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

Điều này thích hợp khi:
- Auto-config có thể hoạt động mà không cần integration.
- Chỉ ứng dụng nào dùng integration mới thêm SDK.
- Thư viện muốn cung cấp một artifact chính nhưng không kéo nhiều SDK vào mọi consumer.

Khi người dùng cần feature, thêm dependency:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>catalog-sdk</artifactId>
    <version>1.2.0</version>
</dependency>
```

Không nên đánh dấu optional nếu thư viện không thể hoạt động hoặc không thể biên dịch/khởi động khi thiếu dependency đó. Optional là quyết định API và phân phối dependency, không phải một cách giấu lỗi cấu hình.

### 8.2. Tách integration thành module/starter

Một cấu trúc nhiều module có thể là:

```text
acme-catalog/
├── acme-catalog-core/
│   └── CatalogService API và nghiệp vụ không phụ thuộc vendor
├── acme-catalog-spring-boot-autoconfigure/
│   └── auto-configuration + condition
└── acme-catalog-spring-boot-starter/
    └── dependency vào autoconfigure và vendor SDK
```

Ứng dụng chỉ dùng API core không bị kéo SDK. Ứng dụng muốn integration thêm starter. Đây là lựa chọn rõ ràng nếu vendor SDK lớn, có license riêng hoặc chỉ một phần nhỏ người dùng cần.

Có thể công bố thêm starter không có vendor SDK và starter có vendor SDK nếu muốn hỗ trợ cả hai cách tích hợp. Tên module và dependency graph nên diễn đạt đúng chức năng để người dùng biết mình đang thêm gì.

### 8.3. Gradle và optional runtime

Trong Gradle, cấu hình dependency cần phản ánh mục tiêu compile và runtime của module:

- `compileOnly`: có mặt khi compile module nhưng không tự đi vào runtime consumer.
- `runtimeOnly`: có mặt ở runtime nhưng không cần type khi compile source.
- `api`/`implementation`: kiểm soát mức dependency được công bố tới consumer trong Gradle.

Không sao chép máy móc quy tắc Maven `optional=true` sang Gradle; hãy kiểm tra published metadata của module và dependency graph thực tế của consumer. Điều cần giữ nguyên là: **nếu SDK có thể vắng mặt ở runtime, auto-configuration phải có classpath guard và không để optional type bị nạp ngoài nhánh được bảo vệ.**

## 9. Những trường hợp cần thiết kế kỹ hơn

### 9.1. Dependency có mặt nhưng cấu hình kết nối không đầy đủ

`@ConditionalOnClass` chỉ xác nhận class tồn tại. Nó không chứng minh:

- URL endpoint hợp lệ.
- Credential có mặt hoặc còn hiệu lực.
- Network tới vendor hoạt động.
- SDK tương thích với server.
- Tài khoản có quyền truy cập.

Nếu bean client cần endpoint, có thể dùng `@ConditionalOnProperty` bổ sung cho property bắt buộc, hoặc dùng `@ConfigurationProperties` có validation để fail-fast với thông báo rõ ràng khi người dùng đã bật feature nhưng thiếu cấu hình cần thiết.

Không nên dùng `@ConditionalOnProperty` để âm thầm bỏ qua cấu hình sai nếu ứng dụng đã chủ động bật tính năng và mong muốn nó hoạt động. Hãy quyết định: **thiếu endpoint thì feature tắt**, hay **feature bật mà thiếu endpoint là lỗi startup**. Hai chính sách này khác nhau.

### 9.2. Người dùng tắt feature nhưng vẫn cung cấp custom bean

Nếu feature condition nằm trên toàn nested configuration, nhánh đó không được import khi flag false. Một bean custom do ứng dụng khai báo độc lập vẫn có thể tồn tại. Đây có thể là hành vi mong muốn: flag chỉ tắt bean mặc định của thư viện.

Nếu hợp đồng yêu cầu flag false phải cấm cả việc sử dụng service do người dùng cung cấp, cần đặt điều kiện ở ranh giới tiêu thụ hoặc dùng một feature policy rõ ràng hơn. Đừng giả định `@ConditionalOnProperty` trên auto-config sẽ xóa bean được tạo từ user configuration.

### 9.3. Tách classpath condition và property condition

Đặt hai condition trên nested configuration giúp logic rõ. Nếu dependency thiếu, không cần quan tâm feature flag; nếu dependency có, property quyết định có áp dụng hay không.

Một số codebase đặt `@ConditionalOnClass` trên outer class và `@ConditionalOnProperty` trên method. Cách đó có thể phù hợp nếu mọi class trong outer class đều an toàn khi load. Nhưng khi có optional type trong method signature, nested configuration thường là cách cô lập dễ hiểu hơn.

### 9.4. Không dùng @ConditionalOnMissingClass để thay thế mọi thiết kế optional

Có thể dùng `@ConditionalOnMissingClass` để cung cấp fallback khi SDK không có. Nhưng cần xác định fallback thực sự có ý nghĩa hay không. Ví dụ service trả dữ liệu rỗng có thể che giấu việc integration chưa được cài. Nếu feature chỉ có ý nghĩa khi SDK tồn tại, không tạo bean và để ứng dụng xử lý optional dependency thường minh bạch hơn.

### 9.5. Bean condition và thứ tự auto-configuration

Nếu service bean cần một bean do auto-configuration khác cung cấp, `@ConditionalOnBean` chỉ nhìn thấy các bean definition đã được xử lý ở thời điểm đánh giá. Khi phụ thuộc vào auto-config khác, dùng `@AutoConfiguration(after = OtherAutoConfiguration.class)` hoặc quan hệ thứ tự tương ứng. Không dùng classpath/property condition để giải quyết lỗi thứ tự đăng ký bean.

## 10. Bảng quyết định thiết kế

| Câu hỏi | Cơ chế nên dùng | Ghi chú |
|---|---|---|
| SDK class có thể vắng mặt? | `@ConditionalOnClass(name=...)` | Đặt trên nested config cô lập optional type |
| Người dùng có quyền tắt feature? | `@ConditionalOnProperty` | Chọn opt-in hoặc opt-out và ghi rõ default |
| Người dùng muốn thay service mặc định? | `@ConditionalOnMissingBean(Service.class)` | Đặt trên bean mặc định |
| Ứng dụng có thể chạy khi service không có? | `ObjectProvider`/`Optional`/feature-specific configuration | Không inject bắt buộc một bean có thể vắng |
| SDK dependency không nên truyền tới mọi consumer? | Maven optional hoặc module/starter riêng | Kiểm tra dependency graph được publish |
| SDK có mặt nhưng thiếu endpoint/credential? | Validation và property contract | Phân biệt tắt feature với cấu hình bật nhưng sai |
| Muốn tắt chỉ một phần nested config? | Condition ở nested config/bean method | Không loại toàn outer auto-config nếu vẫn cần các nhánh khác |
| Cần fallback khi SDK thiếu? | `@ConditionalOnMissingClass` hoặc implementation thay thế | Chỉ dùng nếu fallback có ngữ nghĩa đúng |
| Cần điều kiện bean từ auto-config khác? | `@AutoConfiguration(after=...)` + `@ConditionalOnBean` | Xử lý dependency order ở đúng tầng |

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| App không dùng SDK nhưng startup báo NoClassDefFoundError | Optional type nằm trong outer config/method signature hoặc bị scan/import riêng | Cô lập optional type trong nested config có `@ConditionalOnClass` |
| Đặt enabled=false nhưng bean vẫn có | Bean được tạo bởi user config hoặc auto-config khác | Xác định nguồn bean; feature flag trên thư viện không xóa bean độc lập |
| SDK có mặt, flag thiếu, bean không có | Đang dùng opt-in với `matchIfMissing=false` | Đây là default đã chọn; đặt true nếu muốn bật hoặc đổi policy có chủ đích |
| SDK thiếu nhưng enabled=true, bean vẫn không có | Classpath condition không khớp | Thêm dependency đúng hoặc chấp nhận integration không khả dụng |
| App khởi động fail vì thiếu CatalogService | Consumer inject bắt buộc bean tùy chọn | Dùng ObjectProvider/Optional hoặc condition cả consumer |
| User đã có CatalogService nhưng default vẫn xuất hiện | `@ConditionalOnMissingBean` sai type/name hoặc user bean chưa được xử lý trước | Kiểm tra bean type, qualifier, thứ tự auto-config |
| Class SDK có trên compile nhưng không có runtime | Dependency scope/publication không đúng | Kiểm tra Maven/Gradle runtime graph và published metadata |
| Condition classpath true nhưng tạo client lỗi | Class tồn tại nhưng cấu hình/endpoint/credential không hợp lệ | Validate cấu hình và kiểm tra lỗi constructor/factory |
| Flag false nhưng custom service vẫn tồn tại | User bean được đăng ký ngoài nhánh auto-config | Xác định flag chỉ điều khiển bean mặc định hay toàn feature |
| Test thiếu SDK vẫn pass dù chưa thực sự ẩn class | Chỉ không đăng ký bean, class vẫn có trên classpath | Dùng `FilteredClassLoader` để mô phỏng missing dependency |

## 12. Quy trình kiểm thử trước khi phát hành starter

Một thư viện tự cấu hình nên có tối thiểu các trường hợp:

1. **SDK present + flag true:** bean mặc định xuất hiện.
2. **SDK present + flag false:** bean mặc định không xuất hiện.
3. **SDK present + flag missing:** kết quả đúng chính sách default opt-in/opt-out đã công bố.
4. **SDK missing + flag true:** context không lỗi class loading và không tạo bean integration.
5. **SDK present + custom service:** bean mặc định back off.
6. **SDK present + custom client:** client mặc định back off nếu thư viện hỗ trợ extension point này.
7. **Consumer không có service:** ứng dụng vẫn khởi động nếu tính năng thực sự optional.
8. **Cấu hình bật nhưng endpoint/credential sai:** kết quả đúng hợp đồng fail-fast hoặc disabled đã công bố.

Dùng `ApplicationContextRunner` để kiểm tra auto-configuration nhanh trong các context độc lập. Dùng `FilteredClassLoader` cho trường hợp dependency không có. Với một ứng dụng thật, bổ sung ít nhất một integration test khởi động bằng `@SpringBootTest` hoặc chạy packaged starter trên classpath tiêu thụ để phát hiện lỗi đăng ký imports và dependency propagation.

Khi debug, chạy với `--debug` để xem Condition Evaluation Report. Tìm `OnClassCondition` và `OnPropertyCondition` của nested configuration. Nếu không thấy source, kiểm tra auto-config có được công bố qua `AutoConfiguration.imports` và có bị exclude hay không.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** SDK `CatalogClient` không có trên runtime classpath nhưng feature flag là true. `@ConditionalOnProperty` có thể tự làm bean xuất hiện không?

**Đáp án:** Không. Classpath condition `@ConditionalOnClass` vẫn không khớp; property không cài thêm dependency.

**Câu 2.** Vì sao đặt optional type trong nested configuration có `@ConditionalOnClass`?

**Đáp án:** Để Spring Boot đọc và đánh giá classpath condition trước khi xử lý các method/constructor/type reference phụ thuộc SDK, tránh làm outer auto-configuration lỗi khi SDK vắng mặt.

**Câu 3.** Với `havingValue="true", matchIfMissing=false`, người dùng không khai báo property thì feature có bật không?

**Đáp án:** Không. Đây là chính sách opt-in; người dùng phải đặt true.

**Câu 4.** Với `matchIfMissing=true`, người dùng đặt false thì điều kiện có khớp không?

**Đáp án:** Không. matchIfMissing chỉ áp dụng khi khóa không có mặt; giá trị false vẫn không bằng true.

**Câu 5.** `@ConditionalOnMissingBean(CatalogService.class)` giải quyết tình huống nào?

**Đáp án:** Cho phép auto-configuration nhường bean service mặc định khi ứng dụng đã cung cấp bean phù hợp.

**Câu 6.** SDK có mặt, flag false, ứng dụng vẫn có custom CatalogService do user config tạo. Flag trên nested auto-config có xóa bean đó không?

**Đáp án:** Không. Condition chỉ ngăn nhánh auto-configuration đó được áp dụng; nó không xóa bean từ cấu hình người dùng độc lập.

**Câu 7.** Vì sao consumer nên dùng ObjectProvider cho CatalogService?

**Đáp án:** Vì service có thể không tồn tại khi SDK thiếu hoặc feature bị tắt. ObjectProvider cho phép ứng dụng xử lý trạng thái không có bean mà vẫn khởi động.

## 14. Ghi nhớ

- **Dependency có mặt** và **feature được bật** là hai điều kiện độc lập.
- Dùng `@ConditionalOnClass(name=...)` để kiểm tra optional SDK; đặt điều kiện trên nested static configuration để cô lập các tham chiếu tới optional type.
- Dùng `@ConditionalOnProperty(havingValue="true")` để người dùng kiểm soát feature; chọn `matchIfMissing=false` cho opt-in hoặc `true` cho opt-out.
- Dùng `@ConditionalOnMissingBean` để ứng dụng thay implementation mặc định.
- Không inject bắt buộc một bean có thể vắng mặt; cân nhắc `ObjectProvider`, `Optional` hoặc điều kiện trên component tiêu thụ.
- Kiểm thử classpath thực sự thiếu dependency bằng `FilteredClassLoader`; chỉ kiểm tra property false chưa đủ.
- Auto-configuration không xóa user bean độc lập. Hãy định nghĩa rõ feature flag điều khiển bean mặc định hay toàn bộ đường sử dụng tính năng.

### Tài liệu chính thức

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — ConditionalOnClass API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3 — ConditionalOnProperty API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 — ConditionalOnMissingBean API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 — ApplicationContextRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 — FilteredClassLoader API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
