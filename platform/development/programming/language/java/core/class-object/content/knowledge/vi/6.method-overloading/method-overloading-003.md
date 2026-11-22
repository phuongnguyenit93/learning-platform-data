# Vì sao chỉ đổi kiểu trả về không tạo được nạp chồng phương thức trong Java?

Trong Java, **method overloading (nạp chồng phương thức)** là khai báo nhiều phương thức có **cùng tên nhưng khác danh sách tham số** theo quy tắc chữ ký phương thức (*method signature*). **Chỉ thay kiểu trả về**, chẳng hạn từ `int` sang `String`, trong khi giữ nguyên tên và tham số **không tạo ra một overload hợp lệ**.

Điều này không phải quy ước đặt tên mà là quy tắc của ngôn ngữ Java: **return type không nằm trong chữ ký phương thức dùng để phân biệt các khai báo overload trong mã nguồn**. Ví dụ, hai method sau trong cùng một class sẽ gây lỗi biên dịch:

~~~java
class Report {
    int read(int id) {
        return id;
    }

    String read(int id) {
        return "ID-" + id;
    }
}
~~~

Cả hai đều có chữ ký `read(int)`. Một phương thức trả `int`, một phương thức trả `String`, nhưng compiler vẫn coi đây là **hai khai báo trùng chữ ký**, nên không có chương trình Java hợp lệ được tạo ra từ đoạn mã này.

Bài học dưới đây giải thích chính xác chữ ký gồm những gì, cách compiler chọn overload khi gọi method, sự khác biệt với overriding, các trường hợp gần giống dễ nhầm và cách thiết kế API đúng trên Java 17+.

## 1. Phân biệt tên, chữ ký và kiểu trả về

Xét ví dụ:

~~~java
class Printer {
    public String format(int number, boolean grouped) {
        return number + ":" + grouped;
    }
}
~~~

Đây là một **đoạn khai báo lớp minh họa**, chưa có `main` để chạy độc lập.

| Thành phần | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| Tên method | `format` | Tên được dùng khi gọi |
| Danh sách tham số hình thức | `int number, boolean grouped` | Hai tham số theo đúng thứ tự |
| Các kiểu tham số | `int, boolean` | Thành phần quan trọng của chữ ký |
| Chữ ký theo cách biểu diễn thông thường | `format(int, boolean)` | Phân biệt method với overload khác |
| Kiểu trả về | `String` | Quy định kết quả mà thân method phải tạo ra và caller nhận |
| Modifier | `public` | Quy định khả năng truy cập, không tạo chữ ký mới |
| Tên biến tham số | `number`, `grouped` | Không tạo chữ ký mới nếu chỉ đổi tên |

