# Giữ tên, tùy chọn và kiểu kết quả ổn định cho bên gọi script

## 1. Command là một hợp đồng công khai

Một command có thể được gọi trực tiếp bởi người vận hành, nhưng cũng có thể trở thành một phần của script, pipeline CI/CD hoặc một công cụ tự động hóa khác. Khi một script đã gọi `inventory show --sku=SKU-001`, tên command, tên option, cách hiểu giá trị và định dạng kết quả đều trở thành giao diện mà bên gọi phụ thuộc vào.

Vì vậy, thiết kế CLI cần xem xét cả người dùng tương tác lẫn chương trình gọi tự động. Một hợp đồng command ổn định gồm năm phần:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Tên command | Bên gọi phải nhập từ nào và cấu trúc command có ổn định không? |
| Đầu vào | Option, argument, kiểu dữ liệu, giá trị mặc định và quy tắc validation là gì? |
| Kết quả | Thành công trả về định dạng nào, có schema và kiểu dữ liệu ra sao? |
| Trạng thái | Script nhận biết thành công, lỗi đầu vào và lỗi nghiệp vụ bằng cách nào? |
| Tương thích | Khi cần thay đổi, bên gọi cũ có tiếp tục hoạt động được không? |

Spring Shell cung cấp cơ chế khai báo command, phân tích option/argument, chuyển đổi kiểu, trợ giúp và xử lý trạng thái. Ứng dụng vẫn cần quyết định phần nào của hành vi được cam kết ổn định qua các phiên bản.

## 2. Đặt tên command có cấu trúc và có thể duy trì

Nên chọn tên command mô tả rõ đối tượng và hành động. Một quy ước thường dễ mở rộng là **danh từ trước, động từ sau**:

~~~text
inventory list
inventory show
inventory create
inventory update
inventory delete
~~~

Các command liên quan có thể được đặt trong cùng một nhóm trợ giúp:

~~~java
@Component
class InventoryCommands {

    @Command(
            name = "inventory show",
            description = "Hiển thị thông tin sản phẩm",
            group = "Inventory")
    public String show(/* options */) {
        // Xử lý command
        return "...";
    }
}
~~~

Trong Spring Shell 4.x, tên command có thể khai báo tường minh qua thuộc tính `name` của `@Command`. Hãy khai báo rõ tên thay vì phụ thuộc vào tên phương thức Java được suy ra tự động. Tên phương thức có thể thay đổi khi refactor nội bộ, trong khi tên command là một phần giao diện mà script đang sử dụng.

Một số nguyên tắc đặt tên:

- Dùng cùng một cấu trúc cho các command cùng loại, ví dụ `user list`, `user show`, `user disable`.
- Dùng từ đầy đủ, dễ hiểu; tránh viết tắt tùy tiện hoặc tên gần giống nhau như `update` và `upgrade` nếu hai thao tác dễ bị nhầm.
- Không đổi ý nghĩa của command đã phát hành. Nếu cần hành vi mới, cân nhắc thêm command mới.
- Khai báo alias tường minh khi cần duy trì tên cũ trong giai đoạn chuyển đổi. Không dựa vào việc tự động chấp nhận mọi tiền tố viết tắt.
- Ghi rõ command nào dành cho người dùng tương tác và command nào có thể gọi từ script nếu hai cách dùng có yêu cầu khác nhau.

Ví dụ giữ alias cho tên cũ trong lúc chuyển đổi:

~~~java
@Command(
        name = "inventory show",
        alias = {"product show"},
        description = "Hiển thị thông tin sản phẩm",
        group = "Inventory",
        help = "Dùng inventory show --sku=<mã-sản-phẩm> để xem chi tiết.")
public String show(/* options */) {
    return "...";
}
~~~

Alias `product show` vẫn gọi cùng command. Hãy thông báo tên mới trong trợ giúp và tài liệu, sau đó lên kế hoạch loại bỏ alias theo chính sách tương thích đã công bố. Không nên xóa alias ngay trong một bản phát hành nhỏ nếu script của người dùng vẫn có thể phụ thuộc vào nó.

## 3. Ưu tiên option có tên rõ ràng

Spring Shell phân biệt **option** và **argument**:

