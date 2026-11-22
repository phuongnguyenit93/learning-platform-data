# Mục đích và điều kiện nạp chồng phương thức trong Java

## 1. Nạp chồng phương thức là gì?

**Nạp chồng phương thức** (*method overloading*) là việc khai báo **nhiều phương thức cùng tên nhưng khác danh sách tham số**, để một tên hành vi có thể đáp ứng nhiều cách gọi hợp lý. Ví dụ, một công cụ xuất thông báo có thể hỗ trợ gửi một chuỗi đơn, gửi chuỗi kèm mức độ ưu tiên, hoặc gửi nhiều chuỗi.

```java
class MessagePrinter {
    void print(String message) {
        System.out.println(message);
    }

    void print(String message, int priority) {
        System.out.println("P" + priority + ": " + message);
    }

    void print(int value) {
        System.out.println("number=" + value);
    }
}
```

Các phương thức `print` trên cùng tên nhưng nhận:

- Một đối số kiểu `String`.
- Hai đối số theo thứ tự `String, int`.
- Một đối số kiểu `int`.

Đó là **ba overload hợp lệ**. Trình biên dịch Java căn cứ vào các phương thức có thể truy cập và **kiểu của các biểu thức đối số tại thời điểm biên dịch** để chọn khai báo thích hợp, theo quy tắc phân giải overload.

Nạp chồng có hai mục đích chính:

1. **Giữ một tên hành vi nhất quán:** `print` vẫn có nghĩa là “xuất thông tin”; tên method không phải thay thành `printText`, `printTextWithPriority`, `printNumber` chỉ vì tham số khác nhau.
2. **Tăng tính tiện dụng và khả năng mở rộng API:** có thể bổ sung biến thể nhận tham số khác, hoặc cung cấp giá trị mặc định bằng một overload gọi overload khác.

Đổi lại, nếu viết quá nhiều overload có kiểu tham số gần giống, lời gọi có thể **khó đoán hoặc mơ hồ**. Nạp chồng chỉ có ích khi các phương thức thật sự biểu đạt cùng một nhóm hành vi.

> **Nguyên tắc cốt lõi:** hai phương thức cùng tên phải khác **danh sách kiểu tham số** theo các quy tắc của ngôn ngữ. Chỉ thay kiểu trả về, tên tham số, modifier hoặc danh sách `throws` **không tạo được overload khác biệt hợp lệ**.

## 2. Ví dụ Java 17+ chạy hoàn chỉnh: dùng một tên theo ba cách

Tạo tệp **`OverloadingBasicsDemo.java`**:

```java
class Formatter {
    String format(int quantity) {
        return "quantity=" + quantity;
    }

    String format(double price) {
        return "price=" + price;
    }

    String format(String product, int quantity) {
        return product + " x " + quantity;
    }

    String format(String product) {
        return format(product, 1);
    }
}

public class OverloadingBasicsDemo {
    public static void main(String[] args) {
        Formatter formatter = new Formatter();

        System.out.println(formatter.format(3));
        System.out.println(formatter.format(2.5));
        System.out.println(formatter.format("Pen", 4));
        System.out.println(formatter.format("Book"));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac OverloadingBasicsDemo.java
java OverloadingBasicsDemo
```

Kết quả chính xác:

```text
quantity=3
price=2.5
Pen x 4
Book x 1
```

Cách chọn từng lời gọi:

| Lời gọi | Phương thức được chọn | Lý do |
| --- | --- | --- |
| `format(3)` | `format(int)` | Literal `3` có kiểu `int`, khớp trực tiếp. |
| `format(2.5)` | `format(double)` | Literal `2.5` có kiểu `double`. |
| `format("Pen", 4)` | `format(String, int)` | Hai đối số có kiểu và thứ tự phù hợp. |
| `format("Book")` | `format(String)` | Một đối số `String`; overload này gọi lại `format(product, 1)`. |

`format(String)` là ví dụ về **overload tiện ích (convenience overload)**: nó quy định số lượng mặc định `1` rồi chuyển sang bản triển khai nhận hai tham số. Cách này tránh viết lại phép ghép chuỗi ở nhiều nơi, đồng thời giúp API dễ gọi hơn.

Chú ý lớp `Formatter` ở đây không có `public`; lớp `public` duy nhất là `OverloadingBasicsDemo` nên phải lưu tệp đúng tên `OverloadingBasicsDemo.java`.

## 3. Điều kiện để hai phương thức tạo thành overload

Trong một lớp, các method cùng tên phải có **chữ ký khác nhau** theo quy tắc Java. Khi xét một overload thông dụng không generic, hãy kiểm tra **số lượng, kiểu, hoặc thứ tự kiểu** của các tham số.

### 3.1. Khác số lượng tham số

```java
class Calculator {
    int sum(int a, int b) {
        return a + b;
    }

    int sum(int a, int b, int c) {
        return a + b + c;
    }
}
```

`sum(2, 3)` và `sum(2, 3, 4)` chọn hai overload khác nhau do số tham số khác. Hai method đều trả `int` nhưng **kiểu trả về giống nhau không phải điều kiện bắt buộc** của overload.

### 3.2. Khác kiểu tham số

