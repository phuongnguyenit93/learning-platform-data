# 8.3 Đổi thứ tự, lặp hoặc bỏ vị trí đối số bằng permuteArguments

`MethodHandles.permuteArguments` là một *combinator* của Java MethodHandle: nó tạo **handle mới** có danh sách tham số đầu vào do ta chọn, rồi ánh xạ các tham số ấy tới những vị trí mà handle gốc (*target*) cần. Ba tác dụng quan trọng nhất là **đổi thứ tự**, **dùng lặp một đối số**, và **bỏ qua đối số đầu vào không cần thiết**. Nhờ đó, một hàm đã tồn tại có thể được ghép vào giao diện gọi mới mà không cần viết lại thân hàm, tạo lớp wrapper thủ công hay dùng Reflection lặp lại.

Bài học thuộc chủ đề **8. Kết hợp lời gọi** (*method-handle combinators*). Nó giải thích chính xác quy ước chỉ số `reorder`, `MethodType` đích và mới, điều kiện hợp lệ về kiểu, cách gọi bằng `invokeExact`, cũng như tình huống áp dụng cho bộ định tuyến sự kiện, bộ thích nghi callback, logic pipeline và bộ gọi động. Ví dụ dùng Java 17+.

**Sau bài này, bạn sẽ:**

- Đọc được `target.type()` và `newType`, rồi thiết kế đúng ánh xạ `reorder`.
- Phân biệt “đầu vào của handle mới” với “đối số mà target nhận”.
- Dùng cùng một cơ chế cho đảo vị trí, sao chép vị trí và loại bỏ các vị trí không dùng.
- Nhận diện lỗi độ dài mảng ánh xạ, chỉ số vượt biên, kiểu tham số hoặc kiểu trả về không trùng khớp.
- Biết khi nào dùng `permuteArguments`, `dropArguments`, `insertArguments`, `filterArguments` hoặc `asType` để nối các bước xử lý.

## 1. Chữ ký và mô hình dữ liệu

API của JDK 17:

```java
public static MethodHandle permuteArguments(
        MethodHandle target, MethodType newType, int... reorder)
```

Đây là **chữ ký tham khảo**, không phải chương trình Java độc lập. Ba tham số có ý nghĩa:

| Tham số | Vai trò |
| --- | --- |
| `target` | Handle gốc sẽ được thực thi cuối cùng; có kiểu `target.type()` |
| `newType` | Kiểu đầy đủ (tham số và kết quả) mà **handle mới trả về** phải có |
| `reorder` | Mảng chỉ số cho biết mỗi tham số của `target` được lấy từ **vị trí nào trong đầu vào handle mới** |

Gọi:

- **Incoming**: danh sách tham số mà *người gọi handle mới* truyền vào, được mô tả bởi `newType`. Đánh số từ `0`.
- **Outgoing**: danh sách tham số thật sự chuyển tiếp vào `target`, được mô tả bởi `target.type()`. Cũng đánh số từ `0`.

Quy tắc trung tâm là:

```text
targetArgument[i] = incomingArgument[reorder[i]]
i = 0, 1, ..., target.type().parameterCount() - 1
```

Dấu `=` ở đây mô tả phép ánh xạ giá trị, không có thao tác gán vào một mảng Java cụ thể mà người học phải tự tạo. **Chỉ số `i` thuộc về tham số của target**, còn **giá trị `reorder[i]` trỏ tới vị trí trong danh sách đầu vào của handle mới**.

Độ dài `reorder` phải **bằng số tham số của target**, không phải số tham số của `newType`:

```text
reorder.length == target.type().parameterCount()
0 <= reorder[i] < newType.parameterCount()
```

Ngoài ra:

- `newType.returnType() == target.type().returnType()`.
- Với mỗi vị trí `i` của target: `newType.parameterType(reorder[i]) == target.type().parameterType(i)`.
- Dấu `==` giữa các `Class<?>` ở đây thể hiện **cùng loại kiểu chính xác**, bao gồm primitive, interface, mảng và lớp; không tự chuyển sang supertype hay boxed type.
- Trong những vị trí đầu vào mà `reorder` không nhắc tới, kiểu có thể khác tùy `newType`; target không nhìn thấy chúng.
- Handle kết quả có `type()` **chính xác bằng `newType`**. Handle gốc không bị sửa đổi.

Để hiểu ánh xạ, luôn viết trước danh sách tham số của target và newType rồi điền từng `reorder[i]`, thay vì nhìn vào mảng chỉ số rồi đoán.

