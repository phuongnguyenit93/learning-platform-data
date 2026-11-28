# Ẩn đầu vào nhạy cảm bằng khả năng thành phần được hỗ trợ

Khi command cần nhận mật khẩu, API token hoặc một bí mật khác, việc yêu cầu người dùng gõ trực tiếp giá trị trên dòng lệnh có thể làm lộ dữ liệu. Giá trị nhập sau tên command hoặc option có thể xuất hiện trong lịch sử shell, log của script, danh sách tiến trình hoặc bản ghi CI. Với một thao tác tương tác, Spring Shell 3.x cung cấp **StringInput** để hỏi dữ liệu ngay trong terminal và che ký tự người dùng đang nhập.

Thành phần này cho phép đặt ký tự che bằng **setMaskCharacter()**. Khi mask được bật, phần nhập và phần kết quả hiển thị của component dùng ký tự thay thế, trong khi chương trình vẫn nhận được giá trị gốc để xử lý. **ComponentFlow** cũng hỗ trợ cấu hình tương tự qua **StringInputSpec.maskCharacter()**.

Điểm cần nhớ là che ký tự chỉ bảo vệ nội dung hiển thị trên terminal. Giá trị gốc vẫn tồn tại trong bộ nhớ ứng dụng và có thể bị lộ nếu command ghi log, trả nó ra output hoặc dùng renderer tự in giá trị thô. Bài này trình bày cách dùng component đúng mục đích và cách giữ bí mật trong suốt phần xử lý tiếp theo.

## 1. Vì sao không nên nhập bí mật như một option thông thường?

Ví dụ sau đưa token trực tiếp vào dòng lệnh:

~~~text
account connect --token=my-secret-token
~~~

Đây là cách nhập tiện lợi nhưng có thể để lại giá trị trong:

- Lịch sử command của terminal.
- Log chạy script hoặc CI.
- Danh sách đối số tiến trình tùy hệ điều hành và cách khởi chạy.
- Công cụ ghi lại lệnh, telemetry hoặc bản ghi hỗ trợ.
- Lịch sử thao tác được chia sẻ trong tài liệu hoặc ảnh chụp màn hình.

Với command cần hỏi bí mật từ người vận hành, nên mở một prompt riêng sau khi command bắt đầu:

~~~text
account connect
API token: ***************
Đã kết nối tài khoản.
~~~

Người dùng nhập token tại prompt. Terminal chỉ hiển thị ký tự che, còn command dùng giá trị thật để xác thực. Không đưa token vào tên command, option, argument hoặc ví dụ tài liệu.

## 2. StringInput và ký tự che

**StringInput** là component nhập một chuỗi đơn giản. Component nhận terminal, tên trường và giá trị mặc định; sau đó chạy vòng lặp nhập và trả về **StringInputContext**.

Để che nội dung, gọi:

~~~java
component.setMaskCharacter('*');
~~~

Phương thức này đặt ký tự che cho cả phần input đang nhập và phần kết quả component hiển thị. Ví dụ, nếu người dùng nhập chuỗi **s3cr3t**, terminal hiển thị các dấu sao thay cho nội dung thật.

Các API quan trọng của component:

| API | Vai trò |
|---|---|
| **StringInput** | Component yêu cầu người dùng nhập một chuỗi |
| **setMaskCharacter(Character)** | Chọn ký tự hiển thị thay cho ký tự thật |
| **run(StringInputContext)** | Chạy component và nhận context kết quả |
| **getResultValue()** | Lấy giá trị gốc để xử lý |
| **getMaskedInput()** | Lấy phần đang nhập ở dạng đã che |
| **getMaskedResultValue()** | Lấy kết quả ở dạng đã che |
| **hasMaskCharacter()** | Kiểm tra component có đặt ký tự che hay không |

Các lớp trên thuộc package **org.springframework.shell.component** trong Spring Shell 3.x. **StringInputContext** là interface lồng bên trong **StringInput**.

## 3. Dùng StringInput để hỏi token

Trong mô hình command annotation của Spring Shell 3.x, có thể kế thừa **AbstractShellComponent** để lấy terminal, resource loader và template executor do shell quản lý.

Ví dụ command sau yêu cầu người dùng nhập API token:

