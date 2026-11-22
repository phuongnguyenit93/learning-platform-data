# Advice trước khi điểm can thiệp thực thi (Before Advice) trong AOP

## 1. Before advice là gì?

**Before advice** là đoạn hành vi được một aspect yêu cầu chạy **trước join point đã được pointcut chọn**, theo ngữ nghĩa của mô hình Aspect-Oriented Programming (AOP) đang sử dụng. Đây là một cách đặt logic xuyên cắt, ví dụ logging, tracing, kiểm toán lượt thử hay kiểm tra điều kiện kỹ thuật, tại một tập điểm thực thi mà không phải chép các lời gọi helper vào từng phương thức nghiệp vụ.

Có bốn thành phần cần xác định:

1. **Join point:** sự kiện nào có thể can thiệp: method call, method execution, field access, constructor hoặc một loại được công cụ hỗ trợ.
2. **Pointcut:** điều kiện nào chọn join point, ví dụ chữ ký, type, annotation, vị trí caller hoặc kiểu receiver.
3. **Advice:** điều gì phải xảy ra trước, và hậu quả nếu hành vi trước thành công hoặc thất bại.
4. **Weaving/interception:** công cụ gắn hành vi vào bytecode hoặc đường gọi thực tế như thế nào.

Luồng tổng quát:

~~~text
Caller
  │
  ▼
Join point phù hợp pointcut?
  ├─ Không ──► Chạy đường thực thi gốc
  └─ Có
       │
       ▼
    Before advice
       │
       ├─ Kết thúc bình thường ──► Tiếp tục join point
       │
       └─ Ném lỗi ──► Đường ngoại lệ;
                     phần gốc có thể chưa được thực thi
~~~

Before advice mô tả **thời điểm hành vi được gắn vào luồng**, chứ không bảo đảm join point nào cũng xuất hiện hoặc mọi lời gọi đều được chặn. Nếu pointcut không khớp, lớp không được weave hoặc caller bỏ qua proxy, before advice không có cơ hội chạy ở điểm đó.

## 2. Đặt before advice trong mô hình AOP

| Thuật ngữ | Ý nghĩa | Vai trò trong bài |
|---|---|---|
| **Join point** | Điểm trong quá trình chạy có thể được nhận diện | Xác định hành vi nào sắp diễn ra |
| **Pointcut** | Tập điều kiện chọn join point | Quyết định phạm vi áp dụng advice |
| **Before advice** | Hành vi chạy trước điểm được chọn | Ghi nhận hoặc kiểm tra trước thao tác |
| **Target** | Đối tượng hoặc mã chịu tác động | Cung cấp ngữ cảnh để quan sát/lọc |
| **Weaver** | Công cụ kết hợp aspect với chương trình | Thực thi việc gắn advice vào đúng điểm |
| **Aspect** | Đơn vị tổ chức pointcut, advice và cấu hình | Gom trách nhiệm xuyên cắt |

Ví dụ giả mã **không phải chương trình Java có thể biên dịch**:

~~~text
aspect ExecutionTrace
    pointcut observedOperations =
        execution of methods marked @Observed

    before observedOperations:
        writeStartEvent()
end
~~~

Ý nghĩa: trước khi một execution được chọn bắt đầu, chạy mã ghi dấu. Nhưng đây mới là đặc tả ý định. Bộ dệt hoặc interceptor cần thực sự nhận diện được annotation và tham gia vào đường chạy.

Một ví dụ cú pháp theo **AspectJ**, là một ngôn ngữ AOP cụ thể:

~~~java
// Đoạn minh họa cú pháp AspectJ.
// Cần trình biên dịch/bộ dệt tương ứng, không chạy bằng javac đơn thuần.

aspect TraceAspect {
    before(): execution(* example.OrderService.submit(..)) {
        System.out.println("before submit");
    }
}
~~~

Không được suy rằng mọi engine AOP hỗ trợ các designator hay join point giống AspectJ. Ví dụ chỉ giúp nhận diện cấu trúc **before + pointcut + body**.

