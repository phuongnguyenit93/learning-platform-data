# Giữ logic nghiệp vụ trong thành phần chuyên trách thay vì lớp cấu hình

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Thiết kế và bảo trì  
**Mục tiêu:** Thiết kế auto-configuration chỉ chịu trách nhiệm đăng ký và kết nối bean; đặt quy tắc nghiệp vụ trong service/policy chuyên trách. Bài xây dựng một ví dụ tính giá hóa đơn có thuế, giải thích constructor injection, `@ConditionalOnMissingBean`, cách tổ chức module và cách kiểm thử logic độc lập với Spring cũng như hành vi wiring của ApplicationContext.

## 1. Ranh giới trách nhiệm: cấu hình tạo object, service thực hiện nghiệp vụ

Một lớp auto-configuration trả lời các câu hỏi về **cách lắp ráp ứng dụng**:

- Bean nào được đăng ký?
- Khi nào bean được đăng ký?
- Bean phụ thuộc vào những bean nào?
- Ứng dụng có thể thay implementation mặc định bằng cách nào?
- Những property nào cần bind để cấu hình bean?

Một business service trả lời các câu hỏi về **hành vi của sản phẩm**:

- Một hóa đơn hợp lệ phải thỏa điều kiện gì?
- Subtotal, thuế và tổng tiền được tính ra sao?
- Khi số lượng hoặc đơn giá không hợp lệ thì xử lý thế nào?
- Chính sách làm tròn và quy tắc tính tiền là gì?

Không nên đưa việc tính toán, kiểm tra nghiệp vụ, gọi API, truy vấn dữ liệu hay điều phối quy trình vào phương thức `@Bean` hoặc thân lớp `@Configuration`.

Ví dụ cấu hình không nên làm:

```java
@Configuration
class InvoiceConfiguration {

    @Bean
    InvoicePricingService invoicePricingService(InvoiceRepository repository) {
        // Không nên: truy vấn dữ liệu, tính thuế, áp dụng giảm giá
        // và xử lý toàn bộ nghiệp vụ ngay trong factory method.
        List<Invoice> invoices = repository.findPending();
        BigDecimal total = invoices.stream()
                .map(Invoice::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new InvoicePricingService(total);
    }
}
```

Factory method này vừa đăng ký bean, vừa truy cập repository, vừa thực thi nghiệp vụ. Nó khó kiểm thử độc lập, có thể gây side effect trong lúc khởi động context và làm lớp cấu hình phình to theo từng yêu cầu mới.

Thiết kế tốt hơn:

```java
@AutoConfiguration
class InvoiceAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(InvoicePricingService.class)
    InvoicePricingService invoicePricingService(TaxPolicy taxPolicy) {
        return new DefaultInvoicePricingService(taxPolicy);
    }
}
```

Phương thức `@Bean` chỉ kết nối dependency và tạo implementation. `DefaultInvoicePricingService` chịu trách nhiệm tính toán, kiểm tra dữ liệu và thực hiện quy tắc nghiệp vụ.

**Nguyên tắc:** configuration là composition root của Spring; service/policy là nơi chứa hành vi. Một business service có thể là Spring bean, nhưng không cần đặt logic của nó trong lớp cấu hình.

## 2. Vì sao tách business logic khỏi configuration?

### 2.1. Kiểm thử độc lập

Một class Java thuần có thể được kiểm tra bằng JUnit mà không khởi động Spring, không tạo ApplicationContext và không cần mock container. Test tập trung vào input, output và các trường hợp biên của nghiệp vụ.

Nếu logic nằm trong `@Bean` method, test thường phải khởi động configuration chỉ để gọi một phép tính đơn giản. Điều đó làm test chậm và gắn chặt quy tắc nghiệp vụ với framework.

### 2.2. Tái sử dụng

Một service chuyên trách có thể được gọi từ:

- REST controller.
- Message listener.
- Scheduled job.
- Command-line runner.
- Batch processor.
- Một service nghiệp vụ khác.
- Test hoặc chương trình Java không dùng Spring.

Nếu logic chỉ tồn tại trong lớp cấu hình, các caller dễ phải gọi factory method, tạo object thủ công hoặc sao chép logic.

### 2.3. Thay thế implementation

Một interface giúp ứng dụng thay service mặc định bằng implementation riêng. Ví dụ thư viện cung cấp `DefaultInvoicePricingService`, còn ứng dụng có thể dùng policy tính thuế theo quốc gia.

Spring Boot hỗ trợ mẫu này bằng `@ConditionalOnMissingBean`: auto-configuration tạo default bean khi ứng dụng chưa cung cấp bean tương ứng.

### 2.4. Khởi động an toàn và dễ dự đoán

Configuration class được xử lý trong quá trình khởi tạo ApplicationContext. Nếu factory method thực hiện gọi mạng, đọc file lớn, truy vấn database hoặc xử lý hàng loạt, thời gian khởi động sẽ tăng và lỗi hạ tầng có thể làm context không tạo được.