Theo **Java Language Specification (JLS) `8.4.2**, chữ ký phương thức được xác định bởi **tên phương thức và phần tham số** theo quy tắc về type parameters và các kiểu formal parameter. Khi hai method generic được xét, Java còn có quy tắc thích nghi các type parameters để xác định chữ ký tương đương; điểm cốt lõi ở đây là **return type không nằm trong danh sách đặc trưng phân biệt overload**.

Do đó:

~~~java
// Hai khai báo cùng chữ ký f(int), KHÔNG hợp lệ nếu cùng một class:
int f(int x) { return x; }
long f(int y) { return y; }

// Hai khai báo khác chữ ký g(int) và g(long), có thể cùng một class:
int g(int x) { return x; }
long g(long x) { return x; }
~~~

Các dòng là **minh họa thân method**, không phải mã độc lập để biên dịch cùng lúc. Ở cặp `f`, đổi kiểu kết quả và tên biến tham số không giúp gì. Ở cặp `g`, thay kiểu tham số từ `int` sang `long` tạo được overload, bất kể kiểu trả về của chúng có giống nhau hay không.

**Tóm tắt:** để nhận diện overload, hãy quan sát **tên + các kiểu tham số theo thứ tự và số lượng tham số**, chứ không so các kiểu trả về.

## 2. Lỗi biên dịch khi chỉ thay return type

Giả sử bạn muốn cung cấp hai cách đọc tuổi:

**Tệp `ReturnOnly.java` — ví dụ cố ý sai:**

~~~java
public class ReturnOnly {
    int getAge() {
        return 20;
    }

    String getAge() {
        return "20 tuổi";
    }
}
~~~

Chạy:

~~~bash
javac ReturnOnly.java
~~~

`javac` từ chối và thường có thông báo dạng:

~~~text
ReturnOnly.java:6: error: method getAge() is already defined in class ReturnOnly
~~~

Số dòng, cách trình bày và các chi tiết khác có thể khác theo phiên bản JDK. Nguyên nhân bất biến: hai method có **cùng chữ ký `getAge()`** nhưng khác return type.

Ngay cả khi trong phương thức gọi, người lập trình viết:

~~~java
int numericAge = person.getAge();
String ageLabel = person.getAge();
~~~

thì cũng không khiến hai khai báo `getAge()` trên trở nên hợp lệ. **Compiler phải kiểm tra tính hợp lệ của khai báo method trước**, chứ không thể dựa vào việc caller dự định gán kết quả cho biến gì để hợp thức hóa hai method trùng chữ ký.

### 2.1. Một cách sửa: đặt tên theo ý nghĩa kết quả

Nếu cần hai biểu diễn của cùng dữ liệu, dùng tên khác nhau:

~~~java
class Person {
    private final int age;

    Person(int age) {
        this.age = age;
    }

    int getAge() {
        return age;
    }

    String getAgeLabel() {
        return age + " tuổi";
    }
}
~~~

Ở đây `getAge()` và `getAgeLabel()` có **hai tên khác nhau**, nên không còn xung đột. Ngoài việc biên dịch được, tên còn giúp caller biết mình nhận một số hay một chuỗi trình bày.

### 2.2. Cách sửa khác: khác tham số thật sự

~~~java
class Person {
    private final int age = 20;

    int getAge() {
        return age;
    }

    String getAge(boolean withUnit) {
        return withUnit ? age + " tuổi" : Integer.toString(age);
    }
}
~~~

Hai method có chữ ký `getAge()` và `getAge(boolean)`, nên **overload hợp lệ**. Tuy nhiên, việc thêm một tham số `boolean` chỉ để né lỗi compiler chưa chắc tạo API dễ hiểu. Với bài toán biểu diễn dữ liệu, `getAgeLabel()` hoặc `formatAge()` thường rõ mục đích hơn.

Nguyên tắc thiết kế: **thay danh sách tham số khi hai cách gọi thực sự khác dữ liệu đầu vào hoặc hành vi theo đầu vào**, không thêm tham số thừa chỉ để đổi kiểu trả về.

## 3. Vì sao Java thiết kế overload theo tham số?

Khi gặp lời gọi method, compiler cần xác định **method nào đang được gọi** dựa trên ngữ cảnh mã nguồn, tên method, các đối số, các overload có thể truy cập và quy tắc áp dụng/phân giải overload.

Ví dụ:

~~~java
class Calculator {
    int doubleValue(int number) {
        return number * 2;
    }

    double doubleValue(double number) {
        return number * 2;
    }
}
~~~

Nếu caller viết `calculator.doubleValue(3)`, đối số có kiểu `int` nên overload nhận `int` là lựa chọn phù hợp. Nếu viết `calculator.doubleValue(3.5)`, đối số có kiểu `double` nên overload nhận `double` phù hợp.

Nhưng nếu chỉ khác return type và giữ danh sách tham số y hệt, chẳng hạn:

~~~java
// Không hợp lệ:
int convert(String text) { return Integer.parseInt(text); }
long convert(String text) { return Long.parseLong(text); }
~~~

thì lời gọi `convert("12")` không mang khác biệt về tên hoặc kiểu tham số để nhận diện một khai báo duy nhất. Java **quy định ngay từ mức khai báo** rằng hai method không được khác biệt chỉ bằng return type.

Có hai điểm tinh tế cần hiểu đúng:

1. **Return type không phân biệt hai khai báo cùng chữ ký.** Đây là điều kiện chắc chắn, không có ngoại lệ chỉ nhờ compiler “nhìn vào biến nhận kết quả”.
2. Với các overload **đã hợp lệ**, đặc biệt method generic/poly expressions, **target typing** và type inference có thể tham gia vào quá trình kiểm tra và chọn method trong một số ngữ cảnh. Vì vậy không nên phát biểu quá mức rằng “Java tuyệt đối không xét kiểu kết quả ở mọi bước phân giải method”. Dù có những quy tắc nâng cao như vậy, chúng **không hợp thức hóa** hai method chỉ khác return type.

Ngoài ra, một lời gọi có thể **bỏ qua kết quả**:

~~~java
calculator.doubleValue(3); // hợp lệ: gọi method rồi không dùng kết quả
~~~

Điều này càng cho thấy không thể yêu cầu mọi caller phải cung cấp một “kiểu muốn nhận” để tạo ra sự khác biệt giữa hai method có cùng tên và tham số.

## 4. Ví dụ Java 17+ chạy được: overload hợp lệ dù return type khác nhau

Lưu toàn bộ vào **`OverloadReturnDemo.java`**:

~~~java
import java.util.Locale;

public class OverloadReturnDemo {
    static int convert(int value) {
        return value * 2;
    }

    static String convert(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }

    static double convert(double value) {
        return value / 2.0;
    }

    static int measure(String text) {
        return text.length();
    }

    static String measure(String text, String prefix) {
        return prefix + text;
    }

    static class Parent {
        Number result() {
            return 10;
        }
    }

    static final class Child extends Parent {
        @Override
        Integer result() {
            return 20;
        }
    }

    public static void main(String[] args) {
        System.out.println("int: " + convert(3));
        System.out.println("String: " + convert("  java  "));
        System.out.println("double: " + convert(8.0));

        System.out.println("length: " + measure("Java"));
        System.out.println("prefixed: " + measure("Java", "Hi-"));

        Parent parent = new Child();
        System.out.println("overridden: " + parent.result());
        System.out.println("runtime type: "
                + parent.result().getClass().getSimpleName());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 OverloadReturnDemo.java
java OverloadReturnDemo
~~~

**Stdout chính xác:**

~~~text
int: 6
String: JAVA
double: 4.0
length: 4
prefixed: Hi-Java
overridden: 20
runtime type: Integer
~~~

Giải thích:

1. Ba method tên `convert` có các chữ ký `convert(int)`, `convert(String)`, `convert(double)` nên là **ba overload hợp lệ**. Return type `int`, `String` và `double` khác nhau hoàn toàn không gây lỗi vì **danh sách tham số đã khác**.
2. `convert(3)` gọi bản nhận `int`; `3 * 2` thành 6. `convert("  java  ")` dùng overload nhận `String`, cắt khoảng trắng ở đầu/cuối và đổi thành `JAVA` với `Locale.ROOT`. `convert(8.0)` nhận `double`, chia đôi thành `4.0`.
3. Hai method `measure` khác **số lượng tham số**: `measure(String)` trả chiều dài chuỗi, còn `measure(String, String)` thêm tiền tố vào chuỗi.
4. `Parent.result()` và `Child.result()` là **overriding (ghi đè)**, **không phải overloading**: hai method cùng chữ ký `result()` ở hai class trong quan hệ kế thừa. `Child` được phép trả `Integer` vì `Integer` là subtype của `Number`, tức **covariant return type**.
5. Biến `parent` có kiểu khai báo `Parent` nhưng tham chiếu đến object `Child`. Khi gọi instance method `result()`, dispatch động chọn implementation của `Child`; `20` được boxing thành `Integer`, nên tên runtime type là `Integer`.

Điểm dễ bỏ sót: chỉ riêng `Parent.result()` trả `Number` và `Child.result()` trả `Integer` **không tạo overload**. Kết quả cuối ví dụ minh họa trường hợp **override có return type hẹp hơn**, vốn tuân thủ một bộ quy tắc khác.

## 5. Khi return type khác nhau vẫn có thể overload?

Một cặp phương thức cùng tên được overload hợp lệ khi **danh sách tham số khác nhau** theo quy tắc Java. Return types của chúng **có thể giống hoặc khác**, nhưng sự khác nhau đó không quyết định được overload:

~~~java
class Converter {
    int parse(int number) {
        return number;
    }

    String parse(String text) {
        return text.trim();
    }
}
~~~

`parse(int)` và `parse(String)` hợp lệ vì **kiểu tham số khác nhau**, không phải vì return type int/String. Ngược lại `int parse(String)` và `String parse(String)` trong cùng class sẽ xung đột.

| Hai khai báo | Hợp lệ? | Điểm phân biệt |
| --- | --- | --- |
| `int f()` / `String f(int)` | Có | Số lượng tham số |
| `int f(int)` / `String f(String)` | Có | Kiểu tham số |
| `int f(int,String)` / `String f(String,int)` | Có | Thứ tự kiểu |
| `int f()` / `String f()` | **Không** | `f()` trùng |
| `int f(int)` / `long f(int)` | **Không** | `f(int)` trùng |

Với generic methods, hai kiểu như `List<String>` và `List<Integer>` còn có thể gây **name clash sau erasure**, dù nhìn qua source khác nhau. Đừng kết luận chỉ từ return types hoặc cách ghi type arguments.

## 6. Các thay đổi không cứu được hai chữ ký trùng nhau

Đổi tên tham số `userId` thành `accountId`, đổi `public` thành `private`, `static` thành instance, thêm `final` hay `throws IOException` đều **không** tạo ra overload khi tên và chữ ký tham số vẫn giống nhau. Những khai báo có behavior, ngoại lệ hoặc quyền truy cập khác nhau vẫn không thành hai overload hợp lệ trong cùng class nếu signature trùng.

Cách review: tạm bỏ return type/modifiers/parameter names/throws; so tên method và danh sách kiểu tham số, sau đó xét generic erasure và các quy tắc override-equivalent nếu cần. Bài này tập trung làm rõ vì sao return type chỉ mô tả **kết quả** mà không thể làm **bộ chọn method overload**.

## 7. Phân biệt overloading với overriding

Hai khái niệm dễ bị nhầm vì cả hai cùng dùng tên method.

**Overloading**: trong một class hoặc hệ phân cấp liên quan, có nhiều method **cùng tên nhưng khác tham số**. Compiler lựa chọn overload từ những method có thể áp dụng theo kiểu đối số và các quy tắc phân giải.

**Overriding**: subclass cung cấp implementation thay thế cho **instance method có chữ ký phù hợp** của superclass hoặc thực hiện hợp đồng tương ứng từ interface. Overriding có quy tắc riêng về return type, visibility và checked exceptions.

Ví dụ overriding với kiểu trả về hiệp biến:

~~~java
class Vehicle {
    Vehicle copy() {
        return new Vehicle();
    }
}

class Bicycle extends Vehicle {
    @Override
    Bicycle copy() {
        return new Bicycle();
    }
}
~~~

Method `Bicycle.copy()` trả `Bicycle`, cụ thể hơn `Vehicle`, nhưng đây là **override** vì cùng chữ ký `copy()` trong quan hệ kế thừa, **không phải một overload mới**.

### 7.1. Vì sao kiểu trả về hiệp biến được chấp nhận ở override?

Một chỗ gọi mong đợi `Vehicle` vẫn có thể nhận kết quả `Bicycle` vì `Bicycle` là một subtype của `Vehicle`. Bởi vậy Java cho phép **covariant return** với reference types khi thỏa điều kiện overriding.

Trong cùng **một class**, bạn không thể viết cả `Vehicle copy()` lẫn `Bicycle copy()` với cùng tham số, vì đây vẫn là hai khai báo method trùng chữ ký. Điều được phép là **subclass thay thế implementation** của method superclass một cách tương thích.

### 7.2. Với primitive, không có covariant return

~~~java
class Base {
    int code() {
        return 1;
    }
}

class Derived extends Base {
    // @Override
    // long code() { return 2L; } // Không hợp lệ: return int và long
}
~~~

Hai khai báo nếu bỏ comment vẫn cùng chữ ký `code()`; thay `int` thành `long` trong subclass không hợp lệ để override. Việc `int` có thể widening sang `long` **không** làm kiểu trả về primitive của override được phép thay đổi.

Trong overriding, **return type tương thích** là một điều kiện kiểm tra hợp lệ, nhưng **không phải một thành phần phân biệt hai overload**.

### 7.3. Static method hiding không phải overloading bằng return

Nếu subclass khai báo một `static` method có cùng chữ ký với static method có thể thừa kế từ superclass, đó là **method hiding** khi hợp lệ. Hiding cũng có các quy tắc về return-type compatibility và không biến khác return type thành overload. Đừng sử dụng `static` để “né” vấn đề hai method cùng chữ ký.

## 8. Overload resolution diễn ra như thế nào ở nơi gọi?

Khi viết lời gọi như `calculate(10)`, compiler xác định tên method, các method có thể truy cập, kiểu/số lượng đối số và áp dụng các quy tắc chọn method thích hợp.

Ví dụ:

~~~java
class Demo {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        System.out.println(choose(10));
        System.out.println(choose(Integer.valueOf(10)));
    }
}
~~~

Đây là chương trình chạy được trong tệp **`Demo.java`**. Với JDK 17:

~~~bash
javac Demo.java
java Demo
~~~

Stdout:

~~~text
long
Integer
~~~

Tại `choose(10)`, đối số literal `10` thuộc kiểu `int`; phép widening primitive sang `long` được xét ở pha gọi chặt trước lựa chọn cần boxing thành `Integer`. Tại `choose(Integer.valueOf(10))`, đối số có kiểu `Integer`, nên bản nhận `Integer` là kết hợp trực tiếp.

Điều này minh họa rằng overload **không đơn giản chỉ nhìn kiểu trả về**. Việc chọn overload chịu nhiều quy tắc: primitive widening, boxing/unboxing, varargs, generic inference, method applicability và most-specific. Không nên tự xây quy tắc “tên giống + compiler nhìn biến nhận” vì sẽ dự đoán sai.

### 8.1. Dùng `null` có thể gây ambiguous overload

~~~java
class NullChoice {
    static String describe(String value) {
        return "String";
    }

    static int describe(Integer value) {
        return 1;
    }

    public static void main(String[] args) {
        // describe(null); // Lỗi: ambiguous giữa String và Integer

        System.out.println(describe((String) null));
        System.out.println(describe((Integer) null));
    }
}
~~~

Nếu lưu thành **`NullChoice.java`** và chạy:

~~~bash
javac NullChoice.java
java NullChoice
~~~

Stdout của phiên bản có dòng ambiguous đang comment:

~~~text
String
1
~~~

Hai overload **hợp lệ** vì tham số lần lượt là `String` và `Integer`. Nhưng biểu thức `null` có thể chuyển sang cả hai kiểu tham chiếu không có quan hệ subtype rõ để chọn method cụ thể hơn, nên lời gọi `describe(null)` không ép kiểu là **ambiguous**.

Ngay cả khi một người viết muốn gán kết quả của lời gọi ấy vào biến `String`, **không thể tùy ý lấy return type làm “chữ ký thứ hai”** để hợp thức hóa cách gọi mơ hồ. Cách giải quyết rõ ràng là đặt tên method phù hợp hơn, dùng tham số khác, hoặc khi có chủ đích phải truyền/cast một đối số có kiểu xác định.

### 8.2. Có thể bỏ qua kết quả của method trả giá trị

~~~java
class Cleanup {
    static int compute(int n) {
        return n * 2;
    }

    static void run() {
        compute(10); // Kết quả bị bỏ qua nhưng lời gọi vẫn hợp lệ
    }
}
~~~

Ở đây, không có loại biến “nhận kết quả” nào ở caller; `compute(10)` vẫn được phân giải. Thiết kế ngôn ngữ không đòi caller phải cung cấp kiểu kết quả mong muốn cho mọi lời gọi.

## 9. Varargs và mảng: hai cách viết có thể cùng chữ ký

Một hiểu nhầm khác là tham số `String...` tạo overload khác `String[]`:

~~~java
class VarargsWrong {
    void join(String... parts) { }

    // void join(String[] parts) { } // Lỗi: cùng chữ ký khi xét
}
~~~

`String...` là cách khai báo **variable arity parameter**; về bản chất formal parameter đó có kiểu mảng `String[]`. Do vậy không thể khai báo hai method như trên trong cùng class chỉ bằng việc đổi cách viết varargs/array.

Một overload thực sự khác tham số có thể là:

~~~java
class Joiner {
    void join(String text) { }

    void join(String... parts) { }
}
~~~

`join(String)` và `join(String[])` có kiểu formal parameter khác nhau. Tuy nhiên, các lời gọi với varargs cũng có quy tắc ứng dụng và most-specific; phải xét cẩn thận nếu thêm các overload gần nhau khiến caller khó dự đoán.

**Bài học rút ra:** khi so chữ ký, hãy xét kiểu formal parameter theo quy tắc của Java, không chỉ so hình dạng text `...` và `[]`.

## 10. Generic type erasure: khác nhìn bề ngoài nhưng vẫn xung đột

Java generics khiến việc xác định các khai báo overload phức tạp hơn một chút. Xét:

~~~java
import java.util.List;

class ListService {
    void process(List<String> names) { }

    // void process(List<Integer> numbers) { }
}
~~~

Nếu bỏ comment và biên dịch, Java từ chối hai method này do **name clash / cùng erasure của chữ ký**. Hai tham số nhìn như khác nhau (`List<String>` và `List<Integer>`), nhưng khi **type erasure**, cả hai đều có erasure là `List`. Java không cho tạo hai overload kiểu này trong cùng class.

Thông báo thường có dạng:

~~~text
name clash: process(List<Integer>) and process(List<String>)
have the same erasure
~~~

Wording thực tế có thể khác theo JDK; thông điệp quan trọng là **xung đột sau erasure**.

Đây là câu chuyện *khác nhưng liên quan* với lỗi chỉ khác return type:

- `int f(int)` và `String f(int)`: trùng chữ ký nguồn vì chỉ khác return type.
- `void process(List<String>)` và `void process(List<Integer>)`: cố phân biệt bằng generic type arguments nhưng xung đột **erasure**, dù không phải chỉ khác return type.

### 10.1. Đổi tên type parameter cũng không tạo overload

~~~java
class GenericWrong {
    <T> void handle(T value) { }

    // <U> void handle(U value) { } // Sai: chữ ký tương đương
}
~~~

Hai method generic có cùng cấu trúc tham số; đổi ký hiệu `T` thành `U` không tạo hai overload. Tên type parameter mang tính cục bộ trong khai báo.

### 10.2. Cách làm API generic hợp lệ

Nếu hai thao tác mang mục đích khác nhau, hãy đặt tên cụ thể:

~~~java
import java.util.List;

class Processor {
    void processNames(List<String> names) { }

    void processIds(List<Integer> ids) { }
}
~~~

Nếu cùng một hành vi generic thật sự phù hợp, bạn có thể khai báo một method generic:

~~~java
import java.util.List;

class Printer {
    static <T> int count(List<T> items) {
        return items.size();
    }
}
~~~

Một method `count(List<T>)` phục vụ nhiều kiểu phần tử mà không cần overload theo type argument. Đừng thêm method generic chỉ để che dấu hành vi thực chất khác nhau: cùng kiểu kết quả không có nghĩa hai nhiệm vụ nghiệp vụ là một.

## 11. Return type, method signature và JVM descriptor không phải một khái niệm

Một điểm nâng cao dễ gây tranh luận: **JVM method descriptor** trong bytecode **có mô tả kiểu kết quả**, còn **Java source method signature** dùng để xác định overload **không dùng return type để phân biệt**.

Chẳng hạn, khái niệm JVM descriptor của method nhận `int` và trả `int` khác descriptor của method nhận `int` và trả `String`. Tuy nhiên, điều đó **không cho phép viết trong một Java class nguồn** hai method `int f(int)` và `String f(int)`.

Bạn có thể thấy thêm **bridge methods** do compiler phát sinh khi hỗ trợ generics hoặc covariant overriding trong bytecode. Chúng phục vụ liên kết và tương thích thực thi; đây **không phải lỗ hổng** để ứng dụng viết hai source declarations trùng chữ ký rồi coi chúng là overload.

Ở mức Java source, hãy tuân thủ định nghĩa chữ ký của JLS `8.4.2 và quy tắc method declaration. Khi debug `javac`, tập trung vào **method name, formal parameter types và erasure/subsignature** thay vì nhầm với descriptor cấp JVM.

