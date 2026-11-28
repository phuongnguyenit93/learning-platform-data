# Lập danh sách command, cú pháp, kết quả và mã thoát cần bảo toàn

Khi nâng cấp Spring Shell, thay đổi dễ nhìn thấy nhất thường là annotation, cách đăng ký command hoặc cấu hình runner. Nhưng điều người dùng và script phụ thuộc vào là hợp đồng CLI: tên command, alias, cách truyền tham số, giá trị mặc định, nội dung output, stream nhận output và mã thoát của tiến trình.

Một command vẫn compile sau migration chưa chắc còn tương thích. Đổi option từ tùy chọn thành bắt buộc có thể làm script cũ thất bại; đổi default có thể làm kết quả khác; in thêm banner vào stdout có thể khiến pipeline JSON không parse được; đổi exit code có thể làm CI hiểu nhầm lệnh thành công.

Bài học này hướng dẫn lập danh sách hợp đồng CLI trước khi nâng cấp, lưu lại hành vi của bản hiện tại, phân loại thay đổi tương thích và kiểm chứng bản mới bằng cùng một bộ kịch bản. Phạm vi là Spring Shell trong ứng dụng Java/Spring; nguyên tắc cũng áp dụng cho CLI được gọi từ shell script, CI, scheduler, runbook và công cụ tự động hóa.

## 1. Xem CLI là một giao diện công khai

Một command line interface là giao diện giữa ứng dụng và các caller bên ngoài. Caller có thể là:

- Người dùng nhập lệnh trong REPL.
- Shell script hoặc batch file.
- Pipeline CI/CD.
- Cron, Task Scheduler hoặc hệ thống lập lịch.
- Một ứng dụng khác gọi executable.
- Tài liệu vận hành và runbook.
- Bộ test hoặc công cụ hỗ trợ triển khai.

Các caller này thường không biết code Java bên trong. Chúng chỉ dựa vào hành vi quan sát được: command có tồn tại không, tham số được parse thế nào, output nằm ở đâu và process trả mã gì.

Vì vậy, trước khi thay đổi implementation, hãy ghi lại **hợp đồng bên ngoài**. Có thể đổi cách đăng ký command từ annotation sang registration API, nhưng nếu không có chủ đích phá vỡ tương thích thì người dùng vẫn nên gọi cùng tên command và nhận cùng kết quả.

Một migration có thể xem là tương thích khi những caller hợp lệ trước đây tiếp tục hoạt động với cùng ý nghĩa, cùng output contract và cùng exit behavior.

## 2. Xác định phạm vi caller trước khi kiểm kê

Không phải command nào cũng được gọi theo cùng cách. Một command có thể được dùng trong REPL nhưng không xuất hiện trong script; command khác có thể chỉ được gọi từ CI.

Trước khi lập bảng, xác định:

| Caller | Cách sử dụng | Điều cần bảo toàn |
|---|---|---|
| Người dùng REPL | Gõ command, đọc prompt và output | Tên, trợ giúp, completion, tương tác |
| Shell script | Gọi executable với arguments | Cú pháp, stdout/stderr, exit code |
| CI pipeline | Chạy command trong job | Exit code, thời gian, output máy đọc được |
| Scheduler | Chạy định kỳ | Không phụ thuộc prompt, timeout, idempotency |
| Runbook | Người vận hành sao chép lệnh | Tên option, default, thông báo lỗi |
| Tool khác | Parse JSON/CSV hoặc gọi command | Schema output và thứ tự field nếu có cam kết |

Tìm bằng chứng từ các nguồn đang được duy trì trong quy trình phát triển: script, pipeline, tài liệu vận hành, cấu hình scheduler, ví dụ lệnh trong tài liệu sản phẩm và log sử dụng nếu được phép truy cập. Hỏi người sở hữu automation khi một command có hành vi không rõ.

Đừng chỉ dựa vào danh sách command mà shell in ra từ help. Một command có thể bị ẩn khỏi help nhưng vẫn được gọi từ script; ngược lại, command có trong help có thể chỉ dành cho tương tác thủ công.

## 3. Lập inventory cho mọi command

Mỗi command cần một bản ghi có thể đối chiếu giữa bản cũ và bản mới.

Các trường cơ bản:

| Nhóm | Trường cần ghi |
|---|---|
| Định danh | Command key, alias, nhóm, trạng thái visible/hidden |
| Input | Argument, option, short alias, vị trí, kiểu dữ liệu |
| Ràng buộc | Required/optional, default, arity, giá trị lặp |
| Parse | Cách quote, escape, enum, boolean và conversion |
| Output | Kiểu kết quả, format, schema, stdout/stderr |
| Lỗi | Validation, exception mapping, thông báo |
| Process | Exit code khi thành công/thất bại |
| Mode | REPL, non-interactive, script |
| Side effect | Đọc/ghi, xóa, gọi API, transaction |
| Consumer | Người dùng, script, CI, scheduler hoặc hệ thống khác |

Ví dụ inventory:

| Command key | Caller chính | Input quan trọng | Kết quả | Exit contract |
|---|---|---|---|---|
| **project list** | Người dùng, CI | **--limit**, **--format** | Danh sách dự án | 0 nếu thành công |
| **project show** | Script | **--id** bắt buộc | Một dự án hoặc lỗi not found | Mã cũ khi không tìm thấy |
| **project create** | Người dùng, pipeline | **--name**, **--owner** | ID và trạng thái mới | 0 hoặc mã validation |
| **project delete** | Runbook | **--id**, **--force** | Xác nhận xóa | Giữ nguyên mã từ chối/xóa |
| **system health** | Scheduler | Không có | Kết quả máy đọc được | 0 healthy, non-zero nếu unhealthy |

Các giá trị trong bảng chỉ minh họa cách ghi inventory. Khi migration thực tế, thay bằng command, option và mã đang tồn tại trong ứng dụng.

### 3.1. Ghi cả alias và trạng thái command

Tên command là một phần của giao diện. Nếu command có nhiều alias, phải ghi từng alias và caller nào đang dùng alias đó.

Ví dụ với annotation legacy:

~~~java
@ShellMethod(
        key = {"project list", "projects"},
        value = "List projects.")
public String listProjects() {
    // ...
}
~~~

Inventory nên ghi:

| Command chính | Alias | Cách gọi đã tồn tại |
|---|---|---|
| **project list** | **projects** | **project list**, **projects** |

Không tự ý xóa alias vì thấy alias cũ không còn xuất hiện trong tài liệu. Có thể script lâu năm vẫn gọi alias đó.

Ghi rõ command có bị ẩn khỏi help, bị giới hạn theo profile hoặc phụ thuộc availability condition hay không. Thay đổi điều kiện đăng ký có thể khiến command biến mất trong môi trường production dù code vẫn compile.

## 4. Kiểm kê cú pháp input chi tiết

Đừng chỉ ghi tên option. Hãy ghi chính xác ngữ nghĩa parser mà caller đang dựa vào.

### 4.1. Argument và option

Phân biệt argument theo vị trí với option có tên:

~~~text
project show 101
project show --id 101
~~~

Hai cú pháp có thể cùng gọi một use case nhưng không tương đương đối với script. Nếu caller cũ truyền positional argument, migration không được âm thầm yêu cầu option mới trừ khi đã có kế hoạch chuyển caller.

### 4.2. Required, optional và default

Ví dụ:

~~~java
@ShellMethod(key = "project list")
public String list(
        @ShellOption(defaultValue = "20") int limit) {
    // ...
}
~~~

Hợp đồng cần ghi:

- Có thể bỏ option limit không?
- Default hiện tại là bao nhiêu?
- Giá trị 0 có hợp lệ không?
- Số âm được xử lý thế nào?
- Nếu caller truyền option nhiều lần thì dùng giá trị đầu, cuối hay báo lỗi?
- Nếu option bị thiếu thì lỗi xuất hiện ở parser hay trong command?

Thay default từ 20 thành 50 có thể không làm compile fail nhưng làm kết quả và tải hệ thống thay đổi. Default là một phần của contract.

### 4.3. Kiểu dữ liệu và conversion

Ghi rõ kiểu Java và cách chuyển từ token:

| Input | Kiểu đích | Điều cần kiểm tra |
|---|---|---|
| **--id 101** | **Long** | Chuỗi không phải số |
| **--active true** | **boolean** | Cách xử lý chữ hoa/thường |
| **--status ACTIVE** | Enum | Tên enum và alias |
| **--created-after 2026-01-01** | **LocalDate** | Format và timezone nếu có |
| **--tag a --tag b** | Collection | Có hỗ trợ lặp option không? |

Một custom converter có thể thay đổi hành vi mà không làm chữ ký command thay đổi. Vì vậy, lưu cả input mẫu hợp lệ và không hợp lệ.

### 4.4. Quote, escape và khoảng trắng

Ghi các trường hợp caller có thể sử dụng:

~~~text
project create --name "inventory api"
project create --name inventory-api
project search --query "status:active owner:platform"
~~~

Kiểm tra cách parser xử lý:

- Giá trị chứa dấu cách.
- Dấu nháy đơn và nháy kép.
- Backslash và ký tự escape.
- Chuỗi rỗng.
- Khoảng trắng đầu/cuối.
- Unicode.
- Ký tự đặc biệt của shell hệ điều hành.

Cú pháp người dùng nhập trong REPL có thể khác cách script OS truyền argument array. Nên kiểm thử cả hai nếu ứng dụng hỗ trợ cả hai chế độ.

## 5. Ghi lại output contract

Kết quả command không chỉ là chuỗi được trả về từ method. Caller có thể phụ thuộc vào format, stream, encoding và thứ tự dữ liệu.

Ghi lại:

- Output là text, bảng, JSON, CSV hay file.
- Field nào bắt buộc và kiểu dữ liệu của field.
- Có header hay không.
- Thứ tự hàng và thứ tự field có được cam kết không.
- Kết quả rỗng hiển thị thế nào.
- Có banner, prompt hoặc màu ANSI không.
- Output có newline cuối không.
- Encoding là UTF-8 hay encoding khác.
- Diagnostic và warning được ghi vào stream nào.

Ví dụ contract JSON:

~~~json
{
  "id": 101,
  "name": "inventory-api",
  "status": "ACTIVE"
}
~~~

Nếu script parse JSON từ stdout, chỉ một dòng banner hoặc log chen vào cũng có thể làm parser thất bại.

Một cách tổ chức thường hữu ích:

| Stream | Nội dung |
|---|---|
| stdout | Kết quả chính của command, phù hợp cho caller đọc hoặc parse |
| stderr | Warning, diagnostic và thông báo lỗi |
| File | Artifact được export, báo cáo hoặc dữ liệu lớn |

Nếu bản cũ in thông báo lỗi trên stdout, đó vẫn là hành vi hiện tại mà caller có thể đã dựa vào. Có thể cần sửa thiết kế, nhưng hãy xem đó là thay đổi có kiểm soát và kiểm tra caller trước khi chuyển stream.

### 5.1. Phân biệt output hiển thị và output máy đọc

Một command có thể hỗ trợ hai format:

~~~text
project list --format table
project list --format json
~~~

Ghi rõ:

- Format mặc định.
- Tên format hợp lệ.
- JSON schema hoặc CSV columns.
- Null, field thiếu và giá trị rỗng.
- Cách biểu diễn ngày giờ và timezone.
- Thứ tự kết quả.
- Cách báo lỗi khi format không hợp lệ.

Không nên để banner, màu ANSI hoặc progress spinner xuất hiện trong output máy đọc nếu contract hứa stdout là JSON/CSV thuần.

## 6. Xác định hợp đồng mã thoát

Exit code là một trong những phần quan trọng nhất với script và CI. Một command có thể in thông báo lỗi nhưng process vẫn trả 0; pipeline khi đó có thể đánh dấu job thành công.

Tách hai khái niệm:

- **Command result:** kết quả của một command bên trong REPL hoặc script runner.
- **Process exit code:** mã mà hệ điều hành nhận khi tiến trình kết thúc.

Trong REPL, một command lỗi không nhất thiết kết thúc toàn bộ tiến trình. Người dùng có thể tiếp tục nhập command khác. Trong non-interactive mode, process thường kết thúc sau lần gọi; khi đó exit code của process là điều automation kiểm tra. Script mode có thể chạy nhiều command, nên phải ghi rõ quy tắc khi một lệnh lỗi.

### 6.1. Lập bảng exit code hiện tại

Ví dụ một contract có thể được tài liệu hóa như sau:

| Exit code | Ý nghĩa | Caller xử lý |
|---:|---|---|
| 0 | Thành công | Dùng output |
| 2 | Cú pháp hoặc argument không hợp lệ | Sửa cách gọi |
| 3 | Không tìm thấy tài nguyên | Kiểm tra ID hoặc dữ liệu |
| 4 | Không đủ quyền | Kiểm tra credential/role |
| 5 | Lỗi hệ thống ngoài | Có thể retry theo chính sách |
| 10 | Từ chối thao tác theo quy tắc nghiệp vụ | Xử lý điều kiện trước khi gọi |

Các mã này chỉ là ví dụ. Phải ghi lại đúng mã đang được ứng dụng phát ra, không tự áp dụng bảng ví dụ vào sản phẩm.

### 6.2. Xác định nơi tạo exit code

Trong ứng dụng Spring Boot, exit code có thể được tạo từ các cơ chế như **ExitCodeGenerator** hoặc **ExitCodeExceptionMapper**. Spring Shell runner và exception handling cũng ảnh hưởng tới cách lỗi command được xử lý.

Khi migration, kiểm tra:

- Command trả kết quả bình thường hay ném exception?
- Exception resolver có biến lỗi thành output không?
- Có bean ExitCodeGenerator không?
- Có ExitCodeExceptionMapper không?
- Có code gọi SpringApplication.exit(...) không?
- Runner có dừng ở lỗi đầu tiên không?
- Có logic riêng gọi System.exit(...) không?

Không suy ra process exit code chỉ từ loại exception hoặc nội dung output. Hãy chạy executable thật và đọc Process.exitValue().

### 6.3. Không tái sử dụng mã thoát cho ý nghĩa khác

Nếu code 3 hiện có nghĩa “không tìm thấy tài nguyên”, không đổi nó thành “lỗi database” chỉ vì enum nội bộ được sắp xếp lại.

Caller thường có logic như:

~~~bash
project-cli project show --id 999
status=$?

if [ "$status" -eq 3 ]; then
  echo "Project does not exist"
elif [ "$status" -ne 0 ]; then
  echo "Unexpected failure" >&2
  exit "$status"
fi
~~~

Đổi mã thoát có thể khiến caller xử lý sai nhánh, ngay cả khi message vẫn giống nhau.

