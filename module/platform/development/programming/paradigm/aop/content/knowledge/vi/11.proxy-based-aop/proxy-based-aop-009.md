# Chẩn đoán tình huống lời gọi không kích hoạt advice trong AOP qua proxy

Trong **AOP qua proxy**, advice chỉ có cơ hội chạy khi **lời gọi thực sự đi qua một ranh giới proxy phù hợp**, cơ chế chặn nhận được phương thức, các điều kiện lựa chọn khớp, và đường điều khiển đi đến advice ấy. Khi một chương trình chạy đúng nghiệp vụ nhưng không thấy dòng log `before` hoặc `after`, ta **không thể lập tức kết luận “AOP bị hỏng”**. Có thể caller đang giữ target gốc, một lời gọi nội bộ không qua proxy, pointcut chọn sai chữ ký, interceptor bị tắt, around advice bên ngoài trả sớm, hoặc advice chỉ chạy ở nhánh thành công trong khi nghiệp vụ ném lỗi.

Bài này xây dựng **phương pháp chẩn đoán từ ngoài vào trong**, phân biệt các nguyên nhân của sự kiện “advice không kích hoạt” và cách kiểm chứng bằng Java 17. Các ví dụ tập trung vào **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP) nói chung**; Java dynamic proxy là phương tiện minh họa có thể chạy độc lập. Khả năng chặn method call, method execution, private/final/static methods, trình tự precedence và cách triển khai proxy có thể khác nhau theo công cụ.

## 1. Trước khi sửa: xác định điều gì thực sự “không chạy”

Cụm từ “advice không chạy” dễ gom lẫn các hiện tượng rất khác nhau:

1. **Không qua proxy:** caller đi thẳng vào target, nên handler/interceptor không có cơ hội nhận lời gọi.
2. **Qua proxy nhưng không được chọn:** handler nhận method, song pointcut hoặc bộ lọc method trả false.
3. **Qua proxy và khớp chữ ký nhưng sai ngữ cảnh:** tham số, target, đối tượng đang gọi hoặc trạng thái runtime không thỏa điều kiện động.
4. **Advice có tồn tại nhưng không đi tới:** một lớp bên ngoài đã `return`, ném lỗi hoặc short-circuit trước khi gọi continuation.
5. **Chỉ nhầm thời điểm hoặc loại advice:** `after returning` không chạy khi có ngoại lệ; một `after throwing` không chạy trên nhánh thành công.
6. **Advice chạy nhưng người quan sát không thấy:** log level tắt, bộ ghi bất đồng bộ bị trì hoãn, trace bị lấy mẫu, sai cửa sổ tìm kiếm hoặc logger bị lỗi.
7. **Sai phiên bản artifact/cấu hình:** JVM đang dùng proxy/handler hoặc class loader cũ, không phải cấu hình mới vừa build.
8. **Sai kỳ vọng về phạm vi proxy:** JDK interface proxy không tự biến mọi điểm thực thi bên trong object đích thành một join point chặn được.

Thay vì thay pointcut ngẫu nhiên, nên xác nhận từng tầng bằng một **dấu hiệu kiểm chứng tạm thời, an toàn về dữ liệu**, từ lời gọi bên ngoài tới advice và target.

## 2. Cây quyết định chẩn đoán

~~~text
Bắt đầu: business method có được gọi?
          |
          v
Caller đang gọi object nào?
          |
          +-- target gốc ---------> không qua proxy -> sửa đường tham chiếu
          |
          +-- proxy
                 |
                 v
      Handler có nhận invocation?
                 |
                 +-- không -------> sai proxy/interface/classloader/
                 |                  kiểu method hoặc đường dispatch
                 |
                 +-- có
                        |
                        v
             Pointcut / filter khớp?
                        |
                        +-- không --> kiểm tra tên, overload, declaring
                        |            type, annotation, call/execution
                        |
                        +-- có
                               |
                               v
                   Runtime condition đúng?
                               |
                               +-- không --> args/target/context/flag
                               |
                               +-- có
                                      |
                                      v
                          Có được gọi tới advice?
                                      |
                                      +-- không --> precedence, short-circuit,
                                      |            nhánh lỗi, interceptor order
                                      |
                                      +-- có
                                             |
                                             v
                          Advice có phát tín hiệu?
                                             |
                                             +-- không --> logger, sampling,
                                             |            async exporter
                                             |
                                             +-- có --> kiểm tra sink/traces
~~~

Đây là cây khái niệm. Một số cơ chế kết hợp pointcut và handler tại nhiều pha khác nhau; vì vậy cần ánh xạ các bước vào pipeline thật, không buộc mọi công cụ phải có đúng các hàm như trong sơ đồ.

**Một dấu hiệu quan trọng:** nếu target in `BUSINESS` nhưng handler không in `PROXY received`, lỗi không nằm ở câu lệnh bên trong advice. Trước tiên cần kiểm tra **đối tượng được gọi** và phạm vi interception.

## 3. Phân biệt target, proxy và tham chiếu thực tế của caller

Trong mô hình phổ biến:

~~~text
Client -> Proxy -> Interceptor/handler -> Target
~~~

