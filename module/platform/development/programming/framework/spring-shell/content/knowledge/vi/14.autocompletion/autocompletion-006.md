# Cấu hình gợi ý giá trị cho mô hình annotation 3.x

Khi người dùng nhập command trong Spring Shell, phím Tab có thể hiển thị các giá trị phù hợp cho option hoặc argument hiện tại. Ví dụ, khi nhập `deploy --environment `, shell có thể gợi ý `dev`, `staging` và `production`; khi nhập `project show --name `, shell có thể gợi ý tên các dự án đang hoạt động.

Trong mô hình annotation legacy của Spring Shell 3.x, cơ chế gợi ý giá trị cho tham số được cấu hình bằng `ValueProvider` và thuộc tính `valueProvider` của `@ShellOption`. Provider nhận `CompletionContext` và trả về danh sách `CompletionProposal`. Spring Shell gọi provider khi người dùng yêu cầu hoàn thành trong shell tương tác.

Bài học tập trung vào cách gắn provider vào tham số, đăng ký provider thành Spring bean, dùng provider có sẵn cho enum và file, tự xây dựng gợi ý động từ dữ liệu ứng dụng, và kiểm thử kết quả. Nội dung cũng phân biệt gợi ý giá trị với validation, chuyển đổi kiểu và completion của shell hệ điều hành.

## 1. Gợi ý giá trị giúp người dùng nhập đúng tham số

Một command có thể nhận các giá trị thuộc một tập hợp đã biết:

~~~text
deploy --environment staging
report export --format csv
project show --name inventory-api
~~~

Nếu người dùng phải nhớ mọi giá trị, họ có thể nhập sai tên môi trường, định dạng hoặc tài nguyên. Completion giảm thao tác ghi nhớ bằng cách hiển thị các lựa chọn phù hợp với vị trí con trỏ hiện tại.

Ví dụ, khi nhập:

~~~text
shell:> deploy --environment <TAB>
~~~

Shell có thể đưa ra:

~~~text
dev
staging
production
~~~

Khi nhập:

~~~text
shell:> report export --format <TAB>
~~~

Shell có thể đưa ra:

~~~text
csv
json
xml
~~~

Completion cải thiện khả năng khám phá command và giá trị tham số. Nó không tự bảo đảm giá trị được chọn hợp lệ hoặc người dùng có quyền sử dụng giá trị đó. Command vẫn cần validation và kiểm tra nghiệp vụ khi thực thi.

## 2. Các thành phần của completion trong Spring Shell 3.x

Trong mô hình annotation legacy, các kiểu quan trọng thuộc package `org.springframework.shell` và `org.springframework.shell.standard`:

| Thành phần | Package | Vai trò |
|---|---|---|
| `ValueProvider` | `org.springframework.shell.standard` | Hợp đồng tạo gợi ý cho tham số |
| `CompletionContext` | `org.springframework.shell` | Cung cấp ngữ cảnh dòng lệnh tại vị trí Tab |
| `CompletionProposal` | `org.springframework.shell` | Biểu diễn một giá trị được đề xuất |
| `@ShellOption` | `org.springframework.shell.standard` | Gắn provider vào tham số |
| `@ShellMethod` | `org.springframework.shell.standard` | Khai báo command method |

Hợp đồng `ValueProvider` rất nhỏ:

~~~java
public interface ValueProvider {

    List<CompletionProposal> complete(
            CompletionContext completionContext);
}
~~~

Spring Shell truyền `CompletionContext` cho phương thức `complete`. Provider trả về danh sách `CompletionProposal` tương ứng với vị trí người dùng đang nhập.

Luồng xử lý tổng quát:

~~~mermaid
flowchart TD
    A["Người dùng nhấn Tab"] --> B["Spring Shell tạo CompletionContext"]
    B --> C["Xác định tham số và ValueProvider"]
    C --> D["Gọi complete(context)"]
    D --> E["Provider tạo CompletionProposal"]
    E --> F["JLine hiển thị các lựa chọn"]
    F --> G["Người dùng chọn hoặc tiếp tục nhập"]
    G --> H["Command nhận giá trị khi thực thi"]
