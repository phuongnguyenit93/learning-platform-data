# Tạo proxy bằng `Proxy.newProxyInstance` trong Java

`Proxy.newProxyInstance` là API của `java.lang.reflect.Proxy` dùng để **tạo một đối tượng proxy tại runtime**, triển khai một hoặc nhiều interface đã chỉ định và chuyển các lời gọi phương thức trên đối tượng đó đến một `InvocationHandler`. Đây là cách tạo *JDK dynamic proxy* có sẵn trong Java, không cần tự viết một lớp wrapper cho từng implementation.

Mục tiêu của bài: hiểu chính xác ba tham số của `newProxyInstance`, luồng lời gọi qua handler, cách tạo proxy chạy được trên Java 17+, cách trả giá trị/lan truyền ngoại lệ và những giới hạn cần kiểm soát khi áp dụng thực tế.

## 1. Khi nào cần tạo proxy?

Giả sử ứng dụng có interface `Greeter` và một implementation thật. Nhiều đối tượng cần gọi `greet`, nhưng bạn muốn ghi log trước/sau lời gọi, đo thời gian, kiểm tra quyền hoặc thống kê số lần gọi. Cách gọi trực tiếp sẽ chạy thẳng vào đối tượng thật:

```text
caller ──greet("An")──> Greeter implementation
```

Nếu caller nhận **proxy có cùng interface**, bạn có thể đặt xử lý chung ở giữa:

```text
caller (biết interface Greeter)
      │ gọi greet("An")
      ▼
dynamic proxy (implements Greeter)
      │ chuyển thông tin lời gọi
      ▼
InvocationHandler.invoke(proxy, method, args)
      │ trước lời gọi: log / kiểm tra / đo đạc
      │ tùy thiết kế: method.invoke(target, args)
      │ sau lời gọi: xử lý kết quả / ngoại lệ
      ▼
kết quả hoặc ngoại lệ quay về caller
```

Caller vẫn viết `service.greet("An")` như với một đối tượng `Greeter` bình thường. Điểm khác nằm ở **đối tượng được truyền cho caller**: đó là proxy, và handler được thực thi khi có lời gọi qua proxy.

Điều quan trọng: proxy **không bắt buộc** phải chuyển tiếp tới một đối tượng thật. Handler cũng có thể trả kết quả trực tiếp, lấy dữ liệu từ nơi khác hoặc từ chối lời gọi. Mô hình *proxy bọc target* chỉ là trường hợp thông dụng, dễ hiểu nhất.

## 2. Chữ ký và ý nghĩa của ba tham số

```java
public static Object newProxyInstance(
        ClassLoader loader,
        Class<?>[] interfaces,
        InvocationHandler h)
```

| Tham số | Vai trò | Chọn như thế nào? |
| --- | --- | --- |
| `loader` | Class loader dùng để định nghĩa lớp proxy được tạo tại runtime | Thường sử dụng `Greeter.class.getClassLoader()`; loader phải nhìn thấy các interface cần proxy |
| `interfaces` | Danh sách các interface mà proxy sẽ triển khai | Ví dụ `new Class<?>[] {Greeter.class}`; có thể nhiều interface nếu đáp ứng các ràng buộc của JDK |
| `h` | Đối tượng `InvocationHandler` xử lý các lời gọi lên proxy | Thường là lambda hoặc class cài đặt phương thức `invoke` |

Phương thức **trả về `Object`**, vì danh sách interface chỉ được xác định từ tham số tại runtime. Người gọi thường ép kiểu về interface đã biết:

```java
Greeter proxy = (Greeter) Proxy.newProxyInstance(
        Greeter.class.getClassLoader(),
        new Class<?>[] {Greeter.class},
        handler);
```

Đoạn trên giả định `Greeter` và `handler` đã được khai báo; chương trình chạy đầy đủ ở mục 4.

### Phân biệt proxy với đối tượng đích

