# Varargs Object... của API reflection và cách truyền một mảng như một đối số

## 1. Bài toán: truyền String[] vào Method.invoke nhưng Java lại hiểu thành nhiều đối số

Java Reflection cung cấp `java.lang.reflect.Method.invoke` để gọi một phương thức được xác định ở thời điểm chạy:

~~~java
Object invoke(Object receiver, Object... args)
        throws IllegalAccessException, IllegalArgumentException,
               java.lang.reflect.InvocationTargetException;
~~~

Tham số `receiver` là đối tượng nhận lời gọi (hoặc `null` cho phương thức static). Phần `Object... args` là **danh sách các đối số mà phương thức đích nhận được**, không phải một đối số duy nhất tên `args`. Ở bytecode, tham số thứ hai của `invoke` thực chất là `Object[]`. Ký hiệu ba chấm `...` khiến **trình biên dịch tại nơi gọi** có thể tự tạo mảng `Object[]` chứa từng đối số.

Điều này dễ tạo bẫy khi bản thân phương thức đích cũng cần một đối số là **một mảng**:

~~~java
public void printAll(String[] items) { /* ... */ }
~~~

Nếu gọi:

~~~java
String[] items = {"red", "blue"};
Method method = Printer.class.getMethod("printAll", String[].class);
method.invoke(printer, items); // DỄ SAI: items có thể bị dùng như Object[] đối số
~~~

Vì `String[]` là một kiểu con của `Object[]`, trình biên dịch có thể dùng **chính `items` làm mảng chứa các đối số của `invoke`**. Reflection khi ấy thấy hai đối số `"red"` và `"blue"`, trong khi `printAll` chỉ khai báo **một tham số kiểu `String[]`**. Kết quả là `IllegalArgumentException` do số lượng đối số không khớp.

**Cách truyền chắc chắn một mảng thành một đối số duy nhất:**

~~~java
method.invoke(printer, (Object) items);
method.invoke(printer, new Object[] { items });
~~~

Trong trường hợp trên, cả hai hình thức đều khiến `args` của `Method.invoke` có **một phần tử**, và phần tử đó chính là đối tượng mảng `String[]` cần đưa cho `printAll`.

Bài này phân biệt hai lớp varargs, giải thích trường hợp `String[]` và `int[]`, xử lý `null`, chỉ ra sự khác nhau giữa phương thức đích nhận mảng thường và khai báo `String...`, đồng thời thực hành những lỗi được báo bằng Reflection.

## 2. Hai lớp đối số: Object[] bên ngoài và mảng dữ liệu bên trong

Xét API:

~~~java
Method method = Printer.class.getMethod("printAll", String[].class);
String[] items = {"red", "blue"};
Object result = method.invoke(printer, new Object[] { items });
~~~

Ta có **hai mảng ở hai cấp**:

~~~text
Method.invoke(printer, new Object[] { items })
                      |
                      +-- Object[] args của chính Method.invoke
                          length = 1
                          args[0] --------------+
                                                 |
                                                 v
                                 String[] items = ["red", "blue"]
                                 (một đối số của printAll)
~~~

- **Mảng bên ngoài** có kiểu `Object[]`, biểu diễn *số lượng và thứ tự tham số* cần truyền cho phương thức đích.
- **Mảng bên trong** có kiểu `String[]`, là *giá trị của đúng một tham số* mà `printAll(String[])` mong đợi.
- `args.length == 1` không có nghĩa `items.length == 1`. `items` vẫn chứa hai chuỗi, hoặc có thể chứa hàng nghìn phần tử.
- Phương thức đích nhận đúng một tham số `String[]`. Reflection không tự duyệt `items` và coi từng phần tử là một tham số của `printAll` khi nó đã được bọc đúng cách.

Đối chiếu hai biểu thức:

~~~java
method.invoke(printer, items);
method.invoke(printer, new Object[] { items });
~~~

Chúng **không tương đương** nếu `items` có kiểu `String[]` hoặc một kiểu mảng tham chiếu khác có thể chuyển sang `Object[]`. Biểu thức thứ nhất có thể gửi trực tiếp `items` làm mảng `args` của API `invoke`; biểu thức thứ hai tạo một `Object[]` chứa một phần tử duy nhất là `items`.

