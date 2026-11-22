# Khả năng của mô hình AOP phụ thuộc ngôn ngữ và công cụ

## 1. Điều cần hiểu trước tiên

**Aspect-Oriented Programming (AOP)** là mô hình tổ chức những hành vi xuyên suốt nhiều phần chương trình thành các **aspect**, kết hợp hành vi ấy vào những **điểm thực thi** được chọn. Những khái niệm như *join point*, *pointcut*, *advice*, *aspect* và *weaving* giúp ta mô tả mục tiêu. Tuy nhiên, **không có bảo đảm rằng mọi ngôn ngữ hay mọi công cụ AOP đều hiện thực đầy đủ cùng một mô hình**.

Chẳng hạn, hai công cụ cùng cho phép “chạy mã trước một phương thức” nhưng có thể khác biệt căn bản:

- Một công cụ chỉ can thiệp khi **caller gọi qua proxy**; đối tượng gốc được gọi trực tiếp sẽ không bị chặn.
- Một công cụ dệt hành vi vào **bytecode của phương thức**, nên có thể nhìn thấy một số đường thực thi mà proxy không quan sát được.
- Một công cụ chỉ hỗ trợ **method execution**; một công cụ khác có thể hỗ trợ thêm **method call**, truy cập trường, constructor hoặc xử lý ngoại lệ.
- Một công cụ nhận pointcut tĩnh tại build time; một công cụ khác chọn điểm dựa trên thông tin runtime.
- Một công cụ cho phép advice chỉ quan sát; công cụ khác cho phép thay đối số, kết quả, exception hoặc quyết định có tiếp tục target hay không.

Đây là sự khác nhau về **năng lực thực tế**, không chỉ là khác tên API. Muốn dự đoán đúng chương trình, cần xem chính xác ngôn ngữ, công cụ, phiên bản, thời điểm weaving, cách cấu hình và đường gọi.

**Mục tiêu bài học:** Sau khi học, bạn có thể phân tích một cơ chế AOP bất kỳ bằng bộ câu hỏi nhất quán: nó quan sát được điểm gì, chọn điểm bằng gì, advice làm được gì, kết hợp mã thế nào, giới hạn tại đâu, và ta chứng minh hành vi thực tế ra sao.

## 2. Ba tầng quyết định khả năng AOP

### 2.1. Tầng ngôn ngữ lập trình

Đặc tính ngôn ngữ tạo ra cơ sở cho việc can thiệp:

- **Kiểu và dispatch:** Interface, kế thừa, virtual dispatch, phương thức tĩnh, private/final, extension method, overload và generics quyết định vị trí một lớp bọc có thể tác động.
- **Reflection và metadata:** Có lấy được chữ ký, annotation, kiểu runtime, đối số hay không? Annotation có tồn tại ở runtime hay chỉ ở giai đoạn biên dịch?
- **Cơ chế mở rộng:** Ngôn ngữ có decorator, macro, metaprogramming, compile-time transform, dynamic proxy hoặc API thao tác code/bytecode không?
- **Mô hình lỗi:** Exception, kết quả biểu diễn lỗi, cancellation và cleanup có được advice quan sát hoặc thay đổi không?
- **Concurrency:** Thread, coroutine, task bất đồng bộ, callback, event loop và cách truyền context ảnh hưởng trực tiếp đến ý nghĩa trước/sau một join point.
- **Runtime và mã biên dịch:** Bytecode có thể biến đổi khác với binary native hoặc code bị tối ưu/inlining. Một hook ở nguồn chưa chắc tồn tại tương đương tại runtime.

Ngôn ngữ cho phép một kỹ thuật **không có nghĩa công cụ cụ thể đã triển khai kỹ thuật ấy**. Ví dụ, Java có annotation và reflection, nhưng riêng việc khai báo annotation không tự chạy advice.

### 2.2. Tầng công cụ hoặc framework AOP

Công cụ định nghĩa **join-point model**: tập điểm thực thi có thể chọn và hình thức chọn. Nó cũng quyết định loại advice, cách truyền ngữ cảnh, thứ tự ưu tiên, khả năng tạo aspect theo đối tượng hoặc luồng điều khiển, cùng cơ chế weaving.

Không nên suy luận từ một khái niệm tổng quát ra chức năng cụ thể:

- “Có pointcut” không kéo theo “có thể chọn mọi field access”.
- “Có around advice” không tự bảo đảm được đổi đối số hoặc gọi tiếp nhiều lần.
- “Có marker/annotation” không tự bảo đảm matcher kiểm tra đúng nơi marker được khai báo.
- “Có proxy” không đồng nghĩa “can thiệp được các lời gọi nội bộ”.
- “Có weaving” không tự bảo đảm tương thích mọi bytecode hoặc mọi môi trường nạp lớp.

Cần tra cứu khả năng theo **bản triển khai đang dùng**, rồi xác nhận lại bằng thử nghiệm nhỏ.

### 2.3. Tầng cấu hình và môi trường thực thi

Cùng một công cụ còn có thể hành xử khác nhau theo cấu hình:

