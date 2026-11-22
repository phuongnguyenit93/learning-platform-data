# 7.8 `asSpreader`, `asCollector`, `asVarargsCollector` và `asFixedArity`

## 1. Mục tiêu bài học

`java.lang.invoke.MethodHandle` là tham chiếu có kiểu đến một phép gọi có thể thực thi. Khác với lời gọi method thông thường, `MethodHandle` có thể được **biến đổi thành adapter**: adapter tiếp nhận danh sách đối số theo một hình dạng mới, sắp xếp/chuyển đổi chúng rồi gọi handle đích. Bốn API trong bài tập trung vào ranh giới giữa **một mảng** và **nhiều tham số vị trí**:

- `asSpreader`: nhận **một array** và trải các phần tử của nó thành **N đối số riêng** trước khi gọi target.
- `asCollector`: nhận **N đối số riêng**, gom chúng thành **một array** để truyền vào target.
- `asVarargsCollector`: tạo adapter **variable arity**; khi gọi bằng `invoke`, số lượng đối số ở cuối có thể thay đổi và được gom thành array.
- `asFixedArity`: tắt chế độ variable arity của handle; giữ kiểu và yêu cầu **đúng hình dạng đối số cố định**.

Sau bài này, bạn có thể đọc `MethodType` trước/sau biến đổi, chọn adapter theo hướng dữ liệu, gọi chính xác bằng `invokeExact`/`invoke`, nhận diện lỗi độ dài/kiểu, và phân biệt **Java varargs** với **variable-arity method handle**.

> Tư duy xuyên suốt: **adapter đổi giao diện gọi của handle, không sửa method gốc**. Luôn kiểm tra `handle.type()` và `handle.isVarargsCollector()` để biết chính xác call site có thể cung cấp đối số theo cách nào.

## 2. Nền tảng: `MethodType`, `invokeExact`, `invoke`

Giả sử ta có method Java:

```java
static String pair(String label, String left, String right) {
    return label + ":" + left + "|" + right;
}
```

`MethodHandles.lookup().findStatic(...)` có thể tạo handle kiểu:

```text
(String,String,String)String
     3 tham số   trả String
```

`MethodHandle.type()` trả về một `MethodType` mô tả **kiểu tham số và kiểu trả về chính xác của handle**, không nhất thiết là kiểu ban đầu của method nguồn sau khi đã qua adapter.

Hai cách gọi thường gặp:

| Lời gọi | Quy tắc |
| --- | --- |
| `invokeExact(...)` | Chữ ký tĩnh tại call site, gồm **kiểu trả về**, phải trùng chính xác `MethodType` của handle |
| `invoke(...)` | Có thể chuyển đổi kiểu phù hợp theo cơ chế gần với `asType`; handle variable arity còn có quy tắc gom các đối số cuối |
| `invokeWithArguments(...)` | Nhận số lượng động đối số qua API dựa trên `Object`/`List`; tiện khi đã có dữ liệu động nhưng không giữ tính chặt chẽ của `invokeExact` |

Do `invokeExact` và `invoke` là **signature-polymorphic**, kiểu biểu thức của từng đối số và cả kiểu mà kết quả được sử dụng/cast trong Java có ảnh hưởng tới descriptor được kiểm tra. Ví dụ `(String) mh.invokeExact(...)` yêu cầu handle trả `String`; nếu muốn nhận `Object` thì phải có adapter/kiểu tương ứng.

Một lỗi rất thường gặp: một handle thật ra có kiểu `(String,String[])String`, nhưng viết `mh.invokeExact("P", "a", "b")`. Dù nó có cờ variable arity, `invokeExact` **không tự đóng gói hai String thành array**; sẽ phát sinh `WrongMethodTypeException`.

Các ví dụ ở dưới dùng Java 17+ và in kiểu handle qua `type()` để quan sát thay đổi này.

## 3. So sánh bốn adapter theo hình dạng dữ liệu

| API | Yêu cầu với handle ban đầu | Hình dạng call site sau biến đổi | Chế độ arity |
| --- | --- | --- | --- |
| `asSpreader(A[].class, n)` | Có ít nhất `n` tham số cuối có thể nhận phần tử từ mảng | Thay **n tham số cuối** bằng **một array** | Fixed |
| `asSpreader(pos, A[].class, n)` | Có `n` tham số bắt đầu tại `pos` | Thay nhóm tham số đó bằng một array tại `pos` | Fixed |
| `asCollector(A[].class, n)` | Tham số cuối là array (hoặc kiểu nhận được array yêu cầu) | Thay **một array cuối** bằng **n tham số phần tử** | Fixed |
| `asCollector(pos, A[].class, n)` | Tham số tại `pos` nhận được array được tạo | Thay array tại `pos` bằng `n` tham số phần tử | Fixed |
| `asVarargsCollector(A[].class)` | Tham số cuối nhận được array kiểu `A[]` | `type()` vẫn có **một array cuối**, nhưng `invoke` có thể cung cấp nhiều phần tử cuối | Variable |
| `asFixedArity()` | Bất kỳ handle; hữu ích nhất khi đang variable | `type()` không đổi; array cuối phải được cung cấp theo dạng cố định | Fixed |