~~~

Với command khai báo bằng annotation, provider được chỉ định trực tiếp trên `@ShellOption` của tham số cần gợi ý.

## 3. Gắn ValueProvider vào @ShellOption

Giả sử command triển khai nhận tên môi trường:

~~~java
@ShellComponent
public class DeploymentCommands {

    @ShellMethod(value = "Deploy the application.", key = "deploy")
    public String deploy(
            @ShellOption(
                    value = "--environment",
                    valueProvider = EnvironmentValueProvider.class)
            String environment) {

        return "Deploying to " + environment;
    }
}
~~~

Thuộc tính `valueProvider` nhận class triển khai `ValueProvider`. Khi người dùng hoàn thành giá trị của option `--environment`, Spring Shell sử dụng provider được khai báo để lấy danh sách gợi ý.

Provider đơn giản có thể trả về một tập giá trị cố định:

~~~java
@Component
public class EnvironmentValueProvider implements ValueProvider {

    @Override
    public List<CompletionProposal> complete(
            CompletionContext completionContext) {

        return List.of(
                new CompletionProposal("dev"),
                new CompletionProposal("staging"),
                new CompletionProposal("production"));
    }
}
~~~

Các import chính:

~~~java
import java.util.List;

import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;
import org.springframework.stereotype.Component;
~~~

`ValueProvider` tùy chỉnh dùng với annotation-based command phải là Spring bean. Có thể đăng ký bằng `@Component` như ví dụ hoặc bằng `@Bean`; nếu dùng `@Bean`, bảo đảm kiểu bean khớp với class được tham chiếu trong `valueProvider` và không đăng ký trùng cùng một provider.

## 4. Dùng provider có sẵn cho enum và file

Spring Shell 3.x cung cấp một số implementation `ValueProvider` để phục vụ các kiểu dữ liệu phổ biến.

### 4.1. EnumValueProvider

`EnumValueProvider` tạo gợi ý từ các hằng số của enum. Ví dụ:

~~~java
public enum ReportFormat {
    CSV,
    JSON,
    XML
}
~~~

Khai báo command:

~~~java
@ShellComponent
public class ReportCommands {

    @ShellMethod(value = "Export a report.", key = "report export")
    public String export(
            @ShellOption(
                    value = "--format",
                    valueProvider = EnumValueProvider.class)
            ReportFormat format) {

        return "Export format: " + format;
    }
}
~~~

Provider có thể gợi ý các giá trị enum `CSV`, `JSON` và `XML`. Tham số method vẫn có kiểu `ReportFormat`, vì vậy Spring Shell còn phải chuyển đổi giá trị đã chọn thành enum khi command được thực thi.

Nếu ứng dụng yêu cầu cách viết khác, chẳng hạn `csv` thay vì `CSV`, hãy xác định rõ quy tắc chuyển đổi và kiểm thử với phiên bản đang sử dụng. Gợi ý hiển thị và quy tắc chuyển đổi kiểu là hai việc liên quan nhưng không đồng nhất.


Trong cấu hình chuẩn Spring Shell 3.1, `StandardAPIAutoConfiguration` đã đăng ký sẵn bean cho `EnumValueProvider` và `FileValueProvider`. Khi dùng Spring Shell starter cùng auto-configuration mặc định, có thể tham chiếu trực tiếp các class này trong `@ShellOption`; không cần tự tạo thêm bean cùng loại. Nếu ứng dụng tắt hoặc thay thế standard API auto-configuration, hãy kiểm tra lại các bean provider có mặt hay không.

### 4.2. FileValueProvider

`FileValueProvider` gợi ý tên các file và thư mục trên máy cục bộ, có thể là đường dẫn tuyệt đối hoặc tương đối với working directory hiện tại.

Ví dụ:

~~~java
@ShellComponent
public class ImportCommands {

    @ShellMethod(value = "Import data from a file.", key = "data import")
    public String importData(
            @ShellOption(
                    value = "--file",
                    valueProvider = FileValueProvider.class)
            File file) {

        return "Importing " + file.getPath();
    }
}
~~~