- Aspect đã được đăng ký và kích hoạt ở đúng module chưa?
- Các lớp cần can thiệp có đi qua classloader/transformer được cấu hình không?
- Artifact chạy có phải bản đã được weave đúng phiên bản không?
- Runtime có cho phép instrumentation, mở module hoặc truy cập metadata cần thiết không?
- Proxy có được trao cho caller, hay caller vẫn giữ tham chiếu tới target?
- Thứ tự advice, cơ chế khởi tạo và trạng thái aspect có được quy định không?

Do đó, tuyên bố “AOP hỗ trợ X” chỉ đáng tin khi hoàn chỉnh thành: **“Công cụ T, với cấu hình C và môi trường R, hỗ trợ X ở những điểm Y, với giới hạn Z.”**

## 3. Bản đồ khả năng theo từng thành phần mô hình AOP

| Thành phần | Câu hỏi về khả năng | Khác biệt thường gặp |
| --- | --- | --- |
| **Join point** | Những sự kiện nào có thể bị can thiệp? | Method execution, method call, constructor, field get/set, exception handler hoặc chỉ lời gọi qua wrapper. |
| **Pointcut** | Chọn các sự kiện ấy bằng thông tin gì? | Chữ ký, tên, package, kiểu, marker, đối tượng runtime, context luồng điều khiển hoặc predicate tùy biến. |
| **Advice** | Chạy khi nào và can thiệp sâu tới đâu? | Before, after-returning, after-throwing, finally, around; quan sát thuần hoặc được phép thay hợp đồng. |
| **Join-point context** | Advice nhìn thấy gì? | Tên phương thức, target, caller, đối số, result, exception, metadata, context runtime. |
| **Weaving** | Hành vi được nối vào chương trình ở đâu? | Proxy runtime, biến đổi nguồn, biến đổi bytecode khi build, khi load, instrumentation runtime. |
| **Aspect lifecycle** | Có bao nhiêu instance, trạng thái sống bao lâu? | Singleton, mỗi target, mỗi luồng/ngữ cảnh hoặc mô hình lifecycle riêng. |
| **Precedence** | Nhiều aspect khớp cùng điểm thì chạy thứ tự nào? | Thứ tự được khai báo tường minh, mặc định của công cụ hoặc thứ tự không được bảo đảm. |
| **Introduction** | Có thể mở rộng kiểu/interface/member? | Một số công cụ có thể giới thiệu hành vi/thành viên; nhiều cơ chế proxy đơn giản không có. |
| **Tooling** | Debug/inspect/verify được mã đã can thiệp không? | Khác nhau về source map, bytecode inspection, log matching, trace và tích hợp trình biên dịch. |

Hai công cụ có thể tương đương ở hàng “Advice: before” nhưng khác hoàn toàn ở hàng “Join point: field access”. Khi đánh giá AOP, phải đi theo **cột khả năng cụ thể**, không theo nhãn sản phẩm.

## 4. Join-point model: khác biệt nền tảng nhất

### 4.1. Method execution và method call không giống nhau

Xét mã minh họa:

```java
class ReportService {
    void generate() {
        save();
    }
    void save() {
        // lưu báo cáo
    }
}
```

- **Execution join point** của `save()`: sự kiện khi phần thân `save` đang được thực thi.
- **Call join point** của `save()`: điểm mã gọi `save()`, ở đây nằm trong `generate()`.

Một số ngôn ngữ/công cụ phân biệt được hai loại; một số chỉ cung cấp một loại hoặc một abstraction khác. Nếu advice gắn ở phía **caller**, ngữ nghĩa và số điểm khớp có thể khác với advice gắn ở **callee**. Ví dụ, nhiều vị trí gọi cùng `save()` tạo ra nhiều vị trí *call*, trong khi định nghĩa *execution* trỏ vào nơi phương thức chạy.

Không được viết quy tắc pointcut dựa trên giả định rằng hai sự kiện là một.

### 4.2. Không phải cơ chế nào cũng thấy field, constructor và exception handler

Một số mô hình join point có thể biểu diễn:

- Đọc hoặc ghi trường.
- Khởi tạo đối tượng và/hoặc thực thi constructor.
- Khởi tạo lớp.
- Bắt ngoại lệ tại handler.
- Thực thi advice hoặc những sự kiện đặc thù khác.

Nhưng một **dynamic proxy chỉ triển khai interface phương thức** không tự chặn phép gán `object.field = value`, truy cập `object.field`, lời gọi constructor hoặc các lệnh trong thân phương thức của target. Nếu ứng dụng cần các loại điểm ấy, cần tìm cơ chế hỗ trợ tương ứng; cũng phải đánh giá các rủi ro của việc biến đổi code.

### 4.3. Các điểm bị tối ưu hoặc không tồn tại theo cùng cách

Ngôn ngữ động có thể cho phép thay thuộc tính của object hoặc bọc hàm lúc chạy, nhưng đóng gói, built-in/native function, module scope hay cơ chế binding có thể làm một số đường gọi không đi qua wrapper. Ngôn ngữ biên dịch có thể có inlining, generic specialization, native code và các hạn chế biến đổi binary.

