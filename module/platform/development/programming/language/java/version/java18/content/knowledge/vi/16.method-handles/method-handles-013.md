# invoke(): chuyển đổi kiểu theo quy tắc asType khi chữ ký gọi chưa khớp

## 1. Bối cảnh và mục tiêu học

Trong Java 18 và các JDK hiện đại, `java.lang.invoke.MethodHandle` là một tham chiếu thực thi có kiểu mạnh tới method, constructor, field hoặc một thao tác đã được biến đổi. Mỗi handle có chữ ký xác định, được mô tả bằng `MethodType`: danh sách kiểu tham số và kiểu trả về.

Khi gọi một handle, có hai API quan trọng:

- `invokeExact(...)` yêu cầu chữ ký tại điểm gọi **khớp chính xác** với `handle.type()`.
- `invoke(...)` chấp nhận một số chữ ký không khớp, miễn là có thể chuyển đổi theo quy tắc `MethodHandle.asType(MethodType)`.

Các ví dụ ngắn trong bài dùng lớp minh họa `MathOps` sau (có thể lưu thành `MathOps.java`):

```java
public final class MathOps {
    private MathOps() {
    }

    public static long add(long a, long b) {
        return a + b;
    }

    public static long doubleIt(long value) {
        return value * 2;
    }

    public static int acceptByte(byte value) {
        return value;
    }

    public static String describe(Number value) {
        return value.getClass().getSimpleName();
    }

    public static long constant() {
        return 42L;
    }

    public static void mark(long value) {
        System.out.println("mark: " + value);
    }

    public static String greeting(String name) {
        return "Xin chào " + name;
    }
}
```

Các đoạn gọi handle bên dưới giả định có các import `java.lang.invoke.MethodHandle`, `MethodHandles` và `MethodType`, đồng thời được đặt trong một method khai báo `throws Throwable` hoặc bắt exception tương ứng. Để chạy một ví dụ độc lập hoàn chỉnh, xem chương trình ở phần 17.

Ví dụ tạo handle đại diện method `long add(long, long)`:

```java
MethodHandle add = MethodHandles.lookup().findStatic(
    MathOps.class,
    "add",
    MethodType.methodType(long.class, long.class, long.class)
);
```

Handle có kiểu:

```text
(long,long)long
```

Cả hai lời gọi sau đều có thể thành công:

```java
long exact = (long) add.invokeExact(2L, 3L);
long adapted = (long) add.invoke(2, 3);
```

Ở dòng thứ hai, hai đối số là `int`, trong khi target nhận `long`. `invoke` chấp nhận việc widening từ `int` sang `long` nhờ quy tắc tương đương `asType`; `invokeExact` không làm vậy.

**Mục tiêu của bài:** xác định đúng kiểu của handle và call site, biết chiều chuyển đổi đối số/kết quả, dự đoán khi nào xảy ra `WrongMethodTypeException`, `ClassCastException` hoặc `NullPointerException`, và viết các lời gọi có thể kiểm chứng trên JDK hiện đại.

> Phạm vi: các hợp đồng này là API Java SE hiện hành, không phải mẹo dựa trên implementation cũ. Java 18 gắn với quá trình hiện đại hóa Core Reflection qua JEP 416, nhưng quy tắc `invoke`/`asType` của MethodHandle là hợp đồng riêng thuộc `java.lang.invoke`; không nên đánh đồng hai API.

## 2. MethodType là chữ ký runtime của handle

Một `MethodType` gồm:

- Kiểu trả về, có thể là `void.class`.
- Danh sách kiểu tham số có thứ tự.
- Số lượng tham số (arity).

Tạo và đọc chữ ký:

```java
import java.lang.invoke.MethodType;

MethodType type = MethodType.methodType(
    long.class,
    long.class,
    long.class
);

System.out.println(type);                  // (long,long)long
System.out.println(type.parameterCount()); // 2
System.out.println(type.parameterType(0)); // long
System.out.println(type.returnType());     // long
```

Một handle thu được bằng `findStatic` có các tham số tương ứng với static method đích. Với `findVirtual`, handle còn có **receiver ở vị trí tham số đầu tiên**.

Ví dụ:

```java
MethodHandle substring = MethodHandles.lookup().findVirtual(
    String.class,
    "substring",
    MethodType.methodType(String.class, int.class)
);

System.out.println(substring.type());
// (String,int)String
```

Phương thức nguồn `String.substring(int)` chỉ khai báo một tham số `int`; nhưng handle cần thêm receiver `String` và vì thế có arity 2.

Trước khi chẩn đoán `WrongMethodTypeException`, hãy in `handle.type()`. Đoán chữ ký chỉ từ tên method hoặc từ biểu thức gọi thường không đủ.

## 3. Chữ ký tại call site được quyết định như thế nào?

`invoke` và `invokeExact` là các **signature-polymorphic methods**. Cú pháp Java trông giống varargs `Object...`, nhưng bytecode không coi mọi đối số là một mảng `Object[]` rồi tự unbox như `java.lang.reflect.Method.invoke`.

Theo đặc tả MethodHandle, compiler ghi vào bytecode một **symbolic type descriptor** phản ánh:

1. Kiểu tĩnh của từng biểu thức đối số tại call site.
2. Kiểu trả về mà call site yêu cầu.

Với handle có kiểu `(long,long)long`:

```java
long a = (long) add.invokeExact(2L, 3L);
long b = (long) add.invoke(2, 3);
Object c = (Object) add.invoke(2, 3);
add.invoke(2, 3);
```

