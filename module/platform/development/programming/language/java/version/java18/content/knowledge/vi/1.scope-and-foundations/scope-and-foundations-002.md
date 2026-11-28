# Phân biệt API có từ trước với thay đổi được đưa vào Java 18, đặc biệt là MethodHandle

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Xác định rõ một API được **giới thiệu khi nào**, hành vi nào **thực sự thay đổi từ Java 18**, và điều gì vẫn được **đảm bảo bởi đặc tả API** trên JDK hiện đại. Trọng tâm là `MethodHandle`, `MethodHandles.Lookup` và việc **core reflection dùng method handles bên trong**.

## 1. Vì sao cần phân biệt nguồn gốc API và thời điểm thay đổi?

Khi đọc tài liệu Java 18, hai câu sau trông giống nhau nhưng nói về hai điều khác nhau:

- “`MethodHandle` được giới thiệu trong Java 18.” → **Sai.** `java.lang.invoke.MethodHandle` đã có từ **Java 7**.
- “Java 18 thay đổi cách JDK triển khai core reflection bằng method handles.” → **Đúng.** Đây là nội dung **JEP 416**.

Sự khác biệt có ý nghĩa thực tế. Một đoạn mã sử dụng `MethodHandles.lookup().findVirtual(...)` không phải bằng chứng rằng ứng dụng cần Java 18: API này đã tồn tại trước đó. Ngược lại, mã chỉ dùng `java.lang.reflect.Method.invoke(...)` vẫn có thể chạy qua phần thực thi được tái triển khai từ Java 18, dù **không sửa một dòng mã nguồn nào**.

Khi phân tích thay đổi nền tảng, nên tách thành ba lớp:

1. **API công khai:** Tên lớp, phương thức, chữ ký, hợp đồng lỗi, quyền truy cập; có thể kiểm chứng qua Javadoc và mục `Since`.
2. **Hành vi mặc định hoặc khả năng mới:** Ví dụ Java 18 chuẩn hóa charset mặc định thành UTF-8 (JEP 400) hoặc bổ sung SPI phân giải tên (JEP 418).
3. **Cách JDK thực thi API:** Ví dụ Java 18 thay phần lõi của reflection dùng method handles (JEP 416). Lớp này có thể thay đổi mà chương trình không phải đổi API.

**Quy tắc khi nâng cấp JDK:** Ưu tiên hợp đồng công khai được đặc tả và kiểm chứng trên phiên bản JDK đang chạy. Không gắn tính đúng đắn của ứng dụng với tên lớp nội bộ, chiến lược JIT hay kết quả benchmark từng thời điểm.

## 2. Bản đồ thời gian: cái nào đã có, cái nào thực sự đến từ Java 18?

| Thành phần | Xuất hiện trước Java 18? | Java 18 thay đổi gì? | Cách hiểu đúng trên JDK hiện đại |
|---|---|---|---|
| `java.lang.reflect.Method`, `Field`, `Constructor` | Có; core reflection đã xuất hiện từ các JDK đầu tiên, `Method` có `Since: 1.1` | **JEP 416** thay cơ chế thực thi của core reflection | Tiếp tục sử dụng API reflection bình thường, tuân theo đặc tả |
| `java.lang.invoke.MethodHandle`, `MethodType`, `MethodHandles` | Có; **Java 7** | Không phải API mới do JEP 416 tạo ra | Dùng để biểu diễn, gọi và biến đổi thao tác có kiểu động |
| JVM `invokedynamic` | Có; **Java 7** | Không được Java 18 giới thiệu lại | Cơ chế liên kết lời gọi động của JVM, có quan hệ với method handles |
| `VarHandle` | Có; **Java 9** | Không phải nội dung JEP 416 | API xử lý biến với chế độ truy cập và memory ordering riêng |
| `MethodHandles.privateLookupIn(...)` | Có; **Java 9** | Không phải API mới của Java 18 | Vẫn chịu điều kiện truy cập, nhất là `opens` trong JPMS |
| JPMS (`module-info.java`, `exports`, `opens`) | Có; **Java 9** | JEP 416 không xóa các ràng buộc module | Reflection và method handles đều phải tôn trọng đóng gói |
| Charset mặc định UTF-8 | Trước Java 18 có API UTF-8, nhưng default charset phụ thuộc môi trường | **JEP 400** thay giá trị mặc định trong các trường hợp được quy định | Cần phân biệt charset mặc định với `StandardCharsets.UTF_8` |
| `jwebserver` / `SimpleFileServer` | Chưa có trong JDK trước 18 | **JEP 408** giới thiệu công cụ và API web server tĩnh đơn giản | Có thể dùng để xem nội dung tĩnh khi phát triển |
| Javadoc `{@snippet}` | Chưa có trong standard doclet trước 18 | **JEP 413** bổ sung snippet tag | Tạo ví dụ tài liệu rõ ràng hơn; vẫn phải kiểm thử riêng |
| `InetAddressResolverProvider` | Chưa có trước 18 | **JEP 418** đưa SPI phân giải tên vào Java SE | Có thể cài resolver tùy biến trong phạm vi JVM |

