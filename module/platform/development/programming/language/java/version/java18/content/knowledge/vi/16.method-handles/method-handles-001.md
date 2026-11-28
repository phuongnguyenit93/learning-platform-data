# MethodHandle là tham chiếu thực thi có kiểu và mối liên hệ với cơ chế reflection từ Java 18

## 1. Mục tiêu và bối cảnh

Trong chương **MethodHandle** của module `JAVA_VERSION_JAVA18`, chúng ta tìm hiểu một cách biểu diễn thao tác thực thi động nhưng có **kiểu lời gọi rõ ràng**: `java.lang.invoke.MethodHandle`. Kiến thức này vẫn áp dụng trên các JDK hiện đại, khi ứng dụng cần gọi phương thức, truy cập thành viên hoặc xây dựng bộ điều phối lời gọi theo kiểu dữ liệu tại runtime.

Sau bài học, bạn có thể:

- Giải thích `MethodHandle` biểu diễn **một thao tác có thể gọi** và vì sao mỗi handle gắn với `MethodType`.
- Tạo handle bằng `MethodHandles.Lookup` cho phương thức `static`, phương thức instance và getter; phân biệt kiểu phương thức khi tìm với kiểu của handle sau khi tìm.
- So sánh `invokeExact`, `invoke`, `asType` và `bindTo` qua ví dụ chạy độc lập.
- Phân biệt kiểm tra quyền khi **lấy handle** với lỗi **không khớp kiểu khi gọi handle**.
- Hiểu chính xác mối liên hệ giữa `MethodHandle` và cơ chế core reflection được triển khai lại trong Java 18 (JEP 416).

**Điểm cần làm rõ về lịch sử:** `MethodHandle` xuất hiện từ Java 7. **Java 18 không giới thiệu API này lần đầu**; JEP 416 trong Java 18 triển khai lại các phần của core reflection dựa trên method handles và variable handles. Bài này chỉ sử dụng API công khai còn được hỗ trợ, tránh các kỹ thuật truy cập nội bộ hoặc giả định về chi tiết cài đặt của JDK.

## 2. Khái niệm: tham chiếu thực thi có kiểu

Một `MethodHandle` là đối tượng có thể gọi, biểu diễn trực tiếp một thao tác nền như gọi phương thức, tạo đối tượng hoặc đọc/ghi trường tùy cách thu nhận handle. Không nên hình dung nó chỉ là tên phương thức dạng chuỗi: handle đã mang theo **thao tác đích** cùng với kiểu tham số và kết quả.

Ba khái niệm thường đi cùng nhau:

| Thành phần | Vai trò |
| --- | --- |
| `MethodHandle` | Đối tượng biểu diễn thao tác có thể thực thi; gọi bằng `invokeExact`/`invoke` hoặc các phương thức kết hợp. |
| `MethodType` | Mô tả kiểu trả về và danh sách kiểu tham số của một handle, ví dụ `(int,int)int` hoặc `(Counter,int)int`. |
| `MethodHandles.Lookup` | Đối tượng dùng để tìm hoặc tạo handle trong phạm vi **quyền truy cập của lớp tạo lookup**. |

Giả sử có phương thức:

```java
public static int add(int left, int right) {
    return left + right;
}
```

Để tìm phương thức đó, có thể dùng:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodType signature = MethodType.methodType(
        int.class, int.class, int.class);

MethodHandle handle = lookup.findStatic(
        Example.class, "add", signature);
