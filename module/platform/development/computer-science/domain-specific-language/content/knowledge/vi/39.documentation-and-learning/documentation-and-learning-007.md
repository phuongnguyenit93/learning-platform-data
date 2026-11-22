# Tài liệu API công cụ

Một DSL (Domain-Specific Language) thường đi kèm một bộ công cụ để người dùng viết, kiểm tra, biên dịch, định dạng, chạy hoặc triển khai chương trình. Bộ công cụ đó có thể cung cấp command-line interface (CLI), thư viện lập trình, HTTP API, plugin interface, language server, compiler API và các định dạng cấu hình. Người dùng cần biết mỗi API làm gì, cách gọi, dữ liệu đầu vào, kết quả, lỗi có thể xảy ra và những giới hạn cần tuân thủ.

**Tài liệu API công cụ (tool API documentation)** là hệ thống tài liệu mô tả các interface mà công cụ DSL cung cấp cho người dùng hoặc cho những công cụ khác. Tài liệu tốt giúp người đọc tìm đúng API, hiểu semantics, sử dụng an toàn, xử lý lỗi và nâng cấp khi interface thay đổi.

Ví dụ một công cụ DSL có thể cung cấp CLI:

~~~text
dsl check project.dsl
dsl format --write project.dsl
dsl compile --target wasm project.dsl
dsl run --profile development project.dsl
~~~

Tài liệu API cần giải thích:

- Command nào có sẵn và mục đích của từng command.
- Argument và option nào bắt buộc hoặc tùy chọn.
- Giá trị mặc định, kiểu và tập giá trị hợp lệ.
- File hoặc resource nào được đọc hay ghi.
- Output, exit code và diagnostic format.
- Quyền cần thiết và side effect.
- Cách dùng trong script hoặc CI.
- Khả năng tương thích giữa các phiên bản.

Trong chương **Tài liệu và học tập**, tài liệu API công cụ là cầu nối giữa implementation và người sử dụng. Nó không chỉ liệt kê tên hàm hoặc cú pháp lệnh; nó mô tả hợp đồng có thể dựa vào khi tích hợp, tự động hóa và vận hành công cụ.

## 1. Tài liệu API công cụ là gì?

API là bề mặt giao tiếp mà một thành phần công bố cho bên sử dụng. Với DSL toolchain, API có thể là:

- CLI commands và flags.
- Public library functions, classes và types.
- HTTP endpoints.
- Compiler, parser và AST interfaces.
- Plugin hoặc extension points.
- Language Server Protocol capabilities.
- Build task API.
- Configuration schema.
- File format và artifact interface.

Tài liệu API công cụ mô tả những interface đó theo cách người dùng có thể tra cứu và áp dụng.

### 1.1. API documentation và user guide

Hai loại tài liệu có mục tiêu khác nhau:

| Loại tài liệu | Câu hỏi chính | Nội dung |
|---|---|---|
| API reference | Interface này nhận gì và làm gì? | Signature, option, type, response, error |
| User guide | Tôi nên dùng công cụ để hoàn thành việc gì? | Quy trình, ví dụ, best practice |
| Tutorial | Làm sao bắt đầu từng bước? | Bài thực hành có kết quả |
| Concept guide | Vì sao hệ thống hoạt động như vậy? | Mô hình, semantics, kiến trúc |
| Troubleshooting | Khi gặp lỗi thì xử lý ra sao? | Diagnostics, nguyên nhân, cách sửa |
| Release notes | Phiên bản thay đổi điều gì? | Feature, fix, deprecation, breaking change |

API reference nên chính xác và đầy đủ về interface. Tutorial có thể chọn một luồng phổ biến để người mới học nhanh. Hai loại tài liệu hỗ trợ nhau nhưng không thay thế nhau.

### 1.2. Tài liệu là một phần của API contract

Nếu CLI hứa exit code 2 khi source sai cú pháp, script có thể dựa vào quy tắc đó. Nếu thư viện hứa function trả về một type cụ thể, consumer có thể tích hợp theo type. Tài liệu vì thế là một phần của public contract.

### 1.3. Audience

Một công cụ DSL có thể phục vụ nhiều nhóm:

- Người viết DSL.
- Developer tích hợp CLI vào CI.
- Người xây plugin.
- Người phát triển compiler backend.
- Administrator vận hành dịch vụ.
- Team bảo mật hoặc platform.

Mỗi nhóm cần thông tin khác nhau. Tài liệu cần phân nhóm rõ thay vì đặt mọi API trong một danh sách khó tìm.

## 2. Mục tiêu của tài liệu API

Tài liệu API công cụ nên giúp người đọc:

1. Tìm đúng interface theo công việc cần làm.
2. Hiểu input, output và behavior.
3. Dùng API theo cách hợp lệ.
4. Dự đoán side effect và quyền cần thiết.
5. Xử lý lỗi mà không phải đọc implementation.
6. Tự động hóa công việc bằng script hoặc CI.
7. Xác định phiên bản và compatibility.
8. Biết khi nào cần chuyển sang API khác.

### 2.1. Discoverability

Tên API, command group và navigation cần phản ánh domain. Người dùng không nên phải biết tên class nội bộ mới tìm được thao tác phổ biến.

### 2.2. Accuracy

Mọi signature, option, default và output phải khớp với phiên bản tool đang phát hành. Tài liệu sai có thể gây lỗi tích hợp dù implementation hoạt động đúng.

### 2.3. Completeness

Không chỉ mô tả happy path. Cần nêu input không hợp lệ, lỗi, permission, timeout, output format và giới hạn quan trọng.

### 2.4. Actionability

Ví dụ cần chạy được hoặc có thể chuyển thành ví dụ chạy được. Người đọc cần biết command thực hiện ở thư mục nào, file nào được tạo và kết quả mong đợi.

### 2.5. Maintainability

Tài liệu nên được quản lý cùng source hoặc API schema, có version và có kiểm tra tự động để giảm drift.

## 3. Phân loại API trong một DSL toolchain

