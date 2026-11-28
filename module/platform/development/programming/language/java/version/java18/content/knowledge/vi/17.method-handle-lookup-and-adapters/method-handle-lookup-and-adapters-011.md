# dropArguments() và permuteArguments(): bổ sung hoặc sắp xếp lại chữ ký mà vẫn kiểm soát MethodType

## 1. Mục tiêu bài học

Khi dùng `java.lang.invoke.MethodHandle`, mỗi handle có một **`MethodType` xác định**: kiểu trả về và danh sách kiểu tham số theo đúng thứ tự. Điều này giúp xây dựng bộ định tuyến lời gọi, callback, adapter cho framework hoặc pipeline xử lý dữ liệu mà không cần tạo một method trung gian cho mọi biến thể chữ ký.

Hai combinator trong `java.lang.invoke.MethodHandles` giải quyết hai tình huống thường gặp:

- `dropArguments(target, pos, types...)`: tạo handle mới **nhận thêm các tham số không sử dụng**, sau đó gọi `target` với những tham số gốc.
- `permuteArguments(target, newType, reorder...)`: tạo handle mới **sắp xếp lại, nhân bản hoặc bỏ qua** đối số đầu vào trước khi gọi `target`, theo bản đồ chỉ số `reorder`.

Bài thuộc chương **Lookup và adapter** của module `JAVA_VERSION_JAVA18`. Module khám phá các thay đổi từ Java 18 còn hữu ích trên JDK hiện đại, gồm UTF-8 mặc định, Simple Web Server, Javadoc snippets, reflection và MethodHandle. JEP 416 trong Java 18 đổi cách triển khai Core Reflection dựa trên method handles, nhưng hai combinator trong bài là **public API vẫn được hỗ trợ**, không phải cách truy cập chi tiết triển khai đã lỗi thời.

Sau bài học, bạn có thể:

1. Phân biệt tham số **đầu vào adapter** với tham số **đầu vào target**.
2. Tính kiểu handle mới sau `dropArguments` ở đầu, giữa hoặc cuối danh sách.
3. Đọc `reorder` theo chiều từ mỗi tham số **target** về một tham số **adapter**.
4. Thiết kế `permuteArguments` để đổi thứ tự, dùng một đối số hai lần hoặc bỏ đối số thừa.
5. Phân biệt ràng buộc **khớp kiểu chính xác** lúc tạo adapter với `invokeExact`/`invoke` lúc gọi.
6. Kết hợp cả hai combinator và kiểm tra `MethodType` cuối cùng.
7. Chẩn đoán `IllegalArgumentException`, `WrongMethodTypeException` và các lỗi adapter.
8. Tự kiểm chứng chương trình Java độc lập trên JDK hiện hành.

## 2. Nền tảng: target, adapter và MethodType

Một `MethodHandle` có kiểu cố định, ví dụ:

~~~text
(int, int)int
~~~

Nghĩa là handle nhận hai `int` và trả một `int`. Có thể đọc kiểu của nó:

~~~java
MethodType signature = handle.type();
int numberOfParams = signature.parameterCount();
Class<?> returnClass = signature.returnType();
Class<?> firstParameter = signature.parameterType(0);
~~~

Trong `MethodType.methodType`, truyền **return type trước**, các parameter types sau:

~~~java
MethodType type = MethodType.methodType(
        int.class, int.class, int.class);
System.out.println(type); // (int,int)int
~~~

Khi tạo adapter, dòng dữ liệu có dạng:

~~~text
Caller
   │   Các đối số theo MethodType của adapter
   ▼
Adapter ─── biến đổi danh sách đối số ───► Target
                                             │
                                             ▼
                                       Kết quả trả về
~~~

Combinator **không sửa `target`**. Nó trả về một handle mới. Có thể dùng cùng target để tạo nhiều adapter cho những ngữ cảnh khác nhau.

### 2.1. Hai phía của phép biến đổi

Ta đặt tên:

- **Incoming (I):** các tham số caller truyền cho **handle mới**.
- **Outgoing (O):** các tham số adapter cung cấp cho **target gốc**.

Ví dụ target:

~~~text
target.type() = (String, int)String
~~~

Một adapter có thể nhận thêm `boolean`:

~~~text
adapter.type() = (boolean, String, int)String

incoming: [boolean, String, int]
                     │     │
outgoing:          [String, int]
~~~

Giá trị `boolean` được nhận ở call site nhưng không được chuyển tới target.

**Nguyên tắc:** đọc `target.type()`, tính `adapter.type()` rồi kiểm tra trước khi gọi `invokeExact`.

## 3. Chữ ký API của hai combinator

~~~java
public static MethodHandle dropArguments(
        MethodHandle target,
        int pos,
        Class<?>... valueTypes);

public static MethodHandle dropArguments(
        MethodHandle target,
        int pos,
        List<Class<?>> valueTypes);

public static MethodHandle permuteArguments(
        MethodHandle target,
        MethodType newType,
        int... reorder);
~~~

| Tham số | Ý nghĩa |
| --- | --- |
| `target` | Handle sẽ được gọi sau khi adapter xử lý các tham số đầu vào |
| `pos` của `dropArguments` | Vị trí **chèn các tham số mới vào chữ ký**, chỉ số từ `0` |
| `valueTypes` | Kiểu những đối số adapter nhận nhưng không truyền tới target |
| `newType` của `permuteArguments` | `MethodType` mong muốn của handle mới, gồm return type |
| `reorder` | Với từng tham số của target, chỉ rõ **chỉ số đối số incoming** được lấy |

`dropArguments` có overload nhận varargs `Class<?>...` hoặc `List<Class<?>>`. `permuteArguments` bắt buộc khai báo `newType`; nó không tự suy ra toàn bộ kiểu từ mảng `reorder`.

Đây là adapter của `MethodHandle`, không phải cách sửa khai báo Java source. Đừng nhầm `dropArguments` với `insertArguments` (gắn sẵn giá trị rồi giảm số tham số) hoặc `dropReturn` (bỏ giá trị trả về).

