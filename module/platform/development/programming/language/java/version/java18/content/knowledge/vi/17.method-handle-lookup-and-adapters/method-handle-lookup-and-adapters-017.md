# Kiểm tra handle.type() sau từng bước adapter để định vị lỗi ghép chữ ký

> **Chương:** Lookup và adapter  
> **Module:** JAVA_VERSION_JAVA18 — khám phá các hợp đồng API Java 18 còn áp dụng trên JDK hiện đại, đặc biệt việc kiểm chứng reflection và MethodHandle trên JDK đang dùng.  
> **Mục tiêu:** Đọc chính xác `MethodType` của từng `MethodHandle` sau `Lookup` và sau mỗi adapter; dự đoán được thay đổi ở danh sách tham số/kiểu trả về; phân biệt lỗi tạo adapter, lỗi `invokeExact` và lỗi phát sinh từ code đích.

## 1. Vấn đề: ghép adapter đúng cú pháp nhưng sai chữ ký

Một `MethodHandle` có thể được biến đổi qua nhiều adapter:

~~~text
Lookup.findVirtual(...)
    |
    v
bindTo(receiver)
    |
    v
insertArguments(...)
    |
    v
dropArguments(...)
    |
    v
permuteArguments(...)
    |
    v
filterArguments(...)
    |
    v
filterReturnValue(...)
    |
    v
asType(...)
    |
    v
invokeExact(...)
~~~

Mỗi adapter tạo một handle mới với một kiểu `MethodType` có thể khác handle đầu vào. Nếu chỉ kiểm tra ở cuối chuỗi, một lỗi thứ tự tham số hoặc kiểu dữ liệu rất khó truy ra bước bắt đầu sai.

Ví dụ, một method đích có chữ ký Java:

~~~java
int combine(int x, int y);
~~~

Khi lấy bằng `findVirtual`, handle không chỉ nhận hai `int` mà còn có **receiver**:

~~~text
Chữ ký method Java: (int,int)int
MethodHandle.type(): (Calculator,int,int)int
~~~

Sau khi gắn receiver bằng `bindTo`, kiểu mới là `(int,int)int`. Nếu tiếp tục gắn giá trị cố định cho tham số thứ hai bằng `insertArguments`, kiểu chỉ còn `(int)int`. Gọi `invokeExact` như thể handle vẫn nhận hai `int` sẽ thất bại, dù method đích ban đầu hoàn toàn hợp lệ.

**Nguyên tắc trung tâm của bài:** Sau mỗi phép biến đổi, xác nhận `handle.type()` **trước khi** viết lời gọi đến handle mới.

## 2. MethodType ghi nhận điều gì?

`MethodType` là mô tả bất biến gồm một kiểu trả về và một danh sách kiểu tham số có thứ tự. Có thể tạo và so sánh bằng:

~~~java
MethodType expected = MethodType.methodType(
        int.class, Calculator.class, int.class, int.class);

MethodType actual = handle.type();
if (!actual.equals(expected)) {
    throw new AssertionError("Expected " + expected + ", got " + actual);
}
~~~

Ý nghĩa `MethodType.methodType(R.class, P1.class, P2.class)` là `(P1,P2)R`, tức **kiểu trả về đứng trước** khi khởi tạo đối tượng `MethodType`.

Một số API hữu ích khi debug:

| API | Câu hỏi trả lời |
| --- | --- |
| `handle.type()` | Handle hiện tại yêu cầu kiểu gì? |
| `type.returnType()` | Kiểu trả về chính xác là gì, kể cả `void.class`? |
| `type.parameterCount()` | Handle hiện tại nhận bao nhiêu tham số? |
| `type.parameterType(i)` | Tham số thứ `i` có kiểu nào? |
| `type.parameterList()` | Toàn bộ danh sách kiểu tham số theo thứ tự? |
| `type.equals(expected)` | Chữ ký có khớp chính xác với dự kiến không? |

`MethodType` không chứa **tên** của tham số, chỉ chứa **kiểu** và thứ tự. Vì vậy, hai tham số cùng là `int` có thể vô tình bị hoán đổi mà type vẫn khớp. Cần kiểm tra **cả kiểu lẫn kết quả**.

## 3. Phân biệt kiểu method đích, kiểu Lookup và kiểu handle

Xét lớp:

~~~java
public static final class Calculator {
    private final int base;

    public Calculator(int base) {
        this.base = base;
    }

    public int combine(int x, int y) {
        return base + x * 10 + y;
    }
}
~~~

Khi tìm virtual method:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle raw = lookup.findVirtual(
        Calculator.class,
        "combine",
        MethodType.methodType(int.class, int.class, int.class));
~~~

`MethodType` truyền cho `findVirtual` là `(int,int)int` vì receiver không nằm trong formal parameters của method Java. Nhưng `raw.type()` là `(Calculator,int,int)int` vì handle cần receiver ở vị trí đầu.

