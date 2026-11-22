# Thử biểu thức `var` bằng JShell trên JDK phù hợp — Java 10

**Nhóm:** Biên dịch và kiểm chứng.  
**Nội dung chính:** Sử dụng công cụ **JShell** để thử suy luận kiểu biến cục bộ (`var`), quan sát kiểu compiler đã xác định, phát hiện trường hợp không hợp lệ và so sánh với việc biên dịch file Java 10 thực sự.

**`var` được giới thiệu trong Java 10 theo JEP 286 (*Local-Variable Type Inference*)**. Đây là một **reserved type name** dùng ở những vị trí khai báo biến cục bộ có initializer thích hợp; nó không phải kiểu dữ liệu động, không tự chuyển kiểu trong runtime và không thay thế mọi nơi dùng tên kiểu. **JShell** là công cụ tương tác *Read–Evaluate–Print Loop* có từ **JDK 9**, có thể nhận từng snippet Java, lập tức biên dịch/đánh giá và cho biết biến có kiểu gì. Muốn thử riêng **ngữ nghĩa Java 10** bằng một JDK mới, dùng tùy chọn **`-C--release=10`** của JShell khi compiler tương ứng còn hỗ trợ release 10.

**Special Note — chỉ kiến thức còn áp dụng hiện nay:** Đây vẫn là cách làm hợp lệ trên các JDK hiện đại. Không khuyên cài đặt một bản JDK 10 đã ngừng được hỗ trợ để sử dụng ở production. Những lệnh và ví dụ được kiểm chứng trên **Zulu/OpenJDK 24.0.2** với Java compiler target 10; vì vậy tài liệu nói rõ những gì được chứng minh bởi **compiler mode Java 10**, không mạo nhận JVM đang thực thi chính là Java 10.

**Điểm cốt lõi:** `var count = 10` suy ra kiểu **`int`**, không phải `Object` hay một kiểu thay đổi tùy lúc. Nếu viết `count = "hello"` sau đó, compiler từ chối. JShell có cho phép nhập lại `var count = "hello"` để *thay một variable snippet*; đó là **redefinition của REPL**, không phải một biến Java đang đổi kiểu động.

## 1. Dùng JDK nào và vì sao?

Chạy trong terminal dự định sử dụng để học:

~~~bash
java -version
javac -version
jshell --version
~~~

Nên dùng **một JDK còn được nhà cung cấp cập nhật** và bảo đảm `java`, `javac`, `jshell` cùng trỏ đến đúng cài đặt. Một JRE/runtime image tối giản có thể không có `jshell` hoặc `javac`; đó không phải lỗi của cú pháp `var`.

| Môi trường | Kết quả cần nhớ |
| --- | --- |
| **JDK 9** | JShell đã có, nhưng Java language level 9 **chưa hỗ trợ `var` theo JEP 286** |
| **JDK 10** | Có thể thử `var` trực tiếp trong JShell; là mốc phát hành lịch sử |
| **JDK 11+** | `var` cho local variables vẫn hợp lệ; có thêm một số cú pháp/API mới hơn |
| **JDK mới + `jshell -C--release=10`** | Yêu cầu JShell compiler áp **ngữ nghĩa/source/API Java 10** nếu JDK còn hỗ trợ release đó |
| **`javac --release 10`** | Dùng với **file `.java`** để kiểm source/API và bytecode mục tiêu Java 10 |
| **JVM khi chạy JShell của JDK mới** | Vẫn là JDK hiện đang chạy, **không biến thành runtime Java 10** |

Tài liệu `jshell` hiện hành mô tả `-C` là đường truyền compiler options. Để bắt đầu:

~~~bash
jshell --feedback verbose -C--release=10
~~~

`--feedback verbose` chỉ giúp công cụ nói rõ hơn khi tạo biến/biểu thức; nó không thay đổi quy tắc kiểu. `-C--release=10` mới là phần đặt compiler target.

**Lưu ý cú pháp:** Với JShell dùng **`-C--release=10`**; với `javac` dùng **`--release 10`**. Đây không phải hai tên khác nhau của một câu lệnh và không được gõ option trình khởi động vào prompt `jshell>`.

Nếu có lỗi `release version 10 not supported`, hãy xem `javac --help`, `jshell --help` và dùng một JDK có compiler target phù hợp. Không tự bỏ option rồi khẳng định bài vẫn được kiểm chứng theo source level Java 10.

## 2. JShell làm việc với “snippet” như thế nào?

Trong một phiên JShell, bạn có thể nhập **biểu thức, câu lệnh, khai báo biến, method, class và import**, không cần tạo sẵn một `public static void main`.

Ví dụ, tại prompt JShell:

~~~java
var count = 42;
var name = "Linh";
var ratio = 1.5;
~~~

Sau đó nhập **lệnh JShell**:

~~~text
/vars
~~~

Mô tả phần thông tin chính mà `/vars` hiển thị:

~~~text
int count = 42
String name = "Linh"
double ratio = 1.5
~~~

Đây là **kiểu tĩnh đã được suy luận**:

- `42` là `int`, do đó `count` là `int`.
- `"Linh"` là `String`, do đó `name` là `String`.
- `1.5` là literal `double`, do đó `ratio` là `double`.

`var` **không đóng gói giá trị thành một `Object` cho mọi trường hợp**, và không mặc định thực hiện boxing của `int` thành `Integer`. Nếu muốn nhìn boxed runtime class trong một biểu thức demo có thể ép qua `Object`:

~~~java
System.out.println(((Object) count).getClass().getSimpleName());
~~~

Stdout:

~~~text
Integer
~~~

