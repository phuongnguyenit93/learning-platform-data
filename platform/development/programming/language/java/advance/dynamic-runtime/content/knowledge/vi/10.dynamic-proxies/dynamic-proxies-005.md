# 10.5. Ủy quyền lời gọi đúng đối tượng và tránh đệ quy vô hạn qua dynamic proxy

Trong Java, **dynamic proxy** của `java.lang.reflect.Proxy` tạo ra một đối tượng triển khai một hoặc nhiều interface. Mỗi khi client gọi một phương thức qua đối tượng proxy, JVM chuyển lời gọi tới `InvocationHandler.invoke(proxy, method, args)`. Handler có thể ghi log, đo thời gian, kiểm tra quyền hoặc chuyển tiếp lời gọi tới **đối tượng triển khai thật (target/delegate)**.

Sai lầm phổ biến nhất là nhầm hai đối tượng:

- `proxy` trong tham số `InvocationHandler.invoke` là **chính đối tượng proxy đã nhận lời gọi**, không phải backend.
- `target` là **đối tượng thật** do ứng dụng giữ riêng để thực hiện nghiệp vụ.

Khi handler dùng `method.invoke(proxy, args)` thay vì `method.invoke(target, args)`, lời gọi quay trở lại **cùng handler**, rồi handler lại gọi proxy và tiếp tục không có điểm dừng. Kết quả có thể là đệ quy vô hạn, `StackOverflowError`, hoặc những lớp exception phức tạp do Reflection bọc lỗi.

Mục tiêu của bài là hiểu đúng đường đi của lời gọi, triển khai một handler ủy quyền an toàn, phân biệt **tái nhập do cấu hình sai** với **gọi lồng nhau hợp lệ**, xử lý các trường hợp đặc biệt (`equals`, `hashCode`, `toString`, default methods, exception), và biết cách kiểm thử bằng Java 17+.

## 1. Dynamic proxy gồm những thành phần nào?

Giả sử interface nghiệp vụ là `Service`, implementation thật là `RealService`.

```text
Client
  |
  | service.work("A")
  v
Service proxy (đối tượng do Proxy.newProxyInstance tạo)
  |
  | InvocationHandler.invoke(proxy, method, args)
  v
DelegatingHandler
  |
  | method.invoke(target, args)
  v
RealService target
  |
  | thực hiện nghiệp vụ
  v
Kết quả / exception
  |
  +--------------------------> trả về cho client
```

`Proxy.newProxyInstance(ClassLoader, Class<?>[], InvocationHandler)` tạo đối tượng proxy cho **interface**, không phải một cách tự động subclass mọi class Java bất kỳ. `Service` được hiện thực ở runtime bằng một proxy class do JDK tạo; object implementation `RealService` không biến thành proxy chỉ vì nó được handler tham chiếu.

`InvocationHandler` định nghĩa:

```java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
```

Ba tham số cần hiểu riêng:

| Tham số | Chính xác là gì? | Lưu ý khi ủy quyền |
| --- | --- | --- |
| `proxy` | Object proxy mà client vừa gọi | **Không dùng nó làm receiver** cho `Method.invoke` nếu định gọi target thật |
| `method` | Metadata `java.lang.reflect.Method` đại diện cho lời gọi qua interface hoặc một số method của `Object` | Dùng cả tên **và chữ ký** để nhận diện; đừng chỉ xét tên khi có overload |
| `args` | Mảng các argument đã boxing theo nhu cầu, hoặc `null` nếu method không có tham số | Truyền đúng mảng tới `Method.invoke`; đừng bọc thêm một tầng array |

Object trả về từ handler phải tương thích kiểu trả về của method trên interface. Với `void`, handler có thể trả `null`. Với primitive return, proxy phải có giá trị wrapper thích hợp để unbox; trả `null` cho method trả `int`/`boolean` có thể dẫn tới `NullPointerException`.

**Một handler không nhất thiết chỉ làm delegation**: có thể xử lý một số method ngay trong handler, gọi default interface method, hoặc từ chối operation. Nhưng nếu đã chọn chuyển tiếp đến backend, **receiver đúng là backend**.

## 2. Sai lầm tạo vòng lặp: `Method.invoke(proxy, args)`

Mẫu lỗi điển hình:

```java
InvocationHandler bad = (proxy, method, args) ->
        method.invoke(proxy, args); // SAI: lại gọi chính proxy
```

Đoạn này là **phản ví dụ**, không được chạy tự do trong chương trình thật. Luồng thực thi:

```text
client -> proxy.work()
            |
            v
          handler.invoke(proxy, work, args)
            |
            | method.invoke(proxy, args)
            v
          proxy.work()
            |
            v
          handler.invoke(proxy, work, args)
            |
            | method.invoke(proxy, args)
            v
          proxy.work()
            |
           ...
```

`Method.invoke` không có quy tắc “nếu receiver là proxy thì đi thẳng tới implementation”. Nó thực hiện lời gọi trên **receiver được cung cấp**. Receiver là proxy thì proxy vẫn dispatch tới handler. Nếu không có điều kiện dừng, vòng lặp sẽ lặp tới khi cạn stack hoặc tài nguyên liên quan.

Đổi receiver thành `target` giải quyết **vòng quay trực tiếp**:

```java
InvocationHandler good = (proxy, method, args) ->
        method.invoke(target, args); // ĐÚNG VỀ RECEIVER nếu target tương thích
```

Đây là **đoạn minh họa** sử dụng biến `target` đã tồn tại. Trong production, còn cần xử lý `InvocationTargetException`, `Object` methods, default methods theo chủ đích, và kiểm tra kiểu target. Chương trình hoàn chỉnh ở mục 4 triển khai các phần này.

Lưu ý quan trọng: `target != proxy` là điều kiện cần để tránh vòng lặp trực tiếp **trong cách ủy quyền này**, nhưng **chưa bảo đảm không có chu trình gián tiếp**. Ví dụ proxy A chuyển cho proxy B, còn handler của B lại chuyển về A, vẫn tạo vòng tròn. Cần đánh giá **đường đi tổng thể** của delegation.

