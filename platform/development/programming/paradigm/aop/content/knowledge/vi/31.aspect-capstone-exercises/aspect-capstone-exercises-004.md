# Thực nghiệm khác biệt giữa điểm gọi và điểm thực thi

## 1. Mục tiêu bài thực nghiệm

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming, AOP**), một phương thức có thể được nhìn từ hai vị trí khác nhau:

- **Điểm gọi (method-call join point)**: vị trí nơi chương trình thực hiện lời gọi đến phương thức, tức phía *caller*.
- **Điểm thực thi (method-execution join point)**: sự kiện một phương thức bắt đầu được thực thi ở phía *callee/target*.

Hai khái niệm liên quan với nhau nhưng không đồng nhất. Cùng một phương thức có thể có nhiều vị trí gọi; một vị trí gọi có thể dẫn tới nhiều implementation nhờ đa hình; và lời gọi gián tiếp qua reflection không nhất thiết tạo ra điểm gọi tĩnh tương ứng với phương thức đích trong bộ chọn pointcut. Ngoài ra, không phải mọi hệ AOP đều cung cấp cả hai loại join point.

Bài học này là **một thực nghiệm có giả thuyết, mã chạy, kết quả và phân tích**, nhằm giúp bạn:

1. Vẽ đúng luồng từ caller đến target, phân biệt thời điểm quan sát ở đầu gọi và đầu thực thi.
2. Giải thích sự khác biệt khi nhiều caller gọi cùng một phương thức, khi đối tượng gọi chính phương thức của mình và khi dùng reflection.
3. Hiểu ảnh hưởng của pointcut, weaving/proxy, dynamic dispatch và advice around đối với kết quả thực nghiệm.
4. Có chương trình Java 17+ để đo sự kiện một cách xác định mà không cần thư viện bên ngoài.
5. Biết cách chuyển từ mô hình tự ghi sự kiện sang một thử nghiệm AOP thật với pointcut tương ứng, tránh kết luận quá phạm vi chứng cứ.

**Phạm vi:** AOP nói chung, không mặc định một framework hay một engine cụ thể. Khi nhắc đến cú pháp pointcut kiểu AspectJ, đó là **ví dụ cho một hệ có hỗ trợ call và execution**, không phải tuyên bố cú pháp ấy tồn tại ở mọi AOP engine.

## 2. Hai vị trí trên cùng một đường đi

Xét lời gọi:

~~~java
// Đoạn minh họa nằm trong một phương thức caller, chưa phải file độc lập.
Calculator calculator = new Calculator();
int answer = calculator.add(2, 3);
~~~

Bên trong phương thức đích:

~~~java
// Đoạn minh họa là thân một class Calculator.
public int add(int a, int b) {
    return a + b;
}
~~~

Sơ đồ:

~~~text
Caller.main()                                 Calculator.add()
    |                                               |
    |  [CALL: vị trí calculator.add(2,3)]            |
    +---------------------------------------------->|
                                                    | [EXECUTION: bắt đầu chạy add]
                                                    | return 5
    <-----------------------------------------------+
    | caller nhận 5
~~~

Điểm gọi gắn với **biểu thức/lệnh gọi ở caller**; điểm thực thi gắn với **việc chạy phương thức ở callee**. Nhiều công cụ dùng hai kiểu pointcut tương ứng theo ý tưởng:

~~~text
call(<mẫu chữ ký phương thức>)
execution(<mẫu chữ ký phương thức>)
~~~

Đây là **ký hiệu khái niệm**. Mỗi công cụ hỗ trợ tập join point và cú pháp riêng; một cơ chế proxy chỉ chặn đầu vào phương thức thông qua proxy thường không cung cấp đầy đủ các join point call ở mọi vị trí mã nguồn.

### 2.1. Cách đếm cho đúng

Đừng nhầm “một phương thức có một execution join point trong định nghĩa” với “phương thức chỉ thực thi một lần”. Nếu caller gọi Calculator.add hai lần, khi không bị short-circuit và mọi lời gọi đi tới target sẽ có hai lần thực thi. Ngược lại, nếu hai caller khác nhau đều gọi add, có **hai call site** (hai vị trí mã) nhưng mỗi site có thể được đi qua bao nhiêu lần tùy runtime.

Tách ba khái niệm sau:

| Khái niệm | Đơn vị quan sát | Ví dụ |
| --- | --- | --- |
| **Vị trí call site** | Vị trí câu lệnh/bytecode có invocation | Dòng gọi add trong callerA |
| **Số lần sự kiện call** | Bao nhiêu lần chương trình thực thi qua site đó | Vòng lặp gọi add 10 lần: 10 sự kiện ở một site |
| **Số lần sự kiện execution** | Bao nhiêu lần target method thật bắt đầu | 10 lời gọi đi đến thân add: 10 lần execution |