Các descriptor tại call site, xét về mặt khái niệm, là:

| Câu lệnh | Kiểu đối số tại call site | Kiểu trả về yêu cầu |
| --- | --- | --- |
| `(long) add.invokeExact(2L, 3L)` | `(long,long)` | `long` |
| `(long) add.invoke(2, 3)` | `(int,int)` | `long` |
| `(Object) add.invoke(2, 3)` | `(int,int)` | `Object` |
| `add.invoke(2, 3);` | `(int,int)` | `void` |

Điểm rất quan trọng:

- Phép cast **trực tiếp trên biểu thức invoke** đặt kiểu trả về của call site.
- Nếu kết quả được dùng như một biểu thức mà không có cast thích hợp, kiểu trả về tại call site là `Object`.
- Nếu lời gọi chỉ là một statement, kiểu trả về tại call site là `void`.
- Compiler không tự thực hiện các method invocation conversions trên đối số cho các signature-polymorphic invoker; quy tắc thích ứng thuộc về handle và `asType`.

Do vậy, khi viết `invokeExact`, hãy chú ý **cả đối số lẫn kiểu trả về**. Chỉ đặt đúng giá trị số là chưa đủ.

## 4. invokeExact: khớp chính xác, không chuyển đổi

`invokeExact` yêu cầu:

```text
call-site MethodType == handle.type()
```

Không có widening, boxing, unboxing hay reference cast để sửa chữ ký tại điểm gọi.

Ví dụ:

```java
long ok = (long) add.invokeExact(2L, 3L); // OK

long failed = (long) add.invokeExact(2, 3);
// WrongMethodTypeException: (int,int)long != (long,long)long
```

Và một lỗi tinh vi khác:

```java
Object failedReturn = (Object) add.invokeExact(2L, 3L);
// WrongMethodTypeException: (long,long)Object != (long,long)long
```

Dù giá trị `long` có thể được boxing thành `Long` trong Java thông thường, `invokeExact` không tự boxing kết quả để khớp descriptor `Object`.

Cách đúng là giữ descriptor chính xác, rồi để Java chuyển giá trị **sau lời gọi**:

```java
long primitive = (long) add.invokeExact(2L, 3L);
Object boxedByJava = primitive;
```

Hoặc dùng `invoke` nếu thực sự muốn cơ chế adaptation ở call site:

```java
Object boxedByAdapter = (Object) add.invoke(2L, 3L);
```

## 5. invoke: tương đương asType rồi invokeExact

Theo API, khi descriptor của call site đã khớp `handle.type()`, `invoke` hành xử như `invokeExact`.

Khi không khớp, hành vi về mặt ngữ nghĩa là:

```java
MethodType wantedType = /* descriptor tại call site */;

MethodHandle adapted = original.asType(wantedType);
Object result = /* gọi invokeExact trên adapted theo wantedType */;
```

Đây chỉ là mô hình giải thích, không phải cú pháp cần viết nguyên văn. JVM **không bắt buộc phải thực sự tạo** một adapter object cho từng lần `invoke`; nó có thể tối ưu trực tiếp các phép chuyển đổi.

Với:

```java
long result = (long) add.invoke(2, 3);
```

cách hiểu là:

```text
Handle gốc:
    (long,long)long

Call site cần:
    (int,int)long

asType tạo/diễn giải adapter:
    (int,int)long
         |
         +-- int -> long cho đối số 1
         +-- int -> long cho đối số 2
         +-- gọi handle gốc (long,long)long
         +-- kết quả long giữ nguyên
```

Viết tường minh:

```java
MethodType desired = MethodType.methodType(
    long.class, int.class, int.class
);

MethodHandle adapted = add.asType(desired);

long result = (long) adapted.invokeExact(2, 3);
```

Kết quả tương đương về mặt chuyển đổi đối số và kiểu trả về với `(long) add.invoke(2, 3)`.

**Không hiểu sai:** `asType` thay đổi *giao diện kiểu* của handle, không tìm một overload khác có tên giống nhau, không đổi định nghĩa method đích và không làm mất các ngoại lệ từ method đích.

## 6. Chiều chuyển đổi: đối số và giá trị trả về ngược nhau

Tài liệu `MethodHandle.asType` quy ước hai loại chuyển đổi:

- **Đối số:** từ kiểu mà caller cung cấp (**new type**) sang kiểu target nhận (**old type**).
- **Giá trị trả về:** từ kiểu target trả (**old type**) sang kiểu mà caller muốn nhận (**new type**).

Sơ đồ:

```text
Call site                  Adapter asType                 Target
  int arg  ---------------------> long arg -------------------->
  int arg  ---------------------> long arg -------------------->
          <----- Object / Long <--- long result <---------------
```

Ví dụ nếu caller muốn `Object`:

```java
Object value = (Object) add.invoke(2, 3);
System.out.println(value.getClass()); // class java.lang.Long
```

Hai đối số đi **int → long**. Giá trị trả về đi **long → Long → Object**.

Đây là lý do cần xem đủ `parameterTypes` và `returnType` khi gọi `asType`. Một adapter có thể hợp lệ về đối số nhưng vẫn không hợp lệ về giá trị trả về.

## 7. Ma trận chuyển đổi của asType

Đặc tả JDK phân chia theo kiểu nguồn `T0` và kiểu đích `T1` của từng thành phần, áp dụng đúng chiều ở phần trước.

