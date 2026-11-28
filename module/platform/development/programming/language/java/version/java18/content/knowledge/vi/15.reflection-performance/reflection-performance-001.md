# JEP 416: Method, Constructor và Field được triển khai dựa trên cơ chế method handle

## Mục tiêu bài học

Trong chương **Reflection và hiệu năng** của mô-đun **Java 18**, JEP 416 (*Reimplement Core Reflection with Method Handles*) là một thay đổi quan trọng ở **bên trong JDK**. Từ Java 18, các thao tác cốt lõi của reflection đối với `Method`, `Constructor` và `Field` được triển khai dựa trên cơ chế `java.lang.invoke.MethodHandle`. Đây vẫn là nền tảng cần hiểu khi đánh giá reflection trên JDK hiện đại.

Sau bài này, bạn có thể:

- Giải thích JEP 416 thay đổi **cách triển khai** core reflection mà không làm thay đổi hợp đồng công khai của các API reflection.
- Phân biệt đối tượng metadata `Method`, `Constructor`, `Field` với `MethodHandle` dùng để biểu diễn thao tác gọi/đọc/ghi có kiểu xác định.
- Viết ví dụ đối chiếu phương thức, constructor và field giữa reflection với Method Handle API.
- Giải thích vì sao **mức độ ổn định của đối tượng reflection** có thể ảnh hưởng đến khả năng tối ưu của JIT; không suy diễn một kết quả hiệu năng cố định cho mọi ứng dụng.
- Thiết kế một phép đo đáng tin cậy khi cân nhắc dùng reflection hay Method Handle trực tiếp.

> **Giới hạn phạm vi:** Bài học dựa vào các API đang được hỗ trợ từ JDK 18 trở lên. Các đường triển khai cũ chỉ được nhắc đến để giải thích mục tiêu thiết kế của JEP; không sử dụng thủ thuật truy cập nội bộ JDK, cờ nội bộ hoặc cơ chế đã lỗi thời làm giải pháp triển khai.

## 1. JEP 416 thay đổi điều gì?

**Core reflection** là phần API trong gói `java.lang.reflect` cho phép chương trình quan sát và thao tác với thành viên của lớp khi chạy. Các điểm thường gặp:

- `Method.invoke(Object receiver, Object... args)`: gọi một phương thức.
- `Constructor.newInstance(Object... initargs)`: tạo đối tượng thông qua constructor.
- `Field.get(Object receiver)`, `Field.set(Object receiver, Object value)` và các biến thể cho kiểu nguyên thủy: đọc/ghi trường.

Trước Java 18, phần triển khai nội bộ của những thao tác này có sự kết hợp giữa các cơ chế khác nhau. JEP 416 thống nhất cách triển khai cốt lõi bằng **method handles** khi hệ thống đã qua giai đoạn khởi tạo cần thiết. Mục tiêu của JEP là làm mã triển khai của JDK dễ bảo trì hơn, giảm số cơ chế gọi phản chiếu đặc thù và tạo cơ hội cho JVM/JIT tối ưu các đường gọi.

Điều JEP 416 **không yêu cầu** lập trình viên làm:

- Không cần thay mọi lời gọi `Method.invoke` thành `MethodHandle.invokeExact` khi nâng cấp lên Java 18.
- Không phải khai báo một API `Method`, `Constructor` hoặc `Field` mới.
- Không có lời hứa rằng mọi lời gọi reflection sẽ nhanh hơn Method Handle trực tiếp hay nhanh hơn bản JDK trước đó trong mọi tình huống.
- Không mở rộng quyền truy cập vào `private` member hoặc xuyên qua ranh giới module.

JEP 416 là thay đổi cách JDK **thực hiện** core reflection. API vẫn được sử dụng như trước, và code nghiệp vụ nên dựa trên **hợp đồng API**, không dựa vào lớp triển khai bên trong.

### Sơ đồ khái niệm