Vì thế “call nhiều hơn execution” không phải mệnh đề luôn đúng. Advice ở call site có thể trả sớm nên không có execution tương ứng; advice ở execution có thể chặn trước thân target; reflection, mã native, mã sinh hoặc lớp không được weave có thể tạo khác biệt giữa các sự kiện mà engine thực sự quan sát.

## 3. Giả thuyết và các trường hợp cần kiểm tra

Hãy dùng một lớp Engine có phương thức run(String). Chuẩn bị bốn đường đi:

- **T1 — Caller A:** callerA gọi engine.run("A").
- **T2 — Caller B:** callerB gọi engine.run("B").
- **T3 — Tự gọi:** Engine.selfInvoke gọi run("self") bên trong cùng đối tượng.
- **T4 — Reflection:** reflective gọi java.lang.reflect.Method.invoke để chạy Engine.run("reflect").

Giả thuyết trước khi chạy:

1. T1 và T2 có hai vị trí gọi khác nhau, nhưng cùng đi vào một định nghĩa Engine.run.
2. T3 là lời gọi nội bộ. Với bytecode có một call site được weave, có thể quan sát lời gọi này; với cơ chế proxy chỉ can thiệp lời gọi **qua đối tượng proxy**, lời gọi trực tiếp trên đối tượng gốc có thể không được chặn.
3. T4 có lời gọi tĩnh vào **Method.invoke** ở phía caller, nhưng không có một biểu thức trực tiếp engine.run("reflect") tại vị trí ấy. Nếu bản thân Engine.run được weave, execution của nó vẫn có thể quan sát được. Loại call join point mà một weaver nhận diện phải xem theo engine cụ thể.
4. Nếu gọi run lặp nhiều lần, số lần execution tăng theo **số lần thân method bắt đầu**, không phụ thuộc số vị trí call site khác nhau.

**Điểm quyết định:** phần dưới mô phỏng log ở từng ranh giới để học cách đọc dữ liệu. Nó **không tự cài đặt AOP weaving**. Để chứng minh đúng semantics của call/execution pointcut, phải chạy thêm thử nghiệm bằng công cụ AOP thật ở mục 7.

## 4. Thực nghiệm Java 17+ chạy độc lập: ghi sự kiện rõ ràng

Lưu nguyên chương trình sau vào **CallExecutionLab.java**:

~~~java
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

public class CallExecutionLab {
    private static final List<String> EVENTS = new ArrayList<>();

    static void event(String message) {
        EVENTS.add(message);
    }

    static final class Engine {
        void run(String value) {
            event("EXEC Engine.run(" + value + ")");
        }

        void selfInvoke() {
            event("EXEC Engine.selfInvoke");
            event("CALL Engine.selfInvoke -> run");
            run("self");
        }
    }

    static void callerA(Engine engine) {
        event("CALL callerA -> Engine.run");
        engine.run("A");
    }

    static void callerB(Engine engine) {
        event("CALL callerB -> Engine.run");
        engine.run("B");
    }

    static void reflective(Engine engine) throws Exception {
        Method method = Engine.class.getDeclaredMethod("run", String.class);
        event("CALL reflective -> Method.invoke");
        method.invoke(engine, "reflect");
    }

    public static void main(String[] args) throws Exception {
        Engine engine = new Engine();
        callerA(engine);
        callerB(engine);
        engine.selfInvoke();
        reflective(engine);
        EVENTS.forEach(System.out::println);
    }
}
~~~

Chạy từ thư mục chứa tệp bằng **JDK 17 trở lên**:

~~~bash
javac CallExecutionLab.java
java CallExecutionLab
~~~

Nếu compiler mới hơn mà cần kiểm tra cú pháp/source API Java 17, có thể dùng:

~~~bash
javac --release 17 CallExecutionLab.java
java CallExecutionLab
~~~

**Stdout đã đối chiếu thực tế** khi biên dịch bằng javac 24.0.2 với --release 17 và chạy trên JDK 24.0.2:

~~~text
CALL callerA -> Engine.run
EXEC Engine.run(A)
CALL callerB -> Engine.run
EXEC Engine.run(B)
EXEC Engine.selfInvoke
CALL Engine.selfInvoke -> run
EXEC Engine.run(self)
CALL reflective -> Method.invoke
EXEC Engine.run(reflect)
~~~

### 4.1. Giải thích thứ tự từng sự kiện

**T1 — Caller A**

~~~text
CALL callerA -> Engine.run
EXEC Engine.run(A)
~~~

Tại callerA, chương trình ghi một sự kiện CALL **ngay trước** lệnh engine.run. Sau khi điều khiển đi vào Engine.run, method tự ghi sự kiện EXEC. Vị trí ghi dấu là hai chỗ khác nhau trong source và nằm ở hai đầu ranh giới lời gọi.

**T2 — Caller B**

~~~text
CALL callerB -> Engine.run
EXEC Engine.run(B)
~~~