Một toolchain DSL có thể công bố nhiều lớp API.

~~~mermaid
flowchart TD
    U[Tool users] --> C[CLI API]
    U --> L[Library API]
    A[Automation] --> H[HTTP API]
    P[Plugin developers] --> X[Extension API]
    E[Editors] --> S[Language Server API]
    C --> T[Compiler and runtime]
    L --> T
    H --> T
    X --> T
    S --> T
~~~

### 3.1. CLI API

CLI API gồm command, subcommand, positional argument, flag, environment variable, config file và exit code.

### 3.2. Library API

Library API gồm package, public type, function, constructor, exception, callback và lifecycle.

### 3.3. HTTP API

HTTP API gồm endpoint, method, request/response schema, authentication, status code, pagination và rate limit.

### 3.4. Compiler API

Compiler API có thể cung cấp parse, analyze, compile, emit, diagnostics, AST visitor hoặc intermediate representation.

### 3.5. Plugin API

Plugin API mô tả cách đăng ký extension, lifecycle callback, capability, compatibility version và sandbox boundary.

### 3.6. Editor và language server API

Language server có thể hỗ trợ completion, hover, definition, references, diagnostics, formatting, rename và semantic tokens. Tài liệu cần nêu capability, request/response và behavior khi source chưa hoàn chỉnh.

### 3.7. Configuration API

Configuration API mô tả file cấu hình, schema, environment variable, default, precedence và migration.

## 4. Kiến trúc thông tin của bộ tài liệu

Một bộ tài liệu dễ dùng thường có các phần:

~~~text
docs/
    getting-started/
    concepts/
    tutorials/
    guides/
    reference/
        cli/
        library/
        http/
        compiler/
        plugins/
        configuration/
    examples/
    troubleshooting/
    migration/
    release-notes/
~~~

### 4.1. Getting started

Giải thích cài đặt, yêu cầu môi trường và thao tác đầu tiên. Không nên bắt người mới đọc toàn bộ API reference trước khi chạy được một ví dụ.

### 4.2. Concepts

Giải thích các khái niệm nền tảng như project, module, workspace, profile, target, artifact, compiler phase và execution context.

### 4.3. Guides

Hướng dẫn theo nhiệm vụ: kiểm tra project, tích hợp CI, tạo plugin, viết custom backend hoặc cấu hình language server.

### 4.4. Reference

Reference tổ chức theo từng API family và có trang riêng cho từng command, type hoặc operation.

### 4.5. Examples

Ví dụ nhỏ và project mẫu giúp người đọc áp dụng interface vào tình huống cụ thể.

### 4.6. Troubleshooting

Giải thích error code, nguyên nhân phổ biến và cách xử lý.

### 4.7. Migration và release notes

Mô tả thay đổi giữa phiên bản, deprecation timeline và bước nâng cấp.

## 5. Cấu trúc chuẩn của một trang API reference

Một trang API reference nên có cấu trúc nhất quán để người đọc biết vị trí cần tìm.

Các phần thường gồm:

1. Tên API và mục đích.
2. Availability và version.
3. Signature hoặc command syntax.
4. Parameters, options và types.
5. Defaults và constraints.
6. Return value hoặc output.
7. Side effects và permissions.
8. Errors và diagnostics.
9. Examples.
10. Compatibility notes.
11. Related APIs.

Ví dụ trang command:

~~~text
Command: dsl check

Purpose:
    Parse and validate DSL source without applying changes.

Syntax:
    dsl check [OPTIONS] <FILE...>

Arguments:
    FILE    One or more source files.

Options:
    --format <text|json>
    --strict
    --config <PATH>

Exit codes:
    0  Validation succeeded.
    1  Validation errors were found.
    2  Invocation or configuration error.
~~~

Đây là ví dụ minh họa. Tài liệu thực tế phải phản ánh command implementation.

### 5.1. Purpose

Nêu command hoặc function giải quyết công việc gì. Tránh chỉ lặp lại tên API bằng một câu chung chung.

### 5.2. Availability

Ghi rõ package, edition, platform, feature flag hoặc version cần thiết nếu API không có ở mọi bản cài đặt.

### 5.3. Signature

Hiển thị cú pháp đầy đủ, bao gồm optional argument, generic type hoặc callback khi có.

### 5.4. Parameter table

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| FILE | Path | Yes | — | Source file |
| --format | Enum | No | text | Output format |
| --strict | Boolean | No | false | Enable strict validation |

### 5.5. Return value

Với library API, mô tả return type, nullability, ownership, mutability và exception. Với CLI, mô tả stdout, stderr, output file và exit code.

### 5.6. Side effects

Nêu rõ API có tạo file, ghi cache, gọi network, sửa resource hoặc thay đổi state không.

### 5.7. Related APIs

Liên kết tới API liên quan như check, format, compile, run và diagnostics.

## 6. Tài liệu CLI

CLI thường là interface đầu tiên người dùng tiếp xúc với DSL toolchain. Tài liệu CLI cần giúp cả người dùng tương tác và script tự động hóa.

### 6.1. Command hierarchy

Ví dụ:

~~~text
dsl
  init
  check
  format
  compile
  run
  test
  plugin
  config
~~~

Mỗi command nên có trang reference riêng, ngoài trang tổng quan liệt kê nhóm lệnh.

### 6.2. Positional arguments

Mô tả thứ tự, số lượng, glob behavior và cách xử lý path tương đối.

### 6.3. Options và flags

Với mỗi option, nêu:

- Tên ngắn và tên dài.
- Kiểu dữ liệu.
- Required hay optional.
- Default.
- Có thể lặp lại hay không.
- Có xung đột với option nào không.
- Environment variable thay thế nếu có.

### 6.4. Option precedence

Nếu CLI đọc config file, environment variables và command-line flags, cần mô tả thứ tự ưu tiên. Ví dụ flag tường minh có thể ghi đè environment variable, nhưng phải nêu đúng theo implementation.

### 6.5. Working directory