~~~text
Ma ung dung
   |
   +--> java.lang.reflect.Method.invoke(...)
   +--> java.lang.reflect.Constructor.newInstance(...)
   +--> java.lang.reflect.Field.get/set(...)
                |
                v
       Core reflection trong JDK
                |
                v
        Co che Method Handle
                |
                v
         JVM / JIT / member dich

Neu ung dung dung truc tiep java.lang.invoke:
   MethodHandles.Lookup --> MethodHandle --> JVM / JIT / member dich
~~~

Sơ đồ thể hiện quan hệ **ở mức khái niệm**. Nó không khẳng định rằng mỗi lần `invoke` JDK đều tạo một `MethodHandle` mới hoặc bỏ qua toàn bộ logic kiểm tra đầu vào và ngoại lệ của reflection.

## 2. Ba nhóm thao tác được chú ý trong JEP 416

| API reflection công khai | Thao tác | Cách tiếp cận tương ứng khi dùng Method Handle API trực tiếp |
| --- | --- | --- |
| `Method.invoke(receiver, args...)` | Gọi phương thức instance hoặc static | `Lookup.findVirtual(...)`, `Lookup.findStatic(...)` hoặc cơ chế tìm handle phù hợp |
| `Constructor.newInstance(args...)` | Tạo instance bằng constructor | `Lookup.findConstructor(...)` |
| `Field.get(receiver)` / `Field.set(receiver, value)` | Đọc/ghi instance field | `Lookup.findGetter(...)` / `Lookup.findSetter(...)` |
| `Field.get(null)` / `Field.set(null, value)` | Đọc/ghi static field | `Lookup.findStaticGetter(...)` / `Lookup.findStaticSetter(...)` |

Bảng trên mô tả **các thao tác tương đương về mục đích**. Không nên suy ra JDK luôn dùng chính xác phương thức `Lookup` ở cột cuối trong mọi nhánh triển khai. Những handle do lập trình viên tự tìm phải tuân thủ quy tắc quyền truy cập, kiểu và chuyển đổi riêng của `java.lang.invoke`.

### `Method` và `MethodHandle` không phải cùng một loại đối tượng

`Method` là đối tượng reflection có metadata: tên, modifiers, kiểu tham số, kiểu trả về, annotation, lớp khai báo. Bạn có thể duyệt các phương thức bằng `getDeclaredMethods()`, chọn một `Method` theo tên và gọi `invoke(...)`.

`MethodHandle` là đối tượng thể hiện một thao tác có **method type** cụ thể. Chẳng hạn, handle của instance method `int add(int)` trong lớp `Counter` có thể mang kiểu:

~~~text
(Counter, int)int
~~~

Tham số đầu tiên của handle kiểu này là receiver, được xem như **đối số đầu tiên của handle**. Trong khi đó, `Method.invoke(receiver, 5)` dành riêng một tham số `receiver` và nhận các đối số còn lại qua `Object...`. Hai API cùng làm việc với method đích nhưng khác cú pháp và hợp đồng gọi.

## 3. Vì sao cách triển khai này liên quan đến hiệu năng?

Method handles là cơ chế gọi động đã được JVM/JIT hỗ trợ tối ưu từ lâu. Khi JDK dùng chúng làm nền tảng cho core reflection, trình biên dịch tối ưu có thêm khả năng nhận biết thao tác đích trong những trường hợp thuận lợi.

Một trường hợp đáng chú ý trong mô tả JEP 416 là **đối tượng `Method`, `Constructor` hoặc `Field` được giữ trong trường `static final`**. JIT có thể thấy tham chiếu ổn định và dễ tối ưu đường thực thi hơn khi metadata được chọn động mỗi lần.

Ví dụ:

~~~java
private static final Method CACHED_METHOD = lookupMethod();
~~~

So với việc luân phiên nhiều đối tượng `Method` trong một biến và gọi cùng một vị trí mã, đối tượng ổn định có thể tạo điều kiện thuận lợi hơn cho constant folding và inlining. Tuy nhiên, mức độ tối ưu phụ thuộc mã ứng dụng, phiên bản JDK, JIT, kiểu lời gọi và môi trường.