Trong bảng, `A[].class` là cách nói minh họa về một **array class**, chẳng hạn `String[].class` hoặc `int[].class`. Tham số `arrayType` của API là đối tượng `Class<?>` biểu diễn kiểu mảng, **không phải một mảng giá trị thực tế**.

**Khác biệt quyết định:** `asCollector` chốt sẵn **n** vào `MethodType` mới; `asVarargsCollector` để ngỏ số phần tử cuối tại mỗi lời gọi `invoke` phù hợp. Hai API này không tương đương dù cùng có hành vi tạo mảng.

## 4. `asSpreader`: một array trở thành nhiều tham số

### 4.1. Trải các tham số cuối

Bắt đầu từ:

```text
target:       pair(String label, String left, String right)
type:         (String,String,String)String

asSpreader(String[].class, 2)

adapter:      (String,String[])String
call:         adapter("P", {"A","B"})
target nhận:  pair("P", "A", "B")
kết quả:      P:A|B
```

`asSpreader(String[].class, 2)` thay **hai tham số cuối** của target bằng **một `String[]`**. Mảng truyền vào phải có đúng **2 phần tử**; adapter đọc chúng theo thứ tự và đưa vào `left`, `right`.

Ví dụ lời gọi Java độc lập trong bối cảnh đã tạo `spreadTail`:

```java
String result = (String) spreadTail.invokeExact(
        "P", new String[]{"A", "B"});
// result: "P:A|B"
```

**Không nhầm hướng:** target cần ba `String`, adapter mới nhận hai tham số gồm một `String` và một `String[]`. `asSpreader` không phải “nối các mảng thành một mảng”.

### 4.2. Trải array ở vị trí bất kỳ

Java 9+ có overload:

```java
asSpreader(int spreadArgPos, Class<?> arrayType, int arrayLength)
```

`spreadArgPos` là chỉ số **zero-based** tính trên danh sách tham số của target. Với `pair(String,String,String)`:

```text
pair:             (String,String,String)String
asSpreader(0, String[].class, 2)
adapter:          (String[],String)String

adapter({"P","A"}, "B") -> pair("P","A","B")
```

Điểm này hữu ích khi các dữ liệu đóng gói trong array nằm **giữa hoặc đầu** danh sách đối số, không bắt buộc ở cuối.

### 4.3. Quy tắc về độ dài, null và kiểu mảng

- `arrayLength` là **số phần tử cần trải**, không phải độ dài tối đa tùy ý. Với `arrayLength=2`, mảng độ dài 1 hoặc 3 không khớp và lời gọi có thể ném `IllegalArgumentException` khi kiểm tra độ dài.
- Nếu `arrayLength > 0`, array `null` không thể cung cấp phần tử; việc gọi phát sinh lỗi như `NullPointerException`. Đừng dùng `null` để biểu diễn danh sách trống cho trường hợp này.
- Nếu `arrayLength=0`, adapter vẫn nhận thêm **một tham số array**, nhưng không lấy phần tử nào; null có thể hợp lệ cho mảng độ dài 0 theo hợp đồng này. Đây là góc cạnh dễ bỏ sót khi tự sinh `MethodType`.
- `arrayType` phải là kiểu mảng thực sự. Tham số `n` âm, `pos` âm hoặc vượt số lượng tham số, hay một tổ hợp kiểu không thể thích nghi sẽ bị từ chối khi tạo adapter.
- Nếu phần tử của array cần chuyển kiểu để phù hợp với các tham số target, các quy tắc chuyển kiểu của Method Handle được áp dụng; ví dụ unboxing/cast có thể thành công hoặc ném lỗi ở runtime.
- Array có thể là **primitive array**: từ `(int,int,int)int`, `asSpreader(int[].class,3)` tạo `(int[])int`, không phải `(Integer[])int`.

### 4.4. Khi nào nên dùng?

Khi dữ liệu đến từ một nguồn vốn được đóng thành mảng, chẳng hạn một API parse ra `String[]`, còn target handler cần các tham số riêng biệt **đã biết số lượng và kiểu**. Nó đặc biệt hữu ích trong pipeline xử lý Method Handle, trong đó ta có thể thích nghi signature mà không viết một wrapper Java thủ công cho mỗi hàm.

## 5. `asCollector`: nhiều tham số được gom thành một array

### 5.1. Gom các tham số cuối

Giả sử target là:

```java
static String pack(String prefix, String[] items) {
    return prefix + Arrays.toString(items);
}
```

Target có `MethodType`:

```text
(String,String[])String
```

Adapter:

```java
MethodHandle collected = packHandle.asCollector(String[].class, 3);
```

có kiểu:

```text
(String,String,String,String)String
```

Nó yêu cầu **ba `String` cuối**. Khi gọi `collected("C","a","b","c")`, adapter tạo một `String[]` chứa `{"a","b","c"}` rồi chuyển cho `pack("C", array)`. Kết quả là `C[a, b, c]`.

Điều khác `asSpreader`: `asCollector` chỉ áp dụng cho target **đã có array parameter**, còn adapter mới **bộc lộ N tham số phần tử riêng** ra bên ngoài.

Nếu `arrayLength=0`, tham số array được thay bằng **0 tham số**. Adapter tương ứng chỉ yêu cầu phần tiền tố không đổi; array trống được cung cấp cho target (có thể được triển khai tối ưu hóa để tái sử dụng mảng).

### 5.2. Gom ở vị trí bất kỳ

Overload từ Java 9:

```java
asCollector(int collectArgPos, Class<?> arrayType, int arrayLength)
```

Tham số tại `collectArgPos` của target được thay bằng `arrayLength` tham số mang kiểu phần tử. Chẳng hạn:

```text
target:      surround(String[] parts, String suffix)
type:        (String[],String)String
asCollector(0, String[].class, 2)
adapter:     (String,String,String)String

adapter("L", "R", "done")
       -> surround(new String[]{"L","R"}, "done")
       -> [L, R]/done
```

Vị trí `0` là array đầu tiên; `suffix` ở cuối vẫn là tham số riêng, không bị gom. Điều này có thể tránh phải hoán đổi thứ tự tham số trong một pipeline.

### 5.3. Ràng buộc về kiểu và số lượng

- `arrayType` phải là array class, và array đó phải **gán được vào tham số array của target** tại vị trí gom. Ví dụ target nhận `Object[]` thì có thể gom vào `String[]` do `String[]` là subtype của `Object[]`.
- `arrayLength` là số tham số phần tử **cố định** của adapter; số âm và kiểu/số lượng tham số vượt giới hạn Method Handle là không hợp lệ.
- Nếu target nhận `int[]`, dùng `int[].class` để các tham số mới là `int`, không mặc định chuyển thành `Integer`.
- `asCollector` trả về handle **fixed arity**, kể cả khi handle đầu vào có cờ variable arity. Muốn chấp nhận nhiều số lượng tham số cuối ở các lần gọi khác nhau, cân nhắc `asVarargsCollector`.
- Mỗi method handle có thể có giới hạn số tham số/slot JVM; gom một mảng quá lớn thành quá nhiều tham số sẽ không hợp lệ dù bản thân mảng Java có thể dài hơn nhiều.

### 5.4. Hai chiều không phải luôn là phép nghịch đảo tuyệt đối

Một chuỗi `target.asSpreader(T[].class,n).asCollector(T[].class,n)` thường phục hồi **hình dạng type** ban đầu nếu mọi điều kiện kiểu tương thích, như ví dụ `pair`. Tuy vậy có thể phát sinh conversion, cast hoặc kiểm tra độ dài/mảng, nên **không mặc định** hai adapter tạo ra chính đối tượng handle ban đầu hay tương đương trong mọi tình huống. Kiểm tra `type()` và giá trị thực thi.

## 6. `asVarargsCollector`: số phần tử cuối thay đổi theo `invoke`

### 6.1. Type vẫn có array cuối

Tiếp tục với target `pack(String, String[])`:

```java
MethodHandle variable = packHandle.asVarargsCollector(String[].class);
```

Lúc này:

```text
variable.type()              -> (String,String[])String
variable.isVarargsCollector() -> true
```

`asVarargsCollector` **không** làm cho `type()` có số tham số thay đổi. Nó đặt handle vào **chế độ đặc biệt cho lời gọi `invoke` và `asType`**. Cả hai lần gọi sau đều có thể thành công:

```java
String zero = (String) variable.invoke("V");
String many = (String) variable.invoke("V", "a", "b", "c");
// zero -> "V[]"
// many -> "V[a, b, c]"
```

Khi caller không cung cấp sẵn array cuối theo kiểu tương thích, adapter tạo một `String[]` có số phần tử tương ứng với số đối số còn lại rồi gọi target `pack`.

Khi caller **đưa đúng một array cuối phù hợp**, nó có thể đi qua như array sẵn có. Chẳng hạn:

```java
String direct = (String) variable.invokeExact(
        "V", new String[]{"x", "y"});
// direct -> "V[x, y]"
```

`invokeExact` trong ví dụ trên thành công bởi vì call site **khớp chính xác** `(String,String[])String`, hoàn toàn không cần gom varargs.

