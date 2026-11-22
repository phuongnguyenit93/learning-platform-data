# Ủy quyền qua giao diện so với tạo lớp con trung gian trong AOP qua proxy

## 1. Vấn đề: cùng là proxy, nhưng dựa vào hai cơ chế khác nhau

Trong **Aspect-Oriented Programming (AOP)**, một **aspect** gom các mối quan tâm xuyên suốt như đo thời gian, kiểm toán, ghi log, kiểm soát quyền hoặc chuyển đổi ngoại lệ. Một **pointcut** xác định những **join point** cần áp dụng **advice**. Khi chọn triển khai AOP qua **proxy**, chương trình không nhất thiết sửa bytecode của đối tượng nghiệp vụ; thay vào đó, caller làm việc với một đối tượng trung gian có thể chạy advice và chuyển tiếp thao tác.

Hai hướng xây dựng proxy thường gặp:

1. **Ủy quyền qua giao diện (interface-based delegation proxy)**: proxy triển khai một hay nhiều interface, nhận lời gọi qua các interface ấy rồi ủy quyền tới một **target riêng biệt**.
2. **Tạo lớp con trung gian (subclass-based proxy)**: proxy là một **subclass của kiểu target**, ghi đè những phương thức có thể override để chạy logic xen trước/sau và gọi phần triển khai của lớp cha hoặc ủy quyền theo chiến lược thiết kế.

Hai hướng này khác nhau sâu sắc về **quan hệ kiểu**, **đối tượng thực thi**, **lời gọi nội bộ**, **constructor**, **final/private method**, **trạng thái**, **quyền truy cập**, **kiểm thử** và **giới hạn phạm vi can thiệp**.

Bài tập trung vào **AOP tổng quát**. Java 17 được dùng làm nền tảng minh họa; JDK dynamic proxy là một API Java cụ thể, còn lớp con ghi đè thủ công chỉ minh họa cơ chế subclass proxy chứ không phải một engine sinh lớp con tự động.

## 2. Bộ khái niệm tối thiểu để so sánh hai kiểu proxy

**Caller** giữ reference dùng để gọi. **Proxy** là đối tượng trung gian; **target** thực thi nghiệp vụ. **Interface** quy định API được proxy giao diện triển khai; **subclass** là một kiểu kế thừa class và có thể ghi đè method hợp lệ. Một **interceptor** xử lý lời gọi trước/sau khi chuyển tiếp, còn **advice chain** thể hiện các lớp hành vi lồng nhau.

Trong AOP, **join point** là điểm can thiệp được hỗ trợ, **pointcut** chọn điểm đó, **advice** bổ sung hành vi và **weaving/interception** kết hợp hành vi vào luồng chạy. Đối với chương này, câu hỏi chính không phải thuộc tên thuật ngữ mà là **caller đang gọi object nào, lời gọi được chuyển tiếp bằng delegation hay override, và method ấy có thể được intercept tại điểm đó không**.

## 3. Hình dung hai cấu trúc

### 3.1. Ủy quyền qua giao diện

```text
              implements Interface
 Caller -----------------------> InterfaceProxy
                                      |
                                      | interceptor/advice
                                      v
                                Target implements Interface
                                      |
                                      v
                               Business operation
```

Tại đây **proxy và target là hai đối tượng riêng**. Proxy thường giữ reference tới target và chuyển tiếp lời gọi:

```text
proxy.operation(args):
    beforeAdvice()
    result = target.operation(args)
    afterAdvice()
    return result
```

Đây là **mã giả**; xử lý lỗi và finally sẽ phụ thuộc advice cụ thể.

### 3.2. Tạo lớp con trung gian

```text
                  extends BaseService
 Caller ------------------------------> GeneratedSubclass
                                           |
                                     override operation()
                                           |
                                     beforeAdvice()
                                           |
                                     super.operation()
                                           |
                                     afterAdvice()
```

Ở mô hình subclass **gọi super trên chính receiver proxy**, phần thân lớp cha chạy với `this` là đối tượng subclass. Khi phần thân ấy gọi một phương thức khác có thể override, Java có thể dispatch tới override ở subclass.

Một số giải pháp tạo lớp con nhưng **ủy quyền tới target riêng** thay vì gọi `super` trên receiver. Khi đó hành vi self-invocation có thể khác. Không được suy rằng “subclass proxy” tự động bảo đảm mọi lời gọi nội bộ đều đi qua advice.

## 4. Định nghĩa đúng “ủy quyền” và “kế thừa”

Trong thiết kế hướng đối tượng, **ủy quyền (delegation)** là việc một đối tượng trao trách nhiệm thực hiện công việc cho đối tượng khác. **Kế thừa (inheritance)** là quan hệ subtype giữa class con và class cha.

Một **interface proxy** thường thực hiện cả hai việc:

- Có kiểu tương thích với interface.
- Giữ target và **ủy quyền** thao tác tới target.

Một **subclass proxy** có thể:

- Có kiểu tương thích với class target, vì nó kế thừa class.
- Ghi đè phương thức và dùng `super.method(...)`.
- Hoặc kết hợp kế thừa với một target khác để **ủy quyền**, tùy engine.

**Điểm cần phân biệt:** “interface-based” và “subclass-based” chủ yếu nói về **quan hệ kiểu và cách can thiệp**, trong khi “delegation” nói về **cách chuyển thực thi**. Hai chiều này không luôn loại trừ hoàn toàn nhau.

## 5. So sánh nhanh

| Tiêu chí | Proxy dựa trên interface | Proxy dựa trên subclass |
| --- | --- | --- |
| Kiểu nhìn từ caller | Tương thích những interface proxy triển khai | Tương thích với class cha/kiểu target được kế thừa |
| Có cần interface? | Cần interface mà proxy sẽ hiện thực; có thể do ứng dụng định nghĩa | Không nhất thiết cần interface |
| Có cần subclass target? | Không | Có |
| Target có thể là `final class`? | Có thể, nếu có interface thích hợp và lời gọi qua proxy | Không thể kế thừa trực tiếp class final |
| Bắt method `final` của target? | Có thể can thiệp tại lời gọi interface nếu method đó là cách target hiện thực hợp đồng | Không thể override final method trong subclass |
| Bắt method `private`? | Không tự chặn private call trong target | Không thể override private method |
| Constructor | Proxy có constructor riêng, không chặn constructor target bằng interface dispatch | Tạo subclass đi qua constructor cha; không override constructor |
| Lời gọi nội bộ trên target | Thường bypass proxy nếu target tự gọi `this.method()` | Có thể dispatch vào override khi receiver thực sự là subclass proxy và method override được |
| Identity của proxy và target | Hai object riêng biệt trong mẫu ủy quyền | Có thể cùng một object proxy/subclass trong mẫu `super` |
| Method ngoài interface | Không gọi qua type interface trừ khi proxy có interface khác/adapter tương ứng | Có thể thấy method public/protected của class, nhưng intercept còn tùy override |
| Reflection/JVM | JDK `Proxy` cung cấp proxy interface | Cần lớp con thủ công hoặc công cụ tạo class/bytecode |
| Tương thích class loader/module | Interface và handler phải khả kiến/được phép | Class phải có thể kế thừa/khởi tạo/định nghĩa trong bối cảnh tương ứng |
| Debug | Có thể thấy handler, reflection, generated interface proxy | Có thể thấy subclass sinh, bridge/callback, super call |

