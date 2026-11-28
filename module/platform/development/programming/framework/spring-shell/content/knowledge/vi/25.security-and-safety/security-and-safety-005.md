# Đọc dữ liệu nhạy cảm bằng đầu vào được che khi terminal hỗ trợ

CLI đôi khi cần nhận mật khẩu, API token, mã khôi phục hoặc một giá trị bí mật khác. Nếu nhập trực tiếp giá trị đó như option của command, nội dung có thể xuất hiện trong lịch sử shell, danh sách process hoặc log. Spring Shell 3.x cung cấp `StringInput` để yêu cầu nhập riêng trong terminal và thay ký tự người dùng gõ bằng ký tự che như `*`.

Che ký tự chỉ bảo vệ phần hiển thị khi nhập. Giá trị thật vẫn tồn tại trong bộ nhớ ứng dụng và có thể bị lộ nếu command trả nó ra terminal, ghi log, lưu vào context dùng chung hoặc truyền qua command line. Bài viết hướng dẫn cách dùng `StringInput`, phân biệt giá trị thật với giá trị đã che, xử lý terminal không tương tác và giữ bí mật trong toàn bộ luồng xử lý.

## 1. Vì sao không truyền secret như một option?

Ví dụ không nên dùng:

```bash
credential set-token --token=super-secret-value
```

Giá trị nhạy cảm nằm trong văn bản command. Tùy môi trường, nó có thể được lưu trong:

- Lịch sử terminal hoặc lịch sử REPL.
- Danh sách đối số của process và công cụ giám sát hệ thống.
- Log của CI/CD, wrapper script hoặc công cụ thực thi command.
- Bản ghi audit chứa toàn bộ câu lệnh.
- File script, cấu hình hoặc tài liệu hỗ trợ được chia sẻ.

Trong Spring Shell interactive mode, người dùng nên gọi command không chứa secret, sau đó nhập secret tại prompt được che. Ví dụ:

```text
shell:> credential set-token
API token: **************
Token đã được cập nhật.
```

Command line chỉ chứa tên thao tác. Secret được đọc trong một bước input riêng, không nằm trong chuỗi command mà người dùng đã nhập.

## 2. StringInput trong Spring Shell 3.x

`StringInput` thuộc package `org.springframework.shell.component`. Component nhận một JLine `Terminal`, tên hiển thị và giá trị mặc định. Gọi `setMaskCharacter('*')` để che ký tự trong lúc nhập và phần kết quả được render bởi component.

Các API quan trọng:

| API | Mục đích |
|---|---|
| `new StringInput(terminal, name, defaultValue)` | Tạo input văn bản |
| `setMaskCharacter('*')` | Chọn ký tự dùng để che input và kết quả hiển thị |
| `setResourceLoader(...)` | Cấp resource loader để tải template mặc định |
| `setTemplateExecutor(...)` | Cấp template executor để render component |
| `run(StringInputContext.empty())` | Chạy prompt và nhận context kết quả |
| `getResultValue()` | Lấy giá trị thật đã nhập |
| `getMaskedInput()` | Lấy nội dung input đã che để hiển thị |
| `getMaskedResultValue()` | Lấy kết quả đã che để hiển thị |
| `setPrintResults(false)` | Không in kết quả component ra console sau khi chạy |

`StringInputContext` còn có `getInput()`, nhưng đây là nội dung thô. Khi xử lý secret, không dùng `getInput()` trong renderer, log hoặc thông báo.

## 3. Ví dụ nhập API token bằng StringInput

Trong Spring Shell 3.x, command bean có thể kế thừa `AbstractShellComponent` để dùng terminal, resource loader và template executor do Spring Shell quản lý.

```java
import org.springframework.shell.component.StringInput;
import org.springframework.shell.component.StringInput.StringInputContext;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class CredentialCommands extends AbstractShellComponent {

    private final CredentialService credentialService;

    public CredentialCommands(CredentialService credentialService) {
        this.credentialService = credentialService;
    }

    @ShellMethod(key = "credential set-token", value = "Set an API token")
    public String setToken() {
        StringInput input = new StringInput(
                getTerminal(), "API token", null);

        input.setMaskCharacter('*');
        input.setPrintResults(false);
        input.setResourceLoader(getResourceLoader());
        input.setTemplateExecutor(getTemplateExecutor());

        StringInputContext context = input.run(StringInputContext.empty());
        String token = context.getResultValue();

        if (token == null || token.isBlank()) {
            return "Không có token được cung cấp.";
        }

        credentialService.replaceToken(token);
        return "API token đã được cập nhật.";
    }
}
```