- Option là dữ liệu có tên, ví dụ `--sku=SKU-001` hoặc `--format=json`.
- Argument là dữ liệu theo vị trí, ví dụ `inventory show SKU-001`.

Option có tên thường phù hợp hơn cho script vì cú pháp thể hiện rõ ý nghĩa của từng giá trị. Nếu thêm một tham số mới, script hiện tại ít bị ảnh hưởng hơn so với việc thay đổi thứ tự các argument.

Ví dụ khai báo command với option:

~~~java
@Command(name = "inventory show", description = "Hiển thị thông tin sản phẩm")
public String show(
        @Option(longName = "sku", required = true,
                description = "Mã sản phẩm cần xem") String sku,
        @Option(longName = "format", defaultValue = "plain",
                description = "Định dạng kết quả: plain hoặc json") String format) {
    // Xử lý dữ liệu
    return "...";
}
~~~

Người gọi có thể truyền option theo hai dạng:

~~~text
inventory show --sku=SKU-001 --format=json
inventory show --sku SKU-001 --format json
~~~

Spring Shell 4.x cũng cho phép option và argument xuất hiện theo thứ tự khác nhau. Tuy nhiên, hãy chọn một kiểu viết thống nhất trong tài liệu và script mẫu để mọi người dễ đọc.

Giá trị có khoảng trắng cần được đặt trong dấu nháy, ví dụ `--name="Lan Nguyen"`. Với option boolean, cú pháp Spring Shell yêu cầu truyền giá trị tường minh để parser phân biệt option với argument, ví dụ `--enabled=true` hoặc `--enabled=false`; không giả định rằng chỉ cần viết `--enabled` là đủ. Các tên ngắn không thể ghép thành một nhóm như `-abc`, vì vậy script nên gọi từng option theo cú pháp đã công bố.

### Khi nào dùng argument?

Argument phù hợp với một giá trị chính, luôn có cùng vị trí và khó gây nhầm lẫn, chẳng hạn đường dẫn tệp hoặc mã đối tượng trong một lệnh đơn giản. Với command có nhiều tham số, hãy ưu tiên option có tên.

Nếu dùng argument, khai báo rõ chỉ số và mô tả:

~~~java
@Command(name = "inventory show")
public String show(
        @Argument(index = 0, description = "Mã sản phẩm") String sku) {
    return "Đang xem " + sku;
}
~~~

Không đổi thứ tự hoặc ý nghĩa của argument đã phát hành. Nếu cần thêm đầu vào mới, thêm option có tên thường ít rủi ro hơn việc chèn một argument vào giữa danh sách vị trí.

## 4. Giữ tên option, kiểu và giá trị mặc định nhất quán

Tên option là một phần của giao diện script. Hãy chọn tên dài có ý nghĩa, dùng cùng một tên cho cùng một khái niệm trong toàn ứng dụng và chỉ thêm tên ngắn khi nó thực sự thuận tiện cho người dùng tương tác.

| Quy ước | Ví dụ |
|---|---|
| Mã định danh | `--sku`, `--user-id`, `--order-id` |
| Định dạng kết quả | `--format=plain`, `--format=json` |
| Phân trang | `--limit=50`, `--offset=0` |
| Lọc dữ liệu | `--status=active`, `--from=2026-01-01` |
| Hành vi an toàn | `--dry-run=true`, `--force=true` |

Không dùng cùng một option name cho các kiểu dữ liệu hoặc ý nghĩa khác nhau giữa những command tương tự. Ví dụ, `--limit` nên luôn biểu thị số lượng bản ghi tối đa, không nên là thời gian chờ ở command khác.

### Kiểu dữ liệu và quy tắc chuyển đổi

Chọn kiểu Java phù hợp với miền giá trị:

- `String` cho mã, tên, đường dẫn hoặc nội dung văn bản.
- `int` hoặc `long` cho số đếm và giới hạn có miền giá trị nguyên.
- `BigDecimal` cho giá trị tiền tệ hoặc số thập phân cần độ chính xác.
- `LocalDate` cho ngày lịch không có múi giờ.
- `Instant` cho thời điểm tuyệt đối.
- Enum hoặc một tập giá trị đã kiểm soát cho trạng thái có miền giá trị hữu hạn.