Tạo bean nên chủ yếu là khởi tạo object và kết nối dependency. Công việc nghiệp vụ nên diễn ra khi có request hoặc trigger tương ứng, theo lifecycle được thiết kế rõ ràng.

### 2.5. Dễ bảo trì

Khi quy tắc thay đổi, developer tìm trong business service thay vì lần theo các method cấu hình. Khi cách đăng ký bean thay đổi, configuration có thể được sửa mà không phải viết lại phép tính hoặc quy tắc nghiệp vụ.

## 3. Ví dụ xuyên suốt: dịch vụ tính giá hóa đơn

Ta xây dựng một module Spring Boot auto-configuration cho invoice pricing.

Quy tắc ví dụ:

1. Hóa đơn phải có ít nhất một dòng hàng.
2. Đơn giá không được âm.
3. Số lượng phải lớn hơn 0.
4. Subtotal là tổng `unitPrice × quantity`.
5. Thuế bằng `subtotal × taxRate`.
6. Tiền được làm tròn đến hai chữ số thập phân bằng `HALF_UP`.
7. Tổng tiền bằng subtotal cộng thuế.

Giả sử hóa đơn có:

| Dòng hàng | Đơn giá | Số lượng | Thành tiền |
| --- | ---: | ---: | ---: |
| Book | 10.00 | 2 | 20.00 |
| Pen | 5.00 | 1 | 5.00 |
| **Subtotal** | | | **25.00** |
| Thuế 10% | | | **2.50** |
| **Total** | | | **27.50** |

Phép tính và validation thuộc business service. Tỷ lệ thuế được cung cấp qua một policy. Auto-configuration chỉ đăng ký policy mặc định và service mặc định khi feature được bật và ứng dụng chưa cung cấp implementation thay thế.

## 4. Tổ chức package theo trách nhiệm

Một cấu trúc gọn cho module auto-configuration:

```text
invoice-pricing-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/invoice/
    │   │   ├── api/
    │   │   │   ├── Invoice.java
    │   │   │   ├── InvoiceLine.java
    │   │   │   ├── InvoiceTotal.java
    │   │   │   └── InvoicePricingService.java
    │   │   ├── domain/
    │   │   │   ├── TaxPolicy.java
    │   │   │   ├── ConfiguredTaxPolicy.java
    │   │   │   └── DefaultInvoicePricingService.java
    │   │   ├── config/
    │   │   │   └── InvoicePricingProperties.java
    │   │   └── autoconfigure/
    │   │       └── InvoicePricingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/invoice/
        └── InvoicePricingTests.java
```

Ý nghĩa:

| Package | Trách nhiệm |
| --- | --- |
| `api` | Input/output model và interface mà consumer sử dụng |
| `domain` | Quy tắc tính giá và policy nghiệp vụ |
| `config` | Bind property thành kiểu dữ liệu có cấu trúc |
| `autoconfigure` | Điều kiện và wiring bean cho Spring Boot |

Không bắt buộc dự án nào cũng cần bốn package. Điều quan trọng là phân chia theo lý do thay đổi: business rules thay đổi ở service; cấu hình deployment thay đổi ở properties; cách Spring đăng ký bean thay đổi ở auto-configuration.

## 5. Xây dựng API và model độc lập với Spring

Các model nghiệp vụ không cần import annotation Spring.

### 5.1. `InvoiceLine.java`

```java
package com.acme.invoice.api;

import java.math.BigDecimal;

public record InvoiceLine(
        String description,
        BigDecimal unitPrice,
        int quantity
) {
}
```

`InvoiceLine` mô tả một dòng hàng. Validation về giá trị được đặt trong service để minh họa rõ quy tắc nghiệp vụ và dễ kiểm thử.

### 5.2. `Invoice.java`

```java
package com.acme.invoice.api;

import java.util.List;

public record Invoice(List<InvoiceLine> lines) {

    public Invoice {
        lines = lines == null ? List.of() : List.copyOf(lines);
    }
}
```

Record tạo một snapshot bất biến của danh sách. `List.copyOf` cũng từ chối phần tử `null`; service vẫn chịu trách nhiệm kiểm tra invoice rỗng và các trường của dòng hàng.

### 5.3. `InvoiceTotal.java`

```java
package com.acme.invoice.api;

import java.math.BigDecimal;

public record InvoiceTotal(
        BigDecimal subtotal,
        BigDecimal tax,
        BigDecimal total
) {
}
```

Kết quả tách riêng subtotal, tax và total để caller có thể hiển thị hóa đơn, lưu dữ liệu hoặc viết test từng phần.

### 5.4. `InvoicePricingService.java`

```java
package com.acme.invoice.api;

public interface InvoicePricingService {

    InvoiceTotal calculate(Invoice invoice);
}
```

Consumer phụ thuộc vào interface. Nó không cần biết implementation mặc định là class nào, policy thuế được tạo ở đâu hoặc Spring đăng ký bean ra sao.

## 6. Đặt chính sách thuế trong thành phần chuyên trách

### 6.1. `TaxPolicy.java`

```java
package com.acme.invoice.domain;

import java.math.BigDecimal;

public interface TaxPolicy {

    BigDecimal rate();
}
```

