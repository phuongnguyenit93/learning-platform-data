# Xác nhận aspect đã được cấu hình và nạp trong AOP

## 1. Vì sao kiểm tra một tệp aspect tồn tại là chưa đủ?

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), một **aspect** mô-đun hóa mối quan tâm cắt ngang như ghi nhật ký, đo thời gian, tracing, kiểm soát truy cập hoặc theo dõi lỗi. Một **pointcut** chọn những **join point** mà aspect cần can thiệp; **advice** là logic được thực thi tại những điểm ấy. Tùy mô hình AOP, cơ chế áp dụng có thể là weaving, interceptor, proxy, decorator hay một dạng instrumentation khác.

Khi lời ghi log mong đợi không xuất hiện, nhiều người kết luận ngay rằng pointcut sai. Nhưng một aspect có thể **chưa hề được đăng ký, nạp hoặc gắn vào chương trình**. Ngược lại, aspect có thể đã nạp thành công mà vẫn **không có join point nào khớp** hoặc lời gọi đi qua một đường không được instrument.

Vì vậy, cần phân biệt ít nhất bốn lớp bằng chứng:

1. **Được khai báo/cấu hình**: chương trình đã có thông tin rằng aspect nên được áp dụng.
2. **Được phát hiện và nạp/khởi tạo**: mã aspect hoặc đối tượng chứa advice đã được runtime/build pipeline nhận diện và sẵn sàng hoạt động.
3. **Được liên kết với điểm thực thi phù hợp**: weaving, proxy hoặc interceptor chain thực sự có mặt tại join point cần quan sát.
4. **Đã kích hoạt trong một lượt thực thi cụ thể**: điểm thực thi xảy ra, pointcut/điều kiện runtime thỏa mãn, và advice chạy đúng theo chính sách.

Không được suy từ mức 1 rằng mức 4 chắc chắn đúng. Tương tự, một log không xuất hiện **không đủ** để kết luận aspect chưa nạp: log có thể bị lọc, sink hỏng, nhánh điều kiện không thỏa hoặc thao tác chưa đi qua join point.

Mục tiêu cuối cùng không phải “thấy tên aspect trong cấu hình” mà là có **bằng chứng kiểm chứng được từ cấu hình đến hành vi thật**.

## 2. Bộ khái niệm chẩn đoán

**Aspect:** module định nghĩa concern, pointcut và advice hoặc các quy tắc liên quan. Một số hiện thực AOP tạo đối tượng aspect ở runtime; một số dệt logic thành bytecode từ trước. Vì vậy, “đã load một instance aspect” không phải cách kiểm tra phổ quát.

**Join point:** vị trí mà cơ chế AOP có thể quan sát/can thiệp, ví dụ lời gọi phương thức hoặc thực thi thân phương thức tùy join point model.

**Pointcut:** biểu thức/quy tắc chọn join point. Có thể chứa điều kiện tĩnh trên method/type và điều kiện động trên arguments, object hoặc control flow.

**Advice:** hành vi chạy trước, sau hoặc bao quanh join point, có thể điều khiển việc thực thi target theo contract.

**Weaving:** thao tác gắn aspect vào chương trình. Việc weaving có thể xảy ra khi biên dịch, với bytecode có sẵn, khi nạp lớp hoặc qua các cơ chế instrumentation phù hợp. Không phải mọi AOP đều dùng weaving bytecode.

**Proxy/interceptor:** lớp trung gian hoặc chuỗi callback kiểm soát lời gọi đi qua một đối tượng đại diện. Nếu caller gọi thẳng target, lời gọi có thể không đi qua proxy.

**Activation:** một lời chạy cụ thể làm advice thực thi. Để xác nhận activation, cần một lượt gọi và bằng chứng độc lập như bộ đếm advice, marker test-only hoặc kết quả có thể quan sát được.

**Coverage:** phạm vi các kiểu điểm, lớp, method, call site và đường vào thực sự được bảo vệ. Một lần advice chạy **chưa chứng minh** toàn bộ ứng dụng có coverage đầy đủ.

## 3. Chuỗi kiểm chứng từ ý định đến hành vi

~~~text
Aspect được khai báo
         |
         v
Cấu hình / registration được đọc
         |
         v
Aspect được nhận diện và sẵn sàng
         |
         v
Target/join point thuộc phạm vi instrument
         |
         v
Pointcut match (và điều kiện động đúng)
         |
         v
Caller đi qua đúng ranh giới
         |
         v
Advice thực sự chạy
         |
         v
Lỗi/giá trị/side effect vẫn đúng chính sách
~~~

Mỗi mũi tên là một giả định có thể kiểm tra riêng. Không được nhảy từ “có annotation/tệp cấu hình” sang “advice chắc chắn chạy” khi chưa xác minh đường nối ở giữa.

Bảng kiểm chứng:

| Mức | Câu hỏi | Bằng chứng phù hợp |
| --- | --- | --- |
| Khai báo | Có quy tắc chọn aspect trong cấu hình/build không? | Nguồn cấu hình và artifact build đúng |
| Registration | Bộ quản lý đã đăng ký aspect/interceptor chưa? | Metadata hoặc danh sách registration ở runtime |
| Nạp/khởi tạo | Mã aspect có thể được runtime sử dụng không? | Diagnostic lifecycle, log nạp hoặc kiểm tra instance khi có |
| Instrumentation | Target/call site có được weave/wrap không? | Weave report, kiểm tra bytecode/proxy chain hoặc công cụ phù hợp |
| Pointcut | Chữ ký và điều kiện có match không? | Diagnostic match, test gọi đúng method/context |
| Invocation | Caller thực sự đi qua điểm được instrument không? | Trace test-only hoặc invocation spy |
| Activation | Advice đã chạy bao nhiêu lần và khi nào? | Bộ đếm/marker từ chính advice |
| Outcome | Advice có giữ/đổi kết quả theo policy không? | Assert giá trị, exception và side effect |

