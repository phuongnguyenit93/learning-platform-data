# Khả năng mở rộng framework

## 1. Khả năng mở rộng framework là gì?

Một framework cung cấp cấu trúc và quy tắc chung để xây dựng ứng dụng. Nó thường quản lý vòng đời, cấu hình, thành phần dùng chung, giao tiếp giữa module và các dịch vụ nền tảng. **Khả năng mở rộng framework (framework extensibility)** là khả năng bổ sung hành vi, thành phần hoặc tích hợp mới thông qua các điểm mở rộng đã được thiết kế, mà không phải sửa trực tiếp phần lõi cho từng yêu cầu.

Trong một hệ thống DSL, framework và workbench có thể cung cấp:

- Lexer, parser và semantic analyzer.
- Editor hỗ trợ completion, hover, diagnostics và rename.
- Code generator hoặc runtime.
- Registry cho rule, validator và generator.
- Giao diện plugin.
- Công cụ cấu hình, build và debug.
- Bộ quản lý project, workspace và tài nguyên.

Một tổ chức có thể muốn thêm rule kiểm tra riêng, một backend sinh mã mới, một định dạng import/export hoặc một panel trong workbench. Nếu framework có extension point phù hợp, nhóm phát triển có thể bổ sung chức năng đó như một module độc lập.

Ví dụ, một DSL mô tả workflow mặc định có thể hỗ trợ các node task, condition và transition. Một dự án muốn thêm node approval. Thay vì sửa parser và runtime lõi theo cách đặc thù cho dự án, framework có thể cung cấp API để đăng ký loại node mới, khai báo editor metadata, validator và runtime handler.

Khả năng mở rộng tốt cần cân bằng nhiều yếu tố:

- Dễ bổ sung chức năng.
- Hợp đồng API rõ ràng và ổn định.
- Các extension tương tác được với nhau.
- Kiểm soát dependency và phiên bản.
- Cô lập lỗi và giới hạn quyền.
- Hiệu năng và khả năng quan sát.
- Khả năng kiểm thử và nâng cấp.

Một framework có nhiều plugin chưa chắc đã có kiến trúc mở rộng tốt. Điều quan trọng là extension được tích hợp theo quy tắc dự đoán được và không làm mất tính ổn định của hệ thống.

## 2. Framework, library, plugin và workbench

Các khái niệm này liên quan nhưng không đồng nghĩa.

### 2.1 Library

Library cung cấp hàm hoặc kiểu dữ liệu để ứng dụng chủ động gọi:

~~~java
String normalized = NameUtils.normalize(sourceName);
~~~

Ứng dụng kiểm soát luồng thực thi và gọi library khi cần.

### 2.2 Framework

Framework thường kiểm soát vòng đời và gọi mã của ứng dụng tại những điểm đã định nghĩa. Đây là nguyên tắc inversion of control (IoC): framework điều phối, extension cung cấp hành vi.

Ví dụ:

~~~text
Framework starts
    |
    v
Load configuration
    |
    v
Discover extensions
    |
    v
Create services
    |
    v
Call extension hooks
    |
    v
Run application
~~~

### 2.3 Plugin

Plugin là module bổ sung được framework phát hiện và nạp theo một hợp đồng. Plugin có thể cung cấp command, validator, editor feature, generator hoặc adapter.

Plugin thường có metadata như:

- Plugin ID.
- Version.
- Nhà cung cấp.
- API version tương thích.
- Dependency.
- Capability được cung cấp.
- Capability được yêu cầu.
- Entry point hoặc provider class.

### 2.4 Workbench

Workbench là môi trường làm việc tích hợp các công cụ phát triển. Với DSL, workbench có thể gồm editor, project explorer, console, debugger, model view, property panel và plugin manager.

Framework mở rộng có thể cho phép plugin đóng góp:

- Editor command.
- Menu hoặc toolbar action.
- View hoặc panel.
- Syntax highlighting.
- Content assist.
- Outline provider.
- Debug adapter.
- Project wizard.

Một plugin có thể mở rộng cả phần xử lý ngôn ngữ lẫn trải nghiệm giao diện.

## 3. Vì sao framework cần extension points?

Nhu cầu của người dùng framework không giống nhau. Một DSL có thể được sử dụng trong nhiều ngành, nhóm phát triển và môi trường triển khai.

Các biến thể có thể đến từ:

- Quy tắc nghiệp vụ của từng tổ chức.
- Backend hoặc nền tảng triển khai.
- Loại dữ liệu và schema.
- Hệ thống xác thực hoặc lưu trữ.
- Công cụ editor và quy trình phát triển.
- Quy định bảo mật và kiểm toán.
- Phiên bản ngôn ngữ hoặc runtime.

Nếu mọi yêu cầu đều phải thay đổi framework core, các nhánh triển khai sẽ nhanh chóng phân kỳ. Khi nâng cấp, nhóm phát triển phải hợp nhất nhiều thay đổi đặc thù và nguy cơ hồi quy tăng.

Extension points tạo ranh giới giữa phần ổn định và phần có thể thay thế hoặc bổ sung.

### 3.1 Tách biệt trách nhiệm

Core chịu trách nhiệm về các invariant và dịch vụ nền tảng. Extension chịu trách nhiệm về hành vi chuyên biệt.

Ví dụ:

| Thành phần | Trách nhiệm |
|---|---|
| Parser core | Xây dựng cấu trúc cú pháp theo grammar |
| Semantic core | Phân giải tên, kiểu và model |
| Domain validator | Kiểm tra chính sách riêng |
| Code generator plugin | Sinh mã cho target cụ thể |
| Editor plugin | Cung cấp panel hoặc lệnh riêng |

