# Đối tượng dùng chung và dữ liệu riêng của từng yêu cầu

Trong ứng dụng web MVC, nhiều request có thể được xử lý đồng thời và đi qua cùng một Controller, service hoặc repository. Một số đối tượng được tạo một lần rồi dùng chung trong suốt thời gian ứng dụng chạy; dữ liệu khác chỉ có ý nghĩa trong một request hoặc một lần thực thi use case. Nếu đặt dữ liệu riêng của người dùng vào một đối tượng dùng chung, request này có thể ghi đè dữ liệu của request khác, gây rò rỉ thông tin hoặc tạo lỗi khó tái hiện.

Thiết kế đúng cần xác định **vòng đời của đối tượng**, **phạm vi sở hữu trạng thái** và **cách truy cập đồng thời**. Đối tượng dùng chung nên giữ cấu hình bất biến, dịch vụ không lưu trạng thái theo request hoặc tài nguyên được bảo vệ bằng cơ chế đồng bộ phù hợp. Dữ liệu riêng của request nên nằm trong biến cục bộ, tham số phương thức, request-scoped object hoặc một cấu trúc dữ liệu mới dành cho lần xử lý đó.

Trong MVC, Controller tiếp nhận request và điều phối; Model cùng dịch vụ ứng dụng thực hiện quy tắc; View trình bày kết quả. Cách phân chia này chỉ an toàn khi dữ liệu của từng request không bị lưu nhầm vào field dùng chung và các thành phần được chia sẻ có khả năng phục vụ nhiều request đồng thời.

## 1. Đối tượng dùng chung và dữ liệu riêng request là gì?

**Đối tượng dùng chung (shared object)** là đối tượng có thể được nhiều request, luồng hoặc thành phần truy cập trong cùng khoảng thời gian. Ví dụ:

- Controller hoặc application service được tạo theo singleton scope.
- Repository và client kết nối đến dịch vụ bên ngoài.
- Đối tượng cấu hình được dùng chung.
- Cache dùng chung giữa các request.
- Bộ quản lý tài nguyên hoặc bộ đếm toàn cục.

**Dữ liệu riêng của request (request-local data)** là dữ liệu chỉ thuộc về một lần xử lý HTTP. Ví dụ:

- Path variable, query parameter và dữ liệu form vừa binding.
- Principal hoặc thông tin người dùng được xác thực cho request hiện tại.
- Validation errors.
- DTO hoặc command được tạo từ payload.
- ViewModel dùng để dựng response.
- Correlation ID và thông tin chẩn đoán riêng của request.

Một cách phân biệt hữu ích là hỏi: “Nếu hai người dùng gửi request cùng lúc, hai lần xử lý có được phép nhìn thấy và sửa cùng giá trị này không?” Nếu câu trả lời là không, dữ liệu đó không nên được đặt trong field mutable của một đối tượng dùng chung.

| Đặc điểm | Đối tượng dùng chung | Dữ liệu riêng request |
|---|---|---|
| Phạm vi sử dụng | Nhiều request hoặc thành phần | Một lần xử lý request |
| Vòng đời | Thường dài hơn request | Bắt đầu khi xử lý request và kết thúc sau response |
| Ví dụ | Service stateless, repository, cấu hình | Form DTO, lỗi validation, ViewModel |
| Rủi ro chính | Race condition, trạng thái dùng chung bị thay đổi, rò rỉ dữ liệu | Giữ tham chiếu quá lâu hoặc chuyển nhầm sang request khác |
| Cách tổ chức | Bất biến, stateless hoặc thread-safe | Biến cục bộ, tham số, request scope |

Không phải mọi đối tượng dùng chung đều nguy hiểm. Một service không có trạng thái thay đổi theo request có thể được dùng an toàn bởi nhiều luồng. Ngược lại, một đối tượng được tạo riêng cho request vẫn có thể gây lỗi nếu nó giữ tham chiếu đến một đối tượng mutable dùng chung không được bảo vệ.

## 2. Vòng đời đối tượng trong ứng dụng MVC

