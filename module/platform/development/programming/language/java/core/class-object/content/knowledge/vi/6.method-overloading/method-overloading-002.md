# Phân biệt chữ ký phương thức theo số lượng, kiểu và thứ tự tham số trong Java

Trong Java, **nạp chồng phương thức (method overloading)** cho phép khai báo nhiều phương thức **cùng tên** nhưng có **chữ ký (method signature) khác nhau**. Ba dấu hiệu quan trọng nhất để phân biệt các overload trong thực hành là **số lượng tham số**, **kiểu tham số** và **thứ tự kiểu tham số**. Tên tham số, kiểu trả về hay mệnh đề `throws` không thể tự tạo ra một overload mới.

Bài này giúp đọc chữ ký, dự đoán phương thức được chọn khi gọi, phân tích lỗi trùng khai báo và lỗi mơ hồ, đồng thời hiểu giới hạn do mảng, varargs và generic. Ví dụ chạy với **Java 17 trở lên**.

## 1. Chữ ký phương thức là gì?

Xét ba khai báo đặt trong cùng một lớp:

~~~java
void print(int value) { }
void print(String value) { }
void print(int value, String label) { }
~~~

Ba phương thức đều tên `print`, nhưng danh sách kiểu tham số lần lượt là:

~~~text
print(int)
print(String)
print(int, String)
~~~

Chúng có thể cùng tồn tại vì chữ ký khác nhau.

Theo Java Language Specification (JLS), chữ ký của phương thức bao gồm **tên**, các **tham số kiểu nếu có** và **danh sách kiểu của các tham số hình thức** theo quy tắc thích ứng tham số kiểu. Với các phương thức không generic thông thường, cách đọc nhanh và chính xác là:

~~~text
chữ ký ≈ tên phương thức + số lượng và thứ tự các kiểu tham số
~~~

Dấu `≈` nhắc rằng cú pháp generic và quy tắc *subsignature* có chi tiết bổ sung; không nên giản lược quy tắc JLS thành một chuỗi ký tự so sánh thô.

**Những thành phần không được dùng để tạo khác biệt chữ ký** gồm: kiểu trả về, tên các biến tham số, tên tham số kiểu generic đơn thuần, mức truy cập, `static`, `final`, `synchronized` và `throws`. Một số thành phần vẫn ảnh hưởng quyền gọi hay override, nhưng không biến hai phương thức trùng chữ ký thành hai overload hợp lệ.

| Khai báo | Chữ ký dễ đọc | Có thể khác với `process(int)`? |
| --- | --- | --- |
| `void process(int x)` | `process(int)` | Chính chữ ký mốc |
| `void process(int x, int y)` | `process(int, int)` | Có: số lượng khác |
| `void process(long x)` | `process(long)` | Có: kiểu khác |
| `void process(String x)` | `process(String)` | Có: kiểu khác |
| `int process(int number)` | `process(int)` | Không: chỉ đổi kiểu trả về/tên tham số |
| `static void process(int x)` | `process(int)` | Không: chỉ thêm `static` |

Các dòng trong bảng là **những khai báo để so sánh**, không phải toàn bộ mã có thể đặt chung trong một lớp.

## 2. Khác số lượng tham số

Cách đơn giản nhất là dùng cùng tên nhưng khác **số tham số hình thức**:

~~~java
class Formatter {
    String format() {
        return "(empty)";
    }

    String format(String text) {
        return text;
    }

    String format(String text, int count) {
        return text.repeat(count);
    }
}
~~~

Ba chữ ký là `format()`, `format(String)`, `format(String, int)`. Chúng hợp lệ vì có lần lượt 0, 1 và 2 tham số. Trong Java 17, `String.repeat(int)` lặp chuỗi theo `count`, ném `IllegalArgumentException` khi `count` âm.

Có thể gọi `formatter.format()`, `formatter.format("A")` hoặc `formatter.format("A", 3)` với một đối tượng `Formatter`. Compiler xét **số lượng** và **kiểu đối số** để tìm phương thức phù hợp.

**Không nhất thiết** mỗi phương thức cùng tên phải làm một thao tác có ý nghĩa khác hẳn. Overloading thường cung cấp các cách nhập dữ liệu tiện lợi để thực hiện cùng một ý nghĩa, chẳng hạn `format()` dùng giá trị mặc định và `format(String, int)` cho phép chỉ định thêm tham số.