| Kiểu nguồn → kiểu đích | Quy tắc | Ví dụ |
| --- | --- | --- |
| Primitive → cùng primitive | Giữ nguyên. | `int → int`. |
| Primitive → primitive khác | **Chỉ widening** theo method invocation conversion. | `int → long` hợp lệ; `long → int` bị từ chối. |
| Primitive → reference | Boxing rồi widening reference nếu hợp lệ. | `int → Integer → Number` hợp lệ. |
| Reference → primitive | Unboxing, có thể tiếp tục primitive widening. | `Integer → int → long` hợp lệ. |
| Reference → reference | Ép kiểu reference tới kiểu đích, kiểm tra runtime nếu cần. | `Object → String` có thể thành công hoặc ném `ClassCastException`. |
| Return value → `void` | Bỏ giá trị trả về. | Hàm trả `long` có thể được gọi dưới dạng statement. |
| `void` → reference return | Tạo kết quả `null`. | Hàm `void` được caller yêu cầu `Object`. |
| `void` → primitive return | Tạo giá trị primitive mặc định (zero value). | Caller yêu cầu `int` nhận `0`. |

**Không có primitive narrowing ngầm định trong `asType`.** Ví dụ `int → byte`, `long → int`, `double → float` không được chấp nhận dù giá trị nằm trong miền.

Đối với primitive sang reference, không được mặc định “widen primitive rồi mới boxing”. Chẳng hạn `int → Long` không được `asType` giải quyết như `int → long → Long`; nếu muốn một `Long`, hãy tạo đúng wrapper trước khi gọi hoặc dùng chuyển đổi chủ động ở caller.

Với reference → primitive, việc có thể tạo adapter phụ thuộc *khả năng tồn tại một wrapper phù hợp*, không phụ thuộc giá trị của một object cụ thể tại lúc tạo adapter. Một lời gọi có thể tạo adapter thành công nhưng thất bại khi runtime object không phù hợp.

## 8. Primitive widening: được hỗ trợ, nhưng không tự narrowing

Giả sử:

```java
public static long doubleIt(long value) {
    return value * 2;
}
```

Tạo handle:

```java
MethodHandle twice = MethodHandles.lookup().findStatic(
    MathOps.class,
    "doubleIt",
    MethodType.methodType(long.class, long.class)
);
```

Các lời gọi:

```java
long a = (long) twice.invoke(4);        // int -> long, OK.
long b = (long) twice.invoke((short) 4); // short -> long, OK.
long c = (long) twice.invoke(4L);       // khớp chính xác.
```

Nếu handle nhận `byte`:

```java
public static int acceptByte(byte value) {
    return value;
}
```

thì:

```java
MethodHandle bytes = MethodHandles.lookup().findStatic(
    MathOps.class,
    "acceptByte",
    MethodType.methodType(int.class, byte.class)
);

int fail = (int) bytes.invoke(7);
// WrongMethodTypeException: call site int, target byte.
```

Việc số `7` vừa miền `byte` không thay đổi quy tắc. Số nguyên literal trong biểu thức trên có kiểu `int`; không áp dụng ngoại lệ constant narrowing của assignment context.

Muốn truyền hợp lệ:

```java
int ok = (int) bytes.invoke((byte) 7);
// Hoặc:
byte input = 7;
int alsoOk = (int) bytes.invokeExact(input);
```

Nếu đầu vào là `int` không biết trước, hãy kiểm tra miền rồi cast tường minh:

```java
static byte checkedByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("Out of byte range");
    }
    return (byte) value;
}
```

`MethodHandles.explicitCastArguments` là một adapter khác có luật cast rộng hơn, bao gồm các primitive narrowing conversions; **đừng đánh đồng** nó với `asType`. Với dữ liệu đầu vào có ý nghĩa nghiệp vụ, validate miền và quy tắc làm tròn trước khi dùng narrowing.

## 9. Boxing và unboxing: kiểu tĩnh khác với object runtime

### 9.1. Primitive đến reference

Một handle có tham số `Number` có thể nhận giá trị `int` qua `invoke`:

```java
public static String describe(Number number) {
    return number.getClass().getSimpleName();
}
```

```java
MethodHandle describe = MethodHandles.lookup().findStatic(
    MathOps.class,
    "describe",
    MethodType.methodType(String.class, Number.class)
);

String result = (String) describe.invoke(5);
// "Integer": int được boxing thành Integer, rồi widening thành Number.
```

Đổi chữ ký target thành `Long` sẽ cho kết quả khác: một đối số `int` không tự động widening thành `long` rồi boxing thành `Long` qua `asType`.

### 9.2. Reference đến primitive

Xét handle `(long)long` của `doubleIt`:

```java
Object boxedInt = Integer.valueOf(5);
long ok = (long) twice.invoke(boxedInt);
// Object chứa Integer -> unbox int -> widen long -> 10.
```

Dù kiểu tĩnh của biểu thức là `Object`, adapter vẫn có khả năng thành công vì ở runtime nó chứa một wrapper phù hợp.

Nếu object thực tế không phù hợp:

```java
Object bad = "5";
long result = (long) twice.invoke(bad);
// ClassCastException: không unbox String thành primitive long.
```

Nếu object là null:

```java
Object missing = null;
long result = (long) twice.invoke(missing);
// NullPointerException khi unboxing.
```