Vì thế câu hỏi đúng không phải “ngôn ngữ này có AOP không?”, mà là **“Với điểm thực thi đang cần, công cụ này đặt hook được ở đâu và bằng chứng nào xác nhận hook được kích hoạt?”**

## 5. Pointcut: cú pháp, khả năng biểu đạt và thời điểm đánh giá

Một pointcut có thể sử dụng các loại tiêu chí:

| Tiêu chí | Ví dụ ý tưởng | Điều cần xác minh |
| --- | --- | --- |
| Chữ ký/kiểu tĩnh | Chọn `public` method ở một interface. | Có nhận diện overload, generic bridge, inherited method không? |
| Namespace/package/module | Chọn nhóm thao tác trong một module. | Có thể loại trừ module chứa chính logging/advice để tránh recursion không? |
| Metadata | Chọn method được gắn marker `@Observed`. | Metadata có runtime retention? Được đặt trên interface hay implementation? Có kế thừa không? |
| Đối tượng runtime | Chọn lời gọi trên object thuộc một subtype. | Công cụ hỗ trợ binding kiểu runtime hay chỉ xét chữ ký tĩnh? |
| Tham số/context | Chỉ chọn lời gọi ở một ngữ cảnh. | Có thể lấy đúng đối số; đánh giá predicate trước hay sau biến đổi? |
| Control flow | Chọn sự kiện xảy ra trong phạm vi một lời gọi gốc. | Có hỗ trợ control-flow pointcut và ngữ nghĩa thread/async tương ứng không? |

Ví dụ mô tả **giả mã**, không phải cú pháp được bảo đảm của bất cứ engine nào:

```text
pointcut:
    execution(public method in package "storage")
    AND hasMarker("Observed")
    AND NOT insidePackage("instrumentation")
```

Ở công cụ chỉ có API wrapper, bạn phải tự hiện thực predicate để chọn những method đi qua wrapper. Ở công cụ có ngôn ngữ pointcut, có thể khai báo một biểu thức tương đương nếu đầy đủ loại matcher cần dùng.

**Tĩnh và động:** Một số phần điều kiện có thể được xác định khi build/weave, nhưng một điều kiện phụ thuộc đối tượng hoặc đối số phải được kiểm tra tại runtime. Phân tách này ảnh hưởng đến khả năng tối ưu, chi phí mỗi lần gọi và cách đọc biểu thức.

**Độ phủ:** Cần phân biệt “rule chọn đúng danh sách method” với “mọi lời gọi tới method đó đều đi qua hook”. Đặc biệt ở mô hình proxy, matching chính xác vẫn chưa đủ nếu call path không qua proxy.

## 6. Advice: tên giống nhau nhưng quyền can thiệp khác nhau

Các loại advice quen thuộc gồm:

1. **Before:** chạy trước điểm được chọn.
2. **After returning:** chạy khi điểm đó trả về bình thường.
3. **After throwing:** chạy khi điểm đó kết thúc bởi lỗi/exception phù hợp.
4. **After/finally:** xử lý khi kết thúc qua cả đường thành công và lỗi.
5. **Around:** bao quanh quá trình thực thi, thường có cách tiếp tục vào phần bên trong.

Một số công cụ không có đủ năm loại dưới đúng những tên ấy; có thể chỉ cho phép wrapper/around rồi yêu cầu người dùng tự hiện thực hành vi trước, sau và xử lý lỗi.

### 6.1. `proceed` là khả năng cần khảo sát

Trong mô hình around, thao tác thường gọi là `proceed` chuyển quyền thực thi cho phần bên trong chuỗi advice/target. Nhưng phải kiểm tra:

- Có bắt buộc gọi một lần hay được gọi 0/nhiều lần?
- Có được thay đối số khi gọi tiếp hay không?
- Có thể sửa hoặc thay giá trị trả về không?
- Exception có được truyền lại nguyên dạng hay bị bọc?
- Nếu advice tự lỗi, caller quan sát loại lỗi nào?

Ví dụ giả mã:

```text
around():
    started = monotonicClock()
    try:
        return proceed()
    finally:
        reportDuration(monotonicClock() - started)
```

Đây là mô tả ý tưởng. Tên hàm, cách nhận result/exception, việc truyền tham số và `finally` thực tế tùy công cụ/language. Chỉ đo thời gian một cách chính xác khi hook bao quanh đúng **khoảng công việc cần đo**.

### 6.2. Tại sao khả năng “gọi nhiều lần” đáng quan tâm?

Nếu advice retry bằng cách gọi tiếp hai lần, một thao tác tạo hóa đơn có thể tạo **hai hóa đơn**. Kỹ thuật AOP có thể thực hiện được việc này không đồng nghĩa nó đúng về nghiệp vụ. Chỉ cho phép retry khi đã xác định idempotency, timeout tổng, loại lỗi thử lại được và cách chống trùng lặp.

### 6.3. Binding context không đồng nhất

Một số API cung cấp đối số, tên method, đối tượng receiver, caller, annotation, result và exception; có API chỉ cung cấp callable để tiếp tục. Dữ liệu thu thập ở lúc **call** có thể khác dữ liệu ở lúc **execution**. Chỉ nên dùng những trường context mà công cụ thực sự có hợp đồng hỗ trợ.