Đoạn `Formatter` là **một lớp minh họa**, không có `main`.

## 3. Cùng số lượng nhưng khác kiểu tham số

Xét:

~~~java
static String describe(int number) {
    return "int: " + number;
}

static String describe(long number) {
    return "long: " + number;
}

static String describe(String text) {
    return "text: " + text;
}
~~~

Cả ba phương thức cùng tên và nhận **một tham số**, nhưng `int`, `long` và `String` là những kiểu tham số khác nhau:

~~~text
describe(int)
describe(long)
describe(String)
~~~

Đây là các overload hợp lệ khi đặt trong cùng một lớp, vì chữ ký khác nhau. Cách gọi `describe(7)` thường chọn `int`, `describe(7L)` chọn `long`, còn `describe("A")` chọn `String`.

**Phân biệt kiểu primitive và kiểu wrapper:** `int` khác `Integer`, `long` khác `Long`. Ví dụ `m(int)` và `m(Integer)` là hai overload hợp lệ; phép boxing/unboxing có thể tham gia chọn phương thức ở bước giải quyết lời gọi, chứ không xóa sự khác nhau của hai chữ ký.

**Kiểu khai báo của tham số là cơ sở**, không phải tên tham số. Viết `int points`, `int score` hay `int number` đều tạo cùng một kiểu tham số `int`.

## 4. Cùng kiểu thành phần nhưng khác thứ tự tham số

Thứ tự kiểu là một phần danh sách tham số hình thức:

~~~java
static String convert(int quantity, long price) {
    return "int-long";
}

static String convert(long price, int quantity) {
    return "long-int";
}
~~~

Hai chữ ký là `convert(int, long)` và `convert(long, int)`. Chúng khác nhau vì vị trí của `int` và `long` được hoán đổi, dù **cùng có hai tham số** và cùng sử dụng hai kiểu.

Điều này **không bảo đảm mọi lời gọi đều được compiler chọn duy nhất**:

~~~java
convert(1, 2L);  // int, long -> overload thứ nhất
convert(1L, 2);  // long, int -> overload thứ hai
convert(1, 2);   // lỗi: có thể mơ hồ giữa hai overload
~~~

Các dòng trên là minh họa trong phạm vi có hai overload `convert`; lời gọi cuối được cố ý viết để chỉ ra lỗi. Với `convert(1, 2)`, phương thức thứ nhất khớp tham số `int` đầu và cần nới rộng `int` thành `long` ở tham số sau; phương thức thứ hai có sự tương ứng ngược lại. Không phương thức nào cụ thể hơn phương thức kia trên **toàn bộ danh sách tham số**, nên lời gọi mơ hồ.

Vì vậy thay đổi thứ tự tham số có thể tạo chữ ký hợp lệ nhưng cũng dễ làm API khó dùng. Các tham số cùng loại bị tráo vị trí còn nguy hiểm hơn: nếu hai tham số đều `String`, đổi ý nghĩa `source` và `destination` **không tạo chữ ký mới** và compiler không tự phát hiện việc người gọi đảo chúng.

## 5. Những thứ không phân biệt được overload

### Đổi tên biến tham số

~~~java
void update(int amount) { }
void update(int value) { }
~~~

**Không hợp lệ khi đặt trong cùng một lớp.** Cả hai đều là `update(int)`. Tên `amount` và `value` chỉ dùng bên trong thân và tài liệu, không phải tiêu chí overload.

### Chỉ đổi kiểu trả về

~~~java
int count() {
    return 1;
}

long count() {
    return 2L;
}
~~~

**Không hợp lệ trong cùng lớp:** cả hai là `count()`. Java không chọn overload dựa trên kiểu biến nhận kết quả, chẳng hạn `int x = count();` so với `long y = count();`. Việc đổi `int` thành `long` ở phần `return type` không làm hai chữ ký khác nhau.

### Chỉ đổi access modifier hoặc `static`

~~~java
private void ping(int id) { }
public void ping(int id) { }
~~~

Đây cũng là **hai khai báo trùng chữ ký**, nên không thể cùng nằm trong một lớp. Nếu một phương thức `static` và phương thức kia là instance, cùng tên và cùng tham số, chúng vẫn không tạo thành hai overload phân biệt.

### Chỉ đổi `throws`

~~~java
void load(String path) throws java.io.IOException { }
void load(String path) throws java.sql.SQLException { }
~~~