## 12. Constructor overloading cũng dựa trên tham số

Constructor không có khai báo return type và không dùng tên method độc lập: tên constructor là tên class. Các constructor có thể overloading dựa vào số lượng/kiểu/thứ tự tham số:

~~~java
class Point {
    private final int x;
    private final int y;

    Point() {
        this(0, 0);
    }

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    Point(int coordinate) {
        this(coordinate, coordinate);
    }
}
~~~

Đây là đoạn khai báo class; ba constructor có danh sách tham số `()`, `(int, int)` và `(int)` nên cùng tồn tại hợp lệ. Không thể tạo constructor mới “chỉ khác return type”, bởi **constructor không có return type**.

Viết `void Point() { }` không phải khai báo constructor: đó là một **method tên Point** trả `void` (nếu hợp lệ trong ngữ cảnh khai báo), không thay thế constructor. Sự nhầm lẫn này thường làm người học tưởng mình đã định nghĩa constructor overload.

## 13. Cách thiết kế API khi thật sự cần nhiều kiểu kết quả

Giả sử một nguồn dữ liệu có thể trình bày dưới nhiều dạng. Có nhiều lựa chọn tốt hơn “hai method trùng tham số, khác return type”:

### 13.1. Đặt tên khác nhau theo nghĩa

~~~java
class Student {
    private final int age;