Không thay đổi kiểu hoặc cách diễn giải option đã phát hành một cách âm thầm. Chẳng hạn, nếu `--limit` trước đây nhận số nguyên, không chuyển nó thành chuỗi có cú pháp khác mà không có giai đoạn chuyển đổi. Hãy quy định rõ định dạng ngày, múi giờ, đơn vị đo và miền giá trị hợp lệ.

### Giá trị mặc định là hành vi công khai

Giá trị mặc định ảnh hưởng trực tiếp đến kết quả của script bỏ qua option. Nếu thay `--format` mặc định từ `plain` sang `json`, script cũ có thể nhận đầu ra khác dù không sửa câu lệnh. Vì vậy:

- Chọn giá trị mặc định có ý nghĩa và ghi trong help.
- Không thay đổi mặc định của option đã phát hành trong bản cập nhật tương thích nếu thay đổi đó ảnh hưởng đến output hoặc trạng thái.
- Nếu cần hành vi mới, thêm option hoặc command mới, hoặc yêu cầu bên gọi chọn giá trị tường minh.
- Với option có tác động lớn, tránh mặc định khiến thao tác phá hủy dữ liệu hoặc thay đổi hệ thống.

## 5. Ví dụ: command có đầu vào và output ổn định

Ví dụ dưới đây định nghĩa một hợp đồng đơn giản cho `inventory show`. Bên gọi luôn truyền mã sản phẩm bằng `--sku`; định dạng mặc định là `plain`, còn script có thể yêu cầu JSON bằng `--format=json`.

~~~java
import com.fasterxml.jackson.annotation.JsonPropertyOrder;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Locale;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class InventoryCommands {

    private final ProductService productService;
    private final ObjectMapper objectMapper;

    InventoryCommands(ProductService productService, ObjectMapper objectMapper) {
        this.productService = productService;
        this.objectMapper = objectMapper;
    }

    @Command(
            name = "inventory show",
            description = "Hiển thị thông tin sản phẩm",
            group = "Inventory",
            help = "Ví dụ: inventory show --sku=SKU-001 --format=json")
    public String show(
            @Option(longName = "sku", required = true,
                    description = "Mã sản phẩm") String sku,
            @Option(longName = "format", defaultValue = "plain",
                    description = "Định dạng kết quả: plain hoặc json") String format)
            throws JsonProcessingException {

        if (sku == null || !sku.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("--sku phải gồm chữ in hoa, số hoặc dấu gạch ngang");
        }

        Product product = productService.findBySku(sku);
        ProductOutput output = new ProductOutput(
                1,
                product.sku(),
                product.name(),
                product.availableQuantity());

        return switch (format.toLowerCase(Locale.ROOT)) {
            case "plain" -> "SKU: " + output.sku()
                    + "\nTên: " + output.name()
                    + "\nSố lượng khả dụng: " + output.availableQuantity();
            case "json" -> objectMapper.writeValueAsString(output);
            default -> throw new IllegalArgumentException(
                    "--format chỉ nhận plain hoặc json");
        };
    }
}

@JsonPropertyOrder({"schemaVersion", "sku", "name", "availableQuantity"})
record ProductOutput(
        int schemaVersion,
        String sku,
        String name,
        int availableQuantity) {
}
~~~

Các điểm đáng chú ý:

1. `name = "inventory show"` cố định tên command, không phụ thuộc tên phương thức Java.
2. `--sku` là option bắt buộc và có kiểm tra định dạng trước khi gọi service.
3. `--format` có giá trị mặc định `plain`; miền giá trị được giới hạn thành `plain` hoặc `json`.
4. Kết quả JSON dùng DTO riêng, có tên field và thứ tự field được công bố.
5. `schemaVersion` cho phép bên gọi nhận biết phiên bản cấu trúc output khi hợp đồng dữ liệu cần tiến hóa.

Trong ứng dụng thật, cần định nghĩa rõ định dạng mã sản phẩm theo nghiệp vụ. Biểu thức kiểm tra trong ví dụ chỉ là quy ước minh họa, không phải quy tắc chung cho mọi hệ thống.

