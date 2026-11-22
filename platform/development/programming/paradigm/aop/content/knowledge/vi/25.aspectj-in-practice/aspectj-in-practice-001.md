# AspectJ như một ví dụ cụ thể của mô hình AOP có weaving

## 1. Mục tiêu: nhìn thấy AOP hoạt động qua bytecode

**Aspect-Oriented Programming (AOP)** là một cách tổ chức chương trình nhằm mô-đun hóa những *mối quan tâm cắt ngang* (*cross-cutting concerns*) như quan sát thời gian, truy vết, kiểm toán hoặc các chính sách kỹ thuật được áp dụng nhất quán ở nhiều điểm thực thi. Ý tưởng cốt lõi là mô tả **điểm nào cần can thiệp** và **hành vi gì cần thực thi** mà không phải rải cùng đoạn mã vào từng phương thức nghiệp vụ.

**AspectJ** cung cấp một ví dụ cụ thể cho mô hình này bằng cơ chế **weaving**: kết hợp mã aspect với mã chương trình tại các join point phù hợp. Nhờ đó, một lời gọi nội bộ hay một method execution được lựa chọn có thể được can thiệp ngay trong bytecode, không phụ thuộc việc caller cầm một đối tượng wrapper cụ thể.

Bài này dùng AspectJ để hiểu **AOP từ cơ bản tới nâng cao**. Các khái niệm như *join point*, *pointcut*, *advice*, *aspect*, *composition* là kiến thức AOP chung; cú pháp `aspect`, `execution(...)`, `call(...)`, `declare precedence` và công cụ `ajc` là cách AspectJ hiện thực chúng.

Sau bài học, bạn có thể:

1. Giải thích weaving là gì và phân biệt với việc gọi qua một proxy/decorator.
2. Đọc được pointcut, advice và vòng đời thực thi của một aspect kiểu AspectJ.
3. Biên dịch ví dụ Java 17+ kèm một file `.aj`, kiểm chứng thay đổi đầu ra trước/sau weaving.
4. Phân biệt compile-time, post-compile và load-time weaving; nhận biết khi nào một join point bị/mất matching.
5. Thiết kế pointcut chính xác, chọn thứ tự aspect, bảo toàn exception/return và kiểm thử weaving.
6. Hiểu giới hạn về class loader, đồng thời, callback async, chi phí và quyền hạn khi áp dụng AOP.

## 2. Mô hình khái niệm của AOP

### 2.1. Thuật ngữ cơ bản

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Concern** | Một mối quan tâm cần thực thi | Đo thời gian thao tác xử lý |
| **Cross-cutting concern** | Concern đi qua nhiều module | Tracing cho nhiều service |
| **Join point** | Điểm có nghĩa trong quá trình thực thi | Method execution, method call, constructor execution |
| **Pointcut** | Biểu thức chọn các join point | `execution(* demo..*(..))` |
| **Advice** | Mã chạy trước/sau/xung quanh join point | Đếm số lần gọi, log lỗi |
| **Aspect** | Mô-đun chứa pointcut, advice và cấu trúc liên quan | `LatencyAspect` |
| **Weaver** | Thành phần phối hợp advice với các join point phù hợp | Bộ biên dịch/bytecode weaver |
| **Target / advised code** | Mã gốc được tác động | `GreetingService.greet()` |
| **Inter-type declaration** | Bổ sung member hoặc quan hệ kiểu theo cơ chế AspectJ | Thêm phương thức vào một class qua aspect |

**Join point là sự kiện/địa điểm có nghĩa trong execution model**, còn **pointcut là điều kiện mô tả tập join point**. Không nên nhầm pointcut với một lời gọi phương thức cụ thể; pointcut có thể khớp rất nhiều điểm ở nhiều class.

**Advice** có thể quan sát hoặc điều chỉnh hành vi: advice kiểu `around` thậm chí có thể không cho logic gốc chạy, thực thi lại hoặc đổi giá trị trả về. Vì vậy AOP yêu cầu thiết kế hợp đồng và kiểm thử tương đương nghiêm túc, đặc biệt với thao tác có side effect.

### 2.2. Mô hình thay đổi khi có weaving

~~~text
Mã nguồn nghiệp vụ    Mã nguồn aspect          Bộ công cụ weaving
       |                    |                           |
       +--------------------+-------------------------->|
                                                       |
                                             Bytecode đã được woven
                                                       |
                                                       v
                      JVM chạy method đã chứa điểm thực thi advice
~~~

Khi method được weave, lời gọi Java thường đến method đó có thể kích hoạt advice mà caller không phải gọi qua một đối tượng `Proxy`. Đây là điểm khác biệt quan trọng so với một số cơ chế interception dựa hoàn toàn trên wrapper.

**Không nên hiểu weaving là hệ thống JVM tùy ý sửa mọi class đã chạy xong.** AspectJ xử lý bytecode tại giai đoạn biên dịch, sau biên dịch hoặc khi class được định nghĩa bởi class loader phù hợp. Load-time weaving diễn ra trước khi class đích được định nghĩa; nó không đồng nghĩa tùy ý thay đổi mọi class đã được load.

## 3. Weaving, proxy và decorator: giống và khác nhau

