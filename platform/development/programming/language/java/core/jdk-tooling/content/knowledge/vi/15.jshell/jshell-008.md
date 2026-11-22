# Lưu và tải session trong JShell

## 1. Session trong JShell là gì?

**JShell** là công cụ tương tác REPL (Read-Eval-Print Loop) của JDK. Bạn có thể nhập biểu thức, khai báo biến, method, class và chạy chúng ngay mà không cần tạo project Java hoàn chỉnh.

Một **JShell session** là trạng thái làm việc trong một tiến trình JShell đang chạy. Trạng thái này gồm các snippet đã nhập hoặc tải, những khai báo đang hoạt động và execution state mà JShell duy trì trong tiến trình đó.

Ví dụ, trong cùng một session:

~~~java
String project = "Java";
int version = 17;

int nextVersion(int current) {
    return current + 1;
}

nextVersion(version)
~~~

Các khai báo có thể được sử dụng ở những snippet tiếp theo. Nếu thoát JShell, tiến trình kết thúc và trạng thái runtime trong bộ nhớ sẽ không còn.

Để tiếp tục công việc ở lần chạy sau, JShell cung cấp các lệnh lưu source/history và nạp lại nội dung. Những lệnh quan trọng nhất là:

- **/save:** lưu source của các snippet đang hoạt động.
- **/save -history:** lưu tuần tự các lệnh và snippet đã nhập trong session hiện tại.
- **/open:** đọc file hoặc URL như input của JShell.
- **/reload:** reset rồi chạy lại lịch sử hợp lệ trong session hiện tại.
- **/reload -restore:** khôi phục phần lịch sử trước một lần reset/reload/env trong cùng tiến trình.

Cần phân biệt việc lưu source để chạy lại với việc chụp toàn bộ bộ nhớ của JVM. JShell lưu nội dung có thể thực thi lại; nó không tạo snapshot của object graph, thread, socket, file handle hoặc trạng thái bên ngoài.

## 2. Khởi động JShell và tạo session

Kiểm tra JDK và JShell:

~~~bash
java --version
jshell --version
~~~

Khởi động chế độ tương tác:

~~~bash
jshell
~~~

Có thể chọn feedback mode ngay khi khởi động:

~~~bash
jshell --feedback concise
~~~

Các feedback mode có sẵn gồm:

| Mode | Mục đích |
|---|---|
| silent | Giảm tối đa thông báo feedback của JShell; output do chương trình tự in vẫn xuất hiện. |
| concise | Feedback ngắn gọn, phù hợp khi làm việc thường ngày. |
| normal | Feedback mặc định, cân bằng giữa thông tin và độ gọn. |
| verbose | Hiển thị nhiều thông tin hơn về snippet và kết quả. |

Trong session, nhập các snippet theo từng dòng hoặc theo khối:

~~~java
String course = "Java Core";
int lessons = 12;

int remaining(int completed) {
    return lessons - completed;
}

System.out.println(course + ": " + remaining(5) + " lessons left");
~~~

JShell đánh giá snippet ngay khi nhận được một khai báo hoặc biểu thức hoàn chỉnh. Biến, method và class đã khai báo có thể được sử dụng ở các snippet sau trong cùng session.

Lệnh slash như /list, /save, /open và /exit là lệnh điều khiển của JShell, không phải câu lệnh Java. Không đặt dấu chấm phẩy ở cuối lệnh slash.

## 3. Xem snippet và lịch sử trước khi lưu

Trước khi lưu, nên xem nội dung nào đang tồn tại.

Lệnh:

~~~text
/list
~~~

/list hiển thị các snippet đang hoạt động cùng snippet ID. Các ID này hữu ích khi muốn lưu một phần session.

Xem toàn bộ snippet, gồm cả snippet lỗi, bị ghi đè, đã drop và startup:

~~~text
/list -all
~~~

Xem lịch sử nhập trong session hiện tại:

~~~text
/history
~~~

Xem lịch sử từ session hiện tại và các session trước:

~~~text
/history -all
~~~

Hai lệnh /list và /history trả lời hai câu hỏi khác nhau:

- /list cho biết các snippet đang có hoặc đã từng tồn tại.
- /history cho biết chuỗi lệnh và snippet được nhập theo thời gian.

