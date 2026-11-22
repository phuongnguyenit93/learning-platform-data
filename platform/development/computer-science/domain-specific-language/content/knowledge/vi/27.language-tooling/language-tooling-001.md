# Giao diện dòng lệnh

**Giao diện dòng lệnh** (*Command-Line Interface – CLI*) là cách người dùng tương tác với chương trình bằng cách nhập lệnh và tham số trong terminal hoặc shell. Với bộ công cụ DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), CLI cung cấp cách thống nhất để tạo project, kiểm tra cú pháp, phân tích ngữ nghĩa, định dạng mã, sinh mã, build, chạy chương trình và quản lý dependency.

Ví dụ:

~~~bash
dsl init my-service
dsl check project.dslproj
dsl format src/
dsl generate --target typescript project.dslproj
dsl run examples/hello.dsl
~~~

CLI có thể chạy trên máy phát triển, trong script, CI/CD, container hoặc máy chủ không có giao diện đồ họa. Một CLI tốt cần cú pháp nhất quán, thông báo dễ hiểu, exit code có ý nghĩa, output ổn định và hành vi có thể tự động hóa.

## 1. Vai trò của CLI trong bộ công cụ DSL

Một DSL thường có nhiều thành phần: lexer, parser, semantic analyzer, validator, formatter, compiler, runtime, package manager và language server. CLI cung cấp điểm truy cập để người dùng gọi những chức năng này.

Ví dụ, một project mô tả hạ tầng có thể gồm:

~~~text
infra/
├── project.dslproj
├── modules/
│   ├── network.dsl
│   └── database.dsl
└── services/
    └── api.dsl
~~~

Người dùng có thể gọi CLI để kiểm tra toàn project, xem dependency graph, sinh cấu hình cho nền tảng đích hoặc chạy mô phỏng.

### 1.1. CLI và giao diện đồ họa

GUI cung cấp nút bấm, menu và cửa sổ trực quan. CLI cung cấp lệnh có thể lưu, sao chép, ghép chuỗi và chạy tự động.

| Tiêu chí | CLI | GUI |
|---|---|---|
| Tương tác | Nhập lệnh và tham số | Chuột, bàn phím, menu |
| Tự động hóa | Thuận tiện trong script và CI | Thường cần automation riêng |
| Khả năng lặp lại | Lưu được chính xác lệnh đã chạy | Khó tái hiện chuỗi thao tác dài |
| Môi trường máy chủ | Thường phù hợp | Có thể cần display server |
| Khám phá tính năng | Help, completion, tài liệu | Menu và giao diện trực quan |
| Phản hồi | Text, stream, exit code | Thành phần trực quan, notification |

CLI và GUI nên dùng chung compiler core hoặc application services. Nếu mỗi giao diện tự triển khai parser và quy tắc nghiệp vụ riêng, kết quả có thể không nhất quán.

### 1.2. Nhóm người dùng

CLI của DSL có thể phục vụ người viết DSL, người phát triển module, kỹ sư vận hành, người bảo trì, người phát triển tooling và hệ thống CI. Các nhóm có nhu cầu khác nhau, nhưng đều cần biết command làm gì, nhận đầu vào nào và có thể thay đổi trạng thái nào.

## 2. Cấu trúc cơ bản của command

Một command thường có dạng:

~~~text
program [global-options] <subcommand> [command-options] [arguments]
~~~

Ví dụ:

~~~bash
dsl --verbose check --format json project.dslproj
~~~

- `dsl` là tên chương trình.
- `--verbose` là global option.
- `check` là subcommand.
- `--format json` là command option.
- `project.dslproj` là positional argument.

Một CLI cần quy định rõ global option có thể đứng trước hay sau subcommand. Không nên để cùng một option được parse khác nhau tùy vị trí mà không có tài liệu.

### 2.1. Program name

Tên chương trình nên ngắn, dễ gõ và nhất quán giữa binary, package, tài liệu, thông báo lỗi và shell completion.

### 2.2. Subcommand

Subcommand biểu diễn một hành động:

~~~text
dsl init
dsl check
dsl format
dsl build
dsl generate
dsl run
~~~

Subcommand giúp mở rộng công cụ mà không cần tạo một executable riêng cho từng chức năng.

### 2.3. Positional argument

Positional argument thường là file, thư mục, tên module hoặc resource:

~~~bash
dsl check src/main.dsl
dsl generate project.dslproj
dsl module add acme.logging
~~~

### 2.4. Option

Option điều chỉnh cách command hoạt động:

~~~bash
dsl check --strict --format json project.dslproj
~~~

Trong ví dụ, `--strict` bật policy nghiêm ngặt và `--format json` chọn định dạng diagnostics.

## 3. Thiết kế command và subcommand

Khi CLI có nhiều chức năng, nên tổ chức command theo nhóm:

~~~text
dsl
├── init
├── check
├── format
├── build
├── generate
├── run
├── module
│   ├── add
│   ├── remove
│   └── list
├── schema
│   ├── validate
│   ├── diff
│   └── migrate
└── cache
    ├── inspect
    └── clean
~~~

### 3.1. Một command có một mục đích rõ

`dsl format` định dạng mã; `dsl check` kiểm tra mã; `dsl build` tạo artifact. Nếu một command vừa format, vừa sửa schema, vừa deploy thì khó dự đoán tác động và khó sử dụng trong script.

### 3.2. Dùng tên nhất quán

