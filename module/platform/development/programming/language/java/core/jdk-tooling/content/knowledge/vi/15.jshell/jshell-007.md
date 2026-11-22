# Các lệnh slash trong JShell

## 1. Lệnh slash trong JShell là gì?

**JShell** là công cụ REPL (Read-Eval-Print Loop) đi kèm JDK, cho phép nhập và chạy các khai báo, câu lệnh và biểu thức Java từng phần. Bạn có thể thử một đoạn code, xem kết quả ngay, rồi tiếp tục dùng các biến và method đã khai báo trong cùng phiên.

Tại dấu nhắc JShell, có hai loại đầu vào:

- **Snippet Java**: biểu thức, câu lệnh, khai báo biến, method, class, interface, enum hoặc record.
- **Lệnh slash**: lệnh quản lý phiên JShell, luôn bắt đầu bằng dấu `/`.

Ví dụ:

~~~text
jshell> int total = 10;
jshell> total * 2
$2 ==> 20
jshell> /vars
|    int total = 10
|    int $2 = 20
~~~

Dòng `total * 2` là biểu thức Java. `/vars` là lệnh slash để xem các biến hiện có trong phiên. Lệnh slash do JShell xử lý, không phải cú pháp Java và không được đưa vào file `.java` như một câu lệnh của chương trình.

Lệnh slash giúp bạn tra cứu trợ giúp, xem lại code đã nhập, chỉnh sửa hoặc loại bỏ snippet, lưu và nạp phiên làm việc, thay đổi classpath, cấu hình cách hiển thị và thoát khỏi JShell.

## 2. Tra cứu trợ giúp và danh sách lệnh

Khi chưa nhớ cú pháp, hãy dùng trợ giúp ngay tại dấu nhắc JShell:

~~~text
/help
~~~

`/help` liệt kê các lệnh slash và các chủ đề trợ giúp. Có thể dùng alias `/?`:

~~~text
/?
~~~

Muốn xem chi tiết một lệnh, thêm tên lệnh vào sau `/help`:

~~~text
/help /list
/help /save
/help /reload
~~~

Một số chủ đề hữu ích:

| Lệnh | Nội dung |
|---|---|
| `/help intro` | Giới thiệu cách sử dụng JShell |
| `/help keys` | Các phím điều khiển và chỉnh sửa dòng nhập |
| `/help id` | ID của snippet và cách tham chiếu |
| `/help shortcuts` | Phím tắt, tự động hoàn thành và trợ giúp |
| `/help context` | Classpath, module path và evaluation context |
| `/help rerun` | Cách chạy lại snippet đã nhập |

Trợ giúp phụ thuộc phiên bản JDK đang sử dụng. Nếu một tùy chọn không được nhận diện, hãy kiểm tra `/help` và `/help <tên-lệnh>` trên chính JDK đó thay vì đoán cú pháp.

## 3. Xem lại snippet và trạng thái phiên

JShell gán ID cho các snippet được nhập. ID giúp bạn xem, sửa, loại bỏ hoặc chạy lại một đoạn code cụ thể.

### /list

Hiển thị các snippet đang hoạt động mà bạn đã nhập hoặc nạp bằng `/open`:

~~~text
/list
~~~

Ví dụ:

~~~text
   1 : int base = 10;
   2 : int twice(int value) { return value * 2; }
   3 : twice(base)
~~~

Các tùy chọn:

- `/list -all`: xem cả snippet lỗi, bị ghi đè, đã drop và startup snippet.
- `/list -start`: xem các snippet khởi tạo khi JShell bắt đầu.
- `/list <id>`: xem snippet theo ID.
- `/list <name>`: xem snippet theo tên khai báo.

ID được cấp theo phiên và có thể khác khi chạy lại trong một phiên mới. Hãy xem `/list` trước khi dùng ID trong lệnh khác.

### /vars, /methods, /types và /imports

Các lệnh này giúp kiểm tra những gì đã được khai báo:

| Lệnh | Nội dung |
|---|---|
| `/vars` | Biến và giá trị hiện tại |
| `/methods` | Method và chữ ký method |
| `/types` | Class, interface, enum, record và các kiểu đã khai báo |
| `/imports` | Các import đang có hiệu lực |

Ví dụ:

~~~text
/vars
/methods
/types
/imports
~~~

Có thể lọc theo tên hoặc ID; tùy lệnh, `-all` và `-start` cho phép xem thêm các snippet không còn hoạt động hoặc startup snippet.