Hai khai báo trên cũng trùng `load(String)`, không thể cùng đặt trong một lớp. Danh sách checked exceptions có thể ảnh hưởng nghĩa vụ xử lý lỗi của caller, nhưng **không phải một phần giúp phân biệt chữ ký**.

### Chỉ đổi annotation hoặc `final`

Một khai báo có annotation `@Deprecated` hoặc modifier `final` không vì thế tạo được overload mới của khai báo có cùng tên và cùng tham số. Các yếu tố này phục vụ mục đích riêng, không phải cách làm khác danh sách kiểu tham số.

**Nguyên tắc rà soát nhanh:** xóa phần tên biến tham số và phần trả về, chỉ giữ tên phương thức cùng danh sách kiểu tham số. Nếu hai khai báo vẫn giống nhau (sau khi xét quy tắc generic/erasure liên quan), không thể coi chúng là overload chỉ vì những thông tin bên ngoài chữ ký thay đổi.

## 6. Chương trình chạy độc lập: số lượng, kiểu và thứ tự

Tạo tệp **`OverloadSignatureDemo.java`**:

~~~java
class Printer {
    static String select(int number) {
        return "one-int";
    }

    static String select(int left, int right) {
        return "two-int";
    }

    static String select(long number) {
        return "one-long";
    }

    static String select(String text) {
        return "one-String";
    }

    static String select(Object object) {
        return "one-Object";
    }

    static String select(int first, long second) {
        return "int-long";
    }

    static String select(long first, int second) {
        return "long-int";
    }

    static String select(int... numbers) {
        return "varargs:" + numbers.length;
    }
}

public class OverloadSignatureDemo {
    public static void main(String[] args) {
        System.out.println(Printer.select(7));
        System.out.println(Printer.select(7L));
        System.out.println(Printer.select("Java"));
        System.out.println(Printer.select(new Object()));

        System.out.println(Printer.select(4, 5));
        System.out.println(Printer.select(4, 5L));
        System.out.println(Printer.select(4L, 5));

        System.out.println(Printer.select());
        System.out.println(Printer.select(1, 2, 3));
        System.out.println(Printer.select(new int[] {8, 9}));
    }
}
~~~

Đứng tại thư mục chứa tệp, chạy:

~~~bash
javac -encoding UTF-8 OverloadSignatureDemo.java
java OverloadSignatureDemo
~~~

Stdout:

~~~text
one-int
one-long
one-String
one-Object
two-int
int-long
long-int
varargs:0
varargs:3
varargs:2
~~~

Phân tích từng nhóm:

1. `select(7)` chọn `select(int)`, vì literal nguyên `7` có kiểu `int`; `select(7L)` chọn `select(long)`.
2. `select("Java")` chọn `select(String)`, là kiểu cụ thể hơn `Object` cho đối số kiểu `String`; `select(new Object())` chọn `select(Object)`.
3. `select(4, 5)` có overload nhận chính xác hai `int`; lời gọi có hai đối số này **không rơi vào** `int...` vì đã có overload fixed arity thích hợp và cụ thể.
4. `select(4, 5L)` phù hợp nhất với `select(int, long)`; `select(4L, 5)` phù hợp nhất với `select(long, int)`.
5. `select()` không nhận đối số nào, nhưng `select(int...)` chấp nhận **mảng varargs rỗng**, nên in `varargs:0`.
6. `select(1, 2, 3)` truyền ba số vào `int...`, nên độ dài là 3; `select(new int[] {8, 9})` truyền mảng sẵn có cho cùng overload, nên độ dài là 2.

Ví dụ có nhiều overload để làm rõ tiêu chí chọn. Trong ứng dụng, nên sử dụng overload khi chúng có **cùng ý nghĩa thao tác**, chứ không biến một tên chung thành tập hợp các chức năng không liên quan.

## 7. Chữ ký hợp lệ chưa đủ để lời gọi hợp lệ

Java phân biệt **hai bước tư duy**:

1. **Khai báo:** các phương thức cùng tên có chữ ký có thể cùng tồn tại hay không?
2. **Lời gọi:** với các đối số thực tế tại một vị trí gọi, compiler tìm ra **một phương thức áp dụng được và cụ thể nhất** hay không?

Hai phương thức `convert(int, long)` và `convert(long, int)` ở mục 4 là các khai báo hợp lệ. Nhưng `convert(1, 2)` không hợp lệ vì **ambiguous invocation**. Đó là lỗi tại nơi gọi, không phải hai khai báo trùng chữ ký.

