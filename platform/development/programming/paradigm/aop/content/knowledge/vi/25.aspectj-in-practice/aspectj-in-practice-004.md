# Biểu thức this, target, args và pointcut theo annotation trong AspectJ

## 1. Mục tiêu: chọn đúng join point và lấy đúng ngữ cảnh

Trong Aspect-Oriented Programming (AOP), **pointcut** xác định những join point nào sẽ được aspect can thiệp. Trong AspectJ, ngoài việc chọn loại join point bằng execution() hoặc call(), ta thường muốn ràng buộc **ai đang thực thi**, **đối tượng nào được gọi**, **tham số nào được truyền** và **annotation nào đánh dấu hành vi**.

Bốn câu hỏi liên quan nhưng không đồng nhất:

- **this(...):** tại join point, đối tượng đang thực thi là đối tượng nào?
- **target(...):** đối tượng nhận thao tác hoặc đối tượng đích của join point là đối tượng nào?
- **args(...):** các đối số được truyền vào join point có giá trị/kiểu gì?
- **@annotation(...), @this(...), @target(...), @args(...):** thông tin annotation nằm ở thành phần nào và có thể được dùng để match/bind ra sao?

Chẳng hạn khi một đối tượng OrderScreen gọi service.submit("A-01"), ở **method call join point**, this có thể là OrderScreen (bên gọi) và target là đối tượng service (bên nhận). Ở **method execution join point** của service.submit(), this và target thường cùng là đối tượng service. Việc nhầm hai ranh giới này dẫn đến pointcut không khớp hoặc ghi log sai đối tượng.

Các biểu thức ở đây là **cú pháp ngôn ngữ pointcut của AspectJ**, được minh họa bằng code-style aspect. Nội dung áp dụng cho AOP nói chung và ngữ nghĩa AspectJ, không phụ thuộc cơ chế interception của bất kỳ framework ứng dụng nào.

## 2. Ôn lại join point, pointcut và advice

- **Join point:** một vị trí trong luồng chương trình mà AspectJ nhận diện, chẳng hạn method call, method execution, truy cập field hoặc xử lý ngoại lệ.
- **Pointcut designator (PCD):** thành phần của biểu thức chọn join point, ví dụ call(...), execution(...), this(...), target(...), args(...).
- **Pointcut:** biểu thức ghép các PCD và phép logic && (AND), || (OR), ! (NOT).
- **Advice:** mã chạy trước, sau hoặc quanh join point mà pointcut chọn.
- **Weaving:** ghép advice vào mã tương ứng; AspectJ có các cách như compile-time, post-compile hoặc load-time weaving.

Ví dụ:

~~~aspectj
pointcut pricedCall():
    call(* PriceService.calculate(..))
    && within(shop.ui..*);
~~~

Đây là **mảnh mã minh họa**, giả định đã có kiểu PriceService và package shop.ui; chưa phải chương trình độc lập. call(...) chọn lời gọi khớp chữ ký, còn within(...) giới hạn **vị trí mã chứa lời gọi**. Việc kết hợp kinded PCD (call/execution), scoping PCD (within/withincode) và contextual PCD (this/target/args/annotation) thường làm pointcut dễ hiểu, dễ kiểm thử và giảm phạm vi cần xem xét khi weaving.

### call(...) khác execution(...)

| Đặc điểm | call(MethodPattern) | execution(MethodPattern) |
| --- | --- | --- |
| Điểm được chọn | Vị trí lệnh gọi phương thức | Khi thân phương thức bắt đầu thực thi |
| Mã liên quan | Bên gọi | Bên nhận/triển khai |
| this() | Đối tượng thực thi mã ở vị trí gọi; không có ở ngữ cảnh static | Đối tượng đang thực thi thân phương thức instance |
| target() | Đối tượng đích của lời gọi instance | Đối tượng đang thực thi phương thức instance |
| args() | Các đối số tại lời gọi | Các đối số tại lúc thực thi |
| @annotation() | Annotation trên **subject** của call join point | Annotation trên phương thức thực thi được chọn |

Tại call join point có thể có this != target. Tại execution join point của instance method, this và target là cùng một object. Với những join point thuộc **ngữ cảnh static** hoặc lời gọi static không có receiver instance, các PCD yêu cầu đối tượng this/target có thể không match; không dùng chúng như một điều kiện bao phủ mọi lời gọi static.

