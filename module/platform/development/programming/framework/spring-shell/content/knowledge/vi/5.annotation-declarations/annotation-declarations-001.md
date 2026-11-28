# Khai báo legacy 3.x bằng @ShellComponent, @ShellMethod và @ShellOption

Spring Shell 3.x có mô hình khai báo command cũ được tài liệu gọi là *legacy annotation model*. Mô hình này dùng ba annotation quen thuộc: `@ShellComponent` để đánh dấu lớp chứa command, `@ShellMethod` để biến phương thức thành command và `@ShellOption` để mô tả cách tham số nhận dữ liệu từ dòng lệnh.

Mô hình này hữu ích khi đọc, duy trì hoặc nâng cấp một ứng dụng Spring Shell 3.x đang dùng các annotation quen thuộc. Trong Spring Shell 3.1, tài liệu phân biệt rõ legacy annotation model với annotation model mới dựa trên `@Command`; phần này tập trung vào legacy model và cách dùng đúng ba annotation chính. Ví dụ sử dụng API Spring Shell 3.1.3, Spring Boot 3.1.x, Spring Framework 6 và JDK 17. Hãy đối chiếu phiên bản patch thực tế của dự án trước khi sao chép mã.

## 1. Vai trò của ba annotation

| Annotation | Đặt ở đâu | Vai trò |
|---|---|---|
| `@ShellComponent` | Trên lớp | Đánh dấu bean có thể chứa các phương thức command để Spring Shell xem xét |
| `@ShellMethod` | Trên phương thức | Đăng ký phương thức thành command, khai báo mô tả, tên gọi, alias và nhóm |
| `@ShellOption` | Trên tham số phương thức | Khai báo tên option, bí danh ngắn, giá trị mặc định, số token được nhận và nguồn gợi ý hoàn thành |

Luồng đăng ký có thể hiểu theo thứ tự: Spring tạo bean từ lớp `@ShellComponent`; Spring Shell tìm các phương thức `@ShellMethod` trên bean đó; sau đó thông tin `@ShellOption` được dùng để tạo quy tắc phân tích và chuyển đổi tham số. Khi người dùng chạy command, Spring Shell phân tích dòng lệnh, chuyển giá trị sang kiểu Java, thực hiện validation rồi gọi phương thức tương ứng.

## 2. Chuẩn bị dependency và package

Ví dụ dưới đây lấy Spring Shell 3.1.3 làm mốc tham chiếu. Dự án dùng Spring Boot 3.1.x và JDK 17. Có thể khai báo starter cùng BOM để các artifact Spring Shell dùng cùng một phiên bản.

**Maven**

```xml
<properties>
    <spring-shell.version>3.1.3</spring-shell.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.shell</groupId>
            <artifactId>spring-shell-dependencies</artifactId>
            <version>${spring-shell.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`spring-shell-starter` cung cấp tích hợp Spring Shell với ứng dụng Spring Boot. `spring-boot-starter-validation` bổ sung implementation Bean Validation để các ràng buộc như `@NotBlank` và `@Min` được thực thi. Nếu ứng dụng không dùng validation annotation thì dependency validation có thể không cần thiết.

Các annotation legacy nằm trong package `org.springframework.shell.standard`:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;
```

`Availability` là kiểu thuộc package `org.springframework.shell`. Khi cần hoàn thành giá trị option, các kiểu `ValueProvider` và `CompletionContext` cũng thuộc API Spring Shell 3.x; ví dụ cụ thể sẽ xuất hiện ở phần tự hoàn thành.

## 3. Đánh dấu lớp command bằng @ShellComponent

`@ShellComponent` đánh dấu một lớp có thể chứa các phương thức command. Đây là stereotype annotation được meta-annotate bằng `@Component`, do đó lớp cũng là một Spring bean và tham gia cơ chế component scanning thông thường.

