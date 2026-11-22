# Cú pháp khai báo biến bằng `var` và biểu thức khởi tạo trong Java

## 1. Mục tiêu và phạm vi

Từ **Java 10**, có thể sử dụng `var` để khai báo **biến cục bộ** khi trình biên dịch đủ thông tin suy luận kiểu từ **biểu thức khởi tạo (initializer)**. Cú pháp này tiếp tục dùng được trong các phiên bản Java hiện đại; đây là một tiện ích của **ngôn ngữ Java định kiểu tĩnh**, không phải cơ chế kiểu động.

Sau bài này, bạn có thể:

- Viết đúng khai báo `var identifier = expression;` và `final var identifier = expression;`.
- Giải thích vì sao initializer quyết định kiểu tại thời điểm biên dịch, trong khi gán giá trị sau đó không làm đổi kiểu.
- Nhận biết initializer hợp lệ: literal, phép tính, lời gọi phương thức, biểu thức tạo đối tượng, mảng, biểu thức điều kiện và biểu thức có kiểu đích rõ ràng.
- Nhận biết initializer không hợp lệ hoặc dễ gây suy luận sai: thiếu initializer, `null` thuần túy, lambda/method reference chưa có kiểu đích, array initializer dạng `{...}` và constructor generic dùng diamond không đủ thông tin.
- Phân biệt vị trí cho phép `var` với khai báo field, tham số phương thức, kiểu trả về và các vị trí không được hỗ trợ.
- Đọc/viết được một chương trình Java 17+ minh họa và đối chiếu kết quả chạy.

**Giới hạn:** Bài học tập trung vào **cú pháp khai báo và biểu thức khởi tạo**. Những tính năng Java 10 khác không phải điều kiện cần để hiểu `var`. Chỉ những quy tắc còn hiệu lực trong Java hiện đại được trình bày.

## 2. Cú pháp cơ bản

Cú pháp khai báo biến cục bộ:

~~~java
var variableName = initializerExpression;
~~~

Có thể thêm `final` nếu sau khi khởi tạo không muốn cho gán lại tham chiếu/giá trị của biến:

~~~java
final var maxRetry = 3;
~~~

Giải nghĩa:

| Thành phần | Vai trò |
| --- | --- |
| `var` | Yêu cầu trình biên dịch xác định kiểu cục bộ dựa vào initializer. |
| `variableName` | Tên biến hợp lệ trong Java, tồn tại trong phạm vi cục bộ của khai báo. |
| `=` | Gán giá trị khởi tạo ngay trong câu lệnh khai báo. |
| `initializerExpression` | Một **biểu thức Java có thể xác định kiểu** tại thời điểm biên dịch, ví dụ `42`, `"hello"`, `new ArrayList<String>()` hoặc `factory.create()`. |
| `;` | Kết thúc câu lệnh khai báo cục bộ thông thường. |
| `final` (tùy chọn) | Chặn gán lại chính biến sau khi khởi tạo; không tự làm đối tượng được tham chiếu trở thành bất biến sâu. |

So sánh hai cách khai báo tương đương về kiểu:

~~~java
String language = "Java";
var languageName = "Java"; // String được suy luận từ biểu thức "Java"
~~~

Nếu viết:

~~~java
var count = 5;  // int
count = 10;     // hợp lệ
// count = "10"; // lỗi biên dịch: không thể gán String cho int
~~~

**Quy tắc cốt lõi:** kiểu được xác định từ **initializer ban đầu** và được kiểm tra tĩnh. Java không đợi đến lần gán sau, thao tác trên biến hoặc giá trị runtime để quyết định kiểu. `var` cũng không phải viết tắt của `Object`.

Tên `var` là **tên kiểu bị hạn chế (restricted type name)** trong ngữ pháp Java, không phải từ khóa cấm ở mọi ngữ cảnh. Tuy nhiên, nên dành tên biến để diễn đạt ý nghĩa như `count`, `path`, `customers` thay vì dùng chính chữ `var` làm tên.

## 3. Biểu thức khởi tạo hợp lệ và kiểu suy luận

