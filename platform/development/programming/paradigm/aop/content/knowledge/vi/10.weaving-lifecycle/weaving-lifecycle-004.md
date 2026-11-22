# Can thiệp lúc chạy và giới hạn của nền tảng trong AOP

> **Mục tiêu học tập:** Hiểu “can thiệp lúc chạy” trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP) có thể chỉ **lời gọi được chuyển qua một interceptor/proxy ở runtime**, **weaving khi lớp được nạp**, hoặc **instrumentation/biến đổi lớp trong JVM đang hoạt động**. Phân biệt các cơ chế đó với nhau và với weaving khi biên dịch; đánh giá giới hạn về join point, class loading, bytecode, module, phương thức, constructor, hành vi native, thread và deployment. Biết thiết kế ca kiểm thử chứng minh chính xác **đường nào được can thiệp, đường nào không**.

## 1. “Can thiệp lúc chạy” không phải một cơ chế duy nhất

Một chương trình Java có thể áp dụng mối quan tâm xuyên suốt — ghi log, đo thời gian, kiểm toán kỹ thuật, truy vết hoặc kiểm soát một ranh giới — bằng nhiều cách. Có người gọi tất cả chúng là “runtime AOP”, nhưng cách gọi đó che khuất khác biệt quan trọng.

Ba nhóm điển hình:

1. **Runtime interception bằng proxy/decorator/interceptor:** caller gọi một đối tượng trung gian. Đối tượng này chạy logic bổ sung, rồi có thể chuyển tiếp tới đối tượng đích. Không nhất thiết sửa bytecode của lớp đích.
2. **Load-time weaving (LTW):** một cơ chế xử lý bytecode **trước hoặc trong lúc lớp được định nghĩa/nạp** vào JVM; advice được dệt vào những vị trí phù hợp của lớp.
3. **Instrumentation đối với JVM đang chạy:** một agent hoặc cơ chế tương đương có thể quan sát lớp được nạp, biến đổi bytecode được phép, và trong một số điều kiện yêu cầu **retransformation/redefinition** các lớp đã nạp.

Ba nhóm có thể phối hợp, nhưng không có quyền năng giống nhau. Một proxy thấy **lời gọi đi qua proxy**; một bộ dệt bytecode cần **nhìn thấy và được phép xử lý lớp/mã liên quan**; instrumentation đối với lớp đã nạp chịu **ràng buộc VM, class file và chính API biến đổi**.

Câu hỏi đầu tiên không phải “có bật runtime AOP không?”, mà là:

> **Cơ chế nào thực sự nhận quyền điều khiển, tại ranh giới nào, và từ thời điểm nào?**

## 2. Nhắc lại các thành phần AOP liên quan

| Khái niệm | Câu hỏi nó giải quyết | Ví dụ |
|---|---|---|
| **Join point** | Loại điểm/sự kiện nào trong chương trình có thể được can thiệp? | Method execution, method call, field access, constructor execution nếu mô hình hỗ trợ |
| **Pointcut** | Những điểm nào thuộc tập cần áp dụng? | Chọn các method xử lý đơn hàng, trừ thao tác nội bộ |
| **Advice** | Hành vi nào được kết hợp và chạy ở thời điểm nào? | Ghi trước, sau, sau ngoại lệ, bao quanh |
| **Aspect** | Mối quan tâm xuyên suốt được tổ chức ở đâu? | Module quan sát thời gian xử lý |
| **Weaving** | Advice được kết hợp vào các điểm tương ứng thế nào? | Sinh/biến đổi mã hoặc cơ chế thích hợp khác |
| **Runtime path** | Khi chạy thật, chương trình có đi qua điểm can thiệp? | Gọi qua proxy thay vì gọi trực tiếp target |

Không có một **join point model** thống nhất cho mọi công cụ AOP. Một công cụ chỉ chặn các lời gọi method qua giao diện khác với công cụ có thể dệt vào **method call**, **method execution**, **field get/set** hoặc **constructor**.

Cần tránh hai suy luận sai:

- **“Pointcut đúng” không đồng nghĩa “advice sẽ chạy”:** lớp có thể chưa được dệt, lời gọi không đi qua proxy hoặc điểm chưa xảy ra.
- **“Advice không chạy” không đồng nghĩa “nghiệp vụ không xảy ra”:** caller có thể đã gọi trực tiếp đối tượng đích.

## 3. Phân biệt thời điểm dệt và thời điểm advice chạy

Trong mọi cơ chế AOP có advice, **advice có thể chạy ở runtime** khi join point xuất hiện. Điều đó không có nghĩa **weaving nhất thiết diễn ra ở runtime**.

~~~text
Compile-time weaving:
  source + aspects → weaving / build → class đã dệt → JVM chạy advice

Binary/post-compile weaving:
  class có sẵn + aspects → biến đổi bytecode → JVM chạy advice

Load-time weaving:
  JVM cần định nghĩa class → transformer/weaver → class đã dệt
                                            → JVM chạy advice

Runtime proxy/interceptor:
  tạo/chọn proxy → caller đi qua proxy → handler chạy
                                     → có thể gọi target

Runtime retransform/redefine (khi được hỗ trợ):
  JVM đã có lớp → yêu cầu biến đổi lại phù hợp → các lần chạy tương lai
                      có thể đi qua bytecode mới theo hợp đồng VM
~~~

Điều này tạo hai trục độc lập:

- **Khi nào kết hợp/chốt cơ chế can thiệp?** Compile, sau compile, class loading, sau khi lớp đã được định nghĩa, hoặc lúc tạo/chọn đối tượng trung gian.
- **Khi nào advice thực thi?** Khi một lần join point thực tế được quan sát và điều kiện tương ứng khớp.

Một method đã được dệt có thể không được gọi trong ca thử; không có advice chạy nhưng không phải lỗi weaving. Một proxy có thể được tạo thành công nhưng caller lại giữ tham chiếu target; handler vẫn không chạy.

## 4. Bảng so sánh các kỹ thuật can thiệp lúc chạy

| Thuộc tính | Proxy/interceptor | Load-time bytecode weaving | Retransform/redefine lớp đã nạp |
|---|---|---|---|
| **Ranh giới chính** | Lời gọi đi qua lớp trung gian | Điểm trong mã lớp được xử lý trước khi định nghĩa | Điểm trong phiên bản lớp có thể được cập nhật theo khả năng VM |
| **Cần sửa bytecode lớp đích?** | Không nhất thiết | Thường có | Có thể, nếu yêu cầu biến đổi thực sự |
| **Đối tượng gốc gọi trực tiếp** | Thường bỏ qua proxy | Có thể quan sát nếu mã tương ứng đã được dệt | Tùy phần mã đã thay đổi và join point model |
| **Class đã nạp** | Có thể tạo proxy mới nhưng caller phải dùng nó | Thường không tự động dệt lại class đã nạp | Chỉ khi VM, agent, class và phép biến đổi hỗ trợ |
| **Private/static/constructor/field** | Tùy loại proxy; nhiều loại không được bao phủ | Tùy mô hình join point và giới hạn weaving | Tùy join point model, bytecode và giới hạn VM |
| **Ràng buộc đáng chú ý** | Đường tham chiếu, dispatch, kiểu proxy | Class loader, transformer, class format, module | Quyền instrumentation, modifiability, schema class, trạng thái đang chạy |
| **Kiểu sự cố thường gặp** | Bỏ qua proxy, self-invocation, sai dispatch | Không xử lý đúng lớp, class version, transformer lỗi | Không được retransform, schema thay đổi, linkage/verification |

