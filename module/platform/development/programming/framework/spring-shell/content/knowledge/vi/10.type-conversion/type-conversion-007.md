# Đăng ký converter cho kiểu miền khi mô hình thực thi hỗ trợ

Người dùng nhập command dưới dạng văn bản, nhưng tầng nghiệp vụ thường làm việc với kiểu miền có ý nghĩa rõ ràng hơn. Ví dụ, người vận hành nhập `SKU-123`, còn service muốn nhận một `ProductId`; người dùng nhập `HN`, còn nghiệp vụ muốn nhận `WarehouseCode`. Converter giúp chuyển giá trị văn bản thành đối tượng miền ngay tại ranh giới đầu vào của command.

Spring Shell dựa trên cơ chế chuyển đổi kiểu của Spring Framework. Tuy nhiên, cách đăng ký converter phụ thuộc vào phiên bản và mô hình thực thi command. Spring Shell 2.x có cơ chế tự thu thập converter bean được tài liệu mô tả rõ. Spring Shell 3.x và 4.x cung cấp `ShellConversionServiceSupplier` để cấp `ConversionService` riêng cho shell. Một command chỉ nhận được kiểu miền đã chuyển đổi khi đường thực thi của nó thực sự sử dụng `ConversionService` và khai báo kiểu đích tương ứng.

## 1. Khi nào cần converter cho kiểu miền?

Spring Shell đã hỗ trợ chuyển đổi những kiểu phổ biến như chuỗi, số, Boolean, enum và mảng. Nếu command chỉ nhận `String`, `int`, `long`, `BigDecimal`, `boolean` hoặc enum thông thường thì thường không cần viết converter riêng.

Converter hữu ích khi đầu vào cần trở thành một kiểu miền có quy tắc riêng:

| Giá trị người dùng nhập | Kiểu miền mong muốn | Ví dụ |
|---|---|---|
| `SKU-123` | `ProductId` | Mã định danh sản phẩm |
| `HN` | `WarehouseCode` | Mã kho |
| `2026-11-26` | `BusinessDate` | Ngày nghiệp vụ với định dạng cố định |
| `10.20.30.40` | `IpAddress` | Địa chỉ mạng có kiểm tra định dạng |
| `ORD-2026-0012` | `OrderNumber` | Mã đơn hàng có cấu trúc riêng |

Giả sử command tra cứu tồn kho nhận `String sku`, service phải tự kiểm tra định dạng mã SKU ở mọi nơi gọi. Nếu chuyển đổi thành `ProductId` ngay khi Spring Shell bind tham số, command nhận được một đối tượng đã có cấu trúc hợp lệ. Service vẫn chịu trách nhiệm kiểm tra quy tắc nghiệp vụ như sản phẩm có tồn tại, người dùng có quyền xem hay kho có dữ liệu hay không.

## 2. Cơ chế Converter của Spring Framework

Spring Framework cung cấp `ConversionService` làm API thực hiện chuyển đổi lúc chạy và `ConverterRegistry` làm điểm đăng ký converter. Converter đơn giản nhất triển khai giao diện `Converter<S, T>`:

```java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
```

Trong đó:

- `S` là kiểu nguồn, thường là `String` vì người dùng nhập văn bản.
- `T` là kiểu đích, thường là value object hoặc kiểu miền của ứng dụng.
- `convert` tạo giá trị đích hoặc ném exception nếu đầu vào không hợp lệ.

Spring Framework còn có hai SPI mở rộng:

| SPI | Khi nên dùng |
|---|---|
| `Converter<S, T>` | Một cặp kiểu nguồn và đích cụ thể, chẳng hạn `String` sang `ProductId` |
| `ConverterFactory<S, R>` | Một họ kiểu đích có chung kiểu cơ sở, chẳng hạn chuyển `String` sang nhiều enum khác nhau |
| `GenericConverter` | Cần hỗ trợ nhiều cặp kiểu hoặc cần đọc `TypeDescriptor` để xét metadata của trường/tham số |

Nên bắt đầu bằng `Converter<S, T>` vì nó rõ kiểu và dễ kiểm thử. Chỉ dùng `ConverterFactory` hoặc `GenericConverter` khi có nhu cầu thực sự về nhiều kiểu đích hoặc metadata chuyển đổi.

## 3. Xây dựng kiểu miền và converter

