# Tránh đưa mật khẩu hoặc token vào đối số lộ qua lịch sử và danh sách tiến trình

Không truyền mật khẩu, API token, access key hoặc private key trực tiếp trong command line. Một lệnh như `login --password=...` có thể để lộ bí mật trong lịch sử shell, danh sách tiến trình, log của CI/CD, script wrapper hoặc bản ghi hỗ trợ vận hành. Dùng dấu nháy, biến môi trường trong câu lệnh hay tham số JVM `-D` không làm cho giá trị trở thành bí mật.

Với Spring Shell 3.x, hãy tách dữ liệu định danh có thể công khai khỏi thông tin xác thực. Người dùng có thể nhập bí mật qua component được che ký tự khi chạy terminal tương tác; script và CI nên lấy bí mật từ secret manager hoặc file secret được mount với quyền truy cập giới hạn. Mọi đường nhập đều phải tránh in, ghi log hoặc đưa giá trị bí mật trở lại command history.

## Vì sao đối số command line làm lộ bí mật?

Khi người dùng gõ:

```text
login --username alice --password P@ssw0rd!
```

giá trị password nằm ngay trong dòng lệnh. Nó có thể bị lưu ở nhiều nơi:

- **Shell history:** shell có thể ghi lại dòng lệnh để người dùng gọi lại sau này.
- **Process list:** hệ điều hành và công cụ giám sát có thể hiển thị command line của tiến trình đang chạy; quyền quan sát phụ thuộc hệ điều hành và cấu hình.
- **CI/CD log:** runner có thể ghi lệnh đã thực thi, trace shell, debug output hoặc tham số khi khởi chạy job.
- **Script và cấu hình:** dòng lệnh có thể được commit vào Git, lưu trong ticket, wiki, pipeline definition hoặc file cấu hình.
- **Telemetry và crash report:** wrapper, process supervisor hoặc hệ thống chẩn đoán có thể thu thập command line.

Đặt bí mật trong dấu nháy không thay đổi điều này:

```bash
# Không an toàn: shell vẫn nhận giá trị bí mật trong dòng lệnh.
java -jar customer-cli.jar login --token "eyJhbGciOi..."
```

Các dạng sau cũng là đối số khởi chạy có thể bị quan sát:

```text
java -Dapp.api-token=eyJhbGciOi... -jar customer-cli.jar
java -jar customer-cli.jar --app.api-token=eyJhbGciOi...
```

Spring Boot tự động thêm command-line options vào `Environment`; chúng có độ ưu tiên cao hơn file cấu hình. Vì vậy, không dùng command-line property để truyền password hoặc token chỉ vì ứng dụng có thể bind nó bằng `@Value` hay `@ConfigurationProperties`.

## Shell history có thể lưu những gì?

History thường lưu câu lệnh đã nhập, không chỉ những command đã chạy thành công. Ví dụ PowerShell với PSReadLine duy trì history file chứa các lệnh và dữ liệu đã nhập. PSReadLine có heuristic lọc một số dòng chứa từ như `password`, `token`, `secret` hoặc `apikey`, nhưng hành vi phụ thuộc phiên bản, cú pháp và cấu hình. Không dựa vào bộ lọc đó để bảo vệ bí mật.

Các shell khác cũng có cơ chế history riêng. Một command có thể được lưu bởi shell cục bộ trước khi Spring Shell hoặc ứng dụng Java nhận được đối số. Vì vậy, ứng dụng không thể sửa rủi ro history bằng cách chỉ che output sau khi khởi động.

Quy tắc thực hành:

- Không gõ giá trị bí mật trực tiếp sau tên option hoặc vị trí tham số.
- Không dán bí mật vào command line rồi xóa dòng sau khi chạy; history hoặc log có thể đã ghi.
- Không bật shell tracing như `set -x` quanh bước có secret.
- Không giả định một từ khóa như `--token` luôn được shell history filter nhận diện.
- Nếu bí mật đã xuất hiện trong history hoặc log, xử lý như một lần lộ bí mật: thu hồi/rotate và làm sạch nơi lưu theo quy trình vận hành.

## Nhập bí mật có che ký tự trong Spring Shell 3.x