## 7. Ghi lại hành vi script mode

Một file script có thể chứa nhiều command. Contract cần trả lời:

- Script được nhận qua option nào hoặc runner nào?
- Command được thực thi theo thứ tự nào?
- Một command lỗi có dừng script không?
- Có tiếp tục với command kế tiếp không?
- Exit code cuối cùng là của lệnh cuối, lỗi đầu tiên hay tổng hợp?
- Output của từng command được ghép như thế nào?
- Prompt có bị tắt không?
- Có thể đọc input từ stdin không?

Ví dụ script:

~~~text
project create --name inventory-api
project show --id 101
project list
~~~

Nếu phiên bản mới thay đổi từ “dừng ở lỗi đầu tiên” sang “tiếp tục chạy”, một script có thể tạo ra trạng thái dữ liệu khác. Đây là thay đổi về semantics, không chỉ là thay đổi runner.

Tạo test riêng cho:

1. Tất cả command thành công.
2. Command đầu tiên thất bại.
3. Command ở giữa thất bại.
4. Command cuối cùng thất bại.
5. Có dòng trống hoặc comment.
6. Có input cần prompt.
7. Script kết thúc với mã thoát được quy định.

## 8. Ghi lại side effect và tính an toàn khi retry

Command có thể thay đổi trạng thái bên ngoài. Hợp đồng migration cần ghi rõ hành động và hậu quả:

| Command | Side effect | Câu hỏi cần trả lời |
|---|---|---|
| **project list** | Đọc dữ liệu | Có pagination hoặc sort mặc định không? |
| **project create** | Tạo bản ghi | Gọi lại có tạo bản ghi trùng không? |
| **project delete** | Xóa dữ liệu | Có cần xác nhận hoặc **--force** không? |
| **user sync** | Đồng bộ hệ thống ngoài | Có retry an toàn không? |
| **report export** | Ghi file | File cũ bị overwrite hay tạo tên mới? |

Không chỉ kiểm tra output. Hai phiên bản có thể in cùng một thông báo nhưng thực hiện side effect khác nhau.

Đối với command ghi dữ liệu, kiểm tra:

- Idempotency: chạy lại cùng input có an toàn không?
- Transaction: lỗi giữa chừng có rollback không?
- Partial success: một phần dữ liệu có thể đã được cập nhật không?
- Retry: timeout có khiến caller chạy lại và tạo side effect kép không?
- Confirmation: có prompt xác nhận trong interactive mode không?
- Force option: bỏ qua bước xác nhận có giữ nguyên ý nghĩa không?

Nếu thay đổi semantics của side effect là cần thiết, ghi rõ đây là breaking change và cung cấp hướng dẫn cho caller.

## 9. Tạo manifest hợp đồng CLI

Có thể lưu inventory ở một file CSV, Markdown hoặc YAML trong quy trình phát triển. Mục tiêu là reviewer có thể nhìn thấy khác biệt giữa bản cũ và bản mới.

Ví dụ manifest:

~~~yaml
commands:
  - key: "project show"
    aliases: []
    modes:
      - interactive
      - non-interactive
      - script
    arguments:
      - name: id
        position: 1
        type: long
        required: true
    options:
      - name: format
        aliases:
          - f
        type: enum
        values:
          - table
          - json
        default: table
    output:
      success:
        stream: stdout
        format: selected-by-format
      error:
        stream: stderr
    exitCodes:
      success: 0
      notFound: 3
    sideEffects:
      - read-project
~~~

Manifest này chỉ minh họa cấu trúc dữ liệu. Không cần biến manifest thành runtime configuration của Spring Shell. Nó có thể là tài liệu hợp đồng để sinh test case, review migration hoặc so sánh version.

Một manifest tốt có thể liên kết từng command với:

- Người sở hữu command.
- Script hoặc pipeline đang gọi command.
- Test case bảo vệ contract.
- Tài liệu usage.
- Version bắt đầu hỗ trợ alias hoặc option.
- Version dự kiến loại bỏ một alias nếu có chính sách deprecation.

## 10. Lưu baseline của phiên bản hiện tại

Trước khi thay đổi code, chạy phiên bản đang phát hành và ghi lại hành vi. Đây là baseline để so sánh.

Với mỗi command, lưu:

- Lệnh gọi chính xác và argument array.
- Exit code thực tế.
- stdout nguyên bản.
- stderr nguyên bản.
- Side effect quan sát được.
- Kết quả với input hợp lệ.
- Kết quả với input sai.
- Kết quả với dữ liệu rỗng hoặc không tồn tại.
- Hành vi trong từng mode được hỗ trợ.

Ví dụ cấu trúc fixture:

~~~text
cli-contract/
├── manifest.yml
├── cases/
│   ├── project-list-default/
│   │   ├── args.txt
│   │   ├── stdout.txt
│   │   ├── stderr.txt
│   │   └── exit-code.txt
│   ├── project-show-not-found/
│   │   ├── args.txt
│   │   ├── stdout.txt
│   │   ├── stderr.txt
│   │   └── exit-code.txt
│   └── project-create-duplicate/
│       ├── args.txt
│       ├── stdout.txt
│       ├── stderr.txt
│       └── exit-code.txt
└── README.md
~~~

