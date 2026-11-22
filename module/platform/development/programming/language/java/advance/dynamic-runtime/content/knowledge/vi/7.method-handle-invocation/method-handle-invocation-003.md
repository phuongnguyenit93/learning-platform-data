# 7.3 `invoke`: thích nghi kiểu theo quy tắc `asType`

Trong API `java.lang.invoke` của Java, mỗi `MethodHandle` mang một kiểu phương thức **chính xác** (`MethodType`), gồm danh sách kiểu tham số và **kiểu trả về**. Tuy vậy, lời gọi `handle.invoke(...)` có thể chấp nhận kiểu tại vị trí gọi khác với kiểu của handle khi có thể **thích nghi theo các quy tắc của `MethodHandle.asType(...)`**. Đây chính là khác biệt quan trọng giữa `invoke` và `invokeExact`.

Bài học giải thích hai kiểu cần phân biệt, cách JVM xây dựng *call-site descriptor*, các phép chuyển đổi được phép và không được phép, tình huống boxing/unboxing, kiểu tham chiếu, kiểu trả về, các lỗi thường gặp, cùng cách chuyển từ lời gọi `invoke` sang một adapter `asType` dùng lại. Mã minh họa tương thích Java 17 trở lên.

## 1. Mô hình đúng: kiểu của handle và kiểu của lời gọi

Giả sử một phương thức Java:

~~~java
static long add(long a, long b) {
    return a + b;
}
~~~

Một handle tạo bằng `MethodHandles.Lookup.findStatic` cho method trên có kiểu:

~~~text
(long,long)long
~~~

Thông tin ấy được trả về bởi `handle.type()`. Nó được mô tả bằng `MethodType.methodType(long.class, long.class, long.class)`: đối số đầu của `methodType` là **return type**, các đối số tiếp theo là **parameter types**.

Khi viết lời gọi:

~~~java
long result = (long) handle.invoke(3, 4);
~~~

hai biểu thức `3` và `4` có kiểu tĩnh `int`. Kiểu trả về được yêu cầu bởi phép cast `(long)` là `long`. Do đó **kiểu tại vị trí gọi** (*call-site descriptor*, hay symbolic method type) là:

~~~text
(int,int)long
~~~

Nó khác với kiểu handle `(long,long)long`. `invoke` có thể thực hiện vì `int` có thể **widen** thành `long` đối với từng tham số.

Ngược lại:

~~~java
long result = (long) handle.invokeExact(3, 4);
~~~

không gọi thành công: `invokeExact` yêu cầu call-site type **khớp chính xác** `(long,long)long`. `(int,int)long` không khớp, nên ném `WrongMethodTypeException`. Muốn dùng `invokeExact` cần viết `3L`, `4L`:

~~~java
long result = (long) handle.invokeExact(3L, 4L);
~~~

**Ba thuật ngữ phải nhớ:**

| Thuật ngữ | Ví dụ | Vai trò |
| --- | --- | --- |
| **Target method type** | `(long,long)long` | Kiểu thật của `MethodHandle`, đọc qua `type()` |
| **Call-site type** | `(int,int)long` | Kiểu của các đối số và kiểu trả về tại chính biểu thức `invoke`/`invokeExact` do compiler phát ra |
| **Adapted method type** | `(int,int)long` | Kiểu mà `asType` có thể tạo để làm cầu nối từ call site tới target |

Điểm dễ sai là cho rằng `invoke` sẽ nhìn **giá trị runtime** của mọi argument rồi tự chọn một overload tốt nhất. Thực tế, compiler ghi **kiểu tĩnh tại vị trí gọi**; runtime kiểm tra và áp dụng conversion theo `asType` đối với **handle đã chọn**. Nó không tự gọi lại `findStatic`, `findVirtual` hay chọn một phương thức overload khác.

## 2. `invokeExact` và `invoke` khác nhau ở đâu?

Cả `invokeExact(Object... args)` và `invoke(Object... args)` là các phương thức **signature-polymorphic** của `MethodHandle`. Đừng hiểu chữ ký hiển thị `Object...` trong JavaDoc thành lời gọi Java thông thường nhận một mảng `Object[]`. Với lời gọi Java source bình thường, compiler phát ra symbolic descriptor dựa trên **kiểu của từng biểu thức** được truyền vào và ngữ cảnh kiểu trả về.

| Đặc điểm | `invokeExact` | `invoke` |
| --- | --- | --- |
| Có kiểm tra method type? | Có, **phải bằng chính xác** `handle.type()` | Có, **phải bằng chính xác hoặc thích nghi được** bằng `asType` |
| Có tự widen `int` sang `long`? | Không | Có, nếu conversion hợp lệ |
| Có boxing/unboxing theo adapter? | Không | Có, trong những trường hợp `asType` cho phép |
| Có cast kiểu tham chiếu runtime? | Không thích nghi call-site type; method body vẫn có các cast riêng | Có thể chèn `checkcast` theo adapter, lỗi nếu giá trị thực tế sai kiểu |
| Kiểu trả về tại call site có quan trọng không? | Rất quan trọng, phải trùng | Có, và có thể được thích nghi |
| Mục tiêu sử dụng | Lời gọi có kiểu hoàn toàn đã biết, không cần adapter | Lời gọi cần một tập conversion có kiểm soát |
| Nếu kiểu không hợp lệ | `WrongMethodTypeException` | `WrongMethodTypeException` nếu không thể tạo conversion; có thể gặp `ClassCastException`/`NullPointerException` trong lúc chuyển đổi runtime |

