# Chữ ký phương thức và những thành phần không thuộc chữ ký trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định **chữ ký phương thức** (*method signature*) theo quy tắc của Java, phân biệt với toàn bộ dòng khai báo phương thức và với lời gọi phương thức.
- Nhận ra các thành phần có ảnh hưởng đến chữ ký: **tên phương thức, tham số kiểu của phương thức nếu có và danh sách kiểu tham số hình thức** theo quy tắc đối chiếu chữ ký của Java.
- Chỉ ra các thành phần **không tạo nên chữ ký để phân biệt phương thức**: kiểu trả về, tên tham số, `throws`, access modifier, `static`/`final`, chú thích `@...` và thân phương thức.
- Dự đoán khi nào hai khai báo được xem là cùng chữ ký, khi nào **overload** hợp lệ và khi nào Java báo lỗi trùng khai báo hoặc *name clash* do generic erasure.
- Phân biệt chữ ký ở cấp **ngôn ngữ Java** với *JVM method descriptor*, và hiểu vì sao thay đổi kiểu trả về có thể tác động đến API/binary compatibility dù không phân biệt overload.
- Phân biệt overload với override, bao gồm kiểu trả về hiệp biến (*covariant return type*) và vai trò của `@Override`.

## 1. Một khai báo phương thức gồm những gì?

Xem ví dụ:

~~~java
public final class Calculator {
    public static int add(final int left, int right) throws IllegalArgumentException {
        return left + right;
    }
}
~~~

Đây là tệp `Calculator.java` hợp lệ và biên dịch được (không có `main` để chạy độc lập).

Trong một khai báo như vậy, chúng ta quan sát được nhiều thành phần:

| Thành phần | Trong ví dụ | Vai trò |
| --- | --- | --- |
| Modifier truy cập | `public` | Cho phép sử dụng phương thức từ mã truy cập được |
| Modifier khác | `static` | Phương thức thuộc lớp, không cần đối tượng để gọi |
| Kiểu trả về | `int` | Loại giá trị phương thức trả về cho bên gọi |
| **Tên phương thức** | `add` | Tên dùng để tìm phương thức |
| **Các kiểu tham số** | `int, int` | Kiểu và thứ tự các đối số được chấp nhận |
| Tên tham số | `left, right` | Tên biến dùng bên trong thân phương thức |
| Modifier tham số | `final` trên `left` | Ngăn gán lại biến tham số ấy trong thân phương thức |
| `throws` | `IllegalArgumentException` | Liệt kê loại ngoại lệ được khai báo; đây là ngoại lệ unchecked |
| Thân phương thức | `{ return left + right; }` | Mã thực thi khi gọi |

Dòng khai báo dài gồm nhiều thành phần nhưng **không phải tất cả đều tham gia vào chữ ký phương thức**. Việc phân biệt rất quan trọng khi viết nhiều phương thức trùng tên, triển khai interface, kế thừa hoặc thay đổi API.

## 2. Chữ ký phương thức theo ngôn ngữ Java

Trong Java Language Specification (JLS, mục 8.4.2), **method signature** dựa trên:

1. **Tên phương thức**.
2. **Các tham số kiểu (type parameters) của phương thức**, nếu phương thức là generic.
3. **Các kiểu tham số hình thức (formal parameter types)** theo đúng thứ tự, với các quy tắc điều chỉnh tên tham số kiểu và so sánh chữ ký trong JLS.

Với phương thức thông thường **không generic**, cách xác định rất trực quan:

~~~java
void save(String id, int amount) { }
~~~

Chữ ký có thể ghi gọn để học là **`save(String, int)`**. Hai tên `id`, `amount` không tham gia phân biệt chữ ký. Khi phân tích ở cấp đặc tả, cần nhớ generic method có thêm quy tắc về type parameters, và các phép so sánh như *same signature*, *subsignature* không đơn thuần là so chuỗi văn bản.

Với hai phương thức:

~~~java
void save(String id, int amount) { }
void save(int amount, String id) { }
~~~

Chữ ký lần lượt là **`save(String, int)`** và **`save(int, String)`**. Thứ tự kiểu tham số khác nhau nên chúng có thể cùng tồn tại dưới dạng **overload** (nếu các ràng buộc khác của lớp thỏa mãn).

Ngược lại:

~~~java
void save(String id, int amount) { }
void save(String key, int count) { }
~~~

Đây là **ví dụ cố ý không hợp lệ nếu cả hai dòng xuất hiện trong cùng một lớp**: tên parameter thay đổi, nhưng tên phương thức và thứ tự kiểu tham số vẫn giống hệt nhau. Java sẽ báo lỗi phương thức đã được khai báo.

