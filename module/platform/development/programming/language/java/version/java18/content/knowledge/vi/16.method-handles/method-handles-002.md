# MethodType.methodType(): khai báo kiểu trả về và thứ tự kiểu tham số

## 1. Vì sao `MethodType` cần đúng kiểu và đúng thứ tự?

Với reflection thông thường, lập trình viên có thể quen tìm một phương thức theo tên và kiểu tham số. Khi dùng `java.lang.invoke.MethodHandle`, chữ ký lời gọi còn được mô tả bằng một đối tượng `java.lang.invoke.MethodType`: nó nêu **kiểu trả về** và **danh sách kiểu tham số theo đúng thứ tự**.

Ví dụ, với phương thức:

~~~java
static String describe(int level, String message) {
    return level + ": " + message;
}
~~~

Kiểu phương thức tương ứng được tạo như sau:

~~~java
import java.lang.invoke.MethodType;

MethodType type = MethodType.methodType(
        String.class,  // kiểu TRẢ VỀ
        int.class,     // tham số thứ nhất: level
        String.class   // tham số thứ hai: message
);

System.out.println(type); // (int,String)String
~~~

Công thức cần nhớ:

~~~text
MethodType.methodType(RETURN_TYPE, PARAMETER_TYPE_1, PARAMETER_TYPE_2, ...)
                      ^             ^                 ^
                      kiểu trả về   tham số đầu tiên   tham số thứ hai
~~~

Đây không phải cú pháp khai báo một phương thức Java mới. `MethodType.methodType(...)` tạo **mô tả kiểu** để tra cứu, kiểm tra hoặc kết hợp với `MethodHandle`. Nó không chứa tên phương thức, không chứa thân phương thức và không tự thực thi mã.

Trong module Java 18, đây là kiến thức về hợp đồng `MethodHandle` còn hữu ích trên các JDK hiện đại. API `MethodType` đã tồn tại từ trước Java 18 và vẫn được hỗ trợ; bài học chỉ dùng những khả năng hiện hành.

## 2. Đọc đúng hai thành phần của MethodType

Xét khai báo:

~~~java
public static long total(String group, int amount, boolean active) {
    return active ? amount : 0L;
}
~~~

Phần khai báo kiểu của nó là:

~~~java
MethodType type = MethodType.methodType(
        long.class,
        String.class,
        int.class,
        boolean.class
);
~~~

Ta đọc lần lượt:

| Vị trí trong `methodType(...)` | Giá trị | Vai trò |
| --- | --- | --- |
| Đối số đầu tiên | `long.class` | **Kiểu trả về** của phương thức. |
| Đối số thứ hai | `String.class` | Kiểu tham số số 1: `group`. |
| Đối số thứ ba | `int.class` | Kiểu tham số số 2: `amount`. |
| Đối số thứ tư | `boolean.class` | Kiểu tham số số 3: `active`. |

Dạng rút gọn của `MethodType` là:

~~~text
(String,int,boolean)long
~~~

Phía **trong ngoặc** biểu diễn các kiểu tham số theo thứ tự khai báo; kiểu **sau ngoặc** biểu diễn kiểu trả về. Dù kết quả in ra có kiểu trả về phía cuối, lời gọi factory `methodType(...)` vẫn đặt kiểu trả về **ở đầu**.

Thứ tự tham số là một phần của kiểu. Hai mô tả sau không giống nhau:

~~~java
MethodType first = MethodType.methodType(
        long.class, String.class, int.class);

MethodType second = MethodType.methodType(
        long.class, int.class, String.class);

System.out.println(first.equals(second)); // false
~~~

Hai `MethodType` chỉ bằng nhau khi **kiểu trả về** và **toàn bộ kiểu tham số ở đúng từng vị trí** bằng nhau. Tên tham số (`group`, `amount`), tên phương thức và tên lớp khai báo không tham gia vào phép so sánh này.

## 3. Các cách gọi methodType thường dùng

Lớp `MethodType` cung cấp các overload để tạo kiểu phương thức mà không cần tự ghép một chuỗi descriptor.

| Nhu cầu | Ví dụ | Kiểu được biểu diễn |
| --- | --- | --- |
| Không có tham số | `MethodType.methodType(void.class)` | `()void` |
| Một tham số | `MethodType.methodType(String.class, int.class)` | `(int)String` |
| Nhiều tham số | `MethodType.methodType(long.class, String.class, int.class)` | `(String,int)long` |
| Danh sách kiểu dưới dạng mảng | `MethodType.methodType(String.class, new Class<?>[] {int.class, String.class})` | `(int,String)String` |
| Danh sách kiểu dưới dạng `List` | `MethodType.methodType(String.class, List.of(int.class, String.class))` | `(int,String)String` |

