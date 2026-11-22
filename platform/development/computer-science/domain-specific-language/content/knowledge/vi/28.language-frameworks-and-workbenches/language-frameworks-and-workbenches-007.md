# Tích hợp generated artifact

Trong một hệ thống sử dụng ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), compiler hoặc generator có thể tạo ra nhiều loại đầu ra: mã nguồn, cấu hình, schema, client API, tài liệu, metadata, resource hoặc gói triển khai. Những đầu ra này được gọi chung là **generated artifact**. Việc sinh được tệp mới chỉ là một phần của quy trình. Artifact còn cần được kết nối với framework và workbench để các thành phần khác có thể phát hiện, biên dịch, kiểm tra, hiển thị, đóng gói và sử dụng đúng cách.

**Tích hợp generated artifact** là quá trình đưa sản phẩm do generator tạo ra vào vòng đời của dự án hoặc công cụ phát triển. Quá trình này bao gồm xác định hợp đồng artifact, quản lý vị trí và metadata, đăng ký với framework, cấu hình build/runtime, liên kết dependency, giữ source mapping, quản lý phiên bản và xử lý cập nhật hoặc loại bỏ artifact cũ.

Nếu chỉ ghi tệp vào một thư mục tùy ý, framework có thể không tìm thấy lớp được sinh, build system có thể bỏ qua nguồn mới, IDE có thể không index được symbol, hoặc runtime có thể tải nhầm phiên bản. Tích hợp cần được thiết kế như một phần của kiến trúc DSL, với ranh giới rõ giữa nội dung được sinh, thành phần tiêu thụ và trạng thái quản lý artifact.

## 1. Generated artifact là gì?

Generated artifact là sản phẩm được tạo tự động từ DSL, mô hình miền, schema, template hoặc dữ liệu đầu vào khác. Nó có thể là đầu ra trung gian hoặc sản phẩm được dùng trực tiếp.

Một số loại thường gặp:

| Loại artifact | Ví dụ | Thành phần tiêu thụ |
|---|---|---|
| Generated source | Java, Kotlin, TypeScript, C# | Compiler và IDE |
| Configuration | YAML, JSON, XML, properties | Framework hoặc runtime |
| Schema | JSON Schema, XSD, database schema | Validator, API gateway, database |
| Client/server stub | REST client, RPC stub, adapter | Ứng dụng gọi dịch vụ |
| Resource | route table, registry, lookup table | Runtime framework |
| Documentation | API reference, model diagram | Developer và người vận hành |
| Metadata | manifest, source map, symbol index | Build tool, IDE, debugger |
| Package | JAR, bundle, plugin hoặc deployment archive | Package manager và runtime |

Một DSL workflow có thể tạo ra Java class để đăng ký task, YAML để cấu hình runner và JSON metadata để IDE hiển thị đồ thị workflow. Ba đầu ra này có liên hệ với cùng một mô hình nguồn nhưng được các thành phần khác nhau sử dụng.

Generated artifact cần được xem là một phần của sản phẩm build. Nó có danh tính, phiên bản, nguồn gốc, dependency và vòng đời. Không nên chỉ dựa vào tên tệp để xác định artifact thuộc generator nào hoặc có còn hợp lệ hay không.

## 2. Từ sinh mã đến tích hợp

Một pipeline tổng quát có thể gồm các giai đoạn:

~~~mermaid
flowchart TD
    A[DSL source and model] --> B[Parse and validate]
    B --> C[Generator]
    C --> D[Generated artifact set]
    D --> E[Artifact validation]
    E --> F[Staging and manifest]
    F --> G[Framework and workbench registration]
    G --> H[Build and package integration]
    H --> I[Runtime or IDE consumption]
    I --> J[Diagnostics and lifecycle feedback]
~~~

Các giai đoạn có trách nhiệm khác nhau:

1. **Generation:** tạo nội dung artifact từ mô hình đã kiểm chứng.
2. **Artifact validation:** kiểm tra định dạng, cấu trúc, tham chiếu và tính đầy đủ của đầu ra.
3. **Staging:** chuẩn bị artifact và metadata trước khi công bố.
4. **Registration:** thông báo cho framework hoặc workbench về artifact và vai trò của nó.
5. **Build integration:** đưa generated source/resource vào đúng source set hoặc task graph.
6. **Packaging:** đóng gói artifact và dependency cần thiết.
7. **Consumption:** compiler, IDE, framework hoặc runtime đọc và sử dụng artifact.
8. **Lifecycle management:** cập nhật, invalidation, thay thế và xóa artifact cũ.

Tách các giai đoạn giúp lỗi được định vị rõ. Nếu generator tạo JSON không hợp lệ, đó là lỗi generation hoặc validation. Nếu JSON hợp lệ nhưng runtime không tìm thấy, có thể là lỗi registration hoặc packaging. Nếu IDE vẫn hiển thị phiên bản cũ, cần xem xét indexing và invalidation.