```

Ở đây `Example` là tên lớp chứa `add` trong tình huống minh họa. `MethodType.methodType(int.class, int.class, int.class)` có nghĩa **trả về `int`, nhận hai tham số `int`**; tham số đầu tiên của `methodType` luôn là **kiểu trả về**, không phải receiver.

Bằng `handle.type()`, ta xem được hợp đồng lời gọi của handle:

```text
(int,int)int
```

`MethodType` mô tả **kiểu JVM**, không mang tên biến `left`/`right`, tên phương thức `add` hay thông tin generic như `List<String>`. Một handle có thể được áp dụng thêm bộ chuyển đổi, tạo ra handle mới với kiểu khác mà vẫn hướng tới thao tác gốc.

## 3. Từ `Lookup` đến handle: static, instance và field

### 3.1. Tìm một phương thức `static`

```java
MethodHandle add = MethodHandles.lookup().findStatic(
        Example.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));
```

Vì `add` là `static`, kiểu handle là `(int,int)int`. Khi gọi handle không cần một đối tượng `Example` làm receiver.

### 3.2. Tìm một phương thức instance

Giả sử trong lớp `Counter` có:

```java
int increase(int amount) {
    return amount;
}
```

Tìm handle:

```java
MethodHandle increase = MethodHandles.lookup().findVirtual(
        Counter.class,
        "increase",
        MethodType.methodType(int.class, int.class));
```

`MethodType` truyền vào `findVirtual` mô tả **tham số khai báo của phương thức và kiểu trả về**, chưa gồm receiver. Nhưng kiểu **handle được trả về** bao gồm receiver ở vị trí đầu:

```text
(Counter,int)int
```

Do đó, lời gọi tương ứng có dạng `increase.invokeExact(counter, 5)`, với `counter` là một instance của `Counter`.

### 3.3. Truy cập field qua handle

Các factory `findGetter`, `findSetter`, `findStaticGetter` và `findStaticSetter` tạo ra handle cho thao tác đọc/ghi trường, với chữ ký phản ánh receiver và kiểu trường.

Ví dụ:

```java
MethodHandle getter = lookup.findGetter(
        Counter.class, "value", int.class);
```

Nếu `value` là một trường instance kiểu `int`, handle có kiểu `(Counter)int`. Đây là kiểu **thực thi thao tác đọc**, khác với đối tượng metadata `java.lang.reflect.Field`.

JDK hiện đại cũng có `VarHandle` để biểu diễn các chế độ truy cập biến. Khi bài toán cần thao tác truy cập field có ngữ nghĩa bộ nhớ hoặc đồng bộ rõ ràng, cần nghiên cứu `VarHandle` riêng; không suy diễn rằng mọi thao tác trên field nên dùng `MethodHandle`.

## 4. `invokeExact`: kiểm tra kiểu lời gọi đúng tuyệt đối

`invokeExact` là một phương thức **signature-polymorphic**. Trình biên dịch Java xác định kiểu lời gọi từ **kiểu đối số tại điểm gọi** và **kiểu kết quả mà đoạn mã yêu cầu**. Để gọi thành công, kiểu đó phải khớp **chính xác** với `MethodHandle.type()`.

Ví dụ handle có kiểu `(int,int)int`:

```java
int sum = (int) add.invokeExact(2, 3);  // OK: (int,int)int
```

Trường hợp sau không yêu cầu cùng kiểu trả về:

```java
long sum = (long) add.invokeExact(2, 3); // WrongMethodTypeException
```

Dù Java có phép widening `int → long`, `invokeExact` **không tự đổi** kiểu trả về của handle. Kiểu lời gọi ở câu thứ hai là `(int,int)long`, trong khi kiểu thật của handle là `(int,int)int`.

Tương tự, truyền `Integer` vào vị trí cần `int` không phải lời gọi khớp hoàn toàn theo nghĩa của `invokeExact`. Dùng đúng primitive hoặc chủ động thích nghi handle khi cần thay đổi kiểu.

Cần nhớ cả **kiểu trả về** cũng được kiểm tra: lời gọi `add.invokeExact(2, 3);` như một statement không lấy kết quả sẽ yêu cầu kiểu trả về `void`, nên không hợp lệ cho handle trả `int`.

## 5. `invoke`, `asType` và `bindTo`: thích nghi có kiểm soát

### 5.1. `invoke` thích nghi kiểu lời gọi

`invoke` cũng là signature-polymorphic nhưng có thể áp dụng các chuyển đổi mà `MethodHandle.asType` cho phép. Ví dụ với `add` có kiểu `(int,int)int`:

```java
long result = (long) add.invoke(2, 3); // 5L
```

Ở đây điểm gọi mong `(int,int)long`; việc widening kết quả `int → long` có thể thực hiện theo quy tắc thích nghi. Không nên hiểu `invoke` là “thử mọi kiểu” hoặc có thể tự chuyển chuỗi `"3"` thành số `int`. Chuyển đổi không được hỗ trợ có thể dẫn đến `WrongMethodTypeException` hoặc lỗi kiểu tại runtime, tùy trường hợp.

### 5.2. `asType` trả về handle thích nghi

Để chủ động mô tả kiểu mong muốn, dùng `asType`:

```java
MethodHandle asLong = add.asType(
        MethodType.methodType(long.class, int.class, int.class));

