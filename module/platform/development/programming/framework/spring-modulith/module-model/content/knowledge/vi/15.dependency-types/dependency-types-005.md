# Configuration property như một required interface

Một application module không chỉ cung cấp API cho module khác. Nó còn cần những đầu vào để thực hiện nghiệp vụ: giới hạn tồn kho, thời gian chờ, địa chỉ dịch vụ bên ngoài, chính sách thử lại hoặc cờ bật tắt một tính năng. Trong Spring Modulith, các cấu hình mà module cần từ môi trường chạy là một phần của **required interface** của module.

Spring Boot cung cấp cơ chế khai báo và bind những giá trị này bằng `@ConfigurationProperties`. Spring Modulith có thể nhận diện metadata của các configuration properties thuộc module và đưa chúng vào Application Module Canvas. Nhờ đó, nhóm phát triển và người vận hành nhìn thấy module cần những cấu hình nào, ý nghĩa của chúng và kiểu dữ liệu tương ứng.

Điểm quan trọng là configuration property biểu diễn một yêu cầu đối với môi trường cấu hình. Nó không phải API nghiệp vụ để module khác gọi, cũng không tự tạo dependency giữa hai application module.

## 1. Provided interface và required interface

Một application module có thể được nhìn từ ba phần:

| Phần | Ý nghĩa | Ví dụ trong module `inventory` |
| --- | --- | --- |
| Provided interface | Năng lực module cung cấp cho bên khác | `InventoryManagement`, sự kiện `StockReserved` |
| Internal implementation | Thành phần chỉ phục vụ bên trong module | `StockRepository`, `StockReservationService` |
| Required interface | Những thứ module cần từ bên ngoài để hoạt động | API của module khác, sự kiện module lắng nghe, cấu hình vận hành |

Ví dụ, module `inventory` cung cấp thao tác giữ hàng. Để quyết định khi nào phát cảnh báo thiếu hàng, nó cần một ngưỡng `restock-threshold`. Ngưỡng đó do môi trường triển khai cung cấp thông qua cấu hình.

~~~text
                Môi trường triển khai
             application.yml / env vars
                         |
                         | restock-threshold
                         v
                 +---------------+
                 |   inventory   |
                 |---------------|
                 | Required      |
                 | interface     |
                 |               |
                 | Inventory     |
                 | Properties    |
                 +---------------+
                         |
                         v
                 Quy tắc tồn kho
                         |
                         v
                 StockShort event
~~~

Module cần cấu hình để quyết định hành vi. Giá trị thực tế có thể đến từ file YAML, biến môi trường, tham số dòng lệnh hoặc một nguồn cấu hình khác mà Spring Boot hỗ trợ.

## 2. Vì sao configuration property thuộc required interface?

Required interface mô tả những điều kiện hoặc dịch vụ mà module cần để thực hiện trách nhiệm của nó. Một module có thể cần:

- Một Spring bean do module khác cung cấp.
- Một loại application event mà module đăng ký lắng nghe.
- Một nhóm giá trị cấu hình do môi trường cung cấp.

Configuration property thuộc nhóm thứ ba. Ví dụ, `inventory` cần biết ngưỡng tồn kho tối thiểu. Module không tự quyết định giá trị triển khai; môi trường cấu hình cung cấp giá trị phù hợp với từng môi trường.

Điều này giúp tách chính sách vận hành khỏi mã nghiệp vụ. Cùng một module có thể chạy ở môi trường phát triển với ngưỡng nhỏ, ở môi trường thử nghiệm với ngưỡng khác và ở production với giá trị do đội vận hành quản lý.

Một prefix cấu hình riêng cũng làm rõ quyền sở hữu. Khi thấy `acme.shop.inventory.restock-threshold`, người đọc có thể nhận ra cấu hình này thuộc module `inventory`, thay vì một thuộc tính dùng chung không rõ chủ sở hữu.

## 3. Gom cấu hình của module bằng `@ConfigurationProperties`

