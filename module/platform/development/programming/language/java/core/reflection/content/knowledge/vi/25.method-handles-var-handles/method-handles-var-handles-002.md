# `MethodHandles.Lookup`: quyền được kiểm tra khi tạo handle

Trong Java, `MethodHandle` là một tham chiếu có kiểu đến một phương thức hoặc constructor; `VarHandle` là một đối tượng cung cấp những thao tác truy cập biến/trường/mảng theo kiểu được kiểm soát. Để lấy handle đến **thành viên đã đặt tên** (method, constructor, field), ta thường dùng `java.lang.invoke.MethodHandles.Lookup`. Điểm mấu chốt: **quyền truy cập được kiểm tra lúc tạo handle; khi đã có handle hợp lệ, việc gọi nó không lặp lại kiểm tra quyền truy cập Java vào thành viên đích**. Việc gọi vẫn chịu kiểm tra kiểu, những giới hạn thao tác và ngoại lệ khi mã đích chạy.

Đây là lý do `Lookup` vừa là công cụ tìm thành viên, vừa là một **khả năng được ủy quyền (capability)**: nó mang ngữ cảnh và mức quyền của mã đã tạo ra nó. Nắm rõ ranh giới này giúp viết thư viện, framework, mã Reflection/MethodHandle và mã tương tác với Java Platform Module System (JPMS) đúng và an toàn.

## 1. `Lookup` chứa ngữ cảnh truy cập nào?

`MethodHandles.Lookup` là đối tượng dùng làm “nhà máy” tạo handle. Nó ghi nhận:

- **Lookup class**: lớp mà quyền truy cập được xét theo; lấy bằng `lookup.lookupClass()`.
- **Lookup modes**: các mức quyền còn hiệu lực, chẳng hạn `PUBLIC`, `PACKAGE`, `PROTECTED`, `PRIVATE`, `MODULE`; có thể xem bitmask qua `lookup.lookupModes()`. Các bit này không có nghĩa là được phép truy cập mọi lớp/thành viên ở bất kỳ module nào.
- **Ngữ cảnh module**: quan hệ đọc module, các package được `exports`/`opens` và, với lookup được chuyển sang module khác, cả ngữ cảnh lookup trước đó có thể ảnh hưởng phạm vi truy cập.

Quyền được quyết định từ **lớp gọi đã tạo `Lookup`**, chế độ lookup, khả năng truy cập lớp đích và thành viên đích. Đặt `Lookup` trong một biến tên `admin` hoặc truyền một `Class<?>` khác vào phương thức tìm kiếm không làm tăng quyền.

### Ba cách lấy lookup phổ biến

| Cách | Phạm vi và tác dụng | Giới hạn cần nhớ |
| --- | --- | --- |
| `MethodHandles.lookup()` | Lookup gắn với **lớp đang gọi lệnh** này; thông thường có đầy đủ quyền tương ứng lớp đó, bao gồm private của chính lớp/nestmates và quyền được Java cho phép | Không tự đọc được `private` của một lớp top-level khác chỉ vì cùng package; không vượt qua encapsulation của module khác |
| `MethodHandles.publicLookup()` | Lookup chỉ dành cho các lớp/thành viên `public` đủ điều kiện; hữu ích khi thư viện chỉ cần API công khai | Không lấy được `private`/`package-private`; trong JPMS, đối tượng này chỉ thấy các API công khai ở package được export vô điều kiện |
| `MethodHandles.privateLookupIn(Target.class, callerLookup)` | Tạo lookup có khả năng truy cập private của `Target` **nếu** `callerLookup` được phép thực hiện deep reflection đối với lớp này | Lookup nguồn phải có `PRIVATE` và `MODULE`; giữa các module còn phải đáp ứng điều kiện đọc module và package đích phải được `opens` đến module của bên gọi |

`lookup.in(Target.class)` chỉ **chuyển ngữ cảnh lookup với quyền có thể bị thu hẹp**, không phải lệnh cấp quyền private. Chuyển sang nest/package/module khác có thể làm mất các mode tương ứng. `dropLookupMode(...)` cũng có thể giảm quyền có chủ đích. Muốn truy cập private của lớp khác, dùng `privateLookupIn` khi đủ điều kiện, không coi `in` là lối tắt.

