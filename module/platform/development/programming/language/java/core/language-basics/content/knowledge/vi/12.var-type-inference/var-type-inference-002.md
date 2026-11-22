# `var` giữ nguyên kiểm tra kiểu tĩnh trong Java 17+

## 1. Mục tiêu: ít chữ hơn, không bớt an toàn kiểu

Trong Java, `var` cho phép **suy luận kiểu của biến cục bộ** (*local-variable type inference*) từ biểu thức khởi tạo. Tính năng xuất hiện từ Java 10 và tiếp tục được hỗ trợ trong Java 17+.

~~~java
var count = 10;        // Compiler suy luận int
var title = "Java";    // Compiler suy luận String
var price = 12.5;      // Compiler suy luận double

System.out.println(count + 1);  // 11
System.out.println(title);      // Java
System.out.println(price);      // 12.5
~~~

Điều cốt lõi: **`var` không làm Java trở thành ngôn ngữ có kiểu động (*dynamic typing*)**. Kiểu biến được xác định **khi biên dịch**, sau đó vẫn được compiler kiểm tra trong mọi phép gán và lời gọi method.

~~~java
var count = 10;
count = 20;         // Hợp lệ: int -> int
// count = "twenty"; // Lỗi biên dịch: String không chuyển thành int
~~~

Bạn có thể hình dung `var count = 10;` có tác dụng tương đương về kiểu và hành vi sau suy luận với `int count = 10;`, **không phải** một biến chứa “giá trị bất kỳ”.

### Điều cần đạt sau bài

- Hiểu `var` suy luận kiểu tĩnh, **không đổi kiểu khi gán lại**.
- Phân tích kiểu được suy ra từ literal, method, constructor và generic.
- Dự đoán lỗi compile do gán sai kiểu, thiếu initializer hoặc thiếu kiểu đích.
- Dùng `var` đúng chỗ mà không làm code khó đọc.

## 2. Kiểu tĩnh được chốt một lần từ initializer

Với `var name = expression;`, compiler xác định kiểu của `expression` ngay lúc khai báo. Các lần gán tiếp theo phải phù hợp với kiểu đã suy ra:

~~~java
var number = 7;              // int
number = 9;                  // Hợp lệ.
// number = 9L;              // Lỗi: long không tự thu hẹp về int.
var label = "Java";           // String
// label = 42;                // Lỗi: int không gán được cho String.
~~~

Độ rộng số được quyết định bởi literal hoặc phép toán trong initializer, không bởi các giá trị muốn gán về sau. Bài “Kiểu suy ra từ literal và các phép tính số” phân tích riêng numeric promotion và overflow.

## 3. Vì sao đây vẫn là static typing?

Compiler vẫn kiểm tra những yếu tố bình thường của Java:

1. **Tính hợp lệ của phép gán:** kiểu biểu thức bên phải phải tương thích với kiểu đã suy ra.
2. **Truy cập method/field:** chỉ các thành viên hợp lệ theo **kiểu tĩnh** mới được gọi.
3. **Toán tử:** các toán tử được kiểm tra theo kiểu toán hạng.
4. **Kiểu generic:** `List<String>` khác `List<Integer>`; compiler áp dụng kiểm tra kiểu với phần tử.
5. **Overload resolution:** chọn method theo kiểu tĩnh của đối số tại compile time.

~~~java
var text = "Java"; // String
System.out.println(text.length()); // 4
// System.out.println(text.nonExistingMethod()); // Lỗi compile
// text = 123; // Lỗi compile
~~~

Bạn sẽ thấy cùng mức kiểm tra kiểu nếu viết:

~~~java
String text = "Java";
~~~

**`var` không phải `Object`**. Với `var text = "Java";`, biến có kiểu `String`, nên `text.length()` biên dịch được; với `Object text = "Java";`, lời gọi `text.length()` không hợp lệ nếu không ép kiểu vì `Object` không khai báo `length()`.

**`var` cũng không phải JavaScript `var`**: hai ngôn ngữ dùng cùng chuỗi ký tự cho những cơ chế khác nhau.

## 4. Hai ví dụ cùng chữ `var`, nhưng suy ra hai kiểu khác nhau