Trong Spring Shell 3.x, `ComponentFlow` có thể ghép nhiều input component thành wizard. `StringInputSpec.maskCharacter('*')` đặt ký tự hiển thị thay cho ký tự người dùng đang nhập. Đây là cách phù hợp để hỏi password hoặc token trong phiên terminal tương tác.

```java
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.stereotype.Component;

@Component
class CredentialPrompt {

    private final ComponentFlow.Builder componentFlowBuilder;

    CredentialPrompt(ComponentFlow.Builder componentFlowBuilder) {
        this.componentFlowBuilder = componentFlowBuilder;
    }

    String readApiToken() {
        ComponentFlow.ComponentFlowResult result = componentFlowBuilder.clone().reset()
                .withStringInput("apiToken")
                    .name("API token")
                    .maskCharacter('*')
                    .and()
                .build()
                .run();

        return result.getContext().get("apiToken", String.class);
    }
}
```

Builder được clone và reset để mỗi lần hỏi tạo một flow mới. `ComponentFlowResult.getContext()` trả context kết quả; `get("apiToken", String.class)` lấy giá trị thật để chuyển cho service xác thực.

Không dùng `getMaskedResultValue()` làm credential gửi tới server. Giá trị đó phục vụ hiển thị đã che. Không in `result`, `ComponentContext`, `StringInputContext` hoặc giá trị trả về trong log/debug; context có thể chứa dữ liệu đầu vào gốc.

### Dùng prompt trong command

Không khai báo password hoặc token thành `@ShellOption`/tham số command. Command chỉ gọi prompt rồi chuyển giá trị cho service:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
class LoginCommands {

    private final CredentialPrompt credentialPrompt;
    private final AuthenticationService authenticationService;

    LoginCommands(
            CredentialPrompt credentialPrompt,
            AuthenticationService authenticationService) {
        this.credentialPrompt = credentialPrompt;
        this.authenticationService = authenticationService;
    }

    @ShellMethod(key = "login", value = "Xác thực với dịch vụ")
    public String login() {
        String token = credentialPrompt.readApiToken();
        authenticationService.authenticate(token);
        return "Đã xác thực thành công.";
    }
}
```

Output chỉ thông báo kết quả, không trả token hoặc một phần token. Nếu xác thực thất bại, exception message cũng không được chứa request header, credential hoặc payload nhạy cảm.

### Che ký tự không phải mã hóa

`maskCharacter('*')` chỉ kiểm soát cách input được render trong terminal. Nó không mã hóa secret, không bảo vệ khỏi keylogger, screen recording, debugger hoặc tiến trình có quyền đọc bộ nhớ. Cũng không được coi masking là cơ chế loại bỏ secret khỏi mọi history/log. Hãy kiểm tra hành vi của terminal provider đang dùng và vẫn tuân thủ nguyên tắc không ghi bí mật.

Trong ví dụ trên, `ComponentFlow` trả về `String`. Java `String` là immutable nên ứng dụng không thể chủ động ghi đè nội dung của đối tượng sau khi dùng. Giữ phạm vi sử dụng ngắn, không lưu vào singleton/cache/session lâu dài và không tạo thêm bản sao không cần thiết. Với yêu cầu bảo vệ bộ nhớ nghiêm ngặt, cân nhắc API đọc password trả về `char[]` hoặc một input adapter tự quản lý buffer; xóa mảng bằng `Arrays.fill(chars, '\0')` trong `finally` sau khi service hoàn tất. Việc xóa mảng giảm thời gian lưu plaintext nhưng không bảo đảm mọi bản sao nội bộ đã biến mất.

## Những cách truyền secret nên dùng

Ưu tiên theo thứ tự phù hợp với môi trường:

| Cách | Khi phù hợp | Điểm cần kiểm soát |
|---|---|---|
| Secret manager và workload identity | CI/CD, container, máy chủ hoặc cloud có danh tính workload | Cấp quyền tối thiểu, lấy secret ngắn hạn, không in giá trị khi truy vấn |
| File secret được orchestrator mount | Docker/Kubernetes hoặc máy chủ có cơ chế mount secret | File không nằm trong image/repository; quyền đọc giới hạn; mount đúng thời gian chạy |
| Prompt che ký tự | Người vận hành đang dùng terminal tương tác | Không bật trong batch; không echo/log; xử lý hủy và lỗi |
| Standard input chuyên biệt | Wrapper cần chuyển secret mà không đưa vào argv/history | Chỉ đọc từ stdin khi caller chọn rõ; không echo; tránh xung đột với stdin dùng cho script |
| Environment variable được inject lúc chạy | Nền tảng CI/container chỉ hỗ trợ cách này | Không hardcode; giới hạn scope/process; không dump environment; rotate khi lộ |

Environment variable tránh việc ghi giá trị trực tiếp trong command line, nhưng không phải secret store. OWASP lưu ý biến môi trường thường có thể được tiến trình khác truy cập và có thể xuất hiện trong log hoặc system dump. Không đưa secret vào Dockerfile `ENV` hoặc `ARG`; dùng orchestrator/secret manager để inject khi chạy nếu chưa thể dùng file mount hoặc fetch in-memory.

## Dùng configuration tree để đọc file secret

Spring Boot 3.4 hỗ trợ `configtree:` để biến file trong một thư mục được mount thành property. Ví dụ orchestrator mount file secret tại `/run/secrets/app.api-token`:

```text
/run/secrets/
└── app.api-token    # nội dung file là token, không phải tên file
```

Khai báo import trong `application.yml`:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

File `app.api-token` tạo property `app.api-token`. Có thể bind vào cấu hình ứng dụng:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppCredentialProperties {

    private String apiToken;

    public String getApiToken() {
        return apiToken;
    }

    public void setApiToken(String apiToken) {
        this.apiToken = apiToken;
    }
}
```