| Khía cạnh | Proxy/decorator ở ranh giới lời gọi | Weaving kiểu AspectJ |
| --- | --- | --- |
| Cách can thiệp | Caller phải đi qua wrapper/proxy phù hợp | Bytecode tại join point được kết hợp advice |
| Phạm vi | Thường dựa trên interface, đối tượng hoặc ranh giới đăng ký | Có thể chọn nhiều loại join point trong mô hình AspectJ |
| Self-invocation | Lời gọi trực tiếp bên trong target thường không đi qua wrapper | `execution(...)` được weave tại method có thể áp dụng cả self-call |
| Method call và method execution | Thường thiên về lời gọi qua proxy | Có hai loại join point riêng `call(...)` và `execution(...)` |
| Constructor / field | Wrapper thường không bắt được trực tiếp | AspectJ có designator tương ứng, tùy khả năng và phạm vi weaving |
| Tích hợp | Ít đụng build/class loader hơn | Cần compiler/weaver, cấu hình build/load phù hợp |
| Độ minh bạch | Dễ thấy wrapper khi tạo đối tượng | Source nghiệp vụ có thể không thể hiện advice sẽ chạy |

Ví dụ `service.internal()` gọi `this.process()` trên chính target: một proxy bên ngoài có thể không nhận thấy `process()`, nhưng **AspectJ execution join point** đã được weave ngay trong `process()` vẫn có thể chạy advice khi method đó được thực thi.

Với **call pointcut**, code chứa *vị trí gọi* phải được weave; chỉ weave định nghĩa method đích mà không weave class của caller có thể không bắt được vị trí `call` mong muốn. Đây là khác biệt quan trọng khi quyết định phạm vi triển khai aspect.

Sự lựa chọn giữa proxy và weaving không chỉ là “cái nào mạnh hơn”; cần đánh giá phạm vi join point, quyền kiểm soát mã đích, overhead, tính minh bạch, class loader và khả năng kiểm thử.

## 4. Ba thời điểm weaving

### 4.1. Compile-time weaving (CTW)

**Compile-time weaving** kết hợp mã Java và aspect ngay khi biên dịch bằng `ajc`. Mã nguồn nghiệp vụ và aspect (hoặc aspect đã biên dịch) cùng tham gia công đoạn build. Output là các file `.class` đã được weave.

~~~text
.java + .aj --ajc--> woven .class --JVM--> advice + nghiệp vụ
~~~

Đặc điểm:

- Dễ tái lập ở build pipeline; kết quả weaving có thể được kiểm tra ngay khi build.
- Có thể xử lý những cấu trúc aspect cần nhìn thấy khi compile, chẳng hạn một chương trình tham chiếu member được thêm bởi inter-type declaration.
- Cần kiểm soát cấu hình compiler, phiên bản Java, artifact chứa aspect và các class nguồn tham gia.
- Nếu một class không có trong tập đầu vào build phù hợp, nó có thể không được weave như dự kiến.

### 4.2. Post-compile / binary weaving

Với **post-compile weaving**, ứng dụng được biên dịch thành `.class` hoặc JAR trước, rồi một bước `ajc` khác áp aspect lên **bytecode có sẵn**.

~~~text
.java --javac--> .class/JAR --ajc -inpath + aspect--> woven .class/JAR
~~~

Điều này phù hợp khi không muốn thay compiler của toàn bộ mã nguồn, hoặc cần can thiệp một thư viện mà có quyền xử lý artifact. Tuy nhiên phải bảo đảm đủ class path/aspect path, phạm vi `-inpath`, đồng thời tránh nhập lại chính output làm input của lượt weave tiếp theo. Cần chú ý license và khả năng tương thích bytecode đối với artifact bên thứ ba.

**Điểm phân biệt:** CTW compile nguồn rồi weave; post-compile nhận bytecode đã biên dịch và weave. Cả hai tạo bytecode đã được thay đổi trước khi JVM bình thường load class đích.

### 4.3. Load-time weaving (LTW)

Với **load-time weaving**, bộ weaver can thiệp lúc class loader chuẩn bị định nghĩa class trên JVM. Cách phổ biến là dùng Java agent `aspectjweaver.jar` cùng mô tả aspect/phạm vi trong `META-INF/aop.xml`.

~~~text
JVM startup -javaagent:aspectjweaver.jar
               |
               v
     class loader đọc .class gốc
               |
               v
       weaver áp aspect phù hợp
               |
               v
        JVM định nghĩa class đã weave
~~~

Một số giới hạn:

- Weaver phải biết các aspect đủ sớm **trước lúc class đích được định nghĩa**; class đã load trước đó có thể bị bỏ qua.
- Class loader chỉ có thể weave những class nó trực tiếp định nghĩa theo mô hình LTW; delegation tới parent loader có thể làm thay đổi phạm vi.
- Class loader, module boundary, classpath, artifact chứa aspect và `aop.xml` đều ảnh hưởng tính khả dụng.
- LTW làm phát sinh yêu cầu kiểm soát JVM startup/agent và kiểm thử môi trường runtime, không chỉ build.
- Nếu một class cần biết member do aspect bổ sung ngay khi biên dịch code tham chiếu member ấy, chỉ đổi bytecode ở LTW có thể không đủ; cần sắp xếp compilation phù hợp.

AspectJ mô tả ba giai đoạn chính này trong tài liệu phát triển. Đừng dùng “runtime weaving” để ngụ ý AspectJ mặc định sửa những class đã được định nghĩa và chạy sẵn mà không cơ chế reload/instrumentation chuyên biệt.

## 5. Cú pháp cốt lõi: aspect, pointcut, advice

