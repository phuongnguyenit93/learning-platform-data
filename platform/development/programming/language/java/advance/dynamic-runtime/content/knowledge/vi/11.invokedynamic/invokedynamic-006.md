# 11.6 Kiểm tra kiểu target và quan hệ giữa CallSite với chỉ thị invokedynamic

Trong JVM, chỉ thị **`invokedynamic`** không ghi cố định một method đích theo cách `invokestatic` hoặc `invokevirtual` thường làm. Thay vào đó, nó mang một **tên và method descriptor cố định trong class file**, rồi nhờ một **bootstrap method** liên kết vị trí gọi với một đối tượng `java.lang.invoke.CallSite`. `CallSite` giữ một `MethodHandle` gọi là **target**. Khi liên kết thành công, JVM chuyển các lần gọi sau đến target của call site đó.

Điều kiện kiểu quan trọng nhất:

> **`callSite.getTarget().type()` phải bằng chính xác `MethodType` của descriptor được ghi tại chỉ thị `invokedynamic`.** Một `CallSite` được phép đổi target nếu thuộc loại mutable, nhưng không được đổi **kiểu** của target trong suốt vòng đời.

Học xong phần này, bạn sẽ phân biệt được **kiểu tại call site**, **kiểu target**, **kiểu của bootstrap method**, khi nào JVM ném `BootstrapMethodError`, khi nào `setTarget` ném `WrongMethodTypeException`, và vì sao `dynamicInvoker()` không giống việc giữ lại một `getTarget()` cũ.

## 1. Từ vựng: chỉ thị, bootstrap, CallSite và target

| Thành phần | Vai trò | Điều cố định / có thể thay đổi |
| --- | --- | --- |
| `invokedynamic` instruction | Vị trí gọi động trong bytecode; chỉ tới call site specifier gồm bootstrap method, tên và descriptor | Tên/descriptor cố định trong class file |
| `MethodType` của vị trí gọi | Chữ ký JVM `(tham_số...)kiểu_trả_về`; chính là contract mà các giá trị trên operand stack phải thỏa | Cố định cho vị trí `invokedynamic` |
| Bootstrap method (BSM) | Chạy trong quá trình liên kết, nhận context của caller, tên, `MethodType` và static arguments nếu có; trả `CallSite` | Chạy khi resolution cần; không phải body được gọi mỗi lần |
| `CallSite` | Giữ target `MethodHandle` và bảo đảm kiểu target không đổi | Identity của site được liên kết cố định; target có thể đổi tùy subclass |
| `CallSite.getTarget()` | Lấy handle target hiện tại tại thời điểm đọc | Có thể trả một handle khác sau khi retarget |
| `CallSite.dynamicInvoker()` | Lấy handle thực thi **qua site**, theo target hiện tại | Kiểu cố định, hành vi theo target hiện tại |
| `ConstantCallSite` | Site có target không thể đổi | Target cố định |
| `MutableCallSite` | Site cho đổi target theo ngữ nghĩa biến thông thường | Target đổi được; cần phối hợp visibility đa luồng |
| `VolatileCallSite` | Site có target với ngữ nghĩa volatile | Target đổi được; cập nhật được quan sát theo volatile rules |

Một `CallSite` có thể được JVM liên kết với `invokedynamic`, nhưng cũng có thể tồn tại **độc lập** (*free-floating*), không gắn với bất kỳ instruction nào. Tự viết `new MutableCallSite(...)` trong Java **không tự sinh** một chỉ thị `invokedynamic`. Bạn vẫn có thể gọi site qua `dynamicInvoker()` để kiểm thử cùng mô hình định tuyến.

### Hai đường gọi khác nhau

~~~text
Đường A — một instruction invokedynamic THẬT trong class file

  bytecode invokedynamic (name, descriptor, bootstrap reference, static args)
                        |
        JVM lần đầu liên kết: gọi bootstrap
                        |
          bootstrap trả về CallSite
                        |
        JVM xác nhận target.type() == descriptor
                        |
           lần gọi này và các lần sau
                        |
               CallSite target
                        |
                  method body


Đường B — một CallSite tạo bằng Java source

  new MutableCallSite(target)
                        |
        callSite.dynamicInvoker()
                        |
               CallSite target
                        |
                  method body

Đường B mô phỏng cơ chế target động, nhưng KHÔNG tự tạo invokedynamic bytecode.
~~~

## 2. Kiểu tại invokedynamic là contract tĩnh, không phải “kiểu của bootstrap”

Giả sử class file chứa một instruction có tên `transform` và descriptor JVM:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

Biểu diễn bằng Java API:

~~~java
MethodType siteType = MethodType.methodType(
        String.class, String.class);
System.out.println(siteType);                    // (String)String
System.out.println(siteType.toMethodDescriptorString());
// (Ljava/lang/String;)Ljava/lang/String;
~~~

Đoạn trên là các câu lệnh minh họa trong một method có import `java.lang.invoke.MethodType`. Chữ ký `(String)String` này có nghĩa instruction nhận đúng một tham số `String` và trả `String`. Đối số đó không nhất thiết là receiver của instance method; `invokedynamic` không tự yêu cầu receiver và có thể được liên kết với đủ loại handle đã thích nghi đúng descriptor.

