# Khởi động JShell

**JShell** là công cụ REPL (Read-Eval-Print Loop) đi kèm JDK, cho phép nhập và chạy trực tiếp biểu thức, câu lệnh, khai báo biến, method và class Java mà không cần tạo project hoặc viết phương thức main trước. JShell có từ JDK 9, phù hợp để học Java, thử API, kiểm tra đoạn code nhỏ và tạo prototype nhanh.

Khởi động JShell rất đơn giản: mở terminal, gọi lệnh jshell, sau đó nhập Java snippet tại dấu nhắc. JShell biên dịch và thực thi snippet khi nhận được một đơn vị cú pháp hoàn chỉnh, rồi hiển thị kết quả hoặc thông báo lỗi.

## 1. Điều kiện trước khi khởi động

JShell được phân phối cùng JDK, không phải một ứng dụng độc lập cần tải riêng. Cần cài JDK 9 trở lên; với dự án hiện đại, nên dùng phiên bản JDK mà nhóm phát triển đang hỗ trợ, ví dụ JDK 17 hoặc JDK 21.

Kiểm tra Java runtime, compiler và JShell:

~~~bash
java -version
javac -version
jshell --version
~~~

Các lệnh java, javac và jshell nên trỏ tới cùng một bộ JDK để tránh trường hợp compiler và công cụ tương tác dùng phiên bản khác nhau. Nếu máy có nhiều JDK, kiểm tra đường dẫn thực tế của từng lệnh.

Windows PowerShell:

~~~powershell
Get-Command java
Get-Command javac
Get-Command jshell
~~~

Linux/macOS:

~~~bash
which java
which javac
which jshell
~~~

Nếu terminal báo không tìm thấy jshell:

1. Xác nhận đã cài JDK 9 trở lên, không chỉ cài một JRE cũ.
2. Kiểm tra biến JAVA_HOME trỏ tới thư mục gốc của JDK.
3. Thêm thư mục bin của JDK vào PATH.
4. Mở terminal mới rồi kiểm tra lại jshell --version.
5. Nếu máy có nhiều JDK, đặt PATH theo JDK muốn sử dụng và kiểm tra lại vị trí của cả java, javac và jshell.

Ví dụ đường dẫn thường gặp:

- Windows: C:\Program Files\Java\jdk-21\bin
- Linux: /usr/lib/jvm/jdk-21/bin
- macOS: /Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/bin

Tên thư mục và vị trí cài đặt thực tế tùy cách cài JDK. Không sao chép nguyên các đường dẫn minh họa nếu chúng không tồn tại trên máy.

## 2. Khởi động phiên JShell tương tác

Mở Command Prompt, PowerShell, Terminal hoặc shell tương ứng, rồi nhập:

~~~bash
jshell
~~~

JShell hiển thị thông báo chào mừng, phiên bản và dấu nhắc để nhập snippet. Nội dung welcome cụ thể thay đổi theo phiên bản JDK.

Ví dụ phiên làm việc:

~~~text
$ jshell
|  Welcome to JShell -- Version 21
|  For an introduction type: /help intro

jshell>
~~~

Dấu nhắc jshell> cho biết JShell đang chờ lệnh hoặc Java snippet. Nhập biểu thức:

~~~java
2 + 3
~~~

JShell đánh giá biểu thức và hiển thị kết quả. Một phiên bản feedback có thể hiển thị:

~~~text
jshell> 2 + 3
$1 ==> 5
~~~

Tên biến tạm như $1 là do JShell tự tạo để lưu kết quả biểu thức chưa được gán cho biến. Số ID phụ thuộc các snippet đã nhập trong phiên; không nên dựa vào một số ID cố định trong tài liệu hoặc script.

Để in thông điệp:

~~~java
System.out.println("Hello, JShell!");
~~~

Kết quả do chương trình in:

~~~text
Hello, JShell!
~~~

Không cần khai báo class hoặc phương thức main cho những phép thử đơn giản như vậy.

## 3. Nhập snippet đầu tiên

JShell nhận nhiều loại snippet của ngôn ngữ Java:

- Biểu thức, ví dụ 10 * 5.
- Câu lệnh, ví dụ System.out.println("Hello").
- Khai báo biến, ví dụ int count = 3.
- Khai báo method.
- Khai báo class, interface, enum hoặc record.
- Câu lệnh import.

Ví dụ một phiên làm việc ngắn:

~~~text
jshell> int quantity = 4
quantity ==> 4

jshell> int price = 25000
price ==> 25000

jshell> int total = quantity * price
total ==> 100000

jshell> System.out.println("Total = " + total)
Total = 100000
~~~