Giải thích path được resolve tương đối với current working directory, project root hay file cấu hình.

### 6.6. Exit codes

Exit code là contract quan trọng với shell script và CI. Cần mô tả mã thành công, validation failure, invocation error, cancellation và internal failure.

### 6.7. stdout và stderr

Nêu dữ liệu máy đọc được đi đâu. Ví dụ JSON output nên nằm trên stdout, diagnostics hoặc progress có thể nằm trên stderr. Không để progress text phá JSON stream nếu API cam kết output JSON.

### 6.8. Shell completion

Nếu CLI hỗ trợ completion, tài liệu có thể hướng dẫn cài đặt cho PowerShell, Bash hoặc Zsh và mô tả giới hạn.

## 7. Tài liệu library API

Library API được dùng từ code nên cần mô tả type và behavior chính xác.

Ví dụ signature:

~~~typescript
parseSource(
  source: string,
  options?: ParseOptions
): ParseResult
~~~

### 7.1. Package và import

Nêu package name, version, module path và câu lệnh cài đặt. Nếu có nhiều package như core, compiler và plugin SDK, giải thích trách nhiệm từng package.

### 7.2. Public types

Mô tả field, constructor, enum variant, generic parameter và mutability. Phân biệt public type với internal implementation type.

### 7.3. Lifecycle

Một compiler object có thể cần initialize, compile nhiều lần, close hoặc dispose. Tài liệu cần nêu object có thread-safe không và có thể tái sử dụng giữa request không.

### 7.4. Exceptions và result types

Nêu API báo lỗi bằng exception, result object, callback hay diagnostic collection. Cần mô tả lỗi nào được ném và lỗi nào được trả trong result.

### 7.5. Ownership và resource cleanup

Nếu API trả stream, file handle hoặc native resource, tài liệu cần giải thích ai chịu trách nhiệm đóng và thời điểm đóng.

### 7.6. Thread safety

Ghi rõ object có thể được gọi đồng thời hay không. Không để người dùng suy đoán từ implementation.

## 8. Tài liệu HTTP API

HTTP API reference thường dựa trên OpenAPI hoặc schema tương đương.

Một operation cần mô tả:

- HTTP method và path.
- Path, query và header parameters.
- Request body.
- Authentication và authorization.
- Success response.
- Error response.
- Pagination.
- Rate limit.
- Idempotency.
- Timeout và retry expectation.

Ví dụ:

~~~yaml
paths:
  /projects/{projectId}/validate:
    post:
      summary: Validate a DSL project
      parameters:
        - name: projectId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Validation completed
        "400":
          description: Invalid request
        "401":
          description: Authentication required
        "429":
          description: Rate limit exceeded
~~~

### 8.1. Authentication

Nêu cách cấp token, scope cần thiết, expiry và cách refresh nếu có. Không đưa secret thật vào ví dụ.

### 8.2. Authorization

Mô tả role hoặc permission cần cho operation. Authentication thành công không có nghĩa caller được phép truy cập mọi project.

### 8.3. Pagination

Nêu page size tối đa, cursor format, ordering guarantee và behavior khi cursor hết hạn.

### 8.4. Rate limit

Mô tả scope của quota, response khi vượt giới hạn và header Retry-After nếu có.

### 8.5. Idempotency

Với operation tạo resource hoặc thực hiện action, mô tả idempotency key, phạm vi và thời gian lưu key.

### 8.6. API version

Nêu cách chọn version, thời gian hỗ trợ và quy tắc deprecation.

## 9. Tài liệu compiler và parser API

Compiler API có thể cung cấp những bước xử lý source DSL cho ứng dụng khác.

Ví dụ:

~~~java
ParseResult parse(SourceText source, ParseOptions options);
AnalysisResult analyze(AstNode ast, AnalysisOptions options);
CompilationResult compile(SourceText source, CompileOptions options);
~~~

### 9.1. Input model

Mô tả SourceText, file identity, language version, encoding và include resolver.

### 9.2. Parse result

Nêu AST, diagnostics, partial tree, success state và source map.

### 9.3. Analysis result

Mô tả symbol table, type information, dependency graph và semantic diagnostics nếu được public.

### 9.4. Compile result

Nêu generated artifact, metadata, warnings và failure modes.

### 9.5. Incremental compilation

Nếu API hỗ trợ incremental parse hoặc compile, mô tả cache lifetime, invalidation, edit range và concurrency.

### 9.6. Cancellation và resource limits

Nêu deadline, cancellation token, source size limit, AST limit và behavior khi vượt budget. Người dùng cần biết API có thể trả ResourceLimitExceeded hay timeout result.

### 9.7. Version compatibility

Nếu AST hoặc IR được expose, nêu language version và compiler API version. Không giả định serialized AST có thể đọc giữa mọi phiên bản.

## 10. Tài liệu plugin và extension API

Plugin API cho phép mở rộng compiler, editor, generator hoặc runtime. Tài liệu cần mô tả cả capability và giới hạn bảo mật.

Ví dụ interface:

~~~typescript
interface DslPlugin {
  name: string;
  apiVersion: string;
  initialize(context: PluginContext): void;
  analyze(module: ModuleNode): Diagnostic[];
}
~~~

### 10.1. Plugin lifecycle

Mô tả load, initialize, callback, shutdown và error handling.

### 10.2. Registration

Giải thích cách đăng ký command, function, rule, parser extension hoặc backend.

### 10.3. Context

Nêu dữ liệu và service được cung cấp cho plugin, ví dụ logger, source manager hoặc artifact writer.

### 10.4. Capability

Mô tả plugin được phép đọc file, network, environment variable hoặc ghi output tới đâu.

### 10.5. Compatibility

Nêu plugin API version, supported compiler range và behavior khi version không tương thích.

### 10.6. Resource limits

Ghi rõ timeout, memory, CPU, output và concurrency limit. Nếu plugin chạy trong sandbox, tài liệu cần mô tả capability được expose.

### 10.7. Error isolation