### 3.2 Giảm coupling

Nếu core gọi trực tiếp class của từng dự án, core phụ thuộc vào chi tiết triển khai. Extension point đảo chiều phụ thuộc: core định nghĩa interface, plugin triển khai interface đó.

### 3.3 Tái sử dụng

Một plugin có thể được dùng trong nhiều project nếu API và dependency tương thích. Nhóm phát triển không phải sao chép cùng logic vào từng ứng dụng.

### 3.4 Cho phép cấu hình theo môi trường

Một framework có thể nạp bộ extension khác nhau cho development, testing và production. Ví dụ, workbench có debug tools nhưng runtime production chỉ nạp các extension cần thiết.

## 4. Thiết kế extension point

Extension point là vị trí chính thức mà framework cho phép thành phần bên ngoài bổ sung hành vi.

Một extension point cần trả lời:

- Ai được triển khai?
- Framework gọi extension khi nào?
- Dữ liệu đầu vào có cấu trúc gì?
- Extension trả kết quả theo hợp đồng nào?
- Có được thay đổi trạng thái không?
- Có thể chạy đồng thời không?
- Dependency giữa extension được khai báo ra sao?
- Lỗi của extension được xử lý thế nào?
- API có tương thích qua phiên bản không?

### 4.1 API hẹp và có mục đích

Không nên cung cấp toàn bộ object nội bộ của framework nếu extension chỉ cần một phần dữ liệu.

Ví dụ, validator chỉ cần semantic model, configuration snapshot và diagnostic sink:

~~~java
public interface ModelValidator {
    ValidatorDescriptor descriptor();

    void validate(
        SemanticModel model,
        ValidationContext context,
        DiagnosticReporter reporter
    );
}
~~~

API này thể hiện rõ mục đích. Validator không cần biết editor đang hiển thị tab nào hoặc parser lưu token trong cấu trúc nội bộ ra sao.

### 4.2 Hợp đồng hành vi

Interface chỉ mô tả chữ ký method. Hợp đồng còn cần quy định:

- Method có thể được gọi nhiều lần không?
- Có thể chạy song song trên nhiều project không?
- Input có bất biến không?
- Kết quả có được cache không?
- Extension có cần hỗ trợ cancellation không?
- Có giới hạn thời gian không?
- Exception được xử lý thế nào?

### 4.3 Extension point không phải hook tùy tiện

Một callback được gọi từ bất kỳ vị trí nào trong core có thể tạo coupling khó kiểm soát. Extension point nên có vị trí trong lifecycle, kiểu dữ liệu và semantics được công bố.

### 4.4 Stable contract

Core nên tránh yêu cầu plugin truy cập private field hoặc gọi method nội bộ không được hỗ trợ. Các chi tiết đó có thể thay đổi mà không báo trước, khiến plugin bị hỏng sau một bản nâng cấp.

## 5. Các kiểu extension point phổ biến

Framework có thể cung cấp nhiều cơ chế mở rộng.

| Kiểu | Mục đích | Ví dụ trong DSL workbench |
|---|---|---|
| Interface implementation | Bổ sung một loại dịch vụ | Custom validator |
| Provider/registry | Đăng ký nhiều implementation | Generator registry |
| Event listener | Phản ứng với sự kiện | Document opened |
| Lifecycle hook | Chạy ở giai đoạn cụ thể | Project startup |
| Strategy | Thay thuật toán | Naming policy |
| Adapter | Kết nối hệ thống khác | Database metadata provider |
| Command contribution | Bổ sung hành động UI | Generate deployment plan |
| View contribution | Bổ sung giao diện | Policy inspector |
| Resource resolver | Tìm tài nguyên | Resolve imported schema |
| Serializer/deserializer | Hỗ trợ format | YAML importer |

Không nên dùng một cơ chế cho mọi tình huống. Strategy phù hợp khi chọn một thuật toán; event phù hợp khi nhiều thành phần cần phản ứng; registry phù hợp khi framework cần liệt kê và chọn provider.

## 6. Plugin contract và metadata

Một plugin cần được mô tả đủ để host biết có thể nạp và sử dụng nó hay không.

Ví dụ manifest minh họa:

~~~yaml
plugin:
  id: com.example.dsl.finance
  version: 2.1.0
  apiVersion: 3
  description: Finance validation and generation

requires:
  - capability: semantic-model
    version: ">=2"

provides:
  - capability: semantic-validator
  - capability: java-generator
~~~

Đây là cấu trúc ví dụ, không phải một chuẩn manifest chung.

### 6.1 Plugin ID

ID nên duy nhất, ổn định và có namespace. Không nên dùng tên hiển thị làm khóa vì tên có thể được dịch hoặc thay đổi.

### 6.2 Plugin version

Version của plugin mô tả vòng đời implementation. Nó khác version của extension API và version của DSL language.

### 6.3 Capability

Capability mô tả chức năng plugin cung cấp hoặc cần. Host có thể kiểm tra capability thay vì phụ thuộc vào tên class cụ thể.

### 6.4 Dependency

Plugin có thể phụ thuộc vào:

- Core API.
- Plugin khác.
- Library bên ngoài.
- Capability được host cung cấp.

Dependency cần có version range hoặc quy tắc tương thích rõ.

### 6.5 Metadata validation

Trước khi nạp plugin, host nên kiểm tra:

- Manifest hợp lệ.
- ID không bị trùng.
- Version tương thích.
- Dependency đã có.
- Capability không xung đột.
- Entry point tồn tại.
- Chữ ký hoặc nguồn phân phối được tin cậy nếu chính sách yêu cầu.

## 7. Plugin discovery và registration

Framework cần tìm các plugin có thể sử dụng và đăng ký chúng vào registry.

### 7.1 Đăng ký tường minh

Ứng dụng đăng ký trực tiếp:

~~~java
registry.register(new FinanceValidator());
registry.register(new JavaGenerator());
~~~

Cách này dễ hiểu, phù hợp với ứng dụng có tập extension cố định. Tuy nhiên, host phải biết class của plugin tại thời điểm biên dịch hoặc cấu hình.

### 7.2 Service Provider Interface trong Java

Java ServiceLoader cho phép tìm implementation thông qua provider metadata.

Interface:

~~~java
public interface GeneratorProvider {
    CodeGenerator create();
}
~~~

Provider:

~~~java
public final class JavaGeneratorProvider
        implements GeneratorProvider {

    @Override
    public CodeGenerator create() {
        return new JavaCodeGenerator();
    }
}
~~~

Host:

~~~java
ServiceLoader.load(GeneratorProvider.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .map(GeneratorProvider::create)
    .forEach(generatorRegistry::register);
~~~

Provider cần được khai báo theo cơ chế ServiceLoader tương ứng với classpath hoặc module path. Cần quản lý class loader và dependency để tránh nạp nhầm phiên bản.

### 7.3 Plugin directory

Một workbench có thể quét thư mục plugin. Mỗi plugin có manifest và artifact riêng. Host cần xác thực file, đọc metadata và kiểm tra dependency trước khi nạp class.

Không nên thực thi mã plugin ngay khi vừa phát hiện file. Discovery và activation nên là hai bước riêng.

### 7.4 Explicit allowlist

Trong môi trường cần kiểm soát, host có thể chỉ nạp plugin nằm trong allowlist hoặc được quản trị viên phê duyệt. Đây là cách giảm rủi ro từ mã không tin cậy.

## 8. Lifecycle của extension

Extension cần có vòng đời rõ để khởi tạo tài nguyên và giải phóng chúng.

Một lifecycle khái quát:

~~~text
DISCOVERED
    |
    v
VALIDATED
    |
    v
LOADED
    |
    v
INITIALIZED
    |
    v
ACTIVE
    |
    v
STOPPING
    |
    v
DISPOSED
~~~

### 8.1 Discovery

Host tìm thấy plugin và đọc manifest. Ở giai đoạn này, plugin chưa nhất thiết được thực thi.

### 8.2 Validation

Host kiểm tra API version, dependency, capability và chính sách bảo mật.

### 8.3 Loading

Host nạp class hoặc khởi tạo process plugin theo cơ chế triển khai.

### 8.4 Initialization

Plugin nhận context được cấp và đăng ký contribution. Không nên cho plugin truy cập dịch vụ chưa sẵn sàng.

### 8.5 Activation

Plugin bắt đầu nhận request, event hoặc command theo lifecycle.

### 8.6 Shutdown

Host ngừng cấp công việc mới, yêu cầu task đang chạy kết thúc, giải phóng listener, thread, stream và tài nguyên.

### 8.7 Failure

Nếu plugin lỗi khi khởi tạo, host cần đánh dấu trạng thái lỗi và tiếp tục hoạt động nếu plugin đó không phải dependency bắt buộc.

## 9. Dependency injection và service registry

Plugin thường cần sử dụng dịch vụ do framework cung cấp như logger, project model, resource resolver hoặc configuration service.

### 9.1 Dependency injection

Dependency injection (DI) cung cấp dependency từ bên ngoài thay vì để plugin tự tìm hoặc tự tạo mọi dịch vụ.

Ví dụ:

~~~java
public final class FinanceValidator implements ModelValidator {
    private final CurrencyCatalog currencies;

    public FinanceValidator(CurrencyCatalog currencies) {
        this.currencies = currencies;
    }

    // validate(...)
}
~~~

Host tạo validator và truyền CurrencyCatalog tương ứng.

### 9.2 Constructor injection

Constructor injection giúp dependency rõ ràng, hỗ trợ test và bảo đảm object không hoạt động khi thiếu dependency bắt buộc.

### 9.3 Service registry

Một service registry có thể cung cấp các capability:

~~~java
interface ExtensionContext {
    Logger logger();
    ProjectModel project();
    Configuration configuration();
    ResourceResolver resources();
    CancellationToken cancellation();
}
~~~

Context nên nhỏ và có quyền truy cập được kiểm soát. Không nên đưa toàn bộ application container vào plugin nếu plugin chỉ cần một vài dịch vụ.

### 9.4 Scope của dependency

Dependency có thể tồn tại theo:

- Application scope.
- Workspace scope.
- Project scope.
- Document scope.
- Request scope.

Một parser service có thể dùng chung, trong khi document snapshot phải gắn với version cụ thể. Dùng sai scope có thể tạo dữ liệu cũ hoặc chia sẻ mutable state không an toàn.

### 9.5 Dependency cycle

Nếu plugin A cần B và B cần A, host có thể không khởi tạo được. Dependency graph cần phát hiện cycle và báo lỗi rõ. Tránh giải quyết bằng cách tạo object chưa hoàn chỉnh rồi để lỗi xuất hiện muộn.

## 10. Cấu hình extension

Plugin thường cần tham số riêng nhưng không nên đọc cấu hình tùy tiện từ mọi nguồn.

Ví dụ:

~~~yaml
extensions:
  finance-validator:
    enabled: true
    severity: error
    maximumDiscountPercent: 30

  java-generator:
    enabled: true
    packagePrefix: com.example.generated
~~~

### 10.1 Schema cấu hình

Mỗi plugin nên mô tả:

- Key được hỗ trợ.
- Kiểu dữ liệu.
- Giá trị mặc định.
- Khoảng giá trị hợp lệ.
- Key bắt buộc.
- Key đã deprecated.
- Phạm vi áp dụng.

### 10.2 Cấu hình không hợp lệ

Host nên validate cấu hình trước khi kích hoạt plugin. Nếu maximumDiscountPercent là chuỗi không thể chuyển thành số, cần báo lỗi gắn với key và nguồn cấu hình.

### 10.3 Thứ tự ưu tiên

Framework có thể đọc cấu hình từ default, application, workspace, project và command line. Thứ tự override phải được công bố và nhất quán.

### 10.4 Secret

Mật khẩu, token và khóa riêng không nên lưu trong file cấu hình văn bản thông thường nếu có lựa chọn secret store phù hợp. Plugin chỉ nên nhận secret cần thiết và không log chúng.

### 10.5 Reload cấu hình

Khi cấu hình thay đổi, host có thể:

- Cập nhật plugin đang hoạt động nếu API hỗ trợ.
- Tạo instance mới rồi thay thế.
- Yêu cầu restart workspace.

Việc reload phải xử lý task đang chạy và tài nguyên của instance cũ.

## 11. Composition và thứ tự extension

Nhiều plugin có thể cùng đóng góp một loại chức năng. Framework cần định nghĩa cách kết hợp.

Ví dụ nhiều validator:

~~~text
Semantic model
    |
    +--> Core validator
    +--> Finance validator
    +--> Security validator
    +--> Governance validator
    |
    v
Diagnostic collector
~~~

### 11.1 Independent composition

Nếu validator chỉ đọc model và phát diagnostics, chúng có thể chạy độc lập. Host có thể chạy song song nếu contract cho phép.

### 11.2 Ordered composition

Một số extension cần thứ tự:

~~~text
Resolve imports
    -> Build domain model
    -> Run finance rules
    -> Run reporting rules
~~~

Thứ tự nên được khai báo bằng dependency hoặc phase, không dựa vào thứ tự class được phát hiện ngẫu nhiên.

### 11.3 Priority

Priority có thể hữu ích cho command hoặc provider selection. Cần định nghĩa tie-breaker ổn định và cách xử lý hai extension có cùng priority.

### 11.4 Conflict

Hai plugin có thể đăng ký cùng command ID, generator cho cùng target hoặc contribution cùng vị trí. Host nên từ chối hoặc yêu cầu cấu hình chọn rõ, thay vì âm thầm chọn plugin được nạp cuối.

### 11.5 Decorator và chain

Một extension có thể bọc dịch vụ khác để thêm logging, caching hoặc validation. Chain cần tránh vòng lặp, xác định thứ tự và giữ hợp đồng đầu vào/đầu ra.

## 12. Extension cho compiler và DSL runtime

Trong DSL framework, các extension thường gắn với pipeline ngôn ngữ.

### 12.1 Custom validator

Plugin nhận semantic model và tạo diagnostic theo chính sách riêng.

### 12.2 Code generator

Generator plugin chuyển IR sang target như Java, TypeScript, SQL hoặc workflow runtime.

Một interface có thể là:

~~~java
public interface CodeGenerator {
    GeneratorDescriptor descriptor();

    GeneratedArtifact generate(
        IntermediateModel model,
        GenerationContext context
    );
}
~~~

### 12.3 Importer và exporter

Plugin có thể hỗ trợ nhập dữ liệu từ JSON, YAML, XML hoặc xuất semantic model sang format khác.

### 12.4 Custom type provider

Một module có thể bổ sung kiểu miền như Money, Duration hoặc CustomerId. Type provider cần đăng ký quy tắc parse, kiểm tra và biểu diễn target.

### 12.5 Runtime adapter

DSL có thể mô tả hành động trừu tượng. Adapter plugin kết nối hành động đó với database, message broker hoặc dịch vụ bên ngoài.

### 12.6 Grammar extension

Mở rộng grammar khó hơn mở rộng validator vì có thể tạo xung đột cú pháp và làm thay đổi cách parse chương trình cũ.

Nếu hỗ trợ grammar extension, framework cần:

- Namespace hoặc module grammar.
- Quy tắc ưu tiên và xung đột.
- Phiên bản grammar.
- Kiểm tra ambiguity.
- Cơ chế migration.
- Giới hạn extension nào được phép thay đổi cú pháp lõi.

Không nên cho mọi plugin tự thêm token và production vào grammar mà không có kiểm soát.

## 13. Extension cho editor và workbench

Workbench có thể cho phép plugin đóng góp chức năng giao diện.

### 13.1 Command

Plugin đăng ký command có ID ổn định, tiêu đề, mô tả và handler. Command có thể xuất hiện trong command palette, menu hoặc shortcut.

### 13.2 View và panel

Ví dụ:

- Policy inspector.
- Schema explorer.
- Generated code preview.
- Dependency graph.
- Runtime event viewer.

View nên dùng API layout và lifecycle của workbench, không thao tác trực tiếp vào private UI state.

### 13.3 Editor contribution

Plugin có thể cung cấp:

- Syntax highlighting.
- Completion provider.
- Hover provider.
- Code action.
- Outline provider.
- Formatter.
- Debug configuration.

Nếu nhiều plugin cùng cung cấp completion, host cần định nghĩa cách hợp nhất, ranking và giới hạn thời gian.

### 13.4 Context menu và toolbar

Contribution cần khai báo context hoặc điều kiện hiển thị. Không nên thêm mọi command vào mọi menu vì làm giao diện rối.

### 13.5 UI thread

Plugin không nên thực hiện công việc nặng trực tiếp trên UI thread. Hãy chạy xử lý nền và chuyển kết quả về UI thread theo API workbench.

### 13.6 Accessibility

View và command mới cần hỗ trợ keyboard navigation, focus, label và trạng thái phù hợp. Extension API nên cung cấp component hoặc pattern có accessibility sẵn.

## 14. Event system và lifecycle hooks

Framework có thể phát event khi trạng thái thay đổi:

- Workspace opened.
- Project imported.
- Document saved.
- Build started.
- Build completed.
- Configuration changed.
- Language server initialized.

Plugin đăng ký listener để phản ứng.

### 14.1 Event listener

~~~java
interface WorkspaceListener {
    void projectOpened(ProjectEvent event);
    void projectClosed(ProjectEvent event);
}
~~~

Host cần quản lý đăng ký và hủy đăng ký listener.

### 14.2 Event payload

Event nên mang snapshot hoặc dữ liệu bất biến đủ dùng. Nếu chỉ truyền reference đến mutable object, listener có thể nhìn thấy trạng thái khác nhau tùy thời điểm.

### 14.3 Synchronous và asynchronous event

Synchronous listener chạy trong luồng phát event, có thể làm chậm hoặc gây lỗi cho caller. Asynchronous event giảm coupling thời gian nhưng có thể thay đổi thứ tự và semantics hoàn tất.

Contract cần nêu:

- Listener có được phép chặn không?
- Event có bảo đảm thứ tự không?
- Exception được xử lý ra sao?
- Có retry không?
- Event có thể bị mất khi shutdown không?

### 14.4 Unsubscribe

Plugin phải hủy listener khi bị dispose. Nếu không, host có thể giữ reference đến plugin, gây memory leak hoặc gọi mã đã ngừng hoạt động.

## 15. Dependency và version compatibility

Extension API là hợp đồng giữa core và plugin. Khi API thay đổi, plugin cũ có thể không tương thích.

### 15.1 Các loại version

Cần phân biệt:

- Framework version.
- Extension API version.
- Plugin version.
- DSL language version.
- Semantic model version.
- Runtime version.
- Workbench API version.

Một plugin có thể tương thích với framework core nhưng không tương thích với workbench API hoặc schema mới.

### 15.2 Semantic versioning

Nếu dự án dùng semantic versioning:

- MAJOR: thay đổi không tương thích.
- MINOR: bổ sung tính năng tương thích ngược.
- PATCH: sửa lỗi không thay đổi hợp đồng công khai.

Quy tắc này chỉ có ích nếu dự án định nghĩa rõ những gì được xem là public API.

### 15.3 Version range

Plugin manifest có thể khai báo:

~~~text
requires framework-api >= 3.2 and < 4.0
~~~

Host kiểm tra version trước khi activation. Nếu không tương thích, cần thông báo plugin nào và dependency nào gây lỗi.

### 15.4 Capability negotiation

Version number không phải lúc nào cũng đủ. Host có thể công bố capability như:

- semantic-model-v2.
- cancellation-support.
- workspace-edit-v2.
- streaming-generator.

Plugin khai báo capability cần và host kiểm tra trước khi chạy.

### 15.5 Deprecation

Khi API cũ sắp bị loại bỏ:

1. Đánh dấu deprecated.
2. Cung cấp API thay thế.
3. Nêu thời điểm dự kiến loại bỏ.
4. Giữ giai đoạn chuyển đổi.
5. Cung cấp migration guide.
6. Phát cảnh báo cho plugin vẫn dùng API cũ.

### 15.6 Binary compatibility

Trong Java, thay đổi constructor, method signature, visibility hoặc class hierarchy có thể làm plugin đã biên dịch không chạy được. Kiểm tra source compatibility chưa đủ; cần xem xét binary compatibility và dependency graph.

## 16. Cô lập plugin và quản lý lỗi

Một plugin lỗi không nên làm sập toàn bộ workbench nếu chức năng đó không phải thành phần bắt buộc.

### 16.1 Lỗi khởi tạo

Nếu plugin ném exception khi khởi tạo:

- Đánh dấu plugin FAILED.
- Ghi log ID và version.
- Hiển thị thông báo có thể hành động.
- Bỏ qua contribution của plugin đó.
- Giữ các plugin độc lập hoạt động.

### 16.2 Lỗi khi xử lý request

Host cần đặt ranh giới exception quanh lời gọi extension. Không để exception tùy ý thoát qua giao thức LSP hoặc UI event loop.

### 16.3 Timeout

Plugin xử lý request lâu có thể ảnh hưởng các plugin khác. Host có thể áp dụng timeout hoặc cancellation token, đặc biệt với request tương tác.

### 16.4 Circuit breaker

Nếu một extension liên tục thất bại khi gọi dịch vụ ngoài, host có thể tạm ngừng gọi nó và chuyển sang trạng thái degraded. Circuit breaker cần chính sách reset và hiển thị rõ.

### 16.5 ClassLoader isolation

Trong JVM, class loader riêng có thể giúp cô lập dependency và namespace. Tuy nhiên, class loader không phải sandbox bảo mật hoàn chỉnh. Mã plugin trong cùng process vẫn có thể truy cập tài nguyên mà process được phép.

### 16.6 Process isolation

Với plugin không đáng tin cậy, có thể chạy trong process riêng và giao tiếp qua RPC. Host có thể giới hạn quyền, thời gian và tài nguyên ở mức process hoặc container.

## 17. Security và quyền của extension

Plugin thường là mã có khả năng thực thi. Việc cài plugin tương đương đưa thêm mã vào môi trường làm việc.

Các nguyên tắc:

- Chỉ nạp plugin từ nguồn được tin cậy.
- Xác minh chữ ký hoặc checksum khi chính sách yêu cầu.
- Kiểm tra dependency và nguồn phân phối.
- Cấp quyền tối thiểu.
- Giới hạn file, mạng và process access.
- Không đưa secret không cần thiết vào context.
- Ghi nhận plugin ID/version trong audit.
- Có khả năng disable hoặc gỡ plugin.

### 17.1 Capability-based access

Thay vì cấp toàn quyền, host cung cấp capability cụ thể:

~~~text
Plugin A:
  read-project-model
  publish-diagnostics

Plugin B:
  read-schema-cache
  generate-artifacts
~~~

Plugin chỉ nên có quyền cần cho chức năng đã khai báo.

### 17.2 Trust boundary

Một extension chạy cùng process với host có thể có quyền lớn. Không nên coi interface Java là ranh giới bảo mật. Nếu plugin không tin cậy, cần sandbox hoặc process isolation thực sự.

### 17.3 Supply chain

Plugin có thể kéo theo dependency bắc cầu. Quản lý version, nguồn artifact, checksum và lỗ hổng dependency là một phần của bảo mật framework.

### 17.4 Secret handling

Không ghi token, mật khẩu hoặc credential vào log và diagnostic. Cấu hình plugin nên nhận secret thông qua secret provider hoặc handle được kiểm soát.

## 18. Hiệu năng và tài nguyên

Extension tăng khả năng của framework nhưng cũng tăng chi phí khởi tạo và xử lý.

### 18.1 Lazy loading

Plugin chỉ được nạp khi capability cần thiết được sử dụng. Cách này giảm thời gian startup và bộ nhớ cho những plugin ít dùng.

### 18.2 Caching

Plugin có thể cache kết quả, nhưng cache key cần bao gồm:

- Input version.
- Plugin version.
- Configuration version.
- DSL/model version.
- Dependency data.

Nếu thiếu một yếu tố, cache có thể trả kết quả cũ.

### 18.3 Incremental processing

Với editor, plugin nên xử lý phần thay đổi khi có thể thay vì quét toàn bộ workspace sau mỗi lần gõ.

### 18.4 Thread safety

Nếu một plugin instance được gọi đồng thời cho nhiều project, state bên trong phải thread-safe hoặc host cần tạo instance theo scope phù hợp.

### 18.5 Resource quotas

Host có thể giới hạn:

- Số worker.
- Thời gian xử lý.
- Bộ nhớ.
- Số diagnostic.
- Kích thước artifact.
- Số request đến dịch vụ ngoài.

### 18.6 Backpressure

Nếu extension tạo kết quả nhanh hơn consumer xử lý, queue có thể tăng vô hạn. Cần giới hạn queue hoặc điều tiết producer.

## 19. Extension và tính xác định

Kết quả framework không nên phụ thuộc ngẫu nhiên vào thứ tự nạp plugin hoặc thứ tự iteration của collection.

### 19.1 Deterministic discovery

Nếu nhiều plugin cùng loại được phát hiện, host nên sắp xếp theo quy tắc xác định hoặc dùng priority được khai báo.

### 19.2 Deterministic output

Generator plugin cần tạo output ổn định với cùng input và configuration. Tránh dùng timestamp, random hoặc iteration order không ổn định nếu không thuộc semantics.

### 19.3 Versioned configuration

Kết quả còn phụ thuộc cấu hình. Cần ghi nhận version hoặc fingerprint của profile để có thể tái lập.

### 19.4 Không để plugin âm thầm override

Nếu hai plugin cùng cung cấp một capability mà host chỉ cho phép một provider, việc chọn provider cần rõ ràng và quan sát được.

## 20. Kiểm thử extension

Extension cần được kiểm thử độc lập và trong môi trường host thực tế.

### 20.1 Unit test

Kiểm tra logic của plugin với dependency giả lập:

- Input hợp lệ.
- Input không hợp lệ.
- Cấu hình biên.
- Lỗi dịch vụ.
- Cancellation.
- Kết quả xác định.

### 20.2 Contract test

Contract test xác nhận plugin tuân theo API:

- Descriptor hợp lệ.
- Capability khai báo đúng.
- Không sửa input bất biến.
- Trả diagnostics theo schema.
- Hỗ trợ lifecycle yêu cầu.
- Xử lý cancellation.

### 20.3 Integration test

Chạy plugin trong host thật hoặc host test:

1. Discover.
2. Validate manifest.
3. Resolve dependency.
4. Load và initialize.
5. Đăng ký contribution.
6. Thực thi một request.
7. Dispose plugin.

### 20.4 Compatibility test

Chạy plugin đã biên dịch với các phiên bản API được hỗ trợ. Kiểm tra cả binary compatibility nếu hệ sinh thái dùng plugin JAR.

### 20.5 Failure isolation test

Tạo plugin cố ý ném exception, timeout hoặc không giải phóng tài nguyên. Xác nhận host cô lập lỗi và plugin độc lập vẫn hoạt động.

### 20.6 Security test

Kiểm tra quyền truy cập file, mạng, secret, class loading và giới hạn tài nguyên theo threat model của hệ thống.

### 20.7 UI test

Với workbench contribution, kiểm tra:

- Command xuất hiện đúng context.
- View được mở và dispose.
- Không block UI thread.
- Keyboard navigation.
- Trạng thái khi plugin bị disable.

## 21. Quản lý plugin trong workbench

Workbench thường cần giao diện quản lý extension.

Các chức năng có thể gồm:

- Danh sách plugin đã cài.
- Nhà cung cấp và version.
- Capability được cung cấp.
- Dependency và trạng thái tương thích.
- Enable/disable.
- Update.
- Uninstall.
- Xem log hoặc lỗi khởi tạo.
- Xem quyền được yêu cầu.

### 21.1 Trạng thái plugin

Có thể hiển thị:

| Trạng thái | Ý nghĩa |
|---|---|
| Available | Đã phát hiện nhưng chưa nạp |
| Enabled | Được cấu hình để sử dụng |
| Active | Đang hoạt động |
| Disabled | Bị tắt theo cấu hình |
| Incompatible | Không tương thích API/dependency |
| Failed | Lỗi khi load hoặc initialize |
| Stopping | Đang dừng |

Trạng thái này là mô hình UI minh họa.

### 21.2 Enable và disable

Disable plugin cần ngừng nhận công việc mới, hủy hoặc đợi task đang chạy, gỡ listener và giải phóng tài nguyên. Không nên chỉ ẩn contribution trên UI trong khi service vẫn hoạt động nền.

### 21.3 Update

Update plugin có thể yêu cầu restart workbench nếu class loader hoặc dependency đã được nạp. Cần hiển thị rõ khi nào update có hiệu lực.

### 21.4 Uninstall

Trước khi gỡ plugin, kiểm tra plugin khác có phụ thuộc vào nó không. Nếu có, cần cảnh báo hoặc yêu cầu gỡ dependency theo một thao tác có kiểm soát.

## 22. Migration và nâng cấp framework

Framework cần chiến lược nâng cấp để plugin không bị hỏng bất ngờ.

### 22.1 Public API surface

Chỉ công bố những interface và class cần thiết cho extension. Các package nội bộ không nên được xem là API ổn định.

### 22.2 Compatibility adapter

Khi API mới thay đổi cấu trúc, host có thể cung cấp adapter cho plugin cũ trong giai đoạn chuyển đổi.

### 22.3 Migration tool

Có thể cung cấp công cụ:

- Tìm API deprecated.
- Đổi package hoặc method.
- Cập nhật manifest version.
- Chuyển cấu hình cũ sang schema mới.
- Kiểm tra dependency.

### 22.4 Không hỗ trợ vô thời hạn mọi API cũ

Duy trì compatibility có chi phí. Framework nên công bố thời gian hỗ trợ và chính sách loại bỏ rõ ràng để plugin developer có kế hoạch.

### 22.5 Migration theo capability

Nếu plugin chỉ dùng capability không thay đổi, host có thể tiếp tục hỗ trợ nó qua nhiều minor version. Capability negotiation giúp giảm phụ thuộc vào một version number duy nhất.

## 23. Ví dụ tổng hợp: mở rộng DSL workbench bằng plugin phê duyệt

Giả sử framework có DSL workflow:

~~~text
workflow "Purchase"
  start Request
  task Validate
  task Pay
  end Completed
~~~

Một tổ chức muốn thêm node Approval và view theo dõi người phê duyệt.

### 23.1 Các extension point cần dùng

- Grammar hoặc model extension để nhận diện node Approval.
- Semantic validator để kiểm tra người phê duyệt.
- Editor contribution để hiển thị property.
- Runtime adapter để gửi yêu cầu phê duyệt.
- View contribution để theo dõi trạng thái.

### 23.2 Model contribution

Plugin cung cấp kiểu node:

~~~java
public interface WorkflowNodeProvider {
    String nodeKind();

    NodeDescriptor descriptor();
}
~~~

Descriptor mô tả label, properties, icon hoặc editor metadata theo API của framework.

### 23.3 Validator

~~~java
public final class ApprovalValidator implements ModelValidator {
    @Override
    public ValidatorDescriptor descriptor() {
        return new ValidatorDescriptor(
            "company.approval-owner",
            "Approval owner required"
        );
    }

    @Override
    public void validate(
        SemanticModel model,
        ValidationContext context,
        DiagnosticReporter reporter
    ) {
        for (ApprovalNode node : model.nodesOfType(ApprovalNode.class)) {
            if (node.approver().isEmpty()) {
                reporter.error(
                    "Approval node must define an approver.",
                    node.sourceRange()
                );
            }
        }
    }
}
~~~

Đây là API minh họa. Trong framework thực tế, node type có thể được tạo qua model factory hoặc extension schema thay vì class trực tiếp.

### 23.4 View contribution

Plugin đăng ký view Approval Monitor. View đọc trạng thái qua service được host cấp và không tự truy cập database bằng credential riêng nếu không cần.

### 23.5 Lifecycle

Khi workbench mở project:

1. Host kiểm tra plugin manifest.
2. Resolve dependency đến workflow model API.
3. Khởi tạo plugin.
4. Đăng ký node provider, validator và view.
5. Khi project đóng, hủy listener và giải phóng tài nguyên.

### 23.6 Kiểm tra lỗi

Nếu Approval Monitor không khởi tạo được, validator và node provider vẫn có thể hoạt động nếu chúng là contribution độc lập. Host hiển thị view ở trạng thái lỗi và ghi log nguyên nhân.

Ví dụ cho thấy một plugin có thể mở rộng nhiều lớp của workbench, nhưng mỗi contribution vẫn đi qua extension point và lifecycle rõ ràng.

## 24. Những sai lầm thường gặp

### Công bố quá nhiều internal API

Plugin phụ thuộc vào chi tiết nội bộ khiến core khó thay đổi.

**Cách khắc phục:** công bố API hẹp, có mục đích và tài liệu hóa hợp đồng.

### Extension point không có lifecycle

Plugin đăng ký listener hoặc thread nhưng không biết khi nào phải dừng.

**Cách khắc phục:** định nghĩa initialize, activate, deactivate và dispose.

### Nạp plugin trước khi kiểm tra dependency

Plugin có thể crash vì thiếu service hoặc API version.

**Cách khắc phục:** validate manifest và resolve dependency trước activation.

### Dùng thứ tự discovery ngẫu nhiên

Kết quả có thể khác giữa các lần chạy.

**Cách khắc phục:** khai báo priority/dependency và có tie-breaker ổn định.

### Cho plugin quyền quá rộng

Plugin có thể đọc secret hoặc sửa file không liên quan.

**Cách khắc phục:** capability-based access và process isolation khi cần.

### Coi class loader là sandbox

Class loader chỉ quản lý namespace và dependency, không phải ranh giới bảo mật hoàn chỉnh.

**Cách khắc phục:** dùng process/container isolation cho mã không tin cậy.

### Không cô lập lỗi

Một plugin ném exception có thể làm sập event loop hoặc request handler.

**Cách khắc phục:** đặt error boundary và quản lý trạng thái FAILED.

### Không có compatibility policy

API thay đổi làm plugin cũ hỏng mà không có cảnh báo.

**Cách khắc phục:** versioning, capability negotiation, deprecation và migration guide.

### Chạy công việc nặng trên UI thread

Workbench bị treo khi plugin phân tích project lớn.

**Cách khắc phục:** background executor, cancellation và cập nhật UI qua API phù hợp.

### Không dọn contribution khi disable

Listener, command và view vẫn giữ reference đến plugin.

**Cách khắc phục:** quản lý subscription và disposal tập trung.

## 25. Quy trình thiết kế framework extensible

Khi xây dựng framework hoặc workbench có thể mở rộng, có thể thực hiện:

1. **Xác định biến thể:** liệt kê phần nào cần thay đổi giữa dự án, tổ chức hoặc target.
2. **Giữ invariant trong core:** các quy tắc cần luôn đúng thuộc phần lõi.
3. **Chọn extension point:** interface, provider, event, strategy, adapter hoặc UI contribution.
4. **Thiết kế contract:** input, output, lifecycle, concurrency, cancellation và error handling.
5. **Định danh capability:** plugin ID, API version và dependency.
6. **Xây registry/discovery:** tìm, validate và đăng ký extension theo quy tắc xác định.
7. **Quản lý lifecycle:** load, initialize, activate, stop và dispose.
8. **Cung cấp context tối thiểu:** dependency injection và quyền theo capability.
9. **Định nghĩa composition:** thứ tự, priority và xử lý conflict.
10. **Bảo vệ host:** timeout, cancellation, resource limits và error isolation.
11. **Quản lý compatibility:** semantic versioning, capability negotiation và migration.
12. **Tích hợp workbench:** command, view, editor contribution và accessibility.
13. **Kiểm thử:** unit, contract, integration, compatibility, security và failure isolation.
14. **Quan sát:** log, metrics và trạng thái plugin trong UI.

Hãy bắt đầu từ những extension point thực sự cần thiết. Một framework không cần plugin hóa mọi class; mở rộng quá mức có thể làm API phức tạp và khiến việc hiểu hệ thống khó hơn.

## 26. Câu hỏi tự kiểm tra

1. Khả năng mở rộng framework khác việc sửa trực tiếp core như thế nào?
2. Phân biệt library, framework, plugin và workbench.
3. Extension point cần quy định những phần nào của contract?
4. Khi nào nên dùng interface, strategy, event listener hoặc adapter?
5. Plugin manifest thường chứa metadata gì?
6. Discovery, validation, loading và activation khác nhau ra sao?
7. Dependency injection giúp plugin dễ kiểm thử như thế nào?
8. Vì sao dependency cycle cần được phát hiện trước activation?
9. Framework kết hợp nhiều validator hoặc generator theo quy tắc nào?
10. Extension cho compiler khác extension cho UI workbench ở điểm nào?
11. Vì sao class loader không phải sandbox bảo mật hoàn chỉnh?
12. Capability-based access giúp giảm quyền plugin như thế nào?
13. Semantic versioning và capability negotiation hỗ trợ compatibility ra sao?
14. Khi disable plugin cần giải phóng những contribution nào?
15. Những test nào giúp xác nhận plugin không làm sập host?
16. Vì sao thứ tự nạp plugin cần xác định?
17. Làm thế nào để plugin xử lý cancellation và task chạy lâu?
18. Khi nào nên dùng process isolation cho plugin?

Khả năng mở rộng framework cho phép một nền tảng DSL phục vụ nhiều nhu cầu mà vẫn giữ phần lõi ổn định. Khi extension point, contract, lifecycle, dependency, quyền truy cập và compatibility được thiết kế rõ, plugin có thể bổ sung chức năng cho compiler và workbench mà không làm hệ thống trở nên khó dự đoán hoặc khó nâng cấp.
