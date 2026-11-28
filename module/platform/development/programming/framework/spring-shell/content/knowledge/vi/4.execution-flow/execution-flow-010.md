# Điểm mở rộng cần phân biệt với logic riêng của một lệnh

Spring Shell cung cấp các điểm mở rộng để ứng dụng điều chỉnh cách command được nhận diện, kiểm tra điều kiện sử dụng, gợi ý đầu vào, phân tích cú pháp và báo lỗi. Những điểm mở rộng này thuộc về hạ tầng CLI. Logic nghiệp vụ của một lệnh vẫn nên nằm trong method command và các service mà method đó gọi.

Phân biệt đúng hai phần giúp ứng dụng dễ kiểm thử và thay đổi. Một **CompletionProvider** có thể đề xuất môi trường triển khai, nhưng không nên triển khai ứng dụng. Một **AvailabilityProvider** có thể kiểm tra cấu hình đã sẵn sàng, nhưng không nên thực hiện kết nối tốn thời gian. Một **ExitStatusExceptionMapper** có thể đổi exception thành mã thoát, nhưng không nên quyết định nghiệp vụ thay cho service.

Bài này sử dụng API của Spring Shell 4.x, với các tên kiểu thuộc package **org.springframework.shell.core**. Một số API ở dòng 3.x có tên hoặc package khác; không trộn ví dụ của hai dòng phiên bản trong cùng một lớp mã nguồn.

## 1. Hai loại trách nhiệm trong một ứng dụng CLI

Một command thường có ba phần:

1. **Khai báo giao diện lệnh:** tên, mô tả, help, option, argument, giá trị mặc định và ràng buộc đầu vào.
2. **Điểm mở rộng của shell:** những callback hoặc thành phần mà framework gọi để quyết định command có sẵn không, gợi ý gì khi nhấn Tab, phân tích chuỗi theo quy tắc nào hoặc chuyển exception thành mã thoát nào.
3. **Logic ứng dụng:** công việc người dùng thực sự yêu cầu, chẳng hạn tạo bản sao lưu, triển khai phiên bản, nhập dữ liệu hoặc kiểm tra trạng thái nghiệp vụ.

Ví dụ, lệnh **deploy** có thể nhận **--environment** và **--version**. Spring Shell phân tích hai giá trị này, kiểm tra ràng buộc đầu vào rồi gọi method command. Method command chuyển yêu cầu cho **DeploymentService**. Service kiểm tra quyền, trạng thái triển khai, chính sách phát hành và thực hiện công việc. Provider của shell chỉ bổ sung thông tin để CLI hoạt động thuận tiện và nhất quán.

| Trách nhiệm | Câu hỏi cần trả lời | Nơi nên đặt |
|---|---|---|
| Khai báo command | Lệnh tên gì, có option nào, help ra sao? | **@Command**, **@Option**, **@Argument** |
| Availability | Lúc này người dùng có thể gọi lệnh không? | **AvailabilityProvider** |
| Completion | Khi người dùng nhấn Tab, nên gợi ý giá trị nào? | **CompletionProvider** |
| Validation đầu vào | Giá trị có đúng định dạng và giới hạn khai báo không? | Bean Validation trên tham số |
| Exception mapping | Exception này tương ứng với thông báo và mã thoát nào? | **ExitStatusExceptionMapper** |
| Cấu trúc toàn bộ command | Ứng dụng cần thêm hoặc gỡ command nào? | **CommandRegistryCustomizer**, **CommandRegistry** |
| Cú pháp đầu vào | Chuỗi người dùng nhập được phân tích theo quy tắc nào? | **CommandParser** |
| Nghiệp vụ | Có được phép triển khai không, triển khai ra sao? | Command adapter và application/domain service |

Không phải mọi thành phần trong bảng đều là extension point cùng cấp. **@Command** và các annotation tham số mô tả một command; provider là callback mà command có thể gắn vào; **CommandParser** và **CommandRegistryCustomizer** tác động đến cấu hình của ứng dụng shell rộng hơn.

## 2. Luồng thực thi và vị trí của các điểm mở rộng

