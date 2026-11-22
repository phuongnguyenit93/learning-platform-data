# Khai báo biến trong JShell

## 1. Biến trong JShell là gì?

JShell là công cụ REPL (Read-Eval-Print Loop) đi kèm JDK, cho phép nhập và đánh giá từng đoạn mã Java ngay trong phiên làm việc. Mỗi đoạn mã được nhập vào gọi là **snippet**. Snippet có thể là khai báo biến, method, class, câu lệnh, import hoặc biểu thức.

**Khai báo biến trong JShell** tạo một tên có kiểu dữ liệu để lưu giá trị và sử dụng lại trong các snippet tiếp theo. Khác với chương trình Java thông thường thường bắt đầu từ method §main§, JShell cho phép khai báo biến trực tiếp tại dấu nhắc §jshell>§.

Ví dụ:

§§§text
jshell> int quantity = 3
quantity ==> 3

jshell> quantity + 2
$2 ==> 5
§§§

Sau khai báo đầu tiên, biến §quantity§ tồn tại trong phiên JShell. Snippet tiếp theo có thể sử dụng biến đó mà không cần khai báo lại. Biểu thức §quantity + 2§ tạo ra một scratch variable do JShell quản lý để giữ kết quả; nó không phải biến có tên do lập trình viên khai báo.

Khai báo biến là một persistent snippet: nó tiếp tục có hiệu lực trong phiên cho tới khi bị thay thế, drop hoặc phiên được reset. JShell phù hợp để thử kiểu dữ liệu, kiểm tra biểu thức, thử API, quan sát giá trị sau mỗi lần gán và tạo nhanh một bản thử nghiệm mà chưa cần dựng class hoàn chỉnh.

## 2. Khởi động JShell

JShell được cung cấp cùng JDK. Mở Terminal, Command Prompt hoặc PowerShell và chạy:

§§§bash
jshell
§§§

Kiểm tra phiên bản công cụ:

§§§bash
jshell --version
§§§

Nếu hệ thống báo không nhận diện lệnh §jshell§, kiểm tra JDK đã được cài và thư mục §bin§ của JDK đã nằm trong PATH hay chưa. JShell không có trong một số bản runtime rút gọn chỉ chứa JRE.

Có thể bật chế độ phản hồi chi tiết để quan sát các snippet:

§§§bash
jshell -v
§§§

Ở chế độ verbose, JShell thông báo khi tạo, thay thế hoặc cập nhật biến. Các chế độ phản hồi khác có thể hiển thị ít thông tin hơn; kết quả thực tế cũng có thể khác đôi chút theo phiên bản JDK.

Để kết thúc phiên làm việc:

§§§text
jshell> /exit
§§§

## 3. Cú pháp khai báo biến

Cú pháp khai báo biến Java thông thường vẫn được sử dụng trong JShell:

§§§java
type variableName = initialValue;
§§§

Trong đó:

- §type§ là kiểu dữ liệu của biến.
- §variableName§ là tên biến hợp lệ theo quy tắc định danh Java.
- §initialValue§ là giá trị khởi tạo tương thích với kiểu đã khai báo.

Ví dụ:

§§§java
int age = 25;
double price = 19.95;
boolean isActive = true;
String language = "Java";
§§§

Có thể nhập từng khai báo tại dấu nhắc JShell:

§§§text
jshell> int age = 25
age ==> 25

jshell> double price = 19.95
price ==> 19.95

jshell> boolean isActive = true
isActive ==> true

jshell> String language = "Java"
language ==> "Java"
§§§

JShell thường tự thêm dấu chấm phẩy cho một snippet đã hoàn chỉnh nếu người dùng bỏ qua dấu §;§. Tuy vậy, nên giữ dấu chấm phẩy trong bài thực hành để quen với cú pháp mã nguồn Java và dễ sao chép snippet sang tệp §.java§.

## 4. Khai báo biến theo kiểu dữ liệu

JShell hỗ trợ các kiểu dữ liệu Java như khi viết chương trình thông thường.

### 4.1. Biến kiểu nguyên thủy

Các kiểu nguyên thủy gồm:

| Kiểu | Ví dụ | Công dụng |
|---|---|---|
| §byte§ | §byte level = 2;§ | Số nguyên nhỏ, 8 bit |
| §short§ | §short year = 2026;§ | Số nguyên 16 bit |
| §int§ | §int quantity = 120;§ | Số nguyên 32 bit |
| §long§ | §long population = 8_000_000_000L;§ | Số nguyên 64 bit |
| §float§ | §float ratio = 0.75f;§ | Số thực 32 bit |
| §double§ | §double average = 8.25;§ | Số thực 64 bit |
| §char§ | §char grade = 'A';§ | Một ký tự UTF-16 code unit |
| §boolean§ | §boolean enabled = false;§ | Giá trị đúng hoặc sai |

Ví dụ:

§§§java
int attempts = 3;
long distance = 15000000000L;
float temperature = 36.5f;
double taxRate = 0.08;
char initial = 'J';
boolean completed = false;
§§§

Lưu ý hậu tố literal:

- Số nguyên kiểu §long§ thường dùng hậu tố §L§, ví dụ §100L§.
- Số thực kiểu §float§ cần hậu tố §f§ hoặc §F§, ví dụ §2.5f§.
- Literal số thực không có hậu tố mặc định có kiểu §double§.

### 4.2. Biến kiểu tham chiếu

Biến tham chiếu lưu tham chiếu tới object hoặc array. Một số kiểu thường gặp:

§§§java
String userName = "Lan";
Integer score = 95;
int[] marks = {8, 9, 10};
§§§

Có thể khai báo kiểu collection sau khi import:

§§§java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Minh");
§§§

JShell cho phép nhập import và khai báo biến thành các snippet riêng. Import được giữ trong phiên để các snippet sau sử dụng.

### 4.3. Khai báo array

Có thể khai báo array theo kiểu Java:

§§§java
int[] scores = {80, 90, 95};
String[] tools = new String[] {"javac", "java", "jshell"};
§§§

Truy cập phần tử bằng chỉ số bắt đầu từ 0:

§§§text
jshell> scores[0]
$4 ==> 80

jshell> scores.length
$5 ==> 3
§§§

Số ID scratch variable như §$4§ và §$5§ phụ thuộc những snippet đã nhập trước đó.

## 5. Khai báo biến có hoặc không có giá trị ban đầu

Nên khởi tạo biến ngay khi khai báo để trạng thái của nó rõ ràng:

§§§java
int retryCount = 0;
String status = "READY";
§§§

JShell cũng chấp nhận khai báo biến không có initializer:

§§§text
jshell> int pending;
pending ==> 0

jshell> String note;
note ==> null
§§§

Trong JShell, các biến được khai báo ở cấp cao nhất của phiên có hành vi khởi tạo mặc định tương tự field của Java: số nguyên có giá trị §0§, boolean là §false§, ký tự là §'\u0000'§, còn biến tham chiếu là §null§.

Điểm này khác với biến cục bộ trong method Java thông thường. Trong method, biến cục bộ phải được gán chắc chắn trước khi đọc; nếu đọc trước khi gán, compiler báo lỗi. Không nên dựa vào giá trị mặc định của JShell để viết mã nguồn method.

Ví dụ nên khởi tạo tường minh:

§§§java
int pending = 0;
String note = "";
§§§

Khi biến tham chiếu có giá trị §null§, gọi method hoặc truy cập field trên biến đó có thể gây §NullPointerException§.

## 6. Dùng var để suy luận kiểu dữ liệu

Từ Java 10, có thể dùng từ khóa §var§ để compiler suy luận kiểu biến từ biểu thức khởi tạo. JDK 17 trở lên hỗ trợ cách khai báo này trong JShell.

Ví dụ:

§§§java
var count = 10;
var title = "Java Core";
var average = 8.5;
var names = java.util.List.of("Lan", "Minh");
§§§

Các kiểu được suy luận tương ứng là:

- §count§: §int§.
- §title§: §String§.
- §average§: §double§.
- §names§: §List<String>§.

Có thể kiểm tra kiểu và giá trị bằng lệnh §/vars§.

§var§ không có nghĩa là biến có thể đổi sang mọi kiểu dữ liệu. Kiểu được suy luận tại thời điểm khai báo vẫn là kiểu tĩnh của biến. Ví dụ, §var count = 10;§ tạo biến kiểu §int§; không thể gán một chuỗi vào biến đó.

### 6.1. Các trường hợp không dùng được var

§var§ cần một biểu thức khởi tạo đủ thông tin để suy luận kiểu. Những khai báo sau không hợp lệ:

§§§java
var value;
var empty = null;
var first = 1, second = 2;
§§§

Lý do:

- Không có initializer nên compiler không biết kiểu cần suy luận.
- Literal §null§ không cung cấp kiểu cụ thể.
- Một khai báo §var§ không được có nhiều variable declarator.