Một aspect mã nguồn kiểu AspectJ dùng từ khóa `aspect`, có thể chứa khai báo pointcut và advice. Ví dụ minh họa cú pháp:

~~~java
// Giả sử OrderService có public Receipt place(Order).
// Đây là đoạn minh họa trong file .aj, KHÔNG độc lập để biên dịch.
public aspect OrderObservation {
    pointcut placing():
        execution(* OrderService.place(..));

    before(): placing() {
        System.out.println("đang bắt đầu đặt hàng");
    }

    after() returning: placing() {
        System.out.println("method trả về bình thường");
    }

    after() throwing(Throwable problem): placing() {
        System.out.println("method ném " + problem.getClass().getSimpleName());
    }
}
~~~

Những thành phần:

- `execution(* OrderService.place(..))` chọn **method execution** khớp mẫu kiểu trả về bất kỳ và bất kỳ danh sách tham số.
- `before()` chạy trước join point.
- `after() returning` chỉ chạy khi join point kết thúc bình thường.
- `after() throwing(...)` chỉ chạy khi join point kết thúc bằng exception phù hợp.
- `after()` không có điều kiện returning/throwing là dạng finally-like advice, chạy khi join point kết thúc theo cả hai đường.

Ví dụ ở trên minh họa cấu trúc. Khi cần đo thời gian hay bảo đảm cleanup, **around advice với `try/finally`** thường giúp gắn rõ mốc bắt đầu/kết thúc trong một policy. Với `after returning`, giá trị trả về có thể được bind để quan sát nếu khai báo pointcut/advice phù hợp.

### 5.1. Các designator thông dụng

| Designator | Chọn theo | Lưu ý |
| --- | --- | --- |
| `execution(SignaturePattern)` | Thực thi method | Weave code của method được chọn |
| `call(SignaturePattern)` | Điểm gọi method | Weave *caller code* chứa lời gọi |
| `within(TypePattern)` | Vị trí mã nằm trong một kiểu | Bổ sung filter lexical |
| `withincode(SignaturePattern)` | Join point nằm trong phần thân method/constructor phù hợp | Lọc lexical theo code chứa join point |
| `this(TypeOrId)` | Đối tượng `this` tại join point | Ở một số join point có thể khác `target` |
| `target(TypeOrId)` | Đối tượng đích được gọi | Cần hiểu instance thực tế |
| `args(TypeOrId, ..)` | Đối số và có thể bind giá trị | Không đồng nghĩa lấy mọi object graph |
| `@annotation(AnnotationTypeOrVar)` | Annotation liên quan join point | Chỉ áp nơi annotation được giữ và match theo quy tắc |
| `cflow(Pointcut)` | Join point trong control flow của một pointcut | Có chi phí/semantics động, phải đo đạc |
| `if(BooleanExpression)` | Điều kiện động | Tránh đưa nghiệp vụ nặng vào kiểm tra pointcut |

Ví dụ pointcut kết hợp:

~~~java
// Giả sử tồn tại package demo.billing.
// Minh họa cú pháp, không phải chương trình độc lập.
pointcut measuredCalls():
    execution(public * demo.billing..*(..))
    && !within(demo.billing.observability..*);
~~~

Biểu thức logic `&&`, `||`, `!` có thể kết hợp những điều kiện selection. Hãy đặt pointcut theo **contract của thao tác**, thay vì quét một tên method quá rộng rồi phải thêm vô số ngoại lệ. Với `@annotation`, ý nghĩa và retention của annotation cũng phải được kiểm chứng; không giả định mọi annotation đều xuất hiện ở runtime theo cách giống nhau.

### 5.2. `execution` khác `call` trong tự gọi

Giả sử:

~~~java
class Processor {
    void first() {
        second();
    }
    void second() {
        // nghiệp vụ
    }
}
~~~

Đoạn Java chỉ minh họa. Nếu `execution(void Processor.second())` đã được weave vào method `second`, advice chạy khi `second` thực thi, kể cả được gọi bằng `this.second()` trong `first`. Nếu dùng `call(void Processor.second())` thì vị trí gọi trong `first` phải được weave. Một điểm gọi trong class không được weave có thể không chịu advice này.

Nhờ hiểu hai join point khác nhau, ta tránh những kết luận sai kiểu “weaving bắt mọi lời gọi ở bất kỳ nơi nào” hoặc “self-call luôn bypass như proxy”.

## 6. Ví dụ hoàn chỉnh Java 17+: thêm advice mà không sửa business code

Ví dụ sử dụng **compile-time weaving** để thấy cùng mã Java cho kết quả khác khi có file aspect. Ba file trong cùng một thư mục và đều thuộc default package để các lệnh biên dịch ngắn, độc lập.

### 6.1. Mã nghiệp vụ: `Greeter.java`

~~~java
public class Greeter {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("empty name");
        }
        System.out.println("domain: greet");
        return "Hello " + name;
    }
}
~~~

Method chỉ quan tâm đến hợp đồng: từ chối tên rỗng và trả lời chào hợp lệ. Nó **không gọi aspect** và không chứa tracing.

### 6.2. Chương trình gọi: `Demo.java`

~~~java
public class Demo {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println("main: " + greeter.greet("An"));

        try {
            greeter.greet("   ");
        } catch (IllegalArgumentException e) {
            System.out.println("main: rejected " + e.getMessage());
        }
    }
}
~~~

### 6.3. Aspect: `CallTrace.aj`