Bảng mô tả **những nguyên lý điển hình**, không cam kết mọi AOP runtime đều giống nhau. Muốn đưa ra lựa chọn thực tế phải biết engine dùng interception nào và đường gọi có đi qua nó không.

## 6. JDK dynamic proxy theo interface hoạt động thế nào?

Java SE 17 có `java.lang.reflect.Proxy` và `InvocationHandler`. Một proxy instance được tạo bằng:

```java
Service proxied = (Service) java.lang.reflect.Proxy.newProxyInstance(
        Service.class.getClassLoader(),
        new Class<?>[] { Service.class },
        handler
);
```

Đoạn này chỉ là mảnh code minh họa; `Service` và `handler` phải được khai báo.

Bản thân generated proxy:

- **Implements** những interface được chỉ định.
- Sử dụng `InvocationHandler.invoke(proxy, method, args)` để xử lý lời gọi của các interface ấy.
- Là một class được tạo động, **không phải subclass của target class**.
- Có thể bọc một đối tượng target mà class target là `final`, miễn tương tác đi qua interface thích hợp.
- Được dùng thông qua kiểu interface, không phải ép kiểu thành một class target không liên quan.

Từ góc nhìn gọi hàm:

```text
caller.method(args)
   |
   v
generated interface proxy
   |
   v
InvocationHandler.invoke(proxy, Method, args)
   |
   +-- chọn advice
   +-- method.invoke(target,args)
   +-- xử lý kết quả / ngoại lệ
```

`Method.invoke` chỉ là một cách handler chuyển tiếp; một handler có thể dùng một adapter khác thay vì reflection. Việc proxy JDK sử dụng handler không có nghĩa mọi handler bắt buộc dùng reflection để gọi target.

### 6.1. Interface nào được đưa vào proxy?

Danh sách interface được đưa vào khi tạo proxy phải hợp lệ theo quy tắc API và class loader. Ví dụ nếu một class hiện thực thêm interface không có trong danh sách proxy, caller không tự nhiên có thể ép proxy về interface đó.

Trong Java 17, proxy JDK cần **interface hợp lệ**, không phải class. Sealed interface không được dùng như một proxy interface theo giới hạn `Proxy.newProxyInstance` của Java 17; kiểu interface phải khả kiến với loader và tương thích với module/access rules.

### 6.2. Xử lý `equals`, `hashCode` và `toString`

JDK dynamic proxy cũng chuyển những lời gọi của ba phương thức `Object` này qua `InvocationHandler` theo quy tắc API. Nếu một handler chỉ xử lý method nghiệp vụ và phản xạ mù quáng sang target, semantics identity của proxy có thể không khớp mong đợi.

Cần quyết định rõ:

- `proxy.equals(target)` hay `proxy.equals(anotherProxy)` có ý nghĩa gì?
- `hashCode` có nhất quán với `equals` không?
- `toString` có tiết lộ dữ liệu không nên công bố hoặc kích hoạt vòng gọi advice không?
- Có cần so sánh theo identity proxy, identity target hay business key?

Không có một quy tắc AOP chung bắt buộc mọi proxy phải dùng cùng chính sách equality.

### 6.3. Default method của interface

Một interface Java có thể có default method. Với dynamic proxy, lời gọi default method vẫn đi qua invocation handler; API Java 17 có cơ chế như `InvocationHandler.invokeDefault` để gọi implementation default trong trường hợp phù hợp. Không nên mặc định handler `method.invoke(target, args)` có cùng semantics với gọi default method trên proxy trong mọi thiết kế.

## 7. Subclass proxy dựa trên override hoạt động thế nào?

Java dùng dispatch động đối với những lời gọi instance method có thể override:

```java
class Worker {
    public String execute(String id) {
        return "done:" + id;
    }
}

class InterceptingWorker extends Worker {
    @Override
    public String execute(String id) {
        System.out.println("before");
        String result = super.execute(id);
        System.out.println("after");
        return result;
    }
}
```

Đây là đoạn class Java minh họa. `InterceptingWorker` được caller sử dụng như một `Worker`, vì nó **extends Worker**.

Một subclass proxy tự động có thể sinh override tương tự nhưng dùng dispatcher, method interceptor hoặc callback động. Tùy công cụ, override có thể gọi `super` hoặc ủy quyền sang target.

### 7.1. Tại sao `super.execute` lại quan trọng?

Trong một override, gọi `this.execute(id)` sẽ tiếp tục dispatch tới override hiện tại và có thể gây đệ quy vô hạn. Gọi `super.execute(id)` yêu cầu chạy phần triển khai của lớp cha theo cú pháp Java, tránh vòng lặp trực tiếp ở chính override đó.

Nhưng nếu phần thân `Worker.execute` lại gọi một **phương thức virtual khác**, lời gọi ấy có thể tiếp tục dispatch tới override trong subclass. Đây là nguồn tạo ra khác biệt khi gọi nội bộ và cũng là nguy cơ advice chạy nhiều lần.

### 7.2. Subclass proxy có phải target thật không?

Trong mẫu **lấy subclass instance làm receiver**, đối tượng proxy chính là một instance thuộc subtype của target class; trạng thái kế thừa nằm trên đối tượng ấy.

Trong mẫu **subclass giữ delegate target riêng**, có hai đối tượng: subclass proxy và target. Khi gọi vào delegate, những lời gọi nội bộ trong delegate vẫn dùng receiver của delegate, không tự dispatch sang subclass proxy.

Do đó phải kiểm tra thực tế engine tạo proxy của bạn đang dùng mẫu nào trước khi suy luận về self-invocation hoặc state.

## 8. Java 17 runnable: cùng nghiệp vụ, hai loại proxy, kết quả khác nhau

Ví dụ dưới đây có hai cách triển khai can thiệp:

1. **JDK interface proxy**: handler giữ `Worker target` riêng và gọi `Method.invoke` trên target.
2. **Subclass proxy**: `WorkerSubclassProxy extends Worker`, ghi đè `execute` và gọi `super.execute`.

Đoạn này cố ý để `Worker.batch` gọi `this.execute(id)`. Khi qua **interface proxy**, handler chỉ nhận lời gọi `batch` bên ngoài; target tự gọi `execute` trên target thật. Khi qua **subclass proxy với receiver là subclass**, `Worker.batch` kế thừa gọi `this.execute` và đi vào override.

Đây là **chương trình Java 17 độc lập**, minh họa cơ chế hướng đối tượng và proxy. Nó không phải bộ dệt tự động từ pointcut DSL.

Tạo file `ProxyMechanismsDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ProxyMechanismsDemo {

    interface Port {
        String execute(String id);
        String batch(String id);
    }

    static class Worker implements Port {

        @Override
        public String execute(String id) {
            System.out.println("business:execute:" + id);
            if ("ERR".equals(id)) {
                throw new IllegalStateException("business rejected");
            }
            return "done:" + id;
        }

        @Override
        public String batch(String id) {
            System.out.println("business:batch:" + id);
            return this.execute(id);
        }

        public final String version() {
            System.out.println("business:version");
            return "v1";
        }
    }

    static class WorkerSubclassProxy extends Worker {

        @Override
        public String execute(String id) {
            System.out.println("subclass:before:execute");

            try {
                String result = super.execute(id);
                System.out.println("subclass:after:execute");
                return result;
            } catch (RuntimeException error) {
                System.out.println("subclass:error:"
                        + error.getClass().getSimpleName());
                throw error;
            }
        }

        // batch() kế thừa từ Worker, không override.
        // version() là final nên không thể override.
    }

    public static void main(String[] args) {
        Worker target = new Worker();

        Port interfaceProxy = (Port) Proxy.newProxyInstance(
                Port.class.getClassLoader(),
                new Class<?>[] { Port.class },
                (proxy, method, values) -> {
                    String methodName = method.getName();
                    System.out.println("interface:before:" + methodName);

                    try {
                        Object result = method.invoke(target, values);
                        System.out.println("interface:after:" + methodName);
                        return result;
                    } catch (InvocationTargetException wrapper) {
                        Throwable original = wrapper.getCause();
                        System.out.println("interface:error:"
                                + original.getClass().getSimpleName());
                        throw original;
                    }
                }
        );

        Worker subclassProxy = new WorkerSubclassProxy();

        System.out.println("case:interface-single");
        System.out.println("caller:" + interfaceProxy.execute("A"));

        System.out.println("case:interface-batch");
        System.out.println("caller:" + interfaceProxy.batch("B"));

        System.out.println("case:subclass-single");
        System.out.println("caller:" + subclassProxy.execute("C"));

        System.out.println("case:subclass-batch");
        System.out.println("caller:" + subclassProxy.batch("D"));

        System.out.println("case:subclass-final");
        System.out.println("caller:" + subclassProxy.version());

        System.out.println("case:direct");
        System.out.println("caller:" + target.batch("E"));

        System.out.println("case:interface-error");
        try {
            interfaceProxy.execute("ERR");
        } catch (IllegalStateException error) {
            System.out.println("caller:error:" + error.getMessage());
        }

        System.out.println("case:subclass-error");
        try {
            subclassProxy.execute("ERR");
        } catch (IllegalStateException error) {
            System.out.println("caller:error:" + error.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ProxyMechanismsDemo.java
java ProxyMechanismsDemo
```

**Stdout dự kiến:**

```text
case:interface-single
interface:before:execute
business:execute:A
interface:after:execute
caller:done:A
case:interface-batch
interface:before:batch
business:batch:B
business:execute:B
interface:after:batch
caller:done:B
case:subclass-single
subclass:before:execute
business:execute:C
subclass:after:execute
caller:done:C
case:subclass-batch
business:batch:D
subclass:before:execute
business:execute:D
subclass:after:execute
caller:done:D
case:subclass-final
business:version
caller:v1
case:direct
business:batch:E
business:execute:E
caller:done:E
case:interface-error
interface:before:execute
business:execute:ERR
interface:error:IllegalStateException
caller:error:business rejected
case:subclass-error
subclass:before:execute
business:execute:ERR
subclass:error:IllegalStateException
caller:error:business rejected
```

### 8.1. Trường hợp interface proxy gọi `execute`

Caller giữ `Port interfaceProxy`, nên lời gọi `execute("A")` được dispatcher chuyển đến handler. Handler in `interface:before`, gọi target thực qua reflection, sau đó in `interface:after` rồi trả chuỗi `done:A`.

**Proxy không phải instance của class `Worker`** ở cách này. Nó chỉ được tạo để triển khai `Port`.

### 8.2. Trường hợp interface proxy gọi `batch`

Handler chỉ nhận `batch("B")` bên ngoài:

```text
interfaceProxy.batch(B)
  -> handler (method=batch)
  -> target.batch(B)
     -> target.this.execute(B)   // ở trong target
  -> handler returns
```

Vì `execute` bên trong được gọi trên `target`, nó không quay ngược qua handler proxy. Ta **không thấy** `interface:before:execute` cho lời gọi nội bộ ấy.

Đây là biểu hiện điển hình của **self-invocation bypass** với cấu trúc ủy quyền qua một target riêng.

### 8.3. Trường hợp subclass proxy gọi `batch`

Caller gọi `subclassProxy.batch("D")`, mà `batch` là phương thức **kế thừa từ `Worker`**. Vì receiver thực tế là `WorkerSubclassProxy`, bên trong `Worker.batch`:

```java
return this.execute(id);
```

là một lời gọi virtual đến override trong subclass. Vì vậy có `subclass:before:execute` và `subclass:after:execute` cho lời gọi nội bộ.

**Giới hạn kết luận:** hiện tượng này đúng với **mẫu subclass receiver + super call** trong ví dụ và Java dispatch. Nó không phải bảo đảm rằng mọi công cụ quảng bá “subclass proxy” đều chặn self-invocation; nếu công cụ gọi vào một delegate riêng, hành vi có thể khác.

### 8.4. Trường hợp `version()` là final

`version` thuộc `Worker` và được khai báo `final`. `WorkerSubclassProxy` kế thừa nó nhưng **không thể ghi đè** để chèn advice theo kỹ thuật override. Caller gọi `subclassProxy.version()` sẽ chỉ thấy `business:version`.