Ví dụ sau tạo kiểu `ProductId` với định dạng `SKU-` theo sau bởi 3 đến 12 ký tự chữ in hoa hoặc chữ số. Converter chuẩn hóa khoảng trắng và chữ hoa trước khi tạo đối tượng.

**Kiểu miền `ProductId`:**

```java
package com.example.inventory.domain;

public record ProductId(String value) {

    public ProductId {
        if (value == null || !value.matches("SKU-[A-Z0-9]{3,12}")) {
            throw new IllegalArgumentException(
                    "Mã sản phẩm phải có dạng SKU- theo sau bởi 3 đến 12 chữ cái hoặc chữ số.");
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
```

`ProductId` tự bảo vệ bất biến của nó. Nhờ vậy, đối tượng được tạo từ command, REST API, batch hoặc một phần khác của ứng dụng đều tuân theo cùng định dạng.

**Converter từ `String` sang `ProductId`:**

```java
package com.example.inventory.shell.conversion;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

import com.example.inventory.domain.ProductId;

@Component
public class StringToProductIdConverter implements Converter<String, ProductId> {

    @Override
    public ProductId convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Mã sản phẩm không được để trống.");
        }

        String normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProductId(normalized);
    }
}
```

Ví dụ chuyển đổi:

| Đầu vào | Kết quả |
|---|---|
| `SKU-123` | `ProductId("SKU-123")` |
| ` sku-123 ` | `ProductId("SKU-123")` |
| `SKU-ABC9` | `ProductId("SKU-ABC9")` |
| `123` | Lỗi định dạng |
| `SKU-` | Lỗi định dạng |
| Chuỗi rỗng | Lỗi đầu vào rỗng |

Converter nên không có trạng thái thay đổi trong quá trình chuyển đổi và an toàn khi được dùng đồng thời. Theo hợp đồng Spring Framework, `Converter.convert` không nhận nguồn `null`; dù vậy, việc kiểm tra chuỗi rỗng hoặc chỉ chứa khoảng trắng vẫn cần thiết. Khi không chuyển đổi được, ném `IllegalArgumentException` với thông báo có thể giúp người dùng sửa đầu vào.

## 4. Đăng ký converter theo phiên bản Spring Shell

Không phải mọi thế hệ Spring Shell đều có cùng điểm mở rộng. Hãy xác định phiên bản và cách command nhận tham số trước khi đăng ký converter.

| Phiên bản/mô hình | Cách cung cấp converter | Lưu ý |
|---|---|---|
| Spring Shell 2.1.x, standard annotation API | Đăng ký bean `Converter`, `GenericConverter` hoặc `ConverterFactory` trong ApplicationContext | Tài liệu 2.1.x mô tả Spring Shell tạo `DefaultConversionService` và thu thập các converter bean |
| Spring Shell 3.1.x, legacy `@ShellMethod` | Tham số method được chuyển đổi qua shell `ConversionService`; có thể cung cấp `ShellConversionServiceSupplier` | Không nhầm với `ConversionService` dùng để bind application properties |
| Spring Shell 3.1.x, new `@Command` hoặc `CommandRegistration` | Đường thực thi có khai báo kiểu tham số/option và dùng shell `ConversionService` có thể chuyển đổi kiểu miền | Với option programmatic, khai báo `.type(ProductId.class)` để parser biết kiểu đích |
| Spring Shell 4.x, `@Command` và `@Option` | Dùng Spring converter và shell-specific `ConversionService` | Bản 4.0.0 đến 4.0.2 có lỗi với custom converter trong `@Command`; bản 4.0.3 đã sửa |

## 5. Spring Shell 2.1.x: đăng ký converter bean

Tài liệu Spring Shell 2.1.x mô tả rõ rằng framework tạo `DefaultConversionService`, bật converter mặc định và đăng ký các bean có kiểu `Converter`, `GenericConverter` hoặc `ConverterFactory` được tìm thấy trong ApplicationContext.

Với ví dụ `ProductId`, converter đã có `@Component`, vì vậy Spring có thể phát hiện bean:

```java
@Component
public class StringToProductIdConverter implements Converter<String, ProductId> {

    @Override
    public ProductId convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Mã sản phẩm không được để trống.");
        }
        return new ProductId(source.trim().toUpperCase(Locale.ROOT));
    }
}
```

Command khai báo tham số trực tiếp bằng kiểu miền:

```java
@ShellComponent
public class ProductCommands {

    private final InventoryService inventoryService;

    public ProductCommands(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @ShellMethod(value = "Tra cứu tồn kho theo mã sản phẩm.", key = "stock show")
    public String show(ProductId productId) {
        return inventoryService.showStock(productId);
    }
}
```

Người dùng nhập:

```text
shell:>stock show SKU-123
```

Spring Shell chuyển token `SKU-123` thành `ProductId` trước khi gọi `show`. Nếu converter không thể tạo đối tượng, command không được thực thi và shell hiển thị lỗi chuyển đổi.

Khi muốn thay toàn bộ `ConversionService` trong Spring Shell 2.x, tài liệu hướng dẫn dùng service có qualifier `spring-shell`. Trong trường hợp đó, phải tự đăng ký cả converter tùy chỉnh lẫn các converter mặc định cần thiết. Không thay đổi service chỉ để thêm một cặp chuyển đổi đơn giản nếu có thể dùng converter bean.

## 6. Spring Shell 3.1.x: cung cấp shell ConversionService

Spring Shell 3.x có giao diện `ShellConversionServiceSupplier` trong package `org.springframework.shell.config`. Giao diện này là một `Supplier<ConversionService>` dành riêng cho shell. Auto-configuration sử dụng supplier này khi tạo các bộ phân giải tham số command.

Khi muốn kiểm soát chính xác converter nào được shell sử dụng, có thể cung cấp bean `ShellConversionServiceSupplier`. `DefaultConversionService` đã có các converter mặc định cho kiểu phổ biến; chỉ cần bổ sung converter miền.

```java
package com.example.inventory.shell.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.shell.config.ShellConversionServiceSupplier;

import com.example.inventory.shell.conversion.StringToProductIdConverter;

@Configuration
public class ShellConversionConfiguration {

    @Bean
    ShellConversionServiceSupplier shellConversionServiceSupplier(
            StringToProductIdConverter productIdConverter) {

        DefaultConversionService conversionService = new DefaultConversionService();
        conversionService.addConverter(productIdConverter);

        return () -> conversionService;
    }
}
```

Sau đó, legacy annotation model có thể khai báo tham số kiểu `ProductId`:

```java
@ShellComponent
public class ProductCommands {

    @ShellMethod(value = "Tra cứu tồn kho theo mã sản phẩm.", key = "stock show")
    public String show(@ShellOption(value = "--sku") ProductId productId) {
        return inventoryService.showStock(productId);
    }
}
```

Với command trên, lệnh nhập có thể là:

```text
shell:>stock show --sku SKU-123
```

`ShellConversionServiceSupplier` được dùng để cung cấp service cho cơ chế bind tham số của shell. Khi tự định nghĩa supplier, hãy thêm lại các converter mặc định bằng `DefaultConversionService` nếu ứng dụng cần chúng. Nếu dùng một implementation rỗng hoặc chỉ chứa converter miền, các kiểu số, enum và collection có thể không còn được xử lý như mong đợi.

### 6.1. New annotation model trong 3.1.x

Spring Shell 3.1.x có thêm annotation model mới dựa trên `@Command` và `@Option`. Khi command method khai báo tham số có kiểu miền, đường thực thi cần sử dụng argument resolver được cấu hình với shell `ConversionService`.

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProductCommands {

    @Command(command = "stock show", description = "Tra cứu tồn kho theo mã sản phẩm.")
    public String show(@Option(longNames = "sku") ProductId productId) {
        return inventoryService.showStock(productId);
    }
}
```

Lớp command còn phải được đăng ký theo cơ chế của annotation model mới, ví dụ `@EnableCommand` hoặc `@CommandScan`. Việc converter có thể chạy hay không phụ thuộc đường thực thi bind tham số có nhận shell `ConversionService` hay không; không chỉ dựa vào việc converter tồn tại như một Spring bean.

### 6.2. Programmatic model và kiểu option

Với `CommandRegistration`, builder cần biết kiểu đích của option. Hãy khai báo `.type(ProductId.class)` thay vì để option ở kiểu `String`.

```java
CommandRegistration registration = CommandRegistration.builder()
        .command("stock show")
        .withOption()
            .longNames("sku")
            .type(ProductId.class)
            .required()
            .description("Mã sản phẩm cần tra cứu")
            .and()
        .withTarget()
            .function(context -> {
                ProductId productId = context.getOptionValue("sku");
                return inventoryService.showStock(productId);
            })
            .and()
        .build();