Bảng không phải đặc tả của một framework cụ thể. Nó giúp chọn **câu hỏi xác minh** trước khi thiết kế giải pháp.

## 5. Runtime proxy: nơi can thiệp là đường lời gọi

Một proxy là đối tượng nhận lời gọi ở phía trước đối tượng đích. Với Java, `java.lang.reflect.Proxy` cung cấp cơ chế tạo đối tượng triển khai các **giao diện** được chỉ định và chuyển lời gọi method giao diện tới `InvocationHandler`.

~~~text
client
  |
  | call service.execute()
  v
proxy implements Service
  |
  | InvocationHandler.invoke(...)
  v
target ServiceImpl.execute()
~~~

Nếu client giữ trực tiếp target:

~~~text
client ----------------------> target.execute()
                     (không đi qua handler của proxy)
~~~

Vì vậy **đường đi của tham chiếu** là một phần hợp đồng runtime interception. Một đối tượng `ServiceImpl` không tự biến mọi lời gọi lên nó thành lời gọi qua proxy chỉ vì một proxy cùng trỏ tới nó đã được tạo ra.

### 5.1. Self-invocation và lời gọi bên trong target

Một phương thức trên target có thể gọi tiếp `this.internal()`, `internal()` hoặc phương thức khác cùng đối tượng. Những lời gọi này **không tự quay ra proxy**.

Một handler bao ngoài phương thức `execute()` có thể ghi một sự kiện cho `execute()`, nhưng không có nghĩa mỗi method call bên trong target lại đi qua handler.

Đây là giới hạn của **kiểu can thiệp bằng đối tượng trung gian**. Một cơ chế weaving trực tiếp mã ở method execution hoặc call site có thể có độ bao phủ khác. Không nói “AOP luôn không chặn được self-invocation”.

### 5.2. Static, private, final không thể gộp thành một quy tắc

- **Static method** không được dispatch như method instance của giao diện proxy.
- **Private method** không phải một method mà proxy giao diện đại diện thông thường.
- **Final method** không thể override bằng subclass, nhưng điều đó không tự ngăn **proxy giao diện** chặn lời gọi ở ranh giới ngoài trước khi chuyển tới implementation.
- **Final class** không thể bị kế thừa; giới hạn này ảnh hưởng cách tạo subclass, nhưng không phải lập luận phủ định mọi loại weaving bytecode.

Kết luận luôn phải có dạng **“cơ chế X bị giới hạn bởi Y”**, không phải “mọi AOP đều không thể can thiệp loại method Z”.

## 6. Ví dụ Java 17 chạy được: proxy nhìn thấy gì và bỏ sót gì?

Chương trình dưới đây dùng Java Dynamic Proxy để minh họa:

1. Constructor của target chạy trước khi proxy được tạo.
2. Lời gọi qua proxy kích hoạt handler.
3. Lời gọi `this.finish()` từ nội bộ target **không tạo một lần intercept mới**.
4. Lời gọi trực tiếp target bỏ qua handler.
5. Static method không đi qua đường method giao diện của proxy.

**Đây là mô phỏng runtime interception bằng Java chuẩn, không phải chương trình biến đổi bytecode hoặc công cụ AOP tổng quát.**