Khi call-site type đã **trùng** target type, `invoke` và `invokeExact` đều đi thẳng tới hành vi target. Khi khác kiểu, `invoke` vận hành **như thể** đã gọi `handle.asType(callSiteType)` rồi gọi adapter bằng `invokeExact`. JVM được quyền tối ưu việc này, nên **không nhất thiết tạo một đối tượng adapter vật lý cho mỗi lời gọi**.

### Sơ đồ một lần gọi `invoke`

~~~text
Java source: (long) handle.invoke(3, 4)
          |
          v
Compiler ghi call-site type: (int,int)long
          |
          v
Kiểu thật handle.type():      (long,long)long
          |
          v
Hai kiểu trùng nhau? -- Có --> gọi target
          |
        Không
          |
          v
Có thể asType((int,int)long)?
          |
      +---+-----------------------+
      |                           |
     Có                         Không
      |                           |
      v                           v
Widen int -> long          WrongMethodTypeException
Widen int -> long
      |
      v
Gọi target add(long,long)
      |
      v
Trả long theo call-site type
~~~

Sơ đồ chỉ diễn giải ngữ nghĩa. Implementation có thể biên dịch/inline và bỏ các bước trung gian nhưng phải giữ hành vi có thể quan sát theo hợp đồng API.

## 3. Ví dụ hoàn chỉnh: `invoke` thích nghi, `asType` tạo adapter tường minh

Lưu mã sau vào **`InvokeAdaptDemo.java`**:

~~~java
import java.lang.invoke.*;

public class InvokeAdaptDemo {
    static long add(long a, long b) {
        return a + b;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle sum = MethodHandles.lookup().findStatic(
            InvokeAdaptDemo.class, "add",
            MethodType.methodType(long.class, long.class, long.class)
        );

        System.out.println("targetType=" + sum.type());
        System.out.println("exact=" + (long) sum.invokeExact(3L, 4L));
        System.out.println("invoke=" + (long) sum.invoke(3, 4));

        Object boxed = sum.invoke(
            Integer.valueOf(5), Long.valueOf(6)
        );
        System.out.println(
            "boxed=" + boxed.getClass().getSimpleName() + ":" + boxed
        );

        MethodHandle generic = sum.asType(
            MethodType.methodType(
                Object.class, Object.class, Object.class
            )
        );

        Object result = generic.invokeExact(
            (Object) Integer.valueOf(7),
            (Object) Long.valueOf(8)
        );

        System.out.println("adapterType=" + generic.type());
        System.out.println("adapter=" + result);
        System.out.println("originalType=" + sum.type());
    }
}
~~~

Biên dịch bằng Java 17 (hoặc compiler mới với target 17) và chạy:

~~~sh
javac --release 17 InvokeAdaptDemo.java
java InvokeAdaptDemo
~~~

**Stdout:**

~~~text
targetType=(long,long)long
exact=7
invoke=7
boxed=Long:11
adapterType=(Object,Object)Object
adapter=15
originalType=(long,long)long
~~~

Giải thích:

1. `sum.type()` có kiểu `(long,long)long` và không thay đổi trong suốt chương trình.
2. `sum.invokeExact(3L, 4L)` thành công vì cả hai tham số và kiểu trả về đúng `long`.
3. `sum.invoke(3, 4)` có call site `(int,int)long`; `invoke` chấp nhận widening hai tham số `int → long`.
4. `Object boxed = sum.invoke(Integer.valueOf(5), Long.valueOf(6))` dùng call-site type `(Integer,Long)Object`. Adapter unbox `Integer` thành `int` rồi widen thành `long`, unbox `Long` thành `long`, và **box giá trị trả về `long` thành `Long`** để phù hợp kiểu `Object`.
5. `sum.asType((Object,Object)Object)` tạo **handle mới** chấp nhận hai tham số kiểu `Object` và trả `Object`. Khi truyền một `Integer` và một `Long`, adapter thực hiện unboxing + widening, rồi boxing giá trị trả về. Đây là chuyển đổi có điều kiện, không phải chấp nhận mọi `Object`.
6. `generic.invokeExact(...)` chạy được vì cả hai argument được **cast tĩnh thành `Object`** và kết quả được gán cho biến kiểu `Object`. Call-site type chính xác là `(Object,Object)Object`.
7. `sum.type()` cuối cùng vẫn là `(long,long)long`: `MethodHandle` bất biến. `asType` không sửa handle cũ. Nếu gọi `asType` bằng đúng kiểu hiện tại, API được phép và theo đặc tả sẽ trả lại chính handle đó.

Trong đoạn trên, phép cast `(Object)` trước `Integer` và `Long` **rất quan trọng với `invokeExact`**. Nếu bỏ cast, Java compiler ghi descriptor có các tham số `Integer`/`Long`, không còn trùng `generic.type()` và lời gọi exact sẽ thất bại.

## 4. Quy tắc `asType`: chuyển đổi từ **kiểu mới** sang **kiểu cũ**