## 3. Thời điểm: trước method call khác trước method execution

### 3.1. Before ở method-call join point

Một **call join point** nằm ở vị trí phát lệnh gọi trong mã caller.

~~~java
final class Client {
    void submit(OrderService service) {
        service.create();
    }
}
~~~

Đây là đoạn Java minh họa chưa có định nghĩa OrderService và main. Nếu bộ dệt hỗ trợ method-call join point tại biểu thức **service.create()**, advice trước call chạy tại **biên caller** trước khi lời gọi được chuyển tới phương thức đích.

~~~text
Client.submit()
    │
    ▼
call join point cho service.create()
    │
    ▼
before advice ở phía caller
    │
    ▼
gọi Service.create()
~~~

Call pointcut có thể phân biệt **nơi phát lệnh gọi**, và có thể kết hợp điều kiện caller, vị trí lexical hoặc target runtime theo mô hình hỗ trợ.

### 3.2. Before ở method-execution join point

Một **execution join point** biểu thị việc bắt đầu thực thi thân một phương thức.

~~~text
Caller thực hiện lời gọi
   │
   ▼
dispatch đến thân Service.create()
   │
   ▼
execution join point
   │
   ▼
before advice ở phía phương thức
   │
   ▼
thân Service.create() chạy
~~~

Một execution có thể được gọi từ nhiều caller; advice ở biên execution có thể quan sát các lần thực thi từ các caller khác nhau nếu lớp và join point thực sự được weave.

Điểm khác biệt:

| Tiêu chí | Before tại call | Before tại execution |
|---|---|---|
| Nằm ở đâu? | Biểu thức gọi bên caller | Điểm đi vào thân phương thức đích |
| Quan tâm chính | Ai phát lời gọi và tại vị trí nào | Phương thức thực sự nào bắt đầu chạy |
| Ảnh hưởng của đa hình | Chữ ký/vị trí call có thể giữ nguyên | Implementation thực thi có thể thay đổi |
| Giới hạn thường gặp | Phải instrument được nơi gọi | Phải instrument được thân method hoặc chặn đúng đường chạy |
| Phạm vi proxy đơn giản | Không tự có call join point tại mọi source site | Có thể có interception khi gọi qua proxy, tùy cơ chế |

Một request có thể chứa cả call và execution join point. Nếu pointcut chọn cả hai, advice có thể chạy **hai lượt tại hai điểm khác nhau**, dù nghiệp vụ chỉ thực hiện một thao tác ở mức cao.

### 3.3. Đánh giá đối số có thể thất bại trước join point

Ví dụ Java:

~~~java
service.create(loadInput());
~~~

Nếu **loadInput()** ném ngoại lệ, chương trình có thể không đến lời gọi Service.create. Khi đó trước advice chọn **execution của create** chắc chắn không có execution đó để quan sát. Một before advice tại call cũng phải tuân theo ngữ nghĩa cụ thể của join point trong công cụ, không nên suy rằng nó chạy trước toàn bộ biểu thức con tạo tham số.

Điểm học quan trọng: **trước join point** là mốc của mô hình AOP, không có nghĩa **trước mọi công việc liên quan đến thao tác**.

## 4. Before advice có gì khác các loại advice khác?

| Loại | Thời điểm/khả năng chính | Điều không nên suy |
|---|---|---|
| **Before** | Trước join point khớp | Không mặc nhiên biết kết quả cuối |
| **After returning** | Sau khi join point hoàn tất bình thường | Không nhất thiết chứng minh giao dịch bất đồng bộ/ngoài hệ thống đã commit |
| **After throwing** | Khi join point kết thúc bằng ngoại lệ phù hợp | Không thay thế mọi chính sách exception toàn hệ thống |
| **After/finally** | Khi rời join point theo ngữ nghĩa công cụ | Không tự có nghĩa thao tác thành công |
| **Around** | Bao lấy điểm chọn; có thể điều phối proceed trong mô hình hỗ trợ | Không đồng nhất với một before đơn thuần |