Sau khi khai báo, biến vẫn tồn tại trong trạng thái của phiên. Có thể sử dụng lại trong các snippet tiếp theo:

~~~java
total + 5000
~~~

Kết quả là 105000. JShell giữ trạng thái giữa các lần nhập cho đến khi phiên được reset hoặc kết thúc.

### Dấu chấm phẩy

Với snippet đã hoàn chỉnh, JShell có thể tự thêm dấu chấm phẩy nếu người dùng bỏ quên. Tuy vậy, nên viết dấu chấm phẩy theo quy ước Java để code dễ chuyển sang file .java và tránh nhầm khi nhập nhiều câu lệnh.

Ví dụ:

~~~java
int a = 10;
int b = 20;
System.out.println(a + b);
~~~

Một snippet có nhiều câu lệnh có thể được nhập thành nhiều dòng; JShell tiếp tục chờ cho tới khi cú pháp hoàn chỉnh.

## 4. Khai báo method và class ngay trong phiên

Không cần tạo file riêng để thử method. Ví dụ:

~~~java
int square(int value) {
    return value * value;
}
~~~

Sau khi JShell xác nhận method đã được tạo, gọi thử:

~~~java
square(6)
~~~

Kết quả:

~~~text
$2 ==> 36
~~~

ID kết quả có thể khác tùy phiên. Method có thể được gọi từ các snippet sau đó mà không cần biên dịch lại toàn bộ project.

Có thể khai báo class:

~~~java
class Product {
    String name;
    int price;

    Product(String name, int price) {
        this.name = name;
        this.price = price;
    }

    int priceWithTax(int tax) {
        return price + tax;
    }
}
~~~

Tạo object và gọi method:

~~~java
Product item = new Product("Notebook", 30000);
item.priceWithTax(3000)
~~~

Kết quả của biểu thức cuối là 33000. JShell hữu ích để thử nhanh cấu trúc class, constructor và method trước khi đưa code vào project.

## 5. Nhập nhiều dòng và hoàn tất snippet

Khi nhập một khai báo chưa hoàn chỉnh, JShell chuyển sang dấu nhắc tiếp dòng thường hiển thị là ...>.

Ví dụ:

~~~text
jshell> int add(int a, int b) {
   ...>     return a + b;
   ...> }
|  created method add(int,int)

jshell> add(7, 8)
$1 ==> 15
~~~

Dấu nhắc tiếp dòng cho biết JShell đang chờ phần còn lại của snippet, chẳng hạn dấu đóng ngoặc nhọn hoặc câu lệnh tiếp theo. Khi cú pháp hoàn chỉnh, JShell xử lý toàn bộ khai báo.

Nếu nhập sai, JShell hiển thị diagnostic từ compiler. Đọc vị trí và thông báo lỗi, sửa snippet rồi nhập lại. Với method hoặc class đã khai báo, có thể nhập lại định nghĩa để thay thế phiên bản đang hoạt động.

## 6. Phân biệt Java snippet và JShell command

Trong JShell có hai dạng đầu vào:

| Dạng | Nhận biết | Ví dụ | Mục đích |
|---|---|---|---|
| Java snippet | Cú pháp Java bình thường | int x = 10; | Biên dịch và thực thi code |
| JShell command | Bắt đầu bằng dấu / | /help | Điều khiển phiên và quản lý snippet |

Một số command hữu ích ngay khi mới khởi động:

| Command | Công dụng |
|---|---|
| /help | Liệt kê command và chủ đề trợ giúp |
| /help intro | Giới thiệu cách sử dụng JShell |
| /list | Liệt kê snippet đang hoạt động |
| /vars | Xem biến đã khai báo |
| /methods | Xem method đã khai báo |
| /types | Xem class/interface/enum đã khai báo |
| /imports | Xem import hiện hành |
| /history | Xem lịch sử nhập trong phiên |
| /reset | Xóa trạng thái snippet và khởi động lại môi trường |
| /exit | Thoát JShell |

Ví dụ:

~~~text
jshell> /help intro
~~~

Để xem những import được nạp tự động khi bắt đầu:

~~~text
jshell> /list -start
~~~

JShell có startup script mặc định chứa một số import thường dùng như java.util và java.io. Package java.lang được Java tự động import nên không cần khai báo lại.

Dấu / ở đầu command giúp JShell phân biệt lệnh điều khiển với Java source. Nếu muốn viết biểu thức hoặc statement, hãy nhập cú pháp Java thông thường.

## 7. Điều chỉnh mức feedback khi khởi động

Feedback quyết định mức thông tin JShell hiển thị sau khi nhập snippet. Có thể chọn ngay từ command line bằng --feedback:

~~~bash
jshell --feedback verbose
~~~

Các chế độ chính:

| Mode | Hành vi |
|---|---|
| verbose | Hiển thị chi tiết về snippet và hành động được thực hiện |
| normal | Mức thông tin trung bình; là mặc định |
| concise | Feedback tối giản |
| silent | Ẩn feedback thông thường; diagnostic lỗi vẫn được hiển thị |

Có các dạng viết tắt:

~~~bash
jshell -v
jshell -q
jshell -s
~~~

Tương ứng:

- -v chọn verbose.
- -q chọn concise.
- -s chọn silent.

Có thể thay đổi mode sau khi đã vào phiên:

~~~text
jshell> /set feedback verbose
~~~

Khi học hoặc debug, verbose hữu ích vì cho biết snippet được tạo, sửa hoặc đánh giá như thế nào. Khi chạy script hoặc muốn output gọn, concise hoặc silent có thể phù hợp hơn.

## 8. Khởi động JShell với classpath

Nếu cần sử dụng class nằm trong thư mục đã biên dịch hoặc JAR bên ngoài, hãy chỉ định classpath khi khởi động.

Ví dụ:

~~~bash
jshell --class-path lib/example.jar
~~~

Tùy chọn --class-path chỉ định thư mục và archive được tìm để tải class file. Nó ghi đè giá trị CLASSPATH environment variable. Nếu không có CLASSPATH và không truyền tùy chọn này, thư mục hiện tại được tìm kiếm.

Nếu có nhiều dependency:

Linux/macOS:

~~~bash
jshell --class-path "lib/a.jar:lib/b.jar:build/classes"
~~~

Windows:

~~~powershell
jshell --class-path "lib\a.jar;lib\b.jar;build\classes"
~~~

Dấu phân cách là dấu hai chấm trên Linux/macOS và dấu chấm phẩy trên Windows. Đặt toàn bộ classpath trong dấu nháy để shell không diễn giải các ký tự đặc biệt.

Nếu class không được tìm thấy, kiểm tra:

1. JAR có chứa đúng class và package path không.
2. Classpath có trỏ tới đúng JAR hoặc thư mục gốc của package không.
3. Tên class trong import có đúng package không.
4. Dependency bắc cầu có được cung cấp không.
5. JAR có tương thích với phiên bản Java đang chạy không.

## 9. Khởi động với module path

Nếu cần dùng named module, chỉ định module path:

~~~bash
jshell --module-path mods
~~~

Có thể yêu cầu resolve thêm module:

~~~bash
jshell --module-path mods --add-modules com.acme.library
~~~

Module path dùng để tìm application modules. Nó khác classpath: classpath thường chứa class/JAR thuộc unnamed module, còn module path chứa named module hoặc automatic module.

Nếu JShell không tìm thấy module, kiểm tra:

- Tên module trong module-info.java.
- Module đã được biên dịch và nằm đúng thư mục chưa.
- Đường dẫn mods có chứa module directory hoặc modular JAR cần thiết không.
- Module dependency có được resolve không.
- Package cần dùng đã được module cung cấp export chưa.

Có thể dùng command /env để xem hoặc thay đổi environment settings trong phiên. Khi thay đổi classpath hoặc module path qua /env, JShell khởi động lại trạng thái thực thi và nạp lại startup scripts.

## 10. Khởi động với startup script

JShell có startup script mặc định tên DEFAULT, chứa các import thường dùng. Có thể thay startup script bằng tùy chọn --startup:

~~~bash
jshell --startup my-startup.jsh
~~~

Một số startup script được định nghĩa sẵn:

| Script | Nội dung |
|---|---|
| DEFAULT | Các import thường dùng; được sử dụng mặc định |
| JAVASE | Import các package Java SE; có thể làm thời gian khởi động lâu hơn |
| PRINTING | Định nghĩa method print, println và printf để gọi trực tiếp |
| TOOLING | Định nghĩa method hỗ trợ gọi một số JDK tools như javac, jar và javap |

Có thể nạp nhiều startup script bằng cách lặp lại --startup:

~~~bash
jshell --startup DEFAULT --startup PRINTING
~~~

Các script được chạy theo thứ tự khai báo. Nếu dùng --no-startup, JShell không chạy startup script mặc định; không kết hợp --no-startup với --startup.

### Tạo startup script riêng

Tạo file my-startup.jsh:

~~~java
import java.time.LocalDate;
import java.util.List;

String greeting(String name) {
    return "Xin chào, " + name + "!";
}
~~~

Khởi động:

~~~bash
jshell --startup my-startup.jsh
~~~

Sau khi vào phiên, có thể gọi ngay method greeting:

~~~java
greeting("Java")
~~~

Kết quả:

~~~text
$1 ==> "Xin chào, Java!"
~~~

Startup script được nạp khi JShell bắt đầu và khi session được reset/reload theo quy tắc của công cụ. Nếu thay đổi nội dung file sau khi đã cấu hình bằng /set start, JShell lưu nội dung script tại thời điểm cấu hình; cần chạy lại lệnh cấu hình để cập nhật nội dung được dùng.

Có thể lưu startup setting hiện tại bằng:

~~~text
jshell> /set start -retain
~~~

Thao tác này giữ cấu hình startup cho những phiên JShell tiếp theo của người dùng.

## 11. Chạy script ngay khi khởi động

Ngoài startup script, JShell cho phép truyền file script ở cuối command line:

~~~bash
jshell first-session.jsh
~~~

Script là một chuỗi snippet Java và JShell command. Mỗi snippet hoặc command được viết trên một dòng hoặc nhiều dòng tùy cú pháp.

Ví dụ file first-session.jsh:

~~~java
String greeting = "Xin chào JShell!";
System.out.println(greeting);

int total = 10 + 20;
System.out.println("Total = " + total);
~~~

Chạy với feedback silent để output chương trình gọn:

~~~bash
jshell --feedback silent first-session.jsh
~~~

Stdout của các câu lệnh print:

~~~text
Xin chào JShell!
Total = 30
~~~

File truyền ở cuối command line được chạy khi công cụ khởi động. Có thể truyền nhiều file script; chúng được xử lý theo thứ tự. Để nạp script sau khi đã vào phiên, dùng:

~~~text
jshell> /open first-session.jsh
~~~

Phân biệt:

- --startup dùng script khởi tạo môi trường, được nạp lại khi session reset/reload.
- File script truyền ở cuối command line dùng để thực thi các snippet/command khi công cụ khởi động.
- /open nạp file vào phiên đang chạy.

## 12. Các tùy chọn khởi động hữu ích khác

| Tùy chọn | Công dụng |
|---|---|
| --version | In phiên bản và thoát |
| --show-version | In phiên bản rồi tiếp tục vào JShell |
| --help | Hiển thị trợ giúp tùy chọn |
| --help-extra | Hiển thị các tùy chọn không chuẩn, có thể thay đổi |
| --enable-preview | Cho phép snippet sử dụng preview feature của đúng JDK release |
| -C flag | Truyền tùy chọn cho Java compiler bên trong JShell |
| -R flag | Truyền tùy chọn cho runtime khi thực thi snippet |
| --class-path | Đặt classpath |
| --module-path | Đặt module path |
| --startup | Chỉ định startup script |
| --no-startup | Không chạy startup script |

Ví dụ bật preview features trên đúng JDK release:

~~~bash
jshell --enable-preview
~~~

Chỉ dùng khi JDK đang chạy hỗ trợ preview feature cần thử. Preview feature gắn với release tương ứng; không nên giả định code preview có thể chạy trên mọi phiên bản Java.

Truyền compiler option:

~~~bash
jshell -C-Xlint
~~~

Truyền system property cho runtime thực thi snippet:

~~~bash
jshell -R-Dapp.mode=dev
~~~

Trong JShell, thử đọc property:

~~~java
System.getProperty("app.mode")
~~~

Kết quả là chuỗi dev. -C tác động tới compiler trong JShell; -R tác động tới runtime thực thi snippet. -J truyền flag tới runtime của chính công cụ và không thay thế -R cho execution engine mặc định.

## 13. Thoát và khởi động lại phiên

Để kết thúc phiên, nhập:

~~~text
jshell> /exit
|  Goodbye
~~~

Có thể dùng phím Ctrl+D trên terminal hỗ trợ gửi end-of-file để kết thúc input. Cách phổ biến và rõ ràng nhất vẫn là /exit.

Các command reset/reload khác nhau về cách xử lý state:

| Command | Hành vi |
|---|---|
| /reset | Bỏ toàn bộ snippet hiện tại, khởi động lại trạng thái và chạy startup scripts; không replay history |
| /reload | Khởi động lại trạng thái, chạy startup scripts rồi replay history hợp lệ |
| /env | Xem hoặc thay đổi môi trường; khi có thay đổi, session được khởi động lại và history hợp lệ được replay |
| /exit | Kết thúc công cụ |

Nếu muốn giữ snippet để sử dụng sau, lưu trước khi thoát:

~~~text
jshell> /save session.jsh
~~~