## 3. Hợp đồng artifact

Framework và workbench cần biết cách nhận diện và sử dụng artifact. Hợp đồng artifact (artifact contract) mô tả các thông tin tối thiểu để một thành phần có thể tiêu thụ đầu ra mà không phải đoán.

Một hợp đồng thường gồm:

- **Artifact ID:** định danh ổn định trong phạm vi dự án hoặc workspace.
- **Type/kind:** source, resource, schema, metadata, package hoặc loại khác.
- **Location:** đường dẫn hoặc URI nơi artifact được lưu.
- **Format:** Java source, JSON, YAML, bytecode hoặc định dạng cụ thể.
- **Version:** phiên bản schema hoặc format của artifact.
- **Generator identity:** tên và phiên bản generator tạo artifact.
- **Input provenance:** DSL file, model ID, revision hoặc content hash nguồn.
- **Dependencies:** artifact hoặc runtime component cần thiết.
- **Target:** ngôn ngữ, nền tảng, framework version hoặc profile đích.
- **Integrity:** checksum/hash để phát hiện nội dung thay đổi.
- **Mappings:** source map, source span hoặc symbol mapping nếu cần.
- **Lifecycle metadata:** trạng thái, thời điểm tạo và chính sách thay thế.

Ví dụ manifest khái niệm:

~~~json
{
  "artifactId": "workflow.release.java",
  "kind": "generated-source",
  "format": "java",
  "location": "build/generated/sources/workflow/ReleaseWorkflow.java",
  "generator": {
    "id": "workflow-dsl",
    "version": "2.4.0"
  },
  "schemaVersion": "3",
  "source": {
    "uri": "file:///workspace/workflows/release.dsl",
    "revision": "sha256:..."
  },
  "target": {
    "language": "java",
    "release": "21"
  },
  "dependencies": [
    "workflow-runtime:2.4.0"
  ],
  "checksum": "sha256:..."
}
~~~

Đây là cấu trúc minh họa, không phải định dạng bắt buộc. Điều quan trọng là producer và consumer thống nhất ý nghĩa các trường. Nếu framework chỉ biết một đường dẫn mà không biết format hoặc version, nó có thể xử lý artifact sai cách.

## 4. Artifact ID và quy tắc đặt tên

Artifact ID nên ổn định và có phạm vi. Một tên tệp có thể thay đổi do quy tắc đặt tên, nhưng ID logic nên giúp framework nhận ra cùng một artifact qua các lần sinh.

Có thể xây ID từ:

- Workspace hoặc project ID.
- Module hoặc namespace.
- Loại artifact.
- Định danh phần tử DSL.
- Target platform hoặc profile.

Ví dụ:

~~~text
project:shop/module:orders/kind:java-source/symbol:OrderService
project:shop/module:orders/kind:route-table/target:production
~~~

Không nên dùng đường dẫn tuyệt đối trên máy developer làm ID. Đường dẫn đó có thể khác giữa Windows, Linux, CI và máy build khác. Dùng URI hoặc đường dẫn tương đối đã chuẩn hóa theo workspace.

Nếu tên artifact được tạo từ tên người dùng nhập trong DSL, cần chuẩn hóa identifier, xử lý ký tự không hợp lệ và phát hiện va chạm. Hai tên khác nhau có thể chuyển thành cùng tên tệp sau khi bỏ dấu hoặc chuyển chữ hoa/thường. Generator cần một quy tắc collision rõ ràng, không ghi đè ngầm.

## 5. Vị trí lưu trữ và phân loại output

Generated artifact nên được đặt ở vị trí phù hợp với vai trò của nó.

Một cấu trúc dự án ví dụ:

~~~text
project/
  src/
    main/
      dsl/
        orders.dsl
      java/
        handwritten/
  build/
    generated/
      sources/
        workflow/
      resources/
        workflow/
      metadata/
        manifests/
        sourcemaps/
  dist/
    application.jar
~~~

Các nguyên tắc phổ biến:

- Mã sinh trong build thường đặt dưới build/generated hoặc thư mục tương đương.
- Tài nguyên sinh nên được phân loại riêng với source code.
- Metadata như manifest và source map có thể nằm cạnh artifact hoặc trong thư mục metadata.
- Artifact tạm và staging không nên được runtime hoặc IDE coi là output chính thức.
- Thư mục output cần được cấu hình, không hard-code trong generator.

Không phải mọi dự án đều dùng cấu trúc trên. Một số repository commit generated source để review; một số chỉ sinh trong build. Cần quyết định rõ artifact có được quản lý trong version control hay tái tạo ở mỗi build.

## 6. Đăng ký artifact với framework

Sau khi tạo, artifact cần được framework biết đến. Registration là bước khai báo artifact tồn tại, loại của nó và cách framework nên sử dụng nó.

Ví dụ, một framework DSL có thể cần đăng ký:

- Generated service class vào dependency injection container.
- Route table vào web router.
- Workflow definition vào scheduler.
- Schema vào validation registry.
- Plugin descriptor vào extension registry.
- Resource bundle vào resource loader.

Một API khái niệm:

~~~java
interface ArtifactRegistry {
    void register(ArtifactDescriptor descriptor);
    Optional<ArtifactDescriptor> find(ArtifactId id);
    void unregister(ArtifactId id);
}
~~~

Framework có thể dùng registry trong bộ nhớ, manifest trên đĩa, service loader hoặc cơ chế plugin riêng. Dù cách nào, registration cần idempotent: đăng ký cùng artifact hai lần không được tạo hai component runtime nếu hợp đồng chỉ yêu cầu một.

### 6.1. Đăng ký theo loại

Consumer cần biết cách xử lý artifact dựa trên kind. Ví dụ:

- generated-source được đưa vào compiler.
- generated-resource được đưa vào resource processing.
- schema được đưa vào validation registry.
- plugin-descriptor được đưa vào plugin loader.
- source-map được đưa vào debugger/diagnostic adapter.

Tránh dùng một handler chung chỉ dựa trên phần mở rộng tệp. Một file JSON có thể là cấu hình runtime, manifest hoặc dữ liệu test; vai trò cần được khai báo rõ.

### 6.2. Thứ tự đăng ký

Một số artifact phụ thuộc artifact khác. Ví dụ, generated service cần runtime library; schema registry cần schema đã được nạp trước khi validate tài liệu. Registration cần tuân theo dependency order hoặc dùng hai pha: đăng ký descriptor trước, resolve dependency sau.

Nếu phát hiện dependency thiếu, framework nên báo lỗi chỉ rõ artifact phụ thuộc vào gì và dependency nào không có.

## 7. Tích hợp generated source vào build system

Generated source chỉ được biên dịch nếu build system biết vị trí của nó. Với Java, thư mục source sinh cần được thêm vào source set hoặc task graph phù hợp.

Ví dụ cấu hình Gradle khái niệm:

~~~kotlin
val generatedDslDir =
    layout.buildDirectory.dir("generated/sources/dsl/main")

sourceSets {
    main {
        java.srcDir(generatedDslDir)
    }
}

tasks.named("compileJava") {
    dependsOn("generateDslSources")
}
~~~

Tên task và cách khai báo phụ thuộc vào plugin và cấu trúc dự án. Đoạn trên chỉ minh họa quan hệ: task sinh mã phải hoàn tất trước khi compile task cần các tệp đó.

Với Maven, generated source thường được thêm qua plugin hoặc build-helper mechanism. Với các hệ sinh thái khác, cần dùng extension point tương ứng của build tool.

### 7.1. Khai báo task dependency

Build system cần biết generator là prerequisite của bước tiêu thụ. Nếu compile chạy trước generate, compiler có thể báo thiếu class. Nếu generator chạy sau compile, output không được đưa vào artifact build hiện tại.

Quan hệ task nên được khai báo bằng dependency graph, không dựa vào thứ tự tình cờ trong file build.

### 7.2. Input/output của task

Build task nên khai báo:

- DSL files hoặc model snapshot là input.
- Generator configuration và schema version là input.
- Generated directory là output.
- Tool version hoặc runtime dependency ảnh hưởng kết quả.
- Các environment values được phép ảnh hưởng generation.

Khai báo chính xác giúp build cache và incremental build hoạt động đúng. Nếu một cấu hình ảnh hưởng nội dung nhưng không được khai báo là input, build system có thể tái sử dụng output cũ.

### 7.3. Không đưa generated source vào source set nhiều lần

Một số plugin tự đăng ký generated directory; nếu build script thêm lại cùng thư mục qua cơ chế khác, cùng class có thể được compile hai lần hoặc task graph có cấu hình dư thừa. Chỉ có một nơi chịu trách nhiệm đăng ký output cho mỗi source set.

## 8. Tích hợp generated resource

Không phải artifact nào cũng là source code. JSON, YAML, schema, route table, template hoặc metadata có thể cần được đưa vào resource processing và đóng gói cùng ứng dụng.

Ví dụ cấu trúc:

~~~text
build/generated/resources/dsl/
  routes.json
  workflow-index.json
  schemas/
    order.schema.json
~~~

Build system cần:

- Đưa thư mục resource vào đúng resource set.
- Giữ đường dẫn tương đối mà runtime mong đợi.
- Xử lý duplicate resource.
- Quy định thứ tự ưu tiên nếu có resource cùng tên.
- Đóng gói metadata cần thiết.
- Tránh đưa file staging hoặc file tạm vào package.

Nếu runtime tải resource theo classpath, artifact phải nằm ở đúng vị trí bên trong JAR hoặc package. Một tệp tồn tại trên disk không có nghĩa nó đã được đóng gói.

## 9. Tích hợp với dependency và runtime library

Generated code thường gọi API của runtime library. Generator và runtime phải tương thích về API, version và semantics.