Một **before advice** thông thường không có quyền trực tiếp gọi lệnh **proceed()** để quyết định thực thi target mấy lần hoặc thay return value. Năng lực đó thuộc around advice trong những mô hình cho phép. Tuy nhiên, before advice vẫn có thể ảnh hưởng việc target được thực thi qua **ngoại lệ và side effect**.

Đặc biệt, trước advice không thể tự lấy giá trị trả về mà target **chưa tạo ra**. Muốn tính duration, ghi completion status, quan sát exception hoặc thay return, cần cơ chế thích hợp sau/bao quanh.

## 5. Nếu before advice hoàn tất bình thường

Giả sử advice chỉ ghi log:

~~~text
before: request begins
core: business method starts
core: business method returns
~~~

Đây là trace minh họa, không phải stdout của đoạn Java độc lập.

Nếu advice kết thúc bình thường, phần thực thi gốc có thể tiếp tục tại join point. Với advice quan sát thuần túy, giá trị trả về và ngoại lệ của target thường được giữ theo hợp đồng ban đầu. Nhưng việc đặt advice **không tự bảo đảm thuần túy**: mã advice có thể ghi dữ liệu, thay đổi trạng thái dùng chung, lấy lock hoặc gọi thêm các method.

Vì thế khi đánh giá trước advice, cần hỏi:

- Nó có làm thay đổi dữ liệu đầu vào hoặc trạng thái của target không?
- Nó có thể throw một exception khác không?
- Nó có thể gọi vào phương thức cũng khớp pointcut, gây reentrancy không?
- Nó có làm thay đổi timing, lock ordering hoặc hiệu năng không?

Nếu một concern được mô tả là logging, thiết kế tốt thường giới hạn nó vào ghi nhận cần thiết và không thay đổi nghiệp vụ ngoài ý định.

## 6. Nếu before advice tự ném ngoại lệ

Giả sử advice kiểm tra một context bắt buộc:

~~~text
before join point:
    if context is missing:
        throw MissingContext

target:
    perform work
~~~

Đây là giả mã. Khi advice throw và không có một tầng điều phối khác bắt lỗi/tiếp tục, phần hành vi gốc ở join point có thể **chưa chạy**. Caller sẽ nhận lỗi đến từ advice, không phải từ method gốc.

Điều này khác hoàn toàn với trường hợp target ném lỗi:

~~~text
before runs normally
    ↓
target starts
    ↓
target throws
    ↓
caller handles target error
~~~

Với target ném lỗi, before đã chạy từ trước. Vì vậy ghi một event “đã bắt đầu xử lý” bằng before có thể hợp lệ, nhưng ghi “xử lý thành công” là sai vì tương lai chưa được xác định.

Ngoài ra, ngay cả khi advice throw, side effect nó đã tạo ra trước khi throw có thể vẫn tồn tại. AOP không tự rollback toàn bộ tác dụng phụ của advice.

### 6.1. Khi nào dùng before để chặn?

Một kiểm tra kỹ thuật xuyên cắt có thể từ chối thao tác bằng exception. Nhưng khi kiểm tra liên quan **bảo mật** hoặc **bất biến nghiệp vụ**, cần bảo đảm mọi đường đi cần bảo vệ đều đi qua đúng pointcut/cơ chế interception. Một proxy bị bỏ qua, subclass không nằm trong phạm vi weave hoặc lời gọi nội bộ có thể làm policy không được áp dụng như mong đợi.

Không nên chỉ thêm một before advice rồi mặc định đã có bảo đảm an toàn ở toàn hệ thống.

## 7. Ví dụ Java 17 chạy được: before bằng interceptor qua proxy

Chương trình sau thể hiện ba trường hợp: lời gọi thành công qua bộ chặn, target ném ngoại lệ sau khi before chạy, và một lời gọi trực tiếp target bỏ qua bộ chặn. Đây là **JDK dynamic proxy**, một ví dụ cụ thể của runtime interception; **không phải bytecode weaving tổng quát**.

