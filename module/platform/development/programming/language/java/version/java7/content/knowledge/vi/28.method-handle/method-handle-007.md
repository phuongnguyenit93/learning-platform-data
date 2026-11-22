# MethodHandle trong Java: Chuyển chữ ký bằng asType

## 1. Bài toán: cùng một hàm, nhiều chữ ký cần gọi

Giả sử một bộ xử lý động trong Java đã giữ tham chiếu có kiểu tới một phương thức:

```java
public static int add(int a, int b) {
    return Math.addExact(a, b);
}
```

Phương thức này nhận **hai `int`** và trả **`int`**. Nếu code gọi động sử dụng `MethodHandle`, chữ ký tương ứng là:

```text
(int, int) -> int
hoặc dạng MethodType.toString():
(int,int)int
```

Nhưng hệ thống nhận dữ liệu từ một API khác có thể muốn gọi nó theo chữ ký:

- `(short, byte) -> long`, vì hai đầu vào nhỏ hơn `int`, kết quả muốn dùng `long`.
- `(Integer, Integer) -> Object`, vì tầng xử lý giữ wrapper objects và trả về một giá trị chung.
- `(Object, Object) -> Object`, vì một plugin dispatcher quản lý dữ liệu như `Object` và sẽ kiểm tra kiểu ở runtime.

Có cần viết ba phiên bản `add` hoặc dùng reflection gọi từng lần? **Không nhất thiết.** `java.lang.invoke.MethodHandle.asType(MethodType newType)` tạo ra **một adapter MethodHandle** có chữ ký mới, thực hiện các phép chuyển kiểu cho phép trước và sau khi gọi handle gốc.

**Trọng tâm của bài:**

> `asType` không sửa hàm đích, không sửa chữ ký của handle gốc và không biến bất kỳ kiểu nào thành bất kỳ kiểu nào. Nó xây một **handle mới có `type()` đúng bằng `newType`**, chuyển từng tham số và giá trị trả về theo các quy tắc được Java hỗ trợ.

API `MethodHandle`, `MethodType` và `asType` xuất hiện từ **Java 7** và **vẫn hiện hành**. Nội dung dưới đây sử dụng Javadoc **Java SE 17** để mô tả chính xác các chuyển đổi, kết hợp ví dụ Java 17+ được biên dịch/chạy bằng `javac --release 17 -Xlint:all -Werror`. Không sử dụng kỹ thuật private reflection, API nội bộ JVM hay kiến thức đã deprecated.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Đọc chữ ký của `MethodHandle` qua `type()` và tạo chữ ký mới bằng `MethodType.methodType`.
2. Hiểu chiều chuyển đổi tham số và giá trị trả về của `asType`.
3. Dùng widening primitive, boxing/unboxing và reference cast hợp lệ.
4. Hiểu conversion cho kiểu `void`, gồm bỏ kết quả và sinh giá trị mặc định.
5. Phân biệt `WrongMethodTypeException`, `ClassCastException` và `NullPointerException`.
6. Phân biệt `invokeExact` với `invoke` khi có/không có adapter.
7. Biết vì sao Java không tự chuyển `String` thành số, và không tự cho phép primitive narrowing.
8. Phân biệt `asType` với `explicitCastArguments`, `asCollector`, `asSpreader`, `filterArguments`, `permuteArguments`.
9. Thiết kế và kiểm thử dynamic adapters bằng Java 17.
10. Tránh sai lầm về return type của call site, hiệu năng và quyền truy cập khi dùng method handles.

## 2. MethodHandle là gì?

`MethodHandle` là **tham chiếu thực thi có kiểu** (*typed executable reference*) tới một phương thức, constructor, field hoặc một computation đã được tổ hợp bằng các method-handle combinators.

Ví dụ tạo handle tới static method ở đầu bài:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandle addHandle = MethodHandles.lookup().findStatic(
        MyMath.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));
```

Đây là đoạn minh họa nằm trong phương thức có `throws NoSuchMethodException, IllegalAccessException`; class `MyMath` được ứng dụng định nghĩa và chứa `public static int add(int,int)`.

Các thành phần:

- `MethodHandles.lookup()`: đối tượng `Lookup` chịu trách nhiệm tìm handle theo quyền truy cập của caller.
- `findStatic`: tìm đúng phương thức static với tên và descriptor yêu cầu.
- `MethodType.methodType`: tham số **đầu tiên là return type**, các tham số sau là **parameter types**.
- `int.class`: primitive `int`, khác với `Integer.class`.
- `addHandle.type()`: mô tả chữ ký chính xác của handle.

Khi `findStatic` thành công:

```text
addHandle.type() = (int,int)int
```

**MethodHandle là immutable.** Adapter `asType` không làm thay đổi handle gốc. Tuy nhiên, phương thức đích mà handle trỏ tới **vẫn có thể gây side effects**, làm thay đổi state hoặc ném exception: immutable handle không có nghĩa hàm đích là pure function.

### 2.1. MethodType là danh tính chữ ký thực thi

`java.lang.invoke.MethodType` biểu diễn:

- Một kiểu trả về: `void.class` hoặc một primitive/reference type.
- Một **danh sách có thứ tự** các kiểu tham số.
- Cùng `Class` đại diện cho các kiểu cụ thể, bao gồm class loader identity khi cần.

Ví dụ:

```java
MethodType original = MethodType.methodType(
        int.class, int.class, int.class);
MethodType desired = MethodType.methodType(
        long.class, short.class, byte.class);
```

`original.toString()` là `(int,int)int`; `desired.toString()` là `(short,byte)long`.

**Không đảo thứ tự return type và parameter types**. Một lỗi dễ gặp là tưởng đối số `int.class` đầu tiên của `methodType` thuộc tham số thứ nhất, khiến handle được khai báo sai ngay từ đầu.

### 2.2. Kiểu là một phần của hợp đồng invocation

`MethodHandle` không chỉ giữ “địa chỉ hàm”; nó giữ descriptor. Hai methods cùng tên nhưng khác chữ ký được phân biệt rõ. `invokeExact` và `invoke` là các **signature-polymorphic methods**: compiler ghi **kiểu tĩnh của đối số và kiểu trả về ở call site** vào bytecode.

```java
int result = (int) addHandle.invokeExact(3, 4);
```

Đây là đoạn minh họa với `addHandle` có kiểu `(int,int)int` và một method `throws Throwable`. Cast `(int)` giúp call site yêu cầu return type `int`; `invokeExact` đòi descriptor call site **khớp chính xác** với `addHandle.type()`.

Không coi `invokeExact` là “reflection truyền một mảng Object rồi Java tự convert”: cơ chế thực thi rất khác.

## 3. asType(MethodType): hợp đồng chính thức

Chữ ký API:

```java
public MethodHandle asType(MethodType newType)
```

Cơ chế với handle gốc có type `T_old` và adapter có `T_new`:

```text
Caller cung cấp đối số theo T_new
             |
             v
Chuyển tham số từ T_new.param[i] -> T_old.param[i]
             |
             v
Gọi target handle gốc theo T_old
             |
             v
Chuyển kết quả từ T_old.return -> T_new.return
             |
             v
Caller nhận kết quả theo T_new.return
```

Đây là **sơ đồ**; không phải một method Java tự viết lại.

Lưu ý **hai chiều khác nhau**:

- **Tham số:** từ kiểu **mới** ở call site sang kiểu **cũ** mà hàm đích yêu cầu.
- **Kết quả:** từ kiểu **cũ** do hàm đích trả về sang kiểu **mới** mà caller kỳ vọng.

Một nhầm lẫn phổ biến là áp dụng hướng của return type cho parameters, dẫn đến kết luận sai về conversion.

### 3.1. Adapter không sửa handle gốc

```java
MethodHandle widened = addHandle.asType(
        MethodType.methodType(long.class, short.class, byte.class));