Để lưu lịch sử đầy đủ, kể cả command:

~~~text
jshell> /save -history session-history.txt
~~~

File lưu có thể được nạp lại bằng cách truyền vào khi khởi động hoặc dùng /open. Hãy kiểm tra nội dung file trước khi chia sẻ vì history có thể chứa dữ liệu đã nhập trong phiên.

## 14. Troubleshooting khi khởi động JShell

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jshell không được nhận diện | JDK chưa cài, JDK quá cũ hoặc PATH thiếu thư mục bin | Kiểm tra JDK 9+, JAVA_HOME và PATH |
| java chạy nhưng jshell không chạy | PATH trỏ tới JRE hoặc một JDK khác không có JShell | Kiểm tra Get-Command/which và dùng đúng JDK bin |
| JShell mở với phiên bản không mong muốn | Máy có nhiều JDK và PATH ưu tiên bản khác | Kiểm tra vị trí jshell và sắp xếp lại PATH |
| Import class không thành công | Thiếu classpath hoặc sai package | Dùng --class-path và xác nhận nội dung JAR |
| Không tìm thấy module | Module path sai hoặc module name không đúng | Dùng --module-path, kiểm tra module descriptor |
| Script không chạy | Sai đường dẫn hoặc file không phải script JShell hợp lệ | Kiểm tra working directory, file path và nội dung |
| Startup script không có hiệu lực ngay | Script setting áp dụng ở lần khởi động/reset tiếp theo | Dùng --startup lúc mở mới hoặc /reset sau khi cấu hình |
| Không thấy feedback sau snippet | Đang dùng concise/silent | Kiểm tra --feedback hoặc /set feedback |
| Snippet nhiều dòng chưa thực thi | Cú pháp vẫn chưa hoàn chỉnh | Tiếp tục nhập phần còn lại; kiểm tra ngoặc và dấu chấm phẩy |
| Code dùng preview feature báo lỗi | Chưa bật preview hoặc dùng sai JDK release | Khởi động với --enable-preview trên JDK phù hợp |

Khi gặp lỗi, hãy xem thông báo đầy đủ trước khi đổi cấu hình. Lỗi cú pháp snippet khác với lỗi không tìm thấy class/module và khác với lỗi không khởi động được công cụ.

## 15. Quy trình bắt đầu một phiên làm việc hiệu quả

1. Mở terminal tại thư mục làm việc.
2. Chạy java -version và jshell --version để xác nhận JDK.
3. Gọi jshell để mở REPL.
4. Nhập /help intro để đọc hướng dẫn ban đầu.
5. Thử một biểu thức đơn giản như 2 + 3.
6. Khai báo biến hoặc method để xác nhận trạng thái phiên được giữ.
7. Dùng /vars, /methods, /types và /list để xem snippet.
8. Nếu cần thư viện ngoài, khởi động với --class-path hoặc --module-path.
9. Nếu có các khai báo dùng lại, tạo startup script hoặc nạp file bằng /open.
10. Lưu snippet cần giữ bằng /save rồi thoát bằng /exit.

Đối với một phép thử ngắn, mở JShell mặc định là đủ. Với bài thử cần dependency hoặc nhiều khai báo dùng lại, hãy cấu hình classpath/module path và startup script ngay từ đầu để các snippet chạy trong cùng môi trường.

## 16. Ghi nhớ

- JShell là REPL của Java, được phân phối cùng JDK từ JDK 9.
- Gọi lệnh jshell trong terminal để mở phiên tương tác.
- JShell nhận expression, statement, variable, method, class và import dưới dạng snippet.
- Snippet được đánh giá khi hoàn chỉnh; dấu nhắc ...> báo JShell đang chờ phần còn lại.
- Lệnh JShell bắt đầu bằng dấu / như /help, /list, /vars và /exit.
- Startup script mặc định là DEFAULT; có thể dùng --startup, --no-startup hoặc các script dựng sẵn như PRINTING.
- File truyền ở cuối command line hoặc lệnh /open dùng để nạp snippet từ file.
- --class-path và --module-path giúp JShell truy cập dependency.
- --feedback điều khiển lượng thông tin hiển thị; mặc định là normal.
- /save giúp lưu snippet để sử dụng lại; /exit kết thúc phiên.

## Tài liệu tham khảo chính thức

- [The jshell Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jshell.html)
- [Java Shell User's Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jshell/index.html)
- [Java Shell User's Guide: Commands](https://docs.oracle.com/en/java/javase/26/jshell/commands.html)
- [Java Shell User's Guide: Scripts](https://docs.oracle.com/en/java/javase/26/jshell/scripts.html)