Trong Spring Shell 4, runner nhận đầu vào, parser tạo cấu trúc **ParsedInput**, registry tìm command tương ứng và executor điều phối việc thực thi. Khi command được gọi, **CommandContext** cung cấp dữ liệu đã phân tích, registry, bộ đọc đầu vào và bộ ghi đầu ra.

~~~mermaid
flowchart TD
    A["ShellRunner nhận một dòng lệnh"] --> B["CommandParser"]
    B --> C["ParsedInput"]
    C --> D["CommandRegistry tìm command"]
    D --> E{"AvailabilityProvider"}
    E -->|Chưa sẵn sàng| F["Thông báo lý do không khả dụng"]
    E -->|Sẵn sàng| G["Ánh xạ tham số và Bean Validation"]
    G --> H["Command method hoặc Command.execute"]
    H --> I["Application service"]
    I --> J{"Kết quả"}
    J -->|Thành công| K["Hiển thị output và ExitStatus"]
    J -->|Ném exception| L["ExitStatusExceptionMapper"]
    L --> M["Thông báo lỗi và mã thoát"]
    N["Người dùng nhấn Tab"] --> O["CompletionProvider"]
    O --> P["CompletionProposal"]
~~~

Completion là nhánh hỗ trợ lúc người dùng đang soạn lệnh. Nó thường được gọi khi nhấn Tab trong JLine-based shell, trước khi command được thực thi. Availability được kiểm tra khi shell cần xác định command có thể chạy trong trạng thái hiện tại hay không. Bean Validation kiểm tra tham số trước khi method command được gọi. Exception mapper chỉ tham gia khi quá trình thực thi ném exception.

Sơ đồ mô tả trách nhiệm logic, không cam kết mọi thao tác nội bộ đều diễn ra theo đúng một thứ tự triển khai bất biến ở mọi phiên bản. Khi cần dựa vào chi tiết vòng đời, hãy đối chiếu tài liệu API của phiên bản Spring Shell mà ứng dụng đang sử dụng.

## 3. Các điểm mở rộng gắn với một command

### 3.1. AvailabilityProvider: kiểm tra điều kiện sẵn sàng

Một command có thể đã được đăng ký nhưng chưa phù hợp để chạy. Ví dụ, **download** chỉ có ý nghĩa sau khi người dùng kết nối đến máy chủ. **AvailabilityProvider** trả về **Availability.available()** hoặc **Availability.unavailable(reason)**.

~~~java
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;

@Bean
AvailabilityProvider downloadAvailability(ConnectionService connectionService) {
    return () -> connectionService.isConnected()
            ? Availability.available()
            : Availability.unavailable("you are not connected");
}
~~~

Gắn provider vào command bằng tên bean:

~~~java
@Command(
        name = "download",
        description = "Tải dữ liệu từ máy chủ.",
        availabilityProvider = "downloadAvailability"
)
public String download() {
    return downloadService.downloadLatest();
}
~~~

Nếu command chưa sẵn sàng, Spring Shell có thể giải thích lý do, chẳng hạn **Command 'download' exists but is not currently available because you are not connected.** Phần lý do nên là một cụm từ nối tự nhiên sau chữ “because”, viết thường và không có dấu chấm kết thúc.

Availability phù hợp để phản ánh điều kiện vận hành có thể kiểm tra nhanh: đã cấu hình endpoint chưa, đã có phiên kết nối chưa, phiên đăng nhập còn hiệu lực không. Provider nên có tính đọc, thực thi nhanh và không gây thay đổi trạng thái. Không thực hiện kết nối mạng, tạo tài nguyên hoặc chạy quy trình nghiệp vụ trong provider.

Điều kiện availability cũng không thay thế kiểm tra quyền hay kiểm tra nghiệp vụ trong service. Trạng thái có thể thay đổi ngay sau khi provider trả lời. Ví dụ, một người dùng có thể mất quyền triển khai giữa lúc shell hiển thị command là khả dụng và lúc command thực sự chạy. **DeploymentService** vẫn phải kiểm tra quyền và trạng thái một lần nữa trước khi ghi thay đổi.

### 3.2. CompletionProvider: gợi ý đầu vào

**CompletionProvider** trả về danh sách **CompletionProposal** dựa trên phần văn bản người dùng đang nhập. Spring Shell có sẵn một số provider như **EnumCompletionProvider**, **FileNameCompletionProvider** và **CompositeCompletionProvider**.