Không nên rải nhiều chuỗi cấu hình qua các lớp bằng `@Value` nếu chúng cùng mô tả một nhóm thiết lập của module. Hãy gom chúng vào một kiểu cấu hình có prefix rõ ràng.

Ví dụ, tạo `InventoryProperties.java` trong module `inventory`:

~~~java
package com.acme.shop.inventory.internal.config;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.shop.inventory")
@Validated
public record InventoryProperties(

        @Min(1) int restockThreshold,

        @NotNull Duration reservationTimeout,

        boolean enabled
) {
}
~~~

Kiểu này gom ba thuộc tính có liên quan:

| Thuộc tính Java | Key cấu hình | Ý nghĩa |
| --- | --- | --- |
| `restockThreshold` | `acme.shop.inventory.restock-threshold` | Ngưỡng để đánh giá hàng sắp thiếu |
| `reservationTimeout` | `acme.shop.inventory.reservation-timeout` | Thời gian giữ hàng tối đa |
| `enabled` | `acme.shop.inventory.enabled` | Cho phép module xử lý chức năng tồn kho |

`@ConfigurationProperties` khai báo prefix và yêu cầu Spring Boot bind các giá trị có prefix đó vào đối tượng. `@Validated` bật kiểm tra Bean Validation khi đối tượng được bind; `@Min(1)` và `@NotNull` thể hiện các điều kiện của cấu hình. Để các constraint được thực thi, ứng dụng cần có implementation Jakarta Bean Validation trên classpath.

Record phù hợp với nhóm cấu hình chỉ đọc sau khi khởi tạo. Spring Boot hỗ trợ constructor binding cho record. Nếu dùng class Java thông thường, có thể khai báo các thuộc tính cùng getter/setter hoặc dùng constructor binding theo cách phù hợp với phiên bản Spring Boot.

Đặt kiểu cấu hình trong package nội bộ như `inventory.internal.config` nếu module khác không cần tham chiếu trực tiếp đến bean này. `@ConfigurationPropertiesScan` vẫn có thể tìm thấy kiểu trong package con của package ứng dụng; module sử dụng nên gọi API nghiệp vụ của `inventory` thay vì inject `InventoryProperties`.

## 4. Đăng ký configuration properties với Spring Boot

Spring Boot cần biết kiểu `InventoryProperties` để tạo bean và bind giá trị. Có hai cách phổ biến.

### Dùng configuration properties scanning

Đặt `@ConfigurationPropertiesScan` trên lớp ứng dụng:

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

Theo mặc định, việc scan bắt đầu từ package của lớp được đánh dấu và đi xuống các package con. Vì `InventoryProperties` nằm dưới `com.acme.shop`, Spring Boot có thể tìm thấy kiểu này.

### Đăng ký tường minh

Nếu muốn đăng ký một số kiểu cấu hình cụ thể, dùng `@EnableConfigurationProperties`:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.inventory.internal.config.InventoryProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryProperties.class)
class InventoryConfiguration {
}
~~~

Chọn một cách phù hợp với cách ứng dụng tổ chức cấu hình. Tránh đăng ký cùng một kiểu theo nhiều cơ chế khác nhau nếu không có lý do rõ ràng.

## 5. Cung cấp giá trị từ môi trường

Trong `application.yml`, các key có thể được khai báo như sau:

~~~yaml
acme:
  shop:
    inventory:
      restock-threshold: 12
      reservation-timeout: 15s
      enabled: true
~~~

Spring Boot hỗ trợ relaxed binding, nên tên thuộc tính trong cấu hình dạng kebab-case được bind vào thành phần record dạng camelCase. `Duration` cũng được chuyển đổi từ biểu diễn thời gian như `15s`, `2m` hoặc `1h`.

Trong môi trường container, cùng các giá trị đó có thể được truyền bằng biến môi trường:

~~~text
ACME_SHOP_INVENTORY_RESTOCK_THRESHOLD=12
ACME_SHOP_INVENTORY_RESERVATION_TIMEOUT=15s
ACME_SHOP_INVENTORY_ENABLED=true
~~~

