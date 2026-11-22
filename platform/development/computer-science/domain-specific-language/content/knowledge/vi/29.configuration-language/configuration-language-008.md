# Triển khai cấu hình

## 1. Triển khai cấu hình trong DSL là gì?

Một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL) thường cần các giá trị điều khiển cách parser, validator, generator hoặc runtime hoạt động. Những giá trị đó có thể là tên môi trường, giới hạn tài nguyên, quy tắc kiểm tra, endpoint dịch vụ, đường dẫn schema, chính sách retry hoặc lựa chọn backend.

**Triển khai cấu hình (configuration implementation)** là quá trình thiết kế và hiện thực cách hệ thống nhận, phân tích, kiểm tra, hợp nhất, lưu trữ và áp dụng các giá trị cấu hình trong suốt vòng đời của ứng dụng DSL.

Ví dụ, một công cụ DSL có thể được cấu hình:

~~~yaml
language:
  version: 2
  strictTypes: true

validation:
  failOnWarning: false
  maximumErrors: 100

generation:
  target: java
  packagePrefix: com.example.generated
~~~

Đây là cấu hình điều khiển công cụ. Nó khác với nội dung chương trình DSL mà người dùng viết để mô tả nghiệp vụ. Hai loại có thể dùng chung một định dạng văn bản nhưng cần được phân biệt về mục đích, schema, quyền chỉnh sửa và thời điểm áp dụng.

Một triển khai cấu hình tốt cần:

- Có mô hình dữ liệu và kiểu rõ ràng.
- Xác định các nguồn cấu hình được hỗ trợ.
- Có quy tắc ưu tiên khi nhiều nguồn cùng đặt một giá trị.
- Phân biệt giá trị mặc định, giá trị thiếu và giá trị null.
- Kiểm tra cú pháp, kiểu và ràng buộc nghiệp vụ.
- Xử lý secret và dữ liệu nhạy cảm an toàn.
- Áp dụng cấu hình theo đúng lifecycle.
- Hỗ trợ thay đổi cấu hình và reload có kiểm soát.
- Có khả năng quan sát, kiểm thử và tái lập.

## 2. Cấu hình và dữ liệu DSL

Trong một nền tảng DSL, có thể có nhiều lớp dữ liệu khác nhau:

| Loại dữ liệu | Ví dụ | Mục đích |
|---|---|---|
| Source DSL | workflow, policy, entity | Mô tả chương trình hoặc mô hình miền |
| Tool configuration | target, strict mode, cache | Điều khiển compiler và workbench |
| Project configuration | source folders, schema paths | Cấu hình riêng của project |
| Runtime configuration | endpoint, retry, timeout | Điều khiển ứng dụng khi chạy |
| User preferences | theme, editor font | Cá nhân hóa workbench |
| Secret configuration | API token, password | Cung cấp credential cho dịch vụ |

Không nên gom tất cả vào một object hoặc một file nếu chúng có vòng đời, quyền truy cập và chủ sở hữu khác nhau.

### 2.1 Configuration không phải source code

Source DSL thường có semantics riêng, có thể được parse thành AST và biên dịch. Configuration chủ yếu điều khiển cách hệ thống xử lý hoặc thực thi.

Ví dụ:

~~~text
policy "Discount"
  when order.total > 1000
  then discount 10 percent
~~~

đây là nội dung DSL. Trong khi:

~~~yaml
compiler:
  strictMode: true
  target: java
~~~

là cấu hình compiler.

### 2.2 Cấu hình có thể ảnh hưởng semantics

Dù configuration không phải source DSL, nó có thể làm thay đổi cách chương trình được hiểu hoặc chạy. Ví dụ:

- Language version quyết định cú pháp được chấp nhận.
- Decimal precision ảnh hưởng kết quả tính tiền.
- Timezone ảnh hưởng cách diễn giải ngày giờ.
- Feature flag có thể bật hoặc tắt một tính năng ngôn ngữ.
- Runtime policy có thể thay đổi retry hoặc authorization.

Vì vậy, cấu hình có ảnh hưởng semantics cần được lưu cùng metadata build hoặc execution để có thể tái lập kết quả.

## 3. Thiết kế configuration model

Trước khi chọn YAML, JSON hay TOML, cần xác định cấu trúc và kiểu dữ liệu của cấu hình.

Ví dụ model:

~~~java
public record CompilerConfiguration(
    LanguageConfiguration language,
    ValidationConfiguration validation,
    GenerationConfiguration generation
) {}

public record LanguageConfiguration(
    int version,
    boolean strictTypes
) {}

public record ValidationConfiguration(
    boolean failOnWarning,
    int maximumErrors
) {}

public record GenerationConfiguration(
    String target,
    String packagePrefix
) {}
~~~

Các record trên minh họa một cấu hình có kiểu. Framework thực tế có thể dùng class, immutable data object hoặc schema-generated model.

### 3.1 Typed configuration

Typed configuration chuyển dữ liệu văn bản thành các trường có kiểu như Boolean, Integer, Duration, Path hoặc enum. Điều này giúp phát hiện lỗi sớm và tránh việc mọi thành phần phải tự chuyển chuỗi.

### 3.2 Immutable configuration snapshot

Sau khi parse và validate, có thể tạo một snapshot bất biến:

~~~text
Raw configuration sources
          |
          v
Merge and resolve defaults
          |
          v
Validate
          |
          v
Immutable configuration snapshot
          |
          v
Compiler / Workbench / Runtime
~~~

Các thành phần trong cùng một lượt xử lý dùng cùng snapshot để không đọc những giá trị khác nhau giữa chừng.

### 3.3 Phân nhóm cấu hình

Nhóm theo trách nhiệm giúp tìm kiếm và quản lý dễ hơn:

- language: version, grammar feature, type policy.
- validation: rule enablement, severity, limits.
- generation: target, package, output directory.
- runtime: timeout, retry, connection pool.
- workspace: source root, include/exclude.
- editor: completion behavior, formatting.

Tránh tạo một nhóm quá rộng như misc hoặc options chứa nhiều key không liên quan.

### 3.4 Cấu hình mở rộng

Plugin có thể có namespace riêng:

~~~yaml
extensions:
  finance:
    maximumDiscountPercent: 30
  company.security:
    requireAuditReason: true
~~~

Host nên xác thực namespace và schema của plugin. Không nên chấp nhận mọi key tùy ý nếu chúng có thể bị bỏ qua âm thầm.

## 4. Nguồn cấu hình

Một ứng dụng thường nhận cấu hình từ nhiều nguồn:

- Giá trị mặc định trong code hoặc schema.
- File cấu hình hệ thống.
- File cấu hình người dùng.
- File cấu hình workspace hoặc project.
- Biến môi trường.
- Tham số dòng lệnh.
- Secret manager.
- API quản trị hoặc remote configuration service.
- Cấu hình tạm thời trong UI.

Mỗi nguồn có mục đích khác nhau. Ví dụ, tham số dòng lệnh phù hợp để override một lần chạy, còn file project phù hợp để chia sẻ trong version control.

### 4.1 Default configuration

Default là giá trị được dùng khi không có nguồn nào đặt key. Default nên được mô tả trong schema hoặc configuration model, không rải rác trong nhiều service.

### 4.2 System configuration

System configuration có thể do quản trị viên thiết lập cho toàn máy hoặc môi trường triển khai. Nó có thể đặt giới hạn bảo mật mà người dùng project không được phép nới lỏng.

### 4.3 User configuration

User configuration lưu lựa chọn cá nhân như editor theme hoặc đường dẫn công cụ. Không nên trộn các preference cá nhân vào file project nếu chúng không cần chia sẻ.

### 4.4 Project configuration

Project configuration thường được lưu trong repository để mọi thành viên có cùng thiết lập build, schema và target. Cần tránh lưu credential hoặc thông tin máy cá nhân.

### 4.5 Environment variables

Environment variables hữu ích trong CI/CD và container:

~~~text
DSL_TARGET=java
DSL_STRICT_TYPES=true
DSL_OUTPUT_DIR=build/generated
~~~

Chúng dễ tích hợp với hệ thống triển khai nhưng thường chỉ chứa chuỗi. Parser phải chuyển đổi và báo lỗi nếu giá trị không hợp lệ.

### 4.6 Command-line arguments

Ví dụ:

~~~text
dslc build --target java --strict-types --output build/generated
~~~

CLI override có thể hữu ích cho một lần chạy mà không cần sửa file project.

### 4.7 Remote configuration

Ứng dụng có thể tải cấu hình từ service quản trị. Cần xác thực nguồn, kiểm tra version, cache, timeout và hành vi khi không kết nối được.

### 4.8 Secret store

Credential nên được lấy từ secret manager hoặc hệ thống quản lý danh tính phù hợp. File cấu hình có thể chứa reference đến secret thay vì giá trị bí mật trực tiếp.

## 5. Thứ tự ưu tiên và hợp nhất cấu hình

Khi nhiều nguồn cùng đặt một key, hệ thống cần quy định nguồn nào thắng.

Một thứ tự minh họa:

~~~text
Built-in defaults
       |
       v
System configuration
       |
       v
User configuration
       |
       v
Project configuration
       |
       v
Environment variables
       |
       v
Command-line arguments
       |
       v
Effective configuration
~~~

Trong ví dụ này, nguồn ở dưới có ưu tiên cao hơn. Hệ thống khác có thể chọn thứ tự khác, nhưng cần công bố rõ.

### 5.1 Override theo key

Thông thường, các nguồn được hợp nhất theo từng key. Nếu file project đặt target=java và CLI đặt target=typescript, giá trị hiệu lực là typescript theo thứ tự trên.

### 5.2 Merge object và replace list

Không phải mọi kiểu dữ liệu đều nên merge giống nhau:

- Object có thể merge theo từng key.
- Scalar thường được thay thế toàn bộ.
- List có thể replace, append hoặc merge theo identity.
- Map có thể merge theo key.

Chính sách phải được định nghĩa. Nếu list includePaths bị append từ nhiều nguồn, kết quả khác với việc nguồn ưu tiên cao thay thế toàn bộ list.

### 5.3 Null và xóa giá trị

Một nguồn có thể đặt null để xóa giá trị hoặc biểu thị giá trị rỗng. Cần phân biệt:

- Key không xuất hiện.
- Key xuất hiện với null.
- Key xuất hiện với empty string.
- Key bị xóa tường minh.

Có thể dùng sentinel hoặc cú pháp delete riêng khi cần loại bỏ một giá trị được kế thừa.

### 5.4 Nguồn bị khóa

Một số setting như trust policy, giới hạn bảo mật hoặc endpoint quản trị có thể không cho project override. Configuration merger cần hỗ trợ locked key hoặc policy constraint.

### 5.5 Giải thích nguồn của giá trị hiệu lực

Để debug, nên có khả năng trả lời:

- Giá trị hiện tại là gì?
- Nó đến từ nguồn nào?
- Có bị override không?
- Default ban đầu là gì?
- Key có bị khóa không?

Thông tin provenance giúp người dùng hiểu vì sao một giá trị có hiệu lực.

## 6. Parsing configuration

Sau khi chọn nguồn và đọc byte, hệ thống cần parse nội dung theo format.

~~~text
Configuration file
       |
       v
Read bytes
       |
       v
