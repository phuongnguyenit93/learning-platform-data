# Viết kiểm thử cho cùng hợp đồng lệnh trên mô hình đang sử dụng

Một command Spring Shell có thể chạy đúng khi gọi trực tiếp method Java nhưng vẫn sai khi người dùng nhập lệnh. Parser có thể bind nhầm option, dùng default value không như dự kiến, chuyển kiểu thất bại hoặc hiển thị thông báo không đúng. Vì vậy, kiểm thử command cần xác nhận hợp đồng mà người dùng thực sự nhìn thấy.

Hợp đồng đó gồm tên command, argument/option, giá trị mặc định, kiểu dữ liệu, validation, help, output, lỗi và cách command kết thúc. Bài này xây dựng một bộ kiểm thử cho lệnh tìm mặt hàng theo SKU, dùng Spring Shell 3.3.4 làm ví dụ chính. Cùng cách kiểm thử ở cấp shell có thể áp dụng khi dự án đăng ký command bằng annotation model hoặc programmatic model.

## 1. Kiểm thử hợp đồng lệnh thay vì chỉ kiểm thử method

Giả sử ứng dụng cung cấp command:

~~~text
inventory find --sku SKU-42 --limit 5
~~~

Người dùng quan tâm đến các hành vi sau:

| Thành phần hợp đồng | Điều cần xác nhận |
|---|---|
| Tên command | `inventory find` được đăng ký và gọi được |
| Option bắt buộc | `--sku` phải có giá trị |
| Chuyển kiểu | `--limit` được chuyển thành số nguyên |
| Giá trị mặc định | Bỏ `--limit` thì hệ thống dùng `10` |
| Validation | SKU đúng định dạng và limit nằm trong khoảng cho phép |
| Kết quả | Output có SKU và giới hạn đã áp dụng |
| Lỗi | Input sai tạo thông báo ổn định, dễ hiểu |
| Help | Người dùng xem được mô tả và option |
| Tương tác | Prompt hoặc dữ liệu được hỏi thêm hoạt động đúng nếu command cần |
| Exit status | Tiến trình trả mã thoát đã quy định khi chạy non-interactive |

Kiểm thử trực tiếp method chỉ xác nhận logic Java. Nó không đi qua parser, converter, command registry hoặc result handler của Spring Shell. Một bộ contract test cần gửi nguyên chuỗi lệnh như người dùng nhập.

## 2. Chọn đúng mô hình command của dự án

Spring Shell hỗ trợ hai cách đăng ký command:

- **Annotation model:** phương thức trong component được đánh dấu bằng annotation.
- **Programmatic model:** command được tạo và đăng ký dưới dạng bean hoặc registration.

Trong Spring Shell 3.3.x, annotation model thường dùng `@ShellComponent`, `@ShellMethod`, `@ShellOption`. Programmatic model dùng `CommandRegistration` bean. Spring Shell 4.x chuyển annotation sang `@Command`, `@Option`, `@Argument`, đồng thời có thể đăng ký bean `Command`.

Không cần đổi mô hình command chỉ để kiểm thử. `ShellTestClient` gửi chuỗi lệnh qua parser và registry của ứng dụng; do đó, test có thể xác nhận cùng một hợp đồng CLI dù command được đăng ký bằng annotation hay programmatic model.

Trong các ví dụ chính bên dưới, command dùng annotation model của Spring Shell 3.3.4. Nếu dự án đang dùng `CommandRegistration`, giữ nguyên các chuỗi lệnh và assertion; thay phần cấu hình context để import registration bean của dự án.

## 3. Chuẩn bị test dependencies

Với Spring Shell 3.3.4, test support được chia thành hai module:

- `spring-shell-test`: các API kiểm thử như `ShellTestClient`, `ShellScreen`, `ShellAssertions`.
- `spring-shell-test-autoconfigure`: annotation `@ShellTest` và auto-configuration cho test.