Những lỗi trên khác `WrongMethodTypeException`: chữ ký `(Object)long` **có thể** chuyển đổi sang `(long)long`, nhưng giá trị cụ thể tại runtime không đáp ứng phép chuyển đổi.

### 9.3. Reference kiểu wrapper không phải primitive widening tùy ý

Một trường hợp có thể gây nhầm:

```java
Long boxedLong = Long.valueOf(5);
int result = (int) bytes.invoke(boxedLong);
```

Handle `bytes` nhận `byte`. Chuyển từ reference `Long` sang primitive `byte` không có đường unboxing rồi widening hợp lệ. Do đó adapter không hình thành được và lời gọi ném `WrongMethodTypeException`.

Nếu kiểu tĩnh là `Object`, `asType` có thể chấp nhận khả năng object chứa `Byte`, nhưng với giá trị runtime thật là `Long`, bước chuyển đổi có thể ném `ClassCastException`.

## 10. Reference cast: adapter hợp lệ chưa chắc dữ liệu hợp lệ

Xét virtual method `String.substring(int)`:

```java
MethodHandle substring = MethodHandles.lookup().findVirtual(
    String.class,
    "substring",
    MethodType.methodType(String.class, int.class)
);
// (String,int)String
```

Gọi với receiver có kiểu tĩnh `Object`:

```java
Object validReceiver = "MethodHandle";
String result = (String) substring.invoke(validReceiver, 6);
// "Handle"
```

Call site cần kiểu `(Object,int)String`. Theo `asType`, reference `Object` có thể được cast thành `String` nếu object thực tế đúng kiểu.

Nhưng:

```java
Object invalidReceiver = new StringBuilder("MethodHandle");
String result = (String) substring.invoke(invalidReceiver, 6);
// ClassCastException khi cast receiver sang String.
```

Đặc tả cho phép tạo adapter giữa hai kiểu tham chiếu ngay cả khi chúng không có quan hệ kế thừa rõ ràng, vì một giá trị `null` về mặt lý thuyết có thể cast thành bất kỳ reference type nào. **Reference cast vẫn được kiểm tra đối với giá trị thực khi gọi.**

Nếu reference đã cast thành `null` và target là instance method, việc gọi method trên null có thể phát sinh `NullPointerException` từ quá trình dispatch; đừng nhầm nó với sai chữ ký tại call site.

## 11. Thích ứng giá trị trả về: boxing, unboxing, bỏ kết quả và void

Giả sử target trả `long`:

```java
public static long constant() {
    return 42L;
}
```

Handle có kiểu `()long`:

```java
MethodHandle constant = MethodHandles.lookup().findStatic(
    MathOps.class,
    "constant",
    MethodType.methodType(long.class)
);
```

### 11.1. Giữ nguyên kiểu trả về

```java
long value = (long) constant.invokeExact(); // 42.
```

### 11.2. Boxing kết quả sang reference

```java
Object boxed = (Object) constant.invoke();
// Long(42), sau đó được nhìn như Object.
```

Chuyển đổi ở đây là **target long → boxed Long → Object**, không phải caller đang tự cast một giá trị `Object` được trả về từ generic reflection.

### 11.3. Bỏ giá trị trả về

```java
constant.invoke(); // statement call site có return type void.
```

Target vẫn được gọi, nhưng kết quả `long` bị bỏ đi qua adaptation.

### 11.4. Không tự narrowing kết quả

```java
int fail = (int) constant.invoke();
// WrongMethodTypeException: target trả long, caller yêu cầu int.
```

Vì `long → int` là primitive narrowing, `asType` không cho phép.

Cách tường minh nếu cần kiểm tra miền:

```java
long result = (long) constant.invokeExact();
int value = Math.toIntExact(result);
```

### 11.5. Target void nhưng caller yêu cầu kết quả

Với:

```java
public static void mark(long value) {
    System.out.println("mark: " + value);
}
```

Handle có kiểu `(long)void`. Các lời gọi sau có ý nghĩa:

```java
markHandle.invoke(5L);                       // void -> void.
Object marker = (Object) markHandle.invoke(5L); // null.
int zero = (int) markHandle.invoke(5L);          // 0.
```

Đặc tả `asType` quy định khi target trả `void`, adapter có thể giới thiệu giá trị `null` cho kiểu tham chiếu hoặc zero value cho kiểu primitive mà caller yêu cầu.

Đây là hành vi của MethodHandle adapter, **không** có nghĩa method đích thật sự trả về `0` hoặc `null` trong source Java.

## 12. Khi nào xảy ra WrongMethodTypeException?

`WrongMethodTypeException` phản ánh việc type descriptor của handle và call site không khớp, hoặc một adapter theo `asType` không thể được xây dựng.

Các trường hợp điển hình:

| Tình huống | Ví dụ | Kết quả |
| --- | --- | --- |
| `invokeExact` với kiểu tham số sai | Target nhận `long`, caller truyền `int`. | `WrongMethodTypeException`. |
| `invokeExact` với kiểu trả về sai | Target trả `long`, caller yêu cầu `Object`. | `WrongMethodTypeException`. |
| `invoke` cần primitive narrowing | `int → byte`. | `WrongMethodTypeException`. |
| `invoke` cần narrowing return | `long → int`. | `WrongMethodTypeException`. |
| `invoke` có số đối số khác target fixed-arity | Target nhận hai tham số, caller chỉ truyền một. | `WrongMethodTypeException`. |
| `asType` yêu cầu arity khác fixed-arity target | `(long,long)long → (int)long`. | `WrongMethodTypeException`. |
| `asType` yêu cầu reference-to-primitive bất khả thi | `Long → byte`. | `WrongMethodTypeException`. |