Điều này không nói rằng `final` làm mọi kỹ thuật AOP bất khả thi. Một cơ chế **weaving bytecode trực tiếp** hoặc một **wrapper interface phù hợp** có thể can thiệp tại ranh giới khác mà không cần override final method.

### 8.5. Ngoại lệ qua hai proxy

Trường hợp `ERR` cho thấy cả hai cách có thể chuyển đúng `IllegalStateException` về caller:

- Interface handler gọi target qua `Method.invoke`. Khi target ném lỗi, reflection bọc tạm thời trong `InvocationTargetException`; handler lấy `getCause()` và ném lại.
- Subclass override gọi `super.execute` trực tiếp; nó bắt `RuntimeException` và ném lại, không có lớp bọc reflection trong nhánh này.

Nếu handler ném một **checked exception không được interface khai báo**, proxy JDK có thể bọc bằng `UndeclaredThrowableException` theo hợp đồng của `Proxy`. Không được mặc định mọi ngoại lệ đều đi qua nguyên dạng.

## 9. Kiểu của proxy ảnh hưởng API của caller

Với interface proxy:

```java
Port service = interfaceProxy;
```

Câu trên hợp lệ trong ví dụ. Nhưng:

```java
Worker worker = (Worker) interfaceProxy;
```

sẽ thất bại khi chạy vì JDK dynamic proxy không kế thừa `Worker`; nó chỉ triển khai `Port`.

Ngược lại:

```java
Worker worker = new WorkerSubclassProxy();
```

hợp lệ vì subclass proxy **là một subtype của `Worker`**.

Đây là khác biệt đáng cân nhắc:

- Nếu API hiện hữu nhận/trả **interface**, interface proxy thuận lợi.
- Nếu API yêu cầu **concrete class**, interface proxy có thể không thay thế được mà không sửa ranh giới API.
- Subclass proxy có thể dùng ở vị trí cần base class, nhưng chỉ khi class có thể được kế thừa và khởi tạo hợp lệ.
- Một ứng dụng chỉ giữ target concrete reference và tự gọi trực tiếp sẽ không tự động bắt đầu dùng proxy.

### 9.1. Interface nhỏ giúp giảm coupling

Khi thiết kế từ đầu, việc định nghĩa một **port/interface** cho thao tác quan trọng có thể hỗ trợ decorator, fake trong kiểm thử và proxy. Tuy nhiên, không nên tạo interface chỉ để che một rào cản tạm thời mà không có hợp đồng rõ.

Nếu một thư viện không cung cấp interface, ứng dụng có thể tạo interface do mình sở hữu và viết **adapter** để ủy quyền tới thư viện. Khi ấy proxy chỉ bao những lời gọi đi qua adapter, chứ không trở thành subclass hoặc can thiệp mọi method vendor.

## 10. Hạn chế `final`, `private`, `static` và constructor

### 10.1. `final class`

Java không cho tạo subclass trực tiếp từ final class. Một subclass-based proxy cần kế thừa class target sẽ không áp dụng được qua cơ chế kế thừa thông thường.

JDK interface proxy **có thể** bao quanh lời gọi interface vào đối tượng target final, vì proxy không cần kế thừa target.

### 10.2. `final method`

Subclass không thể override final method, nên không thể chèn advice **bằng override ở chính method đó**.

Một interface proxy có thể can thiệp trước khi gọi final implementation nếu lời gọi đi qua method tương ứng trên interface. Interface proxy chặn **ranh giới gọi qua proxy**, không sửa final method bên trong target.

### 10.3. `private method`

Private method không thể được override. Subclass proxy không biến lời gọi private trong lớp cha thành virtual dispatch qua override.

Nếu cần theo dõi private method, phải cân nhắc điểm public boundary hoặc một công cụ weaving có mô hình pointcut/khả năng biến đổi sâu thích hợp.

### 10.4. `static method`

Static method thuộc class, không được override theo nghĩa đa hình instance. JDK interface proxy không thể chặn một lời gọi tĩnh trên class target bằng dispatch interface thông thường.

Một lời gọi static có thể được quan sát bằng **call-site weaving** nếu công cụ hỗ trợ; đó là cơ chế khác với interface/subclass proxy.

### 10.5. Constructor

Constructor không được kế thừa hay override như instance method. Subclass constructor gọi constructor của superclass theo quy tắc Java.

Một subclass proxy phải có đường khởi tạo hợp lệ. Nếu base class chỉ có constructor không thể truy cập hoặc yêu cầu tham số, một bộ sinh lớp con phải đáp ứng các ràng buộc ấy; có công cụ dùng chiến lược khởi tạo riêng nhưng không thể giả định an toàn cho mọi class.

**Tránh gọi phương thức overridable trong constructor của base class.** Khi base constructor gọi một virtual method, override của subclass có thể chạy trước khi state riêng của subclass được khởi tạo đầy đủ. Với subclass proxy, đây là lỗi thiết kế rất khó chẩn đoán.

## 11. Self-invocation: điều gì thực sự quyết định có advice?

Câu “self-invocation luôn bỏ qua AOP” là **quá rộng**. Cần hỏi:

1. Receiver của lời gọi nội bộ là **target** hay **proxy**?
2. Method được gọi có thể **override/virtual dispatch** không?
3. Interception được cài ở **proxy entry**, **subclass override**, hay **method body weaving**?
4. Có advice ngoài nào chặn `proceed` không?
5. Một method được dệt có sử dụng proxy chain bên trong hay không?

Mô hình:

| Tình huống | Lời gọi nội bộ đi đâu? | Khả năng advice |
| --- | --- | --- |
| Delegate target gọi `this.execute()` | Target → target | Bypass interface proxy ngoài |
| Base method chạy trên subclass proxy, gọi virtual `this.execute()` | Dispatch tới subclass override | Có thể intercept override |
| Base method gọi `super.execute()` ở subclass | Gọi phần triển khai superclass | Không đi qua override cùng điểm đó |
| Base method gọi private/final method | Không thể override bằng subclass | Subclass-override interception không có |
| Method body đã được bytecode weaving | Đường nội bộ đi qua body đã dệt | Có thể có advice theo pointcut/weaving |
| Caller vẫn giữ target gốc, gọi trực tiếp | Không đi qua proxy | Không có proxy-entry advice |

Do đó, **phạm vi can thiệp là thuộc tính của đường gọi thực tế**, không chỉ của từ “proxy”.

## 12. Subclass proxy và trạng thái đối tượng

Khi subclass proxy **tự là đối tượng nghiệp vụ**, state trong field kế thừa thuộc proxy:

```text
WorkerSubclassProxy instance
  +-- fields kế thừa từ Worker
  +-- fields riêng của subclass
  +-- overrides
```