~~~java
assertType(raw, MethodType.methodType(
        int.class, Calculator.class, int.class, int.class));
~~~

Đối với static method, `findStatic` không thêm receiver. Đối với constructor, `findConstructor` dùng return type `void` lúc lookup nhưng handle được trả về có return type là lớp được khởi tạo. Vì vậy, hãy luôn đọc `type()` từ **đối tượng handle trả về**; không suy luận chữ ký sau adapter chỉ dựa vào signature gốc.

## 4. Quy tắc biến đổi kiểu của các adapter quan trọng

| Adapter | Tác động lên chữ ký | Ghi chú thường gây lỗi |
| --- | --- | --- |
| `bindTo(value)` | Gắn **tham số đầu tiên kiểu tham chiếu** và loại nó khỏi danh sách tham số | Dùng cho receiver/các tham số tham chiếu; không dùng để gắn trực tiếp một primitive parameter. |
| `insertArguments(target, pos, values...)` | Gắn trước một hoặc nhiều giá trị ở vị trí `pos`, loại các tham số tương ứng khỏi chữ ký | Vị trí tính theo **kiểu hiện tại của target**, không phải kiểu trước adapter. |
| `dropArguments(target, pos, types...)` | **Thêm** các tham số giả ở vị trí `pos`; target sẽ bỏ qua giá trị của chúng | Tên dễ gây nhầm: hàm này làm chữ ký *dài hơn*, không xóa tham số khỏi chữ ký. |
| `permuteArguments(target, newType, reorder...)` | Tạo chữ ký mới, sắp xếp/nhân bản/bỏ qua nguồn đối số theo chỉ số | Không tự chuyển đổi kiểu. Kiểu từng vị trí được ánh xạ phải khớp chính xác. |
| `filterArguments(target, pos, filters...)` | Thay kiểu đầu vào của các vị trí target bằng kiểu đầu vào của các filter tương ứng | Return type của filter phải bằng đúng kiểu tham số mà target đang cần. |
| `filterReturnValue(target, filter)` | Giữ danh sách tham số, đổi return type thành return type của filter | Filter phải nhận đúng kiểu return của target; nếu target trả `void`, filter phải không có tham số. |
| `asType(newType)` | Chuyển đổi chữ ký sang `newType` nếu kiểu có thể thích ứng | Không đổi số tham số; các phép cast/unbox có thể gây exception khi *gọi*. |
| `asCollector(arrayType, n)` | Thay một tham số mảng ở cuối bằng `n` tham số phần tử | Khi gọi, gom các tham số thành mảng trước khi chuyển cho target. |
| `asSpreader(arrayType, n)` | Thay `n` tham số ở cuối bằng một tham số mảng | Khi gọi, trải các phần tử mảng để chuyển cho target. |

Các adapter này là API đã có từ những JDK trước và vẫn áp dụng trên JDK 18/26. Bài dùng các biến thể cuối-mảng đơn giản của collector/spreader; một số overload có chỉ số vị trí cũng được hỗ trợ trên JDK hiện đại.

## 5. Pipeline từng bước: từ receiver đến chữ ký động

Giả sử `Calculator` khởi tạo với `base = 100` và ta muốn gọi `combine(4, 7)`. Giá trị mong đợi là `100 + 4 * 10 + 7 = 147`.

### Bước 0 — Lookup: thêm receiver

~~~java
MethodHandle raw = lookup.findVirtual(
        Calculator.class, "combine",
        MethodType.methodType(int.class, int.class, int.class));

// (Calculator,int,int)int
~~~

### Bước 1 — bindTo: gắn receiver

~~~java
Calculator calculator = new Calculator(100);
MethodHandle bound = raw.bindTo(calculator);

// (int,int)int
int result = (int) bound.invokeExact(4, 7); // 147
~~~

`bindTo` không gọi method đích ngay. Nó tạo handle mới chứa receiver đã cố định. Vì `Calculator` là kiểu tham chiếu, việc gắn receiver hợp lệ; nếu muốn gắn một giá trị `int` thì dùng `insertArguments`.

### Bước 2 — insertArguments: gắn giá trị y = 7

~~~java
MethodHandle oneArg = MethodHandles.insertArguments(bound, 1, 7);

// (int)int
int result = (int) oneArg.invokeExact(4); // 147
~~~

Vị trí `1` trỏ đến tham số `y` trong **handle `bound`**. Tham số `x` vẫn ở vị trí `0`. Không truyền `y` thêm một lần nữa khi gọi `oneArg`.

### Bước 3 — dropArguments: thêm một tham số bị bỏ qua

~~~java
MethodHandle withTag = MethodHandles.dropArguments(
        oneArg, 0, String.class);

// (String,int)int
int result = (int) withTag.invokeExact("audit", 4); // 147
~~~

`"audit"` là tham số giả để thích ứng với một giao diện gọi cần thêm một tag. Method `combine` không nhận tag; adapter bỏ qua giá trị này. `dropArguments` **thêm** tham số `String` thay vì “drop” một tham số đang có.