Trình biên dịch suy luận kiểu **từ kiểu của toàn bộ initializer**, không chỉ nhìn một từ hoặc một literal xuất hiện bên trong. Các ví dụ dưới đây giả sử nằm trong thân một phương thức Java.

### 3.1. Giá trị literal và phép tính

~~~java
var number = 10;             // int
var bigNumber = 10L;          // long
var fraction = 10.5;          // double
var rate = 10.5f;             // float
var enabled = true;           // boolean
var letter = 'A';             // char
var title = "Java 10";        // String
var sum = 3 + 4;              // int
var mixed = 3 + 4.0;          // double
var message = "count=" + 2;   // String
~~~

Điều quan trọng là literal số mang kiểu mặc định của Java: `10` có kiểu `int`, `10L` có kiểu `long`, `10.5` có kiểu `double`. Vì vậy:

~~~java
var attempts = 1;   // int
// attempts = 1L;   // lỗi: gán long cho int khi không có chuyển kiểu phù hợp

long attempts2 = 1; // hợp lệ nhờ chuyển kiểu mở rộng int -> long khi khai báo tường minh
~~~

Nếu nghiệp vụ cần một kiểu cụ thể như `long`, `short` hoặc `byte`, hãy thể hiện nó bằng cú pháp hoặc khai báo tường minh thích hợp. Ví dụ `var id = 1L;` suy luận `long`; `var flag = (byte) 1;` suy luận `byte`. Đừng dùng `var` với literal nếu nó khiến người đọc khó nhận ra kiểu mong muốn.

### 3.2. Tạo đối tượng bằng `new`

~~~java
var text = new StringBuilder("Java");          // StringBuilder
var names = new ArrayList<String>();           // ArrayList<String>
var lookup = new HashMap<String, Integer>();   // HashMap<String, Integer>
~~~

`var` thường giảm việc phải viết lại tên kiểu dài ở hai vế. Nhưng kiểu suy luận là **kiểu của biểu thức `new`**, chẳng hạn `ArrayList<String>`, không tự suy luận thành interface rộng hơn `List<String>`.

Khi muốn khai báo theo abstraction/interface ngay từ đầu, một kiểu tường minh có thể truyền đạt ý định thiết kế rõ hơn:

~~~java
List<String> names = new ArrayList<>();
~~~

Đừng hiểu `var names = new ArrayList<String>();` là một `List<String>` được khai báo tường minh; nó là biến có kiểu biên dịch `ArrayList<String>` (dù `ArrayList` triển khai `List`).

### 3.3. Giá trị trả về từ lời gọi phương thức

~~~java
var names = List.of("An", "Binh"); // List<String>, List.of có từ Java 9
var first = names.get(0);         // String
var length = first.length();      // int
var stream = names.stream();      // Stream<String>
~~~

Trình biên dịch dùng **kiểu trả về khai báo** của phương thức sau khi áp dụng suy luận generic, chứ không suy đoán kiểu theo đối tượng cụ thể tại runtime.

Ví dụ, nếu đã có:

~~~java
static CharSequence loadTitle() {
    return "Java";
}
~~~

thì `var label = loadTitle();` có kiểu `CharSequence`. Dù đối tượng thực tế là `String`, không thể giả định biến `label` tự có toàn bộ phương thức riêng của `String`.

**Lưu ý:** Các đoạn `import`, phương thức và khai báo trong mục này là ví dụ cú pháp riêng lẻ; chương trình đầy đủ, chạy được, nằm ở mục 8.

### 3.4. Mảng và biểu thức điều kiện

~~~java
var ids = new int[]{1, 2, 3};             // int[]
var words = new String[]{"A", "B"};       // String[]
var empty = new long[5];                 // long[]
var selected = true ? "left" : "right";  // String
var result = true ? 1 : 2L;             // long
~~~

Với toán tử điều kiện `condition ? left : right`, kiểu suy luận tuân theo quy tắc kiểu của toán tử điều kiện Java, không phải luôn là kiểu của nhánh được chọn khi chạy. Vì vậy `result` có kiểu `long` ở cả hai trường hợp của điều kiện.