```java
package com.example.inventory.shell;

import org.springframework.shell.standard.ShellComponent;

@ShellComponent
public class InventoryCommands {
    // Các phương thức @ShellMethod được khai báo ở đây.
}
```

Spring Shell dùng `@ShellComponent` để giới hạn những bean nào được xem xét khi tìm command. Lớp phải nằm trong vùng package được Spring Boot component scan, hoặc được đăng ký bằng cấu hình Spring phù hợp. Chỉ thêm annotation nhưng đặt lớp ngoài vùng scan thì bean có thể không được tạo và command sẽ không xuất hiện.

Thuộc tính `value` của `@ShellComponent` dùng để đặt tên bean Spring. Nó không phải tên command. Tên command được xác định ở phương thức bằng `@ShellMethod`.

Không cần đặt thêm `@Component` trên cùng lớp chỉ để biến nó thành bean, vì `@ShellComponent` đã bao gồm vai trò stereotype đó.

## 4. Đăng ký phương thức bằng @ShellMethod

Một phương thức trở thành command khi nằm trong lớp `@ShellComponent` và được đánh dấu bằng `@ShellMethod`.

```java
@ShellComponent
public class GreetingCommands {

    @ShellMethod("Hiển thị lời chào.")
    public String sayHello() {
        return "Xin chào từ Spring Shell!";
    }
}
```

Nếu không khai báo `key`, Spring Shell suy ra tên command từ tên phương thức. Tên camelCase được chuyển thành dạng kebab-case: `sayHello()` trở thành `say-hello`. Người dùng có thể gọi:

```text
shell:>say-hello
Xin chào từ Spring Shell!
```

### 4.1. Khai báo tên command và alias

Thuộc tính `key` cho phép đặt tên command rõ ràng, độc lập với tên phương thức. Có thể khai báo nhiều key để tạo alias cho cùng một hành động.

```java
@ShellMethod(
    value = "Tra cứu tồn kho theo mã sản phẩm.",
    key = { "stock show", "stock detail" }
)
public String showStock() {
    return "Thông tin tồn kho";
}
```

Hai cách gọi sau cùng chạy một phương thức:

```text
shell:>stock show
Thông tin tồn kho

shell:>stock detail
Thông tin tồn kho
```

`key` có thể chứa nhiều từ, do đó có thể tổ chức command theo dạng `stock show`, `stock adjust` hoặc `user create`. Nên thống nhất quy ước đặt tên trong toàn ứng dụng để người dùng dễ đoán command.

### 4.2. Viết mô tả command

Thuộc tính `value` của `@ShellMethod` là mô tả ngắn về chức năng. Nội dung này được hiển thị trong trợ giúp tích hợp. Nên viết một hoặc hai câu, bắt đầu bằng chữ hoa và kết thúc bằng dấu chấm.

```java
@ShellMethod(
    value = "Tạo một bản ghi sản phẩm mới.",
    key = "product create"
)
public String createProduct() {
    return "Đã tạo sản phẩm.";
}
```

`value` là phần mô tả, còn `key` là tên dùng để gọi command. Không nên nhầm hai thuộc tính này.

### 4.3. Gom nhóm command

Khi ứng dụng có nhiều command, có thể gom chúng thành nhóm để kết quả `help` dễ đọc hơn. Mặc định, Spring Shell suy ra nhóm từ tên lớp command. Có thể ghi đè nhóm bằng thuộc tính `group` của `@ShellMethod`, hoặc dùng `@ShellCommandGroup` trên lớp hay package.

```java
import org.springframework.shell.standard.ShellCommandGroup;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
@ShellCommandGroup("Quản lý kho")
public class InventoryCommands {

    @ShellMethod(value = "Tra cứu tồn kho.", key = "stock show")
    public String showStock() {
        return "Tồn kho hiện tại";
    }

    @ShellMethod(
        value = "Điều chỉnh số lượng tồn kho.",
        key = "stock adjust",
        group = "Thao tác tồn kho"
    )
    public String adjustStock() {
        return "Đã điều chỉnh tồn kho";
    }
}
```

