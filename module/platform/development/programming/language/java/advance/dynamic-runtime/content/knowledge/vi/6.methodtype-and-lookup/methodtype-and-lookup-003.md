# 6.3. Tạo, so sánh và biến đổi MethodType; phân biệt void với Void

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả chính xác ý nghĩa của `java.lang.invoke.MethodType` trong hệ thống `MethodHandle`: một kiểu trả về và dãy kiểu tham số theo **thứ tự**, không chứa tên phương thức hay phần thân thực thi.
2. Tạo `MethodType` bằng các factory `methodType(...)`, `genericMethodType(...)` và từ JVM method descriptor.
3. Đọc, so sánh và biến đổi kiểu bằng `returnType`, `parameterType`, `parameterCount`, `equals`, `changeParameterType`, `changeReturnType`, `insertParameterTypes`, `appendParameterTypes`, `dropParameterTypes`, `erase`, `generic`, `wrap`, `unwrap`.
4. Phân biệt rõ `void.class` và `Void.class`, đặc biệt khi tạo kiểu trả về, kiểu tham số, chuyển đổi wrapper và liên kết lời gọi.
5. Giải thích vì sao thay đổi một `MethodType` **không** tự đổi chữ ký của phương thức thật hoặc của `MethodHandle` đã có; chỉ liên kết/adapt handle khi đúng hợp đồng kiểu.

**Ngữ cảnh:** Khi dùng `MethodHandles.Lookup` để tìm method hoặc constructor, Java cần biểu diễn chính xác signature ở runtime. Cùng một tên phương thức có thể có nhiều overload; `MethodType` giúp định danh kiểu tham số và kiểu kết quả. Nó cũng xuất hiện trong hoạt động liên kết call site, bytecode descriptors và các API biến đổi `MethodHandle`.

## 1. MethodType biểu diễn điều gì?

Một `MethodType` có dạng logic:

```text
(P0, P1, ..., Pn)R
```

Trong đó `P0..Pn` là các lớp/kiểu tham số theo thứ tự, `R` là kiểu trả về. Có thể có **0 tham số**. Mọi thành phần được biểu diễn bởi đối tượng `Class<?>`, chẳng hạn `String.class`, `int.class` hoặc `void.class`.

Ví dụ:

```java
MethodType signature = MethodType.methodType(
        String.class, String.class, int.class);
System.out.println(signature);  // (String,int)String
```

Đoạn minh họa cần import `java.lang.invoke.MethodType`. Nó mô tả lời gọi nhận `String`, `int` và trả `String`. Nó **không** chứa tên method, không tham chiếu một class sở hữu, không tự tìm hoặc thực thi method và cũng không chứa exception checked trong `throws`, generic type parameter hay annotation.

Điểm cần phân biệt:

| Đối tượng | Nó giữ thông tin gì? | Dùng làm gì? |
| --- | --- | --- |
| `MethodType` | Kiểu trả về và danh sách kiểu tham số | Mô tả/so sánh/biến đổi chữ ký JVM method handle |
| `MethodHandle` | Một mục tiêu có thể gọi cùng kiểu phương thức của nó | Thực thi lời gọi, sau khi tìm hoặc tạo/adapt handle |
| `MethodHandles.Lookup` | Ngữ cảnh quyền truy cập và API tìm method/field/constructor | `findStatic`, `findVirtual`, `findConstructor`, ... |
| `java.lang.reflect.Method` | Thành viên phản chiếu của một class, tên, modifiers, parameters ... | Truy vấn metadata, `invoke` theo cơ chế reflection |

### 1.1. Phương thức tĩnh, instance và receiver

Với:

```java
class TextTools {
    static String join(String a, String b) { return a + b; }
    String echo(String value) { return value; }
}
```

Đây là minh họa độc lập về **khai báo class**, chưa phải chương trình có `main`. Khi lookup:

- `lookup.findStatic(TextTools.class, "join", MethodType.methodType(String.class, String.class, String.class))`: kiểu tìm kiếm mô tả hai tham số `String` của method tĩnh, và handle nhận hai tham số đó.
- `lookup.findVirtual(TextTools.class, "echo", MethodType.methodType(String.class, String.class))`: kiểu truyền vào lookup mô tả tham số **được khai báo** bởi method instance. Handle kết quả thường có thêm **receiver** `TextTools` ở vị trí tham số đầu của handle, ví dụ `(TextTools,String)String`.

