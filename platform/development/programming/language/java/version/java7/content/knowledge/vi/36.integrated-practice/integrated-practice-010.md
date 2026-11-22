# Khám phá MethodHandle bằng các chữ ký có kiểu khác nhau

## 1. MethodHandle là gì và vì sao cần quan tâm đến chữ ký?

`java.lang.invoke.MethodHandle` là một tham chiếu có **kiểu** tới một thao tác có thể thực thi: phương thức static, phương thức instance, constructor, truy cập field hoặc một chuỗi biến đổi lời gọi. Một handle không chỉ chứa “tên phương thức”; nó mang theo **chữ ký thực thi** (*method type*) gồm:

- **Kiểu trả về**: `int`, `String`, `void`, `Object`...;
- **Số lượng và thứ tự tham số**;
- **Kiểu của từng tham số** (bao gồm primitive, reference và đối tượng receiver cho phương thức instance).

`MethodHandle.type()` trả về một đối tượng `MethodType` bất biến. Ví dụ:

| Chữ ký MethodHandle | Ý nghĩa |
| --- | --- |
| `(int,int)int` | Nhận hai `int`, trả về `int` |
| `(String,int)String` | Nhận `String` rồi `int`, trả về `String` |
| `(short,short)long` | Nhận hai `short`, trả về `long` |
| `(MethodHandleTypesDemo,String)String` | Nhận instance của class đó làm receiver, tiếp theo `String`, trả về `String` |
| `(Object,Object)Object` | Nhận hai tham chiếu `Object`, trả về `Object` |

**Ý chính của bài:** bạn có thể tham chiếu cùng một hành vi nhưng gọi nó qua những chữ ký khác nhau, miễn là sử dụng đúng phép chuyển đổi hoặc adapter. Ngược lại, một `MethodHandle` có chữ ký không phù hợp với lời gọi sẽ bị JVM từ chối bằng lỗi kiểu tại runtime.

API này đã xuất hiện từ Java 7 và **vẫn là API công khai đang được hỗ trợ** trong các JDK hiện đại. Hãy học và thử nghiệm với JDK 17 trở lên; không cần chạy lại bản JDK 7 cũ. Phần lớn ứng dụng thông thường không cần MethodHandle để gọi hàm trực tiếp; nó có giá trị khi xây dựng bộ điều phối động, runtime, framework và những cơ chế cần ghép các thao tác có kiểu.

## 2. Tạo MethodType: kiểu trả về đứng trước

`MethodType.methodType(returnType, parameterTypes...)` mô tả **kiểu trả về trước**, sau đó là kiểu các tham số:

```java
MethodType addType =
        MethodType.methodType(int.class, int.class, int.class);
System.out.println(addType); // (int,int)int

MethodType joinType =
        MethodType.methodType(String.class, String.class, int.class);
System.out.println(joinType); // (String,int)String

MethodType noArgs =
        MethodType.methodType(void.class);
System.out.println(noArgs); // ()void
```

Đây là **đoạn mã trong một phương thức đã import `java.lang.invoke.MethodType`**, chưa phải chương trình độc lập. `void.class` hợp lệ với **kiểu trả về**; `void` không phải kiểu tham số hợp lệ.

Chữ ký của `MethodType` dựa trên các đối tượng `Class<?>`, bao gồm cả `int.class` khác `Integer.class`, và `String.class` khác `Object.class`. `MethodType.equals(...)` so sánh toàn bộ kiểu trả về và tham số. Hai method có tên giống nhau nhưng overload khác kiểu sẽ cho hai `MethodType` khác nhau.

Các API quan sát hữu ích:

- `type.returnType()` — kiểu trả về;
- `type.parameterCount()` — số tham số;
- `type.parameterType(index)` — kiểu tham số ở vị trí bắt đầu từ 0;
- `type.parameterList()` hoặc `parameterArray()` — toàn bộ kiểu tham số;
- `type.changeReturnType(...)` hoặc `changeParameterType(...)` — tạo một `MethodType` mới, không sửa bản gốc.

**Đừng nhầm:** thay `MethodType` chỉ mô tả một chữ ký mới; nó **chưa** tự thay đổi hành vi của một `MethodHandle`. Muốn một handle chấp nhận chữ ký mới, phải dùng cơ chế chuyển đổi như `asType(...)` khi thích hợp.