Nhóm chỉ ảnh hưởng cách trình bày danh sách trợ giúp. `group` không tạo prefix cho tên command và không thay đổi cách phân tích đầu vào.

## 5. Ánh xạ tham số và @ShellOption

Với legacy annotation model, tham số của phương thức command được tự động ánh xạ thành option theo tên tham số. Ví dụ:

```java
@ShellMethod("Tìm sản phẩm theo mã.")
public String findProduct(String sku) {
    return "Sản phẩm: " + sku;
}
```

Tham số `sku` có thể được truyền như option `--sku`:

```text
shell:>find-product --sku SKU-123
Sản phẩm: SKU-123
```

Khi muốn đổi tên option hoặc khai báo alias, đặt `@ShellOption` trực tiếp trên tham số.

```java
@ShellMethod(value = "Tìm sản phẩm theo mã.", key = "product find")
public String findProduct(
        @ShellOption(value = "--sku") String productCode) {
    return "Sản phẩm: " + productCode;
}
```

Mặc dù tên biến Java là `productCode`, người dùng truyền `--sku`. Nếu giá trị trong `@ShellOption` không có tiền tố `-` hoặc `--`, tiền tố sẽ được lấy từ thuộc tính `prefix` của `@ShellMethod`.

### 5.1. Option dài và bí danh ngắn

Có thể khai báo nhiều tên cho cùng một tham số. Cách thường dùng là một tên dài dễ đọc và một bí danh ngắn theo quy ước POSIX.

```java
@ShellMethod(value = "Hiển thị thông tin sản phẩm.", key = "product show")
public String showProduct(
        @ShellOption(value = { "--sku", "-s" }) String sku) {
    return "Sản phẩm: " + sku;
}
```

Hai lệnh sau tương đương:

```text
shell:>product show --sku SKU-123
shell:>product show -s SKU-123
```

Với boolean flag, kiểu `boolean` hoặc `Boolean` thường được dùng để biểu diễn trạng thái bật/tắt. Cần chọn kiểu và giá trị mặc định có chủ ý để phân biệt trường hợp người dùng bỏ qua option với trường hợp truyền `true` hoặc `false`.

### 5.2. Giá trị bắt buộc và giá trị tùy chọn

Một option không khai báo giá trị mặc định thường được xem là bắt buộc. Nếu muốn cho phép người dùng bỏ qua option, có thể dùng hằng `ShellOption.NULL` làm `defaultValue`.

```java
@ShellMethod(value = "Tìm sản phẩm.", key = "product search")
public String search(
        @ShellOption(value = "--keyword") String keyword,
        @ShellOption(value = "--category", defaultValue = ShellOption.NULL)
        String category) {
    return "Từ khóa=" + keyword + ", danh mục=" + category;
}
```

Trong ví dụ này, `--keyword` là bắt buộc, còn `--category` có thể bỏ qua. Nếu bỏ qua, giá trị của `category` là `null`.

### 5.3. Đặt giá trị mặc định

Nếu một option có giá trị mặc định, người dùng có thể bỏ qua nó trong lệnh. Giá trị mặc định được khai báo dưới dạng chuỗi và Spring Shell chuyển đổi sang kiểu tham số đích.

```java
@ShellMethod(value = "Liệt kê sản phẩm.", key = "product list")
public String listProducts(
        @ShellOption(value = "--limit", defaultValue = "20") int limit,
        @ShellOption(value = "--sort", defaultValue = "name") String sort) {
    return "limit=" + limit + ", sort=" + sort;
}
```

Khi chạy `product list`, phương thức nhận `limit = 20` và `sort = "name"`. Người dùng có thể ghi đè bằng `product list --limit 50 --sort createdAt`.