Đừng tự thêm receiver vào `MethodType` truyền cho `findVirtual`; nhưng **phải** tính receiver khi dùng `invokeExact` trên handle trả về. Constructor lookup lại dùng kiểu trả về `void.class` để biểu diễn constructor được tra cứu, còn handle tạo ra trả về instance của class được khởi tạo. Các quan hệ đó là hợp đồng từng API `Lookup`, không phải quy tắc “MethodType luôn thêm receiver”.

## 2. Tạo MethodType bằng factory

`MethodType` là **final, immutable** và được tạo qua factory, không có lời gọi `new MethodType(...)` công khai.

### 2.1. Tạo signature không tham số hoặc có tham số

```java
import java.lang.invoke.MethodType;

MethodType a = MethodType.methodType(void.class);                     // ()void
MethodType b = MethodType.methodType(int.class, long.class);         // (long)int
MethodType c = MethodType.methodType(
        String.class, String.class, int.class);                      // (String,int)String
```

Các overload cho phép đưa tham số qua `Class<?>[]` hoặc `List<Class<?>>`. Thứ tự tham số quan trọng: `(String,int)String` **khác** `(int,String)String`. Đối với một method được khai báo trả `String`, phải truyền `String.class` làm đối số **đầu tiên** của factory, sau đó mới đến các kiểu tham số.

Ví dụ dùng danh sách:

```java
MethodType fromList = MethodType.methodType(
        String.class, java.util.List.of(String.class, int.class));
```

Đoạn trên là minh họa trong ngữ cảnh đã import `MethodType`; nó tạo cùng signature với biến `c` phía trên.

### 2.2. Tạo kiểu tổng quát

```java
MethodType generic = MethodType.genericMethodType(2);
// (Object,Object)Object

MethodType varargsStyle = MethodType.genericMethodType(2, true);
// (Object,Object,Object[])Object
```

Đây là **signature có các thành phần `Object`**, không phải Java generic method kiểu `<T>` và không tự làm được type inference cho method bất kỳ. Biến thể có tham số cuối `Object[]` hữu ích trong một số cơ chế thu thập đối số động. Kiểu này không đồng nghĩa có thể bỏ qua ép kiểu hoặc kiểm tra lúc chạy.

### 2.3. Từ JVM method descriptor

Một method descriptor là biểu diễn mức bytecode, ví dụ:

```text
(Ljava/lang/String;I)Ljava/lang/String;
```

Nó tương ứng `(String,int)String`. Trong descriptor:
- `I` = `int`, `J` = `long`, `Z` = `boolean`, `V` = `void` (chỉ dùng cho kiểu trả về).
- `Ljava/lang/String;` biểu diễn reference tới `java.lang.String`.
- `[I` là `int[]`; `[Ljava/lang/String;` là `String[]`.
- Dấu `(...)` chứa **danh sách tham số**; ký hiệu sau dấu `)` là kiểu trả về.

```java
MethodType fromDescriptor = MethodType.fromMethodDescriptorString(
        "(Ljava/lang/String;I)Ljava/lang/String;",
        MethodType.class.getClassLoader());
String descriptor = fromDescriptor.toMethodDescriptorString();
```

Đây là minh họa dùng `MethodType` sau import. `fromMethodDescriptorString` cần một `ClassLoader` phù hợp để resolve các tên reference; sử dụng class loader sai có thể gây `TypeNotPresentException` hoặc vấn đề tương thích khi nhiều loader định nghĩa cùng tên class. Descriptor là **kiểu JVM**, không phải dạng `toString()` thân thiện với người đọc.

## 3. Đọc signature: parameter và return

Giả sử:

```java
MethodType type = MethodType.methodType(
        String.class, String.class, int.class);
```

Có thể truy vấn:

| API | Giá trị |
| --- | --- |
| `type.returnType()` | `String.class` |
| `type.parameterCount()` | `2` |
| `type.parameterType(0)` | `String.class` |
| `type.parameterType(1)` | `int.class` |
| `type.parameterList()` | Danh sách không sửa được `[String.class, int.class]` |
| `type.parameterArray()` | Một mảng chứa các kiểu tham số; sửa mảng được trả về không sửa `type` |
| `type.toString()` | `(String,int)String` |
| `type.toMethodDescriptorString()` | `(Ljava/lang/String;I)Ljava/lang/String;` |