Một snippet có thể được sửa hoặc thay thế trong quá trình làm việc. Vì vậy, nội dung trong lịch sử không nhất thiết giống danh sách snippet đang hoạt động. Hãy chọn loại dữ liệu cần lưu trước khi dùng /save.

## 4. Lưu các snippet đang hoạt động bằng /save

Cú pháp cơ bản:

~~~text
/save <file>
~~~

Lệnh này lưu source của các snippet đang hoạt động vào file chỉ định. Ví dụ:

~~~text
/save java-session.jsh
~~~

File **java-session.jsh** chứa source để có thể nạp lại trong JShell. Phần mở rộng .jsh là quy ước dễ nhận biết cho JShell script; tên file khác vẫn có thể dùng nếu nội dung phù hợp.

Lệnh /save thông thường tập trung vào các snippet hiện đang active. Nó phù hợp khi muốn lưu những khai báo có ích để tiếp tục sử dụng, chẳng hạn:

- Import cần thiết.
- Biến và hằng số phục vụ thử nghiệm.
- Method helper.
- Class hoặc record được khai báo trong REPL.
- Các biểu thức hoặc câu lệnh mà bạn muốn chạy lại.

Nếu một snippet đã bị thay thế, bị drop hoặc không biên dịch được, nó không thuộc tập snippet active thông thường. Khi cần giữ cả các trường hợp đó, xem /save -all hoặc /save -history.

Lưu ý: /save ghi source vào file theo đường dẫn mà JShell nhận được. Hãy kiểm tra thư mục làm việc hiện tại để biết file được tạo ở đâu; đường dẫn tương đối được tính từ working directory của tiến trình JShell.

## 5. Lưu toàn bộ snippet bằng /save -all

Cú pháp:

~~~text
/save -all <file>
~~~

Tùy chọn -all lưu source của tất cả snippet, bao gồm:

- Snippet đang hoạt động.
- Snippet đã bị ghi đè.
- Snippet lỗi hoặc không hợp lệ.
- Snippet đã drop.
- Startup code.

Ví dụ:

~~~text
/save java-session-all.jsh
/save -all java-session-complete.jsh
~~~

Lệnh đầu chỉ lưu tập snippet active; lệnh thứ hai lưu thêm những snippet không còn active và startup code.

Dùng -all khi cần lưu dấu vết đầy đủ để xem lại cách thử nghiệm đã diễn ra. File này có thể chứa source lỗi hoặc khai báo trùng, vì vậy không phải lúc nào cũng là script sạch để nạp lại trong một session mới.

Nếu mục tiêu là tạo một file có thể chạy lại ổn định, hãy ưu tiên /save cho snippet active, rồi đọc lại file và kiểm tra thứ tự khai báo trước khi dùng.

## 6. Lưu lịch sử lệnh bằng /save -history

Cú pháp:

~~~text
/save -history <file>
~~~

Ví dụ:

~~~text
/save -history java-session-history.jsh
~~~

Tùy chọn -history lưu lịch sử tuần tự của các lệnh và snippet đã nhập kể từ khi JShell tool được khởi chạy trong session hiện tại.

Khác biệt chính:

| Cách lưu | Nội dung |
|---|---|
| /save file | Source của snippet đang hoạt động. |
| /save -all file | Source của mọi snippet, kể cả failed, overwritten, dropped và startup. |
| /save -history file | Lịch sử tuần tự của lệnh và snippet đã nhập trong session hiện tại. |
| /save -start file | Các startup definition hiện tại. |

History hữu ích khi cần tái hiện quá trình thử nghiệm, kể cả các bước điều chỉnh và lệnh slash. Tuy nhiên, nó có thể chứa lệnh điều khiển, snippet lỗi, thao tác ghi file hoặc hành động bên ngoài. Đọc và rà soát file history trước khi nạp lại.

Lệnh /history -all có thể hiển thị lịch sử của các session trước, nhưng /save -history được mô tả là lưu lịch sử từ lúc JShell tool hiện tại được khởi chạy. Không nên giả định một lần /save -history sẽ xuất toàn bộ lịch sử của mọi tiến trình JShell từng chạy.

## 7. Lưu một hoặc một nhóm snippet theo ID