Điểm quan trọng trong ví dụ:

1. Giá trị mặc định là `null`, không điền sẵn mật khẩu hoặc token.
2. `setMaskCharacter('*')` che ký tự người dùng đang nhập.
3. `setPrintResults(false)` ngăn component tự in kết quả sau khi chạy.
4. `getResultValue()` được dùng nội bộ để chuyển secret cho service.
5. Command chỉ trả thông báo thành công, không trả token.

`CredentialService.replaceToken(...)` phải xử lý secret mà không ghi giá trị vào log hoặc exception message. Nếu việc lưu thất bại, command chỉ nên hiển thị thông báo đã được làm sạch, không nối secret vào nội dung lỗi.

## 4. Giá trị thật và giá trị đã che là hai thứ khác nhau

`StringInputContext` cung cấp cả giá trị thật và giá trị dùng để hiển thị. Không được nhầm hai nhóm API này:

| API | Có chứa secret thật? | Dùng cho |
|---|---:|---|
| `getResultValue()` | Có | Chuyển dữ liệu vào service cần xác thực |
| `getInput()` | Có thể có | Không dùng để hiển thị hoặc ghi log |
| `getMaskedInput()` | Không hiển thị ký tự gốc | Renderer trong lúc nhập |
| `getMaskedResultValue()` | Không hiển thị ký tự gốc | Renderer sau khi xác nhận |
| `getMaskCharacter()` | Không | Kiểm tra ký tự che đã cấu hình |

Đoạn code sau làm lộ secret dù người dùng đã nhập bằng prompt có che:

```java
// KHÔNG LÀM: in giá trị thật ra terminal.
return "Got token: " + context.getResultValue();
```

Đoạn code sau chỉ dùng bản đã che để hiển thị:

```java
return "Token received: " + context.getMaskedResultValue();
```

Trong command nghiệp vụ, cách tốt nhất thường là không hiển thị lại token, kể cả dạng đã che. Chỉ trả trạng thái như `Token đã được cập nhật.`.

## 5. Không để renderer tùy chỉnh làm lộ giá trị

`StringInput` cho phép đặt renderer bằng `setRenderer(...)`. Khi tùy chỉnh giao diện, renderer nhận toàn bộ context, bao gồm cả giá trị thô. Vì vậy, phải chủ động dùng API masked.

```java
import java.util.List;
import java.util.Objects;

import org.jline.utils.AttributedString;

input.setRenderer(context -> {
    String visibleValue = context.getResultValue() != null
            ? context.getMaskedResultValue()
            : context.getMaskedInput();

    String display = Objects.toString(visibleValue, "");
    return List.of(new AttributedString(context.getName() + ": " + display));
});
```

Renderer không được gọi `getResultValue()` hoặc `getInput()` để nối vào chuỗi hiển thị. Không serialize toàn bộ context, không gọi `toString()` trên object có thể chứa secret và không đưa raw value vào template model để debug.

Nếu không cần tùy chỉnh giao diện, hãy dùng renderer/template mặc định và giữ `setPrintResults(false)` để tránh component in kết quả sau khi hoàn tất.

## 6. Dùng StringInput trong ComponentFlow

Khi command có nhiều bước, `ComponentFlow` cho phép ghép các input thành một wizard. `StringInputSpec` hỗ trợ `maskCharacter(...)` giống component độc lập.

```java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("apiToken")
            .name("API token")
            .maskCharacter('*')
            .storeResult(false)
            .and()
        .build();
```

`storeResult(false)` tắt việc tự động đưa kết quả của bước nhập vào `ComponentContext` cha. Giá trị vẫn tồn tại trong context của bước nhập và có thể được đọc bởi handler; vì vậy handler cũng phải tuân thủ quy tắc không log hoặc hiển thị giá trị thật.