Các lệnh này rất hữu ích khi phiên đã có nhiều snippet và bạn không còn nhớ tên biến, method hoặc import nào đang được sử dụng.

### /history

`/history` hiển thị các snippet và lệnh đã nhập trong phiên hiện tại:

~~~text
/history
~~~

`/history -all` hiển thị lịch sử của phiên hiện tại và các phiên trước đó mà JShell lưu lại. Lịch sử giúp tìm lại thao tác cũ; nó khác với `/list`, vốn tập trung vào các snippet và trạng thái code.

## 4. Chỉnh sửa và loại bỏ snippet

### /edit

Mở snippet trong trình soạn thảo ngoài để chỉnh sửa:

~~~text
/edit
~~~

Các dạng thường dùng:

~~~text
/edit 2
/edit twice
/edit -all
/edit -start
~~~

- `/edit <id>` sửa snippet theo ID.
- `/edit <name>` sửa snippet theo tên.
- `/edit -all` sửa toàn bộ snippet, gồm cả snippet lỗi, bị ghi đè, đã drop và startup.
- `/edit -start` sửa startup snippet trong phiên hiện tại.

Trình soạn thảo được cấu hình bằng `/set editor`. Nếu chưa cấu hình, JShell lần lượt kiểm tra các biến môi trường `JSHELLEDITOR`, `VISUAL`, `EDITOR`; nếu không có, JShell có thể mở trình soạn thảo đơn giản tích hợp.

Ví dụ cấu hình editor:

~~~text
/set editor notepad
~~~

Tên lệnh editor và cách truyền tham số phụ thuộc hệ điều hành. Hãy dùng `/help /set editor` để xem cú pháp của phiên bản đang cài.

### /drop

Loại một snippet khỏi trạng thái hoạt động:

~~~text
/drop 1
/drop base
~~~

Sau khi drop, snippet không còn được dùng như khai báo đang hoạt động. Tuy nhiên, nó vẫn có thể xuất hiện trong `/list -all` và lịch sử; `/drop` không xóa file trên đĩa.

Ví dụ:

~~~text
jshell> int base = 10;
jshell> /drop base
jshell> base
|  Error:
|  cannot find symbol
|    symbol:   variable base
~~~

Dùng `/drop` khi một khai báo thử nghiệm không còn cần thiết hoặc khi muốn thay thế một snippet bằng phiên bản khác.

## 5. Lưu và nạp code bằng /save và /open

### /save

Lưu snippet hoặc lịch sử ra file:

~~~text
/save session.jsh
~~~

Các dạng chính:

| Lệnh | Nội dung được lưu |
|---|---|
| `/save <file>` | Source của các snippet đang hoạt động |
| `/save -all <file>` | Source của mọi snippet, gồm cả snippet lỗi, bị ghi đè, đã drop và startup |
| `/save -history <file>` | Lịch sử tuần tự gồm các lệnh và snippet đã nhập trong phiên |
| `/save -start <file>` | Các startup definition hiện tại |
| `/save <id> <file>` | Snippet theo ID được chỉ định |

Phân biệt hai nhu cầu:

- Muốn lưu code còn hoạt động để tiếp tục dùng, chọn `/save <file>`.
- Muốn lưu toàn bộ thao tác đã nhập để xem lại, chọn `/save -history <file>`.

File history có thể chứa cả lệnh slash, lệnh bị lỗi và các biểu thức thử nghiệm. Vì vậy, nó không nhất thiết là một chương trình Java độc lập hoặc một file source sạch để biên dịch bằng `javac`.

### /open

Nạp nội dung file làm đầu vào JShell:

~~~text
/open session.jsh
~~~

JShell đọc file và xử lý nội dung như các snippet và lệnh được nhập tại prompt. File có thể chứa nhiều khai báo Java và lệnh slash.

Ví dụ file `session.jsh`:

~~~java
int limit = 5;
int square(int n) { return n * n; }
System.out.println(square(limit));
/vars
~~~

Nạp file:

~~~text
/open session.jsh
~~~

Kết quả in ra:

~~~text
25
~~~

Lệnh `/open` cũng nhận URL và một số tên file có sẵn như `DEFAULT`, `PRINTING`, `TOOLING`, `JAVASE`. Những file dựng sẵn cung cấp import hoặc định nghĩa tiện ích cho JShell.