Trong khi đó, bootstrap method phổ biến lại có chữ ký **khác hẳn**:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String invokedName,
        MethodType invokedType) throws Throwable
~~~

- `caller`: một `Lookup` đại diện cho lớp **chứa instruction `invokedynamic`**, phục vụ resolution và access checks.
- `invokedName`: tên symbolic tại call site specifier.
- `invokedType`: `MethodType` từ descriptor của **instruction**, ví dụ `(String)String`.
- Các static bootstrap arguments bổ sung (nếu có) được JVM truyền sau ba đối số chuẩn; chúng đến từ phần metadata class file, không phải những đối số runtime của instruction.
- Bootstrap trả **`CallSite`**, không phải `MethodHandle` trực tiếp. JVM sẽ quan sát target do `CallSite` giữ và kiểm tra kiểu của target.

Nếu bootstrap có kiểu `(Lookup,String,MethodType)CallSite` thì đó là **chữ ký để gọi bootstrap**, không phải kiểu mà target phải mang. Hai chữ ký này giải quyết hai chức năng tách biệt.

Một mô hình liên kết:

~~~text
invokedynamic transform : (String)String
           |
           | gọi BSM với (Lookup, "transform", MethodType(String,String))
           v
bootstrap(...) -> new ConstantCallSite(target)
                                    |
                            target.type()=(String)String
                                    |
                           JVM so khớp kiểu: PASS
                                    |
                             liên kết instruction
~~~

**`MethodType.equals` là chuẩn cần so.** `(String)String` khác `(Object)Object` dù Java có thể cast giữa hai kiểu tham chiếu. `(int)int` khác `(Integer)Integer`, và `(long)long` khác `(int)int`. JVM không tự chèn adapter để cứu một bootstrap trả target sai descriptor.

## 3. Luồng linkage của một instruction theo JVMS

Ở mức khái niệm, JVM xử lý như sau:

1. Một instruction `invokedynamic` ban đầu **chưa liên kết** với target. Constant pool và `BootstrapMethods` attribute cung cấp bootstrap specifier, tên, descriptor và static arguments.
2. Trước khi instruction được thực thi lần đầu, JVM resolve các mục cần thiết và chuẩn bị `Lookup` của caller, tên, `MethodType` và static arguments; tiếp đó gọi bootstrap với semantics tương tự `MethodHandle.invoke`.
3. Bootstrap tính toán hoặc tra cứu `MethodHandle` cần dùng rồi trả một `CallSite` (thường `ConstantCallSite`, `MutableCallSite` hoặc `VolatileCallSite`).
4. JVM **kiểm tra kết quả bootstrap không null, là `CallSite`, và `CallSite.type()` bằng descriptor của instruction**. Do `CallSite` duy trì bất biến kiểu, kiểm tra `getTarget().type()` tương đương về mặt hợp đồng.
5. Nếu hợp lệ, instruction được **liên kết đến CallSite**. Các lần thực thi sau dùng target của site mà không phải gọi lại bootstrap chỉ để dispatch.
6. Nếu linkage thất bại, JVM báo lỗi linkage. Các lần thử lại **cùng instruction** không khiến bootstrap chạy lại sau khi resolution đó đã thất bại; lỗi resolution được ghi nhận cho instruction.

**Tinh tế về concurrency:** khi nhiều thread đồng thời đi tới một instruction chưa liên kết, JVM có thể gọi bootstrap nhiều lần trong quá trình cạnh tranh; một kết quả site hợp lệ được chọn để cài đặt cho instruction, các kết quả khác có thể bị bỏ qua. Vì vậy không giả định “bootstrap method chắc chắn chỉ chạy đúng một lần toàn tiến trình”, dù instruction sau khi liên kết không bootstrap lại ở mỗi invocation. Nếu bootstrap có side effect, phải tính đến cạnh tranh đó.

**CallSite identity không đồng nghĩa target identity.** Với mutable/volatile site, JVM giữ liên kết với **site**, còn site có thể tham chiếu một target mới. Việc thay target **không sửa opcode hoặc descriptor**, và không có nghĩa phải bootstrap lại.

## 4. Bất biến kiểu: `CallSite.type()` và `getTarget().type()`

Theo API `CallSite`:

~~~java
MethodType signature = callSite.type();
MethodHandle current = callSite.getTarget();
boolean same = signature.equals(current.type());  // true với CallSite hợp lệ
~~~

Đoạn minh họa giả định biến `callSite` đã tồn tại. `type()` trả **kiểu vĩnh viễn** của site. `getTarget().type()` phải bằng kiểu đó. Một site có thể đổi target, nhưng **không thể đổi kiểu** sang một `MethodType` khác.

Ví dụ hợp lệ:

~~~text
site.type()                = (String)String
firstTarget.type()         = (String)String
secondTarget.type()        = (String)String
setTarget(secondTarget)    = OK (với MutableCallSite / VolatileCallSite)
~~~

Ví dụ không hợp lệ:

~~~text
site.type()                = (String)String
wrongTarget.type()         = (String)int
setTarget(wrongTarget)     = WrongMethodTypeException
~~~