Một call site khác vẫn đi tới cùng thân run. Nếu chỉ quan sát ở đầu thực thi mà không mang theo thông tin caller, hai lượt đều là Engine.run với tham số khác nhau. Nếu chỉ quan sát ở call site, có thể biết mỗi lần xuất phát từ vị trí nào.

**T3 — Gọi từ cùng đối tượng**

~~~text
EXEC Engine.selfInvoke
CALL Engine.selfInvoke -> run
EXEC Engine.run(self)
~~~

Engine.selfInvoke được thực thi, sau đó gọi run trên chính đối tượng hiện tại. Vì ví dụ ghi log trực tiếp ở thân phương thức và ở câu lệnh gọi nội bộ, cả hai loại marker đều xuất hiện. **Không được dùng kết quả này để khẳng định một proxy AOP bất kỳ chặn được self-invocation**: marker ở đây do chính mã nguồn viết ra.

**T4 — Lời gọi thông qua reflection**

~~~text
CALL reflective -> Method.invoke
EXEC Engine.run(reflect)
~~~

Phía caller **gọi Method.invoke**, còn phương thức mục tiêu được kích hoạt gián tiếp. Trong ví dụ, marker EXEC tại run luôn in khi run thực thi, bất kể ai gọi. Nhưng marker CALL ghi rõ vị trí thực tế mà mã Java trực tiếp gọi: Method.invoke. Điều này giúp hình dung tại sao một pointcut **call Engine.run** dựa vào call site tĩnh có thể không bắt được đường gián tiếp tương tự.

### 4.2. Giới hạn và sức mạnh của thí nghiệm

Chương trình chứng minh đường điều khiển và thứ tự **các marker do lập trình viên đặt thủ công**. Nó không chứng minh một engine AOP hỗ trợ loại join point nào, chọn đúng pointcut hay có nhìn thấy bytecode invocation bên trong reflection/runtime hay không. Để kiểm tra điều đó, sử dụng công cụ có tài liệu rõ về call/execution (xem mục 7) và lặp lại cùng bốn ca.

Việc marker CALL được đặt **trước** lệnh gọi còn có một chi tiết: nếu đánh giá receiver/tham số có thể ném lỗi trước khi invocation xảy ra, một log viết không đúng vị trí có thể ghi CALL dù một engine pointcut chưa thực sự vào call join point. Vì thế marker trong ví dụ là mô hình giảng giải, không phải phép đo bytecode tuyệt đối.

## 5. Bảng dự đoán và kết quả kiểm chứng

Từ dữ liệu mục 4, lập bảng:

| Đường đi | Marker phía caller | Marker phía target | Điều được rút ra |
| --- | --- | --- | --- |
| callerA → run | CALL callerA → Engine.run | EXEC Engine.run(A) | Caller A có điểm phát lệnh riêng |
| callerB → run | CALL callerB → Engine.run | EXEC Engine.run(B) | Một định nghĩa phương thức có nhiều call site |
| selfInvoke → run | CALL Engine.selfInvoke → run | EXEC Engine.run(self) | Gọi nội bộ vẫn thực thi target; proxy có thể bỏ qua interception |
| Method.invoke → run | CALL reflective → Method.invoke | EXEC Engine.run(reflect) | Lời gọi gián tiếp và thực thi target nằm ở hai ngữ cảnh khác |

Trong lần chạy này có **bốn lần vào Engine.run**, nhưng chỉ **ba marker CALL trực tiếp đến run** do mã nguồn đặt (A, B, selfInvoke); dòng thứ tư là CALL đến Method.invoke. Không nên biến phép đếm này thành quy tắc “AOP call pointcut chỉ chạy ba lần” khi chưa thử trên engine có weaving thật.

**Phép kiểm tra có thể thực hiện:** đánh dấu trên bản in từng dòng là **đầu gọi** hay **đầu thực thi**, rồi nối các cặp theo ca T1–T4. Mỗi cặp caller-target có thể được tách để so sánh trách nhiệm bắt lỗi, chọn pointcut và đo thời gian.

## 6. Call và execution khác nhau ở điều kiện chọn pointcut

### 6.1. Call pointcut thiên về ngữ cảnh nơi gọi

Trong một hệ có hỗ trợ method-call join point, bộ chọn có thể can thiệp ngay ở nơi gọi. Điều này hữu ích khi bạn quan tâm:

- **Ai đã gọi API?** Ví dụ chỉ áp dụng chính sách cho các call site thuộc một package cụ thể.
- **Lời gọi được phát ra từ khu vực nào?** Có thể phân biệt code thư viện nội bộ với caller bên ngoài.
- **Có cần chặn trước khi đi vào target?** Một around advice ở call site có thể bỏ qua lời gọi nếu hợp đồng cho phép.
- **Điểm gắn vào mã đã build:** muốn thấy call join point ở các caller, engine thường phải quan sát/weave những class chứa call site tương ứng.

Không nên nhầm “call pointcut” với “toàn bộ call stack của caller”; một join point là **sự kiện xác định**, không phải mọi frame dọc đường đi.