Với `original.asType(newType)`, adapter nhận argument theo `newType`, chuyển chúng sang **parameter types của `original.type()`**, gọi original, rồi chuyển **kết quả của original** sang return type của `newType`.

Đối với fixed-arity handle thông thường, các kiểu tham số được đối chiếu **theo từng vị trí** và số lượng tham số phải tương ứng. Nếu handle là *variable-arity collector*, có các quy tắc thu gom đối số thành mảng bổ sung; xem phần sau.

Ví dụ:

~~~text
Original: (long,long)long
New:      (Object,Object)Object

Object #1 --cast/unbox/widen--> long \
                                      -> original.add(long,long) -> long
Object #2 --cast/unbox/widen--> long /                           |
                                                                    v
                                                               box Long -> Object
~~~

### Bảng chuyển đổi hợp lệ và giới hạn

| Hướng chuyển đổi | Quy tắc `asType` | Ví dụ |
| --- | --- | --- |
| Primitive → cùng primitive | Giữ nguyên | `long → long` |
| Primitive → primitive khác | Chỉ **widening primitive** theo Java method invocation conversion | `byte → int`, `int → long`, `float → double` |
| Primitive → primitive hẹp hơn | **Không** qua `asType` | `long → int`, `int → short` sẽ không được thích nghi |
| Primitive → reference | Boxing thành wrapper, rồi widening reference nếu cần | `int → Integer`, `int → Number`, `long → Object` |
| Reference → reference | Runtime cast sang reference type đích nếu cần | `Object → String` có thể tạo adapter, nhưng object thực tế phải là `String` hoặc `null` |
| Wrapper → primitive | Unboxing, có thể tiếp tục widening | `Integer → long`; `Long → double` |
| `Object`/supertype phù hợp → primitive | Runtime unboxing wrapper thực tế rồi widening phù hợp; static type phải có khả năng chứa wrapper hợp lệ | `Object` chứa `Integer(5)` → `long` |
| `null` → primitive | Không có giá trị để unbox | Ném `NullPointerException` khi thực thi |
| Reference sai kiểu thực tế | Reference cast hoặc unboxing thất bại | Ném `ClassCastException` khi thực thi |
| Trả về giá trị → `void` | Bỏ kết quả | `(int)int → (int)void`: tính toán vẫn chạy nhưng kết quả bị bỏ |
| Trả về `void` → reference | Tạo `null` | `(String)void → (String)Object` |
| Trả về `void` → primitive | Tạo giá trị mặc định của primitive | `void → int` cho `0`; `void → boolean` cho `false` |

**Cần đọc bảng theo hướng đúng.** Khi gọi `asType(newType)`, phần **tham số** chuyển từ **newType → old type**, nhưng phần **kết quả** chuyển từ **old type → newType**. Đổi ngược hướng sẽ dẫn tới kết luận sai về narrowing/widening.

### Những chuyển đổi `asType` không thực hiện

- Không chuyển chuỗi số thành số: `"123" → int` không phải conversion `asType`. Muốn parse, viết `Integer.parseInt` hoặc một filter/adapter riêng.
- Không âm thầm narrow `long` thành `int` hoặc `double` thành `float`. Muốn conversion kiểu cast tường minh, nghiên cứu `MethodHandles.explicitCastArguments(...)` hoặc thực hiện conversion chủ động trước khi invoke.
- Không coi `boolean` và `int` là hoán đổi được theo `asType`; không có widening primitive `boolean → int`.
- Không tự reorder tham số, bỏ thêm tham số hay chọn method overload. Những biến đổi đó cần combinator như `permuteArguments`, `dropArguments` hoặc một handle khác.
- Không bảo đảm mọi reference có thể unbox thành primitive. Chẳng hạn `String` không phải wrapper số và cũng không phải supertype của wrapper số.
- Không mặc định mọi Object chứa numeric wrapper đều chuyển được sang mọi primitive: một `Long` không thể *narrow* sang `int` bằng `asType`.

### Vì sao reference cast có thể được tạo dù hai kiểu không liên quan?

Theo JavaDoc `asType`, khi hai đầu đều là reference types, adapter có thể tạo runtime cast tới kiểu đích. Việc tạo adapter **không nhất thiết thất bại ngay** nếu kiểu static không liên quan: giá trị runtime có thể là `null`. Khi thật sự đi qua adapter, value không phải instance phù hợp sẽ làm cast ném `ClassCastException`.

Ví dụ `String` và `Integer` không phải quan hệ subtype. Adapter reference-cast có thể tồn tại trong một số cấu hình; điều đó không có nghĩa một `Integer` bất kỳ sẽ trở thành `String`. **Cast không phải phép đổi định dạng.**

## 5. Hai loại thất bại khác nhau: kiểu không thể thích nghi và dữ liệu sai khi chuyển đổi

Phân biệt hai giai đoạn:

- **Không có phép chuyển kiểu hợp lệ ở mức signature:** `asType` hoặc `invoke` không thể tạo cầu nối hợp lệ giữa các static method types. Kết quả thường là `WrongMethodTypeException`.
- **Cầu nối hợp lệ nhưng giá trị runtime không đạt điều kiện:** adapter đã được tạo, nhưng reference không cast/unbox được hoặc là `null` khi cần primitive. Có thể nhận `ClassCastException` hoặc `NullPointerException`.