Như vậy, module giữ nguyên mã nguồn trong khi môi trường triển khai có thể thay đổi giá trị theo nhu cầu. Những giá trị nhạy cảm như mật khẩu, token hoặc khóa truy cập cũng có thể được cấp qua cơ chế secret/configuration của nền tảng triển khai; không nên ghi bí mật trực tiếp vào file cấu hình được commit.

## 6. Sử dụng cấu hình bên trong module

Sau khi Spring Boot đăng ký bean, các thành phần thuộc module có thể nhận `InventoryProperties` qua constructor injection:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.internal.config.InventoryProperties;
import org.springframework.stereotype.Service;

@Service
class StockMonitoringService {

    private final InventoryProperties properties;

    StockMonitoringService(InventoryProperties properties) {
        this.properties = properties;
    }

    boolean shouldRestock(int availableQuantity) {
        return properties.enabled()
                && availableQuantity <= properties.restockThreshold();
    }
}
~~~

Thành phần nội bộ sử dụng cấu hình để thực hiện quy tắc của module. Module khác không cần lấy `InventoryProperties` để tự quyết định cách tồn kho hoạt động; nếu cần hành vi đó, hãy gọi API nghiệp vụ được công bố bởi `inventory`.

Điều này giữ quyền sở hữu cấu hình trong đúng module. Module `order` có thể yêu cầu giữ hàng qua `InventoryManagement`, nhưng không nên đọc `InventoryProperties` để tự diễn giải ngưỡng tồn kho hoặc thời gian giữ hàng.

## 7. Cấu hình bắt buộc, giá trị mặc định và validation

Configuration property là hợp đồng với môi trường, vì vậy cần xác định rõ giá trị nào bắt buộc và giá trị nào có mặc định.

| Trường hợp | Cách thể hiện | Hành vi cần dự kiến |
| --- | --- | --- |
| Giá trị bắt buộc | Constraint như `@NotNull`, `@Min`, `@NotBlank` | Ứng dụng không nên khởi động nếu cấu hình không hợp lệ |
| Giá trị có mặc định | Khởi tạo giá trị mặc định trong kiểu cấu hình hoặc dùng cơ chế default phù hợp | Module có hành vi xác định khi môi trường không ghi đè |
| Giá trị phụ thuộc môi trường | Cung cấp từ YAML, biến môi trường hoặc config server | Cùng một module có thể chạy với giá trị khác nhau |
| Giá trị có quan hệ | Kiểm tra bằng class-level constraint hoặc logic xác thực phù hợp | Bảo đảm các thuộc tính phối hợp thành cấu hình hợp lệ |

Ví dụ, `restockThreshold` phải lớn hơn 0. Nếu môi trường bỏ qua giá trị này, giá trị mặc định của kiểu `int` là `0` và constraint `@Min(1)` sẽ làm quá trình bind/validation thất bại. Đây là cách biến một yêu cầu cấu hình thành điều kiện rõ ràng khi khởi động.

Không nên đặt mặc định tùy tiện cho một thuộc tính mà thiếu nó sẽ khiến nghiệp vụ chạy sai. Ngược lại, cũng không nên bắt người vận hành khai báo mọi giá trị nếu module có thể cung cấp mặc định an toàn và có ý nghĩa.

## 8. Spring Modulith ghi nhận cấu hình trong Application Module Canvas

`ApplicationModules` tạo mô hình module từ codebase. `Documenter` có thể dùng mô hình này để tạo Application Module Canvas, trong đó có phần cấu hình thuộc module.

Ví dụ:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentation {

    void generate() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        new Documenter(modules).writeModuleCanvases();
    }
}
~~~

Canvas của `inventory` có thể chứa các mục tương tự:

~~~text
Base package
  com.acme.shop.inventory

Configuration properties
  com.acme.shop.inventory.internal.config.InventoryProperties

Properties
  acme.shop.inventory.restock-threshold
    Type: Integer
    Description: Ngưỡng để đánh giá hàng sắp thiếu
  acme.shop.inventory.reservation-timeout
    Type: Duration
  acme.shop.inventory.enabled
    Type: Boolean