Một cách tự kiểm tra trước khi chạy: nếu phương thức đích khai báo `printAll(String[])`, câu hỏi cần hỏi là **`Method.invoke` sẽ nhìn thấy bao nhiêu phần tử trong `Object[] args`?** Câu trả lời phải là một, và phần tử đó phải tương thích với `String[]`.

## 3. Varargs ở Java hoạt động ở nơi gọi như thế nào?

Ký hiệu `Object... args` là cú pháp cho tham số biến độ dài. Ở góc nhìn chữ ký JVM, nó là một tham số mảng `Object[]`. Java cho phép hai cách gọi phổ biến:

~~~java
method.invoke(receiver, value1, value2); // dạng variable arity
method.invoke(receiver, new Object[] { value1, value2 }); // mảng args tường minh
~~~

Trong dạng thứ nhất, trình biên dịch thường tạo `new Object[] { value1, value2 }` để truyền tới phương thức `invoke`. Dạng thứ hai cung cấp trực tiếp mảng `Object[]`, nên trình biên dịch không cần tạo mảng khác.

### Vì sao String[] gây bẫy?

~~~java
String[] words = {"a", "b"};
method.invoke(receiver, words);
~~~

`String[]` là một **reference array** và có quan hệ kiểu con với `Object[]`. Vì vậy, tại vị trí đối số cuối của phương thức `invoke(Object, Object...)`, trình biên dịch có thể chọn cách gọi với tham số mảng `Object[]` đã có (fixed arity). Nó không nhất thiết bọc cả `words` vào một `Object[]` mới.

Đọc theo nghĩa tương đương ở tầng đối số truyền cho Reflection:

~~~text
method.invoke(receiver, words)
    -> args của Method.invoke là words
    -> args.length = words.length
    -> từng phần tử String bị xem là một đối số của phương thức đích
~~~

Khi biên dịch bằng `javac`, lời gọi kiểu này thường xuất hiện cảnh báo *non-varargs call for last parameter; cast to Object for a varargs call or to Object[] for a non-varargs call*. Cảnh báo này nói về **cách biên dịch lời gọi `Method.invoke`**, không phải tuyên bố rằng phương thức đích có hoặc không có varargs.

### Vì sao ép (Object) sửa được?

~~~java
method.invoke(receiver, (Object) words);
~~~

Phép ép làm **kiểu tĩnh** của biểu thức đối số cuối trở thành `Object`, không còn là `Object[]`. Trình biên dịch phải dùng dạng variable arity và bọc giá trị này vào một `Object[]` chứa **một phần tử**.

Đáng chú ý, phép ép `(Object) words` **không thay bản chất runtime của mảng `words`**. Phần tử bên trong vẫn là `String[]` và vẫn có thể chuyển sang `String[]` tại phương thức đích. Phép ép chỉ tác động đến cách trình biên dịch đóng gói tham số cho lời gọi `invoke`.

### Vì sao ép (Object[]) KHÔNG sửa được?

~~~java
method.invoke(receiver, (Object[]) words);
~~~

Với `String[]`, ép kiểu này hợp lệ nhưng vẫn làm lời gọi nhận **một `Object[]` làm container của danh sách đối số**, nên sẽ trải các chuỗi thành nhiều tham số của phương thức đích. Nó chọn *đúng kiểu mảng bên ngoài*, trái với mục tiêu truyền chính mảng dữ liệu như một đối số.

Do đó, khi muốn truyền **một mảng dữ liệu** đến method đích, hãy ưu tiên `(Object) array` hoặc `new Object[]{array}`. Đừng tùy tiện đổi sang `(Object[]) array`.

## 4. Bảng tình huống cần phân biệt

Giả sử phương thức đích là `void accept(String[] values)`, biến `String[] values = {"red", "blue"};`, đối tượng `m` là `Method` mô tả đúng phương thức:

| Cách gọi | Số đối số mà method đích nhận | Kết quả |
| --- | --- | --- |
| `m.invoke(target, (Object) values)` | 1: chính mảng `String[]` | ✅ Đúng |
| `m.invoke(target, new Object[] { values })` | 1: chính mảng `String[]` | ✅ Đúng |
| `Object[] args = { values }; m.invoke(target, args)` | 1: chính mảng `String[]` | ✅ Đúng |
| `m.invoke(target, values)` | 2: `"red"` và `"blue"` | ❌ Sai số tham số |
| `m.invoke(target, (Object[]) values)` | 2: `"red"` và `"blue"` | ❌ Sai số tham số |
| `m.invoke(target, "red", "blue")` | 2 đối số String | ❌ Sai số tham số |
| `m.invoke(target, (Object) null)` | 1 đối số `null` | ✅ Đúng nếu phương thức đích cho phép nhận mảng `null` |
| `m.invoke(target, new Object[] { null })` | 1 đối số `null` | ✅ Đúng |
| `m.invoke(target, (Object[]) null)` | Danh sách đối số ở API `invoke` là `null`, dùng được cho method **không có** tham số | ❌ Không tương thích với method cần một tham số |

Để gọi phương thức nhận **hai `String` riêng lẻ**, ví dụ `void pair(String left, String right)`, cách `m.invoke(target, new Object[]{"red", "blue"})` lại **đúng** vì hai phần tử là hai tham số. Việc mảng `Object[]` bên ngoài chứa bao nhiêu phần tử phải khớp với **số tham số thật sự của phương thức đích**, chứ không dựa vào số lượng phần tử của một dữ liệu mảng bên trong.

Lưu ý với `null`: `(Object) null` bảo đảm **một đối số có giá trị null**; `(Object[]) null` là **một biến mảng đối số bị null** đưa cho `Method.invoke`, không phải một phần tử null. Nếu target không có tham số, Java cho phép `args` là `null` hoặc mảng độ dài 0; với target cần một tham số, hãy dùng dạng chứa một phần tử.

## 5. Ví dụ Java 17+ hoàn chỉnh: mảng String[], primitive int[], varargs và null

