# Tham số varargs trong Java: khai báo, truyền mảng và gọi không đối số

**Varargs** (*variable arity parameters*) cho phép một phương thức Java nhận **số lượng đối số thay đổi** ở vị trí tham số cuối. Thay vì bắt người gọi tạo một mảng ở mọi lần gọi, Java cho phép viết các phần tử liên tiếp: `sum(2, 3, 5)`. Bên trong phương thức, tham số varargs vẫn được xử lý như **một mảng**. Bài học này giải thích cú pháp `T...`, ba cách gọi quan trọng (không đối số, nhiều đối số và truyền mảng sẵn có), các quy tắc về `null`, overload, generic và tác dụng phụ khi dùng mảng.

Các ví dụ được xây dựng cho **Java 17 trở lên**. Những đoạn có tên tệp và lệnh `javac`/`java` là chương trình độc lập; các đoạn ghi rõ “minh họa” chỉ biểu diễn cú pháp hoặc lỗi biên dịch.

## 1. Varargs giải quyết vấn đề gì?

Giả sử cần tính tổng nhiều số nguyên. Có thể khai báo cố định `sum(int a, int b)` nhưng phương thức này chỉ nhận đúng hai số; tiếp tục tạo các phiên bản 3, 4, 5 tham số khiến API rườm rà. Ta có thể cho người gọi truyền `int[]`, nhưng mỗi lần cần gộp những số rời thì họ lại phải tự tạo mảng.

Varargs cung cấp cú pháp thuận tiện:

~~~java
static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total = Math.addExact(total, number);
    }
    return total;
}
~~~

Đây là **đoạn phương thức minh họa**, được đặt trong một lớp và chưa chứa `main`. Khi gọi:

~~~java
sum();                     // Không truyền phần tử nào -> 0
sum(2, 3, 5);              // Truyền ba phần tử -> 10
sum(new int[] {4, 6});     // Truyền sẵn mảng int[] -> 10
~~~

Ba lời gọi đều có thể dùng cùng **một khai báo**. Varargs không biến Java thành ngôn ngữ có số lượng tham số hình thức không giới hạn: trong khai báo vẫn có **một tham số mảng cuối**, nhưng cú pháp lời gọi có thể trải ra thành không, một hoặc nhiều phần tử.

## 2. Cú pháp khai báo `T... name`

Cấu trúc cơ bản:

~~~text
returnType methodName(Type... parameterName) {
    // parameterName được dùng như một mảng Type[]
}
~~~

Ví dụ:

~~~java
static void printWords(String... words) {
    for (String word : words) {
        System.out.println(word);
    }
}
~~~

Trong `String... words`:

- `String` là **kiểu phần tử** được chấp nhận.
- `...` (đúng ba dấu chấm) đánh dấu **varargs**.
- `words` là **tên tham số**; bên trong phương thức có kiểu `String[]`.
- Dấu `()` là danh sách tham số như ở mọi khai báo phương thức Java khác.

Vì `words` là một mảng trong thân phương thức, có thể dùng `words.length`, `words[0]` khi không rỗng, `Arrays.toString(words)` hoặc vòng `for-each`.

Các ràng buộc:

1. Một danh sách tham số hình thức được khai báo **tối đa một varargs**.
2. Nếu có, varargs phải **đứng cuối danh sách tham số**.
3. Có thể có tham số thông thường đứng trước varargs: `printLabels(String prefix, String... labels)`.
4. Không thể có tham số thông thường đứng **sau** varargs.
5. Có thể dùng kiểu nguyên thủy, tham chiếu hoặc mảng làm kiểu phần tử: `int...`, `String...`, `String[]...`.
6. Constructor cũng có thể có varargs: `Bag(String... items)`; quy tắc về vị trí cuối vẫn áp dụng.

Ví dụ **cố ý sai**:

~~~java
void invalid(int... numbers, String name) {
}
~~~

Compiler không chấp nhận vì `numbers` là varargs nhưng còn `name` đứng phía sau. Sửa thành:

~~~java
void valid(String name, int... numbers) {
}
~~~

Các ví dụ trên là **đoạn khai báo trong lớp**, không phải các tệp Java độc lập. Việc “đứng cuối” áp dụng cho thứ tự **tham số hình thức** của một method/constructor; không liên quan việc khai báo các field ở đâu trong lớp.