Java xét phương thức áp dụng qua nhiều giai đoạn trong giải quyết overload. Với Java 17, khi đơn giản hóa cho các trường hợp phổ biến, thứ tự quan trọng là:

- Trước hết thử lời gọi có **số tham số cố định**, cho phép *strict invocation conversions* phù hợp, gồm mở rộng kiểu nguyên thủy (primitive widening) nhưng chưa dựa vào boxing/unboxing.
- Nếu chưa tìm được ứng viên phù hợp, tiếp tục tìm lời gọi fixed arity với *loose invocation conversions*, bao gồm boxing/unboxing theo quy tắc.
- Khi các giai đoạn trên không có phương thức thích hợp, mới xét **variable arity** (varargs), trong đó compiler có thể đóng gói các đối số rời vào một mảng.

Sau mỗi giai đoạn, giữa những ứng viên được áp dụng, Java dùng quy tắc **most-specific method** để lựa chọn; không đơn giản là “khớp tên trước thì dùng” hay “phương thức khai báo trước được ưu tiên”.

**Compiler phân giải overload ở thời điểm biên dịch**, dựa trên kiểu tĩnh của biểu thức và thông tin ngữ cảnh liên quan; không chờ giá trị cụ thể của đối tượng tại runtime để chọn danh sách tham số mới.

## 8. Chuyển kiểu khi gọi khác với chữ ký khi khai báo

Hai declarations `pick(long)` và `pick(Integer)` có thể cùng tồn tại vì **danh sách kiểu tham số khác nhau**. Khi gọi `pick(5)`, literal 5 có kiểu `int`: widening `int → long` có thể áp dụng ở pha strict invocation trước boxing `int → Integer`. Quy tắc ấy giải quyết **một lời gọi**, không đổi chữ ký đã khai báo.

Tương tự, `log(String...)` có một tham số mang kiểu mảng `String[]` trong chữ ký. Khả năng gọi `log("A", "B")` là tiện ích *varargs invocation*, không tạo một chữ ký method thứ hai. Các trường hợp ba pha strict/loose/variable arity và most-specific được phân tích sâu trong bài về thứ tự chuyển kiểu.

Để không nhầm: **(1)** so chữ ký declarations; **(2)** xem kiểu tĩnh ở call site; **(3)** xét chuyển kiểu và most-specific. Không dùng mẹo “ít bước chuyển kiểu nhất” như luật JLS tổng quát.

## 9. `null`: chữ ký hợp lệ không bảo đảm lời gọi hợp lệ

~~~java
static void show(Object value) { }
static void show(String value) { }
// show(null) chọn show(String): String cụ thể hơn Object.
~~~

Nếu một class khác có `show(String)` và `show(Integer)`, hai chữ ký vẫn khác nhau, nhưng `show(null)` **mơ hồ**: không kiểu nào là subtype của kiểu còn lại. `show((String) null)` chọn overload String theo kiểu tĩnh mà cast cung cấp; giá trị vẫn null nên body không được tự ý dereference.

Bài chuyên về null xem xét thêm interfaces, arrays, varargs và generics. Ở đây, bài học là **declaration không trùng chữ ký** và **invocation phân giải duy nhất** là hai yêu cầu khác nhau.

## 10. Varargs: dấu ba chấm không tạo một chữ ký riêng so với mảng

Với khai báo:

~~~java
void log(String... messages) { }
~~~

Tham số `messages` có kiểu `String[]` trong thân. Vì vậy khai báo này trùng chữ ký với:

~~~java
void log(String[] messages) { }
~~~

**Không thể đặt cả hai trong cùng một lớp**; chúng không được xem là hai overload. Dấu `...` khác `[]` về sự thuận tiện khi **gọi**, không phải để tạo một kiểu tham số mới trong chữ ký.

Một phương thức varargs cho phép:

~~~java
log();
log("A");
log("A", "B");
log(new String[] {"A", "B"});
~~~

Nếu chỉ khai báo `log(String[])` thì các lời gọi truyền nhiều `String` rời như `log("A", "B")` không hợp lệ. Với varargs, `log()` sử dụng một mảng rỗng theo ngữ nghĩa lời gọi variable arity. Truyền mảng sẵn có `log(new String[] {...})` sử dụng một đối số mảng tương ứng.