Giá trị mặc định nên hợp lệ với kiểu Java và quy tắc nghiệp vụ. Không nên dùng một chuỗi mặc định có thể khiến thao tác ghi dữ liệu hoặc xóa dữ liệu diễn ra ngoài ý muốn.

### 5.4. Số lượng token của option

Thuộc tính `arity` của `@ShellOption` điều khiển số token mà parser nhận cho một option. Điều này hữu ích khi option nhận mảng hoặc một giá trị có thể bao gồm nhiều token.

```java
@ShellMethod(value = "Ghi nhận nhiều nhãn.", key = "product tag")
public String addTags(
        @ShellOption(value = "--tags", arity = 2) String[] tags) {
    return "Nhãn: " + String.join(", ", tags);
}
```

Ví dụ trên yêu cầu hai giá trị cho `--tags`:

```text
shell:>product tag --tags new sale
Nhãn: new, sale
```

Legacy annotation model có giới hạn về cấu hình arity so với annotation model mới và đăng ký command bằng `CommandRegistration`; tài liệu 3.1.3 nêu rõ legacy model không hỗ trợ khai báo cận dưới của arity. Nếu cần quy tắc số lượng đầu vào phức tạp, hãy cân nhắc mô hình đăng ký mới thay vì cố ép mọi trường hợp vào `@ShellOption`.

## 6. Chuyển đổi kiểu dữ liệu và validation

Giá trị người dùng nhập ban đầu là văn bản. Spring Shell sử dụng cơ chế chuyển đổi kiểu của Spring để đưa giá trị vào tham số Java. Những kiểu thường gặp gồm `String`, kiểu số nguyên, số thực, boolean, enum và mảng các kiểu được hỗ trợ.

```java
public enum StockStatus {
    AVAILABLE,
    OUT_OF_STOCK,
    DISCONTINUED
}

@ShellMethod(value = "Lọc sản phẩm theo trạng thái.", key = "product by-status")
public String findByStatus(
        @ShellOption(value = "--status") StockStatus status,
        @ShellOption(value = "--min-stock", defaultValue = "0") int minStock) {
    return "status=" + status + ", minStock=" + minStock;
}
```

Người dùng có thể nhập:

```text
shell:>product by-status --status AVAILABLE --min-stock 5
```

Với enum, giá trị nhập phải khớp với một hằng enum; Spring Shell 3.1.x hỗ trợ chuyển đổi không phân biệt chữ hoa/chữ thường theo cấu hình mặc định được tài liệu mô tả. Nếu giá trị không chuyển đổi được, command không được gọi và shell trả lỗi phân tích/chuyển đổi.

### 6.1. Validation bằng Bean Validation

Chuyển đổi kiểu chỉ kiểm tra giá trị có thể chuyển thành kiểu Java hay không. Nó không thay thế kiểm tra quy tắc nghiệp vụ. Có thể dùng các annotation Bean Validation trên tham số hoặc phương thức để xác thực đầu vào trước khi gọi thân phương thức.

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class StockCommands {

    @ShellMethod(value = "Điều chỉnh tồn kho.", key = "stock adjust")
    public String adjust(
            @ShellOption(value = "--sku") @NotBlank String sku,
            @ShellOption(value = "--quantity") @Min(1) int quantity) {
        return "Đã nhận yêu cầu điều chỉnh " + quantity + " đơn vị cho " + sku;
    }
}
```

Với `@NotBlank`, mã sản phẩm không được rỗng hoặc chỉ chứa khoảng trắng. Với `@Min(1)`, số lượng phải lớn hơn hoặc bằng một. Nếu người dùng truyền `--quantity 0`, Spring Shell hiển thị thông báo constraint không thỏa mãn và không gọi phương thức command.

Các ràng buộc quan trọng của miền nghiệp vụ vẫn nên được kiểm tra trong service/use case. Validation tham số giúp phản hồi sớm và tạo thông báo dễ hiểu; nó không thay thế kiểm tra tồn kho thực tế, quyền truy cập hay tính nhất quán dữ liệu.

## 7. Điều khiển khả dụng của command

Một command có thể được đăng ký nhưng chỉ có ý nghĩa khi ứng dụng đang ở một trạng thái nhất định. Ví dụ, command tải báo cáo chỉ khả dụng sau khi kết nối máy chủ. Legacy model hỗ trợ kiểm tra này bằng phương thức trả về `Availability`.

Nếu đặt tên phương thức theo quy ước `<tênPhươngThứcCommand>Availability`, Spring Shell tự tìm phương thức đó. Có thể dùng `@ShellMethodAvailability` để chỉ rõ tên phương thức kiểm tra.

```java
import org.springframework.shell.Availability;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellMethodAvailability;

