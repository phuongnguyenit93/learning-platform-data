# Mẫu thiết kế lõi ổn định và plugin cho DSL

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường bắt đầu với một lõi nhỏ: grammar, type system, parser, compiler hoặc interpreter và một runtime tối thiểu. Khi DSL được dùng trong nhiều miền nghiệp vụ, mỗi nhóm có thể cần thêm kiểu dữ liệu, hàm, validator, backend, connector hoặc công cụ riêng. Nếu mọi nhu cầu đều được đưa thẳng vào lõi, ngôn ngữ sẽ phình to, khó kiểm thử và khó giữ tương thích. Nếu mỗi nhóm tự sửa lõi hoặc fork riêng, hệ sinh thái lại bị phân mảnh.

Mẫu thiết kế **lõi ổn định và plugin** (*stable core and plugins*) giải quyết bài toán này bằng cách giữ một phần nền tảng nhỏ, có hợp đồng rõ và thay đổi có kiểm soát, đồng thời cung cấp các điểm mở rộng để plugin bổ sung năng lực theo miền. Lõi sở hữu semantics chung và vòng đời thực thi; plugin sở hữu những khả năng chuyên biệt, được đăng ký qua API công khai.

Mục tiêu không phải làm cho lõi bất biến. Lõi vẫn cần phát triển, nhưng thay đổi phải có chủ đích và có chính sách tương thích. Plugin cũng không phải nơi chứa mọi thứ. Một chức năng chỉ nên trở thành plugin khi nó thực sự là phần mở rộng có ranh giới, dependency và vòng đời riêng. Thiết kế tốt giúp DSL vừa có nền tảng nhất quán, vừa có thể thích ứng với nhiều use case mà không buộc mọi người dùng phải mang theo mọi tính năng.

## 1. Ý tưởng của stable core and plugins

### 1.1. Lõi ổn định

Stable core là tập thành phần tối thiểu định nghĩa bản chất của DSL:
- Lexical grammar và parser contract.
- AST hoặc IR cơ bản.
- Type system và semantics chung.
- Evaluation model.
- Diagnostic model.
- Extension API và lifecycle contract.
- Cơ chế cấu hình và capability chung.

Lõi cần nhỏ đủ để hiểu, kiểm thử và duy trì. Nó chứa những quy tắc mà mọi chương trình DSL cần dựa vào.

### 1.2. Plugin

Plugin là đơn vị mở rộng được host phát hiện và nạp qua một hợp đồng. Plugin có thể bổ sung:
- Domain type và function.
- Validator.
- Data connector.
- Compiler backend.
- Code generator.
- Editor feature.
- Runtime action.
- Formatter hoặc linter rule.
- CLI command.

Plugin không nên thay đổi semantics lõi một cách ngầm định. Nếu muốn thay đổi behavior chung, cần đề xuất sửa core hoặc cung cấp một extension point được thiết kế rõ.

### 1.3. Vì sao cần tách?

Tách core và plugin giúp:
- Giảm số dependency bắt buộc.
- Cho phép cài capability theo nhu cầu.
- Giảm ảnh hưởng khi plugin lỗi.
- Dễ phát triển và phát hành độc lập.
- Hạn chế xung đột giữa các miền.
- Giữ semantics chung nhất quán.
- Tạo ranh giới để kiểm soát quyền và version.

### 1.4. Lõi ổn định không có nghĩa là ít thay đổi bằng mọi giá

Nếu một thiết kế core sai, cần sửa. Nhưng thay đổi phải dựa trên use case rộng, compatibility impact và chi phí bảo trì. Không nên thêm abstraction chỉ để tránh mọi thay đổi; abstraction quá mức cũng làm core phức tạp.

### 1.5. Plugin không phải fork

Fork sao chép và duy trì một phiên bản riêng của core. Plugin mở rộng core qua public API. Plugin thường có thể nâng cấp độc lập hơn, nhưng chỉ trong phạm vi extension point mà core hỗ trợ.

## 2. Xác định ranh giới giữa core và plugin

