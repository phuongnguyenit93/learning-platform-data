# Plugin và extension

Trong kiến trúc tích hợp ứng dụng, một hệ thống thường cần mở rộng chức năng mà không phải sửa trực tiếp phần lõi mỗi khi có yêu cầu mới. Ví dụ, một ứng dụng DSL có thể cần thêm bộ sinh mã cho ngôn ngữ mới, một connector tới cơ sở dữ liệu, một kiểu validator, một lệnh trong IDE, một định dạng import/export hoặc một bộ xử lý triển khai. **Plugin** và **extension** là hai cơ chế thường dùng để bổ sung những khả năng đó thông qua các điểm mở rộng đã được thiết kế trước.

Plugin thường là một đơn vị phần mềm có thể được cài đặt, phát hiện, nạp, cấu hình và quản lý như một thành phần độc lập. Extension là phần triển khai cụ thể đóng góp một khả năng vào extension point do ứng dụng hoặc plugin khác công bố. Trong một số nền tảng, hai thuật ngữ được dùng gần như đồng nghĩa; trong kiến trúc rõ ràng, plugin thường là đơn vị đóng gói và phân phối, còn extension là đóng góp được đăng ký bên trong đơn vị đó.

Với một DSL, plugin có thể thêm cú pháp, kiểu dữ liệu, hàm built-in, validator, generator, runtime adapter, command, editor integration hoặc deployment target. Extension point xác định hợp đồng mà các thành phần bổ sung phải tuân theo. Thiết kế tốt giúp phần lõi ổn định, các phần mở rộng có thể phát triển độc lập và hệ thống vẫn kiểm soát được tính tương thích, thứ tự nạp, quyền truy cập và vòng đời.

## 1. Plugin và extension là gì?

Một plugin là một gói chức năng có thể được tích hợp vào ứng dụng thông qua cơ chế đã định nghĩa. Nó có thể chứa mã thực thi, metadata, tài nguyên, cấu hình, schema, UI contribution và các dependency cần thiết.

Một extension là một thành phần thực hiện một extension point cụ thể. Ví dụ, ứng dụng công bố extension point CompilerBackend. Plugin JavaBackend cung cấp một extension triển khai interface đó; plugin KotlinBackend cung cấp một extension khác.

Ví dụ kiến trúc:

~~~mermaid
flowchart TD
    A[Host application] --> B[Plugin manager]
    B --> C[Plugin registry]
    C --> D[Plugin: Java backend]
    C --> E[Plugin: Database connector]
    C --> F[Plugin: IDE tools]
    D --> G[CompilerBackend extension]
    E --> H[DataSourceProvider extension]
    F --> I[EditorCommand extension]
    G --> J[DSL compiler]
    H --> K[Application runtime]
    I --> L[Workbench UI]
~~~

Trong mô hình này:

- Host application là ứng dụng lõi, chịu trách nhiệm quản lý vòng đời.
- Plugin manager phát hiện, kiểm tra và nạp plugin.
- Plugin registry lưu metadata và các extension đã đăng ký.
- Extension point là hợp đồng được host công bố.
- Extension implementation cung cấp hành vi cụ thể.
- Consumer gọi extension qua API đã định nghĩa.

Một plugin có thể đóng góp nhiều extension point. Ví dụ plugin cho DSL workflow vừa thêm generator, vừa thêm validator, vừa thêm một command trong workbench.

## 2. Vì sao cần kiến trúc plugin?

Nếu mọi chức năng đều được viết trực tiếp trong phần lõi, số lượng nhánh điều kiện và dependency sẽ tăng theo từng tích hợp. Một connector mới có thể buộc sửa nhiều lớp, làm tăng rủi ro regression và khiến việc phát hành ứng dụng phụ thuộc vào lịch phát hành của mọi tích hợp.

Kiến trúc plugin đem lại một số lợi ích:

- **Mở rộng:** thêm tính năng qua hợp đồng công khai.
- **Tách biệt:** chức năng tùy chọn không cần nằm trong core package.
- **Phân phối độc lập:** plugin có thể được phát hành theo chu kỳ riêng nếu compatibility cho phép.
- **Tùy biến:** mỗi deployment có thể cài tập plugin khác nhau.
- **Tái sử dụng:** nhiều ứng dụng host có thể dùng cùng plugin API.
- **Thử nghiệm:** thử plugin mới trong môi trường riêng trước khi phát hành rộng.
- **Quản trị:** bật, tắt, nâng cấp hoặc gỡ plugin theo policy.

Plugin cũng tạo thêm độ phức tạp: dependency resolution, version compatibility, class loading, bảo mật, thứ tự khởi tạo và xử lý lỗi. Không nên tạo extension point cho mọi chi tiết nội bộ. Chỉ mở rộng những phần có nhu cầu thực tế và có thể định nghĩa contract ổn định.

## 3. Phân biệt core, plugin, extension point và extension

Bốn khái niệm cần được phân biệt:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Core/host | Quản lý ứng dụng và cung cấp API nền tảng | DSL runtime, plugin manager |
| Plugin | Đơn vị đóng gói và phân phối chức năng | Plugin hỗ trợ PostgreSQL |
| Extension point | Hợp đồng mà host cho phép mở rộng | DatabaseDialectProvider |
| Extension | Implementation cụ thể của hợp đồng | PostgreSQLDialect |

Ví dụ Java khái niệm:

~~~java
public interface DatabaseDialectProvider {
    String id();
    boolean supports(String databaseProduct);
    SqlDialect createDialect(DatabaseMetadata metadata);
}
~~~

Một plugin triển khai extension:

~~~java
public final class PostgresDialectProvider
        implements DatabaseDialectProvider {

    @Override
    public String id() {
        return "postgres";
    }

    @Override
    public boolean supports(String databaseProduct) {
        return databaseProduct.equalsIgnoreCase("PostgreSQL");
    }

    @Override
    public SqlDialect createDialect(DatabaseMetadata metadata) {
        return new PostgresDialect(metadata);
    }
}
~~~

Host gọi interface thay vì phụ thuộc trực tiếp vào class PostgresDialectProvider. Nhờ đó, plugin khác có thể cung cấp dialect mới mà không cần thay đổi logic lựa chọn trong core.

## 4. Thiết kế extension point

Extension point là ranh giới API giữa host và thành phần mở rộng. Nó cần mô tả:

- Tên và định danh ổn định.
- Mục đích và thời điểm được gọi.
- Input/output contract.
- Quy tắc lỗi và timeout.
- Threading và concurrency semantics.
- Quyền hoặc capability cần thiết.
- Cách đăng ký và hủy đăng ký.
- Version compatibility.
- Quy tắc ordering hoặc priority nếu có.
- Hạn chế side effect và resource.

Một extension point quá rộng khiến plugin có thể truy cập nhiều trạng thái nội bộ và làm host khó thay đổi. Một extension point quá hẹp có thể buộc plugin dùng reflection hoặc workaround. Cần chọn API nhỏ nhưng đủ để hoàn thành use case.

### 4.1. API công khai và API nội bộ

Chỉ công bố những kiểu dữ liệu mà plugin thực sự cần. Tránh để extension nhận toàn bộ object nội bộ của host, vì mọi thay đổi implementation có thể trở thành breaking change.

Ví dụ, thay vì truyền toàn bộ ApplicationContext, có thể truyền một GenerationContext chỉ chứa model, output directory, diagnostics và cancellation token.

### 4.2. Hợp đồng hành vi

Interface chỉ mô tả chữ ký hàm; contract còn phải định nghĩa hành vi. Ví dụ method generate có thể cần quy định:

- Có được gọi đồng thời cho nhiều module không.
- Output directory có sạch trước khi gọi không.
- Plugin có được ghi ngoài output directory không.
- Kết quả rỗng được hiểu là thành công hay lỗi.
- Cancellation có phải được tôn trọng không.
- Diagnostics được trả trực tiếp hay gửi qua callback.

Contract hành vi nên có tài liệu, ví dụ và test tương thích để tránh mỗi plugin hiểu một kiểu.

## 5. Các dạng extension point thường gặp trong DSL

Một nền tảng DSL có thể công bố nhiều loại extension point:

| Extension point | Chức năng mở rộng |
|---|---|
| Parser extension | Thêm token, syntax hoặc grammar module |
| Type provider | Thêm type hoặc type metadata |
| Function provider | Thêm hàm built-in hoặc domain function |
| Validator | Thêm kiểm tra tĩnh hoặc domain validation |
| Compiler backend | Sinh code cho target khác |
| Generator | Tạo source, schema, config hoặc tài liệu |
| Runtime adapter | Kết nối DSL với hệ thống thực thi |
| Data source | Cung cấp dữ liệu hoặc query provider |
| Editor service | Completion, hover, navigation, diagnostics |
| Command | Thêm thao tác trong CLI hoặc workbench |
| Formatter | Thêm quy tắc format |
| Import/export | Hỗ trợ định dạng dữ liệu khác |
| Deployment provider | Triển khai artifact tới môi trường đích |
| Observability provider | Log, metric, trace hoặc audit adapter |

Không phải mọi extension point đều nên cho phép thay đổi grammar. Grammar extension có thể tạo ambiguity, xung đột precedence và làm khó tooling. Với nhiều DSL, cung cấp annotation, function provider hoặc domain library sẽ an toàn hơn việc cho plugin tùy ý thêm syntax.

## 6. Plugin manifest

Plugin cần metadata để plugin manager có thể phát hiện và kiểm tra trước khi nạp mã.

Một manifest minh họa:

~~~yaml
plugin:
  id: com.example.dsl.postgres
  name: PostgreSQL integration
  version: 2.1.0
  vendor: Example Systems
  description: PostgreSQL dialect and migration support

compatibility:
  hostApi: ">=4.2 <5"
  dslApi: "3"
  runtime: ">=7.0"

entrypoints:
  - type: service-provider
    class: com.example.postgres.PostgresPlugin

extensions:
  - point: database.dialect
    id: postgres
  - point: dsl.generator
    id: postgres-migration

dependencies:
  - id: com.example.dsl.database-core
    version: ">=2.0 <3"

permissions:
  - database.metadata.read
  - workspace.output.write

artifacts:
  - path: plugin.jar
    sha256: "..."
~~~

Manifest nên được parse và validate trước khi class loading. Các trường như plugin ID, version, host API constraint, dependency, entry point và permission cần có semantics ổn định.

Manifest cũng có thể chứa chữ ký số, checksum, license, supported platform, minimum runtime, configuration schema và migration metadata.

## 7. Plugin identity và version

Plugin ID cần duy nhất và ổn định. Có thể dùng reverse-domain naming hoặc namespace do tổ chức quản lý:

~~~text
com.example.dsl.postgres
org.acme.workflow.git
net.vendor.dsl.python-backend
~~~

Tên hiển thị có thể thay đổi, nhưng ID dùng trong dependency, configuration, registry và audit nên giữ ổn định.

Plugin version thường có thể dùng Semantic Versioning:

- MAJOR: thay đổi không tương thích của public API hoặc manifest contract.
- MINOR: bổ sung extension hoặc capability tương thích.
- PATCH: sửa lỗi không chủ ý thay đổi contract.