Một request web thường đi qua nhiều thành phần. Framework có thể tạo Controller một lần, còn các tham số và đối tượng dữ liệu được tạo cho từng lần gọi phương thức.

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động"] --> B["Tạo các bean dùng chung"]
    B --> C["Controller / Service / Repository"]
    D["Request A"] --> E["Dữ liệu riêng A"]
    F["Request B"] --> G["Dữ liệu riêng B"]
    C --> H["Xử lý request A"]
    C --> I["Xử lý request B"]
    E --> H
    G --> I
    H --> J["Response A"]
    I --> K["Response B"]
~~~

Trong ví dụ này, hai request có thể dùng chung Controller và Service, nhưng mỗi request có dữ liệu riêng. Controller không nên lưu form A vào field rồi để request B đọc lại field đó. Thay vào đó, dữ liệu được truyền qua tham số phương thức hoặc đối tượng command của từng lần xử lý.

### 2.1. Vòng đời không đồng nghĩa với khả năng truy cập đồng thời

Một đối tượng có vòng đời dài không tự động không an toàn. Điều quan trọng là nó có thể bị nhiều luồng truy cập cùng lúc và có trạng thái mutable hay không.

- Đối tượng immutable sau khi khởi tạo thường dễ chia sẻ an toàn.
- Đối tượng stateless không giữ dữ liệu riêng request trong field thường có thể phục vụ đồng thời.
- Đối tượng mutable dùng chung cần cơ chế bảo vệ hoặc thiết kế lại phạm vi sở hữu.
- Đối tượng request-scoped có thể vẫn bị chia sẻ nếu ứng dụng chủ động truyền tham chiếu của nó sang một luồng khác.

Một Controller singleton có thể an toàn nếu nó chỉ giữ các dependency dùng chung an toàn và mọi dữ liệu xử lý được đặt trong biến cục bộ. Một DTO mới tạo cho request vẫn không an toàn nếu nhiều luồng cùng sửa nó mà không có quy tắc phối hợp.

### 2.2. Vòng đời bean trong Spring

Spring hỗ trợ nhiều bean scope. Scope quyết định container quản lý vòng đời instance như thế nào; nó không tự bảo đảm thread safety cho các object mutable.

| Scope | Vòng đời và phạm vi | Trường hợp thường gặp |
|---|---|---|
| singleton | Một instance cho mỗi bean definition trong một Spring IoC container | Controller, service stateless, repository |
| prototype | Container tạo instance mới mỗi lần bean được yêu cầu | Đối tượng có trạng thái cần instance riêng |
| request | Một instance trong phạm vi một HTTP request | Context hoặc dữ liệu phụ thuộc request |
| session | Một instance trong phạm vi HTTP session của người dùng | Wizard hoặc trạng thái phiên có chủ đích |
| application | Một instance gắn với ServletContext | Dữ liệu ứng dụng dùng chung trong web application |
| websocket | Một instance trong phạm vi WebSocket session | Trạng thái riêng của kết nối WebSocket |

Singleton trong Spring không có nghĩa là một instance duy nhất trên toàn bộ cụm máy chủ. Mỗi application context hoặc mỗi instance ứng dụng có thể có bản singleton riêng. Nếu chạy ba server instance, mỗi instance có thể có một singleton service riêng.

Prototype cũng không tự động tạo một object mới cho mỗi lần gọi phương thức của một singleton. Nếu prototype bean được inject trực tiếp vào singleton, việc resolve dependency thường xảy ra khi singleton được tạo; singleton sẽ giữ instance đó. Nếu cần lấy prototype mới mỗi lần, có thể dùng ObjectProvider, Provider hoặc cơ chế lookup phù hợp.

## 3. Controller singleton và lỗi lưu trạng thái trong field

Trong Spring MVC, Controller thường là singleton. Một instance có thể nhận nhiều request đồng thời. Vì vậy, field mutable chứa dữ liệu người dùng hoặc request là nguồn lỗi phổ biến.

Ví dụ không an toàn:

~~~java
@Controller
class ProfileController {
    private String currentUserName;

    @GetMapping("/profile")
    String profile(@AuthenticationPrincipal AppPrincipal principal,
                   Model viewModel) {
        currentUserName = principal.name();
        viewModel.addAttribute("userName", currentUserName);
        return "profile";
    }
}
~~~

Giả sử hai request gần như đồng thời:

1. Request A của người dùng An gán currentUserName = "An".
2. Request B của người dùng Bình gán currentUserName = "Bình".
3. Request A đọc field và đưa "Bình" vào ViewModel.
4. Người dùng An có thể nhìn thấy tên của người dùng Bình.