~~~java
import org.springframework.shell.component.StringInput;
import org.springframework.shell.component.StringInput.StringInputContext;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class AccountCommands extends AbstractShellComponent {

    private final AccountService accountService;

    public AccountCommands(AccountService accountService) {
        this.accountService = accountService;
    }

    @ShellMethod(
            key = "account connect",
            value = "Kết nối tài khoản bằng API token."
    )
    public String connect() {
        StringInput input = new StringInput(
                getTerminal(),
                "API token",
                null
        );
        input.setResourceLoader(getResourceLoader());
        input.setTemplateExecutor(getTemplateExecutor());
        input.setMaskCharacter('*');

        StringInputContext context =
                input.run(StringInputContext.empty());
        String token = context.getResultValue();

        if (token == null || token.isBlank()) {
            return "Chưa nhập API token.";
        }

        accountService.connect(token);
        return "Đã kết nối tài khoản.";
    }
}
~~~

Command tạo component với tên trường **API token**, gắn resource loader và template executor của shell, rồi bật mask bằng dấu sao. Sau khi người dùng hoàn tất, **getResultValue()** trả về token gốc để service xác thực.

Kết quả command chỉ thông báo thao tác thành công. Không nối token vào chuỗi trả về và không ghi token vào log. Component chịu trách nhiệm hiển thị prompt; service chỉ nhận dữ liệu cần thiết để thực hiện nghiệp vụ.

Nếu ứng dụng đã có một lớp command kế thừa **AbstractShellComponent**, có thể dùng lại các helper của lớp đó. Không tự tạo một terminal mới cho mỗi lần nhập vì component cần sử dụng terminal hiện tại của Spring Shell.

## 4. Giá trị gốc và giá trị đã che trong StringInputContext

**StringInputContext** cung cấp cả giá trị gốc lẫn giá trị đã che. Hai loại giá trị có mục đích khác nhau:

| Phương thức | Dùng cho |
|---|---|
| **getResultValue()** | Chuyển giá trị thật vào service hoặc bước xác thực |
| **getMaskedResultValue()** | Hiển thị kết quả mà không lộ nội dung |
| **getInput()** | Đọc phần input thô trong lúc component chạy |
| **getMaskedInput()** | Hiển thị phần input đã che |
| **getMaskCharacter()** | Xem ký tự che hiện được cấu hình |

Ví dụ, khi cần xác nhận người dùng đã nhập token mà không hiển thị token:

~~~java
StringInputContext context = input.run(StringInputContext.empty());

String token = context.getResultValue();
String safePreview = context.getMaskedResultValue();

if (token == null || token.isBlank()) {
    return "Token không được để trống.";
}

accountService.connect(token);
return "Đã nhận thông tin: " + safePreview;
~~~

Trong command thực tế, thường không cần hiển thị lại token ngay cả ở dạng che. Ví dụ trên chỉ minh họa sự khác nhau giữa hai accessor. Nếu cần thông báo sau khi xác thực, hãy dùng một thông báo trung tính như **Đã kết nối tài khoản**.

Không nhầm **getMaskedResultValue()** với giá trị dùng cho nghiệp vụ. Giá trị này đã bị thay thế bằng ký tự che và không thể dùng để xác thực.

## 5. Dùng mask trong ComponentFlow

Khi command cần hỏi nhiều thông tin theo một quy trình, **ComponentFlow** ghép các component thành một flow. Với chuỗi nhạy cảm, **StringInputSpec.maskCharacter()** đặt ký tự che ngay trong cấu hình builder.

Ví dụ flow nhận token:

~~~java
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class AccountFlowCommands {

    private final ComponentFlow.Builder componentFlowBuilder;
    private final AccountService accountService;

    public AccountFlowCommands(
            ComponentFlow.Builder componentFlowBuilder,
            AccountService accountService) {
        this.componentFlowBuilder = componentFlowBuilder;
        this.accountService = accountService;
    }

    @ShellMethod(
            key = "account connect-wizard",
            value = "Kết nối tài khoản qua các bước tương tác."
    )
    public String connectWizard() {
        ComponentFlow flow = componentFlowBuilder.clone()
                .reset()
                .withStringInput("apiToken")
                    .name("API token")
                    .maskCharacter('*')
                    .and()
                .build();

        ComponentFlow.ComponentFlowResult result = flow.run();
        String token = result.getContext().get("apiToken", String.class);

        if (token == null || token.isBlank()) {
            return "Chưa nhập API token.";
        }

        accountService.connect(token);
        return "Đã kết nối tài khoản.";
    }
}
~~~