Thêm các dependency sau vào Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-test-autoconfigure</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu dự án dùng Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework.shell:spring-shell-test")
    testImplementation("org.springframework.shell:spring-shell-test-autoconfigure")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Dùng Spring Shell BOM hoặc dependency management đã có trong dự án để các module test cùng version với runtime. Không tự đặt một version khác cho `spring-shell-test`.

## 4. Tạo command mẫu có hợp đồng rõ ràng

Ví dụ dưới đây dùng annotation model Spring Shell 3.3.x. Command nhận SKU bắt buộc và limit có giá trị mặc định:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class InventoryCommands {

    private final InventoryQueryService queryService;

    public InventoryCommands(InventoryQueryService queryService) {
        this.queryService = queryService;
    }

    @ShellMethod(
            key = "inventory find",
            value = "Tìm mặt hàng theo mã SKU.")
    public String find(
            @ShellOption(value = "--sku", help = "Mã SKU cần tìm")
            String sku,
            @ShellOption(
                    value = "--limit",
                    defaultValue = "10",
                    help = "Số kết quả tối đa")
            int limit) {
        try {
            return queryService.find(sku, limit);
        }
        catch (InvalidInventoryQueryException ex) {
            return "ERROR: " + ex.getMessage();
        }
    }
}
~~~

Service giữ validation nghiệp vụ:

~~~java
import org.springframework.stereotype.Service;

@Service
public class InventoryQueryService {

    public String find(String sku, int limit) {
        if (sku == null || !sku.matches("SKU-[A-Z0-9]{2,8}")) {
            throw new InvalidInventoryQueryException(
                    "SKU phải có dạng SKU- theo sau bởi 2 đến 8 chữ hoặc số.");
        }
        if (limit < 1 || limit > 50) {
            throw new InvalidInventoryQueryException(
                    "limit phải nằm trong khoảng từ 1 đến 50.");
        }

        return "sku=%s; limit=%d; status=ACTIVE".formatted(sku, limit);
    }
}
~~~

Exception nghiệp vụ:

~~~java
public class InvalidInventoryQueryException extends RuntimeException {

    public InvalidInventoryQueryException(String message) {
        super(message);
    }
}
~~~

Hợp đồng hiển thị của ví dụ:

~~~text
shell:>inventory find --sku SKU-42
sku=SKU-42; limit=10; status=ACTIVE

shell:>inventory find --sku SKU-42 --limit 5
sku=SKU-42; limit=5; status=ACTIVE

shell:>inventory find --sku bad
ERROR: SKU phải có dạng SKU- theo sau bởi 2 đến 8 chữ hoặc số.
~~~

Command chuyển exception nghiệp vụ thành thông báo dành cho người dùng. Với ứng dụng automation cần mã thoát khác 0 khi lỗi, hãy xác định thêm hợp đồng exit status trong runner/command model và kiểm thử ở cấp tiến trình; một chuỗi `ERROR` trong output không tự động có nghĩa tiến trình đã trả mã lỗi.

## 5. Dùng @ShellTest và ShellTestClient

`@ShellTest` tạo test context tập trung vào các thành phần shell. `ShellTestClient` mô phỏng người dùng gửi command và nhận màn hình output.

Tạo cấu hình test chỉ import các bean cần cho command:

~~~java
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Import;

@SpringBootConfiguration
@EnableAutoConfiguration
@Import({
        InventoryCommands.class,
        InventoryQueryService.class
})
class InventoryShellTestApplication {
}
~~~

Test contract:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = InventoryShellTestApplication.class)
class InventoryCommandContractTests {

    @Autowired
    ShellTestClient client;

    @Test
    void usesDefaultLimitWhenOptionIsOmitted() {
        var session = client
                .nonInterative("inventory find --sku SKU-42")
                .run();

        ShellAssertions.assertThat(session.screen())
                .containsText("sku=SKU-42; limit=10; status=ACTIVE");
    }

