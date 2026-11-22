# Mô hình thử nghiệm biểu thức, câu lệnh và khai báo trong JShell

JShell là công cụ Java dạng REPL (read-eval-print loop), được cung cấp cùng JDK từ Java 9. Công cụ cho phép nhập từng đoạn mã, biên dịch và xem kết quả ngay trong phiên làm việc. Các biến, method, kiểu và import hợp lệ được giữ lại để những snippet tiếp theo có thể sử dụng.

Mở JShell từ terminal:

~~~text
jshell --version
jshell
~~~

JShell đi kèm JDK, không phải một runtime riêng và cũng không thay thế trình biên dịch Java hoặc quy trình build của dự án. Phiên bản JDK khởi chạy JShell quyết định những tính năng ngôn ngữ có thể dùng. Ví dụ, suy luận kiểu biến cục bộ bằng var có từ Java 10; record có từ Java 16.

## 1. Snippet là đơn vị làm việc

Một snippet là một đơn vị mã nguồn mà JShell có thể phân tích và xử lý. Những loại thường gặp gồm:

- **Expression:** biểu thức tính ra một giá trị, chẳng hạn 2 + 2.
- **Statement:** câu lệnh thực hiện hành động hoặc điều khiển luồng, chẳng hạn phép gán, if, for hoặc try.
- **Declaration:** khai báo biến, method, class, interface, enum, record hoặc annotation type.
- **Import declaration:** khai báo import để những snippet sau dùng được kiểu hoặc thành viên tương ứng.

JShell phân tích và biên dịch từng snippet trong ngữ cảnh trạng thái hiện tại của phiên. Nếu snippet hợp lệ và có hành vi thực thi, JShell đánh giá nó ngay. Những khai báo được chấp nhận sẽ trở thành một phần trạng thái phiên để các snippet sau có thể tham chiếu.

Prompt thông thường là:

~~~text
jshell>
~~~

Nếu mã chưa hoàn chỉnh, JShell chuyển sang prompt tiếp tục như sau và chờ phần còn lại:

~~~text
...>
~~~

Ví dụ, sau khi nhập dòng khai báo method nhưng chưa đóng ngoặc nhọn, JShell tiếp tục chờ thân method và dấu đóng. Khi cú pháp đã hoàn chỉnh, snippet mới được xử lý.

## 2. Biểu thức (Expression)

Biểu thức tính ra một giá trị. Khi nhập biểu thức ở prompt, JShell đánh giá và hiển thị kết quả:

~~~text
jshell> 2 + 2
$1 ==> 4
~~~

Tên như $1 là biến tạm do JShell tạo để giữ kết quả biểu thức. Số thứ tự phụ thuộc lịch sử snippet của phiên, vì vậy không nên viết mã ứng dụng dựa trên một tên $1 cố định.

Có thể sử dụng kết quả của biểu thức tiếp theo:

~~~text
jshell> $1 * 3
$2 ==> 12
~~~

Biểu thức cũng có thể gọi method, truy cập field, tạo object hoặc gây ra tác dụng phụ. Ví dụ:

~~~text
jshell> System.out.println("Hello")
Hello
~~~

Lệnh trên ghi ra standard output. Nó không trả về một giá trị hữu ích để JShell gán cho biến kết quả. Chế độ feedback quyết định cách JShell trình bày kết quả và khai báo; nó không thay đổi ngữ nghĩa của biểu thức Java.

Một điểm khác biệt quan trọng là JShell chấp nhận expression snippet trực tiếp. Một số biểu thức được chấp nhận tại prompt dù không thể đứng độc lập như một expression statement trong tệp Java thông thường.

## 3. Câu lệnh (Statement)

Câu lệnh thực hiện một hành động. Java có các nhóm câu lệnh như phép gán, lời gọi method, tạo object, block và cấu trúc điều khiển luồng gồm if, switch, for, while và try.

Ví dụ nhập khai báo biến, vòng lặp và câu lệnh điều kiện:

~~~java
int total = 0;

for (int i = 1; i <= 3; i++) {
    total += i;
}

if (total == 6) {
    System.out.println("complete");
}

System.out.println(total);
~~~

Standard output:

~~~text
complete
6
~~~

Khai báo total là một declaration snippet. Vòng for và if là statement snippet. Biến i có phạm vi block thông thường và không trở thành biến cấp cao nhất của JShell. Ngược lại, total được khai báo ở cấp phiên nên vẫn dùng được trong các snippet tiếp theo.

Một statement hoàn chỉnh được thực thi khi nhập. Nếu statement thay đổi object, ghi file hoặc tác động đến trạng thái bên ngoài, tác động đó là thật. JShell không tự hoàn tác các tác động đã xảy ra chỉ vì một statement sau đó gặp lỗi.