Fixture không phải lúc nào cũng cần lưu toàn bộ output. Nếu output chứa timestamp, ID ngẫu nhiên hoặc đường dẫn tạm, tách phần ổn định thành assertion và chuẩn hóa có chủ đích.

Không xóa khác biệt chỉ để test pass. Mỗi normalization phải được giải thích: trường nào động, tại sao động và liệu caller có phụ thuộc trường đó không.

## 11. Phân loại thay đổi tương thích

Trước khi migration, thống nhất mức độ tương thích mà release phải giữ.

| Mức | Ví dụ | Hành động |
|---|---|---|
| Giữ nguyên | Cùng command key, option, default, output và exit code | Regression test phải pass |
| Additive | Thêm option optional hoặc alias mới | Kiểm tra default cũ không đổi |
| Deprecated | Đánh dấu alias cũ sẽ bị loại bỏ | Duy trì alias trong thời gian công bố |
| Breaking | Đổi tên command, đổi default, bỏ option, đổi schema hoặc exit code | Versioning và migration guide rõ ràng |

Một thay đổi additive chỉ thực sự tương thích nếu không làm caller cũ diễn giải input khác đi. Ví dụ thêm một option optional nhưng dùng tên trùng với positional argument có thể thay đổi cách parser hiểu command.

### 11.1. Đổi tên command an toàn

Nếu cần đổi **project list** thành **project ls**, giữ alias cũ trong giai đoạn chuyển tiếp:

~~~java
@ShellMethod(
        key = {"project ls", "project list"},
        value = "List projects.")
public String listProjects() {
    // ...
}
~~~

Sau đó:

1. Công bố tên mới.
2. Giữ tên cũ như alias.
3. Ghi cảnh báo deprecation nếu phù hợp.
4. Kiểm tra log usage hoặc caller inventory.
5. Chỉ loại bỏ alias trong release có thông báo breaking change.

Nếu registration model mới không cho phép khai báo alias giống cách cũ, đăng ký cả hai command key và trỏ về cùng use case. Điều cần bảo toàn là hành vi gọi, không phải annotation cụ thể.

## 12. Giữ contract khi đổi cách đăng ký command

Spring Shell có thể thay đổi cách khai báo command qua các phiên bản: annotation legacy, command registration theo API mới hoặc cấu hình bean. Migration implementation có thể cần:

- Chuyển annotation và metadata.
- Chuyển option binding.
- Chuyển converter.
- Chuyển validation.
- Chuyển result handler.
- Chuyển exception resolver.
- Chuyển availability provider.
- Cập nhật runner hoặc interaction mode.

Sau khi chuyển, đối chiếu từng trường trong manifest. Không coi việc method Java còn tồn tại là bằng chứng command cũ vẫn được đăng ký.

Ví dụ contract cũ:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod(
            key = "project show",
            value = "Show a project.")
    public String show(
            @ShellOption("--id") Long id) {
        return projectService.show(id);
    }
}
~~~

Dù cách đăng ký mới khác, command vẫn phải chấp nhận **project show --id 101** nếu đó là cú pháp công khai cần giữ. Kiểm tra bằng test gửi đúng token như caller cũ, không chỉ gọi trực tiếp method mới.

## 13. Xây dựng regression test cho command syntax

Tạo test case theo từng dòng trong manifest:

| Case | Input | Kết quả cần xác minh |
|---|---|---|
| Default option | Không truyền option | Default không đổi |
| Explicit option | Truyền giá trị hợp lệ | Giá trị được bind đúng |
| Missing required | Bỏ option bắt buộc | Lỗi tương đương contract |
| Invalid conversion | Truyền sai kiểu | Không gọi service nếu parser từ chối |
| Alias | Gọi tên cũ | Vẫn hoạt động trong thời gian tương thích |
| Quoted value | Chuỗi có dấu cách | Nhận nguyên giá trị |
| Repeated option | Truyền option nhiều lần | Semantics được giữ |
| Unknown option | Option không tồn tại | Lỗi rõ ràng, không chạy nghiệp vụ |

Với Spring Shell test support, có thể dùng **@ShellTest**, **ShellTestClient** và **ShellAssertions** để chạy command trong phiên shell giả lập. Các test này xác minh parser, command registration và output trong context Spring.

Ví dụ non-interactive test:

~~~java
@ShellTest
class ProjectCommandContractTests {

    @Autowired
    ShellTestClient client;

    @Test
    void oldCommandSyntaxRemainsAvailable() {
        var session = client.nonInterative(
                "project", "show",
                "--id", "101")
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Project 101"));
    }
}
~~~

Tên method non-interactive phụ thuộc phiên bản Spring Shell. Với nhánh 3.1.x, API được cung cấp có spelling **nonInterative**; từ 3.4.2 có **nonInteractive** và tên cũ được deprecated. Dùng đúng API của dependency dự án.