Đây vừa là race condition vừa là nguy cơ rò rỉ dữ liệu giữa người dùng. Lỗi có thể chỉ xuất hiện khi tải đồng thời, nên kiểm thử thủ công từng request thường không phát hiện được.

Cách sửa là giữ dữ liệu trong biến cục bộ:

~~~java
@Controller
class ProfileController {

    @GetMapping("/profile")
    String profile(
        @AuthenticationPrincipal AppPrincipal principal,
        Model viewModel
    ) {
        String currentUserName = principal.name();
        viewModel.addAttribute("userName", currentUserName);
        return "profile";
    }
}
~~~

Mỗi lần gọi phương thức có stack frame và biến cục bộ riêng. Controller vẫn là singleton, nhưng dữ liệu tên người dùng không còn được chia sẻ qua field.

### 3.1. Field nào có thể giữ trong Controller?

Các field sau thường phù hợp:

- Dependency được inject như service hoặc mapper có khả năng dùng chung an toàn.
- Hằng số static final hoặc cấu hình immutable.
- Thành phần không giữ trạng thái riêng request và được thiết kế để truy cập đồng thời.

Các field sau cần tránh hoặc phải có thiết kế đồng bộ rõ ràng:

- currentUser, currentRequest, currentForm.
- Danh sách kết quả truy vấn được thay đổi theo request.
- Validation errors hoặc ViewModel của một người dùng.
- Biến tạm dùng để lưu ID tài nguyên đang xử lý.
- Bộ đếm hoặc cache mutable tự viết mà không có cơ chế đồng bộ.

Không nên chuyển một field mutable sang static để “dùng chung toàn ứng dụng”. Static làm phạm vi chia sẻ rộng hơn và thường khiến vòng đời, kiểm thử, cấu hình và cách cô lập dữ liệu khó kiểm soát hơn.

## 4. Service dùng chung nên stateless hoặc thread-safe

Service thường được khai báo singleton để tiết kiệm tài nguyên và dùng chung dependency. Điều đó phù hợp nếu service không giữ trạng thái thay đổi theo request.

Ví dụ service stateless:

~~~java
@Service
class PriceCalculator {
    BigDecimal calculate(
        BigDecimal unitPrice,
        int quantity,
        BigDecimal discountRate
    ) {
        return unitPrice
            .multiply(BigDecimal.valueOf(quantity))
            .multiply(BigDecimal.ONE.subtract(discountRate));
    }
}
~~~

Phương thức chỉ dùng tham số và biến cục bộ. Không có field nào lưu giá trị của lần tính trước. Nhiều request có thể gọi cùng một instance mà không ghi đè dữ liệu của nhau.

Ví dụ service có trạng thái nguy hiểm:

~~~java
@Service
class ReportService {
    private List<String> currentRows = new ArrayList<>();

    List<String> buildReport(ReportRequest request) {
        currentRows.clear();
        currentRows.addAll(loadRows(request));
        return currentRows;
    }
}
~~~

Hai request cùng gọi buildReport có thể xóa hoặc thêm dữ liệu vào cùng danh sách. Request A có thể nhận báo cáo chứa dòng của request B.

Nên tạo collection cục bộ cho mỗi lần gọi:

~~~java
@Service
class ReportService {

    List<String> buildReport(ReportRequest request) {
        List<String> rows = new ArrayList<>();
        rows.addAll(loadRows(request));
        return List.copyOf(rows);
    }
}
~~~

List cục bộ thuộc lần gọi hiện tại. List.copyOf trả về danh sách không thể sửa qua API collection thông thường, giúp kết quả được chia sẻ an toàn hơn sau khi hoàn tất dựng báo cáo.

### 4.1. Immutable object giúp chia sẻ an toàn

Một object immutable không cho phép thay đổi trạng thái quan sát được sau khi khởi tạo. Những cách thường dùng:

- Dùng record hoặc final class với field final.
- Không cung cấp setter.
- Sao chép collection đầu vào và trả collection không thể sửa.
- Không để lộ tham chiếu đến object mutable bên trong.
- Khởi tạo đầy đủ trước khi công bố object cho luồng khác.