Chỉ số của `parameterType(index)` bắt đầu từ 0 và nằm trong `[0, parameterCount())`. Vượt phạm vi gây `IndexOutOfBoundsException`.

`lastParameterType()` trả kiểu tham số cuối, nhưng với signature **không có tham số**, nó trả **sentinel `void.class`** (không có nghĩa là signature có một tham số `void`). Điều này thuận tiện cho vài thao tác varargs; khi cần logic chính xác, vẫn nên kiểm tra `parameterCount()`.

## 4. So sánh MethodType và tính bất biến

Hai `MethodType` bằng nhau theo `equals` nếu:

1. **Cùng kiểu trả về**, và
2. **Cùng số lượng, thứ tự và kiểu của mọi tham số**.

```java
MethodType first = MethodType.methodType(
        String.class, String.class, int.class);
MethodType second = MethodType.methodType(
        String.class, new Class<?>[] { String.class, int.class });
MethodType different = MethodType.methodType(
        String.class, int.class, String.class);

System.out.println(first.equals(second));    // true
System.out.println(first.equals(different)); // false
```

Đây là ví dụ minh họa có import `MethodType`. Không dùng `first == second` làm quy tắc so sánh hợp đồng: factory **có thể cache** nhưng không bảo đảm hai lần tạo signature giống nhau luôn trả cùng object. `equals`/`hashCode` mới là cơ sở để làm khóa `Map<MethodType, ...>` và so sánh logic.

`MethodType` bất biến: mọi phương thức `change...`, `insert...`, `drop...`, `erase`, `wrap`, `unwrap` trả về một `MethodType` **mới về mặt ý nghĩa** hoặc có thể dùng lại object hiện có nếu signature không đổi. Không có thay đổi “tại chỗ”; giữ biến gốc không tự cập nhật.

Cũng cần lưu ý: `Class<?>` gắn với class identity và class loader. Hai class có **cùng tên** nhưng do hai class loader khác nhau định nghĩa là hai kiểu khác nhau; hai `MethodType` tương ứng có thể không `equals`, dù hiển thị `toString` hoặc descriptor giống nhau.

## 5. Biến đổi tham số và kiểu trả về

Giả sử signature gốc:

```java
MethodType base = MethodType.methodType(
        String.class, String.class, int.class); // (String,int)String
```

### 5.1. Đổi một tham số: `changeParameterType`

```java
MethodType changed = base.changeParameterType(1, long.class);
// (String,long)String
```

`1` là chỉ số của tham số `int`; nó được thay bằng `long`. Kiểu trả về và các tham số khác giữ nguyên. Index không tồn tại gây `IndexOutOfBoundsException`; `void.class` không hợp lệ làm tham số nên gây `IllegalArgumentException`.

### 5.2. Đổi kiểu trả về: `changeReturnType`

```java
MethodType noReturn = base.changeReturnType(void.class);
// (String,int)void
```

`void.class` **hợp lệ ở vị trí trả về**. Thay nó bằng `Void.class` tạo signature khác: `(String,int)Void`.

### 5.3. Chèn và nối tham số

```java
MethodType inserted = base.insertParameterTypes(1, boolean.class);
// (String,boolean,int)String

MethodType appended = base.appendParameterTypes(double.class);
// (String,int,double)String
```

`insertParameterTypes(pos, ...)` chèn **trước** vị trí `pos`, nhận `pos` từ `0` tới `parameterCount()` (bao gồm vị trí cuối); `appendParameterTypes(...)` nối vào cuối danh sách tham số. Cả hai từ chối kiểu tham số `void.class`.

### 5.4. Bỏ một khoảng tham số

```java
MethodType dropped = base.dropParameterTypes(1, 2);
// (String)String
```

Khoảng `[start, end)` có **start inclusive, end exclusive**: bỏ tham số ở index 1, giữ index 0. Không nhầm `dropParameterTypes(1,2)` là bỏ hai tham số; nó bỏ đúng một tham số. Với `start == end`, không có tham số nào bị bỏ. Index/khoảng không hợp lệ gây `IndexOutOfBoundsException`.

### 5.5. Bảng đối chiếu trực quan