## 3. Ba cách gọi: không đối số, đối số rời, mảng có sẵn

Một lời gọi đến `sum(int... numbers)` có thể có ba hình thức phổ biến:

| Lời gọi | Bên trong `numbers` | Kết quả |
| --- | --- | --- |
| `sum()` | Một `int[]` mới có độ dài 0 trong lời gọi biến độ dài | 0 |
| `sum(2)` | Mảng chứa một phần tử `2` | 2 |
| `sum(2, 3, 5)` | Mảng chứa ba phần tử `2, 3, 5` | 10 |
| `sum(new int[] {4, 6})` | Chính tham chiếu mảng truyền sẵn khi khớp dạng tham số mảng | 10 |
| `sum(new int[0])` | Mảng rỗng do người gọi tạo | 0 |

Với cú pháp đối số rời, có thể hình dung trình biên dịch sắp xếp các phần tử vào một mảng phù hợp để gọi phương thức. Đó là **mô hình ngữ nghĩa** để hiểu Java, không cần giả định một bố trí bộ nhớ hoặc một số lần cấp phát cụ thể mà JVM tối ưu hóa ra sao.

**Gọi không đối số `sum()` không đồng nghĩa tham số là `null`.** Trong lời gọi varargs thông thường, `numbers.length == 0`, nên vòng lặp không chạy và tổng giữ 0. Nếu chính người gọi cố tình truyền `null` với kiểu mảng, ngữ nghĩa lại khác và phải xử lý riêng.

### Tham số thông thường trước varargs

Với khai báo:

~~~java
static String format(String title, String... values) {
    return title + "[" + String.join(", ", values) + "]";
}
~~~

Tham số `title` luôn phải được cung cấp. Chỉ **phần varargs** mới có thể nhận 0 phần tử:

~~~java
format("Names");                   // Names[]
format("Names", "An", "Binh");      // Names[An, Binh]
format("Names", new String[] {"An", "Binh"}); // Names[An, Binh]
~~~

Ba đoạn gọi là minh họa bên trong một phương thức. `format()` không hợp lệ vì thiếu tham số bắt buộc `title`.

## 4. Chương trình hoàn chỉnh: đối chiếu các dạng lời gọi

Tạo tệp **`VarargsBasicsDemo.java`**:

~~~java
import java.util.Arrays;

public class VarargsBasicsDemo {
    static int sum(int... numbers) {
        int result = 0;
        for (int number : numbers) {
            result = Math.addExact(result, number);
        }
        return result;
    }

    static String format(String title, String... values) {
        return title + "[" + String.join(", ", values) + "]";
    }

    static void inspect(String... values) {
        if (values == null) {
            System.out.println("Mảng varargs là null");
            return;
        }

        String first = values.length == 0
                ? "(không có)"
                : String.valueOf(values[0]);

        System.out.println("length=" + values.length + "; first=" + first);
    }

    static void uppercaseFirst(String... values) {
        if (values.length > 0 && values[0] != null) {
            values[0] = values[0].toUpperCase();
        }
    }