Ví dụ:

~~~java
public record AppSettings(
    String defaultLocale,
    int pageSize,
    Set<String> allowedFileTypes
) {
    public AppSettings {
        allowedFileTypes = Set.copyOf(allowedFileTypes);
    }
}
~~~

Record tạo các thành phần final, còn Set.copyOf tạo bản sao không thể sửa thông qua Set API. Nếu phần tử bên trong Set cũng mutable, việc sao chép nông vẫn không làm phần tử trở thành immutable. Cần xem xét cả object graph, không chỉ field ngoài cùng.

### 4.2. Thread-safe không có nghĩa là chỉ dùng collection concurrent

ConcurrentHashMap bảo vệ một số thao tác trên map, nhưng không tự làm toàn bộ quy trình nhiều bước trở thành nguyên tử.

Ví dụ, thao tác “kiểm tra số dư rồi trừ tiền” không thể được bảo vệ chỉ bằng cách dùng ConcurrentHashMap cho số dư. Quy tắc cần một giao dịch hoặc đồng bộ phù hợp bao trùm cả đọc, kiểm tra và cập nhật.

Tương tự, synchronized trên một phương thức không tự giải quyết tính nhất quán giữa nhiều server instance. Lock trong bộ nhớ chỉ điều phối các luồng chia sẻ cùng một lock trong cùng phạm vi runtime. Khi ứng dụng chạy nhiều instance, cần cơ chế ở tầng lưu trữ hoặc phân tán phù hợp.

## 5. Dữ liệu riêng request nên được truyền tường minh

Cách đơn giản nhất để giữ dữ liệu đúng phạm vi là truyền nó qua tham số và giá trị trả về.

~~~java
@PostMapping("/tasks")
String create(
    @Valid @ModelAttribute("form") CreateTaskForm form,
    BindingResult errors,
    @AuthenticationPrincipal AppPrincipal principal,
    Model viewModel
) {
    if (errors.hasErrors()) {
        return "tasks/new";
    }

    CreateTaskCommand command = new CreateTaskCommand(
        form.title(),
        principal.userId()
    );

    TaskResult result = taskService.create(command);
    viewModel.addAttribute("taskId", result.id());
    return "tasks/created";
}
~~~

Trong ví dụ:

- form được binding cho request hiện tại.
- principal đại diện danh tính đã xác thực của request.
- command là dữ liệu đầu vào của use case.
- result là kết quả của lần gọi service.
- viewModel mang dữ liệu cho response hiện tại.

Không cần lưu các giá trị này vào field của Controller hoặc Service. Khi phương thức kết thúc, các biến cục bộ không còn được truy cập qua đường thực thi thông thường; object có thể được thu gom khi không còn tham chiếu.

### 5.1. DTO và command nên có vòng đời ngắn

Request DTO, command, result DTO và ViewModel thường được tạo cho một lần xử lý. Chúng nên được thiết kế để không vô tình trở thành kho trạng thái dùng chung.

Nếu DTO có collection mutable, hãy cân nhắc sao chép dữ liệu đầu vào hoặc dùng collection immutable. Không nên giữ một DTO request trong cache singleton để tái sử dụng cho request tiếp theo.

Không nên đưa HttpServletRequest, HttpServletResponse hoặc đối tượng servlet có vòng đời request vào một service singleton để lưu trong field. Nếu service cần một giá trị từ request, hãy trích xuất giá trị đó ở Controller và truyền vào tham số phù hợp.

## 6. Request scope trong Spring

Spring request scope tạo một bean instance riêng cho mỗi HTTP request. Scope này hữu ích khi nhiều thành phần trong cùng một request cần dùng chung một context request-local mà không phải truyền tham số qua quá nhiều tầng.

Ví dụ:

~~~java
@Component
@RequestScope
class RequestContext {
    private String correlationId;
    private UUID userId;

    public String getCorrelationId() {
        return correlationId;
    }

    public void setCorrelationId(String correlationId) {
        this.correlationId = correlationId;
    }

    public UUID getUserId() {
        return userId;
    }

    public void setUserId(UUID userId) {
        this.userId = userId;
    }
}
~~~

Một interceptor hoặc filter có thể khởi tạo correlation ID; thành phần khác trong cùng request có thể đọc RequestContext. Với bean request-scoped được inject vào singleton, Spring thường dùng scoped proxy để trì hoãn việc truy cập đến instance gắn với request hiện tại.