Bảng này dùng **mốc của lớp/khả năng tiêu biểu**, không giả định mọi phương thức bên trong một lớp đều xuất hiện cùng lúc. Đọc `Since` của **từng thành phần** khi xác định mức JDK tối thiểu của mã.

### Nhìn theo mốc phiên bản

~~~text
Java 1.1      Java 7                 Java 9                 Java 18                 Java 22+
   |             |                      |                       |                        |
Reflection    MethodHandle,          VarHandle,             JEP 416: core           Bỏ triển khai
Method        MethodType,            JPMS,                   reflection dùng         core reflection
              MethodHandles,         privateLookupIn         method handles          cũ của JDK
              invokedynamic                                  bên trong
                                                               |
                                                    JEP 400/408/413/418
                                                    mang các thay đổi khác
~~~

Từ **JDK 22**, triển khai core reflection cũ đã bị loại bỏ. Cờ `-Djdk.reflect.useDirectMethodHandle=false` từng được đề cập để quay về cơ chế cũ trong giai đoạn Java 18 **không còn hiệu lực từ JDK 22**. Vì vậy, không nên đưa cờ này vào cấu hình hoặc hướng dẫn khắc phục sự cố cho JDK hiện đại. Đây là ví dụ cho thấy cần tách **tùy chọn lịch sử** khỏi **hành vi vẫn được hỗ trợ**.

## 3. MethodHandle thực chất là gì? (API có từ Java 7)

`MethodHandle` là tham chiếu có thể thực thi đến một thao tác: gọi phương thức, khởi tạo đối tượng, truy cập trường hoặc một thao tác đã biến đổi từ những handle khác. Mỗi handle có **`MethodType`** mô tả **kiểu trả về** và **các kiểu tham số**, bao gồm cả tham số receiver đối với phương thức instance.

Ví dụ phương thức:

~~~java
public String greet(String name) {
    return "Xin chào, " + name;
}
~~~

Một handle tìm bằng `findVirtual` có thể mang kiểu:

~~~text
(Greeter, String)String
   |        |        |
receiver   tham số   kiểu trả về
~~~

Trong khi phương thức Java được khai báo chỉ có một tham số `String`, một handle gọi phương thức instance có thêm receiver làm tham số đầu tiên.

### 3.1. Ba API cốt lõi đã có từ trước

| API | Trách nhiệm | Điều cần kiểm chứng |
|---|---|---|
| `MethodHandles.lookup()` | Tạo `Lookup` gắn với ngữ cảnh quyền của caller | Không đồng nghĩa “có quyền xem mọi private member” |
| `Lookup.findStatic`, `findVirtual`, `findConstructor` | Tìm handle đến thành phần có chữ ký cụ thể | Tên, kiểu tham số, kiểu trả về và quyền truy cập |
| `MethodType.methodType(...)` | Mô tả kiểu gọi của handle | Chữ ký phải khớp; primitive `int` khác `Integer` |
| `MethodHandle.type()` | Đọc `MethodType` của handle đã tạo | Receiver có thể là tham số đầu |
| `invokeExact(...)` | Gọi với descriptor trùng chính xác | Kiểm tra cả kiểu tham số **và kiểu trả về** tại call site |
| `invoke(...)` | Gọi với chuyển đổi kiểu được `asType` cho phép | Không phải mọi chuyển đổi đều hợp lệ |
| `asType(...)`, `bindTo(...)` | Tạo handle mới bằng phép thích nghi hoặc gắn receiver | Không tự động nâng quyền truy cập |

`MethodHandle` là đối tượng bất biến, nhưng **phương thức hoặc dữ liệu mà nó tham chiếu có thể thay đổi trạng thái**. Không được suy ra “handle bất biến” đồng nghĩa với “lời gọi không có side effect”.

### 3.2. Ví dụ chạy được: cùng một phương thức, ba cách gọi