| Command | Ý nghĩa |
|---|---|
| `init` | Tạo cấu trúc ban đầu |
| `check` | Kiểm tra tính hợp lệ |
| `format` | Định dạng mã |
| `build` | Xây dựng artifact |
| `generate` | Sinh mã hoặc tài nguyên |
| `run` | Chạy chương trình |
| `inspect` | Hiển thị thông tin |
| `list` | Liệt kê đối tượng |
| `add` | Thêm dependency hoặc thành phần |
| `remove` | Gỡ thành phần |
| `migrate` | Chuyển đổi schema hoặc dữ liệu |

### 3.3. Nhóm theo miền

Khi số lượng command lớn, có thể nhóm theo miền như `module`, `schema`, `cache` hoặc `plugin`. Nhóm giúp người dùng khám phá chức năng và giảm xung đột tên.

### 3.4. Alias

Alias ngắn có thể tiện, ví dụ `dsl fmt` cho `dsl format`. Tuy nhiên, quá nhiều alias làm help khó hiểu. Alias cần được ghi nhận rõ và không nên thay đổi ý nghĩa giữa các phiên bản.

### 3.5. Command mặc định

Nếu người dùng chỉ chạy `dsl`, công cụ có thể in help hoặc mở interactive mode. Hành vi này cần được quy định rõ; CLI dùng trong script thường nên có kết quả xác định và không chờ input bất ngờ.

## 4. Positional arguments và đường dẫn

Positional arguments phù hợp với các giá trị cốt lõi của command:

~~~bash
dsl check project.dslproj
dsl format src/
dsl module add acme.logging
~~~

### 4.1. Bắt buộc và tùy chọn

Usage có thể thể hiện:

~~~text
dsl check [options] <file-or-project>
dsl format [options] <paths...>
~~~

Dấu ngoặc nhọn thường biểu thị đối số bắt buộc; dấu ngoặc vuông biểu thị phần tùy chọn. Quy ước cần nhất quán trong help.

### 4.2. Đường dẫn có khoảng trắng

Shell có quy tắc quoting riêng. Ví dụ PowerShell:

~~~powershell
dsl check "Computer Science Domain Specific Language/project.dslproj"
~~~

CLI nhận danh sách argument mà runtime cung cấp; không nên tự tách một chuỗi command theo dấu cách.

### 4.3. Đường dẫn tương đối và tuyệt đối

CLI cần quy định đường dẫn được tính từ working directory hay project root. Một chính sách phổ biến:

- Đường dẫn người dùng nhập được tính từ working directory.
- Đường dẫn nội bộ trong project được resolve theo project root.
- Output path được chuẩn hóa và hiển thị rõ.

Thông báo lỗi nên cho biết đường dẫn đã resolve để người dùng xác định đúng file.

### 4.4. Glob và nhiều file

Một số shell tự mở rộng pattern như `src/**/*.dsl`, một số môi trường không làm điều đó giống nhau. Nếu CLI tự hỗ trợ glob, cần quy định thư mục con, pattern không khớp, file trùng và thứ tự xử lý.

### 4.5. Stdin

Một số command dùng dấu `-` để đọc từ standard input:

~~~bash
cat config.dsl | dsl check -
~~~

CLI cần công bố command nào hỗ trợ stdin, encoding, giới hạn kích thước và cách xử lý input rỗng.

## 5. Options và flags

Option điều khiển cách command thực hiện. Hai dạng phổ biến là option có giá trị và boolean flag.

### 5.1. Option có giá trị

~~~bash
dsl build --target typescript --output dist/
~~~

`--target` nhận tên target; `--output` nhận đường dẫn.

### 5.2. Boolean flag

~~~bash
dsl check --strict
dsl format --no-write
~~~

Flag bật hoặc tắt một hành vi. Không nên dùng một flag cho nhiều ý nghĩa khác nhau, chẳng hạn vừa dry-run vừa chỉ in kết quả ra stdout.

### 5.3. Short option

~~~bash
dsl build -o dist -t java
~~~

Short option hữu ích cho thao tác thường xuyên, nhưng không nên tạo quá nhiều alias một ký tự khó nhớ.

### 5.4. Kiểu giá trị

Option có thể nhận string, integer, decimal, boolean, enum, đường dẫn, danh sách hoặc giá trị có đơn vị:

~~~bash
dsl check --min-severity warning
dsl run --timeout 30s
dsl build --jobs 4
~~~

Nếu giá trị không hợp lệ, CLI nên nêu option sai và liệt kê giá trị hợp lệ khi có thể.

### 5.5. Default

Help nên hiển thị các giá trị mặc định quan trọng:

~~~text
--target <name>       Target language (default: java)
--jobs <count>        Parallel jobs (default: processor count)
--format <format>     Output format: text, json (default: text)
~~~

Không nên giấu default có ảnh hưởng lớn đến kết quả build hoặc deploy.

### 5.6. Option lặp lại

Một option có thể xuất hiện nhiều lần:

~~~bash
dsl check --exclude generated/ --exclude vendor/ project.dslproj
~~~

CLI cần quy định các giá trị được cộng dồn, ghi đè hay gây lỗi khi lặp.

## 6. Global options và command options

Global options áp dụng cho nhiều command:

- `--help`
- `--version`
- `--verbose`
- `--quiet`
- `--config`
- `--no-color`
- `--log-level`

Command options chỉ có ý nghĩa trong một command:

- `check --strict`
- `format --write`
- `build --target`
- `generate --output`
- `run --timeout`

### 6.1. Tránh option mơ hồ

Nếu `--output` trong `build` là thư mục artifact nhưng trong `format` lại là file log, người dùng dễ nhầm. Có thể dùng tên cụ thể hơn hoặc giới hạn option theo command.