### Bước 4 — permuteArguments: đổi thứ tự đối số bên ngoài

~~~java
MethodHandle reordered = MethodHandles.permuteArguments(
        withTag,
        MethodType.methodType(int.class, int.class, String.class),
        1, 0);

// (int,String)int
int result = (int) reordered.invokeExact(4, "audit"); // 147
~~~

Thứ tự đối số đầu vào mới là `(int,String)` nhưng target `withTag` cần `(String,int)`. Dãy chỉ số `1, 0` có nghĩa:

~~~text
Đầu vào adapter:  [ int 4, String "audit" ]
                       0          1
                           |
                       reorder [1,0]
                           |
Đối số đến target: [ String "audit", int 4 ]
~~~

Đừng diễn giải `reorder` là bản đồ từ đầu vào sang đầu ra theo chiều ngược. Mỗi phần tử `reorder[j]` chỉ định **đối số đầu vào nào** sẽ cung cấp **tham số thứ `j` của target**. `permuteArguments` không tự cast hay unbox để sửa một chỉ số hoán vị sai kiểu.

### Bước 5 — filterArguments: String đầu vào thành int

Giả sử một API ngoài cung cấp giá trị `x` dạng chuỗi `"4"`. Ta cần biến đổi trước khi gọi `reordered`:

~~~java
MethodHandle parse = lookup.findStatic(
        Integer.class, "parseInt",
        MethodType.methodType(int.class, String.class));

// parse.type() = (String)int
MethodHandle parsed = MethodHandles.filterArguments(
        reordered, 0, parse);

// (String,String)int
int result = (int) parsed.invokeExact("4", "audit"); // 147
~~~

Vì tham số thứ 0 của `reordered` là `int`, filter phải **trả về int**. Filter nhận `String`, nên tham số thứ 0 trong chữ ký mới trở thành `String`. Tham số thứ 1 vẫn là tag `String`.

Nếu đưa vào một filter trả về `String`, việc ghép adapter sẽ thất bại ở bước `filterArguments`; không cần chờ đến `invokeExact`.

### Bước 6 — filterReturnValue: int kết quả thành String

Viết một method:

~~~java
public static String decorate(int number) {
    return "value=" + number;
}
~~~

Lấy handle và ghép:

~~~java
MethodHandle decorate = lookup.findStatic(
        AdapterTypeTraceDemo.class, "decorate",
        MethodType.methodType(String.class, int.class));

// decorate.type() = (int)String
MethodHandle formatted = MethodHandles.filterReturnValue(
        parsed, decorate);

// (String,String)String
String result = (String) formatted.invokeExact("4", "audit");
// "value=147"
~~~

Lệnh `filterReturnValue` không đổi danh sách tham số. Nó yêu cầu filter đầu ra nhận chính xác kiểu mà `parsed` trả về, tức `int`. Nếu filter nhận `long` mà target trả `int`, phép ghép này không tự widening; hãy dùng `asType` một cách tường minh ở đúng bước nếu cần.

### Bước 7 — asType: giao diện gọi Object/Object

Đôi khi framework chỉ truyền các giá trị ở dạng `Object`. Khi đó có thể chuyển handle sang kiểu tổng quát:

~~~java
MethodHandle generic = formatted.asType(
        MethodType.methodType(
                Object.class, Object.class, Object.class));

// (Object,Object)Object
Object result = (Object) generic.invokeExact(
        (Object) "4", (Object) "audit");
// "value=147"
~~~

Ở đây `asType` chấp nhận chuyển `Object -> String` ở hai đối số và `String -> Object` ở kết quả. **Chữ ký của handle mới là `(Object,Object)Object`**, không còn là `(String,String)String`.

Nếu truyền `Integer.valueOf(4)` ở vị trí thứ nhất, adapter tạo thành công nhưng khi gọi sẽ cố cast giá trị đó sang `String` và có thể ném `ClassCastException`. Đây là lỗi **giá trị runtime**, khác với lỗi ghép chữ ký.

### Bảng tổng kết từng bước

| Bước | Biến handle | `handle.type()` | Lời gọi đúng và kết quả |
| --- | --- | --- | --- |
| 0 | `raw` | `(Calculator,int,int)int` | `raw.invokeExact(calculator,4,7)` → 147 |
| 1 | `bound` | `(int,int)int` | `bound.invokeExact(4,7)` → 147 |
| 2 | `oneArg` | `(int)int` | `oneArg.invokeExact(4)` → 147 |
| 3 | `withTag` | `(String,int)int` | `withTag.invokeExact("audit",4)` → 147 |
| 4 | `reordered` | `(int,String)int` | `reordered.invokeExact(4,"audit")` → 147 |
| 5 | `parsed` | `(String,String)int` | `parsed.invokeExact("4","audit")` → 147 |
| 6 | `formatted` | `(String,String)String` | `formatted.invokeExact("4","audit")` → "value=147" |
| 7 | `generic` | `(Object,Object)Object` | `generic.invokeExact((Object)"4",(Object)"audit")` → "value=147" |