### 6.2. Execution pointcut thiên về phương thức được thực thi

Trong hệ có hỗ trợ method-execution join point, bộ chọn hoạt động ở phương thức đích khi nó được vào thực thi, có thể hữu ích để:

- Quan sát **mọi đường gọi** đến cùng implementation mà engine đã weave, kể cả nhiều caller.
- Đặt chính sách gắn với bản thân hoạt động của phương thức thay vì gắn từng vị trí gọi.
- Thu thập thông tin target, lời gọi, thời gian thân method, return/throw theo semantics của engine.
- Giảm nhu cầu weave mọi caller nếu engine hỗ trợ weave ở class đích theo phạm vi cấu hình.

Cần phân biệt **entry của execution join point** với **việc thân phương thức đã chạy xong**. An around advice ở execution có thể thay đổi hoặc bỏ qua continuation của method body; khi đó sự kiện execution advice có thể được quan sát dù body thật không chạy. Muốn khẳng định body đã chạy, cần log hoặc counter **ngay trong target**.

### 6.3. Bảng khác biệt có điều kiện

| Trục so sánh | Call join point | Execution join point |
| --- | --- | --- |
| Vị trí ý niệm | Nơi mã gọi phương thức | Nơi phương thức bắt đầu chạy |
| Ngữ cảnh nổi bật | Caller và call site | Callee/target và method body |
| Nhiều caller cùng target | Có thể có nhiều call site | Cùng một định nghĩa target |
| Reflection | Không giả định có call site tĩnh đến target | Có thể thấy execution target nếu target được weave |
| Tự gọi trong cùng đối tượng | Có thể có call join point ở call site nội bộ nếu đã weave | Execution có thể được can thiệp nếu method được weave |
| Proxy chỉ bọc đối tượng | Không đại diện đầy đủ cho mọi call site | Gần với chặn lời gọi qua proxy, nhưng vẫn không phải execution weaving tổng quát |
| Phạm vi cần instrument | Code chứa call site phù hợp | Code chứa target method phù hợp |

Đây là **so sánh về mô hình**, không phải ma trận cam kết cho mọi runtime. Hệ AOP chỉ hỗ trợ interception dựa trên proxy có thể không phơi bày loại call join point để chọn độc lập.

## 7. Mở rộng sang thử nghiệm AOP thật với pointcut call/execution

Để kiểm chứng join point thật, cần một **engine có hỗ trợ cả method-call và method-execution pointcut**. Ví dụ sau viết theo cú pháp pointcut của **AspectJ** như một lựa chọn thực nghiệm, không yêu cầu người học dùng engine này cho mọi dự án.

Cần phân biệt hai mức bằng chứng:

1. **Thử nghiệm Java ở mục 4:** chương trình độc lập và stdout đã được kiểm chứng; các marker đặt thủ công.
2. **Thử nghiệm engine ở mục 7:** cần cài và dùng phiên bản compiler/weaver cùng runtime tương thích với JDK đang dùng; stdout và frame chính xác phụ thuộc cách engine weave/cấu hình. Mã bên dưới là **bộ ba tệp mô tả đầu vào cho engine**, không thể biên dịch tệp .aj bằng javac thông thường.

### 7.1. WorkUnit.java

~~~java
public class WorkUnit {
    public void execute(String label) {
        System.out.println("BODY " + label);
    }

    public void callSelf() {
        execute("self");
    }
}
~~~

### 7.2. Client.java

~~~java
public class Client {
    public static void main(String[] args) {
        WorkUnit unit = new WorkUnit();
        unit.execute("external");
        unit.callSelf();
    }
}
~~~

### 7.3. ObserveJoinPoints.aj

~~~java
public aspect ObserveJoinPoints {
    before(): call(void WorkUnit.execute(String)) {
        System.out.println("CALL " + thisJoinPointStaticPart.getSourceLocation());
    }

    before(): execution(void WorkUnit.execute(String)) {
        System.out.println("EXEC " + thisJoinPoint.getArgs()[0]);
    }
}
~~~

Đây là mã theo cú pháp **AspectJ-style .aj**; yêu cầu compiler/weaver hỗ trợ ngôn ngữ aspect, và cần cấu hình classpath/runtime phù hợp với phiên bản thực tế. Phần SOURCE LOCATION có thể khác giữa các môi trường do đường dẫn và thông tin debug; đừng đóng băng chuỗi nguyên văn này làm assertion.

**Điều cần quan sát khi tất cả class liên quan được weave đúng:**

- Với câu lệnh unit.execute("external") ở Client: có **CALL tại Client** và **EXEC của WorkUnit.execute**, ngoài thông báo BODY.
- Với lời gọi execute("self") ở WorkUnit.callSelf: có **CALL trong WorkUnit.callSelf** và **EXEC của WorkUnit.execute**, ngoài thông báo BODY.
- Nếu chỉ weave WorkUnit mà không weave Client theo quy tắc engine, **các call site ở Client có thể thiếu advice call**, trong khi advice execution ở WorkUnit vẫn có thể hoạt động.
- Nếu only call pointcut được chọn, đừng mặc định nó quan sát mọi đường gián tiếp vào WorkUnit. Nếu execution pointcut được chọn, hãy xác nhận class target thực sự đã được weave.