### 2.1. Câu hỏi phân loại

Khi một tính năng mới được đề xuất, hãy hỏi:
1. Tính năng có cần thiết cho mọi chương trình DSL không?
2. Nó định nghĩa semantics chung hay chỉ một domain capability?
3. Nó có dependency đặc thù như database driver hoặc cloud SDK không?
4. Nó có thể được cài hoặc bỏ mà không làm thay đổi ý nghĩa chương trình hiện có không?
5. Nó có cần release cadence riêng không?
6. Nó có yêu cầu quyền hoặc tài nguyên riêng không?
7. Nhiều plugin có thể cung cấp cùng một loại capability không?

### 2.2. Đưa vào core khi

Một chức năng thường thuộc core nếu:
- Là nền tảng để parse, type-check hoặc evaluate mọi chương trình.
- Là một phần không thể tách khỏi semantics chính thức.
- Cần được hỗ trợ đồng nhất trên mọi backend.
- Không thể mô hình hóa hợp lý qua extension API.
- Có dependency tối thiểu và ổn định.

Ví dụ: source span trong diagnostic, kiểu Boolean cơ bản hoặc quy tắc precedence của operator cốt lõi.

### 2.3. Đưa vào plugin khi

Một chức năng thường phù hợp với plugin nếu:
- Chỉ phục vụ một miền hoặc một nhóm người dùng.
- Có dependency riêng.
- Có thể được bật/tắt độc lập.
- Có lifecycle hoặc release cycle riêng.
- Có thể mô tả qua contract ổn định.
- Không cần thay đổi grammar hoặc semantics chung.

Ví dụ: connector PostgreSQL, hàm tính thuế theo một thị trường hoặc backend sinh cấu hình cho một nền tảng.

### 2.4. Vùng trung gian

Một số khả năng được nhiều người dùng cần nhưng không phải semantics bắt buộc. Có thể cung cấp plugin chính thức do cùng nhóm duy trì, hoặc một package chuẩn được phát hành cùng core nhưng vẫn giữ ranh giới module.

### 2.5. Không biến mọi function thành plugin

Nếu một helper nhỏ không có dependency, không cần lifecycle và được dùng rộng rãi, việc tách thành plugin có thể tạo overhead không cần thiết. Mục tiêu là ranh giới có ý nghĩa, không phải tối đa số plugin.

## 3. Kiến trúc tổng thể

### 3.1. Host và plugin

Host là ứng dụng DSL chịu trách nhiệm:
- Đọc manifest.
- Kiểm tra version và dependency.
- Cấp context và capability.
- Nạp plugin.
- Quản lý lifecycle.
- Tiếp nhận extension registration.
- Gọi extension khi cần.
- Thu diagnostic và telemetry.

Plugin triển khai capability đã công bố và tuân thủ contract.

### 3.2. Sơ đồ kiến trúc

~~~mermaid
flowchart TD
    A["DSL Host"] --> B["Stable Core"]
    B --> C["Parser / AST / Type System"]
    B --> D["Runtime / Diagnostics"]
    B --> E["Plugin Manager"]
    E --> F["Extension Registry"]
    F --> G["Domain Plugin"]
    F --> H["Database Plugin"]
    F --> I["Backend Plugin"]
    F --> J["Editor Plugin"]
    G --> K["Core Services"]
    H --> K
    I --> K
    J --> K
~~~

### 3.3. Dependency direction

Core định nghĩa abstraction và contract. Plugin phụ thuộc vào contract của core. Core không import implementation cụ thể của plugin.

~~~text
Core API <---- Plugin A
Core API <---- Plugin B
Core API <---- Plugin C
~~~

Nếu core cần gọi một plugin, nó gọi qua interface/registry đã công bố, không phụ thuộc class implementation của plugin.

### 3.4. Plugin manager

Plugin manager quản lý discovery, validation, dependency resolution, loading, activation, deactivation và disposal. Nó không nên chứa logic nghiệp vụ riêng của từng plugin.