Đây là hai lỗi có nguyên nhân và cách sửa khác nhau.

### Ví dụ 2: `WrongMethodTypeException` so với `ClassCastException`/`NullPointerException`

Lưu **`InvokeErrorsDemo.java`**:

~~~java
import java.lang.invoke.*;

public class InvokeErrorsDemo {
    static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findStatic(
            InvokeErrorsDemo.class, "add",
            MethodType.methodType(int.class, int.class, int.class)
        );

        System.out.println("exact=" + (int) handle.invokeExact(1, 2));
        System.out.println("invokeAsLong=" + (long) handle.invoke(1, 2));

        try {
            long unused = (long) handle.invokeExact(1, 2);
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "invokeExactReturn=" + ex.getClass().getSimpleName()
            );
        }

        try {
            int unused = (int) handle.invoke(1L, 2L);
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "invokeLongArgs=" + ex.getClass().getSimpleName()
            );
        }

        try {
            short unused = (short) handle.invoke(1, 2);
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "invokeNarrowReturn=" + ex.getClass().getSimpleName()
            );
        }

        try {
            handle.asType(
                MethodType.methodType(
                    short.class, int.class, int.class
                )
            );
        } catch (WrongMethodTypeException ex) {
            System.out.println(
                "asTypeNarrowReturn=" + ex.getClass().getSimpleName()
            );
        }

        Object bad = "two";
        try {
            int unused = (int) handle.invoke(bad, 2);
        } catch (ClassCastException ex) {
            System.out.println(
                "badObject=" + ex.getClass().getSimpleName()
            );
        }

        Object absent = null;
        try {
            int unused = (int) handle.invoke(absent, 2);
        } catch (NullPointerException ex) {
            System.out.println(
                "nullObject=" + ex.getClass().getSimpleName()
            );
        }
    }
}
~~~

~~~sh
javac --release 17 InvokeErrorsDemo.java
java InvokeErrorsDemo
~~~

**Stdout:**

~~~text
exact=3
invokeAsLong=3
invokeExactReturn=WrongMethodTypeException
invokeLongArgs=WrongMethodTypeException
invokeNarrowReturn=WrongMethodTypeException
asTypeNarrowReturn=WrongMethodTypeException
badObject=ClassCastException
nullObject=NullPointerException
~~~

Các trường hợp cần hiểu riêng:

1. `invokeExact(1,2)` ép kiểu trả về `int` thành công vì signature đúng `(int,int)int`.
2. `(long) handle.invoke(1,2)` hợp lệ: return type cũ `int` có thể widen sang kiểu trả về call site `long`.
3. `(long) handle.invokeExact(1,2)` ném `WrongMethodTypeException`: dù kiểu Java thông thường có thể gán `int` sang `long`, `invokeExact` **không** cho phép khác return type.
4. `handle.invoke(1L,2L)` yêu cầu parameter conversion `long → int`, là primitive narrowing bị cấm. Lỗi là `WrongMethodTypeException`.
5. Lời gọi `(short) handle.invoke(1,2)` và `asType((int,int)short)` đều cần result conversion `int → short`, bị cấm, nên ném `WrongMethodTypeException`.
6. `Object bad = "two"`: call site dùng parameter type `Object`. Adapter `Object → int` **có thể được tạo** vì một Object *có thể* chứa Integer; nhưng giá trị thực tế là String, nên ném `ClassCastException` khi unboxing.
7. `Object absent = null`: adapter hợp lệ, nhưng unbox `null` vào `int` sẽ ném `NullPointerException`.

Cả `WrongMethodTypeException` lẫn lỗi cast/unbox có thể xuất hiện **trước khi target body chạy**. Tuy nhiên, khi target body ném lỗi cùng loại, cần xem stack trace để phân biệt nguồn. `MethodHandle.invoke` không tự bọc exception từ target bằng `InvocationTargetException` như `java.lang.reflect.Method.invoke`; chữ ký `throws Throwable` cho phép exception từ target truyền ra.

## 6. Java compiler quyết định kiểu tại call site bằng cách nào?

Một lỗi khó nhận ra là `MethodHandle.invoke` được gọi theo **signature polymorphism**: kiểu đối số và kiểu trả về tại call site liên quan trực tiếp đến symbolic descriptor JVM ghi trong bytecode. Compiler **không thực hiện các Java method invocation conversions thông thường lên argument** rồi mới tạo descriptor; thay vào đó, `invoke` chịu trách nhiệm thích nghi khi phù hợp.

Xét handle `(int)int` và các lời gọi:

| Biểu thức Java source | Call-site descriptor | Ý nghĩa |
| --- | --- | --- |
| `int x = (int) h.invokeExact(2);` | `(int)int` | Exact match |
| `long x = (long) h.invokeExact(2);` | `(int)long` | Exact mismatch |
| `long x = (long) h.invoke(2);` | `(int)long` | Widen return `int → long` |
| `int x = (int) h.invoke((short) 2);` | `(short)int` | Widen argument `short → int` |
| `Object x = h.invoke(2);` | `(int)Object` | Box return `int → Integer` rồi nhận dưới `Object` |
| `h.invoke(2);` là **statement** | `(int)void` | `invoke` bỏ result nếu target trả giá trị |
| `h.invokeExact(2);` là **statement** | `(int)void` | Mismatch nếu handle trả `int` |