| Phép biến đổi trên `(String,int)String` | Signature kết quả |
| --- | --- |
| `changeParameterType(1, long.class)` | `(String,long)String` |
| `changeReturnType(void.class)` | `(String,int)void` |
| `insertParameterTypes(1, boolean.class)` | `(String,boolean,int)String` |
| `appendParameterTypes(double.class)` | `(String,int,double)String` |
| `dropParameterTypes(1, 2)` | `(String)String` |

**Cảnh báo quan trọng:** các phép biến đổi trên chỉ tạo **bản mô tả signature**. Chúng **không** tự biến implementation thực tế của method từ `int` sang `long`, không chèn/bỏ đối số của `MethodHandle` hiện có. Khi cần đổi chữ ký thực của handle, dùng các adapter đúng hợp đồng như `asType`, `MethodHandles.dropArguments`, `insertArguments`, `filterArguments`... theo trường hợp cụ thể, và phải kiểm tra conversion có hợp lệ hay không.

## 6. `erase()`, `generic()`, `wrap()` và `unwrap()`

Đây là nhóm phép biến đổi thường dễ bị hiểu nhầm, nhất là khi xuất hiện primitive và `void`.

### 6.1. `erase()` — thay reference thành Object, giữ primitive

```java
MethodType t = MethodType.methodType(
        String.class, String.class, int.class);
System.out.println(t.erase()); // (Object,int)Object
```

`String` (reference) thành `Object` cả ở tham số và trả về. `int` (primitive) **giữ nguyên**. Nếu trả về `void`, `erase` vẫn trả về `void`.

### 6.2. `generic()` — mọi thành phần thành Object

```java
System.out.println(t.generic()); // (Object,Object)Object
```

`generic` thay **cả primitive lẫn reference** bằng `Object`, cùng số tham số. Nó tương đương kết quả `t.wrap().erase()`. Tên “generic” ở đây mô tả một signature tổng quát dạng `Object`; đây **không** phải Java `<T>` generic type declaration. Vì vậy `erase()` và `generic()` không tương đương nếu signature có primitive.

### 6.3. `wrap()` — primitive sang wrapper

```java
System.out.println(t.wrap()); // (String,Integer)String
```

`int` thành `Integer`, các reference như `String` vẫn giữ nguyên. Riêng **kiểu trả về `void`** được thay bằng `java.lang.Void`. `wrap()` không tạo wrapper object hay thực hiện lời gọi, chỉ tạo mô tả signature có kiểu wrapper.

### 6.4. `unwrap()` — wrapper sang primitive

```java
System.out.println(t.wrap().unwrap()); // (String,int)String
```

`Integer` thành `int`. Riêng **kiểu trả về `Void`** được thay bằng `void`. Với tham số kiểu `Void.class`, `unwrap()` **giữ nguyên `Void.class`** vì `void` không được phép làm kiểu tham số. Không được xem `unwrap()` là phép chuyển đổi có thể tự áp dụng an toàn lên mọi giá trị runtime.

### 6.5. Cờ kiểm tra kiểu primitive và wrapper

- `hasPrimitives()` cho biết signature có primitive ở tham số hoặc kết quả. **Kiểu trả về `void` cũng được tính là primitive** khi kiểm tra cờ này.
- `hasWrappers()` cho biết có wrapper type. **`Void.class` ở vị trí trả về** được tính là wrapper.
- Hai cờ này mô tả thành phần signature; chúng **không** xác nhận rằng method target có thể chấp nhận một kiểu khác hoặc đã có adapter chuyển đổi.

## 7. Phân biệt chính xác `void` và `java.lang.Void`

Đây là điểm trọng tâm của bài.

| Tiêu chí | `void` / `void.class` | `java.lang.Void` / `Void.class` |
| --- | --- | --- |
| Bản chất | Từ khóa Java biểu diễn **không có giá trị trả về**; `void.class` là đối tượng `Class` biểu diễn kiểu đặc biệt đó | Một **reference class** thuộc `java.lang`, dùng làm đại diện cho `void` trong ngữ cảnh cần object kiểu Class |
| Có thể khai báo biến giá trị? | Không: `void x` không phải khai báo hợp lệ | Có: `Void x = null;` hợp lệ; `Void` không có instance hữu dụng để xây dựng theo cách thông thường |
| Đối với return type của `MethodType` | Hợp lệ: `methodType(void.class)` → `()void` | Hợp lệ: `methodType(Void.class)` → `()Void` |
| Đối với parameter type của `MethodType` | **Không hợp lệ**: `methodType(int.class, void.class)` ném `IllegalArgumentException` | **Hợp lệ về mặt cấu trúc**: `methodType(int.class, Void.class)` → `(Void)int`, dù hiếm khi hữu ích |
| JVM descriptor trả về | `V` | `Ljava/lang/Void;` |
| Gọi method Java | Method `void` không trả một object nào | Method trả `Void` là reference-returning method; thông thường `return null;` |
| `wrap()/unwrap()` ở return type | `wrap` đổi `void` thành `Void` | `unwrap` đổi `Void` thành `void` |
| So sánh class literal | `void.class == Void.TYPE` là `true` | `Void.class != void.class` là `true` |