Trong flow, **withStringInput("apiToken")** tạo trường nhập có mã định danh **apiToken**. **name()** đặt nhãn hiển thị; **maskCharacter('*')** bật che; **and()** quay lại builder cha để có thể thêm component khác. Sau khi flow chạy xong, **getContext()** lấy context chung và **get("apiToken", String.class)** lấy giá trị được lưu theo ID.

Mặc định, **StringInputSpec** tự lưu kết quả vào **ComponentContext** theo ID của component. Nếu thay đổi cấu hình lưu kết quả bằng **storeResult(false)**, không thể giả định rằng giá trị vẫn có trong context chung; cần thiết kế cách nhận kết quả phù hợp với flow đó.

Dùng **ComponentFlow** khi có nhiều bước như chọn môi trường, nhập tên tài khoản, nhập token và xác nhận. Với một prompt bí mật đơn lẻ, **StringInput** thường ngắn gọn hơn.

## 6. Không để custom renderer làm lộ giá trị

Spring Shell cho phép thay renderer mặc định bằng một hàm hoặc template. Điều này hữu ích khi cần tùy chỉnh giao diện, nhưng renderer có thể làm mất tác dụng của mask nếu đọc nhầm biến.

Trong **StringInputContext**, các cặp accessor có ý nghĩa khác nhau:

- **getInput()** và **getResultValue()** trả về dữ liệu thô.
- **getMaskedInput()** và **getMaskedResultValue()** trả về dữ liệu đã che.

Với trường nhạy cảm, custom renderer chỉ nên dùng accessor đã che. Không render trực tiếp **getInput()**, **getResultValue()** hoặc template variable **input**, **resultValue**.

Ví dụ sau minh họa cách chọn nội dung an toàn cho renderer:

~~~java
String visibleValue;

if (context.getResultValue() != null) {
    visibleValue = context.getMaskedResultValue();
}
else {
    visibleValue = context.getMaskedInput();
}
~~~

Nếu cần template riêng, dùng các biến **maskedInput** và **maskedResultValue** được cung cấp trong context của StringInput. Không đưa giá trị thô vào thuộc tính debug, message hoặc nội dung lỗi của component.

Một renderer tùy chỉnh cũng không nên hiển thị giá trị mặc định nếu default value có chứa thông tin nhạy cảm. Tốt nhất, không cấu hình secret làm default value ngay từ đầu.

## 7. Mask không phải mã hóa hoặc xóa bí mật khỏi bộ nhớ

Ký tự che chỉ thay đổi cách component vẽ dữ liệu trên terminal. Nó không mã hóa giá trị và không loại bỏ giá trị gốc khỏi bộ nhớ của JVM.

Sau khi component hoàn tất:

- **getResultValue()** vẫn trả về chuỗi gốc.
- Service nhận chuỗi gốc để xác thực hoặc gọi API.
- Java String là immutable; ứng dụng không thể ghi đè an toàn nội dung của String sau khi sử dụng.
- Một debugger, heap dump hoặc log vô tình ghi giá trị vẫn có thể làm lộ bí mật.
- Số lượng ký tự che thường cho biết gần đúng độ dài dữ liệu đã nhập.

Do đó, hãy giữ thời gian sống của token ngắn nhất có thể. Không lưu token vào field của command singleton, cache, session không cần thiết hoặc đối tượng flow được giữ lâu. Không gọi **toString()** trên context rồi ghi log.

Nếu yêu cầu bảo mật bắt buộc phải chủ động ghi đè vùng nhớ chứa secret, **StringInput** không cung cấp bảo đảm đó vì kết quả là **String**. Khi ấy cần một cơ chế nhập chuyên biệt trả về vùng nhớ có thể quản lý và xóa theo yêu cầu của hệ thống.

## 8. Không đưa secret vào output, log hoặc thông báo lỗi