### 2.1. Chữ ký không phải tên phương thức đơn lẻ

Nếu một lớp có:

~~~java
void print(int value) { }
void print(String value) { }
void print(String text, int count) { }
~~~

ba chữ ký có thể đọc là `print(int)`, `print(String)`, `print(String, int)`. Cùng tên `print` không đồng nghĩa là cùng chữ ký, vì danh sách kiểu tham số khác nhau. Khả năng đặt các phương thức cùng tên nhưng khác tham số được gọi là **method overloading**.

### 2.2. Số lượng và thứ tự tham số đều có ý nghĩa

Các khai báo sau khác chữ ký:

~~~java
void report() { }
void report(int page) { }
void report(int page, String format) { }
void report(String format, int page) { }
~~~

Có lần lượt 0, 1, 2, 2 tham số. Hai phương thức cuối cùng khác nhau do **thứ tự kiểu**, không phải do tên `page` hay `format`.

Nếu đảo **tên** nhưng không đổi danh sách kiểu, chữ ký không đổi:

~~~java
// Chỉ minh họa hai khai báo trùng chữ ký; không đưa cả hai vào một lớp.
void move(int x, int y) { }
// void move(int row, int column) { } // Trùng move(int, int)
~~~

Đổi tên biến tham số có thể giúp mã dễ hiểu hơn, nhưng không tạo một overload mới.

## 3. Những thành phần KHÔNG thuộc chữ ký phân biệt phương thức

| Thành phần | Có phân biệt chữ ký Java không? | Ví dụ / hệ quả |
| --- | --- | --- |
| **Tên phương thức** | **Có** | `sum(int)` khác `count(int)` |
| **Danh sách kiểu tham số theo thứ tự** | **Có** | `sum(int)` khác `sum(long)` |
| **Type parameters của generic method** | **Được xét theo JLS** | So sánh có bước điều chỉnh tương ứng các type variables |
| Kiểu trả về | **Không** | `int get()` và `String get()` không thể cùng khai báo chỉ nhờ khác kiểu trả về |
| Tên tham số | **Không** | `f(int age)` và `f(int years)` trùng chữ ký |
| Modifier tham số như `final` | **Không** | `f(final int x)` và `f(int x)` trùng chữ ký |
| `throws` | **Không** | `read() throws IOException` và `read() throws Exception` không tạo overload |
| `public`, `private`, `protected` | **Không** | Đổi quyền truy cập không tạo phương thức cùng tên/tham số thứ hai |
| `static`, `final`, `abstract`, `synchronized`, `native` và modifier phương thức khác | **Không** | `static` và instance method không thể trùng chữ ký trong cùng lớp |
| Annotation như `@Deprecated`, `@Override` | **Không** | Annotation cung cấp metadata/kiểm tra, không tạo overload |
| Tên biến local, thân method và thuật toán | **Không** | Thay `return a + b` bằng phép tính khác không tạo chữ ký mới |
| Danh sách tham số generic của **kiểu trả về** | **Không** | `List<String> load()` và `List<Integer> load()` không tạo overload khi cùng tham số hình thức |

**Lưu ý:** “Không thuộc chữ ký” **không có nghĩa là không quan trọng**. Ví dụ kiểu trả về quyết định kiểm tra kiểu của biểu thức nhận kết quả, `throws` ảnh hưởng quy tắc xử lý checked exceptions, access modifier quyết định quyền gọi, và `static` quyết định cách gắn phương thức với lớp. Chúng có thể ảnh hưởng tính hợp lệ của **override**, tương thích API hoặc khả năng gọi phương thức; chỉ riêng việc thay đổi chúng không làm xuất hiện một chữ ký overload khác.

## 4. Vì sao không overload chỉ bằng kiểu trả về?

Ví dụ hai khai báo sau **không biên dịch khi cùng đặt trong một lớp**:

~~~java
// Mã chủ ý không hợp lệ; chỉ dùng để phân tích.
// class InvalidReturns {
//     int convert(String text) { return Integer.parseInt(text); }
//     long convert(String text) { return Long.parseLong(text); }
// }
~~~

Cả hai đều có chữ ký `convert(String)`. Kiểu trả về `int` hay `long` không giúp phân biệt chúng; lỗi là khai báo cùng chữ ký trong một lớp.