## 4. Khai báo (Declaration)

Khai báo giới thiệu một tên để các snippet sau có thể sử dụng. JShell hỗ trợ các khai báo cấp cao nhất thường cần khi thử nghiệm Java.

### 4.1. Khai báo biến

~~~java
int attempts = 3;
String language = "Java";
var status = "ready";
~~~

Biểu thức khởi tạo được thực thi khi khai báo biến được nhập. Từ khóa var yêu cầu compiler suy luận kiểu tĩnh từ biểu thức khởi tạo; đây không phải kiểu dữ liệu động. Kiểu được xác định tại thời điểm biên dịch và var không thể suy luận kiểu chỉ từ giá trị null.

### 4.2. Khai báo method

~~~java
int square(int value) {
    return value * value;
}
~~~

Khai báo method giúp tên square có thể được gọi ngay trong phiên. Thân method chỉ chạy khi có lời gọi:

~~~text
jshell> square(5)
$1 ==> 25
~~~

Có thể khai báo nhiều method cùng tên nếu chữ ký khác nhau, theo quy tắc overload của Java.

### 4.3. Khai báo kiểu

JShell chấp nhận các khai báo class, interface, enum và annotation type ở cấp cao nhất. Các JDK hiện hành cũng hỗ trợ record:

~~~java
class Counter {
    private int value;

    Counter(int initialValue) {
        value = initialValue;
    }

    int increment() {
        return ++value;
    }
}

record Point(int x, int y) {}
~~~

Khai báo kiểu tạo kiểu dữ liệu trong trạng thái phiên. Constructor chỉ chạy khi tạo object; method chỉ chạy khi được gọi. Ví dụ record yêu cầu Java 16 trở lên.

### 4.4. Khai báo import

~~~java
import java.time.LocalDate;
import static java.lang.Math.PI;
~~~

Import là một snippet có trạng thái. Sau khi import được chấp nhận, những snippet tiếp theo có thể tham chiếu kiểu hoặc thành viên static mà không cần viết tên đầy đủ.

Cần phân biệt khai báo cấp cao nhất với biến cục bộ bên trong method hoặc block. Biến cục bộ vẫn tuân theo phạm vi Java thông thường và không trở thành biến cấp cao nhất của JShell.

## 5. Trạng thái phiên và khai báo phụ thuộc

JShell giữ trạng thái tương tác gồm import, biến, method và kiểu đã được chấp nhận. Mỗi snippet mới được biên dịch dựa trên trạng thái đó. Một khai báo có thể phụ thuộc vào khai báo trước; các snippet sau có thể gọi method hoặc thay đổi giá trị đã tạo.

Có thể nhập định nghĩa mới cho một biến, method hoặc kiểu đã tồn tại. JShell kiểm tra định nghĩa mới và báo trạng thái của snippet. Việc định nghĩa lại có thể ảnh hưởng đến snippet phụ thuộc, vì vậy hãy dùng /list, /vars, /methods hoặc /types khi trạng thái không rõ. Method overloading vẫn hoạt động khi chữ ký khác nhau.

Có hai nhóm lỗi cần phân biệt:

- **Lỗi phân tích hoặc biên dịch:** JShell hiển thị diagnostic và từ chối snippet không hợp lệ. Hãy sửa mã rồi nhập lại; các khai báo hợp lệ trước đó vẫn có thể sử dụng.
- **Ngoại lệ lúc chạy:** snippet đã biên dịch nhưng quá trình thực thi phát sinh ngoại lệ. JShell hiển thị ngoại lệ và giữ phiên hoạt động. Tác dụng phụ đã xảy ra trước khi ngoại lệ được ném không tự được hoàn tác.

Trạng thái phiên tồn tại trong bộ nhớ. Khi thoát hoặc reset, trạng thái chưa lưu sẽ mất. Có thể dùng các lệnh lưu và mở snippet để tiếp tục thử nghiệm trong một phiên khác.

## 6. Các lệnh JShell hữu ích

Lệnh điều khiển của JShell bắt đầu bằng dấu gạch chéo /. Đây là lệnh của shell, không phải câu lệnh Java. Dùng /help hoặc /help cùng tên lệnh để xem hướng dẫn.

| Lệnh | Công dụng |
| --- | --- |
| /vars | Liệt kê biến đã khai báo và giá trị hiện tại. |
| /methods | Liệt kê method đã khai báo. |
| /types | Liệt kê class, interface và các kiểu đã khai báo. |
| /imports | Hiển thị các import đang hoạt động. |
| /list | Liệt kê snippet trong phiên. |
| /list -all | Bao gồm snippet không còn hoạt động hoặc đã được thay thế. |
| /drop id | Loại bỏ snippet theo tên hoặc mã snippet. |
| /reset | Xóa trạng thái tương tác và khởi tạo phiên mới. |
| /save -all session.jsh | Lưu snippet của phiên vào tệp. |
| /open session.jsh | Đọc tệp và xử lý nội dung như đầu vào JShell. |
| /set feedback concise | Thay đổi mức độ phản hồi của shell. |
| /exit | Kết thúc phiên JShell. |

