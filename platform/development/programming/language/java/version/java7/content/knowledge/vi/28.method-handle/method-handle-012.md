# MethodHandle: kiểm chứng kiểu gọi, lỗi liên kết và chi phí làm nóng

## 1. Vì sao phải kiểm chứng trước khi tối ưu?

**MethodHandle** đại diện cho một thao tác có thể gọi được và gắn với một **MethodType** xác định kiểu trả về cùng danh sách kiểu tham số có thứ tự. Khi dùng nó để điều phối lời gọi động, một lỗi nhỏ ở **chữ ký lúc gọi** có thể chỉ xuất hiện tại runtime, dù mã Java biên dịch thành công. Ngoài tính đúng đắn, lần chạy đầu của một tuyến gọi còn có thể chịu chi phí **tra cứu, liên kết, khởi tạo lớp và tối ưu JIT**. Những chi phí này không nên bị nhầm với tốc độ của một lời gọi đã hoạt động ổn định.

Bài này tập trung vào ba việc liên quan trực tiếp:

1. **Kiểm chứng kiểu gọi**: biết chính xác **handle.type()**, kiểu đối số và đặc biệt là kiểu kết quả mà **call site** yêu cầu; phân biệt **invokeExact**, **invoke**, **asType** và **invokeWithArguments**.
2. **Phân loại lỗi theo giai đoạn**: lỗi lúc **Lookup** tìm thành viên, lỗi **WrongMethodTypeException** khi gọi, lỗi do conversion/method đích và lỗi **LinkageError/BootstrapMethodError** trong liên kết bytecode hay **invokedynamic**. Chúng không phải cùng một nhóm.
3. **Hiểu chi phí làm nóng**: đo đúng đường xử lý đã hoặc chưa khởi tạo, tránh benchmark sai vì JIT, dead-code elimination, cấp phát, chuyển đổi kiểu và dữ liệu không đại diện.

Các API ở đây là **java.lang.invoke** hiện hành của JDK 17+; những ví dụ chạy được dùng thư viện chuẩn, không cần thư viện bên ngoài. Benchmark chuyên nghiệp được trình bày riêng bằng **JMH**.

## 2. MethodType và call site là hợp đồng chính xác

Ví dụ một phương thức:

~~~java
private static int add(int a, int b) {
    return a + b;
}
~~~

Nếu tạo handle qua:

~~~java
MethodType type = MethodType.methodType(
        int.class, int.class, int.class);
MethodHandle addHandle = MethodHandles.lookup().findStatic(
        Example.class, "add", type);
~~~

đối tượng handle dự kiến có kiểu:

~~~text
(int,int)int
~~~

Đây là **các đoạn minh họa**, cần một lớp **Example** khai báo đúng phương thức **add**, import **MethodHandle/MethodHandles/MethodType** và phương thức gọi xử lý ngoại lệ tra cứu. Đối số đầu tiên của **MethodType.methodType(...)** là **kiểu kết quả**; các đối số tiếp theo mới là **kiểu tham số**.

Điều kiện kiểm chứng đơn giản:

~~~java
MethodType expected = MethodType.methodType(
        int.class, int.class, int.class);
if (!addHandle.type().equals(expected)) {
    throw new IllegalStateException(
            "Unexpected handle type: " + addHandle.type());
}
~~~

**handle.type()** nói chính xác dạng mà handle đó cần. Một **MethodHandle** có thể được tạo từ phương thức static, instance, constructor, field getter/setter hoặc một adapter; không nên đoán chữ ký chỉ từ tên method hay kiểu khai báo ban đầu.

| Loại handle | Ví dụ phương thức/field | Kiểu handle thực tế thường thấy |
| --- | --- | --- |
| Static method | **int add(int,int)** | **(int,int)int** |
| Instance method | **String.substring(int,int)** từ **findVirtual** | **(String,int,int)String**, có receiver đầu tiên |
| Getter instance | field **int count** của Counter | **(Counter)int** |
| Setter instance | field **int count** của Counter | **(Counter,int)void** |
| Getter static | field **static String mode** | **()String** |
| Constructor | **new StringBuilder(String)** | **(String)StringBuilder** |
| Handle đã **bindTo(receiver)** | instance handle được gắn receiver | Bỏ receiver khỏi các tham số còn lại |
| Handle đã **asType(...)** | adapter boxing/unboxing | Kiểu do **asType** yêu cầu nếu conversion được phép |

**MethodType** không chứa tên phương thức, tên tham số, chú thích hay ngoại lệ checked. Nó chỉ biểu diễn **kiểu kết quả + kiểu tham số**. Các class cùng tên nhưng do class loader khác nhau nạp có thể không phải cùng một **Class**, vì vậy chữ ký nhìn bằng chữ có vẻ giống nhau chưa chắc tương thích trong hệ thống nhiều class loader.

### invokeExact kiểm tra cả kiểu trả về

Hai lời gọi sau có ý nghĩa khác nhau dù đối số giống nhau:

~~~java
int good = (int) addHandle.invokeExact(4, 5);

// Lời gọi dưới đây biên dịch được nhưng sai chữ ký:
// long wrong = (long) addHandle.invokeExact(4, 5);
~~~

Đây là ví dụ minh họa trong phương thức có **throws Throwable**. Với **invokeExact**, JVM lấy **chữ ký từ kiểu tĩnh của các đối số và kiểu kết quả tại call site**. **(int,int)int** khớp handle; **(int,int)long** không khớp và ném **WrongMethodTypeException**. Việc **int** có thể được Java chuyển thành **long** trong phép gán thông thường **không** tự động thích nghi lời gọi **invokeExact**.

Điểm dễ bỏ sót: viết một lệnh chỉ gọi **addHandle.invokeExact(4,5);** mà không dùng kết quả sẽ tạo call site yêu cầu kết quả **void**, cũng không khớp handle trả int. Với một biểu thức **invokeExact** không có cast và dùng kết quả dưới dạng Object, kiểu trả của call site có thể là Object. Hãy đặt cast rõ ràng, ví dụ **(int) addHandle.invokeExact(...)**, rồi kiểm tra **handle.type()**.

**Primitive khác wrapper**: **int.class** khác **Integer.class**; **(int,int)int** khác **(Integer,Integer)Integer**. **invokeExact** không tự boxing/unboxing, không tự mở rộng primitive và không tự ép subtype/supertype.

## 3. invoke, asType và invokeWithArguments có vai trò khác nhau

| API | Ràng buộc | Conversion | Sử dụng thích hợp |
| --- | --- | --- | --- |
| **invokeExact(...)** | Call-site MethodType phải bằng **handle.type()** | Không chuyển kiểu tham số/kết quả | Đường gọi có chữ ký đã biết, cần kiểm chứng exact |
| **invoke(...)** | Call-site có thể khác nếu tương thích với **asType(...)** | Adaptation được API cho phép | Cần linh hoạt kiểu trong một arity phù hợp |
| **asType(newType)** | Tạo một **adapter handle** với kiểu mong muốn | Có thể boxing, unboxing, widening/casting theo quy tắc | Chuẩn hóa chữ ký một lần rồi dùng handle mới |
| **invokeWithArguments(...)** | Nhận danh sách Object/array/list ở runtime | Chuyển đổi và đóng gói theo lời gọi generic | Cầu nối API động, xử lý đối số chưa biết tĩnh; cân nhắc overhead |

Ví dụ **int → long** ở kiểu kết quả:

~~~java
// addHandle.type() = (int,int)int
long wider = (long) addHandle.invoke(4, 5); // Hợp lệ: trả 9L.
~~~

**invoke** có thể thích nghi kiểu trả từ int sang long. Điều đó **không** có nghĩa bất kỳ kiểu nào cũng chuyển được: một số conversion bị từ chối ngay khi lập adapter, hoặc thất bại khi runtime cast/unbox.

Ví dụ boxing/unboxing tường minh:

~~~java
MethodType boxedType = MethodType.methodType(
        Integer.class, Integer.class, Integer.class);
MethodHandle boxed = addHandle.asType(boxedType);

// boxed.type(): (Integer,Integer)Integer
Integer result = (Integer) boxed.invokeExact(
        Integer.valueOf(3), Integer.valueOf(7));
~~~

**boxed** là adapter mới có chữ ký được yêu cầu; **addHandle** gốc vẫn là **(int,int)int**. Nếu truyền **null** cho tham số cần unbox sang int, invocation có thể gây **NullPointerException**. Nếu cố chuyển một reference không phù hợp, chẳng hạn String sang wrapper số, có thể gây **ClassCastException**.

**invokeWithArguments** giúp gọi từ một mảng/list đối số không có chữ ký tĩnh cụ thể:

~~~java
Object answer = addHandle.invokeWithArguments(4, 5);
System.out.println(answer); // 9 (Integer được boxing).
~~~

Nó tạo góc nhìn generic của các đối số, có thể thực hiện boxing/unboxing, chuyển đổi reference và xử lý mảng; không nên mặc định là lựa chọn ít overhead nhất cho đường gọi nóng. Một số lỗi về số lượng/khả năng thích nghi đối số gây **WrongMethodTypeException**, còn giá trị có kiểu không phù hợp gây **ClassCastException** hoặc **NullPointerException**, tùy quy tắc conversion. Nếu code đã biết chữ ký, ưu tiên giữ một handle được adapt trước và gọi theo kiểu cụ thể.

## 4. Phân biệt lỗi tra cứu, lỗi gọi và lỗi liên kết

“Lỗi liên kết” đôi khi bị dùng để gọi chung mọi lỗi MethodHandle. Trong Java, cần phân biệt **lỗi lookup**, **lỗi invocation** và **JVM linkage error** để không sửa nhầm vấn đề.