Shell session test không thay thế process test nếu cần xác minh exit code hệ điều hành.

## 14. Regression test cho stdout, stderr và exit code

Để kiểm tra process contract, chạy executable thật bằng process riêng. Đọc stdout, stderr và exit code độc lập.

Ví dụ JUnit dùng file redirect để tránh deadlock khi process ghi nhiều dữ liệu:

~~~java
@Test
void missingProjectKeepsProcessExitContract() throws Exception {
    Path stdout = tempDir.resolve("stdout.txt");
    Path stderr = tempDir.resolve("stderr.txt");

    Process process = new ProcessBuilder(
            javaExecutable,
            "-jar",
            cliJar.toString(),
            "project", "show",
            "--id", "999")
            .redirectOutput(stdout.toFile())
            .redirectError(stderr.toFile())
            .start();

    boolean finished = process.waitFor(15, TimeUnit.SECONDS);
    if (!finished) {
        process.destroyForcibly();
        process.waitFor(5, TimeUnit.SECONDS);
        fail("CLI process did not finish within timeout");
    }

    int exitCode = process.exitValue();
    String out = Files.readString(stdout);
    String err = Files.readString(stderr);

    assertThat(exitCode).isEqualTo(3);
    assertThat(out).doesNotContain("Project 999");
    assertThat(err).contains("Project 999 was not found");
}
~~~

Ví dụ giả định test fixture đã cung cấp **tempDir**, **javaExecutable**, **cliJar** và JUnit/AssertJ imports; mã 3 và thông báo là contract minh họa, cần thay bằng baseline thật.

Dùng timeout để tránh test treo nếu process không thoát. Đọc stdout và stderr từ file sau khi process kết thúc giúp tránh deadlock có thể xảy ra nếu một pipe đầy trong khi test chỉ chờ process.

Với command thành công, thêm test xác minh exit code 0 và output đúng. Với lỗi parser, validation, not found và lỗi hệ thống, xác minh đúng mã đã công bố.

## 15. So sánh output theo đúng mức cam kết

Không phải mọi byte trong terminal đều là contract. Cần xác định phần nào là dữ liệu ổn định và phần nào là presentation có thể thay đổi.

| Output | Cách kiểm tra |
|---|---|
| JSON schema công khai | Parse JSON và so sánh field/value |
| CSV export | Kiểm tra header, delimiter, encoding và dữ liệu |
| Bảng cho người dùng | Kiểm tra cột và giá trị quan trọng |
| Timestamp hiện tại | Kiểm tra format hoặc range, không hardcode thời điểm |
| ANSI color | Chỉ kiểm tra nếu màu là yêu cầu sản phẩm |
| Prompt | Kiểm tra trong interactive test nếu caller phụ thuộc |
| Banner | Kiểm tra riêng; tránh để banner chen vào JSON stdout |

Nếu output JSON có thể thay đổi thứ tự field nhưng schema không yêu cầu thứ tự, parse JSON rồi so sánh cấu trúc thay vì so sánh chuỗi. Với CSV, thứ tự cột thường có ý nghĩa nên cần kiểm tra rõ.

Không chuẩn hóa newline, whitespace hoặc ANSI quá rộng. Nếu caller thực sự parse output bằng exact string hoặc shell tools, những chi tiết đó có thể là contract thực tế.

## 16. Kiểm tra behavior ở cả ba execution mode

Một command có thể hoạt động đúng trong REPL nhưng sai trong non-interactive mode vì prompt hoặc runner khác nhau.

Tạo test matrix:

| Hành vi | Interactive | Non-interactive | Script |
|---|---|---|---|
| Command key | Kiểm tra | Kiểm tra | Kiểm tra |
| Option parsing | Kiểm tra | Kiểm tra | Kiểm tra |
| Prompt | Có thể dùng | Không được phụ thuộc | Phải xác định |
| Output | Màn hình | stdout/stderr | Tổng hợp theo script |
| Lỗi | Người dùng có thể tiếp tục | Process exit | Dừng/tiếp tục theo contract |
| Exit code | Process kết thúc | Quan trọng | Quy tắc tổng hợp |

Nếu một command yêu cầu xác nhận, cần xác định rõ:

- Interactive mode có prompt xác nhận không?
- Non-interactive mode có yêu cầu **--force** hoặc option xác nhận không?
- Script mode xử lý prompt thế nào?
- Khi thiếu input, command fail hay dùng default?

Không để automation bị treo vì prompt không thể trả lời.

## 17. Kiểm tra default và thay đổi cấu hình

Cùng một command có thể trả kết quả khác do profile hoặc environment variable. Khi migration, ghi lại cấu hình có thể tác động tới contract:

- Default limit hoặc page size.
- Output format mặc định.
- Locale và timezone.
- Encoding.
- API endpoint và timeout.
- Feature flag hoặc availability condition.
- Interactive/non-interactive runner.
- Banner, color và logging.