```

Trong mô hình này, `type(ProductId.class)` là metadata để parser chuyển token đầu vào sang kiểu miền. Khi target đọc option từ `CommandContext`, giá trị đã được chuyển đổi theo kiểu được khai báo.

Nếu option vẫn được khai báo là `String.class`, `getOptionValue("sku")` sẽ trả về chuỗi. Trong trường hợp đó, target cần gọi `ConversionService.convert(...)` một cách tường minh hoặc đổi metadata option sang kiểu miền.

## 7. Spring Shell 4.x: custom converter với @Command

Spring Shell 4.x dùng package annotation mới `org.springframework.shell.core.command.annotation`. Ví dụ command khai báo `ProductId` trực tiếp trên tham số:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProductCommands {

    private final InventoryService inventoryService;

    public ProductCommands(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Command(name = "stock show", description = "Tra cứu tồn kho theo mã sản phẩm.")
    public String show(@Option(longName = "sku") ProductId productId) {
        return inventoryService.showStock(productId);
    }
}
```

Spring Shell 4.x vẫn cung cấp `ShellConversionServiceSupplier` trong package `org.springframework.shell.config`. Có thể sử dụng cùng cách cung cấp shell-specific `ConversionService` như ví dụ 3.1.x, nhưng phải dùng dependency và package của phiên bản 4.x.

**Lưu ý về bản phát hành:** Spring Shell 4.0.0, 4.0.1 và 4.0.2 có lỗi khiến custom converter không hoạt động đúng với command khai báo bằng `@Command`. Release notes của Spring Shell 4.0.3 ghi nhận lỗi này đã được sửa. Nếu sử dụng annotation model mới, hãy dùng 4.0.3 trở lên và kiểm thử lại converter trên đúng patch version.

## 8. ConverterFactory và GenericConverter

`Converter<String, ProductId>` phù hợp khi chỉ có một kiểu đích. Nếu cần chuyển đổi một họ kiểu miền có chung quy tắc, có thể dùng `ConverterFactory`.

Ví dụ, ứng dụng có nhiều kiểu mã định danh kế thừa từ một abstraction chung:

```java
public interface DomainCode {
    String value();
}

public record ProductCode(String value) implements DomainCode {}
public record WarehouseCode(String value) implements DomainCode {}
```

Một `ConverterFactory<String, DomainCode>` có thể tạo converter tương ứng với kiểu đích được yêu cầu. Cách này chỉ phù hợp khi các kiểu có chung quy tắc chuyển đổi; nếu mỗi kiểu có định dạng khác nhau, converter riêng thường dễ hiểu và an toàn hơn.

`GenericConverter` phù hợp khi một converter cần hỗ trợ nhiều cặp source/target hoặc phải đọc `TypeDescriptor`. Ví dụ, converter có thể xét generic type của collection hoặc annotation trên tham số. Vì `GenericConverter` phức tạp hơn, hãy chỉ dùng khi `Converter` hoặc `ConverterFactory` không đủ.

## 9. Phân biệt converter với validation và completion

Ba cơ chế này có nhiệm vụ khác nhau:

| Cơ chế | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| Converter | Chuỗi này biểu diễn đối tượng kiểu gì? | `SKU-123` → `ProductId` |
| Validation | Giá trị đã chuyển đổi có thỏa điều kiện không? | Số lượng phải lớn hơn 0 |
| Completion provider | Người dùng có thể nhập những giá trị nào? | Gợi ý `SKU-123`, `SKU-456` khi nhấn Tab |

Converter nên kiểm tra cú pháp và tạo value object hợp lệ. Validation có thể kiểm tra thêm constraint ở tham số hoặc method. Service/use case kiểm tra quy tắc nghiệp vụ cần dữ liệu hoặc trạng thái thực tế, chẳng hạn mã sản phẩm có tồn tại và người dùng có quyền truy cập hay không.

Không nên dùng converter để truy vấn cơ sở dữ liệu hoặc gọi dịch vụ từ xa cho mỗi token. Nếu chuyển đổi `SKU-123` phải tải sản phẩm từ database, command sẽ khó kiểm soát hiệu năng, lỗi mạng và giao dịch. Hãy chuyển thành `ProductId` trước, rồi để service truy vấn sản phẩm trong bước nghiệp vụ.

## 10. Thiết kế converter an toàn và dễ bảo trì