Ví dụ cần Jackson trên classpath để Spring Boot cung cấp `ObjectMapper`. `Product`, `ProductService` và `ProductNotFoundException` là các kiểu miền nghiệp vụ của ứng dụng mẫu, cần được định nghĩa trong project thực tế.

## 6. Định nghĩa output cho con người và cho máy

Output mặc định thường phục vụ người vận hành. Script cần một định dạng có thể phân tích ổn định. Có thể cung cấp hai chế độ rõ ràng:

| Chế độ | Mục đích | Đặc điểm |
|---|---|---|
| `plain` | Người dùng đọc trực tiếp | Có nhãn, xuống dòng và cách trình bày dễ hiểu. |
| `json` | Script hoặc hệ thống khác xử lý | Có cấu trúc, tên field và kiểu dữ liệu rõ ràng. |

Ví dụ gọi từ terminal:

~~~powershell
java -jar inventory-cli.jar inventory show --sku=SKU-001 --format=plain
java -jar inventory-cli.jar inventory show --sku=SKU-001 --format=json
~~~

Output plain:

~~~text
SKU: SKU-001
Tên: Bàn phím cơ
Số lượng khả dụng: 18
~~~

Output JSON:

~~~json
{"schemaVersion":1,"sku":"SKU-001","name":"Bàn phím cơ","availableQuantity":18}
~~~

Khi đã công bố JSON cho script, hãy coi tên field, kiểu dữ liệu, ý nghĩa null, đơn vị và cách biểu diễn thời gian là hợp đồng. Không đổi `availableQuantity` từ số nguyên sang chuỗi chỉ để dễ trình bày. Không đổi `sku` thành `productCode` mà không có kế hoạch tương thích.

### Không trộn dữ liệu với thông báo tiến trình

Nếu stdout chứa JSON, một banner khởi động, dòng tiến trình hoặc thông báo debug xen giữa sẽ khiến script không thể phân tích kết quả. Hãy giữ luồng dữ liệu chính chỉ chứa payload đã cam kết. Chuyển log và thông báo chẩn đoán sang cơ chế logging hoặc luồng lỗi riêng theo cấu hình ứng dụng.

Với kết quả dài, hãy cân nhắc định dạng JSON Lines (mỗi dòng một JSON object) nếu script cần xử lý theo luồng. Chỉ chọn JSON Lines khi đây là định dạng được công bố rõ ràng; không tự ý chuyển từ một JSON object sang nhiều dòng sau khi bên gọi đã phụ thuộc vào cấu trúc cũ.

Không dùng `toString()` mặc định của entity hoặc record làm định dạng máy đọc. Hãy tạo DTO output riêng để tránh việc thêm field nội bộ hoặc thay đổi cách triển khai Java vô tình làm thay đổi dữ liệu script nhận được.

## 7. Thiết kế mã thoát cho script

Nội dung hiển thị cho biết điều gì đã xảy ra; mã thoát cho biết tiến trình thành công hay thất bại. Script thường dựa vào mã thoát để quyết định có chạy bước tiếp theo hay dừng pipeline.

Trong Spring Shell 4.x, `Command.execute(CommandContext)` trả về `ExitStatus`. `ExitStatus` có mã và mô tả, với các trạng thái có sẵn như `OK`, `USAGE_ERROR`, `EXECUTION_ERROR` và `AVAILABILITY_ERROR`. Khi chạy non-interactive, shell runner sử dụng trạng thái thực thi để xác định mã kết thúc của tiến trình.

Một quy ước mã thoát dành cho ứng dụng có thể như sau:

| Mã | Ý nghĩa | Hành động của script |
|---:|---|---|
| `0` | Thành công | Tiếp tục bước tiếp theo. |
| `1` | Lỗi thực thi không dự kiến | Dừng pipeline và ghi log. |
| `2` | Cú pháp hoặc dữ liệu đầu vào không hợp lệ | Báo lỗi cấu hình hoặc yêu cầu sửa tham số. |
| `4` | Không tìm thấy tài nguyên theo yêu cầu | Xử lý nhánh nghiệp vụ tương ứng. |