### 3.5. Extension registry

Registry lưu capability được đăng ký theo extension point. Registry cần kiểm tra tên trùng, chữ ký, version, priority và quyền.

### 3.6. Runtime boundary

Plugin có thể chạy in-process, process riêng hoặc sandbox. Mô hình thực thi cần dựa trên trust level, hiệu năng và quyền cần thiết.

## 4. Thiết kế core nhỏ và ổn định

### 4.1. Trách nhiệm cốt lõi

Core nên tập trung vào:
- Đọc và parse source.
- Tạo AST/IR chuẩn.
- Kiểm tra kiểu và semantics chung.
- Quản lý symbol và scope.
- Tạo diagnostic chuẩn.
- Xây dựng execution plan.
- Điều phối extension qua API.
- Quản lý cancellation và resource budget.

### 4.2. Tránh domain logic trong core

Không đưa quy tắc thuế, shipping, thanh toán hoặc schema của một khách hàng vào core nếu chúng không thuộc semantics chung. Những phần này nên nằm trong plugin hoặc domain module.

### 4.3. Public API và internal API

Phân biệt:
- Public extension API: có tài liệu và compatibility policy.
- Internal implementation: có thể thay đổi trong release theo quy trình nội bộ.

Plugin chỉ nên dùng public API. Nếu plugin phải truy cập private class hoặc field nội bộ, ranh giới core chưa tốt.

### 4.4. Minimal stable interfaces

Interface nên nhỏ và có mục đích. Một interface khổng lồ chứa mọi service khiến plugin phụ thuộc quá sâu và khó tương thích.

### 4.5. Immutable model

AST, type descriptor và execution plan có thể được giữ immutable sau khi compile. Plugin nhận view hoặc context thay vì sửa cấu trúc đang dùng chung.

### 4.6. Core compatibility

Core cần định nghĩa version API, IR và lifecycle. Thay đổi interface hoặc semantics phải đi qua review và migration policy.

### 4.7. Core không nên biết plugin cụ thể

Nếu code core có điều kiện kiểu if pluginId == "vendor.database", đó là dấu hiệu dependency ngược. Hãy dùng capability interface hoặc provider registration.

## 5. Extension point

### 5.1. Extension point là gì?

Extension point là vị trí được thiết kế để plugin bổ sung hành vi. Ví dụ:
- FunctionProvider.
- TypeProvider.
- Validator.
- CodeGenerator.
- DataSourceProvider.
- CompletionProvider.
- FormatterRule.
- RuntimeAction.

### 5.2. Contract

Mỗi extension point cần xác định:
- Input và output type.
- Lifecycle.
- Thread safety.
- Error behavior.
- Timeout và cancellation.
- Capability yêu cầu.
- Version compatibility.
- Thứ tự hoặc priority.
- Quy tắc conflict.

### 5.3. Registration

Plugin đăng ký extension qua registry được host cấp:

~~~java
public interface DslPlugin {
    PluginDescriptor descriptor();
    void initialize(PluginContext context);
    void registerExtensions(ExtensionRegistry registry);
    void dispose();
}
~~~

Đây là interface minh họa. API thực tế cần quy định exception và concurrency semantics.

### 5.4. Không cho registration tùy tiện

Host có thể chỉ cho phép đăng ký trong giai đoạn initialize hoặc register. Sau khi registry được đóng băng, plugin không được thay đổi extension giữa một lần evaluation trừ khi host hỗ trợ dynamic update có kiểm soát.

### 5.5. Extension metadata

Mỗi extension có thể công bố:
- ID.
- Version.
- Tên hiển thị.
- Chữ ký.
- Capability.
- Tính chất pure/side effect.
- Target hoặc language version.
- Documentation reference.

### 5.6. Version hóa extension point

Extension point cũng là API công khai. Nếu thay đổi input/output hoặc lifecycle, cần deprecation và version compatibility tương ứng.

## 6. Các loại extension phổ biến

### 6.1. Function provider

