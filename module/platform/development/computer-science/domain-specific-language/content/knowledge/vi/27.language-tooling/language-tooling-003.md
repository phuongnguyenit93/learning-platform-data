# Trình kiểm tra

Trong quá trình sử dụng **Domain-Specific Language (DSL)**, người viết cần biết chương trình có hợp lệ hay không trước khi đưa nó vào compiler, runtime hoặc môi trường triển khai. Một file DSL có thể sai cú pháp, tham chiếu tới symbol không tồn tại, dùng kiểu dữ liệu không phù hợp hoặc vi phạm quy tắc của miền nghiệp vụ. **Trình kiểm tra (checker)** là công cụ nhận source hoặc artifact DSL, phân tích chúng và thông báo những vấn đề có thể phát hiện.

Ví dụ, một DSL mô tả cấu hình dịch vụ:

~~~text
service "orders-api" {
    replicas = 0
    memory = "512Mi"
    network = "backend"
}
~~~

Đoạn source có thể đúng cú pháp, nhưng replicas = 0 có thể vi phạm quy tắc miền nếu dịch vụ phải có ít nhất một replica. Một trình kiểm tra có thể phát hiện lỗi đó trước khi cấu hình được triển khai.

Checker có thể chạy như lệnh dòng lệnh, chức năng trong IDE, bước trong CI pipeline, thư viện được nhúng vào ứng dụng hoặc dịch vụ kiểm tra từ xa. Dù giao diện khác nhau, mục tiêu chung là đưa ra kết luận có căn cứ về source, giải thích lỗi tại vị trí phù hợp và giúp người dùng sửa chúng.

## 1. Trình kiểm tra là gì?

**Checker** là công cụ phân tích chương trình hoặc cấu hình DSL để xác định chúng có thỏa các quy tắc được định nghĩa hay không. Tùy phạm vi, checker có thể kiểm tra:

- Cấu trúc lexical và cú pháp.
- Tên, scope, module và symbol reference.
- Kiểu dữ liệu, chữ ký hàm và khả năng chuyển kiểu.
- Ràng buộc giữa các thành phần.
- Quy tắc riêng của miền nghiệp vụ.
- Dependency graph, cấu hình và khả năng triển khai.
- Các quy ước chất lượng như tên, cấu trúc hoặc cách dùng tính năng.
- Một số rủi ro bảo mật và cấu hình không an toàn.

Checker thường dùng lại frontend của compiler hoặc language server: lexer, parser, AST, symbol table, type checker và semantic model. Điểm khác biệt chủ yếu nằm ở cách công cụ tổ chức kết quả, cấu hình quy tắc, hiển thị diagnostics và tích hợp với quy trình phát triển.

### 1.1. Checker không chỉ là parser

Parser xác định source có phù hợp grammar và có thể tạo AST hay không. Checker có thể dùng parser làm bước đầu, sau đó kiểm tra những vấn đề cần hiểu ngữ nghĩa hoặc toàn bộ project.

Ví dụ:

~~~text
let timeout: Integer = "fast"
~~~

Grammar có thể chấp nhận khai báo, nhưng type checker phát hiện giá trị String không tương thích với Integer.

Một ví dụ khác:

~~~text
service "api" {
    network = "missing-network"
}
~~~

Tên và kiểu của thuộc tính có thể hợp lệ, nhưng checker cần tra cứu project model để xác định network có tồn tại hay không.

### 1.2. Checker có thể kiểm tra tĩnh hoặc động

- **Static checker:** phân tích source hoặc artifact mà không thực thi toàn bộ chương trình.
- **Dynamic checker:** kiểm tra hành vi khi chương trình chạy hoặc khi dữ liệu thực tế xuất hiện.
- **Hybrid checker:** kết hợp phân tích tĩnh với thông tin từ schema, registry hoặc môi trường đích.

Trong DSL cấu hình và rule, phần lớn lỗi nên được phát hiện tĩnh trước khi triển khai. Một số điều kiện phụ thuộc database, quyền thực tế hoặc dữ liệu runtime chỉ có thể được xác nhận ở giai đoạn sau.

## 2. Vì sao cần checker cho DSL?

DSL thường được sử dụng bởi người hiểu miền nghiệp vụ nhưng không nhất thiết là chuyên gia compiler. Một checker tốt giúp họ phát hiện vấn đề bằng khái niệm quen thuộc của miền thay vì buộc họ đọc lỗi nội bộ của parser hoặc runtime.

Checker đem lại các lợi ích:

- **Phản hồi sớm:** phát hiện lỗi trước khi build, deploy hoặc chạy workflow.
- **Giải thích theo ngữ cảnh:** chỉ ra resource, rule, field hoặc dependency liên quan.
- **Chuẩn hóa quy tắc:** áp dụng cùng chính sách trên máy cá nhân, IDE và CI.
- **Giảm lỗi vận hành:** chặn cấu hình sai hoặc vi phạm invariant trước khi triển khai.
- **Hỗ trợ cộng tác:** cung cấp diagnostics nhất quán trong pull request và pipeline.
- **Tự động hóa:** kiểm tra hàng loạt file, project hoặc repository.
- **Hỗ trợ tiến hóa DSL:** phát hiện cách dùng tính năng cũ hoặc cấu trúc sắp bị loại bỏ.

Ví dụ, thay vì chỉ báo type mismatch, checker chuyên cho DSL hạ tầng có thể báo:

~~~text
services/api.dsl:4:16
error DSL204: Field 'replicas' must be at least 1.
Current value: 0.
~~~

Thông báo theo miền giúp người viết hiểu điều cần sửa và lý do quy tắc tồn tại.

## 3. Phân biệt checker với các công cụ liên quan

Các công cụ phát triển DSL có thể dùng chung parser và semantic model nhưng phục vụ mục tiêu khác nhau.