**Phần trả về là một phần không thể thiếu của descriptor.** Cùng truyền một đối số `2` nhưng gán cho `int`, `long`, `Object` hay bỏ qua kết quả có thể thay đổi descriptor. Đừng xem `(long)` sau `invokeExact` giống phép cast kết quả đã được gọi xong: ở đây nó góp phần **quyết định call-site return type trước khi invocation thực sự diễn ra**.

Ví dụ:

~~~java
Object number = Integer.valueOf(5);
int result = (int) h.invoke(number);
~~~

Call site có tham số **`Object`**, không phải `Integer`, dù runtime value là `Integer`. Nếu target nhận `int`, adapter có thể unbox runtime Integer. Nhưng với `invokeExact`, `Object` khác `int` nên vẫn là mismatch.

### Chú ý khi truyền literal `null`

Uncast `null` trong lời gọi signature-polymorphic có symbolic type `java.lang.Void` theo JavaDoc, không phải tự động là `Object` hay type mà target mong đợi. Khi muốn kiểm soát call-site descriptor, cast tường minh, chẳng hạn `(String) null` hoặc `(Object) null`; với `invoke` vẫn phải tuân theo quy tắc reference cast và target body có thể từ chối `null` vì lý do riêng.

Đừng ghép tên `invokeExact` vào Reflection để gọi như method thông thường. `MethodHandle.invokeExact`/`invoke` có quy tắc JVM riêng; `invokeWithArguments` dành cho tình huống danh sách Object động và có ngữ nghĩa khác.

## 7. `findVirtual`: receiver cũng là một tham số phải thích nghi

Handle lấy bằng `Lookup.findVirtual` thường có **receiver ở tham số đầu**, ngoài các tham số mà Java source biểu diễn trong ngoặc của instance method. Vì thế khi gọi một instance method qua method handle, kiểu receiver cũng chịu các phép thích nghi của `asType`.

Ví dụ `String.substring(int)` có kiểu handle:

~~~text
(String,int)String
~~~

dù source của instance method chỉ nhận một `int`. `String` ở vị trí đầu là receiver.

### Ví dụ 3: cast receiver, widen argument và box/unbox đồng thời