## 4. dropArguments(): thêm tham số nhưng bỏ qua giá trị của chúng

Giả sử target là phép cộng:

~~~text
target.type() = (int, int)int
~~~

Một framework muốn callback nhận thêm metadata `String requestId` đứng trước hai số, trong khi target chỉ cần hai số đó:

~~~java
MethodHandle withRequestId =
        MethodHandles.dropArguments(add, 0, String.class);
~~~

Chữ ký mới:

~~~text
add.type()           = (int, int)int
withRequestId.type() = (String, int, int)int
                        ──────
                        bỏ qua
~~~

Gọi:

~~~java
int result = (int) withRequestId.invokeExact("REQ-123", 2, 3);
System.out.println(result); // 5
~~~

Target `add` vẫn nhận `2` và `3`, không thấy `"REQ-123"`.

### 4.1. Quy tắc pos

Nếu target có `N` formal parameters, `pos` hợp lệ từ **0 đến N, bao gồm cả hai đầu**. Toàn bộ `valueTypes` được chèn liên tục tại vị trí `pos`.

Với một target nối hai chuỗi có kiểu `(String,String)String` (ví dụ handle lấy bằng `findVirtual(String.class, "concat", MethodType.methodType(String.class, String.class))`, trong đó tham số đầu là receiver):

| Adapter | Chữ ký mới | Cách truyền ba giá trị `"x", "y", "z"` |
| --- | --- | --- |
| `dropArguments(cat, 0, String.class)` | `(String,String,String)String` | Bỏ `"x"`, target nhận `"y","z"` |
| `dropArguments(cat, 1, String.class)` | `(String,String,String)String` | Bỏ `"y"`, target nhận `"x","z"` |
| `dropArguments(cat, 2, String.class)` | `(String,String,String)String` | Bỏ `"z"`, target nhận `"x","y"` |

Vì cả ba tham số đều là `String`, `MethodType` của ba adapter này **trông giống nhau**. Chính `pos` quyết định giá trị nào bị bỏ, vì vậy khi kiểm chứng cần xem cả **hành vi**, không chỉ kiểu.

### 4.2. Chèn nhiều tham số một lần

~~~java
MethodHandle withContext = MethodHandles.dropArguments(
        add, 1, long.class, String.class);
~~~

Với `add.type() == (int,int)int`:

~~~text
withContext.type() = (int, long, String, int)int

incoming: [ 7, 123L, "trace", 5 ]
target:   [ 7,                 5 ]  -> 12
~~~

Cách gọi:

~~~java
int total = (int) withContext.invokeExact(
        7, 123L, "trace", 5);
~~~

Hai đối số `123L` và `"trace"` không được chuyển tiếp tới target.

### 4.3. Chèn ở cuối

Vì `N == 2` với target `add`, `pos == 2` hợp lệ:

~~~java
MethodHandle trailing = MethodHandles.dropArguments(
        add, 2, boolean.class);
~~~

Chữ ký mới là `(int,int,boolean)int`. Đối số boolean cuối bị bỏ.

### 4.4. Ràng buộc và lỗi lúc tạo dropArguments

- `pos` âm hoặc lớn hơn `target.type().parameterCount()`: `IllegalArgumentException`.
- Một `valueTypes` là `void.class`: `IllegalArgumentException`, vì `void` không thể làm kiểu tham số.
- `target`, danh sách/mảng `valueTypes` hoặc phần tử của chúng là `null`: `NullPointerException`.
- Kiểu mới vượt giới hạn số slot tham số MethodHandle/JVM: `IllegalArgumentException`.
- **Return type giữ nguyên**; chỉ danh sách parameter types được mở rộng.

Cần phân biệt “bỏ qua đối số” với “không đánh giá biểu thức ở caller”. Trong lời gọi Java, biểu thức `expensive()` vẫn được đánh giá để tạo giá trị truyền vào adapter, dù giá trị đó sau cùng bị bỏ trước khi gọi target. Combinator không loại bỏ side effects của biểu thức đầu vào.

## 5. permuteArguments(): sắp xếp theo bản đồ chỉ số

`permuteArguments` nhận một `newType` và mảng `reorder`. Quy tắc:

> Với tham số thứ `k` của target, adapter lấy đối số incoming ở chỉ số `reorder[k]`.

**`reorder` dài bằng số tham số target**, không nhất thiết bằng số tham số adapter.

Gọi:

- `I = newType.parameterCount()`: số incoming parameters.
- `O = target.type().parameterCount()`: số outgoing parameters.

Điều kiện:

1. `reorder.length == O`.
2. Mỗi `reorder[k]` là chỉ số hợp lệ: `0 <= reorder[k] < I`.
3. `newType.parameterType(reorder[k])` phải **giống hệt** `target.type().parameterType(k)`.
4. `newType.returnType()` phải **giống hệt** `target.type().returnType()`.
5. Adapter không thực hiện chuyển đổi kiểu đối số hoặc return value.

### 5.1. Đảo thứ tự ba tham số

Target:

~~~java
static String describe(String user, int count, boolean urgent) {
    return user + ":" + count + ":" + urgent;
}
~~~

Chữ ký gốc:

~~~text
target.type() = (String,int,boolean)String
~~~

Caller muốn truyền theo thứ tự `(boolean,String,int)String`:

~~~java
MethodType newType = MethodType.methodType(
        String.class, boolean.class, String.class, int.class);

MethodHandle reordered = MethodHandles.permuteArguments(
        target, newType, 1, 2, 0);
~~~

Sơ đồ:

~~~text
incoming theo newType:
index:        0        1        2
type:      boolean   String    int
value:      true     "Mai"      4

target slot 0 (String)  <- incoming[1] = "Mai"
target slot 1 (int)     <- incoming[2] = 4
target slot 2 (boolean) <- incoming[0] = true

reorder = [1, 2, 0]
~~~

Đọc từng phần tử:

- `reorder[0]=1`: tham số target `String user` lấy incoming index `1`.
- `reorder[1]=2`: tham số target `int count` lấy incoming index `2`.
- `reorder[2]=0`: tham số target `boolean urgent` lấy incoming index `0`.

~~~java
String result = (String) reordered.invokeExact(
        true, "Mai", 4);
// result: "Mai:4:true"
~~~

`reordered.type()` bằng `newType`. `target.type()` giữ nguyên.

**Mẹo tránh đảo ngược:** hãy lập bảng “target slot ← incoming index” trước khi viết `reorder`. Đừng viết mảng theo chiều “incoming sẽ đi đâu”; đó là chiều ngược với hợp đồng API.

## 6. permuteArguments() không chỉ hoán vị đơn thuần

Tên `permuteArguments` dễ khiến người học nghĩ rằng `reorder` bắt buộc chứa mỗi chỉ số đúng một lần, chẳng hạn `[2,0,1]`. Thực tế, **đây không nhất thiết là một permutation toán học**: chỉ số có thể lặp và có thể thiếu.

### 6.1. Lặp chỉ số: dùng một incoming argument nhiều lần

Target:

~~~java
static int add(int left, int right) {
    return left + right;
}
~~~

`add.type() = (int,int)int`. Ta muốn một handle nhận **một `int`**, nhưng gửi giá trị này cho cả hai tham số target:

~~~java
MethodHandle twice = MethodHandles.permuteArguments(
        add,
        MethodType.methodType(int.class, int.class),
        0, 0);

int result = (int) twice.invokeExact(21);
System.out.println(result); // 42
~~~

Phân tích:

~~~text
incoming: index 0 -> 21

target argument 0 <- incoming[0] = 21
target argument 1 <- incoming[0] = 21

reorder = [0, 0]
target: add(21, 21)
~~~

Chữ ký adapter là `(int)int`, **ít tham số hơn** target `(int,int)int`. Không có phép tạo giá trị mặc định: cùng một giá trị incoming được dùng ở hai vị trí outgoing.

Nếu incoming argument là kết quả một biểu thức có side effect, biểu thức được đánh giá **một lần** tại call site, rồi giá trị đó được sao chép tới hai slot của target; combinator không tự gọi lại biểu thức.

### 6.2. Bỏ chỉ số: incoming argument không được dùng

Vẫn với target `add(int,int)`, caller có ba tham số `(String,int,int)`, trong đó `String` là mã trace và không được dùng bởi target:

~~~java
MethodHandle withUnusedTrace = MethodHandles.permuteArguments(
        add,
        MethodType.methodType(
                int.class, String.class, int.class, int.class),
        1, 2);

int result = (int) withUnusedTrace.invokeExact(
        "trace-1", 7, 5);
System.out.println(result); // 12
~~~

`reorder = [1,2]` không nhắc incoming index `0`, vì vậy incoming `String` bị bỏ qua.

~~~text
incoming[0]: "trace-1"  (không dùng)
incoming[1]: 7          -> target argument 0
incoming[2]: 5          -> target argument 1
~~~

Chữ ký mới là `(String,int,int)int`, **nhiều tham số hơn** target.

### 6.3. Số tham số incoming và outgoing có thể khác

| Target arity | NewType arity | Ví dụ reorder | Kết quả |
| ---: | ---: | --- | --- |
| 3 | 3 | `[1,2,0]` | Hoán đổi thứ tự |
| 2 | 1 | `[0,0]` | Dùng một incoming hai lần |
| 2 | 3 | `[1,2]` | Bỏ incoming index `0` |
| 2 | 2 | `[1,0]` | Đảo hai tham số |
| 0 | 1 | `[]` | Bỏ incoming argument khi target không cần tham số |

Tuy vậy, mọi `reorder` vẫn phải thỏa quy tắc **độ dài bằng target arity, chỉ số hợp lệ và kiểu chính xác**.

### 6.4. Không thực hiện conversion

Target nhận `String` thì incoming slot được chỉ định cũng phải có kiểu `String.class` trong `newType`. Ngay cả khi `Object` có thể chứa một `String` lúc chạy, adapter **không** cho phép truyền `Object.class` thay `String.class` ở bước `permuteArguments`.

Muốn chuyển đổi kiểu theo một hợp đồng rõ ràng, phải dùng API adapter khác, ví dụ `asType` hoặc `filterArguments` nếu phù hợp; `permuteArguments` không tự thêm cast/boxing/unboxing.

Một trường hợp cần lưu ý: `permuteArguments` trả về một handle **không có chế độ variable arity**, kể cả khi target ban đầu là một varargs collector. Việc sắp xếp tham số không đồng thời bảo tồn mọi đặc điểm của chế độ thu gom varargs.

## 7. Khi nào dùng dropArguments thay vì permuteArguments?

Cả hai đều có thể tạo handle nhận tham số không dùng. So sánh:

~~~java
// add.type() = (int,int)int

MethodHandle byDrop = MethodHandles.dropArguments(
        add, 0, String.class);

MethodHandle byPermute = MethodHandles.permuteArguments(
        add,
        MethodType.methodType(
                int.class, String.class, int.class, int.class),
        1, 2);
~~~

Hai handle có cùng `MethodType`:

~~~text
(String,int,int)int
~~~

Với `"trace",7,5`, cả hai đều tính `7+5`. Nhưng ý định được diễn đạt khác nhau:

- `dropArguments` nói rõ: “giữ nguyên thứ tự các tham số target, **chèn** một tham số không dùng tại vị trí `0`”.
- `permuteArguments` nói rõ: “target nhận incoming index `1` rồi index `2`”.

| Mục tiêu | Ưu tiên |
| --- | --- |
| Thêm một số tham số metadata/callback mà target không cần | `dropArguments` vì đơn giản, trực tiếp |
| Đổi thứ tự tham số | `permuteArguments` |
| Nhân bản một incoming argument sang nhiều target parameters | `permuteArguments` |
| Sắp xếp lại đồng thời bỏ vài incoming arguments | `permuteArguments` hoặc kết hợp hai combinator |
| Muốn ràng buộc một tham số vào giá trị cố định | `insertArguments`, không phải hai combinator này |
| Muốn biến đổi kiểu hoặc giá trị tham số | `asType` / `filterArguments` khi phù hợp |

