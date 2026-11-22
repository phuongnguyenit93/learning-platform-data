# ExceptionInInitializerError và tác động tới lần dùng sau (Java 15+)

## 1. Lỗi khởi tạo lớp khác với lỗi nạp và liên kết lớp

Một lớp Java có thể được **nạp (loading)** và **liên kết (linking)** thành công nhưng lại **khởi tạo (initialization)** thất bại khi thực thi bộ khởi tạo trường `static` hoặc khối `static { ... }`. JVM biên dịch các công việc khởi tạo đó thành logic khởi tạo lớp, thường được gọi là **`<clinit>`**.

Theo Java Language Specification (JLS) `12.4.2, khi khởi tạo lớp thất bại vì một ngoại lệ **không phải `Error`**, JVM bọc nguyên nhân bằng **`ExceptionInInitializerError`** và đánh dấu `Class` tương ứng là **erroneous**. Khi mã cố dùng lại **cùng lớp đó** theo cách cần khởi tạo, JVM **không thử chạy lại initializer**, mà ném **`NoClassDefFoundError`**.

Đây vẫn là quy tắc của Java hiện đại. Chủ đề nằm trong ngữ cảnh **Khởi tạo và sinh mã** vì từ **Java 15**, phương thức `MethodHandles.Lookup.defineHiddenClass(...)` là API chính thức tạo *hidden class* từ bytecode. Tham số `initialize` của API quyết định **thời điểm khởi tạo**, và do đó quyết định lỗi xuất hiện ngay ở bước định nghĩa lớp hay được hoãn cho lần sử dụng đầu tiên.

**Cần phân biệt ba vấn đề:**

1. **Class file sai hoặc truy cập không hợp lệ:** có thể báo `ClassFormatError`, `VerifyError`, `IllegalAccessException` hoặc lỗi tương ứng ngay ở giai đoạn định nghĩa/linking. Đây không nhất thiết là lỗi `<clinit>`.
2. **Khởi tạo lần đầu thất bại:** thường nhận `ExceptionInInitializerError` khi initializer ném `RuntimeException`; `getCause()` chứa nguyên nhân thực tế.
3. **Dùng lại cùng lớp sau khi khởi tạo thất bại:** thường nhận `NoClassDefFoundError` vì lớp đã ở trạng thái erroneous.

Không cần API preview, `sun.misc.Unsafe` hay bất cứ API nội bộ lỗi thời nào để minh họa cơ chế này.

## 2. Khi nào JVM thực hiện khởi tạo lớp?

Các giai đoạn có mục đích khác nhau:

| Giai đoạn | Diễn ra điều gì? | Có bắt buộc chạy `static { ... }`? |
| --- | --- | --- |
| **Loading** | JVM tạo biểu diễn lớp từ class bytes, hoặc từ bytes được `Lookup.defineHiddenClass` cung cấp. | Không |
| **Linking** | Kiểm tra/chuẩn bị lớp, xử lý các tham chiếu khi cần. | Không |
| **Initialization** | Thực thi bộ khởi tạo trường `static` và các khối `static` theo quy tắc của ngôn ngữ. | Có |

Những thao tác có thể dẫn đến yêu cầu khởi tạo gồm: tạo instance bằng `new`, gọi phương thức `static`, đọc/ghi trường `static` thuộc trường hợp yêu cầu khởi tạo, các thao tác reflection thích hợp, gọi `Lookup.ensureInitialized(...)` hoặc lần thực thi một static `MethodHandle` chưa khởi tạo lớp.

**Không phải mọi việc nhắc đến tên lớp đều khởi tạo nó.** Ví dụ, class literal `MyClass.class` không tự chạy initializer. Đọc một `static final` *compile-time constant* qua mã đã biên dịch cũng có thể không kích hoạt khởi tạo lớp chứa hằng. Tương tự, **việc tạo handle bằng `findStatic` không nhất thiết chạy `<clinit>`**; lần thực thi handle có thể là điểm khởi tạo thực sự. Chương trình chạy ở mục 6 kiểm chứng cụ thể trường hợp này.

## 3. Chu trình lỗi đầu tiên và lần dùng tiếp theo

Xét một khối `static` gọi phương thức luôn ném lỗi:

~~~java
static {
    fail();
}

private static void fail() {
    throw new IllegalStateException("broken-init");
}
~~~

Đây là **đoạn minh họa nằm trong lớp**, không phải file độc lập. Khi JVM khởi tạo:

1. `fail()` ném `IllegalStateException`.
2. `IllegalStateException` không phải subtype của `Error`, nên JVM tạo `ExceptionInInitializerError` bọc lỗi gốc; `error.getCause()` trả về nguyên nhân.
3. JVM đánh dấu lớp đang khởi tạo là **erroneous** và hoàn tất bước khởi tạo bằng lỗi.
4. Các lần sử dụng **cùng `Class`** tiếp theo mà cần khởi tạo sẽ ném **`NoClassDefFoundError`**, thay vì thực thi lại `fail()`.

| Tình huống | Kết quả | Trạng thái lớp |
| --- | --- | --- |
| Lần đầu, initializer ném `IllegalStateException` | `ExceptionInInitializerError` với cause `IllegalStateException` | Erroneous |
| Lần dùng tiếp theo của chính lớp đó | `NoClassDefFoundError` | Vẫn erroneous |
| Lần đầu, initializer ném trực tiếp `AssertionError` | `AssertionError` không bị bọc thêm | Erroneous |
| Lần dùng tiếp theo sau `AssertionError` | `NoClassDefFoundError` | Vẫn erroneous |
| Initializer kết thúc bình thường | Không có lỗi | Initialized; không cần chạy lại |

**Không phải mọi lỗi trong initializer đều được bọc bằng `ExceptionInInitializerError`.** Java giữ nguyên một `Error` đã được ném trực tiếp. Hơn nữa, cả `ExceptionInInitializerError` lẫn `NoClassDefFoundError` đều là các subtype của `LinkageError` (thuộc `Error`), vì thế `catch (Exception ex)` **không** bắt được chúng.

Nếu initializer thất bại do initializer của một superclass hoặc superinterface liên quan, việc lan truyền lỗi có thêm quy tắc trong JLS `12.4.2. Đừng suy đoán rằng lỗi gốc luôn nằm ngay trong khối `static` của lớp được gọi; hãy kiểm tra stack trace và cause đầu tiên.