Decode UTF-8
       |
       v
Parse YAML / JSON / TOML
       |
       v
Generic syntax tree
       |
       v
Bind to typed model
~~~

### 6.1 Chọn parser

Mỗi format cần parser tương ứng. Không nên parse YAML bằng cách tự tách dòng hoặc parse CSV bằng split dấu phẩy vì các format có quy tắc quote, escape và nesting riêng.

### 6.2 Parser error

Diagnostic nên chỉ ra:

- File hoặc nguồn cấu hình.
- Dòng và cột.
- Key hoặc node liên quan.
- Loại lỗi cú pháp.
- Gợi ý sửa nếu có thể.

### 6.3 Unknown keys

Nếu file có key mà schema không biết, hệ thống có thể:

- Từ chối.
- Cảnh báo.
- Bỏ qua theo chế độ tương thích.
- Chuyển key cho plugin sở hữu namespace tương ứng.

Chính sách cần rõ. Bỏ qua mọi key không biết có thể che giấu lỗi đánh máy.

### 6.4 Duplicate keys

Một số parser hoặc format cho phép key trùng theo cách khác nhau. Với cấu hình, duplicate key thường gây mơ hồ. Nên từ chối hoặc áp dụng chính sách được tài liệu hóa, thay vì phụ thuộc parser implementation.

### 6.5 Include file

Một file cấu hình có thể include file khác:

~~~yaml
include:
  - config/base.yml
  - config/development.yml
~~~

Include cần quy tắc về:

- Đường dẫn tương đối tính từ đâu.
- Thứ tự áp dụng.
- Vòng lặp include.
- Giới hạn độ sâu.
- File không tồn tại.
- Quyền đọc file.
- Có cho phép URL hoặc remote include không.

Không nên tải URL hoặc đọc path tùy ý từ cấu hình không tin cậy.

## 7. Binding vào kiểu dữ liệu

Sau khi parse thành generic tree, binder chuyển dữ liệu thành model có kiểu.

Ví dụ YAML:

~~~yaml
retry:
  count: 3
  delay: 5s
~~~

Typed model:

~~~java
public record RetryConfiguration(
    int count,
    Duration delay
) {}
~~~

### 7.1 Type conversion

Binder có thể chuyển:

- Chuỗi số thành integer hoặc decimal.
- Chuỗi duration thành Duration.
- Chuỗi path thành Path.
- Tên enum thành enum constant.
- Mapping thành record hoặc class.

Chuyển đổi cần tường minh. Không nên ép kiểu tự động theo cách mất dữ liệu.

### 7.2 Numeric precision

Nếu cấu hình có giá trị tiền tệ hoặc precision, tránh parse thành double khi cần decimal chính xác. Xác định rõ kiểu số và giới hạn.

### 7.3 Enum

Ví dụ:

~~~yaml
generation:
  target: java
~~~

Binder chuyển java thành TargetLanguage.JAVA. Nếu giá trị là target không được hỗ trợ, diagnostic nên liệt kê các lựa chọn hợp lệ.

### 7.4 Path

Path tương đối cần có base directory rõ ràng. Một path trong project config thường được resolve tương đối với thư mục project, còn path trong user config có thể dùng một base khác.

### 7.5 Duration

Định dạng như 5s, 200ms hoặc PT5S cần một grammar xác định. Không nên tự đoán đơn vị nếu thiếu suffix.

### 7.6 Không ép kiểu im lặng

Nếu retryCount là chuỗi "many", không nên tự đổi thành 0. Hãy báo lỗi cấu hình và chỉ áp dụng default nếu chính sách cho phép fallback rõ ràng.

## 8. Default value và giá trị thiếu

Default giúp cấu hình ngắn gọn, nhưng cần được thiết kế cẩn thận.

Ví dụ:

~~~yaml
validation:
  maximumErrors: 100
~~~

Nếu failOnWarning không xuất hiện, hệ thống có thể dùng default false.

### 8.1 Default ở một nơi

Nên định nghĩa default trong schema hoặc configuration model. Nếu mỗi service tự đặt default, cùng một key có thể có giá trị khác nhau.

### 8.2 Missing và null

Missing có thể có nghĩa dùng default. Null có thể có nghĩa không có giá trị, xóa giá trị kế thừa hoặc dữ liệu không hợp lệ. Không nên gộp chúng nếu semantics khác nhau.

### 8.3 Default phụ thuộc môi trường

Một số default có thể phụ thuộc môi trường:

- Development bật debug.
- Production tắt verbose logging.
- CI dùng deterministic build.

Nếu dùng environment-dependent defaults, cần ghi nhận môi trường hoặc effective configuration để tái lập.

### 8.4 Default phụ thuộc field khác

Ví dụ outputDirectory có thể mặc định là build/generated khi target là Java và dist/generated khi target là TypeScript. Default phụ thuộc cần được tính sau khi các giá trị liên quan đã được resolve.

### 8.5 Deprecation của default

Khi đổi default, hành vi ứng dụng có thể thay đổi dù file cấu hình không đổi. Cần ghi nhận thay đổi trong release notes và cân nhắc migration hoặc pin version.

## 9. Validation cấu hình

Một file parse thành công chưa chắc là cấu hình hợp lệ.

Nên chia validation thành nhiều tầng:

1. Syntax validation.
2. Type validation.
3. Schema validation.
4. Cross-field validation.
5. Environment validation.
6. Security/policy validation.

### 9.1 Schema validation

Ví dụ:

~~~yaml
generation:
  target: java
  packagePrefix: com.example.generated
~~~

Schema có thể yêu cầu target là một trong java, typescript hoặc python; packagePrefix là chuỗi hợp lệ.

### 9.2 Range validation

~~~yaml
validation:
  maximumErrors: 100