`dropArguments` không giảm số tham số **đầu vào adapter**: trái lại, nó tăng số tham số nhận vào. Tên gọi “drop” nói về việc **loại đối số trước khi chuyển cho target**.

## 8. Kết hợp hai combinator trong một chuỗi adapter

Một callback nhận chữ ký theo thứ tự:

~~~text
(boolean urgent, Context context, String user, int count) -> String
~~~

Nhưng target gốc chỉ chấp nhận:

~~~text
(String user, int count, boolean urgent) -> String
~~~

Với `Context` chỉ dùng để tương thích với giao diện callback, không chuyển cho target, có thể làm hai bước.

### Bước 1: thêm Context vào đầu chữ ký target

~~~java
MethodHandle withContext = MethodHandles.dropArguments(
        describe, 0, Context.class);
~~~

Kiểu:

~~~text
describe.type()    = (String,int,boolean)String
withContext.type() = (Context,String,int,boolean)String
~~~

### Bước 2: chuyển thứ tự sang chữ ký callback

~~~java
MethodType callbackType = MethodType.methodType(
        String.class,
        boolean.class, Context.class, String.class, int.class);

MethodHandle callback = MethodHandles.permuteArguments(
        withContext, callbackType, 1, 2, 3, 0);
~~~

Bản đồ:

~~~text
Incoming callback: (boolean, Context, String, int)
index:                 0         1        2    3

Target của permute = withContext:
slot 0 Context <- incoming[1]
slot 1 String  <- incoming[2]
slot 2 int     <- incoming[3]
slot 3 boolean <- incoming[0]

reorder = [1, 2, 3, 0]

withContext bỏ slot Context:
describe(String, int, boolean)
~~~

Gọi:

~~~java
String result = (String) callback.invokeExact(
        true, new Context("trace-42"), "Mai", 4);
// "Mai:4:true"
~~~

Dù `Context` được đưa vào `withContext`, nó bị bỏ trước khi gọi `describe`.

### 8.1. Kiểm tra type ở từng bước

~~~java
System.out.println(describe.type());
System.out.println(withContext.type());
System.out.println(callback.type());
~~~

Kết quả:

~~~text
(String,int,boolean)String
(Context,String,int,boolean)String
(boolean,Context,String,int)String
~~~

`callback.type()` chính xác bằng `callbackType` đã yêu cầu. Nếu dự định dùng `Context` làm thông tin thật sự để tính kết quả, **không thể chỉ drop nó**: cần target hoặc filter/combiner khác biết xử lý `Context`.

### 8.2. Thứ tự ghép combinator quan trọng

Về nguyên tắc có thể `permuteArguments` trước rồi `dropArguments` sau, nhưng vị trí chèn và mảng `reorder` sẽ thay đổi. Khi ghép nhiều adapter:

1. Ghi `MethodType` trước/sau từng bước.
2. Đánh số incoming và target slots riêng.
3. Suy từng chỉ số `reorder` bằng bảng.
4. Dùng `handle.type().equals(expectedType)` để kiểm chứng.
5. Chạy thử với các giá trị **dễ phân biệt**; đừng chỉ dùng toàn số `0` hoặc các chuỗi giống nhau vì có thể che lỗi đảo thứ tự.

## 9. Ví dụ Java hoàn chỉnh: các trường hợp đúng và sai