Thông báo cụ thể có thể thay đổi theo JDK; hãy dựa vào **kiểu exception** và `MethodType`, không phụ thuộc vào chuỗi trong error message.

## 13. Phân biệt WrongMethodTypeException, ClassCastException và NullPointerException

Đây là ba lớp thất bại khác nhau:

| Loại lỗi | Diễn giải | Ví dụ |
| --- | --- | --- |
| `WrongMethodTypeException` | Không thể khớp/adapt **chữ ký tĩnh**. | Caller `int`, target `byte`. |
| `ClassCastException` | Adapter về mặt kiểu có thể hợp lệ, nhưng **object thực tế** không cast/unbox được. | Caller tĩnh `Object`, chứa `StringBuilder` nhưng target cần `String`. |
| `NullPointerException` | Cần unbox null hoặc gọi instance target với receiver null. | Caller tĩnh `Object` chứa null, target cần `long`. |

Một phương pháp debug hiệu quả:

1. In `handle.type()` để biết kiểu target thực sự.
2. Ghi kiểu tĩnh của các biểu thức tại call site.
3. Ghi kiểu trả về do cast trên `invoke` yêu cầu.
4. Kiểm tra số tham số.
5. Đánh giá khả năng chuyển đổi theo bảng `asType`.
6. Nếu adaptation có thể thực hiện, kiểm tra kiểu runtime và null của object.

Hãy tránh chuyển tất cả lỗi thành một nhánh `catch (Exception)` rồi kết luận cùng nguyên nhân.

## 14. Sai số lượng đối số và ngoại lệ với varargs collector

Với một **fixed-arity handle**, `asType` chuyển đổi đối số theo từng vị trí và không tự thêm/bỏ vị trí.

Giả sử target:

```text
(long,long)long
```

thì:

```java
long wrong = (long) add.invoke(1L);
// WrongMethodTypeException: target cần hai tham số.
```

Tương tự:

```java
add.asType(MethodType.methodType(long.class, int.class));
// WrongMethodTypeException: yêu cầu arity 1 thay vì 2.
```

Tuy nhiên, `MethodHandle` có khái niệm **variable-arity collector**. Một handle dạng collector có thể gom các đối số cuối vào một mảng, và `invoke`/`asType` có quy tắc bổ sung riêng cho dạng này.

Vì vậy, khi kiểm tra arity:

```java
System.out.println(handle.isVarargsCollector());
System.out.println(handle.type().parameterCount());
```

Nếu cần một handle với số tham số cố định để so sánh chuyển đổi theo từng vị trí, có thể dùng:

```java
MethodHandle fixed = handle.asFixedArity();
```

Không suy ra rằng mọi lời gọi `invoke` đều tự động gom các đối số thành mảng chỉ vì trong source Javadoc chữ ký `invoke(Object...)` trông giống varargs thông thường. Hành vi phụ thuộc kiểu handle, không chỉ cú pháp.

## 15. Dùng asType tường minh và invokeExact sau khi adapt

Nếu một đường gọi lặp lại luôn sử dụng cùng một descriptor không trùng target gốc, có thể tạo adapter một lần:

```java
MethodType callerType = MethodType.methodType(
    Object.class,
    int.class,
    int.class
);

MethodHandle adapted = add.asType(callerType);

System.out.println(adapted.type()); // (int,int)Object

Object result = (Object) adapted.invokeExact(4, 5);
System.out.println(result);             // 9
System.out.println(result.getClass());  // class java.lang.Long
```

Quy trình:

```text
Original handle: (long,long)long
        |
        | asType((int,int)Object)
        v
Adapter handle:  (int,int)Object
        |
        | invokeExact(4, 5)
        v
int -> long, int -> long
        |
        v
target add(long,long) -> long
        |
        v
long -> Long -> Object
```

Ưu điểm của cách viết tường minh:

- Chữ ký adapter được đặt tên và dễ kiểm tra.
- Sau khi tạo adapter, điểm gọi `invokeExact` có descriptor rõ ràng.
- Có thể cache adapter nếu workload thực sự dùng lặp lại cùng một kiểu.

Không có cam kết rằng `asType` tường minh luôn nhanh hơn `invoke`. JVM có thể thích ứng tối ưu ngay trong `invoke`; nếu quan tâm hiệu năng, hãy đo trên JDK hiện tại bằng JMH và không bỏ qua warmup/JIT effects.

Lưu ý: `asType` tạo hoặc trả một handle mới có `type()` bằng `newType`; nếu kiểu đã giống nhau, API có thể trả chính handle ban đầu. Nó không biến đổi `type()` của original handle tại chỗ.

## 16. Trường hợp lỗi: asType có thể tạo được nhưng invoke vẫn thất bại

Ví dụ với method nhận `String`:

```java
public static String greeting(String name) {
    return "Xin chào " + name;
}
```

Tạo handle kiểu `(String)String`:

```java
MethodHandle greet = MethodHandles.lookup().findStatic(
    MathOps.class,
    "greeting",
    MethodType.methodType(String.class, String.class)
);
```

Adapter:

```java
MethodHandle objectInput = greet.asType(
    MethodType.methodType(String.class, Object.class)
);
```