Proxy là **đối tượng trung gian**. Target là **đối tượng nghiệp vụ**. Hai đối tượng có thể cùng triển khai một interface, nhưng **khác identity**. Caller có thể giữ tham chiếu proxy hoặc target gốc; chỉ trường hợp đầu mới chắc chắn đi qua ranh giới proxy này.

Ví dụ giả mã:

~~~java
Task original = new TaskImpl();
Task wrapped = createProxy(original);

wrapped.execute("A");  // Qua proxy: có cơ hội kích hoạt advice.
original.execute("B"); // Đi thẳng target: bỏ qua advice proxy.
~~~

Đây là mảnh minh họa, không phải một chương trình độc lập; `Task`, `TaskImpl`, `createProxy` cần được khai báo tương ứng.

### 3.1 Đừng chỉ dựa vào kiểu biến được khai báo

Hai biến `Task` có thể trỏ tới object runtime khác nhau. Cần kiểm tra **tham chiếu mà code dùng tại điểm gọi**. Với dynamic proxy Java, `Proxy.isProxyClass(object.getClass())` có thể giúp xác nhận một object thuộc dạng JDK dynamic proxy; kết quả false **không chứng minh** object không phải proxy của cơ chế khác (chẳng hạn subclass proxy).

Nếu đang debug production, không in bừa `object.toString()`: toString của proxy có thể lại bị intercept và tạo recursion; toString của target có thể làm lộ secret. Một thông tin kỹ thuật giới hạn như phân loại "proxy/target" và tên thao tác đã duyệt thường đủ.

### 3.2 Có thể proxy đã được tạo nhưng chưa được dùng

Một lỗi lắp ghép phổ biến:

~~~text
create target
create proxy wrapping target
store target in client
discard or never use proxy
~~~

Build/config vẫn có "proxy enabled" nhưng caller gọi object gốc. Để sửa, cần kiểm tra nơi đối tượng được tạo, nơi nó được truyền hoặc gán vào các thành phần khác, và **đối tượng nào thật sự được trả về** sau bước khởi tạo. Nếu cần một chính sách bắt buộc, không nên phát tán tham chiếu target gốc cho những caller có thể bypass.

## 4. Self-invocation: gọi từ target vào chính nó

Một trường hợp đặc biệt quan trọng:

~~~java
class Handler {
    void outer() {
        inner();
    }

    void inner() {
        // Business logic
    }
}
~~~

Đây là mảnh minh họa. Giả sử proxy dùng **delegation sang một instance target riêng**:

1. Client gọi `proxy.outer()`.
2. Proxy intercept `outer` rồi chuyển tiếp tới `target.outer()`.
3. Trong `target.outer()`, lời gọi `inner()` thường là `this.inner()` trên **target**, không qua `proxy`.
4. Nếu advice chỉ được lắp trên proxy đối với `inner`, lời gọi nội bộ có thể **không kích hoạt advice**.

Sơ đồ:

~~~text
Client --outer()--> Proxy --outer()--> Target.outer()
                                       |
                                       +--this.inner()--> Target.inner()
                                                           (không quay proxy)
~~~

Lỗi này thường bị hiểu nhầm thành "pointcut `inner` không khớp". Thực ra có thể **không có join point proxy invocation cho `inner`** trong đường thực thi này.

**Không tuyệt đối hóa self-invocation cho mọi proxy.** Một proxy tạo bằng subclass và thực thi phương thức trên chính instance dẫn xuất có thể có virtual dispatch tới override, khác với mô hình delegation sang target riêng. Ngoài ra, weaver biến đổi bytecode tại method execution có thể quan sát các điểm mà proxy không quan sát. Luôn xác minh mô hình proxy và ranh giới "this" của chính công cụ đang sử dụng.

### 4.1 Cách khắc phục theo kiến trúc

- Đưa trách nhiệm cần advice vào một **thành phần được gọi qua proxy riêng**, nếu việc tách tầng phù hợp nghiệp vụ.
- Đảm bảo caller đi qua **tham chiếu proxy được quản lý** thay vì gọi trực tiếp target.
- Nếu mô hình cho phép, tổ chức lời gọi nội bộ thông qua một tham chiếu trung gian rõ ràng, nhưng tránh vòng lặp phụ thuộc hoặc lộ object gốc.
- Với các điểm bắt buộc không thể đi qua proxy, cân nhắc một **cơ chế weaving thích hợp** hoặc đặt bất biến nghiệp vụ ở nơi không phụ thuộc vào advice proxy.
- Không ép self-invocation quay lại proxy bằng kỹ thuật ẩn làm người đọc khó hiểu, nhất là với chính sách bảo mật; ưu tiên ranh giới thiết kế rõ ràng.

## 5. Handler nhận lời gọi nhưng pointcut không khớp

Nếu có bằng chứng `InvocationHandler` đã nhận invocation, bước tiếp theo là **đánh giá chính xác phương thức và điều kiện match**.

Các lỗi thường gặp:

| Nguyên nhân | Ví dụ | Cách kiểm tra |
| --- | --- | --- |
| Sai tên method | Chọn `save` nhưng lời gọi thực tế là `store` | So sánh tên method thật, không đoán theo endpoint |
| Overload khác | `save(String)` so với `save(Object)` | Xem parameter types và descriptor |
| Sai declaring type | Handler nhận `Method` của interface, bộ lọc đòi implementation class | Kiểm tra `method.getDeclaringClass()` và target runtime class riêng |
| Sai loại join point | Pointcut mô tả execution nhưng cơ chế hiện tại chỉ chặn proxy invocation | Xác minh mô hình được hỗ trợ |
| Annotation không ở chỗ đọc | Annotation khai báo trên implementation, code kiểm tra Method của interface | Đọc metadata đúng method; không mặc định annotation method được kế thừa |
| Chọn package/type quá hẹp | Lớp target không nằm trong nhóm khai báo | Kiểm tra phạm vi cấu trúc |
| Regex/biểu thức khác kỳ vọng | Mẫu tên bỏ sót hậu tố, overload hoặc lớp được sinh | Viết kiểm thử tập điểm match/không match |
| Kiểu động khác kiểu khai báo | Biến interface nhận implementation khác | Phân biệt `Method` tĩnh với `target.getClass()` |
| Generic erasure/bridge | Descriptor sau compile không giống tham số generic nhìn từ source | Xác minh quy tắc match và cách xử lý synthetic/bridge |
| Loại trừ chủ ý | Bộ lọc loại generated methods/namespace hạ tầng | Kiểm tra danh sách exclude được công bố |

### 5.1 Interface Method và implementation Method

Trong **JDK dynamic proxy**, handler thường nhận `Method` tương ứng khai báo ở **giao diện proxy**; nó không tự là `Method` khai báo bởi implementation class. Nếu điều kiện viết như sau:

~~~java
if (method.getDeclaringClass() == RealService.class) {
    // Có thể không khớp khi method đến từ interface.
}
~~~

Đây là mảnh minh họa, giả sử `RealService` đã tồn tại. Với lời gọi `interfaceService.run()` qua JDK proxy, `method.getDeclaringClass()` thường trả interface khai báo `run`. Điều kiện so sánh trực tiếp với `RealService.class` có thể false dù object target là RealService.

Một chiến lược chẩn đoán đúng hơn là **đọc cả hai** thông tin:
- `method.getDeclaringClass()` nói về nguồn khai báo của `Method`.
- `target.getClass()` nói về lớp runtime của đối tượng target mà handler giữ.
- Nếu cần method implementation thực sự, tra cứu theo tên/parameter types trên lớp thích hợp, lưu ý override, visibility, bridge và metadata.

### 5.2 Annotation không phải lúc nào cũng xuất hiện như kỳ vọng

Annotation gắn trên **phương thức interface** không tự mặc nhiên xuất hiện khi đọc một `Method` của implementation, và ngược lại. Annotation `@Inherited` của Java chỉ có ngữ nghĩa kế thừa dành cho **class declarations**, không khiến annotation ở method/parameter tự được kế thừa như class annotation.

Nếu pointcut phụ thuộc annotation:
1. Xác định metadata được đặt ở interface, base class, implementation hay parameter.
2. Xác định proxy handler/weaver đọc `Method` nào.
3. Kiểm tra retention và runtime visibility.
4. Kiểm tra cơ chế xử lý override/bridge nếu có.
5. Thêm test cho cả một trường hợp phải match và một trường hợp không match.

Đừng mở rộng pointcut "bắt tất cả" để che một sai lầm annotation; điều đó có thể làm advice chạy ở những vị trí không mong muốn.

## 6. Giới hạn theo loại proxy: interface, subclass và phương thức đặc biệt

**JDK dynamic proxy** là proxy dựa trên một hoặc nhiều interface. Nó nhận lời gọi tới những phương thức giao diện thích hợp qua `InvocationHandler`; nó **không tự tạo subclass của một concrete class bất kỳ**.

Các giới hạn chẩn đoán:

- **Phương thức chỉ tồn tại trên implementation**, không được công bố qua interface proxy: caller không thể gọi nó trực tiếp qua reference giao diện như một method interface.
- **Private method:** không phải một public instance interface method để JDK dynamic proxy chặn theo cách thông thường.
- **Static method:** gọi trên lớp, không dispatch thông qua object proxy instance theo nghĩa trên.
- **Constructor:** gọi `new Target()` không tự kích hoạt JDK proxy handler.
- **Final class:** vẫn có thể là underlying target của JDK interface proxy nếu nó triển khai interface phù hợp; tính `final` cản **subclassing**, không mặc định cản **interface delegation**.
- **Final method:** hạn chế override trong subclass proxy; nhưng một interface proxy độc lập vẫn có thể **chuyển tiếp** một lời gọi giao diện tới final method implementation nếu tương thích.
- **Default method của interface:** cách dispatch và xử lý method có thể phụ thuộc cách handler tiến hành chuyển tiếp; cần kiểm chứng riêng.
- **`equals`/`hashCode`/`toString`:** những method này có thể được dispatch tới JDK InvocationHandler, nhưng bộ lọc advice có thể chủ động loại chúng.

Một proxy dựa trên **subclass** có ràng buộc khác đối với `final`, `private`, visibility, module boundaries và dispatch nội bộ. Do đó, câu chẩn đoán phải bắt đầu bằng **“đây là proxy loại nào?”**, chứ không bằng quy tắc chung rằng mọi final method đều không được AOP.

## 7. Điều kiện runtime sai dù chữ ký đúng