Khi người dùng nhập `data import --file ` rồi nhấn Tab, provider có thể gợi ý các file và thư mục phù hợp từ filesystem cục bộ.

File completion không thay thế kiểm tra đường dẫn. Khi thực thi, command vẫn cần kiểm tra file tồn tại, định dạng có được hỗ trợ và người dùng có quyền đọc file hay không.

### 4.3. CommandValueProvider

`CommandValueProvider` tạo gợi ý từ tên các command đã đăng ký trong `CommandCatalog`. Provider này hữu ích khi một tham số cần nhận tên command, chẳng hạn command dùng để chạy một tác vụ hoặc tạo shortcut.

`StandardAPIAutoConfiguration` cũng đăng ký sẵn `CommandValueProvider` dưới dạng bean và inject `CommandCatalog` đang được shell sử dụng. Vì vậy, trong cấu hình mặc định của Spring Shell 3.1, có thể dùng trực tiếp `CommandValueProvider.class` trong `@ShellOption`. Không tự tạo một `CommandCatalog` riêng để cấp dữ liệu cho provider, vì danh sách command khi đó có thể không phản ánh catalog thực tế của shell.

## 5. Tạo provider động từ dữ liệu ứng dụng

Các giá trị gợi ý thường thay đổi theo dữ liệu hiện tại. Ví dụ, command `project show` chỉ nên gợi ý những dự án người dùng có thể truy cập hoặc đang hoạt động.

Ta có thể inject service vào provider và truy vấn danh sách phù hợp khi cần.

Giả sử service trả về các lựa chọn:

~~~java
import java.util.List;
import java.util.Locale;

import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;
import org.springframework.stereotype.Component;
~~~

~~~java
public record ProjectChoice(String name, String code) {
}
~~~

~~~java
public interface ProjectQueryService {

    List<ProjectChoice> findActiveProjectsByPrefix(String prefix, int limit);
}
~~~

Provider:

~~~java
@Component
public class ProjectNameValueProvider implements ValueProvider {

    private final ProjectQueryService projectQueryService;

    public ProjectNameValueProvider(
            ProjectQueryService projectQueryService) {
        this.projectQueryService = projectQueryService;
    }

    @Override
    public List<CompletionProposal> complete(
            CompletionContext completionContext) {

        String prefix = completionContext.currentWordUpToCursor();
        if (prefix == null) {
            prefix = "";
        }

        String normalizedPrefix = prefix.toLowerCase(Locale.ROOT);

        return projectQueryService.findActiveProjectsByPrefix(normalizedPrefix, 20).stream()
                .map(project -> new CompletionProposal(project.name())
                        .description(project.code())
                        .category("Project"))
                .toList();
    }
}
~~~

Gắn provider vào tham số:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod(value = "Show a project.", key = "project show")
    public String show(
            @ShellOption(
                    value = "--name",
                    valueProvider = ProjectNameValueProvider.class)
            String projectName) {

        return "Showing project " + projectName;
    }
}
~~~

Khi người dùng nhập:

~~~text
shell:> project show --name inven<TAB>
~~~

Provider đọc phần văn bản tại con trỏ, lọc các dự án có tên bắt đầu bằng `inven` và trả về tối đa 20 gợi ý.

Ví dụ này minh họa các thao tác thường gặp:

- Inject service để lấy dữ liệu.
- Dùng `currentWordUpToCursor()` để đọc phần người dùng đang nhập.
- Gửi prefix và giới hạn kết quả xuống service để truy vấn hiệu quả.
- Dùng `description` và `category` để cung cấp thêm ngữ cảnh cho từng lựa chọn.

Trong ứng dụng thật, service nên lọc theo prefix và giới hạn kết quả ngay tại nguồn dữ liệu, đồng thời áp dụng cùng phạm vi dữ liệu và quyền truy cập của người dùng hiện tại. Không nên gợi ý tên tài nguyên mà người dùng không được phép xem.

## 6. Đọc CompletionContext

