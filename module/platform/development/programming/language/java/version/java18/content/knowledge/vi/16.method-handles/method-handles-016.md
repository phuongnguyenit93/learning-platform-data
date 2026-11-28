# `invokeWithArguments()`: giao diện đối số động, boxing và chi phí chuyển đổi

## 1. Mục tiêu và phạm vi

Bài này thuộc chương **MethodHandle** của module **JAVA_VERSION_JAVA18**. Trọng tâm là `java.lang.invoke.MethodHandle.invokeWithArguments()`: cách gọi một method handle khi **số lượng và giá trị đối số chỉ có ở thời điểm chạy**, chẳng hạn dữ liệu từ bộ điều phối lệnh, biểu mẫu hoặc hệ thống plugin.

Sau bài này, bạn có thể:

- Chọn đúng hai overload `invokeWithArguments(Object... arguments)` và `invokeWithArguments(List<?> arguments)`.
- Giải thích vì sao đối số primitive được boxing khi đi qua `Object`, rồi được chuyển đổi trước khi gọi đích; kết quả primitive cũng trở thành wrapper vì kiểu trả về của API là `Object`.
- Phân biệt `invokeWithArguments`, `invoke` và `invokeExact` về kiểu lời gọi, số lượng đối số, cơ chế chuyển đổi và phạm vi sử dụng.
- Nhận diện các lỗi sai arity, giá trị không chuyển được, `null`, tham số mảng và biến thể varargs collector.
- Đánh giá những nguồn chi phí khi gọi động và lựa chọn giao diện gọi phù hợp cho đường chạy thường xuyên.

**Bối cảnh Java 18:** `MethodHandle` và `invokeWithArguments` đã tồn tại từ trước Java 18. JEP 416 trong Java 18 triển khai lại core reflection của JDK dựa trên method handles và variable handles. Đây là mối liên hệ về **cài đặt reflection**; nó không làm đổi hợp đồng công khai của `invokeWithArguments`. Nội dung dưới đây chỉ dùng API được hỗ trợ trên JDK hiện đại.

## 2. Hợp đồng API: hai cách truyền đối số động

Các chữ ký quan trọng:

```java
public Object invokeWithArguments(Object... arguments) throws Throwable;
public Object invokeWithArguments(java.util.List<?> arguments) throws Throwable;
```

Cả hai đều gọi thao tác được biểu diễn bởi handle, lấy số lượng và thứ tự tham số từ một danh sách giá trị ở runtime. Giá trị trả về có kiểu **`Object`**; nếu thao tác đích có kiểu trả về `void`, kết quả của `invokeWithArguments` là `null`.

| Overload | Nguồn đối số | Khi nào thuận tiện |
| --- | --- | --- |
| `invokeWithArguments(Object...)` | Các đối số viết tại điểm gọi hoặc một `Object[]`. | Có ít đối số, hoặc hệ thống đã nhận một mảng đối số. |
| `invokeWithArguments(List<?>)` | Danh sách các đối số theo thứ tự. | Đối số động được tập hợp trong `List` từ xử lý dữ liệu, dispatch hoặc plugin. |

Với handle có kiểu `(int,int)int`, ba cách gọi sau đều gửi **hai đối số**:

```java
Object a = sum.invokeWithArguments(2, 3);
Object b = sum.invokeWithArguments(new Object[] {2, 3});
Object c = sum.invokeWithArguments(java.util.List.of(2, 3));
```

Ở ví dụ này `sum` là `MethodHandle` trỏ tới một phương thức cộng hai số nguyên. Trong mọi lời gọi, kết quả là một `Integer` được nhìn qua biến kiểu `Object`, bởi phương thức `invokeWithArguments` trả `Object`.

**Không đồng nhất `Object...` với `MethodType` của đích.** Giao diện bên ngoài nhận các giá trị `Object`, nhưng handle vẫn giữ chữ ký thật: `sum.type()` không đổi và vẫn là `(int,int)int`.

## 3. Mô hình chuyển đổi khi gọi

Xem xét:

```java
static int add(int x, int y) {
    return x + y;
}
```

Tìm handle:

```java
MethodHandle sum = MethodHandles.lookup().findStatic(
        Example.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));
```

`Example` là lớp khai báo `add` trong đoạn minh họa; ví dụ hoàn chỉnh ở phần sau dùng tên lớp cụ thể.