`TaxPolicy` diễn tả nguồn cung cấp tỷ lệ thuế. Có thể thay bằng policy theo khu vực, khách hàng hoặc loại hàng mà không phải sửa service tính giá.

### 6.2. `ConfiguredTaxPolicy.java`

```java
package com.acme.invoice.domain;

import java.math.BigDecimal;
import java.util.Objects;

public final class ConfiguredTaxPolicy implements TaxPolicy {

    private final BigDecimal rate;

    public ConfiguredTaxPolicy(BigDecimal rate) {
        this.rate = Objects.requireNonNull(rate, "rate must not be null");

        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "tax rate must be between 0 and 1"
            );
        }
    }

    @Override
    public BigDecimal rate() {
        return this.rate;
    }
}
```

Đây là implementation lấy tỷ lệ thuế từ cấu hình. Nó là một object Java chuyên trách cho policy; nó không biết `Environment`, `@Value` hay ApplicationContext.

Nếu nghiệp vụ sau này cần thuế theo quốc gia, có thể tạo `RegionalTaxPolicy` hoặc một policy resolver riêng. `DefaultInvoicePricingService` vẫn phụ thuộc vào abstraction `TaxPolicy`.

## 7. Đưa toàn bộ quy tắc tính giá vào `DefaultInvoicePricingService`

File `DefaultInvoicePricingService.java`:

```java
package com.acme.invoice.domain;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

import com.acme.invoice.api.Invoice;
import com.acme.invoice.api.InvoiceLine;
import com.acme.invoice.api.InvoicePricingService;
import com.acme.invoice.api.InvoiceTotal;

public final class DefaultInvoicePricingService
        implements InvoicePricingService {

    private static final BigDecimal ZERO = BigDecimal.ZERO;
    private static final BigDecimal ONE = BigDecimal.ONE;
    private static final int MONEY_SCALE = 2;

    private final TaxPolicy taxPolicy;

    public DefaultInvoicePricingService(TaxPolicy taxPolicy) {
        this.taxPolicy = Objects.requireNonNull(
                taxPolicy,
                "taxPolicy must not be null"
        );
    }

    @Override
    public InvoiceTotal calculate(Invoice invoice) {
        if (invoice == null) {
            throw new IllegalArgumentException("invoice must not be null");
        }

        if (invoice.lines().isEmpty()) {
            throw new IllegalArgumentException(
                    "invoice must contain at least one line"
            );
        }

        BigDecimal subtotal = ZERO;

        for (InvoiceLine line : invoice.lines()) {
            if (line.unitPrice() == null
                    || line.unitPrice().compareTo(ZERO) < 0) {
                throw new IllegalArgumentException(
                        "unit price must not be null or negative"
                );
            }

            if (line.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be greater than zero"
                );
            }

            BigDecimal lineTotal = line.unitPrice()
                    .multiply(BigDecimal.valueOf(line.quantity()));

            subtotal = subtotal.add(lineTotal);
        }

        BigDecimal rate = this.taxPolicy.rate();

        if (rate == null
                || rate.compareTo(ZERO) < 0
                || rate.compareTo(ONE) > 0) {
            throw new IllegalStateException(
                    "tax policy must return a rate between 0 and 1"
            );
        }

        subtotal = subtotal.setScale(
                MONEY_SCALE,
                RoundingMode.HALF_UP
        );

        BigDecimal tax = subtotal.multiply(rate).setScale(
                MONEY_SCALE,
                RoundingMode.HALF_UP
        );

        BigDecimal total = subtotal.add(tax).setScale(
                MONEY_SCALE,
                RoundingMode.HALF_UP
        );

        return new InvoiceTotal(subtotal, tax, total);
    }
}
```

Class này chứa những quyết định nghiệp vụ:

- Invoice nào được chấp nhận.
- Đơn giá và số lượng hợp lệ ra sao.
- Cách tính line total và subtotal.
- Tỷ lệ thuế phải thỏa điều kiện gì.
- Thời điểm và cách làm tròn tiền.

Không có annotation Spring trong class. Có thể tạo service bằng `new DefaultInvoicePricingService(...)` trong unit test hoặc để Spring quản lý nó như một bean.

Việc không phụ thuộc Spring giúp business logic dễ tái sử dụng và không bị buộc vào lifecycle của container.

### 7.1. Vì sao dùng `BigDecimal` thay vì `double`?

Tiền tệ cần biểu diễn thập phân chính xác. `double` dùng số thực nhị phân nên các phép tính như `0.1 + 0.2` không bảo đảm biểu diễn chính xác như số thập phân mong muốn.

Dùng `BigDecimal` với constructor từ chuỗi:

```java
new BigDecimal("10.00")
```

Không nên tạo số tiền bằng:

```java
new BigDecimal(10.00)
```

vì biểu diễn nhị phân của `double` có thể đã chứa sai số trước khi chuyển sang `BigDecimal`.