`CompletionContext` mô tả trạng thái dòng nhập tại thời điểm completion được yêu cầu. API Spring Shell 3.1.x cung cấp các thông tin quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| `getWords()` | Các từ trong buffer, không bao gồm tên command |
| `getWordIndex()` | Chỉ số từ hiện tại |
| `getPosition()` | Vị trí con trỏ bên trong từ hiện tại |
| `currentWord()` | Toàn bộ từ đang chứa con trỏ; có thể là `null` nếu con trỏ ở sau từ cuối |
| `currentWordUpToCursor()` | Phần từ từ đầu token đến vị trí con trỏ |
| `upToCursor()` | Nội dung buffer đến vị trí con trỏ |
| `getCommandRegistration()` | Registration của command hiện tại |
| `getCommandOption()` | Metadata option hiện tại nếu completion đang ở ngữ cảnh option |
| `drop(int)` | Tạo context mới sau khi bỏ một số từ đầu |

Ví dụ, với dòng đang nhập:

~~~text
project show --name inven
~~~

Provider có thể dùng `currentWordUpToCursor()` để lấy `inven`. Nếu người dùng đặt con trỏ giữa token, giá trị này chỉ phản ánh phần trước con trỏ, giúp provider lọc gợi ý phù hợp với vị trí đang sửa.

Không nên giả định `getCommandOption()` luôn khác `null` trong mọi ngữ cảnh. Provider cần kiểm tra ngữ cảnh trước khi đọc metadata option, nhất là khi logic được dùng chung hoặc được gọi từ nhiều vị trí.

## 7. Tùy biến CompletionProposal

Mỗi gợi ý được biểu diễn bằng `CompletionProposal`. Constructor nhận giá trị sẽ được chèn vào dòng lệnh:

~~~java
new CompletionProposal("staging")
~~~

Có thể bổ sung metadata:

~~~java
CompletionProposal proposal =
        new CompletionProposal("production")
                .displayText("production")
                .description("Môi trường triển khai chính thức")
                .category("Environment");
~~~

Các thuộc tính thường dùng:

| Thuộc tính | Vai trò |
|---|---|
| `value` | Nội dung đề xuất được dùng để hoàn thành |
| `displayText` | Văn bản hiển thị cho người dùng |
| `description` | Mô tả bổ sung |
| `category` | Nhóm phân loại đề xuất |
| `complete` | Metadata cho biết trạng thái hoàn thành của đề xuất |
| `dontQuote` | Điều khiển việc không tự thêm dấu nháy cho đề xuất |

Ví dụ dùng tên hiển thị khác với giá trị được chèn:

~~~java
return List.of(
        new CompletionProposal("prod")
                .displayText("production")
                .description("Production environment")
                .category("Environment"));
~~~

Khi cần gợi ý đường dẫn hoặc giá trị chứa khoảng trắng, hãy kiểm tra cách shell quote proposal trên parser thực tế. Không đặt dấu nháy thủ công trong `value` nếu chưa xác định rõ quy tắc quoting, vì shell có thể tự xử lý việc này.

## 8. Nhiều lựa chọn và logic theo ngữ cảnh

Một command có thể có nhiều option, mỗi option cần tập gợi ý riêng:

~~~java
@ShellComponent
public class DeploymentCommands {

    @ShellMethod(value = "Deploy an application.", key = "deploy")
    public String deploy(
            @ShellOption(
                    value = "--environment",
                    valueProvider = EnvironmentValueProvider.class)
            String environment,
            @ShellOption(
                    value = "--region",
                    valueProvider = RegionValueProvider.class)
            String region) {

        return "Deploying to " + environment + " in " + region;
    }
}
~~~

Mỗi tham số gắn với một `ValueProvider` riêng. Đây là cách rõ ràng khi các danh sách gợi ý độc lập.

Nếu gợi ý của option thứ hai phụ thuộc vào option thứ nhất, provider có thể đọc `CompletionContext` và metadata command để xác định ngữ cảnh hiện tại. Tuy nhiên, không nên dựa vào dữ liệu chưa được phân tích hoặc giả định mọi option trước đó luôn có mặt. Hãy xử lý trường hợp người dùng chưa nhập option phụ thuộc và trả về danh sách rỗng hoặc danh sách mặc định phù hợp.