### 6.2. `invokeExact` không hỗ trợ đổi số đối số

Điểm thường dẫn tới `WrongMethodTypeException`:

```java
// Trích đoạn phản ví dụ; variable có type (String,String[])String.
String wrong = (String) variable.invokeExact("V", "a", "b");
// Không hợp lệ: call site (String,String,String)String.
```

Dù `isVarargsCollector() == true`, lời gọi `invokeExact` không dùng quy tắc linh hoạt của `invoke`. Nó yêu cầu call site descriptor giống `type()`. Nếu cần gọi ba `String` bằng `invokeExact`, hãy **tạo `asCollector(String[].class,2)` trước** để handle có type `(String,String,String)String`, rồi gọi exact theo type đó.

### 6.3. Điều kiện chọn `arrayType`

Handle ban đầu phải có một **tham số array cuối hoặc một kiểu tham số cuối chấp nhận array được chỉ định**. `arrayType` phải thực sự là một array class. Ví dụ target cuối là `Object[]` có thể nhận `String[]` và được biến đổi thành varargs collector có tham số cuối `String[]`; nhưng nếu target cuối là `int` hoặc `String` không nhận mảng, không thể dùng `asVarargsCollector(String[].class)` hợp lệ.

Nếu handle đã là varargs collector với kiểu array cuối tương đương, gọi lại có thể trả chính handle đó.

### 6.4. Varargs Java source khác cờ varargs của MethodHandle

Một method được khai báo bằng `String... args` trong Java có bytecode parameter là `String[]`, kèm cờ `ACC_VARARGS`. Khi `Lookup.findStatic` / `findVirtual` tìm ra một Java method varargs, handle thường **đã có `isVarargsCollector() == true`** mà không cần gọi `asVarargsCollector` thủ công.

Ngược lại, target `pack(String, String[])` của ví dụ khai báo bằng **mảng thường**, không viết `String...`. Handle tìm được ban đầu là fixed, nhưng ta **chủ động** gọi `asVarargsCollector(String[].class)` để cho phép variable-arity invocation. Điều này **không biến source method thành varargs**, chỉ điều chỉnh hành vi handle.

### 6.5. Tương tác với `asType` và lời gọi có sẵn array

Một varargs collector có thể nhận các yêu cầu `asType` với arity khác hoặc kiểu tham số cuối khác rồi gom tham số tương ứng. Khi caller có cùng arity và kiểu array cuối phù hợp, nó có thể dùng nhánh fixed-arity conversion thay vì đóng gói từng phần tử. Vì vậy, để tránh nhập nhằng khi muốn **chắc chắn truyền nguyên một array**, dùng `invokeExact` với array type và return type **đúng** hoặc chuyển sang `asFixedArity()`.

Với array kiểu `Object[]` và API nhận `Object...`, việc cast mảng thành `Object` trong source Java có thể làm thay đổi cách nhận diện một đối số cuối ở call site. Hãy nhìn **kiểu biểu thức tĩnh**, không chỉ nhìn giá trị runtime.

## 7. `asFixedArity`: tắt cơ chế gom tự động

Gọi:

```java
MethodHandle fixed = variable.asFixedArity();
```

Với `variable` ở trên:

```text
variable.type()       = (String,String[])String
fixed.type()          = (String,String[])String

variable.isVarargsCollector() = true
fixed.isVarargsCollector()    = false
```

Hai handle có cùng `MethodType` nhưng **khác hành vi** khi caller dùng `invoke` với các arity khác nhau.

Hợp lệ:

```java
String value = (String) fixed.invokeExact(
        "F", new String[]{"x", "y"});
// "F[x, y]"
```

Không hợp lệ:

```java
// Trích đoạn phản ví dụ; fixed.type() là (String,String[])String.
String wrong = (String) fixed.invoke("F", "a", "b");
// WrongMethodTypeException: không có cơ chế gom String,String thành String[].
```

`asFixedArity()` **không** biến `(String,String[])String` thành `(String,String)String`, không tự mở array và không làm cho `invokeExact` cho phép kiểu sai. Nó chỉ tắt khả năng variable arity. Nếu handle vốn đã là fixed, `asFixedArity()` có thể trả lại chính handle hiện tại.

Đây là lựa chọn phù hợp khi một framework muốn **array cuối luôn được coi là đúng một đối số**, tránh việc một lời gọi `invoke` vô tình đóng gói thêm các giá trị thành mảng.

> Nếu cần API **luôn nhận đúng ba chuỗi** rồi mới tạo mảng, dùng `asCollector(String[].class, 3)`. Nếu API muốn **mỗi lần nhận số chuỗi khác nhau** bằng `invoke`, dùng `asVarargsCollector(String[].class)`. Nếu API nhận **một mảng đã chuẩn bị**, dùng fixed-arity handle.

