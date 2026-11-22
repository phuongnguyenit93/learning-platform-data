# Snippet trong JShell

JShell là công cụ REPL (Read-Eval-Print Loop) đi kèm JDK, cho phép nhập và chạy mã Java từng phần mà không cần tạo một lớp có phương thức `main` cho mỗi lần thử. Mỗi phần mã Java mà JShell nhận diện và xử lý được gọi là một **snippet**.

Snippet có thể là một biểu thức, câu lệnh, biến, phương thức, lớp, interface hoặc import. Sau khi nhập, JShell phân tích và biên dịch snippet, thực thi khi phù hợp, rồi giữ trạng thái để các snippet tiếp theo có thể sử dụng những khai báo trước đó. Nhờ vậy, lập trình viên có thể thử API, kiểm tra biểu thức, khám phá thư viện và phát triển một ý tưởng Java theo từng bước.

## 1. Snippet là gì?

Trong một tệp Java thông thường, mã chạy thường được tổ chức bên trong class và method. Với JShell, có thể nhập trực tiếp một khai báo biến hoặc biểu thức ở cấp cao nhất:

~~~java
int quantity = 4
quantity * 3
~~~

JShell chấp nhận hai phần mã trên như hai snippet riêng:

- Snippet thứ nhất khai báo biến `quantity`.
- Snippet thứ hai là biểu thức sử dụng biến đã khai báo.
- Biểu thức được đánh giá ngay và JShell lưu kết quả vào một biến tạm có tên như `$2`.

Không cần viết một lớp `Main`, không cần khai báo `public static void main(String[] args)` và không cần biên dịch thủ công bằng `javac` cho mỗi thay đổi nhỏ.

Snippet không phải là một dòng văn bản tùy ý. JShell phân tích cú pháp Java để xác định một đơn vị mã hoàn chỉnh. Một snippet có thể trải dài nhiều dòng, ví dụ một khai báo method hoặc class có thân nằm trong cặp dấu ngoặc nhọn.

## 2. Các loại snippet

API `jdk.jshell` phân loại snippet theo nội dung. Những loại chính gồm:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| `IMPORT` | Khai báo import | `import java.time.LocalDate;` |
| `TYPE_DECL` | Khai báo class, interface, enum, record hoặc annotation type | `class User { }` |
| `METHOD` | Khai báo method ở cấp cao nhất | `int doubleIt(int x) { return x * 2; }` |
| `VAR` | Khai báo biến | `int count = 3;` |
| `EXPRESSION` | Biểu thức cần đánh giá | `count * 2` |
| `STATEMENT` | Câu lệnh Java | `System.out.println(count);` |
| `ERRONEOUS` | Đầu vào không phân tích được thành snippet Java hợp lệ | `int = ;` |

Ví dụ, một phiên làm việc có thể nhập:

~~~java
import java.time.LocalDate
LocalDate today = LocalDate.now()
class Customer {
    String name;
    Customer(String name) { this.name = name; }
}
Customer customer = new Customer("Linh")
customer.name
~~~

Các import, biến và kiểu được khai báo sẽ tiếp tục tồn tại trong trạng thái JShell hiện tại cho đến khi bị thay thế, drop hoặc phiên làm việc được reset.

Không phải mọi dòng lệnh nhập vào đều là snippet. Các lệnh bắt đầu bằng dấu `/`, như `/list` hoặc `/vars`, là **JShell commands** dùng để điều khiển công cụ. Chúng không phải câu lệnh Java và không được lưu như snippet Java thông thường.

## 3. Bắt đầu JShell và nhập snippet

Kiểm tra JDK:

~~~bash
java -version
jshell --version
~~~

Khởi động phiên tương tác:

~~~bash
jshell
~~~

Khi thấy prompt:

~~~text
jshell>
~~~

có thể nhập Java code trực tiếp:

~~~text
jshell> int count = 3
count ==> 3

jshell> count * 2
$2 ==> 6

jshell> System.out.println("Ready")
Ready
~~~

Các dòng trên minh họa feedback mode thông thường. Nội dung hiển thị chính xác có thể khác khi đổi JDK hoặc feedback mode.

- `count` là biến có tên do người dùng khai báo.
- `$2` là tên biến tạm mà JShell tạo cho kết quả của biểu thức.
- `System.out.println(...)` là statement có tác dụng phụ; nó in ra console và không cần tạo biến kết quả.