~~~

maximumErrors có thể phải nằm trong khoảng 1 đến 10000.

### 9.3 Cross-field validation

Một số key chỉ hợp lệ khi đi cùng nhau:

~~~yaml
remoteCache:
  enabled: true
  endpoint: https://cache.example.test
~~~

Nếu enabled là true thì endpoint phải tồn tại. Nếu enabled là false, endpoint có thể được bỏ qua.

### 9.4 Environment validation

Một đường dẫn có thể hợp lệ về cú pháp nhưng file không tồn tại hoặc process không có quyền đọc. Đây là lỗi môi trường, khác với lỗi schema.

### 9.5 Semantic validation

Một cấu hình có thể đúng kiểu nhưng vi phạm quy tắc nghiệp vụ. Ví dụ timeout của một bước workflow không được lớn hơn deadline của toàn workflow.

### 9.6 Diagnostics

Diagnostic nên chứa:

- Configuration key.
- Nguồn file hoặc environment variable.
- Source range nếu parser cung cấp.
- Severity.
- Giá trị hiện tại (đã che secret nếu cần).
- Giá trị mong đợi hoặc tập giá trị hợp lệ.
- Gợi ý khắc phục.

Không đưa giá trị secret nguyên văn vào message hoặc log.

## 10. Hợp nhất cấu hình và tạo effective configuration

Sau khi từng nguồn được parse và validate sơ bộ, hệ thống hợp nhất chúng.

~~~text
Defaults ----\
System -------\
User ----------> Merge policy --> Effective model
Project -------/                     |
Environment ---/                     v
CLI -----------/                Final validation
                                      |
                                      v
                                Apply configuration
~~~

### 10.1 Hai giai đoạn validation

Validation từng nguồn có thể kiểm tra cú pháp và kiểu. Validation sau merge kiểm tra những ràng buộc chỉ biết được khi có effective values.

Ví dụ, file project không có endpoint nhưng environment variable cung cấp endpoint. Chỉ sau merge mới biết cấu hình cuối có đủ thông tin.

### 10.2 Merge có provenance

Mỗi giá trị hiệu lực có thể lưu nguồn tạo ra nó:

~~~text
target:
  value: java
  source: command-line
  overridden:
    - project.yml
    - default
~~~

Provenance không nhất thiết được lưu trong object runtime chính, nhưng hữu ích cho diagnostics và lệnh giải thích cấu hình.

### 10.3 Không thay đổi global state trong lúc merge

Hãy xây effective configuration mới như một snapshot. Chỉ công bố snapshot sau khi parse, merge và validation hoàn tất.

### 10.4 Configuration fingerprint

Có thể tính fingerprint từ effective configuration đã canonicalize để:

- Xác định build có cùng cấu hình không.
- Làm cache key.
- Ghi metadata artifact.
- So sánh giữa môi trường.

Không đưa secret thô vào fingerprint hoặc log. Nếu secret ảnh hưởng kết quả, dùng identifier/version của secret hoặc một cơ chế fingerprint an toàn phù hợp.

## 11. Áp dụng cấu hình vào framework

Sau khi tạo effective configuration hợp lệ, framework cần áp dụng nó vào các service.

### 11.1 Constructor injection

Một cách an toàn là truyền configuration khi tạo service:

~~~java
Compiler compiler = new Compiler(configuration);
~~~

Service nhận snapshot bất biến và không cần tự đọc file cấu hình.

### 11.2 Configuration provider

Một provider có thể cung cấp snapshot hiện tại:

~~~java
interface ConfigurationProvider {
    ConfigurationSnapshot current();
}
~~~

Với request cần tính nhất quán, nên lấy snapshot một lần rồi truyền xuống các tầng thay vì gọi current() nhiều lần giữa chừng.

### 11.3 Tách configuration khỏi business logic

Không nên để mọi hàm tự đọc environment variable hoặc parse YAML. Hãy tập trung việc đọc và hợp nhất ở một lớp, rồi truyền giá trị đã được kiểm tra vào thành phần cần dùng.

### 11.4 Startup configuration

Một số key phải được biết trước khi khởi tạo service, ví dụ port, storage provider hoặc database connection. Chúng cần được load trước startup phase tương ứng.

### 11.5 Runtime configuration

Một số key có thể thay đổi khi ứng dụng đang chạy, ví dụ log level hoặc feature flag. Chỉ các thành phần được thiết kế hỗ trợ dynamic update mới nên nhận thay đổi đó.

## 12. Static configuration và dynamic configuration

Không phải mọi setting đều có thể reload an toàn.

| Loại | Ví dụ | Cách áp dụng |
|---|---|---|
| Startup-only | Port, plugin classpath | Cần restart |
| Workspace-scoped | Source roots, schema paths | Reload project/index |
| Request-scoped | Timeout override cho một request | Gắn vào request context |
| Dynamic | Log level, một số feature flag | Cập nhật snapshot hoặc service |
| Immutable build input | Language version, target | Tạo build mới |

### 12.1 Startup-only

Thay đổi port sau khi server đã bind thường không thể chỉ cập nhật một field. Cần lifecycle restart hoặc cơ chế rebind riêng.

### 12.2 Dynamic setting

Log level có thể thay đổi runtime nếu logger hỗ trợ. Tuy nhiên, thay đổi cần được công bố nhất quán đến các component.

### 12.3 Immutable build input

Language version hoặc target code generation thường cần tạo compilation context mới. Không nên đổi giữa chừng khi một build đang chạy.

### 12.4 Ghi rõ khả năng reload

Schema hoặc documentation nên nêu setting nào reloadable, setting nào cần restart và phạm vi ảnh hưởng.

## 13. Reload cấu hình