Với trường hợp cần biểu diễn giá trị null, hãy khai báo kiểu tham chiếu rõ ràng:

§§§java
String empty = null;
§§§

Với nhiều biến, khai báo riêng để kiểu và mục đích rõ ràng:

§§§java
var first = 1;
var second = 2;
§§§

Không nên dùng §var§ khi kiểu suy luận làm đoạn mã khó đọc. Dùng kiểu tường minh khi kiểu dữ liệu là thông tin quan trọng đối với người đọc.

## 7. Đặt tên biến trong JShell

Tên biến tuân theo quy tắc định danh của Java:

- Có thể chứa chữ cái, chữ số, dấu gạch dưới và ký tự §$§.
- Không được bắt đầu bằng chữ số.
- Không được trùng với từ khóa Java.
- Phân biệt chữ hoa và chữ thường.
- Nên dùng tên thể hiện ý nghĩa dữ liệu.

Ví dụ hợp lệ:

§§§java
int itemCount = 12;
double unitPrice = 4.5;
String customerName = "An";
boolean isReady = true;
§§§

Ví dụ không hợp lệ:

§§§java
int 2items = 2;
int class = 1;
§§§

Quy ước phổ biến cho biến Java là §lowerCamelCase§, ví dụ §totalPrice§, §maxRetries§, §currentUser§.

JShell có thể tạo tên scratch như §$1§, §$2§ cho kết quả của biểu thức không được gán vào biến có tên. Không nên dùng các tên scratch này làm tên biến nghiệp vụ của chương trình.

## 8. Sử dụng và cập nhật biến đã khai báo

Sau khi khai báo, có thể dùng biến trong biểu thức, câu lệnh hoặc khai báo tiếp theo.

Ví dụ:

§§§text
jshell> int unitPrice = 12
unitPrice ==> 12

jshell> int quantity = 4
quantity ==> 4

jshell> int total = unitPrice * quantity
total ==> 48

jshell> total
total ==> 48
§§§

Gán lại giá trị cho biến:

§§§java
quantity = 5;
total = unitPrice * quantity;
§§§

Biến có kiểu tĩnh, vì vậy giá trị gán phải tương thích với kiểu đã khai báo. Ví dụ:

§§§java
int quantity = 5;
quantity = 7;       // Hợp lệ
quantity = 2.5;     // Lỗi: double không thể gán trực tiếp cho int
§§§

Nếu cần chuyển từ §double§ sang §int§, phải chọn cách chuyển đổi có chủ đích. Ép kiểu §(int) 2.5§ sẽ bỏ phần thập phân và cho kết quả §2§; đây không phải phép làm tròn.

Có thể dùng toán tử cập nhật:

§§§java
quantity++;
quantity += 2;
quantity *= 3;
§§§

Mỗi snippet được đánh giá ngay sau khi hoàn tất, vì vậy các giá trị mới có thể được sử dụng ở snippet tiếp theo.

## 9. Dùng final để khai báo biến không gán lại

Từ khóa §final§ ngăn biến được gán lại sau khi đã khởi tạo:

§§§java
final int MAX_RETRIES = 3;
final String APPLICATION_NAME = "Inventory";
§§§

Các phép gán sau không hợp lệ:

§§§java
MAX_RETRIES = 5;
APPLICATION_NAME = "Billing";
§§§

Với biến tham chiếu, §final§ khóa việc gán lại tham chiếu; nó không làm object trở thành bất biến.

Ví dụ:

§§§java
final StringBuilder message = new StringBuilder("Hello");
message.append(" Java");       // Hợp lệ: thay đổi object
// message = new StringBuilder("Other"); // Không hợp lệ: gán lại biến final
§§§

Nên dùng §final§ cho giá trị không có chủ đích thay đổi trong phiên thử nghiệm, chẳng hạn giới hạn, cấu hình hoặc hằng số phục vụ phép tính.

## 10. Biến nguyên thủy và biến tham chiếu

Khi khai báo biến, cần hiểu sự khác nhau giữa kiểu nguyên thủy và kiểu tham chiếu.

| Đặc điểm | Primitive | Reference |
|---|---|---|
| Ví dụ | §int§, §double§, §boolean§ | §String§, array, object |
| Giá trị lưu trữ | Giá trị nguyên thủy | Tham chiếu tới object hoặc §null§ |
| So sánh bằng §==§ | So sánh giá trị | So sánh identity/tham chiếu |
| Có thể là §null§ | Không | Có |
| Ví dụ khai báo | §int score = 90;§ | §String name = "An";§ |