Ví dụ, danh sách region có thể thay đổi theo environment:

- `dev`: `local`, `dev-east`.
- `staging`: `stage-east`, `stage-west`.
- `production`: `prod-east`, `prod-west`.

Provider cần đọc được giá trị environment từ ngữ cảnh đã có theo API của phiên bản đang sử dụng. Nếu không có đủ thông tin, trả về lựa chọn chung hoặc không đưa ra gợi ý thay vì suy đoán.

## 9. Phân biệt completion của tham số với completion của command

Spring Shell 3.x có nhiều cơ chế completion:

| Cơ chế | Mục đích | Cách cấu hình |
|---|---|---|
| `ValueProvider` | Gợi ý giá trị của một tham số | `@ShellOption(valueProvider = ...)` |
| `CompletionResolver` | Gợi ý dùng chung cho nhiều command | Đăng ký resolver bean |
| Completion trên `CommandRegistration` | Gợi ý option trong command đăng ký bằng builder | Cấu hình completion trên option |
| `CommandValueProvider` | Gợi ý tên command | Dùng catalog command |
| Completion command của OS shell | Gợi ý khi nhập lệnh trực tiếp trong Bash | Tạo và nạp script completion |

Trong bài này, trọng tâm là `ValueProvider` cho annotation legacy. Không nên nhầm nó với `CompletionResolver` toàn cục hoặc completion của shell hệ điều hành.

Spring Shell 3.1 có cả mô hình annotation legacy và mô hình annotation mới. Thuộc tính `valueProvider` nằm trên `@ShellOption` của mô hình legacy. Annotation `@Command` mới trong 3.1 không có thuộc tính tương đương; nếu đăng ký command theo mô hình mới bằng `CommandRegistration`, có thể cấu hình completion trực tiếp trên option bằng builder `.completion(...)`. API completion cấp command của Spring Shell 4.x là một thiết kế khác, không áp dụng nguyên trạng cho annotation 3.x.

### 9.1. CompletionResolver dùng chung

Một resolver tổng quát có thể được đăng ký thành bean để bổ sung gợi ý dùng chung cho nhiều tình huống. Spring Shell 3.x có `CompletionResolver`, một interface dựa trên `CompletionContext` và trả về danh sách `CompletionProposal`.

Ví dụ khái quát:

~~~java
import java.util.List;

import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.completion.CompletionResolver;
import org.springframework.stereotype.Component;

@Component
public class CommonValueCompletionResolver implements CompletionResolver {

    @Override
    public List<CompletionProposal> apply(
            CompletionContext completionContext) {

        return List.of(
                new CompletionProposal("yes"),
                new CompletionProposal("no"));
    }
}
~~~

Resolver dùng chung phù hợp với logic hoàn thành có thể áp dụng trên phạm vi rộng. Nếu chỉ một tham số cần danh sách riêng, `ValueProvider` gắn trực tiếp trên `@ShellOption` dễ hiểu và dễ bảo trì hơn.

### 9.2. Completion của shell hệ điều hành

Completion trong prompt Spring Shell sử dụng JLine và có thể gọi `ValueProvider` khi người dùng nhấn Tab.

Completion khi người dùng nhập lệnh trực tiếp trong Bash là một cơ chế khác. Spring Shell 3.x cung cấp command tích hợp `completion` để tạo script cho Bash. Tài liệu 3.1.x mô tả Bash là implementation command-line completion được hỗ trợ tại thời điểm đó.

Vì vậy:

- `ValueProvider` phục vụ gợi ý giá trị trong phiên shell tương tác.
- Script completion của Bash phục vụ gợi ý ở prompt Bash trước khi command được gửi tới tiến trình.
- Khi chạy file script không tương tác, người dùng thường cung cấp giá trị trực tiếp; không có thao tác nhấn Tab trong quá trình thực thi script.

## 10. Thiết kế provider hiệu quả và an toàn

