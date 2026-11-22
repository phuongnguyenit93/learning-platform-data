# ConstantBootstraps: nullConstant, primitiveClass, enumConstant và getStaticFinal (Java 11+)

## 1. Vì sao Java 11 có các bootstrap method cho hằng số động?

Trước khi bàn đến từng phương thức, cần phân biệt **hằng số trong mã Java** với **hằng số động ở tầng JVM**.

Java 11 triển khai **JEP 309 — Dynamic Class-File Constants**. Class file từ phiên bản **55.0** có thể chứa mục `CONSTANT_Dynamic_info` trong constant pool. Mục này mô tả một giá trị mà JVM sẽ **phân giải bằng một bootstrap method** khi cần, rồi ghi nhớ kết quả phân giải cho mục constant pool tương ứng. Nó cho phép các công cụ tạo bytecode, trình biên dịch ngôn ngữ chạy trên JVM và runtime biểu diễn những hằng số không thể ghi trực tiếp bằng các dạng constant pool truyền thống.

Trong module `java.base`, lớp **`java.lang.invoke.ConstantBootstraps`** cung cấp những bootstrap methods dùng sẵn cho một số kiểu giá trị thông dụng. Bài này tập trung đúng bốn tên API:

1. **`nullConstant`** — tạo giá trị `null` cho một **reference type**.
2. **`primitiveClass`** — tạo đối tượng `Class` mô tả kiểu nguyên thủy từ **descriptor JVM**.
3. **`enumConstant`** — lấy một hằng số enum dựa trên **tên hằng và lớp enum**.
4. **`getStaticFinal`** — lấy giá trị từ một **trường `static final`** hợp lệ, gồm hai overload.

**Bài học chỉ dùng kiến thức còn áp dụng hiện nay.** Những API trên có từ Java 11 và vẫn là nền tảng hợp lệ của cơ chế hằng số động. Chúng không phải một lời khuyên thay mọi `static final` trong code Java thông thường bằng `CONSTANT_Dynamic`.

### Mục tiêu học tập

- Hiểu quan hệ **`CONSTANT_Dynamic_info` → `BootstrapMethods` → bootstrap method → giá trị đã phân giải**.
- Đọc đúng ba tham số đầu `lookup`, `name`, `type`; phân biệt chúng ở bốn phương thức.
- Biết **`"I"` khác `"int"`** trong `primitiveClass` và vì sao `Class.class` là kiểu kết quả bắt buộc.
- Biết `enumConstant` phân biệt hoa/thường, và `getStaticFinal` cần quyền truy cập, đúng tên trường, đúng kiểu trường và modifier `final`.
- Phân biệt **lỗi khi gọi phương thức trực tiếp** với **`BootstrapMethodError` hoặc liên kết lỗi khi JVM phân giải condy**.
- Biên dịch/chạy hai chương trình Java 11: một chương trình kiểm tra trực tiếp bốn API, và một chương trình nâng cao tạo **class file có `CONSTANT_Dynamic` thật** bằng JDK thuần, không dùng API nội bộ.

## 2. Mô hình JVM: CONSTANT_Dynamic thực sự hoạt động như thế nào?

### 2.1. Khác nhau giữa ConstantValue, condy và invokedynamic

| Cơ chế | Cấu trúc/liên kết | Mục đích |
| --- | --- | --- |
| Giá trị compile-time thông thường | `CONSTANT_Integer`, `CONSTANT_String`, `ConstantValue`... | Mã hóa những literal/compile-time constants phù hợp. |
| **Dynamic constant / condy** | **`CONSTANT_Dynamic_info`**, `BootstrapMethods` | Phân giải **một giá trị hằng** bằng bootstrap method. |
| Dynamic call site | `CONSTANT_InvokeDynamic_info` và `invokedynamic` | Liên kết một **call site**, trả `CallSite`, không đơn thuần trả hằng số. |
| Trường `static final` Java | Field của lớp, có thể được gán trong initializer | Một thành viên class; **không đồng nghĩa** với condy. |

`CONSTANT_Dynamic_info` có tham chiếu tới **bootstrap method specifier** và cặp **tên + field descriptor**. Trong class file còn có `BootstrapMethods` attribute trỏ tới method handle của bootstrap method và các static arguments nếu có.

Mô hình:

```text
.class (major version 55, Java 11)
  |
  +-- constant_pool
  |     +-- CONSTANT_Dynamic_info
  |            +-- bootstrap_method_attr_index
  |            +-- name_and_type_index
  |                  +-- name: "READY"
  |                  +-- descriptor: Lpkg/State;
  |
  +-- BootstrapMethods attribute
  |     +-- MethodHandle -> ConstantBootstraps.enumConstant
  |     +-- 0 static arguments
  |
  +-- method bytecode: ldc / ldc_w (hoặc ldc2_w nếu type phù hợp)
               |
               v
       JVM resolves dynamic constant
               |
               +-- Lookup của lớp chứa constant-pool entry
               +-- "READY"
               +-- Class<?> cho type trong descriptor
               +-- Các static arguments (nếu có)
               |
               v
       enumConstant(lookup, "READY", State.class)
               |
               v
       State.READY (kết quả đã phân giải)
```

Tên, descriptor và bootstrap method nằm ở **class file**, không phải do Java source tự động tạo chỉ vì thấy `final`.

### 2.2. Ba tham số đầu của bootstrap method

Các bootstrap method trong `ConstantBootstraps` thường theo khuôn:

```java
bootstrap(MethodHandles.Lookup lookup, String name, Class<?> type)
```

Trong cách gọi từ JVM:
- **`lookup`** là ngữ cảnh `MethodHandles.Lookup` của **lớp chứa dynamic constant**, dùng để kiểm tra quyền truy cập khi cần.
- **`name`** là tên unqualified trong `CONSTANT_NameAndType` của dynamic constant, được từng bootstrap method giải thích theo mục đích riêng.
- **`type`** là đối tượng `Class` biểu diễn **kiểu kết quả** trong field descriptor của dynamic constant (không phải `MethodType`).
- Một số bootstrap methods nhận **static arguments** bổ sung sau ba tham số này; `getStaticFinal` bản bốn tham số có `declaringClass`.

**Không nhầm `type` với kiểu class của host, kiểu field khai báo hay tên của enum hằng**. Ý nghĩa chính xác phụ thuộc từng API.

### 2.3. Caching và thời điểm phân giải

Theo JVMS Java 11, khi một symbolic reference `CONSTANT_Dynamic` đã phân giải thành công, những lần phân giải tiếp theo của **cùng mục runtime constant pool** nhận cùng kết quả; bootstrap method **không được thực thi lại** cho các lần đó. Nếu phân giải thất bại, lỗi tương ứng cũng được ghi nhớ theo quy tắc resolution.