### Lưu và khôi phục một phiên

Một quy trình đơn giản:

~~~text
/save my-session.jsh
/exit
~~~

Mở JShell lần sau rồi nạp lại:

~~~bash
jshell --feedback concise
~~~

~~~text
/open my-session.jsh
~~~

Các khai báo được nạp theo thứ tự trong file. Nếu snippet sau phụ thuộc snippet trước, hãy giữ đúng thứ tự để quá trình nạp thành công.

## 6. Chạy lại snippet

JShell hỗ trợ chạy lại snippet mà không phải nhập lại code.

| Cú pháp | Ý nghĩa |
|---|---|
| `/!` | Chạy lại snippet gần nhất |
| `/<id>` | Chạy lại snippet theo ID |
| `/<id>-<id>` | Chạy lại một dải ID |
| `/-<n>` | Chạy lại snippet thứ n tính ngược từ lịch sử gần nhất |

Ví dụ:

~~~text
jshell> int value = 4;
jshell> value + 3
$2 ==> 7
jshell> /!
$3 ==> 7
~~~

`/!` chạy lại biểu thức gần nhất. Trong ví dụ này, JShell đánh giá lại `value + 3` và tạo kết quả mới.

Có thể dùng `/help rerun` để xem quy tắc ID, dải ID và cách đếm snippet trước đó.

Lưu ý: chạy lại snippet có thể thực hiện lại tác dụng phụ. Nếu snippet ghi file, gửi request, cập nhật cơ sở dữ liệu hoặc tăng bộ đếm, lệnh rerun sẽ thực hiện hành động đó thêm lần nữa. Hãy kiểm tra snippet trước khi chạy lại.

## 7. Classpath, module path và /env

JShell cần biết nơi tìm các class và module mà snippet sử dụng.

### Thiết lập khi khởi động

Có thể truyền classpath khi chạy JShell:

~~~bash
jshell --class-path lib/math-utils.jar
~~~

Với ứng dụng modular, có thể chỉ định module path và module cần resolve:

~~~bash
jshell --module-path mods --add-modules com.example.math
~~~

Classpath và module path là hai cơ chế khác nhau. JAR thông thường thường được đưa vào classpath; named module được tìm qua module path.

### Xem hoặc thay đổi evaluation context

Dùng `/env` để xem context hiện tại:

~~~text
/env
~~~

Thay đổi classpath:

~~~text
/env -class-path lib/math-utils.jar
~~~

Thay đổi module path hoặc resolve module:

~~~text
/env -module-path mods -add-modules com.example.math
~~~

Khi `/env` nhận tùy chọn, JShell cập nhật evaluation context, khởi động lại execution state và chạy lại các snippet hợp lệ. Nếu snippet không còn biên dịch được với context mới, lỗi sẽ được hiển thị.

Dấu phân cách nhiều đường dẫn phụ thuộc hệ điều hành: Windows dùng dấu chấm phẩy `;`, Linux và macOS dùng dấu hai chấm `:`.

JShell sử dụng `/env -class-path` để đổi classpath trong phiên; không có lệnh slash tổng quát `/classpath` trong danh sách lệnh của JShell 24.0.2.

## 8. Reset và reload phiên làm việc

Hai lệnh này đều có thể khởi động lại execution state, nhưng mục đích khác nhau.

### /reset

~~~text
/reset
~~~

`/reset` xóa code đã nhập khỏi trạng thái JShell, khởi động lại execution state và chạy lại startup code. Các biến, method và kiểu đã khai báo trong phiên sẽ không còn hoạt động.

Có thể truyền tùy chọn evaluation context cho `/reset`, ví dụ:

~~~text
/reset -class-path lib/math-utils.jar
~~~

Hãy lưu code cần giữ trước khi reset.

### /reload

~~~text
/reload
~~~

`/reload` reset code và execution state, sau đó phát lại các snippet hợp lệ cùng các lệnh `/drop` theo thứ tự đã nhập kể từ lần gần nhất vào JShell hoặc lần `/reset` hay `/reload` gần nhất.

Một số tùy chọn:

- `/reload -quiet`: không hiển thị quá trình phát lại, nhưng lỗi vẫn được báo.
- `/reload -restore`: khôi phục và phát lại lịch sử từ khoảng phiên trước, hữu ích khi muốn phục hồi một phiên JShell trước đó.
- Có thể kết hợp tùy chọn evaluation context như `-class-path`, `-module-path` hoặc `-add-modules`.