Điểm mấu chốt không phải ghi nhớ bảng bằng tay, mà là **in/so sánh `type()` ngay sau từng adapter** trong code, rồi chỉ viết lời gọi với chữ ký đã được xác nhận.

## 6. Code Java hoàn chỉnh: tự kiểm tra kiểu và kết quả

Lưu thành `AdapterTypeTraceDemo.java`. Chương trình chỉ dùng `java.base`, tương thích Java 18 và các JDK hiện đại.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.Objects;

public class AdapterTypeTraceDemo {
    public static final class Calculator {
        private final int base;

        public Calculator(int base) {
            this.base = base;
        }

        public int combine(int x, int y) {
            return base + x * 10 + y;
        }
    }

    public static String decorate(int number) {
        return "value=" + number;
    }

    public static int sum3(int a, int b, int c) {
        return a + b + c;
    }

    public static int sumArray(int[] values) {
        int total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    private static void checkType(
            String stage, MethodHandle handle, MethodType expected) {
        MethodType actual = handle.type();
        if (!actual.equals(expected)) {
            throw new AssertionError(stage + ": expected "
                    + expected + ", got " + actual);
        }
        System.out.println(stage + " type = " + actual);
    }

    private static void checkValue(
            String stage, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(stage + ": expected "
                    + expected + ", got " + actual);
        }
        System.out.println(stage + " result = " + actual);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Calculator calculator = new Calculator(100);

        MethodHandle raw = lookup.findVirtual(
                Calculator.class,
                "combine",
                MethodType.methodType(
                        int.class, int.class, int.class));
        checkType("0.lookup", raw, MethodType.methodType(
                int.class, Calculator.class, int.class, int.class));
        checkValue("0.lookup", 147,
                (int) raw.invokeExact(calculator, 4, 7));

        MethodHandle bound = raw.bindTo(calculator);
        checkType("1.bindTo", bound, MethodType.methodType(
                int.class, int.class, int.class));
        checkValue("1.bindTo", 147,
                (int) bound.invokeExact(4, 7));

        MethodHandle oneArg = MethodHandles.insertArguments(
                bound, 1, 7);
        checkType("2.insertArguments", oneArg,
                MethodType.methodType(int.class, int.class));
        checkValue("2.insertArguments", 147,
                (int) oneArg.invokeExact(4));

        MethodHandle withTag = MethodHandles.dropArguments(
                oneArg, 0, String.class);
        checkType("3.dropArguments", withTag, MethodType.methodType(
                int.class, String.class, int.class));
        checkValue("3.dropArguments", 147,
                (int) withTag.invokeExact("audit", 4));

        MethodHandle reordered = MethodHandles.permuteArguments(
                withTag,
                MethodType.methodType(
                        int.class, int.class, String.class),
                1, 0);
        checkType("4.permuteArguments", reordered, MethodType.methodType(
                int.class, int.class, String.class));
        checkValue("4.permuteArguments", 147,
                (int) reordered.invokeExact(4, "audit"));

        MethodHandle parse = lookup.findStatic(
                Integer.class, "parseInt",
                MethodType.methodType(int.class, String.class));
        checkType("filter.parseInt", parse,
                MethodType.methodType(int.class, String.class));

        MethodHandle parsed = MethodHandles.filterArguments(
                reordered, 0, parse);
        checkType("5.filterArguments", parsed, MethodType.methodType(
                int.class, String.class, String.class));
        checkValue("5.filterArguments", 147,
                (int) parsed.invokeExact("4", "audit"));

        MethodHandle decorate = lookup.findStatic(
                AdapterTypeTraceDemo.class,
                "decorate",
                MethodType.methodType(String.class, int.class));
        checkType("filter.decorate", decorate,
                MethodType.methodType(String.class, int.class));

        MethodHandle formatted = MethodHandles.filterReturnValue(
                parsed, decorate);
        checkType("6.filterReturnValue", formatted,
                MethodType.methodType(
                        String.class, String.class, String.class));
        checkValue("6.filterReturnValue", "value=147",
                (String) formatted.invokeExact("4", "audit"));

        MethodHandle generic = formatted.asType(
                MethodType.methodType(
                        Object.class, Object.class, Object.class));
        checkType("7.asType", generic, MethodType.methodType(
                Object.class, Object.class, Object.class));
        checkValue("7.asType", "value=147",
                (Object) generic.invokeExact(
                        (Object) "4", (Object) "audit"));

        // Lỗi ghép adapter: thứ tự đổi kiểu không tương thích.
        try {
            MethodHandles.permuteArguments(
                    withTag,
                    MethodType.methodType(
                            int.class, String.class, int.class),
                    1, 0);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("bad permutation: IllegalArgumentException");
        }

        // Lỗi ghép adapter: filter trả String nhưng target cần int.
        try {
            MethodHandles.filterArguments(reordered, 0, decorate);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("bad argument filter: IllegalArgumentException");
        }

        // Lỗi tạo adapter: không thể asType để đổi số tham số.
        try {
            parsed.asType(
                    MethodType.methodType(int.class, String.class));
            throw new AssertionError("Expected WrongMethodTypeException");
        } catch (WrongMethodTypeException expected) {
            System.out.println("bad asType arity: WrongMethodTypeException");
        }

        // Lỗi invokeExact: call site nhận int, handle cần String.
        try {
            int unexpected = (int) parsed.invokeExact(4, "audit");
            throw new AssertionError(
                    "Expected WrongMethodTypeException: " + unexpected);
        } catch (WrongMethodTypeException expected) {
            System.out.println("bad invokeExact type: WrongMethodTypeException");
        }

        // Adapter đã tạo hợp lệ, nhưng cast Object -> String thất bại.
        try {
            Object unexpected = (Object) generic.invokeExact(
                    (Object) Integer.valueOf(4), (Object) "audit");
            throw new AssertionError(
                    "Expected ClassCastException: " + unexpected);
        } catch (ClassCastException expected) {
            System.out.println("bad runtime cast: ClassCastException");
        }

        // Exception từ code filter được chuyển ra trực tiếp.
        try {
            int unexpected = (int) parsed.invokeExact("NaN", "audit");
            throw new AssertionError(
                    "Expected NumberFormatException: " + unexpected);
        } catch (NumberFormatException expected) {
            System.out.println("bad parsed value: NumberFormatException");
        }

        // Ví dụ độc lập: collector/spreader với mảng int.
        MethodHandle sumArray = lookup.findStatic(
                AdapterTypeTraceDemo.class, "sumArray",
                MethodType.methodType(int.class, int[].class));
        MethodHandle collector = sumArray.asCollector(int[].class, 3);
        checkType("8.asCollector", collector, MethodType.methodType(
                int.class, int.class, int.class, int.class));
        checkValue("8.asCollector", 6,
                (int) collector.invokeExact(1, 2, 3));

        MethodHandle sum3 = lookup.findStatic(
                AdapterTypeTraceDemo.class, "sum3",
                MethodType.methodType(
                        int.class, int.class, int.class, int.class));
        MethodHandle spreader = sum3.asSpreader(int[].class, 3);
        checkType("9.asSpreader", spreader,
                MethodType.methodType(int.class, int[].class));
        checkValue("9.asSpreader", 6,
                (int) spreader.invokeExact(new int[]{1, 2, 3}));

        try {
            int unexpected = (int) spreader.invokeExact(
                    new int[]{1, 2});
            throw new AssertionError(
                    "Expected IllegalArgumentException: " + unexpected);
        } catch (IllegalArgumentException expected) {
            System.out.println("wrong array length: IllegalArgumentException");
        }

        System.out.println("ALL CHECKS PASSED");
    }
}
~~~

