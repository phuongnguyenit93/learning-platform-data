# `equals`, `hashCode`, `toString` trong Java dynamic proxy: hợp đồng cần định nghĩa

## 1. Vì sao ba phương thức này cần được xử lý riêng?

Dynamic proxy của JDK là một đối tượng được tạo lúc chạy bằng `java.lang.reflect.Proxy` và triển khai một hay nhiều **interface**. Khi mã gọi phương thức của interface, proxy chuyển lời gọi đến `InvocationHandler.invoke(proxy, method, args)` để handler quyết định hành vi.

Có một chi tiết dễ bỏ sót: **`equals(Object)`, `hashCode()` và `toString()` cũng được proxy chuyển đến `InvocationHandler`**, dù chúng được khai báo trong `java.lang.Object` và không được liệt kê trong interface nghiệp vụ. Vì thế, handler phải chủ động xác định đối tượng proxy được xem là bằng đối tượng nào, mã băm của nó ra sao và cách biểu diễn chuỗi của nó. Nếu chỉ xử lý phương thức nghiệp vụ rồi mặc định các phương thức còn lại thuộc về đối tượng đích, chương trình có thể lỗi lúc chạy hoặc tạo ra hành vi không nhất quán trong `HashMap`, `HashSet`, log và kiểm thử.

Phân biệt ba đối tượng có thể xuất hiện:

- **Proxy**: đối tượng mà bên gọi nắm giữ và gọi `proxy.equals(...)`, `proxy.hashCode()`, `proxy.toString()`.
- **Handler**: đối tượng triển khai `InvocationHandler`; nhận lời gọi từ proxy. Bản thân handler có `equals`/`hashCode`/`toString` riêng, nhưng đó **không tự động** là hợp đồng của proxy.
- **Target/delegate** (nếu có): đối tượng thật mà handler chuyển tiếp nghiệp vụ tới. Hợp đồng của target không tự động biến thành hợp đồng của proxy.

Không phải mọi dynamic proxy đều có target: một handler có thể tự tạo kết quả, gửi lời gọi RPC, thực hiện logging hoặc truy cập tài nguyên bên ngoài.

## 2. JVM chuyển ba lời gọi Object vào handler như thế nào?

Với một proxy từ `Proxy.newProxyInstance(...)`:

| Lời gọi của bên dùng | `method.getDeclaringClass()` trong handler | `args` | Kiểu trả về cần cung cấp |
| --- | --- | --- | --- |
| `proxy.equals(other)` | `Object.class` | Một phần tử: `other`, có thể `null` | `Boolean` để proxy trả `boolean` |
| `proxy.hashCode()` | `Object.class` | `null` vì không có tham số | `Integer` để proxy trả `int` |
| `proxy.toString()` | `Object.class` | `null` vì không có tham số | `String` |

Điều này đúng cả khi một interface khai báo lại chữ ký phù hợp của ba phương thức nói trên: `Method` được chuyển vào handler vẫn có declaring class là `Object.class`. Vì vậy, kiểm tra `method.getDeclaringClass() == Object.class` rồi phân nhánh theo tên là cách dễ hiểu để phân biệt ba lời gọi này với phương thức nghiệp vụ. Một phương thức overload như `equals(String)` **không** thay thế `equals(Object)` và phải được nhận diện theo chữ ký riêng nếu interface thực sự có khai báo.

Proxy cũng kế thừa một số phương thức `Object` khác. Các phương thức `final` như `getClass()`, `wait()`, `notify()` không được handler chặn theo cách này; không nên khẳng định *mọi* lời gọi phương thức `Object` đều qua `invoke`.

**Kiểu trả về phải đúng.** `InvocationHandler.invoke` có kiểu kết quả `Object`, nhưng proxy sẽ kiểm tra/ép kết quả theo kiểu trả về của phương thức được gọi. Trả `null` cho `equals` hoặc `hashCode` (kiểu nguyên thủy) gây `NullPointerException` khi unbox; trả sai kiểu có thể gây `ClassCastException`. `toString` có thể trả `null` về mặt kiểu, nhưng giá trị chuỗi có ý nghĩa thường hữu ích hơn. Nếu handler ném checked exception không được khai báo trong chữ ký, proxy có thể bọc nó trong `UndeclaredThrowableException`.

## 3. Hợp đồng của từng phương thức

### `equals(Object)` — định nghĩa thế nào là hai proxy bằng nhau

Hợp đồng cơ bản của `Object.equals` là:

1. **Phản xạ:** `x.equals(x)` là `true`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` đều đúng thì `x.equals(z)` phải đúng.
4. **Nhất quán:** nếu thông tin dùng để so sánh không đổi, gọi lại cho cùng kết quả.
5. **Với `null`:** `x.equals(null)` là `false`.

Hai chiến lược thường dùng:

- **Bằng nhau theo định danh proxy (identity semantics):** chỉ `proxy == other` mới bằng nhau. Hai proxy khác nhau được xem là khác nhau, kể cả nếu chúng cùng chuyển lời gọi tới một target. Đây là chính sách đơn giản và an toàn khi mỗi proxy là một đối tượng wrapper độc lập.
- **Bằng nhau theo định danh logic (logical/value semantics):** hai proxy biểu diễn cùng một thực thể nghiệp vụ/tài nguyên có thể bằng nhau nếu chúng mang cùng khóa logic ổn định. Phải định nghĩa rõ tập đối tượng được so sánh (chẳng hạn cùng kiểu handler và cùng loại dịch vụ), tránh chỉ dựa vào một chuỗi ID mà các kiểu không liên quan cũng dùng.

Không có một chính sách `equals` đúng cho mọi proxy. Phải lựa chọn theo vai trò của proxy và tài liệu hóa rõ, đặc biệt nếu API trả về nhiều proxy bọc cùng đối tượng.

### `hashCode()` — nhất quán với `equals`

Điều kiện bắt buộc: nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()`. Chiều ngược lại không bắt buộc: hai đối tượng khác nhau được phép trùng mã băm.

- Khi dùng **identity semantics**, `System.identityHashCode(proxy)` là lựa chọn phù hợp để tính mã băm trực tiếp từ định danh đối tượng mà không gọi lại `proxy.hashCode()`.
- Khi dùng **logical/value semantics**, mã băm nên tính từ **đúng các khóa ổn định dùng trong `equals`**, ví dụ `Objects.hash(serviceType, resourceId)` hoặc `key.hashCode()` nếu `key` đã bao gồm mọi thành phần nhận dạng.
- Các thuộc tính dùng trong `equals`/`hashCode` không nên thay đổi khi proxy đang là khóa của `HashMap` hay phần tử của `HashSet`; nếu thay đổi, tra cứu có thể thất bại dù phần tử vẫn nằm trong cấu trúc dữ liệu.

`System.identityHashCode(proxy)` **không** phù hợp nếu hai proxy khác nhau được coi là bằng nhau theo khóa logic: chúng có thể nhận các mã băm khác nhau và vi phạm hợp đồng. Không dùng `proxy.hashCode()` ngay trong nhánh xử lý `hashCode` vì sẽ gọi ngược vào cùng handler.

### `toString()` — biểu diễn hữu ích, an toàn

`toString` nên trả về một mô tả ngắn, dễ nhận diện trong log/debug, chẳng hạn `GreeterProxy[label=A]` hoặc tên interface và ID tài nguyên phù hợp. Không có quy tắc bắt buộc rằng hai đối tượng bằng nhau phải có chuỗi giống nhau, nhưng mô tả nhất quán giúp kiểm thử và vận hành.

Không cần liệt kê toàn bộ trạng thái nội bộ, đặc biệt không in token, mật khẩu hoặc dữ liệu nhạy cảm. Tránh viết `return proxy.toString()` hoặc `String.valueOf(proxy)` ngay bên trong nhánh `toString`: chúng sẽ kích hoạt `InvocationHandler.invoke` lần nữa và dẫn tới đệ quy.

## 4. Ví dụ Java 17+: ba hợp đồng theo định danh proxy

Tạo tệp `ProxyObjectMethodsDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashSet;
import java.util.Set;

public class ProxyObjectMethodsDemo {
    public interface Greeter {
        String greet(String name);
    }

    static Greeter createGreeter(String label) {
        InvocationHandler handler = (proxy, method, args) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == args[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "GreeterProxy[label=" + label + "]";
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            if (method.getDeclaringClass() == Greeter.class
                    && method.getName().equals("greet")) {
                return "Xin chào, " + args[0];
            }

            throw new UnsupportedOperationException(method.toString());
        };

        return (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[] { Greeter.class },
                handler);
    }

    public static void main(String[] args) {
        Greeter a = createGreeter("A");
        Greeter b = createGreeter("B");

        System.out.println(a.greet("An"));
        System.out.println(a.equals(a));
        System.out.println(a.equals(b));
        System.out.println(a.equals(null));
        System.out.println(
                a.hashCode() == System.identityHashCode(a));
        System.out.println(a.toString());

        Set<Greeter> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(a);
        System.out.println(set.size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ProxyObjectMethodsDemo.java
java ProxyObjectMethodsDemo
```

Kết quả chuẩn:

```text
Xin chào, An
true
false
false
true
GreeterProxy[label=A]
2
```

Phân tích:

1. `a.greet("An")` là phương thức nghiệp vụ, được handler trả về chuỗi chào.
2. `a.equals(a)` là `true`, còn `a.equals(b)` là `false` mặc dù `a` và `b` đều triển khai `Greeter`. Hai đối tượng proxy được tạo bằng hai lần gọi factory nên có định danh khác nhau.
3. `a.equals(null)` là `false` vì một proxy không đồng nhất với `null`.
4. `a.hashCode() == System.identityHashCode(a)` là `true` theo chính sách đã cài đặt; giá trị mã băm cụ thể có thể khác nhau ở mỗi lần chạy nên ví dụ chỉ kiểm tra tính nhất quán, không in số tùy ý.
5. `a.toString()` tạo chuỗi có thể đọc trực tiếp từ thông tin `label` mà handler đã giữ, không tự gọi lại phương thức của proxy.
6. `HashSet` chỉ chứa hai proxy phân biệt dù chèn `a` hai lần. `HashSet` phụ thuộc cả `hashCode` lẫn `equals` nên đây là kiểm tra thực tế của hợp đồng.

Trong code trên, `args[0]` chỉ được đọc ở nhánh `equals` hoặc `greet`, là hai method có một tham số. Khi nhận `hashCode` hoặc `toString`, `args` là `null` và code không truy cập vào nó.

## 5. Khi proxy bọc target: không chuyển tiếp mù quáng ba phương thức

Giả sử handler chuyển nghiệp vụ đến một đối tượng `target` bằng reflection:

```java
// Minh họa bên trong InvocationHandler, chưa phải chương trình độc lập:
Object result = method.invoke(target, args);
```

Điều này chỉ thích hợp khi `method` thực sự là phương thức muốn gọi trên `target` và điều kiện truy cập/kiểu đối tượng được đáp ứng. Riêng `equals`, `hashCode`, `toString` phải có quyết định rõ ràng.

Ví dụ handler viết `return target.equals(args[0]);` cho `proxy.equals(other)` có thể khiến `proxy.equals(target)` trả `true` nhưng `target.equals(proxy)` lại trả `false`. Như vậy **vi phạm tính đối xứng**. Ngược lại, gọi `method.invoke(proxy, args)` để “trả về mặc định” sẽ kích hoạt lại cùng proxy và tạo chuỗi lời gọi đệ quy.

Nếu muốn **proxy bằng target** hoặc **hai proxy cùng bọc một target thì bằng nhau**, cần kiểm tra cả hai chiều so sánh, kiểu được chấp nhận và mã băm tương ứng. Trong nhiều hệ thống, chọn identity semantics cho proxy và công khai ID nghiệp vụ qua interface là dễ dự đoán hơn.

Một lựa chọn khác là sử dụng **khóa logic bất biến** khi tạo handler. Chẳng hạn handler chứa `record ServiceKey(String tenant, String serviceId) {}` và so sánh hai proxy hợp lệ theo hai khóa `ServiceKey`. Khi đó:

- `equals` cần kiểm tra đối tượng còn lại thuộc nhóm proxy tương thích và handler của nó có khóa tương ứng; có thể dùng `Proxy.isProxyClass(other.getClass())` rồi `Proxy.getInvocationHandler(other)` sau khi đã kiểm tra `other != null`.
- `hashCode` phải được tính từ cùng khóa; **không** tính theo định danh proxy.
- `toString` có thể hiển thị loại dịch vụ và phần ID an toàn để hỗ trợ chẩn đoán.

Việc `Proxy.getInvocationHandler(other)` lấy được handler chỉ xác nhận đối tượng là JDK dynamic proxy (hoặc có thể phát sinh lỗi theo điều kiện API), không tự chứng minh nó là cùng kiểu nghiệp vụ. Hãy kiểm tra kiểu handler/contract trước khi dùng khóa. Hai proxy được coi là bằng nhau phải chia sẻ quy tắc so sánh và mã băm cho cả hai chiều; nếu target của framework khác cũng có `equals` tùy biến, việc so sánh xuyên giữa proxy và target thường phức tạp hơn nhiều.

## 6. Những lỗi phổ biến và cách tránh