Ví dụ đang làm tròn subtotal và tax đến hai chữ số bằng `HALF_UP`. Hệ thống tài chính thực tế phải xác định rõ currency scale, quy tắc làm tròn theo từng dòng hay trên tổng, thuế đã bao gồm hay chưa, và xử lý discount. Những quy tắc đó thuộc domain service/policy, không thuộc auto-configuration.

## 8. Bind cấu hình thành một object có kiểu

File `InvoicePricingProperties.java`:

```java
package com.acme.invoice.config;

import java.math.BigDecimal;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.invoice")
public record InvoicePricingProperties(BigDecimal taxRate) {

    public InvoicePricingProperties {
        taxRate = taxRate == null
                ? new BigDecimal("0.10")
                : taxRate;

        if (taxRate.compareTo(BigDecimal.ZERO) < 0
                || taxRate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "acme.invoice.tax-rate must be between 0 and 1"
            );
        }
    }
}
```

Property tương ứng:

```yaml
acme:
  invoice:
    enabled: true
    tax-rate: 0.10
```

`enabled` được dùng để quyết định auto-configuration có hoạt động hay không. `tax-rate` được bind thành `BigDecimal` trong `InvoicePricingProperties`.

Properties class là adapter giữa cấu hình bên ngoài và kiểu dữ liệu nội bộ. Nó có thể kiểm tra tính hợp lệ cơ bản của cấu hình, nhưng không nên chứa quy trình tính invoice hoặc logic áp dụng discount.

Việc kiểm tra tax rate ở properties và `ConfiguredTaxPolicy` có mục đích bảo vệ các đường khởi tạo khác nhau: properties bảo vệ cấu hình Spring; policy bảo vệ chính object khi được tạo trực tiếp hoặc dùng ngoài Spring.

## 9. Auto-configuration chỉ làm nhiệm vụ wiring

File `InvoicePricingAutoConfiguration.java`:

```java
package com.acme.invoice.autoconfigure;

import com.acme.invoice.api.InvoicePricingService;
import com.acme.invoice.config.InvoicePricingProperties;
import com.acme.invoice.domain.ConfiguredTaxPolicy;
import com.acme.invoice.domain.DefaultInvoicePricingService;
import com.acme.invoice.domain.TaxPolicy;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.invoice",
        name = "enabled",
        havingValue = "true"
)
@EnableConfigurationProperties(InvoicePricingProperties.class)
public class InvoicePricingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(TaxPolicy.class)
    TaxPolicy invoiceTaxPolicy(InvoicePricingProperties properties) {
        return new ConfiguredTaxPolicy(properties.taxRate());
    }

    @Bean
    @ConditionalOnMissingBean(InvoicePricingService.class)
    InvoicePricingService invoicePricingService(TaxPolicy taxPolicy) {
        return new DefaultInvoicePricingService(taxPolicy);
    }
}
```

Lớp cấu hình chỉ thực hiện bốn việc:

1. Điều kiện `acme.invoice.enabled=true` quyết định feature có được bật hay không.
2. `@EnableConfigurationProperties` đăng ký object cấu hình có kiểu.
3. Bean `TaxPolicy` mặc định được tạo nếu ứng dụng chưa cung cấp policy.
4. Bean `InvoicePricingService` mặc định được tạo nếu ứng dụng chưa cung cấp service.

Không có phép tính tiền, vòng lặp dòng hàng, validation invoice hoặc xử lý giảm giá trong class này.

### 9.1. Vì sao dùng tham số method thay vì gọi trực tiếp `@Bean` khác?

Không nên viết:

```java
@Bean
InvoicePricingService invoicePricingService() {
    return new DefaultInvoicePricingService(invoiceTaxPolicy(null));
}
```

Method trên gọi trực tiếp factory method khác và còn truyền sai dependency. Với `@Configuration(proxyBeanMethods = false)`, lời gọi Java thông thường không được intercept để trả về managed bean. Nó có thể tạo một object mới ngoài ý muốn.

Hãy khai báo dependency qua tham số:

```java
@Bean
InvoicePricingService invoicePricingService(TaxPolicy taxPolicy) {
    return new DefaultInvoicePricingService(taxPolicy);
}
```

Spring tìm bean `TaxPolicy` phù hợp và inject vào factory method. Đây là cách thể hiện dependency graph rõ ràng và hoạt động tốt với lite configuration/`proxyBeanMethods = false`.

### 9.2. Vì sao `@ConditionalOnMissingBean` quan trọng?

Auto-configuration cung cấp default cho consumer, nhưng không nên khóa ứng dụng vào implementation mặc định.

Nếu ứng dụng có bean:

```java
@Bean
TaxPolicy regionalTaxPolicy() {
    return new RegionalTaxPolicy();
}
```

thì `@ConditionalOnMissingBean(TaxPolicy.class)` khiến policy mặc định không được đăng ký.

Nếu ứng dụng cung cấp:

```java
@Bean
InvoicePricingService customInvoicePricingService() {
    return new CustomInvoicePricingService();
}
```

thì service mặc định nhường chỗ.