Ví dụ Java sinh ra:

~~~java
public final class ReleaseWorkflow {
    public static Workflow create(WorkflowRuntime runtime) {
        return runtime.workflow("release")
            .task("compile", task -> task.retries(2))
            .task("publish", task -> task.dependsOn("compile"));
    }
}
~~~

Mã này phụ thuộc các kiểu Workflow, WorkflowRuntime và API builder. Artifact descriptor hoặc build plugin cần thể hiện dependency runtime cần thiết.

Cần quản lý:

- Phiên bản runtime tối thiểu/tối đa được hỗ trợ.
- API đã deprecated hoặc bị loại bỏ.
- Dependency bắc cầu.
- Classpath/module path.
- Plugin version và generator version.
- Runtime feature flags.
- Khả năng tương thích giữa generated source và runtime binary.

Một generator mới có thể tạo code gọi method chỉ tồn tại ở runtime version mới. Nếu project dùng runtime cũ, lỗi chỉ xuất hiện ở compile hoặc runtime. Có thể kiểm tra compatibility sớm bằng metadata target và version constraints.

## 10. Tích hợp với framework extension point

Framework thường cung cấp extension point như plugin, service provider, annotation scanning, dependency injection hoặc registry. Generated artifact cần tuân theo contract mà framework yêu cầu.

Ví dụ, một generated plugin descriptor có thể khai báo:

~~~json
{
  "id": "orders.dsl",
  "entryPoint": "com.example.generated.OrdersModule",
  "apiVersion": "2",
  "capabilities": ["routes", "validation"]
}
~~~

Framework loader có thể đọc descriptor, kiểm tra API version và khởi tạo entry point.

Khi tích hợp, cần xác định:

- Artifact được phát hiện tự động hay đăng ký tường minh.
- Thời điểm framework scan.
- Constructor hoặc factory contract.
- Dependency injection scope.
- Error handling khi khởi tạo thất bại.
- Cách unload hoặc reload plugin.
- Quyền và capability được cấp cho artifact.

Generated code không nên phụ thuộc vào chi tiết nội bộ của framework nếu có public extension API. Dùng API công khai giúp artifact ổn định hơn khi framework nâng cấp.

## 11. Tích hợp trong workbench và IDE

Workbench là môi trường làm việc hỗ trợ tạo, chỉnh sửa, kiểm tra và quản lý các thành phần của DSL. Nó có thể gồm editor, project explorer, model view, generator panel, validation view, artifact browser và build integration.

Generated artifact cần được workbench nhận diện để người dùng:

- Xem danh sách artifact được tạo từ một DSL source.
- Mở artifact hoặc source tương ứng.
- Xem trạng thái generate/build.
- Nhận diagnostics và source mapping.
- Phân biệt tệp generated với tệp viết tay.
- Xem dependency giữa artifact.
- Regenerate khi source thay đổi.
- Preview diff trước khi cập nhật.
- Xóa hoặc archive artifact theo ownership.
- Tìm artifact đã lỗi thời hoặc thiếu.

Workbench có thể hiển thị quan hệ:

~~~mermaid
flowchart TD
    A[orders.dsl] --> B[Order model]
    B --> C[OrderService.java]
    B --> D[order.schema.json]
    B --> E[OrderRoutes.json]
    C --> F[Java compiler]
    D --> G[Schema registry]
    E --> H[HTTP runtime]
~~~

Một artifact browser có thể hiển thị ID, loại, nguồn, version, target, checksum và trạng thái. Việc này giúp người dùng hiểu artifact đến từ đâu và thành phần nào đang sử dụng nó.

## 12. Generated artifact và workspace model

Workbench thường có workspace model chứa project, module, source folder, resource folder và dependency. Khi generator tạo artifact, workbench cần cập nhật workspace model hoặc thông báo thay đổi cho các service liên quan.

Một luồng có thể là:

1. Generator ghi artifact vào output directory.
2. Artifact registry cập nhật descriptor.
3. Workspace model đánh dấu resource mới hoặc thay đổi.
4. Indexer quét generated source/resource.
5. Language server cập nhật symbol và reference index.
6. Build integration nhận output mới.
7. UI refresh artifact explorer và diagnostics.

Không nên bắt buộc người dùng đóng/mở lại project sau mỗi lần generate nếu workbench có API refresh hoặc resource delta. Tuy nhiên, refresh cần được giới hạn vào vùng thay đổi để tránh re-index toàn workspace không cần thiết.

## 13. Generated source và Language Server

Nếu generated source thuộc ngôn ngữ mà IDE hỗ trợ, language server hoặc IDE indexer cần biết thư mục đó là source root. Điều này cho phép completion, go-to-definition, references và diagnostics hoạt động trên code sinh.

Cần quyết định:

- Generated source có được index như source thông thường không.
- Có hiển thị diagnostics từ generated code không.
- Có cho phép người dùng sửa trực tiếp không.
- Có ánh xạ lỗi về DSL nguồn bằng source map không.
- Có loại generated symbol khỏi một số kết quả tìm kiếm không.
- Khi source DSL thay đổi, index được invalidated như thế nào.

Một số IDE đánh dấu thư mục generated để phân biệt về giao diện và tránh đề xuất chỉnh sửa trực tiếp. Dù vậy, vẫn cần index nếu generated code là dependency của source viết tay.

## 14. Source map và liên kết về DSL gốc

Generated source thường có cấu trúc khác với DSL. Khi compiler hoặc runtime báo lỗi trong artifact, source map hoặc metadata tương tự giúp chuyển vị trí về source DSL.

Artifact package có thể chứa:

- Source map.
- Source URI hoặc project-relative path.
- Source revision/hash.
- Symbol ID.
- Generated line/column.
- Original line/column.
- Generator version.

Workbench có thể dùng mapping để mở file DSL đúng vị trí khi người dùng click vào diagnostic của generated code. Nếu artifact được tạo từ nhiều file DSL, mapping cần giữ đúng source URI cho từng đoạn.

Source map phải khớp chính xác với artifact. Nếu generated source thay đổi nhưng map cũ vẫn được dùng, diagnostics sẽ trỏ sai. Vì vậy, source map và generated output nên được phát hành như một bộ có cùng build ID hoặc checksum liên kết.

## 15. Artifact dependency graph

Một artifact có thể phụ thuộc vào nhiều đầu vào và artifact khác. Ví dụ:

- Java source phụ thuộc domain model và runtime API.
- Route table phụ thuộc service declarations.
- Client stub phụ thuộc API schema.
- Documentation phụ thuộc schema và annotations.
- Package phụ thuộc source, resource và dependency runtime.

Có thể biểu diễn quan hệ thành DAG:

~~~mermaid
flowchart TD
    A[DSL files] --> B[Domain model]
    B --> C[Generated Java]
    B --> D[Generated schema]
    B --> E[Generated routes]
    C --> F[Compiled classes]
    D --> G[Validation bundle]
    E --> H[Runtime package]
    F --> H
    G --> H
~~~

Dependency graph giúp xác định artifact nào cần regenerate khi input thay đổi. Nếu chỉ route declaration thay đổi, có thể chỉ cần cập nhật route table và artifact downstream; không nhất thiết sinh lại documentation hoặc schema nếu chúng không phụ thuộc phần đó.

Dependency cần được khai báo đủ. Nếu generator đọc một template hoặc config mà không khai báo là input, cache có thể giữ output cũ sau khi template thay đổi.

## 16. Incremental generation và invalidation

Workbench và build system thường cần cập nhật artifact khi source thay đổi. Incremental generation chỉ chạy lại generator hoặc phần generator bị ảnh hưởng.

Một artifact có thể được xem là còn hợp lệ nếu tất cả yếu tố ảnh hưởng nội dung không đổi:

- Source revision hoặc content hash.
- Generator version.
- Schema version.
- Template version.
- Target platform.
- Generator options.
- Runtime API contract nếu code output phụ thuộc nó.
- Dependency artifact hashes.

Có thể lưu fingerprint:

~~~text
fingerprint =
  hash(source + generatorVersion + schemaVersion
       + templateVersion + options + dependencyHashes)
~~~

Nếu fingerprint hiện tại khớp manifest, artifact có thể được tái sử dụng. Nếu khác, cần regenerate hoặc invalidation.

Không nên chỉ dựa vào timestamp. Timestamp có thể có độ phân giải thấp, bị thay đổi khi checkout hoặc không phản ánh nội dung thực. Content hash thường đáng tin cậy hơn, dù chi phí tính hash cần được cân nhắc với kích thước đầu vào.

### 16.1. Invalidation theo dependency

Khi một artifact upstream thay đổi, tất cả artifact downstream phụ thuộc vào nó cần được xem xét. Một dependency graph chính xác cho phép chỉ invalidated phần liên quan.

### 16.2. Cache và reproducibility

Cache artifact nên được khóa theo fingerprint đầy đủ. Nếu cache key thiếu generator option hoặc target version, hệ thống có thể trả artifact không tương thích. Cache entry cũng cần metadata nguồn gốc để có thể debug khi kết quả bất ngờ.

## 17. Quản lý vòng đời artifact

Một artifact thường đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Planned
    Planned --> Generated
    Generated --> Validated
    Validated --> Registered
    Registered --> Consumed
    Consumed --> Stale
    Stale --> Planned
    Generated --> Failed
    Validated --> Failed
    Registered --> Removed
    Removed --> [*]
~~~

Ý nghĩa:

- **Planned:** artifact nằm trong generation plan.
- **Generated:** nội dung đã được tạo.
- **Validated:** nội dung và metadata vượt qua kiểm tra.
- **Registered:** framework/workbench đã nhận descriptor.
- **Consumed:** build, IDE hoặc runtime đã sử dụng.
- **Stale:** đầu vào hoặc dependency thay đổi, artifact không còn đại diện trạng thái mới.
- **Failed:** generation, validation hoặc registration thất bại.
- **Removed:** artifact đã được gỡ khỏi registry và storage theo policy.

Không phải mọi artifact cần tất cả trạng thái. Nhưng việc mô hình hóa lifecycle giúp xử lý lỗi và cập nhật có kiểm soát.

### 17.1. Stale artifact

Nếu DSL source bị xóa hoặc đổi tên, artifact cũ có thể còn trong output directory. Registry cần biết artifact đó không còn được sinh trong generation mới. Chỉ xóa nếu ownership được xác nhận và không có consumer khác đang giữ tham chiếu.

### 17.2. Unregistered artifact

Một tệp tồn tại nhưng không có manifest hoặc registry entry có thể là tệp viết tay, output cũ hoặc artifact từ tool khác. Không nên tự nhận quyền sở hữu và xóa nó. Workbench có thể đánh dấu là orphan và cho người dùng quyết định.

### 17.3. Failed registration

Nếu generation thành công nhưng registration thất bại, artifact chưa nên được xem là sẵn sàng cho runtime. Có thể giữ output trong staging để debug, hoặc rollback publication theo policy.

## 18. Cập nhật artifact an toàn

Một lần generate có thể tạo nhiều artifact. Nếu ghi từng tệp trực tiếp vào thư mục chính và tiến trình thất bại giữa chừng, framework có thể thấy tập output nửa mới nửa cũ.

Một quy trình an toàn:

1. Sinh toàn bộ artifact vào staging.
2. Kiểm tra nội dung và descriptor.
3. Kiểm tra dependency và target compatibility.
4. Tạo manifest mới.
5. Chuẩn bị publication plan.
6. Commit output và manifest theo cơ chế có thể khôi phục.
7. Cập nhật registry sau khi publication hoàn tất.
8. Invalidate consumer cache.
9. Dọn staging và artifact cũ theo ownership.

Với một tệp, atomic replace có thể đủ. Với nhiều tệp, cần journal, versioned output directory hoặc một cơ chế commit theo lô. Cập nhật registry trước khi tệp sẵn sàng có thể tạo tham chiếu tới artifact không tồn tại.

## 19. Tích hợp artifact vào package và deployment

Generated artifact chỉ có tác dụng ở runtime nếu được đóng gói và triển khai đúng.

Cần xác định:

- Artifact nằm ở classpath, module path hay resource path.
- Runtime loader tìm artifact theo ID hay đường dẫn.
- Dependency runtime được đóng gói cùng hay cung cấp bên ngoài.
- Có cần signature hoặc checksum xác minh không.
- Có giữ source map trong package production không.
- Có loại metadata phát triển khỏi package cuối không.
- Cách nâng cấp hoặc rollback artifact.
- Cách phân biệt artifact của các môi trường/profile.

Ví dụ, một route table JSON cần nằm trong package mà HTTP runtime có thể đọc. Nếu chỉ tồn tại trong thư mục build local, deployment container có thể không chứa nó. Build cần kiểm tra artifact thực sự nằm trong package cuối, không chỉ xác nhận generation task thành công.

## 20. Plugin và extension registry

Một workbench hoặc framework có thể cho phép plugin tiêu thụ artifact. Generated artifact có thể đăng ký một extension implementation hoặc capability mới.

Một plugin descriptor nên khai báo:

- Plugin ID và version.
- Entry point.
- API version.
- Artifact dependencies.
- Capabilities cần thiết.
- Compatibility constraints.
- Lifecycle hooks.
- Metadata hiển thị trong workbench.

Plugin loader cần xác thực descriptor và dependency trước khi nạp class hoặc chạy extension. Không nên thực thi plugin chỉ vì một file descriptor xuất hiện trong thư mục. Nguồn plugin cần được tin cậy hoặc chạy trong sandbox phù hợp.

## 21. Tích hợp với test và validation pipeline

Generated artifact cần được kiểm tra ở nhiều cấp:

- Generation output có đúng định dạng không.
- Source có compile được không.
- Resource có load được không.
- Schema có validate được dữ liệu không.
- Plugin có thỏa contract không.
- Runtime có khởi tạo được không.
- Source map có đưa lỗi về đúng DSL không.
- Package cuối có chứa đủ artifact và dependency không.

Build pipeline có thể có các phase:

~~~mermaid
flowchart LR
    A[Validate DSL] --> B[Generate]
    B --> C[Validate artifacts]
    C --> D[Compile and test]
    D --> E[Package]
    E --> F[Integration test]
    F --> G[Publish or deploy]
~~~

Một phase nên tiêu thụ output của phase trước qua task dependency rõ ràng. Nếu artifact validation thất bại, compile/package không nên tiếp tục với một phần output cũ trừ khi có policy fallback được công bố.