## 2. Đổi thứ tự đối số: hoán đổi vị trí

Giả sử có hàm:

```java
static String render(String left, int amount, String right) {
    return left + ":" + amount + ":" + right;
}
```

Đoạn khai báo này là minh họa. Handle gốc có kiểu:

```text
target.type() = (String,int,String)String

Target nhận:  [left:String, amount:int, right:String]
Vị trí:          0           1           2
```

Hệ thống gọi mới lại cung cấp thứ tự `(String left, String right, int amount)`. Ta muốn:

```text
newType = (String,String,int)String

Incoming:      [left:String, right:String, amount:int]
Vị trí:             0             1            2

Target position 0 (left:String)   <- incoming position 0
Target position 1 (amount:int)    <- incoming position 2
Target position 2 (right:String)  <- incoming position 1

reorder = [0, 2, 1]
```

Vậy biểu thức tạo adapter là:

```java
MethodHandle adapted = MethodHandles.permuteArguments(
        target,
        MethodType.methodType(String.class,
                String.class, String.class, int.class),
        0, 2, 1);
```

Đây là đoạn minh họa với `target` đã tra cứu đúng method `render`. Handle mới có kiểu `(String,String,int)String`. Khi gọi `adapted("left", "right", 7)` thì target nhận `("left", 7, "right")` và trả `"left:7:right"`.

**Bảng xác nhận theo từng vị trí của target:**

| `i` của target | Target cần kiểu | `reorder[i]` | New incoming tương ứng |
| --- | --- | --- | --- |
| `0` | `String` | `0` | `left` ở new index 0 |
| `1` | `int` | `2` | `amount` ở new index 2 |
| `2` | `String` | `1` | `right` ở new index 1 |

Một phép đảo đơn giản với `subtract(int a, int b)` có target kiểu `(int,int)int`: dùng cùng `newType` và `reorder = [1,0]`. Khi gọi handle mới với `(2,10)`, target thực sự nhận `(10,2)` nên kết quả là `8`, thay vì `-8`.

## 3. Lặp một đối số: sao chép vị trí, không sao chép object

Không bắt buộc `reorder` là một hoán vị toán học (*permutation*) có từng chỉ số xuất hiện một lần. Chỉ số **được phép lặp**.

Giả sử target tính `sum(int a, int b)` với kiểu `(int,int)int`. Muốn hàm mới chỉ nhận **một `int`** rồi cộng giá trị đó với chính nó:

```text
newType:          (int)int
incoming index:     0

target input 0 = incoming[0]
target input 1 = incoming[0]

reorder = [0, 0]
```

```java
MethodHandle twice = MethodHandles.permuteArguments(
        sum,
        MethodType.methodType(int.class, int.class),
        0, 0);
```

Khi gọi `twice(21)`, target nhận `sum(21,21)` và trả `42`.

**Điều kiện kiểu:** cả hai vị trí target được nối tới incoming index 0 phải có cùng kiểu chính xác. Không thể dùng cùng một incoming `int` cho một target tham số `int` và một tham số `long`, vì `permuteArguments` **không tự widening**.

Nếu incoming là một **tham chiếu đến object mutable**, việc “lặp” chỉ dùng lại cùng một tham chiếu; nó **không clone** object. Một hàm đích nhận hai tham số tham chiếu có thể nhìn thấy cả hai trỏ tới đúng một instance. Với dữ liệu bất biến hay primitive, điều này thường không gây vấn đề; với mutable state, cần hiểu aliasing và side effects.

## 4. Bỏ qua một hoặc nhiều vị trí đầu vào

Target `identify(String name)` có kiểu `(String)String`. Giao diện gọi mới có kiểu `(String,boolean,long)String`, nhưng target chỉ cần tên. Ta có thể tạo:

```java
MethodHandle adapter = MethodHandles.permuteArguments(
        identify,
        MethodType.methodType(String.class,
                String.class, boolean.class, long.class),
        0);
```

`reorder = [0]` vì target chỉ có một tham số và cần incoming index 0. Các vị trí incoming index 1 (`boolean`) và index 2 (`long`) **không xuất hiện** trong `reorder`, nên bị bỏ qua. Gọi adapter với `("Ada", true, 99L)` sẽ gọi target bằng `("Ada")`.

Quy tắc quan trọng:

- `reorder` không chứa một giá trị đặc biệt như `-1` để biểu diễn “bỏ”.
- Muốn bỏ incoming index `j`, chỉ việc **không ghi `j` vào mảng reorder**.
- Những incoming bị bỏ vẫn **phải được truyền vào handle mới** vì `newType` khai báo chúng. Không thể bỏ chúng ngay tại call site của `invokeExact`.
- Việc đánh giá biểu thức đối số vẫn diễn ra **trước lời gọi** theo Java. Bỏ một vị trí không xóa được side effect xảy ra khi tính biểu thức để truyền vào vị trí ấy.
- Đối số bị bỏ có thể là bất kỳ kiểu Java hợp lệ nào được khai báo trong `newType`, miễn các vị trí được dùng giữ đúng kiểu.

**Trường hợp target không tham số:** nếu target `fixed()` có kiểu `()String`, `reorder` phải là mảng **rỗng**. Khi đó newType có thể là `(int,String)String` và tất cả đầu vào bị bỏ:

```java
MethodHandle ignored = MethodHandles.permuteArguments(
        fixed,
        MethodType.methodType(String.class, int.class, String.class));
```

Không có các chỉ số `reorder` sau `newType` là hợp lệ vì phương thức varargs `int... reorder` nhận danh sách rỗng. Kết quả vẫn chỉ gọi `fixed()` một lần.

## 5. Ba thao tác có thể kết hợp trong cùng một ánh xạ

Lấy target kiểu `(String,String)String`, thực hiện `prefix(a,b)` trả `a + "/" + b`. Muốn handle mới nhận `(long,String,boolean,String)String`, target sử dụng:

- target argument 0 ← incoming argument 3: chuỗi cuối.
- target argument 1 ← incoming argument 1: chuỗi giữa.
- incoming argument 0 (`long`) và 2 (`boolean`) bị bỏ.

`reorder = [3,1]` sẽ tạo đúng adapter. Nếu newType là `(String)String` và `reorder = [0,0]`, cùng target được dùng để **nhân đôi** đầu vào thành `"x/x"`. Có thể đồng thời đổi chỗ, lặp và bỏ, miễn các điều kiện về kiểu và số lượng được thỏa mãn.

Ví dụ ứng dụng: một callback cũ nhận `(String topic,String action)`, trong khi bộ định tuyến mới cung cấp `(long timestamp,String action,boolean dryRun,String topic)`. `permuteArguments` thay lớp wrapper thủ công bằng ánh xạ `[3,1]` và trả về handle báo đúng kiểu mới.

## 6. Chương trình Java 17+ đầy đủ: hoán đổi, lặp, bỏ và lỗi