### 6.2. Thứ tự ưu tiên cấu hình

Một CLI có thể lấy cấu hình từ nhiều nguồn:

~~~text
Built-in defaults
       <
Project configuration
       <
Environment variables
       <
Command-line options
~~~

Nguồn ở bên phải thường ghi đè nguồn bên trái. CLI nên công bố thứ tự này và có thể cung cấp command inspect để xem cấu hình hiệu lực.

## 7. Parsing command line

Khi chương trình khởi động, runtime cung cấp danh sách argument đã được shell phân tách. CLI parser chuyển chúng thành cấu trúc dữ liệu để command handler sử dụng.

~~~text
Input:
  ["dsl", "check", "--strict", "--format", "json", "project.dslproj"]

Parsed:
  command = check
  strict = true
  format = json
  input = project.dslproj
~~~

### 7.1. Không parse bằng cách tách chuỗi

Không nên ghép command thành một chuỗi rồi tự tách theo dấu cách. Cách đó dễ lỗi với đường dẫn có khoảng trắng, dấu nháy và ký tự escape. Hãy dùng danh sách argument và parser có quy tắc rõ.

### 7.2. Unknown option

Nếu người dùng nhập:

~~~bash
dsl check --strcit project.dslproj
~~~

CLI nên báo `--strcit` không được nhận diện và có thể gợi ý `--strict` nếu đủ chắc chắn. Không nên tự thực thi command được đoán.

### 7.3. Missing value

Nếu người dùng nhập:

~~~bash
dsl build --target
~~~

CLI cần báo `--target` yêu cầu một giá trị. Không nên âm thầm dùng default vì có thể tạo artifact sai target.

### 7.4. Option xung đột

Nếu `--quiet` và `--verbose` không thể cùng bật, parser hoặc command validation cần báo xung đột. Hành vi khi một option lặp lại cũng phải được định nghĩa.

### 7.5. Parsing và validation

Parsing xác định cấu trúc đối số. Command vẫn cần kiểm tra quy tắc ngữ cảnh, ví dụ `--watch` chỉ dùng với `check` hoặc target phải thuộc danh sách backend được cài.

## 8. Help và usage

Help là một phần quan trọng của CLI vì người dùng thường khám phá công cụ ngay trong terminal.

~~~text
DSL Tool

Usage:
  dsl <command> [options]

Commands:
  init       Create a new DSL project
  check      Validate DSL source and project
  format     Format DSL files
  build      Compile a project
  generate   Generate target-language code
  run        Execute a DSL program
  module     Manage project modules

Global options:
  -h, --help       Show help
  -V, --version    Show version
  -v, --verbose    Show detailed output
      --no-color   Disable colored output
~~~

### 8.1. Usage line

Usage cần thể hiện thứ tự và dạng đối số:

~~~text
dsl check [options] <file-or-project>
~~~

### 8.2. Help tổng quát và help chi tiết

Help tổng quát liệt kê command và mô tả ngắn. Help chi tiết của từng command có thể giải thích mục đích, arguments, options, default, ví dụ, exit behavior và tác động lên file hoặc hệ thống.

### 8.3. Ví dụ có thể chạy

~~~bash
# Check the current project
dsl check project.dslproj

# Emit machine-readable diagnostics
dsl check --format json project.dslproj

# Verify formatting without writing changes
dsl format --check src/
~~~

### 8.4. Gợi ý command gần đúng

~~~text
Unknown command: chek
Did you mean: check?
Run 'dsl --help' to list available commands.
~~~

Gợi ý chỉ nên xuất hiện khi đủ chắc chắn.

## 9. stdin, stdout và stderr

CLI giao tiếp với shell qua ba luồng chuẩn:

- **stdin:** dữ liệu đầu vào từ bàn phím, pipe hoặc file chuyển hướng.
- **stdout:** kết quả chính của command.
- **stderr:** diagnostics, warning, progress và thông báo vận hành.

### 9.1. stdout dành cho kết quả

Với command xuất JSON, stdout nên chứa JSON hợp lệ:

~~~bash
dsl check --format json project.dslproj > diagnostics.json
~~~

Nếu CLI in progress trước JSON vào stdout, file kết quả không còn là JSON thuần.

### 9.2. stderr dành cho thông báo

Progress và log có thể gửi đến stderr để người dùng vẫn thấy thông tin trong terminal mà stdout giữ nguyên cho pipeline.

### 9.3. Pipe giữa command

~~~bash
dsl symbols --format json project.dslproj | jq '.symbols[] | .name'
~~~

Output máy đọc cần ổn định và có schema được tài liệu hóa.

### 9.4. Encoding và stdin

Nếu command đọc source từ stdin, cần quy định encoding, giới hạn kích thước, hành vi khi input rỗng và cách báo lỗi parse. Không nên đóng stream do caller quản lý nếu command được gọi qua API nhúng.

## 10. Exit codes

Exit code là số nguyên process trả về khi kết thúc. Shell và CI dùng nó để biết command thành công hay thất bại.

Quy ước phổ biến là `0` biểu thị thành công; giá trị khác `0` biểu thị lỗi hoặc command không hoàn thành theo yêu cầu.

### 10.1. Bảng exit code ví dụ

| Code | Ý nghĩa |
|---:|---|
| `0` | Thành công |
| `1` | Lỗi tổng quát hoặc validation thất bại |
| `2` | Cú pháp command hoặc đối số không hợp lệ |
| `3` | Không tìm thấy file/project |
| `4` | Dependency hoặc cấu hình không hợp lệ |
| `5` | Lỗi thực thi hoặc runtime |
| `130` | Bị hủy bởi Ctrl+C trên một số môi trường |