Chạy với JDK 18 trở lên:

~~~bash
javac AdapterTypeTraceDemo.java
java AdapterTypeTraceDemo
~~~

Kết quả chính được kỳ vọng:

~~~text
0.lookup type = (Calculator,int,int)int
0.lookup result = 147
1.bindTo type = (int,int)int
1.bindTo result = 147
2.insertArguments type = (int)int
2.insertArguments result = 147
3.dropArguments type = (String,int)int
3.dropArguments result = 147
4.permuteArguments type = (int,String)int
4.permuteArguments result = 147
filter.parseInt type = (String)int
5.filterArguments type = (String,String)int
5.filterArguments result = 147
filter.decorate type = (int)String
6.filterReturnValue type = (String,String)String
6.filterReturnValue result = value=147
7.asType type = (Object,Object)Object
7.asType result = value=147
bad permutation: IllegalArgumentException
bad argument filter: IllegalArgumentException
bad asType arity: WrongMethodTypeException
bad invokeExact type: WrongMethodTypeException
bad runtime cast: ClassCastException
bad parsed value: NumberFormatException
8.asCollector type = (int,int,int)int
8.asCollector result = 6
9.asSpreader type = (int[])int
9.asSpreader result = 6
wrong array length: IllegalArgumentException
ALL CHECKS PASSED
~~~

`MethodType.toString()` có thể hiển thị kiểu lớp bằng tên rút gọn. **Tiêu chí kiểm chứng quyết định là phép `equals(expected)` trên `MethodType`, không phải so chuỗi log**.

Ví dụ là chương trình tự kiểm tra: nếu một bước có kiểu sai, một phép tính khác dự kiến, hoặc một trường hợp lỗi chủ đích không xảy ra, chương trình ném `AssertionError` thay vì chỉ in kết quả. Đây là minh họa học tập; chưa thay thế kiểm thử tự động trong build của dự án.

## 7. asCollector và asSpreader: hai hướng biến đổi mảng

Hai adapter này được tách khỏi pipeline chính để không nhầm chiều biến đổi.