Khi gọi:

```java
Object result = sum.invokeWithArguments(3, 4);
```

có thể hiểu luồng dữ liệu ở mức hợp đồng như sau:

```text
Tại call site
    3, 4 (giá trị int trong mã Java)
       |
       v
Object...  -->  Integer(3), Integer(4) (boxing để chứa trong Object[])
       |
       v
Lời gọi động: hai đối số kiểu Object
       |
       v
Thích nghi theo kiểu handle (int,int)int
    --> kiểm tra/chuyển kiểu, unboxing Integer thành int
       |
       v
add(3, 4) --> int 7
       |
       v
Kết quả của invokeWithArguments có kiểu Object
    --> boxing int thành Integer(7)
```

Đây là mô hình khái niệm, **không phải sơ đồ bắt buộc về số lượng đối tượng thực sự được JVM cấp phát**. JIT có thể tối ưu hóa một số bước. Tuy nhiên, ở cấp API, caller luôn tương tác với đối số `Object` và kết quả `Object`.

Hợp đồng chuyển đổi tương ứng việc gọi một handle bằng chữ ký tổng quát nhận `Object` ở từng vị trí và trả về `Object`, với các chuyển đổi được `MethodHandle.asType` hỗ trợ. Điều này có những giới hạn quan trọng:

- Chuyển từ reference sang primitive có thể cần kiểm tra kiểu và unboxing; chuyển từ primitive sang `Object` có thể cần boxing.
- Phép chuyển đổi kiểu primitive có thể làm tròn hoặc thay đổi giá trị theo quy tắc thích nghi được hỗ trợ. Không giả định mọi chuyển đổi đều bảo toàn chính xác.
- **Không có bước tự phân tích chuỗi số.** Nếu đích cần `int`, truyền `"3"` không tự chuyển thành `3` như một trình phân tích JSON.
- Với reference, giá trị được cast/kiểm tra tương thích tại runtime; sai kiểu có thể phát sinh `ClassCastException`.
- Số lượng đối số phải phù hợp với handle tại thời điểm gọi, có xét khả năng thu gom đối số của **varargs collector** khi được sử dụng.

Đừng cố suy diễn khả năng chuyển đổi chỉ từ quy tắc gán biến trong Java source. Khi cần chắc chắn, đối chiếu hợp đồng `asType` của đúng JDK và kiểm thử trên giá trị thực tế.

## 4. Khác biệt với `invokeExact()` và `invoke()`

Giả sử `sum.type()` là `(int,int)int`:

```java
int direct = (int) sum.invokeExact(3, 4);
long widened = (long) sum.invoke(3, 4);
Object dynamic = sum.invokeWithArguments(3, 4);
```

Bảng so sánh:

| Đặc điểm | `invokeExact` | `invoke` | `invokeWithArguments` |
| --- | --- | --- | --- |
| Kiểu lời gọi | Call site phải khớp chính xác `handle.type()`, kể cả kiểu trả về. | Call site có kiểu do mã Java xác định; có thể thích nghi theo `asType`. | Số lượng đối số xác định ở runtime; các giá trị đi qua giao diện tổng quát `Object`. |
| Đối số động từ `List` | Không phải giao diện nhận danh sách. | Không phải giao diện nhận danh sách. | Có overload `List<?>`. |
| Kết quả primitive | Có thể lấy trực tiếp primitive. | Có thể lấy trực tiếp primitive qua kiểu call site. | API trả `Object`, nên kết quả primitive được boxing về wrapper. |
| Sai kiểu | `WrongMethodTypeException` khi chữ ký call site không khớp. | Tùy chuyển đổi, có thể lỗi kiểu hoặc `WrongMethodTypeException`. | Tùy arity và giá trị, có thể lỗi kiểu hoặc `WrongMethodTypeException`. |
| Mục đích tiêu biểu | Đường gọi có kiểu ổn định, rõ ràng. | Điểm gọi có kiểu rõ nhưng cần thích nghi. | Dispatcher với cấu trúc đối số chỉ biết khi chạy. |

Ví dụ quan trọng về **kiểu trả về ở call site**:

```java
int x = (int) sum.invokeExact(3, 4);   // OK, (int,int)int

// Sai nếu sum.type() là (int,int)int:
// long y = (long) sum.invokeExact(3, 4);
// Điểm gọi yêu cầu (int,int)long: WrongMethodTypeException.

Object z = sum.invokeWithArguments(3, 4); // OK, nhận Integer
```