Điểm quan trọng: `CallSite` yêu cầu **đúng kiểu tuyệt đối** khi đổi target. Không có chuyện “`int` có thể boxing sang `Integer`” hay “`String` là `Object` nên chấp nhận”: nếu `MethodType.equals` trả `false`, `setTarget` từ chối. Khi muốn chuyển đổi an toàn, cần tạo **adapter handle** có `type()` chính xác bằng site type rồi mới cài đặt.

~~~java
MethodHandle generic = lookup.findStatic(
        SomeClass.class, "fromObject",
        MethodType.methodType(Object.class, Object.class));
MethodHandle adapted = generic.asType(
        MethodType.methodType(String.class, String.class));
// adapted.type() = (String)String, nếu conversion được hỗ trợ
~~~

Đây là đoạn **minh họa**, yêu cầu class `SomeClass` có `public/static Object fromObject(Object)` hoặc quyền lookup phù hợp. `asType` có thể chèn reference casts và các chuyển đổi được Java MethodHandle API cho phép; **không** thực hiện mọi chuyển đổi dữ liệu tùy ý. Ví dụ adapter từ `(Object)Object` sang `(String)String` sẽ chuyển argument `String` thành reference `Object` khi gọi, rồi cast kết quả trả về thành `String`. Nếu actual result không phải `String`, bạn có thể nhận `ClassCastException` **khi chạy**, dù hai `MethodType` ở chỗ nối đã đúng.

### Bảng phân biệt ba phép kiểm tra

| Vị trí kiểm tra | Quy tắc | Lỗi khi sai |
| --- | --- | --- |
| **Liên kết `invokedynamic`** bằng kết quả bootstrap | `callSite.type().equals(invokedynamicDescriptor)` | `BootstrapMethodError` |
| **`MutableCallSite`/`VolatileCallSite.setTarget`** | `newTarget.type().equals(callSite.type())` | `WrongMethodTypeException` |
| **`MethodHandle.invokeExact`** từ Java code | Kiểu argument **và return** tại Java call-site phải bằng `handle.type()` | `WrongMethodTypeException` |

Ba lỗi này diễn ra ở **ba tầng khác nhau**. Đừng gom tất cả vào câu “invokedynamic sai kiểu thì luôn ném `WrongMethodTypeException`”. Một `invokedynamic` đã được liên kết thành công mang descriptor khớp target type theo thiết kế; lỗi sai kiểu ở bước bootstrap là **linkage error**. Target method vẫn có thể chủ động ném exception của chính nó, kể cả những runtime exception khác.

## 5. ConstantCallSite, MutableCallSite, VolatileCallSite

### `ConstantCallSite`

~~~java
CallSite site = new ConstantCallSite(target);
~~~

- Target vĩnh viễn. `getTarget()` và `dynamicInvoker()` đều dẫn tới chính target đó; `ConstantCallSite.dynamicInvoker()` trả permanent target.
- `setTarget(...)` luôn ném `UnsupportedOperationException`, ngay cả khi new handle có cùng kiểu.
- Dùng khi linkage không cần tái định tuyến, ví dụ rất nhiều call sites của lambda metafactory hoặc chuỗi ghép do compiler tạo.

### `MutableCallSite`

~~~java
MutableCallSite site = new MutableCallSite(firstTarget);
MethodHandle dispatcher = site.dynamicInvoker();
site.setTarget(secondTarget);                 // type phải bằng firstTarget.type()
MutableCallSite.syncAll(new MutableCallSite[] { site });
~~~

- `getTarget()` đọc target như một biến thông thường; giá trị target có thể thay đổi.
- `dynamicInvoker()` là một handle **gắn với CallSite**, không phải snapshot của target tại thời điểm lấy dispatcher. Khi target đổi, dispatcher có thể gọi target mới.
- Nếu nhiều thread cùng gọi, write `setTarget` **không tự bảo đảm** các thread khác nhận ra bản cập nhật ngay. `syncAll(...)` dùng để buộc các thread bỏ các target cache cũ theo hợp đồng memory visibility được Javadoc mô tả.
- `syncAll` không đảo ngược invocation đã bắt đầu với target cũ; nó có chi phí, nên thường batch các thay đổi. Đồng bộ giữa các writer cũng cần được thiết kế đúng.

Một `MutableCallSite(MethodType)` có thể tạo **site chưa có target nghiệp vụ**. Khi đó target mặc định là handle cùng kiểu nhưng sẽ ném `IllegalStateException` nếu bị gọi; hãy `setTarget` trước khi đưa site vào luồng sử dụng.

### `VolatileCallSite`

~~~java
VolatileCallSite site = new VolatileCallSite(firstTarget);
MethodHandle dispatcher = site.dynamicInvoker();
site.setTarget(secondTarget);
~~~

- Target có ngữ nghĩa đọc/ghi như một biến `volatile`. Các thread đọc sau sẽ nhận cập nhật theo quy tắc volatile memory consistency.
- Không cần API `syncAll` (và không có `VolatileCallSite.syncAll`).
- Có thể có chi phí đồng bộ so với mutable call site tùy workload. Dùng khi cập nhật thường xuyên và visibility giữa thread là yêu cầu rõ ràng.