Reload là quá trình đọc lại nguồn cấu hình và áp dụng một snapshot mới.

Một quy trình:

~~~text
File change / admin update
          |
          v
Read new configuration
          |
          v
Parse and bind
          |
          v
Merge and validate
          |
          v
Build new snapshot
          |
          v
Check reload compatibility
          |
          v
Publish snapshot atomically
          |
          v
Notify interested services
~~~

### 13.1 Validate trước khi publish

Nếu cấu hình mới không hợp lệ, giữ snapshot cũ và báo lỗi. Không nên thay thế cấu hình đang hoạt động bằng object chưa được validate.

### 13.2 Atomic swap

Một cách là lưu snapshot trong AtomicReference:

~~~java
AtomicReference<ConfigurationSnapshot> current =
    new AtomicReference<>(initialSnapshot);

void publish(ConfigurationSnapshot next) {
    current.set(next);
}
~~~

Các request mới lấy snapshot mới. Request đang chạy có thể tiếp tục dùng snapshot cũ đến khi kết thúc.

### 13.3 Listener

Service có thể đăng ký listener để nhận thông báo cấu hình thay đổi. Listener cần được quản lý lifecycle và không nên làm chậm quá trình publish.

### 13.4 Debounce file watcher

Một lần lưu file có thể tạo nhiều filesystem event. Watcher nên debounce hoặc chờ file ổn định trước khi parse, nhưng không được bỏ lỡ thay đổi thực sự.

### 13.5 Reload thất bại

Nếu parse hoặc validation thất bại:

- Giữ snapshot cũ.
- Báo lỗi gắn với nguồn cấu hình.
- Ghi nhận thời điểm reload thất bại.
- Không để một phần service dùng cấu hình mới và phần khác dùng cấu hình cũ ngoài chủ ý.

### 13.6 Reload nhiều file

Nếu configuration gồm nhiều file, cần xác định snapshot được tạo từ một phiên bản nhất quán của tất cả file. Nếu file thay đổi trong lúc đọc, có thể cần đọc lại hoặc dùng version/hash để phát hiện.

## 14. Secret và dữ liệu nhạy cảm

Configuration thường chứa hoặc tham chiếu đến:

- Password.
- API token.
- Private key.
- Database credential.
- Certificate.
- Signing secret.

Các giá trị này cần xử lý riêng.

### 14.1 Không commit secret vào repository

File project nên chứa tên biến hoặc reference:

~~~yaml
database:
  username: app_user
  password:
    fromSecret: billing/database-password
~~~

Runtime lấy secret từ secret provider theo identity được cấp.

### 14.2 Environment variable

Environment variable có thể dùng cho môi trường đơn giản hoặc container, nhưng cần nhớ chúng có thể xuất hiện trong process inspection, dump hoặc diagnostic nếu ứng dụng xử lý sai.

### 14.3 Secret manager

Secret manager có thể cung cấp:

- Access control.
- Rotation.
- Audit.
- Versioning.
- Expiration.

Ứng dụng cần xử lý secret hết hạn hoặc rotation mà không ghi credential vào log.

### 14.4 Redaction

Khi hiển thị effective configuration, các trường secret phải được che:

~~~text
database.password = ********
api.token = [REDACTED]
~~~

Redaction cần dựa trên metadata/schema của key, không chỉ dựa vào tên có chứa password. Secret có thể nằm trong field tên khác.

### 14.5 Không đưa secret vào error message

Nếu kết nối thất bại, message nên nói nguồn và loại lỗi, không in URL chứa password hoặc nguyên văn credential.

## 15. Bảo mật của configuration

Configuration có thể điều khiển file path, plugin, network endpoint, command hoặc quyền runtime. Vì vậy, nó là một bề mặt tấn công.

### 15.1 Path traversal

Nếu cấu hình cho phép output path, không nên chấp nhận đường dẫn tùy ý vượt ra ngoài vùng được phép. Chuẩn hóa path và kiểm tra root policy.

### 15.2 Remote include

Một file cấu hình không tin cậy có thể yêu cầu tải remote include. Điều này có thể tạo SSRF hoặc tải nội dung ngoài dự kiến. Chỉ cho phép nếu có policy, allowlist và kiểm tra nguồn.

### 15.3 Plugin activation

Không tự động nạp mã plugin chỉ vì một file cấu hình có tên plugin. Cần xác thực nguồn, dependency và quyền.

### 15.4 Unsafe deserialization

Dùng safe parser cho YAML hoặc format có khả năng gắn tag/constructor. Không deserialize object tùy ý từ dữ liệu không tin cậy.

### 15.5 Resource exhaustion

Giới hạn:

- Kích thước file.
- Độ sâu cấu trúc.
- Số include.
- Số key.
- Kích thước string.
- Thời gian parse.

### 15.6 Configuration injection

Nếu giá trị cấu hình được nhúng vào SQL, shell hoặc HTML, phải dùng API tham số hóa hoặc serializer đúng ngữ cảnh. Không nối chuỗi tùy tiện.

### 15.7 Quyền override

Project config không nên có quyền tắt policy bảo mật do quản trị viên bắt buộc. Cần tách setting có thể override và setting được khóa.

## 16. Persistence và lưu cấu hình

Hệ thống cần quyết định cấu hình được lưu ở đâu và theo vòng đời nào.

### 16.1 File trong repository

Project config được commit để nhóm dùng chung. Nên chứa giá trị có thể tái lập và tránh thông tin phụ thuộc máy cá nhân.

### 16.2 User home

User preferences có thể nằm trong thư mục cấu hình người dùng. Chúng không nên làm thay đổi build của project nếu không được yêu cầu.

### 16.3 Database