Provider có thể được gọi nhiều lần khi người dùng di chuyển con trỏ hoặc tiếp tục nhập. Vì vậy, việc tạo gợi ý cần nhanh, có giới hạn và không tạo tác dụng phụ.

### 10.1. Giới hạn số lượng gợi ý

Không trả về hàng nghìn lựa chọn cùng lúc. Hãy lọc theo prefix và giới hạn kết quả:

~~~java
return service.findCandidates(prefix).stream()
        .limit(20)
        .map(CompletionProposal::new)
        .toList();
~~~

Nếu dữ liệu lớn, service nên truy vấn theo prefix và giới hạn ngay tại nguồn dữ liệu thay vì tải toàn bộ danh sách rồi mới lọc trong Java.

### 10.2. Tránh thao tác chậm hoặc có tác dụng phụ

Không nên:

- Thực hiện transaction ghi dữ liệu trong provider.
- Gọi API mạng không có timeout.
- Quét toàn bộ filesystem mỗi lần nhấn Tab.
- Tạo kết nối mới chỉ để lấy gợi ý.
- Thực hiện cập nhật trạng thái nghiệp vụ.

Nếu dữ liệu gợi ý đến từ dịch vụ bên ngoài, hãy dùng cache hoặc một nguồn dữ liệu đã được cập nhật có kiểm soát. Provider chỉ nên đọc dữ liệu và tạo đề xuất.

### 10.3. Không tiết lộ dữ liệu nhạy cảm

Danh sách gợi ý cũng là một dạng hiển thị dữ liệu. Không đưa vào completion:

- Tài nguyên người dùng không có quyền xem.
- Token, mật khẩu hoặc secret.
- Đường dẫn nội bộ không được phép tiết lộ.
- Tên tài khoản hoặc dữ liệu cá nhân không liên quan.

Áp dụng cùng phạm vi quyền truy cập cho completion và command thực thi. Dù provider chỉ gợi ý, command vẫn cần xác minh quyền khi nhận giá trị.

### 10.4. Provider nên stateless

Một `ValueProvider` thường được quản lý như Spring bean và có thể được dùng lại. Không lưu prefix hoặc kết quả của lần gọi trước trong field mutable. Hãy dùng biến cục bộ trong `complete()` để tránh dữ liệu giữa các lần gọi ảnh hưởng lẫn nhau.

## 11. Completion không thay thế validation và conversion

Gợi ý chỉ giúp người dùng chọn giá trị. Người dùng vẫn có thể nhập thủ công một giá trị không nằm trong danh sách.

Ví dụ, provider gợi ý:

~~~text
dev
staging
production
~~~

Nhưng người dùng vẫn có thể nhập:

~~~text
deploy --environment test
~~~

Do đó, command hoặc service cần kiểm tra `test` có được hỗ trợ hay không.

Cần phân biệt:

| Cơ chế | Trách nhiệm |
|---|---|
| Completion | Gợi ý giá trị có thể nhập |
| Conversion | Chuyển chuỗi sang kiểu Java |
| Validation | Kiểm tra định dạng và ràng buộc đầu vào |
| Authorization | Xác minh người dùng có quyền thao tác |
| Business logic | Thực hiện nghiệp vụ với dữ liệu đã được kiểm tra |

Không nên xem danh sách completion là whitelist bảo mật. Danh sách gợi ý có thể thay đổi hoặc không đầy đủ, và lệnh vẫn phải tự bảo vệ ở phía thực thi.

## 12. Kiểm thử ValueProvider

Provider nên được kiểm thử độc lập trước, sau đó kiểm thử tích hợp với Spring Shell.

### 12.1. Unit test

Ví dụ kiểm tra provider tĩnh:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;

import static org.assertj.core.api.Assertions.assertThat;

class EnvironmentValueProviderTests {

    private final EnvironmentValueProvider provider =
            new EnvironmentValueProvider();