Một suy nghĩ sai thường gặp là “compiler sẽ chọn phương thức `int convert(String)` khi gán vào `int`, và chọn `long convert(String)` khi gán vào `long`”. Java **không cho phép xây dựng overload theo cách đó**. Việc chọn overload phụ thuộc các quy tắc về tên, các đối số, khả năng áp dụng, mức độ cụ thể, generic inference và ngữ cảnh khi thích hợp; **không** biến hai khai báo trùng chữ ký thành hợp lệ chỉ vì nơi nhận kết quả có kiểu khác nhau.

Giải pháp thực tế:

- Chọn **tên khác nhau** theo ý nghĩa: `parseInt(String)` và `parseLong(String)`.
- Hoặc thiết kế **tham số khác nhau một cách có ý nghĩa**, ví dụ `convert(String)` và `convert(String, int radix)`, nếu thực sự là hai cách gọi hợp lý.
- Không thêm tham số vô nghĩa chỉ để compiler cho phép overload.

Cũng không thể dùng `void` so với kiểu trả về có giá trị để phân biệt:

~~~java
// Không hợp lệ nếu đặt hai khai báo vào cùng một lớp:
// void refresh() { }
// boolean refresh() { return true; }
~~~

Cả hai đều là `refresh()`.

## 5. `throws` và tên tham số không đổi chữ ký

Xét hai khai báo:

~~~java
// Hai dòng sau không được đồng thời xuất hiện trong cùng một lớp:
// void read(String path) throws java.io.IOException { }
// void read(String fileName) throws java.lang.Exception { }
~~~

Hai chữ ký đều là `read(String)` dù:

- `path` đổi thành `fileName`.
- `throws IOException` đổi thành `throws Exception`.

`throws` mô tả hợp đồng ngoại lệ theo các quy tắc của Java. Khi một phương thức **override** phương thức của lớp cha hoặc triển khai interface, ngoại lệ checked được phép khai báo có thể bị giới hạn bởi khai báo bị override; vậy nên `throws` rất quan trọng đối với tính hợp lệ của override, dù không phải thành phần tạo overload.

Ví dụ, nếu interface khai báo `void read() throws IOException;`, lớp triển khai được phép không khai báo checked exception nào, hoặc khai báo checked exception phù hợp với ràng buộc của Java. Nhưng đổi sang `throws Exception` rộng hơn có thể gây lỗi biên dịch khi override. Unchecked exceptions có quy tắc khác.

## 6. Modifier và annotation không phân biệt overload

Hai phương thức sau không thể cùng xuất hiện trong một lớp:

~~~java
// Mã minh họa lỗi:
// static void reset(int value) { }
// void reset(int value) { }
~~~

Cả hai có chữ ký `reset(int)`; thêm/bỏ `static` không tạo một phương thức overload mới.

Tương tự, phương thức `public int size()` không trở thành chữ ký khác khi đổi thành `private int size()`, `protected int size()`, hay thêm `final`. Đó là thay đổi hợp đồng truy cập/hành vi, và có những quy tắc riêng đối với kế thừa hoặc ghi đè.

Annotation chẳng hạn `@Deprecated` đặt trên phương thức cũng không đổi chữ ký. `@Override` yêu cầu compiler kiểm tra tính đúng đắn khi ghi đè/triển khai; annotation này không làm một phương thức trở thành override nếu tên/kiểu tham số thực tế không phù hợp.

## 7. Varargs và tham số mảng: không phải hai chữ ký khác nhau

Khai báo **variable arity parameter** dùng `...` để cho phép truyền số lượng đối số phù hợp linh hoạt tại vị trí tham số cuối. Về chữ ký tương ứng, `String...` và `String[]` không tạo hai overload độc lập:

~~~java
// Hai cách khai báo cùng chữ ký, không được dùng cùng lúc:
// void send(String... messages) { }
// void send(String[] messages) { }
~~~

Cả hai được xử lý với dạng tham số mảng `String[]` trong chữ ký Java. Khác biệt là **khả năng gọi** mà cú pháp varargs mang lại: `send("A", "B")` được cho phép với khai báo varargs; còn với khai báo chỉ nhận mảng, cần truyền một mảng phù hợp. Một phương thức varargs cũng có thể nhận một mảng như đối số.

Ví dụ hợp lệ, lưu trong tệp **`VarargsDemo.java`**:

~~~java
public class VarargsDemo {
    static int count(String... values) {
        return values.length;
    }