### asCollector: từ nhiều phần tử thành một tham số mảng

Method đích:

~~~java
public static int sumArray(int[] values) {
    int sum = 0;
    for (int value : values) sum += value;
    return sum;
}
~~~

Lookup trả handle `(int[])int`. Khi gọi:

~~~java
MethodHandle collector = sumArrayHandle.asCollector(int[].class, 3);

// Từ (int[])int thành (int,int,int)int.
int sum = (int) collector.invokeExact(1, 2, 3); // 6
~~~

Adapter nhận ba `int`, tạo mảng ba phần tử và chuyển mảng đó cho method đích. `arrayLength = 3` là số phần tử mà adapter cần gom, không phải số lượng mảng.

### asSpreader: từ một mảng thành nhiều đối số

Method đích:

~~~java
public static int sum3(int a, int b, int c) {
    return a + b + c;
}
~~~

Lookup trả handle `(int,int,int)int`. Khi gọi:

~~~java
MethodHandle spreader = sum3Handle.asSpreader(int[].class, 3);

// Từ (int,int,int)int thành (int[])int.
int sum = (int) spreader.invokeExact(new int[]{1, 2, 3}); // 6
~~~

Mảng truyền vào `spreader` phải có đúng ba phần tử. Mảng độ dài khác có thể gây `IllegalArgumentException` khi **gọi adapter**, dù việc tạo adapter với `3` hoàn toàn hợp lệ.

So sánh:

| Adapter | Target trước biến đổi | Adapter sau biến đổi | Dữ liệu truyền vào |
| --- | --- | --- | --- |
| `asCollector(int[].class, 3)` | `(int[])int` | `(int,int,int)int` | Ba `int` riêng |
| `asSpreader(int[].class, 3)` | `(int,int,int)int` | `(int[])int` | Một `int[]` đúng ba phần tử |

Đây không phải cơ chế `Object...` của `Method.invoke`. Với `MethodHandle.invokeExact`, **kiểu array ở call site cũng là một phần của MethodType chính xác**.

## 8. Phân loại lỗi: tạo adapter, invokeExact hay chạy bên trong?

Các lỗi khác nhau thường chỉ ra **vị trí** khác nhau trong pipeline:

| Giai đoạn | Ví dụ lỗi | Exception tiêu biểu | Cách khoanh vùng |
| --- | --- | --- | --- |
| Lookup | Tên method không tồn tại hoặc descriptor sai | `NoSuchMethodException` | Kiểm tra tên và `MethodType` dùng trong `findStatic/findVirtual`. |
| Lookup | Thiếu quyền truy cập đến member | `IllegalAccessException` | Kiểm tra `Lookup`, visibility, exports/opens phù hợp. |
| Ghép `insertArguments` | Vị trí `pos` ngoài phạm vi hoặc giá trị bind không phù hợp | `IllegalArgumentException` hoặc lỗi chuyển kiểu | In `target.type()`, kiểm tra `pos` và kiểu từng giá trị. |
| Ghép `permuteArguments` | Chỉ số ánh xạ không đúng, kiểu source-target không đồng nhất | `IllegalArgumentException` | Viết lại bảng chỉ số `reorder[j]` theo thứ tự target. |
| Ghép `filterArguments` | Filter trả về sai kiểu tham số của target | `IllegalArgumentException` | So `filter.type().returnType()` với `target.type().parameterType(pos)`. |
| Ghép `filterReturnValue` | Filter nhận kiểu khác return type của target | `IllegalArgumentException` | So `filter.type().parameterType(0)` với `target.type().returnType()`. |
| Ghép `asType` | Arity khác nhau hoặc conversion không thể thích ứng | `WrongMethodTypeException` | So toàn bộ `oldType` và `newType`. |
| Gọi `invokeExact` | Call site có tham số **hoặc return type** khác `handle.type()` | `WrongMethodTypeException` | So kiểu tĩnh tại call site, không chỉ kiểu runtime của value. |
| Gọi `asType` adapter | `Object` thực tế không cast được sang `String` | `ClassCastException` | Xem kiểu runtime của giá trị đầu vào. |
| Gọi `asSpreader` | Độ dài mảng không bằng `arrayLength` | `IllegalArgumentException` | Kiểm tra độ dài mảng ở runtime. |
| Thực thi filter/target | `Integer.parseInt("NaN")` | `NumberFormatException` | Lỗi từ code được gọi; không mặc định coi là lỗi chữ ký. |

Một số phép chuyển kiểu có thể ném exception khác như `NullPointerException` khi unbox một giá trị `null`, hoặc `ClassCastException` cho reference cast. Thông báo exception có thể khác theo JDK, nhưng vị trí adapter đang được tạo và `handle.type()` vẫn là bằng chứng đáng tin cậy để chẩn đoán.

### 8.1. invokeExact còn kiểm tra kiểu trả về

Ví dụ:

~~~java
MethodHandle h = lookup.findStatic(
        Integer.class, "parseInt",
        MethodType.methodType(int.class, String.class));