## 4. Định nghĩa hidden class: initialize=false và initialize=true

Từ Java 15, `MethodHandles.Lookup.defineHiddenClass(...)` định nghĩa hidden class từ class file hợp lệ:

~~~java
MethodHandles.Lookup owner = MethodHandles.lookup();
MethodHandles.Lookup hidden = owner.defineHiddenClass(classBytes, false);
Class<?> hiddenType = hidden.lookupClass();
~~~

`classBytes` phải chứa class file hợp lệ **cùng package với lookup class**. `owner` cần quyền truy cập phù hợp, cụ thể `full privilege access`. Các điều kiện về quyền/package được kiểm tra **riêng** với quá trình khởi tạo.

### 4.1. initialize=false: định nghĩa xong, khởi tạo sau

~~~java
MethodHandles.Lookup hidden = owner.defineHiddenClass(classBytes, false);
MethodHandle run = hidden.findStatic(
        hidden.lookupClass(), "value", MethodType.methodType(String.class));
~~~

Ở đây JVM có thể tạo hidden class và static MethodHandle **mà chưa thực hiện initializer**. Khi chạy:

~~~java
String value = (String) run.invokeExact();
~~~

lần thực thi này cần khởi tạo hidden class. Nếu `<clinit>` ném `IllegalStateException`, lần `invokeExact` đầu tiên sẽ nhận `ExceptionInInitializerError`. Sau đó, gọi lại cùng handle thường nhận `NoClassDefFoundError` vì **lớp ẩn đó đã erroneous**.