    public static void main(String[] args) {
        System.out.println(count());
        System.out.println(count("A", "B"));
        System.out.println(count(new String[] {"X", "Y", "Z"}));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac VarargsDemo.java
java VarargsDemo
~~~

Kết quả:

~~~text
0
2
3
~~~

Ở đây chỉ có **một** phương thức `count(String...)`; cả ba lời gọi đều được xử lý theo khả năng áp dụng của phương thức đó. Khi có nhiều overload và varargs, Java ưu tiên các pha xét lời gọi đối số cố định trước pha xét varargs theo các quy tắc overload resolution. Đừng suy ra từ chữ `...` rằng JVM có một kiểu tham số hoàn toàn khác với mảng.

## 8. Generic method: type parameters, cùng chữ ký và erasure

Cách nói “chữ ký chỉ là tên + các kiểu tham số” là cách học nhanh cho phương thức không generic. Với generic methods, JLS 8.4.2 còn xét **type parameters của chính phương thức** và định nghĩa quy tắc *same signature* sau khi điều chỉnh các type parameters tương ứng.

Ví dụ:

~~~java
// Chỉ dùng để so sánh, không khai báo đồng thời:
<T> void accept(T item) { }
// <U> void accept(U value) { }
~~~

Dù dùng tên `T` hay `U`, hai khai báo vẫn tương ứng cùng chữ ký theo phép đổi tên/điều chỉnh type parameters của Java. Đổi tên type variable không tạo overload.

Một generic method có thể khai báo như:

~~~java
public static <T> T identity(T value) {
    return value;
}
~~~

Đoạn này là khai báo phương thức `static` hợp lệ nếu đặt trong lớp thích hợp; ở đây `<T>` là **type parameter của method**, `T` trước tên `identity` là kiểu trả về và `T value` là kiểu tham số. Chính sự tồn tại và đối chiếu type parameter declaration khác với việc thay đổi tên tham số `value` đơn thuần.

### 8.1. Erasure gây name clash khi tưởng rằng có thể overload

Xét hai khai báo:

~~~java
// KHÔNG hợp lệ khi đặt chung một lớp:
// void process(java.util.List<String> items) { }
// void process(java.util.List<Integer> items) { }
~~~

Java generics sử dụng **type erasure**: ở mức tương ứng phục vụ kiểm tra name clash/bytecode, cả hai kiểu tham số `List<String>` và `List<Integer>` đều có erasure là `List`. Vì vậy hai khai báo này không thể được overload chỉ nhờ đối số kiểu của cùng một kiểu generic.

Tương tự, đổi `List<String>` thành `List<Long>`, hay đổi tên biến `items`, vẫn không giải quyết được vấn đề. Có thể đặt tên phương thức khác (ví dụ `processNames`, `processIds`) hoặc thay đổi thiết kế API theo dữ liệu thật sự cần phân biệt.

**Phân biệt hai nguyên nhân:** lỗi do *same signature* và lỗi *name clash* có thể được compiler trình bày bằng những thông báo khác nhau. Trong trường hợp generic, ta cần xét đầy đủ **subsignature/override-equivalence và erasure**, không chỉ nhìn xem chuỗi ký tự bên trong dấu `<...>` có khác nhau hay không.

### 8.2. Đừng nhầm generic parameter với generic return type

~~~java
// Không hợp lệ nếu xuất hiện cùng lúc trong một lớp:
// java.util.List<String> load() { return java.util.List.of("A"); }
// java.util.List<Integer> load() { return java.util.List.of(1); }
~~~

Cả hai đều có tên và danh sách tham số tương ứng là `load()`. Sự khác biệt nằm **chỉ ở kiểu trả về**, nên không tạo hai overload. Một nơi gọi mong nhận `List<String>` và nơi khác mong nhận `List<Integer>` không thể dùng để định nghĩa hai phương thức trùng chữ ký như vậy.

## 9. Ví dụ đầy đủ: overload hợp lệ và override hiệp biến

Lưu chương trình dưới tên **`MethodSignatureDemo.java`**:

~~~java
public class MethodSignatureDemo {
    static class Formatter {
        public String format(int value) {
            return "int=" + value;
        }

        public String format(String value) {
            return "text=" + value;
        }

        public String format(String value, int count) {
            return value.repeat(count);
        }

        public Number score(int value) {
            return value * 10;
        }
    }

    static final class AdvancedFormatter extends Formatter {
        @Override
        public Integer score(int value) {
            return value * 100;
        }
    }

    public static void main(String[] args) {
        Formatter formatter = new Formatter();

        System.out.println(formatter.format(7));
        System.out.println(formatter.format("Java"));
        System.out.println(formatter.format("Hi", 2));

        Formatter base = new Formatter();
        Formatter child = new AdvancedFormatter();

        System.out.println("base score=" + base.score(2));
        System.out.println("child score=" + child.score(2));
        System.out.println("child text=" + child.format("OK"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MethodSignatureDemo.java
java MethodSignatureDemo
~~~

Output chính xác:

~~~text
int=7
text=Java
HiHi
base score=20
child score=200
child text=text=OK
~~~

**Giải thích chữ ký của từng phương thức:**

| Khai báo | Chữ ký Java | Quan hệ |
| --- | --- | --- |
| `format(int value)` | `format(int)` | Overload với `format(String)` |
| `format(String value)` | `format(String)` | Overload với `format(int)` |
| `format(String value, int count)` | `format(String, int)` | Overload vì khác số lượng/thứ tự kiểu tham số |
| `Formatter.score(int value)` | `score(int)` | Phương thức ở lớp cha |
| `AdvancedFormatter.score(int value)` | `score(int)` | **Override** phương thức của lớp cha |

Tại `AdvancedFormatter.score(int)`, kiểu trả về đổi từ `Number` sang `Integer`, nhưng chữ ký vẫn là `score(int)`. Đây là **covariant return** hợp lệ: `Integer` là kiểu con của `Number`. Khi gọi `child.score(2)` qua biến kiểu `Formatter`, triển khai override trong đối tượng `AdvancedFormatter` được chọn và trả `200`.

Nếu đổi kiểu trả về ở lớp con sang `String`, chỉ dựa trên cùng chữ ký `score(int)` sẽ **không** biến nó thành overload; compiler sẽ báo lỗi không tương thích kiểu trả về của phương thức override.

Đối với overload `format(int)`, `format(String)`, `format(String,int)`, compiler quyết định khai báo phù hợp dựa trên đối số của lời gọi. Khi chạy, với phương thức instance có override, dispatch động chọn implementation tương ứng. Đó là hai cơ chế liên quan nhưng khác nhau.

## 10. Overload, override và các ràng buộc liên quan đến chữ ký

### 10.1. Overload

**Overload** là các phương thức cùng tên nhưng khác danh sách tham số đủ để được coi là các khai báo hợp lệ trong cùng lớp/ngữ cảnh kế thừa. Ví dụ:

~~~java
void log(int code) { }
void log(String message) { }
void log(String message, int level) { }
~~~

Đây là các method declarations minh họa trong một lớp, không có `main`. Chúng có chữ ký khác nhau.

Những thay đổi sau **không phải cách overload**:

~~~java
// Các cặp dưới đây là mã cố ý không hợp lệ nếu khai báo chung:
// int size() { return 0; }
// long size() { return 0; }

// void update(int x) { }
// void update(int y) throws RuntimeException { }

// static void clear() { }
// void clear() { }
~~~

Điểm chung: mỗi cặp có **tên và kiểu tham số tương ứng trùng nhau**; khác return type, tên parameter, `throws` hoặc modifier không cứu được việc trùng.

### 10.2. Override

**Override** áp dụng với phương thức instance trong quan hệ kế thừa/triển khai khi thỏa quy tắc của Java về chữ ký, subsignature, truy cập, return type và exceptions. Một phương thức ở lớp con có thể override phương thức lớp cha với chữ ký phù hợp, đồng thời:

- Không được giảm quyền truy cập của phương thức bị override theo quy tắc Java.
- Kiểu trả về phải **return-type-substitutable**: có thể là cùng kiểu, kiểu tham chiếu hiệp biến phù hợp hoặc những trường hợp generic được đặc tả cho phép; không thể tùy tiện thay đổi kiểu nguyên thủy.
- Không thể khai báo checked exceptions mới/rộng hơn trái với ràng buộc của phương thức bị override.
- Không thể override `final` instance method.
- Không gọi hiện tượng này là overload chỉ vì đổi chú thích `@Override` hoặc tên parameter.

**Static methods không được override bằng dispatch động như instance methods**: chúng có thể bị *hide* (che giấu) trong lớp con theo các điều kiện Java cho phép. Nếu cố dùng một phương thức instance để override một phương thức static cùng chữ ký của lớp cha, hoặc ngược lại, sẽ gây lỗi. Đây là khác biệt hành vi, không phải chữ ký bổ sung.

### 10.3. Một trường hợp tinh tế: subsignature và tương thích mã generic

JLS định nghĩa **subsignature**: hai chữ ký có thể trùng nhau, hoặc chữ ký này phù hợp với **erasure** của chữ ký kia theo quy tắc cụ thể. Cơ chế đó giúp duy trì một số kiểu override khi API được generic hóa, mà không phải mọi trường hợp ghi đè đều đòi văn bản kiểu tham số giống nhau hoàn toàn.

Khi gặp generic methods, raw types và kế thừa, đừng rút gọn quy tắc thành “chỉ cần cùng tên và cùng số tham số”. Phải xét **kiểu, thứ tự, các type parameters và các quy tắc subsignature/override-equivalence**.

## 11. Method declaration, method signature, method call và JVM descriptor

Bốn khái niệm này thường bị gọi chung là “chữ ký”, nhưng khác nhau:

| Khái niệm | Diễn giải | Ví dụ |
| --- | --- | --- |
| Method declaration | Toàn bộ khai báo gồm modifier, type parameters, return type, tên, parameters, `throws`, thân | `public int add(int x,int y) { return x+y; }` |
| Java method signature | Khái niệm ngôn ngữ dùng để so chữ ký, overload và các quy tắc override | `add(int,int)` (cách ghi ngắn cho method không generic) |
| Method invocation | Biểu thức gọi phương thức, có đối số thực tế, có thể có receiver | `calculator.add(1,2)` |
| JVM method descriptor | Biểu diễn kiểu tham số **và kiểu trả về** trong JVM class file, không phải quy tắc overload của Java source | `(II)I` ứng với hai tham số `int`, trả `int` |

Ví dụ:

~~~java
public int add(int x, int y) {
    return x + y;
}
~~~

Đây là đoạn phương thức minh họa bên trong class. Ở cấp source Java, cách mô tả chữ ký là `add(int,int)`. Ở cấp JVM, **method descriptor** `(II)I` biểu diễn hai parameter `int` và return `int`. Lưu ý *descriptor* không tự chứa **tên phương thức**: trong cấu trúc tham chiếu phương thức JVM, tên được lưu thành thành phần riêng.

Vì vậy, câu “kiểu trả về không thuộc chữ ký Java” **không mâu thuẫn** với việc kiểu trả về xuất hiện trong JVM descriptor hoặc trong nhiều định dạng báo cáo API. Trình biên dịch đôi khi sinh **bridge methods** để duy trì ngữ nghĩa generic/covariant returns ở bytecode; điều đó không cho phép lập trình viên định nghĩa overload chỉ bằng kiểu trả về trong một lớp Java.

Các tài liệu/tooling cũng đôi khi dùng từ “signature” theo nghĩa rộng hơn, hoặc nói đến **generic signature attribute** trong class file. Khi thảo luận về trùng khai báo/overloading ở Java source, phải áp dụng **định nghĩa chữ ký Java**; khi bàn về bytecode, cần ghi rõ đang nói đến JVM descriptor hay một dạng metadata khác.

### 11.1. `javap` cho thấy descriptor có return type

Với tệp `Calculator.java` ở phần đầu, bạn có thể thử:

~~~bash
javac Calculator.java
javap -s Calculator
~~~

Công cụ `javap -s` sẽ hiển thị method descriptors, trong đó phương thức `add(int,int)` có descriptor **`(II)I`**. Đây là lệnh thăm dò bytecode; trình bày của `javap` có thể gồm constructor và các dòng khác tùy phiên bản công cụ. Không nên nhầm descriptor với cấu trúc dùng để định nghĩa overload trong Java source.

## 12. Các tình huống dễ nhầm khi chọn overload

### 12.1. Kiểu tham số là yếu tố chính, nhưng giải quyết lời gọi có nhiều quy tắc

Chẳng hạn một lớp có cả `void f(int x)` và `void f(long x)`. Lời gọi `f(5)` thường chọn `f(int)` vì literal `5` có kiểu `int` và có phương thức áp dụng trực tiếp. Với `f(5L)`, compiler chọn `f(long)`. Với generic, boxing/unboxing, widening, varargs và các overload cùng áp dụng, quá trình chọn còn phức tạp hơn.

Cần phân biệt:

1. **Có thể khai báo hai phương thức hợp lệ không?** Đây là bài toán chữ ký/erasure và các ràng buộc khai báo.
2. **Lời gọi cụ thể sẽ chọn phương thức nào?** Đây là bài toán overload resolution dựa trên kiểu/biểu thức đối số và bối cảnh.
3. **Triển khai override nào chạy lúc runtime?** Đây là dispatch động với instance methods (khi thỏa điều kiện override).

Ba câu hỏi có liên hệ nhưng không tương đương.

### 12.2. `null` có thể tạo lời gọi mơ hồ

Ví dụ có hai overload hợp lệ:

~~~java
void send(String value) { }
void send(Integer value) { }
~~~

Đặt trong một lớp, hai phương thức này khác kiểu tham số. Tuy nhiên, lời gọi `send(null)` gây lỗi **ambiguous method call** do cả `String` và `Integer` đều chấp nhận `null`, nhưng không kiểu nào cụ thể hơn kiểu còn lại theo quy tắc chọn overload thích hợp. Có thể chỉ rõ ý định bằng `send((String) null)` hoặc `send((Integer) null)`, nhưng thực tế API nên tránh những overload làm lời gọi không rõ ràng nếu chúng thường nhận `null`.

### 12.3. Autoboxing không phải thay đổi chữ ký

Hai overload `f(int)` và `f(Integer)` có chữ ký khác nhau, do `int` là primitive, `Integer` là reference type. Java có thể thực hiện boxing/unboxing trong một số lời gọi, nhưng không vì thế hai chữ ký trở thành một. Nếu tự xây dựng ví dụ gọi, cần xét các pha giải quyết overload thay vì suy ra từ khả năng boxing đơn giản.

### 12.4. Generic type arguments không tự tạo overload

`List<String>` và `List<Integer>` đều có erasure là `List`. Tạo hai phương thức chỉ khác phần generic argument sẽ dẫn đến name clash. Nếu muốn xử lý nội dung kiểu khác nhau, cân nhắc một phương thức generic, hai tên phương thức mô tả rõ chức năng hoặc tham số phân biệt hợp lệ có ý nghĩa.

## 13. Cách kiểm tra chữ ký khi đọc một phương thức

Khi gặp khai báo dài, có thể làm theo trình tự:

1. **Tìm tên phương thức** (sau return type, trước dấu `(` của parameter list).
2. **Xác định type parameters của chính method**, nếu có (ví dụ `<T extends Number>` xuất hiện trước return type).
3. **Ghi danh sách kiểu tham số theo đúng thứ tự**: `(String id, int count)` thành `(String,int)`. Đối chiếu kiểu đầy đủ, không chỉ tên đơn giản khi package khác nhau.
4. **Bỏ qua tên parameter**, modifier của parameter, các annotation không liên quan tới phân biệt chữ ký.
5. **Không dùng return type, `throws`, modifier cấp method hoặc thân method để phân biệt overload**.
6. **Nếu có generic, varargs, kế thừa**, xét thêm erasure, subsignature, override-equivalence và array/varargs equivalence theo quy tắc Java.
7. **Sau khi biết các khai báo hợp lệ**, mới xét lời gọi cụ thể và quy tắc overload resolution hoặc dynamic dispatch.

Ví dụ:

~~~java
public static <T extends Number> T pick(
        final T first,
        T second
) throws IllegalArgumentException {
    return first;
}
~~~

Đây là phương thức minh họa hợp lệ trong class thích hợp. Các thành phần cần nhìn khi xét chữ ký là: tên `pick`, type parameter `T extends Number`, kiểu hai formal parameters `T, T`. Các chi tiết `public static`, `final` của `first`, tên `first/second`, return type `T` và `throws IllegalArgumentException` không tự tạo chữ ký mới. Với generic method, không được thay `T` bằng kiểu bất kỳ trong chữ ký rồi kết luận hai khai báo khác nhau; phải tuân thủ quy tắc type parameter adaptation và erasure.

## 14. Lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Compiler báo phương thức đã được định nghĩa | Hai khai báo có cùng chữ ký trong cùng lớp | Thay đổi tên hoặc danh sách kiểu tham số có ý nghĩa; không chỉ đổi return type/tên biến |
| Mong phân biệt `get(): int` và `get(): long` | Return type không phân biệt chữ ký Java | Dùng các tên mô tả khác nhau hoặc thiết kế API lại |
| Hai phương thức khác `throws` vẫn xung đột | Exception declaration không thuộc chữ ký | Chọn một hợp đồng `throws` đúng với chức năng hoặc thay đổi API |
| Dùng `f(String...)` và `f(String[])` cùng lớp | Varargs tương ứng với tham số mảng về chữ ký | Chỉ giữ một khai báo theo cách gọi mong muốn |
| Hai overload chỉ khác `List<String>` và `List<Integer>` bị lỗi | Type erasure dẫn đến name clash | Đổi tên rõ ràng, dùng một method generic hoặc thiết kế tham số khác có ý nghĩa |
| `@Override` báo không ghi đè | Sai tên/kiểu tham số hoặc vi phạm điều kiện override | So sánh chữ ký và các quy tắc return/throws/access |
| Đổi `static` thành instance mà mong thêm overload | Modifier không phân biệt chữ ký | Giữ một khai báo hoặc thay đổi API; không coi static/instance là hai chữ ký |
| `send(null)` mơ hồ | Hai overload có kiểu tham chiếu không so sánh được về độ cụ thể | Chỉ rõ kiểu bằng cast khi cần; cân nhắc thiết kế tránh mơ hồ |
| Thấy `(II)I` ở `javap` rồi nghĩ return type thuộc Java method signature | Nhầm JVM descriptor với chữ ký ngôn ngữ Java | Phân biệt cấp source và cấp bytecode |
| Đổi tên parameter rồi tưởng thay API overload | Parameter names không phân biệt chữ ký | Đổi kiểu/số lượng/thứ tự kiểu nếu thực sự cần overload mới |
| Hai phương thức cùng tên khác tham số nhưng lời gọi vẫn sai | Khai báo overload hợp lệ không bảo đảm mọi lời gọi đều có ứng viên duy nhất | Kiểm tra kiểu đối số, boxing, varargs, generic inference và ambiguity |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Hai khai báo `int total(int a, int b)` và `long total(int x, int y)` có được cùng xuất hiện trong một lớp Java không?  
**Đáp án:** Không. Cả hai có chữ ký `total(int,int)`; chỉ khác return type và tên tham số.

**Câu 2.** `void send(String id, int count)` và `void send(int count, String id)` có cùng chữ ký không?  
**Đáp án:** Không. Lần lượt là `send(String,int)` và `send(int,String)`. Thứ tự kiểu tham số khác nhau nên có thể overload.

**Câu 3.** Hai khai báo `void load() throws IOException` và `void load() throws SQLException` có overload được không?  
**Đáp án:** Không. `throws` không tạo chữ ký khác; cả hai là `load()`.

**Câu 4.** `void log(String[] items)` và `void log(String... items)` có tạo hai chữ ký khác nhau không?  
**Đáp án:** Không. Chúng trùng chữ ký tương ứng dạng mảng `log(String[])`.

**Câu 5.** Vì sao `void consume(List<String>)` và `void consume(List<Integer>)` không overload được?  
**Đáp án:** Cả hai có erasure của tham số là `List` và gây xung đột tên ở cấp Java; kiểu generic argument không đủ để tạo overload độc lập.

**Câu 6.** Một phương thức lớp con trả `Integer` để override phương thức cha trả `Number` có nhất thiết sai vì kiểu trả về khác nhau không?  
**Đáp án:** Không. Với cùng chữ ký phù hợp, `Integer` có thể là kiểu trả về hiệp biến hợp lệ của `Number`, nếu các ràng buộc override khác cũng thỏa mãn.

**Câu 7.** `public static int f(int x)` và `private int f(int y)` khác chữ ký không?  
**Đáp án:** Không. Đều là `f(int)`. Modifier `public/private/static`, tên `x/y` và kiểu trả về không phân biệt chữ ký.

**Câu 8.** `javap -s` hiển thị descriptor `(II)I`. Chữ `I` cuối là gì, và nó có khiến kiểu trả về trở thành thành phần phân biệt chữ ký source Java không?  
**Đáp án:** `I` cuối là kiểu trả về `int` trong JVM descriptor. Đây là cấu trúc bytecode khác chữ ký Java source, nên không cho phép overload chỉ bằng kiểu trả về.

**Câu 9.** Vì sao chỉ so sánh số tham số không đủ để xác định chữ ký?  
**Đáp án:** Vì **kiểu, thứ tự kiểu và quy tắc generic** cũng phải xét. `f(int)` và `f(String)` có cùng số tham số nhưng khác chữ ký.

## Tổng kết

Khi xem một phương thức Java, đừng nhầm **toàn bộ khai báo** với **chữ ký**. Với phương thức không generic, quy tắc thực hành là **tên phương thức + danh sách kiểu tham số theo đúng thứ tự**; với generic methods, phải xét thêm type parameters theo JLS và các quy tắc điều chỉnh tên/erasure. **Kiểu trả về, tên tham số, `throws`, access modifier, `static`, `final`, annotation và thân phương thức không phân biệt chữ ký để tạo overload**. Chữ ký liên quan trực tiếp đến việc hợp lệ khi khai báo, overload và override; lựa chọn overload tại lời gọi và descriptor của JVM là những vấn đề khác cần được xem xét riêng.