Đây là ví dụ quy ước của ứng dụng; các mã `1`, `2` và `4` là chính sách do ứng dụng chọn, không phải lời khẳng định rằng mọi cấu hình Spring Shell đều dùng cùng bảng mã mặc định. Hãy công bố bảng mã thực tế và giữ ổn định qua các lần phát hành. Tránh dùng mã khác nhau cho cùng một loại lỗi ở các command tương tự.

Có thể dùng `ExitStatusExceptionMapper` để chuyển ngoại lệ thành trạng thái phù hợp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class CliExitConfiguration {

    @Bean
    ExitStatusExceptionMapper cliExitStatusMapper() {
        return exception -> {
            if (exception instanceof IllegalArgumentException) {
                return new ExitStatus(2, "Dữ liệu đầu vào không hợp lệ");
            }
            if (exception instanceof ProductNotFoundException) {
                return new ExitStatus(4, "Không tìm thấy sản phẩm");
            }
            return new ExitStatus(1, "Lỗi thực thi command");
        };
    }
}
~~~

Gắn mapper vào command bằng tên bean:

~~~java
@Command(
        name = "inventory show",
        description = "Hiển thị thông tin sản phẩm",
        exitStatusExceptionMapper = "cliExitStatusMapper")
public String show(/* options */) {
    // Tìm sản phẩm và tạo output
    return "...";
}
~~~

Đừng bắt mọi ngoại lệ rồi trả `ExitStatus.OK`. Làm như vậy khiến pipeline nghĩ rằng command thành công dù nghiệp vụ thất bại. Hãy phân biệt lỗi đầu vào, lỗi nghiệp vụ dự kiến và lỗi hạ tầng; ghi log đủ để chẩn đoán nhưng không đưa stack trace hoặc thông tin bí mật vào payload thường.

## 8. Chạy theo cách có thể tự động hóa

Spring Shell hỗ trợ interactive và non-interactive mode. Với Spring Shell 4.x, interactive mode được bật mặc định kể cả khi tiến trình nhận tham số dòng lệnh. Để chạy một command từ tham số tiến trình, đặt:

~~~properties
spring.shell.interactive.enabled=false
~~~

Có thể cấu hình trong `application.properties`, sau đó gọi:

~~~powershell
java -jar inventory-cli.jar inventory show --sku=SKU-001 --format=json
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
~~~

Ví dụ Bash:

~~~bash
java -jar inventory-cli.jar inventory show --sku=SKU-001 --format=json
status=$?
if [ "$status" -ne 0 ]; then
    exit "$status"
fi
~~~

Đối với script, command cần nhận đủ dữ liệu qua option/argument, cấu hình hoặc input được định nghĩa rõ ràng. Không yêu cầu người dùng trả lời prompt tương tác giữa pipeline. Nếu thiếu dữ liệu bắt buộc, trả lỗi có ý nghĩa và hướng dẫn cách truyền option tương ứng.

## 9. Thay đổi hợp đồng mà không làm hỏng script

Khi một CLI được sử dụng trong môi trường tự động hóa, thay đổi nhỏ cũng có thể làm hỏng một quy trình ở nơi bạn không kiểm soát. Hãy áp dụng các nguyên tắc sau:

- **Ưu tiên thay đổi bổ sung:** thêm option mới có giá trị mặc định hợp lý hoặc thêm command mới trước khi loại bỏ giao diện cũ.
- **Không tái sử dụng tên option:** nếu `--status` đã có nghĩa là trạng thái sản phẩm, không đổi nó thành trạng thái đồng bộ.
- **Không đổi ý nghĩa mặc định âm thầm:** thay đổi mặc định có thể làm script chạy ra kết quả khác dù dòng lệnh không thay đổi.
- **Duy trì alias có thời hạn:** khi đổi tên command, giữ alias cũ, thông báo tên mới trong help và tài liệu, sau đó loại bỏ theo mốc phiên bản đã công bố.
- **Phiên bản hóa schema output:** thêm field theo hướng tương thích khi có thể; nếu thay đổi cấu trúc không tương thích, cung cấp schema version hoặc format version mới.
- **Công bố mã thoát:** không thay mã của lỗi hiện có sang một ý nghĩa khác.
- **Kiểm thử script mẫu:** lưu các ví dụ gọi CLI như một phần của tài liệu hoặc bộ kiểm thử tích hợp để phát hiện thay đổi hợp đồng.