## 7. Weaving: cùng aspect, đường chạy có thể khác nhau

### 7.1. Bọc lời gọi bằng proxy hoặc decorator

Sơ đồ:

```text
client -> proxy/wrapper -> [advice] -> target.method()
client -----------------------------> target.method()
                                  (bỏ qua proxy)
```

Cơ chế này phù hợp khi có biên đối tượng rõ và caller nhận proxy thay cho target. Với JDK dynamic proxy, proxy cài các **interface**; callback handler quan sát những lời gọi được phát qua proxy. Nó không sửa class gốc, không tự thay đổi mọi tham chiếu tới target, và không tự can thiệp lời gọi `this.otherMethod()` bên trong target.

Proxy dựa trên lớp có phạm vi khác vì thường phụ thuộc khả năng tạo subtype/override; `final`, `private` và constructor cần được xét riêng theo cơ chế cụ thể.

### 7.2. Dệt vào source hoặc bytecode

Một công cụ weaving có thể kết hợp advice vào mã tại compile time, sau compile, tại lúc load class, hoặc thông qua một cơ chế instrumentation runtime. Thời điểm khác nhau dẫn tới cách build/test/deploy/debug khác nhau.

Các câu hỏi kiểm chứng:

- File nguồn/bytecode nào đã được weave?
- Module và classloader nào nằm trong phạm vi?
- Có tình huống class đã được load trước khi agent/transformer kích hoạt không?
- Mã đã tối ưu, mã sinh tự động và các dependency có nằm trong vùng hỗ trợ không?
- Có cách inspect bytecode hoặc xác nhận danh sách join point thật sự được chọn không?
- Thay phiên bản JDK/compiler/tool có thay tập điểm hỗ trợ không?

Không nên coi weaving tự động “mạnh hơn trên mọi phương diện”. Nó có thể cho phạm vi join point rộng nhưng chi phí build, độ khó gỡ lỗi, yêu cầu tương thích bytecode và nguy cơ thay đổi nhiều module cũng lớn hơn.

### 7.3. Metadata không tự thực thi

Annotation/attribute chỉ là thông tin. Để tạo hành vi, cần **một thành phần đọc metadata**, chọn điểm can thiệp và gắn advice. Trên Java, annotation processing tiêu chuẩn chủ yếu xử lý thông tin trong quá trình biên dịch và có thể sinh file; nó **không mặc nhiên viết lại phần thân mọi phương thức**. Muốn thực hiện kiểu đó phải dùng cơ chế biến đổi hoặc weaving phù hợp.

## 8. So sánh các họ kỹ thuật

Bảng sau là **phân loại kỹ thuật**, không phải lời hứa mọi thư viện thuộc một họ đều hỗ trợ toàn bộ thuộc tính.

| Họ triển khai | Điểm thường nhìn thấy | Cơ chế | Giới hạn nổi bật |
| --- | --- | --- | --- |
| **Wrapper/decorator tường minh** | Lời gọi qua wrapper. | Object gọi object khác với logic trước/sau. | Chỉ áp dụng nơi chủ động dùng wrapper. |
| **Dynamic proxy theo interface** | Lời gọi các method interface qua proxy. | Runtime tạo đối tượng proxy và handler. | Target trực tiếp và self-call không tự đi qua handler; phụ thuộc interface. |
| **Class proxy/subclass** | Lời gọi có thể dispatch qua method được ghi đè/chặn. | Lớp đại diện hoặc subclass. | Phụ thuộc override, visibility, finality, construction và khả năng runtime sinh lớp. |
| **Source/AST transformation** | Những cấu trúc nguồn công cụ có thể nhận diện. | Biến đổi chương trình trước/sát lúc biên dịch. | Ràng buộc compiler, syntax và pipeline build. |
| **Bytecode weaving** | Những join point có thể biểu diễn trong bytecode và được công cụ hỗ trợ. | Chỉnh bytecode trước hoặc trong quá trình nạp/chạy. | Tương thích định dạng bytecode, classloader, agent/build và debugging. |
| **Runtime instrumentation** | Những điểm runtime mà bộ instrumenter có thể can thiệp. | Transformer/hook tại runtime. | Tính khả dụng của API instrumentation; có thể chịu ràng buộc về quyền, startup và tải lớp. |
| **Language-level decorator/macro/metaprogramming** | Các function, method hoặc cú pháp ngôn ngữ cho phép bọc/biến đổi. | Mở rộng/ngữ nghĩa tích hợp của ngôn ngữ hoặc thư viện. | Độ phủ chịu giới hạn binding, đặc tính gọi hàm và khả năng truy cập implementation. |

**Cẩn thận với từ “AOP”:** Một decorator hoặc proxy tự viết có thể hiện thực một phần ý tưởng AOP nhưng không tự trở thành hệ thống pointcut/weaving hoàn chỉnh. Ngược lại, công cụ trình biên dịch có thể hỗ trợ join point ít thấy ở proxy mà không cho phép thay đổi mọi hành vi runtime.

## 9. Ví dụ Java 17 — chứng minh một khả năng và giới hạn của JDK dynamic proxy