Đối số đầu tiên **luôn** là kiểu trả về, kể cả khi truyền tham số qua mảng hoặc `List`. Trong hai cách sau, thứ tự các phần tử của mảng/danh sách chính là thứ tự tham số:

~~~java
import java.lang.invoke.MethodType;
import java.util.List;

MethodType fromArray = MethodType.methodType(
        String.class,
        new Class<?>[] {int.class, String.class});

MethodType fromList = MethodType.methodType(
        String.class,
        List.of(int.class, String.class));

System.out.println(fromArray.equals(fromList)); // true
~~~

Hãy chọn overload dễ đọc nhất cho tình huống: vài tham số cố định thì truyền trực tiếp; dữ liệu chữ ký được thu thập động thì dùng mảng hoặc `List`.

### Phương thức không trả về kết quả

Trong Java, `void` là một kiểu trả về hợp lệ:

~~~java
static void log(String message) {
    System.out.println(message);
}
~~~

Chữ ký tương ứng là:

~~~java
MethodType loggerType = MethodType.methodType(
        void.class, String.class);

System.out.println(loggerType); // (String)void
~~~

Trường hợp **không có tham số và không có giá trị trả về**:

~~~java
MethodType noArgs = MethodType.methodType(void.class);
System.out.println(noArgs); // ()void
~~~

**`void.class` chỉ hợp lệ ở vị trí kiểu trả về**, không hợp lệ như kiểu một tham số:

~~~java
// Không hợp lệ: tham số Java không thể có kiểu void.
MethodType invalid = MethodType.methodType(String.class, void.class);
// Ném IllegalArgumentException khi tạo MethodType.
~~~

Đoạn lỗi ở trên dùng để giải thích ràng buộc; đừng đặt nó trong chương trình chạy bình thường nếu chưa bắt ngoại lệ.

## 4. Kiểu nguyên thủy, wrapper, mảng và varargs

`MethodType` làm việc với các đối tượng `Class<?>`. Cần mô tả kiểu **thật sự xuất hiện trong chữ ký Java**, không suy luận rằng boxing luôn xảy ra.

| Khai báo phương thức | MethodType đúng |
| --- | --- |
| `int plus(int a, int b)` | `methodType(int.class, int.class, int.class)` |
| `Integer plus(Integer a, Integer b)` | `methodType(Integer.class, Integer.class, Integer.class)` |
| `String[] split(String text)` | `methodType(String[].class, String.class)` |
| `void consume(byte[] payload)` | `methodType(void.class, byte[].class)` |
| `void printAll(String... parts)` | `methodType(void.class, String[].class)` |

Hai trường hợp sau **khác kiểu**, dù Java đôi khi cho phép boxing/unboxing ở lời gọi bình thường:

~~~java
MethodType primitive = MethodType.methodType(
        int.class, int.class);

MethodType boxed = MethodType.methodType(
        Integer.class, Integer.class);

System.out.println(primitive.equals(boxed)); // false
~~~

Một tham số khai báo `String... parts` có kiểu runtime là `String[]`. Vì vậy descriptor của phương thức varargs có **một tham số mảng**, không phải số lượng tùy ý các tham số `String.class`.

Tương tự, `int[].class` là kiểu mảng số nguyên; `int.class` là một số nguyên đơn. Chúng không hoán đổi vị trí cho nhau khi tìm phương thức bằng `MethodHandles.Lookup`.

## 5. Ví dụ hoàn chỉnh: findStatic và invokeExact

Ví dụ sau minh họa chuỗi thao tác thực tế: tạo `MethodType`, tìm một phương thức `static` bằng `MethodHandles.Lookup.findStatic` và gọi bằng `invokeExact`.

