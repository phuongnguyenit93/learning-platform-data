# Configuration property như hợp đồng module

Bài này thuộc chương **Model và Spring beans** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp mô hình hóa ứng dụng Spring Boot thành các application module có trách nhiệm, API và quan hệ phụ thuộc rõ ràng. Một module không chỉ cung cấp Spring bean hoặc application event; nó còn có thể nhận cấu hình từ môi trường triển khai thông qua các configuration property.

Các property này tạo thành một **hợp đồng cấu hình** giữa module và môi trường chạy ứng dụng. Module định nghĩa tên khóa, kiểu dữ liệu, ý nghĩa, giá trị mặc định và giới hạn hợp lệ; người vận hành cung cấp giá trị qua YAML, properties, environment variable hoặc nguồn cấu hình khác. Khi hợp đồng được thiết kế rõ, module có thể thay đổi cách triển khai bên trong mà vẫn giữ cách cấu hình ổn định.

## 1. Configuration property nằm ở đâu trong mô hình module?

Một application module thường có ba phần:

- **Provided interface:** Spring bean và application event mà module công khai cho module khác.
- **Internal implementation:** các component, repository, entity và adapter chỉ phục vụ nội bộ.
- **Required interface:** những gì module cần từ bên ngoài, bao gồm bean dependency, event mà module lắng nghe và configuration property mà module sử dụng.

Configuration property thể hiện cách module nhận tham số từ môi trường. Ví dụ, inventory cần biết ngưỡng bổ sung hàng và thời gian giữ chỗ mặc định. Những giá trị này ảnh hưởng đến hành vi nghiệp vụ, nhưng người vận hành cần cấu hình chúng theo môi trường dev, staging hoặc production.

~~~text
                 Môi trường triển khai
          application.yaml / ENV / Config Server
                         |
                         | cấu hình theo prefix
                         v
                Module inventory
          ┌────────────────────────────┐
          │ InventoryProperties       │
          │ restock-threshold          │
          │ reservation-timeout        │
          │                            │
          │ InventoryPolicy            │
          │ StockAvailability          │
          └────────────────────────────┘
                         |
                         | API nghiệp vụ
                         v
                  Module order
~~~

Spring Modulith xem configuration properties là một phần thông tin của application module. Application Module Canvas có thể liệt kê lớp `@ConfigurationProperties` và các property mà module công bố, cùng kiểu dữ liệu và mô tả của chúng.

Điều này giúp nhóm nhận diện được module sở hữu cấu hình nào. Nó không có nghĩa lớp cấu hình phải trở thành Java API cho mọi module khác sử dụng.

## 2. Vì sao property prefix là một hợp đồng?

Giả sử inventory dùng hai giá trị:

- `restock-threshold`: số lượng tồn kho mà khi thấp hơn ngưỡng, module phát tín hiệu cần bổ sung hàng.
- `reservation-timeout`: thời gian một lần giữ hàng có hiệu lực.

Nếu khai báo bằng các tên chung như `threshold` hoặc `timeout`, người đọc khó xác định module nào sở hữu chúng. Khi nhiều module cùng dùng tên ngắn, cấu hình dễ bị trùng và khó quản lý.

Nên đặt prefix theo namespace của module:

~~~yaml
acme:
  shop:
    inventory:
      restock-threshold: 12
      reservation-timeout: 30s
~~~

Hợp đồng cấu hình ở đây gồm:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Prefix | `acme.shop.inventory` | Namespace do module inventory sở hữu. |
| Property key | `restock-threshold` | Tên tham số mà môi trường cần cung cấp. |
| Type | `Integer` | Kiểu dữ liệu được bind. |
| Unit | Số lượng sản phẩm | Cách diễn giải giá trị. |
| Default/required | Bắt buộc hoặc có giá trị mặc định | Hành vi khi cấu hình bị thiếu. |
| Constraint | Lớn hơn hoặc bằng 0 | Miền giá trị được chấp nhận. |
| Description | Ngưỡng phát tín hiệu bổ sung hàng | Ý nghĩa dành cho người vận hành. |

Đổi prefix hoặc tên key có thể làm cấu hình hiện tại không còn được bind. Vì vậy, hãy xem các key đã công bố là một phần hợp đồng cần quản lý tương thích qua các lần phát hành.