API chính thức `Lookup.ensureInitialized(Class<?>)` (có từ Java 15) cho phép yêu cầu khởi tạo một lớp một cách tường minh:

~~~java
hidden.ensureInitialized(hidden.lookupClass());
~~~

Nếu đây là lần khởi tạo đầu tiên của lớp hỏng, lỗi đầu tiên xuất hiện tại `ensureInitialized`. Nếu lớp đã thất bại ở một lời gọi trước đó, `ensureInitialized` gặp `NoClassDefFoundError`.

### 4.2. initialize=true: báo lỗi ngay khi định nghĩa

~~~java
MethodHandles.Lookup eager = owner.defineHiddenClass(classBytes, true);
~~~

`initialize=true` khiến JVM **khởi tạo hidden class ngay trong lời gọi `defineHiddenClass`**. Khi initializer thất bại, API ném lỗi **trước khi trả được `Lookup`**. Với một `IllegalStateException` trong initializer, lỗi đầu tiên vẫn là `ExceptionInInitializerError`; chỉ **thời điểm xuất hiện** khác trường hợp `false`.

`initialize=false` không có nghĩa “sẽ không bao giờ khởi tạo”, càng không phải biện pháp sandbox. Nó chỉ **hoãn tác dụng phụ** tới khi mã kích hoạt khởi tạo.

### 4.3. Hai hidden class cùng bytes vẫn là hai lớp riêng

Mỗi lần `owner.defineHiddenClass(sameBytes, false)` có thể tạo **một hidden class mới với danh tính lớp riêng biệt**. Class thứ nhất đã erroneous **không** tự làm class thứ hai erroneous. Nếu cùng bytes chứa initializer lỗi, class thứ hai sẽ trải qua **lần khởi tạo đầu tiên của chính nó** và cũng thất bại.

Điều đó **không phải hồi phục hay khởi tạo lại lớp cũ**. Trạng thái erroneous gắn với từng lớp được JVM định nghĩa, không gắn với tên file nguồn hay một mảng `byte[]` trong ứng dụng.

## 5. Thiết kế phép thử: ba lớp mẫu và bộ đếm

Chương trình dưới đây chứa ba lớp mẫu lồng nhau:

- **`FailingTemplate`:** khi khởi tạo, gọi một hàm của lớp chủ để tăng `failedRuns` rồi ném `IllegalStateException`. Nhờ bộ đếm, ta biết `<clinit>` chỉ được chạy một lần **trên mỗi định nghĩa lớp**.
- **`HealthyTemplate`:** tăng `healthyRuns`, sau đó trả `"READY"`; dù gọi phương thức tĩnh hai lần, initializer chỉ chạy một lần.
- **`ErrorTemplate`:** tăng `directErrorRuns` rồi ném trực tiếp `AssertionError`; kiểm thử đường xử lý không bọc thêm `Error`.

Dữ liệu class file đến từ `javac`, được đọc qua `getResourceAsStream(...)`. Các hàm tăng bộ đếm của lớp chủ được khai báo `public static` để hidden class **không cần `NESTMATE`** mới có thể gọi chúng. Chúng ta kiểm tra quyền định nghĩa hidden class riêng với logic lỗi khởi tạo; không cố tình tạo xung đột truy cập private không liên quan.

Khi thử hidden class, chương trình dùng **phần chênh bộ đếm** so với trước mỗi lần định nghĩa, để tránh nhầm một class đặt tên đã khởi tạo lỗi với các bản hidden class được định nghĩa từ cùng bytes.

## 6. Chương trình Java 17+ hoàn chỉnh