**Giữ converter đơn giản và không có side effect.** Converter nên xử lý một giá trị đầu vào và trả về một giá trị đích. Tránh ghi dữ liệu, gửi thông báo hoặc thay đổi trạng thái ứng dụng.

**Chuẩn hóa có chủ đích.** Có thể trim khoảng trắng hoặc chuẩn hóa chữ hoa/chữ thường nếu quy tắc miền cho phép. Không tự ý đổi định dạng làm mất ý nghĩa của dữ liệu.

**Báo lỗi có thể sửa được.** Khi dữ liệu sai, thông báo nên cho biết định dạng mong đợi. Không trả về `null` để che giấu lỗi parse.

**Giữ `toString()` có ý nghĩa.** Spring Shell có thể hiển thị `value.toString()` trong thông báo validation. Với value object, nên trả về dạng chuỗi chuẩn đã dùng để tạo đối tượng, ví dụ `SKU-123`, thay vì dạng debug như `ProductId[value=SKU-123]`.

**Đảm bảo thread-safety.** `ConversionService` và converter thường được dùng chung giữa nhiều lệnh hoặc luồng. Không lưu trạng thái của một lần chuyển đổi vào field có thể thay đổi.

**Tránh converter trùng cặp kiểu.** Không đăng ký nhiều converter cùng source/target nhưng cho kết quả khác nhau. Nếu có nhiều cách parse, hãy dùng format rõ ràng hoặc tách kiểu đích để không gây mơ hồ.

## 11. Những nhầm lẫn thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Spring Shell vẫn nhận `String` | Tham số hoặc `OptionSpec.type` vẫn khai báo `String` | Khai báo kiểu miền ở tham số hoặc `.type(ProductId.class)` |
| Converter bean tồn tại nhưng command không dùng | Đường thực thi chưa sử dụng shell `ConversionService` hoặc service chưa đăng ký converter | Kiểm tra `ShellConversionServiceSupplier` và argument resolver của mô hình đang dùng |
| Chỉ cấu hình bean `conversionService` nhưng shell không chuyển đổi | Đó có thể là service dùng cho property binding của Spring Boot | Cung cấp shell-specific service bằng `ShellConversionServiceSupplier` khi cần |
| Kiểu số/enum mặc định không còn hoạt động sau khi tùy biến | Custom service không giữ converter mặc định | Bắt đầu từ `DefaultConversionService` rồi thêm converter riêng |
| `@Command` không dùng custom converter ở Spring Shell 4.0.0–4.0.2 | Lỗi của các bản đầu trong nhánh 4.x | Nâng lên Spring Shell 4.0.3 trở lên |
| Converter không được gọi trong programmatic model | Option được khai báo sai kiểu hoặc target đọc raw string | Khai báo `.type(ProductId.class)` hoặc chuyển đổi tường minh trong target |
| Lỗi định dạng chỉ xuất hiện trong service | Converter chưa kiểm tra cú pháp đầu vào | Kiểm tra cấu trúc chuỗi trong converter/value object; để service xử lý quy tắc nghiệp vụ |
| Thông báo validation khó đọc | `toString()` trả về dạng debug hoặc không ổn định | Trả về chuỗi chuẩn và dễ nhận biết |

Không nhầm converter của Spring Shell với `@ConfigurationPropertiesBinding` của Spring Boot. Annotation đó dành cho chuyển đổi cấu hình bên ngoài khi bind `@ConfigurationProperties`; nó không phải điểm đăng ký converter chuyên biệt cho tham số command.

## 12. Kiểm thử converter và đường thực thi command

Kiểm thử converter độc lập trước, sau đó kiểm thử tích hợp với shell. Điều này giúp phân biệt lỗi parse của converter với lỗi đăng ký command hoặc lỗi cấu hình conversion service.

