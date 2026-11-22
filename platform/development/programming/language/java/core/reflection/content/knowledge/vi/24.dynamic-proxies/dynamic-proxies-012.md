# Nhiều interface có phương thức trùng chữ ký trong Java Dynamic Proxy

## 1. Vấn đề cần hiểu

Một dynamic proxy tạo bằng `java.lang.reflect.Proxy` có thể triển khai **nhiều interface** cùng lúc. Điều gì xảy ra nếu các interface ấy khai báo phương thức có **cùng tên và cùng danh sách kiểu tham số**?

Ví dụ, `Readable` và `Auditable` đều có `String status()`:

~~~java
interface Readable {
    String status();
}
interface Auditable {
    String status();
}
~~~

Về phía người gọi, có thể ép cùng một proxy sang `Readable` hoặc `Auditable` rồi gọi `status()`. Tuy nhiên, class proxy được tạo chỉ có cơ chế thực thi lời gọi chung; nó **không nhận được thông tin người gọi đã ép đối tượng sang interface nào**. Vì vậy, `InvocationHandler.invoke(proxy, method, args)` không thể dựa vào kiểu biến tại chỗ gọi để biết “lời gọi đến từ Readable hay Auditable”.

Điểm cần nắm vững:

- **Thứ tự interface khi tạo proxy có ý nghĩa.** Với các phương thức trùng tên và cùng tham số, proxy ưu tiên `Method` từ interface xuất hiện sớm nhất trong mảng interface (kể cả phương thức interface ấy kế thừa), trong trường hợp phương thức được gộp cùng kiểu trả về.
- **Kiểu trả về phải tương thích** thì proxy mới tạo được. Các kiểu trả về tham chiếu có thể hiệp biến; các kiểu primitive hoặc `void` phải trùng khớp.
- **Checked exception phải hợp lệ với tất cả khai báo liên quan**; nếu không, proxy có thể bọc ngoại lệ bằng `UndeclaredThrowableException`.
- **Default method không tự chạy** chỉ vì interface có thân hàm. Handler muốn dùng một default implementation phải lựa chọn và gọi có chủ đích.
- Một số trường hợp kiểu trả về khác nhau cần phân biệt thêm theo chữ ký ở cấp JVM; không suy diễn máy móc rằng mọi lời gọi trùng tên đều chuyển tới cùng một `Method`.

## 2. “Trùng chữ ký” nghĩa là gì?

Ở mức mã nguồn Java, **method signature** gồm tên phương thức và kiểu tham số (kèm tham số kiểu của phương thức nếu có); **kiểu trả về và `throws` không dùng để overload**. Vì vậy:

| Interface A | Interface B | Quan hệ |
| --- | --- | --- |
| `String name()` | `String name()` | Cùng tên, tham số và kiểu trả về |
| `Number id()` | `Integer id()` | Cùng tên/tham số, kiểu trả về hiệp biến |
| `void send(String s)` | `void send(String s) throws IOException` | Cùng tên/tham số, khác `throws` |
| `void send(String s)` | `void send(int n)` | **Khác** chữ ký vì kiểu tham số khác |
| `int count()` | `long count()` | Cùng tên/tham số nhưng kiểu trả về primitive không tương thích |

Một proxy có thể phục vụ các lời gọi từ nhiều interface. Song phép kiểm tra hợp lệ khi tạo proxy và cách phân phối vào handler tuân theo quy tắc riêng của `Proxy`; nó không hoàn toàn giống việc tự viết `class implements A, B` trong mã nguồn.

## 3. Thứ tự interface quyết định `Method` được thấy trong handler

Tạo proxy bằng:

~~~java
Object proxy = Proxy.newProxyInstance(
        loader,
        new Class<?>[] { Readable.class, Auditable.class },
        handler);
~~~