Có ba lưu ý quan trọng:

1. Phân giải có thể bị kích hoạt khi JVM liên kết hoặc khi code lần đầu dùng hằng; **không hứa chính xác một thời điểm wall-clock**.
2. Nếu **nhiều thread cùng cố phân giải ban đầu**, bootstrap method có thể được gọi đồng thời nhiều lần; JVM chọn **một kết quả** cho entry. Vì thế bootstrap tùy chỉnh nên tránh side effects hoặc phải thread-safe.
3. **Mỗi entry constant pool có vòng đời phân giải riêng**; hai entry có cùng tên/giá trị không nhất thiết chia sẻ một lần bootstrap toàn JVM.

**Gọi trực tiếp `ConstantBootstraps.nullConstant(...)` bằng Java code thông thường không tạo `CONSTANT_Dynamic` và không kích hoạt cơ chế cache của JVM cho entry ấy.** Đây là khác biệt rất quan trọng khi kiểm thử.

## 3. Bảng tổng quan bốn phương thức Java 11

| Phương thức | `name` | `type` | Kết quả |
| --- | --- | --- | --- |
| `nullConstant(Lookup, String, Class<?>)` | Không sử dụng | **Reference type**, không phải primitive | `null` |
| `primitiveClass(Lookup, String, Class<?>)` | **Descriptor JVM** của kiểu nguyên thủy, ví dụ `"I"` | Phải là **`Class.class`** | `int.class`, `boolean.class`... |
| `enumConstant(Lookup, String, Class<E>)` | **Tên enum constant** khớp chính xác | **Lớp enum** | Hằng số enum tương ứng |
| `getStaticFinal(Lookup, String, Class<?>, Class<?>)` | Tên trường `static final` | **Kiểu trường** | Giá trị của trường từ `declaringClass` |
| `getStaticFinal(Lookup, String, Class<?>)` | Tên trường `static final` | Kiểu trường và đồng thời dùng để suy ra declaring class | Giá trị trường trong chính lớp kết quả hoặc wrapper của primitive |

Tất cả các phương thức trên là **`public static`** trong `java.lang.invoke.ConstantBootstraps`, không cần tạo instance. Chúng được thiết kế làm bootstrap methods, nhưng **có thể gọi trực tiếp** để học và kiểm tra hành vi.

**Quy tắc `null`:** tài liệu lớp cho biết các tham số reference null thường làm ném `NullPointerException`, **trừ** tham số được đánh dấu là không sử dụng hoặc chấp nhận null. Hai tham số `lookup`, `name` của `nullConstant` là unused; dù vậy ví dụ vẫn truyền giá trị tường minh cho dễ đọc.

## 4. nullConstant: hằng số null có kiểu tham chiếu

Chữ ký:

```java
public static Object nullConstant(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type)
```

- `lookup`: không dùng.
- `name`: không dùng.
- `type`: phải biểu diễn một **reference type**.
- Kết quả: `null`.

Ví dụ bên trong một phương thức đã có import cần thiết:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

Object a = ConstantBootstraps.nullConstant(
        lookup, "IGNORED", String.class);
Object b = ConstantBootstraps.nullConstant(
        lookup, "IGNORED", int[].class);

System.out.println(a == null); // true
System.out.println(b == null); // true
```

`String.class` và `int[].class` đều là reference types. Dù phần tử của mảng là `int` primitive, **bản thân kiểu mảng `int[]` vẫn là reference type**.

**Sai:**

```java
ConstantBootstraps.nullConstant(
        MethodHandles.lookup(), "ignored", int.class);
```

Đây là **phản ví dụ cố ý gây lỗi**, không dùng trong luồng bình thường: `int.class` là primitive type. Lệnh trên ném **`IllegalArgumentException`** khi gọi trực tiếp.

Tại tầng `CONSTANT_Dynamic`, descriptor của dynamic constant phải là một **field descriptor hợp lệ**; bootstrap phải cung cấp giá trị tương thích kiểu đó. `null` không thể dùng cho kết quả primitive. Đừng tự diễn giải null như giá trị mặc định số `0` hoặc `false`.

### 4.1. NullConstant không phải "null pointer cast" hay dữ liệu null trong DB

Một dynamic constant mang descriptor `Ljava/lang/String;` có thể có giá trị `null`: type mô tả **kiểu giá trị được phép**, không có nghĩa JVM tự tạo một `String`. Đây chỉ là hằng số null được phân giải, không phải Java SQL NULL, Optional.empty hoặc một sentinel có payload.

Nếu ứng dụng Java thông thường chỉ muốn một biến null, viết `String value = null;` rõ ràng và đơn giản hơn nhiều. `nullConstant` hữu ích đặc biệt trong các công cụ **sinh bytecode** cần đại diện null theo cơ chế condy.

## 5. primitiveClass: descriptor JVM khác tên Java thông thường

Chữ ký:

```java
public static Class<?> primitiveClass(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type)
```

Ở đây:
- `lookup`: không sử dụng.
- `name`: **descriptor JVM của primitive type**.
- `type`: **phải chính xác là `Class.class`**, vì giá trị trả về là một class mirror.
- Kết quả: `Class<?>` cho kiểu mô tả trong tên.

### 5.1. Bảng descriptor

| `name` | Giá trị Java | Kiểu Class trả về |
| --- | --- | --- |
| `"Z"` | boolean | `boolean.class` |
| `"B"` | byte | `byte.class` |
| `"C"` | char | `char.class` |
| `"S"` | short | `short.class` |
| `"I"` | int | `int.class` |
| `"J"` | long | `long.class` |
| `"F"` | float | `float.class` |
| `"D"` | double | `double.class` |

`"V"` là descriptor đặc biệt của **void** trong *method return descriptor*, không phải một **field descriptor** hợp lệ cho kiểu giá trị động. Trên JDK đã kiểm thử, lời gọi trực tiếp `primitiveClass(lookup, "V", Class.class)` trả `void.class`. Khi nghiên cứu class-file condy, không được từ đó suy ra có thể đặt **field descriptor `V`** cho `CONSTANT_Dynamic_info`: `V` không thể là kiểu của một giá trị field.

Ví dụ trực tiếp:

```java
Class<?> intMirror = ConstantBootstraps.primitiveClass(
        MethodHandles.lookup(), "I", Class.class);