    Student(int age) {
        this.age = age;
    }

    int ageValue() {
        return age;
    }

    String ageText() {
        return age + " tuổi";
    }
}
~~~

Dễ hiểu nhất khi hai kết quả phục vụ hai mục đích khác nhau. Đọc code `ageValue()` và `ageText()` đủ để biết ý định.

### 13.2. Trả một value object chứa cả hai thông tin

~~~java
record AgeView(int value, String text) { }

class AgeService {
    AgeView describe(int age) {
        return new AgeView(age, age + " tuổi");
    }
}
~~~

Đây là method trong class và một record top-level package-private cùng ví dụ; Java 17 hỗ trợ record. Một kết quả có cả số lẫn chuỗi phù hợp nếu chúng thuộc **một thao tác mô tả**. Hãy lưu `AgeView.java` và `AgeService.java` riêng theo convention khi code phát triển lớn hơn.

### 13.3. Một kiểu kết quả tổng quát khi hợp đồng thật sự chung

Nếu operation là duy nhất và kết quả có nhiều biến thể, có thể mô hình hóa bằng interface hoặc hierarchy phù hợp, thay vì hai method chỉ khác return type. Caller sẽ phân tích kiểu kết quả theo hợp đồng.

Đừng dùng `Object` rồi ép kiểu bừa bãi chỉ để giả lập “trả `int` lúc này, `String` lúc khác” nếu có thể dùng một kiểu dữ liệu mạnh và rõ hơn.