## 3. Gom cấu hình thành kiểu có cấu trúc với @ConfigurationProperties

Spring Boot hỗ trợ `@ConfigurationProperties` để bind một nhóm property vào một đối tượng có kiểu dữ liệu. Cách này phù hợp khi một module có nhiều tham số liên quan.

Ví dụ, đặt lớp cấu hình trong package nội bộ của inventory:

~~~java
package com.acme.shop.inventory.internal.config;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties("acme.shop.inventory")
@Validated
public record InventoryProperties(
        @Min(0) int restockThreshold,
        @NotNull Duration reservationTimeout
) {
}
~~~

Các chi tiết đáng chú ý:

- `@ConfigurationProperties("acme.shop.inventory")` khai báo prefix sở hữu nhóm cấu hình.
- `restockThreshold` được bind từ key `restock-threshold`.
- `reservationTimeout` dùng `Duration`, cho phép biểu diễn thời gian như `30s` hoặc `2m`.
- `@Validated` bật kiểm tra các constraint trên cấu hình.
- `@Min(0)` ngăn ngưỡng tồn kho âm; `@NotNull` yêu cầu thời gian giữ chỗ phải có giá trị.

Lớp `InventoryProperties` chỉ mô tả dữ liệu cấu hình. Hãy giữ nó đơn giản, không đặt logic nghiệp vụ hoặc phụ thuộc bean khác vào trong lớp này.

## 4. Đăng ký configuration properties thành Spring bean

`@ConfigurationProperties` mô tả cách bind dữ liệu, nhưng ứng dụng vẫn cần đăng ký kiểu đó thành bean để inject.