~~~

Để Spring Modulith trích xuất metadata cấu hình, cần sử dụng `spring-boot-configuration-processor` trong quá trình biên dịch. Annotation processor của Spring Boot đọc các kiểu có `@ConfigurationProperties` và sinh metadata, thường ở `META-INF/spring-configuration-metadata.json`. Spring Modulith dùng metadata đó để trình bày cấu hình trong canvas.

Với Gradle:

~~~groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-configuration-processor"
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Annotation processor phục vụ việc sinh metadata và hỗ trợ IDE/documentation. Nó không phải cơ chế bind giá trị lúc chạy. Việc bind và validation vẫn do Spring Boot thực hiện.

## 9. Viết mô tả để cấu hình trở thành hợp đồng dễ hiểu

Tên key và kiểu dữ liệu mới chỉ cho biết một phần ý nghĩa. Hãy viết mô tả ngắn cho từng thuộc tính để người vận hành hiểu khi nào nên thay đổi nó.

Với class Java thông thường, có thể dùng Javadoc trên field để annotation processor đưa mô tả vào metadata:

~~~java
/**
 * Configuration for inventory behavior.
 */
@ConfigurationProperties(prefix = "acme.shop.inventory")
public class InventoryProperties {

    /**
     * Minimum available quantity before a restock signal is raised.
     */
    private int restockThreshold = 12;

    // getters and setters
}
~~~

Với record, mô tả thành phần có thể được cung cấp bằng Javadoc `@param` ở cấp record:

~~~java
/**
 * Inventory module configuration.
 *
 * @param restockThreshold Minimum quantity before restock is triggered.
 * @param reservationTimeout Maximum duration of a stock reservation.
 * @param enabled Whether inventory operations are enabled.
 */
@ConfigurationProperties(prefix = "acme.shop.inventory")
public record InventoryProperties(
        int restockThreshold,
        Duration reservationTimeout,
        boolean enabled
) {
}
~~~

Mô tả nên giải thích ý nghĩa nghiệp vụ, đơn vị, giới hạn hợp lệ và tác động khi thay đổi. Tránh các câu chung chung như “cấu hình tồn kho” hoặc lặp lại tên key.

## 10. Ranh giới module và quyền sở hữu configuration properties

Mỗi module nên sở hữu prefix và kiểu cấu hình phục vụ trách nhiệm của nó:

~~~text
com.acme.shop
├── inventory
│   └── internal
│       └── config
│           └── InventoryProperties
├── order
│   └── OrderProperties
└── payment
    └── PaymentProperties
~~~

Ví dụ:

| Module | Prefix cấu hình | Ví dụ thuộc tính |
| --- | --- | --- |
| `inventory` | `acme.shop.inventory` | `restock-threshold` |
| `order` | `acme.shop.order` | `maximum-items-per-order` |
| `payment` | `acme.shop.payment` | `provider-timeout` |

Không nên gom toàn bộ thuộc tính của ứng dụng vào một lớp `ApplicationProperties` khổng lồ nếu chúng thuộc các năng lực nghiệp vụ khác nhau. Cách đó làm mờ quyền sở hữu và khiến thay đổi cấu hình của một module tác động đến cấu trúc của các module khác.

Tương tự, module không nên import kiểu `PaymentProperties` của module `payment` để đọc cấu hình trực tiếp. Nếu module `order` cần biết một giao dịch thanh toán có được chấp nhận hay không, nó nên sử dụng API nghiệp vụ của `payment`. Cấu hình là chi tiết module sở hữu để thực hiện hợp đồng đó.

## 11. Phân biệt cấu hình ứng dụng, cấu hình module và cấu hình Spring Modulith

Ba nhóm cấu hình có phạm vi khác nhau:

| Nhóm | Ví dụ | Ai sở hữu? |
| --- | --- | --- |
| Cấu hình ứng dụng dùng chung | `server.port`, cấu hình logging | Ứng dụng hoặc nền tảng |
| Cấu hình nghiệp vụ của module | `acme.shop.inventory.restock-threshold` | Module `inventory` |
| Cấu hình framework Spring Modulith | `spring.modulith.events...` | Spring Modulith hoặc phần tích hợp tương ứng |

Bài học này nói về nhóm thứ hai: những giá trị module cần từ môi trường để thực hiện nghiệp vụ. Các thuộc tính bắt đầu bằng `spring.modulith.*` điều khiển hành vi của framework hoặc các tính năng Spring Modulith; chúng không tự động trở thành cấu hình nghiệp vụ của module `inventory`, `order` hay `payment`.

## 12. Những nhầm lẫn thường gặp

**Cho rằng configuration property là dependency giữa hai module.** Một property như `acme.shop.inventory.restock-threshold` là đầu vào cấu hình của `inventory`, thường do môi trường triển khai cung cấp. Nó không có nghĩa `inventory` phụ thuộc vào một application module khác.

**Cho rằng Spring Modulith bind giá trị cấu hình.** Spring Boot thực hiện binding, conversion và validation. Spring Modulith dùng mô hình module và metadata để tài liệu hóa các configuration properties thuộc module.

**Cho rằng annotation processor là bắt buộc để ứng dụng chạy.** `spring-boot-configuration-processor` hỗ trợ sinh metadata cho IDE và Application Module Canvas. Việc đăng ký và bind `@ConfigurationProperties` là trách nhiệm của Spring Boot.

**Dùng `@Value` cho mọi thuộc tính.** `@Value` hữu ích cho một giá trị đơn lẻ, nhưng một nhóm thiết lập liên quan thường dễ quản lý và tài liệu hóa hơn khi được gom bằng `@ConfigurationProperties`.

**Để module khác đọc trực tiếp properties của module sở hữu.** Điều này làm lộ quyết định cấu hình và tăng coupling. Hãy để module sở hữu cấu hình và cung cấp hành vi qua API.

**Không mô tả hoặc xác thực thuộc tính.** Key không có ý nghĩa, đơn vị hoặc giới hạn rõ ràng khiến cấu hình khó vận hành và dễ gây lỗi lúc chạy.

## 13. Checklist thiết kế configuration property cho module

- [ ] Xác định giá trị môi trường mà module thực sự cần để thực hiện nghiệp vụ.
- [ ] Đặt prefix riêng, phản ánh tên ứng dụng và module.
- [ ] Gom các thuộc tính liên quan trong một kiểu `@ConfigurationProperties`.
- [ ] Đăng ký kiểu bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
- [ ] Xác định rõ thuộc tính bắt buộc, mặc định và điều kiện validation.
- [ ] Viết mô tả, đơn vị và giới hạn hợp lệ cho từng thuộc tính.
- [ ] Giữ quyền sở hữu cấu hình trong module; module khác tương tác qua API nghiệp vụ.
- [ ] Thêm `spring-boot-configuration-processor` nếu cần metadata cho IDE và Application Module Canvas.
- [ ] Sinh Application Module Canvas để rà soát các cấu hình module yêu cầu.
- [ ] Kiểm tra binding và validation khi khởi tạo Spring application context.

## 14. Kết luận

Configuration property là một phần của required interface vì module cần các giá trị từ môi trường để thực hiện trách nhiệm của nó. `@ConfigurationProperties` giúp gom các giá trị thành hợp đồng có prefix, kiểu dữ liệu và validation rõ ràng. Spring Boot bind các giá trị khi ứng dụng khởi động; Spring Modulith có thể đưa metadata của chúng vào Application Module Canvas để nhóm phát triển và vận hành hiểu module đang yêu cầu cấu hình nào.

Hãy đặt cấu hình gần module sở hữu nghiệp vụ, đặt tên prefix có chủ đích, mô tả và xác thực giá trị. Khi module khác cần hành vi dựa trên cấu hình đó, hãy sử dụng API nghiệp vụ của module sở hữu thay vì đọc trực tiếp configuration bean.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Generating Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html)