| Công cụ | Trách nhiệm chính | Kết quả |
|---|---|---|
| Lexer | Chuyển ký tự thành token | Token stream |
| Parser | Kiểm tra grammar và tạo cấu trúc | AST hoặc syntax diagnostics |
| Semantic analyzer | Resolve tên, kiểu và ngữ nghĩa | Semantic model và diagnostics |
| Checker | Tổ chức, chạy và trình bày các quy tắc kiểm tra | Kết quả pass/fail, warnings và errors |
| Linter | Phát hiện vấn đề về quy ước, khả năng đọc hoặc pattern đáng ngờ | Warnings, suggestions |
| Formatter | Chuẩn hóa cách trình bày source | Source đã định dạng |
| Compiler | Chuyển source thành artifact thực thi | Bytecode, IR hoặc executable |
| Test runner | Chạy test và so sánh kết quả mong đợi | Test report |

Ranh giới có thể chồng lấn. Một CLI có tên dsl check có thể chạy parser, semantic analyzer, linter và domain validator. Điều quan trọng là tài liệu hóa nhóm quy tắc nào được thực hiện và kết quả nào có thể được xem là bảo đảm.

### 3.1. Checker và compiler

Compiler thường phải từ chối source không thể tạo artifact hợp lệ. Checker có thể chạy trước compiler và có chế độ chỉ kiểm tra, không sinh mã.

Ví dụ:

~~~text
dsl check project/
dsl build project/
~~~

Lệnh check có thể trả diagnostics mà không ghi output build. Lệnh build có thể gọi cùng frontend và dừng nếu có lỗi chặn biên dịch.

### 3.2. Checker và linter

Một checker có thể bao gồm lint rules, nhưng hai nhóm kết quả nên được phân biệt:

- Lỗi ngữ nghĩa hoặc vi phạm hợp đồng làm chương trình không hợp lệ.
- Cảnh báo chất lượng chỉ ra cấu trúc khó bảo trì hoặc có khả năng sai.

Ví dụ, tham chiếu tới resource không tồn tại thường là error; một tên biến không theo convention có thể là warning. Nếu mọi warning đều chặn build, người dùng có thể khó phân biệt lỗi thực sự với khuyến nghị.

## 4. Các lớp kiểm tra

Một checker cho DSL có thể tổ chức quy tắc theo nhiều lớp. Không phải dự án nào cũng cần tất cả.

### 4.1. Kiểm tra lexical

Phát hiện ký tự, literal hoặc token không hợp lệ:

~~~text
let name = "unfinished
~~~

Các vấn đề thường gặp:

- Chuỗi chưa đóng.
- Escape sequence không hợp lệ.
- Ký tự không được phép.
- Number literal sai định dạng.
- Comment hoặc delimiter không hoàn chỉnh.

### 4.2. Kiểm tra cú pháp

Phát hiện source không phù hợp grammar:

~~~text
if condition
    runTask()
~~~

Nếu DSL yêu cầu block bằng dấu ngoặc nhọn, parser có thể báo thiếu dấu mở block.

### 4.3. Kiểm tra tên và phạm vi

Xác nhận tên được khai báo và có thể truy cập:

~~~text
step deploy {
    after package
}
~~~

Nếu không có step package, checker báo undefined reference. Nó cũng có thể phát hiện tên trùng, tham chiếu mơ hồ hoặc truy cập symbol private.

### 4.4. Kiểm tra kiểu

Xác nhận toán hạng, giá trị gán và lời gọi phù hợp:

~~~text
let retries: Integer = "three"
~~~

Checker có thể báo String không thể gán vào Integer.

### 4.5. Kiểm tra cấu trúc và quan hệ

Một thành phần có thể hợp lệ riêng lẻ nhưng sai khi xét cùng thành phần khác:

~~~text
step A { after B }
step B { after A }
~~~

Nếu workflow yêu cầu dependency graph không có chu trình, checker cần xây đồ thị và phát hiện cycle.

### 4.6. Kiểm tra quy tắc miền

Ví dụ:

- Số lượng replica phải lớn hơn 0.
- Ngày kết thúc phải sau ngày bắt đầu.
- Mức giảm giá nằm trong khoảng cho phép.
- Resource phải thuộc đúng environment.
- Một trạng thái chỉ được chuyển sang trạng thái kế tiếp hợp lệ.

Các quy tắc này thường không thể diễn đạt đầy đủ bằng grammar hoặc type system tổng quát.

### 4.7. Kiểm tra bảo mật và chính sách

Checker có thể phát hiện:

- Secret được ghi trực tiếp trong source.
- Capability bị cấm.
- Quyền truy cập rộng hơn policy.
- Image hoặc dependency không nằm trong allowlist.
- Đường dẫn có nguy cơ thoát khỏi workspace.
- Cấu hình dùng thuật toán hoặc protocol không được chấp thuận.

Static checker chỉ có thể phát hiện các pattern và metadata mà nó biết. Nó không thay thế kiểm soát quyền thực tế ở runtime.

### 4.8. Kiểm tra style và maintainability

Ví dụ:

- Tên rule không theo convention.
- Block quá dài.
- Biến không được sử dụng.
- Cấu hình trùng lặp.
- Tính năng deprecated vẫn còn được dùng.
- Điều kiện luôn đúng hoặc luôn sai.

Các quy tắc này thường tạo warning hoặc hint, tùy chính sách dự án.

## 5. Pipeline kiểm tra

Checker nên tổ chức các bước theo quan hệ phụ thuộc giữa dữ liệu phân tích.

~~~mermaid
flowchart TD
    A[Input files and configuration] --> B[Discover project]
    B --> C[Load schemas and dependencies]
    C --> D[Lex and parse]
    D --> E[Build AST]
    E --> F[Resolve names and types]
    F --> G[Build project and domain model]
    G --> H[Run validation rules]
    H --> I[Run lint and policy rules]
    I --> J[Collect diagnostics]
    J --> K[Format and sort results]
    K --> L[CLI / IDE / CI output]
~~~

### 5.1. Khám phá project

Checker xác định file cần kiểm tra, project root, manifest, module và cấu hình. Cần có quy tắc rõ về file pattern, thư mục bị loại trừ và cách xử lý file ngoài workspace.

### 5.2. Nạp schema và dependency

Một số DSL cần schema, catalog, package hoặc resource metadata để resolve tên và kiểm tra kiểu. Checker cần xác định dependency version và xử lý trường hợp thiếu hoặc không tương thích.