### 13.4. Generic return hợp lệ khi đầu vào định rõ type

~~~java
class Defaults {
    static <T> T supplied(T value) {
        return value;
    }
}
~~~

Đây là một method generic duy nhất, không phải hai overload. Java suy luận `T` từ giá trị đầu vào; chẳng hạn `Defaults.supplied("A")` có thể trả `String`. Không nên coi một generic method như bằng chứng rằng Java chấp nhận hai method cùng chữ ký nhưng return type khác nhau.

## 14. Kiểm tra các trường hợp sai và đúng

| Khai báo (cùng class nếu không nói khác) | Kết luận | Giải thích |
| --- | --- | --- |
| `int f()` và `String f()` | Sai | Trùng `f()` |
| `int f(int x)` và `String f(int y)` | Sai | Trùng `f(int)`, tên tham số không quan trọng |
| `int f(int)` và `int f(long)` | Đúng | Khác kiểu tham số |
| `int f(int)` và `String f(String)` | Đúng | Khác kiểu tham số; return khác được phép |
| `void f(int, String)` và `void f(String, int)` | Đúng | Khác thứ tự kiểu tham số |
| `public int f(int)` và `private int f(int)` | Sai | Modifier truy cập không đổi chữ ký |
| `static int f(int)` và `int f(int)` | Sai | Static và instance không phân biệt overload |
| `void f(String...)` và `void f(String[])` | Sai | Varargs là dạng mảng trong chữ ký |
| `void f(List<String>)` và `void f(List<Integer>)` | Sai | Name clash do cùng erasure |
| `<T> void f(T)` và `<U> void f(U)` | Sai | Chữ ký generic tương đương |
| Superclass `Number value()` và subclass `Integer value()` | Có thể đúng | Covariant **override**, không phải overload |
| Superclass `int value()` và subclass `long value()` | Sai | Primitive return không tương thích cho override |
| `A()` và `A(int)` là constructor của class `A` | Đúng | Constructor overload nhờ tham số khác |