Ví dụ, command triển khai có thể gợi ý các môi trường đã được cấu hình:

~~~java
import java.util.List;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Bean
CompletionProvider environmentCompletion() {
    return context -> List.of(
            new CompletionProposal("--environment=dev"),
            new CompletionProposal("--environment=staging"),
            new CompletionProposal("--environment=prod")
    );
}
~~~

Gắn provider với command:

~~~java
@Command(
        name = "deploy",
        completionProvider = "environmentCompletion"
)
public String deploy(
        @Option(longName = "environment", required = true) String environment) {
    return deploymentService.deploy(environment);
}
~~~

Gợi ý là trợ giúp giao diện, không phải danh sách giá trị được đảm bảo hợp lệ tại thời điểm thực thi. Môi trường có thể bị vô hiệu hóa hoặc quyền của người dùng có thể thay đổi sau khi gợi ý được tạo. Service vẫn phải xác minh lại giá trị thực nhận.

Completion provider nên trả về nhanh và tránh gọi API từ xa cho từng lần nhấn Tab. Nếu danh sách đến từ dữ liệu động, hãy cân nhắc dùng cache hoặc một nguồn dữ liệu cục bộ phù hợp. Chỉ dùng completion khi nó giúp người dùng khám phá lựa chọn; không cần viết provider riêng nếu giá trị enum hoặc tên file đã được provider có sẵn xử lý.

### 3.3. Bean Validation: kiểm tra cấu trúc và giới hạn đầu vào

Spring Shell tích hợp Bean Validation để kiểm tra các ràng buộc đặt trên tham số command trước khi gọi method. Ví dụ, **@NotBlank** yêu cầu chuỗi có nội dung, **@Size** giới hạn độ dài và **@Min** đặt giá trị số tối thiểu.

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "create-user", description = "Tạo người dùng mới.")
public String createUser(
        @Option(longName = "username", required = true)
        @NotBlank
        @Size(min = 3, max = 40)
        String username,
        @Option(longName = "age", required = true)
        @Min(18)
        int age) {
    return userService.create(username, age);
}
~~~

Các annotation giúp mô tả quy tắc đầu vào ngay tại giao diện command. Nếu tham số không thỏa mãn constraint, framework báo lỗi validation và không gọi method command.

Hãy phân biệt hai nhóm quy tắc:

- **Ràng buộc đầu vào:** chuỗi không được rỗng, số phải lớn hơn một giới hạn, danh sách không vượt quá số phần tử cho phép. Có thể mô tả bằng Bean Validation.
- **Quy tắc nghiệp vụ:** username đã tồn tại chưa, người gọi có quyền tạo tài khoản không, hạn mức của tổ chức còn đủ không. Những điều kiện này phụ thuộc dữ liệu và trạng thái nghiệp vụ, nên được kiểm tra trong application/domain service.

Ví dụ, **@Min(18)** có thể xác định tuổi nhỏ nhất theo hợp đồng đầu vào. Nhưng nếu độ tuổi tối thiểu thay đổi theo quốc gia hoặc loại tài khoản, quy tắc đó có thể cần được kiểm tra trong service với dữ liệu chính sách tương ứng. Không cố biến mọi quy tắc nghiệp vụ thành annotation trên tham số.

### 3.4. ExitStatusExceptionMapper: chuyển exception thành kết quả CLI

**ExitStatusExceptionMapper** nhận exception phát sinh trong lúc thực thi và trả về một **ExitStatus**, gồm mã và mô tả. Mapper giúp ứng dụng thống nhất cách biểu diễn lỗi cho người dùng và script tự động.

~~~java
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Bean
ExitStatusExceptionMapper deployExitMapper() {
    return exception -> {
        if (exception instanceof DeploymentConflictException) {
            return new ExitStatus(20, "deployment conflict");
        }
        return ExitStatus.EXECUTION_ERROR;
    };
}
~~~

Command có thể tham chiếu mapper theo tên bean:

~~~java
@Command(
        name = "deploy",
        exitStatusExceptionMapper = "deployExitMapper"
)
public String deploy(
        @Option(longName = "version", required = true) String version) {
    return deploymentService.deploy(version);
}
~~~