Nếu chỉ muốn lưu một phần session, dùng snippet ID:

~~~text
/save <id> <file>
~~~

Ví dụ, xem ID:

~~~text
/list
~~~

Sau đó lưu một snippet:

~~~text
/save 3 selected-snippet.jsh
~~~

Có thể lưu nhiều ID hoặc một khoảng ID:

~~~text
/save 1-4 selected-snippets.jsh
~~~

Cách này hữu ích khi session có nhiều thử nghiệm nhưng chỉ một nhóm khai báo cần chia sẻ. Trước khi chọn ID, hãy xem /list để tránh lưu nhầm snippet cũ hoặc snippet không còn active.

Các ID thuộc session cụ thể. Không nên giả định ID của một snippet sẽ giống nhau sau khi mở file trong session mới, vì JShell tạo snippet ID theo quá trình nạp và đánh giá lại.

## 8. Nạp file bằng /open

Cú pháp:

~~~text
/open <file>
~~~

Ví dụ:

~~~text
/open java-session.jsh
~~~

JShell đọc file và xử lý nội dung như input của công cụ. File có thể chứa source snippet và các lệnh JShell phù hợp. Các khai báo được đánh giá theo thứ tự xuất hiện trong file.

Lệnh /open cũng hỗ trợ URL:

~~~text
/open https://example.org/scripts/java-session.jsh
~~~

Khi mở URL, JShell tải nội dung và sử dụng nó làm input. Chỉ mở file hoặc URL từ nguồn đáng tin cậy, vì snippet Java và lệnh JShell có thể thực thi code trong tiến trình của bạn.

Có thể nạp nhiều file khi khởi động JShell:

~~~bash
jshell java-session.jsh
~~~

Hoặc kết hợp với feedback mode:

~~~bash
jshell --feedback silent java-session.jsh
~~~

Cách này thuận tiện cho script cần chạy lại từ đầu hoặc smoke test đơn giản. Nếu muốn tải nội dung vào một JShell đang mở, dùng /open thay vì khởi động tiến trình mới.

Nếu file khai báo lại tên biến, method hoặc class đã tồn tại trong session hiện tại, JShell có thể báo lỗi hoặc tạo trạng thái khác với mong đợi. Khi muốn phát lại toàn bộ file, nên dùng một session mới hoặc reset session trước khi nạp.

## 9. Ví dụ hoàn chỉnh: lưu và mở lại session

Tạo một session tương tác:

~~~bash
jshell --feedback concise
~~~

Nhập các snippet:

~~~java
String project = "JShell";
int attempts = 3;

int retryDelay(int attempt) {
    return attempt * 2;
}

System.out.println(project + " / delay=" + retryDelay(attempts));
~~~

Lưu các snippet đang hoạt động:

~~~text
/save jshell-session.jsh
~~~

Thoát session:

~~~text
/exit
~~~

Mở một tiến trình JShell mới và tải file đã lưu:

~~~bash
jshell --feedback silent jshell-session.jsh
~~~

Stdout của ví dụ:

~~~text
JShell / delay=6
~~~

Ví dụ này đã được kiểm tra với JShell 24.0.2. File script chứa các khai báo và câu lệnh Java; khi mở file, JShell đánh giá lại chúng và câu lệnh println in kết quả.

Có thể thực hiện tương tự trong một session mới bằng lệnh:

~~~text
/open jshell-session.jsh
~~~

Điểm cần nhớ là kết quả được tạo lại bằng cách chạy source. Đây không phải bản ghi nhớ giá trị của biến từ tiến trình cũ.

## 10. Khôi phục lịch sử trong cùng tiến trình bằng /reload

/ reload không phải lệnh đọc file đã lưu. Nó làm việc với lịch sử snippet của JShell tool hiện tại.

Cú pháp:

~~~text
/reload
~~~

Lệnh này reset code và execution state, sau đó phát lại các snippet hợp lệ cùng các lệnh /drop theo thứ tự đã nhập kể từ lúc JShell được khởi chạy hoặc từ lần /reset hay /reload gần nhất.

Có thể dùng khi muốn chạy lại các khai báo từ đầu sau khi thử nghiệm hoặc khi trạng thái hiện tại không còn nhất quán.