Cần phân biệt this(...) của AspectJ với this trong thân advice: trong code-style aspect, this là thể hiện aspect đang thực thi advice, còn this(...) PCD ràng buộc đối tượng của **join point đang được quan sát**.

## 3. this(Type) và this(variable)

**this(Type)** chọn join point mà đối tượng đang thực thi có runtime type phù hợp với Type. **this(variable)** đồng thời chọn theo kiểu của biến formal và **bind đối tượng hiện tại** cho advice sử dụng.

~~~aspectj
pointcut uiCalling():
    call(* *(..))
    && within(shop.ui..*)
    && this(shop.ui.OrderScreen);
~~~

Đoạn này chọn các lời gọi bên trong mã thuộc shop.ui... khi đối tượng hiện hành là OrderScreen; ví dụ chỉ có tác dụng nếu kiểu và package tương ứng tồn tại.

Binding trong một pointcut có tham số:

~~~aspectj
pointcut fromScreen(shop.ui.OrderScreen screen):
    call(* *(..))
    && this(screen);
~~~

Lúc advice nhận biến screen, đó là đối tượng **bên gọi tại call join point**. Nó không tự đồng nghĩa với receiver của phương thức đang được gọi.

Ví dụ dùng execution:

~~~aspectj
pointcut executingOnService(ServiceImpl current):
    execution(* ServiceImpl.*(..))
    && this(current);
~~~

Đây là đoạn cú pháp minh họa, cần đặt trong aspect và có lớp ServiceImpl. Với instance method của ServiceImpl, current chính là đối tượng đang chạy phương thức. Không phải mọi join point đều có this; nếu đặt this(...) trên call từ static main(), kết quả là **không match**, dù lời gọi có receiver là một object.

## 4. target(Type) và target(variable)

**target(Type)** chọn join point theo kiểu runtime của đối tượng đích; **target(variable)** đưa đối tượng đích vào lời advice.

~~~aspectj
pointcut invokingService(ServiceImpl service):
    call(* Service.send(..))
    && target(service);
~~~

Nếu biến bên gọi được khai báo kiểu Service nhưng object thực là ServiceImpl, target(service) vẫn có thể match và bind đối tượng ServiceImpl. Vì target() là một PCD dựa trên runtime type, đừng nhầm nó với pattern chữ ký trong call(...).

Trong ví dụ sau:

~~~text
class Ui {
    void render() {
        Service service = new ServiceImpl();
        service.send("hello");
    }
}
~~~

Tại **call** của service.send trong Ui.render:
- this là một thể hiện Ui;
- target là thể hiện ServiceImpl;
- args là một đối số String có giá trị "hello".

Tại **execution** của ServiceImpl.send:
- this và target cùng là ServiceImpl;
- args vẫn là đối số của lượt thực thi.

**Lưu ý:** câu trong khối text chỉ là ví dụ mô hình; lớp Service và ServiceImpl sẽ được định nghĩa trong chương trình hoàn chỉnh bên dưới.

### Khi nào this và target không bằng nhau?

Chúng thường khác ở lời gọi instance method phát ra từ **một đối tượng khác**. Đối với lời gọi từ một phương thức trên cùng đối tượng, this và target có thể trùng. Ở execution join point của instance method thì chúng trùng theo ngữ nghĩa join point. Sự khác nhau xuất phát từ **loại join point**, không phải từ “đối tượng proxy” trong một framework cụ thể.

## 5. args(TypePattern...) và args(variable...)

**args(...)** kiểm tra kiểu/giá trị đối số tại join point. Có hai cách dùng chính:

1. **Lọc theo kiểu:** args(String), args(int, ..), args(String, *, long), v.v.
2. **Bind giá trị:** args(message), args(amount, ..) khi message/amount được khai báo với kiểu tương ứng trong pointcut hoặc advice.

~~~aspectj
pointcut oneString(String text):
    execution(* Service.send(String))
    && args(text);
~~~

Ở đây text nhận đúng đối số String khi advice chạy. Bản thân args(text) **không** có nghĩa chuỗi phải bằng chữ "text"; đó là tên tham số formal. Muốn kiểm tra giá trị cụ thể, thực hiện trong advice hoặc dùng điều kiện động được thiết kế phù hợp.

Các dấu đặc biệt:

| Cú pháp | Ý nghĩa |
| --- | --- |
| args(String) | Một đối số có kiểu phù hợp String |
| args(int, ..) | Đối số đầu phù hợp int; có thể có thêm đối số phía sau |
| args(.., String) | Đối số cuối phù hợp String; phía trước có thể có nhiều đối số |
| args(*, String) | Chính xác hai đối số; đối số đầu là bất kỳ, đối số sau phù hợp String |
| args(..) | Không ràng buộc danh sách đối số |

**args(...) không giống tham số khai báo trong execution(...).** execution(void Service.handle(Object)) lọc theo chữ ký khai báo, còn args(String) có thể lọc join point mà đối số thực sự là String ở runtime dù tham số khai báo là Object. Với null, AspectJ có quy tắc matching dựa trên kiểu tĩnh vì không có runtime class cho giá trị null; tránh giả định rằng null luôn match hoặc không match mọi type pattern.

### Binding và vị trí tham số

~~~aspectj
pointcut requestAmount(String orderId, int amount):
    execution(* OrderService.reserve(String, int))
    && args(orderId, amount);
~~~

Đây là đoạn mã minh họa cần các kiểu tương ứng và một aspect bao ngoài. Thứ tự binding phải đúng. Nếu phương thức có nhiều đối số, không nên phụ thuộc vào việc đọc tùy ý Object[] rồi ép kiểu dựa trên chỉ số không được kiểm soát.

Khi một pointcut dùng || để ghép hai nhánh có binding, các biến cần được ràng buộc hợp lệ trong mọi nhánh có thể match; biểu thức bind mơ hồ có thể bị compiler từ chối.

## 6. Các pointcut theo annotation: annotation nằm ở đâu?

Trong AspectJ, họ PCD bắt đầu bằng @ dùng metadata đã khai báo trên method, type hoặc runtime class của đối tượng/đối số.

| PCD | Đối tượng được kiểm tra |
| --- | --- |
| @annotation(Trace) | Annotation trên **subject** của join point được chọn, ví dụ phương thức tương ứng với execution(...) |
| @within(Trace) | Mã chứa join point được định nghĩa bên trong kiểu có annotation Trace |
| @withincode(Trace) | Mã chứa join point nằm trong phương thức/constructor được đánh dấu Trace |
| @this(Trace) | Runtime type của object đang được ràng buộc vào this có annotation Trace |
| @target(Trace) | Runtime type của target object có annotation Trace |
| @args(Trace, ..) | Runtime type của đối số đầu có annotation Trace; có thể có thêm đối số |

Tên Trace chỉ là annotation minh họa; mỗi PCD cần một annotation type đúng ngữ cảnh, ví dụ annotation chỉ dùng trên METHOD sẽ không phù hợp để đánh dấu TYPE.

**@annotation** không có nghĩa “bất cứ phương thức nào được gọi bên trong một phương thức có annotation”. Trường hợp đó liên quan tới @withincode. **@within** cũng không phải một cách thay thế cho @target: một cái xét nơi mã được định nghĩa, một cái xét annotation trên runtime target type. Khi kết hợp call hoặc execution, khác biệt vị trí chủ thể của join point rất quan trọng.

### Cần @Retention nào?

Một annotation Java có thể dùng @Retention(SOURCE), @Retention(CLASS), hoặc @Retention(RUNTIME):

- Nếu muốn **bind object annotation** vào biến trong advice, phải dùng RUNTIME.
- Với @this, @target và @args dựa vào annotation của runtime type, AspectJ yêu cầu retention RUNTIME.
- @annotation, @within, @withincode có thể match annotation với ít nhất CLASS retention trong các trường hợp không bind; khi bind giá trị của annotation cũng cần RUNTIME.
- Annotation không tự kế thừa giữa các phương thức override chỉ vì cùng tên. Với annotation trên type, quy tắc kế thừa Java và cách pointcut xét runtime type phải được hiểu riêng.

Để giải thích và chạy code dễ dàng, bài này dùng @Retention(RetentionPolicy.RUNTIME) cho annotation phương thức.

## 7. @annotation(annotationVariable): vừa lọc vừa lấy metadata

Giả sử annotation có thuộc tính value():

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface TraceOperation {
    String value();
}
~~~

Một aspect có thể lấy chính instance annotation:

~~~aspectj
pointcut annotatedWork(TraceOperation operation):
    execution(@TraceOperation * *.*(..))
    && @annotation(operation);