### 5.3. Phân tích source

Lexer và parser tạo AST. Semantic analyzer bổ sung binding và type. Nếu một file có lỗi cú pháp, checker vẫn có thể tiếp tục các file độc lập và tạo diagnostics cho những phần còn phân tích được.

### 5.4. Chạy rule

Rule engine hoặc các visitor chuyên biệt duyệt AST/semantic model để kiểm tra invariant. Mỗi rule nên có ID ổn định, mô tả, severity mặc định và vị trí nguồn.

### 5.5. Tổng hợp kết quả

Diagnostics từ nhiều pha được chuẩn hóa, sắp xếp và chuyển sang output format phù hợp với CLI, IDE hoặc CI.

## 6. Đầu vào của checker

Checker có thể nhận một file, danh sách file, thư mục project hoặc artifact đã build.

### 6.1. File đơn

~~~text
dsl check rules/pricing.dsl
~~~

Phù hợp khi người dùng chỉnh sửa một file độc lập. Checker có thể cần nạp project context nếu file tham chiếu tới module khác.

### 6.2. Project hoặc workspace

~~~text
dsl check .
~~~

Checker khám phá manifest, file source, schema và dependency. Đây là chế độ phù hợp cho CI và kiểm tra toàn bộ project.

### 6.3. Nhiều file được chỉ định

~~~text
dsl check services/*.dsl schemas/*.schema
~~~

Nếu CLI hỗ trợ glob, cần xác định quy tắc mở rộng pattern trên các hệ điều hành và cách xử lý đường dẫn có dấu cách.

### 6.4. Dữ liệu qua stdin

~~~text
cat rules/pricing.dsl | dsl check --stdin --language dsl
~~~

Stdin hữu ích cho editor, script hoặc hệ thống khác tích hợp checker. Checker cần nhận được language mode hoặc project context khi không có file path.

### 6.5. Artifact đã biên dịch

Checker có thể xác thực manifest, dependency, capability hoặc cấu trúc bytecode. Đây là loại kiểm tra khác với kiểm tra source; cần nêu rõ trong output đang kiểm tra source hay artifact.

## 7. Cấu hình checker

Checker thường có cấu hình theo project để các thành viên dùng cùng quy tắc.

Ví dụ file cấu hình minh họa:

~~~yaml
checker:
  version: 1
  include:
    - "src/**/*.dsl"
    - "schemas/**/*.schema"
  exclude:
    - "build/**"
    - "vendor/**"
  rules:
    undefined-resource: error
    unused-variable: warning
    deprecated-feature: warning
    hardcoded-secret: error
  maxDiagnostics: 500
~~~

Schema thực tế phụ thuộc checker. Cấu hình nên có version để công cụ có thể kiểm tra tính tương thích khi format thay đổi.

### 7.1. Nguồn cấu hình

Một checker có thể nhận cấu hình từ:

- Giá trị mặc định trong công cụ.
- File cấu hình project.
- File cấu hình user.
- Tham số CLI.
- Environment variables trong môi trường CI.
- API khi được nhúng vào ứng dụng.

Thứ tự ưu tiên cần được tài liệu hóa. Ví dụ, CLI có thể override project config, còn project config override default.

### 7.2. Include và exclude

Include xác định file cần kiểm tra; exclude bỏ qua file như generated output, cache hoặc dependency vendor. Checker cần tránh vô tình bỏ qua source quan trọng do glob quá rộng.

### 7.3. Severity override

Người dùng có thể đổi severity cho một số rule:

~~~yaml
rules:
  unused-variable: off
  missing-description: info
  invalid-permission: error
~~~

Không nên cho phép cấu hình làm vô hiệu hóa những kiểm tra bắt buộc về an toàn nếu hệ thống triển khai yêu cầu chúng. Có thể tách policy bắt buộc của tổ chức khỏi lint rules tùy chỉnh.

### 7.4. Cấu hình theo thư mục

Với monorepo, các thư mục có thể có cấu hình riêng. Checker cần xác định file cấu hình nào áp dụng cho từng file, cách kế thừa và cách giải quyết xung đột. Cấu hình con không nên vô tình hạ thấp policy bắt buộc ở cấp project hoặc organization.

## 8. Diagnostics

**Diagnostic** là bản ghi mô tả một vấn đề được checker phát hiện. Một diagnostic tốt có đủ thông tin để người dùng tìm tới source và hiểu vấn đề.

Các trường thường có:

| Trường | Ý nghĩa |
|---|---|
| code | ID ổn định của rule hoặc lỗi |
| severity | Error, Warning, Information hoặc Hint |
| message | Mô tả vấn đề |
| file/URI | Tài liệu chứa vấn đề |
| range | Vị trí bắt đầu và kết thúc |
| source | Tên checker hoặc subsystem |
| relatedInformation | Vị trí liên quan |
| tags | Ví dụ deprecated hoặc unnecessary |
| data | Metadata nội bộ cho quick fix hoặc resolve |

Ví dụ:

~~~text
services/api.dsl:4:16
error DSL204: Field 'replicas' must be at least 1.
  Current value: 0.
  Rule: service-replica-range
~~~

### 8.1. Vị trí chính xác

Checker nên chỉ vào token hoặc biểu thức gây lỗi. Với lỗi liên quan nhiều khai báo, có thể dùng related information để chỉ vị trí declaration hoặc dependency khác.

Ví dụ duplicate symbol:

~~~text
rules.dsl:20:6
error DSL101: Duplicate rule name 'shipping'.

Related location:
rules.dsl:4:6
First declaration is here.
~~~

### 8.2. Mã lỗi ổn định

Mã như DSL101 hoặc undefined-resource giúp:

- Cấu hình severity.
- Suppress có kiểm soát.
- IDE liên kết tài liệu.
- CI phân loại lỗi.
- Test xác nhận đúng rule.

Không nên dùng số dòng hoặc thứ tự chạy làm ID vì chúng thay đổi khi nội dung hoặc thứ tự phân tích thay đổi.

### 8.3. Message và gợi ý sửa

Thông báo nên mô tả điều kiện bị vi phạm, giá trị hiện tại nếu hữu ích và cách sửa khả thi. Gợi ý không nên khẳng định một cách sửa duy nhất nếu checker không có đủ ngữ cảnh.