Một cách thực nghiệm phù hợp là sử dụng bộ công cụ AspectJ đã cài theo tài liệu chính thức phiên bản đang sử dụng, biên dịch ba tệp bằng compiler hỗ trợ .aj, xác nhận **log weaving cho cả Client và WorkUnit**, rồi chạy **artifact đã được weave** với runtime tương thích. Vì phiên bản compiler, classpath và cơ chế weave phụ thuộc cài đặt, phần này không đưa ra dòng lệnh giả định chắc chắn có thể chạy trên mọi máy.

### 7.4. Lưu ý về thứ tự advice

Nếu cả hai advice cùng áp dụng cho một lời gọi, CALL và EXEC là **hai ranh giới khác nhau**. Trong đường đi bình thường, advice call ở phía caller có thể chạy trước khi vào phương thức, sau đó advice execution chạy khi tới target. Tuy nhiên, một advice around có thể bỏ qua proceed, trả sớm hoặc ném lỗi; vì vậy trong một ca thực tế không nên khẳng định luôn có đủ cặp CALL/EXEC.

Khi có nhiều aspect, chính sách precedence và cách sắp xếp advice trước/sau/quanh cũng ảnh hưởng thứ tự in. Muốn kết luận cần đọc **event trace có nhãn join point và advice**, không chỉ đếm hai từ CALL và EXEC ở cuối chương trình.

## 8. Bài kiểm tra nâng cao: đa hình và kiểu tĩnh/động

Xét đoạn minh họa:

~~~java
interface Processor {
    void process();
}

final class FastProcessor implements Processor {
    @Override
    public void process() {
        System.out.println("FAST");
    }
}

// Trong một phương thức gọi:
Processor service = new FastProcessor();
service.process();
~~~

Tại call site, kiểu biến được khai báo là Processor, còn object thật là FastProcessor. Phần thực thi diễn ra ở FastProcessor.process() sau dynamic dispatch. Một pointcut gắn với **chữ ký tĩnh ở call site** và một pointcut gắn với **method execution thực tế** có thể match khác nhau, tùy ngôn ngữ pointcut, rule matching và engine.

Cần kiểm tra:
- Chữ ký dùng để match call là chữ ký nào được compiler/weaver ghi nhận?
- Execution advice áp dụng ở interface, class triển khai hay cả hai theo pointcut?
- Target object runtime có phải class con/implementation khác không?
- Method bridge, default method hoặc override có làm sinh thêm phương thức trung gian không?

Đừng phán đoán “call chỉ thấy interface, execution luôn thấy implementation” như một quy tắc tuyệt đối cho mọi AOP framework. Hãy dùng **đúng engine** để xuất thông tin join point và so sánh signature, declaring type, runtime target.

## 9. Bài kiểm tra nâng cao: self-invocation

Có một khác biệt nổi bật giữa cách instrument bằng weaving và chặn thông qua proxy.

### 9.1. Weaving ở call site hoặc method body

Nếu code bên trong WorkUnit.callSelf() được weave, một call join point tại lệnh execute("self") có thể có advice tương ứng. Nếu WorkUnit.execute() được weave theo execution pointcut, mỗi lần vào method đó có thể kích hoạt advice execution, kể cả lời gọi nội bộ.

Tập join point được weave vẫn phụ thuộc luật match, phạm vi class và cấu hình. Không có bằng chứng rằng “mọi self-call đều bị bắt” chỉ vì đã bật một weaver.

### 9.2. Chặn bằng proxy

Một proxy thường hoạt động khi caller đi **qua đối tượng proxy**. Khi target gọi this.execute() hoặc gọi trực tiếp phương thức khác trên chính instance target, đường đi đó có thể không qua proxy. Vì vậy advice chỉ gắn với proxy có thể xuất hiện với lời gọi ngoài nhưng biến mất khi tự gọi.

Tình huống cần kiểm tra:

~~~text
externalCaller --> proxy --> target.callSelf()
                            |
                            +--> this.execute() --> target.execute()
                                 (có thể không đi qua proxy)
~~~

Nếu bạn thử nghiệm bằng proxy nhưng gọi trực tiếp target từ main, bạn có thể bỏ qua chính bộ chặn. Thực nghiệm phải ghi rõ caller giữ reference nào: proxy hay target gốc.

## 10. Bài kiểm tra nâng cao: reflection, method handles và code được sinh

Trong Java, Method.invoke giúp gọi phương thức qua reflection:

~~~java
// Đoạn minh họa, nằm trong phương thức có WorkUnit unit.
java.lang.reflect.Method method =
        WorkUnit.class.getMethod("execute", String.class);