Điều đó chỉ chứng minh khi ép một `int` qua `Object`, Java dùng boxing tạo giá trị tham chiếu `Integer`. **Nó không làm thay đổi kiểu tĩnh của `count`**, vẫn là `int`.

### Các lệnh JShell liên quan

~~~text
/vars
/list
/list -all
/methods
/types
/imports
/reset
/exit
~~~

Những dòng bắt đầu bằng `/` là **lệnh cho JShell**, không phải Java code. `/vars` hiển thị **name/type/value** của active variables; `/list` hiển thị source và ID snippets; `/list -all` có thể hiển thị cả rejected/replaced snippets. `/reset` xóa những snippets người dùng nhập và khởi tạo lại phiên theo cấu hình; `/exit` kết thúc.

### Đừng dựa vào ID `$1`

Nếu nhập biểu thức trần:

~~~java
2 + 3
~~~

JShell có thể tạo **scratch variable** mang tên `$1` hoặc một chỉ số khác. Chỉ số phụ thuộc thứ tự snippets và trạng thái session, nên không thích hợp làm khóa assertion trong bài tự động. Nếu muốn stdout cố định, viết:

~~~java
System.out.println("result=" + (2 + 3));
~~~

Kết quả:

~~~text
result=5
~~~

## 3. `var` suy ra từ biểu thức ở vế phải

Một số ví dụ có thể thử trực tiếp:

~~~java
var size = 100;
var title = "Java 10";
var words = java.util.List.of("An", "Binh");
var count = words.size();
/vars
~~~

Kết quả thông tin kiểu quan trọng:

~~~text
int size = 100
String title = "Java 10"
List<String> words = [An, Binh]
int count = 2
~~~

Những khai báo tương đương về kiểu tĩnh trong chương trình Java:

~~~java
int size = 100;
String title = "Java 10";
java.util.List<String> words = java.util.List.of("An", "Binh");
int count = words.size();
~~~

**Điểm học được:** `var` không “tìm kiểu phù hợp nhất từ toàn bộ các câu lệnh về sau”. Compiler lấy kiểu **ngay khi khởi tạo**, dựa vào biểu thức ở bên phải. Sau đó, assignment và method invocation phải phù hợp kiểu đã chọn.

### Compiler nhìn kiểu tĩnh, không đoán runtime class

~~~java
Object obj = "hello";
var same = obj;
~~~

Ở đây `same` có kiểu tĩnh **`Object`**, vì initializer là biểu thức `obj` đã được khai báo `Object`. Dù giá trị thật là một `String`, compiler không tự cho phép `same.length()`. Cần kiểu tường minh/cast thích hợp.

Ngược lại:

~~~java
var text = "hello";
System.out.println(text.length());
~~~

Stdout:

~~~text
5
~~~

Compiler biết `text` là `String`. Đó là lợi ích khi initializer rõ loại giá trị.

## 4. Thử generic type inference và toán tử diamond

Trong JShell:

~~~java
var strings = java.util.List.of("a", "b");
var typed = new java.util.ArrayList<String>();
var inferred = new java.util.ArrayList<>();
/vars
~~~

Kiểu đáng chú ý:

~~~text
List<String> strings = [a, b]
ArrayList<String> typed = []
ArrayList<Object> inferred = []
~~~

**Vì sao `inferred` suy ra `ArrayList<Object>`?** Với `new ArrayList<>()` không có đủ ngữ cảnh generic từ kiểu viết tường minh bên trái, diamond operator trong ví dụ này chọn `Object`. `var` lấy nguyên kiểu của initializer ấy. Nó **không tự đoán rằng bạn sắp thêm `String` vào list**.

Nếu muốn một list of strings:

~~~java
var typedNames = new java.util.ArrayList<String>();
java.util.List<String> asList = new java.util.ArrayList<>();
~~~

Phương án thứ hai cũng có lợi khi muốn khai báo contract ở mức interface `List` thay vì implementation cụ thể `ArrayList`.

**Quan sát JShell:** Trong test thực tế, `var inferredObject = new ArrayList<>()` được `/vars` hiển thị với kiểu `ArrayList<Object>`. Chỉ nhìn `inferredObject.getClass()` sẽ không thấy generic argument vì **type erasure**.

### Một collection không sửa được không phải tác dụng của `var`

~~~java
var items = java.util.List.of("x", "y");
~~~

`List.of` trả **unmodifiable list**, thuộc hợp đồng của API `List.of` (Java 9+). Nếu gọi `items.add("z")`, code có thể compile vì type là `List<String>`, nhưng runtime ném `UnsupportedOperationException`. Đây không phải `var` khiến list bất biến.

## 5. Script JShell hoàn chỉnh — ví dụ `var` hợp lệ

Để có thể chạy lại thí nghiệm, tạo file **`var-lab.jsh`** với đúng nội dung sau. Đây là file **JShell script**: các snippets và lệnh của JShell, không phải file Java chứa một class `main`.

~~~java
import java.util.*;

var number = 10;
var label = "Java 10";
var names = List.of("An", "Binh");
var set = new HashSet<String>();
set.add("alpha");

var inferredObject = new ArrayList<>();
inferredObject.add("text");
var numbers = new int[]{1, 2, 3};
var twice = (java.util.function.IntUnaryOperator) (x -> x * 2);

System.out.println("number-is-Integer=" +
        (((Object) number) instanceof Integer));
System.out.println("names-count=" + names.size());
System.out.println("set-has-alpha=" + set.contains("alpha"));
System.out.println("diamond-element-object=" +
        (inferredObject.get(0) instanceof Object));
System.out.println("array-sum=" +
        java.util.Arrays.stream(numbers).sum());