Nếu cần thay đổi không tương thích, hãy thông báo trước, nêu rõ cách chuyển đổi và cho người dùng thời gian cập nhật script. Có thể hỗ trợ song song command hoặc schema cũ và mới trong một giai đoạn.

## 10. Kiểm thử hợp đồng command

Kiểm thử cần xác nhận cả cú pháp và dữ liệu mà script thực sự nhận được. Với Spring Shell, có thể dùng `@ShellTest`, `ShellTestClient` và `ShellAssertions` để gửi command và kiểm tra nội dung output.

Một bộ kiểm thử hợp đồng nên bao gồm:

1. **Tên command:** tên chính được đăng ký; alias cũ vẫn hoạt động trong giai đoạn hỗ trợ.
2. **Option bắt buộc:** thiếu `--sku` phải tạo lỗi sử dụng có thể nhận biết.
3. **Kiểu và validation:** mã không đúng định dạng hoặc `--limit` ngoài miền cho phép phải bị từ chối.
4. **Giá trị mặc định:** gọi không truyền `--format` phải cho kết quả đúng theo mặc định đã công bố.
5. **Output plain:** nhãn và thứ tự trường phù hợp với giao diện dành cho người dùng.
6. **Output JSON:** parse được bằng JSON parser; field, kiểu dữ liệu và `schemaVersion` khớp hợp đồng.
7. **Exit code:** thành công trả mã `0`; lỗi đầu vào và lỗi nghiệp vụ trả đúng mã đã công bố ở non-interactive mode.
8. **Không có output phụ:** payload JSON không bị trộn với banner, prompt hoặc thông báo tiến trình.

Ví dụ kiểm tra cấu trúc JSON bằng Jackson:

~~~java
JsonNode json = objectMapper.readTree(output);

assertThat(json.path("schemaVersion").asInt()).isEqualTo(1);
assertThat(json.path("sku").asText()).isEqualTo("SKU-001");
assertThat(json.path("availableQuantity").isInt()).isTrue();
~~~

Không chỉ so sánh một chuỗi JSON đầy đủ nếu thứ tự field không phải cam kết của schema. Hãy parse JSON rồi kiểm tra tên field, kiểu và giá trị. Nếu thứ tự field có ý nghĩa với một giao thức riêng, phải ghi rõ và kiểm thử điều đó.

## 11. Danh sách kiểm tra trước khi phát hành CLI

Trước khi công bố một command cho script sử dụng, hãy xác nhận:

- Tên command được khai báo tường minh và không phụ thuộc tên phương thức Java.
- Tên option dài, kiểu dữ liệu, giá trị mặc định và quy tắc validation được ghi trong help.
- Argument theo vị trí được giữ tối thiểu và không đổi thứ tự sau khi phát hành.
- Alias cũ và chính sách deprecation được công bố khi đổi tên.
- Định dạng plain/JSON được chọn rõ ràng; JSON có DTO và schema version.
- Mã thoát phản ánh đúng kết quả thực thi và ổn định cho bên gọi.
- Chế độ non-interactive không chờ prompt và không trộn dữ liệu với thông báo tiến trình.
- Kiểm thử bao phủ cú pháp, output, lỗi và mã thoát.

## Kết luận

Một command dùng trong script cần được thiết kế như giao diện công khai. Tên command, option, kiểu dữ liệu, giá trị mặc định, định dạng output và mã thoát đều ảnh hưởng đến bên gọi. Hãy đặt tên rõ ràng, ưu tiên option có tên, cung cấp output máy đọc với schema được kiểm soát, ánh xạ lỗi sang mã thoát ổn định và duy trì tương thích khi thay đổi. Những quy tắc này giúp CLI của Spring Shell hoạt động đáng tin cậy trong terminal, script và pipeline tự động hóa.

## Tài liệu tham khảo

- [Spring Shell 4.x – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.x – Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [Spring Shell 4.x – Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html)
- [Spring Shell 4.x – Execution and Non-interactive Mode](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.x – Exception Handling and Exit Status](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.x API – Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html)
- [Spring Shell 4.x API – ExitStatus](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html)
- [Command Line Interface Guidelines](https://clig.dev/)