Tùy chọn -restore:

~~~text
/reload -restore
~~~

-restore khôi phục và phát lại lịch sử trước đó trong cùng tiến trình, tính từ mốc JShell được khởi chạy hoặc mốc /reset, /reload hay /env gần nhất. Nó hữu ích khi muốn phục hồi phần session trước một thao tác reset hoặc thay đổi evaluation context.

Có thể giảm feedback trong lúc replay:

~~~text
/reload -quiet
/reload -restore -quiet
~~~

Tùy chọn -quiet ẩn phần replay thông thường nhưng lỗi vẫn được hiển thị.

Không thể dùng /reload sau khi đã thoát hoàn toàn khỏi tiến trình cũ để khôi phục bộ nhớ của tiến trình đó. Muốn tiếp tục ở một tiến trình mới, hãy lưu source/history ra file rồi dùng /open hoặc truyền file khi khởi động.

## 11. Phân biệt /reset, /reload và /reload -restore

Ba lệnh này có tác động khác nhau:

| Lệnh | Tác động |
|---|---|
| /reset | Xóa code đã nhập, khởi động lại execution state và chạy lại startup code. |
| /reload | Reset rồi phát lại lịch sử hợp lệ kể từ mốc gần nhất. |
| /reload -restore | Phát lại phần lịch sử trước mốc reset/reload/env gần nhất để khôi phục session trước đó trong cùng tiến trình. |

Ví dụ:

~~~text
int base = 10;
base * 2
/reset
~~~

Sau /reset, khai báo base không còn trong session hiện tại. Nếu cần khôi phục các snippet trước lần reset, có thể dùng:

~~~text
/reload -restore
~~~

Lệnh /reset có thể làm mất các khai báo đang có và khởi động lại execution state. Nếu chưa chắc có thể dựng lại trạng thái, hãy lưu source trước khi reset.

Không nên coi /reload là thao tác undo cho mọi tác động. Nếu snippet đã ghi file, gửi request mạng, cập nhật database hoặc thay đổi hệ thống bên ngoài, replay có thể thực hiện hành động đó lần nữa.

## 12. Lưu startup definitions và dùng lại khi khởi động

JShell có startup definitions, tức các khai báo được nạp khi công cụ bắt đầu. Có thể lưu các startup definition hiện tại bằng:

~~~text
/save -start jshell-startup.jsh
~~~

Sau đó dùng file startup khi khởi động một lần:

~~~bash
jshell --startup jshell-startup.jsh
~~~

Tùy chọn --startup thay thế startup definitions mặc định cho lần chạy đó. Nếu muốn bỏ startup definitions mặc định mà không cung cấp file thay thế, có thể dùng:

~~~bash
jshell --no-startup
~~~

Startup file phù hợp cho helper import, method hoặc class dùng lặp lại trong nhiều buổi làm việc. Ví dụ, một nhóm có thể chuẩn bị startup file chứa helper để định dạng JSON hoặc tạo dữ liệu thử nghiệm.

Startup definitions khác với session file:

- Startup file chuẩn bị môi trường khai báo chung khi JShell khởi động.
- Session file chứa snippet và lệnh của một bài thực hành hoặc công việc cụ thể.
- History file lưu lại chuỗi thao tác đã nhập.

Nên tách helper dùng chung khỏi các lệnh thử nghiệm có side effect để startup file dễ tái sử dụng.

## 13. Nạp lại session có dependency và evaluation context

File session có thể sử dụng thư viện bên ngoài hoặc module. Khi nạp lại, JShell phải được khởi động với classpath/module path phù hợp.

Ví dụ thư viện JAR trong thư mục lib:

~~~bash
jshell --class-path "lib/example.jar" java-session.jsh
~~~

Nếu có nhiều thư mục hoặc JAR trên Windows, dùng dấu chấm phẩy để phân tách classpath:

~~~powershell
jshell --class-path "lib\one.jar;lib\two.jar" java-session.jsh
~~~

Trên Linux/macOS, dấu phân tách classpath thường là dấu hai chấm:

~~~bash
jshell --class-path "lib/one.jar:lib/two.jar" java-session.jsh
~~~

Với module:

~~~bash
jshell --module-path mods --add-modules com.example.lib java-session.jsh
~~~