System.out.println(asLong.type()); // (int,int)long
long result = (long) asLong.invokeExact(4, 5); // 9
```

`asType` **không đổi đối tượng `add` gốc**. Nó trả về một handle khác thực hiện phép thích nghi khi gọi. Nếu không có cách chuyển đổi hợp lệ giữa các kiểu, việc tạo handle thích nghi có thể ném `WrongMethodTypeException`. Một phép chuyển đổi hợp lệ về mặt kiểu vẫn có thể mất độ chính xác, ví dụ giá trị nguyên lớn sang số thực dấu phẩy động.

### 5.3. `bindTo` gắn sẵn đối số tham chiếu đầu tiên

Nếu `increase` có kiểu `(Counter,int)int`, có thể cố định receiver:

```java
Counter counter = new Counter(10);
MethodHandle bound = increase.bindTo(counter);
System.out.println(bound.type()); // (int)int
int value = (int) bound.invokeExact(5);
```

`bindTo` nhận một **reference argument** khớp với tham số đầu của handle. Trong ví dụ, `Counter` là tham chiếu nên hợp lệ. Sau khi bind, caller không cần truyền receiver nữa. Đối với các thao tác kết hợp phức tạp, `MethodHandles` còn có nhiều combinator khác như `insertArguments`, `filterArguments`, `guardWithTest` và `permuteArguments`; nên học chúng sau khi nắm chắc quy tắc kiểu cơ bản.

## 6. Ví dụ đầy đủ có thể chạy: `MethodHandleIntro.java`

Ví dụ sau chỉ dùng thư viện chuẩn và cú pháp được hỗ trợ trên JDK 18+.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.Method;

public final class MethodHandleIntro {

    public static int add(int a, int b) {
        return a + b;
    }

    static final class Counter {
        private int value;

        Counter(int initial) {
            this.value = initial;
        }

        int increase(int amount) {
            value += amount;
            return value;
        }
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("JDK: " + Runtime.version());

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType addType =
                MethodType.methodType(int.class, int.class, int.class);

        // Static handle: (int,int)int
        MethodHandle add = lookup.findStatic(
                MethodHandleIntro.class, "add", addType);

        System.out.println("add type: " + add.type());
        int exact = (int) add.invokeExact(2, 3);
        System.out.println("invokeExact: " + exact); // 5

        long adaptedCall = (long) add.invoke(2, 3);
        System.out.println("invoke adapted return: " + adaptedCall); // 5

        MethodHandle longResult = add.asType(
                MethodType.methodType(long.class, int.class, int.class));
        long explicitAdaptation = (long) longResult.invokeExact(4, 5);
        System.out.println("asType result: " + explicitAdaptation); // 9

        try {
            long wrong = (long) add.invokeExact(2, 3);
            throw new AssertionError("Expected WrongMethodTypeException: "
                    + wrong);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong invokeExact: "
                    + expected.getClass().getSimpleName());
        }

        // Virtual handle: (Counter,int)int
        MethodHandle increase = lookup.findVirtual(
                Counter.class, "increase",
                MethodType.methodType(int.class, int.class));

        Counter counter = new Counter(10);
        System.out.println("increase type: " + increase.type());

        int next = (int) increase.invokeExact(counter, 5);
        System.out.println("increase: " + next); // 15

        MethodHandle bound = increase.bindTo(counter);
        System.out.println("bound type: " + bound.type());
        int afterBind = (int) bound.invokeExact(2);
        System.out.println("bound increase: " + afterBind); // 17

        MethodHandle getter = lookup.findGetter(
                Counter.class, "value", int.class);
        int fieldValue = (int) getter.invokeExact(counter);
        System.out.println("getter: " + fieldValue); // 17

        // So sánh hình thức lời gọi core reflection.
        Method method = MethodHandleIntro.class.getDeclaredMethod(
                "add", int.class, int.class);
        Object reflected = method.invoke(null, 2, 3);
        System.out.println("Method.invoke result class: "
                + reflected.getClass().getSimpleName()); // Integer
        System.out.println("Method.invoke value: " + reflected); // 5
    }
}
```