@ShellComponent
public class RemoteCommands {

    private boolean connected;

    @ShellMethod(value = "Kết nối máy chủ từ xa.", key = "remote connect")
    public String connect() {
        connected = true;
        return "Đã kết nối.";
    }

    @ShellMethod(value = "Tải dữ liệu từ máy chủ.", key = "remote download")
    @ShellMethodAvailability("downloadAvailability")
    public String download() {
        return "Đã tải dữ liệu.";
    }

    public Availability downloadAvailability() {
        return connected
                ? Availability.available()
                : Availability.unavailable("bạn chưa kết nối máy chủ");
    }
}
```

Trước khi chạy `remote connect`, lệnh `remote download` tồn tại nhưng chưa khả dụng. Spring Shell hiển thị lý do khi người dùng thử chạy lệnh. Phần lý do nên viết tiếp nối tự nhiên sau cụm “because”, không viết hoa đầu câu và không thêm dấu chấm cuối câu theo hướng dẫn của framework.

Có thể dùng `@ShellMethodAvailability` trên phương thức kiểm tra để điều khiển nhiều command cùng lúc. Nếu không ghi rõ tên phương thức kiểm tra trên command, quy ước tên `<method>Availability` là cách đơn giản cho từng command.

## 8. Tự hoàn thành giá trị bằng ValueProvider

Trong phiên shell tương tác, người dùng có thể nhấn Tab để nhận gợi ý cho tên option hoặc giá trị option. Với legacy annotation model, có thể cung cấp gợi ý giá trị bằng cách triển khai `ValueProvider` và tham chiếu lớp đó trong `@ShellOption`.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;
import org.springframework.stereotype.Component;

@Component
public class WarehouseValueProvider implements ValueProvider {

    @Override
    public List<CompletionProposal> complete(CompletionContext context) {
        return Stream.of("HN", "HCM", "DN")
                .map(CompletionProposal::new)
                .collect(Collectors.toList());
    }
}
```

Khai báo provider trên tham số command:

```java
@ShellComponent
public class WarehouseCommands {

    @ShellMethod(value = "Tra cứu kho.", key = "warehouse show")
    public String show(
            @ShellOption(value = "--code", valueProvider = WarehouseValueProvider.class)
            String warehouseCode) {
        return "Kho: " + warehouseCode;
    }
}
```

`ValueProvider` phải được đăng ký thành Spring bean. Khi người dùng bắt đầu nhập giá trị cho `--code` rồi nhấn Tab, provider trả về danh sách `CompletionProposal` để shell hiển thị gợi ý. Có thể thay danh sách tĩnh bằng truy vấn danh sách kho từ service, nhưng nên giữ việc hoàn thành đủ nhanh để thao tác terminal không bị chậm.

Tự hoàn thành trong shell tương tác và hoàn thành ở command line của hệ điều hành là hai ngữ cảnh khác nhau. `ValueProvider` hỗ trợ gợi ý giá trị trong shell đang chạy; hoàn thành command line bên ngoài cần tích hợp với shell hệ điều hành theo cơ chế tương ứng.

## 9. Ví dụ tổng hợp: command quản lý tồn kho