Ví dụ:

§§§java
int first = 10;
int second = 10;
first == second;                 // true

String a = new String("Java");
String b = new String("Java");
a == b;                          // false
a.equals(b);                     // true
§§§

Hai object §String§ được tạo riêng có nội dung bằng nhau nhưng không nhất thiết là cùng object. Dùng §equals§ để so sánh nội dung của các object có quy tắc equality phù hợp.

## 11. Khai báo biến nhiều dòng và dùng trong biểu thức

JShell hỗ trợ nhập snippet nhiều dòng. Dấu nhắc phụ §...>§ xuất hiện khi một khai báo hoặc block chưa hoàn chỉnh.

Ví dụ khai báo một biến dựa trên biểu thức nhiều dòng:

§§§text
jshell> int finalPrice =
   ...>     100
   ...>     + 20;
finalPrice ==> 120
§§§

Có thể khai báo biến rồi sử dụng trong lambda hoặc stream:

§§§java
var numbers = java.util.List.of(2, 4, 6, 8);
var doubled = numbers.stream()
                     .map(n -> n * 2)
                     .toList();
§§§

Sau đó xem kết quả:

§§§text
jshell> doubled
doubled ==> [4, 8, 12, 16]
§§§

Phương thức §Stream.toList()§ có từ Java 16, nên ví dụ này chạy trên JDK 17 trở lên.

## 12. Quản lý biến bằng các lệnh JShell

JShell có các lệnh bắt đầu bằng dấu §/§. Đây là lệnh điều khiển phiên, khác với snippet Java.

| Lệnh | Công dụng |
|---|---|
| §/vars§ | Liệt kê biến đang hoạt động cùng kiểu và giá trị |
| §/vars name§ | Xem thông tin biến được chỉ định |
| §/list§ | Liệt kê các snippet đã nhập và ID |
| §/list -all§ | Hiển thị cả snippet bị thay thế, bị drop hoặc lỗi |
| §/drop name§ | Gỡ snippet biến có tên tương ứng khỏi trạng thái hoạt động |
| §/save file.jsh§ | Lưu các snippet hiện hoạt động vào tệp |
| §/open file.jsh§ | Nạp và thực thi snippet từ tệp |
| §/history§ | Xem lịch sử lệnh và snippet |
| §/reset§ | Xóa trạng thái snippet và khởi động lại phiên |
| §/exit§ | Thoát JShell |

Ví dụ:

§§§text
jshell> int score = 90
score ==> 90

jshell> String student = "An"
student ==> "An"

jshell> /vars
|    int score = 90
|    String student = "An"

jshell> /list
   1 : int score = 90;
   2 : String student = "An";
§§§

ID snippet trong kết quả thực tế phụ thuộc lịch sử phiên. Các snippet startup có thể có ID riêng và không nhất thiết xuất hiện trong §/list§ mặc định.

Muốn loại bỏ biến thử nghiệm:

§§§text
jshell> /drop score
§§§

Sau khi drop, biến §score§ không còn là khai báo đang hoạt động. Những snippet phụ thuộc vào biến đó có thể trở thành không hợp lệ cho đến khi được sửa hoặc khai báo lại.

## 13. Scratch variable và biến do người dùng khai báo

Khi nhập một biểu thức có kết quả nhưng không gán cho tên biến, JShell tự tạo scratch variable để giữ kết quả.

Ví dụ:

§§§text
jshell> 10 * 5
$1 ==> 50

jshell> "Java".toUpperCase()
$2 ==> "JAVA"
§§§

Tên scratch có dạng §$§ theo sau bởi ID. ID thay đổi tùy các snippet đã nhập trong phiên.

So sánh:

§§§java
int total = 10 * 5;   // Biến có tên do người dùng khai báo
10 * 5;               // Biểu thức; JShell tạo scratch variable
§§§

Dùng biến có tên khi cần tham chiếu lại dữ liệu ở các bước sau. Scratch variable phù hợp để xem nhanh kết quả của một phép tính hoặc lời gọi method.

Lệnh §/vars§ có thể hiển thị cả các biến scratch đang hoạt động. Không nên phụ thuộc vào số ID cụ thể của scratch variable trong tài liệu hoặc script, vì ID có thể thay đổi khi thứ tự snippet thay đổi.

## 14. Khai báo lại biến trong cùng phiên JShell