Mapper chịu trách nhiệm chuyển đổi lỗi sang hợp đồng của CLI. Nó không nên nuốt exception rồi giả vờ thành công, tự thực hiện rollback hoặc chứa logic quyết định có được triển khai hay không. Giao dịch và tính nhất quán dữ liệu thuộc service hoặc tầng persistence. Mapper chỉ định nghĩa cách lỗi đã xảy ra được thể hiện ra ngoài.

Nếu nhiều command có cách ánh xạ lỗi khác nhau, có thể gắn mapper riêng cho từng command. Nếu muốn mọi command dùng một quy tắc chung, hãy thiết kế một chính sách dùng chung và kiểm tra rõ cách Spring Shell cấu hình mapper trong phiên bản đang dùng; không tạo nhiều bean trùng tên hoặc dựa vào thứ tự không được bảo đảm.

### 3.5. CommandContext: tài nguyên của lần gọi hiện tại

**CommandContext** chứa thông tin của lần gọi command hiện tại:

- **parsedInput()** trả về dữ liệu đã phân tích.
- **commandRegistry()** cho phép truy cập registry.
- **inputReader()** đọc dữ liệu người dùng.
- **outputWriter()** ghi nội dung ra shell.
- Các phương thức **getOptionByName**, **getOptionByLongName**, **getOptionByShortName** và **getArgumentByIndex** truy xuất option hoặc argument đã phân tích.

~~~java
@Command(name = "confirm-delete")
public void confirmDelete(
        @Option(longName = "id", required = true) String id,
        CommandContext context) throws Exception {

    String answer = context.inputReader()
            .readInput("Xóa bản ghi " + id + "? (yes/no): ");

    if ("yes".equalsIgnoreCase(answer)) {
        recordService.delete(id);
        context.outputWriter().println("Đã xóa bản ghi " + id);
    }
    else {
        context.outputWriter().println("Đã hủy thao tác");
    }
}
~~~

Context là cầu nối giữa command và môi trường shell. Nó không phải nơi lưu trạng thái nghiệp vụ dài hạn. Nếu nhiều command cần cùng một trạng thái kết nối hoặc cấu hình, hãy đưa trạng thái đó vào service hoặc component quản lý phù hợp.

**InputReader** hữu ích khi cần hỏi thêm dữ liệu hoặc đọc mật khẩu trong phiên tương tác. Tuy nhiên, một command được gọi từ script hoặc chế độ non-interactive không nên phụ thuộc vào prompt mà người chạy không thể trả lời. Với tác vụ tự động, ưu tiên truyền đầy đủ option và argument trên dòng lệnh; chỉ dùng câu hỏi tương tác khi command thực sự yêu cầu phiên làm việc với người dùng.

## 4. Các điểm mở rộng ở phạm vi ứng dụng

### 4.1. CommandRegistryCustomizer: tùy chỉnh tập command

**CommandRegistry** lưu các command mà ứng dụng shell có thể gọi. Spring Shell tự đưa các command đã định nghĩa trong application context vào registry. Ứng dụng có thể đăng ký hoặc gỡ command động thông qua registry.

**CommandRegistryCustomizer** là callback để tùy chỉnh registry. Ví dụ sau bổ sung một command chẩn đoán ở cấp ứng dụng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.autoconfigure.CommandRegistryCustomizer;
import org.springframework.shell.core.command.Command;

@Bean
CommandRegistryCustomizer registerDiagnosticsCommand() {
    return registry -> registry.registerCommand(
            Command.builder()
                    .name("diagnostics")
                    .description("Hiển thị thông tin chẩn đoán.")
                    .execute(context -> "CLI đang hoạt động")
                    .build()
    );
}
~~~

Đây là nơi phù hợp để điều chỉnh tập command chung khi khởi tạo ứng dụng, chẳng hạn bổ sung command đến từ module tùy chọn hoặc gỡ command không được đóng gói trong một cấu hình triển khai. Khi registry đã hoạt động, API **CommandRegistry** cũng cung cấp thao tác đăng ký và gỡ command.