Đây là quy ước minh họa, không phải chuẩn bắt buộc. Mã đã được script sử dụng cần được giữ ổn định và tài liệu hóa.

### 10.2. Warning có làm command thất bại không?

Một policy thường gặp:

- Có error: exit code khác 0.
- Chỉ có warning: exit code 0, trừ khi bật `--warnings-as-errors`.
- Chỉ có information hoặc hint: exit code 0.

Ví dụ:

~~~bash
dsl check --warnings-as-errors project.dslproj
~~~

Severity của từng diagnostic khác với exit code tổng thể. Một lần chạy có thể phát nhiều diagnostics nhưng chỉ trả một exit code.

### 10.3. Hủy command

Khi người dùng nhấn Ctrl+C, CLI nên dừng có kiểm soát, giải phóng tài nguyên và trả mã hủy phù hợp. Process con không nên tiếp tục ghi artifact sau khi command cha đã kết thúc.

## 11. Diagnostics trong CLI

Diagnostics là thông báo có cấu trúc về lỗi, warning hoặc thông tin mà compiler phát hiện.

~~~text
src/service.dsl:12:18: error DSL-TYPE-0017:
property 'replicas' expects Integer, found String
  replicas = "three"
             ^^^^^^^
~~~

Một diagnostic tốt thường có file và vị trí, severity, mã lỗi ổn định, message dễ hiểu, related information và gợi ý sửa nếu an toàn.

### 11.1. Text output

Text phù hợp với người đọc trực tiếp trong terminal. Có thể dùng màu, caret và dòng nguồn để xác định vị trí.

### 11.2. JSON output

~~~json
{
  "diagnostics": [
    {
      "file": "src/service.dsl",
      "line": 12,
      "column": 18,
      "severity": "error",
      "code": "DSL-TYPE-0017",
      "message": "property 'replicas' expects Integer, found String"
    }
  ]
}
~~~

### 11.3. Các format

Một command có thể hỗ trợ:

~~~bash
dsl check --format text project.dslproj
dsl check --format json project.dslproj
dsl check --format sarif project.dslproj
~~~

Tên format phải được tài liệu hóa. Nếu format không hỗ trợ, CLI nên báo giá trị hợp lệ.

### 11.4. Không trộn log với JSON

Khi chọn JSON hoặc SARIF, dữ liệu máy đọc cần được xuất riêng trên stdout. Log và progress nên đi stderr hoặc bị tắt theo option.

## 12. Cấu hình CLI

Một CLI có thể nhận cấu hình từ nhiều nguồn để người dùng không phải lặp option trong mọi command.

~~~toml
[project]
name = "catalog"
source_roots = ["src"]

[compiler]
target = "typescript"
strict = true

[diagnostics]
warnings_as_errors = false
format = "text"
~~~

### 12.1. File cấu hình

CLI có thể tìm file cấu hình ở project root hoặc đường dẫn chuẩn. Help cần nói rõ tên file, vị trí và quy tắc tìm kiếm.

### 12.2. Chỉ định config

~~~bash
dsl check --config ci.dslconfig project.dslproj
~~~

Option này hữu ích khi CI cần policy riêng hoặc người dùng kiểm tra nhiều cấu hình.

### 12.3. Environment variables

~~~bash
DSL_TARGET=java dsl build project.dslproj
~~~

Tên biến nên có prefix thống nhất. Không nên để secret xuất hiện trong help, debug log hoặc command echo.

### 12.4. Xem cấu hình hiệu lực

Khi nhiều nguồn cùng cung cấp giá trị, command inspect config có thể giúp người dùng biết giá trị nào được chọn và nguồn nào đã đặt nó.

## 13. Working directory và project discovery

CLI cần xác định project context trước khi thực hiện một số command.

~~~text
Current directory
       |
       v
Look for project.dslproj
       |
       +-- found --> use this project
       |
       +-- not found --> inspect parent directory
~~~

### 13.1. Explicit project path

~~~bash
dsl check --project path/to/project.dslproj
~~~

Đường dẫn rõ ràng giúp script không phụ thuộc vị trí chạy.

### 13.2. Nhiều project trong một thư mục

Nếu thư mục có nhiều file project, CLI nên yêu cầu chỉ định file hoặc có quy tắc chọn được công bố. Không nên chọn ngẫu nhiên file đầu tiên từ filesystem.

### 13.3. Symlink và canonical path

Khi so sánh đường dẫn, cache hoặc kiểm tra project boundary, cần cân nhắc symlink và canonical path. Cùng một thư mục có thể được truy cập qua nhiều đường dẫn.

## 14. Các command phổ biến của DSL CLI

### 14.1. init

~~~bash
dsl init my-service
~~~

Command có thể tạo file project, thư mục nguồn, ví dụ và cấu hình mặc định. Nếu thư mục đã tồn tại, CLI cần hỏi trước khi ghi đè hoặc yêu cầu flag xác nhận.

### 14.2. check

~~~bash
dsl check --strict --format json project.dslproj
~~~

Command kiểm tra cú pháp, name resolution, type checking và domain rules. Thông thường nó không thay đổi source.

### 14.3. format

~~~bash
dsl format --write src/
dsl format --check src/
~~~

`--write` cập nhật file; `--check` chỉ xác định file đã đúng format chưa và có thể trả exit code khác 0 nếu cần format.

### 14.4. build