### Varargs và overload có độ ưu tiên khác nhau

Đã thấy `select(int, int)` được ưu tiên cho `select(4, 5)` trước khi compiler cần đến dạng gọi biến độ dài `select(int...)`. Tuy nhiên **varargs vẫn có thể áp dụng ở dạng fixed arity** nếu đối số cuối là mảng phù hợp, như `select(new int[]{8, 9})`.

Đừng coi mọi lời gọi tới một phương thức khai báo `T...` đều tự động tạo thêm mảng; nếu caller đã truyền đúng mảng `T[]`, biến tham số có thể dùng chính tham chiếu mảng đó. Việc sửa phần tử mảng có thể ảnh hưởng đến caller.

### Lời gọi không đối số cũng có thể mơ hồ

Hai khai báo này **khác chữ ký và có thể cùng tồn tại**:

~~~java
static void collect(String... values) { }
static void collect(Integer... values) { }
~~~

Nhưng `collect()` có thể dẫn đến **ambiguous method call** vì cả hai nhận 0 phần tử và `String[]` với `Integer[]` không có quan hệ cụ thể hơn để chọn. Có thể truyền rõ `new String[0]` hoặc `new Integer[0]` để chọn overload dự kiến.

## 11. Generic: kiểu tham số hóa và type erasure

Với generic, cần hiểu thêm rằng **không thể phân biệt overload chỉ bằng đối số kiểu của cùng một kiểu generic** trong nhiều trường hợp. Ví dụ:

~~~java
void save(java.util.List<String> names) { }
void save(java.util.List<Integer> numbers) { }
~~~

Hai khai báo trên **gây lỗi name clash** trong cùng lớp. Sau *type erasure*, hai kiểu tham số đều tương ứng với `List`; JVM không giữ `String` và `Integer` như hai kiểu tham số riêng trong descriptor để phân biệt phương thức này.

Nhưng hai khai báo sau hợp lệ:

~~~java
void save(java.util.List<String> names) { }
void save(java.util.Set<String> names) { }
~~~

`List` và `Set` là hai kiểu raw/erasure khác nhau, nên đây là hai overload có thể phân biệt. **Lời gọi `save(null)` vẫn có thể mơ hồ**, vì `List<String>` và `Set<String>` không là subtype của nhau.

### Đổi tên tham số kiểu generic cũng không giúp

~~~java
<T> void accept(T value) { }
<U> void accept(U value) { }
~~~

Đây là hai khai báo **không hợp lệ trong cùng một lớp**: `T` và `U` chỉ là tên tham số kiểu, và chữ ký được so sánh sau khi thích ứng tham số kiểu tương ứng. Đổi chữ `T` sang `U` không tạo phương thức khác.

Tương tự, generic method `<T> void handle(T value)` thường xung đột với `void handle(Object value)` trong cùng lớp vì erasure và quy tắc chữ ký tương ứng. Đừng dựa vào generic type arguments để chế tạo những overload mà runtime không phân biệt được.

### Overload dựa trên generic type có an toàn không?

Cùng một phương thức có thể dùng **generic method**:

~~~java
static <T> void saveAll(java.util.List<T> items) {
    System.out.println(items.size());
}
~~~

Đây là **một** khai báo nhận `List<T>`, có thể sử dụng với `List<String>`, `List<Integer>` và những danh sách có kiểu thích hợp khác. Với nhu cầu cùng thao tác cho nhiều kiểu phần tử, generic method có thể là giải pháp tốt hơn việc cố tạo nhiều overload bị trùng erasure.

## 12. Phân biệt khai báo overload với overriding và static hiding

**Overloading**: cùng tên, **khác chữ ký tham số**. **Overriding**: subclass cung cấp implementation mới cho một instance method đủ điều kiện kế thừa, giữ subsignature phù hợp. **Static method hiding** không phải dynamic override.

Nếu `BaseGreeter ref = new ChildGreeter()`, compiler phân giải những overload có thể thấy qua **kiểu tĩnh BaseGreeter**. Runtime sau đó có thể dispatch method instance đã chọn tới body override của ChildGreeter. Không dùng runtime class của receiver để tự bổ sung các overload không có trong static receiver type.

Các ví dụ sâu về override, static hiding, field hiding và shadowing nằm ở bài so sánh ba cơ chế. Trọng tâm chữ ký ở đây: **khác tham số để overload; thay implementation hợp lệ để override**.