Không dùng việc ẩn hoặc gỡ command làm cơ chế bảo mật duy nhất. Một command không xuất hiện trong help vẫn có thể bị gọi qua một đường khác nếu còn được đăng ký ở nơi khác; và quyền truy cập tài nguyên vẫn phải được xác minh trong service. Registry quyết định command nào được shell công bố, còn service quyết định người gọi có được phép thực hiện hành động hay không.

### 4.2. CommandParser: thay đổi quy tắc phân tích đầu vào

**CommandParser** nhận chuỗi đầu vào và trả về **ParsedInput**. Parser mặc định hỗ trợ tên command, subcommand, option và argument theo cú pháp của Spring Shell. Spring Shell 4 cho phép ứng dụng cung cấp parser riêng dưới dạng bean nếu cú pháp mặc định không đáp ứng yêu cầu.

Một parser tùy chỉnh có ảnh hưởng đến mọi command dùng parser đó. Vì vậy, chỉ nên thay parser khi ứng dụng có yêu cầu cú pháp thực sự ở phạm vi toàn CLI, ví dụ cần tương thích với một định dạng lệnh có sẵn. Nếu chỉ một command có cách xử lý giá trị đặc biệt, hãy dùng option/argument có kiểu phù hợp và xử lý trong command hoặc service.

Parser có nhiệm vụ phân tích cú pháp, không thực hiện truy vấn cơ sở dữ liệu, không kiểm tra quyền nghiệp vụ và không chạy lệnh. Nó nên là thành phần có hành vi xác định: cùng một chuỗi đầu vào và cùng cấu hình sẽ tạo ra cùng một kết quả phân tích. Thay đổi parser cũng cần được kiểm thử với quoting, escaping, option có dấu gạch ngang và argument có khoảng trắng để tránh làm hỏng các command đang dùng.

### 4.3. Runner, input và giao diện tương tác

Runner quyết định shell nhận đầu vào theo cách nào. Spring Shell 4 có runner tương tác và runner non-interactive; JLine bổ sung khả năng chỉnh sửa dòng lệnh, lịch sử và completion cho terminal tương thích. Đây là lựa chọn ở phạm vi vận hành ứng dụng, không phải logic riêng của một command.

Nếu command cần thu thập nhiều bước đầu vào có hướng dẫn, có thể dùng **ComponentFlow** và các component tương tác của Spring Shell. Chẳng hạn, wizard có thể hỏi endpoint, chọn môi trường, xác nhận thao tác rồi chuyển kết quả đã chọn cho service. Các thành phần này tổ chức trải nghiệm nhập liệu; chúng không nên thay thế kiểm tra quyền, validation nghiệp vụ hoặc logic giao dịch.

Giữ ranh giới rõ ràng giữa ba phần: runner tiếp nhận đầu vào, command điều phối tương tác và service thực hiện công việc. Nhờ đó, service có thể được gọi từ command khác, job nền hoặc bài kiểm thử mà không cần khởi chạy terminal.

## 5. Đặt logic nghiệp vụ ở đâu?

Hãy xem một lệnh triển khai ứng dụng. Mỗi trách nhiệm có một nơi phù hợp:

| Công việc | Thành phần chịu trách nhiệm |
|---|---|
| Định nghĩa **deploy --environment --version** và help | Method **@Command**, **@Option** |
| Gợi ý **dev**, **staging**, **prod** khi nhấn Tab | **CompletionProvider** |
| Báo chưa cấu hình thông tin truy cập | **AvailabilityProvider** |
| Kiểm tra option có rỗng hoặc sai độ dài không | Bean Validation |
| Xác minh người dùng có quyền triển khai môi trường production không | **DeploymentService** hoặc authorization service |
| Kiểm tra version đã được phát hành và môi trường còn cho phép triển khai không | **DeploymentService** |
| Thực hiện triển khai và ghi nhận kết quả | **DeploymentService** cùng các thành phần nghiệp vụ |
| Chuyển **DeploymentConflictException** thành mã thoát dễ nhận diện | **ExitStatusExceptionMapper** |
| Thêm hoặc gỡ command quản trị theo cấu hình ứng dụng | **CommandRegistryCustomizer** |

Một method command nên đóng vai trò adapter mỏng:

~~~java
@Component
class DeploymentCommands {