| Lỗi triển khai | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ xử lý tên method nghiệp vụ, quên `equals`/`hashCode`/`toString` | Log hoặc thêm proxy vào `HashSet` có thể ném lỗi | Tạo nhánh chuyên xử lý `Object.class` |
| Dùng `proxy.equals(other)` trong nhánh xử lý `equals` | Đệ quy qua `invoke` | Dùng `proxy == other` cho identity semantics; hoặc so khóa bất biến |
| Dùng `proxy.hashCode()` trong nhánh xử lý `hashCode` | Đệ quy qua `invoke` | Dùng `System.identityHashCode(proxy)` khi chọn identity semantics |
| Dùng `proxy.toString()` trong nhánh `toString` | Đệ quy qua `invoke` | Dựng chuỗi từ dữ liệu handler an toàn |
| `equals` so khóa logic nhưng `hashCode` dùng identity | Có thể vi phạm hợp đồng, làm sai tra cứu trên `HashMap`/`HashSet` | Dùng cùng bộ khóa cho cả hai |
| Ủy quyền thẳng `target.equals(other)` | Có thể bất đối xứng giữa target và proxy | Chọn chính sách rõ ràng và kiểm tra cả hai chiều |
| Trả `null` cho `equals`/`hashCode` | `NullPointerException` khi unbox | Trả `Boolean`/`Integer` đúng kiểu |
| Thay đổi khóa sau khi thêm proxy vào hash collection | Không còn tìm ra phần tử theo khóa cũ | Dùng khóa bất biến trong suốt vòng đời proxy |
| In target/credentials trong `toString` | Dữ liệu nhạy cảm có thể vào log | Chỉ hiển thị metadata an toàn, cần thiết |

**Đừng chỉ kiểm tra tên phương thức.** Nếu interface có overload `equals(String)` thì đây không phải `Object.equals(Object)`. Hãy kết hợp declaring class/chữ ký; điều kiện `method.getDeclaringClass() == Object.class` giải quyết đúng ba method Object đặc biệt được JDK proxy chuyển vào handler.

## 7. Nên kiểm thử hợp đồng ra sao?

Với mỗi loại proxy, tối thiểu nên kiểm tra:

- **`equals`:** `x.equals(x)`, `x.equals(null)`, hai proxy cùng/khác khóa, đối xứng khi so với proxy khác và với target nếu API cho phép.
- **`hashCode`:** các cặp bằng nhau có hash bằng nhau; giá trị ổn định khi trạng thái nhận dạng không đổi; thêm rồi tìm lại trong `HashSet`/`HashMap`.
- **`toString`:** gọi không lỗi, không đệ quy, không chứa dữ liệu nhạy cảm, chuỗi có ích khi đọc log.
- **Phân luồng handler:** ba method Object được phân biệt với method interface; test thêm interface khai báo lại `toString()` hoặc overload `equals(String)` nếu API có tình huống đó.
- **Đường lỗi:** handler không trả `null` cho method trả primitive, không nuốt ngoại lệ nghiệp vụ thành chuỗi thành công giả.

Nếu framework tạo proxy lồng nhau (proxy bọc proxy), cần xác định `equals` đang so lớp wrapper ngoài, wrapper trong hay ID nghiệp vụ; việc dựa đơn thuần vào class proxy sinh tự động hoặc tên của nó thường làm hợp đồng mong manh khi thay đổi interface hay class loader.

## 8. Tự kiểm tra

**Câu 1.** Hai đối tượng được tạo riêng bằng `Proxy.newProxyInstance` cùng trỏ đến một target có bắt buộc phải `equals` nhau không?

**Trả lời:** Không. Điều đó phụ thuộc chính sách `equals` trong handler. Với identity semantics, chúng khác nhau; với logical semantics có thể bằng nhau nếu hợp đồng được thiết kế nhất quán.

**Câu 2.** Tại sao `return proxy.hashCode()` bên trong nhánh xử lý `hashCode` là sai?

**Trả lời:** Lời gọi quay lại đúng proxy và handler, gây đệ quy. Với identity semantics, dùng `System.identityHashCode(proxy)` để tránh dispatch phản chiếu.

**Câu 3.** Có thể dùng `System.identityHashCode(proxy)` khi hai proxy khác nhau được coi là bằng nhau theo `resourceId` không?

**Trả lời:** Không nên: giá trị identity hash có thể khác nhau giữa hai proxy bằng nhau. Hash phải được tính bằng cùng dữ liệu nhận dạng ổn định đã dùng trong `equals`.

**Câu 4.** `getClass()` của proxy có đi vào `InvocationHandler.invoke` như `toString()` không?

**Trả lời:** Không. `getClass()` là phương thức `final` của `Object`; ba phương thức `equals`, `hashCode`, `toString` được JDK dynamic proxy xử lý đặc biệt.

**Ghi nhớ:** Dynamic proxy của JDK không tự cung cấp chính sách equality có nghĩa cho ứng dụng. Handler cần định nghĩa `equals`, `hashCode` và `toString` đồng bộ với cách proxy đại diện cho đối tượng/tài nguyên, rồi kiểm thử chúng qua các thao tác thường ngày như so sánh, lưu tập hợp và ghi log.