```

Sau lời gọi:

```text
addHandle.type(): (int,int)int
widened.type():   (short,byte)long
```

Chính `widened` có descriptor mới; `addHandle` vẫn giữ descriptor gốc. Bạn có thể giữ cả hai và sử dụng ở những call sites khác nhau.

### 3.2. Nếu chữ ký đã giống nhau

Theo Javadoc, nếu `newType.equals(originalHandle.type())` thì `asType(newType)` **trả chính `this`**. Không cần kỳ vọng một adapter mới được cấp phát cho trường hợp identity.

```java
boolean sameObject =
        addHandle.asType(addHandle.type()) == addHandle;
```

Trong trường hợp này `sameObject` là `true`. Nhưng không suy rằng mọi lần yêu cầu cùng một kiểu **khác kiểu gốc** đều trả cùng instance adapter: JVM có thể cache hoặc tạo mới tùy implementation.

### 3.3. Kết quả phải có đúng MethodType được yêu cầu

Một phép `asType` thành công **bảo đảm**:

```java
adapted.type().equals(newType)
```

là `true`.

Nếu conversion không thể xây được, lời gọi `asType` ném `WrongMethodTypeException` thay vì trả adapter nửa vời.

### 3.4. Không gọi hàm đích khi xây adapter

`asType` chỉ tạo **phương thức thích nghi để gọi sau này**. Nó không tự thực thi `add` tại thời điểm tạo. Nếu một target có side effect, side effect chỉ xảy ra khi adapter hoặc handle được invoke, không phải khi chỉ gọi `asType`.

## 4. Chuyển kiểu nguyên thủy: chỉ widening theo method invocation conversion

Đây là phần dễ hiểu sai nhất. Với primitive-to-primitive, `asType` dùng **widening primitive conversion** được phép bởi Java method invocation conversion (JLS `5.3), **không tự chấp nhận narrowing primitive conversion**.

Ví dụ:

- `byte -> short -> int -> long -> float -> double` theo các cạnh widening hợp lệ.
- `char -> int/long/float/double` (không `char -> short`).
- `int -> long` hợp lệ.
- `long -> int` **không** hợp lệ trực tiếp.
- `double -> float` **không** hợp lệ trực tiếp.
- `boolean` chỉ giữ `boolean`, không tự đổi thành `0`/`1` bằng asType.

Không xem chuỗi mũi tên trên là chỉ được chuyển từng nấc ngay bên cạnh; `byte -> double` hoặc `char -> long` cũng có thể là widening trực tiếp theo Java.

### 4.1. Ví dụ hoàn chỉnh về widening

Handle gốc:

```text
(int,int)int
```

Muốn adapter:

```text
(short,byte)long
```

Phân tích:

1. Tham số đầu: `short -> int`, hợp lệ.
2. Tham số thứ hai: `byte -> int`, hợp lệ.
3. Giá trị trả: `int -> long`, hợp lệ.
4. Số tham số vẫn bằng `2`.

```java
MethodHandle widened = addHandle.asType(
        MethodType.methodType(long.class, short.class, byte.class));

long result = (long) widened.invokeExact((short) 12, (byte) 4);
```

Trong đoạn này, giả sử `addHandle` đã tạo hợp lệ như trên và method khai báo `throws Throwable`. `result == 16L`.

**Cast ngay tại call site là quan trọng:** compiler phải thấy hai tham số có kiểu tĩnh đúng `short`, `byte` và return type yêu cầu là `long` để `invokeExact` khớp adapter.

### 4.2. Cố narrowing sẽ thất bại khi asType

Ví dụ muốn adapter:

```java
MethodType illegal = MethodType.methodType(
        int.class, long.class, int.class);
addHandle.asType(illegal);
```

Adapter giả định nhận `long` ở tham số đầu nhưng target cần `int`. `long -> int` là narrowing, do đó `asType` ném `WrongMethodTypeException`.

**Không được sửa bằng cách bắt exception rồi lặng lẽ cắt số** nếu bài toán nghiệp vụ cần số nguyên toàn vẹn. Nếu thật sự muốn cast có narrowing, dùng phép cast tường minh sau khi kiểm tra range, hoặc xem xét `MethodHandles.explicitCastArguments` và nắm rõ chính sách mất dữ liệu.

### 4.3. Widening có thể mất chính xác ở floating point

Dù `int -> float` và `long -> double` được Java cho phép về kiểu, một số giá trị nguyên lớn có thể **không biểu diễn chính xác** trong floating point. “Được widening” không đồng nghĩa giữ mọi bit giá trị số như nhau.

Khi cần exact financial amounts hoặc IDs lớn, không đổi tùy tiện sang `float/double` chỉ vì `asType` cho phép. Hãy dùng kiểu dữ liệu và validation phù hợp với yêu cầu nghiệp vụ.

## 5. Boxing và unboxing: primitive ↔ wrapper/reference

Một pattern phổ biến là tầng gọi mang `Integer` hoặc `Object`, còn phương thức thực nhận `int`.

Ví dụ target:

```text
(int,int)int
```

Adapter:

```text
(Integer,Integer)Object
```

Chuỗi chuyển đổi:

```text
Integer param 1 --unbox--> int
Integer param 2 --unbox--> int
target add(int,int) returns int
int --box--> Integer --reference widen--> Object
```

Mã:

```java
MethodHandle boxed = addHandle.asType(
        MethodType.methodType(
                Object.class, Integer.class, Integer.class));

Object value = (Object) boxed.invokeExact(
        Integer.valueOf(5), Integer.valueOf(7));
```

Khi không có lỗi, `value` là một `Integer` có giá trị `12`, được nhìn dưới kiểu tĩnh `Object`.

### 5.1. Boxing không có nghĩa đổi primitive sang bất kỳ class

Phép chuyển `int -> Object` hợp lệ vì `int` được boxing thành `Integer` rồi mở rộng tham chiếu lên `Object`.

Nhưng chuyển `int -> String` không được phép: `String` không phải superclass của `Integer` và `asType` không có logic `String.valueOf(int)` ngầm.

Tương tự `int -> Long` qua `asType` không có nghĩa “widen int thành long rồi boxing thành Long” trong mọi tổ hợp. Theo hợp đồng primitive-to-reference, việc boxing gắn với **wrapper tương ứng của primitive đầu vào**, rồi widening reference. Muốn chuyển số vào `Long`, thiết kế adapter qua kiểu `long` rồi xử lý boxing phù hợp, hoặc dùng filter rõ ràng.

### 5.2. Unboxing từ Object

`asType` có thể tạo adapter có tham số kiểu `Object` để gọi target `int`:

```java
MethodHandle generic = addHandle.asType(
        MethodType.methodType(
                Object.class, Object.class, Object.class));

Object answer = (Object) generic.invokeExact(
        (Object) Integer.valueOf(9),
        (Object) Integer.valueOf(2));
```

`answer` là `Integer(11)`. Với `Object -> int`, adapter sẽ kiểm tra runtime object có kiểu wrapper phù hợp để unbox (và có thể widen nếu hợp đồng cho phép).

Đây **không** phải parse tùy ý: `"9"` là `String` chứ không phải một wrapper số có thể unbox thành `int`.

### 5.3. Tại sao unboxing null gây NullPointerException?

`null` không chứa giá trị nguyên thủy. Nếu adapter phải unbox một `Object` hoặc `Integer` thành `int` mà đối số thực tế là `null`, nó ném `NullPointerException` **ở runtime**.

Ví dụ:

```java
Object left = null;
Object right = Integer.valueOf(2);
Object x = (Object) generic.invokeExact(left, right);
```

Đây là **mã minh họa cố tình ném lỗi**, vì adapter kiểu `(Object,Object)Object` cố unbox `left` để gọi `add(int,int)`. `asType` có thể tạo adapter thành công, nhưng lỗi chỉ xuất hiện khi gọi với giá trị cụ thể.

### 5.4. Wrong wrapper type gây ClassCastException

Một adapter nhận `Object` chưa biết runtime value là gì. Nếu caller truyền:

```java
Object left = "not-an-int";
Object right = Integer.valueOf(2);
Object x = (Object) generic.invokeExact(left, right);
```

Adapter không thể unbox `String` thành `int` nên ném `ClassCastException`. Không phải `WrongMethodTypeException`, vì **chữ ký (Object,Object)Object hoàn toàn có thể thích nghi**; chỉ **giá trị runtime cụ thể** mới không đáp ứng.

### 5.5. Những wrapper nào được chấp nhận?

Với đích là `int`, khi source là `Object`, runtime có thể unbox các wrapper có primitive có thể widen thành `int`, ví dụ `Byte`, `Short`, `Character` và `Integer`. Không được giả định `Long`/`Double` được làm tròn hoặc cắt ngầm về `int` vì đó là narrowing primitive conversion.

**Cần phân biệt source type tĩnh và runtime wrapper:** `Object -> int` là loại conversion được phép thiết lập vì tồn tại wrapper hợp lệ, nhưng từng giá trị cụ thể vẫn có thể thất bại.

## 6. Chuyển tham chiếu: reference casts và runtime type check

Nếu cả kiểu nguồn lẫn đích là reference, `asType` có thể thiết lập **reference cast**. Theo Javadoc, hai class không nhất thiết phải có quan hệ superclass/subclass tĩnh rõ ràng: `null` có thể chuyển thành bất kỳ reference type, còn giá trị không null phải vượt qua kiểm tra runtime.

Ví dụ lấy handle tới instance method `String.concat(String)`:

```java
MethodHandle concat = MethodHandles.lookup().findVirtual(
        String.class, "concat",
        MethodType.methodType(String.class, String.class));
```

Vì đây là virtual method, handle có **receiver làm tham số đầu**:

```text
(String,String)String
 receiver  arg    return
```

Chuyển thành:

```java
MethodHandle adapted = concat.asType(
        MethodType.methodType(
                Object.class, Object.class, Object.class));
```

Adapter nhận hai `Object` rồi cast chúng thành `String` trước khi gọi; kết quả `String` được mở rộng lên `Object`.

```java
Object joined = (Object) adapted.invokeExact(
        (Object) "Hello", (Object) " Java");
```

`joined.equals("Hello Java")` là `true`.

### 6.1. Reference cast không phải String conversion

Nếu tham số receiver thực tế là `Integer.valueOf(42)`, adapter vẫn có type `(Object,Object)Object` và vẫn được tạo thành công, nhưng lúc gọi sẽ ném `ClassCastException` vì `Integer` không phải `String`.

Không nhầm reference casting với việc tự động gọi `toString()` hoặc `String.valueOf()`. Muốn chuyển bất kỳ `Object` thành chuỗi, cần một adapter có filter gọi API chuyển đổi phù hợp, ví dụ `MethodHandles.filterArguments`/`filterReturnValue` hoặc code wrapper bên ngoài.

### 6.2. Instance method có receiver trong MethodType

Khi dùng `findVirtual`, `MethodType.methodType` cho lookup mô tả **tham số và return của method**, không đưa receiver vào danh sách signature trong lời gọi `findVirtual`. Nhưng `MethodHandle.type()` tạo ra có **receiver đứng đầu**.

Đây là nguồn lỗi arity phổ biến khi thích nghi `asType`:

- Phương thức Java `String.concat(String)` có một tham số tường minh.
- Method handle gọi nó cần **hai đối số**: receiver `String` và chuỗi thứ hai.
- Adapter mới cũng cần giữ số đối số tương ứng trong trường hợp fixed-arity `asType`.

Không cố gọi handle của virtual method chỉ với một parameter vì nghĩ receiver được tự động suy từ `Lookup`.

## 7. Giá trị trả về void: bỏ kết quả hoặc tạo giá trị mặc định

`asType` có quy tắc đặc biệt cho return type `void`.

| Kiểu trả gốc | Kiểu trả mới | Hành vi |
| --- | --- | --- |
| `int` hoặc reference | `void` | Thực thi target rồi **bỏ giá trị trả về** |
| `void` | Reference, ví dụ `Object` | Giới thiệu **`null`** làm kết quả |
| `void` | Primitive, ví dụ `int` | Giới thiệu **zero value** của primitive |
| `void` | `void` | Không thay đổi phần return |

Zero value bao gồm `0` cho số nguyên, `0.0` cho floating point, `false` cho `boolean`, `'\u0000'` cho `char`. Đây là quy tắc adaptation, **không** phải code target gốc đã tính ra những giá trị đó.

### 7.1. Ví dụ static method không có return

```java
public static void record(String event) {
    System.out.println("event=" + event);
}
```

Tạo handle `(String)void` và thích nghi thành `(String)int`:

```java
MethodHandle recorder = MethodHandles.lookup().findStatic(
        EventLog.class, "record",
        MethodType.methodType(void.class, String.class));

MethodHandle withZero = recorder.asType(
        MethodType.methodType(int.class, String.class));

int result = (int) withZero.invokeExact("created");
```

Đây là **ví dụ minh họa**, class `EventLog` do ứng dụng tự định nghĩa. Sau khi `record` chạy thành công, `result == 0`.

### 7.2. Biến return int thành void

Ngược lại:

```java
MethodHandle discard = addHandle.asType(
        MethodType.methodType(void.class, int.class, int.class));

discard.invokeExact(1, 2);
```

Vì call site là lời gọi **statement**, compiler dùng return type `void`. Hàm gốc vẫn tính tổng, nhưng giá trị `int` bị bỏ. Không coi đây là công cụ loại bỏ side effect hoặc tối ưu compiler bỏ qua target.

### 7.3. Không dùng void adaptation che giấu business error

Nếu target ném exception, adapter vẫn propagate exception đó. Việc chuyển return type thành `void` **chỉ bỏ kết quả thành công**, không biến lỗi thành kết quả `0` hay `null`. Muốn xử lý exception cần chính sách riêng, ví dụ exception handlers quanh invocation hoặc `MethodHandles.catchException` khi phù hợp.

## 8. asType và invokeExact: chữ ký phải khớp tuyệt đối

`invokeExact` **không tự áp dụng asType**. Nó yêu cầu descriptor của chính call site giống `handle.type()`, gồm:

- Số lượng tham số.
- Kiểu tĩnh từng tham số.
- Kiểu trả về mà compiler nhìn thấy qua cast/assignment/statement context.

Ví dụ adapter có `type()==(Integer,Integer)Object`:

```java
Object value = (Object) boxed.invokeExact(
        Integer.valueOf(5), Integer.valueOf(7));
```

Hợp lệ.

Nhưng:

```java
int value = (int) boxed.invokeExact(5, 7);
```

**Không hợp lệ tại runtime**: caller dùng `(int,int)int`, còn `boxed` là `(Integer,Integer)Object`. JVM ném `WrongMethodTypeException` ngay khi descriptor không khớp.

Đây là điều rất dễ nhầm: **adapter có khả năng boxing không có nghĩa `invokeExact` được phép tự boxing từ chữ ký bất kỳ**. Muốn exact-call thành công, hãy truyền đúng kiểu của **adapter**, không phải kiểu của target gốc.

### 8.1. Kiểu trả về của call site là phần của chữ ký

`(int,int)int` và `(int,int)long` **khác nhau** dù hai tham số giống nhau.

Ví dụ:

```java
MethodHandle mh = addHandle; // (int,int)int

int ok = (int) mh.invokeExact(3, 4);

// Sai: call site yêu cầu long nhưng mh trả int.
long wrong = (long) mh.invokeExact(3, 4);
```

Đây là đoạn minh họa có **lời gọi thứ hai cố tình ném WrongMethodTypeException**. Cast `(long)` trên call expression không có nghĩa compiler phát sinh một invocation trả `int` rồi widen bình thường; đối với signature-polymorphic invocation, cast quyết định descriptor của call site.

Đúng:

```java
MethodHandle longResult = mh.asType(
        MethodType.methodType(long.class, int.class, int.class));
long okLong = (long) longResult.invokeExact(3, 4);
```

### 8.2. Lời gọi statement có return type void

Nếu viết `mh.invokeExact(3,4);` như một statement, call site thông thường dùng return type `void`. Nếu `mh` đang có return type `int`, exact invocation sẽ mismatch.

Muốn chỉ gọi để lấy side effect, dùng adapter `asType` có return type `void`, hoặc nhận đúng kiểu `int` rồi bỏ biến kết quả trong code Java.

### 8.3. invoke không yêu cầu khớp exact

`invoke` có semantics linh hoạt hơn: nếu call site khác type của handle, runtime có thể **thích nghi như gọi asType** với descriptor call site rồi thực thi.

```java
Object answer = (Object) addHandle.invoke(
        Integer.valueOf(3), Integer.valueOf(8));
```

Call site là `(Integer,Integer)Object`. Target `addHandle` là `(int,int)int`, nhưng `invoke` có thể thích nghi unbox hai `Integer` rồi box kết quả `int` thành `Object`. Kết quả là `Integer(11)`.

### 8.4. Vì sao vẫn dùng asType tường minh?

`invoke` có thể thuận tiện nhưng `asType` đem lại các lợi ích:

- Định nghĩa chữ ký contract **một lần** ở ranh giới API.
- Kiểm tra tính chuyển đổi có thể thực hiện **khi xây adapter** thay vì đợi một call site sau này.
- Sử dụng `invokeExact` với adapter đã có type phù hợp.
- Dễ debug/log `adapter.type()` và unit test riêng từng chuyển đổi.
- Có thể tái sử dụng adapter cho nhiều lời gọi cùng descriptor.
- Hạn chế việc các call site tự áp dụng conversion khác nhau ngoài ý muốn.

Không được bảo đảm `asType` luôn nhanh hơn `invoke` trong mọi workload; JIT có các tối ưu khác nhau. Chọn theo tính rõ ràng, độ an toàn và benchmark trên workload thật khi hiệu năng có ý nghĩa.

### 8.5. invokeWithArguments khác nữa

`invokeWithArguments(Object...)` nhận một danh sách arguments dạng Object và dùng conversions tương tự inexact invocation (cùng các quy tắc varargs khi liên quan). Nó tiện trong công cụ động nhưng có nhiều boxing và runtime checks hơn, nên không nên mặc định dùng cho hot path khi đã biết MethodType chính xác.

Không coi `invokeWithArguments` là cách tự tránh mọi `WrongMethodTypeException`: sai số đối số hay conversion không thể thực hiện vẫn có thể thất bại.

## 9. Những lỗi có thể gặp ở ba giai đoạn

| Giai đoạn | Điều kiện | Lỗi thông thường |
| --- | --- | --- |
| Tìm handle | Không tìm thấy method hoặc thiếu quyền access | `NoSuchMethodException` / `IllegalAccessException` |
| Tạo adapter `asType(newType)` | `newType == null` | `NullPointerException` |
| Tạo adapter | Khác arity khi fixed-arity hoặc conversion không thể thiết lập | `WrongMethodTypeException` |
| Gọi `invokeExact` | Descriptor call site không đúng `adapter.type()` | `WrongMethodTypeException` |
| Gọi adapter | Reference object thực tế không thể cast sang target reference | `ClassCastException` |
| Gọi adapter | Wrapper thực tế không thể unbox/widen thành primitive cần thiết | `ClassCastException` |
| Gọi adapter | `null` được unbox thành primitive | `NullPointerException` |
| Gọi target | Target method ném lỗi nghiệp vụ/overflow/IO | Target exception được propagate theo handle contract |

**Không bắt mọi lỗi thành một kiểu duy nhất.** Việc adapter creation thành công có nghĩa **type-level conversion khả thi**, không cam kết mọi runtime object đều có giá trị tương thích.

### 9.1. WrongMethodTypeException khi khác số tham số

Với target fixed arity `(int,int)int`:

```java
MethodType oneArg = MethodType.methodType(
        int.class, int.class);
addHandle.asType(oneArg);
```

Không thể tự bỏ một tham số bằng asType. Nó ném `WrongMethodTypeException`.

Muốn thêm/bỏ/đổi vị trí các tham số, dùng đúng combinator khác (`dropArguments`, `insertArguments`, `permuteArguments`...) nếu bài toán tương ứng và có logic minh bạch.

### 9.2. WrongMethodTypeException khi primitive narrowing

`long -> int` trong tham số target `int` không được phép bằng `asType`. Lỗi xảy ra khi xây adapter, không đợi giá trị `long` cụ thể có nằm trong range `int` hay không.

Vì vậy ngay cả `1L` (vừa range int) cũng không tự làm conversion type-level đó hợp lệ.

### 9.3. ClassCastException khi đổi reference

`Object -> String` có thể tạo adapter vì một giá trị `Object` thực tế **có thể là String**. Nhưng nếu runtime object là `Integer`, cast thất bại.

### 9.4. NullPointerException khi unboxing

`Object -> int` là conversion có thể thiết lập nếu runtime object là một wrapper phù hợp. Nhưng nếu `Object` thực là null, unboxing thất bại. Phải validate null trước hoặc thiết kế input wrapper contract rõ.

## 10. So sánh asType với những combinator liên quan

| API | Thay đổi chính | Khi nào dùng |
| --- | --- | --- |
| `MethodHandle.asType(newType)` | Chuyển kiểu từng tham số và return theo quy tắc asType | Cùng hình dạng argument list, cần coercion hợp lệ |
| `MethodHandles.explicitCastArguments(target,newType)` | Cho phép Java cast conversions rộng hơn, gồm primitive narrowing và một số conversion đặc biệt | Cần cast tường minh với chính sách mất dữ liệu rõ |
| `MethodHandle.asSpreader(arrayType,n)` | Thay n tham số cuối bằng một mảng và trải chúng ra khi gọi | Caller có array, target cần nhiều vị trí |
| `MethodHandle.asCollector(arrayType,n)` | Gom n tham số cuối thành một mảng để gọi target | Caller có nhiều vị trí, target nhận array |
| `MethodHandles.filterArguments(target,pos,filters...)` | Chèn biến đổi dữ liệu đầu vào bằng các filter handles | Cần parse/validate/normalize tùy ý |
| `MethodHandles.filterReturnValue(target,filter)` | Biến đổi kết quả của target qua một handle thứ hai | Cần mapping tùy ý cho result |
| `MethodHandles.permuteArguments(target,newType,reorder...)` | Đổi thứ tự hoặc tái sử dụng đối số theo mapping | Thay thứ tự tham số, không chỉ đổi kiểu |
| `MethodHandles.dropArguments(target,pos,types...)` | Adapter nhận thêm đối số sẽ bị bỏ qua | Caller có extra context mà target không cần |
| `MethodHandles.insertArguments(target,pos,values...)` | Đóng băng một số tham số thành giá trị cố định | Partial application |
| `MethodHandle.bindTo(receiver)` | Gắn receiver/reference đầu vào | Tạo handle có receiver đã được chọn |

**asType không tự parse `String` thành `int`.** Nếu đây là yêu cầu, cần một filter handle gọi `Integer.parseInt` (có thể ném `NumberFormatException`) trước khi chuyển tới target.

**asType không tự thay số tham số** của fixed-arity handle. Nếu muốn callable nhận một `Object[]` thay vì hai `Object` riêng, `asSpreader` hoặc một adapter thiết kế cụ thể là công cụ phù hợp.

### 10.1. explicitCastArguments có narrowing nhưng không “tự an toàn”

`MethodHandles.explicitCastArguments` có thể thực hiện những chuyển đổi theo Java casting conversion bao gồm primitive narrowing, khác với `asType` vốn chỉ widening ở cặp primitive.

Ví dụ ý tưởng:

```java
MethodHandle narrowed = MethodHandles.explicitCastArguments(
        addHandle,
        MethodType.methodType(
                int.class, long.class, int.class));
```