Các ví dụ sau làm lộ bí mật dù component đã che khi nhập:

~~~java
// Không trả secret ra màn hình
return "Token đã nhập: " + context.getResultValue();

// Không ghi secret vào log
logger.info("Connecting with token {}", context.getResultValue());

// Không đưa secret vào thông báo lỗi
throw new IllegalStateException(
        "Token không hợp lệ: " + context.getResultValue()
);
~~~

Hãy trả về thông báo không chứa giá trị:

~~~java
try {
    accountService.connect(context.getResultValue());
    return "Đã kết nối tài khoản.";
}
catch (InvalidCredentialException ex) {
    logger.warn("Xác thực tài khoản thất bại.");
    return "Không thể xác thực. Hãy kiểm tra token và thử lại.";
}
~~~

Nếu cần liên kết log với một lần thao tác, dùng request ID hoặc account ID không nhạy cảm. Không dùng token, một phần token hoặc hash tự tạo từ token làm mã tương quan nếu chưa có chính sách bảo mật phù hợp.

## 9. Chỉ dùng component tương tác khi có terminal tương tác

**StringInput** và **ComponentFlow** là thành phần hỏi người dùng trong terminal. Chúng cần một phiên input tương tác để nhận phím. Không nên gọi chúng trong một tác vụ batch hoặc script không có người trả lời.

| Môi trường | Cách xử lý phù hợp |
|---|---|
| Người vận hành chạy REPL trong terminal | Dùng StringInput hoặc ComponentFlow với mask |
| Command được gọi từ CI không có TTY | Lấy secret từ secret store của CI hoặc cơ chế cấp credential của môi trường |
| Script chạy tự động | Truyền tham chiếu secret an toàn hoặc inject credential từ môi trường, không mở prompt chờ |
| Test tự động | Dùng terminal test client hoặc test component context; không ghi secret thật vào test log |

Không đặt secret trong file script được commit vào repository. Không truyền token trong đối số command chỉ để tránh prompt nếu cách chạy đó làm token xuất hiện trong process list hoặc lịch sử command.

Nếu command chỉ có ý nghĩa khi người dùng tương tác, có thể khai báo chế độ interactive phù hợp trong command model. Nếu command cần hỗ trợ cả automation, tách luồng tương tác khỏi luồng tự động và định nghĩa rõ nguồn credential của từng chế độ.

## 10. Kiểm thử khả năng che

Kiểm thử nên xác nhận cả hai điều: component cung cấp giá trị gốc cho nghiệp vụ và phần hiển thị không chứa giá trị gốc.

Có thể kiểm tra các accessor của context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.shell.component.StringInput.StringInputContext;

class StringInputMaskTests {

    @Test
    void keepsRawResultForLogicAndMaskedResultForDisplay() {
        StringInputContext context =
                StringInputContext.of(null, '*');
        context.setResultValue("s3cr3t");

        assertThat(context.getResultValue()).isEqualTo("s3cr3t");
        assertThat(context.getMaskedResultValue()).isEqualTo("******");
        assertThat(context.getMaskedResultValue()).doesNotContain("s3cr3t");
    }
}
~~~

Đây là unit test cho quy tắc context, không thay thế kiểm thử component chạy trong terminal. Cần thêm kiểm thử tích hợp để xác nhận:

1. Component thực sự gọi **setMaskCharacter()** với ký tự dự kiến.
2. Khi người dùng gõ, màn hình không hiển thị token gốc.
3. Sau khi hoàn tất, phần kết quả component vẫn hiển thị dạng đã che.
4. Command truyền giá trị gốc vào service nhưng không trả giá trị đó ra output.
5. Log và exception message không chứa secret.
6. Khi component bị hủy hoặc input rỗng, command xử lý đúng trạng thái.
7. Khi chạy non-interactive, command không bị treo vì chờ prompt.
8. Custom renderer chỉ sử dụng **getMaskedInput()** và **getMaskedResultValue()**.

