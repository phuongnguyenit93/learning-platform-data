# Mô hình đối tượng trung gian tiếp nhận và chuyển tiếp lời gọi trong AOP qua proxy

**Proxy** là một đối tượng trung gian đứng giữa **bên gọi (caller/client)** và **đối tượng đích (target/real subject)**. Bên gọi thực hiện lời gọi qua proxy; proxy có cơ hội quan sát, kiểm tra, đo đạc, thay đổi cách điều phối hoặc quyết định có **chuyển tiếp lời gọi** tới target hay không. Đây là một cách tổ chức hành vi cắt ngang trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)** mà không buộc phương thức nghiệp vụ phải chứa trực tiếp mã ghi log, kiểm tra quyền hoặc đo thời gian.

Ý tưởng cốt lõi:

~~~text
Caller
  |
  | gọi qua một giao diện/hợp đồng
  v
Proxy (đối tượng trung gian)
  |-- before: ghi nhận/kiểm tra/đo thời điểm bắt đầu
  |-- chọn tiếp tục hay short-circuit
  |
  +---- nếu tiếp tục ----> Target (đối tượng nghiệp vụ)
  |                             |
  |<--- kết quả hoặc ngoại lệ ---+
  |
  |-- after-success / after-error / finally
  v
Caller nhận kết quả hoặc ngoại lệ
~~~

**Proxy không nhất thiết giống target về danh tính đối tượng.** Hai bên có thể cùng thực hiện một giao diện nhưng có class/runtime identity khác nhau. Mặt khác, **việc phương thức được gọi qua proxy** không tự bảo đảm tất cả join point trong thân target đều bị can thiệp: phạm vi chính xác phụ thuộc vào mô hình proxy, những phương thức được chặn và đường gọi thật.

Bài viết tập trung vào AOP nói chung: mô hình nhận lời gọi–chuyển tiếp, quan hệ giữa proxy và target, lifecycle, advice, pointcut, những tình huống không chuyển tiếp và nguyên tắc bảo toàn hợp đồng. Ví dụ Java 17 dùng **JDK dynamic proxy** để thực thi độc lập, đồng thời làm rõ đó chỉ là **một hiện thực minh họa**, không phải cú pháp hay khả năng mặc định của mọi hệ thống AOP.

## 1. Các vai trò trong mô hình proxy

Một kiến trúc proxy phổ biến có bốn vai trò:

| Vai trò | Nhiệm vụ | Điều cần chú ý |
| --- | --- | --- |
| **Caller/client** | Giữ tham chiếu tới một đối tượng có thể gọi được | Có thể không biết tham chiếu đó đang chỉ proxy |
| **Contract/interface** | Quy định phương thức, kiểu tham số/kết quả và nghĩa vụ | Proxy phải đáp ứng hợp đồng quan sát được |
| **Proxy** | Tiếp nhận lời gọi, thực thi logic can thiệp, chuyển tiếp hoặc xử lý thay thế | Có thể có state, chính sách, cache, thứ tự các interceptor |
| **Target/real subject** | Thực hiện logic nghiệp vụ thực tế | Có thể được tạo trước, tạo lười, lấy từ pool hoặc thay theo cấu hình |

Một proxy thường **thay thế được** target từ góc nhìn những phương thức thuộc hợp đồng giao tiếp đã công bố. Tuy nhiên, điều đó không có nghĩa mọi hành vi như `getClass()`, `==`, identity hash code, serialization hoặc phương thức không thuộc giao diện cũng giống hệt nhau.

**Chuyển tiếp (delegation/forwarding)** là hành động proxy gọi target hoặc một handler/interceptor kế tiếp. Một proxy có thể có trước/sau logic, nhưng cũng có thể trả dữ liệu cache, từ chối bằng ngoại lệ hoặc điều phối tới target khác nếu hợp đồng cho phép.

### 1.1 Proxy nằm ở ranh giới lời gọi, không phải được chọn bằng tên gọi

Nếu bên gọi có biến kiểu giao diện:

~~~java
Catalog catalog = obtainCatalog();
int price = catalog.price(10);
~~~

Đây là **mảnh code minh họa**; `obtainCatalog` giả định tồn tại. `catalog` có thể tham chiếu trực tiếp tới `CatalogImpl` hoặc tới một proxy cũng triển khai `Catalog`. Trong cả hai trường hợp, code phía caller dùng cùng lời gọi `price(10)`, nhưng trường hợp proxy còn đi qua lớp can thiệp.

Ngược lại, nếu caller vẫn giữ tham chiếu tới target gốc và gọi trực tiếp target, lời gọi ấy có thể **bỏ qua proxy**. Kiểm soát đường tham chiếu và nơi các đối tượng được cung cấp cho client vì vậy quan trọng không kém logic của handler.

## 2. Luồng một lời gọi từ đầu đến cuối

Giả sử gọi `service.execute("A")` qua proxy và advice chỉ ghi nhận trạng thái.

**Bước 1 — caller phát sinh lời gọi.** JVM dispatch lời gọi tới object proxy theo giao diện hoặc kiểu proxy.

**Bước 2 — proxy nhận thông tin.** Tùy cơ chế, proxy có thể biết `Method`, mảng `args`, chính object proxy, target, metadata và context khác. Đây chưa chắc là toàn bộ thông tin mà một weaver ở method-execution join point có thể nhận.