`storeResult` mặc định là `true`. Với dữ liệu nhạy cảm, hãy cân nhắc tắt lưu vào context chung nếu các bước sau không cần truy cập secret. Nếu bước sau cần secret, chỉ truyền nó tới service cần thiết và không đưa vào các biến dùng chung của toàn flow.

## 7. Terminal phải có input tương tác

`StringInput` là component tương tác, cần đọc phím từ terminal. Nó phù hợp khi người dùng đang chạy shell trong một terminal có input trực tiếp.

Các tình huống cần kiểm tra:

| Môi trường | Cách xử lý |
|---|---|
| Terminal tương tác bình thường | Mở `StringInput` và dùng ký tự che |
| Terminal qua SSH | Kiểm tra prompt và masking trên terminal từ xa thực tế |
| IDE terminal | Thử nhập, xóa, paste và xác nhận output không lộ secret |
| Input/output bị redirect | Không giả định có thể mở prompt tương tác |
| Script hoặc CI không có TTY | Không gọi `StringInput`; dùng nguồn secret không tương tác |
| Terminal giả lập trong test | Cấp input kiểm thử và xác minh output đã che |

JLine và Spring Shell có kiểm tra terminal/TTY trong hạ tầng component, nhưng việc có biến `TERM` hoặc tên terminal không tự chứng minh rằng người dùng đang có một TTY tương tác. Hãy kiểm tra cách ứng dụng được khởi chạy và thử trên môi trường triển khai.

Nếu không thể bảo đảm prompt được che, không chuyển sang nhập secret bằng `System.in` hoặc `Scanner` với echo mặc định. Hãy từ chối thao tác tương tác đó hoặc chuyển sang cơ chế cấp secret dành cho non-interactive mode.

## 8. Phương án cho non-interactive mode

Script, cron và CI/CD không có người dùng ngồi nhập tại prompt. Trong các môi trường này, không gọi `StringInput` để chờ input.

Ưu tiên các phương án sau theo kiến trúc triển khai:

1. **Secret manager:** lấy secret bằng workload identity hoặc cơ chế xác thực của môi trường chạy.
2. **Secret mount/file được bảo vệ:** hệ thống triển khai mount file với quyền truy cập hạn chế; command đọc file và không in nội dung.
3. **Input stream được kiểm soát:** pipeline cấp secret qua một file descriptor hoặc stdin riêng đã được bảo vệ, nếu ứng dụng có hợp đồng input rõ ràng.

Không mặc định truyền secret qua `--password=...`. Biến môi trường cũng không phải kho bí mật hoàn hảo: chúng có thể được các process cùng quyền truy cập, công cụ chẩn đoán hoặc system dump thu thập. Chỉ dùng environment variable khi nền tảng triển khai có cơ chế cấp phát và bảo vệ phù hợp.

Nên tách hai command hoặc hai adapter:

```text
credential set-token
  -> StringInput có che
  -> CredentialService

credential set-token-from-provider --provider=deployment-secret
  -> SecretProvider
  -> CredentialService
```

Cả hai đường gọi chung service nghiệp vụ. Nhờ vậy, logic lưu và kiểm tra token không phụ thuộc vào terminal hay pipeline.

## 9. Những giới hạn bảo mật của masking

Masking giúp người đứng cạnh khó nhìn thấy nội dung người dùng đang gõ. Nó không mã hóa dữ liệu và không bảo vệ secret trước mọi cách thu thập.

Masking không ngăn được:

- Secret tồn tại trong bộ nhớ JVM sau khi nhập.
- Debugger, heap dump hoặc công cụ giám sát có quyền phù hợp đọc được object chứa secret.
- Screen recording, remote desktop recording hoặc công cụ ghi lại input ở cấp hệ điều hành.
- Ứng dụng tự ghi secret vào log, exception, telemetry hoặc file tạm.
- Người có quyền đọc dữ liệu được lưu sau khi service nhận secret.