Tệp `MethodTypeOrderDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodTypeOrderDemo {

    public static String describe(int level, String message) {
        return level + ": " + message;
    }

    public static void main(String[] args) throws Throwable {
        // 1. Kiểu trả về đặt trước; tham số theo thứ tự (int, String).
        MethodType signature = MethodType.methodType(
                String.class, int.class, String.class);

        // 2. Lookup cần tên phương thức và MethodType khớp chữ ký.
        MethodHandle handle = MethodHandles.lookup().findStatic(
                MethodTypeOrderDemo.class,
                "describe",
                signature);

        System.out.println("type = " + handle.type());
        System.out.println("same type = " + handle.type().equals(signature));

        // 3. invokeExact đòi hỏi kiểu argument và return tại call site
        //    khớp chính xác với type của MethodHandle.
        String result = (String) handle.invokeExact(3, "ready");
        System.out.println("result = " + result);

        // 4. Đổi chỗ kiểu tham số sẽ tạo kiểu phương thức khác.
        MethodType reversed = MethodType.methodType(
                String.class, String.class, int.class);

        try {
            MethodHandles.lookup().findStatic(
                    MethodTypeOrderDemo.class, "describe", reversed);
            throw new AssertionError("Unexpected method found");
        } catch (NoSuchMethodException expected) {
            System.out.println("wrong order: NoSuchMethodException");
        }

        // 5. invokeExact cũng không tự đổi kiểu trả về String -> Object.
        try {
            Object unexpected = (Object) handle.invokeExact(3, "ready");
            System.out.println(unexpected);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong call site: WrongMethodTypeException");
        }
    }
}
~~~

Chạy:

~~~bash
javac MethodTypeOrderDemo.java
java MethodTypeOrderDemo
~~~

Kết quả kỳ vọng:

~~~text
type = (int,String)String
same type = true
result = 3: ready
wrong order: NoSuchMethodException
wrong call site: WrongMethodTypeException
~~~

Các điểm quan trọng:

1. `MethodType.methodType(String.class, int.class, String.class)` tương ứng đúng với `describe(int, String): String`.
2. `findStatic` cần **tên** phương thức, **lớp** chứa phương thức và **MethodType**. Khi thứ tự tham số khác, phương thức có chữ ký ấy không tồn tại, nên phép tra cứu có thể ném `NoSuchMethodException`.
3. `handle.type()` phản ánh kiểu của handle đã tạo. Với handle trỏ tới phương thức static ở ví dụ, nó khớp `signature`.
4. `invokeExact` dùng kiểu tại **call site**, gồm kiểu các đối số **và** kiểu trả về mà trình biên dịch suy ra. Gán kết quả kiểu `String` trực tiếp cho biến `Object` trong lời gọi `invokeExact` sẽ tạo call site yêu cầu kiểu trả về `Object`, nên không khớp handle trả về `String`.

Trong thực hành, `MethodHandle.invoke(...)` có thể áp dụng các phép thích nghi kiểu hợp lệ; `invokeExact(...)` yêu cầu khớp chính xác. Không xem `invoke` là một cơ chế tự sửa mọi chữ ký sai: phép chuyển đổi bất hợp lệ vẫn gây lỗi.

## 6. Thứ tự tham số là thứ tự phương thức khai báo, không phải thứ tự “đẹp mắt”

Giả sử có hai phương thức với tên giống nhau:

~~~java
public static String build(String code, int count) {
    return code + ":" + count;
}

public static String build(int count, String code) {
    return count + ":" + code;
}
~~~

Hai overload được phân biệt bởi **vị trí kiểu tham số**:

~~~java
MethodType stringThenInt = MethodType.methodType(
        String.class, String.class, int.class);

MethodType intThenString = MethodType.methodType(
        String.class, int.class, String.class);
~~~

Một lời gọi `findStatic(..., "build", stringThenInt)` chọn overload nhận `(String, int)`; `findStatic(..., "build", intThenString)` chọn overload nhận `(int, String)`. Cùng tên và cùng kiểu trả về vẫn chưa đủ để hai chữ ký là một.

Một lỗi thường gặp là nhìn tên biến rồi tạo danh sách theo thứ tự bảng dữ liệu, JSON field hoặc key của map. `MethodType` không biết các tên đó; chỉ danh sách **kiểu theo đúng thứ tự khai báo** mới quan trọng.

### MethodType có chứa tên tham số không?

Không. Đối tượng `MethodType` không lưu tên `code`, `count`, annotation của tham số hoặc tên phương thức. Nó chỉ lưu:

- Một `Class<?>` cho kiểu trả về.
- Một danh sách có thứ tự các `Class<?>` cho kiểu tham số.

Nếu framework cần ánh xạ tên field JSON vào vị trí đối số, đó là một bước riêng của framework trước khi dùng `MethodHandle`.

## 7. Đối với instance method, phân biệt kiểu khai báo và kiểu handle

Một điểm dễ nhầm: `Lookup.findVirtual(...)` nhận `MethodType` mô tả **tham số được khai báo trong phương thức**, **chưa thêm receiver**. Sau khi tìm được phương thức instance, `MethodHandle` trả về có receiver ở vị trí tham số đầu tiên.

Ví dụ với phương thức có sẵn `String.substring(int beginIndex, int endIndex)`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodType declaredType = MethodType.methodType(
        String.class, int.class, int.class);

MethodHandle substring = MethodHandles.lookup().findVirtual(
        String.class, "substring", declaredType);

System.out.println(declaredType);    // (int,int)String
System.out.println(substring.type()); // (String,int,int)String

String value = (String) substring.invokeExact("method", 1, 4);
System.out.println(value);           // eth
~~~

Ở `findVirtual`:

- `String.class` chỉ **lớp sở hữu phương thức**.
- `declaredType` mô tả `substring(int, int): String`.
- `substring.type()` chứa thêm tham số receiver `String` ở đầu, bởi handle cần biết sẽ gọi phương thức trên **đối tượng nào**.

Do đó, đừng khai báo `MethodType.methodType(String.class, String.class, int.class, int.class)` làm đối số của `findVirtual` cho `String.substring(int, int)`. Descriptor truyền vào lookup phải khớp **kiểu khai báo**; receiver sẽ được thể hiện ở type của handle tạo ra.

Sự phân biệt này đặc biệt quan trọng khi tạo lời gọi động trong thư viện xử lý đối tượng: thứ tự đối số khi `invokeExact` trên handle của instance method là **receiver trước, các tham số thực sau**.

## 8. Đối với constructor, kiểu trả về ở bước lookup là void

Constructor không khai báo kiểu trả về trong cú pháp Java. API `Lookup.findConstructor(...)` dùng một `MethodType` có **return type là `void.class`** để mô tả các tham số của constructor.

Ví dụ:

~~~java
public record Ticket(String code, int quantity) {}
~~~

Tìm constructor theo chữ ký:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodType constructorType = MethodType.methodType(
        void.class, String.class, int.class);

MethodHandle constructor = MethodHandles.lookup().findConstructor(
        Ticket.class, constructorType);

System.out.println(constructorType); // (String,int)void
System.out.println(constructor.type()); // (String,int)Ticket

Ticket ticket = (Ticket) constructor.invokeExact("T-01", 2);
System.out.println(ticket); // Ticket[code=T-01, quantity=2]
~~~

Điểm cần phân biệt:

- `constructorType` truyền vào `findConstructor` có return type là `void` theo hợp đồng tra cứu constructor.
- `constructor.type()` của handle sau tra cứu **trả về đối tượng mới** thuộc `Ticket`.
- Thứ tự hai tham số vẫn phải là `String.class` rồi `int.class`, đúng thứ tự constructor nhận.

Không dùng `MethodType.methodType(Ticket.class, String.class, int.class)` làm descriptor truyền trực tiếp cho `findConstructor`; chữ ký tìm constructor và chữ ký handle trả về khác nhau ở kiểu trả về.

## 9. Khám phá MethodType thay vì đoán từ chuỗi

`MethodType` cung cấp các phương thức để kiểm tra mô tả kiểu một cách có cấu trúc:

~~~java
import java.lang.invoke.MethodType;
import java.util.Arrays;

MethodType type = MethodType.methodType(
        long.class, String.class, int.class, boolean.class);

System.out.println(type.returnType() == long.class);    // true
System.out.println(type.parameterCount());              // 3
System.out.println(type.parameterType(0) == String.class); // true
System.out.println(type.parameterType(1) == int.class);    // true
System.out.println(type.parameterType(2) == boolean.class);// true

System.out.println(Arrays.toString(type.parameterArray()));
// [class java.lang.String, int, boolean]
~~~

**Chỉ số tham số bắt đầu từ 0.** `parameterType(0)` là tham số đầu tiên, **không phải kiểu trả về**. Kiểu trả về đọc riêng qua `returnType()`.

Nếu cần biểu diễn theo descriptor của JVM, có thể dùng:

~~~java
MethodType type = MethodType.methodType(
        String.class, int.class, String.class);

System.out.println(type.toMethodDescriptorString());
// (ILjava/lang/String;)Ljava/lang/String;
~~~

Ký hiệu JVM descriptor khác với dạng in người đọc dễ hiểu `(int,String)String`. Trong descriptor, `I` là `int`, `Ljava/lang/String;` là `java.lang.String`, và phần sau dấu `)` là kiểu trả về. Đây là một cách kiểm tra chữ ký khi làm việc với bytecode hoặc công cụ JVM; với logic Java thông thường, ưu tiên đọc `returnType()`, `parameterCount()` và `parameterType(i)`.

## 10. MethodType là bất biến: biến đổi kiểu tạo đối tượng kiểu mới

Một `MethodType` không được sửa tại chỗ. Các thao tác như `changeReturnType(...)` và `insertParameterTypes(...)` trả về **một mô tả kiểu mới**.

~~~java
import java.lang.invoke.MethodType;

MethodType base = MethodType.methodType(
        String.class, int.class);
// base: (int)String

MethodType differentReturn = base.changeReturnType(Object.class);
// differentReturn: (int)Object

MethodType withPrefix = base.insertParameterTypes(0, long.class);
// withPrefix: (long,int)String

System.out.println(base);            // (int)String
System.out.println(differentReturn); // (int)Object
System.out.println(withPrefix);      // (long,int)String
~~~

Điều này có ích khi xây pipeline `MethodHandle`: thư viện có thể tạo một kiểu cơ sở rồi tính ra kiểu đích cho các bộ biến đổi khác nhau. Tuy nhiên, **thay đổi mô tả kiểu chưa làm thay đổi phương thức Java mà handle đang gọi**. Khi cần chuyển một `MethodHandle` sang kiểu tương thích, phải dùng các API thích nghi handle thích hợp (ví dụ `asType(...)`) và tôn trọng các quy tắc chuyển đổi được hỗ trợ.

### Các lỗi đầu vào cần tránh

- **Kiểu trả về `null`:** `MethodType` yêu cầu một `Class<?>` hợp lệ; đầu vào `null` dẫn đến `NullPointerException`.
- **Một kiểu tham số `null`:** không hợp lệ; không thể tạo chữ ký chứa một kiểu chưa xác định.
- **`void.class` ở vị trí tham số:** không hợp lệ; `void` chỉ được phép làm kiểu trả về.
- **Thứ tự tham số đảo ngược:** tạo thành một `MethodType` hoàn toàn hợp lệ, nhưng không tìm đúng phương thức dự định nếu chữ ký không tồn tại.
- **Dùng wrapper thay primitive:** tạo mô tả khác, có thể khiến lookup không tìm thấy phương thức.

Trên JDK hiện đại, còn có giới hạn về kích thước kiểu phương thức theo ràng buộc JVM. Các API tạo `MethodType` có thể từ chối descriptor quá lớn; đây là tình huống hiếm đối với phương thức nghiệp vụ bình thường, nhưng cần lưu ý nếu framework sinh chữ ký từ dữ liệu động.

## 11. Phân biệt lỗi tìm phương thức và lỗi gọi handle

Ba thời điểm lỗi quan trọng trong luồng dùng `MethodType`:

| Thời điểm | Ví dụ | Lỗi thường gặp | Ý nghĩa |
| --- | --- | --- | --- |
| **Tạo kiểu** | `methodType(String.class, void.class)` | `IllegalArgumentException` | Mô tả kiểu vi phạm quy tắc của `MethodType`. |
| **Tìm method/constructor** | `findStatic(..., wrongType)` | `NoSuchMethodException` hoặc `IllegalAccessException` | Không có member đúng chữ ký hoặc không đủ quyền lookup. |
| **Gọi MethodHandle** | `handle.invokeExact(...)` với call site khác kiểu | `WrongMethodTypeException` | Handle tồn tại nhưng kiểu tại call site không khớp. |

Một sơ đồ ngắn:

~~~mermaid
flowchart TD
    A["Khai báo MethodType"] --> B{"Kiểu hợp lệ?"}
    B -->|Không| X["Lỗi khi tạo MethodType"]
    B -->|Có| C["Lookup theo tên + lớp + MethodType"]
    C --> D{"Tìm thấy và truy cập được?"}
    D -->|Không| Y["NoSuchMethodException hoặc IllegalAccessException"]
    D -->|Có| E["Nhận MethodHandle"]
    E --> F["Gọi invokeExact với kiểu call site"]
    F --> G{"Kiểu khớp handle.type()?"}
    G -->|Không| Z["WrongMethodTypeException"]
    G -->|Có| H["Thực thi phương thức đích"]
~~~

Ngoài các lỗi về chữ ký, mã của phương thức đích có thể tự ném exception. Khi đó vấn đề nằm ở thân phương thức, không nên tự động kết luận `MethodType` sai.

Nếu đang xây API thư viện, ghi lại `handle.type()`, `methodType.returnType()` và danh sách `parameterArray()` tại điểm lỗi để chẩn đoán. Tránh ghi dữ liệu nhạy cảm chứa trong đối số thực tế.

## 12. Tình huống thực tế: ánh xạ cấu hình động vào MethodHandle

Giả sử một bộ điều phối chỉ biết tên tác vụ `"validate"` và muốn gọi:

~~~java
public static boolean validate(String token, int retryCount) {
    return token != null && retryCount >= 0;
}
~~~

Metadata của framework phải giữ danh sách kiểu **theo thứ tự khai báo**:

~~~java
MethodType signature = MethodType.methodType(
        boolean.class, String.class, int.class);
~~~

Sau đó, framework tra cứu `validate` bằng `findStatic` trong lớp đã xác định và truyền các đối số vào đúng thứ tự. Nếu framework nhận đầu vào dưới dạng map có key `retryCount` và `token`, thứ tự lặp của map **không quyết định** thứ tự đối số method handle. Nó cần một bước mapping có quy tắc từ tên trường vào **vị trí 0, 1, ...** tương ứng chữ ký đích.

Cách này áp dụng cho mapper, RPC dispatcher và plugin được phép truy cập bằng API công khai. Với named module, `MethodHandles.Lookup` vẫn tuân thủ quy tắc kiểm soát truy cập của JDK; `MethodType` chỉ mô tả kiểu chứ không cấp thêm quyền vào member private.

## 13. Bài thực hành tự kiểm chứng

Thực hiện bằng một JDK hiện đại, chỉ sử dụng API `java.lang.invoke` công khai.

1. Viết phương thức `static double scale(int count, double factor)`. Tạo `MethodType` đúng rồi dùng `findStatic` và `invokeExact` để nhận kết quả.
2. Đổi chỗ `int.class` và `double.class` trong `methodType(...)`. Ghi nhận kết quả khi tìm phương thức; giải thích vì sao **cả hai kiểu đều hợp lệ** nhưng chỉ một kiểu tương ứng phương thức đã viết.
3. Thay `double.class` bằng `Double.class` ở vị trí tham số thứ hai. Ghi lại khác biệt giữa kiểu primitive và wrapper.
4. Tạo `MethodType.methodType(void.class)` và `MethodType.methodType(int.class)`. So sánh ý nghĩa của kiểu trả về và số tham số.
5. Tìm một instance method bằng `findVirtual`, sau đó so sánh descriptor truyền vào lookup với `handle.type()` trả về. Xác định vị trí receiver.
6. Tìm constructor đơn giản bằng `findConstructor`. So sánh kiểu trả về của `MethodType` truyền vào với kiểu trả về của handle được tạo.
7. Dùng `returnType()`, `parameterCount()`, `parameterType(i)` và `toMethodDescriptorString()` để ghi lại cùng một chữ ký dưới các cách biểu diễn.

### Câu hỏi tự đánh giá

- Vì sao kiểu trả về đứng **đầu** danh sách đối số `methodType(...)` nhưng lại đứng **sau ngoặc** khi in `MethodType`?
- Hai phương thức có cùng kiểu trả về và cùng tập kiểu tham số, nhưng khác thứ tự tham số, có cùng `MethodType` không?
- `MethodType.methodType(void.class, String.class)` mô tả điều gì?
- Tại sao `MethodType.methodType(Integer.class, Integer.class)` không giống `MethodType.methodType(int.class, int.class)`?
- Vì sao `findVirtual` không nhận thêm receiver vào `MethodType` đầu vào, trong khi `handle.type()` của kết quả lại chứa receiver?
- `NoSuchMethodException` và `WrongMethodTypeException` xuất hiện ở hai giai đoạn khác nhau như thế nào?

## 14. Ghi nhớ

**`MethodType.methodType(...)` đặt kiểu trả về trước, rồi liệt kê kiểu tham số đúng thứ tự khai báo.** `MethodType` mô tả một chữ ký mạnh về kiểu, không chứa tên phương thức và không thực thi mã.

Khi dùng `MethodHandles.Lookup`, phải truyền đúng kiểu trả về, đúng kiểu và thứ tự tham số; chú ý `int.class` khác `Integer.class`. Với instance method và constructor, phân biệt **kiểu được dùng khi lookup** và **`handle.type()` sau lookup**. Khi gọi `invokeExact`, cả kiểu đối số và kiểu trả về tại call site phải khớp chính xác với handle.
