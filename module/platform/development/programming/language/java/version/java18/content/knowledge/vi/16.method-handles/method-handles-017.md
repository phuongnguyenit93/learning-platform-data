# Ngoại lệ do method đích ném qua handle và khác biệt với InvocationTargetException

## 1. Vì sao cùng một phương thức lại có hai cách nhận ngoại lệ?

Giả sử phương thức nghiệp vụ kiểm tra dữ liệu đầu vào và ném một checked exception:

~~~java
public static String normalize(String input) throws InvalidInputException {
    if (input == null || input.isBlank()) {
        throw new InvalidInputException("input must not be blank");
    }
    return input.trim();
}
~~~

Nếu gọi nó bằng `java.lang.reflect.Method.invoke(...)`, ngoại lệ do **thân phương thức đích** ném sẽ được bọc trong `java.lang.reflect.InvocationTargetException`. Mã gọi phải lấy `getCause()` để nhận nguyên nhân gốc.

Nếu gọi cùng phương thức bằng `java.lang.invoke.MethodHandle.invokeExact(...)` hoặc `MethodHandle.invoke(...)`, ngoại lệ do **phương thức đích** ném sẽ được truyền ra trực tiếp, không bị hai phương thức gọi handle này tự động bọc trong `InvocationTargetException`.

~~~text
Gọi qua java.lang.reflect.Method.invoke(...)
       |
       v
    normalize(" ")
       |
       +--> ném InvalidInputException
                    |
                    v
          InvocationTargetException
                    |
                    +--> getCause() = InvalidInputException

Gọi qua MethodHandle.invokeExact(...) / invoke(...)
       |
       v
    normalize(" ")
       |
       +--> ném trực tiếp InvalidInputException
~~~

**Điểm cốt lõi:** Quy tắc bọc exception là hợp đồng của API **gọi phương thức**, không phải thuộc tính bắt buộc của phương thức đích. Khi chuyển một thư viện từ reflection `Method.invoke` sang `MethodHandle`, cách bắt và truyền lỗi cần thay đổi tương ứng.

Bài học thuộc chương **MethodHandle** của module Java 18. `MethodHandle` và `InvocationTargetException` là những API vẫn được dùng trên các JDK hiện đại. Nội dung tập trung vào cách kiểm chứng hợp đồng ngoại lệ hiện hành, không dựa vào thủ thuật truy cập nội bộ JDK.

## 2. So sánh hợp đồng hai cơ chế gọi

| Khía cạnh | `Method.invoke(...)` | `MethodHandle.invokeExact(...)` / `invoke(...)` |
| --- | --- | --- |
| Gọi member | Gọi qua đối tượng `Method` đã tìm được bằng reflection | Gọi qua đối tượng `MethodHandle` với kiểu lời gọi phù hợp |
| Exception do **mã của method đích** ném | Được bọc trong `InvocationTargetException` | Thoát ra trực tiếp, theo kiểu `Throwable` gốc |
| Tìm nguyên nhân nghiệp vụ | `InvocationTargetException.getCause()` hoặc `getTargetException()` | Bắt trực tiếp exception thích hợp |
| Sai kiểu đối số hoặc cách gọi | Có thể ném `IllegalArgumentException` từ cơ chế reflection, trước khi vào method đích | `invokeExact` thường báo `WrongMethodTypeException` nếu call-site type không khớp; `invoke` có thể gặp lỗi chuyển đổi |
| Thiếu quyền truy cập | `IllegalAccessException` khi invoke | `IllegalAccessException` có thể xuất hiện **khi tạo handle** bằng một thao tác lookup |
| Bắt checked exception ở mã nguồn | `Method.invoke` khai báo các checked exception của chính reflection, trong đó có `InvocationTargetException` | `invoke` và `invokeExact` khai báo `throws Throwable`, dù method đích chỉ khai báo một checked exception cụ thể |
| Kiểu trả về và tham số | Runtime kiểm tra argument list do `Method.invoke` nhận | `MethodType` và kiểu tại call site quyết định việc khớp hoặc thích nghi |