~~~java
public aspect CallTrace {
    pointcut greeting(String name):
        execution(String Greeter.greet(String))
        && args(name);

    String around(String name): greeting(name) {
        System.out.println("trace: before");
        try {
            String result = proceed(name);
            System.out.println("trace: after");
            return result;
        } catch (RuntimeException failure) {
            System.out.println("trace: error");
            throw failure;
        }
    }
}
~~~

Giải thích:

- `pointcut greeting(String name)` đặt tên tập join point và **bind** đối số `name` nhờ `args(name)`.
- `execution(String Greeter.greet(String))` chọn method execution của `greet`, với return type `String` và một đối số `String`.
- `around` nhận giá trị đã bind, chạy trước và sau logic gốc; `proceed(name)` tiếp tục tới join point/chuỗi advice bên trong với đối số đó.
- Khi method ném `IllegalArgumentException`, `catch (RuntimeException)` log rồi **ném lại cùng exception**, không chuyển lỗi thành giá trị mặc định.
- Nếu advice thêm một lời gọi `proceed()` thứ hai hoặc tự sửa `name`, nó sẽ thay semantics nghiệp vụ. Đoạn ví dụ cố ý gọi đúng một lần.
- Chỉ có advice được thêm qua weaving; `Greeter.java` và `Demo.java` không phụ thuộc trực tiếp vào tên `CallTrace`.

### 6.4. Chạy Java thường trước khi weave

Đặt file `Greeter.java` và `Demo.java` vào thư mục hiện tại, chạy:

~~~bash
javac --release 17 Greeter.java Demo.java
java Demo
~~~

**Stdout không có aspect:**

~~~text
domain: greet
main: Hello An
main: rejected empty name
~~~

Đây là phép kiểm chứng rằng code nghiệp vụ đứng độc lập, và chạy `java` với class chưa weave không tự kích hoạt file `.aj` chỉ nằm trên đĩa.

### 6.5. Biên dịch/weave với `ajc`

Chuẩn bị hai artifact cùng phiên bản AspectJ:

- `aspectjtools.jar`: chứa compiler/weaver `org.aspectj.tools.ajc.Main`.
- `aspectjrt.jar`: thư viện runtime mà class đã weave có thể cần tại khi chạy.

Dùng một bản phát hành AspectJ hỗ trợ Java 17 và bộ JDK đang sử dụng. Ví dụ dưới đặt hai JAR trong thư mục `lib` với tên đã rút gọn thành `aspectjtools.jar` và `aspectjrt.jar`. Tạo thư mục `woven` và chạy trên **Windows PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force woven | Out-Null
java -cp "lib\aspectjtools.jar" org.aspectj.tools.ajc.Main -17 -classpath "lib\aspectjrt.jar" -d woven Greeter.java Demo.java CallTrace.aj
java -cp "woven;lib\aspectjrt.jar" Demo
~~~

Trên macOS/Linux, classpath lúc chạy dùng dấu `:`:

~~~bash
mkdir -p woven
java -cp "lib/aspectjtools.jar" org.aspectj.tools.ajc.Main -17 -classpath "lib/aspectjrt.jar" -d woven Greeter.java Demo.java CallTrace.aj
java -cp "woven:lib/aspectjrt.jar" Demo
~~~

**Stdout khi đã weave:**

~~~text
trace: before
domain: greet
trace: after
main: Hello An
trace: before
trace: error
main: rejected empty name
~~~

Không có lệnh gọi `CallTrace` trong `Demo`. Sự khác biệt đầu ra đến từ bytecode method `Greeter.greet` đã được `ajc` weave: mỗi lần thực thi method khớp pointcut kích hoạt advice. Lời gọi thành công đi qua `before -> proceed -> after`; lời gọi không hợp lệ đi qua `before -> proceed -> exception -> error` rồi caller bắt exception gốc.

**Cần lưu ý đường chạy:** output `woven` phải được đặt trước các thư mục/JAR chứa phiên bản `Greeter.class` chưa weave trên classpath. Nếu JVM load class gốc từ thư mục hiện tại trước, bạn có thể tưởng weaving “không hoạt động” dù bước compile đã thành công. Các ví dụ sử dụng classpath tường minh chỉ gồm `woven` và runtime.

## 7. Phân tích chính xác điều diễn ra trong ví dụ

### 7.1. Join point không phải là object proxy

`new Greeter()` tạo đối tượng Java thông thường. Aspect advice không được đăng ký bằng `new Wrapper(greeter)` và `Demo` không gọi API reflection/proxy nào. Weaver đưa lời khuyên vào bytecode tương ứng với method execution.

Điều này giải thích vì sao các lời gọi hợp lệ tới method đã weave có thể được quan sát bất kể caller trực tiếp tạo object hay gọi nội bộ. Đừng suy ra mọi bytecode của mọi dependency đều được weave: phạm vi lớp đầu vào cho build hay lớp được load qua weaving loader vẫn quyết định.

### 7.2. Đường thành công và lỗi

- Khi `greet("An")` chạy, advice in `trace: before`.
- `proceed(name)` cho logic gốc chạy: in `domain: greet` và trả `Hello An`.
- Advice in `trace: after` rồi trả lại chính giá trị đó.
- `Demo` in kết quả.
- Với `greet("   ")`, advice in `trace: before`, logic gốc ném `IllegalArgumentException` trước khi in dòng domain.
- Advice in `trace: error` rồi ném lại lỗi; `Demo` bắt và in `main: rejected empty name`.