## 8. Ví dụ Java 17+ hoàn chỉnh và chạy được

Ví dụ này minh họa cả **hai overload có vị trí index**, thao tác trên primitive array, lỗi độ dài, `invokeExact` so với `invoke` và kiểm tra trạng thái varargs.

Lưu toàn bộ nội dung thành **`HandleArrayAdaptersDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.Arrays;

public class HandleArrayAdaptersDemo {
    public static String pair(String label, String left, String right) {
        return label + ":" + left + "|" + right;
    }

    public static String pack(String prefix, String[] items) {
        return prefix + Arrays.toString(items);
    }

    public static String surround(String[] parts, String suffix) {
        return Arrays.toString(parts) + "/" + suffix;
    }

    public static int sum3(int a, int b, int c) {
        return a + b + c;
    }

    public static String natural(String prefix, String... parts) {
        return pack(prefix, parts);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle pair = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "pair",
                MethodType.methodType(String.class,
                        String.class, String.class, String.class));

        // Array -> 2 tham số cuối.
        MethodHandle spreadTail = pair.asSpreader(String[].class, 2);
        // Array -> 2 tham số từ vị trí 0.
        MethodHandle spreadHead = pair.asSpreader(0, String[].class, 2);

        System.out.println("pair type=" + pair.type());
        System.out.println("spread tail type=" + spreadTail.type());
        System.out.println("spread tail=" + (String) spreadTail.invokeExact(
                "P", new String[]{"A", "B"}));
        System.out.println("spread head type=" + spreadHead.type());
        System.out.println("spread head=" + (String) spreadHead.invokeExact(
                new String[]{"P", "A"}, "B"));

        MethodHandle pack = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "pack",
                MethodType.methodType(
                        String.class, String.class, String[].class));

        // 3 tham số String cuối -> 1 String[].
        MethodHandle collected = pack.asCollector(String[].class, 3);
        System.out.println("pack type=" + pack.type());
        System.out.println("collect type=" + collected.type());
        System.out.println("collect=" + (String) collected.invokeExact(
                "C", "a", "b", "c"));

        MethodHandle surround = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "surround",
                MethodType.methodType(
                        String.class, String[].class, String.class));
        MethodHandle collectAtZero =
                surround.asCollector(0, String[].class, 2);
        System.out.println("collect at zero type=" + collectAtZero.type());
        System.out.println("collect at zero=" + (String)
                collectAtZero.invokeExact("L", "R", "done"));

        // Cho phép nhiều arity khi gọi bằng invoke.
        MethodHandle variable = pack.asVarargsCollector(String[].class);
        MethodHandle fixed = variable.asFixedArity();

        System.out.println("variable type=" + variable.type());
        System.out.println("variable flag=" + variable.isVarargsCollector());
        System.out.println("fixed type=" + fixed.type());
        System.out.println("fixed flag=" + fixed.isVarargsCollector());

        System.out.println("variable zero=" + (String)
                variable.invoke("V"));
        System.out.println("variable many=" + (String)
                variable.invoke("V", "a", "b", "c"));
        System.out.println("variable array=" + (String)
                variable.invokeExact("V", new String[]{"x", "y"}));
        System.out.println("fixed array=" + (String)
                fixed.invokeExact("F", new String[]{"x", "y"}));

        // Fixed arity không nhận 2 String thay cho String[].
        try {
            String ignored = (String) fixed.invoke("F", "a", "b");
            System.out.println("unexpected=" + ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("fixed positional=WrongMethodTypeException");
        }

        // Variable arity không làm invokeExact trở nên linh hoạt.
        try {
            String ignored = (String) variable.invokeExact("V", "a", "b");
            System.out.println("unexpected=" + ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("exact positional=WrongMethodTypeException");
        }

        try {
            String ignored = (String) spreadTail.invokeExact(
                    "P", new String[]{"only-one"});
            System.out.println("unexpected=" + ignored);
        } catch (IllegalArgumentException ex) {
            System.out.println("spread bad length=IllegalArgumentException");
        }

        // N=0: array cuối không đóng góp phần tử.
        MethodHandle noArray = pair.asSpreader(String[].class, 0);
        System.out.println("spread zero type=" + noArray.type());
        System.out.println("spread zero=" + (String)
                noArray.invokeExact("P", "A", "B", (String[]) null));

        // Primitive array giữ nguyên kiểu thành phần int.
        MethodHandle sum3 = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "sum3",
                MethodType.methodType(
                        int.class, int.class, int.class, int.class));
        MethodHandle sumArray = sum3.asSpreader(int[].class, 3);
        System.out.println("sum array type=" + sumArray.type());
        System.out.println("sum array=" + (int)
                sumArray.invokeExact(new int[]{2, 3, 4}));

        // findStatic trên Java method varargs tạo variable-arity MH.
        MethodHandle javaVarargs = lookup.findStatic(
                HandleArrayAdaptersDemo.class, "natural",
                MethodType.methodType(
                        String.class, String.class, String[].class));
        System.out.println("source varargs flag="
                + javaVarargs.isVarargsCollector());
        System.out.println("collected flag=" + collected.isVarargsCollector());
        System.out.println("inverse type="
                + spreadTail.asCollector(String[].class, 2).type());
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac HandleArrayAdaptersDemo.java
java HandleArrayAdaptersDemo
```