## 3. Receiver đúng và những lỗi khi chọn target

Với `method` đại diện cho một **instance method** của interface, `method.invoke(receiver, args)` đòi `receiver` là đối tượng mà method đó có thể được gọi trên nó. Nếu backend `RealService implements Service` và method được lấy từ `Service`, lời gọi phản chiếu trên backend là phù hợp.

Những lựa chọn receiver khác nhau:

| Receiver | Kết quả điển hình |
| --- | --- |
| `target` thật, triển khai interface tương ứng | Chạy method nghiệp vụ trên backend |
| `proxy` hiện tại | Handler bị gọi lại, rất dễ thành vòng đệ quy vô hạn |
| `null` với instance method | Không phải receiver hợp lệ; có thể gây `NullPointerException` |
| Object không tương thích với class/interface khai báo method | `IllegalArgumentException` |
| Proxy khác có handler tiếp tục về backend thật | Có thể là **proxy chain hợp lệ** nếu đồ thị không tạo chu trình |
| Proxy khác có handler chuyển ngược về proxy hiện tại | **Chu trình gián tiếp**, vẫn có nguy cơ đệ quy vô hạn |

Không nên “sửa” lỗi kiểu receiver bằng cách gọi `method.invoke` trên một đối tượng bất kỳ có method **trùng tên**. `Method` gắn với class/interface khai báo và signature. Nếu target không triển khai interface được proxy, phải định nghĩa một **adapter/mapping hợp lệ**, tìm `Method` trên đúng target class theo đúng danh sách tham số và kiểm tra access; tránh gọi nhầm overload. Trong bài này, ta cố ý chọn target triển khai cùng interface để giữ delegation rõ ràng.

Nếu backend chính là một dynamic proxy khác, việc ủy quyền có thể vẫn hợp lệ, nhưng cần xác định proxy đó kết thúc ở implementation thật hay tiếp tục quay vòng. Không nên dùng `Proxy.isProxyClass(...)` như kết luận “mọi proxy target đều sai”, vì decorator/transaction chains có thể được thiết kế đúng.

## 4. Ví dụ Java 17+ hoàn chỉnh: delegation đúng, Object methods, default method và vòng lặp được phát hiện an toàn