**Không diễn giải `static final` như một nút bật tốc độ:** cất `Method` trong field này không tự động bảo đảm JVM sẽ inline method đích hay loại bỏ mọi chi phí boxing, truy cập và điều phối. Mục tiêu là giúp mã dễ tái sử dụng metadata và tạo cơ hội tối ưu; kết quả vẫn phải đo.

### Tác động có thể khác nhau tùy kiểu thao tác

Báo cáo thiết kế ban đầu của JEP 416 đưa ra kết quả microbenchmark có trường hợp tăng tốc và có trường hợp chậm hơn, đặc biệt khi đối tượng reflection **không trở thành hằng ổn định cho JIT**. Những con số của thí nghiệm tại thời điểm phát triển JEP không phải đặc tả hiệu năng của mọi bản JDK sau này.

Khi đánh giá hôm nay, cần xem xét:

| Đặc điểm mã | Ảnh hưởng cần kiểm chứng |
| --- | --- |
| `Method`/`Constructor`/`Field` được tái sử dụng ổn định | Giảm chi phí lookup lặp; có thể thuận lợi cho tối ưu JIT |
| Đối tượng reflection đổi liên tục tại cùng điểm gọi | Đường gọi động khó chuyên biệt hóa hơn trong một số trường hợp |
| Mỗi lần gọi lại chạy `getDeclaredMethod(...)` hoặc `getDeclaredField(...)` | Chi phí tìm metadata dễ lấn át chi phí thực thi member |
| Method đích cực ngắn, gọi nhiều lần | Chi phí adapter, boxing/varargs và điều phối trở nên dễ quan sát |
| Method đích làm I/O hoặc tính toán lớn | Thời gian của công việc thực tế thường quan trọng hơn khác biệt giữa hai cách gọi |
| Đường gọi chưa được JIT làm nóng | Kết quả có thể khác rõ với đường gọi hoạt động lâu trong production |
| Method Handle được tìm và lưu lại | Giảm lookup khi gọi lại, nhưng yêu cầu quản lý method type chính xác |

**Nguyên tắc thực hành:** Tối ưu theo điểm nóng đã được đo. Hãy phân biệt chi phí *tìm member*, *chuẩn bị handle*, *gọi member* và *thực thi phần thân member*.

## 4. Ví dụ Java hoàn chỉnh: đối chiếu ba nhóm API

File sau chạy trên JDK 18 trở lên bằng thư viện chuẩn. Nó minh họa cách dùng `Method`, `Constructor`, `Field` và Method Handle tương ứng. Đây là **ví dụ kiểm tra hành vi**, không phải microbenchmark.