~~~java
var primitive = 42;                  // int
var wrapped = Integer.valueOf(42);  // Integer

System.out.println(primitive + 1); // 43
System.out.println(wrapped + 1);   // 43: unboxing rồi tính
~~~

Ở ví dụ `wrapped`, compiler biết biến có kiểu `Integer`; ở ví dụ `primitive`, compiler biết biến có kiểu `int`.

Điều này ảnh hưởng tới khả năng giữ `null`:

~~~java
var count = 5;             // int
// count = null;            // Lỗi compile: primitive int không nhận null

var optionalCount = Integer.valueOf(5); // Integer
optionalCount = null;          // Biên dịch được, vì Integer là reference type
~~~

Nhưng khi auto-unboxing một wrapper null, bạn vẫn gặp `NullPointerException` như với khai báo `Integer` thông thường:

~~~java
if (optionalCount != null) {
    int safe = optionalCount;
    System.out.println(safe);
}
~~~

**Suy luận kiểu không tự bổ sung kiểm tra null runtime.** `var` chỉ giảm lặp tên kiểu tại chỗ khai báo, không thay đổi hợp đồng nullable của kiểu đã suy ra.

## 5. Các lỗi biên dịch điển hình chứng minh kiểu vẫn cố định

Những dòng có comment bên dưới là **ví dụ sai có chủ đích**, không đưa vào chương trình chạy ở phần sau:

~~~java
var score = 10;
// score = "ten";             // String không gán được vào int

var city = "Hà Nội";
// city = 42;                 // int không gán được vào String

var names = new java.util.ArrayList<String>();
names.add("Lan");
// names.add(100);            // int không phù hợp với List<String>

var answer = 2 + 3;         // int
// answer.notARealMethod();   // int không có method như vậy
~~~

Không có “lần gán thứ hai khiến biến đổi kiểu”. Compiler **không suy luận lại** kiểu của `score` hoặc `city` ở các câu lệnh sau.

Một ngoại lệ dễ gây hiểu nhầm về giá trị nhưng **không phải đổi kiểu**:

~~~java
var number = 3;   // int
number = (int) 3.9; // Hợp lệ: cast double -> int, giá trị thành 3
~~~

Ở đây kiểu `number` vẫn là **int**. Dùng cast có thể làm mất dữ liệu; tính đúng nghiệp vụ vẫn phải kiểm tra riêng.

## 6. Những giới hạn kiểu tĩnh vẫn áp dụng khi dùng `var`

Compiler chỉ có thể suy luận khi initializer **có kiểu hợp lệ**. Không thể viết `var item;`, `var item = null;`, `var values = {1, 2};` hoặc gán trực tiếp lambda không có kiểu đích. Có thể sử dụng kiểu tường minh hoặc tạo biểu thức đủ kiểu:

~~~java
String nullable = null;
var typedNull = (String) null; // Kiểu String dù giá trị null
var values = new int[] {1, 2}; // Kiểu int[]
java.util.function.IntUnaryOperator f = x -> x + 1;
var f2 = (java.util.function.IntUnaryOperator) (x -> x + 1);
~~~

Trong cả `f` và `f2`, **functional interface** cung cấp kiểu đích cho lambda; `var` không tự phát minh kiểu functional interface. Quy tắc suy luận từ `null`, mảng và vị trí được phép viết `var` có bài chuyên biệt trong chương; ở đây chúng là **bằng chứng rằng static typing không bị bỏ qua**.

### Kiểu generic và abstraction vẫn được giữ

~~~java
var strings = new java.util.ArrayList<String>();
strings.add("An");
// strings.add(5); // Lỗi biên dịch: cần String

var bag = new java.util.ArrayList<>(); // ArrayList<Object>
bag.add("An");
bag.add(5);

java.util.List<String> names = new java.util.ArrayList<>();
~~~

Không có kiểu đích `String` cho diamond trống của `bag`, nên biến suy ra `ArrayList<Object>` và `add(5)` hợp lệ (boxing thành `Integer`). Đặt `List<String>` ở vế trái khi mục tiêu là dùng **API của interface**, thay vì cho `var` suy ra lớp triển khai cụ thể. Sau khai báo, generic và tập method hợp lệ vẫn được compiler kiểm tra; `var` **không** bỏ qua `UnsupportedOperationException` nếu gọi thao tác không hỗ trợ trên danh sách từ `List.of` lúc chạy.