Cần lưu ý:

- Request scope chỉ tồn tại trong vòng đời request được quản lý bởi web context.
- Không được truy cập bean request-scoped khi không có request hợp lệ, ví dụ trong một tác vụ nền chạy sau response.
- Không nên đưa RequestContext vào static field hoặc giữ tham chiếu đến nó sau khi request kết thúc.
- Request scope không tự biến dữ liệu thành immutable hoặc thread-safe nếu cùng request có nhiều luồng xử lý đồng thời.

Nếu chỉ cần một vài giá trị, truyền chúng qua tham số có thể rõ ràng hơn việc tạo một context dùng chung cho toàn bộ ứng dụng.

## 7. Session scope khác request scope

Session scope gắn dữ liệu với một HTTP session, tức có thể tồn tại qua nhiều request của cùng một phiên. Nó không phải dữ liệu riêng của một request.

Ví dụ wizard có thể lưu bước đang hoàn thành trong session. Nhưng một session có thể gửi nhiều request gần như đồng thời, chẳng hạn người dùng mở hai tab. Nếu cả hai tab cùng sửa một object session mutable, chúng vẫn có thể ghi đè trạng thái của nhau.

| Phạm vi | Ví dụ | Lưu ý |
|---|---|---|
| Request | Form vừa gửi, validation errors, correlation ID | Mỗi request có bản riêng |
| Session | Bước wizard, cart ID tạm, thông tin phiên | Nhiều request trong cùng session có thể truy cập đồng thời |
| Application/shared | Cấu hình, cache chung, service singleton | Nhiều người dùng và request có thể truy cập |
| Database | Đơn hàng, hồ sơ, công việc | Cần giao dịch và kiểm soát cập nhật đồng thời |

Không nên lưu entity lớn hoặc trạng thái nghiệp vụ có thẩm quyền trong session chỉ vì tiện. Có thể giữ ID hoặc bản nháp có giới hạn trong session, còn dữ liệu lâu dài nên nằm ở kho lưu trữ phù hợp.

Với Spring, @SessionScope hoặc @SessionAttributes có thể hữu ích cho luồng nhiều bước. Cần xác định thời điểm kết thúc, timeout, xử lý logout và cách tránh hai tab dùng chung một đối tượng wizard ngoài ý muốn.

## 8. ThreadLocal và ngữ cảnh request

ThreadLocal gắn một giá trị với thread hiện tại. Một số thư viện dùng nó để cung cấp ngữ cảnh như security context, locale hoặc transaction context mà không phải truyền qua mọi phương thức.

Tuy nhiên, thread trong web server thường được tái sử dụng cho nhiều request. Nếu đặt dữ liệu vào ThreadLocal mà không xóa đúng lúc, request tiếp theo chạy trên cùng thread có thể đọc nhầm dữ liệu cũ.

Ví dụ minh họa:

~~~java
private static final ThreadLocal<String> CURRENT_TENANT =
    new ThreadLocal<>();

void handleRequest(String tenantId) {
    try {
        CURRENT_TENANT.set(tenantId);
        process();
    } finally {
        CURRENT_TENANT.remove();
    }
}
~~~

Khối finally bảo đảm giá trị được xóa cả khi xử lý thành công hoặc phát sinh exception. Trong ứng dụng thực tế, nên ưu tiên cơ chế context propagation do framework cung cấp thay vì tự xây ThreadLocal cho mọi dữ liệu.

### 8.1. ThreadLocal không tự truyền sang luồng bất đồng bộ

Khi request chuyển sang executor, CompletableFuture hoặc một thread khác, ThreadLocal thông thường không tự động được truyền theo. Luồng nền có thể không thấy security context hoặc tenant context của request ban đầu.

Cách an toàn hơn là truyền dữ liệu cần thiết một cách tường minh:

~~~java
UUID userId = principal.userId();
UUID taskId = command.taskId();

executor.execute(() -> {
    backgroundService.process(taskId, userId);
});
~~~

Nếu cần truyền context rộng hơn, hãy dùng cơ chế context propagation tương thích với framework và executor. Không giữ HttpServletRequest hoặc request-scoped bean để sử dụng sau khi response đã kết thúc.