Đối với advice production, bảo đảm lỗi từ emitter/tracing không vô tình thay đổi kết quả nghiệp vụ nếu telemetry chỉ có trách nhiệm quan sát. Ví dụ cố ý dùng `System.out.println` để minh họa; logging thật cần xử lý overload và data privacy.

### 7.3. Vì sao `proceed` cần hợp đồng?

Advice `around` có thể:

- Không gọi `proceed`, ví dụ do cache hit, từ chối quyền hoặc circuit breaker.
- Gọi một lần (quan sát đơn giản).
- Gọi nhiều lần (retry nếu operation có thể retry và có idempotency).
- Thay đối số hoặc kết quả (chỉ khi hợp đồng cho phép).

Những khả năng này là **quyền năng**, không phải khuyến nghị mặc định. Việc dùng AspectJ không cấp quyền tự ý nuốt exception, chặn validation nghiệp vụ, thay đổi số tiền, đảo ngược side effect hoặc tạo success giả.

## 8. Annotation-style aspect và code-style aspect

AspectJ hỗ trợ **code style** qua file `.aj` (như `CallTrace.aj`) và **annotation style** qua class Java có annotation như `@Aspect`, `@Pointcut`, `@Before` và `@Around`. Hai cách biểu đạt có thể tham gia weaving nếu được cấu hình đúng.

Ví dụ annotation-style ngắn:

~~~java
// Minh họa API AspectJ: cần dependency aspectjrt và cấu hình weaving.
// Đây KHÔNG là file độc lập có thể chạy bằng javac một mình.
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class BasicTrace {
    @Before("execution(* Greeter.greet(..))")
    public void beforeGreeting() {
        System.out.println("trace: entering greet");
    }
}
~~~

**Viết class có `@Aspect` không tự làm weaving xảy ra khi chỉ chạy `javac` rồi `java`.** Vẫn cần compiler/weaver hoặc LTW phù hợp. Đây là khác biệt giữa **mô tả advice** và **kích hoạt interception**.

Code-style `.aj` cung cấp cú pháp ngôn ngữ AspectJ trực tiếp, và có thể biểu đạt thêm nhiều cấu trúc như inter-type declaration. Annotation style hữu ích khi muốn khai báo aspect bằng Java syntax thông thường, nhưng các khả năng cú pháp không đồng nhất hoàn toàn; cần kiểm tra tính năng cụ thể trong tài liệu công cụ.

## 9. Post-compile weaving: khi mã Java đã biên dịch

Nếu muốn giữ bước biên dịch Java bằng `javac`, có thể compile app trước rồi dùng `ajc` weave bytecode có sẵn.

Giả định `Greeter.java`, `Demo.java` và `CallTrace.aj` như ví dụ, đã có `lib/aspectjtools.jar` và `lib/aspectjrt.jar` cùng phiên bản. Lệnh mang tính mẫu trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force plain, woven | Out-Null
javac --release 17 -d plain Greeter.java Demo.java
java -cp "lib\aspectjtools.jar" org.aspectj.tools.ajc.Main -17 -classpath "lib\aspectjrt.jar" -inpath plain -d woven CallTrace.aj
java -cp "woven;lib\aspectjrt.jar" Demo
~~~

`-inpath plain` là nơi `ajc` nhận **bytecode đầu vào** để weave. `CallTrace.aj` vẫn là nguồn AspectJ cần compile trong bước này. Trong dự án thực, phải phân biệt source path, classpath, aspectpath, inpath và output để không vô ý weave trùng hoặc bỏ sót class.

Để chắc chắn kết quả, so sánh hành vi với bản `plain`, bật báo cáo join point khi compile, và chỉ đóng gói artifact `woven` khi muốn chạy mã đã weave. Khi vừa có class nguyên bản vừa có bản woven trên classpath, thứ tự class loading có thể làm test sai.

## 10. Load-time weaving: cấu hình và giới hạn

Khi cần weave lúc class được định nghĩa, có thể dùng `aspectjweaver.jar` làm Java agent. Đây là **một lựa chọn khác với CTW**, không cần kết hợp cả hai lên cùng class chỉ để bài demo hoạt động.

Ví dụ `META-INF/aop.xml` tối giản:

~~~xml
<aspectj>
  <aspects>
    <aspect name="CallTrace"/>
  </aspects>
  <weaver options="-showWeaveInfo">
    <include within="Greeter"/>
  </weaver>
</aspectj>
~~~

Đây là cấu hình minh họa cho bản aspect đã được **biên dịch và đặt trên classpath**. File `META-INF/aop.xml` cũng cần xuất hiện đúng trên classpath để LTW đọc được. `<include within="Greeter"/>` nhằm giới hạn class được weave; trong dự án có package, nên chọn pattern package/class thích hợp thay vì để phạm vi mặc định quá rộng.

Một lệnh khởi động có hình thức:

~~~powershell
java -javaagent:lib\aspectjweaver.jar -cp "classes;lib\aspectjrt.jar;aspects" Demo
~~~

Trong đó `classes` chứa class gốc, `aspects` chứa aspect đã biên dịch và `META-INF/aop.xml`, và `lib` chứa các JAR AspectJ tương thích. Chỉ lệnh trên không tự tạo những thư mục đó: phải build và đóng gói đúng các thành phần trước. **Không dùng output CTW đã weave lại trong ví dụ LTW này** nếu mục tiêu là kiểm chứng thuần LTW.