Khi cả hai interface có đúng `String status()`, lời gọi qua `((Readable) proxy).status()` và `((Auditable) proxy).status()` đều chuyển tới handler cùng **phương thức đại diện**: `Readable.status()` vì `Readable` đứng trước. Đổi thứ tự mảng thì `Auditable.status()` được chọn. Thứ tự không thay đổi kiểu static của lời gọi tại compiler; nó thay đổi cách proxy sinh ra thực thi và cách chọn `Method`.

Một chi tiết dễ bỏ qua: nếu interface đứng trước **kế thừa** phương thức từ interface cha, `method.getDeclaringClass()` có thể trả về **interface cha thực sự khai báo**, thay vì interface trực tiếp được đưa vào mảng. Do đó, `getDeclaringClass()` không bảo đảm luôn là một phần tử của mảng interface.

### Ví dụ chạy được: đổi thứ tự và ép qua hai interface

Tạo file `DuplicateMethodDemo.java`:

~~~java
import java.lang.reflect.Proxy;

public class DuplicateMethodDemo {
    public interface Readable { String status(); }
    public interface Auditable { String status(); }

    static Object makeProxy(Class<?> first, Class<?> second) {
        return Proxy.newProxyInstance(
                DuplicateMethodDemo.class.getClassLoader(),
                new Class<?>[] { first, second },
                (proxy, method, args) -> {
                    if (method.getName().equals("status")) {
                        System.out.println("Method from: "
                                + method.getDeclaringClass().getSimpleName());
                        return "READY";
                    }
                    throw new UnsupportedOperationException(method.toString());
                });
    }