Đăng ký properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(AppCredentialProperties.class)`. Service đọc giá trị từ properties nhưng không đưa nó vào output:

```java
@Service
class RemoteApiClient {

    private final AppCredentialProperties credentials;

    RemoteApiClient(AppCredentialProperties credentials) {
        this.credentials = credentials;
    }

    void callApi() {
        String token = credentials.getApiToken();
        // Gắn token vào Authorization header của HTTP client.
        // Không ghi header hoặc token vào log.
    }
}
```

File secret phải được orchestrator mount ở runtime, có owner và permission phù hợp. Không copy file secret vào source tree, image layer, artifact hoặc thư mục log. `optional:` cho phép ứng dụng khởi động khi thư mục không tồn tại; nếu secret bắt buộc, bỏ `optional:` hoặc kiểm tra property bắt buộc khi khởi động để fail fast.

## Environment variable: phương án dự phòng có giới hạn

Nếu nền tảng chỉ cung cấp secret dưới dạng environment variable, hãy inject từ secret store lúc tạo process thay vì ghi giá trị vào script hoặc file cấu hình. Ví dụ shell chỉ lưu tên secret và lệnh lấy secret trong history:

```bash
APP_API_TOKEN="$(secret-manager read customer-cli/api-token)" \
  java -jar customer-cli.jar sync
```

Không bật `set -x` trong đoạn này và không chạy `env`, `printenv` hoặc lệnh debug dump toàn bộ environment. Secret vẫn có mặt trong environment của process và bộ nhớ của JVM; giới hạn quyền đọc process, tránh dump môi trường và rotate token theo vòng đời ngắn.

Không dùng cách sau trong Dockerfile:

```dockerfile
# Không an toàn: secret có thể bị lưu trong image metadata/layer.
ENV APP_API_TOKEN=eyJhbGciOi...
ARG APP_API_TOKEN=eyJhbGciOi...
```

Tên biến có thể nằm trong cấu hình triển khai, nhưng giá trị phải được cấp bởi secret store/orchestrator khi chạy và không được commit.

## Standard input cho automation

Một CLI có thể định nghĩa option không chứa bí mật để báo rằng secret sẽ đến từ stdin:

```text
java -jar customer-cli.jar login --token-stdin
```

Wrapper đọc secret từ secret manager rồi chuyển trực tiếp vào stdin của process, không đưa giá trị vào argument vector. Ứng dụng cần đọc đúng một secret, không echo lại, không trộn nó vào output và đóng luồng sau khi đọc.

Ví dụ luồng dữ liệu ở mức khái niệm:

```text
Secret manager
      |
      | secret qua pipe
      v