**Bước 3 — chọn logic can thiệp.** Proxy có thể đối chiếu method, cấu hình policy hoặc một chuỗi interceptor/advice. Nếu cơ chế có pointcut, chỉ những điểm/loại lời gọi phù hợp mới chịu advice tương ứng.

**Bước 4 — xử lý trước.** Ví dụ ghi metric bắt đầu, xác minh đầu vào hoặc kiểm tra quyền trước tác dụng phụ.

**Bước 5 — chuyển tiếp hoặc không chuyển tiếp.** Nếu chuyển tiếp, proxy gọi target hoặc gọi interceptor kế tiếp. Nếu short-circuit, target không chạy qua đường này.

**Bước 6 — nhận kết quả/lỗi.** Chuyển tiếp trả kết quả hoặc ném ngoại lệ; proxy có thể quan sát, chuyển đổi theo hợp đồng hoặc giữ nguyên.

**Bước 7 — kết thúc và trả về caller.** Proxy cần bảo toàn kiểu trả về, hợp đồng ngoại lệ, kết quả, side effects và cleanup phù hợp.

~~~text
Invocation
   |
   v
Proxy handler
   |
   +--> Method/args/context
   |
   +--> Before advice
   |
   +--> Decision?
            |
        +---+---+
        |       |
      proceed  skip
        |       |
        v       v
      Target    cached result / policy exception
        |       |
        +---+---+
            |
            v
      After/error/finally
            |
            v
      Return or throw
~~~

Đó là **sơ đồ ngữ nghĩa**; một cơ chế proxy có thể chuyển tiếp bằng reflection, gọi trực tiếp, method handle hoặc mã được tạo, không bắt buộc dùng cùng các hàm cụ thể.

### 2.1 Điểm phải bảo toàn

Việc “nhận lời gọi và chuyển tiếp” không chỉ là gọi một phương thức có cùng tên. Proxy phải xem xét:

- **Đúng phương thức và overload**: tên, kiểu tham số được khai báo, biến thể gọi và đường dispatch.
- **Đúng thứ tự/giá trị tham số**: `Object[]`, null, boxing/unboxing, varargs.
- **Đúng đối tượng target**: instance phù hợp với thao tác và trạng thái hiện hành.
- **Đúng kết quả**: kiểu trả về, nullability, generic contract, ý nghĩa nghiệp vụ.
- **Đúng ngoại lệ**: lỗi gốc được truyền tiếp hoặc được chuyển đổi theo chính sách, không nuốt ngầm.
- **Tác dụng phụ**: không bỏ qua ghi dữ liệu, gửi sự kiện hoặc phân quyền bắt buộc.
- **Tài nguyên**: cleanup và trạng thái giao dịch không bị rò.
- **Khả năng truy vết**: ghi số request/attempt, cache hit, lỗi đúng đơn vị.

## 3. Proxy liên hệ với AOP như thế nào?

Trong AOP, **join point** là một điểm chương trình có thể can thiệp; **pointcut** là tập điều kiện lựa chọn điểm; **advice** là hành vi cắt ngang. Proxy là **một kỹ thuật áp dụng một phần các ý tưởng đó** qua một **ranh giới lời gọi**.

Ví dụ ý định:

~~~text
Pointcut concept:
  calls through proxy to Catalog.price(int)

Before:
  emit bounded event "price.query"

Proceed:
  forward to underlying Catalog

After-success:
  record completion

After-error:
  record error category; preserve original exception
~~~

Đây là **giả mã**, không phải cú pháp chung. Một dynamic proxy Java không tự hiểu ngôn ngữ pointcut; người lập trình cần viết logic chọn method hoặc tích hợp một bộ chọn của công cụ AOP riêng.

### 3.1 Call join point và execution join point khác nhau

Ở một số hệ thống AOP, **method call** là điểm phát sinh lời gọi ở phía caller, còn **method execution** là lúc phần thân của phương thức đang chạy. Một proxy nằm ở một ranh giới lời gọi **không tự biến thành bộ weaver method-execution toàn cục**.

Nếu target được gọi trực tiếp, method body vẫn thực thi, nhưng proxy handler có thể **không hề biết lần gọi đó**. Một hệ thống biến đổi bytecode trực tiếp vào execution point có thể quan sát đường khác với một hệ thống chỉ dùng proxy.

Đừng nói “AOP qua proxy dệt vào mọi method execution”. Trong proxy-based AOP, phải xác định **đường nào đi qua proxy**, những method nào có thể chặn và các ngoại lệ như self-invocation.

### 3.2 Static structural matching và runtime checks

Nếu cần pointcut chọn phương thức `price(int)`, proxy có thể kiểm tra `Method.getName()` cùng `getParameterTypes()`; chỉ tên là chưa đủ khi có overload. Sau khi match cấu trúc, có thể dùng `args` hoặc target runtime làm điều kiện động.

~~~text
selected(invocation) =
   matchingSignature
   AND matchingProxyBoundary
   AND optionalRuntimeCondition
~~~

Một tham số được **bind** cho advice không có nghĩa đã dùng tham số đó để **lọc** pointcut. Việc đọc `args[0]` và quyết định `args[0] > 0` là hai thao tác riêng.

