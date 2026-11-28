# Kiểm thử ràng buộc ở đúng mô hình annotation hoặc builder đang dùng

Khi người dùng nhập command, Spring Shell cần kiểm tra đầu vào trước khi gọi nghiệp vụ. Một số kiểm tra thuộc parser, chẳng hạn option có được truyền hay không và chuỗi có chuyển được thành số nguyên không. Những kiểm tra khác là ràng buộc dữ liệu, chẳng hạn mã SKU không được rỗng, số lượng phải lớn hơn 0 hoặc mật khẩu phải có độ dài tối thiểu. Sau đó, service còn phải kiểm tra quy tắc nghiệp vụ như sản phẩm có tồn tại và người dùng có quyền điều chỉnh tồn kho.

Spring Shell tích hợp Bean Validation để kiểm tra các annotation trên tham số command trước khi thực thi. Cách khai báo này phù hợp với command dùng annotation. Khi đăng ký command bằng `CommandRegistration` và một `Function<CommandContext, ?>`, builder mô tả cấu trúc option nhưng không cung cấp thuộc tính tương đương `@Min`, `@Pattern` hay `@NotBlank` trên từng option. Target cần gọi `jakarta.validation.Validator` hoặc ủy quyền cho service đã có cơ chế validation.

Bài học dùng Spring Shell 3.1.3 làm mốc cho legacy annotation, annotation model mới và `CommandRegistration`; phần cuối đối chiếu cú pháp annotation trong Spring Shell 4.0.4. Ví dụ dùng Spring Boot 3.x, Jakarta Bean Validation và Java 17.

## 1. Phân biệt các lớp kiểm tra đầu vào

Không phải mọi lỗi đầu vào đều là lỗi Bean Validation. Hãy xác định dữ liệu đang ở giai đoạn nào và cơ chế nào chịu trách nhiệm kiểm tra.

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ | Cơ chế phù hợp |
|---|---|---|---|
| Phân tích cú pháp | Token có khớp cú pháp command không? | Thiếu `--sku`, sai arity, option không tồn tại | Spring Shell parser |
| Chuyển đổi kiểu | Giá trị có chuyển được sang kiểu Java không? | `abc` không chuyển thành `Integer` | Spring `ConversionService` / parser |
| Ràng buộc dữ liệu | Giá trị đã bind có thỏa giới hạn khai báo không? | SKU không rỗng, quantity từ 1 đến 10.000 | Bean Validation |
| Quy tắc nghiệp vụ | Thao tác có hợp lệ với trạng thái hiện tại không? | SKU có tồn tại, kho còn đủ hàng, người dùng có quyền | Service/use case |

Ví dụ với command `stock adjust`:

- Không truyền `--sku`: parser báo thiếu option bắt buộc.
- Truyền `--quantity abc`: parser không chuyển được `abc` thành số nguyên.
- Truyền `--quantity 0`: chuyển đổi thành công, nhưng `@Min(1)` từ chối giá trị.
- Truyền `--quantity 5` cho SKU không tồn tại: dữ liệu qua được parse và Bean Validation, nhưng service từ chối vì vi phạm nghiệp vụ.

Tách các lớp này giúp thông báo lỗi rõ ràng và giúp bài kiểm thử nhắm đúng thành phần cần xác minh.

## 2. Chuẩn bị Bean Validation

Spring Shell tích hợp với Jakarta Bean Validation. Ứng dụng cần có implementation của đặc tả này trên classpath; trong ứng dụng Spring Boot, dependency thường dùng là `spring-boot-starter-validation`.

**Maven:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Với Spring Boot, starter này đưa Hibernate Validator và các thành phần cần thiết vào ứng dụng. Nếu không dùng Spring Boot, cần cấu hình một Bean Validation provider và có thể khai báo `LocalValidatorFactoryBean` để đăng ký `Validator` trong Spring context.

Các constraint thông dụng:

| Annotation | Điều kiện |
|---|---|
| `@NotNull` | Giá trị không phải `null` |
| `@NotBlank` | Chuỗi không `null`, không rỗng và có ký tự không phải khoảng trắng |
| `@NotEmpty` | Chuỗi, collection, map hoặc mảng không `null` và không rỗng |
| `@Size(min, max)` | Kích thước chuỗi/collection/mảng nằm trong giới hạn |
| `@Min(value)` / `@Max(value)` | Giá trị số nằm trong giới hạn |
| `@Positive` / `@PositiveOrZero` | Giá trị số dương hoặc không âm |
| `@Pattern(regexp)` | Chuỗi khớp biểu thức chính quy |
| `@Email` | Chuỗi có định dạng email được validator chấp nhận |
| `@Valid` | Kiểm tra tiếp các đối tượng lồng bên trong |

Constraint chỉ có hiệu lực khi có validator thực sự được gọi. Đặt annotation lên một field hoặc tham số không tự làm cho mọi lời gọi Java trong ứng dụng được kiểm tra.

## 3. Legacy annotation model: @ShellMethod và @ShellOption

Trong Spring Shell 3.1.x, legacy annotation model dùng `@ShellComponent`, `@ShellMethod` và `@ShellOption`. Spring Shell đọc các constraint trên tham số command và kiểm tra chúng trước khi gọi phương thức.