## 13. Primitive và wrapper là hai kiểu chữ ký

~~~java
static String type(int value) { return "primitive"; }
static String type(Integer value) { return "wrapper"; }
~~~

Hai chữ ký `type(int)` và `type(Integer)` khác nhau. `type(5)` chọn int; `type(Integer.valueOf(5))` chọn Integer. `type((Integer) null)` được phân giải tới bản Integer, nhưng body vẫn phải chịu trách nhiệm null safety.

Cần phân biệt **kiểu tham số của declaration** với **boxing/unboxing tại invocation**: primitive và wrapper đủ tạo hai chữ ký, nhưng việc phương thức nào được chọn là câu hỏi khác, phụ thuộc các pha applicability và most-specific.

## 14. Thứ tự tham số và lỗi thiết kế API

Đây là hai chữ ký phân biệt được:

~~~java
void schedule(String title, int hour) { }
void schedule(int hour, String title) { }
~~~

Tuy nhiên cung cấp cả hai overload chỉ vì hoán đổi vị trí thường ít lợi ích và dễ nhầm khi đọc mã. Tệ hơn, nếu hai tham số có **cùng kiểu**:

~~~java
void move(String source, String destination) { }
~~~

thì thay tên biến thành `move(String destination, String source)` **không tạo overload**, vì đều có chữ ký `move(String, String)`. Lỗi đảo đối số ở nơi gọi như `move(destination, source)` vẫn có thể biên dịch thành công nhưng làm sai nghiệp vụ.

Để API dễ dùng:

1. Chọn thứ tự tham số nhất quán, đặt các dữ liệu định danh/ngữ cảnh trước, các tùy chọn phía sau nếu hợp lý.
2. Đặt tên tham số rõ nghĩa; tên tham số **không tạo chữ ký**, nhưng giúp đọc source và hiển thị gợi ý từ IDE.
3. Khi hai tham số cùng kiểu nhưng ý nghĩa khác hẳn, cân nhắc dùng kiểu có ý nghĩa miền nghiệp vụ như `SourcePath`, `DestinationPath` hoặc một đối tượng cấu hình.
4. Chỉ thêm overload khi có một cách gọi mới có ý nghĩa đối với người dùng, không vì muốn tối đa số chữ ký.

### Cẩn trọng với overload nhận `null`

Nếu API khai báo `send(String)`, `send(Integer)` chỉ để tiện gọi, khách hàng viết `send(null)` sẽ gặp mơ hồ. Một tên khác hoặc một kiểu dữ liệu rõ nghĩa hơn thường dễ dùng hơn.

## 15. Chẩn đoán lỗi biên dịch liên quan chữ ký

| Dấu hiệu | Ví dụ | Nguyên nhân | Hướng sửa |
| --- | --- | --- | --- |
| Method is already defined | `f(int a)` và `f(int b)` | Chỉ khác tên tham số | Đổi tên phương thức hoặc danh sách kiểu/số tham số |
| Method is already defined | `int size()` và `long size()` | Chỉ khác kiểu trả về | Giữ một khai báo, hoặc dùng tên khác |
| Name clash | `f(List<String>)`, `f(List<Integer>)` | Trùng erasure | Dùng một generic method hoặc tên riêng |
| Cannot declare both | `f(String[])`, `f(String...)` | Varargs tương ứng kiểu mảng | Chọn một cách khai báo |
| Reference to method is ambiguous | `f(int,long)`, `f(long,int)`, gọi `f(1,1)` | Hai overload đều áp dụng, không cái nào cụ thể hơn | Truyền kiểu cụ thể hoặc đổi API |
| Reference to method is ambiguous | `f(String)`, `f(Integer)`, gọi `f(null)` | `null` phù hợp cả hai kiểu không có quan hệ subtype | Ép kiểu `null` hoặc đổi API |
| Cannot find suitable method | Chỉ có `f(int,int)` nhưng gọi `f("A")` | Không có overload nhận kiểu/số đối số phù hợp | Sửa lời gọi hoặc thêm overload hợp lý |

Thông báo của `javac` có thể khác nhau đôi chút theo phiên bản và ngữ cảnh; hãy đọc **kiểu tham số được khai báo**, **kiểu biểu thức được truyền** và vị trí lỗi. Đừng sửa nhầm kiểu trả về khi compiler báo trùng chữ ký.

### Checklist khi có lỗi ambiguous