customer-cli.jar login --token-stdin
      |
      +--> AuthenticationService
```

Nếu Spring Shell đang dùng stdin để đọc command hoặc file script, cần thiết kế một kênh riêng cho secret hoặc dùng file mount/config tree. Không giả định stdin luôn rảnh trong mọi runner. Không ghi nội dung pipe ra file tạm nếu không có yêu cầu và biện pháp bảo vệ rõ ràng.

## Những nơi không được ghi secret

Không ghi credential vào:

- `System.out`, `System.err`, `CommandContext.outputWriter()` hoặc kết quả command.
- `log.info`, `log.debug`, exception message, stack context hoặc structured logging fields.
- `toString()` của object chứa credential; record Java tự sinh `toString()` có thể in mọi field.
- HTTP request/response dump, wire log, header debug hoặc tracing span attributes.
- Spring Boot Actuator `env`/`configprops` hoặc endpoint chẩn đoán không được bảo vệ.
- File cấu hình mẫu, README, Dockerfile, compose file, test snapshot hoặc fixture đã commit.

Khi cần audit, ghi ai đã yêu cầu secret, secret identifier nào được truy cập, mục đích, thời điểm, kết quả allow/deny và workload identity. Không ghi giá trị secret. Nếu cần tương quan request, dùng secret ID/version hoặc fingerprint có thiết kế phù hợp, không dùng chính token làm correlation ID.

### Redact dữ liệu trước khi log

Nếu một request object chứa token, tránh log toàn bộ object:

```java
// Không nên: toString() có thể đưa credential vào log.
log.debug("Authentication request: {}", request);

// Nên: chỉ ghi metadata không nhạy cảm.
log.debug("Authenticating accountId={} credentialType={}",
        request.accountId(), request.credentialType());