~~~bash
dsl build --target java --output build/ project.dslproj
~~~

Command cần nêu rõ artifact được ghi ở đâu, có xóa output cũ không và build có dùng cache hay không.

### 14.5. generate

~~~bash
dsl generate --target typescript --output generated/ schema.dsl
~~~

Generator cần xử lý conflict, import, source mapping và target version.

### 14.6. run

~~~bash
dsl run examples/hello.dsl
~~~

Command có thể hỗ trợ input, timeout, environment hoặc arguments truyền cho chương trình.

### 14.7. inspect

~~~bash
dsl inspect symbols project.dslproj
dsl inspect ast src/main.dsl
dsl inspect dependencies project.dslproj
~~~

Các lệnh inspect hữu ích khi phát triển DSL hoặc tìm nguyên nhân lỗi.

## 15. Dry-run và xác nhận tác động

Command có thể thay đổi file hoặc hệ thống cần cung cấp cách xem trước tác động.

~~~bash
dsl generate --dry-run project.dslproj
~~~

Dry-run có thể hiển thị file sẽ được tạo, cập nhật, xóa, migration sẽ chạy hoặc dependency sẽ được thêm.

### 15.1. Dry-run không nên tạo tác dụng phụ

Nếu command ghi file tạm, cập nhật cache dùng chung hoặc gọi API từ xa thì cần công bố. Dry-run nên tránh thay đổi có ý nghĩa mà người dùng không mong đợi.

### 15.2. Xác nhận thao tác nguy hiểm

~~~bash
dsl clean --all
~~~

Command xóa dữ liệu có thể yêu cầu xác nhận. Trong CI không có terminal tương tác, có thể cần flag rõ:

~~~bash
dsl clean --all --yes
~~~

`--yes` bỏ qua bước xác nhận nên cần được dùng có chủ ý.

### 15.3. Idempotency

Một command idempotent có thể chạy lại nhiều lần mà trạng thái cuối không thay đổi thêm sau lần đầu. `format`, `check` hoặc đồng bộ cấu hình có thể hướng tới tính chất này. Với command tạo resource hoặc migration, cần xác định hành vi khi chạy lại.

## 16. Interactive và non-interactive mode

Một command có thể hỏi người dùng:

~~~text
Create project in ./my-service? [Y/n]
~~~

Interactive mode hữu ích cho người mới nhưng không phù hợp với mọi script.

### 16.1. Non-interactive mode

~~~bash
dsl init my-service --non-interactive --template service
~~~

Trong chế độ này, mọi giá trị cần thiết phải được cung cấp qua argument, option, config hoặc default đã công bố.

### 16.2. Phát hiện terminal

CLI có thể kiểm tra stdin/stdout có phải terminal tương tác không. Nếu output được pipe hoặc redirect, nên tránh prompt và animation.

### 16.3. EOF và hủy prompt

Nếu người dùng gửi EOF hoặc hủy prompt, CLI cần kết thúc rõ ràng và không coi đó là xác nhận đồng ý.

## 17. Progress, logging và verbosity

Command dài như build hoặc migrate cần thông báo tiến độ:

~~~text
[1/4] Parsing modules...
[2/4] Resolving dependencies...
[3/4] Generating Java sources...
[4/4] Writing artifacts...
Build completed in 2.4s
~~~

### 17.1. Quiet mode

`--quiet` giảm output thông thường, phù hợp script chỉ quan tâm exit code hoặc artifact.

### 17.2. Verbose mode

`--verbose` hiển thị thêm project root, target, dependency resolution và cache decisions.

### 17.3. Debug logging

`--log-level debug` có thể hiển thị chi tiết phục vụ điều tra. Debug log cần tránh in secret hoặc dữ liệu nhạy cảm.

### 17.4. Progress trên terminal

Progress bar hoặc spinner có thể dùng ký tự điều khiển terminal. Khi output được redirect, CLI nên chuyển sang log dòng thông thường hoặc tắt animation.

## 18. Shell completion

Shell completion giúp người dùng khám phá command, option, file hoặc module khi nhấn Tab.

~~~text
dsl bu<Tab>
build
~~~

Completion có thể đề xuất subcommand, option, giá trị enum, project file, DSL source, module hoặc target backend.

### 18.1. Completion phải nhanh

Completion được gọi thường xuyên. Không nên chạy full semantic analysis hoặc truy cập mạng chậm cho mỗi lần Tab.

### 18.2. Completion theo ngữ cảnh

Sau:

~~~bash
dsl build --target <Tab>
~~~

CLI có thể đề xuất các target được cài như `java` hoặc `typescript`.

### 18.3. Cài đặt completion

Tool có thể cung cấp command tạo script completion cho Bash, Zsh, Fish hoặc PowerShell. Cần chỉ rõ file được tạo và cách nạp script.

## 19. CLI và tự động hóa

CLI được dùng nhiều trong script và CI/CD. Những đặc điểm quan trọng là exit code, output ổn định, không prompt bất ngờ và đường dẫn rõ ràng.

~~~bash
dsl format --check src/
dsl check --strict --format sarif project.dslproj
dsl build --target java project.dslproj
~~~

Nếu một bước thất bại, pipeline thường dừng hoặc xử lý theo exit code.

### 19.1. Machine-readable output

JSON hoặc SARIF giúp công cụ khác phân tích diagnostics mà không phải parse văn bản tự do.

### 19.2. Không phụ thuộc màu sắc

Script không nên cần đọc màu ANSI để xác định severity. Hãy dùng structured output hoặc exit code.