### 8.4. Related information

Một lỗi có thể phụ thuộc nhiều vị trí. Ví dụ, dependency cycle cần chỉ ra các cạnh hoặc step tạo thành chu trình. Related information giúp người dùng lần theo toàn bộ quan hệ thay vì chỉ thấy node cuối.

## 9. Severity và chính sách chặn

Checker thường phân loại kết quả theo mức độ:

- **Error:** vi phạm khiến source hoặc artifact không hợp lệ theo policy.
- **Warning:** khả năng sai, rủi ro hoặc cách dùng không được khuyến khích.
- **Information:** thông tin hữu ích nhưng không nhất thiết cần hành động.
- **Hint:** gợi ý nhỏ hoặc cơ hội cải thiện.

Một CLI có thể hỗ trợ các ngưỡng:

~~~text
dsl check --fail-on error
dsl check --fail-on warning
~~~

fail-on error trả exit code thất bại nếu có error. fail-on warning cũng thất bại khi có warning. Cần xác định exit code riêng cho lỗi cấu hình checker, lỗi đọc file hoặc lỗi nội bộ để CI có thể phân biệt.

### 9.1. Severity và confidence

Severity mô tả mức độ quan trọng của vấn đề; confidence mô tả độ chắc chắn của phát hiện. Một checker có thể có warning với confidence thấp khi phát hiện pattern đáng ngờ. Không nên dùng severity để che giấu sự không chắc chắn.

### 9.2. Policy bắt buộc

Một số rule được tổ chức yêu cầu phải luôn bật, chẳng hạn kiểm tra secret hoặc quyền nguy hiểm. Nên phân biệt policy bắt buộc với rule style tùy chỉnh để người dùng không thể vô tình vô hiệu hóa kiểm tra quan trọng bằng config cục bộ.

## 10. CLI của checker

Command-line interface là cách phổ biến để chạy checker trong terminal, script và CI.

Một CLI có thể có:

~~~text
dsl check [paths...]
    --config <path>
    --format <text|json|sarif>
    --fail-on <error|warning|none>
    --rule <rule-id>
    --exclude <glob>
    --stdin
    --quiet
    --verbose
~~~

Các option là ví dụ thiết kế. CLI cần nhất quán với các lệnh build, format và test của toolchain DSL.

### 10.1. Exit code

Ví dụ quy ước:

| Exit code | Ý nghĩa |
|---:|---|
| 0 | Kiểm tra hoàn tất và không có diagnostics vượt ngưỡng |
| 1 | Có lỗi hoặc diagnostics vượt ngưỡng fail-on |
| 2 | Cấu hình hoặc tham số CLI không hợp lệ |
| 3 | Không thể đọc file hoặc dependency bắt buộc |
| 4 | Lỗi nội bộ của checker |

Đây là quy ước minh họa. Một công cụ nên công bố exit code ổn định để script và CI không phải phân tích chuỗi message.

### 10.2. Output dễ đọc

Output text phù hợp cho con người:

~~~text
Checking project: inventory

src/stock.dsl:12:8  error DSL204  replicas must be at least 1
src/order.dsl:31:4  warning DSL310  deprecated field 'legacyCode'

2 diagnostics: 1 error, 1 warning
Check failed.
~~~

Output nên sắp xếp ổn định theo file, dòng, cột và rule code để diff giữa các lần chạy dễ đọc.

### 10.3. Quiet và verbose

Quiet có thể chỉ in diagnostics và summary tối thiểu. Verbose có thể hiển thị project discovery, dependency loading và thời gian từng pha. Không nên để verbose làm lộ secret hoặc nội dung nhạy cảm.

## 11. Output machine-readable

Checker thường cần xuất kết quả để IDE, dashboard hoặc CI đọc tự động.

### 11.1. JSON

Ví dụ:

~~~json
{
  "tool": {
    "name": "dsl-checker",
    "version": "2.3.0"
  },
  "filesChecked": 18,
  "diagnostics": [
    {
      "code": "DSL204",
      "severity": "error",
      "message": "Field 'replicas' must be at least 1.",
      "file": "services/api.dsl",
      "range": {
        "start": { "line": 3, "character": 15 },
        "end": { "line": 3, "character": 16 }
      }
    }
  ]
}
~~~

Schema JSON cần có version và quy tắc encoding rõ. Khi thêm trường, nên duy trì backward compatibility nếu output được các công cụ khác tiêu thụ.

### 11.2. SARIF

SARIF là định dạng trao đổi kết quả phân tích tĩnh, thường dùng để tích hợp findings vào nền tảng code scanning. Checker có thể ánh xạ rule ID, severity, location, related location và remediation vào SARIF.

Khi xuất SARIF, cần xác định URI base, rule metadata và cách ánh xạ severity. Không nên chỉ đổi đuôi file JSON tùy ý thành .sarif; phải tạo cấu trúc đúng schema.

### 11.3. Không trộn log với kết quả

Nếu CI đọc JSON từ stdout, log debug xen giữa có thể làm output không parse được. Có thể quy định:

- stdout chứa machine-readable result.
- stderr chứa progress và log.
- Exit code thể hiện kết quả tổng thể.

Quy tắc này giúp tích hợp ổn định.

## 12. Tích hợp checker với IDE và Language Server

Checker có thể cung cấp engine dùng chung cho CLI và Language Server. IDE cần phản hồi nhanh và chỉ kiểm tra phần source liên quan tới thay đổi.

### 12.1. Diagnostics trực tiếp

Khi document thay đổi, language server có thể:

1. Nhận text document notification.
2. Cập nhật document snapshot.
3. Parse và phân tích semantic.
4. Chạy các rule phù hợp.
5. Gửi diagnostics cho client.

### 12.2. Incremental checking

Thay vì chạy lại toàn bộ project sau mỗi phím gõ, checker có thể dùng dependency graph và cache:

- Thay đổi literal có thể chỉ ảnh hưởng biểu thức hoặc block hiện tại.
- Đổi tên symbol có thể ảnh hưởng mọi reference.
- Sửa schema có thể ảnh hưởng nhiều file phụ thuộc.
- Thay đổi project config có thể làm vô hiệu hóa nhiều kết quả đã cache.