**Ví dụ hai chữ ký khác nhau:**

```java
MethodType noValue = MethodType.methodType(void.class, String.class);
MethodType nullableReference = MethodType.methodType(Void.class, String.class);

System.out.println(noValue);          // (String)void
System.out.println(nullableReference); // (String)Void
System.out.println(noValue.equals(nullableReference)); // false
```

Hai signature **không giống nhau**, kể cả khi nhiều API dùng `Void` để biểu diễn “không có kết quả hữu ích”. Java không cho phép overload hai method chỉ khác return type tại source level; khi định nghĩa hai ví dụ thực thi, ta dùng **hai tên phương thức riêng**.

### 7.1. Đừng nhầm `Void.TYPE` với `Void.class`

`Void.TYPE` chính là `Class` object biểu diễn primitive-like type `void`, tương đương `void.class`. Nhưng `Void.class` là class `java.lang.Void` thực sự. Hai đối tượng Class đó khác nhau:

```java
boolean a = (Void.TYPE == void.class);   // true
boolean b = (Void.class == void.class);  // false
```

### 7.2. Không có “boxing value” của `void`

Đối với `int` có thể boxing giá trị `7` thành `Integer.valueOf(7)`. Nhưng `void` biểu diễn **không có giá trị**, nên không có “giá trị void” để boxing thực sự thành một đối tượng `Void`. `MethodType.wrap()` là phép biến đổi **chữ ký**, không phải thao tác tạo object `Void`. Khi API có generic result `Void`, người viết code thường dùng `null` để biểu diễn hoàn thành nhưng không có payload.

Điều này khác với `Optional<Void>`, `CompletableFuture<Void>` hay một callback có kiểu kết quả `Void`; những cấu trúc đó thường quy ước hoàn tất thành công bằng giá trị `null`, nhưng bản thân `Void` không biến thành kiểu trả về `void` của method thật.

### 7.3. `void` trong MethodHandle thực tế

Khi tìm method bằng `findStatic`, `MethodType` phải khớp **kiểu trả về thực của method**:

```java
public static void ping(String text) { System.out.println(text); }
public static Void boxedPing(String text) {
    System.out.println(text);
    return null;
}
```

Đoạn trên chỉ là **các method khai báo trong một class**, không phải chương trình Java độc lập. Để lookup `ping`, dùng `methodType(void.class, String.class)`; để lookup `boxedPing`, dùng `methodType(Void.class, String.class)`. Không tự ý thay `void` bằng `Void` rồi giả định lookup nhận như nhau.

## 8. Vì sao phải hiểu MethodType khi sử dụng Lookup và MethodHandle?

Xét lời gọi tìm method tĩnh:

```java
MethodType signature = MethodType.methodType(
        String.class, String.class, int.class);
MethodHandle handle = MethodHandles.lookup().findStatic(
        MethodTypeGuide.class, "repeat", signature);
```

Đoạn minh họa này cần đặt trong mã có class `MethodTypeGuide` thực sự chứa method `public static String repeat(String, int)`; ví dụ hoàn chỉnh ở phần tiếp theo.

Trong `findStatic`:
1. `Lookup` cung cấp ngữ cảnh kiểm tra quyền truy cập.
2. Class + tên method + `MethodType` xác định method cần tìm.
3. Lookup có thể lỗi `NoSuchMethodException` hoặc `IllegalAccessException` nếu method không tồn tại, signature không khớp hoặc không được truy cập.
4. Handle nhận được có `handle.type()`, mô tả signature mà caller phải đáp ứng.