```java
class InputReader {
    String read(int index) {
        return "index=" + index;
    }

    String read(String key) {
        return "key=" + key;
    }
}
```

Cùng nhận một đối số nhưng `read(3)` chọn `read(int)` còn `read("name")` chọn `read(String)`. Đây là overload hợp lệ vì tham số có kiểu khác.

### 3.3. Khác thứ tự kiểu tham số

```java
class RequestBuilder {
    String make(String path, int retries) {
        return path + ":" + retries;
    }

    String make(int retries, String path) {
        return retries + ":" + path;
    }
}
```

`make("/users", 3)` và `make(3, "/users")` khác thứ tự kiểu (`String, int` so với `int, String`), vì vậy có thể cùng tồn tại.

Không nên lạm dụng kiểu overload này nếu hai lời gọi biểu thị ý nghĩa tương tự mà dễ đảo nhầm vị trí. Một API rõ ràng đôi khi cần tên method khác hoặc object tham số có tên field cụ thể.

### 3.4. Chữ ký method không gồm kiểu trả về

Ví dụ **cố ý sai, không biên dịch**:

```java
// class WrongReturnType {
//     int parse(String text) {
//         return Integer.parseInt(text);
//     }
//
//     long parse(String text) {
//         return Long.parseLong(text);
//     }
// }
```

Hai method đều tên `parse` và tham số `(String)`. Thay `int` bằng `long` ở kiểu trả về **không làm chữ ký tham số khác**; compiler báo khai báo trùng. Ngay cả khi người gọi viết `long result = parse("12");`, Java cũng không chọn overload chỉ dựa trên biến nhận kết quả.

Cách sửa: dùng tên có ý nghĩa khác (`parseInt` và `parseLong`), hoặc thiết kế các tham số thể hiện rõ đích chuyển đổi nếu đó là API cần thiết.

### 3.5. Thay tên tham số, modifier hoặc `throws` cũng không đủ

Ví dụ sai về **tên tham số**:

```java
// class WrongNames {
//     void save(int id) { }
//     void save(int key) { } // Lỗi: vẫn là save(int).
// }
```

Ví dụ sai về **`throws`**:

```java
// class WrongThrows {
//     void load(String path) { }
//     void load(String path) throws java.io.IOException { }
//     // Lỗi khai báo trùng load(String).
// }
```

Ví dụ sai về **`static`**:

```java
// class WrongStatic {
//     void check(int value) { }
//     static void check(int value) { }
//     // Lỗi khai báo trùng check(int).
// }
```

Trong cùng một lớp, chuyển instance method thành static method (hoặc ngược lại), đổi mức truy cập `public`/`private`, thêm `final`/`synchronized` hay đổi danh sách ngoại lệ cũng không tạo overload mới nếu danh sách tham số vẫn tương đương.

### 3.6. `varargs` là một dạng tham số mảng

`int... values` dùng cú pháp **variable arity parameter** (*tham số số lượng biến đổi*). Một method có thể được gọi với nhiều đối số riêng lẻ phù hợp, nhưng bên trong nó nhận một **mảng**.

```java
class Totalizer {
    int total(int... values) {
        int result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }
}
```

Các lời gọi `total()`, `total(2)`, `total(2, 3, 4)` và `total(new int[]{2, 3})` đều có thể hợp lệ với **một method** `total(int...)`. Số cách gọi nhiều **không đồng nghĩa có nhiều overload**.

Quan trọng: không được khai báo cùng lúc `void add(int... values)` và `void add(int[] values)` trong **cùng một lớp** như hai overload riêng, vì `int...` tương ứng với kiểu tham số mảng `int[]` trong chữ ký:

```java
// class BadVarargs {
//     void add(int... values) { }
//     void add(int[] values) { } // Lỗi: chữ ký tương đương.
// }
```

Một method varargs chỉ có **một tham số varargs**, và tham số ấy phải là **tham số cuối cùng** trong danh sách.

## 4. Thế nào là “chữ ký phương thức” trong Java?

Ở mức học nạp chồng cơ bản, có thể ghi nhớ chữ ký phương thức gồm **tên và các kiểu tham số theo đúng thứ tự**; nó không gồm kiểu trả về, tên biến tham số hay nội dung method.

Ví dụ:

| Khai báo | Chữ ký dễ đọc | Có trùng `log(String)`? |
| --- | --- | --- |
| `void log(String text)` | `log(String)` | Chính nó |
| `void log(String value)` | `log(String)` | **Trùng** |
| `String log(String text)` | `log(String)` | **Trùng** |
| `void log(Object text)` | `log(Object)` | **Khác** |
| `void log(String text, int level)` | `log(String, int)` | **Khác** |
| `void log(int level, String text)` | `log(int, String)` | **Khác** |