Có thể bật scanning trên lớp ứng dụng:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` mặc định quét từ package chứa lớp khai báo annotation và các package con. Nếu dự án muốn giới hạn phạm vi, có thể chỉ định package cụ thể.

Một cách khác là đăng ký tường minh bằng `@EnableConfigurationProperties`:

~~~java
package com.acme.shop.inventory.internal.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryProperties.class)
class InventoryConfiguration {
}
~~~

Chọn một cách phù hợp với cấu trúc dự án và tránh đăng ký cùng một configuration properties type theo nhiều cách không cần thiết.

## 5. Module sử dụng cấu hình của chính nó

Sau khi được đăng ký, module inventory có thể inject `InventoryProperties` vào component nội bộ:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.internal.config.InventoryProperties;
import org.springframework.stereotype.Component;

@Component
class InventoryPolicy {

    private final InventoryProperties properties;

    InventoryPolicy(InventoryProperties properties) {
        this.properties = properties;
    }

    boolean shouldRestock(int availableQuantity) {
        return availableQuantity < properties.restockThreshold();
    }
}
~~~

Component này dùng cấu hình để áp dụng quy tắc nghiệp vụ. Khi môi trường thay đổi `restock-threshold`, module có thể thay đổi hành vi mà không cần sửa mã nguồn.

Đây là ranh giới sở hữu tốt: module inventory định nghĩa property, bind property và sử dụng property trong nội bộ. Module khác không cần biết ngưỡng bổ sung hàng được lưu trong trường nào hoặc quy tắc được cài đặt ra sao.

## 6. Cấu hình từ YAML, properties và môi trường

Với prefix đã khai báo, Spring Boot có thể bind từ nhiều nguồn cấu hình.

YAML:

~~~yaml
acme:
  shop:
    inventory:
      restock-threshold: 12
      reservation-timeout: 30s
~~~

File properties:

~~~properties
acme.shop.inventory.restock-threshold=12
acme.shop.inventory.reservation-timeout=30s
~~~

Environment variable có thể cung cấp cùng nhóm giá trị trong môi trường triển khai. Spring Boot hỗ trợ relaxed binding, nên cách viết key trong môi trường có thể khác dạng kebab-case của YAML.

Ví dụ cấu hình qua dòng lệnh:

~~~bash
java -jar shop.jar \
  --acme.shop.inventory.restock-threshold=20 \
  --acme.shop.inventory.reservation-timeout=45s
~~~

Spring Boot có thứ tự ưu tiên giữa các property source. Một giá trị từ nguồn có ưu tiên cao hơn có thể ghi đè giá trị trong file cấu hình đóng gói cùng ứng dụng. Nhờ đó, cùng một module có thể chạy với các tham số khác nhau ở từng môi trường.

## 7. Property contract cần mô tả rõ hơn tên và kiểu

Một key tồn tại chưa đủ để trở thành hợp đồng dễ sử dụng. Người vận hành cần biết ý nghĩa và quy tắc của giá trị.

Ví dụ:

| Property | Type | Quy tắc | Mô tả |
|---|---|---|---|
| `acme.shop.inventory.restock-threshold` | `Integer` | `>= 0` | Số lượng tồn kho thấp hơn ngưỡng sẽ kích hoạt đánh giá bổ sung hàng. |
| `acme.shop.inventory.reservation-timeout` | `Duration` | `> 0` theo quy tắc nghiệp vụ | Thời gian giữ chỗ tồn kho trước khi hết hiệu lực. |

Khi thiết kế một property, hãy trả lời:

1. Ai sở hữu property này?
2. Giá trị được đo bằng đơn vị nào?
3. Có giá trị mặc định hay bắt buộc phải cấu hình?
4. Giá trị hợp lệ nằm trong khoảng nào?
5. Khi thiếu hoặc sai kiểu, ứng dụng xử lý ra sao?
6. Thay đổi giá trị có ảnh hưởng tới hành vi nghiệp vụ nào?

Tránh những key như `enabled`, `limit` hoặc `timeout` nếu chúng không nằm trong namespace rõ ràng hoặc không có mô tả đủ cụ thể.

## 8. Validation bảo vệ hợp đồng cấu hình

Nếu giá trị cấu hình sai, ứng dụng có thể hoạt động sai ngay cả khi code đã biên dịch thành công. Spring Boot hỗ trợ validation cho `@ConfigurationProperties` khi lớp được đánh dấu `@Validated` và có implementation Jakarta Bean Validation trên classpath.

Ví dụ bổ sung giới hạn cho thời gian giữ chỗ:

~~~java
package com.acme.shop.inventory.internal.config;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties("acme.shop.inventory")
@Validated
public record InventoryProperties(
        @Min(0) int restockThreshold,
        @NotNull Duration reservationTimeout
) {
}
~~~

Các constraint như `@Min`, `@NotNull` giúp kiểm tra giá trị khi binding. Với quy tắc phức tạp hơn, có thể dùng custom validator hoặc kiểm tra ở constructor/service khởi tạo tùy thiết kế.

Nếu cấu hình không hợp lệ, nên để ứng dụng báo lỗi sớm khi khởi động thay vì để một giá trị bất thường âm thầm ảnh hưởng tới nghiệp vụ.

## 9. Không dùng configuration properties của module khác làm API nghiệp vụ

Giả sử order muốn biết ngưỡng tồn kho của inventory. Một cách làm dễ gây coupling là inject trực tiếp `InventoryProperties`:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.internal.config.InventoryProperties;

class PlaceOrderHandler {

    private final InventoryProperties inventoryProperties;

    PlaceOrderHandler(InventoryProperties inventoryProperties) {
        this.inventoryProperties = inventoryProperties;
    }
}
~~~

Cách này làm order phụ thuộc vào chi tiết cấu hình nội bộ của inventory. Order biết tên prefix, các field và cách inventory lưu tham số. Nếu inventory đổi cấu trúc cấu hình, module order có thể phải thay đổi theo.

Nếu order cần biết khả năng đặt hàng, hãy phụ thuộc vào hợp đồng nghiệp vụ do inventory công khai:

~~~java
package com.acme.shop.inventory;

public interface StockAvailability {

    boolean hasAvailableStock(String productCode, int quantity);
}
~~~

Inventory triển khai hợp đồng và tự sử dụng `InventoryProperties` bên trong:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.StockAvailability;
import com.acme.shop.inventory.internal.config.InventoryProperties;
import com.acme.shop.inventory.internal.persistence.StockRepository;
import org.springframework.stereotype.Component;

@Component
class StockAvailabilityService implements StockAvailability {

    private final InventoryProperties properties;
    private final StockRepository stockRepository;

    StockAvailabilityService(
            InventoryProperties properties,
            StockRepository stockRepository
    ) {
        this.properties = properties;
        this.stockRepository = stockRepository;
    }

    @Override
    public boolean hasAvailableStock(String productCode, int quantity) {
        int available = stockRepository.findAvailableQuantity(productCode);

        if (available < properties.restockThreshold()) {
            // Kích hoạt quy trình bổ sung hàng theo chính sách nội bộ.
        }

        return available >= quantity;
    }
}
~~~

Trong ví dụ, repository cung cấp số lượng tồn kho thực tế; property chỉ điều chỉnh thời điểm inventory đánh giá bổ sung hàng. Điều kiện trả lời order vẫn dựa trên số lượng hiện có. Module order chỉ gọi `StockAvailability`, không đọc trực tiếp cấu hình inventory.

Configuration property là hợp đồng cấu hình với môi trường triển khai. API nghiệp vụ là hợp đồng giữa các module. Hai loại hợp đồng có thể liên quan nhưng không nên thay thế cho nhau.

## 10. Spring Modulith thể hiện configuration properties trong Module Canvas

Spring Modulith cung cấp `Documenter` để sinh tài liệu cho mô hình module. Application Module Canvas là bảng tóm tắt các thành phần quan trọng của từng module, bao gồm:

- Base package.
- Spring beans được công khai.
- Aggregate root.
- Application event được phát và được lắng nghe.
- Configuration properties và các property được mô tả.

Ví dụ tạo Module Canvas:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

new Documenter(modules).writeModuleCanvases();
~~~

Canvas có thể thể hiện cấu hình của inventory như sau:

~~~text
Module: inventory

Configuration properties
  InventoryProperties

Properties
  acme.shop.inventory.restock-threshold
    Type: Integer
    Description: Ngưỡng đánh giá bổ sung hàng

  acme.shop.inventory.reservation-timeout
    Type: Duration
    Description: Thời gian giữ chỗ tồn kho
~~~

Để Spring Modulith trích xuất metadata property cho tài liệu, dự án cần dùng artifact `spring-boot-configuration-processor`. Nếu thiếu processor, phần metadata property có thể không xuất hiện đầy đủ trong Module Canvas.

## 11. Bật configuration metadata processor

Với Gradle, khai báo processor trong cấu hình dependency:

~~~groovy
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

Với Maven, thêm artifact `spring-boot-configuration-processor` vào cấu hình annotation processor phù hợp của dự án. Khi dùng Spring Boot dependency management, thông thường không cần tự ghi version riêng nếu BOM đã quản lý phiên bản.

Processor tạo metadata từ các kiểu `@ConfigurationProperties`, giúp IDE hỗ trợ gợi ý key và cung cấp thông tin cho công cụ tài liệu như Module Canvas.

Lưu ý: processor sinh metadata trong quá trình biên dịch; nó không tự đăng ký configuration properties thành bean. Việc đăng ký vẫn cần `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