Đây là đoạn minh họa nằm trong method phù hợp. Nếu thực thi với tham số `long` lớn, việc ép về `int` có thể **mất bit/cắt giá trị** theo semantics cast.

Không dùng chỉ để “vượt qua WrongMethodTypeException” nếu dữ liệu nghiệp vụ không cho phép narrowing. Với ID tài khoản, số tiền hoặc đếm lớn, hãy kiểm tra range và ném lỗi rõ ràng.

### 10.2. Khi cần parse string, dùng filter

Một pipeline động có thể cần `String -> int`, nhưng đó **không phải asType conversion hợp lệ**. Một hướng thiết kế:

```text
String argument
      |
      v
Integer.parseInt(String)   -- có thể NumberFormatException
      |
      v
int argument
      |
      v
target add(int,int)
```

Cần tạo handle đến `Integer.parseInt` và kết hợp `filterArguments`, giữ conversion rõ và test lỗi parse. Điều này khác với tự động boxing/unboxing có sẵn.

### 10.3. Varargs collectors là ngoại lệ nâng cao

Javadoc `asType` có **quy tắc đặc biệt cho variable-arity method handles**: khi adapter của varargs collector đổi arity hoặc trailing argument type, việc thu gom vào mảng có thể được thực hiện theo semantics varargs collector trước khi áp dụng conversions.

Đừng suy từ ngoại lệ này rằng `asType` của **mọi fixed-arity handle** có thể thay đổi số đối số. Trong bài thực hành, handle đến `add(int,int)` là **fixed arity**, vì vậy khác arity bị từ chối.

Để giữ/đặt lại trạng thái variable arity trong các adapter hiện đại, Java còn có `withVarargs(boolean)` (Java 9+); chỉ dùng nếu thực sự triển khai varargs handle và hiểu hợp đồng của nó. Tất cả API này vẫn hiện hành, nhưng không cần dùng để giải bài toán `add` cố định.

## 11. Chương trình Java 17 đã biên dịch và chạy thành công

Tạo file **`MethodHandleAsTypeDemo.java`**. Bài test gồm:

1. Tìm handle gốc `(int,int)int` và xác minh `asType` cùng type trả lại chính handle đó.
2. Tạo adapter `(short,byte)long`, truyền 12 và 4, nhận 16.
3. Tạo adapter `(Integer,Integer)Object`, unbox hai đối số rồi box result 12.
4. Tạo adapter `(Object,Object)Object`, gọi với hai `Integer`, nhận 11.
5. Dùng `invoke` trên original để cho thấy implicit asType.
6. Gọi `invokeExact` với descriptor sai và bắt `WrongMethodTypeException`.
7. Thử `asType` khác số tham số và primitive narrowing, cả hai bị từ chối.
8. Gọi adapter Object với null (unboxing NPE) và String sai kiểu (CCE).
9. Tạo handle cho `String.concat`, thích nghi reference casts và bắt CCE khi receiver sai kiểu.
10. Thử adapter `void -> int` trả zero, `void -> Object` trả null; xác minh target đã chạy hai lần.
11. Thử adapter `int -> void` để bỏ kết quả.
12. Xác nhận original handle vẫn không đổi.

Phần lớn output của demo **không phụ thuộc scheduler**. Mỗi assertion kiểm tra một hợp đồng riêng; phương thức tạo adapter **không được giả định** thực thi target cho tới khi được invoke.

### 11.1. Toàn bộ mã nguồn: MethodHandleAsTypeDemo.java

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.Objects;

public final class MethodHandleAsTypeDemo {
    private static int events;

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static void record(String event) {
        if (!event.isEmpty()) events++;
    }

    private static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle original = lookup.findStatic(
                MethodHandleAsTypeDemo.class, "add",
                MethodType.methodType(int.class, int.class, int.class));
        check("(int,int)int".equals(original.type().toString()),
                "Original descriptor");
        check(original.asType(original.type()) == original,
                "Same type must return original handle");
        System.out.println("original type = " + original.type());

        MethodHandle widened = original.asType(
                MethodType.methodType(long.class, short.class, byte.class));
        long widenedResult = (long) widened.invokeExact(
                (short) 12, (byte) 4);
        check(widenedResult == 16L, "primitive widening");
        System.out.println("widened type = " + widened.type());
        System.out.println("widened result = " + widenedResult);

        MethodHandle boxed = original.asType(
                MethodType.methodType(Object.class,
                        Integer.class, Integer.class));
        Object boxedResult = (Object) boxed.invokeExact(
                Integer.valueOf(5), Integer.valueOf(7));
        check(Objects.equals(boxedResult, Integer.valueOf(12)),
                "unbox args and box return");
        System.out.println("boxed type = " + boxed.type());
        System.out.println("boxed result = " + boxedResult);

        MethodHandle generic = original.asType(
                MethodType.methodType(Object.class,
                        Object.class, Object.class));
        Object genericResult = (Object) generic.invokeExact(
                (Object) Integer.valueOf(9),
                (Object) Integer.valueOf(2));
        check(Objects.equals(genericResult, Integer.valueOf(11)),
                "generic reference adapter");
        System.out.println("generic result = " + genericResult);

        Object invoked = (Object) original.invoke(
                Integer.valueOf(3), Integer.valueOf(8));
        check(Objects.equals(invoked, Integer.valueOf(11)),
                "invoke implicit asType");
        System.out.println("inexact invoke result = " + invoked);

        boolean exactRejected = false;
        try {
            int unused = (int) boxed.invokeExact(1, 2);
            check(unused == -1, "unreachable");
        } catch (WrongMethodTypeException expected) {
            exactRejected = true;
        }
        check(exactRejected, "invokeExact descriptor mismatch");
        System.out.println("invokeExact mismatch rejected = true");

        boolean arityRejected = false;
        try {
            original.asType(MethodType.methodType(int.class, int.class));
        } catch (WrongMethodTypeException expected) {
            arityRejected = true;
        }
        check(arityRejected, "wrong arity must be rejected");
        System.out.println("different arity rejected = true");

        boolean narrowingRejected = false;
        try {
            original.asType(MethodType.methodType(
                    int.class, long.class, int.class));
        } catch (WrongMethodTypeException expected) {
            narrowingRejected = true;
        }
        check(narrowingRejected, "long to int narrowing forbidden");
        System.out.println("primitive narrowing rejected = true");

        boolean nullRejected = false;
        try {
            Object bad = null;
            Object good = Integer.valueOf(2);
            Object unused = (Object) generic.invokeExact(bad, good);
            check(unused == null, "unreachable");
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        check(nullRejected, "null unboxing must fail");
        System.out.println("null unboxing rejected = true");

        boolean castRejected = false;
        try {
            Object bad = "not-an-int";
            Object good = Integer.valueOf(2);
            Object unused = (Object) generic.invokeExact(bad, good);
            check(unused == null, "unreachable");
        } catch (ClassCastException expected) {
            castRejected = true;
        }
        check(castRejected, "bad wrapper must fail");
        System.out.println("wrong wrapper rejected = true");

        MethodHandle concat = lookup.findVirtual(
                String.class, "concat",
                MethodType.methodType(String.class, String.class));
        MethodHandle refAdapted = concat.asType(
                MethodType.methodType(Object.class,
                        Object.class, Object.class));
        Object joined = (Object) refAdapted.invokeExact(
                (Object) "Hello", (Object) " Java");
        check("Hello Java".equals(joined), "reference casting success");
        boolean referenceRejected = false;
        try {
            Object invalidReceiver = Integer.valueOf(42);
            Object other = " Java";
            Object unused = (Object) refAdapted.invokeExact(
                    invalidReceiver, other);
            check(unused == null, "unreachable");
        } catch (ClassCastException expected) {
            referenceRejected = true;
        }
        check(referenceRejected, "invalid reference cast");
        System.out.println(
                "reference cast = Hello Java; bad cast rejected = true");

        MethodHandle recorder = lookup.findStatic(
                MethodHandleAsTypeDemo.class, "record",
                MethodType.methodType(void.class, String.class));
        MethodHandle returnsZero = recorder.asType(
                MethodType.methodType(int.class, String.class));
        int zero = (int) returnsZero.invokeExact("first");
        MethodHandle returnsNull = recorder.asType(
                MethodType.methodType(Object.class, String.class));
        Object missing = (Object) returnsNull.invokeExact("second");
        check(zero == 0 && missing == null && events == 2,
                "void adapts to zero/null");
        System.out.println("void to int = " + zero
                + "; void to Object null = " + (missing == null));

        MethodHandle discardReturn = original.asType(
                MethodType.methodType(void.class, int.class, int.class));
        discardReturn.invokeExact(1, 2);
        System.out.println(
                "discard return type = " + discardReturn.type());

        check("(int,int)int".equals(original.type().toString()),
                "original handle must be preserved");
        System.out.println("original unchanged = true");
        System.out.println("checks = PASS");
    }
}
```

### 11.2. Biên dịch và chạy

Lưu đúng tên file và chạy **JDK 17+**:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 MethodHandleAsTypeDemo.java
java MethodHandleAsTypeDemo
```