    private final DeploymentService deploymentService;

    DeploymentCommands(DeploymentService deploymentService) {
        this.deploymentService = deploymentService;
    }

    @Command(name = "deploy", description = "Triển khai một phiên bản.")
    public String deploy(
            @Option(longName = "environment", required = true) String environment,
            @Option(longName = "version", required = true) String version) {

        DeploymentResult result =
                deploymentService.deploy(environment, version);

        return "Đã triển khai " + result.version()
                + " lên " + result.environment();
    }
}
~~~

Method nhận dữ liệu đã được shell phân tích, gọi service và trình bày kết quả. Service không cần biết lệnh được gọi từ JLine, script hay một thành phần khác. Nếu mai sau ứng dụng bổ sung REST API để triển khai, cùng service vẫn có thể được tái sử dụng.

Không đưa toàn bộ nghiệp vụ vào provider chỉ vì provider có thể truy cập Spring bean. Một provider được gọi trong thời điểm UI cần thông tin, có thể được gọi nhiều lần và có thể chạy khi người dùng chưa thực sự thực thi command. Nếu đặt side effect vào provider, người dùng có thể vô tình kích hoạt hành động khi chỉ đang xem gợi ý.

## 6. Dấu hiệu cho thấy đang dùng sai điểm mở rộng

- **Provider thực hiện hành động:** nhấn Tab hoặc kiểm tra availability lại tạo kết nối, ghi dữ liệu hay chạy deployment. Chuyển side effect sang command/service.
- **Availability thay thế authorization:** command hiển thị là unavailable nên service bỏ qua kiểm tra quyền. Giữ kiểm tra quyền trong service vì trạng thái có thể đổi sau lần kiểm tra availability.
- **Completion là nguồn xác thực:** service chấp nhận mọi giá trị chỉ vì nó từng xuất hiện trong danh sách gợi ý. Xác thực lại giá trị tại thời điểm thực thi.
- **Parser chứa nghiệp vụ:** parser truy vấn database để quyết định option nào hợp lệ. Parser chỉ nên xử lý cú pháp; việc kiểm tra dữ liệu thuộc service.
- **Exception mapper sửa dữ liệu:** mapper bắt exception rồi tự rollback hoặc chạy lại thao tác. Xử lý giao dịch và retry ở tầng nghiệp vụ phù hợp; mapper chỉ chuyển exception thành kết quả CLI.
- **Command method chứa toàn bộ hệ thống:** method vừa parse, kiểm tra quyền, gọi nhiều repository, xử lý giao dịch và định dạng output. Tách phần nghiệp vụ vào service để tái sử dụng và kiểm thử độc lập.
- **Registry được dùng làm tường bảo mật:** command bị ẩn nhưng service không kiểm tra quyền. Ẩn command chỉ cải thiện trải nghiệm và cách công bố giao diện.
- **Tùy biến parser quá sớm:** một command có quy tắc riêng khiến toàn bộ cú pháp CLI bị thay đổi. Trước hết hãy thử biểu diễn bằng named option, positional argument hoặc subcommand.

## 7. Kiểm thử từng ranh giới

Kiểm thử nên xác minh mỗi điểm mở rộng chỉ làm đúng nhiệm vụ của nó:

1. **Command logic:** gọi application service với dữ liệu đã phân tích và trả về thông báo hoặc kết quả phù hợp. Có thể kiểm thử service mà không cần khởi chạy shell.
2. **AvailabilityProvider:** khi chưa kết nối, provider trả về unavailable cùng lý do dễ hiểu; sau khi kết nối, provider trả về available. Xác minh provider không tạo kết nối hoặc thay đổi trạng thái.
3. **CompletionProvider:** đầu vào đang gõ tạo ra các gợi ý phù hợp; provider không thực thi command hoặc ghi dữ liệu.
4. **Bean Validation:** tham số rỗng, quá dài hoặc nhỏ hơn giới hạn bị từ chối trước khi command method được gọi.
5. **ExitStatusExceptionMapper:** từng loại exception quan trọng được ánh xạ sang mã và mô tả mong đợi; lỗi không được nhận diện có fallback rõ ràng.
6. **CommandRegistryCustomizer:** command được bổ sung hoặc gỡ đúng theo cấu hình; tên command không bị đăng ký trùng.
7. **CommandParser:** cú pháp thông thường vẫn hoạt động sau khi tùy chỉnh; kiểm tra cả dấu nháy, escape, option và argument.
8. **Chế độ chạy:** command hoạt động với terminal tương tác và với script/non-interactive. Những command yêu cầu **InputReader** cần được kiểm tra riêng vì script không thể tự trả lời prompt tùy ý.