    @Test
    void bindsExplicitLimit() {
        var session = client
                .nonInterative(
                        "inventory find --sku SKU-42 --limit 5")
                .run();

        ShellAssertions.assertThat(session.screen())
                .containsText("sku=SKU-42; limit=5; status=ACTIVE");
    }

    @Test
    void mapsDomainValidationErrorToCliMessage() {
        var session = client
                .nonInterative("inventory find --sku bad")
                .run();

        ShellAssertions.assertThat(session.screen())
                .containsText("ERROR: SKU phải có dạng SKU-");
    }

    @Test
    void helpDescribesTheCommand() {
        var session = client
                .nonInterative("help inventory find")
                .run();

        ShellAssertions.assertThat(session.screen())
                .containsText("Tìm mặt hàng theo mã SKU");
    }
}
~~~

Trong API Spring Shell 3.3.x, tên method non-interactive là `nonInterative(...)` (thiếu chữ “t” trong “Interactive”). Đây là spelling của API phiên bản này. `run()` thực thi phiên, còn `screen()` trả về nội dung hiển thị để assertion.

Nếu dự án đã có một cấu hình ứng dụng kiểm thử, dùng cấu hình đó thay cho `InventoryShellTestApplication`. Chỉ import command, service và dependency cần thiết; không khởi động toàn bộ hạ tầng production trong test contract nếu không cần.

## 6. Kiểm thử validation ở hai lớp

Validation có thể xảy ra ở parser và ở nghiệp vụ:

| Lớp | Ví dụ | Điều cần kiểm thử |
|---|---|---|
| Parser/binding | `--limit abc` không chuyển được sang `int` | Lệnh bị từ chối trước khi gọi nghiệp vụ |
| Required option | Thiếu `--sku` | Người dùng nhận thông báo thiếu đầu vào |
| Domain validation | SKU sai định dạng | Thông báo lỗi nghiệp vụ ổn định |
| Range validation | `--limit 0` hoặc `--limit 51` | Giá trị ngoài miền bị từ chối |

Test trực tiếp service giúp xác nhận quy tắc nghiệp vụ:

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class InventoryQueryServiceTests {

    private final InventoryQueryService service =
            new InventoryQueryService();

    @Test
    void rejectsSkuWithInvalidFormat() {
        assertThatThrownBy(() -> service.find("bad", 10))
                .isInstanceOf(InvalidInventoryQueryException.class)
                .hasMessageContaining("SKU phải có dạng SKU-");
    }

    @Test
    void rejectsLimitOutsideAllowedRange() {
        assertThatThrownBy(() -> service.find("SKU-42", 0))
                .isInstanceOf(InvalidInventoryQueryException.class)
                .hasMessageContaining("limit");
    }
}
~~~

Shell contract test kiểm tra thông báo đã được command chuyển thành output. Hai lớp test trả lời hai câu hỏi khác nhau: service có áp dụng quy tắc đúng không, và người dùng có nhận được thông báo đúng không.

Với lỗi chuyển kiểu hoặc thiếu option, hãy kiểm tra kết quả parser bằng `ShellTestClient` và ghi nhận thông báo công khai của ứng dụng. Tránh phụ thuộc vào toàn bộ exception text nội bộ của Spring, vì câu chữ có thể thay đổi giữa các phiên bản. Nếu ứng dụng có exception handler riêng, hãy kiểm tra chính thông báo handler cam kết với người dùng.

## 7. Kiểm thử help và tên option như một phần của API

Help là một phần của hợp đồng CLI. Khi đổi tên command, option hoặc mô tả, người dùng script và tài liệu vận hành có thể bị ảnh hưởng.

Các điểm cần xác nhận:

- Command xuất hiện dưới đúng tên.
- Mô tả ngắn giải thích đúng tác dụng.
- Required option được nhận diện là bắt buộc.
- Default value được mô tả chính xác.
- Tên option và alias không bị thay đổi ngoài dự kiến.
- Ví dụ cú pháp trong help phù hợp với command thật.