Một điểm có thể vượt qua bộ chọn cấu trúc nhưng vẫn không thỏa ngữ cảnh:

- `args` thực tế khác giá trị mong muốn.
- Target runtime type không thuộc nhóm mà condition chọn.
- Bộ lọc chỉ bật với một tenant/môi trường/cờ tính năng và hiện đang tắt.
- Dữ liệu context gắn với thread không có trong thread thực thi hiện tại.
- Pointcut theo control flow không khớp đường gọi thật.
- Một validator thu hẹp phạm vi sau khi handler đã tiếp nhận.
- Điều kiện phụ thuộc một snapshot config cũ hoặc thay đổi không được công bố đúng cách giữa nhiều thread.

Ví dụ:

~~~text
matchesStructure = method == "submit(String)"
matchesContext   = enabled AND level == CRITICAL

selected = matchesStructure AND matchesContext
~~~

Đây là **giả mã**. Dù method submit được gọi qua proxy, advice không chạy khi `enabled=false` hoặc `level != CRITICAL` là hành vi **theo đúng thiết kế**, không phải lỗi weaving.

### 7.1 Kiểm tra giá trị mà không làm rò dữ liệu

Không mặc định in toàn bộ `args` để debug; tham số có thể chứa token, password, địa chỉ hoặc dữ liệu riêng tư. Thay vào đó, dùng event nhỏ:

~~~text
operation=submit
via_proxy=true
structural_match=true
runtime_match=false
reason=DISABLED
~~~

Không đưa raw args, response hoặc stack-trace message vào log khi chưa phân loại. Một advice ghi log nhạy cảm có thể tạo sự cố bảo mật nghiêm trọng hơn vấn đề kích hoạt ban đầu.

### 7.2 Kiểm tra cờ bật/tắt đúng thời điểm

Nếu proxy đọc cờ một lần **lúc khởi tạo** thay vì ở mỗi invocation, cập nhật config sau đó không nhất thiết có hiệu lực. Ngược lại, một handler đọc `AtomicBoolean` hoặc snapshot bất biến theo lời gọi có thể thay hành vi advice ngay cả khi proxy không tạo lại.

Cần phân biệt:
- **Configuration value mới đã tồn tại ở kho config?**
- **Proxy hiện tại đã đọc được value mới chưa?**
- **Điều kiện match hiện tại có dùng snapshot đó chưa?**

Không kết luận "reload thành công" chỉ vì tệp cấu hình đã cập nhật.

## 8. Advice bên ngoài short-circuit hoặc một nhánh khác được chọn

Nhiều proxy/interceptor có thể lồng nhau:

~~~text
Caller
  |
  v
CacheInterceptor
  |
  v
AuthorizationInterceptor
  |
  v
MetricsInterceptor
  |
  v
Target
~~~

Nếu CacheInterceptor trả kết quả từ cache **mà không gọi tiếp**, Authorization và Metrics bên trong có thể **không chạy**. Khi đó không phải pointcut của chúng sai; **control flow không đi tới chúng**.

Những nguyên nhân khác:
- Before advice bên ngoài ném lỗi.
- Around advice ngoài không gọi `proceed`.
- Retry interceptor chỉ tiếp tục trong một vài điều kiện.
- Circuit breaker từ chối ngay khi chưa đi tới target.
- Fallback trả sớm sau lỗi ở một lớp trước.
- Handler chỉ tạo một adapter khác và chuyển sang pipeline không mang advice dự kiến.

### 8.1 After-returning không phải finally

Giả sử code minh họa:

~~~text
before()
try:
    result = proceed()
    afterReturning(result)
    return result
catch error:
    afterThrowing(error)
    throw error
finally:
    afterFinally()
~~~

Đây là **giả mã cách tổ chức một wrapper**, không phải định nghĩa thứ tự advice phổ quát của mọi công cụ.

Nếu target ném ngoại lệ:
- Before có thể đã chạy.
- `afterReturning` **không chạy**, vì không có lần trả về bình thường.
- `afterThrowing` có thể chạy theo hợp đồng.
- `finally` của phạm vi đã được vào vẫn chạy.

Vì thế, câu “after advice không chạy” phải được xác định rõ là **after-returning, after-throwing hay finally**; một đoạn log chỉ đặt ở nhánh thành công sẽ không xuất hiện khi target lỗi.

### 8.2 Precedence làm advice nằm ở đâu?

Thứ tự thêm wrapper có thể khác thứ tự vào. Ví dụ:

~~~text
chain = Target
chain = Metrics(chain)
chain = Cache(chain)

effective = Cache(Metrics(Target))
~~~

Cache được thêm **sau** nhưng nằm **ngoài**. Khi cache hit, Metrics bị bỏ qua. Cần quan sát cấu trúc chain có hiệu lực, không suy từ tên file, thứ tự định nghĩa hoặc thứ tự khởi tạo nếu công cụ không bảo đảm.

## 9. Java 17 hoàn chỉnh: một chương trình, năm nguyên nhân

Chương trình sau dùng **JDK dynamic proxy** với:
- `WorkImpl` là target;
- `Work` là interface;
- proxy `InvocationHandler` in dấu **PROXY received** cho mọi lời gọi interface;
- pointcut minh họa chỉ chọn `submit(String)`;
- `AtomicBoolean` là điều kiện runtime bật/tắt advice;
- target có `outer()` gọi `submit()` **trên chính nó**;
- lời gọi trực tiếp tới target; nhánh success và exception.