Chạy từ thư mục chứa file:

```shell
java -version
javac -version
javac -encoding UTF-8 MethodHandleIntro.java
java MethodHandleIntro
```

Các dòng trọng tâm cần thấy (phần phiên bản JDK phụ thuộc máy):

```text
add type: (int,int)int
invokeExact: 5
invoke adapted return: 5
asType result: 9
wrong invokeExact: WrongMethodTypeException
increase type: (MethodHandleIntro$Counter,int)int
increase: 15
bound type: (int)int
bound increase: 17
getter: 17
Method.invoke result class: Integer
Method.invoke value: 5
```

Tên hiển thị của kiểu `Counter` bên trong `MethodType.toString()` có thể dùng dạng tên binary (`MethodHandleIntro$Counter`). Các phép thử cần khẳng định **số lượng/kiểu tham số, kiểu trả về và kết quả** thay vì phụ thuộc vào một chuỗi mô tả tên lớp được định dạng cứng.

**Vì sao `Lookup` đọc được `private int value`?** `Counter` là lớp lồng trong `MethodHandleIntro`; chúng là **nestmates**, nên lookup được tạo trong lớp bao ngoài có quyền truy cập phù hợp đối với private member của lớp lồng. Trường hợp này không minh họa vượt qua ranh giới module.

## 7. Quyền truy cập: `Lookup` không phải công tắc bỏ bảo vệ

`MethodHandles.lookup()` tạo một `Lookup` mang quyền truy cập phù hợp với lớp caller. Khi gọi `findStatic`, `findVirtual`, `findGetter` hoặc `findConstructor`, JVM kiểm tra quyền của lookup đối với thành viên mục tiêu.

- Nếu phương thức hoặc field không tồn tại với tên/chữ ký yêu cầu, thao tác tìm có thể ném `NoSuchMethodException` hoặc `NoSuchFieldException`.
- Nếu lookup không có quyền truy cập mục tiêu, thao tác tìm có thể ném `IllegalAccessException`.
- Nếu tìm được handle nhưng điểm gọi không khớp kiểu, `invokeExact` có thể ném `WrongMethodTypeException`.
- Nếu chính thao tác đích ném ngoại lệ, lời gọi qua handle truyền ngoại lệ đó đến caller; mã gọi phải xử lý phù hợp.

Với named module, **`exports` và `opens` có vai trò khác nhau**:

| Tình huống | API nên xem xét | Điều kiện tiêu biểu |
| --- | --- | --- |
| Gọi thành viên `public` của lớp `public` ở package được export | `MethodHandles.lookup().findVirtual(...)` hoặc `publicLookup()` khi phù hợp | Lớp/field/method phải thực sự có quyền truy cập công khai và package được export cho caller. |
| Tìm private member của lớp trong **cùng module**, khi lookup có đủ quyền | `lookup` hoặc `privateLookupIn` khi phù hợp | Vẫn tuân theo quyền của lớp caller; không đồng nghĩa mọi lớp cùng module trực tiếp đọc được private member. |
| Deep access vào package ở **module khác** | `MethodHandles.privateLookupIn(Target.class, lookup)` | Package đích phải được **opened** cho module caller và lookup nguồn cần có quyền thích hợp. |
| Package của module khác không export/open đúng phạm vi | Không có phép tìm handle hợp lệ để bỏ qua bảo vệ một cách tùy ý | Cần API công khai hoặc điều chỉnh descriptor có chủ đích. |

Ví dụ giả định một module `library` có khai báo:

```java
module library {
    exports lib.api;
    opens lib.internal to tool;
}
```

Module `tool` có `requires library;`, và có thể dùng `privateLookupIn` với lớp thuộc `lib.internal` khi có các điều kiện quyền cần thiết. `opens lib.internal to tool` là khả năng deep reflection cho module `tool`; **không** biến `lib.internal` thành package cho phép import API public từ `tool`. Không thêm tùy chọn mở module rộng rãi chỉ để ví dụ chạy.

Một handle đã lấy thành công mang khả năng gọi tới mục tiêu trong phạm vi quyền được cấp khi tạo. Việc truyền handle cho mã khác có thể trao quyền thực thi thao tác đó; vì vậy tránh vô tình phát tán handle tới thành viên nhạy cảm trong thiết kế thư viện/plugin.

## 8. So sánh `MethodHandle` với `Method.invoke`

Cùng là cơ chế gọi động, nhưng hai API có mục tiêu và hợp đồng khác nhau:

| Tiêu chí | `MethodHandle` | `java.lang.reflect.Method` |
| --- | --- | --- |
| Biểu diễn chính | Một thao tác thực thi có kiểu `MethodType`. | Metadata của phương thức: tên, modifier, tham số, chú thích... |
| Thu nhận | `MethodHandles.Lookup` và factory method phù hợp. | `Class.getMethod`/`getDeclaredMethod` và các API reflection. |
| Kiểu lời gọi | `invokeExact` yêu cầu khớp chính xác; `invoke` cho phép thích nghi theo quy tắc. | `invoke(Object, Object...)` nhận đối số dưới dạng `Object`/`Object[]`; thực hiện kiểm tra, chuyển đổi theo hợp đồng reflection. |
| Primitive result | Có thể trả thẳng primitive theo `MethodType`. | Kết quả primitive được boxing khi trả về `Object`. |
| Ngoại lệ từ mã đích | Được truyền trực tiếp qua lời gọi handle. | Được gói trong `InvocationTargetException`. |
| Truy cập member | Quyền của `Lookup` được kiểm tra khi tạo handle. | Quyền được xét theo hợp đồng reflection và cấu hình `AccessibleObject`. |
| Thao tác kết hợp | `asType`, `bindTo` và các combinator tạo pipeline lời gọi. | Chủ yếu cung cấp metadata và giao diện gọi phản chiếu trực tiếp. |

Ví dụ phân biệt ngoại lệ:

```java
public static void fail() {
    throw new IllegalStateException("boom");
}
```

Nếu tìm được handle cho `fail` và gọi đúng kiểu, `IllegalStateException` được truyền trực tiếp. Với `Method.invoke`, `IllegalStateException` của phương thức đích nằm trong `InvocationTargetException.getCause()`. Điều này ảnh hưởng tới cách thiết kế xử lý lỗi khi xây dựng framework.