| Giai đoạn | Ví dụ lỗi | Ý nghĩa thường gặp |
| --- | --- | --- |
| **Lookup.findStatic/findVirtual/...** | **NoSuchMethodException**, **NoSuchFieldException** | Tên, tham số, kiểu kết quả hoặc field type không khớp thành viên |
| **Lookup / quyền truy cập** | **IllegalAccessException** | Thành viên tồn tại nhưng lookup không đủ quyền; có thể liên quan package/module |
| **invokeExact** | **WrongMethodTypeException** | Kiểu gọi không bằng **handle.type()**, có thể lệch cả return type |
| **invoke / asType** | **WrongMethodTypeException** | Không thể thích nghi kiểu call site với handle |
| **Conversion khi gọi** | **ClassCastException**, **NullPointerException** | Reference cast không hợp lệ hoặc unboxing null |
| **Thực thi method đích** | Bất kỳ ngoại lệ của method, ví dụ **ArithmeticException** | Lỗi nghiệp vụ/runtime của target được chuyển tiếp |
| **Liên kết bytecode của JVM** | **NoSuchMethodError**, **IllegalAccessError**, **IncompatibleClassChangeError** | Thường do binary/classpath/module ABI không tương thích hoặc quy tắc linkage của JVM |
| **invokedynamic / dynamic constant** | **BootstrapMethodError** | Bootstrap không resolve được, ném lỗi hoặc cung cấp call-site/constant sai hợp đồng |

**NoSuchMethodException** là **checked exception** khi thư viện đang *cố tìm* một phương thức bằng API Lookup. **NoSuchMethodError** là **LinkageError** ở phía liên kết bytecode, chẳng hạn mã đã biên dịch tham chiếu một method nhưng runtime nạp phiên bản class không còn method tương thích. Hai tên gần giống nhưng khác giai đoạn và cách xử lý.

**WrongMethodTypeException** là **RuntimeException**, không phải lớp con của **LinkageError**. Với **MethodHandle.invokeExact**, bytecode của invoker signature-polymorphic có cơ chế liên kết riêng: nếu cú pháp descriptor hợp lệ và các lớp được resolve, việc **một handle cụ thể không khớp kiểu call site** thường thể hiện bằng **WrongMethodTypeException tại lúc gọi**. Không quy mọi WrongMethodTypeException thành **BootstrapMethodError**.

### Lookup.findStatic sai và quyền truy cập sai

~~~java
MethodType type = MethodType.methodType(
        int.class, int.class, int.class);

// Không có member tên "notThere" với chữ ký đã yêu cầu:
lookup.findStatic(Example.class, "notThere", type);
// NoSuchMethodException

// Có member private nhưng publicLookup không được phép:
MethodHandles.publicLookup().findStatic(
        Example.class, "secret", MethodType.methodType(int.class, int.class));
// IllegalAccessException
~~~

Đoạn trên minh họa trường hợp lớp **Example** không có **notThere(int,int)** và có **private static int secret(int)**. Cần xử lý các checked exception tại lookup. Nếu dùng sai **Class** hoặc một method cùng tên nhưng khác return type, kết quả tra cứu cũng có thể không tìm được.

### Lỗi tại call site

~~~java
// addHandle.type() == (int,int)int
long wrong = (long) addHandle.invokeExact(4, 5);
// WrongMethodTypeException vì call site đòi (int,int)long.
~~~

Các đoạn lỗi này không chạy trực tiếp trong luồng bình thường nếu chưa có catch. Chương trình hoàn chỉnh ở phần 6 bắt các lỗi có chủ đích và in kết quả.

### Lỗi từ method đích

~~~java
MethodHandle division = lookup.findStatic(
        Example.class,
        "divide",
        MethodType.methodType(int.class, int.class, int.class));

int value = (int) division.invokeExact(6, 0);
// ArithmeticException nếu Example.divide(int,int) thực hiện a / b.
~~~

Lỗi này xảy ra **sau khi** handle và call site đã khớp. **invokeExact/invoke** không tự chuyển ArithmeticException thành WrongMethodTypeException; ngoại lệ từ target có thể truyền qua trực tiếp. Phân loại đúng giúp truy ra vấn đề dữ liệu thay vì cố thay đổi MethodType.

## 5. invokeDynamic, CallSite và BootstrapMethodError

**MethodHandle** là một API lời gọi động; **invokedynamic** là một **bytecode instruction** dùng bootstrap để liên kết một call site khi nó được thực thi lần đầu. Hai khái niệm liên quan nhưng không đồng nhất.

Một luồng đơn giản của **invokedynamic**:

~~~text
invokedynamic trong bytecode
    ↓ liên kết ở lần sử dụng đầu tiên
bootstrap method nhận Lookup + tên + MethodType + bootstrap arguments
    ↓ tạo CallSite hợp lệ
CallSite có target MethodHandle với MethodType đúng descriptor
    ↓
những lần thực thi tiếp theo gọi target theo liên kết đã thiết lập
~~~