**Stdout chính xác của ví dụ (đã kiểm tra trên JDK):**

```text
pair type=(String,String,String)String
spread tail type=(String,String[])String
spread tail=P:A|B
spread head type=(String[],String)String
spread head=P:A|B
pack type=(String,String[])String
collect type=(String,String,String,String)String
collect=C[a, b, c]
collect at zero type=(String,String,String)String
collect at zero=[L, R]/done
variable type=(String,String[])String
variable flag=true
fixed type=(String,String[])String
fixed flag=false
variable zero=V[]
variable many=V[a, b, c]
variable array=V[x, y]
fixed array=F[x, y]
fixed positional=WrongMethodTypeException
exact positional=WrongMethodTypeException
spread bad length=IllegalArgumentException
spread zero type=(String,String,String,String[])String
spread zero=P:A|B
sum array type=(int[])int
sum array=9
source varargs flag=true
collected flag=false
inverse type=(String,String,String)String
```

**Cách diễn giải từng nhóm kết quả:**

1. `pair` có ba tham số `String`; `spreadTail` thay hai tham số cuối bằng `String[]`, còn `spreadHead` thay hai tham số từ chỉ số 0. Hai adapter đều gọi cùng `pair` nhưng giao diện nhận đầu vào khác.
2. `pack` có một tham số array cuối; `collected` thay array đó bằng ba `String`, nên type có tổng cộng **bốn** tham số.
3. `collectAtZero` đổi array ở đầu và giữ `suffix` cuối không thay đổi. Đây là lý do API indexed hữu ích.
4. `variable` và `fixed` cùng `type()` nhưng chỉ `variable` hỗ trợ `invoke` với 0 hoặc nhiều phần tử cuối. `invokeExact` phải dùng array có kiểu chính xác.
5. Lỗi `WrongMethodTypeException` trong ví dụ là các tình huống **cố ý** để chứng minh sự khác nhau giữa fixed, variable và exact. Lỗi độ dài từ spreader là `IllegalArgumentException`.
6. `arrayLength=0` thêm một array parameter nhưng không đọc phần tử, ngay cả khi giá trị array là `null`.
7. Với `int[]`, adapter có type `(int[])int`; không đổi thành `Integer[]`.
8. `natural(String,String...)` được khai báo varargs trong mã nguồn nên lookup có `isVarargsCollector() == true`. `asCollector` tạo fixed adapter; do đó `collected flag=false`.

## 9. Sai lầm phổ biến và cách sửa

### 9.1. Dùng sai hướng của adapter

**Sai nhu cầu:** dữ liệu đã là `String[]`, target cần `String,String`, nhưng dùng `asCollector`.  
**Sửa:** `asSpreader(String[].class,2)` tạo handle chấp nhận mảng. `asCollector` đi hướng ngược: target cần một array, còn caller muốn truyền từng phần tử riêng.

Đọc theo sơ đồ:

```text
Spreader:  caller [array]        -> adapter -> target(arg1, arg2, ...)
Collector: caller (arg1,arg2,...) -> adapter -> target([array])
Varargs:   caller (0..N tail args) -> invoke/adapter -> target([array])
Fixed:     caller ([array])      -> target([array])
```

### 9.2. Cho rằng `asVarargsCollector` tương đương `asCollector(n)`

`asCollector(String[].class,3)` sinh ra **một `MethodType` fixed nhận chính xác ba phần tử** tại vùng gom. `asVarargsCollector(String[].class)` giữ dạng array cuối trong `type()` nhưng cho phép những lời gọi `invoke` với số phần tử cuối thay đổi. Nếu ứng dụng có schema cố định, `asCollector(n)` cho phép kiểm tra chữ ký chặt chẽ hơn.

### 9.3. Dùng `invokeExact` như một lời gọi varargs Java

Lời gọi `variable.invokeExact("P","a","b")` vẫn bị kiểm tra theo `type()`. Hãy truyền một `String[]` đúng kiểu, hoặc tạo fixed collector với số tham số thích hợp. Cờ `isVarargsCollector` chỉ kích hoạt hành vi liên quan tới **plain `invoke`/`asType`**.

### 9.4. Bỏ qua kiểu trả về ở call site