Khi interface proxy giữ **một target riêng**, state nghiệp vụ thuộc target:

```text
InterfaceProxy instance            Worker target instance
  +-- handler                       +-- business fields
  +-- reference to target --------> +-- methods
```

Nếu ứng dụng đã tạo một `Worker` có state từ trước rồi tạo một subclass proxy **mới**, không thể mặc định đối tượng mới mang toàn bộ state, identity hoặc lock của target cũ.

Các lựa chọn của engine (delegate riêng, dùng target thực, tạo đối tượng mới, chuyển state...) có thể tác động:

- Identity (`==`) và equality.
- Lifecycle/constructor side effect.
- Field có tính chất bất biến, `final`, hoặc resource handle.
- Synchronization và monitor lock.
- Cache dựa trên identity/object reference.
- Trạng thái đã được khởi tạo bên ngoài proxy.
- Serialization và framework phản xạ phụ thuộc exact class.

**Đừng tự “copy field”** để biến một đối tượng đang hoạt động thành subclass proxy nếu không hiểu tính nhất quán và lifecycle. Nhiều resource và invariant không thể sao chép an toàn.

## 13. Identity và `equals`/`hashCode`

Trong giao diện ủy quyền, proxy và target là hai object khác nhau:

```text
proxy != target
```

Điều này vẫn đúng nếu handler chuyển hầu hết lời gọi tới target.

Các tình huống cần thiết kế:

- Một map/set chứa target hay proxy làm key?
- Equality giữa hai proxy bao cùng target phải ra sao?
- `hashCode` có nhất quán khi target thay đổi trạng thái không?
- Handler nên xử lý `toString` như thế nào để không để lộ dữ liệu hoặc tự gọi lại proxy?

Subclass proxy thường là một subtype của class target, nhưng **không có bảo đảm equality giống hệt target cũ** nếu có object mới hoặc `equals`/`hashCode` dựa vào exact class hay field.

### 13.1. `getClass()` và class-based logic

Khi dùng proxy, `object.getClass()` có thể trả **class proxy sinh**, không phải concrete target class. Điều đó ảnh hưởng mã dùng so sánh exact class:

```java
if (value.getClass() == Worker.class) {
    // ...
}
```

Đây là mảnh minh họa. Nó có thể không chạy đúng kỳ vọng với subclass proxy hoặc JDK proxy. Nên ưu tiên hợp đồng interface, `instanceof` phù hợp và metadata API được thiết kế rõ thay vì coi exact runtime class luôn là business type.

## 14. Interception và ngoại lệ: giữ đúng hợp đồng

Một proxy có thể quan sát/đổi ngoại lệ ở **ranh giới ngoài**. Cần phân biệt:

- Lỗi do target ném.
- Lỗi từ handler/interceptor trước `proceed`.
- Lỗi từ after advice khi target đã hoàn thành.
- Lỗi của proxy framework hoặc reflection.
- Lỗi do một advice khác trong chuỗi ném.

### 14.1. Interface handler và `InvocationTargetException`

Nếu handler dùng `Method.invoke`, checked wrapper `InvocationTargetException` bao lỗi do target ném. Handler có thể lấy `getCause()` để truyền tiếp đúng loại lỗi.

Đừng ném nguyên `InvocationTargetException` không khai báo qua proxy interface rồi kỳ vọng caller thấy lỗi nghiệp vụ giống như gọi target. Chữ ký interface và quy tắc checked exceptions của JDK Proxy có thể dẫn tới `UndeclaredThrowableException`.

### 14.2. Subclass override và `super`

Một override gọi `super.method()` trực tiếp không đi qua `Method.invoke`, nên lỗi target/super có thể được quan sát bằng Java `try/catch` thường. Nhưng một engine subclass dùng dispatcher và reflection vẫn có thể có wrapper kỹ thuật của riêng nó; **đừng đồng nhất mọi subclass proxy với một override thủ công đơn giản**.

### 14.3. Advice sau khi return có thể đổi “thành công” thành “lỗi”

Nếu method gốc hoàn thành và interceptor sau ném lỗi, caller có thể nhận ngoại lệ dù side effect đã xảy ra. Với retry, phải xem thao tác có idempotent không. Đây là rủi ro của **advice semantics**, không phải điểm riêng của interface hay subclass.

## 15. Lớp sinh, visibility, module và class loader

Một proxy được sinh khi chạy phải thỏa quy tắc của môi trường Java:

- Interface phải khả kiến đối với loader dùng để tạo JDK proxy.
- Những interface non-public có các ràng buộc về package/module.
- Một số tổ hợp interface có chữ ký trùng nhưng kiểu trả về không tương thích có thể không tạo proxy được.
- Named module và `exports`/`opens` ảnh hưởng khả năng reflection sâu và việc định nghĩa/truy cập class.
- Subclass proxy phải được định nghĩa trong bối cảnh cho phép kế thừa target và truy cập constructor/method phù hợp.
- Package-private member và protected access phụ thuộc package/runtime package, quan hệ kế thừa và module.
- Một class có thể nhìn thấy qua loader này nhưng helper/interceptor không khả kiến qua loader khác.

### 15.1. Đừng nhầm public API với toàn quyền reflection

Dùng interface public qua JDK proxy có thể tránh nhu cầu đọc các private field của target. Ngược lại, một subclass proxy tạo động có thể cần mở rộng khả năng tạo/định nghĩa class.

`setAccessible(true)` không phải chiếc chìa khóa vượt qua mọi module boundary. Cần tuân thủ quy tắc Java module system và cấu hình được phép.

### 15.2. Sealed class/interface

Java 17 hỗ trợ sealed types hạn chế những subtype có thể xuất hiện. Một subclass sinh động không nằm trong tập subtype được phép có thể không kế thừa sealed class hợp lệ.

JDK dynamic proxy của Java 17 cũng có giới hạn về việc sử dụng sealed interface làm proxy interface. Vì vậy không thể suy rằng “có interface” là đủ; phải kiểm tra interface **có được API proxy hỗ trợ không**.

### 15.3. Class loader identity

Trong JVM, định danh class phụ thuộc tên nhị phân và defining loader. Một proxy sinh ở loader khác hoặc không thấy interface/helper class có thể thất bại khi định nghĩa, ép kiểu hoặc gọi method.

Trong hệ thống plugin/container, hãy kiểm thử đúng bố trí loader/runtime production, không chỉ trong một project đơn module đơn giản.

## 16. Default methods và method resolution

Interface Java có thể chứa default method. Với JDK dynamic proxy, lời gọi trên interface có thể chuyển vào handler và cần một chiến lược rõ nếu muốn gọi default implementation.