Mô tả plugin exception ảnh hưởng tới toàn compilation hay chỉ plugin đó, và diagnostics nào được phát ra.

## 11. Tài liệu language server và editor integration

Language Server Protocol (LSP) giúp editor giao tiếp với DSL tooling. Tài liệu nên mô tả cách cài đặt server, capabilities và behavior.

Các tính năng thường gặp:

- Diagnostics.
- Completion.
- Hover.
- Go to definition.
- Find references.
- Rename.
- Document symbols.
- Formatting.
- Semantic tokens.
- Code actions.

### 11.1. Capabilities

Nêu tính năng được hỗ trợ và phiên bản protocol. Có thể phân biệt static capability với dynamic registration.

### 11.2. File và workspace support

Giải thích file extension, URI scheme, multi-root workspace và cách server resolve module.

### 11.3. Partial source

Editor thường gửi source chưa hoàn chỉnh. Tài liệu cần nói rõ parser có hỗ trợ partial AST, diagnostics liên tục và cancellation không.

### 11.4. Configuration

Mô tả editor settings, project config và precedence.

### 11.5. Troubleshooting

Hướng dẫn xem log, kiểm tra executable path, protocol version và workspace root khi language server không khởi động.

## 12. Tài liệu configuration API

Tool configuration cũng là một API. Người dùng cần biết key, type, default, scope và precedence.

Ví dụ:

~~~yaml
compiler:
  languageVersion: "2"
  strict: true
  diagnostics:
    format: "json"
  cache:
    enabled: true
    directory: ".dsl-cache"
~~~

### 12.1. Schema

Mỗi key cần có:

- Name.
- Type.
- Required/optional.
- Default.
- Valid values hoặc range.
- Description.
- Scope.
- Introduced version.
- Deprecated version nếu có.

### 12.2. Precedence

Nếu configuration đến từ file, environment variable, CLI và API options, nêu rõ nguồn nào có ưu tiên.

### 12.3. Unknown key

Tool có thể từ chối unknown key hoặc phát warning. Hành vi này cần được tài liệu hóa để typo không bị bỏ qua âm thầm.

### 12.4. Secret configuration

Nêu cách tham chiếu secret provider và cách redaction. Không khuyến khích ghi credential trực tiếp vào file config.

### 12.5. Migration

Khi key đổi tên hoặc semantics thay đổi, cung cấp migration guidance và thời gian deprecation.

## 13. Mô tả kiểu dữ liệu và schema

Tài liệu API phải giải thích kiểu dữ liệu theo semantics của DSL, không chỉ tên kiểu.

Ví dụ:

| Type | Ý nghĩa | Ví dụ |
|---|---|---|
| String | Văn bản Unicode | "staging" |
| Boolean | Giá trị đúng/sai | true |
| Integer | Số nguyên | 3 |
| Decimal | Số thập phân | 12.50 |
| Duration | Khoảng thời gian | 30s |
| ByteSize | Dung lượng | 512Mi |
| Path | Đường dẫn | ./src |
| Enum | Giá trị trong tập xác định | "strict" |
| Reference | Tham chiếu declaration | network.backend |
| Optional<T> | Có thể không có giá trị | null hoặc absent theo contract |

### 13.1. Units

Duration và byte size cần nêu đơn vị, cách chuyển đổi và precision. Ví dụ MB và MiB không giống nhau.

### 13.2. Nullability

Phân biệt field absent, null và empty. Đây là thông tin quan trọng cho serializer và consumer.

### 13.3. Enum

Liệt kê giá trị hợp lệ và behavior khi gặp giá trị mới. Nêu case sensitivity.

### 13.4. Reference

Giải thích cách resolve, scope, namespace và lỗi khi target không tồn tại.

### 13.5. Collection

Mô tả thứ tự list, uniqueness, map key type và maximum size nếu có.

## 14. Tài liệu diagnostics và error codes

Tool DSL thường phát diagnostics khi source sai, configuration thiếu hoặc operation thất bại.

Ví dụ:

~~~text
error DSL101: Unknown attribute 'repilcas'.
  --> services/api.dsl:4:5
  |
4 |     repilcas = 3
  |     ^^^^^^^^
  |
  = help: Did you mean 'replicas'?
~~~

### 14.1. Diagnostic structure

Mô tả:

- Code.
- Severity.
- Message.
- Primary source range.
- Related locations.
- Help hoặc suggestion.
- Documentation link.

### 14.2. Error categories

Phân biệt:

- Invocation error.
- Lexical/syntax error.
- Semantic/type error.
- Configuration error.
- Permission error.
- Resource limit.
- Network/dependency error.
- Internal failure.

### 14.3. Machine-readable output

Nếu CLI hỗ trợ JSON hoặc SARIF, tài liệu cần mô tả schema và version. Script nên dựa vào code hoặc field ổn định thay vì parse human-readable text.

### 14.4. Exit code mapping

Nêu cách diagnostics ảnh hưởng exit code. Ví dụ warning có làm command fail trong strict mode hay không.

### 14.5. Privacy

Diagnostics không nên tiết lộ secret, nội dung file nhạy cảm hoặc path nội bộ ngoài phạm vi cần thiết.

## 15. Ví dụ và code samples

Ví dụ là phần quan trọng của API documentation. Người dùng thường hiểu interface nhanh hơn khi thấy một lời gọi hoàn chỉnh cùng output.

### 15.1. Minimal example

Ví dụ nhỏ nhất nên thể hiện một chức năng:

~~~text
dsl check service.dsl
~~~

### 15.2. Complete example

Ví dụ đầy đủ nên có:

- Source hoặc input.
- Command/API call.
- Output mong đợi.
- File được tạo nếu có.
- Cách xác nhận thành công.

### 15.3. Copyable examples

Code sample nên có thể copy và chạy với ít chỉnh sửa. Dùng placeholder rõ cho token hoặc endpoint và không nhúng secret thật.

### 15.4. Expected output

Nêu phần output ổn định. Nếu output chứa timestamp hoặc random ID, đánh dấu những phần thay đổi.