Adapter này hợp lệ: lúc chạy, nó sẽ cast đối số `Object` sang `String`.

```java
String ok = (String) objectInput.invokeExact((Object) "Java");
// "Xin chào Java"
```

Nhưng:

```java
Object value = new StringBuilder("Java");
String failed = (String) objectInput.invokeExact(value);
// ClassCastException trong adapter.
```

Điểm phân biệt:

- `asType(...)` có thể trả adapter thành công.
- Khi thực thi, giá trị cụ thể mới quyết định reference cast có thành công không.
- Nếu cast thất bại, đây là `ClassCastException`, **không phải** `WrongMethodTypeException` vì descriptor của adapter đã hoàn toàn hợp lệ.

## 17. Ví dụ Java hoàn chỉnh: kiểm tra các kết quả và lỗi

Lưu file `MethodHandleInvokeAsTypeDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleInvokeAsTypeDemo {
    public static final class Targets {
        public static long add(long a, long b) {
            return a + b;
        }

        public static byte acceptByte(byte value) {
            return value;
        }

        public static String greet(String name) {
            return "Hi " + name;
        }

        public static void mark(long value) {
            System.out.println("mark=" + value);
        }

        public static int fail(int value) {
            throw new IllegalStateException("target failure " + value);
        }
    }

    @FunctionalInterface
    interface CheckedCall {
        Object run() throws Throwable;
    }

    static void attempt(String label, CheckedCall call) {
        try {
            Object result = call.run();
            System.out.println(label + " -> " + result);
        } catch (Throwable failure) {
            System.out.println(
                label + " -> " + failure.getClass().getSimpleName()
            );
        }
    }

    public static void main(String[] args) throws Throwable {
        var lookup = MethodHandles.lookup();

        MethodHandle add = lookup.findStatic(
            Targets.class,
            "add",
            MethodType.methodType(long.class, long.class, long.class)
        );

        MethodHandle acceptByte = lookup.findStatic(
            Targets.class,
            "acceptByte",
            MethodType.methodType(byte.class, byte.class)
        );

        MethodHandle greet = lookup.findStatic(
            Targets.class,
            "greet",
            MethodType.methodType(String.class, String.class)
        );

        MethodHandle mark = lookup.findStatic(
            Targets.class,
            "mark",
            MethodType.methodType(void.class, long.class)
        );

        MethodHandle fail = lookup.findStatic(
            Targets.class,
            "fail",
            MethodType.methodType(int.class, int.class)
        );

        System.out.println("target type = " + add.type());

        attempt("exact", () -> (long) add.invokeExact(2L, 3L));

        attempt("int widened", () -> (long) add.invoke(2, 3));

        attempt("return boxed", () -> (Object) add.invoke(2, 3));

        attempt("Object unboxed", () -> {
            Object value = Integer.valueOf(5);
            return (long) add.invoke(value, 2L);
        });

        attempt("narrowing int -> byte", () ->
            (byte) acceptByte.invoke(7));

        attempt("correct byte", () ->
            (byte) acceptByte.invoke((byte) 7));

        attempt("invokeExact wrong args", () ->
            (long) add.invokeExact(2, 3));

        attempt("invokeExact wrong return", () ->
            (Object) add.invokeExact(2L, 3L));

        attempt("wrong arity", () ->
            (long) add.invoke(1L));

        attempt("wrong return narrowing", () ->
            (int) add.invoke(1L, 2L));

        attempt("reference cast failure", () -> {
            Object input = new StringBuilder("Java");
            return (String) greet.invoke(input);
        });

        attempt("unboxing null", () -> {
            Object input = null;
            return (long) add.invoke(input, 2L);
        });

        attempt("void to int", () -> (int) mark.invoke(5));

        attempt("void to Object", () -> (Object) mark.invoke(6L));

        attempt("target exception", () -> (int) fail.invoke(1));

        MethodHandle adapted = add.asType(
            MethodType.methodType(
                Object.class, int.class, int.class
            )
        );

        attempt("adapted invokeExact", () ->
            (Object) adapted.invokeExact(4, 5));

        attempt("explicit asType arity mismatch", () ->
            add.asType(MethodType.methodType(long.class, int.class)));

        // This is deliberately an inexact invocation type mismatch:
        try {
            long ignored = (long) add.invokeExact(2, 3);
            System.out.println(ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("Caught WrongMethodTypeException");
        }
    }
}
```

Biên dịch và chạy trên JDK hiện hành:

```sh
javac MethodHandleInvokeAsTypeDemo.java
java MethodHandleInvokeAsTypeDemo
```

Kết quả cần quan sát:

| Nhãn | Kết quả kỳ vọng |
| --- | --- |
| `exact` | `5`. |
| `int widened` | `5`. |
| `return boxed` | `5` dưới dạng `Long` được nhìn như `Object`. |
| `Object unboxed` | `7`. |
| `narrowing int -> byte` | `WrongMethodTypeException`. |
| `correct byte` | `7`. |
| `invokeExact wrong args` | `WrongMethodTypeException`. |
| `invokeExact wrong return` | `WrongMethodTypeException`. |
| `wrong arity` | `WrongMethodTypeException`. |
| `wrong return narrowing` | `WrongMethodTypeException`. |
| `reference cast failure` | `ClassCastException`. |
| `unboxing null` | `NullPointerException`. |
| `void to int` | In `mark=5`, sau đó kết quả `0`. |
| `void to Object` | In `mark=6`, sau đó kết quả `null`. |
| `target exception` | `IllegalStateException` truyền ra trực tiếp. |
| `adapted invokeExact` | `9` dưới dạng `Long`. |
| `explicit asType arity mismatch` | `WrongMethodTypeException`. |