`invokeWithArguments` giảm sự phụ thuộc vào kiểu tĩnh ở điểm gọi nhưng đổi lại cần kiểm tra/thích nghi nhiều hơn. Đây **không** phải API giúp một handle tự nhận mọi số lượng hay mọi kiểu giá trị.

## 5. Ví dụ Java hoàn chỉnh

Tạo file **`InvokeWithArgumentsDemo.java`**. Chương trình chỉ sử dụng thư viện chuẩn Java, chạy được trên JDK 18 hoặc JDK hiện đại.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.List;

public final class InvokeWithArgumentsDemo {

    public static int add(int a, int b) {
        return a + b;
    }

    public static String describe(String value) {
        return value == null ? "NULL" : "value=" + value;
    }

    public static int size(int[] values) {
        return values.length;
    }

    public static void log(String message) {
        System.out.println("[log] " + message);
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("JDK: " + Runtime.version());

        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle sum = lookup.findStatic(
                InvokeWithArgumentsDemo.class,
                "add",
                MethodType.methodType(int.class, int.class, int.class));

        System.out.println("sum type: " + sum.type());

        // Một lời gọi được kiểm tra kiểu chính xác tại call site.
        int exact = (int) sum.invokeExact(2, 3);
        System.out.println("invokeExact: " + exact);

        // Hai int được boxing để đi qua Object...
        Object fromVarargs = sum.invokeWithArguments(2, 3);
        System.out.println("from Object...: " + fromVarargs);
        System.out.println("result wrapper: "
                + fromVarargs.getClass().getSimpleName());

        Object[] dynamicArguments = {4, 6};
        Object fromArray = sum.invokeWithArguments(dynamicArguments);
        System.out.println("from Object[]: " + fromArray);

        List<?> inputRow = List.of(7, 8);
        Object fromList = sum.invokeWithArguments(inputRow);
        System.out.println("from List: " + fromList);

        // minh họa thích nghi thủ công sang chữ ký toàn Object
        MethodHandle generic = sum.asType(MethodType.genericMethodType(2));
        Object fromGeneric = (Object) generic.invokeExact(
                (Object) Integer.valueOf(10),
                (Object) Integer.valueOf(20));
        System.out.println("generic handle type: " + generic.type());
        System.out.println("generic result: " + fromGeneric);

        MethodHandle describe = lookup.findStatic(
                InvokeWithArgumentsDemo.class,
                "describe",
                MethodType.methodType(String.class, String.class));

        // Cast về Object để truyền một đối số null qua Object...
        Object nullReference = describe.invokeWithArguments((Object) null);
        System.out.println("null reference: " + nullReference);

        MethodHandle arraySize = lookup.findStatic(
                InvokeWithArgumentsDemo.class,
                "size",
                MethodType.methodType(int.class, int[].class));

        // Truyền một int[] vào một vị trí đối số.
        Object arrayResult =
                arraySize.invokeWithArguments((Object) new int[] {5, 6, 7});
        System.out.println("array size: " + arrayResult);

        MethodHandle logger = lookup.findStatic(
                InvokeWithArgumentsDemo.class,
                "log",
                MethodType.methodType(void.class, String.class));

        Object voidResult = logger.invokeWithArguments("hello");
        System.out.println("void result is null: " + (voidResult == null));

        try {
            sum.invokeWithArguments(1); // thiếu tham số thứ hai
            throw new AssertionError("Expected WrongMethodTypeException");
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong arity: WrongMethodTypeException");
        }

        try {
            sum.invokeWithArguments("3", 4); // String không tự đổi thành int
            throw new AssertionError("Expected ClassCastException");
        } catch (ClassCastException expected) {
            System.out.println("wrong value type: ClassCastException");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```shell
java -version
javac -version
javac -encoding UTF-8 InvokeWithArgumentsDemo.java
java InvokeWithArgumentsDemo
```

Ví dụ đầu ra dự kiến (không cố định phiên bản JDK):

```text
sum type: (int,int)int
invokeExact: 5
from Object...: 5
result wrapper: Integer
from Object[]: 10
from List: 15
generic handle type: (Object,Object)Object
generic result: 30
null reference: NULL
array size: 3
[log] hello
void result is null: true
wrong arity: WrongMethodTypeException
wrong value type: ClassCastException
```

Chương trình cũng in dòng `JDK: ...` ở đầu. Các thông báo ngoại lệ trên dựa trên kiểu dữ liệu và handle trong ví dụ. Khi dùng dữ liệu khác, lỗi thực tế còn phụ thuộc vào kiểu/chữ ký của handle và phép chuyển đổi cụ thể.

**Phần kiểm chứng chính:** `sum.type()` luôn là `(int,int)int` dù caller đã dùng nhiều cách truyền đối số. Việc `generic.type()` là `(Object,Object)Object` cho thấy một handle mới có thể được thích nghi một cách tường minh bằng `asType`, còn handle `sum` gốc không bị sửa đổi.

## 6. Bẫy thường gặp với mảng và overload `Object...`

Trong Java, `Object...` chính là tham số varargs được đóng gói thành `Object[]`. Điều này khiến **mảng đối số** và **mảng làm một đối số** dễ bị nhầm lẫn.

Giả sử `sum` nhận đúng hai tham số `int`:

```java
Object[] pair = {2, 3};
sum.invokeWithArguments(pair);       // Hai đối số: 2 và 3
```

Nhưng handle `arraySize` nhận **một** `int[]`:

```java
int[] values = {1, 2, 3};
arraySize.invokeWithArguments((Object) values); // Một đối số là int[]
```

Ép `values` thành `Object` làm ý định rõ ràng tại điểm gọi. Nếu có một `Object[]` cần truyền như **một** đối số duy nhất, cũng dùng cast:

```java
Object[] values = {"a", "b"};
someHandle.invokeWithArguments((Object) values); // Một đối số Object[]
```

Trái lại, `someHandle.invokeWithArguments(values)` coi từng phần tử của `Object[]` là đối số riêng ở giao diện varargs.

Một trường hợp tinh vi khác là `null`:

```java
describe.invokeWithArguments((Object) null); // Một đối số null
```

Dùng cast `(Object)` để làm rõ đây là **một giá trị null**. Nếu muốn biểu diễn chính xác không có đối số, sử dụng `invokeWithArguments()` hoặc một danh sách rỗng; hai trường hợp khác nhau với lời gọi có một đối số null.

**Varargs collector của chính handle:** Một số handle được đánh dấu là *variable arity* và có khả năng thu gom các đối số cuối vào tham số mảng. Hành vi đó xuất phát từ trạng thái/chữ ký của **handle**, khác với cách Java đóng gói các tham số `Object...` cho phương thức `invokeWithArguments`. Khi cần thực thi với số vị trí tham số cố định, xem `isVarargsCollector()`, `asFixedArity()` và phương thức tạo handle tương ứng. Đừng suy luận quy tắc thu gom chỉ từ việc phương thức đích ban đầu khai báo dấu `...`.

## 7. Kiểu runtime và ngoại lệ cần phân biệt

Không có “tự chuyển đổi bằng mọi giá”. Các thất bại thường đến từ nhiều giai đoạn khác nhau:

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `WrongMethodTypeException` | Số lượng vị trí không khớp hoặc không có phép thích nghi chữ ký phù hợp. | In `handle.type()`, kiểm tra số phần tử danh sách và dạng varargs collector. |
| `ClassCastException` | Giá trị tham chiếu runtime không thể dùng ở kiểu đối số mà handle yêu cầu, ví dụ chuỗi thay cho số nguyên. | Chuẩn hóa/kiểm tra dữ liệu đầu vào trước khi gọi. |
| `NullPointerException` | Một thao tác đích dereference null, hoặc chuyển đổi/giải nén giá trị null ở nơi không được chấp nhận. | Xác định nơi phát sinh lỗi trong stack trace và hợp đồng của tham số đích. |
| Ngoại lệ do phương thức đích ném | Ví dụ đích chủ động ném `IllegalArgumentException`. | Xử lý theo hợp đồng nghiệp vụ của phương thức đích; không quy mọi lỗi cho `MethodHandle`. |
| `NoSuchMethodException` / `IllegalAccessException` khi tìm handle | Tên/chữ ký không tồn tại hoặc `Lookup` không có quyền. | Kiểm tra `MethodType`, caller lookup và `exports`/`opens` của JPMS. |

Quan trọng: `invokeWithArguments` khai báo `throws Throwable`. Khác với `Method.invoke`, nó **không bắt buộc bọc** ngoại lệ của phương thức đích vào `InvocationTargetException`. Nếu dùng trong framework, hãy phân biệt rõ lỗi dữ liệu của caller và lỗi được ném từ thao tác đích.

Khi truy cập member thuộc named module khác, quyền vẫn được kiểm tra khi tìm/tạo handle bằng `MethodHandles.Lookup`. `invokeWithArguments` không cấp thêm quyền truy cập và không làm bypass JPMS.

## 8. Chi phí chuyển đổi và lựa chọn trong ứng dụng thực tế

`invokeWithArguments` rất tiện khi hệ thống có một tập giá trị động. Nhưng đối với một đường chạy lặp lại hàng triệu lần, cân nhắc các chi phí có thể xuất hiện:

1. **Tạo hoặc truyền mảng/danh sách đối số:** cú pháp `Object...` có thể yêu cầu một mảng `Object[]`; nếu dữ liệu đã nằm trong `List`, có thể gọi trực tiếp overload `List<?>`.
2. **Boxing/unboxing:** primitive đi qua đối số `Object`, còn primitive result trở về `Object`. Việc này tạo công việc chuyển đổi và có thể phát sinh object allocation; JVM có thể tối ưu ở một số tình huống.
3. **Kiểm tra và thích nghi kiểu:** chữ ký tổng quát cần thích nghi tới `MethodType` của handle. Chi phí tùy cấu trúc handle, kiểu dữ liệu và mức tối ưu của JVM.
4. **Sự ổn định của điểm gọi:** kiểu không ổn định và việc tạo handle liên tục có thể làm JVM khó tối ưu. Nên tạo và lưu handle một lần nếu danh tính thao tác ổn định.
5. **Chi phí thực của phương thức đích:** I/O, truy cập mạng hay thao tác database thường áp đảo chi phí dispatch; cần đo **toàn bộ luồng ứng dụng** trước khi tối ưu vi mô.

| Trường hợp sử dụng | Lựa chọn hợp lý |
| --- | --- |
| Plugin dispatcher nhận `List<?>` có số phần tử do runtime quyết định | `invokeWithArguments(List<?>)` giúp mã rõ ràng. |
| Luồng xử lý có kiểu ổn định và gọi nhiều lần | Cân nhắc handle được lưu và `invokeExact` với chữ ký nhất quán. |
| Kiểu call site ổn định nhưng cần chuyển đổi có kiểm soát | `asType` một lần, sau đó dùng `invokeExact` trên handle đã thích nghi. |
| Tham số có thể không đúng kiểu | Kiểm tra/chuẩn hóa dữ liệu trước lời gọi, kèm thông báo lỗi theo từng tham số. |
| Cần so sánh hiệu năng | Benchmark bằng JMH với warmup, dữ liệu thực tế và cùng JDK/cấu hình; tránh kết luận từ một lượt `System.nanoTime()`. |

**Không có tỷ lệ chậm cố định** giữa `invokeWithArguments` và `invokeExact`: triển khai JDK, tối ưu JIT, cách lấy handle, dữ liệu và môi trường thực thi đều ảnh hưởng. Chọn theo tính rõ ràng và hợp đồng kiểu trước, rồi đo khi có yêu cầu hiệu năng cụ thể.

## 9. Mẫu áp dụng: biên giới giữa dữ liệu động và API có kiểu

Khi đọc từ một nguồn dữ liệu ngoài, chuỗi `"17"` vẫn là `String`. `invokeWithArguments` **không** có nghĩa vụ parse nó thành số. Ở lớp tiếp nhận dữ liệu, có thể kiểm tra rồi chuyển thành giá trị mà đích thực sự nhận:

```java
static Object callAdd(MethodHandle sum, List<String> input)
        throws Throwable {
    if (input.size() != 2) {
        throw new IllegalArgumentException("Cần đúng 2 đối số");
    }

    int a = Integer.parseInt(input.get(0));
    int b = Integer.parseInt(input.get(1));

    return sum.invokeWithArguments(a, b);
}
```

Ví dụ này là một đoạn trích độc lập để áp dụng trong chương trình có handle `sum` kiểu `(int,int)int`. Phần kiểm tra kiểu, tính hợp lệ và lỗi parse dữ liệu là trách nhiệm của lớp nghiệp vụ, còn `MethodHandle` chịu trách nhiệm gọi thao tác có kiểu.

Điểm thiết kế quan trọng: giữ cho **ranh giới dữ liệu động** có trách nhiệm chuẩn hóa dữ liệu; sau đó thực hiện lời gọi trên chữ ký đã biết. Nếu luồng chạy nhiều lần và luôn cùng chữ ký, có thể cân nhắc đưa dữ liệu vào một API typed hơn để giảm chuyển đổi khi gọi.

## 10. Bài tập kiểm chứng

1. Chạy chương trình `InvokeWithArgumentsDemo.java` trên **đúng JDK ứng dụng đang dùng**; ghi lại `java -version`, `sum.type()` và kiểu runtime của `fromVarargs`.
2. Thay `List.of(7, 8)` bằng `List.of("7", "8")`. Quan sát ngoại lệ, sau đó parse chuỗi thành số trước khi gọi và giải thích lý do.
3. Chạy `sum.invokeWithArguments(1)` và `sum.invokeWithArguments(1, 2, 3)` trong hai JVM/lần kiểm thử; xác minh có bao nhiêu đối số và kiểu lỗi phù hợp.
4. Tạo handle nhận `Object[]` làm **một** tham số, rồi thử `invokeWithArguments(values)` và `invokeWithArguments((Object) values)`; so sánh arity tại runtime.
5. Tạo handle cho một phương thức trả về `void`, kiểm tra giá trị trả từ `invokeWithArguments`.
6. So sánh code path dùng `invokeExact`, `asType + invokeExact` và `invokeWithArguments` với đầu vào giống nhau. Nêu các bước boxing, adaptation và lý do cần benchmark trước khi tuyên bố ưu thế hiệu năng.

### Câu hỏi tự kiểm tra

**1. Vì sao `invokeWithArguments` trả `Object` trong khi phương thức đích trả `int`?**

Vì giao diện phương thức được thiết kế để dùng trong lời gọi động, không biết trước kiểu trả về của mọi handle. Kết quả primitive được boxing để trả qua `Object`.

**2. `invokeWithArguments(List.of(3, 4))` có thay đổi `MethodType` gốc của handle không?**

Không. Handle giữ nguyên `type()`. Việc chuyển đổi xảy ra khi lời gọi thích nghi từ danh sách giá trị tới chữ ký của handle.

**3. Đã truyền `Object[]` có hai phần tử thì handle luôn nhận đúng hai tham số chứ?**

Với overload `Object...`, một `Object[]` thường cung cấp các đối số theo phần tử. Tuy nhiên nếu handle là varargs collector, quy tắc thu gom phần tử vào tham số mảng còn phụ thuộc trạng thái handle. Muốn truyền cả mảng như một đối số, dùng `(Object) array` hoặc tạo một danh sách có đúng một phần tử là mảng.

**4. Tại sao `sum.invokeWithArguments("3", 4)` không tự tính được `7`?**

Vì API làm chuyển đổi kiểu có kiểm soát, không thực hiện parse các chuỗi số. Caller phải chuyển `"3"` thành giá trị số trước khi gọi.

**5. Khi nào nên tránh `invokeWithArguments` trên đường chạy nóng?**

Khi số lượng và kiểu đối số đã cố định và phép đo cho thấy việc tạo mảng, boxing hoặc thích nghi lời gọi trở thành chi phí đáng kể. Khi đó, dùng handle ổn định với chữ ký rõ ràng có thể phù hợp hơn.

## 11. Tài liệu tham khảo

- Java SE API — `MethodHandle.invokeWithArguments`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html#invokeWithArguments(java.lang.Object...)
- Java SE API — `MethodHandle.asType`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html#asType(java.lang.invoke.MethodType)
- Java SE API — `MethodType`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE API — `MethodHandles`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html
- OpenJDK JEP 416 — *Reimplement Core Reflection with Method Handles* (Java 18): https://openjdk.org/jeps/416

Các liên kết Java SE 25 là tài liệu cho một JDK hiện đại. Khi xây dựng hợp đồng chuyển đổi kiểu, xử lý ngoại lệ hoặc đo hiệu năng, hãy đối chiếu với **Javadoc và runtime của chính phiên bản JDK đang sử dụng**.