## 3. Tìm handle bằng MethodHandles.Lookup

Một `MethodHandles.Lookup` làm nhiệm vụ tìm phương thức và kiểm tra quyền truy cập khi tạo handle:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle add = lookup.findStatic(
        MethodHandleTypesDemo.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));
```

Đoạn này đặt bên trong một phương thức của class `MethodHandleTypesDemo` có khai báo `public static int add(int a, int b)`, và cần import `MethodHandle`, `MethodHandles`, `MethodType`.

- `findStatic(owner, name, type)`: tham chiếu **phương thức static** đúng tên và chữ ký được yêu cầu. Ví dụ handle `add` có kiểu `(int,int)int`.
- `findVirtual(owner, name, type)`: tham chiếu phương thức **instance**. `MethodType` truyền vào mô tả **tham số phương thức, không gồm receiver**; nhưng handle được trả về sẽ có receiver **đứng đầu** danh sách tham số.
- `findConstructor(owner, MethodType.methodType(void.class, ...))`: tìm constructor; handle thực tế được trả về có **kiểu trả về là class được khởi tạo**, không phải `void`.
- `findGetter`/`findSetter`: tạo handle truy cập field với kiểu đọc/ghi tương ứng, khi quyền truy cập cho phép.

Ví dụ `String` có phương thức instance `String.toUpperCase()` không tham số: tìm qua `lookup.findVirtual(String.class, "toUpperCase", MethodType.methodType(String.class))` sẽ tạo handle có chữ ký `(String)String` vì receiver `String` là tham số thực thi đầu tiên.

Nếu không tìm thấy member đúng chữ ký, `Lookup` có thể ném `NoSuchMethodException` hoặc `NoSuchFieldException`; nếu không đủ quyền, nó có thể ném `IllegalAccessException`. `MethodHandles.lookup()` **không** vượt qua mọi giới hạn access/module; chỉ truy cập những gì quyền lookup cho phép. Không phát tán handle trỏ vào phương thức nhạy cảm tới code không tin cậy: quyền truy cập được kiểm tra tại lúc tạo handle, nên ai có handle phù hợp có thể gọi thao tác đó.

## 4. invokeExact và invoke: tại sao chữ ký của nơi gọi quan trọng?

Hai cách gọi chính của `MethodHandle` là:

- **`invokeExact(...)`**: chữ ký của *call site* phải **khớp 100%** với `handle.type()`, gồm số tham số, kiểu tham số và **kiểu trả về**. Không tự boxing/unboxing, widening hay cast giữa các kiểu.
- **`invoke(...)`**: nếu chữ ký tại call site khác, JVM có thể dùng các phép chuyển đổi tương đương `handle.asType(callSiteType)`. Chỉ các phép chuyển đổi hợp lệ mới được phép; không phải mọi kiểu đều tự chuyển được.

Với handle `add.type() == (int,int)int`:

```java
int sum = (int) add.invokeExact(2, 3);  // Hợp lệ, kết quả 5

Number number = (Number) add.invoke(2, 3);
// Hợp lệ: kết quả int được boxing thành Integer rồi nhìn như Number.
```

**Kiểu trả về không phải chi tiết phụ.** Biểu thức sau **bị từ chối tại runtime** dù hai tham số vẫn đúng:

```java
long x = (long) add.invokeExact(2, 3); // WrongMethodTypeException
```

Call site yêu cầu `(int,int)long` nhưng handle là `(int,int)int`. Tương tự:

```java
int y = (int) add.invokeExact(2L, 3L); // WrongMethodTypeException
```

Call site thứ hai yêu cầu `(long,long)int`. Đối với các lời gọi dạng *signature polymorphic* như `invokeExact`, compiler ghi nhận kiểu tĩnh của đối số và kiểu trả về suy ra từ context/cast. Một lời gọi `invokeExact(...)` không dùng kết quả dưới dạng **statement** có kiểu trả về `void` tại call site; nếu handle thực sự trả `int`, cách gọi đó cũng không khớp.

Lưu ý: `invoke` vẫn là lời gọi **có kiểu** (JVM vẫn biết chữ ký của call site), chỉ là nó chấp nhận điều chỉnh kiểu hợp lệ. Nếu cần gọi một handle khi số/kiểu đối số chỉ xác định ở runtime dưới dạng `Object[]` hoặc `List`, có thể dùng `invokeWithArguments(...)`, nhưng nó dễ tạo boxing/kiểm tra động và không nhất thiết thích hợp cho hot path.

## 5. Chuyển đổi có chủ đích bằng asType

`handle.asType(newType)` trả về **handle mới** có `type()` bằng chính `newType`. Handle gốc vẫn giữ nguyên kiểu và hành vi. Adapter sẽ chuyển đổi đối số sang kiểu mà target nhận, gọi target, rồi chuyển kiểu kết quả như đã khai báo.

Ví dụ với `add: (int,int)int`:

```java
MethodHandle widened = add.asType(
        MethodType.methodType(long.class, short.class, short.class));