`invokeExact` yêu cầu chữ ký ngay tại **call site** phù hợp chính xác với kiểu handle, bao gồm các tham số và kiểu kết quả. Khi sai, có thể ném `WrongMethodTypeException`. `invoke` và `asType` hỗ trợ một số adaptation/conversion theo quy tắc của API, nhưng không có phép biến đổi tùy ý.

Ví dụ, việc gọi `signature.changeParameterType(1, long.class)` tạo một mô tả `(String,long)String` **không khiến** `repeat(String,int)` chấp nhận `long`. Muốn có handle hỗ trợ chữ ký khác, phải kiểm chứng conversion và tạo adapter handle thích hợp (nếu có thể). Đừng chỉ đổi biến `MethodType` rồi gọi target cũ.

## 9. Chương trình Java 17+ hoàn chỉnh và kết quả đã xác minh

Lưu file **`MethodTypeGuide.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodTypeGuide {
    public static String repeat(String text, int count) {
        return text.repeat(count);
    }

    public static void ping(String text) {
        System.out.println("ping=" + text);
    }

    public static Void boxedPing(String text) {
        System.out.println("boxedPing=" + text);
        return null;
    }

    public static void main(String[] args) throws Throwable {
        MethodType base = MethodType.methodType(
                String.class, String.class, int.class);
        MethodType same = MethodType.methodType(
                String.class, new Class<?>[] { String.class, int.class });

        System.out.println("base=" + base);
        System.out.println("equals=" + base.equals(same));
        System.out.println("parameters=" + base.parameterCount());
        System.out.println("second=" + base.parameterType(1).getSimpleName());
        System.out.println("return=" + base.returnType().getSimpleName());
        System.out.println("parameterChanged="
                + base.changeParameterType(1, long.class));
        System.out.println("returnChanged="
                + base.changeReturnType(void.class));
        System.out.println("inserted="
                + base.insertParameterTypes(1, boolean.class));
        System.out.println("appended="
                + base.appendParameterTypes(double.class));
        System.out.println("dropped="
                + base.dropParameterTypes(1, 2));
        System.out.println("erased=" + base.erase());
        System.out.println("generic=" + base.generic());
        System.out.println("wrapped=" + base.wrap());
        System.out.println("unwrapped=" + base.wrap().unwrap());
        System.out.println("descriptor=" + base.toMethodDescriptorString());
        System.out.println("baseStill=" + base);

        MethodType noResult = MethodType.methodType(void.class, String.class);
        MethodType boxedResult = MethodType.methodType(Void.class, String.class);
        System.out.println("voidType=" + noResult);
        System.out.println("VoidType=" + boxedResult);
        System.out.println("voidDescriptor=" + noResult.toMethodDescriptorString());
        System.out.println("VoidDescriptor=" + boxedResult.toMethodDescriptorString());
        System.out.println("voidEqualsVoid=" + noResult.equals(boxedResult));
        System.out.println("wrapVoid=" + noResult.wrap());
        System.out.println("unwrapVoid=" + boxedResult.unwrap());
        System.out.println("voidIsPrimitive=" + noResult.hasPrimitives());
        System.out.println("VoidIsWrapper=" + boxedResult.hasWrappers());

        try {
            MethodType.methodType(int.class, void.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("voidParameter=" + expected.getClass().getSimpleName());
        }

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle repeatHandle = lookup.findStatic(
                MethodTypeGuide.class, "repeat", base);
        String repeated = (String) repeatHandle.invokeExact("ha", 3);
        System.out.println("invokeExact=" + repeated);

        MethodHandle pingHandle = lookup.findStatic(
                MethodTypeGuide.class, "ping", noResult);
        pingHandle.invokeExact("ok");

        MethodHandle boxedPingHandle = lookup.findStatic(
                MethodTypeGuide.class, "boxedPing", boxedResult);
        Void answer = (Void) boxedPingHandle.invokeExact("ok");
        System.out.println("boxedValue=" + answer);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 MethodTypeGuide.java
java MethodTypeGuide
```

**Stdout:**