### 12.1. Unit test cho converter

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class StringToProductIdConverterTests {

    private final StringToProductIdConverter converter =
            new StringToProductIdConverter();

    @Test
    void convertsAndNormalizesSku() {
        ProductId productId = converter.convert(" sku-123 ");

        assertThat(productId.value()).isEqualTo("SKU-123");
        assertThat(productId.toString()).isEqualTo("SKU-123");
    }

    @Test
    void rejectsInvalidSku() {
        assertThatThrownBy(() -> converter.convert("123"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("SKU-");
    }
}
```

### 12.2. Kiểm tra ConversionService

```java
DefaultConversionService conversionService = new DefaultConversionService();
conversionService.addConverter(new StringToProductIdConverter());

assertThat(conversionService.canConvert(String.class, ProductId.class)).isTrue();

ProductId productId = conversionService.convert("SKU-123", ProductId.class);
assertThat(productId).isEqualTo(new ProductId("SKU-123"));
```

### 12.3. Kiểm thử tích hợp command

Khởi động Spring Shell test context với cấu hình converter thật và chạy command qua test client. Xác nhận các trường hợp:

1. Giá trị hợp lệ được chuyển thành đúng kiểu miền và service nhận đúng đối tượng.
2. Giá trị sai định dạng bị từ chối trước khi service được gọi.
3. Giá trị có khoảng trắng hoặc chữ thường được chuẩn hóa đúng theo hợp đồng.
4. Converter vẫn hoạt động với command ở chế độ non-interactive nếu ứng dụng sử dụng script/automation.
5. Các kiểu mặc định như số, enum và Boolean vẫn hoạt động sau khi thay shell `ConversionService`.
6. Trên Spring Shell 4.x, chạy kiểm thử với bản 4.0.3 trở lên để xác nhận custom converter hoạt động cùng `@Command`.

## 13. Quy trình triển khai

1. Xác định kiểu miền cần nhận từ command và định nghĩa rõ biểu diễn chuỗi của nó.
2. Tạo value object để bảo vệ bất biến và tạo `Converter<String, DomainType>`.
3. Viết unit test cho đầu vào hợp lệ, không hợp lệ, khoảng trắng và chuẩn hóa.
4. Xác định phiên bản Spring Shell và mô hình command đang dùng.
5. Đăng ký converter theo cơ chế được hỗ trợ: converter bean trong 2.1.x, shell-specific `ConversionService` qua `ShellConversionServiceSupplier` trong 3.x/4.x, và dùng phiên bản 4.0.3+ cho `@Command`.
6. Khai báo tham số hoặc option với đúng kiểu miền để framework thực hiện chuyển đổi.
7. Chạy kiểm thử tích hợp, kiểm tra cả lỗi parse lẫn các converter mặc định.
8. Giữ truy vấn dữ liệu và quy tắc nghiệp vụ trong service/use case, không đặt chúng trong converter.

## 14. Tổng kết

Converter giúp Spring Shell chuyển token văn bản thành kiểu miền trước khi gọi command. `Converter<S, T>` phù hợp cho một cặp kiểu; `ConverterFactory` và `GenericConverter` dành cho những trường hợp tổng quát hơn. Spring Shell 2.1.x mô tả cơ chế thu thập converter bean; Spring Shell 3.x/4.x cung cấp `ShellConversionServiceSupplier` để cấp `ConversionService` riêng cho shell.

Việc đăng ký converter chỉ có tác dụng khi đường thực thi command sử dụng service đó và biết kiểu đích cần nhận. Hãy khai báo kiểu miền trên tham số method hoặc option registration, kiểm tra converter bằng unit test và kiểm thử qua shell. Với Spring Shell 4.x annotation model, dùng phiên bản 4.0.3 trở lên để có bản sửa lỗi custom converter với `@Command`.

## Tài liệu tham khảo

- [Spring Shell 2.1.x Reference Documentation — Customizing Arguments Conversion](https://docs.spring.io/spring-shell/docs/2.1.0-M2/site/reference/htmlsingle/) — cơ chế đăng ký `Converter`, `GenericConverter` và `ConverterFactory` bean.
- [Spring Shell 3.1.3 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — mục 3.1 Reading Docs, 4.1 Registration và 5.9 Types.
- [ShellConversionServiceSupplier API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/config/ShellConversionServiceSupplier.html) — điểm cung cấp `ConversionService` dành riêng cho shell.
- [ParameterResolverAutoConfiguration API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/boot/ParameterResolverAutoConfiguration.html) — argument resolver nhận `ShellConversionServiceSupplier`.
- [Spring Framework Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html) — `Converter`, `ConverterFactory`, `GenericConverter` và `ConversionService`.
- [Spring Shell 4.x Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — mô hình annotation mới và thay đổi khi nâng từ 3.x lên 4.x.
- [Spring Shell Releases](https://github.com/spring-projects/spring-shell/releases) — ghi chú bản 4.0.3 sửa lỗi custom converter không hoạt động với `@Command`.