Chương trình dùng Java chuẩn: interface `TaskApi`, target `TaskService`, annotation `@Tracked` ở method interface và `InvocationHandler`. Handler chỉ ghi advice cho lời gọi phương thức có marker. Cách triển khai này minh họa **pointcut rất nhỏ bằng predicate Java** và **before/after** trên method invocation qua proxy. Đây **không phải** một bộ engine AOP tổng quát.

Tạo tệp **`AopCapabilityDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AopCapabilityDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Tracked { }

    interface TaskApi {
        @Tracked
        String run(String id);
        String status();
    }

    static final class TaskService implements TaskApi {
        @Override
        public String run(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            System.out.println("TARGET run " + id);
            return "DONE " + id;
        }

        @Override
        public String status() {
            System.out.println("TARGET status");
            return "READY";
        }
    }

    static TaskApi monitored(TaskApi target) {
        return (TaskApi) Proxy.newProxyInstance(
                TaskApi.class.getClassLoader(),
                new Class<?>[] { TaskApi.class },
                (proxy, method, args) -> invoke(target, method, args)
        );
    }

    static Object invoke(TaskApi target, Method method, Object[] args)
            throws Throwable {
        boolean selected = method.isAnnotationPresent(Tracked.class);
        if (selected) {
            System.out.println("ADVICE before " + method.getName());
        }
        try {
            Object result = method.invoke(target, args);
            if (selected) {
                System.out.println("ADVICE returning " + method.getName());
            }
            return result;
        } catch (InvocationTargetException ex) {
            if (selected) {
                System.out.println("ADVICE throwing " + method.getName());
            }
            throw ex.getCause();
        }
    }

    public static void main(String[] args) {
        TaskApi target = new TaskService();
        TaskApi proxy = monitored(target);

        System.out.println("CALLER " + proxy.run("T-17"));
        System.out.println("CALLER " + proxy.status());

        try {
            proxy.run("");
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER error " + ex.getMessage());
        }

        System.out.println("CALLER " + target.run("DIRECT"));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac AopCapabilityDemo.java
java AopCapabilityDemo
```

Đầu ra chuẩn:

```text
ADVICE before run
TARGET run T-17
ADVICE returning run
CALLER DONE T-17
TARGET status
CALLER READY
ADVICE before run
ADVICE throwing run
CALLER error id required
TARGET run DIRECT
CALLER DONE DIRECT
```

### Những điều chương trình **thật sự** chứng minh

1. **Có can thiệp phương thức ở biên interface:** `proxy.run(...)` đi qua handler. Đây là khả năng của đối tượng do `Proxy.newProxyInstance` tạo.
2. **Có chọn điểm bằng metadata:** Handler nhận `Method` từ lời gọi interface và kiểm tra `@Tracked`. Phương thức `status()` vẫn được chuyển qua handler nhưng không kích hoạt các dòng `ADVICE`.
3. **Có quan sát đường thành công/lỗi:** Khi `run` trả về bình thường, handler in `returning`; khi target ném `IllegalArgumentException`, reflective invocation bọc nó vào `InvocationTargetException`; handler gỡ nguyên nhân rồi in `throwing`, caller nhận lỗi gốc.
4. **Gọi trực tiếp bỏ qua cơ chế:** `target.run("DIRECT")` chạy nghiệp vụ mà không có `ADVICE`. Điều này chứng minh đường gọi quan trọng hơn việc phương thức interface có annotation.
5. **Marker nằm trên interface:** Nếu chỉ chuyển annotation sang implementation, biểu thức `method.isAnnotationPresent(Tracked.class)` trong ví dụ sẽ không tự tìm annotation trên phương thức triển khai. Điểm nào được chọn phụ thuộc đúng cách viết matcher.

### Những điều ví dụ **không** chứng minh

- Không chứng minh can thiệp được constructor, field access, `private` method hoặc internal call trên `this`.
- Không chứng minh được capabilities của class proxy hay bytecode weaving.
- Không có pointcut DSL, `proceed` tổng quát, join point context hoàn chỉnh, aspect precedence hoặc lifecycle đa dạng.
- Không cung cấp audit bền vững, bảo mật, retry an toàn hay tracing xuyên tác vụ async.
- Không chứng minh overhead đáng kể hay nhỏ; cần đo trên workload tương ứng.

**Bài thực hành có ích:** Thêm một method không có marker, gọi qua proxy và kiểm tra không in advice; thêm marker vào method interface rồi gọi lại; thử gọi target trực tiếp. Từ ba phép thử, hãy viết **ma trận positive/negative** cho đúng đường gọi đang dùng.

## 10. Sự khác biệt trong kiểu, kế thừa và metadata

### 10.1. Visibility, finality và kế thừa

Với cơ chế tạo subclass để override, những method không thể override sẽ không thể bị chặn theo cách override thông thường. Với proxy interface, phạm vi là những method biểu diễn được trên các interface proxy cài. Với weaving bytecode, tập điểm can thiệp có thể khác; **đừng đem quy tắc của một họ triển khai áp vào họ khác**.

Ở Java, một lời gọi có thể đến method kế thừa, method bị override, bridge method do compiler sinh ra hoặc overload khác. Metadata gắn ở đâu, matcher nhìn vào đối tượng `Method` nào và JVM dispatch tới body nào là các câu hỏi khác nhau.