```text
base=(String,int)String
equals=true
parameters=2
second=int
return=String
parameterChanged=(String,long)String
returnChanged=(String,int)void
inserted=(String,boolean,int)String
appended=(String,int,double)String
dropped=(String)String
erased=(Object,int)Object
generic=(Object,Object)Object
wrapped=(String,Integer)String
unwrapped=(String,int)String
descriptor=(Ljava/lang/String;I)Ljava/lang/String;
baseStill=(String,int)String
voidType=(String)void
VoidType=(String)Void
voidDescriptor=(Ljava/lang/String;)V
VoidDescriptor=(Ljava/lang/String;)Ljava/lang/Void;
voidEqualsVoid=false
wrapVoid=(String)Void
unwrapVoid=(String)void
voidIsPrimitive=true
VoidIsWrapper=true
voidParameter=IllegalArgumentException
invokeExact=hahaha
ping=ok
boxedPing=ok
boxedValue=null
```

### Đọc kết quả

- `base` và `same` được tạo qua hai overload khác nhau của `methodType` nhưng bằng nhau qua `equals`.
- `parameterChanged`, `returnChanged`, `inserted`, `appended`, `dropped` kiểm tra đúng thứ tự và chỉ số tham số. `baseStill` chứng tỏ các phép biến đổi không sửa signature gốc.
- `erased` giữ `int`; `generic` chuyển `int` thành `Object`; `wrapped` chuyển `int` thành `Integer`; `unwrapped` đưa wrapper trở lại kiểu primitive.
- Hai descriptor `(Ljava/lang/String;)V` và `(Ljava/lang/String;)Ljava/lang/Void;` khác nhau ở **return type**. Vì thế `voidEqualsVoid=false`.
- `voidIsPrimitive=true` và `VoidIsWrapper=true` khớp quy tắc riêng của `hasPrimitives` và `hasWrappers`.
- `voidParameter=IllegalArgumentException` minh họa `void.class` **không** được dùng làm parameter type.
- `repeatHandle.invokeExact("ha", 3)` khớp `(String,int)String` và trả `hahaha`. `pingHandle` chạy một method không trả giá trị, còn `boxedPingHandle` trả reference `Void` với giá trị `null`.

Chương trình được viết cho Java 17+ (`String.repeat` có từ Java 11). Các method `main throws Throwable` giúp ví dụ tập trung vào API; ứng dụng thực nên xử lý riêng lỗi lookup/access, adaptation và exception từ target.

## 10. Thiết kế API và kiểm tra lỗi khi tạo MethodType

### 10.1. Kiểm tra đầu vào

| Lỗi cấu hình/lập trình | Kết quả hoặc kiểm tra phù hợp |
| --- | --- |
| `rtype == null` | `methodType` ném `NullPointerException` |
| Một kiểu tham số là `null` | `NullPointerException` |
| Một kiểu tham số là `void.class` | `IllegalArgumentException` |
| Index không thuộc danh sách tham số | `IndexOutOfBoundsException` |
| `insertParameterTypes` chèn sau index cuối | `IndexOutOfBoundsException` |
| Thêm quá nhiều tham số/slots JVM | `IllegalArgumentException` |
| Descriptor sai cú pháp | `IllegalArgumentException` từ `fromMethodDescriptorString` |
| Class trong descriptor không thể resolve | Có thể là `TypeNotPresentException` |
| `Lookup` dùng signature không đúng method thật | Thường là `NoSuchMethodException` khi lookup |
| `invokeExact` dùng kiểu call site sai handle | `WrongMethodTypeException` |

JVM có giới hạn số **parameter slots** trong method descriptor; `long` và `double` chiếm hai slots. Không nên tự xây signature chứa hàng trăm tham số theo dữ liệu ngoài; hãy xác thực độ dài và xây interface/DTO phù hợp.

### 10.2. Tách việc dựng signature khỏi việc thực thi

Một trình gọi động có thể đi qua các bước:

1. Đọc tên method và các type token từ **cấu hình đã kiểm chứng**.
2. Chuẩn hóa thứ tự tham số, đảm bảo không có `null` hoặc `void.class` ở vị trí tham số; phân biệt `void.class` với `Void.class` ở return.
3. Tạo `MethodType`, so sánh với hợp đồng dự kiến bằng `equals`, và log descriptor khi lỗi để tránh nhầm các overload.
4. Resolve handle bằng `Lookup`; kiểm tra `handle.type()` sau khi tìm.
5. Nếu cần adaptation, tạo handle mới bằng API adapter và test kiểu chuyển đổi; không chỉ thay `MethodType` rời rạc.
6. Gọi handle qua đúng signature và chuyển lỗi thành thông báo có ngữ cảnh: class, tên method, descriptor, kiểu đối số, cấu hình liên quan.