Các vấn đề LTW cần biết:

1. JVM cần được khởi động với agent khi thích hợp, trước khi những class cần weave được định nghĩa.
2. Phạm vi type được weave chịu ảnh hưởng class loader delegation và bộ lọc include/exclude.
3. Aspect phải hiện diện với loader/weaver ở giai đoạn cần thiết, và version artifact phải tương thích.
4. Một số môi trường ứng dụng dùng nhiều class loader, module, instrumentation hoặc các bytecode transformer khác; thứ tự và tính tương thích cần được kiểm chứng riêng.
5. Bật LTW trên toàn bộ dependency mà không giới hạn có thể làm tăng chi phí startup và chọn cả join point ngoài ý định.
6. “Agent chạy được” chưa chứng minh mọi pointcut đã match; phải kiểm tra weave info và test hành vi thực tế.

Khi triển khai, nên kiểm tra tài liệu phát triển của AspectJ tương ứng với phiên bản sử dụng, nhất là yêu cầu của JDK, class loader và mô hình đóng gói. **Phần demo CTW ở mục 6 là ví dụ độc lập chính**; cấu hình LTW trong mục này mô tả cơ chế và cần điều chỉnh cho hệ thống cụ thể.

## 11. Đi sâu hơn: binding, context và các loại advice

### 11.1. Bind đối số và lấy metadata

Trong ví dụ, `args(name)` liên kết đối số method với tham số advice để sử dụng trong `proceed(name)`. AspectJ cũng cung cấp metadata của join point, chẳng hạn `thisJoinPointStaticPart`, hữu ích để lấy chữ ký tĩnh cho log/metric.

Minh họa:

~~~java
// Đoạn trong advice code-style, không phải chương trình độc lập:
String signature = thisJoinPointStaticPart.getSignature().toShortString();
~~~

Không tự động đưa `name`, `args` hoặc `toString()` của toàn object vào telemetry. Advice có thể nằm ở vị trí xem dữ liệu nhạy cảm, do đó cần allowlist, giới hạn dung lượng và context tin cậy. Đọc chữ ký tĩnh thường đủ để tạo nhãn operation; full stack trace và reflection sâu có thể đắt đỏ.

### 11.2. Advice trước/sau và trường hợp lỗi

| Advice | Thời điểm | Gợi ý |
| --- | --- | --- |
| `before` | Trước join point | Kiểm tra điều kiện, đánh dấu bắt đầu |
| `after returning` | Chỉ khi trả về bình thường | Ghi nhận kết quả thành công theo contract |
| `after throwing` | Khi kết thúc bằng exception phù hợp | Ghi số lỗi, không tự nuốt lỗi |
| `after` | Kết thúc bất kể đường bình thường/lỗi | Cleanup/tổng kết |
| `around` | Bao trùm join point | Đo thời gian, kiểm soát `proceed`/retry/fallback khi được phép |

Nếu method trả một `Future` hoặc `CompletionStage` ngay lập tức, `after returning` ở method execution chỉ quan sát được **handle**, chưa chắc quan sát được kết quả cuối của phép tính. Đo operation bất đồng bộ cần instrumentation ở ranh giới completion/callback đúng, với logic kết thúc một lần và giữ nguyên semantics hủy/lỗi.

### 11.3. Scope/lifecycle của aspect instance

Trong AOP nói chung, có thể có chính sách aspect instance dùng chung, theo đối tượng hoặc theo control flow. AspectJ có các cơ chế như `perthis`, `pertarget`, `percflow`, `pertypewithin` ở những ngữ cảnh phù hợp. Đừng giả định mỗi method invocation có một aspect object mới.

State dạng field dùng chung trong singleton aspect phải thread-safe; principal, start time và request-local context không nên giữ trong field dùng chung nếu có nhiều luồng. `ThreadLocal` cũng không tự truyền sang executor khác và phải được khôi phục/xóa đúng lúc để tránh rò dữ liệu giữa request.

## 12. Inter-type declaration: một khả năng nâng cao của weaving

Ngoài advice, AspectJ có **inter-type declarations (ITD)** cho phép giới thiệu member/quan hệ kiểu ở những class được chọn. Minh họa code-style:

~~~java
// Giả sử class Account tồn tại.
// Đoạn .aj minh họa, cần class Account và ajc để biên dịch.
public aspect AccountTag {
    public String Account.describe() {
        return "account";
    }
}
~~~

Sau khi aspect được kết hợp bằng compiler/weaver theo điều kiện phù hợp, class được giới thiệu method có thể có hành vi mà mã nguồn `Account` ban đầu không khai báo. Đây là ví dụ rất rõ ràng rằng weaving có thể **tác động đến cấu trúc type**, chứ không chỉ chặn method call.

Tuy vậy, ITD làm tăng sự phụ thuộc ngầm: người đọc class gốc có thể không thấy member được thêm, IDE/compile pipeline phải hiểu nguồn aspect, và binary compatibility hoặc xung đột tên member phải được kiểm thử. Nếu code Java cần gọi `account.describe()` tại compile time, compiler phải nhìn thấy giới thiệu member đó ở bước phù hợp; chỉ để LTW chạy quá muộn không khiến `javac` thông thường chấp nhận member chưa tồn tại.

Không dùng ITD chỉ để “tiện thêm helper”; cân nhắc liệu một interface, adapter hay method trong chính domain model có diễn đạt hợp đồng rõ ràng hơn không.