Lưu file `RuntimeProxyDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class RuntimeProxyDemo {
    interface Service {
        void execute(String job);
        void ping();
    }

    static final class ServiceImpl implements Service {
        private int completed;

        ServiceImpl() {
            System.out.println("target constructor");
        }

        @Override
        public void execute(String job) {
            System.out.println("target execute " + job);
            finish();
            completed++;
        }

        @Override
        public void ping() {
            System.out.println("target ping");
        }

        private void finish() {
            System.out.println("target internal finish");
        }

        static void staticCheck() {
            System.out.println("target static");
        }
    }

    public static void main(String[] args) {
        ServiceImpl target = new ServiceImpl();

        Service proxy = (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] {Service.class},
                (proxyObject, method, values) -> {
                    System.out.println("intercept " + method.getName());
                    try {
                        return method.invoke(target, values);
                    } catch (InvocationTargetException wrapped) {
                        throw wrapped.getCause();
                    }
                }
        );

        System.out.println("-- via proxy --");
        proxy.execute("A");
        proxy.ping();

        System.out.println("-- direct --");
        target.execute("B");
        ServiceImpl.staticCheck();

        System.out.println("completed " + target.completed);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac RuntimeProxyDemo.java
java RuntimeProxyDemo
~~~

**Stdout chính xác:**

~~~text
target constructor
-- via proxy --
intercept execute
target execute A
target internal finish
intercept ping
target ping
-- direct --
target execute B
target internal finish
target static
completed 2
~~~

### 6.1. Tại sao lần gọi `execute("B")` không có `intercept execute`?

Vì caller dùng `target`, không dùng `proxy`. Điều này không liên quan điều kiện pointcut phức tạp: handler **không nằm trên đường lời gọi đó**.

### 6.2. Tại sao `finish()` không có dòng intercept riêng?

`finish()` là method private được gọi trong target. Nó không phải một lời gọi method giao diện đi qua đối tượng proxy. Handler chỉ quan sát lời gọi `execute()` từ bên ngoài, còn code bên trong vẫn chạy.

### 6.3. Tại sao số lần nghiệp vụ là 2?

`completed` tăng trong **cả hai lần** `execute`. Nhờ vậy chương trình chứng minh “không có log intercept” khác với “nghiệp vụ không thực thi”.

### 6.4. Ngoại lệ qua reflection

`Method.invoke` có thể bọc ngoại lệ do method đích ném trong `InvocationTargetException`. Handler giải lớp bọc và ném lại nguyên nhân gốc. Đây là đặc điểm của adapter reflection dùng trong ví dụ, không phải cơ chế xử lý ngoại lệ bắt buộc của mọi weaver.

## 7. Load-time weaving: can thiệp vào lúc lớp được định nghĩa

**Load-time weaving** xử lý mã lớp trong quá trình JVM nạp/định nghĩa class theo cơ chế phù hợp. Một class transformer được gọi với dữ liệu class trước khi class được định nghĩa hoàn tất và có thể trả bytecode đã biến đổi.

~~~text
Application/class loader
         |
         v
Request: define/load Class X
         |
         v
Transformer/weaver receives class bytes
         |
         +---- no change → class bytes gốc
         |
         +---- transform → class bytes đã chỉnh hợp lệ
         |
         v
JVM defines/verifies/links class according to runtime rules
         |
         v
Execution of join points that were instrumented
~~~

Một lớp **không được nạp trong giai đoạn cơ chế còn có cơ hội transform**, hoặc bị loại khỏi phạm vi, có thể không nhận advice mà người viết mong đợi.

Vấn đề cần xác định:

- Cơ chế weaving được kích hoạt **trước hay sau** khi lớp quan trọng được định nghĩa?
- Class nào đi qua transformer nào?
- Class loader nào định nghĩa class đó?
- Pointcut có chọn những join point nằm trong mã thực sự đã biến đổi?
- Có lỗi class file hoặc quyền truy cập khi transformer chạy không?

### 7.1. Load-time không đồng nghĩa “mọi method được kiểm tra pointcut mỗi lần gọi”

Một weaver có thể quyết định theo cấu trúc lúc class loading và **chèn mã** cần thiết. Khi method chạy, mã đã biến đổi thực hiện kiểm tra còn lại, nếu có.

Ngược lại, một proxy có thể đọc tên và đối số tại mỗi lần gọi. Hai cơ chế cùng dẫn tới advice chạy ở runtime nhưng thời điểm phân tích và chi phí khác nhau.

### 7.2. Trường hợp một lớp được nạp từ trước

Nếu một lớp đã được JVM định nghĩa trước khi transformer được đăng ký, việc đăng ký transformer **không tự dệt lại class đã nạp**. Cần một khả năng retransformation/redefinition riêng, nếu công cụ và JVM hỗ trợ; việc “bật AOP sau” không bảo đảm mọi class cũ sẽ đổi.

## 8. Instrumentation agent trong Java là gì?

JDK cung cấp API `java.lang.instrument` cho Java agent quan sát hoặc biến đổi các class ở những ranh giới VM cho phép. Hai hình thức entry point hay được nhắc tới:

- **`premain`**: agent được khởi tạo từ tùy chọn `-javaagent:...` khi JVM khởi động, trước khi phương thức main của ứng dụng chạy theo cơ chế đó.
- **`agentmain`**: entry point của một agent được nạp vào JVM đang chạy theo cơ chế attach tương ứng **nếu môi trường/JVM cho phép**.

Đây là **các entry point instrumentation**, không tự cung cấp pointcut/advice hoàn chỉnh. Muốn dệt các hành vi AOP thực sự, phải xây dựng hoặc dùng một bộ xử lý bytecode/pointcut có mô hình đúng.

### 8.1. Transformer khác với weaver hoàn chỉnh

Một `ClassFileTransformer` nhận bytecode class và có thể trả:

- Một mảng byte mới biểu thị class hợp lệ đã biến đổi.
- `null` để báo **không biến đổi** class.

Việc transformer được gọi hoặc in log **không chứng minh** method đã có advice. Nếu transformer luôn trả `null`, nó chỉ quan sát đường class loading (trong ví dụ này), chưa dệt thêm hành vi method.

## 9. Ví dụ Java 17: Java agent quan sát class loading mà không sửa bytecode

Ví dụ này cho thấy một ranh giới **runtime instrumentation thực sự** bằng JDK thuần. Nó **chỉ in tên một class được nạp**, không tạo pointcut method, không chèn before/after advice.

Ta cần ba tệp: `TraceAgent.java`, `RuntimeSample.java`, và `MANIFEST.MF`.

### 9.1. File `TraceAgent.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public class TraceAgent implements ClassFileTransformer {
    public static void premain(String arguments, Instrumentation instrumentation) {
        System.out.println("[agent] ready");
        instrumentation.addTransformer(new TraceAgent());
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {
        if ("RuntimeSample$Worker".equals(className)) {
            System.out.println("[agent] noticed RuntimeSample$Worker");
        }
        return null; // Không biến đổi bytecode.
    }
}
~~~

Java 17 có overload `transform` nhận `Module` và các thông tin lớp. `return null` ở đây có nghĩa không thay đổi mã class. Ký hiệu `$` thuộc tên nhị phân của lớp lồng, không phải cơ chế của AOP.

### 9.2. File `RuntimeSample.java`

~~~java
public class RuntimeSample {
    static final class Worker {
        Worker() {
            System.out.println("[app] Worker constructed");
        }

        void work() {
            System.out.println("[app] hello");
        }
    }

    public static void main(String[] args) {
        System.out.println("[app] before new");
        Worker worker = new Worker();
        worker.work();
    }
}
~~~

### 9.3. File `MANIFEST.MF`

Lưu **manifest dưới dạng văn bản có dòng kết thúc**:

~~~text
Manifest-Version: 1.0
Premain-Class: TraceAgent

~~~

Dòng trống cuối là cách đơn giản bảo đảm phần main section của manifest kết thúc đúng. Khi tạo tệp thủ công, phải tránh vô tình nối các header vào cùng một dòng.

### 9.4. Biên dịch, đóng gói và chạy

Đặt ba tệp trong cùng thư mục rồi chạy:

~~~bash
javac TraceAgent.java RuntimeSample.java
jar cfm trace-agent.jar MANIFEST.MF TraceAgent.class
java -javaagent:trace-agent.jar RuntimeSample
~~~

Đầu ra dự kiến trong môi trường JDK 17 thông thường:

~~~text
[agent] ready
[app] before new
[agent] noticed RuntimeSample$Worker
[app] Worker constructed
[app] hello
~~~

**Giới hạn của cam kết stdout:** ví dụ chỉ in class `RuntimeSample$Worker`, nên tránh nhiễu từ những class khác. Nhưng những môi trường JVM đặc biệt, công cụ launch, agent bổ sung hoặc các biến đổi startup khác có thể thay đổi trình tự tải lớp hoặc thêm thông báo riêng. Vì vậy đây là output của kịch bản chạy chuẩn, không phải hợp đồng tổng quát của mọi JVM.

### 9.5. Bài học quan trọng nhất

- `[agent] ready` chứng minh `premain` của agent đã khởi động.
- `[agent] noticed ...` chứng minh transformer được gọi khi class mục tiêu được tải/định nghĩa theo đường quan sát được.
- **Không có before/after advice nào được chèn vào `Worker.work()`.**
- `return null` chứng minh ví dụ **không dệt bytecode của method**.

Để từ đây đi tới weaving AOP, cần một cơ chế biến đổi bytecode **hợp lệ**, xác định join point, chèn mã tương ứng và giữ bytecode đúng theo quy tắc xác minh. Không được coi thao tác đăng ký transformer đơn thuần là aspect weaving hoàn chỉnh.

## 10. Khác biệt giữa premain, agentmain và khả năng attach

Agent lúc khởi động và agent được nạp khi JVM đang chạy khác nhau về **thời điểm có quyền can thiệp**.

| Vấn đề | Agent lúc khởi động | Agent được attach sau khi chạy |
|---|---|---|
| **Class đã được nạp trước agent?** | Ít hơn đối với class ứng dụng, nhưng một số class hệ thống vẫn có thể được nạp từ sớm | Có thể rất nhiều |
| **Mục tiêu chính** | Đăng ký transformer trước các class quan trọng | Quan sát/biến đổi sau khi JVM đã hoạt động nếu được hỗ trợ |
| **Khả năng can thiệp vào class đã nạp** | Không tự có chỉ từ đăng ký transformer | Cũng không tự có; cần retransform/redefine và điều kiện tương ứng |
| **Yêu cầu triển khai** | Java agent JAR và cấu hình khởi động | Khả năng attach của VM, quyền truy cập, chính sách vận hành và agent |
| **Độ tin cậy phạm vi** | Dễ kiểm soát hơn khi được cấu hình trước startup | Khó hơn vì nhiều class và call path đã hoạt động |

Không nên mặc định một ứng dụng luôn cho phép **dynamic attach**. JVM, phiên bản runtime, chính sách bảo mật và tùy chọn cấu hình có thể giới hạn hoặc vô hiệu hóa khả năng này. Ở một số môi trường đóng gói đặc biệt, API attach hoặc khả năng instrumentation không hiện diện như ở một JDK đầy đủ.

Từ góc nhìn triển khai, agent là mã có quyền ảnh hưởng trực tiếp JVM. Chỉ nạp mã tin cậy, kiểm tra nguồn/phân phối và có chính sách quản trị phù hợp.

## 11. Re-transformation và redefinition: thay class đã nạp có giới hạn

Hai khái niệm thường xuất hiện:

- **Retransformation:** yêu cầu JVM chạy lại chuỗi transformer phù hợp trên class đã nạp, nếu hỗ trợ và class có thể biến đổi.
- **Redefinition:** cung cấp định nghĩa bytecode mới cho những class đã nạp, nếu khả năng đó được JVM hỗ trợ và được cấu hình cho agent.

Cần kiểm tra các khả năng cụ thể như `Instrumentation.isRetransformClassesSupported()`, `Instrumentation.isRedefineClassesSupported()` và `Instrumentation.isModifiableClass(...)` khi áp dụng Java instrumentation thật.

**Không phải class nào cũng modifiable.** Không phải mọi phép thay bytecode đều hợp lệ. Việc VM hỗ trợ một chức năng không đồng nghĩa agent đã khai báo quyền sử dụng nó hoặc một class mục tiêu thỏa điều kiện.

### 11.1. Giới hạn thay đổi cấu trúc class

Với cơ chế standard JVM class redefinition/retransformation trong những điều kiện thông thường, không được tùy tiện **thêm/xóa method**, **thêm/xóa field**, đổi cấu trúc quan hệ kế thừa hoặc thay đổi một số đặc điểm schema lớp. Những phép biến đổi kiểu này có thể bị từ chối.

Khả năng thay đổi phần thân method cũng có giới hạn xác minh, liên kết và trạng thái JVM. Vì vậy không nên dùng “dệt lại” như lời hứa có thể tái cấu trúc class sống theo bất kỳ cách nào.

### 11.2. Các stack frame đang hoạt động

Một giới hạn quan trọng: sau khi class được định nghĩa lại, các **lời gọi đã đang thực thi** có thể tiếp tục với phiên bản mã cũ theo semantics của VM, trong khi những lần vào sau mới dùng mã mới.

Đó là lý do không thể kết luận “đổi class lúc 12:00 thì mọi lời gọi đang chạy từ 11:59 lập tức chịu advice mới”. Cần kiểm thử trường hợp method đang chạy lâu khi yêu cầu biến đổi.

### 11.3. Đổi bytecode không đồng nghĩa đổi mọi điểm đã quan sát

Một weaver có thể chèn hook tại **execution** của phương thức, nhưng không chèn ở **mọi call site**. Retransform lớp method đích cũng không tự biến đổi bytecode của tất cả caller khác.

Hãy hỏi điểm nào bị thay: method body, call site, constructor hay field access. **Địa điểm dệt** quyết định phạm vi can thiệp.

## 12. Class loader: cùng tên lớp chưa chắc cùng class

Trong Java, danh tính của một class không chỉ là tên nhị phân. **Class loader định nghĩa** cũng có vai trò quan trọng.

Hai module hoặc hệ plugin có thể nạp những lớp cùng tên nhưng dưới các class loader khác nhau. Một cấu hình transformer chọn tên `com.example.Service` có thể bắt gặp nhiều class không cùng danh tính runtime.

Những câu hỏi cần xác minh:

- Class mục tiêu thật sự được định nghĩa bởi loader nào?
- Transformer có được gọi cho loader đó?
- Có loader nào loại trừ instrumentation hay không?
- Code ứng dụng đang gọi tới **bản class nào**?
- Có bao nhiêu phiên bản class được nạp trong cùng tiến trình?
- Có xảy ra class loader isolation khiến một lời gọi proxy/cast lỗi không?

Một advice log tên method `Service.execute` không đủ để chứng minh nó thuộc đúng module/runtime class instance mà người triển khai quan tâm.

### 12.1. Bootstrap classes và class hệ thống

Các class cốt lõi của JVM có thể chịu chính sách đặc biệt về class loading và transformation. Việc instrument chúng cần cân nhắc khả năng tiếp cận, chuỗi phụ thuộc và nguy cơ phá các cơ chế mà chính agent dựa vào.

Một transformer ghi log bằng các API Java tại mọi lần class loading có thể tự kích hoạt thêm việc nạp lớp. Nếu áp dụng phạm vi quá rộng, có nguy cơ **đệ quy, vòng phụ thuộc hoặc làm startup bất ổn**.

Cách tiếp cận thực tế: chọn lớp mục tiêu hẹp, tránh can thiệp các lớp hạ tầng cốt lõi khi chưa có thiết kế và kiểm thử phù hợp.

## 13. Module system và quyền truy cập trên JVM hiện đại

Từ Java 9, **Java Platform Module System (JPMS)** ảnh hưởng đến khả năng đọc và truy cập package, method và field giữa các module.

Cần phân biệt:

- **Exports:** một module công bố package cho việc sử dụng API theo cơ chế module.
- **Opens:** cho phép một số hình thức reflective access tới thành phần bên trong theo điều kiện module.
- **Class loading:** định nghĩa class nào, từ module/loader nào.
- **Instrumentation:** khả năng quan sát và biến đổi class theo hợp đồng VM/agent.

Một agent có khả năng nhận bytecode **không mặc nhiên có quyền reflective access vô hạn** tới mọi private member. Ngược lại, mở package cho reflection không tự cung cấp join point field-write mà công cụ AOP chưa hỗ trợ.

Có các API/module configuration giúp điều chỉnh quan hệ đọc/mở package trong phạm vi được phép, nhưng cần đánh giá rủi ro trước khi mở rộng truy cập.

### 13.1. Sai lầm thường gặp

Một advice muốn đọc private field và gặp lỗi truy cập. Người triển khai kết luận “weaving hỏng”. Nhưng nguyên nhân có thể chỉ ở **runtime reflection/module access** của chính mã advice; bytecode weave vẫn có thể đã được áp dụng đúng.

Phải xác định lỗi phát sinh khi **transform class**, **verify/link class** hay **advice gọi reflective access**.

## 14. Bytecode format, verifier và version compatibility

Khi weaving can thiệp vào bytecode, mã tạo ra phải thỏa quy tắc JVM: cấu trúc class file hợp lệ, kiểu trên operand stack phù hợp, stack map frames khi cần, access hợp lệ, tham chiếu constant pool và ràng buộc của các method.

Những hiện tượng có thể gặp:

- `ClassFormatError`: class file không có cấu trúc được chấp nhận.
- `VerifyError`: bytecode không thỏa quy tắc xác minh.
- `UnsupportedClassVersionError`: class file yêu cầu một phiên bản JVM không tương thích.
- `NoSuchMethodError` hoặc `IllegalAccessError`: một số lỗi liên kết khi mã thực thi tham chiếu thành phần không phù hợp.

**Không phải hễ nhìn thấy các lỗi đó thì weaving là thủ phạm.** Lỗi có thể do artifact build/deploy không khớp, thư viện không tương thích hoặc mã sinh từ công cụ khác.

Phương pháp điều tra tốt:

1. Xác định file class thực tế được nạp.
2. So sánh artifact **trước và sau** biến đổi nếu có.
3. Xác minh JDK, class file version, classpath/module path.
4. Kiểm tra cause và stack trace/diagnostic của transformer hoặc verifier.
5. Tạo một ca tái hiện tối thiểu để cô lập lỗi.

Không nên sửa logic nghiệp vụ khi bằng chứng đang chỉ vào vấn đề bytecode compatibility.

## 15. Những giới hạn về loại join point

Một yêu cầu “ghi log mọi thao tác” rất dễ vượt ngoài mô hình can thiệp của một công cụ.

| Hoạt động | Proxy method-interface | Bytecode weaving/agent có mô hình phù hợp |
|---|---|---|
| Lời gọi method giao diện qua proxy | Có thể chặn | Có thể nếu cơ chế và phạm vi hỗ trợ |
| Gọi trực tiếp vào target | Không qua handler proxy | Có thể ở execution/call site đã được dệt |
| Private method trong target | Không tự có interception riêng | Có thể nếu loại điểm và phạm vi hỗ trợ |
| Static method | Không đi qua instance interface proxy | Có thể theo cơ chế weaving phù hợp |
| Constructor call/execution | Proxy target thông thường không tự chặn | Một số mô hình có khả năng; cần xét semantics |
| Field get/set trực tiếp | Không phải method giao diện | Có thể nếu mô hình có field join point và weaving đúng mã |
| Native method body | Không phải mã bytecode Java thông thường để chèn vào thân native | Cần cơ chế khác hoặc can thiệp ở ranh giới Java/nền tảng |
| Hoạt động ở tiến trình khác | Không nằm trong proxy này | Không tự nằm trong JVM đang instrument |

Từ “có thể” **không phải** lời hứa mọi công cụ bytecode sẽ làm được. Công cụ cần định nghĩa **loại join point**, một vị trí trong mã có thể can thiệp, phạm vi weaving và semantics advice hợp lệ.

### 15.1. Truy cập trường qua reflection hoặc cơ chế bộ nhớ khác

Một công cụ hỗ trợ field get/set tại bytecode truy cập trường thông thường **không tự bao phủ tất cả** các thay đổi trạng thái thông qua reflection, method handle, native memory hoặc cơ chế đặc biệt.

Muốn quan sát mọi thay đổi bất biến nghiệp vụ, thường cần đặt chính sách ở ranh giới sở hữu trạng thái, không chỉ tin vào một nhóm instruction.

### 15.2. Constructor và quá trình khởi tạo

“Có constructor execution join point” không đồng nghĩa “đếm được mọi object allocation”. Các đường tạo đối tượng khác nhau, quá trình constructor delegation và tình trạng object chưa khởi tạo đầy đủ cần được xem xét.

Một advice làm lộ `this` trong constructor, đọc trạng thái chưa sẵn sàng hoặc gọi virtual method quá sớm có thể gây lỗi khó chẩn đoán. Không áp dụng advice constructor như wrapper method thông thường mà bỏ qua quy tắc khởi tạo của Java.

## 16. Dynamic dispatch, reflection, method handle và mã sinh

Java có nhiều đường tạo lời gọi:

- Lời gọi thông thường trong source.
- Gọi qua interface hoặc virtual dispatch.
- Gọi qua `Method.invoke` (reflection).
- Gọi qua method handle và `invokedynamic` trong những trường hợp phù hợp.
- Lambda, class sinh động hoặc proxy do runtime tạo.
- Lời gọi tới native method qua JNI hoặc ranh giới khác.

Độ bao phủ phụ thuộc **điểm dệt**:

- Nếu weaving ở **method execution**, phần thân của phương thức đã được dệt có thể được quan sát dù caller dùng reflection, nếu runtime thực sự vào phần thân đó.
- Nếu weaving ở **call site tĩnh**, lời gọi phát sinh bằng reflection hoặc mã sinh khác có thể không đi qua những call site đã được dệt trong source ban đầu.
- Nếu can thiệp bằng **proxy**, chỉ các lời gọi đi qua đối tượng trung gian được bao phủ.
- Nếu class được sinh/nạp sau khi bộ dệt kích hoạt, cần xác minh class đó có đi qua transformer và phù hợp các bộ lọc.

Không nên xem “gọi cùng tên method” là bảo đảm đi qua cùng loại join point.

## 17. Native code và giới hạn của nền tảng JVM

Bytecode weaving chuyên xử lý những phần của chương trình thể hiện bằng bytecode tương ứng. Mã native nằm bên ngoài thân bytecode của phương thức Java.

Một lời gọi Java **đi vào ranh giới native** có thể được quan sát bằng một số phương thức can thiệp ở phía Java, nếu mô hình hỗ trợ. Nhưng một bộ dệt bytecode Java không tự chèn advice vào từng instruction máy bên trong thư viện native.

Các trường hợp cần giải pháp khác có thể bao gồm:

- Thao tác bộ nhớ native.
- Tương tác driver hoặc runtime nền tảng.
- Sự kiện hệ điều hành hoặc file system do tiến trình khác thực hiện.
- Thay đổi ở hệ thống bên ngoài sau một lời gọi mạng.
- Hoạt động ở database sau khi Java đã gửi yêu cầu.

**AOP trong một JVM không phải hệ thống observability toàn vũ trụ.** Một advice bao quanh `sendMessage()` chỉ biết phương thức Java đó rời phạm vi theo hợp đồng; nó không tự xác nhận message đã được một tiến trình khác xử lý xong.

## 18. AOT, native image và môi trường bị giới hạn

Một số hệ thống chạy dưới môi trường **ahead-of-time compilation (AOT)**, native image hoặc nền tảng có giới hạn động đối với class loading, reflection, attach và instrumentation.

Khi đó cần đánh giá riêng:

- Có JVM với API `java.lang.instrument` giống triển khai thông thường không?
- Cơ chế runtime class loading/bytecode transform có tồn tại không?
- Có thể dùng dynamic proxy/reflection ở mức nào?
- Những metadata nào còn được giữ?
- Có quy tắc khai báo trước hoặc build-time configuration không?
- Chính sách nền tảng có cho phép agent attach không?

Không được kết luận “nếu Java 17 source biên dịch được thì mọi runtime đều cho chạy Java agent theo cách đó”. JDK chuẩn trên JVM và bản build AOT có thể có những năng lực rất khác nhau.

## 19. Giới hạn của attach và bảo mật vận hành

Can thiệp vào JVM đang chạy là khả năng nhạy cảm. Một agent đủ quyền có thể quan sát hoặc thay đổi hành vi sâu bên trong ứng dụng.

Những câu hỏi vận hành:

- Ai được phép khởi động JVM kèm `-javaagent`?
- Ai được phép attach agent khi chạy?
- Agent JAR được lấy từ đâu, kiểm tra và cập nhật thế nào?
- Môi trường production có tắt dynamic attach hoặc hạn chế API này không?
- Có chính sách audit với những thay đổi instrumentation không?
- Có thể rollback mà không làm mất trạng thái hoặc gây ngắt quãng không?
- Có đo chi phí và tác động bảo mật của agent không?

**Không dùng agent như cách lách kiểm soát truy cập.** Cần tuân thủ chính sách của môi trường và xem agent như thành phần mã có mức tin cậy cao.

### 19.1. Quyền instrumentation không phải quyền đọc mọi dữ liệu

Một agent có thể nhận bytecode ở một giai đoạn phù hợp, nhưng điều đó không đồng nghĩa có thể đọc trực tiếp mọi dữ liệu nghiệp vụ hoặc các thành phần private qua Java reflection mà không có quy tắc module/access tương ứng.

Việc một phép biến đổi bytecode được phép cũng không đồng nghĩa một pointcut được phép **thay đối số hoặc short-circuit** trên mọi loại join point. Đây là các mức quyền năng khác nhau.

## 20. Thứ tự transformer và tương tác giữa nhiều công cụ

Một JVM có thể có nhiều agent/transformer cùng tham gia. Mã cuối cùng có thể chịu ảnh hưởng của **thứ tự áp dụng biến đổi**, khả năng retransformation và sự tương thích của các thay đổi.

Các rủi ro:

- Hai transformer cùng dựa vào cấu trúc bytecode ban đầu nhưng một transformer chạy sau đã thấy mã biến đổi.
- Một công cụ chèn một lời gọi helper mà class loader khác không tìm thấy.
- Một transformer thay đổi tên/trạng thái phương thức và ảnh hưởng tới phép nhận diện của công cụ khác.
- Mã mới tạo ra không còn thỏa stack map frame/verification.
- Khi retransformation, các quy tắc có thể khác lúc load lần đầu.
- Hai aspect cùng chặn một join point nhưng dùng thứ tự advice không được hiểu đúng.

Nếu lỗi chỉ xuất hiện khi chạy **kết hợp** nhiều công cụ, cần thử tối thiểu từng công cụ rồi kiểm chứng tương tác. Không nên sửa pointcut một cách mù quáng khi nguyên nhân thật là bytecode đã bị biến đổi bởi một công cụ khác.

## 21. Class initialization và thứ tự khởi động

Một số mã chạy rất sớm trong vòng đời JVM: static initializer, code của class loader, code của agent và những thành phần logging hoặc cấu hình thiết yếu.

Nếu advice hoặc transformer **dùng cùng những class đang được định nghĩa**, có thể phát sinh phụ thuộc vòng:

~~~text
Transformer đang nạp helper A
        |
        v
Helper A lại phụ thuộc class B
        |
        v
Transformer tiếp tục chặn class B
        |
        v
B cố dùng lại A trước khi A khởi tạo xong
~~~

Không phải mọi lần class được nạp bởi agent đều gặp lỗi này; sơ đồ là tình huống rủi ro. Nhưng đây là lý do nên giữ transformer/agent bootstrap **đơn giản, có bộ lọc, ít phụ thuộc** và không thực hiện logging phức tạp tại mọi class load.

### 21.1. Điều kiện đặt breakpoints/debug

Khi instrumentation chạy tại class loading, lỗi có thể xuất hiện trước khi logger ứng dụng được cấu hình. Cần chuẩn bị kênh chẩn đoán và cách giảm phạm vi class mục tiêu.

Không đánh giá toàn bộ kết quả chỉ bằng một dòng log vắng mặt ở giai đoạn rất sớm.

## 22. JIT và việc thay đổi mã khi JVM đã tối ưu

JVM có thể tối ưu bytecode bằng Just-In-Time compilation khi chương trình chạy. Điều đó không biến bytecode weaving thành “chỉ dệt khi interpreter chạy”.

Nếu một class được redefine/retransform thành công theo hợp đồng VM, JVM phải quản lý tính đúng đắn của mã đang chạy và các bản tối ưu theo cơ chế của chính VM. Nhưng:

- **Không đảm bảo mọi frame đang hoạt động lập tức dùng phiên bản mới**.
- Chi phí có thể tăng do hủy/tạo lại một số tối ưu.
- Không nên đưa ra lời hứa về throughput hoặc latency khi chưa đo.
- Phân tích profiler cần phân biệt chi phí advice, dispatch, instrumentation và nghiệp vụ.

**Khả năng hot-swap một số mã** không phải cơ chế triển khai thay đổi không gián đoạn tuyệt đối, càng không phải giấy phép thay đổi mọi schema class.

## 23. Runtime AOP và tính đúng đắn nghiệp vụ

Một aspect có thể chạy ở vùng điều khiển quan trọng, không chỉ in log. Nếu around advice có quyền quyết định có gọi continuation hay không, các rủi ro gồm:

- **Bỏ qua phần gốc:** không gọi `proceed` làm nghiệp vụ không chạy.
- **Gọi nhiều lần:** retry không kiểm soát dẫn tới thao tác lặp.
- **Đổi giá trị trả về:** caller nhận kết quả không phù hợp hợp đồng.
- **Che ngoại lệ gốc:** mã logger/cleanup tự ném lỗi khác trong `finally`.
- **Thay đối số không hợp lệ:** làm sai validation hoặc invariant.
- **Tương tác nhiều aspect:** thứ tự advice làm thay đổi tập thao tác được quan sát.

Một advice đo thời gian thường muốn **không thay đổi hành vi nghiệp vụ**. Điều đó nên được kiểm thử: cùng đầu vào, cùng kết quả/ngoại lệ, cùng số lần thực thi phần gốc, trừ phần overhead được cho phép.

### 23.1. Một lần proceed chưa chắc phần gốc chạy một lần

Trong chuỗi nhiều around advice, `proceed` có thể chuyển sang advice kế tiếp chứ không đi thẳng phần gốc. Advice phía trong có thể short-circuit hoặc, nếu công cụ cho phép, gọi tiếp nhiều lần.

Không suy từ số log của advice bên ngoài thành số lần side effect nghiệp vụ.

## 24. Concurrency, context và dữ liệu riêng tư

Một aspect có thể được kích hoạt đồng thời trên nhiều thread. Nếu trạng thái quan sát được lưu ở một biến static dùng chung, dữ liệu của các lời gọi có thể bị ghi đè.

Những nguyên tắc quan trọng:

- Giữ thời điểm bắt đầu, số lần retry và context liên quan trong **phạm vi invocation**.
- Khi dùng ngữ cảnh theo thread, cần lưu và phục hồi đúng cho lời gọi lồng nhau.
- Không mặc định `ThreadLocal` lan truyền sang tác vụ bất đồng bộ hoặc thread khác.
- Không đưa đối tượng join point thô và mảng đối số mutable sang queue xử lý về sau nếu hợp đồng không cho phép.
- Chỉ ghi dữ liệu tối thiểu; che token, account ID và những trường nhạy cảm.
- Không gọi `toString()` trên mọi đối số một cách tự động.

Can thiệp sâu làm tăng khả năng quan sát, nhưng cũng tăng **bề mặt dữ liệu mà mã instrumentation tiếp cận**. Số lượng dữ liệu có thể lấy không phải lý do để lưu tất cả.

## 25. Vấn đề hiệu năng: chi phí không chỉ nằm ở handler

Tùy cơ chế, overhead có thể đến từ:

1. Dispatch qua proxy/interceptor.
2. Kiểm tra pointcut động tại từng lần gọi.
3. Tạo object/record chứa join point context.
4. Boxing/unboxing, reflection hoặc chuyển đổi đối số.
5. Logging, serialization và gửi sự kiện đi xa.
6. Việc chèn hook vào những method tần suất cao.
7. Chi phí class loading và transformer.
8. Retransformation, verification và tối ưu JIT bị ảnh hưởng.
9. Đồng bộ/lock trong advice hoặc global metrics.
10. Vòng lặp recursion hoặc retry gây thực thi thừa.

Một ví dụ:

~~~text
method A được gọi 5 lần/giây → instrumentation có thể chấp nhận
method B được gọi 2 triệu lần/giây → cùng advice có thể là hot-path bottleneck
~~~

Số liệu ở đây **chỉ minh họa tần suất**, không phải benchmark đo được. Chi phí thật phụ thuộc workload/JVM/bytecode và chính sách quan sát.

### 25.1. Chọn điểm cần quan sát, không phải chọn mọi điểm có thể

Pointcut bao phủ “mọi method” làm nguy cơ overhead, vòng lặp logging và dữ liệu quá tải tăng. Ưu tiên ranh giới có nghĩa: API quan trọng, service operation hoặc tập nhỏ được kiểm chứng.

Nếu công cụ có static matching, loại sớm những điểm không thể khớp giúp giảm kiểm tra động. Nhưng việc tối ưu thực tế vẫn phụ thuộc engine.

## 26. Những lỗi triển khai thường gặp

### 26.1. “Bật agent là mọi method được intercept”

**Sai:** transformer có thể chỉ quan sát class loading, hoặc phạm vi biến đổi chỉ gồm một số class.

**Đúng:** kiểm tra những class/điểm thực sự được biến đổi và ca thử chứng minh advice chạy.

### 26.2. “Class đã được nạp vẫn tự dệt lại sau khi bật transformer”

**Sai:** đăng ký transformer sau class loading không tự thay class đã định nghĩa.

**Đúng:** chỉ retransform/redefine nếu VM/công cụ/class hỗ trợ, và kiểm chứng giới hạn.

### 26.3. “Đọc được Method/Field qua reflection nghĩa là chặn được mọi truy cập”

**Sai:** metadata access và join point interception là hai khả năng khác nhau.

**Đúng:** xác minh loại điểm và đường weave.

### 26.4. “Chỉ cần thêm wildcard vào pointcut để chặn constructor/field”

**Sai:** pointcut chỉ chọn trong miền join point model hiện có.

**Đúng:** muốn loại điểm mới phải có cơ chế hỗ trợ.

### 26.5. “Một proxy được tạo thì caller nào cũng đi qua nó”

**Sai:** caller có thể giữ target và gọi trực tiếp.

**Đúng:** đảm bảo các entry point mong muốn dùng đúng ranh giới.

### 26.6. “Static/final/private luôn không thể can thiệp bằng mọi AOP”

**Sai:** đó là những giới hạn phụ thuộc kiểu proxy/subclass và mô hình weaving.

**Đúng:** mô tả ràng buộc cụ thể thay vì phủ định phổ quát.

### 26.7. “Lỗi khi startup luôn là lỗi logic runtime”

**Sai:** load-time transformer hoặc JVM verifier có thể phát hiện lỗi lúc startup.

**Đúng:** phân biệt nguyên nhân, pha phát hiện, class loader, bytecode và mã advice.

### 26.8. “Advice log RETURNED tức nghiệp vụ đã thành công”

**Sai:** method có thể trả một trạng thái từ chối hoặc một future chưa hoàn tất.

**Đúng:** phân biệt normal return và business outcome/async completion.

### 26.9. “Runtime instrumentation không cần kiểm thử production-like”

**Sai:** class loader, module, JVM và profile triển khai có thể khác máy phát triển.

**Đúng:** thử cùng JDK, launch options, classpath/module layout và tải điển hình.

### 26.10. “Không có exception thì không có vấn đề weaving”

**Sai:** một pointcut không khớp hoặc lớp ngoài weaving scope có thể khiến lời gọi chạy bình thường nhưng không có advice.

**Đúng:** kiểm thử độ bao phủ bằng ca dương/âm.

## 27. Quy trình chẩn đoán runtime interception theo tầng

Khi một thao tác không được quan sát, đi theo thứ tự:

1. **Xác định hành vi:** cần method call, method execution, constructor, field access, exception handler hay sự kiện ngoài JVM?
2. **Kiểm tra mô hình:** công cụ có hỗ trợ loại join point đó không?
3. **Xác định kỹ thuật:** proxy, load-time transform, class redefinition hay kỹ thuật khác?
4. **Xác nhận class và loader:** tên chính xác, class được nạp ở đâu, bởi loader nào?
5. **Kiểm tra thời điểm kích hoạt:** agent/transformer có hoạt động trước khi class được định nghĩa không?
6. **Kiểm tra điểm được dệt:** có bytecode/hook thực sự ở phương thức hoặc call site cần quan sát?
7. **Kiểm tra pointcut:** cú pháp, chữ ký, overload, annotation, điều kiện động và ngoại lệ loại trừ.
8. **Kiểm tra runtime path:** lời gọi đi qua proxy hay target; caller có phát sinh điểm không?
9. **Kiểm tra advice:** có chạy nhưng log bị lọc hoặc chính logger gặp lỗi không?
10. **Kiểm tra nhiều aspect:** ordering, short-circuit, recursion và số lần proceed.
11. **Kiểm tra môi trường:** JPMS, permissions, class file version, agent attach, JDK/JVM.
12. **Tái hiện tối thiểu:** một class, một advice, một ca dương, một ca âm.

Không nên sửa cùng lúc pointcut, cấu hình class loading và logic advice; nếu nhiều biến đổi cùng lúc, rất khó xác định nguyên nhân.

## 28. Ma trận kiểm thử giới hạn nền tảng

Một bộ kiểm thử nên xác định trước **phạm vi được cam kết**, thay vì chỉ xem có một dòng log hay không.

| Ca kiểm thử | Câu hỏi xác minh |
|---|---|
| Gọi interface method **qua proxy** | Handler có chạy và chuyển kết quả đúng không? |
| Gọi trực tiếp **target** | Có bị bỏ qua như thiết kế proxy không? |
| Self-invocation | Có nằm trong ranh giới chặn hay không? |
| Static/private/final method | Công cụ và kỹ thuật đang dùng có hỗ trợ không? |
| Constructor và field access | Loại join point có tồn tại trong mô hình không? |
| Class nạp **trước agent** | Có được retransform hợp lệ không hay giữ nguyên? |
| Class nạp **sau agent** | Transformer có nhận và xử lý đúng class không? |
| Hai class loader với cùng tên | Định danh class/loader có đúng mục tiêu không? |
| Java module giới hạn reflective access | Advice có xử lý thiếu quyền/truy cập không? |
| Runtime dùng phiên bản JDK khác | Class file và agent có tương thích không? |
| Method trả/throw | Advice giữ return value và lỗi theo hợp đồng không? |
| Method đang chạy khi redefine | Các lần vào mới/cũ có được hiểu đúng không? |
| Hoạt động bất đồng bộ | Đo hoàn tất method hay thực sự hoàn tất task? |
| Agent bị tắt hoặc không hỗ trợ | Ứng dụng có phản ứng đúng chính sách không? |

Một kết quả “không chặn được” có thể hoàn toàn đúng nếu đó là **giới hạn công bố**. Chỉ là lỗi khi hệ thống yêu cầu/khẳng định ranh giới ấy được bao phủ nhưng không có bằng chứng thực tế.

## 29. Vòng đời triển khai và khả năng quan sát an toàn

Có ba câu hỏi phải trả lời trước khi đưa runtime instrumentation vào môi trường quan trọng.

**Khởi động và phạm vi:** agent cần được kích hoạt khi nào, class nào cần transform, module/loader nào liên quan? Nếu đòi can thiệp từ trước khi class ứng dụng được tải, thường cần kế hoạch startup phù hợp.

**Thay đổi và rollback:** nếu instrument một class rồi muốn thay đổi/hoàn tác, có thể retransform/redefine theo phạm vi được VM hỗ trợ không? Những frame đang hoạt động, schema class và chuỗi nhiều transformer có thể ảnh hưởng tới tính đúng đắn của thay đổi.

**Lỗi của chính hệ quan sát:** nếu agent, advice hoặc sink hỏng, ứng dụng có tiếp tục không? Với telemetry best-effort, thường muốn hạn chế tác động nghiệp vụ; với kiểm soát bắt buộc cần một hợp đồng fail-open/fail-closed được thiết kế cẩn thận.

Một cơ chế quan sát hữu ích không chỉ có nhiều join point, mà còn phải **giải thích được khi nào nó không quan sát, giữ được hành vi gốc và có thể vận hành an toàn**.

## 30. Bài tập tự kiểm tra

### Bài 1 — Runtime AOP có nghĩa luôn sửa bytecode?

Một nhóm dùng Java Dynamic Proxy để chặn lời gọi qua interface. Họ nói “mọi runtime AOP đều biến đổi bytecode target”.

**Đáp án:** sai. Proxy/interceptor có thể đứng trước target mà không cần sửa bytecode target. Một weaver bytecode lại có cách can thiệp khác.

### Bài 2 — Class được nạp trước khi agent bật

Một transformer được đăng ký sau khi lớp `Ledger` đã được định nghĩa. Có thể kết luận method của `Ledger` đã được dệt lại không?

**Đáp án:** không. Cần cơ chế retransformation/redefinition nếu hỗ trợ và class modifiable. Đăng ký transformer một mình không tự thay class cũ.

### Bài 3 — Java agent in class-name

Một agent in “saw class X”, sau đó trả `null` trong `transform`. Đã dệt before advice vào mọi method của X chưa?

**Đáp án:** chưa. `null` có nghĩa agent không cung cấp bytecode thay thế; in tên lớp chỉ chứng minh nó thấy event class loading.

### Bài 4 — Proxy và self-invocation

`proxy.process()` có log intercept, còn `this.verify()` gọi từ bên trong target không có intercept riêng. Đây có phải lỗi của JVM?

**Đáp án:** không. Đó là đường gọi nội bộ không đi qua proxy. Một cơ chế weaving execution khác có thể có phạm vi khác.

### Bài 5 — Final class

Một cơ chế tạo subclass proxy không thể kế thừa lớp `final`. Có thể suy luận mọi bytecode weaving đều bó tay?

**Đáp án:** không. Ràng buộc của subclass proxy khác với khả năng biến đổi bytecode ở những điểm được mô hình hỗ trợ.

### Bài 6 — Module access

Advice dùng reflection để đọc private field trong module khác rồi gặp lỗi truy cập. Có được kết luận pointcut sai không?

**Đáp án:** không. Vấn đề có thể thuộc quyền reflective access/JPMS của runtime, không phải biểu thức pointcut.

### Bài 7 — Constructor

Một cơ chế chỉ chặn method interface qua proxy. Nó có thể tự động ghi mọi lần `new ServiceImpl()` không?

**Đáp án:** không. Việc target constructor chạy không phải lời gọi method giao diện qua proxy.

### Bài 8 — Đổi bytecode khi method đang chạy

Sau khi redefine class thành công, có chắc mọi stack frame của method vốn đang chạy lập tức dùng phần thân mới không?

**Đáp án:** không. Semantics của VM có thể giữ phiên bản cũ cho frame đang hoạt động; các lần vào sau có thể dùng định nghĩa mới.

### Bài 9 — Observability xuyên tiến trình

Một advice quanh `sendMessage()` chạy sau khi method trả về. Điều đó có chứng minh bên nhận đã xử lý message không?

**Đáp án:** không. Kết thúc lời gọi Java và hoàn tất công việc ở tiến trình bên ngoài là hai sự kiện khác nhau.

### Bài 10 — Thiếu advice nhưng không có lỗi

Một ứng dụng có `submit()` chạy đúng nhưng không ghi sự kiện aspect. Hãy nêu ít nhất bốn nguyên nhân khác nhau.

**Đáp án gợi ý:** pointcut không khớp; class ngoài weaving scope; class được nạp trước lúc transformer hoạt động; caller gọi target trực tiếp; loại join point không được hỗ trợ; advice chạy nhưng logger/sink bị lọc; một advice bao ngoài short-circuit; ca thử không phát sinh join point.

### Bài 11 — Tại sao instrumentation ở startup có thể khó hơn runtime method call?

**Đáp án:** transformer xử lý những class đang trong quá trình định nghĩa; nó có thể chạy trước khi logging được thiết lập, gây nạp thêm class phụ thuộc và vướng class loader/module/bytecode version. Cần bộ lọc hẹp và mã bootstrap đơn giản.

### Bài 12 — Retry bằng multiple proceed

Around advice gọi tiếp hai lần để “an toàn hơn”. Nếu mỗi lần trừ tiền rồi gửi yêu cầu mạng, rủi ro nào?

**Đáp án:** tác dụng phụ có thể lặp; cần kiểm soát idempotency, transaction, lỗi tạm thời, giới hạn retry và bảo đảm công cụ cho phép multiple proceed. Đây là quyết định nghiệp vụ/kiến trúc, không chỉ là cú pháp advice.

## 31. Checklist trước khi tuyên bố “can thiệp lúc chạy bao phủ hệ thống”

1. Tôi đã gọi đúng tên cơ chế: **proxy, LTW, class instrumentation, retransform/redefine** hay một dạng khác?
2. Tôi có biết **điểm nào** được công cụ xem là join point hợp lệ không?
3. Pointcut có xác định đúng phạm vi, bao gồm/loại trừ và điều kiện động không?
4. Với proxy, mọi caller quan trọng có sử dụng đối tượng proxy không?
5. Với LTW, transformer có được kích hoạt trước khi class mục tiêu nạp không?
6. Với class đã nạp, VM/agent/class có đủ điều kiện retransform/redefine không?
7. Class loader, module, package access và classpath có được xác minh?
8. Tôi đã phân biệt lời gọi method, thực thi method, constructor và field access chưa?
9. Tôi có kiểm thử cho self-invocation, direct call và đường ngoài weaving?
10. Tôi có bằng chứng mã **được biến đổi thật**, nếu đang tuyên bố bytecode weaving?
11. Tôi có kiểm thử bảo toàn return value, exception và số lần nghiệp vụ chạy?
12. Môi trường AOT/native/giới hạn attach có ảnh hưởng khả năng triển khai không?
13. Có kiểm soát dữ liệu nhạy cảm, CPU, allocation, logging và reentrancy?
14. Có quy trình rollback, bật/tắt và xử lý lỗi của chính agent?
15. Tôi có ghi rõ **những gì không được bao phủ** để người khác không đặt chính sách bắt buộc ở một ranh giới thiếu chứng minh?

## 32. Tổng kết

**Can thiệp lúc chạy** là một nhóm kỹ thuật, không phải lời hứa rằng mọi câu lệnh Java đều trở thành join point. Proxy quan sát lời gọi qua đối tượng trung gian; load-time weaving có cơ hội biến đổi mã khi class được định nghĩa; Java instrumentation có thể quan sát class loading và, trong các giới hạn của JVM, biến đổi hoặc yêu cầu biến đổi lại những class phù hợp.

**Giới hạn nền tảng** đến từ join point model, class loader, thời điểm định nghĩa class, ràng buộc bytecode/verifier, module/access, khả năng attach, khả năng thay đổi class đã nạp, native/AOT runtime và chính đường thực thi của ứng dụng.

Cách đánh giá đúng không dựa vào từ “runtime” hay một dòng log, mà dựa vào bốn câu hỏi: **(1) mô hình có hỗ trợ loại điểm cần can thiệp? (2) pointcut có chọn điểm đó? (3) mã/đường gọi đã thực sự đi qua cơ chế can thiệp? (4) advice có bảo toàn hợp đồng nghiệp vụ và vận hành được trên nền tảng cụ thể?**

Một thiết kế AOP đáng tin cậy công bố cả **khả năng** lẫn **giới hạn**, kèm thử nghiệm dương/âm tái hiện được trong cùng môi trường triển khai.