Tạo tệp **`PermuteArgumentsDemo.java`** với nội dung sau:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class PermuteArgumentsDemo {
    public static String render(String left, int amount, String right) {
        return left + ":" + amount + ":" + right;
    }

    public static int sum(int a, int b) {
        return a + b;
    }

    public static int subtract(int a, int b) {
        return a - b;
    }

    public static String identify(String name) {
        return "id=" + name;
    }

    public static String fixed() {
        return "ready";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle render = lookup.findStatic(PermuteArgumentsDemo.class, "render",
                MethodType.methodType(String.class, String.class, int.class, String.class));
        MethodHandle reordered = MethodHandles.permuteArguments(render,
                MethodType.methodType(String.class, String.class, String.class, int.class),
                0, 2, 1);
        System.out.println("render original=" + render.type());
        System.out.println("render new=" + reordered.type());
        System.out.println("render=" + (String) reordered.invokeExact("left", "right", 7));

        MethodHandle sum = lookup.findStatic(PermuteArgumentsDemo.class, "sum",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle twice = MethodHandles.permuteArguments(sum,
                MethodType.methodType(int.class, int.class), 0, 0);
        System.out.println("twice type=" + twice.type());
        System.out.println("twice=" + (int) twice.invokeExact(21));

        MethodHandle subtract = lookup.findStatic(PermuteArgumentsDemo.class, "subtract",
                MethodType.methodType(int.class, int.class, int.class));
        MethodHandle swapped = MethodHandles.permuteArguments(subtract,
                subtract.type(), 1, 0);
        System.out.println("subtract=" + (int) subtract.invokeExact(2, 10));
        System.out.println("swapped=" + (int) swapped.invokeExact(2, 10));

        MethodHandle identify = lookup.findStatic(PermuteArgumentsDemo.class, "identify",
                MethodType.methodType(String.class, String.class));
        MethodHandle ignored = MethodHandles.permuteArguments(identify,
                MethodType.methodType(String.class, String.class, boolean.class, long.class), 0);
        System.out.println("ignored type=" + ignored.type());
        System.out.println("ignored=" + (String) ignored.invokeExact("Ada", true, 99L));

        MethodHandle fixed = lookup.findStatic(PermuteArgumentsDemo.class, "fixed",
                MethodType.methodType(String.class));
        MethodHandle zero = MethodHandles.permuteArguments(fixed,
                MethodType.methodType(String.class, int.class, String.class));
        System.out.println("zero=" + (String) zero.invokeExact(3, "unused"));

        try {
            MethodHandles.permuteArguments(sum,
                    MethodType.methodType(int.class, long.class, int.class), 0, 1);
        } catch (IllegalArgumentException e) {
            System.out.println("type mismatch=" + e.getClass().getSimpleName());
        }
        try {
            MethodHandles.permuteArguments(sum,
                    MethodType.methodType(int.class, int.class), 0, 1);
        } catch (IllegalArgumentException e) {
            System.out.println("bad index=" + e.getClass().getSimpleName());
        }
        try {
            MethodHandles.permuteArguments(sum,
                    MethodType.methodType(int.class, int.class, int.class), 0);
        } catch (IllegalArgumentException e) {
            System.out.println("wrong length=" + e.getClass().getSimpleName());
        }
        try {
            MethodHandles.permuteArguments(sum,
                    MethodType.methodType(long.class, int.class, int.class), 0, 1);
        } catch (IllegalArgumentException e) {
            System.out.println("return mismatch=" + e.getClass().getSimpleName());
        }
    }
}
```

Dùng JDK 17 hoặc mới hơn, lưu đúng tên tệp (trùng `public class`), biên dịch và chạy:

```bash
javac --release 17 PermuteArgumentsDemo.java
java PermuteArgumentsDemo
```

`stdout` đầy đủ, đúng với chương trình:

```text
render original=(String,int,String)String
render new=(String,String,int)String
render=left:7:right
twice type=(int)int
twice=42
subtract=-8
swapped=8
ignored type=(String,boolean,long)String
ignored=id=Ada
zero=ready
type mismatch=IllegalArgumentException
bad index=IllegalArgumentException
wrong length=IllegalArgumentException
return mismatch=IllegalArgumentException
```

Các dòng `render` cho thấy việc map `[0,2,1]`; `twice` kiểm tra `[0,0]`; `swapped` kiểm tra `[1,0]`; `ignored` giữ index 0 và bỏ các index còn lại. `zero` chứng minh target `()String` có thể gắn với giao diện nhận đầu vào mà không dùng chúng.

Bốn exception cuối đều xảy ra **khi tạo adapter**, trước khi target được gọi. Đây là validation cấu trúc của `permuteArguments`, không phải exception từ thân hàm `sum`:

1. `type mismatch`: target cần `int` tại position 0 nhưng newType cung cấp `long` ở index 0.
2. `bad index`: target có hai tham số; newType có một, nhưng `reorder[1] == 1` vượt phạm vi index hợp lệ (chỉ `0`).
3. `wrong length`: target có hai tham số nhưng mảng ánh xạ chỉ có một phần tử.
4. `return mismatch`: target trả `int`, newType lại khai báo trả `long`.

## 7. Receiver của phương thức instance cũng là một tham số handle

Không chỉ đối số trong khai báo phương thức mới có thể hoán đổi: với `MethodHandle` cho **instance method**, đối tượng receiver nằm ở **index 0 trong danh sách tham số của handle**. Vì vậy có thể đổi cả vị trí receiver bằng `permuteArguments`.

Ví dụ JDK có `StringBuilder.append(int)`. Nếu lấy bằng:

```java
MethodHandle append = MethodHandles.lookup().findVirtual(
        StringBuilder.class, "append",
        MethodType.methodType(StringBuilder.class, int.class));
```

`append.type()` là `(StringBuilder,int)StringBuilder`, nghĩa là trước tiên receiver `StringBuilder` rồi giá trị `int`. Một adapter cho thứ tự `(int,StringBuilder)StringBuilder` dùng `reorder=[1,0]`.

Chương trình đầy đủ **`ReceiverRoutingDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ReceiverRoutingDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle append = lookup.findVirtual(StringBuilder.class, "append",
                MethodType.methodType(StringBuilder.class, int.class));
        MethodHandle valueFirst = MethodHandles.permuteArguments(append,
                MethodType.methodType(StringBuilder.class, int.class, StringBuilder.class),
                1, 0);
        System.out.println("original=" + append.type());
        System.out.println("permuted=" + valueFirst.type());
        StringBuilder result = (StringBuilder) valueFirst.invokeExact(7, new StringBuilder("n="));
        System.out.println("result=" + result);

        MethodHandle prefix = lookup.findStatic(ReceiverRoutingDemo.class, "prefix",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle duplicate = MethodHandles.permuteArguments(prefix,
                MethodType.methodType(String.class, String.class), 0, 0);
        System.out.println("duplicate=" + (String) duplicate.invokeExact("x"));
        MethodHandle route = MethodHandles.permuteArguments(prefix,
                MethodType.methodType(String.class, long.class, String.class,
                        boolean.class, String.class), 3, 1);
        System.out.println("route=" + (String) route.invokeExact(55L, "inner", true, "outer"));
    }

    public static String prefix(String a, String b) {
        return a + "/" + b;
    }
}
```

```bash
javac --release 17 ReceiverRoutingDemo.java
java ReceiverRoutingDemo
```

`stdout`:

```text
original=(StringBuilder,int)StringBuilder
permuted=(int,StringBuilder)StringBuilder
result=n=7
duplicate=x/x
route=outer/inner
```

Giải thích:

- `valueFirst` có kiểu `(int,StringBuilder)StringBuilder`. Người gọi cung cấp giá trị `7` trước, rồi một `StringBuilder`; target vẫn nhận receiver ở vị trí đầu sau khi hoán đổi.
- `duplicate` biến `prefix(a,b)` thành callable một tham số, và hai tham số gốc cùng nhận `"x"`.
- `route` nhận bốn tham số mới, nhưng chỉ chuyển incoming index 3 (`"outer"`) và 1 (`"inner"`) vào target. Nó bỏ timestamp `55L` và cờ `true`.

Hãy chú ý: `MethodType.methodType(StringBuilder.class, int.class, StringBuilder.class)` có tham số thứ nhất `int` và thứ hai `StringBuilder`. Kết quả vẫn là `StringBuilder`. `permuteArguments` không tạo một instance mới; nó gọi đúng method gốc, nên `StringBuilder` có thể bị thay đổi như mọi lời gọi `append` thông thường.

## 8. Đúng kiểu quan trọng hơn tên và ý định

`permuteArguments` **không thực hiện conversion** đối số hoặc kết quả. Điều kiện tương thích dùng kiểu **đồng nhất** ở từng cạnh của ánh xạ; khác với những phép chuyển đổi có thể xảy ra tại call site của `MethodHandle.invoke` hay qua `asType`.

### 8.1. Kiểu nguyên thủy và wrapper

| Target cần | New incoming được dùng | Hợp lệ trong `permuteArguments`? |
| --- | --- | --- |
| `int` | `int` | Có |
| `int` | `long` | Không |
| `int` | `Integer` | Không |
| `String` | `String` | Có |
| `Object` | `String` | Không, dù `String` là subtype của `Object` |
| `String[]` | `String[]` | Có |
| `String[]` | `Object[]` | Không |
| Target trả `int` | NewType trả `long` | Không, dù Java có widening khi cần |

Để đổi kiểu, có thể dùng `MethodHandle.asType` trước hoặc sau bước `permuteArguments`, tùy kiểu thật sự cần cho từng cạnh. Điều này đòi hỏi bạn xác định rõ thứ tự transformation: `permuteArguments` chỉ làm **routing**, `asType` mới xử lý những chuyển đổi hỗ trợ.

Ví dụ với handle `twice` kiểu `(int)int` (từ chương trình đầu), bạn có thể thích nghi sang `(Integer)Integer` sau khi đã chọn đúng mapping:

```java
MethodHandle boxed = twice.asType(
        MethodType.methodType(Integer.class, Integer.class));