### Trả lời câu hỏi “`getTarget()` hay `dynamicInvoker()`?”

Nếu bạn gọi:

~~~java
MethodHandle savedTarget = mutable.getTarget();
MethodHandle live = mutable.dynamicInvoker();
mutable.setTarget(next);
~~~

sau đó `savedTarget.invokeExact(...)` vẫn gọi **handle cũ mà bạn đã giữ**, còn `live.invokeExact(...)` thực thi thông qua site và có thể quan sát target **mới** theo chính sách đồng bộ của subclass. Không cần tạo lại `live` mỗi lần target đổi.

## 6. Bootstrap method: trả `CallSite` đúng type

Một bootstrap đơn giản cho instruction giả định `transform:(String)String`:

~~~java
public static CallSite bootstrap(MethodHandles.Lookup caller,
                                 String name, MethodType type)
        throws NoSuchMethodException, IllegalAccessException {
    MethodHandle target = caller.findStatic(
            MyLinker.class, name, type);
    return new ConstantCallSite(target);
}
~~~

Đoạn này là **minh họa trong class `MyLinker`**, giả sử `MyLinker` có static method trùng tên/chữ ký và lookup có quyền truy cập. Nếu `name="transform"` và `type=(String)String`, `target.type()` cũng là `(String)String`, đáp ứng contract. Nếu method không tồn tại hoặc không thể truy cập, `findStatic` ném lỗi; khi JVM thực sự dùng bootstrap để liên kết `invokedynamic`, lỗi non-`Error` từ bootstrap thường được bọc thành `BootstrapMethodError`.

Một bootstrap thực tế có thể tạo handle bằng `findVirtual`, `filterArguments`, `guardWithTest`, `asType`, `bindTo` hoặc cache theo schema/caller. Điều cần giữ là:

~~~java
if (!target.type().equals(type)) {
    throw new IllegalArgumentException(
            "target " + target.type() + " differs from invokedynamic " + type);
}
return new ConstantCallSite(target);
~~~

Đây là đoạn kiểm tra **minh họa**, không phải method độc lập. Nếu bootstrap chọn reject và ném `IllegalArgumentException` trong quá trình linkage, JVM sẽ báo lỗi bootstrap (`BootstrapMethodError` do exception non-`Error`), thay vì đợi JVM nhận CallSite sai kiểu. Trường hợp muốn **adapt có chủ đích**:

~~~java
MethodHandle adjusted = target.asType(type);
return new ConstantCallSite(adjusted);
~~~

`asType` chỉ hợp lệ nếu adapter conversion được hỗ trợ. Nó có thể ném `WrongMethodTypeException` ở giai đoạn bootstrap; nếu lỗi này xảy ra trong linkage thực, JVM có thể bọc nó trong `BootstrapMethodError`. Không suy ra “`asType` luôn sửa được mọi mismatch”.

### Bootstrap không được tự do trả gì cũng được

| Bootstrap trả | Khi thật sự liên kết một `invokedynamic` | Vì sao |
| --- | --- | --- |
| `new ConstantCallSite(target đúng type)` | Linkage thành công | Target type bằng descriptor |
| `new MutableCallSite(target đúng type)` | Linkage thành công | Type đúng; target được phép đổi về sau |
| `new VolatileCallSite(target đúng type)` | Linkage thành công | Type đúng; cập nhật có volatile semantics |
| `null` | `BootstrapMethodError` | Thiếu CallSite |
| Một object không phải `CallSite` | `BootstrapMethodError` (sau conversion/check của bootstrap result) | Sai loại kết quả |
| `CallSite` có type **khác** descriptor | `BootstrapMethodError` | Mismatch ở **JVM linkage**, không phải do `CallSite` tự sai |
| Bootstrap ném checked exception hoặc runtime exception | Thường `BootstrapMethodError` bọc nguyên nhân nếu không phải `Error` | Linkage không hoàn tất |
| Bootstrap ném `Error` | Quy tắc JVM có thể truyền chính `Error` đó | Không phải mọi lỗi luôn bị bọc |

**Phân biệt quan trọng:** hoàn toàn hợp lệ khi Java code tự gọi `new ConstantCallSite(wrongTypedHandle)` — constructor chỉ biết kiểu của **chính handle đó**. Nó không biết descriptor của một instruction nào khác. `BootstrapMethodError` chỉ xảy ra khi JVM cố liên kết CallSite ấy với **một instruction có descriptor không phù hợp**.

## 7. Ví dụ Java 17+ hoàn chỉnh: so khớp kiểu, đổi target và một invokedynamic thật

Tạo file **`IndyCallSiteDemo.java`**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;
import java.util.function.UnaryOperator;