Ứng dụng quản trị có thể lưu cấu hình trong database để hỗ trợ nhiều workspace hoặc người dùng. Cần version, transaction và audit.

### 16.4 Remote configuration service

Service trung tâm giúp quản lý nhiều instance nhưng cần xác thực, cache, fallback và consistency policy.

### 16.5 Atomic file write

Khi ghi file cấu hình:

1. Serialize vào file tạm.
2. Flush và đóng file.
3. Validate file vừa ghi nếu cần.
4. Replace file đích theo cơ chế atomic được filesystem hỗ trợ.

Điều này giảm nguy cơ file bị cắt cụt nếu tiến trình dừng giữa lúc ghi. Atomic rename và durability phụ thuộc filesystem và nền tảng.

### 16.6 Concurrent update

Hai tiến trình cùng sửa cấu hình có thể ghi đè lẫn nhau. Có thể dùng lock, revision number, compare-and-swap hoặc service quản lý cấu hình có version.

## 17. Configuration schema và documentation

Một configuration schema là hợp đồng giữa người viết file và ứng dụng.

Schema nên mô tả:

- Key path.
- Kiểu dữ liệu.
- Required/optional.
- Default.
- Nullable.
- Min/max hoặc pattern.
- Enum choices.
- Reloadability.
- Override policy.
- Secret classification.
- Deprecated/removed version.

Ví dụ bảng tài liệu:

| Key | Type | Default | Reloadable | Mô tả |
|---|---|---|---|---|
| language.version | integer | 1 | No | Phiên bản DSL |
| language.strictTypes | boolean | true | Theo project reload | Bật kiểm tra kiểu nghiêm ngặt |
| validation.maximumErrors | integer | 100 | Có | Số lỗi tối đa tích lũy |
| generation.target | enum | java | No trong build đang chạy | Backend sinh mã |
| runtime.requestTimeout | duration | 5s | Có nếu service hỗ trợ | Timeout request |

### 17.1 Machine-readable schema

Schema có thể được dùng bởi editor để cung cấp completion, hover, validation và documentation. Một schema tốt giúp người dùng biết key nào hợp lệ trước khi chạy ứng dụng.

### 17.2 Deprecation

Key cũ nên được đánh dấu deprecated với thông tin thay thế và phiên bản loại bỏ dự kiến.

### 17.3 Unknown key policy

Trong development, có thể báo warning cho key lạ. Trong production hoặc CI, có thể từ chối để tránh cấu hình sai âm thầm.

### 17.4 Examples

Mỗi nhóm cấu hình nên có ví dụ nhỏ và ví dụ đầy đủ. Ví dụ cần phản ánh đúng default và version của schema.

## 18. Versioning và migration cấu hình

Cấu hình tồn tại lâu dài và có thể được đọc bởi phiên bản ứng dụng khác.

### 18.1 Schema version

Ví dụ:

~~~yaml
schemaVersion: 2
generation:
  target: java
~~~

Schema version giúp ứng dụng chọn parser, validator hoặc migration tương ứng.

### 18.2 Backward compatibility

Ứng dụng mới có thể đọc cấu hình cũ và chuyển đổi sang model mới.

### 18.3 Forward compatibility

Ứng dụng cũ có thể gặp key mới. Nó có thể bỏ qua unknown key nếu hợp đồng cho phép, nhưng cần cẩn thận vì bỏ qua key bảo mật hoặc key bắt buộc có thể gây hành vi sai.

### 18.4 Migration

Ví dụ đổi:

~~~yaml
compiler:
  strict: true
~~~

thành:

~~~yaml
language:
  strictTypes: true
~~~

Migration cần:

1. Đọc schema version cũ.
2. Parse bằng model tương ứng.
3. Chuyển key và giá trị.
4. Kiểm tra collision nếu cả key cũ và mới cùng tồn tại.
5. Validate model mới.
6. Hiển thị diff hoặc backup.
7. Ghi file mới nếu người dùng hoặc workflow cho phép.

### 18.5 Không tự ghi đè cấu hình cũ khi đọc

Parsing không nên âm thầm sửa file nguồn. Tách migration thành thao tác riêng để người dùng có thể xem và kiểm soát thay đổi.

### 18.6 Deprecation window

Thông báo key deprecated trước khi loại bỏ. Nêu rõ phiên bản cuối cùng hỗ trợ và cách thay thế.

## 19. Cấu hình cho môi trường và deployment

Một project DSL có thể chạy trong development, test, staging và production.

Ví dụ:

~~~text
config/
  base.yml
  development.yml
  test.yml
  production.yml
~~~

### 19.1 Base configuration

Base chứa giá trị chung cho mọi môi trường.

### 19.2 Environment override

File môi trường chỉ chứa các khác biệt cần thiết. Tránh sao chép toàn bộ cấu hình base vì hai file dễ lệch nhau.

### 19.3 Environment identity

Tên môi trường nên được xác định rõ bằng biến hoặc tham số triển khai. Không nên suy ra production chỉ từ tên hostname không ổn định.

### 19.4 Twelve-factor style

Một nguyên tắc triển khai phổ biến là tách cấu hình thay đổi theo môi trường khỏi artifact build. Cùng một artifact có thể được triển khai ở nhiều môi trường với cấu hình khác nhau.

### 19.5 Không để cấu hình làm thay đổi artifact ngoài ý muốn

Nếu target hoặc language version ảnh hưởng nội dung generated code, chúng là build inputs và cần được ghi nhận. Runtime endpoint thường có thể thay đổi mà không cần build lại, tùy kiến trúc.

### 19.6 CI/CD

Pipeline CI nên:

- Kiểm tra schema cấu hình.
- Kiểm tra secret reference.
- Dùng cấu hình test tách biệt.
- Ghi nhận effective non-secret configuration.
- Không in secret trong log.
- Phát hiện cấu hình thiếu hoặc khác môi trường.