Các kết luận “đúng” ở bảng giả sử không có xung đột khác về generic erasure, kế thừa hoặc declaration constraints; bảng dùng để minh họa những điều kiện cơ bản liên quan trực tiếp đến return type.

## 15. Bài tập tự kiểm tra

**Câu 1.** Có thể khai báo hai method `String get()` và `int get()` trong cùng một class không? Vì sao?

**Đáp án:** Không. Cả hai có chữ ký `get()`; kiểu trả về không phải thành phần phân biệt overload.

**Câu 2.** Hai method `int calc(int a, long b)` và `String calc(long a, int b)` có phải overload hợp lệ không?

**Đáp án:** Có, vì thứ tự kiểu formal parameters khác nhau: `calc(int, long)` và `calc(long, int)`. Return type khác không phải yếu tố quyết định.

**Câu 3.** Đổi `int id(int value)` thành `long id(int number)` có tạo method overload mới được không?

**Đáp án:** Không. Chỉ return type và tên biến tham số thay đổi; chữ ký vẫn là `id(int)`.

**Câu 4.** `Parent Number create()` và `Child Integer create()` có cùng danh sách tham số, nằm trong quan hệ kế thừa. Vì sao có thể hợp lệ?

**Đáp án:** Vì `Child.create()` có thể **override** `Parent.create()` bằng covariant return type nếu thỏa các quy tắc khác của overriding. Đây không phải hai overload khác nhau.