    @Test
    void returnsKnownEnvironments() {
        CompletionContext context = new CompletionContext(
                List.of(""), 0, 0, null, null);
        List<CompletionProposal> proposals =
                provider.complete(context);

        assertThat(proposals)
                .extracting(CompletionProposal::value)
                .contains("dev", "staging", "production");
    }
}
~~~

Constructor của `CompletionContext` nhận danh sách từ trong buffer (không gồm tên command), chỉ số từ, vị trí con trỏ, command registration và option hiện tại. Test trên dùng context tối thiểu vì provider tĩnh không đọc metadata command. Với provider phụ thuộc option hoặc prefix, hãy tạo context có dữ liệu tương ứng và kiểm tra cả prefix rỗng lẫn prefix đã nhập.

### 12.2. Kiểm thử provider động

Với provider sử dụng service, mock service để kiểm tra:

- Chỉ các tài nguyên đang hoạt động được đề xuất.
- Prefix lọc đúng.
- Số lượng kết quả không vượt quá giới hạn.
- Danh sách rỗng khi không có kết quả.
- Không trả về tài nguyên ngoài phạm vi quyền.
- Service lỗi được xử lý theo chính sách phù hợp.

### 12.3. Kiểm thử tích hợp trong shell

Kiểm thử tích hợp cần xác minh:

1. `@ShellComponent` được phát hiện.
2. Command method được đăng ký.
3. `@ShellOption` tham chiếu đúng provider class.
4. Provider đã có bean trong ApplicationContext.
5. Completion được gọi cho đúng tham số.
6. Proposal hiển thị đúng giá trị và metadata.
7. Giá trị được chọn vẫn đi qua conversion và validation khi thực thi.

Unit test gọi trực tiếp `complete()` chưa chứng minh Spring Shell đã kết nối provider với tham số. Cần có test cho cấu hình annotation thực tế hoặc kiểm tra thủ công bằng Tab trong prompt.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Nhấn Tab không có gợi ý | Provider chưa được đăng ký thành bean | Dùng `@Component` hoặc `@Bean` |
| Gợi ý xuất hiện ở sai tham số | Gắn `valueProvider` nhầm `@ShellOption` | Kiểm tra annotation trên từng tham số |
| Provider trả danh sách nhưng shell không dùng | Class provider không được Spring quản lý đúng cách | Kiểm tra ApplicationContext và component scan |
| Provider luôn trả danh sách cũ | Đang cache dữ liệu không cập nhật | Xác định chính sách refresh hoặc cache |
| Gợi ý quá nhiều | Không lọc prefix hoặc giới hạn số lượng | Lọc theo input và đặt giới hạn |
| Gợi ý chậm | Provider truy vấn dữ liệu lớn hoặc gọi dịch vụ mạng | Tối ưu truy vấn, timeout hoặc cache |
| Giá trị gợi ý không thực thi được | Completion không khớp với conversion hoặc validation | Kiểm tra cả pipeline thực thi |
| File provider không thấy file | Working directory khác với dự kiến | Kiểm tra thư mục làm việc và quyền |
| Enum gợi ý khác kiểu chữ mong muốn | Enum constant và quy tắc convert không đồng nhất | Chuẩn hóa quy tắc hiển thị và conversion |
| Bash không có completion | Chưa tạo hoặc nạp script completion | Dùng command tích hợp `completion bash` theo tài liệu phiên bản |

## 14. Bài thực hành: gợi ý môi trường và dự án

Xây dựng ứng dụng Spring Shell 3.x có command:

~~~text
deploy --environment <value> --project <name>
~~~

Yêu cầu:

1. Tạo `EnvironmentValueProvider` trả về `dev`, `staging`, `production`.
2. Gắn provider vào option `--environment` bằng `@ShellOption(valueProvider = ...)`.
3. Tạo `ProjectNameValueProvider` lấy dự án đang hoạt động từ `ProjectQueryService`.
4. Lọc gợi ý dự án theo prefix người dùng đã nhập.
5. Giới hạn tối đa 20 kết quả.
6. Bổ sung `description` hoặc `category` cho từng proposal.
7. Đăng ký cả hai provider thành Spring bean.
8. Kiểm thử provider với prefix rỗng và prefix cụ thể.
9. Kiểm thử command vẫn từ chối environment không hợp lệ.
10. Thử nhấn Tab trong shell tương tác để xác nhận trải nghiệm.