Bổ sung function DSL:
~~~text
commerce.calculateTax(order)
money.convert(amount, targetCurrency)
~~~

Provider công bố chữ ký và semantics để compiler type-check, runtime dispatch.

### 6.2. Type provider

Bổ sung domain type như Money, CustomerId hoặc Address. Type provider cần định nghĩa equality, serialization, operator và constraint nếu được hỗ trợ.

### 6.3. Validator

Kiểm tra quy tắc miền:
- Workflow có trạng thái kết thúc.
- Order không chứa item trùng.
- Một field bắt buộc phải được khai báo.
- Policy không có nhánh unreachable.

Validator trả diagnostic theo schema chung.

### 6.4. Data connector

Kết nối database, API hoặc message broker. Connector công bố schema, capability query, transaction, pagination và authentication.

### 6.5. Backend

Chuyển IR sang SQL, Java, bytecode hoặc target khác. Backend công bố capability và báo lỗi nếu gặp node không hỗ trợ.

### 6.6. Editor extension

Bổ sung completion, hover, code action, formatter hoặc semantic token cho domain-specific construct.

### 6.7. CLI extension

Thêm lệnh kiểm tra, export, migration hoặc deploy. Lệnh cần dùng chung cấu hình và diagnostic model của host.

### 6.8. Observability extension

Cung cấp metrics, trace hoặc audit adapter. Plugin cần tuân thủ data minimization và không log secret.

## 7. Ports and adapters và dependency inversion

### 7.1. Ports and adapters

Ports and adapters (còn gọi là Hexagonal Architecture) đặt abstraction ở ranh giới core. Core định nghĩa port; plugin hoặc adapter triển khai port để kết nối hệ thống ngoài.

~~~text
          Database Plugin
                 |
                 v
       +-------------------+
       |     Core Port     |
       +-------------------+
                 |
                 v
       +-------------------+
       |   DSL Runtime     |
       +-------------------+
~~~

### 7.2. Input port

Input port cho phép host hoặc ứng dụng gọi core:
- Parse source.
- Compile model.
- Evaluate rule.
- Validate document.

### 7.3. Output port

Output port cho phép core sử dụng dịch vụ bên ngoài:
- Data access.
- Clock.
- Logging.
- Secret provider.
- External function.
- Artifact storage.

### 7.4. Dependency inversion

Module cấp cao không phụ thuộc trực tiếp module cấp thấp. Cả hai phụ thuộc abstraction. Core không cần biết connector cụ thể là PostgreSQL hay HTTP.

### 7.5. Adapter

Adapter chuyển contract chung thành API cụ thể của hệ thống ngoài. Ví dụ SQL adapter chuyển QueryPlan thành prepared statement và parameter binding.

### 7.6. Không trừu tượng hóa quá sớm

Chỉ tạo port khi có ranh giới thực sự cần thay đổi hoặc nhiều implementation. Interface không có consumer thứ hai và không có nhu cầu thay thế có thể chỉ làm tăng độ phức tạp.

## 8. Dependency và plugin manifest

### 8.1. Manifest

Manifest mô tả plugin mà không cần thực thi code:

~~~yaml
id: com.example.dsl.commerce
name: Commerce Extension
version: 2.1.0
apiVersion: 3
requires:
  host: ">= 4.0 < 5.0"
  plugins:
    - id: com.example.dsl.money
      version: "^2.0"
entrypoint: plugins/commerce.jar
capabilities:
  - dsl.functions.register
  - dsl.validators.register
~~~

### 8.2. Dependency graph

Plugin có thể phụ thuộc plugin khác. Manager xây dependency graph, phát hiện cycle và xác định thứ tự khởi tạo.

### 8.3. Optional dependency

Một capability có thể chỉ hoạt động khi plugin tùy chọn có mặt. Plugin cần kiểm tra capability trước khi dùng thay vì giả định dependency luôn được cài.

### 8.4. Conflict resolution

Nếu hai plugin yêu cầu hai version không tương thích, manager cần từ chối, cô lập classloader/process hoặc áp dụng policy rõ. Không nạp tùy tiện theo thứ tự tìm thấy.