Với target trả về `int`, đoạn sau có thể thất bại vì caller yêu cầu `Object` thay vì `int`:

```java
// Trích đoạn minh họa, không phải chương trình độc lập.
Object result = sumArray.invokeExact(new int[]{2, 3, 4});
```

Đúng khi cần exact primitive:

```java
int value = (int) sumArray.invokeExact(new int[]{2, 3, 4});
```

Muốn thay đổi kiểu return của handle một cách chủ đích, dùng `asType(...)` phù hợp hoặc gọi `invoke` khi chuyển đổi được chấp nhận. Không đoán `invokeExact` tự boxing.

### 9.5. Đánh đồng `String[]` với `Object[]` hoặc `int[]` với `Integer[]`

`String[]` là subtype của `Object[]`, nhưng `Object[]` không tự động là `String[]`. `int[]` và `Integer[]` là **hai kiểu mảng khác nhau**; Method Handle không có quy tắc tự biến mảng primitive thành mảng wrapper chỉ vì có boxing trên từng phần tử. Cần thiết kế `arrayType` chính xác theo target.

### 9.6. Bỏ qua độ dài array khi dùng spreader

`asSpreader(String[].class,2)` cần mảng **đúng hai phần tử**. Array quá ngắn/quá dài là lỗi runtime; nếu truyền data từ JSON hay dữ liệu mạng, kiểm tra kích thước trước khi gọi. `asCollector(n)` có ràng buộc số phần tử ở ngay giao diện handle, nhưng vẫn có thể gặp lỗi chuyển kiểu hoặc null tại target.

### 9.7. Nhầm `asFixedArity` là “gỡ tất cả adapter”

`variable.asFixedArity()` chỉ chuyển sang chế độ fixed, **không trả về method gốc trước mọi biến đổi**, không đảo thứ tự tham số, không “hủy” `asCollector` hay `asSpreader`. Adapter nhận được vẫn gọi target hiện có với hành vi tương ứng.

### 9.8. Cố dùng adapter để vượt quyền truy cập

`asSpreader`, `asCollector` và các adapter khác không thay đổi quyền Java/module. `MethodHandles.Lookup.findStatic`/`findVirtual`, `privateLookupIn` và module access control quyết định có tạo được target handle hay không. Nếu `Lookup` không được phép tìm target, việc thêm adapter sau đó không giải quyết rào cản access.

## 10. Quy tắc chọn API trong thực tế

| Tình huống | Nên bắt đầu từ | Lý do |
| --- | --- | --- |
| Từ `String[] args` muốn gọi handler nhận `String, String` | `asSpreader(String[].class,2)` | Một array được trải thành hai tham số |
| Handler nhận `String[]`, caller muốn chữ ký gồm đúng 3 `String` | `asCollector(String[].class,3)` | Gom 3 tham số thành array với arity cố định |
| Array nằm ở tham số giữa/đầu, các tham số khác giữ nguyên | `asCollector(pos,...)` hoặc `asSpreader(pos,...)` | Điều khiển vị trí không nhất thiết nằm cuối |
| Wrapper nhận số chuỗi cuối không cố định từ nhiều call site `invoke` | `asVarargsCollector(String[].class)` | Chọn độ dài mảng khi gọi |
| Cần bảo đảm array cuối được truyền như một đối số duy nhất | `asFixedArity()` kết hợp `invokeExact`/signature đúng | Không có gom varargs ngầm |
| API cần array primitive `int[]` | Chỉ định `int[].class` và call site kiểu `int[]` | Tránh nhầm primitive array với wrapper/reference array |
| Muốn giữ varargs khi thay đổi `MethodType` bằng adapter khác | Kiểm tra `isVarargsCollector()`, cân nhắc `withVarargs(boolean)` | Nhiều phép biến đổi khác trả handle fixed |

### 10.1. Quy trình thiết kế adapter cho một dispatcher

Giả sử một framework nhận dữ liệu ở dạng array hoặc danh sách đối số. Trước khi viết combinator, làm lần lượt:

1. **Đọc type của target:** lấy `target.type()`; ghi đủ return type và mỗi parameter type.
2. **Xác định type mong muốn ở caller:** array đã có, số phần tử cố định, hay số phần tử thay đổi?
3. **Chọn hướng chuyển:** caller array → `asSpreader`; caller positional cố định → `asCollector(n)`; caller positional thay đổi qua `invoke` → `asVarargsCollector`.
4. **Xác định array class:** `String[].class`, `Object[].class`, `int[].class`... theo kiểu thật của data và target; không chỉ nhìn `Object`.
5. **Nếu group không nằm cuối:** dùng overload với `spreadArgPos` / `collectArgPos`, đánh số từ 0.
6. **Kiểm tra adapter mới:** gọi `type()`, `isVarargsCollector()` và thử một test với dữ liệu đúng/không đúng.
7. **Quyết định API gọi:** `invokeExact` cho signature đã biết chính xác; `invoke` nếu chủ động muốn chuyển kiểu/variable arity; `invokeWithArguments` khi đã có đối số động dạng danh sách, chú ý đặc tính Object conversion và Java varargs tại call site.
8. **Kiểm tra lỗi ở đúng tầng:** lỗi tạo adapter (`IllegalArgumentException`/`WrongMethodTypeException`) khác với lỗi gọi (`WrongMethodTypeException`, sai độ dài, cast/unbox/null, exception từ target).