**Câu 5.** Vì sao `void process(List<String>)` và `void process(List<Integer>)` không tạo overload hợp lệ?

**Đáp án:** Java generics dùng type erasure; cả hai parameterized `List` có erasure `List`, nên hai khai báo có name clash khi biên dịch.

**Câu 6.** `void show(String... a)` và `void show(String[] b)` có khác chữ ký không?

**Đáp án:** Không. Varargs parameter `String...` có kiểu mảng `String[]` cho mục đích chữ ký.

**Câu 7.** Trong class có `long read(long)` và `String read(String)`, việc hai kiểu trả về khác nhau có vi phạm overloading không?

**Đáp án:** Không. Hai method khác tham số, nên là overload hợp lệ; return types khác nhau không gây vấn đề.

**Câu 8.** Có thể giải quyết xung đột `int getValue()` và `String getValue()` bằng cách gán kết quả lần lượt vào `int` và `String` ở caller không?

**Đáp án:** Không. Đã có lỗi khai báo hai method trùng chữ ký. Cách sửa là đổi **tên method**, hoặc thay **tham số theo nhu cầu API thực tế**, hoặc thiết kế một kiểu kết quả rõ ràng.

**Câu 9.** Chương trình có `choose(String)` và `choose(Integer)`, một lời gọi `choose(null)` có thể lỗi ambiguous không?