public class IndyCallSiteDemo {
    private static String first(String value) { return "v1:" + value; }
    private static String second(String value) { return "v2:" + value; }
    private static int length(String value) { return value.length(); }
    private static Object throughObject(Object value) { return "object:" + value; }

    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String name, MethodType type)
            throws NoSuchMethodException, IllegalAccessException {
        MethodHandle target = caller.findStatic(IndyCallSiteDemo.class, name, type);
        return new ConstantCallSite(target);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType siteType = MethodType.methodType(String.class, String.class);
        MethodHandle a = lookup.findStatic(IndyCallSiteDemo.class, "first", siteType);
        MethodHandle b = lookup.findStatic(IndyCallSiteDemo.class, "second", siteType);
        MethodHandle wrong = lookup.findStatic(IndyCallSiteDemo.class, "length",
                MethodType.methodType(int.class, String.class));

        System.out.println("descriptor = " + siteType.toMethodDescriptorString());
        ConstantCallSite constant = new ConstantCallSite(a);
        System.out.println("constant type = " + constant.type());
        System.out.println("constant invoke = " + (String) constant.dynamicInvoker().invokeExact("x"));
        try {
            constant.setTarget(b);
        } catch (UnsupportedOperationException expected) {
            System.out.println("constant relink = " + expected.getClass().getSimpleName());
        }

        MutableCallSite mutable = new MutableCallSite(a);
        MethodHandle dynamic = mutable.dynamicInvoker();
        MethodHandle snapshot = mutable.getTarget();
        System.out.println("mutable before = " + (String) dynamic.invokeExact("x"));
        mutable.setTarget(b);
        MutableCallSite.syncAll(new MutableCallSite[] { mutable });
        System.out.println("mutable after = " + (String) dynamic.invokeExact("x"));
        System.out.println("saved target = " + (String) snapshot.invokeExact("x"));
        try {
            mutable.setTarget(wrong);
        } catch (WrongMethodTypeException expected) {
            System.out.println("incompatible relink = " + expected.getClass().getSimpleName());
        }
        MethodHandle generic = lookup.findStatic(IndyCallSiteDemo.class, "throughObject",
                MethodType.methodType(Object.class, Object.class));
        MethodHandle adapted = generic.asType(siteType);
        mutable.setTarget(adapted);
        MutableCallSite.syncAll(new MutableCallSite[] { mutable });
        System.out.println("adapted target = " + (String) dynamic.invokeExact("x"));
        System.out.println("type invariant = " + mutable.type().equals(mutable.getTarget().type()));

        VolatileCallSite volatileSite = new VolatileCallSite(a);
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();
        System.out.println("volatile before = " + (String) volatileInvoker.invokeExact("x"));
        volatileSite.setTarget(b);
        System.out.println("volatile after = " + (String) volatileInvoker.invokeExact("x"));

        CallSite manual = bootstrap(lookup, "first", siteType);
        System.out.println("bootstrap manual = " + (String) manual.dynamicInvoker().invokeExact("x"));
        CallSite independentlyWrong = new ConstantCallSite(wrong);
        System.out.println("wrong descriptor = " + !siteType.equals(independentlyWrong.type()));

        // javac emits an invokedynamic instruction for this lambda metafactory call site.
        UnaryOperator<String> trim = String::trim;
        System.out.println("lambda = [" + trim.apply(" x ") + "]");
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file, sử dụng **JDK 17 trở lên**:

~~~bash
javac --release 17 IndyCallSiteDemo.java
java IndyCallSiteDemo
~~~

**`stdout` chính xác:**

~~~text
descriptor = (Ljava/lang/String;)Ljava/lang/String;
constant type = (String)String
constant invoke = v1:x
constant relink = UnsupportedOperationException
mutable before = v1:x
mutable after = v2:x
saved target = v1:x
incompatible relink = WrongMethodTypeException
adapted target = object:x
type invariant = true
volatile before = v1:x
volatile after = v2:x
bootstrap manual = v1:x
wrong descriptor = true
lambda = [x]
~~~

Chương trình này đã được biên dịch với `javac --release 17` và thực thi trên JDK 21; cả 15 dòng output ở trên đã được đối chiếu. Nó **không cố tình tạo một instruction invokedynamic có bootstrap sai** (điều đó đòi kiểm soát class file), mà mô tả sự khác nhau giữa call-site object độc lập và instruction thật thông qua một method reference do `javac` phát sinh.

### 7.1. Diễn giải các dòng in quan trọng

1. `descriptor` là dạng JVM của `(String)String`. Đó là type mà site trong ví dụ mong đợi.
2. `constant` được tạo từ handle `first:(String)String` nên có kiểu `(String)String`. `constant.setTarget(b)` ném `UnsupportedOperationException` vì target bất biến.
3. `mutable.dynamicInvoker()` trả handle gọi qua site. Lần đầu trả `v1:x`; sau `mutable.setTarget(b)`, dispatcher vẫn là object handle cũ nhưng trả `v2:x`.
4. `snapshot = mutable.getTarget()` được lưu **trước khi đổi target** nên vẫn gọi `first` và trả `v1:x`. Đây là sự khác biệt giữa **saved target** và **dynamic invoker**.
5. `wrong` có type `(String)int`, không bằng `(String)String`; `mutable.setTarget(wrong)` lập tức ném `WrongMethodTypeException`. Lỗi này xảy ra trong **Java API**, chưa hề có instruction invokedynamic nào liên kết sai.
6. `generic` có type `(Object)Object`. `generic.asType(siteType)` tạo adapter có type `(String)String`; do method trả `"object:"+value` là `String` thật, cast return thành công.
7. `VolatileCallSite` trả `v1:x` rồi `v2:x` sau update; không dùng `syncAll` vì target có volatile semantics.
8. `bootstrap(lookup,"first",siteType)` được gọi **thủ công từ Java code**, trả `ConstantCallSite` phù hợp. Lời gọi thủ công **không chứng minh** rằng Java source đã gắn method này làm bootstrap của một invokedynamic instruction.
9. `independentlyWrong` là CallSite riêng với type `(String)int`, nên `wrong descriptor = true`; constructor này **không** ném `BootstrapMethodError`. Lỗi BME chỉ được áp dụng nếu JVM thực sự cố liên kết CallSite sai kiểu đó với instruction cần `(String)String`.
10. `String::trim` là một method reference. Compiler Java 17 tạo một `invokedynamic` dùng lambda metafactory để có `UnaryOperator`; khi gọi `trim.apply(" x ")`, kết quả là `"x"`. Đây mới là **instruction `invokedynamic` thật** bên trong class file chương trình.

## 8. Tự kiểm tra bytecode: `javap` chứng minh điều gì?

Chạy tiếp (trong thư mục chứa `IndyCallSiteDemo.class`):

~~~bash
javap -c -p IndyCallSiteDemo
javap -v -p IndyCallSiteDemo
~~~

Với `javac --release 17`, trong output `-c` bạn sẽ thấy các instruction `invokedynamic`. Những dòng ghép chuỗi có thể đi qua `StringConcatFactory`; đáng chú ý hơn, biểu thức `String::trim` sinh một instruction tương ứng với factory của functional interface. Một dòng tiêu biểu có dạng (constant-pool index thay đổi theo compiler):

~~~text
invokedynamic #...,  0  // InvokeDynamic #...:apply:()Ljava/util/function/UnaryOperator;
~~~

Trong output `-v`, phần `BootstrapMethods` chứa một entry tham chiếu đến `java/lang/invoke/LambdaMetafactory.metafactory` với các static arguments do compiler cung cấp. Đó là **bootstrap method thật của lambda call site**, không phải method `IndyCallSiteDemo.bootstrap` mà ví dụ gọi bằng tay. Java source thông thường **không có cú pháp trực tiếp** để viết instruction invokedynamic với bootstrap tùy ý; muốn dùng chính bootstrap của bạn phải sinh/chỉnh class file đúng chuẩn bằng một công cụ bytecode thích hợp.

### Một bẫy về `MethodType` trong ví dụ lambda

Instruction làm ra `UnaryOperator` có descriptor đại loại:

~~~text
()Ljava/util/function/UnaryOperator;
~~~

Tức **instruction `invokedynamic` ở chỗ method reference trả về đối tượng functional interface**, không nhất thiết có descriptor `(String)String` là signature của method `String.trim` hoặc lời gọi `UnaryOperator.apply`. Sau đó gọi `trim.apply(...)` là một invocation khác, thông thường `invokeinterface` với generic-erased descriptor `(Object)Object`.

Vì thế khi đọc `javap`:

- Lấy descriptor **ngay tại từng instruction `invokedynamic`** làm type cần so với `CallSite` được bootstrap tạo cho instruction đó.
- Đừng thay bằng descriptor của method implementation (ở đây `String.trim()`) hoặc method interface SAM (ở đây `UnaryOperator.apply(Object):Object`).
- `LambdaMetafactory` dùng các static bootstrap arguments, như SAM method type, implementation method handle và instantiated method type, để liên kết một factory target có type đúng descriptor của instruction.

Điểm này rất quan trọng: cùng một chương trình có thể có **nhiều instruction invokedynamic** (lambda, method reference, string concatenation...), mỗi instruction có bootstrap specifier và descriptor riêng. Không được áp dụng một `MethodType` của site A cho site B chỉ vì cả hai dùng MethodHandle.

## 9. Phân biệt `BootstrapMethodError` và các lỗi MethodHandle thông thường

| Trường hợp | Lỗi dự kiến | Diễn giải |
| --- | --- | --- |
| Bootstrap trả `null` cho `invokedynamic` | `BootstrapMethodError` | JVM không nhận được CallSite |
| Bootstrap trả CallSite type `(String)int` cho instruction `(String)String` | `BootstrapMethodError` | Type mismatch ở **liên kết instruction** |
| Bootstrap cần lookup method nhưng `findStatic` ném `NoSuchMethodException` | Thường `BootstrapMethodError` bọc cause | Exception không thuộc `Error` khi bootstrap chạy |
| Bootstrap tự ném một `Error` | Có thể truyền chính `Error` | Theo linkage error rules, không mặc định bọc mọi `Error` |
| `MutableCallSite.setTarget` với method type không bằng site type | `WrongMethodTypeException` | Bất biến type của site bị vi phạm |
| `ConstantCallSite.setTarget` bất kể type | `UnsupportedOperationException` | Target là vĩnh viễn |
| `MethodHandle.invokeExact` từ Java code với descriptor khác handle type | `WrongMethodTypeException` | Lỗi tại vị trí gọi handle |
| `asType` không có conversion hợp lệ | `WrongMethodTypeException` (có thể ở bước tạo adapter) | Không thể tạo adapter đúng contract |
| Target handle thực thi body và ném `IllegalArgumentException` | `IllegalArgumentException` từ target | Không đồng nhất với lỗi kiểm tra type linkage |
| `new MutableCallSite(methodType)` bị gọi trước khi cài target nghiệp vụ | `IllegalStateException` | Default target chưa được khởi tạo để làm việc hữu ích |

Cần hiểu chính xác hai tầng lỗi:

**Tầng 1: bootstrap/linkage.** JVM chưa cài được site đúng contract thì báo `BootstrapMethodError` hoặc lỗi liên kết theo quy tắc JVMS. Lỗi đó không được sửa bằng cách cứ gọi lại cùng instruction để hy vọng bootstrap chạy lại.

**Tầng 2: invocation sau linkage.** Sau khi liên kết hợp lệ, target vẫn có thể ném exception của business logic hoặc lỗi của adapter/handle nằm sâu bên trong. Không được suy ra rằng mọi exception khi thực thi instruction đều là lỗi bootstrap. Riêng descriptor của instruction và target type đã được JVM xác nhận tương thích về mặt linkage.

## 10. Chuyển target an toàn: type adapter, visibility và versioning

Một dispatcher động có thể cần đổi từ handler `v1` sang `v2` khi chạy. Quy trình đúng:

1. Lấy `MethodType` từ **contract của site** và xác minh target mới có đúng loại trả về và danh sách parameter types.
2. Nếu không khớp nhưng có thể chuyển an toàn, dùng `asType(site.type())` hoặc các combinators phù hợp để tạo handle **đúng kiểu**, tránh tự chỉnh `MethodType` của site.
3. Kiểm thử adapter với dữ liệu biên; `asType` có thể chấp nhận một conversion mà giá trị runtime thực tế lại cast thất bại.
4. `setTarget(adapted)` trên `MutableCallSite` hoặc `VolatileCallSite`, không trên `ConstantCallSite`.
5. Nếu dùng `MutableCallSite` giữa nhiều thread, phối hợp ghi và `syncAll` theo tài liệu; nếu cần target update nhìn thấy như volatile, dùng `VolatileCallSite`.
6. Không đưa một site vẫn dùng tới target sai kiểu hoặc target chưa sẵn sàng cho người gọi. Nếu đổi sang logic mới cần thêm input, hãy thích nghi nó về descriptor cũ bằng cách bind/filter/defaulting, **không** biến `(String)String` thành `(String,int)String` tại site đã liên kết.

Ví dụ: nếu target mới cần thêm một cấu hình `prefix`, bạn có thể `insertArguments(targetWithPrefix, position, prefix)` để gắn giá trị cố định, tạo ra handle nhận cùng parameter list cũ. Đây là mô hình thay đổi **implementation** nhưng giữ **ABI của call site**.

### Class loader, modules và quyền truy cập

`MethodType` chứa các `Class<?>` thực tế, không chỉ tên kiểu in ra. Hai class có cùng binary name nhưng đến từ hai class loader khác nhau là **hai runtime types khác nhau**, do đó hai MethodType có thể không bằng nhau dù biểu diễn chuỗi trông giống nhau. Ở biên plugin/class loader, đừng so kiểu chỉ bằng `toString()`.

`MethodHandles.Lookup` còn giới hạn khả năng resolve target theo accessibility/JPMS; chỉ vì bootstrap nhận `Lookup` không có nghĩa nó có thể gọi mọi private method của bất kỳ class nào. Hãy dùng lookup đúng caller, xác thực các static bootstrap arguments và hạn chế target đối với input không tin cậy. Một handle private có thể trở thành capability, không nên bị leak tùy tiện.

### Caching và hiệu năng

`invokedynamic` đặc biệt hữu ích khi liên kết một lần rồi gọi nhiều lần. Với `ConstantCallSite`, target ổn định giúp JVM có cơ hội tối ưu. Với `MutableCallSite`/`VolatileCallSite`, JVM phải tôn trọng semantics relink và memory visibility. Không kết luận mọi invokedynamic nhanh hơn `invokevirtual` hoặc reflection: hiệu năng tùy call-site stability, inlining, adapter chain, JIT và workload. Nên benchmark với JMH khi thực sự cần.

## 11. Checklist khi tự viết bootstrap method hoặc dispatcher

- **Descriptor lấy ở đâu?** Với bootstrap, dùng tham số `MethodType type` JVM đưa vào; đừng tự đoán từ method implementation.
- **BSM có trả CallSite không?** Kết quả phải là non-null `CallSite`, không phải chỉ `MethodHandle`.
- **Target đã thích nghi chưa?** Kiểm tra `target.type().equals(type)` trước khi trả site; với mutable site còn cần giữ invariant sau mỗi update.
- **Dùng đúng lỗi để debug?** `BootstrapMethodError` = linkage/BSM, `WrongMethodTypeException` khi `setTarget` hoặc `invokeExact` = mismatch trong API, `UnsupportedOperationException` = relink constant site.
- **Có phân biệt snapshot và live invoker?** `getTarget()` lấy handle tại thời điểm đọc; `dynamicInvoker()` theo site hiện tại.
- **Có xử lý multi-thread chưa?** `MutableCallSite.syncAll(...)` hoặc `VolatileCallSite` tùy hợp đồng visibility.
- **Đã kiểm tra bytecode thật chưa?** Dùng `javap -c -v -p` và tìm đúng descriptor của instruction `invokedynamic`, không nhầm với SAM hoặc implementation.
- **Đã phân biệt Java source test và JVM bootstrap test chưa?** Test `CallSite` độc lập rất hữu ích nhưng không thay thế việc chạy instruction `invokedynamic` với bootstrap thật trong class file.
- **Đã kiểm tra overload/type erasure chưa?** Primitive/reference, return type và type loader đều là thành phần của `MethodType.equals`.
- **Đã test lỗi có chủ đích chưa?** Mismatch khi `setTarget`, adapter không hợp lệ, uninitialized MutableCallSite, và bootstrap kết quả sai trong môi trường có bytecode test phù hợp.

## 12. Câu hỏi tự kiểm tra

**1.** Instruction có descriptor `(String)String`. Bootstrap trả `ConstantCallSite` có target `(Object)Object`; cả hai tham chiếu đều hợp lý. Linkage có thành công không?

**Đáp án:** Không. JVM đòi **MethodType bằng nhau**, không chỉ các kiểu có thể cast. Bootstrap phải tạo adapter target đúng `(String)String` trước khi trả site.

**2.** Để trả CallSite, bootstrap có bắt buộc có return type `MethodHandle` không?

**Đáp án:** Không. Bootstrap trả `CallSite`; target nằm bên trong CallSite. Chữ ký bootstrap không phải descriptor của instruction.

**3.** `CallSite.type()` có đổi theo target mới khi `MutableCallSite.setTarget(...)` không?

**Đáp án:** Không. Kiểu của site cố định. `setTarget` chỉ chấp nhận handle mới có `MethodType` bằng đúng type cũ.

**4.** Giữ `old=site.getTarget()` và `dispatcher=site.dynamicInvoker()` trước khi đổi target. Hai handle có luôn gọi body mới sau cập nhật không?

**Đáp án:** Không. `old` vẫn trỏ trực tiếp đến target cũ. `dispatcher` gọi qua site và theo target mới với visibility thích hợp.

**5.** Trả CallSite sai descriptor từ bootstrap của invokedynamic và gọi `site.setTarget(wrongHandle)` là cùng một loại lỗi?

**Đáp án:** Không. Lỗi bootstrap sai descriptor là `BootstrapMethodError`; `setTarget` sai type trên mutable/volatile site là `WrongMethodTypeException`.

**6.** Vì sao `new ConstantCallSite(wrongHandle)` trong Java code có thể thành công dù `wrongHandle.type()` không bằng một descriptor mà bạn đang nghĩ tới?

**Đáp án:** Constructor chỉ gắn type của chính target làm type của site; nó **không liên kết** với instruction nào. JVM chỉ phát hiện descriptor mismatch khi liên kết nó với một instruction thật.

**7.** Nếu có `String::trim`, descriptor của instruction `invokedynamic` tạo lambda có nhất thiết là `(String)String`?

**Đáp án:** Không. Với Java 17, invokedynamic cho method reference này thường là factory trả `UnaryOperator`, ví dụ `()UnaryOperator`. Việc gọi `apply` là bước khác.

**8.** Hai thread đồng thời gặp cùng instruction chưa liên kết, bootstrap có chắc chỉ chạy đúng một lần không?

**Đáp án:** Không nhất thiết. JVM có thể thực hiện các bootstrap invocation cạnh tranh rồi chọn một kết quả; sau khi instruction liên kết, những lần gọi sau không bootstrap lại vì mỗi lần invoke.

**9.** Khi dùng `VolatileCallSite`, có cần gọi `MutableCallSite.syncAll` không?

**Đáp án:** Không. VolatileCallSite dùng volatile semantics cho target; `syncAll` là API của `MutableCallSite`.

**10.** Nếu logic target bên trong ném `IllegalStateException` sau khi linkage thành công, có phải JVM bắt buộc chuyển lỗi ấy thành `BootstrapMethodError`?

**Đáp án:** Không. `BootstrapMethodError` liên quan tới việc liên kết/bootstrap. Exception của body sau linkage được truyền theo cơ chế gọi handle/target, không tự biến thành lỗi bootstrap.

## Tài liệu đối chiếu chính thức

- [Java SE 21 — `CallSite`: type invariant, target và dynamic invoker](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 21 — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/ConstantCallSite.html)
- [Java SE 21 — `MutableCallSite` và `syncAll`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Java SE 21 — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
- [Java SE 21 — `MethodType`, `MethodHandle.asType` và `invokeExact`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 21 — `java.lang.invoke` package: dynamic call site linkage](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/package-summary.html)
- [JVMS SE 21 — `5.4.3.6 Dynamically-Computed Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS SE 21 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokedynamic)