`StringInputContext.getResultValue()` trả về `String`. Java `String` là immutable, nên ứng dụng không thể ghi đè nội dung của object đó như với một mảng ký tự. Hãy giới hạn thời gian và phạm vi giữ reference, không cache hoặc giữ context lâu hơn cần thiết. Nếu yêu cầu bảo vệ bộ nhớ nghiêm ngặt, cần thiết kế API nhận `char[]` hoặc dùng secret provider chuyên dụng; masking của terminal không cung cấp khả năng zeroize bộ nhớ.

## 10. Không lưu secret trong command history, log hoặc exception

Các quy tắc thực hành:

- Không khai báo mật khẩu/token là positional argument hoặc command option.
- Không đặt secret làm `defaultValue` của `StringInput`.
- Không in `getResultValue()` hoặc `getInput()`.
- Không ghi secret vào logger, audit event, tracing tag, metric label hoặc telemetry.
- Không nối secret vào exception message.
- Không serialize context chứa secret để debug.
- Không ghi secret vào file cấu hình được commit vào version control.
- Không lưu raw secret trong `ComponentContext` dùng chung nếu không cần thiết.
- Không đưa secret vào tên file, tên job hoặc correlation ID.

Khi cần audit thao tác thay đổi credential, chỉ ghi sự kiện và metadata an toàn, ví dụ:

```text
event=credential.updated
account=service-catalog
actor=operator-17
source=interactive-terminal
result=success
```

Không ghi token, password hoặc giá trị băm của secret vào log thông thường. Việc lưu fingerprint chỉ nên thực hiện khi có yêu cầu nghiệp vụ rõ ràng và đã đánh giá nguy cơ dò đoán.

## 11. Kiểm tra đầu vào mà không tiết lộ secret

Secret vẫn phải được xác thực trước khi lưu hoặc sử dụng. Có thể kiểm tra:

- Giá trị có rỗng hoặc chỉ chứa khoảng trắng không.
- Độ dài có nằm trong giới hạn hệ thống không.
- Định dạng có đúng với loại credential không.
- Token có thể xác thực với dịch vụ đích không.
- Credential có đúng phạm vi quyền được yêu cầu không.

Thông báo lỗi chỉ nên mô tả loại lỗi, không hiển thị giá trị đã nhập:

```java
if (token == null || token.isBlank()) {
    return "Token không được để trống.";
}

if (token.length() > MAX_TOKEN_LENGTH) {
    return "Token vượt quá giới hạn độ dài cho phép.";
}

try {
    credentialService.validateAndReplace(token);
    return "Token đã được cập nhật.";
}
catch (CredentialRejectedException ex) {
    return "Token không hợp lệ hoặc không được chấp nhận.";
}
```

Không tự động `trim()` hoặc thay đổi nội dung secret nếu giao thức không quy định điều đó. Một số credential có thể xem khoảng trắng là một phần của giá trị. Việc kiểm tra định dạng và chuẩn hóa phải theo hợp đồng của hệ thống xác thực.

## 12. Kiểm thử masking và luồng dữ liệu

Không chỉ kiểm tra rằng component hiển thị dấu `*`. Cần xác minh secret không xuất hiện ở các đầu ra khác.

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Nhập token bình thường | Ký tự gõ được che bằng mask character |
| Xóa và sửa input | Ký tự hiển thị vẫn được che |
| Xác nhận input | Service nhận giá trị thật đúng một lần |
| Kết quả component | Không tự in raw value ra console |
| Command result | Chỉ hiển thị trạng thái, không có secret |
| Custom renderer | Chỉ dùng `getMaskedInput()` hoặc `getMaskedResultValue()` |
| ComponentFlow | Secret không bị tự động lưu vào context cha nếu đã chọn `storeResult(false)` |
| Input rỗng | Command dừng hoặc báo lỗi mà không gọi service |
| Hủy thao tác | Không cập nhật credential |
| Không có TTY | Không fallback sang nhập plain text |
| Log và exception | Không chứa secret hoặc nội dung input thô |
| Non-interactive run | Dùng secret provider/file/stream đã được bảo vệ |