Với subclass, method dispatch dựa trên các quy tắc kế thừa, override, super call và interface default method resolution của Java.

Một số trường hợp đặc biệt:

- Một interface proxy hiện thực nhiều interface có **chữ ký method trùng nhau**. Handler có thể nhận `Method` liên quan tới interface xuất hiện trước theo quy tắc `Proxy`, không nhất thiết đúng với kiểu reference ở call site.
- Default method có thể cần `InvocationHandler.invokeDefault` nếu muốn gọi implementation mặc định trên proxy.
- Covariant return types và bridge methods do compiler tạo có thể ảnh hưởng reflection/method interception.
- Method `equals`/`hashCode`/`toString` cần chiến lược rõ.
- Một method trong interface không có nghĩa target tự động triển khai hành vi đúng hợp đồng sau khi handler ủy quyền sai.

Không nên suy từ một ví dụ `execute(String)` đơn giản rằng mọi tổ hợp interface nhiều kế thừa luôn có một đường chuyển tiếp duy nhất.

## 17. Constructor, lifecycle và dependency

Một proxy thường được sử dụng như một component có lifecycle:

```text
Construct target
  -> configure target
  -> create proxy/wrapper
  -> give proxy reference to callers
  -> invoke methods through proxy
  -> close/cleanup according to ownership
```

Với giao diện ủy quyền, cần quyết định **ai sở hữu vòng đời của target**. Ví dụ: proxy đóng mà target vẫn được nơi khác sử dụng thì chuyện gì xảy ra?

Với subclass proxy, việc khởi tạo class con đi qua constructor chain và có thể gây side effect. Nếu class yêu cầu factory riêng, bất biến nội bộ, native resources hoặc kiểm tra identity, subclass proxy có thể không thích hợp.

### 17.1. Nhận proxy phải xảy ra trước khi rò rỉ target

Nếu code tạo target rồi truyền reference target thật ra ngoài trước khi gắn proxy, các caller giữ target có thể tiếp tục bypass advice. Điều này đặc biệt nguy hiểm với chính sách kiểm tra quyền nếu chỉ dựa vào proxy.

Nên đưa một **ranh giới tạo đối tượng được quản lý** vào thiết kế khi yêu cầu mọi lời gọi đều qua interception.

### 17.2. Proxy không tự quản lý tất cả lifecycle methods

Constructor, finalizer, static initializer và các hành vi không qua interface/subclass override không tự được can thiệp. Nếu một chính sách phải bao cả vòng đời đối tượng, cần dùng API lifecycle/factory thích hợp hoặc cơ chế weaving có khả năng quan sát ranh giới đó.

## 18. Hiệu năng: không nên chọn theo định kiến “reflection luôn chậm”

Interface proxy dùng handler; subclass proxy có thể dùng override và dispatcher. Tuy nhiên không thể kết luận một cơ chế luôn nhanh hơn trong mọi môi trường:

- Chi phí tạo proxy thường khác chi phí mỗi invocation.
- Handler có thể dùng `Method.invoke`, method handle hoặc adapter được tối ưu tùy triển khai.
- Subclass proxy có thể thực hiện dispatch qua callback phức tạp, không nhất thiết là một lời gọi `super` đơn giản.
- JVM JIT có thể tối ưu nhiều đường gọi phổ biến tùy profile.
- Tỷ lệ pointcut khớp, số advice và nội dung advice quyết định overhead tổng.
- Logging I/O hoặc chính sách kiểm toán có thể tốn hơn chính interceptor nhiều bậc.
- Class generation/verification và startup/memory footprint có thể đáng kể với hệ thống tạo nhiều loại proxy.

Muốn quyết định theo hiệu năng, hãy đo với workload đại diện: baseline không proxy, interface proxy, subclass proxy, cùng advice và cùng số invocation. Kiểm tra throughput, latency p50/p95/p99, allocation, GC và warm-up. Tránh benchmark có `System.out.println` trong hot loop rồi suy ra chi phí dispatch.

## 19. Khi có nhiều proxy/advice lồng nhau

Một target có thể được bao bởi nhiều tầng:

```text
Caller
   |
   v
Tracing Proxy
   |
   v
Security Proxy
   |
   v
Business Target
```

Khi đó:

- Thứ tự advice ảnh hưởng ngoại lệ, return value và việc target có được gọi hay không.
- Một outer advice có thể từ chối trước khi inner nhận lời gọi.
- Một lớp có thể đổi exception khiến lớp ngoài nhìn thấy lỗi đã biến đổi.
- Nếu mỗi tầng proxy giữ target khác, identity và loại runtime có thể khác kỳ vọng.
- Có thể phát sinh double interception khi vô tình bọc cùng một component nhiều lần.
- Một proxy JDK có thể giữ một subclass proxy làm target nếu các ràng buộc kiểu phù hợp; cơ chế có thể kết hợp, không loại trừ nhau.

Ví dụ:

```text
AuditAround(MetricsAround(BusinessOperation))
```

Lỗi `MetricsAround` ném sau khi business thành công có thể bị `AuditAround` hiểu nhầm là lỗi nghiệp vụ. Kiểm thử nhiều advice phải xét **nguồn lỗi và thứ tự thực tế**, không chỉ log cuối.

## 20. Thiết kế pointcut khi chỉ có proxy entry

Một pointcut rộng trên tên method có thể chọn nhiều thao tác không thuộc yêu cầu. Nhưng pointcut đúng về chữ ký vẫn không đảm bảo advice chạy nếu đường gọi **bypass proxy**.

Hai chiều cần kiểm thử riêng:

1. **Matching:** method được chọn đúng hay không?
2. **Reachability:** invocation có đi qua object proxy và interceptor không?

Ví dụ chính sách “ghi audit mọi thao tác thay đổi dữ liệu”:

- Mẫu tên phương thức có thể bỏ sót một method mới không theo convention.
- Một internal call trên delegate có thể không đi qua interface proxy.
- Một final method có thể không được subclass override.
- Một caller giữ target thật có thể bỏ qua toàn bộ chain.
- Một advice ngoài có thể không tiếp tục đến target.

**Bài học:** một cơ chế interception được chọn để triển khai chính sách quan trọng phải được xem xét cùng kiến trúc luồng gọi, không chỉ cú pháp pointcut.

## 21. Khi nào chọn interface proxy?

Interface proxy thường đáng xem xét khi:

- Chương trình đã dùng **interface rõ ràng** để mô tả port hoặc service contract.
- Muốn bọc một đối tượng có class final nhưng triển khai interface có thể proxy.
- Không cần can thiệp private/helper/constructor bên trong target.
- Muốn decorator dễ kiểm thử, dễ thay implementation.
- Có khả năng kiểm soát cách caller nhận reference, để mọi đường quan trọng dùng proxy.
- Muốn giảm phụ thuộc vào cấu trúc kế thừa và constructor của vendor class.

Cần đánh giá rủi ro:

- Caller yêu cầu concrete class chứ không phải interface.
- Một số method không nằm trong interface.
- Lời gọi trực tiếp/self-invocation trên target bypass handler.
- Handler xử lý default methods, equals/hashCode và checked exception chưa đúng.
- Interface/module/class loader không thỏa quy tắc tạo proxy.

## 22. Khi nào chọn subclass proxy?

Subclass proxy có thể phù hợp khi:

- Caller cần object tương thích với **concrete base class**.
- Class target **không final** và có constructor/visibility phù hợp.
- Những điểm muốn intercept là các method có thể **override**.
- Thiết kế có thể chấp nhận class con được tạo động và lifecycle liên quan.
- Engine xử lý đúng state, constructor, module access và return/exception semantics.
- Hành vi inherited virtual dispatch là yếu tố cần thiết và đã được kiểm chứng.

Cần đánh giá rủi ro:

- Class final, sealed hoặc không cho phép subclass hợp lệ.
- Method final/private/static không thể override.
- Constructor khó khởi tạo hoặc gọi virtual method quá sớm.
- Mã nghiệp vụ dùng exact class checks, equality hoặc serialization nhạy với subtype.
- Subclass proxy ủy quyền vào một target khác, khiến self-invocation không giống tưởng tượng.
- Generated class và helper không thể liên kết qua loader/module.

## 23. Nếu cả hai lựa chọn đều không đủ

Không phải mọi bài toán AOP đều nên ép vào một kiểu proxy. Một số phương án khác:

- **Application-owned facade/adapter:** tập trung call site, giúp kiểm soát contract mà không sửa vendor class.
- **Hook/callback chính thức:** nếu thư viện có extension API phù hợp.
- **Compile-time hoặc load-time weaving:** nếu cần can thiệp vào method execution/internal calls mà proxy entry không nhìn thấy, và có năng lực/quyền cần thiết.
- **Bytecode instrumentation có kiểm soát:** có thể phù hợp với tracing sâu hoặc thư viện bên thứ ba, nhưng đòi hỏi kiểm thử tương thích và phạm vi chặt.
- **Thiết kế lại ranh giới nghiệp vụ:** thay vì intercept mọi private helper, đặt policy ở một operation boundary có ý nghĩa.
- **Client/network interceptor:** khi đối tượng cần quan sát là service ngoài tiến trình.

Không nên hạ yêu cầu bảo mật hoặc kiểm toán bắt buộc xuống “proxy có vẻ chạy trong một demo” nếu vẫn có đường bypass chưa được xử lý.

## 24. Ma trận kiểm thử bắt buộc

| Ca | Interface proxy delegation | Subclass proxy override |
| --- | --- | --- |
| Gọi method qua proxy | Handler phải nhận | Override phải nhận nếu method được intercept |
| Gọi target trực tiếp | Không qua handler | Không qua instance subclass nếu là target khác |
| Target tự gọi `this.virtualMethod()` | Thường bypass handler ngoài | Có thể vào override nếu receiver subclass |
| Method final | Có thể bắt ở interface boundary | Không override được |
| Method private | Không nhìn thấy private call bên trong | Không override được |
| Class final | Có thể nếu có interface phù hợp | Không subclass được |
| Interface không có method cần gọi | Không bắt bằng JDK proxy của interface đó | Có thể intercept concrete method nếu override được |
| Method ném ngoại lệ | Handler phải giữ cause/contract | Override giữ exception semantics |
| Checked exception | Đúng interface `throws`, tránh bọc bất ngờ | Đúng quy tắc override và `throws` của Java |
| Advice ném sau return | Caller có thể nhận lỗi sau side effect | Tương tự |
| `equals/hashCode/toString` | Handler kiểm soát theo API proxy | Có thể kế thừa/override tùy method |
| Constructor có side effect | Target và proxy có lifecycle riêng | Có constructor chain của subclass |
| Nhiều proxy/advice | Đúng thứ tự, không double-wrap | Đúng thứ tự, không double-intercept |
| Cấu hình loader/module | Interface khả kiến và proxy tạo được | Class con/helper định nghĩa được |
| Nhiều thread/đệ quy | Không lưu invocation state chung sai cách | Không lưu invocation state chung sai cách |
| Phương thức trả Future | Phân biệt method return và task completion | Tương tự |
| Hiệu năng hot path | Đo trên tải phù hợp | Đo trên tải phù hợp |

### 24.1. Tạo bộ test xác nhận self-invocation

Để kiểm tra một engine proxy cụ thể, tạo class có:

- Method `outer()` gọi `this.inner()`.
- Cả `outer` và `inner` đủ điều kiện trong pointcut.
- Một counter advice tăng theo tên method.
- Test gọi `outer` qua proxy và kiểm tra counter của `inner`.
- Test gọi `inner` trực tiếp qua proxy.
- Test gọi target không qua proxy nếu code cho phép.

**Không suy kết quả trước khi chạy trên engine thật.** Mẫu Java trong phần 8 chỉ là hai cấu trúc đã xác định rõ, không đại diện cho mọi engine.

## 25. Các lỗi hiểu sai phổ biến

**“Có interface thì mọi lời gọi tới target đều đi qua handler.”** Sai. Caller phải dùng proxy, và lời gọi nội bộ trên target riêng thường bypass.

**“Subclass proxy chắc chắn intercept self-invocation.”** Chưa đủ. Cần biết receiver là subclass proxy và method có thể override; một subclass proxy delegating sang target riêng có thể bypass.

**“JDK dynamic proxy kế thừa target class.”** Sai. Nó hiện thực các interface được chỉ định và dùng invocation handler.

**“Subclass proxy luôn tương thích với mọi final method.”** Nó có thể kế thừa final method, nhưng không thể override method ấy để intercept theo cơ chế kế thừa.

**“Final class nghĩa không thể dùng AOP.”** Sai. Interface proxy hoặc bytecode weaving có thể dùng ở ranh giới phù hợp.

**“Private method có thể bị subclass override bằng reflection.”** Sai. Private method không được override theo Java inheritance; reflection và weaving là các cơ chế khác.

**“Chỉ cần đổi class thành subclass sẽ giữ nguyên state của target đang tồn tại.”** Không. Hai object có identity/lifecycle khác nhau; không nên giả định copy state an toàn.