Nếu bootstrap không thể được resolve, ném lỗi, hoặc cung cấp **CallSite có target sai MethodType**, JVM có thể báo **BootstrapMethodError**. Với dynamic constant, lỗi bootstrap hoặc giá trị không đúng type cũng có thể dẫn tới lỗi này. Điều đó khác với việc lập trình viên gọi **lookup.findStatic(...)** và nhận **NoSuchMethodException** hoặc gọi **handle.invokeExact(...)** rồi nhận **WrongMethodTypeException**.

Các tính năng JVM/compiler như lambda linkage và một số thao tác string concatenation có thể dùng **invokedynamic**. Việc lập trình ứng dụng bằng **MethodHandles.Lookup** không tự động sinh một invokedynamic mới tại mỗi lần gọi.

### MutableCallSite cần target có đúng type

**MutableCallSite** lưu một target MethodHandle; **dynamicInvoker()** trả handle để gọi target hiện tại. Target mới phải có **MethodType bằng chính xác type của CallSite**:

~~~java
MutableCallSite site = new MutableCallSite(addHandle);
MethodHandle invoker = site.dynamicInvoker();
int total = (int) invoker.invokeExact(2, 8); // 10

site.setTarget(MethodHandles.constant(String.class, "oops"));
// WrongMethodTypeException: handle ()String không khớp (int,int)int.
~~~

Đoạn này giả định **addHandle** có kiểu **(int,int)int**. Cần import **MutableCallSite**, **MethodHandles** và kiểm tra exception. **Đây chỉ là minh họa API CallSite từ Java**, không phải ví dụ tự phát ra bytecode invokedynamic hay một bootstrap lỗi. Vì thế, **setTarget** sai type ở đây là **WrongMethodTypeException**, không phải **BootstrapMethodError**.

Nếu CallSite mutable có target thay đổi giữa các thread, phải hiểu mô hình visibility của **MutableCallSite.syncAll(...)**, hoặc chọn **VolatileCallSite** khi cần ngữ nghĩa đồng bộ phù hợp. Chỉ gọi **setTarget(...)** không có nghĩa mọi thread sẽ nhìn thấy thay đổi tại cùng thời điểm tức thì.

### Các bước chẩn đoán lỗi liên kết thật

1. Xác định đang ở **lookup**, **invocation**, **bytecode linkage** hay **bootstrap**.
2. Với **NoSuchMethodException**, in **Class**, member name, **MethodType**, access modifiers; xác minh signature thực và class loader.
3. Với **IllegalAccessException**, kiểm tra ngữ cảnh Lookup, quyền truy cập của member và **exports/opens** của JPMS.
4. Với **WrongMethodTypeException**, so **handle.type()** với descriptor được gọi, đặc biệt là **return type**, primitive/wrapper và receiver.
5. Với **NoSuchMethodError/IllegalAccessError**, kiểm tra phiên bản JAR/class nạp tại runtime, binary compatibility và module path/classpath.
6. Với **BootstrapMethodError**, xem **cause**, stack trace, chữ ký bootstrap và kiểu target **CallSite** đã trả. Không chỉ catch rồi bỏ qua; thường cần sửa logic liên kết hoặc dependency.
7. Nếu method đích ném lỗi, debug bên trong method hoặc dữ liệu đầu vào như lời gọi thường.

Một ứng dụng production không nên dùng **catch (LinkageError)** như cơ chế fallback thường ngày để tiếp tục vận hành một classpath hỏng. Phải khắc phục đúng nguyên nhân binary hoặc bootstrap.

## 6. Chương trình Java 17+ chạy được: kiểm chứng và phân loại lỗi

Chương trình sau dùng **JDK thuần**, có đường gọi exact/inexact/adapter, lỗi lookup, lỗi quyền truy cập, conversion lỗi, ngoại lệ từ target và **MutableCallSite**. Nó còn chạy một vòng lặp để làm ấm một đường gọi; phần này **không được coi là benchmark hiệu năng**.