### 8.5. Lockfile

Project có thể khóa plugin version và checksum để build và runtime tái lập. Không tự động resolve latest trong production.

### 8.6. Plugin discovery

Discovery tìm manifest trong nguồn được cấu hình. Discovery không đồng nghĩa loading; cần kiểm tra signature, compatibility và trust policy trước khi thực thi.

## 9. Lifecycle và trạng thái plugin

### 9.1. Các trạng thái

Một lifecycle có thể gồm:
1. Discovered.
2. Validated.
3. Resolved.
4. Loaded.
5. Initialized.
6. Registered.
7. Active.
8. Deactivated.
9. Disposed.

### 9.2. Initialize

Host truyền PluginContext chứa logger, config, service facade, capability, cancellation token và API version.

### 9.3. Register

Plugin đăng ký extension theo contract. Host kiểm tra duplicate ID, signature, capability và priority.

### 9.4. Activate

Plugin có thể mở connection pool hoặc khởi tạo index. Chỉ tạo resource cần thiết khi plugin thực sự được dùng.

### 9.5. Deactivate

Ngừng nhận request mới, chờ hoặc hủy task đang chạy theo policy, đóng resource và gỡ extension nếu an toàn.

### 9.6. Dispose

Giải phóng connection, thread, file handle và cache do plugin sở hữu. Dispose cần idempotent nếu host có thể gọi lại sau lỗi.

### 9.7. Lifecycle failure

Nếu initialize thất bại, plugin không được đánh dấu active. Host cần giải phóng resource đã tạo và báo diagnostic có plugin ID cùng giai đoạn lỗi.

## 10. Cô lập và bảo mật plugin

### 10.1. In-process

Plugin chạy cùng tiến trình:
- Gọi API nhanh.
- Dễ chia sẻ object.
- Lỗi hoặc memory corruption có thể ảnh hưởng host.
- Quyền của plugin gần với quyền process.

### 10.2. Out-of-process

Plugin chạy process riêng:
- Có ranh giới crash và resource tốt hơn.
- Có thể dùng ngôn ngữ khác.
- Cần IPC, serialization và timeout.
- Phải xác thực peer và kiểm tra message.

### 10.3. Sandbox

WebAssembly hoặc restricted runtime có thể giới hạn host imports, memory và execution time. Chỉ cấp capability cần thiết.

### 10.4. Least privilege

Plugin formatter không cần quyền database; validator không cần quyền gửi email. Cấp quyền theo capability cụ thể.

### 10.5. Plugin supply chain

Xác minh package source, checksum, signature, dependency và SBOM. Chỉ activate plugin từ nguồn tin cậy.

### 10.6. Secret handling

Không nhúng secret vào manifest hoặc plugin package. Truyền secret qua provider do host quản lý và chỉ khi plugin được cấp quyền.

### 10.7. Error boundary

Exception của plugin cần được chuyển thành error có cấu trúc. Không để lỗi plugin làm hỏng toàn bộ host nếu có thể cách ly.

## 11. Tương thích giữa core và plugin

### 11.1. Nhiều version

Có thể có:
- Product version.
- Core API version.
- DSL language version.
- IR version.
- Plugin version.
- Plugin API version.

Không giả định chúng tăng cùng nhau.

### 11.2. Compatibility range

Manifest khai báo host và API version được hỗ trợ. Plugin manager kiểm tra trước khi nạp.

### 11.3. Semantic compatibility

Plugin có thể compile với API mới nhưng vẫn hoạt động sai nếu semantics thay đổi. Contract test cần kiểm tra behavior, không chỉ method signature.

### 11.4. Deprecation

Khi extension API sắp bị loại bỏ:
1. Đánh dấu deprecated.
2. Cung cấp API thay thế.
3. Ghi migration guide.
4. Cảnh báo khi plugin cũ được nạp.
5. Chờ support window.
6. Loại bỏ theo major version hoặc policy.

### 11.5. Core evolution