before(TraceOperation operation): annotatedWork(operation) {
    System.out.println(operation.value());
}
~~~

Hai đoạn trên là mảnh minh họa; cần đặt đúng vào các tệp/khối tương ứng và weave bằng AspectJ mới hoạt động. Trong execution(...), @TraceOperation trong method pattern lọc phương thức có annotation ấy; @annotation(operation) bind metadata để advice lấy value(). Có thể dùng execution(* *.*(..)) && @annotation(operation) khi muốn dùng đúng một bộ lọc annotation mà không lặp lại annotation ở chữ ký.

Điểm hữu ích: annotation thể hiện ý định ở ranh giới phương thức, còn aspect thực thi hành vi xuyên suốt. Tuy nhiên, annotation chỉ là metadata; nó không tự phát sinh advice nếu không có pointcut/weaving thực sự áp dụng.

### Phân biệt kiểu runtime của đối số với annotation trên tham số khai báo

@args(TrustedRequest) nói rằng **runtime class của object đối số** có annotation @TrustedRequest. Nó không có nghĩa **tham số trong khai báo phương thức** được gắn annotation @TrustedRequest. Đây là lỗi đọc pointcut khá phổ biến.

Ví dụ:

~~~java
@TrustedRequest
class RequestData {}

void process(RequestData data) {}
~~~

Nếu @TrustedRequest được định nghĩa với @Target(TYPE) và @Retention(RUNTIME), @args(TrustedRequest) có thể match khi runtime argument là RequestData. Ngược lại, gắn annotation lên tham số như void process(@TrustedRequest RequestData data) là metadata **trên formal parameter**; không phải nội dung mà @args kiểm tra. Hai đoạn minh họa này không độc lập để biên dịch.

## 8. Ví dụ đầy đủ: this, target, args và @annotation trong một lần chạy

Ví dụ sau sử dụng **code-style AspectJ** (tệp .aj), chọn một **method call** từ một đối tượng Demo đến đối tượng ServiceImpl, rồi chọn **method execution** có annotation @Trace. Cả hai advice chạy trước phương thức gốc, từ đó thấy được this/target khác nhau ở call và cùng nhận đối tượng service ở execution.

### Tệp 1: Demo.java

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Trace {
    String value();
}

interface Service {
    void send(String message);
}

class ServiceImpl implements Service {
    @Trace("dispatch")
    public void send(String message) {
        System.out.println("body:" + message);
    }
}

public class Demo {
    public void run() {
        Service service = new ServiceImpl();
        service.send("hello");
    }

    public static void main(String[] args) {
        new Demo().run();
    }
}
~~~

### Tệp 2: TracingAspect.aj

~~~aspectj
public aspect TracingAspect {
    pointcut sendCall(Demo caller, ServiceImpl receiver, String message):
        call(void Service.send(String))
        && within(Demo)
        && this(caller)
        && target(receiver)
        && args(message);

    before(Demo caller, ServiceImpl receiver, String message):
            sendCall(caller, receiver, message) {
        System.out.println(
            "call:this=" + caller.getClass().getSimpleName()
            + ",target=" + receiver.getClass().getSimpleName()
            + ",arg=" + message
        );
    }

    pointcut tracedExecution(
            ServiceImpl receiver, String message, Trace trace):
        execution(void ServiceImpl.send(String))
        && this(receiver)
        && args(message)
        && @annotation(trace);

    before(ServiceImpl receiver, String message, Trace trace):
            tracedExecution(receiver, message, trace) {
        System.out.println(
            "execution:annotation=" + trace.value()
            + ",this=" + receiver.getClass().getSimpleName()
            + ",arg=" + message
        );
    }
}
~~~

### Biên dịch và chạy

Cần cài **JDK 17+** và bộ công cụ AspectJ có lệnh **ajc** hỗ trợ Java 17, đồng thời có file aspectjrt.jar từ cùng bản phân phối. Đặt Demo.java, TracingAspect.aj và aspectjrt.jar trong cùng thư mục làm việc để dùng các lệnh sau:

~~~bash
mkdir -p out
ajc -17 -classpath aspectjrt.jar -d out Demo.java TracingAspect.aj
java -cp out:aspectjrt.jar Demo
~~~

Các lệnh trên dùng cú pháp Linux/macOS. Trên Windows PowerShell, tạo thư mục bằng mkdir out và dùng dấu chấm phẩy trong classpath:

~~~powershell
mkdir out
ajc -17 -classpath aspectjrt.jar -d out Demo.java TracingAspect.aj
java -cp "out;aspectjrt.jar" Demo
~~~

javac đơn thuần **không** biên dịch cú pháp aspect trong file .aj; ajc cần nhìn thấy cả tệp Java chứa join point được chọn lẫn aspect khi compile-time weaving. Trong runtime cũng cần aspectjrt.jar. Không dùng câu lệnh Java thuần để chạy mà thiếu phần đã weave, vì advice sẽ không thực thi.

**Kết quả mong đợi sau weaving thành công** (chỉ hiển thị stdout chương trình, không tính thông báo biên dịch):

~~~text
call:this=Demo,target=ServiceImpl,arg=hello
execution:annotation=dispatch,this=ServiceImpl,arg=hello
body:hello
~~~

Giải thích:

1. Demo.run() là instance method, nên call join point có **this=Demo**. Dù biến service được khai báo theo interface Service, receiver thật là ServiceImpl nên **target(receiver)** match runtime type.
2. args(message) ràng buộc giá trị "hello" ở vị trí đối số duy nhất.
3. Khi ServiceImpl.send() được thực thi, **this(receiver)** của execution join point là ServiceImpl.
4. @annotation(trace) bind annotation @Trace("dispatch") khai báo trên ServiceImpl.send(); advice đọc được trace.value() = "dispatch".
5. Cả hai advice đều là before: advice tại call chạy trước khi bước vào execution, sau đó mới chạy thân send().

**Giới hạn kiểm chứng:** bản code được trình bày theo cú pháp AspectJ chuẩn và kết quả được suy ra theo trình tự join point; môi trường soạn bài không có lệnh ajc để chạy thử weaving tại chỗ. Khi thực hành, dùng một phiên bản AspectJ phù hợp với JDK, kiểm tra lệnh ajc -version, rồi đối chiếu stdout thực. Trong các môi trường weaving hoặc cách viết pointcut khác, số join point và thứ tự advice có thể thay đổi nếu tập chọn khác.

## 9. Vì sao từng điều kiện trong ví dụ là cần thiết?

Pointcut call:

~~~aspectj
call(void Service.send(String))
&& within(Demo)
&& this(caller)
&& target(receiver)
&& args(message)
~~~

- call(...) chọn lời gọi theo **chữ ký tại vị trí gọi**. Trong Demo.run(), biến service có kiểu interface Service, nên pattern Service.send phù hợp.
- within(Demo) giới hạn call site vào mã định nghĩa trong Demo.
- this(caller) ràng buộc object đang thực thi mã chứa lời gọi.
- target(receiver) ràng buộc object thực sự nhận lời gọi.
- args(message) lấy argument thực tế.

Pointcut execution:

~~~aspectj
execution(void ServiceImpl.send(String))
&& this(receiver)
&& args(message)
&& @annotation(trace)
~~~

- execution(...) chọn thân phương thức ServiceImpl.send.
- this(receiver) lấy object đang chạy thân phương thức.
- args(message) lấy đối số của lượt thực thi.
- @annotation(trace) chỉ match nếu subject mang annotation có kiểu của biến formal Trace và bind instance annotation.

Nếu đổi Demo.run() thành static method mà vẫn giữ this(caller), call pointcut không match vì không có object caller. Nếu đổi annotation sang chỉ SOURCE retention thì @annotation(trace) không thể bind runtime instance. Nếu đổi pattern call sang một chữ ký khác, pointcut có thể không khớp dù receiver runtime vẫn là ServiceImpl.

## 10. Các pointcut annotation thường dùng và tình huống phù hợp

### @this và @target

~~~aspectj
call(* *.*(..)) && @this(ObservedType)
call(* *.*(..)) && @target(ObservedType)
~~~

Các biểu thức minh họa này giả định @ObservedType là annotation có @Target(TYPE), @Retention(RUNTIME). Biểu thức đầu xét **runtime class của bên đang thực thi mã gọi**, biểu thức sau xét **runtime class của đối tượng đích**. Tại một call join point có object bên gọi và bên nhận khác nhau, chúng có thể cho kết quả khác.

### @within và @withincode

~~~aspectj
execution(* *(..)) && @within(ObservedType)
call(* *.*(..)) && @withincode(ObservedMethod)
~~~