## 2. Quyền được xét ở thời điểm nào?

Xét luồng tìm một method thông qua `findVirtual`:

1. Mã gọi tạo hoặc nhận một `Lookup`; lookup giữ danh tính lớp và các mode truy cập.
2. Mã yêu cầu `lookup.findVirtual(Target.class, "work", MethodType.methodType(ReturnType.class, ...))`.
3. Java phân giải lớp/thành viên và **kiểm tra truy cập**: lớp `Target` có khả kiến không, thành viên có hợp lệ với mode của lookup không, và các ràng buộc module/protected khác có thỏa không.
4. Nếu hợp lệ, API trả một `MethodHandle` có kiểu xác định. Nếu không, thao tác **tạo handle** thất bại, thường bằng `IllegalAccessException` cho trường hợp không đủ quyền hoặc `NoSuchMethodException` cho tìm kiếm method không phù hợp.
5. Bất kỳ mã nào nhận được handle có thể gọi nó theo kiểu và điều kiện invocation của handle, kể cả khi mã đó không thể tự tạo một handle tương đương. **Không có kiểm tra quyền private mới mỗi lần gọi.**

Các API thường kiểm tra truy cập tại lúc tạo gồm `findStatic`, `findVirtual`, `findSpecial`, `findConstructor`, `findGetter`, `findSetter`, `findVarHandle`, `findStaticVarHandle` và nhiều dạng `unreflect`. Khi gọi `unreflect` từ một đối tượng Reflection đã chỉnh trạng thái accessible, hành vi còn phụ thuộc quy tắc tương ứng của API; không nên suy ra rằng mọi `Lookup` đều được vượt quyền.

Đối với `VarHandle`, kiểm tra quyền lúc lấy handle không có nghĩa **mọi access mode** đều khả dụng: ví dụ việc `set` qua VarHandle của một trường `final` thường không được hỗ trợ, và có thể ném `UnsupportedOperationException`. Khả năng get/set/atomic operation và tính đúng kiểu của từng thao tác vẫn là ràng buộc lúc sử dụng.

### Tách lỗi tạo handle khỏi lỗi gọi handle

| Thời điểm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Tạo** | `findVirtual` yêu cầu private member mà lookup không được phép thấy | `IllegalAccessException` |
| **Tạo** | Tên, loại method hoặc chữ ký `MethodType` không tìm thấy | `NoSuchMethodException` (đối với method); tìm field sai có thể là `NoSuchFieldException` |
| **Gọi** | `invokeExact` được gọi với kiểu tham số/trả về không khớp chính xác kiểu của handle | `WrongMethodTypeException` |
| **Gọi** | Giá trị tham số cần ép kiểu tham chiếu nhưng không tương thích | Có thể xảy ra `ClassCastException` |
| **Gọi** | Chính phương thức đích ném ngoại lệ | Ngoại lệ của phương thức đích được truyền ra theo cách gọi handle |

`invokeExact` yêu cầu descriptor tại call site khớp chính xác kiểu của handle; `invoke` cho phép một số phép điều chỉnh kiểu hợp lệ. Sự khác nhau đó là **kiểm tra kiểu khi gọi**, không phải cấp lại quyền đọc private. Ngoài ra, `MethodHandle.asType(...)` tạo handle điều chỉnh kiểu mà không tự đi tìm lại thành viên private, nên không cần `Lookup` mới cho lần điều chỉnh ấy.

## 3. Ví dụ Java 17+: được phép tạo handle, không được phép tự tìm private

Lưu **nguyên vẹn** ví dụ sau vào tệp `LookupAccessDemo.java`. Tệp chứa hai lớp top-level; `SecretBox` **không** phải lớp lồng/nestmate của `LookupAccessDemo`. Điều này quan trọng vì nestmates trong Java hiện đại có thể chia sẻ quyền private theo quy tắc riêng.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;

public class LookupAccessDemo {
    public static String greeting() {
        return "hello";
    }

    private static void consume(MethodHandle handle, SecretBox box)
            throws Throwable {
        // consume không có quyền tự tìm SecretBox.message().
        // Nhưng nó được phép sử dụng handle đã được trao.
        String value = (String) handle.invokeExact(box);
        System.out.println("delegated: " + value);
    }