### 12.3. Debounce và cancellation

IDE có thể gửi nhiều thay đổi liên tiếp. Checker nên hỗ trợ hủy công việc cũ và trì hoãn một khoảng ngắn trước khi phân tích lại. Kết quả của document version cũ không nên ghi đè diagnostics của version mới.

### 12.4. Phân biệt diagnostics từ server và CLI

CLI có thể kiểm tra toàn bộ repository và policy CI. Language server có thể chạy subset quy tắc nhanh cho file đang mở. Cả hai nên dùng cùng rule implementation và cấu hình cốt lõi để tránh kết quả khác nhau không giải thích được.

## 13. Checker trong CI/CD

CI thường chạy checker khi có commit hoặc pull request để chặn lỗi trước khi merge hoặc deploy.

Ví dụ pipeline:

~~~mermaid
flowchart TD
    A[Checkout source] --> B[Install pinned checker]
    B --> C[Resolve dependencies]
    C --> D[Run DSL checker]
    D --> E{Diagnostics pass policy?}
    E -->|No| F[Fail pipeline and publish report]
    E -->|Yes| G[Build or package]
    G --> H[Deploy stage]
~~~

Một lệnh:

~~~text
dsl check . --format sarif --fail-on warning
~~~

### 13.1. Pin phiên bản checker

CI nên dùng phiên bản checker cố định hoặc version range được kiểm soát. Nếu luôn lấy phiên bản mới nhất, cùng một commit có thể cho kết quả khác nhau theo thời điểm chạy.

### 13.2. Cache dependency

Checker có thể cần schema hoặc package. CI có thể cache dependency theo lockfile hoặc manifest hash. Cache cần được invalidation khi version thay đổi.

### 13.3. Chặn merge theo policy

Policy có thể quy định không merge nếu:

- Có error.
- Có warning thuộc nhóm security.
- Số warning mới tăng so với baseline.
- Có rule bắt buộc bị suppress.

Không nên chỉ dựa vào tổng số diagnostics nếu cần phân biệt lỗi mới với debt cũ.

### 13.4. Baseline

Với repository có nhiều warning lịch sử, checker có thể hỗ trợ baseline để theo dõi findings đã tồn tại và chỉ chặn findings mới. Baseline nên gắn với rule ID, file và fingerprint của finding, không chỉ dòng số vì dòng có thể dịch chuyển.

Baseline không nên trở thành cách che giấu lỗi mới hoặc bỏ qua thay đổi severity. Cần có quy trình cập nhật và review baseline.

## 14. Rule engine và cấu trúc rule

Checker có thể dùng tập rule được đăng ký tĩnh hoặc một rule engine có thể mở rộng.

Một rule nên có:

- ID ổn định.
- Tên và mô tả.
- Category.
- Severity mặc định.
- Phiên bản hoặc trạng thái deprecated.
- Điều kiện chạy.
- Logic phân tích.
- Cách tạo diagnostic.
- Quick fix nếu có thể sửa an toàn.

Ví dụ metadata:

~~~yaml
id: service-replica-range
category: domain
defaultSeverity: error
description: Replica count must be positive.
requires:
  - typed-ast
  - service-schema
~~~

### 14.1. Visitor pattern

Một rule có thể duyệt AST bằng visitor:

~~~text
visitServiceDeclaration(node):
    value = constantValue(node.replicas)

    if value is known and value < 1:
        report(
            code = "service-replica-range",
            range = node.replicas.range,
            message = "Replica count must be at least 1."
        )
~~~

Visitor phù hợp với rule gắn vào loại node cụ thể. Những kiểm tra toàn project như dependency cycle cần xây graph hoặc project index thay vì chỉ duyệt từng node độc lập.

### 14.2. Rule có dependency

Một rule có thể cần AST, type information, symbol table hoặc external schema. Checker nên mô tả dependency để chỉ chạy rule khi dữ liệu cần thiết đã sẵn sàng.

Ví dụ:

| Rule | Dữ liệu cần |
|---|---|
| Missing delimiter | Token stream hoặc parser |
| Undefined symbol | Scope và symbol table |
| Invalid assignment | Typed AST |
| Dependency cycle | Project dependency graph |
| Unknown resource | Resource catalog |
| Deprecated field | Schema/version metadata |

### 14.3. Rule độc lập và rule liên file

Rule độc lập có thể chạy song song trên từng file. Rule liên file cần project model đầy đủ. Checker nên phân biệt hai loại để tổ chức scheduling và cache hợp lý.

## 15. Plugin và custom rules

Một số checker cho phép tổ chức hoặc người dùng bổ sung rule.

Custom rule có thể:

- Kiểm tra naming convention riêng.
- Áp dụng policy kiến trúc.
- Cấm một số capability.
- Xác nhận metadata bắt buộc.
- Kiểm tra quy tắc nghiệp vụ riêng của tổ chức.

Một API rule có thể trông như:

~~~text
registerRule({
    id: "company-required-owner",
    phase: "domain",
    severity: "error",
    visit(node, context) {
        if node is ServiceDeclaration and node.owner is missing:
            context.report(node.range, "Service must declare an owner.")
    }
})
~~~

Đây là API giả định. Contract thực tế cần xác định version, kiểu node, khả năng đọc project model và giới hạn quyền.

### 15.1. Trust boundary của plugin

Plugin chạy trong process checker có thể truy cập tài nguyên của process đó. Không nên nạp plugin từ nguồn tùy ý mà không có trust policy. Có thể dùng:

- Allowlist package.
- Version pinning và checksum.
- Chữ ký hoặc registry tin cậy.
- Process isolation cho plugin không tin cậy.
- Timeout và quota.

### 15.2. Tương thích plugin

Checker cần định nghĩa plugin API version. Khi thay đổi AST schema hoặc context API, có thể cần compatibility layer hoặc version mới để plugin cũ không bị lỗi âm thầm.

## 16. Quick fix và autofix

Một số diagnostics có thể đi kèm cách sửa tự động.