Một array initializer trần như `{1, 2, 3}` **không phải biểu thức độc lập có đủ kiểu để dùng ngay sau `var =`**. Muốn dùng `var`, viết `new int[]{1, 2, 3}`; hoặc viết tên kiểu mảng tường minh: `int[] ids = {1, 2, 3};`.

### 3.5. Ép kiểu tường minh cung cấp thông tin kiểu

~~~java
var numeric = (long) 10;       // long
var sequence = (CharSequence) "Java"; // CharSequence
~~~

Ngay cả `var text = (String) null;` cũng xác định được kiểu `String` nhờ phép ép kiểu. Tuy nhiên, câu này tạo giá trị `null` và thường không rõ ràng; nếu cố ý khởi tạo một biến reference bằng `null`, cách viết `String text = null;` dễ đọc hơn. Điều bị cấm là **`var value = null;`**, vì `null` đơn lẻ không có kiểu thích hợp để suy luận.

## 4. Vì sao initializer phải xác định được kiểu?

Khi gặp:

~~~java
var customer = lookupCustomer();
~~~

trình biên dịch xác định kiểu kết quả của `lookupCustomer()` rồi dùng nó làm kiểu của `customer`. Việc này diễn ra tại **thời điểm biên dịch**.

Có ba hệ quả thực tế:

1. **Initializer bắt buộc phải có.** Không thể khai báo `var customer;` rồi gán sau, ngay cả khi các lần gán sau đều cùng kiểu.
2. **Initializer phải cung cấp kiểu.** `null` thuần túy, lambda đơn độc và method reference đơn độc không đủ kiểu đích theo cách suy luận của `var`.
3. **Các phép gán sau phải tương thích với kiểu đã suy luận.** Chúng không thay đổi lại kiểu của biến.

So sánh:

~~~java
String customer;
customer = "Mai"; // hợp lệ: kiểu đã khai báo tường minh

// var customer2; // không hợp lệ: var phải có initializer
~~~

Bên trong biểu thức khởi tạo, biến **đang được khai báo** cũng không được tham chiếu để tự xác định giá trị:

~~~java
// var total = total + 1; // lỗi biên dịch: initializer tự tham chiếu biến
~~~

Hãy khởi tạo bằng một giá trị/biểu thức độc lập hoặc khai báo tường minh khi thật sự cần một chuỗi thao tác gán khác.

## 5. Các dạng khai báo sai: nhận diện và sửa

Những dòng bị chú thích dưới đây là **mã cố ý sai**, không được đưa nguyên dạng vào một chương trình cần biên dịch:

| Cú pháp sai | Nguyên nhân | Cách viết đúng |
| --- | --- | --- |
| `var value;` | Thiếu biểu thức khởi tạo. | `var value = 1;` hoặc `int value;` |
| `var value = null;` | Kiểu `null` không cho biết kiểu biến. | `String value = null;` hoặc thiết kế khác tránh `null`. |
| `var a = 1, b = 2;` | `var` không được khai báo nhiều biến trong cùng một câu lệnh. | `var a = 1; var b = 2;` |
| `var values[] = new int[3];` | Không cho dùng cặp `[]` sau tên biến với `var`. | `var values = new int[3];` |
| `var values = {1, 2};` | Array initializer cần kiểu đích tường minh. | `var values = new int[]{1, 2};` |
| `var self = self + 1;` | Biểu thức khởi tạo tham chiếu chính biến đang khai báo. | Khởi tạo từ giá trị có sẵn hoặc khai báo kiểu tường minh và gán hợp lệ sau. |
| `var action = x -> x + 1;` | Lambda chưa có target functional-interface type. | `Function<Integer, Integer> action = x -> x + 1;` |
| `var measure = String::length;` | Method reference chưa có target functional-interface type. | `Function<String, Integer> measure = String::length;` |

Quy tắc về lambda và method reference không có nghĩa **không thể** dùng chúng với `var`. Chúng cần được đặt trong ngữ cảnh đã xác định kiểu hàm:

~~~java
Function<String, Integer> lengthA = String::length;

// Hợp lệ: phép ép kiểu cho method reference biết kiểu đích trước khi suy luận var
var lengthB = (Function<String, Integer>) String::length;

System.out.println(lengthA.apply("Java")); // 4
System.out.println(lengthB.apply("Java")); // 4
~~~

Ở đây `Function` là `java.util.function.Function`. Trong code ứng dụng, viết tên interface tường minh thường dễ đọc hơn việc ép kiểu chỉ để giữ chữ `var`.

## 6. Phạm vi cho phép sử dụng `var`

Trong Java 10 và các phiên bản hiện đại, `var` dùng tại những vị trí khai báo biến cục bộ phù hợp:

~~~java
// Bên trong một phương thức hoặc khối lệnh:
var city = "Ha Noi";

// Trong for truyền thống:
for (var index = 0; index < 3; index++) {
    System.out.println(index);
}

// Trong for-each:
for (var name : List.of("An", "Binh")) {
    System.out.println(name);
}

// Trong resource của try-with-resources:
try (var reader = new java.io.StringReader("Java")) {
    System.out.println((char) reader.read());
}
~~~

Ví dụ `try-with-resources` có tính minh họa và chỉ cần thư viện chuẩn; đối tượng `StringReader` hỗ trợ `AutoCloseable` thông qua `Reader`. Với vòng lặp `for`, `index` được suy luận là `int`; với `for-each`, `name` được suy luận là `String`.

Không dùng `var` thay cho kiểu trả về, field của lớp hay tham số phương thức thông thường:

~~~java
class InvalidExamples {
    // private var code = 10;             // SAI: instance field
    // static var shared = "x";           // SAI: static field
    // var getCount() { return 10; }     // SAI: return type
    // void print(var value) {}           // SAI: method parameter
    // InvalidExamples(var id) {}         // SAI: constructor parameter
}
~~~

Đây là các dòng **minh họa lỗi**, đã được chú thích để không gây lỗi cú pháp nếu bạn sao chép ví dụ. Java 11 bổ sung cú pháp `var` cho tham số của một số lambda khi có ngữ cảnh suy luận, nhưng đó là thay đổi sau Java 10 và **không biến `var` thành kiểu dùng được cho tham số phương thức**.

**Phạm vi biến** vẫn theo quy tắc Java thông thường: biến cục bộ chỉ truy cập được trong block/phạm vi khai báo thích hợp; `var` không làm biến tự động có phạm vi toàn lớp.

## 7. Kiểu suy luận với generic, diamond và tính dễ đọc

### 7.1. Tránh suy luận `Object` ngoài ý muốn

~~~java
var loose = new ArrayList<>();       // ArrayList<Object>
loose.add("A");
loose.add(123);                      // hợp lệ vì danh sách nhận Object

var strict = new ArrayList<String>(); // ArrayList<String>
strict.add("A");
// strict.add(123);                   // lỗi: Integer không phải String
~~~

Khi sử dụng `new ArrayList<>()`, toán tử diamond `<>` cần ngữ cảnh để suy luận tham số kiểu. Sau `var`, không có tên kiểu tường minh ở vế trái để định hướng, nên trong ví dụ này kiểu phần tử được suy luận thành `Object`. Đừng mặc định trình biên dịch sẽ đoán `String` từ các lần `add` **sau** khai báo.

Nếu muốn khai báo qua interface với generic rõ ràng:

~~~java
List<String> strict = new ArrayList<>();
~~~

Hoặc nếu dùng `var` vì vế phải đã rõ:

~~~java
var strict = new ArrayList<String>();
~~~

Hai đoạn trên là **hai lựa chọn thay thế**, không đặt cùng phạm vi dưới cùng tên `strict`.

### 7.2. Khi nào nên ghi kiểu tường minh?