Ví dụ sau kết hợp `@ShellComponent`, `@ShellMethod`, `@ShellOption`, nhóm command, alias, giá trị mặc định, validation và trạng thái khả dụng. Phần thân phương thức minh họa cách nhận và phản hồi dữ liệu; trong ứng dụng thật, hãy gọi service nghiệp vụ để đọc hoặc cập nhật dữ liệu.

```java
package com.example.inventory.shell;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.shell.Availability;
import org.springframework.shell.standard.ShellCommandGroup;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellMethodAvailability;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
@ShellCommandGroup("Quản lý kho")
public class InventoryCommands {

    private boolean inventoryReady = true;

    @ShellMethod(
        value = "Tra cứu tồn kho theo mã sản phẩm.",
        key = { "stock show", "stock detail" }
    )
    public String show(
            @ShellOption(value = "--sku") @NotBlank String sku,
            @ShellOption(value = { "--warehouse", "-w" }, defaultValue = "HN")
            String warehouse) {
        return "SKU=" + sku + ", warehouse=" + warehouse;
    }

    @ShellMethod(
        value = "Điều chỉnh số lượng tồn kho.",
        key = "stock adjust"
    )
    @ShellMethodAvailability("adjustAvailability")
    public String adjust(
            @ShellOption(value = "--sku") @NotBlank String sku,
            @ShellOption(value = { "--quantity", "-q" }) @Min(1) int quantity,
            @ShellOption(value = "--reason", defaultValue = "Điều chỉnh thủ công")
            String reason,
            @ShellOption(value = "--dry-run", defaultValue = "false") boolean dryRun) {

        if (dryRun) {
            return "Mô phỏng điều chỉnh " + quantity + " cho " + sku
                    + "; lý do: " + reason;
        }

        // Thay phần minh họa này bằng lời gọi InventoryService trong ứng dụng thật.
        return "Đã ghi nhận điều chỉnh " + quantity + " cho " + sku
                + "; lý do: " + reason;
    }

    public Availability adjustAvailability() {
        return inventoryReady
                ? Availability.available()
                : Availability.unavailable("dịch vụ tồn kho đang bảo trì");
    }
}
```

Các lệnh mẫu:

```text
shell:>stock show --sku SKU-123
SKU=SKU-123, warehouse=HN

shell:>stock detail --sku SKU-123 --warehouse HCM
SKU=SKU-123, warehouse=HCM

shell:>stock adjust --sku SKU-123 --quantity 5 --reason "Nhập bổ sung"
Đã ghi nhận điều chỉnh 5 cho SKU-123; lý do: Nhập bổ sung

shell:>stock adjust --sku SKU-123 -q 5 --dry-run true
Mô phỏng điều chỉnh 5 cho SKU-123; lý do: Điều chỉnh thủ công
```

Lệnh `stock show` và `stock detail` là hai alias của cùng một phương thức. Nếu không truyền `--warehouse`, giá trị `HN` được sử dụng. Với `stock adjust`, `--sku` và `--quantity` phải hợp lệ; `--reason` và `--dry-run` có giá trị mặc định. Trước khi phương thức chạy, Spring Shell kiểm tra trạng thái khả dụng qua `adjustAvailability`.

## 10. Kiểm tra command đã được đăng ký đúng

Sau khi khởi động ứng dụng, dùng `help` để xác nhận command có xuất hiện và mô tả được hiển thị. Dùng `help <command>` để xem chi tiết tên, synopsis, option, kiểu dữ liệu và trạng thái bắt buộc.

```text
shell:>help
shell:>help stock show
shell:>help stock adjust
```