method.invoke(unit, "via-reflection");
~~~

Ở mã nguồn caller, lệnh invocation trực tiếp là **method.invoke(...)**, không phải **unit.execute(...)**. Nếu engine dựa trên weave call site tĩnh, không được tự giả định nó biến lời gọi reflection thành call join point của WorkUnit.execute. Tuy nhiên, nếu thân WorkUnit.execute đã được weave theo execution, việc chạy qua reflection vẫn có thể kích hoạt advice khi method đích thật bắt đầu.

Tương tự, mã được sinh động, method handle, JNI, bytecode generator và classloader khác nhau có thể tạo đường gọi đặc biệt. Hãy tách:

- **Phần mã thực tế chạy tại caller**: nhìn thấy những instruction/call site nào?
- **Phương thức cuối cùng được thực thi**: target nào nhận quyền điều khiển?
- **Phạm vi instrumentation/weaving**: phần bytecode nào đã được engine theo dõi?
- **Log và exception**: dấu vết đang đến từ caller, target, proxy hay code sinh?

Nếu một loại join point không quan sát được, có thể do khả năng engine, cấu hình instrumentation hoặc đường điều khiển khác mô hình, thay vì do AOP “bị hỏng”.

## 11. Advice có thể phá quan hệ một call – một execution

Không phải mọi lời gọi đều tạo đúng một lần thực thi thân target. Dưới đây là các ca quan trọng:

| Trường hợp | Tại đầu gọi | Tại đầu thực thi | Vì sao cần kiểm tra |
| --- | --- | --- | --- |
| Lời gọi bình thường | Một call event cho một lần đi qua call site được instrument | Một execution nếu target được vào bình thường | Baseline |
| Around tại call trả sớm | Có thể có call advice | Không đi vào target | Cache hoặc authorization có chủ đích |
| Around tại call gọi proceed hai lần | Có thể có một lần vào call advice | Có thể thực thi target hai lần | Retry/side effect |
| Around tại execution trả sớm | Call có thể vẫn được quan sát | Advice execution chạy, thân target có thể không chạy | Phân biệt advice entry và body entry |
| Target ném exception | Call đã phát sinh | Target có thể đã chạy rồi throw | Kết quả không thành công vẫn là execution |
| Nhiều caller | Các site khác nhau | Cùng một phương thức được vào nhiều lần | Không đếm call site như invocation |
| Reflection | Caller trực tiếp gọi reflection API | Target có thể được thực thi | Cơ chế chọn join point khác nhau |

**Ví dụ suy luận:** nếu advice around ở phía call dùng cache và trả dữ liệu mà không proceed, bạn có thể thấy một **sự kiện call** và **không có lần execution của target**. Đây có thể là hành vi mong đợi. Nhưng nếu advice logging lại ghi một “method executed” ngay ở call entry, metric sẽ sai.

Trong các phép đo:
- **Số lần gọi logic** không luôn bằng **số attempt**.
- **Số lần advice được kích hoạt** không luôn bằng **số lần thân target thực sự chạy**.
- **Số vị trí call site** là một đại lượng cấu trúc, không phải bộ đếm số lần chạy.

Khi cần kiểm chứng, thêm một counter ngay đầu **thân phương thức đích** và một counter cho mỗi advice/event. Hai bộ đếm này cho biết chính xác điểm nào có khác biệt.

## 12. Pointcut theo vị trí code và theo target

Một lợi ích của việc phân biệt call và execution là thiết kế pointcut có chủ đích.

### 12.1. Muốn quan sát caller

Ví dụ: chỉ theo dõi lời gọi từ module bên ngoài vào một API. Nếu engine hỗ trợ call join point và ràng buộc phạm vi lexical/within/withincode tương ứng, có thể chọn call site thuộc một package hoặc class caller.

Vấn đề là nếu module caller không nằm trong phạm vi weaving, call advice ở đó có thể không xuất hiện. Do vậy **việc phụ thuộc vào call pointcut có thể yêu cầu instrument các consumer**; không chỉ đặt aspect vào thư viện target rồi mặc định mọi caller đã được weave.

### 12.2. Muốn quan sát mọi lần vào target

Ví dụ: đo số lần một implementation xử lý công việc, bất kể được gọi từ module nào. Nếu engine hỗ trợ execution join point, instrumentation trong method đích thường là lựa chọn tự nhiên hơn. Nhưng vẫn phải định nghĩa đúng tập target class được weave và lưu ý advice execution có thể bỏ qua thân method.

### 12.3. Muốn quan sát chính sách ở đầu proxy

Nếu công cụ AOP chỉ hỗ trợ proxy interception, hãy nói rõ **đường gọi qua proxy** là đơn vị quan sát. Đừng đặt tên metric là “mọi method call trong JVM” hoặc kết luận tương đương với call pointcut kiểu weaving. Một interceptor tại proxy có thể truy cập Method/args/target nhưng bản thân điều đó không biến nó thành call-site weaving.