Trong reactive application, việc thực thi có thể chuyển giữa các thread; giả định “một request luôn ở cùng một thread” không còn phù hợp. Dùng context mechanism của nền tảng reactive hoặc truyền dữ liệu tường minh.

## 9. Đối tượng dùng chung và cache

Cache là ví dụ điển hình của object dùng chung. Nhiều request có thể đọc và cập nhật cùng một cache entry. Cần xác định:

- Key có phân biệt tenant hoặc người dùng khi dữ liệu mang tính cá nhân không?
- Cache value có immutable hoặc được sao chép khi trả ra không?
- Cập nhật cache có đồng bộ với database không?
- Cache entry hết hạn khi nào?
- Hai request cùng tải một key có tạo tải trùng lặp không?
- Dữ liệu nhạy cảm có bị dùng chung sai phạm vi không?

Ví dụ, cache danh sách quốc gia hoặc cấu hình công khai có thể được dùng chung. Cache hồ sơ cá nhân phải có key và quyền truy cập được thiết kế đúng; không thể dùng một key chung chỉ dựa trên tên endpoint.

Một ConcurrentHashMap có thể giúp bảo vệ cấu trúc map trước truy cập đồng thời, nhưng không giải quyết chính sách hết hạn, cache stampede, invalidation, dữ liệu stale hoặc tính nhất quán với database. Nên dùng giải pháp cache có hợp đồng rõ thay vì tự coi một collection concurrent là cache hoàn chỉnh.

## 10. Giao dịch và cập nhật đồng thời trong Model

Dữ liệu riêng request không đồng nghĩa dữ liệu nghiệp vụ chỉ có một người dùng thao tác. Hai request có thể cùng cập nhật một bản ghi. Model phải bảo vệ bất biến và tính nhất quán ở nơi có thẩm quyền.

Một số cơ chế phổ biến:

- **Transaction:** gom các thao tác lưu trữ cần cùng thành công hoặc rollback.
- **Optimistic locking:** dùng version để phát hiện bản ghi đã thay đổi kể từ lúc đọc.
- **Pessimistic locking:** khóa tài nguyên trong thời gian cần thiết khi xung đột có nguy cơ cao.
- **Unique constraint:** bảo vệ tính duy nhất ở database, kể cả khi nhiều request chạy đồng thời.
- **Atomic operation:** dùng phép cập nhật nguyên tử khi nghiệp vụ cho phép.

Không nên dựa vào một biến boolean trong singleton service để khóa thao tác cho tất cả request. Một biến như isProcessing có thể bị ghi đè, không phân biệt người dùng hoặc tài nguyên, và không phối hợp giữa nhiều instance.

Ví dụ optimistic locking trong JPA:

~~~java
@Entity
class Task {
    @Id
    private UUID id;

    @Version
    private long version;

    private String title;
}
~~~

Nếu hai transaction cùng sửa một version, một transaction có thể thất bại khi flush hoặc commit. Ứng dụng cần chuyển xung đột thành phản hồi phù hợp, chẳng hạn yêu cầu tải lại dữ liệu hoặc trả HTTP 409 theo hợp đồng API.

## 11. Bảo mật khi quản lý trạng thái

Đặt đúng vòng đời dữ liệu cũng là một yêu cầu bảo mật.

- Không giữ tên người dùng, token, dữ liệu form hoặc quyền hiện tại trong field mutable của singleton.
- Không tin dữ liệu client gửi lên chỉ vì nó nằm trong hidden input, cookie hoặc request DTO.
- Không dùng một request context cũ cho request mới.
- Không lưu thông tin nhạy cảm vào cache dùng chung nếu chưa có phân tách key và chính sách truy cập.
- Không đưa dữ liệu session hoặc request sang tác vụ nền nếu không xác định rõ dữ liệu nào được phép truyền.
- Khi logout hoặc session hết hạn, phải vô hiệu hóa trạng thái theo đúng vòng đời.
- Với dữ liệu nhiều tenant, luôn gắn truy vấn và cache key với phạm vi tenant đã xác thực ở server.

Một lỗi dùng chung field có thể không chỉ làm response sai mà còn làm lộ dữ liệu của người dùng khác. Vì vậy, kiểm tra concurrency và kiểm tra phân tách dữ liệu cần được xem là một phần của kiểm thử bảo mật.