1. Ghi ra các overload cùng tên **có thể truy cập** ở nơi gọi.
2. Ghi rõ **kiểu tại compile time** của từng biểu thức đối số; phân biệt `5` (`int`) với `5L` (`long`), `null`, `Object` và `String`.
3. Đối chiếu số lượng và thứ tự tham số ở từng chữ ký.
4. Xem xét primitive widening, boxing/unboxing và varargs theo giai đoạn; loại những ứng viên không áp dụng.
5. Nếu vẫn nhiều ứng viên, xem phương thức nào **most specific**; nếu không có lựa chọn duy nhất, lời gọi mơ hồ.
6. Chỉnh đầu vào hoặc API cho rõ ràng thay vì sử dụng ép kiểu vô cớ ở khắp nơi.

## 16. Tự kiểm tra: khai báo nào hợp lệ, lời gọi nào chọn gì?

**Câu 1.** Trong cùng một lớp có `m()`, `m(int)`, `m(int,int)` và `m(String)`. Có bao nhiêu chữ ký khác nhau? `m(3,4)` chọn gì?

**Câu 2.** Hai khai báo `void pay(int amount)` và `int pay(int cents)` có được cùng tồn tại không? Hãy giải thích vai trò của return type và tên tham số.

**Câu 3.** `void set(int code,long value)` và `void set(long code,int value)` có hợp lệ không? Kết quả khi gọi `set(1,2)` là gì?

**Câu 4.** `void f(List<String>)` và `void f(List<Integer>)` có phải overload được JVM phân biệt bằng generic arguments không?

**Câu 5.** Tại sao `void log(String... xs)` không thể cùng khai báo với `void log(String[] ys)`?

**Câu 6.** Nếu tồn tại `void show(Object)` và `void show(String)`, `show(null)` chọn phương thức nào? Kết quả có thay đổi nếu overload thứ hai là `show(Integer)` thay vì `show(String)` không?

**Câu 7.** Khi có `pick(long)`, `pick(Integer)`, `pick(int...)`, `pick(5)` chọn overload nào, và vì sao?

**Câu 8.** Ở ví dụ `BaseGreeter`/`ChildGreeter`, vì sao `baseView.greet("An")` in `child-object`, trong khi `childView.greet("An")` in `child-string`?

**Đáp án đối chiếu:**

1. Có bốn chữ ký; `m(3,4)` chọn `m(int,int)`.
2. Không hợp lệ: cả hai là `pay(int)`; `void`/`int` và `amount`/`cents` không phân biệt chữ ký.
3. Hai khai báo hợp lệ vì khác **thứ tự kiểu**; `set(1,2)` mơ hồ vì không có overload duy nhất cụ thể hơn.
4. Không. Type erasure khiến chúng xung đột; có thể dùng generic method hoặc tên khác.
5. Trong chữ ký, `String...` tương ứng với `String[]`.
6. `show(String)` cụ thể hơn `show(Object)` nên được chọn; nếu tập overload là `show(Object)` và `show(Integer)` thì `show(Integer)` được chọn vì cụ thể hơn `Object`. **Nếu đồng thời có `show(String)` và `show(Integer)`**, lời gọi `show(null)` mới mơ hồ.
7. `pick(long)`; widening từ `int` sang `long` được xét trước boxing và variable arity.
8. Overload được chọn theo kiểu tĩnh của biến tại compile time; override của instance method được dispatch theo kiểu thực tế của đối tượng khi chạy.

## 17. Tài liệu đối chiếu

- [Java Language Specification 17, §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): chữ ký, subsignature, override-equivalent và quan hệ erasure.
- [Java Language Specification 17, §8.4.9 — Overloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.9): quy tắc khai báo nạp chồng.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): tìm phương thức áp dụng, chọn overload cụ thể nhất và ngữ nghĩa lời gọi.

**Ghi nhớ:** khi đọc một overload, tập trung vào **tên phương thức + số lượng, kiểu và thứ tự của các tham số**. Thay đổi tên biến tham số, kiểu trả về, modifier hoặc `throws` không tạo chữ ký mới. Hai khai báo có chữ ký khác nhau vẫn có thể gây **lời gọi mơ hồ**; và với generic, cần kiểm tra thêm **type erasure**. Phân biệt đúng chữ ký và quy tắc chọn lời gọi sẽ giúp thiết kế API rõ ràng và tránh lỗi biên dịch khó hiểu.