## 12. Kiểm thử binding và validation

Có thể kiểm tra module nhận đúng cấu hình bằng Spring Boot test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "acme.shop.inventory.restock-threshold=15",
    "acme.shop.inventory.reservation-timeout=45s"
})
class InventoryPropertiesTests {

    @Autowired
    InventoryProperties properties;

    @Test
    void bindsInventoryConfiguration() {
        assertThat(properties.restockThreshold()).isEqualTo(15);
        assertThat(properties.reservationTimeout()).hasSeconds(45);
    }
}
~~~

Test này kiểm tra Spring Boot binding và xác nhận kiểu dữ liệu sau khi bind. Có thể bổ sung test cho giá trị thiếu, sai kiểu hoặc vi phạm constraint để bảo đảm ứng dụng từ chối cấu hình không hợp lệ.

Phân biệt hai lớp kiểm tra:

| Kiểm tra | Công cụ | Mục tiêu |
|---|---|---|
| Binding và validation property | Spring Boot context/test | Giá trị cấu hình có bind được và thỏa constraint không? |
| Module architecture | `ApplicationModules.verify()` | Module có vi phạm ranh giới package và dependency không? |
| Tài liệu hợp đồng cấu hình | `Documenter.writeModuleCanvases()` | Module đang công bố bean, event và property nào? |

`ApplicationModules.verify()` không thay thế việc kiểm tra giá trị cấu hình khi Spring Boot khởi động. Module Canvas cũng là tài liệu mô hình, không phải cơ chế tự động kiểm tra mọi giá trị trong file YAML.

## 13. Quản lý thay đổi và tương thích property contract