Chạy test với cấu hình mặc định và cấu hình production. Nếu command được gọi từ nhiều profile, kiểm tra profile nào đang thay đổi hành vi.

Không đưa secret hoặc credential vào fixture. Dùng test credentials và service giả lập khi kiểm tra command contract.

## 18. Quy trình migration theo từng bước

Có thể tổ chức migration thành các bước có thể review:

1. **Inventory:** liệt kê command, alias, input, output, exit code và caller.
2. **Baseline:** chạy bản hiện tại, lưu output/exit code và side effect cần thiết.
3. **Risk review:** đánh dấu command được script hoặc CI sử dụng; ưu tiên bảo vệ các command đó.
4. **Implementation mapping:** ánh xạ registration, option, converter, validation, result handler và exception handler sang API mới.
5. **Contract tests:** chạy cùng bộ input trên implementation mới.
6. **Process tests:** xác minh stdout/stderr, process exit code và timeout.
7. **Mode tests:** kiểm tra interactive, non-interactive và script nếu sản phẩm hỗ trợ.
8. **Differential review:** phân loại mọi khác biệt là giữ nguyên, additive, deprecated hoặc breaking.
9. **Documentation:** cập nhật help, ví dụ, runbook và migration guide.
10. **Release:** chỉ công bố khi các khác biệt có chủ đích đã được caller xử lý.

Nếu migration lớn, có thể chia theo nhóm command thay vì đổi tất cả cùng lúc. Mỗi nhóm cần một bộ contract tests riêng để dễ tìm regression.

## 19. Dùng differential test giữa bản cũ và bản mới

Một cách kiểm tra mạnh là chạy cùng một input trên hai artifact:

~~~text
Input case A -> old CLI -> stdout-old, stderr-old, exit-old
Input case A -> new CLI -> stdout-new, stderr-new, exit-new
                         |
                         v
                  Compare contract
~~~

So sánh:

- Exit code có giống baseline không?
- stdout có cùng schema và ý nghĩa không?
- stderr có thay đổi theo cách caller bị ảnh hưởng không?
- Side effect có giống nhau không?
- Command có hoàn tất trong timeout không?
- Alias cũ có còn hoạt động không?

Nếu khác biệt được cho phép, ghi rõ lý do và test riêng cho behavior mới. Không tự động cập nhật toàn bộ golden files chỉ vì snapshot mới khác snapshot cũ; trước tiên phải hiểu khác biệt.

Với dữ liệu động, dùng fixture cố định hoặc chuẩn hóa trường động có chủ đích. Với database, tạo trạng thái ban đầu giống nhau cho cả hai lần chạy.

## 20. Quản lý deprecation và breaking change

Khi cần thay đổi contract, nên có giai đoạn chuyển tiếp:

- Thêm command key hoặc option mới.
- Giữ tên cũ như alias nếu khả thi.
- Cảnh báo deprecation qua stderr hoặc help mà không làm hỏng output máy đọc.
- Cập nhật runbook và script mẫu.
- Theo dõi caller đã chuyển đổi.
- Công bố phiên bản loại bỏ alias.
- Giữ migration guide với ví dụ trước/sau.

Một thay đổi được xem là breaking khi caller hợp lệ cũ phải sửa mới tiếp tục chạy. Những thay đổi sau thường là breaking:

- Xóa hoặc đổi tên command key.
- Xóa alias.
- Đổi option name hoặc short alias.
- Chuyển option optional thành required.
- Đổi default làm kết quả khác.
- Đổi kiểu dữ liệu hoặc cách conversion.
- Đổi output schema hoặc stream.
- Đổi exit code hoặc ý nghĩa exit code.
- Đổi script stop-on-error behavior.
- Thay đổi side effect hoặc tính idempotent.

Không nên gọi thay đổi là “chỉ refactor” nếu script hoặc người dùng phải sửa lệnh.

## 21. Những lỗi migration thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ kiểm tra code compile | Command có thể không còn đăng ký | Test command key qua shell |
| Bỏ alias cũ | Script lâu năm thất bại | Alias transition |
| Đổi default âm thầm | Output hoặc tải hệ thống thay đổi | Test default |
| Đổi stdout/stderr | Parser hoặc pipeline hỏng | Process contract tests |
| Chỉ test message, bỏ exit code | CI đánh dấu sai thành công/thất bại | Đọc Process.exitValue() |
| Chỉ test REPL | Script có thể treo ở prompt | Test từng execution mode |
| Bỏ qua command ẩn | Automation gọi command cũ bị lỗi | Kiểm kê cả hidden command |
| Thay đổi converter | Input cũ được hiểu khác | Test token hợp lệ và không hợp lệ |
| Golden snapshot tự cập nhật | Che giấu regression | Review từng diff |
| Đổi thứ tự xử lý script | Side effect thay đổi | Test script nhiều command |
| Không kiểm tra timeout | Process có thể treo | Process test có timeout |
| Không kiểm tra idempotency | Retry tạo dữ liệu trùng | Test side effect và retry |