Một chương trình có thể pass các bước đầu mà fail bước cuối, hoặc ngược lại một log tình cờ xuất hiện từ code thủ công nhưng aspect thực ra chưa kích hoạt. Cần bằng chứng **liên quan đúng cơ chế AOP**.

## 4. Bước 1 — xác định cấu hình có hiệu lực, không chỉ cấu hình trên đĩa

“Đã cấu hình” nghĩa là bản cấu hình đó **được build hoặc runtime hiện tại thực sự sử dụng**. Những lỗi thường thấy:

- Tệp cấu hình nằm trong source tree nhưng không được đưa vào package/artifact cuối.
- Một profile hoặc biến môi trường làm tắt instrumentation.
- Điều kiện cho phép tải aspect chỉ bật ở development mà tắt ở production.
- Build đã thay đổi nhưng ứng dụng đang chạy bytecode/artifact cũ.
- Hai cấu hình cùng tên, một bản mới không được chọn.
- Một module/plug-in chứa aspect chưa được đưa vào classpath/module path.
- Cấu hình load-time agent không được truyền cho đúng tiến trình.
- Aspect registration được thực thi quá muộn: một số đối tượng/call site đã được tạo trước khi interceptor được lắp đặt.

Các câu hỏi cần trả lời:

1. **Tiến trình nào** đang được chẩn đoán, dùng artifact/build nào?
2. **Bản cấu hình hiệu lực** chứa lựa chọn aspect nào?
3. **Ai là nơi đọc cấu hình**: build tool, class loader, agent, container của ứng dụng hay mã tự đăng ký interceptor?
4. **Thời điểm** cấu hình được đọc là trước hay sau target được biên dịch/tạo/nạp?
5. Có điều kiện feature toggle, environment hoặc predicate nào làm aspect không đăng ký không?

Khi dùng cấu hình runtime, nên xuất một **diagnostic summary có kiểm soát**: tên component, phiên bản cấu hình, loại instrumentation, danh sách target pattern và trạng thái bật/tắt. Không cần xuất secret/token hay toàn bộ cấu hình nhạy cảm để chứng minh aspect được chọn.

## 5. Bước 2 — phân biệt “được tạo/nạp” với “đã dệt vào target”

Một nhầm lẫn phổ biến là xem constructor hoặc static initializer của một class aspect đã chạy như bằng chứng aspect hoạt động ở mọi join point. Điều đó chỉ chứng minh code đã được nạp/khởi tạo theo đường đó; **không chứng minh** pointcut match hay method target đã instrument.

Ngược lại, trong một số cơ chế weaving tĩnh, logic advice có thể đã được gắn vào bytecode mà không cần quản lý một instance aspect giống đối tượng thông thường. Vì vậy, không nên đặt tiêu chí “phải tìm thấy bean/instance tên X” làm luật chung cho AOP.

### Trong mô hình interceptor hoặc proxy

Bằng chứng có thể gồm:

- Registration của interceptor/advice có mặt trong chain.
- Object mà caller dùng có đúng là đối tượng đại diện/decorator hay không.
- Invocation handler đang trỏ đến target và chain phù hợp.
- Đối tượng có được xây qua composition root/factory phù hợp hay tạo thẳng bằng constructor.
- Registration có đúng phiên bản, pointcut hoặc thứ tự interceptor không.

### Trong mô hình weaving

Bằng chứng có thể gồm:

- Compiler/weaver report về những lớp và join point được dệt.
- Class/jar hoặc artifact thực tế đã chứa kết quả weaving.
- Agent/class loader được kích hoạt trên đúng tiến trình khi load-time weaving.
- Target class đã được nạp sau khi instrumentation được thiết lập nếu cơ chế yêu cầu.
- Mã chạy thật có phải bytecode đã dệt hay một bản duplicate không được dệt.

**Một lớp được load thành công khác với một lớp đã được woven.** Hai trạng thái này có thể đồng thời đúng, chỉ một trạng thái đúng, hoặc ý nghĩa khác nhau tùy mô hình.

## 6. Bước 3 — khớp pointcut và xác định đúng loại join point

Khi registration và instrumentation đã đúng mà advice vẫn không chạy, mới nên điều tra **selection**:

- Tên class, package, module hoặc method có khác pattern không?
- Method signature có thêm overload, đổi kiểu trả về, đổi parameter không?
- Pointcut chọn **method call** hay **method execution**?
- Kiểu join point đó được runtime hỗ trợ không?
- Method thuộc class đã được instrument hay được nạp bởi class loader khác?
- Điều kiện annotation có retention và vị trí phù hợp không?
- Điều kiện argument, object identity hoặc dynamic control flow đã thỏa chưa?
- Có điều kiện loại trừ hoặc pointcut phủ định làm mất match không?
- Aspect có bị precedence/around advice khác short-circuit trước khi đến phần bên trong không?

Ví dụ biểu thức pointcut trong một ngôn ngữ AOP cụ thể có thể chọn method execution:

~~~java
// Mã minh họa ý tưởng một ngôn ngữ pointcut; không phải Java độc lập.
execution(* ReportService.export(..))
~~~

**Điểm tổng quát:** phải phân biệt “cấu hình aspect đã nạp” với “biểu thức chọn đúng điểm”. Cú pháp trên chỉ minh họa một ngôn ngữ pointcut, không được coi là tiêu chuẩn bắt buộc của mọi công nghệ AOP.

### Call và execution có thể cho kết quả khác

~~~text
CallerA ----- call site A ----+
                             |
CallerB ----- call site B ---> Target.process()
                             ^ method execution
~~~

Một cơ chế instrument các call site chỉ áp dụng được tại những caller được instrument. Một cơ chế instrument method execution có thể quan sát phần thân method bất kể caller cụ thể, miễn phần thân đã được instrument. Vì vậy, cần kiểm tra **đường caller thật** khi chẩn đoán, không chỉ tên method.

Một self-call trong cùng object có thể bỏ qua proxy-based interception nhưng vẫn đi qua method-execution weaving. Không kết luận “AOP luôn bỏ qua lời gọi nội bộ” hoặc “AOP luôn bắt được lời gọi nội bộ” khi chưa biết cơ chế đang dùng.

## 7. Bước 4 — tạo probe tối thiểu có kết quả quan sát độc lập

Cách đáng tin nhất để xác nhận advice hoạt động là tạo một **phép thử có mục tiêu**:

1. Chọn một method/operation nhỏ, deterministic và không có side effect nguy hiểm.
2. Bảo đảm test gọi đúng đối tượng hoặc artifact cần instrument.
3. Bật marker ở chính advice cho môi trường test, hoặc đếm số lần advice thực thi.
4. Gọi method đúng một lần qua đường cần kiểm tra.
5. Assert kết quả nghiệp vụ vẫn đúng và advice được chạy đúng số lần.
6. Có **negative control**: gọi đường không instrument (nếu cho phép) để thấy marker không xuất hiện, hoặc vô hiệu hóa registration trong test.
7. Nếu có nhiều advice, kiểm tra thứ tự và tương tác; một before chạy không có nghĩa around/after cũng đúng.

Cần tách ba dấu hiệu:

- **Target chạy**: chỉ chứng minh method nghiệp vụ được gọi.
- **Advice marker chạy**: chứng minh một advice cụ thể đã kích hoạt.
- **Kết quả nghiệp vụ đúng**: chứng minh việc thêm advice không làm sai return/exception trong trường hợp test.

Một marker đặt ngoài advice, ví dụ handler đã tự ghi dòng “ABOUT TO CALL”, **không phải** bằng chứng advice chạy.

### Không dùng production logging làm nguồn duy nhất

Nếu log sink bị tắt, bị filter hoặc lỗi, advice có thể đã chạy mà dòng log không được xuất ra. Ngược lại, một dòng log có thể được in thủ công từ handler mà không liên quan aspect. Trong test, ưu tiên counter/spy được đặt trực tiếp ở advice và assertion rõ ràng. Trong production, có thể dùng event/metrics chẩn đoán riêng, theo chính sách bảo mật và tải hệ thống.

## 8. Ví dụ Java 17+ chạy được: chứng minh registration và interception

Ví dụ sau không cần một thư viện AOP bên ngoài. Nó dùng Java dynamic proxy để **minh họa một cơ chế invocation interception**, từ đó thấy rõ các tầng bằng chứng. Dynamic proxy của Java là một **phương tiện minh họa**, không phải định nghĩa đầy đủ của AOP hay thay thế mọi khả năng weaving.

Mục tiêu:

- Có một handler đóng vai trò advice quanh method invocation.
- Khi caller dùng object proxy, handler chạy.
- Khi caller cầm object đích và gọi trực tiếp, handler **không chạy**.
- Khi target tự gọi method khác trên cùng instance, lời gọi nội bộ không tự đi qua proxy bên ngoài.
- Vẫn kiểm chứng giá trị trả về của từng lời gọi và số lượt target chạy.