Ví dụ:

~~~text
/reload -quiet
/reload -restore
~~~

Khác biệt quan trọng: `/reset` xóa các khai báo hiện tại; `/reload` xây dựng lại trạng thái bằng cách phát lại các snippet hợp lệ trong lịch sử tương ứng.

Vì reload thực thi lại code, các tác dụng phụ như ghi file, cập nhật dữ liệu hoặc gọi dịch vụ ngoài có thể xảy ra lần nữa. Hãy xem lại lịch sử trước khi dùng trên một phiên có thao tác không idempotent.

## 9. Cấu hình JShell bằng /set

`/set` điều khiển cách JShell khởi tạo và hiển thị kết quả. Chạy `/set` không có đối số để xem cấu hình hiện tại.

Các dạng thường dùng:

| Lệnh | Mục đích |
|---|---|
| `/set editor <command>` | Chọn trình soạn thảo cho `/edit` |
| `/set start <file>` | Chọn file startup mặc định |
| `/set feedback <mode>` | Chọn mức feedback |
| `/set mode ...` | Tạo hoặc sửa feedback mode |
| `/set prompt ...` | Tùy chỉnh prompt |
| `/set truncation ...` | Giới hạn độ dài giá trị hiển thị |
| `/set format ...` | Tùy chỉnh định dạng feedback |
| `/set indent <number>` | Đặt số khoảng trắng tự động thụt dòng |

### Feedback mode

JShell có các mode dựng sẵn:

- `verbose`: hiển thị nhiều thông tin.
- `normal`: mức hiển thị thông thường.
- `concise`: hiển thị gọn.
- `silent`: hạn chế feedback.

Có thể chọn mode khi khởi động:

~~~bash
jshell --feedback concise
~~~

Hoặc đổi trong phiên:

~~~text
/set feedback concise
~~~

Feedback mode chỉ thay đổi cách JShell trình bày kết quả và thông báo. Nó không thay đổi ngữ nghĩa thực thi của Java snippet.

### Startup definitions

`/set start <file>` thiết lập nội dung startup snippet và command. Khi JShell khởi động, các định nghĩa đó được nạp như phần khởi tạo.

Ở cấp command line, có thể dùng:

~~~bash
jshell --startup startup.jsh
~~~

Hoặc tắt startup mặc định:

~~~bash
jshell --no-startup
~~~

Startup file phù hợp để khai báo import, helper method hoặc cấu hình tiện ích thường dùng trong quá trình học và thử nghiệm. Không nên đặt thao tác có tác dụng phụ lớn vào startup nếu bạn không muốn chúng chạy mỗi lần mở JShell hoặc reset.

## 10. Ví dụ workflow: thử nghiệm, lưu và nạp lại

Giả sử bạn đang thử một hàm tính thuế đơn giản.

Mở JShell:

~~~bash
jshell --feedback concise
~~~

Nhập các snippet:

~~~java
double taxRate = 0.1;

double totalWithTax(double price) {
    return price * (1 + taxRate);
}

totalWithTax(200)
~~~

Kết quả:

~~~text
$3 ==> 220.0
~~~

Kiểm tra những gì đang hoạt động:

~~~text
/list
/vars
/methods
~~~

Lưu code:

~~~text
/save tax-demo.jsh
~~~

Thoát:

~~~text
/exit
~~~

Mở lại và khôi phục:

~~~bash
jshell --feedback concise
~~~

~~~text
/open tax-demo.jsh
~~~

Sau khi nạp, có thể tiếp tục:

~~~text
totalWithTax(500)
~~~

Giá trị trả về là `550.0`. Tên biến tạm JShell tạo ra để hiển thị kết quả phụ thuộc số snippet đã có trong phiên.

Workflow này phù hợp để thử API, kiểm tra biểu thức, viết helper method nhỏ và lưu các đoạn code hữu ích thành script JShell.

## 11. Lỗi thường gặp khi dùng lệnh slash

### Gõ lệnh slash như code Java

Ví dụ `/vars` là lệnh JShell. Nếu đặt nó trong thân method Java hoặc file `.java`, compiler sẽ báo lỗi cú pháp. Hãy nhập lệnh tại prompt JShell hoặc đặt trong file được nạp bằng `/open`.

### Dùng sai tên lệnh