Ví dụ, checker phát hiện thuộc tính deprecated và biết tên thay thế:

~~~text
legacyTimeout = 30
~~~

Quick fix có thể đề xuất:

~~~text
timeout = 30
~~~

### 16.1. Quick fix

Quick fix là chỉnh sửa được đề xuất cho người dùng chọn. Nó có thể áp dụng một hoặc nhiều text edit, thêm import hoặc cập nhật cấu trúc.

### 16.2. Autofix

Autofix áp dụng sửa đổi mà không cần người dùng xác nhận từng finding. Chỉ nên tự động sửa khi kết quả đủ xác định và không làm đổi semantics ngoài dự kiến.

### 16.3. Safe và unsafe fix

Có thể phân loại:

- **Safe fix:** thay đổi định dạng hoặc chuyển đổi tương đương đã được chứng minh.
- **Potentially unsafe fix:** thay đổi logic, cần người dùng review.
- **Suggestion only:** checker không đủ thông tin để tạo patch đáng tin cậy.

### 16.4. Kiểm tra sau khi sửa

Sau khi áp dụng autofix, checker nên phân tích lại phần bị ảnh hưởng để xác nhận diagnostics đã được giải quyết và không phát sinh lỗi mới. Nếu có nhiều fix chồng lấn cùng vùng source, cần quy tắc ưu tiên hoặc từ chối áp dụng tự động.

## 17. Suppression và ngoại lệ có kiểm soát

Đôi khi một finding là false positive hoặc một ngoại lệ đã được chấp thuận. Checker có thể cho phép suppression:

~~~text
// checker:disable-next-line legacy-field
legacyField = "compatibility-mode"
~~~

Hoặc cấu hình theo file:

~~~yaml
ignore:
  - rule: legacy-field
    path: "migration/**/*.dsl"
    reason: "Temporary compatibility during migration"
~~~

### 17.1. Yêu cầu với suppression

Suppression nên:

- Chỉ áp dụng cho rule cụ thể.
- Có phạm vi nhỏ nhất có thể.
- Có lý do khi policy yêu cầu.
- Có thể được báo cáo trong output.
- Có thể hết hạn hoặc được review định kỳ.

### 17.2. Không suppress lỗi parser tùy tiện

Một lỗi cú pháp có thể khiến các pha sau không hiểu cấu trúc source. Việc bỏ qua diagnostic không làm source trở nên hợp lệ. Suppression chỉ thay đổi cách hiển thị hoặc chính sách đối với finding, không sửa ngữ nghĩa chương trình.

### 17.3. Suppression của policy bắt buộc

Các rule bảo mật hoặc compliance có thể không cho phép suppression ở source. Nếu có ngoại lệ, nên yêu cầu phê duyệt ở cấp policy hoặc repository thay vì comment tùy ý.

## 18. Kiểm tra project và dependency

Checker cho DSL thường cần nhìn rộng hơn một file.

Ví dụ:

~~~text
module orders {
    import shared.money
    use shared.money.Decimal
}
~~~

Checker cần:

- Resolve module path.
- Xác nhận package tồn tại.
- Kiểm tra version tương thích.
- Phát hiện import cycle nếu bị cấm.
- Xác nhận symbol được export.
- Kiểm tra schema hoặc API dependency.

### 18.1. Lockfile và reproducibility

Nếu DSL dùng package hoặc schema có version, checker nên sử dụng lockfile hoặc dependency manifest đã khóa để kết quả ổn định.

### 18.2. External registry

Checker có thể cần metadata từ registry. Cần cache, timeout và thông báo rõ khi registry không truy cập được. Không nên coi lỗi mạng là bằng chứng package không tồn tại.

### 18.3. Offline mode

Offline mode sử dụng dependency cache có sẵn và không gọi mạng. Nếu thiếu metadata, checker cần báo rõ kiểm tra nào chưa thể hoàn tất thay vì trả pass toàn phần.

## 19. Checker và schema validation

Nhiều DSL cấu hình có schema định nghĩa các field, kiểu và constraint.

Ví dụ schema khái niệm:

~~~yaml
type: Service
fields:
  replicas:
    type: Integer
    minimum: 1
    maximum: 100
  memory:
    type: MemorySize
    required: true
  network:
    type: NetworkReference
    required: true
~~~

Checker có thể dùng schema để xác nhận:

- Field có tồn tại không.
- Field bắt buộc có được khai báo không.
- Giá trị có đúng kiểu không.
- Giá trị có nằm trong range không.
- Enum có chứa giá trị được chọn không.
- Reference có trỏ tới resource hợp lệ không.
- Hai field có ràng buộc với nhau không.

### 19.1. Schema validation và domain validation

Schema validation thường kiểm tra hình dạng và constraint của từng đối tượng. Domain validation có thể kiểm tra quan hệ phức tạp giữa nhiều đối tượng hoặc trạng thái.

Ví dụ, schema xác nhận network là string. Domain checker tiếp tục xác nhận network đó tồn tại trong environment và service có quyền sử dụng.

### 19.2. Schema version

Checker cần biết source đang dùng schema version nào. Một field hợp lệ ở schema mới có thể không tồn tại trong schema cũ. Không nên kiểm tra source bằng schema không xác định rồi đưa ra kết luận chắc chắn.

## 20. Kiểm tra policy và bảo mật

Checker có thể tích hợp policy rules để ngăn cấu hình rủi ro trước khi triển khai.

Ví dụ:

~~~text
service "admin-api" {
    public = true
    authentication = "none"
}
~~~

Một policy có thể yêu cầu service public phải bật authentication.

Các nhóm rule thường gặp:

- Secret không được hardcode.
- Không cho phép quyền wildcard.
- Không dùng image không rõ nguồn.
- Không cho phép endpoint không mã hóa.
- Không cấp filesystem write ngoài vùng cho phép.
- Không bật debug mode trong production.
- Không cho phép dependency version không được duyệt.

### 20.1. Static policy và runtime enforcement

Checker phân tích source/config để dự đoán cấu hình. Runtime hoặc nền tảng triển khai vẫn cần enforce quyền thực tế. Ví dụ, checker có thể xác nhận policy khai báo không yêu cầu quyền nguy hiểm, nhưng không thể bảo đảm process không bị cấp thêm quyền từ bên ngoài.