    public static void main(String[] args) {
        System.out.println("sum() = " + sum());
        System.out.println("sum(2, 3, 5) = " + sum(2, 3, 5));
        System.out.println("sum(array) = " + sum(new int[] {4, 6}));

        System.out.println(format("Names"));
        System.out.println(format("Names", "An", "Binh"));

        String[] names = {"Mai", "Lan"};
        System.out.println(format("Array", names));

        inspect();
        inspect("A", "B");
        inspect((String) null);
        inspect((String[]) null);

        String[] mutable = {"minh", "hoa"};
        uppercaseFirst(mutable);
        System.out.println(Arrays.toString(mutable));
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 VarargsBasicsDemo.java
java VarargsBasicsDemo
~~~

Stdout dự kiến:

~~~text
sum() = 0
sum(2, 3, 5) = 10
sum(array) = 10
Names[]
Names[An, Binh]
Array[Mai, Lan]
length=0; first=(không có)
length=2; first=A
length=1; first=null
Mảng varargs là null
[MINH, hoa]
~~~

Giải thích các nhóm dòng:

- Ba lệnh `sum` lần lượt nhận **không phần tử**, **ba phần tử rời**, **một mảng hai phần tử**.
- `format("Names")` có một đối số `title` và **không** có phần tử `values`, vì vậy `String.join` nối mảng rỗng thành chuỗi rỗng.
- `format("Array", names)` đưa đúng mảng `String[]` vào tham số varargs.
- `inspect()` có một mảng tham số độ dài **0**, khác với `inspect((String[]) null)` có tham số mảng là **null**.
- `inspect((String) null)` đưa vào **một phần tử null**, nên độ dài bằng **1**.
- `uppercaseFirst(mutable)` sửa phần tử thứ nhất của mảng `mutable` vì tham số varargs nhận chính tham chiếu mảng được truyền từ bên gọi.

`Math.addExact` giúp ví dụ `sum` phát hiện tràn số nguyên bằng `ArithmeticException`, thay vì âm thầm tràn `int`. API của `sum` chỉ cam kết trả tổng khi phép tính nằm trong miền giá trị `int`.

## 5. Varargs thực chất là mảng trong thân phương thức

Ở cấp khai báo, hai cách viết sau **không thể cùng tồn tại như hai overload** trong một lớp:

~~~java
void print(String... words) {
}

void print(String[] words) {
}
~~~

Đây là ví dụ lỗi cố ý. Hai khai báo đều có kiểu tham số tương đương một `String[]`, nên compiler sẽ báo trùng chữ ký phương thức. Cả `String... words` và `String[] words` đều cho phép dùng `words.length` và duyệt mảng trong thân.

Khác biệt chính nằm ở **cú pháp lời gọi**:

- Với `print(String... words)`, có thể gọi `print()`, `print("A", "B")` hoặc `print(new String[] {"A", "B"})`.
- Với `print(String[] words)` không khai báo varargs, phải truyền đúng một đối số kiểu mảng thích hợp, ví dụ `print(new String[] {"A", "B"})`; không thể gọi `print("A", "B")` để compiler tự gộp đối số rời.

Varargs là tiện ích được Java hỗ trợ ở **thời điểm biên dịch lời gọi**, còn method body sử dụng tham số mảng. Cú pháp dấu ba chấm không làm phần tử mảng trở thành một cấu trúc mới có cơ chế truy cập khác.

### Vì sao truyền mảng sẵn có cần thận trọng?

Nếu đối số cuối trong lời gọi khớp đúng kiểu mảng cần thiết, Java có thể áp dụng lời gọi dạng **fixed arity**: chính đối số mảng ấy được truyền tới phương thức, không nhất thiết đóng gói nó vào một mảng khác. Trong ví dụ `uppercaseFirst(mutable)`, phương thức nhận mảng `String[]` của bên gọi và sửa `mutable[0]`.

Trái lại, gọi `uppercaseFirst("minh", "hoa")` ở dạng biến độ dài làm các đối số rời thành mảng tham số dùng cho lời gọi; bên gọi không có một biến mảng `mutable` độc lập để quan sát như trên. Vẫn có tác dụng phụ đối với mảng bên trong lời gọi, nhưng cách chia sẻ tham chiếu khác nhau.

**Không nên mặc định phương thức varargs là hàm thuần**. Nếu nó sửa các phần tử trong một mảng do người gọi truyền vào, đối tượng của bên gọi cũng thay đổi. Hãy dùng `Arrays.copyOf` hoặc cơ chế sao chép phù hợp nếu phương thức phải giữ độc lập dữ liệu đầu vào.

## 6. Lời gọi không đối số không phải truyền null

Trong thân `inspect(String... values)`, lời gọi `inspect()` tạo một mảng độ dài 0, **không phải** mảng null. Các cách truyền rõ ý định:

| Lời gọi | Kết quả với `values` |
| --- | --- |
| `inspect()` | Mảng không null, độ dài 0 |
| `inspect(new String[0])` | Mảng không null, độ dài 0 |
| `inspect((String[]) null)` | Chính mảng `values == null` |
| `inspect((String) null)` | Mảng độ dài 1, phần tử đầu null |
| `inspect(null, "A")` | Mảng độ dài 2, phần tử đầu null |

Lời gọi `inspect(null)` có thể được xử lý ở **fixed-arity form** như một đối số `String[]` null và `javac` có thể cảnh báo; nó không phải cách biểu đạt “không phần tử”. Nếu muốn rỗng dùng `inspect()`; nếu muốn đúng một phần tử null dùng ép kiểu `(String) null`. Một API nhận mảng từ caller nên quy định rõ có chấp nhận null array hay không và kiểm tra trước `values.length`.

## 7. Tham số thông thường và varargs trong cùng phương thức

Một khai báo như:

~~~java
static int weightedSum(int multiplier, int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total = Math.addExact(
                total, Math.multiplyExact(multiplier, number));
    }
    return total;
}
~~~

cho phép các lời gọi:

~~~java
weightedSum(2);                // 0: không có numbers
weightedSum(2, 3);             // 6: một phần tử
weightedSum(2, 3, 4);          // 14: hai phần tử
weightedSum(2, new int[] {3, 4}); // 14: truyền mảng
~~~

Các đoạn này **minh họa lời gọi và khai báo trong lớp**, chưa là chương trình độc lập. Tham số `multiplier` là bắt buộc, còn `numbers` nhận từ 0 phần tử trở lên.

Nếu muốn nhận **ít nhất một số**, varargs bản thân nó không bảo đảm điều đó. Có thể thiết kế chữ ký `weightedSum(int multiplier, int first, int... rest)` để yêu cầu tối thiểu một phần tử tại compile time; hoặc tiếp tục dùng `int... numbers` và kiểm tra `numbers.length > 0` trong thân nếu API muốn báo lỗi khi rỗng.

Việc dùng các tham số thông thường trước varargs tạo API tự mô tả hơn khi có phần cấu hình bắt buộc và phần dữ liệu số lượng linh hoạt.

## 8. Overload và quy tắc chọn lời gọi varargs

Varargs là một cách khai báo tham số cuối, **không có nghĩa nó luôn thắng** những overload có số lượng tham số cố định. Java lựa chọn phương thức theo các giai đoạn áp dụng; các lời gọi phù hợp theo dạng fixed arity được xét trước khi phải dùng variable arity.

Tạo tệp độc lập **`VarargsOverloadDemo.java`**:

~~~java
public class VarargsOverloadDemo {
    static String choose(int number) {
        return "fixed: " + number;
    }