int ok = (int) h.invokeExact("42"); // Hợp lệ.
long wrong = (long) h.invokeExact("42"); // WrongMethodTypeException.
~~~

Lệnh `invokeExact` thứ hai yêu cầu descriptor `(String)long` tại call site, trong khi `h.type()` là `(String)int`. Việc `int` có thể widening thành `long` trong Java **không** giúp `invokeExact`: hãy dùng `invoke` hoặc tạo `h.asType(MethodType.methodType(long.class, String.class))` nếu muốn conversion rõ ràng.

### 8.2. Adapter không thay đổi method đích gốc

`asType`, `bindTo`, `filterArguments` và các tổ hợp khác trả về **handle mới**; chúng không sửa `MethodType` của handle nguồn:

~~~java
MethodHandle before = raw;
MethodHandle after = raw.bindTo(calculator);

// before.type(): (Calculator,int,int)int
// after.type():  (int,int)int
~~~

Điều này cho phép giữ nhiều adapter khác nhau trên cùng một handle gốc. Khi quản lý pipeline, nên dùng tên biến riêng cho từng stage để debug dễ hơn thay vì gán đè một biến `handle` rồi mất dấu bước biến đổi.

## 9. Quy trình định vị lỗi theo từng bước

Khi gặp `WrongMethodTypeException` hoặc `IllegalArgumentException` sau một chuỗi adapter, làm theo quy trình:

1. **Lấy kiểu gốc:** in `lookupHandle.type()` ngay khi lookup thành công.
2. **Dự đoán stage tiếp theo:** ghi `MethodType` mong đợi theo quy tắc của adapter.
3. **Ghép một adapter duy nhất:** không thêm ba adapter cùng lúc trước khi kiểm tra.
4. **So khớp kiểu thực tế:** dùng `handle.type().equals(expected)`. Nếu sai, sửa ngay tại bước hiện tại.
5. **Kiểm tra giá trị:** gọi thử bằng một bộ đầu vào đơn giản, kiểm tra return value hoặc side effect. Điều này đặc biệt quan trọng với `permuteArguments` khi các tham số cùng kiểu.
6. **Tách lỗi tạo và lỗi gọi:** nếu exception xảy ra khi tạo adapter, đừng tìm lỗi bên trong target; nếu tạo thành công nhưng `invokeExact` lỗi, so lại kiểu tĩnh ở call site.
7. **Tách conversion runtime:** nếu `asType` hợp lệ nhưng giá trị thực tế không cast/unbox được, đó là lỗi runtime input.
8. **Rà ngoại lệ ứng dụng:** filter/target có thể ném exception của chính nó; `MethodHandle` truyền throwable này trực tiếp, không bọc như `java.lang.reflect.Method.invoke`.
9. **Đọc Javadoc của đúng phiên bản JDK:** xác nhận quyền truy cập và ràng buộc adapter trên runtime được triển khai.

### Hàm kiểm tra dùng lại

~~~java
static MethodHandle requireType(
        String stage, MethodHandle h, MethodType expected) {
    if (!h.type().equals(expected)) {
        throw new IllegalStateException(stage
                + ": expected " + expected
                + ", actual " + h.type());
    }
    return h;
}
~~~

Có thể sử dụng trực tiếp sau mỗi adapter:

~~~java
MethodHandle bound = requireType(
        "bindTo",
        raw.bindTo(calculator),
        MethodType.methodType(int.class, int.class, int.class));
~~~

Hàm này giúp lỗi được gắn với **tên stage**, tránh để lỗi dồn đến lời gọi cuối của pipeline.

## 10. Các vấn đề thiết kế đáng lưu ý

### 10.1. Không tự động áp dụng asType cho mọi lỗi

Nếu `permuteArguments` sai chỉ số nhưng vẫn cho ra một chữ ký có các kiểu tương thích, `asType` không thể biết thứ tự nghiệp vụ đúng để sửa. Ví dụ hoán đổi hai tham số cùng kiểu `int` có thể cho kết quả sai **mà không có exception**. Hãy kiểm tra mapping và test kết quả.

Nếu adapter thật sự cần chuyển đổi `String -> int`, hãy dùng `filterArguments` với parser (hoặc chuẩn hóa từ trước), không kỳ vọng `asType` biến chuỗi `"42"` thành `int`: `asType` không thực hiện parse số từ text.

### 10.2. Chọn adapter theo nhu cầu, không ghép càng nhiều càng tốt

Adapter giúp xây dựng runtime linh hoạt, nhưng cũng có chi phí tạo handle, allocation và cơ hội tối ưu hóa khác nhau. Nếu ứng dụng gọi lặp lại một pipeline ổn định, tạo adapter **một lần** rồi cache thường có ý nghĩa hơn việc ghép lại trong mỗi request.