Ngoài dependency, cần chú ý:

- JDK version và API mà snippet sử dụng.
- Preview feature có được bật bằng --enable-preview hay không.
- JVM option dành cho runtime của JShell.
- Compiler option được truyền bằng -C.
- Runtime option dành riêng cho việc chạy snippet bằng -R.
- Working directory, biến môi trường và file resource mà snippet truy cập.

Ví dụ bật preview feature:

~~~bash
jshell --enable-preview --source 24 java-session.jsh
~~~

Tùy phiên bản JDK, tùy chọn source/preview phải phù hợp với release đang dùng. Kiểm tra jshell --help của JDK mục tiêu trước khi dùng trong script tự động.

Không phải mọi evaluation context đều được lưu trong file /save. Khi mở lại, hãy truyền lại classpath, module path, module cần resolve và các option phù hợp.

## 14. Thiết kế session file dễ tái sử dụng

Một session file tốt nên có cấu trúc rõ ràng và có thể chạy lại từ đầu.

Ví dụ:

~~~java
// 1. Imports
import java.time.LocalDate;

// 2. Shared values
String projectName = "Java Core";
LocalDate today = LocalDate.now();

// 3. Helper methods
String label(String name) {
    return projectName + " / " + name;
}

// 4. Demonstration
System.out.println(label(today.toString()));
~~~

Nên sắp xếp theo thứ tự:

1. Import.
2. Hằng số và biến cấu hình.
3. Method helper.
4. Class/record hỗ trợ.
5. Snippet thực hành hoặc câu lệnh chạy demo.

Nếu session có nhiều bước, có thể chia thành nhiều file:

~~~text
jshell-lab/
├── 01-imports.jsh
├── 02-models.jsh
├── 03-helpers.jsh
└── 04-demo.jsh
~~~

Nạp theo thứ tự:

~~~text
/open 01-imports.jsh
/open 02-models.jsh
/open 03-helpers.jsh
/open 04-demo.jsh
~~~

Hoặc truyền nhiều load file khi khởi động JShell:

~~~bash
jshell --feedback concise 01-imports.jsh 02-models.jsh 03-helpers.jsh 04-demo.jsh
~~~

Chỉ chia file khi điều đó làm rõ trách nhiệm và thứ tự phụ thuộc. Với session ngắn, một file duy nhất thường dễ quản lý hơn.

## 15. Side effect và an toàn khi phát lại session

Mở file hoặc replay lịch sử có nghĩa là thực thi lại snippet. Điều này quan trọng nếu session chứa lệnh có tác động bên ngoài.

Ví dụ:

~~~java
Files.writeString(Path.of("result.txt"), "done");
~~~

Mỗi lần snippet này được chạy, file result.txt có thể bị ghi lại. Một snippet gửi HTTP request hoặc ghi database cũng có thể tạo tác động mới khi được mở lại.

Trước khi dùng /open, /reload hoặc nạp history file, hãy xem xét:

- Có lệnh xóa, ghi đè hoặc di chuyển file không?
- Có request gửi đến dịch vụ bên ngoài không?
- Có thao tác insert/update/delete database không?
- Có gửi email, message hoặc kích hoạt job không?
- Có đọc token, password hoặc dữ liệu cá nhân từ file/environment không?
- Có snippet nào phụ thuộc vào trạng thái chỉ tồn tại ở lần chạy trước không?

Không lưu secret trực tiếp vào session file hoặc history. Dùng biến môi trường hoặc cơ chế cấp phát secret phù hợp, đồng thời bảo vệ quyền truy cập file session.

Không mở JShell script từ URL không tin cậy. Nội dung tải về có thể chứa Java code và lệnh điều khiển; việc mở file có thể thực thi chúng trong quyền của người dùng hiện tại.