Tạo file **BeforeAdviceDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.Locale;

public class BeforeAdviceDemo {
    interface Work {
        String process(String input);
        void fail();
    }

    static final class Core implements Work {
        public String process(String input) {
            System.out.println("core: process " + input);
            return input.toUpperCase(Locale.ROOT);
        }

        public void fail() {
            System.out.println("core: fail");
            throw new IllegalStateException("boom");
        }
    }

    static Work withBefore(Work target) {
        return (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[] {Work.class},
                (proxy, method, arguments) -> {
                    System.out.println("before: " + method.getName());
                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException exception) {
                        throw exception.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        Work original = new Core();
        Work observed = withBefore(original);

        System.out.println("result=" + observed.process("alpha"));

        try {
            observed.fail();
        } catch (IllegalStateException exception) {
            System.out.println("caught: " + exception.getMessage());
        }

        System.out.println("direct=" + original.process("beta"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc cao hơn:

~~~bash
javac --release 17 BeforeAdviceDemo.java
java BeforeAdviceDemo
~~~

Stdout:

~~~text
before: process
core: process alpha
result=ALPHA
before: fail
core: fail
caught: boom
core: process beta
direct=BETA
~~~

**Giải thích chi tiết:**

1. **observed.process("alpha")** đi qua proxy nên handler chạy dòng **before: process**, sau đó target thực thi và trả **ALPHA**.
2. **observed.fail()** cũng đi qua proxy. Before chạy trước, rồi target ném **IllegalStateException**; đây là ví dụ “before đã ghi nhận lượt bắt đầu nhưng thao tác thất bại”.
3. Khi lời gọi reflection tạo **InvocationTargetException**, handler dùng **getCause()** để chuyển tiếp lỗi do target gây ra; caller bắt đúng **IllegalStateException** với thông điệp **boom**.
4. **original.process("beta")** gọi target trực tiếp, không đi qua proxy; do đó không có dòng before. Điều này chứng minh điểm chặn phải có mặt trên đường thực thi thật.
5. Handler trong ví dụ không triển khai bộ ngôn ngữ pointcut đầy đủ. Nó chỉ chặn các lời gọi đến các method thuộc giao diện **Work** trên reference proxy tương ứng.

### 7.1. Ví dụ chứng minh được điều gì?

Nó chứng minh cơ chế **thực hiện hành vi trước một lời gọi được chặn** và ảnh hưởng của đường trực tiếp/proxy. Nó không chứng minh tất cả loại join point như constructor, field access, private method hoặc direct bytecode execution đều có thể bị chặn bởi JDK proxy.

Đối với một ngôn ngữ AOP có compile-time hoặc load-time weaving, cần chạy ví dụ tích hợp thật với weaver cụ thể để xác minh tập điểm và thứ tự advice trên những loại join point khác.

## 8. Thông tin có thể đọc trong before advice

Thông tin có thể được công cụ cung cấp hoặc bind vào advice:

- Tên và loại **join point**.
- Chữ ký method/constructor/field nếu loại điểm cho phép.
- Đối tượng đang thực thi và **target** ở những loại join point có các đối tượng đó.
- Tham số đã được đánh giá của lời gọi; type/annotation/metadata phù hợp.
- Trace ID, context hoặc thời điểm bắt đầu nếu đã được ứng dụng cung cấp.

Nhưng **return value chưa có** ở thời điểm before advice. Một method có thể trả về future đại diện cho tác vụ còn chạy, nên advice trước lại càng không có thông tin về việc tác vụ đó hoàn thành.

Trong một ngôn ngữ AOP hỗ trợ binding, ví dụ cú pháp minh họa AspectJ:

~~~java
// Minh họa cú pháp AspectJ, không phải class Java độc lập.
before(String id):
        execution(* example.OrderService.submit(String))
        && args(id) {
    System.out.println("submit begins: " + id);
}
~~~

Điều kiện **args(id)** thể hiện việc bind tham số. Nó không có nghĩa mọi local variable trong target đều truy cập được. Nếu cần kết quả hoặc exception từ target, thiết kế phải sử dụng advice sau hoặc around phù hợp.

### 8.1. Đối số mutable và side effect

Trước advice có reference đến một danh sách mutable có thể thay đổi danh sách đó, gây tác động lên phần thân target sau này. Ví dụ minh họa Java:

~~~java
static void audit(java.util.List<String> values) {
    values.add("marker");  // Sửa nội dung cùng một list.
    values = new java.util.ArrayList<>(); // Chỉ gán lại biến local.
}
~~~

Đây chưa phải chương trình độc lập. Việc gán lại một parameter local của advice không tự thay parameter đang được caller truyền cho target. Nhưng mutate object được chia sẻ có thể làm thay đổi nghiệp vụ. Vì thế một before advice dùng để quan sát nên mặc định **không sửa input**.

## 9. Thứ tự nhiều before advice

Hai aspect có thể có before advice cùng khớp một join point:

~~~text
join point khớp
    ├─ before từ Aspect A
    ├─ before từ Aspect B
    └─ target method
~~~

Sơ đồ trên chỉ minh họa một thứ tự có thể xảy ra. **A trước B** hay **B trước A** phụ thuộc quy tắc precedence/order của công cụ và cấu hình. Không được mặc định thứ tự theo tên file, package hoặc thời gian viết source.

Nếu thứ tự ảnh hưởng hành vi, cần nêu rõ thứ tự yêu cầu và kiểm thử tích hợp, ví dụ:

- Kiểm tra thông tin ngữ cảnh trước khi log dữ liệu sử dụng context ấy.
- Kiểm soát quyền trước khi thao tác có side effect.
- Xác định một hoặc nhiều advice có thể ném lỗi, ngăn những bước sau.

### 9.1. Khi before nằm dưới around

Trong một số cơ chế AOP, **around advice** có thể chặn hoặc chuyển tiếp điểm qua lệnh tương đương **proceed**. Nếu around không chuyển tiếp tới phần join point nơi before được gắn, một số before advice bên trong đường đó có thể không chạy. Vì vậy không được kết luận “mọi before trên điểm khớp luôn chạy” mà không xét các tầng điều phối và precedence.

### 9.2. Before không thay cleanup

Một thao tác cần bảo đảm giải phóng resource sau target không thể chỉ dựa vào before. Cần after/finally hoặc một đường bao quanh có finally tương ứng. Tương tự, một metric duration cần thời điểm **kết thúc thực sự**, không thể tính chỉ từ một event bắt đầu.

## 10. Bao nhiêu lần before chạy trên một nghiệp vụ?

Số lần advice chạy phụ thuộc **số join point thực sự khớp**, không nhất thiết bằng số request nghiệp vụ.

Các trường hợp thường gặp:

- **Call và execution cùng được chọn:** một lời gọi có thể dẫn đến hai điểm khác nhau.
- **Nested calls:** phương thức A gọi B rồi C, trước advice có thể chạy ở cả A, B, C.
- **Recursion:** cùng một method được thực thi nhiều lượt đệ quy, advice có thể chạy từng lượt.
- **Retry:** một yêu cầu có thể dẫn đến nhiều lần thử target; before nằm trong vòng retry có thể chạy nhiều lần.
- **Polymorphism:** call site giữ nguyên nhưng runtime target thay đổi, điều kiện target có thể khớp ở lần này nhưng không khớp lần khác.
- **Dynamic pointcut:** chữ ký tĩnh khớp nhưng điều kiện runtime về argument, receiver hoặc control flow không thỏa nên advice không chạy.

Nếu muốn metric **số yêu cầu từ bên ngoài**, nên chọn một biên yêu cầu ổn định. Nếu muốn metric **số lần thực thi phương thức**, một execution pointcut phù hợp sẽ diễn đạt mục tiêu đó tốt hơn. Đừng đếm một event rồi đặt nhãn mang ý nghĩa khác.

## 11. Kế thừa, override và lời gọi nội bộ

### 11.1. Override có thể thay execution method

Với **Base ref = new Child()** và Child override **work()**, Java dispatch đến **Child.work()**. Một pointcut chọn chính xác execution của thân Base.work không có nghĩa tự áp dụng cho mọi lần gọi work qua reference Base. Cần làm rõ chọn theo call signature, declaring type, runtime type hay subtype pattern.

### 11.2. Self-invocation khi dùng proxy

Ví dụ:

~~~java
class Service {
    void outer() {
        inner();
    }

    void inner() {
        // Hành vi cần quan sát
    }
}
~~~

Nếu một proxy ngoài Service chỉ chặn lời gọi từ caller qua proxy, thì **outer()** gọi **inner()** trực tiếp trên target có thể không kích hoạt handler của proxy lần thứ hai. Nhưng một bytecode weaver có thể chèn advice vào execution của inner và vẫn quan sát được lời gọi nội bộ nếu lớp/method nằm trong phạm vi weave.

Do đó **đường đi qua proxy** và **điểm thực thi được weave** là hai cơ chế cần phân biệt, không áp đặt giới hạn của cơ chế này lên mọi AOP.

### 11.3. Các loại method đặc biệt

| Trường hợp | Điều cần xác minh |
|---|---|
| **Static** | Không có receiver instance; các điều kiện this/target không tự tương đương tên lớp. |
| **Private** | Không hiện diện trên JDK interface proxy; bytecode weaver có thể hỗ trợ execution nếu mô hình cho phép. |
| **Final** | Không thể override bằng subclass proxy theo cách thông thường, nhưng công nghệ weaving có giới hạn khác. |
| **Constructor** | Object có thể chưa hoàn tất bất biến; trước constructor không giống trước mọi bước tạo object. |
| **Class initializer** | Thường gắn với vòng đời lớp, không phải mỗi instance. |

Chọn before ở những điểm vòng đời sớm có thể khiến advice đọc trạng thái chưa hợp lệ hoặc phát tán reference chưa khởi tạo xong. Không nên truy cập đối tượng thiếu an toàn chỉ để lấy thêm thông tin log.

## 12. Chọn những concern thích hợp

### 12.1. Trace bắt đầu

Before advice phù hợp với log **bắt đầu** thao tác tại ranh giới kỹ thuật đã chọn. Nó không cung cấp một kết luận về thành công. Một hệ thống trace hoàn chỉnh cần correlation ID và điểm kết thúc tương ứng.

### 12.2. Audit lượt thử

Ghi **attempted action** trước thao tác có thể có ý nghĩa, kể cả khi target thất bại. Nhưng ghi **succeeded** trong before là không chính xác. Audit bắt buộc cần hợp đồng về lưu bền, xử lý thất bại và tính nguyên tử; AOP không tự giải quyết.

### 12.3. Kiểm tra kỹ thuật

Một chính sách chung về context, cấu hình hoặc điều kiện thực thi có thể được kiểm tra trước nhiều method. Nhưng phải kiểm tra bao phủ, lỗi và khả năng bypass. Quy tắc miền quan trọng vẫn nên có hợp đồng rõ ở nơi sở hữu nghiệp vụ.

### 12.4. Metrics lượt bắt đầu

Một counter tăng ở before đo số lượt **đi vào join point được chọn**. Nếu target throw, lượt vào vẫn được tính. Nếu cần phân biệt success/failure, phải có phần quan sát hoàn tất.

### 12.5. Khi nào không phù hợp?

| Nhu cầu | Before đơn lẻ? | Khả năng phù hợp hơn |
|---|---|---|
| Ghi nhận lượt bắt đầu | Có | Before |
| Quan sát giá trị trả về | Không | After returning / around |
| Ghi ngoại lệ target | Không | After throwing / around |
| Đo latency chính xác | Không | Before + after có context, hoặc around |
| Cleanup bắt buộc | Không | After/finally hoặc around với finally |
| Retry nhiều lần | Không | Around/Decorator hoặc điều phối retry |
| Cache trả kết quả không gọi target | Không | Around hoặc thành phần có quyền điều phối |
| Thay kết quả trả về | Không theo semantics thông thường | Around hoặc xử lý output được định nghĩa |

## 13. Lỗi thường gặp và cách phòng tránh

**Lỗi 1: Nhầm “trước” với “đã thành công”.** Before chỉ chứng minh đã đi vào điểm; target chưa xử lý xong. Hãy dùng nhãn event đúng.

**Lỗi 2: Điểm cắt quá rộng.** Mọi method đều kích hoạt log, kể cả helper logging, tạo reentrancy hoặc spam. Hãy chọn ranh giới rõ và loại trừ hạ tầng advice khi cần.

**Lỗi 3: Advice tự ném lỗi ngoài ý định.** Logging lỗi I/O làm target không chạy. Xác định rõ policy: fail-open hay fail-closed theo yêu cầu thực tế, không giấu lựa chọn đó.

**Lỗi 4: Tưởng before có thể thay return trực tiếp.** Before không tự có kết quả target và không quản lý proceed như around.

**Lỗi 5: Quên đường gọi trực tiếp target.** Khi dùng proxy, caller có thể bỏ qua interception nếu cầm object gốc.

**Lỗi 6: Nhầm call với execution.** Cùng một nghiệp vụ có nhiều join point; placement quyết định event được đếm.

**Lỗi 7: Bỏ qua thứ tự aspect.** Hai before có thể phụ thuộc lẫn nhau nhưng thứ tự không được định nghĩa theo giả định của người viết. Cần precedence và test.

**Lỗi 8: Đọc dữ liệu nhạy cảm.** Log toàn bộ argument/target có thể lộ token và dữ liệu cá nhân. Chỉ ghi những trường cần thiết.

**Lỗi 9: Dùng trạng thái global không đồng bộ.** Advice chạy đồng thời, một counter hoặc context mutable không an toàn gây sai metric.

**Lỗi 10: Kiểm thử bằng cách gọi advice thủ công.** Test đó chỉ kiểm tra nội dung hàm, chưa chứng minh weaving/pointcut thực sự hoạt động.

## 14. Quy trình thiết kế và kiểm thử before advice

1. **Xác định sự kiện cần quan sát:** ví dụ “mỗi lần thực thi public operation” hoặc “mỗi call từ nhóm caller A”. Diễn đạt cụ thể, tránh “mọi request” khi chưa có ranh giới request.
2. **Chọn loại join point:** call hay execution, hoặc điểm khác nếu được engine hỗ trợ.
3. **Viết pointcut với phạm vi ổn định:** kết hợp signature/type/annotation/context khi cần, tránh match rộng ngoài ý định.
4. **Viết before nhỏ và dự đoán side effect:** xác định nó có thể throw không, có mutate state không, cần dữ liệu nào.
5. **Xác minh cơ chế dệt:** đúng artifact, class loader, proxy reference hoặc agent; kiểm tra đường gọi thật.
6. **Thử ca khớp và không khớp:** đảm bảo event xuất hiện đúng nơi, không xuất hiện ngoài phạm vi.
7. **Thử ngoại lệ:** before throw và target throw là hai trường hợp khác nhau; kiểm tra body gốc có chạy không.
8. **Thử nested/retry/self-invocation:** xác nhận số lần chính xác và đường đi bypass nếu có.
9. **Thử nhiều aspect:** xác định precedence và logging sequence.
10. **Đo trên workload thật:** chi phí của logging, reflection, lock, allocation, network I/O có thể chiếm tỷ lệ lớn.
11. **Đảm bảo bảo mật dữ liệu:** không lưu bí mật/PII tùy ý, không giữ reference target lâu.
12. **Lưu regression test:** sau khi thêm subclass, đổi tên method, tách class hoặc thay cấu hình weave, các join point vẫn đúng mong đợi.

### Ma trận kiểm thử gợi ý

| Tình huống | Cần chứng minh |
|---|---|
| Pointcut khớp | Before chạy trước thân được chọn |
| Pointcut không khớp | Advice không chạy |
| Before ném lỗi | Target không tự chạy tiếp ở đường lỗi đó |
| Target ném lỗi | Before đã chạy, lỗi truyền theo hợp đồng |
| Caller bypass proxy | Interceptor không xuất hiện trên đường bypass |
| Gọi method nội bộ | Có thể bỏ qua proxy; kiểm tra theo cơ chế thật |
| Hai aspect cùng khớp | Precedence và số lượt ổn định |
| Recursion hoặc retry | Mỗi event phản ánh đúng biên đã chọn |
| Subclass override | Tập execution được chọn vẫn đúng |
| Thực thi đa luồng | Advice quản lý trạng thái an toàn |

## 15. Tự kiểm tra

**Câu 1.** Before advice chạy trước phương thức save rồi save throw. Có thể nói before advice không chạy vì save thất bại không?

**Đáp:** Không. Before đã chạy trước khi target throw.

**Câu 2.** Ghi “thanh toán hoàn tất” trong before có chính xác không?

**Đáp:** Không. Đó là lời khẳng định về tương lai chưa xảy ra.

**Câu 3.** Nếu before advice tự throw, target có chắc vẫn chạy không?

**Đáp:** Không; trên đường ngoại lệ không bị tầng khác bắt và tiếp tục, target có thể không được thực hiện.

**Câu 4.** Tại sao call và execution có thể khiến một request tạo hai bản ghi before?

**Đáp:** Vì đó là hai join point khác nhau, cùng được pointcut lựa chọn.

**Câu 5.** Vì sao original.process trong Java demo không in before?

**Đáp:** Vì nó bỏ qua reference dynamic proxy và đi thẳng vào Core.

**Câu 6.** Before có thể đọc kết quả trả về của target tại thời điểm bắt đầu không?

**Đáp:** Không. Phải đợi target hoàn tất và dùng advice phù hợp.

**Câu 7.** Khi target được retry ba lần, metric before đo điều gì?

**Đáp:** Tùy điểm đặt: có thể là số lần thử nếu inside retry, hoặc số yêu cầu bên ngoài nếu before ở biên ngoài retry.

**Câu 8.** Có thể tin một unit test gọi tay method ghi log là bằng chứng advice đã được weave đúng không?

**Đáp:** Không. Cần test tích hợp trên đường đi thật và kiểm tra kết quả pointcut.

## 16. Sơ đồ ghi nhớ

~~~text
                 POINTCUT (chọn join point)
                           │
                           ▼
                       Có khớp?
                    ┌──────┴──────┐
                   Không         Có
                    │             │
                    ▼             ▼
                Chạy gốc      BEFORE ADVICE
                                  │
                             ┌────┴────┐
                          Kết thúc    Throw
                          bình thường   │
                             │         ▼
                             ▼       Lỗi trước
                       JOIN POINT     target
                       TIẾP TỤC       có thể
                             │        không chạy
                         ┌───┴───┐
                         ▼       ▼
                      Trả về  Target throw
~~~

**Nguyên lý:** before advice áp dụng hành vi **trước một join point thực sự được chọn và intercept**, có thể nhìn metadata/context đã tồn tại, nhưng không có kết quả tương lai của target. Tính đúng đắn phụ thuộc **loại join point, phạm vi pointcut, đường weaving/interception, thứ tự advice, ngoại lệ và side effect**. Nếu cần hoàn tất, kết quả, cleanup, retry hoặc thay return, hãy dùng mô hình advice hay cơ chế điều phối có khả năng tương ứng.

## Tài liệu đọc thêm

- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): before/after/around, join point và precedence của một ngôn ngữ AOP cụ thể.
- [Java Language Specification, Java SE 17, §15.12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): Java method invocation, argument evaluation và dynamic method lookup.
- [JDK 17 InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): cơ chế JDK proxy dùng trong ví dụ chạy được.