Không phải mọi công cụ JDK đều có một slash command tương ứng. Ví dụ, JShell không có lệnh `/classpath`; hãy dùng `/env -class-path` trong phiên hoặc `--class-path` khi khởi động.

Khi không chắc, dùng `/help` để xem danh sách lệnh mà phiên bản hiện tại hỗ trợ.

### Nhầm /list với /history

`/list` tập trung vào snippet và trạng thái code. `/history` ghi lại thứ tự snippet và command đã nhập. Muốn lưu code đang hoạt động, dùng `/save`; muốn lưu toàn bộ lịch sử nhập, dùng `/save -history`.

### Dùng /drop rồi mong lịch sử biến mất

`/drop` chỉ làm snippet không còn hoạt động. Nó vẫn có thể xuất hiện trong `/list -all` và lịch sử. Muốn xem trạng thái hiện tại, dùng `/list`; muốn kiểm tra mọi snippet, dùng `/list -all`.

### Mất code sau /reset

`/reset` xóa code đã nhập khỏi execution state. Hãy dùng `/save` trước khi reset nếu muốn giữ các snippet đang hoạt động.

### /reload làm thao tác chạy hai lần

`/reload` phát lại các snippet hợp lệ. Nếu code có ghi file, cập nhật database hoặc gọi API, các hành động đó có thể được lặp lại. Kiểm tra lịch sử và tác dụng phụ trước khi reload.

### /open hoặc /save không tìm thấy file

Đường dẫn được xử lý theo môi trường hệ điều hành và thư mục làm việc hiện tại. Dùng đường dẫn chính xác, kiểm tra quyền đọc/ghi và tránh nhầm dấu phân cách đường dẫn. Nếu đường dẫn có khoảng trắng, xem cú pháp mà phiên bản JShell hỗ trợ; không giả định mọi lệnh slash xử lý dấu nháy giống shell.

### Editor không mở

Kiểm tra `/set editor`, sau đó kiểm tra các biến môi trường `JSHELLEDITOR`, `VISUAL` và `EDITOR`. Nếu không có editor ngoài được cấu hình, JShell có thể dùng trình soạn thảo đơn giản tích hợp.

## 12. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
|---|---|
| Xem tất cả trợ giúp | `/help` hoặc `/?` |
| Xem trợ giúp một lệnh | `/help /list` |
| Xem snippet đang hoạt động | `/list` |
| Xem cả snippet cũ/lỗi/drop | `/list -all` |
| Xem biến | `/vars` |
| Xem method | `/methods` |
| Xem kiểu | `/types` |
| Xem import | `/imports` |
| Xem lịch sử nhập | `/history` |
| Sửa snippet | `/edit <id>` |
| Drop snippet | `/drop <id>` |
| Lưu code đang hoạt động | `/save file.jsh` |
| Lưu toàn bộ history | `/save -history file.txt` |
| Nạp file | `/open file.jsh` |
| Chạy lại snippet gần nhất | `/!` |
| Chạy lại theo ID | `/<id>` |
| Đổi classpath | `/env -class-path <path>` |
| Xem evaluation context | `/env` |
| Phát lại snippet | `/reload` |
| Khôi phục history trước | `/reload -restore` |
| Xóa trạng thái phiên | `/reset` |
| Đổi feedback | `/set feedback concise` |
| Thoát JShell | `/exit` |

## 13. Checklist sử dụng JShell hiệu quả

- [ ] Dùng `/help` để kiểm tra cú pháp lệnh trên JDK hiện tại.
- [ ] Dùng `/list`, `/vars`, `/methods`, `/types` để hiểu trạng thái phiên.
- [ ] Dùng `/history` để tìm lại các thao tác đã nhập.
- [ ] Dùng `/edit` để chỉnh snippet dài thay vì nhập lại nhiều lần.
- [ ] Dùng `/drop` để loại khai báo thử nghiệm không còn cần thiết.
- [ ] Dùng `/save` để lưu snippet đang hoạt động trước khi reset.
- [ ] Dùng `/open` để nạp lại script theo đúng thứ tự phụ thuộc.
- [ ] Dùng `/env` khi cần thay đổi classpath hoặc module path.
- [ ] Kiểm tra tác dụng phụ trước `/!`, rerun hoặc `/reload`.
- [ ] Dùng `/set feedback` và `/set start` để điều chỉnh trải nghiệm làm việc.
- [ ] Dùng `/exit` để kết thúc phiên sau khi đã lưu code cần giữ.
