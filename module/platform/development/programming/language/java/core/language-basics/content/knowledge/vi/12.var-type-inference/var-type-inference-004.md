# Vì sao `var` cần giá trị khởi tạo — Java 17+

`var` được Java hỗ trợ cho **suy luận kiểu biến cục bộ** (*local variable type inference*). Khi viết:

~~~java
var quantity = 10;
~~~

compiler đọc biểu thức khởi tạo `10`, xác định biểu thức đó có kiểu `int` và khai báo `quantity` như một biến cục bộ kiểu **`int`**. Sau đó, biến vẫn chịu kiểm tra kiểu tĩnh như bình thường. `var` **không** phải kiểu dữ liệu mới, cũng không làm Java trở thành ngôn ngữ có kiểu động.

**Tại sao cần giá trị khởi tạo?** Vì trong câu lệnh khai báo biến cục bộ dạng `var`, compiler không thấy kiểu được viết ở bên trái. Nếu không có **biểu thức khởi tạo có kiểu xác định**, nó không có căn cứ để suy luận kiểu của biến ngay lúc khai báo.

~~~java
int number;       // Hop le: kieu int da duoc viet ro.
// var number;     // LOI bien dich: khong co initializer de suy kieu.

var age = 18;     // Hop le: suy ra int.
// age = "18";    // LOI bien dich: String khong phai int.
~~~

**Phạm vi bài:** Quy tắc “phải khởi tạo” ở đây nói về **khai báo biến cục bộ thông thường** bằng `var`. Java còn cho phép `var` ở các ngữ cảnh có **nguồn suy kiểu khác**, chẳng hạn biến phần tử trong enhanced `for` và tham số lambda; các trường hợp đó được giải thích riêng ở phần 6.

## 1. So sánh khai báo tường minh và khai báo bằng `var`

| Khai báo | Hợp lệ? | Compiler biết kiểu từ đâu? |
| --- | --- | --- |
| `String text;` | Có | Kiểu `String` được viết trực tiếp |
| `String text = null;` | Có | Kiểu `String` đã được chỉ rõ |
| `var text = "Java";` | Có | Initializer `"Java"` có kiểu `String` |
| `var count = 7;` | Có | Initializer `7` có kiểu `int` |
| `var amount = 7L;` | Có | Initializer `7L` có kiểu `long` |
| `var item;` | **Không** | Thiếu biểu thức để suy kiểu |
| `var item = null;` | **Không** | Literal `null` không cung cấp kiểu tham chiếu cụ thể |
| `var item = (String) null;` | Có | Cast khiến biểu thức có kiểu `String` |
| `var list = new java.util.ArrayList<String>();` | Có | Biểu thức tạo đối tượng có kiểu `ArrayList<String>` |

Điểm dễ nhầm là **biến khai báo tường minh** vẫn có thể chưa được gán khi khai báo, nhưng **biến khai báo bằng `var`** không thể bỏ initializer trong trường hợp khai báo local thông thường.

## 2. Suy luận kiểu diễn ra **lúc biên dịch**, không phải lúc chạy

Quy trình cơ bản:

~~~text
var count = Integer.parseInt("42");
          |
          v
Compiler kiem tra bieu thuc:
  Integer.parseInt(...) tra ve int
          |
          v
Kieu tinh cua count la int
          |
          v
Kiem tra cac lenh su dung count
  count = 50;      // Hop le
  count = "fifty"; // Sai kieu
~~~

Compiler dựa vào **kiểu tĩnh của biểu thức**, không dựa vào giá trị sau khi chương trình đã chạy. Ví dụ một phương thức được khai báo trả về `String` thì lời gọi của nó là biểu thức kiểu `String`, **kể cả khi một lần gọi cụ thể trả về `null`**.

~~~java
static String findTitle(boolean exists) {
    return exists ? "Guide" : null;
}

// Trong mot phuong thuc:
var title = findTitle(false); // Hop le: suy ra String.
System.out.println(title == null); // true.
~~~

Điều này khác hẳn `var title = null;`: literal `null` đơn lẻ không có kiểu cụ thể để dùng làm kiểu biến. Gán cast `(String) null` lại hợp lệ vì lúc đó biểu thức đã có kiểu `String`.

## 3. Ví dụ Java 17+ chạy độc lập