Không nên mặc định `MethodHandle` luôn nhanh hơn reflection trong mọi phép đo. Hiệu năng phụ thuộc độ ổn định của call site, cách JIT tối ưu hóa, kiểu handle, chi phí chuyển đổi, điều kiện warmup và cách benchmark. Trên các JDK hiện đại, core reflection và method handles còn dùng chung một phần cơ chế nội bộ.

## 9. Liên hệ chính xác với Java 18 và JEP 416

**JEP 416 — Reimplement Core Reflection with Method Handles** là thay đổi triển khai trong Java 18. Nó làm cho cơ chế `java.lang.reflect` bên trong JDK dựa vào các công cụ của `java.lang.invoke`: method handles cho các lời gọi phương thức và constructor, variable handles cho truy cập field.

Điều này mang các hệ quả học thuật quan trọng:

1. **API reflection không bị thay bằng API mới.** Người dùng vẫn có `Method.invoke`, `Constructor.newInstance`, `Field.get`/`set` với hợp đồng công khai của chúng.
2. **`MethodHandle` không phải tính năng được sinh ra từ Java 18.** JEP 416 thay đổi cách cài đặt core reflection để tận dụng nền tảng đã có.
3. **Không suy diễn hợp đồng public từ chi tiết cài đặt.** Việc nội bộ dùng handle không làm `Method.invoke` có cùng kiểu trả về hoặc cơ chế bọc ngoại lệ như `invokeExact`.
4. **Kiểm chứng trên đúng JDK sử dụng.** Đo hiệu năng hoặc hành vi trong một runtime không đại diện cho mọi JDK; dùng `java -version`, kiểm tra cấu hình module và viết test theo contract public.

Sơ đồ quan hệ khái quát:

```text
Ứng dụng của bạn
   |                                   |
   v                                   v
java.lang.reflect                    java.lang.invoke
Method / Constructor / Field          MethodHandle / VarHandle
   |                                   ^
   |  JEP 416 (Java 18): tái triển khai |
   +-----------------------------------+
                     |
                     v
          Cơ chế thực thi của JVM/JDK
```

Sơ đồ biểu diễn ý tưởng kiến trúc, không phải chi tiết cố định về toàn bộ pipeline tối ưu hóa của JVM.

## 10. Các sai lầm thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `WrongMethodTypeException` tại `invokeExact` | Kiểu đối số hoặc **kiểu kết quả tại call site** không khớp `handle.type()`. | In `handle.type()`; kiểm tra cast của kết quả, primitive/reference và receiver. |
| `WrongMethodTypeException` khi `asType` | Không có chuyển đổi được hỗ trợ giữa kiểu gốc và kiểu mới. | Đối chiếu từng tham số, kiểu trả về và quy tắc `asType`. |
| `ClassCastException` khi `invoke` | Bộ chuyển đổi tham chiếu tồn tại về mặt kiểu nhưng giá trị runtime không thích hợp. | Kiểm tra kiểu thực của đối tượng và phép chuyển đổi đã yêu cầu. |
| `NoSuchMethodException` từ `findStatic`/`findVirtual` | Sai tên, sai `MethodType`, hoặc chọn nhầm giữa static và instance. | Xem chữ ký thật; nhớ không ghi receiver trong `methodType` truyền cho `findVirtual`. |
| `IllegalAccessException` khi tìm handle | `Lookup` không có quyền với member/module. | Kiểm tra lớp tạo lookup, visibility, `exports`, `opens` và JPMS. |
| `ClassCastException` sau `Method.invoke` | Kết quả primitive đã boxing thành wrapper, cast sang sai wrapper. | Xem kiểu field/method trả về và kiểu wrapper thực tế. |
| Handle gắn receiver nhưng vẫn truyền receiver lúc gọi | `bindTo` đã loại tham số đầu khỏi kiểu handle. | In lại `bound.type()` sau khi bind. |