```

Đừng chỉ dựa vào regex che chuỗi `password=` sau khi log đã được tạo. Cách an toàn hơn là không đưa secret vào log event ngay từ đầu.

## Xử lý secret nếu đã bị lộ

Nếu password/token đã được nhập vào command line, commit vào Git hoặc xuất hiện trong log:

1. Thu hồi hoặc rotate credential ngay theo quy trình của hệ thống đích.
2. Kiểm tra thời điểm, phạm vi và các hệ thống có thể đã nhận bản sao.
3. Hạn chế quyền truy cập vào log/history/artifact liên quan.
4. Xóa hoặc redact bản sao theo chính sách lưu trữ và bảo toàn audit.
5. Kiểm tra truy cập bất thường bằng audit log của secret manager và dịch vụ đích.
6. Cập nhật script/pipeline để lần chạy sau không tái sử dụng cách truyền cũ.

Xóa dòng khỏi history không làm token cũ mất hiệu lực. Hãy rotate/revoke trước, sau đó xử lý các bản sao còn lại.

## Kiểm thử việc không làm lộ bí mật

Kiểm thử cả giao diện và các đường chạy tự động:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Nhập token bằng `ComponentFlow` | Terminal chỉ hiển thị ký tự mask, không hiện token rõ |
| Hoàn tất prompt | Command output không chứa token hoặc một phần token |
| Xác thực thất bại | Exception và log không chứa request header hoặc token |
| Gọi command với `--password`/`--token` | Cú pháp không được hỗ trợ hoặc bị từ chối; secret không nằm trong argv |
| CI lấy secret từ manager | Log pipeline chỉ có tên secret/metadata, không có giá trị |
| Dùng config tree | JVM đọc đúng file mount; file không nằm trong source/image |
| Environment variable fallback | Không có `set -x`, `env` dump hoặc log environment |
| Standard input | Secret không được echo hoặc ghi vào output/file tạm |
| Debug/toString | DTO, exception, tracing và HTTP logging không lộ field bí mật |
| Rotation | Credential cũ bị từ chối sau khi thu hồi/rotate |

Trong test, dùng một chuỗi sentinel giả như `test-secret-do-not-print` rồi kiểm tra output và log capture không chứa chuỗi đó. Không dùng credential thật trong unit test, screenshot, snapshot hoặc báo cáo test.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Token xuất hiện trong `ps` hoặc process monitor | Token được truyền qua option, positional argument hoặc `-D` | Bỏ secret khỏi argv; dùng secret manager, file mount, prompt hoặc stdin |
| Password xuất hiện khi nhấn mũi tên lên | Shell history đã lưu command có secret | Không nhập secret trên command line; rotate nếu đã lộ |
| Input được che nhưng log vẫn có token | Mask chỉ tác động render; code log context/giá trị thật | Không log context, request object hoặc raw value |
| CI log có secret dù command không in | Shell tracing, wrapper hoặc action ghi tham số | Tắt tracing quanh secret, dùng masking của CI như lớp bổ sung và sửa nguồn log |
| Secret nằm trong Docker image | Dùng Dockerfile `ENV`/`ARG` hoặc copy file secret vào image | Inject bằng orchestrator khi runtime hoặc fetch từ secret manager |
| Environment variable bị lộ trong dump | Xem env var như secret store lâu dài | Ưu tiên secret manager/file mount; giới hạn dump/process access và thời gian sống |
| Secret bị in bởi DTO | `toString()`/record chứa field credential | Tách metadata khỏi secret; dùng log allowlist |
| Ứng dụng khởi động dù secret bắt buộc bị thiếu | Dùng `optional:configtree:` mà không validate | Bỏ `optional:` hoặc validate property khi startup |
| ComponentFlow không hỏi password | Builder không đặt `maskCharacter` | Cấu hình `.maskCharacter('*')` và kiểm thử trên terminal mục tiêu |

## Quy trình thiết kế command nhận credential

1. Xác định secret nào thật sự cần thiết và phạm vi quyền tối thiểu của nó.
2. Không khai báo password/token thành command option hoặc positional argument.
3. Với terminal tương tác, dùng `StringInputSpec.maskCharacter(...)` hoặc input reader có masking.
4. Với CI/container, ưu tiên workload identity và secret manager; dùng file mount/config tree nếu phù hợp.
5. Chỉ dùng environment variable khi nền tảng không hỗ trợ cách tốt hơn; inject lúc chạy và giới hạn phạm vi process.
6. Nếu dùng stdin, tạo option không chứa secret để chọn kênh đọc và bảo đảm ứng dụng không echo.
7. Không ghi secret vào output, log, exception, `toString()`, history hoặc tracing.
8. Giữ secret trong bộ nhớ thời gian ngắn; dùng `char[]`/`byte[]` khi API và threat model cho phép.
9. Cấp credential ngắn hạn, quyền tối thiểu và có quy trình rotate/revoke.
10. Kiểm thử bằng sentinel giả trên terminal, CI log capture, process launch và file mount.

Một CLI an toàn không yêu cầu người dùng nhớ cách che giấu password trong command line. Nó cung cấp kênh nhập phù hợp với từng môi trường và giữ secret tách khỏi command syntax, output, log và lịch sử thao tác.

## Tài liệu tham khảo

- [Spring Shell 3.4 — Flow Components](https://docs.spring.io/spring-shell/reference/3.4/components/ui/): component input và `ComponentFlow` để xây dựng luồng nhập tương tác.
- [Spring Shell 3.4 API — BaseStringInput](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/BaseStringInput.html): `StringInputSpec.maskCharacter(Character)` và các thuộc tính input.
- [Spring Shell 3.4.3 API — ComponentFlow.Builder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.Builder.html): builder cho string input và các component flow.
- [Spring Shell 3.4.3 API — ComponentFlowResult](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html): lấy context kết quả từ flow.
- [JLine 3 — Line Reading](https://jline.org/versions/3.x/docs/line-reader/): `LineReader.readLine(...)` hỗ trợ mask character cho input nhạy cảm.
- [Spring Boot 3.4 — Externalized Configuration](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html): thứ tự property sources, command-line precedence và configuration tree `configtree:` cho file secret.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret manager, mounted files, environment-variable risks, xử lý secret trong memory và lifecycle.
- [Microsoft Learn — about_PSReadLine](https://learn.microsoft.com/powershell/module/psreadline/about/about_psreadline?view=powershell-7.4): PSReadLine history file và cơ chế lọc một số command có nội dung nhạy cảm.