Tạo file UTF-8 tên **`VarNeedsInitializerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class VarNeedsInitializerDemo {
    static String findTitle(boolean found) {
        return found ? "Guide" : null;
    }

    static int readCount() {
        return 3;
    }

    public static void main(String[] args) {
        var count = readCount();
        var price = 2.5;
        var title = "Java";

        System.out.println("count=" + count);
        System.out.println("price=" + price);
        title = title + " 17";
        System.out.println("title=" + title);

        var numbers = List.of(2, 4, 6);
        var sum = 0;
        for (var number : numbers) {
            sum += number;
        }
        System.out.println("sum=" + sum);

        var indices = new StringBuilder();
        for (var i = 0; i < 3; i++) {
            indices.append(i);
        }
        System.out.println("indices=" + indices);

        var typedNull = (String) null;
        System.out.println("typedNull=" + (typedNull == null));
        typedNull = "ready";
        System.out.println("typedNullAfterSet=" + typedNull);

        var fromMethod = findTitle(false);
        System.out.println("methodReturnedNull=" + (fromMethod == null));
        fromMethod = findTitle(true);
        System.out.println("methodReturnedText=" + fromMethod);

        String declaredLater;
        declaredLater = "assigned";
        System.out.println("explicitTypeLater=" + declaredLater);

        var parsed = Integer.parseInt("42");
        var boxed = Integer.valueOf(42);
        System.out.println("parsed=" + parsed);
        System.out.println("boxedType="
                + boxed.getClass().getSimpleName());

        var names = new ArrayList<String>();
        names.add("Ada");
        System.out.println("names=" + names);

        var mixed = new ArrayList<>();
        mixed.add("text");
        mixed.add(1);
        System.out.println("mixed=" + mixed);

        var data = new int[]{1, 2, 3};
        System.out.println("arrayLength=" + data.length);

        final var enabled = true;
        System.out.println("enabled=" + enabled);
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) trong thư mục chứa file, dùng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 VarNeedsInitializerDemo.java
java VarNeedsInitializerDemo
~~~

**Expected output chính xác của `java VarNeedsInitializerDemo`:**

~~~text
count=3
price=2.5
title=Java 17
sum=12
indices=012
typedNull=true
typedNullAfterSet=ready
methodReturnedNull=true
methodReturnedText=Guide
explicitTypeLater=assigned
parsed=42
boxedType=Integer
names=[Ada]
mixed=[text, 1]
arrayLength=3
enabled=true
~~~

Đầu ra của `java -version` và `javac -version` phụ thuộc môi trường, không được tính trong khối expected output.

### Giải thích từng trường hợp

- `var count = readCount();` suy ra `int` từ **khai báo kiểu trả về** của `readCount()`. Compiler không cần thực thi phương thức.
- `var price = 2.5;` suy ra `double`; `var title = "Java";` suy ra `String`. Gán nối thêm `" 17"` vẫn hợp lệ vì kiểu biến là String.
- `var numbers = List.of(2, 4, 6);` suy ra `List<Integer>`; trong enhanced `for`, biến `number` nhận kiểu phần tử là `Integer`, rồi được unbox khi cộng vào `int sum`.
- `for (var i = 0; i < 3; i++)` có initializer `0`, nên `i` là `int`; các giá trị lặp là 0, 1, 2.
- `var typedNull = (String) null;` hợp lệ: biểu thức có kiểu `String` mặc dù **giá trị** là null. `var fromMethod = findTitle(false);` cũng hợp lệ vì lời gọi có kiểu `String`.
- `String declaredLater;` hợp lệ vì kiểu khai báo đã rõ. Nếu đọc `declaredLater` trước khi gán, compiler vẫn báo lỗi *variable might not have been initialized*; **có kiểu** không đồng nghĩa **đã có giá trị**.
- `parsed` suy ra `int` từ `parseInt`; `boxed` suy ra `Integer` từ `valueOf`. Java không suy ra wrapper từ primitive chỉ vì hai kết quả đều hiển thị là 42.
- `names` suy ra `ArrayList<String>`. Với `var mixed = new ArrayList<>();` không có kiểu đích generic tường minh nên trường hợp này diamond suy ra `Object`, tạo biến `ArrayList<Object>`.
- `var data = new int[]{1, 2, 3};` có initializer mảng mang kiểu `int[]`. `final var enabled = true;` có kiểu `boolean` và không cho phép gán lại biến.

## 4. Tại sao `var x = null` không hợp lệ, nhưng null có thể là kết quả?

Phân biệt **kiểu của biểu thức** và **giá trị của biểu thức**:

~~~java
// var a = null; // Sai: null literal khong co kieu cu the.

var b = (String) null; // Dung: b co kieu String.
String c = null;       // Dung: kieu viet ro.
~~~

Ví dụ phương thức:

~~~java
static String loadName() {
    return null;
}

// Trong mot phuong thuc:
var name = loadName(); // Dung: suy ra String tu chu ky loadName.
~~~

Khi chạy, `name` vẫn mang `null`; gọi `name.length()` sẽ ném `NullPointerException`. **Dùng `var` không bỏ qua kiểm tra null** và cũng không tạo đối tượng String thay cho null.

Một vài biểu thức khác không có kiểu đích rõ ràng cũng không hợp lệ ngay sau `var`:

~~~java
// var f = x -> x + 1;     // Lambda can target functional interface.
// var maker = String::new; // Method reference can target type.
// var a = {1, 2, 3};      // Dạng initializer mang rut gon can target array.
~~~

Cách viết rõ kiểu hợp lệ:

~~~java
java.util.function.IntUnaryOperator f = x -> x + 1;
java.util.function.Supplier<String> maker = String::new;
var a = new int[]{1, 2, 3};
~~~

Với `var`, compiler không nhận được kiểu đích viết bên trái để dùng cho các biểu thức *poly expression* như lambda hoặc method reference. Dùng kiểu tường minh cho functional interface thường rõ ý hơn.

## 5. Không thể suy kiểu từ phép gán viết **sau** khai báo

~~~java
// var points;
// points = 10;
~~~

Đoạn trên không hợp lệ. Compiler phải xác định kiểu **ở vị trí khai báo** để kiểm tra phần còn lại của chương trình. Nó không “đọc ngược” phép gán phía sau để suy ra kiểu cho khai báo thiếu initializer.

Nếu muốn gán sau, phải cung cấp kiểu:

~~~java
int points;
points = 10;
System.out.println(points);
~~~

Và còn phải thỏa *definite assignment*: một biến cục bộ có kiểu tường minh nhưng chưa được gán không thể bị đọc tùy ý.

Cũng không thể nhờ giá trị thay đổi về sau để “nâng kiểu”:

~~~java
var points = 10;  // int.
points = 20;      // Hop le.
// points = 20L;  // Loi: long khong tu dong thu hep thanh int.
~~~

## 6. Ngoại lệ về **nguồn thông tin kiểu**: enhanced `for` và lambda

Phát biểu “`var` cần initializer” thường được dùng cho khai báo biến cục bộ đơn giản (`var name = expression;`). Tuy nhiên Java còn cho phép `var` ở các vị trí **không có phép gán khởi tạo tường minh ngay tại khai báo** vì compiler lấy kiểu từ ngữ cảnh.

### Biến phần tử trong enhanced `for`

~~~java
int[] values = {2, 4, 6};
for (var value : values) {
    System.out.println(value);
}
~~~

`value` được suy kiểu `int` từ **kiểu phần tử của mảng `int[]`**. Dấu `:` của enhanced `for` cung cấp nguồn suy kiểu, nên không cần viết `var value = ...`.

### Tham số lambda trong Java 17

~~~java
java.util.function.BinaryOperator<Integer> add =
        (var left, var right) -> left + right;
~~~

Hai tham số được suy là `Integer` nhờ **target type** `BinaryOperator<Integer>`. Đây là dạng `var` cho lambda, không phải khai báo biến cục bộ thông thường và không có initializer đi kèm từng tham số.

Khi dùng `var` trong danh sách tham số lambda, **tất cả tham số phải dùng `var`**; không trộn `var` với dạng viết kiểu tường minh hoặc dạng bỏ kiểu trong cùng danh sách.

### Các trường hợp khác

`var` được dùng trong initializer của `for` cổ điển, ví dụ `for (var i = 0; ... )`, và trong khai báo resource của `try-with-resources` như `try (var reader = new StringReader("hi")) { ... }`. Các trường hợp này **vẫn có biểu thức khởi tạo** khi dùng cách khai báo bằng `var`.

**Điểm chung:** compiler phải có **nguồn thông tin kiểu tại chỗ**. Nguồn đó là initializer đối với local variable thông thường, kiểu phần tử với enhanced `for`, hoặc target type đối với lambda.

## 7. Những lỗi biên dịch dễ gặp và cách sửa

| Ví dụ không hợp lệ | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `var x;` | Không có initializer để suy kiểu | `int x;` hoặc `var x = 0;` |
| `var x = null;` | Null literal không xác định kiểu cụ thể | `String x = null;` hoặc `var x = (String) null;` |
| `var x = {1, 2};` | Array initializer ngắn không có kiểu đích | `var x = new int[]{1, 2};` |
| `var f = x -> x + 1;` | Lambda cần target functional interface | `IntUnaryOperator f = x -> x + 1;` |
| `var x = x;` | Không có giá trị hợp lệ để dùng trong chính initializer | Khởi tạo từ biểu thức độc lập, ví dụ `var x = 1;` |
| `var a = 1, b = 2;` | Không được khai báo nhiều biến bằng một local `var` declarator | Tách `var a = 1; var b = 2;` |
| `var x = 1; x = "one";` | `x` đã được suy ra `int` | Chọn kiểu khác ngay từ khai báo nếu cần |

Ngoài ra, `var` **không được dùng làm kiểu trả về phương thức, field của lớp hoặc kiểu tham số phương thức thường**. Đây là giới hạn vị trí cú pháp, độc lập với việc có biểu thức khởi tạo hay không.

## 8. Khi nào nên viết `var`, khi nào nên viết kiểu tường minh?

**Ưu tiên `var`** khi biểu thức khởi tạo làm kiểu đủ rõ:

~~~java
var names = new java.util.ArrayList<String>();
var length = "Java".length();
~~~

**Ưu tiên kiểu tường minh** khi cần để trống biến đến lúc có dữ liệu, cần chủ động chọn interface/superclass làm kiểu biến, hoặc muốn có target type giúp suy generic:

~~~java
String name;
name = readName();

java.util.List<String> names = new java.util.ArrayList<>();
~~~

Với `var list = new java.util.ArrayList<>();`, diamond `<>` không nhận được ràng buộc phần tử từ tên biến bên trái, nên trường hợp này suy ra `ArrayList<Object>`. Ghi `ArrayList<String>` ở initializer hoặc dùng `List<String>` bên trái nếu muốn ràng buộc phần tử String.

`var` là công cụ giảm lặp tên kiểu, **không nên dùng để che giấu kiểu khó hiểu**. Tên biến, phương thức khởi tạo và kiểu dữ liệu phải cùng giúp người đọc suy luận chính xác.

## 9. Bài tập tự kiểm tra

1. **Thiếu initializer:** Vì sao `var score;` không biên dịch nhưng `int score;` hợp lệ?  
   *Đáp án:* `int` cung cấp kiểu tĩnh; `var` cần initializer để suy kiểu của local variable thông thường.
2. **Null:** `var text = null;` khác `var text = (String) null;` thế nào?  
   *Đáp án:* Câu đầu không có kiểu cụ thể để suy; câu sau suy `String` từ cast, dù giá trị là null.
3. **Phương thức trả null:** `static String f() { return null; }` thì `var x = f();` có hợp lệ không?  
   *Đáp án:* Có. Kiểu tĩnh của biểu thức gọi `f()` là `String`.
4. **Không dùng giá trị về sau:** `var x; x = 5;` có hợp lệ không?  
   *Đáp án:* Không; suy kiểu phải xảy ra tại khai báo, không tìm kiểu từ phép gán phía sau.
5. **Hai literal:** `var n = 10;` và `var n = 10L;` lần lượt có kiểu gì?  
   *Đáp án:* `int` và `long`.
6. **Enhanced for:** `for (var c : "ABC".toCharArray())` suy ra `c` kiểu gì dù không có `= initializer`?  
   *Đáp án:* `char` từ kiểu phần tử của mảng.
7. **Lambda:** Vì sao `BinaryOperator<Integer> add = (var a, var b) -> a + b;` hợp lệ?  
   *Đáp án:* Target type `BinaryOperator<Integer>` cung cấp kiểu tham số.

## Checklist

- [ ] `var` dùng để **suy luận kiểu tĩnh**, không phải kiểu động.
- [ ] Với local variable khai báo thông thường, `var` **cần biểu thức khởi tạo** cùng câu lệnh.
- [ ] `var x = null` không hợp lệ; `var x = (String) null` hoặc lời gọi phương thức trả `String` có thể hợp lệ.
- [ ] Kiểu được suy từ **kiểu biểu thức**, không từ giá trị runtime hoặc phép gán phía sau.
- [ ] Không dùng array initializer dạng ngắn, lambda hay method reference trần nếu không có target type.
- [ ] Enhanced `for` suy kiểu từ phần tử, lambda suy kiểu tham số từ target functional interface.
- [ ] Viết kiểu tường minh nếu muốn khai báo trước rồi gán sau, hoặc cần kiểm soát interface/generic target type.

**Kết luận:** `var` cần biểu thức khởi tạo ở khai báo biến cục bộ thông thường vì compiler **phải suy ra kiểu ngay tại nơi khai báo**. Khi một ngữ cảnh khác cung cấp thông tin kiểu (enhanced `for`, lambda), Java có quy tắc riêng; điều không thay đổi là **`var` luôn tham gia hệ thống kiểu tĩnh**, không chờ dữ liệu runtime để đoán kiểu.