## 4. Các kiểu proxy và chiến lược chuyển tiếp

### 4.1 Proxy dựa trên interface

Caller và proxy cùng làm việc qua giao diện. Trong Java, **JDK dynamic proxy** tạo class runtime triển khai những giao diện chỉ định và chuyển lời gọi qua một `InvocationHandler`.

Ưu điểm:
- Dùng API chuẩn JDK.
- Không cần sửa class file của target.
- Dễ gắn interceptor vào các phương thức có mặt trong interface.
- Có thể chọn target runtime hoặc thay handler theo thiết kế.

Giới hạn:
- Chỉ tạo proxy cho **giao diện** được cung cấp, không tạo subclass của một concrete class bất kỳ.
- Phương thức không nằm trong giao diện proxy không tự trở thành phương thức gọi được qua proxy.
- Identity/class của proxy khác target.
- Cần xử lý `equals`, `hashCode`, `toString`, checked exceptions và tham số/kết quả cẩn thận.

### 4.2 Proxy dựa trên subclass

Một số cơ chế tạo **subclass hoặc lớp dẫn xuất** của type đích để ghi đè các phương thức thích hợp và chuyển tiếp qua interceptor. Cách này có thể hỗ trợ lời gọi không được mô tả bằng interface, nhưng bị giới hạn bởi quy tắc ngôn ngữ/runtime: **final class/method, private/static methods, constructor, visibility, module access** và khả năng sinh mã.

Không thể mặc định proxy subclass sẽ chặn mọi lời gọi nội bộ hoặc mọi phương thức: cần biết cách dispatch và cách proxy giữ/delegate tới target, đặc biệt nếu có **hai object riêng** hoặc chỉ dùng một instance được dẫn xuất.

### 4.3 Proxy tĩnh và proxy động

**Proxy tĩnh:** code wrapper được viết hoặc sinh tại build, biết giao diện/các thao tác cụ thể, chuyển tiếp bằng những lời gọi đã được biên dịch.

**Proxy động:** runtime sinh class hoặc handler dựa trên giao diện/kiểu và chính sách cấu hình. Việc tạo lúc chạy không tự có nghĩa handler có thể đổi mọi pointcut tức thời; handler và chuỗi interceptors có thể được chốt khi proxy tạo.

### 4.4 Lazy, remote và virtual proxy

Mô hình trung gian còn có thể dùng để:
- **Lazy initialization:** trì hoãn tạo target tới lần đầu thực sự cần.
- **Remote proxy:** biểu diễn đối tượng ở tiến trình/máy khác; việc chuyển tiếp có thể là network request thay vì local method call.
- **Protection proxy:** kiểm tra quyền trước khi gọi target.
- **Caching proxy:** trả kết quả từ cache khi hợp đồng cho phép.
- **Observability proxy:** metrics, tracing, audit có giới hạn dữ liệu.
- **Retry/fallback proxy:** điều phối nhiều lần thử, có khả năng không gọi hoặc gọi nhiều lần; phải kiểm soát side effect.

Những kiểu proxy này có thể kết hợp với AOP, nhưng **không phải mọi Proxy Pattern đều là một framework AOP**. AOP nhấn mạnh việc áp dụng concern vào các tập join point theo quy tắc; proxy là một cơ chế triển khai có thể dùng cho mục đích ấy.

## 5. Ví dụ Java 17 hoàn chỉnh: nhận, chuyển tiếp và bảo toàn lỗi

Ví dụ này dùng Java `Proxy` và `InvocationHandler`. Nó có:
- Giao diện `Service` gồm `process` và `status`.
- Target `ServiceImpl` thực thi nghiệp vụ.
- Proxy in `ADVICE before`, chuyển lời gọi, in `ADVICE after` trên thành công hoặc `ADVICE error` khi target ném lỗi.
- Một lời gọi **trực tiếp** target để so với lời gọi qua proxy.
- Cách xử lý ba phương thức `Object` để tránh nhận dạng proxy nhầm với target hoặc gây đệ quy khi ghi log.