Chương trình đã **biên dịch với strict warnings-as-errors và chạy trên JDK 17**. Stdout chính xác **17 dòng**:

```text
original type = (int,int)int
widened type = (short,byte)long
widened result = 16
boxed type = (Integer,Integer)Object
boxed result = 12
generic result = 11
inexact invoke result = 11
invokeExact mismatch rejected = true
different arity rejected = true
primitive narrowing rejected = true
null unboxing rejected = true
wrong wrapper rejected = true
reference cast = Hello Java; bad cast rejected = true
void to int = 0; void to Object null = true
discard return type = (int,int)void
original unchanged = true
checks = PASS
```

Dòng `original unchanged = true` là assertion cuối: mọi `asType` trước đó không sửa descriptor gốc.

### 11.3. Vì sao phần main khai báo throws Throwable?

`MethodHandle.invokeExact` và `invoke` được khai báo có thể ném `Throwable`, không giới hạn ở các checked exceptions mà phương thức gốc khai báo. Demo để `main(String[]) throws Throwable` nhằm tập trung vào adaptation thay vì dựng hierarchy xử lý exception.

Trong production, nên **khoanh vùng** lời gọi MethodHandle và xử lý/propagate exception theo contract cụ thể của service, tránh bắt mọi `Throwable` rồi nuốt mất lỗi nghiêm trọng.

### 11.4. Tại sao dùng MethodHandles.lookup ngay trong class?

`Lookup` gắn với caller context và quyền truy cập. Trong demo, `MethodHandleAsTypeDemo` có quyền truy cập static methods của chính class. Code không cần `setAccessible(true)` hoặc bất kỳ API nội bộ nào.

Nếu đang xây plugin system, chỉ cung cấp handles có capability phù hợp; một handle đã được tạo có thể mang quyền gọi target method, và `asType` không tự giảm quyền truy cập đó.

### 11.5. Vì sao test exactRejected dùng int dù adapter trả Object?

Đó chính là lỗi cần tái hiện: caller yêu cầu `(int,int)int` nhưng adapter có `(Integer,Integer)Object`, nên `invokeExact` ném `WrongMethodTypeException`. Code `check(unused == -1, "unreachable")` chỉ là guard nếu một JVM giả định không đúng đi qua nhánh đáng lẽ không thể hoàn tất bình thường.

Bản test này tránh phụ thuộc vào text chi tiết của exception message, vốn có thể thay đổi theo JDK/vendor.

### 11.6. Tại sao null và wrong wrapper được test bằng adapter generic?

Adapter `(Object,Object)Object` được tạo hợp lệ trên target `(int,int)int`. Bởi vậy:

- Null không unbox được thành int → `NullPointerException`.
- String không unbox được thành int → `ClassCastException`.

Hai lỗi xảy ra **khi thực thi**, không phải lúc `asType` được gọi. Điều này minh họa chính xác ranh giới type-level và value-level.

### 11.7. Vì sao return void tạo 0/null?

`record(String)` trả `void` nhưng adapter có return `int` và `Object`. Java không gọi target thêm lần nào chỉ để có giá trị mặc định: sau mỗi lần target chạy, adapter tạo 0 hoặc null theo quy tắc `asType`. Biến `events==2` chứng minh mỗi invocation thực sự đã gọi target.

### 11.8. Khi cần kiểm tra overflow của target

`add` của demo sử dụng `Math.addExact`: nếu phép cộng int bị overflow, nó có thể ném `ArithmeticException` từ target. `asType` không ngăn điều đó. Adapter `(short,byte)long` chỉ widen kết quả **sau khi `add(int,int)` đã tính bằng int**; việc chọn return type `long` không tự làm phép cộng gốc thành phép cộng long.

Nếu bài toán cần cộng hai số lớn an toàn, thay **target algorithm/signature** để dùng `long` hoặc kiểu phù hợp; asType không sửa implementation của hàm đích.

## 12. Áp dụng trong dự án

### 12.1. Dynamic API dispatcher

Một dispatcher có thể muốn mọi handler có chữ ký chung:

```text
(Object,Object)Object
```

Trong khi một handler thực có:

```text
(int,int)int
```

Sau khi tra cứu handle với đúng quyền truy cập:

```java
MethodHandle bridge = handler.asType(
        MethodType.methodType(
                Object.class, Object.class, Object.class));
```

Đây là đoạn minh họa với `handler` được tạo trước và đã có cùng số tham số. Dispatcher chỉ nên truyền các runtime objects phù hợp (ví dụ `Integer`), và phải kiểm tra/validate input, báo lỗi có ngữ cảnh nếu nhận `String` hoặc `null` không hợp lệ.

**Không gọi mọi input lỗi là “MethodHandle bị hỏng”**: adapter có thể đúng, còn dữ liệu caller không thỏa contract.

### 12.2. Tái sử dụng adapter thay vì chuyển mỗi lần

Nếu cùng một handler được gọi hàng triệu lần theo cùng descriptor, thường hợp lý tạo adapter một lần:

```java
MethodHandle typedHandler = original.asType(expectedMethodType);

// Lặp hot path:
// Gọi typedHandler theo đúng expectedMethodType đã xác định.
```

Đây là khung ý tưởng không độc lập. MethodHandle immutable nên có thể được tái sử dụng, miễn target, input và shared state của ứng dụng tuân theo thread-safety riêng.

Đừng đặt `asType` trong mỗi vòng lặp chỉ vì tiện, rồi giả định JVM sẽ luôn tối ưu mọi adapter creation. Trước khi tối ưu microperformance, đo thực tế bằng JMH hoặc workload benchmark chuẩn.

### 12.3. API boundary và schema validation

Nếu schema ngoài được đọc động từ JSON hoặc record của người dùng, một adapter `Object -> int` sẽ ném `ClassCastException` hoặc `NullPointerException` khi object không hợp lệ. Trong API public, có thể tốt hơn:

1. Validate schema/value ở tầng input.
2. Chuyển dữ liệu có thông báo lỗi rõ (ví dụ số nguyên nằm trong range).
3. Sử dụng adapter có descriptor chính xác.
4. Chỉ expose thông tin exception phù hợp, không làm rò chi tiết class nội bộ hay quyền truy cập.

Đối với `String` dạng `"42"`, hãy parse rõ ràng, không hy vọng asType tự đọc chữ số.

### 12.4. Adapter không giải quyết variance tuỳ ý của generic collections

`MethodType` lưu `Class<?>` ở runtime, không lưu đầy đủ generic arguments như `List<String>` so với `List<Integer>`. `asType` không thể runtime-enforce mọi generic element type vốn bị type erasure.