### 10.2. Annotation retention và nơi khai báo

Một marker được dùng để chọn pointcut tại runtime chỉ hữu dụng nếu metadata cần thiết còn có thể đọc tại runtime hoặc đã được công cụ xử lý ở thời điểm trước đó. Trên Java, `RetentionPolicy.RUNTIME` cho phép API reflection đọc annotation ở runtime; `SOURCE` và `CLASS` có ý nghĩa khác. Việc một annotation đánh dấu method trên interface **không bảo đảm** tự xuất hiện như một annotation trên implementation khi reflection được gọi ở đối tượng khác. Công cụ có thể tự xây matcher mạnh hơn, nhưng đó là **quyết định công cụ**.

### 10.3. Generic và method bridge

Compiler có thể tạo phương thức cầu nối (*bridge*) để duy trì dispatch sau type erasure. Một matcher dựa trên chữ ký thô có thể nhìn thấy method khác với chữ ký source mà người viết tưởng tượng. Công cụ thường có chiến lược riêng để xử lý bridge, synthetic, inherited và overridden methods. Khi phạm vi can thiệp quan trọng, nên thử tình huống generic và kế thừa thật thay vì chỉ dùng ví dụ không có inheritance.

## 11. Nhiều aspect: thứ tự, phạm vi và trạng thái

### 11.1. Thứ tự advice có thể làm thay đổi ý nghĩa

Hai advice dạng around có thể lồng nhau:

```text
A.before
    B.before
        target()
    B.after
A.after
```

Nếu đảo A/B, một advice đo thời gian có thể bao gồm hoặc loại trừ công việc của advice khác. Với retry, đo bên ngoài vòng retry cho **tổng thời gian**, đo bên trong có thể cho **thời gian từng lần thử**. Với audit hoặc transaction, thứ tự có thể quyết định liệu “thành công” được ghi trước hay sau một thao tác hoàn tất.

Thứ tự phải được xác nhận bằng khả năng *precedence/order* của công cụ và ca kiểm thử, không dựa vào thứ tự ngẫu nhiên trong cấu hình.

### 11.2. Lifecycle của aspect có thể khác

Một mô hình cung cấp aspect singleton chia sẻ trạng thái giữa mọi lời gọi; mô hình khác hỗ trợ instance theo target hoặc theo một luồng điều khiển. Trạng thái mutable trong aspect singleton cần được bảo vệ trước cạnh tranh. Một aspect theo đối tượng có quy tắc vòng đời khác, nhưng chỉ sử dụng được nếu công cụ hỗ trợ rõ.

Những thuật ngữ như *per-object*, *per-control-flow* mô tả **các lựa chọn có thể có trong một số công nghệ**, không phải phần bắt buộc trong mọi AOP.

### 11.3. Aspect có thể gây recursion/reentrancy

Giả sử advice ghi log bằng một method nằm trong chính tập pointcut. Việc ghi log có thể tiếp tục kích hoạt advice, dẫn tới đệ quy không mong muốn. Biên giới chọn điểm và loại trừ module instrumentation quan trọng hơn việc đổi tên advice. Nếu công cụ hỗ trợ biểu thức chọn theo control flow, cần hiểu cả ngữ nghĩa lồng nhau và tác vụ bất đồng bộ.

## 12. Async, exception và runtime context: nơi mô hình dễ bị hiểu sai

### 12.1. “After returning” khác “công việc đã xong”

Một phương thức có thể trả về `Future`, promise hoặc handle rất nhanh rồi hoàn tất công việc sau đó. Advice after-returning trên lần gọi **chỉ biết lần gọi trả handle đã hoàn tất**, trừ khi công cụ cung cấp hook theo ngữ nghĩa hoàn tất tác vụ.

Muốn đo toàn bộ thời gian hoặc lỗi cuối cùng, phải quan sát completion của tác vụ, không chỉ thời điểm tạo handle. Trên coroutine/event loop, thời điểm suspend/resume cũng có thể đòi hỏi hook riêng.

### 12.2. Thread-local context không mặc nhiên đi theo mọi tác vụ

Nhiều hệ thống dùng correlation ID, trace context hoặc dữ liệu xác thực theo thread. Nếu công việc chuyển sang thread khác hay callback, context có thể không tự đi cùng. Một AOP engine có hook ở phương thức không tự bảo đảm truyền context xuyên scheduler. Phải kiểm tra mô hình concurrency, chính sách propagation, cleanup và đường cancellation.

### 12.3. Exception có thể bị bọc hoặc đổi loại

Reflective invocation của Java có thể gói exception từ target trong `InvocationTargetException`, như ví dụ ở trên. Wrapper, coroutine hoặc task cũng có cơ chế biểu diễn lỗi khác. Advice muốn “giữ nguyên lỗi” phải xử lý theo đúng abstraction, không nuốt lỗi hoặc vô tình biến lỗi thành thành công.