Tạo một file duy nhất `ArgumentAdaptersDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class ArgumentAdaptersDemo {

    private static final class Context {
        private final String traceId;

        Context(String traceId) {
            this.traceId = traceId;
        }
    }

    private static String describe(
            String user, int count, boolean urgent) {
        return user + ":" + count + ":" + urgent;
    }

    private static int add(int left, int right) {
        return left + right;
    }

    private static String pair(String left, String right) {
        return left + "|" + right;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle describe = lookup.findStatic(
                ArgumentAdaptersDemo.class,
                "describe",
                MethodType.methodType(
                        String.class,
                        String.class, int.class, boolean.class));

        MethodHandle add = lookup.findStatic(
                ArgumentAdaptersDemo.class,
                "add",
                MethodType.methodType(
                        int.class, int.class, int.class));

        MethodHandle pair = lookup.findStatic(
                ArgumentAdaptersDemo.class,
                "pair",
                MethodType.methodType(
                        String.class, String.class, String.class));

        // 1. Cùng MethodType mới nhưng bỏ các vị trí khác nhau.
        MethodHandle dropHead =
                MethodHandles.dropArguments(
                        pair, 0, String.class);
        MethodHandle dropMiddle =
                MethodHandles.dropArguments(
                        pair, 1, String.class);
        MethodHandle dropTail =
                MethodHandles.dropArguments(
                        pair, 2, String.class);

        String head = (String) dropHead.invokeExact(
                "x", "y", "z");
        String middle = (String) dropMiddle.invokeExact(
                "x", "y", "z");
        String tail = (String) dropTail.invokeExact(
                "x", "y", "z");

        System.out.println(
                "drop: " + head + ", " + middle + ", " + tail);

        // 2. Bỏ hai tham số được chèn ở giữa.
        MethodHandle extra = MethodHandles.dropArguments(
                add, 1, long.class, String.class);
        int extraResult = (int) extra.invokeExact(
                7, 123L, "trace", 5);
        System.out.println("middle extras: " + extraResult);

        // 3. Thay đổi thứ tự (boolean,String,int) -> target.
        MethodType reorderedType = MethodType.methodType(
                String.class,
                boolean.class, String.class, int.class);

        MethodHandle reordered = MethodHandles.permuteArguments(
                describe, reorderedType, 1, 2, 0);

        String reorderedResult = (String) reordered.invokeExact(
                true, "Mai", 4);

        System.out.println("reordered: " + reorderedResult);
        System.out.println("type matches: "
                + reordered.type().equals(reorderedType));

        // 4. Một incoming int phục vụ hai tham số target.
        MethodHandle twice = MethodHandles.permuteArguments(
                add,
                MethodType.methodType(int.class, int.class),
                0, 0);

        int doubled = (int) twice.invokeExact(21);
        System.out.println("duplicate: " + doubled);

        // 5. Bỏ incoming index 0 theo hai cách.
        MethodType traceType = MethodType.methodType(
                int.class,
                String.class, int.class, int.class);

        MethodHandle skipped = MethodHandles.permuteArguments(
                add, traceType, 1, 2);

        MethodHandle dropped = MethodHandles.dropArguments(
                add, 0, String.class);

        int viaPermute = (int) skipped.invokeExact(
                "trace", 7, 5);
        int viaDrop = (int) dropped.invokeExact(
                "trace", 7, 5);

        System.out.println("ignore: "
                + viaPermute + ", " + viaDrop);

        // 6. Ghép dropArguments và permuteArguments.
        MethodHandle withContext = MethodHandles.dropArguments(
                describe, 0, Context.class);

        MethodType callbackType = MethodType.methodType(
                String.class,
                boolean.class,
                Context.class,
                String.class,
                int.class);

        MethodHandle callback = MethodHandles.permuteArguments(
                withContext, callbackType, 1, 2, 3, 0);

        Context context = new Context("trace-42");
        String callbackResult = (String) callback.invokeExact(
                true, context, "Mai", 4);

        System.out.println("callback: " + callbackResult);
        System.out.println("callback type matches: "
                + callback.type().equals(callbackType));

        // 7. Adapter construction rejects invalid pos.
        try {
            MethodHandles.dropArguments(add, 3, String.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("drop invalid position");
        }

        // 8. void không thể là kiểu của một tham số.
        try {
            MethodHandles.dropArguments(add, 0, void.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("drop void parameter");
        }

        // 9. Mảng reorder phải có đúng target arity.
        try {
            MethodHandles.permuteArguments(
                    add,
                    MethodType.methodType(
                            int.class, int.class, int.class),
                    1);
        } catch (IllegalArgumentException expected) {
            System.out.println("permute wrong reorder length");
        }

        // 10. Parameter types phải giống hệt nhau.
        try {
            MethodHandles.permuteArguments(
                    add,
                    MethodType.methodType(
                            int.class, String.class, int.class),
                    0, 1);
        } catch (IllegalArgumentException expected) {
            System.out.println("permute type mismatch");
        }

        // 11. Kiểu trả về của newType phải đúng bằng target.
        try {
            MethodHandles.permuteArguments(
                    add,
                    MethodType.methodType(
                            Object.class, int.class, int.class),
                    0, 1);
        } catch (IllegalArgumentException expected) {
            System.out.println("permute return mismatch");
        }

        // 12. invokeExact không tự đảo thứ tự cho call site.
        try {
            String impossible = (String) reordered.invokeExact(
                    "Mai", 4, true);
            System.out.println(impossible);
        } catch (WrongMethodTypeException expected) {
            System.out.println("invokeExact wrong signature");
        }
    }
}
~~~

Chạy:

~~~bash
javac ArgumentAdaptersDemo.java
java ArgumentAdaptersDemo
~~~

Kết quả dự kiến:

~~~text
drop: y|z, x|z, x|y
middle extras: 12
reordered: Mai:4:true
type matches: true
duplicate: 42
ignore: 12, 12
callback: Mai:4:true
callback type matches: true
drop invalid position
drop void parameter
permute wrong reorder length
permute type mismatch
permute return mismatch
invokeExact wrong signature
~~~

### 9.1. Vì sao ví dụ không cần mở private member cho framework?

`describe`, `add`, `pair` là static methods private của **chính class đang gọi `MethodHandles.lookup()`**. Caller lookup trong `ArgumentAdaptersDemo` có quyền tra các method ấy, nên có thể tạo handle bằng `findStatic`.

Nếu thay target bằng member private thuộc module khác, việc tạo **target handle** phải tuân thủ quyền của `Lookup` và JPMS. Hai combinator chỉ xử lý một handle đã tồn tại; chúng **không** giúp vượt qua access checks của lookup.

### 9.2. Kết quả “type matches” chứng minh điều gì?

~~~java
reordered.type().equals(reorderedType)
~~~

So sánh này chứng minh adapter có **`MethodType` đã yêu cầu**, không chứng minh mảng `reorder` diễn đạt đúng nghiệp vụ. Ví dụ nếu tất cả tham số đều `String`, đảo nhầm chỉ số có thể vẫn tạo adapter hợp lệ nhưng cho kết quả sai.

Vì vậy cần ít nhất hai lớp kiểm tra:

1. **Kiểu:** `handle.type().equals(expectedType)`.
2. **Hành vi:** truyền các giá trị dễ phân biệt và kiểm tra thứ tự target thực sự nhận.

### 9.3. Bắt lỗi đúng giai đoạn

`IllegalArgumentException` trong các khối `dropArguments`/`permuteArguments` thuộc **giai đoạn tạo adapter**. `WrongMethodTypeException` của `invokeExact` thuộc **giai đoạn gọi adapter**. Phân loại lỗi này rất quan trọng khi phát triển dispatcher: sai sơ đồ chữ ký khác với caller gọi sai chữ ký đã xác lập.

## 10. Target là virtual method: receiver cũng nằm trong MethodType

Không phải target nào cũng là static method. Với `Lookup.findVirtual`, `MethodHandle` thu được có **receiver ở tham số đầu tiên**.

Ví dụ:

~~~java
MethodHandle concat = MethodHandles.lookup().findVirtual(
        String.class,
        "concat",
        MethodType.methodType(String.class, String.class));
~~~

Dù khai báo Java của `String.concat` có một parameter `String str`, handle cho method ảo có kiểu:

~~~text
(String receiver, String argument)String
~~~

Vì vậy cả hai chuỗi đều tham gia danh sách mà `permuteArguments` có thể sắp xếp.

### 10.1. Đổi vị trí receiver và argument

~~~java
MethodHandle reversedConcat = MethodHandles.permuteArguments(
        concat,
        MethodType.methodType(
                String.class, String.class, String.class),
        1, 0);

String result = (String) reversedConcat.invokeExact("A", "B");
System.out.println(result); // BA
~~~

Phân tích:

~~~text
incoming: ["A", "B"]
target receiver <- incoming[1] = "B"
target argument <- incoming[0] = "A"
target executes "B".concat("A") -> "BA"
~~~

Đây là **receiver được đưa qua adapter**, không phải receiver được tìm lại theo tên khi chạy. Có thể đảo vị trí receiver trong chữ ký mới khi các kiểu khớp, nhưng target vẫn là method `Lookup` đã phân giải.

### 10.2. Chèn tham số trước receiver

~~~java
MethodHandle tracedConcat = MethodHandles.dropArguments(
        concat, 0, long.class);
~~~

Chữ ký mới là `(long,String,String)String`, gồm một `long` trace bị bỏ qua, receiver `String` và argument `String`.

Đừng quên tính receiver trong `target.type().parameterCount()`. Lỗi phổ biến là đếm một virtual method chỉ có một tham số và dự đoán `reorder.length == 1`, trong khi target handle thực tế có **hai tham số gồm receiver**.

### 10.3. Adapter không vượt quyền Lookup

`findVirtual`, `findStatic`, `findGetter` hoặc các factory khác phải tạo được target handle theo quyền của `MethodHandles.Lookup`. `dropArguments` và `permuteArguments` không tra cứu member mới và không mở private access trái phép.

Một handle đã tạo có thể mang quyền thực thi member tương ứng như một capability. Khi chia sẻ nó cho module/plugin khác, cân nhắc phạm vi quyền; adapter không phải cách sandbox hay ủy quyền an toàn mặc định.

## 11. Bảng lỗi: tạo adapter và gọi adapter là hai giai đoạn

| Trường hợp | Giai đoạn | Kết quả | Cách xử lý |
| --- | --- | --- | --- |
| `dropArguments` có `pos=-1` | Tạo adapter | `IllegalArgumentException` | `pos` thuộc `[0,N]` |
| `dropArguments` có `pos>N` | Tạo adapter | `IllegalArgumentException` | Đếm đúng số tham số của target |
| `valueTypes` chứa `void.class` | Tạo adapter | `IllegalArgumentException` | Chỉ dùng kiểu tham số hợp lệ |
| `target` hoặc tham số bắt buộc là `null` | Tạo adapter | `NullPointerException` | Cung cấp handle/type đầy đủ |
| `reorder.length` khác target arity | Tạo adapter | `IllegalArgumentException` | Một index cho **mỗi tham số target** |
| `reorder[k]` âm hoặc ngoài incoming arity | Tạo adapter | `IllegalArgumentException` | Chỉ số thuộc `[0,I)` |
| Kiểu incoming được chọn khác kiểu target slot `k` | Tạo adapter | `IllegalArgumentException` | `Class` ở hai vị trí phải giống hệt |
| `newType.returnType()` khác return type target | Tạo adapter | `IllegalArgumentException` | Giữ nguyên return type hoặc dùng adapter conversion khác |
| Chèn quá nhiều tham số, vượt giới hạn JVM | Tạo adapter | `IllegalArgumentException` | Giảm arity, đóng gói dữ liệu |
| `invokeExact` dùng sai kiểu hoặc thứ tự tại call site | Gọi adapter | `WrongMethodTypeException` | Dùng đúng `handle.type()` |
| `invoke` yêu cầu conversion không hợp lệ | Gọi adapter | `WrongMethodTypeException` hoặc lỗi conversion liên quan | Xem `asType` và runtime type |
| Target tự ném exception | Gọi adapter | Exception từ target | Xử lý theo hợp đồng target |

### 11.1. Sai kiểu dù Java có thể boxing

Target `add` nhận `int`, nhưng newType lại dùng `Integer.class`:

~~~java
// add.type() = (int,int)int
MethodType wrong = MethodType.methodType(
        int.class, Integer.class, int.class);

MethodHandle invalid = MethodHandles.permuteArguments(
        add, wrong, 0, 1);
~~~

`Integer.class` không đồng nhất với `int.class`, vì vậy adapter bị từ chối. Java có boxing/unboxing trong những ngữ cảnh khác không làm `permuteArguments` có thêm quyền chuyển đổi.

Nếu thực sự muốn một handle nhận `Integer` và chuyển thành `int`, hãy cân nhắc `asType` ở một bước riêng:

~~~java
MethodHandle converted = add.asType(
        MethodType.methodType(
                int.class, Integer.class, int.class));
~~~

`asType` có hợp đồng conversion riêng; nó không làm thay đổi yêu cầu strict type equality của `permuteArguments`.

### 11.2. Sai chiều reorder

Target `describe(String,int,boolean)String` và incoming `(boolean,String,int)String`. Mảng đúng là `[1,2,0]`. Nếu viết `[0,1,2]`, target yêu cầu `String` ở slot 0 nhưng incoming index 0 lại là `boolean`, nên thất bại **ngay lúc tạo adapter**.

Nhưng nếu các tham số cùng kiểu, một mảng đảo sai vẫn có thể vượt type checks và tạo kết quả sai. Vì vậy cần kiểm thử giá trị để phát hiện lỗi logic.

### 11.3. Kiểu trả về là một phần của hợp đồng

Hai chữ ký:

~~~text
(String,int)String
(String,int)Object
~~~

khác nhau. `permuteArguments` không cho đổi return type từ `String` sang `Object`. Nếu cần thích ứng kết quả, dùng `asType` hoặc `filterReturnValue` khi phù hợp, không thay `newType.returnType()` rồi kỳ vọng combinator tự chuyển.

## 12. Chọn adapter nào cho yêu cầu thực tế?

| Nhu cầu | API phù hợp | Điểm cần nhớ |
| --- | --- | --- |
| Thêm metadata không sử dụng trước/sau tham số | `dropArguments` | Chèn tại `pos`, giữ nguyên return type |
| Đảo thứ tự argument để khớp callback | `permuteArguments` | `reorder[k]` là incoming index cho target slot `k` |
| Dùng một argument cho hai target slots | `permuteArguments` | Lặp chỉ số nếu các kiểu tương ứng bằng nhau |
| Bỏ incoming argument và đổi thứ tự phần còn lại | `permuteArguments` | Incoming index không xuất hiện sẽ bị bỏ |
| Gắn một giá trị cố định vào tham số | `insertArguments` | Khác với chèn dummy argument |
| Chuyển đổi kiểu tham số hoặc return type | `MethodHandle.asType` | Chỉ conversion mà hợp đồng cho phép |
| Biến đổi từng tham số bằng một hàm khác | `filterArguments` | Khác với chỉ di chuyển chỉ số |
| Xử lý kết quả trước khi trả cho caller | `filterReturnValue` | Hai combinator chính giữ nguyên return type |
| Khớp một đoạn danh sách kiểu, thêm dummy ở vị trí thích hợp | `dropArgumentsToMatch` | Có hợp đồng riêng về `skip`/`pos` |
| Sắp xếp lại tọa độ của `VarHandle` | `permuteCoordinates` | Không phải `permuteArguments` của MethodHandle |

Khi thiết kế pipeline, **mỗi bước nên có một nhiệm vụ rõ**: `dropArguments` biểu diễn tham số không dùng, `permuteArguments` biểu diễn thứ tự vị trí, `asType` biểu diễn chuyển đổi kiểu. Sự tách biệt này giúp review và chẩn đoán lỗi chính xác.

## 13. Checklist kiểm chứng MethodType

Khi viết adapter, kiểm tra:

- [ ] Đã đọc `target.type()`, không suy chỉ từ chữ ký method trong source.
- [ ] Với virtual target, đã tính receiver trong danh sách tham số.
- [ ] `dropArguments`: `pos` nằm từ `0` đến `N`; không có `void.class` hoặc `null` trong `valueTypes`.
- [ ] `dropArguments`: thứ tự các tham số gốc không đổi, return type không đổi.
- [ ] `permuteArguments`: `reorder.length == target.type().parameterCount()`.
- [ ] Mỗi `reorder[k]` là index hợp lệ của `newType`.
- [ ] `newType.parameterType(reorder[k]) == target.type().parameterType(k)`.
- [ ] `newType.returnType() == target.type().returnType()`.
- [ ] Nếu lặp index, đó là **chủ ý dùng cùng incoming value nhiều lần**.
- [ ] Nếu thiếu index, đó là **chủ ý bỏ incoming value**.
- [ ] Đã so `adapter.type().equals(expectedType)`.
- [ ] `invokeExact` dùng đúng compile-time types, gồm return type của call site.
- [ ] Đã thử những giá trị phân biệt để phát hiện sai thứ tự.
- [ ] Phân biệt exception lúc **tạo** và lúc **gọi** adapter.
- [ ] Không dùng combinator như cách vượt quyền Lookup hoặc module boundary.
- [ ] Khi source hoặc callback signature thay đổi, chạy lại phép kiểm tra `MethodType` và hành vi.

### 13.1. Kiểm tra tự động với assert

Trong method có `throws Throwable`:

~~~java
MethodType expected = MethodType.methodType(
        String.class, boolean.class, String.class, int.class);

MethodHandle reordered = MethodHandles.permuteArguments(
        describe, expected, 1, 2, 0);

assert reordered.type().equals(expected);

String result = (String) reordered.invokeExact(
        true, "Mai", 4);

assert result.equals("Mai:4:true");
~~~

Để bật Java assertions:

~~~bash
java -ea ArgumentAdaptersDemo
~~~

Không truyền `-ea` thì `assert` thường bị vô hiệu hóa. Với dự án thực tế, nên bổ sung unit tests vì chúng kiểm tra kết quả bất kể cấu hình assertions của launcher.

## 14. Bài tập tự đánh giá

### Bài 1 — Chèn một tham số đầu

Target có kiểu `(String,int)String`. `dropArguments(target,0,long.class)` tạo kiểu nào?

**Đáp án:** `(long,String,int)String`. `long` mới ở vị trí đầu bị loại trước khi target nhận hai tham số gốc.

### Bài 2 — Chèn hai tham số ở giữa

Target `(int,int)int`. `dropArguments(target,1,boolean.class,String.class)` trả handle kiểu gì?

**Đáp án:** `(int,boolean,String,int)int`. Boolean và String ở giữa được bỏ qua.

### Bài 3 — Vị trí pos cuối cùng

Target có ba tham số. `dropArguments(target,3,String.class)` hợp lệ không?

**Đáp án:** Có. `pos == N` hợp lệ và chèn `String` vào cuối chữ ký adapter.

### Bài 4 — Tính reorder

Target `(String,int,boolean)String`, nhưng caller muốn `(boolean,String,int)String`. Mảng `reorder` nào đúng?

**Đáp án:** `[1,2,0]`, vì target String từ incoming 1, target int từ incoming 2, target boolean từ incoming 0.

### Bài 5 — Đảo chiều khiến lỗi

Với bài 4, nếu dùng `[0,1,2]` thì điều gì xảy ra?

**Đáp án:** `IllegalArgumentException` ngay khi tạo adapter vì target slot 0 cần String, nhưng incoming slot 0 có kiểu boolean.

### Bài 6 — Nhân bản một giá trị

Target `subtract(int,int)int` trả `a-b`. Muốn handle mới nhận một `int` rồi truyền giá trị ấy vào cả hai tham số target, viết thế nào?

**Đáp án:**

~~~java
MethodHandle sameValue = MethodHandles.permuteArguments(
        subtract,
        MethodType.methodType(int.class, int.class),
        0, 0);
~~~

Handle mới `(int)int` luôn trả `0` nếu target chỉ thực hiện phép trừ số học thông thường (bỏ qua các tác động ngoại lệ hay hành vi phụ khác).

### Bài 7 — Bỏ một incoming argument

Target `(int,int)int`; incoming `(String,int,int)int`. Làm thế nào bỏ String bằng `permuteArguments`?

**Đáp án:**

~~~java
MethodHandle adapted = MethodHandles.permuteArguments(
        add,
        MethodType.methodType(
                int.class, String.class, int.class, int.class),
        1, 2);
~~~

Incoming index 0 không có trong `reorder` nên bị bỏ.

### Bài 8 — Hai cách bỏ argument có tương đương?

Với `add(int,int)`, so `dropArguments(add,0,String.class)` và `permuteArguments(add,(String,int,int)int,1,2)`.

**Đáp án:** Cả hai cho `(String,int,int)int` và chuyển hai số cho `add`. Nhưng combinator thứ nhất mô tả vị trí chèn, còn thứ hai mô tả mapping index.

### Bài 9 — Sai kiểu do boxing

Target `(int,int)int`; newType `(Integer,int)int` và reorder `[0,1]`. `permuteArguments` có tự unbox `Integer` không?

**Đáp án:** Không. Factory yêu cầu kiểu parameter ở mỗi mapping phải giống hệt nhau. Có thể dùng `asType` ở một bước riêng nếu cần conversion hợp lệ.

### Bài 10 — Sai return type

Target trả `String`; `newType` trả `Object`, còn các parameter types và reorder đều đúng. Có hợp lệ không?

**Đáp án:** Không. `newType.returnType()` phải đồng nhất với return type của target. `permuteArguments` không thực hiện return conversion.

### Bài 11 — Receiver của virtual handle

`lookup.findVirtual(String.class,"concat",methodType(String.class,String.class))` có bao nhiêu tham số trong `handle.type()`?

**Đáp án:** Hai: receiver `String` và tham số `String` của method. Chữ ký là `(String,String)String`.

### Bài 12 — Chữ ký bị đảo lúc invokeExact

Adapter có kiểu `(boolean,String,int)String`. Caller gọi `(String)adapter.invokeExact("Mai",4,true)`. Có thể xảy ra gì?

**Đáp án:** `WrongMethodTypeException` vì kiểu và thứ tự ở call site khác chữ ký handle. Combinator đã sắp xếp bên trong adapter, nhưng caller phải gọi đúng **kiểu adapter**, không phải kiểu target.

### Bài 13 — Bỏ qua argument có bỏ luôn side effect?

Caller gọi một adapter đã được `dropArguments` thêm tham số và truyền vào kết quả của `expensive()`. Liệu `expensive()` không được đánh giá?

**Đáp án:** Không. Java đánh giá argument expression trước khi gọi handle. Giá trị trả về của `expensive()` bị adapter bỏ trước khi gọi target, nhưng side effect đã xảy ra.

### Bài 14 — Kết hợp hai combinator

Target `(String,int,boolean)String`. Thêm một `Context` không dùng ở đầu, rồi tạo callback `(boolean,Context,String,int)String`. Mảng `reorder` ở bước thứ hai là gì?

**Đáp án:** `[1,2,3,0]` vì target của `permuteArguments` lúc đó là `(Context,String,int,boolean)String`.

### Bài 15 — Khi source thay đổi

Một method `describe` đổi tham số `int` thành `long`. Có thể giữ nguyên `newType` và `reorder` cũ vì tên method không đổi không?

**Đáp án:** Không nên. Target handle mới có parameter type khác, nên các vị trí tương ứng trong `newType` cũng phải đổi thành `long.class`, hoặc cần adaptation type có chủ đích. Hãy kiểm tra `target.type()` và chạy lại unit tests.

## Tổng kết

- `dropArguments` tạo handle mới nhận **thêm** tham số bị bỏ trước khi gọi target; `pos` nằm trong `[0,N]` và return type giữ nguyên.
- `permuteArguments` tạo handle mới theo `newType`; với mỗi target slot `k`, lấy incoming index `reorder[k]`.
- `reorder.length` phải bằng số tham số **target**, mọi index hợp lệ, các parameter types và return type phải **khớp chính xác**; combinator không thực hiện conversion.
- `permuteArguments` có thể lặp index để nhân bản giá trị hoặc bỏ index để loại incoming argument, không chỉ hoán vị một-một.
- Hai combinator có thể ghép để thích ứng chữ ký callback, nhưng cần vẽ bản đồ kiểu sau mỗi bước.
- Với virtual method handle, **receiver cũng là một tham số**, nên phải được tính vào arity và mapping.
- `handle.type()` kiểm tra hợp đồng kiểu; test bằng giá trị phân biệt kiểm tra cả hợp đồng **hành vi**.
- `IllegalArgumentException` thường xuất hiện khi tạo adapter sai; `WrongMethodTypeException` thường do call site `invokeExact` không khớp.
- Các combinator không thay đổi quyền của `Lookup` và không làm target chuyển thành method khác.
- Kiến thức này vẫn áp dụng trên JDK hiện đại; có thể kết hợp với `asType`, `insertArguments` và các adapter khác theo đúng hợp đồng công khai.

## Nguồn tham khảo chính thức

1. [Oracle — MethodHandles, Java SE 26: dropArguments và permuteArguments](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): cú pháp, quy tắc vị trí, bản đồ reorder, nhân bản/bỏ tham số, lỗi và ví dụ.
2. [Oracle — MethodType, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodType.html): kiểu trả về, thứ tự parameter types và việc xây dựng `MethodType`.
3. [Oracle — MethodHandle, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact()`, `invoke()` và `WrongMethodTypeException`.
4. [Oracle — MethodHandles.Lookup, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findStatic`, `findVirtual`, quyền truy cập và receiver của virtual handle.
5. [OpenJDK — JEP 416: Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): Java 18 tái triển khai Core Reflection dựa trên MethodHandle, không yêu cầu phụ thuộc chi tiết triển khai.