Với một hệ thống nhận dữ liệu từ bên ngoài, cần kiểm tra số lượng, kiểu và null trước khi gọi. Adapter giúp ghép các thành phần runtime nhưng **không thay thế validation** và không tự tạo bộ chuyển đổi dữ liệu tùy ý.

## 11. Bài tập tự kiểm tra

**Câu 1.** Target có type `(int,int,int)int`. Muốn truyền một `int[]` có ba phần tử bằng `invokeExact`, dùng gì?  
**Đáp án:** `asSpreader(int[].class,3)` tạo handle kiểu `(int[])int`. Call site: `(int) handle.invokeExact(new int[]{1,2,3})`.

**Câu 2.** Target nhận `(String,String[])String`; adapter `asCollector(String[].class,2)` có type gì?  
**Đáp án:** `(String,String,String)String`. Một array cuối bị thay bằng hai `String` vị trí.

**Câu 3.** `variable.isVarargsCollector()==true` và `variable.type()==(String,String[])String`. `(String) variable.invokeExact("P","x")` có tự gom một `String` không?  
**Đáp án:** Không. `invokeExact` yêu cầu đúng `String[]` ở tham số thứ hai. `invoke` có thể dùng cơ chế variable arity theo call site phù hợp.

**Câu 4.** `fixed=variable.asFixedArity()` có đổi `fixed.type()` thành `(String,String)String` không?  
**Đáp án:** Không. Type không đổi; cờ `isVarargsCollector()` chuyển sang `false`.

**Câu 5.** Từ `(String[],String)String` cần caller truyền `("a","b","tail")`. Nên chọn gì?  
**Đáp án:** `asCollector(0,String[].class,2)`; biến hai `String` đầu thành mảng và giữ tham số `tail`.

**Câu 6.** `asSpreader(String[].class,2)` nhận mảng dài 1. Lỗi thuộc tầng nào?  
**Đáp án:** Lỗi lúc **gọi adapter** do mảng không có đúng số phần tử cần trải; trong ví dụ Java có `IllegalArgumentException`.

**Câu 7.** Sau `lookup.findStatic` tới một method source khai báo `String...`, `isVarargsCollector()` có thể đúng mà không gọi `asVarargsCollector` không?  
**Đáp án:** Có. Lookup một Java varargs method tạo handle có chế độ variable arity theo hợp đồng API.

**Câu 8.** `asSpreader(int[].class,3)` có nhận thay thế một `Integer[]` qua `invokeExact` không?  
**Đáp án:** Không. `int[]` và `Integer[]` là hai array class khác nhau; `invokeExact` cần kiểu đúng.

**Câu 9.** Muốn trong một framework mọi lời gọi chỉ chấp nhận array cuối, có nên chỉ giữ `variable` rồi gọi `invoke` tùy ý không?  
**Đáp án:** Nên chuyển về fixed bằng `asFixedArity()` và đưa call site theo chữ ký mong muốn; dùng `invokeExact` khi có type chính xác.

## 12. Ghi nhớ và tài liệu chính thức

- **Spreader**: `N positional parameters ← 1 array`. Array xuất hiện ở call site.
- **Collector**: `1 array parameter ← N positional arguments`. Positional arguments xuất hiện ở call site, `N` cố định.
- **Varargs collector**: `type()` vẫn chứa array cuối, nhưng `invoke` cho phép nhiều arity phù hợp; `invokeExact` không tự gom.
- **Fixed arity**: giữ nguyên `type()`, tắt chế độ nhiều arity; đưa **array cuối** đúng kiểu vào call site.
- **Kiểm chứng bằng `type()` và `isVarargsCollector()`** trước khi gọi, nhất là khi các adapter được xâu chuỗi.

Tài liệu tham khảo:

- [Oracle Java SE 17 — `java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): đặc tả `asSpreader`, `asCollector`, `asVarargsCollector`, `asFixedArity`, `invoke`, `invokeExact` và `isVarargsCollector`.
- [Oracle Java SE 17 — `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): mô hình kiểu method handle, danh sách tham số và return type.
- [Oracle Java SE 17 — `java.lang.invoke.MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): tạo target handle bằng `findStatic`/`findVirtual` và điều kiện quyền truy cập.