Có thể dùng lệnh help trong `ShellTestClient`:

~~~java
@Test
void helpListsThePublicOptions() {
    var session = client
            .nonInterative("help inventory find")
            .run();

    var screen = session.screen();
    ShellAssertions.assertThat(screen)
            .containsText("inventory find")
            .containsText("--sku")
            .containsText("--limit");
}
~~~

Không nên so sánh toàn bộ help output thành một chuỗi dài nếu có thể tránh. Khoảng trắng, thứ tự option hoặc cách căn cột có thể thay đổi theo chiều rộng terminal và phiên bản. Hãy kiểm tra những phần thực sự thuộc hợp đồng.

## 8. Kiểm thử command khi đăng ký bằng programmatic model

Nếu dự án Spring Shell 3.3.x dùng `CommandRegistration` bean, command vẫn xuất hiện trong `CommandRegistry`. Bộ test ở cấp shell không cần biết command được tạo từ `@ShellMethod` hay `CommandRegistration`.

Khi registration đã khai báo đầy đủ target và binding, giữ nguyên các contract test:

~~~java
var session = client
        .nonInterative("inventory find --sku SKU-42 --limit 5")
        .run();

ShellAssertions.assertThat(session.screen())
        .containsText("sku=SKU-42; limit=5");
~~~

Điều quan trọng là test gửi cú pháp công khai qua parser/registry. Không viết test chỉ gọi trực tiếp lambda handler của registration, vì như vậy không xác nhận tên command, option hoặc chuyển kiểu.

Trong Spring Shell 3.3.x, `CommandRegistration` được khai báo như bean và tự động đăng ký. Nếu dự án tự tạo `CommandCatalog` hoặc đăng ký command động, test cần nạp đúng registry đó trước khi gửi command.

## 9. Kiểm thử interactive session và prompt

Nếu command có hỏi thêm dữ liệu, kiểm tra phiên tương tác riêng với test non-interactive. Spring Shell 3.3.x cho phép tạo `InteractiveShellSession` qua `ShellTestClient`.

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

import static org.awaitility.Awaitility.await;
import static org.springframework.test.annotation.DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD;

@ShellTest
@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)
class InventoryInteractiveTests {

    @Autowired
    ShellTestClient client;

    @Test
    void opensPromptAndAcceptsHelpCommand() {
        var session = client.interactive().run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("shell"));

        session.write(
                session.writeSequence()
                        .text("help")
                        .carriageReturn()
                        .build());

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("AVAILABLE COMMANDS"));
    }
}
~~~

Các phiên interactive có trạng thái terminal và runner. Dùng context riêng hoặc `@DirtiesContext` khi mỗi test cần một phiên mới để tránh history, prompt hoặc nội dung màn hình của test trước ảnh hưởng test sau.

Nếu command đọc input bổ sung, cung cấp input theo chuỗi thao tác của session hoặc dùng `ShellInputProvider` ở phiên bản hỗ trợ API đó. Test phải xác nhận cả câu hỏi được hiển thị lẫn cách ứng dụng xử lý câu trả lời.

## 10. Kiểm thử completion

Completion gồm provider tạo candidate và terminal hiển thị candidate. Hai phần cần được xác nhận riêng:

1. **Provider test:** gọi logic provider với context phù hợp và xác nhận danh sách candidate.
2. **Interactive smoke test:** chạy ứng dụng bằng JLine trong terminal/pseudo-terminal, nhập command dở dang và gửi phím Tab để kiểm tra gợi ý thực tế.

Spring Shell 3.3 `ShellWriteSequence` hỗ trợ text, carriage return và một số phím điều hướng. API này không cung cấp thao tác Tab chuyên biệt trong chuỗi ghi. Vì vậy, không nên khẳng định `ShellTestClient` đã kiểm tra được Tab chỉ vì command test đã chạy thành công.