## 22. Diagnostics và truy vết nguồn gốc

Khi một artifact không được tích hợp thành công, thông báo lỗi cần cho biết:

- Artifact ID và kind.
- Generator và version.
- DSL source hoặc model liên quan.
- Đường dẫn artifact.
- Giai đoạn thất bại.
- Dependency hoặc contract bị vi phạm.
- Source span nếu lỗi bắt nguồn từ DSL.
- Hành động khắc phục.

Ví dụ:

~~~text
Artifact integration failed
ID: workflow.release.java
Stage: compile
Generated file: build/generated/sources/workflow/ReleaseWorkflow.java
Source: workflows/release.dsl:12:5
Cause: runtime API 2.1 does not provide WorkflowBuilder.retryPolicy(...)
Required runtime: >= 2.4
~~~

Nếu lỗi thuộc build configuration, cần chỉ ra source set hoặc task dependency còn thiếu. Nếu lỗi ở runtime, cần giữ stack trace gốc và mapping về DSL khi có thể.

## 23. Versioning và compatibility

Có ít nhất ba version cần phân biệt:

1. **DSL/schema version:** cấu trúc và semantics của nguồn.
2. **Generator version:** thuật toán và format đầu ra.
3. **Runtime/framework API version:** API mà artifact cần để chạy.

Ngoài ra có thể có artifact format version và manifest version. Không nên gộp tất cả vào một con số vì mỗi thành phần có thể thay đổi độc lập.

Compatibility matrix có thể giúp công bố phạm vi hỗ trợ:

| Generator | Runtime API | Artifact schema | Trạng thái |
|---|---|---|---|
| 2.3 | 2.3–2.x | 3 | Supported |
| 2.4 | 2.4–2.x | 3 | Supported |
| 3.0 | 3.x | 4 | Requires migration |

Đây là ví dụ minh họa. Khi artifact không tương thích, nên fail sớm ở validation/registration thay vì để lỗi xuất hiện muộn trong runtime.

## 24. Bảo mật và trust boundary

Generated artifact có thể chứa code thực thi, plugin, script, configuration hoặc đường dẫn tài nguyên. Tích hợp nó vào framework có nghĩa là trao cho nó một số quyền.

Cần kiểm soát:

- Artifact có đến từ generator đáng tin cậy không.
- Input DSL có thể điều khiển đường dẫn hoặc tên class hay không.
- Plugin được phép dùng capability nào.
- Runtime có xác minh checksum/signature không.
- Artifact có truy cập file, network hoặc secret không.
- Manifest có thể bị giả mạo hoặc sửa không.
- Source map có tiết lộ đường dẫn/nội dung nguồn không.
- Artifact có vượt giới hạn kích thước hoặc tài nguyên không.

Không nên coi generated code mặc nhiên an toàn chỉ vì nó được tạo tự động. Nếu DSL hoặc template có nội dung không tin cậy, output có thể chứa hành vi nguy hiểm. Cần validation, sandbox và permission enforcement ở đúng ranh giới.

## 25. Ví dụ tích hợp generated artifact trong Java workbench

Giả sử một DSL mô tả các workflow. Generator tạo:

- ReleaseWorkflow.java: generated source.
- workflow-index.json: runtime resource.
- ReleaseWorkflow.smap: source mapping.
- artifacts-manifest.json: metadata đăng ký.

Một workbench có thể thực hiện:

1. Parse và validate release.dsl.
2. Sinh bốn artifact vào staging.
3. Kiểm tra Java source và JSON resource.
4. Ghi manifest với artifact ID, version, hash và dependency.
5. Đăng ký generated source vào Java source set.
6. Đăng ký JSON resource với workflow runtime.
7. Cung cấp source map cho debugger.
8. Cập nhật artifact explorer.
9. Khi DSL thay đổi, tính fingerprint và regenerate phần bị ảnh hưởng.
10. Khi workflow bị xóa, gỡ registry entry và xóa artifact cũ nếu ownership vẫn hợp lệ.

Một descriptor Java giản lược:

~~~java
record ArtifactDescriptor(
    String id,
    ArtifactKind kind,
    Path location,
    String formatVersion,
    String generatorVersion,
    String sourceRevision,
    List<String> dependencies,
    String checksum
) {}

enum ArtifactKind {
    GENERATED_SOURCE,
    RESOURCE,
    SCHEMA,
    SOURCE_MAP,
    METADATA
}
~~~

Một service tích hợp:

~~~java
interface WorkbenchArtifactService {
    void publish(List<ArtifactDescriptor> artifacts);
    List<ArtifactDescriptor> findBySource(String sourceUri);
    void invalidate(String artifactId);
    void removeOwnedArtifacts(String sourceUri);
}
~~~

Đây là ví dụ thiết kế. Implementation cần xác định transaction publication, kiểm tra ownership, đồng bộ thread và API cụ thể của framework/workbench.

## 26. Kiểm thử tích hợp generated artifact