Core nên giữ API ổn định trong phạm vi cam kết. Nếu cần thay đổi breaking, cần adapter hoặc migration layer trong thời gian chuyển tiếp.

### 11.6. Conformance tests

Host có thể cung cấp test kit để plugin xác minh manifest, lifecycle, registration, cancellation, errors và disposal.

## 12. Registry, namespace và conflict

### 12.1. Namespace

Namespace tránh trùng tên:
~~~text
commerce.calculateTax(order)
finance.calculateTax(invoice)
~~~

### 12.2. Stable extension ID

Extension ID nên ổn định và không phụ thuộc display name. Rename không nên làm mất dependency hoặc config.

### 12.3. Duplicate registration

Nếu hai plugin đăng ký cùng ID hoặc cùng function signature, host cần từ chối hoặc yêu cầu cấu hình tường minh.

### 12.4. Priority

Một số extension point như completion provider có thể kết hợp nhiều kết quả. Priority cần được xác định và có thể tái lập.

### 12.5. Override

Không cho plugin override built-in âm thầm. Nếu hỗ trợ override, cần khai báo capability, policy và diagnostics rõ.

### 12.6. Registry freeze

Sau giai đoạn registration, host có thể đóng băng registry để execution plan ổn định. Dynamic registration cần cơ chế version và invalidation cache.

## 13. Cấu hình và khả năng bật/tắt

### 13.1. Plugin configuration

Mỗi plugin có schema cấu hình riêng:
~~~yaml
plugins:
  com.example.dsl.sql:
    dialect: postgresql
    batchSize: 500
~~~

### 13.2. Configuration validation

Host validate cấu hình theo schema plugin công bố. Trường không biết có thể bị từ chối hoặc cảnh báo theo policy.

### 13.3. Global và project scope

Plugin có thể được cài toàn cục nhưng chỉ bật trong workspace cụ thể. Project configuration và lockfile giúp tái tạo tập plugin.

### 13.4. Feature flag

Feature flag có thể bật capability thử nghiệm mà không thay toàn bộ plugin package. Cần phân biệt feature flag với quyền bảo mật; flag không thay authorization.

### 13.5. Disable behavior

Khi plugin bị tắt, host cần xác định:
- Query phụ thuộc plugin có bị từ chối không?
- Có fallback không?
- Artifact cũ có còn chạy không?
- Có cần restart runtime không?

Không nên âm thầm bỏ qua dependency bắt buộc.

## 14. Testing cho stable core và plugin

### 14.1. Core tests

Kiểm tra grammar, type system, semantics, AST/IR contract, lifecycle manager và extension registry.

### 14.2. Plugin contract tests

Kiểm tra:
- Manifest schema.
- API compatibility.
- Initialize/register/dispose.
- Error handling.
- Thread safety.
- Cancellation và timeout.
- Capability enforcement.

### 14.3. Integration tests

Nạp plugin vào host thật và chạy một DSL program sử dụng extension. Xác nhận compile, runtime và diagnostics.

### 14.4. Compatibility matrix

Test các tổ hợp host version, plugin API version và plugin version được công bố hỗ trợ.

### 14.5. Conflict tests

Nạp hai plugin cùng đăng ký tên hoặc extension point để xác nhận conflict policy.

### 14.6. Isolation tests

Mô phỏng plugin crash, timeout hoặc vượt resource. Kiểm tra host và plugin khác vẫn hoạt động theo policy.

### 14.7. Reproducibility tests

Cùng lockfile phải nạp cùng plugin set và tạo cùng execution behavior.

### 14.8. Core regression

Thêm plugin không nên làm thay đổi behavior của chương trình chỉ dùng core. Giữ regression suite cho core-only use case.

## 15. Observability và vận hành

### 15.1. Plugin identity

Log cần ghi plugin ID, version, host version và operation. Điều này giúp xác định nguồn lỗi.

### 15.2. Metrics

Có thể theo dõi:
- Initialize/dispose duration.
- Request count.
- Latency.
- Error và timeout.
- Restart.
- Memory/CPU nếu đo được.