### 19.3. Stable output contract

Nếu CI phụ thuộc JSON field hoặc exit code, thay đổi format cần được quản lý như thay đổi API. Nên có version hoặc quy tắc tương thích cho output schema.

### 19.4. Không prompt trong CI

Command chạy trong môi trường non-interactive không nên chờ người dùng nhập câu trả lời vô thời hạn. Có thể dùng `--non-interactive` hoặc tự phát hiện môi trường.

### 19.5. Reproducible command

Để build có thể tái hiện, cần cố định compiler version, dependency version, target và cấu hình. CLI có thể cung cấp `--version`, lockfile và chế độ in effective configuration.

## 20. Ghép command trong shell

Shell có cú pháp riêng để kết hợp command. CLI cần trả exit code đúng để những cú pháp đó hoạt động.

Ví dụ POSIX shell:

~~~bash
dsl check project.dslproj && dsl build project.dslproj
~~~

Lệnh build chỉ chạy nếu check thành công.

~~~bash
dsl check project.dslproj || echo "DSL validation failed"
~~~

Thông báo thay thế được chạy nếu check thất bại.

Trong PowerShell, có cơ chế xử lý native process exit code riêng. Tài liệu CLI không nên giả định mọi shell dùng cú pháp và biến trạng thái giống nhau.

### 20.1. Pipeline exit code

Khi output được pipe, shell có thể lấy exit code của command cuối hoặc có cơ chế `pipefail` tùy shell. Người viết script cần biết quy tắc này.

### 20.2. Broken pipe

Nếu consumer đóng pipe sớm, producer có thể gặp broken pipe. CLI nên xử lý phù hợp, tránh in stack trace dài cho một thao tác pipe bình thường.

## 21. Bảo mật khi thiết kế CLI

CLI có thể đọc file, chạy plugin, gọi network, ghi artifact và thực thi chương trình. Cần kiểm soát đầu vào và quyền truy cập.

### 21.1. Không ghép chuỗi command tùy tiện

Nếu CLI gọi process con, không nên nối chuỗi từ input người dùng rồi đưa cho shell thực thi. Hãy truyền executable và argument riêng qua API process phù hợp để tránh command injection.

### 21.2. Validate path

Một project có thể chứa đường dẫn tương đối:

~~~text
output = "../../outside/generated"
~~~

Nếu command chỉ được phép ghi trong project root, cần resolve canonical path và kiểm tra boundary trước khi ghi. Kiểm tra chuỗi `../` đơn giản có thể không đủ khi có symlink.

### 21.3. Secret handling

Không đưa credential vào help, log, exception hoặc command echo. Ưu tiên secret store, environment injection an toàn hoặc file có quyền truy cập phù hợp.

### 21.4. Plugin execution

Nếu CLI tải hoặc chạy plugin, cần kiểm tra nguồn, version và quyền thực thi. Không nên tự chạy mã plugin từ project chưa tin cậy mà không có policy rõ.

### 21.5. File overwrite

Command ghi file cần xử lý trường hợp file đã tồn tại. Có thể yêu cầu `--force` hoặc xác nhận tương tác; không nên âm thầm ghi đè dữ liệu quan trọng.

### 21.6. Network access

Command tải dependency hoặc publish artifact cần hiển thị nguồn đích, xử lý TLS đúng và không in token. Cần phân biệt rõ dry-run và thực thi.

## 22. Cross-platform CLI

Một công cụ DSL có thể chạy trên Windows, Linux và macOS. CLI cần tránh giả định chỉ có một shell hoặc một kiểu đường dẫn.

### 22.1. Path separator

Windows thường dùng dấu gạch chéo ngược trong đường dẫn native; Unix thường dùng dấu gạch chéo xuôi. Runtime path API nên được dùng để thao tác file, còn module specifier của target language có quy tắc riêng.

### 22.2. Case sensitivity

Một số filesystem phân biệt chữ hoa/thường, một số không. CLI cần tránh tạo hai file chỉ khác case nếu muốn project di chuyển được giữa nền tảng.

### 22.3. Encoding

Source DSL, config và output cần có quy tắc encoding rõ, thường là UTF-8. CLI nên xử lý tên file và nội dung Unicode đúng.

### 22.4. Terminal capabilities

Không phải terminal nào cũng hỗ trợ ANSI color, cursor movement hoặc Unicode glyph giống nhau. Cung cấp `--no-color` và tránh phụ thuộc vào ký tự trang trí để truyền đạt trạng thái.

### 22.5. Signal và process

Ctrl+C, termination signal và process tree có khác biệt giữa nền tảng. CLI nên có cơ chế cancellation và cleanup phù hợp.

## 23. CLI và quản lý phiên bản

CLI là giao diện công khai. Script hoặc người dùng có thể phụ thuộc vào command, option, output và exit code, vì vậy các thành phần này cần được quản lý ổn định.

### 23.1. Version command

~~~bash
dsl --version
~~~

Có thể hiển thị:

~~~text
dsl 2.4.1
compiler 2.4.1
runtime 2.3.0
target plugins: java 1.8, typescript 1.5
~~~

### 23.2. Deprecation

Nếu đổi tên command hoặc option, nên có giai đoạn cảnh báo:

~~~text
Option --old-target is deprecated; use --target.
It will be removed in a future major release.
~~~

### 23.3. Backward-compatible changes

Thêm command mới thường ít rủi ro hơn đổi nghĩa command cũ. Thay đổi default, exit code, JSON schema hoặc cách resolve path có thể phá script dù command line vẫn chạy.