- `proxy instanceof Greeter` là `true` nếu `Greeter.class` nằm trong danh sách interface được triển khai.
- `proxy` **không phải** một instance của lớp implementation `BasicGreeter`; ép `(BasicGreeter) proxy` sẽ thất bại.
- Proxy thực thi lời gọi trên **interface**. `Proxy.newProxyInstance` không tạo subclass của một lớp Java thông thường. Nếu cần proxy lớp cụ thể, phải dùng chiến lược khác có hỗ trợ việc đó.
- `Proxy.isProxyClass(proxy.getClass())` giúp xác định lớp của đối tượng được tạo bằng cơ chế JDK proxy. `Proxy.getInvocationHandler(proxy)` trả lại handler tương ứng, nhưng đòi hỏi đối tượng đầu vào thực sự là proxy.

Đây cũng là lý do API proxy thường được sử dụng cùng **lập trình hướng interface**: caller phụ thuộc contract `Greeter`, không phụ thuộc vào implementation bên dưới.

## 3. `InvocationHandler` nhận gì khi có lời gọi?

Interface `InvocationHandler` có một phương thức trừu tượng:

```java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
```

| Tham số của `invoke` | Ý nghĩa |
| --- | --- |
| `proxy` | Chính đối tượng proxy đang nhận lời gọi; **không** phải target |
| `method` | Metadata `java.lang.reflect.Method` mô tả phương thức được gọi từ interface (hoặc một trong ba phương thức `Object` đặc biệt) |
| `args` | Các đối số của lần gọi, theo thứ tự; có thể là `null` khi phương thức không có tham số |

Handler có thể nhìn `method.getName()`, `method.getParameterTypes()`, annotation và các metadata khác để quyết định thực hiện hành động nào. Không nên dựa **chỉ** vào tên phương thức nếu interface có overload.

Giá trị handler trả về sẽ thành kết quả của lời gọi trên proxy. Nếu kiểu trả về là primitive như `int`, handler phải trả wrapper phù hợp như `Integer` để Java unbox; trả `null` cho kiểu primitive sẽ dẫn đến `NullPointerException`. Với phương thức `void`, handler nên trả `null`; caller không nhận một giá trị nào.

**Tránh vòng lặp vô hạn:** bên trong `invoke`, gọi lại chính phương thức trên `proxy` sẽ lại kích hoạt handler. Nếu muốn chuyển tiếp đến implementation thật, hãy gọi trên `target` (một đối tượng khác với proxy).

## 4. Ví dụ Java 17+ đầy đủ: tạo proxy, log và chuyển tiếp tới target