Kịch bản mong đợi:

~~~text
shell:> deploy --environment <TAB>
dev
staging
production

shell:> deploy --project inven<TAB>
inventory-api
inventory-worker

shell:> deploy --environment production --project inventory-api
Deploying inventory-api to production
~~~

Bổ sung kiểm tra quyền để provider chỉ gợi ý dự án người dùng hiện tại được phép triển khai.

## 15. Checklist cấu hình completion

- [ ] Xác định đúng mô hình annotation legacy 3.x đang dùng.
- [ ] Khai báo command bằng `@ShellComponent` và `@ShellMethod`.
- [ ] Gắn `valueProvider` trên đúng `@ShellOption`.
- [ ] Provider triển khai `ValueProvider.complete(CompletionContext)`.
- [ ] Provider trả về `List<CompletionProposal>`.
- [ ] Provider được đăng ký thành Spring bean.
- [ ] Sử dụng `EnumValueProvider` hoặc `FileValueProvider` khi phù hợp.
- [ ] Đọc prefix và vị trí con trỏ từ `CompletionContext`.
- [ ] Lọc và giới hạn số lượng proposal.
- [ ] Bổ sung display text, description hoặc category khi cần.
- [ ] Giữ provider nhanh, stateless và không có tác dụng phụ.
- [ ] Không gợi ý dữ liệu người dùng không có quyền xem.
- [ ] Kiểm tra giá trị được chọn qua conversion và validation.
- [ ] Phân biệt completion trong REPL với completion của Bash.
- [ ] Có unit test và integration test cho provider.

## 16. Kết luận

Trong mô hình annotation legacy của Spring Shell 3.x, gợi ý giá trị cho tham số được cấu hình bằng `@ShellOption(valueProvider = ...)`. Class provider triển khai `ValueProvider`, nhận `CompletionContext` và trả về các `CompletionProposal`. Provider phải được đăng ký thành Spring bean để Spring Shell có thể sử dụng khi người dùng nhấn Tab.

Có thể dùng `EnumValueProvider` cho enum, `FileValueProvider` cho file cục bộ hoặc tự xây dựng provider động từ service của ứng dụng. Provider nên lọc theo prefix, giới hạn số lượng kết quả, phản hồi nhanh và tôn trọng phạm vi quyền truy cập.

Completion chỉ hỗ trợ nhập liệu. Giá trị được chọn vẫn phải đi qua conversion, validation, authorization và business logic trước khi command thực hiện hành động. Hãy kiểm thử cả provider độc lập lẫn tích hợp trong shell để bảo đảm gợi ý hiển thị đúng tại tham số cần thiết.

## Tài liệu tham khảo

- [Spring Shell 3.1.0 Reference: Completion](https://docs.spring.io/spring-shell/docs/3.1.0/docs/index.html)
- [Spring Shell 3.1.6 Reference: Completion](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: `ValueProvider`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ValueProvider.html)
- [Spring Shell 3.1 API: `CompletionResolver`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/completion/CompletionResolver.html)
- [Spring Shell 3.1 API: `ShellOption`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellOption.html)
- [Spring Shell 3.1 API: `CompletionContext`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/CompletionContext.html)
- [Spring Shell 3.1 API: `CompletionProposal`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/CompletionProposal.html)
- [Spring Shell 3.1 API: `EnumValueProvider`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/EnumValueProvider.html)
- [Spring Shell 3.1 API: `FileValueProvider`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/FileValueProvider.html)
- [Spring Shell 3.1 API: `CommandValueProvider`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/CommandValueProvider.html)
- [Spring Shell 3.1 API: `StandardAPIAutoConfiguration`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/boot/StandardAPIAutoConfiguration.html)
- [Spring Shell 3.4 Reference: Completion](https://docs.spring.io/spring-shell/reference/completion.html)
- [Spring Shell v4 Migration Guide: Command completion](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