Tạo một file duy nhất tên `ProxyAdviceDiagnosticsDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;

public class ProxyAdviceDiagnosticsDemo {
    interface Work {
        String submit(String id);
        String outer(String id);
        String status();
    }

    static final class WorkImpl implements Work {
        @Override
        public String submit(String id) {
            System.out.println("BODY submit " + id);
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("invalid id");
            }
            return "saved:" + id;
        }

        @Override
        public String outer(String id) {
            System.out.println("BODY outer " + id);
            // this là target WorkImpl, không phải proxy.
            return "outer>" + this.submit(id);
        }

        @Override
        public String status() {
            System.out.println("BODY status");
            return "OK";
        }
    }

    static Object callTarget(
            Work target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static Work wrap(Work target, AtomicBoolean enabled) {
        return (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[] { Work.class },
                (proxy, method, args) -> {
                    Object[] values =
                            args == null ? new Object[0] : args;

                    // Object methods có hợp đồng riêng.
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "toString" -> "WorkProxy";
                            case "hashCode" -> System.identityHashCode(proxy);
                            case "equals" -> proxy == values[0];
                            default -> throw new UnsupportedOperationException();
                        };
                    }

                    System.out.println(
                            "PROXY received " + method.getName());

                    boolean matches =
                            method.getName().equals("submit")
                            && Arrays.equals(method.getParameterTypes(),
                                    new Class<?>[] { String.class });

                    if (!matches) {
                        System.out.println("POINTCUT no match");
                        return callTarget(target, method, values);
                    }

                    if (!enabled.get()) {
                        System.out.println("ADVICE disabled");
                        return callTarget(target, method, values);
                    }

                    System.out.println("ADVICE before submit");
                    try {
                        Object result =
                                callTarget(target, method, values);
                        System.out.println("ADVICE after submit");
                        return result;
                    } catch (Throwable error) {
                        System.out.println("ADVICE error "
                                + error.getClass().getSimpleName());
                        throw error;
                    }
                });
    }

    public static void main(String[] args) {
        WorkImpl original = new WorkImpl();
        AtomicBoolean enabled = new AtomicBoolean(true);
        Work proxy = wrap(original, enabled);

        System.out.println("PROXY_CLASS "
                + Proxy.isProxyClass(proxy.getClass()));

        System.out.println("CASE through-proxy");
        System.out.println("RESULT " + proxy.submit("A"));

        System.out.println("CASE direct-target");
        System.out.println("RESULT " + original.submit("B"));

        System.out.println("CASE self-invocation");
        System.out.println("RESULT " + proxy.outer("C"));

        System.out.println("CASE nonmatching-method");
        System.out.println("RESULT " + proxy.status());

        enabled.set(false);
        System.out.println("CASE dynamic-disabled");
        System.out.println("RESULT " + proxy.submit("D"));

        enabled.set(true);
        System.out.println("CASE business-failure");
        try {
            proxy.submit("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac ProxyAdviceDiagnosticsDemo.java
java ProxyAdviceDiagnosticsDemo
~~~

Stdout theo logic chương trình:

~~~text
PROXY_CLASS true
CASE through-proxy
PROXY received submit
ADVICE before submit
BODY submit A
ADVICE after submit
RESULT saved:A
CASE direct-target
BODY submit B
RESULT saved:B
CASE self-invocation
PROXY received outer
POINTCUT no match
BODY outer C
BODY submit C
RESULT outer>saved:C
CASE nonmatching-method
PROXY received status
POINTCUT no match
BODY status
RESULT OK
CASE dynamic-disabled
PROXY received submit
ADVICE disabled
BODY submit D
RESULT saved:D
CASE business-failure
PROXY received submit
ADVICE before submit
BODY submit bad
ADVICE error IllegalArgumentException
CALLER invalid id
~~~

### 9.1 Đọc output như một bằng chứng chẩn đoán

| Ca | Có `PROXY received`? | Điều kiện chọn | Có advice? | Kết luận |
| --- | --- | --- | --- | --- |
| `through-proxy` | Có, cho submit | Match và enabled | Có, before/after | Đường bình thường |
| `direct-target` | Không | Không được đánh giá tại proxy | Không | Bypass proxy |
| `self-invocation` | Có cho outer; **không cho submit bên trong** | Outer không match | Không cho submit nội bộ | Self-invocation trên target |
| `nonmatching-method` | Có, cho status | Sai tên/chữ ký | Không | Pointcut/filter loại method |
| `dynamic-disabled` | Có, cho submit | Match nhưng cờ false | Không; chỉ dấu disabled | Điều kiện runtime loại advice |
| `business-failure` | Có, cho submit | Match và enabled | Before và error; không after-success | Nhánh exception |

**Tách ba loại chứng cứ:** `PROXY received` chứng minh handler đã nhận lời gọi; `POINTCUT no match` chứng minh loại trừ cấu trúc; `ADVICE disabled` chứng minh điều kiện động loại trừ. Không có `PROXY received` tại direct-target là dấu hiệu **đường gọi bypass proxy**, chứ không phải chứng minh pointcut không khớp.

### 9.2 Chương trình mô phỏng điều gì và không mô phỏng điều gì?

- **Có:** một proxy interface hoạt động thật trên JDK 17, phương thức target thật, reflection, so khớp chữ ký, cờ runtime, chuyển tiếp kết quả và ngoại lệ.
- **Không:** một ngôn ngữ pointcut chuẩn dùng cho mọi nền tảng hoặc weaving vào class bytecode.
- **Không:** lời gọi method-execution join point theo mọi công cụ AOP; đây là lời gọi đi qua JDK dynamic proxy.
- **Không:** xử lý quyền hoặc giao dịch production. Dòng `ADVICE` là tín hiệu kiểm thử, không phải hàng rào an ninh.
- **Không:** bảo đảm debug log có thể in mọi tham số. Mã chỉ in ID giả phục vụ bài học; với dữ liệu nhạy cảm thực, không dùng raw args hoặc raw error messages.
- **Không:** phân biệt mọi kịch bản subclass proxy, bởi final `WorkImpl` vẫn có thể được bọc bằng interface proxy ở đây.

### 9.3 Giải thích reflection exception

Trong `callTarget`, `Method.invoke` bọc lỗi ném từ thân method bằng `InvocationTargetException`. Nếu không tháo bọc, caller và nhánh error của handler có thể nhìn thấy **loại ngoại lệ khác** với hợp đồng nghiệp vụ. Ví dụ dùng `throw ex.getCause()` để truyền `IllegalArgumentException` gốc. Khi dùng JDK dynamic proxy, checked exceptions không được khai báo trong giao diện còn có thể bị bọc thành `UndeclaredThrowableException`; cần tôn trọng hợp đồng phương thức.

## 10. Chẩn đoán “handler có nhận nhưng không có log advice”

Trong một số hệ thống, handler đi qua nhiều lớp:

~~~text
Proxy
  |
  v
Invocation dispatcher
  |
  v
Pointcut matcher
  |
  v
Runtime condition
  |
  v
Advice chain
  |
  v
Target
~~~

Nếu chỉ thấy event từ dispatcher, cần đánh giá theo trình tự:
1. Matcher có nhận **đúng Method** không?
2. Method có cùng tên nhưng sai overload không?
3. Đây là method của interface hay implementation? Có annotation ở chỗ tương ứng không?
4. Điều kiện target/this/args/control flow có false không?
5. Interceptor có bị tắt bằng cấu hình/sampling không?
6. Có một wrapper khác short-circuit không?
7. Advice loại **before**, **after-returning**, **after-throwing** hay **finally**?
8. Trình ghi log có hoạt động/được xem đúng nơi không?

Để xác định rõ, dùng sự kiện với mã nguyên nhân hữu hạn:

~~~text
invocation-received
selection=STRUCTURE_FALSE
selection=CONTEXT_FALSE
selection=ENABLED
proceed-called
advice-enter
advice-success
advice-error
advice-finally
~~~

Các nhãn trên là **một schema debug đề xuất**, không phải API chung. Chỉ phát những nhãn thực tế phù hợp và có ràng buộc về chi phí, bảo mật.

### 10.1 Đừng chỉ nhìn log để kết luận advice không chạy

Một advice có thể chạy nhưng logger đang ở mức không xuất bản, trace bị sampling hoặc các event được gửi qua một exporter bất đồng bộ. Nếu đây là môi trường thử nghiệm đồng bộ, có thể tạm dùng **counter** hoặc một danh sách sự kiện trong bộ nhớ rồi assert số lần và thứ tự để phân biệt "không chạy" với "đã chạy nhưng không thấy log".

Không đưa dữ liệu riêng tư vào diagnostic trace. Khi debug xong cần gỡ hoặc hạ mức instrumentation để tránh overhead và rò dữ liệu.

## 11. Sau khi sửa code/cấu hình mà lỗi vẫn còn

**Thay source advice không tự bảo đảm proxy đang chạy dùng source mới.** Cần xác định:
- Proxy/handler có được xây dựng **trước khi** đổi cấu hình không?
- Handler dùng một snapshot cấu hình tại thời điểm khởi tạo hay đọc động theo invocation?
- Có nhiều instance hoặc nhiều process đang chạy phiên bản khác nhau không?
- Caller dùng object proxy phiên bản mới hay vẫn giữ tham chiếu cũ?
- Runtime classpath/class loader có tải nhầm phiên bản interface hoặc target không?
- Hệ thống có cache matcher/advice chain đã được làm mới khi cấu hình thay đổi chưa?
- Một bản build cập nhật có được triển khai vào process thực sự phục vụ lời gọi không?

Nếu một thành phần chỉ sử dụng cấu hình cố định tại lúc khởi tạo, có thể cần **tạo lại proxy hoặc redeploy**. Nếu JVM đang dùng class definition cũ, thay JAR trên đĩa không tự thay định nghĩa class đã nạp. Nhưng nếu advice đã được lắp và chỉ đọc một cờ động thì có thể đổi hành vi mà không tạo proxy mới; ví dụ `AtomicBoolean` trong chương trình minh họa trường hợp đó.

## 12. Một số bẫy nâng cao

### 12.1 Generic erasure và bridge

Java compiler có thể sinh bridge/synthetic methods để giữ dispatch generic. Một bộ quét `Method[]` có thể thấy nhiều method, nhưng không thể kết luận một bộ AOP sẽ tạo execution join point hoặc chạy advice thêm một lần cho mỗi bridge. Nếu matcher dựa vào kiểu khai báo/source, cần đọc quy tắc xử lý descriptor đã erase và bridge của cơ chế đang dùng.

### 12.2 Default method, Object methods và dispatch

JDK interface proxy nhận `equals`, `hashCode`, `toString` theo quy tắc của InvocationHandler. Nếu pointcut chỉ chọn method nghiệp vụ, việc không thấy advice khi gọi `toString()` có thể là **thiết kế loại trừ có chủ đích**. Trong chương trình mẫu, Object methods được handler xử lý trước logic match.

Đừng log `proxy.toString()` bên trong `toString` handler: có thể gọi lại handler và gây vòng lặp. Phương thức mặc định của interface cần được chuyển tiếp đúng ngữ nghĩa nếu muốn xử lý nó; không mọi handler đều tự có quy tắc giống nhau.

### 12.3 Phạm vi nhiều class loader và đối tượng nhìn giống nhau

Một loader có thể định nghĩa bản riêng của cùng tên class/interface; khi đó có thể gặp lỗi cast, module access hoặc proxy không nhìn đúng interface. Runtime object được tạo từ một class loader khác có thể không phải instance của Class object mà matcher đang dùng dù tên in ra giống nhau. Cần đối chiếu **class identity**, không chỉ class name.

### 12.4 Vòng lặp advice và đệ quy

Nếu trong handler có:

~~~text
on proxy.method():
    log(proxy.toString())
    return proxy.method() // tiếp tục qua chính proxy
~~~

thì rất có thể gọi lại chính handler. Chuyển tiếp đúng thường là target hoặc interceptor **kế tiếp**, không phải proxy hiện tại trừ khi cơ chế cố ý hỗ trợ tái nhập. Thêm breakpoint/event đánh dấu **depth** giúp phát hiện recursion nhưng phải giới hạn log để không làm đầy bộ nhớ.

### 12.5 Lỗi không biểu hiện thành exception ở đúng chỗ

Một phương thức có thể trả `Future`, `CompletionStage` hoặc handle tác vụ khác. Advice `after-returning` trên method tạo handle có thể chạy **khi handle được trả**, trước khi công việc bất đồng bộ hoàn tất. Nếu task lỗi sau đó, không thể mong cùng `after-throwing` đồng bộ tự ghi lỗi của tác vụ, trừ khi advice được gắn đúng vào cơ chế hoàn thành async.

### 12.6 Advice bị che do đặc thù logging

Một logger dùng mẫu không ổn định có thể lọc/mask mất một dòng, hoặc exporter rơi event vì backpressure. Để kiểm chứng không chạy, tốt nhất dùng test với **đếm invocation đã được chặn** thay vì suy từ một dòng log production.

## 13. Ma trận sửa lỗi nhanh

| Triệu chứng | Nghi vấn đầu tiên | Cách xác minh | Hướng xử lý |
| --- | --- | --- | --- |
| Target chạy nhưng handler im lặng | Bypass proxy | Kiểm tra object reference tại call site | Gọi qua proxy được quản lý |
| Proxy tồn tại nhưng caller vẫn có original | Lộ target | Theo dõi nơi cấp phát/gán tham chiếu | Đảm bảo đường vào chuẩn |
| Handler nhận outer, không nhận inner | Self-invocation trên target | In dấu tại outer/inner và handler | Tách ranh giới hoặc chọn weaving phù hợp |
| Handler nhận method nhưng advice không chạy | Sai pointcut/filter | So sánh signature, declaring type, annotation | Sửa selector chính xác |
| Interface method không thấy annotation | Metadata đặt trên implementation | Kiểm tra hai Method | Định nghĩa quy tắc annotation resolution |
| Advice chạy với overload A, không với B | Match không đủ chữ ký | Xem parameter types và overload | Thêm test cho từng overload |
| Chạy lúc enabled=true nhưng im khi false | Điều kiện runtime | Đo trạng thái cấu hình tại invocation | Thiết kế/ghi rõ flag semantics |
| Before chạy, after-success không chạy | Target ném lỗi | Quan sát error/finally branch | Không chờ after-returning trên error |
| Advice trong không chạy khi cache hit | Short-circuit lớp ngoài | Đối chiếu effective interceptor chain | Đặt advice bắt buộc ở ngoài cache hoặc bảo vệ tương đương |
| Method private/static/constructor không bị chặn | Ngoài khả năng interface proxy | Phân loại loại method và proxy | Chọn kỹ thuật weaving phù hợp |
| Final method không override được | Dùng subclass proxy | Kiểm tra final modifier | Thay interface proxy hoặc kiến trúc nếu thích hợp |
| Đổi pointcut mà runtime vẫn cũ | Handler/chain/cache phiên bản cũ | Kiểm tra artifact/config/loader | Rebuild/recreate/redeploy đúng mô hình |
| Log không thấy nhưng counter tăng | Sink/level/sampling | Assert sự kiện trong test | Kiểm tra telemetry pipeline |
| Advice chạy nhiều lần | Proxy lồng nhau/retry/nhiều join point | Đếm layer và invocation | Phân biệt request/attempt, xử lý precedence |
| Chỉ sai ở async | Sai kỳ vọng thời điểm hoàn tất | Phân biệt returned handle/completion | Gắn xử lý vào completion thích hợp |

## 14. Checklist chẩn đoán thực tế

Thực hiện theo trình tự để tránh sửa quá rộng:

- [ ] Ghi **method cần quan sát**, loại join point và kết quả kỳ vọng.
- [ ] Xác định **caller đang giữ proxy hay target** tại chính call site.
- [ ] Xác minh **loại proxy** (interface, subclass, custom wrapper) và phạm vi method nó có thể chặn.
- [ ] Thêm dấu vết an toàn, xác nhận **handler đã nhận invocation**.
- [ ] Nếu handler không nhận, kiểm tra direct call, self-invocation, factory/injection, loader và phiên bản runtime.
- [ ] Nếu handler nhận, so sánh chữ ký thật: method name, overload, declaring class, parameter types và annotation.
- [ ] Xác minh điều kiện runtime trên args/target/context và cờ enable/sampling.
- [ ] Kiểm tra thứ tự interceptor và khả năng short-circuit/exception trước advice.
- [ ] Phân biệt before, after-success, after-error và finally.
- [ ] Kiểm tra log level, exporter, sampling, async queue trước khi tuyên bố advice không chạy.
- [ ] Kiểm thử cả gọi qua proxy, gọi trực tiếp, lời gọi nội bộ, overload, null, exception và async.
- [ ] Kiểm tra bảo mật: không phát raw token/PII khi thêm diagnostic event.
- [ ] Sau khi sửa, tạo test regression có assertion rõ **thứ tự**, **số lần** và **kết quả/ngoại lệ**.
- [ ] Xác minh policy bắt buộc (authorization/audit) không dựa duy nhất vào một đường proxy dễ bypass.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Method `submit` chạy nghiệp vụ nhưng không có log handler. Có thể kết luận pointcut sai không?

**Đáp:** chưa thể. Trước tiên phải xác minh lời gọi đi qua proxy. Nếu gọi target trực tiếp, matcher chưa từng được đánh giá.

**Câu 2.** Client gọi `proxy.outer()`, bên trong `target.outer()` gọi `this.inner()`. Với proxy delegation riêng, vì sao advice của `inner` có thể không chạy?

**Đáp:** lời gọi nội bộ xảy ra trên target, không quay qua proxy; đây là vấn đề đường gọi. Một subtype-based proxy có thể có dispatch khác nên không nên tổng quát máy móc.

**Câu 3.** Handler nhận method của interface nhưng pointcut so `method.getDeclaringClass() == Impl.class`. Kết quả?

**Đáp:** có thể false vì Method trong JDK dynamic proxy thường được khai báo ở interface. Cần tách declared method và target runtime class.

**Câu 4.** Handler nhận `submit`, pointcut match, nhưng advice im lặng khi flag false. Có phải weaving lỗi?

**Đáp:** không nhất thiết; điều kiện động loại bỏ advice đúng theo cấu hình.

**Câu 5.** Before chạy nhưng after-returning không chạy khi target ném `IllegalArgumentException`. Đúng hay sai?

**Đáp:** đúng đối với ngữ nghĩa after-returning: không có một lần trả về bình thường. Cần quan sát error/finally branch.

**Câu 6.** Một `Cache` ở ngoài `Authorization` trả hit mà không proceed. Điều gì cần lo?

**Đáp:** Authorization ở trong có thể không chạy. Nếu mọi lần đọc phải kiểm tra quyền thì đây là rủi ro; cần đặt hàng rào đúng ranh giới.

**Câu 7.** Với JDK dynamic proxy, lớp target `final` có tự làm proxy bất khả thi không?

**Đáp:** không khi proxy dựa trên interface được target triển khai; `final` chủ yếu hạn chế subclass proxy.

**Câu 8.** Không thấy một dòng log advice ở production. Làm sao xác minh một cách ít phụ thuộc logger?

**Đáp:** dùng test với counter hoặc danh sách sự kiện tuần tự tại handler/advice; kiểm tra riêng telemetry level/sampling/exporter.

## 16. Tài liệu tham khảo

- [Java SE 17 – Dynamic Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): proxy class, giao diện, Object methods và runtime dispatch.
- [Java SE 17 – InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): hợp đồng handler, `Method`, `args`, ngoại lệ và Object methods.
- [Java SE 17 – Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)): reflection invocation, `InvocationTargetException`.
- [Java SE 17 – AtomicBoolean](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html): cờ thay đổi động có tính hiển thị giữa thread.
- [Java Language Specification – Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3): ngữ nghĩa `@Inherited` và giới hạn kế thừa annotation.

**Ghi nhớ:** muốn chẩn đoán **“lời gọi không kích hoạt advice”**, hãy đi từ **đường tham chiếu caller → proxy → handler → pointcut → runtime condition → advice chain → log sink**. Nếu một tầng không được đi qua, những tầng bên trong không thể tự có cơ hội chạy. Việc sửa đúng cần dựa vào **bằng chứng về đường thực thi và phạm vi chặn**, không chỉ thêm `println` vào một advice chưa chắc được gọi.