System.out.println(widened.type()); // (short,short)long
long result = (long) widened.invokeExact((short) 3, (short) 4);
System.out.println(result); // 7
```

Lời gọi giờ **exact** vì adapter có kiểu `(short,short)long`: mỗi `short` được mở rộng thành `int` cho `add`, và `int` trả về được mở rộng thành `long`. Đây là minh họa chuẩn về **hai chữ ký khác nhau** cùng đại diện một phép cộng.

Một adapter khác cho phép kiểu `Object`:

```java
MethodHandle objects = add.asType(
        MethodType.methodType(Object.class, Object.class, Object.class));
Object result = (Object) objects.invokeExact(
        (Object) Integer.valueOf(2),
        (Object) Integer.valueOf(3)); // Integer(5) dưới dạng Object
```

Nó có thể cast/unbox đối số `Integer` và boxing kết quả `int`. Nhưng đưa `"two"` thay cho `Integer.valueOf(2)` có thể dẫn tới `ClassCastException` lúc gọi — `asType` không biến văn bản số thành số nguyên theo nghĩa `Integer.parseInt`.

Khi chuyển đổi **không thể được tạo** cho chữ ký yêu cầu, `asType` hoặc `invoke` có thể ném `WrongMethodTypeException`. Khi adapter đã tạo được nhưng một giá trị cụ thể không cast/unbox được, có thể nhận `ClassCastException` hoặc `NullPointerException` (ví dụ unbox `null`). Đừng gom tất cả vào một lỗi “sai phương thức”: phân biệt **không tương thích chữ ký** với **dữ liệu runtime sai kiểu**.

Cũng cần nhớ `asType` không tự thay đổi **số lượng tham số** cho handle arity cố định; để thêm, bớt, sắp xếp lại hoặc cố định đối số, dùng các adapter của `MethodHandles`.

## 6. Thay đổi chữ ký bằng adapter, không cần sửa phương thức gốc

### 6.1 Cố định một tham số với insertArguments

Phương thức `join(String prefix, int n)` có thể nhận handle `(String,int)String`. Khi luôn dùng prefix `"item-"`, hãy cố định tham số đầu:

```java
MethodHandle fixedPrefix = MethodHandles.insertArguments(
        join, 0, "item-");
System.out.println(fixedPrefix.type()); // (int)String

String text = (String) fixedPrefix.invokeExact(7);
System.out.println(text); // item-7
```

Adapter đã **giảm arity** từ 2 còn 1. Nguyên lý này có ích khi xây dựng dispatcher đã biết một phần cấu hình hoặc một số tham số.

### 6.2 Receiver được đưa vào chữ ký của phương thức instance

Cho phương thức:

```java
public String surround(String text) {
    return "[" + text + "]";
}
```

Nằm trong class `MethodHandleTypesDemo`. Tìm handle bằng:

```java
MethodHandle surround = lookup.findVirtual(
        MethodHandleTypesDemo.class, "surround",
        MethodType.methodType(String.class, String.class));
```

Dù `MethodType` đưa vào `findVirtual` chỉ là `(String)String`, `surround.type()` trả về `(MethodHandleTypesDemo,String)String` vì receiver là đối số đầu:

```java
String a = (String) surround.invokeExact(
        new MethodHandleTypesDemo(), "ok"); // [ok]