Bảng này nói về các API gọi trực tiếp trên. Một handle có thể được kết hợp với adapter như `catchException` để **chủ động** bắt hoặc biến đổi lỗi; việc đó là hành vi được lập trình rõ ràng, không phải wrapper mặc định của `invokeExact`.

Ngoại lệ `InvocationTargetException` vẫn **có thể** xuất hiện khi gọi qua method handle nếu **chính method đích hoặc một adapter do ứng dụng viết** chủ động ném loại ngoại lệ ấy. Không nên hiểu câu “MethodHandle không bọc `InvocationTargetException`” thành “không bao giờ có đối tượng `InvocationTargetException` trên đường gọi MethodHandle”.

## 3. Chương trình hoàn chỉnh đối chiếu hai đường gọi

Tệp `ExceptionPropagationDemo.java` sau đây có một phương thức đích duy nhất, được gọi lần lượt bằng reflection `Method.invoke` và bằng `MethodHandle.invokeExact`.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ExceptionPropagationDemo {

    public static class InvalidInputException extends Exception {
        public InvalidInputException(String message) {
            super(message);
        }
    }

    public static String normalize(String input)
            throws InvalidInputException {
        if (input == null || input.isBlank()) {
            throw new InvalidInputException("input must not be blank");
        }
        return input.trim();
    }

    public static void main(String[] args) throws Throwable {
        String invalid = " ";

        // Cách 1: java.lang.reflect.Method
        Method method = ExceptionPropagationDemo.class.getMethod(
                "normalize", String.class);

        try {
            method.invoke(null, invalid); // null: method static
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getCause();
            System.out.println("reflection wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("reflection cause: "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }

        // Cách 2: java.lang.invoke.MethodHandle
        MethodType signature = MethodType.methodType(
                String.class, String.class);

        MethodHandle handle = MethodHandles.lookup().findStatic(
                ExceptionPropagationDemo.class,
                "normalize",
                signature);

        try {
            // Kiểu ở call site phải là (String)String.
            String result = (String) handle.invokeExact(invalid);
            System.out.println("result: " + result);
        } catch (InvalidInputException original) {
            System.out.println("method handle direct: "
                    + original.getClass().getSimpleName()
                    + ": " + original.getMessage());
        }
    }
}
~~~

Có thể biên dịch và chạy trên JDK hiện đại:

~~~bash
javac ExceptionPropagationDemo.java
java ExceptionPropagationDemo
~~~

Đầu ra dự kiến:

~~~text
reflection wrapper: InvocationTargetException
reflection cause: InvalidInputException: input must not be blank
method handle direct: InvalidInputException: input must not be blank
~~~

Lời gọi `method.invoke(null, invalid)` đưa giá trị `null` vào đối số receiver vì `normalize` là phương thức `static`. Ngược lại, `findStatic(...)` trả về một method handle có chữ ký `(String)String`, **không có receiver** trong danh sách đối số.

Tại `handle.invokeExact(invalid)`, việc ép kiểu `(String)` cho kết quả là quan trọng: `invokeExact` phải thấy cả **kiểu tham số và kiểu trả về tại call site** khớp `handle.type()`. Nếu đổi nó thành lời gọi bỏ qua kết quả, call site có return type là `void` và có thể nhận `WrongMethodTypeException` trước khi vào `normalize`.

Với dữ liệu đầu vào không hợp lệ, cả hai đường gọi đều vào được `normalize` và chạy cùng logic nghiệp vụ. Sự khác nhau quan sát được chỉ là **dạng ngoại lệ tới mã gọi**.

## 4. Vì sao Method.invoke có InvocationTargetException?

`Method.invoke(...)` là một API reflection có hợp đồng bao bọc lỗi được ném từ mã đã được gọi. Khi việc **thực thi phương thức đích** ném một exception hoặc error, wrapper `InvocationTargetException` cho biết rằng cuộc gọi reflection đã đến thân method và thất bại ở đó.

Mẫu bắt lỗi chính xác:

~~~java
try {
    Object result = method.invoke(receiver, arguments);
    // Xử lý result.
} catch (InvocationTargetException wrapped) {
    Throwable original = wrapped.getCause();
    // original là Throwable mà method đích đã ném.
}
~~~

`InvocationTargetException.getTargetException()` cũng cung cấp exception đích, nhưng `getCause()` là cách tương thích với mô hình nguyên nhân exception chung trong Java và thường tiện hơn khi xây cause chain.

Đừng nhầm hai cấp:

~~~text
InvocationTargetException       <- wrapper do Method.invoke tạo
  caused by InvalidInputException <- exception do method đích ném
~~~

**Không phải mọi exception do `Method.invoke` ném đều được bọc.** Chẳng hạn:

- `IllegalAccessException` có thể báo rằng mã gọi không được phép truy cập method.
- `IllegalArgumentException` có thể báo sai receiver hoặc danh sách đối số không hợp lệ.
- `ExceptionInInitializerError` có thể phát sinh từ quá trình khởi tạo lớp liên quan, theo hợp đồng API.
- `InvocationTargetException` là tín hiệu cho lỗi **do method đích ném trong khi thực thi**.

Vì thế mã xử lý cần phân biệt *gọi không thành công do reflection* với *method đã chạy rồi ném lỗi nghiệp vụ*. Nếu phương thức đích ném `RuntimeException` hoặc `Error`, khi gọi qua `Method.invoke` ngoại lệ từ method đích đó vẫn nằm ở `getCause()`.

## 5. Vì sao MethodHandle truyền trực tiếp ngoại lệ gốc?

`MethodHandle` biểu diễn một thao tác gọi có kiểu thông qua `MethodType`. `invokeExact` yêu cầu kiểu tại call site khớp chính xác kiểu handle; `invoke` hỗ trợ một số thích nghi kiểu được phép. Khi lời gọi đã đến **method đích**, một exception mà method đích ném sẽ thoát ra như exception đó.

~~~java
try {
    String result = (String) handle.invokeExact(" ");
} catch (InvalidInputException ex) {
    // Bắt trực tiếp exception từ normalize().
    System.err.println(ex.getMessage());
}
~~~

Không có bước `catch (InvocationTargetException e)` bắt buộc ở đây. Một thư viện không nên tự động viết mã “unwrap `InvocationTargetException`” cho tất cả method handle, vì nó có thể che giấu một `InvocationTargetException` được ném **có chủ đích** bởi method đích.

### Điều gì xảy ra với Throwable, RuntimeException và Error?

Nguyên tắc truyền trực tiếp áp dụng cả cho checked exception, unchecked exception và `Error` được ném từ method đích. Ví dụ:

~~~java
static String failFast(String value) {
    throw new IllegalStateException("service unavailable");
}
~~~

Nếu handle gọi được `failFast`, exception nhận được từ `invokeExact` là `IllegalStateException`. Nó không tự trở thành `InvocationTargetException`.

Không nên bắt `Throwable` chỉ để im lặng bỏ qua lỗi. Nếu cần một ranh giới dịch lỗi cho API thư viện, hãy xác định rõ checked exception nào cần chuyển đổi và để `Error` nghiêm trọng tiếp tục được truyền ra.

## 6. Tránh nhầm exception đích với lỗi của lookup hoặc call site

Khi dùng MethodHandle có ít nhất ba giai đoạn độc lập:

~~~mermaid
flowchart TD
    A["Tạo MethodType"] --> B["Lookup: findStatic/findVirtual..."]
    B --> C{"Lookup thành công?"}
    C -->|Không| D["NoSuchMethodException / IllegalAccessException"]
    C -->|Có| E["Có MethodHandle"]
    E --> F["invokeExact / invoke"]
    F --> G{"Kiểu call site hợp lệ?"}
    G -->|Không| H["WrongMethodTypeException hoặc lỗi thích nghi"]
    G -->|Có| I["Thực thi target"]
    I --> J{"Target ném Throwable?"}
    J -->|Có| K["Throwable gốc đi ra trực tiếp"]
    J -->|Không| L["Trả về kết quả"]
~~~

Đây là sơ đồ khái quát. Những handle phức hợp có thể thực thi thêm adapter hoặc filter trước khi vào method đích, và chúng cũng có thể ném exception. Điều cần xác định là **exception xuất hiện ở giai đoạn nào**.

| Giai đoạn | Ví dụ | Loại lỗi | Có phải exception nghiệp vụ từ method đích không? |
| --- | --- | --- | --- |
| Tạo kiểu | `MethodType.methodType(String.class, void.class)` | `IllegalArgumentException` | Không, descriptor tham số không hợp lệ. |
| Lookup | `findStatic` với tên hoặc chữ ký không tồn tại | `NoSuchMethodException` | Không, chưa gọi method đích. |
| Lookup | Member không thể truy cập từ lookup hiện tại | `IllegalAccessException` | Không, là lỗi quyền truy cập. |
| Call site với `invokeExact` | Handle là `(String)String` nhưng call site yêu cầu `(String)Object` | `WrongMethodTypeException` | Không, kiểu lời gọi không khớp. |
| Thích nghi với `invoke` | Adapter phải chuyển đối số không hợp lệ sang kiểu đích | Có thể là `ClassCastException` hoặc lỗi chuyển đổi khác | Không, có thể xảy ra trước khi target được gọi. |
| Method đích | `normalize(" ")` ném `InvalidInputException` | `InvalidInputException` được truyền trực tiếp | Có. |

Một `WrongMethodTypeException` không phải là lời khai rằng method đích đã chạy rồi ném lỗi. Tương tự, `IllegalAccessException` khi lookup xảy ra trước giai đoạn thực thi và không nên bị báo thành lỗi nghiệp vụ.

### Ví dụ lỗi call site

Giả sử `handle.type()` là `(String)String`:

~~~java
import java.lang.invoke.WrongMethodTypeException;

try {
    // Kiểu trả về mà call site yêu cầu là Object, không phải String.
    Object result = (Object) handle.invokeExact("hello");
    System.out.println(result);
} catch (WrongMethodTypeException ex) {
    System.out.println("Call-site type mismatch");
}
~~~

Mặc dù `String` gán được cho biến `Object` trong Java thường, `invokeExact` **không tự chuyển** return type tại call site. Nếu cần thích nghi có kiểm soát, xem xét `invoke(...)` hoặc `asType(...)`, kèm các quy tắc chuyển đổi tương ứng.

## 7. Checked exception: vì sao invokeExact khai báo throws Throwable?

`MethodHandle.invokeExact(...)` và `MethodHandle.invoke(...)` là các phương thức signature-polymorphic. Trong khai báo API, chúng có `throws Throwable`, bất kể method đích cụ thể khai báo loại checked exception nào.

Điểm đặc biệt: **`MethodType` chỉ chứa kiểu trả về và kiểu tham số**, không chứa danh sách checked exceptions như `throws IOException` hoặc `throws InvalidInputException`. Vì vậy compiler không suy được `throws` của method đích chỉ từ biến `MethodHandle`.

Nếu phương thức bao có dạng:

~~~java
static String call(MethodHandle handle, String input) throws Throwable {
    return (String) handle.invokeExact(input);
}
~~~

thì mọi caller của `call` phải xử lý hoặc khai báo `Throwable` theo luật checked exception của Java. Đây là chữ ký API của `invokeExact`, **không có nghĩa method đích đã tự động tạo ra một lớp wrapper kiểu `Throwable`**.

Trong thư viện sản phẩm, có thể đặt ranh giới xử lý lỗi riêng để tránh làm lộ `throws Throwable` ra một public API vốn chỉ cần khai báo exception cụ thể.

### Mẫu adapter có hợp đồng lỗi rõ ràng

Giả sử thư viện chỉ chấp nhận một handle có kiểu `(String)String` và muốn chuyển đúng loại checked exception `InvalidInputException`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;

static String normalizeWithHandle(MethodHandle handle, String input)
        throws InvalidInputException {

    MethodType required = MethodType.methodType(
            String.class, String.class);

    if (!handle.type().equals(required)) {
        throw new IllegalArgumentException(
                "Expected " + required + ", got " + handle.type());
    }

    try {
        return (String) handle.invokeExact(input);
    } catch (InvalidInputException ex) {
        // Giữ nguyên ngoại lệ nghiệp vụ.
        throw ex;
    } catch (RuntimeException | Error ex) {
        // Giữ nguyên lỗi unchecked / Error.
        throw ex;
    } catch (Throwable unexpected) {
        // Bảo vệ hợp đồng public API nếu handle ném checked Throwable khác.
        throw new IllegalStateException(
                "Unexpected checked exception from handle", unexpected);
    }
}
~~~

Đây là mẫu lựa chọn chính sách cho **một hợp đồng cụ thể**; thư viện có thể chọn cách biểu diễn lỗi khác. Điều đáng chú ý:

1. Kiểm tra `handle.type()` trước khi gọi giúp tách lỗi chữ ký ra khỏi lỗi nghiệp vụ.
2. `InvalidInputException` được ném lại **trực tiếp**.
3. `RuntimeException` và `Error` không bị biến thành lỗi cấu hình.
4. Một checked `Throwable` khác được giữ ở cause chain khi chuyển thành `IllegalStateException`.

Đừng bắt `Throwable` rồi bỏ qua, hoặc bao mọi loại lỗi vào một exception chung, vì sẽ mất khả năng chẩn đoán. Mã này cũng không thể suy ra mọi checked exception mà handle tùy ý có thể ném: phải dựa vào hợp đồng do phía cung cấp handle cam kết.

## 8. Khi sử dụng invoke thay vì invokeExact

`MethodHandle.invoke(...)` có khả năng thích nghi các kiểu tại call site khi phép chuyển đổi được cho phép. Nhưng điều đó **không đổi quy tắc bọc ngoại lệ nghiệp vụ**.

~~~java
// handle.type() = (String)String
Object result = handle.invoke("valid");
~~~

Ví dụ này có thể làm việc vì `String` là một kiểu tham chiếu có thể chuyển sang `Object`. Trường hợp tương tự dùng `invokeExact`, call site return type `Object` không khớp chính xác.

Khi gọi `invoke(...)`, có hai nguồn lỗi cần phân biệt:

- **Thích nghi kiểu thất bại:** chẳng hạn đối số có kiểu tham chiếu không thể cast sang kiểu tham số yêu cầu; lỗi có thể xuất hiện trước target.
- **Target ném exception:** exception từ method đích vẫn truyền ra trực tiếp như với `invokeExact`.

`invokeWithArguments(...)` cũng là một API gọi handle với quy tắc thích nghi và kiểm tra đối số riêng. Không nên dựa vào một thử nghiệm của `invokeExact` để suy mọi lỗi khi dùng `invokeWithArguments`; tuy vậy, bản thân cơ chế gọi này cũng không có quy tắc bắt buộc bọc exception target thành `InvocationTargetException`.

Trong codebase có yêu cầu bảo đảm kiểu mạnh, `invokeExact` thường giúp phát hiện mismatch rõ ràng hơn. Lựa chọn giữa các phương thức gọi phụ thuộc use case, không nên xem một API là công cụ “bỏ qua” cơ chế kiểm soát kiểu của JDK.

## 9. Khi một MethodHandle là chuỗi adapter, exception có thể đến từ nhiều nơi

MethodHandle không nhất thiết trỏ trực tiếp tới một Java method. Nó có thể là handle được tạo bởi `asType`, `filterArguments`, `filterReturnValue`, `guardWithTest`, `catchException` hoặc các tổ hợp hợp lệ khác.

Điều này làm việc chẩn đoán cần chính xác hơn:

~~~text
invokeExact
   |
   v
adapter chuyển kiểu đối số
   |
   v
filter kiểm tra / biến đổi dữ liệu
   |
   v
target nghiệp vụ
   |
   v
filter chuyển đổi kết quả
~~~

Một exception có thể đến từ adapter trước target, từ chính target, hoặc từ filter sau target. Tất cả đều có thể thoát ra theo cơ chế của method handle mà không cần wrapper `InvocationTargetException`. Vì vậy, câu “ngoại lệ đi ra trực tiếp” không tự nó chứng minh **method đích cuối cùng** đã ném lỗi; cần biết cấu trúc handle và giai đoạn phát sinh.

### Chủ động bắt exception bằng catchException

`MethodHandles.catchException(...)` là một combinator dùng để **thiết kế hành vi xử lý lỗi** cho handle. Ví dụ xử lý riêng `InvalidInputException` và trả giá trị dự phòng:

~~~java
// Thêm hai method sau vào lớp ExceptionPropagationDemo ở phần 3.
public static String recover(
        InvalidInputException error, String originalInput) {
    return "<invalid>";
}

static void runWithRecovery() throws Throwable {
    MethodHandles.Lookup lookup = MethodHandles.lookup();

    MethodHandle target = lookup.findStatic(
            ExceptionPropagationDemo.class,
            "normalize",
            MethodType.methodType(String.class, String.class));

    MethodHandle handler = lookup.findStatic(
            ExceptionPropagationDemo.class,
            "recover",
            MethodType.methodType(
                    String.class,
                    InvalidInputException.class,
                    String.class));

    MethodHandle recovered = MethodHandles.catchException(
            target, InvalidInputException.class, handler);

    String result = (String) recovered.invokeExact(" ");
    System.out.println(result); // <invalid>
}
~~~

Đoạn code này bổ sung hai method `recover` và `runWithRecovery` vào lớp `ExceptionPropagationDemo` đã khai báo ở phần 3; các import cần thiết đã có trong ví dụ đó. Gọi `runWithRecovery();` từ `main` để quan sát kết quả. Mẫu handler của `catchException` nhận exception làm đối số đầu, tiếp theo là các tham số tương ứng mà combinator chuyển cho handler.

Bộ xử lý trên cố ý biến một exception cụ thể thành kết quả `"<invalid>"`. Đây là lựa chọn ứng dụng, khác hẳn `Method.invoke` mặc định tự bọc mọi exception target vào `InvocationTargetException`.

## 10. Đối chiếu stack trace và cause chain

Khi chẩn đoán, nên ghi nhận loại exception, vị trí gọi và cause chain:

~~~java
static void printThrowable(Throwable error) {
    for (Throwable current = error;
            current != null;
            current = current.getCause()) {
        System.out.println(
                current.getClass().getName() + ": " + current.getMessage());
    }
}
~~~

Với `Method.invoke(...)`, exception phía ngoài thường là `InvocationTargetException` và `getCause()` dẫn tới lỗi đích. Với `MethodHandle.invokeExact(...)`, exception phía ngoài trực tiếp là lỗi đang thoát ra từ target hoặc adapter, trừ khi mã ứng dụng tự tạo wrapper.

Không nên dựa vào **số lượng frame stack trace** hay thứ tự các frame nội bộ JVM để xác định tuyệt đối đường gọi: đó không phải hợp đồng ổn định giữa các bản JDK, cấu hình JIT và triển khai của MethodHandle. Hãy dựa vào loại exception, cause chain và bối cảnh của thao tác.

Khi một exception được chủ động ném lại qua các tầng, nó có thể vẫn mang cause chain của các tầng trước. Việc “MethodHandle không tự bọc lỗi trong `InvocationTargetException`” không có nghĩa mọi exception trả về đều phải có `getCause() == null`.

## 11. Bài kiểm chứng âm: lỗi không đến từ method đích

Một bài test hữu ích cần phân biệt lỗi chữ ký với lỗi target. Dùng handle trỏ tới `normalize(String): String`:

~~~java
MethodHandle handle = MethodHandles.lookup().findStatic(
        ExceptionPropagationDemo.class,
        "normalize",
        MethodType.methodType(String.class, String.class));
~~~

**Kiểm chứng A — Target ném checked exception**

~~~java
try {
    String value = (String) handle.invokeExact(" ");
    System.out.println(value);
} catch (InvalidInputException expected) {
    System.out.println("target: " + expected.getClass().getSimpleName());
}
~~~

Kỳ vọng: `InvalidInputException` đi ra trực tiếp từ target.

**Kiểm chứng B — Call site sai kiểu trả về**

~~~java
try {
    Object value = (Object) handle.invokeExact("ok");
    System.out.println(value);
} catch (java.lang.invoke.WrongMethodTypeException expected) {
    System.out.println("call site mismatch");
}
~~~

Kỳ vọng: `WrongMethodTypeException` xuất hiện vì return type tại call site là `Object`, nhưng handle trả về `String`. Target không cần chạy để lỗi này xảy ra.

**Kiểm chứng C — Reflection tới target lỗi**

~~~java
Method method = ExceptionPropagationDemo.class.getMethod(
        "normalize", String.class);

try {
    method.invoke(null, " ");
} catch (InvocationTargetException expected) {
    System.out.println("reflection wrapper");
    System.out.println(
            expected.getCause().getClass().getSimpleName());
}
~~~

Kỳ vọng: wrapper `InvocationTargetException`, cause là `InvalidInputException`.

**Kiểm chứng D — Reflection lỗi cách gọi**

~~~java
try {
    method.invoke(null, 123); // normalize chỉ nhận String.
} catch (IllegalArgumentException expected) {
    System.out.println("reflection argument mismatch");
}
~~~

Kỳ vọng: lỗi đối số của `Method.invoke`, không phải `InvocationTargetException` do target ném.

Các ví dụ A–D được viết để đặt trong cùng lớp hoặc context có quyền truy cập `InvalidInputException` và các import của chương trình ở phần 3. Mỗi kịch bản có mục tiêu chẩn đoán riêng.

## 12. Bảng xử lý lỗi khi chuyển từ Method.invoke sang MethodHandle

| Mã đang dùng reflection | Khi chuyển sang MethodHandle | Lý do |
| --- | --- | --- |
| `catch (InvocationTargetException ex) { throw ex.getCause(); }` | Bắt trực tiếp loại exception cần xử lý; có thể để exception đi ra nếu API cho phép | Handle không tạo wrapper này mặc định. |
| Bắt `IllegalAccessException` quanh `Method.invoke` | Xử lý `IllegalAccessException` khi `Lookup.findStatic/findVirtual` không có quyền | Quyền truy cập thường được kiểm tra khi tạo handle. |
| Gặp `IllegalArgumentException` do truyền sai đối số reflection | Kiểm tra `MethodType`, `handle.type()`, call-site type và lỗi thích nghi | Cơ chế kiểm tra kiểu của handle khác reflection. |
| Truyền tiếp `InvocationTargetException` như lỗi nghiệp vụ | Giữ nguyên exception gốc và cause chain khi thiết kế API mới | Người gọi không nên phải unwrap wrapper không còn xuất hiện. |
| Ghi log mọi lỗi dưới tên “Invocation failed” | Phân loại lookup, adaptation, target exception | Giúp báo đúng nguyên nhân và giảm thời gian chẩn đoán. |
| Bắt mọi `Throwable` rồi chuyển thành `RuntimeException` | Bắt chính xác loại nghiệp vụ, truyền tiếp runtime exception và `Error` | Tránh làm mất ý nghĩa checked exception và lỗi hệ thống. |

Khi viết adapter để tương thích với public API cũ, cần quyết định rõ **hợp đồng ngoại lệ** nào phải được giữ nguyên. Có thể public API cũ vẫn khai báo `InvocationTargetException` vì tương thích nhị phân hoặc nguồn; nếu vậy, việc chủ động tạo wrapper là **quyết định của lớp adapter**, phải được ghi rõ, không nên hiểu là hành vi tự có của MethodHandle.

## 13. Những nhầm lẫn thường gặp

### “Handle ném InvalidInputException vì nó bị cast từ InvocationTargetException”

Sai. Đối với một lời gọi trực tiếp qua `invokeExact`, method handle không thực hiện bước bọc rồi tự unwrap `InvocationTargetException`. Nó truyền ngoại lệ đang được ném ra từ method/adapter theo hợp đồng của phương thức gọi.

### “Chỉ checked exception mới bị Method.invoke bọc”

Sai. Khi **method đích** ném unchecked exception hoặc `Error`, `Method.invoke` cũng bọc lỗi đích trong `InvocationTargetException` theo hợp đồng của nó. Phân biệt exception sinh từ cơ chế reflection trước khi vào target.

### “MethodType biết các throws của method đích”

Sai. `MethodType` chỉ chứa return type và parameter types. `throws` của `invokeExact` được khai báo ở mức `Throwable`; nó không suy ra danh sách checked exceptions từ phương thức nghiệp vụ.

### “WrongMethodTypeException chính là lỗi do target ném”

Không thể kết luận như vậy. Đây thường là dấu hiệu kiểu tại call site không khớp `MethodHandle.type()`. Nếu chính target chủ động ném ngoại lệ cùng loại, cần dựa vào stack trace/bối cảnh để phân biệt.

### “Không thấy InvocationTargetException nghĩa là target chắc chắn đã chạy”

Sai. Một lỗi của adapter hoặc kiểm tra kiểu cũng có thể đi ra trực tiếp từ handle mà target chưa được gọi.

### “Bắt Throwable là cách tốt nhất để an toàn”

Bắt rộng có thể cần ở ranh giới thích nghi đặc biệt, nhưng không nên nuốt `Error` hay xóa mất exception gốc. Một API public ổn định cần mô tả các loại lỗi có ý nghĩa và giữ nguyên cause chain.

## 14. Bài thực hành và câu hỏi tự đánh giá

1. Thay `InvalidInputException` bằng `IllegalStateException` trong `normalize`. Quan sát `Method.invoke` tạo `InvocationTargetException` còn `invokeExact` trả trực tiếp `IllegalStateException`.
2. Thêm một phương thức `static String failWithError(String input)` ném `AssertionError`. Gọi bằng hai cơ chế và ghi nhận sự khác nhau, đồng thời phân biệt `Error` với lỗi thích nghi kiểu.
3. Đổi kiểu trả về tại call site của `invokeExact` từ `String` sang `Object`, giữ nguyên tham số. Giải thích tại sao có `WrongMethodTypeException`.
4. Dùng `handle.invoke("ok")` gán cho biến `Object`. So sánh với `invokeExact` khi cùng call site return type.
5. Viết adapter `normalizeWithHandle` có `throws InvalidInputException`, giữ nguyên exception nghiệp vụ nhưng thông báo riêng khi `handle.type()` không khớp kỳ vọng.
6. Viết thử `catchException` để thay giá trị trả về cho một exception cụ thể. Nêu tại sao đây là xử lý lỗi **chủ động** và không phải wrapper mặc định.
7. Khi chuyển mã từ `Method.invoke` sang MethodHandle, tại sao bỏ câu lệnh `catch (InvocationTargetException)` là chưa đủ nếu vẫn cần phân loại lỗi lookup và conversion?

Các câu hỏi để tự trả lời:

- `InvocationTargetException` được tạo ở đâu trong đường gọi reflection?
- `getCause()` và `getTargetException()` phục vụ mục đích gì?
- Khi một method handle ném trực tiếp `IOException`, có nhất thiết xảy ra một exception wrapper ẩn mà ứng dụng không thấy không?
- Vì sao `invokeExact` khai báo `throws Throwable` dù `MethodType` của handle chỉ cho biết `(String)String`?
- Khi adapter ném `ClassCastException` trước khi target chạy, ghi log “business method failed” có chính xác không?
- Nếu method đích tự ném `InvocationTargetException`, tại sao vẫn có thể thấy ngoại lệ ấy trên đường gọi MethodHandle?

## 15. Ghi nhớ

- **`Method.invoke(...)`** bọc exception do phương thức đích ném trong **`InvocationTargetException`**; lấy nguyên nhân qua `getCause()`.
- **`MethodHandle.invokeExact(...)` và `MethodHandle.invoke(...)`** truyền exception từ target **trực tiếp**, không tự động tạo wrapper `InvocationTargetException`.
- **`MethodType` không chứa danh sách `throws`**; các lệnh gọi handle khai báo `throws Throwable`, nên tầng API thư viện cần thiết kế chính sách bắt/truyền lỗi rõ ràng.
- **Phân biệt lỗi lookup, lỗi call site/adapter và lỗi do target ném** trước khi đưa ra thông báo chẩn đoán.
- **Adapter và `catchException` có thể cố ý thay đổi luồng lỗi**, nhưng đó là hành vi do ứng dụng cấu hình, không làm thay đổi hợp đồng mặc định của lời gọi MethodHandle.

Khi kiểm chứng trên JDK đang dùng, hãy thực hiện các phép thử đối chiếu cùng một method đích qua `Method.invoke` và `invokeExact`, ghi lại exception type và cause chain, rồi đánh giá chính xác ở giai đoạn nào lỗi được tạo ra.