Trong test, dùng một chuỗi sentinel giả như `TEST-SECRET-DO-NOT-LEAK`. Sau khi chạy command, kiểm tra output, log capture và exception message không chứa chuỗi đó. Không dùng credential thật trong test hoặc ảnh chụp màn hình.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ký tự nhập hiện nguyên văn | Chưa gọi `setMaskCharacter(...)` hoặc đang dùng input thường | Dùng `StringInput` và đặt mask trước `run()` |
| Người dùng thấy token sau khi nhập xong | Component/command in kết quả hoặc command trả raw value | Dùng `setPrintResults(false)` và chỉ trả trạng thái |
| Log chứa token | Ghi `getResultValue()`, `getInput()` hoặc exception có raw input | Loại bỏ secret khỏi log và làm sạch thông báo lỗi |
| Token nằm trong history | Truyền token trong command option | Nhập ở prompt riêng được che |
| Secret xuất hiện trong renderer tùy chỉnh | Renderer dùng trường raw từ context | Dùng `getMaskedInput()` và `getMaskedResultValue()` |
| Secret bị lưu vào flow context | `storeResult` mặc định bật | Dùng `storeResult(false)` khi các bước sau không cần giá trị trong context cha |
| Command treo trong CI | Component chờ người dùng nhập | Chọn secret provider dành cho non-interactive mode |
| Script không thể nhập secret | Script runner không có phiên terminal tương tác | Mount secret hoặc dùng provider/stream được bảo vệ |
| Nghĩ rằng dấu `*` đã mã hóa secret | Nhầm che hiển thị với bảo vệ dữ liệu | Kiểm soát log, bộ nhớ, lưu trữ và quyền truy cập riêng |

## 14. Checklist trước khi nhận dữ liệu nhạy cảm

- [ ] Đã xác định dữ liệu nào thực sự cần nhập qua terminal.
- [ ] Không truyền secret trong command arguments hoặc positional parameters.
- [ ] Dùng `StringInput` và đặt `setMaskCharacter(...)` trước khi chạy.
- [ ] Không đặt secret trong default value.
- [ ] Đã tắt in kết quả component khi không cần hiển thị.
- [ ] Command chỉ trả thông báo trạng thái, không trả giá trị thật.
- [ ] Renderer chỉ dùng masked context fields.
- [ ] Secret không được ghi vào log, exception, telemetry hoặc audit payload.
- [ ] Đã phân biệt rõ interactive TTY với script/CI non-interactive.
- [ ] Không fallback sang input plain text khi masking không hoạt động.
- [ ] Có secret provider hoặc secret file được bảo vệ cho automation.
- [ ] Đã hạn chế thời gian và phạm vi giữ secret trong bộ nhớ.
- [ ] Đã kiểm thử output/log không chứa sentinel secret.
- [ ] Đã kiểm tra quyền truy cập và chính sách lưu credential sau khi nhập.

## Tài liệu tham khảo

1. [Spring Shell 3.3 – `StringInput` API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/StringInput.html) – `setMaskCharacter`, `setPrintResults` và renderer.
2. [Spring Shell 3.3 – `StringInputContext` API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/StringInput.StringInputContext.html) – raw result, masked input và masked result.
3. [Spring Shell 3.3 – `StringInputSpec` API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/StringInputSpec.html) – `maskCharacter` và `storeResult` trong ComponentFlow.
4. [Spring Shell 3.3 – Components: String Input](https://docs.spring.io/spring-shell/reference/3.3/components/ui/stringinput.html) – cách dùng component nhập văn bản nhạy cảm.
5. [JLine 3 – Line Reader](https://jline.org/versions/3.x/docs/line-reader/) – `readLine` hỗ trợ mask character khi nhập mật khẩu.
6. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) – loại bỏ hoặc che password, access token và dữ liệu nhạy cảm khỏi log.
7. [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) – quản lý, cấp phát và bảo vệ secret trong ứng dụng và môi trường triển khai.

`StringInput` giúp người dùng nhập secret mà không hiển thị từng ký tự trên terminal. Hãy xem masking là lớp bảo vệ giao diện: chỉ chuyển giá trị thật đến service cần dùng, không in hoặc ghi log, và chọn secret provider được bảo vệ cho các lần chạy không có terminal tương tác.