## 20. Configuration trong DSL workbench

Workbench có thể cung cấp UI để chỉnh cấu hình thay vì yêu cầu người dùng sửa YAML thủ công.

### 20.1 Property page

Một property page có thể hiển thị:

- Nhóm setting.
- Giá trị hiện tại.
- Default.
- Nguồn của giá trị.
- Validation message.
- Trạng thái reload.

### 20.2 Completion và hover

Schema cho phép editor gợi ý key, kiểu và mô tả:

~~~yaml
generation:
  target: |
~~~

Completion có thể đề xuất java, typescript và python.

### 20.3 Validation trực tiếp

Khi người dùng nhập maximumErrors: -1, editor có thể báo lỗi ngay tại giá trị.

### 20.4 Preview effective configuration

Workbench có thể hiển thị cấu hình sau merge và nguồn của từng giá trị. Secret phải được che.

### 20.5 Apply và reload

UI cần phân biệt Save file với Apply runtime configuration. Một số thay đổi cần restart hoặc reindex, không thể có hiệu lực ngay.

### 20.6 Undo

Chỉnh sửa cấu hình trong workbench nên hỗ trợ undo và hiển thị diff trước khi lưu hoặc apply nếu thay đổi có phạm vi lớn.

## 21. Cấu hình và khả năng tái lập

Hai lần chạy cùng source nhưng dùng cấu hình khác có thể tạo kết quả khác nhau.

Để tái lập:

- Ghi nhận language version.
- Ghi nhận target và generator version.
- Ghi nhận effective configuration không chứa secret.
- Ghi nhận plugin và extension version.
- Ghi nhận schema version.
- Ghi nhận dependency lock hoặc artifact identity.
- Giữ configuration fingerprint.

### 21.1 Build metadata

Artifact sinh ra có thể kèm metadata:

~~~text
source revision: 4a8c...
language version: 2
generator: java-generator 3.1
configuration fingerprint: 91bd...
~~~

Không ghi secret hoặc giá trị nhạy cảm vào metadata công khai.

### 21.2 Deterministic configuration

Nếu list hoặc map có thứ tự không ổn định, output có thể thay đổi giữa các lần chạy. Cần canonicalize hoặc định nghĩa thứ tự nếu output cần reproducible.

### 21.3 Drift detection

Trong production, effective configuration thực tế có thể lệch với cấu hình mong muốn. Có thể so sánh fingerprint hoặc policy snapshot để phát hiện drift.

### 21.4 Audit

Với setting nhạy cảm, lưu ai thay đổi, lúc nào, từ nguồn nào và giá trị nào đã thay đổi. Tránh ghi secret nguyên văn; dùng metadata hoặc version reference.

## 22. Kiểm thử configuration implementation

Configuration cần được kiểm thử độc lập và qua toàn bộ lifecycle.

### 22.1 Parser tests

- File hợp lệ.
- Syntax error.
- Encoding lỗi.
- Duplicate key.
- Unknown key.
- File rỗng.
- File quá lớn.
- Include lồng nhau.

### 22.2 Binding tests

- Kiểu đúng.
- Kiểu sai.
- Enum không tồn tại.
- Duration không hợp lệ.
- Path tương đối.
- Numeric boundary.
- Null và missing.

### 22.3 Merge tests

- Thứ tự ưu tiên.
- Object merge.
- List replace/append theo policy.
- Null/delete semantics.
- Locked setting.
- Provenance.

### 22.4 Validation tests

- Required field.
- Min/max.
- Cross-field dependency.
- Environment resource missing.
- Security policy violation.
- Plugin configuration schema.

### 22.5 Reload tests

- Reload hợp lệ.
- Reload không hợp lệ giữ snapshot cũ.
- Nhiều file đổi cùng lúc.
- File watcher phát duplicate event.
- Request đang chạy giữ snapshot cũ.
- Request mới nhận snapshot mới.
- Listener lỗi không làm hỏng toàn bộ publish.

### 22.6 Secret tests

- Secret không xuất hiện trong log.
- Secret bị che trong UI.
- Missing secret được báo rõ.
- Rotation được xử lý.
- Quyền truy cập bị từ chối an toàn.

### 22.7 Integration tests

Chạy compiler hoặc runtime với cấu hình thực tế và xác nhận target, validation rules, paths và behavior đúng theo effective configuration.

## 23. Những sai lầm thường gặp

### Đọc cấu hình ở mọi nơi

Mỗi service tự đọc file hoặc environment variable tạo kết quả không nhất quán.

**Cách khắc phục:** tập trung load, merge và validate; truyền snapshot có kiểu qua dependency injection.

### Không định nghĩa precedence

Người dùng không biết vì sao một giá trị bị override.

**Cách khắc phục:** công bố thứ tự nguồn và cung cấp provenance.

### Gộp missing với null

Default hoặc kế thừa có thể hoạt động sai.

**Cách khắc phục:** định nghĩa semantics riêng cho missing, null, empty và delete.

### Chỉ parse mà không validate

Một giá trị có thể đúng cú pháp nhưng sai kiểu, ngoài range hoặc không phù hợp môi trường.

**Cách khắc phục:** validation nhiều tầng trước khi apply.

### Thay cấu hình đang chạy từng phần

Service A dùng snapshot mới trong khi service B vẫn dùng snapshot cũ ngoài chủ ý.

**Cách khắc phục:** publish snapshot nguyên tử và xác định consistency boundary.

### Reload cấu hình không hợp lệ

Ứng dụng có thể rơi vào trạng thái một phần mới, một phần cũ.

**Cách khắc phục:** parse và validate trước; nếu lỗi, giữ snapshot cũ.