System.out.println("twice(7)=" + twice.applyAsInt(7));

int total = 0;
for (var n : numbers) total += n;
System.out.println("foreach-sum=" + total);

try (var reader = new java.io.StringReader("ok")) {
    System.out.println("reader-first=" + (char) reader.read());
}

/vars
/list
/exit
~~~

Chạy từ thư mục chứa file:

~~~bash
jshell --feedback normal -C--release=10 var-lab.jsh
~~~

**Tám dòng do `System.out.println` in ra đã được kiểm chứng trên JShell 24.0.2 với target Java 10:**

~~~text
number-is-Integer=true
names-count=2
set-has-alpha=true
diamond-element-object=true
array-sum=6
twice(7)=14
foreach-sum=6
reader-first=o
~~~

Ngoài tám dòng ấy, `/vars` và `/list` **cũng sẽ in thêm thông tin**. Trong `/vars`, các kiểu gồm:

~~~text
int number = 10
String label = "Java 10"
List<String> names = [An, Binh]
HashSet<String> set = [alpha]
ArrayList<Object> inferredObject = [text]
int[] numbers = int[3] { 1, 2, 3 }
IntUnaryOperator twice = ...
int total = 6
~~~

Dấu `...` trên dòng `twice` đại diện cho một **lambda object value không ổn định giữa các lần chạy**, không phải output nguyên văn. JShell có thể dùng các ID `$N` cho kết quả của `set.add(...)` và `inferredObject.add(...)`; **không hard-code ID và giá trị định danh lambda** khi đối chiếu output.

### Giải thích nhanh từng dòng kiểm chứng

- `number-is-Integer=true`: khi `int number` được ép qua `Object`, có boxing thành `Integer`.
- `names-count=2`: `List.of` nhận đúng hai chuỗi.
- `set-has-alpha=true`: `HashSet<String>` có phần tử vừa thêm.
- `diamond-element-object=true`: phần tử đã thêm là một object không null; **kiểu generic của biến** phải kiểm qua `/vars`, không suy từ mỗi dòng này.
- `array-sum=6` và `foreach-sum=6`: hai cách cộng các số 1, 2, 3.
- `twice(7)=14`: lambda nhận target type `IntUnaryOperator` và nhân đôi.
- `reader-first=o`: `StringReader` đọc ký tự đầu `o`; try-with-resources tự đóng reader.

**Đặc điểm học tập của JShell:** một script có thể gồm nhiều snippets, không yêu cầu tất cả được viết trong cùng method. Khi chuyển code sang `.java`, phạm vi biến và cấu trúc class/method sẽ tuân thủ luật Java thông thường.

## 6. Các vị trí `var` hợp lệ trong Java 10

| Nơi khai báo | Ví dụ | Java 10 |
| --- | --- | --- |
| Local variable trong method/block | `var count = 3;` | **Có** |
| `for` initializer | `for (var i = 0; i < 3; i++) ...` | **Có** |
| Enhanced `for` | `for (var name : names) ...` | **Có** |
| Try-with-resources | `try (var in = new StringReader("a")) {...}` | **Có** |
| Local final | `final var price = 100;` | **Có** |
| Không có initializer | `var number;` | **Không** |
| Field trong class | `class C { var x = 3; }` | **Không** |
| Return type method | `var read() {...}` | **Không** |
| Tham số method | `void f(var x) {...}` | **Không** |
| Nhiều biến một lần | `var a = 1, b = 2;` | **Không** |
| `var` trong tham số lambda | `(var a, var b) -> ...` | **Chưa có ở Java 10**, được bổ sung ở Java 11 |

**Lưu ý:** JShell cho phép `var x=1` dưới dạng **variable snippet cấp cao nhất**. Điều này không tạo quyền dùng `var` làm field của một class Java bình thường. Ví dụ `class C { var x=1; }` bị từ chối trong JShell với compiler Java 10.

### Dùng `var` trong enhanced for và try-with-resources

~~~java
var numbers = new int[]{2, 4, 6};
int sum = 0;
for (var n : numbers) sum += n;
System.out.println("sum=" + sum);
~~~

Stdout:

~~~text
sum=12
~~~

Ví dụ reader:

~~~java
try (var reader = new java.io.StringReader("AB")) {
    System.out.println("first=" + (char) reader.read());
}
~~~

Stdout:

~~~text
first=A
~~~

Kiểu `StringReader` được suy luận từ `new StringReader(...)`. Try-with-resources tự đóng tài nguyên vì reader là `AutoCloseable`; **không phải nhờ riêng `var`**.

### `final var` không làm object trở thành immutable

~~~java
final var names = new java.util.ArrayList<String>();
names.add("one"); // Hợp lệ
~~~

Bản thân biến `names` không được gán lại, nhưng object list vẫn có thể sửa. Không nhầm **final reference** với một immutable collection.

## 7. Những biểu thức bị từ chối — thử bằng JShell

Tạo file **`invalid-vars.jsh`**. Các dòng đầu **cố ý sai** để học cách đọc compiler diagnostics:

~~~java
var nothing = null;
var notInitialized;
var fn = x -> x + 1;
var methodRef = String::trim;
var values = {1, 2, 3};
var a = 1, b = 2;
class InvalidField { var property = 1; }
int invalidParameter(var n) { return n; }
java.util.function.BinaryOperator<String> glue =
        (var a, var b) -> a + b;

var cleanArray = new int[]{1, 2, 3};
System.out.println("good-array-length=" + cleanArray.length);

var goodOp = (java.util.function.IntUnaryOperator) (n -> n + 1);
System.out.println("good-lambda=" + goodOp.applyAsInt(4));