Nếu interface nghiệp vụ cần danh sách các DTO cụ thể, validation/serialization/schema phải được thực hiện riêng. Không coi thành công của reference cast `List -> List` là bằng chứng mọi phần tử đều đúng kiểu.

### 12.5. An toàn quyền truy cập

`MethodHandles.Lookup` kiểm tra khả năng truy cập khi tạo handle. Một `MethodHandle` đã được chuyển tới module/plugin khác có thể mang quyền gọi một method vốn không công khai cho plugin đó.

`asType` chỉ thay đổi cách gọi, **không** tự thu hồi capability. Không trao handle đến private/sensitive methods cho untrusted code nếu method đó có tác dụng không mong muốn. Cần kiểm soát authorization tại boundary tạo/chia sẻ handle.

### 12.6. Exception contract ở plugin dispatch

Một target có thể ném `IOException`, `SQLException` hoặc runtime exceptions. `invokeExact` khai báo `throws Throwable`; adapter `asType` không biến chúng thành một lỗi thống nhất.

Đặt chính sách xử lý riêng:

- Lỗi adaptation cấu hình → báo sai descriptor khi build.
- Lỗi runtime value → validate input và báo conversion failure.
- Lỗi target → propagate/wrap theo API của ứng dụng và bảo toàn cause.
- Lỗi access lookup → cấu hình/authorization.
- Lỗi của JVM nghiêm trọng → không nuốt trong catch rộng.

## 13. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng `asType` sửa handle gốc | MethodHandle immutable | Giữ biến adapter riêng |
| Tưởng `asType` gọi luôn target | Chỉ tạo handle mới | Invoke adapter khi cần |
| Nghĩ mọi kiểu chuyển qua lại được | Chỉ conversions có trong hợp đồng | Kiểm tra từng cặp kiểu |
| Cố `long -> int` bằng asType | Primitive narrowing không cho phép | Chọn target long, range check hoặc explicit cast có chủ đích |
| Nghĩ `int -> String` tự tạo chuỗi | Không parse/toString implicit | Dùng filter/converter rõ ràng |
| Nghĩ `String "42" -> int` hợp lệ | Không có parse tự động | `Integer.parseInt` qua tầng riêng |
| Nhầm boxing int → Long | Boxing gắn wrapper của primitive | Chuyển qua long đúng cách |
| Không test null khi unboxing | Null không thành primitive | Validate non-null |
| Nhầm `ClassCastException` với `WrongMethodTypeException` | Khác value-level và type-level | Phân loại đúng thời điểm |
| Gọi `invokeExact` bằng primitive trên adapter wrapper | Exact-call không tự boxing | Dùng đúng adapter descriptor |
| Quên cast return của `invokeExact` | Call site có return type khác | Cast/assignment đúng kiểu |
| Chỉ so tham số, bỏ return type | Return nằm trong MethodType | So đủ descriptor |
| Gọi instance handle mà quên receiver | Receiver nằm ở tham số đầu của handle | Đọc `handle.type()` |
| Cố thêm một argument qua fixed asType | Không đổi arity như vậy | Dùng `dropArguments`/`insertArguments` phù hợp |
| Cố đổi thứ tự tham số qua asType | asType là pairwise conversion | Dùng `permuteArguments` |
| Dùng `invokeWithArguments` mọi lúc | Dynamic varargs/boxing, không tối ưu cho typed path | Reuse typed adapter và `invokeExact` |
| Coi `invoke` với `invokeExact` là một | invoke có implicit adaptation | Chọn theo hợp đồng call site |
| Coi widening primitive giữ chính xác mọi số | float/double có giới hạn precision | Chọn representation phù hợp |
| Nghĩ adapter long return làm target cộng int thành long | Target vẫn chạy bằng int | Đổi thuật toán/target khi cần |
| Dùng `explicitCastArguments` không xét overflow | Narrowing có thể mất dữ liệu | Range-check và test giới hạn |
| Test một giá trị hợp lệ rồi kết luận mọi Object hợp lệ | Reference cast/unboxing có runtime checks | Test null, bad type, good type |
| So identity mọi adapter đã cùng newType | Không hứa cache adapter khác type gốc | Chỉ assert `type().equals` |
| Không tách error của lookup và asType | NoSuchMethod/Access khác WrongMethodType | Phân loại lỗi theo giai đoạn |
| Lạm dụng private reflection để tạo handle | Vi phạm module/access contract | Lookup với quyền hợp lệ |
| Trao sensitive handle cho plugin không tin cậy | Handle mang capability | Kiểm soát authorization |
| Benchmark một lần và nói asType luôn nhanh | JIT/profile ảnh hưởng | Dùng benchmark phù hợp |
| Bỏ qua side effects khi đổi return thành void | Target vẫn chạy | Test side effects và exceptions |
| Dùng generic Object adapter cho dữ liệu typed đã biết | Giảm static clarity, tăng runtime failures | Chọn MethodType cụ thể |

## 14. Bài tập có đáp án

### Bài 1 — Xác định MethodType

Phương thức `static int sum(int a,int b)` tạo `MethodHandle` với type gì?

**Đáp án:** `(int,int)int`.

### Bài 2 — Hướng conversion

Khi `asType` từ handle gốc `(int,int)int` sang `(short,byte)long`, đầu vào chuyển theo hướng nào?

**Đáp án:** `short->int`, `byte->int`, kết quả `int->long`.

### Bài 3 — Có sửa handle gốc không?

`MethodHandle b = a.asType(newType)` làm `a.type()` đổi theo không?

**Đáp án:** Không. `a` immutable; `b.type()` có newType nếu adaptation thành công.

### Bài 4 — Cùng type

`a.asType(a.type()) == a` có đúng không?

**Đáp án:** Đúng theo Javadoc: nếu type giống nhau, trả `this`.

### Bài 5 — Primitive widening

`(int)void` target có tham số `int`; có thể chuyển adapter nhận `short` cho tham số đó không?

**Đáp án:** Có, vì `short->int` widening. Số lượng tham số vẫn phải phù hợp.

### Bài 6 — Narrowing

`(int)int` target nhận `int`; adapter muốn nhận `long` có thành công qua asType không?

**Đáp án:** Không. `long->int` narrowing, bị `WrongMethodTypeException` khi tạo adapter.

### Bài 7 — Box return

Target trả `int`, adapter muốn trả `Object`. Giá trị nhận sẽ có runtime class nào với kết quả `12`?

**Đáp án:** `Integer` được boxing từ `int`, sau đó nhìn dưới type `Object`.

### Bài 8 — Unbox arguments

Adapter `(Integer,Integer)Object` tới target `(int,int)int` có gọi được với hai `Integer` hợp lệ không?

**Đáp án:** Có; unboxing hai đối số và boxing kết quả.

### Bài 9 — Null wrapper

Adapter `(Object,Object)Object` tới target `(int,int)int` nhận đối số đầu `null`. Lỗi gì?

**Đáp án:** `NullPointerException` khi unbox null thành int.

### Bài 10 — String wrapper

Adapter `(Object,Object)Object` nhận `"123"` và `Integer(2)`. Có tự parse string không?

**Đáp án:** Không. `String` không thể unbox int; `ClassCastException` có thể xảy ra ở runtime.

### Bài 11 — Tham chiếu

Adapter cho `String.concat` chấp nhận receiver `Object` thực sự chứa `String`. Có được không?

**Đáp án:** Được; reference cast tới `String` thành công.

### Bài 12 — Receiver sai

Nếu receiver `Object` thực tế là `Integer` khi gọi `String.concat` adapter, lỗi gì?

**Đáp án:** `ClassCastException` vì receiver không phải `String`.

### Bài 13 — Void sang int

Target trả `void`, adapter trả `int`. Khi target hoàn tất thành công, adapter trả gì?

**Đáp án:** Zero value `0` của `int`.

### Bài 14 — Void sang Object

Target trả `void`, adapter trả `Object`. Kết quả?

**Đáp án:** `null`.

### Bài 15 — Int sang void