Lưu toàn bộ mã sau vào tệp **`HiddenInitConsequences.java`** (UTF-8):

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public class HiddenInitConsequences {
    private static int failedRuns;
    private static int healthyRuns;
    private static int directErrorRuns;

    public static void countFailed() { failedRuns++; }
    public static void countHealthy() { healthyRuns++; }
    public static void countDirectError() { directErrorRuns++; }

    public static class FailingTemplate {
        static {
            HiddenInitConsequences.countFailed();
            throwFailure();
        }
        private static void throwFailure() {
            throw new IllegalStateException("broken-init");
        }
        public static String value() { return "UNREACHABLE"; }
    }

    public static class HealthyTemplate {
        static { HiddenInitConsequences.countHealthy(); }
        public static String value() { return "READY"; }
    }

    public static class ErrorTemplate {
        static {
            HiddenInitConsequences.countDirectError();
            throwAnError();
        }
        private static void throwAnError() {
            throw new AssertionError("direct-error");
        }
        public static String value() { return "UNREACHABLE"; }
    }

    private static byte[] resource(String file) throws Exception {
        try (InputStream in = Objects.requireNonNull(
                HiddenInitConsequences.class.getResourceAsStream(file))) {
            return in.readAllBytes();
        }
    }

    private static String kind(Throwable failure) {
        return failure.getClass().getSimpleName();
    }

    public static void main(String[] args) throws Throwable {
        try {
            FailingTemplate.value();
        } catch (ExceptionInInitializerError error) {
            System.out.println("namedFirst=" + kind(error));
            System.out.println("namedCause=" + kind(error.getCause()));
        }
        try {
            FailingTemplate.value();
        } catch (NoClassDefFoundError error) {
            System.out.println("namedLater=" + kind(error));
        }
        System.out.println("namedInitRuns=" + failedRuns);

        MethodHandles.Lookup owner = MethodHandles.lookup();
        byte[] brokenBytes = resource("HiddenInitConsequences$FailingTemplate.class");
        int before = failedRuns;
        MethodHandles.Lookup deferred = owner.defineHiddenClass(brokenBytes, false);
        System.out.println("deferredNoInit=" + (failedRuns == before));
        MethodHandle call = deferred.findStatic(
                deferred.lookupClass(), "value", MethodType.methodType(String.class));
        System.out.println("handleNoInit=" + (failedRuns == before));
        try {
            String unused = (String) call.invokeExact();
        } catch (ExceptionInInitializerError error) {
            System.out.println("hiddenFirst=" + kind(error));
            System.out.println("hiddenCause=" + kind(error.getCause()));
        }
        try {
            String unused = (String) call.invokeExact();
        } catch (NoClassDefFoundError error) {
            System.out.println("hiddenLater=" + kind(error));
        }
        System.out.println("hiddenInitRuns=" + (failedRuns - before));
        try {
            deferred.ensureInitialized(deferred.lookupClass());
        } catch (NoClassDefFoundError error) {
            System.out.println("ensureLater=" + kind(error));
        }

        before = failedRuns;
        try {
            owner.defineHiddenClass(brokenBytes, true);
        } catch (ExceptionInInitializerError error) {
            System.out.println("eagerFirst=" + kind(error));
        }
        System.out.println("eagerInitRuns=" + (failedRuns - before));

        before = failedRuns;
        MethodHandles.Lookup distinct = owner.defineHiddenClass(brokenBytes, false);
        try {
            distinct.ensureInitialized(distinct.lookupClass());
        } catch (ExceptionInInitializerError error) {
            System.out.println("distinctFirst=" + kind(error));
        }
        System.out.println("distinctInitRuns=" + (failedRuns - before));

        byte[] healthyBytes = resource("HiddenInitConsequences$HealthyTemplate.class");
        before = healthyRuns;
        MethodHandles.Lookup healthy = owner.defineHiddenClass(healthyBytes, false);
        MethodHandle ok = healthy.findStatic(
                healthy.lookupClass(), "value", MethodType.methodType(String.class));
        System.out.println("healthyBefore=" + (healthyRuns == before));
        System.out.println("healthyFirst=" + (String) ok.invokeExact());
        System.out.println("healthyAgain=" + (String) ok.invokeExact());
        System.out.println("healthyInitRuns=" + (healthyRuns - before));

        byte[] errorBytes = resource("HiddenInitConsequences$ErrorTemplate.class");
        before = directErrorRuns;
        MethodHandles.Lookup directly = owner.defineHiddenClass(errorBytes, false);
        try {
            directly.ensureInitialized(directly.lookupClass());
        } catch (AssertionError error) {
            System.out.println("errorFirst=" + kind(error));
        }
        try {
            directly.ensureInitialized(directly.lookupClass());
        } catch (NoClassDefFoundError error) {
            System.out.println("errorLater=" + kind(error));
        }
        System.out.println("errorInitRuns=" + (directErrorRuns - before));
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 HiddenInitConsequences.java
java HiddenInitConsequences
~~~

`javac` tạo `HiddenInitConsequences.class` và ba tệp `HiddenInitConsequences$FailingTemplate.class`, `HiddenInitConsequences$HealthyTemplate.class`, `HiddenInitConsequences$ErrorTemplate.class` trong cùng thư mục. Để lệnh `resource(...)` hoạt động, phải giữ các class file ở classpath khi chạy.

**Kết quả stdout chính xác** (đã biên dịch ở mức Java 17 và chạy trên JDK hiện đại):

~~~text
namedFirst=ExceptionInInitializerError
namedCause=IllegalStateException
namedLater=NoClassDefFoundError
namedInitRuns=1
deferredNoInit=true
handleNoInit=true
hiddenFirst=ExceptionInInitializerError
hiddenCause=IllegalStateException
hiddenLater=NoClassDefFoundError
hiddenInitRuns=1
ensureLater=NoClassDefFoundError
eagerFirst=ExceptionInInitializerError
eagerInitRuns=1
distinctFirst=ExceptionInInitializerError
distinctInitRuns=1
healthyBefore=true
healthyFirst=READY
healthyAgain=READY
healthyInitRuns=1
errorFirst=AssertionError
errorLater=NoClassDefFoundError
errorInitRuns=1
~~~

Đọc kết quả theo thứ tự:

- **`namedFirst` / `namedLater`:** lớp đặt tên khởi tạo lỗi trước, sau đó trở thành erroneous; `namedInitRuns=1` xác nhận không thử lại.
- **`deferredNoInit=true` / `handleNoInit=true`:** định nghĩa hidden class với `false` và tạo static MethodHandle chưa kích hoạt initializer trong chương trình này.
- **`hiddenFirst` / `hiddenLater` / `ensureLater`:** lần invoke đầu ném `ExceptionInInitializerError` với cause `IllegalStateException`; lần invoke sau và `ensureInitialized` trên cùng lớp ném `NoClassDefFoundError`.
- **`eagerFirst`:** với `true`, lỗi phát sinh trực tiếp trong `defineHiddenClass`, trước khi trả lookup.
- **`distinctFirst`:** lớp ẩn mới từ cùng bytes có lần khởi tạo đầu tiên độc lập; `distinctInitRuns=1` không có nghĩa lớp ẩn hỏng cũ đã được tái sử dụng.
- **`healthyFirst` / `healthyAgain`:** cả hai trả `READY` nhưng `healthyInitRuns=1`.
- **`errorFirst=AssertionError`:** `Error` gốc truyền thẳng ra, rồi `errorLater=NoClassDefFoundError` ở lần sau; `errorInitRuns=1`.

Chương trình in **tên loại ngoại lệ** bằng `getClass().getSimpleName()` thay vì so sánh toàn bộ `getMessage()` hoặc stack trace. Hidden class có tên chứa hậu tố do JVM tạo; thông điệp `NoClassDefFoundError` và một số thông tin định danh của lớp ẩn **không ổn định để đưa vào kiểm thử tuyệt đối**.

## 7. Hệ quả khi sử dụng lại lớp và xử lý đa luồng

### Không thể gọi lại initializer của cùng Class đã erroneous

Sau khi `<clinit>` thất bại, các lần sử dụng khác của **cùng lớp** không thể biến lớp đó thành chưa khởi tạo. Những thao tác như gọi lại phương thức tĩnh, thực thi lại handle hoặc gọi `ensureInitialized` sẽ gặp lỗi theo quy trình của JVM.

**Không viết vòng lặp** bắt `ExceptionInInitializerError` rồi gọi lại class hỏng với kỳ vọng `<clinit>` sẽ thử thêm lần nữa. Cần sửa **nguyên nhân gốc**, ví dụ cấu hình không hợp lệ, file cấu hình thiếu, dữ liệu khởi tạo lỗi, hoặc một dependency thất bại. Sau đó, nếu kiến trúc cho phép, có thể tạo **định nghĩa lớp mới** (hidden class khác hoặc class loader khác), nhưng đó là **lớp mới có danh tính mới**, không phải khôi phục đối tượng `Class` đã lỗi.

### Đồng bộ khởi tạo giữa các thread

JVM đồng bộ quá trình khởi tạo lớp theo quy tắc của JLS `12.4.2. Khi nhiều thread đồng thời yêu cầu khởi tạo một `Class`, chúng không tự do chạy `<clinit>` song song nhiều lần. Một thread thực hiện khởi tạo, các thread khác phải chờ theo quy tắc. Nếu khởi tạo thất bại, lớp trở thành erroneous.

Trong bài kiểm thử đa luồng, **không nên giả định một thread cụ thể luôn là thread nhìn thấy lỗi khởi tạo đầu tiên** vì lịch chạy có thể thay đổi. Nên kiểm tra số lần initializer thực sự chạy, ngoại lệ phù hợp và tính nhất quán của trạng thái sau khi tất cả thread hoàn tất.

### NoClassDefFoundError không luôn có nghĩa thiếu class file

`NoClassDefFoundError` có thể báo thiếu một định nghĩa cần thiết **hoặc** lớp ở trạng thái erroneous sau khởi tạo hỏng. Khi debug, phải đọc **lỗi đầu tiên** và `ExceptionInInitializerError.getCause()`; chỉ nhìn `NoClassDefFoundError` ở các lần dùng sau dễ dẫn đến chẩn đoán nhầm thành thiếu JAR hoặc classpath.

`ClassNotFoundException` khi cố nạp một class bằng tên là tình huống khác. Hidden class cũng không được tìm lại bằng tên nhị phân thông thường qua `Class.forName(String)`; phải giữ `Class<?>`, `Lookup` hoặc các `MethodHandle` mà framework đã nhận.

## 8. Lưu ý cho hệ thống sinh mã

| Quyết định | Khuyến nghị hiện hành |
| --- | --- |
| Chọn `initialize=false` hay `true` | `false` hoãn khởi tạo đến điểm cần dùng; `true` kiểm tra/khởi tạo sớm tại biên `defineHiddenClass`. Chọn dựa vào thời điểm muốn phát hiện lỗi và tác dụng phụ. |
| Phân biệt lỗi class file và lỗi initializer | `ClassFormatError`, `VerifyError` và lỗi quyền/package trong quá trình định nghĩa không đồng nghĩa `ExceptionInInitializerError` do `<clinit>`. |
| Ghi log chẩn đoán | Ghi **lỗi đầu tiên** và cause; đừng chỉ lưu `NoClassDefFoundError` ở lần dùng sau. |
| Bytecode không tin cậy | Hidden class **không phải sandbox**. Không tạo/khởi tạo bytecode không tin cậy bằng `Lookup` đặc quyền. |
| Khôi phục | Sửa nguyên nhân và tạo lớp mới khi thật sự cần; không tự retry `<clinit>` trên cùng `Class`. |
| Kiểm thử | Kiểm tra cả **lần đầu và lần sau**, đường lỗi `Error` trực tiếp, thành công một lần, và trường hợp tạo hidden class mới. |
| Giữ tham chiếu tới hidden class | Dùng `Lookup.lookupClass()` hoặc MethodHandle đã nhận; không phụ thuộc tên có hậu tố do JVM sinh. |

**Chú ý:** `ClassOption.NESTMATE` quyết định quan hệ nest và quyền truy cập private; `ClassOption.STRONG` ảnh hưởng vòng đời lớp ẩn. **Không option nào tự sửa logic `<clinit>` đang lỗi**. Cũng không nên lạm dụng `catch (Throwable)` trong logic ứng dụng để âm thầm bỏ qua lỗi khởi tạo; chương trình học sử dụng các nhánh `catch` cụ thể nhằm chứng minh hành vi.

## 9. Lỗi hiểu nhầm phổ biến

| Hiểu nhầm | Điều đúng |
| --- | --- |
| Một lỗi `ExceptionInInitializerError` có nghĩa class file bị hỏng | Class file có thể hợp lệ; lỗi phát sinh ở **khởi tạo**, không phải nhất thiết ở linking. |
| Lần dùng sau sẽ ném lại `IllegalStateException` ban đầu | Cùng lớp đã erroneous sẽ báo `NoClassDefFoundError` khi cần khởi tạo. |
| Bắt lỗi rồi gọi lại sẽ giúp `static` initializer chạy lần nữa | JVM không tự khởi tạo lại **cùng lớp** đã hỏng. |
| Mọi lỗi khởi tạo đều được bọc | Nếu nguyên nhân đã là `Error`, nó có thể đi ra trực tiếp. |
| `defineHiddenClass(bytes, false)` không bao giờ khởi tạo | Nó chỉ hoãn; MethodHandle invocation hoặc `ensureInitialized` vẫn có thể kích hoạt. |
| Hai hidden class sinh từ cùng `byte[]` dùng chung trạng thái lỗi | Mỗi định nghĩa hidden class có danh tính và trạng thái khởi tạo riêng. |
| `NoClassDefFoundError` chỉ xảy ra khi thiếu file `.class` | Đây còn là lỗi chuẩn khi lớp đã ở trạng thái erroneous. |
| Assert toàn bộ `getMessage()` của hidden class có thể ổn định trên mọi JDK | Hậu tố tên và thông điệp có thể thay đổi; kiểm tra loại lỗi, cause và bộ đếm đáng tin hơn. |

## 10. Checklist và tài liệu tham khảo

Trước khi triển khai/kiểm thử một hidden class có initializer, hãy xác định **lỗi sẽ xuất hiện ở đâu** (khi `defineHiddenClass(true)`, khi `ensureInitialized` hay ở lần invoke đầu); kiểm tra nguyên nhân của `ExceptionInInitializerError`, khẳng định lần dùng sau cho `NoClassDefFoundError`, theo dõi số lần `<clinit>` chạy, và không nhầm **cùng bytes** với **cùng lớp**.

Các nguồn chuẩn còn hiệu lực:

- [Java Language Specification SE 26 — `12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.4.1).
- [Java Language Specification SE 26 — `12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.4.2): lỗi đầu tiên, trạng thái erroneous, `NoClassDefFoundError` và đồng bộ khởi tạo.
- [Java SE 26 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass` và `ensureInitialized`.
- [Java SE 26 — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ExceptionInInitializerError.html): `getCause()` và cơ chế bọc nguyên nhân.
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): tính năng hidden class chính thức từ Java 15.

**Kết luận:** `ExceptionInInitializerError` thường cho biết **lần khởi tạo đầu tiên đã thất bại**; `NoClassDefFoundError` ở lần dùng sau cho biết **cùng lớp không thể được khởi tạo lại**. Trong mã sinh hidden class Java 15+, `initialize` chỉ thay đổi **thời điểm khởi tạo**, không thay đổi quy tắc trạng thái lỗi của JVM.