### 15.5. Error example

Ví dụ lỗi giúp người dùng hiểu cách tool phản hồi và cách xử lý. Cần bao gồm cả invalid input và permission failure nếu phù hợp.

### 15.6. Multi-language samples

Nếu library API hỗ trợ Java, Kotlin, TypeScript hoặc Python, cung cấp ví dụ theo ngôn ngữ được hỗ trợ. Không copy cùng code nhưng khác cú pháp mà chưa chạy kiểm tra.

### 15.7. Example versioning

Gắn ví dụ với tool version hoặc language version. Ví dụ cũ cần được cập nhật hoặc đánh dấu rõ.

## 16. Tutorials, guides và reference phối hợp

Một người mới thường cần tutorial trước khi đọc reference chi tiết.

### 16.1. Tutorial

Tutorial dẫn người học qua một mục tiêu hoàn chỉnh, ví dụ tạo project, viết DSL, chạy check và compile.

### 16.2. Task-oriented guide

Guide giải quyết một nhiệm vụ cụ thể như tích hợp CLI vào CI hoặc tạo plugin. Nó nên dẫn link tới reference cho từng API.

### 16.3. Reference

Reference trả lời câu hỏi chính xác về signature, option, type và behavior. Nó nên ngắn gọn, có cấu trúc và đầy đủ.

### 16.4. Concept guide

Concept guide giải thích mô hình phía sau API. Ví dụ resource lifecycle hoặc compiler phases giúp người dùng hiểu vì sao API có các option đó.

### 16.5. Link giữa các loại tài liệu

Một trang API nên liên kết tới:

- Tutorial đầu tiên dùng API.
- Guide cho use case phổ biến.
- Concept giải thích semantics.
- Troubleshooting cho lỗi thường gặp.
- Migration guide cho version.

## 17. Tài liệu API được sinh tự động

Một phần API documentation có thể được sinh từ source hoặc schema.

Nguồn sinh:

- Doc comments trong source code.
- Type metadata.
- OpenAPI/AsyncAPI.
- JSON Schema.
- CLI command definitions.
- Plugin manifest.
- Grammar hoặc compiler metadata.

### 17.1. Ưu điểm

- Giảm sai lệch signature.
- Cập nhật khi API thay đổi.
- Tạo navigation nhất quán.
- Có thể sinh nhiều format.
- Tích hợp vào CI.

### 17.2. Giới hạn

Generated reference thường biết type và description nhưng không tự giải thích đầy đủ behavior, trade-off, side effect hoặc use case. Cần nội dung biên tập bổ sung.

### 17.3. Single source of truth

Nếu API được định nghĩa bằng schema, hãy ưu tiên sinh reference từ schema đó. Tránh duy trì hai nguồn thủ công có thể lệch nhau.

### 17.4. Generated docs review

Khi source API thay đổi, CI có thể sinh docs và kiểm tra diff. Reviewer cần xem nội dung public API thay đổi có được mô tả rõ không.

### 17.5. Versioned output

Tài liệu được sinh cần gắn đúng package/tool version. Không để trang latest mô tả API khác với binary mà người dùng đang chạy.

## 18. Doc comments và naming

Doc comment đặt gần declaration có thể làm nguồn cho reference.

Ví dụ:

~~~java
/**
 * Parses a complete DSL source document.
 *
 * @param source source text encoded as Unicode
 * @param options parser options and language version
 * @return parse tree and diagnostics
 */
ParseResult parse(SourceText source, ParseOptions options);
~~~

### 18.1. Viết theo behavior

Mô tả function thực sự làm gì, không chỉ lặp tên. Ví dụ “Parses a complete source document and returns syntax diagnostics” hữu ích hơn “Parse source”.

### 18.2. Naming consistency

Tên trong tài liệu phải khớp API. Nếu API dùng projectRoot, không gọi nó là workspacePath ở một trang khác nếu hai khái niệm khác nhau.

### 18.3. Terminology

Xây glossary cho những thuật ngữ như module, workspace, target, artifact, profile và environment. Dùng nhất quán giữa tutorial, reference và diagnostics.

### 18.4. Description của parameter

Nêu semantics, valid range, default và tác động. Với boolean option, nói rõ behavior khi true và false.

### 18.5. Deprecation annotation

Nếu API bị deprecated, ghi replacement, version bắt đầu deprecation và thời điểm dự kiến removal nếu đã được quyết định.

## 19. Versioning và compatibility của API

Tool API thay đổi theo thời gian. Tài liệu cần cho biết interface nào thuộc phiên bản nào và cách xử lý thay đổi.

### 19.1. API version

Version có thể theo package semver, CLI major version, HTTP path version, plugin API version hoặc DSL language version. Những version này không nhất thiết trùng nhau.

### 19.2. Compatibility matrix

Một bảng có thể cho biết:

| Tool version | Language version | Plugin API | Status |
|---|---|---|---|
| 3.x | 1, 2 | 2 | Supported |
| 4.x | 2, 3 | 3 | Current |
| 2.x | 1 | 1 | End of support |

Đây là ví dụ; cần dùng version thật của sản phẩm.

### 19.3. Breaking change

Breaking change có thể gồm:

- Xóa command hoặc option.
- Đổi default.
- Đổi exit code.
- Đổi field type hoặc nullability.
- Đổi diagnostic code.
- Thay đổi plugin lifecycle.
- Thay đổi AST node hoặc serialized format.

### 19.4. Deprecation

Thông báo deprecation cần có:

- API cũ.
- Replacement.
- Lý do.
- Phiên bản bắt đầu deprecated.
- Thời gian hỗ trợ.
- Cách migration.

### 19.5. Migration guide

Migration guide nên đưa ví dụ before/after và nêu behavior khác biệt, không chỉ liệt kê tên option đổi.

### 19.6. Changelog

Release notes cần phân loại Added, Changed, Fixed, Deprecated và Removed. Chỉ liệt kê thay đổi có ảnh hưởng tới người dùng hoặc consumer API.