Tạo một file tên chính xác **`ProxyDelegationDemo.java`**. Toàn bộ interface, implementation và hai handler cùng nằm trong một public class, nên có thể biên dịch ngay bằng JDK 17+ trên classpath, không cần thư viện ngoài.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class ProxyDelegationDemo {
    public interface Service {
        String work(String value);
        String inner(String value);
        String outer(String value);
        void fail();

        default String decorated(String value) {
            return "<" + work(value) + ">";
        }
    }

    public static final class RealService implements Service {
        @Override
        public String work(String value) {
            return "work:" + value;
        }

        @Override
        public String inner(String value) {
            return "inner:" + value;
        }

        @Override
        public String outer(String value) {
            return "outer(" + inner(value) + ")";
        }

        @Override
        public void fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static final class DelegatingHandler implements InvocationHandler {
        private final Service target;

        public DelegatingHandler(Service target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            // Object methods được định nghĩa theo identity của proxy.
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == args[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "ServiceProxy";
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            System.out.println("log:" + method.getName());

            // Chủ động chạy default method trên proxy (Java 16+).
            if (method.isDefault()) {
                return InvocationHandler.invokeDefault(proxy, method, args);
            }

            // Với method nghiệp vụ, receiver PHẢI là target thật.
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException exception) {
                throw exception.getCause();
            }
        }
    }

    public static final class LoopingHandler implements InvocationHandler {
        private int calls;

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            // Chỉ dành cho demo: phát hiện sau ba lần tái nhập,
            // tránh chạy tới StackOverflowError thật.
            if (++calls > 3) {
                throw new IllegalStateException("proxy re-entered");
            }
            try {
                return method.invoke(proxy, args); // Cố ý sai!
            } catch (InvocationTargetException exception) {
                throw exception.getCause();
            }
        }
    }

    public static void main(String[] args) {
        Service real = new RealService();

        Service service = (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                new DelegatingHandler(real));

        System.out.println("work=" + service.work("A"));
        System.out.println("outer=" + service.outer("B"));
        System.out.println("decorated=" + service.decorated("C"));

        try {
            service.fail();
        } catch (IllegalStateException exception) {
            System.out.println("caught=" + exception.getMessage());
        }

        System.out.println("toString=" + service.toString());
        System.out.println("equalsSelf=" + service.equals(service));
        System.out.println("equalsTarget=" + service.equals(real));
        System.out.println("hashIdentity=" +
                (service.hashCode() == System.identityHashCode(service)));
        System.out.println("sameObject=" + (service == real));

        // Tạo proxy cố ý sai, nhưng có điểm dừng rõ ràng.
        Service broken = (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                new LoopingHandler());
        try {
            broken.work("X");
        } catch (IllegalStateException exception) {
            System.out.println("recursionDetected=" + exception.getMessage());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac --release 17 ProxyDelegationDemo.java
java ProxyDelegationDemo
```

**Stdout thực tế**, đã kiểm chứng:

```text
log:work
work=work:A
log:outer
outer=outer(inner:B)
log:decorated
log:work
decorated=<work:C>
log:fail
caught=boom
toString=ServiceProxy
equalsSelf=true
equalsTarget=false
hashIdentity=true
sameObject=false
recursionDetected=proxy re-entered
```

### 4.1. Dòng `work` chứng minh delegation cơ bản

Client gọi `service.work("A")`, vì `service` là proxy nên handler nhận `method=Service.work`, cùng argument `"A"`. Handler ghi `log:work`, sau đó `method.invoke(target, args)` gọi `RealService.work("A")`. Trả về `work:A`.

Điểm mấu chốt: handler **không gọi `service.work("A")` thêm lần nào**. Nếu handler dùng `method.invoke(proxy, args)`, chính proxy sẽ lại gọi handler.

### 4.2. `outer` gọi `inner` nhưng không thấy thêm `log:inner`: đây không phải vòng đệ quy

`RealService.outer` được thực thi trên **target thật**, bên trong viết `inner(value)` tương đương lời gọi trên `this` (tức `RealService`). Lời gọi nội bộ **không tự quay lại qua proxy**. Vì vậy:

```text
log:outer
outer=outer(inner:B)
```

không có dòng `log:inner`.

Đây là **self-invocation bypass**: một số interceptor dựa trên proxy (logging, transactions, authorization, metrics) sẽ không tự áp dụng cho các lời gọi nội bộ `this.inner(...)` trên target. Điều này có thể là chủ đích hoặc là một rủi ro thiết kế, nhưng **không phải lỗi đệ quy vô hạn**.

Nếu bắt buộc mọi lời gọi tới `inner` phải đi qua interceptor, phải thay đổi kiến trúc: tách collaborator được bọc proxy, điều hướng lời gọi qua một proxy được tiêm vào có kiểm soát, hoặc áp dụng một cơ chế interception khác. **Đừng sửa bằng cách đổi toàn bộ `Method.invoke(target, args)` thành `Method.invoke(proxy, args)`**, vì sẽ tạo vòng lặp ở điểm vào đầu tiên.

### 4.3. `decorated` có hai log vì chủ động gọi default method trên proxy

Interface `Service` khai báo:

```java
default String decorated(String value) {
    return "<" + work(value) + ">";
}
```

Đây là method mặc định của interface, không phải override riêng của `RealService`. Handler lựa chọn:

```java
InvocationHandler.invokeDefault(proxy, method, args)
```

API này có từ Java 16 và được hỗ trợ trên Java 17+. Nó **gọi trực tiếp implementation mặc định** của interface như một lời gọi `Interface.super.method(...)` trên **proxy**, thay vì phát lại `method.invoke(proxy, args)` qua handler cho chính method `decorated`.

Vì thân default method dùng `work(value)` trên `this` đang là proxy, lời gọi `work` tiếp tục vào handler. Do đó trace:

```text
log:decorated
log:work
decorated=<work:C>
```

Đây là **tái nhập hữu ích, có điểm dừng**: `decorated` gọi một method *khác*, rồi `work` được handler chuyển đến backend. Không nên dùng một guard “chặn mọi lần handler bị gọi lồng nhau”, vì nó sẽ phá các trường hợp hợp lệ như thế này.

Nếu thay bằng `method.invoke(target, args)` cho default method, phần thân default method được gọi trên **target**, nên lời gọi `work` bên trong thường sẽ đi thẳng đến target và **không tạo `log:work`**. Hai chiến lược có semantics khác nhau; chọn theo nhu cầu interceptor, không trộn lẫn.

### 4.4. `fail` và `InvocationTargetException`

Method `fail()` trên backend ném `IllegalStateException("boom")`. `Method.invoke(target, args)` sẽ bọc exception do method đích ném trong một **`InvocationTargetException`**.

Handler bắt wrapper này và ném lại **cause gốc**:

```java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException exception) {
    throw exception.getCause();
}
```

Nhờ đó client bắt đúng `IllegalStateException` và in `caught=boom`. Nếu handler ném thẳng `InvocationTargetException` là một checked exception không khai báo bởi interface method, dynamic proxy có thể bọc tiếp nó bằng `UndeclaredThrowableException`. Trả cause gốc giúp giữ hợp đồng exception của method đích, nhưng vẫn phải tuân thủ `throws` clause của interface đối với checked exceptions.

### 4.5. `toString`, `equals`, `hashCode` và `sameObject`

JDK dynamic proxy chuyển các lời gọi `equals(Object)`, `hashCode()` và `toString()` tới handler, với `Method.getDeclaringClass()` là `Object.class`, dù các method này không được viết trực tiếp trong interface.

Ví dụ định nghĩa chính sách **identity semantics** cho proxy:

- `equals`: chỉ đúng khi đối số `== proxy`.
- `hashCode`: dùng `System.identityHashCode(proxy)`.
- `toString`: trả nhãn ổn định `"ServiceProxy"`.

Vì vậy `equalsSelf=true`, `equalsTarget=false`, `hashIdentity=true`. Và `sameObject=false` vì `service` và `real` là **hai object riêng**; proxy *đại diện* target chứ không phải target.

Nếu ứng dụng muốn value equality hoặc muốn nhiều proxy đại diện cùng target được coi là bằng nhau, cần một chính sách `equals/hashCode` nhất quán khác. **Đừng chọn ngẫu nhiên** `equals` theo proxy identity nhưng `hashCode` theo target, hoặc ngược lại: vi phạm hợp đồng hai object bằng nhau phải có cùng hash code.

### 4.6. Minh họa lỗi có điểm dừng, không gây StackOverflow thật

`LoopingHandler` cố ý gọi `method.invoke(proxy, args)` để tái tạo anti-pattern. Tuy nhiên, ví dụ dùng biến `calls` và ném `IllegalStateException("proxy re-entered")` khi quá ngưỡng.

Điều này giúp chứng minh vòng lặp và in `recursionDetected=proxy re-entered` **một cách an toàn**. Biến đếm trong handler này **chỉ dành cho demo đơn luồng**, không phải bộ phát hiện recursion production: nó không reset theo chuỗi lời gọi, không an toàn nếu dùng đồng thời và sẽ từ chối lời gọi tiếp theo sau khi vượt ngưỡng. Trong hệ thống thật, hãy **sửa nguồn chu trình** chứ không chỉ đặt bộ đếm tùy ý.

## 5. Phân biệt đệ quy vô hạn, gọi lồng nhau và self-invocation bypass

Ba tình huống có thể trông giống nhau trên log, nhưng bản chất khác nhau:

| Tình huống | Chuỗi lời gọi | Có lỗi không? | Hướng xử lý |
| --- | --- | --- | --- |
| **Delegation đúng** | `proxy.work` → handler → `target.work` | Không | Cách chuẩn khi backend triển khai interface |
| **Vòng lặp trực tiếp** | `proxy.work` → handler → `proxy.work` → handler → ... | Có | Không dùng `proxy` làm receiver khi ủy quyền |
| **Vòng lặp gián tiếp** | proxy A → handler A → proxy B → handler B → proxy A → ... | Có | Kiểm tra đồ thị delegation, bỏ chu trình |
| **Reentrancy hợp lệ** | proxy.defaultMethod → handler → default body trên proxy → proxy.otherMethod → handler → target | Không nếu có điểm dừng đúng | Cho phép lời gọi lồng nhau có mục đích |
| **Self-invocation bypass** | proxy.outer → handler → target.outer → `this.inner` trên target | Không nhất thiết; nhưng có thể bỏ lỡ interceptor | Điều chỉnh kiến trúc nếu cần interception của `inner` |

Vì vậy, một quy tắc kiểu “handler không được xuất hiện hai lần trong cùng call stack” **không đúng tổng quát**. Điều cần đảm bảo là đường thực thi có điểm dừng hợp lý và lời gọi được chuyển đến **đúng receiver** theo contract.

Nếu có nhiều lớp proxy, có thể vẽ call graph theo mỗi method và target đã được cấu hình:

```text
Client -> LoggingProxy -> SecurityProxy -> RealService   [có điểm dừng]

Client -> ProxyA -> ProxyB -> ProxyA                    [chu trình]
```

Trong hệ thống thực tế, audit chain khi xây đối tượng hiệu quả hơn chờ stack overflow mới điều tra. Các object cấu hình cần được phân biệt theo **identity**, không chỉ class name, bởi hai proxies cùng class generated có thể mang hai handler khác nhau.

## 6. Kỹ thuật ủy quyền an toàn: giữ một target đã được xác nhận

Trong handler production, nên nhận `target` từ constructor hoặc factory có quyền kiểm soát, lưu reference rõ ràng và xác nhận nó thực thi interface.

Ví dụ, khái niệm factory:

```java
static <T> T wrap(Class<T> api, T target, InvocationHandler handler) {
    if (!api.isInterface()) {
        throw new IllegalArgumentException("API must be an interface");
    }
    if (!api.isInstance(target)) {
        throw new IllegalArgumentException("Target does not implement API");
    }
    Object proxy = Proxy.newProxyInstance(
            api.getClassLoader(), new Class<?>[] { api }, handler);
    return api.cast(proxy);
}
```

**Đoạn trên là minh họa rời**: cần import `Proxy`, `InvocationHandler` và cần đảm bảo chính `handler` được truyền đã giữ/được kết nối tới `target`. Nếu `handler` dùng một target hoàn toàn khác, việc kiểm tra biến `target` trong factory chưa bảo đảm delegation đúng. Thiết kế factory thật nên tự tạo handler với target đã xác nhận để tránh lệch cấu hình.

Cách tiếp cận tốt:

1. Định nghĩa rõ **interface được proxy** và **target mà handler thực sự gọi**.
2. Giữ target là một dependency riêng, không dùng tham số `proxy` làm backend.
3. Đảm bảo target không trỏ ngược vào chính proxy hoặc một proxy chain có chu trình ngoài ý muốn.
4. Với method thường, dùng `method.invoke(target, args)` khi target tương thích với method khai báo.
5. Với `Object` methods hoặc default methods, chọn chính sách riêng và ghi thành contract.
6. Chuyển exception từ Reflection về exception nghiệp vụ phù hợp.
7. Dùng test xác minh số lần target được gọi và handler có kết thúc.

Không nên giả định rằng target phải là một concrete class không qua proxy. Một proxy chain có thể đúng trong các framework. Vấn đề là **quyền sở hữu, mapping và cấu trúc chuỗi delegation**, không phải chỉ `Proxy.isProxyClass(target.getClass())`.

## 7. Xử lý `args` và chữ ký phương thức chính xác

`InvocationHandler.invoke` nhận `Object[] args`, hoặc `null` nếu method không có tham số. Vài lỗi thường thấy:

### 7.1. Truyền `args` đúng cách

```java
return method.invoke(target, args);
```

Trong Java, đây là lời gọi varargs nhận trực tiếp mảng `Object[] args`; khi `args == null` cho method không có tham số, `Method.invoke` chấp nhận theo hợp đồng API.

Không thay bằng:

```java
return method.invoke(target, new Object[] { args }); // DỄ SAI
```

Dòng thứ hai đưa **cả mảng cũ** thành **một argument** duy nhất. Nếu method đích nhận hai tham số `(int, String)`, kết quả sẽ sai số lượng/kiểu đối số (`IllegalArgumentException`). Chỉ dùng cách bọc một tầng nếu method đích thật sự nhận **một tham số kiểu mảng** và bạn chủ động muốn truyền cả mảng như một giá trị.

### 7.2. Method overload

Giả sử backend có hai method:

```java
String send(String data);
String send(Object data);
```

Đây là hai khai báo **minh họa** trong một class/interface tương ứng. Chỉ so `method.getName().equals("send")` chưa đủ để biết overload nào được gọi. `Method` chứa parameter types, return type và declaring class. Với một target triển khai interface, dùng chính metadata `Method` được handler nhận (khi hợp lệ) giúp tránh việc tự chọn nhầm method.

Nếu cần map một interface method sang một method backend khác, dùng `method.getParameterTypes()` và signature đầy đủ để tìm target method, không tìm theo tên rồi lấy phần tử đầu của `getMethods()`.

### 7.3. Giá trị trả về

Handler trả về một `Object`:

- Interface method `String foo()` → trả về `String` hoặc `null` khi contract cho phép.
- Interface method `void foo()` → trả `null` là phù hợp.
- Interface method `int count()` → trả wrapper `Integer` phù hợp; nếu trả `null`, generated proxy có thể ném `NullPointerException` khi unbox.
- Trả object sai kiểu cho method reference return có thể gây `ClassCastException`.

`Method.invoke` thường tự boxing primitive result thành wrapper trong giá trị `Object` trả lại cho handler, nên chuyển tiếp trực tiếp kết quả thường phù hợp. Nếu handler sửa return value (cache, mask data, default), phải tuân thủ chính xác contract của interface.

## 8. `InvocationTargetException` và checked exception qua proxy

Reflection phân biệt hai nhóm lỗi:

1. **Method đích thực thi rồi ném exception** → `Method.invoke` bọc lỗi trong `InvocationTargetException`.
2. **Reflection không thể thực hiện lời gọi** (receiver sai, argument sai, access bị từ chối) → lỗi của chính Reflection, ví dụ `IllegalArgumentException` hoặc `IllegalAccessException`.

Handler chuyển tiếp tốt chỉ unwrap **`InvocationTargetException`** khi cần truyền exception của target ra ngoài, và xử lý lỗi wiring/access riêng. Không nên catch mọi `Throwable` rồi bỏ qua: nó có thể làm mất dấu lỗi nghiêm trọng và che giấu recursion.

`InvocationHandler.invoke` khai báo `throws Throwable`, nhưng **proxy method của interface vẫn có throws clause riêng**. Nếu handler ném một **checked exception không được interface method khai báo** (và không phải subtype hợp lệ), generated proxy sẽ bọc nó trong `UndeclaredThrowableException`.

### 8.1. Ví dụ Java 17+ thứ hai: checked exception có khai báo và không khai báo

Lưu thành file độc lập **`ProxyExceptionDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;

public class ProxyExceptionDemo {
    interface Task {
        void declared() throws IOException;
        void undeclared();
    }

    public static void main(String[] args) {
        Task task = (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] { Task.class },
                (proxy, method, values) -> {
                    throw new IOException("disk");
                });

        try {
            task.declared();
        } catch (IOException ex) {
            System.out.println("declared=" + ex.getMessage());
        }

        try {
            task.undeclared();
        } catch (UndeclaredThrowableException ex) {
            System.out.println("wrapped="
                    + ex.getUndeclaredThrowable()
                            .getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 ProxyExceptionDemo.java
java ProxyExceptionDemo
```

Kết quả đã kiểm chứng:

```text
declared=disk
wrapped=IOException
```

`Task.declared()` cho phép `IOException`, nên checked exception được truyền thẳng đến caller. `Task.undeclared()` không cho phép checked `IOException`, nên proxy bọc nó trong `UndeclaredThrowableException`. Trong ví dụ này handler tự ném `IOException`; với handler ủy quyền bằng Reflection, **unwrap cause từ `InvocationTargetException` trước** giúp exception gốc được xử lý đúng theo throws clause.

Không nên khai báo `throws Throwable` ở mọi interface method chỉ để né việc kiểm tra hợp đồng. Hãy định nghĩa exception contract rõ ràng, và khi ánh xạ một exception nội bộ sang một exception public khác, giữ nguyên cause để có thể debug.

## 9. `equals`, `hashCode`, `toString`: lời gọi dễ gây tái nhập bất ngờ

Dynamic proxy xử lý ba phương thức công khai của `Object` là `equals`, `hashCode` và `toString` qua `InvocationHandler`, ngay cả khi interface không liệt kê chúng. Vì vậy một đoạn log tưởng như vô hại có thể gây vòng lặp:

```java
System.out.println("proxy=" + proxy);
```

**Đoạn minh họa rời này nguy hiểm khi đặt trong handler.** Nối chuỗi với `proxy` có thể gọi `proxy.toString()`, rồi `toString()` lại vào handler, handler lại log `proxy`, và cứ thế lặp.

Cách an toàn hơn để nhận diện proxy trong log là dùng thông tin không gọi phương thức ảo trên proxy, ví dụ:

```java
System.out.println("proxyIdentity="
        + System.identityHashCode(proxy));
```

`System.identityHashCode(proxy)` không gọi `proxy.hashCode()` qua handler, vì vậy giúp tránh chu trình do logging. Không được suy rằng `identityHashCode` là ID duy nhất toàn cục; có thể trùng hash và không phù hợp làm định danh bảo mật.

Đối với `equals`:

- Tránh `proxy.equals(other)` ở ngay bên trong xử lý `equals` của chính proxy.
- Nếu cần so sánh identity, dùng `proxy == other`.
- Nếu chính sách bình đẳng dựa trên target, cần quyết định khi so sánh proxy với target, với proxy khác và qua decorator chain; phải tuân hợp đồng phản xạ/đối xứng/bắc cầu của `equals`.

Đối với `hashCode`:

- Hash phải nhất quán với chính sách `equals`.
- Nếu dùng identity semantics trên proxy, `System.identityHashCode(proxy)` là cách đơn giản và không đệ quy.

Đối với `toString`:

- Dùng chuỗi mô tả cố định hoặc metadata đã xác định.
- Tránh gọi lại `proxy.toString()` từ handler.
- Không log thông tin bí mật của target chỉ vì proxy là lớp trung gian.

**Bẫy khác:** kiểm tra method theo `method.getDeclaringClass() == Object.class` cho ba phương thức này là rõ ràng. Nếu một interface cũng khai báo method trùng `equals(Object)`, `hashCode()`, `toString()` của `Object`, JDK vẫn ưu tiên method với declaring class là `Object.class` khi dispatch tới handler.

## 10. Default method: chọn rõ hai chiến lược ủy quyền

Từ Java 8, interface có thể chứa `default` method. Với dynamic proxy, có hai lựa chọn cần phân biệt:

### Chiến lược A — chạy default method trên target

Nếu target triển khai interface và không override default method, `method.invoke(target, args)` sẽ thực thi default implementation **với receiver là target**. Các lời gọi `this.otherMethod()` bên trong default method sẽ đi qua receiver target và có thể **bỏ qua proxy**. Cách này hợp lý khi bạn muốn proxy chỉ intercept lời gọi từ ngoài và để backend xử lý nội bộ tự nhiên.

### Chiến lược B — chạy default method trên proxy bằng `InvocationHandler.invokeDefault`

Nếu handler dùng:

```java
return InvocationHandler.invokeDefault(proxy, method, args);
```

và `method` thực sự là default method hợp lệ của một proxy interface, default implementation được gọi như `Interface.super.method(...)` **trên proxy**. Lời gọi tiếp tới các interface methods khác từ thân default có thể quay vào handler và chịu các interceptor.

Đây là sự **tái nhập có chủ đích** chứ không phải lặp lại cùng default method qua `Method.invoke(proxy, args)`. `InvocationHandler.invokeDefault` **không tương đương** với `method.invoke(proxy, args)`.

`invokeDefault` đòi method phải là default method hợp lệ đối với proxy interface hierarchy. Với interface inheritance phức tạp, default method bị override hoặc chọn method sai, API có thể ném `IllegalArgumentException`/`IllegalAccessException` tương ứng. Chỉ gọi nó sau khi xác định đúng `method.isDefault()` và cấu trúc interface phù hợp.

**Không có một lựa chọn luôn tốt hơn:** việc chọn target hay proxy làm receiver cho default method làm thay đổi phạm vi lời gọi bị intercept. Đừng áp dụng máy móc khi một framework còn có AOP, transaction hoặc permission checks phụ thuộc proxy entrypoint.

## 11. Self-invocation bypass: lỗi dễ bị nhầm với lỗi recursion

Xét code trong `RealService`:

```java
public String outer(String input) {
    return "outer(" + inner(input) + ")";
}
```

Khi client gọi `proxy.outer(...)`, handler chỉ thấy lời gọi `outer` rồi chuyển đến `target.outer(...)`. Lệnh `inner(...)` bên trong target tương đương `this.inner(...)`, nên trực tiếp gọi method của target, **không đi qua proxy**.

Nếu handler đang:

- Ghi log cho từng method;
- Mở transaction ở entrypoint;
- Xác thực/ủy quyền trước một operation;
- Thu metrics hoặc áp dụng cache;

thì lần self-invocation này có thể bỏ qua hành vi interceptor trên `inner`, ngay cả khi hai method đều public và là thành viên interface.

Đây là **hệ quả của mô hình proxy**, không thể giải quyết bằng cách giữ nguyên `target.outer(...)` nhưng mong Java tự rewrite mọi `this` thành `proxy`. Java thông thường không làm vậy.

Các hướng thiết kế tùy nhu cầu:

1. **Tách collaborator:** chuyển phần cần intercept sang một service khác mà target gọi thông qua interface/proxy.
2. **Điều phối ở layer gọi:** thay vì `outer` tự gọi `inner`, controller/application service gọi các operations qua proxy theo thứ tự mong muốn.
3. **Tiêm reference proxy có kiểm soát:** nếu framework hỗ trợ, có thể cho implementation tham chiếu proxy riêng để gọi lại *một method khác*; cần chứng minh không tạo chu trình trực tiếp/gián tiếp, tránh circular dependency.
4. **Dùng interception không chỉ dựa vào proxy entrypoint:** ví dụ bytecode weaving trong framework thích hợp, nếu yêu cầu thật sự là intercept cả self-invocation.

Đừng nhầm lời gọi lồng nhau đúng với recursion sai. Một default method chạy trên proxy có thể cố tình gọi method khác qua handler; đoạn lỗi là khi handler **ủy quyền lại chính method đang xử lý** cho **cùng proxy**.

## 12. Proxy chain và vòng tham chiếu gián tiếp

Một hệ thống thực tế có thể có nhiều lớp:

```text
Client
  -> LoggingProxy
      -> AuthorizationProxy
          -> RetryProxy
              -> RealService
```

Đây là chain hợp lệ nếu các handler được cấu hình rõ ràng và mỗi bước tiến về target cuối. Tuy nhiên:

```text
LoggingProxy
  -> AuthorizationProxy
      -> LoggingProxy
          -> ...
```

là chu trình. Dù mỗi handler riêng lẻ đều dùng biến tên `target`, cấu hình target có thể trỏ vòng.

**Kiểm tra kiến trúc trước khi chạy** là biện pháp tốt hơn là đặt một bộ đếm độ sâu chung để “chữa” mọi recursion. Nếu cần guard trong hệ thống có cấu hình động, thiết kế rõ:

- Guard theo **call chain** hoặc **operation id**, không theo số lượng lời gọi toàn ứng dụng.
- Dùng `try/finally` để giải phóng state.
- Xem xét đa luồng, async delegation, thread pools và context propagation.
- Không chặn recursion nghiệp vụ hợp lệ chỉ vì cùng tên method xuất hiện lại với đối số khác.
- Báo chu trình với tên cấu hình/object identity mà không vô tình gọi `toString` trên proxy.

Một `ThreadLocal` guard có thể hữu ích trong một số trường hợp sync, nhưng **không tự giải quyết** lời gọi qua thread khác, async tasks hoặc virtual-thread context. Không coi nó là thay thế cho thiết kế graph không chu trình.

## 13. Vì sao không nên log `proxy` hoặc gọi `toString` tùy tiện?

Một handler phổ biến:

```java
System.out.printf("Intercepted %s on %s%n", method, proxy);
```

**Đây là phản ví dụ** nếu `proxy` được format bằng `toString()`. Khi method client là `toString`, chính hành vi logging tạo `toString` khác. Nó có thể tạo vòng lặp ngay cả khi phần delegation nghiệp vụ của handler đúng.

Hãy log những thông tin an toàn hơn:

```java
System.out.printf("method=%s proxyId=%d%n",
        method.getName(), System.identityHashCode(proxy));
```

Đoạn trên chỉ là minh họa sử dụng biến handler `method` và `proxy`, không phải chương trình độc lập. Có thể in `method.getDeclaringClass().getName()` hoặc interface name khi cần phân tích overload; cần thận trọng với thông tin nhạy cảm và độ dài log.

Đối với `target`, nếu gọi `target.toString()` trong log, cũng nên xem nó có thể làm gì: một target có thể là proxy khác, method `toString` có thể truy cập dữ liệu nhạy cảm hoặc tái nhập chain. **Logging cũng là hành vi thực thi**, không phải phép quan sát thuần túy.

## 14. Kiểm thử handler: không chỉ kiểm kết quả trả về

Một proxy có thể trả giá trị đúng mà vẫn gọi target hai lần hoặc lặp một phần chuỗi. Kiểm thử nên quan sát **đường đi thực thi**, không chỉ output.

### 14.1. Các trường hợp tối thiểu

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Method trả giá trị | Target thật được gọi đúng một lần cho lời gọi ngoài |
| Method `void` | Handler xử lý `null` return đúng |
| Method không có tham số | `args` có thể `null`, không gây lỗi khi gọi Reflection |
| Method overloaded | Chọn đúng metadata/signature, không trộn các overload |
| Method ném runtime exception | Handler unwrap `InvocationTargetException`, caller thấy lỗi gốc |
| Method ném checked exception | Tôn trọng `throws` clause; hiểu `UndeclaredThrowableException` |
| `equals/hashCode/toString` | Không tái nhập do handler/log, hợp đồng equality nhất quán |
| Default method | Xác nhận chạy trên proxy hay target theo ý định |
| Self-invocation target | Xác nhận có/không cần intercept method nội bộ |
| Proxy chain | Không có vòng tham chiếu giữa các handler |
| Concurrent requests | Handler state, metrics và cache xử lý thread-safe |
| Null/primitive return | Tuân thủ kiểu trả về và quy tắc boxing/unboxing |

Ví dụ kiểm thử tốt có thể sử dụng một target test double tăng `AtomicInteger` trong `work` và kiểm tra con số sau lời gọi proxy. Với tình huống recursion, dùng handler có **điểm dừng rõ ràng** như mục 4 thay vì cố ý gọi vào vòng lặp vô hạn rồi phụ thuộc vào `StackOverflowError`.

### 14.2. Khi lỗi recursion chỉ xảy ra ở `toString`

Nếu `work(...)` hoạt động nhưng `System.out.println(proxy)` gây lỗi, hãy kiểm tra:

1. Handler có ghép chuỗi/log trực tiếp `proxy` không?
2. Nhánh xử lý `Object.toString` có gọi lại `proxy.toString()` không?
3. Target có phải một proxy khác mà `toString()` lại quay về proxy hiện tại không?
4. Equality/hash code của framework có gọi getter hoặc service method rồi quay ngược qua proxy không?

Không chỉ sửa riêng `work(...)`; vòng lặp qua Object methods là một đường lỗi độc lập.

### 14.3. Khi lỗi xuất hiện do exception được bọc nhiều tầng

Nếu stack trace có nhiều `InvocationTargetException` hoặc `UndeclaredThrowableException`, kiểm tra handler đang ném gì. Một `InvocationTargetException` bị truyền qua proxy method không khai báo checked exception có thể bị bọc. Nhưng **không** nên cố unwrap tất cả exception theo một vòng lặp bất chấp ngữ cảnh; có thể có tầng framework có contract riêng. Với handler ủy quyền trực tiếp, unwrap **đúng `InvocationTargetException` vừa được `method.invoke(target,args)` ném ra** là nguyên tắc rõ ràng nhất.

Đồng thời tìm chuỗi `Proxy...invoke → handler.invoke → Method.invoke → Proxy...invoke` lặp đi lặp lại trong stack trace; đó là dấu hiệu receiver có thể là proxy thay vì target.

## 15. Bảng lỗi phổ biến và cách sửa

| Lỗi thường gặp | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `StackOverflowError` khi gọi method qua proxy | Handler gọi `method.invoke(proxy,args)` hoặc proxy chain tạo chu trình | Delegate tới backend thật; sửa chain |
| Handler bị gọi liên tục khi ghi log | Log `proxy` kích hoạt `toString` qua handler | Log method name và `System.identityHashCode(proxy)` |
| `IllegalArgumentException: object is not an instance of declaring class` | `Method.invoke` nhận receiver không tương thích | Đảm bảo target thực thi interface hoặc map đúng method |
| `InvocationTargetException` rò ra caller | Handler không unwrap lỗi của target | `catch (InvocationTargetException e) { throw e.getCause(); }` |
| `UndeclaredThrowableException` | Handler ném checked exception không được interface khai báo | Tuân thủ contract, chuyển thành exception phù hợp hoặc thay interface |
| Không intercept lời gọi `inner` trong `outer` | `this.inner` chạy trực tiếp trên target | Tách service hoặc điều phối qua proxy nếu cần |
| Default method không tạo interceptor nested call như mong muốn | Default method được chạy trên target thay vì proxy | Xem `InvocationHandler.invokeDefault` khi đúng contract |
| `equals` luôn sai hoặc `hashCode` bất nhất | Trộn target equality và proxy identity | Chọn chính sách rõ và nhất quán |
| `NullPointerException` khi method trả primitive | Handler trả `null` cho method trả `int`/`boolean` | Trả wrapper đúng kiểu hoặc xử lý contract |
| `IllegalArgumentException` do số lượng tham số | Bọc `args` thành `new Object[]{args}` không phù hợp | Truyền trực tiếp `args` nếu method nhận các tham số gốc |
| Interceptor chạy hai lần không chủ đích | Một số target calls đi vào proxy khác hoặc self-delegation | Lần theo call graph và định nghĩa ownership |

**Không bắt `StackOverflowError` như chiến lược tránh recursion trong production.** Lỗi này có thể làm môi trường ở trạng thái không an toàn để xử lý tiếp. Nên phòng tránh vòng lặp bằng receiver/graph đúng và kiểm thử có giới hạn từ đầu.

## 16. Quy trình thiết kế một `InvocationHandler` chuyển tiếp đúng

Một cách làm có thể kiểm toán:

1. **Chọn interface** làm hợp đồng public cho proxy; xác định method nào cần can thiệp.
2. **Tạo backend** đúng kiểu và giữ reference riêng trong handler; không dùng parameter `proxy` làm backend.
3. **Quy định chính sách** cho `Object` methods trước, đặc biệt cách `equals/hashCode/toString` tương tác với target.
4. **Quy định default methods**: chạy trên proxy bằng `invokeDefault` hay trên target bằng Reflection? Chọn một chiến lược có chủ đích.
5. **Chuyển method thông thường tới target** bằng `method.invoke(target,args)` sau khi đảm bảo receiver và signature phù hợp.
6. **Unwrap lỗi target** từ `InvocationTargetException` và tuân thủ `throws` clause của interface.
7. **Vẽ proxy chain** nếu có nhiều handler/decorator; xác nhận không có đường quay lại proxy đang gọi.
8. **Kiểm thử reentrancy hợp lệ** (default method gọi method khác) và self-invocation bypass, đừng áp dụng một depth guard quá rộng.
9. **Kiểm thử concurrency và side effects** nếu handler giữ mutable state (counters, cache, tracing context, auth context).
10. **Giữ observability không tái nhập**: không in toàn bộ proxy/target vô điều kiện trong handler; dùng metadata/identity thông minh.

Nếu chỉ cần một decorator tĩnh cho một interface đơn giản, đôi khi một class wrapper viết tay sẽ dễ hiểu, dễ debug và dễ bảo trì hơn dynamic proxy. `Proxy` phù hợp khi bạn cần interception tổng quát cho nhiều interface methods mà không viết boilerplate lặp lại.

## 17. Câu hỏi tự kiểm tra

1. Trong `InvocationHandler.invoke(proxy, method, args)`, `proxy` có phải target thật không? **Không.** Nó là đối tượng proxy mà client đã gọi.
2. Tại sao `method.invoke(proxy,args)` dễ đệ quy vô hạn? **Vì nó lại gọi method trên proxy, khiến JVM dispatch vào handler lần nữa.**
3. `method.invoke(target,args)` luôn đúng với mọi object `target` không? **Không.** Receiver phải tương thích với method khai báo và delegation graph phải có điểm dừng.
4. Proxy A chuyển tới Proxy B rồi Proxy B chuyển tới target thật có sai không? **Không nhất thiết.** Đó có thể là decorator chain hợp lệ.
5. Proxy A chuyển tới Proxy B và Proxy B quay lại Proxy A thì sao? **Tạo chu trình gián tiếp**, dù handler không tự gọi chính proxy của nó.
6. Tại sao `RealService.outer` gọi `inner` không tạo thêm `log:inner`? **Vì `this` là target, không phải proxy.**
7. Tại sao `decorated` ở ví dụ tạo thêm `log:work`? **Vì `invokeDefault` chạy default method trên proxy và `work(...)` trong đó gọi lại qua proxy.**
8. Có nên chặn mọi lần handler tái nhập không? **Không.** Lời gọi lồng nhau khác method có thể hoàn toàn hợp lệ.
9. `InvocationTargetException` có phải exception nghiệp vụ gốc từ target không? **Không.** Đây là wrapper Reflection; lấy cause để truyền lỗi gốc.
10. Vì sao có `UndeclaredThrowableException`? **Vì handler ném checked exception không phù hợp với `throws` clause của interface method.**
11. Vì sao `System.out.println(proxy)` có thể gây recursion? **Vì nó có thể gọi `proxy.toString()`, mà method này cũng bị intercept.**
12. Dùng gì để log identity proxy mà không gọi `proxy.hashCode()`? **`System.identityHashCode(proxy)`**, kèm nhận thức rằng số hash không duy nhất tuyệt đối.
13. `args == null` có phải luôn là lỗi không? **Không.** Đó là trường hợp hợp lệ khi interface method không có đối số.
14. Interface có hai overload cùng tên thì nên chọn method theo tên không? **Không.** Cần xem parameter types/signature.
15. Một `InvocationHandler` có thể chạy default method trên proxy trên Java 17 không? **Có**, với `InvocationHandler.invokeDefault` nếu method hợp lệ.
16. `equals(proxy)` và `hashCode()` có tự được forward vào target không? **Không.** Chúng vào handler, và handler phải quyết định chính sách.
17. Có nên cố ý để vòng lặp chạy tới `StackOverflowError` trong unit test không? **Không.** Nên dùng điểm dừng an toàn hoặc cấu hình được kiểm soát.
18. Điều quan trọng nhất để tránh đệ quy do delegation là gì? **Đảm bảo handler gọi đúng đối tượng nhận (target thật) và đồ thị các lớp proxy không có chu trình ngoài ý muốn.**

## 18. Tài liệu chính thức để đối chiếu

- [Java SE 17 — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): cách tạo dynamic proxy, dispatch interface methods, và trường hợp đặc biệt `Object.equals/hashCode/toString`.
- [Java SE 17 — `InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): ý nghĩa của `proxy`, `method`, `args`, quy tắc exception và `invokeDefault`.
- [Java SE 17 — `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)): receiver, arguments, `InvocationTargetException` và dynamic lookup của instance method.
- [Java SE 17 — `UndeclaredThrowableException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): exception checked không có trong `throws` clause khi đi qua proxy.

**Tóm tắt:** `InvocationHandler` phải phân biệt **`proxy` để nhận và điều phối** với **`target` để thực thi nghiệp vụ**. Tránh `method.invoke(proxy,args)` khi bạn muốn ủy quyền method thường; dùng `method.invoke(target,args)`, unwrap exception của Reflection và xác định riêng chiến lược cho `Object`/default methods. Giữ proxy chain không chu trình, cho phép tái nhập hợp lệ, và kiểm thử đường đi thực thi để tránh cả recursion vô hạn lẫn interception bypass ngoài ý muốn.