Target trả `int`, adapter trả `void`. Target có còn chạy không?

**Đáp án:** Vẫn chạy; chỉ bỏ giá trị trả, side effects/exceptions vẫn tồn tại.

### Bài 16 — Arity

Fixed-arity handle `(int,int)int` thích nghi thành `(int)int` chỉ với asType được không?

**Đáp án:** Không. Sai số tham số, ném `WrongMethodTypeException`.

### Bài 17 — invokeExact

Adapter có type `(Integer,Integer)Object`. Lời gọi `(int)adapter.invokeExact(1,2)` có đúng không?

**Đáp án:** Không; call site `(int,int)int` mismatch, `WrongMethodTypeException`.

### Bài 18 — invoke

`(Object)addHandle.invoke(Integer.valueOf(3),Integer.valueOf(8))` có thể thành công không?

**Đáp án:** Có; `invoke` thích nghi như `asType` nếu conversion hợp lệ, kết quả `Integer(11)` nhìn dưới Object.

### Bài 19 — Result call site

`(long)addHandle.invokeExact(1,2)` trong khi original type là `(int,int)int` có đúng không?

**Đáp án:** Không. Cast `(long)` làm return descriptor của call site là long, nên mismatch. Tạo adapter `(int,int)long` rồi exact-invoke.

### Bài 20 — Float precision

`int -> float` là widening nhưng có thể mất exact numeric precision không?

**Đáp án:** Có. Widening về type không đảm bảo giá trị nguyên lớn được biểu diễn chính xác trong floating point.

### Bài 21 — Parse String

Để nhận `String "12"` và đưa vào target cần int, chọn `asType` hay filter gọi `Integer.parseInt`?

**Đáp án:** Filter/conversion tường minh; `asType` không tự parse chuỗi.

### Bài 22 — explicitCastArguments

Khi nào nên dùng `MethodHandles.explicitCastArguments` thay asType?

**Đáp án:** Khi **cố ý** cần Java cast conversion rộng hơn, như primitive narrowing, đã xem xét rủi ro mất giá trị và kiểm tra range.

### Bài 23 — Chuyển số đối số

Muốn đổi từ hai đối số riêng sang một `Object[]`, asType fixed arity có tự biến đổi không?

**Đáp án:** Không. Xem `asSpreader` hoặc wrapper/combinator phù hợp.

### Bài 24 — Side effect

Tạo adapter bằng asType có làm target static method chạy một lần không?

**Đáp án:** Không. Chỉ khi invocation xảy ra.

### Bài 25 — Exception timing

Lỗi `WrongMethodTypeException` khi tạo adapter khác `ClassCastException` khi invoke ở điểm nào?

**Đáp án:** WrongMethodType nghĩa descriptor không có conversion hợp lệ; ClassCast nghĩa descriptor có thể thích nghi nhưng runtime reference cụ thể không đạt.

### Bài 26 — Type access

Một plugin nhận handle tới private method rồi gọi `asType`. `asType` có tự tước quyền gọi private method không?

**Đáp án:** Không. Quyền/capability đã nằm trong handle được tạo bằng Lookup hợp lệ; phải kiểm soát việc phân phát handle.

### Bài 27 — Hiệu năng

Có thể kết luận `asType + invokeExact` nhanh hơn `invoke` trong mọi điều kiện mà không đo không?

**Đáp án:** Không. JIT, call-site profile, warmup và workload ảnh hưởng; chọn adapter vì contract rõ và benchmark khi cần.

## 15. Checklist thực hành

- [ ] Nắm chính xác type của handle gốc qua `handle.type()`.
- [ ] Tạo `MethodType.methodType(returnType, parameterTypes...)` đúng thứ tự.
- [ ] Xác định conversion **tham số mới -> tham số cũ**.
- [ ] Xác định conversion **return cũ -> return mới**.
- [ ] Với primitive, chỉ dùng widening hợp lệ trong `asType`.
- [ ] Không tự narrowing `long -> int` hoặc `double -> float`.
- [ ] Hiểu boxing primitive -> wrapper tương ứng -> reference widening.
- [ ] Hiểu unboxing wrapper/reference -> primitive có runtime checks.
- [ ] Kiểm thử `null` và wrapper sai kiểu khi adapter nhận reference.
- [ ] Không mong `String` tự parse thành số hoặc Object tự `toString`.
- [ ] Khi `void` đổi sang primitive/reference, xác định zero/null result.
- [ ] Khi đổi return sang `void`, hiểu target vẫn thực thi.
- [ ] Kiểm tra `adapter.type().equals(expectedType)`.
- [ ] Không sửa/ghi đè handle gốc khi cần giữ original signature.
- [ ] Khi `invokeExact`, đối số và return descriptor phải khớp adapter.
- [ ] Kiểm tra cả return type trong context/cast của call site.
- [ ] Với `invoke`, hiểu có implicit asType nếu descriptor lệch.
- [ ] Với fixed-arity handles, không dùng asType để đổi số arguments.
- [ ] Với virtual handle, nhớ tham số receiver ở đầu.
- [ ] Dùng `explicitCastArguments` chỉ nếu đã chủ đích chấp nhận narrowing.
- [ ] Dùng filter/combinators nếu cần parse, thay đổi arity hoặc permutation.
- [ ] Tách WrongMethodType/CCE/NPE/target exceptions trong test.
- [ ] Cache/reuse adapters theo hợp đồng, không phụ thuộc JVM internals.
- [ ] Không chia sẻ method handle có quyền gọi sensitive code cho untrusted plugin.
- [ ] Không dùng `asType` như cơ chế validate business schema đầy đủ.
- [ ] Test ví dụ bằng `javac --release 17 -Xlint:all -Werror` và đúng output.
- [ ] Đọc đúng Oracle Javadoc và giữ API vẫn còn hiện hành.

## 16. Tài liệu chính thức

- [Oracle Java SE 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `asType`, `invokeExact`, `invoke`, pairwise conversions, void return, lỗi có thể gặp.
- [Oracle Java SE 17 — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): mô tả MethodType và tạo descriptor.
- [Oracle Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `Lookup`, `explicitCastArguments`, `filterArguments`, `permuteArguments`, `dropArguments`.
- [Oracle Java SE 17 — WrongMethodTypeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): lỗi descriptor không phù hợp.
- [Java Language Specification SE 17 `5.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3): method invocation conversions và primitive widening.
- [Java Language Specification SE 17 `5.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): casting conversions.
- [Java Virtual Machine Specification SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/index.html): bytecode descriptors và method invocation nền tảng.

## 17. Tổng kết

`MethodHandle.asType(newType)` tạo **adapter có MethodType mới**, chuyển từng tham số **từ chữ ký mới sang chữ ký của target**, gọi target gốc, rồi chuyển kết quả **từ target sang return type mới**. Handle gốc vẫn immutable và không bị đổi descriptor.

Các conversion thường gặp là **widening primitive**, **boxing/unboxing**, **reference cast** và **quy tắc `void`**. `asType` **không** làm primitive narrowing hay tự parse chuỗi thành số. Nếu không thể thiết lập conversion, nó ném `WrongMethodTypeException`; nếu adaptation khả thi nhưng runtime object không phù hợp, invocation có thể ném `ClassCastException` hoặc `NullPointerException`.

`invokeExact` đòi **chữ ký call site khớp tuyệt đối** với adapter, gồm tham số và return; `invoke` có thể tự thích nghi tương đương `asType`. Hãy thiết kế rõ MethodType ở boundary, sử dụng conversion và combinators đúng mục đích, kiểm thử cả trường hợp thành công/lỗi, và bảo vệ quyền truy cập của method handles trong hệ thống động.

**Đây là một cơ chế quan trọng của Java hiện đại, bắt đầu từ Java 7 và vẫn được sử dụng trong các JDK mới**, đặc biệt khi kết hợp dynamic dispatch, runtime-generated call sites hoặc các tầng framework cần một cách gọi có kiểu linh hoạt.