Integer value = (Integer) boxed.invokeExact(Integer.valueOf(21));
System.out.println(value); // 42
```

Đây là đoạn minh họa phụ thuộc `twice` của chương trình đầy đủ. `asType` dùng unboxing trên đầu vào và boxing trên kết quả; `permuteArguments` tự nó không cung cấp hai chuyển đổi này.

### 8.2. invokeExact sử dụng kiểu tại call site

`MethodHandle.invokeExact` yêu cầu chữ ký tại nơi gọi khớp **chính xác** với `handle.type()`, kể cả kiểu trả về. Chẳng hạn `reordered` có kiểu `(String,String,int)String`:

```java
String ok = (String) reordered.invokeExact("left", "right", 7);
```

Nếu thay kết quả mong đợi thành `Object`, hoặc truyền `long` thay cho `int`, lời gọi có thể biên dịch nhưng bị `WrongMethodTypeException` khi chạy. `invoke` có khả năng thích nghi kiểu trong giới hạn được hỗ trợ, còn `invokeExact` không tự thích nghi; cả hai đều không thay đổi mapping `reorder` đã chọn.

`permuteArguments` trả **handle fixed arity**, kể cả khi target gốc là một *varargs collector*. Nếu cần giao diện varargs về sau, phải thiết kế thêm bước chuyển thích hợp; đừng mặc định cờ varargs của handle cũ vẫn được giữ.

### 8.3. Kiểu trả về luôn giữ nguyên

Bạn có thể thay đổi vị trí, số lượng **đầu vào** của handle mới bằng `newType` và `reorder`, nhưng không thể dùng `permuteArguments` để đổi kiểu kết quả. Với target trả `int`, `newType` phải trả `int`. Muốn bỏ kết quả, dùng `MethodHandles.dropReturn` ở JDK hỗ trợ; muốn thích nghi kết quả qua chuyển kiểu, xem `asType` hoặc `filterReturnValue` với filter thích hợp.

## 9. Phân biệt với các combinator liên quan

| API | Làm gì | Khi nào nên chọn |
| --- | --- | --- |
| `permuteArguments` | Chọn vị trí incoming để đưa vào từng tham số target; có thể đảo, lặp, bỏ incoming | Hình dạng tham số không còn theo cùng thứ tự, hoặc cần dùng lặp một incoming |
| `dropArguments` | Thêm các tham số “dummy” ở một vị trí, bỏ qua chúng khi gọi target | Chỉ cần chèn những input không dùng mà vẫn giữ thứ tự tương đối của các input cũ |
| `insertArguments` | Gắn cố định giá trị vào một hay nhiều tham số của target | Một số đối số đã biết trước, ví dụ bind một ID cố định |
| `bindTo` | Gắn object vào tham số đầu của handle | Thường bind receiver hoặc input đầu tiên là tham chiếu |
| `filterArguments` | Đưa một hoặc nhiều tham số qua filter trước khi gọi target | Cần **chuyển đổi/tiền xử lý giá trị**, không chỉ đổi vị trí |
| `filterReturnValue` | Lọc/chuyển kết quả trả về của target bằng handle khác | Muốn thay đổi kết quả, không thay đổi route đầu vào |
| `asType` | Tạo adapter chuyển đổi kiểu nếu JVM hỗ trợ | Target/new caller cần boxing, cast hoặc chuyển primitive hợp lệ |
| `asSpreader` / `asCollector` | Đóng/mở danh sách mảng thành các tham số khi có hợp đồng chính xác | Cần chuyển đổi hình dạng mảng và danh sách tham số |

Ví dụ khi **chỉ** muốn thêm một đối số `long timestamp` vào trước target kiểu `(String)String`, có thể dùng:

```java
MethodHandle withTimestamp =
        MethodHandles.dropArguments(target, 0, long.class);