Lưu chương trình sau thành file **`ProxyDemo.java`**. Ví dụ dùng một interface `Greeter`, implementation `BasicGreeter` và handler vừa log vừa chuyển tiếp lời gọi.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ProxyDemo {
    public interface Greeter {
        String greet(String name);
        int count();
    }

    public static class BasicGreeter implements Greeter {
        private int calls;

        @Override
        public String greet(String name) {
            calls++;
            return "Xin chào, " + name + "!";
        }

        @Override
        public int count() {
            return calls;
        }
    }

    public static void main(String[] args) {
        Greeter real = new BasicGreeter();

        InvocationHandler handler = (proxy, method, passedArgs) -> {
            // Ba phương thức Object này cũng đi qua handler.
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreeterProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == passedArgs[0];
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            System.out.println("Trước: " + method.getName());
            try {
                // Gọi implementation thật, không gọi lại proxy.
                Object result = method.invoke(real, passedArgs);
                System.out.println("Sau: " + method.getName());
                return result;
            } catch (InvocationTargetException exception) {
                // Giữ lại nguyên nhân thật từ phương thức được gọi.
                throw exception.getCause();
            }
        };

        Greeter proxy = (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[] {Greeter.class},
                handler);

        System.out.println(proxy.greet("An"));
        System.out.println("Đếm: " + proxy.count());
        System.out.println(proxy.toString());
        System.out.println("Tự bằng chính mình: " + proxy.equals(proxy));
        System.out.println("Có phải proxy: "
                + Proxy.isProxyClass(proxy.getClass()));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ProxyDemo.java
java ProxyDemo
```

Kết quả chuẩn:

```text
Trước: greet
Sau: greet
Xin chào, An!
Trước: count
Sau: count
Đếm: 1
GreeterProxy
Tự bằng chính mình: true
Có phải proxy: true
```

**Điều xảy ra khi chạy:**

1. `real` là một `BasicGreeter` thực sự và giữ state `calls`.
2. `newProxyInstance` tạo một đối tượng triển khai interface `Greeter`, kết nối đối tượng đó với `handler`.
3. `proxy.greet("An")` được Java chuyển đến `handler.invoke(proxy, method, passedArgs)`. `method.getName()` là `"greet"` và `passedArgs[0]` là `"An"`.
4. Handler in dòng "Trước", gọi `method.invoke(real, passedArgs)`; `BasicGreeter.greet` tăng `calls` và trả chuỗi. Handler in "Sau" rồi trả cùng kết quả cho caller.
5. `proxy.count()` tiếp tục đi qua handler; lần này `passedArgs` là `null` vì `count()` không nhận tham số. Lời gọi `method.invoke(real, passedArgs)` vẫn hợp lệ trong trường hợp này.
6. `toString()`, `equals(Object)` cũng đi vào handler nhưng được tách riêng để có ngữ nghĩa rõ ràng. `hashCode()` được xử lý tương tự bằng identity hash code, nhất quán với phép so sánh identity trong ví dụ.

`InvocationTargetException` là vỏ ngoại lệ mà Reflection dùng khi code ở target ném lỗi. Đoạn `catch` trả lại `getCause()` để proxy lan truyền nguyên nhân thực thay vì vô tình để caller nhận wrapper không được khai báo.

Lưu ý rằng dòng "Sau" trong ví dụ **chỉ in khi target thành công**. Nếu cần đo đạc hoặc log bất kể thành công/thất bại, hãy dùng `try/finally` và phân biệt riêng trạng thái lỗi; không biến lỗi thật thành kết quả thành công.

## 5. Quy trình tạo proxy trong dự án

Khi áp dụng `newProxyInstance` vào code thực tế, có thể làm theo quy trình:

1. **Xác định interface contract** mà caller đang sử dụng, ví dụ `Greeter` hoặc `Repository`. Kiểm tra target thực sự triển khai contract đó nếu bạn định delegate.
2. **Chọn class loader** có thể nhìn thấy interface. Dùng loader của chính interface là lựa chọn tốt cho ví dụ cùng module; khi chạy với plugin hoặc nhiều class loader, phải bảo đảm khả năng nhìn thấy từng interface.
3. **Xây dựng handler** có hành vi rõ: pre-processing, chọn target, delegate, post-processing, xử lý ngoại lệ, quy tắc cho `equals`/`hashCode`/`toString`.
4. **Tạo proxy một lần tại điểm cấu hình** rồi truyền cho caller bằng interface. Đừng tạo proxy mới cho mỗi lời gọi nếu không có lý do cụ thể.
5. **Kiểm thử hành vi thông qua reference proxy**: thành công, ngoại lệ, phương thức không tham số, overload, kiểu trả về, phương thức `Object` và các luồng đồng thời nếu có state chia sẻ.

Một proxy có thể triển khai **nhiều interface** bằng cách truyền thêm các `Class<?>` tương ứng trong mảng, miễn là các interface thỏa các giới hạn của JDK. Tuy nhiên caller phải chọn đúng interface để ép kiểu và bạn vẫn cần thiết kế logic dispatch cho các phương thức có cùng chữ ký.

## 6. Các tình huống thực tế và điều proxy không tự làm

| Mục đích | Handler cần thực hiện | Lưu ý |
| --- | --- | --- |
| Ghi log | Log tên phương thức, đầu vào được phép ghi, kết quả hoặc lỗi | Tránh log mật khẩu, token và dữ liệu nhạy cảm |
| Đo thời gian | Ghi mốc trước khi delegate, đo trong `finally` | Phân biệt thời gian thực thi và thời gian chờ I/O |
| Kiểm tra quyền | Xác minh quyền rồi cho phép hoặc từ chối lời gọi | Phải có contract rõ cho lỗi từ chối |
| Transaction/cross-cutting logic | Bắt đầu, hoàn tất hoặc rollback theo chính sách | Cần quy tắc ngoại lệ, propagation và đồng bộ trạng thái |
| Adapter/client | Dựa trên `Method` và args để gửi tới remote service | Proxy không tự tạo network client hay serializer |

`newProxyInstance` chỉ cung cấp **hạ tầng chuyển lời gọi**. Nó không tự cài logging, authorization, transaction, retry, caching hay serialization. Tất cả hành vi đó đến từ `InvocationHandler` hoặc những thành phần được handler sử dụng.

Cần phân biệt với `java.net.Proxy`: lớp đó mô tả proxy mạng (ví dụ SOCKS/HTTP), **không liên quan tới việc tạo JDK dynamic proxy bằng Reflection**.

## 7. Những giới hạn và lỗi thường gặp

### 7.1. Phải là interface và phải nhìn thấy qua class loader

Mảng `interfaces` phải chứa các interface hợp lệ, không phải class thông thường, kiểu primitive, hidden interface hay sealed interface. Không truyền trùng cùng một `Class<?>`; interface phải nhìn thấy được bằng tên qua loader đã chọn. Những tổ hợp interface có các phương thức xung đột về kiểu trả về, hoặc interface không public thuộc các package/module không tương thích, cũng có thể khiến `newProxyInstance` ném `IllegalArgumentException`.

Với named module (JPMS), quyền truy cập và vị trí của lớp proxy phụ thuộc khả năng truy cập các interface. Không nên giả định rằng tên lớp proxy sinh ra là cố định hay constructor của lớp proxy đó có thể được truy cập trực tiếp. Dùng `newProxyInstance` để tạo instance.

### 7.2. Handler phải xử lý `Object` methods

JDK proxy chuyển cả `equals(Object)`, `hashCode()` và `toString()` đến handler. `method.getDeclaringClass()` của ba phương thức này là `Object.class`.

Nếu delegate mù quáng bằng `method.invoke(real, args)`, `proxy.equals(proxy)` có thể thành `real.equals(proxy)` và trả `false` ngay cả khi bạn so sánh proxy với chính nó. Nếu handler gọi `proxy.toString()` để ghi log cho chính lời gọi `toString()`, nó còn có thể lặp đệ quy.

Chọn chính sách equality rõ ràng: dùng identity của proxy (như ví dụ), hoặc thiết kế value equality phù hợp với abstraction và bảo đảm `equals` nhất quán với `hashCode`.

### 7.3. Ngoại lệ và kiểu trả về

- `Method.invoke(target, args)` bọc lỗi phát sinh từ target trong `InvocationTargetException`. Delegate đúng cách thường cần giải bọc `getCause()`.
- Handler có thể ném unchecked exception. Với **checked exception** không tương thích với `throws` của method thuộc interface, proxy sẽ bọc nó trong `UndeclaredThrowableException`. Vì vậy không thể tùy ý ném checked exception từ handler rồi mong caller nhận nguyên trạng.
- Nếu handler trả sai kiểu so với kiểu trả về đã khai báo, lời gọi qua proxy có thể ném `ClassCastException`; với kiểu primitive mà handler trả `null`, sẽ ném `NullPointerException`.
- Nếu muốn xử lý mọi kết thúc, kể cả khi target ném ngoại lệ, đặt cleanup và ghi metric trong `finally`; không nuốt ngoại lệ trừ khi contract cho phép.

### 7.4. Phương thức `default` và interface trùng chữ ký

Phương thức `default` của interface cũng có thể được chuyển đến handler. Trên Java 17+, khi muốn gọi trực tiếp phần thân default method của một proxy interface từ handler, có thể dùng `InvocationHandler.invokeDefault(proxy, method, args)` sau khi đã kiểm tra `method.isDefault()` và các điều kiện hợp lệ. Đây là API có từ Java 16; không phải mọi lời gọi default method tự bỏ qua handler.

Khi proxy triển khai nhiều interface có cùng tên và danh sách tham số, handler có thể nhận `Method` gắn với interface xuất hiện trước trong mảng interface, bất kể caller gọi qua reference interface nào. Do đó, thứ tự interface và quy tắc xử lý phương thức trùng chữ ký cần được cân nhắc.

### 7.5. Lời gọi trực tiếp và self-invocation không đi qua proxy

Chỉ những lời gọi **thực sự đi qua đối tượng proxy** mới được handler chặn. Nếu code gọi `real.greet("An")`, handler không chạy. Tương tự, nếu một method trong target gọi một method khác trên `this`, lời gọi nội bộ này không tự quay lại proxy. Đây là nguồn gốc của các lỗi khó thấy khi dùng interceptor cho transaction, cache hoặc authorization.

### 7.6. Chi phí hiệu năng, concurrency và input không tin cậy

Dynamic proxy phát sinh chi phí dispatch/Reflection và có thể thêm allocation hoặc logic phụ. Không nên khẳng định luôn chậm một mức cố định; hãy đo trong tình huống thật và tránh tạo proxy hoặc truy tìm metadata lặp đi lặp lại không cần thiết.

Nếu cùng handler/target có state chia sẻ và nhiều thread gọi proxy đồng thời, code handler cần tuân thủ quy tắc thread safety tương ứng. Proxy không tự làm cho counter, cache hay transaction state trở nên an toàn.

Không dùng tên interface/lớp/hành động nhận từ nguồn không tin cậy để tự do khởi tạo hoặc gọi method; hãy giới hạn contract cho phép, kiểm tra dữ liệu đầu vào và quyền thực thi ở điểm thích hợp.

## 8. Khi nào dùng JDK dynamic proxy, khi nào dùng cách khác?

**Ưu tiên `Proxy.newProxyInstance`** khi caller đã làm việc qua interface, và bạn cần hành vi chung xung quanh các lời gọi tại runtime. Điển hình là logging, metrics, remote adapter, invocation routing và nhiều cơ chế interceptor trong thư viện/framework.

**Ưu tiên decorator viết tay** nếu chỉ có một vài interface/lớp ổn định, logic bọc đơn giản và bạn muốn code tường minh, dễ theo dõi bằng IDE, dễ kiểm tra kiểu lúc biên dịch.

**Cân nhắc công cụ proxy bằng subclass hoặc bytecode** nếu contract bắt buộc dựa trên class cụ thể. Giải pháp đó có quy tắc riêng về final method, constructor và access; không thể dùng trực tiếp cùng cơ chế của `java.lang.reflect.Proxy`.

Một lưu ý trong thiết kế: dù proxy có thể dùng để cài cross-cutting concerns, việc dùng dynamic proxy **không tự động biến mọi lời gọi trong hệ thống thành lời gọi được intercept**. Phạm vi luôn phụ thuộc nơi bạn trao đối tượng proxy cho caller.

## 9. Checklist và tự kiểm tra

Trước khi đưa một JDK dynamic proxy vào ứng dụng, hãy xác nhận:

- Interface và class loader phù hợp; caller giữ reference đến **proxy**.
- Handler xác định đúng phương thức và xử lý `args == null`.
- Các giá trị trả về đúng kiểu, đặc biệt với primitive hoặc `void`.
- Ngoại lệ phát sinh từ target được lan truyền theo contract của interface.
- `equals`, `hashCode` và `toString` không có hành vi bất ngờ hay recursion.
- Lời gọi nội bộ trên target, state chia sẻ và performance đã được tính đến.

**Câu hỏi luyện tập:**

1. Vì sao `newProxyInstance` nhận danh sách interface mà không nhận lớp implementation để làm superclass?
2. Nếu thay `proxy.greet("An")` bằng `real.greet("An")` thì output thay đổi ra sao?
3. Tại sao `invoke` cần trả `Integer` khi interface có phương thức trả `int`?
4. Điều gì có thể xảy ra nếu handler gọi `proxy.toString()` khi đang xử lý `toString()`?
5. Tại sao cần `exception.getCause()` sau `Method.invoke` và khi nào proxy tạo `UndeclaredThrowableException`?
6. Vì sao test phải bao gồm cả lỗi, overload, self-invocation và tình huống concurrent?

## Tham khảo API chuẩn

- [`Proxy.newProxyInstance` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html)
- [`InvocationHandler.invoke` và `InvocationHandler.invokeDefault` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html)

Bài này tập trung vào **cách tạo và sử dụng proxy qua `newProxyInstance`**: chọn đúng interface/loader/handler, hiểu dispatch và kiểm soát hành vi. Các kỹ thuật proxy lớp cụ thể, AOP framework và bytecode generation là những chủ đề liên quan nhưng có cơ chế khác.