Một điểm đặc biệt của JShell là có thể nhập định nghĩa mới cho một biến đã khai báo. Định nghĩa mới thay thế snippet cũ có cùng tên.

Ví dụ:

§§§text
jshell> int level = 3
level ==> 3

jshell> String level = "Advanced"
level ==> "Advanced"
§§§

Ở lần nhập thứ hai, JShell thay biến §level§ kiểu §int§ bằng biến §level§ kiểu §String§. Trong chế độ verbose, JShell thông báo biến được thay thế và snippet cũ bị ghi đè.

Điều này hữu ích khi thử nghiệm nhiều kiểu dữ liệu hoặc sửa nhanh một khai báo. Tuy nhiên, nếu method hoặc biến khác đang phụ thuộc vào kiểu cũ, chúng có thể không còn biên dịch hoặc thực thi được. Cần đọc thông báo cập nhật của JShell và kiểm tra lại các snippet phụ thuộc.

Đây là hành vi đặc thù của môi trường REPL. Trong một block hoặc method Java thông thường, không thể khai báo hai biến cùng tên trong cùng scope như ví dụ trên.

Nếu muốn xóa định nghĩa cũ trước khi thử lại, dùng §/drop level§, sau đó khai báo biến mới. Khi cần bắt đầu hoàn toàn sạch, dùng §/reset§.

## 15. Lưu và nạp lại các khai báo biến

Biến và trạng thái object trong phiên JShell tồn tại trong phiên làm việc hiện tại. Khi thoát, trạng thái runtime không tự động được lưu như một chương trình đang chạy.

Có thể lưu các snippet để thực hiện lại sau:

§§§text
jshell> int basePrice = 100
basePrice ==> 100

jshell> int tax = 10
tax ==> 10

jshell> int finalPrice = basePrice + tax
finalPrice ==> 110

jshell> /save pricing.jsh
§§§

Trong phiên khác, nạp lại các snippet:

§§§text
jshell> /open pricing.jsh
§§§

Lệnh §/save§ lưu mã nguồn snippet; §/open§ đọc và đánh giá lại các snippet trong tệp. Nó không lưu snapshot của heap, object đang tồn tại hoặc mọi trạng thái runtime. Nếu snippet phụ thuộc tệp, thư viện hay cấu hình bên ngoài, môi trường mới vẫn cần có những thành phần đó.

## 16. Lỗi thường gặp khi khai báo biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| §cannot find symbol§ | Dùng biến trước khi khai báo hoặc gõ sai tên | Khai báo biến trước và kiểm tra chính tả |
| §incompatible types§ | Giá trị gán không tương thích với kiểu biến | Chọn kiểu phù hợp hoặc chuyển kiểu có chủ đích |
| §variable might not have been initialized§ trong mã Java | Đọc biến cục bộ trước khi gán | Gán giá trị trước khi sử dụng |
| §cannot infer type for local variable§ | Dùng §var§ mà thiếu initializer hoặc initializer không đủ thông tin kiểu | Khai báo kiểu rõ ràng hoặc dùng initializer có kiểu xác định |
| §null§ gây §NullPointerException§ | Biến tham chiếu chưa được gán object | Kiểm tra null hoặc khởi tạo object trước khi gọi method |
| Không gán lại được biến | Biến được khai báo §final§ | Dùng biến khác hoặc bỏ §final§ nếu cần thay đổi |
| Method cũ bị lỗi sau khi đổi kiểu biến | Snippet phụ thuộc vào định nghĩa cũ bị ảnh hưởng khi variable được thay thế | Kiểm tra thông báo cập nhật, sửa hoặc khai báo lại snippet phụ thuộc |
| Không thấy biến sau khi mở JShell mới | Trạng thái phiên cũ đã kết thúc | Lưu snippet bằng §/save§ và nạp lại bằng §/open§ |
| Không hiểu tên §$1§, §$2§ | Đây là scratch variable do JShell tạo cho biểu thức | Dùng §/vars§ hoặc khai báo biến có tên nếu cần dùng lâu hơn |

Một lỗi khác là nhầm lệnh JShell với mã Java. Ví dụ §/vars§ là lệnh điều khiển của JShell; không đặt nó trong tệp §.java§ hoặc trong method.

## 17. Bài thực hành: khai báo và cập nhật biến tính hóa đơn

Mở JShell và nhập các snippet theo thứ tự sau:

Bước 1 — Khai báo dữ liệu sản phẩm:

§§§java
String productName = "Keyboard";
int unitPrice = 450000;
int quantity = 2;
§§§

Bước 2 — Tính tiền hàng và thuế:

§§§java
long subtotal = (long) unitPrice * quantity;
double taxRate = 0.08;
double taxAmount = subtotal * taxRate;
double total = subtotal + taxAmount;
§§§

Bước 3 — In kết quả:

§§§java
System.out.println("Product: " + productName);
System.out.println("Subtotal: " + subtotal);
System.out.println("Tax: " + taxAmount);
System.out.println("Total: " + total);
§§§

Stdout của các lệnh in:

§§§text
Product: Keyboard
Subtotal: 900000
Tax: 72000.0
Total: 972000.0
§§§

Bước 4 — Thay đổi số lượng và tính lại:

§§§java
quantity = 3;
subtotal = (long) unitPrice * quantity;
taxAmount = subtotal * taxRate;
total = subtotal + taxAmount;
§§§

Kiểm tra:

§§§text
jshell> total
total ==> 1458000.0
§§§

Bước 5 — Xem trạng thái biến:

§§§text
jshell> /vars
§§§

Xác nhận các biến §productName§, §unitPrice§, §quantity§, §subtotal§, §taxRate§, §taxAmount§ và §total§ đang tồn tại với kiểu và giá trị mong đợi.

Bài thực hành này cho thấy biến được giữ trong phiên, có thể được cập nhật và dùng trong nhiều snippet liên tiếp mà không cần tạo một class Java hoàn chỉnh.

## 18. Quy trình tốt khi khai báo biến trong JShell

Khi thử nghiệm một đoạn logic:

1. Khởi động JShell bằng JDK phù hợp với dự án.
2. Khai báo biến bằng kiểu tường minh khi kiểu dữ liệu quan trọng; dùng §var§ khi initializer giúp suy luận kiểu rõ ràng.
3. Khởi tạo biến ngay khi khai báo nếu đã biết giá trị ban đầu.
4. Đặt tên biến theo §lowerCamelCase§ và phản ánh đúng ý nghĩa.
5. Nhập các snippet nhỏ theo thứ tự phụ thuộc để dễ xác định lỗi.
6. Dùng §/vars§ để kiểm tra tên, kiểu và giá trị hiện tại.
7. Dùng §/list§ để xem lại các khai báo và ID snippet.
8. Khi thay đổi kiểu hoặc tên biến, kiểm tra các method và snippet phụ thuộc.
9. Dùng §/save§ nếu cần giữ lại mã thử nghiệm; nạp lại bằng §/open§ khi cần.
10. Chuyển phần mã đã ổn định sang tệp §.java§, thêm class, method, kiểm thử và cấu trúc dự án phù hợp.

## 19. Tổng kết

Khai báo biến trong JShell dùng cú pháp Java quen thuộc nhưng được thực hiện trực tiếp trong một phiên REPL. Các khai báo hợp lệ được giữ lại để những snippet tiếp theo sử dụng.

Những điểm cần nhớ:

- Dùng §type name = value;§ để khai báo biến với kiểu tường minh.
- Dùng §var name = expression;§ để suy luận kiểu từ initializer trên Java 10 trở lên.
- Primitive và reference có cách lưu trữ, so sánh và xử lý null khác nhau.
- Nên khởi tạo biến ngay khi khai báo; JShell có giá trị mặc định cho biến cấp cao nhất chưa có initializer, còn biến cục bộ trong method Java phải được gán trước khi đọc.
- Gán lại giá trị không làm thay đổi kiểu tĩnh của biến.
- §final§ ngăn gán lại biến; với reference, nó không làm object bất biến.
- Khai báo lại cùng tên trong JShell sẽ thay thế snippet cũ, đây là hành vi REPL.
- §/vars§, §/list§, §/drop§, §/save§, §/open§, §/reset§ và §/exit§ giúp quản lý phiên.
- Biểu thức không có tên biến có thể tạo scratch variable dạng §$<id>§.

Thực hành khai báo biến trong JShell giúp kiểm tra nhanh kiểu, giá trị và biểu thức Java trước khi chuyển logic đã ổn định vào chương trình chính thức.

**Tài liệu tham khảo chính thức:**

- [The jshell Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jshell.html)
- [Java Shell User's Guide — Snippets](https://docs.oracle.com/en/java/javase/25/jshell/snippets.html)
- [JShell API — Snippet.Kind](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jshell/jdk/jshell/Snippet.Kind.html)