## 20. Tài liệu bảo mật và resource behavior

API công cụ có thể đọc file, gọi network, chạy plugin, tạo artifact hoặc deploy resource. Tài liệu cần nêu quyền và giới hạn quan trọng.

Các thông tin cần có:

- Quyền filesystem.
- Network access.
- Authentication và authorization.
- Secret handling.
- Sandbox behavior.
- CPU, memory và timeout limit.
- Request size và rate limit.
- Output size.
- Audit behavior.
- Side effect và destructive operation.

### 20.1. Security-sensitive option

Option như allow-network, execute-plugin hoặc apply-to-production cần mô tả rõ tác động và default. Không đặt tên mơ hồ khiến người dùng không hiểu quyền được mở.

### 20.2. Least privilege

Hướng dẫn chạy tool bằng identity có quyền tối thiểu. Không dùng admin credential trong ví dụ chỉ để command chạy được.

### 20.3. Secret

Nêu cách cung cấp secret qua secret manager hoặc environment injection phù hợp. Cảnh báo không log token hoặc commit secret vào repository.

### 20.4. Resource limits

Tài liệu cần công bố giới hạn có ảnh hưởng tới người dùng, cách nhận biết khi vượt ngưỡng và behavior của retry hoặc cancellation.

### 20.5. Destructive API

Command xóa hoặc thay thế resource cần nêu target, phạm vi, side effect và cơ chế xác nhận.

## 21. Tài liệu error handling và troubleshooting

Một API reference tốt mô tả lỗi có thể xảy ra; troubleshooting giúp người dùng khắc phục.

Ví dụ:

~~~text
Error: DSL_CONFIG_NOT_FOUND

Cause:
The tool could not locate a project configuration file.

Check:
1. Confirm the current working directory.
2. Pass --config with an explicit path.
3. Verify the file is readable.
~~~

### 21.1. Stable error codes

Error code nên ổn định hơn message text. Script và monitoring nên dựa vào code hoặc structured field.

### 21.2. Cause và remedy

Nêu nguyên nhân phổ biến và bước kiểm tra. Không khẳng định một nguyên nhân duy nhất nếu có nhiều khả năng.

### 21.3. Diagnostics links

Diagnostic có thể chứa URL tới trang tài liệu chi tiết. Link cần version-aware nếu semantics thay đổi.

### 21.4. Debug mode

Giải thích debug hoặc verbose mode tạo thêm thông tin gì và có thể tiết lộ path hoặc dữ liệu nhạy cảm hay không.

### 21.5. Support bundle

Nếu tool có thể tạo support bundle, tài liệu cần nêu file nào được thu thập, cách redact và cách kiểm tra trước khi chia sẻ.

## 22. Accessibility, search và navigation

Tài liệu API thường dài và được tra cứu nhanh. Navigation và accessibility ảnh hưởng trực tiếp tới khả năng tìm thông tin.

### 22.1. Search

Search nên hỗ trợ tên command, class, error code, option, synonym và thuật ngữ domain.

### 22.2. Navigation

Menu nên phản ánh API hierarchy. Breadcrumb giúp người đọc biết đang ở CLI, compiler hay plugin reference.

### 22.3. Anchors

Mỗi command, type và parameter quan trọng nên có anchor ổn định để liên kết từ issue, code review hoặc diagnostic.

### 22.4. Tables

Bảng parameter nên có header rõ, không dựa vào màu sắc để truyền ý nghĩa. Trên màn hình nhỏ, bảng cần có cách cuộn hoặc trình bày thay thế.

### 22.5. Code blocks

Gắn language tag cho syntax highlighting. Đảm bảo code sample có thể đọc bằng screen reader và không dùng màu làm thông tin duy nhất.

### 22.6. Language

Dùng câu ngắn, thuật ngữ nhất quán và giải thích acronym ở lần đầu. Nếu tài liệu đa ngôn ngữ, cần quản lý version để bản dịch không mô tả API cũ.

## 23. Tổ chức examples và sample projects

Một sample project có thể minh họa cách dùng nhiều API kết hợp.

Cấu trúc ví dụ:

~~~text
examples/
    hello-dsl/
    custom-validator/
    cli-ci-integration/
    compiler-library/
    language-server/
    plugin-extension/
~~~

### 23.1. Example README

Mỗi example nên có:

- Mục tiêu.
- Yêu cầu cài đặt.
- Cách chạy.
- Output mong đợi.
- Cách reset hoặc cleanup.
- Version được hỗ trợ.

### 23.2. Không chứa secret

Dùng placeholder và hướng dẫn tạo credential test. Không commit token thật.

### 23.3. Small example và full example

Small example giúp học một API. Full sample thể hiện cách kết hợp nhiều API trong project gần thực tế.

### 23.4. Example maintenance

Sample cần được build/test định kỳ. Ví dụ cũ không còn chạy nên được sửa hoặc đánh dấu version, không để người học sao chép code lỗi thời.

## 24. Docs as code

Docs as code là cách quản lý tài liệu bằng quy trình gần với source code:

- Lưu trong version control.
- Review qua pull request.
- Có owner.
- Chạy lint và link check.
- Test code samples.
- Build preview.
- Publish theo release.

### 24.1. Lợi ích

Tài liệu thay đổi cùng API, có lịch sử và có thể review. Developer có thể sửa docs ngay trong pull request thay vì tạo ticket rời.

### 24.2. Docs versioning

Mỗi major tool release có thể có bộ docs tương ứng. Người dùng cần tìm được tài liệu đúng với version đã cài.

### 24.3. Documentation preview

Pull request có thể tạo preview để reviewer xem navigation, code block, link và rendered page.

### 24.4. Ownership

API owner chịu trách nhiệm nội dung reference; documentation team hoặc technical writer có thể hỗ trợ cấu trúc, ngôn ngữ và trải nghiệm.

## 25. Tự động kiểm tra tài liệu

Tài liệu API cần có các kiểm tra tự động để giảm drift.

Các loại check:

- Markdown lint.
- Link checker.
- Code block syntax check.
- Example build/test.
- API schema validation.
- Generated docs diff.
- CLI help snapshot.
- Signature consistency.
- Spelling và terminology.
- Version metadata.

### 25.1. CLI help consistency

Có thể so sánh output help của CLI với reference hoặc sinh reference từ cùng command definition. Nếu help thay đổi, CI có thể yêu cầu cập nhật docs.

### 25.2. OpenAPI validation

Validate OpenAPI document theo specification và kiểm tra generated client/server.

### 25.3. Example tests

Chạy command hoặc compile sample trong CI với fixture. Dùng temporary directory để không sửa workspace người dùng.

### 25.4. Link checking

Kiểm tra internal link và anchor. External link có thể tạm unavailable nên cần retry hoặc policy riêng.

### 25.5. Generated reference

Generate API docs từ source/schema và phát hiện diff không được review.

### 25.6. Không để lint quyết định chất lượng nội dung

Lint phát hiện format, link hoặc một số vấn đề kỹ thuật. Reviewer vẫn cần đánh giá tính đúng, rõ ràng và đầy đủ của giải thích.

## 26. Quy trình viết một trang API

Một quy trình hữu ích:

1. Xác định audience và use case.
2. Xác định public contract và version.
3. Đọc source hoặc schema chính thức.
4. Liệt kê signature, parameter, type và default.
5. Xác minh output, side effect và error behavior.
6. Viết purpose và syntax.
7. Thêm parameter/return tables.
8. Thêm example tối thiểu và output.
9. Thêm security/resource/permission notes.
10. Liên kết guide, concept và troubleshooting.
11. Chạy example và validation tool.
12. Review với API owner.
13. Publish theo đúng version.

### 26.1. Bắt đầu từ câu hỏi người dùng

Người dùng thường tìm tài liệu bằng câu hỏi như “làm sao validate project?”, “option nào đổi output sang JSON?” hoặc “vì sao plugin không load?”. Cấu trúc trang nên trả lời trực tiếp các câu hỏi đó.

### 26.2. Phân biệt fact và recommendation

Nêu rõ phần nào là behavior được bảo đảm, phần nào là recommendation hoặc best practice. Không biến một cách dùng phổ biến thành guarantee của API.

### 26.3. Xác minh với implementation

Kiểm tra default, exit code và side effect bằng implementation hoặc executable contract. Không suy luận từ tên option.

### 26.4. Review chuyên môn

API owner xác nhận semantics; technical writer kiểm tra tính rõ ràng, cấu trúc và discoverability.

## 27. Quản lý thay đổi tài liệu khi API thay đổi

Khi API thay đổi, tài liệu liên quan cần được cập nhật cùng change.

Một pull request có thể bao gồm:

- Source/API schema change.
- Tests.
- Generated reference.
- Updated examples.
- Migration notes.
- Release note.

### 27.1. Additive change

Thêm command hoặc optional parameter cần bổ sung reference và ví dụ.

### 27.2. Default change

Đổi default có thể ảnh hưởng script hiện có. Cần ghi rõ behavior cũ/mới và migration recommendation.

### 27.3. Removal

Khi xóa API, giữ trang deprecation hoặc redirect tới replacement trong thời gian phù hợp. Không để link cũ dẫn tới trang trống.

### 27.4. Documentation version skew

Docs latest có thể mô tả API chưa có trong bản tool người dùng đang chạy. Hiển thị version selector hoặc banner compatibility.

### 27.5. Changelog và migration guide

Changelog tóm tắt thay đổi; migration guide giải thích cách chuyển đổi. Hai trang có mục đích khác nhau.

## 28. Metrics cho chất lượng tài liệu

Có thể dùng tín hiệu định lượng để tìm phần docs khó hiểu:

- Search query không có kết quả.
- Search result không được click.
- Page exit sau một error search.
- Feedback hữu ích/không hữu ích.
- Link tới trang troubleshooting.
- Tỷ lệ sample chạy thành công.
- Issue hoặc support ticket lặp lại.
- API adoption và deprecation usage.

### 28.1. Không tối ưu chỉ theo page view

Trang được xem nhiều có thể là trang lỗi thường gặp hoặc navigation khó hiểu. Page view không tự chứng minh tài liệu tốt.

### 28.2. Feedback loop

Kết hợp search analytics, support issue, developer interview và API usage để ưu tiên cập nhật.

### 28.3. Privacy

Analytics cần hạn chế thu thập dữ liệu cá nhân, token hoặc nội dung source DSL. Không log search query chứa secret hoặc code riêng tư nếu không cần.

## 29. Các lỗi thường gặp trong tài liệu API công cụ

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ liệt kê tên function | Người đọc không hiểu behavior | Mô tả purpose, input, output và errors |
| Không ghi default | Người dùng dựa vào giả định sai | Nêu default và precedence |
| Không mô tả side effect | Script có thể sửa file hoặc resource ngoài dự kiến | Ghi rõ đọc/ghi/network/deploy behavior |
| Không có exit code | CI khó xử lý kết quả | Công bố exit code ổn định |
| Reference và tutorial trộn lẫn | Khó tra cứu nhanh | Tách reference, guide và tutorial |
| Ví dụ không chạy được | Người học mất thời gian sửa ví dụ | Test sample trong CI |
| Ví dụ chứa secret | Credential có thể bị lộ | Dùng placeholder và secret manager |
| Docs không versioned | Người dùng đọc sai API version | Publish docs theo release |
| Không có error examples | Khó xử lý lỗi thực tế | Mô tả error code và remediation |
| Không có permission notes | Tích hợp thất bại hoặc cấp quyền quá rộng | Ghi auth, role và capability |
| Generated docs không review | Nội dung máy sinh có thể khó hiểu | Kết hợp generation và biên tập |
| Copy API signature thủ công | Dễ drift khỏi source | Generate từ schema/source |
| Link hỏng | Người dùng không tìm được thông tin liên quan | Link check trong CI |
| Không có migration guide | Nâng cấp khó và rủi ro | Before/after và compatibility notes |
| Tên gọi không nhất quán | Người đọc hiểu sai domain | Glossary và terminology review |
| Không nêu resource limits | Script có thể vượt quota | Công bố limits và exceed behavior |