    static String choose(int... numbers) {
        return "varargs: " + numbers.length;
    }

    public static void main(String[] args) {
        System.out.println(choose(7));
        System.out.println(choose(7, 8));
        System.out.println(choose());
        System.out.println(choose(new int[] {1, 2, 3}));
    }
}
~~~

~~~bash
javac VarargsOverloadDemo.java
java VarargsOverloadDemo
~~~

Stdout:

~~~text
fixed: 7
varargs: 2
varargs: 0
varargs: 3
~~~

`choose(7)` chọn overload `int`; hai đối số hoặc không đối số chọn overload varargs; một `int[]` có thể truyền trực tiếp vào varargs.

**Lưu ý nâng cao:** nhiều overload varargs có kiểu phần tử khác nhau, chẳng hạn `send(String...)` và `send(Integer...)`, có thể khiến `send()` mơ hồ vì cả hai nhận 0 phần tử. Chương kế tiếp về **giới hạn vị trí và những lời gọi dễ gây nhầm** phân tích đầy đủ các giai đoạn overload, mơ hồ `null` và lựa chọn mảng/phần tử.

## 9. Varargs với kiểu tham chiếu và mảng nhiều chiều

Varargs nhận kiểu nguyên thủy hoặc kiểu tham chiếu. Nhưng khi bản thân **kiểu phần tử là một mảng**, hình thức trong thân có thêm một chiều mảng:

~~~java
static int countElements(String[]... groups) {
    int count = 0;
    for (String[] group : groups) {
        count += group.length;
    }
    return count;
}
~~~

**Đoạn minh họa trong lớp**, giả sử mọi `group` đều khác null. `String[]... groups` nghĩa là trong thân `groups` có kiểu `String[][]`: mỗi phần tử là một `String[]`.

Có thể gọi:

~~~java
countElements();                                 // 0
countElements(new String[] {"A", "B"});           // 2
countElements(new String[] {"A"}, new String[] {"B", "C"}); // 3
countElements(new String[][] {{"A"}, {"B", "C"}});          // 3
~~~

Hãy so sánh với `String... words`, có kiểu tham số là `String[]` và từng phần tử là `String`. Dấu `...` **không tự “trải phẳng”** mọi loại mảng đệ quy.

### Bẫy của `Object...` và mảng

Ví dụ minh họa:

~~~java
static void log(Object... values) {
    System.out.println(values.length);
}
~~~

- `log(new int[] {1, 2})` đưa vào **một phần tử** kiểu `int[]` do `int[]` là một `Object`, nhưng **không phải** `Object[]`; in `1`.
- `log(new String[] {"A", "B"})` có thể truyền cả mảng `String[]` dưới dạng `Object[]` (mảng tham chiếu có tính hiệp biến); trong thân in `2`.
- `log((Object) new String[] {"A", "B"})` ép kiểu biểu thức thành `Object`, buộc lời gọi biến độ dài nhận **một phần tử duy nhất** là đối tượng mảng; trong thân in `1`.

Sự khác biệt này là hệ quả của kiểu mảng và khả năng tương thích kiểu đối số ở lời gọi. Với API nhận `Object...`, cần cẩn trọng khi khách hàng truyền một mảng mà họ định coi là **một giá trị duy nhất**.

## 10. Varargs, generic và cảnh báo heap pollution

Một khai báo như `static <T> void printGroups(List<T>... groups)` kết hợp **mảng của varargs** với **generic type erasure**. `List<T>` không phải kiểu phần tử reifiable đầy đủ ở runtime, nên `javac` có thể cảnh báo *possible heap pollution* hoặc *unchecked generic array creation*. Không nên coi lời gọi compile được là bằng chứng mọi thao tác với mảng generic đều an toàn.

**Vì sao nguy hiểm?** Nếu code coi mảng `List<String>[]` như `Object[]` rồi ghi vào đó một `List<Integer>`, một phép đọc kiểu String về sau có thể ném `ClassCastException`. Không thao tác ghi sai kiểu lên mảng varargs, không làm lộ mảng cho caller và cân nhắc nhận `List<List<T>>`/`Collection` khi API phù hợp.

`@SafeVarargs` là lời cam kết của tác giả rằng code **không thực hiện thao tác không an toàn trên mảng varargs**; annotation không khiến code sai tự an toàn. Trong Java 17, nó chỉ hợp lệ trên constructor hoặc phương thức `static`, `final` hay `private` đủ điều kiện, không trên instance method có thể override. Chi tiết exploit, ví dụ runnable, cảnh báo compiler và giới hạn annotation được học tại bài **Giới hạn vị trí varargs và những lời gọi dễ gây nhầm**.

Với `int...` hay `String...` đơn giản, người mới chỉ cần nhớ “trong thân là mảng”; chú ý heap pollution nhất khi kiểu phần tử varargs liên quan generic non-reifiable.

## 11. Varargs trong constructor

Constructor cũng có thể khai báo tham số biến độ dài, ví dụ:

~~~java
class Tags {
    private final java.util.List<String> values;