Ví dụ minh họa các kết quả theo hợp đồng API; phần output tổng thể có thêm dòng in của `mark` và thông báo bắt lỗi cuối chương trình.

### 17.1. Vì sao target exception không bị bọc?

Trong ví dụ, `Targets.fail` ném `IllegalStateException`. Lời gọi handle truyền lỗi đó ra trực tiếp.

Đây là điểm khác với `java.lang.reflect.Method.invoke`, vốn bọc ngoại lệ từ method đích bằng `InvocationTargetException`. Với `MethodHandle.invoke`, API khai báo `throws Throwable`, và target exception không được tự động biến thành `InvocationTargetException`.

## 18. Phân biệt invoke với invokeWithArguments

Ngoài `invoke` còn có `invokeWithArguments`:

```java
Object value = add.invokeWithArguments(2, 3);
```

`invokeWithArguments` nhận các đối số dưới dạng danh sách `Object` và có quy tắc xử lý argument list riêng; kết quả trả về cũng được biểu diễn dưới dạng `Object`.

Khác biệt quan trọng:

| API | Xác định kiểu gọi | Mục đích |
| --- | --- | --- |
| `invokeExact` | Descriptor compile-time của call site phải khớp hoàn toàn. | Gọi với kiểu chính xác. |
| `invoke` | Descriptor compile-time; áp dụng chuyển đổi tương đương `asType`. | Gọi có adaptation được kiểm soát theo kiểu. |
| `invokeWithArguments` | Danh sách đối số object, xác định số lượng tại runtime. | Gọi linh hoạt khi dữ liệu đến dưới dạng collection/array. |

`invokeWithArguments` không phải phương án luôn tốt hơn chỉ vì tránh cast tại source code; nó có overhead và quy tắc varargs/boxing riêng. Với hot path có chữ ký rõ ràng, hãy ưu tiên API thể hiện hợp đồng kiểu đầy đủ và đo trước khi tối ưu.

## 19. So sánh với Core Reflection và JEP 416

Java có hai nhánh API thường dễ bị trộn:

| Tiêu chí | `MethodHandle.invoke` | `Method.invoke` |
| --- | --- | --- |
| Chữ ký runtime | `MethodType`, gồm cả kiểu trả về. | `Method` chọn theo khai báo formal. |
| Cách truyền đối số | Signature-polymorphic call site. | Mảng `Object...`. |
| Chuyển đổi | Theo hợp đồng `asType`. | Reflection invocation conversions theo API reflection. |
| Kiểu trả về tại điểm gọi | Có thể yêu cầu `long`, `Object`, `void` qua descriptor. | `Method.invoke` trả `Object`; primitive được boxing. |
| Lỗi chữ ký không thể adapt | `WrongMethodTypeException`. | Thường `IllegalArgumentException` nếu số lượng/kiểu đối số sai. |
| Lỗi target ném ra | `Throwable` từ target truyền ra. | Bọc trong `InvocationTargetException`. |
| Kiểm tra quyền | Khi tạo handle thông qua `Lookup`. | Theo quy tắc reflection tại lúc gọi. |

JEP 416 từ Java 18 dùng method handles làm nền tảng triển khai Core Reflection, nhưng không có nghĩa `Method.invoke` và `MethodHandle.invoke` có cùng interface hay cùng tập exception. Hai API công khai vẫn có hợp đồng riêng.

## 20. Chẩn đoán lỗi thực tế

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `invokeExact` thất bại dù số đúng | Kiểu tĩnh `int` khác `long`. | In `handle.type()`, dùng literal `2L` hoặc biến `long`. |
| `invokeExact` thất bại khi gán kết quả cho `Object` | Call site đòi `Object` còn target trả `long`. | Gọi với cast `(long)` rồi để Java boxing bên ngoài, hoặc dùng `invoke`. |
| `invoke` thất bại với giá trị `7` cho byte | Cần narrowing `int → byte`. | Kiểm tra miền và cast tường minh sang `byte`. |
| `invoke` thất bại khi caller yêu cầu `int` từ target `long` | Return narrowing không được phép. | Nhận `long`, sau đó dùng `Math.toIntExact` nếu phù hợp. |
| `ClassCastException` dù asType thành công | Adapter cho phép reference cast nhưng runtime object sai kiểu. | In `arg.getClass()` và kiểm tra kiểu mong đợi. |
| `NullPointerException` khi truyền `Object` | Object thực tế null nhưng target cần primitive hoặc receiver instance. | Kiểm tra null trước khi gọi. |
| `WrongMethodTypeException` khi truyền thiếu đối số | Fixed-arity handle không đổi số tham số. | Xem `type().parameterCount()`, `isVarargsCollector()`. |
| Kết quả `void` thành `0` hoặc `null` | Return adaptation của asType. | Xem target `type().returnType()` và kiểu caller. |
| Target exception không có `InvocationTargetException` | Đây là MethodHandle, không phải Core Reflection. | Catch loại lỗi thực của target, hoặc xử lý `Throwable` theo hợp đồng. |
| Adapter tạo mới nhưng lỗi vẫn xuất hiện | Cast/unboxing chỉ kiểm tra được object lúc chạy. | Phân biệt khả năng tạo adapter với khả năng chuyển đổi giá trị runtime. |
| Lỗi lookup trước khi invoke | Không tìm thấy method, sai MethodType hoặc thiếu quyền. | Kiểm tra `Lookup.findStatic/findVirtual` và access của class. |
| Muốn gọi theo tên overload khác | asType không thực hiện overload resolution. | Chọn đúng handle khi lookup; sau đó mới adapt. |