// Kiểu mới: (long,String)String.
```

Đoạn minh họa này giả định `target` đã có kiểu `(String)String`; không tự tạo độc lập. Với `permuteArguments` cũng làm được nhưng phải khai báo `newType=(long,String)String`, `reorder=[1]`. Nếu còn phải đổi trật tự và dùng lặp, `permuteArguments` thường biểu đạt rõ hơn.

**Lưu ý về kết hợp:** các combinator tạo ra handle mới; handle gốc là immutable. Có thể xây một chuỗi bước thích nghi (routing, bind, filter, conversion), nhưng cần xác định kiểu chính xác của **mỗi bước** trước khi nối. Không có “auto matching” giữa các combinator.

## 10. Checklist validate trước khi tạo adapter trong hệ thống động

Khi index mapping đến từ cấu hình hoặc logic runtime, hãy kiểm tra có chủ đích trước khi gọi `MethodHandles.permuteArguments`:

1. **Chọn target cụ thể**, biết `target.type()` và quyền gọi handle của nó. Handle có thể từ `findStatic`, `findVirtual`, `unreflect` hoặc combinator khác.
2. **Xác định giao diện mong muốn**: `newType` phải gồm đúng các tham số caller sẽ cung cấp và cùng kiểu trả về target.
3. **Tạo mảng `reorder` dài bằng tham số của target**. Tạo một phần tử cho **từng vị trí target**, kể cả khi các vị trí cùng lấy một incoming.
4. **Kiểm tra index hợp lệ** trong khoảng `0...newType.parameterCount()-1`. Nếu newType không có tham số, target cũng phải có 0 tham số để có thể map.
5. **Kiểm tra kiểu đồng nhất** cho từng cặp `target.type().parameterType(i)` và `newType.parameterType(reorder[i])`.
6. **Chỉ sau khi qua validation mới tạo handle** và lưu vào cache nếu phù hợp. `permuteArguments` tự kiểm tra lại khi tạo và ném `IllegalArgumentException` nếu không hợp lệ.
7. **In/log `handle.type()`, mapping và target type** khi chẩn đoán lỗi, tránh in dữ liệu bí mật của đối số. Khi chạy `invokeExact`, bảo đảm kiểu thực tế tại call site trùng `newType`.

Một hàm kiểm tra mapping có thể trông như sau (minh họa, cần import `MethodHandle`, `MethodType`):

```java
static boolean mappingMatches(MethodHandle target, MethodType newType, int[] reorder) {
    MethodType old = target.type();
    if (old.returnType() != newType.returnType()) return false;
    if (reorder.length != old.parameterCount()) return false;

    for (int i = 0; i < reorder.length; i++) {
        int j = reorder[i];
        if (j < 0 || j >= newType.parameterCount()) return false;
        if (old.parameterType(i) != newType.parameterType(j)) return false;
    }
    return true;
}
```

Hàm này chỉ kiểm tra những bất biến cốt lõi của `permuteArguments`; khi tích hợp thật cần xử lý đầu vào null, lỗi khám phá MethodType, giới hạn số tham số/slot của JVM, quyền truy cập và chính sách xử lý lỗi của ứng dụng. Với mapping hợp lệ, có thể gọi trực tiếp `MethodHandles.permuteArguments` mà không cần wrapper validation bổ sung nếu ứng dụng không cần báo lỗi chuyên biệt.

### 10.1. Tại sao không truyền chỉ số ngược lại?

Giả sử target có 2 tham số mà newType có 3. `reorder` luôn dài **2**, vì mỗi tham số target cần một nguồn. Không tạo mảng dài 3 rồi ghi đích của từng incoming; đó là hướng ánh xạ **ngược** và có thể khiến cấu hình sai.

Với target `(String,int)void`, newType `(int,String,boolean)void`, mapping đúng là `[1,0]` (target String ← incoming String index 1; target int ← incoming int index 0); incoming boolean index 2 bị bỏ. Mảng `[1,0,2]` là sai vì độ dài 3 khác arity 2 của target.

### 10.2. Có thể lặp một index kiểu khác không?

Với target `(int,long)void` và newType `(int)void`, `[0,0]` **không hợp lệ**: incoming index 0 có kiểu `int`, nhưng target position 1 cần `long`. Nếu muốn khai báo một incoming `int` để cấp cho cả `int` và `long`, hãy dùng combinator chuyển kiểu/phân phối dữ liệu phù hợp thay vì dựa vào implicit cast của `permuteArguments`.

## 11. Ngoại lệ và lỗi thường gặp

| Lỗi hoặc hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `IllegalArgumentException` khi gọi `permuteArguments` | `reorder.length` khác arity target; index âm/vượt biên; các kiểu nguồn–đích không đồng nhất; return type khác | Kiểm tra `target.type()`, `newType` và từng `reorder[i]` |
| `NullPointerException` khi tạo adapter | `target`, `newType` hay mảng `reorder` là `null` | Kiểm tra dữ liệu đầu vào, đừng dùng null cho mapping |
| `WrongMethodTypeException` lúc `invokeExact` | Chữ ký compile-time tại call site không trùng `handle.type()` | Xem chính xác `parameterType`, `returnType` và kiểu biểu thức gọi |
| `ClassCastException` trong pipeline đã dùng `asType` | Giá trị runtime không chuyển được về reference type cần thiết | Validate object đầu vào, xem đoạn adapter chuyển kiểu |
| Target được gọi với tham số bị đảo ngược | Hiểu `reorder` là map từ incoming sang target | Viết bảng: từng **vị trí target** lấy từ incoming index nào |
| Input “bỏ” vẫn gây side effect | Java đánh giá biểu thức tham số trước khi gọi handle | Chỉ bỏ **giá trị trong lời gọi target**, không bỏ quá trình tính tham số đầu vào |
| Duplicate object bị thay đổi ngoài ý muốn | Lặp cùng một tham chiếu mutable | Phân biệt alias và copy dữ liệu; thiết kế xử lý side effect |
| Dynamic invoker tưởng sẽ chọn overload khác | Handle đã trỏ tới một target cố định | Chọn MethodHandle đúng từ đầu, không kỳ vọng tự overload resolution |
| Target varargs nhưng adapter không còn varargs | Adapter `permuteArguments` luôn fixed arity | Thêm bước xử lý varargs nếu hợp đồng caller yêu cầu |
| Gọi handle từ cấu hình có param count sai | `newType` khác với số đầu vào caller thực sự truyền | Xác định trước contract; so sánh `newType.parameterCount()` với call site |

**Đừng nhầm lỗi khi tạo và lỗi khi gọi:** những mapping sai cấu trúc bị từ chối ở `permuteArguments` (thường `IllegalArgumentException`). Một adapter tạo thành công vẫn có thể bị gọi sai kiểu ở `invokeExact` (thường `WrongMethodTypeException`), hoặc code của target có thể ném exception riêng. MethodHandle không tự bọc exception target trong `InvocationTargetException` như `Method.invoke` của Reflection.

## 12. Bài tập tự kiểm tra

**Bài 1 — đảo tham số:** target `(int,int)int` làm `a-b`; muốn handle mới vẫn nhận hai int nhưng tạo kết quả `b-a`. Viết mapping.

**Đáp án:** `newType=(int,int)int`, `reorder=[1,0]`.

**Bài 2 — lặp tham số:** target `(String,String)String` nối `a+"/"+b`; muốn chỉ truyền một `String`. Viết mapping và dự đoán kết quả với `"x"`.

**Đáp án:** `newType=(String)String`, `reorder=[0,0]`; target nhận `("x","x")` và trả `"x/x"`.

**Bài 3 — bỏ tham số:** target `(String,int)String`; giao diện mới là `(long,int,String,boolean)String`. Chọn mapping.

**Đáp án:** `reorder=[2,1]`. Incoming index 2 là `String`, incoming index 1 là `int`; index 0 và 3 bị bỏ.

**Bài 4 — đếm mảng ánh xạ:** target `(int,int,int)void`, newType `(int)void`. Có thể lặp một input cho cả ba không?

**Đáp án:** Có; `reorder=[0,0,0]`, độ dài 3 bằng arity target. Target nhận ba lần cùng một `int`.

**Bài 5 — phân biệt phép chuyển kiểu:** target `(long,long)long`, newType `(int)long`, mapping `[0,0]`. Hợp lệ không?

**Đáp án:** Không. Target cần `long`, incoming index 0 có kiểu `int`. `permuteArguments` không widening; hãy thiết kế bước chuyển kiểu tương thích riêng, chẳng hạn tạo handle đã được `asType` thích nghi thích hợp trước khi permute.

**Bài 6 — receiver:** handle instance có kiểu `(Account,String)boolean`. Giao diện callback cần `(String,Account)boolean`. Mapping là gì?

**Đáp án:** `[1,0]`; input mới index 1 cung cấp receiver `Account` cho target position 0.

**Bài 7 — mục tiêu không tham số:** target `()String`, newType `(int,boolean)String`. `reorder` dài bao nhiêu?

**Đáp án:** 0. Mọi input mới bị bỏ; `permuteArguments(target,newType)` là lời gọi đúng.

## Tài liệu nguồn

- [JDK 17 — MethodHandles.permuteArguments](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#permuteArguments(java.lang.invoke.MethodHandle,java.lang.invoke.MethodType,int...)): định nghĩa mapping, ràng buộc kiểu, duplicate/drop, ngoại lệ và quy tắc fixed arity.
- [JDK 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `asType` và các cơ chế thích nghi.
- [JDK 17 — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): cấu trúc tham số/giá trị trả về và cách xây `methodType`.
- [JDK 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `dropArguments`, `insertArguments`, `filterArguments`, `filterReturnValue` và các combinator liên quan.

**Ghi nhớ:** `permuteArguments(target, newType, reorder)` định nghĩa cho **mỗi vị trí target** một chỉ số đầu vào của **handle mới**. Chỉ số có thể **đổi thứ tự**, **xuất hiện nhiều lần**, hoặc **không xuất hiện**. Mọi cạnh ánh xạ phải có **kiểu đúng bằng nhau**, độ dài `reorder` bằng số tham số target và kiểu trả về không đổi. Đó là chìa khóa để kết hợp handle chính xác mà không viết wrapper thủ công.