Tuy nhiên, cần phân biệt plugin version với host API version, DSL language version, extension point version và runtime version. Chúng có thể thay đổi độc lập. Một plugin version 3 không tự động có nghĩa nó hỗ trợ DSL language version 3.

## 8. Khai báo extension trong DSL hoặc manifest

Plugin có thể đăng ký extension bằng manifest, annotation, service provider hoặc DSL configuration. Ví dụ cấu hình khái niệm:

~~~text
plugin "com.example.dsl.postgres" version "2.1.0" {
    enable extension "database.dialect.postgres"
    enable extension "dsl.generator.postgres-migration"
}
~~~

Cấu hình có thể cho phép bật/tắt extension riêng lẻ. Tuy nhiên, nếu một extension phụ thuộc extension khác trong cùng plugin, plugin manager phải kiểm tra dependency trước khi khởi tạo.

Không nên dùng tên class làm định danh public nếu có thể tránh được. Class có thể được refactor hoặc đổi package; extension ID logic nên ổn định hơn.

## 9. Phát hiện plugin (discovery)

Plugin manager cần tìm plugin từ một hoặc nhiều nguồn:

- Thư mục plugin cục bộ.
- Package manager hoặc artifact repository.
- Built-in plugin đi kèm ứng dụng.
- Module path hoặc service loader.
- Registry nội bộ của tổ chức.
- Extension marketplace được quản trị.

Discovery chỉ tìm và đọc metadata. Nó chưa nhất thiết nạp class hoặc chạy plugin.

Một pipeline:

~~~mermaid
flowchart TD
    A[Plugin locations] --> B[Discover manifests]
    B --> C[Parse metadata]
    C --> D[Validate identity and compatibility]
    D --> E[Resolve dependencies]
    E --> F[Verify integrity and permissions]
    F --> G[Create plugin load plan]
    G --> H[Load and initialize]
    H --> I[Register extensions]
~~~

Tách discovery khỏi loading giúp host có thể hiển thị danh sách plugin, báo lỗi manifest hoặc phát hiện xung đột trước khi thực thi code.

## 10. Dependency resolution

Plugin có thể phụ thuộc plugin hoặc library khác. Ví dụ plugin PostgreSQL cần database-core; plugin migration có thể cần SQL parser.

Dependency declaration nên có:
- Plugin ID.
- Version range.
- Optional/required.
- Scope hoặc capability cần thiết.
- Dependency được giải quyết từ registry nào.

Một ví dụ:

~~~yaml
dependencies:
  - id: com.example.dsl.database-core
    version: ">=2.0.0 <3.0.0"
    optional: false
  - id: com.example.dsl.metrics
    version: "^1.4.0"
    optional: true
~~~

Resolver cần chọn một tập version thỏa mọi constraint. Nếu không thể, nên báo dependency conflict với chuỗi phụ thuộc giúp người quản trị hiểu nguồn xung đột.

Không nên tự động chọn phiên bản bất kỳ chỉ vì nó có mặt trong thư mục. Với môi trường production, lockfile hoặc plugin catalog có thể cố định chính xác version và checksum đã được phê duyệt.

## 11. Dependency graph và thứ tự khởi tạo

Plugin dependency tạo thành graph. Nếu plugin B cần API do plugin A cung cấp, A phải được khởi tạo trước B hoặc ít nhất phải đăng ký contract trước khi B resolve extension.

~~~mermaid
flowchart TD
    A[core-api] --> B[database-core]
    A --> C[editor-api]
    B --> D[postgres-plugin]
    C --> E[postgres-editor]
    D --> F[application]
    E --> F
~~~

Plugin manager có thể dùng topological sort để xác định thứ tự nạp. Nếu dependency graph có cycle, cần báo lỗi hoặc dùng một cơ chế hai pha có contract rõ ràng.

Có thể tách:
1. Discover và resolve tất cả plugin.
2. Tạo class loader/module layer.
3. Đăng ký service descriptor.
4. Khởi tạo plugin theo dependency order.
5. Đăng ký extension.
6. Báo trạng thái ready.

Nếu plugin A cần gọi service của B ngay trong constructor trong khi B chưa khởi tạo, có thể xảy ra lỗi thứ tự. Dependency injection container hoặc lifecycle phase rõ ràng giúp giảm coupling này.

## 12. Plugin lifecycle

Một plugin thường đi qua các trạng thái:

- Discovered: manifest đã được tìm thấy.
- Resolved: dependency đã được giải quyết.
- Verified: integrity và policy đã được kiểm tra.
- Loaded: code hoặc module đã được nạp.
- Initialized: plugin đã khởi tạo.
- Active: extension đã đăng ký và có thể được sử dụng.
- Disabled: plugin không được chọn cho hoạt động mới.
- Stopping: đang giải phóng tài nguyên.
- Unloaded: đã được gỡ khỏi registry/classloader nếu nền tảng hỗ trợ.
- Failed: một bước lifecycle thất bại.

Sơ đồ minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> Discovered
    Discovered --> Resolved
    Resolved --> Verified
    Verified --> Loaded
    Loaded --> Initialized
    Initialized --> Active
    Active --> Disabled
    Disabled --> Active
    Disabled --> Stopping
    Active --> Stopping
    Stopping --> Unloaded
    Loaded --> Failed
    Initialized --> Failed
~~~

Không phải runtime nào cũng hỗ trợ unload class hoặc module thực sự. Một số hệ thống chỉ có thể đánh dấu plugin disabled và yêu cầu restart để giải phóng classloader. Điều này cần được công bố trong tài liệu quản trị.

## 13. Lifecycle interface

Một plugin có thể triển khai interface lifecycle:

~~~java
public interface Plugin {
    void initialize(PluginContext context);
    void start();
    void stop();
}
~~~

Trong thực tế, API có thể dùng asynchronous lifecycle, cancellation token hoặc structured result. Cần định nghĩa:
- initialize có được phép đọc configuration không.
- start có thể đăng ký extension vào thời điểm nào.
- stop có timeout không.
- stop có được gọi sau khi initialize thất bại không.
- cleanup exception được xử lý ra sao.
- lifecycle method có thể được gọi nhiều lần hay không.

Lifecycle nên idempotent ở những bước mà manager có thể retry. Nếu start được gọi hai lần, plugin không nên tạo hai listener hoặc hai background worker.

## 14. Đăng ký và tra cứu extension

Sau khi plugin active, extension được đăng ký vào registry. Một registry có thể hỗ trợ:

~~~java
public interface ExtensionRegistry {
    <T> void register(
        ExtensionPoint<T> point,
        String extensionId,
        T implementation
    );

    <T> List<T> findAll(ExtensionPoint<T> point);

    <T> Optional<T> find(
        ExtensionPoint<T> point,
        String extensionId
    );

    void unregisterPlugin(String pluginId);
}
~~~

Registry cần kiểm tra:
- Extension point tồn tại.
- Implementation có đúng contract/type.
- ID extension không xung đột.
- Plugin có permission phù hợp.
- Dependency đã active.
- Ordering hoặc priority hợp lệ.

Khi plugin bị disable, registry cần gỡ các extension do plugin sở hữu. Cần lưu owner plugin ID trên mỗi registration để cleanup chính xác.

## 15. Nhiều extension cùng một extension point

Một extension point có thể có một hoặc nhiều implementation.

Ví dụ:
- Nhiều formatter cho các ngôn ngữ khác nhau.
- Nhiều generator backend.
- Nhiều data source connector.
- Nhiều authentication provider.
- Nhiều rule validator.

API cần xác định cách consumer chọn:
- Tất cả extension.
- Một extension theo ID.
- Extension phù hợp với capability.
- Extension có priority cao nhất.
- Extension được chọn theo target/profile.

Nếu nhiều extension cùng match, không nên phụ thuộc thứ tự filesystem hoặc thứ tự discovery ngẫu nhiên. Có thể dùng priority rõ ràng, selection policy hoặc yêu cầu cấu hình tường minh.

## 16. Ordering và conflict resolution

Một số extension cần chạy theo thứ tự. Ví dụ formatter pipeline có bước normalize trước rồi format; validation pipeline có thể có các validator độc lập nhưng một số validator phụ thuộc kết quả trước.

Các cơ chế thường dùng:
- Priority số.
- before/after relation.
- Explicit order trong configuration.
- Dependency giữa extension.
- Pipeline stage cố định.

Ví dụ:

~~~yaml
extensions:
  - id: normalize-input
    order: 10
  - id: validate-schema
    order: 20
  - id: validate-domain
    order: 30
~~~

Cần xác định tie-breaking khi priority bằng nhau và cách phát hiện ordering cycle. Nếu thứ tự không ảnh hưởng semantics, tốt nhất không yêu cầu thứ tự để cho phép chạy song song.

Conflict có thể xảy ra khi hai plugin đăng ký cùng extension ID, cùng command name, cùng DSL function name hoặc cùng schema namespace. Host nên báo lỗi xác định, kèm plugin owner và extension point liên quan.

## 17. Extension cho parser và grammar DSL

Một plugin có thể thêm cú pháp mới cho DSL, nhưng đây là loại mở rộng nhạy cảm vì grammar ảnh hưởng parser, formatter, completion và tooling.

Một số lựa chọn:

- Grammar module được import tường minh.
- Annotation hoặc metadata extension không thay đổi grammar.
- Macro hoặc custom function trên AST.
- Preprocessor có contract rõ.
- Parser extension theo namespace.

Ví dụ cú pháp minh họa:

~~~text
use plugin "com.example.workflow"

workflow "release" {
    stage "build" {
        run compile()
    }
}
~~~

Plugin workflow có thể cung cấp syntax block workflow. Để tránh xung đột, grammar module cần khai báo namespace, precedence, token ownership và compatibility với grammar lõi.

Nếu plugin tùy ý thêm production có thể nhận cùng token sequence, parser có thể trở nên ambiguous. Có thể yêu cầu import module, dùng keyword riêng hoặc giới hạn extension vào các điểm grammar đã thiết kế.

## 18. Extension cho type system và function provider

Plugin có thể thêm domain type hoặc function:

~~~text
type Money<VND>
type GeoCoordinate

function distance(
    from: GeoCoordinate,
    to: GeoCoordinate
): Decimal
~~~

Type provider cần mô tả:
- Type ID và version.
- Equality/hash semantics.
- Serialization format.
- Nullability.
- Conversion được phép.
- Ordering nếu type hỗ trợ.
- Runtime representation.
- Compatibility với schema và generator.

Function provider cần mô tả:
- Signature.
- Type inference.
- Null behavior.
- Determinism.
- Side effect.
- Thread safety.
- Cost hoặc execution limit.
- Runtime implementation.

Hàm thuần có thể được constant-fold hoặc cache. Hàm đọc network hoặc clock cần được đánh dấu impure và có policy riêng. Không nên để compiler giả định mọi plugin function đều pure.

## 19. Extension cho validator và diagnostics

Validator plugin có thể kiểm tra quy tắc chuyên biệt của miền, ví dụ:
- Schema API phải tuân theo naming convention.
- Workflow không được tham chiếu stage không tồn tại.
- Database model không được có vòng phụ thuộc.
- Deployment target phải hỗ trợ resource được yêu cầu.