### 15.3. Health check

Plugin connector hoặc service có thể cung cấp health check nhẹ. Health check không nên tạo side effect.

### 15.4. Audit

Ghi lại install, enable, disable, upgrade và capability grant. Không log secret hoặc raw payload nhạy cảm.

### 15.5. Degraded mode

Nếu plugin optional bị lỗi, host có thể tiếp tục với core capability và báo rõ phần nào không khả dụng. Nếu plugin bắt buộc, từ chối tác vụ phụ thuộc.

## 16. Ví dụ: core ổn định với plugin function

### 16.1. Core contract

Core định nghĩa function provider interface:

~~~java
public interface DslFunction {
    FunctionSignature signature();
    Value invoke(InvocationContext context, List<Value> arguments);
}
~~~

Interface này mô tả cách gọi function, không biết logic thuế hay shipping.

### 16.2. Plugin implementation

~~~java
public final class TaxFunctionPlugin implements DslPlugin {
    private TaxService taxService;

    @Override
    public void initialize(PluginContext context) {
        this.taxService = context.requireService(TaxService.class);
    }

    @Override
    public void registerExtensions(ExtensionRegistry registry) {
        registry.registerFunction(
            "commerce.calculateTax",
            FunctionSignature.of(Type.ORDER, Type.MONEY),
            invocation -> taxService.calculate(
                invocation.argument(0, Order.class)
            )
        );
    }

    @Override
    public void dispose() {
        // Giải phóng resource do plugin sở hữu.
    }
}
~~~

Mã chỉ minh họa một API giả định. Host cần kiểm soát capability, exception và cancellation.

### 16.3. DSL usage

~~~text
rule OrderTax {
    when order.status == CONFIRMED
    then tax = commerce.calculateTax(order)
}
~~~

Compiler lấy chữ ký từ registry. Runtime dispatch đến implementation đã đăng ký.

### 16.4. Lợi ích ranh giới

Core không cần import TaxService hoặc biết cách tính thuế. Plugin có thể được nâng cấp riêng nếu vẫn tương thích với function contract.

## 17. Ví dụ: plugin backend

### 17.1. Backend contract

~~~text
CodeGenerator.generate(
    validatedIR,
    targetOptions,
    outputSink
) -> GenerationResult
~~~

### 17.2. Capability declaration

Backend công bố node IR và feature được hỗ trợ. Nếu gặp node không hỗ trợ, nó trả diagnostic thay vì bỏ qua.

### 17.3. Đăng ký backend

Host registry backend theo target ID như sql, java hoặc wasm. CLI chọn backend từ danh sách được cài và được phép.

### 17.4. Tương thích IR

Backend cần khai báo IR version range. Core không nên thay đổi IR mà không có migration hoặc compatibility policy.

## 18. Những anti-pattern thường gặp

### 18.1. Fat core

Đưa mọi domain function và connector vào core làm tăng dependency, kích thước và chi phí release. Hãy tách phần chuyên biệt thành plugin.

### 18.2. Leaky abstraction

Plugin phải truy cập internal class để làm việc cho thấy extension API chưa đủ hoặc ranh giới không rõ. Cần bổ sung public contract thay vì để plugin phụ thuộc nội bộ.

### 18.3. Core imports plugin

Core import implementation của plugin tạo dependency ngược và khiến plugin không thể được bỏ độc lập. Dùng registry và interface do core sở hữu.

### 18.4. God Plugin API

Một context chứa toàn bộ host services làm plugin có quyền quá rộng và phụ thuộc nhiều chi tiết. Chia service facade và capability nhỏ.

### 18.5. Dynamic behavior không version hóa

Cho phép plugin thay đổi registry giữa runtime mà không có version hoặc cache invalidation có thể làm execution không tái lập.

### 18.6. Silent override

Plugin ghi đè built-in hoặc plugin khác theo thứ tự load tạo behavior khó đoán. Conflict phải được phát hiện và giải quyết tường minh.