Nên kiểm tra tối thiểu các trường hợp sau:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Chạy command với đầy đủ option hợp lệ | Phương thức command được gọi và trả kết quả |
| Bỏ qua option bắt buộc | Shell báo thiếu option và không gọi phương thức |
| Bỏ qua option có default value | Phương thức nhận giá trị mặc định |
| Truyền option qua alias ngắn | Giá trị được bind vào đúng tham số |
| Truyền giá trị không chuyển đổi được | Shell báo lỗi chuyển đổi trước khi gọi command |
| Vi phạm `@NotBlank` hoặc `@Min` | Shell báo constraint không thỏa mãn |
| Command chưa khả dụng | Shell giải thích lý do command chưa thể chạy |
| Nhấn Tab ở option có `ValueProvider` | Shell đưa ra các gợi ý phù hợp |

Có thể kiểm thử lớp command bằng Spring Boot test và kiểm tra output/side effect của service. Với kiểm thử tích hợp khởi tạo toàn bộ Spring Shell, cần cấu hình chế độ chạy phù hợp để REPL không chờ nhập liệu trong test tự động.

## 11. Giới hạn và ranh giới phiên bản

Legacy annotation model thuận tiện cho command đơn giản và codebase Spring Shell 3.x hiện hữu, nhưng không có đầy đủ khả năng của mô hình annotation mới hoặc đăng ký command bằng `CommandRegistration`. Tài liệu 3.1.3 nêu một số giới hạn cụ thể: legacy annotation không hỗ trợ đặt label riêng cho option và không hỗ trợ khai báo cận dưới của arity. Khi yêu cầu command phức tạp hơn, cần đánh giá mô hình mới thay vì cố mở rộng annotation cũ.

Từ Spring Shell 3.1.x, tài liệu có cả hai mô hình annotation: legacy model dựa trên `@ShellMethod`/`@ShellOption` và mô hình mới dựa trên `@Command`/`@Option`. Chúng là hai cách khai báo khác nhau, có tên thuộc tính và cơ chế đăng ký riêng. Không trộn annotation của hai mô hình trong cùng một command.

Các annotation legacy được giữ để tương thích trong nhánh 3.x và đã bị loại bỏ trong Spring Shell 4. Nếu đang chuẩn bị nâng lên 4.x, cần chuyển sang `@Command`, `@Option`, `@Argument` và package tương ứng của `spring-shell-core`; thay đổi này không chỉ là sửa import.

## 12. Tổng kết

Trong legacy annotation model của Spring Shell 3.x, `@ShellComponent` xác định lớp command được Spring quản lý, `@ShellMethod` khai báo phương thức có thể gọi từ shell, còn `@ShellOption` kiểm soát cách tham số nhận giá trị. Ba annotation phối hợp với cơ chế chuyển đổi kiểu, Bean Validation, trợ giúp, kiểm tra khả dụng và tự hoàn thành để tạo một giao diện CLI dễ sử dụng.

Khi viết command, hãy đặt tên và mô tả rõ ràng, dùng alias có chủ đích, khai báo mặc định cho option tùy chọn, kiểm tra dữ liệu trước khi thay đổi trạng thái và giữ nghiệp vụ trong service. Khi đọc hoặc nâng cấp code, luôn xác nhận dự án đang dùng đúng Spring Shell 3.x và phân biệt legacy model với mô hình `@Command` được giới thiệu từ 3.1.

## Tài liệu tham khảo

- [Spring Shell 3.1.3 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — mục 4.1.3 Legacy Annotation, 4.2 Organizing Commands, 4.3 Dynamic Command Availability, chương 5 Options, 6 Completion.
- [Spring Shell 3.1.x API: org.springframework.shell.standard](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/package-summary.html) — danh sách `ShellComponent`, `ShellMethod`, `ShellOption`, `ShellMethodAvailability`, `ShellCommandGroup` và `ValueProvider`.
- [Spring Shell 3.1.x API: ValueProvider](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ValueProvider.html) — hợp đồng cung cấp gợi ý hoàn thành cho tham số.
- [Spring Shell 4.x Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — ranh giới tương thích và việc loại bỏ legacy annotations khi nâng cấp lên 4.x.