Một extension contract khái niệm:

~~~java
public interface DslValidator {
    String id();

    ValidationResult validate(
        DslModel model,
        ValidationContext context
    );
}
~~~

ValidationResult nên chứa diagnostics có code, severity, source span, message và quick-fix metadata nếu có. Validator không nên tự ghi file hoặc thực hiện side effect.

Host cần định nghĩa validator chạy trước hay sau type checking, có thể chạy song song không và cách giới hạn thời gian. Một validator chậm hoặc lỗi không nên làm treo toàn bộ workbench mà không có timeout hoặc trạng thái rõ ràng.

## 20. Extension cho compiler và generator

Compiler backend hoặc generator plugin chuyển mô hình DSL sang target khác.

Ví dụ extension point:

~~~java
public interface CodeGenerator {
    String targetId();

    GenerationResult generate(
        DslModel model,
        GenerationContext context
    );
}
~~~

GenerationContext có thể cung cấp:
- Output directory.
- Target configuration.
- Diagnostic reporter.
- Source map builder.
- Cancellation token.
- Artifact registry.
- Logger.
- Dependency resolver.

Plugin cần tuân theo output ownership. Generator không nên ghi tùy tiện ra ngoài vùng output được cấp. Nếu tạo nhiều artifact, nên trả manifest mô tả artifact ID, kind, path, checksum và provenance.

## 21. Extension cho runtime adapter và data source

Một DSL có thể được thực thi trong nhiều môi trường. Runtime adapter kết nối mô hình DSL với hệ thống cụ thể.

Ví dụ:
- SQL DSL với PostgreSQL hoặc SQL Server.
- Workflow DSL với scheduler.
- API DSL với HTTP framework.
- Event DSL với message broker.
- Query DSL với data warehouse.
- Device DSL với thiết bị IoT.

Một data source provider có thể có contract:

~~~java
public interface DataSourceProvider {
    String scheme();

    DataSource connect(
        DataSourceConfiguration configuration,
        CredentialProvider credentials
    );
}
~~~

Provider cần xác định transaction, pooling, timeout, retry, resource cleanup và error mapping. Không nên đưa credential thô vào DSL source hoặc manifest. Dùng secret provider hoặc credential handle do host cấp.

## 22. Extension cho IDE và workbench

Plugin có thể thêm:
- Syntax highlighting.
- Completion provider.
- Hover documentation.
- Go-to-definition.
- Reference search.
- Code action.
- Formatter.
- Outline view.
- Project wizard.
- Debug adapter.
- Artifact explorer.
- Build task integration.

Các extension IDE cần tương tác với language server hoặc workbench API ổn định. Không nên truy cập trực tiếp widget hoặc trạng thái UI nội bộ nếu host có command/event API công khai.

Một plugin editor nên tôn trọng cancellation vì người dùng có thể tiếp tục gõ trong khi completion request cũ vẫn đang chạy. Diagnostics cần gắn với document version để kết quả cũ không ghi đè kết quả mới.

## 23. Extension cho CLI và command registry

Plugin có thể thêm command:

~~~text
dsl plugin list
dsl plugin install com.example.dsl.postgres
dsl db inspect
dsl db migrate --plan
~~~

Command registry cần quản lý:
- Tên và namespace.
- Mô tả và help.
- Arguments/options có kiểu.
- Permission.
- Exit code.
- Output format.
- Cancellation.
- Conflict với command khác.

Không nên cho plugin chiếm command lõi một cách âm thầm. Có thể yêu cầu namespace hoặc explicit override policy. Command nhạy cảm như deploy hoặc migrate production cần authorization và audit.

## 24. Dependency injection và service registration

Plugin thường cần service từ host hoặc plugin khác. Dependency injection (DI) giúp tạo và quản lý object theo scope.

Các scope có thể gồm:
- Application singleton.
- Project/workspace.
- Request/session.
- Task execution.
- Plugin instance.

Không nên giữ object request-scoped trong singleton plugin nếu object đó chứa state của người dùng khác. Cần định nghĩa thread safety và lifecycle của service.

Plugin nên đăng ký service qua public DI API hoặc service registry. Tránh tìm implementation bằng reflection không kiểm soát hoặc tự tạo nhiều instance khi host đã quản lý lifecycle.

## 25. Event và hook

Một số extension point dùng event thay vì interface gọi trực tiếp. Ví dụ:
- Project opened.
- DSL model changed.
- Build completed.
- Artifact generated.
- Deployment started.
- User command invoked.

Event contract cần định nghĩa:
- Event có đồng bộ hay bất đồng bộ.
- Thứ tự listener có được đảm bảo không.
- Event có immutable không.
- Listener có thể chặn hành động không.
- Exception của listener được xử lý thế nào.
- Retry và delivery guarantee.
- Có event replay không.
- Có version và correlation ID không.

Event notification thường phù hợp cho quan sát hoặc phản ứng bất đồng bộ. Nếu host cần một kết quả quyết định để tiếp tục, interface request/response có thể phù hợp hơn event fire-and-forget.

Plugin listener cần được unregister khi plugin stop để tránh memory leak và callback vào object đã đóng.

## 26. Cấu hình plugin

Plugin thường cần cấu hình riêng. Cấu hình nên có schema và validation:

~~~yaml
plugin:
  id: com.example.dsl.postgres
  enabled: true
  config:
    defaultSchema: public
    connectionPool:
      maxSize: 12
      timeoutSeconds: 20
~~~

Cần phân biệt:
- Default configuration.
- Project configuration.
- User/workspace configuration.
- Environment-specific configuration.
- Secret reference.
- Runtime override.