    public static void main(String[] args) {
        Object first = makeProxy(Readable.class, Auditable.class);
        System.out.println(((Readable) first).status());
        System.out.println(((Auditable) first).status());

        Object reversed = makeProxy(Auditable.class, Readable.class);
        System.out.println(((Readable) reversed).status());
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac DuplicateMethodDemo.java
java DuplicateMethodDemo
~~~

Kết quả:

~~~text
Method from: Readable
READY
Method from: Readable
READY
Method from: Auditable
READY
~~~

Hai lời gọi đầu dùng các kiểu tham chiếu khác nhau nhưng handler vẫn thấy `Readable`. Lần thứ ba cho thấy **thứ tự đăng ký interface** làm thay đổi `Method` được chuyển vào handler. **Không phân nhánh nghiệp vụ theo kiểu được ép tại phía caller**, bởi handler không có thông tin đó.

## 4. Quy tắc tương thích của kiểu trả về

Với các phương thức cùng tên và cùng danh sách tham số, `Proxy.newProxyInstance` yêu cầu kiểu trả về đáp ứng điều kiện:

1. Nếu **bất kỳ** kiểu trả về nào là primitive hoặc `void`, **tất cả phải đúng kiểu đó**. `int` và `long`, `void` và `Object` không thể gộp; không có tự boxing hay widening để hợp thức hóa proxy.
2. Nếu tất cả là **kiểu tham chiếu**, phải tồn tại một kiểu trả về có thể gán cho **tất cả** kiểu trả về còn lại. Chẳng hạn `Integer` là subtype của `Number` nên `Number code()` và `Integer code()` tương thích. Hai kiểu cuối `String` và `Integer` không có quan hệ subtype phù hợp nên không tương thích.
3. Khi không thỏa điều kiện, lời gọi **tạo proxy** ném `IllegalArgumentException`; không cần chờ đến lần gọi phương thức.

**Điểm tinh tế với covariant return:** `Number code()` và `Integer code()` cùng tên/tham số theo cách nhìn Java, nhưng có **descriptor JVM khác nhau vì descriptor chứa kiểu trả về**. Class proxy có thể sinh các phương thức/bridge cần thiết; trong Java 17, handler có thể thấy `Method` có kiểu trả về `Number` khi gọi qua interface rộng và `Integer` khi gọi qua interface hẹp. Vì vậy, quy tắc “interface đầu tiên thắng” không có nghĩa `method.getReturnType()` luôn giống nhau khi có covariant return. Kiểm tra hành vi cụ thể và luôn trả về đối tượng tương thích với các contract liên quan.

**Giá trị handler trả về:** proxy sẽ kiểm tra/ép sang kiểu trả về tương ứng. Trả sai kiểu tham chiếu gây `ClassCastException`; trả `null` cho kiểu trả về primitive có thể gây `NullPointerException` lúc unboxing. `void` thường cần handler trả về `null` (giá trị trả về của handler sẽ bị bỏ qua).

## 5. `throws` khác nhau: tập checked exception chung mới an toàn

Hai interface có thể cùng khai báo `read()` nhưng một interface `throws IOException`, interface kia `throws SQLException`. Việc **tạo proxy vẫn hợp lệ**, vì `throws` không phải kiểu trả về và không quyết định chữ ký runtime. Tuy nhiên, handler **không được tự do phát ra mọi checked exception từ interface đứng trước**.

Quy tắc: để checked exception đi qua proxy mà không bị bọc, kiểu ngoại lệ đó phải tương thích với ít nhất một exception được khai báo trong **mỗi** phương thức trùng chữ ký thuộc các interface liên quan. Nếu một interface khai báo `Exception` và interface khác khai báo `IOException`, `IOException` có thể đi qua; `SQLException` không thỏa interface thứ hai. Nếu một khai báo `IOException` và một khai báo `SQLException`, một `IOException` thông thường không thể đi thẳng qua hai contract.

Nếu handler ném checked exception không hợp lệ với toàn bộ hợp đồng, proxy bọc nó trong **`java.lang.reflect.UndeclaredThrowableException`**, là unchecked exception. Cần dùng `getUndeclaredThrowable()` hoặc `getCause()` để xem nguyên nhân.

`RuntimeException` và `Error` không chịu giới hạn khai báo `throws` giống checked exception; chúng có thể truyền ra ngoài theo cơ chế unchecked thông thường. Hãy phân biệt lỗi ném ra từ handler với lỗi tạo proxy (thường `IllegalArgumentException`).

## 6. Nhiều default method trùng tên: chọn triển khai một cách tường minh

Java 8 bổ sung **default method** có phần thân bên trong interface. Khi dynamic proxy triển khai hai interface cùng có `default String label()`, việc gọi `label()` **vẫn đi qua `InvocationHandler.invoke`**; proxy không tự động chọn nội dung của interface đầu hoặc thứ hai để chạy.

Từ Java 16, `InvocationHandler.invokeDefault(proxy, method, args...)` cho phép handler gọi một default method cụ thể. Có thể lấy `Method` từ interface mình muốn, ví dụ `Second.class.getMethod("label")`, rồi gọi `invokeDefault`. Đây là quyết định nghiệp vụ riêng với quy tắc `Method` nhận vào handler. Method để gọi phải là default method hợp lệ, có thể truy cập, được khai báo trong proxy interface hoặc được kế thừa mà vẫn có thể chọn theo quy tắc JVM. Khi một interface override default method trong tương lai, lời gọi `invokeDefault` đến implementation cũ có thể không còn hợp lệ.

Trường hợp interface thứ nhất khai báo một phương thức abstract và interface thứ hai khai báo default method cùng tên/tham số, cũng **không suy ra** proxy sẽ tự chạy default method. Handler cần dispatch rõ ràng.

## 7. Ví dụ đầy đủ: kiểu trả về, checked exception và default method (Java 17+)

Tạo file `ProxyEdgeCases.java`:

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.sql.SQLException;

public class ProxyEdgeCases {
    public interface Wide { Number code(); }
    public interface Narrow { Integer code(); }
    public interface BadA { int amount(); }
    public interface BadB { long amount(); }
    public interface Disk { String read() throws IOException; }
    public interface Database { String read() throws SQLException; }
    public interface First {
        default String label() { return "first"; }
    }
    public interface Second {
        default String label() { return "second"; }
    }

    public static void main(String[] args) throws Throwable {
        Object covariant = Proxy.newProxyInstance(
                ProxyEdgeCases.class.getClassLoader(),
                new Class<?>[] { Wide.class, Narrow.class },
                (proxy, method, callArgs) -> {
                    System.out.println("Return token: "
                            + method.getReturnType().getSimpleName());
                    return 42;
                });
        System.out.println(((Wide) covariant).code());
        System.out.println(((Narrow) covariant).code());

        try {
            Proxy.newProxyInstance(
                    ProxyEdgeCases.class.getClassLoader(),
                    new Class<?>[] { BadA.class, BadB.class },
                    (proxy, method, callArgs) -> 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Primitive conflict: IllegalArgumentException");
        }

        Object checked = Proxy.newProxyInstance(
                ProxyEdgeCases.class.getClassLoader(),
                new Class<?>[] { Disk.class, Database.class },
                (proxy, method, callArgs) -> { throw new IOException("failed"); });
        try {
            ((Disk) checked).read();
        } catch (UndeclaredThrowableException ex) {
            System.out.println("Wrapped checked: "
                    + ex.getUndeclaredThrowable().getClass().getSimpleName());
        }

        Object defaults = Proxy.newProxyInstance(
                ProxyEdgeCases.class.getClassLoader(),
                new Class<?>[] { First.class, Second.class },
                (proxy, method, callArgs) -> {
                    System.out.println("Default Method from: "
                            + method.getDeclaringClass().getSimpleName());
                    Method chosen = Second.class.getMethod("label");
                    return InvocationHandler.invokeDefault(proxy, chosen);
                });
        System.out.println(((First) defaults).label());
        System.out.println(((Second) defaults).label());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ProxyEdgeCases.java
java ProxyEdgeCases
~~~

Kết quả xác minh trên OpenJDK 21 với `javac --release 17`:

~~~text
Return token: Number
42
Return token: Integer
42
Primitive conflict: IllegalArgumentException
Wrapped checked: IOException
Default Method from: First
second
Default Method from: First
second
~~~

Giải thích:

- `Wide.code()` và `Narrow.code()` hợp lệ nhờ kiểu trả về hiệp biến. Hai lần gọi nhận `Method` với kiểu trả về tương ứng `Number` và `Integer`; handler trả `Integer(42)` phù hợp cả hai.
- Hai khai báo `amount()` khác kiểu trả về primitive (`int`/`long`) bị từ chối **ngay khi tạo proxy**.
- Handler ném `IOException` trong khi proxy cũng công khai `Database.read() throws SQLException` nên exception bị bọc dù lời gọi thực hiện qua `Disk`.
- Cả hai lần gọi `label()` handler đều nhận `Method` từ `First` vì `First` được đăng ký trước. Nhưng handler chọn **thực thi default implementation của `Second`**, nên kết quả đều là `second`.

Lưu ý kết quả trên là kết quả của **đúng ví dụ này**; sửa thứ tự interface, kiểu trả về, chữ ký, hoặc logic handler sẽ thay đổi kết quả.

## 8. Ba phương thức của `Object` có ưu tiên riêng

`equals(Object)`, `hashCode()` và `toString()` là ba public, non-final method của `Object` được dynamic proxy chuyển đến `InvocationHandler`. Nếu một proxy interface tình cờ khai báo lại chúng với chữ ký tương ứng, `Method` được truyền cho handler vẫn có `getDeclaringClass() == Object.class`, vì các phương thức này được coi là **ưu tiên trước mọi interface** khi chọn `Method`.

Không áp dụng suy luận này cho mọi method của `Object` (ví dụ `getClass()` là final, không được handler override theo cơ chế trên). Handler nên xử lý ba phương thức cơ bản rõ ràng để tránh kết quả `toString()` bất ngờ hoặc vòng lặp đệ quy khi log:

~~~java
// Fragment bên trong InvocationHandler.invoke(proxy, method, args)
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "toString" -> "DynamicServiceProxy";
        case "hashCode" -> System.identityHashCode(proxy);
        case "equals" -> proxy == args[0];
        default -> throw new UnsupportedOperationException(method.toString());
    };
}
~~~

Đây là **fragment**, không phải chương trình độc lập. Đặc biệt, tránh gọi `proxy.toString()` ngay trong nhánh xử lý `toString` của chính handler vì sẽ lại đi vào handler.

## 9. Generic, method erasure và giới hạn của `Method`

Tại runtime, dynamic proxy làm việc với `Method` và kiểu tham số/kiểu trả về đã được JVM biểu diễn. Ví dụ, tham số kiểu `List<String>` và `List<Integer>` có cùng raw type `List` sau erasure; `Method.getParameterTypes()` thông thường cho biết `List.class`, không kiểm chứng từng phần tử lúc chạy.

`Method.getGenericParameterTypes()` có thể đọc thông tin **khai báo generic** còn lưu trong class file, nhưng thông tin đó **không có nghĩa** lời gọi đến proxy được JVM tự kiểm tra sâu thành phần tử `String` hay `Integer`. Khi hai interface có khai báo generic khác nhau nhưng erasure trùng, không được định tuyến nghiệp vụ chỉ dựa trên kiểu generic mong đợi ở caller.

Một vài interface generic sau chuyên biệt hóa có thể xuất hiện **bridge method** do compiler sinh, với đặc điểm `Method.isBridge()` hoặc `isSynthetic()`. Khi chẩn đoán nên quan sát cả `method.getName()`, `getParameterTypes()`, `getReturnType()` và `getDeclaringClass()`, thay vì giả định rằng tên method là định danh duy nhất.

Đầu vào nhận từ bên ngoài vẫn phải được validate nội dung; dynamic proxy không thay thế cơ chế kiểm tra dữ liệu kiểu generic.

## 10. Thiết kế handler ổn định khi kết hợp nhiều interface

Để tránh nhầm lẫn và hành vi lệ thuộc thứ tự một cách vô tình:

1. **Rà soát interface trước khi tạo proxy:** lấy các method public kế thừa và khai báo, nhóm theo tên + danh sách tham số đã erasure; so sánh kiểu trả về, checked exceptions, default implementation và ý nghĩa nghiệp vụ.
2. **Ghi rõ thứ tự interface** truyền vào `Proxy.newProxyInstance`. Đừng lấy thứ tự tùy ý từ `HashSet` hoặc một collection không bảo đảm thứ tự; đây là đầu vào có ý nghĩa.
3. **Hợp nhất nghiệp vụ của method trùng chữ ký** nếu chúng phải dùng chung một hành vi. Nếu hai interface có hai ý nghĩa khác nhau nhưng cùng chữ ký, hãy đổi thiết kế (đổi tên/phân tách proxy) vì handler không thể biết kiểu tham chiếu của caller để phân biệt.
4. **Phân nhánh theo contract đã định nghĩa**, không mặc định dùng `method.getDeclaringClass()` làm “interface người gọi”. Khi có covariant returns hoặc bridge, kiểm tra thêm descriptor/kiểu trả về.
5. **Chọn default method tường minh** với `InvocationHandler.invokeDefault` nếu thật sự muốn gọi thân hàm mặc định.
6. **Chuẩn hóa xử lý exception và giá trị trả về** theo tất cả interface. Kiểm tra riêng `equals`, `hashCode`, `toString` và tránh gọi lại chính proxy một cách không kiểm soát.
7. **Bảo đảm class loader nhìn thấy tất cả interface**, interface là loại phù hợp để tạo proxy và khai báo không có xung đột return type; thay đổi thứ tự mảng có thể tạo một proxy class khác.

Khi cần hai implementation khác nhau cho cùng tên/tham số dựa trên một ngữ cảnh nghiệp vụ, truyền **ngữ cảnh tường minh** (tham số, strategy, adapter) hoặc tạo hai proxy/entry point riêng. Ép một proxy duy nhất qua interface khác nhau không chuyển được thông tin ấy vào `invoke`.

## 11. Bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Handler luôn thấy interface A dù gọi qua B | A đứng trước trong mảng interface và method trùng | Đọc lại thứ tự đăng ký; không suy đoán kiểu caller |
| `IllegalArgumentException` lúc tạo proxy | Return type xung đột hoặc vi phạm điều kiện tạo proxy | Kiểm tra phương thức trùng tên/tham số, return type và visibility |
| `UndeclaredThrowableException` khi gọi method | Checked exception từ handler không hợp lệ với tất cả `throws` | Xem `getUndeclaredThrowable()`, thống nhất hợp đồng lỗi |
| Default method không chạy | Mọi lời gọi proxy đi qua handler | Dùng `InvocationHandler.invokeDefault` với `Method` hợp lệ |
| `method.getReturnType()` khác nhau giữa hai lần gọi | Các method hiệp biến có descriptor return khác | Phân biệt trường hợp này với method cùng return type |
| `ClassCastException` hoặc `NullPointerException` sau `invoke` | Handler trả kết quả không tương thích hoặc `null` cho primitive | Trả đúng kiểu và kiểm tra nullability |
| Handler lặp vô hạn khi log | Handler lại gọi method trên chính proxy | Không gọi `proxy.toString()` từ nhánh `toString` |

## 12. Câu hỏi tự kiểm tra

1. Nếu `A` và `B` đều có `String name()`, proxy được tạo với `[A.class, B.class]`, rồi gọi qua biến kiểu `B`, `Method` thuộc đâu? **`A`** (hoặc interface cha thực sự khai báo method mà `A` kế thừa), vì A đứng trước.
2. Đảo thành `[B.class, A.class]` ảnh hưởng gì? **Có thể đổi `Method` đại diện** cho các method cùng descriptor; không thay đổi nội dung method của từng interface.
3. `Number value()` và `Integer value()` có tạo proxy cùng lúc được không? **Có**, vì `Integer` là subtype của `Number`. Nhưng đừng giả định `Method.getReturnType()` giống nhau ở mọi lời gọi.
4. `int value()` và `long value()` có tạo proxy cùng lúc được không? **Không**; primitive return phải đúng cùng kiểu.
5. Vì sao `throws IOException` và `throws SQLException` có thể dẫn tới `UndeclaredThrowableException`? Vì checked exception từ handler phải hợp lệ với **mọi contract** method trùng; `IOException` không nằm trong `throws SQLException`.
6. Để chạy body của `Second.default label()` khi handler nhận `Method` thuộc `First`, cần gì? **Lấy `Second.class.getMethod("label")` và gọi `InvocationHandler.invokeDefault(proxy, chosen)`** khi method có thể được chọn hợp lệ.
7. Có thể nhìn `method.getDeclaringClass()` để biết caller đã ép proxy sang A hay B không? **Không**. Class proxy không truyền thông tin kiểu tham chiếu của caller vào handler.

## Tài liệu tham khảo

- [Oracle JDK 17 — Proxy: Methods Duplicated in Multiple Proxy Interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Oracle JDK 17 — InvocationHandler và invokeDefault](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)

**Ghi nhớ:** Khi nhiều interface có method trùng tên/tham số, cần xét **thứ tự interface, kiểu trả về, checked exceptions và default methods** như bốn khía cạnh độc lập. `Method` nhận trong handler không phải thông tin về kiểu biến của caller. Thiết kế contract rõ ràng trước khi viết dispatch sẽ tránh phần lớn lỗi khó chẩn đoán.