/vars
/exit
~~~

Chạy:

~~~bash
jshell --feedback normal -C--release=10 invalid-vars.jsh
~~~

**Các negative cases đã được kiểm chứng bằng JShell 24.0.2:**

| Snippet không hợp lệ | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `var nothing = null` | `null` không cung cấp type có thể suy ra trong trường hợp này | `String nothing = null` hoặc `var nothing = (String) null` |
| `var notInitialized;` | `var` yêu cầu initializer | Cung cấp biểu thức khởi tạo |
| `var fn = x -> x + 1` | Lambda cần **target functional interface** | Dùng `IntUnaryOperator fn = ...` hoặc cast target type |
| `var methodRef = String::trim` | Method reference cần target type | Dùng `Function<String,String> ref = String::trim` |
| `var values = {1,2,3}` | Array initializer trần cần type context | `var values = new int[]{1,2,3}` |
| `var a = 1, b = 2` | `var` không cho compound declaration | Tách thành hai khai báo |
| `class InvalidField { var property=1; }` | Field không được dùng `var` | Viết kiểu tường minh, ví dụ `int property` |
| `int invalidParameter(var n)` | Method parameter không được dùng `var` | Viết tham số kiểu tường minh |
| `BinaryOperator<String> glue=(var a,var b)->...` | Java 10 chưa có syntax lambda parameters với `var` | Viết `(a,b)->...` hoặc dùng source level Java 11+ nếu dự án cho phép |

Các dòng hợp lệ phía sau vẫn chạy, và hai dòng do `System.out.println` in ra là:

~~~text
good-array-length=3
good-lambda=5
~~~

**Quan trọng:** JShell **tiếp tục chạy các snippets kế tiếp sau compiler error**. Trong thử nghiệm, file này vẫn có thể làm process `jshell` kết thúc với exit code **0**, dù rất nhiều snippet đã bị từ chối. Không dùng exit code của script làm tiêu chí duy nhất để khẳng định tất cả biểu thức `var` đã hợp lệ.

### Vì sao cast giúp lambda đúng?

Không hợp lệ:

~~~java
var adder = x -> x + 1;
~~~

Hợp lệ vì có **target type**:

~~~java
var adder = (java.util.function.IntUnaryOperator)
        (x -> x + 1);
~~~

Trong code thật thường rõ hơn nếu viết trực tiếp:

~~~java
java.util.function.IntUnaryOperator adder = x -> x + 1;
~~~

**Nguyên lý:** lambda expression và method reference là các **poly expressions** — chúng cần ngữ cảnh kiểu để được diễn giải, không thể dùng `var` trần và mong compiler đoán một functional interface bất kỳ.

## 8. Phân biệt `var` Java 10 và tham số lambda Java 11

**JEP 286** (Java 10) áp dụng local variables. **JEP 323** (Java 11) cho phép `var` trong formal parameters của lambda vốn được suy luận:

~~~java
java.util.function.BinaryOperator<String> concat =
        (var left, var right) -> left + right;
~~~

Đoạn này **không phải Java 10**. Với JShell JDK 24 và `-C--release=10`, compiler từ chối với nhóm chẩn đoán:

~~~text
var syntax in implicit lambdas are not supported in -source 10
~~~

Điều đó **không phủ nhận** Java 10 hỗ trợ:

~~~java
var concat = (java.util.function.BinaryOperator<String>)
        (left, right) -> left + right;
~~~

Ở ví dụ thứ hai, `var` là **local-variable type inference**, còn tham số lambda không dùng từ `var`; cast đã cung cấp target type. Đừng dạy cú pháp JDK 11+ như một phần của Java 10 chỉ vì nó chạy được trên JShell phiên bản mới mặc định.

## 9. Phân biệt API Java 10 với API JDK mới: `String.isBlank()`

`String.isBlank()` được thêm ở **Java 11**. Đoạn sau sẽ không hợp lệ nếu kiểm Java 10:

~~~java
var newer = " ".isBlank();
~~~

Tạo file **`release-api.jsh`**:

~~~java
var newer = " ".isBlank();
System.out.println("after-api-test=true");
/exit
~~~

Chạy hai phiên **tách biệt**:

~~~bash
jshell --feedback normal -C--release=10 release-api.jsh
jshell --feedback normal release-api.jsh
~~~

**Kết quả đã kiểm chứng bằng JDK 24.0.2:**

- **Phiên có `-C--release=10`:** compiler **từ chối** `isBlank()` với diagnostic thuộc nhóm `cannot find symbol: method isBlank()`.
- **Phiên JShell JDK 24 mặc định:** snippet được **chấp nhận**, do API đã có ở JDK 24.
- **Cả hai phiên** có thể in `after-api-test=true` và exit code **0**; đoạn println phía sau vẫn được JShell thực hiện ngay cả khi snippet trước bị lỗi.

**Kết luận:** `-C--release=10` kiểm **source/API level** khi compiler hỗ trợ; nó không khởi chạy một JVM Java 10 khác. Nếu ứng dụng thực tế cần tương thích chính xác với một runtime cụ thể, phải có test runtime bổ sung phù hợp.

## 10. `var` có phải kiểu động? Thử gán và định nghĩa lại

Trong JShell:

~~~java
var value = 10;
value = "text";
~~~

Lệnh thứ hai bị từ chối: **`String` không gán được cho `int`**. Kiểu của `value` được compiler cố định khi khai báo ban đầu.

Bây giờ gõ **một khai báo mới**:

~~~java
var value = "text";
System.out.println("after-redefinition=" + value.toUpperCase());
~~~

Stdout đã kiểm chứng:

~~~text
after-redefinition=TEXT
~~~

`/vars` lúc này thấy `String value = "text"`. Đây là khả năng **redefinition snippet của JShell**; trong một Java method, không thể redeclare cùng tên local variable trong cùng scope theo cách đó. Không kết luận `var` là dynamic typing.

Cũng trong thí nghiệm, chạy:

~~~java
var maybe = (String) null;
System.out.println("cast-null=" + (maybe == null));
~~~

Stdout:

~~~text
cast-null=true
~~~

`var maybe = null;` bị từ chối, nhưng **`(String)null` có kiểu `String`** nên trường hợp thứ hai hợp lệ. Khi so sánh các thử nghiệm, dùng `/list -all` để xem snippet rejected hoặc bị thay thế.

## 11. Biên dịch code Java 10 thực tế, không chỉ JShell

Một chương trình hoàn chỉnh giúp tránh nhầm lẫn về scope/redefinition riêng của JShell. Tạo file **`Java10VarDemo.java`**:

~~~java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.function.IntUnaryOperator;

public class Java10VarDemo {
    static String run() throws Exception {
        var number = 10;
        var names = List.of("An", "Binh");
        var values = new ArrayList<String>();
        values.add("text");

        var loose = new ArrayList<>();
        loose.add("anything");

        int result = 0;
        for (var n : new int[]{1, 2, 3}) result += n;
        for (var index = 0; index < 2; index++) result += index;
        try (var reader = new StringReader("ok")) {
            result += reader.read();
        }
        var handler = (IntUnaryOperator) (x -> x * 2);

        return "number=" + number
                + ";names=" + names.size()
                + ";typedLength=" + values.get(0).length()
                + ";inferredObject=" + (loose.get(0) instanceof Object)
                + ";sum=" + result
                + ";handler=" + handler.applyAsInt(7);
    }