### Lưu secret trong repository

Credential có thể bị lộ qua Git hoặc log.

**Cách khắc phục:** dùng secret manager hoặc environment injection có kiểm soát, redaction và rotation.

### Cho project override mọi setting

Project có thể vô hiệu hóa policy do quản trị viên bắt buộc.

**Cách khắc phục:** phân loại setting được override và setting bị khóa.

### Không version hóa schema

Ứng dụng mới có thể diễn giải file cũ theo semantics khác.

**Cách khắc phục:** schema version, migration và deprecation policy.

### Không ghi nhận effective configuration

Khó tái lập bug hoặc so sánh môi trường.

**Cách khắc phục:** lưu fingerprint và metadata không nhạy cảm.

## 24. Quy trình triển khai configuration

Khi xây dựng configuration subsystem cho DSL, có thể thực hiện:

1. **Phân loại setting:** tool, project, user, runtime, secret và preference.
2. **Thiết kế typed model:** nhóm key theo trách nhiệm và dùng kiểu cụ thể.
3. **Định nghĩa schema:** required, default, nullable, range, enum và reloadability.
4. **Chọn nguồn:** file, environment, CLI, secret store hoặc remote service.
5. **Quy định precedence:** merge, replace, append, null và locked key.
6. **Parse an toàn:** encoding, parser limits, duplicate key và include policy.
7. **Bind kiểu:** Duration, Path, enum, decimal và domain type.
8. **Validate:** syntax, schema, cross-field, environment và security.
9. **Tạo snapshot:** immutable effective configuration kèm provenance.
10. **Inject vào service:** không để business logic tự đọc nguồn thô.
11. **Áp dụng theo lifecycle:** startup-only, dynamic, request-scoped hoặc build-scoped.
12. **Thiết kế reload:** validate trước, atomic publish, listener và fallback.
13. **Bảo vệ secret:** secret provider, redaction và audit.
14. **Version và migrate:** schema version, compatibility và deprecation.
15. **Kiểm thử:** parser, binder, merge, validation, reload, security và integration.
16. **Quan sát:** log nguồn, fingerprint, trạng thái reload và drift mà không lộ dữ liệu nhạy cảm.

## 25. Ví dụ tổng hợp: cấu hình một DSL compiler

Một project dùng file:

~~~yaml
schemaVersion: 2

language:
  version: 2
  strictTypes: true

validation:
  maximumErrors: 100
  failOnWarning: false

generation:
  target: java
  packagePrefix: com.example.generated
  outputDirectory: build/generated

runtime:
  requestTimeout: 5s

extensions:
  finance:
    enabled: true
    maximumDiscountPercent: 30
~~~

### 25.1 Typed model

Binder tạo một CompilerConfiguration với LanguageConfiguration, ValidationConfiguration, GenerationConfiguration, RuntimeConfiguration và extension settings.

### 25.2 Hợp nhất nguồn

Giả sử:

- Default đặt target là java.
- Project file đặt target là java.
- CLI đặt target là typescript.
- System policy khóa strictTypes=true.

Effective configuration:

~~~text
generation.target = typescript
language.strictTypes = true
~~~

CLI override target. Project không thể tắt strictTypes vì setting đó bị khóa bởi system policy.

### 25.3 Validation

Hệ thống kiểm tra:

- Language version 2 được hỗ trợ.
- maximumErrors nằm trong range.
- target typescript có generator.
- packagePrefix phù hợp target.
- outputDirectory nằm trong vùng được phép.
- finance extension đã được cài và hỗ trợ API version cần thiết.

### 25.4 Apply

Compiler nhận snapshot bất biến. Generator được chọn theo target. Validator nhận cùng snapshot và cấu hình finance.

### 25.5 Reload

Nếu người dùng đổi maximumErrors, workbench có thể reload validation settings. Nếu đổi language.version hoặc target trong một build đang chạy, build hiện tại tiếp tục dùng snapshot cũ; build tiếp theo dùng snapshot mới.

### 25.6 Tái lập

Build metadata ghi schemaVersion, language version, target, generator version, extension version và configuration fingerprint. Secret không được ghi vào artifact.

## 26. Câu hỏi tự kiểm tra

1. Triển khai cấu hình trong DSL bao gồm những giai đoạn nào?
2. Phân biệt source DSL, tool configuration, project configuration và runtime configuration.
3. Vì sao nên dùng typed configuration model?
4. Những nguồn cấu hình phổ biến là gì?
5. Precedence và merge policy khác nhau như thế nào?
6. Object, list, null và delete được hợp nhất theo những cách nào?
7. Vì sao cần lưu provenance của effective value?
8. Parsing, binding và validation khác nhau ra sao?
9. Missing, null, empty và default cần được phân biệt như thế nào?
10. Cross-field validation dùng trong trường hợp nào?
11. Vì sao nên tạo immutable configuration snapshot?
12. Static và dynamic configuration khác nhau như thế nào?
13. Reload thất bại nên ảnh hưởng snapshot đang chạy ra sao?
14. Secret manager và redaction giúp bảo vệ credential như thế nào?
15. Configuration có thể tạo ra những rủi ro path traversal hoặc SSRF nào?
16. Schema version và migration giúp tương thích như thế nào?
17. Effective configuration fingerprint hỗ trợ tái lập build ra sao?
18. Cần những nhóm test nào cho configuration subsystem?

Triển khai cấu hình là xây dựng một hợp đồng rõ ràng giữa người vận hành, project và các thành phần của framework. Khi nguồn, kiểu, precedence, validation, secret, lifecycle và reload được quản lý nhất quán, DSL compiler, workbench và runtime có thể hoạt động dự đoán được, an toàn và dễ tái lập.