Có thể nhập dấu chấm phẩy ở cuối snippet. Với nhiều khai báo hoặc biểu thức cấp cao nhất, JShell thường có thể nhận diện ranh giới snippet mà không cần dấu chấm phẩy, nhưng dùng dấu chấm phẩy vẫn giúp mã nhất quán với Java source thông thường.

## 4. Ví dụ hoàn chỉnh: nhiều snippet dùng chung trạng thái

Tạo file `demo.jsh`:

~~~java
int quantity = 4
quantity * 3
String name = "Ada"
void greet(String who) {
    System.out.println("Hello, " + who);
}
greet(name)
/list
/vars
/methods
/exit
~~~

Chạy từ terminal:

~~~bash
jshell --feedback concise demo.jsh
~~~

Với JDK 24.0.2 và feedback mode `concise`, output của ví dụ là:

~~~text
Hello, Ada

   1 : int quantity = 4;
   2 : quantity * 3
   3 : String name = "Ada";
   4 : void greet(String who) {
           System.out.println("Hello, " + who);
       }
   5 : greet(name)
  int quantity = 4
  int $2 = 12
  String name = "Ada"
  void greet(String)
~~~

Ví dụ cho thấy:

1. `quantity` được khai báo ở snippet đầu tiên.
2. Biểu thức `quantity * 3` sử dụng biến đó và tạo kết quả `$2`.
3. Biến `name` được giữ lại trong session.
4. Method `greet` được khai báo một lần rồi có thể gọi ở snippet sau.
5. `/list`, `/vars` và `/methods` xem lại các khai báo đang có.

File `.jsh` có thể chứa cả Java snippets và JShell commands. Khi dùng file, các snippet được xử lý tuần tự theo thứ tự xuất hiện.

## 5. Snippet nhiều dòng và cách JShell xác định ranh giới

Một snippet có thể chứa nhiều dòng. JShell tiếp tục nhận đầu vào khi cú pháp chưa hoàn chỉnh, chẳng hạn khi đang ở trong thân method, class hoặc block.

Ví dụ nhập trực tiếp:

~~~text
jshell> void printRange(int start, int end) {
   ...>     for (int i = start; i <= end; i++) {
   ...>         System.out.println(i);
   ...>     }
   ...> }
~~~

Prompt `...>` cho biết JShell đang chờ phần còn lại của snippet. Khi đóng đủ dấu ngoặc và cú pháp hoàn chỉnh, snippet mới được xử lý.

Có thể khai báo một class nhiều dòng:

~~~java
class Product {
    private final String code;