Precedence giữa các nguồn cần được công bố. Không nên lưu password trực tiếp trong file cấu hình có thể commit vào repository. Dùng secret manager hoặc credential provider.

Plugin nên phát hiện cấu hình không hợp lệ trước khi active và trả diagnostics có path cụ thể như connectionPool.maxSize.

## 27. Plugin isolation và class loading

Plugin có thể được nạp trong cùng process với host hoặc chạy trong process riêng.

### 27.1. In-process plugin

Ưu điểm:
- Gọi API trực tiếp.
- Ít overhead giao tiếp.
- Dễ chia sẻ object và dữ liệu lớn.

Nhược điểm:
- Plugin có thể ảnh hưởng crash hoặc memory của host.
- Xung đột dependency/classpath.
- Khó unload class.
- Ranh giới bảo mật yếu nếu plugin có quyền process.

Có thể dùng classloader riêng hoặc module layer để giảm xung đột dependency. Nhưng classloader isolation không phải sandbox bảo mật hoàn chỉnh.

### 27.2. Out-of-process plugin

Plugin chạy trong process riêng và giao tiếp qua RPC, pipe hoặc message protocol.

Ưu điểm:
- Cô lập crash và memory.
- Có thể dùng ngôn ngữ/runtime khác.
- Dễ giới hạn quyền hệ điều hành.
- Nâng cấp hoặc restart độc lập.

Nhược điểm:
- Có chi phí serialization và IPC.
- Cần timeout, retry và protocol versioning.
- Quản lý process và deployment phức tạp hơn.

Lựa chọn phụ thuộc độ tin cậy, hiệu năng, loại dữ liệu và threat model. Plugin bên thứ ba hoặc không hoàn toàn tin cậy thường cần ranh giới process và capability rõ ràng hơn.

## 28. Bảo mật và quyền của plugin

Plugin là code thực thi. Cài đặt plugin có thể tương đương cấp quyền cho code đó đọc file, truy cập network hoặc gọi service.

Một permission model có thể khai báo capability:

~~~yaml
permissions:
  - workspace.read
  - workspace.generated.write
  - network.connect: api.example.com
  - database.metadata.read
~~~

Host cần:
- Xác minh nguồn plugin và chữ ký nếu policy yêu cầu.
- Kiểm tra checksum artifact.
- Hiển thị permission trước khi cài hoặc kích hoạt.
- Cấp quyền tối thiểu cần thiết.
- Cô lập file/network/process khi có thể.
- Quản lý secret bằng handle thay vì truyền giá trị.
- Ghi audit cho cài đặt, nâng cấp, bật/tắt và hành động nhạy cảm.
- Có cách thu hồi quyền hoặc disable plugin.

Không nên coi manifest permission là sandbox nếu host không thực thi permission đó. Việc khai báo chỉ có ý nghĩa khi runtime enforce capability.

## 29. Trust, supply chain và plugin repository

Plugin có thể đến từ nhà cung cấp, repository nội bộ hoặc marketplace. Quản lý supply chain cần quan tâm:

- Danh tính publisher.
- Nguồn tải.
- Checksum và chữ ký.
- Dependency provenance.
- License.
- Vulnerability advisory.
- Reproducible build nếu có.
- Chính sách review và allowlist.
- Kênh cập nhật.
- Retention của version cũ.

Không nên tự động cập nhật plugin production lên latest mà không qua compatibility và approval policy. Một plugin version mới có thể thay đổi hành vi, dependency hoặc permission.

Plugin catalog có thể công bố version được hỗ trợ, host API range, DSL version, platform, release notes và security status.

## 30. Packaging và phân phối plugin

Một plugin package có thể chứa:

~~~text
postgres-plugin/
  plugin.yml
  lib/
    postgres-plugin.jar
    helper-library.jar
  schemas/
    postgres-config.schema.json
  docs/
    README.md
  licenses/
    THIRD-PARTY-NOTICES.txt
  signatures/
    plugin.sig
~~~

Package cần xác định:
- Entry point.
- Dependency hoặc cách resolve dependency.
- Resource và schema.
- Version và compatibility.
- Permission.
- License.
- Signature/checksum.
- Platform-specific artifact nếu có.

Một số nền tảng dùng JAR, ZIP, OSGi bundle, npm package hoặc container image. Định dạng không quan trọng bằng contract cài đặt và kiểm tra integrity.

Không nên trộn file runtime, file phát triển và test fixture vào package production nếu không cần.

## 31. Cài đặt, nâng cấp và gỡ plugin

Plugin manager cần quản lý các thao tác:

- Install.
- Enable.
- Disable.
- Upgrade.
- Downgrade.
- Uninstall.
- Repair hoặc verify.
- List và inspect.

Nâng cấp có thể ảnh hưởng plugin phụ thuộc. Nếu plugin A yêu cầu API 2.x và plugin B chỉ hỗ trợ API 1.x, nâng cấp A có thể làm B không tương thích.

Một quy trình upgrade an toàn:
1. Tải package vào staging.
2. Xác minh nguồn, signature và checksum.
3. Kiểm tra manifest và dependency.
4. Kiểm tra host/DSL compatibility.
5. Chạy migration hoặc validation nếu cần.
6. Lập kế hoạch thay thế.
7. Activate version mới.
8. Xác nhận extension đăng ký thành công.
9. Nếu lỗi, phục hồi version cũ.
10. Ghi audit event.

Uninstall cần xử lý cấu hình, data và artifact do plugin sở hữu. Không xóa dữ liệu người dùng hoặc artifact mà plugin không có quyền sở hữu. Một plugin có thể cần deactivation và cleanup trước khi package được xóa.

## 32. Compatibility giữa host và plugin