JEP 416 từ Java 18 thay đổi cách triển khai Core Reflection dựa trên Method Handles; điều đó **không thay đổi** hợp đồng `MethodHandle.type()`, `invokeExact` hay các phép ghép adapter trong bài. Nếu muốn so hiệu năng giữa reflection và MethodHandle, phải benchmark theo workload thực thay vì giả định adapter luôn nhanh hơn.

### 10.3. Không dùng private access hoặc API nội bộ để làm ví dụ

Ví dụ sử dụng public methods và `MethodHandles.lookup()` trong cùng lớp. Trên JDK hiện đại, kiểm tra quyền tại lookup vẫn quan trọng: method inaccessible có thể dẫn tới `IllegalAccessException`. Khi truy cập thành viên từ module khác, cần sử dụng exports/opens và `privateLookupIn` đúng theo hợp đồng; không dựa vào hack `setAccessible` hoặc quyền truy cập nội bộ JDK cũ.

## 11. Câu hỏi tự kiểm tra

1. `MethodType` chứa những thành phần nào? Tại sao chỉ so tên method là chưa đủ?
2. Vì sao `findVirtual` với method `combine(int,int)` trả handle `(Calculator,int,int)int`?
3. `bindTo(calculator)` đổi danh sách tham số thế nào?
4. Khác biệt giữa `bindTo` và `insertArguments` là gì?
5. Vì sao `dropArguments` làm chữ ký dài hơn dù có chữ “drop”?
6. Dãy `reorder = {1,0}` ánh xạ đối số theo chiều nào?
7. `filterArguments` yêu cầu kiểu trả về filter khớp với phần nào của target?
8. `filterReturnValue` thay đổi danh sách tham số hay kiểu trả về?
9. Nếu `asType` tạo được handle `(Object,Object)Object`, vì sao truyền Integer vào nơi cần String vẫn lỗi?
10. `asCollector` khác `asSpreader` ở hướng biến đổi nào?
11. Vì sao `invokeExact` có thể lỗi khi chỉ thay biến nhận kết quả từ `int` sang `long`?
12. Một phép `permuteArguments` có thể ghép thành công nhưng làm sai kết quả nghiệp vụ không?
13. Làm thế nào biết lỗi do ghép adapter, do kiểu call site hay do code parser?
14. Vì sao nên kiểm tra `type()` và kết quả sau từng stage thay vì chỉ ở cuối?

## 12. Bài tập thực hành

**Bài 1 — Đọc ma trận:** Trước khi chạy code, tự dự đoán `MethodType` của tám stage từ `raw` tới `generic` và hai adapter mảng. So với log từ chương trình.

**Bài 2 — Phá thứ tự:** Thay `permuteArguments(..., 1, 0)` bằng một mapping sai kiểu, quan sát exception ở **lúc tạo** adapter. Sau đó thử một target có hai tham số đều `int`, đổi thứ tự bằng mapping vẫn hợp lệ và kiểm tra kết quả sai để thấy sự cần thiết của assertion nghiệp vụ.

**Bài 3 — Đổi filter:** Thử filter trả về `String` khi target đòi `int`. Dùng `filter.type()` để giải thích `IllegalArgumentException`. Khôi phục parser rồi truyền `"NaN"` để quan sát `NumberFormatException` ở thời điểm thực thi.

**Bài 4 — Chuyển kiểu trả về:** Dùng `asType` chuyển `(int)int` sang `(int)long`; gọi `invokeExact` và xác minh kiểu `long`. Thử đổi số lượng tham số để quan sát lỗi tạo adapter.

**Bài 5 — Mảng:** Thay `asCollector(int[].class,3)` bằng `asCollector(int[].class,2)` và dự đoán kiểu mới. Thử `asSpreader` với mảng sai độ dài; so sánh lỗi lúc tạo handle và lúc gọi.

**Bài 6 — Code ứng dụng:** Chọn một pipeline thật của dự án có `Lookup`, `bindTo`, `filterArguments` hoặc `asType`. Thêm helper `requireType` sau mỗi bước, ghi lại `MethodType` kỳ vọng và viết một test xác minh kết quả. Không tự thêm adapter nếu pipeline hiện tại không cần.

## Tài liệu tham khảo chính thức

- [Oracle JDK 18 — MethodHandle](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type`, `invokeExact`, `asType`, `bindTo`, `asCollector`, `asSpreader`.
- [Oracle JDK 18 — MethodHandles](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/invoke/MethodHandles.html): `insertArguments`, `dropArguments`, `permuteArguments`, `filterArguments`, `filterReturnValue`.
- [Oracle JDK 18 — MethodType](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/invoke/MethodType.html): cấu trúc và cách so sánh chữ ký bất biến.
- [Oracle JDK 26 — MethodHandle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): hợp đồng các adapter vẫn áp dụng trên JDK hiện đại.
- [Oracle JDK 26 — MethodHandles](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): ràng buộc kiểu và exception của các combinator.
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): bối cảnh Java 18 và giới hạn suy luận hiệu năng từ thay đổi implementation.