### 20.2. Secret detection

Checker có thể phát hiện pattern giống token hoặc password. Tuy nhiên, phát hiện dựa trên pattern có false positive và false negative. Không nên in giá trị secret đầy đủ trong diagnostics hoặc log; chỉ cần chỉ vị trí và gợi ý chuyển sang secret manager.

## 21. Hiệu năng và incremental checking

Một checker project lớn có thể xử lý hàng nghìn file. Thiết kế cần cân bằng độ đầy đủ với thời gian phản hồi.

### 21.1. Cache theo dependency

Có thể cache:

- Token/AST theo file content hash.
- Semantic model theo AST và dependency version.
- Schema metadata theo version.
- Kết quả rule theo node hoặc project snapshot.

Khi file thay đổi, chỉ invalidation những kết quả phụ thuộc vào nội dung hoặc symbol liên quan.

### 21.2. Chạy song song

Các file độc lập có thể parse và chạy local rules song song. Những bước phụ thuộc project index cần chờ dữ liệu chung. Checker phải tránh chia sẻ mutable state không an toàn giữa worker.

### 21.3. Ưu tiên file đang mở

Trong IDE, file đang mở có thể được kiểm tra trước để phản hồi nhanh. Phân tích toàn project có thể chạy nền và cập nhật diagnostics sau.

### 21.4. Giới hạn diagnostics

Một lỗi parser có thể gây nhiều lỗi dây chuyền. Checker có thể giới hạn số diagnostics hoặc dùng error recovery để tránh output quá lớn. Khi đạt giới hạn, cần báo rằng kết quả bị cắt theo chính sách, không khiến người dùng hiểu nhầm chỉ có từng đó vấn đề.

### 21.5. Đo thời gian

Checker có thể cung cấp thống kê theo pha:

~~~text
Project discovery:       45 ms
Dependency loading:     120 ms
Parsing:                310 ms
Semantic analysis:      420 ms
Domain validation:      180 ms
Total:                1,075 ms
~~~

Thống kê giúp xác định bottleneck mà không phải suy đoán. Không nên bật profiling chi tiết mặc định nếu nó làm output hoặc hiệu năng bị ảnh hưởng đáng kể.

## 22. Chất lượng và độ tin cậy của checker

Checker cũng là phần mềm cần được kiểm thử. Kết quả pass không có nghĩa mọi lỗi có thể xảy ra đều đã được phát hiện; nó chỉ có nghĩa các rule được chạy không tìm thấy vi phạm theo dữ liệu và cấu hình hiện có.

### 22.1. Unit tests cho rule

Mỗi rule nên có:

- Ví dụ source hợp lệ không tạo diagnostic.
- Ví dụ source vi phạm tạo đúng diagnostic.
- Vị trí diagnostic chính xác.
- Severity và rule ID đúng.
- Trường hợp biên.

### 22.2. Golden diagnostics

Có thể lưu output diagnostics mong đợi và so sánh với kết quả thực tế. Golden test giúp phát hiện thay đổi message, range và ordering.

### 22.3. Integration tests

Test toàn project với module, schema và dependency thật để xác nhận các pha phối hợp đúng.

### 22.4. Regression tests

Mỗi bug đã sửa nên có input tái hiện để ngăn lỗi quay lại.

### 22.5. Negative tests

Test các input lỗi như file hỏng, URI không hợp lệ, dependency thiếu, config sai kiểu hoặc plugin không tương thích. Checker không nên crash hoặc trả pass giả khi gặp đầu vào bất thường.

### 22.6. Kiểm thử output format

JSON/SARIF phải parse được theo schema. Exit code, stdout/stderr và thứ tự diagnostics cần ổn định theo hợp đồng CLI.

## 23. API để nhúng checker

Ngoài CLI, checker có thể cung cấp API để ứng dụng chủ tích hợp.

Ví dụ mã giả:

~~~typescript
const checker = createChecker({
  configPath: "dsl-check.yml",
  failOn: "error"
});

const result = await checker.checkProject("./workspace");

for (const diagnostic of result.diagnostics) {
  console.log(formatDiagnostic(diagnostic));
}

if (!result.passed) {
  process.exitCode = 1;
}
~~~

API nên xác định:

- Cách tạo và giải phóng checker instance.
- Cấu hình và dependency resolver.
- Kiểu input: file, text snapshot hoặc project.
- Cách nhận cancellation/progress.
- Cấu trúc diagnostic ổn định.
- Cách đăng ký custom rules.
- Quy tắc thread-safety và concurrent calls.
- Version compatibility.

### 23.1. Không để API phụ thuộc CLI

CLI nên là một adapter gọi checker engine. Nếu logic rule nằm trong command handler, IDE hoặc ứng dụng nhúng sẽ khó tái sử dụng và có nguy cơ cho kết quả khác.

### 23.2. Immutable project snapshot

API có thể nhận project snapshot bất biến để một lần check nhìn thấy cùng một trạng thái source và config. Điều này tránh việc file thay đổi giữa các pha làm kết quả không nhất quán.

## 24. Quy trình sử dụng checker trong dự án

Một quy trình làm việc phổ biến:

1. Cài đặt hoặc chọn phiên bản checker.
2. Tạo file cấu hình project và bật các rule cần thiết.
3. Chạy checker trên file đang chỉnh sửa.
4. Sửa errors và xem xét warnings.
5. Dùng quick fix cho các thay đổi an toàn.
6. Chạy checker trên toàn project trước khi commit.
7. Chạy cùng policy trong CI.
8. Lưu machine-readable report khi cần code scanning.
9. Review suppression và baseline định kỳ.
10. Nâng phiên bản checker có kiểm soát và xem xét diagnostics mới.

Ví dụ:

~~~text
dsl check src/rules/
dsl check . --format json --fail-on error
dsl check . --format sarif --fail-on warning
~~~

Lệnh cụ thể phụ thuộc công cụ. Điều quan trọng là developer và CI dùng cùng cấu hình, cùng dependency version và cùng ngưỡng chặn.