## 13. Thứ tự nhiều aspect: composition và precedence

Một join point có thể match nhiều aspect, ví dụ tracing, metric và kiểm soát quyền. Thứ tự advice ảnh hưởng mạnh đến semantics:

~~~text
Metrics -> Authorization -> Domain
         deny: metrics thấy denial

Authorization -> Metrics -> Domain
         deny: metrics bên trong không chạy
~~~

Nếu cache được đặt **ngoài** aspect kiểm tra quyền và trả về khi cache hit, lời gọi có thể bypass quyền. Nếu retry nằm ngoài transaction, mỗi attempt có thể có transaction riêng; nếu retry nằm bên trong transaction, nhiều attempt có thể dùng chung trạng thái giao dịch không phù hợp.

AspectJ có cách mô tả precedence giữa các aspect. Ví dụ cú pháp:

~~~java
// Ví dụ khai báo trong một aspect .aj.
// Các aspect trong ví dụ phải tồn tại; đoạn này không độc lập.
declare precedence: SecurityAspect, MonitoringAspect, *;
~~~

Khai báo này cho ý tưởng ưu tiên `SecurityAspect` trước `MonitoringAspect` và các aspect còn lại; **thứ tự quanh một join point** phải được kiểm tra theo before/after/around của từng advice. Với aspect có ưu tiên cao hơn, phần advice trên đường vào có thể chạy sớm hơn, còn hành vi trên đường ra có thể diễn ra theo thứ tự đảo. Không suy luận bằng cách chỉ nhìn tên aspect; cần integration test thể hiện chuỗi thực thi.

Nếu nhiều pointcut chồng lấn bất ngờ, một operation có thể bị ghi log hai lần hoặc bị retry nhiều tầng. Cần định nghĩa chính sách order công khai, tránh rely vào thứ tự load tình cờ và thiết kế pointcut đủ hẹp.

## 14. Hiệu năng và độ tin cậy của weaving

Weaving thêm bytecode vào những vị trí được chọn. Do đó overhead phụ thuộc **số join point thực sự bị chặn**, nội dung advice, biến động class loading và phần việc telemetry; không thể khẳng định weaving tự động có overhead bằng 0.

Các bẫy thường gặp:

- **Pointcut quá rộng:** `execution(* *(..))` không giới hạn có thể match các method không liên quan, thậm chí telemetry code tạo recursion. Giới hạn package, type, annotation hoặc method contract.
- **Advice quá nặng:** serialize toàn bộ argument, log stack trace mọi lời gọi, truy vấn network đồng bộ ở hot path.
- **Nhiều aspect chồng lấn:** cùng một lời gọi phát nhiều event, tạo hai transaction hoặc retry không mong muốn.
- **State không an toàn đồng thời:** aspect singleton lưu `startNanos`/principal dưới field mutable chung.
- **Giấu exception:** lời gọi nguyên bản ném lỗi nhưng advice trả fallback giả thành công, làm thay đổi hợp đồng nghiệp vụ.
- **Sai classpath:** chạy bản class chưa weave hoặc đưa hai bản cùng tên lên classpath; kết quả khác build đã kiểm chứng.
- **Sai loader/phạm vi LTW:** class đã load trước, nằm trong parent loader hoặc không match bộ lọc.
- **Weave lại không kiểm soát:** pipeline dùng class đã weave làm input, gây cấu trúc không mong muốn hoặc sinh thông báo xung đột.
- **Không theo dõi lỗi weaving:** deployment vẫn chạy nhưng quan sát/bảo vệ phụ thuộc advice không còn hoạt động.

Một Aspect quan sát nên có cơ chế giảm log (sampling/quota), đo overhead, loại trừ chính package hạ tầng của nó khi cần và không thu thập dữ liệu nhạy cảm bằng reflection mặc định.

## 15. Cách xác nhận aspect đã được weave

Không nên kết luận thành công chỉ vì chạy `ajc` không báo lỗi. Một quy trình kiểm chứng tốt:

1. **Đọc pointcut được chọn:** chữ ký có khớp kiểu trả về, visibility, static/instance, package, số tham số không?
2. **Bật thông tin weaver:** dùng `-showWeaveInfo` khi build hoặc `-showWeaveInfo` trong tùy chọn weaver khi LTW.
3. **Chạy đối chứng trước và sau weaving:** mã nghiệp vụ giống nhau, output có/không có advice đúng chỗ.
4. **Test các đường đi:** success, exception, self-call, overload, method từ subclass, async completion và cache hit nếu policy liên quan.
5. **Kiểm tra runtime classpath:** đúng class đã weave, đúng version runtime và đúng class loader.
6. **Kiểm tra giới hạn:** method đích không được weave, caller chưa weave với `call`, class được load trước agent hoặc API nằm ngoài pattern.
7. **Tập trung observable contract:** giá trị trả về, loại lỗi, số side effect, số lần proceed và trạng thái giao dịch phải đúng.
8. **Theo dõi build/deployment:** thông tin weaving nên đủ để phát hiện khi nâng JDK, đổi package hoặc nâng dependency làm pointcut không còn match.

Một số tùy chọn có thể dùng trong môi trường phù hợp:

~~~bash
# Ví dụ thêm tùy chọn vào lệnh ajc ở mục 6:
# -showWeaveInfo: hiện các join point được weave.
# -Xlint: thêm cảnh báo cấu hình/weaving liên quan.
~~~