## 12. Ví dụ tổng hợp: Controller an toàn với nhiều request đồng thời

Một thiết kế phổ biến là Controller singleton inject service stateless; mỗi request có form và command riêng; Model hoặc repository xử lý trạng thái bền vững.

~~~java
@Controller
@RequestMapping("/tasks")
class TaskController {
    private final TaskService taskService;

    TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    @PostMapping
    String create(
        @Valid @ModelAttribute("form") CreateTaskForm form,
        BindingResult errors,
        @AuthenticationPrincipal AppPrincipal principal,
        RedirectAttributes redirectAttributes
    ) {
        if (errors.hasErrors()) {
            return "tasks/new";
        }

        CreateTaskCommand command = new CreateTaskCommand(
            form.title(),
            principal.userId()
        );

        TaskResult result = taskService.create(command);

        redirectAttributes.addFlashAttribute(
            "notice", "Đã tạo công việc."
        );

        return "redirect:/tasks/" + result.id();
    }
}
~~~

Service được chia sẻ nhưng không lưu dữ liệu request trong field:

~~~java
@Service
class TaskService {
    private final TaskRepository repository;

    TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    TaskResult create(CreateTaskCommand command) {
        Task task = Task.create(
            command.title(),
            command.ownerId()
        );

        Task saved = repository.save(task);
        return new TaskResult(saved.getId(), saved.getTitle());
    }
}
~~~

Mỗi lần gọi create có command riêng. Service có thể dùng chung vì dependency được inject và trạng thái request nằm trong tham số cùng biến cục bộ. Transaction bảo vệ thao tác lưu theo cấu hình persistence; quy tắc tạo công việc được đặt trong Model.

Để thiết kế này an toàn, repository và các dependency cũng phải tuân theo hợp đồng truy cập đồng thời của framework. Không nên giả định rằng mọi dependency đều thread-safe chỉ vì chúng được inject vào singleton.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Lưu currentUser hoặc currentRequest trong field Controller | Request khác có thể ghi đè hoặc đọc nhầm dữ liệu | Dùng biến cục bộ, tham số hoặc request scope |
| Cho rằng singleton luôn thread-safe | Race condition trên field mutable | Thiết kế stateless/immutable hoặc đồng bộ đúng phạm vi |
| Cho rằng prototype inject vào singleton sẽ luôn mới | Singleton có thể giữ một prototype instance từ lúc khởi tạo | Dùng ObjectProvider/Provider khi cần instance mới |
| Dùng static mutable để chia sẻ trạng thái | Phạm vi chia sẻ rộng, khó cô lập và kiểm thử | Dùng dependency được quản lý hoặc kho trạng thái phù hợp |
| Dùng session như request scope | Nhiều tab/request cùng sửa trạng thái session | Quản lý concurrency và tách dữ liệu theo luồng nghiệp vụ |
| Dùng ThreadLocal nhưng không remove | Thread pool có thể tái sử dụng dữ liệu cũ | Xóa trong finally hoặc dùng context propagation |
| Truyền request object vào tác vụ nền | Dùng dữ liệu đã hết vòng đời hoặc không thread-safe | Tạo immutable command/snapshot để truyền |
| Nghĩ ConcurrentHashMap giải quyết mọi race | Chuỗi thao tác nhiều bước vẫn có thể không nguyên tử | Dùng transaction, atomic operation hoặc lock đúng phạm vi |
| Giữ entity mutable trong cache dùng chung | Request có thể thay đổi dữ liệu của nhau | Cache immutable DTO hoặc bản sao có kiểm soát |

## 14. Kiểm thử vòng đời và truy cập đồng thời

Kiểm thử đơn lẻ một request không đủ để phát hiện lỗi dữ liệu dùng chung. Cần kiểm tra cả hai request chạy đồng thời, nhiều request cùng session và request được xử lý ở nhiều instance.