Tạo `Jep416Demo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class Jep416Demo {
    public static class Counter {
        public int value;

        public Counter(int initialValue) {
            this.value = initialValue;
        }

        public int plus(int delta) {
            return value + delta;
        }
    }

    // Metadata reflection duoc tra cuu mot lan, giu o static final.
    private static final Constructor<Counter> REF_CONSTRUCTOR;
    private static final Method REF_METHOD;
    private static final Field REF_FIELD;

    // Handle truc tiep cung duoc tra cuu mot lan.
    private static final MethodHandle MH_CONSTRUCTOR;
    private static final MethodHandle MH_METHOD;
    private static final MethodHandle MH_FIELD_GET;
    private static final MethodHandle MH_FIELD_SET;

    static {
        try {
            REF_CONSTRUCTOR =
                    Counter.class.getConstructor(int.class);
            REF_METHOD =
                    Counter.class.getMethod("plus", int.class);
            REF_FIELD =
                    Counter.class.getField("value");

            MethodHandles.Lookup lookup = MethodHandles.lookup();

            MH_CONSTRUCTOR = lookup.findConstructor(
                    Counter.class, MethodType.methodType(void.class, int.class));

            MH_METHOD = lookup.findVirtual(
                    Counter.class, "plus", MethodType.methodType(int.class, int.class));

            MH_FIELD_GET =
                    lookup.findGetter(Counter.class, "value", int.class);
            MH_FIELD_SET =
                    lookup.findSetter(Counter.class, "value", int.class);

        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws Throwable {
        // 1. Constructor
        Counter byReflection = REF_CONSTRUCTOR.newInstance(10);
        Counter byHandle = (Counter) MH_CONSTRUCTOR.invokeExact(20);

        // 2. Method
        Object reflectionResult = REF_METHOD.invoke(byReflection, 5);
        int handleResult = (int) MH_METHOD.invokeExact(byHandle, 5);

        System.out.println("reflection method = " + reflectionResult);
        System.out.println("handle method     = " + handleResult);

        // 3. Field
        REF_FIELD.setInt(byReflection, 30);
        int reflectionValue = REF_FIELD.getInt(byReflection);

        MH_FIELD_SET.invokeExact(byHandle, 40);
        int handleValue = (int) MH_FIELD_GET.invokeExact(byHandle);

        System.out.println("reflection field  = " + reflectionValue);
        System.out.println("handle field      = " + handleValue);
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac Jep416Demo.java
java Jep416Demo
~~~

Đầu ra dự kiến:

~~~text
reflection method = 15
handle method     = 25
reflection field  = 30
handle field      = 40
~~~

### Phân tích ví dụ

**Constructor.** `REF_CONSTRUCTOR.newInstance(10)` khởi tạo một `Counter` và trả về đối tượng kiểu `Counter` nhờ khai báo generic `Constructor<Counter>`. Với `MH_CONSTRUCTOR`, `findConstructor(...)` dùng `MethodType` có kiểu trả về `void` để *mô tả constructor*, nhưng handle nhận được khi gọi có kết quả là `Counter`. Vì vậy, biểu thức `(Counter) MH_CONSTRUCTOR.invokeExact(20)` hợp lệ.

**Method.** `REF_METHOD.invoke(byReflection, 5)` trả về `Object` và hộp giá trị `int` thành `Integer`. `MH_METHOD.invokeExact(byHandle, 5)` yêu cầu kiểu tại điểm gọi khớp chính xác `(Counter, int)int`; phép ép kết quả `(int)` trong mã Java giúp thể hiện chữ ký mong đợi tại điểm gọi.

**Field.** Reflection hỗ trợ `Field.setInt/getInt` cho trường `int`. Method Handle tương ứng có kiểu `(Counter, int)void` cho setter và `(Counter)int` cho getter. `invokeExact` không tự biến một lời gọi sai kiểu thành lời gọi hợp lệ.

**Khả năng tối ưu.** Cả metadata reflection và các MethodHandle trong ví dụ đều được tra cứu một lần và lưu trong `static final` để thuận tiện cho việc dùng lại. Chương trình chỉ gọi mỗi đường rất ít lần nên **không thể kết luận đường nào nhanh hơn** từ đầu ra hoặc thời gian chạy của ví dụ này.

## 5. Hợp đồng API reflection vẫn được giữ nguyên

JEP 416 thay đổi phần triển khai cốt lõi, nhưng lập trình viên vẫn phải tuân thủ hợp đồng của `java.lang.reflect`.

| Vấn đề | Reflection API công khai | Khi trực tiếp dùng Method Handle |
| --- | --- | --- |
| Xác định thành viên | `getMethod(...)`, `getDeclaredMethod(...)`, `getConstructor(...)`, `getField(...)` | `Lookup.findVirtual/findStatic/findConstructor/findGetter/...` và `MethodType` |
| Gọi instance method | `method.invoke(receiver, args...)` | Receiver là đối số theo kiểu handle, chẳng hạn `(Counter, int)int` |
| Gọi static method | `method.invoke(null, args...)`; receiver ở vị trí đầu bị bỏ qua | Handle static không có receiver instance trong chữ ký |
| Giá trị primitive | `Method.invoke` trả `Object`, giá trị primitive được boxing | `invokeExact` có kiểu trả về theo method type, có thể là primitive |
| Lỗi của method/constructor đích | Lỗi từ code đích được bọc trong `InvocationTargetException` theo hợp đồng gọi phản chiếu tương ứng | Lỗi của method đích thường đi thẳng ra điểm gọi handle, không tự được bọc giống reflection |
| Quyền truy cập | Phải tuân thủ access checks; có quy tắc riêng cho `trySetAccessible()`, JPMS | `Lookup` kiểm soát quyền khi tìm handle và các quy tắc liên quan; không phải đường vòng qua JPMS |
| Điều kiện thành công | Receiver đúng kiểu, đối số hợp lệ, member được phép truy cập | Method type, quyền lookup và kiểu đối số tại `invoke`/`invokeExact` phải phù hợp |

**Điểm hay bị nhầm:** việc JDK triển khai reflection bằng method handles **không biến** `Method.invoke(...)` thành API có hợp đồng giống hệt `MethodHandle.invokeExact(...)`. Reflection vẫn có lớp adapter thực thi các quy tắc riêng: kiểm tra receiver, biến đổi đối số theo hợp đồng, boxing kết quả và bọc ngoại lệ từ method đích.

### Phân biệt ngoại lệ với ví dụ ngắn

Giả sử lớp đích khai báo:

~~~java
public void fail() {
    throw new IllegalStateException("business error");
}
~~~

Nếu method được gọi qua `Method.invoke(...)`, lỗi do **phần thân** `fail()` ném sẽ xuất hiện ở bên gọi dưới dạng `InvocationTargetException`, với `getCause()` là `IllegalStateException`. Nếu gọi cùng phương thức bằng handle trực tiếp phù hợp, lời gọi không tự áp dụng lớp bọc `InvocationTargetException` của reflection.

Vì vậy, khi thay reflection bằng Method Handle trong mã ứng dụng, bạn cần xem lại **chữ ký kiểu, chuyển đổi tham số và chiến lược xử lý ngoại lệ**. Cải thiện hiệu năng giả định không đủ để coi hai đường gọi hoán đổi được cho nhau.

## 6. Hiểu đúng `invoke` và `invokeExact`

Method Handle API có hai cách gọi thường gặp:

- `invokeExact(...)` đòi hỏi **kiểu tại điểm gọi** khớp chính xác method type của handle; sai có thể dẫn đến `WrongMethodTypeException`.
- `invoke(...)` cho phép một số chuyển đổi kiểu theo cơ chế method handle, nhưng vẫn chịu quy tắc method type và có thể lỗi khi không thể chuyển đổi.

Ví dụ, với handle lấy từ `findVirtual(Counter.class, "plus", methodType(int.class, int.class))`:

~~~java
Counter counter = new Counter(10);

// Dung: (Counter, int)int
int a = (int) MH_METHOD.invokeExact(counter, 5);

// De gay loi: kieu ket qua tai diem goi bi yeu cau la Object.
// Object b = MH_METHOD.invokeExact(counter, 5);

// Co the thich nghi mot so kieu qua invoke (khac invokeExact).
Object c = MH_METHOD.invoke(counter, 5);
~~~

Đoạn ví dụ nằm trong ngữ cảnh lớp `Jep416Demo` ở mục 4, nơi `MH_METHOD` đã được khai báo. `invokeExact` là lời gọi *signature polymorphic*; ngay cả kiểu kết quả mà compiler nhìn thấy cũng phải tương thích chính xác.

Trong khi đó, `Method.invoke` được khai báo trả `Object`, nên bạn thường cần ép kiểu hoặc unbox kết quả sau đó. Chênh lệch cú pháp cũng có thể tạo ra chi phí khác nhau, nhưng **không suy ra được tốc độ** chỉ bằng cách đọc chữ ký.

### Varargs và quá trình đóng hộp

`Method.invoke(Object, Object...)` tự nó là phương thức varargs. Nếu method đích có tham số mảng, bạn phải truyền **mảng như một đối số** đúng cách; không thể mặc định `Method.invoke` tự đóng gói varargs cho chữ ký method đích. Với Method Handle, kiểu mảng, kiểu thành phần và tính năng varargs collector cũng phải được xử lý theo API `java.lang.invoke` tương ứng.

Khi benchmark, nếu một đường gọi liên tục tạo mảng `Object[]` hoặc boxing còn đường kia sử dụng primitive trực tiếp, kết quả là đo **cả chi phí adapter và cấp phát**, không đơn thuần đo nội bộ JEP 416.

## 7. JIT và trường `static final`: hiểu có điều kiện

JEP 416 đề cập đến sự khác biệt hiệu năng giữa đối tượng reflection được biểu diễn như hằng có thể nhận biết tại lúc JIT biên dịch và đối tượng thay đổi ở điểm gọi.

Mẫu tái sử dụng metadata thường dùng:

~~~java
import java.lang.reflect.Method;

public final class CachedReflection {
    private static final Method COMPUTE;

    static {
        try {
            COMPUTE = Calculator.class.getMethod("compute", int.class);
        } catch (NoSuchMethodException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static Object call(Calculator calculator, int input)
            throws ReflectiveOperationException {
        return COMPUTE.invoke(calculator, input);
    }

    public static class Calculator {
        public int compute(int input) {
            return input * 2;
        }
    }
}
~~~

Đối tượng `COMPUTE` được tìm đúng một lần và tái sử dụng. Điểm gọi với metadata ổn định **có thể** thuận lợi cho JIT. Tuy nhiên:

- Trường `static final` là một điều kiện mã hữu ích cho tối ưu, **không phải bảo đảm** performance.
- Nếu hành vi ứng dụng yêu cầu chọn member theo cấu hình, schema hoặc plugin ở runtime, không thể ép mọi metadata thành hằng chỉ để đạt benchmark đẹp.
- Mảng, map, cấu trúc cache hay gọi qua các lớp trừu tượng có thể khiến JIT khó chứng minh hằng ở một điểm gọi; tác động cụ thể thay đổi theo JDK và ngữ cảnh.
- Tối ưu hóa của JIT có thể thay đổi trong các bản JDK về sau. Không nên sao chép các con số microbenchmark từ lúc JEP được đề xuất làm cam kết cho production.

Mã ứng dụng cần ưu tiên **rõ ràng, đúng chức năng và giảm lookup lặp** trước khi theo đuổi tối ưu trong từng lời gọi reflection.

## 8. Thiết kế benchmark để kiểm chứng trên JDK hiện tại

Nếu mục tiêu thật sự là quyết định có thay reflection bằng Method Handle trực tiếp hay không, hãy thực hiện phép đo trên **đúng phiên bản JDK, hệ điều hành và kiểu tải** mà hệ thống sử dụng.

Một thử nghiệm hợp lý có thể so sánh:

1. **Direct call**: `counter.plus(5)`, dùng làm đường tham chiếu.
2. **Reflection có cache**: `CACHED_METHOD.invoke(counter, 5)`.
3. **Method Handle có cache**: handle đã được tìm trước, gọi đúng method type.
4. **Reflection động**: điểm gọi sử dụng những `Method` khác nhau nếu đây là hành vi thật trong ứng dụng.

Cần đo riêng **lookup/setup** và **invocation** vì hai chi phí trả lời những câu hỏi khác nhau. Ví dụ framework chỉ tìm method khi khởi động nhưng xử lý hàng triệu request thì trọng tâm là đường gọi nóng; một công cụ phân tích metadata một lần thường cần tập trung vào lookup và tính đơn giản hơn.

### Dùng JMH khi cần kết quả đáng tin cậy

JMH (*Java Microbenchmark Harness*) là công cụ benchmark chuyên dụng đang được sử dụng trong hệ sinh thái OpenJDK. Khi xây benchmark ngoài phạm vi bài học này, hãy:

- Chạy **warmup** để JIT có cơ hội tối ưu, đo nhiều lần và sử dụng **fork** JVM phù hợp.
- Tiêu thụ kết quả hoặc làm cho side effect quan sát được để tránh phép tính bị JVM loại bỏ.
- Giữ cùng dữ liệu đầu vào, cùng mục đích gọi và cùng xử lý kết quả cho các phương án.
- Không đưa lookup và khởi tạo handle vào vòng đo invocation, trừ khi ứng dụng thực tế làm như vậy.
- Phân biệt Method Handle `invokeExact` và `invoke` vì khả năng chuyển đổi kiểu khác nhau.
- Thử cả đường **metadata ổn định** và đường **metadata thay đổi** nếu workload có cả hai.
- Ghi rõ JDK build, tham số JVM và số lượng thread khi so sánh hoặc công bố kết quả.

Không lấy `System.nanoTime()` bao quanh một vài lời gọi trong `main` rồi kết luận tốc độ API. Lần chạy đầu thường gồm nạp lớp, khởi tạo, biên dịch nóng và nhiều chi phí khác khiến phép so sánh dễ sai.

### Đọc kết quả thế nào?

| Nếu benchmark cho thấy… | Kiểm tra thêm trước khi kết luận |
| --- | --- |
| Reflection cached gần bằng lời gọi trực tiếp | JIT đã tối ưu được gì? Method đích có bị loại khỏi phép đo không? |
| Method Handle nhanh hơn reflection | Có đang đo boxing, varargs, điều phối và khác biệt hợp đồng của hai API không? |
| Reflection động chậm hơn reflection cached | Chi phí lookup, tính đa hình tại điểm gọi và khả năng constant folding có khác nhau không? |
| Thứ tự xếp hạng đổi giữa hai JDK | JIT/JDK đã thay đổi; kết quả phải gắn với môi trường đo cụ thể |
| Chênh lệch rất nhỏ | Nhiễu đo, warmup, GC và độ ổn định của môi trường có đủ để kết luận không? |

## 9. Khi nào dùng reflection, khi nào dùng Method Handle trực tiếp?

**Giữ reflection** khi bạn cần khám phá metadata ở runtime: tìm method/constructor/field bằng tên, đọc annotation, xây framework dependency injection, serialization, mapping hoặc test tool. Với JDK từ Java 18, các thao tác lõi này đã có đường triển khai dựa trên method handles theo JEP 416. Không cần viết lại chỉ để được hưởng thay đổi nội bộ.

**Xem xét Method Handle trực tiếp** khi bạn đã xác định đích gọi, cần điều khiển chữ ký chặt chẽ, xây adapter/lời gọi động bằng `java.lang.invoke`, hoặc đo được chi phí reflection nằm trên đường nóng. Đổi sang Method Handle cũng mang theo công việc kiểm tra access rules, method type, chuyển đổi và ngoại lệ.

**Xem xét lời gọi Java trực tiếp** khi lớp và method đích đã được biết rõ tại compile time và không có nhu cầu động. Đây thường là thiết kế dễ bảo trì nhất, còn reflection là công cụ cho những nhu cầu thực sự yêu cầu động.

Trong mọi trường hợp, **strong encapsulation** vẫn có hiệu lực. `MethodHandle` không phải cách bỏ qua `exports`, `opens` hay quyền truy cập của member. Nếu một framework phải truy cập sâu, hãy thiết kế hợp đồng public hoặc cấu hình module theo phạm vi được phép thay vì dựa vào cơ chế nội bộ.

## 10. Sai lầm thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “JEP 416 tạo ra API `MethodHandle` trong Java 18.” | `java.lang.invoke` đã có trước; JEP 416 dùng cơ chế này để triển khai core reflection từ Java 18. |
| “`Method.invoke` bây giờ tương đương gọi `invokeExact`.” | Hợp đồng reflection vẫn khác về receiver, đối số, boxing và ngoại lệ. |
| “JEP 416 bảo đảm reflection luôn nhanh hơn.” | Không. Hiệu năng phụ thuộc workload, kiểu member, cách lưu metadata, JIT và phiên bản JDK. |
| “`static final Method` luôn được inline.” | `static final` có thể tạo cơ hội tối ưu nhưng không bảo đảm compiler sẽ inline. |
| “Dùng Method Handle trực tiếp vượt được private/member đóng trong module.” | Cả hai cơ chế phải tuân thủ quyền truy cập và JPMS. |
| “Benchmark một lần gọi trong `main` phản ánh production.” | Cần warmup, fork, phép đo hợp lệ và dữ liệu tải đại diện. |
| “Thay reflection bằng Method Handle không ảnh hưởng xử lý lỗi.” | Ngoại lệ của method đích, kiểu tại điểm gọi và quyền lookup có hợp đồng khác nhau. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trong JDK từ Java 18, vì sao một ứng dụng vẫn có thể gọi `Method.invoke` dù JEP 416 nói đến method handles?

**Trả lời:** JEP 416 thay đổi **phần triển khai bên trong core reflection**, không loại bỏ hoặc thay hợp đồng của `Method.invoke`. Ứng dụng tiếp tục dùng API reflection chuẩn.

**Câu 2.** Vì sao nên cân nhắc lưu `Method` trong `static final` cho một điểm gọi lặp lại?

**Trả lời:** Vì có thể tránh tìm metadata nhiều lần và giúp JIT thấy một đối tượng reflection ổn định, tạo điều kiện tối ưu. Đó là một cơ hội, không bảo đảm tốc độ trong mọi JDK/workload.

**Câu 3.** Vì sao `(int) handle.invokeExact(counter, 5)` cần kiểu kết quả ở điểm gọi?

**Trả lời:** `invokeExact` yêu cầu kiểu tại điểm gọi khớp đúng method type của handle, trong ví dụ là `(Counter, int)int`. Kiểu kết quả cũng là một phần của hợp đồng này.

**Câu 4.** Nếu `Method.invoke` gọi vào method ném `IllegalStateException`, bên gọi quan sát được điều gì? Còn một Method Handle gọi trực tiếp cùng method?

**Trả lời:** Theo hợp đồng reflection, lỗi từ phần thân method được bọc trong `InvocationTargetException`; handle trực tiếp không tự thêm lớp bọc ngoại lệ đó.

**Câu 5.** Nhóm benchmark nào là chưa công bằng khi so sánh hai API?

**Trả lời:** So một lời gọi reflection vừa thực hiện `getDeclaredMethod`, vừa tạo `Object[]` và boxing mỗi lần với Method Handle đã cache và gọi `invokeExact`, rồi kết luận khác biệt chỉ do cơ chế triển khai. Phải tách lookup, adapter và invocation theo mục tiêu phép đo.

## Ghi nhớ

- **JEP 416, có từ Java 18, triển khai lại các thao tác cốt lõi của `Method`, `Constructor` và `Field` dựa trên method handles.**
- **API reflection công khai không đổi hợp đồng**: quyền truy cập, receiver, chuyển đổi đối số, boxing và xử lý ngoại lệ tiếp tục có ý nghĩa.
- JIT **có thể** tối ưu tốt hơn khi đối tượng reflection ổn định, đặc biệt ở điểm gọi với metadata có thể được nhận diện như hằng; kết quả thực tế cần benchmark.
- Dùng Method Handle trực tiếp khi nhu cầu kiểu gọi và kết quả đo chứng minh lợi ích. Không thay toàn bộ reflection theo cảm tính.
- Để ra quyết định trên **JDK đang dùng**, hãy đo workload đại diện, phân biệt lookup và invocation, bảo đảm warmup/fork, và không suy rộng con số đo từ một phiên bản JDK sang phiên bản khác.

**Tài liệu tham khảo:** [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416); Javadoc `java.lang.reflect.Method`, `java.lang.reflect.Constructor`, `java.lang.reflect.Field`; Javadoc `java.lang.invoke.MethodHandle`, `java.lang.invoke.MethodHandles.Lookup` và `java.lang.invoke.MethodType` trên đúng phiên bản JDK đang sử dụng.