Tạo tệp **`ReflectionVarargsDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class ReflectionVarargsDemo {
    public static class Receiver {
        public String accept(String[] values) {
            return values == null
                    ? "array=null"
                    : "array=" + Arrays.toString(values);
        }

        public String collect(String... values) {
            return "varargs=" + Arrays.toString(values);
        }

        public String pair(String first, String second) {
            return "pair=" + first + "+" + second;
        }

        public String numbers(int[] values) {
            return "numbers=" + Arrays.toString(values);
        }

        public String noArguments() {
            return "no-arguments";
        }
    }

    @FunctionalInterface
    interface ReflectCall {
        Object execute() throws Exception;
    }

    private static void attempt(String label, ReflectCall call) {
        try {
            System.out.println(label + ": " + call.execute());
        } catch (Exception error) {
            System.out.println(label + ": "
                    + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Receiver receiver = new Receiver();
        String[] words = {"red", "blue"};

        Method accept = Receiver.class.getMethod(
                "accept", String[].class);
        Method collect = Receiver.class.getMethod(
                "collect", String[].class);
        Method pair = Receiver.class.getMethod(
                "pair", String.class, String.class);
        Method numbers = Receiver.class.getMethod(
                "numbers", int[].class);
        Method none = Receiver.class.getMethod("noArguments");

        System.out.println("accept parameters="
                + accept.getParameterCount());
        System.out.println("collect isVarArgs="
                + collect.isVarArgs());

        attempt("(Object) String[]",
                () -> accept.invoke(receiver, (Object) words));
        attempt("Object[]{String[]}",
                () -> accept.invoke(receiver, new Object[] { words }));
        attempt("(Object[]) String[]",
                () -> accept.invoke(receiver, (Object[]) words));

        attempt("target String...",
                () -> collect.invoke(receiver, (Object) words));
        attempt("target String... separately",
                () -> collect.invoke(receiver, "red", "blue"));

        attempt("two String parameters",
                () -> pair.invoke(receiver, (Object[]) words));

        attempt("primitive int[]",
                () -> numbers.invoke(receiver, (Object) new int[] {1, 2}));

        attempt("(Object) null",
                () -> accept.invoke(receiver, (Object) null));
        attempt("(Object[]) null for one parameter",
                () -> accept.invoke(receiver, (Object[]) null));
        attempt("no-arg method",
                () -> none.invoke(receiver));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp, với JDK 17 trở lên:

~~~bash
javac --release 17 ReflectionVarargsDemo.java
java ReflectionVarargsDemo
~~~

**Stdout được suy ra theo hợp đồng Java SE 17, có thể tái hiện bằng đoạn mã trên:**

~~~text
accept parameters=1
collect isVarArgs=true
(Object) String[]: array=[red, blue]
Object[]{String[]}: array=[red, blue]
(Object[]) String[]: IllegalArgumentException
target String...: varargs=[red, blue]
target String... separately: IllegalArgumentException
two String parameters: pair=red+blue
primitive int[]: numbers=[1, 2]
(Object) null: array=null
(Object[]) null for one parameter: IllegalArgumentException
no-arg method: no-arguments
~~~

### Giải thích code và output

- `accept.getParameterCount()` là `1` vì phương thức khai báo đúng một tham số `String[]`. Phần tử trong mảng dữ liệu không làm số tham số của phương thức tăng lên.
- `collect.isVarArgs()` là `true` vì khai báo nguồn là `String... values`. Trong bytecode, tham số cuối là `String[]`; dấu varargs được ghi trong metadata.
- `accept.invoke(receiver, (Object) words)` và `accept.invoke(receiver, new Object[]{words})` đều truyền một mảng `String[]` duy nhất.
- `(Object[]) words` làm `words` trở thành container `args` của Reflection, nên có hai chuỗi riêng; trong khi `accept(String[])` chỉ yêu cầu một tham số.
- `collect(String... values)` là **varargs của phương thức đích**. Tuy nhiên, `Method.invoke` **không tự gom `"red", "blue"` lại thành một `String[]` chỉ vì `collect.isVarArgs()` trả `true`**. Vì vậy truyền riêng hai chuỗi vẫn báo sai số tham số; cần truyền một `String[]` duy nhất.
- `pair(String,String)` có hai tham số riêng, nên trải `words` (qua `(Object[])`) lại vừa đúng.
- `int[]` là một đối tượng, nhưng **không phải** `Object[]`. Cách `(Object) new int[]{1,2}` truyền chính mảng nguyên thủy thành một đối số; không có auto-boxing từng phần tử `int` thành `Integer`.
- `accept.invoke(receiver, (Object) null)` có **một đối số null** tương thích với `String[]`, còn `accept.invoke(receiver, (Object[]) null)` truyền **mảng danh sách đối số null**, không cung cấp một phần tử như phương thức đích yêu cầu.
- Phương thức không tham số `noArguments()` được gọi bằng `none.invoke(receiver)`; nó không cần cung cấp mảng `args` ở mã nguồn.

Hàm `attempt` cố ý in **tên lớp ngoại lệ**, tránh phụ thuộc thông báo lỗi khác nhau giữa các phiên bản JDK. Khi Reflection gọi được method nhưng method đích tự ném ngoại lệ, `Method.invoke` bọc lỗi gốc thành `InvocationTargetException`; ví dụ này không làm phương thức đích ném ngoại lệ.

## 6. Array covariance, primitive arrays và Object[]

### 7.1. Mảng tham chiếu có tính hiệp biến

Trong Java, `String[]` là subtype của `Object[]`. Điều này giải thích tại sao:

~~~java
String[] words = {"a", "b"};
Object[] asObjects = words;
~~~

là hợp lệ, và tại sao `method.invoke(receiver, words)` có thể bị hiểu như đưa vào toàn bộ mảng đối số `Object[]`. Khi định truyền **mảng như dữ liệu**, hãy dùng `(Object) words` hoặc tạo wrapper `new Object[]{words}`.

Không nên cố “giải quyết” bằng cách đổ `String[]` vào một `Object[]` không có lớp bọc. Ví dụ:

~~~java
Object[] args = words; // mảng args có 2 phần tử, không phải 1
method.invoke(receiver, args); // vẫn hai đối số "a", "b"
~~~

Muốn mảng args có một phần tử:

~~~java
Object[] args = { words }; // length == 1; args[0] là String[]
method.invoke(receiver, args);
~~~

### 7.2. Mảng primitive không phải Object[]

`int[]`, `long[]`, `char[]` đều là object và có thể gán cho `Object`, nhưng **không** là subtype của `Object[]`:

~~~java
int[] nums = {1, 2, 3};
Object asOneObject = nums; // hợp lệ
// Object[] notAllowed = nums; // lỗi biên dịch
~~~

Vì vậy, lời gọi `method.invoke(receiver, nums)` thường được trình biên dịch đóng gói như một đối số `Object` duy nhất do `int[]` không thể trở thành `Object[]` trực tiếp. Tuy nhiên, dùng `(Object) nums` hoặc `new Object[]{nums}` cho rõ ý định và nhất quán với code xử lý nhiều loại mảng.

Một mảng số nguyên **không** tự biến thành `Integer[]`, và `Method.invoke` không tự boxing các phần tử bên trong mảng. Nếu phương thức đích nhận `Integer[]` thì truyền `int[]` vẫn sai kiểu; phải chủ động tạo/chuyển mảng phù hợp trước.

### 7.3. Mảng đa chiều cũng là một giá trị đối số

Ví dụ phương thức đích `void process(String[][] matrix)`:

~~~java
String[][] matrix = { {"a", "b"}, {"c"} };
Method m = Handler.class.getMethod("process", String[][].class);
m.invoke(handler, (Object) matrix);
~~~

`String[][]` cũng là một subtype của `Object[]` (vì mỗi phần tử là `String[]`), nên nếu không ép `(Object)`, nó có thể bị dùng làm container đối số của Reflection. Khi cần chuyển **toàn bộ ma trận là một đối số**, nguyên tắc vẫn giống `String[]`.

Ví dụ này cần lớp `Handler` chứa method `process(String[][])`; đây là minh họa cách truyền, không phải chương trình độc lập.

## 7. Truyền null và mảng rỗng chính xác

Ba khái niệm sau là khác nhau:

1. **Không có đối số cho phương thức đích**: `m.invoke(receiver)` hoặc `m.invoke(receiver, new Object[0])`.
2. **Có đúng một đối số mang giá trị null**: `m.invoke(receiver, (Object) null)` hoặc `m.invoke(receiver, new Object[]{null})`.
3. **Có đúng một đối số là mảng rỗng**: `m.invoke(receiver, (Object) new String[0])` khi phương thức đích nhận `String[]`.

Các giá trị này không thể thay thế cho nhau:

| Phương thức đích | Lời gọi reflection | Ý nghĩa |
| --- | --- | --- |
| `void noArgs()` | `invoke(receiver)` | Không đối số, hợp lệ |
| `void noArgs()` | `invoke(receiver, (Object[]) null)` | `args` null được chấp nhận cho phương thức không tham số |
| `void accept(String[] values)` | `invoke(receiver, (Object) null)` | Một tham số kiểu tham chiếu, giá trị null |
| `void accept(String[] values)` | `invoke(receiver, (Object) new String[0])` | Một tham số String[] hợp lệ, độ dài 0 |
| `void accept(String[] values)` | `invoke(receiver, new Object[]{null})` | Một tham số null hợp lệ |
| `void accept(String[] values)` | `invoke(receiver)` | Thiếu một đối số; lỗi số tham số |
| `void accept(String[] values)` | `invoke(receiver, (Object[]) null)` | Không cung cấp phần tử đối số cần thiết; lỗi số tham số |

Viết `m.invoke(receiver, null)` không có ép kiểu sẽ dễ gây nhầm lẫn ở **thời điểm biên dịch**: literal `null` có thể được coi là mảng `Object[]` của lời gọi varargs. Để truyền **một null đến phương thức đích**, luôn dùng `(Object) null` hoặc `new Object[]{null}`. Để truyền **một mảng rỗng**, tạo mảng **đúng kiểu của tham số đích**; `new Object[0]` bên ngoài có nghĩa không đối số, khác `new Object[]{new String[0]}`.

## 8. Bài tập tự kiểm tra kèm đáp án

**Bài 1.** Cho `void process(String[] names)`, `String[] names = {"An", "Binh"};` và `Method m` tương ứng. `m.invoke(receiver, names)` nhận mấy đối số ở cấp Reflection?

**Đáp án:** Hai phần tử của `names` có thể trở thành hai đối số của `Method.invoke` do `String[]` tương thích `Object[]`. Method đích cần đúng một `String[]` nên lời gọi không đúng. Dùng `m.invoke(receiver, (Object) names)`.

**Bài 2.** Với cùng phương thức đích, `m.invoke(receiver, new Object[]{names})` truyền bao nhiêu tham số?

**Đáp án:** Một tham số là mảng `String[]`, phù hợp chữ ký.

**Bài 3.** `void aggregate(String... names)` được lấy bằng `getMethod("aggregate", String[].class)`. `method.isVarArgs()` trả `true`. Có thể gọi `method.invoke(receiver, "An", "Binh")` để Reflection tự gom hai chuỗi không?

**Đáp án:** Không. Metadata varargs không khiến `Method.invoke` tự đóng gói `String[]` cho method đích. Cần `method.invoke(receiver, (Object) new String[]{"An","Binh"})` hoặc container `new Object[]{new String[]{"An","Binh"}}`.

**Bài 4.** Một method đích nhận đúng hai đối số `String left, String right`. Có một biến `String[] names` chứa đúng hai chuỗi. Viết hai cách gọi hợp lệ.

**Đáp án:** `m.invoke(receiver, names[0], names[1])` hoặc `m.invoke(receiver, (Object[]) names)`; ở trường hợp này trải hai phần tử thành hai đối số mới là điều cần.

**Bài 5.** Với method đích `void accept(int[] values)`, vì sao `int[]` không có cùng bẫy covariance như `String[]`?

**Đáp án:** `int[]` không phải `Object[]`. Nó là một `Object` duy nhất; với `Method.invoke`, có thể bọc thành một phần tử. Vẫn nên dùng `(Object) values` cho rõ ràng và tránh sự khác biệt khi thay kiểu mảng.

**Bài 6.** Phân biệt `m.invoke(receiver, (Object) null)` với `m.invoke(receiver, (Object[]) null)` nếu method đích nhận một `String[]`.

**Đáp án:** Cách thứ nhất truyền một đối số null, hợp lệ về kiểu tham chiếu; cách thứ hai gửi một mảng danh sách đối số null, không thỏa một tham số bắt buộc, nên bị lỗi số đối số.

**Bài 7.** Cho `void consume(Object[] values)`, bạn có `Object[] values = { "a", "b" };`. `consumeMethod.invoke(receiver, values)` có đúng không?

**Đáp án:** Không. Với mục tiêu truyền cả `values` làm một tham số kiểu `Object[]`, dùng `consumeMethod.invoke(receiver, (Object) values)` hoặc `new Object[]{values}`. Nếu bỏ cast, `Object[] values` bị dùng trực tiếp làm container hai đối số.

**Bài 8.** Khi `Method.invoke` ném `InvocationTargetException`, có thể kết luận là do mảng varargs bị trải không?

**Đáp án:** Không. `InvocationTargetException` có nghĩa method đích đã được thực thi và ném ngoại lệ. Lỗi đếm đối số/kiểu đối số ở cơ chế gọi Reflection thường là `IllegalArgumentException` trước khi method được gọi.

## 9. Ghi nhớ

**Đối với `Method.invoke(receiver, Object... args)`, mảng `Object[]` ngoài cùng luôn là danh sách tham số của phương thức đích.** Nếu đích cần **một tham số là mảng**, hãy đưa mảng dữ liệu vào **một phần tử** của danh sách đó:

~~~java
method.invoke(receiver, (Object) array);
method.invoke(receiver, new Object[] { array });
~~~

Đừng nhầm `String...` của phương thức đích với `Object...` của API Reflection; mỗi cơ chế đóng gói diễn ra trong **một lời gọi khác nhau**. Đừng nhầm `(Object) array` (một đối số) với `(Object[]) array` (toàn bộ mảng đối số). Khi chưa chắc, hãy kiểm tra `getParameterTypes()` và tạo `Object[]` bên ngoài tường minh.

**Tài liệu chuẩn:**

- [Java SE 17: `Method.invoke` và `Method.isVarArgs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html).
- [Dev.java: Invoking Methods with Reflection](https://dev.java/learn/reflection/methods/).
- [JLS §15.12.2.4 và §15.12.4.2 — Variable Arity Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html).