    public static void main(String[] args) throws Throwable {
        MethodType noArgsString = MethodType.methodType(String.class);

        MethodHandles.Lookup publicView = MethodHandles.publicLookup();
        MethodHandle greetingHandle = publicView.findStatic(
                LookupAccessDemo.class, "greeting", noArgsString);
        System.out.println("public: " + (String) greetingHandle.invokeExact());

        MethodHandles.Lookup caller = MethodHandles.lookup();
        try {
            caller.findVirtual(SecretBox.class, "message", noArgsString);
            System.out.println("unexpected success");
        } catch (IllegalAccessException expected) {
            System.out.println("normal lookup: denied");
        }

        MethodHandles.Lookup privateView =
                MethodHandles.privateLookupIn(SecretBox.class, caller);

        MethodHandle secretHandle = privateView.findVirtual(
                SecretBox.class, "message", noArgsString);

        SecretBox box = new SecretBox();
        System.out.println(
                "private lookup: " + (String) secretHandle.invokeExact(box));

        consume(secretHandle, box);

        VarHandle countHandle = privateView.findVarHandle(
                SecretBox.class, "count", int.class);
        System.out.println("private VarHandle: " + (int) countHandle.get(box));

        try {
            publicView.findVirtual(SecretBox.class, "message", noArgsString);
            System.out.println("unexpected success");
        } catch (IllegalAccessException expected) {
            System.out.println("public lookup: denied");
        }

        System.out.println(
                "receiver count: " + secretHandle.type().parameterCount());
    }
}

class SecretBox {
    private int count = 7;

    private String message() {
        return "secret=42";
    }
}
~~~

Chạy trong terminal có JDK 17 hoặc mới hơn:

~~~bash
javac LookupAccessDemo.java
java LookupAccessDemo
~~~

Kết quả tiêu chuẩn:

~~~text
public: hello
normal lookup: denied
private lookup: secret=42
delegated: secret=42
private VarHandle: 7
public lookup: denied
receiver count: 1
~~~

Giải thích từng điểm:

- `publicLookup().findStatic(...)` thành công vì `LookupAccessDemo` là lớp public và `greeting()` là phương thức public static. Handle nhận được có kiểu `()String`.
- `caller` là lookup của `LookupAccessDemo`, có thể truy cập phần phù hợp với quyền của lớp này, **không được truy cập private của `SecretBox`** dù hai lớp cùng package.
- `privateLookupIn(SecretBox.class, caller)` thành công trong ví dụ cùng unnamed module, với lookup nguồn đủ quyền. Sau đó `findVirtual` tạo được handle cho `SecretBox.message()` và `findVarHandle` tạo được handle cho trường `count`.
- Phương thức `consume` chỉ **nhận** handle. Nó không cần tự tra cứu hoặc được kiểm tra lại quyền private khi `invokeExact(box)`. Đó chính là việc **trao capability** cho mã khác.
- `publicView` không đủ quyền tìm `SecretBox.message()`; lớp `SecretBox` còn là kiểu package-private, nên bản thân lớp cũng không đáp ứng điều kiện nhìn thấy của public lookup.
- `MethodType.methodType(String.class)` mô tả **các tham số khai báo** của method `message()` (không có tham số). Nhưng handle được tạo bởi `findVirtual` cần receiver `SecretBox` ở vị trí đầu, do đó handle có kiểu `(SecretBox)String` và `parameterCount()` bằng `1`.

Lưu ý: khối `catch (IllegalAccessException ...)` ở đây chủ ý thử **truy cập không được phép khi tạo handle**. Không dùng exception như cơ chế phân quyền chung của ứng dụng; nếu thành viên không tồn tại hoặc chữ ký sai thì phải xử lý loại lỗi tìm kiếm tương ứng.

## 4. Phân biệt với Reflection và phương án cấp quyền khác

Với core Reflection, `Method.invoke` nhìn chung thực hiện kiểm tra quyền truy cập lúc gọi theo cơ chế của Reflection (trạng thái `AccessibleObject` có thể ảnh hưởng); với handle đã được tạo thành công qua `Lookup`, việc invoke về sau không lặp lại bước xét quyền Java cho thành viên gốc. Vì thế:

- `getDeclaredMethod("hidden")` có thể tìm metadata của một method private, nhưng **tìm được method** khác với **được quyền gọi** hoặc **được quyền tạo MethodHandle** cho nó.
- `setAccessible(true)` không phải chìa khóa vượt JPMS tùy ý: truy cập sâu còn bị giới hạn bởi module, và `InaccessibleObjectException` có thể xuất hiện.
- `lookup.findVirtual(...)` có kiểm tra quyền lúc lấy handle; `handle.invokeExact(...)` kiểm tra descriptor và thực hiện mã đích. Đừng trộn lẫn hai thời điểm.
- Trao một `MethodHandle` tới private method hoặc `VarHandle` tới private field cho plugin/callback tương đương với **trao khả năng sử dụng thành viên đó**. Giấu tên method/field sau khi trao handle không thu hồi được capability.
- Trao nguyên đối tượng `Lookup` có nhiều quyền còn rộng hơn: người nhận có thể yêu cầu tạo **những handle khác** trong phạm vi quyền lookup. Nếu chỉ muốn gọi một hành vi được chọn, cấp handle hẹp hoặc một API wrapper thay vì lookup đặc quyền.
- Nếu cần chạy với quyền ít hơn, chủ động dùng `publicLookup()`, `dropLookupMode(...)` hoặc API công khai được thiết kế cho phía tiêu thụ; cần cân nhắc module `exports`/`opens` chính xác.

Khi dùng `MethodHandle` trong framework, hãy xác định ai tạo lookup, lớp nào là lookup class, package của lớp đích có đọc/mở/xuất đúng không, và handle được trao cho ai. Khả năng tạo handle và khả năng sử dụng handle là hai ranh giới quyền khác nhau.

## 5. Những nhầm lẫn phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`MethodHandles.lookup()` cho phép lấy private của mọi lớp cùng package.” | Lookup có quyền gắn với **lớp gọi**; private của lớp top-level khác cần cơ chế hợp lệ như `privateLookupIn`. |
| “`publicLookup()` đọc được mọi member `public` bất kể lớp/module.” | Lớp chứa member phải có thể truy cập và module/package phải đáp ứng ràng buộc công khai. |
| “`lookup.in(Target.class)` giúp nâng quyền lên private của `Target`.” | `in` có thể **làm mất** mode; không làm tăng quyền. |
| “`exports` đủ để lấy private member xuyên module.” | `exports` phục vụ API public; deep reflection xuyên module cần `opens` và các điều kiện lookup khác. |
| “Mỗi `invokeExact` lại kiểm tra xem caller có quyền private hay không.” | Access check dành cho thành viên diễn ra khi **tạo** handle; invocation kiểm tra kiểu và chạy mã. |
| “Tạo được VarHandle là lúc nào cũng `set` được.” | Access mode còn phụ thuộc loại biến, `final` và tính năng được hỗ trợ. |
| “Trao handle private cho bên thứ ba là vô hại.” | Bên nhận có thể dùng handle đã được trao; cần kiểm soát phạm vi ủy quyền. |

### Câu hỏi tự kiểm tra

1. Nếu `A` và `B` là hai lớp top-level trong cùng package, vì sao `MethodHandles.lookup()` từ `A` không thể tự dùng `findVirtual` để mở private method của `B`?
2. Tại sao `privateLookupIn` thành công trong cùng module nhưng có thể thất bại giữa hai named module dù lớp đích là `public`?
3. Khi `findVirtual` thành công và truyền handle cho mã không biết lớp đích, quyền thành viên được kiểm tra lúc nào? Còn kiểu đối số được kiểm tra lúc nào?
4. Vì sao `findVirtual(SomeClass.class, "f", MethodType.methodType(String.class))` tạo handle có thêm một tham số receiver so với `findStatic` cho phương thức không tham số?

**Kết luận:** `Lookup` quyết định **bên nào được tạo handle đến thành viên nào**; handle được tạo thành công là capability có thể được sử dụng hoặc chuyển giao. Kiểm tra quyền truy cập xảy ra khi tạo handle, còn kiểm tra kiểu, hỗ trợ thao tác và ngoại lệ đích vẫn áp dụng khi dùng handle. Nắm ranh giới này là chìa khóa để dùng `MethodHandle`/`VarHandle` đúng với Java 17+ và JPMS.

*Tài liệu đối chiếu: [Java SE 21 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) và [Java SE 21 — MethodHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html).*