Tạo tệp **AspectActivationDemo.java**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AspectActivationDemo {
    interface Work {
        String run(String input);
        String internal();
    }

    static final class WorkImpl implements Work {
        int runs = 0;

        @Override
        public String run(String input) {
            runs++;
            System.out.println("TARGET run " + input);
            return "OK:" + input;
        }

        @Override
        public String internal() {
            System.out.println("TARGET internal");
            return run("inner");
        }
    }

    static final class TraceHandler implements InvocationHandler {
        private final Work target;
        int adviceCalls = 0;

        TraceHandler(Work target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            adviceCalls++;
            System.out.println("ADVICE before " + method.getName());
            try {
                Object result = method.invoke(target, args);
                System.out.println("ADVICE after " + method.getName());
                return result;
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }
    }

    public static void main(String[] args) {
        WorkImpl target = new WorkImpl();
        TraceHandler handler = new TraceHandler(target);

        Work proxy = (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[] { Work.class },
                handler);

        System.out.println("PROXY " + Proxy.isProxyClass(proxy.getClass()));
        System.out.println("RESULT outer=" + proxy.run("outer"));
        System.out.println("RESULT internal=" + proxy.internal());
        System.out.println("RESULT direct=" + target.run("direct"));
        System.out.println("ADVICE_CALLS " + handler.adviceCalls);
        System.out.println("TARGET_RUNS " + target.runs);

        if (handler.adviceCalls != 2 || target.runs != 3) {
            throw new AssertionError("Unexpected interception coverage");
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac AspectActivationDemo.java
java AspectActivationDemo
~~~

Đầu ra dự kiến (xác định đối với chương trình này):

~~~text
PROXY true
ADVICE before run
TARGET run outer
ADVICE after run
RESULT outer=OK:outer
ADVICE before internal
TARGET internal
TARGET run inner
ADVICE after internal
RESULT internal=OK:inner
TARGET run direct
RESULT direct=OK:direct
ADVICE_CALLS 2
TARGET_RUNS 3
~~~

### Giải thích vì sao hai bộ đếm khác nhau

- Object proxy được tạo và caller sử dụng qua interface Work; dòng PROXY true xác nhận class proxy được tạo.
- proxy.run("outer") đi qua InvocationHandler: adviceCalls tăng một lần; target.run cũng tăng một lần.
- proxy.internal() đi qua InvocationHandler một lần nữa, nên adviceCalls tăng thành hai.
- Thân target.internal() gọi run("inner") **trên chính đối tượng target**, không đi qua proxy; vì thế không xuất hiện dòng ADVICE before run ở bước này.
- target.run("direct") được gọi thẳng trên target, cũng không đi qua proxy.
- Tổng cộng có **hai lời gọi interceptor** và **ba lần thực thi method run của target** (outer, inner, direct).

Điều này minh họa khác biệt giữa:

1. Registration/creation của proxy.
2. Caller sử dụng proxy ở đúng ranh giới.
3. Advice thực sự kích hoạt.
4. Phạm vi không bao gồm lời gọi trực tiếp hoặc self-call.

**Giới hạn của ví dụ:** Java dynamic proxy intercept lời gọi qua những interface được proxy triển khai; nó không tự thêm method-execution weaving vào bytecode target, không bắt mọi field access và không phải một AOP engine toàn diện. Với cơ chế instrumentation khác, self-invocation có thể có behavior khác. Không chuyển trực tiếp kết luận của ví dụ thành quy tắc chung cho mọi AOP.

## 9. Bằng chứng “đã nạp” có giá trị đến đâu?

Có thể sắp các tín hiệu chẩn đoán theo độ mạnh:

| Bằng chứng | Kết luận cho phép | Không đủ chứng minh |
| --- | --- | --- |
| Tệp aspect/annotation có trong source | Có khai báo về mặt source | Runtime dùng đúng file đó |
| Cấu hình hiệu lực nhắc đến aspect | Runtime/build được yêu cầu áp dụng aspect | Aspect đã instrument target |
| Class aspect đã được class loader nạp | Class hiện diện trong tiến trình/loader | Có join point match |
| Constructor/initializer aspect chạy | Đối tượng/thành phần được khởi tạo | Mỗi method cần bảo vệ đều đi qua advice |
| Có woven-bytecode/weaver report | Target/join point tương ứng đã instrument theo report | Một lượt runtime sẽ nhất định kích hoạt |
| Object proxy tồn tại | Có đại diện được tạo | Mọi caller đều dùng object proxy |
| Counter trong advice tăng sau lời gọi test | Advice đã chạy trên lượt đó | Mọi đường vào đều được bảo vệ |
| Runtime test trên nhiều đường PASS | Coverage đã được kiểm chứng trong tập trường hợp test | Bao phủ tuyệt đối mọi đường/phiên bản chưa kiểm thử |

Không có một tín hiệu duy nhất thay thế toàn bộ chuỗi. Một xác nhận “aspect đã nạp” mạnh nhất thường là **tập bằng chứng**: cấu hình hiệu lực, registration/weaving đúng target, và test chạy advice trong đường vào mong muốn.

## 10. Chẩn đoán khi advice không chạy: cây quyết định

~~~text
Không thấy advice chạy
        |
        v
Cấu hình hiệu lực có bật/đăng ký aspect?
   | KHÔNG -> kiểm tra packaging, profile, module, startup
   | CÓ
   v
Mã aspect đã được nhận diện/nạp theo mô hình AOP?
   | KHÔNG -> kiểm tra discovery, loader, agent, compiler, classpath
   | CÓ
   v
Target/call site đã được instrument/wrap?
   | KHÔNG -> kiểm tra weaving/proxy creation và object identity
   | CÓ
   v
Pointcut match join point và điều kiện runtime?
   | KHÔNG -> kiểm tra signature, annotation, args, exclusion
   | CÓ
   v
Caller đã đi qua đúng ranh giới?
   | KHÔNG -> direct call, self-call, object ngoài vòng quản lý
   | CÓ
   v
Có advice khác short-circuit hoặc order gây khác biệt?
   | CÓ -> kiểm tra chain và precedence
   | KHÔNG
   v
Advice có chạy nhưng bằng chứng/log bị lọc/hỏng?
   | CÓ -> dùng counter/spy/test marker trực tiếp
   | KHÔNG -> kiểm tra bản build, concurrency, runtime diagnostics
~~~

Đây là **thứ tự điều tra có tính kinh tế**: trước tiên chứng minh có registration và instrumentation, sau đó mới đào sâu pointcut. Đừng bắt đầu bằng việc đổi pattern vô tội vạ, vì nó có thể vô tình mở rộng coverage gây ảnh hưởng ngoài mong muốn.

## 11. Những nguyên nhân cấu hình và nạp thường gặp

### 11.1. Chưa đưa aspect vào artifact

Một file source xuất hiện trong IDE nhưng bị loại khỏi compilation/package. Hãy kiểm tra artifact mà tiến trình thực sự chạy, không chỉ working tree của developer.

### 11.2. Mã được biên dịch nhưng không được weaving

Một compilation Java thông thường có thể tạo class target không chứa instrumentation trong khi aspect definition vẫn nằm trong dự án. Nếu mô hình yêu cầu compile-time weaving, phải chắc build pipeline đã chạy compiler/weaver với cả aspect và target.

### 11.3. Agent load-time không được bật ở tiến trình thật

Một môi trường local có thể truyền agent cho JVM còn staging/production thì không. Hãy kiểm tra launch arguments và class loader của đúng tiến trình. Không kết luận dựa vào một console khác hay process chưa đúng.

### 11.4. Object đích được tạo thẳng

Nếu chỉ những object xây qua một factory/proxying layer mới có interceptor, code gọi new Target() có thể bỏ qua. Kiểm tra object identity và class của object caller đang giữ.

### 11.5. Đăng ký sau khi object hoặc class đã được tạo/nạp

Một số cơ chế yêu cầu registration trước khi tạo proxy hoặc trước khi class được instrument. Nếu setup chạy muộn, những đối tượng cũ có thể không được cập nhật tự động.

### 11.6. Chọn nhầm loại join point

Một pointcut cho call site không tự động tương đương pointcut cho method execution. Nếu caller không được instrument, advice call có thể không chạy dù method được thực thi.

### 11.7. Điều kiện động không thỏa

Pointcut có thể khớp tên method nhưng chỉ kích hoạt khi tham số, annotation, actor hoặc control flow đúng. Cần test cả trường hợp thỏa và không thỏa; nếu chỉ nhìn một lượt không match, dễ chẩn đoán sai.

### 11.8. Một aspect khác thay luồng thực thi

Around advice ngoài cùng có thể trả fallback mà không tiếp tục chain, nên target và advice phía trong không chạy. Đây là **hành vi điều khiển hợp lệ theo một policy**, không nhất thiết là lỗi nạp aspect.

### 11.9. Chạy một bản class khác

Đường classpath, duplicate dependency, shading, jar cũ hoặc class loader riêng có thể làm runtime chọn bytecode khác bản đã inspect. So sánh build identifier, class origin và phiên bản; không log thông tin nhạy cảm ngoài nhu cầu chẩn đoán.

### 11.10. Lỗi telemetry đánh lừa kết quả

Logger bị filter hoặc exception bị bắt ở nơi khác làm marker biến mất. Advice có thể chạy nhưng không tạo dòng log; dùng spy/counter có assert thay vì chỉ tìm chuỗi văn bản.

## 12. Đối chiếu bằng chứng nạp aspect với cơ chế AOP đang chạy

Không có một dấu hiệu **“aspect đã load”** áp dụng cho mọi cơ chế. Hãy chọn **bằng chứng kích hoạt** phù hợp, rồi thử một join point dương và một join point âm:

| Cơ chế | Bằng chứng tối thiểu về cấu hình/nạp | Bằng chứng bổ sung để xác nhận advice hoạt động |
| --- | --- | --- |
| **Compile-time weaving** | Aspect và source target thực sự là input của compiler AOP ở build tương ứng | Weave diagnostics/artifact đã dệt và phép gọi vào method target trong artifact cuối |
| **Post-compile weaving** | Binary aspect/weaver được chạy trên đúng class/JAR input | Output woven **khác** bản gốc, được đóng gói và nạp thật; test dương/âm trên output |
| **Load-time weaving** | Agent/config đã hiệu lực **trước khi** class mục tiêu được định nghĩa và classloader nằm trong scope | Log weaving cho class đích và phép gọi sau nạp; không giả định một class cũ tự được dệt lại |
| **Proxy/interceptor** | Registry/composition root tạo chain và caller giữ đúng **proxy reference** | Counter trong interceptor cho thấy lời gọi đi qua chain; kiểm tra self-call/direct target riêng |
| **Decorator thủ công** | Wrapper được lắp đúng vị trí cung cấp object cho caller | Test đi qua wrapper, đối chứng với đường vào dùng core trực tiếp |

Ví dụ: khi constructor aspect được gọi nhưng interceptor counter vẫn bằng 0, chỉ có **bằng chứng class/instance đã được tạo**, chưa thể khẳng định matcher đúng hay đường gọi đã được dệt/chặn. Nếu weave log có match nhưng runtime chạy JAR nguyên bản, lỗi nằm ở **artifact triển khai**, không phải nhất thiết ở pointcut.

Với mỗi cơ chế, kết luận cuối cùng cần hai tầng riêng: **đã lắp/cấu hình/nạp đúng** và **advice thực sự chạy tại join point dự kiến mà không thay đổi sai return, exception hoặc side effect**. Không thay pointcut theo cảm tính khi tầng trước chưa có bằng chứng.

## 13. Bất đồng bộ: aspect có nạp nhưng điểm quan sát chưa đúng

Một lời gọi có thể trả CompletableFuture đang pending hoặc đăng ký callback rồi trả về ngay. Around/after-returning trên lời gọi này có thể chạy hoàn toàn chính xác, nhưng không xuất hiện log “tác vụ hoàn thành” vì tác vụ chưa hoàn tất.

Ví dụ timeline:

~~~text
t0: caller -> advice -> submitTask()
t1: submitTask trả future pending; advice after-returning chạy
t2: worker thực thi, có thể trên luồng khác
t3: future complete success/error/cancel
~~~

Nếu mục tiêu là xác nhận **aspect ở invocation** được nạp và chạy, marker ở t0/t1 là thích hợp. Nếu mục tiêu là quan sát **completion** ở t3, cần hook đúng mô hình bất đồng bộ; việc after-returning không chờ completion **không phải lỗi activation**.

Những vấn đề khác:

- Callback có thể chạy ngay khi đăng ký hoặc muộn sau đó; đừng mặc định luôn trên thread khác.
- ThreadLocal/correlation context không tự theo executor; diagnostic logger có thể thiếu trace ID dù advice chạy.
- Lỗi trong completion callback có thể ảnh hưởng dependent stage; marker test không nên đổi outcome nghiệp vụ.
- Một task bị hủy trước khi chạy có thể không tạo execution advice/marker, dù submission advice đã chạy.
- Publisher có thể chỉ được tạo chứ chưa được subscribe; không tự subscribe từ advice để “kiểm thử” vì có thể tạo side effect mới.

Vì thế, trước khi kết luận aspect chưa được nạp, hãy viết rõ **join point nào** cần xuất hiện và **sự kiện nào** phải làm nó phát sinh.

## 14. Nhiều đường vào và độ bao phủ

Ngay cả sau khi test một lời gọi có marker đúng, hệ thống vẫn có thể bỏ sót:

- HTTP endpoint phụ hoặc thao tác quản trị.
- CLI/batch/scheduler.
- Message consumer và retry worker.
- Callback, event listener hoặc executor task.
- Direct service call, self-invocation hoặc reflection.
- Method overload hoặc override mới.
- Một class loader/module khác.
- Một instance được tạo ngoài factory quản lý.
- Một phiên bản artifact mới chưa có cấu hình weaving tương ứng.

Nếu concern là logging, thiếu một đường có thể làm mất thông tin vận hành. Nếu concern là authorization, thiếu một đường có thể trở thành lỗ hổng. Do đó phải kiểm thử **cùng chính sách tại những đường vào quan trọng**.

Một test hữu ích không chỉ ghi “adviceCalls > 0”. Nó xác minh **đúng số lần** và **đúng đối tượng**: một lượt gọi qua proxy có thể làm adviceCalls tăng 1; lời gọi nội bộ có thể không tăng; một phương thức bị gọi lại do retry có thể tăng nhiều lần theo chính sách.

## 15. Diagnostic marker nên được thiết kế thế nào?

Một marker chẩn đoán tốt phải:

1. Được phát **trong chính advice** đang cần xác minh.
2. Có định danh join point/operation rõ ràng.
3. Phân biệt phase (before, after-returning, after-throwing, around).
4. Có correlation ID hoặc invocation ID khi concurrent execution quan trọng.
5. Được bật có kiểm soát, tránh gây nhiều log khi tải lớn.
6. Không tiết lộ tham số nhạy cảm, token, mật khẩu hay nội dung dữ liệu.
7. Không tự throw hoặc block làm thay đổi kết quả nghiệp vụ ngoài chính sách.
8. Có cách kiểm thử độc lập ngoài việc nhìn stdout.

Ví dụ fragment có tính minh họa:

~~~java
// Fragment trong advice, counter được cung cấp qua test fixture.
long n = adviceCounter.incrementAndGet();
debugProbe.record("method-entry", n);
~~~

Đây không phải chương trình độc lập: adviceCounter và debugProbe là thành phần của test. Trong production có thể cần counters riêng cho nhiều luồng và sampling; tránh thay đổi hiệu năng quá mức hoặc che lỗi business bằng lỗi của reporter.

Nếu logger mất dữ liệu, counter trong test chạy ổn định hơn. Nếu counter cũng không tăng, tiếp tục truy vết registration/instrumentation/pointcut/invocation.

## 16. Precedence và short-circuit: khởi tạo đúng vẫn có thể không chạy advice mong đợi

Giả sử có chuỗi:

~~~text
Around A (ngoài cùng)
  -> Before B
    -> Around C
      -> Target
~~~

Nếu A không gọi phần tiếp tục, B, C và Target có thể không được chạy. B không phát marker không nhất thiết là B chưa đăng ký. Nó có thể nằm phía trong nhánh đã bị short-circuit.

Một failure khác là A ném exception trước khi proceed, khiến chain dừng. Nếu thứ tự advice không được thiết kế rõ, một security check có thể chạy sau một action không an toàn hoặc telemetry ghi nhận sai.

Khi nhiều aspect cùng match:

- Định nghĩa ai phải chạy trước/ngoài/ trong.
- Ghi marker theo phase thay vì một log chung.
- Kiểm tra trường hợp target thành công và target ném lỗi.
- Kiểm tra around có gọi continuation chính xác số lần theo hợp đồng không.
- Thử nhánh fallback/deny/cached result có chủ đích.
- Kiểm tra retry không nhân đôi side effect ngoài policy.

**Aspect đã nạp** chỉ là điều kiện cần; **thứ tự và điều kiện control flow** còn quyết định advice cụ thể có chạy hay không.

## 17. Quan sát lỗi và giá trị trả về để tránh false positive

Một bài test “có marker” có thể pass nhưng aspect vẫn sai nếu:

- Advice gọi target hai lần.
- Advice trả giá trị thay thế không đúng.
- Advice nuốt exception nghiệp vụ.
- After/finally logger ném exception làm che lỗi target.
- Advice thực thi trên một thread khác không được phép, làm đổi context.
- Lời gọi bị chặn dù chính sách phải cho phép.
- Advice chặn cả method không nằm trong phạm vi dự định vì pointcut quá rộng.

Bởi vậy, test nên assert:

| Trường hợp | Bằng chứng cần có |
| --- | --- |
| Target success | Caller nhận đúng return value và target chạy đúng số lần |
| Target throw | Caller nhận loại/cause/đối tượng exception đúng hợp đồng |
| Logging failure | Không che business outcome nếu policy best effort |
| Denied access | Không gọi target, không có side effect nếu policy yêu cầu |
| Async completion | Observer phù hợp thấy đúng terminal event |
| Direct/self-call | Coverage được định nghĩa và kiểm chứng |
| Multiple aspects | Thứ tự và số lần gọi đúng policy |

Nếu aspect là quan sát thuần túy, test phải chứng minh **không thay đổi outcome nghiệp vụ**. Nếu aspect cố ý điều khiển luồng như access control hoặc caching, outcome mới phải được mô tả thành hợp đồng cụ thể.

## 18. Khi nào dùng debug logs, weave report, test spy và bytecode inspection?

| Kỹ thuật | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Cấu hình hiệu lực / registration listing | Xác nhận phần mềm có ý định bật aspect | Không chứng minh điểm được can thiệp |
| Build/weaver diagnostics | Cho biết những điểm được dệt hoặc lý do không dệt | Có thể không phản ánh artifact được chạy |
| Runtime class/proxy inspection | Xác minh caller đang giữ proxy hoặc bản class cụ thể | Không chứng minh pointcut động sẽ match |
| Marker/counter trực tiếp trong advice | Bằng chứng advice đã chạy ở lượt test | Chỉ bao phủ lượt gọi đã thử |
| Integration test từng entry point | Chứng minh đường vào thực tế | Có thể thiếu đường chưa được liệt kê |
| Bytecode inspection | Xem dấu hiệu instrumentation ở class/jar | Không thay kiểm thử behavior runtime |
| Telemetry/trace production | Quan sát nhiều tình huống thực | Sampling, filter, drop hoặc thiếu context |
| Negative control | Giúp phân biệt có instrumentation với chạy bình thường | Cần chọn nhánh điều khiển hợp lệ để không đổi dữ liệu |

Không dùng một công cụ để giải đáp câu hỏi mà nó không cung cấp bằng chứng. Ví dụ **class loaded** không chứng minh **advice executed**, và **advice executed** trên một test không chứng minh **mọi caller đều covered**.

## 19. Quy trình chẩn đoán thực tế theo mức chi phí

### Pha A — Xác nhận mục tiêu

Viết một câu kiểm chứng rõ ràng: “Advice ghi sự kiện vào của operation X phải chạy đúng một lần khi method Y được gọi qua đường Z với context hợp lệ”. Nếu không có mục tiêu, các log chung rất dễ làm nhóm nhầm triệu chứng.

### Pha B — Kiểm tra cấu hình có hiệu lực

Xác định đúng artifact, tiến trình, phiên bản, class loader và profile. Tìm evidence rằng aspect được đăng ký/kích hoạt. Không sửa pointcut trước khi đã chứng minh runtime có dùng cấu hình cần thiết.

### Pha C — Kiểm tra instrument target

Với weaving, xem diagnostics/output binary; với proxy, xem object/handler chain; với decorator, xem wiring của caller. Tách “đối tượng tồn tại” với “đúng đường thực thi đi qua nó”.

### Pha D — Kiểm tra selection

Xác minh signature, annotation, loại join point, điều kiện args/cflow, exclusion và version của target. Thử một pointcut rất hẹp trên method test an toàn thay vì nới rộng toàn hệ thống.

### Pha E — Kích hoạt thử nghiệm có kiểm soát

Dùng marker test-only đặt trong advice, gọi một lượt deterministic và assert số lần advice/target cũng như return/exception. Có negative control khi khả thi.

### Pha F — Mở rộng coverage và phục hồi

Kiểm thử direct call, self-invocation, callback, worker, retry và startup order. Sau khi tìm được lỗi, sửa đúng tầng (packaging, registration, instrumentation, selection hay control flow), rồi chạy lại regression tests.

Đây là quy trình **đi từ cấu hình đến evidence**, thay vì sửa ngẫu nhiên nhiều thành phần và khó xác định nguyên nhân.

## 20. Những lỗi chẩn đoán phổ biến

**“Có file aspect trong dự án nghĩa là đã nạp.”** Sai. Build/runtime có thể không dùng file đó.

**“Class aspect đã được load nên advice chắc chắn chạy.”** Sai. Chưa chứng minh target được instrument hoặc pointcut match.

**“Có proxy thì mọi method đều đi qua proxy.”** Sai. Caller có thể giữ target trực tiếp, hoặc self-call không đi qua proxy.

**“Không có log nghĩa là advice không chạy.”** Chưa chắc. Logging có thể bị filter hoặc fail.

**“Pointcut đúng trên giấy nên runtime chắc match.”** Sai. Có điều kiện động, overload, type visibility và phạm vi weaving.

**“Advice chạy một lần là cả hệ thống đã covered.”** Sai. Cần test những đường vào quan trọng.

**“Around ngoài cùng không proceed cũng là lỗi cấu hình của advice bên trong.”** Sai. Đây là thay đổi control flow có thể được thiết kế; cần xem precedence/policy.

**“After returning chạy nghĩa là async task thành công.”** Sai. Chỉ method đã trả về handle bình thường.

**“Dùng constructor log của aspect làm kiểm thử duy nhất.”** Sai. Nó không chứng minh activation tại join point.

**“Kiểm tra class file ở build directory là đủ.”** Sai. Process có thể đang chạy artifact khác.

## 21. Bài tập tự đánh giá

**Câu 1.** Một lớp aspect có trong source, nhưng khi chạy không có log. Bước đầu tiên nên kiểm tra gì?

**Đáp án:** Xác định cấu hình/build/artifact có hiệu lực và cơ chế AOP đã đăng ký/nhận diện aspect hay chưa. Không đổi pointcut ngay khi chưa biết aspect có tham gia runtime hay không.

**Câu 2.** Runtime đã khởi tạo aspect instance. Điều đó chứng minh method nhạy cảm được bảo vệ chưa?

**Đáp án:** Chưa. Cần bằng chứng join point được instrument, pointcut match và caller đi qua ranh giới thực thi đúng.

**Câu 3.** Một Java dynamic proxy tồn tại, nhưng caller gọi trực tiếp target. Advice có chạy không?

**Đáp án:** Không qua proxy đó. Phải kiểm tra object reference caller dùng hoặc một điểm enforcement khác. Trong cơ chế weaving vào method execution, kết quả có thể khác.

**Câu 4.** Trong ví dụ Java, vì sao ADVICE_CALLS là 2 nhưng TARGET_RUNS là 3?

**Đáp án:** Hai external call đi qua proxy (run outer và internal). Target.internal tự gọi run inner, rồi main gọi trực tiếp target.run direct, nên ba lần run nhưng chỉ hai lượt interceptor.

**Câu 5.** Lời ghi log ở advice biến mất. Làm sao phân biệt advice không chạy với logger bị filter?

**Đáp án:** Dùng counter/spy test-only nằm trong chính advice và assert sau một lượt gọi. Đồng thời quan sát trạng thái logger theo kênh chẩn đoán phù hợp.

**Câu 6.** Tại sao một advice khác có thể khiến advice đã nạp không chạy?

**Đáp án:** Around advice bên ngoài có thể short-circuit hoặc throw trước khi tiếp tục chain. Precedence và nhánh control flow quyết định điểm nằm trong có được thực thi hay không.

**Câu 7.** After returning của method trả CompletableFuture chạy rồi; có chứng minh task đã hoàn tất không?

**Đáp án:** Không. Đây là invocation return. Cần hook completion để chứng minh trạng thái cuối của future.

**Câu 8.** Một integration test thấy advice chạy từ HTTP nhưng CLI không chạy. Nên xem gì?

**Đáp án:** Lối wiring/target của CLI, phạm vi instrumentation/pointcut, class loader và guard bắt buộc. Không được suy rằng một test HTTP đủ bảo vệ mọi entry point.

**Câu 9.** Một report weaving ghi method X đã được dệt, nhưng marker test không hiện. Có mâu thuẫn không?

**Đáp án:** Không nhất thiết. Có thể runtime dùng artifact khác, pointcut động không thỏa, caller không đi vào đúng path hoặc marker/logger bị vô hiệu. Cần kiểm tra evidence từng tầng.

**Câu 10.** Sau khi xác nhận advice đã chạy, còn phải kiểm tra gì?

**Đáp án:** Số lần gọi target, giá trị/exception, side effect, thứ tự nhiều advice, coverage đường vào và tác động khi instrumentation lỗi.

## 22. Checklist xác nhận aspect đã cấu hình và nạp

- [ ] Đã xác nhận đúng tiến trình, artifact và phiên bản đang chạy.
- [ ] Đã đọc **cấu hình có hiệu lực**, không chỉ file mẫu.
- [ ] Đã xác minh registration/discovery của aspect hoặc interceptor.
- [ ] Đã biết cơ chế áp dụng là weaving, proxy, decorator hay dạng khác.
- [ ] Đã kiểm tra target/call site được instrument đúng.
- [ ] Đã xác nhận pointcut match cả điều kiện tĩnh và động liên quan.
- [ ] Đã có test gọi đúng object và join point cần quan sát.
- [ ] Đã ghi nhận marker/counter **bên trong advice** và so khớp số lần chạy.
- [ ] Đã có negative control phù hợp để phát hiện bypass.
- [ ] Đã kiểm tra direct call, self-call, overload và đường async khi có.
- [ ] Đã kiểm tra error/return/side effect không bị thay đổi ngoài chính sách.
- [ ] Đã kiểm tra precedence/short-circuit nếu có nhiều aspect.
- [ ] Đã phân biệt log bị mất với advice không kích hoạt.
- [ ] Đã xác nhận coverage trên các đường vào quan trọng, không chỉ một luồng.
- [ ] Đã lưu evidence có thể lặp lại trong integration test để phòng regression.

## Kết luận

“Aspect đã được cấu hình và nạp” nên được coi là **một mệnh đề cần có bằng chứng theo nhiều tầng**: cấu hình có hiệu lực, cơ chế đăng ký/nhận diện, instrumentation tại join point, pointcut phù hợp và advice thực sự kích hoạt trong đường chạy mục tiêu. AOP không tự bảo đảm mọi lời gọi đều có advice chỉ vì một module aspect tồn tại. Cách chẩn đoán đáng tin là đi từng tầng từ build/runtime đến test activation, đồng thời kiểm tra đúng return, exception, side effect và những đường vào khác nhau.