Lưu toàn bộ dưới tên `ProxyForwardingDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ProxyForwardingDemo {
    interface Service {
        String process(String id, int quantity);
        String status();
    }

    static final class ServiceImpl implements Service {
        @Override
        public String process(String id, int quantity) {
            System.out.println("TARGET process id=" + id
                    + " qty=" + quantity);
            if (quantity < 0) {
                throw new IllegalArgumentException("negative quantity");
            }
            return "ok:" + id + ":" + quantity;
        }

        @Override
        public String status() {
            System.out.println("TARGET status");
            return "READY";
        }
    }

    static Object invokeTarget(
            Service target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Service wrap(Service target) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                (proxy, method, args) -> {
                    Object[] values =
                            args == null ? new Object[0] : args;

                    // Chính sách identity minh họa riêng cho proxy.
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "toString" -> "ServiceProxy";
                            case "hashCode" -> System.identityHashCode(proxy);
                            case "equals" -> proxy == values[0];
                            default -> throw new UnsupportedOperationException();
                        };
                    }

                    String operation = method.getName();
                    System.out.println("ADVICE before " + operation);

                    try {
                        Object result = invokeTarget(target, method, values);
                        System.out.println("ADVICE after " + operation
                                + " result=" + result);
                        return result;
                    } catch (Throwable error) {
                        System.out.println("ADVICE error " + operation
                                + " " + error.getClass().getSimpleName());
                        throw error;
                    }
                });
    }

    public static void main(String[] args) {
        ServiceImpl original = new ServiceImpl();
        Service proxy = wrap(original);

        System.out.println("META proxyClass="
                + Proxy.isProxyClass(proxy.getClass()));
        System.out.println("META sameTarget=" + (proxy == original));
        System.out.println("META toString=" + proxy);
        System.out.println("META equalsSelf=" + proxy.equals(proxy));
        System.out.println("META equalsTarget=" + proxy.equals(original));

        System.out.println("RESULT " + proxy.process("A", 2));

        try {
            proxy.process("B", -1);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }

        System.out.println("DIRECT");
        System.out.println("RESULT " + original.process("C", 1));
        System.out.println("STATUS " + proxy.status());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac ProxyForwardingDemo.java
java ProxyForwardingDemo
~~~

Stdout xác định:

~~~text
META proxyClass=true
META sameTarget=false
META toString=ServiceProxy
META equalsSelf=true
META equalsTarget=false
ADVICE before process
TARGET process id=A qty=2
ADVICE after process result=ok:A:2
RESULT ok:A:2
ADVICE before process
TARGET process id=B qty=-1
ADVICE error process IllegalArgumentException
CALLER negative quantity
DIRECT
TARGET process id=C qty=1
RESULT ok:C:1
ADVICE before status
TARGET status
ADVICE after status result=READY
STATUS READY
~~~

### 5.1 Đọc đúng output

**`Proxy.isProxyClass(proxy.getClass())` trả true:** đối tượng trung gian là class dynamic proxy được JVM sinh cho giao diện đã chọn; nó **không phải** cùng object với `ServiceImpl`.

**`proxy == original` là false:** caller và target có thể nhìn khác runtime identity. Proxy cần có chính sách nhất quán về `equals`, `hashCode`, `toString` nếu các method ấy được dùng trong cấu trúc dữ liệu, caching hoặc log. Ví dụ chủ động dùng **identity của proxy** và một tên `toString` cố định. Một proxy production có thể chọn chính sách khác, nhưng phải giữ các bất biến của `equals`/`hashCode`.

**`ADVICE before process` xuất hiện trước `TARGET...`:** lời gọi đi vào handler, chạy logic trước, sau đó `invokeTarget` mới gọi target.

**Khi `quantity=-1`:** target đã được gọi, in một dòng, rồi ném `IllegalArgumentException`. `Method.invoke` bọc ngoại lệ nghiệp vụ trong `InvocationTargetException`; code tháo lớp bọc để truyền đúng lỗi gốc. Handler in `ADVICE error` và không in `ADVICE after` thành công.

**Nhánh `DIRECT`:** gọi `original.process("C",1)` trực tiếp không đi qua proxy; chỉ có log target, không có `ADVICE`.

**`status()`:** cũng nằm trên interface proxy, nên cũng được chặn bởi handler. Demo không đặt pointcut lọc tên method, vì thế mọi method interface phù hợp đều vào logic advice.

### 5.2 Giới hạn của chương trình

- Đây là **mô phỏng advice qua dynamic proxy**, không tự dệt bytecode vào target, không cài một ngôn ngữ pointcut phổ quát.
- Handler **được gọi do lời gọi đi qua proxy**; không tự quan sát mọi execution join point trong JVM.
- Ví dụ không kiểm soát danh tính người dùng; không nên biến các dòng `ADVICE` thành cơ chế phân quyền thật.
- Mã ghi result ra console để minh họa; trong thực tế **không nên ghi raw args/result** nếu có thông tin nhạy cảm.
- Handler trả exception gốc qua `throw error`. Với các **checked exceptions không được giao diện khai báo**, dynamic proxy Java có thể bọc thành `UndeclaredThrowableException`; cần thiết kế hợp đồng ngoại lệ phù hợp.
- Nếu đối số hoặc kết quả kiểu primitive được biểu diễn qua `Object` trong proxy, phải bảo đảm boxing/unboxing hợp lệ; `null` cho kiểu primitive có thể gây `NullPointerException` lúc unbox.
- Mã không xử lý caching, retry hay transaction; các mối quan tâm đó cần hợp đồng và kiểm thử riêng.

## 6. Vì sao Object methods cần chính sách rõ?

Dynamic proxy của Java có thể chuyển những lời gọi `equals(Object)`, `hashCode()`, `toString()` đến invocation handler, dù giao diện nghiệp vụ không khai báo chúng. Vì vậy:

~~~text
proxy.toString()  -> handler
proxy.hashCode()  -> handler
proxy.equals(x)   -> handler
~~~

Nếu handler dùng `System.out.println(proxy)` một cách ngây thơ trong mọi lời gọi, việc in có thể lại gọi `proxy.toString()`, khiến handler vào lại và có nguy cơ đệ quy vô hạn.

Các quyết định cần rõ:

- **Identity-based equality:** proxy chỉ bằng chính nó.
- **Target-based equality:** nếu ủy quyền equals cho target, phải xem liệu `target.equals(proxy)` có cùng kết quả với `proxy.equals(target)` không; đối xứng và `hashCode` có thể bị phá.
- **Stable hash code:** nếu dùng proxy làm khóa map, hash code và equality không được thay tùy tiện sau khi thêm/bớt interceptor.
- **Safe toString:** tránh in target hoặc args nếu có bí mật; chuỗi cố định hoặc thông tin đã kiểm duyệt thường an toàn hơn.

Java `==` luôn so sánh identity tham chiếu cho object, nên không thể khiến `proxy == target` true bằng cách viết lại `equals`.

## 7. Chuyển tiếp lời gọi phải tôn trọng dispatch và kiểu

### 7.1 Method và overload

Chỉ lấy `method.getName()` không đủ để phân biệt:

~~~java
void send(String message);
void send(String message, int priority);
~~~

Đây là **mảnh khai báo**, không phải chương trình riêng. Nếu policy muốn chọn overload thứ hai, phải xét `method.getParameterTypes()` hoặc một dạng signature phù hợp, thay vì match mọi method tên `send`.

Proxy dynamic nhận `Method` liên quan interface, không nhất thiết là `Method` của lớp triển khai cuối cùng. Khi cần đọc annotation, phải xác định metadata được khai báo **ở interface hay target implementation**; annotation phương thức/tham số không tự suy theo kiểu như cách kế thừa lớp thông thường.

### 7.2 Varargs, null và generics

- Một phương thức `send(String... values)` biểu diễn varargs bằng một tham số mảng trong chữ ký; `args` không mặc định chứa mỗi phần tử vararg thành một mục riêng.
- Phương thức không tham số có thể cung cấp `args == null` ở JDK dynamic proxy; ví dụ đã chuẩn hóa thành mảng rỗng.
- Phần tử args có thể là `null`, không được luôn gọi `getClass()` trên nó.
- Primitive được boxing vào `Object[]` khi đi qua InvocationHandler.
- Generics Java trải qua type erasure; một số runtime generic checks không hiện ra như `Class<List<String>>` riêng.
- Compiler có thể sinh bridge method để bảo toàn override; đừng suy số method Reflection thấy bằng số join point hoặc số lần advice.

### 7.3 Ngoại lệ

Reflection `Method.invoke` bọc exception từ method đích bằng `InvocationTargetException`. Chuyển tiếp raw wrapper ấy không nhất thiết đáp ứng hợp đồng mà caller kỳ vọng.

Những lựa chọn:
1. Tháo lớp bọc và ném lại **nguyên nhân gốc** nếu hợp đồng cho phép.
2. Ánh xạ có chủ đích sang loại lỗi API/miền nghiệp vụ phù hợp, giữ `cause`.
3. Ghi nhận lỗi bằng mã/nhóm an toàn; không vô tình nuốt lỗi rồi trả thành công giả.

Đối với checked exceptions, còn phải xem khai báo `throws` trên giao diện. Handler có thể ném `Throwable`, nhưng proxy không buộc caller chấp nhận một checked exception mới ngoài hợp đồng.

## 8. Giới hạn đường gọi: proxy không quan sát được mọi lần thực thi

Proxy chỉ nhận invocation thực sự đi qua ranh giới mà nó kiểm soát. Ba trường hợp cần phân biệt:

| Đường gọi | Handler của wrapper proxy có nhận? | Lý do |
| --- | --- | --- |
| `caller → proxy.process()` | Có, nếu method được expose và handler phù hợp | Proxy là receiver của lời gọi ngoài. |
| `caller → target.process()` | Không | Caller đang giữ tham chiếu gốc. |
| `caller → proxy.outer() → target.outer() → this.inner()` | Chỉ nhận `outer` theo mẫu delegating proxy | Lời gọi `inner` phát sinh trên target, không quay về wrapper. |

Trong mẫu subclass proxy **chạy thân method trên chính receiver subclass**, một `this.inner()` có virtual dispatch đến override tương ứng; kết quả có thể khác. Bytecode weaving vào method execution cũng có thể chặn một đường gọi nội bộ nếu class thực sự đã được dệt. Bởi vậy không biến giới hạn của wrapper proxy thành kết luận cho mọi AOP.

Constructor, static, private và final methods còn chịu giới hạn khác nhau theo cách intercept. Nếu nghiệp vụ yêu cầu một policy không thể bỏ qua, phải xác định **toàn bộ đường gọi được phép**, không chỉ thấy một lời gọi mẫu qua proxy thành công.

## 9. Nhiều lớp proxy và thứ tự advice

Có thể ghép nhiều interceptor:

~~~text
Caller
  |
  v
AuthorizationProxy
  |
  v
TransactionProxy
  |
  v
MetricsProxy
  |
  v
Target
~~~

Trong mô hình lớp bọc lồng nhau, đường **vào** thường là:

~~~text
Authorization.before
Transaction.before
Metrics.before
Business
~~~

Đường **ra** khi thành công thường đảo:

~~~text
Metrics.after
Transaction.after
Authorization.after
~~~

Nhưng nếu một advice **không chuyển tiếp** (cache hit hoặc từ chối), mọi lớp **nằm trong điểm short-circuit** có thể chưa chạy, còn lớp ngoài đã vào vẫn có thể thực thi phần after/finally theo thiết kế.

### 9.1 Phép bọc và thứ tự xây dựng

Nếu code tạo chuỗi theo:

~~~text
chain = Target
chain = Metrics(chain)
chain = Transaction(chain)
chain = Authorization(chain)
~~~

thì `Authorization` ở **ngoài cùng**, dù được thêm **sau cùng**. Thứ tự thêm wrapper không nhất thiết bằng thứ tự BEFORE runtime. Một hệ thống AOP có thể định nghĩa precedence riêng; không lấy thứ tự file/aspect hoặc thứ tự khởi tạo làm bảo đảm nếu không có hợp đồng.

### 9.2 Vấn đề khi cache nằm ngoài authorization

~~~text
Cache(Authorization(Target))
~~~

Một cache hit có thể trả sớm mà không gọi `Authorization`. Nếu dữ liệu phải luôn được bảo vệ, thiết kế ấy có thể gây rò rỉ.

~~~text
Authorization(Cache(Target))
~~~

Ở cấu trúc này, quyền được kiểm tra trước khi cache trả kết quả trong đường gọi thông thường. Vẫn cần chứng minh mọi đường vào được bảo vệ và identity/resource được xác thực từ nguồn đáng tin. **Proxy không tự biến một điều kiện runtime không đáng tin thành chính sách phân quyền.**

### 9.3 Retry, transaction và tác dụng phụ

~~~text
Retry(Transaction(Target))
Transaction(Retry(Target))
~~~

Thứ tự có thể thay đổi ranh giới transaction và số lần target chạy. Một retry proxy không được tự lặp lại thao tác có tác dụng phụ nếu chưa có chính sách idempotency. Một transaction proxy phải kết thúc/rollback đúng khi target hoặc advice bên trong ném ngoại lệ, kể cả khi lớp ngoài bắt và trả fallback.

## 10. Proxy không bắt buộc luôn chuyển tiếp

Một proxy có thể thực hiện logic:

~~~text
proxy.handle(invocation):
    if forbidden:
        throw policyError
    if validCacheHit:
        return cachedValue
    return target.handle(invocation)
~~~

Đây là **giả mã**, không phải cú pháp AOP phổ quát. Hai nhánh đầu là **short-circuit**: không gọi target. Điều này có thể đúng đối với yêu cầu bị từ chối hoặc một **truy vấn chỉ đọc có cache hợp lệ**.

Nhưng nếu phương thức gốc cần **ghi tiền, phát sự kiện, lưu đơn hàng hoặc kiểm toán bắt buộc**, proxy không được tùy tiện trả giá trị thành công giả khi chưa thực hiện hậu điều kiện. Kết quả trả về đúng kiểu là chưa đủ.

Một câu hỏi hữu ích trước mọi short-circuit: **những điều gì mà người gọi có quyền kỳ vọng vẫn phải đúng ngay cả khi target không chạy?**

### 10.1 Cache và tính nhất quán

Nếu cache phụ thuộc người dùng, tenant, phiên bản, quyền hoặc thời gian, khóa cache phải phản ánh các yếu tố liên quan. Trả dữ liệu cache của người khác hoặc đã quá hạn có thể vi phạm hợp đồng và bảo mật.

### 10.2 Lazy target

Một proxy có thể chỉ khởi tạo target ở lần gọi đầu, nhưng phải bảo đảm thread safety, publish object an toàn, xử lý thất bại khi khởi tạo và vòng đời tài nguyên. Nếu hai thread gọi cùng lúc, lazy initialization thiếu đồng bộ có thể tạo nhiều target ngoài ý định.

### 10.3 Remote forwarding

Với remote proxy, target ở tiến trình khác. Khi đó lỗi mạng, timeout, retry, serialization, version protocol và idempotency trở thành phần hợp đồng. Không thể coi lời gọi qua mạng tương đương hoàn toàn với local method call, đặc biệt về latency và lỗi.

## 11. Context: proxy, target, this, args không đồng nghĩa

Một điểm dễ nhầm trong AOP là từ **target** và **this**.

- **Proxy object:** đối tượng nhận lời gọi tại ranh giới proxy.
- **Underlying target:** đối tượng nghiệp vụ handler chuyển tiếp tới.
- **`this` trong thân target instance method:** đối tượng đang chạy phần thân, thông thường là target đó.
- **Caller-side `this`:** đối tượng thực thi phương thức phát sinh lời gọi tại một method-call join point, nếu mô hình AOP có expose.
- **Arguments:** giá trị thực tế truyền cho lần gọi.

Trong JDK `InvocationHandler.invoke(proxy, method, args)`, tham số `proxy` là **chính proxy**, không phải đối tượng caller-side `this`. Target chỉ khả dụng khi handler giữ hoặc giải quyết nó; nó không tự được API đưa vào như tham số độc lập.

Tại **execution của phần thân** khi dùng một loại weaving khác, this/target có thể được mô hình hóa khác với invocation handler. Vì vậy không dùng tên `proxy` để suy ý nghĩa `this` hay `target` của mọi ngôn ngữ pointcut.

## 12. Hiệu năng, khả năng mở rộng và vòng đời

Mỗi lớp proxy có thể gây overhead:
- Dispatch bổ sung và đôi khi boxing/unboxing qua `Object[]`.
- Kiểm tra pointcut hoặc điều kiện runtime.
- Thêm hoạt động logging, tracing, metrics.
- Đồng bộ trạng thái, cache hoặc truy vấn cấu hình.
- Reflection hoặc metadata lookup khi chưa có cache hợp lý.
- Lồng nhiều wrapper và cấp phát đối tượng bổ sung.

Overhead thực tế phụ thuộc JVM/JIT, loại proxy, mức độ nóng của phương thức và logic advice; không thể khẳng định “proxy luôn chậm nhiều” hoặc “không có overhead” mà chưa đo.

### 12.1 Đo đúng ranh giới

Nếu `MetricsProxy` ở **ngoài** lớp Authorization và Cache, nó có thể đo cả nhánh bị từ chối và cache hit. Nếu nằm **trong Cache**, cache hit không đi qua nó. Cần định nghĩa **latency toàn lời gọi** và **latency target** khác nhau.

### 12.2 Trạng thái và thread safety

Một proxy dùng chung giữa nhiều caller có thể chạy song song trên nhiều thread. Nếu handler giữ counters, cấu hình, connection, session hoặc cache mutable, cần quy tắc đồng bộ hoặc cấu trúc dữ liệu thread-safe.

Nếu proxy đọc một policy có thể đổi động, nên dùng **snapshot bất biến trên mỗi invocation** để tránh nửa đầu dùng policy cũ, nửa sau dùng policy mới. Nhưng đổi cấu hình không tự thêm một join point mà proxy không bao phủ.

### 12.3 Rò rỉ dữ liệu khi log args/result

Proxy có thể thấy mảng `args`, kết quả và ngoại lệ; đó là dữ liệu rất nhạy cảm. Không mặc định `Arrays.toString(args)`, `target.toString()` hoặc `error.getMessage()` an toàn. Ưu tiên event schema allowlist và chỉ ghi trường được phê duyệt, tránh secret/token/PII, hạn chế retention và quyền truy cập.

### 12.4 Đệ quy do proxy tự gọi lại

Nếu handler dùng `proxy.process(...)` để “chuyển tiếp” thay vì gọi target, nó có thể quay lại chính handler và lặp vô hạn. Một handler còn có thể đệ quy nếu gọi `proxy.toString()` trong bước logging. Phải xác định **đối tượng tiếp nhận continuation** và cơ chế chống reentrancy của mỗi advice.

## 13. Kiểm thử đúng mô hình trung gian

Một bộ kiểm thử nên chứng minh cả **có chặn đúng** và **không thay đổi hợp đồng ngoài ý định**.

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Caller gọi qua proxy | Before chạy, target nhận đúng args, after chạy khi thành công |
| Target ném exception | Nhánh error chạy và caller nhận lỗi phù hợp; không in after-success |
| Caller gọi trực tiếp target | Không có advice proxy ngoài dự đoán |
| Proxy `equals`/`hashCode`/`toString` | Không đệ quy, nhất quán với chính sách identity |
| Overload/varargs/null | Handler nhận đúng method, args và xử lý giá trị null |
| Interface/proxy runtime type | Không nhầm declaring type, proxy class với target class |
| Self-invocation | Chỉ khẳng định advice chạy nếu đường nội bộ thực sự đi qua proxy |
| Nhiều proxy | Thứ tự vào/ra và nhánh short-circuit đúng |
| Cache hit | Không gọi target nếu hợp đồng cho phép; vẫn bảo vệ dữ liệu |
| Authorization reject | Target không có tác dụng phụ; audit bắt buộc không bị bỏ qua |
| Checked exception | Giữ loại lỗi hợp đồng, không bọc sai hoặc nuốt lỗi |
| Concurrent callers | Không có race/lost update trong handler/cache |
| Async/remote | Phân biệt lúc trả completion handle với lúc hoàn thành thật |
| Direct/execution weaving comparison | Không suy phạm vi proxy bằng phạm vi bytecode weaving |

### 13.1 Kiểm tra thứ tự bằng trace

Thay vì chỉ nhìn hai dòng BEFORE/AFTER, có thể trong test gom event:

~~~text
expected:
  proxy.before
  target.enter
  target.return
  proxy.after
  caller.receive
~~~

Với nhánh lỗi:

~~~text
expected:
  proxy.before
  target.enter
  target.throw
  proxy.error
  caller.catch
~~~

Đó là **trình tự giả định của wrapper đã định nghĩa**. Một cơ chế AOP khác có thể có nhiều advice/loại join point hơn; trace dùng cho kiểm thử phải dựa vào hợp đồng thực tế.

### 13.2 Hợp đồng bảo mật quan trọng hơn chỉ số advice

Nếu proxy làm kiểm soát quyền, một test chỉ thấy `ADVICE before` là chưa đủ. Phải kiểm chứng mọi đường vào bảo vệ đều đi qua kiểm tra, danh tính được xác thực từ nguồn tin cậy, quyền đúng theo tài nguyên và không có đường short-circuit ở lớp ngoài làm bỏ qua policy.

## 14. Những ngộ nhận thường gặp

1. **“Proxy và target luôn là một object.”** Sai: dynamic proxy thường là object riêng.
2. **“Proxy chặn mọi lời gọi trong ứng dụng.”** Sai: chỉ những đường đi qua phạm vi proxy.
3. **“Proxy handler chính là method-execution join point ở target.”** Không tự suy được từ JDK dynamic proxy.
4. **“Chỉ cần method cùng tên là forward đúng overload.”** Phải xét signature và dispatch.
5. **“Object methods không liên quan AOP.”** `equals`, `hashCode`, `toString` có thể đi qua handler và cần chính sách.
6. **“Reflection có `throws Throwable` nên checked exception nào cũng hợp lệ.”** Java proxy có quy tắc ngoại lệ hợp đồng.
7. **“Gọi target và gọi proxy có cùng `getClass()`.”** Không bắt buộc; class proxy có thể khác.
8. **“Tự gọi `this.other()` luôn quay qua proxy.”** Không đối với mọi cơ chế, đặc biệt delegation qua object gốc.
9. **“Cache proxy được trả thành công cho mọi ghi dữ liệu.”** Vi phạm hậu điều kiện nếu side effect bị bỏ qua.
10. **“Đặt Authorization ở trong Cache vẫn bảo vệ mọi cache hit.”** Cache ở ngoài có thể không gọi tiếp.
11. **“Thêm interceptor vào danh sách luôn làm nó chạy trước.”** Phụ thuộc thuật toán lồng wrapper/precedence.
12. **“Proxy phải dùng Reflection.”** Không; có thể dùng lời gọi trực tiếp, mã sinh, method handle.
13. **“Proxy luôn tốt hơn bytecode weaving.”** Hai kỹ thuật có khả năng và giới hạn khác nhau.
14. **“Chỉ log arguments là vô hại.”** Args có thể chứa mật khẩu, token, dữ liệu cá nhân.
15. **“Chạy thành công qua proxy chứng minh không cần test concurrency.”** State handler dùng chung vẫn có rủi ro race.

## 15. Bài tập tự luyện

**Bài 1.** Cho `Client → Proxy → Target`. Advice before in một dòng, gọi target, after in một dòng. Nếu target trả giá trị bình thường, thứ tự nào được kỳ vọng?

**Đáp:** before → target → after, rồi caller nhận kết quả. Đó là thứ tự của **chuỗi handler này**, không là quy tắc chung của mọi advice độc lập trong mọi bộ AOP.

**Bài 2.** Caller giữ `Target` gốc và gọi nó trực tiếp. Proxy có quan sát chắc chắn được lần gọi đó không?

**Đáp:** không. Caller bypass proxy. Nếu chính sách bắt buộc áp dụng cho tất cả đường vào, phải kiểm soát cách phát hành tham chiếu hoặc bổ sung ranh giới đáng tin khác.

**Bài 3.** Một `CacheProxy` bao ngoài `AuthorizationProxy`. Cache hit không chuyển tiếp. Kiểm tra quyền bên trong có chạy không?

**Đáp:** không qua nhánh đó. Đây có thể là lỗ hổng nếu mọi lần đọc cần xác thực/phân quyền trước khi trả dữ liệu.

**Bài 4.** Vì sao gọi `proxy.toString()` từ log trong InvocationHandler có thể nguy hiểm?

**Đáp:** việc gọi `toString()` có thể quay lại chính handler, tạo đệ quy. Cần xử lý Object methods tường minh hoặc ghi metadata an toàn không gọi lại proxy.

**Bài 5.** Handler dùng `Method.invoke(target, args)`; target ném `IllegalArgumentException`. Điều gì cần xử lý?

**Đáp:** `Method.invoke` bọc ngoại lệ target trong `InvocationTargetException`. Handler thường cần tháo bọc và truyền tiếp lỗi gốc theo hợp đồng, không vô tình báo lỗi wrapper như lỗi nghiệp vụ.

**Bài 6.** Một proxy dựa trên interface có chặn được một private method chỉ có trong implementation không?

**Đáp:** không thể mặc định. JDK dynamic proxy chặn lời gọi thông qua các interface đã cung cấp; private method của target không là lời gọi public interface tới proxy.

**Bài 7.** Một remote proxy retry gửi tiền lần nữa sau timeout. Vì sao nguy hiểm?

**Đáp:** timeout không chứng minh thao tác đầu chưa tạo tác dụng phụ; retry có thể gửi tiền hai lần nếu thiếu idempotency và giao thức xác nhận kết quả đáng tin.

## 16. Ghi nhớ

Mô hình proxy trong AOP có thể tóm tắt thành bốn câu hỏi:

1. **Ai nhận lời gọi trước?** Proxy hay target gốc?
2. **Proxy có những thông tin nào?** Method, args, chính proxy, target và ngữ cảnh phù hợp.
3. **Proxy làm gì trước khi chuyển tiếp?** Advice, kiểm tra, metric, cache, short-circuit?
4. **Proxy có thực sự chuyển tiếp không và giữ đúng hợp đồng không?** Nếu không, hệ quả nào xảy ra với target, các advice bên trong và caller?

**Kết luận:** proxy là **đối tượng trung gian tiếp nhận và điều phối lời gọi**. Nó có thể cho AOP tách mối quan tâm cắt ngang khỏi mã nghiệp vụ, nhưng chỉ tác động tới **đường gọi đi qua ranh giới của nó**. Thiết kế tốt phải phân biệt proxy/target, giữ đúng tham số–kết quả–ngoại lệ, cấu hình thứ tự advice có chủ đích và kiểm chứng các đường bypass cùng nhánh short-circuit. Không nên coi proxy là công cụ dệt mọi join point của chương trình.