Nếu advice tự ném exception trong `finally`, nó có thể che mất exception ban đầu. Với logging/metrics nên xác định fail-open hay fail-closed dựa trên hợp đồng; với audit bắt buộc hoặc kiểm tra quyền, quyết định này liên quan trực tiếp tính đúng đắn và cần thiết kế rõ ràng.

## 13. Kiểm chứng năng lực công cụ bằng ma trận, không bằng khẩu hiệu

Một thử nghiệm AOP nghiêm túc nên có **hai chiều**: loại join point và đường gọi. Ví dụ:

| Thử nghiệm | Câu hỏi cần chứng minh |
| --- | --- |
| Phương thức được chọn qua proxy | Advice có chạy đúng một lần, đúng thứ tự không? |
| Phương thức không được chọn qua proxy | Advice có thực sự không chạy không? |
| Gọi thẳng target | Handler có bị bỏ qua như dự kiến không? |
| Target tự gọi method khác | Self-invocation có đi qua hook theo cơ chế được chọn không? |
| Method overloaded/override/inherited | Matcher lấy đúng chữ ký và metadata không? |
| Method private/final/static | Điểm đó có nằm trong join-point model thực tế không? |
| Constructor hoặc field access | Cơ chế có hỗ trợ loại join point này không? |
| Target ném exception | Advice nào chạy; caller nhận lỗi gốc hay lỗi đã biến đổi? |
| Nhiều advice cùng khớp | Thứ tự có cố định và đúng hợp đồng không? |
| Tác vụ asynchronous | Advice đang quan sát việc gọi hay sự kiện hoàn tất thực? |
| Runtime/classloader khác | Hook có thực sự được cài trong artifact sẽ triển khai không? |
| Tải cao hoặc recursion | Advice có gây overhead, vòng lặp, rò context hoặc lộ dữ liệu không? |

Không nhất thiết mọi hàng đều phải “có”. Một thiết kế đúng có thể **cố ý không hỗ trợ** một số điểm. Mục tiêu kiểm thử là khớp với **hợp đồng được tuyên bố**, không phải biến một cơ chế nhỏ thành công cụ làm mọi việc.

### Checklist lựa chọn cơ chế

Trước khi nhận một công cụ AOP vào dự án, trả lời theo thứ tự:

1. **Chính sách cần tách là gì?** Có thực sự là hành vi kỹ thuật dùng chung, hay là quyết định nghiệp vụ cần tường minh?
2. **Cần loại join point nào?** Method execution/call, constructor, field access, xử lý lỗi hay hoàn tất tác vụ async?
3. **Cần pointcut biểu đạt gì?** Chữ ký, marker, kiểu runtime, đối số, ngữ cảnh luồng điều khiển?
4. **Advice có quyền gì?** Chỉ quan sát, thay input/output, gọi lại, chặn, hay tạo side effect?
5. **Weaving đặt ở đâu?** Interface wrapper, class proxy, build tool, classloader hay runtime agent?
6. **Các giới hạn nào quan trọng?** Self-call, method visibility, module/classloader, reflection, generic bridge, native runtime?
7. **Thứ tự và trạng thái ra sao?** Precedence, lifecycle, concurrency, exception và cleanup có contract không?
8. **Có chứng minh được không?** Positive test, negative test, integration test qua pipeline thật và benchmark phù hợp?

Nếu giải pháp chỉ đòi hỏi bọc vài object, decorator/interface proxy có thể đủ và dễ kiểm soát. Nếu yêu cầu điểm can thiệp sâu hơn, cần xem khả năng weaving cụ thể cùng chi phí kiểm thử, build và bảo trì. Nếu chính sách làm thay đổi quyết định nghiệp vụ, có thể cần domain policy hoặc workflow tường minh thay vì aspect.

## 14. Tình huống phân tích nâng cao

### Tình huống A — Đo thời gian lưu dữ liệu qua interface

**Yêu cầu:** Mọi lời gọi tới interface lưu trữ thông qua lớp ứng dụng đều cần ghi latency, không sửa giá trị trả về. **Phương án:** Dùng wrapper/proxy nếu kiểm soát được đường gọi và các điểm không đi qua wrapper đã được loại trừ. **Cần chứng minh:** Mọi caller dùng object được bọc, exception được bảo toàn và overhead chấp nhận được.

### Tình huống B — Cần can thiệp lúc ghi một field

**Yêu cầu:** Kiểm tra một sự kiện thay đổi trạng thái ngay khi lệnh ghi field diễn ra. **Giới hạn:** Interface dynamic proxy thông thường không chặn được thao tác ghi field trực tiếp. **Phương án:** Tốt nhất có thể là thiết kế lại setter/domain method tường minh; nếu cần AOP trên field access, phải dùng công cụ hỗ trợ join point đó và kiểm thử trên bytecode thật. Không suy ra khả năng từ từ khóa “AOP”.

### Tình huống C — Muốn dùng aspect để bảo vệ mọi đường truy cập dữ liệu

**Yêu cầu:** Không một lệnh truy cập trái phép nào được vượt qua. **Rủi ro:** Một nhánh gọi trực tiếp target, method không khớp pointcut hoặc module chưa được weave có thể bỏ qua chính sách. **Phương án:** Đặt kiểm tra quyền tại biên tin cậy và các bất biến nghiệp vụ; AOP có thể bổ sung kiểm tra kỹ thuật ở điểm đã được chứng minh, nhưng không được mặc định là lớp bảo vệ duy nhất.