### 23.4. Help theo version

Help cần tương ứng với binary đang chạy. Không nên hiển thị option chỉ tồn tại ở phiên bản mới hơn nếu binary hiện tại chưa hỗ trợ.

## 24. Kiến trúc nội bộ cho CLI

CLI nên là lớp giao tiếp mỏng, gọi các service dùng chung với IDE hoặc API khác.

~~~text
Process entry point
       |
       v
Argument parser
       |
       v
Command dispatcher
       |
       v
Command handler
       |
       v
Application services
       |
       +--> Parser
       +--> Semantic analyzer
       +--> Formatter
       +--> Compiler
       +--> Runtime
       +--> Dependency resolver
       |
       v
Output renderer and exit policy
~~~

### 24.1. Argument parser

Phân tích command line, kiểm tra kiểu đối số và tạo command request.

### 24.2. Command dispatcher

Chọn handler tương ứng với subcommand.

### 24.3. Command handler

Điều phối nghiệp vụ của command nhưng không nên chứa toàn bộ parser/compiler logic.

### 24.4. Application service

Service có thể được tái sử dụng bởi CLI, IDE, GUI hoặc server. Ví dụ `ProjectCheckService` thực hiện kiểm tra project; CLI chỉ quyết định cách nhận input và render diagnostics.

### 24.5. Output renderer

Renderer chuyển kết quả thành text, JSON hoặc SARIF. Renderer không nên làm thay đổi kết quả semantic.

### 24.6. Exit policy

Exit policy ánh xạ kết quả nghiệp vụ thành exit code. Ví dụ, diagnostics có error làm command `check` thất bại; command `inspect` có thể thành công nếu chỉ hiển thị symbol.

## 25. Ví dụ thiết kế command check

Usage:

~~~text
dsl check [options] <file-or-project>

Options:
  --strict                 Treat selected warnings as errors
  --warnings-as-errors     Fail when any warning is reported
  --format <text|json>     Diagnostic output format
  --exclude <path>         Exclude a path; may be repeated
  --config <file>          Use a specific configuration file
  --quiet                  Suppress non-essential messages
  --verbose                Print analysis details
~~~

Ví dụ:

~~~bash
dsl check --strict --format text project.dslproj
~~~

Quy trình nội bộ:

1. Parse arguments.
2. Resolve project path.
3. Load configuration.
4. Discover source files.
5. Parse từng file.
6. Build symbol index và dependency graph.
7. Chạy semantic analysis và domain validation.
8. Thu thập diagnostics.
9. Render diagnostics theo format.
10. Tính exit code theo severity và policy.

### 25.1. Kết quả text

~~~text
Checking project: shop

src/order.dsl:18:14: error DSL-TYPE-0017:
expected Money, found String

src/legacy.dsl:4:1: warning DSL-DEPR-0003:
property 'legacyMode' is deprecated

1 error, 1 warning
Check failed.
~~~

### 25.2. Kết quả JSON

~~~json
{
  "project": "shop",
  "success": false,
  "diagnostics": [
    {
      "file": "src/order.dsl",
      "line": 18,
      "column": 14,
      "severity": "error",
      "code": "DSL-TYPE-0017",
      "message": "expected Money, found String"
    }
  ],
  "summary": {
    "errors": 1,
    "warnings": 1
  }
}
~~~

Nếu policy quy định error làm check thất bại, command trả mã khác 0. Warning có thể không làm thất bại, trừ khi `--warnings-as-errors` được bật.

## 26. Ví dụ thiết kế command generate

~~~text
dsl generate [options] <input>

Options:
  --target <name>       Target language
  --output <directory> Output directory
  --dry-run             Show planned changes without writing
  --force               Overwrite generated files
  --clean               Remove stale generated files
~~~

Ví dụ:

~~~bash
dsl generate --target typescript --output generated/ project.dslproj
~~~

Command cần xác định file nào được tạo, cập nhật hoặc xóa; cách xử lý file do người dùng chỉnh sửa; cách xử lý import conflict; source mapping và target version.

`--clean` và `--force` có tác động khác nhau. `--force` thường cho phép ghi đè output đã tồn tại; `--clean` có thể xóa output không còn được sinh. Help cần mô tả rõ để tránh mất dữ liệu.

## 27. Ví dụ thiết kế command run

Command run cần phân biệt option của CLI với đối số truyền cho chương trình DSL. Một cú pháp phổ biến dùng dấu phân cách `--`:

~~~bash
dsl run examples/report.dsl -- --month 11 --format csv
~~~

Phần trước dấu phân cách thuộc CLI; phần sau được truyền cho chương trình được chạy.

Command có thể hỗ trợ timeout, environment, input, tracing hoặc profiling. Nếu chương trình DSL có thể thực thi mã hoặc truy cập tài nguyên, CLI cần làm rõ quyền và môi trường thực thi.

## 28. Interactive REPL

Một số DSL cung cấp REPL (*Read-Eval-Print Loop*) để nhập biểu thức và xem kết quả ngay.

~~~text
$ dsl repl
DSL REPL 2.4.1
> 1 + 2
3
> let x = 10
> x * 2
20
> :type x
Integer
> :quit
~~~

REPL thường có bốn bước:

1. Read: đọc input.
2. Eval: phân tích và đánh giá.
3. Print: hiển thị kết quả.
4. Loop: quay lại chờ input tiếp theo.

### 28.1. Lệnh đặc biệt

Các lệnh như `:help`, `:type`, `:load` hoặc `:quit` có thể là REPL commands, không phải cú pháp DSL. Cần phân biệt chúng với biểu thức người dùng nhập.