Ví dụ, mã sản phẩm phải có dạng `SKU-` theo sau bởi 3 đến 12 chữ cái in hoa hoặc chữ số; số lượng điều chỉnh phải nằm trong khoảng từ 1 đến 10.000:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class StockCommands {

    private final InventoryService inventoryService;

    public StockCommands(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @ShellMethod(value = "Điều chỉnh số lượng tồn kho.", key = "stock adjust")
    public String adjust(
            @ShellOption(value = "--sku")
            @NotBlank
            @Pattern(regexp = "SKU-[A-Z0-9]{3,12}")
            String sku,
            @ShellOption(value = "--quantity")
            @Min(1)
            @Max(10000)
            int quantity) {

        return inventoryService.adjust(sku, quantity);
    }
}
```

Các lệnh mẫu:

```text
shell:>stock adjust --sku SKU-123 --quantity 5
Đã điều chỉnh tồn kho.

shell:>stock adjust --sku SKU-123 --quantity 0
The following constraints were not met:
  --quantity int : must be greater than or equal to 1

shell:>stock adjust --sku bad-code --quantity 5
The following constraints were not met:
  --sku String : must match "SKU-[A-Z0-9]{3,12}"
```

Thông báo thực tế phụ thuộc phiên bản, message bundle và cách hiển thị kết quả. Điểm quan trọng là khi constraint không đạt, phương thức `adjust` không được gọi.

### 3.1. Phân biệt required với @NotBlank

Option bắt buộc và constraint kiểm tra nội dung giải quyết hai vấn đề khác nhau:

- `@ShellOption` không có default (hoặc cấu hình mandatory tương ứng) khiến parser yêu cầu người dùng truyền option.
- `@NotBlank` kiểm tra giá trị chuỗi sau khi đã được bind.

Nếu người dùng truyền `--sku ""` hoặc `--sku "   "`, option đã hiện diện nên kiểm tra required không đủ để từ chối chuỗi rỗng. `@NotBlank` xử lý trường hợp đó. `@NotNull` cũng không thay thế `@NotBlank`, vì chuỗi rỗng không phải `null`.

### 3.2. Ràng buộc trên method

Tài liệu Spring Shell 3.1.3 nêu rõ constraint trên tham số command và constraint ở cấp method được kích hoạt trước khi command thực thi. Constraint ở cấp method hữu ích cho điều kiện liên quan nhiều tham số, chẳng hạn ngày bắt đầu phải trước ngày kết thúc.

Với constraint cross-parameter tùy chỉnh, cần khai báo validator theo Bean Validation API với `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`. Đây là phần mở rộng nâng cao; với command đơn giản, nên ưu tiên constraint trên từng tham số hoặc chuyển dữ liệu thành một request object để kiểm tra tập trung.

## 4. Annotation model mới trong Spring Shell 3.1.x

Spring Shell 3.1.x có annotation model mới dùng `@Command` và `@Option`. Constraint Bean Validation vẫn được đặt trực tiếp trên tham số phương thức command; khác biệt nằm ở annotation dùng để đăng ký command và option.

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class StockCommands {

    private final InventoryService inventoryService;

    public StockCommands(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Command(command = "stock adjust", description = "Điều chỉnh số lượng tồn kho.")
    public String adjust(
            @Option(longNames = "sku", required = true)
            @NotBlank
            @Pattern(regexp = "SKU-[A-Z0-9]{3,12}")
            String sku,
            @Option(longNames = "quantity", required = true)
            @Min(1)
            @Max(10000)
            int quantity) {

        return inventoryService.adjust(sku, quantity);
    }
}
```

Lớp chứa command cần được đăng ký bằng `@EnableCommand` hoặc `@CommandScan` theo cấu hình của ứng dụng. Ví dụ trên chỉ minh họa phần khai báo command và constraint.

### 4.1. Không trộn annotation của hai mô hình

| Mục đích | Legacy model | New annotation model |
|---|---|---|
| Đánh dấu lớp command | `@ShellComponent` | Bean Spring, thường là `@Component` |
| Đánh dấu phương thức | `@ShellMethod` | `@Command` |
| Khai báo tên option | `@ShellOption` | `@Option` |
| Ràng buộc dữ liệu | `@NotBlank`, `@Min`, `@Pattern`, ... | Cùng các constraint Bean Validation |

Không đặt `@ShellOption` lên phương thức `@Command` hoặc `@Option` lên phương thức legacy rồi kỳ vọng framework tự hợp nhất hai mô hình. Hãy chọn một cách đăng ký command nhất quán; các constraint Jakarta Validation có thể dùng chung.

## 5. Programmatic model: phân biệt kiểm tra parser và Bean Validation

Với `CommandRegistration`, builder mô tả command và option. Các cấu hình như `.required()`, `.type(...)`, `.arity(...)` và `.defaultValue(...)` kiểm soát việc phân tích và bind đầu vào.

```java
CommandRegistration registration = CommandRegistration.builder()
        .command("stock adjust")
        .withOption()
            .longNames("sku")
            .type(String.class)
            .required()
            .and()
        .withOption()
            .longNames("quantity")
            .type(Integer.class)
            .required()
            .and()
        .withTarget()
            .function(context -> {
                String sku = context.getOptionValue("sku");
                Integer quantity = context.getOptionValue("quantity");
                return inventoryService.adjust(sku, quantity);
            })
            .and()
        .build();
```

Builder có thể tự từ chối option bị thiếu hoặc giá trị không chuyển được sang kiểu khai báo. Tuy nhiên, `.required()` không kiểm tra chuỗi có rỗng hay không, `.type(Integer.class)` không kiểm tra số lượng có dương hay không, và `.arity(...)` chỉ kiểm tra số token được nhận. Những cấu hình này không thay thế `@NotBlank`, `@Min` hoặc `@Max`.

Với target dạng `Function<CommandContext, ?>`, builder không có thuộc tính constraint tương đương để gắn `@Min` hoặc `@Pattern` trực tiếp lên từng `OptionSpec`. Hãy tạo một đối tượng đầu vào có constraint rồi gọi `Validator.validate(...)` trước khi gọi service.

## 6. Kiểm tra Bean Validation thủ công trong builder target

Tạo request object gom các giá trị cần kiểm tra. Constraint đặt trên record component sẽ được Bean Validation sử dụng khi kiểm tra instance.

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record AdjustStockRequest(
        @NotBlank
        @Pattern(regexp = "SKU-[A-Z0-9]{3,12}")
        String sku,
        @NotNull
        @Min(1)
        @Max(10000)
        Integer quantity) {
}
```

Sau đó, inject `jakarta.validation.Validator` vào cấu hình đăng ký command:

```java
import java.util.Comparator;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class StockCommandConfiguration {

    @Bean
    CommandRegistration adjustStockCommand(
            Validator validator,
            InventoryService inventoryService) {

        return CommandRegistration.builder()
                .command("stock adjust")
                .description("Điều chỉnh số lượng tồn kho.")
                .withOption()
                    .longNames("sku")
                    .type(String.class)
                    .required()
                    .and()
                .withOption()
                    .longNames("quantity")
                    .type(Integer.class)
                    .required()
                    .and()
                .withTarget()
                    .function(context -> {
                        AdjustStockRequest request = new AdjustStockRequest(
                                context.getOptionValue("sku"),
                                context.getOptionValue("quantity"));

                        var violations = validator.validate(request);
                        if (!violations.isEmpty()) {
                            String message = violations.stream()
                                    .sorted(Comparator.comparing(v ->
                                            v.getPropertyPath().toString()))
                                    .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                                    .collect(Collectors.joining("; "));
                            throw new IllegalArgumentException(
                                    "Dữ liệu không hợp lệ: " + message);
                        }

                        return inventoryService.adjust(
                                request.sku(), request.quantity());
                    })
                    .and()
                .build();
    }
}
```

Trong ví dụ này, parser vẫn kiểm tra option bắt buộc và chuyển `quantity` sang `Integer`. Sau khi tạo `AdjustStockRequest`, Bean Validation kiểm tra định dạng SKU và giới hạn số lượng. Chỉ khi không còn violation, target mới gọi `inventoryService.adjust(...)`.

Nếu muốn giữ thông báo lỗi thân thiện và mã thoát phù hợp, có thể dùng exception riêng cho lỗi đầu vào và cấu hình `CommandExceptionResolver` cho command. Không nên trả về kết quả thành công khi validation thất bại.

### 6.1. Vì sao nên gom dữ liệu vào request object?

Một request object giúp kiểm tra các ràng buộc liên quan nhiều trường và dùng lại cùng constraint trong nhiều kênh đầu vào. Ví dụ, nếu `startDate` phải trước `endDate`, có thể đặt class-level constraint lên request và kiểm tra toàn bộ object bằng `validator.validate(request)`.

Không nên đặt truy vấn database vào `ConstraintValidator` chỉ để kiểm tra SKU có tồn tại. Đó là quy tắc nghiệp vụ cần thực hiện trong service, nơi có transaction, quyền truy cập và ngữ cảnh phù hợp.

## 7. Kiểm tra ở service/use case

Một service có thể được gọi từ CLI, REST API, batch hoặc message consumer. Những quy tắc quan trọng cần được bảo vệ ở tầng nghiệp vụ để không phụ thuộc vào việc caller có đi qua Spring Shell hay không.

Ví dụ:

```java
public String adjust(String sku, int quantity) {
    Product product = productRepository.findBySku(sku)
            .orElseThrow(() -> new ProductNotFoundException(sku));

    if (quantity > product.getMaximumAdjustment()) {
        throw new InvalidStockAdjustmentException(
                "Số lượng vượt mức điều chỉnh cho phép.");
    }

    // Kiểm tra quyền, trạng thái kho và cập nhật theo quy tắc nghiệp vụ.
    return "Đã điều chỉnh tồn kho.";
}
```

Nếu muốn dùng Bean Validation ở biên service, có thể khai báo constraint trên tham số phương thức và dùng Spring method validation với class `@Validated`. Đây là cơ chế method validation của Spring Framework, dựa trên AOP proxy. Nó khác với cơ chế Spring Shell kiểm tra constraint trên tham số command trước khi target chạy.

## 8. Kiểm thử constraint trong annotation model

Nên có hai lớp kiểm thử: kiểm thử validator/constraint độc lập và kiểm thử tích hợp qua Spring Shell. Unit test xác nhận rule đúng; integration test xác nhận Spring Shell thực sự kích hoạt rule trước khi gọi command.

### 8.1. Unit test cho request hoặc constraint

Với annotation model, có thể kiểm tra trực tiếp đối tượng hoặc validator được dùng cho command. Ví dụ kiểm tra request object:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class AdjustStockRequestValidationTests {

    @Autowired
    Validator validator;

    @Test
    void rejectsZeroQuantity() {
        AdjustStockRequest request = new AdjustStockRequest("SKU-123", 0);

        Set<ConstraintViolation<AdjustStockRequest>> violations =
                validator.validate(request);

        assertThat(violations)
                .anySatisfy(violation -> {
                    assertThat(violation.getPropertyPath().toString())
                            .isEqualTo("quantity");
                });
    }

    @Test
    void rejectsMalformedSku() {
        AdjustStockRequest request = new AdjustStockRequest("bad", 5);

        Set<ConstraintViolation<AdjustStockRequest>> violations =
                validator.validate(request);

        assertThat(violations)
                .anySatisfy(violation -> {
                    assertThat(violation.getPropertyPath().toString())
                            .isEqualTo("sku");
                });
    }
}
```

Unit test này kiểm tra constraint trên request. Với command annotation, vẫn cần integration test để chứng minh Spring Shell đã đọc annotation trên tham số phương thức.

### 8.2. Integration test qua ShellTestClient

Spring Shell 3.1.3 cung cấp `spring-shell-test` và `spring-shell-test-autoconfigure`. `@ShellTest` tạo môi trường kiểm thử shell; `ShellTestClient` có thể chạy command non-interactive và đọc màn hình kết quả.

```java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.SECONDS;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.annotation.DirtiesContext;

@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class StockCommandValidationTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    InventoryService inventoryService;

    @Test
    void rejectsQuantityBelowMinimumBeforeCallingService() {
        var session = client.nonInterative(
                "stock", "adjust",
                "--sku", "SKU-123",
                "--quantity", "0")
                .run();

        await().atMost(2, SECONDS).untilAsserted(() -> {
            ShellAssertions.assertThat(session.screen())
                    .containsText("The following constraints were not met")
                    .containsText("--quantity");
        });

        org.mockito.Mockito.verifyNoInteractions(inventoryService);
    }
}
```

Phương thức `nonInterative(...)` là tên API trong Spring Shell 3.1.x. Các bản mới hơn có thể cung cấp tên `nonInteractive(...)`; hãy dùng API của đúng phiên bản dependency. Trong Spring Shell 4.0.4, phần validation minh họa lỗi command với trạng thái `USAGE_ERROR`, vì vậy kiểm tra cả nội dung lỗi và việc target không được thực thi.

## 9. Kiểm thử constraint trong programmatic builder

Với builder target dạng `Function`, hãy kiểm thử cả validator lẫn đường chạy command:

1. Unit test `validator.validate(request)` với dữ liệu hợp lệ và không hợp lệ.
2. Integration test gửi token qua `CommandRegistration` và xác nhận target không gọi service khi request vi phạm constraint.
3. Kiểm thử riêng các lỗi parser như thiếu option, sai kiểu hoặc sai arity; đây không phải Bean Validation violation.

Ví dụ unit test cho request dùng trong builder:

```java
@Test
void builderRequestRejectsQuantityAboveLimit() {
    AdjustStockRequest request = new AdjustStockRequest("SKU-123", 10001);

    var violations = validator.validate(request);

    assertThat(violations)
            .anySatisfy(violation -> {
                assertThat(violation.getPropertyPath().toString())
                        .isEqualTo("quantity");
            });
}
```

Trong integration test của builder command, gửi `stock adjust --sku SKU-123 --quantity 0`, kiểm tra thông báo `Dữ liệu không hợp lệ` có trường `quantity`, và xác nhận `InventoryService` chưa được gọi. Gửi `--quantity abc` trong một test riêng để xác nhận parser từ chối lỗi chuyển đổi trước khi Function được thực thi.

Nếu builder dùng `.withTarget().method(...)` để gọi một phương thức POJO thay vì Function, hãy kiểm tra hành vi của adapter method target trên đúng phiên bản. Khi cần hành vi nhất quán, có thể đặt validation rõ ràng trong request/service hoặc dùng Function và gọi `Validator` trực tiếp như ví dụ trên.

## 10. Kiểm thử ràng buộc tùy chỉnh và ràng buộc nhiều trường

Khi constraint mặc định không diễn đạt đủ quy tắc, có thể tạo annotation `@Constraint` và lớp `ConstraintValidator`.

Ví dụ nghiệp vụ yêu cầu ngày bắt đầu không được sau ngày kết thúc. Có thể tạo request object với class-level constraint `@ValidDateRange` rồi gọi `validator.validate(request)` trong builder target. Với annotation command, constraint có thể được đặt lên kiểu tham số request và kích hoạt cascade bằng `@Valid` nếu đường bind hỗ trợ kiểu đó.

Khi kiểm thử custom constraint, cần bao gồm:

- Dữ liệu nằm đúng biên dưới và biên trên.
- Dữ liệu lệch một đơn vị so với biên.
- Giá trị `null`, chuỗi rỗng hoặc collection rỗng nếu các trường hợp này có ý nghĩa.
- Hai trường hợp liên trường: ngày bắt đầu trước ngày kết thúc và ngày bắt đầu sau ngày kết thúc.
- Message template và message sau khi nội suy.
- Constraint không làm thay đổi dữ liệu hoặc gọi service ngoài dự kiến.

## 11. Các lỗi kiểm thử thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Annotation có trên tham số nhưng không có lỗi validation | Thiếu Bean Validation provider hoặc command không đi qua cơ chế validation của Spring Shell | Kiểm tra dependency `spring-boot-starter-validation`, mô hình đăng ký và phiên bản |
| Option thiếu bị báo lỗi nhưng chuỗi rỗng vẫn qua | Chỉ dùng `required`, chưa dùng `@NotBlank` | Kết hợp required với constraint nội dung |
| `--quantity abc` báo lỗi parse thay vì `@Min` | Chuyển đổi kiểu thất bại trước Bean Validation | Kiểm thử lỗi parse riêng; dùng số hợp lệ nhưng nằm ngoài miền để kiểm tra `@Min` |
| Builder command không kích hoạt `@Min` trên Function target | Function chỉ nhận `CommandContext`; builder không tự áp constraint lên giá trị option | Tạo request object và gọi `Validator.validate` trong target |
| Validation thất bại nhưng service vẫn chạy | Target gọi service trước khi kiểm tra violation | Chỉ gọi service sau khi tập violation rỗng |
| Test khởi tạo shell bị treo hoặc không ổn định | Test vô tình chạy REPL tương tác hoặc đọc màn hình quá sớm | Dùng `ShellTestClient` non-interactive và chờ output bằng Awaitility |
| Test không tìm thấy thông báo lỗi | Nội dung thay đổi theo locale hoặc phiên bản | Kiểm tra message ổn định, tên option hoặc `ConstraintViolation` thay vì khớp toàn bộ chuỗi |
| Constraint trong service không chạy | Service chưa bật method validation hoặc lời gọi không đi qua Spring proxy | Kiểm tra `@Validated`, provider và đường gọi qua proxy |

## 12. Ma trận kiểm thử đề xuất

Với command điều chỉnh tồn kho, tối thiểu nên có các trường hợp sau:

| Đầu vào | Lớp dự kiến xử lý | Kết quả mong đợi |
|---|---|---|
| Không truyền `--sku` | Parser | Báo thiếu option bắt buộc |
| `--sku ""` | Bean Validation | `@NotBlank` thất bại |
| `--sku bad` | Bean Validation | `@Pattern` thất bại |
| `--quantity abc` | Parser/conversion | Không chuyển được thành Integer |
| `--quantity 0` | Bean Validation | `@Min(1)` thất bại |
| `--quantity 10001` | Bean Validation | `@Max(10000)` thất bại |
| `--quantity 5` với SKU không tồn tại | Service | Báo không tìm thấy sản phẩm |
| `--quantity 5` với SKU hợp lệ | Service | Điều chỉnh thành công |

Với annotation model, xác nhận constraint được kích hoạt trước khi phương thức command chạy. Với builder model, xác nhận Function gọi `Validator` trước khi gọi service. Với cả hai, kiểm tra thông báo đủ rõ để người vận hành sửa đúng option.

## 13. Nguyên tắc thiết kế

- Dùng constraint trên tham số command cho kiểm tra dữ liệu đơn giản, độc lập từng tham số.
- Dùng request object khi có nhiều trường cần kiểm tra cùng nhau hoặc cần tái sử dụng constraint ở nhiều đầu vào.
- Dùng `.required()`, `.type()`, `.arity()` và `.defaultValue()` trong builder cho cấu trúc và parse option.
- Dùng `Validator` trong Function target khi builder cần kiểm tra constraint Bean Validation.
- Để service bảo vệ quy tắc nghiệp vụ và trạng thái dữ liệu, kể cả khi command đã qua Bean Validation.
- Không dùng `@NotNull` thay cho `@NotBlank`; không dùng `required` thay cho kiểm tra nội dung chuỗi.
- Kiểm thử riêng parse, Bean Validation và nghiệp vụ để xác định lỗi thuộc lớp nào.
- Tránh đưa thông tin nhạy cảm như mật khẩu vào thông báo lỗi hoặc log. Ví dụ Spring Shell chính thức cũng khuyến cáo không in mật khẩu ra terminal.

## 14. Ranh giới phiên bản

Spring Shell 3.1.3 mô tả legacy annotation model (`@ShellMethod`, `@ShellOption`), new annotation model (`@Command`, `@Option`) và programmatic model (`CommandRegistration`). Phần Validation của tài liệu 3.1.3 nêu constraint trên tham số command và ở cấp method được kích hoạt trước khi thực thi.

Spring Shell 4.x đã bỏ legacy annotation model. Trong Spring Shell 4.0.4, tài liệu Option Validation minh họa constraint trên tham số `@Option` của phương thức `@Command`; lỗi được hiển thị kèm tên option và trạng thái `USAGE_ERROR`. Với builder target nhận `CommandContext`, tiếp tục phân biệt cấu hình parser với kiểm tra Bean Validation tường minh.

Khi nâng phiên bản, hãy chạy lại integration test cho từng command. Đừng chỉ kiểm tra unit test của `Validator`, vì unit test không chứng minh Spring Shell đã kết nối đúng annotation, parser, target và result handler.

## 15. Tổng kết

Trong annotation model, Spring Shell có thể đọc constraint Bean Validation trực tiếp trên tham số command và kiểm tra trước khi gọi phương thức. Dùng `@NotBlank`, `@Pattern`, `@Min`, `@Max` và các constraint phù hợp; kết hợp required của option với constraint nội dung để xử lý cả trường hợp thiếu và rỗng.

Trong programmatic builder, `.required()`, `.type()` và `.arity()` kiểm tra cấu trúc đầu vào. Với target dạng Function, hãy tạo request object có constraint, gọi `Validator.validate(...)`, xử lý violation rồi mới gọi service. Luôn kiểm thử ở ba lớp: parser, Bean Validation và nghiệp vụ; integration test qua `ShellTestClient` xác nhận command thực sự tuân thủ các ràng buộc.

## Tài liệu tham khảo

- [Spring Shell 3.1.3 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — mục 5.7 Validation, 4.1 Registration và 11 Testing.
- [Spring Shell 4.0.4 Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html) — constraint trên tham số `@Option`, thông báo vi phạm và trạng thái `USAGE_ERROR`.
- [Spring Shell 4.0.4 Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) — khai báo `@Command`, `@Option` và cấu trúc tham số.
- [Spring Shell 3.1.x ShellTestClient API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.html) — chạy phiên shell tương tác và non-interactive trong kiểm thử.
- [Spring Framework: Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html) — provider, `Validator`, custom constraint và method validation.
- [Spring Boot: Validation](https://docs.spring.io/spring-boot/reference/io/validation.html) — cấu hình method validation và dependency Bean Validation trong ứng dụng Spring Boot.