| Tình huống | Khai báo thường dễ đọc |
| --- | --- |
| Vế phải cho biết kiểu rất rõ | `var names = new ArrayList<String>();` |
| Giá trị trả về của factory ít rõ và kiểu quan trọng | `List<Customer> customers = repository.findAll();` |
| Muốn định kiểu bằng interface | `Map<String, Integer> counts = new HashMap<>();` |
| Literal số phải có kiểu nghiệp vụ cụ thể | `long timeoutMillis = 1000;` hoặc `var timeoutMillis = 1000L;` |
| Dữ liệu có thể chứa `null` hoặc chưa có giá trị ban đầu | Khai báo kiểu tường minh, cân nhắc `Optional` hoặc thiết kế tránh `null`. |
| Biểu thức lambda/method reference cần target type | `Function<String, Integer> length = String::length;` |

Nguyên tắc: dùng `var` để **xóa lặp cú pháp** mà vẫn giữ được ý nghĩa của biến. Tên biến cần nói được vai trò (`retryCount`, `usersById`, `sourcePath`), và initializer nên gần khai báo để người đọc nhìn ra kiểu.

### 7.3. `final var` không làm đối tượng bất biến sâu

~~~java
final var colors = new ArrayList<String>();
colors.add("red"); // hợp lệ: thay đổi nội dung đối tượng
// colors = new ArrayList<String>(); // không hợp lệ: gán lại biến final
~~~

`final` khóa thao tác **gán lại biến**, không tự cấm gọi phương thức thay đổi của đối tượng. Nếu yêu cầu collection không sửa đổi, hãy chọn cấu trúc/API phù hợp như `List.of(...)` hoặc `List.copyOf(...)` cùng với dữ liệu phần tử thích hợp. Các API này vẫn có giá trị trong Java hiện đại, nhưng chúng giải quyết vấn đề **tính không sửa đổi collection**, khác với bài toán **suy luận kiểu của `var`**.

## 8. Ví dụ đầy đủ có thể biên dịch và chạy (Java 17+)