### Tình huống D — Đo thời gian một công việc bất đồng bộ

**Yêu cầu:** Đo từ lúc gửi task đến lúc task thật sự hoàn tất. **Giới hạn:** Advice bao quanh method trả `Future` có thể chỉ đo thời gian tạo/sắp xếp task. **Phương án:** Quan sát completion của task/future bằng abstraction thích hợp; xác định riêng timeout, cancellation, exception và context propagation.

### Tình huống E — Tác động vào nhiều method có cùng marker

**Yêu cầu:** Gắn chính sách vào nhóm method khai báo marker. **Cần kiểm tra:** Marker ở interface hay implementation, retention, cơ chế tìm annotation, method được kế thừa/override, tên và chữ ký thay đổi sau refactor. Nếu matcher không tìm đúng metadata, aspect có thể không chạy dù source trông đã đánh dấu đủ.

## 15. Ngộ nhận thường gặp

**“Định nghĩa AOP có field join point, nên công cụ AOP tôi dùng cũng phải có.”** Sai: tập join point là một phần năng lực của công cụ.

**“Dùng annotation là đủ để phương thức được can thiệp.”** Sai: annotation chỉ là metadata; cần matcher và cơ chế kết hợp hành vi.

**“Proxy chặn được tất cả method cùng tên.”** Sai: phải xác định call path, interface/class proxy, visibility, dispatch và cách chọn method.

**“Weaving nghĩa là mọi thứ đều được can thiệp.”** Sai: weaving vẫn có tập điểm hỗ trợ, phạm vi artifact/classloader và cấu hình cụ thể.

**“Sau khi method trả về có nghĩa async job đã hoàn tất.”** Sai với method trả handle cho công việc tương lai, trừ khi có hook quan sát completion riêng.

**“Nếu test target trực tiếp chạy đúng, advice cũng sẽ chạy đúng.”** Sai: muốn kiểm tra AOP phải dùng cơ chế thật, cả test được chọn lẫn test loại trừ.

**“Một aspect hoạt động trong demo nên an toàn cho toàn ứng dụng.”** Sai: nhiều aspect, side effect, concurrency, exception, error handling và chi phí thực thi phải được kiểm chứng riêng.

## 16. Câu hỏi tự đánh giá

1. Hai công cụ đều có before advice, nhưng chỉ một công cụ can thiệp được constructor. Đây là khác biệt của thành phần nào trong mô hình AOP?
2. Vì sao kiểm tra `method.isAnnotationPresent` trên một `Method` của interface có thể cho kết quả khác khi marker chỉ đặt trên implementation?
3. Một `TaskService` được đưa vào proxy, nhưng nơi khác vẫn giữ `new TaskService()` rồi gọi trực tiếp. Điều gì xảy ra với advice của proxy?
4. Vì sao cần phân biệt method call và method execution khi viết pointcut?
5. Một around advice đo method trả `Future` sau 2 ms, trong khi tác vụ mất 5 giây. Số đo 2 ms phản ánh điều gì?
6. Công cụ hỗ trợ bytecode weaving. Có thể kết luận chắc chắn nó chặn được mọi thao tác đọc trường và mọi constructor không? Vì sao?
7. Nếu một advice ghi log chính method được pointcut chọn, nguy cơ nào xuất hiện?
8. Cần những kiểm thử nào trước khi tuyên bố một chính sách đã bao phủ đủ điểm thực thi?

**Đáp án gợi ý:** (1) Join-point model. (2) Runtime matcher nhận một `Method` cụ thể; metadata không mặc nhiên chuyển từ method triển khai sang method interface hay ngược lại. (3) Lời gọi trực tiếp bỏ qua proxy. (4) Chúng là hai loại sự kiện/điểm đặt hook có ngữ nghĩa khác nhau. (5) Thời gian gọi/đăng ký tác vụ, chưa chắc là thời gian hoàn tất. (6) Không; phải xác nhận loại join point, phạm vi bytecode, phiên bản và cấu hình. (7) Reentrant/recursive advice có thể chạy lặp vô hạn. (8) Positive/negative path, direct call, self-call, error, nhiều advice, async, cấu hình weave và benchmark theo yêu cầu.

## Kết luận

Mô hình AOP cung cấp **ngôn ngữ tư duy chung** để nói về concern, aspect, join point, pointcut, advice và weaving. Nhưng **năng lực thực thi** không chỉ đến từ định nghĩa; nó xuất hiện từ giao điểm của đặc tính ngôn ngữ, kỹ thuật công cụ và môi trường chạy. Hiểu giới hạn này giúp bạn chọn đúng kỹ thuật, kiểm soát phạm vi tác động và tránh áp đặt lên một proxy nhỏ những khả năng chỉ tồn tại ở một công cụ weaving khác. Trước khi tin rằng aspect sẽ chạy, hãy xác định **điểm nào được hỗ trợ, đường gọi nào đi qua hook, matcher nào đang dùng và phép thử nào chứng minh điều đó**.