### 12.4. Tránh pointcut quá rộng

Một pointcut call chọn cả lời gọi của logic ghi log vào chính nó có thể gây reentrancy hoặc recursion. Một execution pointcut chọn quá rộng có thể làm chậm cả helper method hoặc biến đổi những nơi không mong muốn.

Thiết kế **positive case và negative case**: một phương thức phải match và một phương thức tuyệt đối không được match. Ghi rõ lý do giới hạn và kiểm tra bằng trace thực tế.

## 13. Cách đọc stack trace khi thực nghiệm

Stack trace cũng giúp truy ra đường đi, nhưng không nên xem nó là danh sách mọi join point AOP:

~~~text
Caller.callerA(...)
  --> Engine.run(...)
      --> lỗi được ném
~~~

Khi exception được tạo ở Engine.run, stack trace thường hiển thị method đích gần phía trên và caller ở bên dưới. Nếu có proxy/reflection/weaver, có thể xuất hiện thêm frame trung gian hoặc mã sinh. Ngược lại, advice được weave trực tiếp vào bytecode có thể **không có frame riêng**.

Phân biệt:

- **Call stack hiện tại** tại thời điểm chụp.
- **Stack trace đã lưu trong Throwable** tại thời điểm lỗi được ghi, có thể chứa frame method đã unwind khỏi stack hiện tại.
- **Các event call/execution** do advice hoặc instrumentation ghi: đây là dòng thời gian sự kiện, không nhất thiết bằng một stack snapshot.

Một trường hợp exception được ném ở target rồi bị advice catch và trả fallback có thể có execution event nhưng không có exception thoát ra caller. Nếu advice ở call site ném lỗi trước khi proceed, có thể không có execution event target. Vì vậy phải kết hợp trace, event log, số attempt và kết quả cuối.

## 14. Thiết kế bài thực nghiệm có phép kiểm soát

Để kết luận vững, thực hiện theo ma trận thay vì chỉ chạy một lần:

| Lượt | Đổi điều kiện | Giữ cố định | Bằng chứng cần thu |
| --- | --- | --- | --- |
| A | Gọi trực tiếp từ callerA | Cùng target, cùng đầu vào | Call marker và execution marker |
| B | Gọi từ callerB | Cùng target implementation | Phân biệt call site |
| C | Gọi từ chính target | Cùng method run | Tính hiện diện của self-call |
| D | Gọi qua reflection | Cùng method run | Caller gọi Method.invoke và target vẫn vào method |
| E | Chỉ bật advice call ở engine thật | Cùng mã và weaving scope đã ghi | Match ở site nào? |
| F | Chỉ bật advice execution | Cùng mã và weaving scope | Target nào thật sự được instrument? |
| G | Bật cả hai loại advice | Cùng mã, cùng input | Thứ tự event, số lần, exception |
| H | Around call chặn hoặc retry (nếu được phép) | Cùng target | Số lần call advice so với target-body |
| I | Đổi phạm vi weaving của caller | Không đổi target | Call site biến mất/xuất hiện ra sao? |

**Trong mỗi lượt, chỉ thay một yếu tố** và lưu:
- JDK/phiên bản engine AOP, compiler/weaver, build flags.
- Class nào đã được weave; class nào do proxy tạo; caller có đi qua proxy không.
- Source file, method, thread, logical request id, attempt id.
- Kết quả và exception thực tế, counter ở thân target, log từ call/execution advice.
- Lệnh chạy và output mong đợi/quan sát được.

Nếu thử nghiệm nhận kết quả không trùng dự đoán, trước hết kiểm tra việc method thực sự được gọi và việc engine có instrument đúng bytecode. Thiếu event không mặc nhiên chứng minh lỗi logic.

## 15. Lỗi thường gặp khi phân tích hai loại join point

1. **Gọi call site là mọi lần execution:** một chỗ gọi có thể thực thi 100 lần, một phương thức có thể có 100 caller khác nhau. Luôn đếm riêng vị trí và sự kiện.
2. **Tưởng proxy interception là call pointcut đầy đủ:** proxy thường chỉ nhận lời gọi qua chính proxy, không weave mọi caller.
3. **Bỏ qua self-invocation:** test ngoài chạy nhưng lời gọi nội bộ bypass proxy; với weaving, kết quả còn tùy phạm vi instrument.
4. **Dùng reflection rồi mong có lời gọi tĩnh đến target:** tại caller, mã gọi reflection API. Phân biệt đường đi đến target với bytecode call site.
5. **Cho rằng không thấy EXEC là target không làm gì:** có thể log hoặc advice bị thiếu do cấu hình; cần counter ở thân target và trace thật.
6. **Cho rằng nhìn thấy execution advice là body đã chạy:** around advice có thể bỏ qua proceed. Dùng body-entry marker để chứng minh.
7. **Bỏ qua dynamic dispatch:** call signature và execution implementation có thể match khác nhau khi có interface, kế thừa, override.
8. **Không ghi phạm vi weave:** class caller có thể chưa được weave dù class target đã được weave; call advice ở caller khi đó không xuất hiện.
9. **Trộn sự kiện với stack snapshot:** một stack trace không kể đủ toàn bộ lịch sử các call/execution advice.
10. **Đo số lần chạy từ logger thay vì target:** retry, cache, fallback hoặc lỗi logger làm log và thực thi khác nhau.
11. **Dựa vào thứ tự file để suy ra advice order:** precedence cần cấu hình và kiểm chứng theo engine thực tế.
12. **Bật/tắt nhiều điều kiện cùng lúc:** không còn cơ sở kết luận thay đổi nào làm phát sinh hoặc loại bỏ khác biệt.