Trong kiểm thử tích hợp, có thể dùng hỗ trợ kiểm thử của Spring Shell để gửi command và xác nhận output. Đồng thời kiểm thử trực tiếp provider như các function/service thông thường để xác định lỗi nằm ở hook hay ở nghiệp vụ. Khi một command thất bại, cần xác định đó là lỗi cú pháp, validation, availability, nghiệp vụ hay ánh xạ exit status; các loại lỗi này có ý nghĩa khác nhau với người dùng và script gọi CLI.

## 8. Khác biệt tên API giữa 3.x và 4.x

Nếu duy trì ứng dụng qua nhiều phiên bản, cần chú ý một số tên thay đổi:

| Khái niệm | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|
| Đăng ký command lập trình | **CommandRegistration** | **Command** / **Command.Builder** |
| Tập command | **CommandCatalog** | **CommandRegistry** |
| Tùy chỉnh catalog | **CommandCatalogCustomizer** | **CommandRegistryCustomizer** |
| Gợi ý đầu vào | **ValueProvider**, **CompletionResolver** tùy mô hình | **CompletionProvider** |
| Availability của annotation mới | **@CommandAvailability** và **AvailabilityProvider** | Thuộc tính **availabilityProvider** trên **@Command** |
| Ánh xạ lỗi | **CommandExceptionResolver** | **ExitStatusExceptionMapper** |
| Parser | Cơ chế phân tích theo mô hình registration của 3.x | **CommandParser** |

Các dòng phiên bản có thể tiếp tục bổ sung API, vì vậy hãy dùng tài liệu đúng minor/patch version trước khi chuyển mã. Đặc biệt, không lấy ví dụ **CommandCatalogCustomizer** của 3.x rồi đổi tên class một cách máy móc; hợp đồng và kiểu command mà registry quản lý trong 4.x đã thay đổi.

## 9. Cách quyết định có cần mở rộng hay không

Trước khi tạo một extension bean, hãy trả lời ba câu hỏi:

- Hành vi có thuộc riêng một command không? Nếu có, ưu tiên metadata hoặc provider được gắn trực tiếp vào command.
- Hành vi có cần áp dụng cho mọi command hoặc thay đổi cách toàn CLI hoạt động không? Nếu có, xem xét parser hoặc registry customizer ở cấp ứng dụng.
- Hành vi có làm thay đổi dữ liệu, kiểm tra quyền hoặc thực hiện quy trình nghiệp vụ không? Nếu có, đặt nó trong application/domain service và gọi service từ command.

Nếu chức năng mặc định của Spring Shell đã đáp ứng nhu cầu, không cần thêm extension point. Một command có thể chỉ cần **@Command**, các tham số **@Option**/**@Argument** và một lời gọi service. Chỉ mở rộng khi có yêu cầu cụ thể mà metadata và hành vi mặc định chưa giải quyết được.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — annotation model, programmatic model và **CommandRegistry**.
- [Spring Shell — Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html) — **AvailabilityProvider** và điều kiện command khả dụng.
- [Spring Shell — Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html) — **CompletionProvider** và **CompletionProposal**.
- [Spring Shell — Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html) — Bean Validation trước khi thực thi command.
- [Spring Shell — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html) — **ExitStatusExceptionMapper** và mã thoát.
- [Spring Shell — Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html) — **CommandContext**, input reader và output writer.
- [Spring Shell — Reading Input](https://docs.spring.io/spring-shell/reference/commands/reading.html) — đọc dữ liệu trong command.
- [Spring Shell — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) — quy tắc phân tích option/argument và tùy biến **CommandParser**.
- [Spring Shell API — CommandRegistryCustomizer](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/CommandRegistryCustomizer.html) — hook tùy chỉnh registry.