System.out.println(intMirror == int.class); // true
```

Hai lỗi phổ biến:
1. Ghi `"int"` thay vì `"I"` → **`IllegalArgumentException`**.
2. Ghi `Object.class` thay cho `Class.class` ở tham số `type` → **`IllegalArgumentException`**.

**Không nhầm `Integer.class` với `int.class`**. Kết quả cho descriptor `"I"` là primitive class mirror `int.class`, không phải wrapper `java.lang.Integer.class`.

### 5.2. Vì sao type là Class.class?

Với dynamic constant sinh một class mirror, descriptor của **dynamic constant** là `Ljava/lang/Class;`. Tên `"I"` trong cặp NameAndType được `primitiveClass` hiểu thành kiểu **int** mà mirror biểu diễn.

Ví dụ conceptual:

```text
CONSTANT_Dynamic name: "I"
CONSTANT_Dynamic type descriptor: Ljava/lang/Class;
bootstrap: ConstantBootstraps.primitiveClass
result: int.class
```

Đoạn trên là **mô tả cấu trúc**, không phải cú pháp Java source hoặc lệnh `javap` đầy đủ.

## 6. enumConstant: tên hằng enum phải khớp chính xác

Chữ ký generic:

```java
public static <E extends Enum<E>> E enumConstant(
        MethodHandles.Lookup lookup,
        String name,
        Class<E> type)
```

- `lookup`: ngữ cảnh truy cập.
- `name`: **tên literal** của enum constant; phân biệt hoa/thường.
- `type`: lớp enum thực, ví dụ `State.class`.
- Kết quả: enum constant thuộc lớp đó.

Ví dụ:

```java
enum State {
    READY, DONE
}

State state = ConstantBootstraps.enumConstant(
        MethodHandles.lookup(), "READY", State.class);
System.out.println(state == State.READY); // true
```

Đây là **mảnh mã minh họa** gồm khai báo enum và phần gọi trong một phương thức.

**Điểm cần hiểu:** `name` là `"READY"`, không phải tên class `"State"`. `type` phải biểu diễn `State.class`, **không** phải `Enum.class` hay `String.class`.

Lỗi khi gọi trực tiếp:
- `"ready"` hoặc `"MISSING"` không khớp enum constant → **`IllegalArgumentException`**.
- `type` không phải enum class → **`IllegalArgumentException`**.
- `lookup` không có quyền truy cập enum class/field từ ngữ cảnh đó → có thể **`IllegalAccessError`**.

Với `CONSTANT_Dynamic`, descriptor của kết quả phải là kiểu enum, chẳng hạn `Lcom/example/State;`. Giá trị thực là **đúng enum singleton** `State.READY`, không phải một String mới có nội dung `"READY"`.

### 6.1. So với Enum.valueOf

`Enum.valueOf(State.class, "READY")` cũng lấy một enum constant theo tên. Khác biệt là `enumConstant` được đóng gói theo **hợp đồng bootstrap của JVM**, nhận `Lookup`, tên và kiểu kết quả từ dynamic constant. Đừng thay `Enum.valueOf` trong code ứng dụng chỉ để “dùng hằng số động”.

## 7. getStaticFinal: hai overload và ranh giới truy cập

`ConstantBootstraps` có **hai overload**:

```java
public static Object getStaticFinal(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        Class<?> declaringClass);

public static Object getStaticFinal(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type);
```

Cả hai đọc một **static final field**, không phải gọi static method và không đọc instance field.

### 7.1. Bốn tham số: nêu declaring class rõ ràng

```java
class Settings {
    static final int LIMIT = 12;
}

Object value = ConstantBootstraps.getStaticFinal(
        MethodHandles.lookup(),
        "LIMIT",
        int.class,
        Settings.class);
```

Đây là **mảnh mã minh họa** (không phải một file độc lập, cần đặt `value` trong phương thức). Bốn yếu tố phải đúng:
1. `lookup` có **quyền truy cập** đối với class và field.
2. `name` là tên field chính xác, ở đây `LIMIT`.
3. `type` là **đúng kiểu khai báo của field**, ở đây `int.class`.
4. `declaringClass` là class chứa field, ở đây `Settings.class`.

Với giá trị primitive, kiểu trả về khai báo `Object` nên lời gọi trực tiếp nhận **giá trị boxed** thích hợp, ví dụ `Integer` cho `int`. Điều này khác với descriptor nguyên thủy của một condy entry, nơi JVM còn xác nhận/biến đổi kết quả sang field type theo luật resolution.

Ví dụ field `private static final` cũng có thể đọc được **khi lookup của caller thật sự đủ quyền**. Không có quyền thì `IllegalAccessError`; việc method là `public static` không làm bypass access check.

### 7.2. Ba tham số: declaring class được suy từ type

```java
Object ten = ConstantBootstraps.getStaticFinal(
        MethodHandles.lookup(),
        "TEN",
        java.math.BigInteger.class);
```

Overload này **không tìm field trong caller class**. Nó suy ra class khai báo field bằng **`type`**:
- Với reference type, tìm field `static final` **trong chính lớp kiểu kết quả**. Ví dụ `BigInteger.TEN` có kiểu `BigInteger`, nên `type=BigInteger.class` hợp lệ.
- Với primitive field, dùng **wrapper class** của primitive làm declaring class. Ví dụ `type=int.class` tìm trong `Integer.class`, nên `name="MAX_VALUE"` có thể trả `Integer.MAX_VALUE`.

Ví dụ:

```java
Object max = ConstantBootstraps.getStaticFinal(
        MethodHandles.lookup(), "MAX_VALUE", int.class);
System.out.println(max); // 2147483647
```

**Sai về ý nghĩa:**

```java
ConstantBootstraps.getStaticFinal(
        MethodHandles.lookup(),
        "GREETING",
        String.class);
```

Nếu field `GREETING` nằm trong `MyApp.class` nhưng không nằm trong `String.class`, lời gọi rút gọn này **không tìm MyApp.GREETING**; nó cố tìm `String.GREETING` và có thể ném **`NoSuchFieldError`**. Phải dùng overload **bốn tham số** với `MyApp.class`.

### 7.3. Những trường hợp lỗi cần phân biệt

| Tình huống | Hành vi theo hợp đồng API |
| --- | --- |
| Field không tồn tại hoặc không khớp name/type | **`NoSuchFieldError`**. |
| Field không phải `final` | **`IncompatibleClassChangeError`**. |
| Field không đủ quyền truy cập trong `lookup` | **`IllegalAccessError`**. |
| Field không phải `static` | Không đáp ứng yêu cầu static final; truy xuất thất bại khi tìm static getter. |
| Class chứa field có initialization phức tạp | Việc đọc giá trị có thể kích hoạt khởi tạo class theo luật JVM. |

**Lưu ý:** `getStaticFinal` trả **giá trị của field**, không trả một `VarHandle` và không cho sửa `final`. Những API bootstrap VarHandle khác cũng tồn tại, nhưng không thuộc bốn phương thức chính của bài.

## 8. Chương trình Java 11 hoàn chỉnh: gọi trực tiếp bốn bootstrap methods

Ví dụ đầu tiên dùng các phương thức Java bình thường để kiểm tra **chữ ký, giá trị, quyền truy cập và exception**. Nó **không tự tạo constant-pool entry `CONSTANT_Dynamic`**; mục 9 sẽ làm điều đó.

Lưu file **`ConstantBootstrapsDirectDemo.java`**:

```java
import java.lang.invoke.ConstantBootstraps;
import java.lang.invoke.MethodHandles;
import java.math.BigInteger;