Tạo tệp **`VarInitializerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.function.Function;

public class VarInitializerDemo {
    public static void main(String[] args) {
        var quantity = 2;                            // int
        var price = 3.5;                             // double
        var language = "Java";                       // String

        var topics = new ArrayList<String>();       // ArrayList<String>
        topics.add(language);
        topics.add("var");

        var topicCount = topics.size();              // int
        var tags = new String[]{"type", "init"};     // String[]
        var upper = (Function<String, String>)
                String::toUpperCase;                 // Function<String, String>

        final var version = 10;                      // int, không gán lại được

        System.out.println("quantity=" + quantity);
        System.out.println("price=" + price);
        System.out.println("topics=" + topics);
        System.out.println("topicCount=" + topicCount);
        System.out.println("tags=" + Arrays.toString(tags));
        System.out.println("upper=" + upper.apply(topics.get(1)));
        System.out.println("version=" + version);
    }
}
~~~

Trong thư mục chứa tệp, chạy:

~~~bash
javac VarInitializerDemo.java
java VarInitializerDemo
~~~

**Kết quả chuẩn (stdout):**

~~~text
quantity=2
price=3.5
topics=[Java, var]
topicCount=2
tags=[type, init]
upper=VAR
version=10
~~~

Giải thích từng bước:

1. Các literal `2`, `3.5` và `"Java"` có kiểu `int`, `double` và `String`; `var` giữ các kiểu đó.
2. `new ArrayList<String>()` tạo biểu thức kiểu `ArrayList<String>`; các lệnh `add` sau chỉ chấp nhận `String`.
3. `topics.size()` trả `int` nên `topicCount` là `int`.
4. `new String[]{...}` là biểu thức khởi tạo mảng có kiểu `String[]`, khác với mảng viết dưới dạng `{...}` đứng độc lập.
5. Ép kiểu `(Function<String, String>)` cấp kiểu đích cho `String::toUpperCase`, nên `upper` có thể suy luận được.
6. `final var version = 10;` suy luận `int` nhưng cấm gán lại biến `version`.

Ví dụ dùng những API ổn định của thư viện chuẩn, có thể chạy trên Java 17 hoặc JDK mới hơn. Nó cũng chỉ dùng cú pháp tương thích Java 10. Nếu biên dịch với JDK hiện đại và cần kiểm tra đúng API/bytecode của Java 10, có thể chạy `javac --release 10 VarInitializerDemo.java` **nếu phiên bản `javac` đang sử dụng vẫn hỗ trợ đích 10**.

## 9. Bài tập ngắn tự kiểm tra

**Bài 1.** Xác định kiểu biên dịch của các biến sau:

~~~java
var a = 1;
var b = 1L;
var c = 1 + 2.0;
var d = new int[]{1, 2};
var e = java.util.List.of("x", "y");
~~~

**Đáp án:** `a` là `int`; `b` là `long`; `c` là `double`; `d` là `int[]`; `e` là `List<String>`.

**Bài 2.** Phát hiện ba lỗi trong đoạn sau:

~~~java
// Mã cố ý sai, không chạy:
var x;
var y = null;
var z = {1, 2, 3};
~~~

**Đáp án:** `x` không có initializer; `y` khởi tạo bằng `null` đơn lẻ; `z` dùng array initializer trần không có kiểu đích. Có thể sửa:

~~~java
var x = 0;
String y = null;
var z = new int[]{1, 2, 3};
~~~

**Bài 3.** Vì sao hai dòng sau không tương đương về kiểu dữ liệu?

~~~java
var first = new ArrayList<>();
var second = new ArrayList<String>();
~~~

**Đáp án:** `first` suy luận `ArrayList<Object>`; `second` suy luận `ArrayList<String>`. Các lệnh sau khai báo không quyết định lại tham số kiểu cho `first`.

**Bài 4.** Sau `var number = 5;`, có thể viết `number = 7L;` không? Nếu không, sửa thế nào?

**Đáp án:** Không; `number` có kiểu `int`. Nếu cần lưu `long`, khởi tạo ban đầu bằng `var number = 5L;` hoặc dùng `long number = 5;`.

**Bài 5.** `final var names = new ArrayList<String>();` có cho phép `names.add("A");` không?

**Đáp án:** Có; `final` cấm gán lại `names`, không cấm thay đổi trạng thái `ArrayList` mà biến đang tham chiếu.

## 10. Checklist áp dụng trong dự án

- [ ] `var` nằm ở vị trí hợp lệ cho khai báo cục bộ.
- [ ] Có đúng **một** biến được khai báo và có initializer ngay trong câu lệnh.
- [ ] Initializer có kiểu xác định được: không phải `null` trần, lambda/method reference chưa có target type hoặc array initializer trần.
- [ ] Không tham chiếu lại chính biến đang được khai báo bên trong initializer.
- [ ] Kiểu suy luận đúng ý định, nhất là literal số, method return type, generic và diamond `<>`.
- [ ] Nếu cần abstraction `List`/`Map` hoặc kiểu nghiệp vụ rõ ràng, cân nhắc viết tên kiểu tường minh.
- [ ] Tên biến và biểu thức khởi tạo đủ sáng nghĩa để người khác đọc code không phải đoán kiểu.
- [ ] Nếu có `final`, hiểu rõ sự khác biệt giữa không thể **gán lại biến** và không thể **thay đổi đối tượng**.

## 11. Nguồn chuẩn để tra cứu

- [Oracle Java 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): vị trí sử dụng `var` và hướng dẫn về tính dễ đọc.
- [Java Language Specification 17 — `14.4` Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): các điều kiện biên dịch, initializer và suy luận kiểu.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): lý do thiết kế và phạm vi tính năng từ Java 10.
- [OpenJDK FAQ for JEP 286](https://cr.openjdk.org/~briangoetz/jep-286/lvti-faq.html): giải thích diamond, initializer, `final var` và giới hạn suy luận.

Những quy tắc cốt lõi này vẫn được dùng trong Java hiện đại: **biến có kiểu tĩnh, initializer quyết định kiểu, và `var` chỉ hợp lý khi giúp code rõ ràng hơn**.