Điều kiện nên đặt trên auto-configuration bean method, nơi Spring Boot có thể xét user bean definitions đã được xử lý trước đó. Hãy khai báo kiểu trả về đủ cụ thể để Spring nhận diện được loại bean mà method cung cấp.

### 9.3. Không cần `@Service` và `@Bean` cùng lúc

Trong ví dụ library, `DefaultInvoicePricingService` là class Java thuần và được đăng ký bằng `@Bean`.

Không cần thêm `@Service` vào class này, vì auto-configuration đã tạo bean. Nếu đồng thời component scan và `@Bean` đăng ký cùng implementation, ứng dụng có thể có hai bean cùng contract và phát sinh ambiguity hoặc hành vi ngoài ý muốn.

## 10. Đăng ký auto-configuration trong JAR

Với Spring Boot 2.7 trở lên, tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.invoice.autoconfigure.InvoicePricingAutoConfiguration
```

Mỗi dòng là một fully qualified class name. File này giúp Spring Boot khám phá auto-configuration trong dependency JAR.

Với Boot 2.6 trở xuống, cơ chế cũ dùng key `EnableAutoConfiguration` trong `META-INF/spring.factories`. Nếu thư viện hỗ trợ nhiều dòng Boot, cần lựa chọn registration và annotation tương thích với baseline thấp nhất. Ví dụ hiện tại dùng `@AutoConfiguration`, nên target Boot 2.7+.

File imports là registration metadata, không chứa business logic. Không đưa class `DefaultInvoicePricingService` vào file imports nếu class đó chỉ là implementation được tạo bởi auto-configuration; chỉ đăng ký configuration class cấp cao nhất.

## 11. Maven setup cho ví dụ

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>invoice-pricing-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Ví dụ dùng Spring Boot 3.3.13 và Java 17. Parent quản lý version cho các dependency Spring Boot. Module autoconfigure không cần kéo `spring-boot-starter-web` nếu nó không cung cấp web endpoint.

Nếu đây là thư viện publish cho consumer, hãy khai báo dependency API/runtime theo đúng contract của module và giữ annotation processor/test dependencies ở đúng scope. Một starter tổng hợp có thể phụ thuộc vào module autoconfigure và các dependency mà người dùng cuối cần.

## 12. Kiểm thử business service mà không khởi động Spring

File `InvoicePricingServiceUnitTests.java`:

```java
package com.acme.invoice;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.acme.invoice.api.Invoice;
import com.acme.invoice.api.InvoiceLine;
import com.acme.invoice.api.InvoiceTotal;
import com.acme.invoice.domain.DefaultInvoicePricingService;
import com.acme.invoice.domain.TaxPolicy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class InvoicePricingServiceUnitTests {

    private static Invoice sampleInvoice() {
        return new Invoice(List.of(
                new InvoiceLine("Book", new BigDecimal("10.00"), 2),
                new InvoiceLine("Pen", new BigDecimal("5.00"), 1)
        ));
    }

    @Test
    void calculatesSubtotalTaxAndTotal() {
        TaxPolicy tenPercent = () -> new BigDecimal("0.10");

        DefaultInvoicePricingService service =
                new DefaultInvoicePricingService(tenPercent);

        InvoiceTotal result = service.calculate(sampleInvoice());

        assertThat(result.subtotal()).isEqualByComparingTo("25.00");
        assertThat(result.tax()).isEqualByComparingTo("2.50");
        assertThat(result.total()).isEqualByComparingTo("27.50");
    }

    @Test
    void rejectsNonPositiveQuantity() {
        TaxPolicy tenPercent = () -> new BigDecimal("0.10");

        DefaultInvoicePricingService service =
                new DefaultInvoicePricingService(tenPercent);

        Invoice invalidInvoice = new Invoice(List.of(
                new InvoiceLine("Book", new BigDecimal("10.00"), 0)
        ));

        assertThatThrownBy(() -> service.calculate(invalidInvoice))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("quantity must be greater than zero");
    }
}
```

Chạy:

```bash
mvn -Dtest=InvoicePricingServiceUnitTests test
```

Kết quả mong đợi:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Hai test này tạo service trực tiếp bằng constructor. Không cần ApplicationContext, Spring runner, mock container hay `@SpringBootTest`.

Đây là lợi ích quan trọng của việc tách business logic: test xác nhận quy tắc tính tiền mà không phụ thuộc vào cách Spring đăng ký bean.

## 13. Kiểm thử wiring và back-off bằng `ApplicationContextRunner`

Unit test không kiểm tra auto-configuration có tạo đúng bean hay không. Ta cần thêm context test cho phần wiring.

File `InvoicePricingAutoConfigurationTests.java`:

```java
package com.acme.invoice;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.acme.invoice.api.Invoice;
import com.acme.invoice.api.InvoiceLine;
import com.acme.invoice.api.InvoicePricingService;
import com.acme.invoice.api.InvoiceTotal;
import com.acme.invoice.autoconfigure.InvoicePricingAutoConfiguration;
import com.acme.invoice.domain.TaxPolicy;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class InvoicePricingAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    InvoicePricingAutoConfiguration.class
                            )
                    );

    private static Invoice sampleInvoice() {
        return new Invoice(List.of(
                new InvoiceLine("Book", new BigDecimal("10.00"), 2),
                new InvoiceLine("Pen", new BigDecimal("5.00"), 1)
        ));
    }

    @Test
    void doesNotRegisterServiceWhenEnabledPropertyIsMissing() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(InvoicePricingService.class);
        });
    }

    @Test
    void doesNotRegisterServiceWhenFeatureIsDisabled() {
        this.runner
                .withPropertyValues("acme.invoice.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(InvoicePricingService.class);
                });
    }

    @Test
    void registersDefaultServiceWhenFeatureIsEnabled() {
        this.runner
                .withPropertyValues("acme.invoice.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(InvoicePricingService.class);

                    InvoiceTotal result = context
                            .getBean(InvoicePricingService.class)
                            .calculate(sampleInvoice());

                    assertThat(result.total()).isEqualByComparingTo("27.50");
                });
    }

    @Test
    void usesApplicationProvidedServiceInsteadOfDefault() {
        this.runner
                .withPropertyValues("acme.invoice.enabled=true")
                .withUserConfiguration(UserPricingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(InvoicePricingService.class);

                    InvoiceTotal result = context
                            .getBean(InvoicePricingService.class)
                            .calculate(sampleInvoice());

                    assertThat(result.total()).isEqualByComparingTo("99.00");
                });
    }

    @Test
    void injectsApplicationProvidedTaxPolicyIntoDefaultService() {
        this.runner
                .withPropertyValues("acme.invoice.enabled=true")
                .withUserConfiguration(UserTaxPolicyConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(InvoicePricingService.class);

                    InvoiceTotal result = context
                            .getBean(InvoicePricingService.class)
                            .calculate(sampleInvoice());

                    assertThat(result.subtotal()).isEqualByComparingTo("25.00");
                    assertThat(result.tax()).isEqualByComparingTo("5.00");
                    assertThat(result.total()).isEqualByComparingTo("30.00");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPricingConfiguration {

        @Bean
        InvoicePricingService customInvoicePricingService() {
            return invoice -> new InvoiceTotal(
                    new BigDecimal("0.00"),
                    new BigDecimal("0.00"),
                    new BigDecimal("99.00")
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserTaxPolicyConfiguration {

        @Bean
        TaxPolicy customTaxPolicy() {
            return () -> new BigDecimal("0.20");
        }
    }
}
```

Chạy:

```bash
mvn -Dtest=InvoicePricingAutoConfigurationTests test
```

Kết quả mong đợi:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

`ApplicationContextRunner` được dùng ở đây để kiểm tra cách configuration kết nối các thành phần:

- Thiếu property: feature không được đăng ký.
- Property `false`: feature không được đăng ký.
- Property `true`: service mặc định được tạo và thực hiện phép tính.
- User service có mặt: default service nhường chỗ.
- User policy có mặt: default service nhận policy do ứng dụng cung cấp.

Test back-off dùng `AutoConfigurations.of(...)` cho auto-configuration và `withUserConfiguration(...)` cho user config. Cách này mô phỏng thứ tự xử lý user bean trước auto-configuration, phù hợp với mục đích kiểm tra `@ConditionalOnMissingBean`.

## 14. Unit test và context test bảo vệ hai hợp đồng khác nhau

| Loại test | Kiểm tra | Không cần kiểm tra |
| --- | --- | --- |
| Unit test service | Công thức, validation, rounding, trường hợp biên | Bean registration, property binding |
| Context test | Condition, bean wiring, override, policy injection | Toàn bộ quy tắc nghiệp vụ |
| Integration test | Resource registration, startup, kết nối module thực tế | Mọi tổ hợp input nghiệp vụ |
| End-to-end test | Hành vi từ request/message đến output | Chi tiết nội bộ từng class |

Không nên đưa mọi test vào `@SpringBootTest`. Với business logic thuần, unit test nhanh và tập trung hơn. Dùng Spring test support cho phần Spring thực sự chịu trách nhiệm: condition, bean creation, property binding và override.

Nếu module được publish, cần thêm integration test dùng `@EnableAutoConfiguration` mà không import trực tiếp class, để xác nhận `AutoConfiguration.imports` được tìm thấy. `AutoConfigurations.of(...)` truyền class trực tiếp nên chỉ xác nhận logic auto-configuration, chưa xác nhận registration resource.

## 15. Nếu là ứng dụng thay vì thư viện, có thể dùng `@Service`

Trong một ứng dụng Spring Boot thông thường, service thường được đánh dấu:

```java
@Service
public class InvoicePricingServiceImpl implements InvoicePricingService {
    // Business logic
}
```

Constructor injection kết nối policy hoặc repository:

```java
@Service
public class InvoiceApplicationService {

    private final InvoicePricingService pricingService;

    public InvoiceApplicationService(InvoicePricingService pricingService) {
        this.pricingService = pricingService;
    }
}
```

Component scanning sẽ phát hiện class trong package được quét.

Với thư viện auto-configuration, explicit `@Bean` thường phù hợp hơn `@ComponentScan` rộng:

- Consumer chủ động nhận bean qua dependency của thư viện.
- Auto-configuration có thể bật/tắt theo property/class condition.
- `@ConditionalOnMissingBean` cho phép consumer override.
- Thư viện không vô tình quét package ứng dụng và đăng ký component không liên quan.

Có thể dùng `@Service` trong module library nếu component scanning được thiết kế có chủ đích, nhưng phải kiểm tra nguy cơ đăng ký trùng khi auto-configuration cũng tạo cùng bean. Chọn một cơ chế đăng ký rõ ràng.

## 16. Những anti-pattern cần tránh

### 16.1. Business logic trong `@Bean` method

**Vấn đề:** Factory method vừa tạo bean vừa thực hiện quy trình nghiệp vụ.

**Hậu quả:** Khó unit test, startup có side effect và cấu hình phình to.

**Cách sửa:** Chuyển logic vào service/policy; factory method chỉ gọi constructor và truyền dependency.

### 16.2. Dùng configuration class như service

**Vấn đề:** Controller hoặc service khác inject `InvoicePricingAutoConfiguration` để gọi method tính giá.

**Hậu quả:** Consumer phụ thuộc vào lớp hạ tầng Spring thay vì business contract.

**Cách sửa:** Inject `InvoicePricingService` hoặc abstraction nghiệp vụ.

### 16.3. Inject `Environment` vào mọi business service

**Vấn đề:** Service tự đọc chuỗi property và tự chuyển kiểu.

**Hậu quả:** Business logic phụ thuộc cấu trúc cấu hình và khó test.

**Cách sửa:** Bind bằng `@ConfigurationProperties`, sau đó truyền giá trị có kiểu hoặc policy vào constructor.

### 16.4. Dùng static mutable state trong configuration

**Vấn đề:** Lưu dependency hoặc kết quả nghiệp vụ vào static field.

**Hậu quả:** Trạng thái khó cô lập giữa context/test, khó chạy nhiều application context và có nguy cơ race condition.

**Cách sửa:** Dùng bean stateless hoặc state có lifecycle rõ ràng; inject qua constructor.

### 16.5. Gọi trực tiếp một `@Bean` method khác

**Vấn đề:** Trong `proxyBeanMethods = false`, lời gọi Java trực tiếp có thể tạo object mới thay vì lấy managed bean.

**Cách sửa:** Khai báo dependency bằng tham số method hoặc constructor injection.

### 16.6. Tạo bean mặc định nhưng không cho consumer override

**Vấn đề:** Bean luôn được đăng ký dù ứng dụng đã có implementation riêng.

**Hậu quả:** Có nhiều candidate, ambiguity hoặc consumer bị buộc dùng sai service.

**Cách sửa:** Dùng `@ConditionalOnMissingBean` cho default bean và test user override.

### 16.7. Component scan toàn bộ package consumer

**Vấn đề:** Auto-configuration quét package quá rộng.

**Hậu quả:** Thư viện có thể đăng ký nhầm bean của ứng dụng hoặc tạo duplicate bean.

**Cách sửa:** Đăng ký rõ configuration hỗ trợ bằng `@Import` hoặc `@Bean`; để ứng dụng tự quản lý component scan của nó.

### 16.8. Constructor service thực hiện I/O

**Vấn đề:** Constructor kết nối database, gọi HTTP hoặc tải dữ liệu lớn.

**Hậu quả:** Tạo ApplicationContext trở nên phụ thuộc hạ tầng và khó kiểm thử.

**Cách sửa:** Constructor chỉ nhận dependency và thiết lập invariant. Thực hiện I/O qua method nghiệp vụ hoặc lifecycle component được thiết kế riêng.

## 17. Quy trình thiết kế một auto-configuration có business service

1. Xác định business contract dưới dạng interface và model độc lập với Spring.
2. Viết implementation service với constructor dependency rõ ràng.
3. Đưa policy thay đổi được vào abstraction riêng.
4. Viết unit test cho quy tắc, validation và trường hợp biên trước.
5. Tạo `@ConfigurationProperties` cho các giá trị cấu hình có kiểu.
6. Tạo auto-configuration chỉ chứa condition, property registration và bean wiring.
7. Dùng `@ConditionalOnMissingBean` để hỗ trợ implementation do consumer cung cấp.
8. Dùng tham số `@Bean` hoặc constructor injection thay vì gọi factory method trực tiếp.
9. Đăng ký auto-configuration qua imports file phù hợp với Boot baseline.
10. Viết context test cho property on/off, default bean và user override.
11. Nếu publish library, viết integration test xác nhận discovery từ registration resource.
12. Kiểm tra JAR cuối cùng và chạy consumer smoke test.

Mỗi bước bảo vệ một ranh giới riêng: domain rules, cấu hình, Spring wiring và artifact publication.

## 18. Checklist review code

- [ ] Lớp cấu hình không chứa công thức hoặc quy tắc nghiệp vụ.
- [ ] Factory method chỉ tạo object và kết nối dependency.
- [ ] Business service có interface/contract phù hợp với consumer.
- [ ] Service có thể unit test mà không cần Spring context.
- [ ] Constructor injection thể hiện rõ dependency bắt buộc.
- [ ] Policy có thể thay thế mà không sửa service chính.
- [ ] Properties được bind thành kiểu dữ liệu có cấu trúc.
- [ ] `@ConditionalOnProperty` phản ánh đúng trạng thái bật/tắt.
- [ ] Default bean dùng `@ConditionalOnMissingBean` khi cần cho phép override.
- [ ] User-provided service/policy được test trong context.
- [ ] Không vừa component scan vừa `@Bean` tạo trùng cùng implementation.
- [ ] Không dùng `Environment` hoặc static mutable state trong domain nếu không cần thiết.
- [ ] Không thực hiện I/O hoặc xử lý nghiệp vụ nặng trong lúc tạo bean.
- [ ] Có unit test, context test và integration test phù hợp với contract.
- [ ] Auto-configuration registration resource nằm trong JAR đúng module.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Lớp `@AutoConfiguration` nên chịu trách nhiệm chính về điều gì?  
**Đáp án:** Khai báo condition, đăng ký properties và kết nối bean/dependency. Business rules nằm trong service hoặc policy chuyên trách.

**Câu 2.** Vì sao không nên tính tổng hóa đơn bên trong một method `@Bean`?  
**Đáp án:** Factory method sẽ trộn wiring với nghiệp vụ, làm khó unit test và có nguy cơ thực hiện công việc không cần thiết trong lúc ApplicationContext khởi động.

**Câu 3.** Business service có bắt buộc phải mang `@Service` không?  
**Đáp án:** Không. Nó có thể là class Java thuần được đăng ký bằng `@Bean`, hoặc được component scan phát hiện khi thiết kế theo kiểu ứng dụng.

**Câu 4.** `@ConditionalOnMissingBean(InvoicePricingService.class)` giúp ích gì?  
**Đáp án:** Auto-configuration chỉ tạo implementation mặc định khi consumer chưa cung cấp service phù hợp.

**Câu 5.** Vì sao dùng constructor injection?  
**Đáp án:** Dependency bắt buộc được thể hiện rõ, object có thể được tạo ở trạng thái hợp lệ và unit test dễ truyền fake/stub implementation.

**Câu 6.** `@ConfigurationProperties` nên chứa loại logic nào?  
**Đáp án:** Bind giá trị cấu hình thành kiểu dữ liệu và kiểm tra invariant cơ bản của cấu hình; không nên chứa quy trình nghiệp vụ của invoice.

**Câu 7.** Với `proxyBeanMethods = false`, vì sao không nên gọi trực tiếp method `@Bean` khác?  
**Đáp án:** Lời gọi Java có thể tạo object mới thay vì lấy bean được Spring quản lý. Khai báo dependency bằng tham số method.

**Câu 8.** Unit test và `ApplicationContextRunner` khác nhau ở đâu?  
**Đáp án:** Unit test kiểm tra business rules độc lập; `ApplicationContextRunner` kiểm tra conditions, bean registration, wiring và override.

**Câu 9.** Trong library auto-configuration, vì sao thường tránh `@ComponentScan` rộng?  
**Đáp án:** Nó có thể quét nhầm package của consumer, đăng ký component ngoài ý muốn hoặc tạo bean trùng. Explicit `@Bean`/`@Import` giữ registration có kiểm soát.

**Câu 10.** Nếu consumer cần tính thuế theo quốc gia, có phải sửa lớp auto-configuration không?  
**Đáp án:** Thông thường không. Cung cấp một `TaxPolicy` implementation khác; service tiếp tục gọi abstraction. Auto-configuration chỉ cần back-off cho policy do consumer cung cấp.

## 20. Nguyên tắc cần nhớ

- Auto-configuration là composition root: quyết định khi nào và bằng cách nào bean được đăng ký.
- Business service/policy chứa hành vi, validation và quy tắc nghiệp vụ.
- `@Bean` method nên ngắn, khai báo rõ dependency và tránh side effect.
- Business service không bắt buộc phải import Spring; có thể được tạo bằng constructor trong unit test.
- Dùng interface và constructor injection để tách consumer khỏi implementation.
- Dùng `@ConfigurationProperties` cho cấu hình có kiểu; không để domain service tự đọc property string.
- Dùng `@ConditionalOnMissingBean` để consumer thay implementation mặc định.
- Với `proxyBeanMethods = false`, inject dependency qua tham số method thay vì gọi trực tiếp `@Bean` method khác.
- Phân biệt unit test nghiệp vụ, context test wiring và integration test discovery.
- Không để auto-configuration quét package consumer hoặc thực hiện nghiệp vụ nặng trong startup.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `@AutoConfiguration`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 API — `@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Framework — Using `@Bean` Methods](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework — Constructor-based Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Boot 3.3 — Configuration Metadata and `@ConfigurationProperties`](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Testing Auto-configuration with `ApplicationContextRunner`](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