public class ConstantBootstrapsDirectDemo {
    private enum State { READY, DONE }
    public static final String GREETING = "Xin chao";
    private static final String PRIVATE_NAME = "chi noi bo";
    public static final int MAX_TASKS = 12;
    public static String MUTABLE = "not final";

    private static void expectError(String label, Class<? extends Throwable> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected " + expected.getName());
        } catch (AssertionError error) {
            throw error;
        } catch (Throwable error) {
            if (!expected.isInstance(error)) {
                throw new AssertionError("Expected " + expected.getName()
                        + " but got " + error, error);
            }
            System.out.println(label + "=" + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        System.out.println("nullString=" +
                (ConstantBootstraps.nullConstant(lookup, "anything", String.class) == null));
        System.out.println("nullArray=" +
                (ConstantBootstraps.nullConstant(lookup, "anything", int[].class) == null));

        System.out.println("primitiveI=" +
                (ConstantBootstraps.primitiveClass(lookup, "I", Class.class) == int.class));
        System.out.println("primitiveZ=" +
                (ConstantBootstraps.primitiveClass(lookup, "Z", Class.class) == boolean.class));
        System.out.println("primitiveJ=" +
                (ConstantBootstraps.primitiveClass(lookup, "J", Class.class) == long.class));
        System.out.println("primitiveVoid=" +
                (ConstantBootstraps.primitiveClass(lookup, "V", Class.class) == void.class));

        System.out.println("enumReady=" +
                ConstantBootstraps.enumConstant(lookup, "READY", State.class));

        System.out.println("staticFour=" +
                ConstantBootstraps.getStaticFinal(lookup, "GREETING", String.class,
                        ConstantBootstrapsDirectDemo.class));
        System.out.println("staticPrivate=" +
                ConstantBootstraps.getStaticFinal(lookup, "PRIVATE_NAME", String.class,
                        ConstantBootstrapsDirectDemo.class));
        System.out.println("staticPrimitive=" +
                ConstantBootstraps.getStaticFinal(lookup, "MAX_TASKS", int.class,
                        ConstantBootstrapsDirectDemo.class));
        System.out.println("staticThreeRef=" +
                ConstantBootstraps.getStaticFinal(lookup, "TEN", BigInteger.class));
        System.out.println("staticThreePrimitive=" +
                ConstantBootstraps.getStaticFinal(lookup, "MAX_VALUE", int.class));

        expectError("nullPrimitiveError", IllegalArgumentException.class,
                () -> ConstantBootstraps.nullConstant(lookup, "ignored", int.class));
        expectError("primitiveNameError", IllegalArgumentException.class,
                () -> ConstantBootstraps.primitiveClass(lookup, "int", Class.class));
        expectError("primitiveReturnTypeError", IllegalArgumentException.class,
                () -> ConstantBootstraps.primitiveClass(lookup, "I", Object.class));
        expectError("enumNameError", IllegalArgumentException.class,
                () -> ConstantBootstraps.enumConstant(lookup, "ready", State.class));
        expectError("missingFieldError", NoSuchFieldError.class,
                () -> ConstantBootstraps.getStaticFinal(lookup, "MISSING",
                        String.class, ConstantBootstrapsDirectDemo.class));
        expectError("notFinalError", IncompatibleClassChangeError.class,
                () -> ConstantBootstraps.getStaticFinal(lookup, "MUTABLE",
                        String.class, ConstantBootstrapsDirectDemo.class));
        expectError("privateAccessError", IllegalAccessError.class,
                () -> ConstantBootstraps.getStaticFinal(MethodHandles.publicLookup(),
                        "PRIVATE_NAME", String.class, ConstantBootstrapsDirectDemo.class));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 11 ConstantBootstrapsDirectDemo.java
java ConstantBootstrapsDirectDemo
```

**Stdout đã kiểm chứng** khi biên dịch mức Java 11 bằng `--release 11` và chạy trên JDK 24:

```text
nullString=true
nullArray=true
primitiveI=true
primitiveZ=true
primitiveJ=true
primitiveVoid=true
enumReady=READY
staticFour=Xin chao
staticPrivate=chi noi bo
staticPrimitive=12
staticThreeRef=10
staticThreePrimitive=2147483647
nullPrimitiveError=IllegalArgumentException
primitiveNameError=IllegalArgumentException
primitiveReturnTypeError=IllegalArgumentException
enumNameError=IllegalArgumentException
missingFieldError=NoSuchFieldError
notFinalError=IncompatibleClassChangeError
privateAccessError=IllegalAccessError
```

### 8.1. Ý nghĩa quan trọng của kết quả

- `nullString=true` và `nullArray=true`: null hợp lệ cho reference types kể cả kiểu mảng.
- `primitiveI/Z/J=true`: tên descriptor **một ký tự**, không phải tên từ khóa Java, được chuyển thành primitive class mirrors.
- `primitiveVoid=true`: trong implementation đã kiểm thử, `"V"` mô tả `void.class` ở API trực tiếp; **không phải field type hợp lệ để đặt làm descriptor của dynamic constant**.
- `enumReady=READY`: tên hằng enum khớp chính xác; lowercase `"ready"` bị từ chối.
- `staticFour/staticPrivate/staticPrimitive`: overload 4 đối số đọc trường `static final` của class được chỉ rõ; private đọc thành công vì `lookup` được tạo **trong chính lớp sở hữu field**.
- `staticThreeRef=10`: overload 3 đối số tìm `BigInteger.TEN`. Nó không đi tìm field tên `TEN` ở class caller.
- `staticThreePrimitive=2147483647`: đối với `int.class`, overload 3 đối số dùng wrapper `Integer.class` và tìm `MAX_VALUE`.
- `missingFieldError`, `notFinalError` và `privateAccessError` chứng minh ba nhóm lỗi **khác nhau**. `publicLookup()` không có quyền đọc private field của lớp demo.

`expectError` được viết để **bắt đúng loại lỗi mong đợi**. Nếu việc gọi không ném lỗi hoặc ném loại khác, test ném `AssertionError` và không in PASS giả. Đây là ví dụ học tập, không phải framework unit test thay thế.

## 9. Ví dụ nâng cao: tạo CONSTANT_Dynamic thật, không phụ thuộc thư viện ngoài

Gọi trực tiếp bốn phương thức trong mục 8 chỉ minh họa hành vi từng API. Để kiểm tra **con đường phân giải condy của JVM**, cần có một **class file version 55** chứa:
- Các entry `CONSTANT_Dynamic_info` (tag 17).
- Các `CONSTANT_MethodHandle_info` (tag 15, `REF_invokeStatic`).
- Một `BootstrapMethods` attribute.
- Bytecode `ldc` hoặc `ldc_w` tham chiếu tới các constant pool entries động.

Phần này dùng Java 11 **`DataOutputStream`** để ghi một class file **tối giản** bằng tay, sau đó nạp bằng `ClassLoader#defineClass`. Đây là **ví dụ đào sâu về class-file format**, không phải đề xuất tự viết bytecode assembler cho sản phẩm. Khi triển khai thực tế, nên dùng thư viện sinh bytecode được hỗ trợ và phù hợp phiên bản class file hoặc giao diện tooling hiện đại của môi trường. Không dùng những package `jdk.internal.*` để né kiểm soát module.

Bốn entry trong ví dụ:

| Phương thức do class sinh ra | Tên trong dynamic entry | Field descriptor của entry | Bootstrap |
| --- | --- | --- | --- |
| `readNull()` | `ignored` | `Ljava/lang/String;` | `nullConstant` |
| `readPrimitive()` | `I` | `Ljava/lang/Class;` | `primitiveClass` |
| `readEnum()` | `READY` | `LCondyClassfileDemo$State;` | `enumConstant` |
| `readStatic()` | `GREETING` | `Ljava/lang/String;` | `getStaticFinal`, thêm static argument `CondyClassfileDemo.class` |

Lưu file **`CondyClassfileDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

public class CondyClassfileDemo {
    public enum State { READY, DONE }
    public static final String GREETING = "Xin chao Condy";

    static final class Pool {
        final List<byte[]> entries = new ArrayList<>();

        int add(int tag, Writer data) throws Exception {
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            DataOutputStream d = new DataOutputStream(b);
            d.writeByte(tag);
            data.write(d);
            d.flush();
            entries.add(b.toByteArray());
            return entries.size();
        }

        int utf(String value) throws Exception {
            return add(1, d -> d.writeUTF(value));
        }

        int cls(String name) throws Exception {
            int u = utf(name);
            return add(7, d -> d.writeShort(u));
        }

        int nameType(String name, String descriptor) throws Exception {
            int n = utf(name), t = utf(descriptor);
            return add(12, d -> {
                d.writeShort(n);
                d.writeShort(t);
            });
        }

        int methodHandle(String owner, String method, String descriptor)
                throws Exception {
            int c = cls(owner), nt = nameType(method, descriptor);
            int ref = add(10, d -> {
                d.writeShort(c);
                d.writeShort(nt);
            });
            return add(15, d -> {
                d.writeByte(6); // REF_invokeStatic
                d.writeShort(ref);
            });
        }

        int dynamic(int bootstrapIndex, String name, String descriptor)
                throws Exception {
            int nt = nameType(name, descriptor);
            return add(17, d -> {
                d.writeShort(bootstrapIndex);
                d.writeShort(nt);
            });
        }

        void emit(DataOutputStream d) throws Exception {
            d.writeShort(entries.size() + 1);
            for (byte[] entry : entries) {
                d.write(entry);
            }
        }
    }

    interface Writer {
        void write(DataOutputStream out) throws Exception;
    }

    static byte[] generate() throws Exception {
        Pool cp = new Pool();
        int thisClass = cp.cls("GeneratedCondy");
        int superClass = cp.cls("java/lang/Object");
        int codeName = cp.utf("Code");
        int bootstrapName = cp.utf("BootstrapMethods");
        int methodDesc = cp.utf("()Ljava/lang/Object;");

        String base = "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;)";

        int bsmNull = cp.methodHandle("java/lang/invoke/ConstantBootstraps",
                "nullConstant", base + "Ljava/lang/Object;");
        int bsmPrimitive = cp.methodHandle("java/lang/invoke/ConstantBootstraps",
                "primitiveClass", base + "Ljava/lang/Class;");
        int bsmEnum = cp.methodHandle("java/lang/invoke/ConstantBootstraps",
                "enumConstant", base + "Ljava/lang/Enum;");
        int bsmStatic = cp.methodHandle("java/lang/invoke/ConstantBootstraps",
                "getStaticFinal", "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;Ljava/lang/Class;)"
                + "Ljava/lang/Object;");

        int ownerClass = cp.cls("CondyClassfileDemo");
        String[] names = {"readNull", "readPrimitive", "readEnum", "readStatic"};
        String[] constNames = {"ignored", "I", "READY", "GREETING"};
        String[] types = {
                "Ljava/lang/String;", "Ljava/lang/Class;",
                "LCondyClassfileDemo$State;", "Ljava/lang/String;"
        };

        int[] nameIndices = new int[names.length];
        int[] constIndices = new int[names.length];
        for (int i = 0; i < names.length; i++) {
            nameIndices[i] = cp.utf(names[i]);
            constIndices[i] = cp.dynamic(i, constNames[i], types[i]);
        }

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        DataOutputStream d = new DataOutputStream(out);
        d.writeInt(0xCAFEBABE);
        d.writeShort(0);
        d.writeShort(55); // Java 11 class-file major version
        cp.emit(d);

        d.writeShort(0x0021); // public class + ACC_SUPER
        d.writeShort(thisClass);
        d.writeShort(superClass);
        d.writeShort(0); // interfaces_count
        d.writeShort(0); // fields_count
        d.writeShort(names.length);

        for (int i = 0; i < names.length; i++) {
            d.writeShort(0x0009); // public static
            d.writeShort(nameIndices[i]);
            d.writeShort(methodDesc);
            d.writeShort(1); // Code attribute count

            d.writeShort(codeName);
            d.writeInt(16); // Code payload = 12 + 4 byte instructions
            d.writeShort(1); // max_stack
            d.writeShort(0); // max_locals
            d.writeInt(4); // code_length
            d.writeByte(0x13); // ldc_w
            d.writeShort(constIndices[i]);
            d.writeByte(0xB0); // areturn
            d.writeShort(0); // exception_table_length
            d.writeShort(0); // nested attributes_count
        }

        d.writeShort(1); // class attributes_count
        d.writeShort(bootstrapName);
        d.writeInt(20); // 2 + 4 entries x 4 + 1 argument x 2
        d.writeShort(4); // num_bootstrap_methods
        d.writeShort(bsmNull);
        d.writeShort(0);
        d.writeShort(bsmPrimitive);
        d.writeShort(0);
        d.writeShort(bsmEnum);
        d.writeShort(0);
        d.writeShort(bsmStatic);
        d.writeShort(1);
        d.writeShort(ownerClass);
        d.flush();
        return out.toByteArray();
    }

    static class GeneratedLoader extends ClassLoader {
        GeneratedLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(byte[] code) {
            return defineClass("GeneratedCondy", code, 0, code.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = generate();
        Class<?> klass = new GeneratedLoader(
                CondyClassfileDemo.class.getClassLoader()).define(bytes);

        Method readNull = klass.getMethod("readNull");
        Method readPrimitive = klass.getMethod("readPrimitive");
        Method readEnum = klass.getMethod("readEnum");
        Method readStatic = klass.getMethod("readStatic");

        System.out.println("classfileMajor=55");
        System.out.println("condyNull=" + (readNull.invoke(null) == null));
        System.out.println("condyPrimitive=" + (readPrimitive.invoke(null) == int.class));
        System.out.println("condyEnum=" + (readEnum.invoke(null) == State.READY));
        System.out.println("condyStatic=" + GREETING.equals(readStatic.invoke(null)));
        System.out.println("repeatStaticSame=" +
                (readStatic.invoke(null) == readStatic.invoke(null)));

        if (args.length > 0) {
            java.nio.file.Files.write(java.nio.file.Path.of(args[0]), bytes);
        }
    }
}
```

**Chạy với JDK hỗ trợ Java 11**:

```bash
javac -encoding UTF-8 --release 11 CondyClassfileDemo.java
java CondyClassfileDemo GeneratedCondy.class
javap -v -p GeneratedCondy
```

Lệnh thứ hai ghi class file được tạo ra vào `GeneratedCondy.class` để lệnh `javap` đọc. Không cần tải JAR ngoài; mã thuần Java 11.

**Stdout của lệnh `java` đã kiểm chứng:**

```text
classfileMajor=55
condyNull=true
condyPrimitive=true
condyEnum=true
condyStatic=true
repeatStaticSame=true
```

**Kiểm chứng `javap -v -p` trên class file sinh ra:** có các mục constant pool `Dynamic`, `BootstrapMethods` và lệnh `ldc_w`. Các chỉ số `#nn` trong `javap` thay đổi theo cách tạo constant pool, nên không so sánh chúng theo số cố định.

### 9.1. Giải thích chương trình class file

`Pool.add(tag, ...)` dựng những constant pool entries. Trong đó:

| Tag / kiểu entry | Ý nghĩa |
| --- | --- |
| `1 — CONSTANT_Utf8` | Lưu tên, descriptor và tên attribute. |
| `7 — CONSTANT_Class` | Chỉ tên class, ví dụ `CondyClassfileDemo`. |
| `10 — CONSTANT_Methodref` | Tham chiếu bootstrap method trong `ConstantBootstraps`. |
| `12 — CONSTANT_NameAndType` | Tên dynamic constant + kiểu field descriptor. |
| `15 — CONSTANT_MethodHandle` | Method handle cho phương thức bootstrap static. |
| **`17 — CONSTANT_Dynamic`** | Mục hằng số động được JVM phân giải. |

Chương trình ghi `BootstrapMethods` với **bốn bootstrap specifiers**:
- `nullConstant` nhận ba đối số ngầm định từ JVM.
- `primitiveClass` nhận tên `I` và result type `Class`.
- `enumConstant` nhận `READY` và result type là nested enum `State`.
- `getStaticFinal` overload bốn tham số nhận thêm **static argument `CondyClassfileDemo.class`** để biết class chứa `GREETING`.

Mỗi phương thức `read...` của class sinh ra chứa lệnh `ldc_w` tham chiếu đến dynamic constant rồi `areturn`. Khi gọi qua reflection, **JVM**, không phải một đoạn code Java trực tiếp của `CondyClassfileDemo`, thực hiện bước phân giải dynamic constant.

Dòng `repeatStaticSame=true` chỉ chứng minh hai lần đọc trả về **cùng reference của hằng String đã phân giải** trong ví dụ. Lý do về caching nằm ở hợp đồng JVMS, không dựa duy nhất vào phép so sánh reference. Nếu dùng các bootstrap methods có side effects trong hệ thống thật, phải tính đến khả năng bootstrap chạy đồng thời ở lần phân giải đầu.

### 9.2. Vì sao cần một class loader riêng?

`ClassLoader#defineClass` nạp byte array thành một `Class<?>` mới có tên `GeneratedCondy`. Nó không sửa file JDK hay module khác. Một class đã được JVM nạp theo **class loader + binary name** không thể tùy ý nạp lại bằng cách ghi đè bytecode trong cùng loader; ví dụ dùng một loader mới để tạo class minh họa.

Đây là **thực hành kiểm thử bytecode nội bộ**, không phải phương án tạo class từ byte do người dùng không tin cậy gửi vào. Trong sản phẩm cần xác thực nguồn classfile, quản lý memory/classloader lifecycle và kiểm tra bảo mật.

### 9.3. Đừng nhầm tên phương thức "readStatic" với getStaticFinal

`readStatic()` là **phương thức static** của class được sinh để kích hoạt `ldc_w`. Bootstrap `getStaticFinal` thực sự đọc **field `GREETING` của `CondyClassfileDemo`**. Cờ `static` của phương thức đọc không thay thế yêu cầu trường được đọc phải `static final`.

## 10. Lỗi của bootstrap khi gọi trực tiếp và khi JVM phân giải

Cùng một lỗi logic có thể xuất hiện **khác lớp exception** tùy đường đi.

### 10.1. Gọi trực tiếp

Khi gọi `ConstantBootstraps` như Java method bình thường, bạn quan sát trực tiếp các exception/error nêu trong API Java 11:

| API | Input sai | Lỗi trực tiếp |
| --- | --- | --- |
| `nullConstant` | `type=int.class` hoặc primitive khác | `IllegalArgumentException`. |
| `primitiveClass` | `name="int"` thay vì `"I"` | `IllegalArgumentException`. |
| `primitiveClass` | `type=Object.class` thay vì `Class.class` | `IllegalArgumentException`. |
| `enumConstant` | Không có hằng đúng tên, ví dụ `"ready"` | `IllegalArgumentException`. |
| `enumConstant` | Caller không có quyền truy cập enum/field | `IllegalAccessError`. |
| `getStaticFinal` | Field không tồn tại | `NoSuchFieldError`. |
| `getStaticFinal` | Field không có modifier final | `IncompatibleClassChangeError`. |
| `getStaticFinal` | Lookup không có quyền với class/field | `IllegalAccessError`. |

### 10.2. JVM phân giải CONSTANT_Dynamic

Khi JVM thực hiện bootstrap trong quá trình resolution:

1. JVM phân giải method handle, tên và kiểu; tạo `Lookup` của lớp chứa entry.
2. Bootstrap được gọi với ba tham số đầu và các static arguments.
3. Kết quả được chuyển sang **kiểu của entry `CONSTANT_Dynamic`**.
4. Nếu bootstrap ném **exception không thuộc `Error`** (ví dụ `IllegalArgumentException`), resolution thất bại với **`BootstrapMethodError`** có cause tương ứng.
5. Nếu bootstrap ném **`Error`** (ví dụ một `LinkageError`), quy tắc JVMS có thể truyền lỗi đó trong resolution.
6. Nếu bootstrap trả giá trị không chuyển được sang kiểu của dynamic constant (ví dụ trả `null` cho primitive, gây `NullPointerException` trong chuyển đổi), resolution cũng có thể thất bại với **`BootstrapMethodError`**.

Sau khi một entry condy đã phân giải thất bại, JVM ghi nhớ **lỗi phân giải** cho entry ấy; không xem lần dùng tiếp theo là một lượt retry tùy ý.

**Điểm thực hành:** trong code xử lý việc nạp classfile, không bắt `IllegalArgumentException` rồi nghĩ đã bao phủ mọi lỗi condy runtime. Trường hợp JVM link có thể báo `BootstrapMethodError` hoặc các `LinkageError` khác. Đừng nuốt `Error` toàn cục để tiếp tục ứng dụng trong trạng thái không chắc chắn.

## 11. Phân biệt dynamic constant với final field của Java

Ví dụ:

```java
class Example {
    static final String FIXED = "ABC";
    static final Object CREATED = new Object();
}
```

Cả hai là **`static final`**, nhưng:
- `FIXED` có thể là **compile-time constant variable**, được `javac` dùng/inline theo quy tắc JLS.
- `CREATED` là reference tới object được tạo trong class initialization; nó không phải compile-time constant biểu diễn trực tiếp được bằng literal constant pool đơn giản.
- **Không cái nào bắt buộc khiến `javac --release 11` sinh `CONSTANT_Dynamic`.**

`ConstantBootstraps.getStaticFinal` đọc field `static final` theo cấu hình thích hợp, nhưng **không biến field đó thành một tính năng condy chỉ bằng cách gọi phương thức**. Chỉ khi một class file có `CONSTANT_Dynamic_info` dùng bootstrap đó, kết quả mới tham gia cơ chế resolution/caching của dynamic constant.

Một vấn đề tương tự: `enumConstant` không thay thế enum declaration và `primitiveClass` không tạo một kiểu nguyên thủy mới. Chúng chỉ hỗ trợ biểu diễn/đọc giá trị qua cơ chế bootstrap.

## 12. Khi nào thực tế nên dùng từng bootstrap?

| Nhu cầu | Bootstrap phù hợp | Khi nào không cần |
| --- | --- | --- |
| Sinh bytecode có constant `null` với descriptor reference | `nullConstant` | Java source chỉ cần gán `null`. |
| Sinh bytecode phải mang `Class<?>` của primitive dựa trên descriptor | `primitiveClass` | Source có thể viết thẳng `int.class`. |
| Sinh bytecode tham chiếu một enum singleton theo tên | `enumConstant` | Code bình thường dùng `State.READY` hoặc `Enum.valueOf`. |
| Sinh bytecode cần giá trị `static final` có declaring class và quyền phù hợp | `getStaticFinal` (4 args) | Code Java bình thường có thể đọc field trực tiếp. |
| Sinh bytecode dùng constant instance kiểu self-declared, ví dụ `BigInteger.TEN` | `getStaticFinal` (3 args) | Source thường viết `BigInteger.TEN`. |
| Muốn tự sinh khóa/đối tượng mutable mỗi lần gọi | Không dùng condy như factory mỗi lần | Dùng constructor/factory method. |
| Muốn gọi method với arguments và nhận kết quả mỗi lần | Không nhầm `invokedynamic` với `CONSTANT_Dynamic` | Dùng API gọi/phương thức phù hợp. |

Các công cụ sinh bytecode, compilers cho ngôn ngữ khác và frameworks tối ưu bootstrap là đối tượng thường cần hiểu cơ chế này. Với ứng dụng nghiệp vụ Java tiêu chuẩn, **mã trực tiếp rõ ràng thường tốt hơn** việc tự viết classfile.

## 13. Những hiểu lầm và lỗi phổ biến

| Hiểu nhầm | Điều đúng |
| --- | --- |
| Java 11 có từ khóa source `condy` hoặc `dynamic constant`. | Không có từ khóa Java source tương ứng; đây là cấu trúc **class file/JVM**. |
| Gọi trực tiếp `ConstantBootstraps.*` tự tạo `CONSTANT_Dynamic_info`. | Không. Chỉ là gọi một phương thức Java bình thường. |
| `nullConstant` chấp nhận `int.class` và tự cho giá trị 0. | Không; chỉ reference types và trả `null`. |
| Kiểu mảng `int[]` là primitive. | Không; `int[].class` là reference type. |
| `primitiveClass` nhận tên Java `"int"`. | Không; nhận **descriptor `"I"`**. |
| `primitiveClass(..., "I", int.class)` là hợp đồng đúng. | Không; `type` của bootstrap phải là **`Class.class`**. |
| `"V"` có thể làm field descriptor của condy. | Không; void không là field type, dù API trực tiếp có thể trả `void.class` cho `"V"`. |
| `primitiveClass("I")` trả `Integer.class`. | Không; trả `int.class`. |
| `enumConstant` tìm hằng theo tên enum class. | `name` là tên **member**, ví dụ `READY`. |
| `enumConstant` không phân biệt hoa/thường. | Có phân biệt; `"ready"` không bằng `"READY"`. |
| `getStaticFinal(lookup,"X",String.class)` tìm field `X` trong caller. | Overload 3 args tìm trong **`String.class`**. |
| `getStaticFinal` đọc được mọi static field. | Chỉ chấp nhận `static final` hợp lệ, với lookup có quyền. |
| `getStaticFinal` bypass private nhờ dùng bootstrap method public. | Không; access control dựa trên `Lookup`. |
| `getStaticFinal` chỉ dùng cho primitive compile-time constants. | Có thể đọc cả field kiểu object, ví dụ `BigInteger.TEN`. |
| Bất kỳ exception direct-call nào cũng xuất hiện giống hệt trong condy resolution. | JVM có quy tắc **`BootstrapMethodError`/`LinkageError`** khi resolution. |
| Một dynamic constant được tính lại trên mỗi lệnh `ldc`. | Sau resolution thành công, JVM dùng kết quả đã ghi nhớ cho **cùng entry**. |
| Bootstrap chắc chắn chỉ chạy một lần kể cả race ở lần đầu. | JVM có thể gọi bootstrap đồng thời ở initial resolution; logic tùy chỉnh phải thread-safe. |
| Mỗi hằng `static final` Java 11 là `CONSTANT_Dynamic`. | Không. Đây là hai khái niệm khác nhau. |
| `CONSTANT_Dynamic` và `invokedynamic` giống nhau vì cùng có bootstrap. | Một bên tạo **value**, một bên liên kết **call site**. |

## 14. Bài tập tự luyện kèm đáp án

**Câu 1.** `nullConstant(lookup, "x", String.class)` trả gì?

**Đáp án:** `null`. `lookup` và `name` không được sử dụng, còn `type` phải là reference type.

**Câu 2.** `nullConstant(lookup, "x", int[].class)` có hợp lệ không?

**Đáp án:** Có. `int[]` là reference type, dù thành phần mảng là primitive `int`.

**Câu 3.** `nullConstant(lookup, "x", int.class)` có trả 0 không?

**Đáp án:** Không. Gọi trực tiếp ném `IllegalArgumentException`.

**Câu 4.** `primitiveClass(lookup, "int", Class.class)` có đúng không?

**Đáp án:** Không. `name` cần descriptor JVM `"I"`; `"int"` gây `IllegalArgumentException`.

**Câu 5.** Trong một dynamic constant dùng `primitiveClass` để trả `int.class`, descriptor của **kết quả** là `I` hay `Ljava/lang/Class;`?

**Đáp án:** **`Ljava/lang/Class;`**, vì kết quả là một đối tượng `Class`. Tên dynamic constant `"I"` mô tả kiểu primitive được phản chiếu.

**Câu 6.** `"V"` của `primitiveClass` có nghĩa có thể tạo condy với field type void không?

**Đáp án:** Không. `void.class` là một class mirror đặc biệt; JVM không cho `V` làm field descriptor của constant.

**Câu 7.** `enumConstant(lookup, "READY", State.class)` tạo một instance `State` mới không?

**Đáp án:** Không. Nó trả **enum constant hiện có** `State.READY`.

**Câu 8.** `enumConstant(lookup, "ready", State.class)` khi enum chỉ có `READY` thì sao?

**Đáp án:** Gọi trực tiếp ném `IllegalArgumentException` vì tên phân biệt hoa/thường.

**Câu 9.** Muốn đọc `private static final String SECRET` ở `MyApp` bằng overload 4 args cần gì?

**Đáp án:** `name="SECRET"`, `type=String.class`, `declaringClass=MyApp.class` và một `Lookup` có **quyền truy cập private** phù hợp.

**Câu 10.** Vì sao `getStaticFinal(lookup,"MAX_VALUE",int.class)` có thể thành công nhưng `getStaticFinal(lookup,"MAX_TASKS",int.class)` không tìm field ở caller?

**Đáp án:** Overload 3 args dùng **`Integer.class`** làm declaring class cho primitive `int`. Field `MAX_TASKS` ở caller cần overload 4 args.

**Câu 11.** Field tồn tại nhưng không `final` thì sao?

**Đáp án:** `getStaticFinal` có thể ném `IncompatibleClassChangeError`; đây không phải cơ chế đọc mọi static mutable field.

**Câu 12.** Một bootstrap trực tiếp ném `IllegalArgumentException`. Khi JVM phân giải condy có thể xuất hiện lỗi nào?

**Đáp án:** **`BootstrapMethodError`** với nguyên nhân là exception được ném, theo hợp đồng JVMS khi bootstrap không thành công bằng exception không phải Error.

**Câu 13.** Sau lần đầu phân giải thành công, cùng entry condy có nhất thiết gọi bootstrap lần nữa mỗi khi `ldc_w` không?

**Đáp án:** Không. JVM ghi nhớ kết quả; những lượt dùng tiếp theo của cùng entry nhận cùng resolved value.

**Câu 14.** Để chứng minh một class file thực sự dùng condy, chỉ nhìn dòng in từ `nullConstant` trực tiếp đã đủ chưa?

**Đáp án:** Chưa. Cần class file có `CONSTANT_Dynamic_info`, `BootstrapMethods` và bytecode sử dụng entry; kiểm tra bằng `javap -v` hoặc công cụ tương đương.

**Câu 15.** `getStaticFinal` có đọc được `BigInteger.TEN` với bản 3 args không?

**Đáp án:** Có, khi dùng tên `"TEN"` và type `BigInteger.class` phù hợp. Bản 3 args chọn chính lớp `BigInteger` làm nơi khai báo field.

**Câu 16.** JDK 11 `javac` có bắt buộc phát sinh condy cho mọi `static final` không?

**Đáp án:** Không. `static final` là khai báo field Java; condy là cơ chế class-file riêng, phổ biến trong bytecode generation/language tooling.

## 15. Tổng kết và nguồn tài liệu chuẩn

- Java 11 đưa **`CONSTANT_Dynamic_info`** vào class file thông qua JEP 309; những bootstrap methods trong **`java.lang.invoke.ConstantBootstraps`** vẫn phù hợp.
- `nullConstant` trả `null` chỉ cho **reference types**.
- `primitiveClass` nhận **descriptor JVM** (ví dụ `"I"`), trả `int.class` khi `type=Class.class`.
- `enumConstant` lấy đúng enum singleton theo **tên hằng**, và chịu kiểm tra quyền truy cập.
- `getStaticFinal` đọc **static final field**; bản 4 args chỉ rõ declaring class, bản 3 args suy từ result type (hoặc wrapper cho primitive).
- Phải phân biệt **gọi method Java trực tiếp** với **JVM resolution của dynamic constant**. JVM có quy tắc ghi nhớ kết quả/lỗi, kiểm tra kiểu và `BootstrapMethodError`.
- Java source code không có cú pháp trực tiếp bắt buộc để phát sinh condy; chương trình thứ hai chứng minh class-file mechanism bằng cách sinh bytecode Java 11 thực.
- Không dùng condy như công cụ vượt quyền `private`, khởi tạo đối tượng mutable mỗi lần, hay giải pháp thay thế mặc định cho `static final`/`enum` bình thường.

**Tài liệu chính thức (API và tiêu chuẩn đang còn hiệu lực):**

- [Oracle Java SE 11 — ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html).
- [Oracle Java SE 11 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Oracle Java SE 11 — JVMS `4.4.10 CONSTANT_Dynamic_info](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10).
- [Oracle Java SE 11 — JVMS `4.7.23 BootstrapMethods](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.23).
- [Oracle Java SE 11 — JVMS `5.4.3.6 Dynamic Constant Resolution](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6).
- [Oracle Java SE 11 — JVMS `4.3.2 Field Descriptors](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.3.2).
- [OpenJDK — JEP 309 Dynamic Class-File Constants](https://openjdk.org/jeps/309).