Khi module đã được triển khai ở nhiều môi trường, property key trở thành một phần hợp đồng vận hành. Hãy quản lý thay đổi cẩn thận:

- **Thêm property:** xác định giá trị mặc định hoặc yêu cầu cấu hình mới.
- **Đổi tên property:** cung cấp giai đoạn chuyển tiếp nếu cần hỗ trợ cấu hình cũ.
- **Xóa property:** kiểm tra các file YAML, environment variable, Helm chart và pipeline triển khai còn sử dụng key cũ không.
- **Đổi type:** đánh giá khả năng bind dữ liệu hiện tại và hành vi khi chuyển đổi.
- **Đổi unit:** làm rõ đơn vị cũ/mới; ví dụ milliseconds sang Duration có thể làm thay đổi đáng kể giá trị.
- **Đổi default:** xem xét tác động tới tất cả môi trường không khai báo giá trị riêng.

Không nên dùng cùng một key cho nhiều module chỉ vì tên tham số giống nhau. Hai module có thể có ngưỡng hoặc timeout riêng với ngữ nghĩa khác nhau; mỗi module nên sở hữu namespace riêng.

## 14. Bảo vệ thông tin nhạy cảm trong cấu hình

Một số property chứa mật khẩu, token hoặc khóa truy cập. Chúng vẫn thuộc hợp đồng cấu hình của module, nhưng cần được quản lý theo chính sách bảo mật.

- Không ghi giá trị bí mật thật vào mã nguồn hoặc tài liệu Module Canvas.
- Dùng environment variable, secret manager hoặc configuration tree phù hợp cho giá trị nhạy cảm.
- Chỉ log tên property hoặc trạng thái đã cấu hình khi cần chẩn đoán; tránh in giá trị bí mật.
- Giữ quyền truy cập cấu hình theo nguyên tắc tối thiểu.
- Tách property thông thường khỏi secret nếu chúng có vòng đời và quyền truy cập khác nhau.

Module Canvas mô tả metadata như tên, kiểu và nội dung property; tài liệu này không nên chứa giá trị cấu hình thật của từng môi trường.

## 15. Quy trình thiết kế configuration property như hợp đồng module

1. **Xác định module sở hữu.** Property phục vụ capability nào và module nào chịu trách nhiệm về hành vi đó?
2. **Chọn prefix riêng.** Dùng namespace ổn định, ví dụ `acme.shop.inventory`.
3. **Thiết kế kiểu dữ liệu.** Ưu tiên `@ConfigurationProperties` có cấu trúc và kiểu rõ ràng.
4. **Mô tả ý nghĩa.** Ghi đơn vị, default, tính bắt buộc và miền giá trị.
5. **Đăng ký bean.** Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
6. **Áp dụng trong module sở hữu.** Inject property vào component nội bộ cần nó.
7. **Giữ API nghiệp vụ độc lập.** Module khác gọi bean/event API thay vì đọc trực tiếp configuration properties nội bộ.
8. **Bật metadata processor.** Thêm `spring-boot-configuration-processor` để IDE và Module Canvas có metadata.
9. **Sinh Module Canvas.** Dùng `Documenter.writeModuleCanvases()` để review cấu hình cùng các hợp đồng khác.
10. **Kiểm thử binding.** Kiểm tra giá trị hợp lệ, giá trị thiếu và constraint.
11. **Quản lý tương thích.** Xem key, type và default là hợp đồng cần review khi phát hành phiên bản mới.

## Ghi nhớ

Configuration property là hợp đồng giữa module và môi trường cấu hình: module sở hữu prefix, key, kiểu dữ liệu, ý nghĩa, default và constraint; môi trường cung cấp giá trị qua YAML, properties hoặc các nguồn externalized configuration. Spring Modulith có thể đưa metadata cấu hình vào Application Module Canvas để nhóm nhìn thấy module nào công bố property nào.

Hãy dùng `@ConfigurationProperties` để tạo hợp đồng có kiểu, đăng ký bean đúng cách, validate giá trị và giữ property của module trong namespace riêng. Module khác nên sử dụng API nghiệp vụ được công khai thay vì phụ thuộc trực tiếp vào lớp cấu hình nội bộ. Kết hợp kiểm thử binding với tài liệu Module Canvas giúp cấu hình trở thành một phần có thể review và quản lý trong thiết kế modular monolith.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html)