## 22. Bài thực hành: bảo toàn hợp đồng Project CLI

Giả sử ứng dụng hiện có:

~~~text
project list [--limit N] [--format table|json]
project show --id ID
project create --name NAME --owner OWNER
project delete --id ID [--force]
~~~

Thực hiện:

1. Lập manifest cho bốn command.
2. Ghi alias, option, kiểu, required/default và format.
3. Xác định caller chính cho từng command.
4. Chạy bản cũ với input hợp lệ và input lỗi.
5. Lưu stdout, stderr và exit code.
6. Ghi side effect của create/delete.
7. Thực hiện migration registration API hoặc version Spring Shell theo mục tiêu dự án.
8. Chạy lại cùng bộ input trên bản mới.
9. So sánh output, exit code và side effect.
10. Giữ alias cũ hoặc tạo deprecation plan nếu tên command thay đổi.
11. Viết process test cho một trường hợp thành công và các lỗi quan trọng.
12. Cập nhật help, runbook và migration guide.

Bảng review cuối:

| Contract | Baseline cũ | Bản mới | Kết luận |
|---|---|---|---|
| Command key |  |  | Giữ nguyên / thay đổi |
| Alias |  |  | Giữ nguyên / deprecated |
| Required options |  |  | Tương thích / breaking |
| Default values |  |  | Giữ nguyên / thay đổi |
| Output schema |  |  | Tương thích / breaking |
| stdout/stderr |  |  | Tương thích / breaking |
| Exit codes |  |  | Tương thích / breaking |
| Script error policy |  |  | Tương thích / breaking |
| Side effects |  |  | Tương thích / breaking |

Không kết luận migration tương thích chỉ vì tất cả unit test đều pass. Contract phải được xác minh ở đường gọi CLI thật.

## 23. Checklist trước khi phát hành phiên bản mới

- [ ] Đã liệt kê tất cả command đang đăng ký, kể cả command ẩn.
- [ ] Đã ghi alias và caller sử dụng từng alias.
- [ ] Đã ghi positional argument, option, short alias và kiểu dữ liệu.
- [ ] Đã ghi required, optional, default và arity.
- [ ] Đã kiểm tra conversion, quoting, escaping và option lặp.
- [ ] Đã ghi output format, schema, stdout và stderr.
- [ ] Đã ghi validation và thông báo lỗi.
- [ ] Đã ghi exit code và ý nghĩa từng mã.
- [ ] Đã phân biệt command result với process exit code.
- [ ] Đã ghi behavior của script khi một command lỗi.
- [ ] Đã ghi side effect, transaction và retry semantics.
- [ ] Đã chạy baseline trên artifact cũ.
- [ ] Đã chạy cùng bộ input trên artifact mới.
- [ ] Đã có shell tests và process-level tests.
- [ ] Đã có timeout cho process test.
- [ ] Đã review mọi khác biệt golden output.
- [ ] Đã có kế hoạch deprecation cho command/option cũ.
- [ ] Đã cập nhật help, tài liệu và runbook.
- [ ] Đã phân loại rõ mọi breaking change.

## 24. Kết luận

Migration Spring Shell không chỉ là chuyển annotation hoặc cập nhật dependency. Cần bảo toàn hợp đồng mà người dùng, script và CI đang gọi: command key, alias, argument, option, default, conversion, output, stream, exit code và side effect.

Hãy lập inventory trước khi thay đổi, lưu baseline của artifact hiện tại và chạy lại cùng bộ input trên phiên bản mới. Dùng shell test để xác minh registration, parsing và màn hình; dùng process test để kiểm tra stdout, stderr, timeout và exit code thật. Với script mode, ghi rõ thứ tự thực thi và cách xử lý khi một command lỗi.

Khi có khác biệt, phân loại nó là giữ nguyên, additive, deprecated hoặc breaking. Chỉ phát hành khi mọi thay đổi có chủ đích đã được kiểm tra và caller có hướng dẫn chuyển đổi rõ ràng.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.3 Reference: Command Registration](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/index.html)
- [Spring Shell 3.3 Reference: Legacy Annotation Registration](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html)
- [Spring Shell 3.3 Reference: Non-interactive Mode](https://docs.spring.io/spring-shell/reference/3.3/commands/non-interactive.html)
- [Spring Shell 3.3 Reference: Script Runner](https://docs.spring.io/spring-shell/reference/3.3/commands/script.html)
- [Spring Shell 3.1 API: ShellMethod](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellMethod.html)
- [Spring Shell 3.1 API: ShellOption](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellOption.html)
- [Spring Boot 3.1 API: ExitCodeGenerator](https://docs.spring.io/spring-boot/docs/3.1.x/api/org/springframework/boot/ExitCodeGenerator.html)
- [Spring Boot 3.1 API: ExitCodeExceptionMapper](https://docs.spring.io/spring-boot/docs/3.1.x/api/org/springframework/boot/ExitCodeExceptionMapper.html)
- [Spring Shell 3.1 API: ShellTestClient](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.html)