Compatibility không chỉ là plugin có load được hay không. Cần kiểm tra:

- Host API version.
- Extension point version.
- DSL language version.
- Runtime ABI/API.
- Java/runtime version.
- Operating system/architecture.
- Dependency plugin versions.
- Manifest schema version.
- Configuration schema version.

Ví dụ:

~~~yaml
compatibility:
  hostApi: ">=4.2 <5"
  extensionPoints:
    database.dialect: "2"
    dsl.generator: "3"
  java: ">=21"
  platforms:
    - linux-x64
    - windows-x64
~~~

Nếu extension point thay đổi không tương thích, host có thể cung cấp adapter hoặc versioned interface trong một giai đoạn chuyển tiếp. Không nên đổi method public rồi giả định tất cả plugin sẽ tự cập nhật.

## 33. Deprecation và migration của extension API

Khi host cần thay đổi extension contract:

1. Thêm API mới song song.
2. Đánh dấu API cũ deprecated.
3. Cung cấp migration guide và ví dụ.
4. Có adapter nếu chuyển đổi semantics được.
5. Cho plugin maintainer thời gian cập nhật.
6. Theo dõi usage của API cũ.
7. Loại bỏ ở major release đã công bố.

Deprecation cần nêu phiên bản dự kiến loại bỏ và phương án thay thế. Nếu chỉ đánh dấu deprecated mà không có migration path, plugin author không biết phải chuyển sang đâu.

Một API có thể giữ binary compatibility nhưng thay đổi semantics. Vì vậy, cần test cả compile/link và hành vi runtime.

## 34. Plugin và extension trong môi trường nhiều ứng dụng

Một plugin có thể được dùng bởi nhiều host application, nhưng không nên giả định mọi host cung cấp cùng API. Có thể tạo shared extension API độc lập với implementation cụ thể của host.

Ví dụ:
- Core extension API mô tả model và validator contract.
- IDE host cung cấp editor services.
- CLI host cung cấp command registry.
- Server host cung cấp runtime services.

Plugin có thể khai báo capability optional để chỉ đăng ký phần phù hợp. Nếu một host không có editor API, phần editor extension có thể không được kích hoạt trong host đó.

Tránh phụ thuộc trực tiếp vào implementation của một ứng dụng cụ thể nếu mục tiêu là tái sử dụng plugin ở nhiều môi trường.

## 35. Observability và chẩn đoán plugin

Plugin manager nên cung cấp thông tin vận hành:

- Plugin ID/version.
- Publisher.
- Trạng thái lifecycle.
- Dependency resolution.
- Extension point đã đăng ký.
- Permission được cấp.
- Thời gian initialize/start/stop.
- Lỗi và warning.
- Resource usage.
- Số lần gọi extension.
- Latency và timeout.
- Version host/runtime đang chạy.

Log nên gắn plugin ID và extension ID để truy vết. Không log secret hoặc payload nhạy cảm. Với lỗi khởi tạo, báo rõ bước nào thất bại và dependency nào liên quan.

Một plugin lỗi không nhất thiết phải làm sập toàn bộ host. Host có thể cô lập failure theo policy, đánh dấu plugin failed và tiếp tục nếu extension đó không bắt buộc cho ứng dụng.

## 36. Kiểm thử plugin và extension

Kiểm thử nên bao phủ contract, lifecycle, compatibility và vận hành.

### 36.1. Contract tests

- Extension implementation thỏa interface.
- Input/output semantics đúng.
- Diagnostics có source span và code hợp lệ.
- Thread safety theo contract.
- Cancellation và timeout được tôn trọng.
- Extension không ghi ngoài output được cấp.

### 36.2. Plugin manager tests

- Discovery manifest hợp lệ.
- Reject manifest sai hoặc thiếu field.
- Dependency resolution thành công/thất bại đúng.
- Cycle được phát hiện.
- Version conflict có diagnostics.
- Integrity/signature được xác minh.
- Extension ID collision được xử lý xác định.

### 36.3. Lifecycle tests

- Initialize/start/stop đúng thứ tự.
- Failure ở từng phase được cleanup.
- Disable gỡ extension khỏi registry.
- Enable lại không đăng ký trùng.
- Stop idempotent.
- Background thread/listener được giải phóng.

### 36.4. Compatibility tests

- Plugin hỗ trợ host API được chấp nhận.
- Plugin yêu cầu API không hỗ trợ bị từ chối sớm.
- Manifest schema version được kiểm tra.
- Config migration hoạt động.
- Nhiều plugin version cùng dependency graph không gây conflict.

### 36.5. Security tests

- Permission được enforce.
- Plugin không truy cập capability không được cấp.
- Package tampered bị từ chối.
- Secret không xuất hiện trong log.
- Path traversal và archive bomb bị chặn.
- Out-of-process plugin bị giới hạn resource và network.

### 36.6. Integration tests

Chạy host thực tế với tập plugin đại diện để xác nhận extension được phát hiện, gọi đúng và cleanup đúng. Có thể dùng test fixture plugin cố ý chậm, lỗi hoặc trả output không hợp lệ để kiểm tra failure isolation.

## 37. Ví dụ: plugin generator cho DSL

Giả sử host có extension point CodeGenerator. Plugin PostgreSQL đóng góp generator tạo migration SQL từ DSL schema.

Manifest:

~~~yaml
plugin:
  id: com.example.dsl.postgres
  version: 2.1.0

compatibility:
  hostApi: ">=4.2 <5"
  dslApi: "3"

extensions:
  - point: dsl.generator
    id: postgres-migration
    implementation: com.example.postgres.PostgresMigrationGenerator

permissions:
  - workspace.generated.write
~~~

Extension:

~~~java
public final class PostgresMigrationGenerator
        implements CodeGenerator {

    @Override
    public String targetId() {
        return "postgres-migration";
    }

    @Override
    public GenerationResult generate(
            DslModel model,
            GenerationContext context) {

        List<SqlStatement> statements =
            transformModel(model);

        context.output().writeText(
            "migration.sql",
            render(statements)
        );

        return GenerationResult.success();
    }
}
~~~

Host có thể:
1. Phát hiện plugin manifest.
2. Kiểm tra host API và DSL API compatibility.
3. Resolve dependency.
4. Xác minh package.
5. Nạp plugin.
6. Đăng ký CodeGenerator extension.
7. Khi người dùng chọn target postgres-migration, gọi generator.
8. Ghi artifact vào output directory được cấp.
9. Thu thập diagnostics và manifest.
10. Gỡ extension khi plugin bị disable.

Ví dụ cho thấy plugin bổ sung backend mới mà core compiler không cần chứa logic PostgreSQL cụ thể.

## 38. Quy trình thiết kế plugin system

Có thể triển khai theo các bước:

1. **Xác định nhu cầu mở rộng:** liệt kê những khả năng thực sự cần plugin.
2. **Chọn extension point:** định nghĩa API nhỏ, ổn định và có contract hành vi.
3. **Định nghĩa identity/version:** plugin ID, extension ID và version scheme.
4. **Thiết kế manifest:** entry point, dependency, compatibility, permission và artifact.
5. **Thiết kế discovery:** nguồn plugin và cách đọc metadata.
6. **Xây dependency resolver:** version range, lockfile và cycle detection.
7. **Xây lifecycle manager:** load, initialize, activate, disable và cleanup.
8. **Xây extension registry:** đăng ký, tra cứu, ordering và unregister.
9. **Chọn isolation model:** in-process hay out-of-process.
10. **Enforce security:** signature, checksum, capability và resource limit.
11. **Thiết kế packaging/distribution:** install, upgrade, rollback và uninstall.
12. **Công bố compatibility policy:** host API, DSL API và extension point version.
13. **Tích hợp observability:** trạng thái, log, metric và audit.
14. **Viết contract/integration/security tests:** kiểm tra plugin hoạt động trong host thực tế.

## 39. Những lỗi thiết kế thường gặp

- Công bố quá nhiều API nội bộ làm host khó refactor.
- Extension point không có contract hành vi.
- Dùng class name làm ID public.
- Nạp plugin trước khi xác minh dependency và integrity.
- Phụ thuộc vào thứ tự discovery không xác định.
- Không kiểm tra version compatibility.
- Cho nhiều plugin ghi cùng output mà không có ownership.
- Không unregister listener khi plugin stop.
- Để plugin chạy thread nền không quản lý.
- Cho plugin quyền rộng hơn nhu cầu.
- Coi classloader isolation là sandbox bảo mật.
- Tự động cập nhật production lên latest.
- Không có rollback khi upgrade thất bại.
- Không có error isolation cho plugin lỗi.
- Cho phép grammar extension gây ambiguity.
- Không kiểm thử plugin với host version thực tế.

Các vấn đề này thường không xuất hiện ở ví dụ plugin đầu tiên, nhưng sẽ trở nên nghiêm trọng khi hệ sinh thái có nhiều nhà phát triển và nhiều version cùng tồn tại.

## 40. Nguyên tắc thiết kế

- **Giữ core nhỏ và ổn định:** chỉ mở rộng qua các điểm đã có nhu cầu rõ.
- **Tách plugin khỏi extension:** plugin là đơn vị đóng gói; extension là đóng góp vào một hợp đồng.
- **Thiết kế API công khai tối thiểu:** tránh lộ trạng thái nội bộ của host.
- **Định nghĩa contract hành vi:** input, output, lifecycle, threading, error và cancellation phải rõ.
- **Dùng manifest có version:** metadata cần đủ để resolve, verify và quản trị.
- **Resolve dependency trước khi nạp:** phát hiện conflict và cycle sớm.
- **Quản lý lifecycle tường minh:** initialize, activate, disable và cleanup có thứ tự.
- **Gắn extension với owner plugin:** disable/uninstall phải gỡ đúng registration.
- **Xác định ordering và conflict policy:** không phụ thuộc thứ tự file hoặc discovery.
- **Cẩn trọng với grammar extension:** ưu tiên extension point có namespace và semantics rõ.
- **Tách host API, DSL version và extension point version:** các trục tương thích độc lập.
- **Cấp quyền tối thiểu:** manifest permission chỉ có ý nghĩa khi runtime thực thi.
- **Chọn isolation theo trust model:** plugin không tin cậy cần ranh giới process/capability phù hợp.
- **Bảo vệ supply chain:** xác minh publisher, checksum, signature và dependency.
- **Nâng cấp có thể phục hồi:** staging, validation, activation và rollback.
- **Quan sát plugin như thành phần độc lập:** log, metric, trạng thái và audit cần gắn identity.
- **Kiểm thử contract lẫn host integration:** plugin compile được chưa có nghĩa tích hợp đúng.

Plugin và extension cho phép ứng dụng DSL phát triển thành một nền tảng có thể mở rộng. Khi host công bố extension point ổn định, plugin có manifest và dependency rõ, lifecycle được quản lý, quyền được giới hạn và compatibility được kiểm tra, các chức năng mới có thể được tích hợp mà không làm phần lõi phụ thuộc trực tiếp vào từng nhà cung cấp. Cùng với registry, isolation, observability và kiểm thử, kiến trúc này giúp hệ sinh thái plugin phát triển có kiểm soát qua nhiều ứng dụng và phiên bản.