    Product(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

Sau đó tạo instance:

~~~java
Product product = new Product("P-100")
product.code()
~~~

JShell phân tích cú pháp để xác định khi nào snippet hoàn chỉnh. Vì vậy, không nên giả định mỗi dòng nhập tương ứng với một snippet. Một khai báo nhiều dòng vẫn là một snippet duy nhất.

## 6. Biểu thức và biến kết quả tự động

Khi nhập một biểu thức độc lập, JShell đánh giá biểu thức và lưu kết quả vào biến tạm nếu biểu thức có giá trị trả về.

Ví dụ:

~~~java
10 + 5
Math.sqrt(81)
"java".toUpperCase()
~~~

Các kết quả được gán cho những biến tạm như `$1`, `$2`, `$3` tùy thứ tự snippet trong phiên.

Có thể sử dụng kết quả tạm ở snippet tiếp theo:

~~~java
$1 * 2
~~~

Tên biến tạm được JShell cấp tự động. Nếu cần tham chiếu lâu dài hoặc mã dễ đọc, nên gán kết quả vào biến có tên rõ ràng:

~~~java
int total = 10 + 5
double root = Math.sqrt(81)
String language = "java".toUpperCase()
~~~

Sau đó có thể dùng trực tiếp `total`, `root` và `language`.

Một statement như:

~~~java
System.out.println("Hello")
~~~

thực hiện hành động in ra console. Nó không tạo giá trị biểu thức để lưu vào biến tạm.

## 7. Snippet ID và xem lại mã đã nhập

JShell gán ID cho các snippet được nhập trong phiên. ID thường là số tăng dần; snippet khởi tạo từ startup definitions có thể dùng tiền tố khác.

Lệnh quan trọng nhất để xem snippet:

~~~text
/list
~~~

`/list` hiển thị các snippet đang hoạt động, kèm ID. Có thể xem một snippet theo ID:

~~~text
/list 3
~~~

Xem toàn bộ lịch sử snippet, bao gồm snippet lỗi, bị thay thế, bị drop và startup:

~~~text
/list -all
~~~

Xem các snippet startup:

~~~text
/list -start
~~~

Một số lệnh khác cũng hỗ trợ tra cứu theo ID hoặc tên. ID chỉ có ý nghĩa trong lịch sử của session hiện tại; sau khi reset, không nên giả định ID cũ vẫn đại diện cho cùng một snippet.

Các lệnh bắt đầu bằng `/` không được tính là snippet ID. Ví dụ `/list` không trở thành snippet số tiếp theo.

## 8. Xem biến, method, type và import

JShell cung cấp các lệnh riêng để xem những khai báo đang tồn tại.

### Xem biến với /vars

~~~text
/vars
~~~

Lệnh này hiển thị kiểu, tên và giá trị của các biến đang hoạt động. Có thể xem theo tên hoặc ID:

~~~text
/vars total
/vars 2
/vars -all
~~~

`/vars -all` bao gồm cả biến đã bị thay thế, drop, lỗi hoặc được khai báo trong startup snippets.

### Xem method với /methods

~~~text
/methods
~~~

Lệnh hiển thị tên method, kiểu tham số và kiểu trả về. Có thể lọc theo tên:

~~~text
/methods greet
~~~

Hoặc xem toàn bộ lịch sử method:

~~~text
/methods -all
~~~

### Xem class và interface với /types

~~~text
/types
/types Product
/types -all
~~~

Lệnh này giúp kiểm tra các type declaration đang hoạt động, bao gồm class, interface và những kiểu khai báo Java được JShell hỗ trợ.

### Xem import với /imports

~~~text
/imports
~~~

Lệnh hiển thị các import đang hoạt động, bao gồm import từ startup definitions.

Các lệnh này giúp quan sát trạng thái hiện tại mà không cần tìm lại từng dòng đã nhập.

## 9. Vòng đời và trạng thái của snippet

Snippet có vòng đời gắn với trạng thái biên dịch và trạng thái thực thi. Trong API `jdk.jshell`, `Snippet.Status` định nghĩa những trạng thái như:

| Trạng thái | Ý nghĩa tổng quát |
|---|---|
| `VALID` | Snippet được biên dịch/đánh giá hợp lệ và đang hoạt động. |
| `RECOVERABLE_DEFINED` | Một khai báo vẫn được xác định nhưng có tham chiếu chưa được giải quyết hoàn toàn. |
| `RECOVERABLE_NOT_DEFINED` | Snippet chưa thể được xác định đầy đủ do dependency chưa có. |
| `DROPPED` | Snippet đã bị người dùng loại khỏi trạng thái hoạt động. |
| `OVERWRITTEN` | Snippet đã bị khai báo mới thay thế. |
| `REJECTED` | Snippet bị từ chối do lỗi biên dịch hoặc lỗi phân tích không thể khôi phục. |
| `NONEXISTENT` | Không có snippet tương ứng trong trạng thái được truy vấn. |

Đây là các trạng thái của API JShell; người dùng REPL thông thường không cần ghi nhớ toàn bộ enum. Khi cần xem lịch sử, `/list -all` là cách trực tiếp để thấy cả snippet hiện tại và những snippet không còn hoạt động.

Một snippet có thể được chấp nhận về cú pháp nhưng phụ thuộc vào một kiểu hoặc biến chưa được khai báo. JShell có thể giữ thông tin để trạng thái được khôi phục khi dependency xuất hiện. Ngược lại, lỗi cú pháp không thể khôi phục sẽ khiến snippet bị từ chối.

Cần phân biệt trạng thái snippet với kết quả chạy. Một snippet có thể biên dịch thành công nhưng ném exception lúc thực thi. Khi đó lỗi runtime được hiển thị, nhưng điều đó không đồng nghĩa snippet có lỗi cú pháp hoặc tự động bị xóa khỏi lịch sử.

## 10. Thay thế và drop snippet

Nếu khai báo lại một biến cùng tên, JShell thay thế khai báo trước đó:

~~~java
int score = 10
score + 1
int score = 20
score
~~~

Sau lần khai báo cuối, `score` có giá trị mới. Snippet khai báo cũ được đánh dấu là đã bị thay thế trong lịch sử.

Có thể kiểm tra:

~~~text
/list -all
/vars -all
~~~

Để loại một snippet khỏi trạng thái hoạt động, dùng:

~~~text
/drop 3
~~~

Có thể drop theo tên:

~~~text
/drop score
~~~

`/drop` làm snippet không còn hoạt động trong trạng thái JShell. Nếu snippet khác phụ thuộc vào khai báo vừa drop, những snippet phụ thuộc có thể không còn sử dụng được cho tới khi dependency được định nghĩa lại.

Drop một khai báo không giống xóa một dòng trong file nguồn thông thường. JShell quản lý lịch sử và quan hệ phụ thuộc giữa các snippet; dùng `/list -all` để xem lại những gì đã xảy ra.

## 11. Chỉnh sửa snippet bằng /edit

Có thể mở snippet trong trình soạn thảo ngoài:

~~~text
/edit 4
~~~

Hoặc chỉnh theo tên:

~~~text
/edit greet
~~~

Trình soạn thảo được cấu hình bằng `/set editor`. Nếu chưa cấu hình, JShell tìm các biến môi trường `JSHELLEDITOR`, `VISUAL`, `EDITOR`, rồi mới dùng trình soạn thảo đơn giản tích hợp nếu cần.

Ví dụ cấu hình trên môi trường có `notepad`:

~~~text
/set editor notepad
~~~

Sau khi chỉnh sửa và lưu trong editor, JShell nhận phần mã đã cập nhật và đánh giá lại snippet tương ứng. Những khai báo phụ thuộc có thể được cập nhật theo kết quả biên dịch mới.

Có thể chỉnh các snippet đang hoạt động cùng lúc:

~~~text
/edit
~~~

Hoặc chỉnh toàn bộ lịch sử, bao gồm snippet lỗi, overwritten, dropped và startup:

~~~text
/edit -all
~~~

Khi chỉnh sửa nhiều snippet, cần giữ thứ tự và quan hệ phụ thuộc hợp lý. Nếu một method sử dụng class khác, class đó phải được định nghĩa hoặc có thể được phân giải trong session.

## 12. Lưu và nạp snippet bằng /save và /open

Để lưu các snippet đang hoạt động vào file:

~~~text
/save session.jsh
~~~

Lưu tất cả snippet, kể cả snippet lỗi, bị thay thế, bị drop và startup:

~~~text
/save -all full-session.jsh
~~~

Lưu lịch sử tuần tự của các lệnh và snippet đã nhập:

~~~text
/save -history command-history.txt
~~~

Có thể lưu một snippet theo ID:

~~~text
/save 3 selected-snippet.jsh
~~~

Để nạp file trở lại session:

~~~text
/open session.jsh
~~~

JShell đọc file và xử lý nội dung như đầu vào tương tác, bao gồm các snippet và JShell commands có trong file. Các snippet được thực hiện theo thứ tự trong file.

Một file `.jsh` có thể dùng để chia sẻ ví dụ, tạo buổi thực hành, chuẩn bị môi trường demo hoặc tái hiện lỗi. Tuy nhiên, `/open` thực thi mã Java và các JShell commands trong file. Chỉ nạp file từ nguồn tin cậy; không mở một script lạ như thể nó chỉ là tài liệu văn bản.

## 13. Reset và reload session

Lệnh `/reset` khởi động lại trạng thái thực thi JShell và xóa các snippet đã nhập trong session hiện tại. Startup definitions được thực thi lại:

~~~text
/reset
~~~

Hãy lưu công việc trước khi reset nếu cần giữ lại mã.

`/reload` reset trạng thái rồi phát lại các snippet hợp lệ và các lệnh drop theo thứ tự đã nhập trong khoảng lịch sử hiện tại:

~~~text
/reload
~~~

Có thể dùng:

~~~text
/reload -quiet
~~~

để giảm phần hiển thị khi phát lại, nhưng lỗi vẫn được báo.

`/reload -restore` có thể khôi phục lịch sử từ khoảng phiên trước theo quy tắc của JShell. Đây là cơ chế phục hồi session trong REPL, không thay thế việc lưu mã nguồn vào file nếu cần lưu trữ lâu dài.

Khác biệt chính:

- `/reset`: bỏ trạng thái code hiện tại và bắt đầu lại.
- `/reload`: reset rồi chạy lại lịch sử hợp lệ của khoảng session hiện tại.
- `/save`: lưu source/history thành file để sử dụng ở phiên khác.

## 14. Startup definitions và feedback mode

Khi khởi động, JShell thường nạp một tập startup snippets, gồm các import phổ biến và một số định nghĩa hỗ trợ. Vì vậy, một số lớp trong `java.util` hoặc `java.io` có thể được dùng mà không cần import tường minh.

Xem import hiện tại:

~~~text
/imports
~~~

Có thể tắt startup definitions:

~~~bash
jshell --no-startup
~~~

Hoặc chỉ định file startup:

~~~bash
jshell --startup my-startup.jsh
~~~

Startup definitions có thể thay đổi môi trường ban đầu của session. Khi cần kết quả tái lập, hãy ghi rõ JDK, startup file và các tùy chọn khởi động được dùng.

Feedback mode quyết định mức thông tin JShell in ra sau khi xử lý snippet. Các mode dựng sẵn gồm `normal`, `concise`, `silent` và `verbose`.

Có thể chọn lúc khởi động:

~~~bash
jshell --feedback concise
~~~

Hoặc đổi ngay trong session:

~~~text
/set feedback concise
~~~

- `normal`: hiển thị thông tin kết quả và phản hồi tương đối đầy đủ.
- `concise`: giảm bớt phản hồi, phù hợp demo hoặc script.
- `silent`: giảm tối đa feedback thông thường.
- `verbose`: hiển thị nhiều thông tin hơn về quá trình xử lý.

Feedback mode chỉ thay đổi cách trình bày kết quả. Nó không thay đổi ý nghĩa Java của snippet.

## 15. Dùng snippet với thư viện và module bên ngoài

Nếu snippet sử dụng lớp trong JAR bên ngoài, cần thêm JAR vào classpath của JShell.

Ví dụ:

~~~bash
jshell --class-path "lib/customer-api.jar;lib/common.jar"
~~~

Trên Windows, classpath dùng dấu chấm phẩy. Trên Linux/macOS, dùng dấu hai chấm:

~~~bash
jshell --class-path "lib/customer-api.jar:lib/common.jar"
~~~

Sau khi mở session, có thể import và sử dụng lớp từ thư viện:

~~~java
import com.acme.api.Customer
Customer customer = new Customer("Linh")
~~~

Với ứng dụng modular, JShell hỗ trợ `--module-path` và `--add-modules`:

~~~bash
jshell --module-path mods --add-modules com.acme.customer
~~~

Module phải có thể được phân giải từ module path. Nếu không chắc, kiểm tra module descriptor và dependency trước khi chạy JShell.

Tùy chọn `-C` truyền cờ cho compiler bên trong JShell:

~~~bash
jshell -C-Xlint
~~~

Có thể truyền một cờ compiler với đối số riêng bằng cách dùng `-C` cho từng thành phần:

~~~bash
jshell -C--release=17
~~~

Tùy chọn `-R` truyền cờ cho runtime khi snippet được thực thi. Ví dụ:

~~~bash
jshell -R-Dapp.mode=demo
~~~

Sau đó snippet có thể đọc property:

~~~java
System.getProperty("app.mode")
~~~

Không nhầm `-J` với `-R`: `-J` truyền cờ cho tiến trình JVM chạy công cụ JShell; `-R` áp dụng cho runtime thực thi snippet theo cơ chế execution engine.

## 16. Snippet trong quy trình học tập và phát triển

JShell phù hợp với những việc cần phản hồi nhanh:

- Thử một biểu thức hoặc thuật toán nhỏ.
- Khám phá method của một API.
- Kiểm tra cách một class trong thư viện hoạt động.
- Thử xử lý chuỗi, collection, date/time và stream.
- Kiểm tra kết quả chuyển đổi kiểu hoặc generic.
- Tạo ví dụ ngắn cho bài học hoặc buổi demo.
- Tái hiện một lỗi bằng vài snippet tối thiểu.

Ví dụ khám phá Stream API:

~~~java
import java.util.List
List<Integer> numbers = List.of(2, 4, 6, 8)
numbers.stream().map(n -> n * n).toList()
~~~

Ví dụ kiểm tra Date/Time:

~~~java
import java.time.LocalDate
LocalDate.of(2026, 11, 10).plusDays(7)
~~~

Khi thử nghiệm đã ổn định và cần trở thành thành phần của ứng dụng, hãy chuyển mã sang file `.java`, thêm cấu trúc package, kiểm thử và build bằng công cụ dự án. JShell rất hữu ích cho khám phá nhanh, nhưng không thay thế compiler/build/test pipeline của ứng dụng hoàn chỉnh.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `cannot find symbol` | Biến, method, class hoặc import chưa tồn tại trong session. | Khai báo dependency trước, kiểm tra `/vars`, `/methods`, `/types` và `/imports`. |
| JShell tiếp tục hiện prompt `...>` | Snippet nhiều dòng chưa đóng ngoặc hoặc cú pháp chưa hoàn chỉnh. | Hoàn tất block, đóng ngoặc hoặc kiểm tra cú pháp. |
| Snippet không chạy vì lỗi cú pháp | Java code không hợp lệ hoặc khai báo chưa đầy đủ. | Đọc diagnostic, sửa snippet rồi nhập lại hoặc dùng `/edit`. |
| Method gọi được trước đó nhưng hiện không còn | Method hoặc dependency đã bị drop/overwritten. | Dùng `/list -all`, kiểm tra trạng thái và định nghĩa lại dependency. |
| Giá trị biến khác dự kiến | Biến đã được khai báo lại hoặc snippet phụ thuộc đã được đánh giá ở thời điểm trước. | Dùng `/vars -all`, `/list -all` và chạy lại biểu thức cần kiểm tra. |
| Không tìm thấy lớp trong JAR | Thiếu classpath hoặc module path. | Khởi động với `--class-path`, `--module-path` và `--add-modules` phù hợp. |
| `/edit` không mở editor mong muốn | Chưa cấu hình editor hoặc biến môi trường không đúng. | Dùng `/set editor` hoặc cấu hình `JSHELLEDITOR`, `VISUAL`, `EDITOR`. |
| Mất code sau khi đóng session | Chưa lưu snippet ra file. | Dùng `/save` hoặc `/save -history` trước khi thoát. |
| File `/open` gây lỗi hàng loạt | File chứa snippet không hợp lệ, phụ thuộc sai thứ tự hoặc command không phù hợp. | Kiểm tra file theo từng đoạn và nạp từ một bản đã được rà soát. |
| Output khác với hướng dẫn | Khác JDK, feedback mode, startup definitions hoặc môi trường. | Kiểm tra `jshell --version`, `/set`, `/imports` và tùy chọn khởi động. |

Một lỗi runtime như `NullPointerException` có thể xảy ra sau khi snippet đã biên dịch thành công. Hãy phân biệt diagnostic biên dịch với exception khi chạy: một lỗi cần sửa source/type, lỗi còn lại cần kiểm tra dữ liệu và logic thực thi.

## 18. Quy trình làm việc khuyến nghị

Một session JShell dễ theo dõi có thể thực hiện theo trình tự:

1. Kiểm tra phiên bản JDK bằng `jshell --version`.
2. Khởi động với feedback mode phù hợp.
3. Import thư viện cần dùng.
4. Khai báo biến và type trước khi sử dụng.
5. Nhập biểu thức hoặc statement nhỏ để kiểm tra hành vi.
6. Khai báo method/class khi muốn tái sử dụng logic.
7. Dùng `/list`, `/vars`, `/methods`, `/types` và `/imports` để kiểm tra trạng thái.
8. Dùng `/edit` hoặc `/drop` khi cần sửa session.
9. Dùng `/save` để lưu source snippets trước khi kết thúc.
10. Chuyển phần mã đã ổn định sang source file và chạy build/test chính thức.

Nếu đang điều tra lỗi, hãy lưu một file `.jsh` nhỏ có thể tái hiện lỗi, ghi rõ phiên bản JDK và các dependency cần thiết. Một ví dụ tối thiểu, có thứ tự snippet rõ ràng, thường giúp người khác chạy lại và xác định nguyên nhân nhanh hơn.

## 19. Ghi nhớ

Snippet là đơn vị mã Java mà JShell phân tích, đánh giá và lưu trong trạng thái REPL. Snippet có thể là import, type, method, variable, expression hoặc statement; nhiều snippet có thể sử dụng các khai báo đã nhập trước đó.

Các lệnh `/list`, `/vars`, `/methods`, `/types` và `/imports` giúp quan sát session. `/edit`, `/drop`, `/save`, `/open`, `/reload` và `/reset` giúp quản lý vòng đời mã đã nhập. Khi hiểu ranh giới snippet, ID, dependency và trạng thái hoạt động, JShell trở thành môi trường thử nghiệm Java nhanh, có thể lưu lại và tái lập.