**“Proxy chậm vì Java reflection luôn chậm.”** Không thể kết luận chung. Chi phí tùy handler, JIT, advice, điểm nóng và workload.

**“Giá trị trả về đúng là đủ chứng minh proxy đúng.”** Chưa đủ. Phải kiểm tra ngoại lệ, advice order, side effects, self-invocation, identity và đường bypass.

**“Một kiểu proxy tốt nhất cho mọi chương trình.”** Không. Lựa chọn phụ thuộc hợp đồng kiểu, quyền kiểm soát đường gọi và các điểm cần can thiệp.

## 26. Bài tập luyện tư duy

**Bài 1 — Interface proxy và final class.** Class `FinalGateway` là final nhưng implements `GatewayPort`. Ứng dụng chỉ gọi qua `GatewayPort`. Dùng JDK dynamic proxy được không?

**Gợi ý:** có thể nếu `GatewayPort` là interface hợp lệ theo `Proxy` và loader/module đáp ứng; proxy hiện thực interface, không cần subclass `FinalGateway`.

**Bài 2 — Concrete API.** Một thư viện yêu cầu tham số đúng kiểu `Worker`, không nhận `Port`. Có thể truyền JDK dynamic proxy của `Port` không?

**Gợi ý:** không thể ép interface proxy thành `Worker` nếu proxy không kế thừa `Worker`. Cần thay API, adapter ở ranh giới khác, subclass proxy hợp lệ hoặc giải pháp tương đương.

**Bài 3 — Self-invocation.** `Worker.batch` gọi `this.execute`; đối tượng đang chạy là `WorkerSubclassProxy` và `execute` có override. Lời gọi nào chạy?

**Gợi ý:** virtual dispatch có thể gọi override trong subclass. Khác với interface handler ủy quyền vào `Worker target` riêng.

**Bài 4 — Final method.** Subclass kế thừa `public final version()`. Vì sao không in advice bằng cách override?

**Gợi ý:** Java cấm override final method. Muốn quan sát phiên gọi phải đặt interception ở boundary khác được hỗ trợ.

**Bài 5 — Constructor.** Base constructor gọi method có thể override; subclass proxy chưa khởi tạo state riêng. Rủi ro gì?

**Gợi ý:** override có thể chạy với state chưa sẵn sàng; tránh gọi overridable methods trong constructor và xem ràng buộc proxy generation.

**Bài 6 — Exception.** Handler gọi `Method.invoke` và target ném `IllegalArgumentException`. Handler nhận gì?

**Gợi ý:** reflection thường đưa `InvocationTargetException`; handler có thể lấy cause để trả lại lỗi gốc. Checked exceptions không khai báo cần xét `UndeclaredThrowableException`.

**Bài 7 — Đa luồng.** Handler giữ biến `currentRequest` dùng chung để log. Hai request chạy cùng lúc. Điều gì có thể sai?

**Gợi ý:** event có thể bị gán nhầm request; nên lưu state theo invocation và truyền context đúng ranh giới.

**Bài 8 — Kết quả trả Future.** Advice after-returning in “đã thành công” khi method trả `CompletableFuture`. Có chắc task hoàn tất chưa?

**Gợi ý:** không. Method return và future completion khác ranh giới; cần quan sát completion nếu chính sách yêu cầu.

## 27. Checklist chọn kiểu proxy cho hệ thống thực

- [ ] Xác định rõ điểm can thiệp là **lời gọi qua proxy**, không chỉ chữ ký method.
- [ ] Liệt kê contract mà caller cần: interface hay concrete class.
- [ ] Biết target có final/sealed hay method final/private/static cần quan sát không.
- [ ] Biết subclass cần constructor nào và có thể định nghĩa hợp lệ không.
- [ ] Kiểm tra class loader/module và các interface được phép proxy.
- [ ] Xác định subclass là **receiver thực** hay delegating tới target khác.
- [ ] Có test self-invocation và gọi trực tiếp target.
- [ ] Kiểm tra `equals`, `hashCode`, `toString` và identity.
- [ ] Không để state đã tạo ở target bị mất khi chuyển sang proxy khác.
- [ ] Không lưu context theo invocation vào shared mutable field không bảo vệ.
- [ ] Có test return value, checked/unchecked, cause và side effect.
- [ ] Đã xác định thứ tự nhiều advice/proxy.
- [ ] Có test negative chứng minh không intercept method ngoài chính sách.
- [ ] Phân biệt method return với completion bất đồng bộ.
- [ ] Đo startup, class generation, throughput, tail latency, allocation.
- [ ] Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm trong handler logging.
- [ ] Có kế hoạch nâng cấp, debug và phương án thay thế nếu proxy không phù hợp.
- [ ] Nếu chính sách bắt buộc không được bypass, kiến trúc phải chặn được mọi đường cần bảo vệ.

## 28. Tài liệu đối chiếu Java 17

Các tài liệu sau giúp xác minh những giới hạn **API Java cụ thể** được dùng làm ví dụ; chúng không định nghĩa toàn bộ AOP:

- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): tạo proxy implement interface và giới hạn interface/class loader/module.
- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): quy tắc dispatch và xử lý default method.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): reflective invocation và `InvocationTargetException`.
- [Java Language Specification — Overriding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): override, final methods và quy tắc kế thừa.

Khi đưa AOP qua proxy vào môi trường thực, cần thêm tài liệu chính thức của **công cụ đang tạo proxy**: cách chọn join point, cơ chế delegate hay super invocation, precedence, lifecycle và giới hạn hoạt động.

## 29. Kết luận

**Interface proxy** là lựa chọn phù hợp khi ứng dụng giao tiếp qua một hợp đồng interface và có thể điều khiển đường gọi để lời gọi đi qua một handler **ủy quyền tới target riêng**. **Subclass proxy** phù hợp khi cần quan hệ subtype với class cụ thể và class/method được phép kế thừa, override. Nhưng subclass proxy không tự giải quyết mọi vấn đề: final/private/static/constructor, state, lifecycle và cả kiểu ủy quyền nội bộ đều ảnh hưởng kết quả.

Điểm mấu chốt là **đừng chọn proxy chỉ vì tên kỹ thuật**. Hãy xác định ai là receiver, lời gọi đi qua những đối tượng nào, method có virtual dispatch hay không, target có được dùng trực tiếp ở đâu không, và hợp đồng kết quả/ngoại lệ phải được giữ thế nào.

Một thiết kế AOP qua proxy đáng tin cậy là thiết kế có **ranh giới rõ, coverage kiểm thử được, không bypass những chính sách bắt buộc và không làm sai hành vi nghiệp vụ**.