Lưu tệp **MethodHandleCallSiteDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleCallSiteDemo {
    private static int add(int a, int b) {
        return a + b;
    }

    private static int divide(int a, int b) {
        return a / b;
    }

    private static int secret(int x) {
        return x * 2;
    }

    private static long loop(MethodHandle handle, int count)
            throws Throwable {
        long checksum = 0;
        for (int i = 0; i < count; i++) {
            checksum += (int) handle.invokeExact(i & 7, 1);
        }
        return checksum;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(
                int.class, int.class, int.class);
        MethodHandle add = lookup.findStatic(
                MethodHandleCallSiteDemo.class, "add", signature);

        System.out.println("type=" + add.type());
        System.out.println("exact=" + (int) add.invokeExact(4, 5));
        System.out.println("widened=" + (long) add.invoke(4, 5));

        MethodHandle boxed = add.asType(MethodType.methodType(
                Integer.class, Integer.class, Integer.class));
        System.out.println("adaptedType=" + boxed.type());
        Integer boxedValue = (Integer) boxed.invokeExact(
                Integer.valueOf(3), Integer.valueOf(7));
        System.out.println("boxed=" + boxedValue);

        try {
            long wrong = (long) add.invokeExact(4, 5);
            System.out.println(wrong);
        } catch (WrongMethodTypeException expected) {
            System.out.println(
                    "exactMismatch=WrongMethodTypeException");
        }

        try {
            lookup.findStatic(
                    MethodHandleCallSiteDemo.class,
                    "missing", signature);
        } catch (NoSuchMethodException expected) {
            System.out.println(
                    "missingMember=NoSuchMethodException");
        }

        try {
            MethodHandles.publicLookup().findStatic(
                    MethodHandleCallSiteDemo.class, "secret",
                    MethodType.methodType(int.class, int.class));
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "accessDenied=IllegalAccessException");
        }

        try {
            Object ignored = add.invokeWithArguments("not an int", 5);
            System.out.println(ignored);
        } catch (ClassCastException expected) {
            System.out.println(
                    "badArgument=ClassCastException");
        }

        MethodHandle division = lookup.findStatic(
                MethodHandleCallSiteDemo.class, "divide", signature);
        try {
            int value = (int) division.invokeExact(6, 0);
            System.out.println(value);
        } catch (ArithmeticException expected) {
            System.out.println(
                    "targetFailure=ArithmeticException");
        }

        MutableCallSite callSite = new MutableCallSite(add);
        MethodHandle dynamic = callSite.dynamicInvoker();
        System.out.println("callSiteType=" + dynamic.type());
        System.out.println("callSiteResult="
                + (int) dynamic.invokeExact(2, 8));

        try {
            callSite.setTarget(
                    MethodHandles.constant(String.class, "bad"));
        } catch (WrongMethodTypeException expected) {
            System.out.println(
                    "targetTypeMismatch=WrongMethodTypeException");
        }

        long warmup = 0;
        for (int k = 0; k < 5; k++) {
            warmup = loop(add, 10_000);
        }
        System.out.println("warmupChecksum=" + warmup);
        System.out.println("runChecksum=" + loop(add, 100_000));
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac MethodHandleCallSiteDemo.java
java MethodHandleCallSiteDemo
~~~

**Stdout xác định của ví dụ:**

~~~text
type=(int,int)int
exact=9
widened=9
adaptedType=(Integer,Integer)Integer
boxed=10
exactMismatch=WrongMethodTypeException
missingMember=NoSuchMethodException
accessDenied=IllegalAccessException
badArgument=ClassCastException
targetFailure=ArithmeticException
callSiteType=(int,int)int
callSiteResult=10
targetTypeMismatch=WrongMethodTypeException
warmupChecksum=45000
runChecksum=450000
~~~

Những kết quả trên đã được kiểm tra bằng **JShell trên JDK 24** với cùng thân chương trình. Các API được dùng đều có trong JDK 17.

**Giải thích quan trọng:**

- **exact=9** đến từ chữ ký **(int,int)int**, còn **widened=9** cho thấy **invoke** chấp nhận thích nghi return **int → long**.
- **boxed=10** thể hiện adapter **(Integer,Integer)Integer** đã được tạo một lần bằng **asType**.
- **exactMismatch** là lỗi kiểu tại call site, không phải lỗi lookup và cũng không phải BootstrapMethodError.
- **missingMember/accessDenied** xảy ra khi tạo handle, trước khi gọi method đích.
- **badArgument** phát sinh do String không phù hợp với chuyển đổi tới primitive int.
- **targetFailure** chứng minh handle đã liên kết đúng vẫn có thể truyền ra ngoại lệ của method đích.
- **targetTypeMismatch** xảy ra khi gán target có MethodType khác cho MutableCallSite.
- **warmupChecksum** và **runChecksum** là giá trị cộng dồn kiểm chứng đường gọi đã chạy; **chúng không đo tốc độ**, không chứng minh JIT đã compile và không chỉ ra handle nhanh hơn hay chậm hơn.

## 7. Chi phí làm nóng: những khoản nào xảy ra trước khi chạy ổn định?

“Làm nóng” (*warm-up*) là quá trình một JVM đang chạy thu thập thông tin thực thi và có thể tối ưu những tuyến code hay dùng. **Không có số lần gọi cố định** bảo đảm một MethodHandle đã tối ưu xong trên mọi JDK, JVM flag, kiến trúc CPU hoặc workload.

Có thể tách ra một số khoản chi phí:

| Công đoạn | Thời điểm và tác động |
| --- | --- |
| **Nạp/xác minh/khởi tạo lớp** | Có thể xảy ra khi lần đầu dùng các lớp liên quan; không phải mỗi invocation đều phải làm lại |
| **Lookup và tạo MethodHandle** | Tìm member, kiểm tra quyền, tạo handle; cache nếu chữ ký và quyền truy cập đã ổn định |
| **Tạo adapter** | **asType**, **bindTo**, combinators có thể tạo tuyến handle khác; tránh dựng lại trong vòng lặp nóng |
| **Liên kết call site** | Call-site signature-polymorphic có resolution tương ứng; **invokedynamic** dùng bootstrap khi call site được liên kết lần đầu |
| **Thông dịch và profiling** | JVM quan sát hành vi thực tế; nóng đến mức nào tùy workload/JVM |
| **JIT compilation / inlining** | JVM có thể biên dịch và tối ưu đường gọi; mức tối ưu phụ thuộc độ ổn định của call site và logic |
| **GC, allocation, cache CPU, contention** | Có thể gây dao động thời gian đo, kể cả khi MethodHandle đã sẵn sàng |

**Lookup một lần rồi dùng nhiều lần** thường là lựa chọn hợp lý nếu method/field và quyền truy cập không thay đổi. Ví dụ:

~~~java
private static final MethodHandle ADD = findAdd();

private static MethodHandle findAdd() {
    try {
        return MethodHandles.lookup().findStatic(
                Example.class, "add",
                MethodType.methodType(
                        int.class, int.class, int.class));
    } catch (NoSuchMethodException | IllegalAccessException e) {
        throw new ExceptionInInitializerError(e);
    }
}
~~~

Đây là **mẫu thiết kế minh họa**, yêu cầu lớp **Example** có static method **add(int,int)** và các import; không phải chương trình độc lập. Không cần tạo **MethodHandles.lookup().findStatic(...)** liên tục trong mỗi iteration để đo chi phí **invokeExact**. Ngược lại, nếu cần đo *chi phí lookup*, phải làm đúng thao tác lookup trong benchmark riêng và đặt tên kết quả cho rõ.

### Tại sao lần gọi đầu chậm hơn không chứng minh MethodHandle chậm?

Lần đầu có thể gồm nhiều công việc mà steady-state invocation không còn phải làm. Một vòng lặp dùng **System.nanoTime()** quanh một invocation ngắn cũng có thể đo chủ yếu **clock overhead, scheduling và biên dịch JIT**. Đếm số vòng cố định như 1.000 hay 10.000 rồi khẳng định “warm-up đủ” là suy diễn không đáng tin.

Điều quan trọng là xác định chính xác **câu hỏi đo**:

1. **Cold-start latency**: độ trễ khi code hoặc call site mới được dùng lần đầu (bao gồm class init, lookup, bootstrap khi có).
2. **Steady-state throughput/latency**: độ trễ sau khi JVM đã có cơ hội profile/tối ưu đường gọi ổn định.
3. **Chi phí adapter/boxing**: chênh lệch giữa exact signature, adapted handle và đường generic với cùng công việc thực tế.
4. **Chi phí liên kết động**: bootstrap và khởi tạo call site; không gộp vào phép đo invocation đều đặn nếu mục tiêu là invoke throughput.

Một phép đo chỉ có ý nghĩa khi diễn giải đúng **khoản chi phí nó bao gồm**.

## 8. Đo vi mô với JMH: tách cấu hình, warm-up và measurement

**JMH (Java Microbenchmark Harness)** là công cụ OpenJDK được duy trì để đo hiệu năng JVM ở mức microbenchmark. Nó hỗ trợ **warm-up iterations, measurement iterations, forks**, các đơn vị đo và các cơ chế hạn chế benchmark bị JVM tối ưu mất. JMH là thư viện bên ngoài JDK; phần này dành cho dự án JMH đã được cấu hình bằng công cụ tạo project/hướng dẫn chính thức.

Ví dụ **MethodHandleBench.java** trong một **project JMH**, không thể chạy độc lập chỉ với **javac**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class MethodHandleBench {
    private MethodHandle add;
    private int left = 17;
    private int right = 23;

    public static int sum(int a, int b) {
        return a + b;
    }

    @Setup(Level.Trial)
    public void setup() throws ReflectiveOperationException {
        add = MethodHandles.lookup().findStatic(
                MethodHandleBench.class, "sum",
                MethodType.methodType(
                        int.class, int.class, int.class));
    }

    @Benchmark
    public int direct() {
        return sum(left, right);
    }

    @Benchmark
    public int handleExact() throws Throwable {
        return (int) add.invokeExact(left, right);
    }
}
~~~

**Cách sử dụng đúng:** Tạo project bằng archetype JMH theo tài liệu **https://github.com/openjdk/jmh/**, đưa class trên vào source benchmark, build và chạy qua runner JMH. Runner tự thực hiện warm-up, measurement và fork theo annotation hoặc cấu hình CLI. Không có **stdout hay tỷ lệ nhanh/chậm cố định** cho ví dụ này: kết quả phụ thuộc JVM, CPU, mức tối ưu, trạng thái tải và cấu hình benchmark.

- **@Setup(Level.Trial)** lấy MethodHandle trước khi đo, giúp so sánh **chi phí gọi**. Nếu muốn đo lookup, tạo benchmark khác với setup tương ứng; không trộn hai mục tiêu.
- **@State(Scope.Thread)** giữ dữ liệu đầu vào của từng worker; benchmark trả **int** để kết quả được JMH quan sát.
- **@Warmup**, **@Measurement** và **@Fork** kiểm soát các pha đo và chạy các JVM fork độc lập.
- Hai benchmark phải thực hiện cùng phép tính; đo những path có semantic khác nhau không cho phép kết luận chính xác.
- Mẫu quá đơn giản như **sum(left,right)** có thể bị JVM tối ưu mạnh. Hãy thử cả dữ liệu biến thiên và workload đại diện, tránh kết luận tổng quát từ một phép cộng hằng.
- Khi dùng **Blackhole** cho kết quả phức tạp, chỉ dùng đúng API của JMH; không tự giả định một phép in ra console trong vòng lặp là cách chống tối ưu hợp lý.

### Những sai lầm phổ biến khi benchmark MethodHandle

| Cách làm sai | Vì sao sai lệch | Cách khắc phục |
| --- | --- | --- |
| So một lần gọi đầu của handle với method direct đã nóng | Bao gồm lookup/class init/JIT khác nhau | Phân biệt cold start và steady state |
| Tạo MethodHandle trong mỗi iteration dù mục tiêu là invocation | Đo cả lookup/allocation | Tạo handle trong setup |
| Liên tục gọi **asType(...)** trong benchmark invocation | Đo adapter creation lẫn invocation | Tạo adapter trước khi đo |
| Dùng **invokeWithArguments** thay **invokeExact** rồi kết luận mọi MethodHandle chậm | Đo cả generic adaptation/boxing/array | So nhiều kiểu API theo mục đích |
| Bỏ qua kết quả tính toán | JIT có thể loại bỏ code | Trả kết quả hoặc dùng Blackhole của JMH |
| In **System.out.println** trong vùng đo | I/O lấn át chi phí invocation | Chỉ in log sau khi benchmark kết thúc |
| Dùng 1 JVM/1 vòng đo rồi chốt số | JIT, scheduling, GC dao động | Nhiều warm-up/measure/forks |
| Tin rằng sau N lần gọi luôn đã JIT | Compiler/JVM quyết định tùy profile và flags | Quan sát độ ổn định và dùng công cụ phù hợp |
| Kết luận nanosecond benchmark áp dụng trực tiếp cho request ứng dụng | Chưa tính GC, I/O, concurrency, cache/DB | Đo thêm end-to-end ở tải thực |

**Kết quả hiệu năng không có tính bảo đảm theo đặc tả Java.** MethodHandle có thể được JVM tối ưu mạnh khi handle và call site ổn định; cũng có thể có overhead ở đường gọi biến thiên, generic adaptation hoặc lookup liên tục. Đừng tuyên bố một con số “nhanh hơn reflection X lần” nếu không có phép đo lặp lại trên JVM và workload cụ thể.

## 9. Kiểm thử tính đúng đắn trước khi kiểm thử tốc độ

Một **test matrix** hữu ích cho cơ chế gọi động gồm:

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Lookup đúng tên, đúng MethodType, đủ quyền | Tạo handle; **handle.type()** bằng kỳ vọng |
| MethodHandle cho instance method | Có receiver đầu ở chữ ký; gọi đúng object |
| Tra cứu sai method name/parameter/return type | **NoSuchMethodException** |
| Tra cứu thiếu quyền, module không mở hợp lệ | **IllegalAccessException** |
| **invokeExact** sai return type hoặc wrapper/primitive | **WrongMethodTypeException** |
| **invoke** với conversion được phép | Nhận kết quả đúng; không suy diễn mọi conversion đều được |
| Conversion reference không hợp lệ | **ClassCastException** tùy adapter |
| Unboxing null | **NullPointerException** |
| Method đích ném exception | Exception đó truyền ra lời gọi |
| **MutableCallSite.setTarget** sai type | **WrongMethodTypeException** |
| Bootstrap invokedynamic thất bại | **BootstrapMethodError**, xem cause |
| Nạp nhầm phiên bản class/JAR tại runtime | Có thể là **NoSuchMethodError** hoặc LinkageError khác |
| Warm-up + JMH measurement | Báo số đo thực tế, variance, fork, JVM version; không gán số kỳ vọng cứng |

Một chiến lược kiểm thử đủ thực dụng:

1. Test **member lookup** riêng: đúng lớp, name, MethodType, visibility, class loader.
2. Test **call-site signature** với cả kiểu return, primitive/wrapper, receiver và các tình huống adaptation.
3. Test **target behavior** (đầu vào, ngoại lệ, side effect) độc lập với cơ chế gọi.
4. Với bootstrap hoặc CallSite thay đổi, test **type invariants**, behavior của target mới và concurrency visibility.
5. Sau đó mới profile hoặc đo JMH với dữ liệu đại diện và kiểm tra biến thiên qua nhiều fork.

Không dùng benchmark throughput để thay thế kiểm chứng chức năng: một method chạy rất nhanh vẫn có thể gọi sai overload hoặc trả giá trị sai.

## 10. Những điểm hay nhầm trong ứng dụng Java hiện đại

### Nhầm runtime typing với compile-time typing

Dòng **(long) handle.invokeExact(...)** có thể biên dịch, nhưng **call site muốn kiểu trả long**. Điều đó khác với **(long) (int) handle.invokeExact(...)**: đoạn thứ hai buộc lời gọi trả int rồi Java mới cast giá trị int sang long **sau invocation**. Dấu ngoặc và vị trí cast có ý nghĩa thực sự đối với phương thức signature-polymorphic.

### Nhầm handle được tạo thành công với target luôn chạy được

**Lookup.findStatic** có thể thành công nhưng target vẫn có thể ném exception khi thực thi; adapter còn có thể gây lỗi conversion. Một test chỉ xác minh **findStatic không ném lỗi** là chưa kiểm tra được logic nghiệp vụ.

### Nhầm lỗi bootstrap với lỗi invokeExact

Một **BootstrapMethodError** thuộc bước liên kết **invokedynamic/dynamic constant**, còn **WrongMethodTypeException** trong **invokeExact** là lỗi kiểu call site khi thực thi MethodHandle. Chúng cần hai hướng sửa khác nhau.

### Nhầm MethodType của member và kiểu handle đã biến đổi

**findVirtual** thêm receiver; **bindTo** có thể bỏ receiver; **asType** thay kiểu nhìn từ call site; các combinator khác có thể thêm/bớt đối số. **Đọc handle.type() tại điểm gọi** luôn đáng tin hơn việc lấy lại MethodType của phương thức ban đầu từ trí nhớ.

### Nhầm tốc độ steady state với chi phí khởi động

Trong một request lạnh, một lần lookup/link/init có thể quan trọng. Trong vòng lặp nóng, overhead của invoke và khả năng JIT inline có thể quan trọng hơn. Chỉ một benchmark duy nhất không thể đại diện cho cả hai mục tiêu. Khi tối ưu, xét cả khả năng cache handle và việc không tạo adapter trong đường nóng.

## 11. Câu hỏi tự kiểm tra

1. **Handle có type (int,int)int. Đọc kết quả bằng long sau invokeExact có hợp lệ không?** Không. Call site yêu cầu **(int,int)long** và ném WrongMethodTypeException. Có thể ép kết quả int sau khi gọi exact hoặc dùng invoke/adapt hợp lệ.
2. **findStatic trả NoSuchMethodException, có nên catch BootstrapMethodError?** Không. Đó là lỗi tra cứu thành viên, cần kiểm tra tên và MethodType.
3. **Một method đích gọi bằng invokeExact ném ArithmeticException. Có nghĩa chữ ký không khớp?** Không. Đó là lỗi từ target, có thể xảy ra sau khi kiểu gọi đã hợp lệ.
4. **MutableCallSite.setTarget nhận target sai type thì lỗi gì?** Thông thường **WrongMethodTypeException** theo hợp đồng type của CallSite; không phải một lần bootstrap invokedynamic.
5. **Lần đầu gọi mất nhiều thời gian hơn lần thứ 100 có chứng minh invokeExact chậm?** Không. Có thể do class loading, lookup, linkage, JIT, cache hoặc môi trường.
6. **Để so sánh direct call và MethodHandle trong steady state nên dùng gì?** JMH với cùng công việc, chuẩn bị handle ngoài vùng đo, warm-up/measurement/fork và quan sát cả kết quả lẫn biến thiên.
7. **Có nên dùng invokeWithArguments cho tất cả lời gọi chỉ vì đơn giản?** Không. Nó phù hợp đối số động nhưng có thêm công việc chuyển đổi/generic mà một call-site exact có thể tránh.
8. **LinkageError nào có thể chỉ ra classpath không tương thích?** Ví dụ **NoSuchMethodError** hoặc **IllegalAccessError** khi bytecode/runtime ABI không khớp. Cần kiểm tra thực tế bản class/JAR đang nạp.

**Ghi nhớ:** Với MethodHandle, hãy **xác nhận handle.type() và chữ ký call site trước**, **phân loại lỗi theo đúng giai đoạn lookup → invocation → linkage/bootstrap**, rồi mới đo hiệu năng. **Warm-up không có ngưỡng cố định**; dùng JMH cho microbenchmark và luôn kiểm thử hành vi đúng trên JVM/workload thật.

**Tài liệu hiện hành để tham khảo:**

- [Java SE 25 — MethodHandle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): invokeExact, invoke, asType, WrongMethodTypeException.
- [Java SE 26 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): tìm thành viên, quyền truy cập và các checked exception.
- [Java SE 21 — java.lang.invoke package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/package-summary.html): CallSite, bootstrap, invokedynamic và dynamic constants.
- [Java SE 17 — BootstrapMethodError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/BootstrapMethodError.html): lỗi liên kết bootstrap.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ và hướng dẫn benchmark cho JVM.