Lưu mã sau vào `InvocationPaths.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class InvocationPaths {
    public static class Greeter {
        public String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    public static void main(String[] args) throws Throwable {
        Greeter receiver = new Greeter();

        // Cách 1: lời gọi Java thông thường.
        String normal = receiver.greet("An");

        // Cách 2: API reflection đã có từ trước Java 18.
        Method reflected = Greeter.class.getMethod("greet", String.class);
        String throughReflection = (String) reflected.invoke(receiver, "An");

        // Cách 3: MethodHandle đã có từ Java 7.
        MethodType declaredType =
                MethodType.methodType(String.class, String.class);
        MethodHandle handle = MethodHandles.lookup().findVirtual(
                Greeter.class, "greet", declaredType);

        System.out.println(handle.type());
        // (Greeter,String)String

        String throughHandle =
                (String) handle.invokeExact(receiver, "An");

        if (!normal.equals(throughReflection)
                || !normal.equals(throughHandle)) {
            throw new AssertionError("Kết quả không đồng nhất");
        }
        System.out.println(throughHandle);
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~shell
javac -encoding UTF-8 InvocationPaths.java
java InvocationPaths
~~~

Dòng `handle.type()` cho thấy chữ ký runtime của handle. Cả ba cách đều có thể cho kết quả `Xin chào, An`.

**Điểm cốt lõi:** Bất kể chương trình chạy trên Java 17 hay một JDK hiện đại, *cách viết* của lời gọi reflection và method handle không đột nhiên được tạo ra tại Java 18. JEP 416 thay phần triển khai mà lời gọi reflection đi qua **khi chạy trên JDK có thay đổi đó**.

### 3.3. Chuyển từ reflection sang MethodHandle bằng API có sẵn

Không nhất thiết tìm lại phương thức bằng tên và `MethodType`. `Lookup.unreflect(Method)` chuyển một `Method` thành handle khi quyền truy cập cho phép:

~~~java
Method method = Greeter.class.getMethod("greet", String.class);
MethodHandle handle = MethodHandles.lookup().unreflect(method);

// Kiểu của handle instance vẫn gồm receiver:
System.out.println(handle.type()); // (Greeter,String)String

String result = (String) handle.invokeExact(new Greeter(), "Bình");
System.out.println(result); // Xin chào, Bình
~~~

Đoạn trên có thể đặt **bên trong phương thức `main` của lớp `InvocationPaths`** ở ví dụ trước, nơi `Greeter` đã được định nghĩa và đã import các kiểu cần thiết. `unreflect` là **API cũ**, không phải tên gọi của JEP 416. API này vẫn thực hiện kiểm tra quyền thích hợp; nó không tự mở thành phần private của module khác.

## 4. Tại sao `invokeExact` không giống `Method.invoke`?

Hãy xét một đối tượng cung cấp phép tính:

~~~java
public static class Calculator {
    public int plus(int a, int b) {
        return a + b;
    }
}
~~~

Với `findVirtual(Calculator.class, "plus", MethodType.methodType(int.class, int.class, int.class))`, kiểu handle là:

~~~text
(Calculator,int,int)int
~~~

Nó chấp nhận một receiver kiểu `Calculator`, hai `int`, và trả về `int`.

### 4.1. Kiểu trả về cũng là một phần chữ ký

~~~java
MethodHandle h = MethodHandles.lookup().findVirtual(
        Calculator.class, "plus",
        MethodType.methodType(int.class, int.class, int.class));

Calculator calculator = new Calculator();

// Đúng: call site là (Calculator,int,int)int.
int correct = (int) h.invokeExact(calculator, 2, 3);

// Sai: call site yêu cầu trả về long thay vì int.
try {
    long wrong = (long) h.invokeExact(calculator, 2, 3);
    throw new AssertionError("Không được chạy đến đây: " + wrong);
} catch (java.lang.invoke.WrongMethodTypeException expected) {
    System.out.println(expected.getClass().getSimpleName());
}

// Hợp lệ: invoke có thể thích nghi kết quả int sang long.
long adapted = (long) h.invoke(calculator, 2, 3);
System.out.println(correct + ", " + adapted); // 5, 5
~~~

`invokeExact` kiểm tra descriptor do trình biên dịch tạo từ **kiểu thực tế ở call site**. Phép ép kiểu `(int)` hoặc `(long)` trong biểu thức gọi đóng vai trò xác định kiểu trả về mà call site yêu cầu; vì vậy không thể bỏ qua nó khi phân tích lỗi `WrongMethodTypeException`.

`invoke` linh hoạt hơn `invokeExact` vì nó có thể áp dụng những chuyển đổi hợp lệ theo `asType` (chẳng hạn widening từ `int` sang `long` ở vị trí trả về). Nó vẫn có thể ném `WrongMethodTypeException` hoặc `ClassCastException` tùy kiểu và giá trị thực tế.

### 4.2. Reflection gọi động theo hợp đồng khác

~~~java
Method method = Calculator.class.getMethod(
        "plus", int.class, int.class);

Object value = method.invoke(new Calculator(), 2, 3);
int answer = (Integer) value;
System.out.println(answer); // 5
~~~

`Method.invoke` nhận danh sách đối số qua `Object...` và trả `Object`, do đó boxing/unboxing thường xuất hiện với kiểu nguyên thủy. Nó cho phép các chuyển đổi widening hợp lệ ở tham số, nhưng không chấp nhận mọi chuyển đổi kiểu tùy ý.

| Khía cạnh | `Method.invoke` | `MethodHandle.invokeExact` | `MethodHandle.invoke` |
|---|---|---|---|
| Đầu vào về mặt API | `Object` receiver và `Object...` arguments | Call site có descriptor cụ thể | Call site có descriptor cụ thể, có thể thích nghi |
| Trả về | `Object` (hoặc `null` với phương thức `void`) | Đúng kiểu trả về tại call site | Có thể chuyển đổi kiểu trả về hợp lệ |
| Kiểm tra quyền | Kiểm tra truy cập khi gọi, trừ khi được phép bỏ qua | Kiểm tra quyền khi **tạo** handle | Tương tự `invokeExact` |
| Sai số lượng/kiểu đối số | Thường `IllegalArgumentException` | `WrongMethodTypeException` nếu descriptor không khớp | Có thể `WrongMethodTypeException` hoặc lỗi chuyển đổi |
| Ngoại lệ từ phương thức đích | Bọc trong `InvocationTargetException` | Truyền ngoại lệ đích trực tiếp | Truyền ngoại lệ đích trực tiếp |

Không nên lấy “cả hai đều gọi phương thức” làm lý do thay thế `Method.invoke` bằng `invokeExact` mà không đổi thiết kế bộ xử lý kiểu và ngoại lệ.

### 4.3. Ngoại lệ của phương thức đích: một khác biệt dễ bỏ sót

~~~java
public static class FailingService {
    public void fail() {
        throw new IllegalStateException("Lỗi nghiệp vụ");
    }
}
~~~

Với reflection:

~~~java
Method m = FailingService.class.getMethod("fail");
try {
    m.invoke(new FailingService());
} catch (java.lang.reflect.InvocationTargetException e) {
    System.out.println(e.getCause().getClass().getSimpleName());
    // IllegalStateException
}
~~~

Với method handle:

~~~java
MethodHandle h = MethodHandles.lookup().findVirtual(
        FailingService.class, "fail",
        MethodType.methodType(void.class));

try {
    h.invokeExact(new FailingService()); // Trả về void.
} catch (IllegalStateException e) {
    System.out.println(e.getMessage()); // Lỗi nghiệp vụ
}
~~~

Các đoạn minh họa thuộc ngữ cảnh đã import `java.lang.invoke.*` và `java.lang.reflect.*` như ở ví dụ trước. Trong ứng dụng thật, một `MethodHandle` có thể ném nhiều kiểu ngoại lệ khác và phương thức gọi khai báo `throws Throwable` hoặc xử lý theo yêu cầu. **Không** được dùng cùng logic `catch (InvocationTargetException)` cho cả hai con đường.

## 5. JEP 416 thay đổi chính xác điều gì?

### 5.1. Phần được thay đổi trong Java 18

Trước JEP 416, HotSpot/JDK có các cơ chế thực thi core reflection khác nhau, trong đó có lời gọi native và các lớp truy cập sinh mã phục vụ lời gọi reflection. JEP 416 đơn giản hóa bằng cách triển khai các thao tác qua hạ tầng method handles.

~~~text
Ứng dụng Java
    |
    |  API công khai ổn định
    v
Method.invoke / Constructor.newInstance / Field.get
    |
    |  JEP 416: thay cơ chế thực thi trong JDK 18
    v
Hạ tầng java.lang.invoke / MethodHandle
    |
    v
Thao tác trên phương thức, constructor, field đích
~~~

Mục tiêu của JEP 416 là giảm chi phí duy trì các cơ chế song song, làm đơn giản nội bộ HotSpot và tạo nền tảng thuận lợi hơn cho việc hỗ trợ thay đổi ngôn ngữ tương lai. Đây là **thay đổi triển khai**, không phải lời hứa rằng mọi lời gọi reflection chạy nhanh hơn hoặc rằng các hạn chế truy cập đã được gỡ bỏ.

Các lớp API vẫn được dùng theo hợp đồng của `java.lang.reflect`:

- `Method.invoke(Object, Object...)` vẫn trả `Object` và bọc ngoại lệ do đích ném trong `InvocationTargetException`.
- `Constructor.newInstance(Object...)` vẫn hoạt động theo hợp đồng constructor reflection.
- `Field.get`/`set` vẫn tuân theo quy tắc truy cập, kiểu và tính bất biến của trường tương ứng.

Để bảo đảm mã có thể chạy lâu dài, **không truy cập** lớp nội bộ của trình thực thi reflection, không sửa các trường private của `java.lang.reflect` và không phụ thuộc tên lớp do JDK tự tạo. Đây không phải các API được bảo đảm tương thích.

### 5.2. Có phải từ Java 18 mọi API đều trở thành MethodHandle?

**Không.** Method handles là nền tảng bên trong **core reflection** theo phạm vi JEP 416. Ứng dụng vẫn tự chọn API:

- Dùng `java.lang.reflect` khi cần liệt kê phương thức, đọc annotation, hoặc gọi member theo dữ liệu cấu hình.
- Dùng `MethodHandle` khi cần thao tác có `MethodType` rõ ràng và có nhu cầu thích nghi hoặc tái sử dụng điểm gọi.
- Dùng lời gọi Java trực tiếp khi thành phần được biết sẵn lúc biên dịch và không có nhu cầu động.
- Dùng `VarHandle` nếu bài toán thuộc về truy cập biến với memory ordering/atomic operations; **VarHandle không phải alias của MethodHandle**.

API nào được chọn nên theo thiết kế chương trình; JEP 416 không bắt ứng dụng phải viết lại các điểm sử dụng reflection hiện hữu.

### 5.3. Không khôi phục cơ chế reflection cũ trên JDK hiện đại

Tài liệu Java 18 từng nhắc `-Djdk.reflect.useDirectMethodHandle=false` để tạm quay lại cơ chế trước JEP 416. Theo ghi chú chính thức của **JDK 22**, triển khai cũ đã bị xóa và tùy chọn này chỉ còn là `no-op`. Do đó:

- Không dùng cờ đó để “sửa” ứng dụng chạy trên JDK 22+.
- Không kiểm tra hoặc sửa mã dựa trên sự tồn tại của lớp nội bộ reflection trước Java 18.
- Khi có lỗi nâng cấp, đối chiếu **hợp đồng API**, **quyền truy cập module**, **thư viện phụ thuộc** và **stack trace hiện tại**, sau đó tái hiện với bài test nhỏ.

Điều còn áp dụng lâu dài là kiến trúc dùng method handles bên trong reflection và hợp đồng Java SE; cách quay về triển khai lịch sử đã hết giá trị.

## 6. Quyền truy cập: JEP 416 không bỏ qua Java access control hay JPMS

### 6.1. Hai con đường kiểm tra quyền

**Reflection:** `Class.getDeclaredMethod` có thể trả về mô tả của phương thức private, nhưng điều đó **không** chứng minh caller có thể gọi phương thức ấy. `Method.invoke` kiểm tra quyền; `trySetAccessible()` chỉ thành công trong điều kiện API và module cho phép.

**MethodHandle:** `MethodHandles.Lookup` kiểm tra quyền tại thời điểm lấy handle. Một khi đã tạo handle hợp lệ, có thể truyền nó như một năng lực gọi cho nơi khác; mỗi lần `invokeExact` không thực hiện lại phép kiểm tra của `Lookup` theo danh tính caller mới. Vì vậy **không chia sẻ handle tới member nhạy cảm** cho mã không đáng tin cậy.

Ví dụ:

~~~java
MethodHandles.Lookup callerLookup = MethodHandles.lookup();

// publicLookup chỉ có khả năng công khai tương ứng.
MethodHandles.Lookup publicLookup = MethodHandles.publicLookup();

// Khi được phép deep reflection, có thể lấy lookup cho lớp đích.
// API này xuất hiện ở Java 9, không phải Java 18.
MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(Target.class, callerLookup);
~~~

`Target` ở đây là lớp đích minh họa. Câu lệnh cuối có thể ném `IllegalAccessException` nếu caller không đáp ứng điều kiện. Đừng xem nó như cách vượt qua mọi ranh giới module.

### 6.2. Ví dụ JPMS với `exports` và `opens`

Giả sử module thư viện chứa package `com.example.library` và module plugin là `com.example.plugin`.

~~~java
// module-info.java của thư viện
module com.example.library {
    exports com.example.library;
    // Chỉ thêm dòng sau nếu thực sự cần cho phép deep reflection:
    opens com.example.library to com.example.plugin;
}
~~~

Ở module plugin:

~~~java
module com.example.plugin {
    requires com.example.library;
}
~~~

`exports` cho phép truy cập các thành phần public phù hợp từ module đọc được thư viện. `opens` cho phép deep reflection trong phạm vi được nêu (ở đây chỉ cho module plugin). Quyền deep reflection liên quan cả `setAccessible` và `privateLookupIn`; JEP 416 **không tạo ra quyền mới**.

Dùng `--add-opens` chỉ như giải pháp tạm khi cần xử lý thư viện bên thứ ba và có hiểu biết về quyền bị mở. Thiết kế bền vững thường là định nghĩa API public rõ ràng hoặc khai báo `opens ... to ...` một cách có kiểm soát.

### 6.3. Một số trường hợp báo lỗi cần phân loại

| Hiện tượng | Khả năng nguyên nhân | Hướng kiểm chứng |
|---|---|---|
| `NoSuchMethodException` khi tìm bằng reflection/Lookup | Sai tên hoặc chữ ký; phân biệt public/inherited và declared | Xem `getMethod` với `getDeclaredMethod`, đối chiếu tham số chính xác |
| `IllegalAccessException` khi tạo handle | `Lookup` không đủ quyền truy cập | Kiểm tra caller class, module readability, `exports`/`opens` |
| `InaccessibleObjectException` tại `setAccessible(true)` | Không được quyền bỏ qua kiểm tra truy cập | Kiểm tra cấu hình module của class đích |
| `WrongMethodTypeException` ở `invokeExact` | Kiểu call site không khớp `MethodType` của handle | In `handle.type()`; kiểm tra receiver, primitive và kiểu trả về |
| `InvocationTargetException` tại `Method.invoke` | Phương thức đích đã ném ngoại lệ | Xem `getCause()` để tìm lỗi thực của nghiệp vụ |
| `ClassCastException` sau `invoke`/`Method.invoke` | Ép hoặc chuyển đổi tham chiếu không phù hợp | Kiểm tra kiểu runtime và hợp đồng trả về |

Cùng một lỗi quyền truy cập có thể xuất hiện ở **thời điểm khác nhau** tùy API: lookup method handle có thể thất bại ngay khi tạo, còn reflection thường phát hiện lúc gọi hoặc lúc thử thay đổi cờ accessibility.

## 7. Hiệu năng: vấn đề cần đo, không phải kết luận từ JEP

Từ “tái triển khai core reflection bằng method handles” không đủ để suy luận “reflection luôn nhanh hơn kể từ Java 18”. JEP 416 phân tích những kết quả microbenchmark có khác biệt theo cách các đối tượng `Method`, `Field` và `Constructor` được lưu và tối ưu hóa, đặc biệt khi đối tượng phản chiếu được giữ ổn định ở vị trí giúp JIT nhận diện.

Hiệu năng thực tế còn phụ thuộc:

- **Kiểu member:** phương thức, constructor, đọc/ghi field.
- **Cách xây dựng và lưu handle/member:** tạo mới mỗi lần so với cache; đối tượng có thể được JIT xem như hằng số hay không.
- **Chữ ký và chuyển đổi:** boxing, varargs, `asType`, `invokeWithArguments`.
- **Profile thực tế:** chi phí thao tác I/O, parse dữ liệu hoặc xử lý nghiệp vụ có thể lớn hơn nhiều chi phí reflection.
- **JDK và JVM cụ thể:** phiên bản, cấu hình tối ưu hóa, warmup, GC và workload.

### Ví dụ quyết định kỹ thuật

Một bộ ánh xạ DTO đọc annotation, sau đó gọi getter trên hàng triệu đối tượng. Có thể:

1. Dùng reflection một lần để **khám phá metadata**.
2. Lưu `Method` và thực thi `Method.invoke`; bắt đầu bằng phương án đơn giản, có test rõ ràng.
3. Nếu benchmark xác nhận bottleneck, cân nhắc tạo và cache `MethodHandle` từ `Lookup.unreflect`, đồng thời kiểm tra kiểu và quyền truy cập.
4. Đo lại trên **JDK mục tiêu**, dữ liệu đại diện và tải có ý nghĩa.

Một handle đã tạo không bảo đảm luôn nhanh hơn reflection. Cũng không cần tái viết mọi thư viện reflection chỉ vì JEP 416 đã được đưa vào JDK.

Nếu cần đo lường microbenchmark, nên dùng một framework đo phù hợp như JMH, bao gồm warmup, lặp lại, nhiều fork khi cần và tránh phép đo bị JIT loại bỏ. Không rút kết luận từ một vòng lặp duy nhất dùng `System.nanoTime()`.

## 8. “Chạy được trên JDK mới” không có nghĩa “API xuất hiện trên JDK mới”

Đây là quy trình xác định đúng mốc API:

1. **Xác định lớp và phương thức cụ thể.** `MethodHandle` và `MethodHandle.asSpreader` có thể có mốc `Since` khác nhau dù nằm cùng lớp.
2. **Đọc Javadoc của phiên bản JDK mục tiêu** và mục `Since` cho class hoặc member được dùng.
3. **Đối chiếu JEP / release notes** để biết JDK thay đổi API, hành vi mặc định hay triển khai.
4. **Biên dịch bằng `--release` khi cần kiểm tra tương thích mã nguồn/API.** Ví dụ `--release 17` kiểm tra khả năng tham chiếu API trong Java 17; tùy chọn đó **không đổi** engine reflection của JDK dùng để chạy chương trình.
5. **Chạy kiểm thử trên từng JDK mục tiêu** khi cần xác nhận hành vi runtime; chỉ biên dịch được chưa đủ để kết luận các đặc điểm như hiệu năng hoặc chi tiết reflection.

Ví dụ:

~~~shell
java -version
javac -version

# Dùng JDK hiện tại để biên dịch với bộ API tương thích Java 17.
javac --release 17 InvocationPaths.java

# Chạy bằng Java hiện tại; runtime quyết định cách triển khai.
java InvocationPaths
~~~

Vì `MethodHandle` đã tồn tại từ Java 7, ví dụ này không cần API mới của Java 18. Nếu muốn kiểm chứng phần triển khai reflection, phải quan sát hành vi trên JDK thực tế, không thể suy ra chỉ từ `--release 17`. Đừng dùng các tùy chọn nội bộ/đã loại bỏ của JDK để làm “bằng chứng”.

### Checklist phân loại một phát biểu kỹ thuật

| Phát biểu | Phân loại | Dựa vào đâu để xác minh |
|---|---|---|
| “`MethodHandle` được thêm ở Java 18.” | Sai mốc | Javadoc `MethodHandle` ghi `Since: 1.7` |
| “`VarHandle` là API mới của Java 18.” | Sai mốc | Javadoc `VarHandle` ghi `Since: 9` |
| “`Method.invoke` đã có trước Java 18.” | Đúng | Javadoc `Method` ghi `Since: 1.1` |
| “JEP 416 đổi cơ chế core reflection.” | Đúng, thay đổi triển khai | JEP 416 và ghi chú phát hành JDK 18 |
| “Java 18 cho phép truy cập mọi member private bằng reflection.” | Sai hợp đồng | `AccessibleObject`, `Lookup`, điều kiện JPMS |
| “JDK 22+ có thể bật lại core reflection cũ bằng cờ của JEP 416.” | Sai ở JDK hiện đại | Ghi chú phát hành JDK 22: cờ trở thành `no-op` |
| “Một benchmark Java 18 đủ để bảo đảm MethodHandle luôn nhanh hơn.” | Sai về suy luận | Cần benchmark trên JDK và workload cụ thể |

## 9. Các lỗi tư duy phổ biến khi học Java 18

### 9.1. “JEP nhắc đến API” ⇒ “JEP đã giới thiệu API”

Không đúng. Một JEP có thể **sử dụng** cơ chế cũ để thay phần triển khai của API khác. JEP 416 nhắc `MethodHandle` vì JDK dùng nó làm nền tảng; mốc ra đời của `MethodHandle` vẫn là Java 7.

### 9.2. “Reflection dùng MethodHandle bên trong” ⇒ “Hai API có cùng cách gọi và lỗi”

Không đúng. `Method.invoke` vẫn trả `Object`, hỗ trợ truyền `Object...` và bọc lỗi đích. `invokeExact` xét đúng descriptor, bao gồm kiểu trả về, và truyền trực tiếp ngoại lệ đích. Đây là **hợp đồng quan sát được** của hai API, tồn tại độc lập với chi tiết tối ưu hóa của JDK.

### 9.3. “MethodHandle” ⇒ “Có thể bỏ qua private access”

Không đúng. Quyền của `Lookup` được kiểm tra khi tạo handle; `privateLookupIn` còn chịu ràng buộc module. Handle có thể là năng lực nhạy cảm nên việc trao nó cho mã khác cần được xem xét.

### 9.4. “Thay nội bộ bằng MethodHandle” ⇒ “Phải migrate hết reflection”

Không đúng. Không có yêu cầu chuyển `Method.invoke` sang `MethodHandle.invokeExact`. Chỉ thay cách xây dựng lời gọi nếu thiết kế hoặc phép đo thực tế cho thấy cần thiết.

### 9.5. “Tùy chọn chạy được trên một bản cũ” ⇒ “Còn đáng dùng trên JDK hiện nay”

Không đúng. Ví dụ rõ ràng là cờ bật lại triển khai core reflection cũ đã hết tác dụng từ JDK 22. Khi đọc blog hoặc ví dụ từ thời Java 18 mới ra mắt, hãy kiểm tra release notes của JDK mục tiêu.

## 10. Bài thực hành có tiêu chí kiểm chứng

### Bài 1 — Phân loại mốc API

Xác định mốc `Since` cho `Method`, `MethodHandle`, `VarHandle` và `MethodHandles.privateLookupIn` trên Javadoc JDK hiện đại. Tìm JEP 416 và giải thích vì sao nó không chứng minh `MethodHandle` ra đời ở Java 18.

**Đạt khi:** Phân biệt được “API được giới thiệu” với “triển khai của API khác được thay đổi”.

### Bài 2 — Kiểm tra kiểu lời gọi

Chạy `InvocationPaths.java`. Thêm `Calculator` và tạo handle cho `plus(int,int)`. In `handle.type()`, chạy một lệnh `invokeExact` đúng kiểu, rồi cố ý đổi kiểu trả về mong đợi sang `long`.

**Đạt khi:** Dự đoán đúng `WrongMethodTypeException` và giải thích được vì sao `invoke` có thể thích nghi `int` thành `long`.

### Bài 3 — So sánh ngoại lệ

Tạo `FailingService.fail()` ném `IllegalStateException`. Gọi cùng phương thức qua reflection và MethodHandle.

**Đạt khi:** Nhìn thấy `InvocationTargetException.getCause()` ở reflection và lỗi đích trực tiếp ở MethodHandle.

### Bài 4 — Ranh giới module

Tạo hai module: thư viện export một package và plugin đọc package đó. Thử `getDeclaredMethod` trên private method, `trySetAccessible()`, rồi `privateLookupIn`. Thay đổi `module-info.java` để cấp `opens` cho plugin có kiểm soát.

**Đạt khi:** Giải thích được sự khác biệt giữa `exports` và `opens`, đồng thời chỉ ra JEP 416 không nới quyền truy cập.

### Bài 5 — Đánh giá phát biểu về hiệu năng

Một đồng nghiệp nói: “Đã lên Java 18 nên mọi lời gọi `Method.invoke` chắc chắn nhanh hơn phiên bản cũ.” Hãy đưa ra cách kiểm chứng và các biến số cần giữ ổn định.

**Đạt khi:** Không khẳng định hiệu năng tuyệt đối; đề xuất đo trên JDK mục tiêu, kiểm tra cache/call site và workload thực tế.

## 11. Nguồn tra cứu chính thức

Dùng tài liệu đúng phiên bản JDK đang triển khai. Các liên kết dưới đây ưu tiên đặc tả và ghi chú chính thức, tránh ví dụ dựa vào API nội bộ hoặc cờ đã hết hiệu lực:

1. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): xác định rõ phạm vi **thay đổi triển khai** ở Java 18.
2. [Oracle JDK 18 Release Notes — JEP 416](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html): mô tả thay đổi reflection và những phụ thuộc vào cơ chế nội bộ có thể bị ảnh hưởng.
3. [Oracle JDK 22 Release Notes — Old Core Reflection Implementation Removed](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html): xác nhận cơ chế cũ đã loại bỏ và cờ quay về cũ trở thành `no-op`.
4. [`Method` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html): `Since: 1.1`, hợp đồng `invoke` và xử lý lỗi.
5. [`MethodHandle` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): `Since: 1.7`, `invokeExact`, `invoke`, `MethodType` và kiểm tra chữ ký.
6. [`MethodHandles.Lookup` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): tạo handle và quy tắc quyền truy cập.
7. [`VarHandle` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html): `Since: 9` và memory ordering.
8. [`AccessibleObject` — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html): điều kiện `setAccessible` và `trySetAccessible`.

**Ghi nhớ khi học module Java 18:** Điều đáng học lâu dài không chỉ là ghi nhớ số JEP, mà là đọc đúng lớp thay đổi: **API mới**, **hành vi mặc định mới**, hay **triển khai bên trong JDK được cải tiến**. Với MethodHandle, mốc Java 7 và với core reflection, mốc tái triển khai Java 18 phải được phân biệt rõ để viết mã có thể duy trì trên JDK hiện đại.