    public static void main(String[] args) throws Exception {
        System.out.println(run());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 Java10VarDemo.java
java Java10VarDemo
~~~

**Stdout chính xác đã kiểm thử trên JDK 24:**

~~~text
number=10;names=2;typedLength=4;inferredObject=true;sum=118;handler=14
~~~

**Giải thích phép tính:** for-each tổng `1+2+3=6`, vòng `for` chỉ cộng `0+1=1`, và `StringReader.read()` trả mã ký tự `'o' = 111`. Tổng `6+1+111=118`. `handler.applyAsInt(7)=14`. `List.of` có 2 phần tử, chuỗi `"text"` dài 4.

**Lợi ích của đối chứng:** JShell cho bạn sửa snippet rất nhanh, nhưng `javac --release 10` trên source file thật xác minh rằng code **thực sự hợp lệ với cú pháp/API Java 10** và không đang lợi dụng khả năng khai báo lại biến của REPL. Runtime vẫn là JVM được dùng ở câu lệnh `java`.

## 12. Kiểm thử tự động bằng `jdk.jshell` thay vì chỉ đọc stdout

Để một pipeline thật sự biết **snippet hợp lệ hay bị từ chối**, JDK có module **`jdk.jshell`**. API `JShell.eval(String)` trả những `SnippetEvent`, từ đó có thể kiểm `Snippet.Status.VALID`, `REJECTED`, diagnostics và kiểu biến từ `VarSnippet.typeName()`.

Tạo file **`JsApiContractTest.java`**:

~~~java
import java.util.List;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;
import jdk.jshell.VarSnippet;

public class JsApiContractTest {
    static SnippetEvent one(JShell shell, String source) {
        List<SnippetEvent> events = shell.eval(source);
        if (events.size() != 1) {
            throw new AssertionError(
                    "Unexpected events for " + source);
        }
        return events.get(0);
    }

    static void expectType(JShell shell, String source,
                           String expectedType) {
        SnippetEvent event = one(shell, source);
        if (event.status() != Snippet.Status.VALID
                || !(event.snippet() instanceof VarSnippet)) {
            throw new AssertionError(
                    "Expected valid variable: " + source);
        }

        String actual = ((VarSnippet) event.snippet()).typeName();
        if (!expectedType.equals(actual)) {
            throw new AssertionError(expectedType + " != " + actual);
        }
    }

    static void expectRejected(JShell shell, String source) {
        SnippetEvent event = one(shell, source);
        if (event.status() != Snippet.Status.REJECTED
                || shell.diagnostics(event.snippet()).count() == 0) {
            throw new AssertionError(
                    "Expected rejected: " + source);
        }
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.builder()
                .compilerOptions("--release", "10").build()) {
            expectType(shell, "var count = 10;", "int");
            expectType(shell, "var text = \"Java 10\";", "String");
            expectType(shell,
                    "var list = new java.util.ArrayList<>();",
                    "java.util.ArrayList<Object>");

            expectRejected(shell, "var unknown = null;");
            expectRejected(shell,
                    "var newer = \" \".isBlank();");
            expectRejected(shell,
                    "java.util.function.BinaryOperator<String> f = "
                    + "(var a, var b) -> a + b;");

            System.out.println("valid-snippets=3");
            System.out.println("rejected-snippets=3");
            System.out.println("java10-checks=PASS");
        }
    }
}
~~~

Lệnh (trên một JDK có module `jdk.jshell` và compiler target 10):

~~~bash
javac --release 10 JsApiContractTest.java
java JsApiContractTest
~~~

**Stdout đã kiểm chứng:**

~~~text
valid-snippets=3
rejected-snippets=3
java10-checks=PASS
~~~

Chương trình **ném `AssertionError` nếu status hoặc type không đúng**; vì vậy có thể dùng như một bài kiểm chứng thực sự thay cho việc chỉ nhìn JShell script exit 0. `JShell.Builder.compilerOptions("--release","10")` đặt target cho snippet compiler; `VarSnippet.typeName()` xác định kiểu suy luận `int`, `String` và `java.util.ArrayList<Object>`.

**Một khác biệt hiển thị:** Tại script tương tác có `import java.util.*`, `/vars` có thể viết `ArrayList<Object>`. Trong API test, snippet dùng tên đầy đủ `java.util.ArrayList<>` nên `typeName()` trả `java.util.ArrayList<Object>`. Điều cần so là kiểu, không phải cách rút gọn class name trong mọi UI.

**API `jdk.jshell` dành cho công cụ JDK**, không phải điều kiện cần để sử dụng `var` trong code ứng dụng. Một `javac` hỗ trợ Java 10+ đã xử lý `var` khi biên dịch source code bình thường.

## 13. Quy tắc QA quan trọng: JShell có thể “exit 0” dù snippet lỗi

Tạo file script:

~~~java
var invalid = null;
System.out.println("after-error=true");
/exit
~~~

Nếu nạp bằng `jshell -C--release=10`:

1. JShell in chẩn đoán vì `var invalid = null` không hợp lệ.
2. JShell **vẫn tiếp tục** thực thi `System.out.println` và in `after-error=true`.
3. `/exit` thông thường làm công cụ kết thúc với **mã 0**, dù có một snippet bị lỗi biên dịch.

Đã kiểm chứng hành vi này bằng JShell 24.0.2. Do vậy, một script CI kiểu “chạy JShell xong thấy `$LASTEXITCODE == 0` là PASS” là **không đầy đủ**. Tốt hơn dùng:

- **Thủ công:** `/vars`, `/list -all`, đọc compiler errors.
- **Tự động kiểm kiểu:** API `JShell`/`SnippetEvent.status`/`VarSnippet.typeName` như bài kiểm `JsApiContractTest`.
- **Ứng dụng `.java`:** `javac --release 10` và unit/integration tests của project.
- **Không hard-code text động:** ID `$N`, hash/địa chỉ lambda object, toàn bộ thông báo diagnostic cụ thể theo JDK.

JShell là **REPL phục vụ thử nghiệm**, không được thiết kế để mỗi rejected snippet trong một file luôn làm process tool trả nonzero exit code.

## 14. Các lệnh JShell cần biết

| Lệnh | Chức năng | Tình huống |
| --- | --- | --- |
| `/help` hoặc `/help intro` | Trợ giúp | Tìm cú pháp đúng phiên bản |
| `/vars` | Biến đang active, kiểu và giá trị | **Kiểm `var` inferred type** |
| `/vars -all` | Kể cả biến bị thay, không còn active | Xem lịch sử redefinition |
| `/list` | Liệt kê active snippets cùng source/ID | Kiểm cái gì đã chạy |
| `/list -all` | Cả rejected, overwritten, dropped snippets | **Phân tích lỗi** |
| `/imports` | Imports đang có | Chẩn đoán mất type do thiếu import |
| `/methods` | Methods đã khai báo | Kiểm signature |
| `/types` | Classes/interfaces/enums | Kiểm type snippets |
| `/drop ten-bien` | Vô hiệu snippet theo tên/ID | Thử lại độc lập |
| `/reset` | Xóa snippets đã nhập và nạp lại startup theo cấu hình | Bắt đầu test sạch |
| `/open var-lab.jsh` | Chạy file script trong phiên | Nạp lại bộ ví dụ |
| `/save my-snippets.jsh` | Lưu snippets active | Chia sẻ bài học |
| `/set feedback verbose` | Đổi mức phản hồi | Xem rõ feedback khi học |
| `/exit` | Thoát | Không có nghĩa mọi snippet trước đó đều đúng |

**Cảnh báo về `/reset`:** Nó bỏ các biến/snippets người dùng khai báo, nhưng startup imports/cấu hình môi trường có thể được nạp lại. Trong thí nghiệm thực tế, sau `var sessionValue=123` rồi `/reset`, `/vars` không còn liệt kê `sessionValue`.

### JShell script và classpath

Nếu muốn kiểm một dependency JAR riêng, dùng:

~~~bash
jshell --class-path libs/example.jar -C--release=10
~~~

Đường JAR ở trên **chỉ là ví dụ về cú pháp**, không cần file đó để chạy bài `var`. Khi có JAR thật, cần kiểm thêm bytecode/API compatibility của dependency; việc snippet compile dưới `--release10` **không tự đảm bảo** toàn bộ thư viện/runtime có thể chạy đúng trên JVM Java 10.

JShell startup mặc định thường import `java.util.*`, nhưng tệp `var-lab.jsh` vẫn viết `import java.util.*;` tường minh để dễ tái tạo. Nếu dùng `--no-startup`, các imports mặc định không có; phải import hoặc dùng tên class đầy đủ.

## 15. Khi nào nên dùng `var` trong code thật?

**Dùng khi kiểu rõ ràng từ initializer:** `var count=10`, `var file=Path.of(...)` (lưu ý `Path.of` chỉ có từ Java 11, **không dùng trong code nhắm Java 10**), `var names=List.of(...)`, `var user=new User(...)` khi class rõ.

**Cân nhắc kiểu tường minh** khi kiểu là **phần quan trọng của API contract** hoặc initializer che khuất ý nghĩa:

~~~java
java.util.List<String> items = new java.util.ArrayList<>();
~~~

So với:

~~~java
var items = new java.util.ArrayList<String>();
~~~

Cả hai có thể chứa String, nhưng biến thứ nhất được khai báo qua interface **`List<String>`**. Chọn kiểu tường minh có thể tăng tính linh hoạt khi thay implementation; không nên ép `var` trong mọi tình huống.

### Những ngộ nhận cần tránh

- “`var` biến Java thành JavaScript kiểu động.” **Sai** — Java vẫn static typing.
- “`var x = null` hợp lệ vì null là object.” **Sai** — thiếu type để infer.
- “`var` suy ra generic type từ những lệnh `add()` phía sau.” **Sai** — inference thực hiện khi khai báo.
- “`new ArrayList<>()` luôn hiểu là `ArrayList<String>`.” **Sai** — nếu thiếu context có thể thành `ArrayList<Object>`.
- “Chạy được trên JShell JDK 24 nghĩa là cú pháp/API Java 10.” **Sai** — cần compiler release target và đối chiếu nguồn.
- “`var` dùng được cho field/method parameter/return type.” **Sai** — Java 10 local-variable syntax có phạm vi rõ ràng.
- “Cú pháp `var` trong lambda parameter là Java 10.” **Sai** — Java 11 JEP 323.
- “`var` giảm runtime overhead vì không cần type.” **Sai** — compiler vẫn quyết định type tĩnh.
- “JShell cho redefinition nên biến đổi kiểu lúc chạy.” **Sai** — REPL thay snippet.
- “`jshell` exit code 0 nghĩa mọi snippet hợp lệ.” **Sai** — cần diagnostics/status.
- “`getClass()` có thể đọc đủ generic type của mọi `var`.” **Sai** — type erasure làm mất generic arguments runtime.
- “`final var` làm object bất biến.” **Sai** — ràng buộc tham chiếu/biến, không đóng băng object.

### Đề xuất thói quen thực hành

Viết biểu thức muốn thử → xem `/vars` → quan sát compile errors đối với biến thể sai → chuyển vào file `.java` → chạy `javac --release 10` → so unit test output. Dùng `var` khi làm code **dễ đọc hơn**, không phải vì phải chứng tỏ mình biết cú pháp mới.

## 16. Troubleshooting những vấn đề thường gặp

| Triệu chứng | Vì sao xảy ra? | Cách sửa |
| --- | --- | --- |
| `jshell` không tồn tại | Dùng runtime image/JRE tối giản hoặc PATH sai | Chọn JDK có JShell, kiểm `JAVA_HOME/bin` |
| JDK9 JShell không nhận `var` | JEP 286 chỉ từ Java 10 | Dùng JDK10+ |
| `-C--release=10` báo unsupported | Compiler JDK không hỗ trợ target đó | Xem `jshell --help`/`javac --help`, chọn JDK phù hợp |
| Thấy lỗi khi gõ `-C--release=10` trong JShell | Đó là launcher option | Thoát và truyền trên command line |
| `var x;` lỗi | Thiếu initializer | Gán giá trị hoặc dùng kiểu tường minh |
| `var nothing=null` lỗi | Không suy ra type từ null thuần | Cast hoặc kiểu tường minh |
| Lambda/method ref lỗi với `var` | Thiếu target type | Dùng functional interface cụ thể |
| Array initializer trần lỗi | Cần type context | Dùng `new int[]{...}` |
| `var` trong class field bị từ chối | Không thuộc phạm vi JEP 286 | Viết kiểu tường minh |
| Lambda params `var` lỗi ở Java10 target | Tính năng từ Java11 | Dùng tham số không có `var` |
| `String.isBlank` bị từ chối | API Java11, không phải Java10 | Dùng API Java10 hoặc cập nhật target có chủ đích |
| `/vars` có kiểu khác mong muốn | Generic inference hoặc snippet redefinition | Xem initializer và `/list -all` |
| `/vars` không thấy biến vừa khai báo | Snippet có compiler error hoặc đã `/reset`/`/drop` | Xem diagnostics và state |
| Output `$1` thay đổi giữa lần chạy | Scratch IDs phụ thuộc session | Dùng các nhãn `System.out.println` cố định |
| Lambda hiển thị tên/địa chỉ khác | Value representation không ổn định | Kiểm type và hành vi function |
| `jshell` script có error nhưng exit 0 | REPL tiếp tục sau lỗi | Dùng API snippet status và test assertions |
| JShell thành công, project compile fail | Script và file code có scope/imports/target khác | Compile source thật bằng `--release` |
| Dùng `List.of` rồi sửa list thất bại | List unmodifiable theo API | Dùng mutable collection nếu cần, không đổ lỗi cho `var` |

## 17. Bài tập tự kiểm tra

1. JShell có từ Java release mấy?
2. `var` trong local variable có từ release nào, JEP gì?
3. `var n=10` suy ra `int` hay `Integer`?
4. `var word="hi"` suy ra kiểu gì?
5. `var names=List.of("A","B")` thường có generic type nào?
6. `var names=new ArrayList<>()` thiếu ngữ cảnh thì có thể suy ra gì?
7. `var x=null` có hợp lệ không? Vì sao `var x=(String)null` lại hợp lệ?
8. Vì sao `var action = s -> s.length()` không thể suy ra functional interface?
9. `var values={1,2}` có hợp lệ không? Thay bằng gì?
10. `var` có hợp lệ trong enhanced for và try-with-resources không?
11. `var` có dùng làm instance field hay return type Java 10 không?
12. `var` ở tham số lambda được hỗ trợ từ Java 10 hay 11?
13. JShell cho `var value=1` rồi `var value="x"` có nghĩa Java dynamic typing không?
14. `/vars` khác `/list` ở điểm nào?
15. Sau `/reset` còn biến user tạo trước đó không?
16. `-C--release=10` có biến runtime JDK24 thành Java10 không?
17. Vì sao `String.isBlank()` bị compiler Java10 từ chối dù runtime mới có API đó?
18. Script JShell báo compiler error nhưng exit code 0 có được xem là QA PASS không?
19. API nào cho phép kiểm `Snippet.Status.REJECTED` và `VarSnippet.typeName()`?
20. Khi nào nên ưu tiên kiểu tường minh thay vì `var`?

**Đáp án:**

1. **Java 9**.
2. **Java 10, JEP 286**.
3. **`int`**.
4. **`String`**.
5. **`List<String>`**.
6. Có thể suy ra **`ArrayList<Object>`**.
7. Null thuần không đủ type; cast `(String)null` cung cấp type `String`.
8. Lambda cần target functional interface.
9. Không; dùng `new int[]{1,2}`.
10. Có.
11. Không.
12. **Java 11, JEP 323**.
13. Không; JShell **định nghĩa lại snippet**, không gán kiểu khác vào biến cũ.
14. `/vars` cho name/type/value, `/list` cho source snippets/IDs.
15. Không; user snippets bị reset.
16. Không; chỉ kiểm compilation level được compiler hỗ trợ.
17. Vì method `String.isBlank` chỉ xuất hiện từ Java11.
18. Không; phải kiểm compiler diagnostics hoặc snippet status.
19. `jdk.jshell.JShell`/`SnippetEvent`/`VarSnippet`.
20. Khi public contract hoặc ý nghĩa type cần minh bạch và initializer không đủ rõ.

## 18. Checklist QA hoàn thành bài

- [ ] Đã xác nhận đúng JDK qua `java -version`, `javac -version`, `jshell --version`.
- [ ] Phân biệt JShell Java9 và `var` Java10.
- [ ] Trên JDK mới, đã dùng `-C--release=10` khi muốn giới hạn cú pháp/API Java10.
- [ ] Không tuyên bố compiler target10 là runtime Java10.
- [ ] Đã xem `/vars` để xác nhận type được infer từ initializer.
- [ ] Đã kiểm kiểu primitive `int`, reference `String`, generics `List<String>`.
- [ ] Đã nhận ra diamond `new ArrayList<>()` có thể cho `ArrayList<Object>`.
- [ ] Đã thử `var` trong for/foreach/try-with-resources.
- [ ] Đã thử negative: không initializer, null, lambda/method ref không target, array initializer.
- [ ] Đã biết `var` không dùng cho field/method parameter/return type.
- [ ] Đã phân biệt `var` lambda parameters Java11 với local `var` Java10.
- [ ] Đã phân biệt phép gán incompatible với JShell redefinition.
- [ ] Đã đối chiếu API Java10 qua `String.isBlank` negative test.
- [ ] Đã compile/run file `Java10VarDemo.java` với `javac --release 10`.
- [ ] Đã chạy `JsApiContractTest.java` và kiểm `VALID/REJECTED` bằng API.
- [ ] Không dùng riêng exit code của JShell file script làm dấu PASS.
- [ ] Không hard-code scratch IDs `$N` hoặc object identities.
- [ ] Không nhầm `var` với dynamic types hoặc tối ưu hiệu năng.
- [ ] Thử nghiệm được chạy trong JDK còn được hỗ trợ và với code Java10 compatible.

## 19. Tham khảo nguồn hiện hành và nguồn gốc tính năng

- **OpenJDK — JEP 286, Local-Variable Type Inference (Java 10):** https://openjdk.org/jeps/286
- **OpenJDK — JEP 323, Local-Variable Syntax for Lambda Parameters (Java 11):** https://openjdk.org/jeps/323
- **Oracle Java SE 17 — Local Variable Type Inference, các quy tắc còn áp dụng:** https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html
- **Oracle Java SE 25 — `jshell` command (`-C--release=<N>`, /vars, /list, /reset):** https://docs.oracle.com/en/java/javase/25/docs/specs/man/jshell.html
- **Oracle Java SE 10 — `jshell` (mốc lịch sử, các lệnh vẫn phổ biến):** https://docs.oracle.com/javase/10/tools/jshell.htm
- **Oracle Java SE 25 — JShell User Guide:** https://docs.oracle.com/en/java/javase/25/jshell/index.html
- **Oracle Java SE 26 — JShell Commands:** https://docs.oracle.com/en/java/javase/26/jshell/commands.html
- **Oracle Java SE 25 — `jdk.jshell.JShell` API:** https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jshell/jdk/jshell/JShell.html
- **Oracle Java SE 25 — `VarSnippet` và `SnippetEvent`:** https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jshell/jdk/jshell/VarSnippet.html
- **Oracle Java SE 25 — `javac --release`:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- **Oracle Java SE 11 — thay đổi ngôn ngữ, phân biệt JEP 286 và JEP 323:** https://docs.oracle.com/en/java/javase/11/language/java-language-changes-release.html

**Kết luận:** Có thể **thử `var` theo Java 10 ngay trong JShell** của một JDK phù hợp bằng `jshell -C--release=10`, rồi dùng `/vars` kiểm **kiểu tĩnh suy luận** từ initializer. Những chỗ sai như `var x=null`, lambda không có target type hoặc field `var` phải bị compiler từ chối. JShell hỗ trợ **redefinition của snippet**, không phải dynamic typing. Khi chuyển sang dự án thật, hãy compile bằng **`javac --release 10`** và chạy unit tests. Đối với kiểm thử tự động, dùng **`SnippetEvent.status()`** hoặc kiểm build thật, **không** xem exit code 0 của JShell script là bằng chứng mọi snippet đều hợp lệ.