## 21. Quy tắc triển khai an toàn

1. **Kiểm tra `handle.type()` trước.** Đừng suy đoán kiểu chỉ từ method source.
2. **Viết cast cho kiểu trả về một cách chủ động.** Tránh để call site thành `Object` hoặc `void` ngoài ý muốn.
3. **Dùng `invokeExact` nếu muốn kiểm tra kiểu chính xác.** Không kỳ vọng nó sẽ widening hoặc boxing.
4. **Dùng `invoke` nếu muốn chuyển đổi tương đương `asType`.** Chỉ những chuyển đổi được đặc tả cho phép mới thành công.
5. **Không tự narrowing primitive.** Kiểm tra miền và cast tường minh; nếu dùng `explicitCastArguments`, hiểu rõ semantics riêng của nó.
6. **Phân biệt lỗi descriptor và lỗi object runtime.** `WrongMethodTypeException` khác `ClassCastException`/`NullPointerException`.
7. **Phân biệt receiver của virtual handle với static handle.** `findVirtual` thêm receiver vào tham số đầu.
8. **Với varargs collector, kiểm tra `isVarargsCollector()`.** Dùng `asFixedArity()` khi muốn kiểm tra chuyển đổi theo số tham số cố định.
9. **Không coi adapter là phương tiện vượt quyền truy cập.** `Lookup` phải có quyền tạo handle ngay từ đầu.
10. **Không bỏ qua ngoại lệ của target.** MethodHandle không bọc chúng thành `InvocationTargetException`.
11. **Chỉ tối ưu sau khi đo.** Nếu adapt lặp lại một kiểu cố định, có thể cache adapter, nhưng lợi ích hiệu năng phải được đo trên workload thật.

## 22. Bài tập tự kiểm tra

1. Tạo handle cho `long add(long,long)`, in `type()` và giải thích arity.
2. So sánh `(long) add.invokeExact(2L,3L)` với `(long) add.invoke(2,3)`.
3. Gọi `(Object) add.invoke(2L,3L)`, kiểm tra runtime class của kết quả.
4. Thử `(Object) add.invokeExact(2L,3L)`; giải thích vì sao return descriptor làm lời gọi thất bại.
5. Gọi handle nhận `byte` bằng literal `7`; phân biệt primitive narrowing với integer constant assignment.
6. Tạo một `Object` chứa `Integer` và gọi handle nhận `long`; giải thích các bước unbox/widen.
7. Thay nội dung `Object` bằng `String` và bằng `null`; so sánh `ClassCastException` và `NullPointerException`.
8. Gọi virtual handle của `String.substring` với receiver tĩnh `Object` hợp lệ và không hợp lệ.
9. Dùng `asType` tạo adapter `(int,int)Object` từ handle `(long,long)long`, rồi gọi `invokeExact`.
10. Thử một `asType` sai số lượng tham số và một `asType` cần return narrowing.
11. Tạo handle cho method trả `void`, yêu cầu kiểu trả về `Object` và `int` ở hai call site. Giải thích kết quả `null` và `0`.
12. Viết method đích ném `IllegalStateException`. Xác minh MethodHandle truyền exception ra không qua `InvocationTargetException`.
13. Dùng `isVarargsCollector()` và `asFixedArity()` để phân biệt fixed-arity và variable-arity.
14. So sánh `invoke` với `invokeWithArguments` khi nhận dữ liệu từ một collection.
15. Lập bảng trường hợp thành công và lỗi trên JDK hiện tại, ghi rõ `handle.type()`, call-site descriptor và exception.

**Tiêu chí hoàn thành:** bạn mô tả đúng quy trình `invoke → asType-equivalent adaptation → invokeExact`, nắm cả chuyển đổi đối số và giá trị trả về, dự đoán được `WrongMethodTypeException` khi descriptor không thể thích ứng, phân biệt lỗi chuyển đổi runtime và tự kiểm tra được các ví dụ trên JDK hiện đại.

## 23. Tài liệu tham khảo

- [Oracle Java SE 27 — MethodHandle API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): đặc tả đầy đủ cho `invoke`, `invokeExact`, `asType`, signature polymorphism, chuyển đổi đối số và return, exception.
- [Oracle Java SE 27 — MethodType API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodType.html): mô tả `MethodType`, arity, danh sách tham số và kiểu trả về.
- [Oracle Java SE 27 — WrongMethodTypeException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): lỗi chữ ký call site không khớp handle hoặc adapter không thể tạo.
- [Oracle Java SE 27 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): tìm static/virtual handles và kiểm tra quyền tại lúc tạo handle.
- [Oracle Java SE 27 — MethodHandles API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.html): các combinators, bao gồm `explicitCastArguments` để so sánh với `asType`.
- [Oracle Java SE 27 — JLS 5.3 Method Invocation Contexts](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html#jls-5.3): primitive widening, boxing, unboxing và method invocation conversions trong ngôn ngữ Java.
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): bối cảnh Java 18 liên quan đến triển khai Core Reflection, không thay thế hợp đồng MethodHandle API.