## 7. Overload được chọn theo kiểu tĩnh, không theo nội dung lúc chạy

Giả sử có hai overload:

~~~java
static void describe(Object object) {
    System.out.println("Object");
}

static void describe(String text) {
    System.out.println("String");
}
~~~

Trong `main`:

~~~java
var text = "Java";           // Kiểu String
var object = (Object) "Java"; // Kiểu Object

describe(text);   // String
describe(object); // Object
~~~

Cả hai biến **có thể cùng tham chiếu tới một object String**, nhưng overload được lựa chọn **khi biên dịch** dựa trên kiểu tĩnh của biểu thức:

- `text` kiểu `String` → chọn `describe(String)`.
- `object` kiểu `Object` → chọn `describe(Object)`.

**`var` không hỗ trợ tự đổi overload theo runtime.** Đây là dấu hiệu trực quan rằng suy luận kiểu trong Java vẫn thuộc mô hình static typing.



## 8. Chương trình Java 17 chạy độc lập

Tạo file đúng tên **`VarStaticTypingDemo.java`**:

~~~java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.function.BinaryOperator;
import java.util.function.IntUnaryOperator;

public final class VarStaticTypingDemo {
    private VarStaticTypingDemo() {}

    record Person(String name, int age) {}

    static int sum(int a, int b) {
        return a + b;
    }

    static void describe(Object object) {
        System.out.println("overload=Object");
    }

    static void describe(String text) {
        System.out.println("overload=String");
    }

    public static void main(String[] args) throws Exception {
        var number = 10;         // int
        number = 12;
        var longNumber = 10L;    // long
        var ratio = 2.5;         // double
        var enabled = true;      // boolean
        var title = "Java";      // String

        System.out.println("int=" + number);
        System.out.println("long=" + longNumber);
        System.out.println("double=" + ratio);
        System.out.println("boolean=" + enabled);
        System.out.println("text length=" + title.length());

        var answer = sum(2, 3); // int từ kiểu trả về
        System.out.println("sum=" + answer);

        var names = new ArrayList<String>();
        names.add("Lan");
        names.add("An");
        System.out.println("names=" + names);
        System.out.println("first name=" + names.get(0));

        var words = List.of("A", "B");
        for (var word : words) {
            System.out.println("word=" + word);
        }

        var bag = new ArrayList<>();
        bag.add("text");
        bag.add(123);
        System.out.println("Object bag=" + bag);

        var flags = new boolean[] {true, false};
        System.out.println("flags length=" + flags.length);

        var person = new Person("Mai", 20);
        System.out.println("person=" + person.name() + ":" + person.age());

        var asString = "Java";
        var asObject = (Object) "Java";
        describe(asString);
        describe(asObject);

        var optional = (String) null;
        System.out.println("typed null=" + (optional == null));

        var increment = (IntUnaryOperator) (x -> x + 1);
        System.out.println("lambda=" + increment.applyAsInt(4));

        BinaryOperator<String> merge =
                (var left, var right) -> left + "-" + right;
        System.out.println("lambda parameters=" + merge.apply("A", "B"));

        for (var i = 0; i < 2; i++) {
            System.out.println("for i=" + i);
        }

        try (var reader = new StringReader("X")) {
            System.out.println("resource char=" + (char) reader.read());
        }

        var original = new ArrayList<String>();
        var alias = original;
        alias.add("shared");
        System.out.println("same reference=" + (original == alias));
        System.out.println("original=" + original);
    }
}
~~~

**Biên dịch và chạy với JDK 17+**. Mở terminal trong thư mục chứa file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 VarStaticTypingDemo.java
java -cp . VarStaticTypingDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\VarStaticTypingDemo.java
java -cp . VarStaticTypingDemo
~~~

**Exact expected output:**

~~~text
int=12
long=10
double=2.5
boolean=true
text length=4
sum=5
names=[Lan, An]
first name=Lan
word=A
word=B
Object bag=[text, 123]
flags length=2
person=Mai:20
overload=String
overload=Object
typed null=true
lambda=5
lambda parameters=A-B
for i=0
for i=1
resource char=X
same reference=true
original=[shared]
~~~