Spring Shell 3.3 có **ShellTestClient** và **ShellTest** để kiểm thử phiên shell. Có thể chạy phiên interactive trong test, gửi chuỗi input giả lập và kiểm tra màn hình sau khi component hoàn tất. Dùng secret giả lập như **test-token-123**, không dùng credential thật trong fixture hoặc log.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Người dùng vẫn nhìn thấy token khi gõ | Chưa gọi **setMaskCharacter()** hoặc **maskCharacter()** | Bật mask trên đúng StringInput |
| Token bị lộ sau khi nhấn Enter | Renderer hiển thị giá trị thô | Dùng **getMaskedResultValue()** |
| Token bị lộ trong prompt tùy chỉnh | Renderer đọc **getInput()** | Dùng **getMaskedInput()** |
| Command trả token ra terminal | Nối **getResultValue()** vào chuỗi kết quả | Chỉ trả thông báo trung tính |
| Log chứa token | Ghi context hoặc giá trị gốc | Che dữ liệu log và chỉ ghi mã tương quan |
| Không lấy được giá trị trong flow | Sai ID hoặc tắt **storeResult** | Dùng đúng ID và kiểm tra cấu hình lưu kết quả |
| Component chờ mãi khi chạy CI | Command gọi prompt trong môi trường không có TTY | Dùng nguồn credential dành cho automation |
| Bí mật có sẵn trước khi người dùng nhập | Đặt secret làm default value | Không dùng default value cho trường nhạy cảm |
| Nghĩ rằng mask xóa secret khỏi JVM | Nhầm bảo vệ hiển thị với mã hóa bộ nhớ | Giữ scope ngắn và áp dụng cơ chế quản lý secret phù hợp |

## 12. Checklist sử dụng StringInput cho dữ liệu nhạy cảm

- [ ] Dùng **StringInput** hoặc **ComponentFlow** thay cho option chứa trực tiếp secret.
- [ ] Đặt **setMaskCharacter()** hoặc **maskCharacter()** trước khi chạy component.
- [ ] Không đặt secret làm default value.
- [ ] Dùng **getResultValue()** chỉ để chuyển dữ liệu vào service cần thiết.
- [ ] Dùng **getMaskedInput()** và **getMaskedResultValue()** khi cần hiển thị.
- [ ] Không dùng raw **getInput()** hoặc **getResultValue()** trong custom renderer.
- [ ] Không ghi secret vào log, exception, output, metric hoặc audit event.
- [ ] Không giữ context hoặc secret trong field sống lâu.
- [ ] Xử lý riêng trường hợp hủy input, chuỗi rỗng và terminal không tương tác.
- [ ] Dùng secret giả lập trong kiểm thử và xác nhận màn hình không chứa giá trị gốc.
- [ ] Ghi nhớ rằng mask không mã hóa và không bảo đảm xóa dữ liệu khỏi bộ nhớ.

Khả năng mask của Spring Shell giúp người vận hành nhập dữ liệu nhạy cảm mà không hiển thị nội dung trên terminal. Bảo vệ chỉ hoàn chỉnh khi command tiếp tục giữ kín giá trị gốc trong renderer, log, output, exception và vòng đời xử lý.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — String Input](https://docs.spring.io/spring-shell/reference/3.3/components/ui/stringinput.html) — component nhập chuỗi và tùy chọn che dữ liệu nhạy cảm.
- [Spring Shell 3.3.4 — Component Render](https://docs.spring.io/spring-shell/reference/3.3/components/ui/render.html) — renderer tùy chỉnh và context của component.
- [Spring Shell 3.3.4 — Flow](https://docs.spring.io/spring-shell/reference/3.3/components/flow/index.html) — ghép nhiều component thành một flow.
- [Spring Shell 3.3.0 API — StringInput](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/StringInput.html) — constructor, run và setMaskCharacter.
- [Spring Shell 3.3.0 API — StringInputContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/StringInput.StringInputContext.html) — giá trị gốc, masked input và masked result.
- [Spring Shell 3.3.0 API — StringInputSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/StringInputSpec.html) — maskCharacter trong ComponentFlow builder.
- [Spring Shell 3.3.0 API — ComponentFlow.ComponentFlowResult](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html) — context kết quả của flow.
- [Spring Shell 3.3.0 API — ComponentContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/context/ComponentContext.html) — truy xuất giá trị theo ID và kiểu dữ liệu.
- [Spring Shell 3.3.0 API — ShellTestClient](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html) — kiểm thử phiên shell tương tác và non-interactive.