**Đáp án:** Có. `null` phù hợp cả hai parameter types không liên hệ theo quan hệ subtype để chọn một overload cụ thể; có thể truyền giá trị có kiểu rõ ràng hoặc cast phù hợp.

**Câu 10.** Tại sao JVM descriptor có return type nhưng Java vẫn cấm hai source method chỉ khác return type?

**Đáp án:** Đây là **hai mức mô tả khác nhau**. Chữ ký method của Java source theo JLS dùng để quy định declaration/overloading; descriptor JVM phục vụ biểu diễn và liên kết ở bytecode. Quy tắc mức nguồn vẫn cấm hai khai báo đó.

## 16. Checklist khi gặp lỗi “method is already defined”

1. **Đọc tên method** và xác định các khai báo trùng tên trong class hoặc hệ phân cấp có liên quan.
2. **Viết lại danh sách kiểu tham số theo thứ tự**, bỏ qua tên biến tham số; ví dụ `calculate(int, String)`.
3. **Không dùng return type, modifier hay `throws`** để kỳ vọng tách hai chữ ký giống nhau.
4. **Nếu có generics**, kiểm tra erasure, type parameters và ràng buộc khai báo tương ứng.
5. **Nếu có varargs**, nhớ tham số `T...` tương ứng với kiểu mảng `T[]` khi xét chữ ký.
6. **Nếu có subclass**, xác định ý định là overriding hay overloading; kiểm tra covariant return đối với reference type khi override.
7. **Nếu muốn hai dạng dữ liệu khác nhau từ cùng đầu vào**, ưu tiên các tên method phản ánh ý nghĩa, value object hoặc hợp đồng generic phù hợp.
8. **Biên dịch lại bằng `javac`** sau khi sửa, rồi thử các lời gọi đặc trưng để phát hiện overload ambiguous hoặc chọn không như dự đoán.

### Ghi nhớ

**Nạp chồng không dựa trên kiểu trả về.** Trong Java, khi hai phương thức cùng tên, **khác số lượng, kiểu hoặc thứ tự kiểu tham số** mới là các cách phân biệt overload thường gặp. Nếu chỉ đổi `int` thành `String` ở kết quả của hai method có cùng chữ ký, compiler báo trùng phương thức. **Covariant return ở overriding** và **return type nằm trong JVM descriptor** là hai khái niệm có thật nhưng **không phủ nhận quy tắc này** trong khai báo method Java.