Đây là chú giải tùy chọn, không phải lệnh chạy độc lập. Kiểm tra chính xác syntax/version từ help `ajc -help` và tài liệu của bản AspectJ đang dùng.

### 15.1. Bộ kiểm thử định hướng hành vi

| Tình huống | Cần chứng minh |
| --- | --- |
| Method hợp lệ với CTW | Advice chạy đúng một lần, kết quả không đổi |
| Method ném exception | Advice ghi lỗi, caller nhận exception gốc |
| Method không thuộc pointcut | Không bị chặn |
| Method overload | Pattern chọn đúng overload cần quan sát |
| Self-call | `execution` của method được weave vẫn chạy |
| Caller chưa weave + `call` | Không suy luận sai rằng call site đã được chặn |
| Hai advice cùng join point | Thứ tự/precedence đúng hợp đồng |
| LTW thiếu aspect/aop.xml | Test phát hiện khi lớp không được weave |
| Classloader khác | Phạm vi weaving được xác nhận theo topology loader |
| Async trả handle | Không báo “business success” trước completion thật |
| Retry hoặc cache hit | Không phát side effect trùng hoặc bypass policy |
| Tải cao | Overhead, memory, telemetry loss được đo và giới hạn |

## 16. Lỗi tư duy phổ biến

**“Chỉ cần thêm file aspect là runtime tự chạy.”** Sai. Phải có compilation/weaving phù hợp; annotation hay file `.aj` chỉ biểu diễn chính sách, không thay thế bước tích hợp.

**“Weaving là một proxy trong suốt.”** Sai về cơ chế. Weaving tác động bytecode ở join point, trong khi proxy thường chỉ intercept lời gọi đi qua đối tượng đại diện.

**“`call` và `execution` như nhau.”** Sai. Call join point nằm ở vị trí gọi; execution ở thân method. Điều này ảnh hưởng cần weave class nào và phát hiện self-invocation.

**“LTW thay mọi class đang chạy.”** Sai. LTW làm việc khi class được định nghĩa trong phạm vi class loader/weaver; class đã load trước có thể không được can thiệp.

**“Advice là kỹ thuật nên được phép đổi kết quả nghiệp vụ.”** Sai. Around advice có thể thay hành vi nhưng chỉ nên làm vậy nếu contract công khai cho phép. Ngay cả log cũng không được làm lộ thông tin hoặc gây lỗi mới che mất lỗi gốc.

**“Pointcut rộng giúp không bỏ sót gì.”** Không hẳn. Pointcut quá rộng dễ gây recursion, overhead, chặn sai domain semantics và khó bảo trì. Bao phủ đúng là một yêu cầu có test, không phải vấn đề số lượng join point tối đa.

**“Sau khi method trả về là operation đã kết thúc.”** Với API bất đồng bộ, chỉ có handle được trả; hoàn tất vật lý và hoàn tất logic có thể đến về sau.

**“Compiler báo thành công nghĩa là kết quả chắc đã weave đúng.”** Không đủ. Một pattern không khớp hoặc classpath sai có thể làm chương trình chạy thiếu advice; cần báo cáo weaver và kiểm thử đối chứng.

## 17. Checklist kiến trúc AOP có weaving

Trước khi đưa một aspect vào dự án, hãy ghi lại:

1. **Chính sách:** concern nào được mô-đun hóa? Hợp đồng của advice có được phép block, retry, mutate hay fallback không?
2. **Join point:** `execution` hay `call`, constructor/field hay loại khác? Vì sao chọn loại ấy?
3. **Pointcut scope:** chọn package, class, method, annotation và exclusion nào? Có method mới hoặc overload bị match sai không?
4. **Weaving stage:** CTW, binary weaving hay LTW? Đầu vào/đầu ra và loader nào chịu trách nhiệm?
5. **Dependencies:** phiên bản compiler/weaver/runtime có tương thích JDK và nhau không?
6. **Advice contract:** `proceed` chạy bao nhiêu lần; exception, return, side effect và async completion được bảo toàn như thế nào?
7. **State/thread-safety:** aspect instance có chia sẻ không, per-invocation state đặt ở đâu, context qua thread được phục hồi ra sao?
8. **Composition:** nhiều aspect có thứ tự nào, có cache-hit bypass authorization hay double retry không?
9. **Observability và bảo mật:** log/metric nào được phép, mức overhead và dữ liệu nhạy cảm được kiểm soát ra sao?
10. **Validation:** có so sánh trước/sau weaving, showWeaveInfo, test self-call/exception/async và kiểm tra startup/classpath chưa?

### Tài liệu tham khảo

- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/index.html) — thuật ngữ AOP, pointcut, advice, join point và các đặc trưng ngôn ngữ.
- [AspectJ Development Guide: ajc](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html) — cách biên dịch, inpath, cảnh báo và tùy chọn weaver.
- [AspectJ Development Guide: Load-Time Weaving](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html) — CTW, binary weaving, LTW, agent, class loader và cấu hình.

**Ý chính cần giữ:** AspectJ minh họa rất rõ AOP có weaving vì khái niệm “chọn join point rồi kết hợp advice” được thể hiện thành bytecode thực thi, không chỉ là cách gói một object. Nắm được **các loại join point, thời điểm weaving, phạm vi class được weave, thứ tự advice và hợp đồng nghiệp vụ** mới là nền tảng để dùng AOP an toàn, hiệu quả và có thể kiểm chứng.
