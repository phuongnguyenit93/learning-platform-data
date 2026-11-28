# CompletionProvider ở phạm vi command trong 4.x

Spring Shell 4 chuyển cơ chế tự hoàn thành từ cách khai báo riêng cho từng option sang một `CompletionProvider` ở phạm vi command. Provider nhận toàn bộ ngữ cảnh của dòng lệnh hiện tại và trả về danh sách gợi ý. Nhờ đó, cùng một provider có thể gợi ý tên option, giá trị option, argument hoặc đề xuất phụ thuộc vào những option người dùng đã nhập trước đó.

Ví dụ, khi người vận hành chạy `stock show`, danh sách SKU cần gợi ý có thể phụ thuộc vào kho đã chọn. Nếu người dùng đã nhập `--warehouse HCM`, nhấn Tab tại `--sku` nên chỉ gợi ý những SKU thuộc kho HCM. Đây là trường hợp mà completion ở phạm vi command giải quyết tự nhiên hơn các provider tách rời theo từng option.

Bài học sử dụng API Spring Shell 4.0.4 trong package `org.springframework.shell.core.command.completion`. Các ví dụ dùng annotation model mới `@Command`/`@Option`; phần cuối so sánh với cách hoàn thành theo từng option trong Spring Shell 3.x.

## 1. CompletionProvider ở phạm vi command là gì?

`CompletionProvider` là một functional interface nhận `CompletionContext` và trả về `List<CompletionProposal>`:

```java
@FunctionalInterface
public interface CompletionProvider
        extends Function<CompletionContext, List<CompletionProposal>> {
}
```

Khi người dùng nhấn Tab trong shell tương tác dựa trên JLine, Spring Shell gọi provider gắn với command hiện tại. Provider đọc ngữ cảnh và quyết định những đề xuất phù hợp.

Trong Spring Shell 4, khai báo provider ở thuộc tính `completionProvider` của `@Command`. Giá trị thuộc tính là tên bean trong Spring ApplicationContext. Nếu dùng mô hình đăng ký command bằng Java, có thể đặt provider trực tiếp bằng `Command.Builder.completionProvider(...)`.

Khác biệt quan trọng so với cách cũ là provider nhận ngữ cảnh ở cấp command, không chỉ ngữ cảnh của một option riêng lẻ. Vì thế, nó có thể xét những option đã nhập để đưa ra gợi ý phụ thuộc lẫn nhau.

## 2. Những thành phần chính của API

### 2.1. CompletionContext

`CompletionContext` mô tả vị trí và nội dung dòng lệnh tại thời điểm completion được yêu cầu. Trong Spring Shell 4.0.4, các thông tin hữu ích gồm:

| API | Ý nghĩa |
|---|---|
| `getCommand()` | Command hiện tại đang được hoàn thành |
| `getCommandOption()` | Option hiện tại liên quan đến vị trí completion, có thể là `null` |
| `getWords()` | Các token trong buffer, không bao gồm tên command |
| `getWordIndex()` | Chỉ số token đang đặt con trỏ |
| `getPosition()` | Vị trí con trỏ bên trong token hiện tại |
| `currentWord()` | Toàn bộ token tại vị trí con trỏ; `null` nếu con trỏ ở sau token cuối |
| `currentWordUpToCursor()` | Phần token từ đầu đến vị trí con trỏ |
| `upToCursor()` | Nội dung buffer tính đến vị trí con trỏ |
| `drop(n)` | Tạo ngữ cảnh mới sau khi bỏ `n` token đầu tiên |

`getWords()` đặc biệt hữu ích khi gợi ý phụ thuộc vào option khác. Ví dụ, provider có thể tìm `--warehouse HCM` hoặc `--warehouse=HCM` trong các token trước đó rồi dùng mã kho để truy vấn SKU phù hợp.

### 2.2. CompletionProposal

Mỗi `CompletionProposal` mô tả một đề xuất cho thao tác Tab. Constructor nhận chuỗi sẽ được chèn vào dòng lệnh:

```java
new CompletionProposal("--sku=SKU-123")
```

Có thể bổ sung metadata để người dùng hiểu lựa chọn:

```java
new CompletionProposal("--sku=SKU-123")
        .displayText("SKU-123")
        .description("Sản phẩm thuộc kho HCM")
        .category("Sản phẩm");
```

| Thuộc tính | Công dụng |
|---|---|
| `value` | Nội dung được chèn khi chọn đề xuất |
| `displayText` | Nhãn hiển thị trong danh sách gợi ý |
| `description` | Mô tả bổ sung cho đề xuất |
| `category` | Nhóm hiển thị của đề xuất |
| `complete` | Cho biết đề xuất có hoàn tất phần nhập hiện tại hay không |
| `dontQuote` | Điều khiển việc parser có cần quote giá trị đề xuất hay không |

Nếu giá trị có khoảng trắng hoặc ký tự đặc biệt, hãy để parser xử lý quy tắc quote phù hợp. Chỉ bật `dontQuote(true)` khi chắc chắn chuỗi đề xuất cần được chèn nguyên trạng.

## 3. Gắn provider vào command bằng annotation

Một command 4.x phải là phương thức trong bean do Spring quản lý, chẳng hạn lớp có `@Component`. `@Command` khai báo tên command và tên bean provider:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class StockCommands {

    private final InventoryService inventoryService;

    public StockCommands(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Command(
        name = "stock show",
        description = "Tra cứu tồn kho theo mã sản phẩm.",
        completionProvider = "stockCompletionProvider"
    )
    public String show(
            @Option(longName = "warehouse", defaultValue = "HN") String warehouse,
            @Option(longName = "sku") String sku) {
        return inventoryService.showStock(warehouse, sku);
    }
}
```

Provider được khai báo thành bean có tên `stockCompletionProvider`. Tên này phải khớp với giá trị `completionProvider` trong `@Command`.

## 4. Ví dụ thực tế: gợi ý SKU theo kho đã chọn

Giả sử ứng dụng có `InventoryCatalog` với phương thức `findSkuCodes(warehouse, prefix)`, trả về các mã SKU phù hợp với kho và phần đầu mã người dùng đang nhập.

Provider cần thực hiện ba việc:

1. Xác định option hiện đang được hoàn thành qua `CompletionContext.getCommandOption()`.
2. Nếu option hiện tại là `sku`, đọc giá trị `warehouse` đã nhập trước đó.
3. Truy vấn các SKU phù hợp và trả về `CompletionProposal`.

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Configuration
public class StockCompletionConfiguration {

    @Bean
    CompletionProvider stockCompletionProvider(InventoryCatalog inventoryCatalog) {
        return context -> {
            CommandOption currentOption = context.getCommandOption();

            if (currentOption == null || !"sku".equals(currentOption.longName())) {
                return List.of();
            }

            String selectedWarehouse = optionValue(
                    context.getWords(), "--warehouse");
            String warehouse = selectedWarehouse == null
                    ? "HN"
                    : selectedWarehouse;

            String prefix = currentValuePrefix(context, "--sku");

            return inventoryCatalog.findSkuCodes(warehouse, prefix).stream()
                    .map(sku -> new CompletionProposal("--sku=" + sku)
                            .displayText(sku)
                            .description("Sản phẩm thuộc kho " + warehouse)
                            .category("SKU"))
                    .toList();
        };
    }

    private static String optionValue(List<String> words, String optionName) {
        for (int i = 0; i < words.size(); i++) {
            String word = words.get(i);

            if (word.equals(optionName)
                    && i + 1 < words.size()
                    && !words.get(i + 1).startsWith("-")) {
                return words.get(i + 1);
            }

            String prefix = optionName + "=";
            if (word.startsWith(prefix)) {
                return word.substring(prefix.length());
            }
        }
        return null;
    }

    private static String currentValuePrefix(
            CompletionContext context, String optionName) {
        String current = context.currentWordUpToCursor();
        if (current == null) {
            return "";
        }

        String prefix = optionName + "=";
        if (current.equals(optionName)) {
            return "";
        }
        return current.startsWith(prefix)
                ? current.substring(prefix.length())
                : current;
    }
}
```

Giả sử dữ liệu kho như sau:

| Kho | SKU có sẵn |
|---|---|
| `HN` | `SKU-100`, `SKU-101`, `SKU-120` |
| `HCM` | `SKU-200`, `SKU-201`, `SKU-220` |
| `DN` | `SKU-300`, `SKU-310` |

Khi nhập:

```text
shell:>stock show --warehouse HCM --sku <Tab>
```

Provider đọc được `--warehouse HCM` từ `getWords()` và chỉ yêu cầu catalog trả SKU thuộc kho HCM. Các gợi ý có thể là:

```text
SKU-200    Sản phẩm thuộc kho HCM
SKU-201    Sản phẩm thuộc kho HCM
SKU-220    Sản phẩm thuộc kho HCM
```

Nếu người dùng bỏ qua `--warehouse`, ví dụ dùng giá trị mặc định `HN`, provider cũng dùng kho HN. Vì provider được gắn ở cấp command, cùng một hàm có thể xử lý completion cho nhiều option nếu cần.

`optionValue(...)` minh họa cách đọc cả hai dạng `--warehouse HCM` và `--warehouse=HCM`. Trong ứng dụng thực tế, cần tính đến alias của option, giá trị được quote và quy ước parser mà ứng dụng đang dùng. Nếu option có short name, hãy bổ sung nhận diện tên ngắn tương ứng.

## 5. Dùng CompletionProvider với enum và file

Spring Shell 4 cung cấp các provider dựng sẵn để tránh viết lại logic phổ biến.

### 5.1. EnumCompletionProvider

`EnumCompletionProvider` gợi ý các hằng enum. Có thể truyền prefix để tạo đề xuất theo dạng option `key=value`:

```java
public enum StockStatus {
    AVAILABLE,
    RESERVED,
    OUT_OF_STOCK
}

CompletionProvider statusProvider =
        new EnumCompletionProvider(StockStatus.class, "--status=");
```

### 5.2. FileNameCompletionProvider

`FileNameCompletionProvider` gợi ý tên file và thư mục cục bộ, có thể dùng đường dẫn tuyệt đối hoặc tương đối với working directory hiện tại:

```java
CompletionProvider fileProvider = new FileNameCompletionProvider();
```

Provider này phù hợp cho command nhận đường dẫn như `--file` hoặc `--output`.

### 5.3. DefaultCompletionProvider

`DefaultCompletionProvider` có từ Spring Shell 4.0.1. Nó hỗ trợ completion cho option kiểu enum và tạo prefix cho tên option dựa trên ngữ cảnh đầu vào hiện tại.

Nếu command có custom provider, có thể kết hợp provider mặc định với provider riêng để giữ các gợi ý enum và option tiêu chuẩn.

### 5.4. CompositeCompletionProvider

`CompositeCompletionProvider` kết hợp nhiều provider và gom các đề xuất từ chúng. Ví dụ:

```java
@Bean
CompletionProvider stockCompletionProvider(InventoryCatalog catalog) {
    CompletionProvider defaults = new DefaultCompletionProvider();
    CompletionProvider skuProvider = context -> {
        // Sinh gợi ý SKU theo kho và option hiện tại.
        return List.of(new CompletionProposal("--sku=SKU-100"));
    };

    return new CompositeCompletionProvider(defaults, skuProvider);
}
```

Trong ví dụ rút gọn này, provider mặc định xử lý gợi ý option và enum, còn provider riêng xử lý SKU. Với danh sách động, thay phần `List.of(...)` bằng kết quả truy vấn service như ví dụ ở phần trước.

## 6. CompletionProvider trong mô hình đăng ký bằng Java

Spring Shell 4 cho phép định nghĩa command bằng `Command.Builder`. Có thể gắn provider trực tiếp vào command bằng `.completionProvider(...)`:

```java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandOption;

@Bean
Command stockShowCommand(CompletionProvider stockCompletionProvider) {
    return Command.builder()
            .name("stock show")
            .description("Tra cứu tồn kho theo mã sản phẩm.")
            .options(
                    CommandOption.with()
                            .longName("warehouse")
                            .type(String.class)
                            .defaultValue("HN")
                            .build(),
                    CommandOption.with()
                            .longName("sku")
                            .type(String.class)
                            .build())
            .completionProvider(stockCompletionProvider)
            .execute(context -> "Đã tra cứu tồn kho.");
}
```

Trong ví dụ này, `CommandOption.with()` tạo metadata cho từng option, còn `.options(...)` gắn chúng vào command. Điểm đáng chú ý là completion provider được gắn trực tiếp vào đối tượng `Command`; không cần tra tên bean từ thuộc tính annotation.

## 7. Vì sao Spring Shell 4 chuyển completion lên cấp command?

Trong Spring Shell 3, completion giá trị option được định nghĩa riêng cho từng option. Legacy annotation model sử dụng `ValueProvider` trên `@ShellOption`; mô hình đăng ký bằng builder có thể khai báo completion trên từng `OptionSpec`.

Cách cũ hoạt động tốt với gợi ý độc lập, ví dụ `--status` gợi ý `AVAILABLE` hoặc `OUT_OF_STOCK`. Tuy nhiên, provider của option này không dễ dùng thông tin option khác để quyết định danh sách gợi ý. Nếu có nhiều option phụ thuộc nhau, ứng dụng có thể phải tạo nhiều provider và lặp logic.

Spring Shell 4 tập trung completion vào command:

| Nội dung | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|
| Phạm vi provider | Thường gắn với từng option | Gắn ở cấp command |
| Ngữ cảnh | Ngữ cảnh completion của option | Ngữ cảnh command, option và các token hiện có |
| Gợi ý phụ thuộc option khác | Khó thực hiện do provider tách riêng | Có thể đọc `getWords()` và xét option khác |
| Annotation | `ValueProvider` và `@ShellOption(valueProvider = ...)` trong legacy model | `@Command(completionProvider = "...")` |
| Programmatic | Completion có thể gắn lên option registration | `.completionProvider(...)` trên `Command.Builder` |
| `@OptionValues` | Có thể xuất hiện trong API cũ/new model tùy phiên bản | Đã bị loại bỏ trong 4.x |

Thay đổi này cũng có nghĩa provider phải tự phân nhánh theo `context.getCommandOption()` khi một command có nhiều loại giá trị cần hoàn thành.

## 8. Dùng context để tạo gợi ý phụ thuộc lẫn nhau

Một provider ở cấp command có thể xử lý nhiều trường hợp trong cùng một hàm:

```java
@Bean
CompletionProvider orderCompletionProvider(OrderCatalog catalog) {
    return context -> {
        CommandOption option = context.getCommandOption();
        if (option == null || option.longName() == null) {
            return List.of();
        }

        return switch (option.longName()) {
            case "customer" -> catalog.findCustomerNames().stream()
                    .map(name -> new CompletionProposal("--customer=" + name))
                    .toList();
            case "order" -> {
                String customer = optionValue(context.getWords(), "--customer");
                yield catalog.findOrdersFor(customer).stream()
                        .map(id -> new CompletionProposal("--order=" + id))
                        .toList();
            }
            default -> List.of();
        };
    };
}
```

Khi đang hoàn thành `--customer`, provider gợi ý khách hàng. Khi đang hoàn thành `--order`, provider đọc `--customer` đã nhập và chỉ gợi ý đơn hàng của khách hàng đó. Đây là ví dụ điển hình cho lợi ích của command-level completion.

Trong ứng dụng thực tế, cần xử lý trường hợp `customer` chưa được nhập, bị bỏ qua hoặc không hợp lệ. Provider nên trả danh sách rỗng hoặc danh sách gợi ý chung khi chưa đủ ngữ cảnh, thay vì ném exception làm gián đoạn thao tác Tab.

## 9. Những lưu ý khi triển khai

**Chỉ chạy completion ở ngữ cảnh tương tác phù hợp.** Tài liệu Spring Shell mô tả thao tác Tab trong shell dựa trên JLine. `SystemShellRunner` sử dụng Java Console tiêu chuẩn và không có các tính năng nâng cao như history, Tab completion và rich text. Nếu cần trải nghiệm completion đầy đủ trong Spring Shell 4, hãy sử dụng JLine shell runner và dependency `spring-shell-jline`.

**Giữ provider nhanh.** Completion được gọi trong lúc người dùng gõ. Tránh truy vấn hàng nghìn bản ghi, gọi dịch vụ mạng chậm hoặc thực hiện tác vụ đồng bộ dài. Nên lọc theo prefix, giới hạn số kết quả và dùng truy vấn chỉ lấy các trường cần hiển thị.

**Không coi completion là validation.** Một giá trị xuất hiện trong danh sách gợi ý vẫn có thể đã hết hiệu lực khi command chạy. Parser và service phải xác minh lại đầu vào; completion chỉ giúp người dùng khám phá giá trị.

**Không lộ dữ liệu nhạy cảm.** Provider chỉ nên gợi ý dữ liệu mà người dùng hiện tại được phép nhìn thấy. Nếu danh sách SKU, khách hàng hoặc tài nguyên phụ thuộc quyền, hãy áp dụng cùng phạm vi phân quyền trong truy vấn completion.

**Trả về giá trị có thể được parser chèn đúng.** Dùng `CompletionProposal.value(...)` cho nội dung cần chèn, `displayText(...)` cho nhãn thân thiện và `description(...)` cho giải thích. Với chuỗi có khoảng trắng, hãy kiểm tra quote/escape trên parser đang dùng.

**Xử lý ngữ cảnh chưa hoàn chỉnh.** Người dùng có thể nhấn Tab sau một option chưa có giá trị, ở giữa token hoặc sau khi nhập một phần tên option. Kiểm tra `getCommandOption()`, `currentWord()` và `currentWordUpToCursor()` trước khi truy cập dữ liệu.

**Tránh trả đề xuất trùng.** Khi ghép nhiều provider bằng `CompositeCompletionProvider`, bảo đảm các nguồn không tạo quá nhiều đề xuất trùng hoặc gây nhiễu.

## 10. Kiểm thử CompletionProvider

Provider có thể được kiểm thử như một hàm Java thông thường: tạo `CompletionContext`, gọi `apply(context)` và xác minh danh sách `CompletionProposal`. Các trường hợp nên kiểm tra gồm:

1. Đang hoàn thành option `sku` với kho HN: chỉ có SKU của HN.
2. Đang hoàn thành option `sku` với kho HCM: chỉ có SKU của HCM.
3. Không có `--warehouse`: dùng giá trị mặc định hoặc gợi ý chung theo thiết kế.
4. Đang hoàn thành option khác `sku`: provider SKU không trả đề xuất.
5. Prefix không khớp SKU nào: trả danh sách rỗng.
6. Ngữ cảnh chưa hoàn chỉnh hoặc `getCommandOption()` là `null`: không phát sinh exception.
7. Người dùng không có quyền xem một số SKU: provider không đưa các mã đó vào danh sách.

Ví dụ kiểm thử logic đọc option:

```java
@Test
void readsWarehouseInSeparatedOptionForm() {
    List<String> words = List.of("--warehouse", "HCM", "--sku", "SKU-");

    String warehouse = optionValue(words, "--warehouse");

    assertThat(warehouse).isEqualTo("HCM");
}

@Test
void readsWarehouseInEqualsForm() {
    List<String> words = List.of("--warehouse=HN", "--sku=SKU-");

    String warehouse = optionValue(words, "--warehouse");

    assertThat(warehouse).isEqualTo("HN");
}
```

Ngoài unit test, nên kiểm tra trực tiếp bằng JLine shell: nhập command, nhấn Tab ở từng vị trí, quan sát giá trị được chèn và thử cả option đã nhập trước đó. Unit test provider không chứng minh parser và terminal đang hiển thị completion đúng như mong muốn.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có gợi ý khi nhấn Tab | Đang dùng runner không hỗ trợ completion nâng cao hoặc chưa bật JLine | Dùng JLine-based shell runner và dependency phù hợp |
| Provider không được gọi | Tên bean trong `completionProvider` không khớp hoặc bean chưa được đăng ký | Kiểm tra bean name và Spring component/configuration scan |
| Chỉ có gợi ý cho một option | Provider chưa kiểm tra `context.getCommandOption()` hoặc trả rỗng cho option khác | Phân nhánh theo option hiện tại trong provider cấp command |
| Không lọc theo kho đã chọn | Provider chỉ đọc option hiện tại, không xem `getWords()` | Đọc option đã nhập trước đó và truyền ngữ cảnh vào truy vấn |
| Gợi ý bị chèn sai định dạng | `CompletionProposal.value()` không khớp cú pháp option của command | Trả về dạng proposal theo cú pháp `--option=value` hoặc dạng mà parser đang yêu cầu |
| Tab làm shell chậm | Provider gọi truy vấn hoặc dịch vụ tốn thời gian | Lọc theo prefix, giới hạn kết quả, tối ưu truy vấn và cache có kiểm soát |
| Gợi ý chứa dữ liệu người dùng không được xem | Provider không áp dụng quyền truy cập | Lọc dữ liệu theo cùng security context với command |
| Gợi ý từ enum biến mất sau khi thêm custom provider | Custom provider không kết hợp provider mặc định | Dùng `CompositeCompletionProvider` với `DefaultCompletionProvider` hoặc `EnumCompletionProvider` |
| Code cũ dùng `@OptionValues` không biên dịch | Annotation đã bị loại bỏ trong Spring Shell 4 | Chuyển logic sang command-level `CompletionProvider` |

## 12. Quy trình chuyển từ 3.x sang 4.x

Khi nâng cấp ứng dụng, hãy rà soát từng command có completion tùy chỉnh:

1. Tìm `ValueProvider`, `valueProvider` trong `@ShellOption`, `@OptionValues` và completion gắn trực tiếp vào option builder.
2. Gom logic liên quan đến cùng một command vào một `CompletionProvider`.
3. Dùng `CompletionContext.getCommandOption()` để xác định option đang được hoàn thành.
4. Dùng `getWords()` và các phương thức về cursor để đọc những option đã nhập và phần văn bản hiện tại.
5. Trả về `CompletionProposal` với nội dung chèn đúng cú pháp command 4.x.
6. Đăng ký provider thành Spring bean và đặt tên bean trong `@Command(completionProvider = "...")`.
7. Nếu command khai báo bằng Java, gắn provider qua `Command.Builder.completionProvider(...)`.
8. Kết hợp provider dựng sẵn nếu vẫn cần completion cho enum, option và file.
9. Chạy unit test provider và thử thao tác Tab trong JLine shell.

Không chuyển nguyên `ValueProvider` của 3.x sang 4.x bằng cách đổi package. Mô hình 4.x dùng interface, context và phạm vi provider khác; cần thiết kế lại cách phân nhánh và tạo đề xuất.

## 13. Tổng kết

Spring Shell 4 đưa completion về phạm vi command thông qua `CompletionProvider`. Provider nhận `CompletionContext`, xác định command/option hiện tại, đọc các token đã nhập và trả về `CompletionProposal`. Thiết kế này cho phép gợi ý phụ thuộc lẫn nhau giữa các option, chẳng hạn SKU được lọc theo kho đã chọn.

Gắn provider vào `@Command` bằng tên bean hoặc vào `Command.Builder` bằng `.completionProvider(...)`. Dùng `DefaultCompletionProvider`, `EnumCompletionProvider`, `FileNameCompletionProvider` và `CompositeCompletionProvider` khi phù hợp. Giữ provider nhanh, tôn trọng quyền truy cập và luôn kiểm tra lại đầu vào khi command thực thi. Để sử dụng Tab completion, cần chạy shell tương tác dựa trên JLine.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html) — cách đăng ký provider bằng bean, annotation và `Command.Builder`.
- [CompletionProvider API 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html) — hợp đồng `Function<CompletionContext, List<CompletionProposal>>`.
- [CompletionContext API 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionContext.html) — command, option, words và vị trí con trỏ.
- [CompletionProposal API 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProposal.html) — giá trị, nhãn hiển thị, mô tả, category và quote behavior.
- [EnumCompletionProvider API 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/EnumCompletionProvider.html) — completion cho enum và prefix option.
- [Command.Builder API 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.Builder.html) — gắn provider và option vào command programmatic.
- [CommandOption.Builder API 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.Builder.html) — mô tả tên, kiểu, default và tính bắt buộc của option.
- [CompositeCompletionProvider API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompositeCompletionProvider.html) — kết hợp nhiều provider.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — lý do chuyển từ completion riêng từng option sang command-level completion và việc loại bỏ `@OptionValues`.