Nếu completion là chức năng quan trọng, thêm smoke test riêng qua terminal thật hoặc pseudo-terminal. Kiểm tra:

- Candidate được trả về theo đúng context và vị trí con trỏ.
- Candidate không chứa giá trị đã bị vô hiệu hóa hoặc dữ liệu không được phép xem.
- Tab hoàn tất duy nhất một candidate theo đúng hành vi mong đợi.
- Nhiều candidate được hiển thị khi có nhiều lựa chọn.
- Provider lỗi hoặc không có dữ liệu không làm hỏng phiên shell.

## 11. Kiểm thử output và định dạng

Output cũng là một phần của CLI contract, đặc biệt khi command được gọi từ script và kết quả được pipe sang công cụ khác.

Với output văn bản:

- Kiểm tra các trường quan trọng có xuất hiện.
- Kiểm tra đơn vị, định dạng ngày và dấu thập phân nếu chúng ảnh hưởng người dùng.
- Không phụ thuộc màu ANSI trong test nghiệp vụ.
- Không phụ thuộc toàn bộ padding/căn cột nếu bố cục không phải hợp đồng cố định.

Với output JSON hoặc CSV:

- Parse output bằng parser tương ứng rồi so sánh dữ liệu.
- Kiểm tra header, thứ tự cột và encoding nếu là cam kết của command.
- Kiểm tra ký tự quote, delimiter, newline và dữ liệu Unicode.
- Kiểm tra stdout chỉ chứa payload nếu người dùng cần pipe; ghi log chẩn đoán sang stderr.

Ví dụ, thay vì so sánh toàn bộ bảng:

~~~java
ShellAssertions.assertThat(session.screen())
        .containsText("SKU-42")
        .containsText("ACTIVE");
~~~

Nếu command xuất JSON, lấy nội dung output theo giao ước của ứng dụng và parse JSON trước khi assertion. Không kiểm tra JSON bằng cách tìm một chuỗi con có thể xuất hiện ở nhiều vị trí.

## 12. Kiểm thử exit code ở cấp tiến trình

`ShellTestClient` giúp gửi command và kiểm tra màn hình. Nó không thay thế kiểm thử tiến trình đã đóng gói và không phải lúc nào cũng cung cấp mã thoát của tiến trình Java.

Nếu hợp đồng của ứng dụng bao gồm exit code, chạy JAR như một tiến trình con:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryProcessTests {

    @Test
    void successfulCommandReturnsZero(
            @TempDir Path directory) throws Exception {

        Path output = directory.resolve("stdout.txt");
        Process process = new ProcessBuilder(
                "java",
                "-jar",
                "build/libs/inventory-shell.jar",
                "inventory",
                "find",
                "--sku",
                "SKU-42")
                .redirectErrorStream(true)
                .redirectOutput(output.toFile())
                .start();

        boolean finished = process.waitFor(15, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
        }
        assertThat(finished).isTrue();
        assertThat(process.exitValue()).isZero();

        String text = Files.readString(output, StandardCharsets.UTF_8);
        assertThat(text).contains("sku=SKU-42");
    }
}
~~~

Đường dẫn JAR và executable Java cần được lấy từ cấu hình build/test của dự án. Ví dụ trên minh họa ranh giới kiểm thử; không hard-code một đường dẫn build nếu project có nhiều module hoặc classifier khác nhau.

Viết thêm test cho input sai để xác nhận mã thoát đã cam kết:

~~~java
assertThat(process.exitValue()).isEqualTo(expectedFailureCode);
~~~

Giá trị `expectedFailureCode` phải theo quy ước mà ứng dụng lựa chọn. Không mặc định rằng mọi exception trong command annotation sẽ tự tạo cùng một exit code trên mọi runner. Hãy chạy đúng command bằng đúng chế độ non-interactive mà người dùng automation sử dụng.

## 13. Phân biệt test logic, test shell và test tiến trình

Ba tầng test bổ sung cho nhau:

| Tầng | Công cụ | Kiểm tra chính |
|---|---|---|
| Unit test | JUnit, Mockito/AssertJ | Quy tắc nghiệp vụ, validation, mapping dữ liệu |
| Shell contract test | `@ShellTest`, `ShellTestClient`, `ShellAssertions` | Parser, binding, command registry, help và output |
| Process/terminal test | `ProcessBuilder`, terminal hoặc pseudo-terminal | Startup, runner, exit code, signal, Tab và hành vi đóng tiến trình |

Không cần đưa mọi test lên tầng tiến trình. Tầng này chậm và phụ thuộc môi trường hơn. Dùng unit test để kiểm tra nhiều trường hợp dữ liệu; dùng shell contract test cho các luồng command đại diện; dùng process/terminal test cho những hành vi chỉ tồn tại ở ranh giới tiến trình.

## 14. Kiểm thử Spring Shell 4.x

Spring Shell 4.x có test starter riêng:

~~~groovy
dependencies {
    testImplementation("org.springframework.shell:spring-shell-starter-test")
}
~~~

Trong API 4.x, `ShellTestClient` cung cấp `sendCommand(String)` và trả về `ShellScreen`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = InventoryShellApplication.class)
class InventoryCommandContractTests {

    @Autowired
    ShellTestClient client;

    @Test
    void preservesThePublicCommandContract() throws Exception {
        var screen = client.sendCommand(
                "inventory find --sku SKU-42 --limit 5");

        ShellAssertions.assertThat(screen)
                .containsText("sku=SKU-42; limit=5");
    }
}
~~~

Trong Spring Shell 4, command annotation dùng `@Command`, `@Option`, `@Argument`; programmatic model dùng bean `Command`. Cách viết command có thể khác, nhưng chuỗi command người dùng nhập và assertion về output vẫn là hợp đồng cần giữ.

Không trộn import và API kiểm thử của 3.3 với 4.x trong cùng một test source. Khi nâng cấp major version, cập nhật test dependency, annotation và cách gửi command theo API của version mới.

## 15. Những lỗi thường gặp khi viết contract test

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ gọi trực tiếp method command | Không kiểm tra parser và binding | Gửi chuỗi lệnh bằng `ShellTestClient` |
| Chỉ kiểm tra service | Command có thể bind sai option mà test vẫn pass | Thêm shell contract test |
| So sánh toàn bộ màn hình terminal | Test dễ vỡ vì padding, màu hoặc terminal width | Assertion các phần thuộc hợp đồng |
| Dùng `@SpringBootTest` cho mọi test shell | Context nặng, runner có thể chờ input | Dùng `@ShellTest` cho test tập trung vào shell |
| Dùng test non-interactive để kết luận Tab hoạt động | Không kiểm tra JLine line editor | Thêm interactive terminal smoke test |
| Kiểm tra output `ERROR` rồi cho rằng exit code khác 0 | Nội dung và mã thoát là hai hợp đồng khác nhau | Chạy tiến trình và assert `exitValue()` |
| Gộp lỗi parser và lỗi nghiệp vụ | Không biết lỗi xảy ra ở lớp nào | Test parser/binding và service validation riêng |
| Test phụ thuộc dữ liệu production | Kết quả thay đổi theo môi trường | Dùng fixture hoặc service giả ổn định |
| Dùng API 3.3 và 4.x lẫn nhau | Test không compile hoặc chạy sai | Khóa test dependency theo BOM của version |
| Không cô lập interactive session | History/screen từ test trước rò sang test sau | Tạo context/session riêng khi cần |

## 16. Ma trận contract test đề xuất

Với mỗi command quan trọng, tạo ma trận dựa trên hợp đồng công khai:

| Nhóm | Ca kiểm thử tối thiểu |
|---|---|
| Đăng ký | Tên command xuất hiện trong help |
| Binding | Argument/option đúng vị trí và đúng tên |
| Default | Bỏ option tùy chọn thì nhận default |
| Conversion | Chuỗi được chuyển thành kiểu dữ liệu mong muốn |
| Required | Thiếu option bắt buộc bị từ chối |
| Validation | Giá trị sai định dạng hoặc ngoài range bị từ chối |
| Business result | Input hợp lệ trả kết quả đúng |
| Error message | Người dùng nhận thông báo ổn định, không lộ stack trace |
| Help | Mô tả, usage và option đúng |
| Completion | Provider trả candidate đúng; Tab được smoke test ở terminal |
| Interactive input | Prompt nhận câu trả lời và xử lý đúng |
| Output format | Văn bản/JSON/CSV đúng hợp đồng |
| Exit code | Process trả mã thành công và thất bại đúng quy ước |
| Automation | Non-interactive command kết thúc, không chờ REPL |

Không phải command nào cũng cần tất cả các hàng. Chọn các ca phù hợp với chức năng và người dùng của command, nhưng giữ các ca đã công bố trong tài liệu hoặc script vận hành.

## 17. Quy trình làm việc khi thay đổi command

Khi đổi tên command, thêm option hoặc thay đổi output, thực hiện theo trình tự:

1. Ghi lại cú pháp command công khai hiện tại.
2. Xác định default, required option, kiểu dữ liệu và validation.
3. Cập nhật unit test cho nghiệp vụ.
4. Cập nhật shell contract test bằng chuỗi command thật.
5. Kiểm tra help output và lỗi mà người dùng nhìn thấy.
6. Nếu có prompt hoặc completion, kiểm tra interactive session.
7. Nếu command được dùng trong script/CI, kiểm tra exit code và non-interactive process.
8. Chạy test suite của dự án bằng đúng Spring Shell version.
9. Cập nhật tài liệu sử dụng nếu hợp đồng CLI thay đổi.

Nếu thay đổi chỉ là nội bộ service và không đổi command contract, shell contract test vẫn phải tiếp tục pass mà không cần sửa assertion. Đây là dấu hiệu tốt cho thấy giao diện CLI được giữ ổn định.

## 18. Tổng kết

Một command Spring Shell có hai mặt cần kiểm thử: logic xử lý bên trong và hợp đồng CLI mà người dùng gọi. Unit test xác nhận logic nghiệp vụ; `ShellTestClient` xác nhận parser, binding, command registry, help và output; process/terminal test xác nhận startup, exit code và thao tác tương tác thực tế.

Spring Shell 3.3.4 dùng `@ShellTest` cùng `ShellTestClient.nonInterative(...).run().screen()`. Dự án dùng annotation model hay `CommandRegistration` đều có thể gửi cùng chuỗi command để kiểm thử giao diện công khai. Spring Shell 4.x dùng test starter và `ShellTestClient.sendCommand(...)`, nhưng vẫn giữ nguyên nguyên tắc kiểm thử theo hợp đồng.

Khi kiểm thử đúng ranh giới, dự án có thể thay đổi cách đăng ký command hoặc tổ chức service mà vẫn giữ cú pháp, default, validation, help và output mà người dùng đang dựa vào.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Testing Basics](https://docs.spring.io/spring-shell/reference/3.3/testing/basics.html) — `@ShellTest`, `ShellTestClient`, interactive và non-interactive session.
- [Spring Shell 3.3.0 — ShellTestClient API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html) — API session và `nonInterative(...)`.
- [Spring Shell 3.3.0 — ShellAssertions API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellAssertions.html) — assertion cho shell screen.
- [Spring Shell 3.3.4 — Programmatic Command Registration](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/programmatic.html) — đăng ký `CommandRegistration` bằng bean.
- [Spring Shell 4.0.4 — Testing](https://docs.spring.io/spring-shell/reference/testing.html) — test starter, `ShellScreen`, `ShellAssertions`, `ShellTestClient` và `ShellInputProvider`.
- [Spring Shell 4.0.4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — annotation model và programmatic model.