Về mặt đặc tả Java (*Java Language Specification*), khái niệm chữ ký còn xét đến **tham số kiểu của generic method**, phép thay thế tham số kiểu và các quy tắc **override-equivalent signatures**/**type erasure**. Vì vậy mẹo “khác ký tự trên dòng tham số là đủ” không chính xác với generic hoặc varargs.

Ví dụ hai khai báo sau khác chữ viết nhưng xung đột ở mức Java:

```java
// import java.util.List;
//
// class InvalidGenerics {
//     void accept(List<String> values) { }
//     void accept(List<Integer> values) { }
// }
```

Trong cùng một lớp, cả hai kiểu tham số generic đều có **erasure** là `List`. Compiler báo **name clash**, chứ không xem đây là overload hợp lệ. Phần này sẽ được giải thích kỹ hơn ở mục generic.

## 5. Overload resolution xảy ra khi nào?

**Phân giải nạp chồng** (*overload resolution*) về cơ bản là quyết định của **trình biên dịch** dựa vào:

1. **Tên method** và tập khai báo có thể tìm thấy từ biểu thức gọi, phạm vi truy cập và kiểu tĩnh liên quan.
2. **Số lượng và kiểu tĩnh của các biểu thức đối số**, kể cả các chuyển đổi mà Java cho phép.
3. **Những overload áp dụng được** theo các pha kiểm tra thích hợp.
4. **Phương thức cụ thể nhất** (*most specific*) trong các overload thích hợp; nếu có nhiều ứng viên mà không chọn được duy nhất, lời gọi có thể **mơ hồ và không biên dịch**.

Sau khi compiler chọn một chữ ký, nếu đó là **instance method có thể override**, runtime vẫn có thể chọn **phần thân triển khai của lớp con** dựa theo đối tượng nhận lời gọi. Đây là hai bước khác nhau: **chọn overload ở compile time**, và có thể **dispatch implementation ở runtime**.

### Thứ tự ưu tiên khái quát của các pha

Java xét các ứng viên theo một số pha, theo thứ tự ưu tiên. Trong cách hiểu cơ bản về method invocation:

1. **Strict invocation**: áp dụng các chuyển đổi như identity, primitive widening và reference widening thích hợp; chưa cần boxing/unboxing hay phép mở rộng varargs.
2. **Loose invocation**: nếu pha trước chưa tìm được overload áp dụng, có thể xét boxing/unboxing và các chuyển đổi phù hợp.
3. **Variable arity**: nếu hai pha trước không tìm được, xét phương thức varargs với số đối số thay đổi.

Trong mỗi pha, quy tắc **most specific** tiếp tục chọn phương thức phù hợp nhất; không đơn giản là “Java luôn chọn method có tên kiểu giống nhất theo mắt người”.

Để tránh nhầm, hãy **xác định kiểu tĩnh của đối số trước**, rồi xem chuyển đổi nào được phép, những chữ ký nào áp dụng ở pha sớm nhất và có ứng viên cụ thể nhất hay không.

## 6. Widening, boxing và varargs: vì sao thứ tự lựa chọn quan trọng?

Ví dụ chuẩn: một literal số nguyên `5` có kiểu `int`. Nếu tồn tại overload nhận `long` và `Integer`, Java có thể chọn `long` bằng **primitive widening** ở pha trước, thay vì boxing sang `Integer`.

Tạo tệp **`OverloadResolutionDemo.java`**:

```java
class Selector {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    static String choose(int... values) {
        return "int... count=" + values.length;
    }

    static String identify(Object value) {
        return "Object";
    }

    static String identify(String value) {
        return "String";
    }
}

public class OverloadResolutionDemo {
    public static void main(String[] args) {
        System.out.println(Selector.choose(5));
        System.out.println(Selector.choose(Integer.valueOf(5)));
        System.out.println(Selector.choose());
        System.out.println(Selector.choose(1, 2));
        System.out.println(Selector.identify("Java"));
        System.out.println(Selector.identify((Object) "Java"));
        System.out.println(Selector.identify(null));
    }
}
```

Biên dịch và chạy:

```bash
javac OverloadResolutionDemo.java
java OverloadResolutionDemo
```

Output:

```text
long
Integer
int... count=0
int... count=2
String
Object
String
```

Giải thích:

- `choose(5)`: đối số có kiểu `int`, có thể **widen** sang `long` ở pha strict. Boxing sang `Integer` không được ưu tiên trước widening, nên chọn `choose(long)`.
- `choose(Integer.valueOf(5))`: đối số đã có kiểu `Integer`; `choose(Integer)` khớp trực tiếp, thắng so với đường unbox rồi widen `long` ở pha muộn hơn.
- `choose()`: không có overload một tham số cố định nào phù hợp; `choose(int...)` nhận **0** phần tử bằng variable arity.
- `choose(1, 2)`: cần overload varargs, nhận hai giá trị `int`.
- `identify("Java")`: đối số có kiểu tĩnh `String`, có thể dùng overload `Object` nhưng `String` cụ thể hơn, nên chọn `identify(String)`.
- `identify((Object) "Java")`: ép kiểu thay **kiểu tĩnh của biểu thức đối số** thành `Object`, nên chọn `identify(Object)` dù object runtime vẫn là một `String`.
- `identify(null)`: literal `null` phù hợp cả `Object` và `String`; `String` là subtype của `Object` và cụ thể hơn, nên Java chọn `identify(String)`.

### Ghi chú về số nguyên literal và narrowing

`choose(5)` trong ví dụ có kiểu `int`, không tự coi là `byte` chỉ vì giá trị 5 nằm trong phạm vi `byte`.

```java
class NumericChoice {
    static String select(byte value) {
        return "byte";
    }

    static String select(short value) {
        return "short";
    }
}
```

Trong lớp này, `NumericChoice.select(5)` **không biên dịch**: `5` có kiểu `int`, và lời gọi method thông thường không tự thu hẹp `int` sang `byte`/`short` như cách một số phép gán hằng có quy tắc riêng. Viết `NumericChoice.select((byte) 5)` sẽ chọn bản `byte`; viết `NumericChoice.select((short) 5)` sẽ chọn bản `short`.

Một **explicit cast** có thể làm thay đổi quá trình chọn overload, nhưng cũng có thể mất dữ liệu nếu ép kiểu số vượt miền biểu diễn. Không nên thêm cast chỉ để ép compiler chọn nhánh nếu API có cách gọi rõ ràng hơn.

## 7. Tại sao `null` có thể làm lời gọi mơ hồ?

`null` có thể chuyển thành nhiều kiểu tham chiếu, nhưng **không có kiểu runtime cụ thể của một object để giúp chọn overload**. Khi hai kiểu tham số không có quan hệ subtype theo hướng cho ra ứng viên cụ thể nhất, lời gọi có thể mơ hồ.

Ví dụ cố ý không biên dịch ở dòng được chú thích:

```java
class NullChoice {
    static String test(String value) {
        return "String";
    }

    static String test(Integer value) {
        return "Integer";
    }

    static void demo() {
        // System.out.println(test(null));
        // Bỏ comment -> lỗi: reference to test is ambiguous.
        System.out.println(test((String) null));
        System.out.println(test((Integer) null));
    }
}
```

`test(null)` có hai ứng viên `test(String)` và `test(Integer)`. Không có quan hệ “`String` là subtype của `Integer`” hoặc ngược lại, nên không có ứng viên cụ thể nhất duy nhất. Cast tường minh định rõ kiểu biểu thức và giải quyết lời gọi trong ví dụ.

Một ví dụ khác:

```java
class RelatedChoice {
    static String select(Object value) {
        return "Object";
    }

    static String select(String value) {
        return "String";
    }
}
```

`RelatedChoice.select(null)` chọn `String` vì `String` cụ thể hơn `Object`. Vì thế nói “truyền `null` vào mọi overload đều lỗi” là sai; phải xem quan hệ kiểu giữa **các ứng viên thật sự áp dụng**.

**Lưu ý:** Cast `(String) null` không tạo một đối tượng `String`; giá trị vẫn là `null`. Nó chỉ định kiểu tĩnh để phân giải overload. Nếu thân phương thức dereference giá trị này, vẫn có thể phát sinh `NullPointerException`.

## 8. `varargs` và overload dạng tham số cố định

Một overload có **fixed arity** thường thắng lời gọi phù hợp ở pha sớm hơn so với lời gọi varargs cần gom nhiều đối số. Tuy nhiên, một khai báo varargs cũng có thể được gọi như một phương thức có tham số mảng với số lượng đối số cố định; do đó không nên rút gọn mọi tình huống thành câu “Java luôn bỏ qua varargs”.

Tạo tệp **`VarargsOverloadDemo.java`**:

```java
class Printer {
    static String show(int value) {
        return "one=" + value;
    }

    static String show(int... values) {
        return "many=" + values.length;
    }
}

public class VarargsOverloadDemo {
    public static void main(String[] args) {
        System.out.println(Printer.show(4));
        System.out.println(Printer.show(4, 5));
        System.out.println(Printer.show());
        System.out.println(Printer.show(new int[]{7, 8, 9}));
    }
}
```

Lệnh:

```bash
javac VarargsOverloadDemo.java
java VarargsOverloadDemo
```

Output:

```text
one=4
many=2
many=0
many=3
```

Phân tích:

1. `show(4)` khớp `show(int)` bằng fixed arity; bản `show(int...)` không được chọn khi lời gọi một `int` đã có ứng viên ở pha sớm hơn.
2. `show(4, 5)` không khớp `show(int)` vì có hai đối số; varargs thu các giá trị thành một `int[]`.
3. `show()` được xử lý bằng varargs với mảng rỗng.
4. `show(new int[]{7,8,9})` truyền trực tiếp một **mảng** tới tham số có kiểu `int[]` của `show(int...)`; đây là cách gọi hợp lệ ở **fixed-arity form** của phương thức varargs.

### Varargs có thể gây mơ hồ

```java
class AmbiguousVarargs {
    static void process(int... values) { }
    static void process(boolean... values) { }

    static void demo() {
        // process(); // Lỗi biên dịch: cả hai cùng nhận 0 phần tử.
        process(1);    // Hợp lệ: chỉ int... phù hợp.
        process(true); // Hợp lệ: chỉ boolean... phù hợp.
    }
}
```

Thêm nhiều overload varargs với các kiểu phần tử không liên quan khiến lời gọi không đối số khó phân giải. API thường nên có một overload không tham số riêng hoặc tránh các overload varargs gây mơ hồ.

## 9. Nạp chồng qua kế thừa và khác biệt với ghi đè

Một lớp có thể định nghĩa overload mới bên cạnh các overload **kế thừa hợp lệ**. Nhưng **overloading** và **overriding** là hai cơ chế khác nhau:

| Khía cạnh | Overloading (nạp chồng) | Overriding (ghi đè) |
| --- | --- | --- |
| Mối quan hệ | Nhiều method cùng tên, **khác danh sách tham số/chữ ký hợp lệ** | Lớp con cung cấp implementation cho instance method có chữ ký tương ứng của lớp cha |
| Có cần kế thừa? | Không; có thể xảy ra ngay trong một lớp | Có quan hệ kiểu/triển khai thích hợp |
| Thời điểm quyết định | Chọn overload chủ yếu ở **compile time** | Chọn implementation ghi đè tại **runtime** với instance method có thể override |
| Kiểu trả về | Có thể khác, nhưng không đủ để phân biệt overload | Phải tương thích theo quy tắc kiểu trả về, kể cả covariant return khi hợp lệ |
| `static` | Có thể nạp chồng static method bằng danh sách tham số khác | Static method **không override**, có thể hide theo quy tắc |
| `@Override` | Không dùng để đánh dấu một overload mới thuần túy | Dùng để nhờ compiler kiểm tra ý định ghi đè |

### Ví dụ kết hợp, chạy được

Tạo tệp **`OverloadVsOverrideDemo.java`**:

```java
class Animal {
    String sound() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "dog";
    }
}

class Inspector {
    static String inspect(Animal animal) {
        return "Animal overload: " + animal.sound();
    }

    static String inspect(Dog dog) {
        return "Dog overload: " + dog.sound();
    }
}

public class OverloadVsOverrideDemo {
    public static void main(String[] args) {
        Animal general = new Dog();
        Dog specific = new Dog();

        System.out.println(Inspector.inspect(general));
        System.out.println(Inspector.inspect(specific));
    }
}
```

Chạy:

```bash
javac OverloadVsOverrideDemo.java
java OverloadVsOverrideDemo
```

Output:

```text
Animal overload: dog
Dog overload: dog
```

Dòng đầu có **hai quyết định độc lập**:

1. `general` có **kiểu tĩnh `Animal`**, nên `inspect(Animal)` được chọn **khi biên dịch**. Java không chọn `inspect(Dog)` chỉ vì object runtime là `Dog`.
2. Bên trong `inspect(Animal)`, lời gọi `animal.sound()` là instance method có thể override. Vì receiver runtime là `Dog`, implementation `Dog.sound()` trả `dog`.

Dòng thứ hai: `specific` có kiểu tĩnh `Dog`, nên `inspect(Dog)` được chọn từ đầu; gọi `sound()` trên receiver `Dog` cũng trả `dog`.

### Overload được kế thừa có thể tham gia lựa chọn

```java
class BaseNotifier {
    void notify(Object message) {
        System.out.println("object");
    }
}

class TextNotifier extends BaseNotifier {
    void notify(String message) {
        System.out.println("text");
    }
}
```

Trong phạm vi truy cập hợp lệ, `new TextNotifier().notify("hi")` chọn overload `notify(String)`; `new TextNotifier().notify((Object) "hi")` chọn `notify(Object)` được kế thừa.

Nếu đặt `BaseNotifier base = new TextNotifier();` rồi gọi `base.notify("hi")`, compiler chỉ thấy overload `notify(Object)` qua **kiểu tĩnh `BaseNotifier`**, nên chọn bản đó. `TextNotifier.notify(String)` không override `BaseNotifier.notify(Object)` vì danh sách kiểu tham số khác.

Các lớp trên là **mảnh khai báo có thể biên dịch nhưng chưa có `main`**, dùng để minh họa sự khác nhau giữa tập overload mà compiler nhìn thấy và object runtime.

## 10. Nạp chồng static method và instance method

Cả **static method** và **instance method** đều có thể được nạp chồng khi chữ ký hợp lệ khác nhau:

```java
class Parser {
    static int parse(String value) {
        return Integer.parseInt(value);
    }

    static int parse(String value, int radix) {
        return Integer.parseInt(value, radix);
    }

    String render(int value) {
        return Integer.toString(value);
    }

    String render(long value) {
        return Long.toString(value);
    }
}
```

- `Parser.parse("10")` chọn bản một tham số, trả `10`.
- `Parser.parse("10", 2)` chọn bản hai tham số, diễn giải chuỗi ở cơ số 2 và trả `2`.
- Với `Parser parser = new Parser();`, `parser.render(10)` chọn `render(int)`.
- `parser.render(10L)` chọn `render(long)`.

Trong cùng một lớp, **không thể** khai báo `static void f(int x)` và `void f(int x)` chỉ vì một method static và method kia instance; hai chữ ký vẫn trùng.

Khi static method trong lớp con cùng chữ ký một static method được kế thừa hợp lệ, đó là **method hiding**, không phải overriding; không nên dựa vào kiểu runtime của đối tượng để chọn static method.

## 11. Nạp chồng constructor: cùng ý tưởng, quy tắc sử dụng khác

Mặc dù chủ đề ở đây là **method overloading**, constructor cũng có thể được **overload** theo danh sách tham số, để cung cấp nhiều cách tạo instance:

```java
class UserProfile {
    private final String name;
    private final int level;

    UserProfile(String name) {
        this(name, 1);
    }

    UserProfile(String name, int level) {
        this.name = name;
        this.level = level;
    }

    String summary() {
        return name + ":" + level;
    }
}
```

- `new UserProfile("Lan")` chọn constructor một `String`; constructor này gọi `this(name, 1)` để tái sử dụng logic.
- `new UserProfile("Lan", 3)` chọn constructor `(String, int)`.
- Constructor **không có kiểu trả về** và không phải method thông thường.
- Khi lớp đã khai báo một constructor có tham số, Java **không tự thêm constructor mặc định không tham số**.

Constructor overloading dùng nguyên tắc chọn chữ ký thích hợp tại compile time, nhưng constructor **không được kế thừa hoặc override**. Constructor chaining bằng `this(...)` cũng phải tuân theo các quy tắc riêng; trên Java 17, lời gọi `this(...)` tường minh phải xuất hiện đầu thân constructor.

Việc nhắc constructor ở đây chỉ giúp phân biệt hai cơ chế có nét tương đồng; trong phần thiết kế API, không nên biến constructor thành “phương thức trả về đối tượng” hay đánh đồng với instance method.

## 12. Generic methods và type erasure: chữ ký trông khác vẫn có thể xung đột

Với **generic methods** và tham số generic, cần tính đến **type erasure**. Những tham số dạng `List<String>` và `List<Integer>` mang thông tin kiểu ở compile time, nhưng cả hai đều có erasure là `List`.

Đoạn **cố ý sai**:

```java
// import java.util.List;
//
// class Repository {
//     void store(List<String> values) { }
//     void store(List<Integer> values) { }
//     // Lỗi name clash: hai khai báo có cùng erasure.
// }
```

Sửa bằng cách chọn những **kiểu tham số phân biệt được**, đổi tên phương thức theo ý nghĩa, hoặc thiết kế một generic method hợp lý:

```java
import java.util.List;

class Repository {
    <T> int count(List<T> values) {
        return values.size();
    }

    int count(String text) {
        return text.length();
    }
}
```

Đây là khai báo lớp hợp lệ:

- `count(List<T>)` là **generic method** áp dụng cho danh sách có kiểu phần tử thích hợp.
- `count(String)` là overload khác, vì tham số kiểu `String` khác tham số `List`.
- Với `List<String> items = List.of("a", "b");` thì `new Repository().count(items)` trả `2`.
- Với `new Repository().count("Java")` thì kết quả là `4`.

Không phải cứ hai method dùng generic theo cách nào đó đều xung đột; lỗi phát sinh khi quan hệ chữ ký/erasure khiến khai báo **không còn phân biệt hợp lệ**. Nếu muốn overload theo kiểu phần tử generic của các `List`, chỉ thay `List<String>` thành `List<Integer>` không đủ vì giới hạn erasure.

### Generic method có thể tham gia chọn overload

```java
class GenericChoice {
    static <T> String select(T value) {
        return "generic";
    }

    static String select(String value) {
        return "string";
    }
}
```

Hai method này hợp lệ: signature sau erasure của bản generic là `select(Object)`; bản còn lại là `select(String)`. Với `GenericChoice.select("hello")`, Java chọn bản `String` cụ thể hơn. Với `GenericChoice.select(123)`, compiler có thể suy ra `T` thích hợp và gọi bản generic, trả `generic`.

Đây là mảnh khai báo minh họa **không có `main` riêng**. Việc chọn overload generic trong tình huống phức tạp còn chịu **type inference** và các quy tắc most-specific chính xác của JLS; nên xây API tránh những chữ ký buộc người gọi phải đoán logic suy luận kiểu.

## 13. Khi nào nên và không nên nạp chồng?

Một API dùng overload tốt khi các biến thể có **cùng ý nghĩa**, nhưng khác dữ liệu đầu vào hoặc mức tiện dụng:

| Trường hợp | Overload thường phù hợp? | Giải thích |
| --- | --- | --- |
| `print(String)` và `print(int)` | Có | Cùng hành động xuất thông tin, chấp nhận nhiều loại dữ liệu. |
| `connect(host)` và `connect(host, timeout)` | Có, nếu hành vi mặc định rõ | Bản một tham số có thể dùng timeout mặc định hợp lý. |
| `sum(int, int)` và `sum(double, double)` | Có | Cùng phép cộng với nhóm kiểu khác nhau. |
| `save(Customer)` và `save(Order)` | Có điều kiện | Hai loại thực thể có thể chia sẻ hợp đồng `save`; chú ý `save(null)` có thể mơ hồ. |
| `delete(String)` nhưng một overload “chỉ kiểm tra” | Không nên | Cùng tên gợi cùng hành vi mà tác dụng khác; dễ dùng sai. |
| Nhiều overload khác chỉ ở chuỗi `String` cùng số tham số | Không hợp lệ | Tên tham số không tạo chữ ký mới. |
| `process(List<String>)` với `process(List<Integer>)` | Không hợp lệ trong cùng lớp | Name clash do erasure. |

### Nguyên tắc thiết kế overload thân thiện

1. **Các overload cùng tên nên biểu đạt cùng một hành vi ở mức trừu tượng.** Nếu một bản có tác dụng xóa còn bản kia chỉ xem trạng thái, nên đặt tên riêng.
2. **Giữ thứ tự tham số ổn định** giữa các overload, nhất là khi nhiều tham số đều cùng kiểu `String` hoặc `int`.
3. **Tránh tổ hợp kiểu tham chiếu không liên quan** nếu API thường nhận `null`. `save(String)` và `save(Integer)` làm `save(null)` mơ hồ.
4. **Ưu tiên overload ít tham số gọi overload đủ tham số** để logic kiểm tra/hành vi không bị lặp và các biến thể nhất quán.
5. **Thận trọng với widening, boxing, generic và varargs.** Một overload mới có thể đổi kết quả phân giải của những lời gọi hiện có khi mã nguồn được biên dịch lại, dù không đổi tên method.
6. **Không dùng kiểu trả về để “định hướng” overload.** Nếu muốn API trả nhiều mô hình khác nhau cho cùng đối số, cân nhắc phương thức tên riêng hoặc thêm tham số kiểu/đích có ý nghĩa.
7. **Viết các bài kiểm tra hành vi theo loại đối số đặc trưng**, đặc biệt `null`, literal số, boxing và lời gọi varargs, khi API thực tế có nhiều chữ ký gần nhau.

## 14. Những lỗi thường gặp và cách chẩn đoán

### Lỗi 1: chỉ thay kiểu trả về

`int convert(String)` và `long convert(String)` không cùng tồn tại trong một lớp như overload. Kiểu trả về **không thuộc điều kiện phân biệt chữ ký**.

### Lỗi 2: thay tên biến tham số

`save(int id)` và `save(int key)` vẫn trùng chữ ký `save(int)`. Compiler không dùng tên tham số để chọn method.

### Lỗi 3: chỉ thêm `throws`, `public`, `static` hoặc `final`

Các modifier và danh sách ngoại lệ không làm thay đổi danh sách kiểu tham số; chúng không đủ tạo overload khác.

### Lỗi 4: tưởng Java chọn bằng kiểu object runtime

Nếu `Object value = "hello";`, lời gọi `use(value)` được phân giải theo kiểu tĩnh **`Object`**, không âm thầm chọn `use(String)` chỉ vì runtime value là `String`. Đây là điểm phân biệt overloading với overriding.

### Lỗi 5: dùng `null` với hai reference types không liên quan

`method(String)` và `method(Integer)` có thể làm `method(null)` mơ hồ. Có thể truyền một giá trị cụ thể hoặc cast tường minh nếu hợp đồng cho phép `null`, nhưng cast không thay đổi việc giá trị vẫn là `null`.

### Lỗi 6: tưởng `int` tự narrow sang `short` khi gọi method

Lời gọi method với literal `1` mang kiểu `int` và không tự chọn `method(short)` nhờ giá trị nhỏ. Cần một kiểu đối số phù hợp hoặc cast khi thật sự muốn.

### Lỗi 7: nghĩ `int...` và `int[]` là hai overload

Hai khai báo cùng tên `f(int...)` và `f(int[])` trùng kiểu tham số ở mức chữ ký; không được khai báo như hai phương thức riêng cùng lớp.

### Lỗi 8: chỉ thay `List<String>` thành `List<Integer>`

Generic type arguments có thể bị **erasure** khiến hai chữ ký đụng nhau. Hãy xem loại tham số sau erasure, không chỉ phần trong `<...>`.

### Lỗi 9: quá nhiều overload varargs

Hai varargs method không tương thích như `f(int...)` và `f(boolean...)` có thể đều chấp nhận lời gọi `f()`. Nếu không có lựa chọn cụ thể nhất, compiler báo ambiguous.

### Lỗi 10: nhầm constructor overload với method overload

Constructor có tên lớp và **không có kiểu trả về**; method có kiểu trả về (kể cả `void`). Constructor được chọn khi khởi tạo đối tượng; method được gọi trên đối tượng hoặc qua lớp tùy static/instance.

### Lỗi 11: thêm overload mà quên xem lời gọi cũ

Ví dụ API ban đầu chỉ có `log(Object)`, nên `log("abc")` dùng bản đó. Khi thêm `log(String)` rồi **biên dịch lại mã nguồn**, lời gọi `log("abc")` thường được chọn sang `log(String)`. API overload mới có thể thay đổi **hành vi khi tái biên dịch**. Nếu một chương trình đã biên dịch trước, bytecode vẫn tham chiếu đến method descriptor cũ khi nó còn tồn tại; đó là góc nhìn tương thích nhị phân khác với phân giải mã nguồn.

### Lỗi 12: lạm dụng `@Override` cho method nạp chồng

`@Override` yêu cầu method thực sự override/implement một method thích hợp từ siêu kiểu (trừ các chi tiết ngôn ngữ cụ thể). Nếu chỉ khai báo method mới cùng tên nhưng khác tham số mà không override, `@Override` có thể gây lỗi biên dịch.

## 15. Tự kiểm tra với câu hỏi và đáp án

**Câu 1.** Hai method `void draw(int size)` và `void draw(double size)` có overload hợp lệ không?

**Đáp án:** Có. Chúng cùng tên nhưng khác kiểu tham số (`int` so với `double`).

**Câu 2.** `int read(String path)` và `String read(String path)` có cùng tồn tại không?

**Đáp án:** Không. Khác kiểu trả về nhưng danh sách tham số trùng, nên không hình thành overload hợp lệ.

**Câu 3.** Với các method `choose(long)` và `choose(Integer)`, gọi `choose(7)` sẽ chọn gì?

**Đáp án:** `choose(long)` do literal `7` là `int`, chuyển `int → long` bằng primitive widening được xét trước boxing `int → Integer`.

**Câu 4.** Với `void save(Object)` và `void save(String)`, gọi `save(null)` có mơ hồ không?

**Đáp án:** Không. `String` cụ thể hơn `Object` nên `save(String)` được chọn.

**Câu 5.** Với `void save(String)` và `void save(Integer)`, gọi `save(null)` có biên dịch được không?

**Đáp án:** Không; hai kiểu tham số không có quan hệ cụ thể hơn để quyết định một overload duy nhất. Có thể dùng một cast hợp lệ nếu muốn chỉ rõ ý định.

**Câu 6.** `void write(int... values)` và `void write(int[] values)` có tạo hai overload không?

**Đáp án:** Không. Tham số varargs là tham số mảng ở chữ ký tương ứng; hai khai báo xung đột.

**Câu 7.** Tại sao `process(List<String>)` và `process(List<Integer>)` không là hai overload hợp lệ trong cùng lớp?

**Đáp án:** Cả hai có erasure `process(List)`; Java báo name clash.

**Câu 8.** Với `Animal a = new Dog();` và hai overload `inspect(Animal)`, `inspect(Dog)`, `inspect(a)` chọn bản nào?

**Đáp án:** `inspect(Animal)` vì compiler dùng **kiểu tĩnh `Animal`** của `a` khi chọn overload. Nếu trong thân gọi một instance method được `Dog` override, runtime dispatch vẫn có thể dùng triển khai của `Dog`.

**Câu 9.** `sum(int, int)` và `sum(int, int, int)` có overload hợp lệ không? Có thể giữ cùng kiểu trả về không?

**Đáp án:** Hợp lệ vì khác số tham số. Có thể cùng trả `int`; overload không bắt buộc đổi kiểu trả về.

**Câu 10.** Vì sao thêm `log(String)` vào lớp vốn đã có `log(Object)` có thể ảnh hưởng chương trình sau khi build lại?

**Đáp án:** Những lời gọi có đối số kiểu tĩnh `String` sẽ có một ứng viên mới cụ thể hơn. Khi biên dịch lại, chúng có thể được liên kết với `log(String)` và có hành vi khác với trước.

## 16. Quy trình phân tích một lời gọi bị lỗi “ambiguous” hoặc “cannot be applied”

Khi compiler báo khó chọn method, có thể thực hiện theo trình tự sau:

1. **Liệt kê đúng tập overload có thể gọi** từ tên method, kiểu tĩnh của receiver, phạm vi truy cập và các khai báo liên quan.
2. **Ghi kiểu tĩnh của từng biểu thức đối số.** Literal `1` là `int`; `1L` là `long`; `"x"` là `String`; `null` là null type đặc biệt.
3. **Đối chiếu số lượng và thứ tự tham số.** Nhớ rằng `varargs` chỉ có thể mở rộng ở pha phù hợp, và có trường hợp nhận mảng ở fixed arity.
4. **Kiểm tra chuyển đổi cho phép.** Primitive widening khác narrowing; boxing/unboxing có thứ tự xét; một cast tường minh làm thay đổi kiểu biểu thức.
5. **Áp dụng pha sớm nhất có ứng viên thích hợp**, rồi chọn ứng viên most-specific. Nếu nhiều ứng viên không có lựa chọn duy nhất, lời gọi ambiguous.
6. **Với generic, kiểm tra type inference và erasure.** Lỗi name clash ở khai báo khác lỗi ambiguous ở lời gọi.
7. **Phân biệt overload với override.** Runtime receiver có thể quyết định phần thân override, nhưng không tự thay đổi chữ ký overload đã được compiler chọn.
8. **Sửa bằng API sáng rõ:** đổi tên cho hành vi khác, giảm overload không cần thiết, thống nhất thứ tự tham số, sử dụng kiểu rõ ràng hoặc cast khi thực sự cần.

Ví dụ chẩn đoán nhanh:

```java
class Choice {
    static void f(String value) { }
    static void f(Integer value) { }
}
```

Trong class khác, `Choice.f(null)` bị ambiguous. Compiler không thiếu thông tin về **số lượng tham số**, mà thiếu một **kiểu đích cụ thể nhất duy nhất** cho `null`. Sửa bằng `Choice.f((String) null)` hoặc tránh API đòi người dùng phân biệt hai nhánh chỉ bằng một giá trị `null`.

---

**Ghi nhớ:** **Overloading** cho phép nhiều phương thức cùng tên để phục vụ **những danh sách tham số khác nhau**. Một overload hợp lệ được phân biệt bằng chữ ký và các quy tắc generic/erasure, **không chỉ bằng kiểu trả về hoặc modifier**. Việc chọn overload diễn ra ở compile time dựa trên **kiểu tĩnh đối số**, thứ tự pha chuyển đổi và ứng viên cụ thể nhất; quá trình này khác **overriding** theo receiver runtime. API tốt dùng overload để diễn đạt một hành vi nhất quán và tránh các chữ ký gây mơ hồ.