Lưu ý thêm: `MethodHandle.invokeExact` và `invoke` có khai báo ném `Throwable`. Trong ví dụ học thuật, `main(...) throws Throwable` giữ mã ngắn. Trong ứng dụng thực tế, hãy bắt hoặc khai báo loại ngoại lệ phù hợp với thao tác đích thay vì che lấp các lỗi lập trình khi dùng handle.

## 11. Bài tập thực hành

1. Chạy `MethodHandleIntro.java` trên JDK đang sử dụng, ghi lại `java -version`, `add.type()`, `increase.type()` và `bound.type()`.
2. Đổi `int exact = (int) add.invokeExact(2, 3);` thành `long exact = (long) add.invokeExact(2, 3);`, chạy lại để xác nhận `WrongMethodTypeException`. Giải thích vì sao phép `int → long` hợp lệ ở `invoke` nhưng không áp dụng tự động với `invokeExact`.
3. Tạo handle getter cho `Counter.value` và handle setter với `findSetter`, ghi giá trị `42`, sau đó đọc lại. Hãy dự đoán chữ ký `(Counter,int)void` của setter trước khi gọi.
4. Dùng `MethodHandles.lookup().findStatic` để tìm một phương thức không tồn tại hoặc sai chữ ký. Phân biệt `NoSuchMethodException` tại thời điểm tìm với `WrongMethodTypeException` tại thời điểm gọi.
5. Viết một phương thức `throw new IllegalStateException("boom")`, gọi qua `MethodHandle` và `Method.invoke`, so sánh dạng ngoại lệ mà caller quan sát.
6. Giải thích vì sao việc dùng `MethodHandle` trong code ứng dụng không yêu cầu Java 18, nhưng khi nghiên cứu **cách JDK triển khai core reflection**, Java 18/JEP 416 là mốc quan trọng.

### Tự kiểm tra

**Câu 1.** `MethodHandle` có đơn giản là `Method` được đổi tên không?

**Trả lời:** Không. `MethodHandle` là tham chiếu thực thi với kiểu lời gọi xác định; `Method` là metadata reflection có giao diện `invoke(Object, Object...)`. Các hợp đồng trả về, chuyển đổi và ngoại lệ khác nhau.

**Câu 2.** Với `findVirtual(Counter.class, "increase", methodType(int.class, int.class))`, kiểu handle nhận được là gì?

**Trả lời:** `(Counter,int)int`. Receiver `Counter` được thêm vào trước tham số khai báo `int`.

**Câu 3.** `invokeExact` có tự widening kiểu kết quả `int` sang `long` không?

**Trả lời:** Không. Lời gọi phải khớp hoàn toàn với `handle.type()`. Có thể dùng `invoke` khi phép thích nghi hợp lệ hoặc tạo handle mới qua `asType`.

**Câu 4.** Java 18 có giới thiệu `MethodHandle` lần đầu không?

**Trả lời:** Không. API có từ Java 7; JEP 416 trong Java 18 thay đổi cách cài đặt core reflection dựa trên method handles và variable handles.

**Câu 5.** Có thể dùng `Lookup` để đọc private field của bất kỳ named module nào không?

**Trả lời:** Không. Lookup mang quyền của caller; deep access xuyên module còn phụ thuộc `opens` và điều kiện của `privateLookupIn`. Không dùng method handles để vượt qua kiểm soát truy cập.

## 12. Tài liệu tham khảo

- OpenJDK JEP 416 — *Reimplement Core Reflection with Method Handles*: https://openjdk.org/jeps/416
- Java SE API — `MethodHandle`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE API — `MethodHandles.Lookup`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE API — `MethodType`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE API — `java.lang.reflect.Method`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html

Các liên kết Java SE 25 minh họa tài liệu API của một JDK hiện đại. Khi chạy và kiểm chứng ví dụ, hãy đối chiếu với **Javadoc của đúng phiên bản JDK đang sử dụng**, đặc biệt khi đánh giá hiệu năng, quyền truy cập module hoặc chi tiết ngoại lệ.