| Phạm vi | Nội dung cần xác minh |
|---|---|
| Controller | Không có field mutable giữ dữ liệu người dùng hoặc request |
| Service | Nhiều lời gọi đồng thời không trộn tham số hoặc kết quả |
| Request scope | Mỗi request nhận context riêng và context không tồn tại sau response |
| Session scope | Nhiều request cùng session được xử lý theo quy tắc concurrency |
| Cache | Key phân tách người dùng/tenant và value không bị sửa ngoài ý muốn |
| Persistence | Transaction, version và constraint ngăn trạng thái không hợp lệ |
| Async | Tác vụ nền nhận dữ liệu cần thiết và không phụ thuộc request đã kết thúc |

Một số kịch bản cụ thể:

1. Gửi đồng thời hai request profile với hai người dùng khác nhau; mỗi response phải chứa đúng danh tính.
2. Gửi nhiều request tạo công việc; không có tiêu đề hoặc ownerId bị trộn giữa các request.
3. Mở hai tab cùng session và cập nhật hai wizard; trạng thái không ghi đè nếu nghiệp vụ yêu cầu tách riêng.
4. Chạy tác vụ nền sau khi response kết thúc; tác vụ vẫn có dữ liệu cần thiết mà không đọc request object.
5. Gọi service đồng thời với dữ liệu khác nhau; kết quả mỗi lần gọi phải độc lập.
6. Hai transaction cập nhật cùng entity; xung đột được phát hiện và phản hồi rõ ràng.
7. Kiểm tra cache với hai tenant; không trả dữ liệu chéo tenant.

Có thể dùng kiểm thử tích hợp, công cụ tải hoặc test concurrency có đồng bộ điểm bắt đầu để tăng xác suất tái hiện race condition. Không nên chỉ thêm sleep ngẫu nhiên rồi coi đó là bằng chứng thread safety.

## 15. Quy trình chọn phạm vi lưu trạng thái

Khi tạo một object hoặc field mới, hãy xác định:

1. Ai sở hữu dữ liệu: một request, một session, toàn ứng dụng hay database?
2. Dữ liệu tồn tại trong bao lâu?
3. Có thể có nhiều luồng truy cập cùng lúc không?
4. Object có mutable không? Nếu có, ai được phép thay đổi?
5. Có thể dùng immutable object hoặc biến cục bộ thay thế không?
6. Nếu dùng scope dài hơn request, cơ chế đồng bộ và hết hạn là gì?
7. Dữ liệu có nhạy cảm hoặc phụ thuộc tenant/người dùng không?
8. Nếu chuyển sang tác vụ async, dữ liệu nào cần được truyền tường minh?
9. Nếu ứng dụng chạy nhiều instance, trạng thái có cần kho dùng chung không?
10. Có kiểm thử cho request đồng thời và vòng đời sau response không?

Nếu dữ liệu chỉ cần trong một lần xử lý, hãy ưu tiên biến cục bộ hoặc tham số. Nếu nhiều thành phần trong cùng request cần dùng chung context, request scope có thể phù hợp. Nếu dữ liệu tồn tại qua nhiều request của cùng người dùng, session có thể phù hợp với dữ liệu tạm. Nếu dữ liệu là trạng thái nghiệp vụ lâu dài, hãy lưu ở kho dữ liệu có thẩm quyền và bảo vệ cập nhật đồng thời.

## 16. Những điểm cần ghi nhớ

Đối tượng dùng chung và dữ liệu riêng request có vòng đời và phạm vi sở hữu khác nhau. Controller, service và repository singleton có thể phục vụ nhiều request đồng thời nếu chúng không lưu trạng thái riêng request trong field mutable và các dependency được chia sẻ có cơ chế truy cập an toàn.

Dữ liệu form, principal, validation errors, command và ViewModel nên thuộc lần xử lý hiện tại. Hãy truyền dữ liệu qua tham số hoặc dùng request scope khi có lý do rõ ràng. Session scope tồn tại qua nhiều request và cũng cần xử lý truy cập đồng thời, nhất là khi người dùng mở nhiều tab.

ThreadLocal cần được dọn dẹp và không tự truyền qua tác vụ bất đồng bộ. Cache, transaction và collection concurrent có phạm vi bảo vệ riêng; không cơ chế đơn lẻ nào thay thế việc thiết kế đúng quyền sở hữu trạng thái. Khi vòng đời và phạm vi dữ liệu được xác định rõ, các tầng MVC có thể xử lý nhiều request cùng lúc mà không trộn lẫn trạng thái hoặc làm lộ dữ liệu người dùng.