Lưu **`ReceiverAdaptDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ReceiverAdaptDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle substring = MethodHandles.lookup().findVirtual(
            String.class, "substring",
            MethodType.methodType(String.class, int.class)
        );

        System.out.println("handleType=" + substring.type());

        Object receiver = "abcdef";
        Object inexact = substring.invoke(receiver, (short) 2);
        System.out.println("inexact=" + inexact);

        String exact = (String) substring.invokeExact("abcdef", 2);
        System.out.println("exact=" + exact);

        MethodHandle general = substring.asType(
            MethodType.methodType(
                Object.class, Object.class, Object.class
            )
        );
        Object result = general.invokeExact(
            (Object) "hello",
            (Object) Integer.valueOf(1)
        );
        System.out.println("general=" + result);

        try {
            Object wrongReceiver = Integer.valueOf(42);
            Object unused = substring.invoke(wrongReceiver, 1);
        } catch (ClassCastException ex) {
            System.out.println(
                "wrongReceiver=" + ex.getClass().getSimpleName()
            );
        }
    }
}
~~~

~~~sh
javac --release 17 ReceiverAdaptDemo.java
java ReceiverAdaptDemo
~~~

**Stdout:**

~~~text
handleType=(String,int)String
inexact=cdef
exact=cdef
general=ello
wrongReceiver=ClassCastException
~~~

**Giải thích:**

- `substring.type()` là `(String,int)String`; phần `String` đầu tiên đại diện receiver.
- `Object receiver = "abcdef"`; khi `substring.invoke(receiver, (short) 2)`, call site là `(Object,short)Object`. `asType` chèn cast `Object → String`, widen `short → int` và widen reference return `String → Object`. Kết quả là `"cdef"`.
- `substring.invokeExact("abcdef",2)` với cast return `String` có descriptor trùng toàn bộ, nên chạy ngay.
- `general` nhận `(Object,Object)Object`; second Object chứa `Integer(1)` nên unbox sang `int`, first Object chứa String nên cast được sang receiver String.
- `wrongReceiver` chứa Integer: adapter có thể xây dựng từ static Object sang String, nhưng cast runtime thất bại với `ClassCastException`.

Trường hợp receiver sai kiểu không phải “JVM tự tìm một `substring` thích hợp trên Integer”. Handle vẫn mô tả chính `String.substring(int)`; conversion thất bại vì Object runtime không phải String.

## 8. Thích nghi kiểu trả về: boxing, bỏ kết quả và `void`

Kiểu trả về ảnh hưởng trực tiếp đến phép gọi. `asType` có ba quy tắc đặc biệt với `void`:

1. **Target trả giá trị, call site muốn `void`:** kết quả bị bỏ; target vẫn thực thi.
2. **Target trả `void`, call site muốn reference:** adapter tạo `null`.
3. **Target trả `void`, call site muốn primitive:** adapter tạo default value; ví dụ `0` cho `int`, `false` cho `boolean`.

Nếu target trả primitive và call site yêu cầu reference thích hợp, adapter có thể **boxing** primitive return value. Nếu target trả wrapper và call site yêu cầu primitive, adapter có thể unbox (và widening nếu hợp lệ).

### Ví dụ 4: kết quả được thay đổi theo ngữ cảnh return type

Lưu **`ReturnAdaptDemo.java`**:

~~~java
import java.lang.invoke.*;

public class ReturnAdaptDemo {
    static void log(String s) {
        System.out.println("log=" + s);
    }

    static int doubleIt(int n) {
        return n * 2;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle logger = MethodHandles.lookup().findStatic(
            ReturnAdaptDemo.class, "log",
            MethodType.methodType(void.class, String.class)
        );

        Object value = logger.invoke("alpha");
        System.out.println("voidAsObject=" + value);

        int zero = (int) logger.invoke("beta");
        System.out.println("voidAsInt=" + zero);

        MethodHandle doubleIt = MethodHandles.lookup().findStatic(
            ReturnAdaptDemo.class, "doubleIt",
            MethodType.methodType(int.class, int.class)
        );

        Object boxed = doubleIt.invoke(3);
        System.out.println(
            "boxed=" + boxed.getClass().getSimpleName() + ":" + boxed
        );

        doubleIt.invoke(4);
        System.out.println("ignoredResult=done");

        MethodHandle voidAdapter = doubleIt.asType(
            MethodType.methodType(void.class, int.class)
        );
        voidAdapter.invokeExact(5);
        System.out.println("voidAdapterType=" + voidAdapter.type());
    }
}
~~~

~~~sh
javac --release 17 ReturnAdaptDemo.java
java ReturnAdaptDemo
~~~

**Stdout:**

~~~text
log=alpha
voidAsObject=null
log=beta
voidAsInt=0
boxed=Integer:6
ignoredResult=done
voidAdapterType=(int)void
~~~

- Trong `Object value = logger.invoke("alpha")`, target return `void` và call site yêu cầu `Object`, nên kết quả được **tạo thành `null`**.
- Trong `int zero = (int) logger.invoke("beta")`, target return `void` và call site muốn `int`, nên kết quả là `0`. Đây là quy tắc riêng của adapter; **không có nghĩa** Java source thông thường cho phép ép một method `void` thành `int`.
- `doubleIt.invoke(3)` được dùng với return type `Object`, nên số `6` được boxing thành `Integer`.
- `doubleIt.invoke(4);` là expression statement; compiler tạo call-site return type `void`. `invoke` chấp nhận bỏ kết quả của target. `voidAdapter` là cách làm tường minh tương đương cho handle `(int)void`.
- `voidAdapter.invokeExact(5);` phải được viết ở statement context để có return `void` chính xác. Nếu viết `Object result = voidAdapter.invokeExact(5);`, return mismatch và sẽ ném `WrongMethodTypeException`.

Không nên lẫn “target `void` được adapter cho return `int`” với “target thực sự trả `int`”. Việc thêm giá trị mặc định do adapter thực hiện, không phải method body.

## 9. So sánh `invoke`, `asType`, `invokeWithArguments` và `explicitCastArguments`

Dùng đúng API giúp hạn chế conversion ngoài ý muốn và tránh lỗi do kiểu call site không rõ.

| API | Ý nghĩa | Khi nào phù hợp |
| --- | --- | --- |
| `handle.invokeExact(...)` | Không thích nghi call-site type; yêu cầu chính xác cả tham số và trả về | Cần type contract chính xác, call site biết tĩnh |
| `handle.invoke(...)` | Thích nghi như thể `handle.asType(callSiteType)` khi cần | Biết method handle nhưng caller sử dụng một số kiểu có thể chuyển |
| `handle.asType(newMethodType)` | Tạo handle mới có kiểu tường minh; adapter pairwise theo quy tắc `asType` | Chuẩn hóa nhiều nguồn kiểu về một API chung hoặc tái sử dụng adapter |
| `handle.invokeWithArguments(...)` | Nhận danh sách đối số dạng `Object[]`/`List<?>`; xử lý theo generic invocation và conversion theo API | Số/type arguments được xây động hoàn toàn; tooling, scripts, bridge code |
| `MethodHandles.explicitCastArguments(target,newType)` | Cho phép thêm một số phép **casting** ngoài `asType` như primitive narrowing | Có yêu cầu chủ động chuyển kiểu tường minh và đã xử lý rủi ro mất dữ liệu |

**Không nhầm `invokeWithArguments` với `invoke` thông thường.** `invokeWithArguments` thực hiện chuyển đổi từ lập luận động theo danh sách Object và có những quy tắc riêng với variable-arity handles; nó không dùng chính call-site descriptor được compiler tạo cho một lời gọi signature-polymorphic. Đổi API có thể thay đổi hiệu năng và điểm ném exception, nên cần kiểm chứng trên signature thật.

### Mẫu dùng `asType` trong lớp adapter

Đây là **snippet minh họa**, giả định có `MethodHandle target` mang đúng kiểu `(long,long)long`, được tạo như ví dụ 3:

~~~java
MethodType api = MethodType.methodType(
    Object.class, Object.class, Object.class
);
MethodHandle adapter = target.asType(api);

// Từ đây, code dùng chính xác API Object,Object -> Object.
Object result = adapter.invokeExact(
    (Object) Integer.valueOf(10),
    (Object) Long.valueOf(20)
);
System.out.println(result); // 30
~~~

Đoạn này không phải chương trình độc lập vì `target` được giả định có sẵn. Ý tưởng là chọn **một điểm chuẩn hóa kiểu**, lấy adapter trước, lưu lại rồi các caller đáp ứng descriptor exact của adapter. Điều này làm type contract dễ đọc và dễ kiểm tra hơn; không cần khẳng định performance luôn tốt hơn khi chưa đo bằng benchmark.

### Varargs collector là ngoại lệ cần xét riêng

Phân tích pairwise ở phần 4 dành cho **fixed-arity handle**. Một `MethodHandle` có trạng thái `isVarargsCollector()==true` có thể chấp nhận cách gọi variable-arity ở vị trí cuối, gom các argument thành mảng theo quy tắc API. Vì vậy, không nên khẳng định rằng `asType` luôn yêu cầu arity giống nhau trong **mọi** trường hợp.

Nếu cần tránh biến đổi varargs bất ngờ, có thể dùng `asFixedArity()` để xem handle như fixed arity; khi đó lời gọi phải phù hợp số tham số xác định, hoặc dùng combinator `asCollector` / `asSpreader` để diễn đạt việc gom/tách mảng một cách tường minh. Nội dung chính của bài này là **type adaptation**, còn collection/spreading là chủ đề riêng và không nên dùng như lý do để nhầm giữa widening và thay đổi số tham số.

## 10. Nguyên tắc chẩn đoán lỗi trong thực tế

Khi gặp `WrongMethodTypeException`, đừng chỉ nhìn runtime value. Kiểm tra theo thứ tự:

1. **In `handle.type()`.** Viết đầy đủ cả tham số và return type. Với virtual handle, đừng quên receiver đứng đầu.
2. **Suy ra call-site descriptor từ source:** kiểu tĩnh của từng biểu thức argument (kể cả `(short)`, `(Object)`, boxing wrapper hay literal `null`) và kiểu return do cast/assignment/statement context.
3. **Nếu là `invokeExact`**, so sánh hai signature **100%**: số tham số, từng `Class<?>`, kiểu trả về. Java source cast trên kết quả không sửa được một mismatch bằng conversion hậu kỳ.
4. **Nếu là `invoke`**, xét tính hợp lệ của `asType(callSiteType)`, đúng hướng parameter và return. Primitive narrowing hoặc số lượng tham số sai với fixed-arity handle thường là nguyên nhân `WrongMethodTypeException`.
5. **Nếu thấy `ClassCastException`**, adapter có thể đã hợp lệ ở mức kiểu nhưng runtime object không đúng wrapper/reference type. Kiểm tra `arg.getClass()` khi `arg != null` và kiểu target thực sự cần.
6. **Nếu thấy `NullPointerException`**, tìm chỗ unbox `null` thành primitive; cũng cần loại trừ NPE phát sinh bên trong chính target method.
7. **Nếu thấy lỗi khác**, xác định đó là lỗi access khi tạo handle (`findStatic`/`findVirtual`/`Lookup`), lỗi converter, hay exception được target ném. `invoke` khai báo `throws Throwable` nên exception target có thể truyền trực tiếp ra.
8. **Nếu đang dùng varargs collector**, xem `handle.isVarargsCollector()`, kiểu tham số mảng cuối, và có cần `asFixedArity()`/`asCollector(...)` không.
9. **Khi sửa**, chọn chuyển đổi tường minh ở một nơi: đổi call site đúng kiểu, xây `asType` adapter rõ contract, hoặc thực hiện conversion dữ liệu riêng (chẳng hạn parse chuỗi). Đừng lạm dụng `Object` để che mọi mismatch.

### Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân điển hình | Cách sửa |
| --- | --- | --- |
| `invokeExact` với `3` thay vì `3L` | Call site `int` nhưng handle nhận `long` | Dùng `3L` hoặc cast `(long) 3`, hoặc chủ động dùng `invoke` |
| `invokeExact` trong statement, handle trả `int` | Call-site return type `void` khác `int` | Dùng `int x = (int) h.invokeExact(...)` hoặc chọn `invoke` để bỏ kết quả |
| `invoke` nhận `long` nhưng target nhận `int` | Primitive narrowing bị cấm | Kiểm tra miền giá trị và cast chủ động trước call |
| `invoke` cần return `short` từ target `int` | Return narrowing bị cấm | Nhận `int` rồi chuyển giá trị có kiểm soát, hoặc dùng API casting rõ ràng |
| `invoke` nhận `Object` chứa String nhưng target nhận primitive `int` | Runtime unboxing thất bại | Parse String thành Integer/int trước, hoặc sửa dữ liệu/contract |
| `invoke` nhận `Object null` cho primitive | Unboxing null | Validate đầu vào và xử lý null rõ ràng |
| `invoke` trên virtual handle với receiver sai class | Cast receiver thất bại | Lấy đúng instance, xem `handle.type().parameterType(0)` |
| Gọi `invokeWithArguments` mong cùng hành vi với `invokeExact` | Danh sách Object/variable arity khác descriptor chính xác | Chọn API và conversion strategy theo contract |
| `findVirtual`/`findStatic` ném `IllegalAccessException` | Lookup thiếu quyền | Xem class/method access, package/module, quyền của lookup |
| Dự đoán `asType` tự parse chuỗi | Adapter không có string-to-number conversion | Thực hiện parse hoặc filter riêng |

### Quan sát kiểu tại runtime

Snippet sau giả định đã có biến `MethodHandle handle` và một đối số `value`; đây **không phải chương trình độc lập**:

~~~java
MethodType type = handle.type();
System.out.println("target=" + type);
System.out.println("parameterCount=" + type.parameterCount());
System.out.println("returnType=" + type.returnType().getTypeName());
System.out.println("varargs=" + handle.isVarargsCollector());
System.out.println("argumentRuntime=" +
    (value == null ? "null" : value.getClass().getName()));
~~~

Dòng `argumentRuntime` chỉ giúp giải thích lỗi cast/unboxing tại runtime. Nó **không thay thế** việc kiểm tra kiểu tĩnh của expression tại call site; cùng một Object runtime có thể được truyền bằng biểu thức kiểu `Object` hoặc `Integer` và dẫn đến descriptor khác nhau.

## 11. Bài tập tự kiểm tra

**Câu 1.** Handle có kiểu `(long)long`. `(long) h.invoke(5)` có chạy được không? Còn `(long) h.invokeExact(5)`?

**Đáp án:** `invoke` có thể widen argument `int → long`. `invokeExact` không chạy vì parameter call-site type `int` không trùng `long`. Viết `5L` để exact.

**Câu 2.** Handle có kiểu `(int)int`. `long result = (long) h.invoke(7)` có chạy được không? `long result = (long) h.invokeExact(7)` thì sao?

**Đáp án:** `invoke` có thể widen return `int → long`. `invokeExact` ném `WrongMethodTypeException` do return type không khớp dù argument đúng.

**Câu 3.** Handle `(int)int` nhận `Object x = Integer.valueOf(7)`; gọi `(int) h.invoke(x)` có thể thành công không? Nếu `x = "7"`?

**Đáp án:** Với Integer, Object được unbox thành `int` và có thể chạy; với String, adapter hợp lệ ở mức static Object nhưng runtime unboxing thất bại với `ClassCastException`. API không parse `"7"`.

**Câu 4.** Vì sao adapter `(Object,Object)Object` được tạo từ handle `(long,long)long` vẫn có thể ném exception khi gọi `invokeExact`?

**Đáp án:** Descriptor của `invokeExact` khớp adapter, nhưng **conversion bên trong adapter** vẫn phụ thuộc giá trị Object. Object sai kiểu ném `ClassCastException`; null khi phải unbox sang long ném `NullPointerException`.

**Câu 5.** Một handle gốc `(String)void` được gọi bằng `Object result = h.invoke("hello")`; result là gì?

**Đáp án:** `null`; `asType` có quy tắc sinh null khi chuyển return `void` sang reference. Target vẫn được chạy.

**Câu 6.** Tại sao `Object receiver = "hello"` có thể dùng với `substring.invoke(receiver,1)`, nhưng `substring.invokeExact(receiver,1)` không khớp?

**Đáp án:** Virtual handle có receiver parameter `String`. Với `invoke`, có thể cast runtime `Object → String`. `invokeExact` yêu cầu receiver argument có kiểu tĩnh `String` và return descriptor tương ứng; biến `Object` không khớp.

**Câu 7.** `asType` có thể đổi primitive `long` thành `int` để đáp ứng một caller không? Khi nào cần `explicitCastArguments`?

**Đáp án:** Không cho primitive narrowing theo `asType`. Nếu bài toán thực sự cho phép narrowing và chấp nhận rủi ro mất dữ liệu, có thể cân nhắc `explicitCastArguments` với type contract tường minh, hoặc cast chủ động trước khi gọi.

**Câu 8.** `MethodHandle.type()` thay đổi khi bạn gọi `h.asType(newType)` không?

**Đáp án:** Không. `asType` trả về một handle thích nghi mới, còn `h` ban đầu giữ nguyên. Với `newType` bằng chính kiểu cũ, API trả lại handle gốc.

## 12. Nguồn tham khảo chính thống

- Java SE 17 — `java.lang.invoke.MethodHandle` (các mục *Method handle compilation*, *Method handle invocation*, `invoke`, `invokeExact`, `asType`, `invokeWithArguments`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17 — `java.lang.invoke.MethodType` và `MethodHandle.type()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE 17 — `java.lang.invoke.MethodHandles` (`lookup`, `findStatic`, `findVirtual` và `explicitCastArguments`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17 — `WrongMethodTypeException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html
- Java Language Specification 17 — *Method Invocation Conversion*, `5.3`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3

**Kết luận cần nhớ:** `invokeExact` yêu cầu descriptor tại call site trùng `MethodHandle.type()`, **kể cả return type**. `invoke` cho phép một descriptor khác nếu kiểu handle có thể chuyển bằng `asType`: widening primitive, boxing, unboxing, reference cast và các quy tắc `void` phù hợp. Khi conversion không thể hình thành, gặp `WrongMethodTypeException`; khi conversion hợp lệ nhưng giá trị runtime sai kiểu hoặc null không thể unbox, có thể gặp `ClassCastException` hoặc `NullPointerException`.