`MethodType` **không mang tên class/method hoặc access permission**. Vì thế kiểm tra `equals` chỉ cho biết hai signature có giống nhau, chưa chứng minh method tồn tại, có quyền truy cập hay logic target đúng.

## 11. Sai lầm thường gặp

1. **Đặt tham số trước return type trong `methodType`.** Đối số đầu tiên của factory là **return type**; các đối số sau là tham số theo thứ tự.
2. **Dùng `==` để so sánh MethodType.** Factory có thể cache, nhưng điều kiện bằng nhau phải dùng `equals`.
3. **Cho rằng `changeParameterType` làm method đang chạy đổi tham số.** Nó chỉ trả signature khác; handle và implementation gốc không thay đổi.
4. **Đồng nhất `erase` và `generic`.** `erase` giữ primitive; `generic` chuyển cả primitive thành `Object`.
5. **Hiểu `wrap()` tạo object wrapper.** Nó chỉ đổi chữ ký; `void` không có giá trị để boxing.
6. **Đồng nhất `void.class` và `Void.class`.** Chúng khác class identity, descriptor và hợp đồng lời gọi.
7. **Cho phép tham số `void.class`.** `void` không thể là kiểu parameter, nhưng `Void.class` là reference parameter type hợp lệ.
8. **Quên receiver trong handle của method instance.** `findVirtual` nhận signature khai báo, còn handle trả về có receiver là tham số đầu.
9. **Đọc `toString` như JVM descriptor.** `(String,int)String` chỉ là biểu diễn dễ đọc; descriptor đúng là `(Ljava/lang/String;I)Ljava/lang/String;`.
10. **Dùng `MethodType` làm bằng chứng method có thể invoke.** Vẫn phải lookup đúng target, kiểm tra quyền và kiểu tại call site.

## 12. Bài tập củng cố

**Bài 1 — Đọc và biến đổi:**

Cho `MethodType t = MethodType.methodType(long.class, int.class, String.class);`. Hãy dự đoán `t`, `t.erase()`, `t.generic()`, `t.wrap()`, `t.dropParameterTypes(0,1)`.

**Đáp án:** `(int,String)long`, `(int,Object)long`, `(Object,Object)Object`, `(Integer,String)Long`, `(String)long`.

**Bài 2 — void với Void:**

`MethodType.methodType(void.class, int.class)` có hợp lệ không? `MethodType.methodType(int.class, void.class)` thì sao? `MethodType.methodType(int.class, Void.class)` thì sao?

**Đáp án:** Lần lượt **hợp lệ**, **không hợp lệ** (`IllegalArgumentException`), **hợp lệ** (tham số reference `Void`, tuy hiếm hữu ích).

**Bài 3 — Phân tích bug:**

Một method thực tế là `public static void log(String message)`. Code gọi `findStatic(clazz, "log", MethodType.methodType(Void.class, String.class))` bị lỗi lookup. Vì sao?

**Đáp án:** Return type phải là `void.class`. `Void.class` mô tả một method trả reference `Void`, khác chữ ký method trả `void`.

**Bài 4 — Kiểm tra receiver:**

Với `String.concat(String)`, `findVirtual(String.class, "concat", MethodType.methodType(String.class, String.class))` dùng signature khai báo một tham số `String`. Handle thu được có dạng `(String,String)String`; `String` đầu tiên là receiver. Viết `invokeExact` sao cho trả chuỗi `"Java17"` từ receiver `"Java"` và tham số `"17"`.

**Gợi ý:** `(String) handle.invokeExact("Java", "17")`, với `handle` là MethodHandle đã lookup thành công.

## Tài liệu chính thức

- [Java SE 17 API — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 17 API — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 API — Void](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Void.html)

## Kết luận

`MethodType` là **mô tả kiểu bất biến** của lời gọi: kiểu trả về cùng dãy kiểu tham số theo thứ tự. Hãy tạo nó bằng factory, so sánh qua `equals`, biến đổi bằng các API trả một signature khác và phân biệt rõ thao tác **trên signature** với adaptation/thực thi của `MethodHandle`. Trong mọi trường hợp cần kết quả “không trả giá trị”, nhớ rằng **`void.class` khác `Void.class`**: `void` là return type không có giá trị, còn `Void` là reference type, và hai kiểu có chữ ký JVM khác nhau.