## 30. Ví dụ tổng hợp: tài liệu CLI của DSL tool

Giả sử tool có command:

~~~text
dsl compile <PROJECT>
    --target <TARGET>
    --output <DIR>
    --profile <PROFILE>
    --format <text|json>
~~~

Một trang reference có thể viết:

### Purpose

Compile một project DSL thành artifact cho target được chọn. Command chỉ tạo output trong thư mục chỉ định và không triển khai artifact lên môi trường đích.

### Syntax

~~~text
dsl compile <PROJECT> [OPTIONS]
~~~

### Arguments

| Argument | Type | Required | Description |
|---|---|---|---|
| PROJECT | Path | Yes | Project directory hoặc manifest |

### Options

| Option | Type | Default | Description |
|---|---|---|---|
| --target | Enum | Tool default | Target backend |
| --output | Path | build/output | Output directory |
| --profile | String | default | Configuration profile |
| --format | Enum | text | Diagnostic output format |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Compilation succeeded |
| 1 | Source or semantic errors |
| 2 | Invalid invocation or configuration |
| 3 | Resource limit or timeout |
| 4 | Internal tool failure |

### Example

~~~text
dsl compile ./orders \
    --target wasm \
    --profile production \
    --output ./dist
~~~

Expected result:

~~~text
Compilation succeeded.
Artifact: ./dist/orders.wasm
Diagnostics: 0 errors, 1 warning
~~~

### Side effects and permissions

Command đọc project source, configuration và dependency được phép. Nó ghi artifact vào output directory. Nếu backend cần tải dependency, network access phải được cấu hình theo policy. Command không thay đổi deployment environment.

### Errors

- Project manifest không tồn tại.
- Target không được hỗ trợ.
- Dependency không resolve được.
- Source có syntax hoặc semantic error.
- Output directory không ghi được.
- Resource budget bị vượt.

Ví dụ này cho thấy một trang API tốt kết hợp cú pháp, parameter, default, output, exit code, side effect và lỗi.

## 31. Checklist review tài liệu API

Khi review một trang API, có thể xem xét:

- Audience và mục đích có rõ không?
- API có đúng tên và đúng version không?
- Signature hoặc syntax có đầy đủ không?
- Parameter type, required, default và constraints có được mô tả không?
- Return value hoặc output schema có rõ không?
- Side effect, permission và resource limit có được nêu không?
- Error code, exit code và retry behavior có được giải thích không?
- Example có chạy được và không chứa secret không?
- Link tới guide, concept và troubleshooting có phù hợp không?
- Compatibility và deprecation có được cập nhật không?
- Generated content có khớp implementation không?
- Navigation và anchor có dễ tìm không?

Checklist hỗ trợ review, nhưng không thay thế việc xác minh behavior bằng implementation hoặc test.

## 32. Quy trình xây dựng bộ tài liệu API công cụ

Một dự án có thể triển khai theo các bước:

1. **Lập inventory API:** CLI, library, HTTP, compiler, plugin, language server và configuration.
2. **Xác định audience:** người viết DSL, integrator, plugin author, operator và administrator.
3. **Xác định source of truth:** source annotations, API schema, OpenAPI, grammar hoặc command definition.
4. **Thiết kế information architecture:** getting started, concepts, guides, reference, examples và troubleshooting.
5. **Chuẩn hóa reference template:** purpose, syntax, parameters, output, errors, permissions và examples.
6. **Đặc tả types và semantics:** nullability, defaults, units, version và constraints.
7. **Tài liệu hóa behavior vận hành:** side effects, timeout, resource limits, retry và cancellation.
8. **Tạo examples:** minimal, complete, error và integration samples.
9. **Sinh nội dung tự động:** reference từ source/schema khi phù hợp.
10. **Kiểm tra tự động:** lint, links, schema, generated diff và example tests.
11. **Review với API owner:** xác nhận contract và compatibility.
12. **Version và publish:** gắn docs với tool release.
13. **Theo dõi feedback:** search, support issues và usage.
14. **Cập nhật migration:** deprecation, breaking change và version transition.

## 33. Tiêu chí của tài liệu API công cụ tốt

Tài liệu API công cụ tốt cho người đọc biết chính xác interface nào được hỗ trợ, cách gọi, input hợp lệ, output, lỗi và tác động của thao tác. Nó được tổ chức theo nhu cầu tra cứu, liên kết với hướng dẫn sử dụng và được version hóa cùng sản phẩm.

Các câu hỏi quan trọng:

- CLI, library, HTTP, compiler và plugin API có được phân loại rõ không?
- Mỗi API có purpose, signature và parameter table không?
- Default, precedence và validation rules có được ghi không?
- Return value, output schema và exit code có rõ không?
- Side effect, permission và resource limits có được mô tả không?
- Error code và remediation có thể tra cứu được không?
- Ví dụ có chạy được và gắn đúng version không?
- Generated docs có nguồn dữ liệu đáng tin cậy không?
- Compatibility, deprecation và migration có được công bố không?
- Người dùng có thể tìm API bằng search, anchor và navigation không?
- Tài liệu có được kiểm tra cùng CI và release không?
- Feedback từ người dùng có được dùng để cải thiện docs không?

Tài liệu API công cụ là một phần của trải nghiệm và hợp đồng sử dụng DSL toolchain. Khi interface được mô tả chính xác, có ví dụ thực thi được, nêu rõ lỗi và side effect, đồng thời được quản lý theo version, người dùng có thể tích hợp và tự động hóa công cụ với ít giả định sai hơn. Một hệ thống tài liệu tốt giúp API dễ khám phá, dễ học, dễ vận hành và có thể tiến hóa mà vẫn giữ được khả năng tương thích cho các consumer.