## 16. Lỗi thường gặp khi lưu và tải session

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| /open không tìm thấy file | Đường dẫn tương đối được tính từ working directory khác dự kiến. | Kiểm tra thư mục hiện tại hoặc dùng đường dẫn đầy đủ. |
| Nạp file nhưng biến không tồn tại | Snippet khai báo biến lỗi hoặc không được đánh giá thành công. | Xem feedback, /list và nội dung file. |
| Method hoặc class bị khai báo trùng | File được /open trong session đã có các khai báo cùng tên. | Dùng session mới hoặc /reset trước khi nạp. |
| /save không chứa snippet vừa thử | Snippet lỗi, bị drop hoặc không còn active. | Dùng /list -all hoặc /save -history nếu cần giữ lịch sử. |
| File history nạp lại có nhiều lỗi | History chứa snippet cũ, lệnh điều khiển hoặc code thử nghiệm không còn phù hợp. | Rà soát file history và tạo session script sạch. |
| Mở lại session không tìm thấy thư viện | Không truyền lại classpath hoặc module path. | Khởi động với --class-path, --module-path và --add-modules cần thiết. |
| Kết quả khác lần chạy trước | JDK, dependency, working directory, dữ liệu bên ngoài hoặc thời gian đã thay đổi. | Ghi rõ môi trường và dữ liệu đầu vào cần thiết. |
| /reload không khôi phục sau khi đóng JShell | /reload chỉ dùng lịch sử của tiến trình hiện tại. | Lưu source/history trước /exit và nạp lại ở tiến trình mới. |
| Replay làm ghi file hoặc cập nhật dữ liệu lần nữa | Snippet có side effect. | Rà soát source, dùng dữ liệu thử nghiệm và thiết kế thao tác idempotent. |
| Startup helper không xuất hiện | JShell được khởi động với --no-startup hoặc startup file khác. | Kiểm tra --startup và cấu hình khởi động. |
| Tên snippet ID thay đổi | ID được cấp lại khi file được nạp trong session khác. | Tìm lại ID bằng /list sau khi nạp. |

## 17. Quy trình lưu, kiểm tra và khôi phục session

Một quy trình an toàn cho công việc thông thường:

1. Dùng /list để kiểm tra snippet active.
2. Dùng /history nếu cần xem lại chuỗi thao tác.
3. Chọn /save để lưu source active hoặc /save -history để lưu quá trình thử nghiệm.
4. Kiểm tra file vừa lưu, loại bỏ lệnh thừa và secret nếu cần chia sẻ.
5. Ghi nhận JDK version, dependency, classpath/module path và các option cần thiết.
6. Mở một tiến trình JShell mới và nạp file bằng lệnh jshell file.jsh hoặc /open file.jsh.
7. Xác nhận snippet được nạp và kết quả demo đúng.
8. Chỉ dùng /reload -restore khi cần khôi phục lịch sử trong cùng tiến trình.
9. Sau khi sửa session file, chạy lại từ đầu để xác nhận file có thể tái lập kết quả.
10. Lưu session file trong version control nếu đây là tài liệu thực hành hoặc quy trình dùng chung.

Với script dùng trong CI, nên ưu tiên lệnh chạy file khi khởi động, chọn feedback mode phù hợp và kiểm tra exit code. Tránh phụ thuộc vào prompt tương tác hoặc thao tác thủ công.

## 18. Checklist khi làm việc với JShell session

- [ ] Đã phân biệt session runtime với file lưu source/history.
- [ ] Đã dùng /list và /history để hiểu nội dung cần lưu.
- [ ] Đã chọn đúng giữa /save, /save -all, /save -history và /save -start.
- [ ] Đã dùng snippet ID đúng nếu chỉ lưu một phần.
- [ ] Đã biết /open nạp file hoặc URL như input của JShell.
- [ ] Đã kiểm tra file trước khi replay vì snippet có thể thực thi lại side effect.
- [ ] Đã phân biệt /reload với /reload -restore và /reset.
- [ ] Đã biết /reload chỉ hoạt động trong tiến trình hiện tại.
- [ ] Đã truyền lại classpath/module path và các option cần thiết.
- [ ] Đã phân biệt startup file với session file.
- [ ] Đã tránh lưu secret trong file session/history.
- [ ] Đã mở lại file trong một session mới để kiểm tra khả năng tái lập.

JShell lưu và tải session bằng cách lưu source hoặc lịch sử rồi đánh giá lại chúng trong một tiến trình. Khi chọn đúng loại /save, rà soát file trước /open và giữ lại dependency/evaluation context cần thiết, bạn có thể tái sử dụng các thử nghiệm Java một cách có kiểm soát.