### 28.2. Multi-line input

DSL có block hoặc expression nhiều dòng cần cơ chế nhận biết input đã hoàn chỉnh chưa. REPL có thể tiếp tục prompt phụ khi ngoặc hoặc block chưa đóng.

### 28.3. State

REPL có thể giữ biến và định nghĩa qua nhiều lần nhập. Cần quy định cách xử lý khai báo trùng, reset environment và load file.

## 29. Định dạng output

CLI nên tách dữ liệu kết quả khỏi cách trình bày. Một command có thể hỗ trợ `text`, `json`, `yaml` hoặc `sarif` tùy nhu cầu.

### 29.1. Schema output

~~~json
{
  "version": 1,
  "command": "check",
  "success": true,
  "diagnostics": []
}
~~~

### 29.2. Version output schema

Output schema có thể thay đổi độc lập với version CLI. Nếu script bên ngoài tiêu thụ JSON, cần có chính sách tương thích và cách nhận diện version.

### 29.3. Deterministic output

Cùng input và cấu hình nên tạo output ổn định. Timestamp hoặc đường dẫn máy cục bộ có thể làm output khó so sánh; chỉ thêm metadata khi cần hoặc khi người dùng yêu cầu verbose mode.

## 30. Những sai lầm thường gặp

**Command làm quá nhiều việc.** Một command có nhiều tác động khó hiểu sẽ khó sử dụng và khó tự động hóa. Nên chia hành động thành subcommand rõ.

**Help không thể hiện default.** Người dùng không biết command sẽ chọn target hoặc config nào khi bỏ option.

**Trộn log với machine-readable output.** Một dòng progress trong stdout có thể làm hỏng JSON hoặc pipeline.

**Exit code không phản ánh kết quả.** CI có thể báo thành công dù validation thất bại, hoặc thất bại vì warning không quan trọng.

**Prompt trong môi trường non-interactive.** Script có thể treo nếu CLI chờ câu trả lời.

**Resolve path không nhất quán.** Cùng một lệnh có thể đọc file khác nhau tùy working directory mà người dùng không nhận ra.

**Tự parse command bằng cách tách chuỗi.** Đường dẫn có khoảng trắng và ký tự đặc biệt dễ bị xử lý sai.

**Không kiểm tra option xung đột.** Hai option có ý nghĩa đối lập cùng bật có thể tạo hành vi khó hiểu.

**Thay đổi default mà không thông báo.** Script cũ có thể tạo artifact khác dù command line không đổi.

**In secret trong verbose log.** Credential có thể bị lưu trong CI log hoặc shell history.

**Không hỗ trợ machine-readable output.** Script phải parse text không ổn định thay vì dùng schema.

**Không kiểm soát ghi/xóa file.** Generator có thể ghi đè mã người dùng hoặc clean nhầm dữ liệu.

## 31. Ghi nhớ

- CLI là giao diện văn bản để người dùng và script gọi các chức năng của bộ công cụ DSL.
- Một command thường gồm program, subcommand, positional arguments và options.
- Subcommand nên có mục đích rõ; global option và command option cần được phân biệt.
- Parser cần xử lý đúng argument, quoting, option thiếu giá trị, unknown option và xung đột.
- Help cần có usage, mô tả, default và ví dụ có thể chạy.
- stdin, stdout và stderr có vai trò riêng; stdout nên giữ sạch khi xuất JSON hoặc dữ liệu cho pipe.
- Exit code là hợp đồng giữa CLI và shell/CI; cần ổn định và phản ánh kết quả thực tế.
- Diagnostics nên có severity, code, vị trí và định dạng text hoặc machine-readable.
- Cấu hình có thể đến từ default, file, environment và command line; precedence cần được công bố.
- Dry-run, confirmation và non-interactive mode giúp command có tác động rõ ràng và tự động hóa an toàn.
- CLI cần xử lý cancellation, path, encoding, secret và plugin theo chính sách bảo mật.
- Output schema, command names, options, defaults và exit codes đều cần được quản lý qua phiên bản.

## 32. Câu hỏi tự kiểm tra

1. CLI là gì và vì sao bộ công cụ DSL cần CLI?
2. Phân biệt subcommand, positional argument, option và global option.
3. Vì sao command nên có một mục đích rõ ràng?
4. CLI cần xử lý đường dẫn có khoảng trắng và glob như thế nào?
5. Phân biệt option có giá trị với boolean flag.
6. Vì sao cần quy định precedence giữa default, config file, environment variable và command line?
7. stdin, stdout và stderr có vai trò gì trong pipeline shell?
8. Vì sao progress và log không nên trộn vào stdout khi command xuất JSON?
9. Exit code giúp shell và CI quyết định điều gì?
10. Khi nào warning nên làm command trả exit code thất bại?
11. Dry-run và force overwrite có mục đích khác nhau như thế nào?
12. Vì sao CLI cần non-interactive mode?
13. Shell completion nên lấy những thông tin nào và vì sao phải phản hồi nhanh?
14. Những nguyên tắc nào giúp CLI an toàn khi xử lý path, secret và process con?
15. Phân biệt output dành cho con người với output machine-readable.
16. Hãy thiết kế usage và options cho command check có strict mode, JSON diagnostics và exclude path.
17. Vì sao CLI nên gọi application service dùng chung thay vì tự triển khai parser và semantic analysis riêng?
18. Khi đổi default hoặc exit code trong phiên bản mới, những script và người dùng nào có thể bị ảnh hưởng?