## 25. Ví dụ tổng hợp: checker cho DSL workflow

Xét source:

~~~text
workflow "release" {
    step build {
        command = "build.sh"
    }

    step test {
        command = "test.sh"
        after build
    }

    step deploy {
        command = "deploy.sh"
        after publish
        retries = 0
    }
}
~~~

Checker có thể chạy các lớp:

1. Parser xác nhận cấu trúc block và thuộc tính.
2. Name resolution xác nhận build, test, deploy và tham chiếu publish.
3. Type checking xác nhận command là String và retries là Integer.
4. Domain validation phát hiện step publish không tồn tại.
5. Domain validation phát hiện retries phải lớn hơn hoặc bằng 1.
6. Graph validation kiểm tra dependency cycle sau khi các reference hợp lệ.

Diagnostics có thể là:

~~~text
release.dsl:15:15
error WF102: Step 'publish' is not declared in workflow 'release'.

release.dsl:16:19
error WF205: 'retries' must be at least 1.
Current value: 0.
~~~

Checker không nên báo cycle dựa trên graph chưa resolve đầy đủ nếu missing reference khiến cấu trúc graph không đáng tin cậy. Có thể tiếp tục những kiểm tra độc lập và bỏ qua rule phụ thuộc dữ liệu chưa hợp lệ.

## 26. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra cú pháp | Lỗi tên, kiểu và nghiệp vụ lọt qua | Bổ sung semantic và domain validation |
| Trộn warning với error | Người dùng khó biết lỗi nào chặn build | Định nghĩa severity và fail threshold |
| Rule không có ID ổn định | Config và CI dễ hỏng khi message đổi | Dùng rule code ổn định |
| Chỉ có output text | IDE/CI khó tích hợp | Cung cấp JSON hoặc SARIF có schema |
| Log trộn vào JSON stdout | Machine consumer không parse được | Tách stdout và stderr |
| Kiểm tra một file mà bỏ qua project context | Bỏ sót dependency hoặc reference | Có chế độ project check |
| Cache không invalidation | Kết quả cũ được dùng sau khi source đổi | Theo dõi dependency của từng kết quả |
| Chạy mọi rule sau lỗi parser | Sinh nhiều diagnostics sai lệch | Dùng recovery và dependency gating |
| Autofix thay đổi semantics | Có thể làm hỏng chương trình | Phân loại safe/unsafe và kiểm tra lại |
| Suppression quá rộng | Lỗi mới bị che khuất | Giới hạn scope, yêu cầu reason và review |
| Plugin không được kiểm soát | Checker có thể chạy mã không tin cậy | Version pinning và trust policy |
| CI dùng version không cố định | Kết quả thay đổi theo thời gian | Pin checker và dependency |
| Baseline không được quản lý | Technical debt tồn tại vô thời hạn | Fingerprint, owner và quy trình review |
| Báo pass khi thiếu dependency | Kết quả tạo cảm giác an toàn giả | Báo incomplete hoặc lỗi môi trường |

## 27. Quy trình thiết kế một checker cho DSL

Khi xây dựng checker mới, có thể thực hiện theo các bước:

1. **Xác định đối tượng kiểm tra:** file đơn, project, workspace hay artifact.
2. **Liệt kê nhóm quy tắc:** lexical, syntax, name, type, domain, policy và style.
3. **Xác định dữ liệu cần:** AST, symbol table, type model, schema, dependency graph hoặc environment metadata.
4. **Thiết kế pipeline:** sắp xếp pha theo dependency và cho phép bỏ qua rule không đủ dữ liệu.
5. **Định nghĩa diagnostic schema:** rule ID, severity, message, source range và related information.
6. **Xây rule registry:** metadata, cấu hình, dependency và lifecycle của mỗi rule.
7. **Thiết kế giao diện:** CLI, API, Language Server hoặc CI adapter.
8. **Quy định exit code và output format:** giữ contract ổn định cho automation.
9. **Thiết kế suppression và autofix:** giới hạn phạm vi và bảo đảm khả năng truy vết.
10. **Tích hợp project/dependency resolver:** hỗ trợ multi-file và version pinning.
11. **Tối ưu incremental và parallel analysis:** chỉ khi workload yêu cầu.
12. **Kiểm thử:** unit, golden diagnostics, integration, regression và failure cases.
13. **Tài liệu hóa policy:** giải thích rule, severity, cấu hình và cách xử lý findings.

Một checker nên bắt đầu với nhóm rule thiết yếu, có giá trị rõ ràng cho người dùng. Có thể mở rộng rule set khi đã có diagnostic contract, cấu hình và cách kiểm thử ổn định.

## 28. Tiêu chí của một trình kiểm tra tốt

Một checker tốt đưa ra kết quả có thể hành động: chỉ đúng vị trí, giải thích quy tắc bị vi phạm, phân biệt lỗi với cảnh báo và cho biết những phần nào chưa thể kiểm tra vì thiếu dữ liệu. Nó chạy nhất quán trong terminal, IDE và CI, đồng thời không biến một kết quả chưa đầy đủ thành trạng thái pass.

Các câu hỏi quan trọng:

- Checker kiểm tra source, project hay artifact?
- Những lớp kiểm tra nào được chạy?
- Rule nào cần schema, dependency hoặc metadata bên ngoài?
- Diagnostics có rule ID và source range ổn định không?
- Severity và exit code được định nghĩa thế nào?
- CLI có output machine-readable không?
- IDE và CI có dùng chung rule engine không?
- Incremental checking có invalidation cache chính xác không?
- Autofix và suppression có kiểm soát được không?
- Plugin và custom rule có trust/version policy không?
- Khi dependency không sẵn sàng, checker báo incomplete hay pass?
- Có thể tái hiện kết quả bằng phiên bản checker và cấu hình đã pin không?

Trình kiểm tra là lớp công cụ giúp người dùng DSL hiểu source của họ có thỏa cú pháp, ngữ nghĩa và policy hay không trước khi đưa vào sử dụng. Khi pipeline, rule, diagnostics, cấu hình và cách tích hợp được thiết kế rõ ràng, checker trở thành một phần thống nhất của quy trình phát triển, review và triển khai DSL.