MethodHandle bound = surround.bindTo(new MethodHandleTypesDemo());
System.out.println(bound.type());          // (String)String
String b = (String) bound.invokeExact("hi"); // [hi]
```

`bindTo` cố định **receiver đầu tiên là kiểu tham chiếu**. Đừng nhầm với `findStatic` vốn không có receiver. Khi class có overload, xác định đúng `MethodType` của phương thức muốn tìm.

### 6.3 Các adapter khác nên nhận diện

- `MethodHandles.dropArguments(target, position, types...)`: tạo handle chấp nhận thêm những tham số mà target **không sử dụng**. Cẩn thận với chữ ký mới và vị trí thêm.
- `MethodHandles.permuteArguments(target, newType, reorder...)`: hoán vị/đổi thứ tự tham số theo bản đồ chỉ số; phải bảo đảm các kiểu tương thích.
- `MethodHandles.filterArguments(...)`, `filterReturnValue(...)`: biến đổi đối số hoặc kết quả qua handle khác.
- `MethodHandles.guardWithTest(...)`: chọn giữa hai nhánh dựa trên điều kiện; test/target/fallback phải có các chữ ký phù hợp.
- `asSpreader(...)` và `asCollector(...)`: chuyển giữa nhiều đối số riêng lẻ và đối số mảng theo kích thước xác định.

Các adapter tạo **MethodHandle mới**, không thay đổi target gốc; có thể ghép nhiều adapter để tạo chuỗi xử lý. Không nên dùng adapter phức tạp chỉ để thay thế một lời gọi Java trực tiếp ngắn gọn — mục đích của chúng là đáp ứng nhu cầu xử lý động và type composition.

## 7. Chương trình Java độc lập: bốn dạng chữ ký và hai loại lỗi

Chương trình dưới đây minh họa:

1. Handle static `(int,int)int` với `invokeExact` và `invoke`.
2. Adapter `(short,short)long` tạo từ cùng handle cộng.
3. `(String,int)String` rồi cố định prefix thành `(int)String`.
4. Handle instance `(MethodHandleTypesDemo,String)String` rồi bind receiver thành `(String)String`.
5. Adapter `(Object,Object)Object`, một lời gọi thành công và một lỗi cast giá trị.
6. Hai lỗi `WrongMethodTypeException` do kiểu trả về hoặc kiểu tham số tại call site `invokeExact` khác handle.

Tạo tệp **`MethodHandleTypesDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleTypesDemo {
    public static int add(int a, int b) {
        return a + b;
    }

    public static String join(String prefix, int n) {
        return prefix + n;
    }

    public String surround(String text) {
        return "[" + text + "]";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle add = lookup.findStatic(
                MethodHandleTypesDemo.class, "add",
                MethodType.methodType(
                        int.class, int.class, int.class));

        System.out.println("add.type=" + add.type());
        System.out.println("add.exact=" + (int) add.invokeExact(2, 3));

        Number boxed = (Number) add.invoke(2, 3);
        System.out.println("add.invoke=" + boxed);

        MethodHandle widened = add.asType(
                MethodType.methodType(
                        long.class, short.class, short.class));
        System.out.println("widened.type=" + widened.type());
        System.out.println("widened="
                + (long) widened.invokeExact((short) 3, (short) 4));

        MethodHandle join = lookup.findStatic(
                MethodHandleTypesDemo.class, "join",
                MethodType.methodType(
                        String.class, String.class, int.class));
        MethodHandle fixedPrefix = MethodHandles.insertArguments(
                join, 0, "item-");

        System.out.println("join.type=" + join.type());
        System.out.println("prefix.type=" + fixedPrefix.type());
        System.out.println("prefix.value="
                + (String) fixedPrefix.invokeExact(7));

        MethodHandle surround = lookup.findVirtual(
                MethodHandleTypesDemo.class, "surround",
                MethodType.methodType(String.class, String.class));
        System.out.println("virtual.type=" + surround.type());
        System.out.println("virtual.value="
                + (String) surround.invokeExact(
                        new MethodHandleTypesDemo(), "ok"));

        MethodHandle bound = surround.bindTo(
                new MethodHandleTypesDemo());
        System.out.println("bound.type=" + bound.type());
        System.out.println("bound.value="
                + (String) bound.invokeExact("hi"));

        try {
            long wrongReturn = (long) add.invokeExact(2, 3);
            System.out.println("UNEXPECTED=" + wrongReturn);
        } catch (WrongMethodTypeException expected) {
            System.out.println(
                    "wrong.return=WrongMethodTypeException");
        }

        try {
            int wrongArgs = (int) add.invokeExact(2L, 3L);
            System.out.println("UNEXPECTED=" + wrongArgs);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong.args=WrongMethodTypeException");
        }

        MethodHandle objects = add.asType(
                MethodType.methodType(
                        Object.class, Object.class, Object.class));
        System.out.println("objects.type=" + objects.type());
        System.out.println("objects.value="
                + objects.invokeExact(
                        (Object) Integer.valueOf(2),
                        (Object) Integer.valueOf(3)));

        try {
            Object wrongValue = (Object) objects.invokeExact(
                    (Object) "two", (Object) Integer.valueOf(3));
            System.out.println("UNEXPECTED=" + wrongValue);
        } catch (ClassCastException expected) {
            System.out.println("wrong.value=ClassCastException");
        }
    }
}
```

**Biên dịch và chạy** bằng JDK 17+:

```bash
javac -encoding UTF-8 MethodHandleTypesDemo.java
java MethodHandleTypesDemo
```

**Đầu ra đã kiểm tra với JDK hiện đại**:

```text
add.type=(int,int)int
add.exact=5
add.invoke=5
widened.type=(short,short)long
widened=7
join.type=(String,int)String
prefix.type=(int)String
prefix.value=item-7
virtual.type=(MethodHandleTypesDemo,String)String
virtual.value=[ok]
bound.type=(String)String
bound.value=[hi]
wrong.return=WrongMethodTypeException
wrong.args=WrongMethodTypeException
objects.type=(Object,Object)Object
objects.value=5
wrong.value=ClassCastException
```

**Giải thích các dòng trọng tâm:**

- `add.exact=5`: hai đối số kiểu `int` và kiểu kết quả `int` được yêu cầu tại call site trùng `add.type()`.
- `add.invoke=5`: call site yêu cầu `Number`, JVM chuyển kết quả `int` thành đối tượng phù hợp.
- `widened.type=(short,short)long`: type adapter cho phép chuyển đối số `short` → `int` và kết quả `int` → `long`.
- `prefix.type=(int)String`: `insertArguments` đã bỏ tham số `String prefix` khỏi chữ ký gọi.
- `virtual.type=(MethodHandleTypesDemo,String)String`: receiver nằm trong chữ ký handle mặc dù không khai báo trong `MethodType` đầu vào của `findVirtual`.
- `bound.type=(String)String`: receiver đã cố định, caller chỉ cần truyền `text`.
- `wrong.return` và `wrong.args`: gọi `invokeExact` với return hoặc argument khác kiểu gây `WrongMethodTypeException`; không cần thay đổi code của hàm `add`.
- `objects.value=5`: truyền các tham chiếu `Object` đang chứa `Integer` hợp lệ; `wrong.value`: một `Object` thực tế là `String` nên thất bại khi adapter cần unbox sang `int`.

**Vì sao ví dụ dùng `throws Throwable`?** Theo API, `invokeExact` và `invoke` có thể truyền qua bất kỳ `Throwable` nào từ thao tác được tham chiếu. Với ứng dụng sản xuất, cần chiến lược xử lý ngoại lệ phù hợp tầng ứng dụng; `throws Throwable` ở `main` ở đây chỉ giúp mã minh họa rõ ràng, không phải quy ước bắt buộc cho code nghiệp vụ.

## 8. Tại sao “cùng chức năng” chưa chắc “cùng chữ ký”?

Một số điểm khiến người mới dễ nhầm:

| Tình huống | Chữ ký của handle | Chữ ký tại call site | Kết quả |
| --- | --- | --- | --- |
| Cộng hai `int`, trả `int` qua `invokeExact` | `(int,int)int` | `(int,int)int` | Thành công |
| Cộng hai `int` nhưng cast kết quả sang `long` qua `invokeExact` | `(int,int)int` | `(int,int)long` | `WrongMethodTypeException` |
| Truyền hai `long` cho `invokeExact` | `(int,int)int` | `(long,long)int` | `WrongMethodTypeException` |
| Dùng `invoke` và nhận kết quả kiểu `Number` | `(int,int)int` | `(int,int)Number` | Thành công với chuyển đổi hỗ trợ |
| Dùng `asType` để nhận hai `short`, trả `long` | `(short,short)long` | `(short,short)long` | Thành công qua adapter |
| Truyền `Object("two")` vào adapter cần `int` | `(Object,Object)Object` | `(Object,Object)Object` | Call site khớp nhưng giá trị sai kiểu → `ClassCastException` |
| Tìm phương thức instance bằng `findVirtual` | `(Receiver,Args...)Return` | Cần receiver đúng kiểu ở đầu | Thiếu receiver → lỗi kiểu/arity |
| Chuyển receiver thành bound | `(Args...)Return` | Không cần truyền receiver nữa | Thành công nếu `bindTo` hợp lệ |

Đừng suy luận kiểu từ cách nhìn bằng mắt một expression. Trường hợp `invokeExact` đặc biệt nhạy với cast trả về và **kiểu tĩnh** của tham số ở call site. Ví dụ một biến `Object x = Integer.valueOf(2)` khác với một biến `int x = 2` về chữ ký tại call site, dù cả hai có thể biểu diễn giá trị số 2.

## 9. Áp dụng đúng chỗ và tránh tối ưu hóa theo suy đoán

Một bộ đăng ký xử lý tác vụ động có thể giữ các `MethodHandle` đến những callback đã được xác thực. Khi có nhiều callback với chữ ký khác nhau, có thể dùng `asType` để đưa chúng về một **chữ ký chuẩn** có chủ đích, chẳng hạn `(Object)Object`; sau đó dispatcher không cần biết mỗi method ban đầu trả `String` hay một lớp khác, miễn phép chuyển đổi đã được kiểm tra và dữ liệu ở runtime phù hợp.

Các bước an toàn:

1. Định nghĩa **chữ ký chuẩn** của dispatcher và ý nghĩa từng đối số.
2. Dùng `MethodHandles.Lookup` với quyền tối thiểu cần thiết để tìm method. Không tạo lookup quá rộng rồi truyền handle nhạy cảm cho plugin không tin cậy.
3. Quan sát `handle.type()`, xác minh số/kiểu đối số và kiểu kết quả; tạo adapter một lần ở bước đăng ký nếu cần.
4. Ghi rõ lỗi chuẩn hóa chữ ký (`WrongMethodTypeException`), lỗi giá trị runtime (`ClassCastException`/`NullPointerException`), và lỗi nghiệp vụ do phương thức gốc ném.
5. Chạy thử với các giá trị hợp lệ và không hợp lệ; đo hiệu năng dưới tải thực tế trước khi tối ưu.

Không coi MethodHandle luôn nhanh hơn `java.lang.reflect.Method` hay lời gọi trực tiếp. JVM có thể tối ưu tốt lời gọi có handle/loại ổn định, nhưng hiệu năng phụ thuộc hình dạng call site, khả năng JIT inline, tần suất thay đổi target và các adapter đi kèm. `invokeWithArguments` đặc biệt tiện cho kịch bản động nhưng tạo thêm chi phí chuyển đổi/đóng gói so với lời gọi exact được chuẩn hóa. Hãy benchmark trên JDK và workload thật nếu hiệu năng là lý do sử dụng.

## 10. Lỗi thường gặp và cách khắc phục

1. **Nhầm thứ tự trong `MethodType.methodType`:** đối số đầu là kiểu **trả về**, không phải tham số thứ nhất. Kiểm tra `handle.type()` ngay sau lookup.
2. **Quên receiver của phương thức instance:** `findVirtual` nhận `MethodType` của method nhưng tạo handle có receiver ở đầu; dùng `bindTo` hoặc truyền receiver đúng kiểu.
3. **Quên cast kiểu trả về ở `invokeExact`:** với handle trả `int`, gọi dưới dạng statement hoặc cast `long`/`Object` sẽ yêu cầu kiểu trả về khác, dẫn tới `WrongMethodTypeException`.
4. **Tin rằng `invokeExact` tự boxing/widening:** nó không thực hiện chuyển đổi kiểu; gọi `asType`/`invoke` khi cần phép chuyển hợp lệ.
5. **Cho rằng `invoke` chuyển được mọi kiểu:** nó không tự parse `String` thành `int`; cần mã chuyển đổi cụ thể nếu nghiệp vụ muốn vậy.
6. **Nhầm `WrongMethodTypeException` với `ClassCastException`:** lỗi chữ ký xảy ra khi không khớp/chuyển được method type; lỗi cast giá trị xảy ra khi giá trị runtime không đúng kiểu yêu cầu.
7. **Cho rằng `asType` thay thế việc thêm/bớt đối số:** dùng `insertArguments`, `dropArguments` hoặc adapter phù hợp để thay arity.
8. **Dựa vào Reflection để gọi `MethodHandle.invokeExact` như method varargs thông thường:** nó có cách xử lý *signature polymorphic* đặc biệt tại bytecode, không phải wrapper reflection chung.
9. **Bỏ qua quyền truy cập của Lookup:** `lookup()` không tự phá giới hạn Java access/module. Với thành viên không truy cập được, phải xử lý `IllegalAccessException` theo thiết kế module và quyền hợp lệ.
10. **Nhầm primitive với wrapper:** `int.class` và `Integer.class` khác nhau trong `MethodType`; chuyển đổi cần phép adaptation tương ứng.
11. **Gọi handle bằng `null` ở vị trí primitive:** adapter unbox có thể ném `NullPointerException`; kiểm tra input nếu null không hợp lệ.
12. **Tạo lookup/adapters liên tục trong đường chạy nóng:** có thể lưu cache handle đã chuẩn hóa theo đúng cấu hình quyền/kiểu, sau đó benchmark; tránh cache sai class loader hoặc dùng chung handle nhạy cảm ngoài phạm vi được phép.
13. **Không định nghĩa rõ xử lý ngoại lệ từ method gốc:** nó có thể ném bất kỳ lỗi nào; ngoại lệ đó được chuyển tiếp qua handle, không phải lúc nào cũng được bọc thành `InvocationTargetException` như khi dùng Reflection.

## 11. Bài tập củng cố có lời giải

**Bài 1.** Handle có kiểu `(int,int)int`. Vì sao `(long) mh.invokeExact(2,3)` không tương đương với `(long) ((int) mh.invokeExact(2,3))`?

**Đáp án:** Ở biểu thức đầu, cast ngoài cùng làm **kiểu trả về của call site** trở thành `long` và không trùng handle. Ở biểu thức thứ hai, cast `int` nằm trực tiếp trên invocation, nên call site là `(int,int)int`; sau khi đã nhận `int`, Java mới widening sang `long`.

**Bài 2.** Có phương thức instance `String surround(String)` và handle `(MyClass,String)String`. Làm gì để gọi bằng đúng một đối số `String`?

**Đáp án:** Cố định receiver bằng `bindTo(instance)` để tạo handle `(String)String`. Nếu không bind, phải truyền instance làm đối số đầu.

**Bài 3.** `asType` từ `(int,int)int` sang `(short,short)long` có làm thay đổi định nghĩa `add(int,int)` không?

**Đáp án:** Không. Adapter mới nhận `short`, chuyển thành `int` cho target, rồi chuyển kết quả `int` thành `long`; handle và phương thức gốc không đổi.

**Bài 4.** Chữ ký của `lookup.findVirtual(String.class, "length", MethodType.methodType(int.class))` là gì?

**Đáp án:** `(String)int`, do receiver `String` được thêm vào đầu danh sách tham số của handle; `String.length()` vốn không nhận đối số thường.

**Bài 5.** Một adapter có kiểu `(Object,Object)Object`, nhưng caller đưa `"not-a-number"` và `Integer.valueOf(3)` cho target cộng `int`. Call site có đúng chữ ký không? Có chắc chạy được không?

**Đáp án:** Call site có thể khớp `(Object,Object)Object`, nhưng khi adapter cố unbox đối số thứ nhất thành `int`, giá trị thực tế là `String` nên thất bại (`ClassCastException`). Khớp `MethodType` không đồng nghĩa mọi giá trị đều hợp lệ.

**Bài 6.** Khi nào không nên đưa MethodHandle vào code chỉ để gọi một phương thức?

**Đáp án:** Khi target được biết từ lúc biên dịch và lời gọi Java trực tiếp đủ rõ ràng. MethodHandle mang thêm cơ chế lookup/type-adaptation để phục vụ ghép thao tác động; lợi ích hay hiệu năng cần căn cứ vào nhu cầu thực tế và đo lường.

### Tài liệu Java hiện hành

- [Oracle Java SE 25 — `MethodHandle`, `invokeExact`, `invoke` và `asType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Oracle Java SE 25 — `MethodType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Oracle Java SE 25 — `MethodHandles` và các adapter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Oracle Java SE 25 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Oracle Java SE 25 — `WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html)