Dùng /list để tìm mã snippet trước khi xóa hoặc kiểm tra một snippet cụ thể. Tệp snippet đã lưu hữu ích để phát lại thử nghiệm, nhưng vẫn khác với một dự án Java thông thường có cấu trúc source, cấu hình build và test.

## 7. Khởi chạy JShell với dependency

JShell sử dụng compiler và runtime của JDK đã khởi chạy nó. Nếu thử nghiệm cần thư viện bên ngoài, hãy cung cấp vị trí thư viện ngay khi mở shell.

Với dependency trên classpath:

~~~text
jshell --class-path "lib/example.jar"
~~~

Với named module:

~~~text
jshell --module-path "mods" --add-modules com.example
~~~

Dùng jshell --help để xem tùy chọn được JDK đang cài hỗ trợ. Hãy đặt đường dẫn trong dấu nháy kép khi có khoảng trắng. Nếu dependency không có sẵn, JShell không thể phân giải kiểu hoặc thành viên tương ứng; cần sửa classpath/module path và mở lại một phiên phù hợp.

## 8. Quy trình làm việc thực tế và giới hạn

JShell phù hợp để kiểm tra một biểu thức, khám phá API, thử thuật toán nhỏ, quan sát hành vi object hoặc tạo ví dụ nhanh. Một quy trình đáng tin cậy:

1. Khởi chạy JShell từ đúng JDK dự kiến sử dụng.
2. Import API cần thiết và khai báo biến hoặc method trợ giúp nhỏ.
3. Nhập từng expression, statement hoặc declaration hoàn chỉnh.
4. Kiểm tra kết quả và trạng thái phiên bằng /vars, /methods, /types và /list.
5. Lưu snippet hữu ích nếu cần phát lại.
6. Chuyển mã đã kiểm chứng vào source file thông thường và chạy compiler, build cùng test của dự án.

JShell không thay thế quy trình biên dịch và kiểm thử của dự án. Công cụ được thiết kế cho snippet tương tác, không phải để build một ứng dụng nhiều tệp hoàn chỉnh có package layout, module descriptor, xử lý resource, annotation processing hoặc test framework. Dùng javac hoặc build tool của dự án để kiểm tra mã trong cấu trúc source thực tế.

Trạng thái shell có thể che giấu import hoặc khai báo bị thiếu: một đoạn mã chạy được sau nhiều snippet trước đó có thể thất bại trong phiên sạch. Hãy chạy lại ví dụ quan trọng từ phiên mới hoặc sau khi reset, đồng thời giữ các import và khai báo phụ thuộc cùng mã cần bảo toàn.

## 9. Ví dụ tổng hợp

Chuỗi lệnh sau kết hợp khai báo, câu lệnh và biểu thức. Cú pháp dùng được trên các JDK hiện đại:

~~~java
int[] values = {2, 4, 6};

int sum(int[] numbers) {
    int result = 0;
    for (int number : numbers) {
        result += number;
    }
    return result;
}

System.out.println(sum(values));
~~~

Câu lệnh cuối in ra:

~~~text
12
~~~

Khai báo mảng tạo trạng thái có thể dùng lại. Khai báo method đăng ký một phép xử lý. Vòng lặp là statement nằm trong thân method. Lời gọi method cuối cùng là một biểu thức được dùng làm đối số cho lời gọi println. Sau đó có thể nhập trực tiếp sum(values) để xem giá trị trả về dưới dạng kết quả của expression snippet.

## Ghi nhớ

- JShell xử lý snippet hoàn chỉnh gồm biểu thức, câu lệnh, khai báo và import.
- Khai báo được chấp nhận cùng trạng thái của chúng tồn tại trong các snippet tiếp theo của cùng phiên.
- Biểu thức tạo giá trị; câu lệnh thực hiện hành động; khai báo giới thiệu tên có thể tái sử dụng.
- JShell báo lỗi biên dịch và ngoại lệ lúc chạy nhưng vẫn giữ shell hoạt động.
- Dùng lệnh bắt đầu bằng / để kiểm tra, quản lý, lưu và reset trạng thái phiên.
- Phiên bản JDK quyết định những tính năng ngôn ngữ có thể sử dụng.
- Dùng build và test thông thường của dự án để xác minh mã dành cho production.