**Giải thích kết quả dễ nhầm:**

- `number` suy ra kiểu `int`; gán `12` được phép nhưng không thể gán String.
- `answer` suy ra `int` từ method `sum`.
- `names` có kiểu `ArrayList<String>`, nên chỉ cho thêm giá trị String theo generic.
- `bag` được tạo với diamond trống và không có target type ngoài `var`, vì vậy suy ra `ArrayList<Object>`; thêm cả String và Integer là hợp lệ.
- `asString` và `asObject` dẫn tới overload khác nhau **theo kiểu tĩnh**, không do object String thay đổi.
- `optional` vẫn có kiểu `String` dù giá trị hiện tại là null.
- `increment` có target type qua cast `IntUnaryOperator`; `merge` có target type `BinaryOperator<String>`.
- `for` và `try-with-resources` sử dụng `var` trong vị trí hợp lệ.
- `alias = original` giữ cùng tham chiếu, không sao chép ArrayList.

**Không có** các dòng compile error cố ý trong chương trình này; các ví dụ code không hợp lệ ở phần trước đều được comment hoặc đặt riêng. Ví dụ dùng các API tiêu chuẩn của JDK 17 và không cần thư viện ngoài.



## 9. Bài tập và đáp án

### Bài A — suy luận literal

~~~java
var x = 1;
var y = 1L;
var z = 1.0f;
~~~

**Đáp án:** `x` là `int`, `y` là `long`, `z` là `float`.

### Bài B — gán lại sai kiểu

~~~java
var label = "A";
label = "B";
// label = 10;
~~~

**Đáp án:** gán `"B"` hợp lệ; gán `10` lỗi biên dịch vì `label` có kiểu `String` đã chốt.

### Bài C — generic

~~~java
var scores = new java.util.ArrayList<Integer>();
scores.add(1);
// scores.add("two");
~~~

**Đáp án:** `scores` có kiểu `ArrayList<Integer>`, nên thêm `"two"` không hợp lệ. `var` không bỏ kiểm tra generic.

### Bài D — overload

~~~java
static void show(Object x) { System.out.println("Object"); }
static void show(String x) { System.out.println("String"); }

// Trong main:
var a = "Hi";
var b = (Object) "Hi";
show(a);
show(b);
~~~

**Đáp án:**

~~~text
String
Object
~~~

### Bài E — null

~~~java
// var a = null;
String b = null;
var c = (String) null;
~~~

**Đáp án:** khai báo `a` sai, vì compiler không suy ra kiểu từ null literal. `b` và `c` hợp lệ; `c` có kiểu `String` dù giữ giá trị null.

### Bài F — chọn `var` hay kiểu tường minh?

Bạn muốn công khai ý định làm việc qua giao diện `List<String>` thay vì các thao tác riêng của `ArrayList`:

~~~java
var names = new java.util.ArrayList<String>();
~~~

**Đáp án:** có thể viết:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
~~~

Cách này thể hiện rõ **hợp đồng phụ thuộc vào `List`**. `var` vẫn đúng về kiểu; vấn đề ở đây là tính dễ đọc và mức abstraction mong muốn, không phải Java kiểm tra kiểu yếu hơn.

## 10. Checklist và kết luận

- [ ] Với `var`, phép gán sai kiểu vẫn bị từ chối tại compile time.
- [ ] Method access, generic và overload vẫn dựa trên kiểu tĩnh suy ra.
- [ ] Phân biệt `int` với `Integer` và kiểm tra null trước khi unbox.
- [ ] Phân biệt `var text = "Java";` với `Object text = "Java";`.
- [ ] Hiểu vì sao biến cùng trỏ một `String` có thể chọn hai overload khác nhau khi kiểu tĩnh khác nhau.
- [ ] Có thể chạy `VarStaticTypingDemo.java` và giải thích các kết quả.

**Kết luận:** `var` rút gọn khai báo biến cục bộ, nhưng kiểm tra kiểu tĩnh, lựa chọn overload và kiểm tra generic vẫn hoạt động như với khai báo tường minh.