Kiểm thử nên xác nhận artifact có thể được tiêu thụ thực sự, không chỉ được tạo ra.

### 26.1. Kiểm thử contract

- Artifact ID ổn định.
- Kind và format chính xác.
- Manifest có generator/schema version.
- Dependency được khai báo đầy đủ.
- Hash khớp nội dung.
- Đường dẫn nằm trong output root.

### 26.2. Kiểm thử build integration

- Generated source được compile.
- Resource xuất hiện trong package.
- Task dependency bảo đảm generation chạy trước consumer.
- Build cache invalidates khi input hoặc generator version đổi.
- Không compile hoặc package một artifact hai lần.

### 26.3. Kiểm thử framework registration

- Registry phát hiện artifact.
- Registration lặp không tạo component trùng.
- Dependency thiếu tạo diagnostics rõ.
- Artifact không tương thích bị từ chối sớm.
- Unregister hoặc replacement giải phóng trạng thái cũ.

### 26.4. Kiểm thử workbench

- Artifact browser hiển thị đúng nguồn và trạng thái.
- Refresh sau generation.
- IDE index generated source.
- Diagnostics có thể điều hướng về DSL.
- Orphan/stale artifact được nhận diện.
- User-authored file không bị cleanup.

### 26.5. Kiểm thử lifecycle và failure

- Generation thất bại trước publication.
- Registration thất bại sau generation.
- Commit bị gián đoạn giữa nhiều tệp.
- Source thay đổi trong khi generation đang chạy.
- Hai generation chạy đồng thời.
- Rollback hoặc recovery không để registry trỏ đến output không tồn tại.

## 27. Quy trình triển khai tích hợp artifact

Có thể thực hiện theo các bước:

1. **Liệt kê artifact kinds:** xác định generator tạo source, resource, schema, metadata hay package.
2. **Định nghĩa contract:** ID, format, version, location, provenance, dependency và checksum.
3. **Chọn output layout:** tách generated source, resource, metadata và staging.
4. **Xây manifest/registry:** lưu ownership và thông tin consumer cần.
5. **Tích hợp build graph:** khai báo input/output và task dependency.
6. **Đăng ký với framework:** kết nối extension point hoặc runtime registry.
7. **Cập nhật workbench:** refresh workspace model, index và artifact browser.
8. **Giữ source mapping:** liên kết generated position về DSL khi cần.
9. **Thiết kế invalidation:** tính fingerprint và dependency graph.
10. **Quản lý publication:** staging, validation, commit và recovery.
11. **Đóng gói:** xác nhận artifact cùng dependency có trong package cuối.
12. **Kiểm thử consumer:** compile, load, register và runtime integration.
13. **Quản lý version:** kiểm tra generator, schema và runtime compatibility.
14. **Bảo vệ trust boundary:** xác minh nguồn gốc, quyền và integrity.

## 28. Nguyên tắc thiết kế

- **Xem artifact là sản phẩm có contract:** mô tả ID, kind, format, version và nguồn gốc.
- **Tách generation khỏi publication:** chỉ công bố artifact sau khi đã kiểm tra.
- **Dùng đường dẫn ổn định và tương đối:** không phụ thuộc máy developer.
- **Đăng ký đúng consumer:** source, resource, schema và plugin cần handler phù hợp.
- **Khai báo build dependency rõ ràng:** consumer chỉ chạy sau khi producer hoàn tất.
- **Theo dõi dependency và fingerprint:** invalidation phải phản ánh mọi input ảnh hưởng output.
- **Giữ manifest và registry nhất quán:** không để descriptor trỏ đến tệp chưa commit.
- **Quản lý stale/orphan theo ownership:** không xóa tệp không thuộc generator.
- **Giữ source mapping và provenance:** hỗ trợ diagnostics, debugger và truy vết.
- **Kiểm tra compatibility sớm:** generator, artifact schema và runtime API phải tương thích.
- **Tích hợp vào package thực tế:** tệp có trên disk chưa có nghĩa runtime sẽ tải được.
- **Cập nhật workbench có kiểm soát:** refresh index và UI theo vùng thay đổi.
- **Bảo vệ artifact như code thực thi:** xác minh integrity, quyền và capability.
- **Kiểm thử consumer end-to-end:** xác nhận framework, build, IDE và runtime thực sự sử dụng đúng artifact.

Tích hợp generated artifact hoàn tất khi đầu ra của DSL trở thành thành phần được quản lý và tiêu thụ đúng trong framework hoặc workbench. Một hợp đồng artifact rõ ràng, manifest và registry nhất quán, build dependency chính xác, source mapping, version compatibility và lifecycle có thể phục hồi giúp hệ thống biết artifact đến từ đâu, dùng ở đâu và khi nào cần cập nhật. Nhờ đó, việc sinh mã không còn là thao tác tạo tệp rời rạc mà trở thành một phần có kiểm soát của vòng đời phát triển và vận hành DSL.