### 18.7. Optional dependency bị coi là bắt buộc

Plugin có thể hoạt động khi dependency có mặt trên máy developer nhưng thất bại ở production. Manifest và capability check cần phân biệt optional/required.

### 18.8. Không có contract test

Plugin có thể compile nhưng vi phạm lifecycle hoặc error contract. Cần test kit và compatibility matrix.

### 18.9. Chia plugin quá nhỏ

Mỗi helper thành một plugin làm tăng dependency graph và overhead. Nhóm các capability có cohesion và lifecycle chung.

### 18.10. Chia plugin quá lớn

Một plugin chứa nhiều domain không liên quan sẽ khó release và cấp quyền. Tách theo capability và ownership thực tế.

## 19. Quy trình thiết kế stable core và plugin

Một quy trình có thể gồm:
1. **Xác định semantics bắt buộc:** những gì mọi chương trình DSL cần.
2. **Lập ranh giới core:** grammar, type system, AST/IR, runtime contract và diagnostics.
3. **Liệt kê nhu cầu mở rộng:** function, type, validator, connector, backend và editor feature.
4. **Chọn extension point:** chỉ tạo điểm mở rộng có use case và contract rõ.
5. **Định nghĩa dependency direction:** plugin phụ thuộc core API; core không phụ thuộc implementation plugin.
6. **Thiết kế registry và manifest:** ID, version, dependency, capability và entry point.
7. **Thiết kế lifecycle:** initialize, register, activate, deactivate và dispose.
8. **Chọn isolation model:** in-process, process riêng hoặc sandbox theo trust.
9. **Định nghĩa conflict policy:** namespace, duplicate ID, priority và override.
10. **Định nghĩa compatibility:** core API, IR, plugin API và version range.
11. **Xây contract test:** lifecycle, errors, cancellation, resource và behavior.
12. **Tích hợp observability:** log, metrics, audit và health.
13. **Tài liệu hóa:** plugin guide, sample và migration policy.
14. **Phát hành và quản trị:** registry, signing, lockfile, deprecation và support.

## 20. Câu hỏi tự đánh giá

1. Stable core and plugins giải quyết vấn đề gì trong DSL?
2. Làm thế nào quyết định một tính năng thuộc core hay plugin?
3. Vì sao core không nên import implementation của plugin?
4. Extension point cần mô tả những thành phần nào?
5. Ports and adapters giúp tách DSL runtime khỏi hệ thống ngoài ra sao?
6. Plugin manager và extension registry có trách nhiệm gì?
7. Manifest và lockfile giúp quản lý dependency như thế nào?
8. In-process và out-of-process plugin khác nhau ra sao?
9. Capability security giới hạn quyền plugin như thế nào?
10. Vì sao cần version riêng cho core API, IR và plugin API?
11. Conflict resolution cần xử lý những trường hợp nào?
12. Contract tests xác nhận điều gì ngoài việc plugin compile?
13. Làm thế nào bảo đảm plugin mới không làm thay đổi core-only behavior?
14. Những anti-pattern nào khiến core hoặc plugin khó duy trì?

## Kết luận

Mẫu thiết kế lõi ổn định và plugin tạo một nền tảng DSL có semantics chung, API mở rộng rõ và dependency direction có kiểm soát. Core giữ grammar, type system, AST/IR, evaluation model, diagnostics và lifecycle contract. Plugin bổ sung capability chuyên biệt qua extension point, registry và manifest mà không buộc core biết implementation cụ thể.

Thiết kế bền vững cần public API nhỏ, dependency inversion, version compatibility, conflict policy, lifecycle rõ, least privilege và contract tests. Plugin có thể chạy trong process, process riêng hoặc sandbox tùy mức tin cậy. Core vẫn được phép phát triển nhưng thay đổi phải có versioning và migration policy. Khi ranh giới được xác định đúng, DSL có thể hỗ trợ nhiều miền và backend mà vẫn giữ nền tảng dễ hiểu, dễ kiểm thử và dễ duy trì.