@within xét annotation trên kiểu **định nghĩa mã gắn với join point**; @withincode xét annotation trên **phương thức hoặc constructor bao lấy vị trí mã**. Ví dụ dùng @withincode để chỉ đo các lời gọi phát ra từ những phương thức đã được chú thích, thay vì những lời gọi đến các phương thức được chú thích.

### @args

~~~aspectj
execution(* Service.consume(..)) && @args(ObservedPayload, ..)
~~~

Nếu @ObservedPayload có @Target(TYPE), @Retention(RUNTIME), biểu thức trên cần đối số đầu là object có **runtime class** mang annotation ấy. Nó không xét annotation trên chính tham số được khai báo trong phương thức consume. Với đối số null, không có runtime type để đọc annotation, nên không được xem null như một object annotated.

### @annotation

~~~aspectj
execution(* ServiceImpl.*(..)) && @annotation(Trace)
~~~

Lọc việc thực thi phương thức trong ServiceImpl có subject mang @Trace. Dạng @annotation(trace) với biến formal Trace trace dùng khi advice cần đọc thuộc tính. Điểm mạnh là mô tả ý định rõ bằng annotation. Điểm yếu là có thể bỏ sót phương thức chưa gắn annotation và có thể nhầm vị trí annotation ở interface so với implementation; cần kiểm thử trên join point thực tế.

## 11. Phối hợp pointcut bằng phép logic và binding đúng

**AND:** các điều kiện cùng phải đúng.

~~~aspectj
execution(* ServiceImpl.send(..))
&& args(String)
&& @annotation(Trace)
~~~

**OR:** được phép chọn hai nhóm join point, nhưng cần lưu ý binding. Trong biểu thức có biến formal, các nhánh hợp lệ phải ràng buộc đầy đủ và không mơ hồ.

**NOT:** loại bỏ phần không mong muốn, ví dụ tránh gắn aspect vào chính lớp logging/aspect hoặc những thao tác nội bộ.

~~~aspectj
execution(* shop..*(..)) && !within(shop.instrumentation..*)
~~~

Đây là biểu thức minh họa cần package thực. Không nên viết pointcut quá rộng như execution(* *(..)) rồi chỉ dựa vào kiểm tra kiểu động để quyết định ở hàng triệu join point; giới hạn theo loại join point, phạm vi package/type và ngữ cảnh khi có thể. Điều này giúp giảm chi phí weaving và làm tác động của aspect dễ theo dõi.

### Pointcut không phải truy vấn dữ liệu nghiệp vụ

args(orderId) bind ID thực tế nhưng không kiểm chứng quyền truy cập đối với đơn hàng đó. @annotation(RequiresRole) có thể giúp chọn phương thức cần áp dụng chính sách, nhưng annotation hay tên vai trò không tự chứng minh người gọi có quyền với **tài nguyên cụ thể**. Advice phải gọi logic phân quyền đáng tin với dữ liệu thích hợp nếu nhiệm vụ là kiểm soát truy cập.

Tương tự, target(ServiceImpl) không xác nhận đây là “đúng tenant”. Type của receiver chỉ là một yếu tố lựa chọn join point, không thay thế các bất biến của domain.

## 12. Các lỗi thường gặp và cách chẩn đoán

| Lỗi | Biểu hiện | Nguyên nhân và cách khắc phục |
| --- | --- | --- |
| Dùng this(ServiceImpl) tại call từ Demo | Advice không chạy | this ở call là **Demo**, cần target(ServiceImpl) cho receiver |
| Dùng target(Demo) ở call đến ServiceImpl | Không match | target là đối tượng đích |
| Dùng this(...) tại static main | Không match | Không có instance this ở static context |
| Dùng call(ServiceImpl.send) nhưng call site khai báo interface Service | Có thể không match | Chữ ký của call site thường là Service.send; kiểm tra chữ ký thực và dùng target(...) nếu cần loại runtime |
| Nhầm args(String) với execution(...(String)) | Chọn nhầm join point | args xét kiểu đối số runtime/giá trị; execution xét chữ ký khai báo |
| Dùng @args để tìm annotation trên parameter | Không match kỳ vọng | @args kiểm tra runtime type của **đối số** |
| Dùng @annotation để tìm annotation trên class | Không match kỳ vọng | Dùng @within, @this hoặc @target theo ý nghĩa |
| Annotation chỉ SOURCE/CLASS nhưng cố bind annotation runtime | Không biên dịch hoặc không bind như mong muốn | Dùng RUNTIME cho annotation cần binding |
| Điểm match quá rộng | Weaving chậm, advice xuất hiện không mong muốn | Thêm kinded/scoping PCD và giới hạn đúng loại join point |
| Advice không xuất hiện dù code hợp lệ | Chạy chương trình không weave hoặc bỏ sót nguồn | Bảo đảm compile/weave đúng tệp và dùng đúng runtime classpath |
| Biến formal khai báo sai kiểu/vị trí | Lỗi compile hoặc lọc sai | Đối chiếu kiểu/đối số với args(...) và advice signature |
| Log dữ liệu từ args(...) không chọn lọc | Rò token, dữ liệu cá nhân | Chỉ đọc/trích xuất tham số đã kiểm duyệt |