## 16. Bài tập tự luyện với tiêu chí chấm rõ ràng

### Bài A — Lặp một call site

Trong main của CallExecutionLab, thêm vòng lặp gọi callerA(engine) ba lần. Trước khi chạy, dự đoán có mấy dòng CALL callerA và EXEC Engine.run(A) mới. Sau khi chạy, giải thích sự khác biệt giữa **số dòng log tăng** và **số vị trí câu lệnh gọi trong source**.

**Tiêu chí:** ba lần gọi callerA tạo thêm ba cặp sự kiện; call site trong callerA vẫn là một vị trí mã.

### Bài B — Tạo hai implementation

Thay Engine bằng interface Worker có hai implementation; cho một caller giữ reference Worker và lần lượt gán mỗi implementation. Gắn marker trong cả hai method body. Dự đoán caller có thay đổi vị trí lệnh call hay không, và execution đi vào implementation nào.

**Tiêu chí:** phân biệt kiểu khai báo của reference, dispatch runtime và nơi execution thật.

### Bài C — Tạo lời gọi gián tiếp

Viết thêm một helper dùng Method.invoke hoặc MethodHandle để gọi Engine.run. Ghi marker ở lệnh gọi helper, ở invocation API và ở thân target. So sánh với callerA trực tiếp.

**Tiêu chí:** không tự đặt nhãn CALL Engine.run cho một bytecode site chỉ gọi Method.invoke; chỉ phát biểu về AOP call pointcut sau khi có engine test.

### Bài D — So sánh weaving và proxy

Trên một engine AOP có hỗ trợ weaving call/execution, chạy cùng target với hai advice và ghi log join point signature, source location, thread. Nếu có thể, chạy thêm proxy interception để so sánh self-invocation.

**Tiêu chí:** nêu rõ engine/phiên bản, class được weave, đường đi qua proxy, các sự kiện quan sát thực tế và giới hạn kết luận.

### Bài E — Around chặn trước target

Tạo một advice around ở call join point cho phép trả kết quả cache mà không proceed. Đặt counter trong target. Gọi hai lần với dữ liệu đã cache/không cache và so sánh call advice, execution advice và body count.

**Tiêu chí:** phân biệt hành vi được thiết kế với “thiếu execution do cấu hình”, đồng thời không chấp nhận dữ liệu cache sai hợp đồng.

## 17. Checklist trước khi kết luận

- [ ] Tôi biết đang so sánh **vị trí call site**, **số lần sự kiện call** hay **số lần method execution**.
- [ ] Tôi phân biệt được caller và callee, cùng điểm ghi sự kiện cho từng bên.
- [ ] Tôi đã thử tối thiểu hai caller, một self-call và một lời gọi gián tiếp.
- [ ] Tôi biết ví dụ Java tự ghi marker hay engine AOP thật sự tạo join point; không đánh đồng hai loại bằng chứng.
- [ ] Tôi đã xác minh cơ chế proxy/weaving, engine version, tập class được instrument và pointcut.
- [ ] Tôi hiểu rằng advice around có thể bỏ qua hoặc gọi proceed nhiều lần.
- [ ] Tôi đã xem xét đa hình, reflection, exception, lời gọi nội bộ và mã sinh nếu chúng liên quan.
- [ ] Tôi có stdout/event trace hoặc assertion chính xác kèm số lần target thực chạy.
- [ ] Tôi có cả test phải match lẫn test không được match, và thay một điều kiện mỗi lượt.
- [ ] Mỗi kết luận chỉ nói về cơ chế, engine và tình huống đã kiểm chứng.

**Kết luận thực nghiệm:** điểm gọi trả lời **“lời gọi được thực hiện ở đâu, bởi ai?”**, còn điểm thực thi trả lời **“phương thức nào đang được vào thực thi?”**. Chúng liên quan nhưng không thay thế nhau. Bằng cách tách call-site event, target-body event và interception event, ta có thể giải thích đúng trường hợp nhiều caller, tự gọi, reflection, đa hình, retry hoặc short-circuit, đồng thời tránh quy kết sai cho AOP chỉ vì một marker không xuất hiện.