    Tags(String... names) {
        if (names == null) {
            throw new IllegalArgumentException("names là null");
        }
        values = java.util.List.copyOf(java.util.Arrays.asList(names));
    }

    int size() {
        return values.size();
    }
}
~~~

**Đây là định nghĩa lớp minh họa**, không có `main`; `Tags()`, `Tags("A")`, `Tags("A", "B")` đều gọi được constructor có varargs. `Tags(new String[] {"A", "B"})` cũng được chấp nhận.

`List.copyOf` tạo danh sách không cho phép sửa qua API; nó cũng từ chối phần tử `null`. Nếu muốn hợp đồng rõ hơn với phần tử null, hãy kiểm tra từng tên trước khi tạo danh sách. Việc nhận varargs ở constructor không làm đối tượng tự bất biến: tính bất biến còn phụ thuộc toàn bộ trường và đối tượng mà chúng tham chiếu.

Nếu thiết kế constructor có tham số bắt buộc trước varargs, ví dụ `Tags(String owner, String... names)`, thì `owner` luôn phải xuất hiện khi gọi; số tên ở phần varargs vẫn có thể là 0.

## 12. Các API Java quen thuộc có varargs

Một số API tiêu chuẩn thể hiện lợi ích của varargs:

- `System.out.printf("%s: %d%n", "Count", 3)`: định dạng đầu ra; `printf` có tham số định dạng rồi đến `Object...`.
- `String.format("%s-%d", "ID", 7)`: trả một `String` đã định dạng theo quy tắc format.
- `java.util.List.of("A", "B", "C")`: tạo danh sách không hỗ trợ sửa qua API; `List.of` cung cấp nhiều overload và có overload varargs.
- `java.util.Arrays.asList("A", "B")`: tạo danh sách có kích thước cố định và liên kết với mảng đầu vào/đằng sau theo hợp đồng API.
- `java.nio.file.Path.of("dir", "file.txt")`: có overload nhận `String first, String... more` để ghép các phần đường dẫn.

Không phải mọi API ở trên đều có cùng ngữ nghĩa về `null`, sao chép dữ liệu hay tính thay đổi được của kết quả. **Varargs chỉ mô tả cách truyền số lượng đối số**, không tự định nghĩa hành vi nghiệp vụ của API đó.

Đừng nhầm varargs với cú pháp `...` khi người viết tài liệu muốn ghi “vân vân”: trong mã Java, `Type...` là cú pháp chính thức có ràng buộc vị trí và kiểu.

## 13. Lỗi biên dịch và lỗi runtime thường gặp

| Vấn đề | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Varargs không đứng cuối | `void f(int... xs, String label)` | Đổi thành `void f(String label, int... xs)` |
| Khai báo hơn một varargs | `void f(int... a, String... b)` | Chỉ giữ tối đa một, ở cuối |
| Dùng sai kiểu phần tử | `sum("3", "4")` với `int...` | Truyền `int` hoặc chuyển đổi dữ liệu hợp lệ |
| Nghĩ lời gọi `sum()` tạo `null` | Dùng `numbers == null` để phát hiện mảng rỗng | Kiểm tra `numbers.length == 0` |
| Truyền `(String[]) null` nhưng duyệt ngay | `for (String x : words)` | Kiểm tra null hoặc từ chối đầu vào |
| Không phân biệt null mảng và null phần tử | `f((String[]) null)` và `f((String) null)` | Ép kiểu để nêu rõ ý định |
| Nghĩ mảng truyền sẵn luôn được sao chép | `uppercaseFirst(array)` | Coi là mảng chia sẻ; tránh sửa hoặc tự sao chép |
| Gọi varargs overload mơ hồ | `send()` với `String...` và `Integer...` | Chỉ định kiểu mảng hoặc cải thiện API |
| Overload `int[]` và `int...` | Hai khai báo tương đương chữ ký | Chỉ giữ một khai báo |
| Lạm dụng generic varargs | `List<String>...` rồi thao tác trên `Object[]` | Tránh ghi không an toàn, cân nhắc thiết kế kiểu khác |
| Gắn `@SafeVarargs` không đúng | Dùng trên phương thức có thể override hoặc code unsafe | Chỉ dùng khi đủ điều kiện và thực sự bảo đảm an toàn |
| Đưa mảng primitive vào `Object...` và mong tách phần tử | `log(new int[]{1,2})` | Nhận biết nó là một object `int[]`; xử lý phù hợp |

Một nhầm lẫn khác là coi varargs như cách truyền tham chiếu đến **biến** của người gọi. Java luôn truyền đối số **theo giá trị**: khi truyền mảng, giá trị được sao chép là tham chiếu đến mảng; **đối tượng mảng** có thể được chia sẻ, còn gán lại biến tham số không đổi biến mảng ở phía gọi.

## 14. Chọn varargs hay mảng hoặc collection?

Không phải mọi phương thức có danh sách dữ liệu đều nên sử dụng varargs.

| Nhu cầu | Lựa chọn thường thích hợp | Lý do |
| --- | --- | --- |
| API tiện lợi với số phần tử nhỏ và biến thiên | `T...` | Gọi `f(a, b, c)` rõ và ngắn |
| Người gọi đã có một mảng | `T...` hoặc `T[]` | Cả hai nhận mảng; varargs còn tiện khi gọi rời |
| Cần làm rõ bắt buộc phải truyền một collection | `List<T>` hoặc `Collection<T>` | Thể hiện đối tượng collection và các thao tác của nó |
| Cần dữ liệu có kích thước lớn hoặc được truyền qua nhiều tầng | `List<T>`, mảng, iterator/stream theo mục đích | Tránh cú pháp gọi quá dài, quản lý ownership rõ |
| API yêu cầu tối thiểu một phần tử | `f(T first, T... rest)` hoặc validation trong thân | Varargs một mình cho phép 0 phần tử |
| Có nhiều overload cùng tên và nhiều kiểu varargs | Cân nhắc tên khác hoặc một API nhận collection | Tránh ambiguous invocation |

Varargs tốt cho trải nghiệm **người gọi**. Khi thiết kế API, vẫn phải nêu rõ điều gì xảy ra nếu không có phần tử, có null, có phần tử trùng, dữ liệu đầu vào bị thay đổi hoặc số lượng quá lớn.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Với `static int sum(int... xs)`, những lời gọi `sum()`, `sum(1, 2)`, `sum(new int[]{1, 2})` có hợp lệ không? `xs.length` lần lượt là bao nhiêu?

**Câu 2.** Vì sao `static void log(String... xs, int level)` không hợp lệ? Viết lại nếu `level` là bắt buộc, còn `xs` có số lượng linh hoạt.

**Câu 3.** Với `void show(String... words)`, điều gì khác giữa `show()`, `show((String[]) null)` và `show((String) null)`?

**Câu 4.** Một mảng `String[] labels = {"a", "b"}` được truyền cho `uppercaseFirst(labels)`. Vì sao sau lời gọi `labels[0]` có thể đổi thành `"A"`? Nếu phương thức chỉ đọc mảng, có tác dụng phụ đó không?

**Câu 5.** Tại sao hai phương thức cùng tên `void print(int[] values)` và `void print(int... values)` không thể cùng khai báo trong một lớp?

**Câu 6.** Với hai overload `choose(int)` và `choose(int...)`, lời gọi `choose(5)` chọn phương thức nào? `choose()` thì sao?

**Câu 7.** Với `log(Object... values)`, `log(new int[]{1, 2})` và `log(new String[]{"A", "B"})` có cùng số phần tử `values` không?

**Câu 8.** Tại sao generic varargs như `List<String>...` có thể phát sinh cảnh báo? `@SafeVarargs` có quyền hợp thức hóa code ghi sai kiểu vào mảng không?

**Đáp án tham khảo:**

1. Cả ba đều hợp lệ; độ dài lần lượt là 0, 2 và 2.
2. Varargs phải cuối; viết `static void log(int level, String... xs)`.
3. Mảng rỗng độ dài 0; tham chiếu mảng null; mảng độ dài 1 chứa phần tử null.
4. Vì phương thức nhận tham chiếu tới cùng mảng rồi sửa phần tử; phương thức chỉ đọc không gây side effect sửa mảng ấy.
5. Cả hai có kiểu tham số `int[]` ở chữ ký, gây khai báo trùng.
6. `choose(int)` cho một số; `choose(int...)` khi không truyền số.
7. Khác: `int[]` là một object trong `Object...` nên độ dài 1; `String[]` có thể được truyền như `Object[]` nên độ dài 2.
8. Do generic type erasure kết hợp cách mảng được kiểm tra kiểu runtime; annotation là cam kết của tác giả, không biến thao tác không an toàn thành an toàn.

## 16. Tài liệu tham khảo

- [Java Language Specification 17, §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): khai báo tham số biến độ dài và ràng buộc vị trí.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): các pha chọn overload và lời gọi variable arity.
- [Java SE 17 API — SafeVarargs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): ý nghĩa và điều kiện sử dụng annotation.
- [Java SE 17 API — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): các phương thức làm việc với mảng, gồm `asList` và `toString`.

**Ghi nhớ:** `T... values` là cú pháp khai báo một **tham số mảng ở cuối**, cho phép người gọi truyền **0, 1, nhiều phần tử rời** hoặc **một mảng phù hợp**. Mảng rỗng khác mảng `null`; mảng truyền sẵn có thể được chia sẻ; overload và generic varargs cần chú ý những quy tắc bổ sung khi thiết kế API.