Để chẩn đoán, hãy kiểm tra theo thứ tự: join point là call hay execution; chữ ký tại điểm đó; this/target/args thật; annotation nằm trên member hay type nào, retention gì; pointcut có được woven vào đúng code hay không; và advice có thật sự áp dụng trong luồng gọi đang thử không.

## 13. Bài tập kiểm tra hiểu đúng

1. Trong một instance method của Caller có lệnh api.send("hi"), với api được khai báo kiểu Interface nhưng object thật là Impl: ở call join point, this và target lần lượt là gì? Viết pointcut chọn riêng target Impl.
2. Nếu lệnh gọi trên được chuyển vào static method, this(Caller) còn match không? target(Impl) có thể vẫn match không?
3. Một phương thức process(Object x) nhận runtime object String: execution(* process(Object)) && args(String) khác execution(* process(String)) thế nào?
4. Một phương thức annotated @Trace trên implementation nhưng không trên interface: so sánh call và execution join point; pointcut @annotation có thể bị ảnh hưởng thế nào?
5. Lớp RequestPayload có @Sensitive trên type; tham số method lại không có annotation. Biểu thức @args(Sensitive, ..) đang kiểm tra điều gì?
6. Nếu muốn chỉ đo các lời gọi **phát ra từ** các phương thức được chú thích @Audited, nên cân nhắc @withincode(Audited) hay @annotation(Audited)? Giải thích vì sao.

**Đáp án định hướng:** (1) this=Caller, target=Impl; kết hợp call(...) && target(Impl). (2) this(Caller) không match trong static context; target(Impl) vẫn có thể match một instance call. (3) chữ ký vẫn nhận Object, nhưng args(String) có thể match khi đối số runtime là String; execution pattern nhận String không tương đương. (4) annotation trên member được chọn, nên phải xác nhận subject của call và execution thay vì giả định giống nhau. (5) xét annotation trên runtime class của giá trị truyền vào. (6) @withincode chọn join point nằm trong mã phương thức được chú thích, còn @annotation chọn join point có subject được chú thích.

## 14. Tóm lược nguyên tắc thiết kế

- Bắt đầu bằng việc xác định **call** hay **execution**, rồi mới chọn this/target.
- Dùng **this** cho đối tượng hiện hành, **target** cho đối tượng nhận thao tác, **args** cho đối số thực.
- Dùng **@annotation** cho annotation trên subject, **@within/@withincode** cho ngữ cảnh mã, **@this/@target/@args** cho annotation trên runtime type của object tương ứng.
- Khi cần sử dụng giá trị/metadata trong advice, khai báo **biến formal** đúng kiểu và bind rõ ràng; với annotation binding phải bảo đảm RUNTIME retention.
- Đặt kinded/scoping PCD để giới hạn tập join point, tránh pointcut quá rộng.
- Luôn xác nhận join point có được weaving thực sự và khớp tập tình huống cần đo/bảo vệ.
- Không dùng PCD thay thế nghiệp vụ hoặc phân quyền; thông tin runtime thu được chỉ là ngữ cảnh để advice thực hiện đúng trách nhiệm.

**Kết luận:** this, target và args mô tả **ngữ cảnh động của một join point**; các pointcut theo annotation cho phép chọn và bind metadata theo **vị trí annotation thực sự tồn tại**. Hiểu đúng sự khác biệt call/execution và member/type/argument giúp viết aspect chính xác, dễ kiểm thử và tránh can thiệp nhầm hành vi.
